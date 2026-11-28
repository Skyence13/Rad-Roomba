# Review of chassis stage 4 and firmware round 4: traction inhibit

Reviewer: the same independent engineer as `REVIEW_traction_inhibit.md` and `REVIEW_traction_inhibit_followup.md`. Date: 2026-11-28. Bounded review of the stage-4 parts only. Not a certified safety assessment: the design states it is not a safety function.

Tags: **[N]** netlist (circuit.py + overrides.py, queried with my `q.py`; `overrides.py` self-check PASSED) · **[P]** placement (`out/pinmap.json`) or DRC rules (`RR-CHS-MAIN.kicad_dru`) · **[F]** firmware source at HEAD · **[E]** emulator run with my own fault model (scratchpad copy `…/review_chain/emu4/`, repository untouched) · **[C]** my calculation · **[I]** inferred or recalled datasheet value.

Run: `firmware/chassis/check.sh` exit 0 (test_chain 331, test_state_machine 1195, test_review 65, test_rearm 45, test_drive 2476, integration tests, both STM32 images). The board was not rebuilt.

## 1. Closure of N1–N6 and the minors

| Item | Status | Evidence |
|---|---|---|
| **N1** re-arm refused when following `rearm_ready`; repeated presses never succeed | **Closed**, with operating limits to state (S1, S2) | [N] U33B compares SET_DIV (1 M / 348 k from SET_CAP, hysteresis R_SDH 2.2 M) with CLAMP_REF 2.5 V: **SET_READY rises at 10.82 V and falls at 9.32 V** [C], as T11 says. Q_SETC in the stack (gate from SET_READY via 100 k / 470 nF), so a press while SET_READY is low cannot touch C_SET. R_SET 15 k. [F] `rearm_ready` comes from SET_READY_RB high ≥ 30 ms; every press gets REARM_REFUSED with a reason (`rearm_why`, press outcome after 300 ms); `rearm_refusal` is in the ICD (§4.6) and in the host fake. |
| **N2** short taps → fatal LATCH_NO_REARM | **Closed**, with a level-margin caveat (S3) | [N] C_SF 2.2 µF qualifies the press (T13: 3.2–11.2 ms before a pulse can start). The set contact is now read on IOX_A GPB6 at 1 kHz (R_SRB 33 k / R_SRB2 47 k from REARM_SET_RAW). [F] Both edges come from the 1 kHz lines. A K1 sealed without U_HOLD is PARTIAL: ARM_PERMIT is withdrawn for 200 ms, non-fatal, and K1_WELD needs CHAIN_END known dead. |
| **N3** loop photo-MOS short latent | **Closed** | [N] CH_N6A tap (R_N6A1/R_N6A2/C_N6A/D_N6A) → IOX_D P6. [F] LOOP_SW_SHORT: a channel open while the node behind its photo-MOS is still live (CHN6A_RB for U21/Q22, BODY_BUMPER_L_RB for U21B/Q_LB) on two samples is fatal. Self-test before every arming (`loop_test_step`): TEST_A must take GPA5 and CHN6A_RB low; TEST_B must take loop B and CH_N8A low while A stays closed. |
| **N4** U_HOLD/U_LS LED nodes and the DRC rule | **Closed** | [P] `chain_to_supply` now lists HOLD_A, LS_A, HSET_D, U_SET_K and RELAY_RTN, and 3V3/V5_AUX as aggressors. No pad of these nets is within 1.6 mm of a 3V3/V5_AUX/VBAT_SW/V12_AUX/VSYS pad on the same side. |
| **N5** Schottky D_RUN leakage | **Closed** | [N] D_RUN is an S1G; R_RHD 10 k from RUN_HD to GND. [C] S1G leakage of tens of µA × 10 k stays far below the LED forward voltage (T14 agrees). Brake-relay release is unchanged: each coil keeps its own clamp across it; the bleed only makes RUN_HD fall faster. Cost: 1.3 mA more chain current, 17 mW. |
| **N6** loop between the channel thresholds made fatal | **Closed** | [N] R_LB2 30.9 k: channel B threshold 1.22 V → loop **1.89 kΩ** [C]. [F] 1.65–2.05 kΩ gives HEAD_LOOP_OPEN + LOOP_HIGH_R; LOOP_FAIL only if B closes above 2.05 kΩ or A closes with the analog copy open. Margin above B's tolerance is only about 5 % against an analog copy that assumes V5_AUX = 5.00 V (not measured): see O1. |
| m-B P17 drives the discharge transistor | **Closed** | [N] Q_SDISB has its own divider from CHAIN_END (100 k / 56 k, C_SDB 1 µF). P17 no longer touches the set stage. |
| m-C 5.5 V ESD on the aux line | **Closed** | [N] D29 removed; D_AUX (PESD15VL2BT) on REARM_BTN_RAW/BTN_3V3. |
| m-D W-018 note | **Not closed** | `harness/cables.md` W-018 still says "section 5 rows 42-46" and still gives the lay instruction that cannot hold in a 3-pair bundle. |
| D1 stale documents | **Mostly closed** | TIM8 break now described consistently (§2.1, README). New inconsistency: T13 says PARTIAL "drops ARM_PERMIT 50 ms"; firmware and ICD use 200 ms. |

