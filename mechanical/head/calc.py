"""Head calculations (closed form, evidence class: CALCULATED). Reuses the mount model of mechanical/common/calc/structure.py
and adds what the lead's model does not contain: the y = 0 joint of the printed frame, the lid fastened through discrete
standoffs, the rail kinematics, the light-path table, the tolerance stack and a lumped thermal check.
"""
from __future__ import annotations

import math

from mechanical.common import params as P
from mechanical.common.calc import structure as S

from . import hp as H

G = 9.81
E_AL = P.MATERIALS["AL6061"]["E"]
G_AL = E_AL / 2.66
TIP = S.TIP_LOAD


# ------------------------------------------------------------------------------------------------ section properties
def _rects_ei(rects):
    """rects: (E, width, z0, z1) -> EI about the horizontal neutral axis, and its height."""
    ea = sum(e * w * (z1 - z0) for e, w, z0, z1 in rects)
    zc = sum(e * w * (z1 - z0) * (z0 + z1) / 2 for e, w, z0, z1 in rects) / ea
    ei = sum(e * (w * (z1 - z0) ** 3 / 12 + w * (z1 - z0) * ((z0 + z1) / 2 - zc) ** 2) for e, w, z0, z1 in rects)
    return ei, zc


def frame_walls(e_frame):
    """Front and rear wall of the tray cut by a plane y = const through a window (not through a chimney)."""
    return [(e_frame, H.XF - H.CAV_X1, H.Z_FB, H.Z_SPR0), (e_frame, H.XF - H.BAY_X1, H.Z_SPR0, H.Z_WALL_TOP),
            (e_frame, H.CAV_X0 - H.XR, H.Z_FB, H.Z_SPR0), (e_frame, H.BAY_X0 - H.XR, H.Z_SPR0, H.Z_WALL_TOP)]


POST_FIXITY = 0.2          # STATED ASSUMPTION: a 5 mm post clamped in 2 mm plates reaches 20 % of the fixed-fixed stiffness
POST_K = POST_FIXITY * 12 * E_AL * (math.pi * H.LID_STANDOFF_D ** 4 / 64) / (H.Z_LID0 - H.Z_SPR1) ** 3     # N/mm per lid standoff
K_BOSS = {"prototype": 1500.0, "production": 8000.0}   # STATED ASSUMPTION: lateral stiffness of one M3 lid screw in a printed boss with a heat-set
                                                        # insert (prototype) / tapped in a 6061 boss (production), N/mm


def lid_rows(build):
    """Shear-web stiffness of the lid fastener rows (front and rear lines), N/mm per mm of row x height (= G t equivalent)."""
    from . import parts as T
    h = (H.Z_LID0 + H.Z_LID1) / 2 - (H.Z_SPR0 + H.Z_SPR1) / 2
    front = [p for p in T.lid_holes() if p[0] > 150]
    rear = [p for p in T.lid_holes() if p[0] < 90]
    bf = [p for p in T.lid_boss_xy() if p[0] > 150]
    kf = (len(front) * POST_K + len(bf) * K_BOSS[build]) * h / (2 * H.YW)
    kr = len(rear) * POST_K * h / (2 * H.YW)
    return {"front_row_Gt": kf, "rear_row_Gt": kr, "n_front": len(front) + len(bf), "n_rear": len(rear)}


def section(e_frame, lid_composite, build="prototype"):
    w_spr, w_lid = H.SPR_X1 - H.SPR_NOTCH_X, H.XF - H.XR - 2 * H.LID_INSET
    plates = [(E_AL, w_spr, H.Z_SPR0, H.Z_SPR1), (E_AL, w_lid, H.Z_LID0, H.Z_LID1)]
    walls = frame_walls(e_frame)
    if lid_composite:
        ei, zc = _rects_ei(walls + plates)
    else:       # lid bends about its own axis (no shear connection)
        ei1, zc = _rects_ei(walls + plates[:1])
        ei = ei1 + _rects_ei(plates[1:])[0]
    # torsion about y: open (St Venant, thin strips) and the spreader-lid cell closed through the standoff rows
    g_fr = e_frame / 2.7
    gj_open = sum(g_fr * (z1 - z0) * w ** 3 / 3 if w < (z1 - z0) else g_fr * w * (z1 - z0) ** 3 / 3 for _, w, z0, z1 in walls) + \
        G_AL * (w_spr + w_lid) * 2.0 ** 3 / 3
    b = 183.0 - 77.5                       # distance between the front and rear standoff rows
    h = (H.Z_LID0 + H.Z_LID1) / 2 - (H.Z_SPR0 + H.Z_SPR1) / 2
    rows = lid_rows(build)
    gt_web = min(rows["front_row_Gt"], rows["rear_row_Gt"])     # equivalent G*t of the weaker lid fastener row
    flex = 2 * b / (G_AL * 2.0) + 2 * h / gt_web
    gj_closed = 4 * (b * h) ** 2 / flex
    return {"EI": ei, "zc": zc, "GJ_open": gj_open, "GJ_closed": gj_closed + gj_open, "cell_b": b, "cell_h": h, "gt_web": gt_web}


