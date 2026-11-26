"""Robot geometry from the project sources, never from literals (DEC-041).

Order of lookup: $RR_FRAMES_YAML / $RR_CONTRACT_YAML, then
$RR_REPO/mechanical/common/frames.yaml and $RR_REPO/interface/system/contract.yaml,
then the snapshots packaged in rr_bringup/config (copied from the repository on
the date in their header; a unit test fails when they differ from the repository).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

CONFIG = Path(__file__).with_name("config")


def _find(env, rel, snapshot):
    if os.environ.get(env):
        return Path(os.environ[env])
    repo = os.environ.get("RR_REPO")
    if repo and (Path(repo) / rel).exists():
        return Path(repo) / rel
    return CONFIG / snapshot


def load_robot_geometry() -> dict:
    fpath = _find("RR_FRAMES_YAML", "mechanical/common/frames.yaml", "frames_snapshot.yaml")
    cpath = _find("RR_CONTRACT_YAML", "interface/system/contract.yaml", "contract_snapshot.yaml")
    frames = yaml.safe_load(fpath.read_text())
    contract = yaml.safe_load(cpath.read_text())
    body = (contract.get("frames", contract).get("body_rev_e") or contract.get("body_rev_e"))
    fp = frames["footprint"]
    head = fp["head_envelope_m"]
    half_w = max(abs(v) for v in body["shell_envelope_mm"]["y"]) / 1000.0
    radii = body.get("swept_radii_m") or {}
    motion = contract["motion"]
    lidar = frames["frames"]["lidar_link"]
    hm = frames["frames"]["head_mount"]
    return {
        "outline": {"body_x": [fp["body_x_m"][0], max(fp["body_x_m"][1], head["x"][0])], "body_half_width": half_w,
                    "head_x": list(head["x"]), "head_half_width": max(abs(v) for v in head["y"]),
                    "turn_radius": max(radii.values()) if radii else None,
                    "source": f"{fpath.name} footprint + {cpath.name} body_rev_e (contract {contract.get('contract_version')})"},
        "mount_transform": {"xyz_m": list(hm["xyz"]), "rpy_rad": list(hm["rpy"]),
                            "basis": f"{fpath.name} frames.head_mount (nominal design value, not a measured as-installed transform)"},
        "lidar": {"xy": [lidar["xyz"][0], lidar["xyz"][1]], "yaw": lidar["rpy"][2]},
        "kinematics": {"track_m": frames["kinematics"]["track_m"], "wheel_radius_m": frames["kinematics"]["wheel_radius_m"]},
        "guided_arrival_tolerance_m": motion["guided_arrival_tolerance_m"],
        "expose_spot_reverse_offset_m": motion["expose_spot_reverse_offset_m"],
        "survey_speed_mps": motion["survey_speed_mps"],
        "sources": {"frames": str(fpath), "contract": str(cpath)},
    }
