"""RR-X assembly: gathers every real part (rrx.structure/battery/shells/running) and the purchased envelopes."""
from __future__ import annotations

import time

import cadquery as cq

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import battery, dims as D, running, shells, structure
from . import sensors as S
from .util import Part, bounds, box, cyl, fuse, place

Z1 = D.PLATE_Z[1]
LOW_ZONES_UV = [(0, 14, 88, 100), (146, 160, 88, 100), (0, 45, 0, 20), (112, 160, 0, 22)]


def purchased(add):
    C = {"motor": "#8a8f93", "pcb": "#2e7d4f", "keep": "#e6c04a", "batt": "#c95146", "conn": "#b5c6ca", "ctl": "#da9745", "sens": "#7b5ea7", "comp": "#3d6fb0", "lidar": "#71acbb", "heat": "#b67346"}
    B = P.BATTERY_BAY
    for tag, s in (("L", 1), ("R", -1)):
        m = L.motor(s).moved(cq.Location(cq.Vector(0, s * P.MOTOR_FACE_Y, P.AXLE_Z)))
        add(Part("RRX-H40", f"motor_{tag}", m, "purchased", "STEEL", "drive", color=C["motor"], mass=L.mass("motor"), mpn=L.PARTS["motor"]["mpn"], verified="envelope VERIFIED; boss, shaft offset, hole pattern UNVERIFIED",
                 internal=False, mates={f"motor_pod_{tag}", f"screw_ring_{tag}", f"wheel_hub_{tag}", f"wheel_rim_{tag}"}))
    cx, cy = P.CASTER_SWIVEL
    add(Part("RRX-H41", "caster", L.caster().moved(cq.Location(cq.Vector(cx, cy, P.CASTER_MOUNT_Z))), "purchased", "STEEL", "caster", color=C["motor"], mass=L.mass("caster"),
             mpn=L.PARTS["caster"]["mpn"], verified="VERIFIED (TENTE datasheet); -20 C limit, plain bearing", internal=False, mates={"caster_shim", "caster_disc", "chassis_plate"}))
    add(Part("RRX-H42", "battery_pack", box(*B["pack_x"], -B["pack_half_y"], B["pack_half_y"], *B["pack_z"]), "purchased", "PACK", "cassette", color=C["batt"], mass=L.mass("battery_12ah"),
             mpn=L.PARTS["battery_12ah"]["mpn"], verified="VERIFIED", mates={"battery_cassette", "cassette_lid"}))
    cz = B["coupler_z"]
    add(Part("RRX-H43", "coupler_cassette", box(B["coupler_x"][0], -44.0, -B["coupler_half_y"], B["coupler_half_y"], *cz), "purchased", "PA", "cassette", color=C["conn"], mass=0.03,
             mpn="Anderson SBS50 housing + 2 power + 2 aux contacts (cassette half)", verified="UNVERIFIED envelope", mates={"coupler_fixed", "coupler_carrier", "battery_cassette", "battery_tunnel"}))
    add(Part("RRX-H43", "coupler_fixed", box(-44.0, B["coupler_x"][1], -B["coupler_half_y"], B["coupler_half_y"], *cz), "purchased", "PA", "battery_bay", color=C["conn"], mass=0.03,
             mpn="Anderson SBS50 housing + contacts (fixed half, cross-pinned in the cradle)", verified="UNVERIFIED envelope", mates={"coupler_cassette", "battery_tunnel"}))
    e = L.env("chassis_heater")
    add(Part("RRX-H44", "chassis_heater_pad", box(-164, -164 + e["l"], -e["w"] / 2, e["w"] / 2, Z1 + 1.0, Z1 + 1.0 + e["h"]), "purchased", "PI", "battery_bay", color=C["heat"], mass=L.mass("chassis_heater"),
             mpn=L.PARTS["chassis_heater"]["mpn"], verified="design value", mates={"floor_plug", "battery_tunnel"}))
    # (no bolt-on clamp resistor: RR-CHS-MAIN carries its own clamp resistors, IB-26)
    b = P.CHS_MAIN
    ox, oy, oz = b["origin"]
    w_, h_ = b["outline"]
    add(Part("RRX-E01", "RR-CHS-MAIN_pcb", box(ox, ox + h_, oy - w_, oy, oz, oz + b["thickness"]), "purchased", "FR4", "chs_main", color=C["pcb"], mass=0.22, mpn="RR-CHS-MAIN rev A (custom)", verified="contract outline"))
    top = oz + b["thickness"]
    keep = box(ox, ox + h_, oy - w_, oy, top, top + b["max_top"])
    for (u0, u1, v0, v1) in LOW_ZONES_UV:                     # 12 mm zones: front corners (board_envelopes.yaml) and rear corners (CCR-E08)
        keep = keep.cut(box(ox + v0, ox + v1, oy - u1, oy - u0, top + 12.0, top + b["max_top"] + 1))
    add(Part("RRX-E01", "RR-CHS-MAIN_top_parts", keep, "purchased", "KEEPOUT", "chs_main", color=C["keep"], mass=0.0,
             verified="18 mm top envelope; 12 mm in the front corners (board_envelopes.yaml) and rear corners (CCR-E08 request)"))
    add(Part("RRX-E01", "RR-CHS-MAIN_bottom_parts", box(ox, ox + h_, oy - w_, oy, oz - b["max_bottom"], oz), "purchased", "KEEPOUT", "chs_main", color=C["keep"], mass=0.0, mates={"*standoff*"}))
    c = P.CM5_POSE
    e = L.env("cm5_carrier")
    add(Part("RRX-H46", "CM5_carrier_assembly", box(c["x"][0], c["x"][1], c["y"][0], c["y"][1], c["pcb_z"] - 3, c["pcb_z"] - 3 + e["h_assembled"]), "purchased", "PCB", "compute", color=C["comp"],
             mass=L.mass("cm5") + L.mass("cm5_carrier") + 0.04, mpn="Raspberry Pi CM5104032 on Waveshare CM5-IO-BASE-A + heat sink", verified="outline VERIFIED, height/holes UNVERIFIED", mates={"cm5_tray"}))
    lx, ly = P.LIDAR_POSE["xy"]
    add(Part("RRX-H47", "lidar", L.lidar().moved(cq.Location(cq.Vector(lx, ly, P.LIDAR_POSE["base_z"]))), "purchased", "AL", "lidar", color=C["lidar"], mass=L.mass("lidar"), internal=False,
             mpn=L.PARTS["lidar"]["mpn"], verified="footprint PARTIAL; scan plane, holes, connector UNVERIFIED", mates={"battery_hump"}))
    pc = P.PANEL_CONTROLS["annunciator"]["xyz"]
    pe = L.env("panel_board")
    zt = pc[2] - P.PANEL_BOARD["below_skin"]
    add(Part("RRX-E02", "RR-PANEL", box(pc[0] - pe["l"] / 2, pc[0] + pe["l"] / 2, pc[1] - pe["w"] / 2, pc[1] + pe["w"] / 2, zt - pe["h"], zt), "purchased", "FR4", "controls", color=C["pcb"],
             mass=L.mass("panel_board"), mpn="RR-PANEL (custom)", verified="contract outline", mates={"panel_tray"}))
    kinds = {"estop": "estop", "hands_on": "pushbutton_22", "mode_selector": "mode_selector", "rearm_start": "pushbutton_22", "pause_stop": "pushbutton_22"}
    for name, kind in kinds.items():
        ctl = P.PANEL_CONTROLS[name]
        head, body = L.panel_device(kind)
        side = "rear_deck_L" if ctl["xyz"][1] > 0 else "rear_deck_R"
        pn = {"estop": "RRX-H50", "mode_selector": "RRX-H55", "pushbutton_22": "RRX-H56"}[kind]
        add(Part(pn, f"{name}_operator", place(head, ctl["xyz"], ctl["normal"]), "purchased", "PA", "controls", color=C["ctl"], internal=False, mass=0.0, mates={f"{name}_body", side}))
        add(Part(pn, f"{name}_body", place(body, ctl["xyz"], ctl["normal"]), "purchased", "PA", "controls", color=C["ctl"], internal=False, mass=L.mass(kind),
                 mpn=L.PARTS[kind]["mpn"], verified=str(L.PARTS[kind]["verification"])[:60], mates={f"{name}_operator", side}))
    rec, _ = L.inlet()
    ci = P.CHARGE_INLET
    add(Part("RRX-H51", "charge_inlet", place(rec, ci["xyz"], ci["normal"]), "purchased", "BRASS", "charge", color=C["conn"], internal=False, mass=L.mass("charge_inlet"),
             mpn=L.PARTS["charge_inlet"]["mpn"], verified="UNVERIFIED", mates={"rear_deck_R", "inlet_cover"}))
    for jn, key in (("J1", "j1_receptacle"), ("J2", "j2_receptacle")):
        j = P.J_RECEPTACLES[jn]
        rec, plug, nut = L.receptacle(key)
        add(Part("RRX-H52" if jn == "J1" else "RRX-H57", f"{jn}_receptacle", place(rec, j["xyz"], j["normal"]), "purchased", "BRASS", "connectors", color=C["conn"], internal=False, mass=L.mass(key),
                 mpn=L.PARTS[key]["mpn"], verified="UNVERIFIED cut-out", mates={"nose_cowl", f"{jn}_mated_plug"}))
        add(Part("RRX-H52", f"{jn}_mated_plug", place(plug, j["xyz"], j["normal"]), "purchased", "BRASS", "head_placeholder", color=C["conn"], internal=False, mass=0.0, hard=True,
                 mates={f"{jn}_receptacle", "nose_cowl"}))
    for name, t in P.TOF_SENSORS.items():
        xdir = (1.0, 0.0, 0.0) if name.startswith("tof_cliff_f") else S.seat_xdir(t["dir"], S.seat_kind(name))
        brd = box(-9.0, 9.0, -7.0, 7.0, -6.0, -2.7)
        add(Part("RRX-E03", name, place(brd, t["xyz"], t["dir"], xdir), "purchased", "FR4", "tof", color=C["sens"], internal=False, mass=L.mass("tof_board"), mpn="RR-TOF (custom, VL53L4ED)", verified="contract outline",
                 mates={"*"}))
    sw = L.switch()
    for name, xyz in P.BODY_BUMPER_SWITCHES.items():
        tag = "L" if xyz[1] > 0 else "R"
        d = D.BUMPER_DIR[tag]
        add(Part("RRX-H53", name, place(box(-6.65, 6.65, -2.65, 2.65, -10.8, -3.8), xyz, (-d[0], -d[1], 0.0)), "purchased", "PBT", "bumper", color=C["sens"], internal=False, mass=0.004,
                 mpn=L.PARTS["bumper_switch"]["mpn"], verified="dimensions PARTIAL", mates={"*"}))
    x, y, z = P.HEAD_DOCK_SWITCH
    add(Part("RRX-H53", "head_dock_switch", box(x - 3.5, x + 3.0, y - 6.65, y + 6.65, z - 2.65, z + 2.65), "purchased", "PBT", "receiver", color=C["sens"], internal=False, mass=0.004,
             mpn=L.PARTS["bumper_switch"]["mpn"], verified="dimensions PARTIAL", mates={"dock_switch_bracket"}))
    lb = P.RECEIVER["latch_box"]
    add(Part("RRX-H54", "head_latch", box(*lb), "purchased", "SS304", "receiver", color=C["ctl"], internal=False, mass=0.05,
             mpn="over-centre draw latch, stainless, 25 mm glove loop (Southco C7 / Protex class)", verified="UNVERIFIED selection; envelope from interfaces", mates={"latch_arm", "nose_cowl", "head_envelope"}))
    add(Part("RRX-H54", "hatch_latch", box(-228.0, -204.0, 26.0, 44.0, B["hump_z"][1], B["hump_z"][1] + 12.0), "purchased", "SS304", "hatch", color=C["ctl"], internal=False, mass=0.05,
             mpn="over-centre draw latch (same type as the head latch)", verified="UNVERIFIED selection", mates={"battery_hump", "hatch_door"}))