# ------------------------------------------------------------------------------------------------ joint (y = 0) stiffness
def joint_stiffness(build):
    """Rotational stiffness (N mm / rad, bending about x) of everything that crosses the y = 0 plane between the two shoes."""
    span = 2 * H.SHOE_Y - 2 * H.SHOULDER_HY          # free length between the T-head regions: 135 mm
    out = {}
    w_spr, w_lid = H.SPR_X1 - H.SPR_X0, H.XF - H.XR - 2 * H.LID_INSET
    out["spreader alone (2 mm)"] = E_AL * w_spr * 2.0 ** 3 / 12 / span
    out["lid alone (2 mm)"] = E_AL * w_lid * 2.0 ** 3 / 12 / span
    h = (H.Z_LID0 + H.Z_LID1) / 2 - (H.Z_SPR0 + H.Z_SPR1) / 2
    from . import parts as T
    half = span / 2
    k_conn = sum(POST_K for x, y in T.lid_holes() if abs(y) <= half) + sum(K_BOSS[build] for x, y in T.lid_boss_xy() if abs(y) <= half)
    out["spreader + lid as a couple through the lid fasteners near the joint (slip model)"] = h ** 2 * k_conn / 4
    out["rear bridge plate (3 x 13 on edge, T-head to T-head)"] = E_AL * H.BRIDGE_T * 13.0 ** 3 / 12 / (2 * H.BRIDGE_HY)
    if build == "production":
        e = E_AL
        ei = _rects_ei(frame_walls(e))[0]
        out["one-piece aluminium frame walls"] = ei / span
    return out


def halves_model(k_c, k_joint, f=TIP, y_load=None):
    """Two rigid halves, each on its own shoe (two lands, local roll stiffness of the 16 mm wide lands), joined at y = 0 by
    a stiff shear connection and the rotational spring k_joint. Returns the deflection at the outer window corner (mm)."""
    y_load = y_load or (H.SEG_Y[0] + H.ACT_Y / 2)
    kv = 2 * k_c                                    # vertical, two lands per shoe
    kr = 2 * k_c * H.SHOE_W ** 2 / 12               # local roll of one shoe on its lands
    ks = 1.0e5                                      # shear across the joint (dowels + tongue + plates), N/mm
    b = H.SHOE_Y
    # DOF: w1, t1 (left half at its shoe), w2, t2 (right half). Displacement of the left half at offset d (toward +y): w1 + t1 * d
    import numpy as np
    K = np.zeros((4, 4))
    K[0, 0] += kv; K[1, 1] += kr; K[2, 2] += kv; K[3, 3] += kr
    # joint shear: left edge at d = -b, right edge at d = +b (right half coordinate toward +y)
    v = np.array([1.0, -b, -1.0, -b])
    K += ks * np.outer(v, v)
    r = np.array([0.0, 1.0, 0.0, -1.0])
    K += k_joint * np.outer(r, r)
    F = np.array([f, f * (y_load - b), 0.0, 0.0])
    u = np.linalg.solve(K, F)
    return float(u[0] + u[1] * (y_load - b)), u


def structure(masses):
    """Corner deflection under 20 N and first modes for the split printed head and the one-piece aluminium head."""
    res, md = {}, []
    cases = [("prototype, split PA-CF (dry) frame", "PA-CF", 1.0, "prototype", RC_K["printed"]),
             ("prototype, split PA-CF (conditioned, E x 0.5)", "PA-CF", 0.5, "prototype", RC_K["printed"]),
             ("prototype, split PETG-CF frame", "PETG-CF", 1.0, "prototype", RC_K["printed"]),
             ("production, one-piece 6061 frame", "AL6061", 1.0, "production", RC_K["al"])]
    arm_f = S.ARM_FRONT
    y_c = S.Y_C
    for name, mat, ef, build, k_c in cases:
        e = P.MATERIALS[mat]["E"] * ef
        mass = masses[build] / 1000.0
        al = mat == "AL6061"
        kj = joint_stiffness(build)
        kj_all = sum(kj.values())
        kj_nolid = kj_all - kj["lid alone (2 mm)"] - kj["spreader + lid as a couple through the lid fasteners near the joint (slip model)"]
        root_y = H.SHOE_Y + H.THEAD_HY                     # wing clamps at the outer end of the T-head / spreader tab
        wing = H.YW - root_y
        out = {}
        for tag, comp, kjv, closed in (("lid fitted (all screws)", True, kj_all, True), ("lid removed (service state)", False, kj_nolid, False)):
            sec = section(e, comp, build)
            # (a) rigid-body pitch on the four lands (lead's model, mount C), (b) roll through the two-halves model, (c) wing bending, (d) wing twist
            pitch = S.point_deflection("C", k_c, al, TIP, arm_f, 0.0, arm_f, 0.0) - TIP / (4 * k_c)
            roll, _ = halves_model(k_c, kjv)
            bend = TIP * (y_c - root_y) ** 3 / (3 * sec["EI"])
            gj = sec["GJ_closed"] if closed else sec["GJ_open"]
            twist = TIP * (P.ACTIVE_X / 2) * wing / gj * (P.ACTIVE_X / 2)
            out[tag] = {"pitch": pitch, "roll_incl_joint": roll, "wing_bending": bend, "wing_twist": twist, "total": pitch + roll + bend + twist,
                        "EI_Nm2": sec["EI"] / 1e6, "GJ_Nm2": gj / 1e6, "k_joint_Nm_per_rad": kjv / 1000}
        # rigid joint reference (what a monolithic head of the same material would do)
        roll_rigid, _ = halves_model(k_c, 1e12)
        out["roll_if_joint_rigid"] = roll_rigid
        # modes
        k_pitch, k_roll, _ = S.mount_stiffness("C", k_c, al)
        lever = (S.ARM_ROW - 5 + S.MOUNTS["C"]["c0"]) / 1000
        i_pitch = mass * (lever ** 2 + 0.118 ** 2 / 12)
        i_roll = mass * 0.350 ** 2 / 12
        sec = section(e, True, build)
        mu = mass / (2 * H.YW / 1000)
        f_wing = 1.875 ** 2 / (2 * math.pi) * math.sqrt((sec["EI"] / 1e6) / (mu * (wing / 1000) ** 4))
        i_half = (mass / 2) * (H.YW / 1000) ** 2 / 12
        kr = 2 * k_c * H.SHOE_W ** 2 / 12
        f_butterfly = math.sqrt((2 * kj_all + kr) / 1000 / i_half) / (2 * math.pi)
        f = {"pitch on the mount": math.sqrt(k_pitch / 1000 / i_pitch) / (2 * math.pi), "roll on the mount": math.sqrt(k_roll / 1000 / i_roll) / (2 * math.pi),
             "halves rocking about the y = 0 joint": f_butterfly, "wing bending": f_wing}
        out["modes_hz"] = f
        out["f1_hz"] = min(f.values())
        out["joint_terms_Nm_per_rad"] = {k: v / 1000 for k, v in kj.items()}
        out["mass_kg"] = mass
        res[name] = out
    return res


