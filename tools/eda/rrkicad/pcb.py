"""PCB generation with the pcbnew Python API (runs inside the KiCad container).

build_pcb()   definition + schematic netlist -> unrouted .kicad_pcb
export_dsn()  Specctra DSN for Freerouting
finish_pcb()  import SES, verify pre-routes, fill zones, add fab notes, save
"""
import hashlib
import math
import os

import pcbnew

from .model import DefinitionError
from . import locallib
from .autoplace import autoplace

MM = pcbnew.FromMM
STOCK_FP_DIR = os.environ.get("KICAD9_FOOTPRINT_DIR", "/usr/share/kicad/footprints")
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0)}


def _seed(*parts):
    h = hashlib.sha1("\x1f".join(parts).encode()).digest()
    pcbnew.KIID.SeedGenerator(int.from_bytes(h[:4], "big"))


class Frame:
    """Board (x right, y up) <-> KiCad page coordinates (y down)."""

    def __init__(self, ox, oy):
        self.ox, self.oy = ox, oy

    def k(self, x, y):
        return pcbnew.VECTOR2I(MM(self.ox + x), MM(self.oy - y))

    def kmm(self, x, y):
        return (self.ox + x, self.oy - y)

    def user(self, v):
        return (round(pcbnew.ToMM(v.x) - self.ox, 4), round(self.oy - pcbnew.ToMM(v.y), 4))


def outline_bbox(board):
    xs = [p[0] for p in board.outline["pts"]]
    ys = [p[1] for p in board.outline["pts"]]
    return (min(xs), min(ys), max(xs), max(ys))


def page_and_origin(board):
    x0, y0, x1, y1 = outline_bbox(board)
    w, h = x1 - x0, y1 - y0
    paper = None
    for name in ("A4", "A3", "A2", "A1"):
        pw, ph = PAPER[name]
        if w <= pw - 150 and h <= ph - 80:
            paper = name
            break
    if paper is None:
        raise DefinitionError("board too large for the supported page sizes")
    pw, ph = PAPER[paper]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    ox = round(30.0 + w / 2.0 + 20.0 - cx)
    oy = round(ph / 2.0 - 10.0 + cy)
    return paper, pw, ph, float(ox), float(oy)


def _stackup(board):
    t = board.thickness
    L = []

    def lay(name, typ, th=None, extra=""):
        s = '\t\t\t(layer "%s"\n\t\t\t\t(type "%s")\n' % (name, typ)
        if th is not None:
            s += "\t\t\t\t(thickness %s)\n" % (("%.4f" % th).rstrip("0").rstrip("."))
        s += extra + "\t\t\t)\n"
        L.append(s)
    die = '\t\t\t\t(material "FR4")\n\t\t\t\t(epsilon_r 4.5)\n\t\t\t\t(loss_tangent 0.02)\n'
    lay("F.SilkS", "Top Silk Screen")
    lay("F.Paste", "Top Solder Paste")
    lay("F.Mask", "Top Solder Mask", 0.01)
    lay("F.Cu", "copper", 0.035)
    if board.layers == 2:
        lay("dielectric 1", "core", t - 0.09, die)
        desc = ["F.Cu 0.035", "core FR-4 %.3f" % (t - 0.09), "B.Cu 0.035"]
    elif board.layers == 4:
        pp, inner = 0.2104, 0.0152
        core = t - 0.09 - 2 * pp - 2 * inner
        lay("dielectric 1", "prepreg", pp, die)
        lay("In1.Cu", "copper", inner)
        lay("dielectric 2", "core", core, die)
        lay("In2.Cu", "copper", inner)
        lay("dielectric 3", "prepreg", pp, die)
        desc = ["F.Cu 0.035 (signal)", "prepreg %.4f" % pp, "In1.Cu %.4f (plane)" % inner,
                "core FR-4 %.4f" % core, "In2.Cu %.4f (plane)" % inner, "prepreg %.4f" % pp,
                "B.Cu 0.035 (signal)"]
    else:
        pp, ppm, inner = 0.0994, 0.1088, 0.0152
        core = (t - 0.09 - 2 * pp - ppm - 4 * inner) / 2.0
        lay("dielectric 1", "prepreg", pp, die)
        lay("In1.Cu", "copper", inner)
        lay("dielectric 2", "core", core, die)
        lay("In2.Cu", "copper", inner)
        lay("dielectric 3", "prepreg", ppm, die)
        lay("In3.Cu", "copper", inner)
        lay("dielectric 4", "core", core, die)
        lay("In4.Cu", "copper", inner)
        lay("dielectric 5", "prepreg", pp, die)
        desc = ["F.Cu 0.035 (signal)", "prepreg %.4f" % pp, "In1.Cu %.4f (GND plane)" % inner,
                "core FR-4 %.4f" % core, "In2.Cu %.4f (signal)" % inner, "prepreg %.4f" % ppm,
                "In3.Cu %.4f (signal)" % inner, "core FR-4 %.4f" % core, "In4.Cu %.4f (power plane)" % inner,
                "prepreg %.4f" % pp, "B.Cu 0.035 (signal)"]
    lay("B.Cu", "copper", 0.035)
    lay("B.Mask", "Bottom Solder Mask", 0.01)
    lay("B.Paste", "Bottom Solder Paste")
    lay("B.SilkS", "Bottom Silk Screen")
    text = "\t\t(stackup\n" + "".join(L) + '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)\n'
    return text, desc


def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def header_text(board, paper, ox, oy):
    stack, _ = _stackup(board)
    ids = {"In1.Cu": 4, "In2.Cu": 6, "In3.Cu": 8, "In4.Cu": 10}
    inner = "".join('\t\t(%d "%s" %s)\n' % (ids[l], l, "power" if l in board.plane_layers else "signal")
                    for l in board.copper_layers[1:-1])
    return (
        '(kicad_pcb\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n'
        '\t(general\n\t\t(thickness %s)\n\t\t(legacy_teardrops no)\n\t)\n'
        '\t(paper "%s")\n'
        '\t(title_block\n\t\t(title %s)\n\t\t(date %s)\n\t\t(rev %s)\n\t\t(company %s)\n'
        '\t\t(comment 1 %s)\n\t\t(comment 2 %s)\n\t\t(comment 3 %s)\n\t)\n'
        '\t(layers\n\t\t(0 "F.Cu" signal)\n%s\t\t(2 "B.Cu" signal)\n'
        '\t\t(9 "F.Adhes" user "F.Adhesive")\n\t\t(11 "B.Adhes" user "B.Adhesive")\n'
        '\t\t(13 "F.Paste" user)\n\t\t(15 "B.Paste" user)\n'
        '\t\t(5 "F.SilkS" user "F.Silkscreen")\n\t\t(7 "B.SilkS" user "B.Silkscreen")\n'
        '\t\t(1 "F.Mask" user)\n\t\t(3 "B.Mask" user)\n'
        '\t\t(17 "Dwgs.User" user "User.Drawings")\n\t\t(19 "Cmts.User" user "User.Comments")\n'
        '\t\t(21 "Eco1.User" user "User.Eco1")\n\t\t(23 "Eco2.User" user "User.Eco2")\n'
        '\t\t(25 "Edge.Cuts" user)\n\t\t(27 "Margin" user)\n'
        '\t\t(31 "F.CrtYd" user "F.Courtyard")\n\t\t(29 "B.CrtYd" user "B.Courtyard")\n'
        '\t\t(35 "F.Fab" user)\n\t\t(33 "B.Fab" user)\n\t)\n'
        '\t(setup\n%s\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n'
        '\t\t(tenting front back)\n\t\t(aux_axis_origin %s %s)\n\t\t(grid_origin %s %s)\n\t)\n'
        '\t(net 0 "")\n\t(embedded_fonts no)\n)\n'
    ) % (("%.4f" % board.thickness).rstrip("0").rstrip("."), paper, _q(board.title), _q(board.date), _q(board.rev),
         _q(board.company), _q("Doc No: %s" % board.docnum), _q("Board: %s" % board.name),
         _q("Generated by rrkicad from board.py"), inner, stack,
         ("%.4f" % ox).rstrip("0").rstrip("."), ("%.4f" % oy).rstrip("0").rstrip("."),
         ("%.4f" % ox).rstrip("0").rstrip("."), ("%.4f" % oy).rstrip("0").rstrip("."))


