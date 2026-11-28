# Independent review: heater, motor and supply interference against the SiPM front end (RR-HEAD-ACQ rev A)

Reviewer: independent second engineer (analogue / detector front-end), 2026-11-27. I did not design any of this.
Evidence labels as in the project: *calculated* = arithmetic or simulation shown here; *assumed* = my design-range input with no
source in the repository; *recalled* = device or physics value from memory, **not verified** against a document on this machine.
Nothing here is measured. Designators are those of `electronics/head_acq/design/circuit.py` (netlist identical in the stage-2
board, `STAGE2_CHANGE_REQUESTS.md` "Net changes in rev A: none").

## 1. Scope and method

Interface reviewed: every path by which the head heater, the traction motors and bridges, the DC/DC converters, the SiPM bias
supply and the digital/monitor lines can put charge into an anode input, move a threshold or baseline, or corrupt live-time /
classification, and whether the claimed counter-measures exist in the circuit, the board placement, the harness and the firmware.

Read in full or in the relevant parts: `electronics/head_acq/design/circuit.py` (all 1342 lines), `overrides.py`, `layout.py`,
`layout_frozen.json` (bond/shield parts), `design/layout_guidance.md`, `STAGE2_CHANGE_REQUESTS.md`, `STATUS.md`;
`RR-HEAD-ACQ.kicad_pcb` parsed for footprint positions and pad nets (placement only; routing not reviewed);
`electronics/analysis/head_afe_budget.md`, `head_afe_calc.py`, `head_afe_calc_out.md`, `head_design_review_checklist.md`;
`electronics/chassis_main/design/circuit.py` (bridges, VMOT, head branches, NT1, motor connector parts, loop/presence drive),
`electronics/analysis/chassis_design_notes.md`; `harness/cables.md` (W-006/007, W-008/009, W-101..W-119), `harness/lab_extension.md`;
`mechanical/head/out/head_report.md`, `mechanical/head/parts.py` (heater, carrier, cut-out, NTC geometry),
`mechanical/common/out/mechanical_interfaces.md`; `firmware/head/README.md`, `CONTRACT_CHANGE_REQUESTS.md` (CR-H9..H16),
`core/rrh_evtcap.c`, `core/rrh_control.c`, `core/rrh_config.h`, `port/stm32g474/bsp.c` (IMON scan), `port/stm32g474/hal_stm32.c`
(DAC writes); `interface/head_icd_addendum_0.4.md`; `docs/architecture/INTEGRATION_BACKLOG.md`; `docs/build/05_first_bench_tests.md`;
`planning/Detector_Head_RFQ_0.4.md` (yield and coax requirements).

Run (throwaway scripts in the session scratchpad `review_emi/`, not in the repository):
* `fp.py` / `nets.py`: footprint positions and pad nets of FRAME, SHLD_J1, SHLD_J2, heater nets from the `.kicad_pcb`.
* `emf.py`: imports `head_afe_calc.py` and drives its J60035@2.5 V transfer function `chain_tfs()["fast"]` with the Norton
  equivalent (i = C_d·de/dt) of a series EMF in the SiPM loop, to convert pickup voltages into p.e. at FAST.
* `mux.py`: comparator-node model FAST –330 Ω– FCMP –1 kΩ– monitor mux – MON_BUS, for loading and switching transients.
* `lf2.py`: analytic low-frequency tail at FAST (anode AC coupling C(PINA–PIN) 100 nF / 1.02 kΩ, preamp R_G to 10 µF, PZ divider).
* Poisson / Monte-Carlo efficiency versus threshold and yield.

`head_afe_calc.py` was used through its functions (its T2/T6 numbers reproduce: 1 p.e. = 6.93 mV at FAST, 37.5 µV at node A).

## 2. Findings by severity

Counts: **Critical 1, Major 7, Minor 7, Observation 6.**

---

### C1 (Critical, conditional on the optical yield) — the alpha decision is a charge threshold that bright betas cross; misclassified betas are counted as alphas with no flag

Evidence.
* Firmware class rule, `firmware/head/core/rrh_evtcap.c:313`: `cls = alpha ? ALPHA : (uld ? REJECT : BETA)`. ALPHA has priority over ULD.
* The ALPHA comparator (TLV3501 per floor channel, `circuit.py:311–317`) looks at SLOW only. The slow shaper responds *more* per p.e.
  to fast plastic light than to ZnS light: 0.369 mV/p.e. (beta) vs 0.218 mV/p.e. (alpha) — `head_afe_calc_out.md` T2.
* Design ranges (budget §2.3, T3): beta maximum 120 p.e. → SLOW 44 mV; alpha minimum 150 p.e. → SLOW 33 mV. **The ranges overlap; no
  ALPHA code separates them.** With the firmware default ALPHA = baseline + 30 mV (CR-H16), every fast pulse ≥ 81 p.e. is an alpha.
* Consequence: the alpha channel's background budget is 0.01 s⁻¹ (`analysis/radiometry/report/detectability_report.md` line 33,
  b_alpha), while the beta-window photon rate is ~33 s⁻¹ per µSv/h (same file, S_beta). A beta tail fraction of only 3 × 10⁻⁴ above
  81 p.e. already equals the whole alpha background budget at 1 µSv/h. That tail is small if the MIP-equivalent yield is the
  assumed 15 p.e. (a stopping electron in 0.25 mm deposits at most ~2.7 × the 51 keV MIP value, *calculated* from a CSDA range of
  ~0.27 mm at 150 keV, *recalled*), but it is not small at the ≥ 30 p.e. mean yield that finding M1 says the beta channel needs
  (2.7 × 30 × light-collection non-uniformity 1.5 ≈ 120 p.e.). **The two requirements conflict under the present classification:
  if the optics is good enough for the beta channel, the alpha counts are corrupted undetectably.**
* The pulse-shape information exists in hardware but is not used: FAST/SLOW per p.e. is 18.8 for betas and 6.7 for ZnS alphas
  (T2), and the raw-LLD time over threshold is already captured per event (TIM4/TIM3). Estimated TOT at an 8 p.e. threshold
  (*calculated* from the T2 pulse shapes and the assumed 200 ns ZnS decay): beta 120 p.e. ≈ 120–170 ns; alpha 150 p.e. ≈ ≥ 280 ns,
  alpha 1500 p.e. ≈ ≥ 700 ns.

