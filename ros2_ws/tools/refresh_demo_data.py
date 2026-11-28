#!/usr/bin/env python3
"""Refresh the packaged demonstration calibration, site profile and calibration-record schema from analysis/radiometry.

    python3 tools/refresh_demo_data.py            # copy (byte-identical) into src/rr_core/rr_core/data/
    python3 tools/refresh_demo_data.py --check    # exit 1 if a packaged file differs from its source

The packaged files are never edited by hand: `rr_core/test/test_demo_data.py` fails when they differ from the analysis
directory (the owner of these records), as the contract snapshot test does for the contract.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
REPO = WS.parent
SRC = REPO / "analysis" / "radiometry"
DST = WS / "src" / "rr_core" / "rr_core" / "data"
FILES = {"demo_calibration.json": SRC / "demo_calibration.json",
         "demo_site_profile_ore.json": SRC / "demo_site_profile_ore.json",
         "calibration_record.schema.json": SRC / "schemas" / "calibration_record.schema.json"}


def stale():
    return [name for name, src in FILES.items() if not (DST / name).exists() or (DST / name).read_bytes() != src.read_bytes()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    st = stale()
    if a.check:
        print("stale: " + ", ".join(st) if st else "packaged demonstration data up to date")
        return 1 if st else 0
    for name in st:
        (DST / name).write_bytes(FILES[name].read_bytes())
        print(f"refreshed {DST / name}")
    if not st:
        print("packaged demonstration data up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