RC_K = {"printed": P.RECEIVER["contact_k_printed"], "al": P.RECEIVER["contact_k_aluminium"]}


# ------------------------------------------------------------------------------------------------ rails
def rails():
    sw = H.SW
    pt_lo, pt_nom, pt_hi = 0.6, 0.8, sw["pt_max"]
    total = sw["pt_max"] + sw["ot_min"]                 # FP max - TTP max = 2.1 mm plunger travel available
    slope = H.CAM_RISE / H.CAM_RAMP
    lost = 0.15                                         # pin-to-notch clearance + pin-to-plunger gap as modelled
    front = {
        "stroke_to_stop_mm": H.RAIL_GAP,
        "trip_travel_mm": {"min": pt_lo / slope, "nominal": pt_nom / slope + lost, "max (unshimmed, PT max)": pt_hi / slope + lost},
        "post_trip_stroke_mm": H.RAIL_GAP - (pt_hi / slope + lost),
        "plunger_depression_at_stop_mm": H.CAM_RISE, "plunger_travel_available_mm": total,
        "cam": f"notch {H.CAM_RISE} deep, ramp {H.CAM_RAMP} long ({math.degrees(math.atan(slope)):.0f} deg), then dwell on the rod diameter",
    }
    k, free = H.SPRING["rate"], H.SPRING["free"]
    l_rest = H.ROD_BORE_DEPTH - H.ROD_ENGAGE
    l_full = l_rest - H.RAIL_GAP
    front["spring_force_N"] = {"rest (both)": 2 * k * (free - l_rest), "full stroke (both)": 2 * k * (free - l_full), "solid length ok": l_full > H.SPRING["solid"]}
    front["trip_force_N_estimate"] = 2 * k * (free - l_rest) + sw["of_max_n"] * slope + 0.3 * (2 * k * (free - l_rest))
    th0, th1 = math.asin((H.XF + H.RAIL_GAP - H.BAIL_D / 2 - H.BAIL_X) / H.BAIL_L), math.asin((H.XF - H.BAIL_D / 2 - H.BAIL_X) / H.BAIL_L)
    kt = 79000 * (math.pi * H.BAIL_D ** 4 / 32) / (2 * H.BAIL_Y)
    lever = H.BAIL_L * math.cos(th0)
    front["bail"] = {"arm_angle_rest_deg": math.degrees(th0), "arm_angle_full_deg": math.degrees(th1), "tip_z_rest": H.BAIL_Z - H.BAIL_L * math.cos(th0),
                     "tip_z_full": H.BAIL_Z - H.BAIL_L * math.cos(th1), "sync_stiffness_N_per_mm_differential": kt / lever ** 2,
                     "lag_of_far_end_mm_for_end_hit": k * (free - l_rest) / (kt / lever ** 2)}
    # energy / load into the frame: robot 12 kg at survey speed stopping on the positive stop (worst case, drive not yet stopped)
    front["stop_model_mm"] = {"travel after contact, contract inputs (0.10 m/s)": 27.5, "travel after contact, electronics model (0.10 m/s)": 14.3}
    front["max_speed_stopping_inside_post_trip_stroke_mps"] = {
        "contract inputs (t 0.15 s, a 0.4)": _vmax(front["post_trip_stroke_mm"], 0.15, 0.4), "t 0.05 s, a 1.0 m/s2": _vmax(front["post_trip_stroke_mm"], 0.05, 1.0)}
    # side zones: 45 deg slide, plunger along x, adjusting screw presets the plunger
    preset = (0.25, 0.40, 0.55)
    gap = H.SIDE_GAP
    side = {"travel_to_stop_lateral_mm": gap, "slide_travel_mm": gap * math.sqrt(2),
            "trip_lateral_mm": {"min": max(pt_lo - preset[2], 0.05), "nominal": pt_nom - preset[1], "max": pt_hi - preset[0]},
            "plunger_depression_at_stop_mm": gap + preset[2], "plunger_travel_available_mm": total,
            "margin_trip_before_stop_mm": gap - (pt_hi - preset[0]),
            "note": "adjusting screw M3 on the wing return presets the plunger 0.40 +- 0.15 mm; both a lateral hit on the side strip and a rear hit on the wing return move the L-rail along the 45 deg guide"}
    return {"front": front, "side": side, "switch_data": {"PT_max": sw["pt_max"], "OT_min": sw["ot_min"], "MD": sw["md"], "OF_max_N": sw["of_max_n"],
                                                           "status": "PARTIAL: values read from a search extract of the Omron D2HW table (FP 11.2 max, OP 10.4 +-0.2, TTP 9.1 max); confirm on the datasheet"}}


def _vmax(d_mm, t, a):
    d = d_mm / 1000.0
    return (-t + math.sqrt(t * t + 2 * d / a)) * a


