# RR-HEAD-ACQ - status

Updated: 2026-11-27 (stage 3, review fixes; head electronics).  Overall: **FAIL** (not routed) - see C.

| Deliverable | State | Evidence |
|---|---|---|
| A. Schematic | **done** - 1095/1095 records (1085 stage 1 + 10 stage 3), 31 sheets, ERC 0 errors / 8 warnings (the same 8 reviewed pin_to_pin warnings: lane-mux GND inputs S6/S8 against the PWR_FLAG); tool cross-check OK; `scripts/netcheck.py`: KiCad netlist = circuit.py + exactly the S3 overrides (39 pin moves, 21 value changes, 10 added parts), 0 problems; `python3 overrides.py`: stage-1 self-check re-run on the overridden netlist PASS, lanes identical | `out/RR-HEAD-ACQ-schematic.pdf`, `reports/netlist_vs_circuit.json`, `reports/overrides_applied.json` |
| B. Placement | **done (stage 3)** - `build --no-route`: 0 courtyard overlaps, DRC 0 errors (3 waivers, same kinds as stage 2 + the frame-track waiver), parity 0, ERC 0 / 8; `scripts/placecheck.py` 0 problems besides the stage-2 J2601 wall note; heights max 6.0 mm, nothing on the bottom; plane fan-out 857 vias, 138 plane pads without a via | `scripts/placecheck.py`, `reports/summary.json` |
| C. Routing | **not routed.** Stage 3 changed the stack-up (In3 is now a power plane, In4 GND) and the placement of the J1 landing, the lane-can clips, the frame / shield parts and added a part per channel inside every can: **the whole stage-2 partial routing is invalidated** (the lead's 1 h 45 min run, 340 open, was on the old stack-up: 1035 of its routed items were on In3, which no longer carries signals; the stored lane routes in `route/blocks.json` are stale - the block signatures changed - and are ignored by the tool). `route/RR-HEAD-ACQ.ses` is kept but does not match the new DSN. The `--no-route` board has **1468 connections open (not routed)**. The HV_BUS riser to C2213 was never placed (stage 2 note, unchanged). | `reports/summary.json` |
| D. README / CRs | done | `README.md`, `STAGE2_CHANGE_REQUESTS.md` section "Stage 3" |

Stage 3 changes (details and IDs in `STAGE2_CHANGE_REQUESTS.md`):
* Netlist: monitor taps 10 k at op-amp outputs (S3-01); MON_LANE_EN off state for all lane muxes via TCA9534 P7 + R2418 (S3-02); frame-bond fuse F2801
  and frame-potential monitor on the idle MON_BUS (S3-03); 47 nF in series with R_PZ in every channel (S3-04); per-hole frame nets, C2802 to H8 (S3-05).
* Placement: J2001/J2601 7 mm forward (IB-61), heater cell and power entry compressed in front of them, side-wall can clips moved (all lanes), frame bond
  and J1 shield parts at H1, J2 shield parts at H3, HF frame capacitors at H2/H5/H6/H8, plug keep-out; drain pads TP2004/TP2501 at the landings (IB-57).
* Stack-up F / GND / sig / PWR / GND / B (review M6).
* Analysis: `electronics/analysis/head_afe_budget.md` section 13, calculator tables T13-T17.

To finish: route again from scratch on the new stack-up (3 signal layers; budgeted runs, not part of this stage), hand pre-routes of the J1 landing
heater loop (now 7 mm further forward), and head mechanical acceptance of CR-M06..M08.
