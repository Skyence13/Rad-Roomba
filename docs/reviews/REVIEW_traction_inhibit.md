# Independent review: traction inhibit (hardwired chain ↔ chassis firmware ↔ motion commands)

Reviewer: independent second engineer (did not design any of it). Date: 2026-11-27. Status: review findings only; nothing in the project was changed. This is not a safety assessment against any standard: the design states it is not a certified safety system, and the purpose here is to check that its claims and stated limits are true and complete.

## 1. Scope, method, confidence tags

**Question asked.** Can the robot move, keep moving or restart when it must not? Is every claim that "the hardware stops it regardless of firmware" true of the circuit as drawn?

**Read (primary sources):** `electronics/chassis_main/design/circuit.py` (all of it), `electronics/chassis_main/overrides.py`, `out/pinmap.json`, `out/RR-CHS-MAIN.net`, the `Relay:G6S-2` symbol embedded in `chain_2.kicad_sch`, `RR-CHS-MAIN.kicad_pcb` (track geometry only), `STAGE2_CHANGE_REQUESTS.md`, `design/CONTRACT_CHANGE_REQUESTS.md`, `electronics/analysis/chassis_safety_chain.md` (all), `chassis_braking.py`, `chassis_braking_tables.md`, `chassis_design_notes.md`, `chassis_design_review_checklist.md`, `circuit_description.md`; firmware `core/rrch.h`, `rrch_chain.c`, `rrch_core.c`, `rrch_motion.c`, the motion and re-arm parts of `rrch_proto.c`, `port/stm32g474/src/bsp.c`, `main.c`, `include/board_pins.h`, `port/host/sim.c`/`sim.h`, `tests/test_chain.c`, `tests/test_state_machine.c` (the relevant sections), `pinmap.yaml`, `README.md`, `CONTRACT_CHANGE_REQUESTS.md`; `interface/system/contract.yaml` (safety_chain, enums), `interface/chassis_icd.md` (§1.3, §3.6, §5), `docs/architecture/SYSTEM_ARCHITECTURE.md` §6, `docs/architecture/INTEGRATION_BACKLOG.md` IB-01, 02, 03, 13, 16, 24, 34, 60, `harness/cables.md` (W-005, W-015…W-022).

**Ran:**
- `python3 electronics/chassis_main/overrides.py`: override log as expected, stage-1 self-check on the overridden netlist PASSED.
- `firmware/chassis/check.sh` (build directory redirected to the scratchpad): all five steps passed, 311 + 1187 + 2476 unit checks, integration tests, both STM32 images.
- Throwaway scripts in `/tmp/claude-0/-home-user-Rad-Roomba/243ed1e7-dcf1-5450-82ee-f4f91fbe9462/scratchpad/review_chain/`: `q.py` (everything on a net in circuit.py + overrides), `cmpnet.py` (KiCad netlist export compared with the Python netlist for the 67 chain and drive nets: **0 differences**), `calc.py` (back-feed, pull-down, VMOT decay and set-pulse numbers), `clear.py` (routed track clearances of chain nets to supply nets).
- A **patched copy of the emulator** (`…/review_chain/emu/`, repository untouched): three fault models added (K1 coil fed from CHAIN_END without REARM; head-loop comparator stuck "healthy"; C_SET back-feed of CHAIN_END) and HW_LATCH modelled as the tap on RUN_12V that it is on the board. `review_test.c` and `review_test2.c` drive the unmodified firmware core through it.

**Confidence tags used below:**
**[N]** verified in the netlist (circuit.py + overrides; the chain nets also checked against the KiCad export) · **[P]** verified in placement/routing data (`pinmap.json`, `.kicad_pcb`) · **[F]** verified in firmware source · **[E]** demonstrated in the patched emulator copy (simulated, my fault model) · **[C]** my calculation from netlist values · **[I]** inferred from a description or a recalled datasheet value, not verified.

## 2. Summary

| # | Sev. | Finding (one line) |
|---|---|---|
| C1 | Critical | "No restart without REARM" rests on K1's contacts and the off-board REARM wiring. A welded K1, or a short of V12_AUX or LAMP_REARM_K onto K1_SET in the REARM cable, lets the latch set by itself. Nothing detects it: the firmware check claimed in rows #39/#40 does not exist, the brake test cannot see it, and the emulator models it wrongly. Demonstrated: the robot drives again 60 ms after a bumper is released, with no REARM. |
| C2 | Critical | Head-rail loop: the firmware "second channel" claimed in rows #18/#22 only raises a non-fatal warning. Credible single faults (U30 pin 1 open, U30 pin 7 to pin 8 solder bridge, R74 shorted) leave a pressed rail with no effect at all. Demonstrated: the robot drove 300 mm with the rail open. |
| M1 | Major | C_SET back-feeds CHAIN_END (and the nodes after an opened element) through R_SET. Readbacks are wrong for seconds after every drop. PERMIT_STUCK_ON fires falsely after any ARM_PERMIT withdrawal about 2 s or more after arming (brake test included), and after resets, giving FAULT and a watchdog reset loop. The HANDS-ON lamp stays dark after HANDS-ON is pressed. |
| M2 | Major | The firmware can bypass U21/U22. Their comparator gate nodes are also bidirectional expander pins, so "nothing can back-drive the chain" (§2.3) is false for HEAD_LOOP_OK_RB and LAB_KEY_N_RB. U9's input is also a firmware-configurable MCU pin. |
| M3 | Major | The internal pull-downs enabled on PB12 (ESTOP_A_RB) and PD2 (HW_LATCH_RB, also U9.B) load the 100 k/56 k taps below a valid high at normal pack voltages. Result: false ESTOP_DISCREPANCY, and U9's input depends on firmware configuration. |
| M4 | Major | Seven further claimed detections or paths do not exist in firmware or the port: the MCU's own watchdog, refusal on a held REARM, the boot "K1 not welded" check, the TIM8 break path, and others. |
| M5 | Major | The emulator differs from the netlist exactly where these faults live: HW_LATCH, C_SET, the watchdog and the windows. Tests reported as closing IB-01/02 pass on signatures the board cannot produce. |
| M6 | Major | A board-level short of RUN_12V or CHAIN_END to a supply is missing from the table. It removes every element except E-stop pole B. The CH_N0 and CHAIN_END test points are 4.25 mm apart. |
| m1–m11 | Minor | VMOT decay limit too tight for capacitor tolerance; watchdog strobe-edge margin; REARM pre-arm window; minimum opening width not stated; wrong designators in the fault table; one I2C read failure drops the latch; other items in §3.3. |
| o1–o5 | Obs. | PAUSE keeps traction energised; no hardware speed or force limit; brake-model inputs and slopes; positive checks. |

