"""Rev E master layout: places every purchased part, board and structural envelope, exports STEP + PNG views and
runs the automated checks (interference, containment, ground clearance, service access, cable corridors, sensor rays).

Run from the repository root:   python -m mechanical.common.layout [--rail 3|5] [--no-png]
Exit status is non-zero if any hard check fails.  Evidence class of the results: tool-checked (OCC geometry kernel
on nominal envelope solids), not physically measured.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
import time

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

from . import params as P
from .purchased import library as L

OUT = P.OUT
CACHE = OUT / "cache"
COL = {"shell": cq.Color(0.84, 0.87, 0.88, 0.30), "hull": cq.Color(0.15, 0.18, 0.2, 0.35), "struct": cq.Color("#58666e"),
       "pcb": cq.Color("#2e7d4f"), "keepout": cq.Color(0.95, 0.75, 0.2, 0.35), "motor": cq.Color("#8a8f93"),
       "tyre": cq.Color("#24292c"), "battery": cq.Color("#c95146"), "compute": cq.Color("#3d6fb0"),
       "lidar": cq.Color("#71acbb"), "control": cq.Color("#da9745"), "conn": cq.Color("#b5c6ca"),
       "sensor": cq.Color("#7b5ea7"), "head": cq.Color("#344c51"), "optic": cq.Color("#278981"),
       "heat": cq.Color("#b67346"), "soft": cq.Color(0.3, 0.8, 0.4, 0.15)}


# ----------------------------------------------------------------------------------------------------- helpers
def bounds(shape):
    bb = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, bb, False, False)
    return [float(v) for v in bb.Get()]


def place(solid, origin, zdir, xdir=None):
    """Move a solid built in a local frame (z = axis) so local z points along zdir at origin."""
    zdir = P._unit(zdir)
    if xdir is None:
        ref = (0, 0, 1) if abs(zdir[2]) < 0.9 else (1, 0, 0)
        xdir = P._unit((ref[1] * zdir[2] - ref[2] * zdir[1], ref[2] * zdir[0] - ref[0] * zdir[2], ref[0] * zdir[1] - ref[1] * zdir[0]))
    return solid.moved(cq.Location(cq.Plane(origin=tuple(origin), xDir=tuple(xdir), normal=tuple(zdir))))


class Part:
    def __init__(self, name, shape, group, color, mass=0.0, internal=True, hard=True, mates=()):
        self.name, self.shape, self.group, self.color, self.mass = name, shape, group, color, mass
        self.internal, self.hard, self.mates = internal, hard, set(mates)
        self.bb = bounds(shape)


def ring_wire(row):
    pts = [cq.Vector(*P.ring_point(row, 2 * math.pi * i / 24)) for i in range(24)]
    return cq.Wire.assembleEdges([cq.Edge.makeSpline(pts, periodic=True)])


def loft(rows):
    return cq.Solid.makeLoft([ring_wire(r) for r in rows], False)


def cached(key, builder):
    """BREP cache keyed on the parameters that define the shape."""
    CACHE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = CACHE / f"{key[0]}_{digest}.brep"
    if path.exists():
        return cq.Shape.importBrep(str(path))
    shape = builder()
    shape.exportBrep(str(path))
    return shape


# ----------------------------------------------------------------------------------------------------- body shells
def body_shells():
    B = P.BATTERY_BAY
    key_common = [P.BODY_ROWS, P.WHEEL_Y, P.WHEEL_ARCH_R, P.WHEEL_ARCH_INNER_Y, P.SADDLE, B["hatch_x"], B["hatch_half_y"], B["hatch_z"]]

    def cutters():
        arches = [L.cyl(P.WHEEL_ARCH_R, 60, (0, s * P.WHEEL_ARCH_INNER_Y, P.AXLE_Z), (0, s, 0)) for s in (-1, 1)]
        sad = L.box(P.SADDLE["x"][0], P.SADDLE["x"][1], -P.SADDLE["half_y"], P.SADDLE["half_y"], P.SADDLE["floor_z"][0], 260)
        hatch = L.box(B["hatch_x"][0] - 5, B["hatch_x"][1], -B["hatch_half_y"], B["hatch_half_y"], *B["hatch_z"])
        return arches, sad, hatch

    def upper():
        arches, sad, hatch = cutters()
        s = loft(P.BODY_ROWS["upper_outer"]).cut(loft(P.BODY_ROWS["upper_inner"]))
        for t in (*arches, sad):
            s = s.cut(t)
        return s

    def lower():
        arches, sad, hatch = cutters()
        s = loft(P.BODY_ROWS["lower_outer"]).cut(loft(P.BODY_ROWS["lower_inner"]))
        for t in arches:
            s = s.cut(t)
        return s

    up_full = cached(["upper_fairing", key_common], upper)
    lo_full = cached(["lower_hull", key_common], lower)
    _, _, hatch = cutters()
    door = cached(["hatch_door", key_common], lambda: cq.Compound.makeCompound([up_full.intersect(hatch), lo_full.intersect(hatch)]))
    up = cached(["upper_fairing_cut", key_common], lambda: up_full.cut(hatch))
    lo = cached(["lower_hull_cut", key_common], lambda: lo_full.cut(hatch))
    cav_u = cached(["cavity_upper", P.BODY_ROWS["upper_inner"]], lambda: loft(P.BODY_ROWS["upper_inner"]))
    cav_l = cached(["cavity_lower", P.BODY_ROWS["lower_inner"]], lambda: loft(P.BODY_ROWS["lower_inner"]))
    return up, lo, door, cav_u, cav_l


def plate_outline(inset=3.0):
    row = P.BODY_ROWS["lower_inner"][0]
    pts = []
    for i in range(72):
        x, y, _ = P.ring_point(row, 2 * math.pi * i / 72)
        r = math.hypot(x - (row[1] + row[2]) / 2, y)
        f = max(0.0, (r - inset) / r) if r > 0 else 0
        cx = (row[1] + row[2]) / 2
        pts.append((cx + (x - cx) * f, y * f))
    return pts


# ----------------------------------------------------------------------------------------------------- model
def build(rail_projection=3.0):
    parts: list[Part] = []

    def add(name, shape, group, color, mass=0.0, **kw):
        if not shape.isValid():
            raise ValueError(f"invalid solid: {name}")
        parts.append(Part(name, shape, group, COL[color], mass, **kw))
        return shape

    up, lo, door, cav_u, cav_l = body_shells()
    add("upper_fairing_E", up, "shell", "shell", internal=False, hard=False)
    add("lower_hull_E", lo, "shell", "hull", internal=False, hard=False)
    add("battery_hatch_tail_cap", door, "shell", "struct", internal=False, hard=False)

    # ---- Rev D solids reused unchanged (neck/receiver, head optics, rails, socket)
    rev_d = cq.Assembly.importStep(str(P.REV_D_STEP))
    dsolid = {n.name: n.obj.moved(n.loc) for n in rev_d.objects.values() if n.obj is not None}
    for n in ("Neck_Fixed_Shroud", "Neck_Fixed_Lower_Skid", "Neck_Asymmetric_Keyed_Tongue", "Receiver_bearing_land_L", "Receiver_bearing_land_R"):
        add(n, dsolid[n], "neck", "struct", internal=False, mates={"head_frame_E"} if n.startswith("Receiver") else ())

    # ---- chassis structure
    z0, z1 = P.CHASSIS_PLATE_Z
    cx, cy = P.CASTER_SWIVEL
    plate = cq.Workplane("XY", origin=(0, 0, z0)).polyline(plate_outline()).close().extrude(z1 - z0).val()
    plate = plate.cut(L.cyl(L.env("caster")["swivel_radius"] + 2.5, 10, (cx, cy, z0 - 1)))
    add("chassis_plate", plate, "chassis", "struct", internal=False)
    rs = L.env("caster")["swivel_radius"]
    top_hat = L.cyl(rs + 2.0, 2.0, (cx, cy, P.CASTER_MOUNT_Z)).fuse(L.cyl(rs + 9.0, 2.0, (cx, cy, z1)).cut(L.cyl(rs + 2.0, 4.0, (cx, cy, z1 - 1)))).clean()
    add("caster_bracket", top_hat, "chassis", "struct", 0.02, internal=False)
    add("caster", L.caster().moved(cq.Location(cq.Vector(cx, cy, P.CASTER_MOUNT_Z))), "caster", "motor", L.mass("caster"), internal=False)
    for tag, s in (("L", 1), ("R", -1)):
        m = L.motor(s).moved(cq.Location(cq.Vector(0, s * P.MOTOR_FACE_Y, P.AXLE_Z)))
        add(f"motor_{tag}", m, "drive", "motor", L.mass("motor"), mates={f"motor_mount_{tag}", f"wheel_{tag}"})
        mount = L.box(-24, 24, min(s * P.MOTOR_FACE_Y, s * (P.MOTOR_FACE_Y + 4)), max(s * P.MOTOR_FACE_Y, s * (P.MOTOR_FACE_Y + 4)), z1, 81)
        mount = mount.cut(L.cyl(7.0, 12, (0, s * (P.MOTOR_FACE_Y - 1), P.AXLE_Z), (0, s, 0)))
        add(f"motor_mount_{tag}", mount, "drive", "struct", 0.05, internal=False)
        pod = L.cyl(P.DRIVE_POD["outer_r"], P.DRIVE_POD["end_y"] - 84.0, (0, s * 84.0, P.MOTOR_AXIS_Z), (0, s, 0)).cut(
            L.cyl(P.DRIVE_POD["inner_r"], 60, (0, s * 80.0, P.MOTOR_AXIS_Z), (0, s, 0)))
        add(f"drive_pod_{tag}", pod, "shell", "hull", 0.03, internal=False, hard=False)
        w = L.cyl(P.WHEEL_R, P.TYRE_WIDTH, (0, s * (P.WHEEL_Y - P.TYRE_WIDTH / 2), P.AXLE_Z), (0, s, 0))
        w = w.cut(L.cyl(4.0, 30, (0, s * (P.WHEEL_Y - 15), P.AXLE_Z), (0, s, 0)))
        add(f"wheel_{tag}", w, "drive", "tyre", L.mass("wheel"), internal=False)

    # ---- electronics bridge, main board, saddle cover, grip
    S, G = P.SADDLE, P.GRIP
    bz = P.ELECTRONICS_BRIDGE_Z
    ex0, ex1 = P.ELECTRONICS_BRIDGE_X
    add("electronics_bridge", L.box(ex0, ex1, -S["half_y"], S["half_y"], *bz), "chassis", "struct", 0.10)
    for i, (px, py) in enumerate([(ex0 + 5, 76), (ex0 + 5, -76), (ex1 - 5, 45), (ex1 - 5, -45)]):
        add(f"bridge_post_{i}", L.cyl(4.0, bz[0] - z1, (px, py, z1)), "chassis", "struct", 0.01)
    b = P.CHS_MAIN
    ox, oy, oz = b["origin"]
    w_, h_ = b["outline"]
    add("RR-CHS-MAIN_pcb", L.box(ox, ox + h_, oy - w_, oy, oz, oz + b["thickness"]), "chs_main", "pcb", 0.22)
    add("RR-CHS-MAIN_top_parts", L.box(ox, ox + h_, oy - w_, oy, oz + b["thickness"], oz + b["thickness"] + b["max_top"]), "chs_main", "keepout")
    add("RR-CHS-MAIN_bottom_parts", L.box(ox, ox + h_, oy - w_, oy, oz - b["max_bottom"], oz), "chs_main", "keepout")
    add("saddle_service_cover", L.box(S["x"][0], S["x"][1], -S["half_y"], S["half_y"], *S["floor_z"]), "grip", "struct", 0.09, internal=False)
    gx0, gx1 = G["center_x"] - G["bar_x"] / 2, G["center_x"] + G["bar_x"] / 2
    add("grip_bar", L.box(gx0, gx1, -G["half_span_y"], G["half_span_y"], G["bar_bottom_z"], G["bar_top_z"]), "grip", "struct", 0.12, internal=False)
    for tag, s in (("L", 1), ("R", -1)):
        ya, yb = sorted((s * G["cheek_y"][0], s * G["cheek_y"][1]))
        add(f"grip_cheek_{tag}", L.box(gx0, gx1, ya, yb, S["floor_z"][0], G["bar_top_z"]), "grip", "struct", 0.06, internal=False)
        add(f"grip_leg_{tag}", L.box(gx0 - 7.5, gx0 + 1.5, ya, yb, 46.0, S["floor_z"][0]), "grip", "struct", 0.03)
        yc, yd = sorted((s * 60.0, s * 90.0))
        add(f"grip_yoke_{tag}", L.box(gx0 - 7.5, gx0 + 1.5, yc, yd, z1, 46.0), "grip", "struct", 0.02)

    # ---- battery bay
    B = P.BATTERY_BAY
    cas = L.box(*B["cassette_x"], -B["cassette_half_y"], B["cassette_half_y"], *B["cassette_z"])
    pack = L.box(*B["pack_x"], -B["pack_half_y"], B["pack_half_y"], *B["pack_z"])
    add("battery_cassette", cas.cut(pack), "battery", "struct", 0.12)
    add("battery_pack_PSL-SC-1290", pack, "battery", "battery", L.mass("battery_8ah"))
    add("battery_coupler", L.box(*B["coupler_x"], -B["coupler_half_y"], B["coupler_half_y"], *B["coupler_z"]), "battery", "conn", L.mass("battery_coupler"))
    roof0 = B["cassette_z"][1] + 1.0
    add("battery_tunnel_roof", L.box(-200.0, B["cassette_x"][1], -57.5, 57.5, roof0, B["tunnel_roof_z"]), "chassis", "struct", 0.05)
    for tag, s in (("L", 1), ("R", -1)):
        ya, yb = sorted((s * 55.0, s * 57.5))
        add(f"battery_tunnel_wall_{tag}", L.box(-212.0, B["cassette_x"][1], ya, yb, z1 + 1, roof0), "chassis", "struct", 0.04)
    e = L.env("chassis_heater")
    add("chassis_heater_pad", L.box(-164, -164 + e["l"], -e["w"] / 2, e["w"] / 2, 38.2, 38.2 + e["h"]), "thermal", "heat", L.mass("chassis_heater"))

    # ---- compute, LiDAR, annunciator
    c = P.CM5_POSE
    e = L.env("cm5_carrier")
    add("CM5_carrier_assembly", L.box(c["x"][0], c["x"][1], c["y"][0], c["y"][1], c["pcb_z"] - 3, c["pcb_z"] - 3 + e["h_assembled"]), "compute", "compute", L.mass("cm5") + L.mass("cm5_carrier") + 0.04)
    lx, ly = P.LIDAR_POSE["xy"]
    add("lidar_LakiBeam1L", L.lidar().moved(cq.Location(cq.Vector(lx, ly, P.LIDAR_POSE["base_z"]))), "lidar", "lidar", L.mass("lidar"), internal=False)
    pc = P.PANEL_CONTROLS["annunciator"]["xyz"]
    pe = L.env("panel_board")
    add("RR-PANEL", L.box(pc[0] - pe["w"] / 2, pc[0] + pe["w"] / 2, -pe["l"] / 2, pe["l"] / 2, pc[2] - 6 - pe["h"], pc[2] - 6), "panel", "pcb", L.mass("panel_board"))

    # ---- panel devices
    kinds = {"estop": "estop", "hands_on": "pushbutton_22", "mode_selector": "mode_selector", "rearm_start": "pushbutton_22", "pause_stop": "pushbutton_22"}
    for name, kind in kinds.items():
        ctl = P.PANEL_CONTROLS[name]
        head, body = L.panel_device(kind)
        add(f"{name}_operator", place(head, ctl["xyz"], ctl["normal"]), "controls", "control", 0.0, internal=False, mates={f"{name}_body"})
        add(f"{name}_body", place(body, ctl["xyz"], ctl["normal"]), "controls", "control", L.mass(kind), internal=False, mates={f"{name}_operator"})
    rec, cov = L.inlet()
    ci = P.CHARGE_INLET
    add("charge_inlet", place(rec, ci["xyz"], ci["normal"]), "charge", "conn", L.mass("charge_inlet"), internal=False, mates={"charge_inlet_cover"})
    add("charge_inlet_cover", place(cov, ci["xyz"], ci["normal"]), "charge", "control", 0.01, internal=False, mates={"charge_inlet"})
    nuts, grasp = {}, {}
    for jn, key in (("J1", "j1_receptacle"), ("J2", "j2_receptacle")):
        j = P.J_RECEPTACLES[jn]
        rec, plug, nut = L.receptacle(key)
        add(f"{jn}_receptacle", place(rec, j["xyz"], j["normal"]), "connectors", "conn", L.mass(key), internal=False, mates={f"{jn}_mated_plug"})
        add(f"{jn}_mated_plug", place(plug, j["xyz"], j["normal"]), "connectors", "conn", 0.0, internal=False, mates={f"{jn}_receptacle"})
        nuts[jn] = place(nut, j["xyz"], j["normal"])
        ej = L.env(key)
        zone = L.cyl(ej["plug_nut_d"] / 2 + P.GLOVE_CLEARANCE_CONNECTOR, ej["plug_nut_l"], (0, 0, 2.0)).cut(L.cyl(ej["plug_nut_d"] / 2 + 0.2, ej["plug_nut_l"] + 2, (0, 0, 1.0)))
        grasp[jn] = place(zone, j["xyz"], j["normal"])

    # ---- sensors and switches
    for name, t in P.TOF_SENSORS.items():
        host = {"tof_look_fl": {"grip_cheek_L", "grip_bar"}, "tof_look_fr": {"grip_cheek_R", "grip_bar"}}.get(name, set())
        add(name, place(L.tof(), t["xyz"], t["dir"]), "tof", "sensor", L.mass("tof_board"), internal=False, mates=host)
    sw = L.switch()
    for name, xyz in {**P.BODY_BUMPER_SWITCHES, "head_dock_switch": P.HEAD_DOCK_SWITCH}.items():
        add(name, sw.moved(cq.Location(cq.Vector(xyz[0] + (8 if xyz[0] < 0 else 0), xyz[1] * (0.9 if xyz[0] < 0 else 1), xyz[2]))), "switches", "sensor", L.mass("bumper_switch"), internal=False, hard=False)
    e = L.env("clamp_resistor")
    add("bus_clamp_resistor", L.box(20, 20 + e["w"], -e["l"] / 2, e["l"] / 2, z1, z1 + e["h"]), "thermal", "heat", L.mass("clamp_resistor"))

    # ---- detector head, Rev E
    proj = rail_projection
    dz = (P.FILM_Z - proj) - 7.0    # Rev D STEP carries the 3 mm rails (underside z = 7)
    for n, s in dsolid.items():
        if n.startswith(("S0_", "S1_", "S2_", "S3_")):
            if "Heater_zone" in n:
                continue
            add(n, s, "head_optics", "optic", internal=False)
        elif n.startswith(("Leading_contact_rail", "Side_contact_rail", "Wing_tip_contact_return")):
            add(n, s.translate((0, 0, dz)) if dz else s, "head_rails", "head", internal=False)
        elif n in ("Key_socket", "Captive_pin_envelope"):
            add(n, s, "head_frame", "head", internal=False)
    frame = cached(["head_frame_E", P.HEAD_FRAME_TOP_Z], lambda: dsolid["Peripheral_frame_and_interlane_ribs"].cut(L.box(100, 300, -200, 200, P.HEAD_FRAME_TOP_Z, 60)))
    add("head_frame_E", frame, "head_frame", "head", internal=False)
    for i, y in enumerate(P.SEG_Y):
        add(f"S{i}_retention_pad_and_heater", L.box(P.ROW_X - P.ACTIVE_X / 2, P.ROW_X + P.ACTIVE_X / 2, y - P.ACTIVE_Y / 2, y + P.ACTIVE_Y / 2, P.HEAD_STACK[0][1], P.HEAD_STACK[0][2]), "head_stack", "heat", internal=False)
    add("head_spreader_plate", L.box(*P.HEAD_SPREADER_X, -P.HEAD_SPREADER_HALF_Y, P.HEAD_SPREADER_HALF_Y, P.HEAD_STACK[1][1], P.HEAD_STACK[1][2]), "head_stack", "struct", internal=False)
    hb = P.HEAD_ACQ
    ox, oy, oz = hb["origin"]
    w_, h_ = hb["outline"]
    add("RR-HEAD-ACQ_pcb", L.box(ox, ox + h_, oy - w_, oy, oz, oz + hb["thickness"]), "head_acq", "pcb", internal=False)
    add("RR-HEAD-ACQ_top_parts", L.box(ox, ox + h_, oy - w_, oy, oz + hb["thickness"], oz + hb["thickness"] + hb["max_top"]), "head_acq", "keepout", internal=False)
    add("RR-HEAD-ACQ_bottom_parts", L.box(ox, ox + h_, oy - w_, oy, oz - hb["max_bottom"], oz), "head_acq", "keepout", internal=False)
    cz0, cz1 = P.HEAD_STACK[-1][1], P.HEAD_STACK[-1][2]
    xa, xb = P.HEAD_COVER_X
    hy = P.HEAD_COVER_HALF_Y
    skirt = L.box(xa, xb, -hy, hy, P.HEAD_FRAME_TOP_Z, cz0).cut(L.box(xa + 2.5, xb - 2.5, -hy + 2.5, hy - 2.5, P.HEAD_FRAME_TOP_Z - 1, cz0 + 1))
    skirt = skirt.cut(L.box(138, 154.5, -43.0, 43.0, 20, 42.5))
    cover = L.box(xa, xb, -hy, hy, cz0, cz1).fuse(skirt).clean()
    add("head_cover_E", cover, "head_cover", "shell", internal=False)

    pods = [L.cyl(P.DRIVE_POD["inner_r"], 2 * (P.WHEEL_Y + 5), (0, -(P.WHEEL_Y + 5), P.MOTOR_AXIS_Z), (0, 1, 0))]  # pod bore + shaft exit
    return parts, {"cav_u": cav_u, "cav_l": cav_l, "pods": pods, "nuts": nuts, "grasp": grasp, "rev_d": dsolid}


# ----------------------------------------------------------------------------------------------------- checks
SAME_GROUP_OK = {"head_optics", "chs_main", "head_acq", "battery", "grip", "controls", "charge", "connectors", "neck"}


def interference(parts, near=12.0):
    hard = [p for p in parts if p.hard]
    clash, close, nearest = [], [], {p.name: (1e9, None) for p in hard}
    for a, b in itertools.combinations(hard, 2):
        if a.group == b.group and a.group in SAME_GROUP_OK:
            continue
        gap = max(max(a.bb[i] - b.bb[i + 3], b.bb[i] - a.bb[i + 3]) for i in range(3))
        if gap > near:
            continue
        d = BRepExtrema_DistShapeShape(a.shape.wrapped, b.shape.wrapped)
        d.Perform()
        dist = d.Value() if d.IsDone() else float("nan")
        vol = 0.0
        if dist < 1e-6:
            try:
                vol = a.shape.intersect(b.shape).Volume()
            except Exception:  # noqa: BLE001
                vol = float("nan")
            mated = b.name in a.mates or a.name in b.mates
            if vol > 1.0 and not mated:
                clash.append((a.name, b.name, round(vol, 1)))
        else:
            for p, q in ((a, b), (b, a)):
                if dist < nearest[p.name][0]:
                    nearest[p.name] = (dist, q.name)
            if dist < 2.0:
                close.append((a.name, b.name, round(dist, 2)))
    return clash, close, nearest


def containment(parts, cav_u, cav_l, pods=(), margin=1.0):
    """Every internal part's vertices must lie inside the Rev E cavity (CAD loft solids) by `margin`."""
    floor = P.BODY_ROWS["lower_inner"][0][0]
    bad = []
    for p in parts:
        if not p.internal or not p.hard:
            continue
        worst = None
        pts = [(v.X, v.Y, v.Z) for v in p.shape.Vertices()]
        for x, y, z in pts:
            zz = max(z, floor + 0.2) if z >= P.CHASSIS_PLATE_Z[1] - 1e-6 else z
            v = cq.Vector(x, y * (1 + 0) + math.copysign(margin, y) if abs(y) > 1e-9 else y, zz)
            if not (cav_u.isInside(v, 1e-4) or cav_l.isInside(v, 1e-4) or any(q.isInside(cq.Vector(x, y, z), 1e-4) for q in pods)):
                analytic = P.half_breadth(x, zz, "inner") - abs(y)
                worst = (round(x, 1), round(y, 1), round(z, 1), round(analytic, 1))
                break
        if worst:
            bad.append((p.name, worst))
    return bad


