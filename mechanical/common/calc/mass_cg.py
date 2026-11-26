"""Mass budget, centre of gravity, wheel/caster reactions, tip margins, traction and drive-torque margin."""
from __future__ import annotations

import math

from .. import params as P
from ..purchased import library as L
from . import f, inputs_table, table

G = 9.81
SLOPE_DEG = 5.0
MU = {"dry plywood / aluminium (assumed)": 0.6, "frosted or wet (assumed)": 0.3}
C_RR = 0.03


def shell_area(rows):
    """Lateral area of a lofted skin from its section table (perimeter x slant height), mm2."""
    def perim(row, n=180):
        pts = [P.ring_point(row, 2 * math.pi * i / n) for i in range(n)]
        return sum(math.dist(pts[i][:2], pts[(i + 1) % n][:2]) for i in range(n))
    a = 0.0
    for r0, r1 in zip(rows, rows[1:]):
        p0, p1 = perim(r0), perim(r1)
        slant = math.hypot(r1[0] - r0[0], (p1 - p0) / (2 * math.pi))
        a += (p0 + p1) / 2 * slant
    return a


def plan_area(row, n=360):
    pts = [P.ring_point(row, 2 * math.pi * i / n) for i in range(n)]
    return abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2


A_UP = shell_area(P.BODY_ROWS["upper_outer"]) + plan_area(P.BODY_ROWS["upper_outer"][-1])
A_LO = shell_area(P.BODY_ROWS["lower_outer"])
A_PLATE = plan_area(P.BODY_ROWS["lower_inner"][0])
X_BODY = (P.BODY_TAIL_X + P.BODY_NOSE_X) / 2 - 0.185 * 0.35 * (P.BODY_NOSE_X - P.BODY_TAIL_X) / 2   # egg form is fuller aft
B = P.BATTERY_BAY
X_PACK = sum(B["pack_x"]) / 2


MOUNT_HW = {   # body-side mount hardware per trade-study option: (description, mass kg, x mm, z mm)
    "A": ("neck shroud, keyed tongue, bearing lands, dock latch", 0.30, 118.0, 38.0),
    "B": ("front beam, 2 receiver channels, draw latch (arms are on the head)", 0.20, 35.0, 28.0),
    "C": ("front beam, 2 receiver channels, draw latch, dock switch", 0.20, 35.0, 28.0),
}
MOUNT_DX = {"A": 0.0, "B": 0.0, "C": P.HEAD_DX}       # shift of the head relative to the Rev D position
MOUNT_HEAD_EXTRA = {"A": 0.0, "B": 0.14, "C": 0.05}   # head-side arms / shoes beyond the Rev D socket (kg)


