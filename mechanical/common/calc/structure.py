"""Head cantilever deflection, receiver compliance, first natural frequencies and grip stress (closed-form, calculated)."""
from __future__ import annotations

import math

from .. import params as P
from . import f, inputs_table, table

G = 9.81
TIP_LOAD = 20.0                      # N, task statement
SOCKET_HALF_Y = 39.75                # Rev D key-socket collar half width (clamped root of each wing)
WING = P.HEAD_FRAME_HALF_Y - SOCKET_HALF_Y        # cantilever length of each wing
WALL_H = P.HEAD_FRAME_TOP_Z - 9.6    # frame wall height (Rev D frame bottom z = 9.6)
SPREADER_W = P.HEAD_SPREADER_X[1] - P.HEAD_SPREADER_X[0]
CELL_H = P.HEAD_STACK[-1][1] - P.HEAD_STACK[1][2]  # closed cell between spreader top and cover skin
RECEIVER = {   # STATED ASSUMPTIONS -- no test or FEA data exists. k in N m/rad, play in mm over the 24 mm land spacing
    "prototype (printed PA-CF receiver, steel pin)": {"k_pitch": 1500.0, "k_roll": 1200.0, "play_mm": 0.10},
    "production (aluminium receiver, preloaded pin)": {"k_pitch": 6000.0, "k_roll": 5000.0, "play_mm": 0.03},
}
LAND_BASE = 24.0
CASES = {   # frame material, wall thickness mm, head mass kg, receiver key, cold modulus factor
    "prototype PETG-CF": ("PETG-CF", 3.0, 1.62, "prototype (printed PA-CF receiver, steel pin)"),
    "prototype PA-CF (dry)": ("PA-CF", 3.0, 1.62, "prototype (printed PA-CF receiver, steel pin)"),
    "prototype PA-CF (conditioned, E x 0.5)": ("PA-CF", 3.0, 1.62, "prototype (printed PA-CF receiver, steel pin)"),
    "prototype ASA": ("ASA", 3.0, 1.62, "prototype (printed PA-CF receiver, steel pin)"),
    "production 6061": ("AL6061", 2.5, 2.05, "production (aluminium receiver, preloaded pin)"),
}


def section(material, t_wall, e_factor=1.0):
    """Composite bending stiffness EI (N mm2) of one wing about the x axis and torsional GJ (open / closed)."""
    e_w = P.MATERIALS[material]["E"] * e_factor
    e_s = P.MATERIALS["AL6061"]["E"]
    a_w, i_w, z_w = 2 * t_wall * WALL_H, 2 * t_wall * WALL_H ** 3 / 12, 9.6 + WALL_H / 2
    a_s, i_s, z_s = SPREADER_W * 2.0, SPREADER_W * 2.0 ** 3 / 12, 31.0
    zc = (e_w * a_w * z_w + e_s * a_s * z_s) / (e_w * a_w + e_s * a_s)
    ei = e_w * (i_w + a_w * (z_w - zc) ** 2) + e_s * (i_s + a_s * (z_s - zc) ** 2)
    g_w, g_s = e_w / 2.7, e_s / 2.66
    gj_open = g_w * 2 * WALL_H * t_wall ** 3 / 3 + g_s * SPREADER_W * 2.0 ** 3 / 3
    cell = SPREADER_W * CELL_H
    g_cover = g_w if material != "AL6061" else g_s
    t_cover = 2.0 if material != "AL6061" else 1.5
    flex = SPREADER_W / (g_s * 2.0) + SPREADER_W / (g_cover * t_cover) + 2 * CELL_H / (g_cover * 2.5)
    gj_closed = 4 * cell ** 2 / flex
    return ei, gj_open, gj_closed, zc


