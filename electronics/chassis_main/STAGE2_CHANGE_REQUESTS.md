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

## Stage 3 (review fixes) — `docs/reviews/REVIEW_traction_inhibit.md`

Owner: chassis electronics, 2026-11-27. Every item is an override in `overrides.py` with ID **S3-xx** (same check-against-baseline
mechanism as S2). Status column: **DESIGNED** = decided and listed here for firmware; **IN NETLIST** = applied in `overrides.py` and the
self-check passes. This list is kept current while the work proceeds.

### 3.1 Firmware-relevant changes (chassis firmware engineer: read this first)

| # | Item | Change | What firmware must do / may assume | Status |
|---|---|---|---|---|
| F1 | **New expander IOX_D** = TCA9534PWR (U47), I2C_SYS, **7-bit address 0x22** (A0 = GND, A1 = 3V3, A2 = GND); no reset pin, no interrupt; all 8 pins INPUTS (never write the configuration register to anything but 0xFF) | P0 `LATCH_NC_RB`, P1 `LATCH_RUN_RB`, P2 `HEAD_LOOP2_OK_RB`, P3 `REARM_SET_RB`, **P4 tied to 3V3 (reads 1), P5-P7 tied to GND (read 0)**: fixed pattern, check `(in & 0xF0) == 0x10` on every read; mismatch or NACK = IOX_D unknown | Read at >= 100 Hz. Unknown -> withhold arming (ARM_PERMIT low before REARM); while latched treat as m7 (several consecutive failures / age > 50 ms before dropping) | IN NETLIST |
| F2 | `LATCH_NC_RB` (IOX_D P0) | Tap on K1 pole A **NC** contact; K1 pole A common (K1_SEAL_A) is biased from 3V3 (BAT54 + 47 k), so the reading is valid with the chain dead / ARM_PERMIT low. **HIGH = K1 pole A released**, LOW = K1 operated (or pole A NO welded, or NC contact open) | Expect HIGH whenever HW_LATCH_RB is low for > 30 ms (K1 release <= 4 ms [U] + margin). LOW with HW_LATCH_RB low > 30 ms -> **K1_WELD** (fatal, ARM_PERMIT low, no re-arm until power cycle). Boot: must be HIGH before ARM_PERMIT is raised the first time | IN NETLIST |
| F3 | `LATCH_RUN_RB` (IOX_D P1) | Tap on the new node **K1_RUN** (net name of the readback: LATCH_RUN_RB, not K1_* so it stays out of the SAFETY_CHAIN net class) = K1 pole B output (before the new hold element U_HOLD). HIGH = CHAIN_END live AND K1 pole B closed. 100 k / 56 k / 22 nF / BAT54 like the other taps | LATCH_RUN_RB HIGH while no REARM set pulse has been accepted (i.e. HW_LATCH_RB low) for > 30 ms -> **K1_WELD** (pole A or pole B welded: the latch re-closed by itself; the new hardware element U_HOLD keeps RUN_12V off, so this is detection, not the barrier). **Boot / BRAKE_TEST step**: raise ARM_PERMIT with all elements closed and no REARM: LATCH_RUN_RB and HW_LATCH_RB must stay LOW for >= 100 ms (this is now implementable: "K1 not welded at boot") | IN NETLIST |
| F4 | HW_LATCH_RB (PD2) meaning | Still the tap on RUN_12V. RUN_12V is now fed CHAIN_END -> K1 pole B -> K1_RUN -> **U_HOLD** (photo-MOS, self-holding, set only by the REARM set pulse) -> RUN_HD -> **D_RUN** (Schottky) -> RUN_12V. HIGH = latched (K1 AND U_HOLD AND chain live) | HW_LATCH_RB HIGH with LATCH_RUN_RB LOW (> 5 ms, allow for the 1 kHz / 100 Hz sampling difference: use 30 ms) -> **RUN_SHORT** (RUN_12V fed by something other than the latch; fatal, DRV_NSLEEP low, ARM_PERMIT low). HW_LATCH_RB rise only accepted within 150 ms after a debounced rising edge of BOTH REARM_BTN (IOX_A GPB2) and REARM_SET_RB (IOX_D P3); otherwise **LATCH_UNEXPLAINED** (review C1 rule, still wanted as the firmware layer) | IN NETLIST |
| F5 | `REARM_SET_RB` (IOX_D P3) | The REARM **set** contact (J_BTN 1-2) is now a 5 V signal (V5_AUX via 1 k to J_BTN 1, J_BTN 2 -> on-board edge-triggered set stage), **no longer the K1 coil node**. HIGH = set contact closed | REARM_SET_RB and REARM_BTN (aux contact) must agree within 200 ms; disagreement -> **REARM_DISCREPANCY** (withhold arming, report; covers a welded contact and a W-018 short to a contact line). "REARM held > 2 s -> refuse" can now be built from both contacts | IN NETLIST |
| F6 | `HEAD_LOOP2_OK_RB` (IOX_D P2) | New **second, diverse head-loop channel B**: TLV3201 comparator (U46, CMOS push-pull) on its own filter from LOOP_SNS and its own reference divider, driving a new series photo-MOS **U21B** between U21 and U22 (new chain node CH_N6A between U21 and U21B). HIGH = channel B sees the loop closed (loop < about 2.8 kOhm). Channel B detects open/high-resistance only; short detection stays with U30B / U32A | While latched: HEAD_LOOP_OK_RB (GPA5) LOW, or HEAD_LOOP2_OK_RB LOW, or HEAD_LOOP_SHORT_RB HIGH -> ARM_PERMIT low at once (review C2 rule). GPA5 vs P2 disagreement > 20 ms (any state) -> **LOOP_DISCREPANCY made fatal** until REARM after agreement. The ADC copy (PC1) stays as a third, diagnostic view | IN NETLIST |
| F7 | IOX_A GPA5 (HEAD_LOOP_OK_RB), GPA7 (LAB_KEY_N_RB) | Now connected **through 47 k series resistors** (nets HEAD_LOOP_OK_IO, LAB_KEY_N_IO); the comparator / Q22 / Q28 gate nodes can no longer be driven by the expander (M2) | No logic change, same bits and polarity. **GPPU (pull-up) must stay disabled** on these pins (100 k pull-up against 47 k series would read a LOW node as 1.05 V, undefined). Read IODIRA/IODIRB back periodically: fault unless 0xFF/0xFF | IN NETLIST |
| F8 | IOX_A GPB7 (SENTINEL) and PB11 (WDG_STROBE) | GPB7 now through **47 k series** (net WDG_STROBE_IO); WDG_STROBE gets a **10 k pull-down** (defined LOW at reset; an expander pin driving GPB7 can no longer strobe the watchdog) | No logic change. PB11 push-pull drives 0.33 mA more. GPPU off on GPB7 | IN NETLIST |
| F9 | **Watchdog strobe** (m2) | TPS3430 datasheet read (TI SBVS...-rev, fetched 2026-11-27): **WDI is falling-edge triggered** [D]; presets CWD = NC, SET0 = 0, SET1 = 1: tWDL 1.48-2.22 ms, tWDU 23.375-31.625 ms, tRST 170-230 ms; WDI VIL 0.3 VDD, VIH 0.8 VDD [D]. Pin table = circuit.py [D]. Toggling every 10 ms gives falling edges 20 ms apart: 3.4 ms margin to tWDU(min). **New scheme: toggle PB11 every 5 ms** (10 ms period) -> falling edges every 10 ms: 7.8 ms above tWDL(max), 13.4 ms below tWDU(min); also safe if a part treated both edges (5 ms intervals) | `RR_WDG_STROBE_PERIOD_MS` = 5 ms half-period (or a 10 ms period with a LOW pulse of 1-5 ms). Hung-MCU detection: last falling edge + tWDU(max) 31.6 ms (was 43.1 ms worst with the 20 ms falling-edge spacing). README first power-up step 7 to read "falling edge every 10 ms" | IN NETLIST |
| F10 | PB12 (ESTOP_A_RB) and PD2 (HW_LATCH_RB) taps (M3) | Dividers stiffened **100 k / 56 k -> 22 k / 15 k** (R99/R100, R117/R118): with the STM32 pull-down enabled (25 k worst) a node above 7.7 V still reads HIGH; without it above 5.7 V | Still: **GPIO_NOPULL on PB12, PD2, PC13** (taps). PB13 / PC12 (P-FET detectors with 10 k external pull-downs) may keep their pull-downs. U9.B no longer connects to PD2 at all (own tap HW_LATCH_G on RUN_HD), so PD2 configuration cannot affect the nSLEEP gate | IN NETLIST |
| F11 | REARM_BTN (IOX_A GPB2) | Aux contact now feeds GPB2 through a blocking BAT54 (D_RB) + R129 4.7 k (was 10 k) with R130 100 k (was 47 k): HIGH level 2.9 V (was 2.67 V, below the MCP23S17 0.8 VDD = 2.64 V margin); GPB2 configured as an output can no longer reach the set stage | No logic change; GPPU off | IN NETLIST |
| F12 | C_SET / set path (M1, m3, m11) | Series diode **D_RSET** (1N4148W) CHAIN_END -> R_SET: C_SET no longer back-feeds CHAIN_END or the nodes before it; CHAIN_END and every tap now fall with the tap time constant (about 0.8 ms) after an opening. **C_SET is discharged within about 0.3 s whenever CHAIN_END is dead** (Q_SDIS, 1 k), so REARM can set only after the chain has been closed continuously for about 1-2 s (C_SET recharge, tau 2.2 s): "everything healthy, then press" is now enforced in hardware, and re-arm after a drop needs the same wait | PERMIT_STUCK_ON can be judged on CHAIN_END_RB with the normal 5-10 ms filter (no seconds-long blind spot). The REARM lamp "ready" indication should wait >= 2 s of continuous CHAIN_END_RB HIGH | IN NETLIST |
| F13 | Brake relay coil return (M6) | K2/K3 coils now return through a new low-side photo-MOS **U_LS** (RELAY_RTN -> COIL_RTN -> E-stop pole B), whose LED is fed from RUN_HD (live only with a real latch). A board short of RUN_12V to a supply no longer energises the brake relays | Timing unchanged (clamps are across each coil). K2/K3 clamp Zeners 24 V -> 20 V (U_LS / chain photo-MOS off-state stays below 40 V even with RUN_12V held up): brake relay release assumed about 0.3 ms slower; firmware windows (BRAKE_x_RB low within 25 ms) unaffected | IN NETLIST |
| F14 | VMOT decay (m1) | Hardware unchanged (1 kOhm bleed on 3 x 270 uF + 20 uF). Worst case to 1 V: 2.66 s from 14.6 V with +20 % capacitors | `brake.vmot_decay_max_ms` >= 3500 ms (rrch.h already shows 3500) | IN NETLIST |
| F15 | VMOT eFuse enable and nSLEEP gate inputs | U8 EN divider (R133) and the new U9.B tap now on **RUN_HD** (before D_RUN) instead of RUN_12V | None (hardware only); HW_LATCH_RB polarity and pin unchanged | IN NETLIST |

Pins that must have pulls disabled: STM32 PB12, PD2, PC13; MCP23S17 GPPUA = GPPUB = 0x00 (all IOX_A inputs are taps, comparator
nodes behind 47 k, or RC-filtered contact inputs); TCA9535 P17; TCA9534 IOX_C / IOX_D have no pull configuration.
No MCU pin and no existing expander pin moves. No polarity of an existing signal changes.