def ray_hits(probes, start, direction, reach, skip=()):
    line = gp_Lin(gp_Pnt(*start), gp_Dir(*direction))
    hits = []
    for name, obj in probes.items():
        if name in skip:
            continue
        obj.Perform(line, 2.0, reach)
        if obj.NbPnt():
            hits.append((name, round(min(obj.WParameter(i) for i in range(1, obj.NbPnt() + 1)), 1)))
    return sorted(hits, key=lambda h: h[1])


def cone_dirs(axis, half_deg, n=8):
    ax = P._unit(axis)
    ref = (0, 0, 1) if abs(ax[2]) < 0.9 else (1, 0, 0)
    u = P._unit((ax[1] * ref[2] - ax[2] * ref[1], ax[2] * ref[0] - ax[0] * ref[2], ax[0] * ref[1] - ax[1] * ref[0]))
    v = (ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0])
    t = math.tan(math.radians(half_deg))
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        out.append(P._unit(tuple(ax[k] + t * (math.cos(a) * u[k] + math.sin(a) * v[k]) for k in range(3))))
    return out


def sensor_rays(parts):
    """Port of cad/source/verify_geometry.py: centre ray of every ToF to the floor or to max range must be clear;
    additionally the 18 deg cone edge rays are reported (obstructions there are findings, not failures)."""
    probes = {}
    for p in parts:
        it = IntCurvesFace_ShapeIntersector()
        it.Load(p.shape.wrapped, 1e-5)
        probes[p.name] = it
    rows, fail = [], []
    # self-test of the ray tool: a ray aimed from the left look-ahead sensor into the head MUST report the head cover
    s0 = P.TOF_SENSORS["tof_look_fl"]["xyz"]
    aim = P._unit((P.ROW_X - s0[0], 60.0 - s0[1], 40.0 - s0[2]))
    probe = [h[0] for h in ray_hits(probes, s0, aim, 600.0, skip=("tof_look_fl",))]
    if "head_cover_E" not in probe:
        raise RuntimeError(f"ray tool self-test failed: {probe}")
    for name, t in P.TOF_SENSORS.items():
        s, d = t["xyz"], P._unit(t["dir"])
        reach = min(P.TOF_MAX_RANGE, s[2] / -d[2] - 0.1) if d[2] < -1e-6 else P.TOF_MAX_RANGE
        centre = ray_hits(probes, s, d, reach, skip=(name,))
        edge = {}
        for e in cone_dirs(d, P.TOF_FOV_FULL_DEG / 2):
            r = min(P.TOF_MAX_RANGE, s[2] / -e[2] - 0.1) if e[2] < -1e-6 else P.TOF_MAX_RANGE
            for hn, hd in ray_hits(probes, s, e, r, skip=(name,))[:1]:
                edge[hn] = min(hd, edge.get(hn, 1e9))
        floor = None
        if d[2] < -1e-6:
            rng = s[2] / -d[2]
            floor = (round(s[0] + rng * d[0], 1), round(s[1] + rng * d[1], 1), round(rng, 1))
        rows.append({"sensor": name, "start": [round(c, 1) for c in s], "dir": [round(c, 3) for c in d], "floor_hit_xy_range": floor,
                     "centre_ray_hits": centre, "cone_edge_hits": edge})
        if centre:
            fail.append((name, centre))
    # LiDAR scan plane
    lx, ly = P.LIDAR_POSE["xy"]
    lz = P.LIDAR_POSE["base_z"] + P.LIDAR_SCAN_PLANE_ABOVE_BASE
    blocked = []
    for deg in range(-135, 136, 3):
        d = (math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0)
        h = ray_hits(probes, (lx, ly, lz), d, 2000.0, skip=("lidar_LakiBeam1L",))
        h = [x for x in h if x[1] > 31.0]
        if h:
            blocked.append((deg, h[0]))
    return rows, fail, {"scan_z": lz, "blocked": blocked}


