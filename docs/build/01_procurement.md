# 01 Procurement: what to buy, from which document, and what is not ready

Design 0.4 (draft). Nothing in this project has been built, printed, ordered or measured. Every statement of status below is read from the files cited; I did not open any manufacturer document, supplier page or distributor stock list while writing this file. No part number, price, lead time or supplier is invented here: where a source does not give one, the entry says "not stated" or "not yet defined".

Evidence classes (full legend in [README.md](README.md)): `calculated`, `simulated`, `tool-checked`, `UNVERIFIED` (recalled, not confirmed against a manufacturer document), `design value`, `assumed`.

**Update 2026-11-28.** Re-written against the repository after four independent reviews (`docs/reviews/`), the board stages 3 to 5, head firmware 0.6.0, chassis stage-5 firmware, MODEL.md revision 5, contract draft11, the production body and the registers (56 decisions, 110 requirements, 81 verification tests, 59 risks: `planning/README_0.4.md`) and the backlog to IB-75. Changes that matter for ordering: both large boards are placed but **not routed** (chassis about 1260 connections open, head 1468); the fit review found that **neither body can be assembled as modelled** (IB-73) and the rework is in progress, so body parts are not released; the head front-edge board connectors do not fit and a board change is assigned (IB-75, CR-H17); the RFQ now asks for at least 18 p.e. at the MIP most-probable deposit, ZnS decay data and the SiPM type; new BOM lines N09 to N18 exist (motor suppression, heater splices and insulation, thermal-break kit, body and head part lists).

## 1. How the verification words are used

The registers use four words for a purchased part. They are not interchangeable with "checked against the manufacturer's document by the reader of this file".

| Word in the source | Meaning in the source | What it means for ordering |
|---|---|---|
| `VERIFIED` | The mechanical or modules engineer read a manufacturer or distributor document for the quantity named (`mechanical/common/purchased/parts.yaml`; `electronics/modules/*.md` tag `[D]`) | Acceptable to order for the quantities named. Not re-checked by me. |
| `PARTIAL` | Some quantities verified, others not (always read the per-quantity list in `parts.yaml`) | Order only if the unverified quantities do not decide the purchase (for example mounting holes), otherwise check first. |
| `UNVERIFIED` / `verify: true` / `VERIFY` | Recalled from memory or assumed | Read the manufacturer document and record the result (VT-047) before ordering. |
| `NOT STATED` / `TBD` / "no part number in any source" | Nothing selected | Cannot be ordered. Select a part from a manufacturer document first. |

A blank `verify` flag in a board BOM (`planning/bom_0.4/RR-*_bom.csv`) means only that the source does not flag the line. It does not mean that the part was checked: for the head board, `electronics/analysis/head_design_review_checklist.md` item B1 lists which datasheets were read and which pin-outs were recalled, and for the chassis board `electronics/analysis/chassis_design_review_checklist.md` item A lists the `verify=True` parts still open. Distributor availability and lifecycle status were not checked for any part (`head_design_review_checklist.md` C7: distributor sites blocked from the design environment).

## 2. Readiness by group

Counts in the "Lines" columns are my tally of the CSV files on 2026-11-27. The BOM files are regenerated (`python3 planning/bom_0.4/extract_board_boms.py`; `python3 harness/build.py`), so re-tally before ordering.