# ------------------------------------------------------------------------------------------------ light paths
def light_paths():
    """Every joint of the light-tight volume: (id, joint, from, to, path description, length mm, turns, barriers, builds)."""
    a, b, hl = H.CAS_LIP_Y
    ax, bx, hlx = H.CAS_LIP_X
    half_rib = H.RIB_W / 2
    rows = [
        ("L01", "frame halves, y = 0 (prototype)", "ambient (front / rear / underside slit)", "bay",
         f"butt faces; U-shaped tongue {H.TONGUE_T} x {H.TONGUE_H} in a groove (0.15 clearance) below the deck, continued by a {H.LAP_H} mm ship-lap of the upper walls: in, across, out",
         2 * H.TONGUE_H + H.TONGUE_T + 1.0, 4, "tongue-and-groove + ship-lap; the lap ends under the lid gasket; black PA-CF", "X"),
        ("L02", "frame halves, y = 0 (prototype)", "ambient / bay", "lane S1 or S2",
         f"the joint plane never touches a lane: each half rib is {half_rib:.2f} mm solid; remaining routes are L04 (rib top) and L06 (cassette)", half_rib, 0,
         f"{half_rib:.2f} mm solid wall (1.45 mm at the groove)", "X"),
        ("L03", "lid on the tray wall", "ambient", "bay", "flat joint, gasket on the wall top (lid seated on hard bosses / standoffs inside the gasket loop), then the EMI fence flange with its conductive gasket (prototype) / conductive gasket in a groove (production)",
         H.XF - H.BAY_X1, 0, "black closed-cell gasket 1.2 -> 0.8 mm + second (conductive) gasket line; lid interlock opens the bias first", "X,P"),
        ("L04", "spreader on the rib tops", "lane", "adjacent lane", "under the spreader across the rib: land, gasket strip in the 0.6 mm relief, land",
         H.RIB_W, 0, "black gasket strip 5.4 mm wide compressed 40 % + retention pads lapping the cavity edges", "X,P"),
        ("L05", "spreader edge at the outer side walls", "lane S0 / S3 (top)", "bay", "0.3 mm slot between the spreader edge and the side wall, closed by the pad pressed on the 45 deg relief",
         2.0, 1, "compressed pad edge; bay is inside the light-tight volume", "X,P"),
        ("L06", "window cassette, long sides at a seam rib", "ambient (0.4 mm slot between cassettes)", "lane",
         f"up the slot, over the rib fin, down/up the lip in its groove ({hl} mm lip, {hl - 0.5:.2f} mm overlap), gasket land {a:.2f} mm", 0.5 + 2 * hl + a + 1.0, 3,
         "lip in groove + black gasket on the 1.05 mm land + film bond", "X,P"),
        ("L07", "window cassette, long side at the outer wall", "ambient (behind the side rail)", "lane S0 / S3",
         f"lip in the open rebate of the wall foot, gasket land {a:.2f} mm; the side rail strip covers the slot from outside", hl + a + 0.9, 2,
         "lip + gasket; weakest cassette joint (driven by the 3.75 mm outer margin)", "X,P"),
        ("L08", "window cassette, front and rear borders", "ambient", "lane", f"lip {hlx} mm tall at the border edge in a groove / rebate, then {ax:.1f} mm gasket land",
         hlx * 2 + ax, 2, "lip + 5.9 mm gasket land + film bond", "X,P"),
        ("L09", "cassette to cassette under a rib", "lane", "adjacent lane", "gasket land, lip, rib fin 3.4 mm, lip, gasket land", 2 * (a + hl) + 3.4, 4, "two lips + two gasket lands", "X,P"),
        ("L10", "entrance film", "ambient", "lane", "aluminised film bonded all round to the cassette land (1.05 mm on the long sides, 5 mm on the ends)", 1.05, 0,
         "opaque film; pinholes are a film acceptance item (dark-count test)", "X,P"),
        ("L11", "barrier plate in the lane", "floor part of the lane", "reference part of the same lane",
         "around the plate edge: under the lower spacer ring, 0.1 mm edge clearance with foam edge, over the upper ring", 2.4 + 2.0 + 2.4, 2,
         "2 mm opaque plate + black foam edge + two ring overlaps of 2.4 mm", "X,P"),
        ("L12", "chimney insert shelf", "floor carrier space", "reference carrier space (same lane)", "shelf at barrier height; coax notch 5 x 2.5 packed with black foam",
         2.5, 1, "shelf + foam plug; SiPM carriers are opaque-potted by the OEM (UNKNOWN)", "X,P"),
        ("L13", "chimney to chimney via the bay", "lane (carrier aperture)", "other lane", "up the chimney, along the rear strip of the bay, down the next chimney",
         87.5 + 2 * 15, 2, "depends on the OEM carrier-to-guide seal (UNKNOWN); chimney inserts are black; dark-count cross-talk test at end of line", "X,P"),
        ("L14", "cable port", "ambient", "bay", "split grommet with three internal ribs on a black cable jacket, compressed by the lid", H.BAY_X0 - H.XR + 1.5, 0,
         "compressed elastomer around the cable", "X,P"),
        ("L15", "breather vent", "ambient", "bay", "membrane, then a printed baffle with two 90 deg turns behind the rear comb", 8.0, 2, "ePTFE membrane (translucent) + black baffle", "X,P"),
        ("L16", "rail stop / switch pin", "ambient (rod bore)", "bay", "rod annulus 0.15 x 25 mm, turn up, pin annulus 0.05 x 14 mm, silicone membrane under the saddle",
         25 + 14, 1, "two close annuli + membrane", "X,P"),
        ("L17", "side-zone guide slits and pin holes", "ambient", "bay", "slit is blind; pin hole closed by the screw and the spreader", 6.0, 1, "screw shank + spreader", "X,P"),
        ("L18", "side switch lead channel", "ambient (switch pocket)", "bay", "channel 1.9 x 2.8 mm potted with black RTV after wiring", 9.0, 1, "potting", "X,P"),
        ("L19", "T-head pocket", "ambient", "lane", "no opening: 2.0 mm solid web between the pocket and the cavities", 2.0, 0, "solid wall + aluminium T-head", "X,P"),
        ("L20", "outer side wall", "ambient", "lane S0 / S3", "1.5 mm solid wall (four perimeters, black PA-CF); side rail strip 0.95 mm outside", H.SIDE_WALL, 0,
         "solid wall; printed wall opacity to be confirmed by the dark-count test (foil tape contingency)", "X"),
        ("L21", "chimney drain (one per lane)", "ambient (frame underside behind the cassette)", "chimney / lane carrier space",
         f"up {H.DRAIN['z_ch'][0] - H.Z_FB:.1f} mm, across {H.DRAIN['x_in'] - H.DRAIN['x_out']:.2f} mm in a {H.DRAIN['d']} x 1.0 channel in the floor, up {H.CHIM_FLOOR_REAR - H.DRAIN['z_ch'][1]:.1f} mm, "
         "then 0.6 mm under the black chimney insert", 0.9 + (H.DRAIN['x_in'] - H.DRAIN['x_out']) + 0.6 + 3.0, 3, "three right-angle turns in black material; no straight line of sight (tool-checked)", "X,P"),
        ("L22", "lid screw holes (34 M3)", "ambient", "bay", "screw head on a bonded sealing washer; boss / standoff top clamped to the lid underside",
         2.0, 1, "bonded sealing washer (elastomer) + clamped hard seat; holes are inside the gasket loop", "X,P"),
    ]
    return [dict(zip(("id", "joint", "from", "to", "path", "length_mm", "turns", "barriers", "builds"), r)) for r in rows]