## 3. Findings

### 3.1 Critical

#### C1. The latch can set without REARM, and nothing notices

**Evidence.**
- [N] RUN_12V (the only supply of K2/K3 coils `A1`, U8 EN divider R133/R134 and the HW_LATCH_RB tap R117) has exactly one source: K1 pin 8 (NO2), whose common K1 pin 9 is CHAIN_END. The K1 coil node `K1_COIL_P` connects to K1.1 (coil+), K1.5 (NO1, seal-in, fed from CHAIN_END via D_SEAL and COM1), D15 (clamp), and R96 (0 Ω) → `K1_SET` → **J_BTN pin 2, off the board**. So "no restart without REARM" is implemented by K1 pole A/B alone, plus the integrity of the REARM device wiring.
- [N]/harness: J_BTN pin 6 = V12_AUX (12 V from F_AUX) and pin 7 = LAMP_REARM_K run in the same 6-core cable W-018 to the same illuminated button as pin 2 = K1_SET (`harness/cables.md` W-018.2/.5/.6, `hdata_conn.py` REARM-DEV "12 V LED block"). V12_AUX on K1_SET energises K1 permanently. LAMP_REARM_K on K1_SET feeds the coil through the lamp while the lamp driver is off, which is the case whenever latched (`rrch_core.c` 622–625), so it holds K1. Either short is equivalent to a welded K1 and **is not in the fault table**.
- [F] Firmware has no correlation between a HW_LATCH rise and a REARM press. `rrch_chain.c` 347–357 clears all latched hardware reasons on any latch rise. `di_changed()` (56–71) only calls `rrch_rearm_sw()` on a REARM edge. LATCH_STUCK (271–274) fires only for `latch && !arm_permit`, and ARM_PERMIT is high in STANDBY/HW_INHIBIT (`rrch_core.c` 711–713). Row #39 says "firmware sees HW_LATCH_RB rise without a REARM_BTN event … → ARM_PERMIT low, watchdog strobe stopped, FAULT". **Not implemented.**
- [N]+[F] The brake test cannot see a weld. HW_LATCH_RB taps RUN_12V, which is fed from CHAIN_END, so when step 1 drops ARM_PERMIT (`rrch_core.c` 315–346) RUN_12V dies whether or not K1 is welded. §7's "K1 is not welded at boot (#39, #40)" refers to a boot step 2 that is not implemented (IB-60 lists only the watchdog half of it).
- [F] The emulator's `latch_weld` (`sim.c` 79 `SET(HW_LATCH, s->latch)`, 328) keeps HW_LATCH high with the chain open, which the board cannot do. The test "welded latch fails, latches BRAKE_TEST_FAIL" (`test_state_machine.c` 516–531) therefore proves nothing about a real weld.
- [E] With the K1 coil fed from CHAIN_END (pole A welded / K1_SET short) and the host streaming DRIVE at 50 Hz (`review_test.c` A): the bumper hit stopped the robot after 3.5 mm. After the bumper was released, **with no REARM**, the latch re-set, the first DRIVE was accepted 60 ms later and the robot drove 326 mm in 5 s. With the weld present from power-up (`review_test2.c` D), no REARM was ever pressed. The latch set as soon as ARM_PERMIT went high, the HOST_LINK_LOST stop was cleared remotely by REARM_SW, BRAKE_TEST **passed**, and the robot drove 132 mm. The only network operations involved were REARM_SW and DRIVE, contradicting `contract.yaml` safety_chain.rearm "No network path can set the hardware latch" in effect.

**Why it matters.** A person trips the bumper or head rail, the robot stops, the element re-closes (the person steps back or the bumper springs back), and traction power returns with no local action. The firmware reports ARMED_IDLE with no reasons (ICD §5.1 says a momentary cause "stays reported until an operator has re-armed at the robot"; the firmware equates "latch readback high" with "operator re-armed"). A host that resumes on ARMED_IDLE re-drives into the same place after the 1.5 s alert. Pre-use check 5 ("none restarts by itself", `docs/service/01_operator_procedures.md`) would find a pre-existing fault only if run, and not one arising mid-mission.

