# RR-P production body -- status

## State (2026-11-27): complete; `build.sh` exit 0, all checks pass (result block at the end)

| Item | State |
|---|---|
| Build switch in the shared model (`RR_BUILD=production`, `prototype_x1c/rrx/dims.py`, `production.py`) | done; default x1c build unchanged (prototype build exit 0 after the change) |
| Production geometry: one-piece SLS lower hull and lid, tapped machined pods, machined rims, cast tyres; everything else same geometry | done |
| Process plan (process, tooling class, min feature / tolerance, sealing, carried over) | `process_plan.md` (generated) |
| STEP per made part, per-subassembly STEP, full assembly (untracked) | `step/`, `assembly/`, `out/` |
| Fabrication drawings (multi-sheet PDF) | `drawings/RRP_fabrication_drawings.pdf` |
| DXF + hole tables for flat parts | `dxf/` |
| BOM, hardware, assembly sequence, mass/CG, comparison, report | generated |
| Check suite (same as prototype + process envelopes + one-piece skins) | `production_report.md`, `out/checks.json` |

## Known limits

- Supplier capabilities (SLS envelope 700 x 380 x 580, cast-PU shop), material data (PA11, PU 85A, G-10) and the G-10 bushing as a stock item are UNVERIFIED.
- Drawings: the datum parts (plate, receiver channel, shim) carry hand-placed critical dimensions; every other sheet has tool-generated views, overall
  reference dimensions and a tool-extracted hole / thread / insert table, not a full dimensioning scheme (the STEP is the master).
- The motor pods and rims keep the printed-part geometry in aluminium (heavier than needed): a metal-optimised redesign is a follow-up.
- Caster rated to -20 C only (plain bearing): production needs a low-temperature caster selection.
- Full assembly STEP is above 50 MB and is not tracked; `mechanical/production/out/cache` was captured by a WIP snapshot commit before
  `.gitignore` existed (CR-11 in `prototype_x1c/CHANGE_REQUESTS.md`).

## Run time

Cold BREP cache: about 45 min on the shared machine (the one-piece lid booleans); warm: about 15 min, of which about 10 min is the exact
boolean of lower hull x lid (contact only, 0.0 mm3; RR_BOOL_TIMEOUT=1200 in build.sh, result cached in out/_interference).

## Result of the last run (2026-11-27, tool-checked unless marked)

- `build.sh` exit 0, 926 s warm. Interference 0 clashes in 371 pairs (20 declared through-wall envelope overlaps); containment, floor contact,
  ToF / LiDAR rays, removal sweeps and glove zones, chin rule, receiver interface 41/41 (incl. the thermal break), width <= 295, corridors,
  CCR-E08 keep-outs, slivers (< 100 mm3, same as the prototype), one valid solid per part, 45/45 process envelopes, one-piece skins: all PASS.
  Grip proof: PASS (calculated).
- Mass / CG (calculated): body 7.36 kg; with prototype head 9.23 kg, CG x -48.4, fwd tip margin 39.2 mm, hang -11.3 deg; with production head
  9.44 kg, CG x -44.2, 35.1 mm, -8.7 deg (`mass_cg.md`).
- 45 part STEP, 4 subassembly STEP (largest 44 MB), full assembly 60 MB in out/ (untracked), 9 DXF + hole tables, 50 drawing sheets.
- Fixes made during this pass: one-piece hull trimmed at x 62 (nose lip and chin belong to the lid); the skin strip that closes the hump
  opening starts at the hump rear face (the hatch frame owns the 3.3 mm gap behind it).
