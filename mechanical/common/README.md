# mechanical/common — Rev E master layout (mechanical lead)

Single parametric source for both mechanical builds (X1C prototype and production), the purchased-part envelope
library, the board envelopes for the electronics leads, the static frames for the robot software, the master layout
assembly with automated checks, and the mechanical calculations.

**Status of every number: design value.** Results are labelled `calculated` (closed-form, in `calc/`) or
`tool-checked` (OCC kernel on nominal envelope solids, in `layout.py`). Nothing is simulated by FEA and nothing is
physically measured. Purchased-part dimensions carry a per-dimension verification status in `purchased/parts.yaml`.

## Rebuild

```bash
# once: recreate the environment (Python 3.12)
cd mechanical/common
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
# every time (from anywhere): regenerates all outputs and runs all checks, non-zero exit on failure, about 1.5 min
mechanical/common/build.sh              # or: RR_PY=/path/to/python mechanical/common/build.sh
mechanical/common/build.sh --rail 5     # same with the 5 mm rail insert
```

`build.sh` runs, from the repository root:

| Step | Command | Writes |
|---|---|---|
| 1 | `python -m mechanical.common.params` | `out/params_summary.json` |
| 2 | `python -m mechanical.common.gen_interfaces` | `board_envelopes.yaml`, `frames.yaml`, `out/boards/RR-*-envelope.step` |
| 3 | `python -m mechanical.common.layout [--rail 3\|5] [--no-png]` | `out/RR_E_master_layout.step`, `out/RR_E_head_layout.step`, `out/RR_E_master_layout_{top,side,front}.png`, `out/layout_report.md`, `out/layout_checks.json` |
| 4 | `python -m mechanical.common.calc.run_all` | `out/mech_calcs.md`, `out/gap_measurement_method.md`, `out/mech_calcs.json` |

`out/cache/` holds BREP caches of the lofted shells keyed on the parameters; delete it to force a full rebuild.
Inputs read from outside this folder: `interface/system/contract.yaml`, `cad/source/body_shell.py` (section tables
are parsed, not imported), `cad/Rad_Roomba_D.step` (neck, receiver, optical stack, rails and key socket are reused
unchanged).

Checks that fail the build: volumetric interference between hard envelopes, containment of internal parts in the
body cavity, head inside the contract Rev E envelope, wheels and caster on the floor plane, the 11 ToF centre rays
and the LiDAR scan plane, service sweeps (battery, wheels, head, grip hand zone), the 45 mm glove zone round the J1/J2
coupling nuts, reserved cable corridors, mass above 12 kg, look-ahead cone edge into the head. The ray tool has a
self-test (a ray aimed at the head must hit it). The negative forward tip margin is reported as a finding, not a
build failure.

## What downstream engineers import

```python
from mechanical.common import params as P          # no CadQuery needed
P.HEAD_MOUNT, P.ROW_X, P.SEG_Y, P.FILM_Z           # contract datums (loaded from contract.yaml)
P.HEAD_STACK, P.HEAD_TOP_Z, P.HEAD_ACQ             # head stack-up and acquisition board (origin, holes, limits)
P.CHS_MAIN, P.board_to_base(origin, u, v)          # main board and the board->base_link transform
P.BODY_ROWS, P.half_breadth(x, z, "inner"|"outer"), P.roof_z(x, y), P.inside_body(x, y, z)   # Rev E skin
P.TRACK, P.CASTER_SWIVEL, P.MOTOR_AXIS_Z, P.BATTERY_BAY, P.SADDLE, P.GRIP, P.LIDAR_POSE, P.CM5_POSE
P.TOF_SENSORS, P.PANEL_CONTROLS, P.J_RECEPTACLES, P.CHARGE_INLET, P.MATERIALS
from mechanical.common.purchased import library as L   # CadQuery envelope solids: L.motor(), L.caster(), L.receptacle(...)
from mechanical.common import layout                   # layout.build(rail) -> placed parts; layout.interference(parts)
```

Rules: never retype a datum — import it; contract values come from `P.C`; change a layout decision only in
`params.py` and rerun `build.sh`; `board_envelopes.yaml` and `frames.yaml` are generated, do not edit them.
Head mechanical owns everything inside `P.HEAD_ENV_E`; the optical stack below z = 28.5 is Rev D and frozen.

## Parameter guide (params.py)

| Block | Meaning |
|---|---|
| contract datums | loaded from `contract.yaml` (`C`): axle 52, wheel 104, head mount (138.5, 0, 32), row x 204, film z 10, lanes, motion limits, board outlines |
| `BODY_SCALE_XYZ`, `BODY_PIVOT` | Rev E body proposal: Rev D section tables scaled 1.40 (length) / 1.30 (width, height) about the Rev D nose and underside, so all growth is rearward and upward |
| `TRACK`, `CASTER_SWIVEL`, `CASTER_MOUNT_Z`, `MOTOR_*`, `DRIVE_POD` | running gear; motor can clocked 7 mm above the axle (eccentric output shaft) so the plate needs no cut-outs |
| `HEAD_STACK`, `HEAD_TOP_Z`, `HEAD_ACQ` | head stack above the reference guides and the acquisition board |
| `CHS_MAIN`, `ELECTRONICS_BRIDGE_*`, `SADDLE`, `GRIP` | main board on a bridge over the motors under the removable grip saddle |
| `BATTERY_BAY` | centre-line cassette, removal direction −x through the tail-cap hatch |
| `TOF_SENSORS`, `PANEL_CONTROLS`, `J_RECEPTACLES`, `CHARGE_INLET` | positions computed on the skin from the section law |

