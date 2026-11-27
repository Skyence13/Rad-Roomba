# Independent review: CAD against PCBs and harness (fit, assembly, service)

Reviewer: independent second engineer (mechanical / electromechanical integration). I designed none of the parts reviewed.
Date: 2026-11-27. Repository state: commit f379fc1 plus the working tree of that day.

Interface under review: do the boards, connectors, mated plugs, cables and their bend space, fasteners and tools fit in the
body and head models, in the X1 Carbon prototype (RR-X) and the production build (RR-P), and do the mechanical model, the
board files and the harness tables describe the same interface.

## 1. Scope and method

**Measured in the geometry (tool-checked by me, CadQuery/OCC, scripts in the session scratch directory `review_fit/`):**

* The four KiCad boards were parsed directly (`RR-CHS-MAIN.kicad_pcb`, `RR-HEAD-ACQ.kicad_pcb`, `RR-TOF-A.kicad_pcb`,
  `RR-PANEL.kicad_pcb`): outline, holes, every footprint's courtyard, side, and the 3D envelope height that the electronics
  build attaches (`_h<height>.step`). Heights are therefore the electronics team's bounding-box envelopes, not manufacturer
  data.
* The prototype body was measured on the per-part base_link STEP files of the latest build
  (`mechanical/prototype_x1c/out/parts_base_link/*.step`, 17:21 build; older files still on disk were ignored). The
  production body was measured on `mechanical/production/step/RRP-*.step` (all are in base_link). The head was measured on
  `mechanical/head/prototype/step/*.step`.
* Methods: boolean intersection of fastener / tool / plug solids that I built from ISO dimensions with the model solids;
  point classification of the harness route polylines of `harness/hdata_cables.py` (the paths that produce the lengths in
  `cables.csv`) against every solid of the prototype body; thin-slab sections of the shells for the service opening; panel
  device bodies lengthened by +5 / +10 mm and intersected with the body.

**Read from documents (not measured):** purchased-part dimensions (`parts.yaml`), harness construction, assembly
sequences, the head check code (`asbuilt.py`, `checks.py`) and its report, the CR / backlog records.

**Not done:** I did not run any `build.sh`; I did not route cables in 3D; mated-plug and wire envelopes of the board
connectors are estimates from the families (marked *estimate*) because no manufacturer drawing exists in the repository
(IB-35).

Fastener stack used in my checks (ISO values, recalled): ISO 4762 M4 head 7.0 x 4.0; DIN 6796 M4 1.3 high; ISO 7089 M4
0.8; ISO 7045 M4 pan head 7.0 x 3.1; ISO 10511 M3 nyloc 4.0 high, 5.5 AF; G-10 bushing flange 10 x 1.0 (params).

## 2. Summary

| Severity | Count |
|---|---|
| Critical (cannot be assembled / a board or connector does not fit) | 4 |
| Major | 11 |
| Minor | 9 |
| Observation | 5 |

The model checks that report PASS do not see any of the Critical items, because (a) the body carries RR-CHS-MAIN as an
18 mm / 12 mm keep-out box, not the board file; (b) fasteners are hardware-list rows, not solids, so screw heads, nuts and
tool access are never intersected; (c) the ToF carrier is a 3.3 mm slab without its connector; (d) the harness lengths are
straight polylines that are never tested against the solids.

## 3. Findings

### Critical

**C1 - RR-CHS-MAIN mounting holes H1/H3 sit on the bridge posts; the board cannot be fastened as specified (both builds).**
*Measured.* Bridge posts 0/1 (`dims.POSTS`, Ø8 x 41, M4 tapped) are at (-64, ±76); board holes H1/H3 are at (-63, ±76),
1.0 mm away (board file and `board_envelopes.yaml` agree). Consequences:
* The M3 nyloc nut that `hardware.py` / `hardware_production.md` put under the tray at H1/H3 would be inside the post:
  92 mm3 overlap of an M3 nut envelope with `bridge_post_0`.
* The M4 x 8 pan head that holds the tray to post 0 sits on top of the tray exactly under the board standoff:
  69 mm3 overlap with `board_standoff_0`.
