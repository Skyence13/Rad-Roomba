# RR-P production body (Rad Roomba Rev E, 5-25 units per year)

The production build of the robot body. It has the same outer form, interfaces, checks and `mechanical/common` parameters as the X1C prototype
(`mechanical/prototype_x1c`). It is generated from **the same parametric code** with a build switch:
`RR_BUILD=production` (`prototype_x1c/rrx/dims.py: PROD`). Process, material and part-number labels come from
`prototype_x1c/rrx/production.py`.

```
RR_PY=<python with CadQuery 2.7, ezdxf, matplotlib> ./mechanical/production/build.sh   # exit code != 0 if a check fails
   options: --no-drawings  --no-assembly-step
```

## What changes against the X1C build

| Part class | X1C prototype | Production | Why |
|---|---|---|---|
| Skins | 10 printed ASA pieces (lower hull 4: x -71 / y 0 splits; lid 6: nose cowl, 2 shoulders, 2 rear decks, hump) with joint flanges, dowels, inserts | **2 pieces, SLS PA11**: one-piece lower hull RRP-S01 and one-piece lid RRP-S02 (nose + shoulders + decks + hump) | no tooling at this volume; no bed-size splits; PA11 keeps its ductility in the cold |
| Covers, cassette, trays, clips, pods for sensors, bulkhead, bumpers | ASA / PAHT-CF prints | SLS PA11, nested in the skin builds, same geometry | same parts, isotropic and dense |
| Motor pods | PAHT-CF prints with M4 heat-set inserts | CNC 6061, M4 tapped | creep under the motor clamp and wheel load, cold impact |
| Wheel rims | PAHT-CF prints | CNC 6061 | as above |
| Tyres | printed TPU 95A | cast polyether PU 85A on the keyed rim (soft aluminium mould) | wear, layer lines, cold stiffening |
| Chassis plate | laser blank + manual ops | waterjet / laser blank + one CNC fixture (reams, pockets, taps) | the receiver datum chain |
| Receiver channels, G-10 shims, grip, bridge, caster plates, latch arm | machined / laser / bent sheet | same parts and processes | already production processes |

The details for each part are in `process_plan.md`: process, tooling class (none / soft / hard), minimum feature and tolerance assumption, sealing
approach, what is carried over unchanged, and what it replaces. Cold-weather notes for the -25 C objective are at its end.

## Outputs

| Path | Content |
|---|---|
| `step/` | one STEP per made part (base_link coordinates), file `<PN>_<part>.step` |
| `assembly/` | per-subassembly STEP (tracked); the full assembly with the production head goes to `out/RRP-000_assembly_full.step` (untracked, over 50 MB) |
| `drawings/RRP_fabrication_drawings.pdf` | multi-sheet A3 fabrication drawings. Plate, receiver channel and shim sheets carry datums and critical tolerances; every made part gets views, a tool-extracted hole/thread/insert table, material, finish, process and the general tolerance block |
| `dxf/` | flat parts (plate, side plates, bridge tray, screw rings, caster plates, shims, latch arm) with hole tables (+ `_holes.csv`) |
| `bom_production.csv` / `.md` | make/buy, process, tooling, material, finish, quantity, mass, X1C part replaced |
| `hardware_production.md` / `.csv` | screws, pins, inserts, seals with torques; fastener count |
| `assembly_sequence.md` | stages with torque and sealing notes, end-of-line checks |
| `mass_cg.md` | mass, CG, tip margins, hang angle: no head, prototype head, production head (calculated) |
| `comparison.md` | prototype vs production: part / piece / fastener counts, mass, per-unit process content (no prices) |
| `production_report.md` | check results (tool-checked / calculated) |
| `out/` | BREP and interference caches, `checks.json`, full assembly STEP (all regenerable, git-ignored) |

## Evidence classes and open items

- **tool-checked** = computed on the solids by `build.sh` (interference, containment, floor contact, sensor rays, sweeps and glove zones, chin rule,
  receiver interface incl. the thermal break, width rule, corridors, CCR-E08 keep-outs, slivers, swept radius, process envelopes);
  **calculated** = closed-form / lumped (mass/CG, grip proof, thermal break, heater sizing in `mechanical/common`).
- UNVERIFIED: every supplier process capability and envelope (SLS large frame 700 x 380 x 580, cast-PU shop), every material property
  (PA11 density, elongation and cold impact; PU 85A cold hardness and Tg; G-10 conductivity and modulus), the DIN 6796 spring-washer data,
  the G-10 top-hat bushing as a stock item, and every purchased dimension already marked so in the prototype (`purchased/parts.yaml`).
- The caster is rated to -20 C (plain bearing), below the -25 C objective: production needs a low-temperature caster (to be selected).
- Prices are not estimated (comparison gives physical process content only).
