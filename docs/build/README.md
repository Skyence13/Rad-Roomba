# Rad Roomba build documents (design 0.4, draft)

For the person who will procure, print, assemble, bring up and test the first prototype largely alone. These documents tell you which source file to follow, in what order, and where to stop. They do not replace the subsystem documents and they never state a result that does not exist.

**Nothing in this project has been built, printed, ordered or measured.** Every figure is `calculated`, `simulated`, `tool-checked`, a `design value`, `assumed` or `UNVERIFIED` (recalled, not confirmed against a manufacturer document). Where a source lacks a needed fact the file says "not yet defined" and lists it in its "Open items" section with the backlog (IB-xx), verification (VT-xxx), risk (RSK-xxx) or requirement (RQ-xxx) identifier if one exists.

The authoritative list of known open items is `docs/architecture/INTEGRATION_BACKLOG.md` (IB-01 to IB-75 when this was written, 2026-11-28; it states what is closed, open and in progress). Read it with these documents.

| File | Content |
|---|---|
| [01_procurement.md](01_procurement.md) | what to buy from which document; how many part numbers are verified, recalled or not selected; "order now / after verification / cannot order yet"; lead-time-critical items |
| [02_printing.md](02_printing.md) | printing the body and head on a Bambu Lab X1 Carbon: files, materials, stated settings, inserts, first-article coupons, pre-assembly measurements |
| [03_assembly_and_wiring.md](03_assembly_and_wiring.md) | order of assembly across subsystems with hold points (continuity, polarity, isolation, chain wiring) |
| [04_bring_up.md](04_bring_up.md) | staged electrical and firmware bring-up, supply limits, rail values, programming, emulator-in-the-loop, hardwired chain tests, first motion, head attach/binding, and what must be true before the robot moves near a person |
| [05_first_bench_tests.md](05_first_bench_tests.md) | observation sheets T1 to T11 (SiPM bias and dark scan, beta yield, alpha/beta, live time, motor pickup B11, heater, cold box, stop distance, ToF, head gap, link errors) |

Operation, calibration, cleaning, fault isolation and maintenance are in [../service/README.md](../service/README.md).

## State of the design, 2026-11-28 (what is verified by which command, what is open, what you can do now)

Read this table with `docs/architecture/INTEGRATION_BACKLOG.md`. "Verified" means a tool, test or build the lead or the engineer reported as passing: **none of it is a physical measurement**. The commands are the top-level `Makefile` targets (`make help`; `make check-fast` about 3 min; `make check` adds radiometry, small boards, mechanical and robot software; the large-board target exits non-zero by design).