* The tray holes merge: at y = 76 the tray (`bridge_tray.step` and `RRP-F04`) has no material from its edge x -69.0 to
  x -61.4, so the 5.5 mm standoff at H1 bears on about 1 mm of tray.
* Posts 2/3 at (30, ±45) are under the PCB at board (u, v) = (35, 97) / (125, 97): a 3.1 mm M4 pan head on the 2 mm tray
  reaches z 83.1 against the PCB underside at z 83.0 on 3.0 mm spacers (0.1 mm interference, the board rocks; the
  assembly check "board lies flat" fails), and C177 (bottom side) is 0.1 mm radially from the head edge.
* All four tray screws are under the board, while the nuts of H2, H4..H6 are under the tray in pockets closed by the hump
  wall, the grip feet, the motors and the front bulkhead: the board can be fitted only to a tray that is already off the
  robot, and the tray can then not be screwed down. There is no assembly order that works.

Proposed change (body mechanical, both builds): replace the six nyloc joints by M3 self-clinching standoffs or blind
threaded bushes in the tray (screwed from above, no nut under the tray); move posts 0/1 at least 8 mm off H1/H3 (for example
to (-64, ±62), clear of the tray pass-throughs) and posts 2/3 outside the board outline or under a board area with no part
within 5 mm, or use countersunk tray screws flush with the tray top. Re-run the interference check with fasteners modelled
as solids.

**C2 - Receiver thermal-break screws collide with parts fitted later; two screws per side cannot be installed (both builds).**
*Measured.* Plate holes 1-3 / 21-23 (`chassis_plate_holes.csv`), M4 x 18 + DIN 6796 + washer + G-10 top-hat bushing
from above (head stack top z 44.1):
* (14, ±104.5): the motor pod stands on it. Head stack overlap with `motor_pod_L` 351 mm3 (prototype) / 363 mm3 (RRP-P01L)
  of a 366 mm3 stack; there is no counterbore. In addition the pod foot screw at (20, ±103.5) is inserted from below, but
  the G-10 shim (`receiver_shim_L_out`, 229 mm3) and the channel ear (480 mm3) cover its insertion path. Fitting the
  receiver first blocks the pod; fitting the pod first covers the receiver screw. The countersink of the pod screw
  (Ø about 9 at the plate underside) breaks into the Ø6.0 bushing bore by 1.42 mm; the web at the bores is 0.83 mm.
* (14, ±70.5): head stack overlap with the lower hull front piece (`lower_hull_FL` / RRP-S01) 247 mm3, and the motor can
  is 0.0 mm above it (0.1 mm3 contact); the hex-key column above the head is fully blocked by the motor (1170 mm3).
* (50, ±70.5): the head sits in a blind hull pocket; the tool column is blocked by hull material from z 44.1 (508 mm3).

Production `assembly_sequence.md` 8.3 ("re-torque the receiver screws after the first thermal cycle") cannot be done
without removing motors, pods and the RTV-sealed one-piece hull; the prototype `assembly.md` stage-1 isolation check and
the land-height / latch-preload re-check of IB-64 have the same problem. Proposed change (body mechanical): move the
outboard screw out of the pod footprint (for example x 32, outside x -26..26) and the inboard x 14 screw forward of the
motor can (x >= 24); give the hull pockets with tool access from above, or turn the joint round (screw from below into
inserts in the plate with the bushing in the ear); check every fastener head and tool column as solids.

**C3 - RR-TOF carrier does not fit the four look-ahead seats, and no seat has room for the mated plug (both builds).**
*Measured on the board file, read from the seat code.* `RR-TOF-A.kicad_pcb`: J1 is a horizontal JST GH SM06B on the
**bottom** (window-remote) side, 3D envelope 4.25 mm, courtyard on the board edge (v 0.45..6.85 of 14). Seat
(`rrx/sensors.py`, shared by production): board front at 2.6 mm behind the window plane (1.1 window recess + 1.5 foam),
PCB back at 4.2 mm, header back at 8.45 mm.
* Look seats (`look_f`, `look_r`: 4 sensors, RRP-P54 x 4): the clip plane is at 6.3 mm, an 8 mm strip across the board
  centreline. The header occupies the band 0.15..6.55 mm off the centreline in the short direction, so the clip lands on
  the header with 2.15 mm interference: the board cannot be clamped.
