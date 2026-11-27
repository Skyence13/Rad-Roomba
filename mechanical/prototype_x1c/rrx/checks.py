"""Automated checks of the RR-X build (tool-checked on the nominal CAD solids with the OCC kernel) and the calculated
mass / CG / tip / hang / grip proof-load results.  Reuses the ray, containment and sweep tools of mechanical.common.layout."""
from __future__ import annotations

import fnmatch
import itertools
import math
import time

import cadquery as cq
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

from mechanical.common import layout as LY
from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import dims as D
from . import shells
from .export import mass_of
from .util import box, cyl, place

# purchased envelopes that pass through / seat in a printed wall BY DESIGN (the envelope body is larger than the cut-out)
THROUGH_SKIN = ("*_operator", "*_body", "*_receptacle", "*_mated_plug", "charge_inlet", "tof_*", "bumper_sw_*", "head_dock_switch")
SHELL_GROUPS = {"lower_hull", "lid", "hatch", "service_cover"}
INTERNAL = ("battery_tunnel", "battery_cassette", "cassette_lid", "coupler_*", "battery_pack", "cm5_tray", "CM5_carrier_assembly", "bridge_tray", "bridge_post_*",
            "board_standoff_*", "RR-CHS-MAIN_*", "RR-PANEL", "panel_tray", "grip_foot_*", "chassis_heater_pad", "bus_clamp_resistor", "cassette_handle")
ROBOT_EXCLUDE = {"tray", "cassette_option", "head_placeholder"}
G = 9.81
CR04_GRIP_X = -30.0          # requested grip bar centre (CHANGE_REQUESTS.md CR-04), for the comparison column only
SLIVER_MAX = 100.0           # mm3: largest boolean sliver that may be dropped from a printed/fabricated part


