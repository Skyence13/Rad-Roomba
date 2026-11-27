# rrkicad generator tests (not product designs)

| dir | what | run |
|---|---|---|
| `stress/` | synthetic 4-layer 100 x 80 mm board, 150 parts, 146 auto-arranged: LQFP-64, QFN-48 0.5 mm, 20 SOT-23-5, multi-unit SOIC-8, local symbol + footprint, DNP, cut-out, keep-out, pre-route, split power plane | `python3 tools/eda/rrkicad.py build tools/eda/tests/stress/board.py` (10-20 min) |
| `stress6/` | same circuit on 6 layers, MCU decoupling on the bottom side | `... build tools/eda/tests/stress6/board.py` (1.5-3 min) |
| `replicate/` | two identical lanes via `board.replicate()` (placement + routes), `waive()` / `severity()` | `... build tools/eda/tests/replicate/board.py` (25 s; build twice to freeze the block routes) |
| `import_chassis/`, `import_panel/`, `import_head_acq/` | `rrkicad.importer.from_circuit()` on the three stage-1 `circuit.py` files, schematic + ERC only | `... sch tools/eda/tests/import_chassis/board.py` (3-17 s) |
| `scale500/` | synthetic 6-layer 160 x 100 mm, 493 parts (LQFP-100, LQFP-64, 2 QFN, 2 TSSOP, 40 SOT-23(-5), 13 edge connectors, two-sided, 0.8-1.5 mm power nets) | `... build tools/eda/tests/scale500/board.py` - generation tested only, not routed (the real boards below were the better evidence) |
| `head_escape/` | copy of the inputs of `electronics/head_acq/` (1085 parts) with escape on - routing test | `... build tools/eda/tests/head_escape/board.py --budget 2400` (about 70 min) |
| `chassis_escape/` | copy of the inputs of `electronics/chassis_main/` (771 parts) - routing test | `... build tools/eda/tests/chassis_escape/board.py --budget 2400` |

Results: `<dir>/reports/summary.json` (builds), `<dir>/route/progress.log` (one line per autorouter run), or
`reports/erc.*` + `reports/import_report.json` (imports). Measured results and their history: `tools/eda/STATUS.md`
and "Stress test and practical limits" in `tools/eda/README.md`.
