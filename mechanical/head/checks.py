"""Automated checks (evidence class: TOOL-CHECKED on the CadQuery model unless a row says calculated).

Run: python -m mechanical.head.checks        -> out/checks.json, out/head_report.md ; exit 1 if any check FAILS.
Status values: pass | fail | deviation (does not meet a common datum on purpose; needs the lead's decision, listed in the report).
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

import yaml

from .geom import Part

from mechanical.common import params as P

from . import assembly as A
from . import calc as C
from . import hp as H
from . import parts as T
from .geom import OUT, bounds, box, compound, cyl, cyl2, mass_cg, oriented, volume

TOL_VOL = 0.5      # mm3 of overlap tolerated (tessellation-free boolean noise)
BED = (256.0, 256.0, 250.0)     # stock X1C preset volume (mechanical/tools/README.md)
BED_MARGIN = 8.0                # 5 mm brim + 3 mm edge margin on each side
EXCLUDE = (18.0, 28.0)          # front-left corner the X1C cannot print on


def _allowed(a, b):
    for x, y in ((a, b), (b, a)):
        for pat in x.allow:
            if pat == y.name or (pat.endswith("*") and y.name.startswith(pat[:-1])):
                return True
    return False


def interference(parts, label, only_between=None):
    """Pairwise boolean intersection of every pair whose bounding boxes overlap."""
    bbs = [bounds(p.shape) for p in parts]
    hits, n = [], 0
    for i, a in enumerate(parts):
        for j in range(i + 1, len(parts)):
            b = parts[j]
            if only_between and not ((a.name in only_between) ^ (b.name in only_between)):
                continue
            A_, B_ = bbs[i], bbs[j]
            if A_[3] < B_[0] + 1e-6 or B_[3] < A_[0] + 1e-6 or A_[4] < B_[1] + 1e-6 or B_[4] < A_[1] + 1e-6 or A_[5] < B_[2] + 1e-6 or B_[5] < A_[2] + 1e-6:
                continue
            if _allowed(a, b) or a.pn == "-" or b.pn == "-":
                continue
            n += 1
            try:
                v = volume(a.shape.intersect(b.shape))
            except Exception as e:      # noqa: BLE001
                v = float("nan")
            if not (v <= TOL_VOL):
                hits.append((a.name, b.name, round(v, 2)))
    return {"label": label, "pairs_tested": n, "overlaps": hits}


def window_check(parts):
    """Each cassette + frame must leave exactly the contract aperture open: an 80 x 100 probe is free, a probe 0.2 mm larger is not."""
    rows, ok = [], True
    by = {p.name: p for p in parts}
    frames = [p for p in parts if p.name.startswith("frame")]
    for i, yc in enumerate(P.SEG_Y):
        cas = by[f"S{i}_cassette"]
        e = 0.02
        inner = box(P.ROW_X - P.ACTIVE_X / 2 + e, P.ROW_X + P.ACTIVE_X / 2 - e, yc - P.ACTIVE_Y / 2 + e, yc + P.ACTIVE_Y / 2 - e, H.CAS_Z0 - 1, H.Z_SEAT - 0.05)
        v_in = volume(inner.intersect(cas.shape)) + sum(volume(inner.intersect(f.shape)) for f in frames)
        webs = 3 * H.CAS_WEB_W * (P.ACTIVE_Y - 2 * e) * (H.FILM_Z - H.CAS_Z0)
        free = abs(v_in - webs) < 1.0
        edges_ok = True
        x0, x1, ya, yb = P.ROW_X - P.ACTIVE_X / 2, P.ROW_X + P.ACTIVE_X / 2, yc - P.ACTIVE_Y / 2, yc + P.ACTIVE_Y / 2
        z0, z1 = H.CAS_Z0 + 0.2, H.FILM_Z - 0.2
        for strip in (box(x0 - 0.2, x0, ya + 1, yb - 1, z0, z1), box(x1, x1 + 0.2, ya + 1, yb - 1, z0, z1),
                      box(x0 + 1, x1 - 1, yb, yb + 0.2, z0, z1), box(x0 + 1, x1 - 1, ya - 0.2, ya, z0, z1)):
            edges_ok &= volume(strip.intersect(cas.shape)) > 0.99 * volume(strip)
        film = by.get(f"S{i}_film")
        fz = bounds(film.shape)[2] if film else H.FILM_Z
        good = free and edges_ok and abs(fz - P.FILM_Z) < 1e-6
        ok &= good
        rows.append({"lane": i, "centre_y": yc, "aperture_free_except_webs": bool(free), "aperture_edges_at_80x100": bool(edges_ok), "film_underside_z": fz})
    return ok, rows


def printed_catalogue():
    from . import export as E
    return E.printed_parts()


def bed_fit():
    rows, ok = [], True
    lim = (BED[0] - 2 * BED_MARGIN, BED[1] - 2 * BED_MARGIN, BED[2])
    for r in printed_catalogue():
        b = bounds(oriented(r["shape"], r["orient"]))
        dims = (b[3] - b[0], b[4] - b[1], b[5] - b[2])
        fits = (dims[0] <= lim[0] and dims[1] <= lim[1] or dims[1] <= lim[0] and dims[0] <= lim[1]) and dims[2] <= lim[2]
        # the exclusion corner only matters when the part needs the full bed in both directions
        corner_ok = min(dims[0], dims[1]) <= BED[1] - 2 * BED_MARGIN - EXCLUDE[1] or max(dims[0], dims[1]) <= BED[0] - 2 * BED_MARGIN - EXCLUDE[0]
        ok &= fits and corner_ok
        rows.append({"pn": r["pn"], "part": r["name"], "bbox_print_mm": [round(d, 1) for d in dims], "fits": bool(fits and corner_ok)})
    return ok, rows, lim


def bond_pitch(parts):
    """Largest spacing between consecutive BOND points along each prototype EMI fence (requirement <= 50 mm). A bond point is a screw or a
    lid standoff that clamps the fence foot to the spreader; a clearance hole is not counted. Standoff clamping is tool-checked (fence
    material under the standoff base annulus)."""
    by = {p.name: p for p in parts}
    clamp = {}
    for x, y in T.lid_holes():
        ring = cyl(H.LID_STANDOFF_D / 2, H.FENCE_T, (x, y, H.Z_SPR1)).cut(cyl(1.7, 2, (x, y, H.Z_SPR1 - 0.5)))
        on = [n for n in ("fence_front", "fence_side_L", "fence_side_R", "fence_rear") if volume(ring.intersect(by[n].shape)) >= 0.95 * volume(ring)]
        clamp[(x, y)] = on[0] if on else None
    fr = sorted([s_ * y for y in T.FENCE_FRONT_Y for s_ in (1, -1)] + [y for (x, y), f in clamp.items() if f == "fence_front"])
    sd = sorted(list(T.FENCE_SIDE_X) + [x for (x, y), f in clamp.items() if f == "fence_side_L"])
    rr = sorted([s_ * y for y in H.REAR_SCREW_Y for s_ in (1, -1)] + [y for x, y in H.REAR_BOND] + [y for (x, y), f in clamp.items() if f == "fence_rear"])
    gaps = lambda v, lo, hi: max(b - a for a, b in zip([lo] + v, v + [hi]))
    hy = T.FENCE_SIDE_Y + H.FENCE_T
    out = {"front": gaps(fr, -hy, hy), "side": gaps(sd, 79.2, T.FENCE_FRONT_X - 2.7), "rear": gaps(rr, -hy, hy)}
    return out, {f"{x:.1f},{y:+.1f}": f for (x, y), f in clamp.items()}, {"front": fr, "side": sd, "rear": rr}


def lid_pitch():
    """Lid fasteners round the closed loop: largest distance between neighbours (requirement <= 40 mm)."""
    pts = T.lid_loop()
    d = [math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    k = max(range(len(d)), key=lambda i: d[i])
    return len(pts), max(d), (pts[k], pts[(k + 1) % len(pts)])


def drain_check(frame_shapes):
    """Each chimney drain: the three legs are open (probe solids free of frame material) and the straight line from the outlet to the
    inlet is blocked by frame material (no line of sight)."""
    d, rows, ok = H.DRAIN, [], True
    for i, yc in enumerate(P.SEG_Y):
        yd = yc + d["dy"] * (1 if yc > 0 else -1)
        legs = [cyl(0.5, d["z_ch"][0] - H.Z_FB - 0.1, (d["x_out"], yd, H.Z_FB + 0.05)),
                box(d["x_out"], d["x_in"], yd - 0.4, yd + 0.4, d["z_ch"][0] + 0.2, d["z_ch"][1] - 0.2),
                cyl(0.5, H.CHIM_FLOOR_REAR - d["z_ch"][1] - 0.1, (d["x_in"], yd, d["z_ch"][1] + 0.05))]
        open_ = sum(volume(l.intersect(f)) for l in legs for f in frame_shapes) < 1e-3
        r = d["d"] / 2 - 0.05          # extreme sight lines: every pair of opposite rim points of the outlet (bottom) and inlet (top)
        lines = [cyl2(0.02, (d["x_out"] + a * r, yd + b * r, H.Z_FB - 0.01), (d["x_in"] + c * r, yd + e * r, H.CHIM_FLOOR_REAR + 0.01))
                 for a, b in ((-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)) for c, e in ((-1, 0), (1, 0), (0, -1), (0, 1), (0, 0))]
        blocked = all(sum(volume(l.intersect(f)) for f in frame_shapes) > 1e-4 for l in lines)
        ok &= open_ and blocked
        rows.append({"lane": i, "passage_open": bool(open_), "line_of_sight_blocked": bool(blocked)})
    return ok, rows


def overhangs(shape, orient, min_area=4.0):
    """Downward-facing faces (normal z < -0.707) above the bed in print orientation: these need support or bridging."""
    o = oriented(shape, orient)
    out = []
    for f in o.Faces():
        try:
            n = f.normalAt()
        except Exception:      # noqa: BLE001
            continue
        if n.z < -0.707:
            b = bounds(f)
            if b[2] > 0.3 and f.Area() >= min_area:
                out.append({"z": round(b[2], 1), "area_mm2": round(f.Area(), 1), "span_mm": round(min(b[3] - b[0], b[4] - b[1]), 1), "length_mm": round(max(b[3] - b[0], b[4] - b[1]), 1)})
    return sorted(out, key=lambda r: -r["area_mm2"])


FRAME_NET = ("spreader", "lid", "j1_blister", "fence_", "lid_standoffs", "board_standoffs", "hd_board", "hd_lid", "hd_rear", "hd_ffoot", "hd_sfoot", "hd_rbond", "frame")
SHOE_NET = ("shoe_L", "shoe_R", "bridge", "keeper", "hd_thead")


def frame_isolation(parts):
    """Smallest metal-to-metal distance between the FRAME net (spreader, lid, fences, standoffs and their screws) and the receiver metal
    (shoes, bridge, keeper, T-head screws) -- the receiver touches the body channels when docked."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    fr = compound([p.shape for p in parts if p.name.startswith(FRAME_NET) and p.name != "fence_gaskets" and p.material in ("AL6061", "AL5052", "BRASS", "SS304", "STEEL")])
    wash = box(0, 300, -200, 200, 0, H.Z_SPR1 + 0.8)            # the T-head screw sits on an insulating shoulder washer (prototype): metal starts above it
    sh = compound([p.shape.cut(wash) if p.name.startswith("hd_thead") else p.shape for p in parts if p.name.startswith(SHOE_NET) and not p.name.startswith("shoe_isolator")])
    d = BRepExtrema_DistShapeShape(fr.wrapped, sh.wrapped)
    d.Perform()
    p1, p2 = d.PointOnShape1(1), d.PointOnShape2(1)
    return d.Value(), (round(p1.X(), 1), round(p1.Y(), 1), round(p1.Z(), 1))


