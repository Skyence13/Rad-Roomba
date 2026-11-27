# Rad Roomba harness package

Cable and connector definition for the robot and the detachable head. Everything here is derived from the other engineers' files; nothing in this directory was measured or built. **Every length is estimated from layout, confirm on first build.**

| File | What it is |
|---|---|
| `connectors.yaml` | every connector, receptacle, inline half, splice, fuse and device end (143 rows): ID, location, function, part number and status, mating half, contacts, seal, temperature, keying, pin -> net -> wire, unconnected pins with reasons, documented net pairs |
| `pin_views.md` | two labelled pin views (MATING FACE and WIRE-ENTRY) of every connector with the keying feature; **geometry is a convention, UNVERIFIED** (no manufacturer drawings in the sources) |
| `cables.csv` | one row per wire (284 wires in 58 numbered assemblies W-001..W-201; W-044 removed): from/to connector.pin, nets, AWG, colour, insulation, twist, shield and where it is bonded, length, upstream protection, labels, strain relief |
| `cables.md` | the rules (colour scheme, insulation, length method, labels), the summary and the detail of every assembly, the head interlock loop drawn, the unconnected-pin list |
| `lab_extension.md` | the LAB ONLY 2 m extension pair J1X/J2X: construction, pin tables, 0.125 ohm arithmetic, 1.50 kohm resistor, shield handling, labelling, acceptance test, what the robot must report |
| `cross_check.py`, `cross_check_report.md` | the automatic cross-check and its latest result |
| `parts_status.md` | every part number with its verification status |
| `build.py`, `hdata_conn.py`, `hdata_cables.py`, `hsrc.py` | the generator. **The data tables are in `hdata_*.py`**; `connectors.yaml`, `cables.csv`, `pin_views.md`, `cables.md` and `parts_status.md` are generated: edit the tables, not the outputs |
| `STATUS.md` | progress record |

## How to run

```
python3 harness/build.py          # regenerate connectors.yaml, cables.csv, pin_views.md, cables.md, parts_status.md
python3 harness/cross_check.py    # run the cross-check; writes cross_check_report.md; exit status 1 if any ERROR
```

Needs Python 3 with PyYAML. Both scripts only read the other directories and only write inside `harness/`.

The cross-check loads the chassis, head and panel `circuit.py`, `electronics/chassis_main/design/connectors.yaml`, `electronics/tof_carrier/out/pinmap.json`, `firmware/chassis/pinmap.yaml`, `firmware/head/pinmap.yaml`, `interface/system/contract.yaml`, `connectors.yaml` and `cables.csv`, and checks: board connector pin nets against the circuit definitions; both ends of every wire (same net, or a documented pair); J1/J2 against the contract at the chassis board, the receptacle, the plug and the head board with a continuous wire path; every firmware signal that leaves a board reaches the expected connector pin and a wire; wire gauge against the crimp range and the branch current; no pin used twice; unconnected pins and their reasons; the LAB extension. A deliberately wrong wire is caught (mutation-tested when written).

**Latest result: see `cross_check_report.md` and `STATUS.md`.** Stage 2 (2026-11-27): the chassis circuit is read WITH `electronics/chassis_main/overrides.py` applied, connector positions come from the placed boards' `out/pinmap.json`, sensor positions from `mechanical/common/frames.yaml`. The six AWG 18 on Micro-Fit errors are closed by S2-02 (J_HEAD1 = Mini-Fit Jr 2x5) and S2-xx (W-010 AWG 20). The only remaining errors are the two ToF cables over 300 mm that follow from the IB-34 mapping (OD-1).

## Stage-2 changes in the harness (IB-32..IB-37, IB-44)

