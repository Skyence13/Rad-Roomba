# Rad Roomba harness package

Cable and connector definition for the robot and the detachable head. Everything here is derived from the other engineers' files; nothing in this directory was measured or built. **Every length is estimated from layout, confirm on first build.**

| File | What it is |
|---|---|
| `connectors.yaml` | every connector, receptacle, inline half, splice, fuse and device end (145 rows): ID, location, function, part number and status, mating half, contacts, seal, temperature, keying, pin -> net -> wire, unconnected pins with reasons, documented net pairs |
| `pin_views.md` | two labelled pin views (MATING FACE and WIRE-ENTRY) of every connector with the keying feature; **geometry is a convention, UNVERIFIED** (no manufacturer drawings in the sources) |
| `cables.csv` | one row per wire (288 wires in 59 numbered assemblies W-001..W-201): from/to connector.pin, nets, AWG, colour, insulation, twist, shield and where it is bonded, length, upstream protection, labels, strain relief |
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

**Latest result: FAIL, 6 errors** (all of one kind, see `cross_check_report.md`): AWG 18 conductors on Micro-Fit pins whose mating contact is listed for AWG 20-24 (J_HEAD1 pins 3/4 heater pair, J_CM5 four pins). It is a real conflict between the sources (OI-02), not a transcription slip.

## Build order for the technician

Do not cut wire before the blocking open items (OI-01 .. OI-06 below) are closed or knowingly accepted. Steps:

1. **Check the data first.** Read `cables.md` section 1 (colours, insulation, labels). Run `cross_check.py`. Confirm the part numbers you are about to order against `parts_status.md` (every TBD and UNVERIFIED line is an open item).
2. **Pack side** (bench, before the robot): W-002 cassette wiring (AWG 12 leads, optional cassette fuse, NTC, presence link) -> check polarity with a meter against `connectors.yaml` CPL-C.
3. **Power entry:** W-001 pack feed (trunk, fuse within 150 mm of the coupler, 1-to-2 splices, 2 x AWG 16 per pole into the Mini-Fit Jr), W-003 aux pair, W-004 charge inlet, W-005 cover switch. Mini-Fit and charge link last: mark the 8-way housing against pin 1.
4. **Drive:** W-006 / W-007 motors (re-terminate the Pololu pigtails into 43025-0600; left and right are not coded: label them, wheel-up test finds a swap).
5. **Head interface (chassis side):** W-008 and W-009 leads with the J1/J2 receptacles; shield braid 360 degrees on the receptacle, open at the board end.
6. **Head (separate bench):** W-101 and W-102 pigtails with plugs (shield drain to TP2004/TP2501 and the backshell), the J2 plug link pin 7 to pin 4, W-103 heater/cut-out/NTC, W-104..106 rail switches (COM and NC only), W-107 lid switch, W-108..W-111 lane aux, W-112..W-119 coax pairs. Check the interlock loop with a meter: 1.00 kohm +- 0.1 % between J1 pins 5 and 6 with the three switches closed; open when any one is pressed.
7. **Operator controls (yellow SAFETY loom, separate from VBAT conductors):** W-015 E-stop, W-016 selector, W-017 HANDS-ON, W-018/W-019 REARM and PAUSE Y-loom, W-020 dock, W-021/W-022 bumpers.
8. **Panel and sensors:** W-023 RR-PANEL, W-024 sounder (optional), W-030..W-040 ToF, W-041 bay heater with cut-out, W-042 NTCs, W-044 clamp resistor (optional, not fitted).
9. **Compute:** W-010 5 V feed, W-011 LiDAR power, W-012 LiDAR Ethernet, W-013/W-014 USB.
10. **Unpowered continuity** of every wire against `cables.csv`, then the unpowered continuity step of `electronics/analysis/chassis_safety_chain.md` section 8 (each switch loop < 1 ohm, CH_N0 to ground > 50 kohm, COIL_RTN to ground < 1 ohm released and open pressed, K2/K3 motor terminal A to B about 0.7 ohm). Four-wire resistance of the pack feed and the heater branches (the power budget assumes 5 mohm per contact pair: record the real values).
11. Only then power up per `chassis_safety_chain.md` section 8 (bench supply, current limited). The LAB extension is built and accepted separately (`lab_extension.md` section 7).

## Tools (crimp tools per contact family)

**None of the sources names a crimp tool, an insertion/extraction tool or a tool part number.** Contact families and wire ranges are from `connectors.yaml` (chassis side) and the head `circuit.py` notes.

