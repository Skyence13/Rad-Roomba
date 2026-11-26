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
| 2 | `python -m mechanical.common.gen_interfaces` | `board_envelopes.yaml`, `frames.yaml`, `out/mechanical_interfaces.md`, `out/boards/RR-*-envelope.step` |
| 3 | `python -m mechanical.common.layout [--rail 3\|5] [--no-png]` | `out/RR_E_master_layout.step`, `out/RR_E_head_layout.step`, `out/RR_E_master_layout_{top,side,front}.png`, `out/layout_report.md`, `out/layout_checks.json` |
| 4 | `python -m mechanical.common.calc.run_all` | `out/mech_calcs.md`, `out/gap_measurement_method.md`, `out/head_mount_trade_study.md`, `out/mech_calcs.json` |

`out/cache/` holds BREP caches of the lofted shells keyed on the parameters; delete it to force a full rebuild.
Inputs read from outside this folder: `interface/system/contract.yaml`, `cad/source/body_shell.py` (section tables
are parsed, not imported), `cad/Rad_Roomba_D.step` (optical stack, head frame and rails are reused, shifted by `P.HEAD_DX`; the Rev D neck,
tongue and key socket are no longer used).

Checks that fail the build: volumetric interference between hard envelopes, containment of internal parts in the
body cavity, head inside the contract Rev E envelope, wheels and caster on the floor plane, the 11 ToF centre rays
and the LiDAR scan plane, service sweeps (battery, wheels, head, grip hand zone), the 45 mm glove zone round the J1/J2
coupling nuts, reserved cable corridors, mass above 12 kg, look-ahead cone edge into the head. The ray tool has a
self-test (a ray aimed at the head must hit it). The negative forward tip margin is reported as a finding, not a
build failure.

## What downstream engineers import

