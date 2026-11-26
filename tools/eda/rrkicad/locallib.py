"""Project-local symbol / footprint libraries generated from the board definition.

Library nickname is always ``rr_local``:
  <board dir>/rr_local.kicad_sym      symbols (user-defined + generated power symbols)
  <board dir>/rr_local.pretty/*.kicad_mod   footprints (user-defined + mounting holes)
"""
import copy
import math
import os

from .sexpr import Q, dump, find, find_all
from .model import stable_uuid, DefinitionError

NICK = "rr_local"
SYM_VERSION = "20241209"
FP_VERSION = "20241229"


def _font(size=1.27, hide=False, justify=None):
    e = ["effects", ["font", ["size", size, size]]]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def _prop(name, value, x, y, rot=0, hide=False, justify=None):
    return ["property", Q(name), Q(value), ["at", x, y, rot], _font(hide=hide, justify=justify)]


def make_symbol(name, spec):
    """Box symbol from a SymPin list."""
    pins = spec["pins"]
    units = sorted({p.unit for p in pins}) or [1]     # pin-less symbols (mechanical parts) are allowed
    sx = ["symbol", Q(name),
          ["pin_names", ["offset", 1.016]],
          ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"]]
    subs = []
    ref_at = None
    for u in units:
        ups = [p for p in pins if p.unit == u]
        side = {s: [p for p in ups if p.side.upper().startswith(s)] for s in "LRTB"}
        if sum(len(v) for v in side.values()) != len(ups):
            raise DefinitionError("local symbol %s: pin side must be L/R/T/B" % name)
        nv = max(len(side["L"]), len(side["R"]), 1)
        nh = max(len(side["T"]), len(side["B"]), 0)
        half_h = math.ceil((nv + 1) / 2.0) * 2.54
        lname = max([len(p.name) for p in side["L"]] + [0])
        rname = max([len(p.name) for p in side["R"]] + [0])
        need_w = max((lname + rname) * 1.0 + 5.0, nh * 2.54 + 5.08, 10.16)
        half_w = math.ceil(need_w / 2.0 / 2.54) * 2.54
        if (side["T"] or side["B"]):
            tn = max([len(p.name) for p in side["T"] + side["B"]] + [0])
            half_h = max(half_h, math.ceil((nv * 2.54 / 2.0 + tn * 1.0 + 1.5) / 2.54) * 2.54)
        body = ["symbol", Q("%s_%d_1" % (name, u)),
                ["rectangle", ["start", -half_w, half_h], ["end", half_w, -half_h],
                 ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]]

        def pin(p, x, y, ang):
            return ["pin", p.etype, "line", ["at", x, y, ang], ["length", 2.54],
                    ["name", Q(p.name), _font()], ["number", Q(p.number), _font()]]
        for i, p in enumerate(side["L"]):
            body.append(pin(p, -half_w - 2.54, half_h - 2.54 * (i + 1), 0))
        for i, p in enumerate(side["R"]):
            body.append(pin(p, half_w + 2.54, half_h - 2.54 * (i + 1), 180))
        for sd, yy, ang in (("T", half_h + 2.54, 270), ("B", -half_h - 2.54, 90)):
            n = len(side[sd])
            x0 = -math.floor((n - 1) / 2.0) * 2.54
            for i, p in enumerate(side[sd]):
                body.append(pin(p, x0 + i * 2.54, yy, ang))
        subs.append(body)
        if ref_at is None:
            ref_at = (-half_w, half_h + 1.27, -half_h - 1.27)
    sx += [
        _prop("Reference", spec.get("ref_prefix", "U"), ref_at[0], ref_at[1], justify="left bottom"),
        _prop("Value", name, ref_at[0], ref_at[2], justify="left top"),
        _prop("Footprint", spec.get("footprint", ""), 0, 0, hide=True),
        _prop("Datasheet", spec.get("datasheet", ""), 0, 0, hide=True),
        _prop("Description", spec.get("description", ""), 0, 0, hide=True),
    ]
    sx += subs
    sx.append(["embedded_fonts", "no"])
    return sx


def make_power_symbol(name, template_sx, template_name):
    """Clone a stock power symbol (GND / VCC graphics) under a new rail name."""
    sx = copy.deepcopy(template_sx)
    sx[1] = Q(name)
    for item in sx:
        if not isinstance(item, list) or not item:
            continue
        if item[0] == "property":
            if item[1] == "Value":
                item[2] = Q(name)
            elif item[1] == "Description":
                item[2] = Q('Power symbol creates a global label with name "%s"' % name)
        elif item[0] == "symbol":
            s = str(item[1])
            item[1] = Q(name + s[len(template_name):])
            for p in find_all(item, "pin"):
                nm = find(p, "name")
                if nm is not None:
                    nm[1] = Q(name)
    return sx


def library_text(symbols):
    """symbols: list of flattened symbol s-expressions (unprefixed names)."""
    tree = ["kicad_symbol_lib", ["version", SYM_VERSION], ["generator", Q("rrkicad")],
            ["generator_version", Q("9.0")]]
    tree += sorted(symbols, key=lambda s: str(s[1]))
    return dump(tree)


# ------------------------------------------------------------------ footprints
def _stroke(w):
    return ["stroke", ["width", w], ["type", "solid"]]


def _fp_header(name, descr, attrs):
    u = lambda *k: Q(stable_uuid("fp", name, *k))
    return ["footprint", Q(name),
            ["version", FP_VERSION], ["generator", Q("rrkicad")], ["generator_version", Q("9.0")],
            ["layer", Q("F.Cu")], ["descr", Q(descr)],
            ], u


def _text_prop(name, value, x, y, layer, u, size=0.8, hide=False):
    p = ["property", Q(name), Q(value), ["at", x, y, 0], ["layer", Q(layer)]]
    if hide:
        p.append(["hide", "yes"])
    p += [["uuid", u("prop", name)],
          ["effects", ["font", ["size", size, size], ["thickness", round(size * 0.15, 3)]]]]
    return p


def make_hole_footprint(drill, plated=False, pad=None):
    """Mounting hole without courtyard (the keep-out rule area plays that role)."""
    if plated:
        name = "MountingHole_%smm_Pad_%smm" % (_n(drill), _n(pad))
    else:
        name = "MountingHole_%smm_NPTH" % _n(drill)
    fp, u = _fp_header(name, "Mounting hole %s mm%s (generated by rrkicad)" % (
        _n(drill), (", plated, pad %s mm" % _n(pad)) if plated else ", NPTH"), None)
    r = (pad if plated else drill) / 2.0 + 0.15
    fp += [
        _text_prop("Reference", "REF**", 0, -r - 0.8, "F.Fab", u, 0.6),
        _text_prop("Value", name, 0, r + 0.8, "F.Fab", u, 0.5, hide=True),
        _text_prop("Datasheet", "", 0, 0, "F.Fab", u, hide=True),
        _text_prop("Description", "", 0, 0, "F.Fab", u, hide=True),
        ["attr", "board_only", "exclude_from_pos_files", "exclude_from_bom", "allow_missing_courtyard"],
        ["fp_circle", ["center", 0, 0], ["end", r, 0], _stroke(0.1), ["fill", "no"], ["layer", Q("F.Fab")], ["uuid", u("fab")]],
        ["fp_circle", ["center", 0, 0], ["end", r, 0], _stroke(0.1), ["fill", "no"], ["layer", Q("B.Fab")], ["uuid", u("bfab")]],
    ]
    if plated:
        fp.append(["pad", Q("1"), "thru_hole", "circle", ["at", 0, 0], ["size", pad, pad], ["drill", drill],
                   ["layers", Q("*.Cu"), Q("*.Mask")], ["remove_unused_layers", "no"], ["uuid", u("pad")]])
    else:
        fp.append(["pad", Q(""), "np_thru_hole", "circle", ["at", 0, 0], ["size", drill, drill], ["drill", drill],
                   ["layers", Q("*.Cu"), Q("*.Mask")], ["uuid", u("pad")]])
    fp.append(["embedded_fonts", "no"])
    return name, dump(fp)


def _n(v):
    s = ("%.3f" % v).rstrip("0").rstrip(".")
    return s


def make_footprint(name, spec):
    pads = spec["pads"]
    if not pads:
        raise DefinitionError("local footprint %s has no pads" % name)
    kind = spec.get("kind") or ("through_hole" if any(p.kind == "thru" for p in pads) else "smd")
    fp, u = _fp_header(name, spec.get("description") or (name + " (generated by rrkicad)"), None)
    ext = []
    for p in pads:
        w, h = (p.h, p.w) if (p.rot % 180) else (p.w, p.h)
        ext.append((p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2))
    bx0, by0 = min(e[0] for e in ext), min(e[1] for e in ext)
    bx1, by1 = max(e[2] for e in ext), max(e[3] for e in ext)
    body = spec.get("body")
    if body:
        hw, hh = body[0] / 2.0, body[1] / 2.0
    else:
        hw, hh = max(abs(bx0), abs(bx1)), max(abs(by0), abs(by1))
    cy = spec.get("courtyard")
    if cy:
        cx0, cy0, cx1, cy1 = -cy[0] / 2.0, -cy[1] / 2.0, cy[0] / 2.0, cy[1] / 2.0
    else:
        cx0, cy0 = min(bx0, -hw) - 0.25, min(by0, -hh) - 0.25
        cx1, cy1 = max(bx1, hw) + 0.25, max(by1, hh) + 0.25
    g = 0.05
    cx0, cy0, cx1, cy1 = [round(round(v / g) * g, 3) for v in (cx0, cy0, cx1, cy1)]
    fp += [
        _text_prop("Reference", "REF**", 0, cy0 - 0.8, "F.SilkS", u, 0.8),
        _text_prop("Value", name, 0, cy1 + 0.8, "F.Fab", u, 0.6),
        _text_prop("Datasheet", "", 0, 0, "F.Fab", u, hide=True),
        _text_prop("Description", "", 0, 0, "F.Fab", u, hide=True),
        ["attr", kind],
        ["fp_rect", ["start", -hw, -hh], ["end", hw, hh], _stroke(0.1), ["fill", "no"], ["layer", Q("F.Fab")], ["uuid", u("fabrect")]],
        ["fp_rect", ["start", cx0, cy0], ["end", cx1, cy1], _stroke(0.05), ["fill", "no"], ["layer", Q("F.CrtYd")], ["uuid", u("crtyd")]],
    ]
    # silkscreen: top and bottom body edges where no pad is underneath, plus a pin-1 dot
    k = 0
    for yy in (-hh - 0.11, hh + 0.11):
        clear = True
        for e in ext:
            if e[1] - 0.2 < yy < e[3] + 0.2 and e[2] > -hw and e[0] < hw:
                clear = False
        if clear:
            fp.append(["fp_line", ["start", -hw, yy], ["end", hw, yy], _stroke(0.12), ["layer", Q("F.SilkS")], ["uuid", u("silk", k)]])
        k += 1
    if spec.get("pin1", True):
        p1 = pads[0]
        w1, h1 = (p1.h, p1.w) if (p1.rot % 180) else (p1.w, p1.h)
        dx = p1.x - w1 / 2 - 0.35 if p1.x <= 0 else p1.x + w1 / 2 + 0.35
        dy = p1.y
        if cx0 + 0.15 <= dx <= cx1 - 0.15:
            fp.append(["fp_circle", ["center", dx, dy], ["end", dx + 0.1, dy], _stroke(0.12), ["fill", "yes"],
                       ["layer", Q("F.SilkS")], ["uuid", u("pin1")]])
        fp.append(["fp_circle", ["center", -hw + min(0.5, hw / 2), -hh + min(0.5, hh / 2)],
                   ["end", -hw + min(0.5, hw / 2) + 0.1, -hh + min(0.5, hh / 2)], _stroke(0.1), ["fill", "no"],
                   ["layer", Q("F.Fab")], ["uuid", u("pin1fab")]])
    fp.append(["fp_text", "user", Q("${REFERENCE}"), ["at", 0, 0, 0], ["layer", Q("F.Fab")], ["uuid", u("reftext")],
               ["effects", ["font", ["size", 0.5, 0.5], ["thickness", 0.08]]]])
    for i, p in enumerate(pads):
        if p.kind == "smd":
            layers = [Q("F.Cu"), Q("F.Mask")] + ([Q("F.Paste")] if p.paste else [])
            pad = ["pad", Q(p.number), "smd", p.shape, ["at", p.x, p.y, p.rot], ["size", p.w, p.h], ["layers"] + layers]
        elif p.kind == "thru":
            if not p.drill:
                raise DefinitionError("footprint %s pad %s: thru pad needs drill" % (name, p.number))
            pad = ["pad", Q(p.number), "thru_hole", p.shape, ["at", p.x, p.y, p.rot], ["size", p.w, p.h],
                   ["drill", p.drill], ["layers", Q("*.Cu"), Q("*.Mask")], ["remove_unused_layers", "no"]]
        elif p.kind == "npth":
            pad = ["pad", Q(""), "np_thru_hole", "circle", ["at", p.x, p.y], ["size", p.drill or p.w, p.drill or p.w],
                   ["drill", p.drill or p.w], ["layers", Q("*.Cu"), Q("*.Mask")]]
        else:
            raise DefinitionError("footprint %s pad %s: kind must be smd/thru/npth" % (name, p.number))
        if p.shape == "roundrect":
            pad.append(["roundrect_rratio", p.rratio])
        pad.append(["uuid", u("pad", i)])
        fp.append(pad)
    fp.append(["embedded_fonts", "no"])
    if spec.get("model"):
        fp.append(["model", Q(spec["model"]), ["offset", ["xyz", 0, 0, 0]], ["scale", ["xyz", 1, 1, 1]],
                   ["rotate", ["xyz", 0, 0, 0]]])
    return dump(fp)


def write_tables(board_dir, have_sym, have_fp):
    """Write project sym-lib-table / fp-lib-table (always, so the project is self-describing)."""
    sym = "(sym_lib_table\n\t(version 7)\n"
    if have_sym:
        sym += '\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "Project-local symbols generated by rrkicad"))\n' % (NICK, NICK)
    sym += ")\n"
    fp = "(fp_lib_table\n\t(version 7)\n"
    if have_fp:
        fp += '\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.pretty")(options "")(descr "Project-local footprints generated by rrkicad"))\n' % (NICK, NICK)
    fp += ")\n"
    with open(os.path.join(board_dir, "sym-lib-table"), "w") as f:
        f.write(sym)
    with open(os.path.join(board_dir, "fp-lib-table"), "w") as f:
        f.write(fp)
