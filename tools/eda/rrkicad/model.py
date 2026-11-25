"""Board-definition API (the single source of truth for a board).

A board definition file (``electronics/<board>/board.py``) builds one ``Board``
object and leaves it in a module-level variable called ``board``.

Units are millimetres.  Board coordinates are X right, **Y up**, relative to the
board origin chosen by the outline call; rotations are KiCad footprint
orientations in degrees (counter-clockwise positive, as shown in the footprint
properties dialog).  See tools/eda/README.md for the full reference.
"""
import fnmatch
import hashlib
import re

__all__ = ["Board", "Group", "Part", "Rules", "Pad", "SymPin", "DefinitionError"]

PKG_METRIC = {"0201": "0603", "0402": "1005", "0603": "1608", "0805": "2012", "1206": "3216",
              "1210": "3225", "1812": "4532", "2010": "5025", "2512": "6332"}


class DefinitionError(Exception):
    """The board definition is inconsistent."""


def stable_uuid(*parts):
    """Deterministic UUID derived from a hash of *parts*."""
    h = hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return "%s-%s-%s-%s-%s" % (h[0:8], h[8:12], "5" + h[13:16], "8" + h[17:20], h[20:32])


class Rules:
    """Fabrication rules (defaults: JLCPCB-class 2/4-layer, 1.6 mm)."""

    def __init__(self, min_track=0.15, min_clearance=0.15, min_via_dia=0.6, min_via_drill=0.3,
                 min_annular=0.13, edge_clearance=0.3, min_hole=0.3, min_hole_clearance=0.25,
                 min_hole_to_hole=0.25, track=0.2, clearance=0.15, via_dia=0.6, via_drill=0.3,
                 min_silk_text=0.8, min_silk_thickness=0.1, silk_clearance=0.0):
        self.min_track, self.min_clearance = min_track, min_clearance
        self.min_via_dia, self.min_via_drill, self.min_annular = min_via_dia, min_via_drill, min_annular
        self.edge_clearance, self.min_hole = edge_clearance, min_hole
        self.min_hole_clearance, self.min_hole_to_hole = min_hole_clearance, min_hole_to_hole
        self.track, self.clearance, self.via_dia, self.via_drill = track, clearance, via_dia, via_drill
        self.min_silk_text, self.min_silk_thickness = min_silk_text, min_silk_thickness
        self.silk_clearance = silk_clearance


class Pad:
    """Pad of a project-local footprint.  Coordinates: footprint editor frame
    (x right, **y down**, top view), mm.

    kind: "smd" | "thru" | "npth".  shape: "rect" | "roundrect" | "circle" | "oval".
    """

    def __init__(self, number, x, y, w, h=None, shape="roundrect", kind="smd", drill=None,
                 rot=0, rratio=0.25, paste=True):
        self.number, self.x, self.y = str(number), x, y
        self.w, self.h = w, (w if h is None else h)
        self.shape, self.kind, self.drill, self.rot, self.rratio, self.paste = shape, kind, drill, rot, rratio, paste


class SymPin:
    """Pin of a project-local symbol.

    etype: KiCad electrical type (input, output, bidirectional, tri_state, passive,
    power_in, power_out, open_collector, open_emitter, no_connect, unspecified, free).
    side: "L" | "R" | "T" | "B" (pins are stacked in the order given, 2.54 mm pitch).
    """

    def __init__(self, number, name, etype="passive", side="L", unit=1):
        self.number, self.name, self.etype, self.side, self.unit = str(number), name, etype, side, unit


