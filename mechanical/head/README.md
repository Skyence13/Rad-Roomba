# mechanical/head -- four-lane detector head, prototype and production builds

Detachable, independently buildable scintillation detector head: four 80 (y) x 100 (x) mm windows at 87.5 mm pitch, entrance film at z 10.00
(10 mm above the floor), 350 mm wide, twin-shoe receiver (mount option C), RR-HEAD-ACQ board above the reference guides under an aluminium
cover. Two builds from one parametric CadQuery model:

- **Prototype RR-HD-X-000**: two PA-CF frame halves printed on a stock Bambu Lab X1 Carbon, split on the y = 0 seam rib between S1 and S2.
- **Production RR-HD-P-000**: one-piece CNC 6061 frame, sheet / laser-cut parts, MJF PA12 and POM small parts (5-25 units per year).

Plus a dummy head (mass / CG / dock / loop representative), a bench cradle with a repeatable 10.00 mm source-to-film standoff and gap gauges (`aux/`).

## Rebuild

```
mechanical/head/build.sh              # everything (about 6-8 min on 4 cores; frames are cached in out/cache)
mechanical/head/build.sh --no-render  # skip the assembly step renders
RR_PY=/path/to/python mechanical/head/build.sh
```

Python 3.12 with cadquery 2.7.0 / OCP 7.8.1, numpy, matplotlib, pyyaml, ezdxf, pillow (same environment as `mechanical/common/requirements.txt` + ezdxf).
`build.sh` deletes and regenerates all generated outputs, and its exit status is that of `checks.py` (non-zero if any check fails). Single steps:

| Command | Output |
|---|---|
| `python -m mechanical.head.checks` | `out/checks.json`, `out/head_report.md` (exit 1 on a failed check) |
| `python -m mechanical.head.export [--no-mesh]` | `prototype/` and `production/` STEP (parts + assembly), `prototype/print/` (STEP, STL, 3MF in print orientation), DXF, `prototype/plates.yaml` |
| `python -m mechanical.head.drawings joints fab steps steps_production` | `prototype/joints/` (full-size joint sections, PNG + SVG), `production/drawings/` (PDF + SVG), `prototype/assembly/`, `production/assembly/`, `aux/dummy_head_lid_off.png` |
| `python -m mechanical.head.docs` | `prototype/purchased_and_fabricated.csv`, `production/bom_production.csv`, `prototype/print_schedule.md`, `prototype/assembly.md`, `production/assembly.md`, `aux/README.md` |

Hand-written: this file, `production/README.md` (fabrication / test pack), `STATUS.md`.

## Where things are

| Path | Content |
|---|---|
| `hp.py` | head parameters; every shared datum is imported from `mechanical/common/params.py` (never retyped) |
| `asbuilt.py` | reads the as-built RR-HEAD-ACQ placement from `electronics/head_acq/RR-HEAD-ACQ.kicad_pcb` (holes, can outlines, mouse holes, clips, courtyards, 3D heights) for the board-fit check |
| `pigtail.py` | J1 / J2 pigtails outside the head: boots, docked / parked paths, check against the body nose STEP (review M6) |
| `routes.py` | every lead inside the head as a routed solid, GH plug keep-outs, `out/lead_routes.yaml` (review M5 / M11) |
| `CHANGE_REQUESTS.md` | requests to electronics, harness, body, common, lead |
| `parts.py` | all part geometry (both builds, dummy, cradle, gauges), base_link coordinates, installed position |
| `assembly.py` | part lists of the three builds with part numbers, materials, masses |
| `calc.py` | closed-form calculations: deflection / modes, rails, light paths, tolerance stack, thermal, OEM-dependent list |
| `checks.py`, `report.py` | tool checks on the solids + calculations -> report |
| `export.py`, `dxf.py`, `draw.py`, `drawings.py`, `docs.py` | outputs |
| `prototype/` | RR-HD-X: STEP, print files, `plates.yaml`, `print_schedule.md`, BOM csv, DXF, joint sections, `assembly.md` |
| `production/` | RR-HD-P: STEP, drawings, DXF, BOM csv, `assembly.md`, `README.md` (fabrication, bonding, sealing, harness, variants, service, end-of-line tests) |
| `aux/` | dummy head, bench cradle, gap gauges (STEP, notes) |

## Parameter guide (hp.py)

