# 03 Assembly and wiring: order across subsystems, with hold points

Nothing has been assembled. This file fixes the order in which the subsystem documents are used and where work stops until a check passes. It does not repeat the detailed procedures. The order is **proposed**: the subsystem documents are individually written, but no source sequences them against each other, and the board bring-up placement (before or after installation) is my proposal.

**Status 2026-11-28: neither body can be assembled as modelled, so no assembly phase of the robot is released.** The fit review (`docs/reviews/REVIEW_cad_pcb_harness_fit.md`, IB-73, IB-75) found, tool-checked on the STEP and KiCad files: the main board cannot be fastened (bridge posts 1.0 mm from the board holes, nut inside the post, a screw head over a standoff, pan heads under the PCB); the receiver thermal-break screws collide with the motor pods and lower hull, and the "re-torque after the first thermal cycle" step cannot be done; the ToF carrier does not fit the four look-sensor seats; the plate grommets are blocked by the motor cans; the main board cannot be removed through the 102 x 150 mm service opening; the J_PWR plug cannot be unplugged by hand; the carrier boxes in the CM5; 30 of 41 robot cable paths cross solids; the docked J1/J2 pigtails pass through the hull and cannot make their bend in the 4 to 11 mm gap; and 8 of 11 ToF carriers need the shell opened. Rework is in progress with a re-orientation of the J1/J2 receptacles; the head's front-edge board connectors also do not fit (CR-H17). **The stage numbers, torques, posts and hold points quoted from `assembly.md` below are those of the pre-rework model; when the lead records the rework as verified, regenerate and read `mechanical/prototype_x1c/assembly.md` again.** What can be assembled now is limited to bench work: board-level bring-up when boards exist, harness sub-assemblies on the bench (W-002 cassette wiring, LAB extension, head pigtails), the head's mechanical sub-assemblies that the rework does not touch, and the mechanical trials of [02_printing.md](02_printing.md) section 4.

Detailed documents (read each in full before starting its phase):

| Subsystem | Document | Content |
|---|---|---|
| Chassis body | `mechanical/prototype_x1c/assembly.md` (stages 1 to 10, generated, with `img/`) | order, torques, harness routing per stage, a "check before the next stage" per stage |
| Hardware lists | `mechanical/prototype_x1c/hardware_by_subassembly.md`, `purchased_and_fabricated.csv`; joints `mechanical/prototype_x1c/joints/README.md` | every screw and torque |
| Harness | `harness/README.md` "Build order for the technician" (steps 1 to 11); `harness/cables.md` (58 assemblies, 284 wires); `harness/connectors.yaml`; `harness/pin_views.md` | wire by wire; **pin positions and key orientations are conventions, UNVERIFIED (IB-35)** |
| Head | `mechanical/head/prototype/assembly.md` (steps 1 to 9 and end-of-assembly checks); `mechanical/head/production/README.md` sections 4, 8, 9 (tests E1 to E8) | |
| Head board bring-up | `electronics/head_acq/design/layout_guidance.md` section 7 | see [04_bring_up.md](04_bring_up.md) |
| LAB extension | `harness/lab_extension.md` section 7 (acceptance test) | optional for first assembly |

The head and body mechanical packages were still changing when this was written (grip bar to x = -30, Pause/Stop envelope, head board change requests). If a generated assembly document and this file disagree on a step, the generated document wins; tell the lead.

## 1. Preconditions (no assembly before these)

| Precondition | Source | State today |
|---|---|---|
| Parts received and incoming-inspected; printed parts first-articled | [01_procurement.md](01_procurement.md), [02_printing.md](02_printing.md) | nothing ordered |
| RR-CHS-MAIN populated (installed in stage 5) | IB-42, IB-43, IB-06 | cannot be made yet |
| RR-HEAD-ACQ populated (installed in head step 5) | IB-51, IB-52 | cannot be made yet |
| Optics lane(s) and SiPMs | RFQ 0.4 | no supplier |
| Wire, contacts, connectors with part numbers | IB-35 | no part numbers |
| ST VL53L4ED driver (for any motion on hardware) | IB-04 | stub |

