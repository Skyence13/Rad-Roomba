#!/usr/bin/env python3
"""RR-X prototype body: regenerate every output and run the checks.

    python -m mechanical.prototype_x1c.build            (from the repository root; or ./mechanical/prototype_x1c/build.sh)
    options: --no-images  --no-assembly-step  --no-checks  --no-mesh

Stages: parts (cached BREP in out/cache) -> per-part STEP/STL/3MF in print orientation + fabricated STEP/DXF -> assembly STEP
-> checks (out/checks.json, out/prototype_report.md) -> plates.yaml, print_schedule.md, BOM, joints/, img/.
Exit status is non-zero if a check in the summary fails.
"""
from __future__ import annotations

import argparse
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--no-assembly-step", action="store_true")
    ap.add_argument("--no-checks", action="store_true")
    ap.add_argument("--no-mesh", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    from .rrx import assembly, checks, docs, export, structure
    from .rrx.util import OUT, Part
    OUT.mkdir(exist_ok=True)
    print("[1/6] building parts", flush=True)
    parts = assembly.build()
    bad = [p.name for p in parts if not p.shape.isValid() or (p.kind in ("printed", "fabricated") and len(p.shape.Solids()) != 1)]
    if bad:
        print("  WARNING invalid or multi-body parts:", bad)
    print(f"[2/6] exporting parts ({time.time() - t0:.0f} s)", flush=True)
    extra = [Part(f"RRX-P02{tag}", f"receiver_channel_fitcheck_{tag}", structure.receiver_channel(s), "printed", "PAHT-CF", "receiver_option", orient=(180, 0, 0), hard=False,
                  print_note="plate face on the bed (upside-down); no supports; FIT CHECK ONLY, the datum part is the machined RRX-F02", note="optional") for tag, s in (("L", 1), ("R", -1))]
    table = export.export_all(parts + extra, meshes=not args.no_mesh)
    nh = export.export_plate_holes()
    print(f"  chassis plate hole table: {nh} holes", flush=True)
    if not args.no_assembly_step:
        print(f"[3/6] assembly STEP ({time.time() - t0:.0f} s)", flush=True)
        export.export_assembly(parts)
    ok = True
    if not args.no_checks:
        print(f"[4/6] checks ({time.time() - t0:.0f} s)", flush=True)
        R = checks.run_all(parts, table)
        R["multi_body_or_invalid_parts"] = bad
        R["summary"]["every printed/fabricated part is one valid solid"] = [not bad, "all single valid solids" if not bad else str(bad)]
        for k, (good, txt) in R["summary"].items():
            print(f"  {'PASS' if good else 'FAIL'}  {k}: {txt[:150]}")
        ok = all(v[0] for v in R["summary"].values())
    print(f"[5/6] documents ({time.time() - t0:.0f} s)", flush=True)
    docs.write_plates(table)
    docs.write_bom(parts, table)
    if not args.no_images:
        print(f"[6/6] images and joint sections ({time.time() - t0:.0f} s)", flush=True)
        docs.write_images(parts)
        docs.write_joints(parts)
    docs.write_assembly(parts)
    if not args.no_checks:
        docs.write_report(R, table, parts, f"{time.time() - t0:.0f} s (BREP cache {'warm' if time.time() - t0 < 400 else 'cold or partly cold'})")
    print(f"done in {time.time() - t0:.0f} s -> {'ALL CHECKS PASS' if ok else 'CHECK FAILURES (see out/prototype_report.md)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
