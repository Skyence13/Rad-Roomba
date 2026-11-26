# rrkicad generator tests (not product designs)

| dir | what | run |
|---|---|---|
| `stress/` | synthetic 4-layer 100 x 80 mm board, 150 parts, 146 auto-arranged: LQFP-64, QFN-48 0.5 mm, 20 SOT-23-5, multi-unit SOIC-8, local symbol + footprint, DNP, cut-out, keep-out, pre-route, split power plane | `python3 tools/eda/rrkicad.py build tools/eda/tests/stress/board.py` (5-10 min) |
| `replicate/` | two identical lanes via `board.replicate()`, plus `waive()` / `severity()` | `python3 tools/eda/rrkicad.py build tools/eda/tests/replicate/board.py` (15 s) |

Results: `<dir>/reports/summary.json`; measured timings and limits: "Stress test and practical limits"
in `tools/eda/README.md`. The stress board is expected to FAIL with a few unconnected items unless
its placement is tuned by hand - that is the honest result of fully automatic placement + routing.