| Item | Harness now | Source |
|---|---|---|
| PAUSE | own connector J_PAUSE (JST GH 5-way): 1 PAUSE_3V3, 2 PAUSE_BTN_RAW, 3 V12_AUX, 4 LAMP_PAUSE_K, 5 NC; W-019 own cable AWG 26, no splices; W-018 6 wires direct, J_BTN pins 5/8 NC; SPL-BTN3/6 removed | chassis STAGE2 S2-01 |
| J_HEAD1 | Mini-Fit Jr 2x5 39-30-1100, pins 1-8 = J1 pins 1-8, 9/10 NC; W-008 terminals 39-00-0038 AWG 18-24 [UNVERIFIED] | S2-02 |
| J_CM5 | stays Micro-Fit; W-010 AWG 18 -> AWG 20 | STAGE2 IB-32 |
| Rear-right cluster | J_PAUSE, J_TOF3, J_TOF10, J_BUMP_R, J_TOF6 positions from pinmap.json: W-019 290 -> 170, W-022 430 -> 310, W-033 400 -> 290, W-040 400 -> 290 mm | STAGE2 IB-12/33 |
| Look sensors (IB-34, lead) | J_TOF4 = LOOK_FL, J_TOF5 = LOOK_FR, J_TOF6 = LOOK_RL, J_TOF7 = LOOK_RR (old names retired); W-034 150, W-035 280, W-036 360, W-037 350 mm | lead; frames.yaml |
| Panel | J1/J2 on the top side, cable leaves over the v = 24 edge (which end faces +y unconfirmed) | panel P1 |
| Head | J2001/J2601 side by side at the rear edge, J1 port y 76.2, J2004 at u 144.6, GH-6 and U.FL positions as built; coax 45-50 mm; shield drains 130/110 mm | head STAGE2 S2-L3..L6, CR-M03 |
| IB-37 | J_PAUX pins 3/4 stay unwired; offset accepted (about 3.4 K warm on discharge, about 0.7 K cold on charge) | chassis STAGE2 |
| Bus clamp | W-044 and CLAMP-EXT removed: the board carries its own 2 x 9.1 ohm clamp resistors, no bolt-on part | lead decision, IB-26 |

## IB-36 contradictions: what the harness assumes