# ----------------------------------------------------------------- geometry
def fillet(pts, radius):
    """Round the corners of a closed polygon.

    Returns [(kind, a, b[, mid])]: ("line", p, q) / ("arc", start, end, mid), and a
    densified point list approximating the same shape."""
    n = len(pts)
    if radius <= 0:
        return [("line", pts[i], pts[(i + 1) % n]) for i in range(n)], list(pts)
    corners = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        u1, u2 = (v1[0] / l1, v1[1] / l1), (v2[0] / l2, v2[1] / l2)
        cosang = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        ang = math.acos(cosang)
        if ang < 1e-6 or abs(ang - math.pi) < 1e-6:
            corners.append((p1, p1, None, None))
            continue
        d = radius / math.tan(ang / 2.0)
        if d > min(l1, l2) / 2.0 + 1e-9:
            raise DefinitionError("corner radius %.2f too large for outline edge" % radius)
        a = (p1[0] + u1[0] * d, p1[1] + u1[1] * d)
        b = (p1[0] + u2[0] * d, p1[1] + u2[1] * d)
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        bl = math.hypot(*bis)
        cdist = radius / math.sin(ang / 2.0)
        c = (p1[0] + bis[0] / bl * cdist, p1[1] + bis[1] / bl * cdist)
        mid = (c[0] - bis[0] / bl * radius, c[1] - bis[1] / bl * radius)
        corners.append((a, b, mid, c))
    segs, dense = [], []
    for i in range(n):
        a, b, mid, c = corners[i]
        na = corners[(i + 1) % n][0]
        if mid is not None:
            segs.append(("arc", a, b, mid))
            a0 = math.atan2(a[1] - c[1], a[0] - c[0])
            a1 = math.atan2(b[1] - c[1], b[0] - c[0])
            da = a1 - a0
            while da > math.pi:
                da -= 2 * math.pi
            while da < -math.pi:
                da += 2 * math.pi
            for k in range(0, 9):
                t = a0 + da * k / 8.0
                dense.append((c[0] + radius * math.cos(t), c[1] + radius * math.sin(t)))
        else:
            dense.append(a)
        if math.hypot(na[0] - b[0], na[1] - b[1]) > 1e-9:
            segs.append(("line", b, na))
    return segs, dense


