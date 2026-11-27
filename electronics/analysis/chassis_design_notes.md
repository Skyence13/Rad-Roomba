# RR-CHS-MAIN design calculations and EMC notes

Owner: chassis electronics. Evidence class `calculated`; nothing measured. Tags: [D] datasheet read in stage 1, [C] calculated, [A] assumed, [U] unverified. Part references are those of `electronics/chassis_main/design/circuit.py`. The power budget, voltage drops and thermal totals are in `power_budget.md`; the chain, braking and clamp energy are in `chassis_safety_chain.md` and `chassis_braking_tables.md`.

## 1. Charger (U3 LTC4162-F)

The LTC4162-F datasheet could not be opened from the design environment (analog.com returned HTTP 503). What was confirmed from search results [D]: 35 V / 3.2 A LiFePO₄ buck charger with PowerPath and I²C telemetry, 1–9 cells, 4.5–35 V input, JEITA temperature-qualified charging, 28-lead 4 × 5 mm QFN, variants -FAD (I²C-adjustable voltage), -FFS, -FST with "M" suffix versions that enable MPPT. **Everything else in this section is [U] and must be checked against the datasheet before layout**, including every pin number of U3.

| Quantity | Design value | Basis |
|---|---|---|
| Variant | LTC4162EUFD-FAD | adjustable charge voltage, MPPT off; default per-cell voltage assumed 3.60 V [U] → 14.4 V for 4 cells |
| Cell count | 4, by the CELLS1/CELLS0 straps | coding [U]: both pins have three strap positions (GND, INTVCC, VCC2P5) as DNP 0 Ω options |
| Charge current | 3.0 A; R_SNSB 10 mΩ gives 3.2 A full scale with a 32 mV sense voltage [U] | contract 3.0 A = 0.25 C on 12 Ah; set by register or by a 10.7 mΩ resistor if 3.0 A must be the power-on default |
| Input current limit | 4.0 A with R_SNSI 8 mΩ [U] | supply 3.75 A: set the register to 3.5 A so the adapter is never overloaded; power-on default 4.0 A exceeds it by 7 % (adapter has its own limit) |
| Inductor L1 | 4.7 µH, I_sat > 6 A | ripple ΔI = V_out (1 − V_out/V_in) / (L f) = 14.4 × 0.4 / (4.7 µH × 1.5 MHz) = 0.82 A [C] with f = 1.5 MHz [U] |
| Input demand | 3.0 A × 14.4 V / 0.93 + service load 12 W = 56 W, 2.35 A at 24 V | [C], efficiency [A] |
| Dissipation | about 3.2 W in U3 and L1 at full charge current | [C]; on the gap pad |
| Cold inhibit | hardware: U32B opens Q6 below +5.3 °C on the pack-surface NTC (10 kΩ B3435, 10.0 kΩ to 3.000 V: 22.6 kΩ ↔ 2.08 V) [C]; 2 K hysteresis | independent of charger registers; open sensor = cold |
| Thermistor for the charger | cassette NTC 10 kΩ via the coupler auxiliary contact, 10 kΩ bias | JEITA defaults [U]; firmware writes the +5 °C lower limit as a second layer |

Bench tests: charge a pack from 12.0 V and log INA228 current against LTC4162 telemetry (CC 3.0 A ±5 %, CV 14.4 V ±1 %, termination below C/10 with the CM5 running at full load); pull the charge plug at 3 A and scope VSYS (no dip below 9 V, no MCU reset); cool the NTC through +5 °C and confirm charge current falls to zero within one telemetry cycle; open the NTC line; reverse the inlet polarity through a 5 A supply.

## 2. 5 V compute rail (U10 LM61460, U13 eFuse)

