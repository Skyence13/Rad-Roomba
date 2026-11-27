# RR-CHS-MAIN hardwired traction chain: circuit, timing, single faults, braking

Owner: chassis electronics. Evidence class: `calculated`. Nothing here is measured.
Tags: **[D]** datasheet value read, **[C]** calculated (`electronics/analysis/chassis_braking.py`, tables in `chassis_braking_tables.md`), **[A]** assumed, **[U]** UNVERIFIED.

**This is not a certified safety system.** It is a single-channel relay chain with diagnostics, built from standard (not force-guided) relays, photo-MOS relays, comparators and one microcontroller. It has no performance level, no category and no SIL, and it must never be described as a safety function. Section 6 lists every single fault found, and section 6.1 the ones that leave no hardware barrier.

Net and reference names are those of the netlist as built: `electronics/chassis_main/design/circuit.py` (stage 1) **plus** `electronics/chassis_main/overrides.py` (stage 2 S2-xx and stage 3 S3-xx). Stage 3 (2026-11-27) applies the fixes for the independent review `docs/reviews/REVIEW_traction_inhibit.md`; the change list with reasons is `electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md` section "Stage 3 (review fixes)". Firmware statements below name the function where the behaviour was read in `firmware/chassis/core` (state of 2026-11-27, commit 77507bc); everything else is marked "requested, not implemented".

## 1. Headline numbers

