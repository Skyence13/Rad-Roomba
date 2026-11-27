"""RR-X shells: the approved rounded Rev E skin (P.BODY_ROWS, unchanged) split for the 256 mm bed.

Pieces (all outer surfaces are the common skin law; every piece is thicker inward only):
  lower hull   FL FR RL RR      z 33..61.9, split at x = D.X_LOWER and y = 0, sole ring on the chassis plate
  nose cowl    one piece        upper skin x >= 47 + lower lip x >= 62 + chin floor (slides on over the latch arm)
  lid          shoulder L/R (x -45..47), rear deck L/R (x <= -45), battery hump (separate, coaming joint)
  saddle cover service cover over RR-CHS-MAIN;  hatch frame + tail-cap door
Joints: perimeter lap (tongue on the hull inside the lid skirt, gasket on the 1.78 mm land gap), bolted internal
flanges with 1 mm flat gasket at the vertical splits, coaming at the hump, face gasket at the hatch frame."""
from __future__ import annotations

import math

import cadquery as cq

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import dims as D
from . import sensors as S
from .structure import CHEEK_X0, LATCH_ARM_X1, LATCH_ARM_Z, LATCH_SCREW_X, plate_blank, plate_outline, sole_screw_xy
from .util import Part, V, biggest, box, cached, cut, cyl, fuse, inset_rows, loft, mirror_y, place, prism

R = P.BODY_ROWS
B = P.BATTERY_BAY
SAD = P.SADDLE
Z1 = D.PLATE_Z[1]
ZL, ZU = D.SPLIT_Z_LOWER_TOP, D.SPLIT_Z_UPPER_BOT
GAP = 0.25                      # each vertical joint face is set back by this (0.5 mm for the 1 mm gasket, compressed)
LEDGE_Z = (102.6, SAD["floor_z"][0])
HUMP_X = (B["hatch_x"][1], B["hump_x"][1])          # hump shortened to the hatch frame plane (deviation D-03)
FRAME_X = (B["hump_x"][0], B["hatch_x"][1])         # hatch frame ring -233..-230
FRAME_OPEN_HY = 55.2                                # clear opening of the frame (cassette |y| <= 54.5)
FRAME_SCREW_Y = 57.8                                # frame -> tunnel end-boss screws (inside the 60.4 frame edge)
PERIM_DEG = {"nose": (20.0, 40.0), "shoulder": (50.0,), "deck": (85.0, 100.0, 120.0, 140.0)}   # shoulder station clear of the motor pod (x +-26)


# ----------------------------------------------------------------------------------------------- base solids (cached)
def UO():
    return cached(["UO", R["upper_outer"]], lambda: loft(R["upper_outer"]))


def UI():
    return cached(["UI", R["upper_inner"]], lambda: loft(R["upper_inner"]))


def LO():
    return cached(["LO", R["lower_outer"]], lambda: loft(R["lower_outer"]))


def LI():
    return cached(["LI", R["lower_inner"]], lambda: loft(R["lower_inner"]))


def UINS():
    return cached(["UINS", R["upper_inner"], D.FLANGE_DEPTH], lambda: loft(inset_rows(R["upper_inner"], D.FLANGE_DEPTH)))


def skin_upper():
    return cached(["SKIN_U", R["upper_outer"], R["upper_inner"]], lambda: UO().cut(UI()))


def skin_lower():
    return cached(["SKIN_L", R["lower_outer"], R["lower_inner"]], lambda: LO().cut(LI()))


def gap_fill():
    """Solid ring between the lower land (61.9) and the upper land (63.68): used where a piece spans the split."""
    def b():
        g = loft([R["lower_outer"][-1], R["upper_outer"][0]])
        return g.cut(UI()).cut(LI())
    return cached(["GAPFILL", R["lower_outer"][-1], R["upper_outer"][0]], b)


def tongue_ring():
    c, t, h = D.TONGUE
    def b():
        a = loft(inset_rows(R["upper_inner"], c, 0.0))
        i = loft(inset_rows(R["upper_inner"], c + t, 0.0))
        return box(-400, 200, -200, 200, ZL, ZL + h).intersect(a).cut(i).intersect(scaled_xy(UI(), 1.0 - c / 120.0))   # >= ~0.3 mm inside the lid skin everywhere
    return cached(["TONGUE", 3, R["upper_inner"], D.TONGUE, ZL], b)


