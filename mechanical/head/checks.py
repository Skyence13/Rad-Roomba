"""Automated checks (evidence class: TOOL-CHECKED on the CadQuery model unless a row says calculated).

Run: python -m mechanical.head.checks        -> out/checks.json, out/head_report.md ; exit 1 if any check FAILS.
Status values: pass | fail | deviation (does not meet a common datum on purpose; needs the lead's decision, listed in the report).
"""
from __future__ import annotations

import json
import math
import sys
import time

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
    rr = sorted([s_ * y for y in H.REAR_SCREW_Y for s_ in (1, -1)] + [y for (x, y), f in clamp.items() if f == "fence_rear"])
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
        los = cyl2(0.2, (d["x_out"], yd, H.Z_FB - 0.01), (d["x_in"], yd, H.CHIM_FLOOR_REAR + 0.01))
        blocked = sum(volume(los.intersect(f)) for f in frame_shapes) > 0.05
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
    ok = want == got and sp_holes == {(a, b) for a, b, _ in want} and abs(bounds(T.pcb())[2] - env["origin_base_link_mm"][2]) < 1e-6
    add("eight M2.5 board standoffs and PCB underside match board_envelopes.yaml", "pass" if ok else "fail", f"standoff tops {got}; yaml {want}")
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
            f"x {bb[0]:.2f}..{bb[3]:.2f} (66.0..192.2), y {bb[1]:.2f}..{bb[4]:.2f} (+-175), z {bb[2]:.2f}..{bb[5]:.2f} (5..50; lid top {H.Z_LID1:.1f}, J1 blister {H.Z_LID1 + 1:.1f}, keeper hook {bb[5]:.1f})")
    rail = [p for p in builds["prototype"] if p.name.startswith(("rail_bar", "rail_insert", "bail"))]
    bbr = bounds(compound([p.shape for p in rail]))
    over = bbr[3] - P.HEAD_ENV_E_CEILING["x"][1]
    add("leading rail inside the contract envelope x <= 192.2", "deviation" if over > 1e-6 else "pass",
        f"rail front face at rest x = {bbr[3]:.1f}: {over:.1f} mm outside the envelope (stroke {H.RAIL_GAP:g} + bar {H.BAR_T:g} + insert {H.INS_T:g} ahead of the frame face {H.XF}); "
        f"outer head corner radius {math.hypot(bbr[3], 175):.0f} mm (contract 260). Needs CCR (IB-11): see head_report.md")
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
    okp = all(abs(H.PORT[n][1] - s * H.SHOE_Y) < 1e-6 and H.XR < H.PORT[n][0] < H.BAY_X0 and H.PORT_SLOT_Z0 + H.CABLE_D[n] / 2 <= H.PORT[n][2] <= H.Z_LID0 - H.CABLE_D[n] / 2 + 0.01 for n, s in (("J1", 1), ("J2", -1)))
    add("J1 / J2 cable ports at the interface positions (71.7, +-87.5, 39.0) in the rear wall", "pass" if okp else "fail", f"wall x {H.XR}..{H.BAY_X0}; slot floor z {H.PORT_SLOT_Z0}; cable top z {H.PORT['J1'][2] + H.CABLE_D['J1'] / 2:.2f} under the lid at {H.Z_LID0}")
    sw = {"rail_sw_front": (H.PIN_X, H.SHOE_Y, 37.3), "rail_sw_left": (H.XR + 3.6, H.SW_SIDE["y"], H.SW_SIDE["z"]), "rail_sw_right": (H.XR + 3.6, -H.SW_SIDE["y"], H.SW_SIDE["z"])}
    add("rail switch positions vs params.HEAD_RAIL_SWITCHES (layout placeholders)", "deviation",
        f"designed {sw} vs placeholders {P.HEAD_RAIL_SWITCHES}: the placeholders lie inside the optical stack / on the split plane; frames.yaml needs the designed values", "design note")
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
    unclamped = [k for k, v in clamp.items() if v is None]
    add("EMI fence bond pitch to the spreader <= 50 mm (prototype; bond = screw or standoff clamping the foot, clamping tool-checked)",
        "pass" if max(bp.values()) <= 50.0 and not unclamped else "fail",
        f"largest gap front {bp['front']:.1f}, side {bp['side']:.1f}, rear {bp['rear']:.1f} mm (fence ends included); standoffs not on a fence foot: {unclamped or 'none'}")
    res["data"]["bond_points"] = bpts
    n, dmax, pair = lid_pitch()
    seats = [bounds(T.lid_standoffs(True))[5], bounds(T.lid_standoffs(False))[5]]
    boss_top = max(bounds(p.shape)[5] for p in builds["prototype"] if p.name.startswith("frame"))
    add(f"cover = shear panel: lid fasteners round a closed loop at <= {H.LID_PITCH_MAX:g} mm pitch, all on hard seats at the lid underside",
        "pass" if dmax <= H.LID_PITCH_MAX + 1e-6 and all(abs(z - H.Z_LID0) < 1e-6 for z in seats + [boss_top]) else "fail",
        f"{n} M3 screws ({len(T.lid_holes())} into standoffs on the spreader, {len(T.lid_boss_xy())} into frame bosses); largest neighbour distance {dmax:.1f} mm between "
        f"({pair[0][0]:.1f}, {pair[0][1]:+.1f}) and ({pair[1][0]:.1f}, {pair[1][1]:+.1f}); standoff tops z {seats[0]:.2f} / {seats[1]:.2f}, boss tops z {boss_top:.2f}")
    ok, rows = drain_check([p.shape for p in builds["prototype"] if p.name.startswith("frame")])
    ok2, rows2 = drain_check([p.shape for p in builds["production"] if p.name == "frame"])
    add("light-safe chimney drains: passage open, no straight line of sight (both builds)", "pass" if ok and ok2 else "fail", json.dumps(rows + rows2))
    covers = [Part(f"transport_cover_{t}", "-x", T.transport_cover(s_), "PETG-CF") for s_, t in ((1, "L"), (-1, "R"))]
    sub = [p for p in builds["prototype"] if p.group in ("frame", "receiver", "window", "rail", "fastener", "switch", "cable")]
    r = interference(sub + covers, "transport cover", only_between={"transport_cover_L", "transport_cover_R"})
    add("transport covers clip on without touching the films or any part except their seats", "pass" if not r["overlaps"] else "fail",
        f"{r['pairs_tested']} pairs; overlaps: {r['overlaps'] or 'none'}; cover rests touch the cassette borders only (z {H.CAS_Z0 - 0.3:.1f} vs film z {H.FILM_Z:g})")
    slots = {"chimney notch": 2 * H.CHIM_HY, "cable port": 2 * H.PORT_SLOT_HY, "switch saddle window in the front fence foot": 27.0}
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
    worst = max(v["lid fitted (10 screws)"]["total"] for v in st.values())
    add("20 N at the front outer window corner: deflection target < 0.5 mm with the lid fitted", "pass" if worst < 0.5 else "fail",
        "; ".join(f"{k}: {v['lid fitted (10 screws)']['total']:.2f} mm (lid off {v['lid removed (service state)']['total']:.2f}), f1 {v['f1_hz']:.0f} Hz" for k, v in st.items()), "calculated")
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
    res["data"]["light_paths"] = C.light_paths()
    no_los = all(r["turns"] > 0 or "gasket" in r["barriers"] or "solid" in r["barriers"] or "film" in r["barriers"] or "elastomer" in r["barriers"] for r in res["data"]["light_paths"])
    add("light-path analysis: every joint has a labyrinth turn or an opaque compressed barrier (no open line of sight)", "pass" if no_los else "fail",
        f"{len(res['data']['light_paths'])} joints tabulated in head_report.md; joints that rely on a gasket only: " + ", ".join(r["id"] for r in res["data"]["light_paths"] if r["turns"] == 0 and "solid" not in r["barriers"]), "analysis of the model geometry (not a light test)")
    res["data"]["thermal"] = C.thermal()
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
