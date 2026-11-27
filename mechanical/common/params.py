"""Rad Roomba Rev E master-layout parameters -- the single parametric source for both builds.

Units: millimetres, kilograms, degrees Celsius unless a name says otherwise.
Frame: ``base_link`` = Rev D CAD origin (level floor below the drive-axle midpoint), +x forward, +y left, +z up.

Rules
-----
* Anything that exists in ``interface/system/contract.yaml`` is LOADED from it (``C``), never retyped.
* The Rev D rounded-body section tables are PARSED from ``cad/source/body_shell.py`` (never retyped) and
  transformed by the Rev E body proposal (uniform scale about the nose/underside pivot).
* Every layout decision made here is a design value (evidence class: calculated / tool-checked by
  ``layout.py``), nothing is physically measured.
* This module imports only the standard library, ``math`` and ``yaml`` so firmware/ROS tooling can import it
  without CadQuery.

Downstream:  ``from mechanical.common import params as P``
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT_PATH = REPO / "interface" / "system" / "contract.yaml"
REV_D_STEP = REPO / "cad" / "Rad_Roomba_D.step"
REV_D_SHELL_SRC = REPO / "cad" / "source" / "body_shell.py"
OUT = HERE / "out"

C = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
CONTRACT_VERSION = C["contract_version"]
_F = C["frames"]

# --------------------------------------------------------------------------- contract datums (loaded)
AXLE_Z = float(_F["axle_height_mm"])                      # 52.0
WHEEL_D = float(_F["wheel"]["nominal_diameter_mm"])       # 104.0
WHEEL_R = WHEEL_D / 2
CONTRACT_TRACK = float(_F["wheel"]["track_mm"])           # 270.0 since contract 0.4.0-draft4 (CCR-01 adopted, DEC-039)
ENCODER_CPR = int(_F["wheel"]["encoder_counts_per_wheel_rev"])
CONTRACT_CASTER = dict(_F["caster"])                      # Rev D values; Rev E proposal below (CCR-02)
HEAD_MOUNT_CONTRACT = tuple(float(v) for v in _F["head_mount"]["xyz_mm"])  # (138.5, 0, 32) until CCR-11 is applied
HEAD_ENV_D = {k: tuple(v) for k, v in _F["head_envelope_rev_d_mm"].items()}
HEAD_ENV_E_CEILING = {k: tuple(v) for k, v in _F["head_envelope_rev_e_mm"].items()}
_O = _F["optics"]
ROW_X_CONTRACT = float(_O["row_center_x_mm"])             # 204 until CCR-11 is applied
# ---- head mount, option C of out/head_mount_trade_study.md (DEC-041): twin shoe receiver on the lane seams, overhang shortened.
# The head itself (optics, stack, board, rails) is the Rev D/Rev E head translated rigidly in x; nothing inside it moves.
REV_D_ROW_X = 204.0                                       # x of the optical row in cad/Rad_Roomba_D.step (geometry reference)
REV_D_HEAD_MOUNT = (138.5, 0.0, 32.0)                     # Rev D mount datum in the same STEP
ROW_X = 131.2                                             # PROPOSED row centre (CCR-11). Limit: tyre front (x 51.5 at head height) + 14.5 mm
HEAD_DX = round(ROW_X - REV_D_ROW_X, 3)                             # -72.8: rigid shift of every head coordinate
HEAD_MOUNT = (round(REV_D_HEAD_MOUNT[0] + HEAD_DX, 3), 0.0, REV_D_HEAD_MOUNT[2])   # (65.7, 0, 32): row stays 65.5 mm ahead of the mount datum
FILM_Z = float(_O["entrance_film_z_mm"])                  # 10
RAIL_PROJECTIONS = tuple(float(v) for v in _O["rail_projection_options_mm"])   # (3, 5)
SEG_PITCH = float(_O["segment_pitch_mm"])                 # 87.5
ACTIVE_X = float(_O["active_x_mm"])                       # 100 along travel
ACTIVE_Y = float(_O["active_y_mm"])                       # 80 across travel
SEG_Y = tuple(float(v) for v in _O["segment_center_y_mm"])  # S0 (left) .. S3 (right)
_M = C["motion"]
V_SURVEY = float(_M["survey_speed_mps"])
V_MAX_FWD = float(_M["max_forward_speed_mps"])
V_MAX_REV = float(_M["max_reverse_speed_mps"])
YAW_MAX = float(_M["max_yaw_rate_radps"])
A_MAX = float(_M["max_accel_mps2"])
A_DECEL = float(_M["controlled_decel_mps2"])
STOP_T_DELAY, STOP_A_MIN, STOP_MARGIN_M = 0.15, 0.40, 0.020   # design inputs quoted in contract motion.stop_model
BOARDS_C = C["boards"]
POWER_C = C["power"]
MASS_GOAL_KG = 12.0          # RQ-002 packaging ceiling (planning/requirements.csv)
T_OPERATING_C, T_QUAL_C = -20.0, -25.0   # RQ-029

# --------------------------------------------------------------------------- Rev D rounded form (parsed, not retyped)
def _parse_rev_d_tables():
    tree = ast.parse(REV_D_SHELL_SRC.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("UPPER", "LOWER", "inner_rows"):
                found[name] = ast.literal_eval(node.value)
            elif name == "inner_lo" and isinstance(node.value, ast.Call):
                found[name] = ast.literal_eval(node.value.args[0])
    missing = {"UPPER", "LOWER", "inner_rows", "inner_lo"} - set(found)
    if missing:
        raise RuntimeError(f"Rev D shell tables not found in {REV_D_SHELL_SRC}: {missing}")
    return found


_T = _parse_rev_d_tables()
CHASSIS_PLATE_Z = (33.0, 37.0)  # Rev D chassis plate elevation retained (4 mm); its top is the cavity floor
REV_B_TO_D_DX = -10.0   # cad/source/build_concept.py translates the Rev B body by -10 mm in x
SUPER_EXP = 0.925       # exponent and egg factor of body_shell.ringwire()
EGG = 0.185


def _to_d(rows):
    """(z, tail, nose, half-breadth) rows in Rev D coordinates."""
    return [(z, t + REV_B_TO_D_DX, n + REV_B_TO_D_DX, b) for z, t, n, b in rows]


REV_D_ROWS = {"upper_outer": _to_d(_T["UPPER"]), "lower_outer": _to_d(_T["LOWER"]),
              "upper_inner": _to_d(_T["inner_rows"]), "lower_inner": _to_d(_T["inner_lo"])}
REV_D_NOSE_X = max(r[2] for r in REV_D_ROWS["upper_outer"])    # 102.0 (table value, loft overshoots to 102.26)
REV_D_UNDERSIDE_Z = min(r[0] for r in REV_D_ROWS["lower_outer"])  # 33.0

# --------------------------------------------------------------------------- Rev E BODY PROPOSAL (lead decision D-1)
# The Rev D body (267 x 225 x 85 mm shell) cannot contain the selected hardware (see out/layout_report.md).
# Proposal: the approved rounded section law and station tables are kept and scaled, growing rearward and upward
# only: 1.30 in width and height, 1.40 in length (see README "Body proposal" for the sizing drivers).
BODY_SCALE_XYZ = (1.40, 1.30, 1.30)
BODY_SCALE = BODY_SCALE_XYZ[1]    # the width/height factor, quoted as "the" scale
BODY_PIVOT = (REV_D_NOSE_X, 0.0, REV_D_UNDERSIDE_Z)   # nose x and underside z stay where Rev D has them


def d_to_e(x, y, z):
    """Rev D body point -> Rev E body point."""
    px, _, pz = BODY_PIVOT
    sx, sy, sz = BODY_SCALE_XYZ
    return (px + (x - px) * sx, y * sy, pz + (z - pz) * sz)


def e_to_d(x, y, z):
    px, _, pz = BODY_PIVOT
    sx, sy, sz = BODY_SCALE_XYZ
    return (px + (x - px) / sx, y / sy, pz + (z - pz) / sz)


def _row_e(row):
    z, t, n, b = row
    return (d_to_e(0, 0, z)[2], d_to_e(t, 0, 0)[0], d_to_e(n, 0, 0)[0], b * BODY_SCALE_XYZ[1])


BODY_ROWS = {k: [_row_e(r) for r in v] for k, v in REV_D_ROWS.items()}   # Rev E section tables (z, tail, nose, b)


def ring_point(row, theta):
    """Point on a body section ring (same law as cad/source/body_shell.ringwire)."""
    z, tail, nose, b = row
    cen, half = (tail + nose) / 2, (nose - tail) / 2
    c, s = math.cos(theta), math.sin(theta)
    x = cen + half * math.copysign(abs(c) ** SUPER_EXP, c)
    y = b * math.copysign(abs(s) ** SUPER_EXP, s) * (1 - EGG * c)
    return (x, y, z)


def _interp_row(rows, z):
    if z < rows[0][0] or z > rows[-1][0]:
        return None
    for a, b in zip(rows, rows[1:]):
        if a[0] <= z <= b[0]:
            f = 0.0 if b[0] == a[0] else (z - a[0]) / (b[0] - a[0])
            return tuple(a[i] + f * (b[i] - a[i]) for i in range(4))
    return rows[-1]


def _half_breadth_row(row, x):
    _, tail, nose, b = row
    cen, half = (tail + nose) / 2, (nose - tail) / 2
    u = (x - cen) / half
    if abs(u) >= 1:
        return 0.0
    c = math.copysign(abs(u) ** (1 / SUPER_EXP), u)
    s = math.sqrt(max(0.0, 1 - c * c))
    return b * s ** SUPER_EXP * (1 - EGG * c)


def half_breadth(x, z, surface="inner"):
    """Body half-breadth |y| at station x, height z for the Rev E 'inner' or 'outer' skin (0 outside).
    Linear interpolation between section rows (the loft is a spline; allow >= 1.5 mm margin when using this)."""
    best = 0.0
    if surface == "inner":      # cavity floor: the chassis plate top closes the hull below the lowest inner station
        z0 = BODY_ROWS["lower_inner"][0][0]
        if CHASSIS_PLATE_Z[1] <= z < z0:
            z = z0
    for part in ("upper", "lower"):
        row = _interp_row(BODY_ROWS[f"{part}_{surface}"], z)
        if row is not None:
            best = max(best, _half_breadth_row(row, x))
    return best


def roof_z(x, y, surface="outer"):
    """Height of the upper skin above (x, y) (bisection on half_breadth); None if outside the plan form."""
    rows = BODY_ROWS[f"upper_{surface}"]
    lo, hi = rows[0][0], rows[-1][0]
    if half_breadth(x, lo, surface) <= abs(y):
        return None
    if half_breadth(x, hi, surface) > abs(y):
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        if half_breadth(x, mid, surface) > abs(y):
            lo = mid
        else:
            hi = mid
    return lo


def inside_body(x, y, z, margin=1.5):
    """True if the point is inside the Rev E inner skin with the given margin."""
    return half_breadth(x, z, "inner") - abs(y) >= margin


BODY_TAIL_X = min(r[1] for r in BODY_ROWS["upper_outer"])
BODY_NOSE_X = max(r[2] for r in BODY_ROWS["upper_outer"])
BODY_HALF_WIDTH = max(r[3] for r in BODY_ROWS["upper_outer"]) * (1 + EGG * 0.42)  # approx; layout.py reports the tool-checked value
BODY_UNDERSIDE_Z = BODY_ROWS["lower_outer"][0][0]
BODY_CROWN_Z = BODY_ROWS["upper_outer"][-1][0]
BODY_SPLIT_Z = BODY_ROWS["upper_outer"][0][0]          # shell split / perimeter seal line

# --------------------------------------------------------------------------- running gear (layout decisions)
TRACK = CONTRACT_TRACK        # tyre centre to tyre centre, 270 (loaded)
WHEEL_Y = TRACK / 2
TYRE_WIDTH = 25.0             # Rev D tyre section retained
WHEEL_ARCH_R = 56.0           # Rev D arch radius 55.8 retained (not scaled; wheel is not scaled)
WHEEL_ARCH_INNER_Y = WHEEL_Y - 14.3   # Rev D relation: arch cut plane 14.3 mm inboard of the tyre centre
MOTOR_SHAFT_OFFSET = 7.0      # output shaft is eccentric to the 37 mm can (UNVERIFIED, recalled from the Pololu drawing)
MOTOR_AXIS_Z = AXLE_Z + MOTOR_SHAFT_OFFSET   # can clocked straight UP so it clears the chassis plate without cut-outs
MOTOR_FACE_Y = WHEEL_Y - 20.0  # gearbox face; boss 6 + shaft 16 puts the shaft tip 2 mm beyond the tyre centre plane
CASTER_SWIVEL = (float(CONTRACT_CASTER["swivel_x_mm"]), float(CONTRACT_CASTER["y_mm"]))  # (-195, 0) loaded; trail = caster offset 9 mm
CASTER_MOUNT_Z = 36.0          # mounting face = caster overall height (Tente Compacta 25 mm: 36 mm) -> ride height kept

# --------------------------------------------------------------------------- detector head, Rev E stack (z, mm)
# Optical stack below z = 28.5 is Rev D unchanged (cad/source/build_concept.py). Above the reference guides:
HEAD_REF_GUIDE_TOP_Z = 28.5
HEAD_STACK = [   # (name, z_bottom, z_top, note)
    ("module_retention_pad_and_heater", 28.5, 30.0, "1.2 mm compliant thermal/light-seal pad + 0.3 mm polyimide heater film bonded to the spreader underside, zoned per lane"),
    ("spreader_plate", 30.0, 32.0, "one-piece 2.0 mm aluminium heat spreader / stiffener / EMI screen across the y = 0 split (DEC-034); sits on the frame top"),
    ("pcb_bottom_clearance", 32.0, 34.5, "0.25 mm insulating film on the spreader + 2.0 mm bottom-side parts + 0.25 mm air"),
    ("RR-HEAD-ACQ_pcb", 34.5, 36.1, "1.6 mm, 4 layers"),
    ("pcb_top_parts", 36.1, 42.1, "6.0 mm maximum component height"),
    ("cover_clearance", 42.1, 43.0, "0.9 mm (cover deflection + tolerance)"),
    ("cover_skin", 43.0, 45.0, "2.0 mm cover (printed PA-CF/ASA prototype, 1.5 mm Al or MJF PA12 production) with perimeter seal"),
]
HEAD_FRAME_TOP_Z = 30.0        # Rev D frame top 32.6 lowered to carry the spreader
HEAD_TOP_Z = 45.0              # Rev E head ceiling used (contract ceiling 50, Rev D 39 cover / 42 socket)
HEAD_FRAME_FRONT_X = round(HEAD_ENV_D["x"][1] + HEAD_DX, 3)   # 192.2: front of the head frame (rail bar fully stroked at 195.2)
HEAD_ENV_E = {"x": (round(HEAD_ENV_D["x"][0] + HEAD_DX, 3), float(HEAD_ENV_E_CEILING["x"][1])), "y": HEAD_ENV_E_CEILING["y"],
              "z": (FILM_Z - max(RAIL_PROJECTIONS), HEAD_TOP_Z)}   # x max 212.5 (contract draft6): the sprung leading rail (IB-40)
# Finished head (mechanical/head, IB-40): leading rail bar front face x 212.2 unloaded / 195.2 fully stroked, bar z 8..22
# (insert to the film projection below), |y| <= 175 (mechanical/head/hp.py RAIL_GAP, BAR_Z0/1, BAR_HY; head_report.md).
HEAD_LEAD_RAIL = {"x": (HEAD_FRAME_FRONT_X, 212.2), "z": (FILM_Z - min(RAIL_PROJECTIONS), 22.0), "half_y": 175.0}
# Head mass and CG incl. pigtails (calculated by the head engineer: mechanical/head/out/head_report.md section 3)
HEAD_JACKET = {"top_z": 48.0, "front_x": 191.2}   # standard 3 mm insulating jacket below 0 C (cap top, front band face), head_report.md section 9
HEAD_MASS = {"prototype": (1.862, 118.4, 34.5), "production": (2.082, 120.0, 32.9)}   # kg, x, z (base_link mm); refreshed below from the head build
try:   # read the finished head's calculated mass/CG at build time (mechanical/head/out/checks.json data.mass_*)
    _hc = json.loads((REPO / "mechanical" / "head" / "out" / "checks.json").read_text(encoding="utf-8"))["data"]
    for _b in ("prototype", "production"):
        _m = _hc.get(f"mass_{_b}")
        if _m:
            HEAD_MASS[_b] = (round(_m["mass_g"] / 1000.0, 4), round(_m["cg_mm"][0], 1), round(_m["cg_mm"][2], 1))
except (OSError, KeyError, ValueError):
    pass
HEAD_FRAME_X = (round(143.0 + HEAD_DX, 3), round(261.0 + HEAD_DX, 3))  # Rev D frame extents, shifted
HEAD_FRAME_HALF_Y = 172.5
HEAD_COVER_X = (round(143.4 + HEAD_DX, 3), round(260.6 + HEAD_DX, 3))
HEAD_COVER_HALF_Y = 172.1
HEAD_SPREADER_X = (round(155.0 + HEAD_DX, 3), round(257.5 + HEAD_DX, 3))   # rear edge held back: SiPM pigtail chimney (9 mm deep) behind it
HEAD_SPREADER_HALF_Y = 168.5
HEAD_PIGTAIL_EXIT = {"J1": (round(144.5 + HEAD_DX, 3), 76.2, 39.0), "J2": (round(144.5 + HEAD_DX, 3), -SEG_PITCH, 39.0)}  # J1 at y 76.2: head-board CR-M03a accepted (IB-52), as in the head model  # strain-relief ports in the rear wall at the inactive seams, cables leave -x/+z

# --------------------------------------------------------------------------- head / body receiver interface (option C)
RECEIVER = {
    "type": "twin shoe: two rails on the head slide rearward (-x) into two channels under the chassis front beam",
    "shoe_y": SEG_PITCH,                    # shoe centre lines on the S0|S1 and S2|S3 lane seams (y = +-87.5)
    "shoe_width": 16.0, "shoe_z": (16.0, 30.0),            # head-side rail section (y width, z range)
    "shoe_x": (4.0, HEAD_FRAME_X[0]),                     # shoe tip .. head frame rear face (rail continues into the seam rib)
    "channel_x": (2.0, HEAD_MOUNT[0]), "channel_width": 24.0, "channel_z": (12.0, 33.0),   # body-side block outer envelope; runs to the x-stop plane (CR-01)
    "channel_clear": 0.5,                                  # running clearance each side before the lands
    "land_x": (8.0, 62.0),                                 # centres of the two bearing lands in each channel -> base e = 54 mm
    "x_stop": HEAD_MOUNT[0],                               # datum A: head shoulders seat on the channel front faces at x = 65.7
    "fixed_side": "left (+y) channel locates y; right channel floats +-0.3 mm in y (thermal growth over 175 mm)",
    "z_datum": 16.0,                                       # datum C: shoe undersides on the channel floor lands
    "latch_box": (88.0, 108.0, -12.0, 12.0, 46.0, 60.0),   # one captive over-centre draw latch under the nose tip, lever lifts forward
    "latch_keeper": (104.0, 0.0, HEAD_TOP_Z),              # keeper on the head cover, centre rear
    "front_beam": (2.0, 62.0, -119.5, 119.5),             # chassis plate front beam/horns (x0, x1, y0, y1); |y| 119.5 carries the front cliff ToF (CR-01)
    "chin_cut": (62.0, 50.0),                              # lower hull removed for x > 62 below z = 50 (nose overhangs the head by 36 mm)
    "contact_k_printed": 1500.0, "contact_k_aluminium": 6000.0,   # N/mm per bearing land -- STATED ASSUMPTION for all mount options
}
# Receiver thermal break (contract draft8 power.thermal_policy.head_receiver_thermal_break, DEC-045, IB-64).
# Each channel hangs under the plate on a ground G10 shim; no metal part bridges the shim (screws in G10 top-hat bushings,
# the location dowels split into two staggered sets so that each set engages metal on one side of the shim only).
# Datum C (z 16) and the land pins (centre z 14) are unchanged: the channel ears are lowered by the shim thickness and the
# two roof bridges at the land stations stand up into 1.5 mm pockets milled in the plate underside (1.5 mm air gap).
RECEIVER_BREAK = {
    "shim_material": "NEMA G-10 (FR4 class) glass-epoxy laminate, both faces surface ground",
    "shim_t": 4.0, "shim_t_tol": 0.02, "shim_flatness": 0.01,             # mm; the two shims of a set ground together
    "k_shim_w_mk": 0.30,             # through-thickness, handbook class value for G-10/FR4 (0.25..0.30) -- UNVERIFIED for the purchased sheet
    "e_shim_flatwise_mpa": 10000.0,  # compressive modulus normal to the laminate -- ASSUMED handbook class, UNVERIFIED
    "shim_creep_factor": 1.3,        # total / elastic strain after ~1e5 h at <= 25 % of flatwise strength, RT -- ASSUMED, UNVERIFIED
    "shim_dy": (12.5, 21.0),         # |dy| band of the shim strips about the channel centre line (ear footprint minus the spine)
    "ear_top_z": CHASSIS_PLATE_Z[0] - 4.0, "ear_t": 7.5,                  # ear top = plate underside - shim
    "bridge_x": ((2.0, 13.0), (56.0, HEAD_MOUNT[0])),                     # roof bridges over the slot at the two land stations
    "bridge_top_z": CHASSIS_PLATE_Z[0], "plate_pocket_depth": 1.5, "pocket_margin": 1.0,
    "screw": "M4 x 18 ISO 4762 A2-70", "screw_preload_n": 1500.0, "screw_torque_nm": 1.2,
    "disc_spring": "DIN 6796 4 A2 conical spring washer (d1 4.3, d2 9, h 1.3, s 1.0; flat load about 2 kN) -- UNVERIFIED",
    "washer": "ISO 7089 4 A2 (OD 9 x 0.8)",
    "bushing": {"flange_od": 10.0, "flange_t": 1.0, "sleeve_od": 6.0, "sleeve_len": 3.5, "id": 4.3, "material": "G-10 machined top-hat bushing (PEEK-GF30 alternative) -- UNVERIFIED stock item"},
    "pins_lower": ((28.5, -17.0), (43.5, -17.0)),   # 4 m6 x 8 pressed 5.5 into the ear, 2.5 into the shim; top 1.5 below the plate
    "pins_upper": ((21.0, -17.0), (36.0, -17.0)),   # 4 m6 x 8 pressed flush into the plate, through the shim; tip in a 6.5 x 1.5 ear relief
    "pin_relief": (6.5, 1.5),
    "target_w_per_k": 0.10,          # per channel, body side (task statement / DEC-045)
}

# --------------------------------------------------------------------------- boards (envelopes confirmed/corrected here)
# Board frame convention (both big boards): origin at the rear-left corner seen from above with robot-forward up,
# +u toward robot right (-y_base), +v forward (+x_base), component (top) side +z.  base = origin + (v, -u, 0).
def board_to_base(origin, u, v):
    return (origin[0] + v, origin[1] - u, origin[2])


HEAD_ACQ = {
    "outline": tuple(BOARDS_C["RR-HEAD-ACQ"]["outline_mm"]),          # (326, 96) confirmed
    "origin": (round(ROW_X - 48.0, 3), 163.0, 34.5),                             # rear-left corner, PCB underside
    "thickness": 1.6,
    "max_top": float(BOARDS_C["RR-HEAD-ACQ"]["max_height_top_mm"]),    # 6.0 confirmed
    "max_bottom": float(BOARDS_C["RR-HEAD-ACQ"]["max_height_bottom_mm"]),  # 2.0 confirmed
    # as built: electronics/head_acq/layout.py HOLES (H2801..H2808); H1 moved to (75.5, 30.0) by CR-M02 (IB-52)
    "holes_uv": [(75.5, 30.0), (163.0, 4.5), (250.5, 4.5), (75.5, 91.5), (163.0, 91.5), (250.5, 91.5), (5.0, 48.0), (321.0, 48.0)],
    "hole_d": 2.7, "hole_keepout_d": 6.0, "screw": "M2.5",
}
CHS_MAIN = {
    "outline": tuple(BOARDS_C["RR-CHS-MAIN"]["outline_mm"]),          # (160, 100) confirmed (needs BODY_SCALE >= 1.30)
    "origin": (-67.0, 80.0, 83.0),                                     # rear-left corner, PCB underside
    "thickness": 1.6,
    "max_top": float(BOARDS_C["RR-CHS-MAIN"]["max_height_top_mm"]),    # 18
    "max_bottom": float(BOARDS_C["RR-CHS-MAIN"]["max_height_bottom_mm"]),  # 3
    "holes_uv": [(4.0, 4.0), (80.0, 4.0), (156.0, 4.0), (4.0, 96.0), (80.0, 96.0), (156.0, 96.0)],
    "hole_d": 3.2, "hole_keepout_d": 7.0, "screw": "M3",
}
TOF_BOARD = {"outline": tuple(BOARDS_C["RR-TOF"]["outline_mm"]), "thickness": 1.6, "depth_behind_window": 6.0}
PANEL_BOARD = {"outline": tuple(BOARDS_C["RR-PANEL"]["outline_mm"]), "thickness": 1.6, "center": (-80.0, 97.0), "long_axis": "x", "max_top": 8.0, "below_skin": 21.0}
ELECTRONICS_BRIDGE_Z = (78.0, 80.0)    # 2 mm tray over the motors carrying RR-CHS-MAIN (screen + H-bridge heat path)

# --------------------------------------------------------------------------- body packaging (layout decisions)
BATTERY_BAY = {            # 8/9 Ah SLA-format pack lying on its side on the centreline, cassette slides out rearward (-x)
    # Baseline pack PSL-SC-12120 (DEC-040) lying on its 151 x 101 side: 99 mm tall. The 9 Ah PSL-SC-1290 fits the same
    # cassette lying on its side (99 wide, 65 tall) with a 34 mm spacer -- kept as an alternative at no cost.
    "cassette_x": (-230.0, -73.5), "cassette_half_y": 54.5, "cassette_z": (40.0, 144.0),
    "pack_x": (-227.5, -76.5), "pack_half_y": 50.5, "pack_z": (42.5, 141.5),
    "coupler_x": (-73.5, -16.0), "coupler_half_y": 19.0, "coupler_z": (44.0, 62.0),
    "tunnel_roof_z": 150.0, "removal_direction": (-1.0, 0.0, 0.0), "removal_travel": 165.0,
    "hatch_x": (BODY_TAIL_X - 1.0, -230.0),   # the tail cap behind the cassette is the hatch door
    "hatch_half_y": 58.0, "hatch_z": (38.5, 148.0),
    # local growth for the 12 Ah pack: a dorsal hump over the tunnel (outer box), 7 mm above the Rev E crown
    "hump_x": (-233.0, -70.5), "hump_half_y": 60.5, "hump_z": (100.0, 150.0), "hump_wall": 3.0,
}
SADDLE = {                 # carry-grip saddle over RR-CHS-MAIN = removable service cover (replaces the Rev D hand well)
    "x": (-69.0, 47.0), "half_y": 82.0, "floor_z": (105.0, 108.0),
}
GRIP = {                   # transverse bridge grip above the centre of gravity (lead decision D-2; bar moved aft by CR-04 / IB-10)
    "center_x": -30.0, "bar_x": 25.0, "bar_z": 22.0, "glove_clearance_below": 45.0, "half_span_y": 84.0,
    "cheek_y": (84.0, 98.0),
    # hand zone (CR-04): 45 mm in front of the bar and below it, 45 mm behind it at bar height and above (palm, above the
    # hump top z 150), but only 25 mm behind it below the bar (fingertips)
    "hand_behind_below": 25.0,
}
GRIP["bar_bottom_z"] = SADDLE["floor_z"][1] + GRIP["glove_clearance_below"]
GRIP["bar_top_z"] = GRIP["bar_bottom_z"] + GRIP["bar_z"]
LIDAR_POSE = {"xy": (-150.0, 0.0), "base_z": 150.0}          # behind the grip, on the battery hump
CM5_POSE = {"x": (-154.0, -69.0), "y": (59.0, 115.0), "pcb_z": 55.0}   # left side bay
DRIVE_POD = {"inner_r": 21.0, "outer_r": 23.5, "end_y": 119.5}   # motor pod on each flank behind the tyre (local growth, hidden by the wheel)
ELECTRONICS_BRIDGE_X = (-69.0, 35.0)
GLOVE_CLEARANCE_CONNECTOR = 45.0     # required free radius around J1/J2 coupling nuts
GLOVE_CLEARANCE_GRIP = 45.0

# --------------------------------------------------------------------------- materials (handbook values; cold caveats in calc/)
MATERIALS = {   # E in MPa at +23 C (typical supplier data sheet values, UNVERIFIED for the purchased spool), density g/cm3
    "PETG-CF": {"E": 3800.0, "rho": 1.25, "note": "Bambu PETG-CF TDS class; printed XY. Cold: modulus rises ~10-20 %, impact strength falls"},
    "PA-CF": {"E": 5500.0, "rho": 1.22, "note": "PAHT-CF class, DRY value; wet (conditioned) modulus roughly halves -> use dry-cold as the upper and wet-warm as the lower bound"},
    "ASA": {"E": 2200.0, "rho": 1.07, "note": "unfilled; lowest stiffness candidate, best UV/chemical wipe-down"},
    "AL6061": {"E": 68900.0, "rho": 2.70, "note": "6061-T6 plate/billet"},
    "PA12-MJF": {"E": 1700.0, "rho": 1.01, "note": "HP 3D HR PA12 class"},
    "PMMA": {"E": 3000.0, "rho": 1.19, "note": "light guides"},
    "FR4": {"E": 22000.0, "rho": 1.85, "note": "PCB"},
}


# --------------------------------------------------------------------------- skin helpers, sensors, controls, connectors
def skin_point(theta_deg, z, surface="outer"):
    """Point on the Rev E skin at ring angle theta (0 = nose, 180 = tail, +90 = left) and height z."""
    for part in ("upper", "lower"):
        row = _interp_row(BODY_ROWS[f"{part}_{surface}"], z)
        if row is not None:
            return ring_point(row, math.radians(theta_deg))
    raise ValueError(f"z = {z} outside the body")


def roof_normal(x, y, h=2.0):
    """Unit outward normal of the upper outer skin above (x, y)."""
    zx = (roof_z(x + h, y) - roof_z(x - h, y)) / (2 * h)
    zy = (roof_z(x, y + h) - roof_z(x, y - h)) / (2 * h)
    n = math.sqrt(zx * zx + zy * zy + 1)
    return (-zx / n, -zy / n, 1 / n)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _dir(yaw_deg, depression_deg):
    """Boresight from yaw about +z (0 = forward, +90 = left) and depression below horizontal."""
    yw, dp = math.radians(yaw_deg), math.radians(depression_deg)
    return (math.cos(dp) * math.cos(yw), math.cos(dp) * math.sin(yw), -math.sin(dp))


TOF_FOV_FULL_DEG = 18.0       # VL53L4ED field of view (UNVERIFIED, ST datasheet value recalled)
TOF_MAX_RANGE = 1300.0        # mm (UNVERIFIED, dark-ambient typical)
LOOKAHEAD_FWD_DEPRESSION = 18.0
_cliff_f = skin_point(41.0, 41.0)
_cliff_r = skin_point(150.0, 41.0)
_la_r = skin_point(157.0, 100.0)
_px_c = skin_point(180.0, 118.0)
_px_s = skin_point(152.0, 80.0)
TOF_SENSORS = {   # id: position of the sensor aperture (mm, base_link), unit boresight, purpose
    "tof_cliff_fl": {"xyz": (46.0, 109.5, 31.0), "dir": (0.0, 0.0, -1.0), "purpose": "downward cliff on the outboard end of the chassis front beam: 46 mm ahead of the axle, 13 mm inboard of the left tyre"},
    "tof_cliff_fr": {"xyz": (46.0, -109.5, 31.0), "dir": (0.0, 0.0, -1.0), "purpose": "downward cliff on the outboard end of the chassis front beam, right"},
    "tof_cliff_rl": {"xyz": (_cliff_r[0], _cliff_r[1], 41.0), "dir": (0.0, 0.0, -1.0), "purpose": "downward cliff, rear left of the caster (reverse and pivot)"},
    "tof_cliff_rr": {"xyz": (_cliff_r[0], -_cliff_r[1], 41.0), "dir": (0.0, 0.0, -1.0), "purpose": "downward cliff, rear right of the caster (reverse and pivot)"},
    # look-ahead set (IB-34, lead decision): two forward-looking + two rearward-looking oblique sensors.  Renamed for
    # clarity: tof_look_fl -> tof_look_fwd_left, tof_look_fr -> tof_look_fwd_right, tof_look_rl -> tof_look_rev_left,
    # tof_look_rr -> tof_look_rev_right (positions unchanged; the forward pair stays at x 1.5 after the grip moved aft, CR-04)
    "tof_look_fwd_left": {"xyz": (1.5, 91.0, 162.0), "dir": _dir(6.0, LOOKAHEAD_FWD_DEPRESSION), "purpose": "oblique look-ahead (forward), left: floor/drop-off ahead of the leading rail; on the grip cheek fairing nose"},
    "tof_look_fwd_right": {"xyz": (1.5, -91.0, 162.0), "dir": _dir(-6.0, LOOKAHEAD_FWD_DEPRESSION), "purpose": "oblique look-ahead (forward), right"},
    "tof_look_rev_left": {"xyz": (_la_r[0], _la_r[1], 100.0), "dir": _dir(170.0, 22.0), "purpose": "oblique look-ahead (rearward), left: floor/drop-off behind the tail before reverse"},
    "tof_look_rev_right": {"xyz": (_la_r[0], -_la_r[1], 100.0), "dir": _dir(-170.0, 22.0), "purpose": "oblique look-ahead (rearward), right"},
    "tof_prox_rc": {"xyz": (-236.0, 0.0, 158.0), "dir": _dir(180.0, 0.0), "purpose": "rear proximity, centre (in the brow above the battery hatch)"},
    "tof_prox_rl": {"xyz": (_px_s[0], _px_s[1], 80.0), "dir": _dir(145.0, 0.0), "purpose": "rear proximity, left quarter"},
    "tof_prox_rr": {"xyz": (_px_s[0], -_px_s[1], 80.0), "dir": _dir(-145.0, 0.0), "purpose": "rear proximity, right quarter"},
}


def _deck(x, y):
    return (x, y, roof_z(x, y))


PANEL_CONTROLS = {   # centre of the control on the outer skin, actuation axis = local skin normal
    "estop": {"xyz": _deck(-120.0, -98.0), "desc": "latching E-stop, 22 mm, 2 NC positive opening (ESTOP)"},
    "hands_on": {"xyz": _deck(-172.0, -97.0), "desc": "HANDS-ON maintained illuminated pushbutton (HANDS_ON)"},
    "mode_selector": {"xyz": _deck(-135.0, 98.0), "desc": "master OFF / SERVICE / RUN selector (MODE_RUN)"},
    "rearm_start": {"xyz": _deck(-172.0, 97.0), "desc": "REARM / Start, guarded momentary NO"},
    "pause_stop": {"xyz": _deck(-84.0, -122.0), "desc": "Pause / Stop momentary (moved 10 mm outboard from y -112, CR-08: its body, 50 mm deep UNVERIFIED + 3 mm, now clears the IB-12 rear-right connector space; an aft move would have closed the gap to the E-stop mushroom)"},
    "annunciator": {"xyz": _deck(*PANEL_BOARD["center"]), "desc": "RR-PANEL: five status light pipes + buzzer port, left deck beside the grip, long axis along x"},
}
for _c in PANEL_CONTROLS.values():
    _c["normal"] = roof_normal(_c["xyz"][0], _c["xyz"][1])
_ci = skin_point(-128.0, 88.0)
CHARGE_INLET = {"xyz": _ci, "normal": _unit((_ci[0] - (-150.0), _ci[1], 0.0)),
                "desc": "charge inlet (M12 L-coded) under a hinged cover with cover switch, right rear quarter"}
J_RECEPTACLES = {    # panel receptacles on the front shoulders; mating axis = local skin normal
    "J1": {"xyz": _deck(72.0, 32.0), "family": C["connectors"]["J1"]["family"], "side": "left"},
    "J2": {"xyz": _deck(72.0, -32.0), "family": C["connectors"]["J2"]["family"], "side": "right"},
}
for _c in J_RECEPTACLES.values():
    _c["normal"] = roof_normal(_c["xyz"][0], _c["xyz"][1])
IMU_POSE = {"xyz": (0.0, 0.0, CHS_MAIN["origin"][2] + CHS_MAIN["thickness"] + 0.5), "rpy": (0.0, 0.0, 0.0),
            "note": "reserved BMI088 footprint on RR-CHS-MAIN at board (u, v) = (80, 67): directly above base_link"}
LIDAR_SCAN_PLANE_ABOVE_BASE = 60.0   # UNVERIFIED (no Richbeam drawing obtained): confirm before fixing lidar_link z
_bs = skin_point(143.0, 66.0)
BODY_BUMPER_SWITCHES = {"bumper_sw_l": (_bs[0], _bs[1], 66.0), "bumper_sw_r": (_bs[0], -_bs[1], 66.0)}
# as designed in mechanical/head (head_report.md "rail switch positions", IB-40); D2HW-C201M, plunger axes in the head model
HEAD_RAIL_SWITCHES = {"rail_sw_front": (182.6, 87.5, 37.3), "rail_sw_left": (73.8, 156.75, 20.75), "rail_sw_right": (73.8, -156.75, 20.75)}
HEAD_LID_SWITCH = (183.0, -SEG_PITCH)   # head lid interlock switch (x, y), mechanical/head/hp.py LID_SW
HEAD_DOCK_SWITCH = (-3.0, SEG_PITCH, 23.0)   # body-side D2HW behind the left receiver channel, pressed by the fully seated shoe tip


def summary():
    return {
        "contract_version": CONTRACT_VERSION,
        "body_scale_xyz": BODY_SCALE_XYZ, "body_pivot": BODY_PIVOT,
        "body_x": (round(BODY_TAIL_X, 1), round(BODY_NOSE_X, 1)),
        "body_crown_z": round(BODY_CROWN_Z, 1), "body_split_z": round(BODY_SPLIT_Z, 1),
        "track": TRACK, "caster_swivel": CASTER_SWIVEL, "head_top_z": HEAD_TOP_Z,
        "grip_bar_z": (GRIP["bar_bottom_z"], GRIP["bar_top_z"]),
        "tof": {k: tuple(round(c, 1) for c in v["xyz"]) for k, v in TOF_SENSORS.items()},
        "controls": {k: tuple(round(c, 1) for c in v["xyz"]) for k, v in PANEL_CONTROLS.items()},
        "J": {k: (tuple(round(c, 1) for c in v["xyz"]), tuple(round(c, 3) for c in v["normal"])) for k, v in J_RECEPTACLES.items()},
        "charge_inlet": tuple(round(c, 1) for c in CHARGE_INLET["xyz"]),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=1))
