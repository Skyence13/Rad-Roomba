"""Head mount stiffness, cantilever deflection, first modes and grip stress (closed-form, calculated).

One mount model serves every option of the head-mount trade study so they compare on the same basis:
four bearing lands at (+-e/2, +-b) with one contact stiffness k_c per land (STATED ASSUMPTION), optional twin arms
between the receiver and the head (cantilever beams), and head wings cantilevered beyond the outermost support.
"""
from __future__ import annotations

import math

from .. import params as P
from . import f, inputs_table, table

G = 9.81
TIP_LOAD = 20.0                      # N, task statement
WALL_H = P.HEAD_FRAME_TOP_Z - 9.6    # frame wall height (Rev D frame bottom z = 9.6)
SPREADER_W = P.HEAD_SPREADER_X[1] - P.HEAD_SPREADER_X[0]
CELL_H = P.HEAD_STACK[-1][1] - P.HEAD_STACK[1][2]  # closed cell between spreader top and cover skin
RC = P.RECEIVER
ARM_ROW, ARM_FRONT, ARM_REAR = 65.5, 115.5, 15.5   # mount datum -> row centre / front / rear edge of the windows (head-internal, fixed)
Y_C = P.SEG_Y[0] + P.ACTIVE_Y / 2
E_AL, E_STEEL = P.MATERIALS["AL6061"]["E"], 200000.0

MOUNTS = {   # b: half spacing of the bearing lands (y); e: land base (x); c0: land midpoint -> mount datum; root_y: wing clamp;
             # arm: free length between receiver and head rear face, EI per arm (N mm2) for printed / aluminium builds
    "A": {"name": "A  Rev D central keyed neck", "b": 31.0, "e": 24.0, "c0": 12.0, "root_y": 39.75, "arm": None, "play": 0.10},
    "B": {"name": "B  twin arms at the lane seams, row stays at x = 204", "b": RC["shoe_y"], "e": RC["land_x"][1] - RC["land_x"][0],
          "c0": P.HEAD_MOUNT[0] - sum(RC["land_x"]) / 2, "root_y": RC["shoe_y"] + RC["shoe_width"] / 2,
          "arm": {"L": -P.HEAD_DX, "EI_printed": 5500.0 * 16 * 21 ** 3 / 12 + E_STEEL * math.pi * 10 ** 4 / 64, "EI_al": E_AL * 16 * 21 ** 3 / 12}, "play": 0.05},
    "C": {"name": "C  twin shoes at the lane seams, overhang shortened (implemented)", "b": RC["shoe_y"], "e": RC["land_x"][1] - RC["land_x"][0],
          "c0": P.HEAD_MOUNT[0] - sum(RC["land_x"]) / 2, "root_y": RC["shoe_y"] + RC["shoe_width"] / 2, "arm": None, "play": 0.05},
}
BUILDS = {   # frame material, wall mm, head mass kg, contact stiffness N/mm, E factor
    "prototype PETG-CF": ("PETG-CF", 3.0, 1.65, RC["contact_k_printed"], 1.0),
    "prototype PA-CF (dry)": ("PA-CF", 3.0, 1.65, RC["contact_k_printed"], 1.0),
    "prototype PA-CF (conditioned, E x 0.5)": ("PA-CF", 3.0, 1.65, RC["contact_k_printed"], 0.5),
    "prototype ASA": ("ASA", 3.0, 1.65, RC["contact_k_printed"], 1.0),
    "production 6061": ("AL6061", 2.5, 2.10, RC["contact_k_aluminium"], 1.0),
}


def section(material, t_wall, e_factor=1.0):
    """Composite bending stiffness EI (N mm2) of the head about the x axis and torsional GJ (open / closed)."""
    e_w = P.MATERIALS[material]["E"] * e_factor
    a_w, i_w, z_w = 2 * t_wall * WALL_H, 2 * t_wall * WALL_H ** 3 / 12, 9.6 + WALL_H / 2
    a_s, i_s, z_s = SPREADER_W * 2.0, SPREADER_W * 2.0 ** 3 / 12, 31.0
    zc = (e_w * a_w * z_w + E_AL * a_s * z_s) / (e_w * a_w + E_AL * a_s)
    ei = e_w * (i_w + a_w * (z_w - zc) ** 2) + E_AL * (i_s + a_s * (z_s - zc) ** 2)
    g_w, g_s = e_w / 2.7, E_AL / 2.66
    gj_open = g_w * 2 * WALL_H * t_wall ** 3 / 3 + g_s * SPREADER_W * 2.0 ** 3 / 3
    g_cover, t_cover = (g_w, 2.0) if material != "AL6061" else (g_s, 1.5)
    flex = SPREADER_W / (g_s * 2.0) + SPREADER_W / (g_cover * t_cover) + 2 * CELL_H / (g_cover * 2.5)
    return ei, gj_open, 4 * (SPREADER_W * CELL_H) ** 2 / flex, zc


