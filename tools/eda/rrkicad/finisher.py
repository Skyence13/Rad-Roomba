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


def _rasterize(obs, win, net, w, vr, vdrill, layers):
    """Blocked maps: track[layer] (ny, nx) and via (ny, nx)."""
    rr = obs.r
    q = win.g * 0.5
    trk = {l: np.zeros((win.ny, win.nx), dtype=bool) for l in layers}
    via = np.zeros((win.ny, win.nx), dtype=bool)
    bb = (win.x0, win.y0, win.x0 + win.nx * win.g, win.y0 + win.ny * win.g)
    seen = set()
    for it in obs.near(*bb):
        if id(it) in seen:
            continue
        seen.add(id(it))
        same = it["net"] == net and net != ""
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
                    trk[l][sj, si] |= d < c + w / 2.0 + q
            via[sj, si] |= d < c + vr + q
        elif it["kind"] == "pad" and not it["drill"]:
            via[sj, si] |= d < vr + 0.05 + q
        hd = it.get("drill") or 0.0
        if hd:
            cx, cy = (it["x"], it["y"]) if it["kind"] == "via" else (it["cx"], it["cy"])
            via[sj, si] |= np.hypot(PX - cx, PY - cy) < hd / 2.0 + vdrill / 2.0 + rr.min_hole_to_hole + obs.margin + q
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
    return trk, via


class Budget(Exception):
    pass


def _astar(win, trk, via, layers, starts, goals, budget=1_500_000):
    L, ny, nx = len(layers), win.ny, win.nx
    N = L * ny * nx
    blocked = np.stack([trk[l] for l in layers]).reshape(-1)
    vflat = via.reshape(-1)            # True = no via allowed here
    gcost = np.full(N, np.inf, dtype=np.float64)
    parent = np.full(N, -1, dtype=np.int64)
    goal = set()
    for (l, i, j) in goals:
        goal.add(l * ny * nx + j * nx + i)
    gx = sum(g[1] for g in goals) / float(len(goals))
    gy = sum(g[2] for g in goals) / float(len(goals))
    heap = []
    for (l, i, j) in starts:
        s = l * ny * nx + j * nx + i
        gcost[s] = 0.0
        heapq.heappush(heap, (math.hypot(i - gx, j - gy), 0.0, s))
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.41421356), (1, -1, 1.41421356), (-1, 1, 1.41421356), (-1, -1, 1.41421356)]
    pops = 0
    while heap:
        f, gc, s = heapq.heappop(heap)
        if gc > gcost[s]:
            continue
        if s in goal:
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
            ng = gc + c
            if ng < gcost[t]:
                gcost[t] = ng
                parent[t] = s
                heapq.heappush(heap, (ng + math.hypot(ii - gx, jj - gy), ng, t))
        if L > 1 and not vflat[j * nx + i]:
            for l2 in range(L):
                if l2 == l:
                    continue
                t = l2 * ny * nx + j * nx + i
                if blocked[t] and t not in goal:
                    continue
                ng = gc + VIA_COST
                if ng < gcost[t]:
                    gcost[t] = ng
                    parent[t] = s
                    heapq.heappush(heap, (ng + math.hypot(i - gx, j - gy), ng, t))
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
        m = _surface_dist(it, PX, PY) <= -win.g * 0.25 if it["kind"] != "seg" else \
            _segdist_grid(PX, PY, it["a"][0], it["a"][1], it["b"][0], it["b"][1]) <= win.g * 0.5
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