| Quantity | Value | Tag |
|---|---|---|
| Chain element opens → brake resistors connected (contact elements; also total power loss) | ≤ 10.8 ms | [D]+[A] |
| Same, HEAD_LOOP (either channel) / LAB_KEY (comparator + photo-MOS) | ≤ 13.3 ms | [D]+[A]+[U] |
| Same, firmware withdraws ARM_PERMIT | ≤ 13.8 ms | [A] |
| Same, MCU stops (external window watchdog, falling edge every 10 ms) | ≤ 43.4 ms after the last valid falling edge | [D]+[A] |
| VMOT eFuse off / bridges asleep after an element opens (both fed from RUN_HD, upstream of K1 release) | ≤ 1.0 / 2.2 ms | [A]/[C] |
| Brake resistor (per motor, across the relay's NC contacts) | **1.0 Ω**, 2512, 2 W pulse-rated; brake loop 3.22 Ω cold including the 2.18 Ω winding | design value |
| Stopping distance from 0.20 m/s, level floor (nominal / conservative) | 8.8 / 28.6 mm | [C] |
| Same, from 0.10 / 0.05 m/s | 3.8 / 14.3 mm, 1.6 / 7.1 mm | [C] |
| Same from 0.20 m/s with 100 °C windings (+ magnet derating) | 9.8 / 34.2 mm (12.0 / 47.5 mm) | [C]+[A] (T9) |
| Worst calculated case: MCU fails with full drive torque applied, from 0.20 m/s | 57 mm | [C], conservative |
| Downhill slope the braked robot is calculated to stop on (half friction / nominal friction) | ≤ 3–6° / ≤ 6–10°; beyond, it creeps at 12–36 mm/s (T8) | [C]+[A] |
| VMOT below 1 V after a drop (1 kΩ bleed, +20 % capacitors, 14.6 V) | ≤ 2.65 s (τ 0.82–0.99 s) | [C] (T10) |

The "conservative" column assumes the lower force constant (17.4 N/A, from the catalogue stall torque), a rotor inertia of 2 × 10⁻⁶ kg m² per motor and **no friction at all**; "nominal" uses the power-balance constant (31.7 N/A), 1 × 10⁻⁶ kg m² and the friction implied by the 0.2 A no-load current. The rotor inertia is not published by Pololu and dominates the result; a wheel-up spin-down test (§8 step 12) closes it. The firmware emulator and this model use the same constants (IB-03): their agreement is consistency, not validation.

For comparison the contract stop model with its example inputs (0.15 s, 0.40 m/s², 20 mm) gives 100 mm at 0.20 m/s. The head rail's lead over the entrance film (7.4–11 mm, design text §4) is **not** covered at 0.20 m/s by the conservative figure and is marginal at 0.10 m/s: the rail needs ≥ 15 mm of over-travel at 0.10 m/s, or the approach speed near obstacles stays at 0.05 m/s, until the spin-down test is done.

## 2. Circuit description

### 2.1 Series path

```
VBAT_SW ─ F_CHAIN (PTC 0.20 A hold) ─ CH_N0
  CH_N0  ─[ J_MODE 3-4: selector contact closed only in RUN ]───────────── CH_N1   MODE_RUN
  CH_N1  ─[ J_ESTOP 1-2: E-stop pole A, NC, positive opening ]──────────── CH_N2   ESTOP (high side)
  CH_N2  ─[ J_HANDS 1-2: HANDS-ON maintained button, NC ]───────────────── CH_N3   HANDS_ON
  CH_N3  ─[ J_COVER 1-2: inlet cover switch, closed = cover shut ]───────── CH_N4A  CHG_COVER (cover)
  CH_N4A ─[ U20 photo-MOS: on only if plug link absent AND inlet dead ]─── CH_N4   CHG_COVER (plug)
  CH_N4  ─[ J_DOCK 1-3: head dock switch ]──────────────────────────────── CH_N5   HEAD_DOCK
  CH_N5  ─[ U21 photo-MOS: loop channel A, U30 window 0.59–1.55 kΩ ]───── CH_N6A  HEAD_LOOP (A)
  CH_N6A ─[ U21B photo-MOS: loop channel B, U46, loop < 2.70 kΩ ]──────── CH_N6   HEAD_LOOP (B)   stage 3
  CH_N6  ─[ U22 photo-MOS: PRES_ID 3.92–5.64 kΩ (head, no LAB resistor) ]─ CH_N7   LAB_KEY_N
  CH_N7  ─[ J_BUMP_L 1-2 ]─ CH_N8A ─[ J_BUMP_R 1-2 ]────────────────────── CH_N8   BODY_BUMPER
  CH_N8  ─[ U23 photo-MOS: external window watchdog satisfied ]──────────── CH_N9   WDG_OK
  CH_N9  ─[ U24 photo-MOS: MCU ARM_PERMIT high ]────────────────────────── CHAIN_END  ARM_PERMIT

Latch (two diverse hold elements in series, stage 3):
CHAIN_END ─ D_SEAL ─[ K1 pole A NO: seal-in ]─ K1_COIL_P ─ K1 coil ─ COIL_RTN
CHAIN_END ─[ K1 pole B NO ]─ K1_RUN ─[ U_HOLD photo-MOS, self-holding ]─ RUN_HD ─ D_RUN (Schottky) ─ RUN_12V
     U_HOLD LED: from RUN_HD (1.5 kΩ) = holds itself while RUN_HD is live; set only by the REARM set pulse (Q_HSET from V5_AUX)
RUN_HD  ─ U8 EN divider (R133/R134, VMOT eFuse) ; U9.B own tap (HW_LATCH_G, nSLEEP gate) ; U_LS LED (1.5 kΩ)
RUN_12V ─ K2 coil ─┐  RUN_12V ─ K3 coil ─┐   (brake relays; each coil clamped by 1N4148W + 20 V Zener across the coil)
                   └──────── RELAY_RTN ──┴─[ U_LS photo-MOS, low side ]─ COIL_RTN
COIL_RTN ─[ J_ESTOP 3-4: E-stop pole B, NC ]─ GND                                   ESTOP (low side)

Set stage (on board, stage 3): C_SET 100 µF charged CHAIN_END ─ D_RSET ─ R_SET 22 kΩ ─ SET_CAP;
SET_CAP ─[ U_SET photo-MOS ]─ K1_SET ─ R96 0 Ω ─ K1_COIL_P.  U_SET LED on only while Q_SETA (gate = AC-coupled edge of the
REARM set contact, J_BTN 1-2, 110 ms) AND Q_SETB (gate = level of the REARM aux contact, J_BTN 3-4) both conduct.
C_SET is discharged (Q_SDIS, 1 kΩ, τ 0.1 s) whenever CHAIN_END is dead.
```

The order is exactly the contract's `safety_chain.series_elements`; HEAD_LOOP is now two series photo-MOS (channels A and B), CHG_COVER is two series contacts (cover switch, plug-link element) and BODY_BUMPER two (left, right), each with its own readback. **Contract note for the lead:** `safety_chain.series_elements` stays valid; its HEAD_LOOP entry should say "two channels in series".

Design rules applied:

- **Coil current is the chain current.** K1 is fed from CHAIN_END through D_SEAL and its own seal-in; K2 and K3 are fed from CHAIN_END through K1 pole B, U_HOLD and D_RUN, and return through U_LS. Opening any element removes CHAIN_END at once; K2/K3, the VMOT eFuse enable and the nSLEEP gate do not wait for K1 to release. About 95 mA flows through every element when latched (K1 11.7 mA, K2 and K3 33–40 mA each, U_HOLD and U_LS LEDs 6–9 mA each), which also wets the switch contacts.
- **E-stop has two poles.** Pole A opens the high side of the chain; pole B opens the common return of all three coils (K2/K3 through U_LS). Either alone drops K1, K2 and K3. With pole B alone, RUN_HD (VMOT enable, nSLEEP) falls when K1 releases (≤ 4 ms [U]).
- **"No restart without REARM" rests on two diverse hold elements in series:** K1 (relay, seal-in) and U_HOLD (photo-MOS whose LED is fed from its own output RUN_HD). U_HOLD can be set only by the REARM set pulse, through Q_HSET from V5_AUX: nothing on the coil side of K1 can reach its LED. A welded K1 contact (either pole) therefore re-energises K1 when the chain re-closes, but U_HOLD stays off and RUN_HD, RUN_12V, VMOT and the brake relays stay dead. The weld is visible to firmware through LATCH_NC_RB and LATCH_RUN_RB (§2.3).
- **REARM can only set, never hold, and only from the robot.** The K1 coil node no longer leaves the board (stage 3, review C1). The REARM set contact (J_BTN 1-2) only switches 5 V (V5_AUX through 1 kΩ) into an on-board stage that needs the *closing edge* of the set contact (1 µF coupling, gate pulse about 110 ms) **and** the *level* of the second, separate aux contact (J_BTN 3-4) at the same time. Then U_SET dumps C_SET into the K1 coil (τ = 100 µF × 1028 Ω = 103 ms) and Q_HSET lights U_HOLD's LED. A held, shorted or welded REARM gives at most one pulse and then nothing; a shorted U_SET connects C_SET permanently to the coil, so C_SET never charges and the coil sees at most CHAIN_END × 1028/23 028 ≤ 0.65 V (below the 1.2 V must-release [D family]). Set margin over supply and temperature: T11 (sets at ≥ 12 V pack up to +50 °C, at 10 V only up to +23 °C; where it does not set, REARM is refused, which is fail-safe).
- **REARM needs a healthy, closed chain for about 1–2 s first.** C_SET charges only from CHAIN_END (τ 2.2 s) and is emptied within about 0.3 s whenever CHAIN_END is dead (Q_SDIS). A REARM pressed while any element is open finds C_SET empty; a chain that closes during the pulse charges C_SET far too slowly to set K1 (review m3, m11: "re-arming is locked out" now applies after every drop, not only after a REARM press).
- **No back-feed.** D_RSET (silicon, low leakage) stops C_SET feeding CHAIN_END and the nodes behind an opened element (review M1); D_RUN stops anything on RUN_12V feeding RUN_HD, K1_RUN or CHAIN_END, and keeps the K2/K3 coil kick away from the chain elements (an opening photo-MOS now sees at most the pack voltage instead of pack + 25 V). The HANDS-ON lamp is fed from the upstream node to ground, not across the contact. Every readback is a 100 kΩ (22 kΩ on PB12/PD2) tap or sits behind ≥ 47 kΩ (§2.3).
- **Three independent consequences of a drop**: (1) K2/K3 release: each motor's two terminals leave the bridge (NO contacts) and are joined through a 1.0 Ω brake resistor (NC contacts); (2) the VMOT eFuse U8 loses its enable (RUN_HD) and VMOT is bled to zero through 1 kΩ; (3) the bridges' nSLEEP is forced low by U9 (AND of the MCU's DRV_NSLEEP and its own RUN_HD tap HW_LATCH_G), independent of firmware. The TIM8 break input is **not used** (review M4; firmware README).
- **A board short of RUN_12V to a supply does not move the robot** (stage 3, review M6): RUN_12V then has a supply, but the brake relays' return U_LS is lit only from RUN_HD, which only a real latch can feed (D_RUN blocks back-feed), and VMOT and nSLEEP are taken from RUN_HD too. A short of RUN_HD, K1_RUN or CHAIN_END itself is in §6.1.

### 2.2 Electronic elements

| Element | Sensing | Closed when | Fails open on |
|---|---|---|---|
| U20 plug link / inlet | Gate of Q20 is pulled up from V5_AUX; the plug link (J_PWR 4–8, linked in the charge plug) or Q21 (on when the inlet carries > ~10 V) pulls it low | no plug link **and** no inlet voltage | loss of V5_AUX, link wire shorted to ground |
| U21 HEAD_LOOP channel A | V5_AUX → R65 1.00 kΩ → R66 100 Ω → J1 pin 5 → head (3 NC rail switches + 1.00 kΩ) → J1 pin 6 → R67 100 Ω → LOOP_SNS → R68 1.00 kΩ to ground. LOOP_SNS → R69/C75 (1 ms) → LOOP_F, compared by U30 (LM2903B, wired-AND open-collector outputs, R74 10 kΩ pull-up, drives Q22) with the taps of R70/R71/R72 on V5_AUX (ratiometric; R73 2.2 MΩ keep-alive on the lower tap) | loop 0.59–1.55 kΩ [C] (1.33–1.79 V; healthy 1.56 V; short 2.27 V; open 0 V) | open loop, unplugged J1, shorted pair, either line to ground or +12 V, loss of V5_AUX |
| U21B HEAD_LOOP channel B (stage 3) | Same LOOP_SNS node, own filter R_LB1/C_LB1 (1 ms) → LOOP_FB, own reference R_LB2/R_LB3 on V5_AUX (1.02 V), comparator U46 (TLV3201, CMOS input, push-pull, a different type and technology from U30), drives Q_LB → U21B LED. Output pin adjacent to V− (a solder bridge opens channel B) | loop < 2.70 kΩ (detects open and high-resistance loops; short detection stays with channel A and U32A) | open loop, loss of V5_AUX, output stuck low |
| U22 LAB_KEY_N | VREF_3V0 → R77 4.70 kΩ 0.1 % → J1 pin 7; code resistor returns to J1 pin 2. Window comparator U31 against R79/R80/R81 on VREF_3V0 (R82 pull-up, Q28) | PRES_ID 3.92–5.64 kΩ [C] (1.364–1.636 V; head direct = 1.500 V) | no head (> 5.64 kΩ), LAB extension fitted (1.137 kΩ → 0.58 V), extension alone (1.50 kΩ → 0.73 V), short, loss of VREF or V5_AUX |
| U23 WDG_OK | TPS3430 window watchdog U40, CWD = NC, SET0 = 0, SET1 = 1: **falling** edge on WDI required between tWDL(max) 2.22 ms and tWDU(min) 23.375 ms after the previous one; tWDU(max) 31.625 ms; WDO 170–230 ms [D, datasheet read 2026-11-27]. Firmware: 5 ms high pulse every 10 ms (`rrch_supervise_100hz`): falling edges 10 ms apart. WDO drives Q23, Q29 (heater clamps, FAULT LED) and, through D13 and JP1, NRST. WDG_STROBE has a 10 kΩ pull-down (stage 3) | watchdog satisfied | missing, early or late strobe; loss of 3V3 |
| U24 ARM_PERMIT | MCU PB10 with R94 4.7 kΩ pull-down drives Q24 | pin driven high | MCU in reset, unprogrammed, in the ROM bootloader (AN2606 pin use not verified [U]: if PB10 were driven, U23 is still open because nothing strobes); loss of 3V3 |
| U_HOLD (stage 3) | LED from RUN_HD through R_HA 1.5 kΩ (5.9–8.9 mA), set through Q_HSET + R_HS 470 Ω from V5_AUX during the REARM pulse | latch set and RUN_HD live | any chain opening, K1 release, loss of V5_AUX before set |
| U_LS (stage 3) | LED from RUN_HD through R_LSA 1.5 kΩ | RUN_HD live | as U_HOLD |

The J1 loop is potential-free **at the head**. At the chassis it is sourced from V5_AUX and referenced to chassis ground: short-circuit current 2.3 mA, a short to +12 V drives the sense node high and opens channel A; both lines have 100 Ω + TVS + 1 ms RC. The lab extension (`harness/lab_extension.md`) adds only conductor resistance to the loop (0.35 Ω) and its 1.50 kΩ code on PRES_ID (pin 7 to 2), which opens U22. Putting the rail contacts themselves in the chain current path was rejected: the head has a 1.00 kΩ resistor in the loop, the contract makes the pair potential-free, and the chain current (95 mA at pack voltage) would then run through J1 and the detachable head.

The PRES_ID return shares J1 pin 2 with the head electronics current (about 30 mV at 1 A [C]) against a ±136 mV window.

### 2.3 Readbacks (what can and cannot back-drive the chain)

Chain node taps: 100 kΩ from the node, 56 kΩ to ground, 22 nF (τ ≈ 0.8 ms), BAT54 clamp to 3V3. Exceptions (stage 3, review M3): ESTOP_A_RB (PB12) and HW_LATCH_RB (PD2) are 22 kΩ / 15 kΩ. Read thresholds per input type [C; input levels: MCP23S17 VIH 0.8 VDD as stage 1 [D]; TCA9535/TCA9534 VIH 0.7 VCC [U]; STM32G474 VIH 0.7 VDD and pull-down 25–55 kΩ [U]]:

| Input | Tap | Node reads HIGH above | LOW below | With STM32 pull-down enabled (25 kΩ) |
|---|---|---:|---:|---|
| MCP23S17 (IOX_A) | 100 k / 56 k | 7.4 V | 1.8 V | n/a (GPPU must be off) |
| TCA9535 P17 (CHAIN_END_RB), TCA9534 IOX_D | 100 k / 56 k | 6.4 V | 1.8 V | n/a |
| STM32 PC13 (WDG_OK_RB) | 100 k / 56 k | 6.4 V | 2.8 V | 14 V: **pull must be off** |
| STM32 PB12, PD2 | 22 k / 15 k | 5.7 V | 2.4 V | 7.7 V (still valid at a 10 V pack) |

At a 10 V pack every chain node reads high on every input type. Pins that must have pulls disabled: PB12, PD2, PC13; all MCP23S17 inputs (GPPUA = GPPUB = 0).

Back-drive: a tap pin configured as a 3.3 V output pushes at most 33 µA (150 µA on the 22 kΩ taps) into a chain node, 8–35 times less than the smallest must-release current (1.17 mA for K1) [C], and cannot light a photo-MOS LED (none is fed from a chain node except U_HOLD/U_LS, which need ≥ 1.3 V across 1.5 kΩ from RUN_HD). Stage 3 removed the three paths the review found (M2):
- HEAD_LOOP_OK_RB (Q22 gate) and LAB_KEY_N_RB (Q28 gate) reach IOX_A GPA5/GPA7 through 47 kΩ (R_GA5, R_GA7): an expander output can no longer hold a sinking comparator node high (70 µA against mA).
- U9.B has its own tap on RUN_HD (HW_LATCH_G); PD2 is not connected to the nSLEEP gate at all.
- The IOX_A sentinel GPB7 reaches WDG_STROBE through 47 kΩ against a 10 kΩ pull-down: an expander output can raise WDI to 0.58 V at most (< VIL 0.99 V [D]), so it cannot strobe the watchdog while PB11 is high-impedance.
- REARM_BTN (GPB2) is fed from the aux contact through D_RB, so GPB2 as an output cannot enable the set stage (Q_SETB gate is on its own divider from the contact).

| Readback | Source | MCU / expander pin |
|---|---|---|
| MODE_RUN_RB, HANDS_ON_RB, CHG_COVER_RB, CHG_PLUG_LINK_RB, HEAD_DOCK_RB | CH_N1, CH_N3, CH_N4A, CH_N4, CH_N5 | IOX_A GPA0–GPA4 |
| HEAD_LOOP_OK_RB (via 47 k), HEAD_LOOP_SHORT_RB, LAB_KEY_N_RB (via 47 k) | U30 window (high = in window), U32A (high = loop below window), U31 window | IOX_A GPA5, GPA6, GPA7 |
| HEAD_LOOP2_OK_RB (stage 3, via 47 k) | U46 channel B output (high = loop < 2.70 kΩ) | IOX_D P2 |
| CHAIN_END_RB | CHAIN_END | IOX_B P17 (input) |
| BODY_BUMPER_L_RB, BODY_BUMPER_R_RB | CH_N8A, CH_N8 | IOX_A GPB0, GPB1 |
| ESTOP_A_RB, ESTOP_B_RB | CH_N2 (22 k/15 k); COIL_RTN P-MOSFET detector | PB12, PB13 |
| WDG_OK_RB | CH_N9 | PC13 |
| HW_LATCH_RB | RUN_12V (22 k/15 k): K1 AND U_HOLD AND chain live | PD2 |
| LATCH_RUN_RB (stage 3) | K1_RUN: K1 pole B closed AND CHAIN_END live | IOX_D P1 |
| LATCH_NC_RB (stage 3) | K1 pole A **NC** contact; K1_SEAL_A biased from 3V3 (D_K1B + 47 kΩ, ≤ 62 µA into the coil), so high = pole A released is valid with the chain dead | IOX_D P0 |
| REARM_BTN, REARM_SET_RB (stage 3) | aux contact (J_BTN 3-4); set contact (J_BTN 1-2) | IOX_A GPB2, IOX_D P3 |
| VMOT_SENSE, HEAD_LOOP_SENSE, HEAD_PRES_ID | analogue | PA2, PC1, PC0 |
| BRAKE_L_RB, BRAKE_R_RB | §2.4 | PC14, PC15 |

IOX_D (U47, TCA9534 at 0x22, stage 3) also carries a fixed pattern (P4 high, P5–P7 low through 10 kΩ) so that a dead or stuck expander is recognised.

A tap reads the **node**, i.e. "the chain is live up to and including this element". Firmware derives an element's state from the first dead node; an element downstream of an open one is unknown, not closed. With D_RSET fitted, nodes are no longer held up by C_SET after an opening: every tap falls within a few ms (tap τ 0.8 ms).

### 2.4 Brake relays and their readback

Per motor one Omron G2RL-2 (DPDT, 8 A, 12 V coil, 400 mW, release ≤ 5 ms [D]). Pole 1: common = motor terminal A, NO = bridge OUT1, NC = brake node A. Pole 2: common = motor terminal B, NO = bridge OUT2, NC = brake node B. The 1.0 Ω brake resistor joins brake nodes A and B. De-energised, the motor is disconnected from the bridge on both terminals and shorted through 1.0 Ω.

The state of the power contacts is measured: motor terminal A is biased from 3V3 through a Schottky and 2.2 kΩ; each bridge output has a 4.7 kΩ pull-down; two LM2903B comparators per motor look at OUT1 and OUT2 with a 0.20 V threshold. With the bridges asleep: relay released → `BRAKE_x_RB` **low**; relay energised → high; one NO contact welded → stays high. Low is reported only when both poles are positively isolated. Valid only while the bridges sleep; both levels are exercised on every arm/drop cycle (`rrch_chain_step`: the bridges wake only after both relays read connected; mismatch for 200 ms → VMOT_FAULT).

### 2.5 HANDS-ON indicator

The lamp is supplied from CH_N2 (upstream of the button) and switched by Q27, which conducts only while CH_N3 **and** HW_LATCH_RB are both low (Q25, Q26). Lit means: upstream chain live, HANDS-ON contact open, latch dropped. With D_RSET the back-fed CH_N3 that kept the lamp dark for seconds (review M1) no longer exists. If the E-stop is also pressed or the selector is not in RUN the lamp is dark (not confirmed by this lamp). The lamp feed runs beside the contact pair in W-017: a lamp-to-contact short bypasses HANDS-ON (row 9).

### 2.6 What stays live with the selector in OFF

As before: OFF opens the enable of the pack switch and of all three regulators through MOSFETs. Pack coupler, harness, main fuse, J_PWR pins 1–2, the TVS, the MOSFET drains and the 100 kΩ enable feed stay at pack voltage; a connected charger keeps its inlet side at 24 V. **OFF is a functional switch-off, not isolation.** Isolation for service is removal of the pack and of the charge plug.

## 3. Timing budget

See `chassis_braking_tables.md` T2. Contact-element case:

| t (ms) | Event |
|---:|---|
| 0 | Contact opens. CHAIN_END, K1_RUN, RUN_HD and RUN_12V lose their source. K2/K3 coil currents commutate into their clamps (20 V Zener + diode, across each coil); K1's into its 24 V clamp. |
| ≤ 1 | VMOT eFuse enable falls (RUN_HD, 0.1 ms RC); U_HOLD, U_LS LEDs off. |
| ≤ 2.2 | U9 forces nSLEEP low (own RUN_HD tap); bridges asleep (tSLEEP 1 ms [D]). |
| ≤ 4 | K1 released [U]. |
| ≤ 7.8 | K2, K3 NO contacts open (5 ms bare-coil release [D] × 1.56 for the 20 V clamp [A]). |
| ≤ 10.8 | NC contacts closed and settled [A]: brake resistor connected. 2.2 mm travelled at 0.20 m/s. |

The NO contacts normally break no current, because the bridges are asleep first.

**Minimum opening that is guaranteed to drop the latch (review m4):** U_HOLD's LED loses its current as soon as RUN_HD dies, so U_HOLD opens after its turn-off time (assumed ≤ 1 ms [U]) even if K1 would ride through a short dip; once U_HOLD is off, only REARM sets it again. An opening of ≥ 2 ms is therefore taken to drop the latch [A]; shorter dips may not. Firmware also turns any fall of HW_LATCH_RB into a full drop (`rrch_chain_step`, drop_ms; ARM_PERMIT held low ≥ 50 ms in `rrch_tick_1khz`). Bench step 8 adds a pulse-width test.

## 4. Braking calculation

Model [C] (script `chassis_braking.py`, table T1): each motor is a back-EMF source of 31.7 V per m/s behind 2.18 Ω (cold). Shorted through 1.0 Ω plus 0.04 Ω, both motors give 343 N per m/s (conservative) to 624 N per m/s (nominal); time constant 46–132 ms. Brake current peaks at 1.97 A from 0.20 m/s and 4.3 A from the 14.4 V runaway speed of 0.44 m/s; resistor energy below 0.7 J per stop.

| Case | 0.20 m/s | 0.10 m/s | 0.05 m/s |
|---|---:|---:|---:|
| Both motors braked, nominal | 8.8 mm | 3.8 mm | 1.6 mm |
| Both motors braked, conservative | 28.6 mm | 14.3 mm | 7.1 mm |
| Conservative, windings at 100 °C (T9) | 34.2 mm | | |
| Conservative, 100 °C windings and ferrite magnet derating [A] (T9) | 47.5 mm | | |
| One motor braked, the other coasting without friction (robot yaws) | 55 mm | 27 mm | 14 mm |
| No dynamic braking at all, nominal friction (16 N) | 38 mm | 10 mm | 3 mm |
| No dynamic braking, half friction, high inertia | 114 mm | 29 mm | 8 mm |
| MCU failure with full torque until the watchdog acts | 57 mm | 39 mm | 30 mm |

**Slopes (T8, review o3).** Dynamic braking gives no holding force; the conservative model has no friction, so on its own it never stops on any incline. With the assumed friction (rolling 3.5 N + gearboxes 12.7 N, from the no-load current, not measured) the braked robot stops on downhill slopes up to about 6° (3° with half the friction) and otherwise creeps at 12–36 mm/s (6–10°). Trailer door ramps above about 3° are outside what the chain is calculated to hold until the holding angle is measured; no parking brake is fitted.

**Hot windings (T9).** R_M is the cold extrapolated 2.18 Ω; at 100 °C the loop is 21 % higher and the conservative distance 20 % longer; if the magnets are ferrite (−0.2 %/K [A]) the braking coefficient falls with the square of the flux and the distance grows by about two thirds. Repeat the spin-down test warm.

Why 1.0 Ω: a dead short would halve the time constant but allows 6.4 A from the runaway speed; 1.0 Ω keeps the worst loop current at 4.3 A.

## 5. Regeneration

The pack switch is bidirectional, so a pack that accepts charge absorbs regenerated energy (at most 0.9 J per stop from 0.20 m/s [C]). When the BMS has opened or refuses charge, a hardware clamp on VMOT holds the bus: comparator U33 on at 15.6 V, off at 15.0 V, switching **two 9.1 Ω 2512 resistors in parallel (4.55 Ω)** through Q40, behind the 1.1 A PTC F_CLAMP; 53 W peak against 34 W of worst-case regeneration [C]. Without it about 1 mF of bus capacitance would rise to about 45 V [C]. Details in T7 and `chassis_design_notes.md`.

## 6. Single-fault table

Every row is a statement about the netlist after stage 3. Columns: fault → effect → hardware detection or barrier → firmware detection ("implemented in `f()`" = read in `firmware/chassis/core` at commit 77507bc; "requested" = listed in `STAGE2_CHANGE_REQUESTS.md` Stage 3 F-items or the review, not implemented) → residual risk. **⚠** = dangerous (stop function degraded or lost) and not detected at once.

| # | Fault | Effect | Hardware detection / barrier | Firmware detection | Residual risk |
|---:|---|---|---|---|---|
| 1 | F_CHAIN open / tripped | chain dead | cannot arm | MODE_RUN element open (`rrch_chain_step` node decode) | none |
| 2 | F_CHAIN low-resistance | a chain short to ground is limited only by the 20 A main fuse | none | none | **⚠ latent**, fire risk with a second fault |
| 3 | Selector RUN contact welded / wiring short | MODE_RUN lost; SERVICE no longer opens the chain | other elements remain | none (no SERVICE readback; host op_mode caps are unrelated) | **⚠ latent**; OFF still removes all power |
| 4 | Selector RUN contact open | cannot arm | — | MODE_RUN open | none |
| 5 | Selector EN contact shorted | OFF does not switch the pack off | operator sees the robot alive | none | traction still needs RUN + REARM |
| 6 | E-stop pole A closed (weld, pins 1–2 shorted) | pole A lost | pole B drops K1, K2, K3; VMOT/nSLEEP follow K1 (≤ 4 ms) | ESTOP_DISCREPANCY at the next press (`rrch_chain_step`) | detected at actuation |
| 7 | E-stop pole B closed / COIL_RTN shorted to ground | pole B lost | pole A remains | ESTOP_DISCREPANCY (`rrch_chain_step`) | detected at actuation |
| 8 | Chain harness or board node CH_N1…CH_N9 shorted to +12 V | elements upstream of the short bypassed | elements downstream remain | CHAIN_IMPLAUSIBLE (node live behind a dead node) when an upstream element is actuated (`rrch_chain_step`) | **⚠ latent** until actuation |
| 9 | HANDS-ON contact welded, wiring short, or lamp-to-contact short in W-017 (m9) | HANDS-ON lost | lamp does not light | HANDS_ON_RB stays high when pressed (element state, `rrch_chain_step`) | **⚠** until next use; never rely on an unlit lamp |
| 10 | Q25 or HANDS_ON tap open | lamp lit whenever dropped | — | none | **⚠** indicator untruthful until the daily check |
| 11 | Q26, Q27, lamp, lamp wiring open | lamp never lights | visible | — | none (dark = not confirmed) |
| 12 | Cover switch closed | cover channel lost | plug link + inlet detection (U20) remain | CHARGER cause if the charger reports input (`rrch_chain_step`) | none while U20 works |
| 13 | Plug-link wiring open | link channel lost | cover + inlet detection remain | none | **⚠ latent** |
| 14 | Q20 D-S short or U20 output short | U20 always closed | cover switch remains | CHG_PLUG_LINK_RB high while the charger reports input (`rrch_chain_step` CHARGER cause) | detected at the next charge |
| 15 | Q21 / inlet divider open | inlet channel lost | link + cover remain | none | **⚠ latent** |
| 16 | **Loop channel A always closed**: U30A cannot sink, U30 pin 1 open, U30 pin 7–8 bridge, R74 short, HEAD_LOOP_OK_RB to 3V3/V5_AUX, R72 short (lower threshold 0 V), Q22 D-S short, U21 output short | channel A lost | **channel B (U46, Q_LB, U21B) still opens the chain on a pressed rail or open J1** | while latched, the analog copy (PC1) reading open withdraws ARM_PERMIT and a comparator/ADC disagreement > 5 ms is LOOP_FAIL (`rrch_chain_step`); GPA5 vs HEAD_LOOP2_OK_RB disagreement: requested (F6) | detected at the next rail press; one channel remains meanwhile |
| 17 | **Loop channel B always closed**: U46 output stuck high, Q_LB short, U21B output short, R_LB3 open, LOOP_FB to a supply | channel B lost | channel A remains | GPA5 vs HEAD_LOOP2_OK_RB: requested (F6), not implemented | **⚠ latent** until F6 exists (channel A still acts) |
| 18 | Shared loop path: R65 open/short, R68 open/short, R66/R67 open, D10 short | reads open or short | both channels open (out of window / below 2.7 kΩ), immediately | LOOP state (`rrch_chain_step`) | none |
| 19 | LOOP_SNS (shared sense node) with a resistive leakage of about 1.2–3 kΩ to V5_AUX or 3V3 | an open loop reads healthy to **both** channels and the ADC | none | none | **⚠ no barrier** for the head rail (§6.1); improbable (needs a kΩ-level leak); LOOP_SNS kept short and away from supply copper |
| 20 | Loop pair shorted (cable, J1, head connector) | rail switches bypassed | channel A short detection (U30B) opens | HEAD_LOOP_SHORT_RB (U32A) and the ADC copy withdraw ARM_PERMIT (`rrch_chain_step`) | none |
| 21 | U30B or U32A stuck "no short" | short detection degraded | U32A / U30B / ADC remain | ADC copy (`rrch_chain_step`) | latent; needs a pair short as second fault |
| 22 | Head-side bypass of the rail switches but not of the 1.00 kΩ | rail switches bypassed, loop reads healthy | none at the chassis | none | **⚠ no barrier** (§6.1); head design: resistor at the far end of the switch string; pre-use rail press |
| 23 | One rail switch welded | that rail zone lost | none | none | **⚠ no barrier** for that zone (§6.1); pre-use rail press |
| 24 | LAB_KEY_N always closed: U31 cannot sink, U31 pin 7–8 bridge, R82 short, Q28 short, U22 output short | LAB_KEY_N lost | HEAD_DOCK is open whenever the head is off the robot (LAB) | PRES_ID decode raises LAB_KEY (`rrch_chain_step`); LAB mode withholds ARM_PERMIT (`rrch_tick_1khz`) | needs two more faults to move in LAB |
| 25 | R77 / VREF drift or open | outside the window | U22 opens | PRES fault (`rrch_chain_step`) | none |
| 26 | Dock switch closed | HEAD_DOCK lost | HEAD_LOOP (J1 unplugged) and LAB_KEY_N remain | dock vs presence cross-check: requested, not implemented | detected at the next head removal only by inspection |
| 27 | Body bumper switch L or R welded, or its wiring shorted | that bumper lost | none (single contact per side) | none | **⚠ no barrier** for that side (§6.1); pre-use bumper press |
| 28 | Chain harness wire open | chain open | — | first dead node | none |
| 29 | Chain harness wire short to chassis/ground | F_CHAIN trips, chain dead | — | CH_N1 low | none |
| 30 | Readback tap open or short | wrong readback | chain unaffected | CHAIN_IMPLAUSIBLE / element plausibility (`rrch_chain_step`) | none for the chain |
| 31 | IOX_A stuck or SPI fault | wrong readbacks | — | sentinel GPB7 / IOX_A fault, fatal within 5 ms (`rrch_chain_step`) | none |
| 32 | IOX_A GPA5/GPA7/GPB7/GPB2, STM32 PB12/PD2/PC13 configured as outputs (firmware defect, SPI corruption) | cannot hold an element closed any more (47 kΩ isolation, U9 own tap, D_RB) | by design (stage 3) | PIN_CONFIG (`rrch_chain_step`, from the port's `io_cfg_ok`) | none |
| 33 | U40 WDO stuck high, Q23 D-S short, U23 output short | WDG_OK element lost | U24 (firmware) remains | boot test "withhold strobe, WDG_OK_RB must fall": requested (IB-60), not implemented | **⚠ latent for the life of the board**; a hung MCU then needs a second fault to keep moving (#35) |
| 34 | U40 WDO stuck low | chain open | — | WDG_OK_RB | none |
| 35 | MCU hangs with ARM_PERMIT high and PWM running | bridges drive until the watchdog opens the chain (≤ 43.4 ms, 57 mm from 0.20 m/s) | external watchdog | MCU IWDG: configured in the port (`bsp.c`, seen, not reviewed here) | the 57 mm case |
| 36 | PB10 / Q24 / U24 stuck closed | ARM_PERMIT element lost | U23 opens when the strobe stops | PERMIT_STUCK_ON (`chain_end_step`) stops the strobe (`rrch_supervise_100hz`). With D_RSET the rev-A back-feed window (`CHAIN_BACKFEED_MS`) is no longer needed: request to set it to 0 | detected within about 30 ms |
| 37 | **K1 pole A (seal-in) welded** | K1 re-energises whenever the chain re-closes | **U_HOLD stays off: RUN_HD/RUN_12V dead, no restart without REARM** | LATCH_NC_RB low with the latch down (F2) and LATCH_RUN_RB high without a set (F3): requested, not implemented. HW_LATCH_RB does not rise, so the existing LATCH_NO_REARM cannot see it | hold reduced to U_HOLD alone until F2/F3 exist |
| 38 | **K1 pole B welded** | K1_RUN follows CHAIN_END | **U_HOLD stays off: no restart** | LATCH_RUN_RB high without a set (F3), boot check with ARM_PERMIT raised before REARM (F3): requested | as #37 |
| 39 | U_HOLD output shorted, or Q_HSET D-S short (U_HOLD LED always lit) | hold reduced to K1 alone | none | none possible directly; with a later K1 weld, LATCH_NO_REARM (latch rise without a REARM edge, `rrch_chain_step`) | **⚠ latent**; needs K1 weld as second fault, then firmware only |
| 40 | U_HOLD open or LED open; R_HA open | cannot arm | — | no HW_LATCH after REARM | none |
| 41 | K1 coil open, contacts open, D_SEAL open | cannot arm / cannot stay armed | — | no HW_LATCH after REARM | none |
| 42 | **V12_AUX, LAMP_REARM_K, BTN_3V3 or REARM_SET_SRC shorted to REARM_SET_RAW (W-018)**, or set contact welded | one edge on the set line, aux contact not pressed | **set stage needs the aux contact level at the same time: no set** | REARM_SET_RB vs REARM_BTN discrepancy (F5): requested | none; later REARM presses give no edge (cannot arm until repaired) |
| 43 | Aux contact bridged in W-018 (pins 3–4, or V12_AUX/BTN_3V3 to REARM_BTN_RAW) | aux level permanently true | set still needs a set-contact edge | REARM_HELD after 2 s (`rrch_chain_step`) blocks ARM_PERMIT (`rrch_rearm_blocked`) | cannot arm (permit held low) |
| 44 | Multi-conductor crush of W-018 putting a supply on REARM_SET_RAW and REARM_BTN_RAW at once | looks like a REARM press: the latch can set once (chain closed, C_SET charged) | every element still drops it | indistinguishable from a press | **⚠** one unintended arming (§6.1) |
| 45 | Q_SETA D-S short or C_SC short | edge requirement lost: the aux contact alone sets | aux contact press still needed | none | **⚠ latent**; a W-018 aux short then sets once (two faults) |
| 46 | Q_SETB D-S short | aux requirement lost: a set-line edge alone sets | set-contact edge still needed | LATCH_NO_REARM if the latch rises without a REARM_BTN edge (`rrch_chain_step`) | latent; a W-018 set-line short then sets once and firmware faults |
| 47 | U_SET output short, Q_SETA+Q_SETB stuck on, Q_SDIS short, Q_SDISB open, D_RSET open | C_SET cannot charge | cannot arm | — | none |
| 48 | R_SET short | C_SET charges fast; with a held REARM U_SET is still on for only ~110 ms after the edge | cannot hold | — | none |
| 49 | Q_SDIS open, Q_SDISB short, R_SDIS open | C_SET not emptied after a drop: REARM pressed during an opening can set if the chain closes within the 110 ms pulse (m3) | — | REARM edge accepted only with every element closed and ARM_PERMIT high, else ARM_PERMIT held low 300 ms (`rrch_chain_step`) | **⚠ latent**, covered by firmware |
| 50 | D_RSET short | back-feed of M1 returns (readbacks wrong for seconds after a drop) | — | back-feed window handling (`chain_end_step`, `CHAIN_BACKFEED_MS`) if left configured | no motion effect |
| 51 | **RUN_12V shorted to a supply (board or harness)** | K2/K3 coils have a supply | **U_LS (lit only from RUN_HD) keeps the relays released; VMOT and nSLEEP come from RUN_HD; D_RUN blocks back-feed** | LATCH_NO_REARM on the HW_LATCH_RB rise (`rrch_chain_step`); HW_LATCH_RB high with LATCH_RUN_RB low (F4): requested | none while U_LS and D_RUN are healthy |
| 52 | D_RUN short | RUN_12V can back-feed RUN_HD | — | none | **⚠ latent**; needs #51 as second fault |
| 53 | U_LS output short | relay return unconditional | K1 + U_HOLD still switch the supply | none | **⚠ latent**; needs #51 as second fault |
| 54 | D_RUN open, U_LS open | relays never pick up | cannot drive | bridges stay asleep until both relays read connected; mismatch → VMOT_FAULT (`rrch_chain_step`) | none |
| 55 | **RUN_HD shorted to a supply (board)** | U_LS lit, VMOT enabled, nSLEEP gate enabled, relays energised | E-stop pole B only | LATCH_NO_REARM (`rrch_chain_step`) → FAULT, DRV_NSLEEP low | **⚠ no hardware barrier except pole B** (§6.1); 1.0 mm DRC rule to supplies |
| 56 | **K1_RUN or CHAIN_END shorted to a supply (board)** | before a REARM nothing (U_HOLD off); after the next REARM U_HOLD self-holds through the short and every element is bypassed | E-stop pole B only after REARM | CHAIN_END: CHAIN_IMPLAUSIBLE (`chain_end_step`); K1_RUN: LATCH_RUN_RB high without a set (F3, requested) → FAULT, DRV_NSLEEP low | **⚠ no hardware barrier except pole B** after REARM (§6.1) |
| 57 | K1_COIL_P, K1_SEAL_A, K1_SET or SET_CAP shorted to a supply | K1 held / C_SET charged | U_HOLD still needs REARM and drops with any opening | as #37 | none (as a K1 weld) |
| 58 | K2 or K3 one NO contact welded | that wheel has no brake path and stays on the bridge | VMOT removal and nSLEEP | BRAKE_x_RB stays high after the drop → VMOT_FAULT (`rrch_chain_step`), BRAKE_TEST relay step (`bt_step`) | one unbraked stop |
| 59 | K2 or K3 both NO welded / armature stuck | motor stays on the bridge, no dynamic brake on that wheel | VMOT removal (U8) and nSLEEP (U9) | as #58 | as #58 |
| 60 | K2/K3 NC contact high-resistance / open, brake resistor open, brake path open | relay isolates but that motor is not braked | none at standstill | dynamic deceleration check after a drop: requested, not implemented | **⚠ undetected**; one wheel coasts (55 mm) |
| 61 | Brake resistor or winding degraded high but not open; hot winding | longer stop (T9) | none | none | **⚠ undetected**; up to +66 % distance |
| 62 | K2/K3 coil open | no drive on that wheel | — | relays_ok never true (`rrch_chain_step`) | none |
| 63 | K2/K3 clamp Zener short | release ≈ 3× slower (15–20 ms) | none | BRAKE_TEST latch/relay timing only if beyond its limit (`bt_step`) | **⚠ latent**; +2–3 mm |
| 64 | K2/K3 clamp open | coil kick of hundreds of volts on RELAY_RTN/RUN_12V: D_RUN (60 V), U_LS (40 V [U]) may fail short (#52, #53) | none | none | **⚠ latent** |
| 65 | K1 clamp open | K1_COIL_P kick: D_SEAL (30 V) or U_SET (40 V) may fail short (U_SET short = cannot arm) | none | none | **⚠ latent** (D_SEAL short has no safety effect) |
| 66 | U8 FET short / enable stuck | VMOT stays after a drop | brake relays + nSLEEP | VMOT not below threshold within `brake.vmot_decay_max_ms` → VMOT_FAULT (`rrch_chain_step`, `bt_step`) | none |
| 67 | VMOT bleed open | slow decay | — | as #66 | none |
| 68 | U9 output stuck high | bridges awake without the latch | VMOT absent and motors disconnected | none | **⚠ latent** loss of one of three drop paths |
| 69 | DRV8874 output FET short | uncommanded current while armed | relays disconnect on a drop | nFAULT, IPROPI, encoder (firmware, not reviewed here) | the chain does not detect it |
| 70 | 3V3 or V5_AUX lost | all photo-MOS LEDs off | chain open | — | none |
| 71 | 3V3 over-voltage (buck failure) | MCU, expanders, watchdog damaged in unknown ways | contact elements remain | — | **⚠** common cause of all electronic elements |
| 72 | Pack / BMS / main fuse opens while moving | all coils drop | brake resistors need no power | — | same as a contact element |
| 73 | Drive-loop error with supervision alive (wrong speed, too much torque) | robot faster or pushing harder than commanded | **no hardware speed or force limit** (no-load 0.44 m/s at 14.4 V; 93–170 N at stall) | firmware speed caps only | contact elements remain (o2) |

### 6.1 Single faults that leave no hardware barrier

After stage 3 these single faults leave the robot able to move into a person with no remaining hardware barrier for the zone concerned:

1. **A welded head-rail switch** (that rail zone), or a **head-internal bypass** of the switch string that leaves the 1.00 kΩ in circuit (#22, #23). Not detectable at the chassis; the pre-use rail press is the only check.
2. **A welded or shorted body bumper switch** or its wiring, left or right (#27): single contact per side. Rear and quarter contact then rests on the firmware rear ToF. A second, diverse channel needs a two-contact bumper switch and a 3-way cable (proposal for rev C; harness and mechanical change, not made).
3. **A kΩ-level leakage from the shared loop sense node LOOP_SNS to a 3.3/5 V supply** (#19): both loop channels share the sense resistor pair. Improbable; a third, fully separate loop source would need a second J1 pair (contract change).
4. **A board short of RUN_HD, K1_RUN or CHAIN_END to a supply** (#55, #56): only E-stop pole B remains (RUN_HD at once; K1_RUN and CHAIN_END after the next REARM), plus firmware DRV_NSLEEP. These are short copper nodes on the board; DRC enforces 1.0 mm to every supply net (`placement.chain_rules()`), and the test points are spaced ≥ 10 mm.
5. **A multi-conductor crush of W-018** that puts a supply on both REARM contact lines at once (#44): it can arm the robot once as a REARM press would; every element still drops it.

Faults that the review listed here and that now have a hardware barrier: welded K1 (U_HOLD), V12_AUX or lamp short onto the REARM set line (two-contact edge-triggered set stage, coil node on the board), every single fault in the U30/R74/Q22/U21 loop channel (channel B), a board short of RUN_12V to a supply (U_LS, D_RUN), expander/MCU pins driving the U21/U22/U9 gate nodes (series isolation).

The stated limits remain: no hardware speed or force limit (#73), no holding brake on slopes (T8), latent faults that need periodic checks (#3, #13, #15, #17 without F6, #33, #39, #45, #49, #52, #53, #60, #63–#65, #68), and the common-cause 3V3 over-voltage (#71).

## 7. Stationary brake self-test (BRAKE_TEST): what it can and cannot show

Sequence as implemented in `bt_step` (`rrch_core.c`), plus the steps requested for stage 3:

1. Preconditions (implemented): latch set, both relays read connected, VMOT present.
2. ARM_PERMIT low (implemented): HW_LATCH_RB must fall within `brake.latch_drop_max_ms`, BRAKE_L_RB and BRAKE_R_RB must fall, VMOT_SENSE below `brake.vmot_off_v` within `brake.vmot_decay_max_ms` (≥ 3.5 s required: worst case 2.65 s to 1 V, T10).
3. Probe (implemented): bridges awake at a small duty with the latch down; the motor current must stay below `brake.probe_i_max` (relays isolate the motors).
4. **Requested (F2, F3):** with the latch down, LATCH_NC_RB must read high (K1 pole A released); raise ARM_PERMIT again with all elements closed and **no REARM**: LATCH_RUN_RB and HW_LATCH_RB must stay low for ≥ 100 ms (K1 not welded on either pole). This also is the boot check ("K1 not welded at boot"), which was not implementable on the stage-1 circuit.
5. **Requested (IB-60):** boot only, with JP1 open or with the reset path accounted for: withhold the strobe, WDG_OK_RB must fall within 35 ms.
6. Operator presses REARM to arm for the mission (needs the chain closed for about 1–2 s first, §2.1).

| Shown by the stationary test | Not shown |
|---|---|
| Each brake relay's NO contacts open on both poles when released (#58, #59) | That the NC contacts and the brake resistor conduct (#60) |
| Each relay picks up (#62) | Brake force, stopping distance, slope holding |
| VMOT appears with the latch and disappears without it (#66, #67) | Release times (only a gross limit) |
| With step 4: K1 not welded (#37, #38) | U_HOLD shorted (#39), U_LS / D_RUN shorted (#52, #53) |
| With step 5: watchdog element opens (#33) | Contact elements: only actuating each one shows it opens (pre-use check) |
| Readback paths toggle | Clamp components (#63–#65), nSLEEP gate (#68) |

Dynamic check recommended in addition (firmware, requested): on the first drop from ≥ 0.05 m/s of each mission, compare the encoder deceleration with the braked model; a time constant more than twice the calibrated value on either wheel raises BRAKE_TEST_FAIL.

## 8. First power-up procedure for the chain (bench, wheels off the ground, current-limited supply)

Record every reading. Stop at the first deviation.

1. **Unpowered continuity.** No pack. With all field devices connected and in their run state: each switch loop < 1 Ω; CH_N0 to ground > 30 kΩ; COIL_RTN to ground < 1 Ω with the E-stop released and open with it pressed. K2/K3: motor terminal A to B ≈ 0.7 Ω (1.0 Ω ∥ winding); motor terminals to bridge outputs open.
2. **Logic rails only.** 12.0 V, 0.5 A limit, selector SERVICE. Expect 3V3, V5_AUX, VREF 3.000 V; CH_N1 = 0 V; all readbacks low; LATCH_NC_RB high; VMOT 0 V. Selector RUN: operate each device in turn and note the node that falls and the readback bit.
3. **HEAD_LOOP windows.** Decade box on J1 pins 5–6: U21 (channel A) on between 0.59 and 1.55 kΩ (±5 %), off at 0 Ω, open, and either pin to ground or 12 V through 1 kΩ. U21B (channel B) on below 2.70 kΩ (±5 %), off above and open. Then disable each channel in turn (lift U30 pin 1; then lift U46 pin 1 with U30 restored) and confirm the other alone opens the chain at 3 kΩ and open. Log HEAD_LOOP_SENSE at 0.6, 1.0, 1.6 kΩ (expect 1.79, 1.56, 1.32 V).
4. **PRES_ID window.** Decade box on J1 pins 7–2: U22 on between 3.92 and 5.64 kΩ only; 1.137 kΩ, 1.50 kΩ, open and short give off.
5. **Plug link / inlet.** Link J_PWR 4–8: CH_N4 falls. Remove the link, 24 V on the inlet pins through 1 kΩ: CH_N4 falls.
6. **Watchdog and permit** (test firmware): no strobe → CH_N9 low; a falling edge every 10 ms → high; falling edges every 1 ms and every 40 ms → low. ARM_PERMIT low/high → CHAIN_END follows. MCU held in reset: CHAIN_END low. Drive IOX_A GPB7 as an output with PB11 high-impedance: WDI must stay below 1 V.
7. **Latch and set stage.** All elements closed for ≥ 3 s. Press REARM: K1, U_HOLD, U_LS, K2, K3 pick up; RUN_12V = supply − < 0.8 V; chain current 85–110 mA. Then each of these must **not** set the latch (all elements closed, C_SET charged): (a) apply V12_AUX to J_BTN pin 2 (set line) without the aux contact; (b) bridge J_BTN 3–4 (aux) permanently and cycle an element; (c) apply LAMP_REARM_K to J_BTN pin 2 with the REARM lamp blinking; (d) short J_BTN 1–2 permanently and cycle an element; (e) press REARM while an element is open, close the element within 0.1 s. Firmware must fault within 0.2 s where it sees a latch rise. (f) Hold REARM and open any element: everything drops and does not return while held.
8. **Each element drops the latch.** Arm; open each element in turn (each E-stop pole alone by lifting one wire); re-arm between. Scope RUN_HD, RUN_12V and a brake-relay NC contact: time to NC closure ≤ 10.8 ms (≤ 13.3 ms for the loop channels and PRES_ID). Pulse-width test (m4): open ARM_PERMIT for 0.5, 1, 2, 5 ms; record the shortest that drops the latch (expect ≤ 2 ms [A]).
9. **Weld simulation.** Arm, drop, then bridge K1 pins 9–8 (pole B) with a wire: re-close the chain without REARM: RUN_HD and RUN_12V must stay dead, LATCH_RUN_RB high. Repeat with pins 4–5 (pole A): K1 picks up, RUN_HD stays dead, LATCH_NC_RB low. Remove the wire.
10. **RUN_12V short simulation.** Latch dropped: connect RUN_12V (TP39) to VBAT_SW through 10 Ω: K2/K3 must stay released (BRAKE_x_RB low), VMOT 0 V. Remove.
11. **VMOT.** Current limit 3 A. Arm: VMOT rises in 2–5 ms; drop: eFuse off within 1.5 ms, VMOT < 1 V within 3 s.
12. **Brake readback.** Dropped: BRAKE_x_RB low. Jumper one bridge output to its motor terminal (simulated weld): high. Remove.
13. **Braking.** Motors fitted, wheels free. Run each wheel at the 0.20 m/s equivalent, open the E-stop: record the encoder spin-down with the brake resistor fitted and, once, lifted (coast). Repeat with the motors warm. The time constants replace the inertia and friction assumptions of §4.
14. **Bus clamp.** Pack disconnected, bench supply with a series diode; back-drive a wheel: VMOT must not exceed 16.0 V; BUS_CLAMP_ACTIVE pulses.
15. Only then: on the floor, restrained, VT-003/004 stopping-distance trials at 0.05, 0.10, 0.20 m/s for every initiating element, and a holding test on the steepest ramp in the operating envelope.
