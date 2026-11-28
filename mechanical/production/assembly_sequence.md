# RR-P production body: assembly sequence with torque and sealing notes

Torques for A2-70 screws, dry with medium thread-lock where stated (values from the hardware model). Sealing: neutral-cure silicone RTV (-50 C), closed-cell silicone gaskets (-55 C), EPDM bonded washers (-40 C). Assembly fixtures: none required beyond a flat table and the receiver gauge pins.


## 1 Chassis plate and receiver (thermal break)

1. Plate RRP-F01 as delivered (machined, chromate/anodised, holes per `dxf/chassis_plate.dxf`). Press the two upper 4 m6 x 8 pins per channel flush from above.
2. Channels RRP-F02L/R: press the two lower 4 m6 x 8 pins (2.5 mm stand) and the two hardened 4 m6 x 24 land pins (datum C, flush both sides).
3. Degrease the ground G-10 shims RRP-F12 / F13 (one matched set); fit shims on the lower pins, channel + shims onto the upper pins under the plate.
4. Per screw: M4 x 18 A2-70 + DIN 6796 + ISO 7089 + G-10 top-hat bushing. Medium thread-lock, **1.2 N m** in two passes. Check channel-to-plate isolation > 1 Mohm.
5. Dock switch bracket, cliff pods (M3 x 10, 0.6 N m), caster disc (M3 x 6 csk, 0.8 N m, thread-lock), caster + shim (M4 x 6, 1.5 N m, thread-lock).

## 2 Drive

1. Machined pods RRP-P01L/R to the plate: 4 x M4 x 12 countersunk from below into the tapped pod, **1.5 N m**, thread-lock (no inserts).
2. Gearmotor into the pod, screw ring, 6 x M3 x 6 button head, 0.5 N m. Hub on the D shaft; wheel (machined rim with the cast PU tyre) to the hub, 6 x M3 x 8, 0.6 N m, medium thread-lock.

## 3 Battery bay, bridge, grip

1. Tunnel, floor plug with the 20 W pad + NTC + cut-out, fixed coupler half (M4 x 55 cross pins, 1.0 N m), hatch frame.
2. Bridge posts (M4 x 10 csk, 1.5 N m), bridge tray, gap pad, RR-CHS-MAIN (M3 x 10 + nyloc, 0.5 N m), CM5 tray and carrier.
3. Grip feet (M5 x 16 csk through-bolted, **4.0 N m**), side plates (M5 x 16, 4.0 N m), bar (M6 x 16, **6.0 N m**, thread-lock) -- proof-load path.

## 4 Lower hull (one piece)

1. RTV bead (neutral cure, -50 C) on the plate edge; lower the one-piece SLS hull RRP-S01 over the plate; sole-ring M3 x 8 countersunk from below, 0.6 N m.
2. Membrane vent (M12) in the right rear quarter; duck-bill drains in the plate.

## 5 Front bulkhead, latch, nose items

1. Front bulkhead, latch arm (M5 x 25 csk, 3.0 N m), draw latch (M4 x 10, 2.0 N m).

## 6 Lid (one piece)

1. Pre-fit into the one-piece SLS lid RRP-S02: J1/J2 receptacles, ToF modules + clips (M2 x 6, 0.15 N m), panel tray (M3 x 8), light pipes, controls, charge inlet, LiDAR on the hump pad, cassette plunger (M10, 4.0 N m).
2. Perimeter silicone gasket on the hull tongue land (continuous, one butt joint at the tail, bonded with silicone adhesive).
3. Lower the lid over the grip side plates (slots) onto the tongue; perimeter M3 x 10 button head + EPDM bonded washer, **0.5 N m** in a cross pattern (gasket compression 25-35 %).
4. Cheek fairings (M3 x 20 + nyloc through the side plates, 0.5 N m), saddle cover (6 captive M3, 0.5 N m, cover gasket), bumpers (guide screws, 0.5 N m).

## 7 Cassette, door, head

1. Cassette with pack, foam pads, handle; slide in through the hatch; index plunger engages. Door on the jamb pegs, draw latch, lanyard.
2. Head: slide on the receiver (shoes into the channels), latch preload 100..200 N.

## 8 End-of-line checks

1. Receiver: datum C height at the four lands (gauge pins), channel-to-plate isolation (> 1 Mohm), x-stop coplanarity 0.05.
2. Gap measurement method of `mechanical/common/out/gap_measurement_method.md` (20 N corner test <= 1.0 mm, returns within 0.1 mm).
3. Seal check: 5 kPa over-pressure through the vent port, decay < 10 % in 60 s (method, threshold ASSUMED); re-torque the receiver screws after the first thermal cycle.