| Quantity | Value | Basis |
|---|---|---|
| Input | VSYS: 10.0–14.6 V on battery, 24 V ±5 % while charging; device range 3–36 V [D] | — |
| Output | 1.0 V × (1 + 41.2 k/10 k) = 5.12 V | FB reference 1.0 V [U] |
| Frequency | 400 kHz, RT = 33.2 kΩ [D] | below the AM band, low switching loss at 24 V |
| Inductor | 6.8 µH: ΔI = 5.12 × (1 − 5.12/12.8) / (6.8 µH × 400 kHz) = 1.13 A; 1.49 A at 25.2 V [C] | 23–30 % of 5 A |
| Output capacitors | 3 × 22 µF (about 35 µF effective at 5 V bias [A]) + 22 µF after the eFuse | ripple ≈ ΔI / (8 f C) = 10 mV [C] |
| Current limit | high-side 8.9–11.5 A [D]; the 5.0 A limit is the eFuse U13 (RILM 665 Ω → 3343/665 = 5.03 A, ±10 % [D table]) | — |
| Loss | R_DS(on) 41 + 21 mΩ typ [D]; about 0.6 W at 1.4 A out, 1.1 W at 2.4 A | [A] 92 % |
| Hold-up across MCU reset | EN from EN_SYS (selector), not from the MCU; U13 is on by a resistor divider; only IOX_B P12 (outside NRST) can switch it off | requirement |

Bench tests: load step 0.5 → 4 A (deviation < 150 mV at the carrier); short the output (eFuse trips, V5_CM5_NFLT low, auto-retry); reset the MCU by SWD while logging V5_CM5 (no dip); measure the carrier voltage at 3 A at −20 °C.

## 3. Logic rails (U11, U12 LMR51610, U14 REF3030)

3.3 V: 0.8 V × (1 + 31.6 k/10 k) = 3.33 V; 5 V_AUX: 0.8 × (1 + 52.3/10) = 4.98 V [C], reference 0.788–0.812 V [D]. 22 µH: ripple 0.28 A (3.3 V from 12.8 V), 0.32 A from 24 V [C]. PFM variant for low idle loss; if PFM ripple shows up in the loop or PRES_ID readings fit the FPWM variant (same footprint). VREF_3V0 load: 0.64 mA PRES pull-up + 0.9 mA NTCs + 0.14 mA divider + MCU VREF+ ≈ 2.5 mA against 25 mA capability [U].

## 4. H-bridges (U5, U6 DRV8874)

| Quantity | Value | Basis |
|---|---|---|
| Rating | 4.5–37 V, 6 A peak, over-current trip 6 A min / 10 A max, R_DS(on) 100 + 100 mΩ typ, 120 + 120 mΩ max at 25 °C [D] | stall current of the motor (5.5 A at 12 V, 6.6 A at 14.4 V) is **not** carried: it is above the 6 A minimum trip |
| Hardware current limit | ITRIP = VREF / (R_IPROPI × A_IPROPI) = 3.000 / (2490 × 450 µA/A) = **2.68 A** [C], mirror error ±5.5 % above 2 A [D] | 49 % of 12 V stall; thrust at the limit 2 × 43 N [C], near the traction limit (12 kg × 0.7 on the drive wheels × μ 0.8 ≈ 66 N [A]) |
| Current feedback | 1.1205 V/A at the ADC, full scale = ITRIP | 1 kΩ / 10 nF filter, sampled at PWM centre |
| Chopping | fixed off-time 25 µs [D] in the IMODE setting to be strapped [U] | — |
| PWM | 20 kHz centre-aligned, IN/IN mode with slow decay (PMODE high [D]) | winding ripple 12 V × 0.25 / (2.5 mH × 20 kHz) = 60 mA [C, L assumed] |
| Edges | 150 ns [D], not adjustable: 12 V / 150 ns = 80 V/µs | ferrite + 1 nF at the connector, short bridge-relay-connector path |
| Dissipation | 0.2 Ω × I²: 0.05 W at 0.5 A, 0.45 W at 1.5 A, 1.4 W typ / 2.4 W hot at the 2.68 A limit; quiescent 3 mA × VMOT [D] | junction rise at stall about 2.4 W × 35 K/W [A] = 85 K: allowed for the 2 s stall timer, not continuously |
| Sleep | nSLEEP low → outputs Hi-Z within 1 ms [D]; gate U9 forces it whenever the latch is dropped | — |

Bench tests: locked-rotor current waveform (limit 2.68 A ±0.2 A, no nFAULT); IPROPI against a current probe at 0.3, 1, 2 A; case temperature after 2 s stall and after 10 min at 1.5 A; conducted ripple on VBAT_SW and on HEAD_PWR_P with both motors at 50 % duty.

