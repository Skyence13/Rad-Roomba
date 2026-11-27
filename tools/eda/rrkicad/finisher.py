"""Finisher: a plain grid maze router (A*) for the few connections the autorouter leaves open.

Runs inside the KiCad container on the routed, zone-filled board.  For every open
connection that KiCad's DRC reports (two items of one net, with positions), it searches
a path on the board's *signal* layers (plane layers are never routed on) through a
clearance-inflated occupancy grid:

* grid pitch `GRID` (0.05 mm), 8 directions, through vias between signal layers;
* a cell is blocked for a track centre when copper of another net is closer than
  clearance(both net classes) + half the track width + half a grid cell; for a via
  centre when any copper of another net on any layer is closer than clearance + via
  radius, when another drill is closer than the hole-to-hole rule, or when a same-net
  SMD pad would be touched;
* board edge / cut-out clearance and keep-out rule areas are obstacles;
* the search window grows (6 mm, 15 mm, whole board) until a path is found.

The path is simplified to straight segments and then re-checked with the exact
geometry of geom.Obstacles before it is accepted; nothing that fails the exact check is
added.  Added items are stored in route/<name>.finish.json together with the SHA-256
of the SES they complete, and re-applied by finish_pcb() on every later build that uses
the same SES (so a cached build reproduces them).  KiCad DRC then checks the result like
everything else - the finisher never marks anything as connected by itself.
"""
import hashlib
import heapq
import json
import math
import os
import re
import time

import numpy as np
import pcbnew

from .geom import Obstacles, MM, T

GRID = 0.05
VIA_COST = 40.0          # in grid steps (2 mm of track)


class _Bld:
    """Minimal stand-in for pcb.Builder that geom.Obstacles needs."""

    def __init__(self, board, pcb, fr):
        from .pcb import fillet, circle_pts
        self.b, self.pcb, self.fr = board, pcb, fr
        self.outline_dense = fillet(board.outline["pts"], board.outline["radius"])[1]
        self.cutout_polys = []
        for c in board.cutouts:
            self.cutout_polys.append(circle_pts(c["x"], c["y"], c["dia"]) if c["kind"] == "circle"
                                     else fillet(c["pts"], c.get("radius", 0))[1])
        self._all_keepouts = []
        cu = list(board.copper_layers)
        for z in pcb.Zones():
            if not z.GetIsRuleArea():
                continue
            ol = z.Outline()
            if ol.OutlineCount() < 1:
                continue
            o = ol.Outline(0)
            pts = [fr.user(o.CPoint(i)) for i in range(o.PointCount())]
            lays = [l for l in cu if z.GetLayerSet().Contains(pcb.GetLayerID(l))]
            self._all_keepouts.append({"_pts": pts, "layers": lays, "tracks": z.GetDoNotAllowTracks(),
                                       "vias": z.GetDoNotAllowVias()})