## Body proposal (lead decision D-1) and the other decisions needed

The Rev D shell (267 × 225 × 85 mm, 1.8 l free) cannot contain the selected hardware (2.1 l of bare envelopes;
`out/layout_report.md` §3). Proposal, with a complete checked layout:

| | Rev D | Rev E proposal |
|---|---|---|
| Body shell x / width / top z | −165…102 / 225 / 117.6 | −272…102 / 293 / 143 (same section law and station tables) |
| Track / across tyres | 220 / 245 | 270 / 295 |
| Caster contact x | −116 | −204 |
| Overall length × width × height | 430 × 350 × 159 | 537 × 350 × 216 (LiDAR top; grip bar top 175) |
| Tail swept radius | 176 | 278 (inside the 318 mm head-corner circle) |

Sizing drivers: the 160 × 100 main board needs the 1.30 width at z 83–103; the 151 × 99 × 65 pack in a rear-removable
cassette needs the 1.40 length; the cantilevered head needs everything else behind the axle (see D-3).

- **D-1 body growth** as above (CCR-01…03). Alternatives considered: uniform 1.30 (pack and board collide), uniform 1.40
  (works, 22 mm wider for no benefit), stretch only (board does not fit the Rev D width).
- **D-2 carry grip and LiDAR swap places.** The Rev D deep hand well cannot coexist with a 65 mm pack under it at any
  scale below about 1.8. Proposed: a transverse bridge grip over the centre of gravity (bar z 153–175, 45 mm glove
  clearance, hang angle within ±6° with a head fitted) whose saddle is the service cover of the main board; the LiDAR
  moves aft over the battery tunnel. This changes the top-side appearance; the shell form is kept.
- **D-3 balance.** Calculated forward tip margin is −7…+18 mm; with the 9 Ah pack and the heaviest head the caster
  unloads under 0.4 m/s² braking on a 5° down-slope. Remedy: 0.85 kg tail ballast (still 9.8 kg total), or the 12 Ah
  pack (does not fit, D-4), or a lighter head, or a support roller under the neck (architecture change).
- **D-4 pack size.** 12 Ah (151 × 99 × 101) needs 35 mm more tail height; not contained.
- **D-5 rail stroke / stop inputs** (CCR-08), **D-6 heater budget** (CCR-10).

Change requests to the contract are in `CONTRACT_CHANGE_REQUESTS.md`.

## Assumptions needing supplier or measured confirmation

1. **Gearmotor**: 7 mm shaft eccentricity, boss Ø12 × 6, 6 × M3 on Ø31, cold behaviour — recalled, drawing is an image (UNVERIFIED). Length 72.5, Ø37, shaft Ø6 × 16, 0.21 kg, torque/current figures VERIFIED.
2. **Drive wheel**: no catalogue 104 × 25 mm wheel or hub verified (open item); mass assumed 0.15 kg.
3. **Caster** (TENTE Compacta 25 mm, dimensions VERIFIED): plain bearing, rated to −20 °C only; a sealed ≤ 36 mm caster was not found.
4. **Battery**: PSL-SC-1290 dimensions and mass VERIFIED; discharge range read without row labels (same as the verified 12 Ah sheet); BMS cold behaviour and continuous current to confirm. Contract says 8 Ah, pack is 9 Ah.
5. **Battery coupler** (Anderson SBS50 candidate), **selector, pushbuttons, charge inlet, J1/J2 receptacle and plug dimensions**: recalled (UNVERIFIED). E-stop depth 43 mm from a distributor (50 used).
6. **CM5 / carrier**: 85 × 56 outline and interfaces VERIFIED; assembled height 24 mm, hole pattern, CM5 temperature range UNVERIFIED.
7. **LiDAR**: 60 × 60 × 80 from the family listing (PARTIAL); scan plane 60 mm above the base, connector exit and mounting holes UNVERIFIED — this sets `lidar_link` z and the clearance over the grip bar (21 mm calculated).
8. **VL53L4ED** 18° field of view and 1.3 m range recalled; grazing-incidence performance of the forward look-ahead (14° to the floor, 670 mm) is a test item.
9. **Optical module thickness** above z 28.5 (supplier drawing pending): 1.5 mm pad allowance.
10. **Masses** of all printed/machined structure, harness and head (±15 %); receiver stiffness 1500 / 6000 N·m/rad and play; tyre stiffness 40 N/mm; friction 0.6 / 0.3; film coefficients 12 / 25 W/m²K; polymer moduli (data-sheet class values, anisotropy and cold not measured).
11. **Floor features** used in the gap budget (1.5 / 3 / 5 mm) are representative values, not site data.
12. Body inner skin is the scaled Rev D inner table (about 5 mm wall); a thinner real wall only adds margin.

## Known gaps

- No fasteners, printable splits, seals or drawings: envelope fidelity only (left to the three downstream engineers).
- Head rail switches, body bumper band and dock switch are placed as points/small boxes, not designed.
- Cable corridors are reserved boxes checked for interference; no harness lengths.
- The 12 Ah pack and a flush (recessed) grip are not achievable in this proposal.
- No FEA; cantilever and frequency results are beam/lumped estimates with assumed joint stiffness.
