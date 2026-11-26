"""Geometry helpers, BREP cache and the part record used by every head module."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

from . import hp

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CACHE = OUT / "cache"
V = cq.Vector


def box(x0, x1, y0, y1, z0, z1):
    x0, x1, y0, y1, z0, z1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, h, base, axis=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, h, V(*base), V(*axis))


def cyl2(r, p0, p1):
    d = V(*p1) - V(*p0)
    return cq.Solid.makeCylinder(r, d.Length, V(*p0), d)


def compound(shapes):
    return cq.Compound.makeCompound(list(shapes))


def fuse_all(shapes):
    """Sequential fuse (a compound of overlapping tools gives wrong results in OCCT booleans)."""
    shapes = list(shapes)
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    try:
        return out.clean()
    except Exception:
        return out


def cut_all(base, tools):
    for t in tools:
        base = base.cut(t)
    return base


def mirror_y(shape):
    return shape.mirror("XZ")


def prism(pts, z0, z1):
    return cq.Workplane("XY", origin=(0, 0, z0)).polyline([tuple(p) for p in pts]).close().extrude(z1 - z0).val()


def prism_xz(pts, y0, y1):
    """Polygon given in (x, z), extruded from y0 to y1."""
    return cq.Workplane("XZ", origin=(0, y0, 0)).polyline([tuple(p) for p in pts]).close().extrude(-(y1 - y0)).val()


def round_z(shape, r, selector="|Z"):
    """Fillet the vertical edges picked by a CadQuery selector that lie on the bounding box corners (cheap)."""
    try:
        return cq.Workplane("XY").add(shape).edges(selector).fillet(r).val()
    except Exception:
        return shape


def bounds(shape):
    bb = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, bb, False, False)
    return tuple(round(float(v), 4) for v in bb.Get())   # x0 y0 z0 x1 y1 z1


def volume(shape):
    return float(shape.Volume())


def centroid(shape):
    c = cq.Shape.centerOfMass(shape)
    return (c.x, c.y, c.z)


def cached(key, builder):
    """BREP cache keyed by the head parameters + a caller key + the source of the builder's module."""
    import inspect
    src = inspect.getsource(inspect.getmodule(builder)) if inspect.getmodule(builder) else ""
    blob = json.dumps([key, {k: v for k, v in vars(hp).items() if k.isupper() and isinstance(v, (int, float, tuple, list, dict, str))}],
                      sort_keys=True, default=str) + src
    h = hashlib.sha1(blob.encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{key if isinstance(key, str) else key[0]}_{h}.brep"
    if f.exists():
        try:
            return cq.Shape.importBrep(str(f))
        except Exception:
            pass
    s = builder()
    s.exportBrep(str(f))
    return s


@dataclass
class Part:
    name: str                      # unique instance name in the assembly
    pn: str                        # part number (RR-HD-X-xxx prototype, RR-HD-P-xxx production, RR-HD-S-xxx shared)
    shape: object                  # solid in base_link coordinates (installed position, 3 mm rail insert)
    material: str
    kind: str = "fab"              # printed | fab (machined / sheet) | purchased | envelope (other work package)
    group: str = "frame"
    desc: str = ""
    mass_g: float | None = None    # override (purchased items); otherwise volume x density
    color: str = "#888888"
    orient: tuple = (0.0, 0.0, 0.0)   # print orientation: Euler X, Y, Z (deg) applied to the installed shape
    proc: str = ""                 # manufacturing process note
    hard: bool = True              # False: compliant item modelled at its compressed size (interference check still applies)
    allow: set = field(default_factory=set)   # instance names (or prefixes ending with *) this part may overlap by design

    def mass(self):
        if self.mass_g is not None:
            return self.mass_g
        return volume(self.shape) / 1000.0 * hp.MATERIAL_DENSITY[self.material]

    def cg(self):
        return centroid(self.shape)

    def bb(self):
        return bounds(self.shape)


def mass_cg(parts):
    m = sum(p.mass() for p in parts)
    if m <= 0:
        return 0.0, (0.0, 0.0, 0.0)
    c = [sum(p.mass() * p.cg()[i] for p in parts) / m for i in range(3)]
    return m, tuple(c)


def oriented(shape, orient):
    """Apply a print orientation (Euler X, Y, Z deg) and drop the part onto z = 0 with its bounding box min at the origin."""
    s = shape
    for ax, ang in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient):
        if abs(ang) > 1e-9:
            s = s.rotate(V(0, 0, 0), V(*ax), ang)
    b = bounds(s)
    return s.translate(V(-b[0], -b[1], -b[2]))


def export_step(shape, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape if isinstance(shape, cq.Shape) else shape, str(path))


def assembly_step(parts, path, name):
    asm = cq.Assembly(name=name)
    for p in parts:
        asm.add(p.shape, name=p.name, color=cq.Color(*[int(p.color[i:i + 2], 16) / 255 for i in (1, 3, 5)]))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    asm.save(str(path))
