# rrkicad generator tests (not product designs)

| dir | what | run |
|---|---|---|
| `stress/` | synthetic 4-layer 100 x 80 mm board, 150 parts, 146 auto-arranged: LQFP-64, QFN-48 0.5 mm, 20 SOT-23-5, multi-unit SOIC-8, local symbol + footprint, DNP, cut-out, keep-out, pre-route, split power plane | `python3 tools/eda/rrkicad.py build tools/eda/tests/stress/board.py` (15-25 min) |
| `stress6/` | same circuit on 6 layers, MCU decoupling on the bottom side | `... build tools/eda/tests/stress6/board.py` (15-25 min) |
| `replicate/` | two identical lanes via `board.replicate()` (placement + routes), `waive()` / `severity()` | `... build tools/eda/tests/replicate/board.py` (25 s; build twice to freeze the block routes) |
| `import_chassis/`, `import_panel/`, `import_head_acq/` | `rrkicad.importer.from_circuit()` on the three stage-1 `circuit.py` files, schematic + ERC only | `... sch tools/eda/tests/import_chassis/board.py` (3-17 s) |

Results: `<dir>/reports/summary.json` (builds) or `reports/erc.*` + `reports/import_report.json` (imports).
Both stress boards FAIL with a few open connections at the two 0.5 mm-pitch ICs - that is the honest
result of fully automatic placement + routing; see "Stress test and practical limits" in `tools/eda/README.md`.