* All seats: the pocket is the board + 0.5 mm (18.5 x 14.5). The GH plug enters along the board plane from the long edge
  on the connector side; the header mouth is about 2 mm inside that edge (fab outline), so the mated plug and its wire
  exit stand beyond the board edge where the seat wall is 0.25 mm away (*estimate* of the GHR housing, UNVERIFIED). No
  seat has a relief for it.
* Standard seats (7 sensors): the clip at 9.5 mm is 1.05 mm behind the header back; nothing clamps the board except the
  1.5 mm foam (see m9).
* The carrier depth is 1.6 + 4.25 + 1.0 (sensor) = 6.85 mm plus the 1.5 mm foam, against the "6 mm depth behind a 1 mm
  window" of `board_envelopes.yaml` / `parts.yaml` `tof_board.depth`.

Proposed change (chassis electronics with body mechanical): either a vertical (top-entry) GH header on the back with the
cable leaving rearward through the open seat back, or a slot in each seat wall on the connector side (>= 10 x 6 mm, depth
from 4.2 to 9 mm) and the look-seat clip moved to 9.0 mm with a spacer; update the envelope to the real stack.

**C4 - Grommets for the dock-switch and front cliff ToF leads are blocked from both sides (both builds).**
*Measured.* The only plate pass-throughs for these leads are the two 8 mm grommets at (-2, ±80) (hole table rows 20/40).
Above: the motor can is 3.45 mm above the plate top (215 mm3 of motor in a Ø8 x 8 column) and the lower hull has
material at z 37..41 (81 mm3; same in RRP-S01). Below: the dock switch bracket fills z 20..33 under the left hole (382 mm3)
with the switch itself (80 mm3). A lead cannot enter the grommet, and the HEAD_DOCK lead (a safety-chain element) has no
other modelled route. The harness path W-020 ignores the grommet and passes through the PCB keep-out, the tray, the hull
(15 mm), the plate (10 mm) and the channel. Proposed change (body mechanical + harness): move the pass-throughs to a free
plate area (for example x 25..30, y ±80, ahead of the can, behind post 2/3) with a cable channel in the hull, add the
dock-lead channel in the bracket, and re-path W-020 / W-030 / W-031 through it.

### Major

**M1 - RR-CHS-MAIN cannot come out through the service opening; edge plugs are not reachable under the ledge.**
*Measured.* Section of the shoulders / rear decks / hump at the ledge (z 104) gives a service opening x -62..40,
|y| <= 75 (102 x 150 mm) in both builds (RRP-S02 identical). The board is 100 x 160 at x -67..33: 10 mm wider than the
opening and 5 mm under the rear ledge. A tilted extraction needs >= 21 deg of roll (60 mm of edge lift), but the grip bar
is 48 mm above the opening (z 153) across x -42.5..-17.5 and the cheek fairings leave 152.3 mm between them (|y| >= 76.16)
from z 115.8. No document or model shows a removal path. Edge plugs: J_PWR (Mini-Fit Jr, 12.8 mm) mates at y = -80,
5..17 mm outboard of the opening edge, with 5.2 mm between its top and the ledge (z 102.6): its latch cannot be pressed by
hand; J_MOT_L/R, J_CM5, J_LIDAR (7 mm) have 11 mm. `board_envelopes.yaml` ("service access from above, no shell split
needed") and `mechanical_interfaces.md` section 3 claim an access the geometry does not give. Proposed change (body
mechanical): make the opening >= 106 x 166 mm (move the side ledges outboard of the board edge, rear ledge behind x -67),
or define board service as "remove grip fairings and shoulders" and say so; give each edge plug >= 20 mm finger room above.