def _pip_grid(PX, PY, poly):
    inside = np.zeros(PX.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        inside ^= ((y1 > PY) != (y2 > PY)) & (PX < (x2 - x1) * (PY - y1) / (y2 - y1) + x1)
    return inside


def _segdist_grid(PX, PY, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return np.hypot(PX - ax, PY - ay)
    t = np.clip(((PX - ax) * dx + (PY - ay) * dy) / l2, 0.0, 1.0)
    return np.hypot(PX - (ax + t * dx), PY - (ay + t * dy))


class Window:
    def __init__(self, x0, y0, x1, y1, g=GRID):
        self.x0, self.y0, self.g = x0, y0, g
        self.nx = max(2, int(math.ceil((x1 - x0) / g)))
        self.ny = max(2, int(math.ceil((y1 - y0) / g)))
        self.X = x0 + (np.arange(self.nx) + 0.5) * g
        self.Y = y0 + (np.arange(self.ny) + 0.5) * g

    def sub(self, bb, grow):
        i0 = max(0, int(math.floor((bb[0] - grow - self.x0) / self.g)))
        i1 = min(self.nx, int(math.ceil((bb[2] + grow - self.x0) / self.g)) + 1)
        j0 = max(0, int(math.floor((bb[1] - grow - self.y0) / self.g)))
        j1 = min(self.ny, int(math.ceil((bb[3] + grow - self.y0) / self.g)) + 1)
        if i1 <= i0 or j1 <= j0:
            return None
        PX, PY = np.meshgrid(self.X[i0:i1], self.Y[j0:j1])
        return (slice(j0, j1), slice(i0, i1), PX, PY)

    def cell(self, x, y):
        return (min(self.nx - 1, max(0, int((x - self.x0) / self.g))), min(self.ny - 1, max(0, int((y - self.y0) / self.g))))

    def xy(self, i, j):
        return (self.x0 + (i + 0.5) * self.g, self.y0 + (j + 0.5) * self.g)


def _surface_dist(it, PX, PY):
    k = it["kind"]
    if k == "via":
        return np.hypot(PX - it["x"], PY - it["y"]) - it["r"]
    if k == "seg":
        return _segdist_grid(PX, PY, it["a"][0], it["a"][1], it["b"][0], it["b"][1]) - it["w"] / 2.0
    if it["circle"] is not None:
        return np.hypot(PX - it["cx"], PY - it["cy"]) - it["circle"]
    r = it["rect"]
    dx = np.maximum(np.maximum(r[0] - PX, 0.0), PX - r[2])
    dy = np.maximum(np.maximum(r[1] - PY, 0.0), PY - r[3])
    return np.hypot(dx, dy)


def _rasterize(obs, win, net, w, vr, vdrill, layers, soft_ok=None):
    """Blocked maps: track[layer] (ny, nx) and via (ny, nx).  With *soft_ok* (item -> bool),
    copper of items for which it returns True goes into separate "soft" maps instead
    (rip-up candidates); returns (trk, via, trk_soft, via_soft) then."""
    rr = obs.r
    q = 0.0       # no grid margin: optimistic raster, every path is re-checked exactly afterwards
    trk = {l: np.zeros((win.ny, win.nx), dtype=bool) for l in layers}
    via = np.zeros((win.ny, win.nx), dtype=bool)
    bb = (win.x0, win.y0, win.x0 + win.nx * win.g, win.y0 + win.ny * win.g)
    seen = set()
    trk_s = {l: np.zeros((win.ny, win.nx), dtype=bool) for l in layers}
    via_s = np.zeros((win.ny, win.nx), dtype=bool)
    for it in obs.near(*bb):
        if id(it) in seen:
            continue
        seen.add(id(it))
        same = it["net"] == net and net != ""
        soft = soft_ok is not None and not same and soft_ok(it)
        T_, V_ = (trk_s, via_s) if soft else (trk, via)
        c = obs.clr(net, it["net"])
        grow = max(c + w / 2.0, c + vr) + q + 0.6
        s = win.sub(it["bb"], grow)
        if s is None:
            continue
        sj, si, PX, PY = s
        d = _surface_dist(it, PX, PY)
        if not same:
            for l in layers:
                if l in it["layers"]:
                    T_[l][sj, si] |= d < c + w / 2.0 + q
            V_[sj, si] |= d < c + vr + q
        elif it["kind"] == "pad" and not it["drill"]:
            via[sj, si] |= d < vr + 0.05 + q
        hd = it.get("drill") or 0.0
        if hd:
            cx, cy = (it["x"], it["y"]) if it["kind"] == "via" else (it["cx"], it["cy"])
            V_[sj, si] |= np.hypot(PX - cx, PY - cy) < hd / 2.0 + vdrill / 2.0 + rr.min_hole_to_hole + obs.margin + q
    # board edge, cut-outs, keep-outs
    PX, PY = np.meshgrid(win.X, win.Y)
    inside = _pip_grid(PX, PY, obs.outline)
    ed = np.full(PX.shape, 1e9)
    polys = [obs.outline] + obs.cutouts
    for c in obs.cutouts:
        inside &= ~_pip_grid(PX, PY, c)
    for poly in polys:
        n = len(poly)
        for k in range(n):
            a, b = poly[k], poly[(k + 1) % n]
            if min(a[0], b[0]) > bb[2] + 3 or max(a[0], b[0]) < bb[0] - 3 or min(a[1], b[1]) > bb[3] + 3 or max(a[1], b[1]) < bb[1] - 3:
                continue
            ed = np.minimum(ed, _segdist_grid(PX, PY, a[0], a[1], b[0], b[1]))
    e = rr.edge_clearance + obs.margin + q
    for l in layers:
        trk[l] |= ~inside | (ed < e + w / 2.0)
    via |= ~inside | (ed < e + vr)
    for ko in obs.keepouts:
        kin = None
        if ko["tracks"] or ko["vias"]:
            kin = _pip_grid(PX, PY, ko["poly"])
            n = len(ko["poly"])
            kd = np.full(PX.shape, 1e9)
            for k in range(n):
                a, b = ko["poly"][k], ko["poly"][(k + 1) % n]
                kd = np.minimum(kd, _segdist_grid(PX, PY, a[0], a[1], b[0], b[1]))
        if ko["tracks"]:
            for l in layers:
                if l in ko["layers"]:
                    trk[l] |= kin | (kd < w / 2.0 + q)
        if ko["vias"]:
            via |= kin | (kd < vr + q)
    if soft_ok is not None:
        for l in layers:
            trk_s[l] &= ~trk[l]
        via_s &= ~via
        return trk, via, trk_s, via_s
    return trk, via


class Budget(Exception):
    pass


SOFT_COST = 30.0         # extra cost per grid step through rip-up candidate copper


def _astar(win, trk, via, layers, starts, goals, budget=1_500_000, trk_soft=None, via_soft=None, goal_mask=None):
    L, ny, nx = len(layers), win.ny, win.nx
    N = L * ny * nx
    blocked = np.stack([trk[l] for l in layers]).reshape(-1)
    vflat = via.reshape(-1)            # True = no via allowed here
    softc = np.stack([trk_soft[l] for l in layers]).reshape(-1) if trk_soft is not None else None
    vsoft = via_soft.reshape(-1) if via_soft is not None else None
    gcost = np.full(N, np.inf, dtype=np.float64)
    parent = np.full(N, -1, dtype=np.int64)
    goal = set()
    for (l, i, j) in goals:
        goal.add(l * ny * nx + j * nx + i)
    hw = 0.0 if goal_mask is not None else 1.0       # goal mask (any cell where it is True): Dijkstra
    gx = sum(g[1] for g in goals) / float(len(goals)) if goals else 0.0
    gy = sum(g[2] for g in goals) / float(len(goals)) if goals else 0.0
    heap = []
    for (l, i, j) in starts:
        s = l * ny * nx + j * nx + i
        gcost[s] = 0.0
        heapq.heappush(heap, (hw * math.hypot(i - gx, j - gy), 0.0, s))
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.41421356), (1, -1, 1.41421356), (-1, 1, 1.41421356), (-1, -1, 1.41421356)]
    pops = 0
    while heap:
        f, gc, s = heapq.heappop(heap)
        if gc > gcost[s]:
            continue
        if s in goal or (goal_mask is not None and gc > 0 and goal_mask[s % (ny * nx)]):
            path = []
            while s != -1:
                path.append(s)
                s = int(parent[s])
            return path[::-1]
        pops += 1
        if pops > budget:
            raise Budget()
        l, rem = divmod(s, ny * nx)
        j, i = divmod(rem, nx)
        base = l * ny * nx
        for di, dj, c in moves:
            ii, jj = i + di, j + dj
            if ii < 0 or jj < 0 or ii >= nx or jj >= ny:
                continue
            t = base + jj * nx + ii
            if blocked[t] and t not in goal:
                continue
            if di and dj and (blocked[base + j * nx + ii] or blocked[base + jj * nx + i]):
                continue           # no corner cutting past an obstacle
            ng = gc + c + (SOFT_COST * c if softc is not None and softc[t] else 0.0)
            if ng < gcost[t]:
                gcost[t] = ng
                parent[t] = s
                heapq.heappush(heap, (ng + hw * math.hypot(ii - gx, jj - gy), ng, t))
        if L > 1 and not vflat[j * nx + i]:
            for l2 in range(L):
                if l2 == l:
                    continue
                t = l2 * ny * nx + j * nx + i
                if blocked[t] and t not in goal:
                    continue
                ng = gc + VIA_COST + (SOFT_COST * 4 if (vsoft is not None and vsoft[j * nx + i]) or
                                      (softc is not None and softc[t]) else 0.0)
                if ng < gcost[t]:
                    gcost[t] = ng
                    parent[t] = s
                    heapq.heappush(heap, (ng + hw * math.hypot(i - gx, j - gy), ng, t))
    return None