## 5. Regeneration clamp (U33, Q40)

Energy and power are in `chassis_braking_tables.md` T7: at most 0.9 J per stop and 34 W peak; bus capacitance 1010 µF would otherwise rise to about 45 V. Clamp: on at 2.5 V × (100 k + 19.1 k)/19.1 k = 15.59 V; hysteresis 3.3 MΩ ≈ 0.5 V [C]; reference tolerance 0.5 % plus 1 % resistors → 15.3–15.9 V. Above the highest normal bus voltage (14.6 V) and below the pack-switch over-voltage cut-off (16.5 V [U threshold]) and every part rating on the bus (TPS259470 23 V, TPS25982 24 V, DRV8874 37 V [D]). Resistor 2 × 9.1 Ω in parallel: 3.4 A, 53 W peak; PTC F_CLAMP trips if the FET sticks. Powered from VBAT_SW, so it works without the logic rails.

Bench test: section 8 step 13 of `chassis_safety_chain.md`; additionally decelerate both wheels from full speed with the pack switch opened by the selector and scope VMOT (must stay below 16.0 V).

## 6. Encoder inputs

Hall outputs on a 5 V supply (F 0.1 A PTC per motor), 10 kΩ pull-ups to 5 V, 4.7 kΩ / 1 nF (τ = 4.7 µs, corner 34 kHz) into 74LVC2G17 Schmitt buffers at 3.3 V (5 V-tolerant inputs [D]). Highest edge rate: 67 rpm × 150 / 60 × 64 = 10.7 kHz of counts, i.e. 2.7 kHz per channel, 93 µs between edges: 20 time constants [C]. ESD array at the connector. The buffers drive PB4–PB7 push-pull, which also overrides the UCPD dead-battery pull-downs the pin map mentions.

Bench test: count error over 100 wheel revolutions in each direction with the other motor PWM-ing at stall (must be zero); scope A/B at the MCU pins with motor current at the limit.

## 7. I²C buses

System bus (400 kHz, 2.2 kΩ): U2 0x40, U15 0x41, U3 0x68, U44 0x20, U45 0x21: five loads, about 60 pF, rise 110 ns [C]. ToF bus: see `electronics/modules/tof_vl53l4ed.md` (400 kHz justified per branch; the muxes isolate a hung cable, and IOX_B P16 resets both muxes). A stuck SDA on one ToF branch is cleared by deselecting the channel; the system bus is not affected because it is a separate MCU peripheral.

## 8. RS-485 head link (U61 FT230X, U62 THVD1450)

| Quantity | Value | Basis |
|---|---|---|
| Baud rate | 1 000 000 = 3 MHz / 3, exact | FT-X baud generator [U] |
| Bit time | 1 µs; a 2048-byte record takes 20.5 ms | contract |
| Direction | TXDEN (CBUS0) drives DE and /RE together: asserted about one bit before the start bit, released at the end of the stop bit | [U] documented for the FT232R; FT230X default CBUS0 function to be confirmed or programmed |
| Driver enable/disable | propagation 250–500 ns, disable ≤ 200 ns [D] | the bus is released within 0.2 µs of the last stop bit |
| Turnaround rule for the head | do not drive before 2 bit times (2 µs) after the last stop bit of a request; release within 1 bit time after the last stop bit of a reply | covers TXDEN + disable time with margin; the head firmware's reply latency (≥ tens of µs) already satisfies it |
| Host latency | FTDI latency timer 1 ms minimum (default 16 ms) [D FTDI knowledge base]: set `latency_timer` = 1 | adds up to 1 ms, one-sided, to the four-timestamp exchange: the time bound cannot be better than about 0.6 ms from this term; the 2 ms target and 10 ms limit are met [C] |
| Receiver while transmitting | disabled; RXD held at mark by 4.7 kΩ through the diode coupling | no echo to discard |
| Termination and bias | 120 Ω at each end; 560 Ω bias pair at the chassis only: 5 V × 60 / (560 + 60 + 560) = 254 mV idle differential [C] | above the 200 mV threshold; the receiver is also fail-safe by design [D family] |
| Protection | 10 Ω series, common-mode choke, SM712 at the connector; transceiver ±18 kV IEC contact [D] | — |
| Presence | J2 pin 7 to ground in the head plug → P-MOSFET detector → PC12 with EXTI | sub-millisecond bounce still latches an event |
| BUS_5V | TPS2553 current-limited switch, about 0.17 A [U], short-proof | powers the bus side of the head's isolated transceiver |