## 2. New findings

### Major

**S1 — The latent-fault service tests S4 and S5 cannot be done on the assembled robot, and S5's pass criterion fails a healthy board.**
- [P] Every chain test point the tests need is on the **bottom** side: TP38 CHAIN_END, TP39 RUN_12V, TP61 K1_RUN, TP62 RELAY_RTN, TP60 CH_N6A, TP40 COIL_RTN. `layout_guidance.md` puts the gap pad and the bridge-tray contact on the bottom. [I] With the board mounted these points are not reachable, so S4 (§8 step 9, bridging K1 pole B) and S5 (§8 step 10, RUN_12V to VBAT_SW through 10 Ω) need the main board out. Section 6.2 presents them as 6-monthly checks "wheels off the ground". Tests that need the board removed will in practice be skipped, and the latent faults they control (U_HOLD, Q_HSET, U_LS, D_RUN, RELAY_RTN) then stay latent for life.
- [N] S5 asks for "RELAY_RTN to GND resistance > 100 kΩ with the latch down". A healthy board reads about **37 kΩ**: RELAY_RTN → K2/K3 coils (180 Ω) → RUN_12V → R117 22 k + R118 15 k (the HW_LATCH_RB tap) → GND. The clamp diodes block in that polarity. A technician either fails a good board or learns to ignore the criterion.
- [N] S5 also claims to cover "R_RHD open". With a silicon D_RUN at room temperature, R_RHD open changes nothing measurable in S5, and there is **no test point on RUN_HD**. That claim is not real; R_RHD needs a resistance measurement at its pads (top side).
- **Change:**
  - Bring TP38, TP39, TP61, TP62 and a new RUN_HD test point to the top side, or to a service header on the board edge (TP38–TP61 is the K1 pole B bridge for S4, so no relay pins need clipping).
  - Correct S5's criterion to "RELAY_RTN to GND 30–45 kΩ, latch down, pack removed; < 1 kΩ = RELAY_RTN short".
  - Measure R_RHD (10 kΩ) at its pads.
  - State which S-tests need the board out.

### Minor