| # | Group | Source of record | Lines | Marked VERIFIED | PARTIAL / UNVERIFIED / flagged | Not selected | Readiness |
|---|---|---|---:|---:|---:|---:|---|
| 1 | Detector optics: floor and reference assemblies, SiPMs, carriers, coax pigtails (W37, W38, N02) | `planning/Detector_Head_RFQ_0.4.md`; `planning/bom_0.4/procurement_bom.csv` | 3 | 0 | 0 | 3 | Cannot be ordered: no supplier selected, no response in the repository |
| 2 | Custom boards: RR-HEAD-ACQ, RR-CHS-MAIN, RR-PANEL, RR-TOF-A x 11 (B01, B02, B03, W21) | `planning/bom_0.4/procurement_bom.csv`; `electronics/*/README.md` | 4 designs | n/a (in-house) | see section 4 | fabrication supplier not stated | Mixed, section 4 |
| 3 | Board components (all four boards) | `planning/bom_0.4/RR-*_bom.csv` (regenerated: `python3 planning/bom_0.4/extract_board_boms.py`) | 250 + 199 + 19 + 8 MPN lines (chassis, head, panel, ToF) | none recorded | 72 + 25 + 6 + 1 lines flagged VERIFY | 0 | Order only after VT-047 on the flagged lines, and not before the layout of that board is final |
| 4 | Purchased modules with a part number (W06, W07, W10, W13, W15, W24, W25, W28, R01, R02, R05 ...) | `planning/bom_0.4/procurement_bom.csv` (86 lines); `mechanical/common/purchased/parts.yaml` | lines with quantity above 0, excluding the 10 custom lines: 3 VERIFIED + 5 PARTIAL + 17 UNVERIFIED + 19 NOT STATED + 4 mixed (W30, N16, N17, N18) | 3 (W13, W28, R02) | 5 PARTIAL (W07, W10, W15, W24, W25) + 17 UNVERIFIED | 19 NOT STATED (W09, W17, W29b, W31a/b/c, W37, W38, E09, R07, N02, N04, N05, N06, N07, N09, N10, N11, N13) | Section 5 |
| 5 | Connectors, contacts, housings (143 connector rows) | `harness/parts_status.md` | 143 | 79 "verified (not flagged in source)" | 27 UNVERIFIED | 37 TBD | Section 6 |
| 6 | Cables, wire, coax, splices, fuses, heaters, NTCs, switches without a number | `harness/parts_status.md` ("Cables and wire", "Contacts, housings, splices", "Protection devices", "Devices") | about 30 lines | 0 | few | nearly all "no part number in any source" | Cannot be ordered (IB-35) |
| 7 | Fabricated body parts (prototype RRX-F.. and production CNC/SLS parts) | `mechanical/prototype_x1c/purchased_and_fabricated.csv`; `mechanical/production/bom_production.csv` | prototype 13 fabricated lines; production 44 unique made parts, 339 fasteners (IB-68) | n/a | production supplier capability UNVERIFIED (VT-073) | fabricators not stated | **Not released**: the fit review (IB-73) found neither body can be assembled as modelled; rework in progress |
| 8 | Prototype body hardware (screws, inserts, seals, latches) | `mechanical/prototype_x1c/hardware_by_subassembly.md`; same CSV | 74 | 37 `STD` (ISO standard parts) | 35 `UNVERIFIED`, 3 `DESIGN` | inserts: brand to choose | Section 7 |
| 9 | Head purchased parts and fasteners | `mechanical/head/prototype/purchased_and_fabricated.csv` | 86 lines, of which 47 purchased | 0 | 45 UNVERIFIED, 4 PARTIAL | supplier not stated | Section 7 |
| 10 | Filament, consumables, tools, test equipment | Sections 8 and 9 below | n/a | n/a | n/a | tools: none named in any source | Section 8, 9 |

Nothing in the registers states a price, a supplier availability or a lead time ("Not priced", `planning/README_0.4.md`). That gap is listed in section 10.

## 3. Lead-time-critical items (by dependency, not by quoted lead time)

No source quotes a lead time. The items below are on the critical path because other work waits for them. Quote requests to confirm lead time are not yet made.

| Item | Why it is critical | Source |
|---|---|---|
| Optical assemblies (W37, W38) | The beta channel works only if the guaranteed photoelectron yield exceeds the dark-limited threshold of about 7 to 10 p.e.; no head test (VT-042, VT-015, VT-043) can start without a real lane. The 0.3 baseline plan buys one lane first and four only after single-lane evidence (gate G1). | `planning/Detector_Head_RFQ_0.4.md` section A; `docs/Rad_Roomba_Design.pdf` ch. 09 gates; `electronics/analysis/head_afe_budget.md` sections 3.2, 12; RSK-019 |
| RR-HEAD-ACQ and RR-CHS-MAIN boards | Both are placed but not routed (about 1260 and 1468 connections open) and the layouts need a layout engineer's review before fabrication; the head board also needs the front-edge connector change; every electrical bring-up stage waits for them. | IB-42, IB-51, IB-74, IB-75, VT-048; `docs/architecture/SYSTEM_ARCHITECTURE.md` (Morgan, 2026-11-27) |
| Charger IC pin map and strap check | IB-06 must close before RR-CHS-MAIN fabrication. | IB-06, RSK-024 |
| J1/J2 circular connectors (binder M16 and M12 families) and the head pigtail cables | Family only; no code, no contact range check (0.75 mm2 on the M16 contacts unverified). Both ends of the head interface wait on it. | IB-35, `harness/parts_status.md`, OI-06 |
| Anderson SBS50 coupler | Candidate only, recalled to -20 C; the battery cassette cannot be completed without it. | `electronics/modules/battery_pack_and_coupler.md`; OI-04 |
| Optics RFQ answer with the stricter requirements | At least 18 p.e. at the most-probable MIP deposit at the worst point of the plate at +10 C (position map of at least 9 points), the SiPM type, ZnS decay time and afterglow data, bond-line limits at the +5 C set-point and rating to -25 C: no supplier has answered; the head cannot choose its time-over-threshold cut without them | `planning/Detector_Head_RFQ_0.4.md` sections A, E, J, K; VT-042, VT-050, VT-051; RSK-019 |
| ST VL53L4ED driver (not a purchase but gates motion) | The firmware driver is a stub; on hardware every direction is refused. | IB-04; `firmware/chassis/README.md` Known gaps |

## 4. Custom boards