Bench tests: scope TXDEN against TXD and the bus at 1 Mbaud (enable lead, release lag); 10⁷ records of the head protocol with both motors PWM-ing at stall and both heaters cycling: zero CRC errors expected; pull J2 during traffic (event latched, no latch-up); short BUS_5V to ground and to pin 1.

## 9. Keeping motor and heater noise off the head supply and data

| Coupling path | Measure on RR-CHS-MAIN | Bench test that verifies it |
|---|---|---|
| 20 kHz PWM ripple and its harmonics on VBAT_SW → HEAD_PWR | 810 µF low-ESR bulk at VMOT behind the eFuse; L5 + 20 µF on the head feed (corner 11 kHz, −40 dB/decade above) | Spectrum of HEAD_PWR_P at J1 with motors at 25/50/75 % duty and at stall: < 20 mV p-p in 20 kHz–1 MHz; then count-rate test in the head with a pulser |
| Bridge edges (80 V/µs) radiating from motor leads into J1/J2 cables | ferrite + 1 nF at each motor pin; twisted motor pairs; J1/J2 shielded and bonded at the receptacle | Near-field probe along the motor leads; head dark-count rate with motors running against stopped |
| Heater switching steps on the shared bus | head heater on its own pair with its own return (NT1); DVDT capacitor gives a ms-scale turn-on; the head switches its heater on gate boundaries | Scope HEAD_PWR_P and the loop sense while HEAD_HTR toggles at 4 A: step < 100 mV, no comparator chatter |
| Heater return current shifting the PRES_ID reference and the loop sense | separate heater return; PRES_ID window tolerates 0.27 V | Log HEAD_PRES_ID and HEAD_LOOP_SENSE with the heater on and off through the 2 m extension |
| Buck converters (400 kHz, 1.5 MHz) into the bus and the RS-485 pair | compact hot loops, shielded inductors, RS-485 pair 5 mm away, RBOOT option | Spectrum of VSYS and VBAT_SW; bit-error test as in §8 |
| Common-mode noise on the data cable | CMC, bias, fail-safe receiver, shield bonded at the chassis | Inject 1 V p-p common mode at 20 kHz–10 MHz on the cable with a clamp; zero CRC errors |
| ESD at operator-accessible points (E-stop, buttons, inlet, J1/J2 shells) | TVS on every power output, ESD arrays or dual diodes on every signal that leaves the board, 100 kΩ taps into the chain readbacks | ±8 kV contact / ±15 kV air on shells and buttons with the system running: no latch drop without a real element opening, no reset |

## 10. Open design items (not yet closed in rev A)

1. LTC4162-F pin map, strap coding and register defaults (§1).
2. Pin numbers of the `verify=True` parts (132 lines in `circuit.py`), in particular K1–K3 contact numbering, TPS259470 pins 3/4, BMI088, FT230X, MCP23S17.
3. Photo-MOS type: TLP241A is a 4-pin DIP/SMD part 4 mm high; ratings and turn-off time unread. Any 40–60 V, ≥ 0.5 A, ≤ 1 ms, −40 °C form-A type fits the netlist.
4. LM74502 enable and over-voltage thresholds and the recommended inrush network.
5. IMODE strap of the DRV8874.
6. No electronic current limit at pack level (CCR-E01); no MCU input for pack presence or BUS_5V fault.
7. Sounder level (RR-PANEL).

## 11. Stage 3 (review fixes): component choices

Circuit and fault analysis are in `chassis_safety_chain.md` §2 and §6; the change list is `electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md` "Stage 3".