def _simplify(win, layers, path):
    """Grid path -> list of (kind, data): ("seg", layer, a, b) / ("via", (x, y))."""
    ny, nx = win.ny, win.nx
    pts = []
    for s in path:
        l, rem = divmod(s, ny * nx)
        j, i = divmod(rem, nx)
        pts.append((l, i, j))
    out = []
    k = 0
    while k < len(pts) - 1:
        l, i, j = pts[k]
        if pts[k + 1][0] != l:
            out.append(("via", win.xy(i, j)))
            k += 1
            continue
        d = (pts[k + 1][1] - i, pts[k + 1][2] - j)
        m = k + 1
        while m + 1 < len(pts) and pts[m + 1][0] == l and (pts[m + 1][1] - pts[m][1], pts[m + 1][2] - pts[m][2]) == d:
            m += 1
        out.append(("seg", layers[l], win.xy(i, j), win.xy(pts[m][1], pts[m][2])))
        k = m
    return out


def _los(win, blocked, a, b):
    """Straight segment a-b (mm) crosses no blocked cell (sampled at a quarter cell)."""
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d / (win.g * 0.25)))
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        y = a[1] + (b[1] - a[1]) * k / n
        i, j = win.cell(x, y)
        if blocked[j, i]:
            return False
    return True


def _smooth(win, trk, route):
    """String pulling within each straight-layer run: drop intermediate points while the
    direct segment stays on free cells."""
    out = []
    k = 0
    while k < len(route):
        if route[k][0] != "seg":
            out.append(route[k])
            k += 1
            continue
        layer = route[k][1]
        pts = [route[k][2], route[k][3]]
        m = k + 1
        while m < len(route) and route[m][0] == "seg" and route[m][1] == layer:
            pts.append(route[m][3])
            m += 1
        blocked = trk[layer]
        a = 0
        keep = [pts[0]]
        while a < len(pts) - 1:
            b = len(pts) - 1
            while b > a + 1 and not _los(win, blocked, pts[a], pts[b]):
                b -= 1
            keep.append(pts[b])
            a = b
        for p0, p1 in zip(keep[:-1], keep[1:]):
            out.append(("seg", layer, p0, p1))
        k = m
    return out


