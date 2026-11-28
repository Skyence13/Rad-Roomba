#!/usr/bin/env python3
"""Step 5 - synthetic calibration record and ore site profile for the robot simulator.

Both files are SYNTHETIC, carry field_use_approved = false and exist to exercise the code path
(MODEL.md section 7). The transfer coefficients come from a simulated clean-floor fit so that
u(k), u(b) and cov(k,b) are mutually consistent."""
import json

import numpy as np

from common import (ALPHA, ALPHA_SIDAK, B_OFF_ALPHA, B_OFF_BETA, BETA, K_ALPHA_NOM, K_NOM, LAYOUT, MISSION_ALLOWANCE, ROOT,
                    S_ALPHA, S_BETA, SEED, U_REL_K, U_REL_K_ALPHA)

rng = np.random.default_rng(SEED + 5)
U_POINTS = np.geomspace(2.0, 150.0, 12)       # reference rates of the simulated clean-floor runs (1/s)
T_RUN = 600.0                                  # s per run
SPEC = {"beta_window": 0.03, "alpha_like": 0.10}   # assumed relative spectral-mismatch component of u(k)
TRUE = {"beta_window": dict(k=1.0, b=B_OFF_BETA, K=K_NOM, u_rel_K=U_REL_K, basis="Cl-36-equivalent (synthetic)"),
        "alpha_like": dict(k=S_ALPHA / S_BETA, b=B_OFF_ALPHA, K=K_ALPHA_NOM, u_rel_K=U_REL_K_ALPHA,
                           basis="thin natural-uranium alpha equivalent at 10 mm (synthetic)")}
LANE_K = {"beta_window": [0.97, 1.02, 1.00, 0.95], "alpha_like": [1.03, 0.98, 1.00, 0.94]}
LANE_k = [1.00, 1.03, 0.98, 1.01]


def fit_line(k_true, b_true):
    """Weighted least-squares fit F = k U + b to simulated Poisson runs; returns estimates and covariance."""
    n_u = rng.poisson(U_POINTS * T_RUN)
    n_f = rng.poisson((k_true * U_POINTS + b_true) * T_RUN)
    U, F = n_u / T_RUN, n_f / T_RUN
    var = (np.maximum(n_f, 1) + k_true**2 * np.maximum(n_u, 1)) / T_RUN**2     # effective variance incl. reference counts
    A = np.vstack([U, np.ones_like(U)]).T
    W = np.diag(1.0 / var)
    cov = np.linalg.inv(A.T @ W @ A)
    k_hat, b_hat = cov @ A.T @ W @ F
    return float(k_hat), float(b_hat), cov


def sig(x, n=4):
    return float(f"{x:.{n}g}")


lanes = []
for lane in range(4):
    classes = {}
    for cls, t in TRUE.items():
        k_hat, b_hat, cov = fit_line(t["k"] * LANE_k[lane], t["b"])
        u_fit = float(np.sqrt(cov[0, 0]))
        u_k = float(np.hypot(u_fit, SPEC[cls] * k_hat))
        classes[cls] = {
            "k": sig(k_hat, 5), "b_cps": sig(b_hat, 4), "u_k": sig(u_k), "u_b_cps": sig(float(np.sqrt(cov[1, 1]))),
            "cov_kb_cps": sig(float(cov[0, 1])),
            "u_k_components": {"fit": sig(u_fit), "spectral_mismatch_relative": SPEC[cls]},
            "K_cps_per_Bq_cm2": sig(t["K"] * LANE_K[cls][lane]), "u_rel_K": t["u_rel_K"], "K_basis": t["basis"],
        }
    lanes.append({"lane_index": lane, "classes": classes})