**M2 - CM5 carrier connectors have no room; selector and REARM bodies are 2.6 / 3.5 mm above it.**
*Measured.* Around the carrier box (x -154..-69, y 59..115, z 52..76): long edge +y 3.7 mm to the lower hull, long edge
-y 1.0 mm to the tunnel wall, end +x 1.0 mm to bridge post 0; only the -x end has >= 50 mm. Above: `mode_selector_body`
at 2.6 mm and `rearm_start_body` at 3.5 mm. If the RJ45 and USB-A sit on a long edge of the Waveshare carrier
(UNVERIFIED), W-012, W-013 and W-014 cannot be plugged; W-010 lands on the 40-pin header on the carrier top, 2.6 mm under
the selector body. The harness end point for all four is the centre of the carrier box (-111, 87, 66), not a connector.
Depth sensitivity (Q3): selector +5 mm intersects the carrier (60 mm3, 1122 mm3 at +10), REARM +5 mm (43 / 419 mm3);
carrier height +3 mm (24 mm is UNVERIFIED) reaches the selector. Proposed change (body + chassis electronics): fix the
carrier orientation with the connector edge toward -x and model the plugs; move the carrier down or the selector/REARM
outboard so that >= 15 mm is free above the 40-pin header.

**M3 - Forward look-ahead ToF leads (W-034 / W-037): the only passage is a 3.1 mm slot; the cables are about 30 mm short.**
*Read from code, measured path.* The shoulder slot (`shells.py` 331 / 588) is x -32..-18, y ±(84.6..87.7): 14 x 3.1 mm.
The GH-6 plug (about 9 x 4 mm, recalled) cannot pass it and the 6-core shielded cable (*estimate* 3.2-3.6 mm OD) barely.
The harness path runs straight from J_TOF4 (-2, 70.9) through the shoulder skin (16 mm, measured) to the sensor. Along the
slot and the fairing channel (x -30..-2, z 100..156) the path is about 112 mm, so 112 + 2 x 15 + 30 = 172 -> 180 mm
against 150 mm specified (*estimate*). Proposed change: widen the slot to >= 10 x 6 mm with a grommet, re-path and re-cut
W-034 / W-037 (still under the 300 mm limit).

**M4 - Harness route polylines pass through solid parts; several lengths are not achievable.**
*Measured* (point test every 1.5 mm, 4 mm skipped at each end). 30 of the 41 robot cables with a path cross at least one
solid. The ones that change a length or a decision:

| Cable | Stated (mm) | Crosses (length in the solid) | Consequence (estimate) |
|---|---|---|---|
| W-001 / W-003 pack feed / aux | 300 / 300 | `motor_R` 36 mm, tray | real route in front of the can (x 25) and up beside the pod: >= 350 mm; W-001 fuse distance and trunk length to re-check |
| W-039 REAR_C ToF | 290 | battery hump, cassette, pack, cassette lid, LiDAR, plunger | around the hump side and over the roof to the brow: about 310 mm, above the 300 mm I2C limit |
| W-032 CLIFF_RL / W-036 LOOK_RR | 290 / 290 | tunnel + cassette corner; HANDS-ON body 30 mm | after detours about 300 mm, at the limit |
| W-004 / W-005 inlet | 280 / 270 | `pause_stop_body` 28 mm (Pause moved by CR-08, paths not re-done) | +15..20 mm |
| W-017 HANDS-ON, W-018 REARM, W-021 / W-038 | 250 / 240 / 330 / 270 | E-stop, selector, REARM bodies 15..30 mm | +10..20 mm each |
| W-011 / W-012 LiDAR | 290 / 260 | hump, cassette, pack, LiDAR body | route outside the hump: +30..50 mm |
| W-020 dock, W-030 / W-031 front cliff | 270 / 190 / 190 | PCB keep-out, tray, hull, plate, channel, sensor | no modelled route (C4) |
| W-010 / W-013 / W-014 | 190 / 190 / 200 | carrier box | end point undefined (M2) |

Proposed change (harness + body): route every cable on the solids (or at least test the polyline as I did), add the
corridor geometry and P-clip points to both bodies, and keep a length margin of >= 30 mm under the 300 mm ToF limit.

**M5 - Head rail-switch and lid-switch leads are sized to stale switch positions.**
*Read and calculated.* `hdata_cables.py` hard-codes the switches at (184.2, 0, 21) and (131.2, ±168.5, 21);
`frames.yaml` / `params.HEAD_RAIL_SWITCHES` (IB-40, closed) have (182.6, 87.5, 37.3) and (73.8, ±156.75, 20.75), and
`params.HEAD_LID_SWITCH` exists although W-107 says "switch position not in the sources". To the current positions:
W-104 needs about 160 mm (specified 90), W-105 / W-106 about 330 mm (270 / 280); the head's own route calculation
(`calc.harness_routes`, head report line 261) gives 92 / 292 / 302 / 142 mm route only. Three numbers for the same lead,
and the harness is 50-70 mm short. The D2HW lead length is UNVERIFIED. Proposed change (harness): read the switch
positions from `frames.yaml` like the ToF positions and rebuild.