| Contact family | Contact / wire range (source) | Crimp tool | Extraction tool |
|---|---|---|---|
| Molex Mini-Fit Jr (J_PWR) | 39-00-0078 AWG 16 (pins 1/2/5/6); 39-00-0038 AWG 18-24 (rest) | TBD - not in sources | TBD - not in sources |
| Molex Micro-Fit 3.0 (power) | 43030-0007 AWG 20-24; 43030-0010 AWG 26-30; head note: '43030 18-24 AWG variant' (suffix not given) | TBD - not in sources | TBD - not in sources |
| Molex CLIK-Mate 2.00 (SAFETY) | 502438-0000 AWG 24-30 | TBD - not in sources | TBD - not in sources |
| JST GH 1.25 mm | SSHL-002T-P0.2 AWG 26-30 | TBD - not in sources | TBD - not in sources |
| Hirose U.FL / MHF plug on 1.13 mm micro-coax | plug part TBD - not in sources | TBD - not in sources | n/a |
| binder M16 8-pole / M12 A-coded 8-pole | solder cups or crimp: TBD | soldering tools / TBD | n/a |
| Anderson SBS50 | contacts TBD - not in sources | TBD - not in sources | TBD - not in sources |
| Faston 6.35 mm (cassette) | insulated fastons AWG 12 | TBD - not in sources | n/a |

## Open items (blocking first, then the rest)

