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

No ROS imports.
"""
from __future__ import annotations

import math

import numpy as np


class PlanConfig:
    def __init__(self, wall_margin_m=0.03, turn_margin_m=0.02, front_margin_m=0.03, door_margin_m=0.10,
                 pair_overlap_m=0.005, allowance_m=0.010, speed_mps=0.10, transit_speed_mps=0.10,
                 reverse_speed_mps=0.05, yaw_rate_radps=0.25, end_caps=True, method="CONTINUOUS_SCAN",
                 station_pitch_m=0.10, settle_s=0.5, scaler_preset_s=10.0, premotion_s=1.5):
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
    x_door_pivot = cfg.door_margin_m + max(-outline.rear, outline.turn_radius)
    x_front_pivot = length_m - cfg.front_margin_m - outline.turn_radius
    x_front_end = length_m - cfg.front_margin_m - outline.front       # axle x with the nose at the front margin
    x_door_end = cfg.door_margin_m + outline.front                    # axle x heading -x with the nose at the door margin
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
    # ---- predicted coverage and residual strips (analytic; the survey reports the achieved ones)
    covered_lo, covered_hi = -y_max + pair_lo, -y_max + (n_pairs - 1) * stride + pair_hi
    x_cov_lo = x_door_end - lay["x_max"]            # -x passes: aperture leading edge (eroded)
    x_cov_hi = x_front_end + lay["x_max"]
    residual = {"left_wall_strip_m": round(width_m / 2 - covered_hi, 4),
                "right_wall_strip_m": round(covered_lo + width_m / 2, 4),
                "door_end_strip_m": round(x_cov_lo, 4), "front_end_strip_m": round(length_m - x_cov_hi, 4),
                "end_zone_single_heading_m": {"door": round(x_door_pivot + lay["x_min"] - x_cov_lo, 4),
                                              "front": round(x_cov_hi - (x_front_pivot - lay["x_min"]), 4)},
                "note": "wall strips are set by the in-place turn radius of the outline; see README coverage section"}
    # ---- time estimate
    t_pass = sum(abs(t["x_end"] - t["x_start"]) for t in tasks) / cfg.speed_mps
    if cfg.method == "STEP_AND_COUNT":
        n_st = sum(int(abs(t["x_end"] - t["x_start"]) / cfg.station_pitch_m) + 1 for t in tasks)
        t_pass = n_st * (cfg.scaler_preset_s + cfg.settle_s + cfg.station_pitch_m / cfg.speed_mps + 1.0)
    n_turn_180 = n_pairs
    n_shift = (3 if cfg.end_caps else 1) * n_pairs
    t_turn = (n_turn_180 * math.pi + n_shift * math.pi) / cfg.yaw_rate_radps
    t_retreat = len(tasks) * ((outline.turn_radius - outline.front + 0.02) / cfg.reverse_speed_mps + 2.0)
    t_lateral = (n_pairs * (3 if cfg.end_caps else 1) * off + max(0, n_pairs - 1) * stride) / cfg.reverse_speed_mps
    total = t_pass + t_turn + t_retreat + t_lateral + cfg.premotion_s
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
                                 "lateral_shifts": round(t_lateral, 1)},
            "config": dict(cfg.__dict__), "outline": outline.as_dict()}


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
    if not (y0 - 1e-6 <= ty <= y1 + 1e-6) or abs(s) > 0.05:
        return None                       # outside the reachable track band / not a track heading
    xa = min(max(tx - c * standoff_m, x0), x1)
    prims = transit(pose, (xa, ty, tyaw), region)
    ahead = (tx - xa) * c
    if abs(ahead) > 0.002:
        prims.append({"kind": "straight", "to": (tx, ty), "reverse": ahead < 0, "why": "APPROACH",
                      "speed": 0.05, "creep_m": 0.08})
    return prims