**M6 - J1 / J2 pigtails in the docked geometry: no feasible modelled route; pinch points; splice in the bend.**
*Measured.* The head model's pigtails (`PUR-CABLE-J1/J2`), placed docked, intersect the body: J1 with `lower_hull_FL`
504 mm3 and the chassis plate 30 mm3; J2 with `lower_hull_FR` 352 mm3, the plate 17 mm3 and `shoulder_R`. The head
model's plug ends at x -50..0.7, z 129..190, not at the body's J1 receptacle (x 66..131, z 112..184): the two models of the
same cable disagree, and no check compares them. Section at y = 76.2: the gap between the head rear face (grommet x 68.7,
frame x 70.2) and the body nose is 11 mm at z 48 (hull at x 57.5), 7 mm at z 53, 4 mm at z 60 (nose cowl x 64.5); above
z 50 the space over the head is open. With the stated exit "-x/+z" and the 40 mm bend radius of `parts.yaml`, the cable
needs about 12 mm of rearward travel to turn upward and meets the hull lip: the exit must be +z (or +z/+x over the head
top). Pinch: `mechanical_interfaces.md` section 1 and W-101 say "clipped to the shoe root"; the shoe root is at z 16..30
right beside the datum-A x-stop pads that seat on the channel front faces (x 65.7) under 100-200 N latch preload, so a
clipped cable is drawn into the seating plane. The AWG 18/20 splice "30 mm outside the gland" lands at about z 50..65,
x 60..68 in docked geometry, i.e. inside the bend and in the gap that closes during the last 66 mm of docking.
Proposed change (head mechanical + harness + body): exit +z through a strain relief on the rear wall top, clip to the
head rear wall above z 45 (not the shoe root), splice at >= 80 mm from the gland in the free run above the nose, model the
docked pigtail and the mated plug in one assembly and check it at the docked position and during the 66 mm slide.

**M7 - RR-PANEL J1 plug faces the tray wall; the tray notch is elsewhere.**
*Measured on the board, read from the tray code.* `RR-PANEL.kicad_pcb`: J1 (GH-10 side entry, top side) at u 21.5..38.5,
J2 (GH-2) at u 46..53, mating faces toward the v = 24 long edge (panel CR P1). `sensors.panel_tray`: the only cable
notches are at x -108..-96 (u 7..19 from the -x end, u 51..63 from the +x end); elsewhere the long wall (2.2 mm) stands
6 mm above the pocket floor. J1 meets the wall in either orientation. The board's M2.5 holes (3.5, 20.5) / (66.5, 20.5)
are not used by the tray, so the board has no retention. Proposed change (body + panel): notch at u 19..41 and 44..55 for
the fixed orientation, two M2.5 bosses at the board holes; the panel README asks mechanical to fix the orientation.

**M8 - Production assembly sequence has no harness steps; the one-piece lid makes several connections unreachable.**
*Read; geometry measured.* `production/assembly_sequence.md` step 6 lowers the one-piece lid (RRP-S02) with the J1/J2
receptacles, 5 controls, RR-PANEL, 5 ToF, LiDAR and inlet pre-fitted, "over the grip side plates" (top z 174, so the lid
must start >= 74 mm above its seat). The CM5 carrier (x -154..-69) lies outside the service opening (x >= -62): the RJ45
(W-012) and USB (W-013/014) can only be mated before the lid is lowered, with the lid hanging on 260 mm leads that have
50 mm of service loop (about 80 mm more needed, *estimate*). The prototype splits the lid in decks and a hump and asks for
60 mm service loops; production has no equivalent instruction. Proposed change (production body + harness): write the
harness steps, add in-line disconnects at the lid (or a lid-mounted bulkhead connector), and size the loops for the lift.

