# RR-CHS-MAIN stage 2: change requests against the stage-1 design

Owner: chassis electronics stage 2. Addressed to the stage-1 owner (`design/`), the integration lead, harness and
mechanical as named. `design/circuit.py` is NOT edited: every change below is applied in `overrides.py` (same IDs),
checked against the baseline on every build (an override that no longer matches circuit.py stops the build) and
logged to `reports/overrides_applied.json`. `python3 electronics/chassis_main/overrides.py` prints the change log and
re-runs the stage-1 self-check on the overridden netlist (PASSED).

Type: **NET** = netlist change, **ADD** = part added, **PART** = BOM/package change, **RENUM** = pin numbers changed to
the footprint's pad numbers (same names and nets), **LIB** = CAD library choice only, **PLACE** = placement only.

## Netlist / BOM changes (please adopt in circuit.py)

| ID | Type | Item | Change | Reason / backlog |
|---|---|---|---|---|
| S2-01a/b | NET | J_BTN pins 5 (PAUSE_BTN_RAW), 8 (LAMP_PAUSE_K) | → not connected. J_BTN stays an 8-way CLIK-Mate (keeps its circuit count unique among the safety headers; REARM pins 1-4, 6, 7 unchanged) | IB-33: the PAUSE button is on the right deck |
| S2-01e | ADD | **J_PAUSE** JST GH 5-way vertical BM05B-GHS-TBT | 1 PAUSE_3V3, 2 PAUSE_BTN_RAW, 3 V12_AUX (lamp +), 4 LAMP_PAUSE_K, 5 NC, MP GND. Signal family (PAUSE is program control, CCR-E12); 5 ways = unique in the rear-right cluster (J_NTC/J_PAUX 4-way GH, ToF 6-way GH, safety headers CLIK-Mate) | IB-33 |
| S2-01f | ADD | R_PAUSE 1 k 0603, 3V3 → PAUSE_3V3 | own current-limited contact supply (as R128 does for BTN_3V3), so the PAUSE cable never carries BTN_3V3 across the board | IB-33 |
| S2-01g | ADD | D_PAUSE TPD4E05U06 | ESD at the rear-right connectors: PAUSE_BTN_RAW, PAUSE_3V3, PACK_PRES_N (pins 5, 6, 7, 9, 10 NC) | IB-33 |
| S2-01c/d | NET | D29 pins 2 (PAUSE_BTN_RAW), 5 (PACK_PRES_N) | → NC (moved to D_PAUSE, next to J_PAUSE / J_PAUX) | D29 stays at J_BTN in the rear-left corner |
| S2-02 | PART | **J_HEAD1** Micro-Fit 3.0 2x4 43045-0800 | → **Mini-Fit Jr 2x5 RA 39-30-1100** (5569-10A2 land), pins 1-8 = J1 pins 1-8 as before, 9/10 NC | IB-32: the head-heater pair (pins 3/4, 4.05 A, AWG 18 per contract J1) needs an AWG 18 contact; Mini-Fit Jr 5556 terminals take 18-24 AWG [U, part numbers recalled]. 10 ways: cannot mate with the 8-way J_PWR. Fits the front-edge allocation u 14.5..37.8 (out of the 12 mm corner zone; header 12.8 mm high) |
| S2-04 | PART | R46 (U17 ILM) 825 Ω | → **845 Ω** RC0603FR-07845RL: HEAD_HTR limit 3343/845 = 3.96 A nominal (3.56-4.35 A) | IB-28: 4.05 A was above the contract's 4.0 A; heater draw ≤ 3.04 A (4.8 Ω at 14.6 V), M16 contact 5 A |
| S2-05 | NET | U42 BMI088 pin 2 | NC → GND (GNDA) | KiCad's stock BMI088 symbol has GNDA on pins 2 and 4; stage-1 pin numbers were recalled [U]. **Verify against the Bosch datasheet** |

## No netlist change (decisions and numbers)

### IB-32, J_CM5 (pins 1-4, V5_CM5 5.0 A on 2+2 contacts): keep Micro-Fit 3.0, **harness W-010 to AWG 20**
Each contact carries 2.5 A, so the 20-24 AWG terminal 43030-0007 is adequate with AWG 20. Voltage drop, W-010 = 180 mm [harness estimate]:

| | AWG 20 (33.3 mΩ/m) | AWG 18 (20.9 mΩ/m) |
|---|---:|---:|
| conductor loop, 2 wires per pole, 0.18 m | 6.0 mΩ → 30 mV at 5 A | 3.8 mΩ → 19 mV |
| Micro-Fit contacts, 2 per pole, ≤ 10 mΩ each [U] | 10 mΩ → 50 mV | 50 mV |
| total at 5.0 A | **80 mV**: 5.12 V → ≥ 5.04 V at the carrier | 69 mV |

The 11 mV difference is negligible against the 5.12 V set point; AWG 18 would need a terminal the housing does not take.
**Request to harness:** W-010 AWG 18 → AWG 20 (silicone). J_HEAD1: see S2-02 (harness W-008: Mini-Fit Jr 2x5 receptacle
39-01-2100 class + 5556 terminals, all seven wires fit 18-24 AWG) [U part numbers].

### IB-28, as-built branch limits vs contract (`interface/system/contract.yaml power.rails`)
| Rail | Contract `limit_a` | As built | Proposal |
|---|---:|---|---|
| HEAD_HTR | 4.0 | 3.96 A nominal after S2-04 (3.56-4.35 A) | compliant (nominal); record the ±10 % band in the contract note |
| VMOT | 12.0 | 6.5 A eFuse (±8 %), each bridge chops at 2.68 A (CCR-E06) | contract value is a ceiling: no board change; record "as built 6.5 A" |
| BUS_5V | 0.15 | TPS2553 RILIM 133 k ≈ 0.17 A typ [U formula]; `power_budget.md` says 150 k [U] — the two stage-1 documents disagree | not changed on the board because the RILIM formula is unverified; stage 1 to read the TPS2553 datasheet and pick RILIM for ≤ 0.15 A max, or the lead changes the contract to "0.15 A load, 0.2 A protection" |