| Board | Status in the sources | Bare board can be ordered? | Condition |
|---|---|---|---|
| RR-TOF-A (11 per robot, plus spares) | ERC 0/0, DRC 0/0, 0 unconnected, parity 0; Gerbers in `electronics/tof_carrier/out/gerber/` (`tool-checked`). VL53L4ED ordering code `VL53L4EDV0DH/1` not checked against the ST datasheet. JST GH rated -25 C only by recall (IB-08). | Yes, as a bare board | Assembly: confirm the sensor orderable code first. Spares count is not defined in any source. |
| RR-PANEL (1) | ERC 0/0, DRC 0/0, Gerbers in `electronics/panel/out/gerber/`. Open: mounting holes (3.5, 20.5) and (66.5, 20.5) are a stage-1 proposal that mechanical never confirmed; which end faces +y and the cable exit edge are unconfirmed; LED intensity and buzzer level `UNVERIFIED` (`electronics/panel/README.md`). | After a check | Confirm hole positions against the printed `panel_tray` (RRX-P50) and the cable exit with the prototype body owner before ordering. |
| RR-CHS-MAIN (1) | 160 x 100 mm, 6 layers; chassis stage 5 netlist self-check PASS, ERC 0/0, DRC 0 errors, parity 0, **about 1260 connections unrouted** (`INTEGRATION_BACKLOG.md` IB-74; `electronics/chassis_main/README.md`; `tool-checked`). Placeholder land patterns for U8, U10, U13, U16-U19, L3, L4 are from memory (IB-43). L60 choke winding pairing unverified (a wrong pairing shorts RS-485 A to B). The traction-inhibit chain was reviewed three times (IB-66, IB-70, IB-74); the independent reviewer would sign the chain description, the single-fault list and the operating limits but not the latent-fault control until the service-test fixes of stage 5 are accepted (reachability of the ten top-side service pads SVC1-SVC10 inside the body is still being checked). | No | Route by hand in KiCad (power pours, safety-chain pre-routes), redraw placeholder footprints from manufacturer drawings, close IB-06, layout-engineer review (VT-048), hazard-owner disposition of the residual single faults (IB-16, IB-71). |
| RR-HEAD-ACQ (1) | 326 x 96 mm, 6 layers, stage 3 (new stack-up: signal / GND / signal / power / GND / signal; J1 landing 7 mm further forward; frame-bond fuse F2801 0.5 A and frame monitor; monitor muxes with MON_LANE_EN off). **Not routed**: the stage-2 partial routing was invalidated by stage 3 and the --no-route board has 1468 unconnected (`electronics/head_acq/README.md`; C-12 in `planning/README_0.4.md`). **The front-edge JST GH headers J2002/J2003/J2004/J2201/J2402 do not fit** (mated plugs reach x 185.65 against the frame wall at 185.6 and hit the front fence, lid bosses, a standoff and the desiccant): a board change is assigned (CR-H17, IB-75). Land patterns for the shield clip and common-mode choke are from memory (IB-53). | No | As for RR-CHS-MAIN, plus the CR-H17 board change and head mechanical adoption of the J1/J2 pigtail boots. A Gerber set exists in `electronics/head_acq/out/gerber/` but belongs to an earlier, partly routed state: do not send it. |

The head board's open-connection figure has been quoted as 1090 (README text), 340 (IB-51 first text) and 1468 (after stage 3): use 1468 and the file's date (C-12).

## 5. Purchased modules

Evidence is `UNVERIFIED` or `VERIFIED` as in the source column. "Order now" means the source marks the properties that decide the purchase as verified, or the purchase is for bench use where the open quantity does not matter.

