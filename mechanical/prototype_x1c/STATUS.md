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
