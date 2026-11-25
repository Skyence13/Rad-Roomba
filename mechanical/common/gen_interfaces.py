"""Generate board_envelopes.yaml, frames.yaml and the board envelope STEP solids from params.py.

Run:  python -m mechanical.common.gen_interfaces   (from the repository root)
Evidence class of every number: calculated from params.py; fit is tool-checked by layout.py.
"""
from __future__ import annotations

import sys

import yaml

from . import params as P

R = lambda v, n=2: [round(float(c), n) for c in v]   # noqa: E731


def holes(board):
    out = []
    for i, (u, v) in enumerate(board["holes_uv"], 1):
        out.append({"id": f"H{i}", "board_uv_mm": [u, v], "base_link_xyz_mm": R(P.board_to_base(board["origin"], u, v))})
    return out


def corners(board):
    w, h = board["outline"]
    return {k: R(P.board_to_base(board["origin"], u, v)) for k, (u, v) in
            {"rear_left_origin": (0, 0), "rear_right": (w, 0), "front_right": (w, h), "front_left": (0, h)}.items()}


CONVENTION = ("Board frame: origin at the rear-left corner seen from above with robot-forward up; +u toward robot right "
              "(= -y of base_link), +v forward (= +x of base_link), +w up (= +z); top/component side faces +z. "
              "base_link = origin + (v, -u, w). Origin z is the PCB UNDERSIDE. All dimensions mm.")