Until the boards exist, the mechanical stages 1 to 4 (plate, hull, drive, battery bay) and the head mechanical stages (frame halves, rails, switches) can proceed with the dummy head and with envelopes; stages that need a board wait.

## 2. Order of work

| Phase | Work | Document | Hold point on exit |
|---|---|---|---|
| P0 | Incoming inspection; first-article coupons | 01, 02 | HP-0 |
| P1 | Board bench bring-up before installation (proposed) | [04_bring_up.md](04_bring_up.md) stages B1 to B6 | HP-B (boards pass) |
| P2 | Chassis stages 1 to 4: plate with receiver channels and dock switch, lower hull, drive (motor pods, wheels), battery bay with fixed coupler half and heater | body `assembly.md` stages 1 to 4 | HP-1 to HP-4 |
| P3 | Cassette wiring and pack-side polarity (bench, off the robot) | `harness/README.md` step 2 | HP-5 |
| P4 | Stage 5: grip feet and side plates, bridge posts, RR-CHS-MAIN, CM5; board connectors in the stated order | stage 5 and harness steps 3 to 10 | HP-6, HP-7 |
| P5 | Stages 6 to 9: nose and J1/J2 receptacles, lid with controls and sensors, cheek fairings with the forward look sensors and grip bar, cassette and bumper | body stages 6 to 9 | HP-8, HP-9 (proof load) |
| P6 | Head build on its own bench: frame, shoes, rails, switches, lane kits, spreader, board, lid, cassettes | head `assembly.md` steps 1 to 9; head board bring-up per layout_guidance first | HP-10, HP-11 |
| P7 | Head-to-robot interface: dock, J1/J2 mate, loop and presence, isolation | stage 10; head checks 3 to 5; E6, E7 | HP-12, HP-13 |
| P8 | Electrical power-up of the assembled robot per [04_bring_up.md](04_bring_up.md) | | per that file |

Why the boards are tested before installation (proposed): in stage 5 the board sits on a bridge tray under the grip saddle; replacing it later means removing the saddle cover and unplugging about 30 connectors. The hardwired-chain procedure `chassis_safety_chain.md` section 8 is written for a bench with wheels off the ground and temporary devices ("all field devices connected and in their run state") and can be done with the devices in a test loom. The final chain test is repeated on the assembled robot because that wiring is what the operator uses.

## 3. Hold points

A hold point means: stop, record the reading in the build record, continue only on a pass. A failure that is not explained is not repaired in place; stop and report. Readings are recorded, not just ticked.