Proposed change.
1. Firmware (no hardware change): classify as alpha only if ALPHA **and** TOT(raw LLD) ≥ 250 ns (setup member, default 250 ns,
   enters `setup_id`); ALPHA without that width → `floor_reject` with a new DIAG counter `alpha_short`. The capture already exists
   (`rrh_evtcap.c` width path); events with no measured width must not default to alpha.
2. Set the default ALPHA threshold from SLOW(beta max) × 1.3 once T2 measures the beta spectrum, not as a fixed 30 mV.
3. Test (T3 extension): Sr-90/Y-90 alone at the window, count alpha-class events per 10⁶ beta-window events with and without the
   width rule; acceptance ≤ 10⁻⁴ (radiometry owner to confirm the number).

---

### M1 (Major) — sharpened IB-22: with a dark-rate criterion consistent with the radiometry background, the beta channel needs a mean yield of about 30 p.e.

The budget picks the threshold where the dark trigger rate is < 1 s⁻¹ per chain (T6). The radiometry assumes the *total*
untracked beta-window background is b_beta = 0.5 s⁻¹ (range 0–2; `detectability_report.md` line 32). A chain dark rate of
1 s⁻¹ alone is twice that, and it drifts with temperature (×2 per 8 °C, assumed law). A dark contribution that is ≤ 10 % of
b_beta needs ≤ 0.05 s⁻¹, i.e. the bracketed T6 column: **10 p.e. at +10 °C, 11 at +25 °C, 8–9 at −20 °C** (J60035 @2.5 V typ),
one to two p.e. above the numbers quoted in IB-22 and the RFQ.

Efficiency (*calculated*: Poisson photostatistics × a Moyal-approximated energy-loss spread with MPV 0.7 of the mean × ±50 %
uniform light-collection variation over the 80 × 100 mm plate, the last two *assumed*):

| mean yield p.e. | threshold 8 | threshold 10 |
|---|---|---|
| 8 | 0.46 | 0.31 |
| 15 (assumed typical) | 0.82 | 0.71 |
| 30 | 0.98 | 0.96 |
| 45 | 1.00 | 0.99 |

Pure Poisson (no spread) needs μ = 14.3 p.e. for 90 % at threshold 10. The beta response K_beta = 24 s⁻¹ per Bq/cm² is read across
from a PMT-read AB-100 (`detectability_report.md` line 40), whose threshold is not dark-limited; it is not supported at 15 p.e.
and is unreachable at 4–8 p.e.

There is no dark-noise coincidence anywhere in the chain (one SiPM or one parallel group per chain, eight chains used), so the
only levers are those the budget lists. Dark-count arithmetic was checked: 50 kHz/mm² × 36.8 mm² = 1.84 MHz at 25 °C, ×2^(−15/8) =
0.50 MHz at +10 °C, Borel crosstalk μ = −ln(0.92); pure crosstalk multiplicity alone gives ~0.4 s⁻¹ at ≥ 8 cells at +10 °C
(*calculated*), consistent with the budget's statement that below 0 °C crosstalk, not pile-up, sets the limit. Delayed crosstalk
and afterpulsing are not modelled (checklist A3) and can only raise the threshold.

Proposed change (RFQ, `planning/Detector_Head_RFQ_0.4.md` §A): demand a **guaranteed minimum yield of ≥ 15 p.e. at the
Landau most-probable deposit of a normally incident MIP at the worst point of the 80 × 100 mm plate** (≈ 1.5 × the 10 p.e.
threshold), equivalently a plate-average mean ≥ ~30 p.e., at the stated overvoltage and +10 °C, with the position map measured
(≥ 9 points). Set the VT-042 margin to "yield_min(worst point, MPV) ≥ 1.5 × LLD(dark ≤ 0.05 s⁻¹)". Ask the radiometry owner to
re-derive K_beta from that efficiency instead of the AB-100 read-across. Note the interaction with C1.

---

### M2 (Major) — scanning the anode-current monitor while armed modulates one channel's threshold and injects switching charge at the comparator input (CR-H10 / IB-58, quantified)

Circuit. `MON_MUX_A[1:0]` drive the lane-monitor decoder U2701 (74HC238, `circuit.py:941–945`; E3 tied to +3V3 and E1/E2 to
GND, so **one lane mux is always enabled**); `MON_MUX_A2` is A0 of every lane mux U1007/U1107/U1207/U1307 (`circuit.py:373–380`).
With MON_EXT = 0 and MON_MUX_A3 = 0 the enabled lane mux connects **F_MFAST or R_MFAST**, i.e. the comparator input node FCMP
through only 1 kΩ (R125 class, `circuit.py:285`), to MON_BUS. The IMON scan (`port/stm32g474/bsp.c` `imon_select()`/
`bsp_imon_step()`, enabled while armed by `RRH_IMON_SCAN_WHILE_ARMED 1`, `rrh_config.h:82–83`) steps every 10 ms, so each of the
eight FAST taps is connected for 10 ms of every 80 ms and every channel sees two switch events per cycle (≈ 25 s⁻¹).

