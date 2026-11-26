"""Coverage planner for a rectangular floor (DEC-030): serpentine passes
parallel to the trailer length with the offset pattern that closes the lane
seams, end-cap recovery passes, and the residual strips it cannot reach.

Everything is derived from the DESCRIPTOR lane polygons through the mount
transform and from the robot outline (frames.yaml) - no geometry literals.

Derivation (all lengths in the lateral direction y):
    eroded lane width      we   = w - 2e          (e = position-uncertainty allowance)
    eroded seam            se   = p - we          (p = lane pitch)
    offset of pass B       off  = p / 2           (puts every seam of A under a lane centre of B)
    seam overlap per side  ov_s = (we - se) / 2   (must be >= 0, else the pattern cannot close the seams)
    A+B pair union         [lo, hi] = [min(c) - we/2, max(c) + we/2 + off]
    pair stride            S <= (hi - lo) - ov    (ov = overlap between neighbouring pairs)
Along x a pass can only measure ahead of the axle, so each heading leaves an
end zone that the other heading covers; short end-cap passes on the partner
track close the seams there.  In-place turns need the outline's turn radius
from every wall, which sets the outermost track and therefore the wall strips.

Wall tracks (owner decision 2026-11-26, CR-06 / IB-29), `wall_track_entry`:
    in_place       only the pivot-limited tracks above; ~0.14 m strips stay along the walls.
    reverse_entry  (default) one extra pair of tracks per side wall, as close to the wall as the
                   STRAIGHT-motion outline allows (half-width + wall margin + tracking tolerance),
                   outer track +x and inner track (offset p/2 inward) -x.  The robot never pivots
                   fully there: it enters by reversing along a shallow diagonal (nose turned away
                   from the wall by `wall_entry_angle_rad`) from a pivot-clear point, aligns with a
                   small pivot, scans, then backs off along the track, peels off with the same
                   small pivot and drives forward along the diagonal back to the pivot-clear band.
                   Every primitive of the manoeuvre (and the pass) is checked here with the swept
                   rectangle outline (body + head + tail) against the floor rectangle shrunk by the
                   wall/door/front margins and the tracking tolerance; a side whose manoeuvre does
                   not fit is left in_place and the numbers are reported (never a weaker check).
                   No coverage credit is given on the manoeuvre primitives (no `stage`).

No ROS imports.
"""
from __future__ import annotations

import math

import numpy as np

from rr_core.geometry import swept_parts, wrap


class PlanConfig:
    def __init__(self, wall_margin_m=0.03, turn_margin_m=0.02, front_margin_m=0.03, door_margin_m=0.10,
                 pair_overlap_m=0.005, allowance_m=0.010, speed_mps=0.10, transit_speed_mps=0.10,
                 reverse_speed_mps=0.05, yaw_rate_radps=0.25, end_caps=True, method="CONTINUOUS_SCAN",
                 station_pitch_m=0.08, settle_s=0.5, scaler_preset_s=10.0, premotion_s=1.5, door_end_x_m=0.0,
                 wall_track_entry="reverse_entry", wall_entry_angle_rad=0.09, track_tol_m=0.005):
        self.__dict__.update(locals())
        del self.__dict__["self"]


def lane_layout(lane_polys, allowance):
    """Lateral layout of the lanes in base_link from the descriptor polygons."""
    polys = [np.asarray(p) for p in lane_polys]
    cy = [float(p[:, 1].mean()) for p in polys]
    w = min(float(np.ptp(p[:, 1])) for p in polys)
    order = sorted(cy)
    pitch = float(np.mean(np.diff(order))) if len(order) > 1 else w
    we = w - 2 * allowance
    seam = pitch - w
    seam_e = pitch - we
    return {"centers_y": cy, "width": w, "pitch": pitch, "seam": seam, "eroded_width": we, "eroded_seam": seam_e,
            "offset": pitch / 2, "seam_overlap_per_side": (we - seam_e) / 2,
            "x_min": min(float(p[:, 0].min()) for p in polys) + allowance,
            "x_max": max(float(p[:, 0].max()) for p in polys) - allowance,
            "x_center": float(np.mean([p[:, 0].mean() for p in polys])),
            "length": min(float(np.ptp(p[:, 0])) for p in polys),
            "y_lo": min(order) - we / 2, "y_hi": max(order) + we / 2}