**S2 — COIL_HOT is judged on the board NTC beside the H-bridges, not at K1.**
- [F] `rearm_why` refuses with COIL_HOT above 45 °C board NTC (RT1, "next to the H-bridges"); [F] it is a *reason*, not a block, so a press may still set.
- After driving, or in a 45–60 °C trailer (inside the contract's 60 °C limit), the lamp says "not ready / coil hot" while a press would usually work (T11: set margin 5.5 ms at 50 °C). Either the operator learns that the lamp is wrong, or the robot cannot be re-armed in the upper part of its stated temperature range.
- **Change:** state the 45 °C limit as an operating limit in the contract, or measure the temperature near K1. Make the lamp and STATE agree with what the hardware will do: block the press when COIL_HOT, or show it as a warning only.

**S3 — Thin high-level margin on the 1 kHz set-contact readback.**
- [N]+[C] With the contact closed, REARM_SET_RAW = V5_AUX × 29.6 k/30.6 k (R_SPD 47 k ∥ R_SRB+R_SRB2 80 k, behind R_SSRC 1 k). GPB6 then reads 2.83 V nominal, and 2.76 V with V5_AUX at −2.5 %. MCP23S17 VIH(max) = 0.8 VDD = 2.66–2.73 V for a 3V3 rail at 3.33–3.41 V: **30–100 mV of margin**.
- If GPB6 misses the high on a press the hardware accepts, the firmware sees only the aux edge and declares LATCH_NO_REARM, which is fatal.
- **Change:** R_SRB 27 k (about 2.99 V), or take the readback after R_SSER with its own divider.
- The doc's "2.7–2.9 V HIGH" should be compared with VIH(max), not typical.

**S4 — A stuck-on Q_LTA is fail-safe but misreported.**
- [N] The analog loop copy (HEAD_LOOP_SENSE) is taken from LOOP_F, the node Q_LTA pulls to ground. A D-S short of Q_LTA therefore makes channel A *and* the analog copy read open while channel B (from LOOP_SNS) correctly reads closed. [F] The rule reads that as "B stuck healthy".
- [E] Q_LTA stuck on, armed: latch dropped, FAULT with LOOP_FAIL; from power-up the same. Fail-safe and detected, but the diagnosis points at channel B.
- Also, the analog "arbiter" is not independent of channel A's filter and test FET.
- **Change:** take the analog copy from LOOP_SNS through its own RC, or add "Q_LTA stuck" to the LOOP_FAIL diagnosis text.

**S5 — A gloved long press arms and then drops 2 s later with a misleading reason.**
- [E] REARM held 2.5 s: the latch rose after 7 ms and dropped at 2057 ms (the W-018 rule `latched_held_ms > 2000`). After release REARM_HELD is cleared (non-sticky) and the latched hardware reason is MCU_NOT_READY. No REARM_REFUSED is given because the latch had risen.
- Safe, but an operator pressing firmly for more than 2 s (gloves, cold) gets an unexplained drop, and C_SET then needs 2.3–6 s to recharge (T12).
- **Change:** report a dedicated reason (REARM_HELD_AFTER_SET), sound the buzzer while the button is held, put "press briefly, < 2 s" in the operator procedure, or raise the limit to about 5 s (the W-018 crush case then lasts 5 s instead of 2 s).

**S6 — Latent set-stage faults assigned to S3 are not all revealed by S3.**
- [N] S3 (§8 step 7 a–g) reveals a shorted Q_SETA (b), a shorted Q_SETB (a, g) and a shorted Q_SETC (press 1 s before SET_READY, watching SET_CAP).
- No step reveals a **shorted C_SC or an open R_SG**: both turn the edge requirement into "held level", and every S3 step either opens the set line or holds both lines together (which also sets on a healthy board).
- **Add:** (h) close the set line alone, wait 0.5 s, then close the aux line: no set.

### Stage-4 parts checked and found sound

| Part | Verdict |
|---|---|
| **SET_READY / U33B and divider** | Stuck high (U33B cannot sink, SET_READY shorted to 3V3, LM4040 short) re-enables Q_SETC permanently. That is only the stage-3 behaviour: an early press dumps C_SET and is reported SET_FAILED. [F] SET_STAGE_FAULT (SET_READY high with CHAIN_END dead > 1 s) catches it at the first drop longer than 1 s, at the latest at the preflight brake test. Stuck low / LM4040 open: cannot arm, reported NOT_READY or SUPPLY_LOW. **Common cause noted:** U33B shares U33 and CLAMP_REF with the bus clamp U33A, so an LM4040 fault also disables or forces the regeneration clamp (forced: F_CLAMP trips, BUS_CLAMP readback; disabled: latent, revealed only because arming is blocked). |
| **Q_SETC gate network** | R_SCG open or C_SCG short: never on, so SET_FAILED is reported. Q_SETC D-S short: latent and harmless (stage-3 behaviour); S3 reveals it. On-time 13–28 ms after SET_READY rises: [F] the firmware offers the press only 30 ms after the first high sample. |
| **C_SF** | Open: no qualification, but the 1 kHz readback still sees any closure that can operate K1. Short: cannot arm. |
| **Partial set** | [F] handled non-fatally (PARTIAL, ARM_PERMIT withdrawn 200 ms). The emulator switches U_HOLD instantly, so on the board PARTIAL will occur somewhat more often than simulated; the firmware outcome is the same. |
| **Q_LTA / Q_LTB** | [N] Drain on LOOP_F / LOOP_FB, source to GND: they can only force a channel open. Gates 100 k to GND, driven by TCA9534 P4/P7, which power up as inputs: **off at reset**. IOX_D is outside the NRST domain, but the port writes the output register before the configuration (`bsp.c` init) and checks configuration 0x6F and the output register every pass. [F] Never asserted while latched (`lt_start` needs the latch down; a latch rise aborts the test and clears the outputs). Even if asserted, the chain only opens. Stuck on: A → LOOP_FAIL (S4); B → LOOP_DISCREPANCY, arming withheld. Fail-safe. |
| **CH_N6A tap** | [N] 100 k / 56 k with a BAT54 clamp, as every other tap: P6 as a 3.3 V output could push ≤ 33 µA into CH_N6A, which cannot hold anything. The configuration is read back. |
| **D_AUX, R_RHD, S1G** | Correct (see N5 and m-C above). |
| **BUS_CLAMP on IOX_D P3** | Now read at 100 Hz over I2C instead of 1 kHz. Short clamp pulses may be missed, but this is diagnostics only; a stuck clamp is continuous and still seen. 100 k / 33 k from the 10–12 V CLAMP_G gives 2.48–2.98 V against TCA9534 VIH 2.31 V [I]. |
| **Self-test effect on C_SET** | [C] The 30 ms dead / 20 ms live / 30 ms dead sequence takes SDISB_G to about 1.2–1.4 V at the end of TEST_B, near Q_SDISB's 0.8–1.5 V threshold, so a short partial discharge is possible. It runs about 100 ms after chain closure, when C_SET is nearly empty anyway: negligible. |

## 3. Emulator against the netlist at the stage-4 parts

| Constant | Emulator | Netlist / tables | Could it hide a defect? |
|---|---|---|---|
| SET_READY thresholds | 10.8 V up / 9.3 V down | 10.82 / 9.32 V nominal; 10.57–10.99 V with tolerances (T11) | No. The firmware's SUPPLY_LOW uses the worst-case 11.7 V. The emulator arms nominal boards at 11.4–11.7 V, where a worst-case board never would; the outcome is reported either way. |
| C_SET final voltage | 0.989 · (vbat − 0.4) | same (T12) | No |
| Qualification | 6.0 ms fixed | 3.2–11.2 ms (T13) | Small: only the nominal corner is simulated by default (configurable) |
| Pulse length | 110 ms − qual; ended by release; Q_SETC off 50 ms after SET_READY falls | 151–168 ms held; Q_SETC off 37–67 ms after the fall; effective about 52–82 ms | No (≫ K1 operate time) |
| K1 operate | 3 ms, 8.75 mA; "committed" at half the operate time [A] | ≤ 4 ms [U], 8.75 mA (T11) | No |
| U_HOLD turn-on | instant | ≤ 3 ms [U] | Partly: PARTIAL outcomes under-represented; firmware handling is non-fatal either way |
| K1 release / relays | 4 ms / 7.8–10.8 ms | same | No |
| Coil temperature | board NTC (temp[2]) for both | the NTC is beside the bridges, not at K1 | **Yes:** hides S2 (false COIL_HOT after driving) |
| Loop A / B / analog | 590–1550 Ω / 1890 Ω / analog follows Q_LTA | same [N] | No. Stuck-on test FETs are not modelled; my model gives S4. |
| C_SET discharge | "dead ≥ 50 ms" counter | RC integrator, 41–64 ms | Negligible (see the self-test row above) |
| GPB6 / REARM_SET level | logical | 2.76–2.83 V against VIH(max) 2.66–2.73 V | **Yes:** hides S3 |

The 7.5 V-style divergence of the last round is not repeated: every stage-4 threshold equals the netlist's nominal value. The two divergences that matter (S2, S3) are analog levels the emulator treats as logic.

## 4. Re-arm outcome logic (`rrch_chain.c`, `tests/test_rearm.c`)

Every press made with the latch down gets either the latch or a REARM_REFUSED reason within 300 ms. A refused press is never a fault. No corner I could construct refuses silently.

Remaining fatal outcomes on a legitimate press:
- GPB6 missing the high level (S3);
- the 2 s held-press drop (S5): non-fatal, but explained only as MCU_NOT_READY.

The REARM_HELD rule itself is right for the W-018 crush case. Its 2 s limit is short for a gloved operator (S5).

## 5. Periodic tests (section 6.2)

| Test | Reveals its assigned faults? | Possible on the assembled robot? |
|---|---|---|
| **P1** (per shift) | Yes for the E-stop (firmware pole A/B discrepancy), HANDS-ON (lamp must light), each bumper and rail zone (latch drop), selector RUN welded (MODE_RUN open in SERVICE). Seven drops with a re-arm of 2.3–6 s each (T12) fit in about 2 min. | Yes |
| **S3** set stage | Q_SETA, Q_SETB, Q_SETC: yes. **C_SC short / R_SG open: no** (S6). | Partly: J_BTN and the SET_CAP pad are on the top side, so it needs the body open plus a pulse generator. |
| **S4** U_HOLD / Q_HSET | Yes (bridge CHAIN_END–K1_RUN: RUN_HD must stay dead) | **No**: bottom test points (S1) |
| **S5** U_LS / D_RUN / RELAY_RTN / R_RHD | U_LS and D_RUN: yes. RELAY_RTN: wrong criterion. R_RHD: no (S1) | **No**: bottom test points (S1) |
| **S6** U23 / U9 | Yes, with the test firmware | Yes (SWD/test firmware, JP1 handling) |
| **S7** braking | Yes (spin-down, drop timing) | Yes, wheels off the ground; scope points partly on the bottom |
| **S8** plug link / inlet | Yes | Yes (inlet) |

## 6. Residual-risk statement for the traction chain as it now stands

*For the hazard owner to sign or refuse. Every value is calculated or assumed; nothing is built or measured.*

1. **What the chain does.**
   - Traction power (VMOT, brake-relay pick-up, bridge nSLEEP) exists only while two diverse hold elements (K1 relay, U_HOLD photo-MOS) are set. Only a two-contact, edge-qualified local REARM press can set them, and only with C_SET charged.
   - Opening any series element (selector RUN, E-stop both poles, HANDS-ON, charge cover and plug, head dock, head loop channels A and B, LAB key, both body bumpers, watchdog, ARM_PERMIT) removes it. The motors are then shorted through their brake resistors without power or firmware.
   - No network command can set it. In the files read, no single fault lets it restart without a REARM press.

2. **Single faults that leave no hardware barrier (§6.1):**
   - a welded head-rail switch or head-internal bypass (that zone);
   - a welded or shorted body bumper switch (that side);
   - a kΩ leak from LOOP_SNS to a supply (both loop channels);
   - a board short of RUN_HD, K1_RUN or CHAIN_END to a supply (only E-stop pole B remains);
   - a W-018 multi-pair crush (one arming lasting 2 s);
   - a welded HANDS-ON contact or W-017 lamp-to-contact short (the hands-on worker relies on the lit lamp);
   - a welded selector RUN contact (use OFF, not SERVICE);
   - a W-015 multi-pair crush (E-stop lost).
   The per-shift check P1 is the only control for the contact-type ones.

3. **Latent faults (one barrier left until a second fault).** These are controlled by the 6-monthly tests S3–S8. **As drawn, S4 and S5 need the main board removed and S5's criterion is wrong (S1)**, so U_HOLD, U_LS, D_RUN and RELAY_RTN faults are effectively uncontrolled until that is fixed. The U23 boot self-test is still absent (S6 covers it). The dynamic brake-deceleration check is still absent (S7 covers it).

4. **Operating limits created by the chain:**
   - no re-arm below about **11.7 V** pack, while the BATTERY_LOW stop is 11.2 V;
   - no guaranteed re-arm above **45 °C** board temperature;
   - no hardware speed or force limit (0.44 m/s, 93–170 N at stall);
   - no holding brake (stops on slopes only up to about 3–6°);
   - not a certified safety function.

5. **Conditions to sign.** I would sign items 1, 2 and 4 as a true description. I would **not** sign item 3 until S1 is fixed (top-side or edge service points, corrected S5 criterion) and S6 adds the C_SC/R_SG step. S3 (GPB6 margin) should be fixed or measured before the first build.