# ------------------------------------------------------------------------------------------------ tolerance stack
def tolerance_stack():
    lever = (H.WIN_X1 - sum(P.RECEIVER["land_x"]) / 2) / (P.RECEIVER["land_x"][1] - P.RECEIVER["land_x"][0])
    rows = [  # contributor, nominal (signed, mm, from datum C upward +), prototype tol, production tol, note
        ("shoe underside (datum C, z 16.00) to T-head top", H.Z_SPR0 - 0.5 - H.SHOE_Z0, 0.03, 0.03, "one machined part"),
        ("G10 isolator (both builds)", 0.5, 0.05, 0.02, "G10 sheet, measured and selected (0.40 / 0.50 / 0.60) for trimming"),
        ("spreader underside = frame top seat (z 30.00)", 0.0, 0.0, 0.0, "interface plane"),
        ("frame top seat to frame underside", -(H.Z_SPR0 - H.Z_FB), 0.15, 0.03, "printed height over 19.5 mm (0.2 mm layers) / one CNC set-up"),
        ("cassette seat bosses (frame underside to cassette top)", -(H.Z_FB - H.FILM_Z), 0.05, 0.02, "hard seats at the four cassette screws"),
        ("film bond line", 0.0, 0.02, 0.02, "transfer adhesive 0.03 mm"),
        ("frame / spreader flatness over the 350 mm width", 0.0, 0.20, 0.08, "printed halves pulled flat by the spreader / machined"),
        (f"shoe pair parallelism 0.03 over the 54 mm land base x {lever:.2f}", 0.0, 0.03 * lever, 0.02 * lever, "front window edge; from the shoe drawing tolerance"),
    ]
    nom = H.SHOE_Z0 + sum(r[1] for r in rows)
    out = {"nominal_film_z": nom}
    for col, tag in ((2, "prototype"), (3, "production")):
        tols = [r[col] for r in rows]
        out[tag] = {"worst_case_pm_mm": sum(tols), "rss_pm_mm": math.sqrt(sum(t * t for t in tols))}
    out["rows"] = [dict(zip(("contributor", "nominal_mm", "prototype_pm", "production_pm", "note"), r)) for r in rows]
    out["budget_line_in_mech_calcs_pm_mm"] = 0.30
    return out


# ------------------------------------------------------------------------------------------------ thermal (lumped, IB-39 assumption set)
K_FOAM, K_PRINT, K_AL, K_AIR = 0.035, 0.30, 160.0, 0.024   # W/m K: closed-cell foam, printed PA-CF, 6061, air (handbook)
K_G10, K_PA66, K_GUIDE, K_CU = 0.29, 0.25, 0.19, 390.0     # W/m K: G10 through-thickness, PA66 washer, PVT/PMMA guide, copper (handbook)
SIGMA, EMISSIVITY = 5.67e-8, 0.9                           # frame underside / film and floor both taken as 0.9 (conservative for the loss)
# IB-39 assumption set (one set for the project; mechanical/common/calc/thermal.py uses the same):
T_AMBIENT_C = (-20.0, -25.0)          # RQ-029 operating / qualification ambient
T_SET_C = 10.0                        # regulated set-point at the SiPM carrier (baseline)
T_SET_OPTION_C = 5.0                  # labelled option, reason in thermal()["_option"]
H_EXT = {"still air": 12.0, "moving / draught": 25.0}      # W/m2 K incl. radiation; 25 = sensitivity
H_IN = 6.0                            # W/m2 K inside the closed head (natural convection)
FLOOR_GAP = 0.010                     # m: film plane z 10 above the floor (near-floor air layer, stable: hot above cold -> conduction only)
P_ELEC_TYP, P_ELEC_MAX = 1.20, 2.10   # W: electronics/analysis/head_afe_budget.md section 8 "Total at J1 pins 1/2: 1.20 W typical, 2.10 W maximum";
                                      # only the typical value is credited as heating (power_budget.md still carries the 5 W contract target: no
                                      # typical head figure there)
