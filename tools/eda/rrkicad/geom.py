"""Exact 2-D clearance geometry shared by the fine-pitch escape generator and the finisher.

Everything is in KiCad millimetres (page frame, y down).  Copper items are kept in a
bucket grid; every check is an exact distance test (segment/segment, segment/rectangle,
point/polygon), with the net-class clearance of both nets plus a safety margin, so that
the generated copper is DRC-clean in KiCad *and* in Freerouting's (25 um wider) model.
"""
import math

import pcbnew

MM = pcbnew.FromMM
T = pcbnew.ToMM
CELL = 1.0


# ----------------------------------------------------------------- primitives
def pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _cross(ax, ay, bx, by, cx, cy):
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def seg_seg(a, b, c, d):
    """Minimum distance between segments ab and cd (0 if they cross)."""
    d1 = _cross(a[0], a[1], b[0], b[1], c[0], c[1])
    d2 = _cross(a[0], a[1], b[0], b[1], d[0], d[1])
    d3 = _cross(c[0], c[1], d[0], d[1], a[0], a[1])
    d4 = _cross(c[0], c[1], d[0], d[1], b[0], b[1])
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return 0.0
    return min(pt_seg(a[0], a[1], c[0], c[1], d[0], d[1]), pt_seg(b[0], b[1], c[0], c[1], d[0], d[1]),
               pt_seg(c[0], c[1], a[0], a[1], b[0], b[1]), pt_seg(d[0], d[1], a[0], a[1], b[0], b[1]))


def pt_rect(px, py, r):
    dx = max(r[0] - px, 0.0, px - r[2])
    dy = max(r[1] - py, 0.0, py - r[3])
    return math.hypot(dx, dy)


def seg_rect(a, b, r):
    if r[0] <= a[0] <= r[2] and r[1] <= a[1] <= r[3]:
        return 0.0
    if r[0] <= b[0] <= r[2] and r[1] <= b[1] <= r[3]:
        return 0.0
    c = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    return min(seg_seg(a, b, c[i], c[(i + 1) % 4]) for i in range(4))


def pip(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def pt_poly_edge(x, y, poly):
    n = len(poly)
    return min(pt_seg(x, y, poly[i][0], poly[i][1], poly[(i + 1) % n][0], poly[(i + 1) % n][1]) for i in range(n))


def seg_poly_edge(a, b, poly):
    n = len(poly)
    return min(seg_seg(a, b, poly[i], poly[(i + 1) % n]) for i in range(n))


def bbox_of(pts, grow=0.0):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)


