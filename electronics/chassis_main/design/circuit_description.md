# RR-CHS-MAIN rev A circuit description

Companion to `circuit.py` (the netlist), `connectors.yaml` (harness view), `layout_guidance.md`, and the analyses in `electronics/analysis/` (`power_budget.md`, `chassis_safety_chain.md`, `chassis_design_notes.md`). Tags: [D] datasheet read in stage 1 (TI PDFs fetched and searched; the files are not in the repository), [C] calculated, [A] assumed, [U] unverified. Not a certified safety system.

## Block summary

| Block (`block` in circuit.py) | Main parts | What it does |
|---|---|---|
| power_entry | J_PWR, TVS, U1 LM74502 + Q1/Q2, R_SH1 + U2 INA228 | Pack feed in, reverse-polarity protection, selector-controlled master switch with slew-limited turn-on and 16.5 V over-voltage cut-off, pack current/energy metering. Output: VBAT_SW. |
| charger | F_CHG, Q3, U3 LTC4162-F, Q4, Q5, L1, sense resistors, Q6 | 24 V inlet → reverse protection → input ideal diode → VSYS (service loads) → 3 A buck charger → VBAT_SW; battery ideal diode VBAT_SW → VSYS when no input. Hardware +5 °C charge inhibit through the NTC line. |
| rails | U10 LM61460 (5.12 V, 6 A), U13 eFuse, U11/U12 LMR51610 (3.3 V, 5 V_AUX), U14 REF3030 | All three converters run from VSYS and are enabled by the selector (EN_SYS), not by the MCU: V5_CM5 stays up across MCU resets. |
| branches | U15 INA3221 + shunts, U16–U19 TPS259470, U25 TPS2553 | HEAD_PWR 1.5 A (with LC filter), HEAD_HTR 4.05 A, CHS_HTR 3.04 A, V12_LIDAR 1.5 A, BUS_5V 0.17 A. Head branches are forced off in hardware while the charge inlet is live; both heaters are forced off when the watchdog is not satisfied. |
| chain | F_CHAIN, field connectors, U20–U24 photo-MOS, U30–U32 comparators, U40 watchdog, K1, taps | The hardwired traction chain. See `chassis_safety_chain.md`. |
| drive | U8 TPS25982, VMOT bulk, U5/U6 DRV8874, K2/K3, brake resistors, U9, U33 clamp, U35–U38 | VMOT exists only while the latch is set; two H-bridges in PWM (IN/IN) mode at 20 kHz; DPDT brake relays; 1.0 Ω brake resistors; brake-chopper clamp at 15.6 V; encoder buffers. |
| mcu | U20M STM32G474RET6, Y1, U42 BMI088, U43–U45 expanders, SWD, debug UART, USB | Pin use exactly as `firmware/chassis/pinmap.yaml`. |
| tof | U50/U51 TCA9548A, J_TOF0–10 | Eleven sensor branches, each with pull-ups, 100 Ω series resistors, ESD array and a filtered 3.3 V feed. |
| head_link | U61 FT230X, U62 THVD1450, L60, D60, J_HEAD1, J_HEAD2, U63 (DNP) | Host-side head data link and the J1/J2 harness landings. |
| panel_io | Q50–Q58, J_PANEL | Low-side drivers for the panel LEDs, button lamps and sounder. |

## Power tree

```
pack ─ coupler ─ 20 A fuse ─ J_PWR ─ Q1/Q2 (U1, EN from selector) ─ R_SH1 ─ VBAT_SW ─┬─ F_CHAIN ─ safety chain ─ relay coils
                                                                                       ├─ U8 (EN = RUN_12V) ─ VMOT ─ U5, U6 ─ K2, K3 ─ motors
                                                                                       ├─ R_SH2 ─ U16 ─ L5 ─ HEAD_PWR (J1 1/2)
                                                                                       ├─ R_SH3 ─ U17 ─ HEAD_HTR (J1 3/4)
                                                                                       ├─ R_SH4 ─ U18 ─ CHS_HTR
                                                                                       ├─ U19 ─ V12_LIDAR
                                                                                       ├─ F_AUX ─ V12_AUX (lamps, sounder, fan)
                                                                                       └─ Q5 (battery ideal diode) ─┐
24 V inlet ─ J_PWR ─ F_CHG ─ Q3 ─ Q4 (input ideal diode) ─ R_SNSI ─────────────────── VSYS ─┬─ U10 ─ U13 ─ V5_CM5
                                             U3 buck: VSYS ─ L1 ─ R_SNSB ─ VBAT_SW (charge) ├─ U11 ─ 3V3
                                                                                            └─ U12 ─ V5_AUX ─ U14 ─ VREF_3V0
```

While charging, VSYS is at the inlet voltage (24 V) and the compute, logic and network loads draw from the supply, not from the pack, so the charger's termination current is not disturbed. Everything on the battery side that could load the pack during charge is either off (head branches, by hardware; traction, by the chain) or deliberate (bay heater).

### Charger behaviour (design intent; register-level behaviour of the LTC4162 is [U])

