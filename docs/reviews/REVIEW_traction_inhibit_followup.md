# Follow-up review: traction inhibit after chassis stage 3 and two firmware rounds

Reviewer: the same independent engineer as `REVIEW_traction_inhibit.md`. Date: 2026-11-27. Scope: verify the stage-3 circuit changes (`electronics/chassis_main/overrides.py` S3-xx) and the firmware rounds against my findings, and look for defects the fixes introduced. Not a certified safety assessment; the design still states it is not a safety function.

Tags: **[N]** netlist (circuit.py + overrides.py, queried with my `q.py`) · **[P]** placement data (`out/pinmap.json`) or the generated DRC rules · **[F]** firmware source (HEAD b452931) · **[E]** emulator run with my own fault models in a scratchpad copy (repository untouched) · **[C]** my calculation · **[I]** inferred or recalled datasheet value, not verified.

## 1. Method

- `python3 electronics/chassis_main/overrides.py`: exit 0, stage-1 self-check on the overridden netlist PASSED.
- `firmware/chassis/check.sh`, build directory in the scratchpad: exit 0. test_chain 329, test_state_machine 1193, test_review 64, test_drive 2476 checks; integration tests and both STM32 images pass. The board was not rebuilt.

**Summary.**
- C1, M1, M2, M3 and the minors are closed. C2, M4, M5 and M6 are closed in their main part.
- New: 5 Major (N1–N5), 4 Minor (N6, m-B, m-C, m-D) and one documentation item (D1).
- §6.1 lacks 3 single faults (HANDS-ON, selector RUN, W-015 crush).
- The host no-auto-resume claim holds in every path read, but it is proven only against a fake chassis that differs from the firmware.
- Every new net of S3-C1, S3-C2, S3-M1, S3-M2, S3-M6 and S3-F1 dumped with `q.py`. Pad and test-point spacing read from `out/pinmap.json`; the custom DRC rules read from `RR-CHS-MAIN.kicad_dru`. The board is placed, not routed, so copper clearance could not be checked.
- Firmware read: `rrch_chain.c` (complete), the permit, brake-test and supervisor parts of `rrch_core.c`, `bsp.c` (IOX_D, WDI, IWDG, TIM8 break, pin check). The emulator diff since my first review was also read.
- Emulator: a scratchpad copy of the current `sim.c` and harness (`…/review_chain/emu3/`) with four switches of mine:
  - K1 must-operate voltage on C_SET (the emulator uses 7.5 V; T11 uses 9 V);
  - K1 pick-up time 3 ms (G6S ≤ 4 ms [U]; the emulator uses 10 ms);
  - set pulse ending when the set contact opens (on the board, D_SGN resets the gate on release);
  - U21 or U21B output shorted while the comparators stay healthy.
  Scenarios are in `rv3.c` and `rv3b.c`. They drive the unmodified firmware core.

## 2. Stage-3 latch topology as built [N]

- **Set request.** J_BTN 1 = REARM_SET_SRC (V5_AUX via R_SSRC 1 k) → set contact → J_BTN 2 = REARM_SET_RAW (R_SPD 47 k, D_SET 15 V ESD) → R_SSER 10 k → REARM_SET → C_SC 1 µF → SET_G (R_SG 100 k, D_SGN) → gate of Q_SETA.
- **Aux contact.** BTN_3V3 → J_BTN 4 = REARM_BTN_RAW → R_AG 10 k → REARM_AUX_G (R_AGP 100 k) → gate of Q_SETB. Q_SETA and Q_SETB are in series and sink the U_SET LED (V5_AUX via R_USA 470).
- **Set switch.** U_SET joins SET_CAP to K1_SET → R96 → K1_COIL_P. The coil node no longer leaves the board. Q_HSET (BSS84, gate U_SET_K) feeds the U_HOLD LED from V5_AUX through R_HS only while the U_SET LED conducts.
- **Hold path.** K1 pole B → K1_RUN → U_HOLD → RUN_HD → D_RUN (B160 Schottky) → RUN_12V. U_HOLD self-holds from RUN_HD through R_HA 1.5 k. RUN_HD feeds the U8 EN divider, U9's own tap (HW_LATCH_G) and the U_LS LED (R_LSA 1.5 k). RUN_12V feeds the K2/K3 coils and HW_LATCH_RB (22 k/15 k → PD2).
- **Relay return.** K2/K3 return through RELAY_RTN → U_LS → COIL_RTN → E-stop pole B.
- **C_SET.** Charged from CHAIN_END through D_RSET + R_SET 22 k. Discharged through R_SDIS 1 k by Q_SDIS whenever Q_SDISB is off, i.e. whenever the CHAIN_END_RB tap (also IOX_B P17) is below the threshold of Q_SDISB (CHAIN_END below about 2–4 V).
- **Readbacks.** LATCH_NC_RB: K1 NC1, with K1_SEAL_A biased from 3V3 via D_K1B/R_K1B. LATCH_RUN_RB: K1_RUN tap. HEAD_LOOP2_OK_RB: U46 output via 47 k. REARM_SET_RB: REARM_SET via 47 k. All four go to IOX_D (U47, TCA9534 at 0x22), whose P4–P7 carry the fixed pattern 1,0,0,0.
- **Head loop.** Channel A (U30 → Q22 → U21, CH_N5 → CH_N6A) and channel B (U46 TLV3201 → Q_LB → U21B, CH_N6A → CH_N6) are in series. They share R65/R66/R67/R68 and the sense node LOOP_SNS. **CH_N6A and CH_N6 have test points only (TP60, TP8), no readback.**