def mount_stiffness(mount, k_c, aluminium):
    """Pitch and roll stiffness seen at the head mount datum (N mm/rad) incl. arms, and the arm data used."""
    m = MOUNTS[mount]
    k_pitch, k_roll = 4 * k_c * (m["e"] / 2) ** 2, 4 * k_c * m["b"] ** 2
    arm = None
    if m["arm"]:
        ei = m["arm"]["EI_al" if aluminium else "EI_printed"]
        arm = {"L": m["arm"]["L"], "EI": ei}
        k_pitch = 1 / (1 / k_pitch + arm["L"] / (2 * ei))
        k_roll = 1 / (1 / k_roll + arm["L"] ** 3 / (3 * ei * 2 * m["b"] ** 2))
    return k_pitch, k_roll, arm


def point_deflection(mount, k_c, aluminium, force, x_load, y_load, x_pt, y_pt):
    """Vertical deflection (mm, + down) at a head point from a force at another head point; x measured from the mount datum.
    Rigid head on the compliant mount (contact lands + arms)."""
    m = MOUNTS[mount]
    k_pitch0, k_roll0 = 4 * k_c * (m["e"] / 2) ** 2, 4 * k_c * m["b"] ** 2
    L_arm = m["arm"]["L"] if m["arm"] else 0.0
    lever_load, lever_pt = x_load + L_arm + m["c0"], x_pt + L_arm + m["c0"]
    d = force * lever_load / k_pitch0 * lever_pt + force * y_load / k_roll0 * y_pt + force / (4 * k_c)
    if m["arm"]:
        ei2 = 2 * m["arm"]["EI_al" if aluminium else "EI_printed"]
        mom = force * x_load
        d += force * L_arm ** 3 / (3 * ei2) + mom * L_arm ** 2 / (2 * ei2) + (force * L_arm ** 2 / (2 * ei2) + mom * L_arm / ei2) * x_pt
        d += (force * y_load / (2 * m["b"])) * L_arm ** 3 / (3 * ei2 / 2) / m["b"] * y_pt
    return d


