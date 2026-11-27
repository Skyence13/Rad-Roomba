# Production head RR-HD-P-000 -- fabrication and test pack

Production build for 5-25 units per year: one-piece CNC 6061-T6 frame, laser-cut / formed sheet parts, MJF PA12 lane parts, POM wear parts.
Everything here is generated from the CadQuery model in `mechanical/head/` (`build.sh`); numbers quoted from `out/checks.json` are **calculated** or
**tool-checked** as labelled there. Nothing has been built or measured. Not released: design-stage drawings.

## 1. Identification

| Prefix | Meaning |
|---|---|
| `RR-HD-P-xxx` | production-only part (CNC frame, MJF / POM variants of printed parts, bond shims) |
| `RR-HD-X-xxx` | prototype-only part (printed halves, PA-CF / PETG-CF / TPU parts, G10 isolators, EMI fences) |
| `RR-HD-S-xxx` | shared fabricated part, identical in both builds (shoes, bridge, keeper, spreader, lid, blister, rail bar, rods, bail, side rails) |
| `RR-HD-D/C/G-xxx` | dummy head, bench cradle, gap gauges (`aux/`) |
| `PUR-xxx`, `OEM-xxx`, `EL-xxx` | purchased, OEM optics (RFQ), electronics work package |

## 2. Files

| What | Where |
|---|---|
| Assembly STEP (all parts, rails at rest, 3 mm inserts) | `RR-HD-P-000_head_assembly_production.step` |
| Part STEP (installed position, base_link) | `step/` |
| Flat patterns (spreader, lid, blister, side rails 3 / 5 mm, shield can) | `dxf/` (layers CUT, TAP, BEND, ETCH) |
| Fabrication drawings (orthographic views and sections generated from the model, dimensions, datums A/B/C, GD&T, finish, masking, threads) | `drawings/RR-HD-P_fabrication_drawings.pdf` and one SVG per sheet |
| Assembly drawing with balloons and BOM table | sheet `RR-HD-P-000_assembly` |
| Interface control sheet (film plane, standoff, shoe GD&T) | sheet `RR-HD-P-000-ICD_interface_control` |
| Variant BOM (complete, with quantities and supplier verification status) | `bom_production.csv` (prototype: `../prototype/purchased_and_fabricated.csv`) |
| Assembly sequence with rendered steps, torques | `assembly.md` |

Drawing sheets: RR-HD-P-101 frame (2 sheets), RR-HD-S-111 receiver shoe, RR-HD-S-121 spreader, RR-HD-S-122/123 + RR-HEAD-SHLD-A lid, blister and lane
shield can, RR-HD-P-000 assembly, RR-HD-P-000-ICD, RR-HD-S-40x rail parts. Parts without their own sheet (bridge, keeper, cassette, POM parts, MJF lane
parts, bail blocks) are made from STEP with the general tolerance ISO 2768-mK stated in the title block -- **open item**: sheets for the bridge, keeper
and cassette before the first production order.

## 3. Fabrication notes (summary of the drawing notes)

- **Frame RR-HD-P-101**: 6061-T6 plate 35 mm, 3-axis, two set-ups plus front / rear drilling. Black anodise MIL-A-8625 type II class 2 (matte, bead-blasted;
  Ra <= 1.6 in the lane cavities). **Masked** (chromate conversion MIL-DTL-5541 type II class 3, conductive): spreader seat z 30.0, wall-top gasket
  land z 42.2 and the 18 lid boss tops (z 43.0), so the lid and spreader bond to the frame. The T-head pockets stay **anodised** (0.3 mm air gap + anodise
  isolate the frame from the shoes). Threads: M2.5-6H (ribs, rear zone,
  cassettes, bail blocks), M3-6H x 8 in the lid bosses, M6 x 0.75 vent. Guide-rod bores 4.00 H8, PAR 0.05 to datum A. Light-trap drains (one per
  chimney): 1.2 vertical from below at x 71.0, 1.2 cross-drilled from the rear face at z 11.9 and plugged (press pin), 1.2 vertical from the chimney floor at x 75.0.
- **Shoe RR-HD-S-111**: datums A (x-stop shoulder face, x 65.7), B (shoe side faces), C (underside z 16.00); hard anodise 25-40 um all over in both builds
  (threads masked only): the shoe faces that touch the body channels are insulating, no chromate bond faces.
