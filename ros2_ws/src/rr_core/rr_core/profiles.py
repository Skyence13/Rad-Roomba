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
                       goal=None, alpha=0.05, beta=0.05, speed_mps=None, speed_tol=0.0, standoff_mm=None, require_standoff=False):
        """(ok, reason).  Reference-rate range with the R7 cap, head temperature, speed of the member gates (pose interval),
        standoff (descriptor value; nominal until measured), setup_id where given (review M7)."""
        env = self.envelope
        rr = env.get("reference_rate_cps") or {}
        if rr and not (rr.get("min", 0.0) <= U <= rr.get("max", float("inf"))):
            return False, "reference rate outside qualified range"
        if goal is not None and u_k_floor(U, self.cal(lane, channel), alpha, beta) >= goal:
            return False, "sensitivity insufficient - reference rate above qualified range"
        tr = env.get("head_temperature_C") or {}
        if tr and head_c is not None and not (tr.get("min", -1e9) <= head_c <= tr.get("max", 1e9)):
            return False, "head temperature outside qualified range"
        sp = env.get("speed_m_s") or {}
        if sp and speed_mps is not None and not (sp.get("min", 0.0) - speed_tol <= speed_mps <= sp.get("max", 1e9) + speed_tol):
            return False, f"speed {speed_mps:.4f} m/s outside the calibrated range"
        so = env.get("standoff_mm") or {}
        if so and standoff_mm is not None and not (so.get("min", -1e9) <= standoff_mm <= so.get("max", 1e9)):
            return False, "standoff outside the calibrated range"
        if so and standoff_mm is None and require_standoff:
            return False, "standoff unknown"
        es = env.get("setup_id")
        if setup_id is not None and es and es != setup_id:
            return False, "setup_id differs from the calibration"
        return True, ""

    @property
    def identity(self) -> dict:
        """MODEL.md rev 5 section 1: head serial, electronics revision, firmware, setup_id and the per-board cal_id the
        record is bound to (record member `identity`; the demonstration record has none)."""
        return dict(self.record.get("identity") or {})

    def summary(self) -> dict:
        return {"calibration_id": self.calibration_id, "sha256": self.sha256,
                "synthetic": self.synthetic, "field_use_approved": self.field_use_approved,
                "identity": self.identity or None, "cov_FU_assumed": self.cov_FU_assumed,
                "u0_evaluation_in_record": self.u0_evaluation,
                "u0_evaluation_used": "MODEL.md rev 5 section 3 (two reference sub-windows, larger mean, predictive threshold); the record's u0_evaluation is not used",
                "validity_envelope": self.envelope}


IDENTITY_FIELDS = (("head_serial", "head_id"), ("electronics_revision", "electronics_revision"), ("firmware", "firmware"),
                   ("setup_id", "setup_id"), ("cal_id", "cal_id"))
DEMONSTRATION_BANNER = ("DEMONSTRATION CALIBRATION BINDING - the calibration's head identity was NOT checked against the attached "
                        "head; synthetic coefficients; never for a survey or a release decision")