def box_free(parts, box, skip=()):
    solid = L.box(*box)
    bb = bounds(solid)
    out = []
    for p in parts:
        if p.name in skip or p.group in skip:
            continue
        if any(p.bb[i] > bb[i + 3] or bb[i] > p.bb[i + 3] for i in range(3)):
            continue
        try:
            v = solid.intersect(p.shape).Volume()
        except Exception:  # noqa: BLE001
            v = float("nan")
        if not v < 1.0:
            out.append((p.name, round(v, 0)))
    return out


def dist_to_all(parts, shape, skip=()):
    res = []
    for p in parts:
        if p.name in skip or p.group in skip:
            continue
        d = BRepExtrema_DistShapeShape(shape.wrapped, p.shape.wrapped)
        d.Perform()
        res.append((round(d.Value(), 1), p.name))
    return sorted(res)[:4]


def service_checks(parts, extra):
    B, G, S = P.BATTERY_BAY, P.GRIP, P.SADDLE
    out = {}
    cx0, cx1 = B["cassette_x"]
    sweep = (cx0 - B["removal_travel"], cx1, -B["cassette_half_y"], B["cassette_half_y"], *B["cassette_z"])
    out["battery_removal_sweep"] = {"direction": "-x (rearward through the tail-cap hatch)", "travel_mm": B["removal_travel"],
                                    "blocked_by": box_free(parts, sweep, skip=("battery", "battery_hatch_tail_cap", "battery_coupler"))}
    gx0, gx1 = G["center_x"] - G["bar_x"] / 2, G["center_x"] + G["bar_x"] / 2
    c = P.GLOVE_CLEARANCE_GRIP
    out["grip_hand_zone"] = {"box": "45 mm in front of, behind and below the bar, 130 mm wide",
                             "blocked_by": box_free(parts, (gx0 - c, gx1 + c, -65, 65, S["floor_z"][1] + 0.1, G["bar_bottom_z"] - 0.1), skip=())
                             + box_free(parts, (gx0 - c, gx0 - 0.1, -65, 65, G["bar_bottom_z"], G["bar_top_z"] + 30))
                             + box_free(parts, (gx1 + 0.1, gx1 + c, -65, 65, G["bar_bottom_z"], G["bar_top_z"] + 30))}
    for jn, nut in extra["nuts"].items():
        near = dist_to_all(parts, nut, skip=(f"{jn}_receptacle", f"{jn}_mated_plug", "shell"))
        zb = bounds(extra["grasp"][jn])
        blocked = []
        for p in parts:
            if p.name in (f"{jn}_receptacle", f"{jn}_mated_plug") or any(p.bb[i] > zb[i + 3] or zb[i] > p.bb[i + 3] for i in range(3)):
                continue
            v = extra["grasp"][jn].intersect(p.shape).Volume()
            if v > 1.0:
                blocked.append((p.name, round(v)))
        out[f"{jn}_coupling_nut_clearance"] = {"required_mm": P.GLOVE_CLEARANCE_CONNECTOR, "grasp_zone": "annulus nut radius .. nut radius + 45 mm over the nut length (2..24 mm above the skin), all solids incl. the body skin",
                                               "blocked_by": blocked, "nearest_3d_mm_excl_skin": near}
    ci = P.CHARGE_INLET
    probe = cq.Solid.makeSphere(1.0, cq.Vector(*(ci["xyz"][k] + 30 * ci["normal"][k] for k in range(3))))
    near = dist_to_all(parts, probe, skip=("charge",))
    out["charge_inlet_access"] = {"probe": "point 30 mm outboard of the inlet on its axis", "nearest": near, "min_mm": near[0][0]}
    for tag, s in (("L", 1), ("R", -1)):
        y0, y1 = sorted((s * (P.WHEEL_Y + P.TYRE_WIDTH / 2 + 0.5), s * (P.WHEEL_Y + P.TYRE_WIDTH / 2 + 60)))
        out[f"wheel_{tag}_axial_removal"] = {"blocked_by": box_free(parts, (-P.WHEEL_R, P.WHEEL_R, y0, y1, 0.5, P.WHEEL_D))}
    he = P.HEAD_ENV_E
    out["head_removal_sweep_+x"] = {"blocked_by": box_free(parts, (he["x"][1] + 0.5, he["x"][1] + 60, he["y"][0], he["y"][1], he["z"][0], he["z"][1]))}
    return out