class Part:
    def __init__(self, group, ref, symbol, value, footprint=None, mpn="", mfr="", pins=None, nc=(),
                 unused="error", at=None, side=None, near=None, edge=None, dnp=False, bom=True,
                 notes="", verify=False, datasheet=None, description=None, fields=None, sch_rot=0,
                 silk_ref=None, model=None, rot=None):
        self.group, self.ref, self.symbol, self.value = group, ref, symbol, str(value)
        self.footprint, self.mpn, self.mfr = footprint, mpn, mfr
        self.pins = {str(k): v for k, v in (pins or {}).items()}
        self.nc = [str(n) for n in nc]
        self.unused = unused
        self.at, self.near, self.edge = at, near, edge
        self.side = side
        if at is not None:
            at = tuple(at)
            if len(at) not in (2, 3, 4):
                raise DefinitionError("%s: at=(x, y[, rot[, 'F'|'B']])" % ref)
            self.x, self.y = float(at[0]), float(at[1])
            self.rot = float(at[2]) if len(at) > 2 else 0.0
            if len(at) > 3:
                self.side = at[3]
        else:
            self.x = self.y = self.rot = None
        self.auto_rot = rot if at is None else None   # rotation constraint for auto-arrange
        self.side = (self.side or "F").upper()[0]
        if self.side not in "FB":
            raise DefinitionError("%s: side must be 'F' or 'B'" % ref)
        self.dnp, self.bom, self.notes, self.verify = dnp, bom, notes, verify
        self.datasheet, self.description = datasheet, description
        self.fields = dict(fields or {})
        self.sch_rot = sch_rot
        self.silk_ref = silk_ref
        self.model = model
        # resolved later
        self.sym = None          # SymbolDef
        self.pin_net = {}        # pin number -> net name | None (no-connect)
        self.pin_name = {}       # pin number -> pin name
        self.auto_placed = False

    @property
    def placed(self):
        return self.x is not None


class Group:
    """A functional group = one hierarchical schematic sheet."""

    def __init__(self, board, name, title, notes=""):
        if not re.match(r"^[A-Za-z0-9_\-]+$", name):
            raise DefinitionError("group name '%s': use letters, digits, '_' or '-'" % name)
        self.board, self.name, self.title, self.notes = board, name, title, notes
        self.parts = []

    def part(self, ref, symbol, value, footprint=None, **kw):
        """Add a part.  ``pins`` maps pin number or pin name -> net name."""
        if ref in self.board._refs:
            raise DefinitionError("duplicate reference %s" % ref)
        p = Part(self, ref, symbol, value, footprint, **kw)
        self.parts.append(p)
        self.board._refs[ref] = p
        return p

    # --- two-pin conveniences -------------------------------------------------
    def _two(self, ref, sym, fp, value, a, b, kw):
        kw.setdefault("pins", {"1": a, "2": b})
        return self.part(ref, sym, value, fp, **kw)

    def R(self, ref, value, a, b, pkg="0402", **kw):
        return self._two(ref, "Device:R", "Resistor_SMD:R_%s_%sMetric" % (pkg, PKG_METRIC[pkg]), value, a, b, kw)

    def C(self, ref, value, a, b, pkg="0402", **kw):
        return self._two(ref, "Device:C", "Capacitor_SMD:C_%s_%sMetric" % (pkg, PKG_METRIC[pkg]), value, a, b, kw)

    def L(self, ref, value, a, b, pkg="0603", **kw):
        return self._two(ref, "Device:L", "Inductor_SMD:L_%s_%sMetric" % (pkg, PKG_METRIC[pkg]), value, a, b, kw)

    def FB(self, ref, value, a, b, pkg="0603", **kw):
        return self._two(ref, "Device:FerriteBead", "Inductor_SMD:L_%s_%sMetric" % (pkg, PKG_METRIC[pkg]), value, a, b, kw)

    def LED(self, ref, value, anode, cathode, pkg="0603", **kw):
        kw.setdefault("pins", {"A": anode, "K": cathode})
        return self.part(ref, "Device:LED", value, "LED_SMD:LED_%s_%sMetric" % (pkg, PKG_METRIC[pkg]), **kw)


