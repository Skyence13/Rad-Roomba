#!/usr/bin/env python3
"""Recompute one decision cell from a mission archive plus calibration and profile files (MODEL.md rev 5 section 8).

    python3 tools/recompute_cell.py <run_dir> <ix> <iy> [--calibration cal.json ...] [--profile profile.json]

Runs inside the container (tools/_common.sh rr_docker_run) or anywhere rr_core is importable.  See rr_core/recompute.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "rr_core"))
from rr_core.recompute import main  # noqa: E402

main()
