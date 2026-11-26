"""Configuration follows the contract (CR-05 accepted: STEP_AND_COUNT station pitch 0.080 m)."""
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
    assert _contract_pitch(CONFIG / "contract_snapshot.yaml") == repo_pitch     # packaged snapshot not stale
    assert MissionConfig().station_pitch_m == repo_pitch and PlanConfig().station_pitch_m == repo_pitch
    # still a parameter: the mission config overrides the contract default
    assert survey_method_defaults({"survey_methods": {"STEP_AND_COUNT": {"params": {"station_pitch_m": 0.05}}}}) == {"station_pitch_m": 0.05}