Estimates (`mux.py`; FCMP node 12 pF, switch source 10 pF, both *assumed*; MON_BUS capacitance *assumed* 50–150 pF = four TMUX1108
drains + ~300 mm of bus trace + buffer; the budget's 12–15 pF ignores the trace and the drains):

| Effect | Result at FCMP (J60035, 6.56 mV/p.e. at FCMP) |
|---|---|
| Loading while connected (bus 15 / 50 / 100 / 150 pF) | 1-p.e. amplitude −7 / −14 / −17 / −18 %: an 8 p.e. threshold becomes 8.6 / 9.3 / 9.6 / 9.8 p.e. on the connected channel |
| Charge sharing at closure, bus left at another tap's baseline (ΔV 30 / 100 / 300 mV) | +0.8–1.0 / +2.8–3.3 / +8.2–10 p.e., decaying with 1.33 kΩ × C_bus = 70–200 ns |
| TMUX1108 charge injection 0.3 / 1 / 3 pC into the source node (value range *recalled*, not verified) | +0.7 / +2.4 / +7.1 p.e., ~17 ns wide (TLV3502 follows it) |

Baselines of different FAST outputs differ by up to ±20 mV each (budget §7: 0.60 V ± 20 mV), so ΔV ≈ 40 mV → ~1.3 p.e. per closure.
Count corruption (*calculated* from the T6 Monte-Carlo crossing rates, threshold 8): an injected 3 p.e. adds ~0.003 s⁻¹ per channel,
5 p.e. ~0.1 s⁻¹, 7 p.e. ~4 s⁻¹ (probability that the dark pile-up already sits within the remaining margin, × 25 s⁻¹). The outcome
hinges on the unmeasured injection charge; the counts are periodic, unflagged and look like dark counts. Freezing the scan
(`RRH_IMON_SCAN_WHILE_ARMED 0`) removes the switching but leaves one channel permanently loaded (−7…−18 % threshold in p.e.).

Proposed change.
* Rev A board (no new parts): move the FAST monitor tap from FCMP to the op-amp output: R125 class pin 1 from `Fn_FCMP` to `Fn_FAST`
  (likewise SLOW from SCMP to SLOW, `circuit.py:310`) and raise the taps to 4.99–10 kΩ. The OPA838 output impedance then absorbs
  loading and injection; FCMP is no longer touched. Monitor bandwidth falls (see m4), which the monitor does not deliver anyway.
* Drive U2701 E3 (pin 6) from the spare TCA9534 bit `EXP_P7` (or E1_N from a spare MCU pin) so that all lane muxes can be
  disabled while counting; firmware parks the lane monitor off whenever armed and no engineering capture is requested.
* Rev B: give the IMON mux its own address lines.
* Firmware now: default `RRH_IMON_SCAN_WHILE_ARMED 0` until a B8-class test passes; scan IMON between gates of a dedicated
  housekeeping state, or accept "not measured" while armed.
* Test: see M7 (scope on FCMP via the `Fn PRE` pad is not enough; probe the comparator input or LLD with a trigger on MON_MUX_A0).

---

### M3 (Major) — the frame bond and all four RF frame capacitors are placed at the far end of the board next to lane 3, not at the J1 entry; cable-shield terminations are 60–130 mm from their entries

Evidence (positions from `RR-HEAD-ACQ.kicad_pcb` and `layout_frozen.json`, board (u, v) mm):
* R2801 (0 Ω FRAME–GND, "single-point DC bond … next to H1", `circuit.py:1003`) at **(318.9, 23.9)**; R2802 (1 MΩ) at (318.9, 25.6);
  C2801–C2804 ("one near each of H2, H3, H5, H6", `circuit.py:1007`) at **(316.4–321.4, 22.2–27.3)** — all clustered beside the lane 3
  can (u ≤ 312.25) and 7 mm from it. H1 (H2801) is at (75.5, 30.0). `layout_guidance.md` §1/§3 and S2-04 say R2801 is at H1.
  The parts are auto-arranged passives frozen in `layout_frozen.json`; `layout.py` has no explicit entry for them.
* FRAME has no copper on the board other than the eight hole pads and these R/C pads (no zone): the connection between R2801 and the
  holes, and between holes, is through the standoffs and the aluminium spreader.
* SHLD_J1 parts R2012/C2007/TP2004 at (21–24.5, 68.5–70.5), i.e. in front of the lane 0 logic, 63 mm laterally and 60 mm forward of
  J2001 (u 73–100, v 0–10.6); harness drain W-101.S is 130 mm inside the head. SHLD_J2 parts R2505/C2504/TP2501 at (250.7–252.7,
  67.0–69.8); drain W-102.S 110 mm.

Consequence. Every common-mode current that the J1/J2 shields bring to FRAME through their 10 nF (and any ESD to the cover,
spreader or frame) must run along the whole 316 mm spreader, under all four lanes and their SiPM carriers, and enters board GND
beside the lane 3 AFE. The HF "distributed" bond is in fact one point. Order of magnitude (*calculated*, chassis ground bounce
0.1–1 V at PWM edges *assumed* by the budget, loop ≈ 10–30 Ω at 2 MHz): 3–100 mA on the spreader; spreader-to-board parallel-plate
inductance ≈ μ0·2.5 mm·0.3 m/0.096 m ≈ 10 nH → 0.4–13 mV between the spreader and local GND at the far lanes. Through ~1 pF to a
carrier/anode that is ≤ 13 fC ≈ 0.03 p.e. — small for counting, but the design principle the documents claim (bond at the cable
entry, distributed RF bonds) is not what is built, and ESD current injection next to lane 3 is a survivability/upset concern.

Proposed change (placement, before routing): explicit entries in `layout.py BOARD` — R2801/R2802 within 3 mm of H2801 pad
(75.5, 30.0) with a short FRAME track; C2801..C2804 at H2802, H2803, H2805, H2806 as the netlist text says; R2012/C2007/TP2004
within 10 mm of J2001 with a FRAME track to H2801; R2505/C2504/TP2501 within 10 mm of J2501 tied to H2803. Shorten W-101.S/W-102.S
accordingly (≤ 30 mm). Add a check to `scripts/` that fails if any FRAME or SHLD part is > 10 mm from its intended hole/connector.

---

### M4 (Major) — motor pickup: the budget's aggressor is mis-specified, the mechanisms that probably dominate (common-mode dV/dt and brush arcing) are not estimated, and the motor-terminal suppression IB-09 asks for is in neither the netlist nor the harness

Re-derivation (`emf.py`, J60035 @2.5 V; mutual inductance by the coaxial-dipole formula μ0·A1·A2/(2πr³), the most favourable
orientation, as the budget uses):

| Case | Inputs | EMF | FAST p.e. (open pigtail 0.5 cm² @35 mm / 0.68 cm² @47.5 mm) | with coax (2 mm² launch) |
|---|---|---|---|---|
| Budget case reproduced | 1 A in 100 ns, 10 cm² at 65 mm | 0.36 mV | **6.8** (budget says ≈ 10) / 9.4 | 0.26 (budget 0.4) |
| Same, 150 ns edges (DRV8874, `chassis_design_notes.md` §4) | 1 A / 150 ns | 0.24 mV | 4.6 / 6.3 | 0.18 |
| Real differential motor-lead current | winding ripple 60 mA p-p (same §4: lead current is continuous, L ≈ 2.5 mH assumed there) | 14 µV | 0.28 / 0.38 | 0.01 |
| Bridge hot loop on RR-CHS-MAIN | ≤ 2.68 A in 150 ns, 2 cm² (*assumed*), ≈ 90 mm (bridge tray x −67…33, z 83 vs carriers x 79, z 13–28) | 66 µV | 1.3 / 1.7 | 0.05 |
| Common-mode lead current from dV/dt | 80 V/µs × C(winding+lead to can) 0.3–1 nF (*assumed*) = 24–80 mA in 150 ns, nearest lead ≈ 74 mm | 21–70 µV | 0.4–1.4 / 0.55–1.9 | ≤ 0.05 |
| Brush commutation arc | ~0.1 A common-mode in ~5 ns (*assumed*: 20 V arc step, lead inductance-limited) | ≈ 3.7 mV for 5 ns | **≈ 20 (order of magnitude)** | ≈ 0.6 |

Conclusions.
* The budget's 1 A / 100 ns step "in a 10 cm² motor-lead loop" does not exist: the motor inductance keeps the lead current continuous
  (60 mA ripple); the fast current step lives in the bridge loop on the chassis board. The headline numbers are of the right order
  only by accident, and the pigtail-length increase (35 → 45–50 mm, IB-57; ~60 mm in one BOM line) scales the open-loop case by
  1.3–1.7, not the coax case.
* With coax pigtails every PWM-related term is ≤ 0.3 p.e. **Brush arcing is the outlier**: PWM-independent (present at 100 % duty,
  while coasting or back-driven, and during brake relay K2/K3 transitions), ns-fast, and not estimated anywhere except "covered
  only by test". The 0.6 p.e. coax figure assumes the launch loop is the only residual; finding m1 adds the shield-loop term.
* Suppression actually present: a BLM31SN500 bead (50 Ω at 100 MHz) + 1 nF to GND per motor pin **at the chassis board connector**
  (`chassis_main/design/circuit.py:541–545`). At the 1–3 MHz content of a 150 ns edge the bead is a few ohms (*recalled* bead
  curve), so motor-lead dV/dt is not reduced; the parts help above ~50 MHz and only for the board end. Harness W-006/W-007:
  "Shield / bonding: none (… ferrite + 1 nF at the board connector)" (`harness/cables.md:222, 241`). **Nothing at the motor
  terminals.** IB-09 therefore remains unimplemented, not just open.

Proposed change.
* Chassis harness/motor: at each gearmotor's terminals, 47–100 nF X7R/film across the terminals plus 2 × 4.7–10 nF from each
  terminal to the motor can, can bonded to the chassis plate with a short strap; motor pair twisted to the motor; encoder pair
  routed away from the head side. Record as a harness item on W-006/W-007 and as a part in the chassis BOM.
* Keep coax pigtails mandatory (IB-23 stands); change the budget table to the physical aggressors above.
* Test: M7 items 1–3.

---

### M5 (Major) — a live heater-domain part touching the spreader would put up to ~1.5 A of heater return current through R2801 and the board ground plane; nothing in the design or the tests excludes it

Circuit/mechanics. FRAME (spreader) is bonded to GND by R2801 (0 Ω 0603). On the spreader sit: four polyimide heater zones bonded to its
underside (`mechanical/head/parts.py` lane_parts "heater", 0.3 mm film), the bimetal cut-out PUR-TCO in the **return** leg
("on the spreader tab", KSD-01F / Airpax 67F class, `mechanical/head/docs.py:41`) and the regulation NTC as an M3 **ring-lug** screwed
to the spreader (PUR-NTC-10K, `docs.py:42`), whose return wire W-103.7 is board GND. In KSD-01F-class parts the metal cap is often
in contact with the switching contact (*recalled*, not verified; insulated variants exist); a ring-lug NTC is only safe if the lug
is isolated from both leads.

Estimate (*calculated*): if the cut-out case or a damaged film edge contacts the spreader, the heater return (J1 pin 4, ≈ 30 mΩ
cable + contacts) is paralleled by spreader → R2801 → In1 GND plane → J1 pin 2 (≈ 50 mΩ). Up to ~1.5 A of the 3.1 A then flows in the
plane from u 319 to u 94 (≈ 2.3 squares of 1.1 mΩ/□ In1 copper, 15 µm in the stack-up) → 2–4 mV gradient across the AFE strip,
switching with the heater. Thresholds for lanes 2/3 come from DACs at u 146–173 while their comparators sit at u 190–312: a 2–4 mV
slow step is **0.3–0.6 p.e. threshold shift per heater edge** (6.9 mV/p.e.), and R2801 (0603 0 Ω, ~1 A class *recalled*) is
overloaded. Bring-up step 0 (`layout_guidance.md` §7) checks "J2001.4 to GND open" on a bare board with no heater and no spreader,
so it cannot find this.

Proposed change. (1) Specify PUR-TCO with an electrically isolated case (≥ 100 MΩ case-to-terminals, stated in the BOM line) and
the NTC with an isolated lug, or mount both on a 0.1 mm polyimide pad; (2) add to the head end-of-line test: with the heater
assembly fitted and the spreader bolted to the board, J2601.1/.2/.3 to FRAME and to GND ≥ 10 MΩ at 100 V; (3) in firmware,
compare HTR_SENSE (head shunt) with the chassis INA3221 HEAD_HTR channel per gate; a difference > 10 % means a sneak return.

---

### M6 (Major) — 6-layer stack-up puts the long event lines over the split power layer and broadside-couples In2/In3

`RR-HEAD-ACQ.kicad_pcb` stack-up: F.Cu / 0.099 / In1 GND / 0.571 / In2 sig / 0.109 / In3 sig / 0.571 / In4 power (split: +5V_A,
+3V3_EVT islands per lane, +5V6, +3V3; `layout.py _planes`) / 0.099 / B.Cu sig. The guidance routes BUSY/ULD/ALPHA/LLD/CLR
"on layer 4 (bottom) in v > 34" (circuit.py NET_CLASSES EVENT). On this stack the bottom layer references In4 — the split power
layer — so the return current of every 3.3 V, ~1.5 ns comparator/latch edge (≈ 3.3 V × 40 pF → ~70 mA peak) flows in a power
island and must cross the island edges at v 41.5 and around each lane through decoupling capacitors. Plane inductance of a few
tenths of nH gives mV-level spikes on +5V_A/+3V3 near the lane fronts (*calculated* order: 0.2 nH × 70 mA / 2 ns ≈ 7 mV); In2 and
In3 are 0.11 mm apart (strong broadside crosstalk) and 0.57 mm from their nearest plane. Coupling of a 7 mV +5V_A spike to an anode
through the BAV99 clamp capacitance (~1.5 pF to +5V_A, `circuit.py:225`, *recalled* Cj) is ~10 fC = 0.02 p.e.; through op-amp PSRR
at > 100 MHz it is unquantified. Not catastrophic, but it is the moment to fix it, since routing has not started in earnest.

Proposed change: re-stack as F sig / In1 GND / In2 sig / In3 PWR / In4 GND / B sig (both outer and both inner signal layers adjacent
to a GND plane, power plane tightly coupled to GND), or keep the current order but make In4 a solid GND and move the power islands
to In3 with no signals under the cans. Route event lines only over GND.

---

### M7 (Major) — the bench tests cannot expose most of the mechanisms above

1. **T5/B11 pass criterion "no excess in the shortest time-over-threshold bin" is not a diagnostic.** The bins are < 150 ns /
   150–400 ns / 0.4–2 µs / > 2 µs (`firmware/head/README.md`, event capture). The FAST FWHM is 80 ns (T2), so essentially *every*
   dark and beta event near threshold has TOT < 150 ns; pickup cannot be told apart. Pulses < ~14 ns may lose the falling capture
   and land in no bin at all (budget §4).
2. **Count-rate tests at 3 p.e. are insensitive.** The dark crossing rate at 2.5 p.e. is ≈ 4.5 × 10⁴ s⁻¹ (T6 Monte-Carlo, 25 °C):
   σ of a 100 s count = 2100, so the 3σ resolution is ≈ 63 s⁻¹. Pickup adding 60 s⁻¹ at 3 p.e. passes while it could still be
   60 × the dark budget at the operating threshold. The B11 "1 V LISN, ratio within 5 %" has the same weakness (5 % of 4.5 × 10⁴).
3. **Missing measurement (the important one): coherent, aggressor-synchronised waveform capture.** Scope the comparator input
   (FCMP probed directly with a ≤ 1 pF active probe, or the `Fn PRE` pad through its 453 Ω) triggered on the aggressor — bridge
   output node, HTR_GATE, MON_MUX_A0, PULSER_STROBE, LED_STROBE, a commutator-noise current probe on a motor lead — and average
   ≥ 10⁴ triggers. Random dark pulses average out; coherent pickup stays. Sensitivity ≪ 0.1 p.e. Report injected amplitude in p.e.
   per aggressor. This replaces count-rate deltas as the pass criterion; count rates remain the final system check.
4. Motor states missing: motors driven from a DC bench supply at 100 % (brushes only, no PWM edges); wheels back-driven with the
   bridges asleep (brush noise only); brake relay K2/K3 transitions; head undocked on the J1X/J2X extension with motors running.
5. Missing: common-mode injection on the J1 and J2 cables with a current clamp (1–30 MHz) while counting; ESD to cover/spreader with
   the head counting (frame-bond placement, M3).
6. Missing as T-sheets although in the budget: B5 (dark rate with the boost running vs. an external quiet bias), B6 (crosstalk),
   B8 (digital activity, **including the IMON scan on/off and HV_SET tracking writes**, see m7), B12 (cover/cans on/off).
7. T6 (heater): add a cut-out actuation (heat the cut-out with a hot-air tool while counting) and the heater-domain insulation check of M5.
8. T1/T2: record the lane-monitor state; perform the threshold scans with the lane monitor parked and the IMON scan frozen; take
   single-p.e. spacing from the PRE pads or the threshold scan, not from J2701 (m4).
9. Lab grounding is unspecified: scope earth on J2701/PRE pads, a debug-UART adapter on J2402, SWD and the dark-box metal each add an
   earth connection to head GND (§4 below). Sheets must state isolated/differential probing and record the configuration.
10. T3: add beta efficiency vs. time after a large alpha (Am-241 or the 1 nF C_INJ2 pulser at 2.5 nC, then a 10 p.e. pulse at
    20–500 µs delay) — see m2.

---

### m1 (Minor) — ground loops at the SiPM carrier that the budget does not include

Per SiPM: two 1.13 mm coax (anode, bias) with each shield bonded to GND at the U.FL and at the carrier (W-112..W-119 "the two shields are
separate conductors"), plus two AWG 28 GND wires of the lane auxiliary pigtail (W-108..W-111) to the carrier, and the RFQ asks for a
≥ 10 nF bias decoupling capacitor on the carrier, so the shields carry signal return. At the board the anode and bias U.FL are 5.1 mm
apart and the GH-6 is 8.6 mm from the floor anode U.FL (S2-L3): loops of ≈ 1–2 cm² over 35–50 mm in the chimney.
Estimate with the budget's own aggressor (*calculated*, LF transfer impedance = shield resistance 0.2 Ω/m *recalled* for 1.13 mm
coax, loop L 50 nH): shield-loop current 3.5 mA, 32 µV in series with the anode for ~3 µs → **0.27 p.e.**, i.e. as large as the
claimed coax residual; at tens of MHz the braid transfer impedance rises and this is not bounded.
Change: lay each anode/bias coax pair and the aux pigtail as one tight bundle (touching, tied every 10 mm), shortest common path;
ask the OEM (RFQ §B) for the carrier ground scheme and loop area; require that carrier ground never touches the spreader/frame.

### m2 (Minor) — the PZ network passes DC: FAST undershoot after a large alpha is not "suppressed by 10⁻⁴"

Budget §2.3 (`head_afe_budget.md:94`) says the 100 µs input-coupling undershoot is suppressed at FAST by ~10⁻⁴. The pole-zero network
(R_PZ 226 Ω ∥ C_D 220 pF from PRE to FS, R_D 100 Ω to VBL, `circuit.py:274–277`) has DC transmission R_D/(R_D+R_PZ) = 0.307, so FAST
sees 21 × 0.307 = 6.45 × PRE at low frequency. The calculator's pulse model omits the input coupling (C 100 nF, `circuit.py:262`) and
the preamp R_G AC ground (10 µF, `circuit.py:268`), which is why T7 reports zero undershoot.
*Calculated* (`lf2.py`) FAST tail after a 15 000 p.e. alpha: −18 p.e. at 1 µs, −10.6 at 50 µs, −5.9 at 100 µs, **−3.1 at 150 µs (end of
the default hold)**, −1.5 at 200 µs, zero crossing at 314 µs, +0.3 p.e. at 500 µs; after a 1500 p.e. alpha −0.3 p.e. at 150 µs. The beta
threshold is effectively raised after big alphas beyond the booked hold. Small at survey alpha rates; up to ~15 % efficiency loss in
a calibration with 10³ s⁻¹ alphas. Change: firmware default `afterglow.alpha_hold_us` 300 µs (≤ 500 allowed); optionally a 47–100 nF
capacitor in series with R_PZ (τ 10–20 µs) to remove the DC path (verify at bring-up step 8); add the LF poles to `head_afe_calc.py`.

### m3 (Minor) — HF ground paths bypass the J1 common-mode choke and the J2 isolation

At ≥ 1 MHz the head GND is connected to the chassis by four parallel paths: J1 pin 2 through L2001; J1 shield 10 nF (C2007) → FRAME →
R2801; J2 shield 10 nF (C2504) → FRAME → R2801; and the heater films' capacitance to the spreader (*calculated* 9–18 nF for four 73 cm²
zones, 50 % foil coverage, 25–50 µm polyimide εr 3.4, *assumed* construction) → R2801, closing through J1 pins 3/4, which have only
TVS + 10 µF on the head (C2601) and no common-mode element. 10 nF is 16 Ω at 1 MHz. Budget §3.4 "the J2 side is galvanically
isolated" and checklist C3 "J2 is isolated" are true at DC only. Counting impact estimated small (M3 numbers), but the CM current
path runs through the spreader under the SiPMs. Change: correct the text; if B11/CM injection shows sensitivity, add a CM choke on the
heater pair at J2601 (4 A class) or reduce the film-to-spreader coupling with a grounded screen layer in the film (OEM option).

