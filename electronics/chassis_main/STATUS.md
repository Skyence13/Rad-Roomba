# RR-CHS-MAIN stage 2 — status

Updated as work proceeds.

| Step | State |
|---|---|
| A. RR-PANEL full flow | DONE — PASS (ERC 0/0, DRC 0/0, unconnected 0, parity 0), all outputs in `electronics/panel/out/` |
| B. Chassis schematic | DONE — 771 parts (768 from circuit.py + 3 added by S2-01), 432 nets, 18 A3 sheets; ERC 0 errors / 0 warnings; netlist cross-check OK (771 components, all pins); every part has value, footprint, MPN, manufacturer; `out/RR-CHS-MAIN-schematic.pdf` |
| C. Placement (`build --no-route`) | DONE — every part placed (148 explicit by hand + 623 auto-arranged passives, frozen in `placement_auto.py`); DRC 0 errors (176 warnings: silk, dangling escape vias), parity 0, 0 courtyard overlaps; 499 unconnected (unrouted). Unrouted STEP, renders, assembly PDFs and fit check in `reports/placement/`, `reports/fitcheck.json`, `reports/cable_lengths.json` |
| D. Routing attempt (stage-2 netlist, superseded by stage 3) | DONE (not complete): one Freerouting run 780 s (1 pass, CPU-starved): 1169 → 802 unrouted; routed board saved with planes/fan-out/escape intact; DRC 1 error (via through NT1 net-tie polygon), 145 warnings, parity 0; 802 open (KiCad lists 499: `reports/open_connections.txt`); post stage needed a workaround for a tool crash (README) — FAIL |
| E. Docs | panel README done; chassis README, STAGE2_CHANGE_REQUESTS.md, reports/erc_warnings_review.md written; panel STAGE2_CHANGE_REQUESTS.md written |
| F. Stage 3 (review fixes, 2026-11-27) | Netlist: S3-xx in `overrides.py` (72 parts added, C1/C2/M1/M2/M3/M6 fixes), self-check PASSED. Firmware change list F1-F18 in `STAGE2_CHANGE_REQUESTS.md` §3.1. Safety analysis rewritten (`electronics/analysis/chassis_safety_chain.md`: 73-row fault table, §6.1 no-barrier list), braking tables T8-T11 added. Board: `sch` ERC and `build --no-route` results in README "What is tool-checked"; chain clearance rules enforced by DRC (`RR-CHS-MAIN.kicad_dru`). **Not routed**: the stage-2 routing is superseded. Open: hand placement of the stage-3 parts, firmware F1-F18, harness relabel of W-018.1/.2 |

Files: `board.py` (definition), `overrides.py` (stage-2 deviations S2-xx on top of design/circuit.py), `placement.py` (floorplan, classes, planes, routing), `placement_auto.py` (frozen auto-arranged passives), `tools/` (fit check, cable-length re-estimate, near-distance report, freeze).
