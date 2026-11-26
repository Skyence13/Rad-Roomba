"""Plane fan-out: a short track + via beside every SMD pad whose net has a zone on an
inner plane layer.  Done here (not by the autorouter) so that plane nets are complete
before autorouting and Freerouting only has to route signals.

Rules respected: copper clearance to other nets (pads, tracks, vias), hole-to-hole,
board-edge clearance, cut-outs, via keep-outs, the via must land inside *its own* net's
plane polygon (split planes), and - where possible - outside other parts' courtyards.
Pads for which no legal position exists are left to the autorouter and reported.
"""
import math

import pcbnew

MM = pcbnew.FromMM
CELL = 2.0
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.7071, 0.7071), (-0.7071, 0.7071), (0.7071, -0.7071), (-0.7071, -0.7071)]
GAPS = (0.15, 0.3, 0.5, 0.8, 1.2, 1.7, 2.3)


def _pip(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _rect_dist(x, y, r):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Grid:
    def __init__(self):
        self.cells = {}

    def add(self, rect, item):
        for i in range(int(math.floor(rect[0] / CELL)), int(math.floor(rect[2] / CELL)) + 1):
            for j in range(int(math.floor(rect[1] / CELL)), int(math.floor(rect[3] / CELL)) + 1):
                self.cells.setdefault((i, j), []).append(item)

    def near(self, x0, y0, x1, y1):
        seen = set()
        out = []
        for i in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for j in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                for it in self.cells.get((i, j), ()):
                    if id(it) not in seen:
                        seen.add(id(it))
                        out.append(it)
        return out


def plane_fanout(bld, skip=None):
    """Add locked fan-out tracks/vias to bld.pcb.  Returns stats dict.
    *skip*: pad keys (ref, number, x, y) already escaped by escape.escape()."""
    b, pcb, fr = bld.b, bld.pcb, bld.fr
    zones = []      # (layer name, priority, net, polygon in KiCad mm)
    for zd in b.zones:
        for lname in zd["layers"]:
            if lname in b.plane_layers:
                zones.append((lname, zd["priority"], zd["net"], [fr.kmm(*p) for p in (zd["polygon"] or b.outline["pts"])]))
    if not zones:
        return {"plane_nets": [], "vias": 0, "failed": []}
    plane_nets = sorted({z[2] for z in zones})
    layers = sorted({z[0] for z in zones})

    def in_plane(net, x, y):
        for ln in layers:
            best = None
            for (l, prio, n, poly) in zones:
                if l == ln and _pip(x, y, poly) and (best is None or prio > best[0]):
                    best = (prio, n)
            if best is not None and best[1] == net:
                return True
        return False
    r = b.rules
    vr, vdr = r.via_dia / 2.0, r.via_drill
    outline = [fr.kmm(*p) for p in bld.outline_dense]
    cutouts = [[fr.kmm(*p) for p in c] for c in bld.cutout_polys]
    kos = [[fr.kmm(*p) for p in ko["_pts"]] for ko in b.keepouts if ko.get("vias") and "_pts" in ko]
    for h in b.holes:   # hole keep-outs were added as board keep-outs by the builder
        pass
    ring = [(math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)) for a in range(8)]

    def edge_ok(x, y):
        m = vr + r.edge_clearance + 0.05
        for cx, cy in [(0, 0)] + ring:
            px, py = x + cx * m, y + cy * m
            if not _pip(px, py, outline) or any(_pip(px, py, c) for c in cutouts):
                return False
        for cx, cy in [(0, 0)] + ring:
            px, py = x + cx * vr, y + cy * vr
            if any(_pip(px, py, k) for k in bld.via_keepouts):
                return False
        return True
    pads = Grid()       # dict(rect, net, layers, ref)
    court = Grid()      # dict(rect, ref)
    vias = Grid()       # dict(x, y, r, drill, net)
    segs = Grid()       # dict(a, b, w, layer, net)
    todo = []
    for fp in pcb.GetFootprints():
        ref = fp.GetReference()
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        if cy.OutlineCount() > 0:
            bb = cy.BBox()
            rect = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            court.add(rect, {"rect": rect, "ref": ref})
        part = b._refs.get(ref)
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            rect = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            tht = pad.GetDrillSize().x > 0
            lay = "*" if tht else ("B.Cu" if pad.IsOnLayer(pcbnew.B_Cu) else "F.Cu")
            item = {"rect": rect, "net": pad.GetNetname(), "layer": lay, "ref": ref, "tht": tht}
            pads.add(rect, item)
            if not tht and item["net"] in plane_nets and not (part is not None and part.zone_connect == "none"):
                p = pad.GetPosition()
                if skip and (ref, pad.GetNumber(), round(pcbnew.ToMM(p.x), 3), round(pcbnew.ToMM(p.y), 3)) in skip:
                    continue
                todo.append(item)
    for t in pcb.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            v = {"x": pcbnew.ToMM(p.x), "y": pcbnew.ToMM(p.y), "r": pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2.0,
                 "drill": pcbnew.ToMM(t.GetDrillValue()), "net": t.GetNetname()}
            vias.add((v["x"] - v["r"], v["y"] - v["r"], v["x"] + v["r"], v["y"] + v["r"]), v)
        else:
            a, e = t.GetStart(), t.GetEnd()
            s = {"a": (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)), "b": (pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)),
                 "w": pcbnew.ToMM(t.GetWidth()), "layer": t.GetLayerName(), "net": t.GetNetname()}
            segs.add((min(s["a"][0], s["b"][0]), min(s["a"][1], s["b"][1]), max(s["a"][0], s["b"][0]), max(s["a"][1], s["b"][1])), s)

    def via_ok(x, y, net, me, allow_courtyard):
        clr = max(r.clearance, b.class_of(net)["clearance"]) + 0.03
        m = vr + clr + 1.0
        if not in_plane(net, x, y) or not edge_ok(x, y):
            return False
        for q in pads.near(x - m, y - m, x + m, y + m):
            if q is me:
                continue
            d = _rect_dist(x, y, q["rect"])
            if q["net"] == net:
                if d < vr + 0.1:
                    return False
            elif d < vr + clr or d < vdr / 2.0 + r.min_hole_clearance + 0.03:
                return False
        for v in vias.near(x - m, y - m, x + m, y + m):
            d = math.hypot(x - v["x"], y - v["y"])
            if d < vdr / 2.0 + v["drill"] / 2.0 + r.min_hole_to_hole + 0.05:
                return False
            if d < vr + v["r"] + (clr if v["net"] != net else 0.05):
                return False
        for s in segs.near(x - m, y - m, x + m, y + m):
            if s["net"] != net and _seg_dist(x, y, s["a"][0], s["a"][1], s["b"][0], s["b"][1]) < vr + s["w"] / 2.0 + clr:
                return False
        if not allow_courtyard:
            for c in court.near(x, y, x, y):
                if c["ref"] != me["ref"] and c["rect"][0] < x < c["rect"][2] and c["rect"][1] < y < c["rect"][3]:
                    return False
        return True

    def track_ok(ax, ay, bx, by, w, layer, net, me):
        clr = max(r.clearance, b.class_of(net)["clearance"]) + 0.01
        n = max(1, int(math.hypot(bx - ax, by - ay) / 0.08))
        mr = me["rect"]
        m = w / 2.0 + clr
        near_p = pads.near(min(ax, bx) - m, min(ay, by) - m, max(ax, bx) + m, max(ay, by) + m)
        near_v = vias.near(min(ax, bx) - m - 1, min(ay, by) - m - 1, max(ax, bx) + m + 1, max(ay, by) + m + 1)
        near_s = segs.near(min(ax, bx) - m - 1, min(ay, by) - m - 1, max(ax, bx) + m + 1, max(ay, by) + m + 1)
        for k in range(n + 1):
            x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
            if mr[0] <= x <= mr[2] and mr[1] <= y <= mr[3]:
                continue          # still inside the pad's own copper
            for q in near_p:
                if q is me or q["net"] == net or q["layer"] not in ("*", layer):
                    continue
                if _rect_dist(x, y, q["rect"]) < m:
                    return False
            for v in near_v:
                if v["net"] != net and math.hypot(x - v["x"], y - v["y"]) < v["r"] + m:
                    return False
            for s in near_s:
                if s["net"] != net and s["layer"] == layer and \
                        _seg_dist(x, y, s["a"][0], s["a"][1], s["b"][0], s["b"][1]) < s["w"] / 2.0 + m:
                    return False
        return True
    made, failed = 0, []
    centre = {}      # ref -> pad-bbox centre and pad count, to fan big ICs out towards their inside
    for me in todo:
        pass
    for fp in pcb.GetFootprints():
        ps = [p.GetPosition() for p in fp.Pads()]
        if ps:
            centre[fp.GetReference()] = (pcbnew.ToMM(sum(p.x for p in ps) / len(ps)), pcbnew.ToMM(sum(p.y for p in ps) / len(ps)), len(ps))
    for me in todo:
        net = me["net"]
        x0, y0, x1, y1 = me["rect"]
        px, py = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        w, h = x1 - x0, y1 - y0
        tw = max(r.min_track, min(b.class_of(net)["track"], min(w, h) - 0.05))
        cands = []
        cx, cy, npads = centre.get(me["ref"], (px, py, 0))
        for ux, uy in DIRS:
            e = min(w / 2.0 / abs(ux) if ux else 1e9, h / 2.0 / abs(uy) if uy else 1e9)
            # ICs: prefer vias under the package (towards its centre) so the outside stays free for signal escape
            inward = 0 if (npads < 16 or (ux * (cx - px) + uy * (cy - py)) > 0.3 * math.hypot(cx - px, cy - py)) else 1
            for g in GAPS:
                d = e + g + vr
                cands.append((inward, d, px + ux * d, py + uy * d))
        cands.sort()
        cands = [c[1:] for c in cands]
        hit = None
        for allow in (False, True):
            for d, vx, vy in cands:
                if via_ok(vx, vy, net, me, allow) and track_ok(px, py, vx, vy, tw, me["layer"], net, me):
                    hit = (vx, vy)
                    break
            if hit:
                break
        if not hit:
            failed.append("%s pad at (%.2f, %.2f) [%s]" % (me["ref"], px - fr.ox, fr.oy - py, net))
            continue
        vx, vy = hit
        ni = bld.net(net)
        tr = pcbnew.PCB_TRACK(pcb)
        tr.SetStart(pcbnew.VECTOR2I(MM(px), MM(py)))
        tr.SetEnd(pcbnew.VECTOR2I(MM(vx), MM(vy)))
        tr.SetLayer(pcbnew.F_Cu if me["layer"] == "F.Cu" else pcbnew.B_Cu)
        tr.SetWidth(MM(tw))
        tr.SetNet(ni)
        tr.SetLocked(True)
        pcb.Add(tr)
        via = pcbnew.PCB_VIA(pcb)
        via.SetPosition(pcbnew.VECTOR2I(MM(vx), MM(vy)))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(pcbnew.F_Cu, MM(r.via_dia))
        via.SetDrill(MM(vdr))
        via.SetNet(ni)
        via.SetLocked(True)
        pcb.Add(via)
        v = {"x": vx, "y": vy, "r": vr, "drill": vdr, "net": net}
        vias.add((vx - vr, vy - vr, vx + vr, vy + vr), v)
        s = {"a": (px, py), "b": (vx, vy), "w": tw, "layer": me["layer"], "net": net}
        segs.add((min(px, vx), min(py, vy), max(px, vx), max(py, vy)), s)
        made += 1
    return {"plane_nets": plane_nets, "vias": made, "failed": failed}