| ID | When | Check | Pass | Source |
|---|---|---|---|---|
| HP-0 | After printing | insert hole sizes, bounding boxes, joint fit, head light test | section 8 of 02 | 02 |
| HP-B | Before installing either large board | all bring-up stages B1 to B6 for that board pass | see 04 | 04 |
| HP-1 | End of stage 1 | 16.00 x 14.00 x 70 mm gauge bar slides the full length of each channel: left no perceptible y shake, right 0.6 mm total y float; 0.06 mm feeler fits under the roof pad, 0.12 mm does not; X-stop faces coplanar within 0.05 mm; dock switch clicks in the last 1.5 mm of gauge travel (continuity meter) | as stated | body stage 1 |
| HP-2 | End of stage 2 | underside flush with the plate (no step above 0.3 mm); lower land at z = 61.9 continuous across the four pieces, gap at most 0.3 mm | as stated | stage 2 |
| HP-3 | End of stage 3 | wheels spin freely by hand; tyre run-out under 0.5 mm radial (dial gauge); both tyre bottoms and caster wheel on a surface plate within 0.3 mm | as stated | stage 3 |
| HP-4 | End of stage 4 | empty cassette slides in and out with no binding; key rib reversed is blocked at the gate; coupler halves mate by hand | as stated | stage 4 |
| HP-5 | Before the pack is ever mated | with a meter and **no pack on the coupler**, check cassette-side polarity against `connectors.yaml` CPL-C: pack positive to the contacts that reach J_PWR pins 1/2 and negative to pins 5/6; NTC and presence-link contacts on J_PAUX pins 1/2 | polarity correct; no short between + and - | `harness/README.md` build order step 2 (J_PWR and J_PAUX assignment from `electronics/modules/battery_pack_and_coupler.md`) |
| HP-6 | After the harness is built, before power | unpowered continuity of every wire against `cables.csv`; four-wire resistance of the pack feed and the heater branches (record the real values; the power budget assumes 5 mohm per contact pair, not yet measured, OI-18); then chain continuity of `chassis_safety_chain.md` section 8 step 1: each switch loop under 1 ohm; CH_N0 to ground over 50 kohm; COIL_RTN to ground under 1 ohm with the E-stop released and open with it pressed; K2/K3 motor terminal A to B about 0.7 ohm (1.0 ohm brake resistor in parallel with the winding); motor terminals to bridge outputs open | as stated | harness step 10; safety chain section 8 step 1 |
| HP-6a | After W-018 is routed (REARM cable) | continuity pin to pin; insulation between all six conductors (label W-018.ISO); no supply conductor between the two contact pairs; W-018 is a bundle of three twisted pairs and a crush that shorts pairs is a stated residual fault | as stated | `harness/cables.md` section 8; `chassis_safety_chain.md` section 6.1 item 5 |
| HP-6b | Motors fitted | motor-terminal suppression at each motor (C_X across the terminals, C_Y from each terminal to the can, leads at most 5 mm, can strap at most 30 mm): can to chassis plate under 0.1 ohm (four-wire); capacitances within -20 to +20 % of nominal measured with the capacitors disconnected during assembly; motor terminals to can insulated (over 10 Mohm at 50 V with the Y capacitors disconnected); keep the motor cable path at least 50 mm from the head pigtail path (calculated 55 and 54 mm) | as stated; bond to the Pololu can UNVERIFIED | `harness/cables.md` section 7; labels W-006.SUP, W-007.SUP |
| HP-7 | Stage 5 | board lies flat on the six spacers (no rocking); continuity from the board mounting holes H1 and H3 to the chassis plate under 0.1 ohm; grip side plates vertical within 1 degree | as stated | body stage 5 |
| HP-7a | Stage 5, power wiring | insulation between each chain node (CH_N0 to CH_N9) and +12 V on the dry board: over 10 Mohm (a damp-board repeat belongs to the cold/humid trials) | 10 Mohm | `chassis_design_review_checklist.md` F (humid return); proposed for the dry case |
| HP-8 | Stage 6 | with a head or the 16 x 14 shoe gauge bars plus a latch keeper dummy, the draw latch closes with a clear over-centre snap; a 45 mm glove ring round each coupling nut is free | as stated | body stage 6 |
| HP-9 | Stage 8 | **grip proof load (VT-002):** hang 3 x 9 kg = 265 N on the bar centre over 100 mm for 60 s; no permanent set at the side plates, feet or plate (dial gauge on the plate edge under 0.1 mm residual). Before any carry with a head fitted: the bar position is moving to x = -30 (CR-04, DEC-042); use the as-built position of the part you built | as stated | body stage 8; VT-002 |
| HP-9a | Stage 9 | door will not close unless the cassette is fully home; cassette does not move at 100 N on the handle with the plunger engaged; each bumper segment trips its D2HW within 2 to 6 mm and returns; 8 mm free stroke | as stated | body stage 9 |
| HP-10 | Head: head board alone | bring-up steps 0 to 13 of `layout_guidance.md` section 7 pass, **before** the board is fitted in the head | see 04 | head layout guidance |
| HP-11 | End of head assembly | rail trip at most 2.0 mm and at least 15 mm after trip (calculated 1.13 / 1.38 trip, 15.6 stroke); side zones trip before the 0.95 mm stop; HEAD_LOOP across J1 pins 5/6 reads 1.00 kohm +-1 % and opens when any zone is pressed; PRES_ID 4.70 kohm pin 7 to pin 2; film plane 10.00 +-0.30 mm at the four outer corners on the bench cradle | as stated; the 15 mm after trip is `calculated` only | head `assembly.md` end checks; E2, E4, E6 |
| HP-11a | After closing the head lid | E1 dark-count light tightness (lit / dark ratio at most 1.05, 10 min dark counts per channel) before any source run | proposed acceptance | head E1 |
| HP-12 | Head docked or on the bench with the receiver metal contacted, **J1 and J2 unmated, chassis unpowered** | **E7 (harness label): frame (spreader) to receiver metal, 100 V DC, at least 10 Mohm**; head checklist E2 / harness label W-103.HTR-ISO on the assembled head with the board disconnected: heater circuit (J2601 pins 1, 2, 3 and NTC pins 4/5) to FRAME and to GND at least 10 Mohm at 100 V; isolated-case cut-out at least 100 Mohm case to terminals; **never run the 100 V tester mated** | as stated | `harness/cables.md` section 8; VT-062; `head_design_review_checklist.md` E1, E2; IB-38 |
| HP-12a | Head mated (J1/J2 plugged), chassis unpowered | **E7M (separate step): four-wire resistance frame to chassis GND at the J1 receptacle shell at 100 mA or less** (F2801 0.5 A fuse + R2801 + about 0.44 m of AWG 20/18 + contact pairs); record the real fuse resistance | expected under 2 ohm, dominated by the fuse (UNVERIFIED); if the chassis board GND is not bonded to chassis metal the mated reading is at least 1 Mohm through the drain network (not stated in the sources) | VT-062; `harness/cables.md` section 8 |
| HP-13 | Head docked | HEAD_DOCK reads closed only with the latch closed and the head fully seated; presence code read at J1 pin 7 to pin 2 is 4.70 kohm (head) and J2 pin 7 to pin 4 linked | as stated | body stage 10; contract J1/J2 |