def plan_coverage(length_m, width_m, outline, lane_polys, cfg: PlanConfig) -> dict:
    lay = lane_layout(lane_polys, cfg.allowance_m)
    if lay["seam_overlap_per_side"] < 0:
        raise ValueError("eroded lane narrower than the eroded seam: one half-pitch offset cannot close the seams")
    off = lay["offset"]
    turn_clear = outline.turn_radius + cfg.turn_margin_m
    side_clear = max(outline.half_width + cfg.wall_margin_m, turn_clear)
    y_max = width_m / 2 - side_clear
    pair_lo, pair_hi = lay["y_lo"], lay["y_hi"] + off
    stride_max = (pair_hi - pair_lo) - cfg.pair_overlap_m
    span = 2 * y_max - off
    if span < 0:
        raise ValueError("floor too narrow for the turn radius of the outline")
    n_pairs = max(1, int(math.ceil(span / stride_max - 1e-9)) + 1)
    stride = span / (n_pairs - 1) if n_pairs > 1 else 0.0
    xd = cfg.door_end_x_m               # 0, or the removable door-end target's x (doors open, IB-30)
    x_door_pivot = xd + cfg.door_margin_m + max(-outline.rear, outline.turn_radius)
    x_front_pivot = length_m - cfg.front_margin_m - outline.turn_radius
    x_front_end = length_m - cfg.front_margin_m - outline.front       # axle x with the nose at the front margin
    x_door_end = xd + cfg.door_margin_m + outline.front               # axle x heading -x with the nose at the door margin
    if x_front_pivot <= x_door_pivot:
        raise ValueError("floor too short for in-place turns")
    stage = {"CONTINUOUS_SCAN": "SCAN", "SEARCH_THEN_COUNT": "SEARCH", "STEP_AND_COUNT": "SCALER"}[cfg.method]
    tasks = []

    def task(name, y, heading, x0, x1, cap):
        tasks.append({"id": f"T{len(tasks):03d}", "name": name, "y": round(y, 5), "heading": heading,
                      "x_start": round(x0, 5), "x_end": round(x1, 5), "stage": stage, "end_cap": cap,
                      "status": "PENDING", "attempts": 0})
    for j in range(n_pairs):
        ya = -y_max + j * stride
        yb = ya + off
        task(f"pair{j}:A+", ya, 0.0, x_door_pivot, x_front_end, False)
        if cfg.end_caps:
            task(f"pair{j}:B+cap", yb, 0.0, x_front_pivot - 0.02, x_front_end, True)
        task(f"pair{j}:B-", yb, math.pi, x_front_pivot, x_door_end, False)
        if cfg.end_caps:
            task(f"pair{j}:A-cap", ya, math.pi, x_door_pivot + 0.02, x_door_end, True)
    n_pair_tasks = len(tasks)
    wall = {"mode": cfg.wall_track_entry, "sides": {}}
    if cfg.wall_track_entry == "reverse_entry":
        bounds = (cfg.door_end_x_m + cfg.door_margin_m, length_m - cfg.front_margin_m,
                  -width_m / 2 + cfg.wall_margin_m + cfg.track_tol_m, width_m / 2 - cfg.wall_margin_m - cfg.track_tol_m)
        region = {"x": [x_door_pivot, x_front_pivot], "y": [-y_max, y_max]}
        for side, label in ((1, "L"), (-1, "R")):
            info = _wall_side(side, label, width_m, y_max, off, outline, cfg, bounds, region,
                              x_door_pivot, x_front_pivot, x_door_end, x_front_end, stage)
            wall["sides"][label] = {k: v for k, v in info.items() if k != "tasks"}
            for t in info.get("tasks", []):
                t["id"] = f"T{len(tasks):03d}"
                tasks.append(t)
    elif cfg.wall_track_entry != "in_place":
        raise ValueError("wall_track_entry must be in_place or reverse_entry")
    # ---- predicted coverage and residual strips (analytic; the survey reports the achieved ones)
    covered_lo, covered_hi = -y_max + pair_lo, -y_max + (n_pairs - 1) * stride + pair_hi
    if wall["sides"].get("L", {}).get("feasible"):
        covered_hi = max(covered_hi, wall["sides"]["L"]["y_outer"] + lay["y_hi"])
    if wall["sides"].get("R", {}).get("feasible"):
        covered_lo = min(covered_lo, wall["sides"]["R"]["y_outer"] + lay["y_lo"])
    x_cov_lo = x_door_end - lay["x_max"]            # -x passes: aperture leading edge (eroded)
    x_cov_hi = x_front_end + lay["x_max"]
    residual = {"left_wall_strip_m": round(width_m / 2 - covered_hi, 4),
                "right_wall_strip_m": round(covered_lo + width_m / 2, 4),
                "door_end_strip_m": round(x_cov_lo, 4), "front_end_strip_m": round(length_m - x_cov_hi, 4),
                "end_zone_single_heading_m": {"door": round(x_door_pivot + lay["x_min"] - x_cov_lo, 4),
                                              "front": round(x_cov_hi - (x_front_pivot - lay["x_min"]), 4)},
                "note": ("wall strips: reverse-entry wall tracks (straight-motion outline limit)" if wall["sides"] and
                         all(v.get("feasible") for v in wall["sides"].values()) else
                         "wall strips are set by the in-place turn radius of the outline") + "; see README coverage section"}
    # ---- time estimate
    pair_tasks = tasks[:n_pair_tasks]

    def pass_time(ts):
        if cfg.method == "STEP_AND_COUNT":
            n_st = sum(int(abs(t["x_end"] - t["x_start"]) / cfg.station_pitch_m) + 1 for t in ts)
            return n_st * (cfg.scaler_preset_s + cfg.settle_s + cfg.station_pitch_m / cfg.speed_mps + 1.0)
        return sum(abs(t["x_end"] - t["x_start"]) for t in ts) / cfg.speed_mps
    t_pass = pass_time(pair_tasks)
    t_wall = 0.0
    prev = (pair_tasks[-1]["x_end"], pair_tasks[-1]["y"]) if pair_tasks else (x_door_pivot, -y_max)
    for t in tasks[n_pair_tasks:]:
        m = t["maneuver"]
        t_wall += pass_time([t]) + m["time_s"] + math.pi / cfg.yaw_rate_radps \
            + math.dist(prev, m["entry_pose"][:2]) / cfg.transit_speed_mps
        prev = tuple(m["exit_point"])
    n_turn_180 = n_pairs
    n_shift = (3 if cfg.end_caps else 1) * n_pairs
    t_turn = (n_turn_180 * math.pi + n_shift * math.pi) / cfg.yaw_rate_radps
    t_retreat = n_pair_tasks * ((outline.turn_radius - outline.front + 0.02) / cfg.reverse_speed_mps + 2.0)
    t_lateral = (n_pairs * (3 if cfg.end_caps else 1) * off + max(0, n_pairs - 1) * stride) / cfg.reverse_speed_mps
    total = t_pass + t_turn + t_retreat + t_lateral + t_wall + cfg.premotion_s
    wall["extra_time_s"] = round(t_wall, 1)
    return {"layout": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in lay.items()},
            "n_pairs": n_pairs, "pair_stride_m": round(stride, 5), "pair_stride_max_m": round(stride_max, 5),
            "pair_overlap_m": round((pair_hi - pair_lo) - stride, 5) if n_pairs > 1 else None,
            "offset_m": round(off, 5), "seam_overlap_per_side_m": round(lay["seam_overlap_per_side"], 5),
            "track_y_max_m": round(y_max, 5), "side_clearance_m": round(side_clear, 5),
            "turn_radius_m": round(outline.turn_radius, 5),
            "pivot_region": {"x": [round(x_door_pivot, 4), round(x_front_pivot, 4)], "y": [round(-y_max, 4), round(y_max, 4)]},
            "tasks": tasks, "predicted_residual": residual, "method": cfg.method, "stage": stage,
            "estimated_time_s": round(total, 1),
            "time_breakdown_s": {"passes": round(t_pass, 1), "turns": round(t_turn, 1), "retreats": round(t_retreat, 1),
                                 "lateral_shifts": round(t_lateral, 1), "wall_tracks": round(t_wall, 1)},
            "wall_tracks": wall,
            "config": dict(cfg.__dict__), "outline": outline.as_dict()}