## 3. Closure of the original findings

| Finding | Status | Evidence | Remaining |
|---|---|---|---|
| **C1** latch sets without REARM | **Closed in hardware; firmware detection implemented** | [N] the coil node is on the board; RUN_HD needs U_HOLD, which can only be set by Q_HSET during a two-contact (edge AND level) set pulse. [F] `rrch_chain_step`: LATCH_NO_REARM needs an aux edge and a set edge within 110 ms, then a latch rise within 300 ms; K1_WELD from LATCH_NC_RB/LATCH_RUN_RB with the latch down; `rrch_rearm_blocked` will not raise ARM_PERMIT until K1 reads released; BRAKE_TEST step 3 (ARM_PERMIT up, no REARM, 120 ms). The emulator now takes HW_LATCH from RUN_12V. | U_HOLD short / Q_HSET short / HOLD_A shorted to a logic supply is latent (N4). A W-018 crush can arm once (doc #44). New defects in the set stage: N1, N2. |
| **C2** head loop with no second channel | **Closed in hardware for the comparator path; partly for the photo-MOS path** | [N] channel B (U46/Q_LB/U21B) in series, of a different type. [F] while latched, any opening seen by A, B or the analog copy withdraws ARM_PERMIT; A/B disagreement with the analog copy reading open is LOOP_FAIL. [E] covered by test_review "channel A stuck healthy". | A shorted U21, Q22, U21B or Q_LB is now **latent** (no tap on CH_N6A): N3. A loop of 1.65–2.6 kΩ is wrongly made fatal: N6. The shared LOOP_SNS leak remains (doc 6.1 item 3). |
| **M1** C_SET back-feed | **Closed** | [N] D_RSET (silicon; T11 explains why not Schottky); Q_SDIS empties C_SET when the chain is dead. [F] `chain.backfeed_ms` default 0. | Consequence of the discharge: every ARM_PERMIT dip empties C_SET, which feeds N1. |
| **M2** firmware can bypass U21/U22; U9 on an MCU pin | **Closed** | [N] R_GA5/R_GA7 47 k; U9.B has its own tap on RUN_HD; D_RB on the aux line; R_GB7 47 k + R_WDPD 10 k on WDI. [F] `io_cfg_check` reads IODIRA/B and GPPU back periodically and raises PIN_CONFIG. | New, minor: IOX_B P17 sits directly on CHAIN_END_RB, which now also drives Q_SDISB, and the IOX_B configuration register is not read back (m-B). |
| **M3** pull-downs on the tap inputs | **Closed** | [N] PB12/PD2 taps now 22 k/15 k. [F] `bsp.c` NOPULL on PB12, PC13 and PD2, checked by `io_cfg_check`. | — |
| **M4** claimed detections absent | **Mostly closed; documents stale** | [F] IWDG about 250 ms, refreshed with the strobe; REARM_HELD and REARM_DISCREPANCY; K1 weld checks; TIM8 break **now enabled** (PD2, active low, auto re-enable). | The U23 boot self-test is still absent (IB-60). `chassis_safety_chain.md` §6 still says F2/F3/F5/F6 are "requested, not implemented" and §2.1 says TIM8 break is "not used"; README line 315 says the same. Both are now wrong (D1). |
| **M5** emulator differs from the netlist | **Partly closed** | [F] HW_LATCH from run12, C_SET with diode and discharge, LAB and loop windows, WDI edge model, relay times all aligned. | New divergences exactly at the new parts: K1 operate 7.5 V instead of 9 V, so the "2 s" claim passes only in the emulator; K1 pick-up 10 ms; set pulse not truncated on release; U_HOLD switches instantly. These hide N1 and N2. |
| **M6** board short of RUN_12V / CHAIN_END; test points | **Closed for RUN_12V with a temperature caveat; RUN_HD / K1_RUN / CHAIN_END listed as residual** | [N] U_LS lit only from RUN_HD; D_RUN; U8 and U9 from RUN_HD. [P] chain test points ≥ 10 mm from supply test points (nearest 15.0 mm); DRC rule `chain_to_supply` 1.0 mm. [F] RUN_SHORT (HW_LATCH high, K1_RUN low) is fatal. | D_RUN is a Schottky: hot reverse leakage can light U_LS/U_HOLD after a drop (N5). The DRC rule omits the U_HOLD/U_LS LED nodes and treats neither 3V3 nor V5_AUX as an aggressor (N4). |
| m1 VMOT decay limit | Closed | `brake.vmot_decay_max_ms` 3500 | — |
| m2 WDI edge margin | Closed | 5 ms high pulse every 10 ms; falling edges 10 ms apart against tWDU(min) 23.375 ms; IWDG added | Boot path before the ticks start is not covered (README "Known gaps", CCR-E11): keep JP1 open until measured. |
| m3 pre-arm window | Closed in hardware | C_SET is empty whenever the chain is open; the firmware also holds ARM_PERMIT low for 300 ms after an early press | Q_SDIS open / Q_SDISB short reopen it (doc #49, latent, firmware covers it) |
| m4 minimum opening | Closed by design statement and firmware | U_HOLD drops whenever RUN_HD dies; any latch-readback fall holds ARM_PERMIT low ≥ 50 ms | ≥ 2 ms is [A]; bench step 8 measures it |
| m5 designators | Closed | §2.2 now uses netlist refs (R65/R68/R70–R74 checked) | — |
| m6 K2/K3 supply text | Closed | §2.1 rewritten and agrees with [N] | — |
| m7 one I2C read drops the latch | Closed while latched | 50 ms tolerance while latched; bus re-init after 3 failed reads | Before arming, one IOX_B or IOX_D read failure blocks ARM_PERMIT for ≥ 50 ms, which **empties C_SET** (N1) |
| m8 IOX_B writes unsupervised | Open | README gap | — |
| m9 HANDS-ON lamp beside contact | Documented (row 9) | — | — |
| m10 bootloader pins | Documented [U] | — | — |
| m11 lockout wording | Closed | §2.1 | — |

## 4. New findings introduced by, or exposed by, the fixes

### Major

**N1 — A legitimate re-arm is refused when the operator follows `rearm_ready`; repeated presses never succeed.**
- [N] C_SET charges only through D_RSET + R_SET 22 k (τ = 2.2 s), and every interruption of CHAIN_END empties it in about 0.3 s.
- [C] T11's set threshold is a K1 coil current above 8.75 mA, i.e. C_SET ≥ 9.0 V at 23 °C and about 9.9 V for a 50 °C coil. T11 assumes a full charge, "chain closed ≥ 10 s".
- [F] `rearm_ready`, and the blinking REARM lamp, come on after `ce_high_ms ≥ 2000` (CHAIN_END_RB high for 2 s). At 2 s, C_SET holds about 60 %: [C] 7.4–7.6 V from a 12.8–13.0 V pack.
- [E] With 9.0 V as K1's threshold: `rearm_ready` came on 1.9 s after the chain re-closed (C_SET 7.56 V). The press at that moment was refused. Pressing again every 0.9 s **never armed in 8 s**, because each press dumps C_SET into the coil (back to 3.9 V) and 0.9 s of charge does not reach 9 V.
- With the emulator's own 7.5 V threshold the same press arms. That is why the repository's tests pass: the 7.5 V comment in `sim.c` says it was chosen to give "the 2 s of section 2.1".
- [C] The needed wait at 23 °C is about 2.9 s from a 12.8 V pack and about 3.6 s for a 50 °C coil, longer at low battery. T11 itself shows "no" at 10 V above 23 °C and at 12 V/85 °C.
- No event or STATE member reports that a press was refused. The ARM_PERMIT dips at the start (permit hold after a drop, `rearm_blocked` on an IOX_D read failure, the 300 ms early-press block) each empty C_SET again and restart the wait silently.
- **Why it matters.** It is fail-safe, but an operator in a trailer sees a lamp that says "press now", presses, nothing happens, and keeps pressing, each press resetting the charge. This invites workarounds. It also hides the low-battery and hot-coil refusals of T11 that the question asks about. A robot that cannot be armed on a low or hot pack is acceptable only if it says so.
- **Change.**
  1. Raise the `rearm_ready` delay to cover C_SET ≥ 10 V at the measured pack voltage: compute it from VBAT_SENSE (t = 2.2 s · ln((Vbat − 0.4)/(Vbat − 10.4))) with a floor of 3.5 s. Better, add an ADC tap on SET_CAP: a spare ADC pin, or a comparator to IOX_D P4–P7, which are free apart from the pattern.
  2. Report REARM_REFUSED (aux and set edges seen, no latch within 300 ms) with the reason (C_SET low, pack low, coil hot), and show it on the lamp, e.g. a fast blink.
  3. Set the emulator's threshold to T11's 9 V and add the 50 °C case.

**N2 — The hardware accepts REARM taps the firmware cannot verify, giving a fatal LATCH_NO_REARM and a watchdog reset.**
- [N] The set pulse ends when the set contact opens: on release, REARM_SET falls, C_SC drives SET_G negative and D_SGN clamps it. A 4–9 ms tap therefore gives a 4–9 ms U_SET pulse. [I] That is long enough for K1 (operate ≤ 4 ms [U]) and U_HOLD (turn-on ≤ 3 ms [U]).
- [F] The set contact is seen only through IOX_D (I2C, ≥ 10 ms period in `bsp_background`; slower when other I2C devices time out). `legit` needs a set edge within 110 ms of the aux edge.
- [E] With K1 operating in 3 ms and the pulse truncated on release, taps of 4–9 ms latched the hardware in every phase. The firmware declared LATCH_NO_REARM (fatal, stops the strobe → MCU reset) in 7/10 phases at 4 ms, falling to 2/10 at 9 ms, and 0 at 11 ms.
- [I] The emulator's 10 ms K1 pick-up hides this. On the board, a tap that sets K1 a little before U_HOLD conducts would leave K1 sealed with RUN_HD dead, which the weld rule reports as K1_WELD (fatal, no reset) once the 300 ms pulse allowance has passed.
- Fail-safe, but a brisk press of the "Start" button puts the robot into FAULT.
- **Change.** Hardware: make the set pulse a fixed one-shot that is not cut short by release, or add a minimum-press filter (e.g. 20 ms RC before C_SC), so the hardware never accepts what the firmware cannot see. Firmware: sample REARM_SET_RB at 1 kHz (route it to an MCU pin or a spare IOX_A input). Treat "K1 closed, RUN_HD dead within 300 ms of a REARM edge" as a refused set: drop the permit for 50 ms, no fatal.

**N3 — A short of either head-loop photo-MOS or its driver is now latent (a diagnostic regression).**
- [N] U21 (channel A) and U21B (channel B) are in series between CH_N5 and CH_N6 with no tap between them; CH_N6A has only TP60.
- [F] The firmware compares the *comparator* outputs (HEAD_LOOP_OK_RB, HEAD_LOOP2_OK_RB) with the analog copy. A shorted U21 or Q22, or U21B or Q_LB, leaves both comparators correct. When the rail opens, the other photo-MOS opens the chain, every readback agrees, and nothing is flagged.
- On stage 2, a shorted U21/Q22 was found at the next rail press by CHAIN_IMPLAUSIBLE (CH_N8A live while the comparator said open). That detection is gone.
- [E] U21 shorted: rail press → latch dropped, **no fault**, robot re-armed normally. Only when U21B was shorted as well did CHAIN_IMPLAUSIBLE fire and the firmware stop it (permit withdrawal on any comparator opening), so a firmware barrier remains after the second fault.
- Rows #16 ("detected at the next rail press") and #17 ("latent until F6 exists"; F6 now exists but does not see photo-MOS or driver shorts) are wrong for this subset.
- **Change.** Add a 100 k/56 k tap on CH_N6A to a free IOX_D input (P5–P7 are pattern pins; one can become a readback, with the pattern reduced to P4 and P7), and extend the implausibility rule: CH_N6A live with channel A's comparator open → U21/Q22 short; CH_N8A live with channel B open → U21B/Q_LB short. Correct rows #16/#17 and the §6.1 latent list.

**N4 — The two new hold elements can be lost to an ordinary short against a logic supply, and the DRC rule does not cover it.**
- [P] The U_HOLD LED anode HOLD_A is 2.25–2.43 mm from 3V3 pads (R183, R268). The U_LS LED anode LS_A is 2.43 mm from a 3V3 pad (R274). HSET_D (R_HS / Q_HSET drain) is 2.29 mm from a V5_AUX pad (U36 pin 8).
- [N] A short of HOLD_A to 3V3 or V5_AUX lights U_HOLD permanently (equivalent to #39). A short of LS_A lights U_LS permanently (#53).
- [P] `chain_to_supply` in `RR-CHS-MAIN.kicad_dru` lists neither HOLD_A, LS_A, HSET_D nor RELAY_RTN on side A. It lists neither 3V3 nor V5_AUX on side B. Unlike the coil nodes, an LED node is driven by 3.3 V.
- Latent; it matters with a second fault (K1 weld, or RUN_12V short).
- **Change.** Add HOLD_A, LS_A, HSET_D, U_SET_A/U_SET_K and RELAY_RTN to side A, and 3V3/V5_AUX to side B, with 1.0 mm. Add these shorts to rows #39/#53.

**N5 — The M6 closure (RUN_12V shorted to a supply) depends on the Schottky D_RUN's reverse leakage staying below the photo-MOS trigger current.**
- [N] When a drop happens with RUN_12V held up by such a short, D_RUN is reverse-biased by up to 14.6 V. Its leakage flows into RUN_HD, whose only loads are the U_HOLD and U_LS LEDs (1.5 k each) and two ≥ 122 k dividers.
- [I] A 1 A/60 V Schottky (B160) leaks on the order of 0.1–0.5 mA at 25 °C and several mA at 75–100 °C. TLP241A trigger current is ≤ 3 mA max, typically well below. G2RL must-release is about 5 % of the rated voltage, so a few mA in the coil can hold an energised relay.
- At temperature, U_LS can therefore stay partly on and K2/K3 may not release: the drive is removed (VMOT and nSLEEP follow RUN_HD, which stays near the LED forward voltage), but there is **no dynamic braking** for that stop (38–114 mm instead of about 10 mm from 0.20 m/s, T4).
- The analysis chose a silicon D_RSET for exactly this leakage reason (T11) but used a Schottky for D_RUN. [F] RUN_SHORT is fatal and prevents re-arming, so this is about the one stop after a short that appears while moving.
- **Change.** Use a silicon rectifier for D_RUN (S1G/1N4002 class: µA leakage; 0.8 V drop at 80 mA is acceptable at the 8.4 V must-operate), and/or a bleed of a few kΩ from RUN_HD to ground, sized so that worst-case leakage stays below 1 V. Add the case to row #51.

### Minor

- **N6 — Loop decision table: a loop between the two channel thresholds is made fatal.**
  - [F] Channel A passes 0.59–1.55 kΩ; channel B passes < 2.70 kΩ by design. For a loop of 1.65–2.6 kΩ (aged rail-switch contacts, a damaged cable), A reports open, B reports closed and the analog copy says open, so `ab && ana == 1` raises **LOOP_FAIL (fatal)**, as if B were stuck healthy.
  - [E] Loops of 1700/2000/2400/2600 Ω while armed all gave mode FAULT with LOOP_FAIL. 1600 Ω gave LOOP_DISCREPANCY and 2900 Ω a normal open.
  - It is fail-safe, but the cause is misreported and a reset is needed.
  - Change: if the analog copy says the loop is between 1.65 kΩ and 2.6 kΩ (inside B's pass band), report HEAD_LOOP_OPEN plus a "loop resistance high" diagnostic. Keep LOOP_FAIL for an analog reading above about 2.9 kΩ with B still closed.
- **m-B — IOX_B P17 drives the discharge transistor directly.** [N] IOX_B P17 sits directly on CHAIN_END_RB, which now also gates Q_SDISB. A firmware or bus fault that turns P17 into an output can disable the C_SET discharge (reopening m3; also PERMIT_STUCK_ON at the next permit low, so it is detected) or force it on (cannot arm). [F] `io_cfg_check` reads IOX_A and the STM32 pins, not the IOX_B configuration register. Read IOX_B register 0x07 back with IOX_D's 0x03.
- **m-C — 5.5 V ESD array on a line that can see 12 V.** [N] The aux line REARM_BTN_RAW and BTN_3V3 are on D29 (TPD4E05U06, 5.5 V). The doc's own fault #43 (V12_AUX onto REARM_BTN_RAW) drives that array into conduction from a 0.35 A PTC, while the set lines were given a 15 V part (D_SET) for this reason. A failed-short D29 leaves the aux line grounded: cannot arm, fail-safe, but the fault looks like a broken button. Use a 15 V part here too.
- **m-D — Stale cross-references in the harness note.** `harness/cables.md` W-018 cites "chassis_safety_chain.md section 5 rows 42-46"; they are in section 6. Its lay instruction ("keep the lamp pair on the OUTSIDE next to nothing but P3's own return") cannot hold in a bundle of three twisted pairs, where every pair touches the other two. The design does not depend on it (single shorts onto either contact line are harmless by design); state that instead.

### Documentation (D1)

- `chassis_safety_chain.md` §6 states its firmware column was read at commit 77507bc, and marks F2/F3/F5/F6 and the boot "K1 not welded" check as "requested, not implemented". They are implemented in HEAD (`rrch_chain_step`, `rrch_rearm_blocked`, `bt_step` case 3). Rows #37, #38, #42, #51 and §7 step 4 understate the detection; #16/#17 overstate it (N3).
- §2.1 and README line 315 say TIM8 break is not used. `bsp.c` 241–251 enables it on PD2.
- Row #35 says the IWDG was "seen, not reviewed here". It is in `bsp.c` `iwdg_start`: about 250 ms, refreshed in `h_strobe` only when the supervisor's checks pass.

## 5. Single faults of the new parts (question 2)

Each fault was checked against the netlist [N] and the firmware rules [F].
- **Fail-safe** = cannot arm, or the chain opens.
- **Latent** = a barrier is silently lost.

| Part | Fault | Outcome | Detected? |
|---|---|---|---|
| U_SET | output short | C_SET sits on the coil and never charges (≤ 0.65 V): cannot arm | as "cannot arm" only |
| U_SET | LED or output open, LED short | cannot arm | same |
| Q_SETA, C_SC | D-S short / C_SC short | edge requirement lost: the aux contact alone sets (doc #45) | **latent** |
| Q_SETA, C_SC | open / G-S short | cannot arm | — |
| Q_SETB | D-S short | aux requirement lost: the set contact alone sets (doc #46) | latent; LATCH_NO_REARM only if the aux contact then fails |
| Q_SETB | open | cannot arm | — |
| D_SGN | short | no gate pulse: cannot arm | — |
| R_SG | open | gate holds after the edge, so U_SET stays on while the button is held: same as a C_SC short | latent |
| U_HOLD | output short, LED node shorted to 3V3/V5_AUX (N4) | hold rests on K1 alone (doc #39) | **latent for life** (see below) |
| U_HOLD | open, LED open/short, R_HA open, D_HR short | cannot arm | — |
| Q_HSET | D-S short | U_HOLD LED permanently lit (#39) | **latent** |
| Q_HSET | open | cannot arm | — |
| D_RUN | short | RUN_12V can back-feed RUN_HD; matters with a RUN_12V short (#52) | **latent** |
| D_RUN | open | relays never pick up; bridges never wake (relays_ok) | yes |
| D_RUN | reverse leakage at temperature | N5 | no |
| U_LS | output short, LS_A shorted to a logic supply (N4) | relay return unconditional (#53) | **latent** |
| U_LS | open | relays never pick up | yes |
| U46 | output stuck high | channel B lost | yes: LOOP_FAIL at the next rail press [E] |
| U46 | output stuck low | chain open; LOOP_DISCREPANCY withholds arming | yes |
| U46 | pin bridges 1–2, 2–3, 4–5 | all open channel B | fail-safe (good pin choice) |
| U21B, Q_LB | short | channel B photo-MOS lost | **no (N3)** |
| U21B, Q_LB | open | chain open | — |
| D_RSET | open | cannot arm | — |
| D_RSET | short | the M1 back-feed returns and keeps Q_SDISB on (no discharge) | false PERMIT_STUCK_ON → FAULT (detected, fail-safe) |
| Q_SDIS | short | C_SET always empty: cannot arm | — |
| Q_SDIS | open; Q_SDISB short | no discharge: pre-arm window back (#49) | firmware 300 ms block covers it; latent |
| Q_SDISB | open | always discharging: cannot arm | — |
| U47 (IOX_D) | dead, stuck, or a pattern error | IOX_D fault | arming blocked; while latched the hardware channel B still acts, so firmware visibility of K1/loop-B is lost only for monitoring |
| U47 | configuration changed | register 0x03 checked every 100 ms | yes |
| Changed resistors | R99/R100, R117/R118 drift or open | readback wrong in the safe direction (reads open) | yes |
| Changed resistors | R_GA5/R_GA7/R_GB7 short | M2 path back (expander can drive the gate node) | PIN_CONFIG checks IODIR/GPPU [F]; latent otherwise |
| Changed resistors | R_WDPD open | WDI floats at reset: TPS3430 input [U] | not detected |
| Changed resistors | D32/D35 now Z20 | 20 V clamp: release about 0.3 ms slower [A]; Zener short as #63 | — |

**What the design relies on with U_HOLD, U_LS or D_RUN shorted** (the electronics engineer's "latent" set, confirmed).
- **U_HOLD short.** "No restart without REARM" rests on K1 alone, plus the firmware K1 checks, which are implemented [F]:
  - K1 pole A welded later: LATCH_NC_RB reads not-released, so `rrch_rearm_blocked` never raises ARM_PERMIT again. Firmware barrier.
  - K1 pole B welded later: ARM_PERMIT is raised, CHAIN_END → K1_RUN → RUN_HD gives traction power without REARM until the debounced latch rise (50 ms) raises LATCH_NO_REARM (fatal). The bridges stay asleep because no DRIVE is accepted; firmware barrier only.
- **U_LS short.** The barrier against a RUN_12V short is gone; K1 + U_HOLD still switch the supply.
- **D_RUN short.** A RUN_12V short then feeds RUN_HD, which lights U_LS and U_HOLD and enables U8 and U9. With D_RUN shorted, a RUN_12V short behaves like a RUN_HD short (6.1 item 4).
- **Periodic test.** None exists. None of the three can be revealed in normal operation: U_HOLD is always set together with K1, and D_RUN/U_LS are tested only by an applied RUN_12V fault. The only test that reveals them is bench steps 9–10 of §8 (weld wire on K1, RUN_12V tied to VBAT_SW through 10 Ω). **Recommendation:** make §8 steps 9 and 10 a periodic service test (e.g. at every annual service, and after any repair near K1/K2/K3), and record it. Do not add a firmware-controlled path that sets K1 without U_HOLD just to test it.

**Does the set stage set reliably? (T11)**
- With a full C_SET, the margin is ≥ 3× the operate time at 12.8–14.6 V up to +50 °C. It refuses at 10 V above +23 °C and at 12 V/+85 °C.
- Refusing at 10 V is consistent with the firmware's own BATTERY_LOW stop at 11.2 V; nobody should arm an empty pack. Refusing at 12 V in a hot trailer (+85 °C coil) is a real availability limit; the doc should say so.
- It is **acceptable only if reported**. Today nothing reports it:
  - no REARM_REFUSED event or STATE member exists in the firmware or the ICD;
  - the host fake (`rr_core/fakes/chassis.py`) invents `rearm_refusal` and a `REARM_REFUSED` event that the real chassis never sends;
  - in practice the dominant refusal is N1 (pressing after 2 s rather than about 3–4 s), not the battery.
- **Change:** N1 points 1–3, plus the same refusal reason in the ICD and the fake.

## 6. Completeness of §6.1 and the W-018 claims (question 3)

§6.1 items 1–5 are confirmed against the netlist. Item 4 is right that the remaining barrier is E-stop pole B: [N] U_LS returns to COIL_RTN, so pole B also opens the K2/K3 return.

**Not listed but belonging there** (single faults that leave the person concerned with no hardware barrier):

1. **HANDS-ON contact welded, or the W-017 lamp-to-contact short (row #9).** The person doing hands-on work has no hardware barrier; the latch stays set and the host can drive. Only "lamp lit = inhibit proven" protects them. That is a procedure, and §6.1 should say so.
2. **Selector RUN contact welded (row #3).** Moving the selector to SERVICE no longer opens the chain. A person servicing in SERVICE is protected only by OFF (which removes power) or by E-stop/HANDS-ON. List it, or tell the procedure to use OFF, not SERVICE, for work at the wheels.
3. **Multi-conductor crush of W-015 (E-stop)** that shorts pole A's pair and pole B's COIL_RTN–GND pair without touching CH_N1 to ground: the E-stop is lost entirely. Same class as item 5 (W-018 crush); improbable, but listed for symmetry.

**Belongs in the latent list (two faults to remove the barrier), not 6.1:**
- U21/Q22 or U21B/Q_LB short (N3);
- HOLD_A/LS_A to a logic supply (N4);
- **RELAY_RTN shorted to GND** [N]: bypasses U_LS and E-stop pole B for K2/K3 together. Pole B still drops them through K1 → RUN_HD, but a RUN_12V short as the second fault then has no barrier at all. RELAY_RTN is not in the DRC rule.

**W-018 claims checked against `harness/cables.md`.**
- [N] matches the cable table: pins 1/2 set contact (YE, pair P1), 3/4 aux contact (P2), 6/7 lamp (P3); 5 and 8 empty.
- The claim that single conductor-to-conductor shorts are harmless holds [N]:
  - V12_AUX, LAMP_REARM_K, BTN_3V3 or REARM_SET_SRC onto REARM_SET_RAW gives one edge without the aux level;
  - the aux contact bridged needs a set edge as well, and REARM_HELD then blocks arming.
- Two corrections:
  - **(a)** The harness note's cross-reference ("section 5 rows 42-46") and its lay instruction are wrong (m-D). In a 3-pair bundle the lamp pair touches both contact pairs, so the crush of §6.1 item 5 is geometrically the expected multi-pair fault, not an exotic one.
  - **(b)** After a W-018 crush arms the robot, the aux line stays high. REARM_HELD is raised after 2 s, but `rrch_rearm_blocked` returns false while latched, so the latch stays set [F]. **Change:** a REARM contact still closed 2 s after a latch rise should withdraw ARM_PERMIT. That turns item 5 from "armed for the mission" into "armed for 2 s".

## 7. Timing (question 4)

| Item | Finding |
|---|---|
| REARM acceptance window | `legit` = aux edge (1 kHz, IOX_A) and set edge (IOX_D, ≥ 10 ms period, longer when other I2C devices time out) within 110 ms, latch rise (debounced 50 ms) within 300 ms of the later edge. **Legitimate refusals:** taps of 4–9 ms (N2), and an IOX_D read delayed past 110 ms (background loop slowed by I2C timeouts: 5 ms each, several devices per 100 ms pass). **Illegitimate acceptance:** only the simultaneous W-018 crush (§6.1 item 5). No race accepts a set without both contacts. |
| 110 ms set pulse | With the X7R 1 µF at 5 V bias and −25 °C the gate pulse shortens to about 55–90 ms [I]; still ≫ K1 operate (≤ 4 ms) and U_HOLD turn-on (≤ 3 ms). The real limit is that release truncates it (N2). |
| 2 s `rearm_ready` | Too early for the charge K1 needs. Refusal with no report (N1). |
| 0.3 s C_SET discharge | Works as intended (m3 closed). Side effect: **every** ARM_PERMIT dip ≥ 50 ms costs ≥ 40 % of the charge: the 50 ms hold after a drop, `rearm_blocked` during an IOX_B/IOX_D read failure, and the 300 ms early-press block. Each restarts the multi-second recharge with no indication (N1). |
| K1 / U_HOLD release against the 50 ms permit hold | K1 4 ms [U] and U_HOLD ≤ 1 ms [U] against 50 ms: sufficient; any HW_LATCH fall becomes a full drop. |
| 300 ms "in pulse" allowance of the weld rule | A set where K1 seals but U_HOLD does not (short tap, slow U_HOLD) leaves K1 closed with RUN_HD dead. After 300 ms that is K1_WELD (fatal, no reset). Fail-safe, but it is a false weld (N2). |
| 5 ms WDI pulse | Falling edges every 10 ms; both-edge counting would see 5 ms. Both are inside tWDL(max) 2.22 ms … tWDU(min) 23.375 ms [D per the doc]. A dead control tick leaves WDI high, so WDO fires. IWDG at about 250 ms. **Gap:** the boot path before the ticks start (HSE timeout, I2C probes) is not covered (README); with JP1 closed a slow boot can loop on WDO resets (fail-safe). Keep JP1 open until it is measured, as the README says. |

## 8. Loop decision table (question 5)

Inputs [F]:
- cmp: channel A comparator (OK, OPEN, SHORT);
- B: channel B, via IOX_D (closed / open);
- ana: analog copy (OK 620–1500 Ω, OPEN > 1650 Ω, SHORT < 560 Ω, otherwise marginal).

| Case | Firmware action | Verdict |
|---|---|---|
| Latched, any of cmp ≠ OK, B open, ana OPEN/SHORT for 2 ms | ARM_PERMIT withdrawn + STOP_ESCALATED | correct (closes C2's firmware half) |
| A closed, B open, ana OPEN for 20 ms | LOOP_FAIL (A stuck healthy) | correct |
| A open, B closed, ana OPEN | LOOP_FAIL (B stuck healthy) | **correct only above about 2.9 kΩ. Between 1.65 and 2.6 kΩ both channels are right (different thresholds by design) and LOOP_FAIL is wrong (N6, [E])** |
| A says open / B closed, or the reverse, with ana OK or marginal | LOOP_DISCREPANCY (non-fatal, permit withheld) | correct: the channel saying open holds the chain open anyway |
| cmp SHORT (B blind to shorts) | not a disagreement; permit withdrawn while latched | correct |
| ana alone disagrees with A and B agreeing | LOOP_DISCREPANCY after 200 ms; while latched the permit is withdrawn (ana_bad) | acceptable (an ADC fault and a double hardware failure look the same; the firmware stops either way) |
| IOX_D unknown | falls back to the stage-2 A-vs-analog rule (LOOP_FAIL after 5 ms while latched) | correct |
| U21/Q22 or U21B/Q_LB short | not visible: the comparators are correct and nothing is compared at node level | **gap (N3)** |

## 9. Host claim "no automatic resumption" (question 6)

Read: `rr_coverage/supervisor.py` (commands, holds, `step`), `rr_coverage/motion.py` (`inhibited`, `step`, `_hold`), `rr_core/chassis_link.py` (`_drive`, link up/down, HELLO), `rr_guidance/guidance.py` (`step`, `on_control_lost`), `rr_bringup/app.py` (restart and checkpoint), `rr_sim/scenarios.py` s15, `rr_core/fakes/chassis.py`.

**Verdict: true in every path I read.**
- **Coverage scan and step-and-count hop series.** `Mission.step` enters HOLD on any chassis mode other than ARMED_IDLE/MOVING (with the link up). The mover holds on any inhibit, including a link down and any rejected non-zero DRIVE. `_enter_hold` cancels the mover and clears the command. `chassis_link._drive` drops a rejected non-zero command and never resends it. Only `resume` (an operator command, MOTION_COMMANDS in the web layer) leaves HOLD, into the RECOVER phase. On the chassis side, `rrch_drive_stop` forces the full pre-motion alert on the next start even inside a hop series with a raised `alert.rest_ms`.
- **Guided revisit.** A HELD/BLOCKED/FAILED mover aborts the move ("re-arm and send a fresh command"). The automatic REAPPROACH retry happens only after a move that completed (DONE) and only while not inhibited; it is part of the same commanded move, not a resumption after a stop.
- **Link loss.** The command is cleared on link down. HELLO opens a new session, and the chassis latches HOST_LINK_LOST if it was moving. The mission stays HOLD until `rearm` + `resume` (s15 c).
- **Remote PAUSE clear.** `rearm` sends only REARM_SW, and is refused while hardware reasons are present. The mission stays HOLD until `resume` (s15 b).
- **Host process restart.** The mission is rebuilt from the plan; the checkpoint restores only task DONE status; the state is CONFIGURE. The `"resume"` journal op in `pipeline.py` is a trajectory epoch, not motion.

**Caveats.**
- The evidence (s15) runs against the Python fake chassis, not the firmware emulator. The fake models a fixed 2 s "DISCHARGE_TIME" and a `rearm_refusal`/`REARM_REFUSED` interface the firmware does not have. The no-auto-resume property does not depend on these, but the s15 check "REARM pressed too early is refused **and reported**" tests a feature that does not exist on the robot.
- **Change:** either implement the refusal report in the firmware (N1) or remove it from the fake. Run s15 once against `rr_chassis_sim` as well.

## 10. Residual-risk list as I would state it

**No hardware barrier after one fault** (`chassis_safety_chain.md` §6.1, completed):
1. A welded head-rail switch or a head-internal bypass of the switch string: that rail zone.
2. A welded or shorted body bumper switch: that side (rear ToF in firmware only).
3. A kΩ-level leak from LOOP_SNS to a supply: both loop channels.
4. A board short of RUN_HD, K1_RUN or CHAIN_END to a supply: only E-stop pole B, plus firmware nSLEEP.
5. A W-018 multi-pair crush: one unintended arming. It lasts the mission until the firmware drops ARM_PERMIT on a held REARM contact (§6 b).
6. *(add)* HANDS-ON welded / W-017 lamp-to-contact short: the hands-on worker relies on the lit lamp only.
7. *(add)* Selector RUN contact welded: SERVICE no longer inhibits; use OFF for hands-on work.
8. *(add, improbable)* W-015 multi-pair crush: E-stop lost.

**Latent faults with no periodic test** (one barrier left until a second fault):
- U_HOLD, Q_HSET or HOLD_A short;
- U_LS or LS_A short;
- D_RUN short, RELAY_RTN to GND;
- U21/Q22 or U21B/Q_LB short (N3);
- Q_SETA/C_SC or Q_SETB short;
- Q_SDIS open;
- U23/U40 (no boot watchdog test);
- K2/K3 brake path open (no dynamic deceleration check);
- clamp Zener short or open;
- U9 stuck high;
- selector RUN welded;
- plug-link and inlet channels.

Mitigation: §8 steps 3 (each loop channel alone), 7, 9 and 10 repeated at periodic service, plus N3's CH_N6A tap.

**Conditional on temperature:** the RUN_12V-short barrier (D_RUN leakage, N5) and the K1 set margin (T11, N1).

**Unchanged stated limits:**
- not a certified safety function;
- no hardware speed or force limit (#73);
- no holding brake on slopes (T8: stops only up to about 3–6°);
- every timing, threshold and leakage value tagged [U]/[A] is still unmeasured; nothing has been built.

**Could not be assessed from the files:**
- datasheets: TLP241A (trigger current, turn-on/off), G6S-2 operate/release, B160 reverse leakage, TPS3430 start-up behaviour after power-on and WDO release, TLV3201 pinout, TCA9534 registers;
- routed copper (the board is not routed);
- real behaviour of the set stage on hardware.
