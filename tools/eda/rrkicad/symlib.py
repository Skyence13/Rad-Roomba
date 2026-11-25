"""Symbol-library access: stock KiCad libraries + project-local symbols.

Only the requested symbol block is parsed (the stock libraries are tens of MB),
derived symbols (``extends``) are flattened the way KiCad does when it embeds a
symbol into a schematic.
"""
import copy
import math
import os
import re

from .sexpr import Q, parse, find, find_all, extract_block

STOCK_SYMBOL_DIR = os.environ.get("KICAD9_SYMBOL_DIR", "/usr/share/kicad/symbols")


class Pin:
    __slots__ = ("number", "name", "etype", "x", "y", "angle", "length", "unit", "hidden")

    def __init__(self, number, name, etype, x, y, angle, length, unit, hidden):
        self.number, self.name, self.etype = number, name, etype
        self.x, self.y, self.angle, self.length = x, y, angle, length
        self.unit, self.hidden = unit, hidden

    @property
    def outward(self):
        """Unit vector pointing away from the body (symbol coords, y up)."""
        a = math.radians(self.angle)
        return (-round(math.cos(a)), -round(math.sin(a)))

    def __repr__(self):
        return "Pin(%s %s %s)" % (self.number, self.name, self.etype)


class SymbolDef:
    """A flattened library symbol."""

    def __init__(self, lib, name, sx):
        self.lib, self.name, self.sx = lib, name, sx
        self.lib_id = "%s:%s" % (lib, name)
        self.props = {}
        for p in find_all(sx, "property"):
            self.props[str(p[1])] = p
        self.is_power = find(sx, "power") is not None
        self.pins = []
        self._bbox = {}
        units = set()
        for sub in find_all(sx, "symbol"):
            m = re.match(r"^(.*)_(\d+)_(\d+)$", str(sub[1]))
            if not m:
                continue
            unit, style = int(m.group(2)), int(m.group(3))
            if style > 1:
                continue  # De Morgan alternate body: not used
            if unit:
                units.add(unit)
            for p in find_all(sub, "pin"):
                at = find(p, "at")
                ln = find(p, "length")
                hide = find(p, "hide")
                hidden = (hide is not None and (len(hide) < 2 or hide[1] == "yes")) or ("hide" in p[1:4])
                self.pins.append(Pin(
                    str(find(p, "number")[1]), str(find(p, "name")[1]), str(p[1]),
                    float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0,
                    float(ln[1]) if ln else 0.0, unit, hidden))
            bb = _graphics_bbox(sub)
            if bb:
                self._bbox.setdefault(unit, []).append(bb)
        self.units = sorted(units) or [1]

    def prop(self, name, default=""):
        p = self.props.get(name)
        return str(p[2]) if p is not None else default

    def unit_pins(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]

    def body_bbox(self, unit):
        """(xmin, ymin, xmax, ymax) of the body graphics of *unit* (symbol coords, y up)."""
        boxes = self._bbox.get(unit, []) + self._bbox.get(0, [])
        if not boxes:
            pts = []
            for p in self.unit_pins(unit):
                a = math.radians(p.angle)
                pts.append((p.x + p.length * math.cos(a), p.y + p.length * math.sin(a)))
            if not pts:
                return (-2.54, -2.54, 2.54, 2.54)
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            return (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5)
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def embedded(self):
        """S-expression for a schematic's ``lib_symbols`` section."""
        sx = copy.deepcopy(self.sx)
        sx[1] = Q(self.lib_id)
        return sx


