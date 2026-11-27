# 05 Maintenance and spares

**Status.** No part has worn, failed or been serviced. Intervals are **not defined in any source** except where quoted; the schedule below is a set of proposals built from the design documents, to be replaced by measured wear. Evidence classes as in `docs/build/README.md`. Every maintenance action that touches the traction chain, the head rail or switches, the brakes, the tyres, the motors, the sensors' positions or the firmware timing reopens stopping or coverage evidence (0.3 baseline, `docs/Rad_Roomba_Design.pdf` chapter 09 "Configuration control and handover"): record it and decide with the lead which trials to repeat.

## 1. Periodic checks (proposed intervals)

| Check | Interval | Method | Source of the check |
|---|---|---|---|
| Pre-use set (local stops, head identity, source check, window, tyres, caster, pack) | every shift | 01 section 3 | field checklist |
| Chain element actuation: E-stop, HANDS-ON, each rail zone, bumper segments, dock switch, cover switch, selector, REARM | every shift (pre-use); full element-by-element test after any repair of the chain | `docs/build/04_bring_up.md` section 6 | VT-039 |
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

**Host-side items that changed in the finished firmware and must be matched before using it with the workspace** (IB-59, IB-60): new DIAG lane members `alpha_idle_clears` and `imon_na`, STATUS members, health code `BIAS_PERMIT`, new setup members that enter `setup_id`, `DIAG.bumper_zones` null, DIAG reply length 1404 bytes; for the chassis `STATE.chain` false meaning open or unknown, the new ToF ids and index order, the 23-character `readbacks`, new fault flags, renamed `look.*` keys, and a `BRAKE_TEST` that takes about 2.2 s (the host reply timeout must be at least 3 s).

**Software bring-up caveat.** The web service is HTTP-only with demonstration accounts; replace the accounts file before any field use (`users:=` launch argument) and do not expose the service beyond the robot's isolated network.

## 6. Open items

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