Note on HP-12 and HP-12a. Test labels: the lead's shorthand "E9" is not the heater test; in the harness E7 is frame isolation and W-103.HTR-ISO the heater-circuit test; in `head_design_review_checklist.md` E7 is the post-alpha tail and E2 the heater-circuit check (C-09, `planning/README_0.4.md`); this file uses the harness labels E7, E7M and W-103.HTR-ISO. The contract makes J1 pin 2 the only DC ground connection between head and chassis, bonds the cable shield to chassis at the receptacle and to the head frame through 1 Mohm in parallel with 10 nF, and fits R2801 (board ground to frame). With J1 and J2 mated a DC path between frame and chassis therefore exists by design (about 1 Mohm through the shield, and through R2801 to board ground to J1 pin 2). A reading below 10 Mohm with the cables mated is not a failure of the isolation; the 10 Mohm test applies to the mechanical path through the shoes. E7 does not say whether the cables are mated; unmated is my reading (open item).

## 4. Wiring order (summary of `harness/README.md`)

1. Check the data first: run `python3 harness/cross_check.py` (last result in `harness/cross_check_report.md`: pass, 0 errors; `tool-checked`), and confirm every part number against [01_procurement.md](01_procurement.md).
2. Pack side on the bench: W-002 cassette wiring, polarity (HP-5).
3. Power entry: W-001 pack feed (trunk, fuse within 150 mm of the coupler, 1-to-2 splices, 2 x AWG 16 per pole into the Mini-Fit Jr), W-003 aux pair, W-004 charge inlet, W-005 cover switch; Mini-Fit and charge link last, mark the 8-way housing against pin 1. Heater pair: AWG 18 from the M16 plug to a sealed crimp splice (SPL-JH3/JH4) 30 mm outside the head gland, AWG 20 through the gland to the Micro-Fit terminal (calculated delivered power 19.9 W at 10 V and 28.7 W at 12 V; protection gap between 3.13 A and 3.56 A: IB-69).
4. Drive: W-006 and W-007; re-terminate the Pololu pigtails into the Micro-Fit plugs; left and right are not coded, label them; a wheel-up test finds a swap.
5. Head interface, chassis side: W-008 and W-009 with the J1/J2 receptacles; 360-degree shield termination on the receptacle, open at the board end.
6. Head, separate bench: W-101 and W-102 pigtails with plugs, J2 plug link pin 7 to pin 4, W-103 heater, cut-out and NTC, W-104 to W-106 rail switches (COM and NC only), W-107 lid switch, W-108 to W-111 lane auxiliary, W-112 to W-119 coax pairs. Check the interlock loop: 1.00 kohm +-0.1 % between J1 pins 5 and 6 with all three switches closed, open when any one is pressed.
7. Operator controls on the yellow SAFETY loom, kept apart from VBAT conductors: W-015 E-stop, W-016 selector, W-017 HANDS-ON, W-018 REARM, W-019 PAUSE (own cable from J_PAUSE), W-020 dock, W-021/W-022 bumpers.
8. Panel and sensors: W-023 RR-PANEL, W-024 sounder (optional), W-030 to W-040 ToF, W-041 bay heater with cut-out, W-042 NTCs. Sensor mapping (DEC-043): J_TOF4 = LOOK_FL, J_TOF5 = LOOK_RL, J_TOF6 = LOOK_RR, J_TOF7 = LOOK_FR; the forward pair sits in the grip cheeks, the rearward pair at the tail. Electronics text and net labels still use the old names LOOK_LO/LI/RI/RO (IB-34).
9. Compute: W-010 5 V feed (AWG 20), W-011 LiDAR power, W-012 LiDAR Ethernet, W-013/W-014 USB.
10. HP-6, then power-up per [04_bring_up.md](04_bring_up.md).