def check_prims(outline, pose, prims, bounds, step=0.005):
    """Swept-outline check of a primitive sequence from `pose` against the rectangle
    bounds = (x_lo, x_hi, y_lo, y_hi).  Returns (min clearance in m (negative = excursion), end pose).
    Straight primitives must lie along the current heading (forward or reverse)."""
    x_lo, x_hi, y_lo, y_hi = bounds
    worst = math.inf
    x, y, yaw = pose
    for p in prims:
        if p["kind"] == "straight":
            dx, dy = p["to"][0] - x, p["to"][1] - y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                along = dx * math.cos(yaw) + dy * math.sin(yaw)
                if abs(abs(along) - d) > 1e-4 or (along < 0) != bool(p.get("reverse")):
                    return -math.inf, (x, y, yaw)              # not a straight move along the heading
            move = {"kind": "straight", "dist": -d if p.get("reverse") else d}
            parts = swept_parts(outline, (x, y, yaw), move, 0.0, step)
            x, y = p["to"]
        elif p["kind"] == "pivot":
            parts = swept_parts(outline, (x, y, yaw), {"kind": "pivot", "angle": wrap(p["yaw"] - yaw)}, 0.0, step)
            yaw = p["yaw"]
        else:
            continue
        pts = np.vstack(parts)
        worst = min(worst, float(pts[:, 0].min() - x_lo), float(x_hi - pts[:, 0].max()),
                    float(pts[:, 1].min() - y_lo), float(y_hi - pts[:, 1].max()))
    return worst, (x, y, yaw)