class Board:
    def __init__(self, name, title, rev="A", date="", docnum="", company="", layers=2, thickness=1.6,
                 rules=None, description="", silk_refs=True, paper="A3"):
        if not re.match(r"^[A-Za-z0-9_\-\.]+$", name):
            raise DefinitionError("board name must be file-name safe")
        if layers not in (2, 4):
            raise DefinitionError("layers must be 2 or 4")
        self.name, self.title, self.rev, self.date = name, title, rev, date
        self.docnum, self.company, self.layers, self.thickness = docnum, company, layers, thickness
        self.rules = rules or Rules()
        self.description = description
        self.silk_refs = silk_refs
        self.paper = paper
        self.groups = []
        self._refs = {}
        self.rails = {}          # net -> {"symbol": lib_id|None, "style": "gnd"|"supply"}
        self.netclasses = []     # dicts
        self.outline = None      # {"pts": [(x,y)...], "radius": r}
        self.cutouts = []
        self.holes = []
        self.zones = []
        self.keepouts = []
        self.tracks = []
        self.vias = []
        self.texts = []
        self.waivers = []
        self.severities = []
        self.local_symbols = {}
        self.local_footprints = {}
        self.routing = {"passes": 100, "threads": None, "timeout": None, "enabled": True, "extra_args": [],
                        "optimizer": True}
        self.autoplace = {"clearance": 0.3, "grid": 0.25, "edge_margin": 0.5, "ic_halo": 1.5, "rotations": (0, 90, 180, 270)}
        self.stackup_notes = []

    # ------------------------------------------------------------------ parts
    def group(self, name, title=None, notes=""):
        if any(g.name == name for g in self.groups):
            raise DefinitionError("duplicate group '%s'" % name)
        g = Group(self, name, title or name, notes)
        self.groups.append(g)
        return g

    @property
    def parts(self):
        return [p for g in self.groups for p in g.parts]

    def part(self, ref):
        return self._refs[ref]

    # ------------------------------------------------------------------- nets
    def rail(self, *names, symbol=None, style=None):
        """Declare power rails: drawn with power symbols instead of labels.

        The stock ``power:<name>`` symbol is used when it exists, otherwise a
        local power symbol is generated (style "gnd" or "supply", guessed from
        the name unless given)."""
        for n in names:
            st = style or ("gnd" if re.search(r"GND|VSS|^0V", n, re.I) else "supply")
            self.rails[n] = {"symbol": symbol, "style": st}

    def netclass(self, name, nets, track=None, clearance=None, via_dia=None, via_drill=None,
                 diff_width=None, diff_gap=None):
        """Net class; *nets* are exact names or KiCad wildcard patterns (``*``/``?``)."""
        r = self.rules
        self.netclasses.append({
            "name": name, "nets": list(nets),
            "track": track if track is not None else r.track,
            "clearance": clearance if clearance is not None else r.clearance,
            "via_dia": via_dia if via_dia is not None else r.via_dia,
            "via_drill": via_drill if via_drill is not None else r.via_drill,
            "diff_width": diff_width, "diff_gap": diff_gap})

    def class_of(self, net):
        """Net-class dict for *net* (first matching class wins; else defaults)."""
        for nc in self.netclasses:
            for pat in nc["nets"]:
                if pat == net or fnmatch.fnmatchcase(net, pat):
                    return nc
        r = self.rules
        return {"name": "Default", "track": r.track, "clearance": r.clearance,
                "via_dia": r.via_dia, "via_drill": r.via_drill}

    # ---------------------------------------------------------------- outline
    def outline_rect(self, w, h, radius=0.0, origin="center"):
        """Rectangular outline; origin 'center' or 'corner' (lower-left)."""
        if origin == "center":
            x0, y0 = -w / 2.0, -h / 2.0
        elif origin == "corner":
            x0, y0 = 0.0, 0.0
        else:
            raise DefinitionError("origin must be 'center' or 'corner'")
        self.outline = {"pts": [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], "radius": radius}

    def outline_poly(self, pts, radius=0.0):
        """Polygon outline (list of (x, y)); *radius* rounds every corner."""
        self.outline = {"pts": [tuple(map(float, p)) for p in pts], "radius": radius}

    def cutout_rect(self, x, y, w, h, radius=0.0):
        """Internal cutout, centred at (x, y)."""
        self.cutouts.append({"kind": "poly", "radius": radius,
                             "pts": [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]})

    def cutout_circle(self, x, y, dia):
        self.cutouts.append({"kind": "circle", "x": x, "y": y, "dia": dia})

    def cutout_poly(self, pts, radius=0.0):
        self.cutouts.append({"kind": "poly", "pts": [tuple(p) for p in pts], "radius": radius})

    def hole(self, ref, x, y, drill, keepout=None, plated=False, pad=None, net=None):
        """Mounting hole (board-only footprint).  *keepout*: diameter of a circular
        rule area (no tracks/vias/copper pour/footprints) centred on the hole."""
        if ref in self._refs or any(h["ref"] == ref for h in self.holes):
            raise DefinitionError("duplicate reference %s" % ref)
        if plated and not pad:
            raise DefinitionError("%s: plated hole needs pad=<diameter>" % ref)
        self.holes.append({"ref": ref, "x": float(x), "y": float(y), "drill": float(drill),
                           "keepout": keepout, "plated": plated, "pad": pad, "net": net})

    # ----------------------------------------------------------- copper items
    def zone(self, net, layers, polygon=None, priority=0, clearance=None, min_width=0.2,
             connect="thermal", thermal_gap=0.25, thermal_width=0.3, name=None, islands="remove"):
        """Copper zone.  polygon=None fills the whole board outline.
        connect: 'thermal' | 'solid' | 'none'.  islands: 'remove' | 'keep'."""
        if isinstance(layers, str):
            layers = [layers]
        self.zones.append({"net": net, "layers": list(layers), "polygon": polygon, "priority": priority,
                           "clearance": clearance, "min_width": min_width, "connect": connect,
                           "thermal_gap": thermal_gap, "thermal_width": thermal_width,
                           "name": name or ("%s_%s" % (net, "_".join(layers))), "islands": islands})

    def keepout(self, name, polygon=None, circle=None, layers=("*.Cu",), tracks=True, vias=True,
                pads=False, copper=True, footprints=False):
        """Rule area.  polygon=[(x, y)...] or circle=(x, y, dia)."""
        if (polygon is None) == (circle is None):
            raise DefinitionError("keepout %s: give polygon or circle" % name)
        self.keepouts.append({"name": name, "polygon": polygon, "circle": circle, "layers": list(layers),
                              "tracks": tracks, "vias": vias, "pads": pads, "copper": copper,
                              "footprints": footprints})

    def track(self, net, pts, layer="F.Cu", width=None):
        """Pre-route: fixed track through *pts* (kept untouched by the autorouter)."""
        self.tracks.append({"net": net, "pts": [tuple(map(float, p)) for p in pts], "layer": layer, "width": width})

    def via(self, net, x, y, dia=None, drill=None):
        """Pre-route: fixed through via."""
        self.vias.append({"net": net, "x": float(x), "y": float(y), "dia": dia, "drill": drill})

    def text(self, text, x, y, layer="F.SilkS", size=1.0, thickness=None, rot=0, justify="center"):
        """Board text.  ``{name}``, ``{rev}``, ``{date}``, ``{title}``, ``{docnum}`` are substituted."""
        self.texts.append({"text": text, "x": x, "y": y, "layer": layer, "size": size,
                           "thickness": thickness, "rot": rot, "justify": justify})

    # ------------------------------------------------------- checks / waivers
    def waive(self, check, rule, reason, match=None):
        """Waive ERC/DRC violations of type *rule* whose text matches regex *match*
        (None = all of that type).  Listed with *reason* in reports/summary.json."""
        if check not in ("erc", "drc"):
            raise DefinitionError("waive: check must be 'erc' or 'drc'")
        if not reason or len(reason.strip()) < 10:
            raise DefinitionError("waive: a written justification is required")
        self.waivers.append({"check": check, "rule": rule, "match": match, "reason": reason})

    def severity(self, check, rule, level, reason):
        """Change a KiCad rule severity in the project ('error'|'warning'|'ignore').
        Recorded as a waiver in the summary."""
        if level not in ("error", "warning", "ignore"):
            raise DefinitionError("severity level must be error|warning|ignore")
        if not reason or len(reason.strip()) < 10:
            raise DefinitionError("severity: a written justification is required")
        self.severities.append({"check": check, "rule": rule, "level": level, "reason": reason})

    # ------------------------------------------------------- local libraries
    def symbol(self, name, pins, ref_prefix="U", footprint="", datasheet="", description="", units=None):
        """Define a project-local symbol ``rr_local:<name>`` from a pin list."""
        self.local_symbols[name] = {"pins": list(pins), "ref_prefix": ref_prefix, "footprint": footprint,
                                    "datasheet": datasheet, "description": description}
        return "rr_local:" + name

    def footprint(self, name, pads, body=None, courtyard=None, pin1=True, kind=None, description="",
                  height=None, model=None):
        """Define a project-local footprint ``rr_local:<name>`` from a pad list.

        body=(w, h): package outline drawn on F.Fab and (outside the pads) F.SilkS.
        courtyard=(w, h): defaults to pads+body bounding box + 0.25 mm."""
        self.local_footprints[name] = {"pads": list(pads), "body": body, "courtyard": courtyard, "pin1": pin1,
                                       "kind": kind, "description": description, "height": height,
                                       "model": model}
        return "rr_local:" + name

    # ---------------------------------------------------------------- routing
    def route(self, **kw):
        """Autorouter options: passes, threads, timeout (s), enabled, optimizer, extra_args."""
        for k in kw:
            if k not in self.routing:
                raise DefinitionError("unknown routing option '%s'" % k)
        self.routing.update(kw)

    def autoplace_options(self, **kw):
        for k in kw:
            if k not in self.autoplace:
                raise DefinitionError("unknown autoplace option '%s'" % k)
        self.autoplace.update(kw)

    def fab_note(self, text):
        """Extra numbered note on the fabrication drawing."""
        self.stackup_notes.append(text)

    def uuid(self, *parts):
        return stable_uuid(self.name, *parts)