- **Spreader RR-HD-S-121**: 2.00 sheet, chromate both sides (no anodise). Eight clinch standoffs M2.5 x 2.5, tops z 34.50 +-0.05, POS 0.2 (board datum).
- **Lid RR-HD-S-122**: 2.00 5052-H32, chromate inside, black anodise or powder outside; 35 holes 3.4. Flatness 0.2.
- **Cassette RR-HD-P-201**: 6061 from 4 mm, black anodise, film land masked (bond), four CSK seats; the seat bosses set the film plane (z 10.00).
- Window plane, board standoffs and receiver shoes carry GD&T on the drawings; the head's contribution to the film-to-floor gap is +-0.25 worst case /
  +-0.11 RSS (calculated, head_report.md section 7).

## 4. FRAME net and grounding scheme (answers CCR-HE-03 / IB-20; lead decision: the same scheme in both builds)

The contract makes the J1 electronics return (pin 2) the only DC ground path between head and robot, and EMI results must transfer between the builds,
so the head frame is **isolated from the chassis at the receiver shoes in both builds** and the board's single FRAME-to-ground bond R2801 is **fitted in both**.
(Lead decision IB-38; this section was already in that form, the bonded-shoe text is gone. Thermal consequence of the G10 isolator: head_report.md section 9.)

| | Prototype RR-HD-X-000 | Production RR-HD-P-000 |
|---|---|---|
| FRAME net = | spreader + EMI fences (rear comb, sides, front) + lid + blister + standoffs; the board's eight standoff screws | spreader + one-piece aluminium frame (masked lands) + lid + blister + standoffs |
| Receiver metal (shoes, T-heads, bridge, keeper) | isolated: 0.5 mm G10 RR-HD-S-113 under each T-head, insulating shoulder washers under the 8 T-head screws, 0.3 mm air round each T-head in its pocket, bridge 0.3 mm behind the frame, keeper 0.6 mm above the lid + 0.1 mm polyimide tape | identical, plus anodise on the shoes (all over) and in the T-head pockets as a second barrier |
| Smallest FRAME-to-receiver metal gap | tool-checked in checks.py ("FRAME net isolated ... BOTH builds"), see head_report.md | same check |
| Does the frame touch chassis metal when docked? | **No** | **No** (shoe contact faces hard-anodised; body channels need not be conductive) |
| R2801 | fitted | fitted |
| Cable shields | bonded to chassis at the receptacles; at the head SHLD_J1 / SHLD_J2 -> 1 Mohm // 10 nF -> FRAME (contract shield rule) | same |

The EMI enclosure required by `electronics/head_acq/design/layout_guidance.md` section 4: prototype = 0.5 mm 5052 fences round the board bonded to the
spreader at <= 50 mm (bond points tool-checked: front 48.0, side 31.2, rear 48.5 mm largest gap) + the aluminium lid on conductive gaskets; production =
the frame itself. The rear chimney is closed on five sides (comb liners in the prototype, the frame in production) with the spreader as the sixth; lane
shield cans RR-HEAD-SHLD-A clip onto the board. Openings: cable ports only, plus the 18 mm chimney notches in the spreader (under the board, closed by the
comb liner / frame) and the 27 mm saddle windows in the prototype front-fence foot (flat on the spreader) -- the last one is listed as a deviation for
the lead's acceptance.

## 5. Sealing and fastening

| Joint | Seal | Fastening |
|---|---|---|
| Lid to frame | lid gasket on the wall-top land, closed-cell silicone 1.2 -> 0.8 (conductive Ni/graphite silicone in production) | 34 x M3 button + bonded sealing washer at <= 40 mm pitch round a closed loop except the 60.5 mm J1 bay forced by CR-M03 (shear panel; tool-checked, DEVIATION for the lead): 16 into standoffs on the spreader, 18 into wall bosses (hard seats z 43.0 inside the gasket loop) |
| Window cassettes | cassette gasket 0.8 -> 0.45, lip in groove, film bonded | 4 x M2.5 CSK each; hard seat bosses |
| Lanes to each other | rib gasket strips under the spreader, 1.0 -> 0.6 | spreader: 10 x M2.5 CSK on the ribs, 6 x M2.5 rear zone, 8 x M3 into the T-heads |
| Cable entries J1 / J2 | split grommet (moulded silicone; TPU in the prototype) with three internal ribs, compressed by the lid | lid |
| Breather | ePTFE membrane vent M6 in the rear wall at y -65, internal baffle | thread + O-ring |
| Drains | four light-trap drains (one per chimney), three turns, no line of sight (tool-checked) | -- |
| Desiccant | 4 pouches in the front strip, indicator card visible with the lid off | -- |
| Insulating jacket (standard cold configuration, required below 0 C) | 3 mm closed-cell foam cap RR-HD-S-131 on the lid (top z 48.0) + front band RR-HD-S-132 (x 188.2..191.2, z 32.3..45); clear of the latch box, rails and receiver (tool-checked) | PSA; the cap's 9 mm holes leave the lid screws accessible |