### m4 (Minor) — monitor bandwidth overstated

Budget §2.4: "1 kΩ × ~12–15 pF → 10–15 MHz". MON_BUS carries four TMUX1108 drains, ~300 mm of trace from u 31 to u 294 and the buffer:
*assumed* 50–150 pF → 1–3 MHz, so J2701 low-passes the 80 ns FAST pulse substantially. T1/T2 "single-p.e. spacing at FAST" must use
the PRE pads or threshold scans. Correct the text; after M2 (higher-value taps) the monitor becomes a slow/baseline monitor only.

### m5 (Minor) — the heater domain is linked to ground by more than "the 100 kΩ sense resistors and the INA180 inputs"

`layout_guidance.md` §3. Also: the gate driver (R2604 47 kΩ → Q2602 → GND) carries (V_bus − ~3 V)/47 kΩ ≈ 0.2 mA while on; R2610
100 kΩ + R2611 33 kΩ push (15 V − 3.6 V)/133 kΩ − 3.6 V/100 kΩ ≈ 50 µA into +3V3 through clamp D2603 whenever the feed is present
and the cut-out closed (27 µA at 12 V; it back-powers +3V3 when the head is unpowered); and the 9–18 nF film capacitance of m3.
All harmless for counting (µV, ms), but the documentation should state them, and B10/T6 should scope +3V3 with the head unpowered and
the heater feed live.

