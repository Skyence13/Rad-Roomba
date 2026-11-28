"""Configuration follows the contract (CR-05 accepted: STEP_AND_COUNT station pitch 0.080 m)."""
import importlib.util
import os
import sys
from pathlib import Path

import yaml

SRC = Path(__file__).resolve().parents[2]
for pkg in sorted(SRC.iterdir()):
    if (pkg / pkg.name).is_dir() and str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
REPO = Path(os.environ.get("RR_REPO", SRC.parents[1]))

from rr_bringup.geometry_config import CONFIG, load_robot_geometry, survey_method_defaults  # noqa: E402
from rr_coverage.planner import PlanConfig  # noqa: E402
from rr_coverage.supervisor import MissionConfig  # noqa: E402


def _contract_pitch(path):
    return float(yaml.safe_load(Path(path).read_text())["survey_methods"]["STEP_AND_COUNT"]["params"]["station_pitch_m"])


def test_step_and_count_pitch_default_follows_contract():
    repo_pitch = _contract_pitch(REPO / "interface/system/contract.yaml")
    assert abs(repo_pitch - 0.080) < 1e-9                     # CR-05 as accepted by the lead
    assert load_robot_geometry()["survey_method_defaults"]["station_pitch_m"] == repo_pitch
    assert MissionConfig().station_pitch_m == repo_pitch and PlanConfig().station_pitch_m == repo_pitch
    # still a parameter: the mission config overrides the contract default
    assert survey_method_defaults({"survey_methods": {"STEP_AND_COUNT": {"params": {"station_pitch_m": 0.05}}}}) == {"station_pitch_m": 0.05}


def _load_snapshot_tool():
    spec = importlib.util.spec_from_file_location("snapshot_contract", SRC.parent / "tools" / "snapshot_contract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _diff(snap, ref, path=""):
    """Every difference between the snapshot and the contract at the same path (the snapshot is a
    nested subset of the contract: each field present in it must be present and equal there)."""
    out = []
    if isinstance(snap, dict):
        if not isinstance(ref, dict):
            return [f"{path}: contract has no mapping here"]
        for k, v in snap.items():
            if k not in ref:
                out.append(f"{path}/{k}: missing in contract")
            else:
                out += _diff(v, ref[k], f"{path}/{k}")
    elif snap != ref:
        out.append(f"{path}: snapshot {snap!r} != contract {ref!r}")
    return out


def test_contract_snapshot_equals_contract_in_every_field():
    contract = yaml.safe_load((REPO / "interface/system/contract.yaml").read_text())
    snap = yaml.safe_load((CONFIG / "contract_snapshot.yaml").read_text())
    tool = _load_snapshot_tool()
    # (a) every field of the snapshot equals the contract (other than its own header fields)
    body = {k: v for k, v in snap.items() if k not in ("source", "contract_version")}
    assert snap["contract_version"] == contract["contract_version"]
    diffs = _diff(body, contract)
    assert not diffs, "contract_snapshot.yaml differs from the contract (run tools/test.sh snapshot):\n" + "\n".join(diffs)
    # (b) the snapshot is exactly what the generator writes: no field added by hand, none dropped
    assert snap == tool.build_snapshot(contract)
    assert (CONFIG / "contract_snapshot.yaml").read_text() == tool.render(contract)


def test_snapshot_comparison_detects_a_single_changed_field():
    contract = yaml.safe_load((REPO / "interface/system/contract.yaml").read_text())
    snap = _load_snapshot_tool().build_snapshot(contract)
    snap["frames"]["body_rev_e"]["swept_radii_m"]["head_outer_corner"] += 0.001
    snap["survey_methods"]["STEP_AND_COUNT"]["params"]["settle_s"] += 1
    body = {k: v for k, v in snap.items() if k not in ("source", "contract_version")}
    assert len(_diff(body, contract)) == 2


def test_in_place_turn_radius_follows_the_contract():
    contract = yaml.safe_load((REPO / "interface/system/contract.yaml").read_text())
    radii = contract["frames"]["body_rev_e"]["swept_radii_m"]
    want = max(radii.values())
    assert want == radii["tail_corner"] == 0.290                    # contract 0.4.0-draft7: as-built tail incl. rear bumper
    from rr_core.geometry import RobotOutline
    outline = RobotOutline(**load_robot_geometry()["outline"])
    assert outline.turn_radius == want
    from rr_coverage.planner import plan_coverage
    from rr_core.geometry import lane_polygons
    from rr_core.profiles import DATA
    import json
    lanes = lane_polygons(json.loads((DATA / "head_descriptor_demo.json").read_text()), load_robot_geometry()["mount_transform"])
    assert plan_coverage(3.0, 1.2, outline, lanes, PlanConfig())["turn_radius_m"] == want
