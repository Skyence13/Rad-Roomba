"""KiCad 9 schematic generation (S-expressions written directly).

Layout model: one hierarchical sheet per functional group (overflowing onto
extra sheets when needed).  Every symbol unit becomes a "cell" holding the body,
a short wire stub per used pin ending in a global label (or a power symbol for
declared rails), no-connect flags, and the Reference/Value fields.  Cells are
packed on a regular grid; cell sizes are computed from label lengths so labels
never overlap neighbouring cells.
"""
import math
import os

from .sexpr import Q, dump, find
from .model import DefinitionError
from . import locallib

SCH_VERSION = "20250114"
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}
G = 2.54            # placement grid
STUB = 2.54         # pin stub length
CHAR_W = 1.1        # conservative advance per character at 1.27 mm text
FONT = 1.27
MARGIN = 15.0       # drawing area margin from the page edge
TB_W, TB_H = 120.0, 45.0   # reserved title-block area (bottom right)


def _rot(x, y, r):
    r %= 360
    if r == 0:
        return (x, y)
    if r == 90:
        return (-y, x)
    if r == 180:
        return (-x, -y)
    if r == 270:
        return (y, -x)
    raise DefinitionError("schematic rotation must be 0/90/180/270")


def _pos(x, y, r):
    """Symbol (y-up) point -> sheet offset (y-down) for instance rotation r."""
    rx, ry = _rot(x, y, r)
    return (rx, -ry)


def _snap(v, g=G):
    return round(round(v / g) * g, 4)


def _ceil(v, g=G):
    return round(math.ceil(v / g - 1e-9) * g, 4)


def _font(size=FONT, justify=None, hide=False, bold=False):
    f = ["font", ["size", size, size]]
    if bold:
        f += [["thickness", round(size * 0.2, 3)], ["bold", "yes"]]
    e = ["effects", f]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def _field_angle(horizontal, rot):
    """Stored field angle so the text is displayed horizontal/vertical for a symbol rotation."""
    sym_swaps = (rot % 180) == 90
    return 0 if (horizontal != sym_swaps) else 90


LABEL_ROT = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}
LABEL_JUST = {0: "left", 180: "right", 90: "left", 270: "right"}


class Rail:
    """How a power rail is drawn."""

    def __init__(self, net, sym):
        self.net, self.sym = net, sym
        bb = sym.body_bbox(1)
        # natural pointing direction on the sheet: (0,-1) = up, (0,1) = down
        self.natural = (0, -1) if (bb[1] + bb[3]) / 2.0 > 0 else (0, 1)

    def rotation(self, d):
        """Instance rotation so the graphic points along sheet direction d."""
        order_up = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}
        order_dn = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}
        return (order_up if self.natural == (0, -1) else order_dn)[d]


class Cell:
    def __init__(self, part, unit):
        self.part, self.unit = part, unit
        self.items = []      # drawing records, coordinates relative to the symbol origin
        self.boxes = []      # occupied rectangles (x0, y0, x1, y1)
        self.fields = {}     # name -> (x, y, angle, justify)
        self.x = self.y = 0.0  # symbol origin on the sheet (set by the packer)

    def bbox(self):
        return (min(b[0] for b in self.boxes), min(b[1] for b in self.boxes),
                max(b[2] for b in self.boxes), max(b[3] for b in self.boxes))


def _hits(box, boxes, m=0.3):
    for b in boxes:
        if box[0] - m < b[2] and box[2] + m > b[0] and box[1] - m < b[3] and box[3] + m > b[1]:
            return True
    return False


