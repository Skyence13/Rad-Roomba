"""Review-queue policy (owner decision 2026-11-27, contract survey_methods.review_queue_policy)."""
import json
from types import SimpleNamespace

import pytest

from rr_core.processing import classify_cell
from rr_core.profiles import DATA, ProfileError, ProfileStore, decision_parameters, review_queue_policy

LEVEL = 0.30


def dec(D, u, detected, beta=0.05):
    return SimpleNamespace(D=D, u_total=u, detected=detected, beta=beta)


def test_alarm_only_queues_alarms_only():
    # poorly resolved, not alarming: D# above the goal but no alarm -> not flagged under ALARM_ONLY
    weak = dec(0.13, 0.14, detected=False)
    assert classify_cell(weak, LEVEL, "ALARM_ONLY") is None
    assert classify_cell(weak, LEVEL, "ALL_UNRESOLVED") == "UNRESOLVED_EXCEEDANCE"
    # an alarm is flagged under both policies, with the same kind
    for d, kind in ((dec(0.72, 0.15, True), "INVESTIGATION_LEVEL"), (dec(0.20, 0.10, True), "UNRESOLVED_EXCEEDANCE"),
                    (dec(0.05, 0.01, True), "SCAN_DETECTION")):
        assert classify_cell(d, LEVEL, "ALARM_ONLY") == kind
        assert classify_cell(d, LEVEL, "ALL_UNRESOLVED") == kind
    # a clean, well-resolved cell is never flagged
    assert classify_cell(dec(0.01, 0.02, False), LEVEL, "ALARM_ONLY") is None
    assert classify_cell(dec(0.01, 0.02, False), LEVEL, "ALL_UNRESOLVED") is None
    assert classify_cell(dec(None, None, False), LEVEL, "ALARM_ONLY") is None


def test_policy_default_validation_and_parameters():
    store = ProfileStore(json.loads((DATA / "demo_site_profile_ore.json").read_text()))
    assert all(p["review_queue_policy"] == "ALARM_ONLY" for p in store.document["profiles"])   # absent -> default
    p = dict(store.document["profiles"][0])
    params = decision_parameters(p, 300)
    assert params["review_queue_policy"] == "ALARM_ONLY" and params["alpha_queue"] == p["alpha_per_decision"] == params["alpha_scan"]
    assert review_queue_policy({"review_queue_policy": "ALL_UNRESOLVED"}) == "ALL_UNRESOLVED"
    with pytest.raises(ProfileError):
        review_queue_policy({"review_queue_policy": "EVERYTHING"})