# ------------------------------------------------------------------------------------------------ RR-HEAD-ACQ as built vs the head (IB-52)
BOARD_SKIP = ("H28", "SH1013", "SH1113", "SH1213", "SH1313")     # holes and cans are compared separately (cans enclose their parts by design)


def board_asbuilt():
    from . import asbuilt as AB
    return AB.load()


def board_fit(builds):
    """Compare the board AS BUILT (electronics/head_acq/RR-HEAD-ACQ.kicad_pcb) with the head model. Returns (rows, data); each row is
    (item, ok, detail). Everything is read from the board file; the model values come from hp.py / parts.py."""
    from . import asbuilt as AB
    fp, meta = board_asbuilt()
    rows, data = [], {"source": {k: v for k, v in meta.items() if k != "hole_keepouts"}}
    tol = 0.01
    # (a) mounting holes: board file vs model standoffs vs spreader holes
    holes = sorted((round(AB.to_base(r["u"], r["v"])[0], 3), round(AB.to_base(r["u"], r["v"])[1], 3)) for k, r in fp.items() if k.startswith("H28"))
    model = sorted((round(x, 3), round(y, 3)) for x, y, _ in T.board_holes())
    spr = sorted((round(x, 3), round(y, 3)) for x, y, d, why in T.spreader_holes() if "board standoff" in why)
    ok = len(holes) == 8 and all(math.dist(a, b) <= tol for a, b in zip(holes, model)) and model == spr
    h1 = AB.to_base(fp["H2801"]["u"], fp["H2801"]["v"])
    rows.append(("8 mounting holes (H2801..H2808) = model standoffs = spreader clinch holes", ok,
                 f"board file {holes}; H1 (H2801) at u/v ({fp['H2801']['u']}, {fp['H2801']['v']}) = base ({h1[0]:.1f}, {h1[1]:.1f}) (CR-M02)"))
    # (b) shield cans: outline, mouse holes, clips
    oz = H.ACQ["origin"][2] + H.ACQ["thickness"]
    can_rows = []
    for k, lane in ((10, 0), (11, 1), (12, 2), (13, 3)):
        c = fp[f"SH{k}13"]
        u0, v0, u1, v1 = c["fab_uv"]
        x0, x1, y0, y1 = AB.uv_box_to_base(c["fab_uv"])
        b = bounds(T.shield_can(lane))
        out_ok = all(abs(a - b_) <= tol for a, b_ in ((x0, b[0]), (x1, b[3]), (y0, b[1]), (y1, b[4]))) and abs(b[2] - oz) < 1e-6 and abs(b[5] - oz - c["height"]) < 1e-6
        lc = (u0 + u1) / 2
        mice = sorted(round((r[0] + r[2]) / 2 - lc, 3) for r in c["fab_rects_uv"] if abs((r[2] - r[0]) - H.MOUSE_W) < 0.01 and abs(r[1] - v0) < 0.01)
        anodes = sorted(round(fp[f"J{100 * (lane + c_) + 1}"]["pads_uv"][0][1] - lc, 3) for c_ in (1, 5))    # floor / reference anode U.FL, pad 1 (centre)
        can = T.shield_can(lane)
        holes_open = all(volume(can.intersect(box(x0 - 0.5, x0 + 0.5, P.SEG_Y[lane] - du - 0.6, P.SEG_Y[lane] - du + 0.6, oz + 0.2, oz + 1.0))) < 1e-6 for du in H.CAN_MOUSE_DU)
        mice_ok = mice == sorted(H.CAN_MOUSE_DU) and anodes == sorted(H.CAN_MOUSE_DU) and holes_open
        clips = [fp[f"SH{k}{n:02d}"] for n in range(1, 13)]
        walls = {"rear": v0 + 0.1, "front": v1 - 0.1, "left": u0 + 0.1, "right": u1 - 0.1}     # wall mid-planes (0.2 wall)
        on_wall = []
        for cl in clips:
            d = min(abs(cl["v"] - walls["rear"]), abs(cl["v"] - walls["front"])) if cl["rot"] in (0.0, 180.0) else min(abs(cl["u"] - walls["left"]), abs(cl["u"] - walls["right"]))
            on_wall.append(d <= 0.05)
        clear_of_mice = all(min(abs(cl["u"] - lc - du) for du in H.CAN_MOUSE_DU) > 2.0 for cl in clips if abs(cl["v"] - walls["rear"]) < 0.1)
        can_rows.append({"lane": lane, "outline_uv": c["fab_uv"], "model_bbox_x_y": [round(b[0], 2), round(b[3], 2), round(b[1], 2), round(b[4], 2)],
                         "outline_ok": out_ok, "mouse_du_board": mice, "anode_pad_du": anodes, "mouse_holes_open_in_model": holes_open,
                         "clips_on_wall": sum(on_wall), "clips_clear_of_mouse_holes": clear_of_mice})
        ok_can = out_ok and mice_ok and all(on_wall) and clear_of_mice
        if not ok_can:
            rows.append((f"shield can lane {lane}", False, json.dumps(can_rows[-1])))
    data["cans"] = can_rows
    if all(r["outline_ok"] for r in can_rows):
        r0 = can_rows[0]
        rows.append(("4 shield cans: outline v 8.25..40.25 (CR-M01), 2 mouse holes at the anode U.FL pads (CR-M04), 12 clips on the wall line each", all(
            r["outline_ok"] and r["clips_on_wall"] == 12 and r["clips_clear_of_mouse_holes"] and r["mouse_du_board"] == r["anode_pad_du"] for r in can_rows),
            f"lane 0 outline u/v {r0['outline_uv']} = model x/y {r0['model_bbox_x_y']}; mouse holes du {r0['mouse_du_board']} (board) = anode pads {r0['anode_pad_du']} "
            f"= model {sorted(H.CAN_MOUSE_DU)}, open in the can solid; clips on the wall mid-plane 12/12 per can"))
    # (c) J1 port at the J2001 centre (CR-M03 a), Micro-Fit bodies as in hp.py
    jb = fp["J2001"]["fab_uv"]
    y_j = 163.0 - (jb[0] + jb[2]) / 2
    ok = abs(H.PORT_Y["J1"] - y_j) <= 0.1 and all(abs(fp[r]["fab_uv"][0] - u0) < tol and abs(fp[r]["fab_uv"][2] - u1) < tol for r, (u0, u1) in H.MICROFIT_BODY_U.items())
    rows.append(("J1 cable port at the J2001 centre (CR-M03 a); Micro-Fit bodies = hp.MICROFIT_BODY_U", ok,
                 f"J2001 body u {jb[0]}..{jb[2]} -> centre y {y_j:.2f}; port y {H.PORT_Y['J1']:.2f} (hp.PORT_Y); J2601 body u {fp['J2601']['fab_uv'][0]}..{fp['J2601']['fab_uv'][2]}"))
    # (d) every component body (courtyard, else fab outline, x the 3D envelope height; Micro-Fit at the IB-19 allowance) vs the head solids
    heads = [p for p in builds["prototype"] + [q for q in builds["production"] if q.name == "frame"]
             if p.group not in ("optic", "lane", "window", "rail") and not p.name.startswith(("pcb", "S0_shield", "S1_shield", "S2_shield", "S3_shield", "plug_ko", "pigtail", "plug_J", "fasteners_lumped"))]
    hb = [(p, bounds(p.shape)) for p in heads]
    hits, n, worst = [], 0, (99.0, "")
    over = []
    for ref, r in fp.items():
        if ref.startswith(BOARD_SKIP) or r["height"] is None:
            continue
        bb = r["crtyd_uv"] or r["fab_uv"]
        if bb is None:
            continue
        hgt = H.MICROFIT_H_ALLOW if ref in H.MICROFIT_BODY_U else r["height"]
        inj1 = 50 <= r["u"] <= 100 and r["v"] <= 18
        if r["height"] > (8.3 if inj1 else H.ACQ["max_top"]) or r["side"] != "F":
            over.append((ref, r["height"], r["side"]))
        x0, x1, y0, y1 = AB.uv_box_to_base(bb)
        z1 = oz + hgt
        fb = box(x0, x1, y0, y1, oz, z1)
        for p, b in hb:
            if b[3] < x0 or b[0] > x1 or b[4] < y0 or b[1] > y1 or b[5] < oz or b[2] > z1:
                continue
            n += 1
            v = volume(fb.intersect(p.shape))
            if v > TOL_VOL:
                hits.append((ref, p.name, round(v, 2)))
        # vertical clearance to the ceiling straight above (lid / liner / blister), for the report
        cz = min((b[2] for p, b in hb if p.name in ("lid", "lid_liner", "j1_blister") and b[0] < x1 and b[3] > x0 and b[1] < y1 and b[4] > y0
                  and volume(box(x0, x1, y0, y1, z1, 50).intersect(p.shape)) > 1e-6), default=None)
        if cz is not None:
            lo = min((bounds(box(x0, x1, y0, y1, z1, 50).intersect(p.shape))[2] for p, b in hb if p.name in ("lid", "lid_liner", "j1_blister")
                      and volume(box(x0, x1, y0, y1, z1, 50).intersect(p.shape)) > 1e-6), default=99)
            if lo - z1 < worst[0]:
                worst = (lo - z1, ref)
    data["component_pairs_tested"] = n
    rows.append((f"{sum(1 for k in fp if not k.startswith(BOARD_SKIP))} component bodies (board-file courtyard x 3D envelope height; Micro-Fit at {H.MICROFIT_H_ALLOW:g} mm) vs every head part",
                 not hits and not over, f"{n} candidate pairs intersected; overlaps: {hits or 'none'}; height-zone violations (6.0 top / 8.3 J1 landing / top side only): {over or 'none'}; "
                 f"smallest clearance to the lid / liner / blister above a body: {worst[0]:.2f} mm ({worst[1]})"))
    # (f) frame contact at every mounting hole (stage 3, S3-03 / S3-05): each hole is its own frame net on the board
    nets_of = {}
    for ref, r in fp.items():
        for pd in r.get("pads", []):
            if pd["net"]:
                nets_of.setdefault(pd["net"], set()).add(ref)
    metal = ("BRASS", "AL6061", "SS304", "STEEL", "AL5052")
    so = {b_: next(p for p in builds[b_] if p.name == "board_standoffs") for b_ in ("prototype", "production")}
    spr_ok = all(next(p for p in builds[b_] if p.name == "spreader").material in metal for b_ in so)
    fc = []
    screw_r = 2.75          # M2.5 serrated (lock) washer OD 5.5 under the pan head (recalled DIN 6798 A, UNVERIFIED); pan head r 2.25
    for k in range(1, 9):
        ref = f"H280{k}"
        r = fp[ref]
        nets = sorted({pd["net"] for pd in r["pads"] if pd["net"]})
        others = sorted(set().union(*[nets_of.get(n, set()) for n in nets]) - {ref})
        pad_r = max(max(pd["size"]) for pd in r["pads"] if pd["size"]) / 2
        ko = meta["hole_keepouts"].get(f"KO_{ref}")
        ko_r = min(math.dist((r["u"], r["v"]), q) for q in ko) if ko else None
        xb, yb = AB.to_base(r["u"], r["v"])[:2]
        has_so = any(math.dist((xb, yb), (cx, cy)) < 0.01 for cx, cy, _ in T.board_holes())
        fc.append({"hole": ref, "uv": (r["u"], r["v"]), "base": (round(xb, 1), round(yb, 1)), "board_nets": nets, "board_parts_on_net": others,
                   "pad_r": pad_r, "copper_keepout_r": round(ko_r, 2) if ko_r else None, "standoff_metal_both_builds": has_so and all(q.material in metal for q in so.values()) and spr_ok,
                   "washer_to_foreign_copper_mm": round(ko_r - screw_r, 2) if ko_r else None})
    data["frame_contacts"] = fc
    expects = [f for f in fc if f["board_parts_on_net"]]
    rows.append(("frame contact at every hole the board relies on (F2801/R2801 at H1, capacitors / J2 shield parts at H2..H8): metal standoff clinched in the "
                 "aluminium spreader + M2.5 screw and serrated washer on the hole pad, both builds", all(f["standoff_metal_both_builds"] for f in fc),
                 "; ".join(f"{f['hole']} {'/'.join(f['board_nets'])} ({', '.join(f['board_parts_on_net'][:4]) or 'no part'})" for f in fc)
                 + f"; {len(expects)} holes carry parts, all 8 have the metal stack. H3 washer edge to the edge of its copper keep-out (BUS_GND side): "
                 f"{next(f for f in fc if f['hole'] == 'H2803')['washer_to_foreign_copper_mm']} mm (pad r {next(f for f in fc if f['hole'] == 'H2803')['pad_r']:.2f})"))
    # (g) bottom side: the head has no room under the board for parts it does not know about -> fail loudly, never skip
    bottom = sorted(k for k, r in fp.items() if r["side"] == "B" or r.get("b_crtyd_uv") or r.get("b_fab_uv"))
    rows.append(("no bottom-side parts on the board (B.Cu footprints / B.CrtYd / B.Fab read; the spreader is 2.5 mm below the PCB)", not bottom,
                 f"bottom-side footprints: {bottom or 'none'}"))
    # (e) mated Micro-Fit plug keep-outs: their interference with the head is part of the assembly interference check; record the rear-strip numbers
    plugs = {ref: bounds(ko) for ref, ko in T.microfit_plugs()}
    data["plug_keepouts_xyz"] = plugs
    back = min(b[0] for b in plugs.values())
    rows.append((f"mated plug keep-outs (Micro-Fit CR-M06 v {H.PLUG_V[0]:g}..{H.PLUG_V[1]:g} at the IB-19 height; J2501 GH-8 CR-M08) clear of standoffs, fences, cut-out, NTC, bond screws, lid", True,
                 f"keep-outs x {back:.1f}..{max(b[3] for b in plugs.values()):.1f}, y {min(b[1] for b in plugs.values()):.2f}..{max(b[4] for b in plugs.values()):.2f}, "
                 f"z {oz:.1f}..{oz + H.MICROFIT_H_ALLOW:.1f}: in the prototype and production assemblies (interference checks above, parts plug_ko_J2001 / plug_ko_J2601 / plug_ko_J2501)"))
    return rows, data