## 6. Harness routing inside the head

- **J1 pigtail** (power, heater pair AWG 20, loop, PRES_ID): grommet in the rear wall at (71.7, +76.2, 39.0) (CR-M03) -> mated J2001 plug (stage 3,
  CR-M06: headers 7 mm forward, plug over x 81.8..91.7, y 62.3..90.0). The jacket ends in the grommet (its three ribs are the strain relief; no internal
  P-clip: no jacket inside); the conductors fan in over the 9.0 mm behind the plug (prototype 8.4 mm to the comb wall). Calculated in head_report.md
  (check "J1 landing harness buildable"): fits with thin-wall AWG 20 of OD <= 1.6 mm at R = 2 x OD; a standard PVC UL1007 AWG 20 does not.
- **Heater / NTC / cut-out** (J2601 beside J2001, plug over x 81.8..91.7, y 91.1..112.7): wires turn +y along the rear strip to the S0 chimney notch
  (film tails), the isolated-case thermal cut-out on a polyimide pad at (77..81.6, 81..87.5) (low side of the element) and the isolated-lug NTC at (81, 109).
  Lid standoff (77.5, +90.3) stands between the J2001 and J2601 wire groups.
- **J2 pigtail** (RS-485, BUS_5V, sync, J2_PRES): grommet at (71.7, -87.5, 39.0) -> J2501 GH-8 at u 262.3 (y -99.3); mated-plug keep-out of CR-M08
  (x 76.7..83.95, y -106.6..-92.0) is clear: the lid standoff moved from (77.5, -104.5) to (77.5, -109.2).
- **SiPM coax** (16 x U.FL class): from each carrier up through the chimney insert channel, R >= 6 mm bend, to the AFE_STRIP rear-edge connector pair at
  the lane centre (u +-13).
- **Rail switches** (NC loop): front switch at (183, +87.5) and lid interlock at (183, -87.5) in the front strip; side switches at (73.8, +-156.75) with
  leads up the potted channel into the rear corners, along the side strips, along the front strip, into the front-edge connectors J2002 (front, u 154.5), J2003 (left,
  u 171.5), J2004 (right, u 144.6 = y +18.4, S2-L6) and J2201 (lid, u 122.0); lead lengths in head_report.md section 12. In the prototype the loop leads enter the fence enclosure through a 3 mm notch in the front-fence wall at y +-14 (**not modelled**: open item
  for the fence DXF). Loop wires are potential-free and stay away from the AFE strip.

## 7. Variant BOM

`bom_production.csv` and `../prototype/purchased_and_fabricated.csv` list every part with quantity, make, candidate supplier part and verification status.
Rail variants (both builds): wear inserts are reversible (edge "3 DOWN" = 7 mm floor clearance, flipped = 5 mm); side strips RR-HD-S-431/432 (3 mm) or
RR-HD-S-433/434 (5 mm), same holes and tabs. Differences between the builds:

| Function | Prototype (RR-HD-X) | Production (RR-HD-P) | Requalify if changed? |
|---|---|---|---|
| Frame | two PA-CF halves, tongue-and-groove + ship-lap, 2 dowels, 56 heat-set inserts | one CNC 6061 part, tapped threads | yes: light tightness (E1), corner deflection, film plane |
| Shoe isolation | G10 isolators + insulating washers | identical (shared RR-HD-S-113) + anodised shoes and pockets | no (same scheme); E7 on every head |
| Insulating jacket | RR-HD-S-131 / 132 | identical | yes if changed: E8 heater duty at the cold set-point |
| EMI enclosure | 0.5 mm fences + conductive gaskets | frame + conductive lid gasket | yes: B11 bench EMI test |
| Lane rings, barrier, chimney insert | PETG-CF / PA-CF printed | MJF PA12 dyed black | yes: E1 (opacity) |
| Cassette | PETG-CF printed | 6061 black anodise | yes: film plane E4, E1 |
| Rail inserts, bail blocks, saddles | PA-CF printed | POM-C black | rail force / travel E2 |
| Grommets | TPU 95A printed | moulded silicone | E3 seal |
| Lid standoffs | 11 x M3 x 10.5 on fence feet + 6 x M3 x 11 | 17 x M3 x 11 | no |
| Lid gasket | black closed-cell silicone | conductive silicone | E3, B11 |