### m6 (Minor) — the heater-transition marker never reaches the analysis

`rrh_evtcap.c:124–125` sets `heater_transition_in_gate`; it is carried only in DIAG (contract `acq_mapping`), which the host does not
consume (only `ros2_ws/src/rr_core/rr_core/fakes/head.py` mentions it). Given the coupling estimates in §3 (≤ 10⁻⁴ p.e.) this is
acceptable, but "marked per gate" is not a counter-measure until the host archives and can exclude those gates; either archive DIAG
per gate (26 % bus load, addendum) or move a one-bit flag into the ACQ frame in the next schema revision.

### m7 (Minor) — bias tracking writes the HV_SET DAC while armed, contrary to the budget

Budget §3.3 row "SPI/I²C activity": "DACs written only when disarmed (firmware)". `rrh_control.c bias_loop()` writes HV_SET via
`rrh_hal_bias_set()` → `bsp_dac_write(0, 6, …)` (`hal_stm32.c:83–96`) every 100 ms control period whenever the temperature target
moves > 5 mV (≤ 20 mV per step). Electrically harmless (*calculated*: 20 mV step through the 6 Hz loop and 160 Hz filters → C_d·dV/dt ≈
3 nA at the anode; U_DAC0 output 6 shares the package with the lane 0/1 thresholds, glitch through 1 kΩ/100 nF ≈ 50 µV = 0.007 p.e.
for an assumed 5 nV·s), but B8 must be run with tracking active and the budget text corrected.