def evaluate(mount, build):
    mat, t, mass, k_c, ef = BUILDS[build]
    al = mat == "AL6061"
    m = MOUNTS[mount]
    ei, gj_o, gj_c, zc = section(mat, t, ef)
    wing = P.HEAD_FRAME_HALF_Y - m["root_y"]
    w_wing = mass * G / (2 * P.HEAD_FRAME_HALF_Y)                    # N/mm of head width
    bend_sw = w_wing * wing ** 4 / (8 * ei)
    bend_tip = TIP_LOAD * (Y_C - m["root_y"]) ** 3 / (3 * ei)
    tw_o, tw_c = (TIP_LOAD * (P.ACTIVE_X / 2) * wing / gj for gj in (gj_o, gj_c))
    W = mass * G
    out = {
        "self weight": {"row centre": point_deflection(mount, k_c, al, W, ARM_ROW - 5, 0, ARM_ROW, 0),
                        "rear outer corner": point_deflection(mount, k_c, al, W, ARM_ROW - 5, 0, ARM_REAR, Y_C) + bend_sw,
                        "front outer corner": point_deflection(mount, k_c, al, W, ARM_ROW - 5, 0, ARM_FRONT, Y_C) + bend_sw},
        "20 N at row centre": {k: point_deflection(mount, k_c, al, TIP_LOAD, ARM_ROW, 0, x, y) for k, (x, y) in
                               {"row centre": (ARM_ROW, 0), "rear outer corner": (ARM_REAR, Y_C), "front outer corner": (ARM_FRONT, Y_C)}.items()},
    }
    for tag, tw in (("20 N at front outer corner, cover NOT structural (open section)", tw_o), ("20 N at front outer corner, cover screwed as shear panel (closed cell)", tw_c)):
        out[tag] = {"row centre": point_deflection(mount, k_c, al, TIP_LOAD, ARM_FRONT, Y_C, ARM_ROW, 0),
                    "rear outer corner": point_deflection(mount, k_c, al, TIP_LOAD, ARM_FRONT, Y_C, ARM_REAR, Y_C) + bend_tip - tw * P.ACTIVE_X / 2,
                    "front outer corner": point_deflection(mount, k_c, al, TIP_LOAD, ARM_FRONT, Y_C, ARM_FRONT, Y_C) + bend_tip + tw * P.ACTIVE_X / 2}
    play = m["play"] / m["e"]
    L_arm = m["arm"]["L"] if m["arm"] else 0.0
    out["receiver play (unloaded rattle, +-)"] = {"row centre": play * (ARM_ROW + L_arm + m["c0"]), "rear outer corner": play * (ARM_REAR + L_arm + m["c0"]), "front outer corner": play * (ARM_FRONT + L_arm + m["c0"])}
    k_pitch, k_roll, _ = mount_stiffness(mount, k_c, al)
    lever_cg = ARM_ROW - 5 + (0 if m["arm"] else m["c0"])
    i_pitch = mass * ((lever_cg / 1000) ** 2 + 0.118 ** 2 / 12)
    i_roll = mass * 0.350 ** 2 / 12
    mu = mass / (2 * P.HEAD_FRAME_HALF_Y / 1000)
    freq = {"pitch": math.sqrt(k_pitch / 1000 / i_pitch) / (2 * math.pi), "roll": math.sqrt(k_roll / 1000 / i_roll) / (2 * math.pi),
            "wing": 1.875 ** 2 / (2 * math.pi) * math.sqrt((ei / 1e6) / (mu * (wing / 1000) ** 4))}
    return out, {"EI": ei / 1e6, "GJ_open": gj_o / 1e6, "GJ_closed": gj_c / 1e6, "zc": zc, "k_pitch": k_pitch / 1000, "k_roll": k_roll / 1000,
                 "wing": wing, "f": freq, "f1": min(freq.values())}


