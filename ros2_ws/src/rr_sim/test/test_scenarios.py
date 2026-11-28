"""End-to-end scenario tests (simulated; deterministic seeds). Evidence is written to ros2_ws/evidence/.
Traces: see ros2_ws/README.md traceability table."""
import pytest
from rr_sim import scenarios as sc


def run(fn, tmp_path, **kw):
    ev = fn(tmp_path, **kw)
    failed = [c for c in ev["checks"] if not c["ok"]]
    assert not failed, failed
    return ev


def test_s01_normal_survey_and_guided_revisit(tmp_path):
    run(sc.s01_normal_survey_and_revisit, tmp_path)


def test_s02_head_reset_and_disconnect(tmp_path):
    run(sc.s02_head_reset_and_disconnect, tmp_path)


def test_s03_protective_stop(tmp_path):
    run(sc.s03_protective_stop, tmp_path)


@pytest.mark.parametrize("cleared", [True, False])
def test_s04_blocked_strip(tmp_path, cleared):
    run(sc.s04_blocked_strip, tmp_path, cleared=cleared)


def test_s05_revisit_with_person(tmp_path):
    run(sc.s05_revisit_with_person, tmp_path)


def test_s06_charge_service(tmp_path):
    run(sc.s06_charge_service, tmp_path)


def test_s07_lost_control_session(tmp_path):
    run(sc.s07_lost_control_session, tmp_path)


def test_s08_replay(tmp_path):
    run(sc.s08_replay, tmp_path)


def test_s09_timing(tmp_path):
    run(sc.s09_timing, tmp_path)


def test_s10_step_and_count(tmp_path):
    run(sc.s10_step_and_count, tmp_path)


@pytest.mark.parametrize("policy", ["INLINE", "DEFERRED"])
def test_s11_search_then_count(tmp_path, policy):
    run(sc.s11_search_then_count, tmp_path, policy=policy)


def test_s12_reboot_resume(tmp_path):
    run(sc.s12_reboot_resume, tmp_path)


def test_s13_door_target(tmp_path):
    run(sc.s13_door_target, tmp_path)


def test_s14_wall_tracks(tmp_path):
    run(sc.s14_wall_tracks, tmp_path)


def test_s15_no_automatic_resume(tmp_path):
    run(sc.s15_no_auto_resume, tmp_path)
