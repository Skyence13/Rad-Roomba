"""The packaged demonstration calibration / profile / schema are generated copies of analysis/radiometry (staleness test,
like the contract snapshot's), and calibration records are validated against the schema on load."""
import copy
import importlib.util
import json

import pytest

from rr_core.profiles import DATA, Calibration, CalibrationError
from conftest import REPO


def _tool():
    spec = importlib.util.spec_from_file_location("refresh_demo_data", REPO / "ros2_ws" / "tools" / "refresh_demo_data.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_packaged_demo_data_equal_the_analysis_directory():
    assert _tool().stale() == [], "run tools/refresh_demo_data.py"


def test_calibration_records_are_validated_against_the_schema():
    rec = json.loads((DATA / "demo_calibration.json").read_text())
    cal = Calibration(rec)
    assert cal.identity["head_serial"] == "HEAD-DEMO-001" and cal.envelope["speed_m_s"]["max"] == 0.12
    bad = copy.deepcopy(rec)
    del bad["identity"]
    with pytest.raises(CalibrationError):
        Calibration(bad)