def deflections(name):
    mat, t, mass, rk = CASES[name]
    ef = 0.5 if "conditioned" in name else 1.0
    ei, gj_o, gj_c, zc = section(mat, t, ef)
    rc = RECEIVER[rk]
    w_wing = mass * G * (WING / (2 * P.HEAD_FRAME_HALF_Y)) / WING          # N/mm on one wing
    arm_row = P.ROW_X - P.HEAD_MOUNT[0]                                     # 65.5
    arm_front = P.ROW_X + P.ACTIVE_X / 2 - P.HEAD_MOUNT[0]                  # 115.5
    arm_rear = P.ROW_X - P.ACTIVE_X / 2 - P.HEAD_MOUNT[0]                   # 15.5
    y_c = P.SEG_Y[0] + P.ACTIVE_Y / 2                                       # 171.25
    out = {}
    # self weight
    pitch_sw = mass * G * (arm_row / 1000) / rc["k_pitch"]                  # rad, head CG ~ row centre
    bend_sw = w_wing * WING ** 4 / (8 * ei)
    out["self weight"] = {"row centre": pitch_sw * arm_row, "rear outer corner": pitch_sw * arm_rear + bend_sw, "front outer corner": pitch_sw * arm_front + bend_sw}
    # 20 N at the front outer corner (and at the row centre for the centre value)
    m_pitch = TIP_LOAD * arm_front / 1000
    m_roll = TIP_LOAD * y_c / 1000
    th_p, th_r = m_pitch / rc["k_pitch"], m_roll / rc["k_roll"]
    bend_tip = TIP_LOAD * (y_c - SOCKET_HALF_Y) ** 3 / (3 * ei)
    twist_o = TIP_LOAD * (P.ACTIVE_X / 2) * WING / gj_o
    twist_c = TIP_LOAD * (P.ACTIVE_X / 2) * WING / gj_c
    for tag, tw in (("20 N at front outer corner, cover NOT structural (open section)", twist_o), ("20 N at front outer corner, cover screwed as shear panel (closed cell)", twist_c)):
        out[tag] = {"row centre": th_p * arm_row,
                    "rear outer corner": th_p * arm_rear + th_r * y_c + bend_tip - tw * P.ACTIVE_X / 2,
                    "front outer corner": th_p * arm_front + th_r * y_c + bend_tip + tw * P.ACTIVE_X / 2}
    out["20 N at row centre"] = {"row centre": TIP_LOAD * (arm_row / 1000) / rc["k_pitch"] * arm_row, "rear outer corner": TIP_LOAD * (arm_row / 1000) / rc["k_pitch"] * arm_rear,
                                 "front outer corner": TIP_LOAD * (arm_row / 1000) / rc["k_pitch"] * arm_front}
    play = rc["play_mm"] / LAND_BASE
    out["receiver play (unloaded rattle, +-)"] = {"row centre": play * arm_row, "rear outer corner": play * arm_rear, "front outer corner": play * arm_front}
    # frequencies
    mu = mass * (WING / (2 * P.HEAD_FRAME_HALF_Y)) / (WING / 1000)          # kg/m
    f_wing = 1.875 ** 2 / (2 * math.pi) * math.sqrt((ei / 1e6) / (mu * (WING / 1000) ** 4))
    i_pitch = mass * ((arm_row / 1000) ** 2 + (118e-3) ** 2 / 12)
    i_roll = mass * (0.350 ** 2) / 12
    f_pitch = math.sqrt(rc["k_pitch"] / i_pitch) / (2 * math.pi)
    f_roll = math.sqrt(rc["k_roll"] / i_roll) / (2 * math.pi)
    return out, {"EI": ei / 1e6, "GJ_open": gj_o / 1e6, "GJ_closed": gj_c / 1e6, "f_wing": f_wing, "f_pitch": f_pitch, "f_roll": f_roll, "zc": zc}