cal = {
    "format_version": "0.2-demo",
    "schema": "analysis/radiometry/schemas/calibration_record.schema.json",
    "document": "Rad Roomba demonstration calibration record",
    "synthetic": True,
    "field_use_approved": False,
    "notice": "SYNTHETIC DEMONSTRATION VALUES. Not measured on any detector. For the simulator and software tests only; "
              "never use for a survey, a release decision or a performance claim.",
    "calibration_id": "DEMO-CAL-SYNTH-0001",
    "identity": {
        "head_serial": "HEAD-DEMO-001",
        "electronics_revision": "bench-A",
        "firmware": "sim-1.0",
        "setup_id": "optic-test-01",
        "cal_id": "FAKE-BOARD-CAL-0",
        "synthetic": True,
        "note": "values of the emulated head (ros2_ws rr_core/data/head_descriptor_demo.json, rr_core/fakes/head.py) so that "
                "strict binding can be exercised; no real head carries them",
    },
    "generated_by": "analysis/radiometry/scripts/s5_demo_files.py (fixed seed)",
    "model": "analysis/radiometry/MODEL.md sections 1-3: r = F - k*U - b; D = r/K",
    "units": {"k": "dimensionless (floor counts per reference count)", "b_cps": "1/s", "u_k": "same as k",
              "u_b_cps": "1/s", "cov_kb_cps": "1/s", "K_cps_per_Bq_cm2": "1/s per Bq/cm2", "u_rel_K": "relative standard uncertainty"},
    "lane_order": "0-3 from the robot's left to right facing the direction of travel",
    "u0_evaluation": "smoothed_reference",
    "cov_FU_assumed": 0.0,
    "validity_envelope": {
        "setup_id": "optic-test-01",
        "reference_rate_cps": {"min": float(U_POINTS[0]), "max": float(U_POINTS[-1])},
        "head_temperature_C": {"min": 5.0, "max": 35.0},
        "standoff_mm": {"min": 8.0, "max": 12.0},
        "speed_m_s": {"min": 0.0, "max": 0.12, "basis": "qualified range of the MEASURED gate speed (pose interval); "
                      "surveys command at most max minus the speed-control tolerance (demo: 0.10 m/s commanded)"},
        "photon_field": "synthetic; ore-like spectrum assumed",
    },
    "reference_rate_ratios": {
        "values": [1.0, 1.0, 1.0, 1.0], "relative_standard_uncertainty": 0.01,
        "definition": "lane reference rate / four-lane mean reference rate in a uniform field (MODEL.md section 1, rev 5)",
        "validity": "same setup_id; synthetic"},
    "time_over_threshold_cut": {"applies_to": ["floor_beta_window", "reference"], "definition": "pulses classified alpha-like by "
                                "time over threshold are excluded from both chains (MODEL.md section 1, rev 5)",
                                "rejected_fraction_qualified_range": {"floor": [0.0, 0.05], "reference": [0.0, 0.05]},
                                "value": "synthetic"},
    "lanes": lanes,
}
(ROOT / "demo_calibration.json").write_text(json.dumps(cal, indent=2) + "\n", encoding="utf-8")

profile = {
    "format_version": "0.3-demo",
    "purpose": "SYNTHETIC demonstration site profile for the simulator. Not a site decision.",
    "synthetic": True,
    "field_use_approved": False,
    "surface_activity_unit": "Bq/cm2",
    "profiles": [
        {
            "id": "ore-floor-demo-synthetic",
            "revision": 1,
            "enabled_for_operational_surveys": False,
            "field_use_approved": False,
            "material": "Uranium ore",
            "survey_scope": "Trailer or seacan floor",
            "decision_class": "beta_window",
            "investigation_level_Bq_cm2": 0.30,
            "site_reported_comparison_Bq_cm2": 0.40,
            "detection_goal_Bq_cm2": 0.20,
            "detection_goal_acceptance": "D# strictly below the goal and calibration validity envelope satisfied (MODEL.md section 3)",
            "alpha_per_decision": ALPHA,
            "beta_per_decision": BETA,
            "per_mission_false_investigation_allowance": {
                "probability_of_at_least_one": MISSION_ALLOWANCE,
                "method": "sidak",
                "independent_decision_areas": None,
                "note": "alpha per decision = 1 - (1 - allowance)^(1/n); n is counted by the host for each mission and stored "
                        "with the result",
                "example": {"independent_decision_areas": LAYOUT.n_cells, "alpha_per_decision": float(f"{ALPHA_SIDAK:.6g}")},
            },
            "stationary_recount_s": {"default": 30.0, "maximum": 100.0},
            "scan_speed_m_s": {"commanded": 0.10, "note": "must not exceed the calibration's speed_m_s.max minus the speed-control tolerance"},
            "head_calibration_id": "DEMO-CAL-SYNTH-0001",
            "criterion_basis_and_averaging_area_cm2": None,
            "minimum_patch_shape_and_dimensions_cm": None,
            "calibration_material_and_channels": None,
            "site_procedure_and_revision": None,
            "design_entrance_gap_mm": 10,
        },
        {
            "id": "uranium-concentrate-floor-template",
            "revision": 1,
            "enabled_for_operational_surveys": False,
            "field_use_approved": False,
            "material": "Uranium concentrate (yellowcake)",
            "decision_class": None,
            "investigation_level_Bq_cm2": None,
            "site_reported_comparison_Bq_cm2": None,
            "detection_goal_Bq_cm2": None,
            "alpha_per_decision": None,
            "beta_per_decision": None,
            "per_mission_false_investigation_allowance": None,
            "head_calibration_id": None,
            "note": "Unconfigured. The site radiation-protection team supplies every value.",
        },
    ],
}
(ROOT / "demo_site_profile_ore.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
print("s5: demo files written")
