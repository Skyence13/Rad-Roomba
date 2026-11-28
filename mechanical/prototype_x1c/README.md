# RR-X -- Rad Roomba prototype body for the Bambu Lab X1 Carbon

Parametric CadQuery model of the mobile base (Rev E rounded body) built from printed parts on a stock X1 Carbon
(256 x 256 mm bed) plus purchased and simple fabricated parts. Every interface value is imported from
`mechanical/common/params.py`; nothing in `mechanical/common` is edited here. The head is another work package: this
package uses the common head envelope (extended to the contract's x 212.5) as a placeholder and puts the head engineer's
`RR-HD-X-000` assembly STEP into the robot assembly STEP when it exists.

## Rebuild

```bash
./mechanical/prototype_x1c/build.sh            # everything: parts, exports, checks, documents, images (non-zero exit on a failed check)
./mechanical/prototype_x1c/build.sh --no-images --no-assembly-step     # faster iteration
```

`PY` may point at any Python 3.12 with `requirements.txt` (CadQuery 2.7.0). Shell pieces are cached as BREP in
`out/cache` (keyed on the parameters and a version number per builder); delete `out/cache` for a cold rebuild.
No slicing is run: the owner slices from the exports in Bambu Studio (`mechanical/tools/slice_plates.py` is an optional
helper that reads `plates.yaml`).

## Layout

| Path | Content |
|---|---|
| `rrx/dims.py` | prototype design values (walls, fits, fasteners, split stations); everything else from `mechanical.common.params` |
| `rrx/structure.py` | chassis plate with front beam, machined receiver channels + dowel-pin lands, dock-switch bracket, motor pods, bridge tray/posts, grip frame (side plates, angle feet, 14 mm bar, sleeve, cheek fairings), caster disc, latch arm, front bulkhead |
| `rrx/battery.py` | battery tunnel, insulating floor plug (heater carrier), cassette + lid, floating coupler carrier, cam bail, 9 Ah spacer |
| `rrx/shells.py` | Rev E skin split for the bed: 4 lower-hull pieces, nose cowl, 2 shoulders, 2 rear decks, battery hump, saddle (service) cover, hatch frame, tail-cap door; joints, flanges, inserts, dowels |
| `rrx/sensors.py` | ToF seats (3 kinds), panel-device seats, receptacle seats, RR-PANEL tray, CM5 tray, charge-inlet cover and seat |
| `rrx/running.py` | printed wheel rim + TPU tyre on a Pololu #1999 hub, front cliff pods with tyre-to-head debris deflectors, three-segment bumper, transport tray, ToF clips/windows |
| `rrx/assembly.py` | part registry + purchased envelopes + head placeholder |
| `rrx/checks.py`, `rrx/interference.py` | tool-checked and calculated checks (see `out/prototype_report.md`) |
| `rrx/export.py`, `rrx/docs.py`, `rrx/render.py`, `rrx/hardware.py` | exports, plates/print schedule, BOM, assembly document, images, joint sections |
| `out/step/` | every printed part in PRINT orientation (+Z up, bed z = 0); `out/stl/`, `out/3mf/` the same as meshes |
| `out/parts_base_link/` | every real part (printed, fabricated, purchased envelope) as STEP in its assembled position |
| `out/fabricated/step/`, `out/dxf/` | fabricated parts; DXF profiles of the flat ones; `out/dxf/chassis_plate_holes.csv` hole table |
| `out/RRX_assembly.step` | full robot assembly (sub-assemblies as in the BOM) |
| `out/checks.json`, `out/prototype_report.md` | check results and report |
| `out/_interference/exact_cache.json` | cached exact boolean results of the interference check (keyed on the BREP digests of each pair) |
| `out/cache/` | BREP cache of the shell pieces (warm build about 5 min; cold about 25-30 min on the shared machine) |
| `plates.yaml`, `print_schedule.md` | plates, orientation, material, supports, bed fit |
| `purchased_and_fabricated.csv`, `hardware_by_subassembly.md` | bill of parts and of hardware by sub-assembly |
| `assembly.md`, `img/` | illustrated assembly sequence |
| `joints/` | 16 true-size joint sections (PNG + PDF), index in `joints/README.md` |
| `CHANGE_REQUESTS.md` | deviations from `mechanical/common` and requests to the lead |
| `STATUS.md` | work-package status |

## Evidence classes

*tool-checked* = computed by the OCC kernel / mesh tools on the nominal CAD solids of this model; *calculated* =
closed-form with stated inputs. Nothing has been printed, measured or sliced. Supplier data not confirmed in this work
package is marked UNVERIFIED in the BOM and the report.