def head_acq():
    b = P.HEAD_ACQ
    lane_u = [round(b["origin"][1] - y, 2) for y in P.SEG_Y]
    return {
        "status": "CONFIRMED with one correction (PCB underside z 33.0 -> 34.5)",
        "outline_mm": list(b["outline"]), "shape": "rectangle, corner radius <= 1.0",
        "thickness_mm": b["thickness"], "layers": P.BOARDS_C["RR-HEAD-ACQ"]["layers"],
        "origin_base_link_mm": R(b["origin"]), "orientation": "long axis (u) along -y; rpy = (0, 0, -90 deg) from base x to board u",
        "centre_base_link_mm": R(P.board_to_base(b["origin"], b["outline"][0] / 2, b["outline"][1] / 2)),
        "corners_base_link_mm": corners(b),
        "mounting": {"screw": "8 x M2.5 into standoffs clinched in the spreader plate (standoff height 2.5 mm)",
                     "hole_diameter_mm": b["hole_d"], "pad_keepout_diameter_mm": b["hole_keepout_d"], "holes": holes(b),
                     "rationale": "Six holes on the three inactive lane seams (y = +87.5, 0, -87.5) so the four lane circuits stay identical and unbroken; two end holes at mid-height carry the 75 mm end overhangs. Longest unsupported span 87.5 mm."},
        "max_height_top_mm": b["max_top"], "max_height_bottom_mm": b["max_bottom"],
        "height_headroom_note": "Head top is z = 45.0 against the 50.0 ceiling. Each extra mm of top-side height raises the cover 1:1; up to 11 mm top-side is possible before the ceiling, but costs look-ahead sightline margin (see out/mech_calcs.md). Request before using it.",
        "lane_centre_u_mm": {f"S{i}": u for i, u in enumerate(lane_u)},
        "zones_uv_mm": [
            {"id": "AFE_STRIP", "u": [0, 326], "v": [0, 30], "top_max": 6.0, "bottom_max": 2.0,
             "use": "Eight SiPM front ends. Pigtail connector pairs (floor + reference) on the REAR edge centred on each lane centre u (+/-13 mm): the SiPM carriers stand in the rear chimney (base x 151.4..152.9) directly below this edge at z 11..28.5, so the pigtails are < 35 mm long. Per-lane NTC travels in the same pigtail."},
            {"id": "J1_LANDING", "u": [50, 100], "v": [0, 18], "top_max": 6.0,
             "use": "J1 pigtail (power, heater pair, interlock loop, PRES_ID) + heater-film tail + spreader NTC. On the S0|S1 seam (y = +87.5): the cable enters through the rear wall at this y. Excludes the H1 pad."},
            {"id": "J2_LANDING", "u": [226, 276], "v": [0, 18], "top_max": 6.0,
             "use": "J2 pigtail (RS-485, BUS_5V, sync pair, J2_PRES). On the S2|S3 seam (y = -87.5). Isolation barrier belongs here. Excludes the H3 pad."},
            {"id": "RAIL_SWITCH_LANDING", "u": [150, 176], "v": [84, 96], "top_max": 6.0,
             "use": "Three head rail switches (front, left, right NC loop) land on the FRONT edge centre; leads run in the front wall channel."},
            {"id": "DIGITAL_POWER", "u": [0, 326], "v": [30, 84], "top_max": 6.0, "bottom_max": 2.0,
             "use": "Bias supply, DACs, comparators, FPGA, MCU, rails. Heater switch next to J1_LANDING; keep heater current out of AFE_STRIP (route in v > 30)."},
            {"id": "SERVICE", "u": [100, 226], "v": [84, 96], "top_max": 6.0,
             "use": "SWD/JTAG, 50 ohm monitor output, test points: reachable with the cover off, no external opening."},
        ],
        "keepouts": [
            "6.0 mm diameter around every mounting hole, both sides (standoff + screw head).",
            "1.5 mm from every edge for copper/components; no part may overhang the rear edge (chimney is 9 mm deep in x).",
            "Bottom side: 2.0 mm max everywhere; 0.25 mm polyimide/Formex sheet lies on the spreader.",
            "Key-socket collar (base x <= 153.8, |y| <= 39.75, top z = 42.0) is 2.2 mm behind the rear edge between u = 123 and 203: no cable may leave rearward there.",
        ],
        "cable_exits": {
            "sipm_pigtails": "down (-z) off the rear edge into the chimney at each lane centre",
            "J1": f"rear wall port at base {R(P.HEAD_PIGTAIL_EXIT['J1'])}, cable leaves the head toward -x/+z, strain relief inside the wall",
            "J2": f"rear wall port at base {R(P.HEAD_PIGTAIL_EXIT['J2'])}, cable leaves the head toward -x/+z",
            "heater_and_ntc": "heater film is bonded under the spreader; its tail and the spreader NTC come up the chimney at y = +87.5 to J1_LANDING",
        },
        "contract_deviation": "PCB underside z = 34.5 (contract nominal 33.0). Reason: a 2.0 mm structural spreader plate plus 1.5 mm module retention pad/heater sit between the reference guides (top z 28.5) and the board, and the 2.0 mm bottom-side allowance needs 2.5 mm of gap. Outline, hole count and both height limits are unchanged.",
    }