---

### Observations

* **O1 Lane 0 is the most exposed lane by placement**: J2601 (heater/NTC header, 3 A) body at u 50.2, 0.45 mm from the lane 0 can wall
  (u 49.75); LMR51606 buck U2101 at (58, 52), 14 mm from the can corner; TMP117 U2402 and its I²C at (53, 39) at the can corner; the
  heater tail rises in the chimney at u 75.5. Normal heater edges are harmless (§3), but per-lane pickup results should be expected to
  differ; analyse lanes separately in every test.
* **O2 Cut-out actuation** (fault case only) is a fast edge on the heater element: mean element potential jumps by ~V/2 = 6–7.5 V with
  contact bounce. Through 0.1–0.5 pF film-to-carrier (*assumed*) that is 0.75–3.8 pC = **1.6–8 p.e. per bounce** in the reference
  channels under the film; through 9–18 nF to the spreader, 65–130 nC of ground current. HTR_CUTOUT_OK (0.33 ms filter) latches
  HEATER_CUTOUT in the same gate: null that gate's counts, not just flag it.
* **O3 Pulser strobe reaches all eight switches** (PULSER_STROBE on pin A of every 74LVC2G53, `circuit.py:239–243`); inhibited switches
  still see the control edge, and C_INJ (100 pF) delivers nearly all of any feedthrough charge into the anode. Unquantified (no
  feedthrough figure for the inhibited state in the repository); it biases B6/T4 crosstalk results during pulser tests only, since
  the strobe is idle in survey.
