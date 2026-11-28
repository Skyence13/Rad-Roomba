# 05 Maintenance and spares

**Updated 2026-11-28:** section 6 (the per-shift check P1 and the six-monthly service tests S3 to S8 of the traction chain) is new; sections 1 to 5 and 7 are revised for the stage-5 chassis board and firmware, head stage 3 and firmware 0.6.0, and the thermal policy. **Status.** No part has worn, failed or been serviced. Intervals are **not defined in any source** except where quoted; the schedule below is a set of proposals built from the design documents, to be replaced by measured wear. Evidence classes as in `docs/build/README.md`. Every maintenance action that touches the traction chain, the head rail or switches, the brakes, the tyres, the motors, the sensors' positions or the firmware timing reopens stopping or coverage evidence (0.3 baseline, `docs/Rad_Roomba_Design.pdf` chapter 09 "Configuration control and handover"): record it and decide with the lead which trials to repeat.

## 1. Periodic checks (proposed intervals)

| Check | Interval | Method | Source of the check |
|---|---|---|---|
| Pre-use set (local stops, head identity, source check, window, tyres, caster, pack) | every shift | 01 section 3 | field checklist |
| **Per-shift check P1** (E-stop, HANDS-ON lamp and latch, each bumper and rail zone, selector SERVICE shows MODE_RUN open, brief REARM press when ready) | every shift, operator, about 2 min | section 6.1 | `chassis_safety_chain.md` section 6.2 |
| **Service tests S3 to S8** (set stage, U_HOLD, U_LS, D_RUN, R_RHD, brake path and relays, plug channels, watchdog and nSLEEP gate) | **every 6 months**, and after any repair on the chassis board, K1/K2/K3 or the cables W-015 to W-022, and after any of `K1_WELD`, `RUN_SHORT`, `LOOP_FAIL`, `LOOP_SW_SHORT`, `SET_STAGE_FAULT` or a repeated `REARM_REFUSED PARTIAL`; cover off, wheels off the ground | section 6.2 | `chassis_safety_chain.md` section 6.2, table T15; **not a certified proof-test interval** |
| Full element-by-element chain test (each element opened, drop time recorded) | after any repair of the chain; first time before the first move | `docs/build/04_bring_up.md` section 6 | VT-039 |
| Brake test | every boot (required before motion) | `BRAKE_TEST`; counts until the next MCU boot | `chassis_icd.md` 3.13; RQ-058 |
| Dynamic brake check (deceleration against the braked model) | the first drop of each mission, and the spin-down once per service interval | firmware check proposed in `chassis_safety_chain.md` section 7; spin-down VT-045 | the stationary test cannot see an open brake path |
| Head rail trip and stroke; side zones; loop 1.00 kohm; PRES_ID 4.70 kohm | after any impact, rail insert change or head repair; interval not defined | head E2, E6 | `mechanical/head/production/README.md` section 9 |
| Head light tightness (E1), film plane (E4), isolation (E7, at least 10 Mohm FRAME to receiver shoes) | after any opening of the lid, spreader, cassette; E7 after any change to the receiver or shoes | head tests | same |
| Dark rate per lane (lid closed), reference health | per shift or per use | 02 section 5 | |
| Torque re-check: M5 grip and M4 receiver after the first -20 C soak; later: not defined | after the first cold soak, then after any impact | `mechanical/prototype_x1c/assembly.md` general rules | printed parts creep |
| Insert pull-out coupons, cold impact coupons | first articles; repeat when the filament lot or process changes | `docs/build/02_printing.md` | IB-55 |
| Grip proof load | first article and after any grip change or heavy impact | 265 N for 60 s, residual under 0.1 mm | VT-002 |
| Cassette latch pull test (100 N on the handle with the plunger engaged); door will not close unless the cassette is home | at assembly and after any cassette or latch change | | body stage 9 |
| Gaskets, RTV beads, vents, drains | at every service opening | visual; vents clear, drain valves intact | `hardware_by_subassembly.md` |
| Desiccant indicator (saddle cover 10 g, head 4 x 0.5 g pouches) | each opening of the cover; change on indicator | | N05; head BOM |
| Connector inspection: J1, J2, J_PWR, SBS50 coupler, inlet; shell shields; strain relief | monthly proposed; after any pull | `harness/` documents | contacts are recalled parts (OI-04 to OI-06) |
| Pack: voltage, temperature, identification, terminal inspection | each swap | 01 section 9 | |
| Wheel run-out (under 0.5 mm radial) and caster | after tyre or rim change, and when a vibration appears | dial gauge | body stage 3 |
| Position of the head relative to the chassis, gap (T10) and calibration standoff | after any head swap or receiver repair | `docs/build/05_first_bench_tests.md` T10 | RQ-015 |
| Software and firmware version record review | each service | section 5 | |

