"""Fit checks added after the independent CAD / PCB / harness review (docs/reviews/REVIEW_cad_pcb_harness_fit.md):

* fastener_access   every modelled fastener's tool column against the parts present at the step that fits it (assembly
                    sequence of docs.STEPS), and in its service state where it has one (tool-checked);
* service_sweeps    real solids swept along their removal paths: RR-CHS-MAIN (plugs unplugged, stated parts removed), each board
                    plug along its pull direction plus a gloved-finger zone, the CM5 carrier, every ToF carrier (clip screws reachable
                    and carrier withdrawn) in the stated service states (tool-checked);
* the fastener solids and the board / plug / wire-exit solids themselves are in the normal interference check (assembly.py).
"""
from __future__ import annotations

import fnmatch
import time

from mechanical.common import params as P

from . import dims as D
from .interference import overlaps
from .util import CACHE, Part, box, compound, cyl, frame, to_frame

STAGE_EXTRA = {"02_lower_hull": ["lower_hull"], "07_lid": ["upper_shell"]}      # production one-piece skins
NOT_PRESENT = ("tray", "head_placeholder", "fastener", "cassette_option")


def stage_index():
    from .docs import STEPS
    keys = [s[0] for s in STEPS]
    pats = [(s[0], list(s[2]) + STAGE_EXTRA.get(s[0], [])) for s in STEPS]
    return keys, pats


def stage_of(name, pats):
    for i, (k, ps) in enumerate(pats):
        if any(fnmatch.fnmatch(name, p) for p in ps):
            return i
    return None


def _robot(parts):
    return [p for p in parts if p.group not in NOT_PRESENT and p.hard]


def _blocked(probes, present, tag, log, vol_tol=1.0):
    """probes: list of Parts.  Returns {probe name: [(part, mm3)]} for overlaps above vol_tol."""
    if not probes:
        return {}
    rows = overlaps(probes + present, CACHE.parent / "_interference", log=lambda *a: None)
    pn = {p.name for p in probes}
    out = {p.name: [] for p in probes}
    for a, b, v, method, dt in rows:
        if (a in pn) == (b in pn):
            continue
        if v > vol_tol:
            pr, other = (a, b) if a in pn else (b, a)
            out[pr].append((other, round(v, 1)))
    return out


def fastener_access(parts, F, log=print):
    t0 = time.time()
    keys, pats = stage_index()
    rob = _robot(parts)
    st = {p.name: stage_of(p.name, pats) for p in rob}
    res, fails = [], []
    groups = {}
    for f in F:
        if f.step is not None:
            groups.setdefault((f.step, f.later), []).append(f)
    for (step, later), fs in groups.items():
        k = keys.index(step)
        present = [p for p in rob if st[p.name] is not None and st[p.name] <= k and not any(fnmatch.fnmatch(p.name, q) for q in later)]
        probes = [Part("TOOL", f"tool_{f.fid}", f.tool(), "purchased", "-", "tool") for f in fs]
        blk = _blocked(probes, present, step, log)
        for f in fs:
            b = blk.get(f"tool_{f.fid}", [])
            res.append({"fastener": f.fid, "size": f"{f.size} {f.kind} x {f.length:g}", "step": step, "tool": f"{f.tool_name}, column dia {f.tool_d:.1f} x {f.tool_len:.0f}",
                        "blocked_by": b, "note": f.note})
            if b:
                fails.append(f.fid)
    svc = {}
    for f in F:
        if f.service:
            svc.setdefault(f.service, []).append(f)
    for state, fs in svc.items():
        removed = SERVICE_STATES.get(state, ())
        present = [p for p in rob if not any(fnmatch.fnmatch(p.name, r) for r in removed)]
        probes = [Part("TOOL", f"tool_{f.fid}", f.tool(), "purchased", "-", "tool") for f in fs]
        blk = _blocked(probes, present, state, log)
        for f in fs:
            b = blk.get(f"tool_{f.fid}", [])
            res.append({"fastener": f.fid, "size": f"{f.size} {f.kind} x {f.length:g}", "step": f"SERVICE: {state}", "tool": f"{f.tool_name}, column dia {f.tool_d:.1f} x {f.tool_len:.0f}",
                        "blocked_by": b, "removed": list(removed), "note": f.note})
            if b:
                fails.append(f"{f.fid} ({state})")
    log(f"  fastener access: {len(F)} fasteners, {len(res)} tool columns, {len(fails)} blocked, {time.time() - t0:.0f} s")
    return {"rows": res, "blocked": fails, "ok": not fails, "count": len(F)}


