# chassis_escape - routing test on a copy of RR-CHS-MAIN

Copy (2026-11-27) of the inputs of `electronics/chassis_main/` (board.py, overrides.py, placement.py,
placement_auto.py, design/circuit.py); the original directory is not touched. Only change: `placement.py`
-> `board.route(passes=200, threads=3, timeout=900, retries=2, escape="auto", finisher=True, optimizer=False)`.

    python3 tools/eda/rrkicad.py build tools/eda/tests/chassis_escape/board.py --budget 2400

Results: tools/eda/STATUS.md.