def base_items(build, mount="C"):
    """(name, mass kg, x, z, basis). build = 'prototype' (printed, X1C) or 'production' (CNC Al + MJF PA12)."""
    proto = build == "prototype"
    rho_shell, t_shell, kf = (P.MATERIALS["PETG-CF"]["rho"], 3.0, 1.25) if proto else (P.MATERIALS["PA12-MJF"]["rho"], 2.5, 1.20)
    m_up = A_UP * t_shell * rho_shell * kf / 1e6
    m_lo = A_LO * t_shell * rho_shell * kf / 1e6
    m_plate = (A_PLATE * 6.0 * P.MATERIALS["PA-CF"]["rho"] * 0.8 / 1e6 + 0.16) if proto else A_PLATE * 4.0 * 2.70 * 0.65 / 1e6
    cx = P.CASTER_SWIVEL[0]
    items = [
        ("upper fairing incl. ribs/bosses", m_up, X_BODY, 105, f"calc: {A_UP / 1e2:.0f} cm2 x {t_shell} mm x {rho_shell} g/cm3 x {kf}"),
        ("lower hull + tail-cap hatch + drive pods", m_lo + 0.06, X_BODY, 48, f"calc: {A_LO / 1e2:.0f} cm2 x {t_shell} mm x {rho_shell} g/cm3 x {kf} + 0.06"),
        ("battery hump + rear sensor brow (12 Ah growth)", 0.08, sum(B["hump_x"]) / 2, 130, "estimate"),
        ("chassis plate" + (" (6 mm printed PA-CF + 2 Al rails)" if proto else " (4 mm 6061, 35 % lightened)"), m_plate, X_BODY + 8, 35, f"calc from plan area {A_PLATE / 1e2:.0f} cm2"),
        ("electronics bridge + posts (2 mm Al)", 0.115, -17, 79, "calc: 104 x 164 x 2 mm Al + posts"),
        ("grip bar, cheeks, legs, yokes, saddle cover", 0.36 if proto else 0.42, P.GRIP["center_x"], 120, "estimate (printed with Al core / machined Al)"),
        ("battery tunnel, cassette, guides, latch", 0.30, X_PACK, 85, "estimate"),
        ("motor mounts x2", 0.10, 0, 59, "estimate"),
        (MOUNT_HW[mount][0], MOUNT_HW[mount][1], MOUNT_HW[mount][2], MOUNT_HW[mount][3], "estimate"),
        ("gearmotors x2", 2 * L.mass("motor"), 0, P.MOTOR_AXIS_Z, "Pololu #2828, VERIFIED 0.210 kg each"),
        ("wheels + hubs x2", 2 * L.mass("wheel"), 0, P.AXLE_Z, "UNVERIFIED estimate 0.15 kg each"),
        ("caster + bracket", L.mass("caster") + 0.02, cx, 20, "TENTE datasheet, VERIFIED 0.03 kg"),
        ("battery coupler pair + pack leads", L.mass("battery_coupler") + 0.05, -40, 53, "UNVERIFIED estimate"),
        ("RR-CHS-MAIN populated", 0.22, -17, 90, "estimate: 160 x 100 FR4 + relays, inductors, connectors"),
        ("CM5 + carrier + heat sink", L.mass("cm5") + L.mass("cm5_carrier") + 0.04, sum(P.CM5_POSE["x"]) / 2, 62, "UNVERIFIED estimate"),
        ("LiDAR LakiBeam 1L", L.mass("lidar"), P.LIDAR_POSE["xy"][0], P.LIDAR_POSE["base_z"] + 40, "vendor listing, VERIFIED 0.16 kg"),
        ("E-stop, selector, 3 pushbuttons", L.mass("estop") + L.mass("mode_selector") + 3 * L.mass("pushbutton_22"), -135, 110, "UNVERIFIED estimate"),
        ("RR-PANEL, 11 RR-TOF, 4 switches", 0.012 + 11 * 0.002 + 4 * 0.004, -120, 95, "estimate"),
        ("J1/J2 receptacles, charge inlet + cover", 0.035 + 0.04, 0, 105, "UNVERIFIED estimate"),
        ("bus clamp resistor, chassis heater, NTCs, cut-out", 0.08, -20, 42, "estimate"),
        ("harness (power, sensor, Ethernet, USB)", 0.45, -60, 85, "estimate: ~9 m of cold-rated wire and connectors"),
        ("bay insulation liner (5 mm closed-cell foam) + gaskets", 0.15, X_BODY, 80, "estimate: 0.25 m2 x 5 mm x 60 kg/m3 + seals"),
        ("fasteners, inserts, standoffs", 0.25, -60, 70, "estimate"),
    ]
    return items


def head_items(build, mount="C"):
    proto = build == "prototype"
    dx = MOUNT_DX[mount]
    items = [
        ("8 light guides + scintillators + films (OEM)", 0.41, 204, 19, "calc: 8 x 100 x 80 x 5 mm PMMA 1.19 + 0.03 (supplier drawing pending)"),
        ("barrier / absorber allowance x4", 0.10, 204, 19, "estimate (material undecided: 76 g plastic .. 173 g aluminium)"),
        ("frame + inter-lane ribs" + (" (printed PETG-CF/PA-CF, split at y=0)" if proto else " (machined 6061)"), 0.22 if proto else 0.43, 200, 20, "calc: ~170 cm3 printed / ~160 cm3 Al"),
        ("spreader plate 2 mm Al + standoffs", 0.19, 206, 31, "calc: 102.5 x 337 x 2 mm x 2.70"),
        ("retention pads + heater film + foam liner", 0.06, 204, 30, "estimate"),
        ("RR-HEAD-ACQ populated", 0.145, 204, 36, "calc: 326 x 96 x 1.6 FR4 + 50 g parts"),
        ("cover + seal", 0.12 if proto else 0.11, 202, 42, "calc: 2 mm printed / 1.5 mm Al"),
        ("contact rails, stems, 3 switches", 0.07, 215, 14, "estimate"),
        ("receiver hardware on the head (socket/pin, arms or shoes, keeper)", 0.08 + MOUNT_HEAD_EXTRA[mount], {"A": 146, "B": 105, "C": 110}[mount], 28, "estimate"),
        ("stiffening rods x2 (prototype only)", 0.03 if proto else 0.0, 204, 26, "8 mm CF tube"),
        ("fasteners, inserts", 0.06, 204, 30, "estimate"),
        ("J1 + J2 pigtails with plugs (head-borne half)", 0.13, 135, 60, "estimate: 2 x 0.3 m cable + M16/M12 plugs"),
    ]
    return [(n, m, x + dx, z, s) for n, m, x, z, s in items]