HEATER_FILMS_W = 4 * 7.5              # BOM PUR-HEATER: four 7.5 W polyimide zones at 12 V = 30 W (= 4.8 ohm element of head_afe_budget.md section 9)
HEATER_AT_10V_W = 20.8                # head_afe_budget.md section 9: 4.8 ohm at 10.0 V (end of discharge)
CUTOUT_OPEN_C = 45.0                  # BOM PUR-TCO bimetal, opens 45 C (UNVERIFIED part data)
# Receiver boundary: the T-heads are isolated from the heated spreader by the 0.5 mm G10 (IB-38), but the shoes sit in the body channels.
# Body side (prototype body RR-X: PAHT-CF channels with steel dowel-pin lands on the aluminium chassis plate, mechanical/prototype_x1c) per shoe:
# x-stop pads 560 mm2 through 6 mm PAHT-CF (0.028 W/K) + two dowel-pin line contacts (0.01 W/K each) + printed side / roof pads (0.02 W/K)
# -> 0.07 W/K, with the chassis plate at ambient. STATED ASSUMPTION (order of magnitude); the bound "receiver metal at ambient" is shown too.
G_BODY_PER_SHOE = 0.07
C_P = {"PA-CF": 1300, "PETG-CF": 1200, "ASA": 1300, "PA12-MJF": 1600, "POM": 1450, "TPU": 1500, "AL6061": 896, "AL5052": 900, "SS304": 500, "SS301": 500,
       "STEEL": 470, "BRASS": 380, "COPPER": 385, "FR4": 1100, "PMMA": 1450, "PVT": 1400, "SIL-FOAM": 1100, "EPDM-FOAM": 1500, "PI": 1100, "PET": 1200, "MIXED": 900}


def jacket_coverage():
    """Projected areas (m2) actually covered by the jacket and the liner, from the solids."""
    from . import parts as T
    from .geom import box, volume
    cap = T.jacket_top()
    z = H.Z_LID1 + H.JACKET_T
    a_cap = volume(cap.intersect(box(0, 300, -200, 200, z - 0.1, z))) / 0.1 / 1e6
    a_front = volume(T.jacket_front()) / H.JACKET_T / 1e6
    a_liner = volume(T.lid_liner()) / T.LINER_T / 1e6
    return a_cap, a_front, a_liner


def receiver_conductance(build):
    """Head (FRAME / interior) -> receiver metal (shoes, T-heads, bridge, keeper), W/K, from the model geometry (calculated)."""
    xe = H.XR - H.THEAD_POCKET_CLR
    h_t = (H.Z_SPR0 - 0.5) - H.SHOE_Z0                               # T-head height in the pocket
    a_g10 = (H.THEAD_X1 - H.XR) * 2 * H.THEAD_HY / 1e6                # isolator area under the spreader, one shoe
    a_gap = (2 * H.THEAD_HY * h_t + 2 * (H.THEAD_X1 - xe) * h_t + (H.THEAD_X1 - xe) * 2 * H.THEAD_HY) / 1e6   # front, ends, bottom faces in the 0.3 air gap
    g10 = K_G10 * a_g10 / 0.0005
    r_gap = H.THEAD_POCKET_CLR / 1000 / K_AIR + (0.002 / K_PRINT if build == "prototype" else 0.0)   # + 2 mm printed web behind the gap (prototype)
    gap = a_gap / r_gap
    washer = K_PA66 * (math.pi * (3.0 ** 2 - 1.6 ** 2) / 1e6) / 0.0008 + K_PA66 * (math.pi * 4.6 * 2.0 / 1e6) / 0.0007   # under the head + shoulder sleeve
    screws = len(H.THEAD_SCREW_DY) * washer
    per_shoe = g10 + gap + screws
    keeper = K_AIR * (40.8 * 30.0 / 1e6) / 0.0007                     # keeper plate 0.6 mm air + 0.1 mm tape above the lid
    a_br = (2 * (H.BRIDGE_HY - 0.2) * 13.0 + 40.0 * 14.6) / 1e6
    bridge = a_br / (0.0003 / K_AIR + (0.0026 / K_PRINT if build == "prototype" else 0.0))     # bridge 0.3 mm behind the rear wall
    return {"G10 isolators (2)": 2 * g10, "air gaps round the T-heads (2)": 2 * gap, "T-head screws through insulating washers (8)": 2 * screws,
            "keeper over the lid": keeper, "bridge behind the rear wall": bridge, "total": 2 * per_shoe + keeper + bridge}


def cable_conductance(h):
    """J1 / J2 pigtails as infinite copper fins (conservative: tanh -> 1), conductors per contract J1/J2 pin tables + an assumed 1.0 mm2 braid."""
    awg = {18: 0.823, 20: 0.519, 24: 0.205}
    cables = {"J1": (2 * awg[20] + 2 * awg[18] + 3 * awg[24] + 1.0, H.CABLE_D["J1"]), "J2": (8 * awg[24] + 1.0, H.CABLE_D["J2"])}
    return {k: math.sqrt(h * math.pi * d / 1000 * K_CU * a / 1e6) for k, (a, d) in cables.items()}


def h_floor(t_amb, t_set, h_ext):
    """Floor-facing side: 10 mm near-floor air layer (conduction; stable stratification) + radiation to the floor at ambient. In the moving-air
    sensitivity the floor side gets the external coefficient (bound)."""
    tm = (t_amb + t_set) / 2 + 273.15
    e = 1 / (2 / EMISSIVITY - 1)
    still = K_AIR / FLOOR_GAP + 4 * SIGMA * e * tm ** 3
    return still if h_ext <= 12.0 else max(h_ext, still)