def circle_pts(x, y, dia, n=48):
    r = dia / 2.0
    return [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


class Builder:
    def __init__(self, board, paths):
        self.b, self.paths = board, paths
        self.paper, self.pw, self.ph, ox, oy = page_and_origin(board)
        self.fr = Frame(ox, oy)
        self.warnings = []
        self.fps = {}
        self.envelope_files = set()
        self._all_keepouts = []

    # ------------------------------------------------------------ primitives
    def layer(self, name):
        lid = self.pcb.GetLayerID(name)
        if lid < 0:
            raise DefinitionError("unknown layer '%s'" % name)
        return lid

    def copper_ids(self, names):
        out = []
        for n in names:
            if n == "*.Cu":
                out += [self.layer(l) for l in self.b.copper_layers]
            else:
                out.append(self.layer(n))
        return out

    def net(self, name):
        ni = self.pcb.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(self.pcb, name)
            self.pcb.Add(ni)
        return ni

    def _edge(self, segs):
        for s in segs:
            sh = pcbnew.PCB_SHAPE(self.pcb)
            if s[0] == "line":
                sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
                sh.SetStart(self.fr.k(*s[1]))
                sh.SetEnd(self.fr.k(*s[2]))
            else:
                sh.SetShape(pcbnew.SHAPE_T_ARC)
                sh.SetArcGeometry(self.fr.k(*s[1]), self.fr.k(*s[3]), self.fr.k(*s[2]))
            sh.SetLayer(pcbnew.Edge_Cuts)
            sh.SetWidth(MM(0.05))
            self.pcb.Add(sh)

    def _poly_zone(self, pts):
        z = pcbnew.ZONE(self.pcb)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            v = self.fr.k(x, y)
            ol.Append(v.x, v.y)
        return z

    # ----------------------------------------------------------------- build
    def build(self, nl, pages):
        b, paths = self.b, self.paths
        with open(paths.pcb, "w") as f:
            f.write(header_text(b, self.paper, self.fr.ox, self.fr.oy))
        _seed(b.name, "build")
        self.pcb = pcbnew.LoadBoard(paths.pcb)
        pcb = self.pcb
        ds = pcb.GetDesignSettings()
        origin = self.fr.k(0, 0)
        ds.SetAuxOrigin(origin)
        ds.SetGridOrigin(origin)
        # nets: definition order first, then the schematic's unconnected-(...) nets
        for name in list(b._nets) + sorted(n for n in nl.nets if n not in b._nets):
            self.net(name)
        # outline
        segs, self.outline_dense = fillet(b.outline["pts"], b.outline["radius"])
        self._edge(segs)
        self.cutout_polys = []
        for c in b.cutouts:
            if c["kind"] == "circle":
                sh = pcbnew.PCB_SHAPE(pcb)
                sh.SetShape(pcbnew.SHAPE_T_CIRCLE)
                sh.SetCenter(self.fr.k(c["x"], c["y"]))
                sh.SetEnd(self.fr.k(c["x"] + c["dia"] / 2.0, c["y"]))
                sh.SetLayer(pcbnew.Edge_Cuts)
                sh.SetWidth(MM(0.05))
                pcb.Add(sh)
                self.cutout_polys.append(circle_pts(c["x"], c["y"], c["dia"]))
            else:
                segs, dense = fillet(c["pts"], c.get("radius", 0))
                self._edge(segs)
                self.cutout_polys.append(dense)
        page_by_group = {}
        for p in pages:
            page_by_group.setdefault(p.group.name, p)
        # footprints
        for part in b.parts:
            self._add_part(part, nl, pages)
        for h in b.holes:
            self._add_hole(h)
        # keep-outs before auto-placement (they block it)
        for ko in b.keepouts:
            self._add_keepout(ko)
        self._replicas()                 # copies of explicitly placed sources (block the auto-arranger)
        placed = autoplace(self)
        self._replicas()                 # copies of auto-arranged sources
        for part in b.parts:
            if not part.placed:
                raise DefinitionError("%s could not be placed" % part.ref)
        self._silk_refs()
        for z in b.zones:
            self._add_zone(z)
        for t in b.tracks:
            self._add_track(t)
        for v in b.vias:
            self._add_via(v)
        for t in b.texts:
            self._add_text(t)
        self.block_copies = self._block_routes()
        # fine-pitch escape first (it also takes the plane pads of those ICs), then plane fan-out
        from .escape import escape
        esc, handled = escape(self)
        for sk in esc["skipped"]:
            if "no legal escape position" in sk:
                self.warnings.append("escape: " + sk + " (left to the autorouter)")
        # signal escape vias (KiCad mm): the post-route clean-up may drop the ones the router did not use
        import json
        with open(os.path.join(self.paths.route_dir, "escape_vias.json"), "w") as f:
            json.dump(esc.pop("_vias", []), f)
            f.write("\n")
        self.escape = esc
        fan = {"plane_nets": [], "vias": 0, "failed": []}
        if b.routing.get("plane_fanout", True):
            from .fanout import plane_fanout
            self.via_keepouts = [[self.fr.kmm(*p) for p in ko["_pts"]] for ko in self._all_keepouts if ko["vias"]]
            fan = plane_fanout(self, skip=handled)
            for f in fan["failed"]:
                self.warnings.append("plane fan-out: no legal via position for " + f + " (left to the autorouter)")
        self.fanout = fan
        pcb.BuildConnectivity()
        pcbnew.SaveBoard(paths.pcb, pcb, True)
        placement = {}
        for part in b.parts:
            placement[part.ref] = [round(part.x, 3), round(part.y, 3), round(part.rot, 1), part.side]
        x0, y0, x1, y1 = outline_bbox(b)
        return {"placement": placement, "autoplaced": placed, "warnings": self.warnings, "fanout": fan,
                "escape": self.escape,
                "block_copies": self.block_copies,
                "origin": [self.fr.ox, self.fr.oy], "bbox": [x0, y0, x1, y1]}

    def _load_fp(self, lib_id):
        lib, name = lib_id.split(":", 1)
        if lib == locallib.NICK:
            d = os.path.join(self.paths.dir, locallib.NICK + ".pretty")
        else:
            d = os.path.join(STOCK_FP_DIR, lib + ".pretty")
        if not os.path.exists(os.path.join(d, name + ".kicad_mod")):
            hint = ""
            if os.path.isdir(d):
                import difflib
                close = difflib.get_close_matches(name, [f[:-10] for f in os.listdir(d)], 4)
                hint = ("; did you mean: " + ", ".join(close)) if close else ""
            raise DefinitionError("footprint '%s' not found%s" % (lib_id, hint))
        fp = pcbnew.FootprintLoad(d, name)
        if fp is None:
            raise DefinitionError("footprint '%s' failed to load" % lib_id)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        return fp

    def _add_part(self, part, nl, pages):
        pcb = self.pcb
        fp = self._load_fp(part.footprint)
        fp.SetReference(part.ref)
        fp.SetValue(part.value)
        comp = nl.components[part.ref]
        fp.SetPath(pcbnew.KIID_PATH(comp["sheet_tstamps"] + comp["tstamps"][0]))
        fp.SetSheetname(comp["sheet_names"])
        page = [p for p in pages if any(c.part is part for c in p.cells)][0]
        fp.SetSheetfile(page.file)
        # mirror what "Update PCB from schematic" does with symbol fields
        sym = part.sym
        ds = part.datasheet if part.datasheet is not None else sym.prop("Datasheet")
        de = part.description if part.description is not None else sym.prop("Description")
        for key, val in (("Datasheet", ds), ("Description", de)):
            try:
                fp.GetFieldByName(key).SetText(val)
            except Exception:
                pass
        extra = [("MPN", part.mpn), ("Manufacturer", part.mfr)]
        if part.notes:
            extra.append(("Notes", part.notes))
        if part.verify:
            extra.append(("Verify", "MPN/part data not verified against manufacturer data"))
        for k in sorted(part.fields):
            extra.append((k, str(part.fields[k])))
        for key, val in extra:
            fp.SetField(key, val)
            f = fp.GetFieldByName(key)
            f.SetVisible(False)
            f.SetLayer(pcbnew.F_Fab)
        attrs = fp.GetAttributes()
        if part.dnp:
            attrs |= pcbnew.FP_DNP
        if not part.bom:
            attrs |= pcbnew.FP_EXCLUDE_FROM_BOM
        fp.SetAttributes(attrs)
        pcb.Add(fp)
        # pad nets from the schematic netlist
        pad_numbers = set()
        for pad in fp.Pads():
            num = pad.GetNumber()
            pad_numbers.add(num)
            net = nl.pin_net.get((part.ref, num))
            if net is not None:
                pad.SetNet(self.net(net))
            elif num and pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                self.warnings.append("%s pad '%s' has no pin in symbol %s (left without net)" % (part.ref, num, part.symbol))
        for num, net in part.pin_net.items():
            if num not in pad_numbers:
                if net is not None:
                    raise DefinitionError("%s: symbol pin %s (net %s) has no pad in footprint %s" % (
                        part.ref, num, net, part.footprint))
                self.warnings.append("%s: unconnected symbol pin %s has no pad in footprint %s" % (part.ref, num, part.footprint))
        if part.zone_connect:
            fp.SetLocalZoneConnection({"solid": pcbnew.ZONE_CONNECTION_FULL, "thermal": pcbnew.ZONE_CONNECTION_THERMAL,
                                       "none": pcbnew.ZONE_CONNECTION_NONE}[part.zone_connect])
        model = part.model
        if not model and self.b.envelopes and not self._stock_model_exists(fp):
            model = self._envelope(part, fp)
        if model:
            fp.Models().clear()
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = model
            fp.Add3DModel(m)
        self.fps[part.ref] = fp
        if part.placed:
            self.place(part, part.x, part.y, part.rot, part.side)

    def _stock_model_exists(self, fp):
        base = os.environ.get("KICAD9_3DMODEL_DIR", "/usr/share/kicad/3dmodels")
        for m in fp.Models():
            fn = str(m.m_Filename).replace("${KICAD9_3DMODEL_DIR}", base).replace("${KIPRJMOD}", self.paths.dir)
            stem = os.path.splitext(fn)[0]
            if any(os.path.exists(stem + ext) for ext in (".step", ".stp", ".STEP", ".wrl")):
                return True
        return False

    _HEIGHTS = (("R_0201", 0.26), ("R_0402", 0.35), ("R_0603", 0.45), ("R_0805", 0.5), ("R_1206", 0.55),
                ("C_0201", 0.3), ("C_0402", 0.5), ("C_0603", 0.8), ("C_0805", 1.25), ("C_1206", 1.6),
                ("L_0603", 0.8), ("L_0805", 0.9), ("LED_0603", 0.6), ("LED_0805", 0.8),
                ("SOT-23", 1.1), ("SOT-223", 1.6), ("SOIC", 1.75), ("TSSOP", 1.2), ("LQFP", 1.6), ("TQFP", 1.2),
                ("QFN", 0.9), ("DFN", 0.8), ("USON", 0.55), ("PinHeader_", 8.5))

    def _envelope(self, part, fp):
        """Box 3D model from the F.Fab outline and a height (part.height or a per-package default)."""
        from .stepbox import box_step
        xs, ys = [], []
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_Fab and g.GetClass() == "PCB_SHAPE":
                bb = g.GetBoundingBox()
                xs += [bb.GetLeft(), bb.GetRight()]
                ys += [bb.GetTop(), bb.GetBottom()]
        if not xs:
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                xs += [bb.GetLeft(), bb.GetRight()]
                ys += [bb.GetTop(), bb.GetBottom()]
        if not xs:
            return None
        pos = fp.GetPosition()
        x0, x1 = pcbnew.ToMM(min(xs) - pos.x), pcbnew.ToMM(max(xs) - pos.x)
        y0, y1 = pcbnew.ToMM(min(ys) - pos.y), pcbnew.ToMM(max(ys) - pos.y)
        name = part.footprint.split(":", 1)[1]
        h = part.height
        if h is None:
            for key, val in self._HEIGHTS:
                if name.startswith(key) or ("_" + key) in name:
                    h = val
                    break
        if h is None:
            h = 1.0
            self.warnings.append("%s: 3D envelope uses the default height 1.0 mm (give height=)" % part.ref)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        fn = "%s_h%s.step" % (safe, ("%.2f" % h).replace(".", "p"))
        d = os.path.join(self.paths.dir, "3d")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, fn)
        text = box_step(safe, round(x0, 4), round(-y1, 4), 0.0, round(x1, 4), round(-y0, 4), float(h), self.b.date or "1970-01-01")
        if not os.path.exists(path) or open(path).read() != text:
            with open(path, "w") as f:
                f.write(text)
        self.envelope_files.add(fn)
        return "${KIPRJMOD}/3d/" + fn

    def place(self, part, x, y, rot, side):
        fp = self.fps[part.ref]
        pos = self.fr.k(x, y)
        if side == "B" and not fp.IsFlipped():
            fp.SetPosition(pos)
            fp.Flip(pos, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(pos)
        fp.SetOrientationDegrees(rot)
        part.x, part.y, part.rot, part.side = x, y, rot, side

    def _replicas(self):
        for _ in range(8):               # chains: a copy of a copy
            done = True
            for part in self.b.parts:
                if part.replica_of and not part.placed:
                    src = self.b.part(part.replica_of[0])
                    if src.placed:
                        self.place(part, round(src.x + part.replica_of[1], 4), round(src.y + part.replica_of[2], 4),
                                   src.rot, src.side)
                        done = False
            if done:
                break

    def _block_routes(self):
        """Pre-route the source block and its copies from route/blocks.json (see Board.replicate)."""
        import json
        b = self.b
        path = os.path.join(self.paths.route_dir, "blocks.json")
        reps = [r for r in b.replicas if r["routes"]]
        if not reps or not os.path.exists(path):
            return 0
        with open(path) as f:
            stored = json.load(f)
        by_key = {(s["first"], s["dx"], s["dy"]): s for s in stored}
        n = 0
        done_src = set()
        # copper already on the board (definition pre-routes) or already replayed is not added twice
        # (a definition that pre-routes every lane itself gave co-located vias on the copies)
        have = set()
        for t in self.pcb.GetTracks():
            if t.GetClass() == "PCB_VIA":
                x_, y_ = self.fr.user(t.GetPosition())
                have.add(("via", t.GetNetname(), round(x_, 3), round(y_, 3)))
            else:
                a_, b_ = self.fr.user(t.GetStart()), self.fr.user(t.GetEnd())
                a_, b_ = (round(a_[0], 3), round(a_[1], 3)), (round(b_[0], 3), round(b_[1], 3))
                have.add(("seg", t.GetNetname(), t.GetLayerName(), min(a_, b_), max(a_, b_)))
        for rep in reps:
            s = by_key.get((sorted(rep["pairs"])[0], rep["dx"], rep["dy"]))
            if s is None or s["sig"] != block_signature(b, rep["pairs"]):
                self.warnings.append("replicate: stored block routes are stale (source placement changed) - "
                                     "copies of %s... are routed by the autorouter; rebuild to refresh" % sorted(rep["pairs"])[0])
                continue
            for it in s["items"]:
                for net, dx, dy in ((it["src"], 0.0, 0.0), (it["dst"], rep["dx"], rep["dy"])):
                    if dx == 0.0 and dy == 0.0:
                        key = json.dumps(it, sort_keys=True)
                        if key in done_src:
                            continue
                        done_src.add(key)
                    if it["k"] == "via":
                        key = ("via", net, round(it["xy"][0] + dx, 3), round(it["xy"][1] + dy, 3))
                    else:
                        a_ = (round(it["a"][0] + dx, 3), round(it["a"][1] + dy, 3))
                        b_ = (round(it["b"][0] + dx, 3), round(it["b"][1] + dy, 3))
                        key = ("seg", net, it["layer"], min(a_, b_), max(a_, b_))
                    if key in have:
                        continue
                    have.add(key)
                    if it["k"] == "via":
                        self._add_via({"net": net, "x": it["xy"][0] + dx, "y": it["xy"][1] + dy, "dia": it["dia"], "drill": it["drill"]})
                    else:
                        self._add_track({"net": net, "layer": it["layer"], "width": it["w"],
                                         "pts": [(it["a"][0] + dx, it["a"][1] + dy), (it["b"][0] + dx, it["b"][1] + dy)]})
                    n += 1
        return n

    def _add_hole(self, h):
        fp = self._load_fp("%s:%s" % (locallib.NICK, h["footprint"]))
        fp.SetReference(h["ref"])
        fp.SetValue("M-hole %smm" % locallib._n(h["drill"]))
        self.pcb.Add(fp)
        fp.SetPosition(self.fr.k(h["x"], h["y"]))
        fp.SetLocked(True)
        if h["plated"] and h["net"]:
            for pad in fp.Pads():
                pad.SetNet(self.net(h["net"]))
        self.fps[h["ref"]] = fp
        if h["keepout"]:
            self._add_keepout({"name": "KO_%s" % h["ref"], "polygon": None, "circle": (h["x"], h["y"], h["keepout"]),
                               "layers": ["*.Cu"], "tracks": True, "vias": True, "pads": False, "copper": True,
                               "footprints": True})

    def _add_keepout(self, ko):
        pts = ko["polygon"] or circle_pts(ko["circle"][0], ko["circle"][1], ko["circle"][2])
        z = self._poly_zone(pts)
        ls = pcbnew.LSET()
        for lid in self.copper_ids(ko["layers"]):
            ls.AddLayer(lid)
        z.SetLayerSet(ls)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(bool(ko["tracks"]))
        z.SetDoNotAllowVias(bool(ko["vias"]))
        z.SetDoNotAllowPads(bool(ko["pads"]))
        z.SetDoNotAllowCopperPour(bool(ko["copper"]))
        z.SetDoNotAllowFootprints(bool(ko["footprints"]))
        z.SetZoneName(ko["name"])
        self.pcb.Add(z)
        ko["_pts"] = pts
        self._all_keepouts.append(ko)

    def _add_zone(self, zd):
        b = self.b
        pts = zd["polygon"] or b.outline["pts"]
        z = self._poly_zone(pts)
        ls = pcbnew.LSET()
        for lid in self.copper_ids(zd["layers"]):
            ls.AddLayer(lid)
        z.SetLayerSet(ls)
        z.SetNet(self.net(zd["net"]))
        z.SetZoneName(zd["name"])
        z.SetAssignedPriority(int(zd["priority"]))
        clr = zd["clearance"] if zd["clearance"] is not None else max(b.rules.clearance, b.class_of(zd["net"])["clearance"], 0.2)
        z.SetLocalClearance(MM(clr))
        z.SetMinThickness(MM(zd["min_width"]))
        z.SetPadConnection({"thermal": pcbnew.ZONE_CONNECTION_THERMAL, "solid": pcbnew.ZONE_CONNECTION_FULL,
                            "none": pcbnew.ZONE_CONNECTION_NONE}[zd["connect"]])
        z.SetThermalReliefGap(MM(zd["thermal_gap"]))
        z.SetThermalReliefSpokeWidth(MM(zd["thermal_width"]))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS if zd["islands"] == "remove"
                               else pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        self.pcb.Add(z)

    def _add_track(self, t):
        b = self.b
        w = t["width"] or b.class_of(t["net"])["track"]
        lid = self.layer(t["layer"])
        for p, q in zip(t["pts"][:-1], t["pts"][1:]):
            tr = pcbnew.PCB_TRACK(self.pcb)
            tr.SetStart(self.fr.k(*p))
            tr.SetEnd(self.fr.k(*q))
            tr.SetLayer(lid)
            tr.SetWidth(MM(w))
            tr.SetNet(self.net(t["net"]))
            tr.SetLocked(True)
            self.pcb.Add(tr)

    def _add_via(self, v):
        nc = self.b.class_of(v["net"])
        via = pcbnew.PCB_VIA(self.pcb)
        via.SetPosition(self.fr.k(v["x"], v["y"]))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(pcbnew.F_Cu, MM(v["dia"] or nc["via_dia"]))
        via.SetDrill(MM(v["drill"] or nc["via_drill"]))
        via.SetNet(self.net(v["net"]))
        via.SetLocked(True)
        self.pcb.Add(via)

    def _add_text(self, t):
        b = self.b
        txt = pcbnew.PCB_TEXT(self.pcb)
        s = t["text"].format(name=b.name, rev=b.rev, date=b.date, title=b.title, docnum=b.docnum)
        txt.SetText(s)
        lid = self.layer(t["layer"])
        txt.SetLayer(lid)
        txt.SetPosition(self.fr.k(t["x"], t["y"]))
        txt.SetTextSize(pcbnew.VECTOR2I(MM(t["size"]), MM(t["size"])))
        txt.SetTextThickness(MM(t["thickness"] or max(0.1, round(t["size"] * 0.15, 2))))
        txt.SetTextAngleDegrees(t["rot"])
        txt.SetHorizJustify({"left": pcbnew.GR_TEXT_H_ALIGN_LEFT, "center": pcbnew.GR_TEXT_H_ALIGN_CENTER,
                             "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[t["justify"]])
        if t["layer"].startswith("B."):
            txt.SetMirrored(True)
        self.pcb.Add(txt)

    def _silk_refs(self):
        b = self.b
        for part in b.parts:
            fp = self.fps[part.ref]
            ref = fp.Reference()
            sr = part.silk_ref
            if sr is None:
                sr = b.silk_refs
            if sr is False:
                ref.SetVisible(False)
            elif sr is not True:
                sr = tuple(sr)
                ref.SetPosition(self.fr.k(sr[0], sr[1]))
                if len(sr) > 2:
                    ref.SetTextAngleDegrees(sr[2])
                size = sr[3] if len(sr) > 3 else 0.8
                ref.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
                ref.SetTextThickness(MM(max(0.1, round(size * 0.15, 2))))
                ref.SetVisible(True)
        for h in b.holes:
            self.fps[h["ref"]].Reference().SetVisible(True)


def build_pcb(board, paths, nl, pages, root_uuid):
    from .model import resolve  # noqa: F401  (nets already resolved by the caller)
    if not hasattr(board, "_nets"):
        board._nets = {}
        for part in board.parts:
            for num, net in part.pin_net.items():
                if net:
                    board._nets.setdefault(net, []).append((part.ref, num))
    bld = Builder(board, paths)
    return bld.build(nl, pages)


# -------------------------------------------------------------------- routing
def _edge_guard(pcb, board):
    """Autorouter-only keep-out bands along the outline (inside) and around cut-outs so
    that routed copper respects the board-edge clearance (the DSN format has no such rule).
    Added to the in-memory copy used for the DSN export, never saved."""
    paper, pw, ph, ox, oy = page_and_origin(board)
    fr = Frame(ox, oy)
    w = board.rules.edge_clearance + 0.05
    polys = [(fillet(board.outline["pts"], board.outline["radius"])[1], True)]
    for c in board.cutouts:
        pts = circle_pts(c["x"], c["y"], c["dia"]) if c["kind"] == "circle" else fillet(c["pts"], c.get("radius", 0))[1]
        polys.append((pts, False))
    ls = pcbnew.LSET()
    for l in board.copper_layers:
        ls.AddLayer(pcb.GetLayerID(l))
    for pts, inward in polys:
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        sign = (1.0 if area > 0 else -1.0) * (1.0 if inward else -1.0)   # left normal points inside for CCW polygons
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            dx, dy = q[0] - p[0], q[1] - p[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                continue
            nx, ny = -dy / ln * sign * w, dx / ln * sign * w
            ex, ey = dx / ln * w, dy / ln * w      # extend along the edge so corners are covered
            quad = [(p[0] - ex, p[1] - ey), (q[0] + ex, q[1] + ey), (q[0] + ex + nx, q[1] + ey + ny), (p[0] - ex + nx, p[1] - ey + ny)]
            z = pcbnew.ZONE(pcb)
            ol = z.Outline()
            ol.NewOutline()
            for x, y in quad:
                v = fr.k(x, y)
                ol.Append(v.x, v.y)
            z.SetLayerSet(ls)
            z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowVias(True)
            z.SetDoNotAllowPads(False)
            z.SetDoNotAllowCopperPour(False)
            z.SetDoNotAllowFootprints(False)
            pcb.Add(z)


def _net_tie_guard(pcb, board):
    """Rule areas over the copper polygons of net-tie footprints (Freerouting does not see them):
    no vias on any layer, no tracks on the polygon's layer.  The tie's own pads are cut out so the
    router can still reach them."""
    paper, pw, ph, ox, oy = page_and_origin(board)
    n = 0
    cu_all = pcbnew.LSET()
    for l in board.copper_layers:
        cu_all.AddLayer(pcb.GetLayerID(l))
    for fp in pcb.GetFootprints():
        shapes = [g for g in fp.GraphicalItems() if g.GetClass() == "PCB_SHAPE" and pcbnew.IsCopperLayer(g.GetLayer())]
        if not shapes:
            continue
        for g in shapes:
            poly = pcbnew.SHAPE_POLY_SET()
            g.TransformShapeToPolygon(poly, g.GetLayer(), 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
            pads = pcbnew.SHAPE_POLY_SET()
            for pad in fp.Pads():
                if pad.IsOnLayer(g.GetLayer()):
                    pad.TransformShapeToPolygon(pads, g.GetLayer(), pcbnew.FromMM(0.05), pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
            poly.BooleanSubtract(pads)
            for k in range(poly.OutlineCount()):
                o = poly.Outline(k)
                if o.PointCount() < 3:
                    continue
                for vias_only in (True, False):
                    z = pcbnew.ZONE(pcb)
                    ol = z.Outline()
                    ol.NewOutline()
                    for m in range(o.PointCount()):
                        p = o.CPoint(m)
                        ol.Append(p.x, p.y)
                    if vias_only:
                        z.SetLayerSet(cu_all)
                    else:
                        ls = pcbnew.LSET()
                        ls.AddLayer(g.GetLayer())
                        z.SetLayerSet(ls)
                    z.SetIsRuleArea(True)
                    z.SetDoNotAllowTracks(not vias_only)
                    z.SetDoNotAllowVias(vias_only)
                    z.SetDoNotAllowPads(False)
                    z.SetDoNotAllowCopperPour(False)
                    z.SetDoNotAllowFootprints(False)
                    pcb.Add(z)
                n += 1
    return n


def zone_nets(board):
    """Nets the autorouter must not route as ordinary tracks (4/6 layers, route(zone_nets="exclude")):
    every net that has a copper zone.  Their pads connect through the zone fill and the plane
    fan-out; whatever stays open is left to the finisher and reported."""
    mode = board.routing.get("zone_nets", "auto")
    if mode == "route" or (mode == "auto" and board.layers < 4):
        return set()
    return {z["net"] for z in board.zones}


def export_dsn(pcb_path, dsn_path, board=None):
    """Export a Specctra DSN.  Zones on outer *signal* layers are left out (their nets are routed
    with real tracks on 2-layer boards; on 4/6 layers zone nets are excluded from autorouting, see
    zone_nets()); inner plane zones are kept.  Rule areas that ban neither tracks nor vias (e.g.
    "no footprints here") are left out - KiCad would export them as full routing keep-outs.

    pcbnew note: nothing may be created after BOARD.Remove() in the same process (the SWIG proxies
    of new objects degrade, e.g. ZONE.Outline() comes back as a bare SwigPyObject), so all new
    rule areas are added first and the removals come last."""
    pcb = pcbnew.LoadBoard(pcb_path)
    drop = []
    for z in list(pcb.Zones()):
        if z.GetIsRuleArea():
            if not (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
                drop.append(z)
            continue
        lids = [l for l in z.GetLayerSet().CuStack()]
        if all(pcb.GetLayerType(l) == pcbnew.LT_SIGNAL for l in lids):
            drop.append(z)
    if board is not None:
        _net_tie_guard(pcb, board)
        _edge_guard(pcb, board)
    for z in drop:
        pcb.Remove(z)
    pcb.BuildConnectivity()
    if os.path.exists(dsn_path):
        os.remove(dsn_path)
    ok = pcbnew.ExportSpecctraDSN(pcb, dsn_path)
    if not ok or not os.path.exists(dsn_path):
        raise RuntimeError("Specctra DSN export failed")
    # Freerouting's clearance model is a few tens of micrometres more optimistic than KiCad's DRC
    # at fine-pitch pads: give it 25 um of extra clearance so its result passes DRC.
    import re
    with open(dsn_path) as f:
        text = f.read()

    def bump(m):
        v = float(m.group(1))
        return "(clearance %s" % (("%.1f" % (v + 25.0)).rstrip("0").rstrip(".") if v >= 100.0 else m.group(1))
    text2 = re.sub(r"\(clearance ([0-9.]+)", bump, text)
    ignored = []
    if board is not None:
        text2, ignored = _split_classes(text2, zone_nets(board))
    if text2 != text:
        with open(dsn_path, "w") as f:
            f.write(text2)
    return ignored


def _sexpr_end(text, i):
    """Index after the parenthesised expression starting at text[i] == '('."""
    depth, q = 0, False
    while i < len(text):
        c = text[i]
        if q:
            if c == '"':
                q = False
        elif c == '"':
            q = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced DSN")


def _split_classes(text, nets):
    """Move *nets* out of their DSN net classes into classes named RR_ZONE_<class> (same rules);
    returns (text, [new class names]) - the caller tells Freerouting to ignore those classes."""
    import re
    if not nets:
        return text, []
    out, pos, made = [], 0, []
    for m in re.finditer(r"\(class ", text):
        if m.start() < pos:
            continue
        end = _sexpr_end(text, m.start())
        block = text[m.start():end]
        k = block.index("(", 1)              # first sub-expression: (circuit ...) / (rule ...)
        head, body = block[:k], block[k:]
        toks = re.findall(r'"[^"]*"|[^\s()]+', head)[1:]   # drop "class"
        name, members = toks[0], toks[1:]
        bare = [t[1:-1] if t.startswith('"') else t for t in members]
        keep = [t for t, b in zip(members, bare) if b not in nets]
        move = [t for t, b in zip(members, bare) if b in nets]
        out.append(text[pos:m.start()])
        if not move:
            out.append(block)
        else:
            cname = "RR_ZONE_" + re.sub(r"[^A-Za-z0-9_]", "_", name.strip('"'))
            made.append(cname)
            if keep:
                out.append("(class %s %s\n      %s\n    " % (name, " ".join(keep), body))
            out.append("(class %s %s\n      %s" % (cname, " ".join(move), body))
        pos = end
    out.append(text[pos:])
    return "".join(out), made


def block_netmap(board, pairs):
    """{source net: destination net} for nets that live entirely inside the source block."""
    src = set(pairs)
    out = {}
    for net, pins in board._nets.items():
        if net in board.rails or not all(ref in src for ref, _ in pins):
            continue
        dst = {board.part(pairs[ref]).pin_net.get(pin) for ref, pin in pins}
        if len(dst) == 1 and None not in dst:
            out[net] = dst.pop()
    return out


def block_signature(board, pairs):
    return ";".join("%s:%.3f,%.3f,%.1f,%s" % (r, board.part(r).x, board.part(r).y, board.part(r).rot, board.part(r).side)
                    for r in sorted(pairs))


def save_block_routes(board, pcb, fr, paths):
    """Store the routed tracks/vias of block-internal nets for Board.replicate(routes=True)."""
    import json
    blocks = []
    for rep in board.replicas:
        if not rep["routes"]:
            continue
        nm = block_netmap(board, rep["pairs"])
        items = []
        # locked copper is the generator's (escape, plane fan-out, earlier block copies) unless it is a
        # pre-route of the definition: only router copper and definition pre-routes are stored - the
        # generator re-creates its own copper for every copy (storing it gave co-located vias)
        user_vias = {(round(v["x"], 3), round(v["y"], 3), v["net"]) for v in board.vias}
        user_segs = set()
        # items replayed from the previous blocks.json are locked too: keep them
        try:
            with open(os.path.join(paths.route_dir, "blocks.json")) as f_:
                for blk in json.load(f_):
                    for it in blk.get("items", []):
                        if it["k"] == "via":
                            user_vias.add((round(it["xy"][0], 3), round(it["xy"][1], 3), it["src"]))
                        else:
                            a_, b_ = (round(it["a"][0], 3), round(it["a"][1], 3)), (round(it["b"][0], 3), round(it["b"][1], 3))
                            user_segs.add((min(a_, b_), max(a_, b_), it["src"]))
        except (OSError, ValueError, KeyError):
            pass
        for tdef in board.tracks:
            for p_, q_ in zip(tdef["pts"][:-1], tdef["pts"][1:]):
                a_, b_ = (round(p_[0], 3), round(p_[1], 3)), (round(q_[0], 3), round(q_[1], 3))
                user_segs.add((min(a_, b_), max(a_, b_), tdef["net"]))
        for t in pcb.GetTracks():
            n = t.GetNetname()
            if n not in nm:
                continue
            if t.IsLocked():
                if t.GetClass() == "PCB_VIA":
                    x_, y_ = fr.user(t.GetPosition())
                    if (round(x_, 3), round(y_, 3), n) not in user_vias:
                        continue
                else:
                    a_, b_ = fr.user(t.GetStart()), fr.user(t.GetEnd())
                    a_, b_ = (round(a_[0], 3), round(a_[1], 3)), (round(b_[0], 3), round(b_[1], 3))
                    if (min(a_, b_), max(a_, b_), n) not in user_segs:
                        continue
            if t.GetClass() == "PCB_VIA":
                x, y = fr.user(t.GetPosition())
                items.append({"k": "via", "src": n, "dst": nm[n], "xy": [x, y],
                              "dia": round(pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)), 4), "drill": round(pcbnew.ToMM(t.GetDrillValue()), 4)})
            else:
                a, e = fr.user(t.GetStart()), fr.user(t.GetEnd())
                items.append({"k": "seg", "src": n, "dst": nm[n], "layer": t.GetLayerName(), "a": list(a), "b": list(e),
                              "w": round(pcbnew.ToMM(t.GetWidth()), 4)})
        items = sorted({json.dumps(i, sort_keys=True): i for i in items}.values(), key=lambda i: json.dumps(i, sort_keys=True))
        blocks.append({"sig": block_signature(board, rep["pairs"]), "first": sorted(rep["pairs"])[0],
                       "dx": rep["dx"], "dy": rep["dy"], "items": items})
    path = os.path.join(paths.route_dir, "blocks.json")
    if blocks:
        with open(path, "w") as f:
            json.dump(blocks, f, indent=0, sort_keys=True)
            f.write("\n")
    elif os.path.exists(path):
        os.remove(path)


def _track_key(t):
    a, b = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
    if b < a:
        a, b = b, a
    return (t.GetClass(), a, b, t.GetLayer(), t.GetNetname())


def import_ses(name, pcb_path, ses, clean="1", min_track="0"):
    """Phase A (own process): import the SES, verify pre-routes, drop dangling stubs, save.
    clean: "1" dangling stubs + unused escape vias (only if fully connected), "d" dangling only, "0" none.

    Runs in a separate interpreter because removing items leaves the pcbnew SWIG
    proxies of that process in an unreliable state."""
    _seed(name, "import")
    pcb = pcbnew.LoadBoard(pcb_path)
    info = {}
    pre = {}
    for t in pcb.GetTracks():
        if t.IsLocked():
            pre[_track_key(t)] = t
    if not pcbnew.ImportSpecctraSES(pcb, ses):
        raise RuntimeError("SES import failed")
    have = {_track_key(t) for t in pcb.GetTracks()}
    missing = [k for k in pre if k not in have]
    info["preroutes"] = len(pre)
    info["preroutes_missing_after_import"] = len(missing)
    if missing:
        raise RuntimeError("%d pre-routed track(s)/via(s) were altered by the autorouter" % len(missing))
    widened = 0
    mt = MM(float(min_track))
    for t in pcb.GetTracks():
        if _track_key(t) in pre:
            t.SetLocked(True)
        elif t.GetClass() != "PCB_VIA" and t.GetWidth() < mt:
            # Freerouting may "neck down" below the fab minimum; restore the minimum width
            # (if that creates a clearance problem, DRC reports it - nothing is hidden)
            t.SetWidth(mt)
            widened += 1
    info["necked_tracks_widened"] = widened
    # finisher items stored for this SES (route/finish.json): add now, removals at the end
    from . import finisher
    ax = pcb.GetDesignSettings().GetAuxOrigin()
    n_fin, fin_gone = finisher.apply(pcb, Frame(pcbnew.ToMM(ax.x), pcbnew.ToMM(ax.y)), os.path.dirname(ses), ses)
    info["finisher_items"] = n_fin
    info["finisher_removed"] = len(fin_gone)
    pcbnew.ZONE_FILLER(pcb).Fill(pcb.Zones())
    pcb.BuildConnectivity()
    info["unconnected_before_cleanup"] = int(pcb.GetConnectivity().GetUnconnectedCount(True))
    # collect everything first, remove last: after BOARD.Remove() the pcbnew SWIG proxies of this
    # process are unreliable (that is what crashed the unused-escape clean-up on RR-CHS-MAIN)
    dang = _dangling_victims(pcb) if clean in ("1", "d") else []
    # unused escape vias are only dropped on a completely connected board: while anything is open
    # they are the finisher's (and the engineer's) best starting points
    esc = _unused_escape_victims(pcb, os.path.join(os.path.dirname(ses), "escape_vias.json"), skip=dang) \
        if clean == "1" and info["unconnected_before_cleanup"] == 0 else []
    info["dangling_tracks_removed"] = len(dang)
    info["unused_escapes_removed"] = sum(1 for it in esc if it.GetClass() == "PCB_VIA")
    fin_keys = {_track_key(t) for t in fin_gone}
    for it in fin_gone + [t for t in dang + esc if _track_key(t) not in fin_keys]:
        pcb.Remove(it)
    pcbnew.SaveBoard(pcb_path, pcb, True)
    return info


def finish_pcb(board, paths, ses=None):
    import json
    import subprocess
    import sys
    paper, pw, ph, ox, oy = page_and_origin(board)
    fr = Frame(ox, oy)
    info = {}
    def load_filled():
        _seed(board.name, "finish")
        pcb = pcbnew.LoadBoard(paths.pcb)
        pcbnew.ZONE_FILLER(pcb).Fill(pcb.Zones())
        pcb.BuildConnectivity()
        return pcb, int(pcb.GetConnectivity().GetUnconnectedCount(True))
    if ses:
        if not os.path.exists(ses):
            raise RuntimeError("SES file not found: %s" % ses)
        import shutil
        unrouted = paths.pcb + ".unrouted"
        shutil.copyfile(paths.pcb, unrouted)
        # the result goes through a file: SWIG prints leak notices on stdout when the process exits
        res_path = paths.pcb + ".import.json"
        code = ("import json,sys; from rrkicad import pcb; "
                "r = pcb.import_ses(*sys.argv[1:6]); open(sys.argv[6], 'w').write(json.dumps(r))")

        def run(clean):
            if os.path.exists(res_path):
                os.remove(res_path)
            r = subprocess.run([sys.executable, "-c", code, board.name, paths.pcb, ses, clean, str(board.rules.min_track),
                                res_path], capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(res_path):
                raise RuntimeError("SES import step failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
            with open(res_path) as f:
                out = json.load(f)
            os.remove(res_path)
            return out
        try:
            info.update(run("1"))
            pcb, after = load_filled()
            if after > info["unconnected_before_cleanup"]:
                # the clean-up removed something that mattered: redo the import without it
                shutil.copyfile(unrouted, paths.pcb)
                info.update(run("0"))
                info["dangling_cleanup"] = "skipped (would have reduced connectivity)"
                pcb, after = load_filled()
        finally:
            os.remove(unrouted)
    else:
        pcb, after = load_filled()
    n_tr = n_via = 0
    length = 0.0
    drills = {}
    for t in pcb.GetTracks():
        if t.GetClass() == "PCB_VIA":
            n_via += 1
            d = round(pcbnew.ToMM(t.GetDrillValue()), 3)
            drills[(d, True)] = drills.get((d, True), 0) + 1
        else:
            n_tr += 1
            length += pcbnew.ToMM(t.GetLength())
    for fp in pcb.GetFootprints():
        for pad in fp.Pads():
            ds = pad.GetDrillSize()
            if ds.x > 0:
                d = round(pcbnew.ToMM(ds.x), 3)
                plated = pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH
                key = (d, plated) if ds.x == ds.y else ("%sx%s" % (d, round(pcbnew.ToMM(ds.y), 3)), plated)
                drills[key] = drills.get(key, 0) + 1
    info.update({"tracks": n_tr, "vias": n_via, "track_length_mm": round(length, 2),
                 "unconnected_after_fill": int(pcb.GetConnectivity().GetUnconnectedCount(True))})
    if ses:
        save_block_routes(board, pcb, fr, paths)
    _fab_notes(board, pcb, fr, drills, n_via)
    pcbnew.SaveBoard(paths.pcb, pcb, True)
    return info


def _unused_escape_victims(pcb, listing, skip=()):
    """Drop escape via + stub pairs the router never used (the via touches nothing but its own
    stub): they are dead-end antennas and give via_dangling warnings.  Only vias listed by the
    escape generator are considered; the caller re-checks connectivity and redoes the import
    without clean-up if anything got worse."""
    import json
    if not os.path.exists(listing):
        return []
    with open(listing) as f:
        want = {(MM(x), MM(y), n) for x, y, n in json.load(f)}
    if not want:
        return []
    skip_keys = {_track_key(t) for t in skip}
    tracks = [t for t in pcb.GetTracks() if t.GetClass() == "PCB_TRACK" and _track_key(t) not in skip_keys]
    ends = {}
    for t in tracks:
        for p in (t.GetStart(), t.GetEnd()):
            ends.setdefault((p.x, p.y), []).append(t)
    tol = MM(0.002)
    victims = []
    for v in [t for t in pcb.GetTracks() if t.GetClass() == "PCB_VIA" and t.IsLocked()]:
        p = v.GetPosition()
        key = None
        for (x, y, n) in want:
            if abs(x - p.x) <= tol and abs(y - p.y) <= tol and n == v.GetNetname():
                key = (x, y, n)
                break
        if key is None:
            continue
        touching = [t for t in tracks if t.GetNetCode() == v.GetNetCode() and
                    (t.HitTest(p, v.GetWidth(pcbnew.F_Cu) // 2) or t.GetStart() == p or t.GetEnd() == p)]
        if len(touching) != 1 or not touching[0].IsLocked():
            continue
        # walk the locked stub back towards the pad while each node joins exactly two stub segments
        chain = [touching[0]]
        node = touching[0].GetStart() if touching[0].GetEnd() == p else touching[0].GetEnd()
        while True:
            nxt = [t for t in ends.get((node.x, node.y), []) if t not in chain]
            if len(nxt) != 1 or not nxt[0].IsLocked() or nxt[0].GetNetCode() != v.GetNetCode():
                break
            chain.append(nxt[0])
            node = nxt[0].GetStart() if nxt[0].GetEnd() == node else nxt[0].GetEnd()
        victims.append(v)
        victims += chain
    return victims


def _dangling_victims(pcb):
    """Autorouter left-overs: unlocked track segments with a free end (unused fan-out stubs).
    Returned, not removed (the caller removes everything at the end and re-checks connectivity)."""
    conn = pcb.GetConnectivity()
    tracks = [t for t in pcb.GetTracks() if t.GetClass() != "PCB_VIA" and not t.IsLocked()]
    # single pass on purpose: the connectivity object cannot be refreshed reliably
    # from Python after removals, and a stale one reports false positives
    return [t for t in tracks if conn.TestTrackEndpointDangling(t, True)]


def pad_positions(pcb_path, board):
    """{(ref, pad): (x, y, side)} in board coordinates, read back from the PCB file."""
    pcb = pcbnew.LoadBoard(pcb_path)
    paper, pw, ph, ox, oy = page_and_origin(board)
    fr = Frame(ox, oy)
    out = {}
    for fp in pcb.GetFootprints():
        side = "B" if fp.IsFlipped() else "F"
        for pad in fp.Pads():
            x, y = fr.user(pad.GetPosition())
            out.setdefault((fp.GetReference(), pad.GetNumber()), []).append((round(x, 3), round(y, 3), side))
    return out


def _text(pcb, s, x, y, layer, size=1.5, just=pcbnew.GR_TEXT_H_ALIGN_LEFT, bold=False):
    t = pcbnew.PCB_TEXT(pcb)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(round(size * (0.2 if bold else 0.13), 3)))
    t.SetHorizJustify(just)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_TOP)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    pcb.Add(t)
    return t


def _dim(pcb, a, b, height):
    d = pcbnew.PCB_DIM_ALIGNED(pcb, pcbnew.PCB_DIM_ALIGNED_T)
    d.SetStart(a)
    d.SetEnd(b)
    d.SetHeight(height)
    d.SetLayer(pcbnew.Dwgs_User)
    d.SetUnitsMode(pcbnew.DIM_UNITS_MODE_MM)
    d.SetPrecision(pcbnew.DIM_PRECISION_X_XX)
    d.SetTextSize(pcbnew.VECTOR2I(MM(1.2), MM(1.2)))
    d.SetTextThickness(MM(0.15))
    d.SetLineThickness(MM(0.12))
    d.SetArrowLength(MM(1.0))
    d.Update()
    pcb.Add(d)


def _fab_notes(board, pcb, fr, drills, n_via):
    """Fabrication drawing content: dimensions on Dwgs.User, notes/tables on Cmts.User."""
    r = board.rules
    x0, y0, x1, y1 = outline_bbox(board)
    # overall dimensions
    _dim(pcb, fr.k(x0, y0), fr.k(x1, y0), MM(6.0))
    _dim(pcb, fr.k(x0, y1), fr.k(x0, y0), MM(6.0))
    # origin marker
    for (ax, ay, bx, by) in ((-1.5, 0, 1.5, 0), (0, -1.5, 0, 1.5)):
        s = pcbnew.PCB_SHAPE(pcb)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(fr.k(ax, ay))
        s.SetEnd(fr.k(bx, by))
        s.SetLayer(pcbnew.Dwgs_User)
        s.SetWidth(MM(0.1))
        pcb.Add(s)
    # hole position dimensions (from the lower-left corner of the outline bbox)
    for i, h in enumerate(board.holes):
        _dim(pcb, fr.k(x0, y1), fr.k(h["x"], y1), MM(-(4.0 + 3.5 * i)))
    _, stack = _stackup(board)
    lines = [
        "%s  %s   rev %s   %s   %s" % (board.name, board.title, board.rev, board.date, board.docnum),
        "",
        "FABRICATION NOTES",
        "1. Material FR-4, Tg >= 150 C, %d copper layers, finished thickness %.2f mm +/-10 %%." % (board.layers, board.thickness),
        "2. Outer copper 35 um (1 oz) finished%s." % ("; inner copper 17.5 um (0.5 oz)" if board.layers > 2 else ""),
        "3. Min track / space %.2f / %.2f mm.  Min finished hole %.2f mm.  Min annular ring %.2f mm." % (
            r.min_track, r.min_clearance, r.min_hole, r.min_annular),
        "4. Surface finish ENIG.  Solder mask both sides, vias tented.  Silkscreen both sides.",
        "5. Board outline per layer Edge.Cuts, tolerance +/-0.1 mm.  Outline %.2f x %.2f mm." % (x1 - x0, y1 - y0),
        "6. Drill / pick-and-place origin = board origin, marked + on this drawing (Y axis up).",
        "7. Electrical test 100 % against the supplied Gerber netlist data.",
    ]
    for i, n in enumerate(board.stackup_notes):
        lines.append("%d. %s" % (8 + i, n))
    lines += ["", "STACKUP (top to bottom, mm)"] + ["   " + s for s in stack]
    lines += ["", "HOLE TABLE (finished sizes, mm)", "   dia      type   qty   use"]
    hole_refs = {}
    for h in board.holes:
        hole_refs.setdefault((round(h["drill"], 3), bool(h["plated"])), []).append(
            "%s (%.2f, %.2f)" % (h["ref"], h["x"], h["y"]))
    for key in sorted(drills, key=lambda k: (str(k[0]), k[1])):
        d, plated = key
        use = []
        if key in hole_refs:
            use.append("mounting: " + ", ".join(hole_refs[key]))
        lines.append("   %-8s %-6s %-5d %s" % (d, "PTH" if plated else "NPTH", drills[key], "; ".join(use)))
    lines.append("   (%d of the plated holes are vias)" % n_via)
    tx = fr.ox + x1 + 16.0
    ty = fr.oy - y1 - 2.0
    _text(pcb, "\n".join(lines), tx, ty, pcbnew.Cmts_User, 1.3)