LID_PIECES = ("shoulder_*", "rear_deck_*", "upper_shell")
GRIP_TOP = ("saddle_cover", "grip_bar", "grip_sleeve", "grip_screw_*", "cheek_fairing_*", "rrtof_look_fwd_*", "tof_clip_look_fwd_*", "tof_window_look_fwd_*", "fx_cover_*")
SERVICE_STATES = {
    "receiver re-torque (robot on its back, head removed)": (),
    "cover (routine)": (),
    "board service (lid off)": GRIP_TOP + LID_PIECES + ("nose_cowl", "J?_receptacle", "J?_mated_plug", "*_operator", "*_body", "RR-PANEL_*", "panel_tray", "lidar", "charge_inlet", "inlet_cover", "rrtof_look_rev_*", "rrtof_prox_*",
                                                       "tof_clip_look_rev_*", "tof_clip_prox_*", "tof_window_*", "bumper_sw_*", "fx_perim_*", "RR-CHS-MAIN_plug_*", "CM5_plug_*", "battery_hump"),
    "routine (saddle cover off, head removed)": ("saddle_cover", "fx_cover_*"),
}


def _sweep_boxes(part_names, parts, dz=None, vec=None, dist=150.0):
    """Swept envelope of real solids moved along vec by dist: each solid's bounding box extended along the path (conservative)."""
    out = []
    for p in parts:
        if p.name not in part_names:
            continue
        for s in (p.shape.Solids() or [p.shape]):
            b = s.BoundingBox()
            x0, x1, y0, y1, z0, z1 = b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax
            v = vec or (0, 0, 1)
            x0, x1 = min(x0, x0 + v[0] * dist), max(x1, x1 + v[0] * dist)
            y0, y1 = min(y0, y0 + v[1] * dist), max(y1, y1 + v[1] * dist)
            z0, z1 = min(z0, z0 + v[2] * dist), max(z1, z1 + v[2] * dist)
            out.append(box(x0 + 0.05, x1 - 0.05, y0 + 0.05, y1 - 0.05, z0 + 0.05, z1 - 0.05))
    return compound(out) if out else None