* **O4 RS-485 island** (u 230–272) and the J2 pigtail sit 5–17 mm from the lane 2/3 cans and the lane 3 U.FLs; their common-mode potential
  is the chassis'. With ≤ 50 fF to an anode node (layout rule analogous to the budget's 15 fF/3.3 V rule) a 1 V CM step is ≤ 0.1 p.e.
  Keep the rule explicit in the routing constraints.
* **O5 Interlock loop and presence ID are not low-impedance second grounds**: R2001 returns on pin 2 (cable side of L2001); the loop
  is fed through 1.1 kΩ from chassis V5_AUX and returned through 1.1 kΩ to chassis GND (`chassis_main/design/circuit.py:394–395`) and
  touches nothing on the head. The rail-switch cables W-104..W-106 (92–302 mm) carry chassis-referenced loop conductors and head
  AUX_GND past the lane 0/3 chimneys: route them outside the EMI fence where possible.
* **O6 Default thresholds** (CR-H16) assume 6.9 mV/p.e. This is correct for J60035 @2.5 V with the netlist values (my independent
  check: node A peak 37.5 µV, FAST 6.93 mV) but the candidates span 6.3–24 mV/p.e. (T2): "8 p.e." means 2.3–8.8 real p.e. With an
  NUV-MT the default would sit in the dark-count sea. Firmware must refuse ARM with placeholder thresholds once a device type is set.

## 3. Answers to the eight questions, in short

**1 Heater.** High-side P-FET Q2601 (SUD50P04-08) at the head on HEAD_HTR_P, Miller-controlled: *calculated* on ≈ 0.7–0.8 ms
((V_bus − 3 V)/47 kΩ − 3 V/68 kΩ into 10 nF C2604 = 15–21 V/ms), off ≈ 2.7–3.4 ms (3 V/68 kΩ = 4.4 V/ms); dI/dt ≈ 4 kA/s on, 1 kA/s off.
Return: J2601.2 → HEAD_HTR_N (no board-GND contact) → J1 pin 4 → chassis NT1 at the VBAT_SW bulk (`chassis_main/design/circuit.py:718`).
No shared conductor, plane or pin with the analogue or bias return on the head; sharing exists on the chassis board (between NT1 and the
pack entry) and potentially via the spreader (M5). Injection with normal edges: magnetic 4.4 kA/s × 10 nH = 44 µV for 0.7 ms → charge
C_d·E = 0.18 pC spread over ~0.1 ms → < 10⁻⁴ p.e. at FAST; capacitive film-to-carrier 0.1–0.5 pF × 7.5 V = 0.75–3.8 pC over 0.7 ms →
1–5 nA → < 10⁻⁴ p.e.; film-to-spreader displacement 65–130 nC per edge (0.1–0.2 mA for 0.7 ms) through R2801 and the plane → µV, ms.
Marking per gate is adequate **for these edge rates**; zero-cross switching is meaningless (DC) and gate synchronisation is already
implemented (`rrh_evtcap.c close_gate()` applies the request on the boundary; edges fit easily in a 100 ms gate). What is needed
instead: keep the edge-rate stop condition of bring-up step 13 (> 0.2 ms) as a production test, M5, O2, m6.

**2 Motors.** See M4: budget arithmetic reproduced (6.8 p.e., not 10; 0.26 p.e. with coax) but the aggressor is the wrong physical
current; realistic PWM terms ≤ 1.9 p.e. open / ≤ 0.05 coax; brush arcing ~20 p.e. open / ~0.6 coax (order of magnitude); plus m1
shield loops ~0.3 p.e.; longer pigtails ×1.3–1.7 on the open case only. Motor-terminal suppression: recommended, absent.

**3 Bias.** Ripple to gain: ΔG/G = ΔV/V_ov; 1 mV → 0.04 % → 0.003 p.e. at an 8 p.e. threshold — negligible. Filters at 700 kHz
(*calculated*, X7R DC-bias derating 50 % *assumed*): 100 Ω/1 µF −47 dB; follower: gate via C_gd ~2 pF (*recalled*) into 1 nF −54 dB and
1/g_m ≈ 1 kΩ against 1 µF on HV_BUS −73 dB, drain–source C_ds path −106 dB; per channel 1 kΩ/1 µF −67 dB, 100 Ω/100 nF −27 dB: total
well above 150 dB against the 82 dB requirement; the real limit is stray coupling from the boost cell (B5 must run). Between the 6 Hz
loop and the 340 Hz gate filter HV_BUS follows HV_RAWF nearly 1:1 (by design); light-load burst ripple (TPS61391 light-load mode not
documented here) of 50 mV at 1 kHz would give ≈ 1.7 mV at the cathode = 0.07 % gain — negligible. OVP trip: PERMIT cleared, pass gate
pulled low, 47 kΩ bleeder over ≈ 9.8 µF (τ ≈ 0.46 s): displacement into the anode ≈ 4 nF × 60 V/s = 0.24 µA — harmless, counts are
nulled by BIAS_TRIP. Per-channel IMON mux U2703: switching its 100 nF between TRIMDRV nodes up to 2.4 V apart draws ≤ 0.24 mA through
R108 (10 kΩ) from the TLV9062 output; with ~1 Ω closed-loop output impedance and 4.99 kΩ/4.8 µF to the trim node that is ≈ 10 µV, ms —
harmless. The real CR-H10 problem is the lane-monitor taps (M2).

