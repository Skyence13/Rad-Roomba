"""Importer smoke test: converts electronics/head_acq/design/circuit.py (stage-1, tool-neutral)
into a rrkicad Board and generates the schematic.  NOT the chassis board design - no placement, no rails.

    python3 tools/eda/rrkicad.py sch tools/eda/tests/import_chassis/board.py
"""
import json
import os

from rrkicad import Board
from rrkicad.importer import from_circuit

REPO = os.environ.get("RR_REPO", os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
board = Board("IMPORT-HEAD", title="circuit.py importer test (head_acq)", rev="X", date="2026-11-26",
              docnum="RR-EL-TEST3", layers=6)
report = from_circuit(board, os.path.join(REPO, "electronics/head_acq/design/circuit.py"), allow_missing=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports"), exist_ok=True)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "import_report.json"), "w") as f:
    json.dump(report, f, indent=1)
board.outline_rect(326, 96, radius=2, origin="corner")