def service_sweeps(parts, log=print):
    t0 = time.time()
    from . import boards_body as BB
    rob = _robot(parts)
    byn = {p.name: p for p in parts}
    out = {}

    def run(label, sweep, removed, also_skip=()):
        present = [p for p in rob if not any(fnmatch.fnmatch(p.name, r) for r in tuple(removed) + tuple(also_skip))]
        b = _blocked([Part("SWEEP", f"sweep_{len(out)}", sweep, "purchased", "-", "tool")], present, label, log)
        out[label] = {"removed": list(removed), "blocked_by": next(iter(b.values()))}

    lid_off = SERVICE_STATES["board service (lid off)"]
    brd = [n for n in byn if n.startswith("RR-CHS-MAIN_") and "plug" not in n]
    run("RR-CHS-MAIN lifted 150 mm (+z) after unplugging all plugs, lid off", _sweep_boxes(brd, parts), lid_off, also_skip=brd + ["fx_board_*"])
    cm5 = [n for n in byn if n.startswith("CM5_carrier")]
    run("CM5 carrier lifted 150 mm (+z), lid off, plugs out", _sweep_boxes(cm5, parts), lid_off, also_skip=cm5 + ["cm5_tray"])
    # every board plug pulled out of engagement along its mating direction; RR-CHS-MAIN / CM5 plugs also need a gloved-finger zone
    # over the plug footprint (30 mm).  State: lid off for the main board and the CM5 carrier; cover off for lid-mounted boards
    # (their plugs are mated on the bench before the lid goes on, so only the pull path is checked in place).
    ENG = {"JST GH": 4.0, "Molex CLIK-Mate": 5.0, "Molex Micro-Fit 3.0": 6.0, "Molex Mini-Fit Jr": 8.0}
    for (board, ref, tag), port in BB.PORTS.items():
        pn = f"{tag}_plug_{ref}" if board != "CM5" else f"CM5_plug_{ref}"
        if pn not in byn:
            continue
        pl = byn[pn]
        d = port["dir"]
        plug_only = pl.shape.Solids()[0] if pl.shape.Solids() else pl.shape
        bb = plug_only.BoundingBox()
        dist = ENG.get(port["family"], 8.0)
        sw = compound([plug_only.translate(tuple(c * dist * k / 4 for c in d)) for k in range(1, 5)])      # oriented: the plug itself, moved out of engagement
        main = board in ("RR-CHS-MAIN", "CM5")
        if main and abs(d[2]) < 0.5:
            sw = compound([sw, box(bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmax + 0.1, bb.zmax + 30.0)])
        state = lid_off if main else SERVICE_STATES["routine (saddle cover off, head removed)"]
        own = [pn, f"{tag}_*"] if board != "CM5" else [pn, "CM5_*"]
        run(f"plug {tag}.{ref} pull{' + finger zone' if main and abs(d[2]) < 0.5 else ''}", sw, state, also_skip=own)
    # ToF carriers: withdrawn 25 mm along -boresight from the seat in the routine state (inside access through the cover only)
    tof = {}
    for name, t in P.TOF_SENSORS.items():
        tag = "rr" + name
        names = [n for n in byn if n.startswith(tag + "_")]
        d = tuple(-c for c in t["dir"])
        sw = _sweep_boxes(names, parts, vec=d, dist=25.0)
        state = SERVICE_STATES["routine (saddle cover off, head removed)"]
        present = [p for p in rob if not any(fnmatch.fnmatch(p.name, r) for r in tuple(state) + tuple(names) + (f"tof_clip_{name[4:]}", f"tof_window_{name[4:]}"))]
        b = _blocked([Part("SWEEP", f"sweep_tof_{name}", sw, "purchased", "-", "tool")], present, name, log)
        tof[name] = next(iter(b.values()))
    out["tof_withdrawal_in_place"] = tof
    log(f"  service sweeps: {len(out)} sweeps, {time.time() - t0:.0f} s")
    hard = [k for k, v in out.items() if k != "tof_withdrawal_in_place" and v["blocked_by"]]
    return {"sweeps": out, "blocked": hard, "ok": not hard}


# ----------------------------------------------------------------------------------------------- RR-CHS-MAIN service pads, bottom zone
SVC_BOX_UV = (126.0, 140.0, 75.0, 84.0)     # SVC1..SVC10 test-pad array (stage 5), probe access zone to 40 mm above the board
SVC_H = 40.0


def svc_access(parts, routes):
    """Probe access to the SVC1..SVC10 array with the cover off, the board fitted and every cable on its route (tool-checked)."""
    from mechanical.common import boards as BD
    from .boards_body import _xf_chs, _box_uv
    import math
    u0, u1, v0, v1 = SVC_BOX_UV
    probe = _box_uv((u0, u1, v0, v1, 0.05, SVC_H), _xf_chs)
    b = probe.BoundingBox()
    bd = BD.load("RR-CHS-MAIN")["parts"]
    pads = sorted(r for r, q in bd.items() if ("TestPoint" in q["fp"] or r.startswith("SVC")) and u0 <= q["uv"][0] <= u1 and v0 <= q["uv"][1] <= v1)
    state = SERVICE_STATES["routine (saddle cover off, head removed)"]
    present = [p for p in _robot(parts) if not any(fnmatch.fnmatch(p.name, r) for r in state) and not p.name.startswith("RR-CHS-MAIN_")]
    comps = [(r, q["height"]) for r, q in bd.items() if q["box_uv"] and q["height"] and q["box_uv"][0] < u1 and q["box_uv"][2] > u0 and q["box_uv"][1] < v1 and q["box_uv"][3] > v0
             and r not in pads]
    blk = _blocked([Part("SWEEP", "svc_probe", probe, "purchased", "-", "tool")], present, "svc", print, vol_tol=0.5)
    inside = lambda q: b.xmin <= q[0] <= b.xmax and b.ymin <= q[1] <= b.ymax and b.zmin <= q[2] <= b.zmax
    route_hits, clip_hits = [], []
    for cid, r in routes.items():
        pts = r.get("polyline") or []
        for a, c in zip(pts, pts[1:]):
            n = max(2, int(math.dist(a, c) / 1.0))
            if any(inside([a[i] + (c[i] - a[i]) * k / n for i in range(3)]) for k in range(n + 1)):
                route_hits.append(cid)
                break
        clip_hits += [cid for cl in r.get("clips", []) if inside(cl["at"])]
    parts_hit = next(iter(blk.values()))
    return {"pads_in_board_file": pads, "board_components_in_zone (info)": comps, "zone_base_link": [round(v, 1) for v in (b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax)],
            "parts_in_zone": parts_hit, "routes_over_zone": route_hits, "clips_over_zone": clip_hits,
            "ok": bool(pads) and not parts_hit and not route_hits and not clip_hits}


