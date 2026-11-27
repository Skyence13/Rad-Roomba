# RR-HEAD-ACQ stage 2 - status

Updated: 2026-11-27 (stage-2 engineer).

| Deliverable | State | Evidence |
|---|---|---|
| A. Schematic | **done** - 1085/1085 records, 31 sheets (lanes = 4 identical sets of 5 sheets), ERC 0 errors / 8 warnings (reviewed); netlist identical to design/circuit.py | `out/RR-HEAD-ACQ-schematic.pdf`, `reports/erc_warnings_review.md`, `reports/netlist_vs_circuit.json` |
| B. Placement | **done for `build --no-route`**: 0 courtyard overlaps, 0 DRC errors other than unconnected, parity 0; lane 0 laid out, lanes 1-3 replicated; 6 layers; planes/splits/keep-outs/net classes; top courtyard fill 27.5 % (+ 4 cans), bottom empty; heights <= 6.0 mm | `out/RR-HEAD-ACQ-placement*.png`, `out/RR-HEAD-ACQ.step`, `reports/fit_check.json` |
| C. Routing | first Freerouting run in progress (pre-routes: HV trunk/drops/riser, HVF links, anode stubs) | `route/`, `reports/summary.json` |
| D. README / CRs | written | `README.md`, `STAGE2_CHANGE_REQUESTS.md` |

Mechanical fit depends on CR-M01..M05 (head mechanical).
