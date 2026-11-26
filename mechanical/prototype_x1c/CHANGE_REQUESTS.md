# RR-X prototype body -- deviations from `mechanical/common` and change requests

Owner of `mechanical/common` (params, interfaces): mechanical lead. This package imports every interface value from
`mechanical/common/params.py`; nothing in that directory was edited. Items below are either **deviations** this package
made inside its own parts (outer skin and every interface position unchanged unless stated) or **requests** that need the
lead's decision. Numbers are design values: *calculated* or *tool-checked* as marked; see `out/prototype_report.md`.

## Deviations taken in this package (no action needed unless the lead objects)

| ID | Item | Interface says | Prototype does | Why |
|---|---|---|---|---|
| D-01 | Chassis front beam plan form | front beam x 2.0..62.0, \|y\| <= 99.5 at plate elevation | beam is part of the 4 mm 6061 chassis plate, extended aft to x = -26 and widened to \|y\| <= 119.5 | (a) the interface itself puts the front cliff ToF apertures at y = +-109.5 "on the chassis front beam, outboard end", outside the 99.5 beam; (b) the motor pods (y 98.5..117.5) must stand on the same beam (interface section 3). Tool-checked: 3.0 mm to the tyre inner face, no interference. |
| D-02 | Receiver channel x extent | channel outer envelope x 2.0..64.0, x-stop (datum A) at x = 65.7 | channel block x 2.0..65.7: an x-stop flange x 59.7..65.7 with two 16 x 14 pads each side of the shoe | the interface's own datum A (channel front faces at 65.7) lies 1.7 mm ahead of its stated envelope; the flange is what makes datum A. Head envelope starts at 66.0, so 0.3 mm remains (tool-checked: no head/channel interference). |
| D-03 | Battery hump rear end | hump outer x -233.0..-70.5 | printed hump x -230.0..-70.5; the 3 mm ring x -233..-230 is the separate PAHT-CF hatch frame (the gasket land of the door) | the outer form is unchanged; the frame carries the bail cam ears and closes the tunnel, hump and jambs in one stiff ring. |
| D-04 | Charge-inlet cover height | parts.yaml candidate cover 36 x 36 x 8 | 36 x 36, 5 mm above the receptacle nose (3 mm air) | keeps the closed cover inside the 295 mm tyre width (shared rule 8.3). Receptacle position and axis unchanged. |
| D-05 | Wheel hub | wheel/hub "select to fit", candidate Pololu #1999 | Pololu #1999 confirmed as the M3 version (25.4 x 9.2 mm, six M3 tapped holes, 6.8 g, VERIFIED from the Pololu spec page 2026-11-26); bolt circle 19.05 mm still UNVERIFIED -> 3.6 mm rim holes | parts.yaml hub length 16 mm is not the #1999 (9.2 mm); the wheel envelope (104 x 25) is unchanged. |

## Requests to the lead

| ID | Request | Why (evidence) | Affects |
|---|---|---|---|
| CR-01 | Record in `mechanical_interfaces.md` section 1 that the channel block runs to the x-stop plane (x 2.0..65.7) and the front beam to \|y\| 119.5 (D-01, D-02) | interface text is self-contradictory as written | production body (same interface), head engineer (nothing changes for the head) |
| CR-02 | `parts.yaml` `wheel.hub_l`: 16 -> 9.2 and hub = Pololu #1999 M3 (D-05) | verified spec page | layout envelope only |
| CR-03 | `parts.yaml` `charge_inlet.cover`: 36 x 36 x 8 -> 36 x 36 x 5 (D-04) | tyre-width rule | layout envelope only |
| CR-04 | **IB-10 carry attitude: move the grip bar aft** from centre x = -11 to x = **-30** (bar x -42.5..-17.5, z unchanged), and define the grip hand zone as 45 mm in front of and below the bar and 25 mm behind it below z 153 (fingertips), instead of 45 mm behind as well | see section "IB-10" below and report section 7 (calculated) | `P.GRIP`, `layout.py` hand-zone boxes, look-ahead ToF stays at x 1.5 on a forward fairing extension, both body builds |
| CR-05 | CCR-E08 answers (chassis electronics): see section "CCR-E08" below | tool-checked keep-outs in `out/prototype_report.md` | chassis electronics |

## IB-10 (carry attitude)

Filled in from the model by the final build: see `out/prototype_report.md` section 7 for the calculated hang angles with the
bar at x = -11 (as built, interface value) and with the CR-04 position.

## CCR-E08 (chassis electronics, board-level fit)

See `out/prototype_report.md` section 10 (tool-checked keep-out boxes over RR-CHS-MAIN).
