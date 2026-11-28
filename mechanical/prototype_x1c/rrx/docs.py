"""Generated documents of the RR-X build: plates.yaml, print_schedule.md, purchased_and_fabricated.csv, joints/,
assembly step images, out/checks.json and out/prototype_report.md.  Everything is regenerated from the model."""
from __future__ import annotations

import csv
import fnmatch
import json

import yaml

from mechanical.common import params as P

from . import dims as D
from . import hardware, render
from .export import unique_parts
from .structure import sole_screw_xy
from .util import OUT, ROOT

PROCESS = {
    "ASA": {"layer": 0.20, "walls": 4, "infill": "20 % gyroid", "plate": "Textured PEI Plate", "process": "0.20mm Standard @BBL X1C",
            "overrides": {"wall_loops": 4, "sparse_infill_density": "20%", "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": 5}},
    "PAHT-CF": {"layer": 0.20, "walls": 5, "infill": "35 % gyroid", "plate": "Textured PEI Plate", "process": "0.20mm Strength @BBL X1C",
                "overrides": {"wall_loops": 5, "sparse_infill_density": "35%", "sparse_infill_pattern": "gyroid", "brim_type": "outer_only", "brim_width": 5}},
    "TPU95A": {"layer": 0.20, "walls": 4, "infill": "20 % gyroid", "plate": "Textured PEI Plate", "process": "0.20mm Standard @BBL X1C",
               "overrides": {"wall_loops": 4, "sparse_infill_density": "20%", "sparse_infill_pattern": "gyroid"}},
}
MATERIAL_WHY = {
    "ASA": "Skins, covers, cassette, trays. UV-stable (outdoor grade), tolerates the wipe-down agents expected (water/detergent, 70 % IPA short contact, dilute hypochlorite; NOT ketones/esters), "
           "glass transition ~100 C so heat-set inserts and a sun-heated trailer are safe, lower density than PETG-CF. Unfilled, so it keeps some ductility at -25 C (notched impact falls to roughly half of the "
           "+23 C value: handbook trend, UNVERIFIED for the spool -> drop/impact coupons at -25 C are a first-article test). Needs the closed chamber and a brim on the tall pieces (warp).",
    "PAHT-CF": "Load-bearing printed parts (motor pods, wheel rims, bulkhead, hatch frame, cassette handle, cliff pods, service cover). Highest stiffness and creep resistance of the stock X1C "
               "materials, low moisture uptake for a polyamide, keeps strength at -25 C. Carbon-filled: electrically conductive surface -> not used for the cassette or anything touching terminals. "
               "Print dry (80 C / 8 h), layer adhesion in Z is about half of XY -> every part is oriented so the service load is in-plane.",
    "TPU95A": "Tyres only. 95A grips painted steel/plywood when warm; it stiffens markedly below about -10 C and approaches its glass transition near -30 C (polyester grades earlier) -> traction and "
              "compliance at -20/-25 C are NOT assumed, see the wheel caveats in the report.",
}
RATE_G_PER_H = {"ASA": 20.0, "PAHT-CF": 14.0, "TPU95A": 9.0}      # rough rule-of-thumb only, NOT a slicer estimate


def _supports(note):
    n = note.lower()
    if "no supports" in n and "except" not in n:
        return "none"
    return note


# ----------------------------------------------------------------------------------------------- plates
def make_plates(table):
    printed = [r for r in table if r["kind"] == "printed"]
    plates, n = [], 0
    for mat in ("ASA", "PAHT-CF", "TPU95A"):
        rows = sorted([r for r in printed if r["material"] == mat], key=lambda r: -(r["bbox_print"][0] * r["bbox_print"][1]))
        small = []
        for r in rows:
            w, d = r["bbox_print"][0], r["bbox_print"][1]
            if max(w, d) > 150 or w * d > 15000:
                for q in range(r["qty"]):
                    n += 1
                    plates.append({"id": f"P{n:02d}", "name": r["name"] + (f" ({q + 1}/{r['qty']})" if r["qty"] > 1 else ""), "material": mat,
                                   "parts": [{"part": r["name"], "mesh": f"out/stl/{r['name']}.stl", "position": [128.0, 128.0], "qty": 1, "pn": r["pn"]}]})
            else:
                small.extend([r] * r["qty"])
        while small:                                         # shelf-pack the small parts, several per plate
            n += 1
            x, y, rowh, placed, rest = 22.0, 8.0, 0.0, [], []
            for r in small:
                w, d = r["bbox_print"][0], r["bbox_print"][1]
                if x + w > 248.0:
                    x, y, rowh = 8.0, y + rowh + 8.0, 0.0
                if y + d > 248.0:
                    rest.append(r)
                    continue
                if x < 26.0 and y < 36.0:
                    x = 26.0
                placed.append({"part": r["name"], "mesh": f"out/stl/{r['name']}.stl", "position": [round(x + w / 2, 1), round(y + d / 2, 1)], "qty": 1, "pn": r["pn"]})
                x += w + 8.0
                rowh = max(rowh, d)
            small = rest
            plates.append({"id": f"P{n:02d}", "name": f"{mat} small parts", "material": mat, "parts": placed})
    return plates