**4 Grounding.** Loops actually present:
(a) DC: chassis GND —J1 pin 2 (W-008.2 + W-101.2, ~0.44 m)— L2001 — head GND: the only DC path (correct).
(b) HF: head GND — R2801 (at u 319, M3) — spreader/standoffs — C2007 10 nF — J1 drain (130 mm) — braid — J1R shell — chassis; same with
C2504 for J2; same with the film capacitance via J1 pins 3/4 (m3).
(c) At each SiPM: anode-coax shield, bias-coax shield, 2 aux GND wires in parallel between board GND and carrier GND (m1).
(d) Conditional: heater-domain part live to the spreader (M5); carrier ground touching the spreader or chimney (m1 requirement).
(e) Lab: scope earth on J2701 (u 214, v 91) or PRE pads, UART adapter on J2402, SWD, dark box → earth; the robot on its charger is
earthed through the inlet FE (`harness/cables.md:189–190`, charge-inlet lead). That closes a metre-scale loop through head GND and the 2 m J1X
pin 2; mains-frequency and charger switching currents then cross the head plane from the service strip to J2001. Specify isolated
probing (M7 item 9). Presence ID and interlock loop do not close loops (O5).
Frame isolation: G10 isolators give ~0.1 nF (*calculated* order) head-frame-to-receiver, so the scheme isolates below ~100 kHz and the
10 nF shield bonds dominate above — consistent with the intent, once M3 is fixed.

**5 Thresholds and baselines.** Discriminator references: thresholds from four DAC60508 internal references, baseline from U_DAC1's
reference via 0.1 % divider and 1 µF; absolute mismatch ≤ ±2.5 mV (0.36 p.e., removed by the baseline scan), drift ≈ 13 µV/°C
(0.002 p.e./°C) — sound. Hysteresis 6 mV vs 1.7 mV rms FAST noise (3.5 σ): no chatter expected. Rate-induced FAST baseline shift via the
PZ DC path: −0.06 mV (0.008 p.e.) at 1.8 MHz dark rate, −0.24 mV at 7.4 MHz (4-device array) — negligible; after big alphas it is not
negligible (m2). 6.9 mV/p.e. is consistent with the netlist for J60035 only (O6).

**6 Yield.** See M1 (needs ≈ 30 p.e. mean; ≥ 15 p.e. at the worst point at the MPV) and the C1 conflict.

**7 Tests.** See M7.

**8 Claims beyond the design.** Budget §2.3 FAST suppression of the undershoot (m2); §2.4 monitor bandwidth (m4); §3.3 "DACs written
only when disarmed" (m7); §3.4 motor-lead 1 A/100 ns aggressor and "0.4 p.e. before shielding" as a bound (M4, m1); §3.4 and checklist
C3 "J2 isolated" (m3); `layout_guidance.md` §1/§3 and S2-04 R2801/C2801–4 positions (M3) and the heater–ground link list (m5);
`chassis_design_notes.md` §9 "ferrite + 1 nF at each motor pin" as edge suppression (M4); T5 TOT-bin diagnostic (M7); the alpha channel
as a "confirmation channel" that cannot be confused (C1); RFQ/IB-22 thresholds at the 1 s⁻¹ criterion (M1).

## 4. Checked and found sound

* Heater switch topology, edge rates and gate-boundary switching in firmware; heater return kept off the head GND net
  (`circuit.NETS['HEAD_HTR_N']`: J2001.4, J2601.2, D2601, C2601 only); heater loop confined to the J1 landing by placement
  (Q2601 (73.5, 17), R2601 (84, 15.2), J2601/J2001 adjacent); +5V6 plane, not +5V_A, under the heater cell (In4 zone P5V6).
* Bias filter chain and its corners against 700 kHz; OVP/PERMIT/bleeder action on the anode; per-channel IMON mux effect on the trim node.
* Supply filtering for +5V_A: LC 10 µH/22 µF (10.7 kHz nominal, ~18 kHz with derated 22 µF, *assumed*) ≈ −72 dB at 1.1 MHz plus the
  LDO and per-channel bead + 4.7 µF; the 100 dB B11 requirement is plausible by design, layout-limited.
* Buck (U2101/L2101) H-field to the nearest pigtail: ≈ 0.2 µV (*calculated*, 0.3 A/5 ns, 0.3 cm² loop, 50 mm) — negligible.
* Electronic noise (0.25 p.e. rms), DAC resolution (0.09 p.e.), comparator offset handling, 6.9 mV/p.e. for J60035 @2.5 V,
  dark-count arithmetic of T6 (scaling and Monte-Carlo agreement), live-time splitting at gate boundaries (code read).
* Isolation barrier geometry (4 mm keep-outs on all layers, island u 230–272, v 0–13) and BUS_GND content.
* Presence-ID and interlock loop are not second ground connections (O5).
* Pickup of the anode/bias coax launch at the board: U.FL via keep-out is a 4.8 mm *diameter* rule (`layout.py _keepouts`, the third
  `circle` parameter is a diameter, as `KO_HVVIA` shows), so GND vias can sit ≤ 0.8 mm from the shell pads; the 2 mm² launch loop is
  achievable.

## 5. Cannot be assessed until hardware (or OEM data) exists

Brush-arc spectra and motor winding-to-can capacitance; micro-coax transfer impedance above 1 MHz and the actual pigtail routing; the OEM
carrier's ground scheme, bias capacitor and loop area; TMUX1108 charge injection and MON_BUS capacitance in circuit; real yields, the
light-collection map, delayed crosstalk and afterpulsing; recharge time (PZ match) and C_d; heater-film construction and capacitance;
cut-out and NTC case insulation; FET edge times with the real gate charge; plane impedances and return paths (routing incomplete:
340 open connections, IB-51); TPS61391 light-load behaviour; chassis-board ground bounce at J_HEAD1 versus the J1R shell; ESD behaviour.