def board_bottom_zone(parts):
    """Bottom-side parts of RR-CHS-MAIN: height against the 3.0 mm zone and footprint over a bridge-tray feature (tool-checked)."""
    from mechanical.common import boards as BD
    from .boards_body import _xf_chs
    b = BD.load("RR-CHS-MAIN")
    feats = []
    flush = [(f"flush countersunk tray screw at post {i} (no protrusion, info)", x, y, D.CSK["M3"] / 2 + 0.5) for i, (x, y) in enumerate(D.POSTS)]
    for h in [h for h in b["holes"] if h.get("mounting") and h["ref"].startswith("H")]:
        x, y, _ = _xf_chs(h["uv"][0], h["uv"][1], 0.0)
        feats.append((f"clinch standoff {h['ref']}", x, y, D.CLINCH_SO["od"] / 2 + 0.5))
    ex0 = P.ELECTRONICS_BRIDGE_X[0]
    out, over, info = [], [], []
    for ref, side, bx in BD.components("RR-CHS-MAIN"):
        if side != "B":
            continue
        h = -bx[4] - b["thickness"]
        pts = [_xf_chs(u, v, 0) for u in (bx[0], bx[1]) for v in (bx[2], bx[3])]
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        out.append((ref, round(h, 2)))
        for name, fx, fy, r in feats:
            if x0 - r <= fx <= x1 + r and y0 - r <= fy <= y1 + r:
                over.append((ref, name))
        for name, fx, fy, r in flush:
            if x0 - r <= fx <= x1 + r and y0 - r <= fy <= y1 + r:
                info.append((ref, name))
        for yy in (-60.0, 60.0):
            if x0 <= ex0 + 30 and x1 >= ex0 + 14 and y0 <= yy + 6 and y1 >= yy - 6:
                info.append((ref, f"over the tray pass-through at y {yy:+.0f} (hole: no contact, info)"))
    too_tall = [r for r in out if r[1] > 3.0]
    return {"bottom_parts": len(out), "max_height_mm": max((r[1] for r in out), default=0.0), "over_3mm": too_tall, "over_tray_features": over, "over_pass_throughs_info": info,
            "ok": not too_tall and not over, "source": b["source"]}


def receptacle_depth(parts, margin=5.0):
    """J1 / J2 receptacle bodies with their UNVERIFIED depth behind the panel + 5 mm against every other part (tool-checked)."""
    from mechanical.common.purchased import library as L
    out = {}
    for jn, key in (("J1", "j1_receptacle"), ("J2", "j2_receptacle")):
        j, e = P.J_RECEPTACLES[jn], L.env(key)
        probe = place_cyl((e["flange_d"] - 4.0) / 2, e["depth_behind_panel"] + margin, j["xyz"], j["normal"])
        present = [p for p in _robot(parts) if p.name not in (f"{jn}_receptacle", f"{jn}_mated_plug") and not p.name.startswith(("nose_cowl", "upper_shell"))]
        b = _blocked([Part("SWEEP", f"depth_{jn}", probe, "purchased", "-", "tool")], present, jn, print, vol_tol=0.5)
        out[jn] = {"depth_mm": e["depth_behind_panel"], "margin_mm": margin, "blocked_by": next(iter(b.values()))}
    return {"rows": out, "ok": all(not v["blocked_by"] for v in out.values())}


def place_cyl(r, depth, xyz, n):
    from .util import place
    return place(cyl(r, depth, (0, 0, -depth - 0.5)), xyz, n)