def _match(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


REAL = ("printed", "fabricated")


def is_mate(a, b):
    if a.kind in REAL and b.kind in REAL:          # two real parts may touch, never overlap
        return False
    for p, q in ((a, b), (b, a)):
        pats = [m for m in p.mates if m != "*"]
        if "*" in p.mates and _match(q.name, THROUGH_SKIN):
            return True
        if _match(q.name, pats):
            return True
    return False


def interference(parts, vol_tol=5.0, log=print):
    from .interference import overlaps
    from .util import CACHE
    hard = [p for p in parts if p.hard and p.group != "tray"]
    byn = {p.name: p for p in hard}
    t0 = time.time()
    rows = overlaps(hard, CACHE.parent / "_interference", log=log)
    clash, declared = [], []
    for a, b, v, method, dt in rows:
        if not v <= vol_tol:
            (declared if is_mate(byn[a], byn[b]) else clash).append((a, b, round(v, 1), method))
    slow = sorted(((dt, a, b, m) for a, b, v, m, dt in rows), reverse=True)[:5]
    log(f"  interference: {len(rows)} candidate pairs, {len(clash)} clash(es), {len(declared)} declared envelope overlaps, {time.time() - t0:.0f} s")
    return {"pairs_evaluated": len(rows), "clashes": sorted(clash, key=lambda c: -c[2] if c[2] == c[2] else 0), "declared_overlaps": sorted(declared, key=lambda c: -c[2]),
            "methods": {m: sum(1 for r in rows if r[3] == m) for m in {r[3] for r in rows}}, "slowest_pairs_s": slow}


def containment(parts):
    class _P:   # view accepted by layout.containment
        def __init__(self, p):
            self.name, self.shape, self.internal, self.hard = p.name, p.shape, True, True
    B = P.BATTERY_BAY
    hx, hy, hz, hw = B["hump_x"], B["hump_half_y"], B["hump_z"], B["hump_wall"]
    pods = [cyl(P.DRIVE_POD["inner_r"], 2 * (P.WHEEL_Y + 5), (0, -(P.WHEEL_Y + 5), P.MOTOR_AXIS_Z), (0, 1, 0)),
            box(hx[0] - 12, hx[1] - hw, -hy + hw, hy - hw, hz[0] - 5, hz[1] - hw)]
    sel = [_P(p) for p in parts if _match(p.name, INTERNAL)]
    bad = LY.containment(sel, shells.UI(), shells.LI(), pods)
    return {"checked": [p.name for p in sel], "outside": bad}


def floor_contact(parts):
    z = {p.name: round(p.bb[2], 3) for p in parts if p.name.startswith("tyre_") or p.name == "caster"}
    low = sorted((round(p.bb[2], 1), p.name) for p in parts if p.group not in ROBOT_EXCLUDE and p.group != "tray" and not p.name.startswith(("tyre_", "caster")))[:5]
    return {"contact_z": z, "ok": all(abs(v) < 0.05 for v in z.values()), "lowest_other_parts": low}


def sensor_rays(parts):
    hard = [p for p in parts if p.group != "tray" and p.name != "spacer_9ah"]
    probes = {}
    for p in hard:
        it = IntCurvesFace_ShapeIntersector()
        it.Load(p.shape.wrapped, 1e-5)
        probes[p.name] = it
    s0 = P.TOF_SENSORS["tof_look_fl"]["xyz"]
    aim = P._unit((P.ROW_X - s0[0], 60.0 - s0[1], 40.0 - s0[2]))
    st = [h[0] for h in LY.ray_hits(probes, s0, aim, 600.0, skip=("tof_look_fl",))]
    if "head_envelope" not in st:
        raise RuntimeError(f"ray tool self-test failed: {st}")
    rows, fail = [], []
    for name, t in P.TOF_SENSORS.items():
        s, d = t["xyz"], P._unit(t["dir"])
        own = (name, "tof_window_" + name[4:], "tof_clip_" + name[4:])
        reach = min(P.TOF_MAX_RANGE, s[2] / -d[2] - 0.1) if d[2] < -1e-6 else P.TOF_MAX_RANGE
        centre = LY.ray_hits(probes, s, d, reach, skip=own)
        edge = {}
        for e in LY.cone_dirs(d, P.TOF_FOV_FULL_DEG / 2):
            r = min(P.TOF_MAX_RANGE, s[2] / -e[2] - 0.1) if e[2] < -1e-6 else P.TOF_MAX_RANGE
            for hn, hd in LY.ray_hits(probes, s, e, r, skip=own)[:1]:
                edge[hn] = min(hd, edge.get(hn, 1e9))
        rows.append({"sensor": name, "centre_ray_hits": centre, "cone_edge_hits": edge})
        if centre:
            fail.append((name, centre))
    lx, ly = P.LIDAR_POSE["xy"]
    lz = P.LIDAR_POSE["base_z"] + P.LIDAR_SCAN_PLANE_ABOVE_BASE
    blocked = []
    for deg in range(-135, 136, 3):
        d = (math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0)
        h = [x for x in LY.ray_hits(probes, (lx, ly, lz), d, 2000.0, skip=("lidar",)) if x[1] > 31.0]
        if h:
            blocked.append((deg, h[0]))
    return {"self_test": "ray aimed at the head hits head_envelope", "tof": rows, "tof_centre_blocked": fail, "lidar_scan_z": lz, "lidar_blocked": blocked,
            "ok": not fail and not blocked}


def service(parts):
    B, Gp, S = P.BATTERY_BAY, P.GRIP, P.SADDLE
    robot = [p for p in parts if p.group != "tray" and p.name != "spacer_9ah"]
    out = {}
    cx0, cx1 = B["cassette_x"]
    out["battery_removal_sweep"] = {"what": "cassette envelope swept 165 mm along -x; door, centre bumper and coupler removed/unmated",
                                    "blocked_by": LY.box_free(robot, (cx0 - B["removal_travel"], cx1, -B["cassette_half_y"], B["cassette_half_y"], B["cassette_z"][0] + 0.05, B["cassette_z"][1]),
                                                              skip=("cassette", "hatch_door", "bumper_centre", "coupler_fixed", "hatch_latch", "cassette_plunger"))}
    for tag, s in (("L", 1), ("R", -1)):
        y0, y1 = sorted((s * (P.WHEEL_Y + P.TYRE_WIDTH / 2 + 0.5), s * (P.WHEEL_Y + P.TYRE_WIDTH / 2 + 60)))
        out[f"wheel_{tag}_axial_removal"] = {"what": "104 mm disc swept 60 mm outboard", "blocked_by": LY.box_free(robot, (-P.WHEEL_R, P.WHEEL_R, y0, y1, 0.5, P.WHEEL_D))}
    he = P.HEAD_ENV_E
    out["head_removal_sweep_+x"] = {"what": "head envelope swept 66 mm forward", "blocked_by": LY.box_free(robot, (D.HEAD_X1 + 0.5, D.HEAD_X1 + 66, he["y"][0], he["y"][1], he["z"][0], he["z"][1]))}
    sx0, sx1 = S["x"]
    out["service_cover_lift"] = {"what": "cover lifted straight up to the underside of the grip bar (45 mm), then slid forward over the nose",
                                 "blocked_by": LY.box_free(robot, (sx0 + 0.4, sx1 - 0.4, -S["half_y"] + 0.4, S["half_y"] - 0.4, S["floor_z"][1] + 0.1, Gp["bar_bottom_z"] - 0.5))}
    gx0, gx1 = Gp["center_x"] - Gp["bar_x"] / 2, Gp["center_x"] + Gp["bar_x"] / 2
    c = P.GLOVE_CLEARANCE_GRIP
    out["grip_hand_zone"] = {"what": "45 mm in front of, behind and below the bar, 130 mm wide (same boxes as layout.py)",
                             "blocked_by": LY.box_free(robot, (gx0 - c, gx1 + c, -65, 65, S["floor_z"][1] + 0.1, Gp["bar_bottom_z"] - 0.1))
                             + LY.box_free(robot, (gx0 - c, gx0 - 0.1, -65, 65, Gp["bar_bottom_z"], Gp["bar_top_z"] + 30))
                             + LY.box_free(robot, (gx1 + 0.1, gx1 + c, -65, 65, Gp["bar_bottom_z"], Gp["bar_top_z"] + 30))}
    for jn, key in (("J1", "j1_receptacle"), ("J2", "j2_receptacle")):
        j, ej = P.J_RECEPTACLES[jn], L.env(key)
        zone = place(cyl(ej["plug_nut_d"] / 2 + P.GLOVE_CLEARANCE_CONNECTOR, ej["plug_nut_l"], (0, 0, 2.0)).cut(cyl(ej["plug_nut_d"] / 2 + 0.2, ej["plug_nut_l"] + 2, (0, 0, 1.0))), j["xyz"], j["normal"])
        zb = LY.bounds(zone)
        blocked = []
        for p in robot:
            if p.name in (f"{jn}_receptacle", f"{jn}_mated_plug") or any(p.bb[i] > zb[i + 3] or zb[i] > p.bb[i + 3] for i in range(3)):
                continue
            v = sum(s.Volume() for s in zone.intersect(p.shape).Solids())
            if v > 1.0:
                blocked.append((p.name, round(v)))
        out[f"{jn}_glove_zone"] = {"what": f"annulus {P.GLOVE_CLEARANCE_CONNECTOR:.0f} mm round the coupling nut, all solids incl. the skin", "blocked_by": blocked}
    ci = P.CHARGE_INLET
    probe = cq.Solid.makeSphere(22.5, cq.Vector(*(ci["xyz"][k] + 45 * ci["normal"][k] for k in range(3))))
    out["charge_inlet_glove_zone"] = {"what": "45 mm sphere in front of the opened inlet (cover swung up)", "blocked_by": [(p.name, 0) for p in robot if p.group != "charge" and p.name != "rear_deck_R"
                                                                                                                        and not any(p.bb[i] > LY.bounds(probe)[i + 3] or LY.bounds(probe)[i] > p.bb[i + 3] for i in range(3))
                                                                                                                        and sum(s.Volume() for s in probe.intersect(p.shape).Solids()) > 1.0]}
    from .battery import HANDLE_L, HANDLE_X
    out["handle_glove_gap"] = {"what": "finger gap between the pulled-out handle bar and the cassette rear face (calculated from the model dimensions)",
                               "value_mm": HANDLE_L - 4.0 - (P.BATTERY_BAY["cassette_x"][0] - HANDLE_X[1]), "required_mm": 45.0}
    out["handle_glove_gap"]["ok"] = out["handle_glove_gap"]["value_mm"] >= 45.0
    return out


def chin_rule(parts):
    """Interface rule: nothing of the body below z = 50 ahead of x = 62 except the latch (and the x-stop / deflector exceptions)."""
    xc, zc = P.RECEIVER["chin_cut"]
    probe = box(xc + 0.05, 200, -200, 200, 0, zc - 0.05)
    hits = []
    for p in parts:
        if p.group in ROBOT_EXCLUDE or p.group == "tray" or p.bb[3] <= xc + 0.05 or p.bb[2] >= zc - 0.05:
            continue
        v = sum(s.Volume() for s in probe.intersect(p.shape).Solids())
        if v > 0.5:
            hits.append((p.name, round(v), round(p.bb[3], 1)))
    allowed = ("head_latch", "receiver_channel_*", "land_pin_*", "J?_mated_plug")
    return {"parts_in_the_zone": hits, "allowed": allowed, "ok": all(_match(h[0], allowed) for h in hits),
            "note": "receiver flange = the x-stop pads of datum A (x 59.7..65.7); land pin at x = 62 +- 2"}


def receiver_check(parts):
    RC = P.RECEIVER
    byn = {p.name: p for p in parts}
    rows = []

    def row(item, req, meas, tol=0.011):
        ok = abs(meas - req) <= tol if isinstance(req, (int, float)) else bool(meas)
        rows.append({"item": item, "required": req, "measured": round(meas, 3) if isinstance(meas, float) else meas, "ok": ok})
    for tag, s in (("L", 1), ("R", -1)):
        ch, shoe = byn[f"receiver_channel_{tag}"], byn[f"head_shoe_{tag}"]
        pins = [byn[f"land_pin_{tag}{i}"] for i in (0, 1)]
        row(f"{tag} datum A: channel front face x", RC["x_stop"], ch.bb[3])
        row(f"{tag} channel rear x", RC["channel_x"][0], ch.bb[0])
        row(f"{tag} channel z bottom", RC["channel_z"][0], ch.bb[2])
        row(f"{tag} channel z top (under the beam)", RC["channel_z"][1], ch.bb[5])
        row(f"{tag} datum C: land (dowel) top z", RC["z_datum"], max(p.bb[5] for p in pins))
        for i, x in enumerate(RC["land_x"]):
            row(f"{tag} land {i} centre x", x, (pins[i].bb[0] + pins[i].bb[3]) / 2)
        row(f"{tag} land centre line y", s * RC["shoe_y"], (pins[0].bb[1] + pins[0].bb[4]) / 2)
        d = cq.Shape.distance(shoe.shape, ch.shape) if hasattr(cq.Shape, "distance") else shoe.shape.distance(ch.shape)
        row(f"{tag} smallest shoe-to-channel gap (fit at the stations)", min(D.RX_FIT_Y_LEFT if s > 0 else D.RX_FLOAT_Y_RIGHT, D.RX_FIT_Z), float(d), 0.012)
        v = sum(q.Volume() for q in shoe.shape.intersect(ch.shape).Solids())
        row(f"{tag} shoe / channel interference volume (mm3)", 0.0, float(v), 0.01)
        row(f"{tag} shoe rests on both lands (distance)", 0.0, float(max(shoe.shape.distance(p.shape) for p in pins)), 0.001)
        probe = box(30.0, 40.0, s * RC["shoe_y"] - 20, s * RC["shoe_y"] + 20, RC["shoe_z"][0] + 2, RC["shoe_z"][1] - 2)   # away from the stations
        free = probe.cut(ch.shape)
        ys = LY.bounds(max(free.Solids(), key=lambda q: q.Volume()))
        row(f"{tag} running clearance each side away from the lands", RC["channel_clear"], (ys[4] - ys[1] - RC["shoe_width"]) / 2)
    sw = byn["head_dock_switch"]
    row("HEAD_DOCK switch body centre y", P.HEAD_DOCK_SWITCH[1], (sw.bb[1] + sw.bb[4]) / 2)
    row("HEAD_DOCK switch body centre z", P.HEAD_DOCK_SWITCH[2], (sw.bb[2] + sw.bb[5]) / 2)
    row("HEAD_DOCK switch body centre x (plunger +x, push pin through the channel end wall)", P.HEAD_DOCK_SWITCH[0], (sw.bb[0] + sw.bb[3]) / 2, 0.3)
    lt = byn["head_latch"]
    row("latch envelope x0", RC["latch_box"][0], lt.bb[0])
    row("latch envelope z0", RC["latch_box"][4], lt.bb[2])
    return {"rows": rows, "ok": all(r["ok"] for r in rows)}


# ----------------------------------------------------------------------------------------------- calculated
LUMPED = [   # not modelled as solids; values from the common mass budget (estimates)
    ("harness (power, sensor, Ethernet, USB)", 0.450, -60.0, 0.0, 85.0), ("fasteners, inserts, standoffs", 0.250, -60.0, 0.0, 70.0),
    ("foam liner 5 mm + gaskets", 0.150, -97.0, 0.0, 80.0), ("RR-TOF harness ends, NTCs, cut-out, vent, light pipes", 0.040, -120.0, 0.0, 95.0)]
HEADS = {   # (kg, x, z) incl. pigtails: mechanical/head/out/head_report.md section 3 (calculated by the head engineer, 2026-11-26)
    "none (transport / LAB)": None,
    "prototype head RR-HD-X (1.864 kg)": (1.864, 118.4, 34.5),
    "production head (2.083 kg)": (2.083, 119.9, 32.9),
    "production head + 15 % margin": (2.396, 119.9, 32.9)}
HEAD_PROTO = "prototype head RR-HD-X (1.864 kg)"


def mass_cg(parts):
    items, m, mx, my, mz = [], 0.0, 0.0, 0.0, 0.0
    groups = {}
    for p in parts:
        if p.group in ROBOT_EXCLUDE or p.group == "tray":
            continue
        mp = mass_of(p)
        if mp <= 0:
            continue
        c = p.centroid()
        m, mx, my, mz = m + mp, mx + mp * c.x, my + mp * c.y, mz + mp * c.z
        g = groups.setdefault(p.group, [0.0, 0.0, 0.0])
        g[0] += mp
        g[1] += mp * c.x
        g[2] += mp * c.z
        items.append((p.name, round(mp, 4), round(c.x, 1), round(c.z, 1)))
    for name, mp, x, y, z in LUMPED:
        m, mx, my, mz = m + mp, mx + mp * x, my + mp * y, mz + mp * z
        groups["lumped: " + name] = [mp, mp * x, mp * z]
    base = {"mass": m, "x": mx / m, "y": my / m, "z": mz / m}
    Lc = -(P.CASTER_SWIVEL[0] - L.env("caster")["offset"])
    gx, gz = P.GRIP["center_x"], (P.GRIP["bar_bottom_z"] + P.GRIP["bar_top_z"]) / 2
    cfg = []
    for hn, h in HEADS.items():
        M, X, Z = m, mx, mz
        if h:
            M, X, Z = M + h[0], X + h[0] * h[1], Z + h[0] * h[2]
        x, z = X / M, Z / M
        caster = M * G * (-x) / Lc
        slope = math.tan(math.radians(5.0))
        fwd = -(x + z * (P.A_DECEL / G + slope))
        rear = (x + Lc) - z * (P.A_MAX / G + slope)
        nrm = math.hypot(Lc, P.WHEEL_Y)
        lat = abs((0 - x) * P.WHEEL_Y / nrm * 1.0 - 0.0) if False else (P.WHEEL_Y * (x + Lc) / nrm) - z * slope
        cfg.append({"head": hn, "mass_kg": round(M, 2), "cg_x": round(x, 1), "cg_z": round(z, 1), "caster_N": round(caster, 1), "each_wheel_N": round((M * G - caster) / 2, 1),
                    "caster_fraction": round(caster / (M * G), 3), "tip_margin_forward_mm": round(fwd, 1), "tip_margin_rearward_mm": round(rear, 1), "tip_margin_lateral_mm": round(lat, 1),
                    "hang_angle_deg": round(math.degrees(math.atan2(x - gx, gz - z)), 1),
                    "hang_angle_deg_CR04_bar_x-30": round(math.degrees(math.atan2(x - CR04_GRIP_X, gz - z)), 1)})
    return {"base_without_head": {k: round(v, 2) for k, v in base.items()}, "groups": {k: {"mass_kg": round(v[0], 3), "x": round(v[1] / v[0], 1), "z": round(v[2] / v[0], 1)} for k, v in sorted(groups.items())},
            "items": items, "configurations": cfg, "mass_goal_kg": P.MASS_GOAL_KG,
            "assumptions": "printed parts: CAD volume x density x effective fill (dims.MAT); purchased: parts.yaml masses; lumped items from the common budget; evidence class: calculated"}


def _plate_half_width(x):
    from .structure import plate_outline
    pts = plate_outline()
    ys = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (x0 - x) * (x1 - x) <= 0 and x0 != x1:
            ys.append(abs(y0 + (y1 - y0) * (x - x0) / (x1 - x0)))
    hw = max(ys) if ys else 0.0
    if D.BEAM_X[0] <= x <= D.BEAM_X[1]:
        hw = max(hw, D.BEAM_HALF_Y)
    return hw


def plate_bending(M):
    """Chassis plate as a beam when the robot hangs on the grip: everything is lifted through the two foot lines
    (x -56..-22); the plate carries the masses ahead of and behind them in bending.  -> rows (calculated)."""
    items = [(m, x) for _, m, x, _ in M["items"]] + [(m, x) for _, m, x, _, _ in LUMPED]
    head = HEADS[HEAD_PROTO]
    items.append((head[0], head[1]))
    t = D.PLATE_Z[1] - D.PLATE_Z[0]
    rows = []
    for xs, side in ((-60.0, "aft"), (-90.0, "aft"), (-140.0, "aft"), (-15.0, "fore"), (30.0, "fore")):
        sel = [(m, x) for m, x in items if (x < xs if side == "aft" else x > xs)]
        Mb = sum(m * G * D.GRIP_FACTOR * abs(x - xs) for m, x in sel)        # N mm, 3 x g
        w = 2 * _plate_half_width(xs)
        x0, x1, hy = D.BAY_WINDOW
        if x0 <= xs <= x1:
            w -= 2 * hy
        if abs(xs - P.CASTER_SWIVEL[0]) < D.CASTER_HOLE_R:
            w -= 2 * D.CASTER_HOLE_R
        sig = 6 * Mb / (w * t * t)
        rows.append((f"chassis plate bending at x = {xs:.0f} ({side} masses {sum(m for m, _ in sel):.2f} kg x 3 g; net width {w:.0f} mm x {t:.0f} mm, shells and tunnel ignored)",
                     round(sig, 1), "MPa", "allow 240 (6061-T6) -> SF %.1f" % (240 / sig if sig else 99)))
    return rows


def grip_proof(M=None):
    W = D.GRIP_DESIGN_MASS * G * D.GRIP_FACTOR
    Pside = W / 2
    od = D.GRIP_BAR_D
    I = math.pi * od ** 4 / 64
    span = D.GRIP_PLATE_Y[0] + D.GRIP_PLATE_Y[1]            # between plate mid-planes
    hand = 100.0
    Mb = Pside * (span / 2 - hand / 4)
    s_tube = Mb * (od / 2) / I
    defl = (W * span ** 3 / (48 * 68900 * I)) * 0.75          # distributed over the hand: ~0.75 of the point-load value
    tp = D.GRIP_PLATE_Y[1] - D.GRIP_PLATE_Y[0]
    leg_w = 9.0
    e = abs(D.GRIP_BAR_X - (-26.5))
    s_leg = Pside / (leg_w * tp) + 6 * Pside * e / (tp * leg_w ** 2)
    s_cheek = Pside / ((D.GRIP_PLATE_FRONT_X - (-21.0) - D.CLEAR["M6"]) * tp)
    bear = Pside / (6.0 * tp)
    tau6 = Pside / 20.1                                     # M6 shank/thread section in shear (friction ignored)
    a_toe, b_bolt = (D.GRIP_PLATE_Y[0] - 1.5) - (D.GRIP_PLATE_Y[0] - 25.0), 71.0 - (D.GRIP_PLATE_Y[0] - 25.0)
    T = Pside * a_toe / b_bolt / 2
    As5 = 14.2
    s_angle = 6 * Pside * ((D.GRIP_PLATE_Y[0] - 1.5) - 71.0) / (34.0 * 3.0 ** 2)
    pull_through = math.pi * 9.2 * 2.0 * 0.6 * 240.0          # csk head through the remaining 2 mm of 6061-T6 (shear 0.6 x 240)
    ins = 600.0                                              # N, M3 brass heat-set insert in ASA, typical static pull-out (UNVERIFIED, test coupon required)
    lid_screws = 16
    rows = [
        ("design load = 3 x 9 kg x g", round(W, 1), "N", ""),
        ("load per side plate", round(Pside, 1), "N", ""),
        ("bar 14 mm solid 6061-T6: bending stress (hand 100 mm, span %.0f mm)" % span, round(s_tube, 1), "MPa", "allow 240 (0.2 % proof, T6) -> SF %.1f" % (240 / s_tube)),
        ("bar mid-span deflection", round(defl, 2), "mm", ""),
        ("side plate leg 9 x 6 6061-T6: tension + bending from the %.1f mm offset" % e, round(s_leg, 1), "MPa", "allow 240 -> SF %.1f" % (240 / s_leg)),
        ("side plate net section at the M6 bar-screw hole (cheek x -21..%.0f)" % D.GRIP_PLATE_FRONT_X, round(s_cheek, 1), "MPa", "SF %.0f" % (240 / s_cheek)),
        ("M6 bar screw bearing on the 6 mm plate", round(bear, 1), "MPa", "allow 300"),
        ("M6 bar screw shear (friction ignored)", round(tau6, 1), "MPa", "A2-70 shear ~ 270 -> SF %.0f" % (270 / tau6)),
        ("M5 through-bolt tension at the foot (prying about the angle toe, 2 bolts)", round(T, 1), "N", "A2-70 proof 450 MPa x 14.2 mm2 = %.0f N -> SF %.0f" % (450 * As5, 450 * As5 / T)),
        ("angle foot 3 mm leg bending", round(s_angle, 1), "MPa", "allow 150 (6060-T6) -> SF %.1f" % (150 / abs(s_angle))),
        ("M5 countersunk head pull-through in the 4 mm plate", round(pull_through, 0), "N capacity", "SF %.0f" % (pull_through / T)),
        ("inserts in the lifting path", 0, "-", "none: bar -> 2 x M6 into the tapped bar ends -> side plates -> angle feet -> M5 through-bolts with nyloc nuts -> chassis plate"),
        ("misuse case: whole 3 x weight hung on the lid (16 perimeter M3 inserts in shear/pull-out)", round(W / lid_screws, 1), "N per insert", "typ. pull-out %.0f N (UNVERIFIED) -> SF %.0f" % (ins, ins / (W / lid_screws))),
    ]
    ok_plate = True
    if M is not None:
        pr = plate_bending(M)
        rows += pr
        ok_plate = all(r[1] < 240 / 1.5 for r in pr)
    return {"rows": rows, "ok": s_tube < 160 and s_leg < 240 and abs(s_angle) < 150 and ok_plate,
            "cold_note": "6061/6060-T6 and A2 fasteners gain strength at -25 C and stay ductile; no polymer is in the lifting path. Proof test: 3 x weight for 60 s warm and at -20 C (VT-002)."}


def width_rule(parts):
    """Shared rule 8.3: nothing on the body wider than the tyres (|y| <= WHEEL_Y + TYRE_WIDTH / 2)."""
    lim = P.WHEEL_Y + P.TYRE_WIDTH / 2 + 0.01
    over = [(p.name, round(max(-p.bb[1], p.bb[4]), 2)) for p in parts
            if p.group not in ROBOT_EXCLUDE and p.group != "tray" and max(-p.bb[1], p.bb[4]) > lim]
    return {"limit_half_width_mm": round(lim, 2), "over": over, "ok": not over}


def corridors(parts):
    robot = [p for p in parts if p.group not in ROBOT_EXCLUDE and p.group != "tray"]
    return {k: {"box": list(b), "use": use, "blocked_by": LY.box_free(robot, b)} for k, (b, use) in LY.CORRIDORS.items()}


def ccr_e08(parts):
    """CCR-E08 (chassis electronics): 12 mm clear height over the rear corners and the front-centre strip of RR-CHS-MAIN,
    and room for the mated right-angle Mini-Fit (J_PWR, right edge rear u = 160, v 8..31) with its 2-into-1 loom."""
    b = P.CHS_MAIN
    ox, oy, oz = b["origin"]
    top = oz + b["thickness"]

    def uv_box(u0, u1, v0, v1, z0, z1):
        return (ox + v0, ox + v1, oy - u1, oy - u0, z0, z1)
    zones = {"rear-left corner u 0-45, v 0-20, 12 mm above the PCB": uv_box(0, 45, 0, 20, top + 0.05, top + 12.0),
             "rear-right corner u 112-160, v 0-22, 12 mm above the PCB": uv_box(112, 160, 0, 22, top + 0.05, top + 12.0),
             "front-centre strip u 40-120, v 80-100, 12 mm above the PCB (strip extent ASSUMED)": uv_box(40, 120, 80, 100, top + 0.05, top + 12.0),
             "J_PWR mated plug + loom: u 160..183 (23 mm beyond the right edge), v 7..32, PCB top .. +14 mm": uv_box(160, 183, 7, 32, top - 1.5, top + 14.0),
             "rear-edge connector space u 0..18 and 142..160 behind the board (x -79..-67), z PCB .. +12 mm (IB-12)": None}
    robot = [p for p in parts if p.group not in ROBOT_EXCLUDE and p.group != "tray" and not p.name.startswith("RR-CHS-MAIN")]
    out = {}
    for k, bx in zones.items():
        if bx is None:
            blk = LY.box_free(robot, (ox - 12.0, ox - 0.05, oy - 18.0, oy, top, top + 12.0)) + LY.box_free(robot, (ox - 12.0, ox - 0.05, oy - 160.0, oy - 142.0, top, top + 12.0))
            out[k] = {"blocked_by": blk}
        else:
            out[k] = {"box": [round(v, 1) for v in bx], "blocked_by": LY.box_free(robot, bx)}
    return out


def slivers(parts):
    rows = [(p.name, p.dropped) for p in parts if p.dropped]
    return {"dropped": rows, "ok": all(max(d) <= SLIVER_MAX for _, d in rows)}


def run_all(parts, table, log=print):
    R = {}
    R["interference"] = interference(parts, log=log)
    t = time.time()
    R["containment"] = containment(parts)
    R["floor"] = floor_contact(parts)
    R["rays"] = sensor_rays(parts)
    R["service"] = service(parts)
    R["chin_rule"] = chin_rule(parts)
    R["receiver"] = receiver_check(parts)
    log(f"  containment / floor / rays / sweeps / receiver: {time.time() - t:.0f} s")
    R["bed_fit"] = [{"part": r["name"], "pn": r["pn"], "bbox_print": r["bbox_print"], "verdict": r["bed_fit"], "note": r["bed_note"], "open_edges": r.get("open_edges")}
                    for r in table if r["kind"] == "printed"]
    R["width_rule"] = width_rule(parts)
    R["corridors"] = corridors(parts)
    R["ccr_e08"] = ccr_e08(parts)
    R["slivers"] = slivers(parts)
    R["mass_cg"] = mass_cg(parts)
    R["grip"] = grip_proof(R["mass_cg"])
    svc_block = {k: v["blocked_by"] for k, v in R["service"].items() if v.get("blocked_by")}
    worst_fit = [r for r in R["bed_fit"] if r["verdict"] == "NO"]
    leaks = [r["part"] for r in R["bed_fit"] if r["open_edges"]]
    R["summary"] = {
        "no interference among real parts and purchased envelopes": [not R["interference"]["clashes"], f"{len(R['interference']['clashes'])} clash(es) in {R['interference']['pairs_evaluated']} pairs; {len(R['interference']['declared_overlaps'])} declared through-wall envelope overlaps"],
        "internals inside the shell cavity": [not R["containment"]["outside"], f"{len(R['containment']['checked'])} parts checked, {len(R['containment']['outside'])} outside"],
        "wheels and caster on the floor": [R["floor"]["ok"], str(R["floor"]["contact_z"])],
        "ToF centre rays and LiDAR plane clear": [R["rays"]["ok"], f"blocked ToF {R['rays']['tof_centre_blocked']}; LiDAR bearings blocked {len(R['rays']['lidar_blocked'])}"],
        "removal sweeps and glove zones": [not svc_block and R["service"]["handle_glove_gap"]["ok"], "free" if not svc_block else str(svc_block)],
        "nothing below z = 50 ahead of x = 62 except latch / datum A": [R["chin_rule"]["ok"], str(R["chin_rule"]["parts_in_the_zone"])],
        "receiver interface matches mechanical_interfaces.md": [R["receiver"]["ok"], f"{sum(r['ok'] for r in R['receiver']['rows'])}/{len(R['receiver']['rows'])} items"],
        "every printed part fits the X1C bed in its print orientation": [not worst_fit, f"{len(R['bed_fit'])} parts; marginal: {[r['part'] for r in R['bed_fit'] if r['verdict'] == 'MARGINAL']}; no-fit: {[r['part'] for r in worst_fit]}"],
        "printed-part meshes watertight": [not leaks, "all closed" if not leaks else f"open edges in {leaks}"],
        "grip proof-load calculation (3 x 9 kg)": [R["grip"]["ok"], "calculated"],
        "nothing wider than the tyres (295 mm)": [R["width_rule"]["ok"], "none over" if R["width_rule"]["ok"] else str(R["width_rule"]["over"])],
        "cable corridors of the master layout free": [not any(v["blocked_by"] for v in R["corridors"].values()), (str({k: v["blocked_by"] for k, v in R["corridors"].items() if v["blocked_by"]}) if any(v["blocked_by"] for v in R["corridors"].values()) else "all free")],
        "CCR-E08 keep-outs over RR-CHS-MAIN free": [not any(v["blocked_by"] for v in R["ccr_e08"].values()), (str({k[:30]: v["blocked_by"] for k, v in R["ccr_e08"].items() if v["blocked_by"]}) if any(v["blocked_by"] for v in R["ccr_e08"].values()) else "all free")],
        "boolean slivers dropped from parts below %.0f mm3" % SLIVER_MAX: [R["slivers"]["ok"], str(R["slivers"]["dropped"]) if R["slivers"]["dropped"] else "none"],
    }
    return R