| Group | Parameters | Change when |
|---|---|---|
| Lane cavity (OEM-dependent) | `EDGE`, `Z_SEAT`, `STACK`, `PAD_T`, `CARRIER`, `SIPM`, `CHIM_*` | the OEM drawing arrives (list: head_report.md section 8) |
| Split joint (prototype) | `JOINT_Y`, `TONGUE_T/H`, `LAP_T/H`, `DOWEL_D` | print trials show a loose / tight joint |
| Lid fastening | `LID_STANDOFFS`, `LID_BOSS_*`, `INSERT_M3`, `LID_PITCH_MAX` | the 40 mm pitch is re-negotiated; `checks.py` verifies the loop |
| Window cassette | `CAS_*`, `FOOT_*` | film / guard grille changes |
| Leading rail | `RAIL_GAP` (stroke), `BAR_*`, `INS_*`, `CAM_*`, `SPRING`, `PIN_*`, `BAIL_*` | stroke requirement or switch data change |
| Side zones | `SIDE_*`, `GUIDE_PINS`, `SW_SIDE` | |
| Switch | `SW` (D2HW-C201M; PARTIAL data) | datasheet confirmed |
| Ports, vent, drain | `PORT_*`, `CABLE_D`, `VENT`, `DRAIN` | connector / cable selection |

## Calculated vs tool-checked

- **Tool-checked** (on the CadQuery solids, every build): pairwise interference of every part including modelled screw heads (prototype, production,
  dummy; rail at rest and at full stroke with both inserts; side rails at their stop; 5 mm side strips; transport covers), windows and film plane vs the
  contract, rail heights, board standoffs vs `board_envelopes.yaml`, board height limits, envelope, shoes / keeper / ports vs `mechanical_interfaces.md`,
  bed fit and downward-facing faces of every printed part in print orientation, split joint vs windows, EMI bond pitch (clamping checked), lid fastener
  pitch and hard seats, drain passage and line of sight, FRAME-to-receiver isolation gap, spreader hole webs.
- **Tool-checked against the board file** (IB-52): the as-built RR-HEAD-ACQ (`electronics/head_acq/RR-HEAD-ACQ.kicad_pcb`, parsed by `asbuilt.py`):
  8 holes vs standoffs and spreader holes, 4 can outlines / mouse holes / 48 clips vs the can model, J1 port vs the J2001 centre, all 1073 component bodies
  (courtyard x 3D envelope height, Micro-Fit at 8.3 mm) intersected with every head part, mated Micro-Fit plug keep-outs (CR-M03 v -8.4..1.5) in the assemblies.
- **Calculated** (closed form, stated assumptions in calc.py): masses / CG (model volumes x handbook densities, OEM modules assumed 50 + 52 g), corner
  deflection and modes, rail kinematics and forces (switch data PARTIAL), tolerance stack, heater power on the IB-39 assumption set (`out/thermal_summary.json`),
  warm-up, rail-switch lead lengths, light-path table (geometry analysis, not a light test).
- **Not done**: slicing (owner slices from STEP), FEA, any physical test. Supplier data marked UNVERIFIED / PARTIAL in the BOM csv files.

## Open items (details: head_report.md section 2, CHANGE_REQUESTS.md, STATUS.md)

1. **Front GH headers (DEVIATION, CR-H17):** J2002 / J2003 / J2004 / J2201 / J2402 cannot be mated in the front strip (plug + crimp reach x 185.65,
   wall 185.6, prototype fence 180.0, bosses, a lid standoff, desiccant). Board-side change requested.
2. **Pigtail boots / holsters above z 50 (DEVIATION, CR-HL1):** local items to z 70 forward of the nose-cowl V, checked free of the body.
3. **Lid fastener pitch (DEVIATION):** 47 mm on the -y rear line (CR-M08). 4. Slot / window rule: 27 mm saddle windows in the prototype fence foot.
5. Head mass 1881 g (prototype) / 2100 g (production) vs 1.67 / 2.10 kg in mech_calcs.md (+17 g: pigtail boots and holsters, review M6).
6. Heater (IB-39, +5 C, CR-10 shoe basis): fits the 30 W films at 12 V in all jacketed cases; at 10 V the 25 W/m2K cases exceed (head_report.md section 9).
7. Every OEM-dependent dimension (head_report.md section 8); switch data PARTIAL; most PUR items UNVERIFIED (Micro-Fit / GH plug data, wire ODs,
   D2HW lead length, G10 / washer conductivities, M16 contact range for AWG 20).
