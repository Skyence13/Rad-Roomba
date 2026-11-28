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

## Fit-review pass (2026-11-28, docs/reviews/REVIEW_cad_pcb_harness_fit.md) -- IN PROGRESS

Written to disk so far (both builds share it through the rrx code):
- New checks: `rrx/fasteners.py` (fasteners as solids + tool columns per assembly step / service state), `rrx/boards_body.py` +
  `mechanical/common/boards.py` (RR-CHS-MAIN, RR-PANEL, RR-TOF-A x 11 read from the KiCad files, both sides, mated plug + wire exit per
  connector; CM5 carrier with plugs), `rrx/routes.py` (voxel routing + exact tube check of every robot cable, published to
  `mechanical/common/out/cable_routes.yaml`; docked J1/J2 pigtail corridors with ToF-cone and LiDAR-plane margins), `rrx/fitchecks.py`
  (tool access, service sweeps of real parts, plug pull + finger zones, ToF carrier withdrawal per seat, SVC1..10 probe access, board
  bottom zone, receptacle depth + 5 mm).  Wired into checks.run_all and the report section 11.
- Fixes: C1 posts 0/1 to (-64, +-62), flush M3 tray screws, clinch standoffs (no nuts); C2 receiver joint turned round (screws from
  below into the tapped plate, inboard ear only); C3 seats on the real RR-TOF-A outline with J1 plug relief, new clip on the
  header-free half, two carriers turned (TOF_FLIP); C4 grommets moved (dock grommet (28, 58), cliff leads through the pod bay);
  M3 look-ahead slot moved under the fairing nose; M7 panel turned (plugs outboard), notches, bosses, light pipes from the LED
  positions; M2 CM5 carrier 8 mm lower; grip plate screws from inboard (tapped plates); pod front screws y 105; tunnel rear foot
  x -212; cliff pod screws countersunk from above; perimeter / cover / cliff screw lengths; caster disc countersinks.
- J1 / J2 receptacles moved to the nose front (skin angle +-12 deg, z 96, axis 20 deg up / 8 deg out): docked pigtail apex about
  z 125 (was 195..226), free length about 262..274 mm (not shorter: the forward-facing plug needs a 180 deg return loop at the
  40 / 35 mm bend radius), corridors in `mechanical/common` params PIGTAIL_CORRIDOR.
- NOT yet done at the time of writing: full prototype / production build runs with the new checks; route iteration; M9 / m6.

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