| Situation | Behaviour |
|---|---|
| Charger unplugged while running | Q4 blocks, Q5 conducts within the IC's ideal-diode response; VSYS falls from 24 V to pack voltage. U10–U12 ride through (input range 4–36 V and 4–65 V). The chain stays open until the cover is shut **and** REARM is pressed: unplugging cannot start motion. |
| Pack full | Charger terminates on C/10 with only pack current in R_SNSB; service load continues from the inlet. |
| Pack cold (< +5 °C at the pack-surface NTC) | U32B opens Q6: the charger sees a very cold thermistor and pauses. Independent of that the charger's own JEITA limit is set to +5 °C by firmware and the BMS refuses charge at 0 °C [D pack sheet]. Service loads still run from the inlet. |
| Pack empty / BMS in under-voltage cut-off | VBAT_RAW is dead, so EN_SYS is low and the board is off even with the charger connected. The charger cannot wake a pack through the open main switch. **Gap:** recovering a BMS-latched pack needs the bench charger (R10). |
| BMS opens during charge or drive | VBAT_SW is held by the charger (if connected) or collapses. On collapse everything stops and the brake relays drop. Regeneration with the BMS open is taken by the 15.6 V clamp. |
| Selector OFF with charger connected | Nothing runs, nothing charges. |

## Decisions and their reasons

1. **Two USB cables, no hub.** The MCU's CDC link and the FT230X bridge are independent USB devices on separate host ports. A hub would add a crystal, a 3.3 V load and a single part whose failure removes both the chassis link and the head link at once; with two cables a link failure is attributable. Cost: two host ports on the carrier (CCR-E10).
2. **FT230X with TXDEN** for RS-485 direction: the driver enable is generated in the bridge from the UART shift register, so turnaround does not depend on host scheduling. 1 Mbaud is an exact divisor (3 MHz / 3). The bridge is bus-powered so it enumerates whenever the host is up; 1 kΩ series resistors and a diode-coupled RXD stop either side back-feeding the other.
3. **5 V RS-485 transceiver** (THVD1450 from V5_AUX) because the bus side of the head's isolated transceiver is powered by BUS_5V from the same rail.
4. **eFuses (one type, TPS259470) on every switched branch** instead of smart high-side switches: ±10 % limit accuracy (the 16 mΩ high-side switch considered has 2.6–5.7 A spread on a 4.4 A setting [D]), built-in slew control, fault output, reverse-current blocking.
5. **Photo-MOS relays for the electronic chain elements**: galvanic separation between the 12 V chain and the logic that evaluates the loop, PRES_ID, watchdog and ARM_PERMIT; they fail open when their logic rail disappears.
6. **Standard relays, not force-guided**: force-guided types of the needed rating are 24–25 mm high against 18 mm. The contact state is measured electrically instead (brake readback); the limits of that are in the single-fault table.
7. **PWM 20 kHz**, both bridges from TIM8, centre-aligned. Above hearing, 60 mA ripple in the windings [C, 2.5 mH assumed], well below the DRV8874's capability. The detector head sees it only through the shared bus: the L5 filter, the head's own regulators and the separate heater pair deal with that; the bench test is in `chassis_design_notes.md`.

## Prototype-to-production crosswalk (0.3 BOM rows carried forward)

| 0.3 row | 0.3 item | Custom design |
|---|---|---|
| W08 | NUCLEO-G474RE motion MCU | U20M STM32G474RET6 + Y1 + J_SWD on RR-CHS-MAIN; same pin map on the Nucleo morpho headers for bring-up |
| W09 | Board interconnect, level matching | U37/U38 encoder buffers, U42 IMU on board, USB CDC to the CM5 |
| W11 | RoboClaw 2×15 A | U5/U6 DRV8874 + U8 + K2/K3; RoboClaw stays a bench fallback (firmware DRIVE interface unchanged) |
| W18 | BMI088 carrier | U42 on the board at (80, 67) |
| W20/W21 | VL53L4ED carriers and bus | RR-TOF ×11 via U50/U51 and J_TOF0–10 |
| W24 | D2HW switches | J_BUMP_L/R, J_DOCK, J_COVER (and the head's three rail switches through J1) |
| W25, E10 | E-stop and drive inhibit, external stop provision | K1 latch, J_ESTOP (two poles); an external stop is a second NC device in series with J_ESTOP pins 1–2 and 3–4 (no board change) |
| W26, E06 | ADM2582E evaluation boards | chassis end: U61 + U62 (non-isolated, 5 V); isolation is in the head (DEC-024) |
| W27 | Head connector set | J_HEAD1, J_HEAD2 landings |
| W28, E01, R01, R02 | Pack, coupler, spare | J_PWR + J_PAUX; modules sheet `battery_pack.md` |
| W29, R03, R04 | Charger, inlet, power path | U3 block, J_PWR pins 3/4/7/8, U20 plug-link element |
| W30, E02, E03 | Rails, D24V90F5, branch protection, braking energy | U10–U14, U16–U19, U8, U33/Q40 clamp |
| W31, E08, E09 | Heaters and cut-outs | U17, U18, INA3221, J_HTR, J_NTC; cut-outs are in the harness/head |
| W32 | Current and voltage logging | U2 INA228, U15 INA3221, IPROPI |
| E11 | Annunciator panel | RR-PANEL + Q50–Q58 |
| R05 | Master selector | J_MODE (EN contact + RUN contact) |
| R06 | Start/Resume, Pause/Stop | J_BTN (REARM set path + aux contact, PAUSE contact, lamps) |
| R10 | Spare-pack bench charger | purchased module, `bench_charger.md` |
| R11, R12 | Access supervision, personnel-protection scanner | not on this board; a supervised external stop output can be inserted as a further series contact at J_ESTOP |