def _touch(a, b):
    """Same-net copper items a and b touch on a common layer."""
    from .geom import seg_seg, pt_seg, pad_dist, pad_seg_dist
    if not (a["layers"] & b["layers"]):
        return False
    if a["kind"] == "pad" and b["kind"] != "pad":
        a, b = b, a
    ka, kb = a["kind"], b["kind"]
    eps = 0.002
    if ka == "seg" and kb == "seg":
        return seg_seg(a["a"], a["b"], b["a"], b["b"]) <= (a["w"] + b["w"]) / 2.0 + eps
    if ka == "seg" and kb == "via":
        return pt_seg(b["x"], b["y"], a["a"][0], a["a"][1], a["b"][0], a["b"][1]) <= b["r"] + a["w"] / 2.0 + eps
    if ka == "via" and kb == "seg":
        return _touch(b, a)
    if ka == "via" and kb == "via":
        return math.hypot(a["x"] - b["x"], a["y"] - b["y"]) <= a["r"] + b["r"] + eps
    if ka == "seg" and kb == "pad":
        return pad_seg_dist(b, a["a"], a["b"]) <= a["w"] / 2.0 + eps
    if ka == "via" and kb == "pad":
        return pad_dist(b, a["x"], a["y"]) <= a["r"] + eps
    if ka == "pad" and kb == "pad":
        r1, r2 = a["rect"], b["rect"]
        return not (r1[2] < r2[0] or r2[2] < r1[0] or r1[3] < r2[1] or r2[3] < r1[1])
    return False


def _cluster(obs, net, x, y, layers):
    """Copper items of *net* connected (geometrically) to the item at (x, y) on *layers*."""
    from .geom import pad_dist, pt_seg
    items = obs.by_net.get(net, [])
    seed = None
    best = 1e9
    for it in items:
        if not (it["layers"] & set(layers)):
            continue
        if it["kind"] == "pad":
            d = pad_dist(it, x, y)
        elif it["kind"] == "via":
            d = max(0.0, math.hypot(x - it["x"], y - it["y"]) - it["r"])
        else:
            d = max(0.0, pt_seg(x, y, it["a"][0], it["a"][1], it["b"][0], it["b"][1]) - it["w"] / 2.0)
        if d < best:
            best, seed = d, it
    if seed is None or best > 0.05:
        return []
    out, todo = [seed], [seed]
    seen = {id(seed)}
    while todo:
        c = todo.pop()
        for it in items:
            if id(it) not in seen and _touch(c, it):
                seen.add(id(it))
                out.append(it)
                todo.append(it)
    return out


def _cells(win, items, sig):
    """(layer index, i, j) of grid cells covered by the copper of *items* (signal layers only)."""
    out = set()
    for it in items:
        s = win.sub(it["bb"], win.g)
        if s is None:
            continue
        sj, si, PX, PY = s
        if it["kind"] == "seg":
            m = _segdist_grid(PX, PY, it["a"][0], it["a"][1], it["b"][0], it["b"][1]) <= win.g * 0.5
        elif it["kind"] == "via":
            m = _surface_dist(it, PX, PY) <= -win.g * 0.25
        else:                       # pads: the distance is 0 inside the pad
            m = _surface_dist(it, PX, PY) <= 0.0
        jj, ii = np.nonzero(m)
        for l in it["layers"]:
            if l in sig:
                li = sig.index(l)
                for a, c in zip(ii, jj):
                    out.add((li, int(a) + si.start, int(c) + sj.start))
    return out


def _snap(it, p):
    """Point on the centre of item *it* (via centre / track centreline) nearest to p, so that a
    track ending there is connected for KiCad; pads: p itself (it lies inside the pad)."""
    if it is None or it["kind"] == "pad":
        return None
    if it["kind"] == "via":
        return (it["x"], it["y"])
    ax, ay = it["a"]
    bx, by = it["b"]
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return (ax + t * dx, ay + t * dy)


def _owner(win, items, cellxyl, sig):
    l, i, j = cellxyl
    x, y = win.xy(i, j)
    from .geom import pad_dist, pt_seg
    for it in items:
        if sig[l] not in it["layers"]:
            continue
        if it["kind"] == "pad" and pad_dist(it, x, y) <= 0:
            return it
        if it["kind"] == "via" and math.hypot(x - it["x"], y - it["y"]) <= it["r"]:
            return it
        if it["kind"] == "seg" and pt_seg(x, y, it["a"][0], it["a"][1], it["b"][0], it["b"][1]) <= max(it["w"] / 2.0, win.g * 0.5):
            return it
    return None