# ------------------------------------------------------------------ obstacles
class Obstacles:
    """All copper / holes / courtyards / rule areas of a board for exact clearance checks.

    Items (dicts): kind "pad" (rect or circle), "via", "seg"; every item has "net",
    "layers" (set of copper layer names) and "bb" (bounding box for the bucket grid)."""

    def __init__(self, bld, margin=0.03):
        self.bld = bld
        b = bld.b
        self.b, self.r = b, b.rules
        self.margin = margin
        self.cells = {}
        self.court = []                    # (rect, ref)
        self.cu = list(b.copper_layers)
        self.lid = {l: bld.pcb.GetLayerID(l) for l in self.cu}
        self.sig_layers = [l for l in b.copper_layers if l not in b.plane_layers]
        fr = bld.fr
        self.outline = [fr.kmm(*p) for p in bld.outline_dense]
        self.cutouts = [[fr.kmm(*p) for p in c] for c in bld.cutout_polys]
        self.keepouts = []
        for ko in getattr(bld, "_all_keepouts", []):
            if "_pts" not in ko:
                continue
            lays = set()
            for l in ko["layers"]:
                lays |= set(self.cu) if l == "*.Cu" else {l}
            poly = [fr.kmm(*p) for p in ko["_pts"]]
            self.keepouts.append({"poly": poly, "bb": bbox_of(poly), "layers": lays,
                                  "tracks": bool(ko.get("tracks")), "vias": bool(ko.get("vias"))})
        self._clr = {}
        self.why = ""
        self.pads_by_ref = {}
        self._load(bld.pcb)

    # ------------------------------------------------------------- loading
    def clr(self, n1, n2):
        key = (n1, n2)
        if key not in self._clr:
            c = self.r.clearance
            for n in (n1, n2):
                if n:
                    c = max(c, self.b.class_of(n)["clearance"])
            self._clr[key] = c + self.margin
        return self._clr[key]

    def _add(self, it):
        bb = it["bb"]
        for i in range(int(math.floor(bb[0] / CELL)), int(math.floor(bb[2] / CELL)) + 1):
            for j in range(int(math.floor(bb[1] / CELL)), int(math.floor(bb[3] / CELL)) + 1):
                self.cells.setdefault((i, j), []).append(it)

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

    def _load(self, pcb):
        for fp in pcb.GetFootprints():
            ref = fp.GetReference()
            fp.BuildCourtyardCaches()
            cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
            if cy.OutlineCount() > 0:
                bb = cy.BBox()
                self.court.append(((T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom())), ref))
            for pad in fp.Pads():
                it = pad_item(pad, ref, self.lid)
                if it is None:
                    continue
                self._add(it)
                self.pads_by_ref.setdefault(ref, []).append(it)
        for t in pcb.GetTracks():
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                self.add_via(T(p.x), T(p.y), T(t.GetWidth(pcbnew.F_Cu)) / 2.0, T(t.GetDrillValue()), t.GetNetname())
            elif t.GetClass() == "PCB_TRACK":
                a, e = t.GetStart(), t.GetEnd()
                self.add_seg((T(a.x), T(a.y)), (T(e.x), T(e.y)), T(t.GetWidth()), t.GetLayerName(), t.GetNetname())
            else:   # arcs: approximate by their chord + bulge bbox (conservative enough for rejection)
                a, e = t.GetStart(), t.GetEnd()
                self.add_seg((T(a.x), T(a.y)), (T(e.x), T(e.y)), T(t.GetWidth()) + 0.2, t.GetLayerName(), t.GetNetname())

    def add_via(self, x, y, r, drill, net):
        it = {"kind": "via", "x": x, "y": y, "r": r, "drill": drill, "net": net, "layers": set(self.cu),
              "bb": (x - r, y - r, x + r, y + r)}
        self._add(it)
        return it

    def add_seg(self, a, b, w, layer, net):
        it = {"kind": "seg", "a": a, "b": b, "w": w, "net": net, "layers": {layer},
              "bb": (min(a[0], b[0]) - w / 2, min(a[1], b[1]) - w / 2, max(a[0], b[0]) + w / 2, max(a[1], b[1]) + w / 2)}
        self._add(it)
        return it

    # -------------------------------------------------------------- checks
    def board_ok_point(self, x, y, rad):
        """Copper disc (x, y, rad) is inside the outline with edge clearance, clear of cut-outs."""
        m = rad + self.r.edge_clearance + self.margin
        if not pip(x, y, self.outline) or pt_poly_edge(x, y, self.outline) < m:
            return False
        for c in self.cutouts:
            if pip(x, y, c) or pt_poly_edge(x, y, c) < m:
                return False
        return True

    def board_ok_seg(self, a, b, w):
        m = w / 2.0 + self.r.edge_clearance + self.margin
        if not pip(a[0], a[1], self.outline) or seg_poly_edge(a, b, self.outline) < m:
            return False
        for c in self.cutouts:
            if pip(a[0], a[1], c) or seg_poly_edge(a, b, c) < m:
                return False
        return True

    def via_ok(self, x, y, r, drill, net, courtyard_ignore=(), check_court=True, ignore=None):
        self.why = "edge"
        if not self.board_ok_point(x, y, r):
            return False
        self.why = "keepout"
        for ko in self.keepouts:
            if ko["vias"] and ko["bb"][0] - r <= x <= ko["bb"][2] + r and ko["bb"][1] - r <= y <= ko["bb"][3] + r:
                if pip(x, y, ko["poly"]) or pt_poly_edge(x, y, ko["poly"]) < r:
                    return False
        if check_court:
            for rect, ref in self.court:
                if ref not in courtyard_ignore and pt_rect(x, y, rect) < r:
                    self.why = "courtyard of " + ref
                    return False
        rr = self.r
        m = r + 1.0
        for it in self.near(x - m, y - m, x + m, y + m):
            if ignore is not None and id(it) in ignore:
                continue
            same = it["net"] == net and net != ""
            k = it["kind"]
            self.why = "via: %s %s %s" % (k, it["net"], it.get("ref", ""))
            if k == "via":
                d = math.hypot(x - it["x"], y - it["y"])
                if d < drill / 2.0 + it["drill"] / 2.0 + rr.min_hole_to_hole + self.margin:
                    return False
                if not same and d < r + it["r"] + self.clr(net, it["net"]):
                    return False
            elif k == "pad":
                d = pad_dist(it, x, y)
                if it.get("drill"):
                    dh = math.hypot(x - it["cx"], y - it["cy"])
                    if dh < drill / 2.0 + it["drill"] / 2.0 + rr.min_hole_to_hole + self.margin:
                        return False
                if same:
                    if d < r + 0.05 and not it.get("drill"):
                        return False      # no via in (or touching) an SMD pad
                elif d < r + self.clr(net, it["net"]) or d < drill / 2.0 + rr.min_hole_clearance + self.margin:
                    return False
            else:
                if not same and pt_seg(x, y, it["a"][0], it["a"][1], it["b"][0], it["b"][1]) < r + it["w"] / 2.0 + self.clr(net, it["net"]):
                    return False
        return True

    def seg_ok(self, a, b, w, layer, net, own=None, ignore=None):
        """Track a-b (width w, layer) is clear of everything of other nets.  *own*: item ids that
        the track may overlap whatever their net (the pad it starts from)."""
        self.why = "seg edge"
        if not self.board_ok_seg(a, b, w):
            return False
        self.why = "seg keepout"
        for ko in self.keepouts:
            if ko["tracks"] and layer in ko["layers"]:
                if pip(a[0], a[1], ko["poly"]) or pip(b[0], b[1], ko["poly"]) or seg_poly_edge(a, b, ko["poly"]) < w / 2.0:
                    return False
        m = w / 2.0 + 1.0
        for it in self.near(min(a[0], b[0]) - m, min(a[1], b[1]) - m, max(a[0], b[0]) + m, max(a[1], b[1]) + m):
            if layer not in it["layers"]:
                continue
            if (own is not None and id(it) in own) or (ignore is not None and id(it) in ignore):
                continue
            if it["net"] == net and net != "":
                continue
            c = self.clr(net, it["net"]) + w / 2.0
            k = it["kind"]
            self.why = "seg: %s %s %s" % (k, it["net"], it.get("ref", ""))
            if k == "via":
                if pt_seg(it["x"], it["y"], a[0], a[1], b[0], b[1]) < c + it["r"]:
                    return False
            elif k == "pad":
                if pad_seg_dist(it, a, b) < c:
                    return False
            else:
                if seg_seg(a, b, it["a"], it["b"]) < c + it["w"] / 2.0:
                    return False
        return True

    def courtyard_of(self, ref):
        return [rect for rect, r in self.court if r == ref]