def resolve(board, libs):
    """Bind every part to its library symbol and compute pin->net maps.

    Returns ``nets``: {net: [(ref, pin_number), ...]} in definition order.
    Raises DefinitionError listing *all* problems found.
    """
    errs = []
    nets = {}
    if board.outline is None:
        errs.append("board has no outline (outline_rect / outline_poly)")
    for part in board.parts:
        try:
            sym = libs.get(part.symbol)
        except KeyError as e:
            errs.append("%s: %s" % (part.ref, e.args[0]))
            continue
        part.sym = sym
        if part.footprint is None:
            part.footprint = sym.prop("Footprint")
        if not part.footprint or ":" not in part.footprint:
            errs.append("%s: no footprint given and symbol %s has no default" % (part.ref, part.symbol))
        by_num, by_name = {}, {}
        for pin in sym.pins:
            by_num.setdefault(pin.number, pin)
            by_name.setdefault(pin.name, []).append(pin)
        pin_net = {}
        for key, net in part.pins.items():
            if key in by_num:
                targets = [by_num[key]]
            elif key in by_name:
                targets = by_name[key]
            else:
                errs.append("%s: symbol %s has no pin '%s' (pins: %s)" % (
                    part.ref, part.symbol, key,
                    ", ".join("%s=%s" % (p.number, p.name) for p in sym.pins)))
                continue
            if not net or not isinstance(net, str):
                errs.append("%s pin %s: net name must be a non-empty string" % (part.ref, key))
                continue
            for t in targets:
                if t.number in pin_net and pin_net[t.number] != net:
                    errs.append("%s pin %s assigned twice (%s / %s)" % (part.ref, t.number, pin_net[t.number], net))
                pin_net[t.number] = net
        for key in part.nc:
            if key in by_num:
                targets = [by_num[key]]
            elif key in by_name:
                targets = by_name[key]
            else:
                errs.append("%s: nc pin '%s' not in symbol %s" % (part.ref, key, part.symbol))
                continue
            for t in targets:
                if t.number in pin_net:
                    errs.append("%s pin %s is both connected and nc" % (part.ref, t.number))
                pin_net[t.number] = None
        missing = []
        for pin in sym.pins:
            if pin.number in pin_net:
                continue
            if pin.etype == "no_connect" or part.unused == "nc":
                pin_net[pin.number] = None
            else:
                missing.append("%s=%s" % (pin.number, pin.name))
        if missing:
            errs.append("%s: pins neither connected nor declared nc: %s" % (part.ref, ", ".join(missing)))
        # pins stacked at one location must share a net
        for unit in sym.units:
            pos = {}
            for pin in sym.unit_pins(unit):
                pos.setdefault((round(pin.x, 3), round(pin.y, 3)), []).append(pin)
            for plist in pos.values():
                ns = {pin_net.get(p.number) for p in plist}
                if len(ns) > 1:
                    errs.append("%s: stacked pins %s must share one net, got %s" % (
                        part.ref, "/".join(p.number for p in plist), sorted(map(str, ns))))
        part.pin_net = pin_net
        part.pin_name = {p.number: p.name for p in sym.pins}
        for pin in sym.pins:
            n = pin_net.get(pin.number)
            if n:
                nets.setdefault(n, [])
                if (part.ref, pin.number) not in nets[n]:
                    nets[n].append((part.ref, pin.number))
    for item, kind in [(t, "track") for t in board.tracks] + [(v, "via") for v in board.vias] + \
                      [(z, "zone") for z in board.zones]:
        if item["net"] not in nets:
            errs.append("%s refers to unknown net '%s'" % (kind, item["net"]))
    for h in board.holes:
        if h["net"] and h["net"] not in nets:
            errs.append("hole %s refers to unknown net '%s'" % (h["ref"], h["net"]))
    for n in board.rails:
        if n not in nets:
            errs.append("rail '%s' is declared but no pin uses it" % n)
    if errs:
        raise DefinitionError("board definition errors:\n  - " + "\n  - ".join(errs))
    return nets
