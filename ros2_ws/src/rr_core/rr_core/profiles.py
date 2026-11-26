"""Calibration records and site survey profiles (host side).

Calibration: MODEL.md section 1 record per lane and class with validity
envelope; loaded from analysis/radiometry/demo_calibration.json format.
Profiles: design 0.3 section 5 / RQ-035: explicit units (Bq/cm2 stored;
entering 4 Bq/m2 means 0.0004 Bq/cm2; a unit change never rescales a stored
number silently), versioned edits restricted to the RP role, no implied
yellowcake preset, mission snapshot immutable.

Everything shipped here is SYNTHETIC (`field_use_approved: false`).
No ROS imports.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .estimator import Cal, kappa, u_k_floor

UNIT_FACTORS = {"Bq/cm2": 1.0, "Bq/m2": 1.0e-4}     # to Bq/cm2
CLASS_OF_CHANNEL = {"beta": "beta_window", "alpha": "alpha_like"}
ROLES = ("viewer", "operator", "rp")
SURVEY_METHODS = ("CONTINUOUS_SCAN", "SEARCH_THEN_COUNT", "STEP_AND_COUNT")   # contract survey_methods (DEC-038)

DATA = Path(__file__).with_name("data")


class ProfileError(ValueError):
    pass


def to_bq_cm2(value: float, unit: str) -> float:
    """Explicit unit entry rule (design 0.3 section 5)."""
    if unit not in UNIT_FACTORS:
        raise ProfileError(f"unit must be one of {sorted(UNIT_FACTORS)}; got {unit!r}")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ProfileError("activity value must be a non-negative number")
    return float(value) * UNIT_FACTORS[unit]


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------- calibration
class Calibration:
    def __init__(self, record: dict):
        self.record = record
        self.calibration_id = record["calibration_id"]
        self.field_use_approved = bool(record.get("field_use_approved", False))
        self.synthetic = bool(record.get("synthetic", True))
        self.envelope = record.get("validity_envelope", {})
        self.sha256 = canonical_sha256(record)
        self.u0_evaluation = record.get("u0_evaluation", "smoothed_reference")
        self.cov_FU_assumed = record.get("cov_FU_assumed", 0.0)
        self._cal = {}
        for lane in record["lanes"]:
            for cls, c in lane["classes"].items():
                comp = c.get("u_k_components", {})
                u_common = comp.get("spectral_mismatch_relative", 0.0) * c["k"]
                u_lane = comp.get("fit")
                if u_lane is None:
                    u_lane = max(c.get("u_k", 0.0) ** 2 - u_common ** 2, 0.0) ** 0.5
                self._cal[(lane["lane_index"], cls)] = Cal(
                    k=c["k"], b=c["b_cps"], u_k_lane=u_lane, u_k_common=u_common, u_b=c.get("u_b_cps", 0.0),
                    cov_kb=c.get("cov_kb_cps", 0.0), K=c["K_cps_per_Bq_cm2"], u_rel_K=c.get("u_rel_K", 0.0),
                    eps=c.get("leakage_fraction"))

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def cal(self, lane: int, channel: str) -> Cal:
        return self._cal[(lane, CLASS_OF_CHANNEL.get(channel, channel))]

    def classes(self):
        return sorted({c for _, c in self._cal})

    def check_envelope(self, lane: int, channel: str, U: float, head_c, setup_id=None,
                       goal=None, alpha=0.05, beta=0.05):
        """(ok, reason).  Reference-rate range with the R7 cap, temperature, setup."""
        env = self.envelope
        rr = env.get("reference_rate_cps") or {}
        if rr and not (rr.get("min", 0.0) <= U <= rr.get("max", float("inf"))):
            return False, "reference rate outside qualified range"
        if goal is not None and u_k_floor(U, self.cal(lane, channel), alpha, beta) >= goal:
            return False, "sensitivity insufficient - reference rate above qualified range"
        tr = env.get("head_temperature_C") or {}
        if tr and head_c is not None and not (tr.get("min", -1e9) <= head_c <= tr.get("max", 1e9)):
            return False, "head temperature outside qualified range"
        return True, ""

    def summary(self) -> dict:
        return {"calibration_id": self.calibration_id, "sha256": self.sha256,
                "synthetic": self.synthetic, "field_use_approved": self.field_use_approved,
                "u0_evaluation": self.u0_evaluation, "cov_FU_assumed": self.cov_FU_assumed,
                "validity_envelope": self.envelope}


class CalibrationStore:
    """Robot-side calibration registry; `resolve` is the head-link calibration check."""

    def __init__(self, calibrations=(), strict_setup: bool = False):
        self.by_id = {c.calibration_id: c for c in calibrations}
        self.strict_setup = strict_setup

    def resolve(self, verified: dict, hello: dict) -> dict:
        from .descriptor import DescriptorError
        cal_id = verified.get("calibration_id")
        if verified["mode"] == "BENCH" and not cal_id:
            return None
        cal = self.by_id.get(cal_id)
        if cal is None:
            raise DescriptorError("CALIBRATION_UNKNOWN", f"no local calibration record {cal_id!r}")
        if verified["mode"] == "SURVEY" and not cal.field_use_approved:
            raise DescriptorError("CALIBRATION_NOT_APPROVED", "calibration is not approved for field use")
        setup = cal.envelope.get("setup_id")
        if self.strict_setup and setup and setup != hello["setup_id"]:
            raise DescriptorError("CALIBRATION_SETUP_MISMATCH",
                                  f"calibration is for setup {setup}, head reports {hello['setup_id']}")
        return {"calibration_id": cal.calibration_id, "sha256": cal.sha256,
                "field_use_approved": cal.field_use_approved, "synthetic": cal.synthetic,
                "setup_match": (setup == hello["setup_id"]) if setup else None}


# -------------------------------------------------------------------- profiles
REQUIRED_FOR_DECISION = ("decision_class", "investigation_level_Bq_cm2", "detection_goal_Bq_cm2",
                         "alpha_per_decision", "beta_per_decision", "head_calibration_id")
ACTIVITY_FIELDS = ("investigation_level_Bq_cm2", "site_reported_comparison_Bq_cm2", "detection_goal_Bq_cm2")


class ProfileStore:
    """Versioned site profiles with role-checked, audited edits."""

    def __init__(self, document: dict):
        if document.get("surface_activity_unit") != "Bq/cm2":
            raise ProfileError("profile document must state surface_activity_unit Bq/cm2")
        self.document = copy.deepcopy(document)
        self.history = []          # every superseded revision is retained
        self.audit = []

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def ids(self):
        return [p["id"] for p in self.document["profiles"]]

    def get(self, profile_id: str) -> dict:
        for p in self.document["profiles"]:
            if p["id"] == profile_id:
                return p
        raise ProfileError(f"unknown profile {profile_id!r}")

    @staticmethod
    def missing_for_decision(profile: dict) -> list:
        return [k for k in REQUIRED_FOR_DECISION if profile.get(k) is None]

    def snapshot(self, profile_id: str, calibration: Calibration | None, mode: str) -> dict:
        """Immutable copy bound to a mission; raises when it cannot produce a decision.

        Unapproved (synthetic) profiles are usable only in COMMISSIONING.
        """
        p = copy.deepcopy(self.get(profile_id))
        missing = self.missing_for_decision(p)
        if missing:
            raise ProfileError(f"profile {profile_id} is not configured: missing {missing}")
        approved = bool(p.get("field_use_approved")) and bool(p.get("enabled_for_operational_surveys"))
        if mode != "COMMISSIONING" and not approved:
            raise ProfileError(f"profile {profile_id} is not approved for operational surveys")
        if calibration is None or calibration.calibration_id != p["head_calibration_id"]:
            raise ProfileError("profile calibration reference does not match the bound head calibration")
        p["unit"] = "Bq/cm2"
        p["field_use_approved"] = approved and calibration.field_use_approved
        p["sha256"] = canonical_sha256(p)
        return p

    def edit(self, profile_id: str, changes: dict, user: str, role: str, mission_active: bool = False,
             unit: str | None = None) -> dict:
        """RP-only edit.  Activity fields need an explicit `unit`; the value is
        converted and stored in Bq/cm2.  Bumps the revision and keeps history."""
        if role != "rp":
            self.audit.append({"op": "profile_edit", "user": user, "role": role, "accepted": False,
                               "reason": "ROLE"})
            raise ProfileError("only the RP role may edit profiles")
        if mission_active:
            self.audit.append({"op": "profile_edit", "user": user, "role": role, "accepted": False,
                               "reason": "MISSION_ACTIVE"})
            raise ProfileError("profiles cannot be changed while a mission uses a snapshot")
        p = self.get(profile_id)
        new = copy.deepcopy(p)
        for key, value in changes.items():
            if key in ("id", "revision"):
                raise ProfileError(f"{key} cannot be edited")
            if key in ACTIVITY_FIELDS and value is not None:
                if unit is None:
                    raise ProfileError(f"{key} needs an explicit unit (Bq/cm2 or Bq/m2)")
                value = to_bq_cm2(value, unit)
            if key == "survey_method" and value not in SURVEY_METHODS:
                raise ProfileError(f"survey_method must be one of {SURVEY_METHODS}")
            new[key] = value
        new["revision"] = p.get("revision", 0) + 1
        self.history.append(copy.deepcopy(p))
        p.clear()
        p.update(new)
        self.audit.append({"op": "profile_edit", "user": user, "role": role, "accepted": True,
                           "profile": profile_id, "revision": new["revision"],
                           "changes": sorted(changes), "unit": unit})
        return p

    def change_unit(self, *_args, **_kw):
        raise ProfileError("a unit change needs an intentional re-entry of the value with its unit")


def decision_parameters(profile: dict, n_decision_cells: int) -> dict:
    """alpha/beta of the two-stage rule (MODEL.md section 3, R3) for a mission.

    alpha_scan = the profile's per-decision alpha; alpha_recount = Sidak value of
    the mission allowance over n fixed decision cells (falls back to alpha_scan
    when the profile carries no allowance)."""
    from .estimator import sidak_alpha
    a_scan = profile["alpha_per_decision"]
    beta = profile["beta_per_decision"]
    allow = profile.get("per_mission_false_investigation_allowance") or {}
    p_m = allow.get("probability_of_at_least_one")
    a_rec = sidak_alpha(p_m, max(1, n_decision_cells)) if p_m else a_scan
    rec = profile.get("stationary_recount_s") or {}
    return {"alpha_scan": a_scan, "alpha_recount": a_rec, "beta": beta, "kappa_scan": kappa(a_scan),
            "n_decision_cells": n_decision_cells, "mission_allowance": p_m,
            "recount_default_s": rec.get("default", 30.0), "recount_max_s": rec.get("maximum", 100.0)}
