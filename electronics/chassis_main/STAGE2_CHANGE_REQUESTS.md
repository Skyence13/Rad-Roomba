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
| Connector | Stage 1 zone | Stage 2 position (centre) | Estimated cable (stage-2 estimate; superseded by the harness generator, IB-57) |
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
* ~~SAFETY_CHAIN clearance in DRC is 0.2 mm~~ — superseded in stage 3: class clearance 0.5 mm and custom DRC rules for the 1.0 mm / 2.0 mm functional clearances and test-point spacing (section 3.2).
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
| F16 | Back-feed window (`CHAIN_BACKFEED_MS`, `chain_end_step` / `rrch_chain_step`) | With D_RSET (F12) C_SET cannot hold CHAIN_END or any node up after an opening | Set `CHAIN_BACKFEED_MS` to 0 for this netlist (hardware revision with S3 overrides): PERMIT_STUCK_ON and CHAIN_IMPLAUSIBLE then have no blind window. Keep the boot-time `ce_live_us` rule only if a rev-A board must still be supported | IN NETLIST |
| F17 | REARM qualification (`rrch_chain_step`) | Hardware now refuses a REARM pressed while the chain is open (C_SET empty) and needs both contacts | Keep the existing rules (edge seen with all elements closed, 250 ms window, LATCH_NO_REARM); add REARM_SET_RB to the qualification (both contacts' rising edges within 100 ms of each other). The 300 ms ARM_PERMIT hold after an early press is no longer needed but harmless | IN NETLIST |
| F18 | Watchdog strobe (already in `rrch_supervise_100hz`: 5 ms high pulse every 10 ms) | Matches F9 | No change needed; falling edges are 10 ms apart | IN NETLIST |

Pins that must have pulls disabled: STM32 PB12, PD2, PC13; MCP23S17 GPPUA = GPPUB = 0x00 (all IOX_A inputs are taps, comparator
nodes behind 47 k, or RC-filtered contact inputs); TCA9535 P17; TCA9534 IOX_C / IOX_D have no pull configuration.
No MCU pin and no existing expander pin moves. No polarity of an existing signal changes.

### 3.2 Netlist / BOM changes (overrides.py S3-xx; please adopt in circuit.py)

| ID | Type | Item | Change | Finding |
|---|---|---|---|---|
| S3-C1a/b | NET | J_BTN pins 1, 2 | SET_CAP / K1_SET → **REARM_SET_SRC** (V5_AUX via R_SSRC 1 k) / **REARM_SET_RAW**: the REARM set contact only signals; the K1 coil node and C_SET stay on the board | C1 |
| S3-C1g | ADD | set stage: R_SSRC, R_SPD, R_SSER, C_SF, D_SCL, D_SET (PESD15VL2BT), C_SC 1 µF, R_SG, D_SGN, Q_SETA, Q_SETB (BSS138 stack), R_AG, R_AGP, C_AG, R_USA, **U_SET** (TLP241A, SET_CAP → K1_SET), R_USK, **Q_HSET** (BSS84), R_SRB, **D_RSET** (1N4148W), **R_SDIS / Q_SDIS / Q_SDISB / R_SDG** (C_SET discharge while CHAIN_END dead), D_RB | set only on (closing edge of the set contact) AND (level of the aux contact); C_SET charged only from a closed chain and emptied when it opens | C1, M1, m3, m11 |
| S3-C1c | NET | R129 pin 1 | REARM_BTN_RAW → REARM_BTN_D (through D_RB) | C1/M2 |
| S3-C1d/h | NET+ADD | K1 pin 8 (NO2) → **K1_RUN**; **U_HOLD** (TLP241A, K1_RUN → RUN_HD, LED self-fed from RUN_HD via R_HA 1.5 k, set via Q_HSET/R_HS 470), D_HR; **D_RUN** (B160, RUN_HD → RUN_12V) | second, diverse hold element; RUN_12V cannot back-feed | C1, M6 |
| S3-C1e | NET+ADD | K1 pin 3 (NC1) → K1_NC1; D_K1B + R_K1B 47 k (3 V bias on K1_SEAL_A), R_NC1/R_NC2/C_NC/D_NC → LATCH_NC_RB | K1 pole A state readable with the chain dead | C1 |
| S3-C1h | ADD | tap R_KR1/R_KR2/C_KR/D_KR: K1_RUN → LATCH_RUN_RB; tap R_U9T1/R_U9T2/C_U9T/D_U9T: RUN_HD → HW_LATCH_G | K1 weld detection; U9 own input | C1, M2 |
| S3-C1f | NET | R133 pin 1 (U8 EN divider) | RUN_12V → RUN_HD | M6 |
| S3-M2d | NET | U9 pin 2 (B) | HW_LATCH_RB → HW_LATCH_G | M2, M3 |
| S3-M6a-d, h | NET+ADD | K2.A2, K3.A2, D31.A, D34.A | COIL_RTN → **RELAY_RTN**; **U_LS** (TLP241A, RELAY_RTN → COIL_RTN, LED from RUN_HD via R_LSA 1.5 k), D_LSR | M6 (RUN_12V short) |
| S3-M6e/f | PART | D32, D35 (K2/K3 clamp Zener) | BZT52C24-7-F → **BZT52C20-7-F** | photo-MOS off-state ≤ 36.5 V in the RUN_12V-short case |
| S3-M1a | NET | R_SET pin 1 | CHAIN_END → RSET_A (behind D_RSET) | M1 |
| S3-C2a/b | NET+ADD | U21 pin 4 → **CH_N6A**; channel B: R_LB1, C_LB1, R_LB2 39 k, R_LB3 10 k, C_LB2, **U46** (TLV3201AIDBVR), C_U46, R_LBG, R_LBR 47 k, Q_LB, R_21BA 680, **U21B** (TLP241A, CH_N6A → CH_N6) | second, diverse head-loop channel in series | C2 |
| S3-M2a/b/c, e | NET+ADD | U43 GPA5, GPA7, GPB7 → HEAD_LOOP_OK_IO, LAB_KEY_N_IO, WDG_STROBE_IO through R_GA5, R_GA7, R_GB7 (47 k); R_WDPD 10 k WDG_STROBE → GND | no logic pin can drive a chain-control node | M2 |
| S3-M3a-f | PART | R99/R100, R117/R118 100 k/56 k → **22 k/15 k**; R129 10 k → 4.7 k; R130 47 k → 100 k | tap valid with STM32 pull-downs; REARM_BTN level margin | M3 |
| S3-F1 | ADD | **U47** TCA9534PWR (IOX_D, 0x22), C_U47, R_D4..R_D7 | new readbacks | — |
| S3-M6g | ADD | TP60 (CH_N6A), TP61 (K1_RUN), TP62 (RELAY_RTN) | test points | — |
| S3-N1a-d | PART | J_TOF4..7 descriptions | LOOK_LO/LI/RI/RO → LOOK_FL/RL/RR/FR (DEC-043) | IB-34 |

Board definition (no netlist change): SAFETY_CHAIN class clearance 0.2 → **0.5 mm**; In4 VBAT_SW/VMOT/VSYS splits with 1.0 mm zone clearance;
`RR-CHS-MAIN.kicad_dru` written by `board.py` from `placement.chain_rules()` and checked by DRC: high-side chain nets ≥ 1.0 mm from supply
nets, loop-sense nets ≥ 2.0 mm from heater nets (J_HEAD1 pin 4/5 pad pair exempt: contract pinout), chain test points ≥ 10 mm from every
other chain and supply test point; TP8/9/38/39/40/50/60/61/62 placed explicitly to meet it (M6).

### 3.3 Consequences for harness and mechanical owners

* **No connector moves and no pin moves.** J_BTN keeps its housing, pins and wires; only the meaning of W-018.1/.2 changes:
  W-018.1 = REARM_SET_SRC (5 V through 1 kΩ, ≤ 5 mA), W-018.2 = REARM_SET_RAW (contact output). The coil pulse no longer runs in
  the cable; the wires stay in the yellow safety loom (a short onto them can no longer set the latch, but keep the pair twisted and
  apart from V12_AUX: a crush shorting a supply onto both REARM contact lines at once is a residual, `chassis_safety_chain.md` #44).
  Harness net labels SET_CAP / K1_SET in `harness/` and `cables.md` W-018 should be renamed.
* Bench step 7 of the safety-chain procedure now applies V12_AUX to J_BTN pin 2: harmless by design.
* Pause/Stop button moved 10 mm outboard (IB-65, CR-08): **no board effect** — J_PAUSE stays at (101.4, 15.2); W-019 length is the
  harness's (its generator reads `out/pinmap.json`).
* New parts are SMD ≤ 4.0 mm (TLP241A SMDIP-4 on top, the rest ≤ 1.6 mm), auto-arranged by the tool in this pass (see README): no part
  enters the front-corner 12 mm zones or the bottom gap-pad area by rule; the height zones of `board_envelopes.yaml` are unchanged.
* `tools/cable_lengths.py` (IB-57) rewritten: it no longer estimates lengths, it reports the harness generator's own lengths next to
  the board connector positions; `reports/cable_lengths.json` keeps its fields for `harness/cross_check.py`.

### 3.4 UNVERIFIED in stage 3

TLV3201 DBV pinout and the TCA9534 pin table (recalled; U45 uses the same); TLP241A ratings, IFT, turn-on/off times (as stage 1);
B160 Vf and rating; G6S-2 must-operate 75 % / must-release 10 % and 4 ms operate/release (family values); TCA953x and STM32G474 input
thresholds and pull-down values; Schottky leakage figures used to choose silicon for D_RSET. Verified in stage 3: TPS3430 WDI falling-edge
trigger, window limits, reset delay and pin table (TI datasheet fetched 2026-11-27).

## Stage 4 (follow-up review fixes) — `docs/reviews/REVIEW_traction_inhibit_followup.md`

Owner: chassis electronics, 2026-11-27. Overrides **S4-xx** in `overrides.py`. Status: **DESIGNED** = decided, written here first for the
firmware engineer; **IN NETLIST** = applied and self-check passed. Stage-3 items not mentioned here are unchanged.

### 4.1 Firmware-relevant changes (chassis firmware engineer: read this first)

| # | Item | Hardware change | What firmware must do / may assume | Status |
|---|---|---|---|---|
| G1 | **SET_READY** (N1) | New comparator on the set reservoir: U33B (spare half of the bus-clamp LM2903B, supplied from VBAT_SW) compares SET_CAP / 4.3 (R_SD1 1.00 M, R_SD2 348 k, hysteresis R_SDH 2.2 M) with CLAMP_REF 2.500 V. Output SET_READY (10 k pull-up to 3V3) is HIGH when C_SET ≥ **10.8 V rising** (10.6-11.0 V; falls again below **≈ 9.3 V**). SET_READY drives a new third FET Q_SETC in the U_SET stack (gate through 100 k / 470 nF: stays on 37-67 ms after SET_READY falls), so **a press while SET_READY is low does not touch the reservoir** | Read **SET_READY_RB = IOX_D P5** (HIGH = the set stage will set now, coil ≤ +45 C). `rearm_ready` (and the blinking REARM lamp) = SET_READY_RB high AND every element closed AND ARM_PERMIT high AND board NTC ≤ 45 C. No fixed 2 s delay. SET_READY_RB high while CHAIN_END has been dead > 1 s (C_SET is discharged then) → **SET_STAGE_FAULT** (comparator stuck; non-fatal, blocks arming) | IN NETLIST |
| G2 | Readiness timing and minimum supply (N1) | R_SET 22 k → **15 k** (charge tau 1.5 s, held-stack-fault coil voltage ≤ 0.94 V < 1.2 V must-release); C_SET discharge now starts only after CHAIN_END has been dead for 41-64 ms (own gate divider + 1 µF, G6) | Expected time from chain closure to SET_READY: t = 1.48 s · ln(Vmax / (Vmax − 10.8)), Vmax = 0.989 · (VBAT_SENSE − 0.5 V): 3.2 s at 12.8 V (worst 4.2 s), 2.8 s at 13.3 V, 4.4 s at 12.0 V (T12). **Minimum supply to arm: VBAT ≥ 11.7 V** worst case (11.4 V nominal; SET_READY never comes below that). Report **REARM_NOT_READY** with reason SUPPLY_LOW (VBAT < 11.7 V and SET_READY low), CHARGING (t < expected), COIL_HOT (board NTC > 45 C: SET_READY may be high but the set margin is not guaranteed) | IN NETLIST |
| G3 | REARM refusal report (N1, N2) | — | **REARM_REFUSED** event + STATE member: aux and set edges seen, no HW_LATCH within 300 ms. Reason: NOT_READY (SET_READY low at the press: reservoir untouched, press again when ready), PARTIAL (K1 closed = LATCH_NC_RB low, HW_LATCH low: drop ARM_PERMIT 50 ms, **not** K1_WELD, not fatal), COIL_HOT, SUPPLY_LOW. Lamp: fast blink for 2 s. ICD and the host fake to carry the same reasons | IN NETLIST |
| G4 | **REARM set contact readback moved to IOX_A GPB6** (N2) | REARM_SET_RB now from REARM_SET_RAW (stage 4: 33 k / 47 k; **stage 5 H1: 10 k / 47 k + BAT54 clamp, ≥ 3.5 V high**) to **IOX_A GPB6 (read at 1 kHz)**; **BUS_CLAMP_ACTIVE moves from IOX_A GPB6 to IOX_D P3** | Sample both REARM contacts at 1 kHz on IOX_A (GPB2 aux, GPB6 set) **without debounce for the edge capture**. Hardware guarantee: a set pulse cannot start before the set contact has been closed for **≥ 3.2 ms** (min, all tolerances; typ 6 ms, max 11 ms; C_SF 2.2 µF qualification, T13), so every press that can set the latch is sampled ≥ 3 times. The pulse ends when the set contact opens (presses of 3-15 ms can give a PARTIAL set, G3). BUS_CLAMP_ACTIVE is diagnostic only: 100 Hz via IOX_D is enough | IN NETLIST |
| G5 | **CH_N6A tap and loop self-test** (N3) | New tap 100 k/56 k/22 nF/BAT54 on CH_N6A → **CHN6A_RB = IOX_D P6**. New test FETs: **LOOP_TEST_A = IOX_D P4** (output; HIGH pulls LOOP_F to ground through Q_LTA → channel A reads "open"), **LOOP_TEST_B = IOX_D P7** (output; HIGH pulls LOOP_FB to ground through Q_LTB → channel B reads "open"). 100 k gate pull-downs: off at power-up. A test output can only force a channel open, never closed | Rules: CHN6A_RB high (CH_N5 live) with channel A comparator open (GPA5 low) for > 10 ms → **U21/Q22 SHORT** (fatal). CH_N8A (BODY_BUMPER_L_RB) high with HEAD_LOOP2_OK_RB low (> 10 ms, U22 and J_BUMP_L closed) → **U21B/Q_LB SHORT** (fatal). **Self-test at every arming (latch down, chain otherwise closed, ARM_PERMIT high)**: assert LOOP_TEST_A 30 ms → GPA5 must go low and CHN6A_RB low; release, wait 20 ms; assert LOOP_TEST_B 30 ms → HEAD_LOOP2_OK_RB low and BODY_BUMPER_L_RB low; release. Any failure → LOOP_FAIL, no arming. Never assert both at once; never while latched (each test opens the chain). Note: during TEST_A the analog copy (PC1, via R76 from LOOP_F) reads open; during TEST_B LOOP_SNS drops by about 6 % (1.56 → 1.46 V), channel A stays closed | IN NETLIST |
| G6 | IOX_D pin map and integrity (replaces the stage-3 pattern) | U47 (TCA9534, 0x22): **P0 LATCH_NC_RB, P1 LATCH_RUN_RB, P2 HEAD_LOOP2_OK_RB, P3 BUS_CLAMP_ACTIVE, P4 LOOP_TEST_A (out), P5 SET_READY_RB, P6 CHN6A_RB, P7 LOOP_TEST_B (out)**. Pattern resistors R_D4-R_D7 removed | Configuration register 0x03 = **0x6F** (P4, P7 outputs), output register P4 = P7 = 0 except during the self-test; check 0x03 and 0x01 every 100 ms and that input bits 4/7 read what was written (replaces the fixed 1,0,0,0 pattern) | IN NETLIST |
| G7 | Head-loop channel B threshold (N6) | R_LB2 39 k → **30.9 k**: channel B passes loop < **1.89 kΩ** (was 2.70 kΩ); tolerance 1.85-1.93 kΩ. Channel A unchanged 0.59-1.55 kΩ | Marginal band 1.55-1.93 kΩ: A open, B closed is **correct** there. With the analog copy in 1.65-2.05 kΩ report HEAD_LOOP_OPEN + "loop resistance high" (non-fatal); LOOP_FAIL (B stuck healthy) only for analog > 2.05 kΩ with B still closed | IN NETLIST |
| G8 | C_SET discharge gate (m-B) | Q_SDISB gate no longer on CHAIN_END_RB / IOX_B P17: own divider R_SDB1 100 k / R_SDB2 56 k from CHAIN_END with C_SDB 1 µF (discharge starts 41-64 ms after CHAIN_END dies; stops 6-13 ms after it returns) | IOX_B P17 is again a pure readback. Read IOX_B configuration register 0x07 back (bit 7 must be 1) with IOX_D 0x03 (m-B) | IN NETLIST |
| G9 | RUN_HD bleed, D_RUN silicon (N5) | D_RUN B160 (Schottky) → **S1G-13-F** (silicon, 0.75-0.85 V at 95 mA [U]); new **R_RHD 10 k** RUN_HD → GND (1.3 mA when latched) | RUN_12V is about 0.4 V lower than in stage 3 (K2/K3 pick-up at the 11.3 V minimum supply: 10.3-10.5 V on the coil, against 8.4 V must-operate at 23 C, 10.4 V at +85 C: marginal only hot AND at minimum supply; then relays_ok never becomes true, which is the existing "cannot drive" path). No firmware change | IN NETLIST |
| G10 | Aux-contact ESD (m-C) | D29 (5.5 V TPD4E05U06) removed; REARM_BTN_RAW / BTN_3V3 on a new **D_AUX PESD15VL2BT** (15 V) | None | IN NETLIST |
| G11 | Held REARM after a latch rise (review §6 b) | — | REARM contact (either) still closed 2 s after a latch rise → withdraw ARM_PERMIT (turns a W-018 crush from "armed for the mission" into "armed for 2 s") | IN NETLIST |
| G12 | Emulator constants (M5) | — | K1 must-operate **9.0 V at 23 C** (75 % of 12 V [D family G6S, U]); must-release 1.2 V; coil 1028 Ω × (1 + 0.00393 (T − 23 C)); operate ≤ 4 ms, release ≤ 4 ms [U]; C_SET 100 µF ±20 %, R_SET 15 k, D_RSET 0.4 V, Vmax = 0.989 (CHAIN_END − 0.4 V), charge tau 1.5 s; SET_READY rising 10.8 V (10.6-11.0 V), falling ≈ 9.3 V; Q_SETC gate on-delay 13-28 ms, off-delay 37-67 ms; set qualification 3.2-11.2 ms after set-contact closure; set pulse ends at set-contact release or 100-170 ms after the closure (T13); U_HOLD turn-on ≤ 3 ms, off ≤ 1 ms [U]; C_SET discharge: starts 41-64 ms after CHAIN_END dies, then tau 0.1 s; SET_READY gives a guaranteed set (≥ 6 ms above must-operate at C_SET −20 %) for a coil ≤ +45 C (T11). Add the 50 C coil case and a PARTIAL-set case (K1 seals, U_HOLD does not, 3-15 ms press) | IN NETLIST |

Pins that must have pulls disabled: unchanged from stage 3, plus IOX_A GPB6 (now a 33 k/47 k divider). IOX_D P4/P7 are outputs.
No MCU pin moves. Expander changes: IOX_A GPB6 (BUS_CLAMP_ACTIVE → REARM_SET_RB), IOX_D P3-P7 (new map above).

### 4.2 Netlist / BOM changes (overrides.py S4-xx; please adopt in circuit.py)

| ID | Type | Item | Change | Finding |
|---|---|---|---|---|
| S4-N1a/b | NET | U33 pins 5, 7 (spare comparator B) | 2IN+ GND → SET_DIV; 2OUT NC → SET_READY | N1 |
| S4-N1 (S3-C1g) | ADD | R_SD1 1 M, R_SD2 348 k, R_SDH 2.2 M, C_SD 10 n, R_SRP 10 k, R_SRR 47 k; **Q_SETC** (BSS138, third stack FET), R_SCG 100 k, C_SCG 470 n | set only when C_SET ≥ 10.8 V; SET_READY_RB to IOX_D P5 | N1 |
| S4-N1c | PART | R_SET 22 k → **15 k** | charge tau 1.5 s | N1 |
| S4-N2 (S3-C1g) | PART/NET | C_SF 10 n → **2.2 µF**; R_SRB 47 k from REARM_SET → **33 k from REARM_SET_RAW** + R_SRB2 47 k | set qualification ≥ 3.2 ms; fast readback | N2 |
| S4-N2a | NET | U43 pin 7 (GPB6) | BUS_CLAMP_ACTIVE → REARM_SET_RB (BUS_CLAMP_ACTIVE → U47 P3) | N2 |
| S4-N3 | ADD | tap R_N6A1/R_N6A2/C_N6A/D_N6A on CH_N6A → CHN6A_RB (U47 P6); **Q_LTA** (LOOP_F), **Q_LTB** (LOOP_FB) with R_LTA/R_LTB 100 k, gates on U47 P4/P7 | readback between the loop photo-MOS, self-test that can only open | N3 |
| S4-G6 (S3-F1) | NET/REMOVE | U47 P3-P7 remapped; R_D4-R_D7 withdrawn | IOX_D map | — |
| S4-mB (S3-C1g) | NET/ADD | Q_SDISB gate CHAIN_END_RB → SDISB_G; R_SDB1 100 k, R_SDB2 56 k, C_SDB 1 µF | IOX_B P17 no longer gates the C_SET discharge; short permit dips keep the charge | m-B, N1 |
| S4-N5 (S3-C1h) | PART/ADD | D_RUN B160 → **S1G-13-F**; **R_RHD** 10 k RUN_HD → GND | no leakage hold of U_LS / U_HOLD | N5 |
| S4-N6 (S3-C2b) | PART | R_LB2 39 k → **30.9 k** | channel B threshold 2.70 → 1.89 kΩ | N6 |
| S4-mC | REMOVE/ADD | **D29 removed** (TPD4E05U06, 5.5 V; its remaining channels were REARM_BTN_RAW, BTN_3V3); **D_AUX** PESD15VL2BT on REARM_BTN_RAW / BTN_3V3 | 12 V-proof ESD on the aux pair | m-C |

New override kind **REMOVE** (expected MPN checked against circuit.py) in `overrides.py`.

Board definition (N4): new net class **CHAIN_CTRL** (0.5 mm) for every photo-MOS LED anode/cathode node, the driver and set-stack gate
nodes and SDIS/SDISB gates (`placement.CTRL_NETS`); DRC rules in `RR-CHS-MAIN.kicad_dru` (from `placement.chain_rules()`):
`chain_to_supply` 1.0 mm (high-side chain nodes and HOLD_A/LS_A/HSET_D against pack/VBAT/VMOT/VSYS/V12/branch outputs),
`hold_led_to_logic` 1.0 mm (HOLD_A/LS_A/HSET_D against 3V3, 3V3A, V5_AUX, V5_BUCK, V5_CM5, BUS_5V, VREF_3V0),
`chain_to_logic` 0.5 mm (high-side chain nodes against the logic supplies: ≤ 5.25 V cannot energise a coil, VMOT or nSLEEP),
`ctrl_to_supply` 0.5 mm (LED/gate nodes against every supply), `led_cathode_to_gnd` 0.5 mm (LED cathodes, stack nodes, RELAY_RTN
against GND); pads of one footprint are exempt (`A.Parent == B.Parent`, inherent to the pinout, e.g. U30 pins 7/8 — channel B
covers that bridge). Test points: TP44 (3V3) and TP45 (V5_AUX) added to the 10 mm spacing rule; TP50 moved to (122.5, 3.0).

### 4.3 Consequences for harness and mechanical owners

* No connector, pin or wire changes. `harness/cables.md` W-018 note (owner: harness, review m-D): its cross-reference should read
  "chassis_safety_chain.md section 6 rows 42-46" and the lay instruction should be replaced by "single shorts onto either REARM
  contact line are harmless by design; a multi-pair crush can arm once (section 6.1 item 5)". The aux pair now has a 15 V ESD part.
* New parts are SMD ≤ 4 mm (no new TLP241A): no height-zone change.
* Operator / service procedures (`docs/service/`, owner: lead): pre-use check P1 and the 6-monthly service test S3-S8 of
  `chassis_safety_chain.md` §6.2; "use OFF, not SERVICE, for work at the wheels"; REARM only when the lamp says ready.

### 4.4 UNVERIFIED in stage 4

S1G-13-F Vf and reverse leakage; BSS138 / BSS84 off-state leakage at temperature; TLP241A lowest holding LED current (0.1 mA
assumed); G6S-2 must-operate and operate time (T11 relies on them); LM2903B output and the LM4040C tolerance as recalled; X7R
DC-bias derating of C_SF/C_SC (folded into the −20 % corner); the +45 °C coil design limit is an assumption on the environment.

## Stage 5 (stage-4 review) — `docs/reviews/REVIEW_traction_inhibit_stage4.md`

Owner: chassis electronics, 2026-11-28. Overrides **S5-xx**. Firmware-relevant items first (status DESIGNED → IN NETLIST as applied).

### 5.1 Firmware-relevant changes

| # | Item | Hardware change | What firmware must do / may assume | Status |
|---|---|---|---|---|
| H1 | GPB6 (REARM_SET_RB) level (review S3) | R_SRB 33 k → **10 k**, R_SRB2 stays 47 k, new **BAT54 clamp D_SRB to 3V3** (as every chain tap) | HIGH level is now the clamp level VDD + 0.1…0.3 V, **≥ 3.5 V worst case** against MCP23S17 VIH(max) 0.8 VDD = 2.73 V (margin ≥ 0.75 V); LOW 0 V (≤ 0.05 V with ESD leakage) against VIL(min) 0.65 V. No logic change; GPPU stays off | DESIGNED |
| H2 | Board NTC position (review S2) | **RT1 moved next to K1** (top side at board (80.5, 26.0), 3.5 mm from K1's coil end); same net NTC_BOARD_ADC / PC4 | `board_c` is now the board temperature **at K1** (8 mm from U8, 26 mm from U6; no longer "beside the H-bridges"). Coil estimate for COIL_HOT: **T_coil = T_RT1 + ΔT_self**, ΔT_self = 10 K × f, f = first-order filter (τ 300 s) of the latch-set state (coil 0.17 W at 13.3 V, assumed 60 K/W [A]); set `REARM_NTC_OFFSET_K` to 0 and use the self-heat term instead. COIL_HOT stays a warning (the press is still offered; the hardware decides; T11). Expect COIL_HOT after long armed periods at board ≥ 35 °C and after hard driving in a warm trailer | DESIGNED |
| H3 | Analog loop copy independent of channel A (review S4) | R76 (HEAD_LOOP_SENSE feed) from LOOP_F → **LOOP_SNS** (filter now R76 10 k / C79 10 n, 0.1 ms) | HEAD_LOOP_SENSE (PC1) no longer follows LOOP_TEST_A or a stuck Q_LTA: during TEST_A expect the analog copy to stay OK; during TEST_B it drops about 6 % (still OK band). A Q_LTA D-S short now reads "A open, B closed, analog OK" = LOOP_DISCREPANCY / self-test failure, no longer "B stuck healthy". Average the ADC over ≥ 1 ms (the 1 ms RC is gone from this path) | DESIGNED |
| H4 | PARTIAL-set permit dip (review D1: T13 50 ms vs firmware 200 ms) | — | Both are safe. **Recommendation: 30 ms**: K1 releases in ≤ 4 ms [U]; the C_SET discharge cannot start before 41 ms (C_SDB), so a 30 ms dip keeps the reservoir and the operator can press again at once. 200 ms empties C_SET (next press after 2.3-6 s, T12). The general "≥ 50 ms after a drop" rule stays | DESIGNED |
| H5 | Low-battery warning before re-arm becomes impossible (operating limits) | — | Warning **BATTERY_REARM_LOW at VBAT ≤ 12.0 V** (resting, filtered ≥ 10 s): "re-arming may become impossible below 11.7 V"; BATTERY_LOW stop stays 11.2 V. Between 11.7 and 11.2 V an armed robot keeps driving but cannot be re-armed after a stop | DESIGNED |
| H6 | Held press (review S5) | — | Report REARM_HELD_AFTER_SET when the W-018 rule drops the latch; raise the limit to **5 s** (crush case then arms for 5 s); buzzer while held > 1 s. Operator text: "press briefly (< 2 s)" | DESIGNED |
| H7 | Service header J_SVC (S1) | New top-side 2 × 5 box header **J_SVC** carrying CHAIN_END, K1_RUN, RUN_HD, RUN_12V, RELAY_RTN, HOLD_A, LS_A, CH_N6A, SET_CAP through **220 kΩ** each, plus GND | No firmware change. The tests in `chassis_safety_chain.md` §6.2 use a meter only; S3/S6 use the existing test firmware | DESIGNED |

No MCU pin moves; no expander pin moves; no new readback (a U_LS off-state readback was evaluated and rejected: §6.2).