def chs_main():
    b = P.CHS_MAIN
    return {
        "status": "CONFIRMED (160 x 100 rectangle) -- but ONLY in the Rev E body proposal; it does NOT fit the Rev D body",
        "does_not_fit_rev_d": "The Rev D shell cavity is 191 mm wide between wheel wells and <= 76 mm tall with the hand well, motors, battery and LiDAR in it; no 160 x 100 x 22.6 mm slot exists at any orientation (see out/layout_report.md, section 'Rev D containment'). Rev E body proposal: Rev D form scaled 1.30 (width, height) / 1.40 (length).",
        "outline_mm": list(b["outline"]), "shape": "rectangle, corner radius <= 2.0",
        "thickness_mm": b["thickness"], "layers": P.BOARDS_C["RR-CHS-MAIN"]["layers"],
        "origin_base_link_mm": R(b["origin"]), "orientation": "long axis (u) along -y, horizontal, top side up; rpy = (0, 0, -90 deg) from base x to board u",
        "centre_base_link_mm": R(P.board_to_base(b["origin"], 80, 50)),
        "corners_base_link_mm": corners(b),
        "position_rationale": "Flat on a 2 mm aluminium bridge tray over the two gearmotors, under the removable carry-grip saddle cover (service access from above, no shell split needed). Centre of the board is 17 mm behind the axle.",
        "mounting": {"screw": "6 x M3 into standoffs on the electronics bridge (standoff height 3.0 mm)",
                     "hole_diameter_mm": b["hole_d"], "pad_keepout_diameter_mm": b["hole_keepout_d"], "holes": holes(b)},
        "max_height_top_mm": b["max_top"], "max_height_bottom_mm": b["max_bottom"],
        "zones_uv_mm": [
            {"id": "FRONT_CORNER_LOW", "u": [[0, 14], [146, 160]], "v": [88, 100], "top_max": 12.0,
             "use": "Only height restriction: the shell roof closes in on the two front corners."},
            {"id": "THERMAL_TO_BRIDGE", "u": [50, 110], "v": [30, 70], "bottom_max": 3.0,
             "use": "Preferred place for the H-bridges and the 5 V converter: a 3 mm gap pad on the bottom side couples them to the aluminium bridge tray."},
            {"id": "IMU", "u": [74, 86], "v": [61, 73], "use": "Reserved BMI088 footprint centred (80, 67): exactly above base_link origin (yaw centre). imu_link in frames.yaml assumes it."},
        ],
        "connector_edges": {
            "right_edge_rear  (u = 160, v 4..34)": "POWER ENTRY: pack feed from the blind-mate coupler (under the board, routed around the right side), charge inlet feed (inlet is on the right rear quarter), bus-clamp resistor. Main protection, charger and latch/brake relays belong in this corner.",
            "right_edge_front (u = 160, v 68..96)": "Right motor + encoder, right look-ahead ToF (in the right grip cheek).",
            "left_edge_front  (u = 0, v 68..96)": "Left motor + encoder, left look-ahead ToF.",
            "left_edge_rear   (u = 0, v 4..34)": "HOST: USB to the CM5 and the 5.1 V compute feed (CM5 carrier is in the left rear bay), LiDAR 12 V.",
            "rear_corners     (v = 0, u 0..25 and 135..160)": "left: RR-PANEL, selector / REARM / Pause; rear ToF x5, body bumper switches. right: E-stop (2 poles), HANDS-ON, charge-cover switch, chassis heater + bay NTCs.",
            "front_edge       (v = 100, u 8..40)": "J1 feed (HEAD_PWR, HEAD_HTR, loop, PRES_ID) to the left shoulder receptacle.",
            "front_edge       (v = 100, u 120..152)": "J2 feed (RS-485, BUS_5V, sync, J2_PRES) to the right shoulder receptacle.",
            "front_edge       (v = 100, u 50..110)": "Front cliff ToF x2, HEAD_DOCK switch.",
        },
        "keepouts": [
            "NO connectors on the rear edge between u = 26 and 134: the battery cassette top (z 110) stands 3.5 mm behind it.",
            "NO connectors on the left/right edges between v = 34 and 68: the grip cheek legs stand 4 mm outboard of the board there.",
            "7.0 mm diameter around every mounting hole, both sides.",
            "Top-entry plugs are not possible above 18 mm: the saddle cover underside is 20.4 mm above the PCB top. Use right-angle or low-profile vertical headers.",
        ],
        "cable_exits": "Horizontally outward from the named edges; side bays (|y| 80..115) and the front bay (x > 33) are the cable corridors.",
        "contract_deviation": "None for the board itself. Requires body proposal D-1 (CCR-03).",
    }