**Shared parts** (identical drawings, interchangeable between builds): RR-HD-S-111 shoe, -114 bridge, -115 keeper, -121 spreader, -122 lid, -123 blister,
-401 rail bar, -402 guide rod, -403 bail, -404 bail clip, -431..434 side rails, RR-HEAD-SHLD-A shield can, all PUR items except the standoffs, gaskets and
the isolation washers. A change to any shared part, to the OEM optics, to the film, to the cassette or to anything in the light-tight volume requires
requalification by E1 + E4; a change to the receiver (shoe, bridge, keeper) requires the interface checks of `mechanical_interfaces.md` section 1 and E5.

## 8. Service access

| Task | Access | Tools |
|---|---|---|
| Change an entrance film / window | from below, head on the bench cradle or transport cover: 4 x M2.5 CSK per cassette; lid stays closed, light seal unaffected | 1.5 hex, torque driver |
| Flip / change rail inserts (3 <-> 5 mm), side strips | from the front / sides, 2 x M3 per insert | 2.5 hex |
| Board, shield cans, desiccant, switches | lid off (34 x M3 through the jacket holes), keeper swung back first; the jacket cap stays on the lid | 2.0 hex |
| Lane optics | lid, board (8 screws, unplug coax), spreader (24 screws) off, then from above | as above |
| Vent | from outside | 8 mm spanner |
| Shoes / bridge / keeper | rear, without opening the head | 2.5 / 3 hex |

Every intervention that opens the light-tight volume (lid, spreader, cassette) is followed by E1; a cassette or film change also by E4 and a service-ID entry
(head_icd.md section 2).

## 9. End-of-line tests (every head; the dummy head gets E2, E5, E6, E7)

| Id | Test | Method | Acceptance (proposed, to be confirmed with the first heads) |
|---|---|---|---|
| E1 | Dark-count light tightness | head powered, bias at the operating point, 20 C; 10 min dark counts per channel in a dark box; then the same with the box lit (1000 lux LED panel, then a 500 lm torch swept along every joint of the light-path table L01..L22 in head_report.md section 6, 30 s per joint) | lit / dark count-rate ratio <= 1.05 per channel and no joint-correlated increase; floor/reference cross-talk with an LED pulser per lane below the RFQ figure |
| E2 | Rail switch travel and force | force gauge on a linear stage at the bar centre and both ends, and laterally on each side strip; loop resistance logged | front: trip <= 2.0 mm (calculated 1.13 nominal), >= 15 mm after trip, return force 3-13 N; sides: trip before the 0.95 mm stop; every zone opens HEAD_LOOP |
| E3 | Seal check | vent replaced by a test fitting, +20 mbar, 2 min stabilise, 2 min decay | <= 2 mbar/min (sets the gasket and grommet compression; value to be set on the first unit) |
| E4 | Standoff height / film plane | head on the bench cradle (datums A/B/C), wedge gauge or followers at the four outer window corners and the row centre | 10.00 +-0.30 mm (production stack +-0.25 worst case, calculated) |
| E5 | Mass and CG | three scales under the shoe lands and the front post | within +-3 % / +-3 mm of the calculated values (head_report.md section 3) |
| E6 | Loop and presence | J1 pins 5/6 and 7/2 | 1.00 kOhm +-1 %, 4.70 kOhm +-1 %, J2 pin 7-4 linked |
| E7 | FRAME isolation | insulation tester FRAME (spreader) to each shoe shoulder and to the keeper, 50 V | >= 10 Mohm, both builds (R2801 fitted) |
| E8 | Heater chain | zone resistances, cut-out continuity, NTC at 20 C | per heater datasheet; NTC 10 k +-3 % |
| E9 | Heater insulation (review M5) | before the board is connected: 100 V insulation tester, J2601 plug pins (element, cut-out, NTC, shorted) to the spreader | >= 10 MOhm, both builds; films, isolated-case cut-out and isolated NTC lug on 0.1 mm polyimide pads (BOM PUR-HEATER / PUR-TCO / PUR-NTC-10K / PUR-PI-PAD, part data UNVERIFIED) |