def _layers_of(desc, sig):
    if "PTH" in desc or desc.startswith("Via") or "Via " in desc:
        return list(sig)
    m = re.search(r"on (\S+\.Cu)", desc)
    if m and m.group(1) in sig:
        return [m.group(1)]
    return list(sig)


def _components(items):
    """Connected groups (lists) of same-net copper items (geometric touching)."""
    left = list(items)
    out = []
    while left:
        seed = left.pop()
        comp, todo = [seed], [seed]
        while todo:
            c = todo.pop()
            keep = []
            for it in left:
                if _touch(c, it):
                    comp.append(it)
                    todo.append(it)
                else:
                    keep.append(it)
            left = keep
        out.append(comp)
    return out


def _centre(items, fallback):
    if not items:
        return fallback
    xs = [(it["bb"][0] + it["bb"][2]) / 2.0 for it in items]
    ys = [(it["bb"][1] + it["bb"][3]) / 2.0 for it in items]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _connect(ctx, net, ca, cb, pa, pb, la, lb, ripup):
    """Search a route between copper groups ca and cb of *net*.  Returns
    (route, width, via_dia, via_drill, rip-items) or (None, reason)."""
    board, obs, sig, fr = ctx["board"], ctx["obs"], ctx["sig"], ctx["fr"]
    rr = board.rules
    nc = board.class_of(net)
    vdia, vdr = nc["via_dia"], nc["via_drill"]
    vr = vdia / 2.0
    attempts = [(nc["track"], 6.0, GRID), (nc["track"], 15.0, 0.1)]
    if rr.min_track < nc["track"]:
        attempts.append((rr.min_track, 15.0, GRID))
    attempts.append((rr.min_track, None, 0.1))
    soft_ok = (lambda it: it["kind"] in ("seg", "via") and not it.get("locked", True)
               and it["net"] not in ctx["protected"]) if ripup else None
    why = "no path"
    for w, grow, g in attempts:
        if grow is None:
            bx = [fr.kmm(*p) for p in board.outline["pts"]]
            x0, y0 = min(p[0] for p in bx) - 1, min(p[1] for p in bx) - 1
            x1, y1 = max(p[0] for p in bx) + 1, max(p[1] for p in bx) + 1
        else:
            x0, y0 = min(pa[0], pb[0]) - grow, min(pa[1], pb[1]) - grow
            x1, y1 = max(pa[0], pb[0]) + grow, max(pa[1], pb[1]) + grow
        win = Window(x0, y0, x1, y1, g)
        ras = _rasterize(obs, win, net, w, vr, vdr, sig, soft_ok)
        trk, via = ras[0], ras[1]
        trk_s, via_s = (ras[2], ras[3]) if ripup else (None, None)
        starts = _cells(win, ca, sig) or {(sig.index(l),) + win.cell(*pa) for l in la}
        goals = _cells(win, cb, sig) or {(sig.index(l),) + win.cell(*pb) for l in lb}
        starts -= goals
        if not starts or not goals:
            continue
        try:
            path = _astar(win, trk, via, sig, sorted(starts), sorted(goals), trk_soft=trk_s, via_soft=via_s)
        except Budget:
            why = "search budget exhausted (window %s, grid %.2f)" % ("board" if grow is None else "%g mm" % grow, g)
            continue
        if path is None:
            why = "no free path%s (window %s, grid %.2f)" % (" even with rip-up" if ripup else "",
                                                            "board" if grow is None else "%g mm" % grow, g)
            continue
        los = trk if not ripup else {l: trk[l] | trk_s[l] for l in sig}
        route = _smooth(win, los, _simplify(win, sig, path))
        if not route:
            continue
        ny, nx = win.ny, win.nx

        def st(sidx):
            l, rem = divmod(sidx, ny * nx)
            j2, i2 = divmod(rem, nx)
            return (l, i2, j2)
        s0, s1 = st(path[0]), st(path[-1])
        for (cell, items_, pt, at_start) in ((s0, ca, pa, True), (s1, cb, pb, False)):
            own = _owner(win, items_, cell, sig) if items_ else None
            lay = sig[cell[0]]
            cxy = win.xy(cell[1], cell[2])
            tgt = _snap(own, cxy) if own is not None else (pt if not items_ else None)
            if tgt is None or math.hypot(tgt[0] - cxy[0], tgt[1] - cxy[1]) < 1e-6:
                continue
            if at_start:
                route.insert(0, ("seg", lay, tgt, cxy))
            else:
                route.append(("seg", lay, cxy, tgt))
        route = [r for r in route if r[0] != "seg" or math.hypot(r[3][0] - r[2][0], r[3][1] - r[2][1]) >= 1e-6]
        rips, bad = {}, None
        for r in route:
            hits = obs.hits_seg(r[2], r[3], w, r[1], net) if r[0] == "seg" else obs.hits_via(r[1][0], r[1][1], vr, vdr, net)
            if hits is None:
                bad = "edge / cut-out / keep-out"
                break
            for it in hits:
                if not ripup or not soft_ok(it):
                    bad = "%s of %s" % (it["kind"], it["net"] or "-")
                    break
                rips[id(it)] = it
            if bad:
                break
        if bad:
            why = "exact re-check failed: " + bad
            continue
        return route, w, vdia, vdr, list(rips.values())
    return None, why