def small_boards():
    return {
        "RR-TOF": {"status": "CONFIRMED", "outline_mm": list(P.TOF_BOARD["outline"]),
                   "note": "Sensor on the board centre; long axis tangent to the skin. 6 mm depth behind a 1 mm window, window clear aperture >= 8 x 6 mm (emitter/receiver split by a light barrier). 11 positions in frames.yaml."},
        "RR-PANEL": {"status": "CONFIRMED", "outline_mm": list(P.PANEL_BOARD["outline"]),
                     "centre_base_link_mm": R(P.PANEL_CONTROLS["annunciator"]["xyz"]),
                     "orientation": "long axis along y, component side up under the top skin between grip and LiDAR; max height top 8 mm (light pipes), bottom 3 mm",
                     "note": "Buttons are separate 22 mm panel devices on the left/right rear decks; the board carries only LEDs, buzzer and the harness landing."},
    }


def board_doc():
    return {
        "generated_by": "mechanical/common/gen_interfaces.py from params.py -- do not edit by hand",
        "contract_version": P.CONTRACT_VERSION, "evidence_class": "calculated (fit tool-checked by layout.py)",
        "convention": CONVENTION,
        "head_stack_up": {
            "datum": "Optical stack below z = 28.5 is Rev D, unchanged (entrance film z = 10.0).",
            "layers_z_mm": [{"layer": n, "z": [a, b], "note": note} for n, a, b, note in P.HEAD_STACK],
            "head_top_z_mm": P.HEAD_TOP_Z, "ceiling_z_mm": P.HEAD_ENV_E_CEILING["z"][1],
            "head_envelope_rev_e_used_mm": {k: list(v) for k, v in P.HEAD_ENV_E.items()},
            "order_rationale": "Spreader between optics and board: it heats the optical modules uniformly, screens the SiPMs from the logic, takes the board's own dissipation and bridges the printed y = 0 split. Board above it stays accessible under the cover.",
        },
        "RR-HEAD-ACQ": head_acq(), "RR-CHS-MAIN": chs_main(), **small_boards(),
    }


def frames_doc():
    f = {"generated_by": "mechanical/common/gen_interfaces.py from params.py -- do not edit by hand",
         "contract_version": P.CONTRACT_VERSION, "parent": "base_link", "units": {"xyz": "m", "rpy": "rad", "dir": "unit vector in base_link"},
         "status": "Rev E PROPOSAL (body proposal D-1 pending lead decision). Evidence class: calculated."}
    m = lambda v: [round(float(c) / 1000.0, 5) for c in v]   # noqa: E731
    lx, ly = P.LIDAR_POSE["xy"]
    frames = {
        "lidar_link": {"xyz": m((lx, ly, P.LIDAR_POSE["base_z"] + P.LIDAR_SCAN_PLANE_ABOVE_BASE)), "rpy": [0, 0, 0],
                       "note": "scan plane; height above the LiDAR base is UNVERIFIED (assumed 60 mm). 270 deg field centred on +x, blind sector to the rear."},
        "imu_link": {"xyz": m(P.IMU_POSE["xyz"]), "rpy": list(P.IMU_POSE["rpy"]), "note": P.IMU_POSE["note"]},
        "head_mount": {"xyz": m(P.HEAD_MOUNT), "rpy": [0, 0, 0], "note": "contract datum, unchanged"},
    }
    for i, y in enumerate(P.SEG_Y):
        frames[f"seg{i}_aperture"] = {"xyz": m((P.ROW_X, y, P.FILM_Z)), "rpy": [0, 0, 0], "parent_alt": "head_mount",
                                      "xyz_in_head_mount": m((P.ROW_X - P.HEAD_MOUNT[0], y, P.FILM_Z - P.HEAD_MOUNT[2])),
                                      "size_xy": m((P.ACTIVE_X, P.ACTIVE_Y)), "note": "centre of the entrance film, normal -z"}
    f["frames"] = frames
    f["tof"] = {k: {"xyz": m(v["xyz"]), "dir": [round(c, 5) for c in v["dir"]], "purpose": v["purpose"],
                    "fov_full_deg": P.TOF_FOV_FULL_DEG} for k, v in P.TOF_SENSORS.items()}
    f["panel_controls"] = {k: {"xyz": m(v["xyz"]), "normal": [round(c, 4) for c in v["normal"]], "desc": v["desc"]}
                           for k, v in P.PANEL_CONTROLS.items()}
    f["connectors"] = {k: {"xyz": m(v["xyz"]), "mating_axis": [round(c, 4) for c in v["normal"]], "family": v["family"], "side": v["side"]}
                       for k, v in P.J_RECEPTACLES.items()}
    f["connectors"]["charge_inlet"] = {"xyz": m(P.CHARGE_INLET["xyz"]), "mating_axis": [round(c, 4) for c in P.CHARGE_INLET["normal"]], "desc": P.CHARGE_INLET["desc"]}
    f["connectors"]["head_pigtail_exits"] = {k: m(v) for k, v in P.HEAD_PIGTAIL_EXIT.items()}
    f["kinematics"] = {"track_m": P.TRACK / 1000, "wheel_radius_m": P.WHEEL_R / 1000, "axle_height_m": P.AXLE_Z / 1000,
                       "caster_swivel_xy_m": m(P.CASTER_SWIVEL + (0,))[:2],
                       "note": "track and caster differ from contract 0.4.0-draft1 (220 mm; -100/-116): see CONTRACT_CHANGE_REQUESTS.md CCR-01/02"}
    f["footprint"] = {"body_x_m": [round(P.BODY_TAIL_X / 1000, 4), round(P.BODY_NOSE_X / 1000, 4)],
                      "head_envelope_m": {k: m(v) for k, v in P.HEAD_ENV_E.items()},
                      "note": "tool-checked extents are in out/layout_report.md"}
    return f


