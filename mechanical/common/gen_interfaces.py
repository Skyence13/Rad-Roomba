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
        "status": "CONFIRMED as built (IB-52): H1 at (75.5, 30.0) [CR-M02], J1 landing u 50..101 with 8 mm local height [CCR-HE-02], shield cans at v 8.25..40.25 [CR-M01]; source electronics/head_acq/layout.py HOLES, libs.py, STAGE2_CHANGE_REQUESTS.md. Origin x %.1f (mount option C, CCR-11)" % b["origin"][0],
        "outline_mm": list(b["outline"]), "shape": "rectangle, corner radius <= 1.0",
        "thickness_mm": b["thickness"], "layers": P.BOARDS_C["RR-HEAD-ACQ"]["layers"],
        "origin_base_link_mm": R(b["origin"]), "orientation": "long axis (u) along -y; rpy = (0, 0, -90 deg) from base x to board u",
        "centre_base_link_mm": R(P.board_to_base(b["origin"], b["outline"][0] / 2, b["outline"][1] / 2)),
        "corners_base_link_mm": corners(b),
        "mounting": {"screw": "8 x M2.5 into standoffs clinched in the spreader plate (standoff height 2.5 mm)",
                     "hole_diameter_mm": b["hole_d"], "pad_keepout_diameter_mm": b["hole_keepout_d"], "holes": holes(b),
                     "rationale": "Holes on the three inactive lane seams (y = +87.5, 0, -87.5) so the four lane circuits stay identical and unbroken; H1 moved to v 30 (CR-M02) because the J1 header sits on the rear edge; two end holes at mid-height carry the 75 mm end overhangs. Longest unsupported span 87.5 mm."},
        "max_height_top_mm": b["max_top"], "max_height_bottom_mm": b["max_bottom"],
        "height_headroom_note": "Head top is z = 45.0 against the 50.0 ceiling. Each extra mm of top-side height raises the cover 1:1; up to 11 mm top-side is possible before the ceiling, but costs look-ahead sightline margin (see out/mech_calcs.md). Request before using it.",
        "lane_centre_u_mm": {f"S{i}": u for i, u in enumerate(lane_u)},
        "zones_uv_mm": [
            {"id": "AFE_STRIP", "u": [0, 326], "v": [0, 30], "top_max": 6.0, "bottom_max": 2.0,
             "use": "Eight SiPM front ends. Pigtail connector pairs (floor + reference) on the REAR edge centred on each lane centre u (+/-13 mm): the SiPM carriers stand in the rear chimney (9 mm deep, directly behind the spreader) below this edge at z 11..28.5, so the pigtails are < 35 mm long. Per-lane NTC travels in the same pigtail."},
            {"id": "J1_LANDING", "u": [50, 101], "v": [0, 18], "top_max": 8.0,
             "use": "J1 pigtail (8-way J2001, body u 73.0..100.7) + heater/NTC (6-way J2601, body u 50.2..72.0): rear-facing Micro-Fit headers, pin row v 10.57, mating faces v 1.5, mated plugs overhang the rear edge to v -8.4 "
                    "(electronics/head_acq/layout.py, STAGE2_CHANGE_REQUESTS.md S2-L5, CR-M03). top_max 8.0 under the 8.9 mm head-lid blister (CCR-HE-02 accepted, CR-M05; header seat height <= 6.0 UNVERIFIED). "
                    "The board centres J2001 on y = 76.2 (u 86.8); CR-M03 asks head mechanical to move the J1 cable port there (head-owned, `HEAD_PIGTAIL_EXIT`)."},
            {"id": "LANE_SHIELD_CANS", "u": [[lc - 18.0, lc + 18.0] for lc in lane_u], "v": [8.25, 40.25], "top_max": 5.0,
             "use": "RR-HEAD-SHLD-A cans 36 x 32 x 5 mm (0.2 mm wall) per lane, rear outer face v 8.25 (+2.75 mm, CR-M01; electronics/head_acq/libs.py CAN_V0/CAN_D); anode mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04)."},
            {"id": "J2_LANDING", "u": [226, 276], "v": [0, 18], "top_max": 6.0,
             "use": "J2 pigtail (RS-485, BUS_5V, sync pair, J2_PRES). On the S2|S3 seam (y = -87.5). Isolation barrier belongs here. Excludes the H3 pad."},
            {"id": "RAIL_SWITCH_LANDING", "u": [150, 176], "v": [84, 96], "top_max": 6.0,
             "use": "Three head rail switches (front, left, right NC loop) land on the FRONT edge centre; leads run in the front wall channel."},
            {"id": "DIGITAL_POWER", "u": [0, 326], "v": [30, 84], "top_max": 6.0, "bottom_max": 2.0,
             "use": "Bias supply, DACs, comparators, event logic and head MCU (100-pin LQFP, DEC-037: no FPGA; 1.6 mm package height is inside the 6.0 mm limit), rails. Heater switch next to J1_LANDING; keep heater current out of AFE_STRIP (route in v > 30)."},
            {"id": "SERVICE", "u": [100, 226], "v": [84, 96], "top_max": 6.0,
             "use": "SWD/JTAG, 50 ohm monitor output, test points: reachable with the cover off, no external opening."},
        ],
        "keepouts": [
            "6.0 mm diameter around every mounting hole, both sides (standoff + screw head).",
            "1.5 mm from every edge for copper/components; no part may overhang the rear edge (chimney is 9 mm deep in x).",
            "Bottom side: 2.0 mm max everywhere; 0.25 mm polyimide/Formex sheet lies on the spreader.",
            "Mount option C (DEC-041): no socket collar behind the board any more. The two bearing shoes are below the board (z 16..30) on the seams; the J1/J2 ports sit above them at z = 39.",
        ],
        "cable_exits": {
            "sipm_pigtails": "down (-z) off the rear edge into the chimney at each lane centre",
            "J1": f"rear wall port at base {R(P.HEAD_PIGTAIL_EXIT['J1'])}, cable leaves the head toward -x/+z, strain relief inside the wall",
            "J2": f"rear wall port at base {R(P.HEAD_PIGTAIL_EXIT['J2'])}, cable leaves the head toward -x/+z",
            "heater_and_ntc": "heater film is bonded under the spreader; its tail and the spreader NTC come up the chimney at y = +87.5 to J1_LANDING",
        },
        "contract_deviation": "Origin x in base_link is %.1f (contract 0.4.0-draft4 says 156.0): the head moves 72.8 mm rearward with mount option C (CCR-11). In the head_mount frame nothing moves: origin = (+17.5, +163.0, +2.5) from the mount datum. Note for the layout: the board rear edge is now about 65 mm ahead of the gearmotor cans." % b["origin"][0],
    }