Board connector order in stage 5 (`assembly.md`): (1) J_PWR (right rear edge; keep 12 mm clear height over the inboard top-entry headers free of loom); (2) motor connectors J_MOT_L/R; (3) cliff and dock leads; (4) CM5 USB x2 and Ethernet; (5) rear-left corner headers (panel, mode, buttons, bumper, rear ToF); (6) rear-right corner headers (E-stop, HANDS-ON, cover, NTC, heater). Tie-wrap or P-clip within 40 mm of every header.

Known wiring issues to resolve before cutting wire (blocking items of `harness/README.md`): OI-01 (no wire part number), OI-04 (SBS50 -20 C), OI-05 (JST GH -25 C), OI-06 (M16 contact range for 0.75 mm2), OD-3 (head AWG 18 on a recalled Micro-Fit contact variant at up to 4.35 A), OD-2 (coax pigtail 45 to 50 mm against 35 mm assumed in the pickup calculation, IB-23, IB-57). Shield drain wires TP2004/TP2501 are 130 and 110 mm (OD-4).

## 5. Safety-chain wiring: what must be right before the first power

The chain is series wiring of: MODE_RUN, ESTOP (two poles), HANDS_ON, CHG_COVER, HEAD_DOCK, HEAD_LOOP, LAB_KEY_N, BODY_BUMPER, WDG_OK, ARM_PERMIT (`interface/system/contract.yaml safety_chain`). During wiring:

