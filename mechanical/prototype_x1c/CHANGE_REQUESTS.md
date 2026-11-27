# RR-X prototype body -- deviations from `mechanical/common` and change requests

Owner of `mechanical/common` (params, interfaces): mechanical lead. This package imports every interface value from
`mechanical/common/params.py`; nothing in that directory was edited. Items below are either **deviations** this package
made inside its own parts (outer skin and every interface position unchanged unless stated) or **requests** that need the
lead's decision. Numbers are design values, *calculated* or *tool-checked* as marked; see `out/prototype_report.md`.

## Deviations taken in this package (no action needed unless the lead objects)

| ID | Item | Interface / common says | Prototype does | Why |
|---|---|---|---|---|
| D-01 | Chassis front beam plan form | front beam x 2.0..62.0, \|y\| <= 99.5 | the beam is part of the 4 mm 6061 chassis plate, extended aft to x = -26 and widened to \|y\| <= 119.5 | the interface itself puts the front cliff ToF apertures at y = +-109.5 "on the chassis front beam, outboard end", outside the 99.5 beam, and the motor pods (y 98.5..117.5) must stand on the same beam (interface section 3). 3.0 mm to the tyre inner face (tool-checked, no interference). |
| D-02 | Receiver channel x extent | channel envelope x 2.0..64.0 with the x-stop (datum A) at x = 65.7 | channel block x 2.0..65.7: x-stop flange x 59.7..65.7 with 16 x 14 pads each side of the shoe | the interface's own datum A (channel front faces at 65.7) lies 1.7 mm ahead of its stated envelope; the head envelope starts at 66.0 (0.3 mm left). |
| D-03 | Battery hump rear end | hump outer x -233.0..-70.5 | printed hump x -230.0..-70.5; the 3 mm ring x -233..-230 is the separate PAHT-CF hatch frame (gasket land of the door) | outer form unchanged. |
| D-04 | Charge-inlet cover height | parts.yaml candidate cover 36 x 36 x 8 | 36 x 36, 5 mm above the receptacle nose (3 mm air), seated on a flat spot face (plinth) | keeps the closed cover inside the 295 mm tyre width (shared rule 8.3). Receptacle position and axis unchanged. |
| D-05 | Wheel hub | wheel "select to fit", hub_l 16 | Pololu #1999 confirmed as the M3 version: 25.4 x 9.2 mm, six M3 tapped holes, 6.8 g (VERIFIED, pololu.com spec page, 2026-11-26); bolt circle 19.05 mm UNVERIFIED -> 3.6 mm rim holes | wheel envelope (104 x 25) unchanged. |
| D-06 | Grip bar construction | mech_calcs: printed bar with a 10 mm core / layout: 25 x 22 bar | 14 mm solid 6061-T6 bar on 2 x M6 into its tapped ends, printed 25 x 22 sleeve; side-plate cheek front edge x -8.6 | the first engineer's 16 x 2 tube on an M8 rod collided with the look-ahead ToF seats behind the (interface) apertures at x 1.5; the look-ahead seats are made shallow (6.3 mm) and the bar moved to x -15.5. Bar section and position of the hand surface unchanged. |
| D-07 | Battery cassette latch | "positive latch with captive release; hatch cannot close unless the cassette is latched; rear pull handle >= 45 mm glove clearance" | captive spring index plunger (pull knob) through the hump roof into the cassette lid; fold-flat pull handle (47.5 mm finger gap); interlock finger on the door that stops 0.5 mm behind the home position of the cassette | the first engineer's cam bail could not stand up inside the tail cap (the tail is about 11 mm deep behind the cassette at \|y\| 51, z 102: tool-checked clash with the door). Interface values (cassette envelope, removal, coupler) unchanged. |
| D-08 | Saddle-cover fixing | "gasketed, captive screws" | 6 captive M3: 4 on the front ledge (ahead of the board edge x 33) and 2 in the rear corners | the RR-CHS-MAIN 18 mm top envelope reaches the ledge underside (z 102.6): screw bosses can only hang below the ledge where the board is limited to 12 mm (rear corners, CCR-E08) or outside the board. See CR-06. |
| D-10 | Battery tunnel at the tail | bay guide walls \|y\| 55.5..58 from the plate to z 100, x -230..-73.5 | walls, feet and gate trimmed to the Rev E inner skin; the hull keeps its full skin there | tool-checked: the wall corner at (-230, +-58, 37) lies 5.8 mm outside the inner skin (half-breadth 52.2 at that height). The common layout's containment tool clamps z to the floor and did not see it. Cassette envelope and removal path unaffected (sweep checked). |
| D-11 | Lid perimeter screws | -- | 7 radial M3 per side (nose 20/40 deg, shoulder 50 deg, deck 85/100/120/140 deg); no station in the tail quarter | stations at 150..160 deg collided with the rear proximity ToF seat or reached into the hatch opening; the tail is held by the hatch frame, jambs and hump. |
| D-09 | Shell split stations (design values, not interface) | -- | lid: nose cowl x >= 47, shoulders x -36..47, rear decks x <= -36, hump; lower hull split at x = -71 and y = 0 | the -45 station of the first engineer cut through the RR-PANEL tray; -36 is between the grip slots (x -21.5) and the tray (x -42.5). |

