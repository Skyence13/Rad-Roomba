"""CadQuery export helper shared by the mechanical work packages.

export_part(shape, name, out_dir, orient=(rx, ry, rz)) rotates the part into its PRINT orientation (Euler angles in
degrees applied about the fixed X, then Y, then Z axes), drops it onto z = 0 with its bounding-box minimum corner at
the origin, and writes
    <out_dir>/step/<name>.step      B-rep in print orientation, +Z up, bed plane z = 0
    <out_dir>/stl/<name>.stl        binary STL, same orientation (what slice_plates.py consumes)
    <out_dir>/3mf/<name>.3mf        plain 3MF, same orientation
and returns a dict with the bounding box, volume, triangle count, watertightness and the bed-fit verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cadquery as cq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mesh_io as M  # noqa: E402

BED = (256.0, 256.0, 256.0)          # Bambu Lab X1 Carbon nominal build volume
STOCK_Z = 250.0                       # printable height of the stock 0.4 mm machine preset
MARGIN = 3.0                          # kept free at every plate edge
EXCLUDE = (18.0, 28.0)                # front-left corner the X1C cannot print on


def to_print_orientation(shape, orient=(0, 0, 0)):
    rx, ry, rz = orient
    s = shape
    for ang, axis in ((rx, (1, 0, 0)), (ry, (0, 1, 0)), (rz, (0, 0, 1))):
        if ang:
            s = s.rotate(cq.Vector(0, 0, 0), cq.Vector(*axis), ang)
    bb = s.BoundingBox()
    return s.translate(cq.Vector(-bb.xmin, -bb.ymin, -bb.zmin))


def bed_fit(size, margin=MARGIN):
    """-> (verdict, note). verdict: OK | MARGINAL | NO."""
    x, y, z = size
    lim_xy = BED[0] - 2 * margin
    a, b = max(x, y), min(x, y)
    if a > lim_xy or z > BED[2] - margin:
        return "NO", f"{x:.1f} x {y:.1f} x {z:.1f} exceeds {lim_xy:.0f} x {lim_xy:.0f} x {BED[2] - margin:.0f}"
    notes = []
    if z > STOCK_Z - margin:
        notes.append(f"height {z:.1f} > {STOCK_Z - margin:.0f} (stock preset prints 250 mm; raise printable_height or re-orient)")
    if a > lim_xy - 10:
        notes.append(f"long side {a:.1f} within 10 mm of the usable {lim_xy:.0f} mm: no room for a brim")
    if x > lim_xy - EXCLUDE[0] and y > lim_xy - EXCLUDE[1]:
        notes.append("footprint reaches the 18 x 28 mm front-left exclusion corner: check the first layer outline there")
    return ("MARGINAL" if notes else "OK"), "; ".join(notes)


def export_part(shape, name, out_dir, orient=(0, 0, 0), tol=0.06, ang=0.25, step=True, mesh=True):
    out_dir = Path(out_dir)
    s = to_print_orientation(shape, orient)
    bb = s.BoundingBox()
    size = (bb.xlen, bb.ylen, bb.zlen)
    info = {"name": name, "orient_euler_xyz_deg": list(orient), "bbox_print": [round(v, 2) for v in size], "volume_cm3": round(s.Volume() / 1000.0, 2)}
    info["bed_fit"], info["bed_note"] = bed_fit(size)
    if step:
        (out_dir / "step").mkdir(parents=True, exist_ok=True)
        cq.exporters.export(cq.Workplane("XY").add(s), str(out_dir / "step" / f"{name}.step"))
    if mesh:
        tris = M.tessellate_to_tris(s, tol, ang)
        (out_dir / "stl").mkdir(parents=True, exist_ok=True)
        (out_dir / "3mf").mkdir(parents=True, exist_ok=True)
        M.write_stl(out_dir / "stl" / f"{name}.stl", tris)
        M.write_3mf(out_dir / "3mf" / f"{name}.3mf", [(name, tris)], title=name)
        info["triangles"] = len(tris)
        info["open_edges"] = M.open_edges(tris, 1e-3)
        info["mesh_volume_cm3"] = round(abs(M.volume(tris)) / 1000.0, 2)
    return info