| ID | Item | Part (as in the source) | Source status | Decision |
|---|---|---|---|---|
| W28, R02 | LiFePO4 pack 12.8 V 12 Ah, 1 fitted + 1 spare | Power-Sonic PSL-SC-12120 | VERIFIED: dimensions, mass, temperature, current (`parts.yaml` battery_12ah) | Order now. Open and not blocking the purchase: UN 38.3 shipping documentation, BMS behaviour below -20 C cell temperature, whether the charger can wake a pack after a BMS under-voltage latch (`electronics/modules/battery_pack_and_coupler.md`; VT-040). Pack charge range is 0 to +45 C [source: pack sheet]. |
| W13 | Rear caster | TENTE Compacta 1430POI025P60-35x30 | VERIFIED, but plain bearing and -20 C limit | Order now for warm bench work. The caster choice for the cold objective is a lead decision still open (IB-26). |
| W10 | Gearmotor with encoder | Pololu #2828 | PARTIAL: can, body length, shaft, mass, ratings VERIFIED; boss, shaft offset, mount pattern, temperature rating UNVERIFIED; rotor inertia and inductance not published | Order now. Check the gearbox thread pattern on arrival (pod has both clockings; M3 engagement at most 3 mm, `hardware_by_subassembly.md` C). Order a spare (see section 11). |
| W12 hub | Wheel hub | Pololu #1999 | VERIFIED 25.4 x 9.2 mm, six M3 (`parts.yaml` wheel, 2026-11-26); bolt circle UNVERIFIED | Order now. The wheel itself is printed (RRX-P30/P31). W12 as a catalogue wheel is "select to fit": not used in the printed prototype. |
| W24 | Switches, 7 per robot | Omron D2HW-C201M | temperature and IP67 VERIFIED; dimensions PARTIAL (drawing fragments); mass UNVERIFIED | Order now with spares; the pockets were drawn from fragments, so fit-check one switch in a printed pocket first. The head lid interlock switch is not counted and has no part (IB-26). |
| W25 | E-stop | Schneider Harmony XB5AS8444 | cut-out, head diameter, 2 NC VERIFIED; depth PARTIAL (43 mm listed, 50 used); head height UNVERIFIED; temperature PARTIAL | Order now. |
| W07 | CM5 carrier | Waveshare CM5-IO-BASE-A | length, width, interfaces VERIFIED; assembled height (24 mm assumed), mounting holes, temperature UNVERIFIED | After verification of the holes (the `cm5_tray` pattern depends on it; IB-55). |
| W06 | Compute module | Raspberry Pi CM5104032 | all recalled; lower limit -20 C recalled | After verification of the orderable code and temperature range; no margin at -25 C. |
| W15 | LiDAR | Richbeam LakiBeam 1L | footprint PARTIAL (60 x 60 x 80 listed for the family); mass, temperature VERIFIED; scan plane height, holes, connector UNVERIFIED | After verification of the hole pattern and connector (the printed hump pad is drilled 4 x 3.4 on a 50 mm square as a guess). Alternative SICK PICS150-01000 (W16, quantity 0, temperature UNVERIFIED). |
| R01 | Battery coupler | Anderson SBS50 with two auxiliary contacts | UNVERIFIED (housing colour, key code, auxiliary kit, temperature range recalled -20 to +105 C) | After verification; Anderson page returned HTTP 404 during the harness check. Also needs contact parts that no source names. |
| R05, R06a, R06b, N01 | Selector, REARM, PAUSE, HANDS-ON | Schneider Harmony XB5 family; XB5AD33 candidate (catalogue assembly has 2 NO, one block must be exchanged to ZBE-102 NC); the other three "reference TBD" | UNVERIFIED | After the exact references are selected and the contact arrangements confirmed (`electronics/modules/estop_and_operator_switches.md`). These are chain elements: do not substitute without re-reading the chain. |
| R03, W29b | Charge inlet and plug | M12 L-coded 4+FE | UNVERIFIED / not stated | Cannot be ordered until selected. |
| W27a, W27b | J1 and J2 receptacles | binder M16 8-pole (423/723 family) and M12-A 8-pole (763 family) | UNVERIFIED (only the 20 mm connector diameter is PARTIAL) | After selection and a contact-range check (IB-35, OI-06). |
| W29a | 24 V charge supply | Mean Well GST90A24-P1M candidate | UNVERIFIED (rating, -30 to +70 C range, plug) | After verification. Bench work can use a laboratory 24 V supply with a 3 A limit (source note on W29a). |
| R10 | Spare-pack bench charger | Power-Sonic PSC-124000-LIFE | UNVERIFIED (input range, temperature, connector) | Optional; not needed for first bring-up. |
| W20 | ToF sensor, 11 per robot | ST VL53L4EDV0DH/1 | ordering suffix not checked | After the suffix is checked against the ST datasheet. |
| W18 | IMU (on RR-CHS-MAIN) | Bosch BMI088 | flagged verify, pin numbers recalled | Part of the board BOM (group 3). |
| W31a, W31b, W31c, E09 | Heater films, cut-outs, NTCs | none | design value / not stated | Cannot be ordered. Selection depends on the thermal test; cut-out rating: at least 3.04 A at 14.4 V DC for the bay (`parts_status.md`); trip temperature for the head cut-out is "not stated" in the head BOM, while the head CSV lists a KSD-01 class device opening at 45 C as UNVERIFIED. |
| W09, W17, N07, R07 | Board interconnect cables, LiDAR harness, cassette wiring, LAB extension | none | not stated | Cannot be ordered until the cable parts in group 6 are selected. |
| N04, N05, N06 | Vents, desiccant, drain valves | none | not stated | Select (class stated in `mechanical/common/out/mech_calcs.md` section 7). |
| N08 | External sounder | class XB5KSB/XB5KS2, no part verified | UNVERIFIED | Optional; the on-board piezo is about 60 dB at 1 m and probably too quiet (`electronics/panel/README.md`). |

**Added since the first version (`planning/bom_0.4/procurement_bom.csv`; none has a part number):**

| ID | Item | Why it exists | Status |
|---|---|---|---|
| N09, N10, N11 | Motor-terminal suppression at each motor: 47 to 100 nF X7R at least 50 V across the terminals (1206 or film); 4.7 to 10 nF X7R at least 100 V from each terminal to the can; can bonding strap at most 30 mm and at least 2.5 mm wide to the chassis plate | review M4: brush arcing has no suppression in the netlist (IB-67); `harness/cables.md` section 7 | NOT STATED; X7R rating at -25 C and DC-bias loss to verify on the chosen part; how the strap bonds to the Pololu can is UNVERIFIED |
| N12, N13 | Thin-wall AWG 20 conductors in the head (outer diameter at most 1.60 mm prototype, 1.75 mm production) and sealed crimp splices SPL-JH3/JH4 30 mm outside the head gland (AWG 18 to AWG 20) | J1 fan-in (IB-61) and heater wiring (IB-69) | NOT STATED |
| N14 | Heater insulation items: NTC 10 kohm with an isolated lug (or on a 0.1 mm polyimide pad), bimetal cut-out with an isolated case (at least 100 Mohm case to terminals at 100 V), heater film edges with 1 mm polyimide overlap | review M5 (heater return through R2801); head checklist E1 | UNVERIFIED |
| N15 | Receiver thermal-break kit per body: 4.00 mm ground G-10 shims (RRX-F12/F13), G-10 top-hat bushings, split pins, M4 screws with DIN 6796 spring washers | DEC-045, IB-64 | G-10 data UNVERIFIED (conductivity 0.30 W/m K handbook); VT-058, VT-060 |
| N16, N17, N18 | Body (prototype), production body and head mechanical lists | consolidated parts lists | follow their source CSVs; the bodies are not released (IB-73) |