def dump(path, doc, header):
    path.write_text(header + yaml.safe_dump(doc, sort_keys=False, width=160, allow_unicode=True), encoding="utf-8")


def board_step():
    import cadquery as cq
    (P.OUT / "boards").mkdir(parents=True, exist_ok=True)
    for name, b in (("RR-HEAD-ACQ", P.HEAD_ACQ), ("RR-CHS-MAIN", P.CHS_MAIN)):
        w, h = b["outline"]
        ox, oy, oz = b["origin"]
        def slab(z0, t):
            return cq.Workplane("XY", origin=(ox + h / 2, oy - w / 2, z0)).box(h, w, t, centered=(True, True, False)).val()
        pcb = slab(oz, b["thickness"])
        for u, v in b["holes_uv"]:
            x, y, _ = P.board_to_base(b["origin"], u, v)
            pcb = pcb.cut(cq.Solid.makeCylinder(b["hole_d"] / 2, 5, cq.Vector(x, y, oz - 1)))
        asm = cq.Assembly(name=name)
        asm.add(pcb, name=f"{name}_pcb", color=cq.Color("#2e7d4f"))
        asm.add(slab(oz + b["thickness"], b["max_top"]), name=f"{name}_top_component_envelope", color=cq.Color(0.9, 0.7, 0.2, 0.35))
        asm.add(slab(oz - b["max_bottom"], b["max_bottom"]), name=f"{name}_bottom_component_envelope", color=cq.Color(0.9, 0.5, 0.2, 0.35))
        asm.export(str(P.OUT / "boards" / f"{name}_envelope.step"))


def main():
    P.OUT.mkdir(exist_ok=True)
    dump(P.HERE / "board_envelopes.yaml", board_doc(),
         "# Rad Roomba board envelopes -- mechanical lead's confirmation of contract.yaml > boards.\n"
         "# Positions are in base_link (mm) for the Rev E layout. STEP solids: out/boards/*.step\n")
    dump(P.HERE / "frames.yaml", frames_doc(),
         "# Rad Roomba static frames for the robot software (base_link -> sensors, head, controls, connectors).\n")
    if "--no-step" not in sys.argv:
        board_step()
    print("wrote board_envelopes.yaml, frames.yaml" + ("" if "--no-step" in sys.argv else ", out/boards/*.step"))


if __name__ == "__main__":
    main()