**M9 - Rear-edge loom has no room under the cover and ledge.**
*Calculated estimate.* Thirteen vertical headers stand on the rear edge at u 28..140 (J_MODE straddles u 20 as well) although `board_envelopes.yaml`
keep-out says "NO connectors on the rear edge between u = 20 and 140" (the rule's reason, the hump wall 3.5 mm behind the
edge, means all their leads must run along the edge to the corners). The rear-right corner then carries about 30
conductors (W-003/005/015/017/019/022/041/042) plus three ToF cables: a bundle of about 12-13 mm diameter (AWG 24 silicone
1.5 mm, AWG 26 1.2 mm, ToF 3.5 mm OD, fill 0.6; all ODs UNVERIFIED). Above the mated plugs the 12 mm zone leaves 8.4 mm to
the cover and 6 mm under the rear ledge (x <= -62), and `assembly.md` stage 5 forbids loom in the 12 mm zone. Proposed
change (chassis electronics + body): fan the rear connectors out to the side edges or raise the cover by >= 8 mm locally
over the rear band; show the loom in the model.

**M10 - Eight of eleven ToF carriers cannot be replaced without opening the shell; production makes it worse.**
*Read from the assembly documents and seat code.* Standard seats are clipped from inside: rear proximity (3) and rear look
(2) behind the decks and hump, rear cliff (2) in lower-hull bosses (prototype stage 4/7). In production all of these sit in
the one-piece lid or the RTV-bonded one-piece hull (`assembly_sequence.md` 4.1). Only the front cliff pods (from below)
and the forward look sensors (fairing removal) are serviceable. Proposed change (body): front-loading seats (carrier and
window from outside under a screwed bezel), or accept and write it in the service manual.

**M11 - The head board-fit tool check (`asbuilt.py` / `checks.board_fit`) covers bodies, not connections.**
*Read from the code.* Covered: 8 holes, 4 can outlines, mouse holes, 48 clips, J1 port, component bodies (courtyard x
3D height, top side), mated-plug keep-outs for J2001, J2601 and J2501 only. Not covered: (a) the six other mated GH plugs:
J1001..J1301 (GH-6, rear edge v 0.8..7.2, same orientation as J2501, so their plugs overhang the rear edge into the
7.9-9 mm chimney where the coax pairs come up) and J2002, J2003, J2004, J2201, J2402 on the front edge (plugs overhang
v 96 toward the front wall and the lid switch at x 183.25); (b) every wire: U.FL coax from the chimney over the rear edge
to jacks at v 1.6..5.9, heater film tails, cut-out and NTC leads (W-103), rail-switch and lid-switch leads; (c) bottom-side
parts (none exist today: the code would skip them silently because it reads only F.CrtYd / F.Fab). The U.FL jacks are not
under the cans (v <= 5.92 against the can rear wall at v 8.25), so "U.FL plug height under the cans" does not arise.
Proposed change (head mechanical): add GH plug keep-outs for all board connectors and wire envelopes (coax bend 6 mm at
the rear edge, chimney) to the interference set; make `asbuilt.py` read B.CrtYd too.

### Minor

**m1 - J_PWR is in the 12 mm rear-corner zone; J_HEAD1 height understated.** *Measured.* J_PWR (Mini-Fit Jr 5569-08A2,
12.8 mm) covers v 14.5..22 of REAR_CORNER_LOW (12.0). The cover boss (z 97.6) is over v <= 6, so it clears physically, but
the zone is violated as written. J_HEAD1 (5569-10A2, same family and orientation) carries a 7.0 mm envelope while
`checks.ccr_e08` assumes 12.8 mm. Change: one height for the 5569 family; shorten the zone to v 0..12 or accept the
deviation in writing (chassis electronics / mechanical lead).

**m2 - Board screws too short for the nyloc.** *Calculated.* M3 x 10 through PCB 1.6 + spacer 3.0 + tray 2.0 = 6.6 mm,
plus ISO 10511 nut 4.0 = 10.6 mm: the nylon ring is not engaged. Use M3 x 12, or C1's clinch standoffs (body mechanical).

**m3 - RR-PANEL orientation stated three ways.** `board_envelopes.yaml`: long axis along y; `mechanical_interfaces.md`
and the body model: along x (bbox x -115..-45); harness W-023 still "bottom side" (panel CR P1). Fix in `gen_interfaces.py`.

