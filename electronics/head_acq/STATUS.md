# RR-HEAD-ACQ stage 2 - status

Updated: 2026-11-27 02:05 UTC (stage-2 engineer).  Overall: **FAIL** (routing incomplete) - see C.

| Deliverable | State | Evidence |
|---|---|---|
| A. Schematic | **done** - 1085/1085 records (77 DNP / pad-only flagged), 31 sheets (lanes = 4 identical sets of 5 sheets), ERC 0 errors / 8 warnings (reviewed); tool cross-check OK; netlist == design/circuit.py (2987 pins, 581 nets, values/MPN/manufacturer/DNP) | `out/RR-HEAD-ACQ-schematic.pdf`, `reports/erc_warnings_review.md`, `reports/netlist_vs_circuit.json` |
| B. Placement | **done** - `build --no-route`: 0 courtyard overlaps, 0 DRC errors other than unconnected, parity 0. 6 layers, lane 0 laid out + 3 replicated lanes, planes / splits / island + barrier / keep-outs / net classes; top courtyards 8608 mm2 = 27.5 % of the board + 4 cans; bottom empty; max height 6.0 mm | `out/RR-HEAD-ACQ-placement.png`, `out/RR-HEAD-ACQ-placement-lane0.png`, `out/RR-HEAD-ACQ.step`, `reports/fit_check.json` |
| C. Routing | **incomplete**: 1090 connections open on 212 nets after one 540 s Freerouting run (second build; lane-0 block routes replicated to lanes 1-3 = 444 locked items); DRC 0 errors, parity 0. Pre-routes (1947 locked items incl. plane fan-out) all intact | `reports/open_connections.md`, `reports/summary.json`, `route/` |
| D. README / CRs | done | `README.md`, `STAGE2_CHANGE_REQUESTS.md` |

Routing runs: build 1 (whole board, one 1075 s pass): 1530 -> 1113 unrouted (Freerouting count); build 2 (blocks frozen
and replicated): 1475 -> 1099 unrouted in 537 s, KiCad 1090 open; the automatic continue run crashed in the tool
(`pcb._edge_guard`: 'SwigPyObject' has no attribute 'NewOutline'), so `retries=0` is set now.

To finish: many more router passes (~9-18 min each at this size) or hand pre-routing of the lane block, the MCU and
DAC fan-outs (escape routing for the LQFP-100 / WQFN-16 when the tool's escape feature is documented as working).
Mechanical fit depends on CR-M01..M05 (head mechanical).
