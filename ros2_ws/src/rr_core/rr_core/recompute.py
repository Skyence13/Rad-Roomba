"""Stand-alone recomputation of one decision cell from a mission archive (MODEL.md rev 5 section 8; review C3).

Inputs: the run directory (journal + run.json), the calibration file(s) and the profile file - nothing from the export
and nothing from the live process.  What it does:
 1. replays the archived raw head stream through the ICD interpreter and the archived poses / supervisor marks (the
    same decoding and credit qualification as the survey: which lane-gates are credited, and the coverage raster);
 2. recomputes the cell's MEMBERSHIP AND WEIGHTS by its own path: for every credited lane-gate near the cell, the swept
    eroded footprint from the archived poses and the descriptor (erosion = the credited 2 sigma recorded per gate),
    its exact area fraction in the cell, rounded to 0.05, cut at 0.10;
 3. rebuilds the reference series from the decoded gates (not from processing state), forms U_null under MODEL.md rev 5
    section 3 and evaluates the statistic with a FRESH exact evaluator;
 4. returns D, u_stat, u_total, D*, D#, the decision, the status and the comparison with the replayed processing.
Shared with the survey code: the ICD decoder, the trajectory interpolation, the geometry primitives, rr_core.unull and the
exact evaluator (cross-tested against analysis/radiometry/rrrad).  No ROS imports.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import estimator as est
from . import unull
from .geometry import convex_hull, erode_convex, rect_clip_area, transform
from .pipeline import build_from_run
from .profiles import Calibration


def _members_independent(proc, cell):
    """(attachment index, sequence, lane, weight) of the cell recomputed from gate_log, poses and descriptor."""
    cy, cx = cell
    c = proc.cfg.cell_m
    x0, y0 = proc.x0 + cx * c, proc.y0 + cy * c
    out = []
    for g in proc.gate_log:
        if g["stage"] not in ("SCAN", "SEARCH", "SCALER") or g["pose"] is None or g["t0_us"] is None:
            continue
        a = proc.a_index(g["attachment"])
        polys = proc._geom[a][0]
        try:
            poses = proc.traj.interval(g["t0_us"], g["t1_us"])
        except Exception:
            continue
        for lane in g["lanes"]:
            if not lane["credited"] or lane.get("erosion_m") is None:
                continue
            if g["stage"] == "SCALER":
                tag = proc.mark_at(g["t0_us"])[1].get("station")
                if not proc._station_result.get(tag):
                    continue
            er = erode_convex(polys[lane["id"]], lane["erosion_m"])
            pts = np.concatenate([transform((p["x"], p["y"], p["yaw"]), er) for p in (poses[0], poses[len(poses) // 2], poses[-1])])
            hull = convex_hull(pts)
            lo, hi = hull.min(axis=0), hull.max(axis=0)
            if hi[0] < x0 or lo[0] > x0 + c or hi[1] < y0 or lo[1] > y0 + c:
                continue
            area = rect_clip_area(hull, -1e9, 1e9, -1e9, 1e9)
            f = rect_clip_area(hull, x0, x0 + c, y0, y0 + c) / area
            w = round(round(f / est.WEIGHT_STEP) * est.WEIGHT_STEP, 10)
            if w >= est.MIN_LANE_GATE_WEIGHT - 1e-12:
                out.append((a, g["sequence"], lane["id"], w))
    return sorted(out)


def _series_from_gates(proc, a_idx):
    """Reference series of one attachment rebuilt from the decoded gates (gate_log reasons + counts), not processing state."""
    ref, geo = {}, {}
    for g in proc.gate_log:
        if proc.a_index(g["attachment"]) != a_idx:
            continue
        row = []
        for lane in sorted(g["lanes"], key=lambda l: l["id"]):
            cnt = proc._gate_counts.get((a_idx, g["sequence"], lane["id"]))
            reasons = [r for r in lane["reasons"] if not r.startswith(("NO_CREDIT", "POSE_", "NO_POSE", "NO_HOST_TIME", "NO_CALIBRATION"))]
            bad = any(r.startswith("HEAD_FLAG") or r in ("LANE_FLAG:REFERENCE_FAULT", "LANE_FLAG:DISCRIMINATOR_FAULT", "NULL:photon_ref",
                                                         "UNSYNCED", "HOLDOVER", "BOUND") for r in reasons)
            row.append(None if cnt is None or bad else (cnt[3], cnt[4]))
        ref[g["sequence"]] = row
        if g["pose"] is not None:
            geo[g["sequence"]] = (g["pose"][0], g["pose"][1])
    return unull.Series.build(ref, geo)


def recompute_cell(run_dir, ix, iy, calibration_files=(), profile=None):
    run_dir = Path(run_dir)
    cals = [Calibration.load(p) for p in calibration_files] or None
    prof = json.loads(Path(profile).read_text()) if isinstance(profile, (str, Path)) else profile
    mission_cal = cals[0] if cals else None
    pipe, run = build_from_run(run_dir, calibration=mission_cal, profile=prof, calibrations=cals)
    proc = pipe.proc
    proc.finish()
    cell = (iy, ix)
    ch = proc._decision_channel()
    alpha, beta = proc.params["alpha_scan"], proc.params["beta"]
    members = _members_independent(proc, cell)
    m_cand = max(1, len({(a, ln) for a, _q, ln, _w in members}))
    alpha_min = (1.0 - est.ALPHA_SPLIT_COMBINED) * alpha / m_cand
    test = {}
    for a, q, _ln, _w in members:
        test.setdefault(a, set()).add(q)
    units = []
    series = {a: _series_from_gates(proc, a) for a in test}
    glog = {(proc.a_index(g["attachment"]), g["sequence"]): g for g in proc.gate_log}
    tw = [(glog[(a, q)].get("head_c"), w) for a, q, _ln, w in members if glog[(a, q)].get("head_c") is not None]
    head_c = sum(t * w for t, w in tw) / sum(w for _t, w in tw) if tw else None
    for (a, ln) in sorted({(a, ln) for a, _q, ln, _w in members}):
        cal_a = proc.cal_of(a)
        if cal_a is None:
            continue
        rows = [(q, w) for aa, q, l2, w in members if aa == a and l2 == ln]
        runs, run_ = [], []
        for q in sorted(test[a]):
            if run_ and q > run_[-1] + 1:
                runs.append(run_)
                run_ = []
            run_.append(q)
        runs.append(run_)
        wsum = [sum(w for q, w in rows if r[0] <= q <= r[-1]) for r in runs]
        best = runs[int(np.argmax(wsum))]
        rec = unull.u_null(series[a], ln, (best[0], best[-1]), alpha_min, exclude_seqs=test[a])
        cnt = [proc._gate_counts[(a, q, ln)] for q, _w in rows]
        k = 0 if ch == "beta" else 2
        c = cal_a.cal(ln, ch)
        ok, why = True, ""
        if rec.get("U0") is not None:
            ok, why = cal_a.check_envelope(ln, ch, rec["U0"], head_c, goal=proc.profile["detection_goal_Bq_cm2"], alpha=alpha, beta=beta,
                                           speed_mps=max([glog[(a, q)].get("speed_mps") or 0.0 for q, _w in rows], default=None),
                                           speed_tol=proc.cfg.speed_tolerance_mps, standoff_mm=proc.att[a]["standoff"]["mm"],
                                           require_standoff=True)
        units.append(est.LaneGates(ln, [w for _q, w in rows], [x[1] for x in cnt], [x[k] for x in cnt], [x[4] for x in cnt],
                                   [x[3] for x in cnt], rec.get("U0"), "recompute", c, ok, why,
                                   N_post=rec.get("N_post"), T_post=rec.get("T_post"), u0_rec=rec))
    d = est.combine(units, alpha, beta, decider=est.Decider())
    proc.finalize()
    rd = proc.recorded[ch].get(cell)
    st = proc.cell_status(cell, d=d)          # status rules of MODEL.md rev 5 section 6 applied to THIS decision
    out = {"cell": {"ix": ix, "iy": iy}, "members": len(members),
           "members_equal_processing": members == sorted(proc.members.get(cell, [])),
           "D": d.D, "u_stat": d.u_stat, "u_total": d.u_total, "D_star": d.D_star, "D_hash": d.D_hash, "detected": d.detected,
           "m": d.m, "method": d.method, "status": st[0], "status_reason": st[1],
           "processing": None if rd is None else {"D": rd.D, "D_star": rd.D_star, "D_hash": rd.D_hash, "detected": rd.detected}}
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Recompute one decision cell from a mission archive (MODEL.md rev 5 section 8)")
    ap.add_argument("run_dir")
    ap.add_argument("ix", type=int)
    ap.add_argument("iy", type=int)
    ap.add_argument("--calibration", action="append", default=[], help="calibration file (first = mission calibration); default: the records in run.json")
    ap.add_argument("--profile", default=None, help="profile snapshot JSON (default: the one in run.json)")
    a = ap.parse_args(argv)
    r = recompute_cell(a.run_dir, a.ix, a.iy, a.calibration, a.profile)
    print(json.dumps(r, indent=1, default=lambda v: None if isinstance(v, float) and not math.isfinite(v) else str(v)))


if __name__ == "__main__":
    main()
