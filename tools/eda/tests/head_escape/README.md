# head_escape - routing test on a copy of RR-HEAD-ACQ

Copy (2026-11-27) of the inputs of `electronics/head_acq/` (board.py, layout.py, layout_frozen.json, libs.py,
overrides.py, design/circuit.py, scripts/fp_geometry.json, route/blocks.json) - the original directory is not
touched. Only change: `layout.py` -> `board.route(escape=True, finisher=True, retries=2, timeout=900, passes=200,
fallback_strategies=continue)`. Run:

    python3 tools/eda/rrkicad.py build tools/eda/tests/head_escape/board.py --budget 2400

Results: see tools/eda/STATUS.md.
