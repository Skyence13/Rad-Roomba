# RR-X prototype body -- status

Scope note (owner, via coordinator): **no slicing is run in this work package**. `mechanical/tools/slice_plates.py` stays as an
optional convenience; the owner slices from the STEP/STL/3MF exports in Bambu Studio.

## State: complete, end-to-end `build.sh` runs and writes every output

| Item | State |
|---|---|
| Parts: structure, battery bay, shells (split for the 256 mm bed), sensor/control mounts, wheels, bumper, tray | done; 0 clashes among real parts and purchased envelopes (tool-checked) |
| Exports: printed parts as STEP/STL/3MF in print orientation, every part as STEP in base_link, fabricated STEP + DXF + hole table, robot assembly STEP (with the head engineer's RR-HD-X-000 STEP) | done |
| plates.yaml, print_schedule.md | done (generated) |
| out/checks.json, out/prototype_report.md | done (generated); one remaining finding is interface-owned (CR-08: Pause/Stop body envelope in the IB-12 rear-right connector space) |
| purchased_and_fabricated.csv, hardware_by_subassembly.md | done (generated) |
| assembly.md + img/ (10 rendered stages), joints/ (16 true-size sections) | done (generated) |
| README.md, CHANGE_REQUESTS.md | done |

## Follow-on 2026-11-27 (lead decisions on CR-01..CR-09)

All CRs closed (see CHANGE_REQUESTS.md). Applied here: CR-04 grip bar aft (sleeve x -42.5..-17.5, bar screw x -25, side-plate
cheek x -32..-18 through a moved roof slot, fairing nose carries the forward look-ahead ToF at x 1.5, shoulder/deck split
moved to x -38, deck joint screw at z 116 dropped (its boss reached the side plate)); CR-08 Pause/Stop moved outboard to
y -122 (from `mechanical/common`); IB-26 bolt-on clamp resistor removed; IB-34 ToF names (tof_look_fwd_left/right,
tof_look_rev_left/right); head masses and envelope taken from `mechanical/common` (P.HEAD_MASS, x 212.5).
`mechanical/common` was updated in the same pass (owner of that pass: this engineer).

## Follow-on 2026-11-27 (2): receiver thermal break (DEC-045, IB-64) -- built, checked

Each receiver channel hangs on a ground 4.0 mm G-10 shim under its ears (RRX-F12 inboard / RRX-F13 outboard strips); no metal
crosses the shim: M4 x 18 A2-70 in G-10 top-hat bushings with DIN 6796 + ISO 7089 (1500 N, 1.2 N m); lower 4 m6 x 8 pins in the
ear engage only the shim, upper pins pressed in the plate end in an ear relief; the roof exists only as two bridges at the
land stations, standing in 1.5 mm plate pockets (1.5 mm air gap). Ears and walls stop at z 29.0; datum C and the land pins
unchanged. Tool-checked: receiver interface 41/41 (incl. shim thickness, ear top z, min channel-to-plate gap >= 1.0 mm, pins
clear of the far part), 0 clashes, build exit 0. Calculated (`mechanical/common/out/mech_calcs.md` section 9): 0.081 W/K per
channel (target 0.10), datum-C stack +-0.057 -> +-0.093 worst case, 20 N corner deflection +1.6 % (printed head) / +7 %
(aluminium head), first mode -1 % / -4 %, preload loss 6 % with the spring washer (57 % without), engagement 7.1 mm = 1.8 d.
Joint section J17 added; stage 1 work instructions, hardware and tolerance table updated. The same parametric code now has a
build switch (`RR_BUILD=production`, `rrx/production.py`) used by `mechanical/production`; the default build is unchanged.
`mechanical/common` thermal: bay rows follow the draft8 policy (-10 C hold on pack power, +5 C pre-heat); the head set-point is read from the
contract (draft9: +5 C) and the head rows are read from `mechanical/head/out/thermal_summary.json` at build time (0.07 W/K-per-shoe rows,
stated as depending on the break). The CCR-E08 keep-out check reads the common layout boxes, not `pinmap.json` (re-run, all free).

## Fit-review pass (2026-11-28, docs/reviews/REVIEW_cad_pcb_harness_fit.md) -- STAGE 1: prototype

Result of the last prototype build: see the block "Prototype build result" at the end of this section.

**New checks (tool-checked, both builds share the code):**
- Fasteners as solids (`rrx/fasteners.py`): 96 fasteners from the hole lists (plate table, board holes, posts, cover, perimeter,
  grip, receiver): head + washers + 0.8 d shank + nut in the interference check; 114 tool columns (stated tool) checked against the
  parts present at the assembly step that fits them (docs.STEPS order, with "fitted later in the same stage" lists) and in their
  service state (receiver re-torque from below, board service lid off, cover routine).
- Boards from the board files (`mechanical/common/boards.py`, method of mechanical/head/asbuilt.py; `rrx/boards_body.py`):
  RR-CHS-MAIN (stage 5 file, 881 footprints, both sides), RR-PANEL, RR-TOF-A x 11 in their seats (oriented), CM5 carrier with RJ45 /
  USB-A / 40-pin plugs; a mated plug + wire-exit solid per connector (family estimates + 1 mm, UNVERIFIED).
- Cable routes (`rrx/routes.py`): every robot cable of harness/cables.csv routed through the voxelised free space, exact tube check
  against every part, bend / clip-point report, lengths; published to `mechanical/common/out/cable_routes.yaml`; docked J1/J2
  pigtail corridors with ToF-cone and LiDAR-plane margins.
- Service sweeps of real parts (`rrx/fitchecks.py`): board lifted with plugs out (lid off), CM5 carrier, every plug pulled out of
  engagement (+ finger zone on the main board / CM5), ToF carrier withdrawal per seat (M10 table), SVC1..SVC10 probe zone, board
  bottom zone, receptacle depth + 5 mm.

**Closed (tool-checked in the prototype build):**
- C1: posts 0/1 at (-64, +-62); flush M3 countersunk tray screws; self-clinching standoffs at the six board holes (no nuts); every
  fastener solid clash-free and reachable.
- C2: receiver joint turned round (M4 from below into the tapped plate, bushing under the inboard ear, outboard ear removed);
  tool access at stage 1 and for the re-torque from below: free.  Thermal break 0.077 W/K per channel (calculated).
- C3: seats on the real RR-TOF-A outline (sensor offset o1), J1 plug + wire relief, clip on the header-free half (m9), two carriers
  turned; all 11 carriers with plugs clash-free.  M10 answer per seat in the report (ToF withdrawal table).
- C4: x -2 grommets removed; dock grommet at (28, 58) + hull notch, dock lead W-020 routed; cliff leads rise through the pod bays
  (plate window 21.5 x 27.6 + hull notch) -- W-030 / W-031 still OPEN (see below).
- M1: board service defined as lid off (+ nose cowl in the prototype); board lift and all main-board plug pulls free.
- M2: CM5 carrier 6 mm lower, connector edge -x with plugs; clear of the selector / REARM bodies (interference + sweeps PASS).
- M3: look-ahead lead slot 10 x 7 under the fairing nose + fairing channel.
- M7: RR-PANEL orientation fixed (plugs outboard), notches, M2.5 bosses, light pipes from the LED positions.
- SVC1..SVC10 (stage 5): 11 test pads found in the board file; no part, route or clip over the probe zone.
- J1/J2 receptacles: nose front, skin +-17 deg, z 97, axis 25 deg up / 16 deg out (z 94 -> 97 after the common layout found the
  grasp annulus touching the head cold jacket, z 48); pigtail apex about z 131 (was 195..226); free length about 285 / 270 mm (not shorter); corridors >= 20 mm from the look-ahead cones, about 80 mm below the LiDAR plane; grasp
  zones free; receptacle depth + 5 mm free.
- Minor: m2 (no nyloc), m3 / m4 (interfaces text, 6-layer from the files), m7 (tray flat, production rule), m9, o1, o4.

**Not closed (OPEN, listed with reasons in the report and in cable_routes.yaml):** routes W-001, W-023, W-030, W-031, W-034,
W-035, W-037 (small grazes or an enclosed voxel pocket at plug / seat ends: real fixes proposed, not yet modelled), W-032 / W-033
(rear cliff seats enclosed), W-036 / W-040 (right look-behind / REAR_R over the 270 mm ToF budget: electronics CR-15), W-039
(REAR_C in the hump brow, hump full), W-041 / W-042 (heater / NTC lead exit from the tunnel floor not modelled).  M5 and M11 are
head / harness items; M9 is CR-15; m6 (can strap bond hole) open.

**Prototype build result (2026-11-28, run 7):** `build.sh` exit 0, ALL CHECKS PASS (0 clashes in 1070 pairs; 96 fasteners / 114 tool columns, 0 blocked; all service sweeps free; SVC PASS; receptacle depth PASS; 25 / 39 cables routed collision-free, 2 not routed by design (W-002 inside the cassette, W-024 optional), 12 OPEN findings listed above; both pigtail corridors clear). Mass / CG (calculated):
  none (transport / LAB): 6.69 kg, CG x -92.4, fwd tip 81.9 mm, hang -37.2 deg
  prototype head RR-HD-X (1.881 kg): 8.57 kg, CG x -44.2, fwd tip 35.1 mm, hang -8.7 deg
  production head (2.100 kg): 8.79 kg, CG x -39.8, fwd tip 30.8 mm, hang -6.0 deg
  production head + 15 % margin: 9.1 kg, CG x -34.0, fwd tip 25.2 mm, hang -2.4 deg

- 2026-11-28 later: receptacles raised to z 97 (head jacket); common build exit 0; prototype run 8 and production run 2 RUNNING (chained).

## Run times (shared 4-core machine)

Warm BREP cache: about 4-6 min for everything. Cold (empty `out/cache`): the shell pieces take 20-25 min on the shared CPU
(the rounded skin booleans), the rest about 5 min. The cache is keyed on parameters + a version number per builder; bump the
version in `rrx/shells.py` when a builder changes (stale versions are pruned by `build.py`).

## Handover history

1. First engineer: modules written, never run end to end.
2. Second engineer: first end-to-end run; real-vs-real overlaps can no longer be hidden by "mates"; about 30 genuine clashes
   fixed (see CHANGE_REQUESTS.md D-01..D-11 for the ones that changed a concept: grip bar, cassette latch, cover screws,
   split station, tunnel trim, perimeter stations); interference engine rebuilt (mesh screening of all pairs + exact OCC
   boolean per flagged pair in its own process, cached); new checks (tyre width, corridors, CCR-E08 keep-outs, slivers,
   swept radius, plate bending in the grip proof).

## Open (needs others)

CR-04 (grip bar aft for IB-10), CR-06/CR-08 (board envelope zones / Pause body depth), CR-09 (swept radius incl. bumper),
UNVERIFIED supplier data listed in the BOM. First-article tests: insert pull-out coupons, -25 C impact coupons (ASA,
PAHT-CF), tyre cold traction, grip proof load (VT-002), cassette latch pull test.