def roll_up(items):
    m = sum(i[1] for i in items)
    return m, sum(i[1] * i[2] for i in items) / m, sum(i[1] * i[3] for i in items) / m


PACKS = {"12 Ah PSL-SC-12120 (1.65 kg, baseline)": 1.65, "9 Ah PSL-SC-1290 (1.00 kg, alternative)": 1.00}


def cases(ballast=0.0, mount="C"):
    base_p, base_q = base_items("prototype", mount), base_items("production", mount)
    hp, hq = roll_up(head_items("prototype", mount)), roll_up(head_items("production", mount))
    heads = {"none (transport / LAB)": (0.0, 0.0, 0.0), "prototype printed head": hp, "production Al head": hq,
             "heaviest / dummy head (production + 15 %)": (hq[0] * 1.15, hq[1], hq[2])}
    out = []
    Lc = -(P.CASTER_SWIVEL[0] - L.env("caster")["offset"])
    for bname, base in (("prototype", base_p), ("production", base_q)):
        mb, xb, zb = roll_up(base)
        for pname, mp in PACKS.items():
            for hname, (mh, xh, zh) in heads.items():
                parts = [(mb, xb, zb), (mp, X_PACK, sum(B["pack_z"]) / 2), (mh, xh, zh), (ballast, P.BODY_TAIL_X + 22, 60.0)]
                m = sum(p[0] for p in parts)
                x = sum(p[0] * p[1] for p in parts) / m
                z = sum(p[0] * p[2] for p in parts) / m
                n_c = m * G * (-x) / Lc
                shift = z * (P.A_DECEL / G + math.tan(math.radians(SLOPE_DEG)))
                out.append({"build": bname, "pack": pname, "head": hname, "m": m, "x": x, "z": z, "L": Lc,
                            "N_caster": n_c, "N_wheel_each": (m * G - n_c) / 2,
                            "fwd_tip_margin_mm": -(x + shift), "N_caster_brake_slope": m * G * (-(x + shift)) / Lc,
                            "rear_tip_margin_mm": Lc + x - z * (P.A_MAX / G + math.tan(math.radians(SLOPE_DEG))),
                            "lat_tip_margin_mm": P.TRACK / 2 - z * (P.V_MAX_FWD * P.YAW_MAX / G + math.tan(math.radians(SLOPE_DEG)))})
    return out


def ballast_needed(target_fraction=0.08):
    """Tail ballast so that the worst operating case keeps >= target fraction of weight on the caster under braking + slope."""
    for b in [i * 0.05 for i in range(0, 61)]:
        worst = min(c["N_caster_brake_slope"] / (c["m"] * G) for c in cases(b) if not c["head"].startswith("none"))
        if worst >= target_fraction:
            return b, worst
    return None, None