## 2. Wear parts and what is known about their life

| Part | Wear mechanism | Life | Source |
|---|---|---|---|
| Printed TPU tyres | tread wear, contamination, stiffening in the cold | not defined; not assumed below -10 C | body print schedule; IB-55 |
| Caster (TENTE plain bearing, -20 C limit) | bearing, cold | not defined | `parts.yaml`; IB-26 |
| Head leading-rail wear inserts (3 mm / 5 mm projection) | floor contact | print 8 (one spare set); wear rate not defined | head print schedule |
| Side contact strips (0.8 mm 301 stainless, 3 mm or 5 mm variants) | contact | not defined | head BOM |
| Bumper guide screws, sleeves, springs (about 0.5 N/mm); push pins | cycles | not defined | `hardware_by_subassembly.md` G bumper |
| Switches Omron D2HW-C201M (7 plus 4 in the head) | cycles | not defined (the source lists temperature and IP67 verified, no life figure) | `parts.yaml` |
| Brake relays K2, K3 (DPDT) and latch relay K1; photo-MOS | contact wear, welding | **mechanical life 10^6 to 10^7 operations is a recalled figure [U]**; the brake relays do not break more than 2.7 A; a welded K1 contact falls back to firmware (fault rows 39, 40) | `chassis_design_review_checklist.md` D; safety chain |
| Gaskets, RTV, O-ring cord, vents, drain valves | compression set, ageing, contamination | not defined | J seals list |
| Entrance film and cassette | contact, puncture, contamination | not defined; replaced as a cassette | head `production/README.md` section 8 |
| Gearmotors (brushed) | brushes, commutator, bearings | not published by the maker; the motor has no published temperature rating | `electronics/modules/gearmotor_pololu_2828.md` |
| Latent hold elements (U_HOLD, U_LS, D_RUN, RELAY_RTN path, R_RHD, the set-stack parts) | silent failure; D_RUN reverse leakage grows with temperature (the silicon rectifier with a bleed is the stage-4 fix; leakage table at +60 and +85 C, VT-081) | not defined; covered by S4 and S5 | `chassis_safety_chain.md` 6.2; IB-70 |
| Boot counter in chassis flash | one flash page erase per boot | about 10 000 boots | `firmware/chassis/README.md` Known gaps |
| Heater film, bimetal cut-outs, NTCs | thermal cycling | not defined | |
| Cables with repeated flexing: head pigtails and the LAB extension | flex | not defined; strain relief within 40 mm of headers | `harness/README.md` |
| Battery pack | cycle life and calendar | not stated in the sources; pack ID tracked | `battery_pack_and_coupler.md` (R02) |
| Desiccant, tape, foam jacket | consumable | change on indicator | N05 |

## 3. Battery care

- Charge only a pack at or above about +5 C (hardware gate, 01 section 9); a cold pack is warmed first; the BMS accepts charge from 0 to +45 C and discharge from -20 to +60 C (pack datasheet).
- Charge 3.0 A to 14.4 V (3.60 V per cell); the bench charger PSC-124000-LIFE (4 A) has no access to the cassette NTC.
- Keep each pack identified and tracked (R02); one spare pack per robot is the stated minimum for pack-swap surveys; the second pack stays off-board.
- Do not swap a live or cold pack (RSK-017); isolate the load first; remove the pack (that is the isolation).
- Inspect the faston/tab terminals, the cassette leads (AWG 12 silicone), the NTC and presence contacts, EPDM pads and the SBS50 coupler halves at each swap; the coupler is recalled at -20 C only.
- Record deliverable capacity in the cold when measured (VT-040); until then use the assumed 0.80 at -20 C and 0.75 at -25 C only for planning.
- Storage conditions, long-term storage charge, cycle-count limit and end-of-life criterion: not defined in any source. Shipping needs UN 38.3 documentation (open).

## 4. Recommended spares (proposed; only the second pack and the rail-insert set are defined in the sources)

Rationale: the items that wear or get damaged in use, the parts with long or unknown lead time (see `docs/build/01_procurement.md`), and the parts that are difficult to source one at a time.

