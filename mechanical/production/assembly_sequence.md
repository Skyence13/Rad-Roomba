# RR-P production body: assembly sequence with torque and sealing notes

Torques for A2-70 screws, dry with medium thread-lock where stated (values from the hardware model). Sealing: neutral-cure silicone RTV (-50 C), closed-cell silicone gaskets (-55 C), EPDM bonded washers (-40 C). Assembly fixtures: none required beyond a flat table and the receiver gauge pins.


## 1 Chassis plate and receiver (thermal break, screws from below)

1. Plate RRP-F01 as delivered (machined, holes per `dxf/`); work on the plate upside down. Press the two upper 4 m6 x 8 pins per channel flush from above.
2. Channels RRP-F02L/R: press the two lower 4 m6 x 8 pins (2.5 mm stand) and the two hardened 4 m6 x 24 land pins (datum C, flush both sides).
3. Degrease the ground G-10 shim RRP-F12 (one matched set); shim on the lower pins, channel + shim onto the upper pins under the plate.
4. Per screw FROM BELOW: G-10 top-hat bushing in the ear bore, ISO 7089, DIN 6796, M4 x 18 A2-70 into the tapped plate; medium thread-lock, **1.2 N m** (3.6 mm of plate thread: never more). Isolation channel-to-plate > 1 Mohm.
5. Dock-switch bracket and switch; lead along the plate underside (2 adhesive P-clips) to the grommet at (28, 58). Cliff pods with carriers: plug the GH lead into the carrier BEFORE the pod is screwed (3 x M3 x 10 pan from above, 0.6 N m); the cable rises through the pod bay.
6. Caster disc (M3 x 6 countersunk, 0.8 N m, thread-lock), caster + shim from below (M4 x 6, 1.5 N m, thread-lock).

## 2 Drive

1. Machined pods RRP-P01L/R: 4 x M4 x 12 countersunk from below into the tapped pod, **1.5 N m**, thread-lock (no inserts).
2. Gearmotor into the pod, screw ring, 6 x M3 x 6 button head, 0.5 N m; motor lead out of the encoder end, clipped to the pod. Hub on the D shaft; wheel (machined rim with the cast PU tyre) to the hub, 6 x M3 x 8, 0.6 N m, medium thread-lock.

## 3 Battery bay, bridge, board, grip

1. Tunnel, floor plug with the 20 W pad + NTC + cut-out (leads forward under the tunnel floor), fixed coupler half (M4 x 55 cross pins, 1.0 N m), hatch frame.
2. Bridge tray prepared off the robot: six self-clinching M3 standoffs pressed in. Bridge posts (M4 x 10 countersunk from below, 1.5 N m), tray with 4 x M3 x 8 countersunk flush (0.8 N m), gap pad, RR-CHS-MAIN with 6 x M3 x 6 pan heads into the standoffs (0.5 N m) -- fit review C1: no nuts, no heads under the board.
3. CM5 tray and carrier (connector edge toward -x); plug the RJ45, both USB-A and the 40-pin power plug NOW (carrier connectors are outside the cover opening).
4. Grip feet (M5 x 16 csk through-bolted, **4.0 N m**), side plates (M5 x 16, 4.0 N m).

## 4 Harness, body side (before the skins)

1. Lay every cable on its route of `mechanical/common/out/cable_routes.yaml` (polyline, clip points with the part each clip goes on, length). Clips: adhesive P-clips or cable-tie bases on the listed parts.
2. Board end: plug in the order of the service sweep: J_PWR (right rear edge, Mini-Fit), J_MOT_L/R, J_CM5, J_LIDAR (left edge), front-edge GH (cliff, dock, J_HEAD1/2), then the rear-edge headers left to right; fan the rear-edge leads to the two corners (fit review M9).
3. Lid-mounted devices (ToF x 5, controls x 5, RR-PANEL, LiDAR, charge inlet, J1/J2 receptacles): their leads end in in-line disconnects parked on the bridge-tray edge clips, so the one-piece lid can be lowered, lifted and set aside (fit review M8; disconnect part numbers: harness CR).

## 5 Lower hull (one piece)

1. RTV bead (neutral cure, -50 C) on the plate edge; lower the one-piece SLS hull RRP-S01 over the plate (rear cliff carriers pre-fitted in the hull with their leads); sole-ring M3 x 8 countersunk from below, 0.6 N m.
2. Membrane vent (M12) in the right rear quarter; duck-bill drains in the plate.

## 6 Front bulkhead, latch

1. Front bulkhead, latch arm (M5 x 25 csk from below, 3.0 N m), draw latch (M4 x 10, 2.0 N m).

## 7 Lid (one piece)

1. Pre-fit into the one-piece SLS lid RRP-S02 on the bench: J1/J2 receptacles, ToF carriers in their seats (GH plug in, clip 2 x M2 x 6, 0.15 N m), panel tray + RR-PANEL (2 x M2.5 + 2 x M3), light pipes, controls, charge inlet, LiDAR, cassette plunger (M10, 4.0 N m); each device lead to its in-line disconnect.
2. Hold the lid 80 mm above its seat on two spacer blocks (it clears the grip side plates, top z 174); mate every in-line disconnect (service loop >= 80 mm each).
3. Perimeter silicone gasket on the hull tongue land; lower the lid over the side plates onto the tongue; perimeter M3 x 10 button head + EPDM bonded washer, **0.5 N m** in a cross pattern.
4. Cheek fairings (look-ahead ToF leads down through the roof slots, grommet), grip bar (M6 x 16, 6.0 N m, thread-lock), saddle cover (6 captive M3, 0.5 N m, cover gasket), bumpers.

## 8 Cassette, door, head

1. Cassette with pack, foam pads, handle; slide in through the hatch; index plunger engages. Door on the jamb pegs, draw latch, lanyard.
2. Head: slide on the receiver; the pigtails leave the head rear wall upward and run in the body's free corridor (mechanical_interfaces.md section 1); latch preload 100..200 N; plug J1/J2.

## 9 End-of-line checks

1. Receiver: datum C height at the four lands (gauge pins), channel-to-plate isolation (> 1 Mohm), x-stop coplanarity 0.05.
2. Gap measurement method of `mechanical/common/out/gap_measurement_method.md`.
3. Seal check: 5 kPa over-pressure through the vent port, decay < 10 % in 60 s (method, threshold ASSUMED). Re-torque the receiver screws from below after the first thermal cycle (robot on its back, head removed; tool-checked access).

## Service: RR-CHS-MAIN removal (tool-checked sweep)

1. Head off; saddle cover, grip bar, cheek fairings off; lid off (perimeter screws, in-line disconnects); unplug the board plugs in the order of step 4 reversed; 6 x M3 out; lift the board straight up. The 160 mm board does not pass the 150 mm cover opening (fit review M1).