class CalibrationStore:
    """Robot-side calibration registry; `resolve` is the head-link calibration check (MODEL.md rev 5 section 1, review C2).

    strict (default): the record named by the registry must carry an `identity` that equals the attached head's serial
    (HELLO head_id), electronics revision (descriptor), firmware (HELLO), setup_id (HELLO) and, where the head reports
    one, the per-board cal_id (STATUS identity); otherwise CALIBRATION_IDENTITY_MISMATCH and no session is opened.
    demonstration=True: an explicit, loudly marked mode for the synthetic demonstration calibration: the identity is
    not checked, the binding says so and every product carries the DEMONSTRATION banner."""

    def __init__(self, calibrations=(), strict_setup: bool = True, demonstration: bool = False):
        self.by_id = {c.calibration_id: c for c in calibrations}
        self.strict_setup = strict_setup and not demonstration
        self.demonstration = bool(demonstration)
        if self.demonstration:
            import sys
            print("WARNING: " + DEMONSTRATION_BANNER, file=sys.stderr)

    def resolve(self, verified: dict, hello: dict, head_status: dict | None = None) -> dict:
        from .descriptor import DescriptorError
        cal_id = verified.get("calibration_id")
        if verified["mode"] == "BENCH" and not cal_id:
            return None
        cal = self.by_id.get(cal_id)
        if cal is None:
            raise DescriptorError("CALIBRATION_UNKNOWN", f"no local calibration record {cal_id!r}")
        if verified["mode"] == "SURVEY" and not cal.field_use_approved:
            raise DescriptorError("CALIBRATION_NOT_APPROVED", "calibration is not approved for field use")
        if verified["mode"] == "SURVEY" and self.demonstration:
            raise DescriptorError("CALIBRATION_DEMONSTRATION", "the demonstration calibration binding is refused in SURVEY mode")
        head = {"head_id": hello.get("head_id"), "firmware": hello.get("firmware"), "setup_id": hello.get("setup_id"),
                "electronics_revision": (verified.get("descriptor") or {}).get("electronics_revision", verified.get("electronics_revision")),
                "cal_id": ((head_status or {}).get("identity") or {}).get("cal_id")}
        ident = cal.identity
        mism = []
        for rec_key, head_key in IDENTITY_FIELDS:
            want = ident.get(rec_key)
            have = head.get(head_key)
            if rec_key == "cal_id" and have is None:
                continue                      # head without STATUS identity: cal_id not checkable
            if want is None or want != have:
                mism.append(f"{rec_key}: calibration {want!r} vs head {have!r}")
        env_setup = cal.envelope.get("setup_id")
        if env_setup and env_setup != hello.get("setup_id"):
            mism.append(f"validity_envelope.setup_id {env_setup!r} vs head {hello.get('setup_id')!r}")
        if mism and self.strict_setup:
            raise DescriptorError("CALIBRATION_IDENTITY_MISMATCH", "; ".join(mism))
        return {"calibration_id": cal.calibration_id, "sha256": cal.sha256,
                "field_use_approved": cal.field_use_approved, "synthetic": cal.synthetic,
                "identity_match": not mism, "identity_mismatches": mism, "head_identity": head,
                "demonstration": bool(mism) and self.demonstration,
                "binding_mode": "STRICT" if self.strict_setup else "DEMONSTRATION",
                "setup_match": (env_setup == hello.get("setup_id")) if env_setup else None,
                "notice": DEMONSTRATION_BANNER if (mism and self.demonstration) else None}


# -------------------------------------------------------------------- profiles
REVIEW_QUEUE_POLICIES = ("ALARM_ONLY", "ALL_UNRESOLVED")     # contract survey_methods.review_queue_policy


def review_queue_policy(profile: dict) -> str:
    """Site-profile setting (owner decision 2026-11-27).  Absent -> ALARM_ONLY (contract default).
      ALARM_ONLY      only cells whose statistic exceeds the decision threshold at alpha_scan are flagged
                      and queued; non-alarming cells with D# above the goal are 'insufficient sensitivity'
                      on the map / in the report, not queued.
      ALL_UNRESOLVED  every cell that cannot be cleared at the investigation level is queued (pre-2026-11-27)."""
    v = profile.get("review_queue_policy") or "ALARM_ONLY"
    if v not in REVIEW_QUEUE_POLICIES:
        raise ProfileError(f"review_queue_policy must be one of {REVIEW_QUEUE_POLICIES}, not {v!r}")
    return v


REQUIRED_FOR_DECISION = ("decision_class", "investigation_level_Bq_cm2", "detection_goal_Bq_cm2",
                         "alpha_per_decision", "beta_per_decision", "head_calibration_id")
ACTIVITY_FIELDS = ("investigation_level_Bq_cm2", "site_reported_comparison_Bq_cm2", "detection_goal_Bq_cm2")


class ProfileStore:
    """Versioned site profiles with role-checked, audited edits."""

    def __init__(self, document: dict):
        if document.get("surface_activity_unit") != "Bq/cm2":
            raise ProfileError("profile document must state surface_activity_unit Bq/cm2")
        self.document = copy.deepcopy(document)
        for prof in self.document.get("profiles", []):          # contract default when the field is absent
            prof["review_queue_policy"] = review_queue_policy(prof)
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
        p["review_queue_policy"] = review_queue_policy(p)          # explicit in the mission snapshot
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
            "review_queue_policy": review_queue_policy(profile), "alpha_queue": a_scan,
            "n_decision_cells": n_decision_cells, "mission_allowance": p_m,
            "recount_default_s": rec.get("default", 30.0), "recount_max_s": rec.get("maximum", 100.0)}