def _wall_side(side, label, width_m, y_max, off, outline, cfg, bounds, region,
               x_door_pivot, x_front_pivot, x_door_end, x_front_end, stage):
    """Reverse-entry wall tracks for one side wall (side=+1 left/+y, -1 right/-y)."""
    y_out = width_m / 2 - (outline.half_width + cfg.wall_margin_m + cfg.track_tol_m)
    info = {"y_outer": round(side * y_out, 5), "y_band_edge": round(side * y_max, 5), "feasible": False}
    if y_out - off <= y_max + 1e-4 and y_out <= y_max + 1e-4:
        info["reason"] = "wall tracks would not reach beyond the pivot-clear band"
        return info
    tracks = [(f"wall{label}:outer+", side * y_out, 0.0, x_door_pivot, x_front_end),
              (f"wall{label}:inner-", side * (y_out - off), math.pi, x_front_pivot, x_door_end)]
    tried = []
    for theta in sorted({cfg.wall_entry_angle_rad, 0.08, 0.07, 0.06, 0.05}, reverse=True):
        if theta > cfg.wall_entry_angle_rad + 1e-12:
            continue
        out_tasks, worst, ok = [], math.inf, True
        for name, y_t, h, x0, x1 in tracks:
            dirn = math.cos(h)                                 # +1 for +x, -1 for -x
            s_rel = side * dirn                                # +1: wall on the robot's left
            h_m = wrap(h - s_rel * theta)                      # nose turned away from the wall
            # the align/peel pivots swing the tail behind the axle further than at the track heading:
            # start the track far enough from the end wall behind it for the whole pivot range
            phis = np.linspace(0.0, theta, 25)
            px, py = outline.points[:, 0], np.abs(outline.points[:, 1])
            rear_ext = float(max(np.max(-(px * math.cos(f)) + py * math.sin(f)) for f in phis))
            x0 = max(x0, bounds[0] + rear_ext + cfg.track_tol_m) if dirn > 0 else min(x0, bounds[1] - rear_ext - cfg.track_tol_m)
            dy = abs(y_t - side * y_max)
            if dy < 1e-4:                                      # already inside the band: ordinary task
                out_tasks.append({"name": name, "y": round(y_t, 5), "heading": h, "x_start": round(x0, 5), "x_end": round(x1, 5),
                                  "stage": stage, "end_cap": False, "status": "PENDING", "attempts": 0, "wall_track": label})
                continue
            D = dy / math.tan(theta)
            diag = dy / math.sin(theta)
            P = (x0 + dirn * D, side * y_max, h_m)
            x_q = x_front_pivot if dirn > 0 else x_door_pivot
            Fb = (x_q - dirn * D, y_t)
            Q = (x_q, side * y_max)
            in_region = region["x"][0] - 1e-6 <= P[0] <= region["x"][1] + 1e-6 and (Fb[0] - x0) * dirn >= -1e-6
            entry = [{"kind": "straight", "to": (round(x0, 5), round(y_t, 5)), "reverse": True, "why": "WALL_ENTRY", "speed": cfg.reverse_speed_mps},
                     {"kind": "pivot", "yaw": h, "why": "WALL_ALIGN"}]
            pass_prim = [{"kind": "straight", "to": (x1, y_t), "reverse": False}]
            exit_ = [{"kind": "straight", "to": (round(Fb[0], 5), round(y_t, 5)), "reverse": True, "why": "WALL_BACKOFF", "speed": cfg.reverse_speed_mps},
                     {"kind": "pivot", "yaw": h_m, "why": "WALL_PEEL"},
                     {"kind": "straight", "to": (round(Q[0], 5), round(Q[1], 5)), "reverse": False, "why": "WALL_EXIT"}]
            c_entry, pose = check_prims(outline, P, entry, bounds)
            c_pass, pose = check_prims(outline, pose, pass_prim, bounds)
            c_exit, _ = check_prims(outline, pose, exit_, bounds)
            c = min(c_entry, c_pass, c_exit)
            worst = min(worst, c)
            if not in_region or c < -1e-9:
                ok = False
                tried.append({"theta_rad": theta, "track": name, "clearance_m": round(c, 5) if math.isfinite(c) else None,
                              "entry_point_in_pivot_region": in_region})
                break
            t_m = diag / cfg.reverse_speed_mps + theta / cfg.yaw_rate_radps \
                + abs(x1 - Fb[0]) / cfg.reverse_speed_mps + theta / cfg.yaw_rate_radps + diag / cfg.transit_speed_mps
            out_tasks.append({"name": name, "y": round(y_t, 5), "heading": h, "x_start": round(x0, 5), "x_end": round(x1, 5),
                              "stage": stage, "end_cap": False, "status": "PENDING", "attempts": 0, "wall_track": label,
                              "maneuver": {"theta_rad": theta, "h_m": round(h_m, 6),
                                           "entry_pose": [round(P[0], 5), round(P[1], 5), round(h_m, 6)],
                                           "entry": entry, "exit": exit_, "exit_point": [round(Q[0], 5), round(Q[1], 5)],
                                           "clearance_min_m": round(c, 5), "time_s": round(t_m, 1),
                                           "diagonal_m": round(diag, 4), "lateral_m": round(dy, 4)}})
        if ok:
            info.update(feasible=True, theta_rad=theta, clearance_min_m=round(worst, 5), tasks=out_tasks,
                        tried=tried, bounds=[round(b, 5) for b in bounds])
            return info
    info.update(reason="no entry angle satisfies the swept-outline check", tried=tried, bounds=[round(b, 5) for b in bounds])
    return info