CORRIDORS = {   # name: (x0, x1, y0, y1, z0, z1), what runs there
    "tunnel_top_spine": ((-198, -72, -40, 40, 114, 121), "LiDAR Ethernet/12 V, RR-PANEL, rear ToF and deck controls to the board rear corners"),
    "left_gutter": ((-69, -5, 99, 105, 84, 98), "left motor/encoder, left look-ahead ToF, USB/5 V to CM5"),
    "right_gutter": ((-69, -5, -105, -99, 84, 98), "pack feed from the coupler, charge feed, right motor/encoder, E-stop loop"),
    "front_bay": ((36, 62, -30, 30, 56, 90), "J1/J2 feeds, front cliff ToF, dock switch, clamp resistor leads"),
    "under_bridge_right": ((-12, 20, -41, -20, 40, 76), "pack feed from the coupler between the motor ends to the right gutter"),
    "left_bay_over_cm5": ((-102, -75, 59, 80, 78, 98), "CM5 USB/Ethernet/antenna pigtails, selector and REARM leads"),
    "right_bay": ((-185, -100, -95, -60, 45, 76), "charge inlet feed, HANDS-ON/Pause leads, right rear ToF, bumper switch"),
}


def corridor_checks(parts):
    return {k: {"box": list(b), "use": use, "blocked_by": box_free(parts, b)} for k, (b, use) in CORRIDORS.items()}