**m4 - Layer counts.** `board_envelopes.yaml` gives 4 layers for RR-CHS-MAIN and RR-HEAD-ACQ; both board files are 6-layer
(thickness 1.6 mm, so no fit consequence). Mechanical common.

**m5 - Head chimney depth.** 9 mm in `board_envelopes.yaml` / interfaces section 2, 7.9 mm in the head report (line 167).
Head mechanical to state one value.

**m6 - Motor-terminal suppression and can strap have no hardware in the body.** `cables.md` section 7 requires a can strap
<= 30 mm to the chassis plate and three capacitors at the terminals; the plate hole table has no bond hole and the model
no envelope. The pod's "encoder-lead notch" (`structure.py` 238) is at the gearbox end (y about 98.5) while the harness
and `parts.yaml` put the lead exit at the encoder end (y ±42.5). Body mechanical + harness.

**m7 - Tray features versus documents.** The two harness pass-throughs in the tray (x -55..-39, y ±60) are used by no
harness path. `process_plan.md` / BOM call RRP-F04 "laser cut + press-brake bent"; the STEP and the BOM mass (88.8 g =
33140 mm3 x 2.68) are a flat 2 mm plate. Production mechanical.

**m8 - J1 pigtail length stated three ways.** Interfaces section 1: free length 150..200 mm; harness W-101: 200 mm outside
+ 90 mm inside = 300 mm; head model: 12 + 120 mm. Align after M6.

**m9 - ToF board not clamped in standard seats.** Clip plane 9.5 mm vs header back 8.45 mm (1.05 mm free); retention is
the 1.5 mm foam only (see C3). Add a 1 mm spacer pad on the clip.

### Observations

**o1 - RR-TOF sensor is 2.4 mm off the board centre.** `tof_carrier/board.py` outline y -9.4..4.6 about the sensor;
`board_envelopes.yaml` says "Sensor on the board centre" and the seat, window, 12 x 8 aperture and foam are centred on the
board. Estimated cone clearance to the 8 mm aperture edge about 0.7 mm (18 deg FoV UNVERIFIED). Re-centre the aperture on
the sensor or move the sensor.

**o2 - The body has no harness geometry.** Corridors are boxes checked "free"; no cable solids, P-clips or bend envelopes.
Only six cable features exist in the body code (two blocked grommets, tray pass-throughs, the 3.1 mm look slot, an 8 mm
J1/J2 pass, panel tray notches, LiDAR gland).

**o3 - `comparison.md` lists counts only.** I found no interface position that differs between the builds (same
`params.py`, same seat and fastener code; checked on the solids for C1, C2, C4, M1). The service consequences of the
one-piece skins (M8, M10) are differences in practice and are not listed.

**o4 - Stale STEP files on disk.** `parts_base_link/` still holds `bus_clamp_resistor.step` (removed by IB-26),
`tof_*_look_fl/fr/rl/rr` and `receiver_shim_L/R` from earlier builds. They are git-ignored, but a reviewer or a script
globbing the folder picks them up. Clean the folder at the start of `build.sh`.

**o5 - J2 receptacle rear body intersects the nose cowl** by 67 mm3 more than 6 mm behind the skin (declared mate, so the
interference check skips it). Probably the seat boss; confirm.

## 4. Answers to the questions (short)

1. Chassis main board: outline, holes and zones agree between board file, `board_envelopes.yaml` and the body envelope.
   No top part above 18 mm (tallest K2/K3 15.7 mm, 4.7 mm under the cover); bottom parts <= 2.5 mm; no bottom part on the
   gap pad; no part in a hole keep-out; IMU U42 at (80, 67). Stage-3 parts break no height limit except m1. The fixing is
   impossible (C1); the board cannot be lifted out through the cover (M1); J_PWR and the side-edge plugs are not
   hand-unmatable under the ledge (M1); the rear-edge headers break the keep-out text and leave no loom room (M9).
