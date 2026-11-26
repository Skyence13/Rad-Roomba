# mechanical/tools -- shared slicing and mesh helpers

Owner: prototype mechanical engineer (`mechanical/prototype_x1c/`). Used by every work package that prints parts
(`mechanical/prototype_x1c/plates.yaml`, `mechanical/head/prototype/plates.yaml`).

| File | Purpose |
|---|---|
| `slice_plates.py` | plate manifest -> Bambu Studio project `.3mf` per plate -> headless slice (`.gcode.3mf`) -> JSON/CSV summary |
| `slice.sh` | thin wrapper: `mechanical/tools/slice.sh MANIFEST [options]` |
| `mesh_io.py` | stdlib-only STL read/write, plain 3MF writer (welded vertices), Euler transforms, watertight check, CadQuery tessellation bridge |
| `export_parts.py` | CadQuery helper: shape + print orientation -> STEP, STL and 3MF in print orientation (z = 0 on the bed) with bounding box, volume and bed-fit data |

Requirements: Python 3 with PyYAML (system `python3` is enough for slicing; CadQuery only for `export_parts.py`), docker with
the image `linuxserver/bambustudio:latest` (Bambu Studio 02.09.02.62, binary `/opt/bambustudio/bin/bambu-studio`). The
container runs with `--network none`; nothing is downloaded. The stock presets are read from the image
(`/opt/bambustudio/resources/profiles/BBL`) and cached under `~/.cache/rr_slice/` (override with `RR_SLICE_CACHE`).

## Commands

```bash
python3 mechanical/tools/slice_plates.py mechanical/prototype_x1c/plates.yaml              # every plate
python3 mechanical/tools/slice_plates.py mechanical/head/prototype/plates.yaml --plates H01  # one plate
python3 mechanical/tools/slice_plates.py MANIFEST --precheck-only    # fit / overlap / watertight, no docker
python3 mechanical/tools/slice_plates.py MANIFEST --no-slice         # project .3mf only
python3 mechanical/tools/slice_plates.py MANIFEST --out DIR --timeout 3600 --keep-work
```

Outputs (default `<manifest dir>/out/slices/`): `<id>.3mf` (Bambu Studio project, parts at the manifest positions, stock
machine/process/filament presets + overrides embedded), `<id>.gcode.3mf` (sliced, printable file), `<id>.summary.json`,
and for the whole manifest `slice_summary.json` + `slice_summary.csv`. Exit status is non-zero if any selected plate did
not reach `SLICED`.

## Plate manifest schema `rr-plates/1`

```yaml
schema: rr-plates/1
printer:                      # optional; these are the defaults (stock Bambu Lab X1 Carbon, 0.4 mm nozzle)
  model: "Bambu Lab X1 Carbon"
  machine_profile: "Bambu Lab X1 Carbon 0.4 nozzle"   # stock machine preset name in the image
  bed: [256, 256, 250]        # usable x, y, z (the stock preset prints 250 mm high, not 256)
  exclude_area: [0, 0, 18, 28]   # front-left corner the X1C cannot print on
  edge_margin: 3.0            # mm kept free at the plate edge (raise it for brims)
defaults:
  plate_type: "Textured PEI Plate"        # or "Cool Plate", "Engineering Plate", "High Temp Plate", "Supertack Plate"
  process: "0.20mm Standard @BBL X1C"     # stock process preset name
  part_gap: 6.0                           # mm between auto-arranged parts
materials:                    # named material choices; plates refer to them by key
  PETG-CF:
    filament_profile: "Bambu PETG-CF @BBL X1C 0.4 nozzle"   # stock filament preset name (must exist in the image)
    density_g_cm3: 1.25       # optional, only for the solid-mass estimate in the summary
    process: "0.20mm Strength @BBL X1C"   # optional per-material default process
    plate_type: "Textured PEI Plate"      # optional
    overrides: {}             # optional process-setting overrides applied to every plate of this material
    filament_overrides: {}    # optional filament-setting overrides
    justification: "free text, copied nowhere by the tool"
plates:
  - id: P01                   # unique; used for the output file names
    name: "front beam and motor mounts"
    material: PETG-CF         # key into materials (or give filament_profile: directly)
    process: "0.20mm Strength @BBL X1C"   # optional
    plate_type: "Textured PEI Plate"      # optional
    overrides:                # optional Bambu process keys, scalar values are expanded to the preset's array length
      wall_loops: 4
      sparse_infill_density: "25%"
      enable_support: true
      support_type: "tree(auto)"
      brim_type: outer_only
      brim_width: 5
    edge_margin: 8.0          # optional per-plate margin (brim)
    parts:
      - part: chassis_front            # name shown in Bambu Studio
        mesh: out/stl/chassis_front.stl   # path relative to the manifest; binary or ASCII STL, millimetres
        position: [128, 128]           # bed x, y of the bounding-box centre; omit -> the tool shelf-packs the part
        rotation_z: 90                 # deg about +z, applied before placement (optional)
        orient: {rx: 180, ry: 0, rz: 0}   # optional Euler angles (X, then Y, then Z) for meshes NOT already in print orientation
        qty: 1                         # qty > 1 needs `positions: [[x, y], ...]` or none (auto)
        # any other keys (orientation_note, supports, part_number ...) are ignored by the tool and may be used for documentation
```

Rules: meshes are expected **in print orientation** (the face that goes on the bed at the lowest z); the tool always drops
the part onto z = 0. The tool does not let the slicer re-arrange or re-orient anything (`--arrange 0`), so the project file
shows exactly the manifest layout.

## What the summary means

| `status` | Meaning |
|---|---|
| `SLICED` | CLI returned 0 and the `.gcode.3mf` contains G-code. `slicer.total_time`, `filament_g`, `layers`, `slice_info_support_used` come from the slicer's own output |
| `PRECHECK_FAILED` | tool-side check failed (outside the plate, exclusion corner, overlapping boxes, mesh not watertight, mesh missing); slicer not run |
| `PROJECT_EXPORT_FAILED` / `SLICE_FAILED` / `SLICE_TIMEOUT` | Bambu Studio error; `pending_reason` holds the CLI's `error_string` (e.g. *G-code outside of the printable area*, *object conflicts*, *floating/ empty layers*) |
| `PROJECT_ONLY`, `PRECHECK_OK` | the stage requested with `--no-slice` / `--precheck-only` passed; **not** a slice |

`slicer.messages` lists every `[warning]`/`[error]` line of the CLI log except display noise (the container has no display,
so Bambu Studio cannot render plate thumbnails; the files are otherwise complete). Evidence class of a `SLICED` row:
**tool-checked** (slicer estimate), not a print.

## Known limits

- No thumbnails in the exported 3MF (headless container). Open and re-save in Bambu Studio if the printer UI should show them.
- Estimated time and mass are slicer predictions for the stock presets; filament-specific drying, chamber heat-soak and
  first-layer inspection are not included.
- Stock presets used through `--load-settings` are flattened copies (the CLI does not resolve `inherits` for system
  presets); the preset names are kept, so Bambu Studio shows them as the system presets plus the listed overrides.