def transit(pose, target, region, reverse_short_m=0.5):
    """Primitives from `pose` to the start pose `target` (x, y, yaw) using only
    straight legs and in-place pivots inside the pivot-clear region:
    retreat (reverse straight) into the region if needed, pivot, straight, pivot."""
    x, y, yaw = pose
    prims = []
    (x0, x1), (y0, y1) = region["x"], region["y"]
    # 1. retreat along the current heading until a pivot is clear of the end walls
    c, s = math.cos(yaw), math.sin(yaw)
    if abs(c) > 0.7:
        if x > x1 + 1e-4 and c > 0 or x < x0 - 1e-4 and c < 0:
            xr = x1 if x > x1 else x0
            d = (x - xr) / c
            prims.append({"kind": "straight", "to": (xr, y - d * s), "reverse": True, "why": "RETREAT"})
            x, y = xr, y - d * s
    dx, dy = target[0] - x, target[1] - y
    dist = math.hypot(dx, dy)
    dyaw = math.atan2(math.sin(target[2] - yaw), math.cos(target[2] - yaw))
    if dist < 0.004:
        if abs(dyaw) > 0.003:
            prims.append({"kind": "pivot", "yaw": target[2]})
        return prims
    bearing = math.atan2(dy, dx)
    fwd_turn = abs(math.atan2(math.sin(bearing - yaw), math.cos(bearing - yaw)))
    if fwd_turn < 0.02 and abs(dyaw) < 0.02:
        prims.append({"kind": "straight", "to": (target[0], target[1]), "reverse": False, "why": "TRANSIT"})
        return prims
    rev_heading = bearing + math.pi
    rev_turn = abs(math.atan2(math.sin(rev_heading - yaw), math.cos(rev_heading - yaw)))
    rev_total = rev_turn + abs(math.atan2(math.sin(target[2] - rev_heading), math.cos(target[2] - rev_heading)))
    fwd_total = fwd_turn + abs(math.atan2(math.sin(target[2] - bearing), math.cos(target[2] - bearing)))
    use_reverse = dist <= reverse_short_m and rev_total < fwd_total - 0.2
    leg_heading = rev_heading if use_reverse else bearing
    prims.append({"kind": "pivot", "yaw": leg_heading})
    prims.append({"kind": "straight", "to": (target[0], target[1]), "reverse": use_reverse, "why": "TRANSIT"})
    prims.append({"kind": "pivot", "yaw": target[2]})
    return prims


def approach(pose, target, region, standoff_m=0.30):
    """Primitives that end with a straight forward approach along the target heading
    (used for deferred counts and guided revisits): transit to a point on the target
    line inside the pivot-clear region, then drive forward (or back) onto the target."""
    tx, ty, tyaw = target
    c, s = math.cos(tyaw), math.sin(tyaw)
    (x0, x1), (y0, y1) = region["x"], region["y"]
    if not (y0 - 0.005 <= ty <= y1 + 0.005) or abs(s) > 0.05:      # 5 mm: path-following tolerance of a track
        return None                       # outside the reachable track band / not a track heading
    xa = min(max(tx - c * standoff_m, x0), x1)
    prims = transit(pose, (xa, ty, tyaw), region)
    ahead = (tx - xa) * c
    if abs(ahead) > 0.002:
        prims.append({"kind": "straight", "to": (tx, ty), "reverse": ahead < 0, "why": "APPROACH",
                      "speed": 0.05, "creep_m": 0.08})
    return prims