def _graphics_bbox(sub):
    xs, ys = [], []
    for g in sub[2:]:
        if not isinstance(g, list):
            continue
        k = g[0]
        if k == "rectangle":
            for key in ("start", "end"):
                c = find(g, key)
                xs.append(float(c[1])); ys.append(float(c[2]))
        elif k in ("polyline", "bezier"):
            for c in find_all(find(g, "pts") or [], "xy"):
                xs.append(float(c[1])); ys.append(float(c[2]))
        elif k == "circle":
            c = find(g, "center"); r = float(find(g, "radius")[1])
            xs += [float(c[1]) - r, float(c[1]) + r]; ys += [float(c[2]) - r, float(c[2]) + r]
        elif k == "arc":
            for key in ("start", "mid", "end"):
                c = find(g, key)
                if c:
                    xs.append(float(c[1])); ys.append(float(c[2]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


class SymbolLibs:
    """Resolve ``Lib:Name`` ids against stock libraries and local library texts."""

    def __init__(self, stock_dir=STOCK_SYMBOL_DIR, local=None):
        self.stock_dir = stock_dir
        self.local = dict(local or {})  # nickname -> library text
        self._text = {}
        self._cache = {}

    def add_local(self, nickname, text):
        self.local[nickname] = text
        self._text.pop(nickname, None)
        for k in [k for k in self._cache if k.startswith(nickname + ":")]:
            del self._cache[k]

    def _libtext(self, lib):
        if lib not in self._text:
            if lib in self.local:
                self._text[lib] = self.local[lib]
            else:
                path = os.path.join(self.stock_dir, lib + ".kicad_sym")
                if not os.path.exists(path):
                    raise KeyError("symbol library '%s' not found (%s)" % (lib, path))
                with open(path, encoding="utf-8") as f:
                    self._text[lib] = f.read()
        return self._text[lib]

    def names(self, lib):
        return re.findall(r'^\t\(symbol "([^"]+)"', self._libtext(lib), re.M)

    def has(self, lib_id):
        try:
            self.get(lib_id)
            return True
        except KeyError:
            return False

    def _raw(self, lib, name):
        text = self._libtext(lib)
        m = re.search(r'^\t\(symbol "%s"\s*$' % re.escape(name), text, re.M)
        if not m:
            import difflib
            close = difflib.get_close_matches(name, self.names(lib), 5)
            raise KeyError("symbol '%s' not in library '%s'%s" % (
                name, lib, ("; did you mean: " + ", ".join(close)) if close else ""))
        return parse(extract_block(text, m.start() + 1))

    def _flat(self, lib, name, depth=0):
        sx = self._raw(lib, name)
        ext = find(sx, "extends")
        if ext is None:
            return sx
        if depth > 8:
            raise ValueError("extends loop at %s:%s" % (lib, name))
        parent = self._flat(lib, str(ext[1]), depth + 1)
        pname = str(parent[1])
        out = copy.deepcopy(parent)
        out[1] = Q(name)
        # child properties override / extend the parent's
        child_props = find_all(sx, "property")
        names = [str(p[1]) for p in child_props]
        merged = []
        seen = set()
        for item in out:
            if isinstance(item, list) and item and item[0] == "property":
                pn = str(item[1])
                if pn in names:
                    merged.append(child_props[names.index(pn)])
                    seen.add(pn)
                else:
                    merged.append(item)
            else:
                merged.append(item)
        # append properties only the child has, right after the last property
        extra = [p for p in child_props if str(p[1]) not in seen]
        if extra:
            last = max(i for i, it in enumerate(merged)
                       if isinstance(it, list) and it and it[0] == "property")
            merged[last + 1:last + 1] = extra
        for item in merged:
            if isinstance(item, list) and item and item[0] == "symbol":
                s = str(item[1])
                if s.startswith(pname + "_"):
                    item[1] = Q(name + s[len(pname):])
        return merged

    def get(self, lib_id):
        if lib_id not in self._cache:
            if ":" not in lib_id:
                raise KeyError("symbol id must be 'Library:Name', got '%s'" % lib_id)
            lib, name = lib_id.split(":", 1)
            self._cache[lib_id] = SymbolDef(lib, name, self._flat(lib, name))
        return self._cache[lib_id]