def build_cell(part, unit, rails):
    sym, rot = part.sym, part.sch_rot
    cell = Cell(part, unit)
    bb = sym.body_bbox(unit)
    cs = [_pos(x, y, rot) for x in (bb[0], bb[2]) for y in (bb[1], bb[3])]
    body = (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))
    occupied = []
    # one stub per distinct pin location
    groups = {}
    for pin in sym.unit_pins(unit):
        key = (round(pin.x, 3), round(pin.y, 3))
        groups.setdefault(key, []).append(pin)
    stubs = []
    for key in sorted(groups):
        plist = groups[key]
        net = part.pin_net.get(plist[0].number)
        vis = [p for p in plist if not p.hidden] or plist
        pin = vis[0]
        px, py = _pos(pin.x, pin.y, rot)
        ox, oy = _rot(pin.outward[0], pin.outward[1], rot)
        d = (ox, -oy)
        if net is None:
            if all(p.etype == "no_connect" and p.hidden for p in plist):
                continue
            cell.items.append(("nc", px, py, plist))
            occupied.append((px - 0.7, py - 0.7, px + 0.7, py + 0.7))
            continue
        ex, ey = px + d[0] * STUB, py + d[1] * STUB
        stubs.append({"net": net, "p": (px, py), "e": (ex, ey), "d": d, "pins": plist})
    for s in stubs:
        net, (px, py), (ex, ey), d = s["net"], s["p"], s["e"], s["d"]
        cell.items.append(("wire", px, py, ex, ey, s["pins"]))
        if net in rails:
            tl = len(net) * CHAR_W
            vertical_text = False
            if d[0] == 0:
                for o in stubs:
                    if o is not s and o["d"] == d and abs(o["e"][0] - ex) < tl / 2.0 + 1.6:
                        vertical_text = True
                if vertical_text:
                    box = (ex - 1.4, min(ey, ey + d[1] * (3.4 + tl)), ex + 1.4, max(ey, ey + d[1] * (3.4 + tl)))
                    fpos = (ex, ey + d[1] * (3.4 + tl / 2.0), False)
                else:
                    hw = max(1.4, tl / 2.0)
                    box = (ex - hw, min(ey, ey + d[1] * 5.0), ex + hw, max(ey, ey + d[1] * 5.0))
                    fpos = (ex, ey + d[1] * 3.9, True)
            else:
                box = (min(ex, ex + d[0] * (3.4 + tl)), ey - 1.2, max(ex, ex + d[0] * (3.4 + tl)), ey + 1.2)
                fpos = (ex + d[0] * (3.4 + tl / 2.0), ey, True)
            cell.items.append(("power", net, ex, ey, d, fpos, s["pins"]))
        else:
            lt = len(net) * CHAR_W + 3.0
            if d[0] == 0:
                box = (ex - 1.1, min(ey, ey + d[1] * lt), ex + 1.1, max(ey, ey + d[1] * lt))
            else:
                box = (min(ex, ex + d[0] * lt), ey - 1.1, max(ex, ex + d[0] * lt), ey + 1.1)
            cell.items.append(("glabel", net, ex, ey, d, s["pins"]))
        occupied.append((min(px, ex) - 0.1, min(py, ey) - 0.1, max(px, ex) + 0.1, max(py, ey) + 0.1))
        occupied.append(box)
    # Reference / Value placement: first candidate block that collides with nothing
    ref = part.ref
    val = part.value
    tw = max(len(ref) + (1 if len(sym.units) > 1 else 0), len(val)) * CHAR_W
    pitch = 2.0
    cx, cy = (body[0] + body[2]) / 2.0, (body[1] + body[3]) / 2.0
    cands = [
        ("left", body[2] + 1.0, cy - pitch / 2.0),                     # right of body
        ("left", body[0], body[1] - 1.2 - pitch),                      # above, left aligned
        ("left", body[0], body[3] + 1.2),                              # below, left aligned
        ("right", body[0] - 1.0, cy - pitch / 2.0),                    # left of body
    ]
    allb = occupied + [body]
    top = min(b[1] for b in allb)
    cands.append(("left", body[0], top - 1.5 - pitch))                 # above everything
    chosen = None
    for just, x0, y0 in cands:
        bx = (x0, y0 - 0.8, x0 + tw, y0 + pitch + 0.8) if just == "left" else (x0 - tw, y0 - 0.8, x0, y0 + pitch + 0.8)
        if not _hits(bx, occupied + [body], 0.2) or (just, x0, y0) == cands[-1]:
            chosen = (just, x0, y0, bx)
            break
    just, x0, y0, bx = chosen
    ang = _field_angle(True, rot)
    if rot == 0:
        cell.fields["Reference"] = (x0, y0, 0, just)
        cell.fields["Value"] = (x0, y0 + pitch, 0, just)
    else:  # centred text is immune to KiCad's justification flipping on rotated symbols
        xc = (bx[0] + bx[2]) / 2.0
        cell.fields["Reference"] = (xc, y0, ang, None)
        cell.fields["Value"] = (xc, y0 + pitch, ang, None)
    cell.boxes = occupied + [body, bx]
    return cell