| Spare | Suggested quantity | Why |
|---|---|---|
| Battery pack PSL-SC-12120 | 1 (defined) | pack-swap surveys |
| Printed tyres, rims, motor pod set | 2 sets of tyres | wear and contamination; 7.5 h per tyre |
| Caster | 1 | |
| Head rail inserts | 1 set (defined: print 8 = one spare set); side strips 1 pair | |
| Entrance films and a spare cassette | 2 films, 1 cassette | window damage; the film changes the response, so a spare film must be the same material |
| Omron D2HW-C201M | 4 | bumpers, rails, dock, cover |
| Bumper springs, guide screws, push pins | 1 set | |
| RR-TOF-A carriers | 2 | the robot has 11; identical boards, individually replaceable |
| RR-PANEL | 1 | |
| Gearmotor Pololu #2828 and hub | 1 each | |
| Gasket stock, RTV, ePTFE vents, drain valves, desiccant | 1 kit | |
| Connectors, contacts, wire and cable of every family with the right crimp tools | per `harness/parts_status.md` once numbers exist | contacts are recalled parts and unverified |
| Fuse(s) | 2 | the main fuse part is not yet selected |
| XB5 control devices (E-stop, REARM, PAUSE, HANDS-ON, selector) | 1 each if their references are stable | chain elements |
| Bimetal cut-outs, NTCs, heater film | 1 each | not yet selected |
| Printed spares of the structural parts in PAHT-CF/ASA | the first-article set | prints are cheap in material (ASA 1510 g, PAHT-CF 228 g per body) and slow (123 h rule of thumb) |
| Spare boards: RR-CHS-MAIN, RR-HEAD-ACQ | 1 each at the first fabrication run | long lead and a layout that is not final |
| SiPM lane | not defined; depends on the optics supplier | RFQ 0.4 |
| ST-LINK, USB-UART, isolated RS-485 adapter | 1 each | service tools |
| Service-test kit: the REARM test plug RTP-1 (bench-built), a DMM with the 2 Mohm range and 10 Mohm DC input, a x10 scope probe, an SWD probe with the test firmware | 1 set | P1 and S3 to S8 (section 6) |
| Spare chain parts: K1, K2, K3 and the photo-MOS relays, U_HOLD, U_LS (TLP241A class) | not defined | a failed S-test withdraws the robot; the parts are on the board and need a rework station |
| Motor-terminal suppression parts (47 to 100 nF, 4.7 to 10 nF, straps) | 1 set per motor | N09 to N11; replaced with any motor |
| G-10 shims, bushings, split pins, spring washers | 1 set per body | the receiver thermal break (DEC-045); creep and re-torque (VT-060) |

A spare that is not identical (a different film, a different tyre, a different switch) is a configuration change.

## 5. Firmware and software updates, and version recording

**What is versioned.** The contract version (`0.4.0-draft7`), the firmware version strings in the boot banners and in `HELLO` (`fw`, `hw_rev`, `serial`, `boot_id`, `proto`), the head descriptor id, `setup_id` (hash of thresholds, trims, pulser, enables, bias set-point and coefficient, heater set-points and the firmware version string), the geometry id, the calibration id, the profile revision, the ROS image tag (`rad-roomba/ros2-ws:0.4`; resolved packages in `ros2_ws/docker/versions.lock`), the repository commit, and the configuration of the chassis (the `CONFIG` keys: `id.*`, `cal.*` wheel radii and track, `caps.*`, `stop.*`, `look.*`, `cliff.*`, `rear.*`, `batt.*`, `temp.*`, `heater.*`, `brake.*`; two alternating flash copies with a layout version, generation counter and CRC; every change is logged as a `CONFIG` event).

**Procedure (proposed; nothing has been tried).**