- Run the chain devices on the separate SAFETY loom; check that no tap, lamp or test point bridges a chain element (`chassis_design_review_checklist.md` C: "review the routed board, not only the netlist"; not possible until the board exists).
- Left and right bumper switch cables, the rail-switch cables W-105/W-106 (swapped between J2003/J2004 so they do not cross, which swaps the idle zone labels; the zone read-back is not available in rev A, IB-21, IB-57): confirm each rail switch opens the loop by pressing it.
- Check E-stop with each pole lifted alone only with the bring-up procedure, not during wiring.
- Do not use any jumper to bypass a chain element for a test unless the procedure says so (`head_icd.md` section 7: no jumper may bridge the mount or drive inhibit to run the bench test).

Wiring rules that come from the single-fault analysis (`electronics/analysis/chassis_safety_chain.md` section 6.1; these are faults that leave no hardware barrier, so the wiring has to avoid them):

- Keep W-015 (E-stop: pole A pair CH_N1/CH_N2 and pole B pair COIL_RTN/GND in one cable), W-017 (HANDS-ON: CH_N2/CH_N3 and the lamp pair HANDS_LAMP_P / HANDS_LAMP_K in one loom) and W-018 (REARM, three twisted pairs) protected against crush and chafe; a multi-conductor crush that shorts both pairs is a stated residual fault (W-015: the E-stop is lost entirely; W-018: arms once, for 5 s).
- Procedure that the wiring cannot enforce: never work at the wheels unless the HANDS-ON lamp is lit (a welded HANDS-ON contact or a lamp-to-contact short removes the barrier); use selector OFF, not SERVICE, for work at the wheels (a welded RUN contact leaves SERVICE closed).
- The ten service pads SVC1 to SVC10 (TP63 to TP72, 2 x 5 array at 2.54 mm, board (128 to 138, 78 to 81), top side, 220 kohm each) must be reachable with the service cover off and the board fitted; **whether they are reachable inside the body is still being checked** (IB-74) and the board-removal and service-opening findings of IB-73 apply.
- JP1 (watchdog output to NRST) is to stay **open** until the first-strobe timing after reset has been measured (VT-055); the IWDG still resets the MCU (`firmware/chassis/README.md` Known gaps).

This is not a certified safety function (see 04).

## 6. Open items

| Item | ID | Status |
|---|---|---|
| Pin positions and key orientations in `pin_views.md` are conventions | IB-35, OI-19 | Open |
| Head-frame bonding scheme final for both builds (implemented; whether E7 is run mated or unmated is not stated) | IB-20, IB-38 | Closed in design; test condition not defined |
| Grip bar moving to x = -30; saddle, fairing and side plates change; carry attitude target 10 degrees | IB-10, DEC-042 | being applied |
| Pause/Stop body envelope in the rear-right connector space | IB-55 (CR-08), IB-12 | Open |
| Head board change requests CR-M01..M04 (J1 port, standoffs, mounting hole) | IB-52 | Open; head fit not confirmed |
| J1 landing connector may need 8 mm against the 6 mm height limit | IB-19 | Open |
| Cable lengths: `electronics/chassis_main/tools/cable_lengths.py` numbers for W-001/003/004/005/006/007 are wrong | IB-57 | Open; "confirm on first build" (`harness/README.md`) |
| Torque values for receptacle nuts (typical 1.0 to 1.5 N m, UNVERIFIED) and for the latch screws | body stage 6 | UNVERIFIED |
| Acceptance force for cable strain relief pull test | `lab_extension.md` item 8 | not yet defined (proposal 50 N for 60 s) |
| Fit review findings C1 to C4, M1 to M11 on both bodies and the head: rework in progress; stage numbers and torques of `assembly.md` are pre-rework | IB-73, IB-75 | Open |
| Reachability of the service-pad array SVC1 to SVC10 in the body | IB-74 | Open (body engineer checking) |
| Hazard owner's disposition of the residual single faults of `chassis_safety_chain.md` section 6.1 | IB-16, IB-71, IB-74 | Open |
| Assembly time estimates, a worker count, a build record template | not yet defined | no backlog ID |