**Test items that are also a purchase or a fabrication:** the REARM test plug RTP-1 (a CLIK-Mate 8-way to the J_BTN connector with two separate push buttons, SET on pins 1-2 and AUX on pins 3-4, lamp pins open), described in `electronics/analysis/chassis_safety_chain.md` section 6.2; it has no part list and is a bench-built item.

Development items (quantity 0 per robot) are the way to start electronics work while the large boards cannot be made: NUCLEO-G474RE (as in the 0.3 BOM; the chassis firmware image runs on it for protocol bring-up, the head firmware has a `nucleo_bringup` environment), SATEL-VL53L4ED (two breakouts, room-temperature ranging), a Raspberry Pi CM5 IO board for bench use (named in the W07 note, 160 x 90 mm), the RoboClaw 2x15A IMC412 (bring-up alternative to the on-board bridges). Their part numbers are "as in 0.3 BOM"/not flagged; confirm each against the manufacturer document before ordering like any other part.

## 6. Connectors, contacts, wire (the harness)

Source: `harness/parts_status.md` (generated; "verified (not flagged in source)" means no source flags the number, not that anyone checked it). Connector rows by status of the fixed-half part: 79 not flagged, 27 UNVERIFIED, 37 TBD. The JST GH, Hirose U.FL-R-SMT-1(10) and Tag-Connect TC2030 rows are the not-flagged ones; the Molex Mini-Fit Jr (39-xx), Micro-Fit 3.0 (43xxx), CLIK-Mate (502xxx) rows are all recalled (`connectors.yaml verify: true`).

| Item | Number in the source | Status | Blocking question |
|---|---|---|---|
| Mini-Fit Jr J_PWR (8-way) and J_HEAD1 (10-way) housings and terminals | 39-01-2080, 39-01-2100; 39-00-0078 (AWG 16), 39-00-0038 (AWG 18-24) | UNVERIFIED | Terminal wire ranges and temperature range not confirmed (Molex page returned HTTP 503) |
| Micro-Fit 3.0 housings and terminals | 43025-xx00, 43045-xx00, 43030-0007 (AWG 20-24), 43030-0010 (AWG 26-30) | UNVERIFIED | Head end J2001 pins 3/4 and J2601 pins 1/2 need an AWG 18 contact variant with no suffix in any source (IB-32 open at the head end, OD-3) |
| CLIK-Mate chain connectors | 502439-xx00 housings, 502438-0000 contacts, 502443-xxx0 headers | UNVERIFIED | None selected beyond family; these connect chain elements |
| JST GH signal connectors (about 50) | GHR-xxV-S, SSHL-002T-P0.2, BM/SM..B-GHS | not flagged | Recalled rating -25 to +85 C: no margin at the -25 C objective (IB-08, OI-05) |
| binder M16 (J1) and M12 A-coded (J2) plugs, sockets, extension halves | family only, no code | TBD | Contact range against 0.75 mm2, solder-cup or crimp variant |
| Charge inlet and plug (M12 L-coded) | none | TBD | Part number "with the harness lead" |
| Hirose U.FL-R-SMT-1(10) receptacles on the head board | U.FL-R-SMT-1(10) | not flagged | Mating plug for 1.13 mm micro-coax (I-PEX MHF I LK or U.FL-LP class) has no number |
| Anderson SBS50 contacts and auxiliary kit | none | TBD | See section 5 |
| Wire and cable: silicone AWG 12/14/16/18/20/22/24, FEP/ETFE AWG 24-28, shielded J1 multicore (7 conductors + braid, OD at most 7.5 mm, PUR/TPE jacket for -40 C), shielded 4-pair J2 cable (OD at most 6.5 mm), USB 2.0 shielded AWG 28, ToF 6 x AWG 28 cable, 50 ohm 1.13 mm micro-coax | none | TBD | Cold-flexible rating, OD limits (they set the head grommet bore) |
| Fuses: 20 A, 32 V, at least 1 kA blade fuse and holder; cassette fuse | none | TBD | Source: `electronics/analysis/power_budget.md` section 5 |
| Crimp, insertion and extraction tools for every contact family | none | TBD | `harness/README.md` "Tools": none named in any source |

Contradictions the harness engineer recorded and that affect what to buy (all in `harness/README.md`, IB-36, IB-57): the J_PWR trunk is AWG 14 splitting into 2 x AWG 16 per pole because the fitted contact takes AWG 16, while `power_budget.md` assumed AWG 14 to the board; SBS50 is recalled to -20 C only; the head pigtail is specified at 290 mm (200 mm free plus about 90 mm inside) against 0.35 m in the budget.