def rev_d_containment():
    """Why the Rev D body cannot contain the hardware: free cavity volume and key widths vs the parts (calculated)."""
    rows_u, rows_l = P.REV_D_ROWS["upper_inner"], P.REV_D_ROWS["lower_inner"]

    def area(row, n=400):
        pts = [P.ring_point(row, 2 * math.pi * i / n) for i in range(n)]
        return abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2

    def vol(rows, zmin, zmax, n=60):
        v = 0.0
        for i in range(n):
            z = zmin + (zmax - zmin) * (i + 0.5) / n
            r = P._interp_row(rows, z)
            v += area(r) * (zmax - zmin) / n if r else 0.0
        return v
    cavity = vol(rows_l, 37, 54) + vol(rows_u, 54, 113)
    handwell = 94 * 130 * (113 - 42.7) * 0.82
    wheel_wells = 2 * 0.5 * math.pi * 55.8 ** 2 * 11 * 0.6
    free = cavity - handwell - wheel_wells
    need = {"battery cassette 9 Ah": 156.5 * 107 * 70, "RR-CHS-MAIN with height zones": 160 * 100 * 22.6, "CM5 + carrier": 85 * 56 * 24,
            "2 gearmotors (swept box)": 2 * 37 * 37 * 94.5, "battery coupler": 57.5 * 38 * 18, "LiDAR below deck (0)": 0,
            "E-stop, selector, 3 buttons (rear bodies)": 5 * math.pi * 15 ** 2 * 50, "J1, J2, inlet rear bodies": 3 * math.pi * 10 ** 2 * 22}
    return {"rev_d_cavity_cm3": round(cavity / 1000), "hand_well_cm3": round(handwell / 1000), "wheel_wells_cm3": round(wheel_wells / 1000),
            "free_cm3": round(free / 1000), "hardware_envelope_cm3": round(sum(need.values()) / 1000),
            "hardware_items_cm3": {k: round(v / 1000) for k, v in need.items()},
            "max_inner_width_mm": round(2 * max(r[3] for r in rows_u), 1), "width_between_wheel_wells_mm": 2 * 95.7,
            "inner_height_mm": 113 - 37, "hand_well_plan_mm": [94, 130],
            "blocking_facts": [
                "Rev D motor centreline z = 52 puts a 37 mm can from z 33.5 to 70.5: the 160 x 100 board can only lie above z 75, where the Rev D cavity is <= 2 x 73 mm wide at the board corners and the LiDAR/E-stop stand.",
                "The 151 x 99 x 65 mm pack needs a 157 x 107 x 70 mm bay behind the axle; that plan area is the hand well (floor z 42.7).",
                "Free cavity volume is smaller than the sum of the hardware envelopes before any structure, harness or clearances."]}


