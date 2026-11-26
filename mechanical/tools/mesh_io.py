"""Small dependency-free mesh helpers shared by the mechanical work packages (stdlib only).

read_stl / write_stl   binary (and ASCII read) STL as a flat list of triangles ((x, y, z) * 3)
write_3mf              plain 3MF core-spec package (one or more objects, welded vertices, millimetres)
transform / bbox       Euler rotation (deg, applied X then Y then Z), translation, bounding box
tessellate_to_tris     CadQuery/OCP shape -> triangle list (only imported when called)
"""
from __future__ import annotations

import math
import struct
import zipfile
from pathlib import Path


# ----------------------------------------------------------------------------------------------- STL
def read_stl(path):
    data = Path(path).read_bytes()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):
            tris = []
            for rec in struct.iter_unpack("<12fH", data[84:]):
                tris.append((rec[3:6], rec[6:9], rec[9:12]))
            return tris
    tris, cur = [], []
    for line in data.decode("ascii", "replace").splitlines():
        t = line.split()
        if len(t) == 4 and t[0] == "vertex":
            cur.append((float(t[1]), float(t[2]), float(t[3])))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    if not tris:
        raise ValueError(f"{path}: not a readable STL")
    return tris


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    m = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    return (n[0] / m, n[1] / m, n[2] / m) if m > 0 else (0.0, 0.0, 0.0)


def write_stl(path, tris):
    buf = bytearray(b"RR mesh_io binary STL".ljust(80, b" "))
    buf += struct.pack("<I", len(tris))
    for a, b, c in tris:
        buf += struct.pack("<12fH", *_normal(a, b, c), *a, *b, *c, 0)
    Path(path).write_bytes(bytes(buf))


# ----------------------------------------------------------------------------------------------- geometry
def bbox(tris):
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    zs = [p[2] for t in tris for p in t]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def rot_matrix(rx=0.0, ry=0.0, rz=0.0):
    """Rotation matrix for Euler angles in degrees applied in the order X, then Y, then Z (fixed axes)."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    mx = ((1, 0, 0), (0, ca, -sa), (0, sa, ca))
    my = ((cb, 0, sb), (0, 1, 0), (-sb, 0, cb))
    mz = ((cc, -sc, 0), (sc, cc, 0), (0, 0, 1))

    def mul(p, q):
        return tuple(tuple(sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(mz, mul(my, mx))


def transform(tris, m=None, t=(0.0, 0.0, 0.0)):
    m = m or ((1, 0, 0), (0, 1, 0), (0, 0, 1))

    def f(p):
        return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + t[0],
                m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + t[1],
                m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + t[2])
    return [(f(a), f(b), f(c)) for a, b, c in tris]


def volume(tris):
    """Signed volume of a closed triangle mesh (mm3)."""
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return v / 6.0


def weld(tris, tol=1e-4):
    """-> (vertices, faces) with coincident vertices merged and degenerate faces dropped."""
    index, verts, faces = {}, [], []
    inv = 1.0 / tol
    for tri in tris:
        ids = []
        for p in tri:
            key = (round(p[0] * inv), round(p[1] * inv), round(p[2] * inv))
            i = index.get(key)
            if i is None:
                i = index[key] = len(verts)
                verts.append(p)
            ids.append(i)
        if ids[0] != ids[1] and ids[1] != ids[2] and ids[0] != ids[2]:
            faces.append(tuple(ids))
    return verts, faces


def open_edges(tris, tol=1e-4):
    """Number of mesh edges not shared by exactly two triangles (0 = watertight, manifold)."""
    _, faces = weld(tris, tol)
    count = {}
    for f in faces:
        for i in range(3):
            e = (f[i], f[(i + 1) % 3])
            k = (min(e), max(e))
            count[k] = count.get(k, 0) + 1
    return sum(1 for n in count.values() if n != 2)


# ----------------------------------------------------------------------------------------------- 3MF
_CT = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
       '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def write_3mf(path, objects, title="RR part"):
    """objects: list of (name, tris) or (name, tris, (tx, ty, tz)). Coordinates in mm, +z up, bed at z = 0."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
           f'<metadata name="Title">{title}</metadata>\n<metadata name="Application">RR mechanical/tools/mesh_io.py</metadata>\n<resources>\n']
    items = []
    for n, obj in enumerate(objects, start=1):
        name, tris = obj[0], obj[1]
        t = obj[2] if len(obj) > 2 else (0.0, 0.0, 0.0)
        verts, faces = weld(tris)
        out.append(f'<object id="{n}" name="{name}" type="model"><mesh><vertices>\n')
        out.append("".join(f'<vertex x="{v[0]:.5f}" y="{v[1]:.5f}" z="{v[2]:.5f}"/>\n' for v in verts))
        out.append("</vertices><triangles>\n")
        out.append("".join(f'<triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>\n' for f in faces))
        out.append("</triangles></mesh></object>\n")
        items.append(f'<item objectid="{n}" transform="1 0 0 0 1 0 0 0 1 {t[0]:.5f} {t[1]:.5f} {t[2]:.5f}"/>\n')
    out.append("</resources>\n<build>\n" + "".join(items) + "</build>\n</model>\n")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", "".join(out))


# ----------------------------------------------------------------------------------------------- CadQuery bridge
def tessellate_to_tris(shape, tol=0.05, ang=0.3):
    """CadQuery Shape -> triangle list (linear deflection tol mm, angular deflection ang rad)."""
    verts, faces = shape.tessellate(tol, ang)
    pts = [(v.x, v.y, v.z) for v in verts]
    return [(pts[a], pts[b], pts[c]) for a, b, c in faces]