def ua_case(build, h_ext, jacket, t_amb, t_set, receiver="body"):
    a_cap, a_front, a_liner = _COV()
    wall_k = K_PRINT if build == "prototype" else K_AL
    a_top = (H.XF - H.XR) * 2 * H.YW / 1e6
    a_side = 2 * ((H.XF - H.XR) + 2 * H.YW) * (H.Z_LID1 - H.Z_FB) / 1e6
    a_win = 4 * H.ACT_X * H.ACT_Y / 1e6
    a_bot = a_top - a_win
    r_liner, r_j = 0.0005 / K_FOAM, H.JACKET_T / 1000 / K_FOAM
    r_top = 1 / h_ext + 1 / H_IN
    ua_top = (a_top - a_liner) / r_top + a_liner / (r_top + r_liner)
    if jacket:      # the cap covers the liner area and the rest (holes / keeper / latch cut-outs uncovered): split proportionally
        f = a_cap / a_top
        ua_top = (1 - f) * ua_top + f * ((a_top - a_liner) / (r_top + r_j) + a_liner / (r_top + r_liner + r_j))
    r_side = 1 / h_ext + 0.0026 / wall_k + 1 / H_IN
    ua_side = a_side / r_side if not jacket else (a_side - a_front) / r_side + a_front / (r_side + r_j)
    hf = h_floor(t_amb, t_set, h_ext)
    ua_win = a_win / (0.00525 / 2 / K_GUIDE + 0.00025 / K_GUIDE + 0.001 / K_AIR + 1 / hf)   # floor SiPM carrier at set-point -> floor guide mid-plane
    ua_bot = a_bot / (1 / H_IN + 0.004 / wall_k + 1 / hf)
    rc = receiver_conductance(build)
    g_ra = 2 * G_BODY_PER_SHOE + h_ext * 0.0036 if receiver == "body" else 1e9      # + exposed bridge / keeper faces (0.0036 m2)
    ua_rec = 1 / (1 / rc["total"] + 1 / g_ra)
    cab = sum(cable_conductance(h_ext).values())
    ua = ua_top + ua_side + ua_win + ua_bot + ua_rec + cab
    return ua, {"top": ua_top, "sides": ua_side, "windows (floor gap)": ua_win, "underside frame (floor gap)": ua_bot, "receiver shoes": ua_rec, "cables J1 + J2": cab}, hf


_COV_CACHE = {}


def _COV():
    if "v" not in _COV_CACHE:
        _COV_CACHE["v"] = jacket_coverage()
    return _COV_CACHE["v"]


def thermal_mass(parts):
    """J/K from the model masses x handbook specific heat (calculated)."""
    return sum(p.mass() / 1000.0 * C_P.get(p.material, 900) for p in parts)


def warmup_min(c, ua, p, t_amb, t_set):
    """Lumped first-order warm-up from a soak at t_amb to t_set with constant power p (minutes); None if never reached."""
    t_inf = t_amb + p / ua
    if t_inf <= t_set:
        return None
    return c / ua * math.log((t_inf - t_amb) / (t_inf - t_set)) / 60.0


def thermal(builds=None):
    """IB-39: heater power to hold the SiPM carrier at the set-point, one assumption set (calculated, lumped steady state)."""
    out = {"_assumptions": {
        "ambient_c": list(T_AMBIENT_C), "set_point_c": T_SET_C, "set_point_option_c": T_SET_OPTION_C, "h_ext_w_m2k": dict(H_EXT), "h_in_w_m2k": H_IN,
        "electronics_credit_w": P_ELEC_TYP, "electronics_max_w_not_credited": P_ELEC_MAX, "floor_gap_mm": FLOOR_GAP * 1000, "emissivity": EMISSIVITY,
        "receiver_body_side_w_per_k_per_shoe": G_BODY_PER_SHOE, "jacket": "RR-HD-S-131/132 fitted below 0 C (standard cold configuration); no-jacket shown"}}
    a_cap, a_front, a_liner = _COV()
    a_top = (H.XF - H.XR) * 2 * H.YW / 1e6
    out["_jacket_coverage"] = {"top_area_m2": a_top, "cap_covered_m2": a_cap, "cap_fraction": a_cap / a_top, "front_band_m2": a_front, "liner_m2": a_liner,
                               "side_area_m2": 2 * ((H.XF - H.XR) + 2 * H.YW) * (H.Z_LID1 - H.Z_FB) / 1e6}
    out["_receiver"] = {b: receiver_conductance(b) for b in ("prototype", "production")}
    out["_cables"] = {k: cable_conductance(v) for k, v in H_EXT.items()}
    rows = []
    for build in ("prototype", "production"):
        for hname, h in H_EXT.items():
            for jacket in (True, False):
                for t_set in (T_SET_C, T_SET_OPTION_C):
                    for t_amb in T_AMBIENT_C:
                        for rec in (("body", "bound") if (t_set == T_SET_C and jacket) else ("body",)):
                            ua, split, hf = ua_case(build, h, jacket, t_amb, t_set, rec)
                            need = max(ua * (t_set - t_amb) - P_ELEC_TYP, 0.0)
                            rows.append({"build": build, "ambient_c": t_amb, "set_point_c": t_set, "h_ext_w_m2k": h, "air": hname, "jacket": jacket,
                                         "receiver_boundary": "body channels (0.07 W/K per shoe)" if rec == "body" else "BOUND: receiver metal at ambient",
                                         "electronics_credit_w": P_ELEC_TYP, "ua_w_per_k": round(ua, 3), "heater_power_w": round(need, 1),
                                         "within_30w_films": need <= HEATER_FILMS_W, "within_20w8_at_10v": need <= HEATER_AT_10V_W,
                                         "split_w_per_k": {k: round(v, 3) for k, v in split.items()}, "h_floor_w_m2k": round(hf, 2)})
    out["cases"] = rows
    if builds:
        out["thermal_mass_j_per_k"] = {b: round(thermal_mass(builds[b])) for b in ("prototype", "production")}
        wu = {}
        for b in ("prototype", "production"):
            ua, _, _ = ua_case(b, H_EXT["still air"], True, -25.0, T_SET_C)
            c = out["thermal_mass_j_per_k"][b]
            wu[b] = {"ua_w_per_k": round(ua, 3), "tau_min": round(c / ua / 60, 0),
                     "warmup_min_30w_12v": warmup_min(c, ua, HEATER_FILMS_W + P_ELEC_TYP, -25.0, T_SET_C),
                     "warmup_min_20w8_10v": warmup_min(c, ua, HEATER_AT_10V_W + P_ELEC_TYP, -25.0, T_SET_C),
                     "steady_c_heater_stuck_on_15v_at_+20c": round(20.0 + (46.9 + P_ELEC_MAX) / ua_case(b, 12.0, True, 20.0, 20.0)[0], 0),
                     "steady_c_full_30w_at_-25c": round(-25.0 + (HEATER_FILMS_W + P_ELEC_TYP) / ua, 0)}
        out["warmup_from_-25c_soak"] = wu
    out["_option"] = (f"Option set-point +{T_SET_OPTION_C:g} C (labelled option, not the baseline): head_afe_budget.md section 3.2 shows the lowest usable BETA_LLD falling "
                      "with temperature (8-9 p.e. at +10 C, 7-8 at -20 C) and crosstalk-limited below about 0 C, so +5 C costs no threshold against +10 C; "
                      "+5 C is also inside the +5..+10 C bond-line range assumed for the OEM modules (head_report.md section 8). It is NOT chosen as the "
                      "baseline because the OEM carrier / bond-line limits are unknown (no OEM drawing) and the project uses +10 C.")
    return out