def run(mount="C"):
    md, key = [], {}
    m = MOUNTS[mount]
    md.append("## 4. Head mount stiffness, cantilever deflection and natural frequencies\n")
    md.append(f"Mount as implemented: **{m['name'].strip()}**. Model: rigid head on four bearing lands (two per shoe, {m['e']:.0f} mm apart in x, shoes {2 * m['b']:.0f} mm apart in y) with one contact stiffness per land; "
              f"the head wings are cantilevers of {P.HEAD_FRAME_HALF_Y - m['root_y']:.1f} mm beyond the shoes; bending section = two frame walls ({WALL_H:.1f} mm tall) + 2 mm aluminium spreader (transformed section); "
              "wing torsion uses the open section (cover not structural) or the closed spreader-cover cell.\n")
    md.append(inputs_table([
        ("Tip load", TIP_LOAD, "N", "task statement"),
        ("Bearing land spacing 2b / base e", f"{2 * m['b']:.0f} / {m['e']:.0f}", "mm", "params.RECEIVER"),
        ("Contact stiffness per land, printed / aluminium", f"{RC['contact_k_printed']:.0f} / {RC['contact_k_aluminium']:.0f}", "N/mm", "STATED ASSUMPTION (no test data) -- measure on the first article; all results scale with 1/k"),
        ("Mount datum to rear / centre / front of the active row", f"{ARM_REAR} / {ARM_ROW} / {ARM_FRONT}", "mm", "head-internal geometry, unchanged"),
        ("Outer window corner y", Y_C, "mm", "contract optics"),
        ("E PETG-CF / PA-CF dry / ASA / 6061", "3800 / 5500 / 2200 / 68900", "MPa", "typical data-sheet values at 23 C, UNVERIFIED for the purchased material; printed parts are anisotropic (Z about 50-60 % of XY)"),
        ("Cold caveat", "E rises ~10-25 % at -20 C; impact strength and strain to failure fall", "-", "general polymer behaviour, not measured -> deflections are conservative for cold, strength is NOT"),
        ("PA-CF moisture caveat", "conditioned modulus about 0.5 x dry", "-", "typical PA-CF data sheets -> both tabulated"),
        ("Receiver play (rattle before preload)", m["play"], f"mm over {m['e']:.0f} mm", "ASSUMPTION; the draw latch preloads the shoes against the x-stops"),
        ("Head mass used (prototype / heaviest = production + 15 %)", "1.65 / 2.10", "kg", "section 1, rounded up"),
    ]))
    for build in BUILDS:
        d, s = evaluate(mount, build)
        md.append(f"\n### {build}\n")
        md.append(f"EI = {s['EI']:.0f} N m2, GJ open / closed = {s['GJ_open']:.1f} / {s['GJ_closed']:.0f} N m2, mount pitch / roll stiffness = {s['k_pitch']:.0f} / {s['k_roll']:.0f} N m/rad.\n")
        md.append(table(["Load case", "Row centre (mm)", "Rear outer window corner (mm)", "Front outer window corner (mm)"],
                        [(k, f(v["row centre"], 2), f(v["rear outer corner"], 2), f(v["front outer corner"], 2)) for k, v in d.items()]))
        md.append(f"\nFirst modes (calculated): head pitch on the mount {s['f']['pitch']:.0f} Hz, head roll on the mount {s['f']['roll']:.0f} Hz, wing bending {s['f']['wing']:.0f} Hz.")
        key[build] = {"self_front": d["self weight"]["front outer corner"], "tip_open": d["20 N at front outer corner, cover NOT structural (open section)"]["front outer corner"],
                      "tip_closed": d["20 N at front outer corner, cover screwed as shear panel (closed cell)"]["front outer corner"], "centre_20N": d["20 N at row centre"]["row centre"],
                      "f1": s["f1"], "k_pitch": s["k_pitch"], "k_roll": s["k_roll"]}
    md.append("\n**Reading.** Positive values are downward at the named point. With the shoes on the lane seams the roll term almost disappears and the wing overhang is 77 mm instead of 133 mm; what remains is pitch on the land base and, "
              "if the cover is not a shear panel, wing twist. Design rules for the head engineers: (1) screw the cover to the frame at <= 40 mm pitch so the spreader-cover cell is closed; (2) the spreader stays one piece across y = 0 "
              "(each printed half now carries its own shoe, so the y = 0 joint is no longer in the primary load path); (3) prove the land stiffness by a 20 N corner test (target < 0.5 mm printed).")
    k_tyre, mv = 40e3, 9.0
    md.append(f"\nVehicle heave on the tyres: with an assumed 40 N/mm per tyre and 9 kg, f = {math.sqrt(2 * k_tyre / mv) / (2 * math.pi):.0f} Hz (assumption; solid-tyre stiffness must be measured).")
    load = P.MASS_GOAL_KG * G * 3.0
    span, hand = 2 * P.GRIP["half_span_y"], 100.0
    sig = load / 2 * (span / 2 - hand / 4) / (P.GRIP["bar_x"] * P.GRIP["bar_z"] ** 2 / 6)
    cheek_a = (P.GRIP["cheek_y"][1] - P.GRIP["cheek_y"][0]) * P.GRIP["bar_x"]
    md.append("\n## 5. Carry-grip load path\n")
    md.append(inputs_table([("Design load", f"{load:.0f}", "N", "12 kg x g x 3 (handling factor, assumed)"), ("Bar section / span", f"{P.GRIP['bar_x']} x {P.GRIP['bar_z']} / {span}", "mm", "params.GRIP"),
                            ("Hand width", hand, "mm", "assumed gloved")]))
    md.append(f"\nBar bending stress {sig:.1f} MPa (solid section; a printed bar needs a 10 mm aluminium or CF tube core through both cheeks for creep and cold impact), "
              f"cheek tension {load / 2 / cheek_a:.2f} MPa, each cheek leg carries {load / 2:.0f} N into its yoke on the chassis plate (2 x M5 per yoke: {load / 4:.0f} N per screw at the design load). "
              "Proof test: 3 x weight for 60 s warm and at -20 C (VT-002).")
    key["grip_sigma_mpa"] = sig
    return "\n".join(md), key