RIGID = ("frame", "spreader", "lid", "j1_blister", "pcb", "S0_shield", "S1_shield", "S2_shield", "S3_shield", "lid_standoffs", "board_standoffs", "fence_",
         "hd_", "desiccant", "sw_", "thermal_cutout", "ntc", "boot_", "S0_chimney", "S1_chimney", "S2_chimney", "S3_chimney", "shoe_", "bridge")


def harness_checks(builds, res, add):
    """Review M5 / M6 / M11: GH plug keep-outs, routed internal leads, pigtails against the body (docked, parked, docking stroke), ToF sight lines,
    out/lead_routes.yaml."""
    from . import pigtail as PG
    from . import routes as RT
    fp, meta = board_asbuilt()
    # (1) mated GH plugs incl. wire exit (CR-M08 template) vs every hard head part
    ko = RT.gh_keepouts(fp)
    rear, front = {}, {}
    for b_ in ("prototype", "production"):
        hard = [(p, bounds(p.shape)) for p in builds[b_] if p.pn != "-" and p.group not in ("optic", "lane", "window") and not p.name.startswith(("pcb", "plug_ko", "pigtail", "plug_J", "fasteners_lumped"))]
        for ref, k in ko.items():
            bx = box(*k)
            for p, bb in hard:
                if bb[3] < k[0] or bb[0] > k[1] or bb[4] < k[2] or bb[1] > k[3] or bb[5] < k[4] or bb[2] > k[5]:
                    continue
                v = volume(bx.intersect(p.shape))
                if v > TOL_VOL:
                    (rear if ref in RT.GH_REAR else front).setdefault(ref, set()).add(f"{p.name} ({b_})")
    res["data"]["gh_keepouts"] = {r: [round(v, 2) for v in k] for r, k in ko.items()}
    add("mated GH plugs + wire exit, rear edge (J1001..J1301 lane aux, J2501): clear of every head part (both builds)", "pass" if not rear else "fail",
        f"keep-outs {GH_TXT} for {', '.join(RT.GH_REAR)}; clashes: {({k: sorted(v) for k, v in rear.items()}) or 'none'}", "tool-checked against the board file")
    add("mated GH plugs + wire exit, FRONT edge (J2002 / J2003 / J2004 rail switches, J2201 lid switch, J2402)", "deviation" if front else "pass",
        f"keep-outs to x {max(ko[r][1] for r in RT.GH_FRONT):.1f} (front wall inner face x {H.BAY_X1}, prototype front EMI fence x 180.0..180.5); clashes: "
        f"{({k: sorted(v) for k, v in front.items()}) or 'none'}. The side-entry GH headers face the front wall from 0.8 mm inside the board edge: mated plug + "
        "crimp + one bend need about 11.5 mm beyond the header body, the front strip has 6.4 (production) / 1.5 (prototype, fence). Board-side change requested "
        "(CR-H17 in mechanical/head/CHANGE_REQUESTS.md: top-entry GH headers or headers >= 6 mm further rearward)", "tool-checked against the board file")
    # (2) pigtails vs the body (read-only STEP of mechanical/prototype_x1c)
    pig = PG.evaluate()
    res["data"]["pigtails"] = {k: ({kk: vv for kk, vv in v.items() if not kk.startswith("_")} if isinstance(v, dict) and k in ("J1", "J2") else v) for k, v in pig.items()}
    for n in ("J1", "J2"):
        g = pig[n]
        add(f"{n} pigtail free of the body: docked (mated) route, parked (unmated) set and the {pig['stroke_mm']:g} mm docking stroke",
            "pass" if g["ok"] else "fail",
            f"cable {g['cable_d']} mm, catalogue bend radius {g['bend_r']:g} (route at {g['docked_min_radius_mm']:g}); boot top {g['boot_top']} -> plug back {g['plug_back']} "
            f"(body J{n[1]}_mated_plug.step): {g['docked_length_mm']:.0f} mm, x {g['docked_x_range']}, y {g['docked_y_range']}, apex z {g['docked_apex_z']:.0f}; body hits {g['docked_clash'] or 'none'}, "
            f"clearance >= {g['docked_min_gap_mm']:g} mm (sampled rings). Parked: loop R {g['parked']['loop_r_mm']}, apex z {g['parked']['apex_z']:.0f}, plug in the holster at "
            f"{g['parked']['holster_xy']}; hits at stroke positions {g['parked']['clash_by_stroke_position']}; swept volume {g['swept_volume']}. Clip / strain relief = the boot "
            "(z 46..70), outside datum A and every seating face", "tool-checked (sampled point classification on the body STEP files) + calculated")
    # (3) ToF look-ahead sight lines vs the docked pigtails (cone half-angle 9 deg = 18 deg FoV, UNVERIFIED)
    worst = (180.0, None)
    for k, t in P.TOF_SENSORS.items():
        if "fwd" not in k:
            continue
        o, dv = np.array(t["xyz"], float), np.array(t["dir"], float)
        dv /= np.linalg.norm(dv)
        for n in ("J1", "J2"):
            for q in pig[n]["_docked_points"]:
                w = np.array(q, float) - o
                ang = math.degrees(math.acos(float(np.clip(w @ dv / np.linalg.norm(w), -1, 1)))) - math.degrees(math.atan(pig[n]["cable_d"] / 2 / np.linalg.norm(w)))
                if ang < worst[0]:
                    worst = (ang, (k, n, tuple(round(float(c), 0) for c in q)))
    res["data"]["tof_pigtail_angle_deg"] = worst
    add("forward look-ahead ToF cones (18 deg FoV, UNVERIFIED) clear of the docked pigtails", "pass" if worst[0] > 9.0 else "deviation",
        f"smallest angle between a sensor axis and the cable surface {worst[0]:.1f} deg ({worst[1]}); cone half-angle 9 deg", "calculated")
    # (4) every lead inside the head as a routed tube vs the rigid head parts
    R = RT.routes(fp, pig)
    hits = {}
    for b_ in ("prototype", "production"):
        rig = [(p, bounds(p.shape)) for p in builds[b_] if p.name.startswith(RIGID)]
        for r in R:
            if not r["points"]:
                continue
            t = RT.tube(r["points"][1:-1] if len(r["points"]) > 3 else r["points"], r["bundle_d"])
            tb = bounds(t)
            for p, bb in rig:
                if bb[3] < tb[0] or bb[0] > tb[3] or bb[4] < tb[1] or bb[1] > tb[4] or bb[5] < tb[2] or bb[2] > tb[5]:
                    continue
                v = volume(t.intersect(p.shape))
                if v > 0.5:
                    hits.setdefault(f"{r['cable_id']} {r['lead'][:40]}", set()).add(f"{p.name} ({b_}) {v:.1f} mm3")
    res["data"]["lead_route_hits"] = {k: sorted(v) for k, v in hits.items()}
    add(f"{sum(1 for r in R if r['points'])} routed leads inside the head (end terminations excluded) clear of the rigid head parts (both builds)", "pass" if not hits else "fail",
        f"hits: {({k: sorted(v) for k, v in hits.items()}) or 'none'}; routes and lengths in out/lead_routes.yaml", "tool-checked (tube solids on the stated waypoints)")
    RT.write_yaml(R, OUT / "lead_routes.yaml", {"board_file": meta["file"], "board_mtime_utc": meta["mtime_utc"],
                                               "pigtail_docked": {n: {"boot_top": pig[n]["boot_top"], "plug_back": pig[n]["plug_back"], "free_length_mm": pig[n]["docked_length_mm"]} for n in ("J1", "J2")},
                                               "note_harness_ids": "W-105 / W-106 sides: board J2003 = LEFT, J2004 = RIGHT (design/circuit.py loop order F, L, R; S2-L6); "
                                                                   "harness/cables.csv has W-105 RIGHT -> J2003 and W-106 LEFT -> J2004 (swapped)"})
    res["data"]["lead_routes"] = {r["cable_id"] + " | " + r["lead"]: r["length_mm"] for r in R}
    return R, pig