| Subsystem | Verified by (evidence class) | Open (backlog) | Owner can do now | Must wait |
|---|---|---|---|---|
| Registers: 56 decisions, 110 requirements, 81 verification tests (all pending), 59 risks, BOMs, RFQ | `make registers` (checker "ALL CHECKS PASS", `tool-checked`) | 19 tests have "criterion not yet defined" with a named owner; site decisions DEC-001/002/012/015; contradictions C-01..C-16 (IB-71) | read; use as the record; order parts from the BOM lines marked VERIFIED | nothing blocks reading |
| Chassis firmware (stage-5 chain, REARM, brake test) | `make firmware-chassis`: test_chain 337, test_state_machine 1195, test_review 65, test_rearm 65, test_drive 2476, 10 integration tests, both STM32 images (`simulated`/`tool-checked`; never run on hardware) | VL53L4ED driver stub (IB-04); LTC4162-F driver disabled (IB-06); boot watchdog self-test and dynamic brake check not implemented; JP1 open until VT-055 (IB-74, IB-60) | build and run the emulators and ROS simulation; program a NUCLEO-G474RE for protocol work | any motion on hardware (ToF driver); charger |
| Head firmware 0.6.0 (device type before ARM, time-over-threshold cut, per-gate stats, heater over-current, frame monitor) | `make firmware-head` (host tests under ASan/UBSan, emulator interoperability, STM32 image; `tool-checked`/`simulated`) | thresholds and alpha cut `assumed`, must come from Am-241 and Sr-90 histograms; waveform capture not in the port; IB-58 (monitor injection, dead-channel detection at -25 C) | as above | all detector tests (no optics, no boards) |
| Radiometry: MODEL.md revision 5, detectability study | `make radiometry` (unit tests, tables, figures; `calculated`, synthetic coefficients) | no measured coefficient; validation limits (MODEL section 9); K depends on the site's meaning of 1 Bq/cm2 | read; rerun | any detection-capability claim |
| Robot software (ROS 2 workspace, operator page) | `make ros-unit ros-scenarios` (Docker; `simulated`); revision-5 items written and unit-tested | revision-5 implementation in progress; full scenario and native runs pending; plain HTTP and demonstration accounts; serial transports and stand-alone nodes untested (IB-49, IB-72, `ros2_ws/STATUS.md`) | run the simulation | field use; hardware links |
| Harness | `make harness` (generator and cross-check: PASS, 0 errors at the last read; `tool-checked`) | no part number for wire, cable, coax, fuses, heater films, cut-outs, NTCs, lid switch, inlet, tools (IB-35); lead lengths from real routes in progress (W-104 112 mm against 90, W-105 329 against 270, W-106 319 against 280, W-107 150 against 200: IB-75); heater AWG 20 contact rating UNVERIFIED (IB-69) | read; prepare the build record | cutting wire |
| Small boards: RR-TOF-A, RR-PANEL | `make boards-small` (ERC 0/0, DRC 0/0, parity 0; `tool-checked`) | VL53L4ED ordering code unchecked; panel hole positions and cable exit unconfirmed | order bare RR-TOF-A; RR-PANEL after the hole check | assembly of the ToF boards (driver) |
| Large boards: RR-CHS-MAIN, RR-HEAD-ACQ | `make boards-large-noroute` (netlist, ERC, placement; chassis DRC 0 errors and parity 0; `tool-checked`); **not routed**: chassis about 1260 connections open, head 1468 | routing; placeholder land patterns (IB-43, IB-53); IB-06; head front-edge connectors do not fit (CR-H17, IB-75); layout-engineer review (VT-048); hazard-owner disposition of the residual chain faults (IB-16, IB-74); service-pad reachability (IB-74) | review the schematics and the chain analysis | fabrication; every electrical bring-up stage |
| Traction chain (analysis, firmware) | three independent reviews (`docs/reviews/REVIEW_traction_inhibit*.md`); stage-5 netlist and firmware (`simulated`); not a certified function | latent-fault control depends on service tests S3 to S8 not yet reachable in the body; residual single faults with no barrier (04 section 6c); no hardware speed or force limit, no holding brake; re-arm needs 11.7 V | read 04 section 6; prepare RTP-1 | everything on hardware |
| Body (prototype RR-X and production RR-P) | `make mech-prototype mech-production mech-common` (build exit 0, checks pass: `tool-checked`) **but the independent fit review found neither body assemblable as modelled** (IB-73: main-board fastening, thermal-break screws, ToF seats, grommets, service access, cable routes) | rework in progress with the J1/J2 receptacle re-orientation (IB-75); production body supplier capability UNVERIFIED (IB-68); Pause/Stop depth (IB-65) | print coupons and the fit-check parts of 02 section 4 | printing and fabricating body parts for assembly; assembly |
| Head mechanical | `make mech-head` (lead-verified 2026-11-28: 51 pass, 0 fail, 5 deviations; `tool-checked`) | front-edge board connectors do not fit (CR-H17); pigtail boots and receptacle orientation (IB-75); contract height exception for boots and holsters pending | trial frame halves only (02 section 4) | head build; fabricated head parts |
| Detector optics and SiPMs | RFQ rewritten (18 p.e. at the MIP MPV, ZnS decay, SiPM type); no supplier response | everything (RSK-019) | send the RFQ | T1 to T3, T5, T12, T13 |
| Thermal | contract draft11 `thermal_policy` (head +5 C; bay hold at least -10 C on pack power; pre-heat to +5 C on external power); `calculated` | head heater short of capacity at 10 V in moving air at -25 C; bay pre-heat 95 to 200 min with an assumed coupling; thermal-break conductance, G-10 data UNVERIFIED (IB-62, IB-64; VT-057 to VT-060) | nothing physical | cold trials |
| Braking, personnel protection, cold, radiometric trials | none run; all VT pending | VT-003, 004, 005, 035, 013, 015 to 018, 032, 045 and the new VT-049 to VT-081 | prepare fixtures | the robot may not move near a person (04 section 9) |