### IB-37, pack NTC / presence sense return: accept the offset, keep J_PAUX pins 3/4 = GND
The NTC and presence link return to pack negative inside the cassette; pack negative carries the full pack current, about 0.1 V
offset at full load (backlog). With the 10.0 k pull-up to 3.000 V and a 10 k B3435 NTC the sensitivity at 25 °C is about 29 mV/K [C]:
* discharging: pack negative sits below board GND → the node reads lower → the NTC looks **warmer** (≈ 3.4 K at full load): over-temperature trips early (safe side);
* charging (≤ 3 A): offset reverses and shrinks to ≈ 20 mV → reads ≈ 0.7 K **colder**: the +5 °C hardware charge inhibit trips ≈ 0.7 K early (safe side);
* PACK_PRES_N: logic level against a 3.3 V pull-up, 0.1 V is irrelevant.

Decision: no board change. J_PAUX pins 3/4 stay on board GND and must be wired **only** if the cassette provides a sense return
that is isolated from pack negative (W-002 change); wiring them to a cassette return that is also tied to pack negative would put
an AWG 26 wire in parallel with the pack return (≈ 1-2 % of pack current). **Request to harness / battery cassette (W-002, W-003):**
either an isolated sense return, or leave J_PAUX 3/4 unwired (as now) and record the accepted offset.

### IB-12 / IB-33, connector positions (PLACE; board frame (u, v), see README)
| Connector | Stage 1 zone | Stage 2 position (centre) | Estimated cable (`tools/cable_lengths.py`, harness model) |
|---|---|---|---|
| J_TOF3 (CLIFF_RR) | rear-left | rear-right GH row (114.0, 15.2) | W-033 400 → ≈ 290 mm |
| J_TOF10 (REAR_R) | rear-left | rear-right GH row (127.6, 15.2) | W-040 400 → ≈ 290 mm |
| J_BUMP_R | rear-left | rear-right CLIK-Mate row (134.8, 6.2) | W-022 430 → ≈ 310 mm (no crossing of the board) |
| J_PAUSE (new) | — | rear-right GH row (101.4, 15.2) | W-019 becomes its own cable, ≈ 200 mm (was a 290 mm Y-branch from J_BTN) |
| J_TOF5 (LOOK_LI) | left edge front | rear-left GH row (21.1, 22.6) | W-035 360 → ≈ 270 mm **if** LOOK_LI is the tail-mounted `tof_look_rl` (harness assumption, unresolved) |
| J_TOF6 (LOOK_RI) | right edge front | rear-right GH row (131.2, 22.6) | W-036 360 → ≈ 290 mm, same assumption |
| J_TOF9 / J_TOF8 / J_TOF2 | rear-left | rear-left GH row, longest cable nearest the corner | ≈ 290 / 270 / 290 mm |

All eleven ToF cables are then ≤ 300 mm (estimates from the harness model, ±20 mm on connector positions; confirm on the first build).
If LOOK_LI/LOOK_RI are in fact at the grip cheeks (front), J_TOF5/J_TOF6 must go back to the front-edge zones (space exists next to
J_TOF4/J_TOF7). The chain now runs ... U22 → J_BUMP_L (rear-left) → J_BUMP_R (rear-right) → U23 (rear-right), which is the
physical order anyway.

**Requests to harness:** re-pin W-018 (J_BTN: pins 5 and 8 unused, splices SPL-BTN3/SPL-BTN6 removed), new W-019 J_PAUSE → PAUSE
button (JST GH contacts take AWG 26-30: W-019 AWG 24 → AWG 26; lamp ≤ 20 mA), move W-022/W-033/W-040/W-035/W-036 board ends as above.
J_PWR now spans v 14.5..33.6 (allocation v 4..34; stage 1 said v 8..31) so the rear-right corner below it stays free for cables.

### Placement-level deviations from `layout_guidance.md`
* 6 copper layers (guidance: 4): In1 solid GND, In2/In3 signal, In4 power splits (VBAT_SW, VMOT, VSYS, 3V3). Reason: 771 parts with
  fine-pitch ICs need the two inner routing layers; the planes stay solid. Thickness 1.6 mm unchanged.
* SAFETY_CHAIN clearance in DRC is 0.2 mm, not the 0.5 mm / 1.0 mm functional clearances of guidance §5 (tool limitation, see README).
* The VSYS/rails row (U10, U11, U12) sits on the gap pad next to the VMOT bulk capacitors as in the guidance floor plan; VSYS is
  routed + In4 split only around the charger.

## Pin renumbering and library choices (no electrical change)
| ID | Parts | What |
|---|---|---|
| S2-06a | Q1, Q2 (CSD18540Q5B), Q4, Q5, Q40 (CSD18543Q3A) | drain pins 6-9 merged into pad 5 (stock KiCad NexFET footprints/symbols) |
| S2-06b | K2, K3 (G2RL-2) | stage-1 numbers 1..8 [U] → terminal marks A1/A2, 11/12/14, 21/22/24 by pin name (stock symbol and footprint) |
| S2-07 | 15 parts without footprint + rejected symbol hints | see README "Library resolution" (CLIK-Mate 502443 stock, TI VQFN-HR and TPS25982 PLACEHOLDER land patterns, WE-LQS 5040 estimated, W1 pads) |
