# RR-CHS-MAIN hardwired traction chain: circuit, timing, single faults, braking

Owner: chassis electronics. Evidence class: `calculated`. Nothing here is measured.
Tags: **[D]** datasheet value, **[C]** calculated (`electronics/analysis/chassis_braking.py`, tables in `chassis_braking_tables.md`), **[A]** assumed, **[U]** UNVERIFIED.

**This is not a certified safety system.** It is a single-channel relay chain with diagnostics built from standard (not force-guided) relays, photo-MOS relays, comparators and one microcontroller. It has no performance level, no category and no SIL, and it must never be described as a safety function. Section 6 lists the single faults that defeat part of it without being detected.

Net and reference names are those of `electronics/chassis_main/design/circuit.py`.

## 1. Headline numbers

| Quantity | Value | Tag |
|---|---|---|
| Chain element opens → brake resistors connected (contact elements; also total power loss) | ≤ 10.5 ms | [D]+[A] |
| Same, HEAD_LOOP / LAB_KEY (comparator + photo-MOS) | ≤ 13.0 ms | [D]+[A]+[U] |
| Same, firmware withdraws ARM_PERMIT | ≤ 13.5 ms | [A] |
| Same, MCU stops (external window watchdog) | ≤ 43.1 ms after the last valid strobe | [D]+[A] |
| VMOT eFuse off / bridges asleep after a contact element opens | ≤ 5.0 ms | [U] K1 release time |
| Brake resistor (per motor, across the relay's NC contacts) | **1.0 Ω**, 2512, 2 W pulse-rated; brake loop 3.22 Ω including the 2.18 Ω winding | design value |
| Stopping distance from 0.20 m/s (nominal / conservative) | 8.7 / 28.5 mm | [C] |
| Stopping distance from 0.10 m/s | 3.8 / 14.3 mm | [C] |
| Stopping distance from 0.05 m/s | 1.5 / 7.1 mm | [C] |
| Worst calculated case: MCU fails with full drive torque applied, from 0.20 m/s | 56 mm | [C], conservative |

The firmware simulation's 14.8 mm from 0.20 m/s lies between the two figures; to align it use R_brake = 1.0 Ω, R_motor = 2.18 Ω, 31.7 V per m/s per motor, friction 16 N total and a reflected rotor inertia of 8.3 kg per motor (nominal case), with 10.5 ms of dead time before the brake engages.

The "conservative" column assumes the lower force constant (17.4 N/A, from the catalogue stall torque), a rotor inertia of 2 × 10⁻⁶ kg m² per motor and **no friction at all**; "nominal" uses the power-balance constant (31.7 N/A), 1 × 10⁻⁶ kg m² and the friction implied by the 0.2 A no-load current. The rotor inertia is not published by Pololu and dominates the result (two reflected rotors are 8–33 kg against a 12 kg robot). A wheel-up spin-down test closes it.

For comparison the contract stop model with its example inputs (0.15 s, 0.40 m/s², 20 mm) gives 100 mm at 0.20 m/s; the hardware chain is calculated to be well inside it. The head rail's lead over the entrance film (7.4–11 mm, design text §4) is **not** covered at 0.20 m/s by the conservative figure and is marginal at 0.10 m/s: the mechanical lead needs ≥ 15 mm of rail over-travel at 0.10 m/s, or the approach speed near obstacles stays at 0.05 m/s, until the spin-down test is done.

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
  CH_N5  ─[ U21 photo-MOS: J1 loop 0.59–1.55 kΩ ]───────────────────────── CH_N6   HEAD_LOOP
  CH_N6  ─[ U22 photo-MOS: PRES_ID 3.92–5.64 kΩ (head, no LAB resistor) ]─ CH_N7   LAB_KEY_N
  CH_N7  ─[ J_BUMP_L 1-2 ]─ CH_N8A ─[ J_BUMP_R 1-2 ]────────────────────── CH_N8   BODY_BUMPER
  CH_N8  ─[ U23 photo-MOS: external window watchdog satisfied ]──────────── CH_N9   WDG_OK
  CH_N9  ─[ U24 photo-MOS: MCU ARM_PERMIT high ]────────────────────────── CHAIN_END  ARM_PERMIT

CHAIN_END ─ D_SEAL ─[ K1 pole A, NO: seal-in ]─ K1_COIL_P ─ K1 coil ─ COIL_RTN
CHAIN_END ─ R_SET 22 kΩ ─ SET_CAP (C_SET 100 µF) ─[ J_BTN 1-2: REARM, momentary NO ]─ K1_COIL_P
CHAIN_END ─[ K1 pole B, NO ]─ RUN_12V ─ K2 coil ─ COIL_RTN        (left brake relay)
                              RUN_12V ─ K3 coil ─ COIL_RTN        (right brake relay)
                              RUN_12V ─ divider ─ EN of the VMOT eFuse U8, HW_LATCH_RB, nSLEEP gate U9
COIL_RTN ─[ J_ESTOP 3-4: E-stop pole B, NC ]─ GND                                   ESTOP (low side)
```

The order is exactly the contract's `safety_chain.series_elements`. CHG_COVER is two series contacts (cover switch, plug-link element) and BODY_BUMPER is two (left, right), each with its own readback.

Design rules applied:

- **Coil current is the chain current.** K2 and K3 (the brake relays) take their coil supply from CHAIN_END. Opening any element removes it directly; they do not wait for K1 and they drop even if both K1 contacts are welded. About 80 mA flows through every element when latched (K1 11.7 mA + K2, K3 33.3 mA each [D]), which also wets the switch contacts. Before latching only the readback dividers load the chain (≈ 0.1 mA per node).
- **E-stop has two poles.** Pole A opens the high side of the chain; pole B opens the common return of all three coils. Either alone drops everything.
- **REARM can only set, never hold.** REARM discharges C_SET (charged from CHAIN_END through 22 kΩ) into the K1 coil: τ = 100 µF × 1028 Ω = 103 ms, coil above its 9 V must-operate level for ≥ 6.6 ms at 11 V with a hot coil against a 4 ms operate time [C]/[U]. A held or welded button passes 14.6 V × 1028/(22 000 + 1028) = 0.65 V to the coil, below the 1.2 V (10 %) must-release level [D], so it cannot hold or re-set the latch. Re-arming is locked out for about 5 s (recharge τ = 2.2 s) [C]. D_SEAL stops C_SET feeding the brake relays if REARM happens to be held when the chain opens.
- **No element is bridged by anything.** Readbacks are 100 kΩ taps to ground-referenced dividers; the HANDS-ON lamp is fed from the upstream node to ground, not across the contact.
- **Three independent consequences of a drop**: (1) K2/K3 release: each motor's two terminals leave the bridge (NO contacts) and are joined through a 1.0 Ω brake resistor (NC contacts); (2) the VMOT eFuse U8 loses its enable and VMOT is bled to zero through 1 kΩ; (3) the bridges' nSLEEP is forced low by U9 (AND of the MCU's DRV_NSLEEP and the latched state), independent of firmware. The MCU's TIM8 break input on HW_LATCH_RB is a fourth, firmware-configured, path.

### 2.2 Electronic elements

| Element | Sensing | Closed when | Fails open on |
|---|---|---|---|
| U20 plug link / inlet | Gate of Q20 is pulled up from V5_AUX; the plug link (J_PWR 4–8, linked in the charge plug) or Q21 (on when the inlet carries > ~10 V) pulls it low | no plug link **and** no inlet voltage | loss of V5_AUX, link wire shorted to ground |
| U21 HEAD_LOOP | V5_AUX → 1.00 kΩ → J1 pin 5 → head (3 NC rail switches + 1.00 kΩ) → J1 pin 6 → 1.00 kΩ to ground; 100 Ω in each line. The voltage on the lower 1.00 kΩ is compared with two taps of a divider on the same V5_AUX (ratiometric) by U30 (LM2903B, open-collector outputs wired-AND) | loop resistance 0.59–1.55 kΩ [C] (1.33–1.79 V on the sense resistor; healthy 1.56 V; short 2.27 V; open 0 V) | open loop, unplugged J1, shorted pair, either line shorted to ground or to +12 V, loss of V5_AUX |
| U22 LAB_KEY_N | VREF_3V0 → 4.70 kΩ 0.1 % → J1 pin 7; code resistor returns to J1 pin 2. Window comparator U31 against a divider on VREF_3V0 | PRES_ID resistance 3.92–5.64 kΩ [C] (1.364–1.636 V; head direct = 1.500 V) | no head (> 5.64 kΩ), LAB extension fitted (1.137 kΩ → 0.58 V), extension alone (1.50 kΩ → 0.73 V), short, loss of VREF or V5_AUX |
| U23 WDG_OK | TPS3430 window watchdog U40, presets CWD = NC, SET0 = 0, SET1 = 1: strobe must arrive 2.2–23.4 ms after the previous one [D]; firmware strobes every 10 ms. WDO (open drain, 200 ms assertion [D]) drives Q23 and, through a Schottky and solder jumper JP1 (normally closed, firmware request), the MCU's NRST. A watchdog fault also forces both heater enables off and lights the FAULT LED in hardware | watchdog satisfied | missing, early or late strobe; loss of 3V3 |
| U24 ARM_PERMIT | MCU PB10 with 4.7 kΩ pull-down drives Q24 | pin driven high | MCU in reset, unprogrammed, in the ROM bootloader; loss of 3V3 |

The J1 loop is potential-free **at the head** (it touches nothing but switch contacts and one resistor there). At the chassis it is sourced from V5_AUX through 1.00 kΩ and referenced to chassis ground: short-circuit current is 2.3 mA, a short to +12 V drives the sense node high and opens the chain, and both lines have 100 Ω + TVS + 1 ms RC. Galvanic isolation of the loop from chassis logic was rejected: it would need an isolated supply on the board and buys nothing while the head end floats. The chain itself is separated from the loop electronics by the photo-MOS U21.

The PRES_ID return shares J1 pin 2 with the head electronics current. With the head docked the return drop is about 30 mV at 1 A [C], shifting the 1.500 V reading by +15 mV against a ±136 mV window. The window tolerates 0.27 V of return drop.

### 2.3 Readbacks (nothing can back-drive the chain)

Every chain node CH_N1…CHAIN_END, RUN_12V and VMOT has a tap: 100 kΩ from the node, 56 kΩ to ground, 22 nF (τ ≈ 0.8 ms), Schottky clamp to 3V3, into an input of the MCU or of the SPI expander IOX_A (MCP23S17, V_IH = 0.8 VDD = 2.64 V [D]). The tap reads high for a node above 7.4 V and low below 1.8 V [C]. A fault that turns a readback pin into a 3.3 V output can push at most 33 µA into the chain, 35 times less than the smallest relay must-release current (1.17 mA for K1) [C].

A tap reads the **node**, i.e. "the chain is live up to and including this element". Firmware derives an element's state from the first dead node; an element downstream of an open one is reported as unknown, not as closed. E-stop pole B is read separately (P-MOSFET detector on COIL_RTN, high = pole closed).

| Readback | Source | MCU / expander pin |
|---|---|---|
| MODE_RUN_RB, HANDS_ON_RB, CHG_COVER_RB, CHG_PLUG_LINK_RB, HEAD_DOCK_RB | CH_N1, CH_N3, CH_N4A, CH_N4, CH_N5 | IOX_A GPA0–GPA4 |
| HEAD_LOOP_OK_RB, HEAD_LOOP_SHORT_RB, LAB_KEY_N_RB | comparator outputs as the pin map asks: U30 window (high = in window), U32A (high = loop below window, a third comparator diverse from U30), U31 window (high = head without LAB resistor). Nodes CH_N6 and CH_N7 behind the photo-MOS relays have test points only; their state is inferred from BODY_BUMPER_L_RB (CH_N8A) | IOX_A GPA5, GPA6, GPA7 |
| CHAIN_END_RB | CHAIN_END. No pin was allocated in the pin map; wired to IOX_B P17 (its spare), to be read as an input (change request CCR-E02) | IOX_B P17 |
| BODY_BUMPER_L_RB, BODY_BUMPER_R_RB | CH_N8A, CH_N8 | IOX_A GPB0, GPB1 |
| ESTOP_A_RB, ESTOP_B_RB | CH_N2; COIL_RTN detector | PB12, PB13 |
| WDG_OK_RB | CH_N9 | PC13 |
| HW_LATCH_RB | RUN_12V | PD2 (also TIM8 break) |
| VMOT_SENSE | VMOT, 47 k/10 k | PA2 (ADC) |
| BRAKE_L_RB, BRAKE_R_RB | see 2.4; high = motor connected to the bridge on at least one pole | PC14, PC15 |
| HEAD_LOOP_SENSE, HEAD_PRES_ID | analogue copies of the loop sense voltage and PRES_ID | PC1, PC0 (ADC) |
| REARM_BTN | second, separate contact of the REARM button | IOX_A GPB2 |

### 2.4 Brake relays and their readback

Per motor one Omron G2RL-2 (DPDT, 8 A, 12 V coil, 400 mW, release ≤ 5 ms [D]). Pole 1: common = motor terminal A, NO = bridge OUT1, NC = brake node A. Pole 2: common = motor terminal B, NO = bridge OUT2, NC = brake node B. The 1.0 Ω brake resistor joins brake nodes A and B. De-energised, the motor is disconnected from the bridge on both terminals and shorted through 1.0 Ω.

Because both poles carry motor current there is no spare contact. The state of the **power contacts themselves** is measured instead: motor terminal A is biased from 3V3 through a Schottky and 2.2 kΩ; each bridge output has a 4.7 kΩ pull-down; two comparators per motor (LM2903B) look at OUT1 and OUT2 with a 0.20 V threshold. With the bridges asleep:

- relay released and both NO contacts open: OUT1 = OUT2 = 0 V → the wired-AND comparator node `BRAKE_x_ISO` is high → `BRAKE_x_RB` (after the inverter Q41/Q42) is **low** = "both poles isolated from the bridge, motor on the brake branch";
- relay energised: OUT1 = OUT2 ≈ 1.5 V → `BRAKE_x_RB` high;
- relay released but one NO contact welded: that output sees the motor bias (≥ 0.4 V even with VMOT at zero and the bridge body diode conducting) → `BRAKE_x_RB` stays **high** → BRAKE_TEST_FAIL.

The polarity is the pin map's (high = motor connected to the bridge). The signal is an OR over the two poles, so low is only reported when both poles are positively measured as isolated. It is valid only while the bridges are asleep (during PWM the outputs toggle). Both levels are exercised on every arm/drop cycle, so a stuck readback path is found.

### 2.5 HANDS-ON indicator

The lamp in the HANDS-ON button is supplied from CH_N2 (the chain node upstream of the button) and switched to ground by Q27, which conducts only while CH_N3 (downstream of the button) **and** RUN_12V are both low (Q25, Q26 pull its gate down otherwise). Lit therefore means: upstream chain live, HANDS-ON contact open, latch dropped. No firmware is involved. If the E-stop is also pressed or the selector is not in RUN the lamp is dark (state not confirmed by this lamp).

### 2.6 What stays live with the selector in OFF

The selector's second contact opens the enable of the pack switch (LM74502 + back-to-back MOSFETs) and of all three regulators. In OFF: the pack coupler, harness, main fuse, J_PWR pins 1–2, the TVS, the MOSFET drains and the 100 kΩ enable feed to the selector are at pack voltage; everything else is dead, including the chain. A connected charger keeps its inlet, fuse and the charger IC's input side at 24 V; nothing is charged and nothing runs in OFF. **OFF is a functional switch-off through MOSFETs, not isolation.** Isolation for service is removal of the pack (blind-mate coupler) and of the charge plug.

## 3. Timing budget

See `chassis_braking_tables.md` T2 for every term. Summary of the contact-element case:

| t (ms) | Event |
|---:|---|
| 0 | Contact opens. K1, K2, K3 coil current commutates into the Zener clamps (24 V + diode per coil). |
| ≤ 4 | K1 released [U]: RUN_12V is disconnected; VMOT eFuse enable falls (0.1 ms RC). |
| ≤ 5 | VMOT eFuse off; bridges asleep (tSLEEP 1 ms [D]). Residual winding current decays through the bridge body diodes in about 1 ms. |
| ≤ 7.5 | K2, K3 NO contacts open (5 ms bare-coil release [D] × 1.5 for the clamp [A]). |
| ≤ 10.5 | NC contacts closed and settled [A]: brake resistor connected. Robot has travelled 2.1 mm at 0.20 m/s. |

The NO contacts normally break no current, because the bridge is asleep first; if K1 is slow they break at most the 2.68 A bridge current limit at ≤ 14.6 V, inside the contact rating.

## 4. Braking calculation

Model [C] (script `chassis_braking.py`, table T1): each motor is a back-EMF source of 31.7 V per m/s of ground speed behind 2.18 Ω (12 V / 5.5 A). The motor-level constant is 869 rpm/V (10 050 rpm at 11.56 V). With the motor shorted through 1.0 Ω plus 0.04 Ω of contacts and leads, both motors together give a braking force of 343 N per m/s (conservative constant) to 624 N per m/s (power-balance constant); the speed decays exponentially with a time constant of 46–132 ms depending on the rotor inertia assumed. Brake current peaks at 1.97 A from 0.20 m/s and 4.3 A from the 14.4 V runaway speed of 0.44 m/s; resistor energy is below 0.7 J per stop.

Stopping distances after the initiating event (level floor) are in table T3 of `chassis_braking_tables.md`; degraded cases in T4:

| Case | 0.20 m/s | 0.10 m/s | 0.05 m/s |
|---|---:|---:|---:|
| Both motors braked, nominal | 8.7 mm | 3.8 mm | 1.5 mm |
| Both motors braked, conservative | 28.5 mm | 14.3 mm | 7.1 mm |
| One motor braked, the other coasting without friction (robot yaws) | 55 mm | 27 mm | 14 mm |
| No dynamic braking at all, nominal friction (16 N) | 38 mm | 10 mm | 3 mm |
| No dynamic braking, half friction, high inertia | 114 mm | 29 mm | 8 mm |
| MCU failure with full torque until the watchdog acts | 56 mm | 39 mm | 30 mm |

Why 1.0 Ω: a dead short would halve the time constant but allows 6.4 A in the brake loop from the runaway speed; 1.0 Ω keeps the worst loop current at 4.3 A (inside the 8 A contacts and near the motor's stall rating) for a third more distance.

Dynamic braking gives no holding force. Gearbox friction (12.7 N [A], from the no-load current) holds the stationary robot up to about 6° (3° with half that friction) [C]; steeper, the unpowered robot creeps. No parking brake is fitted. The permitted slope must come from a measurement (design text §4: "select a power-off brake or limit the operating envelope").

## 5. Regeneration

The pack switch is bidirectional, so a pack that accepts charge absorbs regenerated energy (at most 0.9 J per stop from 0.20 m/s [C]; average regeneration is below the standing load). When the BMS has opened or refuses charge, a hardware clamp on VMOT (comparator on at 15.6 V, off at 15.0 V, 4.7 Ω, 52 W peak against 34 W of worst-case regeneration [C]) holds the bus; without it 1010 µF of bus capacitance would rise to about 45 V [C]. Details in `chassis_braking_tables.md` T7 and `chassis_design_notes.md`.

## 6. Single-fault table

Columns: failure mode → effect on the chain → detected by → residual risk. "Arm cycle" means the checks the firmware makes each time the latch is set or dropped; "BRAKE_TEST" is the stationary self-test of section 7. Dangerous = the stop function is degraded or lost. Undetected dangerous faults are marked **⚠**.

| # | Component | Failure mode | Effect | Detected by | Residual risk |
|---:|---|---|---|---|---|
| 1 | F_CHAIN chain PTC | open / tripped | chain dead, cannot arm | CH_N1 low with selector in RUN | none (safe) |
| 2 | F_CHAIN | fails low-resistance | none in normal use; a chain short to ground is then limited only by the 20 A main fuse and AWG 24 wire | not detected | fire risk only with a second fault (wire short) **⚠ latent** |
| 3 | Selector RUN contact | welded / shorted wiring | MODE_RUN element lost; SERVICE no longer inhibits traction through the chain | MODE_RUN_RB high while EN contact says not RUN is not observable (no SERVICE readback) | **⚠** undetected. SERVICE also keeps traction off only through this contact and firmware mode logic; OFF still removes all power |
| 4 | Selector RUN contact | open | cannot arm | CH_N1 low | none |
| 5 | Selector EN contact | shorted | OFF does not switch the pack off | operator sees the robot alive in OFF | traction still needs RUN + REARM; isolation is by pack removal |
| 6 | E-stop pole A | fails closed (weld, wiring short pins 1–2) | high-side pole lost; pole B still drops all coils | ESTOP_A_RB stays high with ESTOP_B_RB low at the next press (firmware A/B disagreement) | detected at next actuation; covered by pole B meanwhile |
| 7 | E-stop pole B | fails closed, or COIL_RTN wiring shorted to ground/chassis | low-side pole lost; pole A still opens the chain | ESTOP_B_RB stays high at the next press | as #6 |
| 8 | E-stop harness | pole A wire shorted to +12 V downstream (CH_N2 to VBAT) | bypasses MODE_RUN and E-stop pole A | MODE_RUN_RB / ESTOP_A_RB mismatch only when the selector leaves RUN or the E-stop is pressed | pole B still works; **⚠** latent until actuation |
| 9 | HANDS-ON button | contact welded / wiring short | HANDS-ON inhibit lost | lamp does not light and HANDS_ON_RB stays high when pressed (operator and firmware) | detected on use; the operator must not rely on an unlit lamp |
| 10 | HANDS-ON lamp circuit Q25 or its tap | open | lamp lit whenever the latch is dropped, button pressed or not | daily check: lamp must go out when the button is released | **⚠** indicator untruthful until the check; the chain is unaffected |
| 11 | Q26, Q27, lamp, lamp wiring | open | lamp never lights | visible | none (dark = not confirmed) |
| 12 | Cover switch | fails closed | cover channel lost | CHG_COVER_RB high with the charger connected (charger telemetry / link) | plug link and inlet-voltage channel remain |
| 13 | Plug link wiring | open | link channel lost | only when a de-energised charge cable is fitted (no inlet voltage to compare with) | **⚠** latent; cover switch and inlet-voltage detection remain |
| 14 | Q20 (U20 LED driver) | drain-source short | U20 permanently on: plug link and inlet-voltage channel both lost | CHG_PLUG_LINK_RB high while the charger reports input power | detected at the next charge; cover switch remains; firmware also blocks ARM_PERMIT in SERVICE_CHARGE |
| 15 | Q21 (inlet-voltage detect) | open / divider open | inlet-voltage channel lost | not detected | **⚠** latent; link and cover remain |
| 16 | U20, U21, U22, U23, U24 photo-MOS | output shorted (MOSFET failure) | that element permanently closed | the next read-back node stays high when the element's input condition is false (U21/U22: comparator output low while BODY_BUMPER_L_RB stays high): U23/U24 at every boot (firmware withholds strobe and permit in turn, see §7); U21 whenever a rail switch is pressed or the head removed; U22 whenever the head is removed or LAB is entered; U20 at every charge | U21/U22: **⚠** latent between head removals; the other chain elements are unaffected |
| 17 | same | LED open, output open | chain open | readback | none |
| 18 | U30 loop comparator A (open detection) | output stuck off (high-Z) | open loop no longer opens U21: head rail contact and unplugged J1 are not seen by the chain | firmware compares HEAD_LOOP_SENSE (ADC) and the third comparator HEAD_LOOP_SHORT_RB with HEAD_LOOP_OK_RB at 1 kHz and withdraws ARM_PERMIT on disagreement; proven at each pre-use rail press | **⚠** dangerous until the first disagreement; then stopped by firmware (second channel is software) |
| 19 | U30 comparator B (short detection) | output stuck off | a shorted loop pair is accepted | same ADC cross-check; only exercised with a shorting plug (commissioning) | **⚠** latent; needs a second fault (pair short) to matter |
| 20 | U30 | output stuck low | chain open | readback | none |
| 21 | Loop source R70 / sense R71 (1.00 kΩ) | drift, open, short | R70 open or R71 short: reads open → chain opens. R71 open: reads high → opens. R70 short: healthy loop reads 1.92 V → opens | readback, ADC | none; ±20 % drift of one resistor shifts the window by about 0.2 kΩ (noticed in the ADC value) |
| 22 | Threshold divider R72 (top), R73 (middle), R74 (bottom), R75 (2.2 MΩ keep-alive to the lower tap) | open or short of one resistor | R72 open or short, R73 short, R74 open: the window closes → chain opens (safe). **R73 open**: upper threshold goes to 5 V (short detection lost); R75 keeps the lower threshold at ≈ 23 mV so an open loop is still detected. **R74 short**: lower threshold 0 V, open-loop detection becomes indeterminate | closed-window cases: readback. R73 open, R74 short: firmware ADC cross-check only | **⚠** R73 open is latent (needs a pair short as second fault); R74 short is dangerous until the ADC cross-check acts (thick-film resistors rarely fail short) |
| 23 | Q22 (U21 LED driver) | drain-source short | U21 permanently on: HEAD_LOOP element lost | HEAD_LOOP_OK_RB low while BODY_BUMPER_L_RB (downstream node) stays high | **⚠** as #18 |
| 24 | Head-side: wire-to-wire short inside the head that bypasses the three switches but not the 1.00 kΩ | — | rail switches bypassed, loop reads healthy | not detectable by the chassis | **⚠** head design must place the resistor at the far end of the switch string and the pre-use rail press finds it |
| 25 | U31 LAB comparators, Q28 | stuck so that U22 stays on | LAB_KEY_N lost: with the LAB extension fitted only HEAD_DOCK (open, head is off the robot) keeps the chain open | firmware decodes PRES_ID on the ADC and compares with LAB_KEY_N_RB | LAB still has HEAD_DOCK open and ARM_PERMIT low; needs two more faults to move |
| 26 | PRES pull-up R80 / VREF | open, drift | reads low or high → outside window → chain open | ADC | none |
| 27 | Dock switch | fails closed | HEAD_DOCK lost; head removal is then seen only by HEAD_LOOP (J1 unplugged) and LAB_KEY_N | HEAD_DOCK_RB high while PRES_ID says absent | detected at the next head removal |
| 28 | Body bumper switch L or R | fails closed / wiring short | that bumper lost | pre-use bumper press (readback must fall) | **⚠** latent between checks; single-channel contact detection |
| 29 | Any chain harness wire | open | chain open | readback of the first dead node | none |
| 30 | Any chain harness wire | short to chassis/ground | F2 trips, chain dead | CH_N1 low | none |
| 31 | Any chain harness wire | short to +12 V (another branch) | every element upstream of the short is bypassed | readbacks upstream go low on actuation while downstream stay high | **⚠** latent until an upstream element is actuated; harness rule: chain wires in their own loom away from VBAT conductors |
| 32 | Readback tap (100 k / 56 k / 22 nF / clamp) | open or short | wrong readback, chain unaffected | plausibility between neighbouring nodes; exercised on every actuation | none for the chain |
| 33 | IOX_A, MCU input | stuck | wrong readback | sentinel bit (IOX_A GPB7 follows WDG_STROBE), neighbours | none for the chain |
| 34 | U40 watchdog | WDO stuck high (never asserts) | WDG_OK element lost: a hung MCU is not caught by hardware | boot test: firmware withholds the strobe and expects WDG_OK_RB to fall, every power-up | **⚠** between boots; ARM_PERMIT state of a hung MCU is then undefined, see #37 |
| 35 | U40 | WDO stuck low | chain open | WDG_OK_RB | none |
| 36 | Q23 (U23 driver) | short | as #34 | same boot test (CH_N9 must fall) | as #34 |
| 37 | MCU | hangs with ARM_PERMIT high and PWM running | bridges keep driving until the watchdog opens the chain (≤ 43 ms): up to 56 mm from 0.20 m/s [C] | external watchdog; MCU's own independent watchdog (firmware) | the 56 mm case; with #34 also present (two faults) motion continues until an operator or contact element opens the chain |
| 38 | MCU pin PB10 / Q24 | stuck high / short | ARM_PERMIT element lost: firmware permissives (brake test, sensors, mode, charger) no longer gate arming | firmware reads CHAIN_END_RB (IOX_B P17, needs CCR-E02) high with ARM_PERMIT commanded low → stops strobing the watchdog, which opens U23 | detected at once by a healthy MCU; hardware elements unaffected |
| 39 | K1 | seal-in contact (pole A) welded | latch cannot drop by itself, but all coils still lose supply when any element opens; **when the chain re-closes K1 re-energises without REARM** (automatic restart of the latch) | firmware sees HW_LATCH_RB rise without a REARM_BTN event and without its own arming sequence → ARM_PERMIT low, watchdog strobe stopped, FAULT | **⚠** the latch re-sets for a few ms each time before firmware reacts; the bridges are held asleep by firmware (DRV_NSLEEP) during that time, so no motion with a healthy MCU |
| 40 | K1 | pole B welded | RUN_12V follows CHAIN_END without the latch: VMOT enable and brake relays energise whenever the chain is closed, without REARM | as #39 | **⚠** as #39; "no restart without REARM" then rests on firmware |
| 41 | K1 | coil open, contacts fail open | cannot arm | no HW_LATCH_RB after REARM | none |
| 42 | D_SEAL, R_SET, C_SET (set path) | D_SEAL open: K1 will not seal → cannot stay armed. D_SEAL short: brake relays may hold ≈ 18 ms longer if REARM is held during a stop. R_SET short: a held/welded REARM can hold K1 and re-set it. C_SET open or short: cannot arm | D_SEAL open, C_SET: obvious. D_SEAL short, R_SET short: not detected | R_SET short: **⚠** latent; needs a welded or held REARM as second fault (firmware flags REARM_BTN held > 2 s) |
| 43 | REARM button | welded / held | no effect on the latch (cap-coupled); firmware flags a button held > 2 s and refuses ARM_PERMIT | REARM_BTN (separate contact) | none with R_SET healthy |
| 44 | K2 or K3 | one NO contact welded | that motor terminal stays on the bridge; the other pole still transfers, so the motor has no closed drive path and **no brake path**: that wheel coasts, the other brakes (55 mm / yaw from 0.20 m/s [C]) | BRAKE_x_RB stays high after the drop → BRAKE_TEST_FAIL, no ARM_PERMIT | detected at the next drop; one unbraked stop can occur |
| 45 | K2 or K3 | both NO contacts welded, or armature stuck energised | motor stays connected to the bridge; VMOT removal and nSLEEP still take the drive away; no dynamic brake on that wheel | BRAKE_x_RB high after the drop | as #44; drive removal then rests on U8 and U9 |
| 46 | K2 or K3 | NC contact high-resistance / open, brake resistor open, brake path trace open | relay isolates correctly but that motor is not braked | **not detected by the stationary test** (the motor shunts the resistor at DC). Detected only dynamically: firmware compares the measured deceleration after a drop with the model | **⚠** undetected at standstill; coast distance for one wheel as in §4 |
| 47 | K2 or K3 | coil open / fails to pick up | that motor never connects: no drive on one wheel | BRAKE_x_RB stays low when latched only if both poles fail; a single failed pole shows as stall/encoder fault on first motion | none (safe) |
| 48 | Coil clamp (diode + 24 V Zener) | Zener shorted | plain diode clamp: release slows to roughly 3× (≈ 15–20 ms) | not detected | **⚠** latent; adds ≈ 2–3 mm at 0.20 m/s |
| 49 | Coil clamp | open | coil kick (hundreds of volts) across the opening contact/photo-MOS: contact wear, photo-MOS over-voltage → may fail short (#16) | not detected | **⚠** latent; photo-MOS 40 V rating is protected only by the other coils' clamps on the same node |
| 50 | U8 VMOT eFuse | FET shorted / enable stuck high | VMOT stays after a drop | VMOT_SENSE not ≈ 0 V within the brake-test window → VMOT_FAULT | brake relays and nSLEEP still act; detected at every drop |
| 51 | U8 enable divider | open top | VMOT never on | VMOT_SENSE | none |
| 52 | U9 nSLEEP AND gate | output stuck high | bridges awake without the latch | not directly read back | VMOT absent and motors disconnected, so no motion; **⚠** latent loss of one of three paths |
| 53 | U5/U6 DRV8874 | output FET short (OUT to VM or GND) | uncommanded motor current while armed; on drop the relays disconnect it | bridge nFAULT / over-current, IPROPI, encoder mismatch → firmware stop; any chain element | stopped by firmware or the operator; the chain does not detect it by itself |
| 54 | VMOT bleed resistor | open | VMOT decays slowly after a drop (leakage only) | VMOT_SENSE late → VMOT_FAULT | none |
| 55 | 3V3 or V5_AUX rail | lost | all photo-MOS LEDs off → chain open | everything stops | none |
| 56 | 3V3 rail | over-voltage (buck failure) | MCU, expanders, watchdog damaged in unknown ways | not handled | **⚠** common-cause fault of all electronic elements; contact elements (selector, E-stop both poles, HANDS-ON, cover, dock, bumpers) remain |
| 57 | Pack / BMS / main fuse | opens while moving | all coils drop, brake resistors connected (needs no power) | — | same stopping distance as a contact element |
| 58 | Firmware | wrong ARM_PERMIT logic | permissives bypassed | reviews, emulator tests | hardware elements unaffected |

Summary of undetected (latent) dangerous single faults found: selector RUN contact welded (#3); harness short to +12 V (#8, #31); HANDS-ON lamp sense open (#10); plug link open and inlet-detect open (#13, #15); photo-MOS U21/U22 shorted between head removals (#16); loop comparator or its driver failed "healthy" (#18, #19, #23) where the only second channel is firmware; head-internal bypass of the rail switches (#24); bumper switch failed closed between checks (#28); watchdog dead between boots (#34, #36); welded K1 contact, where "no restart without REARM" falls back to firmware (#39, #40); R_SET shorted (#42); brake path open (#46); Zener or clamp failure (#48, #49); nSLEEP gate (#52); 3V3 over-voltage as a common cause (#56).

The two that matter most for people in the trailer: **#46** (an open brake path is invisible at standstill) and **#18/#23** (the head rail's only hardware evaluation is one comparator and one transistor; the cross-check is firmware). If the hazard analysis asks for more, the first upgrade is a second, diverse loop evaluation driving its own series photo-MOS, and force-guided relays with mirror contacts in place of K1–K3 (they need about 25 mm of height; the board allows 18 mm).

## 7. Stationary brake self-test (BRAKE_TEST): what it can and cannot show

Sequence (firmware; hardware supports each step):

1. Latch dropped, bridges asleep. Expect VMOT_SENSE < 0.5 V, HW_LATCH_RB low, BRAKE_L_RB and BRAKE_R_RB **low** (isolated).
2. Boot only: withhold the watchdog strobe → WDG_OK_RB must fall within 35 ms and return 200 ms after strobing resumes. Then assert ARM_PERMIT with every other element closed → CHAIN_END_RB must rise; de-assert → must fall. HW_LATCH_RB must stay low throughout (K1 not welded).
3. Operator presses REARM. Expect HW_LATCH_RB high within 30 ms, VMOT_SENSE within 5 % of VBAT_SENSE within 50 ms, BRAKE_L_RB and BRAKE_R_RB **high** (bridges still asleep).
4. Firmware drops ARM_PERMIT. Expect HW_LATCH_RB low within 15 ms, BRAKE_L_RB and BRAKE_R_RB low within 25 ms, VMOT_SENSE < 1 V within 1 s (1 kΩ bleed on 810 µF: τ = 0.8 s; the window must allow 3 τ).
5. Operator presses REARM again to arm for the mission (5 s lock-out applies).

| Shown by the stationary test | Not shown |
|---|---|
| Each brake relay's NO contacts are open on both poles when released (#44, #45) | That the NC contacts and the brake resistor actually conduct (#46) |
| Each relay picks up (#47) | Brake force, stopping distance, slope holding |
| VMOT appears with the latch and disappears without it (#50, #51, #54) | Release time of K1–K3 (only a gross limit, firmware-timed) |
| K1 is not welded at boot (#39, #40) | A K1 contact that welds during the mission (found at the next drop) |
| Watchdog and ARM_PERMIT elements open the chain (#34–#38), at boot | Contact elements: only actuating each one shows it opens (pre-use check) |
| Readback paths toggle | Clamp components (#48, #49), nSLEEP gate (#52) |

Dynamic check recommended in addition (firmware, no extra hardware): on the first protective or commanded drop from ≥ 0.05 m/s of each mission, compare encoder deceleration with the braked model; a time constant more than twice the calibrated value on either wheel raises BRAKE_TEST_FAIL.

## 8. First power-up procedure for the chain (bench, wheels off the ground, current-limited supply)

Record every reading. Stop at the first deviation.

1. **Unpowered continuity.** No pack. With all field devices connected and in their run state, measure J_MODE 3 → J_ESTOP… through to U20 input: each switch loop < 1 Ω; CH_N0 to ground > 50 kΩ; COIL_RTN to ground < 1 Ω with the E-stop released and open with it pressed. K2/K3: motor terminal A to B = 1.0 Ω + winding in parallel (≈ 0.7 Ω); motor terminals to bridge outputs open.
2. **Logic rails only.** Bench supply 12.0 V, 0.5 A limit, selector SERVICE. Expect 3V3, V5_AUX, VREF 3.000 V; CH_N1 = 0 V; all readbacks low; VMOT 0 V. Selector RUN: CH_N1…CH_N4 follow as each device is closed; operate each device in turn and note the node that falls and the readback bit.
3. **HEAD_LOOP window.** Decade box on J1 pins 5–6: U21 on between 0.59 kΩ and 1.55 kΩ (±5 %), off at 0 Ω, at open, and with either pin tied to ground or to 12 V through 1 kΩ. Log HEAD_LOOP_SENSE at 0.6, 1.0, 1.6 kΩ (expect 1.79, 1.56, 1.32 V).
4. **PRES_ID window.** Decade box on J1 pins 7–2: U22 on between 3.92 and 5.64 kΩ only; check 1.137 kΩ, 1.50 kΩ, open and short all give off. Log the ADC value at each contract code.
5. **Plug link / inlet.** Link J_PWR 4–8: CH_N4 falls. Remove link, apply 24 V to the inlet pins through 1 kΩ: CH_N4 falls.
6. **Watchdog and permit** with a test firmware: no strobe → CH_N9 low; 10 ms strobe → high; 1 ms and 40 ms strobe → low. ARM_PERMIT low/high → CHAIN_END follows. Hold the MCU in reset: CHAIN_END low.
7. **Latch.** All elements closed. Press REARM: K1, K2, K3 pick up; RUN_12V = supply − < 0.5 V; chain current 70–90 mA. Hold REARM and open any element: everything drops and does not return while the button is held; after release and re-close, nothing returns until REARM is pressed again, and not within 3 s of the previous press. Short the REARM contacts permanently: the latch must not set after an element is cycled.
8. **Each element drops the latch.** Arm; open each element in turn (including each E-stop pole alone, by lifting one wire); re-arm between. Scope RUN_12V and a brake-relay NC contact: record time to NC closure (expect ≤ 10.5 ms; ≤ 13 ms for the loop and PRES_ID).
9. **Power loss.** Arm; switch the supply off: scope as in 8.
10. **VMOT.** Raise the current limit to 3 A. Arm: VMOT rises in 2–5 ms (soft start); drop: eFuse off within 5 ms, VMOT < 1 V within 3 s.
11. **Brake readback.** Dropped: BRAKE_x_RB low. Jumper one bridge output to its motor terminal (simulated weld): high. Remove.
12. **Braking.** Motors fitted, wheels free. Run each wheel at the 0.20 m/s equivalent, open the E-stop: record encoder spin-down with the brake resistor fitted and, once, with it lifted (coast). The two time constants give the rotor inertia and friction that replace the assumptions of §4.
13. **Bus clamp.** Pack disconnected, bench supply with a series diode; back-drive a wheel by hand or decelerate from speed: VMOT must not exceed 16.0 V; BUS_CLAMP_ACTIVE pulses.
14. Only then: on the floor, restrained, VT-003/004 stopping-distance trials at 0.05, 0.10, 0.20 m/s for every initiating element.