def chs_main():
    b = P.CHS_MAIN
    return {
        "status": "CONFIRMED (160 x 100 rectangle) in the adopted Rev E body (DEC-039); unchanged by the 12 Ah pack and by mount option C",
        "outline_mm": list(b["outline"]), "shape": "rectangle, corner radius <= 2.0",
        "thickness_mm": b["thickness"], "layers": P.BOARDS_C["RR-CHS-MAIN"]["layers"],
        "origin_base_link_mm": R(b["origin"]), "orientation": "long axis (u) along -y, horizontal, top side up; rpy = (0, 0, -90 deg) from base x to board u",
        "centre_base_link_mm": R(P.board_to_base(b["origin"], 80, 50)),
        "corners_base_link_mm": corners(b),
        "position_rationale": "Flat on a 2 mm aluminium bridge tray over the two gearmotors, under the removable carry-grip saddle cover (service access from above, no shell split needed). Centre of the board is 17 mm behind the axle.",
        "pack_and_receiver_note": "12 Ah baseline pack (DEC-040): the cassette top is now z = 144 and stands 6.5 mm behind the rear edge (was z = 110, 3.5 mm). The blind-mate coupler is still under the board on the centre line (x -73.5..-16).",
        "mounting": {"screw": "6 x M3 into standoffs on the electronics bridge (standoff height 3.0 mm)",
                     "hole_diameter_mm": b["hole_d"], "pad_keepout_diameter_mm": b["hole_keepout_d"], "holes": holes(b)},
        "max_height_top_mm": b["max_top"], "max_height_bottom_mm": b["max_bottom"],
        "zones_uv_mm": [
            {"id": "FRONT_CORNER_LOW", "u": [[0, 14], [146, 160]], "v": [88, 100], "top_max": 12.0,
             "use": "The shell roof closes in on the two front corners."},
            {"id": "REAR_CORNER_LOW", "u": [[0, 45], [112, 160]], "v": [[0, 20], [0, 22]], "top_max": 12.0,
             "use": "Rear corners (chassis electronics CCR-E08 request, CR-06): the saddle-cover rear screw bosses hang to 13.0 mm above the PCB here."},
            {"id": "THERMAL_TO_BRIDGE", "u": [50, 110], "v": [30, 70], "bottom_max": 3.0,
             "use": "Preferred place for the H-bridges and the 5 V converter: a 3 mm gap pad on the bottom side couples them to the aluminium bridge tray."},
            {"id": "IMU", "u": [74, 86], "v": [61, 73], "use": "Reserved BMI088 footprint centred (80, 67): exactly above base_link origin (yaw centre). imu_link in frames.yaml assumes it."},
        ],
        "connector_edges": {
            "right_edge_rear  (u = 160, v 4..34)": "POWER ENTRY: pack feed from the blind-mate coupler (under the board, routed around the right side), charge inlet feed (inlet is on the right rear quarter). Main protection, charger and latch/brake relays belong in this corner.",
            "right_edge_front (u = 160, v 72..96)": "Right motor + encoder, right look-ahead ToF (in the right grip cheek).",
            "left_edge_front  (u = 0, v 72..96)": "Left motor + encoder, left look-ahead ToF.",
            "left_edge_rear   (u = 0, v 4..34)": "HOST: USB to the CM5 and the 5.1 V compute feed (CM5 carrier is in the left rear bay), LiDAR 12 V.",
            "rear_corners     (v = 0, u 0..18 and 142..160)": "left: RR-PANEL, selector / REARM; rear ToF x5, body bumper switches. right: E-stop (2 poles), HANDS-ON, Pause/Stop, charge-cover switch, chassis heater + bay NTCs. Only 18 mm of rear edge is free each side of the battery hump: put the larger connectors on the left/right edge rear zones.",
            "front_edge       (v = 100, u 8..40)": "J1 feed (HEAD_PWR, HEAD_HTR, loop, PRES_ID) to the left shoulder receptacle.",
            "front_edge       (v = 100, u 120..152)": "J2 feed (RS-485, BUS_5V, sync, J2_PRES) to the right shoulder receptacle.",
            "front_edge       (v = 100, u 50..110)": "Front cliff ToF x2 (on the chassis front beam beside the tyres), HEAD_DOCK switch (behind the left receiver channel), head latch switch if fitted.",
        },
        "keepouts": [
            "NO connectors on the rear edge between u = 20 and 140: the battery hump front wall and cassette (top z 144) stand 3.5 to 6.5 mm behind it.",
            "NO connectors on the left/right edges between v = 34 and 70: the grip cheek legs and cheeks (|y| 84..98) stand 4 mm outboard of the board there.",
            "7.0 mm diameter around every mounting hole, both sides.",
            "Top-entry plugs are not possible above 18 mm: the saddle cover underside is 20.4 mm above the PCB top. Use right-angle or low-profile vertical headers.",
        ],
        "cable_exits": "Horizontally outward from the named edges; side bays (|y| 80..115) and the front bay (x > 33) are the cable corridors.",
        "contract_deviation": "None.",
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
         "status": "Rev E body adopted (DEC-039). Head mount option C (DEC-041 study) is implemented here and PENDING contract change CCR-11. Evidence class: calculated."}
    m = lambda v: [round(float(c) / 1000.0, 5) for c in v]   # noqa: E731
    lx, ly = P.LIDAR_POSE["xy"]
    frames = {
        "lidar_link": {"xyz": m((lx, ly, P.LIDAR_POSE["base_z"] + P.LIDAR_SCAN_PLANE_ABOVE_BASE)), "rpy": [0, 0, 0],
                       "note": "scan plane; height above the LiDAR base is UNVERIFIED (assumed 60 mm). 270 deg field centred on +x, blind sector to the rear."},
        "imu_link": {"xyz": m(P.IMU_POSE["xyz"]), "rpy": list(P.IMU_POSE["rpy"]), "note": P.IMU_POSE["note"]},
        "head_mount": {"xyz": m(P.HEAD_MOUNT), "rpy": [0, 0, 0], "note": "mount option C (CCR-11): x-stop plane of the twin-shoe receiver; contract 0.4.0-draft4 still says (0.1385, 0, 0.032). Head-internal geometry relative to this frame is unchanged."},
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
    f["head_switches"] = {**{k: m(v) for k, v in P.HEAD_RAIL_SWITCHES.items()},
                          "lid_interlock_xy": m(P.HEAD_LID_SWITCH), "head_dock_switch_body": m(P.HEAD_DOCK_SWITCH),
                          "note": "rail and lid switches as designed in mechanical/head (IB-40); HEAD_DOCK is on the body"}
    f["head"] = {"envelope_x_m": m(P.HEAD_ENV_E["x"]), "leading_rail_front_x_m": {"unloaded": P.HEAD_LEAD_RAIL["x"][1] / 1000, "fully_stroked": 0.1952},
                 "mass_cg": {b: {"mass_kg": v[0], "cg_xz_m": m(v[1:])} for b, v in P.HEAD_MASS.items()},
                 "source": "mechanical/head/out/head_report.md (calculated by the head engineer)"}
    f["kinematics"] = {"track_m": P.TRACK / 1000, "wheel_radius_m": P.WHEEL_R / 1000, "axle_height_m": P.AXLE_Z / 1000,
                       "caster_swivel_xy_m": m(P.CASTER_SWIVEL + (0,))[:2],
                       "note": "track and caster are the contract values (0.4.0-draft4)"}
    f["footprint"] = {"body_x_m": [round(P.BODY_TAIL_X / 1000, 4), round(P.BODY_NOSE_X / 1000, 4)],
                      "head_envelope_m": {k: m(v) for k, v in P.HEAD_ENV_E.items()},
                      "note": "tool-checked extents are in out/layout_report.md"}
    return f


def interfaces_md():
    RCV, B, S, G = P.RECEIVER, P.BATTERY_BAY, P.SADDLE, P.GRIP
    t = lambda v, n=1: "(" + ", ".join(f"{c:.{n}f}" for c in v) + ")"   # noqa: E731
    L = []
    A = L.append
    A("# Mechanical interfaces between the head, prototype-body and production-body work packages\n")
    A(f"Generated by `mechanical/common/gen_interfaces.py` from `params.py` (contract {P.CONTRACT_VERSION}). base_link mm unless stated. "
      "Design values (calculated / tool-checked by `layout.py`). **Import the named parameters; do not retype these numbers.** "
      "If an interface has to move, change `params.py` through the mechanical lead and rerun `build.sh`.\n")
    A("## 0. Who owns what\n")
    A("| Work package | Owns | Must not change |\n|---|---|---|")
    A(f"| Head (both builds), `mechanical/head/` | everything inside the head envelope x {P.HEAD_ENV_E['x'][0]}..{P.HEAD_ENV_E['x'][1]}, |y| <= 175, z {P.HEAD_ENV_E['z'][0]}..{P.HEAD_TOP_Z}, plus the two shoes, the latch keeper, the pigtails up to the J plugs | optical stack below z 28.5, board outline/holes, shoe section and datums, port positions |")
    A("| Prototype body (X1C), `mechanical/prototype_x1c/` | printed shells, chassis plate and front beam, receiver channels, latch, bridge, grip, battery bay and cassette, sensor and panel mounts | skin law (`P.BODY_ROWS`), running-gear datums, every position in sections 2-7 |")
    A("| Production body, `mechanical/production/` | the same parts as CNC aluminium + MJF PA12 | the same interfaces; a part may change material and wall, not its interface |")
    A("\nBoth body builds must accept both head builds and both must pass `layout.py` with their detailed parts substituted for the envelopes.\n")
    A("## 1. Head / body receiver (mount option C, DEC-041 study; pending CCR-11)\n")
    A("| Item | Value | Owner |\n|---|---|---|")
    A(f"| `head_mount` frame (datum A, x-stop plane; origin on the centre line) | {t(P.HEAD_MOUNT)}; optical row at +65.5 in x, film at -22.0 in z of this frame (unchanged from Rev D) | lead |")
    A(f"| Datum A: x-stops | head shoulders (rear face of the head frame beside each shoe) seat on the channel front faces, nominal x = {RCV['x_stop']} ; two pads 16 x 14 mm each side | head: shoulders; body: channel front faces |")
    A(f"| Datum B: y location | left shoe (y = +{RCV['shoe_y']}) runs in a fitted channel; right channel floats +-0.3 mm | body: channels; head: shoes |")
    A(f"| Datum C: z location | shoe undersides z = {RCV['z_datum']} on two lands per channel centred at x = {RCV['land_x'][0]} and {RCV['land_x'][1]} (base {RCV['land_x'][1] - RCV['land_x'][0]:.0f} mm), 8 mm long each; hold-down by the channel roof bridges at the two land stations at z = {RCV['shoe_z'][1]} | body: lands (replaceable wear strips); head: shoe undersides |")
    A(f"| Shoes (head side, 2 off) | section {RCV['shoe_width']:.0f} mm (y) x {RCV['shoe_z'][1] - RCV['shoe_z'][0]:.0f} mm (z {RCV['shoe_z'][0]}..{RCV['shoe_z'][1]}), centre lines y = +-{RCV['shoe_y']}, from x = {RCV['shoe_x'][0]} to the head frame rear face x = {RCV['shoe_x'][1]}, continued into the seam rib; 3 mm lead-in chamfers; aluminium in both builds | head |")
    A(f"| Channels (body side, 2 off) | outer envelope x {RCV['channel_x'][0]}..{RCV['channel_x'][1]}, {RCV['channel_width']:.0f} mm wide about y = +-{RCV['shoe_y']}, z {RCV['channel_z'][0]}..{RCV['channel_z'][1]}; open to the front and underneath between the lands (drain, wipe-down); bolted under the chassis front beam (x {RCV['front_beam'][0]}..{RCV['front_beam'][1]}, |y| <= {RCV['front_beam'][3]}, z {P.CHASSIS_PLATE_Z[0]}..{P.CHASSIS_PLATE_Z[1]}) | body |")
    RB = P.RECEIVER_BREAK
    A(f"| Receiver thermal break (DEC-045, IB-64) | each channel hangs on a {RB['shim_t']:.1f} +-{RB['shim_t_tol']:.2f} mm ground G10 shim under its ears (ear top z {RB['ear_top_z']:.1f}); no metal crosses the shim: {RB['screw']} in G10 top-hat bushings with a DIN 6796 spring washer ({RB['screw_preload_n']:.0f} N), two lower 4 m6 pins ear -> shim, two upper 4 m6 pins plate -> shim; roof bridges at the land stations stand in {RB['plate_pocket_depth']} mm plate pockets with a {RB['plate_pocket_depth']} mm air gap. Datum C and the land pins unchanged. Calculated channel -> plate conductance <= {RB['target_w_per_k']:.2f} W/K per channel (mech_calcs.md section 9); the head heater figures at 0.07 W/K per shoe depend on it | body |")
    A(f"| Running clearance | {RCV['channel_clear']} mm each side and above the shoe away from the lands (between the land stations the channel roof is open and the shoe top is 3 mm below the plate underside) | both |")
    A(f"| Insertion / removal | head slides -x to seat, +x to remove; free travel needed {RCV['shoe_x'][1] - RCV['shoe_x'][0]:.0f} mm; nothing may be placed ahead of the head | body |")
    A(f"| Latch | one captive over-centre draw latch on the body, envelope x {RCV['latch_box'][0]}..{RCV['latch_box'][1]}, |y| <= {RCV['latch_box'][3]}, z {RCV['latch_box'][4]}..{RCV['latch_box'][5]} under the nose tip; lever lifts forward/up, glove loop >= 25 mm; pulls the head -x with 100..200 N preload | body |")
    A(f"| Latch keeper | on the head cover/frame, centre rear, at {t(RCV['latch_keeper'])}; must take the preload into the frame rear wall, not into the cover skin | head |")
    A(f"| HEAD_DOCK switch | D2HW-C201M on the body at {t(P.HEAD_DOCK_SWITCH)} behind the left channel; the left shoe tip (x = {RCV['shoe_x'][0]}) presses it in the last 1.5 mm of travel | body (switch), head (flat shoe tip) |")
    A(f"| Nose over the head | lower hull removed for x > {RCV['chin_cut'][0]} below z = {RCV['chin_cut'][1]}; nothing of the body below z = {RCV['chin_cut'][1]} ahead of x = {RCV['chin_cut'][0]} except the latch; head top is z = {P.HEAD_TOP_Z} | body |")
    A(f"| Tyre to head | head rear-most parts (wing returns) at x = {141.6 + P.HEAD_DX:.1f}; tyre front at head height x = 51.5 -> 17 mm; the head carries a wipeable splash lip on the wing rear faces, the body a debris deflector ahead of each tyre | both |")
    A(f"| Cable ports on the head | J1 at {t(P.HEAD_PIGTAIL_EXIT['J1'])}, J2 at {t(P.HEAD_PIGTAIL_EXIT['J2'])} in the rear wall above the shoes; sealed strain relief inside the wall, cable leaves -x/+z; pigtail free length 150..200 mm, clipped to the shoe root | head |")
    A(f"| J1 / J2 receptacles on the body | J1 at {t(P.J_RECEPTACLES['J1']['xyz'])}, axis {t(P.J_RECEPTACLES['J1']['normal'], 3)}; J2 at {t(P.J_RECEPTACLES['J2']['xyz'])}, axis {t(P.J_RECEPTACLES['J2']['normal'], 3)}; keep the 45 mm radial grasp zone round each coupling nut free | body |")
    A("| Bench stand | the head stands on its two shoes and a front foot; the stand must not touch the films | head |")
    A("\n## 2. Head internal stack and RR-HEAD-ACQ mounting (head engineer)\n")
    A("| Layer | z bottom | z top | Note |\n|---|---|---|---|")
    for n, a, b, note in P.HEAD_STACK:
        A(f"| {n} | {a} | {b} | {note} |")
    hb = P.HEAD_ACQ
    A(f"\nBoard origin (rear-left corner, PCB underside) {t(hb['origin'])}; +u = -y, +v = +x. Eight M2.5 standoffs 2.5 mm tall clinched in the spreader at board (u, v): "
      + ", ".join(f"({u}, {v})" for u, v in hb["holes_uv"]) + f". Top parts <= {hb['max_top']} mm, bottom <= {hb['max_bottom']} mm. Rear chimney 9 mm deep behind the spreader for the SiPM pigtails at lane centres y = "
      + ", ".join(f"{y:+.2f}" for y in P.SEG_Y) + ". Zones and connector edges: `board_envelopes.yaml`.\n")
    A("## 3. RR-CHS-MAIN mounting (body engineers)\n")
    cb = P.CHS_MAIN
    A(f"Board origin {t(cb['origin'])}, 160 (u, along -y) x 100 (v, along +x), on an aluminium bridge tray z {P.ELECTRONICS_BRIDGE_Z[0]}..{P.ELECTRONICS_BRIDGE_Z[1]} spanning x {P.ELECTRONICS_BRIDGE_X[0]}..{P.ELECTRONICS_BRIDGE_X[1]}, |y| <= {S['half_y']}; six M3 standoffs 3.0 mm tall at board (u, v): "
      + ", ".join(f"({u}, {v})" for u, v in cb["holes_uv"]) + f". Free height above the PCB top {S['floor_z'][0] - cb['origin'][2] - cb['thickness']:.1f} mm to the saddle cover underside (z {S['floor_z'][0]}). "
      f"The saddle cover (x {S['x'][0]}..{S['x'][1]}, |y| <= {S['half_y']}, z {S['floor_z'][0]}..{S['floor_z'][1]}) is the service cover: gasketed, captive screws, removable without touching the grip. "
      f"Grip bar x {G['center_x'] - G['bar_x'] / 2}..{G['center_x'] + G['bar_x'] / 2}, z {G['bar_bottom_z']}..{G['bar_top_z']}, cheeks |y| {G['cheek_y'][0]}..{G['cheek_y'][1]} (bar moved aft from x -11 by CR-04, IB-10); lifting load goes cheeks -> legs -> yokes on the chassis plate, never through a shell. "
      f"Hand zone kept free (130 mm wide): {P.GLOVE_CLEARANCE_GRIP:.0f} mm in front of the bar and below it; behind the bar {G['hand_behind_below']:.0f} mm below the bar (fingertips) and {P.GLOVE_CLEARANCE_GRIP:.0f} mm at bar height and above. "
      "The forward look-ahead ToF pair stays at x 1.5 on a forward nose of the cheek fairings. "
      f"Motor axis z = {P.MOTOR_AXIS_Z} (can clocked {P.MOTOR_SHAFT_OFFSET} mm above the axle, UNVERIFIED eccentricity), gearbox faces at y = +-{P.MOTOR_FACE_Y}; motor mounts stand on the same front beam as the receiver channels.\n")
    A("## 4. Sensor windows (body engineers; RR-TOF 18 x 14 board 6 mm behind a 1 mm window, clear aperture >= 12 x 8 mm)\n")
    A("| Sensor | Aperture xyz | Boresight | Mounted on | Purpose |\n|---|---|---|---|---|")
    host = {"tof_cliff_f": "chassis front beam, outboard end", "tof_cliff_r": "lower hull, rear quarter", "tof_look_fwd": "grip cheek fairing nose, front face", "tof_look_r": "upper fairing, tail", "tof_prox_rc": "brow above the battery hatch", "tof_prox_r": "upper fairing, rear quarter"}
    for k, v in P.TOF_SENSORS.items():
        h = next(val for key, val in host.items() if k.startswith(key))
        A(f"| {k} | {t(v['xyz'])} | {t(v['dir'], 3)} | {h} | {v['purpose']} |")
    A("\nLook-ahead set (IB-34, lead decision): two forward-looking and two rearward-looking oblique sensors. Names changed in this revision (firmware and harness follow these names): "
      "`tof_look_fl` -> `tof_look_fwd_left`, `tof_look_fr` -> `tof_look_fwd_right`, `tof_look_rl` -> `tof_look_rev_left`, `tof_look_rr` -> `tof_look_rev_right`. Positions and boresights unchanged.")
    lx, ly = P.LIDAR_POSE["xy"]
    A(f"\nLiDAR pad: 60 x 60 mm flat at z = {P.LIDAR_POSE['base_z']} centred {t((lx, ly))} on the battery hump; scan plane assumed z = {P.LIDAR_POSE['base_z'] + P.LIDAR_SCAN_PLANE_ABOVE_BASE} (UNVERIFIED +60 mm); nothing on the robot may rise above z = {P.LIDAR_POSE['base_z'] + P.LIDAR_SCAN_PLANE_ABOVE_BASE - 10:.0f} inside the forward 270 deg. "
      f"Body bumper switches at {t(P.BODY_BUMPER_SWITCHES['bumper_sw_l'])} and mirrored; the bumper band and its stroke are body-engineer design items (>= 8 mm stroke for the 0.05 m/s reverse stop).\n")
    A("## 5. Battery cassette interface (body engineers; identical in both builds so packs and cassettes interchange)\n")
    A("| Item | Value |\n|---|---|")
    A("| Pack | Power-Sonic PSL-SC-12120, 151 x 99 x 95 (101 over terminals) mm, 1.65 kg, lying on its 151 x 101 side (99 mm tall), terminals to +y |")
    A(f"| Cassette outer envelope (installed) | x {B['cassette_x'][0]}..{B['cassette_x'][1]}, |y| <= {B['cassette_half_y']}, z {B['cassette_z'][0]}..{B['cassette_z'][1]} (156.5 x 109 x 104 mm); 2.5 mm walls |")
    A(f"| Bay | guide walls at |y| = 55.5..58 from the plate to z = {B['hump_z'][0]}; dorsal hump outer x {B['hump_x'][0]}..{B['hump_x'][1]}, |y| <= {B['hump_half_y']}, top z = {B['hump_z'][1]} ({B['hump_wall']} mm wall); cassette runs on two 2 mm floor ribs (drain underneath) |")
    A(f"| Removal | straight -x through the tail-cap hatch (opening |y| <= {B['hatch_half_y']}, z {B['hatch_z'][0]}..{B['hatch_z'][1]}), {B['removal_travel']:.0f} mm travel; rear pull handle with >= 45 mm glove clearance; positive latch with captive release; hatch cannot close unless the cassette is latched |")
    A(f"| Coupler | keyed, finger-proof blind-mate (candidate Anderson SBS50 with auxiliary pack-presence contacts) on the centre line, mated envelope x {B['coupler_x'][0]}..{B['coupler_x'][1]}, |y| <= {B['coupler_half_y']}, z {B['coupler_z'][0]}..{B['coupler_z'][1]}; fixed half on the bay front bulkhead, cassette half floating +-1 mm; reverse insertion blocked by an off-centre key rib on the cassette floor |")
    A("| 9 Ah alternative | PSL-SC-1290 in the same cassette lying on its side with a 34 mm top spacer; no body change |")
    A("| Bay walls at the tail | the guide walls and their feet end inside the hull inner skin at the tail corners: at x -230 the inner half-breadth at the floor is 52.2 mm, 5.8 mm inside the wall line (CR-07); cassette envelope and removal path unchanged |")
    A("| Heater | 90 x 70 mm pad on the bay floor x -164..-74, bay NTC beside it, bimetal cut-out on the plate |")
    A(f"| Caster | TENTE Compacta 25 mm on a top-hat bracket, mounting face z = {P.CASTER_MOUNT_Z}, swivel axis {t(P.CASTER_SWIVEL)}; 48 mm clearance hole in the plate; the bracket sits under the cassette floor |")
    A("\n## 6. Panel cut-outs and connectors (body engineers; axis = local skin normal, 22.3 mm holes with anti-rotation notch)\n")
    A("| Device | Centre on the outer skin | Axis | Notes |\n|---|---|---|---|")
    for k, v in P.PANEL_CONTROLS.items():
        A(f"| {k} | {t(v['xyz'])} | {t(v['normal'], 3)} | {v['desc']} |")
    A(f"| charge_inlet | {t(P.CHARGE_INLET['xyz'])} | {t(P.CHARGE_INLET['normal'], 3)} | {P.CHARGE_INLET['desc']}; cover hinge at the top, D2HW cover switch |")
    A(f"\nRR-PANEL (70 x 24) lies with its long axis along x, {P.PANEL_BOARD['below_skin']:.0f} mm below the skin at the annunciator position, with 20 mm light pipes. Each device needs 50 mm free depth behind the skin (checked in `layout.py`); flat spot faces of 34 mm diameter on the skin.\n")
    A("## 7. Parameters to import from `params.py` (never redefine)\n")
    A("| Engineer | Import |\n|---|---|")
    A("| Head | `HEAD_MOUNT`, `ROW_X`, `HEAD_DX`, `SEG_Y`, `SEG_PITCH`, `ACTIVE_X`, `ACTIVE_Y`, `FILM_Z`, `RAIL_PROJECTIONS`, `HEAD_ENV_E`, `HEAD_TOP_Z`, `HEAD_STACK`, `HEAD_FRAME_TOP_Z`, `HEAD_FRAME_X`, `HEAD_COVER_X`, `HEAD_SPREADER_X`, `HEAD_ACQ`, `board_to_base`, `HEAD_PIGTAIL_EXIT`, `HEAD_RAIL_SWITCHES`, `RECEIVER` (shoe_*, x_stop, z_datum, latch_keeper), `MATERIALS` |")
    A("| Prototype body and production body | `BODY_ROWS`, `half_breadth`, `roof_z`, `skin_point`, `inside_body`, `BODY_SPLIT_Z`, `CHASSIS_PLATE_Z`, `TRACK`, `WHEEL_Y`, `AXLE_Z`, `WHEEL_R`, `MOTOR_AXIS_Z`, `MOTOR_FACE_Y`, `DRIVE_POD`, `CASTER_SWIVEL`, `CASTER_MOUNT_Z`, `RECEIVER` (channel_*, land_x, front_beam, chin_cut, latch_box), `HEAD_DOCK_SWITCH`, `HEAD_ENV_E` (keep-out), `CHS_MAIN`, `ELECTRONICS_BRIDGE_X/Z`, `SADDLE`, `GRIP`, `BATTERY_BAY`, `LIDAR_POSE`, `CM5_POSE`, `PANEL_BOARD`, `PANEL_CONTROLS`, `CHARGE_INLET`, `J_RECEPTACLES`, `TOF_SENSORS`, `BODY_BUMPER_SWITCHES`, `GLOVE_CLEARANCE_*` |")
    A("| All | purchased envelopes from `mechanical.common.purchased.library` (solids) and `purchased/parts.yaml` (dimensions with verification status); `layout.build()` to get the placed envelope set to design against |")
    A("\n## 8. Shared rules\n")
    for line in [
        "Gaskets: closed-cell silicone rated -40 C on every joint named in `mech_calcs.md` section 7; membrane vents and drains as listed there.",
        "Fasteners into printed parts: heat-set inserts, M3 minimum for structure; no thread forming in printed polymer for anything that is serviced.",
        "Anything wider than the tyres (295 mm) on the body, or outside the head envelope on the head, needs the lead's agreement (swept volume and wall strips).",
        "A prototype part may be thicker than its production twin inward only: outer skin and every interface in this file stay identical.",
        "Open items the downstream engineers must not design around silently: wheel/hub selection, caster sealing, receptacle and switch dimensions marked UNVERIFIED in `parts.yaml`, LiDAR scan-plane height.",
    ]:
        A(f"- {line}")
    return "\n".join(L) + "\n"


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
    (P.OUT / "mechanical_interfaces.md").write_text(interfaces_md(), encoding="utf-8")
    if "--no-step" not in sys.argv:
        board_step()
    print("wrote board_envelopes.yaml, frames.yaml" + ("" if "--no-step" in sys.argv else ", out/boards/*.step"))


if __name__ == "__main__":
    main()