| ID | Item | Where it bites |
|---|---|---|
| OI-01 | No cable or wire part number in any source. Cold-flexible conductors (silicone/FEP class, rated <= -40 C), the shielded multicores for J1/J2, the 1.13 mm micro-coax and the USB cable need supplier datasheets showing the rating at -40 C. PVC is excluded; the power budget's 'PVC-free 105 C' AWG 14 is not a cold rating. | all cables |
| OI-02 | **AWG 18 against Micro-Fit contact range.** `connectors.yaml` fits 43030-0007 for AWG 20-24 but marks J_HEAD1 pins 3/4 and all four J_CM5 pins as AWG 18; the head board note says a '43030 18-24 AWG variant' exists; CCR-HE-02 says Micro-Fit is the only locking family that took AWG 18. Find the AWG 18 Micro-Fit terminal (and confirm it fits both housings) or move the heater pair/CM5 feed to a family that takes AWG 18. | W-008, W-010, W-101, W-103 |
| OI-03 | **J_PWR gauge.** `power_budget.md` assumes AWG 14 to the board; the Mini-Fit Jr terminal 39-00-0078 is AWG 16. Resolved as AWG 14 trunk + crimp splice + 2 x AWG 16 per pole (W-001); splice, fuse holder and the SBS50 power-contact wire range are TBD. | W-001 |
| OI-04 | **SBS50 coupler rated -20 C only** (`parts.yaml`: -20..+105 C, UNVERIFIED, recalled; the modules sheet says the -40 C rating is not confirmed) against a -20 C operating target: no margin. Also housing colour, key code and the auxiliary-contact kit are unconfirmed. | CPL-B/CPL-C |
| OI-05 | **JST GH is recalled as -25..+85 C [U]** (CCR-E05, IB-08): all signal connectors (ToF, panel, USB, NTC, data landing J_HEAD2) have no margin at the -25 C objective. | ~50 connectors |
| OI-06 | **M16 8-pole contact acceptance of 0.75 mm2 (AWG 18)** for the LAB extension and the J1 cable (CCR-E07); binder solder cups may be limited to 0.5 mm2. J1/J2 receptacle, plug, socket and charge-inlet part numbers are not in the sources (family only). | W-008, W-101, W-200 |
| OI-07 | **ToF cables over 300 mm**: W-033 (CLIFF_RR) 400, W-035 (LOOK_LI) 360, W-036 (LOOK_RI) 360, W-040 (REAR_R) 400 mm. Cause: five rear ToF connectors and both bumper connectors are allocated to the rear-LEFT board corner while the sensors are also on the right; fix by placing J_TOF3, J_TOF10, J_BUMP_R and PAUSE in the rear-RIGHT cluster (stage 2 layout). | W-033/035/036/040, W-022, W-019 |
| OI-08 | **ToF look-ahead count**: contract and firmware have four look-AHEAD sensors (LOOK_LO/LI/RI/RO); `frames.yaml` has two look-ahead (grip cheeks) and two look-BEHIND (tail). The harness maps LOOK_LI/RI to the tail positions as an assumption. Resolve with the lead before W-035/W-036 are cut. | W-035, W-036 |
| OI-09 | **J_BTN carries REARM (left deck) and PAUSE (right deck)** in one connector at the rear-left corner: the harness needs a Y-loom with two splices and the PAUSE branch crosses the board (W-018/W-019). Recommend a separate PAUSE connector in the rear-right cluster. | W-018, W-019 |
| OI-10 | **Head pigtail free length**: the straight line from the head rear port to the plug rear is 142 mm; 150 mm is too short once the 40 mm bend radius is respected. 200 mm specified (upper end of the 150-200 mm in `mechanical_interfaces.md`). The receptacle lead is specified at 150 mm in `connectors.yaml`; the layout gives 150 mm. | W-101, W-102 |
| OI-11 | **Head rail-zone read-back** (J2002..J2004 pins 3/4) is not wired (CCR-HE-04, IB-21): the firmware inputs BUMP_ZONE_F/L/R_N read 'not actuated' for ever. A double-pole switch or an isolated auxiliary contact per zone would fix it. | W-104..W-106 |
| OI-12 | **Bus-clamp resistor**: `parts.yaml` puts a 50 W wirewound in the front bay, `board_envelopes.yaml` lists a 'bus-clamp resistor' on the right edge rear, `power_budget.md` treats the clamp as on-board, `circuit.py` has only DNP pads W1; value TBD. IB-24 also notes 4.7 ohm vs the 2 x 9.1 = 4.55 ohm on the board. Not fitted. | W-044 |
| OI-13 | **ToF cable shield**: `layout_guidance.md` says '300 mm unshielded sensor cables'; the task and this harness specify shielded cables with the drain at the board end only. A drain shares the GND crimp (two wires in one 26-30 AWG contact): confirm the contact permits it. | W-030..W-040 |
| OI-14 | **CM5 carrier-end termination** of 2 x AWG 18 per pole on the 40-pin header is unresolved; the carrier back-feed/protection behaviour and `usb_max_current_enable` are [U] (modules sheet). Alternative: USB-C power-only pigtail. | W-010 |
| OI-15 | **Both CM5-IO-BASE-A USB-A ports are used** by the two links: no port for a wired service adapter (CCR-E10, IB-07). | W-013, W-014 |
| OI-16 | Operator device part numbers: selector, HANDS-ON, REARM, PAUSE references and contact-block terminal numbers are UNVERIFIED/TBD; the D2HW lead wire gauge, length and colours are not in the sources (splice or direct crimp to the CLIK-Mate contacts); external sounder not selected. | W-015..W-022, W-024 |
| OI-17 | Not in the sources: heater film parts (bay and head), both bimetal cut-outs (>= 3.04 A at 14.4 V DC for the bay), NTC parts, lid switch type and position, SiPM carrier connectors, charge inlet and plug part numbers, LiDAR connector/pigtail, mating housing of the head Micro-Fit (the head note gives 43645-0800/-0600, UNVERIFIED), U.FL mating plug, fuse and fuse holder. | `parts_status.md` |
| OI-18 | Voltage-drop assumptions in `power_budget.md` (5 mohm per contact pair, 0.25 mohm SBS50, splice not counted, 0.25 m lead lengths) are assumptions: measure the first harness four-wire. Lengths over the power budget: W-004 260 mm vs 250 mm (negligible). | W-001, W-004, W-011 |
| OI-19 | Pin positions and key orientation in `pin_views.md` are conventions; confirm every family against the manufacturer drawing before the first crimp (Molex 43045/43025/43650/43645/39-30/502443/502439, JST GH, binder M16/M12, SBS50, Hirose U.FL). | all |
| OI-20 | `power_budget.md` assigns AWG 20 to J1 pins 1/2; the LAB extension specifies AWG 18 on them to meet 0.125 ohm (deliberate deviation, reported by the cross-check as a warning). | W-200 |
| OI-21 | The J_PAUX NTC/presence return rides the pack-negative power path (about 0.1 V at 12.5 A, a few degC of NTC error); J_PAUX pins 3/4 are left unwired. A Kelvin return would need a third SBS50 auxiliary contact. | W-003 |
| OI-22 | USB shield: terminated through 1 Mohm || 10 nF at the board and on the plug shell at the carrier (two terminations by the board design); no ground-loop analysis in the sources. | W-013, W-014 |

## Contradictions between sources found while building this

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