**Summary for the owner.** *Order now:* the VERIFIED purchased parts (pack, caster, motors, hubs, switches, E-stop), standard fasteners, filament and coupon material, bare ToF boards, development boards and adapters, the test equipment of 01 section 9; send the optics RFQ. *Print now:* coupons and the fit-check or trial articles of 02 section 4 only. *Assemble now:* nothing of the robot; bench work only once parts and part numbers exist. *Test now:* the software and emulators (04 stage S0, emulator-in-the-loop arrangements), coupons, and nothing electrical on hardware until the large boards exist. Everything else waits for the items in the last column.

## Order in which to read and work

1. `docs/architecture/SYSTEM_ARCHITECTURE.md` and `interface/system/contract.yaml` (the contract wins over the architecture text), then the backlog.
2. 01, then start the long-lead actions (the optics request for quotation can be sent; no response exists).
3. 02 while parts arrive; 03 and 04 in parallel for the head and chassis benches; 05 as the detector lane and boards become available.
4. Software-only work (04 stage S0) can start now.

## Evidence classes

| Class | Meaning |
|---|---|
| `calculated` | closed-form or script result from stated inputs |
| `simulated` | result of running firmware or software on a plant or emulator |
| `tool-checked` | result of a tool (CAD kernel, ERC/DRC, compiler, unit test) on the design files |
| `design value` / `assumed` | a number chosen for the design, not derived or measured |
| `UNVERIFIED` | recalled from memory, not confirmed against a manufacturer document |
| `pending` | a verification test (VT-xxx) not yet run; **all** are pending |

Pending trials that remain visible throughout: **cold** (-20 C warm-start, -25 C objective), **braking** (stop distances), **personnel protection**, **radiometric** (calibration, detection capability). The register now holds 81 verification tests, VT-001 to VT-081, **all pending**.

## Things that apply to every file

- Not a certified safety system. The hardwired traction chain, the contact rails and the software stops are design intent; see 04 section 9 for the limits.
- Both large boards (RR-CHS-MAIN, RR-HEAD-ACQ) have schematics and placement and are **not routed** (chassis about 1260 connections open, head 1468); the ToF carrier and the panel board are complete. Both large boards need a layout engineer's review before fabrication.
- First motion on hardware is blocked by the VL53L4ED driver stub (IB-04).
- **Neither body can be assembled as modelled (fit review, IB-73); the rework is in progress.** The mechanical packages (`mechanical/common`, `mechanical/prototype_x1c`, `mechanical/production`, `mechanical/head`), the ROS workspace and `tools/eda` keep changing. Quote numbers only with their source file, and re-read the source before relying on a number here.
- Identifiers carried forward from the 0.3 baseline are kept: requirements RQ-001..051 and the new RQ-052..083, tests VT-001..035 and VT-036..048, risks RSK-001..040, decisions DEC-001..044, delivery gates G0 to G4 (`docs/Rad_Roomba_Design.pdf` chapter 09), the 0.3 survey sequence (chapter 02 "Normal survey sequence", steps 1 to 6) and the field worksheet `planning/Survey_Field_Checklist.md`.

## Mapping to the baseline delivery gates (0.3)

| Gate | Evidence required (baseline) | Where in these documents |
|---|---|---|
| G1 independent benches | base stops safely on the ground rig; detector bench yields counts, stability and photon-matching evidence; emulated and physical records decode against the same schema; single-segment evidence supports the decision to purchase four | 04 (stages B, M), 05 (T1 to T6, T8, T11) |
| G2 integrated guarded mock | documented stopping margin in all enabled directions; mechanical and electrical review closes interference, connector, window and power issues | 03, 04 sections 8 and 9, 05 (T8 to T10) |
| G3 environmental and radiometric | operating envelope, moving sensitivity and uncertainty, worst stop margin, usable runtime | 05 (T7), service documents; all pending |
| G4 controlled site pilot | site approval of permitted use | not covered; site and radiation protection |
