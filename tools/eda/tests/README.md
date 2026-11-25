# rrkicad tests

`stress/board.py` — synthetic 4-layer 100 x 80 mm board with 150 parts (STM32G474 LQFP-64,
STM32F103 QFN-48 0.5 mm, 20 SOT-23-5 opamps, SOIC-8 multi-unit opamp, SOT-223 LDO, 110+ 0402/0603/0805
passives, 2x10 headers, JST GH, screw terminal, local symbol + footprint, DNP part, cut-out, keep-out,
pre-routed track, split power plane).  146 parts are auto-arranged.  Not a product design.

    python3 tools/eda/rrkicad.py build tools/eda/tests/stress/board.py

Results and measured timings: `stress/reports/summary.json` and the "Stress test" section of
`tools/eda/README.md`.