## Requests to the lead

| ID | Request | Why (evidence) | Affects |
|---|---|---|---|
| CR-01 | Record in `mechanical_interfaces.md` section 1 that the channel block runs to the x-stop plane (x 2.0..65.7) and the front beam to \|y\| 119.5 (D-01, D-02) | the interface text is self-contradictory as written | production body (same interface); nothing changes for the head |
| CR-02 | `parts.yaml` `wheel.hub_l`: 16 -> 9.2 and hub = Pololu #1999 (M3) (D-05) | verified spec page | layout envelope only |
| CR-03 | `parts.yaml` `charge_inlet.cover`: 36 x 36 x 8 -> 36 x 36 x 5 (D-04) | tyre-width rule | layout envelope only |
| CR-04 | **IB-10 carry attitude: move the grip bar aft** from centre x = -11 to x = **-30** (bar x -42.5..-17.5, z unchanged) and define the grip hand zone as 45 mm in front of and below the bar and 25 mm behind it below z 153 (fingertips; the palm is above the hump top at z 150) | hang angle with the prototype head about -21 deg now, about -10 deg with the bar at -30 (calculated, report section 7). Ballast would need about 1.9 kg in the nose. | `P.GRIP`, `layout.py` hand-zone boxes, both body builds; the look-ahead ToF can stay at x 1.5 on a forward fairing extension |
| CR-05 | CCR-E08 answers for chassis electronics: (a) the combined 8-way Mini-Fit at the right-rear edge has 23 mm of free space beyond the board edge for the mated plug and the 2-into-1 loom (tool-checked); (c) 12 mm clear height is kept over the rear corners and the front-centre strip (tool-checked keep-out boxes, report section 10); the body puts two cover-screw bosses over the rear corners with their underside 13.0 mm above the PCB | as checked | chassis electronics |
| CR-06 | `board_envelopes.yaml` RR-CHS-MAIN: add the rear-corner zones u 0..45 / 112..160, v 0..20 / 0..22 with `top_max: 12.0` (the electronics engineer's own CCR-E08 request) | the saddle-cover rear screws rely on it (D-08) | chassis electronics, both body builds |

| CR-07 | `mechanical_interfaces.md` section 5: note that the bay guide walls end inside the hull skin at the tail corners (D-10) | interface geometry vs the Rev E section law | production body |
| CR-08 | IB-12 / CCR-E08: the Pause/Stop device body (interface position (-84, -112, 122), parts.yaml depth 50 mm UNVERIFIED) reaches into the rear-right connector space behind the board (u 142..160, x -79..-67, z 84.6..96.6); confirm the real depth of the Harmony XB5 body or move Pause/Stop 15 mm aft | tool-checked keep-out box, report section 10 | chassis electronics, lead |

## IB-10 (carry attitude) and IB-12

IB-10: calculated hang angles are in `out/prototype_report.md` section 7 (with the bar at x = -11, as built, and with the
CR-04 position). IB-12: the rear-edge connector space of 18 mm each side of the hump is free in this body (tool-checked
keep-out box behind the board edge, report section 10).
