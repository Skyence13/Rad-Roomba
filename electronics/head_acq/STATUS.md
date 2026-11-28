# RR-HEAD-ACQ - status

Updated: 2026-11-28 (stage 4: CR-H17 front headers; stage 3 review fixes lead-verified 2026-11-27; head electronics).  Overall: **FAIL** (not routed) - see C.

| Deliverable | State | Evidence |
|---|---|---|
| A. Schematic | **done** - 1095/1095 records (1085 stage 1 + 10 stage 3), 31 sheets, ERC 0 errors / 8 warnings (the same 8 reviewed pin_to_pin warnings: lane-mux GND inputs S6/S8 against the PWR_FLAG); tool cross-check OK; `scripts/netcheck.py`: KiCad netlist = circuit.py + exactly the S3 overrides (39 pin moves, 21 value changes, 10 added parts), 0 problems; `python3 overrides.py`: stage-1 self-check re-run on the overridden netlist PASS, lanes identical | `out/RR-HEAD-ACQ-schematic.pdf`, `reports/netlist_vs_circuit.json`, `reports/overrides_applied.json` |
| B. Placement | **done (stage 3)** - `build --no-route`: 0 courtyard overlaps, DRC 0 errors (3 waivers, same kinds as stage 2 + the frame-track waiver), parity 0, ERC 0 / 8; `scripts/placecheck.py` 0 problems besides the stage-2 J2601 wall note; heights max 6.0 mm, nothing on the bottom; plane fan-out 857 vias, 135 plane pads without a via (stage 4 build) | `scripts/placecheck.py`, `reports/summary.json` |
| C. Routing | **not routed.** Stage 3 changed the stack-up (In3 is now a power plane, In4 GND) and the placement of the J1 landing, the lane-can clips, the frame / shield parts and added a part per channel inside every can: **the whole stage-2 partial routing is invalidated** (the lead's 1 h 45 min run, 340 open, was on the old stack-up: 1035 of its routed items were on In3, which no longer carries signals; the stored lane routes in `route/blocks.json` are stale - the block signatures changed - and are ignored by the tool). `route/RR-HEAD-ACQ.ses` is kept but does not match the new DSN. The `--no-route` board has **1465 connections open (not routed)** (stage 4; 1468 after stage 3). The HV_BUS riser to C2213 was never placed (stage 2 note, unchanged). | `reports/summary.json` |
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

Stage 4 (2026-11-28, CR-H17): front-edge GH headers J2002/J2003/J2004/J2201/J2402 6.25 mm rearward (courtyard v <= 89) and spread along the front
band (J2003 LEFT u 16, J2002 FRONT u 67, J2402 u 91, J2201 u 232, J2004 RIGHT u 310), plug keep-outs in front of each, rail-zone parts and R2019 moved
with them, LOOP net class 0.5 mm; no netlist change. Checks: `overrides.py` self-check PASS; `netcheck.py` 0 problems; ERC 0 errors / 8 warnings;
`build --no-route` DRC 0 errors, parity 0, 0 courtyard overlaps, 1465 unconnected (not routed); `placecheck.py` clean (stage-2 J2601 wall note only).

**Known obstacles to routing (re-checked on the stage-4 build):** (1) the HV_BUS riser to C2213 is still not placed (`reports/preroute_notes.json`:
"no via position next to C2213" - the riser via finder finds no 1.0 mm-clear spot round C2213 pad 1); (2) 135 plane pads without a fan-out via
(`summary.json` routing.plane_fanout.failed; the 135th is the +3V3 pad of the DNP isolator U2503 at the barrier, "no free path") - 134 of them are reported as "long fan-out time cap (600 s) used up", i.e. the tool stopped looking, not
proven impossible; by area: bias block C22xx/U22xx (~25), DACs C23xx/U23xx (~12), regulators U21xx/C21xx (~9), monitor U27xx (~5), MCU (~3), heater
cell, and lane parts (C1x/U1x of lanes 0-3, ~25). Beyond these, known structural limits rather than single obstacles: 3 routing layers (In3 is a
plane since stage 3), fine-pitch escape disabled in this definition (LQFP-100 + four WQFN-16), and the interlock loop now spans the board (~0.65 m).
No new obstacle came from stage 4 (the front band was free).

**Hand-placement / pre-route actions before the long autorouting run (in this order):**
1. C2213 / HV riser: shift C2213 (or its GND neighbour) ~1.5 mm so a 1.0 mm-clear via exists next to pad 1, then pre-route the riser on In2 from the
   trunk via at (138.6, 43.0) and add its via keep-out band (`layout._hv_via_bands` does this once the riser exists).
2. Plane pads: re-run the fan-out with a longer cap (`board.route(long_fanout_seconds=...)`) to separate "time ran out" from "no spot"; then for the
   remaining pads nudge/rotate the passive (0.5-1 mm) or move a decoupling capacitor to the other side of its IC, worst areas first: bias block,
   DAC row (VDD 1 uF / 100 nF at U2301..U2304), regulator cell, lane-0 can (fix once, replicated).
3. Heater loop: hand pre-route HEAD_HTR_P / HTR_PS / HTR_SW / HEAD_HTR_N in the J1 landing (>= 2.5 mm, F.Cu + B.Cu in parallel, feed over return),
   J2001.3/.4 and J2601.1/.2 now at v 17.57.
4. Lane-0 critical routes (layout_guidance section 5: anode input, preamp/fast feedback, FCMP, comparator -> OR -> latch, S3 C_PZ and monitor taps
   at the op-amp outputs), locked, so `replicate()` copies them to lanes 1-3.
5. Fine-pitch escape for U2401 (LQFP-100) and U2301..U2304 (WQFN-16): keep >= 2 mm free round them and enable the tool escape, or hand escape.
6. Long DC/event corridors: MON_BUS + IMON along their corridor, BUSY/ULD/ALPHA/LLD/CLR on B.Cu over In4 GND, the LOOP nets at 0.5 mm along the
   front band away from the AFE strip.
7. Then the budgeted autorouting run (`build --budget`, idle machine), finisher, DRC.
