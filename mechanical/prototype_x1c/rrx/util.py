"""Geometry helpers, BREP cache and the part registry for the RR-X prototype body."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

from mechanical.common import params as P

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
CACHE = OUT / "cache"
V = cq.Vector


def box(x0, x1, y0, y1, z0, z1):
    x0, x1, y0, y1, z0, z1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), min(z0, z1), max(z0, z1)
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, h, base=(0, 0, 0), axis=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, h, V(*base), V(*axis))


def cyl2(r, p0, p1):
    """Cylinder between two points."""
    d = V(*p1) - V(*p0)
    return cq.Solid.makeCylinder(r, d.Length, V(*p0), d)


def cone(r0, r1, h, base, axis=(0, 0, 1)):
    return cq.Solid.makeCone(r0, r1, h, V(*base), V(*axis))


def fuse(*solids):
    out = solids[0]
    for s in solids[1:]:
        out = out.fuse(s)
    return out.clean()


def cut(a, *tools):
    for t in tools:
        a = a.cut(t)
    return a


def compound(shapes):
    return cq.Compound.makeCompound(list(shapes))


def mirror_y(shape):
    return shape.mirror("XZ")


def prism(pts, z0, z1):
    """Extruded polygon (pts in xy)."""
    return cq.Workplane("XY", origin=(0, 0, z0)).polyline([tuple(p) for p in pts]).close().extrude(z1 - z0).val()


def prism_xz(pts, y0, y1):
    """Polygon given in (x, z), extruded from y0 to y1."""
    w = cq.Workplane("XZ", origin=(0, y0, 0)).polyline([tuple(p) for p in pts]).close().extrude(-(y1 - y0))
    return w.val()


def prism_yz(pts, x0, x1):
    """Polygon given in (y, z), extruded from x0 to x1."""
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline([tuple(p) for p in pts]).close().extrude(x1 - x0).val()


def rbox(x0, x1, y0, y1, z0, z1, r, axis="z"):
    """Box with the four edges parallel to `axis` rounded."""
    b = cq.Workplane("XY").add(box(x0, x1, y0, y1, z0, z1))
    sel = {"z": "|Z", "x": "|X", "y": "|Y"}[axis]
    return b.edges(sel).fillet(r).val()


def place(solid, origin, zdir, xdir=None):
    """Move a solid built in a local frame (z = axis) so local z points along zdir at origin."""
    zdir = P._unit(zdir)
    if xdir is None:
        ref = (0, 0, 1) if abs(zdir[2]) < 0.9 else (1, 0, 0)
        xdir = P._unit((ref[1] * zdir[2] - ref[2] * zdir[1], ref[2] * zdir[0] - ref[0] * zdir[2], ref[0] * zdir[1] - ref[1] * zdir[0]))
    return solid.moved(cq.Location(cq.Plane(origin=tuple(origin), xDir=tuple(xdir), normal=tuple(zdir))))


def bounds(shape):
    bb = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, bb, False, False)
    return [float(v) for v in bb.Get()]


def solids_of(shape):
    return shape.Solids() if hasattr(shape, "Solids") else [shape]


def biggest(shape):
    """Largest solid of a boolean result (drops slivers)."""
    s = solids_of(shape)
    return max(s, key=lambda q: q.Volume()) if s else shape


USED = set()     # cache files used in this run (build.py prunes the rest)


def cached(key, builder):
    """BREP cache keyed on the parameters (and source digest) that define the shape."""
    CACHE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = CACHE / f"{key[0]}_{digest}.brep"
    USED.add(path.name)
    if path.exists():
        return cq.Shape.importBrep(str(path))
    shape = builder()
    shape.exportBrep(str(path))
    return shape


def src_digest(*modules):
    h = hashlib.sha1()
    for m in modules:
        h.update(Path(m.__file__).read_bytes())
    h.update(json.dumps(P.summary(), sort_keys=True, default=str).encode())
    return h.hexdigest()[:12]


# ----------------------------------------------------------------------------------------------- skin
def ring_wire(row, n=24):
    pts = [V(*P.ring_point(row, 2 * math.pi * i / n)) for i in range(n)]
    return cq.Wire.assembleEdges([cq.Edge.makeSpline(pts, periodic=True)])


def loft(rows):
    return cq.Solid.makeLoft([ring_wire(r) for r in rows], False)


def inset_rows(rows, d, top_drop=None):
    """Approximate inward offset of a section table by d (plan) and of the crown by top_drop (default d)."""
    td = d if top_drop is None else top_drop
    z0, z1 = rows[0][0], rows[-1][0]
    out = []
    for z, t, n, b in rows:
        f = (z - z0) / (z1 - z0)
        out.append((z - td * f ** 2, t + d, n - d, b - d))
    return out


def ring_xy(row, n=120):
    return [P.ring_point(row, 2 * math.pi * i / n)[:2] for i in range(n)]


def interp_row(part, z):
    return P._interp_row(P.BODY_ROWS[part], z)


# ----------------------------------------------------------------------------------------------- registry
class Part:
    """One real part of the RR-X build, modelled in base_link coordinates (assembled position)."""

    def __init__(self, pn, name, shape, kind, material, group, *, qty=1, mass=None, color="#9aa3a8", orient=(0, 0, 0), note="",
                 hard=True, internal=None, mates=(), supplier="", mpn="", verified="", print_note="", subasm="", process=None, local=None):
        self.pn, self.name, self.shape, self.kind, self.material, self.group = pn, name, shape, kind, material, group
        self.qty, self._mass, self.color, self.orient, self.note = qty, mass, color, orient, note
        self.hard, self.internal, self.mates = hard, internal, set(mates)
        self.supplier, self.mpn, self.verified, self.print_note, self.subasm, self.process = supplier, mpn, verified, print_note, subasm or group, process
        self.local = local          # same solid in its own flat frame (for parts that are placed at an angle)
        self.bb = bounds(shape)
        self.dropped = []           # volumes (mm3) of boolean slivers removed by assembly.add()

    @property
    def volume(self):
        return sum(s.Volume() for s in solids_of(self.shape))

    def centroid(self):
        tot, acc = 0.0, V(0, 0, 0)
        for s in solids_of(self.shape):
            v = s.Volume()
            acc = acc + cq.Shape.centerOfMass(s) * v
            tot += v
        return acc / tot if tot else V(0, 0, 0)