**Proposed change.**
1. Firmware: accept a HW_LATCH rise only within about 150 ms after a debounced REARM_BTN rising edge (the second, separate contact). Otherwise latch a new fault LATCH_UNEXPLAINED (the contract already has the enum): ARM_PERMIT low (U24 is upstream of K1 pole B, so this removes RUN_12V even with K1 welded), stop DRIVE, FAULT. Also treat "HW_LATCH high in STANDBY/HW_INHIBIT with no REARM edge" the same way; this is the continuous form of §7 step 2.
2. Emulator: HW_LATCH = K1 closed AND CHAIN_END live AND pole B (the RUN_12V tap). Add a "K1 coil fed from CHAIN_END" fault and replace the `latch_weld` test with one that checks (1).
3. Hardware rev B: do not take the K1 coil node off the board. For example, let the REARM contact switch a low-voltage signal into an on-board set circuit, or put a diode plus an on-board series element so that 12 V on the cable cannot reach the coil. Feed the REARM lamp from a supply that cannot hold the coil. The force-guided K1 with a mirror contact read by the MCU (already the doc's first upgrade) closes it properly.
4. Add the rows "V12_AUX or LAMP_REARM_K shorted to K1_SET (W-018 / REARM device)" to §6, and a bench step to §8 step 7: "apply V12_AUX to J_BTN pin 2 with all elements closed: the firmware must fault within 0.2 s and the latch must drop".

#### C2. Head-rail loop: credible single faults leave no barrier, and the claimed firmware second channel does not act

**Evidence.**
- [N] Open-loop detection is done only by U30A (1IN+ = LOOP_F, 1IN− = LOOP_VLO). U30B detects only a short. Both outputs (U30.1, U30.7) are wired together with the 10 k pull-up **R74** (3V3), the gate of Q22 (U21 LED driver) and MCP23S17 GPA5 (net HEAD_LOOP_OK_RB). Anything that stops this node going low keeps U21 closed: U30A output unable to sink, **U30 pin 1 open** (solder joint), **R74 shorted**, the node shorted to 3V3 or V5_AUX, or R72 (divider bottom) shorted.
- [P] U30 pin 7 (HEAD_LOOP_OK_RB) is the neighbour of U30 pin 8 (VCC = V5_AUX) at 1.27 mm pitch on the bottom side. A solder bridge there holds the node at 5 V. R74's own pads are 1.65 mm apart. These are ordinary assembly defects.
- [F] The firmware second channel only warns. `rrch_chain.c` 213–218 computes the ADC loop state and sets **LOOP_DISCREPANCY after 200 ms, which is not in RRCH_FLT_FATAL_MASK**. ARM_PERMIT (`rrch_core.c` 711–713) does not depend on it or on `hw_live & HEAD_LOOP_OPEN`. `mode_eval()` (630–662) uses `hw_live` only for CHARGER and LAB_KEY, and no protective-stop reason exists for the loop. CHAIN_IMPLAUSIBLE (`n8a && !n7`, line 239) needs the comparator itself to report "open", so it does not apply. Row #18 claims "withdraws ARM_PERMIT on disagreement; then stopped by firmware". **Not implemented.** Row #22 claims the same for the divider faults.
- [E] With the comparator stuck healthy, the loop opened (rail pressed) at 0.10 m/s for 3 s: latch still set, ARM_PERMIT high, robot moved **300 mm**. Only LOOP_DISCREPANCY was raised (`review_test.c` B).
- Context: the MCU has no forward or side ranging (`SYSTEM_ARCHITECTURE.md` §6.3, IB-13). In front, the head rail is the only protection that does not depend on the host.

**Why it matters.** One undetected component or assembly fault removes the only non-host frontal contact protection, and the robot then pushes into a person at survey speed. The doc presents this case as caught by firmware.

**Proposed change.**
- Firmware: while the latch is set, withdraw ARM_PERMIT at once (no 200 ms filter in the "open" direction) when the ADC loop state is not OK, when HEAD_LOOP_SHORT_RB is asserted, or when comparator and ADC disagree. Make LOOP_DISCREPANCY block ARM_PERMIT until a REARM after agreement. More generally: any element known OPEN (`hw_live != 0`) while HW_LATCH is high means the hardware failed to drop, and that should be permit-low + fault.
- Hardware rev B: the doc's second, diverse loop evaluation with its own series photo-MOS. Meanwhile, put U30 pins 1/7/8 and R74 on the AOI/inspection list, and make "press each rail zone and see the latch drop" a recorded pre-use step.
- Correct rows #18 and #22, and add "U30 pin 7–8 bridge / R74 short / HEAD_LOOP_OK_RB shorted to a supply" as named faults.

### 3.2 Major

#### M1. C_SET back-feeds the chain through R_SET: readbacks are wrong after every drop, and the ARM_PERMIT supervision produces false faults

**Evidence.** [N] Net CHAIN_END = {D_SEAL.A, K1.9, R115 (tap), R_SET, TP38, U24.4}. R_SET (22 k) joins it to SET_CAP (C_SET 100 µF), with no diode. Once K1 has released, nothing but the 156 k taps loads CHAIN_END and the nodes connected to it through still-closed elements. C_SET, charged to about 12.8 V while latched, then holds those nodes up. [C] (`calc.py`):

| Element that opened | Held node | Reads HIGH on MCP23S17 / TCA9535 for | τ |
|---|---:|---:|---:|
| U24 (ARM_PERMIT low) | 11.2 V | 7.5 s / 9.9 s | 17.8 s |
| U23 (watchdog) | 10.0 V | 3.1 s / 4.4 s | 10.0 s |
| bumper L | 8.2 V | 0.7 s / 1.5 s (indeterminate band for 9 s) | 6.1 s |
| HANDS-ON | 6.0 V (tap 2.16 V) | in the undefined band for about 5 s | 4.2 s |

C_SET recharges with τ = 2.2 s after each REARM press (7.6 V after 2 s, 10.7 V after 4 s).

**Consequences.**
- [F]+[E] `chain_end_step()` (`rrch_chain.c` 110–144) counts `p_low && chain_end` and sets **PERMIT_STUCK_ON (fatal, and stops the strobe)**. Emulated: BRAKE_TEST 0.3 s after REARM passed. BRAKE_TEST **4.3 s after REARM gave PERMIT_STUCK_ON, FAULT and 12 watchdog-forced MCU resets** (`review_test.c` C). On the board, any reset or power cycle within about 10 s of a latched period boots into the same false fault, because C_SET still holds CHAIN_END up.
- [C] After a bumper hit, BODY_BUMPER_L reads closed again 50 ms (close debounce) after K1 releases, while the bumper is still pressed. `rearm_ready` and the blinking REARM lamp then invite a REARM that cannot latch.
- [C]/[I] The HANDS-ON lamp is dark for about 1.5–3 s after HANDS-ON is pressed while armed. The back-fed CH_N3 tap at about 2.2 V holds Q25 on; Vgs(th) 0.8–1.5 V is recalled. The contract says the lamp is "illuminated from the actual chain state".
- [I] Where tap inputs with different thresholds sit in the undefined band (TCA9535 has no hysteresis; STM32 PC13 is not Schmitt-limited the same way as the MCP23S17), CHAIN_IMPLAUSIBLE (fatal) can also trip on ordinary openings.

**Why it matters.** It is fail-safe in the motion sense, but it makes the PERMIT_STUCK_ON detection for row #38 unusable as built. The obvious firmware workaround (wait seconds before judging CHAIN_END) would turn that detection into a seconds-long blind spot. The readback-based element states and the lamp are not truthful after a drop.

**Proposed change.** A small-signal diode in series with R_SET (anode at CHAIN_END), so C_SET charges from CHAIN_END but cannot feed it. Keep D_SEAL. The held-REARM case stays at about 0.6 V on the coil. Then add the back-feed case to the emulator, as a regression for the fix. Do not fix this in firmware by lengthening timeouts.

#### M2. Firmware-reachable bypass of the loop and LAB elements; U9's input is an MCU pin

**Evidence.** [N] HEAD_LOOP_OK_RB is the gate net of Q22, which drives U21's LED. LAB_KEY_N_RB is the gate net of Q28, which drives U22's LED. Both are open-collector comparator outputs with 10 k pull-ups and are wired directly to MCP23S17 GPA5 and GPA7, pins whose direction is set by a register. HW_LATCH_RB is U9.B and is also wired to STM32 PD2. §2.3 claims "nothing can back-drive the chain … at most 33 µA". That is true for the 100 k taps, false for these three nets. [F] The firmware never writes IOX_A's IODIR (`bsp.c` 392–395 only reads it), so this needs a firmware defect or SPI corruption on SPI1, which is shared with the IMU. [I] Whether an MCP23S17 output-high overrides a sinking LM2903B depends on drive strengths (about 25 mA source against 6–16 mA sink): plausible, not certain. PD2 driven as an output removes the U9 path without question.

**Proposed change.** Fit 10–47 k series resistors between each comparator node and its expander pin, and between the RUN_12V tap and PD2, or give U9 its own tap. Then no logic pin can drive a chain-control node. Firmware: read IODIRA/B back periodically and fault unless both are 0xFF. Correct §2.3.

#### M3. Internal pull-downs on two tap inputs defeat the tap design and make U9 depend on firmware configuration

**Evidence.** [F] `bsp.c` 128 and 130 enable GPIO_PULLDOWN on PB12 (ESTOP_A_RB) and PD2 (HW_LATCH_RB). [N] Both are 100 k/56 k taps (R99/R100 on CH_N2; R117/R118 on RUN_12V), and PD2 is also U9.B. [C] Pin voltage for RPD 25/40/55 k [I, STM32 values recalled]: at a 13.2 V node 1.95/2.50/2.87 V; at 12.0 V 1.77/2.27/2.61 V; at 11.2 V 1.65/2.12/2.43 V. Compare VIH 0.7 VDD = 2.31 V (or 1.88 V if the TT formula applies) and 74LVC1G08 VIH 2.0 V.

**Why it matters.** With the chain live, ESTOP_A can read open while pole B reads closed, giving ESTOP_DISCREPANCY (fatal) at normal and low pack voltage. HW_LATCH can read low or chatter, and U9 can hold the bridges asleep or toggle nSLEEP. All of this is fail-safe, but erratic. More importantly, the "hardware" nSLEEP gate's input level depends on how firmware configures a pin. §2.3's "reads high above 7.4 V" holds only for the MCP23S17 inputs.

**Proposed change.** Use GPIO_NOPULL on PB12 and PD2; the external 56 k already defines the open-wire level. Recompute the read thresholds per input type at a 10 V pack and state them.

#### M4. Further claimed detections or paths that are not implemented (beyond IB-60's boot watchdog test)

[F] Each of the following appears as a mitigation in `chassis_safety_chain.md` and does not exist in `core/` or `port/stm32g474/`:

| Claim | Where | Reality |
|---|---|---|
| "MCU's own independent watchdog (firmware)" | row #37 | IWDG never configured; only the reset-cause flag is read (`bsp.c` 733) |
| "firmware flags REARM_BTN held > 2 s and refuses ARM_PERMIT" | rows #42, #43 | no held-button logic anywhere; ARM_PERMIT does not depend on REARM_BTN |
| firmware detects latch rise without REARM | rows #39, #40 | absent (C1) |
| ADC cross-check withdraws ARM_PERMIT | rows #18, #22 | absent (C2) |
| "TIM8 break input on HW_LATCH_RB is a fourth, firmware-configured, path" | §2.1 | break deliberately disabled (`bsp.c` 203–204; README "TIM8 break input is not used") |
| boot test U23/U24 and "K1 not welded at boot" | rows #16 (U23), #34, #36; §7 step 2 and table | not implemented (the watchdog half is in IB-60); the K1 half cannot be done by the runtime test (C1) |
| summary paragraph "detected / stopped by firmware" for #18, #23, #39 | §6 summary | true only for #23 (CHAIN_IMPLAUSIBLE when the comparator reports open) |

**Proposed change.** Either implement each one or strike it from the table, and re-derive the "undetected dangerous faults" summary. With #34/#36 the watchdog element is latent for the life of the board, not "between boots". Add the list to IB-16.

#### M5. The emulator differs from the netlist where the faults live

[F] vs [N]:
- `sim.c` 79: HW_LATCH = K1 armature, where the board has a tap on RUN_12V. This hides C1.
- No R_SET/C_SET path. This hides M1.
- Watchdog model trips at "no strobe 35 ms, any edge" (`sim.c` 117–124, 419); the hardware is TPS3430 tWDU 23.4–31.6 ms with WDI edge polarity to be confirmed (m2).
- LAB window modelled as "not 900–2500 Ω" (`sim.c` 35, 73); the hardware is a pass window of 3.92–5.64 kΩ, so "no head" passes in the model and fails on the board.
- Loop window 600–1600 Ω against 590–1550 Ω.

IB-01/02 are recorded as "Closed in firmware" on tests run against this model. Proposed change: align these five points and add the three fault models used here (`…/review_chain/emu/sim.c` shows a minimal form).

#### M6. A board-level short of RUN_12V or CHAIN_END to a supply is missing from the fault table

**Evidence.**
- [N] RUN_12V to VBAT_SW, V12_AUX or VSYS energises K2/K3, U8 and HW_LATCH with the whole chain bypassed. Only E-stop **pole B** (COIL_RTN) still drops the relays.
- [F] Firmware has no rule for "latched without REARM", so a host DRIVE is accepted.
- [N] CHAIN_END to a supply bypasses U23/U24 as well; after one REARM, K1 self-holds through the short. [F] The firmware sees `n9_dead && chain_end` → CHAIN_IMPLAUSIBLE → FAULT, and the remaining barrier is firmware's DRV_NSLEEP low through U9. ARM_PERMIT and the watchdog are upstream of the short and cannot open it.
- [P] Test points TP50 (CH_N0 = fused VBAT_SW) and TP38 (CHAIN_END) sit 4.25 mm apart on the bottom side; one bench clip across them bypasses everything except pole B. TP39 (RUN_12V) is 5.8 mm from TP42 (VSYS).
- `STAGE2_CHANGE_REQUESTS.md` line 82: the SAFETY_CHAIN DRC clearance is 0.2 mm, not the 0.5/1.0 mm functional rule. [P] My track-to-track check found no chain track within 3 mm of VBAT_SW/VSYS/VMOT tracks; pours were not assessed.

**Proposed change.** Add rows for "RUN_12V / CHAIN_END / K1_COIL_P shorted to a supply (board)". The C1 firmware rule turns the RUN_12V case into FAULT with nSLEEP low. Move TP38/TP39 away from the supply test points. Run a zone-aware clearance check of the chain nets against the 1.0 mm rule before release.

### 3.3 Minor

- **m1 — VMOT decay limit too tight.** [C] `brake.vmot_decay_max_ms` = 2500 ms. With 3 × 270 µF at +20 % plus 20 µF (992 µF) and a 1 k bleed, decay to 1 V takes 2.57 s from 13.4 V and 2.66 s from 14.6 V. Result: false VMOT_NOT_REMOVED (BRAKE_TEST_FAIL) and a spurious latched VMOT_FAULT after drops on a full pack (`rrch_chain.c` 329). Use 3.5 s, or derive the limit from the τ measured at commissioning.
- **m2 — Watchdog strobe-edge margin.** [I] `h_strobe` toggles PB11 every 10 ms. If TPS3430 WDI is falling-edge triggered (my recollection; confirm in the datasheet), valid strobes are 20 ms apart against tWDU min 23.4 ms: 3.4 ms of margin for ISR latency and `irq_lock` sections. Strobe as a short pulse every 10 ms instead, and correct README §first power-up step 7 ("one edge every 10 ms").
- **m3 — REARM "pre-arm" window.** [C] The set pulse keeps K1 above a typical hold level for about 0.1 s and above must-release for 0.245 s. If the chain closes inside that window (bumper or HANDS-ON released just after pressing REARM, or ARM_PERMIT rising), the latch sets. "Everything healthy, then press" is not enforced. With C1's rule, also reject a latch rise if any element was known open at the REARM edge.
- **m4 — Minimum opening width not stated.** [I] Openings shorter than the K1/K2/K3 drop-out (well under 4 ms) may not drop the latch. They are also invisible to firmware (tap τ 0.8 ms, 1 kHz sampling, `rrch_chain.c` 183 immediate open). State the minimum opening that is guaranteed to drop, and add a pulse-width test to §8 step 8.
- **m5 — Fault-table designators do not match the netlist.** Rows #21, #22 and #26 use refs that do not match circuit.py [N]: loop source/sense are R65/R68 (not R70/R71); the divider is R70/R71/R72 (top/middle/bottom); R73 is the 2.2 M keep-alive; R74 is the HEAD_LOOP_OK_RB pull-up; R80 is in the LAB divider. A fault insertion by designator would test the wrong part, and the real "R74 short" is a C2 fault.
- **m6 — K2/K3 coil supply described wrongly.** §2.1 "K2 and K3 take their coil supply from CHAIN_END" and T2 "VMOT removal waits for K1": [N] K2.A1, K3.A1, the U8 EN divider and the HW_LATCH tap are all on RUN_12V (K1 pole B). Drop timing is fine (the source is still CHAIN_END; CCR-CHS-11 b), but the text hides that "no restart without REARM" is K1 alone (C1).
- **m7 — One failed I2C read drops the latch.** [F] A single failed IOX_B read sets `chain_end_known = false` (`rrch_chain.c` 116–118), so the permit falls at once (`rrch_core.c` 713) and the latch drops while driving. The bus is shared with the charger, INA228, INA3221 and IOX_C, uses 5 ms HAL timeouts and has no bus-recovery code. It is safe, but any I2C glitch ends an unattended mission. Withhold arming on stale data; while latched, require several consecutive failures or an age above about 50 ms. Add SCL recovery.
- **m8 — IOX_B output writes are not supervised.** [F] Failures only retry (`bsp.c` 771–775); panel LEDs and the REARM lamp can freeze in a stale state without a fault.
- **m9 — HANDS-ON lamp feed beside the contact.** [N]+harness: the lamp + (HANDS_LAMP_P) is the upstream chain node CH_N2, routed beside the contact pair in W-017 to the same device. A lamp-to-contact short bypasses HANDS-ON. Row #9 covers the effect; name the cause and keep "lamp dark = not confirmed" in operator training.
- **m10 — Bootloader pin states unverified.** [I] "In the ROM bootloader all outputs are high-Z" (README, pinmap) is not verified against AN2606; bootloader peripherals do configure some pins. Even if PB10 were driven, U23 stays open because there is no strobe, so the chain is still open. Verify and state it.
- **m11 — "Re-arming is locked out for about 5 s" (§2.1).** This applies only after a REARM press. After a chain drop C_SET is still charged, so re-arm is immediate. Reword.
- **Comment only.** `bsp.c` 131 says PC14/PC15 have "external pull-downs"; [N] they have 10 k pull-ups plus the Q41/Q42 inverters.

### 3.4 Observations

- **o1 — PAUSE keeps traction energised.** The hardware latch, VMOT and awake bridges remain in HOLD, and REARM_SW clears LOCAL_PAUSE remotely (owner decision, RSK-034, CCR-E12). With a host that streams DRIVE, the robot moves 1.5 s after a remote clear, beside the person who pressed "Pause/Stop". This is documented in the operator procedures §8. Consider not labelling the button "Stop", and/or dropping ARM_PERMIT once at rest after LOCAL_PAUSE.
- **o2 — No hardware speed or force limit.** The 0.20 m/s ceiling is firmware only; the motor no-load speed at 14.4 V is about 0.44 m/s (T6), and the bridges chop at 2.68 A each. [C] That is about 93–170 N of push force at stall (17.4–31.7 N/A × 5.36 A). A drive-loop fault with both ISRs alive is not caught by the watchdog; only the contact elements remain. Add this to the stated limits (row #58 and architecture §6.1).
- **o3 — Stop-distance model.** The electronics brake model and the emulator plant use the same constants (IB-03; README within 4 %). Their agreement is consistency, not validation. Dominant unverified inputs, in order:
  - rotor inertia (factor 3 between low and high, not published);
  - force constant choice (17.4 vs 31.7 N/A);
  - K2/K3 release plus transfer (5 ms [D] + 2.5 ms + 3 ms [A]);
  - winding resistance hot: R_M is the cold extrapolated 2.18 Ω, and a winding at about 100 °C adds about 30 % to the loop, i.e. roughly 20 % to the braking distance, not covered by "conservative";
  - R_PATH 0.04 Ω [A].
  The 1 % brake-resistor tolerance is negligible.
  The "conservative" case **is** conservative on a level floor, dry or wet: its peak deceleration of 1.5 m/s² needs μ of about 0.2 or more, the 12 kg mass exceeds the 8.6 kg robot, and the nominal case would become traction-limited before it. It **is not** a bound on a slope. With its zero-friction assumption a braked robot never stops on any incline (creep 30 mm/s at 5°). Holding up to about 6° rests entirely on the assumed 12.7 N gearbox friction, which matters for trailer door ramps.
  Low battery does not change dynamic braking. It reduces the K1 set margin (10.8 ms above 9 V at a 10 V pack), which is fail-safe.
- **o4 — Firmware alone cannot energise traction (positive).** Verified [N]: RUN_12V has only K1.8 as a source, the K1 coil has only the seal-in and J_BTN pin 2, and no MCU or expander pin drives K1/K2/K3 or U8 EN. The firmware-controlled elements (U23, U24) can only open. The remaining paths are faults (C1, M2, M6).
- **o5 — K1 contact numbering (positive).** [N]+symbol: K1's numbering (NC 3/10, NO 5/8, COM 4/9) agrees with the stock KiCad Relay:G6S-2 graphics. Omron's drawing is still [U].

## 4. Element-by-element trace (question 1)

| Element (net in → out) | Opened by | Removes, when open | Firmware can hold it closed? |
|---|---|---|---|
| F_CHAIN (VBAT_SW → CH_N0) | over-current | everything below | no |
| J_MODE 3-4 (→ CH_N1) | selector not in RUN | CHAIN_END → K1 seal, RUN_12V → K2/K3 coils (brake), U8 EN (VMOT), HW_LATCH → U9 (nSLEEP) | no |
| J_ESTOP 1-2 pole A (→ CH_N2) | E-stop | as above | no |
| J_ESTOP 3-4 pole B (COIL_RTN → GND) | E-stop | coil return of K1, K2, K3 [N]; U8 EN and nSLEEP follow when K1 releases | no |
| J_HANDS, J_COVER, J_DOCK, J_BUMP_L/R | contact | as pole A | no |
| U20 (plug link / inlet; Q20, Q21) | link, inlet > ~10 V, V5_AUX loss | as pole A | no |
| U21 (HEAD_LOOP; U30, Q22) | comparator window, V5_AUX loss | as pole A | **yes, through IOX_A GPA5 as output (M2)**; fails healthy on U30A/R74/pin-bridge faults (C2) |
| U22 (LAB_KEY_N; U31, Q28) | PRES_ID window | as pole A | **yes, through GPA7 (M2)** |
| U23 (WDG_OK; U40 WDO, Q23) | missing/early/late strobe, 3V3 loss | as pole A; WDO also resets the MCU (D + JP1) and clamps heaters | by design, by strobing (supervisor checks control/background liveness) |
| U24 (ARM_PERMIT PB10, Q24) | PB10 low (4.7 k R94 in reset) | as pole A | by design |
| K1 pole A/B, set path (REARM, C_SET, R_SET) | coil loses CHAIN_END | RUN_12V | no; held by faults C1, M6 |
| U9 (nSLEEP = DRV_NSLEEP AND HW_LATCH_RB) | latch low | bridge drive | PD2 output/pull configuration affects it (M2, M3) |

Reset-state pins [N]+[F]: ARM_PERMIT 4.7 k down, DRV_NSLEEP and DRV_NSLEEP_G 10 k down, MOT_x_INx 10 k down, WDG_STROBE static (no edges), and `gpio_init` writes safe levels before switching pins to outputs. A crashed MCU, a held reset or an unprogrammed part leaves the chain open at U23 and U24. A reset loop cannot re-latch, because each reset drops ARM_PERMIT and K1 needs REARM (absent C1).

## 5. Single-fault table spot check (question 5)

| Row | Claimed | My verdict |
|---|---|---|
| #3 selector RUN welded | undetected; "SERVICE keeps traction off only through this contact and firmware mode logic" | correct that it is undetected. The "firmware mode logic" is the host-set op_mode (caps 0 in SERVICE), unrelated to the selector position |
| #8/#31 harness short to +12 V | latent; readback mismatch on actuation | correct for shorts at CH_N1…CH_N9: CHAIN_IMPLAUSIBLE (`rrch_chain.c` 239) → FAULT → U23/U24 open. Missing the CHAIN_END/RUN_12V/K1_SET cases (C1, M6) |
| #16 photo-MOS shorted | U21/U22 seen on actuation; U23/U24 "at every boot" | U21/U22 correct (CHAIN_IMPLAUSIBLE). U23: no boot test, so latent for life. U24: PERMIT_STUCK_ON in principle, but unusable as built (M1) |
| #18 U30A stuck off | "stopped by firmware" | **wrong** (C2) |
| #22 divider faults | ADC cross-check | **wrong** (C2), and wrong designators (m5) |
| #23 Q22 short | ⚠ as #18 | better than stated: CHAIN_IMPLAUSIBLE stops it about 35 ms after the rail press [F] |
| #34/#36 watchdog dead | boot test every power-up | **not implemented**; latent indefinitely |
| #37 MCU hang | external + own watchdog | external path correct [N]. "Own watchdog" absent (M4). 43 ms depends on m2 |
| #38 PB10/Q24 stuck high | PERMIT_STUCK_ON → strobe stop → U23 opens | logic correct, but false positives from C_SET (M1) |
| #39/#40 K1 welded | firmware catches, "no motion with a healthy MCU" | **wrong**; demonstrated restart (C1) |
| #42/#43 R_SET short, REARM held | "firmware flags REARM held > 2 s" | **not implemented**; R_SET short + held REARM → auto-restart with no detection |
| #44/#45 brake relay NO welded | BRAKE_x_RB after the drop | correct [N]+[F]: OR over poles, `brb` (`rrch_chain.c` 334) → VMOT_FAULT → permit low |
| #46 brake path open | undetected at standstill | correct; the recommended dynamic deceleration check is also not implemented |
| #52 U9 stuck high | latent | correct; add the PD2 configuration dependence (M2, M3) |

**Missing dangerous single faults:**
- V12_AUX or LAMP_REARM_K shorted to K1_SET (C1).
- U30 pin 1 open, U30 pin 7–8 bridge, R74 short, HEAD_LOOP_OK_RB shorted to 3V3 or V5_AUX (C2).
- RUN_12V or CHAIN_END shorted to a supply on the board, including the TP50/TP38 clip case (M6).
- Expander pin GPA5/GPA7 or PD2 configured as output (M2).
- Brake resistor or winding degraded high but not open (longer stop, undetected; o3).
- Drive-loop fault with the supervisor alive: no hardware speed limit (o2).

**Single faults that leave the robot able to drive into a person with no remaining hardware barrier:**
1. Frontal contact: any C2 fault. No firmware barrier either; only the host LiDAR route hold remains.
2. Rear or quarter contact: a welded bumper switch or bumper wiring short (#28); only the firmware rear ToF remains.
3. A welded head rail switch, or a head-internal bypass (#24), for that zone.
4. Repeated re-approach after a contact stop: C1. Every contact still drops the latch, but every release restarts it.
5. RUN_12V shorted to a supply: everything except E-stop pole B (M6).
6. A drive-loop error with supervision alive: no speed or force limit, though the contact elements remain (o2).

The doc's §6 summary lists (2) and (3) honestly. It presents (1) and (4) as firmware-covered, which they are not, and omits (5).

## 6. Checked and found correct

- Series order equals `contract.yaml` safety_chain.series_elements; each element's sense and supply as in §2.2. KiCad netlist export equals circuit.py + overrides for all 67 chain and drive nets [N].
- E-stop pole A on the high side; pole B on the common coil return of K1, K2 and K3 [N].
- Coil clamps: 1N4148 anode on coil−, Z24 anode on coil+, common cathode. That is a diode + 24 V Zener clamp with the right polarity for fast release [N].
- A held REARM passes 0.58–0.65 V to the coil, below the 1.2 V must-release, so it cannot hold or re-set the latch with R_SET healthy [N]+[C].
- Brake relays: de-energised connects the motor across 1.0 Ω and isolates both terminals from the bridge [N]. The readback is a wired-AND of both outputs below 0.20 V, then Q41/Q42, so high = connected, as the firmware decodes it. The bridges wake only after both relays read back connected (`rrch_chain.c` 334–339, `rrch_motion.c` 530) [F].
- Watchdog: WDO drives Q23/U23, Q29 → WDG_FAULT (heaters and FAULT LED), and NRST through a diode and JP1 [N]. The supervisor strobes only if the control tick count is 8–12 per 10 ms, the flow markers are complete and the background loop is alive; TIMING and PERMIT_STUCK_ON stop the strobe [F].
- IOX_A integrity: sentinel GPB7 = WDG_STROBE checked every read, failure is fatal within 5 ms; IODIR read at init; no IOX_A writes. IOX_B P17 configured as input; permit withheld while CHAIN_END_RB is unreadable [F].
- Node decode CLOSED/OPEN/UNKNOWN is consistent with node taps (ignoring M1). CHAIN_IMPLAUSIBLE catches a live node behind a dead one [F].
- Motion commands [F]:
  - DRIVE needs a session, increasing seq, TTL ≤ 250 ms (from `issued_us` or receipt), a matching op_mode, a passed brake test since boot, mode ARMED_IDLE/MOVING and no directional inhibit;
  - any stop discards the command (`rrch_drive_stop`) and forces the 1.5 s pre-motion alert on the next start;
  - nothing auto-clears; REARM_SW needs the current chassis-issued nonce and never sets the hardware latch;
  - HELLO while moving latches HOST_LINK_LOST; link loss latches HOST_LINK_LOST after `link.timeout_ms`;
  - protocol handlers run with the ticks masked, so no command/tick race; the CONFIG_SET flash write runs outside the lock and only when stationary.
- `check.sh` and the overrides self-check pass.

## 7. Not assessable from the files

- Datasheet values used above but not read here:
  - TLP241A turn-off, trigger current and off-state leakage;
  - G6S-2 / G2RL-2 release and hold voltages and the Omron pin drawing;
  - TPS3430 WDI edge polarity and window limits;
  - LM2903B sink current against MCP23S17 source current (the magnitude of M2);
  - STM32G474 RPD and VIH per pin type (M3), and AN2606 bootloader pin use (m10);
  - TCA9535 input thresholds and hysteresis;
  - DRV8874 IN/IN truth table.
- Rotor inertia, friction, slope holding, real stopping distances, head-rail and bumper pre-travel and actuation force, and the head-side loop topology (#24).
- Copper pours and zone clearances of the chain nets on the routed board; leakage when damp.
- Host behaviour: whether `rr_core` or the bridge resumes DRIVE automatically when the chassis returns from HW_INHIBIT to ARMED_IDLE. This decides whether C1 becomes motion in practice.
- Anything on real hardware; nothing has been built or measured.

## 8. Items worth recording in the backlog

These sharpen existing rows; they are not duplicates:
- **IB-16**: add C1, C2, M6 and the missing rows of §5.
- **IB-60**: add the REARM-correlated latch check (C1), the loop permit rule (C2), the REARM-held logic and IWDG (M4), the PB12/PD2 pull-down fix (M3), the I2C transient (m7) and the decay limit (m1).
- **IB-01/02**: reopen against M1 and M5; their closure tests ran on a model without C_SET and with HW_LATCH taken from the K1 armature.
- **Electronics rev B**: R_SET diode (M1), series resistors on the comparator and PD2 nets (M2), an on-board K1 set node (C1), test-point spacing (M6), and the §2.1, §2.3, §6 and §7 text corrections.