class SheetPage:
    def __init__(self, group, index, name):
        self.group, self.index, self.name = group, index, name
        self.file = name + ".kicad_sch"
        self.cells = []
        self.uuid = None
        self.page_no = 0


def paginate(board, cells_by_group):
    """Pack cells into pages.  Returns list of SheetPage."""
    pw, ph = PAPER[board.paper]
    pages = []
    for group in board.groups:
        cells = cells_by_group[group.name]
        note_lines = (group.notes.count("\n") + 1) if group.notes else 0
        top0 = MARGIN + 12.0 + note_lines * 2.6 + (4.0 if note_lines else 0.0)
        left, right, bottom = MARGIN + 5.0, pw - MARGIN, ph - MARGIN
        tb_x, tb_y = pw - 10.0 - TB_W, ph - 10.0 - TB_H
        idx = 0
        page = None

        def new_page():
            nonlocal page, idx
            idx += 1
            page = SheetPage(group, idx, group.name if idx == 1 else "%s_%d" % (group.name, idx))
            pages.append(page)
            return {"x": left, "y": _ceil(top0), "row_h": 0.0, "col_w": 0.0, "col_y": _ceil(top0)}
        st = new_page()
        min_row = 55.88
        for cell in cells:
            b = cell.bbox()
            pad = G
            w = _ceil(b[2] - b[0] + 2 * pad)
            h = _ceil(b[3] - b[1] + 2 * pad)
            if w > right - left or h > bottom - _ceil(top0):
                raise DefinitionError("%s: symbol too large for paper %s; use a bigger paper" % (cell.part.ref, board.paper))
            while True:
                row_h = max(st["row_h"], min_row)
                # stack in the current column?
                if st["col_w"] and st["col_y"] + h <= st["y"] + row_h and st["x"] + max(w, st["col_w"]) <= right:
                    x, y = st["x"], st["col_y"]
                    if not (x + w > tb_x and y + h > tb_y):
                        st["col_w"] = max(st["col_w"], w)
                        st["col_y"] = y + h
                        break
                # next column in this row
                nx = st["x"] + st["col_w"]
                if nx + w <= right and st["y"] + h <= bottom and not (nx + w > tb_x and st["y"] + h > tb_y):
                    st["x"], st["col_w"], st["col_y"] = nx, w, st["y"] + h
                    st["row_h"] = max(st["row_h"], h)
                    x, y = nx, st["y"]
                    break
                # next row
                ny = st["y"] + max(st["row_h"], min_row if st["col_w"] else 0.0)
                if st["col_w"] and ny + h <= bottom:
                    st.update({"x": left, "y": _ceil(ny), "row_h": 0.0, "col_w": 0.0, "col_y": _ceil(ny)})
                    if not (left + w > tb_x and st["y"] + h > tb_y):
                        continue
                st = new_page()
            cell.x = _snap(_ceil(x) + _ceil(-b[0] + pad))
            cell.y = _snap(_ceil(y) + _ceil(-b[1] + pad))
            page.cells.append(cell)
    for i, p in enumerate(pages):
        p.page_no = i + 2
        p.uuid = board.uuid("sheet", p.name)
    return pages