The SiPM coax length is stated three ways: 35 mm (RFQ 0.4 section B, RQ-062, `board_envelopes.yaml`), 45 to 50 mm (harness stage 2, OD-2, IB-57), and "about 60 mm" (`mechanical/head/prototype/purchased_and_fabricated.csv` PUR-COAX). The length is set by the supplier of the optics together with the head layout; it must be settled before the RFQ is awarded because bench test B11 (VT-041) is sensitive to the pigtail loop.

## 7. Prototype body, head and fabricated parts

**Status: not released for ordering or fabrication.** The independent fit review (`docs/reviews/REVIEW_cad_pcb_harness_fit.md`, IB-73; tool-checked on the STEP and KiCad files, board connector envelopes estimated) found that **neither body can be assembled as modelled**, in both builds: the chassis main board cannot be fastened (bridge posts 1.0 mm from board holes, nut inside the post, a screw head over a standoff), the receiver thermal-break screws collide with the motor pods and lower hull, the ToF carrier does not fit the four look-sensor seats (2.15 mm interference at the rear header, no room for the mated plug), and the plate grommets are blocked by the motor cans and hull. Major findings add that the main board cannot be removed through the service cover, 30 of 41 cable paths cross solids (the pack feed needs about 350 mm against 300), the docked J1/J2 pigtails pass through the hull, and 8 of 11 ToF carriers need the shell opened. The rework is in progress (body engineer, both builds) together with a re-orientation of the J1/J2 receptacles (IB-75). Until the lead records that the rework is verified, **do not order the plate, channels, posts, shims or hardware lists, and do not rely on any part number, plate count or hardware quantity read from the generated files**; every figure below is "as of the last re-read" and will move.

**Body (RR-X)** `mechanical/prototype_x1c/purchased_and_fabricated.csv` (generated; 156 lines at the last re-read) and `hardware_by_subassembly.md`: printed, fabricated (plate, machined channels, G-10 shims RRX-F12/F13, screw rings, grip parts, bridge tray and posts, latch arm, tray base), purchased and hardware lines, with `STD` for ISO standard parts and `UNVERIFIED` where a supplier part or a dependent dimension is unconfirmed. Heat-set inserts: brand to choose, pull-out value 600 N `UNVERIFIED` until the coupon test (VT-061, IB-55). No fabricator is named.

**Production body** (`mechanical/production/`, IB-68; lead-verified 2026-11-27, 0 clashes in 371 pairs): same parametric code; two SLS PA11 skins instead of ten printed pieces, CNC 6061 pods, rims, plate and channels, cast PU 85A tyres; 44 unique made parts, 339 fasteners, body mass 7.36 kg (9.44 kg with the production head), 50 A3 drawing sheets of which only the plate, receiver channel and shim sheets are fully dimensioned (STEP is the master). `UNVERIFIED`: the SLS large-frame envelope (700 x 380 x 580 mm), PA11 and PU cold properties, G-10 data, supplier capability (VT-073). It is not a prototype purchase; it shares the assembly findings of IB-73. DEC-033 names MJF PA12; the production body uses SLS PA11 (C-10).

**Head (RR-HD-X-000)** `mechanical/head/prototype/purchased_and_fabricated.csv` (86 lines at the last re-read, 47 purchased of which 45 `UNVERIFIED` and 4 `PARTIAL`; 21 machined or sheet lines; 13 printed): lead-verified build 2026-11-28 (51 pass, 0 fail, 5 deviations, IB-75) but **the front-edge board connectors do not fit and the pigtail geometry depends on the body's receptacle re-orientation**; the shield-can, lid and spreader parts that cover the J1/J2 area may change. Items needing a decision before ordering: heater zones (4 x 7.5 W films, PUR-HEATER), the bimetal cut-out with an isolated case (head checklist E1), the entrance film (aluminised PET, areal density "per radiometry": not stated), the insulating jacket foam (standard cold configuration), the M3 x 10.5 spacers.

What can be bought and used without waiting for the rework: purchased modules whose decision does not depend on the mechanics (section 5), filament, coupon material, and the fit-check parts listed in [02_printing.md](02_printing.md) section 4.

## 8. Filament and consumables

| Item | Source | Note |
|---|---|---|
| ASA (Bambu ASA, stock X1C profile) about 1510 g body (as of the last re-read, 2026-11-27) | `mechanical/prototype_x1c/print_schedule.md` | `calculated` from CAD volume; add spools for failed prints (not defined) |
| PAHT-CF (Bambu PAHT-CF) about 228 g body, plus head frame halves and small parts | same; `mechanical/head/prototype/print_schedule.md` | Dry 80 C / 8 h before printing; carbon-filled: not for anything touching terminals |
| TPU 95A about 129 g (tyres); head grommets | same | Head grommets from an external spool, not the AMS (`plates.yaml` TPU) |
| PETG-CF (head cassettes, lane rings, barrier, transport covers, cradle) | `mechanical/head/prototype/plates.yaml` | head only |
| Neutral-cure RTV silicone, -50 C, one 80 ml tube; black RTV 2 x 0.1 ml; silicone adhesive; flexible cyanoacrylate or polyurethane adhesive (tyres) | `hardware_by_subassembly.md` B, C, J | Part numbers not stated |
| Medium thread-lock; anti-seize for stainless in aluminium | `assembly.md` general rules | Part numbers not stated |
| Conductive epoxy (J1 blister bead), polyimide tape 0.1 mm, conductive fabric-over-foam strips | head CSV | UNVERIFIED |
| Thermal gap pad 60 x 40 x 2 mm, at least 3 W/mK | `hardware_by_subassembly.md` E | UNVERIFIED |
| Desiccant with humidity indicator | N05 | consumable |
| EVA foam pad, cam straps, wood screws for the transport tray | `hardware_by_subassembly.md` K | STD |