def _commit(ctx, net, route, w, vdia, vdr):
    obs, fr = ctx["obs"], ctx["fr"]
    added_obs, added = [], []
    for r in route:
        if r[0] == "seg":
            it = obs.add_seg(r[2], r[3], w, r[1], net)
            added.append({"k": "seg", "net": net, "layer": r[1], "w": w,
                          "a": list(fr.user(pcbnew.VECTOR2I(MM(r[2][0]), MM(r[2][1])))),
                          "b": list(fr.user(pcbnew.VECTOR2I(MM(r[3][0]), MM(r[3][1]))))})
        else:
            it = obs.add_via(r[1][0], r[1][1], vdia / 2.0, vdr, net)
            added.append({"k": "via", "net": net, "dia": vdia, "drill": vdr,
                          "xy": list(fr.user(pcbnew.VECTOR2I(MM(r[1][0]), MM(r[1][1]))))})
        it["locked"] = True          # finisher copper is never ripped up again
        added_obs.append(it)
    return added_obs, added


def run(board, paths, fr, ses_sha, drc_unrouted):
    """Route the open connections on paths.pcb; write route/finish.json.  Returns stats."""
    t0 = time.time()
    pcb = pcbnew.LoadBoard(paths.pcb)
    bld = _Bld(board, pcb, fr)
    obs = Obstacles(bld, margin=0.01)
    sig = [l for l in board.copper_layers if l not in board.plane_layers]
    # nets with copper zones are never ripped up (their connectivity runs through the zone)
    protected = {z.GetNetname() for z in pcb.Zones() if not z.GetIsRuleArea()}
    ctx = {"board": board, "obs": obs, "sig": sig, "fr": fr, "protected": protected}
    items, removed, done, failed = [], [], [], []
    fn = os.path.join(paths.route_dir, "finish.json")
    if os.path.exists(fn):
        with open(fn) as f:
            old = json.load(f)
        if old.get("ses_sha256") == ses_sha:          # already on the board (applied by finish_pcb)
            items = list(old.get("items", []))
            removed = list(old.get("remove", []))
    ripup = board.routing.get("finisher_ripup", True)
    budget = float(board.routing.get("finisher_seconds", 900))
    for u in drc_unrouted:
        net = u["net"]
        if time.time() - t0 > budget:
            failed.append({"net": net, "why": "finisher time budget (%g s) used up" % budget})
            continue
        if len(u["ends"]) != 2 or net == "?":
            failed.append({"net": net, "why": "unparsed DRC item"})
            continue
        (ea, eb) = u["ends"]
        pa = fr.kmm(*ea["xy_mm"])
        pb = fr.kmm(*eb["xy_mm"])
        la, lb = _layers_of(ea["item"], sig), _layers_of(eb["item"], sig)
        ca = _cluster(obs, net, pa[0], pa[1], la)
        cb = _cluster(obs, net, pb[0], pb[1], lb)
        if ca and cb and any(it in cb for it in ca):
            ca = cb = []          # our geometry sees them joined: fall back to the two points
        res = _connect(ctx, net, ca, cb, pa, pb, la, lb, False)
        used_ripup = False
        if res[0] is None and ripup and net not in protected:
            first_why = res[1]
            res = _connect(ctx, net, ca, cb, pa, pb, la, lb, True)
            used_ripup = res[0] is not None
            if res[0] is None:
                res = (None, first_why + "; rip-up: " + res[1])
        if res[0] is None:
            failed.append({"net": net, "why": res[1], "ends": [ea["item"], eb["item"]]})
            continue
        route, w, vdia, vdr, rips = res
        # rip up, route, then reconnect every ripped net (which may rip up further router copper,
        # never the finisher's own new copper); bounded, and undone completely on failure
        all_rips = list(rips)
        for it in rips:
            obs.remove(it)
        new_obs, new_items = _commit(ctx, net, route, w, vdia, vdr)
        queue = sorted({it["net"] for it in rips})
        touched = list(queue)
        ok, why, steps = True, "", 0
        while queue and ok:
            n = queue.pop(0)
            while True:
                steps += 1
                if steps > 40:
                    ok, why = False, "rip-up cascade too long (40 steps)"
                    break
                comps = [c for c in _components(obs.by_net.get(n, [])) if c]
                if len(comps) <= 1:
                    break
                comps.sort(key=len, reverse=True)
                a = comps[0]
                ac = _centre(a, None)
                b = min(comps[1:], key=lambda c: math.hypot(_centre(c, ac)[0] - ac[0], _centre(c, ac)[1] - ac[1]))
                r2 = _connect(ctx, n, a, b, ac, _centre(b, ac), sig, sig, False)
                if r2[0] is None and ripup:
                    r2 = _connect(ctx, n, a, b, ac, _centre(b, ac), sig, sig, True)
                if r2[0] is None:
                    ok, why = False, "could not reconnect ripped net %s: %s" % (n, r2[1])
                    break
                for it in r2[4]:
                    obs.remove(it)
                    all_rips.append(it)
                    if it["net"] not in queue and it["net"] != n:
                        queue.append(it["net"])
                        touched.append(it["net"])
                o2, i2 = _commit(ctx, n, *r2[:4])
                new_obs += o2
                new_items += i2
        if not ok:
            for it in new_obs:
                obs.remove(it)
            for it in all_rips:
                obs._add(it)
            failed.append({"net": net, "why": "rip-up undone: " + why, "ends": [ea["item"], eb["item"]]})
            continue
        items += new_items
        removed += [it["key"] for it in all_rips]
        done.append({"net": net, "segments": sum(1 for r in route if r[0] == "seg"),
                     "vias": sum(1 for r in route if r[0] == "via"), "width": w,
                     "ripped_up_items": len(all_rips), "rerouted_nets": sorted(set(touched))})
    res = {"ses_sha256": ses_sha, "items": items, "remove": removed}
    with open(fn, "w") as f:
        json.dump(res, f, indent=0, sort_keys=True)
        f.write("\n")
    return {"routed": done, "failed": failed, "seconds": round(time.time() - t0, 1), "items": len(items),
            "removed": len(removed)}