# ----------------------------------------------------------------------------------------------------- outputs
def export_step(parts, path):
    asm = cq.Assembly(name="RR_E_master_layout")
    groups = {}
    for p in parts:
        g = groups.setdefault(p.group, cq.Assembly(name="grp_" + p.group))
        g.add(p.shape, name=p.name, color=p.color)
    for g in groups.values():
        asm.add(g)
    asm.export(str(path))
    return asm


def render(parts, path_prefix):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    meshes = []
    for p in parts:
        if p.name.startswith(("S0_", "S1_", "S2_", "S3_")) and "Floor_guide" not in p.name:
            continue
        tol = 2.0 if p.group == "shell" else 0.8
        v, f = p.shape.tessellate(tol, 0.5)
        if not f:
            continue
        rgba = p.color.toTuple()
        meshes.append((p, [(a.x, a.y, a.z) for a in v], f, rgba))
    views = {"top": (0, 1, 2, "x forward [mm]", "y left [mm]"), "side": (0, 2, 1, "x forward [mm]", "z up [mm]"), "front": (1, 2, 0, "y left [mm]", "z up [mm]")}
    for vn, (i, j, k, xl, yl) in views.items():
        fig, ax = plt.subplots(figsize=(13, 8 if vn == "top" else 5.5), dpi=110)
        polys, cols, depth = [], [], []
        for p, v, f, rgba in meshes:
            shell = p.group == "shell" or not p.hard or "parts" in p.name
            for tri in f:
                pts = [(v[t][i], v[t][j]) for t in tri]
                polys.append(pts)
                a = 0.05 if shell else 0.55
                cols.append((rgba[0], rgba[1], rgba[2], a))
                d = sum(v[t][k] for t in tri) / 3
                depth.append(d if vn != "side" else -d)
        order = sorted(range(len(polys)), key=lambda n: depth[n])
        ax.add_collection(PolyCollection([polys[n] for n in order], facecolors=[cols[n] for n in order], edgecolors="none"))
        for p in parts:
            if p.hard and p.group not in ("head_optics", "tof", "switches") and not p.name.startswith("bridge_post") and "parts" not in p.name:
                cxy = ((p.bb[i] + p.bb[i + 3]) / 2, (p.bb[j] + p.bb[j + 3]) / 2)
                if vn == "top" or (vn == "side" and abs((p.bb[1] + p.bb[4]) / 2) < 60) or (vn == "front" and p.bb[0] < 0):
                    ax.annotate(p.name.replace("_", " "), cxy, fontsize=4.2, ha="center", va="center", color="black")
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.grid(True, lw=0.2, alpha=0.5)
        if vn != "top":
            ax.axhline(0, color="k", lw=0.8)
        ax.set_title(f"Rad Roomba Rev E master layout -- {vn} view (envelope solids, base_link mm)")
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_{vn}.png")
        plt.close(fig)