## 9. Tools and test equipment named in the sources

No source gives a tool part number. The list below is what the documents require; test-equipment BOM lines W36, E12, E13, E14, R08 are "not stated".

| Need | Where required |
|---|---|
| Bambu Lab X1 Carbon with hardened 0.4 mm nozzle, closed chamber, textured PEI plate, filament dryer (80 C) | `print_schedule.md` |
| Soldering iron with insert tips for M2 to M4 inserts (ASA 220-235 C, PAHT-CF 240-250 C; head 230-250 C) | `assembly.md`; head `print_schedule.md` |
| Torque drivers covering 0.15 to 6 N m, hex keys 1.5, 2.0, 2.5, 3; 8 mm spanner | body and head assembly documents |
| Pin gauges or equivalent for insert holes; reamers 4.3 H9 and 3.0 H8 (head); 4 H7 reamer (receiver dowel holes) | head `print_schedule.md`; body `assembly.md` stage 1 |
| Surface plate, feeler gauges (0.06 and 0.12 mm named), straight edge, dial gauge, depth gauge, 16.00 x 14.00 x 70 mm head-shoe gauge bar, 10.00 mm setting block | body `assembly.md` stage 1, 3; head assembly 1, 3; `gap_measurement_method.md` |
| Force gauge and linear stage (rail trip and stroke), 3 scales for mass and CG, grip proof-load rig (3 x 9 kg = 265 N) | head E2, E5; body stage 8 |
| Multimeter with 4-wire resistance, decade resistance box (0.59 to 1.55 kohm loop window and 3.92 to 5.64 kohm PRES_ID window), insulation tester 50 V (head E7) and 500 V (LAB extension) | `chassis_safety_chain.md` section 8; head E7; `lab_extension.md` section 7 |
| Current-limited bench supplies (two channels at least: 12 V and a 5 V isolated supply), laboratory 24 V supply with 3 A limit | `layout_guidance.md` section 7; W29a |
| Oscilloscope with a 50 ohm input for the monitor output | `head_afe_budget.md` |
| ST-LINK/V2 or V3, USB-UART adapter, isolated USB-RS-485 adapter | firmware READMEs |
| Dark box, 1000 lux LED panel, 500 lm torch, 1000 lm lamp | head E1, `print_schedule.md` |
| Temperature chamber and cold box (to -25 C); thermocouples | VT-013, VT-040, VT-042 |
| Calibrated radioactive sources (Sr-90/Y-90 or Tl-204; Am-241; planar sources) under site control | VT-042, VT-016, `head_afe_budget.md` B7 |
| Crimp tools for each contact family | none named (`harness/README.md` Tools) |
| REARM test plug RTP-1 (bench-built), DMM with a 2 Mohm range and 10 Mohm DC input (+-1 %) and a low-voltage resistance range, scope with a x10 probe, SWD probe with test firmware, LCR meter (1 kHz), four-wire meter limited to 100 mA | S3 to S8 and P1 service tests: `chassis_safety_chain.md` section 6.2; `harness/cables.md` sections 7 and 8 |
| 100 V DC insulation tester (head E7, heater-circuit insulation, motor-can check), pulse generator for brisk REARM taps (2 to 40 ms) and for the head pulser | VT-062, VT-080 |
| Active probe of 1 pF or less (or the PRE pad through its 453 ohm) and an averaging scope (at least 10^4 triggers), current probe on a motor lead, 1 to 30 MHz current clamp for cable common-mode injection, hot-air tool for a cut-out event, DC bench supply to run the motors at 100 % with the bridges asleep | VT-049, VT-063; `REVIEW_head_interference.md` M7 |
| Am-241 and Sr-90/Y-90 sources for the time-over-threshold histograms | VT-050 |
| Guarded floor rig, fall restraint, instrumented dummy head with gap followers | `gap_measurement_method.md` section 2; VT-003, VT-004, VT-005 |

## 10. Order now, order after verification, cannot order yet

**A. Can be ordered now** (the source marks the deciding properties verified, standard parts, or the item is bench-only):

- PSL-SC-12120 pack (1 fitted + 1 spare) subject to the shipping-documentation question; TENTE caster (warm bench work); Pololu #2828 motors and #1999 hubs; Omron D2HW-C201M (7 + spares); XB5AS8444 E-stop.
- Standard ISO fasteners (37 `STD` lines), PEI-plate filament, RTV and adhesives, EVA foam, wood screws and plywood for the tray.
- Bare RR-TOF-A boards (11 + spares).
- Development items: NUCLEO-G474RE (two: one per firmware), SATEL-VL53L4ED, ST-LINK, USB-UART and isolated RS-485 adapters, a CM5 IO board.
- **Not** the fabricated body parts: the body is not released (section 7, IB-73). Fabrication of the machined channels, plate, posts and shims waits for the rework to be verified; the ordering of G-10 stock for the coupons (VT-060) and for the thermal-break trial can go ahead.