def scaled_xy(shape, f):
    """Shape scaled by f in x and y about the body section centre (x = mid of tail and nose, y = 0); z unchanged."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform
    from OCP.gp import gp_GTrsf, gp_Mat, gp_XYZ
    cx = (P.BODY_TAIL_X + P.BODY_NOSE_X) / 2
    g = gp_GTrsf(gp_Mat(f, 0, 0, 0, f, 0, 0, 0, 1), gp_XYZ(cx * (1 - f), 0, 0))
    return cq.Shape.cast(BRepBuilderAPI_GTransform(shape.wrapped, g, True).Shape())


def skin_frame(theta_deg, z, surface="inner", part="upper"):
    """Point on a skin ring and the outward horizontal-ish normal there."""
    row = P._interp_row(R[f"{part}_{surface}"], z)
    t = math.radians(theta_deg)
    p = P.ring_point(row, t)
    a, b = P.ring_point(row, t - 0.01), P.ring_point(row, t + 0.01)
    tx, ty = b[0] - a[0], b[1] - a[1]
    n = P._unit((ty, -tx, 0.0))
    return p, n


def perim_stations():
    out = []
    for grp, degs in PERIM_DEG.items():
        for dg in degs:
            for sgn in (1, -1):
                p, n = skin_frame(sgn * dg, ZL + 5.5)
                out.append((grp, sgn, p, n))
    return out


SPLICE_Z = 44.0                 # lower-hull splice screw height: below the CM5 deck (z 49.5)


def bumper_switch_seat(s):
    """D2HW seat at the body bumper switch: (block, holes) in base_link; s = +1 left, -1 right."""
    sw = P.BODY_BUMPER_SWITCHES["bumper_sw_" + ("l" if s > 0 else "r")]
    d = D.BUMPER_DIR["L" if s > 0 else "R"]
    n = (-d[0], -d[1], 0.0)
    blk = place(box(-10, 10, -9, 9, -12.0, -1.0), sw, n)
    hole = place(fuse(box(-6.9, 6.9, -2.9, 2.9, -11.0, -3.6), cyl(1.7, 12, (0, 0, -4.0)), cyl(2.6, 20, (-14.0, 0, -8.0)), cyl(2.6, 20, (14.0, 0, -8.0))), sw, n)
    return blk, hole


def tongue_keepout():
    """Hull tongue + its insert bosses (+0.3): the lid pieces are cut by it so they only touch the hull at the land."""
    def b():
        k = tongue_ring()
        for g, sgn, pt, n in perim_stations():
            q = tuple(pt[i] - n[i] * D.TONGUE[0] for i in range(3))
            k = k.fuse(place(cyl(4.7, 8.1, (0, 0, -7.8)), q, n))
        return k
    return cached(["TONGUE_KEEP", 3, R["upper_inner"], D.TONGUE, ZL, PERIM_DEG], b)


def arch_cut():
    return [cyl(P.WHEEL_ARCH_R, 60, (0, s * P.WHEEL_ARCH_INNER_Y, P.AXLE_Z), (0, s, 0)) for s in (1, -1)]


def arch_liner():
    out = None
    for s in (1, -1):
        y0 = s * (P.WHEEL_ARCH_INNER_Y - 3.0)
        a = cyl(P.WHEEL_ARCH_R + 3.0, 63, (0, y0, P.AXLE_Z), (0, s, 0)).cut(cyl(P.WHEEL_ARCH_R, 60, (0, s * P.WHEEL_ARCH_INNER_Y, P.AXLE_Z), (0, s, 0)))
        out = a if out is None else out.fuse(a)
    return out


def pod_cut():
    return [cyl(P.DRIVE_POD["outer_r"] + 0.3, 60, (0, s * 80.0, P.MOTOR_AXIS_Z), (0, s, 0)) for s in (1, -1)]


# ----------------------------------------------------------------------------------------------- masters (cached)
def upper_master():
    def b():
        sx0, sx1 = SAD["x"]
        hy = SAD["half_y"]
        w = D.WELL_WALL
        sh = UO().cut(UI())
        well = box(sx0 - w, sx1 + w, -hy - w, hy + w, LEDGE_Z[0], 220).cut(box(sx0, sx1, -hy, hy, 0, 300)).intersect(UO())
        ledge = box(sx0, sx1, -hy, hy, *LEDGE_Z).cut(box(sx0 + 7, sx1 - 7, -hy + 7, hy - 7, 90, 110))
        liner = arch_liner().intersect(UO())
        sh = sh.fuse(well).fuse(ledge).fuse(liner)
        jamb = box(-400, FRAME_X[0], D.HATCH_JAMB[0], D.HATCH_JAMB[1], ZU, 160).intersect(UO())
        sh = sh.fuse(jamb).fuse(jamb.mirror("XZ"))
        sh = cut(sh, box(sx0, sx1, -hy, hy, LEDGE_Z[1], 300), *arch_cut(), *pod_cut(),
                 box(HUMP_X[0] - 3.3, SAD["x"][0], -B["hump_half_y"] - 0.3, B["hump_half_y"] + 0.3, 90, 300),
                 box(-400, B["hatch_x"][1], -B["hatch_half_y"], B["hatch_half_y"], B["hatch_z"][0], 200))
        for s in (1, -1):                                          # slots for the grip side plates through the shoulder roof
            sh = sh.cut(box(CHEEK_X0 - 0.5, D.GRIP_PLATE_FRONT_X + 0.5, s * D.GRIP_PLATE_Y[0] - 0.4 * s, s * D.GRIP_PLATE_Y[1] + 0.4 * s, 90, 220))
        return sh.clean()
    return cached(["upper_master", 9, CHEEK_X0, D.GRIP_PLATE_FRONT_X, R, SAD, B, D.GRIP_PLATE_Y, LEDGE_Z, D.HATCH_JAMB, P.DRIVE_POD, P.WHEEL_ARCH_INNER_Y], b)


def lower_master():
    def b():
        sh = LO().cut(LI())
        ring_in = prism(plate_outline(D.PLATE_INSET + 10.0), Z1 - 2, Z1 + 6)
        sole = box(-400, 200, -200, 200, Z1, Z1 + 4.0).intersect(LO()).cut(ring_in)
        liner = arch_liner().intersect(LO())
        jamb = box(-400, FRAME_X[0], D.HATCH_JAMB[0], D.HATCH_JAMB[1], B["hatch_z"][0], ZL).intersect(LO())
        sh = sh.fuse(sole).fuse(liner).fuse(jamb).fuse(jamb.mirror("XZ")).fuse(tongue_ring())
        sh = cut(sh, ring_in, plate_blank(0.25, Z1 - 8, Z1), *arch_cut(), *pod_cut(),
                 box(P.RECEIVER["chin_cut"][0], 200, -200, 200, 0, P.RECEIVER["chin_cut"][1]),
                 box(P.RECEIVER["chin_cut"][0], 200, -200, 200, ZL, ZL + 30),                       # no tongue under the one-piece nose
                 box(-400, B["hatch_x"][1], -B["hatch_half_y"], B["hatch_half_y"], B["hatch_z"][0], 200),
                 box(FRAME_X[0], FRAME_X[1] + 0.3, -70, 70, Z1 + 1.2, 200))                          # hatch frame seat
        for s in (1, -1):                                          # reliefs for parts that stand on the plate edge
            sh = cut(sh, box(-27.0, 27.0, s * (D.POD_Y0 - 0.5), s * 125.0, Z1 - 0.1, Z1 + 9.3),
                     box(D.FOOT_X[0] - 1, D.FOOT_X[1] + 1, s * 60.0, s * (D.GRIP_PLATE_Y[1] + 0.6), Z1 - 0.1, Z1 + 26.5))
        sh = cut(sh, *internal_clearance())
        return sh.clean()
    return cached(["lower_master", 13, R, D.PLATE_INSET, D.BEAM_X, D.BEAM_HALF_Y, B, D.TONGUE, D.HATCH_JAMB, D.POD_Y0, D.FOOT_X, D.GRIP_PLATE_Y, P.RECEIVER["chin_cut"]], b)


def internal_clearance():
    """Envelopes (+0.5 mm) of internal parts standing on the plate that the hull sole ring / tongue must clear."""
    from .battery import tunnel  # noqa: F401  (geometry reference: the tunnel footprint below)
    c = P.CM5_POSE
    tools = [box(D.TUNNEL_X[0] - 0.5, D.TUNNEL_X[1] + 3.5, -69.5, 69.5, Z1 - 0.1, Z1 + 9.0).intersect(LI()),   # tunnel feet, gate, floor (inside the skin only)
             box(c["x"][0] - 2.5, c["x"][1] + 0.5, c["y"][0] - 0.5, c["y"][1] + 0.3, Z1 - 0.1, c["pcb_z"] + 21.5)]   # CM5 tray + carrier
    for s in (1, -1):
        tools.append(cyl(19.0, 80.0, (0, s * 40.0, P.MOTOR_AXIS_Z), (0, s, 0)))                                # gearmotor can
    for x, y in D.POSTS:
        tools.append(cyl(4.6, 10.0, (x, y, Z1 - 0.1)))                                                         # bridge posts
    from .structure import front_bulkhead
    tools.append(front_bulkhead())                                                                             # bulkhead + latch-arm pedestals
    return tools


def flange(plane, pos, side, region):
    """Internal bolted flange at a vertical split plane. plane 'x' or 'y'; side +1: material on the + side.
    Clipped by the wheel arches, motor-pod openings, saddle opening and grip slots (the master has them; the flange must too)."""
    a, b_ = (pos + GAP, pos + GAP + D.FLANGE_T) if side > 0 else (pos - GAP - D.FLANGE_T, pos - GAP)
    slab = box(a, b_, -200, 200, 0, 220) if plane == "x" else box(-400, 200, a, b_, 0, 220)
    f = slab.intersect(region).intersect(box(-400, 200, -200, 200, ZL + D.TONGUE[2] + 0.5, 300)).intersect(UI()).cut(UINS())   # above the hull tongue
    return cut(f, *arch_cut(), *pod_cut(), box(SAD["x"][0], SAD["x"][1], -SAD["half_y"], SAD["half_y"], LEDGE_Z[0], 300),
               box(SAD["x"][0], SAD["x"][1] + D.WELL_WALL + 1.0, -70.0, 70.0, 0, LEDGE_Z[0]))     # nothing over the board's front connectors (u 10..150) below the ledge


def insert_boss_x(x_face, y, z, side, m="M3"):
    """Boss + insert bore on a flange (insert axis along x, opening at the joint face)."""
    d, l = D.INSERT[m]
    x0 = x_face + side * GAP
    boss = cyl(d / 2 + 2.2, l + 1.5, (x0, y, z), (side, 0, 0))
    bore = cyl(d / 2, l, (x0 - side * 0.01, y, z), (side, 0, 0))
    return boss, bore


DOWELS = {"nose": {"zs_side": (81.0,)}, "deck": {"zs_side": (108.0,), "ys_roof": (95.0,)}}
DECK_JOINT = {"zs_side": (100.0,), "ys_roof": (104.0,)}      # x = X_DECK screws: above the wheel arch (r 56 reaches z 93 at x -38); no screw at z 116: its boss would reach the grip side plate


def dowel_bores(x, key, sgn=1):
    """3 mm x 8 alignment dowels across a vertical lid joint (4.2 mm deep each side)."""
    return _union([cyl(1.5, 8.4, (x - 4.2, y, z), (1, 0, 0)) for (y, z) in x_joint_points(x, sgn=sgn, **DOWELS[key])])


def x_joint_points(x, ys_roof=(), zs_side=(), sgn=1):
    """Fastener points 4.5 mm inside the inner skin at station x: on the flank at heights zs, on the roof at |y| ys."""
    pts = [(sgn * (P.half_breadth(x, z, "inner") - 4.6), z) for z in zs_side]
    pts += [(sgn * y, P.roof_z(x, y, "inner") - 4.6) for y in ys_roof]
    return pts


# ----------------------------------------------------------------------------------------------- lid pieces
def _union(shapes):
    out = None
    for sh in shapes:
        out = sh if out is None else out.fuse(sh)
    return out


def _features(piece, feats, skin=None):
    """feats: (add, cut) or (add, cut, trim). trim=True (default) clips the added solid to the outer skin.
    All adds are united first and clipped/fused once, all cuts are united and cut once (two booleans on the skin)."""
    skin = UO() if skin is None else skin
    trim = _union([f[0] for f in feats if f[0] is not None and (len(f) < 3 or f[2])])
    free = _union([f[0] for f in feats if f[0] is not None and len(f) == 3 and not f[2]])
    if trim is not None:
        piece = piece.fuse(trim.intersect(skin))
    if free is not None:
        piece = piece.fuse(free)
    tool = _union([f[1] for f in feats if f[1] is not None])
    return piece.cut(tool) if tool is not None else piece


def perim_screws(piece, grp, sgns=(1, -1)):
    """Radial M3 clearance holes + 7 mm spot faces through the lid skirt at the perimeter stations."""
    tool = _union([place(fuse(cyl(D.CLEAR["M3"] / 2, 14, (0, 0, -4)), cyl(3.6, 6, (0, 0, 4.2))), p, n)
                   for g, sgn, p, n in perim_stations() if g == grp and sgn in sgns])
    return piece.cut(tool) if tool is not None else piece


def _nose_lip_chin():
    """Lower lip and chin floor of the one-piece nose (below the split line, ahead of the chin cut)."""
    xc = P.RECEIVER["chin_cut"][0]
    lip = LO().cut(LI()).fuse(gap_fill()).intersect(box(xc + GAP, 200, -200, 200, P.RECEIVER["chin_cut"][1], ZU + 0.01))
    chin = box(xc - 4.0, 200, -200, 200, P.RECEIVER["chin_cut"][1], LATCH_ARM_Z[0]).intersect(LO()).cut(box(xc - 5, xc + GAP, -200, 200, 0, 300))
    return lip, chin


def _nose_details(n):
    """J1/J2 receptacle seats, latch screw holes through the chin floor and the latch-arm pocket (shared by both builds)."""
    feats = []
    for jn, key in (("J1", "j1_receptacle"), ("J2", "j2_receptacle")):
        j, e = P.J_RECEPTACLES[jn], L.env(key)
        a, c, _ = S.device_seat(j["xyz"], j["normal"], hole_d=e["flange_d"] - 4 + 0.3, face_d=e["flange_d"] + 6.0, boss_d=e["flange_d"] + 10.0, notch=False, panel_t=3.5)
        feats.append((a, c))
    n = _features(n, feats)
    for x in LATCH_SCREW_X:                                      # latch screws pass through the chin floor into the arm
        for y in (-7.0, 7.0):
            n = n.cut(cyl(D.CLEAR["M4"] / 2, 8, (x, y, P.RECEIVER["chin_cut"][1] - 1)))
    return n.cut(box(P.RECEIVER["chin_cut"][0] - 5.0, LATCH_ARM_X1 + 0.5, -12.8, 12.8, LATCH_ARM_Z[0], LATCH_ARM_Z[1] + 0.3))   # arm pocket, open rearward (cowl slides on)


def nose_cowl():
    def b():
        xc = P.RECEIVER["chin_cut"][0]
        up = upper_master().intersect(box(D.X_NOSE + GAP, 200, -200, 200, 0, 300))
        lip = LO().cut(LI()).fuse(gap_fill()).intersect(box(xc + GAP, 200, -200, 200, P.RECEIVER["chin_cut"][1], ZU + 0.01))
        chin = box(xc - 4.0, 200, -200, 200, P.RECEIVER["chin_cut"][1], LATCH_ARM_Z[0]).intersect(LO()).cut(box(xc - 5, xc + GAP, -200, 200, 0, 300))
        fl = flange("x", D.X_NOSE, +1, box(0, 200, -200, 200, 0, 300)).cut(box(0, 200, -SAD["half_y"] - D.WELL_WALL, SAD["half_y"] + D.WELL_WALL, 0, 300))
        n = _union([up, lip, chin, fl])
        n = _nose_details(n)
        for sgn in (1, -1):                                          # joint to the shoulders: M3 clearance + dowel
            for (y, z) in x_joint_points(D.X_NOSE, zs_side=(74.0, 88.0), sgn=sgn):
                n = n.cut(cyl(D.CLEAR["M3"] / 2, 12, (D.X_NOSE - 1, y, z), (1, 0, 0)))
        n = n.cut(dowel_bores(D.X_NOSE, "nose", 1)).cut(dowel_bores(D.X_NOSE, "nose", -1))
        n = perim_screws(n, "nose").cut(tongue_keepout())
        n = n.cut(cyl(4.0, 12, (58.0, 0.0, LEDGE_Z[0] + 8.0), (1, 0, 0)))                                   # J1/J2 lead pass to the board front edge
        return n
    return cached(["nose_cowl", 16, DOWELS, R, D.X_NOSE, P.J_RECEPTACLES, LATCH_ARM_Z, PERIM_DEG, LATCH_ARM_X1, LATCH_SCREW_X], b)


def shoulder(s):
    def b():
        reg = box(D.X_DECK + GAP, D.X_NOSE - GAP, 0.0, 200, 0, 300)
        p = upper_master().intersect(reg)
        p = _union([p, flange("x", D.X_NOSE, -1, reg), flange("x", D.X_DECK, +1, reg)])
        for (y, z) in x_joint_points(D.X_NOSE, zs_side=(74.0, 88.0)):
            bo, br = insert_boss_x(D.X_NOSE, y, z, -1)
            p = p.fuse(bo.intersect(UI())).cut(br)
        for (y, z) in x_joint_points(D.X_DECK, **DECK_JOINT):
            bo, br = insert_boss_x(D.X_DECK, y, z, +1)
            p = p.fuse(bo.intersect(UI())).cut(br)
        a, c = cover_bosses(reg)
        p = p.fuse(a).cut(c).cut(dowel_bores(D.X_NOSE, "nose")).cut(dowel_bores(D.X_DECK, "deck"))
        p = p.cut(box(CHEEK_X0, D.GRIP_PLATE_FRONT_X, D.GRIP_PLATE_Y[0] - 3.4, D.GRIP_PLATE_Y[0] - 0.3, 90, 220))     # look-ahead ToF lead slot beside the side plate (under the fairing)
        p = p.cut(tongue_keepout())
        return perim_screws(p, "shoulder", (1,))
    p = cached(["shoulder", 17, DECK_JOINT, DOWELS, R, D.X_NOSE, D.X_DECK, PERIM_DEG, COVER_SCREWS], b)
    return p if s > 0 else mirror_y(p)


HUMP_SCREW_X = (-212.0, -168.0, -124.0, -84.0)


def _deck_feats(p, s):
    """Seats and holes of one rear deck side (ToF, controls, panel tray, light pipes, inlet, bumper switch, door peg); returns (p, feats)."""
    tag = "l" if s > 0 else "r"
    feats = []
    for name in ("tof_look_rev_" + {"l": "left", "r": "right"}[tag], "tof_prox_r" + tag):
        t = P.TOF_SENSORS[name]
        k = S.seat_kind(name)
        feats.append((S.tof_boss(t["xyz"], t["dir"], k), S.tof_pocket(t["xyz"], t["dir"], kind=k), False))
    ctl = {"l": ("mode_selector", "rearm_start"), "r": ("estop", "hands_on", "pause_stop")}[tag]
    for name in ctl:
        c = P.PANEL_CONTROLS[name]
        a, cu, _ = S.device_seat(c["xyz"], c["normal"])
        feats.append((a, cu))
    if s > 0:
        pc = P.PANEL_CONTROLS["annunciator"]["xyz"]
        _, ztray = S.panel_tray()
        for sy in (-1, 1):
            x, y = pc[0], pc[1] + sy * S.PANEL_BOSS_DY
            feats.append((cyl(4.2, 60, (x, y, ztray)), cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x, y, ztray - 0.01))))
        for x, y in S.lightpipe_xy():
            feats.append((None, cyl(1.55, 60, (x, y, 100))))
        feats.append((None, cyl(4.0, 60, (pc[0] - 26.0, pc[1], 100))))                          # sounder port (membrane vent behind)
    else:
        ci = P.CHARGE_INLET
        a, cu, spot = S.inlet_seat()
        xd = S.inlet_xdir()
        p = p.cut(place(spot, ci["xyz"], ci["normal"], xd))                 # flat spot face: nothing of the skin above the seat plane
        feats.append((place(a, ci["xyz"], ci["normal"], xd).intersect(box(-400, 0, -200, 0, ZL + D.TONGUE[2] + 0.5, 300)), place(cu, ci["xyz"], ci["normal"], xd), False))
    feats.append((None, bumper_switch_seat(s)[1]))                          # switch block is on the lower hull; the lid skirt only gets the holes
    from .battery import DOOR_PEG
    feats.append((box(DOOR_PEG[0] - 5, DOOR_PEG[0] + 3.5, s * D.HATCH_JAMB[0], s * (D.HATCH_JAMB[1] + 6.5), DOOR_PEG[1] - 5.5, DOOR_PEG[1] + 5.5),
                  cyl(D.INSERT["M4"][0] / 2, D.INSERT["M4"][1] + 1.0, (DOOR_PEG[0], s * D.HATCH_JAMB[0], DOOR_PEG[1]), (0, s, 0))))
    return p, feats


def rear_deck(s):
    tag = "l" if s > 0 else "r"

    def base():
        reg = box(-400, D.X_DECK - GAP, 0.0, 200, 0, 300)
        p = upper_master().intersect(reg)
        curb = box(HUMP_X[0], HUMP_X[1], B["hump_half_y"] + 0.3, B["hump_half_y"] + 6.3, 0, 300).intersect(UI()).cut(UINS())
        p = _union([p, flange("x", D.X_DECK, -1, reg), curb])
        for (y, z) in x_joint_points(D.X_DECK, **DECK_JOINT):
            p = p.cut(cyl(D.CLEAR["M3"] / 2, 12, (D.X_DECK - 8, y, z), (1, 0, 0)))
        for x in HUMP_SCREW_X:
            z = P.roof_z(x, B["hump_half_y"] + 3.0, "inner") - 4.6
            p = p.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x, B["hump_half_y"] + 0.3, z), (0, 1, 0)))
        p = p.cut(dowel_bores(D.X_DECK, "deck")).cut(tongue_keepout())
        a, c = cover_bosses(reg)
        if a is not None:
            p = p.fuse(a).cut(c)
        return perim_screws(p, "deck", (1,))

    def b():
        p = cached(["rear_deck_base", 16, DECK_JOINT, DOWELS, R, D.X_DECK, HUMP_X, PERIM_DEG, COVER_SCREWS], base)
        p = p if s > 0 else mirror_y(p)
        p, feats = _deck_feats(p, s)
        return _features(p, feats).cut(tongue_keepout())                 # features (ToF seats) must clear the hull tongue too
    key = ["rear_deck", tag, 20, COVER_SCREWS, S.SEAT, R, D.X_DECK, HUMP_X, PERIM_DEG, P.TOF_SENSORS, P.PANEL_CONTROLS, P.CHARGE_INLET, D.BUMPER_DIR]
    if tag == "r":
        key.append(("inlet_seat", S.INLET_COVER_T, 2))
    return cached(key, b)


def hump():
    def b():
        hy, hz, hw = B["hump_half_y"], B["hump_z"], B["hump_wall"]
        x0, x1 = HUMP_X
        h = box(x0, x1, -hy, hy, hz[0], hz[1]).cut(box(x0 - 1, x1 - hw, -hy + hw, hy - hw, hz[0] - 1, hz[1] - hw))
        brow = box(B["hump_x"][0] - 4.0, B["hump_x"][0] + 8.0, -14.0, 14.0, hz[1], hz[1] + 16.0)
        t = P.TOF_SENSORS["tof_prox_rc"]
        front = box(x1, SAD["x"][0] - 0.2, -hy, hy, hz[0], hz[1])                                  # front wall thickened up to the saddle edge
        h = fuse(h, brow, front)                                                               # (the saddle-cover ledge belongs to the rear decks)
        for s in (1, -1):                                                                      # roof guide rails for the cassette
            h = h.fuse(box(x0 + 6, x1 - hw - 4, s * 30.0, s * 36.0, B["cassette_z"][1] + 0.6, hz[1] - hw))
        h = h.clean()
        h = h.cut(S.tof_pocket(t["xyz"], t["dir"]))
        h = h.cut(box(t["xyz"][0] + 2.0, B["hump_x"][0] + 6.0, -9.5, 9.5, hz[1] - hw - 1, hz[1] + 13.0))    # brow cavity, lead drops into the hump roof
        lx, ly = P.LIDAR_POSE["xy"]
        for sx in (-1, 1):
            for sy in (-1, 1):
                h = h.cut(cyl(D.CLEAR["M3"] / 2, 8, (lx + sx * 25.0, ly + sy * 25.0, hz[1] - hw - 1)))
        h = h.cut(cyl(6.0, 8, (lx + 38.0, ly, hz[1] - hw - 1)))                                 # LiDAR cable gland (M12)
        from .battery import PLUNGER_X
        h = h.cut(cyl(5.1, 8, (PLUNGER_X, 0.0, hz[1] - hw - 1)))                                 # cassette index plunger (M10 body, nut inside)
        for x in HUMP_SCREW_X:
            z = P.roof_z(x, hy + 3.0, "inner") - 4.6
            for s in (1, -1):
                h = h.cut(cyl(D.CLEAR["M3"] / 2, 6, (x, s * (hy - hw - 1), z), (0, s, 0)))
        for s in (1, -1):                                                                      # latch (top) + frame screws
            h = h.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x0 - 0.01, s * (hy - 1.5), 138.0), (1, 0, 0)))
        return h
    return cached(["hump", 12, S.SEAT, B, HUMP_X, LEDGE_Z, P.LIDAR_POSE, P.TOF_SENSORS["tof_prox_rc"], HUMP_SCREW_X], b)


# Captive cover screws: four at the front ledge (ahead of the board edge x 33) and two at the rear corners, where the boss
# underside (z 97.6, 13.0 mm above the PCB) stays above the 12 mm rear-corner zones of CCR-E08.  No screws over the rest
# of the board (its 18 mm top envelope reaches the ledge underside, z 102.6).
COVER_SCREWS = [(SAD["x"][1] - 3.5, y) for y in (-75.0, -20.0, 20.0, 75.0)] + [(SAD["x"][0] + 3.5, y) for y in (-75.0, 75.0)]


def saddle_cover():
    sx0, sx1 = SAD["x"]
    hy = SAD["half_y"]
    c = cq.Workplane("XY").add(box(sx0 + 0.4, sx1 - 0.4, -hy + 0.4, hy - 0.4, *SAD["floor_z"])).edges("|Z").fillet(2.0).val()
    for x, y in COVER_SCREWS:
        c = c.cut(cyl(D.CLEAR["M3"] / 2, 5, (x, y, SAD["floor_z"][0] - 1)))
    return c


def cover_bosses(reg):
    """Insert bosses under the ledge for the captive cover screws that fall inside region `reg` (-> add, cut)."""
    add, cu = None, None
    for x, y in COVER_SCREWS:
        bo = box(x - 4.5, x + 4.5, y - 3.5, y + 3.5, LEDGE_Z[0] - 5.0, LEDGE_Z[0])
        br = cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x, y, LEDGE_Z[1] - D.INSERT["M3"][1]))
        add = bo if add is None else add.fuse(bo)
        cu = br if cu is None else cu.fuse(br)
    add = add.intersect(reg)
    return (add if add.Solids() else None), cu


# ----------------------------------------------------------------------------------------------- lower hull pieces
def lower_piece(front, s):
    tag = ("F" if front else "R") + ("L" if s > 0 else "R")

    def base():
        reg = box(D.X_LOWER + GAP, P.RECEIVER["chin_cut"][0] - GAP, GAP, 200, 0, 300) if front else box(-400, D.X_LOWER - GAP, GAP, 200, 0, 300)
        p = lower_master().intersect(reg)
        # splice flange at the transverse split (z 41..61.9), bolted M3 + gasket
        slab = box(D.X_LOWER + GAP, D.X_LOWER + GAP + D.FLANGE_T, 0, 200, Z1 + 4.0, ZL) if front else box(D.X_LOWER - GAP - D.FLANGE_T, D.X_LOWER - GAP, 0, 200, Z1 + 4.0, ZL)
        fl = cut(slab.intersect(LI()).cut(loft(inset_rows(R["lower_inner"], D.FLANGE_DEPTH, 0.0))), *internal_clearance())
        p = p.fuse(fl).clean()
        # no splice screw: the x = -71 station lies in the CM5 bay (its clearance removes the flange there); the four lower
        # pieces are held by the plate sole screws and the lid tongue, the butt joint is sealed with RTV
        for x, yy in sole_screw_xy():                                    # M3 inserts in the sole ring (screws from below)
            if yy > 0 and ((x > D.X_LOWER) == front):
                p = p.cut(cyl(D.INSERT["M3"][0] / 2, 4.0, (x, yy, Z1 - 0.01)))
        for g, sgn, pt, n in perim_stations():                           # insert bosses on the tongue
            if sgn > 0 and ((pt[0] > D.X_LOWER) == front) and pt[0] < P.RECEIVER["chin_cut"][0]:
                q = tuple(pt[i] - n[i] * D.TONGUE[0] for i in range(3))
                p = p.fuse(place(cyl(4.4, 7.5, (0, 0, -7.5)), q, n).intersect(UI())).cut(place(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (0, 0, -D.INSERT["M3"][1])), q, n))
        return p.clean()

    def b():
        p = cached(["lower_base", front, 16, SPLICE_Z, R, D.X_LOWER, PERIM_DEG, D.TONGUE, D.POSTS, P.CM5_POSE], base)
        p = p if s > 0 else mirror_y(p)
        if not front:
            blk, hole = bumper_switch_seat(s)
            p = p.fuse(blk.intersect(LO()).intersect(box(-400, 200, -200, 200, 0, ZL + D.TONGUE[2]))).cut(hole)
            t = P.TOF_SENSORS["tof_cliff_r" + tag[1].lower()]
            p = p.fuse(S.tof_boss(t["xyz"], t["dir"]).intersect(LO())).cut(S.tof_pocket(t["xyz"], t["dir"]))
            if s < 0:                                                    # membrane breather (M12 x 1.5 ePTFE vent) in the right rear quarter
                pt, n = skin_frame(-136.0, 55.0, "outer", "lower")
                a, c, _ = S.device_seat(pt, n, hole_d=12.2, face_d=20.0, boss_d=24.0, notch=False, panel_t=4.0)
                p = p.fuse(a.intersect(LO())).cut(c)
        return p
    return cached(["lower_piece", tag, 17, S.SEAT, R, D.X_LOWER, PERIM_DEG, P.TOF_SENSORS, D.HATCH_JAMB], b)


# ----------------------------------------------------------------------------------------------- hatch frame and door
def hatch_frame():
    """Flat ring that is the gasket land of the door and ties tunnel, hump and jambs together.  Below the hump top it stays
    inside the jamb inner faces (|y| <= 60.4); its top bar is the rear end of the hump growth."""
    hy, hz = B["hump_half_y"], B["hump_z"]
    x0, x1 = FRAME_X
    f = box(x0, x1, -hy - 2.0, hy + 2.0, Z1 + 1.2, hz[1]).cut(box(x0 - 1, x1 + 1, -FRAME_OPEN_HY, FRAME_OPEN_HY, B["cassette_z"][0] - 0.1, 146.5))
    f = f.intersect(fuse(box(x0 - 1, x1 + 1, -60.4, 60.4, 0, 300), box(x0 - 1, x1 + 1, -100, 100, 146.0, 300)))
    for s in (1, -1):
        f = f.cut(cyl(D.CLEAR["M3"] / 2, 6, (x0 - 1, s * (hy - 1.5), 138.0), (1, 0, 0)))          # to the hump end
        for z in (48.0, 92.0):
            f = f.cut(cyl(D.CLEAR["M3"] / 2, 6, (x0 - 1, s * FRAME_SCREW_Y, z), (1, 0, 0)))      # to the tunnel wall end bosses
    return biggest(f.cut(skin_lower()))


def door():
    def b():
        hx = B["hatch_x"][1]
        hy = B["hatch_half_y"] - 0.3
        zb, zt = B["hatch_z"][0] + 0.3, B["hatch_z"][1] - 0.3
        skin = UO().cut(UI()).fuse(LO().cut(LI())).fuse(gap_fill())
        cap = skin.intersect(box(-400, FRAME_X[0] - 0.3, -hy, hy, zb, zt))                # stops at the frame face (gasket land)
        plate = box(FRAME_X[0] - 3.3, FRAME_X[0] - 0.3, -hy, hy, 100.0, B["hump_z"][1] - 0.5).cut(UI())
        plate = plate.cut(box(FRAME_X[0] - 4, FRAME_X[0], -55.0, 55.0, 90.0, 144.5))              # ring only: the folded handle lies inside it
        inside = UO().fuse(LO()).fuse(gap_fill())
        skirt = box(-400, FRAME_X[0] - 0.3, -hy + 0.2, hy - 0.2, 86.0, 142.0).cut(box(-401, FRAME_X[0], -55.0, 55.0, 30, 160)).intersect(inside)
        skirt = skirt.cut(box(-262.0, FRAME_X[0], -60.0, 60.0, 88.0, 114.0)).cut(box(-262.0, FRAME_X[0], -54.0, 54.0, 0.0, 300.0))   # relief for the look-behind ToF seats
        d = _union([cap, plate, skirt])
        d = d.fuse(box(-400, B["cassette_x"][0] - 0.5, -4.0, 4.0, 88.0, 100.0).intersect(inside))   # interlock finger: door closes only on a cassette that is home (= latched)
        from .battery import DOOR_PEG
        for s in (1, -1):                                                # hook-and-swing: the door is lowered onto the jamb pegs tilted back, then swung shut
            slot = box(DOOR_PEG[0] - 2.3, DOOR_PEG[0] + 2.3, s * 54.0, s * 58.5, 80.0, DOOR_PEG[1] + 2.3)   # hook slots, open downward
            d = d.cut(slot)
        for name in ("tof_look_rev_left", "tof_look_rev_right"):          # relief round the look-behind seats of the decks
            t = P.TOF_SENSORS[name]
            d = d.cut(S.tof_boss(t["xyz"], t["dir"], "look_r", grow=0.4, back=4.0))
        for y in (-30.0, 30.0):                                           # bushings for the centre bumper guide pins
            d = d.cut(cyl(2.6, 30, (P.BODY_TAIL_X - 3.0, y, 66.0), (1, 0, 0)))
        d = d.cut(cyl(D.CLEAR["M4"] / 2, 8, (FRAME_X[0] - 4.3, 35.0, 141.0), (1, 0, 0)))            # latch catch plate screws
        d = d.cut(cyl(D.CLEAR["M4"] / 2, 8, (FRAME_X[0] - 4.3, 35.0, 131.0), (1, 0, 0)))
        return d
    return cached(["door", 14, S.SEAT, R, B, FRAME_X], b)


# ----------------------------------------------------------------------------------------------- production build (RR_BUILD=production)
# One SLS PA11 piece for the whole lower hull and one for the whole lid (nose cowl + shoulders + rear decks + battery hump):
# no x = 47 / x = -38 / x = -71 / y = 0 joints, no joint flanges, dowels or inserts.  Every functional seat, the tongue, the
# perimeter screw stations (lid -> hull), the cover / hatch / door interfaces are the prototype features unchanged.
def lower_hull_one_piece():
    def base():
        p = lower_master().intersect(box(-400, P.RECEIVER["chin_cut"][0] - GAP, -200, 200, 0, 300))   # nose lip / chin belong to the lid
        for x, yy in sole_screw_xy():                                    # M3 inserts in the sole ring (screws from below)
            p = p.cut(cyl(D.INSERT["M3"][0] / 2, 4.0, (x, yy, Z1 - 0.01)))
        for g, sgn, pt, n in perim_stations():                           # insert bosses on the tongue (lid perimeter screws)
            if pt[0] < P.RECEIVER["chin_cut"][0]:
                q = tuple(pt[i] - n[i] * D.TONGUE[0] for i in range(3))
                p = p.fuse(place(cyl(4.4, 7.5, (0, 0, -7.5)), q, n).intersect(UI())).cut(place(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (0, 0, -D.INSERT["M3"][1])), q, n))
        return p.clean()

    def b():
        p = cached(["lower_one_base", 2, R, PERIM_DEG, D.TONGUE, D.POSTS, P.CM5_POSE], base)
        for s in (1, -1):
            tag = "L" if s > 0 else "R"
            blk, hole = bumper_switch_seat(s)
            p = p.fuse(blk.intersect(LO()).intersect(box(-400, 200, -200, 200, 0, ZL + D.TONGUE[2]))).cut(hole)
            t = P.TOF_SENSORS["tof_cliff_r" + tag.lower()]
            p = p.fuse(S.tof_boss(t["xyz"], t["dir"]).intersect(LO())).cut(S.tof_pocket(t["xyz"], t["dir"]))
        pt, n = skin_frame(-136.0, 55.0, "outer", "lower")              # membrane breather (M12 x 1.5 ePTFE vent), right rear quarter
        a, c, _ = S.device_seat(pt, n, hole_d=12.2, face_d=20.0, boss_d=24.0, notch=False, panel_t=4.0)
        return p.fuse(a.intersect(LO())).cut(c).clean()
    return cached(["lower_one", 2, S.SEAT, R, PERIM_DEG, P.TOF_SENSORS, D.HATCH_JAMB], b)


def upper_shell_one_piece():
    def base():
        up = upper_master()
        lip, chin = _nose_lip_chin()
        hy = B["hump_half_y"]
        x0, x1 = HUMP_X
        opening = box(HUMP_X[0], SAD["x"][0], -hy - 0.3, hy + 0.3, 90, 300)          # behind x0 the hatch frame owns the 3.3 mm gap
        ring = UO().cut(UI()).intersect(opening).cut(box(x0, x1, -hy, hy, 0, 300))     # skin strip between the hump walls and the deck opening
        ring = ring.cut(box(-400, B["hatch_x"][1], -B["hatch_half_y"], B["hatch_half_y"], B["hatch_z"][0], 200))
        n = _union([up, lip, chin, ring, hump()])
        n = _nose_details(n)
        a, c = cover_bosses(box(-400, 200, -200, 200, 0, 300))
        n = n.fuse(a).cut(c)
        for sg in (1, -1):                                               # look-ahead ToF lead slots beside the grip side plates (under the fairings)
            n = n.cut(box(CHEEK_X0, D.GRIP_PLATE_FRONT_X, sg * (D.GRIP_PLATE_Y[0] - 3.4), sg * (D.GRIP_PLATE_Y[0] - 0.3), 90, 220))
        n = n.cut(cyl(4.0, 12, (58.0, 0.0, LEDGE_Z[0] + 8.0), (1, 0, 0)))                                   # J1/J2 lead pass to the board front edge
        for grp in ("nose", "shoulder", "deck"):
            n = perim_screws(n, grp, (1, -1))
        return n.cut(tongue_keepout()).clean()

    def b():
        p = cached(["upper_one_base", 2, R, SAD, B, HUMP_X, LEDGE_Z, PERIM_DEG, COVER_SCREWS, P.J_RECEPTACLES, LATCH_ARM_Z, LATCH_ARM_X1, LATCH_SCREW_X], base)
        for s in (1, -1):
            p, feats = _deck_feats(p, s)
            p = _features(p, feats)
        return p.cut(tongue_keepout()).clean()
    return cached(["upper_one", 2, S.SEAT, R, P.TOF_SENSORS, P.PANEL_CONTROLS, P.CHARGE_INLET, D.BUMPER_DIR, ("inlet_seat", S.INLET_COVER_T, 2)], b)


def build(add):
    ASA = D.MAT["ASA"]["color"]
    hullc = "#3a4247"
    if D.PROD:
        add(Part("RRX-P20", "lower_hull", lower_hull_one_piece(), "printed", "ASA", "lower_hull", color=hullc, internal=False, mates={"*"}))
        add(Part("RRX-P22", "upper_shell", upper_shell_one_piece(), "printed", "ASA", "lid", color=ASA, internal=False, mates={"*"}))
        _build_covers(add, ASA)
        return
    for front in (True, False):
        for tag, s in (("L", 1), ("R", -1)):
            n = f"lower_hull_{'F' if front else 'R'}{tag}"
            add(Part(f"RRX-P2{0 if front else 1}{tag}", n, lower_piece(front, s), "printed", "ASA", "lower_hull", color=hullc, internal=False, hard=True,
                     orient=(180, 0, 0), print_note="upside-down: gasket land (z 61.9) on the bed, tongue hangs below -> print the tongue first on a 9 mm support raft OR use tree supports under the land; supports inside under the chine and sole ring",
                     mates={"*"}))
    add(Part("RRX-P22", "nose_cowl", nose_cowl(), "printed", "ASA", "lid", color=ASA, internal=False, orient=(0, 90, 0),
             print_note="standing on the rear joint face (x = 47 plane on the bed), nose tip up; tree supports under the lip step and inside the tip", mates={"*"}))
    for tag, s in (("L", 1), ("R", -1)):
        sh = shoulder(s)
        add(Part(f"RRX-P23{tag}", f"shoulder_{tag}", sh, "printed", "ASA", "lid", color=ASA, internal=False, orient=(0, -90, 0),
                 print_note="standing on the rear joint face (x = -38 plane on the bed); supports under the well ledge", mates={"*"}))
        add(Part(f"RRX-P24{tag}", f"rear_deck_{tag}", rear_deck(s), "printed", "ASA", "lid", color=ASA, internal=False, orient=(0, 0, 0),
                 print_note="as fitted (perimeter land on the bed); tree supports inside under the deck roof and sensor bosses", mates={"*"}))
    add(Part("RRX-P25", "battery_hump", hump(), "printed", "ASA", "lid", color=ASA, internal=False, orient=(0, 90, 0),
             print_note="standing on the front face (x = -69.2 plane on the bed), roof vertical; supports only under the brow", mates={"*"}))
    _build_covers(add, ASA)


def _build_covers(add, ASA):
    cov = saddle_cover()
    add(Part("RRX-P26", "saddle_cover", cov, "printed", "PAHT-CF", "service_cover", color="#33383c", internal=False, orient=(0, 0, 0), print_note="flat", mates={"*"}))
    add(Part("RRX-P27", "hatch_frame", hatch_frame(), "printed", "PAHT-CF", "battery_bay", color="#33383c", internal=False, orient=(0, 90, 0), print_note="flat (ring on the bed), no supports", mates={"*"}))
    add(Part("RRX-P28", "hatch_door", door(), "printed", "ASA", "hatch", color=ASA, internal=False, orient=(0, -90, 0),
             print_note="skirt/end-plate face (x = -233 plane) on the bed, tail apex up; tree supports inside under the apex", mates={"*"}))