2. Harness: both ends exist for all robot cables except the CM5 connectors (M2) and the head switches (stale positions,
   M5). 30 of 41 path polylines cross solids (M4). ToF: W-039 about 310 mm on a real route (> 300), W-032 / W-036 at the
   limit, W-034 / W-037 30 mm short (M3). Motor leads: suppression parts and strap have no envelope or bond point (m6);
   the lead leaves the can end at y ±42.5 with 23.5 mm to the coupler and must pass in front of the can (x 18.5..26) to
   reach the edge plug (length still covered by the 50 mm loop, *estimate*). Battery coupler lead (W-001/003) goes through
   the right motor (M4). J1/J2 pigtails: M6. LiDAR: M4. Panel: M7. Pause/Stop W-019 follows the CR-08 position and is clear;
   E-stop W-015 is clear; HANDS-ON W-017 runs through the E-stop body (M4). No modelled path: W-002 (inside the cassette),
   W-024, W-107, W-108..W-119 (head internal), W-200/201 (lab), and in the body every cable (o2).
3. Panel devices: depth +5 / +10 mm causes no new intersection for E-stop, HANDS-ON, Pause/Stop, charge inlet and J1
   (measured); the selector and REARM bodies at +5 mm hit the CM5 carrier (M2). J2 see o5. Inside-nut and terminal-wiring
   space behind the receptacles and the XB5 contact blocks is not modelled (section 6).
4. Head: see M11 for the check's scope, M6 for the pigtail.
5. ToF carriers: C3, M10, m9, o1.
6. Assembly order: C1 (board / tray), C2 (receiver screws, pods, hull), C4 (grommets), M8 (production lid).
7. Prototype vs production: same interfaces; o3. Drawing versus STEP: m7.
8. Claims not supported by the geometry: board service from above (M1), "harness corridors free" as evidence of routable
   cables (o2, M4), "board lies flat on six spacers" (C1), "re-torque receiver screws" (C2), W-107 "position not in the
   sources" (M5), "sensor on the board centre" (o1), "pigtail clipped to the shoe root" (M6).

## 5. Checked and found consistent

* RR-CHS-MAIN outline 160 x 100 and H1..H6 positions: board file = `board_envelopes.yaml` = body model (`board_standoff_*`).
* RR-CHS-MAIN heights: top <= 18 mm everywhere, 12 mm front corners clear, bottom <= 2.5 mm (limit 3.0), gap-pad zone
  free of bottom parts, 7 mm hole keep-outs free, U42 at (80, 67).
* Rear cover-screw bosses (z 97.6) are not above any part taller than 12 mm; K2/K3 have 4.7 mm under the cover.
* J_PWR mated-plug room 23 mm beyond the right edge (side-plate leg starts at x -32; `ccr_e08` box confirmed).
* Left-edge plugs J_CM5 / J_LIDAR / J_MOT_L: no side-plate material at their x (plate leg x -31..-22 above z 63).
* RR-HEAD-ACQ: no bottom-side parts; 8 holes as reported; U.FL jacks outside the cans; J1 port y 76.2 in board, head
  model and `params`.
* Production ToF clip quantities: RRP-P53 x 5 (standard) + RRP-P54 x 4 (look) + 2 cliff pods = 11.
* W-019 (Pause/Stop) path uses the CR-08 position and crosses no other part; Pause body +5 mm stays clear of the IB-12
  rear-right connector space (radial reach y -85.3 at board level against the board edge y -80, calculated).
* Service opening, receiver screws, grommets and tray holes are identical in the two builds (measured on both).

## 6. Cannot be assessed without the real purchased parts

* Mated envelopes, latch access and minimum wire bend of JST GH, Molex CLIK-Mate, Micro-Fit 3.0 and Mini-Fit Jr plugs
  (all heights here are the electronics build's bounding boxes; Micro-Fit right-angle seated height is UNVERIFIED).
* Harmony XB5 body and contact-block depths and their terminal wire exits; selector and REARM references are not chosen.
* binder M16 / M12 receptacle rear depth, panel-nut size and spanner access inside the nose; contact wire ranges.
* Waveshare CM5-IO-BASE-A connector edge, assembled height and hole pattern; LiDAR connector exit and cable.
* Anderson SBS50 envelope and lead exit; Pololu 37D encoder-end terminal access for the suppression capacitors; whether
  the gearbox bracket touches the can.
* D2HW-C201M lead length (decides splices on W-104..W-107, W-020, W-021/022); cable ODs and bend radii of every harness
  item; splice dimensions on W-101.
* VL53L4ED field of view and optical centre in the package (o1).