1. Take the robot out of service: stop, inhibit, head detached or in LAB, no mission running; record the current versions and the `CONFIG` dump (`CONFIG_GET` with `_keys`).
2. Build from a recorded commit with the pinned toolchain: head `pio run -e rr_head_acq`, chassis `pio run -e rr_chs_main` in `firmware/chassis/port/stm32g474` (platform `ststm32` pinned: 19.4.0 for the head, 20.0.0 for the chassis as written in the READMEs; ARM toolchain GCC 12.3.1). Run `firmware/head/check.sh` and `firmware/chassis/check.sh` (the host tests and the emulator tests) and archive the results with the image and its checksum.
3. Flash over SWD (`pio run -e <env> -t upload`, ST-LINK) with the robot unpowered from the pack where possible; chassis: do not hold the MCU halted in a debugger while traction is armed; the hardware latch is open while the MCU is in reset (ARM_PERMIT is low), so a flash cannot arm the robot. The head persists a setup image in the last 2 kB of flash (`ENG_SETUP_SET {"persist":true}`) and refuses to write if the program image reaches it.
4. After a head firmware change: `setup_id` changes (it includes the firmware version), so the binding is invalid and the calibration validity envelope names a `setup_id`; **a new calibration revision or a documented setup-equivalence decision by the site is required** before field use (02). After a chassis firmware change: the brake test, the chain element test (04 section 6), and the stop-distance trials that depend on firmware timing are repeated: the baseline reopens stopping evidence for "firmware timing".
5. Host software update: rebuild the image, run `ros2_ws/tools/test.sh` and the scenarios on the emulators on an idle host (IB-46), check the contract snapshot (`tools/snapshot_contract.py --check`), and update the head registry and site configuration deliberately.
6. Record in the maintenance log: date, operator, commit, image checksums, tests passed, reason, the versions before and after, approving person.

**Updates since the first version.** (1) Head firmware is 0.6.0 (`rr-head-0.6.0`): STATUS now carries `build.build_id` (git commit, `-dirty` if the tree differs), `build.image_crc32`, `proto`, `acq_format` and `identity.cal_id`; record all of them (a CRC-32 is not a cryptographic digest and the build toolchain version is not covered). `setup_id` includes the firmware string, so a head firmware update invalidates the binding and the calibration validity (02: a calibration is bound to serial, electronics revision, firmware and `setup_id`). The per-board BIAS_VMON ratio and the calibrated flag are stored in the non-volatile setup but are not in `setup_id`; they are identified by `cal_id`. (2) Chassis firmware is the stage-5 firmware: its tests must be re-run after any change (`firmware/chassis/check.sh`: 337, 1195, 65, 65, 2476 checks and 10 integration tests on 2026-11-28), and the dynamic deceleration check and the boot watchdog self-test are not implemented. (3) **JP1 stays open** (WDO does not reset the MCU; the IWDG still does) until the first-strobe timing after reset is measured; after any change that touches boot, the HSE start-up or the I2C probes, repeat the measurement of VT-055 before closing JP1. (4) After any chassis firmware change repeat the chain checks that depend on it: the brake test, the loop self-test and the REARM behaviour (VT-080). (5) The host must not resume motion by itself after a hardware inhibit, FAULT or reset (`chassis_icd.md` section 9, VT-067).

**Host-side items that changed in the finished firmware and must be matched before using it with the workspace** (IB-59, IB-60): new DIAG lane members `alpha_idle_clears` and `imon_na`, STATUS members, health code `BIAS_PERMIT`, new setup members that enter `setup_id`, `DIAG.bumper_zones` null, DIAG reply length 1404 bytes; for the chassis `STATE.chain` false meaning open or unknown, the new ToF ids and index order, the 23-character `readbacks`, new fault flags, renamed `look.*` keys, and a `BRAKE_TEST` that takes about 2.2 s (the host reply timeout must be at least 3 s).

**Software bring-up caveat.** The web service is HTTP-only with demonstration accounts; replace the accounts file before any field use (`users:=` launch argument) and do not expose the service beyond the robot's isolated network.

## 6. The chain checks: per-shift P1 and six-monthly service tests S3 to S8