**B. Order only after the listed verification** (read the manufacturer document and record it, VT-047):

- Every `verify=True` / `VERIFY` board component (72, 25, 6 lines) before assembling a board, and not before the layout of that board is final.
- Raspberry Pi CM5 (code, temperature), Waveshare carrier (mounting holes, height), LiDAR (holes, connector, scan plane height), Anderson SBS50 (everything), XB5 selector and buttons (references, contact blocks), ST VL53L4ED (suffix), Mean Well supply (rating, plug), binder M16/M12 receptacles and plugs (codes, contact range), Molex Mini-Fit/Micro-Fit/CLIK-Mate (terminal ranges and temperature), JST GH if the -25 C objective is kept (IB-08).
- Heat-set inserts (brand chosen, pull-out coupon first), gasket and foam stock (-40 C ratings), index plunger, draw latch, light pipes, ePTFE vents.
- RR-PANEL bare board (hole positions and cable exit).

**C. Cannot be ordered yet**

| Item | Why |
|---|---|
| Detector optics (W37, W38, N02) | Supplier not selected; RFQ 0.4 not answered |
| RR-HEAD-ACQ, RR-CHS-MAIN | Not routed (head 1468, chassis about 1260 connections open), layout review not done, IB-06, IB-43, IB-53, CR-H17 (IB-75) |
| Both bodies (plate, channels, posts, shims, hardware sets) | Fit review IB-73: not assemblable as modelled; rework in progress |
| Motor-terminal capacitors and straps, heater splices, thin-wall AWG 20, isolated NTC and cut-out | No part number (N09 to N14) |
| All cable, wire, coax, splice, fuse, fuse holder, heater film, bimetal cut-out, NTC, lid switch, sounder, charge inlet and plug, LiDAR pigtail, U.FL plugs | No part number in any source (IB-35) |
| Crimp and extraction tools | None named |
| Calibration sources, test fixtures (bench cradle, instrumented dummy head, floor rig) | Site or in-house items: not defined |

## 11. Spares (what the sources say)

Only one source defines spares: a second pack (R02), the rail insert print count ("print 8, one spare set", head `print_schedule.md`), and "one spare per robot for pack-swap surveys". Spare switches, motors, ToF boards, connectors and fuses: not yet defined. Recommended spares for the prototype are in [../service/05_maintenance_and_spares.md](../service/05_maintenance_and_spares.md) and are proposals.

## 12. Open items

| Item | ID | Status |
|---|---|---|
| No cable, wire, connector-contact, fuse, heater film, cut-out, NTC, lid switch, charge inlet or tool part number; pin positions in `harness/pin_views.md` are conventions | IB-35 | Open |
| No verification of Molex/JST/Anderson/binder data from a manufacturer page (three fetches failed) | IB-57, OI-04..06 | Open |
| Datasheet verification of flagged components and purchased-part data | VT-047, RSK-030, RSK-039 | Pending |
| Charger pin map, cell-count strap, JEITA defaults (the firmware driver stays disabled until IB-06 closes; INA228/INA3221 drivers are written but never run: IB-05) | IB-06, IB-05, RSK-024 | Open |
| ST VL53L4ED driver is a stub; firmware refuses all motion on hardware | IB-04, RSK-025 | Open (external) |
| Backlog now runs to IB-75; IB-58 to IB-60 are host-software and head-electronics questions; IB-61 to IB-75 and the reviews change what can be ordered (sections 4, 7, 10) | IB-58 to IB-75 | see the backlog |
| Heater contact rating and protection gap (3.13 A recalled against a 3.56 to 4.35 A chassis trip) | IB-69, RQ-101, VT-071 | Open |
| Production-body supplier capability (SLS envelope, PA11, PU 85A, G-10) | IB-68, VT-073 | Open |
| Motor-terminal suppression parts; thin-wall AWG 20; isolated cut-out and NTC | N09 to N14; IB-67 | no part numbers |
| Land patterns drawn from memory | IB-43, IB-53 | Open |
| Head-board change requests CR-M01..M04 not adopted | IB-52 | Open |
| `parts.yaml` pack quantities show 9 Ah; TENTE caster plain bearing; lid interlock switch not counted; bolt-on clamp resistor listed | IB-26 | Open |
| M16 J1 contact acceptance of 0.75 mm2 | IB-32, OI-06 | Open |
| Optical supplier: p.e. yield guarantee, breakdown matching (2 V vs 2.4 V), -25 C rating | IB-22, RSK-019, RSK-031 | Open (RFQ not answered) |
| Prices, supplier availability, lead times, quantities of spares, fabricator for RRX-F parts, PCB fabrication and assembly supplier | not yet defined | no backlog ID |
| UN 38.3 documentation and BMS behaviour below -20 C | `battery_pack_and_coupler.md`; VT-040 | Open |