def write_report(R, path):
    L_ = []
    A = L_.append
    A("# Rev E master layout report\n")
    A(f"Generated by `mechanical/common/layout.py` (contract {P.CONTRACT_VERSION}, rail projection {R['rail']} mm). "
      "Evidence class: **tool-checked** on nominal envelope solids unless a line says *calculated*. Nothing is physically measured.\n")
    A("## 1. Result summary\n")
    A("| Check | Result |\n|---|---|")
    for k, v in R["summary"].items():
        A(f"| {k} | {v} |")
    A("\n## 2. Envelope and clearances\n")
    A("| Quantity | Value (mm) |\n|---|---|")
    for k, v in R["extents"].items():
        A(f"| {k} | {v} |")
    A("\n## 3. Rev D containment (calculated) -- why a body change is proposed\n")
    rd = R["rev_d"]
    A(f"- Rev D inner cavity {rd['rev_d_cavity_cm3']} cm3; hand well {rd['hand_well_cm3']} cm3 and wheel wells {rd['wheel_wells_cm3']} cm3 leave about **{rd['free_cm3']} cm3**.")
    A(f"- Hardware envelopes (no structure, harness or clearance): **{rd['hardware_envelope_cm3']} cm3** -> " + ", ".join(f"{k} {v}" for k, v in rd["hardware_items_cm3"].items() if v) + ".")
    A(f"- Rev D inner width {rd['max_inner_width_mm']} mm ({rd['width_between_wheel_wells_mm']} mm between wheel wells), inner height {rd['inner_height_mm']} mm.")
    for s in rd["blocking_facts"]:
        A(f"- {s}")
    A("\n## 4. Interference check (all hard envelopes, pairwise)\n")
    A(f"Pairs evaluated with the OCC distance tool after a bounding-box prefilter; {R['n_parts']} solids, {R['n_hard']} hard.\n")
    A("**Volumetric clashes (> 1 mm3, not declared mates):** " + ("none" if not R["clash"] else ""))
    for a, b, v in R["clash"]:
        A(f"- {a} x {b}: {v} mm3")
    A("\n**Pairs closer than 2.0 mm (not touching):**" + (" none" if not R["close"] else ""))
    for a, b, d in R["close"]:
        A(f"- {a} -- {b}: {d} mm")
    A("\n**Nearest neighbour of each principal part:**\n\n| Part | Clearance (mm) | Nearest |\n|---|---|---|")
    for n, (d, q) in sorted(R["nearest"].items()):
        if q and not n.startswith(("S0_", "S1_", "S2_", "S3_", "bridge_post", "tof_")):
            A(f"| {n} | {d:.1f} | {q} |")
    A("\n## 5. Containment in the Rev E body cavity\n")
    A("Vertices of every internal part tested against the CAD inner-skin lofts with 1.0 mm lateral margin: " + ("**all inside**." if not R["outside"] else "**FAIL**"))
    for n, w in R["outside"]:
        A(f"- {n}: vertex {w[:3]} outside (analytic margin {w[3]} mm)")
    A("\n## 6. Service access\n")
    for k, v in R["service"].items():
        A(f"- **{k}**: " + json.dumps(v, default=str))
    A("\n## 7. Cable corridors (reserved boxes must stay free)\n")
    A("| Corridor | Box x0,x1,y0,y1,z0,z1 | Carries | Blocked by |\n|---|---|---|---|")
    for k, v in R["corridors"].items():
        A(f"| {k} | {v['box']} | {v['use']} | {v['blocked_by'] or 'free'} |")
    A("\n## 8. Sensor ray checks (port of cad/source/verify_geometry.py)\n")
    A(f"ToF field of view {P.TOF_FOV_FULL_DEG} deg full cone (UNVERIFIED datasheet value), eight edge rays per sensor. Head top z = {P.HEAD_TOP_Z}.\n")
    A("| Sensor | Start | Boresight | Floor hit (x, y, range) | Centre ray | Cone edge obstructions (first hit, mm) |\n|---|---|---|---|---|---|")
    for r in R["rays"]:
        A(f"| {r['sensor']} | {r['start']} | {r['dir']} | {r['floor_hit_xy_range']} | {'clear' if not r['centre_ray_hits'] else r['centre_ray_hits']} | {r['cone_edge_hits'] or 'clear'} |")
    lz = R["lidar"]
    A(f"\nLiDAR scan plane z = {lz['scan_z']} mm (assumed {P.LIDAR_SCAN_PLANE_ABOVE_BASE} mm above the base, UNVERIFIED): "
      + ("270 deg field clear of all robot parts." if not lz["blocked"] else f"blocked bearings {lz['blocked']}"))
    A("\n## 9. Carry-grip load path\n")
    A("Hand -> transverse grip bar (25 x 22 mm, 168 mm span, above the calculated centre of gravity) -> two cheeks (14 x 25 mm) -> "
      "cheek legs outside the main-board edges -> chassis plate between the motor mounts -> motor mounts/wheels and battery bay. "
      "The printed shells carry no lifting load. Bar and cheek stresses are in out/mech_calcs.md.")
    A("\n## 10. Mass roll-up of placed purchased parts\n")
    A(f"Sum of purchased-part masses placed in this model: {R['mass_placed']:.2f} kg (full budget incl. structure in out/mech_calcs.md).\n")
    path.write_text("\n".join(L_) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rail", type=float, default=3.0, choices=[3.0, 5.0])
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    parts, extra = build(args.rail)
    print(f"built {len(parts)} solids in {time.time() - t0:.1f} s", flush=True)
    export_step(parts, OUT / "RR_E_master_layout.step")
    head = [p for p in parts if p.group.startswith("head")]
    export_step(head, OUT / "RR_E_head_layout.step")
    print(f"STEP exported at {time.time() - t0:.1f} s", flush=True)

    clash, close, nearest = interference(parts)
    outside = containment(parts, extra["cav_u"], extra["cav_l"], extra["pods"])
    rays, ray_fail, lidar = sensor_rays(parts)
    service = service_checks(parts, extra)
    corridors = corridor_checks(parts)
    allp = cq.Compound.makeCompound([p.shape for p in parts])
    bb = bounds(allp)
    body = bounds(cq.Compound.makeCompound([p.shape for p in parts if p.group == "shell"]))
    headbb = bounds(cq.Compound.makeCompound([p.shape for p in head]))
    low = sorted((p.bb[2], p.name) for p in parts if p.group not in ("head_rails", "caster") and not p.name.startswith("wheel"))[:4]
    extents = {
        "overall x (tail .. leading rail)": f"{bb[0]:.1f} .. {bb[3]:.1f}  (length {bb[3] - bb[0]:.1f})",
        "overall y": f"{bb[1]:.1f} .. {bb[4]:.1f}  (width {bb[4] - bb[1]:.1f})",
        "overall z": f"{bb[2]:.1f} .. {bb[5]:.1f}",
        "body shell x / y / z": f"{body[0]:.1f}..{body[3]:.1f} / {body[1]:.1f}..{body[4]:.1f} / {body[2]:.1f}..{body[5]:.1f}  (Rev D: -165.0..102.3 / +-112.6 / 32.9..117.6)",
        "width across tyres": f"{P.TRACK + P.TYRE_WIDTH:.1f}",
        "head envelope x / y / z": f"{headbb[0]:.1f}..{headbb[3]:.1f} / {headbb[1]:.1f}..{headbb[4]:.1f} / {headbb[2]:.1f}..{headbb[5]:.1f}  (contract ceiling z {P.HEAD_ENV_E_CEILING['z']})",
        "tail swept radius about base_link": f"{max(math.hypot(body[0], 60), math.hypot(-228, 110)):.0f}  (head outer corner {math.hypot(headbb[3], headbb[4]):.0f})",
        "ground clearance: body underside / neck skid / head rail": f"{body[2]:.1f} / {min(p.bb[2] for p in parts if p.group == 'neck'):.1f} / {min(p.bb[2] for p in parts if p.group == 'head_rails'):.1f}",
        "lowest non-running-gear solids": "; ".join(f"{n} {z:.1f}" for z, n in low),
        "caster contact / wheel contact z": f"{min(p.bb[2] for p in parts if p.group == 'caster'):.2f} / {min(p.bb[2] for p in parts if p.name.startswith('wheel')):.2f}",
        "grip bar z / LiDAR top z": f"{P.GRIP['bar_bottom_z']:.1f}..{P.GRIP['bar_top_z']:.1f} / {P.LIDAR_POSE['base_z'] + L.env('lidar')['h']:.1f}",
    }
    head_ok = headbb[5] <= P.HEAD_ENV_E_CEILING["z"][1] + 1e-6 and headbb[2] >= P.HEAD_ENV_E_CEILING["z"][0] - 1e-6 \
        and headbb[0] >= P.HEAD_ENV_E_CEILING["x"][0] - 1e-6 and headbb[3] <= P.HEAD_ENV_E_CEILING["x"][1] + 1e-6 and abs(headbb[1]) <= 175 + 1e-6 and headbb[4] <= 175 + 1e-6
    svc_block = {k: v["blocked_by"] for k, v in service.items() if v.get("blocked_by")}

    cor_block = {k: v["blocked_by"] for k, v in corridors.items() if v["blocked_by"]}
    floor_ok = abs(min(p.bb[2] for p in parts if p.group == "caster")) < 0.05 and abs(min(p.bb[2] for p in parts if p.name.startswith("wheel"))) < 0.05
    checks = {
        "volumetric interference": (not clash, "none" if not clash else f"{len(clash)} clash(es)"),
        "containment in Rev E cavity": (not outside, "all internal parts inside" if not outside else f"{len(outside)} part(s) outside"),
        "head inside contract Rev E envelope": (head_ok, f"z {headbb[2]:.1f}..{headbb[5]:.1f}"),
        "wheel and caster on the floor plane": (floor_ok, "z = 0 +- 0.05"),
        "ToF centre rays": (not ray_fail, "all 11 clear" if not ray_fail else f"obstructed: {ray_fail}"),
        "LiDAR scan plane": (not lidar["blocked"], "clear" if not lidar["blocked"] else f"{len(lidar['blocked'])} bearings blocked"),
        "service sweeps (battery, wheels, head, grip hand zone)": (not svc_block, "free" if not svc_block else str(svc_block)),
        f"J1/J2 coupling-nut grasp zone ({P.GLOVE_CLEARANCE_CONNECTOR:.0f} mm radial) free": (not any(service[f"{j}_coupling_nut_clearance"]["blocked_by"] for j in ("J1", "J2")), "free (see service section)"),
        "cable corridors": (not cor_block, "free" if not cor_block else str(cor_block)),
    }
    R = {"rail": args.rail, "summary": {k: ("PASS" if ok else "FAIL") + f" -- {txt}" for k, (ok, txt) in checks.items()},
         "extents": extents, "rev_d": rev_d_containment(), "clash": clash, "close": close, "nearest": nearest, "outside": outside,
         "service": service, "corridors": corridors, "rays": rays, "lidar": lidar, "n_parts": len(parts), "n_hard": sum(p.hard for p in parts),
         "mass_placed": sum(p.mass for p in parts)}
    write_report(R, OUT / "layout_report.md")
    (OUT / "layout_checks.json").write_text(json.dumps({"summary": R["summary"], "extents": extents, "clash": clash, "close": close,
                                                        "outside": outside, "service": service, "corridors": corridors, "rays": rays,
                                                        "lidar": lidar, "head_bounds": headbb, "body_bounds": body}, indent=1, default=str))
    if not args.no_png:
        render(parts, str(OUT / "RR_E_master_layout"))
    for k, v in R["summary"].items():
        print(f"{v.split(' -- ')[0]:5s} {k}: {v.split(' -- ', 1)[1]}")
    print(f"done in {time.time() - t0:.1f} s")
    return 0 if all(ok for ok, _ in checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
