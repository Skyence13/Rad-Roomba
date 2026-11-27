"""Exports of the RR-X build: STEP/STL/3MF of every printed part IN PRINT ORIENTATION (+Z up, bed at z = 0), STEP (+DXF
for flat parts) of every fabricated part, the full-assembly STEP in base_link, and the parts table used by the documents."""
from __future__ import annotations

import csv
import json
import sys

import cadquery as cq

from mechanical.common import params as P

from . import dims as D
from .util import OUT, ROOT, bounds

sys.path.insert(0, str(ROOT.parent / "tools"))
import export_parts as X  # noqa: E402

FAB_FLAT = {"chassis_plate": (0, 0, 0), "bridge_tray": (0, 0, 0), "screw_ring": (90, 0, 0), "grip_side_plate": (90, 0, 0), "caster_disc": (0, 0, 0),
            "caster_shim": (0, 0, 0), "latch_arm": (0, 0, 0), "tray_base": (0, 0, 0)}


def unique_parts(parts, kind):
    seen, out = {}, []
    for p in parts:
        if p.kind != kind:
            continue
        if p.pn in seen:
            seen[p.pn]["qty"] += 1
            seen[p.pn]["instances"].append(p.name)
            continue
        rec = {"part": p, "qty": 1, "instances": [p.name], "file": p.name if p.pn[-1] in "LR" or not p.name[-1].isdigit() else p.name.rstrip("0123456789").rstrip("_")}
        base = p.name
        for suf in ("_L", "_R"):
            if base.endswith(suf) and not p.pn.endswith(suf[1]):
                base = base[:-2]
        if kind == "printed" and base.startswith("tof_clip"):
            base = "tof_clip"
        rec["file"] = base.rstrip("0123456789").rstrip("_") if base[-1].isdigit() and not p.pn[-1].isdigit() is False and kind != "printed" else base
        seen[p.pn] = rec
        out.append(rec)
    return out


def mass_of(p):
    if p._mass is not None:
        return p._mass
    m = D.MAT.get(p.material)
    if not m:
        return 0.0
    return p.volume / 1000.0 * m["rho"] * m["fill"] / 1000.0


def export_all(parts, meshes=True, log=print):
    table = []
    for rec in unique_parts(parts, "printed"):
        p = rec["part"]
        shape = p.local if p.local is not None else p.shape
        info = X.export_part(shape, rec["file"], OUT, p.orient or (0, 0, 0), mesh=meshes)
        info.update(pn=p.pn, kind="printed", material=p.material, qty=rec["qty"], instances=rec["instances"], group=p.group, print_note=p.print_note,
                    mass_each_g=round(mass_of(p) * 1000, 1), note=p.note)
        table.append(info)
        log(f"  {p.pn:9s} {rec['file']:22s} {info['bbox_print']}  {info['bed_fit']:8s} open_edges={info.get('open_edges')}")
    (OUT / "dxf").mkdir(parents=True, exist_ok=True)
    for rec in unique_parts(parts, "fabricated"):
        p = rec["part"]
        key = next((k for k in FAB_FLAT if p.name.startswith(k)), None)
        orient = FAB_FLAT.get(key, (0, 0, 0))
        info = X.export_part(p.shape, rec["file"], OUT / "fabricated", orient, mesh=False)
        info.update(pn=p.pn, kind="fabricated", material=p.material, qty=rec["qty"], instances=rec["instances"], group=p.group, note=p.note,
                    mass_each_g=round(mass_of(p) * 1000, 1), dxf=None)
        if key:
            s = X.to_print_orientation(p.shape, orient)
            try:
                sec = cq.Workplane("XY").add(s).section(s.BoundingBox().zlen / 2)
                cq.exporters.exportDXF(sec, str(OUT / "dxf" / f"{rec['file']}.dxf"))
                info["dxf"] = f"out/dxf/{rec['file']}.dxf"
            except Exception as e:  # noqa: BLE001
                info["dxf"] = f"FAILED: {e}"
        table.append(info)
        log(f"  {p.pn:9s} {rec['file']:22s} {info['bbox_print']}  dxf={info['dxf']}")
    (OUT / "parts_table.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
    return table


def export_plate_holes():
    from .structure import plate_holes, sole_screw_xy
    rows = plate_holes() + [(x, y, D.CLEAR["M3"], "csk_bottom", "lower-hull sole ring M3 (insert in the hull)") for x, y in sole_screw_xy()]
    (OUT / "dxf").mkdir(parents=True, exist_ok=True)
    with open(OUT / "dxf" / "chassis_plate_holes.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["n", "x_base_link_mm", "y_base_link_mm", "diameter_mm", "operation", "purpose"])
        for i, (x, y, d, kind, why) in enumerate(rows, 1):
            w.writerow([i, round(x, 2), round(y, 2), d, kind, why])
    return len(rows)


def export_assembly(parts, path=None):
    path = path or OUT / "RRX_assembly.step"
    asm = cq.Assembly(name="RRX_prototype_assembly")
    groups = {}
    real_head = (ROOT.parent / "head" / "prototype" / "RR-HD-X-000_head_assembly_prototype.step").exists()
    for p in parts:
        if real_head and (p.name == "head_envelope" or p.name.startswith("head_shoe_")):
            continue
        g = groups.setdefault(p.subasm, cq.Assembly(name="sub_" + p.subasm))
        g.add(p.shape, name=p.name, color=cq.Color(p.color) if isinstance(p.color, str) else p.color)
    for g in groups.values():
        asm.add(g)
    real = ROOT.parent / "head" / "prototype" / "RR-HD-X-000_head_assembly_prototype.step"
    head, label = (real, "head_RR-HD-X-000_prototype_from_mechanical_head") if real.exists() else (P.OUT / "RR_E_head_layout.step", "head_layout_placeholder_from_mechanical_common")
    if head.exists():
        try:
            objs = cq.importers.importStep(str(head)).vals()
            comp = cq.Compound.makeCompound([o for o in objs if isinstance(o, cq.Shape)])
            asm.add(comp, name=label, color=cq.Color(0.2, 0.3, 0.32, 1.0))
            bb = comp.BoundingBox()
            print(f"  head in the assembly: {head.name}, bbox x {bb.xmin:.1f}..{bb.xmax:.1f}, z {bb.zmin:.1f}..{bb.zmax:.1f}")
        except Exception as e:  # noqa: BLE001
            print(f"  head STEP not added: {e}")
    asm.export(str(path))
    return path