def run(board, paths, fr, ses_sha, drc_unrouted):
    """Route the open connections on paths.pcb; write route/<name>.finish.json.  Returns stats."""
    t0 = time.time()
    pcb = pcbnew.LoadBoard(paths.pcb)
    bld = _Bld(board, pcb, fr)
    obs = Obstacles(bld, margin=0.01)
    sig = [l for l in board.copper_layers if l not in board.plane_layers]
    rr = board.rules
    items, done, failed = [], [], []
    fn = os.path.join(paths.route_dir, "finish.json")
    if os.path.exists(fn):
        with open(fn) as f:
            old = json.load(f)
        if old.get("ses_sha256") == ses_sha:
            items = list(old.get("items", []))     # already on the board (applied by finish_pcb)
    for u in drc_unrouted:
        net = u["net"]
        if len(u["ends"]) != 2 or net == "?":
            failed.append({"net": net, "why": "unparsed DRC item"})
            continue
        (ea, eb) = u["ends"]
        pa = fr.kmm(*ea["xy_mm"])
        pb = fr.kmm(*eb["xy_mm"])
        la, lb = _layers_of(ea["item"], sig), _layers_of(eb["item"], sig)
        nc = board.class_of(net)
        ok = False
        why = "no path"
        ca = _cluster(obs, net, pa[0], pa[1], la)
        cb = _cluster(obs, net, pb[0], pb[1], lb)
        if ca and cb and any(it in cb for it in ca):
            ca = cb = []          # our geometry sees them joined (e.g. via a zone): fall back to the two points
        attempts = [(nc["track"], 6.0, GRID), (nc["track"], 15.0, 0.1)]
        if rr.min_track < nc["track"]:
            attempts.append((rr.min_track, 15.0, GRID))
        attempts.append((rr.min_track, None, 0.1))
        vdia, vdr = nc["via_dia"], nc["via_drill"]
        vr = vdia / 2.0
        for w, grow, g in attempts:
            if grow is None:
                bx = [fr.kmm(*p) for p in board.outline["pts"]]
                x0, y0 = min(p[0] for p in bx) - 1, min(p[1] for p in bx) - 1
                x1, y1 = max(p[0] for p in bx) + 1, max(p[1] for p in bx) + 1
            else:
                x0, y0 = min(pa[0], pb[0]) - grow, min(pa[1], pb[1]) - grow
                x1, y1 = max(pa[0], pb[0]) + grow, max(pa[1], pb[1]) + grow
            win = Window(x0, y0, x1, y1, g)
            trk, via = _rasterize(obs, win, net, w, vr, vdr, sig)
            starts = _cells(win, ca, sig) or {(sig.index(l),) + win.cell(*pa) for l in la}
            goals = _cells(win, cb, sig) or {(sig.index(l),) + win.cell(*pb) for l in lb}
            starts -= goals
            if not starts:
                continue
            try:
                path = _astar(win, trk, via, sig, sorted(starts), sorted(goals))
            except Budget:
                why = "search budget exhausted (window %s mm, grid %.2f)" % ("board" if grow is None else grow, g)
                continue
            if path is None:
                why = "no free path (window %s mm, grid %.2f)" % ("board" if grow is None else grow, g)
                continue
            route = _smooth(win, trk, _simplify(win, sig, path))
            if not route:
                continue
            # connect the grid ends to the copper they start / end in
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
            bad = None
            for r in route:
                if r[0] == "seg":
                    if math.hypot(r[3][0] - r[2][0], r[3][1] - r[2][1]) < 1e-6:
                        continue
                    if not obs.seg_ok(r[2], r[3], w, r[1], net):
                        bad = obs.why
                        break
                elif not obs.via_ok(r[1][0], r[1][1], vr, vdr, net, check_court=False):
                    bad = obs.why
                    break
            if bad:
                why = "exact re-check failed: " + bad
                continue
            for r in route:
                if r[0] == "seg":
                    if math.hypot(r[3][0] - r[2][0], r[3][1] - r[2][1]) < 1e-6:
                        continue
                    obs.add_seg(r[2], r[3], w, r[1], net)
                    items.append({"k": "seg", "net": net, "layer": r[1], "w": w,
                                  "a": list(fr.user(pcbnew.VECTOR2I(MM(r[2][0]), MM(r[2][1])))),
                                  "b": list(fr.user(pcbnew.VECTOR2I(MM(r[3][0]), MM(r[3][1]))))})
                else:
                    obs.add_via(r[1][0], r[1][1], vr, vdr, net)
                    items.append({"k": "via", "net": net, "dia": vdia, "drill": vdr,
                                  "xy": list(fr.user(pcbnew.VECTOR2I(MM(r[1][0]), MM(r[1][1]))))})
            done.append({"net": net, "segments": sum(1 for r in route if r[0] == "seg"),
                         "vias": sum(1 for r in route if r[0] == "via"), "width": w})
            ok = True
            break
        if not ok:
            failed.append({"net": net, "why": why, "ends": [ea["item"], eb["item"]]})
    res = {"ses_sha256": ses_sha, "items": items}
    with open(os.path.join(paths.route_dir, "finish.json"), "w") as f:
        json.dump(res, f, indent=0, sort_keys=True)
        f.write("\n")
    return {"routed": done, "failed": failed, "seconds": round(time.time() - t0, 1), "items": len(items)}


def apply(board, pcb, fr, paths, ses_path):
    """Add stored finisher items if they belong to this SES.  Returns the number added (or None)."""
    fn = os.path.join(paths.route_dir, "finish.json")
    if not os.path.exists(fn) or not ses_path or not os.path.exists(ses_path):
        return None
    with open(fn) as f:
        data = json.load(f)
    h = hashlib.sha256(open(ses_path, "rb").read()).hexdigest()
    if data.get("ses_sha256") != h:
        return None
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
    return n