| Part | Choice | Reason |
|---|---|---|
| D_RSET (C_SET charge diode) | 1N4148W, silicon | blocks C_SET back-feed (M1). A Schottky's reverse leakage at temperature (tens to hundreds of µA [A]) into the 156 kΩ CHAIN_END tap would hold CHAIN_END up again. Reverse ≤ 14.6 V |
| U_SET, U_HOLD, U_LS, U21B | TLP241A, as U20–U24 | one photo-MOS type on the board; ratings, IFT and switching times [U] (stage-1 note). With D_RUN and the 20 V K2/K3 clamps no photo-MOS sees more than 36.5 V off-state, even with RUN_12V held up by a fault |
| Q_HSET (U_HOLD set current) | BSS84 from V5_AUX, gate = set-stack node | the U_HOLD LED must be unreachable from the K1 coil side, otherwise a welded K1 seal-in would hold U_HOLD; a diode from the set pulse would have cost 0.75 V of set margin and leaks the seal-in voltage |
| D_RUN | B160-13-F (60 V, 1 A Schottky, SMA) [U ratings recalled] | 0.3 V at 95 mA [A]; 60 V because the K2/K3 kick (≤ 21.9 V) adds to a live RUN_HD in fault cases |
| D32, D35 (K2/K3 clamp Zener) | BZT52C24 → BZT52C20 | keeps U_LS off-state ≤ 36.5 V when RUN_12V is held up; release about 0.3 ms slower [A] (T2) |
| U46 (loop channel B) | TLV3201AIDBVR, CMOS push-pull | diverse from the LM2903B (bipolar, open collector); OUT (pin 1) next to V− (pin 2), so a solder bridge opens the channel. DBV pinout recalled [U] |
| U47 (IOX_D) | TCA9534PWR at 0x22 | the MCU and IOX_A/B/C have no free pin; same part and pin table as U45 [U] |
| Readback series resistors | 47 kΩ | 70 µA from a 3.3 V output against a comparator sinking mA; inputs see < 50 mV drop with < 1 µA leakage |
| Taps on PB12, PD2 | 22 kΩ / 15 kΩ | valid HIGH above 7.7 V even with the STM32 pull-down enabled (M3); clamp current into 3V3 ≤ 0.26 mA per tap at 14.6 V |

K1 set margin over supply and temperature is table T11 of `chassis_braking_tables.md`; VMOT decay with capacitor tolerance T10.

## 12. Stage 4 (follow-up review fixes): component choices

| Part | Choice | Reason |
|---|---|---|
| U33B (SET_READY) | the unused half of the bus-clamp LM2903B, reference CLAMP_REF (LM4040C 2.5 V) | no new IC; supplied from VBAT_SW like the reservoir; rising 10.8 V / falling 9.3 V with R_SD1 1 M, R_SD2 348 k, R_SDH 2.2 M (T11). A shared-IC failure costs availability (never/always ready), not a barrier |
| Q_SETC + R_SCG/C_SCG | third FET in the set stack, 100 k / 470 nF gate | an early press cannot dump C_SET; the gate RC keeps the stack on 37-67 ms into the dump although SET_READY falls |
| R_SET | 15 k (was 22 k) | charge tau 1.5 s; a stuck-on stack still gives ≤ 0.94 V on the coil (< 1.2 V must-release) |
| C_SF | 2.2 µF X7R 16 V 0603 | qualification: the set pulse cannot start earlier than 3.2 ms after the set contact closes (T13), so the 1 kHz firmware sampling sees every press that can set |
| D_RUN | S1G-13-F silicon (was B160 Schottky) + R_RHD 10 k | hot Schottky leakage (mA) could hold U_LS/U_HOLD after a drop with RUN_12V held up (review N5); silicon leaks µA, bled below the LED forward voltage (T14). Costs about 0.4 V on the K2/K3 coils |
| D_AUX | PESD15VL2BT on the aux pair (D29 removed) | 15 V stand-off as D_SET; the 5.5 V TPD4E05U06 would conduct from a V12_AUX short (review m-C) |
| Q_LTA / Q_LTB | BSS138 on LOOP_F / LOOP_FB, gates on IOX_D outputs with 100 k pull-downs | self-test that can only force a channel open; off at power-up; drain leakage pulls the filter node towards "open" (≤ 50 mV hot) |
| Channel B threshold | R_LB2 30.9 k: 1.89 kΩ (was 2.70 kΩ) | narrows the marginal band between the channels to 1.55-1.93 kΩ (review N6) |
