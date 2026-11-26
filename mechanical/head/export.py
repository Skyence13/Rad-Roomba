"""Exports: STEP of every part and assembly, print-orientation STEP/STL/3MF of printed parts, DXF of sheet parts,
plates.yaml (schema rr-plates/1 of mechanical/tools) and the print schedule.

Run: python -m mechanical.head.export [--no-mesh]
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from . import assembly as A
from . import hp as H
from . import parts as T
from .geom import HERE, assembly_step, bounds, export_step, oriented, volume

sys.path.insert(0, str(HERE.parent / "tools"))
PROTO, PROD, AUX = HERE / "prototype", HERE / "production", HERE / "aux"

MATERIALS = {
    "PA-CF": {"filament_profile": "Bambu PAHT-CF @BBL X1C", "density_g_cm3": 1.22, "process": "0.20mm Standard @BBL X1C", "plate_type": "Textured PEI Plate",
              "justification": "PAHT-CF (PA12-based, low moisture uptake): highest dry stiffness of the candidates (E about 5.5 GPa XY), keeps impact strength at -20 C better than "
                               "PETG-CF, creep-resistant under the insert and screw preloads next to the +10 C heater plane, matte black and opaque. Print dry (80 C / 8 h), store dry; "
                               "conditioned modulus about half the dry value -> structure is checked with both. Used for the frame halves and every small structural part."},
    "PETG-CF": {"filament_profile": "Bambu PETG-CF @BBL X1C", "density_g_cm3": 1.25, "process": "0.20mm Standard @BBL X1C", "plate_type": "Textured PEI Plate",
                "justification": "Flat, lightly loaded, wipe-down parts (cassettes, lane rings, barrier, covers): dimensionally stable, no drying sensitivity, good chemical resistance to "
                                 "decontamination wipes. Lower cold impact strength than PA-CF: not used where a rail or latch load passes. Alternative for the frame if PA-CF warps."},
    "ASA": {"filament_profile": "Bambu ASA @BBL X1C", "density_g_cm3": 1.07, "process": "0.20mm Standard @BBL X1C", "plate_type": "Textured PEI Plate",
            "justification": "Not selected for the head: E about 2.2 GPa gives 2.5 x the wall deflection of PA-CF and unfilled ASA is notch-sensitive in the cold. Kept as a listed "
                             "fallback for the transport covers only (UV / wipe resistance)."},
    "TPU": {"filament_profile": "Bambu TPU 95A @BBL X1C", "density_g_cm3": 1.21, "process": "0.20mm Standard @BBL X1C", "plate_type": "Textured PEI Plate",
            "justification": "Split strain-relief grommets (95A stays flexible at -20 C; external spool, not through the AMS). A moulded silicone grommet replaces it in production."},
}
STD = {"layer_height": 0.2, "walls": 4, "infill": "25 % gyroid", "top_bottom_layers": 5, "brim": "none"}


def printed_parts():
    """Catalogue of every printed part: one row per part number (qty = number per head / kit)."""
    P = {p.name: p for p in A.build("prototype")}
    lane = T.lane_parts(1)
    rows = []

    def add(pn, name, shape, orient, material, qty, plate, supports, note, kit="head", **over):
        d = dict(STD)
        d.update(over)
        rows.append({"pn": pn, "name": name, "shape": shape, "orient": orient, "material": material, "qty": qty, "plate": plate, "supports": supports, "note": note, "kit": kit, **d})

    add("RR-HD-X-101", "frame_half_left", P["frame_L"].shape, (0, 0, 0), "PA-CF", 1, "H01",
        "optional, non-critical: the rear wall bridges 60 mm over each T-head pocket opening at z 30.0 (tree supports from the pocket floor; the face carries no load, the spreader is the seat). "
        "Everything else bridges <= 13.5 mm (side switch pocket roof, guide slits, drain channel) or overhangs <= 5 mm (lid boss undersides, tongue). Horizontal bores (guide rods 4.3, dowels, bail-block inserts) print as holes and are reamed. "
        "No support on the cassette seat (bed face), the module seat shoulders, the rib tops, the spreader seat or the joint faces.",
        "underside (z 10.5) on the bed; cavity walls, seat shoulder, rib top and wall top are all vertical or upward faces; joint face vertical", walls=5, infill="40 % gyroid (100 % below z 11 and in the ribs: 4-5 perimeters fill them)", brim="5 mm outer brim (PA-CF warp)")
    add("RR-HD-X-102", "frame_half_right", P["frame_R"].shape, (0, 0, 0), "PA-CF", 1, "H02", "as RR-HD-X-101", "as RR-HD-X-101 (groove side of the joint, vent hole)", walls=5,
        infill="40 % gyroid (ribs solid by perimeters)", brim="5 mm outer brim (PA-CF warp)")
    add("RR-HD-X-201", "window_cassette", T.cassette(1), (0, 0, 0), "PETG-CF", 4, "H03", "none", "underside on the bed, lips and seat bosses up; webs full height so nothing bridges", walls=3, infill="100 %")
    add("RR-HD-X-301", "lane_spacer_lower", lane["spacer_lower"][0], (0, 0, 0), "PETG-CF", 4, "H04", "none", "flat", walls=3, infill="100 %")
    add("RR-HD-X-303", "lane_spacer_upper", lane["spacer_upper"][0], (0, 0, 0), "PETG-CF", 4, "H05", "none", "flat", walls=3, infill="100 %")
    add("RR-HD-X-302", "lane_barrier", lane["barrier"][0], (0, 0, 0), "PETG-CF", 4, "H06", "none", "flat, 100 % infill for opacity", walls=3, infill="100 %")
    add("RR-HD-X-304", "chimney_insert", lane["chimney_insert"][0], (0, -90, 0), "PA-CF", 4, "H07", "none", "rear face on the bed, fingers and shelf up", walls=3, infill="100 %")
    add("RR-HD-X-411", "rail_insert", P["rail_insert_1"].shape, (0, 90, 0), "PA-CF", 4, "H07", "none", "lying on the contact face (smooth bed side = wear / contact face); print 8 (one spare set)", walls=4, infill="100 %")
    add("RR-HD-X-405", "bail_block", P["bail_block_C"].shape, (0, -90, 0), "PA-CF", 3, "H07", "none", "frame-side face on the bed; the 2.8 mm wire bore prints as a horizontal hole", walls=4, infill="100 %")
    add("RR-HD-X-421", "front_switch_saddle", P["sw_front_saddle"].shape, (180, 0, 0), "PA-CF", 1, "H07", "none", "upside down (top bar on the bed)", walls=3, infill="100 %")
    add("RR-HD-X-422", "lid_switch_saddle", P["sw_lid_saddle"].shape, (180, 0, 0), "PA-CF", 1, "H07", "none", "upside down (top bar on the bed)", walls=3, infill="100 %")
    add("RR-HD-X-511", "grommet_J1", P["grommet_J1"].shape, (0, -90, 0), "TPU", 1, "H08", "none", "cable axis vertical; slit with a blade after printing", walls=3, infill="100 %")
    add("RR-HD-X-512", "grommet_J2", P["grommet_J2"].shape, (0, -90, 0), "TPU", 1, "H08", "none", "cable axis vertical; slit with a blade after printing", walls=3, infill="100 %")
    add("RR-HD-X-601", "transport_cover_left", T.transport_cover(1), (0, 0, 0), "PETG-CF", 1, "H09", "yes: snap bridge over the shoe and the front lip (two short bridges, tree supports optional)", "tray floor on the bed", walls=3, infill="20 % gyroid")
    add("RR-HD-X-602", "transport_cover_right", T.transport_cover(-1), (0, 0, 0), "PETG-CF", 1, "H10", "as RR-HD-X-601", "tray floor on the bed", walls=3, infill="20 % gyroid")
    add("RR-HD-D-302", "dummy_lane_spacer", T.dummy_spacer(1, 2.0), (0, 0, 0), "PETG-CF", 4, "H11", "none", "floor on the bed, open side up (as installed); height follows the ballast thickness in checks.json", kit="dummy head", walls=3, infill="20 % gyroid")
    for nm, shape, mat, kind, desc in T.cradle_parts():
        if kind == "printed" and nm.endswith("_L"):
            flat = (0, 90, 0) if "cable_rest" in nm else (0, 0, 0)
            add("RR-HD-C-" + ("611" if "fence" in nm else "612"), nm[:-2], shape, flat, "PETG-CF", 2, "H12" if "fence" in nm else "H13", "none", "mirror in the slicer for the right-hand part" if "fence" in nm else "lying on its side", kit="bench cradle", walls=4)
    return rows


def shelf_pack(items, bed=(256.0, 256.0), margin=8.0, gap=6.0):
    """items: (name, w, d). Returns {name: (cx, cy)} or None if they do not fit one plate. Skips the 18 x 28 exclusion corner."""
    x, y, row_h, out = margin, margin + 28.0, 0.0, {}
    for name, w, d in items:
        if x + w > bed[0] - margin:
            x, y, row_h = margin, y + row_h + gap, 0.0
        if y + d > bed[1] - margin or w > bed[0] - 2 * margin:
            return None
        out[name] = (round(x + w / 2, 1), round(y + d / 2, 1))
        x += w + gap
        row_h = max(row_h, d)
    return out


def run(mesh=True):
    import mesh_io as M
    for d in (PROTO / "step", PROTO / "print", PROD / "step", AUX / "step", PROTO / "dxf", PROD / "dxf"):
        d.mkdir(parents=True, exist_ok=True)
    summary = {"step": 0, "print": 0}
    # ---- STEP of every part (installed position) and of the assemblies
    for build, root in (("prototype", PROTO), ("production", PROD)):
        parts = A.build(build)
        done = set()
        for p in parts:
            if p.pn == "-" or p.kind in ("envelope",) or p.pn in done and p.pn.startswith("PUR"):
                continue
            key = (p.pn, p.name.split("_")[0] if p.name.startswith("S") and p.name[1].isdigit() else p.name)
            fn = f"{p.pn}__{p.name}.step".replace("/", "-")
            if p.name[0] == "S" and p.name[1].isdigit() and p.name[1] != "1":     # one instance of each lane part is enough
                continue
            export_step(p.shape, root / "step" / fn)
            done.add(p.pn)
            summary["step"] += 1
        assembly_step(parts, root / f"RR-HD-{'X' if build == 'prototype' else 'P'}-000_head_assembly_{build}.step", f"RR_head_{build}")
    m_proto = sum(p.mass() for p in A.build("prototype"))
    dummy, t = A.build_dummy(m_proto)
    (AUX / "step").mkdir(parents=True, exist_ok=True)
    assembly_step(dummy, AUX / "RR-HD-D-000_dummy_head_assembly.step", "RR_dummy_head")
    for p in dummy:
        if p.pn.startswith("RR-HD-D") and (p.name[0] != "S" or p.name[1] == "1"):
            export_step(p.shape, AUX / "step" / f"{p.pn}__{p.name}.step")
    from .geom import Part
    cr = [Part(n, "RR-HD-C-" + str(600 + k), s, m, kind=kd, desc=d, color="#8e6bbf") for k, (n, s, m, kd, d) in enumerate(T.cradle_parts(), start=1)]
    for p in cr:
        export_step(p.shape, AUX / "step" / f"{p.pn}__{p.name}.step")
    assembly_step(cr + [Part(q.name, q.pn, q.shape, q.material, color=q.color) for q in A.build("prototype") if q.group in ("frame", "receiver", "window", "rail")],
                  AUX / "RR-HD-C-600_bench_cradle_with_head.step", "RR_bench_cradle")
    for k, (n, s, m, kd, d) in enumerate(T.gauge_parts(), start=1):
        export_step(s, AUX / "step" / f"RR-HD-G-70{k}__{n}.step")
    export_step(T.shield_can(), PROTO / "step" / "RR-HEAD-SHLD-A__lane_shield_can.step")
    # ---- printed parts in print orientation
    rows = printed_parts()
    plates = {}
    for r in rows:
        o = oriented(r["shape"], r["orient"])
        b = bounds(o)
        r["bbox"] = [round(b[3] - b[0], 1), round(b[4] - b[1], 1), round(b[5] - b[2], 1)]
        r["volume_cm3"] = round(volume(o) / 1000, 1)
        stem = f"{r['pn']}__{r['name']}"
        export_step(o, PROTO / "print" / f"{stem}.step")
        if mesh:
            tris = M.tessellate_to_tris(o, 0.05, 0.3)
            M.write_stl(PROTO / "print" / f"{stem}.stl", tris)
            M.write_3mf(PROTO / "print" / f"{stem}.3mf", [(r["name"], tris)], title=stem)
            r["open_edges"] = M.open_edges(tris)
        summary["print"] += 1
        plates.setdefault(r["plate"], []).append(r)
    man = {"schema": "rr-plates/1",
           "printer": {"model": "Bambu Lab X1 Carbon", "machine_profile": "Bambu Lab X1 Carbon 0.4 nozzle", "bed": [256, 256, 250], "exclude_area": [0, 0, 18, 28], "edge_margin": 3.0},
           "defaults": {"plate_type": "Textured PEI Plate", "process": "0.20mm Standard @BBL X1C", "part_gap": 6.0},
           "notes": ["Not sliced (owner decision: STEP files are imported into Bambu Studio by the owner). Fit is tool-checked by bounding box in the stated orientation "
                     "(mechanical/head/checks.py, 8 mm margin each side, 18 x 28 mm exclusion corner avoided by the shelf pack below).",
                     "Meshes are in print orientation with z = 0 on the bed. qty > 1 parts are packed by the listed positions.",
                     "filament_profile names are the stock Bambu names as used by mechanical/tools; UNVERIFIED against the installed Bambu Studio version."],
           "materials": MATERIALS, "plates": []}
    fits_all = True
    for pid in sorted(plates):
        rs = plates[pid]
        items = []
        for r in rs:
            for k in range(r["qty"] if r["pn"] not in ("RR-HD-X-411",) else 8):
                items.append((f"{r['name']}#{k + 1}", r["bbox"][0], r["bbox"][1], r))
        pos = shelf_pack([(n, w, d) for n, w, d, _ in items])
        if pos is None:      # try the parts rotated 90 deg
            pos = shelf_pack([(n, d, w) for n, w, d, _ in items])
            rot = 90
        else:
            rot = 0
        fits_all &= pos is not None
        mat = rs[0]["material"]
        pl = {"id": pid, "name": ", ".join(sorted({r["name"] for r in rs})), "material": mat, "kit": rs[0]["kit"],
              "overrides": {"wall_loops": rs[0]["walls"], "sparse_infill_density": rs[0]["infill"].split()[0] + "%" if "%" not in rs[0]["infill"].split()[0] else rs[0]["infill"].split()[0].replace(" ", ""),
                            "enable_support": rs[0]["supports"].startswith("yes"), "brim_type": "outer_only" if "brim" in rs[0]["brim"] and rs[0]["brim"] != "none" else "no_brim"},
              "edge_margin": 8.0, "fits_one_plate": pos is not None, "parts": []}
        seen = {}
        for n, w, d, r in items:
            e = seen.setdefault(r["name"], {"part": r["name"], "part_number": r["pn"], "mesh": f"print/{r['pn']}__{r['name']}.stl", "step": f"print/{r['pn']}__{r['name']}.step",
                                            "qty": 0, "positions": [], "rotation_z": rot, "orientation_note": r["note"], "supports": r["supports"], "layer_height": r["layer_height"],
                                            "walls": r["walls"], "infill": r["infill"], "brim": r["brim"], "bbox_print_mm": r["bbox"], "volume_cm3": r["volume_cm3"], "mesh_open_edges": r.get("open_edges")})
            e["qty"] += 1
            if pos:
                e["positions"].append(list(pos[n]))
        pl["parts"] = list(seen.values())
        man["plates"].append(pl)
    (PROTO / "plates.yaml").write_text("# Plate manifest for the printed head parts (schema rr-plates/1, see mechanical/tools/README.md). Generated by mechanical/head/export.py.\n"
                                       + yaml.safe_dump(man, sort_keys=False, width=160))
    summary["plates"] = len(man["plates"])
    summary["all_plates_fit"] = fits_all
    from . import dxf
    summary["dxf"] = dxf.run()
    print("== export:", summary)
    return summary, rows, man


if __name__ == "__main__":
    s, _, _ = run(mesh="--no-mesh" not in sys.argv)
    sys.exit(0 if s["all_plates_fit"] else 1)