def apply(pcb, fr, route_dir, ses_path):
    """Add the stored finisher items to *pcb* if they belong to this SES.  Returns
    (number of items added, [board items to remove]) - the caller removes those LAST (after
    BOARD.Remove() pcbnew's SWIG proxies in the same process are unreliable).  (None, []) when
    there is nothing for this SES."""
    from .geom import item_key
    fn = os.path.join(route_dir, "finish.json")
    if not os.path.exists(fn) or not ses_path or not os.path.exists(ses_path):
        return None, []
    with open(fn) as f:
        data = json.load(f)
    h = hashlib.sha256(open(ses_path, "rb").read()).hexdigest()
    if data.get("ses_sha256") != h:
        return None, []
    gone = {json.dumps(k) for k in data.get("remove", [])}
    victims = [t for t in pcb.GetTracks() if not t.IsLocked() and json.dumps(item_key(t)) in gone] if gone else []
    n = 0
    for it in data["items"]:
        ni = pcb.FindNet(it["net"])
        if it["k"] == "via":
            v = pcbnew.PCB_VIA(pcb)
            v.SetPosition(fr.k(*it["xy"]))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetWidth(pcbnew.F_Cu, MM(it["dia"]))
            v.SetDrill(MM(it["drill"]))
            v.SetNet(ni)
            pcb.Add(v)
        else:
            t = pcbnew.PCB_TRACK(pcb)
            t.SetStart(fr.k(*it["a"]))
            t.SetEnd(fr.k(*it["b"]))
            t.SetLayer(pcb.GetLayerID(it["layer"]))
            t.SetWidth(MM(it["w"]))
            t.SetNet(ni)
            pcb.Add(t)
        n += 1
    return n, victims