class SchematicWriter:
    def __init__(self, board, libs, nets):
        self.board, self.libs, self.nets = board, libs, nets
        self.root_uuid = board.uuid("root-sheet")
        self.rails = {}
        self.pwr_no = 0
        self.flg_no = 0
        self.flag_nets = []
        self.local_syms = {}

    # ------------------------------------------------------------ preparation
    def prepare_libs(self):
        """Create local symbols (user-defined + generated power symbols)."""
        b = self.board
        for name, spec in b.local_symbols.items():
            self.local_syms[name] = locallib.make_symbol(name, spec)
        if self.local_syms:
            self.libs.add_local(locallib.NICK, locallib.library_text(list(self.local_syms.values())))
        for net, r in b.rails.items():
            if r["symbol"]:
                continue
            if self.libs.has("power:" + net):
                r["symbol"] = "power:" + net
            else:
                tpl = self.libs.get("power:GND" if r["style"] == "gnd" else "power:VCC")
                self.local_syms[net] = locallib.make_power_symbol(net, tpl.sx, tpl.name)
                r["symbol"] = "%s:%s" % (locallib.NICK, net)
        if self.local_syms:
            self.libs.add_local(locallib.NICK, locallib.library_text(list(self.local_syms.values())))

    def local_library_text(self):
        return locallib.library_text(list(self.local_syms.values())) if self.local_syms else None

    # ---------------------------------------------------------------- helpers
    def _tb(self, title, page):
        b = self.board
        return ["title_block", ["title", Q(title)], ["date", Q(b.date)], ["rev", Q(b.rev)],
                ["company", Q(b.company)],
                ["comment", 1, Q("Doc No: %s" % b.docnum)],
                ["comment", 2, Q("Board: %s - %s" % (b.name, b.title))],
                ["comment", 3, Q("Generated by rrkicad from board.py - edit the definition, not this file")]]

    def _text(self, key, text, x, y, size=FONT, bold=False, justify="left bottom"):
        return ["text", Q(text), ["exclude_from_sim", "no"], ["at", x, y, 0],
                _font(size, justify, bold=bold), ["uuid", Q(self.board.uuid("text", key))]]

    def _wire(self, key, x1, y1, x2, y2):
        return ["wire", ["pts", ["xy", x1, y1], ["xy", x2, y2]], ["stroke", ["width", 0], ["type", "default"]],
                ["uuid", Q(self.board.uuid("wire", key))]]

    def _glabel(self, key, net, x, y, d):
        rot = LABEL_ROT[d]
        return ["global_label", Q(net), ["shape", "passive"], ["at", x, y, rot],
                _font(justify=LABEL_JUST[rot]), ["uuid", Q(self.board.uuid("glabel", key))],
                ["property", Q("Intersheetrefs"), Q("${INTERSHEET_REFS}"), ["at", x, y, 0],
                 _font(justify=LABEL_JUST[rot], hide=True)]]

    def _props(self, sym, values, fields, x, y, hidden_extra):
        """Property list for a symbol instance."""
        out = []
        for name in ("Reference", "Value"):
            fx, fy, ang, just = fields[name]
            hide = fields.get("_hide_" + name, False)
            out.append(["property", Q(name), Q(values[name]), ["at", fx, fy, ang], _font(justify=just, hide=hide)])
        for name in ("Footprint", "Datasheet", "Description"):
            out.append(["property", Q(name), Q(values.get(name, "")), ["at", x, y, 0], _font(hide=True)])
        for name, v in hidden_extra:
            out.append(["property", Q(name), Q(v), ["at", x, y, 0], _font(hide=True)])
        return out

    def _instance(self, lib_id, x, y, rot, unit, uuid, props, pins, path, ref, in_bom=True, on_board=True, dnp=False):
        s = ["symbol", ["lib_id", Q(lib_id)], ["at", x, y, rot], ["unit", unit],
             ["exclude_from_sim", "no"], ["in_bom", "yes" if in_bom else "no"],
             ["on_board", "yes" if on_board else "no"], ["dnp", "yes" if dnp else "no"],
             ["uuid", Q(uuid)]]
        s += props
        for pn in pins:
            s.append(["pin", Q(pn), ["uuid", Q(self.board.uuid("pin", uuid, pn))]])
        s.append(["instances", ["project", Q(self.board.name),
                                ["path", Q(path), ["reference", Q(ref)], ["unit", unit]]]])
        return s

    def _power(self, key, net, x, y, d, fpos, path, used):
        rail = self.rails[net]
        sym = rail.sym
        used[sym.lib_id] = sym
        rot = rail.rotation(d)
        self.pwr_no += 1
        ref = "#PWR%04d" % self.pwr_no
        fx, fy, horiz = fpos
        fields = {"Reference": (x, y, 0, None), "_hide_Reference": True,
                  "Value": (fx, fy, _field_angle(horiz, rot), None)}
        values = {"Reference": ref, "Value": net, "Description": sym.prop("Description")}
        uuid = self.board.uuid("power", key)
        return self._instance(sym.lib_id, x, y, rot, 1, uuid, self._props(sym, values, fields, x, y, []),
                              [p.number for p in sym.unit_pins(1)], path, ref, in_bom=True)

    # ------------------------------------------------------------------ sheets
    def build(self, out_dir):
        b = self.board
        self.prepare_libs()
        for net, r in b.rails.items():
            self.rails[net] = Rail(net, self.libs.get(r["symbol"]))
        cells_by_group = {}
        for g in b.groups:
            cells = []
            for part in g.parts:
                for unit in part.sym.units:
                    cells.append(build_cell(part, unit, self.rails))
            cells_by_group[g.name] = cells
        pages = paginate(b, cells_by_group)
        self.pages = pages
        self._power_flags()
        files = {}
        for page in pages:
            files[page.file] = self._sheet(page)
        files[b.name + ".kicad_sch"] = self._root(pages)
        for name, text in files.items():
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
                f.write(text)
        return pages

    def _power_flags(self):
        """Nets with power-input pins (incl. power symbols) but no power-output pin need a PWR_FLAG."""
        b = self.board
        flags = []
        for net, pins in self.nets.items():
            types = set()
            for ref, num in pins:
                part = b.part(ref)
                for p in part.sym.pins:
                    if p.number == num:
                        types.add(p.etype)
            if net in b.rails:
                types.add("power_in")
            if "power_in" in types and "power_out" not in types:
                flags.append(net)
        self.flag_nets = flags

    def _sheet(self, page):
        b = self.board
        g = page.group
        pw, ph = PAPER[b.paper]
        path = "/%s/%s" % (self.root_uuid, page.uuid)
        used = {}
        body = []
        ncs, wires, labels, syms = [], [], [], []
        n_pages = len([p for p in self.pages if p.group is g])
        title = g.title + ("" if n_pages == 1 else " (%d/%d)" % (page.index, n_pages))
        texts = [self._text((page.name, "title"), title, MARGIN + 5.0, MARGIN + 8.0, 3.0, bold=True)]
        if g.notes and page.index == 1:
            texts.append(self._text((page.name, "notes"), g.notes, MARGIN + 5.0, MARGIN + 11.0, 1.5, justify="left top"))
        for cell in page.cells:
            part, sym, unit = cell.part, cell.part.sym, cell.unit
            X, Y = cell.x, cell.y
            ck = (part.ref, unit)
            used[sym.lib_id] = sym
            for it in cell.items:
                kind = it[0]
                if kind == "nc":
                    ncs.append(["no_connect", ["at", X + it[1], Y + it[2]],
                                ["uuid", Q(b.uuid("nc", ck, it[3][0].number))]])
                elif kind == "wire":
                    wires.append(self._wire((ck, it[5][0].number), X + it[1], Y + it[2], X + it[3], Y + it[4]))
                elif kind == "glabel":
                    labels.append(self._glabel((ck, it[5][0].number), it[1], X + it[2], Y + it[3], it[4]))
                elif kind == "power":
                    fx, fy, hz = it[5]
                    syms.append(self._power((ck, it[6][0].number), it[1], X + it[2], Y + it[3], it[4],
                                            (X + fx, Y + fy, hz), path, used))
            fields = {k: ((X + v[0], Y + v[1], v[2], v[3]) if not k.startswith("_") else v)
                      for k, v in cell.fields.items()}
            values = {"Reference": part.ref, "Value": part.value, "Footprint": part.footprint or "",
                      "Datasheet": part.datasheet if part.datasheet is not None else sym.prop("Datasheet"),
                      "Description": part.description if part.description is not None else sym.prop("Description")}
            extra = [("MPN", part.mpn), ("Manufacturer", part.mfr)]
            if part.notes:
                extra.append(("Notes", part.notes))
            if part.verify:
                extra.append(("Verify", "MPN/part data not verified against manufacturer data"))
            for k in sorted(part.fields):
                extra.append((k, str(part.fields[k])))
            uuid = b.uuid("symbol", part.ref, unit)
            syms.append(self._instance(sym.lib_id, X, Y, part.sch_rot, unit, uuid,
                                       self._props(sym, values, fields, X, Y, extra),
                                       [p.number for p in sym.unit_pins(unit)], path, part.ref,
                                       in_bom=part.bom, dnp=part.dnp))
        tree = ["kicad_sch", ["version", SCH_VERSION], ["generator", Q("rrkicad")], ["generator_version", Q("9.0")],
                ["uuid", Q(page.uuid)], ["paper", Q(b.paper)],
                self._tb(title, page.page_no),
                ["lib_symbols"] + [used[k].embedded() for k in sorted(used)]]
        tree += ncs + wires + texts + labels + syms
        tree.append(["embedded_fonts", "no"])
        return dump(tree)

    def _root(self, pages):
        b = self.board
        path = "/%s" % self.root_uuid
        used = {}
        items = []
        pw, ph = PAPER[b.paper]
        x0 = MARGIN + 5.0
        items.append(self._text("root-title", "%s  -  %s" % (b.name, b.title), x0, MARGIN + 10.0, 5.0, bold=True))
        info = ["Revision %s    Date %s    Doc No %s" % (b.rev, b.date, b.docnum)]
        if b.description:
            info += [""] + b.description.strip().split("\n")
        info += ["", "Layers: %d    Thickness: %.2f mm" % (b.layers, b.thickness),
                 "Rails: " + (", ".join(sorted(b.rails)) or "-")]
        for nc in b.netclasses:
            info.append("Net class %s: track %.2f mm, clearance %.2f mm, via %.2f/%.2f mm  [%s]" % (
                nc["name"], nc["track"], nc["clearance"], nc["via_dia"], nc["via_drill"], ", ".join(nc["nets"])))
        info += ["", "This schematic is generated from board.py by tools/eda (rrkicad).",
                 "All nets are connected by name (global labels / power symbols); there are no drawn wires between symbols."]
        items.append(self._text("root-info", "\n".join(info), x0, MARGIN + 14.0, 1.8, justify="left top"))
        # sheet symbols
        sy0 = _ceil(MARGIN + 14.0 + len(info) * 3.1 + 12.0)
        longest = max([len(p.group.title) + 8 for p in pages] + [20])
        sw, sh = _ceil(max(60.96, longest * 1.75 + 6.0)), 15.24
        per_row = max(1, int((pw - 2 * MARGIN - 10.0) // (sw + 12.7)))
        sheets = []
        items.append(self._text("root-sheets", "Sheets", x0, sy0 - 6.0, 2.5, bold=True))
        for i, p in enumerate(pages):
            sx = _ceil(x0) + (i % per_row) * (sw + 12.7)
            sy = sy0 + (i // per_row) * (sh + 12.7)
            n_pages = len([q for q in pages if q.group is p.group])
            label = p.group.title + ("" if n_pages == 1 else " (%d/%d)" % (p.index, n_pages))
            sheets.append(["sheet", ["at", sx, sy], ["size", sw, sh],
                           ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
                           ["fields_autoplaced", "yes"],
                           ["stroke", ["width", 0.1524], ["type", "solid"]],
                           ["fill", ["color", 0, 0, 0, "0.0000"]],
                           ["uuid", Q(p.uuid)],
                           ["property", Q("Sheetname"), Q(p.name), ["at", sx, sy - 0.7, 0], _font(justify="left bottom")],
                           ["property", Q("Sheetfile"), Q(p.file), ["at", sx, sy + sh + 0.6, 0], _font(justify="left top")],
                           ["instances", ["project", Q(b.name), ["path", Q(path), ["page", Q(str(p.page_no))]]]]])
            items.append(self._text(("root-sheet-title", p.name), label, sx + 2.0, sy + sh / 2.0 + 1.0, 1.8))
        last_row = (max(len(pages) - 1, 0)) // per_row
        fy = _ceil(sy0 + (last_row + 1) * (sh + 12.7) + 20.0)
        syms, wires, labels = [], [], []
        if self.flag_nets:
            flg = self.libs.get("power:PWR_FLAG")
            used[flg.lib_id] = flg
            items.append(self._text("root-flags", "Power flags (ERC: these nets are fed from outside this sheet set / via passives)",
                                    x0, fy - 9.0, 2.5, bold=True))
            fx = _ceil(x0) + G * 2
            pitch = 33.02
            per = max(1, int((pw - 2 * MARGIN - 10.0) // pitch))
            for i, net in enumerate(self.flag_nets):
                x = fx + (i % per) * pitch
                y = fy + (i // per) * 25.4
                self.flg_no += 1
                ref = "#FLG%03d" % self.flg_no
                fields = {"Reference": (x, y, 0, None), "_hide_Reference": True, "Value": (x, y - 4.6, 0, None)}
                values = {"Reference": ref, "Value": "PWR_FLAG", "Description": flg.prop("Description")}
                syms.append(self._instance(flg.lib_id, x, y, 0, 1, b.uuid("flag", net),
                                           self._props(flg, values, fields, x, y, []),
                                           [p.number for p in flg.unit_pins(1)], path, ref))
                x2 = x + 12.7
                wires.append(self._wire(("flag", net), x, y, x2, y))
                if net in self.rails:
                    d = self.rails[net].natural
                    syms.append(self._power(("flag", net), net, x2, y, d, (x2, y + d[1] * 3.9, True), path, used))
                    # a local label keeps ERC from reporting the flag as "not connected"
                    # (a PWR_FLAG wired to nothing but a power symbol counts as unconnected)
                    labels.append(["label", Q(net), ["at", x + 2.54, y, 0], _font(justify="left bottom"),
                                   ["uuid", Q(b.uuid("flaglabel", net))]])
                else:
                    labels.append(self._glabel(("flag", net), net, x2, y, (1, 0)))
        tree = ["kicad_sch", ["version", SCH_VERSION], ["generator", Q("rrkicad")], ["generator_version", Q("9.0")],
                ["uuid", Q(self.root_uuid)], ["paper", Q(b.paper)],
                self._tb("%s (root)" % b.name, 1),
                ["lib_symbols"] + [used[k].embedded() for k in sorted(used)]]
        tree += wires + items + labels + syms + sheets
        tree.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
        tree.append(["embedded_fonts", "no"])
        return dump(tree)
