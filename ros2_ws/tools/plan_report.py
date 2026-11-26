#!/usr/bin/env python3
"""Calculated coverage plan + mission-time estimate for a trailer floor (default 16.0 x 2.5 m),
for the three survey methods as implemented in rr_coverage/planner.py.

    tools/test.sh plan          # writes evidence/plan_2.5x16.json (runs inside the image)  Evidence class: calculated."""
import json, sys
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / "src"
for p in SRC.iterdir():
    sys.path.insert(0, str(p))
from rr_bringup.geometry_config import load_robot_geometry
from rr_core.geometry import RobotOutline, lane_polygons
from rr_core.profiles import DATA
from rr_coverage.planner import plan_coverage, PlanConfig

L, W = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (16.0, 2.5)
geo = load_robot_geometry()
out = RobotOutline(**geo["outline"])
lanes = lane_polygons(json.loads((DATA / "head_descriptor_demo.json").read_text()), geo["mount_transform"])
res = {"evidence_class": "calculated", "floor_m": [L, W],
       "note": "SEARCH_THEN_COUNT estimate is the search stage only; add per alarm: scaler count (30 s preset, <=100 s adaptive) + stop/peak follow <=0.15 m + reverse/realign"}
for name, kw in (("continuous_0.10", dict(speed_mps=0.10)), ("continuous_0.03", dict(speed_mps=0.03)),
                 ("search_then_count_0.10_search_only", dict(method="SEARCH_THEN_COUNT", speed_mps=0.10)),
                 ("step_and_count_10s", dict(method="STEP_AND_COUNT", scaler_preset_s=10.0)),
                 ("continuous_0.10_no_endcaps", dict(speed_mps=0.10, end_caps=False))):
    p = plan_coverage(L, W, out, lanes, PlanConfig(**kw))
    r = {k: p[k] for k in ("n_pairs", "offset_m", "pair_stride_m", "pair_overlap_m", "seam_overlap_per_side_m", "track_y_max_m",
                           "turn_radius_m", "predicted_residual", "estimated_time_s", "time_breakdown_s")}
    r["method"] = kw.get("method", "CONTINUOUS_SCAN")
    r["n_tasks"] = len(p["tasks"]); r["layout"] = p["layout"]
    pr = p["predicted_residual"]
    r["predicted_covered_fraction"] = round((W - pr["left_wall_strip_m"] - pr["right_wall_strip_m"]) * (L - pr["door_end_strip_m"] - pr["front_end_strip_m"]) / (L * W), 4)
    r["estimated_time_h"] = round(p["estimated_time_s"] / 3600, 2)
    res[name] = r
res["outline"] = out.as_dict(); res["mount"] = geo["mount_transform"]
print(json.dumps(res, indent=1))