def plane_connect(bld, failed):
    """Generation time: pads of plane nets that the plane fan-out could not give a via beside the
    pad get a maze-routed connection from the pad to the nearest legal via position inside their
    own plane polygon (a "long fan-out"), as locked pre-routes - so nets with a plane never reach
    the autorouter.  *failed*: fan-out items (rect, net, layer, ref).  Returns (routed, still failed)."""
    from .geom import pip, pad_dist
    b, pcb, fr = bld.b, bld.pcb, bld.fr
    obs = Obstacles(bld, margin=0.03)                 # with the DSN's 25 um margin
    sig = [l for l in b.copper_layers if l not in b.plane_layers]
    zones = []
    for zd in b.zones:
        for ln in zd["layers"]:
            if ln in b.plane_layers:
                zones.append((ln, zd["priority"], zd["net"], [fr.kmm(*p) for p in (zd["polygon"] or b.outline["pts"])]))
    r = b.rules
    vdia, vdr = r.via_dia, r.via_drill
    vr = vdia / 2.0
    done, left = [], []
    for me in failed:
        net = me["net"]
        x0, y0, x1, y1 = me["rect"]
        px, py = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        w = max(r.min_track, min(b.class_of(net)["track"], min(x1 - x0, y1 - y0) - 0.05))
        own = None
        for it in obs.pads_by_ref.get(me["ref"], []):
            if abs(it["cx"] - px) < 1e-3 and abs(it["cy"] - py) < 1e-3:
                own = it
        if own is None:
            left.append(me)
            continue
        ok = False
        why = "no path"
        for grow, g in ((5.0, GRID), (12.0, 0.1), (30.0, 0.2)):
            win = Window(px - grow, py - grow, px + grow, py + grow, g)
            trk, via = _rasterize(obs, win, net, w, vr, vdr, sig)
            PX, PY = np.meshgrid(win.X, win.Y)
            inplane = np.zeros(PX.shape, dtype=bool)
            for ln in sorted({z[0] for z in zones}):
                best_p = np.full(PX.shape, -1)
                best_own = np.zeros(PX.shape, dtype=bool)
                for (l, prio, n, poly) in zones:
                    if l != ln:
                        continue
                    m = _pip_grid(PX, PY, poly) & (prio > best_p)
                    best_p = np.where(m, prio, best_p)
                    best_own = np.where(m, n == net, best_own)
                inplane |= best_own
            for rect, ref in obs.court:               # no long fan-out via inside another part's courtyard
                if ref == me["ref"]:
                    continue
                s_ = win.sub(rect, vr)
                if s_ is not None:
                    sj, si, QX, QY = s_
                    dx = np.maximum(np.maximum(rect[0] - QX, 0.0), QX - rect[2])
                    dy = np.maximum(np.maximum(rect[1] - QY, 0.0), QY - rect[3])
                    via[sj, si] |= np.hypot(dx, dy) < vr
            goal = (~via) & inplane
            starts = {c for c in _cells(win, [own], sig)}
            if not starts:
                why = "pad not on a signal layer"
                break
            if not goal.any():
                why = "no legal via position inside the own plane polygon within %g mm" % grow
                continue
            try:
                path = _astar(win, trk, via, sig, sorted(starts), [], budget=400_000, goal_mask=goal.reshape(-1))
            except Budget:
                path = None
                why = "search budget"
            if path is None:
                why = "no free path to the plane within %g mm" % grow
                continue
            route = _smooth(win, trk, _simplify(win, sig, path))
            l_end, rem = divmod(path[-1], win.ny * win.nx)
            je, ie = divmod(rem, win.nx)
            vxy = win.xy(ie, je)
            l0, rem0 = divmod(path[0], win.ny * win.nx)
            j0, i0 = divmod(rem0, win.nx)
            route.insert(0, ("seg", sig[l0], (px, py), win.xy(i0, j0)))
            route.append(("via", vxy))
            route = [q for q in route if q[0] != "seg" or math.hypot(q[3][0] - q[2][0], q[3][1] - q[2][1]) >= 1e-6]
            bad = False
            for q in route:
                if q[0] == "seg":
                    bad = not obs.seg_ok(q[2], q[3], w, q[1], net, own={id(own)})
                else:
                    bad = not obs.via_ok(q[1][0], q[1][1], vr, vdr, net, courtyard_ignore=(me["ref"],))
                if bad:
                    why = "exact re-check: " + obs.why
                    break
            if bad:
                continue
            ni = bld.net(net)
            for q in route:
                if q[0] == "seg":
                    t = pcbnew.PCB_TRACK(pcb)
                    t.SetStart(pcbnew.VECTOR2I(MM(q[2][0]), MM(q[2][1])))
                    t.SetEnd(pcbnew.VECTOR2I(MM(q[3][0]), MM(q[3][1])))
                    t.SetLayer(pcb.GetLayerID(q[1]))
                    t.SetWidth(MM(w))
                    t.SetNet(ni)
                    t.SetLocked(True)
                    pcb.Add(t)
                    obs.add_seg(q[2], q[3], w, q[1], net)
                else:
                    v = pcbnew.PCB_VIA(pcb)
                    v.SetPosition(pcbnew.VECTOR2I(MM(q[1][0]), MM(q[1][1])))
                    v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetWidth(pcbnew.F_Cu, MM(vdia))
                    v.SetDrill(MM(vdr))
                    v.SetNet(ni)
                    v.SetLocked(True)
                    pcb.Add(v)
                    obs.add_via(q[1][0], q[1][1], vr, vdr, net)
            done.append("%s [%s] %.1f mm" % (me["ref"], net, sum(math.hypot(q[3][0] - q[2][0], q[3][1] - q[2][1]) for q in route if q[0] == "seg")))
            ok = True
            break
        if not ok:
            me["_why"] = why
            left.append(me)
    return done, left