GH_TXT = "courtyard width x 7.25 mm beyond the mating-side courtyard edge x 4.3 mm high (CR-M08 template, UNVERIFIED housing data)"


def spreader_hole_web(min_web=1.0):
    """Every pair of spreader holes keeps >= min_web of material between their edges (CSK seats counted at the 5.2 head diameter)."""
    hs = [(x, y, 5.2 if "countersunk" in why else d, why) for x, y, d, why in T.spreader_holes()]
    worst = (99.0, None)
    for i in range(len(hs)):
        for j in range(i + 1, len(hs)):
            a, b = hs[i], hs[j]
            w = math.dist(a[:2], b[:2]) - (a[2] + b[2]) / 2
            if w < worst[0]:
                worst = (w, (a[:2], a[3][:30], b[:2], b[3][:30]))
    return worst


def run():
    t0 = time.time()
    res = {"generated_by": "mechanical/head/checks.py", "contract_version": P.CONTRACT_VERSION, "checks": [], "data": {}}

    def add(name, status, detail, cls="tool-checked"):
        res["checks"].append({"check": name, "status": status, "evidence": cls, "detail": detail})
        print(f"  [{status.upper():9s}] {name}: {detail if isinstance(detail, str) else ''}"[:230])

    builds = {b: A.build(b) for b in ("prototype", "production")}
    m_proto, cg_proto = mass_cg(builds["prototype"])
    dummy, t_ballast = A.build_dummy(m_proto)
    builds["dummy"] = dummy

    # 1 interference, rails at rest
    for b, parts in builds.items():
        r = interference(parts, b)
        add(f"no interference, {b} assembly, rails at rest", "pass" if not r["overlaps"] else "fail", f"{r['pairs_tested']} candidate pairs intersected; overlaps: {r['overlaps'] or 'none'}")
    # 1b interference at full stroke (leading rail on its stop; side rails on their stops) and with the 5 mm inserts
    for proj, trav in ((3.0, H.RAIL_GAP), (5.0, 0.0), (5.0, H.RAIL_GAP)):
        parts = A.build("prototype", projection=proj, travel=trav)
        moving = {p.name for p in parts if p.name.startswith(("rail_bar", "rail_insert", "guide_rod", "bail", "stop_pin"))} - {"bail_block_C", "bail_block_L", "bail_block_R"}
        sub = [p for p in parts if p.group in ("rail", "frame", "window", "receiver", "switch", "deck") and not p.name.startswith("rod_spring")]
        r = interference(sub, f"proj {proj} travel {trav}", only_between=moving)
        add(f"no interference, leading rail travel {trav:g} mm, {proj:g} mm insert", "pass" if not r["overlaps"] else "fail", f"{r['pairs_tested']} pairs; overlaps: {r['overlaps'] or 'none'}")
    s_full = H.SIDE_GAP * math.sqrt(2) - 0.02
    parts = [p for p in builds["prototype"] if p.group in ("frame", "window", "receiver", "switch", "deck") or p.name.startswith("guide_pins")]
    side_parts = [Part(f"side_rail_{t}", "-", T.side_rail(s, s_full), "SS301", allow={f"guide_pins_{t}", f"sw_side_{t}"}) for s, t in ((1, "L"), (-1, "R"))]
    r = interference(parts + side_parts, "side stroke", only_between={"side_rail_L", "side_rail_R"})
    add(f"no interference, side rails at their positive stop (slide {s_full:.2f} mm)", "pass" if not r["overlaps"] else "fail", f"{r['pairs_tested']} pairs; overlaps: {r['overlaps'] or 'none'}")

    # 2 windows and film plane
    for b in ("prototype", "production"):
        ok, rows = window_check(builds[b])
        add(f"four 80 x 100 windows at the contract positions, film underside z = {P.FILM_Z:g} ({b})", "pass" if ok else "fail", json.dumps(rows))
    # 3 rail underside
    for proj in P.RAIL_PROJECTIONS:
        zs = [bounds(T.insert_segment(k, proj))[2] for k in range(4)]
        want = P.FILM_Z - proj
        low_other = min(bounds(p.shape)[2] for p in builds["prototype"] if not p.name.startswith(("rail_insert",)))
        ok = all(abs(z - want) < 1e-6 for z in zs) and low_other >= want - 1e-6 if proj == 3.0 else all(abs(z - want) < 1e-6 for z in zs)
        add(f"leading rail underside with the {proj:g} mm insert orientation", "pass" if ok else "fail", f"insert underside z = {zs[0]:.2f} (required {want:.2f}); lowest other part z = {low_other:.2f} (side rails {H.SIDE_Z0:.1f})")
    p5 = A.build("prototype", projection=5.0)
    zs3 = [bounds(p.shape)[2] for p in builds["prototype"] if p.name.startswith("side_rail")]
    zs5 = [bounds(p.shape)[2] for p in p5 if p.name.startswith("side_rail")]
    ok = all(abs(z - (P.FILM_Z - 3.0)) < 1e-6 for z in zs3) and all(abs(z - (P.FILM_Z - 5.0)) < 1e-6 for z in zs5)
    movers = {p.name for p in p5 if p.name.startswith(("side_rail", "rail_insert"))}
    r = interference([p for p in p5 if p.group in ("frame", "window", "receiver", "rail", "switch", "deck", "fastener")], "5 mm rails", only_between=movers)
    add("side rails / wing returns underside for both projections (RR-HD-S-431/432 3 mm, RR-HD-S-433/434 5 mm)", "pass" if ok and not r["overlaps"] else "fail",
        f"side strip underside z = {zs3[0]:.2f} (3 mm set) / {zs5[0]:.2f} (5 mm set); 5 mm set vs head: {r['pairs_tested']} pairs, overlaps {r['overlaps'] or 'none'}")
    # 4 board standoffs
    env = yaml.safe_load((P.HERE / "board_envelopes.yaml").read_text())["RR-HEAD-ACQ"]
    want = sorted(tuple(round(v, 3) for v in h["base_link_xyz_mm"]) for h in env["mounting"]["holes"])
    got = sorted((round(x, 3), round(y, 3), round(H.Z_SPR1 + H.STANDOFF_BOARD_H, 3)) for x, y, _ in T.board_holes())
    sp_holes = {(round(x, 3), round(y, 3)) for x, y, d, why in T.spreader_holes() if "board standoff" in why}
    holes_p = sorted((round(x, 3), round(y, 3), round(H.Z_SPR1 + H.STANDOFF_BOARD_H, 3)) for x, y in
                     [P.board_to_base(H.ACQ["origin"], u, v)[:2] for u, v in H.ACQ["holes_uv"]])
    ok = got == holes_p and sp_holes == {(a, b) for a, b, _ in got} and abs(bounds(T.pcb())[2] - env["origin_base_link_mm"][2]) < 1e-6
    add("eight M2.5 board standoffs and PCB underside match params.HEAD_ACQ (board file comparison below)", "pass" if ok else "fail", f"standoff tops {got}")
    # interface records owned by mechanical/common must follow the as-built board (IB-52); the head model follows the board file
    stale = []
    if want != got:
        stale.append(f"board_envelopes.yaml hole table {[w for w in want if w not in got]} vs as built {[g for g in got if g not in want]}")
    if abs(H.PORT["J1"][1] - H.PORT_Y["J1"]) > 1e-6:
        stale.append(f"params.HEAD_PIGTAIL_EXIT J1 y {H.PORT['J1'][1]} vs head port y {H.PORT_Y['J1']} (CR-M03 a)")
    add("mechanical/common interface records follow the as-built board (IB-52: board_envelopes.yaml holes, HEAD_PIGTAIL_EXIT)", "deviation" if stale else "pass",
        "; ".join(stale) + ("; owner mechanical/common (head model already follows the board file)" if stale else "board_envelopes.yaml and params agree with the head"), "design note")
    fit_rows, fit_data = board_fit(builds)
    res["data"]["board_fit"] = fit_data
    for item, ok_, det in fit_rows:
        add(f"RR-HEAD-ACQ as built vs head: {item}", "pass" if ok_ else "fail", det, "tool-checked against electronics/head_acq/RR-HEAD-ACQ.kicad_pcb")
    harness_checks(builds, res, add)
    web = spreader_hole_web()
    add("spreader plate: every hole pair keeps >= 1.0 mm web (countersinks at 5.2 mm)", "pass" if web[0] >= 1.0 else "fail",
        f"smallest web {web[0]:.2f} mm between {web[1][0]} ({web[1][1]}) and {web[1][2]} ({web[1][3]})")
    plugs = [b_ for _, b_ in [(r, bounds(k)) for r, k in T.microfit_plugs()]]
    behind = min(b_[0] for b_ in plugs) - H.BAY_X0
    fan = {"prototype (to the comb wall x %.1f)" % (T.FENCE_REAR_X + H.FENCE_T): C.j1_fan_in(board_asbuilt()[0], T.FENCE_REAR_X + H.FENCE_T),
           "production (to the rear wall x %.1f)" % H.BAY_X0: C.j1_fan_in(board_asbuilt()[0], H.BAY_X0)}
    res["data"]["j1_wire_exit_mm"] = {"to_rear_wall": round(behind, 2), "required_single_bend": H.WIRE_EXIT_MIN, "fan_in": fan}
    ok = behind >= H.WIRE_EXIT_MIN and all(v["ok"] for v in fan.values())
    add("J1 landing harness buildable: wire exit + one bend behind the mated J2001 / J2601 plugs into the rear strip, rise to the J1 boot (review M6 routing)", "pass" if ok else "fail",
        f"plug backs at x {min(b_[0] for b_ in plugs):.1f} (v {H.PLUG_V[0]:g}, CR-M06): {behind:.1f} mm to the rear wall. Per wire 2 mm straight + 90-degree bend at R = 2 x OD into "
        "the strip, run +y at x 76.6 to the boot slot, rise there: " + "; ".join(f"{k}: {v['available_mm']} mm available, worst pin needs {max(r['x_needed_mm'] for r in v['rows'])} mm, "
        f"largest wire OD that fits {v['max_od_that_fits_mm']} mm" for k, v in fan.items()) + f" (AWG 20 assumed {H.J1_WIRE_OD['20']} mm; PVC UL1007 about 1.9 mm also fits; OD UNVERIFIED)",
        "calculated on tool-checked positions")
    top, bot, j1 = T.pcb_keepouts()
    lid_under = bounds(T.lid())[2]
    liner_under = lid_under - T.LINER_T
    pcb_top = H.ACQ["origin"][2] + H.ACQ["thickness"]
    ok = bounds(top)[5] <= liner_under + 1e-6 and bounds(bot)[2] >= H.Z_SPR1 - 1e-6 and lid_under - pcb_top >= 6.3 and (H.Z_LID1 - pcb_top) >= 8.3
    add("board height limits: 6.0 top / 2.0 bottom, >= 6.3 mm clear under the lid, >= 8.3 mm over J1_LANDING", "pass" if ok else "fail",
        f"PCB top {pcb_top:.1f}; lid underside {lid_under:.1f} ({lid_under - pcb_top:.1f} mm), liner underside {liner_under:.1f} ({liner_under - pcb_top:.1f} mm); "
        f"J1 blister underside {H.Z_LID1:.1f} ({H.Z_LID1 - pcb_top:.1f} mm); bottom keep-out to spreader {bounds(bot)[2] - H.Z_SPR1:.2f} mm")
    cans_top = pcb_top + 5.0
    add("lane shield cans (36 x 32 x 5) clear of lid liner, standoffs and fences", "pass" if cans_top + 0.5 <= liner_under else "fail",
        f"can top z {cans_top:.1f}, liner underside {liner_under:.1f}; pairwise clearance covered by the interference check")
    # 5 envelope
    for b in ("prototype", "production"):
        parts = builds[b]
        fixed = [p for p in parts if p.pn != "-" and not p.name.startswith(("pigtail", "plug", "shoe_L", "shoe_R", "rail_bar", "rail_insert", "guide_rod", "bail", "bail_clip"))
                 or p.name.startswith("bail_block")]
        bb = bounds(compound([p.shape for p in fixed]))
        e = P.HEAD_ENV_E_CEILING
        ok = bb[0] >= e["x"][0] - 1e-6 and bb[3] <= e["x"][1] + 1e-6 and bb[1] >= e["y"][0] - 1e-6 and bb[4] <= e["y"][1] + 1e-6 and bb[2] >= e["z"][0] - 1e-6 and bb[5] <= e["z"][1] + 1e-6
        add(f"head without the leading-rail stroke system inside the contract envelope ({b})", "pass" if ok else "fail",
            f"x {bb[0]:.2f}..{bb[3]:.2f} ({e['x'][0]}..{e['x'][1]}), y {bb[1]:.2f}..{bb[4]:.2f} (+-175), z {bb[2]:.2f}..{bb[5]:.2f} ({e['z'][0]}..{e['z'][1]}; lid top {H.Z_LID1:.1f}, jacket top {H.Z_LID1 + H.JACKET_T:.1f}, keeper hook {bb[5]:.1f})")
    rail = [p for p in builds["prototype"] if p.name.startswith(("rail_bar", "rail_insert", "bail"))]
    bbr = bounds(compound([p.shape for p in rail]))
    xe = P.HEAD_ENV_E_CEILING["x"][1]
    full = bounds(compound([p.shape for p in A.build("prototype", travel=H.RAIL_GAP) if p.name.startswith(("rail_bar", "rail_insert"))]))[3]
    res["data"]["rail_front_face"] = {"unloaded_x": bbr[3], "full_stroke_x": full, "window_front_edge_x": H.WIN_X1,
                                      "residual_strip_unloaded_mm": bbr[3] - H.WIN_X1, "residual_strip_full_stroke_mm": full - H.WIN_X1}
    add(f"leading rail inside the contract envelope x <= {xe:g} (draft6, sprung rail admitted)", "pass" if bbr[3] <= xe + 1e-6 else "fail",
        f"rail front face unloaded x {bbr[3]:.1f}, fully stroked (bar on the frame face) x {full:.1f}; end-wall residual strip window front edge x {H.WIN_X1:.1f} to rail face: "
        f"{bbr[3] - H.WIN_X1:.1f} mm unloaded, {full - H.WIN_X1:.1f} mm stroked; outer corner radius {math.hypot(bbr[3], 175):.0f} mm")
    add("lid top at HEAD_TOP_Z", "pass" if abs(H.Z_LID1 - P.HEAD_TOP_Z) < 1e-6 else "fail", f"lid top z = {H.Z_LID1}; local items above it: J1 blister z 46.0, keeper z 49.8 (ceiling 50, latch box z 46..60)")
    # 6 receiver interface
    sh = T.shoe(1)
    bs = bounds(sh)
    tip = bounds(sh.intersect(box(H.SHOE_X0 - 1, H.SHOE_X0 + 0.01, 0, 200, 0, 60)))
    sec = bounds(sh.intersect(box(30, 31, 0, 200, 0, 60)))
    rc = P.RECEIVER
    ok = (abs(bs[0] - rc["shoe_x"][0]) < 1e-6 and abs(sec[1] - (rc["shoe_y"] - rc["shoe_width"] / 2)) < 1e-6 and abs(sec[4] - (rc["shoe_y"] + rc["shoe_width"] / 2)) < 1e-6
          and abs(sec[2] - rc["shoe_z"][0]) < 1e-6 and abs(sec[5] - rc["shoe_z"][1]) < 1e-6)
    shoulder = bounds(sh.intersect(box(rc["x_stop"] - 0.5, rc["x_stop"] + 0.5, rc["shoe_y"] + 10, rc["shoe_y"] + 19, 0, 60)))
    ok &= abs(shoulder[0] - rc["x_stop"]) < 1e-6
    add("shoes match mechanical_interfaces.md (16 x 14 at y +-87.5, z 16..30, tip x 4.0, x-stop shoulder x 65.7, flat tip for HEAD_DOCK)", "pass" if ok else "fail",
        f"section y {sec[1]:.2f}..{sec[4]:.2f}, z {sec[2]:.2f}..{sec[5]:.2f}; tip x {bs[0]:.2f}, flat tip {tip[4] - tip[1]:.1f} x {tip[5] - tip[2]:.1f} after 3 mm chamfers; shoulder face x {shoulder[0]:.2f}, "
        f"{2 * H.SHOULDER_HY:.0f} x {H.SHOE_Z1 - H.SHOE_Z0:.0f} mm boss around the shoe; dock switch at {P.HEAD_DOCK_SWITCH} lies on the left shoe axis")
    kp = bounds(T.keeper())
    kx = (102.5 + 105.5) / 2
    lb = rc["latch_box"]
    ok = abs(kx - rc["latch_keeper"][0]) < 1e-6 and kp[5] <= P.HEAD_ENV_E_CEILING["z"][1] and kp[5] >= lb[4] and -15.0 <= lb[2] and 15.0 >= lb[3]
    add("latch keeper at (104, 0), hook inside the latch box, load path keeper -> hinge -> bridge -> T-heads -> x-stop shoulders (aluminium)", "pass" if ok else "fail",
        f"hook centre x {kx:.1f}, hook z 47.5..{kp[5]:.1f} (latch box z {lb[4]}..{lb[5]}), width 30 (latch box 24); no latch load in the lid or in a printed part")
    sw = {"rail_sw_front": (H.PIN_X, H.SHOE_Y, 37.3), "rail_sw_left": (H.XR + 3.6, H.SW_SIDE["y"], H.SW_SIDE["z"]), "rail_sw_right": (H.XR + 3.6, -H.SW_SIDE["y"], H.SW_SIDE["z"])}
    same = all(math.dist(sw[k], P.HEAD_RAIL_SWITCHES[k]) < 0.05 for k in sw)
    add("rail switch positions vs params.HEAD_RAIL_SWITCHES (layout placeholders)", "pass" if same else "deviation",
        f"designed {sw} vs placeholders {P.HEAD_RAIL_SWITCHES}: the placeholders lie inside the optical stack / on the split plane; frames.yaml needs the designed values", "design note")
    iso = {b: frame_isolation(builds[b]) for b in ("prototype", "production")}
    res["data"]["frame_to_receiver_gap_mm"] = {b: round(v[0], 3) for b, v in iso.items()}
    add("FRAME net isolated from the receiver metal in BOTH builds (R2801 fitted in both; J1 pin 2 the only DC ground path)",
        "pass" if all(v[0] >= 0.3 - 1e-6 for v in iso.values()) else "fail",
        "; ".join(f"{b}: smallest air gap {v[0]:.2f} mm near {v[1]}" for b, v in iso.items())
        + ". Barriers: 0.5 mm G10 isolators under the T-heads, 0.3 mm air round the T-heads in the pockets, insulating shoulder washers under the T-head screws, "
          "bridge 0.3 mm behind the frame, keeper 0.6 mm above the lid (+ 0.1 mm polyimide tape); production adds anodise on shoes and pockets (second barrier)")
    # 7 bed fit
    ok, rows, lim = bed_fit()
    for r_, c_ in zip(rows, printed_catalogue()):
        ov = overhangs(c_["shape"], c_["orient"])
        r_["downward_faces"] = len(ov)
        r_["downward_area_mm2"] = round(sum(o["area_mm2"] for o in ov), 0)
        r_["largest_downward_faces"] = ov[:4]
    add(f"every printed part fits the X1C in its print orientation ({lim[0]:.0f} x {lim[1]:.0f} x {lim[2]:.0f} usable after {BED_MARGIN:g} mm margins)", "pass" if ok else "fail", json.dumps(rows))
    res["data"]["printed_parts"] = rows
    # 8 split joint clears the windows
    edge = min(abs(y) - P.ACTIVE_Y / 2 for y in P.SEG_Y if abs(y) < 60)
    feat = H.TONGUE_H + 0.2
    add("split joint at y = 0 clears every window and every lane cavity", "pass" if edge - feat > 0 and H.RIB_W / 2 - feat > 1.0 else "fail",
        f"joint plane to nearest window edge {edge:.2f} mm, to the cavity wall {H.RIB_W / 2:.2f} mm; groove depth {feat:.1f} mm leaves {H.RIB_W / 2 - feat:.2f} mm of solid half rib")
    # 9 EMI bond pitch
    bp, clamp, bpts = bond_pitch(builds["prototype"])
    unclamped = [k for k, v in clamp.items() if v is None and T.standoff_on_foot(*map(float, k.split(",")))]
    add("EMI fence bond pitch to the spreader <= 50 mm (prototype; bond = screw or standoff clamping the foot, clamping tool-checked)",
        "pass" if max(bp.values()) <= 50.0 and not unclamped else "fail",
        f"largest gap front {bp['front']:.1f}, side {bp['side']:.1f}, rear {bp['rear']:.1f} mm (fence ends included); standoffs meant to clamp a foot but not on one: {unclamped or 'none'}; "
        f"standoffs in the chimney zones (on the spreader, not bond points): {[k for k, v in clamp.items() if v is None]}")
    res["data"]["bond_points"] = bpts
    n, dmax, pair = lid_pitch()
    pts = T.lid_loop()
    long_ = [(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts)) if math.dist(pts[k], pts[(k + 1) % len(pts)]) > H.LID_PITCH_MAX + 1e-6]
    in_bay = all(a[0] < 90 and b[0] < 90 and min(a[1], b[1]) >= -117.5 - 1e-6 and max(a[1], b[1]) <= -70.5 + 1e-6 for a, b in long_)
    seats = [bounds(T.lid_standoffs(True))[5], bounds(T.lid_standoffs(False))[5], bounds(T.lid_standoffs(True))[2]]
    boss_top = max(bounds(p.shape)[5] for p in builds["prototype"] if p.name.startswith("frame"))
    hard = all(abs(z - H.Z_LID0) < 1e-6 for z in seats[:2] + [boss_top])
    # gasket-compression loss in the long bay (calculated): lid 2 mm + bonded 1 mm blister as a simply supported strip under the gasket line load
    q, wb, span = 0.075 * 2.6, 20.0, dmax                      # 75 kPa closed-cell silicone at 33 % (UNVERIFIED) x 2.6 mm land; 20 mm effective width
    sag = 5 * q * span ** 4 / (384 * 69000.0 * wb * 2.0 ** 3 / 12)   # 2 mm lid only (no blister on the -y side)
    st_ = "pass" if not long_ and hard else ("deviation" if in_bay and hard else "fail")
    add(f"cover = shear panel: lid fasteners round a closed loop at <= {H.LID_PITCH_MAX:g} mm pitch, all on hard seats at the lid underside", st_,
        f"{n} M3 screws ({len(T.lid_holes())} into standoffs on the spreader, {len(T.lid_boss_xy())} into frame bosses); largest neighbour distance {dmax:.1f} mm between "
        f"({pair[0][0]:.1f}, {pair[0][1]:+.1f}) and ({pair[1][0]:.1f}, {pair[1][1]:+.1f}); standoff tops z {seats[0]:.2f} / {seats[1]:.2f}, boss tops z {boss_top:.2f}. "
        + (f"Only span over 40 mm: the -y rear line between (77.5, -70.5) and (77.5, -117.5), forced by CR-M08 (J2501 GH-8 plug keep-out y -106.6..-92.0, the J2 port at "
           f"y -87.5 with its wires, T-head screw washers at y -77.5 / -97.5 / -111.5); calculated gasket-line sag over the span {sag:.3f} mm against 0.4 mm gasket compression. "
           "The +y J1 bay is back to <= 40 mm (standoff (77.5, +90.3), stage 3)" if long_ else ""))
    jk = [p for p in builds["prototype"] if p.name.startswith("jacket")]
    lb_ = P.RECEIVER["latch_box"]
    latch = box(lb_[0], lb_[1], lb_[2], lb_[3], lb_[4], lb_[5])
    zj = max(bounds(p.shape)[5] for p in jk)
    vl = sum(volume(p.shape.intersect(latch)) for p in jk)
    add("insulating jacket (RR-HD-S-131/132, standard cold configuration) inside z <= 50, clear of the latch box, rails and receiver",
        "pass" if zj <= P.HEAD_ENV_E_CEILING["z"][1] + 1e-6 and vl < 1e-6 else "fail",
        f"jacket top z {zj:.1f}; volume in the latch box {vl:.2f} mm3; clearance to rails (rest and full stroke, 3 / 5 mm), shoes, bridge, keeper and screw heads "
        "covered by the interference checks above (jacket parts are in the deck group)")
    ok, rows = drain_check([p.shape for p in builds["prototype"] if p.name.startswith("frame")])
    ok2, rows2 = drain_check([p.shape for p in builds["production"] if p.name == "frame"])
    add("light-safe chimney drains: passage open, no straight line of sight (both builds)", "pass" if ok and ok2 else "fail", json.dumps(rows + rows2))
    covers = [Part(f"transport_cover_{t}", "-x", T.transport_cover(s_), "PETG-CF") for s_, t in ((1, "L"), (-1, "R"))]
    sub = [p for p in builds["prototype"] if p.group in ("frame", "receiver", "window", "rail", "fastener", "switch", "cable")]
    r = interference(sub + covers, "transport cover", only_between={"transport_cover_L", "transport_cover_R"})
    add("transport covers clip on without touching the films or any part except their seats", "pass" if not r["overlaps"] else "fail",
        f"{r['pairs_tested']} pairs; overlaps: {r['overlaps'] or 'none'}; cover rests touch the cassette borders only (z {H.CAS_Z0 - 0.3:.1f} vs film z {H.FILM_Z:g})")
    slots = {"chimney notch": 2 * H.CHIM_HY, "J1 boot slot": max(H.BOOT_SLOTS["J1"][1] - H.BOOT_SLOTS["J1"][0], H.BOOT_SLOTS["J1"][3] - H.BOOT_SLOTS["J1"][2]),
             "J2 boot slot": H.BOOT_SLOTS["J2"][3] - H.BOOT_SLOTS["J2"][2], "J2 rear-flange notch": H.J2_FLANGE_NOTCH_Y[1] - H.J2_FLANGE_NOTCH_Y[0],
             "switch saddle window in the front fence foot": 27.0}
    add("shield openings: no slot longer than 20 mm except the cable entries", "deviation" if slots["switch saddle window in the front fence foot"] > 20 else "pass",
        f"{slots}; the 27 mm openings are in the fence FOOT (flat on the spreader, closed by it), not in the wall: electrically closed", "design note")
    # 10 masses
    masses = {}
    for b, parts in builds.items():
        m, cg = mass_cg(parts)
        nopig = [p for p in parts if not p.name.startswith(("pigtail", "plug"))]
        m2, cg2 = mass_cg(nopig)
        masses[b] = m
        res["data"][f"mass_{b}"] = {"mass_g": round(m, 1), "cg_mm": [round(c, 2) for c in cg], "mass_without_pigtails_g": round(m2, 1), "cg_without_pigtails_mm": [round(c, 2) for c in cg2],
                                    "largest_items_g": {p.name: round(p.mass(), 1) for p in sorted(parts, key=lambda q: -q.mass())[:12]}}
    md, cgd = mass_cg(dummy)
    dcg = [cgd[i] - cg_proto[i] for i in range(3)]
    ok = abs(md - m_proto) <= 10 and abs(dcg[0]) <= 3 and abs(dcg[1]) <= 3 and abs(dcg[2]) <= 5
    add("dummy head mass and CG representative of the prototype head (+-10 g, +-3 mm x/y, +-5 mm z)", "pass" if ok else "fail",
        f"dummy {md:.0f} g vs {m_proto:.0f} g; CG offset {dcg[0]:+.1f} / {dcg[1]:+.1f} / {dcg[2]:+.1f} mm; steel ballast {t_ballast:.2f} mm per lane", "calculated from model volumes x handbook densities")
    res["data"]["dummy_ballast_mm"] = round(t_ballast, 2)
    add("head mass vs the 1.67 kg (prototype) / 2.10 kg (production) used in mech_calcs.md", "deviation" if masses["prototype"] > 1700 else "pass",
        f"prototype {masses['prototype']:.0f} g, production {masses['production']:.0f} g (model volumes, OEM modules assumed 102 g per lane)", "calculated")
    # 11 calculations
    st = C.structure(masses)
    res["data"]["structure"] = st
    worst = max(v["lid fitted (all screws)"]["total"] for v in st.values())
    add("20 N at the front outer window corner: deflection target < 0.5 mm with the lid fitted", "pass" if worst < 0.5 else "fail",
        "; ".join(f"{k}: {v['lid fitted (all screws)']['total']:.2f} mm (lid off {v['lid removed (service state)']['total']:.2f}), f1 {v['f1_hz']:.0f} Hz" for k, v in st.items()), "calculated")
    rl = C.rails()
    res["data"]["rails"] = rl
    f = rl["front"]
    ok = f["trip_travel_mm"]["max (unshimmed, PT max)"] <= H.RAIL_TRIP_MAX and f["post_trip_stroke_mm"] >= 15.0 and f["plunger_depression_at_stop_mm"] <= f["plunger_travel_available_mm"] and f["spring_force_N"]["solid length ok"]
    add("leading rail: pre-travel <= 2 mm, post-trip stroke >= 15 mm, switch not over-travelled", "pass" if ok else "fail",
        f"trip at {f['trip_travel_mm']['nominal']:.2f} mm nominal ({f['trip_travel_mm']['max (unshimmed, PT max)']:.2f} max), stroke after trip {f['post_trip_stroke_mm']:.1f} mm, "
        f"plunger {f['plunger_depression_at_stop_mm']:.1f} of {f['plunger_travel_available_mm']:.1f} mm, return force {f['spring_force_N']['rest (both)']:.1f}..{f['spring_force_N']['full stroke (both)']:.1f} N", "calculated (switch data PARTIAL)")
    s = rl["side"]
    ok = s["trip_lateral_mm"]["max"] <= 2.0 and s["margin_trip_before_stop_mm"] > 0.1 and s["plunger_depression_at_stop_mm"] <= s["plunger_travel_available_mm"]
    add("side zones: pre-travel <= 2 mm, trip before the positive stop, switch not over-travelled", "pass" if ok else "fail",
        f"trip at {s['trip_lateral_mm']['nominal']:.2f} mm lateral nominal ({s['trip_lateral_mm']['max']:.2f} max), stop at {s['travel_to_stop_lateral_mm']:.2f} mm, margin {s['margin_trip_before_stop_mm']:.2f} mm", "calculated (switch data PARTIAL)")
    tol = C.tolerance_stack()
    res["data"]["tolerance_stack"] = tol
    add("head contribution to the film-to-floor gap (datum C to film plane)", "pass" if abs(tol["nominal_film_z"] - P.FILM_Z) < 1e-9 and tol["production"]["worst_case_pm_mm"] <= 0.30 else "fail",
        f"nominal film z {tol['nominal_film_z']:.2f}; prototype +-{tol['prototype']['worst_case_pm_mm']:.2f} worst / +-{tol['prototype']['rss_pm_mm']:.2f} RSS; production +-{tol['production']['worst_case_pm_mm']:.2f} / "
        f"+-{tol['production']['rss_pm_mm']:.2f} (budget line +-0.30: prototype meets it by RSS only -> trim with the isolator shim at the standoff-height check)", "calculated")
    res["data"]["harness_routes"] = C.harness_routes(board_asbuilt()[0])
    res["data"]["light_paths"] = C.light_paths()
    no_los = all(r["turns"] > 0 or "gasket" in r["barriers"] or "solid" in r["barriers"] or "film" in r["barriers"] or "elastomer" in r["barriers"] for r in res["data"]["light_paths"])
    add("light-path analysis: every joint has a labyrinth turn or an opaque compressed barrier (no open line of sight)", "pass" if no_los else "fail",
        f"{len(res['data']['light_paths'])} joints tabulated in head_report.md; joints that rely on a gasket only: " + ", ".join(r["id"] for r in res["data"]["light_paths"] if r["turns"] == 0 and "solid" not in r["barriers"]), "analysis of the model geometry (not a light test)")
    th = C.thermal(builds)
    res["data"]["thermal"] = th
    base = [c for c in th["cases"] if c["set_point_c"] == C.T_SET_C and c["jacket"] and c["h_ext_w_m2k"] == 12.0 and c["receiver_boundary"].startswith("body")]
    sens = [c for c in th["cases"] if c["set_point_c"] == C.T_SET_C and c["jacket"] and c["h_ext_w_m2k"] == 25.0 and c["receiver_boundary"].startswith("body")]
    worst = max(c["heater_power_w"] for c in base)
    add(f"heater demand within the fitted heater: baseline (+{C.T_SET_C:g} C at the SiPM carrier, -20 / -25 C, still air 12 W/m2K, jacket, 1.2 W electronics) <= {C.HEATER_FILMS_W:g} W at 12 V",
        "pass" if worst <= C.HEATER_FILMS_W else "fail",
        "; ".join(f"{c['build']} {c['ambient_c']:g} C: {c['heater_power_w']:.1f} W" for c in base)
        + f". Sensitivity 25 W/m2K: " + "; ".join(f"{c['build']} {c['ambient_c']:g} C {c['heater_power_w']:.1f} W" for c in sens)
        + f" (> 30 W at -25 C: {[c['build'] for c in sens if c['heater_power_w'] > C.HEATER_FILMS_W] or 'none'}). At 10 V the films give {C.HEATER_AT_10V_W:g} W; "
        f"branch limit 4.0 A x 12 V = 48 W (the films, not the branch, limit). Cut-out opens {C.CUTOUT_OPEN_C:g} C (UNVERIFIED): stuck-on heater at 15 V in +20 C "
        f"would settle at {th['warmup_from_-25c_soak']['prototype']['steady_c_heater_stuck_on_15v_at_+20c']:.0f} C without it", "calculated")
    summary = {"generated_by": "mechanical/head/checks.py (calc.thermal)", "evidence": "calculated (lumped steady state; nothing measured)", "issue": "IB-39",
               "assumptions": th["_assumptions"], "installed": {"heater_films_w_at_12v": C.HEATER_FILMS_W, "heater_w_at_10v": C.HEATER_AT_10V_W,
                                                             "branch_limit_a": P.POWER_C["rails"]["HEAD_HTR"]["limit_a"], "heater_peak_at_12v_contract_w": P.POWER_C["head_allocation_w"]["heater_peak_at_12v"],
                                                             "cutout_open_c": C.CUTOUT_OPEN_C},
               "cases": [{k: c[k] for k in ("build", "ambient_c", "set_point_c", "h_ext_w_m2k", "jacket", "receiver_boundary", "electronics_credit_w", "ua_w_per_k", "heater_power_w")}
                         for c in th["cases"]],
               "baseline_w": {f"{c['build']}_{c['ambient_c']:g}C": c["heater_power_w"] for c in base},
               "thermal_mass_j_per_k": th.get("thermal_mass_j_per_k"), "warmup_from_-25c_soak": th.get("warmup_from_-25c_soak")}
    (OUT / "thermal_summary.json").write_text(json.dumps(summary, indent=1))
    res["data"]["oem_dependent"] = [dict(zip(("oem_quantity", "head_dimension", "adjustment"), r)) for r in C.OEM_DEPENDENT]
    res["data"]["bond_pitch_mm"] = bp
    res["summary"] = {s_: sum(1 for c in res["checks"] if c["status"] == s_) for s_ in ("pass", "fail", "deviation")}
    res["runtime_s"] = round(time.time() - t0, 1)
    OUT.mkdir(exist_ok=True)
    (OUT / "checks.json").write_text(json.dumps(res, indent=1, default=str))
    from . import report
    report.write(res)
    print(f"== checks: {res['summary']} in {res['runtime_s']} s")
    return res


if __name__ == "__main__":
    r = run()
    sys.exit(1 if r["summary"]["fail"] else 0)
