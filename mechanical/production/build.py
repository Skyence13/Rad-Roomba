#!/usr/bin/env python3
"""RR-P production body (5-25 units/year): regenerate every output from the shared RR-X model with RR_BUILD=production
and run the prototype check suite on the production assembly.

    python -m mechanical.production.build      (from the repository root; or ./mechanical/production/build.sh)
    options: --no-drawings  --no-assembly-step

Outputs (tracked): step/ (every made part, base_link), assembly/ (per-subassembly STEP), dxf/ (flat parts + hole tables),
drawings/RRP_fabrication_drawings.pdf, bom_production.csv, hardware_production.md, process_plan.md, assembly_sequence.md,
mass_cg.md, comparison.md, production_report.md.  Untracked (out/, .gitignore): BREP cache, full assembly STEP, checks.json.
Exit status is non-zero if any check fails.
"""
from __future__ import annotations

import os

os.environ["RR_BUILD"] = "production"          # must precede every rrx import

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
STEP_LIMIT_MB = 50.0


def _fit(size, env):
    """True if an axis-aligned box `size` fits `env` in any of the 6 axis permutations."""
    import itertools
    return any(all(a <= b for a, b in zip(p, env)) for p in itertools.permutations(size))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-drawings", action="store_true")
    ap.add_argument("--no-assembly-step", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    import cadquery as cq

    from mechanical.common import params as P
    from mechanical.prototype_x1c.rrx import assembly, checks, export, util
    from mechanical.prototype_x1c.rrx import production as PR
    from mechanical.prototype_x1c.rrx.util import OUT

    from . import docs
    assert util.BUILD == "production" and OUT == HERE / "out", "build switch not applied"
    OUT.mkdir(exist_ok=True)
    print("[1/7] building parts (RR_BUILD=production)", flush=True)
    parts = assembly.build()
    used_prefix = {n.rsplit("_", 1)[0] for n in util.USED}
    stale = [f for f in util.CACHE.glob("*.brep") if f.name not in util.USED and f.name.rsplit("_", 1)[0] in used_prefix]
    for f in stale:
        f.unlink()
    print(f"  BREP cache: {len(util.USED)} entries used, {len(stale)} stale removed", flush=True)
    bad = [p.name for p in parts if not p.shape.isValid() or (p.kind in ("printed", "fabricated") and len(p.shape.Solids()) != 1)]

    print(f"[2/7] exporting part STEP ({time.time() - t0:.0f} s)", flush=True)
    table = export.export_all(parts, meshes=False, log=lambda *a: None)       # out/fabricated (+ tray prints): parts table for the checks
    step_dir = HERE / "step"
    step_dir.mkdir(exist_ok=True)
    for f in step_dir.glob("*.step"):
        f.unlink()
    made = docs.unique_made(parts)
    for rec in made:
        p = rec["part"]
        cq.exporters.export(cq.Workplane("XY").add(p.shape), str(step_dir / f"{p.pn}_{rec['file']}.step"))
    print(f"  {len(made)} unique made parts -> step/ (base_link)", flush=True)
    asm_info = {}
    if not args.no_assembly_step:
        print(f"[3/7] assembly STEP ({time.time() - t0:.0f} s)", flush=True)
        asm_info = docs.export_assemblies(parts, STEP_LIMIT_MB)
        for k, v in asm_info.items():
            print(f"  {k}: {v['path']} {v['mb']:.1f} MB{' (over the limit: out/, untracked)' if v['untracked'] else ''}")

    print(f"[4/7] checks ({time.time() - t0:.0f} s)", flush=True)
    R = checks.run_all(parts, table)
    R["multi_body_or_invalid_parts"] = bad
    # production replacements / additions to the summary (same suite otherwise)
    R["summary"].pop("every printed part fits the X1C bed in its print orientation", None)
    R["summary"].pop("printed-part meshes watertight (info: the owner slices from STEP)", None)
    env_rows, env_ok = [], True
    for rec in made:
        p = rec["part"]
        env, label = docs.process_envelope(p)
        if env is None:
            continue
        b = p.bb
        size = [round(b[3] - b[0], 1), round(b[4] - b[1], 1), round(b[5] - b[2], 1)]
        ok = _fit(size, env)
        env_ok &= ok
        env_rows.append({"pn": p.pn, "part": rec["file"], "process": p.process_class, "size": size, "envelope": list(env), "envelope_label": label, "fits": ok})
    R["process_envelope"] = env_rows
    one = {n: next((len(p.shape.Solids()) for p in parts if p.name == n), 0) for n in ("lower_hull", "upper_shell")}
    R["summary"]["every printed/fabricated part is one valid solid"] = [not bad, "all single valid solids" if not bad else str(bad)]
    R["summary"]["every made part fits its process envelope (SLS / CNC / sheet / cast, UNVERIFIED supplier sizes)"] = [env_ok, f"{sum(r['fits'] for r in env_rows)}/{len(env_rows)} fit"]
    R["summary"]["lower hull and lid are one piece each"] = [all(v == 1 for v in one.values()), str(one)]
    tray_bed = [r for r in R["bed_fit"] if r["verdict"] == "NO"]
    R["summary"]["shop-aid prints (transport tray) fit the X1C bed"] = [not tray_bed, f"{len(R['bed_fit'])} parts"]
    for k, (good, txt) in R["summary"].items():
        print(f"  {'PASS' if good else 'FAIL'}  {k}: {txt[:150]}")
    ok = all(v[0] for v in R["summary"].values())
    (OUT / "checks.json").write_text(json.dumps(R, indent=1, default=str), encoding="utf-8")
    from mechanical.prototype_x1c.rrx import routes as RT
    RT.write_yaml(R["routes"], HERE / "cable_routes.yaml", "production (RR-P)")

    print(f"[5/7] documents ({time.time() - t0:.0f} s)", flush=True)
    proto = docs.prototype_reference()
    docs.write_bom(parts, made)
    hw = docs.write_hardware()
    docs.write_process_plan(made)
    docs.write_assembly_sequence()
    docs.write_mass(R)
    docs.write_comparison(parts, made, R, hw, proto)
    print(f"[6/7] DXF ({time.time() - t0:.0f} s)", flush=True)
    nd = docs.write_dxf(parts)
    print(f"  {nd} DXF files with hole tables", flush=True)
    sheets = 0
    if not args.no_drawings:
        print(f"[7/7] fabrication drawings ({time.time() - t0:.0f} s)", flush=True)
        from . import drawings
        sheets = drawings.fab(parts, made)
        print(f"  {sheets} sheets -> drawings/RRP_fabrication_drawings.pdf", flush=True)
    docs.write_report(R, made, asm_info, sheets, f"{time.time() - t0:.0f} s")
    print(f"done in {time.time() - t0:.0f} s -> {'ALL CHECKS PASS' if ok else 'CHECK FAILURES (see production_report.md)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
