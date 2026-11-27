# RR-P production body -- status

## State (2026-11-27): first complete build; see the result block at the end (written after the run)

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

Cold BREP cache: about 20-30 min on the shared machine (skins); warm: see the result block.