OEM_DEPENDENT = [
    ("Module plan size (assumed 80.6 x 100.6 nominal, band 80.2..80.9 x 100.2..100.9)", "EDGE (0.5 per side), cavity 81.0 x 101.0, seat shoulder 0.5 mm", "side shims 0.1 / 0.25 mm; below 80.2 the seat shadows the edge or the module must hang from the pad"),
    ("Floor assembly thickness (assumed 5.25: screen 0.25 + guide 5.0)", "seat z 11.0, lower spacer ring 1.75", "ring thickness is a printed part: re-print for 4.5..6.5 mm"),
    ("Barrier / particle-stop allowance (assumed 2.0 at z 18..20)", "barrier plate 2.0, shelf of the chimney insert", "plate 1..3 mm by re-printing the two rings"),
    ("Reference assembly thickness (assumed 5.5: tile 0.5 + guide 5.0)", "upper ring 3.0, reference top z 28.5", "pad 1.0 / 1.5 / 2.0 mm + 0.25 / 0.5 / 1.0 shims: total stack 16.0..18.0 mm accepted (nominal 17.5)"),
    ("SiPM carrier size and position (assumed 13 x 5 x 1.5 at the rear guide edge, lane centre, x 78.6..80.1)", "chimney 18 wide x 7.9 deep, insert fingers at +-5.2..8.1, carrier band +-1.0 in y, +-0.5 in z, 1.0..2.0 thick",
     "chimney insert is a small printed part: re-print for another carrier; the frame chimney takes carriers up to 16 x 6 x 2.5"),
    ("SiPM connector / pigtail (assumed two micro-coax per SiPM, U.FL class, exit upward)", "coax channel 5 x 2.5 in the insert, 18 mm spreader notch, bend radius 6 mm to the board rear edge", "a side-exit connector needs a deeper chimney (not available: 7.9 mm)"),
    ("Entrance plane definition and permissible window load", "film on the cassette at z 10.00, three 0.8 mm guard webs under the film", "cassette is the only part to change (webs, film, aperture)"),
    ("Module mass (assumed 50 g floor, 52 g reference)", "mass / CG, dummy ballast, pad preload (about 6 N per lane)", "ballast thickness is computed from the measured mass"),
    ("Module retention force / permissible clamp load on the guides", "pad compression 0.3 mm of 1.5 mm (silicone foam, about 6 N per lane)", "softer pad or thicker shim"),
    ("Optical seal of the carrier to the guide edge (opaque potting assumed)", "light paths L12, L13", "black foam plug at the coax notch; dark-count cross-talk test"),
    ("Thermal limits of the bond lines (heater set-point +5..+10 C assumed)", "heater on the spreader, 1.5 W/cm2 max film", "set-point is firmware"),
]


# ------------------------------------------------------------------------------------------------ rail-switch harness reach (S2-L6)
def harness_routes(fp):
    """Lead length from each D2HW to its board connector along the routing of production/README.md section 6 (calculated, mm): side switches up the
    potted channel (11 mm), along the side strip to the front strip (x 180), along the front strip, 5 mm into the GH-4; front / lid switch along the
    front strip. Connector positions from the board file (J2002 F, J2003 L, J2004 R per design/circuit.py loop order; J2201 lid)."""
    def at(ref):
        r = fp[ref]
        return 83.2 + r["v"], 163.0 - r["u"]
    sw = {"front (J2002)": ((183.25, H.SHOE_Y), "J2002", False), "left (J2003)": ((H.XR + 3.6, H.SW_SIDE["y"]), "J2003", True),
          "right (J2004, S2-L6 u 144.6)": ((H.XR + 3.6, -H.SW_SIDE["y"]), "J2004", True), "lid (J2201)": ((183.25, -H.SHOE_Y), "J2201", False)}
    out = {}
    for name, ((x, y), ref, side) in sw.items():
        cx, cy = at(ref)
        if side:
            length = 11.0 + (180.0 - x) + abs(y - cy) + (180.0 - cx) + 5.0
        else:
            length = abs(y - cy) + abs(x - cx) + 5.0
        out[name] = {"connector_base_xy": (round(cx, 1), round(cy, 1)), "route_mm": round(length, 0)}
    # the right switch to the edge of the old landing (u 150 = y 13.0) for comparison
    out["right switch to the stage-1 landing edge (u 150)"] = {"route_mm": round(11.0 + (180.0 - H.XR - 3.6) + abs(-H.SW_SIDE["y"] - 13.0) + (180.0 - 175.2) + 5.0, 0)}
    return out