def run():
    md, key = [], {}
    md.append("## 4. Head cantilever deflection and natural frequencies\n")
    md.append("Model: each wing is a cantilever of length {:.1f} mm clamped at the key-socket collar edge; the bending section is the two frame walls (front and rear, {:.1f} mm tall) plus the 2 mm aluminium spreader "
              "(transformed section); pitch and roll at the receiver are lumped springs (stated assumption); wing torsion uses the open section (cover not structural) or the closed spreader-cover cell.\n".format(WING, WALL_H))
    md.append(inputs_table([
        ("Tip load", TIP_LOAD, "N", "task statement"), ("Wing cantilever", f(WING), "mm", "Rev D frame half width 172.5 - socket collar 39.75"),
        ("Arms from head_mount to rear / centre / front of the active row", "15.5 / 65.5 / 115.5", "mm", "contract datums"),
        ("Outer window corner y", P.SEG_Y[0] + P.ACTIVE_Y / 2, "mm", "contract optics"),
        ("E PETG-CF / PA-CF dry / ASA / 6061", "3800 / 5500 / 2200 / 68900", "MPa", "typical data-sheet values at 23 C, UNVERIFIED for the purchased material; printed parts are anisotropic (Z about 50-60 % of XY)"),
        ("Cold caveat", "E rises ~10-25 % at -20 C; impact strength and strain to failure fall", "-", "general polymer behaviour, not measured -> deflections below are conservative for cold, strength is NOT"),
        ("PA-CF moisture caveat", "conditioned modulus about 0.5 x dry", "-", "typical PA6/PA12-CF data sheets -> both values tabulated"),
        ("Receiver pitch / roll stiffness, prototype", "1500 / 1200", "N m/rad", "ASSUMPTION (two lands 62 mm apart, 24 mm engagement, printed) -- measure on the first article"),
        ("Receiver pitch / roll stiffness, production", "6000 / 5000", "N m/rad", "ASSUMPTION"),
        ("Receiver play prototype / production", "0.10 / 0.03", "mm over 24 mm", "ASSUMPTION; preload should remove it"),
        ("Head mass used (prototype / production + 15 % = dummy head)", "1.62 / 2.05", "kg", "section 1"),
    ]))
    for name in CASES:
        d, s = deflections(name)
        md.append(f"\n### {name}\n")
        md.append(f"EI = {s['EI']:.0f} N m2, GJ open / closed = {s['GJ_open']:.1f} / {s['GJ_closed']:.0f} N m2, neutral axis z = {s['zc']:.1f} mm, receiver: {CASES[name][3]}.\n")
        md.append(table(["Load case", "Row centre (mm)", "Rear outer window corner (mm)", "Front outer window corner (mm)"],
                        [(k, f(v["row centre"], 2), f(v["rear outer corner"], 2), f(v["front outer corner"], 2)) for k, v in d.items()]))
        md.append(f"\nFirst modes (calculated): head pitch on the receiver {s['f_pitch']:.0f} Hz, head roll on the receiver {s['f_roll']:.0f} Hz, wing bending {s['f_wing']:.0f} Hz.")
        key[name] = {"self_front": d["self weight"]["front outer corner"], "tip_open": d["20 N at front outer corner, cover NOT structural (open section)"]["front outer corner"],
                     "tip_closed": d["20 N at front outer corner, cover screwed as shear panel (closed cell)"]["front outer corner"], "centre_20N": d["20 N at row centre"]["row centre"],
                     "f1": min(s["f_pitch"], s["f_roll"], s["f_wing"])}
    md.append("\n**Reading.** Positive values are downward at the named point. The wings themselves are stiff (short, deep); the receiver joint and, if the cover is not a shear panel, wing twist dominate the 20 N corner case. "
              "Design rules for the head engineers: (1) screw the cover to the frame at <= 40 mm pitch so the spreader-cover cell is closed; (2) the spreader must be one piece across y = 0 and bolted to both frame halves; "
              "(3) receiver stiffness >= 1500 N m/rad in pitch is the number to prove by test (20 N at the front corner then moves it < 1 mm).")
    # whole-vehicle bounce (tyres)
    k_tyre, m = 40e3, 9.0
    md.append(f"\nVehicle heave on the tyres: with an assumed 40 N/mm per tyre and 9 kg, f = {math.sqrt(2 * k_tyre / m) / (2 * math.pi):.0f} Hz (assumption; solid-tyre stiffness must be measured). All head modes are well above it and above the seam-crossing excitation.")
    # grip
    load = P.MASS_GOAL_KG * G * 3.0
    span, hand = 2 * P.GRIP["half_span_y"], 100.0
    m_b = load / 2 * (span / 2 - hand / 4)
    z_mod = P.GRIP["bar_x"] * P.GRIP["bar_z"] ** 2 / 6
    sig = m_b / z_mod
    cheek_a = (P.GRIP["cheek_y"][1] - P.GRIP["cheek_y"][0]) * P.GRIP["bar_x"]
    md.append("\n## 5. Carry-grip load path\n")
    md.append(inputs_table([("Design load", f"{load:.0f}", "N", "12 kg x g x 3 (handling factor, assumed)"), ("Bar section / span", f"{P.GRIP['bar_x']} x {P.GRIP['bar_z']} / {span}", "mm", "params.GRIP"),
                            ("Hand width", hand, "mm", "assumed gloved")]))
    md.append(f"\nBar bending stress {sig:.1f} MPa (solid section; a printed bar needs a 10 mm aluminium or CF tube core through both cheeks for creep and cold impact), "
              f"cheek tension {load / 2 / cheek_a:.2f} MPa, each cheek leg carries {load / 2:.0f} N into its yoke on the chassis plate (2 x M5 per yoke: {load / 4:.0f} N per screw at the design load). "
              "Proof test: 3 x weight for 60 s warm and at -20 C (VT-002).")
    key["grip_sigma_mpa"] = sig
    return "\n".join(md), key