Source: `electronics/analysis/chassis_safety_chain.md` section 6.2 and `electronics/analysis/chassis_braking_tables.md` table T15 (stage 5, written for the independent stage-4 review finding S1: every test must work on the assembled robot). Evidence class: **calculated**. **Nothing here has been done on a board.** The pass and fail bands are calculated from 1 % resistors and a 1 % meter; **some are close together** (read from the table: the D_RUN healthy band starts at 476 kohm and the shorted band ends at 449 kohm, a gap of about 6 % of the reading; for U_LS the gap between the band edges 224 and 252 kohm is about 11 %; the lead's summary of the source is "some only 10 to 15 % apart"), so a loose meter, a damp board or a different test voltage can mislead, and **the resistance bands assume that the meter's lowest-voltage resistance range keeps the tap clamp diodes off (node voltages under 0.2 V): UNVERIFIED for the meter in use.** Record the meter model and its test voltage with every reading, and calibrate your own healthy readings on the first good board; a reading that falls between the healthy and fault bands is a fail, not a pass. The hazard owner's disposition of the residual single faults and the reachability of the service-pad array inside the body are open (IB-74); until the lead records that the pads are reachable, the tests below cannot be done on a built robot.

**What the tests are for.** The latent faults are single faults that leave one barrier and that nothing in operation shows: a shorted U_HOLD, U_LS or D_RUN, the RELAY_RTN path to ground, an open R_RHD, set-stack faults (Q_SETA, Q_SETB, Q_SETC, C_SC, R_SG, Q_SDIS), an open brake path, a clamp Zener fault, a stuck nSLEEP gate, the plug and inlet channels. The shorted loop photo-MOS cases are tested automatically at every arming (loop self-test) and are not on this list. A stationary brake test does not see an open brake path; S7 does.

**Instruments (all named in the source):** a DMM with a 10 Mohm DC input and a 2 Mohm resistance range (+-1 %); the REARM test plug **RTP-1** (a CLIK-Mate 8-way to the J_BTN connector with two separate push buttons, SET on pins 1-2 and AUX on pins 3-4, lamp pins open; bench-built); an SWD probe with the test firmware (S6); a scope with a x10 probe (S7); the charge plug (S8).

**Pads.** The ten top-side service pads SVC1 to SVC10 (TP63 to TP72, a 2 x 5 array at 2.54 mm at board position (128 to 138, 78 to 81)), each behind 220 kohm 1 %: SVC1 GND, SVC2 CHAIN_END, SVC3 K1_RUN, SVC4 RUN_HD, SVC5 RUN_12V, SVC6 RELAY_RTN, SVC7 HOLD_A, SVC8 LS_A, SVC9 CH_N6A, SVC10 SET_CAP. A slip is safe by calculation: any pad to 14.6 V drives at most 66 uA into its node and any two pads shorted at most 33 uA, which can neither hold K1 (1.16 mA must-release at -25 C), light a photo-MOS LED nor pick up a relay.

### 6.1 P1, every shift (operator, about 2 min, robot complete)

| Step | Action | Pass | Fail |
|---|---|---|---|
| P1.1 | Arm. Press the E-stop, release it, re-arm when the REARM lamp says ready | the latch drops (ESTOP shown); re-arm only after "ready" | the robot stays armed, or `ESTOP_DISCREPANCY` |
| P1.2 | Press and hold HANDS-ON | lamp lit and latch drops | lamp dark: **do not work at the wheels** |
| P1.3 | Press each body bumper and each head-rail zone in turn, re-arming between | the latch drops and the element is named | no drop: a welded switch; stop and report |
| P1.4 | Selector to SERVICE, then back to RUN | MODE_RUN shown open in SERVICE | not shown: use OFF, never SERVICE, for any work at the wheels |
| P1.5 | Press REARM briefly (well under 5 s; the buzzer sounds from 1 s of holding) only when the lamp says ready | arms | `REARM_REFUSED`: note the reason (01 section 4) |

P1 is the only check of the single-channel elements (selector RUN contact, HANDS-ON, E-stop poles, bumpers, rail zones); a welded rail switch or bumper is not detectable any other way.

### 6.2 S-tests, every 6 months (service cover off, wheels off the ground, record every reading)

| Test | Fault covered | Conditions | Pads and action | Pass (healthy) | Fail (fault) |
|---|---|---|---|---|---|
| S4a | U_HOLD output short (#39) | pack removed, charge plug out, E-stop released | resistance, red lead SVC3, black SVC4 | 593 to 617 kohm (605 nominal) | 431 to 449 kohm |
| S4b | Q_HSET short, set stack stuck on, HOLD_A or HSET_D on a logic supply | pack fitted, selector RUN, latch down | DC volts SVC7 to SVC1 (the 220 kohm reads 2.2 % low) | under 0.05 V | 1.05 to 1.28 V (U_HOLD LED lit) |
| S5a | U_LS short, RELAY_RTN to GND (#53) | pack removed | resistance SVC6 (red) to SVC1 | 252 to 262 kohm (257) | 216 to 224 kohm (220) |
| S5b | D_RUN short (#52) | pack removed | resistance SVC5 (red) to SVC4 | 476 to 495 kohm (486) | 431 to 449 kohm (440) |
| S5c | R_RHD open (#52) | pack removed | resistance SVC4 (red) to SVC1 | 224 to 233 kohm (229) | 283 to 294 kohm (288) |
| S5d | LS_A on a logic supply | pack fitted, RUN, latch down | DC volts SVC8 to SVC1 | under 0.05 V | 1.05 to 1.28 V (U_LS LED lit) |
| S3 | set stage: Q_SETA, Q_SETB, Q_SETC, C_SC, R_SG, Q_SDIS, Q_SDISB, C_SDB (#45 to #49) | pack fitted, RUN, chain closed, **W-018 unplugged**, RTP-1 on J_BTN, DMM on SVC10 (SET_READY at 10.57 to 10.99 V at the cap, 10.34 to 10.75 V at the pad) | a) SET alone while SVC10 is at or above 10.6 V; b) AUX alone held 1 s; c) SET and AUX together within 1 s of chain closure (SVC10 below 10.3 V); d) SET and AUX together with SVC10 at or above 10.6 V; e) E-stop pressed for 1 s; h) SET held alone 0.5 s, then AUX | a) and b): no set; c) no set and SVC10 keeps rising; d) sets; e) SVC10 below 0.5 V; h) no set | a) sets: Q_SETB short; b) sets: Q_SETA short; c) sets or SVC10 drops: Q_SETC short or SET_READY stuck; d) no set: set stage faulty; e) over 1 V: Q_SDIS open; h) sets: C_SC short or R_SG open |
| S6 | U40/Q23/U23 watchdog element (#33) and the nSLEEP gate U9 (#68) | JP1 open, test firmware | stop the strobe: WDG_OK_RB and CH_N9 must fall within 35 ms; with the latch down and DRV_NSLEEP high, U5/U6 pin 3 (nSLEEP, top side) must stay low | as stated | CH_N9 stays live: U40, Q23 or U23; nSLEEP goes high: U9 |
| S7 | braking: K2/K3 brake path open or degraded, clamp Zener short or open (#60, #61, #63 to #65) | wheels free, scope with a x10 probe on SVC4/SVC5 (220 kohm with the probe: under 5 us) and a K2/K3 NC pin | open each element; spin-down warm and cold | RUN_HD falls in under 1 ms; NC closed within 10.8 ms; spin-down tau at most 2 x the commissioning value | slower: clamp or relay; tau high: brake path |
| S8 | plug link and inlet channels (#13, #15) | charge plug | `chassis_safety_chain.md` section 8 step 5 | CH_N4 falls with the link and with 24 V on the inlet | no fall |

Resistance readings: pack removed, charge plug out, E-stop released, DMM on the 2 Mohm range, red lead on the first pad named. **Never press the REARM button or operate RTP-1 on a robot whose pack is fitted unless the step says so.** A failed S-test means the robot is withdrawn from service until the fault is found; do not repeat the test hoping for a pass.

Not testable at the chassis (stated limits, section 6.1 of the chain analysis): a welded head-rail switch or head-internal bypass, a leak from LOOP_SNS to a supply, a board short of RUN_HD, K1_RUN or CHAIN_END to a supply (detected, bridges asleep). Not implemented: the boot watchdog self-test and the dynamic brake check (S6 and S7 substitute at service time).

## 7. Open items

| Item | ID | Status |
|---|---|---|
| Service intervals and measured wear lives | not yet defined | no backlog ID |
| Relay contact life (recalled 10^6 to 10^7 operations) | `chassis_design_review_checklist.md` D | UNVERIFIED |
| Battery storage, cycle life, end-of-life criterion; UN 38.3 | `battery_pack_and_coupler.md` | open |
| Spares quantities (only the second pack and rail inserts are stated) | not yet defined | proposed above |
| Whether a firmware update with an unchanged `setup_id` reasoning is acceptable to the site | 02 | site |
| Crimp tools and extraction tools | IB-35 | open |
| Configuration control: which maintenance actions reopen which VT | baseline chapter 09 | lead to define a table |
| Remote or wired service path (Wi-Fi only on rev A) | IB-07 | decided for rev A |
| Service-test bands calculated; some 10 to 15 % apart; the meter's test-voltage assumption UNVERIFIED; no certified proof-test interval | IB-74, `chassis_braking_tables.md` T15 | open |
| Reachability of SVC1 to SVC10 in the body; RTP-1 has no drawing or parts list | IB-74 | open |
| Hazard owner's disposition of the residual single faults | IB-16, IB-71 | open |
| Thermal: receiver thermal-break creep, G-10 data, pack-to-body coupling | VT-058, VT-059, VT-060 | pending |