def pad_item(pad, ref, lid):
    """Copper description of a pad (None if it has no copper, e.g. paste-only apertures).
    *lid*: {copper layer name: layer id}."""
    lays = {l for l, i in lid.items() if pad.IsOnLayer(i)}
    if not lays:
        return None
    bb = pad.GetBoundingBox()
    rect = (T(bb.GetLeft()), T(bb.GetTop()), T(bb.GetRight()), T(bb.GetBottom()))
    p = pad.GetPosition()
    drill = T(pad.GetDrillSize().x) if pad.GetDrillSize().x > 0 else 0.0
    it = {"kind": "pad", "rect": rect, "net": pad.GetNetname(), "layers": lays, "ref": ref, "num": pad.GetNumber(),
          "cx": T(p.x), "cy": T(p.y), "drill": drill, "bb": rect, "circle": None}
    try:
        shape = pad.GetShape(pcbnew.F_Cu)
    except TypeError:
        shape = pad.GetShape()
    if shape == pcbnew.PAD_SHAPE_CIRCLE:
        it["circle"] = (rect[2] - rect[0]) / 2.0
    return it


def pad_dist(it, x, y):
    if it["circle"] is not None:
        return max(0.0, math.hypot(x - it["cx"], y - it["cy"]) - it["circle"])
    return pt_rect(x, y, it["rect"])


def pad_seg_dist(it, a, b):
    if it["circle"] is not None:
        return max(0.0, pt_seg(it["cx"], it["cy"], a[0], a[1], b[0], b[1]) - it["circle"])
    return seg_rect(a, b, it["rect"])