```python
from mechanical.common import params as P          # no CadQuery needed
P.HEAD_MOUNT, P.ROW_X, P.HEAD_DX, P.RECEIVER       # mount option C datums (CCR-11); P.SEG_Y, P.FILM_Z from the contract
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
| contract datums | loaded from `contract.yaml` (`C`): axle 52, wheel 104, track 270, caster, film z 10, lanes, motion limits, board outlines; `HEAD_MOUNT_CONTRACT` / `ROW_X_CONTRACT` keep the contract values until CCR-11 is applied |
| `ROW_X`, `HEAD_DX`, `HEAD_MOUNT`, `RECEIVER` | head mount option C: row x 131.2, rigid head shift -72.8, mount datum (65.7, 0, 32), shoe / channel / land / latch / beam / chin dimensions |
| `BODY_SCALE_XYZ`, `BODY_PIVOT` | Rev E body proposal: Rev D section tables scaled 1.40 (length) / 1.30 (width, height) about the Rev D nose and underside, so all growth is rearward and upward |
| `TRACK`, `CASTER_SWIVEL`, `CASTER_MOUNT_Z`, `MOTOR_*`, `DRIVE_POD` | running gear; motor can clocked 7 mm above the axle (eccentric output shaft) so the plate needs no cut-outs |
| `HEAD_STACK`, `HEAD_TOP_Z`, `HEAD_ACQ` | head stack above the reference guides and the acquisition board |
| `CHS_MAIN`, `ELECTRONICS_BRIDGE_*`, `SADDLE`, `GRIP` | main board on a bridge over the motors under the removable grip saddle |
| `BATTERY_BAY` | centre-line cassette for the 12 Ah pack, dorsal hump, removal direction −x through the tail-cap hatch |
| `TOF_SENSORS`, `PANEL_CONTROLS`, `J_RECEPTACLES`, `CHARGE_INLET` | positions computed on the skin from the section law |

## Current design state (2026-11-26)

Adopted by the lead (contract 0.4.0-draft4): Rev E body (Rev D section law scaled 1.40 length / 1.30 width and height about
the nose and underside), track 270, caster contact at -204, bridge grip over the main board, LiDAR aft, 12 Ah pack as baseline.
Implemented here and **pending contract change CCR-11..14**: local growth for the 12 Ah pack and head mount option C.

| | Rev D | Rev E as built here |
|---|---|---|
| Body shell x / width / crown z | -165..102 / 225 / 117.6 | -272..102 / 293 / 143; battery hump top 150 (x -233..-70.5, 121 wide), sensor brow 166 |
| Track / across tyres | 220 / 245 | 270 / 295 |
| Caster contact x | -116 | -204 |
| Head mount datum / optical row x | 138.5 / 204.0 | **65.7 / 131.2** (option C) |
| Head envelope x | 138.8..265.0 | 66.0..192.2 (+ two shoes back to x 4) |
| Overall length x width x height | 430 x 350 x 159 | **464 x 350 x 230** (LiDAR top; grip bar top 175) |
| Swept radius: head corner / tail | 318 / 176 | 260 / 278 |

- **12 Ah pack (DEC-040)**: PSL-SC-12120 lies on its 151 x 101 side, 99 mm tall; cassette z 40..144, removed rearward through the
  tail-cap hatch. Growth is a dorsal hump over the tunnel only (7 mm above the crown); the LiDAR base rises from z 136 to 150.
  The 9 Ah PSL-SC-1290 fits the same cassette with a spacer.
- **Head mount (DEC-041)**: `out/head_mount_trade_study.md` compares A (Rev D neck), B (twin arms at the lane seams), C (twin shoes,
  overhang shortened) and D (floor-following). C is recommended and implemented: two 16 x 14 mm shoes on the head at y = +-87.5
  slide into two channels under the chassis front beam, one draw latch under the nose tip, row at x = 131.2. The neck is deleted
  and the lower hull ends at x = 62 below z = 50.
- **Interfaces for the three downstream engineers**: `out/mechanical_interfaces.md` (generated).
- Forward tip margin (0.4 m/s2 braking, 5 deg down-slope, heaviest head): +26.6 mm with the 12 Ah pack, +17.4 mm with the 9 Ah
  pack; no ballast. With the Rev D neck it would be +5.8 / -5.0 mm.

Items still needing a decision or confirmation:

- CCR-11..14 (new mount datum, row x, head envelope, body envelope, corner radius, sensor positions).
- Carry attitude: the centre of gravity is now 24..33 mm behind the grip (tail-down 15..20 deg with a head, more without).
- Head front ends are about 65 mm ahead of the gearmotor cans (EMI check by head electronics).
- Rail stroke / stop inputs (CCR-08) and heater budget (CCR-10) are unchanged findings.
- Ground clearance under the receiver channels is 12 mm.

Change requests to the contract are in `CONTRACT_CHANGE_REQUESTS.md`.

## Assumptions needing supplier or measured confirmation

1. **Gearmotor**: 7 mm shaft eccentricity, boss Ø12 × 6, 6 × M3 on Ø31, cold behaviour — recalled, drawing is an image (UNVERIFIED). Length 72.5, Ø37, shaft Ø6 × 16, 0.21 kg, torque/current figures VERIFIED.
1b. **Mount**: contact stiffness 1500 / 6000 N/mm per bearing land (printed / aluminium) is an assumption common to all mount options; prove with the 20 N corner test.
2. **Drive wheel**: no catalogue 104 × 25 mm wheel or hub verified (open item); mass assumed 0.15 kg.
3. **Caster** (TENTE Compacta 25 mm, dimensions VERIFIED): plain bearing, rated to −20 °C only; a sealed ≤ 36 mm caster was not found.
4. **Battery**: PSL-SC-12120 (baseline) dimensions, mass, 15 A continuous and -20 C discharge limit VERIFIED from the datasheet; BMS cold behaviour to confirm. PSL-SC-1290 (alternative) dimensions and mass VERIFIED.
5. **Battery coupler** (Anderson SBS50 candidate), **selector, pushbuttons, charge inlet, J1/J2 receptacle and plug dimensions**: recalled (UNVERIFIED). E-stop depth 43 mm from a distributor (50 used).
6. **CM5 / carrier**: 85 × 56 outline and interfaces VERIFIED; assembled height 24 mm, hole pattern, CM5 temperature range UNVERIFIED.
7. **LiDAR**: 60 × 60 × 80 from the family listing (PARTIAL); scan plane 60 mm above the base, connector exit and mounting holes UNVERIFIED — this sets `lidar_link` z and the clearance over the grip bar (35 mm calculated).
8. **VL53L4ED** 18° field of view and 1.3 m range recalled; grazing-incidence performance of the forward look-ahead (18° to the floor, 524 mm) is a test item.
9. **Optical module thickness** above z 28.5 (supplier drawing pending): 1.5 mm pad allowance.
10. **Masses** of all printed/machined structure, harness and head (±15 %); receiver stiffness 1500 / 6000 N·m/rad and play; tyre stiffness 40 N/mm; friction 0.6 / 0.3; film coefficients 12 / 25 W/m²K; polymer moduli (data-sheet class values, anisotropy and cold not measured).
11. **Floor features** used in the gap budget (1.5 / 3 / 5 mm) are representative values, not site data.
12. Body inner skin is the scaled Rev D inner table (about 5 mm wall); a thinner real wall only adds margin.

## Known gaps

- No fasteners, printable splits, seals or drawings: envelope fidelity only (left to the three downstream engineers).
- Head rail switches, body bumper band and dock switch are placed as points/small boxes, not designed.
- Cable corridors are reserved boxes checked for interference; no harness lengths.
- A flush (recessed) grip is not achievable; the grip is 24..33 mm ahead of the centre of gravity.
- No FEA; cantilever and frequency results are beam/lumped estimates with assumed joint stiffness.
