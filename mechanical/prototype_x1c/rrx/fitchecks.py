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
    by_step = {}
    for f in F:
        if f.step is not None:
            by_step.setdefault(f.step, []).append(f)
    for step, fs in by_step.items():
        k = keys.index(step)
        present = [p for p in rob if st[p.name] is not None and st[p.name] <= k]
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
    "board service (lid off)": GRIP_TOP + LID_PIECES + ("*_operator", "*_body", "RR-PANEL_*", "panel_tray", "lidar", "charge_inlet", "inlet_cover", "rrtof_look_rev_*", "rrtof_prox_*",
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
    # every board plug pulled along its mating direction (+ 10 mm) with a 20 x 20 x 30 mm gloved-finger zone over it
    for (board, ref, tag), port in BB.PORTS.items():
        pn = f"{tag}_plug_{ref}" if board != "CM5" else f"CM5_plug_{ref}"
        if pn not in byn:
            continue
        pl = byn[pn]
        b = pl.bb
        d = port["dir"]
        sw = _sweep_boxes([pn], parts, vec=d, dist=10.0)
        fz = box(b[0] - 2, b[3] + 2, b[1] - 2, b[4] + 2, b[5] + 0.1, b[5] + 30.0) if abs(d[2]) < 0.5 else None
        state = lid_off if board in ("RR-CHS-MAIN", "CM5") else SERVICE_STATES["routine (saddle cover off, head removed)"]
        run(f"plug {tag}.{ref} pull + finger zone", compound([s for s in (sw, fz) if s is not None]), state, also_skip=[pn, f"{tag}_*" if board != "CM5" else "CM5_*"])
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