def write_plates(table):
    by = {r["name"]: r for r in table}
    plates = make_plates(table)
    man = {"schema": "rr-plates/1",
           "note": "Generated by rrx/docs.py. NOT sliced in this work package (owner slices from the STEP/STL/3MF exports in Bambu Studio); the manifest works with the optional mechanical/tools/slice_plates.py.",
           "printer": {"model": "Bambu Lab X1 Carbon", "machine_profile": "Bambu Lab X1 Carbon 0.4 nozzle", "bed": [256, 256, 250], "edge_margin": 3.0},
           "defaults": {"plate_type": "Textured PEI Plate", "process": "0.20mm Standard @BBL X1C", "part_gap": 8.0},
           "materials": {m: {"filament_profile": D.MAT[m]["profile"], "density_g_cm3": D.MAT[m]["rho"], "process": PROCESS[m]["process"], "plate_type": PROCESS[m]["plate"],
                             "overrides": PROCESS[m]["overrides"], "justification": MATERIAL_WHY[m]} for m in PROCESS},
           "plates": []}
    for pl in plates:
        ent = {"id": pl["id"], "name": pl["name"], "material": pl["material"], "parts": []}
        sup = any(_supports(by[p["part"]]["print_note"]) != "none" for p in pl["parts"])
        if sup:
            ent["overrides"] = {"enable_support": True, "support_type": "tree(auto)"}
        for p in pl["parts"]:
            r = by[p["part"]]
            ent["parts"].append({"part": p["part"], "mesh": p["mesh"], "position": p["position"], "qty": 1, "part_number": r["pn"],
                                 "orientation_note": r["print_note"], "supports": _supports(r["print_note"]), "bbox_print_mm": r["bbox_print"], "bed_fit": r["bed_fit"]})
        man["plates"].append(ent)
    (ROOT / "plates.yaml").write_text(yaml.safe_dump(man, sort_keys=False, width=200, allow_unicode=True), encoding="utf-8")
    A = ["# RR-X print schedule (Bambu Lab X1 Carbon, 0.4 mm hardened nozzle)\n",
         "Generated by `rrx/docs.py` from the model. **Nothing in this file was sliced**: per the owner's instruction slicing is done by the owner in Bambu Studio from the exports. "
         "Every printed part is exported **in its print orientation, +Z up, lowest face on z = 0, bounding-box corner at the origin** as `out/step/<part>.step`, `out/stl/<part>.stl` and `out/3mf/<part>.3mf`. "
         "Bed-fit is a bounding-box check (tool-checked) against 250 x 250 mm (3 mm edge margin on the 256 mm plate) and 253 mm height; the stock 0.4 mm preset prints 250 mm high. "
         "Mass is CAD volume x density x effective fill (calculated estimate); time is a rule-of-thumb from the mass, not a slicer figure.\n",
         "## Materials\n", "| Material | Stock filament preset | Layer / walls / infill | Plate | Why |\n|---|---|---|---|---|"]
    for m, pr in PROCESS.items():
        A.append(f"| {m} | {D.MAT[m]['profile']} | {pr['layer']} mm / {pr['walls']} / {pr['infill']} | {pr['plate']} | {MATERIAL_WHY[m]} |")
    A.append("\nGeneral: closed chamber for ASA and PAHT-CF; glue stick on the textured PEI for PAHT-CF; brim 5 mm on every part taller than 80 mm or with a contact patch under 25 cm2; "
             "seam at the rear/inside; heat-set inserts after printing (see `assembly.md`). Supports = tree (auto) only where the table says so.\n")
    A.append("## Part table\n")
    A.append("| Part no. | Part | Qty | Material | Print orientation (as exported) | Supports expected, on which surfaces | Bounding box in print orientation (mm) | Bed fit | Mass each (g, calc.) | Rough time each (h) |\n|---|---|---|---|---|---|---|---|---|---|")
    tot_m, tot_t = {}, 0.0
    for r in sorted([r for r in table if r["kind"] == "printed"], key=lambda r: r["pn"]):
        t = r["mass_each_g"] / RATE_G_PER_H[r["material"]] + 0.3
        tot_m[r["material"]] = tot_m.get(r["material"], 0) + r["mass_each_g"] * r["qty"]
        tot_t += t * r["qty"]
        fit = r["bed_fit"] + (f" ({r['bed_note']})" if r["bed_note"] else "")
        A.append(f"| {r['pn']} | {r['name']} | {r['qty']} | {r['material']} | Euler XYZ {r['orient_euler_xyz_deg']} deg from the assembled pose: {r['print_note']} | {_supports(r['print_note'])} | "
                 f"{r['bbox_print'][0]:.1f} x {r['bbox_print'][1]:.1f} x {r['bbox_print'][2]:.1f} | {fit} | {r['mass_each_g']:.0f} | {t:.1f} |")
    A.append(f"\nPrinted mass by material (calculated): " + ", ".join(f"{m} {v:.0f} g" for m, v in tot_m.items()) + f". Rough total machine time {tot_t:.0f} h (rule of thumb).\n")
    A.append("## Plates (which parts share a plate)\n")
    A.append("| Plate | Material | Parts (position of the bounding-box centre on the bed, mm) | Supports on this plate |\n|---|---|---|---|")
    for pl in man["plates"]:
        A.append(f"| {pl['id']} | {pl['material']} | " + "; ".join(f"{p['part']} @ ({p['position'][0]:.0f}, {p['position'][1]:.0f})" for p in pl["parts"]) + f" | {'tree (auto)' if 'overrides' in pl else 'none'} |")
    A.append("\nLarge shell pieces are one per plate. The small-part plates are shelf-packed with 8 mm gaps and keep clear of the 18 x 28 mm front-left exclusion corner; re-arrange freely in Bambu Studio. "
             "Left/right mirrored pieces must not be swapped for one another: each has its own file.\n")
    (ROOT / "print_schedule.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    return man


# ----------------------------------------------------------------------------------------------- BOM
def write_bom(parts, table):
    rows = []
    for kind in ("printed", "fabricated", "purchased"):
        bom_parts = [q for q in parts if not (q.material == "KEEPOUT" or q.group == "head_placeholder" or q.name.endswith("_operator"))]
        for rec in unique_parts(bom_parts, kind):
            p = rec["part"]
            t = next((r for r in table if r["pn"] == p.pn), {})
            status = {"fabricated": "DESIGN (fabricate to the STEP/DXF)", "printed": "DESIGN (print to out/step, see print_schedule.md)"}.get(kind) or (p.verified or "see parts.yaml")
            if kind == "purchased" and "UNVERIFIED" not in status.upper() and "VERIFIED" not in status.upper() and "standard" not in status.lower() and "contract" not in status.lower() and "design" not in status.lower():
                status = "UNVERIFIED: " + status
            rows.append({"subassembly": p.subasm, "category": kind, "part_number": p.pn, "item": rec.get("file", p.name), "qty": rec["qty"], "material": p.material,
                         "supplier_pn_or_spec": p.mpn or p.note, "status": status, "drawing": t.get("dxf") or (f"out/fabricated/step/{t.get('name')}.step" if kind == "fabricated" else (f"out/step/{t.get('name')}.step" if kind == "printed" else "")), "torque_Nm": "", "note": p.note})
    for h in hardware.rows():
        rows.append({"subassembly": h["subassembly"], "category": "hardware", "part_number": "", "item": h["item"], "qty": h["qty"], "material": "", "supplier_pn_or_spec": h["spec"],
                     "status": h["status"], "drawing": "", "torque_Nm": h["torque_Nm"], "note": (h["where"] + ("; " + h["note"] if h["note"] else ""))})
    with open(ROOT / "purchased_and_fabricated.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    A = ["# RR-X bill of hardware by sub-assembly\n", "Generated by `rrx/docs.py` from `rrx/hardware.py` (same lists that cut the holes). Full list incl. purchased and fabricated parts: `purchased_and_fabricated.csv`. "
         "STD = standard part; UNVERIFIED = supplier number or a dimension it depends on not confirmed in this session; DESIGN = defined by this model.\n"]
    cur = None
    for h in hardware.rows():
        if h["subassembly"] != cur:
            cur = h["subassembly"]
            A.append(f"\n## {cur}\n\n| Item | Specification | Qty | Where | Torque (N m) | Status | Note |\n|---|---|---|---|---|---|---|")
        A.append(f"| {h['item']} | {h['spec']} | {h['qty']} | {h['where']} | {h['torque_Nm']} | {h['status']} | {h['note']} |")
    (ROOT / "hardware_by_subassembly.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    return rows


# ----------------------------------------------------------------------------------------------- images
STEPS = [
    ("01_chassis", "Stage 1: chassis plate, receiver channels on G10 thermal-break shims with dowel lands, dock switch, cliff pods, caster",
     ["chassis_plate", "receiver_channel_*", "receiver_shim_*", "rx_pin_*", "land_pin_*", "dock_switch_bracket", "head_dock_switch", "cliff_pod_*", "tof_cliff_f?", "tof_window_cliff_f?", "caster*"], (-125.0, -28.0)),
    ("02_lower_hull", "Stage 2: lower hull (four pieces) lowered onto the plate, front bulkhead", ["lower_hull_*", "front_bulkhead", "tof_cliff_r?", "tof_window_cliff_r?", "tof_clip_cliff_r?"], (-58.0, 30.0)),
    ("03_drive", "Stage 3: motor pods, gearmotors, screw rings, hubs, wheels and tyres", ["motor_*", "screw_ring_*", "wheel_*", "tyre_*"], (-58.0, 30.0)),
    ("04_battery_bay", "Stage 4: battery tunnel, floor plug with heater, fixed coupler half, hatch frame", ["battery_tunnel", "floor_plug", "chassis_heater_pad", "coupler_fixed", "hatch_frame"], (-58.0, 38.0)),
    ("05_bridge_grip", "Stage 5: grip feet and side plates, bridge posts, tray, RR-CHS-MAIN, CM5 tray",
     ["grip_foot_*", "grip_side_plate_*", "bridge_*", "board_standoff_*", "RR-CHS-MAIN_*", "cm5_tray", "CM5_*"], (-58.0, 38.0)),
    ("06_nose", "Stage 6: latch arm, nose cowl (slid on rearward), J1/J2 receptacles, head latch", ["latch_arm", "nose_cowl", "J?_receptacle", "head_latch"], (-40.0, 26.0)),
    ("07_lid", "Stage 7: lid (shoulders, rear decks, hump) with controls, sensors, LiDAR, charge inlet",
     ["shoulder_*", "rear_deck_*", "battery_hump", "*_operator", "*_body", "lidar", "charge_inlet", "inlet_cover", "RR-PANEL_*", "panel_tray", "tof_look_rev_*", "tof_prox_*", "tof_window_look_rev_*", "tof_window_prox_*", "tof_clip_look_rev_*", "tof_clip_prox_*", "bumper_sw_*", "door_peg_*", "hatch_latch"], (-58.0, 30.0)),
    ("08_grip_cover", "Stage 8: cheek fairings, grip bar, sleeve, saddle service cover", ["cheek_fairing_*", "grip_bar", "grip_screw_*", "grip_sleeve", "saddle_cover", "tof_look_fwd_*", "tof_window_look_fwd_*", "tof_clip_look_fwd_*"], (-58.0, 30.0)),
    ("09_cassette_door", "Stage 9: battery cassette with fold-flat handle, index-plunger latch, tail-cap door, three-segment bumper",
     ["battery_cassette", "battery_pack", "cassette_lid", "coupler_carrier", "coupler_cassette", "cassette_handle", "cassette_plunger", "hatch_door", "bumper_side_*", "bumper_centre"], (-140.0, 24.0)),
    ("10_head_tray", "Stage 10: head docked (placeholder envelope) and the robot on the transport tray", ["head_*", "J?_mated_plug", "tray_*"], (-50.0, 28.0)),
]


STAGE_TEXT = {   # hand-written work instructions per stage: (do, inserts / torque notes, harness, check after the stage)
    "01_chassis": (
        ["Deburr the plate; countersink from BELOW and tap per `out/dxf/chassis_plate_holes.csv` (hole table). Mill the four 1.5 mm receiver bridge pockets from below; ream the four 4 H7 upper-pin holes in one set-up with the hole pattern.",
         "Receiver thermal break (DEC-045): press the two upper 4 m6 x 8 pins flush into the plate from above. Press the two lower 4 m6 x 8 pins 5.5 mm into each channel ear (2.5 mm stand). Press the two hardened 4 m6 x 24 land pins through each channel (z datum C: flush both sides, no burr on the top line).",
         "Clean and degrease the G10 shims (ground faces, L/R pair from one grinding set-up, marked); no sealant, no paint on the ground faces. Fit shim on the channel lower pins, channel + shim onto the upper pins under the plate (the slotted shim holes take the pin spacing).",
         "Per screw FROM BELOW (plate upside down, fit review C2): G10 top-hat bushing into the 6.1 bore of the ear, ISO 7089 washer, DIN 6796 spring washer (cone toward the head), M4 x 18 A2-70 through ear and shim into the tapped plate (tip stays 0.4 below the plate top). Medium thread-lock; 1.2 N m in two passes; never more (3.6 mm of thread in the plate). Check with a 500 V insulation tester or ohmmeter: channel to plate > 1 Mohm (no metal bridge). Re-torque at service from the floor side with the robot on its back and the head removed (tool-checked access).",
         "Dock switch: D2HW-C201M into the bracket pocket (2 x M2 into inserts), 3 mm push pin into the left channel end wall, bracket to the plate (2 x M3 from above).",
         "Cliff pods: RR-TOF boards with light-blocker foam into the pods, IR window bonded in its recess (clear silicone, no squeeze-out over the aperture); pods to the plate (3 x M3 each).",
         "Caster: 2.5 mm stainless disc on the plate TOP over the 48 mm hole (4 x M3 countersunk into the tapped plate); 1 mm shim and caster from below through the hole, 4 x M4 pan head into the tapped disc (thread-lock)."],
        "Inserts: dock switch bracket 2 x M3, cliff pods 3 x M3 each (set at 230-245 C tip for PAHT-CF, flush +-0.1). Torques: M4 receiver 1.2 N m (G10 joint; re-check at the first service), M3 0.6 N m, M4 caster 1.5 N m.",
        "Dock-switch lead: out of the bracket lead exit toward -x, along the plate underside (two adhesive P-clips) to the 8 mm grommet at (28, 58) and up. Front cliff leads: GH plug into the carrier in its pod, cable up out of the pod bay through the plate window (fit review C4). Routes and lengths: mechanical/common/out/cable_routes.yaml.",
        "Slide a 16.00 x 14.00 x 70 mm gauge bar (the head-shoe gauge) the full length of each channel: left channel no perceptible y shake, right channel 0.6 mm total y float; 0.06 mm feeler fits under the roof pad, 0.12 mm does not. "
        "X-stop faces coplanar within 0.05 mm (straight edge + feelers). Dock switch clicks in the last 1.5 mm of gauge travel (continuity meter)."),
    "02_lower_hull": (
        ["Set all inserts in the four hull pieces first (sole ring, tongue, bumper-switch seats).",
         "Butter the x = -71 butt faces with RTV (no splice screw: the joint lies in the CM5 bay).",
         "Run a bead of neutral-cure RTV round the plate edge, lower each hull half onto the plate (the sole ring wraps the plate edge) and screw from below (M3 x 8 countersunk into the sole inserts). Close the y = 0 butt seams on the floor with RTV.",
         "Front bulkhead on the plate at the chin cut (its pedestals take the latch-arm bolts in stage 6).",
         "Rear cliff ToF boards into the hull bosses with their clips (2 x M2 each)."],
        "Inserts: M3 in the sole ring and tongue (ASA: 220-235 C tip), M2 in the ToF seats. Torque M3 into ASA inserts 0.5-0.6 N m (stop at first resistance + 1/8 turn).",
        "Nothing routed yet; rear cliff leads coiled inside.",
        "Underside flush with the plate (no step > 0.3 mm a broom could catch); lower land at z = 61.9 continuous across the four pieces (straight edge, gap <= 0.3 mm)."),
    "03_drive": (
        ["Insert each gearmotor into its pod from inboard, gearbox face against the pod end wall; 6 x M3 x 6 button head through the stainless screw ring (use whichever of the two printed clockings matches the motor).",
         "O-ring cord in the pod skin notch; lower the pod+motor into the hull and screw it to the plate from below (4 x M4 x 12 countersunk).",
         "Hub on the D shaft, flat face outboard, two set screws on the flat (thread-lock); then the wheel rim onto the hub from outboard (6 x M3 x 8), tyre pre-bonded on the rim keys."],
        "Inserts: 4 x M4 per pod (PAHT-CF). Torque M4 1.5 N m; motor M3 0.5 N m (<= 3 mm thread engagement: use the 6 mm screws only).",
        "Motor + encoder leads up the pod notch into the left / right gutter (z 84..92 along the hull wall, x -69..-5); cable-tie to the gutter clips, 20 mm service loop at the pod.",
        "Wheels spin freely by hand, tyre run-out < 0.5 mm radial (dial gauge), both tyre bottoms and the caster wheel on a surface plate within 0.3 mm (feeler under each)."),
    "04_battery_bay": (
        ["Insulating floor plug into the plate window (RTV the flange), heater pad on the plug, NTC beside it; bimetal cut-out screwed to the plate under the tunnel foot.",
         "Tunnel onto the plate (10 x M3 x 8 countersunk from below), fixed SBS50 half into the cradle and cross-pinned (2 x M4 x 55 + nyloc).",
         "Hatch frame onto the tunnel end bosses (4 x M3 x 10)."],
        "Inserts: tunnel feet 10 x M3, end bosses 4 x M3, cradle 2 x M3. Torque M3 0.6 N m, M4 cross pins 1.0 N m (snug: the housing is plastic).",
        "Pack feed + aux leads from the fixed coupler half along under_bridge_right to the right gutter (2-into-1 loom to J_PWR, CCR-E08), heater/NTC leads with them; P-clip at the cradle (strain relief).",
        "An empty cassette slides in and out with no binding; key rib reversed = blocked at the gate; coupler halves mate by hand."),
    "05_bridge_grip": (
        ["Grip feet (angle) on the plate: 2 x M5 x 16 countersunk from below + nyloc above each; side plates to the feet (2 x M5 x 10 cap screws from INBOARD through the foot into the tapped side plate, medium thread-lock).",
         "Bridge tray first, off the robot: press the six self-clinching M3 standoffs (3 mm) into the tray at the board holes. Four bridge posts (M4 x 10 countersunk from below), tray on top with 4 x M3 x 8 countersunk, flush (fit review C1: nothing above the tray under the board, no nuts under the tray). Gap pad on the tray under the bridge zone, RR-CHS-MAIN on the standoffs with 6 x M3 x 6 pan heads from above (H1 and H3 bond to chassis).",
         "CM5 tray (4 x M3 from below), CM5 carrier (4 x M2.5). No bolt-on clamp resistor (RR-CHS-MAIN carries its own, IB-26)."],
        "Torques: M5 grip 4.0 N m (proof-load path: no thread-lock substitutes for the nyloc), M4 1.5 N m, M3 tray 0.8 N m, M3 board 0.5 N m.",
        "Now connect in this order: (1) J_PWR (right rear edge, the only Mini-Fit) -- 12 mm clear height over the inboard top-entry headers must be kept free of loom; (2) motor connectors J_MOT_L/R from the gutters; "
        "(3) cliff and dock leads from the grommets via front_bay; (4) CM5 USB x2 + Ethernet over left_bay_over_cm5; (5) rear-left corner headers (panel, mode, buttons, bumper, rear ToF) via hump_side_left; (6) rear-right corner headers (E-stop, HANDS-ON, cover, NTC, heater). Every lead tie-wrapped within 40 mm of its header.",
        "Grip side plates vertical within 1 deg; board lies flat on the six standoffs (tool-checked: no screw head under the PCB); continuity board H1/H3 to plate < 0.1 ohm."),
    "06_nose": (
        ["Latch arm onto the bulkhead pedestals (4 x M5 x 25 countersunk from below through the plate).",
         "Nose cowl: J1/J2 receptacles fitted first (O-ring on the outside face, nut inside); slide the cowl rearward over the latch arm until its flange meets the shoulders line (x = 47).",
         "Draw latch through the chin floor into the tapped arm (4 x M4)."],
        "Torques: M5 3.0 N m; M4 latch 2.0 N m; receptacle nuts per binder (UNVERIFIED, typ. 1.0-1.5 N m).",
        "J1/J2 internal leads down the nose cavity through front_bay to the board front edge.",
        "With a head (or the 16 x 14 shoe gauge bars + a latch keeper dummy) the latch closes with a clear over-centre snap; 45 mm glove ring round each coupling nut free (feel with a gloved hand)."),
    "07_lid": (
        ["Pre-assemble the lid pieces off the robot: panel devices into the decks (anti-rotation notch), RR-PANEL on its tray with the light pipes, rear ToF boards and clips, charge inlet + cover + cover switch, bumper switches, door pegs, LiDAR on the hump (gasket, cable gland).",
         "Perimeter gasket on the lower land; lower the shoulders over the grip side plates (slots), then the rear decks; dowels at x = -45 and x = 47; flange screws.",
         "Hump down through the deck opening onto the tunnel; curb screws (M3 countersunk from inside), hatch-frame screw at the top."],
        "Inserts: deck/shoulder flanges, perimeter tongue, hump curb, panel tray bosses, ToF seats. Radial perimeter screws M3 x 10 + bonded washer at 0.5 N m (do not crush the gasket below 1.5 mm).",
        "Deck harness (controls, panel, rear ToF, LiDAR, inlet) into the board rear corners along hump_side_left / right_bay before the hump closes the space; service loop 60 mm so a deck half can be lifted 50 mm.",
        "Perimeter land gap even all round (1.5-2.0 mm compressed gasket visible); every control actuates without touching the skin; E-stop latches and resets."),
    "08_grip_cover": (
        ["On the bench: look-ahead ToF board, foam blocker and window into each fairing nose, shallow clip from behind (2 x M2). Then the fairings over the side plates (2 x M3 x 20 through each).",
         "Printed sleeve onto the 14 mm bar (bar centre x -25, sleeve centre x -30 after CR-04), bar between the side plates, one M6 x 16 cap screw + washer through each plate and fairing pocket into the tapped bar ends (thread-lock); push-in caps.",
         "Saddle cover on its gasket ledge, 9 captive M3 screws."],
        "Torque M6 into the 6061 bar 6.0 N m (medium thread-lock); captive cover screws 0.5 N m.",
        "Look-ahead ToF leads down the fairing channel into the gutters.",
        "PROOF LOAD (VT-002): hang 3 x 9 kg = 265 N on the bar centre over 100 mm for 60 s; no permanent set at the side plates, feet or plate (dial gauge on the plate edge < 0.1 mm residual)."),
    "09_cassette_door": (
        ["Pack into the cassette with EPDM pads (terminals +y), leads to the floating SBS50 half on its carrier, lid (2 x M3).",
         "Index plunger into the hump roof (O-ring under the flange, nut inside, before the hump is fitted in stage 7). Cassette in until the coupler seats and the plunger pin drops into the lid hole (audible click); handle folded down.",
         "Hook the door onto the jamb pegs tilted back, swing shut, close the hatch draw latch; bumper segments on their guide screws with springs."],
        "Inserts: cassette lid 2 x M3, handle hinge lugs 2 x M3 (shoulder screws), carrier 4 x M3, bumper guides 6 x M3.",
        "None (the cassette harness is self-contained).",
        "Door will NOT close unless the cassette is fully home (the door finger stops 0.5 mm behind the cassette rear face), and home = latched by the plunger; the draw latch pulls the door onto the gasket. Pull test: cassette does not move at 100 N on the handle with the plunger engaged. Each bumper segment trips its D2HW within 2-6 mm and returns by spring; 8 mm free stroke."),
    "10_head_tray": (
        ["Dock the head: shoes into the channels from the front, push to the x-stops, close the draw latch; plug J1/J2.",
         "For transport: robot onto the tray (wheels into the chocks, caster into the cup), head guards screwed on, straps over saddle and hump."],
        "-", "J1/J2 pigtails clipped to the shoe roots (head side).",
        "HEAD_DOCK reads closed only with the latch closed and the head fully seated; head film gap per the head checklist."),
}


def write_assembly(parts, log=print):
    """assembly.md: illustrated sequence (images from write_images), inserts/torques, harness order, checks per stage."""
    from .checks import grip_proof
    A = ["# RR-X prototype body -- assembly sequence\n",
         "Generated by `rrx/docs.py` from the model (stage images `img/step_*.png` are rendered from the CAD: the new parts of each stage in colour, earlier parts grey). "
         "Fastener list by sub-assembly with quantities: `hardware_by_subassembly.md`; full parts list: `purchased_and_fabricated.csv`; joint sections at 1:1: `joints/README.md`.\n",
         "## General rules\n",
         "- **Heat-set inserts** go in before any part is assembled: soldering iron with the matching insert tip, ASA 220-235 C, PAHT-CF 240-250 C (dry the part first), "
         "press square to 0.1 mm proud then flatten with a cold flat tip; pull-test one coupon per batch (M3 target >= 400 N in ASA, the value the grip misuse case uses at 600 N is UNVERIFIED until tested).",
         "- **Screws into inserts**: M2 0.15, M2.5 0.3, M3 0.5-0.6, M4 1.5, M5 2.5 N m. Into aluminium (tapped): M3 0.8, M4 2.2, M5 3.0-4.0 N m. Stainless into aluminium: anti-seize, or medium thread-lock where stated.",
         "- **Gaskets** (closed-cell silicone, -40 C): fit dry, butt joints scarfed 45 deg and glued with silicone adhesive; never stretch the strip round corners.",
         "- **Cold**: assemble and torque at room temperature; re-check the M5 grip and M4 receiver torques after the first -20 C soak (aluminium/steel differential is small; printed parts creep).",
         "- Work order follows the load path: plate and datum first, then everything that is screwed from below, then the lid, cover and the removable items.\n"]
    shown = []
    for i, (key, title, pats, _) in enumerate(STEPS, 1):
        new = [p.name for p in _sel(parts, pats) if p.name not in shown]
        shown += new
        do, ins, harness, check = STAGE_TEXT[key]
        A.append(f"## {title}\n\n![{key}](img/step_{key}.png)\n")
        A.append(f"Parts added ({len(new)}): {', '.join(new)}.\n")
        A += [f"{j}. {t}" for j, t in enumerate(do, 1)]
        A.append(f"\n**Inserts / torques:** {ins}\n\n**Harness:** {harness}\n\n**Check before the next stage:** {check}\n")
    g = grip_proof()
    A.append("## Harness routing order (summary)\n")
    A.append("Corridors are the reserved boxes of `mechanical/common/layout.py` (checked free in `out/prototype_report.md`): front_bay (J1/J2, front cliff, dock switch), left/right gutter "
             "(motors, look-ahead ToF, CM5 power; pack and charge feed on the right), under_bridge_right (pack feed between the motor ends), left_bay_over_cm5 (CM5 USB/Ethernet), hump_side_left "
             "(LiDAR, RR-PANEL, rear ToF, deck controls), right_bay (charge inlet, HANDS-ON/Pause, right rear ToF, bumper). Order: plate-level leads (stage 1-4) -> board connectors in the stage 5 order "
             "-> nose (stage 6) -> lid (stage 7) -> grip ToF (stage 8). Strain relief: P-clip or tie-wrap within 40 mm of every board header, grommet at every plate pass-through, "
             "sealed glands at the LiDAR and at the J receptacles (connector seals), service loops where a lid piece must lift.\n")
    A.append(f"## Removal procedures (checked as sweeps in the report)\n\n- **Battery**: open the hatch latch, lift the door off its pegs, pull the plunger knob on the hump (twist to its rest position), unfold the handle, pull 165 mm straight back (unmates the coupler).\n"
             "- **Wheel**: 6 x M3 out of the rim web, pull the wheel 60 mm outboard; the hub stays on the shaft.\n- **Head**: open the draw latch (lever forward/up), unplug J1/J2, slide the head 66 mm forward.\n"
             "- **Service cover**: 9 captive screws, lift straight up under the bar, slide forward over the nose. The grip stays in place.\n")
    A.append(f"Grip proof-load design value: {g['rows'][0][1]} N (calculated, see report section 8).\n")
    (ROOT / "assembly.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    log("  assembly.md written")


def _sel(parts, pats):
    return [p for p in parts if any(fnmatch.fnmatch(p.name, q) for q in pats) and p.name != "spacer_9ah"]


def write_images(parts, log=print):
    img = ROOT / "img"
    img.mkdir(exist_ok=True)
    shown, out = [], []
    for key, title, pats, (az, el) in STEPS:
        new = [p for p in _sel(parts, pats) if p not in shown]
        shown += new
        render.view(shown, img / f"step_{key}.png", highlight={p.name for p in new}, title=title, azim=az, elev=el)
        out.append((key, title, [p.name for p in new]))
        log(f"  image step_{key}.png ({len(new)} new parts)")
    robot = [p for p in parts if p.group != "tray" and p.name != "spacer_9ah"]
    render.view(robot, img / "rrx_iso_front.png", title="RR-X prototype body with the head placeholder", azim=-55.0, elev=24.0)
    render.view(robot, img / "rrx_iso_rear.png", title="RR-X rear quarter: hatch door, bumper, controls", azim=-140.0, elev=22.0)
    render.view(robot, img / "rrx_side.png", title="RR-X side view", azim=-90.0, elev=0.0, size=(12, 5.5))
    lid = {"shoulder_L", "shoulder_R", "rear_deck_L", "rear_deck_R", "battery_hump", "nose_cowl", "saddle_cover", "hatch_door", "lower_hull_FL", "lower_hull_RL"}
    render.view(robot, img / "rrx_internal.png", title="RR-X internal arrangement (lid, nose, left hull and door ghosted)", azim=-60.0, elev=32.0, ghost=lid)
    shells_ = [p for p in parts if p.group in ("lid", "lower_hull", "hatch", "service_cover") or p.name in ("hatch_frame", "front_bulkhead")]
    render.view(shells_, img / "rrx_shell_split.png", title="Shell split: 4 lower hull pieces, nose cowl, 2 shoulders, 2 rear decks, hump, cover, door", azim=-58.0, elev=30.0)
    return out


JOINTS = [
    ("J01_perimeter_lap", "x", -122.0, (120, 152, 48, 80), "Lid / lower hull perimeter lap joint at a screw station",
     ["4 x 2.5 silicone foam on the 1.78 mm land gap (z 61.9..63.68)", "tongue 3 mm inside the lid skirt, 9 mm high: shingled, water cannot climb", "radial M3 x 10 + bonded washer into the tongue insert"]),
    ("J02_lid_flange_x-38", "z", 100.0, (-56, -20, 96, 130), "Shoulder / rear deck bolted flange joint (x = -38)",
     ["4 mm flanges, 9 mm deep, faces set back 0.25 mm each for the 1 mm gasket", "M3 x 12 into insert bosses at z 100 and on the roof; 3 mm dowels at z 108 and on the roof", "flanges start above the hull tongue and stop at the wheel arch"]),
    ("J03_nose_flange_x47", "z", 74.0, (30, 64, 66, 98), "Nose cowl / shoulder flange joint (x = 47)", ["nose is one piece across the centre line: no joint on the nose top", "M3 x 12 + 3 mm dowel per side"]),
    ("J04_hump_curb", "x", -124.0, (44, 80, 104, 154), "Hump wall / rear deck coaming joint", ["hump wall passes down through the deck opening; deck curb 6 mm bolted to it (M3 x 8 countersunk from inside)", "1 mm gasket between wall and curb + sealant fillet outside"]),
    ("J05_saddle_cover_side", "x", -25.0, (66, 106, 90, 180), "Saddle well wall, cover ledge, grip side plate through the shoulder slot, cheek fairing on the roof, grip bar",
     ["cover 3 mm PAHT-CF on a 6 x 2 gasket (no side screws: the board's 18 mm envelope reaches the ledge)", "side plate passes through a slot covered and RTV-sealed by the fairing; ToF lead slot beside it"]),
    ("J06_cover_rear_corner", "x", -65.5, (56, 92, 80, 115), "Saddle cover rear-corner captive screw into the rear-deck ledge boss over the board corner",
     ["boss underside z 97.6 = 13.0 mm above the PCB (CCR-E08 rear-corner zone 12 mm)", "board, bridge tray and top-part envelope shown"]),
    ("J07_hatch_frame_top", "y", 35.0, (-252, -212, 118, 168), "Hatch frame, door end-plate ring, hump end and draw latch (top of the hatch)",
     ["door end-plate ring seals on the frame face through a 3 x 2 gasket", "latch on the hump roof pulls the catch on the door +x"]),
    ("J16_cassette_latch", "y", 0.0, (-252, -190, 36, 172), "Cassette latch: index plunger through the hump roof into the lid, folded handle, door interlock finger",
     ["plunger pin drops 2.4 mm into the lid hole when the cassette is home (coupler mated)", "door finger stops 0.5 mm behind the home position: the door closes only on a latched cassette"]),
    ("J08_door_peg", "z", 100.0, (-254, -224, 42, 72), "Door hook slot on the jamb peg, jamb / frame joint", ["door hangs on two M4 dog-point pegs (hook-and-swing)", "skirt fits inside the jamb; frame ring is the gasket land"]),
    ("J09_sole_plate_edge", "x", None, None, "Lower hull sole ring on the chassis plate edge", ["hull wraps the plate edge; M3 countersunk from below into the sole insert", "RTV bead in the corner; plate underside flush with the hull"]),
    ("J10_hull_splice", "z", 52.0, (-88, -54, 90, 148), "Lower hull front / rear butt joint (x = -71) beside the CM5 bay", ["no splice screw (CM5 bay): both pieces screwed to the plate and held by the lid tongue", "butt joint sealed with RTV, 1 mm gasket where the flange exists"]),
    ("J11_nose_bulkhead_latch", "y", 0.0, (26, 112, 28, 72), "Front bulkhead, chin floor of the nose cowl, latch arm and draw latch over the head", ["latch reaction: latch -> arm -> pedestals -> M5 -> plate -> channels", "nothing but the latch below z = 50 ahead of x = 62"]),
    ("J12_receiver_station", "x", 8.0, (58, 118, 8, 40), "Receiver channel at the rear land station (x = 8) with the head shoe", ["dowel-pin land top = datum C (z 16.0)", "roof pad 14.06 above the land on the rear bridge; bridge in a 1.5 mm plate pocket (air gap)", "ears on the 4 mm G10 shim: no metal contact with the plate"]),
    ("J17_receiver_break", "y", 70.5, (0, 62, 16, 42), "Receiver thermal break, left inboard ear line: M4 in G10 top-hat bushings, lower and upper location pins, G10 shim", ["M4 x 18 + DIN 6796 + ISO 7089 + G10 bushing, 1500 N / 1.2 N m", "lower pins ear -> shim, upper pins plate -> shim; each touches metal on one side only"]),
    ("J13_receiver_long", "y", 87.5, (-16, 74, 8, 40), "Left receiver channel, longitudinal section: lands, x-stop flange, dock switch and push pin", ["x-stop face x = 65.7 (datum A)", "push pin 3 x 6 pressed by the shoe tip in the last 1.5 mm"]),
    ("J14_motor_pod", "x", 0.0, (78, 152, 0, 110), "Motor pod, gearmotor (shaft 7 mm below the can axis), screw ring, hub, wheel, tyre", ["pod base bolted to the plate; pod passes the skin through a sealed notch", "hub fixed on the D shaft first, wheel bolted on from outboard"]),
    ("J15_bumper", "z", 66.0, (-292, -222, 50, 130), "Bumper: side segment on two guide pins with the D2HW, centre segment on the door with overlapping wings", ["stroke 8.5 mm before the bosses reach the skin", "centre wings push both side segments"]),
]


def write_joints(parts, log=print):
    jd = ROOT / "joints"
    jd.mkdir(exist_ok=True)
    robot = [p for p in parts if p.group != "tray" and p.name != "spacer_9ah"]
    A = ["# RR-X joint details (true-size sections cut from the CAD model)\n",
         "Generated by `rrx/docs.py` (`render.section`): each image is the model cut by a 0.4 mm slab at the stated plane, drawn at 1:1 when printed at 254 dpi (PDF copies are vector-true-size). "
         "Colours are the part colours of the assembly; the legend lists the parts cut.\n"]
    for key, plane, pos, win, title, notes in JOINTS:
        if pos is None:
            x, y = sole_screw_xy()[3]
            pos, win = x, (y - 20, y + 16, 28, 48)
        seen = render.section(robot, plane, pos, win, jd / f"{key}.png", title, notes=notes)
        A.append(f"## {key.replace('_', ' ')}\n\n{title}. Plane {plane} = {pos:.1f} mm, window {tuple(round(v, 1) for v in win)}.\n\n![{key}]({key}.png)\n")
        A += [f"- {n}" for n in notes]
        A.append(f"- parts cut: {', '.join(seen)}\n")
        log(f"  joint {key}: {len(seen)} parts")
    (jd / "README.md").write_text("\n".join(A) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------- report
def write_report(R, table, parts, timing):
    (OUT / "checks.json").write_text(json.dumps(R, indent=1, default=str), encoding="utf-8")
    A = []
    w = A.append
    w("# RR-X prototype body -- check report\n")
    w(f"Generated by `mechanical/prototype_x1c/build.py` (contract {P.CONTRACT_VERSION}). Evidence classes: **tool-checked** = OCC geometry kernel on the nominal CAD solids of this model; "
      "**calculated** = closed-form with the stated inputs. Nothing is measured, printed or sliced.\n")
    w("## 1. Summary\n\n| Check | Class | Result |\n|---|---|---|")
    for k, (ok, txt) in R["summary"].items():
        w(f"| {k} | {'calculated' if 'calculation' in k else 'tool-checked'} | {'PASS' if ok else 'FAIL'} -- {txt} |")
    n_print = sum(1 for r in table if r["kind"] == "printed")
    n_fab = sum(1 for r in table if r["kind"] == "fabricated")
    w(f"\nPart count: {len([p for p in parts if p.group not in ('head_placeholder',)])} placed solids; {n_print} unique printed parts ({sum(r['qty'] for r in table if r['kind'] == 'printed')} pieces), "
      f"{n_fab} unique fabricated parts, {len(unique_parts(parts, 'purchased'))} purchased part types (envelopes). Build time {timing}.\n")
    w("## 2. Interference (tool-checked)\n")
    I = R["interference"]
    w(f"{I['pairs_evaluated']} pairs with overlapping bounding boxes were intersected (boolean common, threshold 5 mm3).\n")
    w("**Clashes:** " + ("none" if not I["clashes"] else ""))
    for a, b, v, m in I["clashes"]:
        w(f"- {a} x {b}: {v} mm3 ({m})")
    w("\n**Declared through-wall envelope overlaps** (the purchased envelope is deliberately larger than its cut-out, e.g. a 30 mm switch body behind a 22.3 mm hole, or two mated parts modelled line-to-line):\n")
    for a, b, v, m in I["declared_overlaps"]:
        w(f"- {a} x {b}: {v} mm3 ({m})")
    w("\n**Coincident-face contact films** (overlap whose mean thickness 2V/A < 0.05 mm: the two parts share a surface; not a clash):\n")
    for a, b, v, m in I.get("contact_films", []):
        w(f"- {a} x {b}: {v} mm3 ({m})")
    w(f"\nEvaluation methods: {I['methods']} ('sampled' = boolean did not finish within the time limit; overlap volume from a 1 mm point grid). Slowest pairs: {I['slowest_pairs_s']}.\n")
    w("\n## 3. Containment, floor contact, sensor rays (tool-checked)\n")
    w(f"- Internal parts checked against the inner skin lofts (1 mm margin, tool of `mechanical/common/layout.py`): {len(R['containment']['checked'])}; outside: {R['containment']['outside'] or 'none'}.")
    w(f"- Floor contact z: {R['floor']['contact_z']}; lowest other parts: {R['floor']['lowest_other_parts']}.")
    w(f"- ToF centre rays blocked: {R['rays']['tof_centre_blocked'] or 'none of 11'}; LiDAR scan plane z = {R['rays']['lidar_scan_z']} (UNVERIFIED +60 mm), blocked bearings: {R['rays']['lidar_blocked'] or 'none'}.")
    w("\n| Sensor | Centre ray | 18 deg cone edge: first obstruction (mm from the aperture) |\n|---|---|---|")
    for r in R["rays"]["tof"]:
        w(f"| {r['sensor']} | {'clear' if not r['centre_ray_hits'] else r['centre_ray_hits']} | {r['cone_edge_hits'] or 'clear'} |")
    w("\nCone-edge obstructions are findings, not failures (same rule as the master layout). Window assumptions: 1.0 mm IR-pass PMMA normal to the boresight, bonded in a 1.1 mm recess; a die-cut black foam "
      "light blocker separates emitter and receiver between the VL53L4ED and the window (the 2.6 mm air gap is far above the ST guideline for a bare cover glass, so crosstalk calibration per sensor is mandatory; "
      "a 5..10 deg window tilt is the fallback if the calibration margin is poor). All UNVERIFIED until an RR-TOF board is on the bench.\n")
    w("## 4. Removal sweeps and glove zones (tool-checked)\n")
    for k, v in R["service"].items():
        w(f"- **{k}**: {v.get('what', '')} -> " + (f"{v['value_mm']:.0f} mm (required {v['required_mm']:.0f})" if "value_mm" in v else ("free" if not v["blocked_by"] else f"BLOCKED by {v['blocked_by']}")))
    w(f"- **below z = 50 ahead of x = 62**: {R['chin_rule']['parts_in_the_zone']} ({R['chin_rule']['note']}).")
    w("\n## 5. Receiver interface against `mechanical_interfaces.md` section 1 (tool-checked)\n\n| Item | Required | Measured on the model | OK |\n|---|---|---|---|")
    for r in R["receiver"]["rows"]:
        w(f"| {r['item']} | {r['required']} | {r['measured']} | {'yes' if r['ok'] else 'NO'} |")
    w("\n### Tolerance-critical dimensions of the receiver (fabrication drawing values)\n")
    w("| Feature | Nominal | Tolerance | Why |\n|---|---|---|---|")
    RC = P.RECEIVER
    RB = P.RECEIVER_BREAK
    for f in [("Ear top face to land-pin bore centre (4 H7)", f"{RB['ear_top_z'] - (RC['shoe_z'][0] - D.RX_LAND_PIN_D / 2):.2f} mm", "+-0.03", "with the shim sets the head height: 1:1 into the film gap"),
              ("G10 shim thickness (L/R pair ground together)", f"{RB['shim_t']:.2f} mm", f"+-{RB['shim_t_tol']:.2f}, flatness {RB['shim_flatness']}, L/R within 0.01", "in the datum-C stack (thermal break)"),
              ("Roof pad to land-pin bore centre (4 H7)", f"{RC['shoe_z'][1] - RC['shoe_z'][0] + D.RX_FIT_Z + D.RX_LAND_PIN_D / 2:.2f} mm", "+0.04 / -0.02", "z fit of the 14.00 mm shoe: 0.04..0.10 mm play -> 0.07..0.19 mm at the row over the 54 mm base"),
              ("Land-pin bores", "4 H7, two per channel at x = 8.0 and 62.0", "+-0.05 on the 54 mm spacing", "datum C base; pins 4 m6 hardened, replaceable"),
              ("Left channel width at the two stations", f"{RC['shoe_width'] + 2 * D.RX_FIT_Y_LEFT:.2f} mm", "+0.05 / 0", "datum B (y) of the head"),
              ("Right channel width at the stations", f"{RC['shoe_width'] + 2 * D.RX_FLOAT_Y_RIGHT:.2f} mm", "+-0.1", "floats +-0.3 mm (thermal growth over 175 mm)"),
              ("Channel centre distance", f"{2 * RC['shoe_y']:.1f} mm", "+-0.1 (plate 4 H7 upper-pin holes -> shim -> lower pins)", "left fixed, right floating; two pin fits in the chain"),
              ("X-stop faces (two channels)", f"x = {RC['x_stop']} from the plate pin holes", "coplanar within 0.05", "datum A; latch preload 100..200 N seats the head shoulders here"),
              ("Slot width / roof pads", "17.0 / 30.5 at the two bridges, roof open between", "+-0.2", "0.5 mm running clearance, open underneath for wipe-down"),
              ("Plate pockets over the bridges", f"{RB['plate_pocket_depth']} deep from below, 1.0 margin", "+0.2 / 0 depth", "1.5 mm air gap: no metal contact")]:
        w("| " + " | ".join(f) + " |")
    w("\n**Printed with metal lands or fabricated aluminium?** Decision: the chassis plate (4 mm 6061, laser cut, two 1.5 mm pockets milled from below per channel) with the front beam in one piece, and two **machined 6061 channels** with hardened 4 mm dowel pins as the "
      "replaceable z lands. Reasons (calculated/handbook): (1) stiffness: the common model assumes 6000 N/mm per aluminium land against 1500 N/mm printed, i.e. four times the pitch stiffness and half the rattle-mode "
      "amplitude at the row; a printed PAHT-CF channel also halves its modulus when moist. (2) wear: aluminium shoes sliding on a printed slot with grit abrade the datum; a steel dowel is a line contact that does not "
      "pick up grit and is replaced by pressing it out. (3) creep: the latch preload sits on the x-stop pads permanently. (4) the part is a prismatic block: one slot milled from below, four reamed cross holes, "
      "tapped and pinned ears. A printed copy of the same geometry (`out/step/receiver_channel_fitcheck_*.step`) is exported for a fit check before metal is cut; it is not the datum build.\n")
    rb = {}
    try:
        import json as _j
        rb = _j.loads((P.OUT / "mech_calcs.json").read_text(encoding="utf-8")).get("receiver_break", {})
    except (OSError, ValueError):
        pass
    gtxt = f"{rb['g_per_channel']:.3f} W/K per channel" if rb else "see `mechanical/common/out/mech_calcs.md` section 9"
    w("**Receiver thermal break (DEC-045 / IB-64, built).** Each channel (RRX-F02L/R) hangs under the plate on a ground 4.0 mm G-10 shim (RRX-F12L/R) under its ears; "
      "no metal part crosses the shim: the three M4 x 18 screws sit in G-10 top-hat bushings in 6.0 mm plate holes (DIN 6796 spring washer + ISO 7089 washer under the head, 1500 N, 1.2 N m); "
      "two lower 4 m6 x 8 pins pressed into the ear engage the shim only (top 1.5 mm below the plate); two upper pins pressed flush into the plate pass through the shim and end in a 6.5 x 1.5 relief in the ear. "
      "The channel ears and walls stop at z 29.0 (plate - shim); the roof exists only as two bridges over the land stations, which stand up into 1.5 mm pockets in the plate underside with a 1.5 mm air gap. "
      f"Datum C (z 16.0) and the land pins are unchanged (tool-checked, section 5 rows). Conductance channel -> plate (calculated, G-10 0.30 W/m K handbook class, UNVERIFIED): **{gtxt}** "
      "against the 0.10 W/K target; the joint it replaces was about 6.5 W/K. Tolerance stack, G-10 creep and preload, stiffness and thread engagement: `mechanical/common/out/mech_calcs.md` section 9.\n")
    w("## 6. Bed fit of every printed part in its print orientation (tool-checked bounding boxes)\n\n| Part | Bounding box (mm) | Verdict | Note | Mesh open edges |\n|---|---|---|---|---|")
    for r in R["bed_fit"]:
        w(f"| {r['part']} | {r['bbox_print']} | {r['verdict']} | {r['note']} | {r['open_edges']} |")
    M = R["mass_cg"]
    w("\n## 7. Mass, centre of gravity, tip margins, hang angle (calculated)\n")
    w(f"{M['assumptions']}.\n\n| Group | Mass (kg) | x (mm) | z (mm) |\n|---|---|---|---|")
    for k, v in M["groups"].items():
        w(f"| {k} | {v['mass_kg']:.3f} | {v['x']} | {v['z']} |")
    b = M["base_without_head"]
    w(f"| **Base with the 12 Ah pack, no head** | **{b['mass']:.2f}** | {b['x']:.1f} | {b['z']:.1f} |")
    w("\n| Head | Mass (kg) | Margin to 12 kg | CG x | CG z | Caster N (fraction) | Each wheel N | Tip margin forward (0.4 m/s2 braking, 5 deg) | rearward | lateral | Hang angle at the grip x -30 (deg, - = tail down) | (before CR-04, bar at x -11) |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in M["configurations"]:
        w(f"| {c['head']} | {c['mass_kg']} | {M['mass_goal_kg'] - c['mass_kg']:.2f} | {c['cg_x']} | {c['cg_z']} | {c['caster_N']} ({c['caster_fraction']:.2f}) | {c['each_wheel_N']} | {c['tip_margin_forward_mm']} | "
          f"{c['tip_margin_rearward_mm']} | {c['tip_margin_lateral_mm']} | {c['hang_angle_deg']} | {c['hang_angle_deg_old_bar_x-11']} |")
    w("\nHead masses and CGs are the head engineer's calculated values (`mechanical/head/out/head_report.md` section 3, incl. pigtails). The 9 Ah pack variant is 0.65 kg lighter at x = -152 (spacer +0.05 kg).\n")
    w("\nLayout budget for comparison (`mech_calcs.md`, prototype, 12 Ah): 6.90 kg / CG x -86.3 / z 82.0 without head; 8.57 kg / -46.5 / 71.6 with the printed head (tip margin 37.3 mm, hang -19.6 deg).\n")
    w("**IB-10 (carry attitude), CR-04 applied:** the grip bar centre moved from x -11 to x -30 with the hand zone reduced to 25 mm behind the bar below it (fingertips; the palm is above the hump top z 150). "
      "The last column shows the hang angle the old position gave.\n")
    w("## 8. Carry-grip proof load (calculated)\n\n| Item | Value | Unit | Assessment |\n|---|---|---|---|")
    for item, val, unit, note in R["grip"]["rows"]:
        w(f"| {item} | {val} | {unit} | {note} |")
    w(f"\n{R['grip']['cold_note']}\n")
    w("## 9. Wheel (design item: no 104 x 25 catalogue wheel)\n")
    w("Printed PAHT-CF rim (86 mm, 8 drive keys) bolted from outboard to a purchased 6 mm set-screw hub (Pololu #1999 class, UNVERIFIED dimensions) that is fixed on the D shaft first; printed TPU 95A tyre 9 mm thick, "
      "keyed and bonded, rolling diameter 104.0 mm unloaded (contract). Caveats: (1) TPU 95A stiffens strongly below about -10 C and loses grip on frost; the contract friction values are not demonstrated cold. "
      "(2) A 9 mm solid tyre under 33..36 N per wheel compresses by a few tenths of a millimetre and creeps when parked cold -> the film gap calibration must be done loaded and after a cold soak. "
      "(3) Printed TPU has layer lines across the tread: tread wear and diameter must be re-measured after the first hours. (4) Alternative kept open: the same rim turned down to carry a purchased 86 x 9 polyurethane "
      "tyre/O-ring band (60..70A cold-grade) if the cold traction test fails. The shaft eccentricity (shaft 7 mm below the can axis, UNVERIFIED) is handled in the pod: can bore on z = 59, shaft boss hole on z = 52, "
      "and twelve M3 holes so the UNVERIFIED six-hole pattern fits in either clocking.\n")
    w("## 10. Rules, corridors and the RR-CHS-MAIN keep-outs (tool-checked)\n")
    wr = R["width_rule"]
    w(f"- Width rule (nothing wider than the tyres, |y| <= {wr['limit_half_width_mm']}): {'PASS' if wr['ok'] else 'FAIL ' + str(wr['over'])}.")
    for k, v in R["corridors"].items():
        w(f"- corridor **{k}** {v['box']} ({v['use']}): {'free' if not v['blocked_by'] else 'BLOCKED by ' + str(v['blocked_by'])}")
    sr = R["swept_radius"]
    w(f"\n**Swept radius (IB-48):** tail {sr['tail_max_radius_mm']} mm from the axle centre ({sr['tail_part']}; without the bumper {sr['tail_without_bumper_mm']} mm, {sr['tail_without_bumper_part']}); body ahead of the axle {sr['front_body_max_radius_mm']} mm ({sr['front_body_part']}); head envelope corner {sr['head_envelope_corner_radius_mm']} mm. {sr['note']}.\n")
    w("\nCCR-E08 (chassis electronics) answers, checked as keep-out boxes against every body part:\n")
    for k, v in R["ccr_e08"].items():
        w(f"- {k}: {'free' if not v['blocked_by'] else 'BLOCKED by ' + str(v['blocked_by'])}")
    w("\nThe two rear cover-screw bosses hang to z 97.6 (13.0 mm above the PCB) over the rear corners, i.e. above the 12 mm the request asks for. "
      "The combined 8-way Mini-Fit at the right-rear edge (CCR-E08 a) has its mated plug and loom room beyond the board edge. Boolean slivers removed from parts: "
      f"{R['slivers']['dropped'] or 'none'}.\n")
    w("## 11. Fit checks after the independent fit review (tool-checked; docs/reviews/REVIEW_cad_pcb_harness_fit.md)\n")
    w(fit_report(R))
    w("## 12. Deviations and change requests\n\nSee `CHANGE_REQUESTS.md` (deviations taken inside this package, requests to the lead / electronics / harness / head).\n")
    (OUT / "prototype_report.md").write_text("\n".join(A) + "\n", encoding="utf-8")


def fit_report(R):
    """Markdown of the fit-review checks: fasteners, sweeps, routes, SVC pads, board bottom zone (shared by both builds)."""
    A = []
    w = A.append
    F = R.get("fasteners", {})
    w(f"**Fasteners as solids ({F.get('count', 0)} modelled):** every fastener solid (head, washers, 0.8 d shank, nut) is in the interference check of section 2; "
      "each tool column (stated tool, from the head or nut outward) is intersected with the parts present at the step that fits it (stage order of assembly.md) "
      "and in its service state. Blocked: " + (", ".join(F.get("blocked", [])) or "none") + ".\n")
    w("| Fastener | Size | Step / state | Tool | Blocked by |\n|---|---|---|---|---|")
    for r in F.get("rows", []):
        if r["blocked_by"] or r["step"].startswith("SERVICE") or r["fastener"].startswith(("rx_", "board_", "tray_", "gripplate_", "pod_")):
            w(f"| {r['fastener']} | {r['size']} | {r['step']} | {r['tool']} | {r['blocked_by'] or 'free'} |")
    S = R.get("service_sweeps", {}).get("sweeps", {})
    w("\n**Service sweeps of real parts:**\n\n| Sweep | Removed first | Blocked by |\n|---|---|---|")
    for k, v in S.items():
        if k == "tof_withdrawal_in_place":
            continue
        w(f"| {k} | {', '.join(v['removed'][:8])}{' ...' if len(v['removed']) > 8 else ''} | {v['blocked_by'] or 'free'} |")
    tof = S.get("tof_withdrawal_in_place", {})
    if tof:
        w("\n**ToF carrier replacement in place (fit review M10; cover off, head removed; carrier withdrawn 25 mm along -boresight):**\n\n| Sensor | Withdrawal | Needs |\n|---|---|---|")
        for n, b in tof.items():
            need = "from inside after removing the part(s) listed" if b else "replaceable in place (inside access)"
            w(f"| {n} | {b or 'free'} | {need} |")
    RT = R.get("routes", {})
    w("\n**Cable routes (published to mechanical/common/out/cable_routes.yaml):**\n\n| Cable | From -> to | OD / bend R (mm) | Route (mm) | Length (mm) | Collisions | Tight bends | Free spans | Result |\n|---|---|---|---|---|---|---|---|---|")
    for k, r in RT.items():
        if "polyline" not in r:
            w(f"| {k} | - | - | - | - | - | - | - | {r.get('status')} |")
            continue
        tb = sum(1 for b in r.get("bends", []) if not b["ok"])
        fs = sum(1 for c in r.get("clips", []) if not c["ok"])
        w(f"| {k} | {r['from']} -> {r['to']} | {r['od_mm']} / {r['min_bend_r_mm']} | {r['route_mm']} | {r.get('length_mm', '-')} | {r.get('collisions') or 'none'} | {tb} | {fs} | {r.get('status')} |")
    sv = R.get("svc_access", {})
    if sv:
        w(f"\n**SVC1..SVC10 test-pad array (stage 5 board):** pads in the board file {sv['pads_in_board_file']}; probe zone {sv['zone_base_link']} (u 126-140, v 75-84, 40 mm above the board); "
          f"parts in the zone {sv['parts_in_zone'] or 'none'}; cable routes over it {sv['routes_over_zone'] or 'none'}; clip points over it {sv['clips_over_zone'] or 'none'} -> {'PASS' if sv['ok'] else 'FAIL'}.")
    bb = R.get("board_bottom", {})
    if bb:
        w(f"\n**RR-CHS-MAIN bottom side ({bb['source']}):** {bb['bottom_parts']} parts, tallest {bb['max_height_mm']} mm (zone 3.0); over 3 mm: {bb['over_3mm'] or 'none'}; "
          f"over a bridge-tray feature (clinch standoffs, flush post screws, pass-throughs): {bb['over_tray_features'] or 'none'}.")
    return "\n".join(A) + "\n"