def run():
    md, key = [], {}
    md.append("## 1. Mass budget, centre of gravity, reactions and tip margins\n")
    md.append(inputs_table([
        ("Mass goal", P.MASS_GOAL_KG, "kg", "RQ-002"), ("Track", P.TRACK, "mm", "params.TRACK (CCR-01)"),
        ("Caster swivel x / contact x (forward travel)", f"{P.CASTER_SWIVEL[0]} / {P.CASTER_SWIVEL[0] - L.env('caster')['offset']}", "mm", "params + TENTE datasheet offset 9 mm"),
        ("Controlled deceleration / max acceleration", f"{P.A_DECEL} / {P.A_MAX}", "m/s2", "contract motion"),
        ("Slope", SLOPE_DEG, "deg", "task statement"), ("Lateral acceleration v*w", f(P.V_MAX_FWD * P.YAW_MAX, 3), "m/s2", "contract motion"),
        ("Upper / lower skin area", f"{A_UP / 1e2:.0f} / {A_LO / 1e2:.0f}", "cm2", "calculated from the Rev E section tables"),
        ("Pack CG x", f(X_PACK), "mm", "params.BATTERY_BAY"), ("Optical row x", P.ROW_X, "mm", "params (mount option C, CCR-11)"),
    ]))
    for build in ("prototype", "production"):
        b, h = base_items(build), head_items(build)
        mb, xb, zb = roll_up(b)
        mh, xh, zh = roll_up(h)
        md.append(f"\n### {build.capitalize()} build -- item masses\n")
        md.append(table(["Item", "Mass (kg)", "x (mm)", "z (mm)", "Basis"], [(n, f(m, 3), f(x, 0), f(z, 0), s) for n, m, x, z, s in b]
                        + [("**Base without pack**", f"**{mb:.2f}**", f(xb), f(zb), "")]
                        + [(n, f(m, 3), f(x, 0), f(z, 0), s) for n, m, x, z, s in h] + [("**Head**", f"**{mh:.2f}**", f(xh), f(zh), "")]))
        key[f"{build}_base_kg"], key[f"{build}_head_kg"] = mb, mh
    cs = cases()
    md.append("\n### Configurations (calculated; rigid body on a level floor unless stated)\n")
    md.append(table(["Build", "Pack", "Head", "Mass (kg)", "Margin to 12 kg", "CG x (mm)", "CG z (mm)", "Caster N", "Each wheel N", "Caster N under 0.4 m/s2 braking on 5 deg down-slope", "Forward tip margin (mm)", "Rearward (mm)", "Lateral (mm)"],
                    [(c["build"], c["pack"], c["head"], f(c["m"], 2), f(P.MASS_GOAL_KG - c["m"], 2), f(c["x"]), f(c["z"]), f(c["N_caster"]), f(c["N_wheel_each"]),
                      f(c["N_caster_brake_slope"]), f(c["fwd_tip_margin_mm"]), f(c["rear_tip_margin_mm"], 0), f(c["lat_tip_margin_mm"], 0)) for c in cs]))
    op = [c for c in cs if not c["head"].startswith("none")]
    worst = min(op, key=lambda c: c["fwd_tip_margin_mm"])
    heavy = max(cs, key=lambda c: c["m"])
    key.update(worst_fwd_tip_mm=worst["fwd_tip_margin_mm"], worst_case=f"{worst['build']}, {worst['pack']}, {worst['head']}", worst_static_caster_N=min(c["N_caster"] for c in op),
               heaviest_kg=heavy["m"], cg_range_mm=(min(c["x"] for c in op), max(c["x"] for c in op)), cases=cs)
    bal, frac = ballast_needed()
    key["ballast_kg"] = bal
    md.append(f"\n**Finding (calculated).** Forward tip margin = -(x_CG + z_CG (a/g + tan 5 deg)); the head lands on its rails when it reaches zero. "
              f"Worst operating case: {key['worst_case']} -> margin **{worst['fwd_tip_margin_mm']:.1f} mm**, static caster load {worst['N_caster']:.1f} N "
              f"({100 * worst['N_caster'] / (worst['m'] * G):.1f} % of weight). With the Rev D neck (row at x = 204) and the 9 Ah pack this margin was -6.9 mm; the 12 Ah baseline pack and the shortened head overhang (row at x = {P.ROW_X}) "
              f"move the centre of gravity rearward (head {key['production_head_kg']:.2f} kg).")
    if bal is None:
        md.append("No tail ballast up to 3 kg reaches the 8 % target: architecture change needed.")
    elif bal > 0:
        md.append(f"To keep >= 8 % of the weight on the caster under braking on the 5 deg down-slope in every operating configuration, add **{bal:.2f} kg tail ballast** at x = {P.BODY_TAIL_X + 22:.0f} mm "
                  f"(inside the tail-cap hatch) -> worst caster fraction {100 * frac:.1f} %. The 12 Ah pack provides most of this by itself.")
    else:
        md.append(f"No ballast is needed for the 8 % caster-load target (worst fraction {100 * frac:.1f} %).")
    md.append("Main assumptions: masses marked estimate/UNVERIFIED above (+-15 % on structure moves x_CG by about +-4 mm); rigid tyres; weigh all three contacts on the first build (VT-032).")
    # traction and torque
    md.append("\n## 2. Traction-limited push force and drive-torque margin\n")
    c = max(op, key=lambda c: c["m"])
    r = P.WHEEL_R / 1000
    t_cont, t_inst, t_stall = L.PARTS["motor"]["ratings"]["max_cont_torque_nm"], L.PARTS["motor"]["ratings"]["max_instant_torque_nm"], L.PARTS["motor"]["ratings"]["stall_torque_nm"]
    f_need = c["m"] * (G * math.sin(math.radians(SLOPE_DEG)) + P.A_MAX + C_RR * G)
    t_need = f_need / 2 * r
    rows = []
    for name, mu in MU.items():
        push = mu * 2 * c["N_wheel_each"]
        rows.append((name, mu, f(push), f(push / 2 * r, 2), f(2 * t_stall / r, 0), "traction" if push < 2 * t_stall / r else "motor"))
    md.append(inputs_table([("Heaviest operating mass", f(c["m"], 2), "kg", "table above"), ("Wheel radius", P.WHEEL_R, "mm", "contract"),
                            ("Motor continuous / instantaneous / stall torque", f"{t_cont} / {t_inst} / {t_stall}", "N m", "Pololu 37D datasheet p.1 (100 / 250 kg mm recommended limits; 49 kg cm extrapolated stall), VERIFIED"),
                            ("Rolling resistance coefficient", C_RR, "-", "assumed (small hard caster, seams)"), ("Friction coefficients", str(list(MU.values())), "-", "assumed, to be measured (VT-003)")]))
    md.append("\n" + table(["Surface", "mu", "Max push force (N)", "Wheel torque at slip (N m)", "Force at motor stall (N)", "Limited by"], rows))
    md.append(f"\nDrive torque needed to accelerate at {P.A_MAX} m/s2 up a {SLOPE_DEG:.0f} deg slope with C_rr = {C_RR}: {f_need:.1f} N total = **{t_need:.2f} N m per wheel**; "
              f"margin to the {t_cont} N m continuous recommendation **x{t_cont / t_need:.1f}**, to the instantaneous limit x{t_inst / t_need:.1f}. "
              f"No-load wheel speed 67 rpm = {67 / 60 * math.pi * P.WHEEL_D / 1000:.2f} m/s, so {P.V_MAX_FWD} m/s needs {100 * P.V_MAX_FWD / (67 / 60 * math.pi * P.WHEEL_D / 1000):.0f} % of no-load speed. "
              "Push force is traction-limited, not stall-limited, on both assumed surfaces; the wheel-slip torque on dry floor exceeds the continuous motor recommendation, so the firmware current limit must cap the torque.")
    key.update(push_dry_N=MU["dry plywood / aluminium (assumed)"] * 2 * c["N_wheel_each"], torque_need=t_need, torque_margin=t_cont / t_need)
    # carry
    gz = (P.GRIP["bar_bottom_z"] + P.GRIP["bar_top_z"]) / 2
    rows = []
    for cc in cs:
        if cc["build"] == "production" and cc["pack"].startswith("12"):
            rows.append((cc["head"], f(cc["m"], 2), f(cc["x"]), f(math.degrees(math.atan2(cc["x"] - P.GRIP["center_x"], gz - cc["z"])))))
    md.append("\n## 3. Carry balance at the grip\n")
    md.append(table(["Head", "Mass (kg)", "CG x (mm)", "Hang angle at the grip, + = nose down (deg)"], rows))
    md.append(f"\nGrip centre x = {P.GRIP['center_x']} mm, z = {gz:.0f} mm. A Rev D-style rear grip (x = -94 scaled to about -170) would hang the robot more than 45 deg nose-down.")
    return "\n".join(md), key