| Item | Harness assumption | Follows |
|---|---|---|
| J_PWR gauge | AWG 14 trunk + crimp splice + 2 x AWG 16 per pole (39-00-0078 contacts are AWG 16) | `electronics/chassis_main/design/connectors.yaml` (not changed by stage 2); `power_budget.md` assumed AWG 14 to the board |
| SBS50 temperature | recalled -20..+105 C, UNVERIFIED; no margin at -20 C; web page not reachable | `mechanical/common/purchased/parts.yaml` battery_coupler; modules sheet says -40 C not confirmed |
| Bus-clamp resistor | none bolt-on; board resistors only | `electronics/chassis_main/design/circuit.py` (2 x 9.1 ohm 2512) |
| Motor lead gauge | AWG 22 (maker's pigtail, not published) | `power_budget.md`; connectors.yaml recommends AWG 20; both fit 43030-0007 |
| Head pigtail | 200 mm free + about 90 mm inside = 290 mm (budget 0.35 m) | `mechanical_interfaces.md` 150..200 mm and the 142 mm geometry check |

## Build order for the technician

Do not cut wire before the blocking open items (OI-01 .. OI-06 below) are closed or knowingly accepted. Steps:

1. **Check the data first.** Read `cables.md` section 1 (colours, insulation, labels). Run `cross_check.py`. Confirm the part numbers you are about to order against `parts_status.md` (every TBD and UNVERIFIED line is an open item).
2. **Pack side** (bench, before the robot): W-002 cassette wiring (AWG 12 leads, optional cassette fuse, NTC, presence link) -> check polarity with a meter against `connectors.yaml` CPL-C.
3. **Power entry:** W-001 pack feed (trunk, fuse within 150 mm of the coupler, 1-to-2 splices, 2 x AWG 16 per pole into the Mini-Fit Jr), W-003 aux pair, W-004 charge inlet, W-005 cover switch. Mini-Fit and charge link last: mark the 8-way housing against pin 1.
4. **Drive:** W-006 / W-007 motors (re-terminate the Pololu pigtails into 43025-0600; left and right are not coded: label them, wheel-up test finds a swap).
5. **Head interface (chassis side):** W-008 and W-009 leads with the J1/J2 receptacles; shield braid 360 degrees on the receptacle, open at the board end.
6. **Head (separate bench):** W-101 and W-102 pigtails with plugs (shield drain to TP2004/TP2501 and the backshell), the J2 plug link pin 7 to pin 4, W-103 heater/cut-out/NTC, W-104..106 rail switches (COM and NC only), W-107 lid switch, W-108..W-111 lane aux, W-112..W-119 coax pairs. Check the interlock loop with a meter: 1.00 kohm +- 0.1 % between J1 pins 5 and 6 with the three switches closed; open when any one is pressed.
7. **Operator controls (yellow SAFETY loom, separate from VBAT conductors):** W-015 E-stop, W-016 selector, W-017 HANDS-ON, W-018 REARM, W-019 PAUSE (own cable from J_PAUSE), W-020 dock, W-021/W-022 bumpers.
8. **Panel and sensors:** W-023 RR-PANEL, W-024 sounder (optional), W-030..W-040 ToF, W-041 bay heater with cut-out, W-042 NTCs.
9. **Compute:** W-010 5 V feed (AWG 20), W-011 LiDAR power, W-012 LiDAR Ethernet, W-013/W-014 USB.
10. **Unpowered continuity** of every wire against `cables.csv`, then the unpowered continuity step of `electronics/analysis/chassis_safety_chain.md` section 8 (each switch loop < 1 ohm, CH_N0 to ground > 50 kohm, COIL_RTN to ground < 1 ohm released and open pressed, K2/K3 motor terminal A to B about 0.7 ohm). Four-wire resistance of the pack feed and the heater branches (the power budget assumes 5 mohm per contact pair: record the real values).
11. Only then power up per `chassis_safety_chain.md` section 8 (bench supply, current limited). The LAB extension is built and accepted separately (`lab_extension.md` section 7).

## Tools (crimp tools per contact family)

**None of the sources names a crimp tool, an insertion/extraction tool or a tool part number.** Contact families and wire ranges are from `connectors.yaml` (chassis side) and the head `circuit.py` notes.

| Contact family | Contact / wire range (source) | Crimp tool | Extraction tool |
|---|---|---|---|
| Molex Mini-Fit Jr (J_PWR) | 39-00-0078 AWG 16 (pins 1/2/5/6); 39-00-0038 AWG 18-24 (rest) | TBD - not in sources | TBD - not in sources |
| Molex Mini-Fit Jr (J_HEAD1, stage 2) | 39-00-0038 AWG 18-24 [UNVERIFIED] | TBD - not in sources | TBD - not in sources |
| Molex Micro-Fit 3.0 (power) | 43030-0007 AWG 20-24; 43030-0010 AWG 26-30; head note: '43030 18-24 AWG variant' (suffix not given) | TBD - not in sources | TBD - not in sources |
| Molex CLIK-Mate 2.00 (SAFETY) | 502438-0000 AWG 24-30 | TBD - not in sources | TBD - not in sources |
| JST GH 1.25 mm | SSHL-002T-P0.2 AWG 26-30 | TBD - not in sources | TBD - not in sources |
| Hirose U.FL / MHF plug on 1.13 mm micro-coax | plug part TBD - not in sources | TBD - not in sources | n/a |
| binder M16 8-pole / M12 A-coded 8-pole | solder cups or crimp: TBD | soldering tools / TBD | n/a |
| Anderson SBS50 | contacts TBD - not in sources | TBD - not in sources | TBD - not in sources |
| Faston 6.35 mm (cassette) | insulated fastons AWG 12 | TBD - not in sources | n/a |

## Open decisions (these keep `cross_check.py` at exit status 1 or leave warnings)

| ID | Decision | Detail |
|---|---|---|
| OD-1 | **IB-34 mapping vs connector positions.** With J_TOF5 = LOOK_FR, J_TOF6 = LOOK_RL, J_TOF7 = LOOK_RR the connectors J_TOF6 (rear-right) and J_TOF7 (front-right edge) are on the wrong side: W-036 360 mm and W-037 350 mm exceed the 300 mm I2C limit (cross-check ERROR). The stage-1 order (LO/LI/RI/RO = FL, RL, RR, FR, i.e. J_TOF5 = RL, J_TOF6 = RR, J_TOF7 = FR) gives 150 / 270 / 290 / 150 mm for J_TOF4..7 and passes. Change only `LOOK_MAP` in `hdata_cables.py` if the lead agrees. Firmware pinmap and contract still carry LOOK_LO/LI/RI/RO (cross-check warning). | lead |
| OD-2 | SiPM coax pigtails W-112..W-119 are 45-50 mm (35 mm in board_envelopes.yaml) after the S2-L3 layout; carrier position assumed at the lane centre, drop 25 mm. | head electronics / mechanical |
| OD-3 | Head J2001 pins 3/4 and J2601 pins 1/2 (AWG 18, up to 4.35 A) still rely on a recalled Micro-Fit '43030 18-24 AWG variant'; the head stage-2 file does not address it. Same remedy as chassis S2-02 (Mini-Fit Jr) or AWG 20 on the head side. | head electronics |
| OD-4 | TP2004 / TP2501 (shield drain pads) are 60-100 mm from the J2001 / J2501 landings; drains are 130 / 110 mm separate wires. | head electronics |
| OD-5 | Which end of RR-PANEL faces +y (cable exit edge); head CR-M01..M04 not yet adopted by head mechanical (IB-52); chassis cable_lengths.py takes path[0] as the board connector (wrong for W-001/003/004/005/006/007) - corrected here, tool is not mine. | mechanical |
| OD-6 | Head rail switch connector order puts the right-rail connector left of centre: W-105/W-106 cross; swapping them is functionally free in rev A. | head electronics |

## Open items carried over (blocking first, then the rest)

| ID | Item | Where it bites |
|---|---|---|
| OI-01 | No cable or wire part number in any source; cold-flexible (-40 C) conductors, shielded multicores, micro-coax, USB cable need supplier datasheets. | all cables |
| OI-04 | SBS50 rated -20 C only (recalled): no margin at -20 C. Housing colour, key code, auxiliary kit unconfirmed. | CPL-B/CPL-C |
| OI-05 | JST GH recalled as -25..+85 C (IB-08): no margin at -25 C for about 50 connectors. | signal connectors |
| OI-06 | M16 8-pole contact acceptance of 0.75 mm2 (CCR-E07) and receptacle/plug part numbers not in sources. | W-008, W-101, W-200 |
| OI-13 | ToF cable shield drain shares the GND crimp; layout guidance says unshielded. | W-030..W-040 |
| OI-14 | CM5 carrier-end termination of 2 x AWG 20 per pole on the 40-pin header unresolved; back-feed behaviour [U]. | W-010 |
| OI-15 | Both CM5 USB-A ports used (IB-07). | W-013, W-014 |
| OI-16/17 | Operator device references, heater films, cut-outs, NTCs, lid switch, charge inlet, fuse, crimp tools: no part numbers (see `parts_status.md`). | many |
| OI-18 | Power-budget voltage-drop assumptions (5 mohm per contact pair, splice not counted): measure on the first harness. W-004 280 mm vs 250 mm. | W-001, W-004 |
| OI-19 | Pin positions and key orientations in `pin_views.md` are conventions (incl. Mini-Fit Jr 2x5). | all |
| OI-20 | LAB extension AWG 18 on J1 pins 1/2 deliberate (warning). | W-200 |
| OI-22 | USB shield terminated at both ends by design. | W-013, W-014 |
| OI-10 | Head pigtail 200 mm free length (IB-36 above). | W-101, W-102 |
| OI-11 | Rail-zone read-back not available in rev A (IB-21 closed for rev A). | W-104..W-106 |

(Closed by stage 2: OI-02 AWG 18 on Micro-Fit at the chassis, OI-03 recorded as IB-36, OI-07 rear-right cluster, OI-09 PAUSE connector, OI-12 clamp, OI-21 accepted IB-37.)

## Contradictions between sources found while building this

(Stage 2 status: 1, 3, 4, 8 are resolved as recorded in the IB-36 table above; 2 is closed at the chassis end and open at the head end (OD-3); 5 look-ahead 4 vs 2+2 is IB-34 (OD-1); 7 is closed by the rear-right cluster and J_PAUSE. The text below is the stage-1 record.)

1. AWG 14 trunk (`power_budget.md`) vs 39-00-0078 AWG 16 contacts (`connectors.yaml`): OI-03.
2. AWG 18 on Micro-Fit (`connectors.yaml` awg column, `power_budget.md`) vs 43030-0007 AWG 20-24 (`connectors.yaml` mating contacts) vs '18-24 AWG variant' (head `circuit.py`): OI-02.
3. Motor lead AWG 22 (`power_budget.md`) vs AWG 20 recommended (`connectors.yaml` J_MOT): the Pololu lead gauge is not published; AWG 22 used.
4. Bus clamp: OI-12.
5. ToF 'unshielded' (`layout_guidance.md`) vs shielded (task): OI-13. Look-ahead 4 vs 2 + 2: OI-08.
6. D2HW-C201M temperature: VERIFIED in `parts.yaml`, tagged [U] in the modules sheet.
7. Panel J_BTN/J_PANEL allocation to the rear-left corner vs devices on the right: OI-07, OI-09.
8. Head pigtail 'about 150 mm' vs the geometry (142 mm straight line): OI-10. Head `power_budget.md` assumes 0.35 m of pigtail (290 mm specified here, shorter).
9. Head eFuse (TPS26600, 1.0 A) vs chassis HEAD_PWR limit (1.51 A) vs contract 1.5 A: no wire consequence (AWG 20 carries all), reported for the lead.
10. Mating housing of the head Micro-Fit headers (43645, single row) vs the chassis tables (43025, dual row): different boards, no cross-mating, both listed.

## Parts with UNVERIFIED or TBD status

See `parts_status.md` for the full list. In short: every Molex Mini-Fit/Micro-Fit/CLIK-Mate mating part number is 'recalled, not confirmed' (`verify: true` in the source); JST GH parts are not flagged but are rated -25 C [U]; the J1/J2 receptacles and plugs, SBS50, charge inlet, XB5 selector/buttons, LiDAR and CM5 carrier connectors are UNVERIFIED; heaters, cut-outs, NTCs, fuse, cable, coax plug, SiPM carrier connectors and the lid switch are TBD.
