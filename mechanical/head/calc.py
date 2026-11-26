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
        ("isolator / bond shim", 0.5, 0.05, 0.02, "G10 sheet / aluminium shim; selectable 0.40 / 0.50 / 0.60 for trimming"),
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


# ------------------------------------------------------------------------------------------------ thermal (lumped)
def thermal():
    """Steady-state UA of the head as designed (lid 2 mm Al + 0.5 mm liner, printed walls, no side foam) -- same film coefficients
    as mechanical/common/calc/thermal.py so the numbers compare with mech_calcs.md section 7."""
    out = {}
    a_top = (H.XF - H.XR) * 2 * H.YW / 1e6
    a_side = 2 * ((H.XF - H.XR) + 2 * H.YW) * (H.Z_LID1 - H.Z_FB) / 1e6
    a_win = 4 * H.ACT_X * H.ACT_Y / 1e6
    a_bot = a_top - a_win
    for label, hext, wall_k, wall_t in (("prototype, still air", 12.0, 0.30, 0.0026), ("prototype, draught 3 m/s", 25.0, 0.30, 0.0026),
                                        ("production, still air", 12.0, 160.0, 0.0026), ("production, draught 3 m/s", 25.0, 160.0, 0.0026)):
        r_in = 1 / 6.0
        liner = 0.0005 / 0.035
        for jacket in (0.0, 0.003):
            r_top = 1 / hext + liner + r_in + jacket / 0.035
            ua_top = a_top / r_top
            ua_side = a_side / (1 / hext + wall_t / wall_k + r_in + (0.0 if wall_k < 5 else 0.0))
            ua_win = a_win / (1 / 8.0 + 0.001 / 0.024 + 0.0055 / 0.19 + 1 / 8.0)        # floor-facing: low coefficient, air gap, guide
            ua_bot = a_bot / (1 / 8.0 + 0.004 / wall_k + r_in)
            ua = ua_top + ua_side + ua_win + ua_bot + 0.06
            out[f"{label}, {'3 mm external jacket' if jacket else 'no jacket'}"] = {
                "UA_W_per_K": ua, "heater_W_at_-20C_setpoint_+5C": max(ua * 25 - 5.0, 0), "heater_W_at_-25C_setpoint_+10C": max(ua * 35 - 5.0, 0),
                "split": {"top": ua_top, "sides": ua_side, "windows": ua_win, "underside": ua_bot, "mount+cables": 0.06}}
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