def head_placeholder(add):
    he, RC = P.HEAD_ENV_E, P.RECEIVER
    env = box(he["x"][0] + 2.8, D.HEAD_X1, he["y"][0], he["y"][1], he["z"][0], he["z"][1])
    add(Part("HEAD", "head_envelope", env, "placeholder", "-", "head_placeholder", color="#344c51", internal=False, mass=0.0, mates={"head_latch", "head_shoe_L", "head_shoe_R"}))
    for tag, s in (("L", 1), ("R", -1)):
        yc = s * RC["shoe_y"]
        shoe = box(RC["shoe_x"][0], he["x"][0] + 2.8, yc - RC["shoe_width"] / 2, yc + RC["shoe_width"] / 2, *RC["shoe_z"])
        sh = fuse(shoe, box(RC["x_stop"], he["x"][0] + 2.8, yc - 25.0, yc + 25.0, RC["shoe_z"][0], RC["shoe_z"][1]))      # shoulders seating on datum A
        add(Part("HEAD", f"head_shoe_{tag}", sh, "placeholder", "-", "head_placeholder", color="#58666e", internal=False, mass=0.0,
                 mates={f"receiver_channel_{tag}", f"land_pin_{tag}0", f"land_pin_{tag}1", "head_envelope"}))


def build(verbose=True):
    parts: list[Part] = []
    t0 = time.time()

    def add(p):
        if p.shape is None:
            raise ValueError(f"no shape: {p.name}")
        if p.kind in ("printed", "fabricated") and len(p.shape.Solids()) > 1:
            # boolean slivers: keep the main body, record what was dropped (checked: must stay below SLIVER_MAX)
            sol = sorted(p.shape.Solids(), key=lambda q: -q.Volume())
            p.dropped = [round(q.Volume(), 1) for q in sol[1:]]
            p.shape = sol[0]
            p.bb = bounds(p.shape)
            if p.local is not None and len(p.local.Solids()) > 1:
                p.local = max(p.local.Solids(), key=lambda q: q.Volume())
        parts.append(p)

    for mod in (structure, battery, shells, running):
        t = time.time()
        mod.build(add)
        if verbose:
            print(f"  {mod.__name__.split('.')[-1]:10s} {time.time() - t:6.1f} s  ({len(parts)} parts)", flush=True)
    purchased(add)
    head_placeholder(add)
    names = [p.name for p in parts]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"duplicate part names: {dup}")
    if verbose:
        print(f"  assembly built: {len(parts)} parts in {time.time() - t0:.1f} s", flush=True)
    return parts
