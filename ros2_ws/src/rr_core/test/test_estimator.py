"""MODEL.md rev 2 estimator; cross-test against analysis/radiometry/rrrad (calculated).
Traces: RQ-021, RQ-022, RQ-023, RQ-035; VT-020, VT-021, VT-022."""
import math, sys
import numpy as np
import pytest
from rr_core import estimator as est
from rr_core.estimator import Cal, LaneStat
from rr_core.profiles import Calibration, ProfileStore, ProfileError, to_bq_cm2, DATA, decision_parameters

CAL = Cal(k=1.0, b=0.5, u_k_lane=0.003, u_k_common=0.03, u_b=0.054, cov_kb=-7.6e-5, K=24.0, u_rel_K=0.15)


def test_net_estimate_matches_model_equations():
    e = est.net_estimate(40, 2.0, 30, 2.0, CAL)
    F, U = 20.0, 15.0
    assert e["r"] == pytest.approx(F - 1.0 * U - 0.5)
    v_stat = 40 / 4 + 30 / 4
    v_cal = U**2 * (0.003**2 + 0.03**2) + 0.054**2 + 2 * U * -7.6e-5
    assert e["u_stat_D"] == pytest.approx(math.sqrt(v_stat) / 24)
    assert e["u_total_D"] == pytest.approx(math.sqrt((v_stat + v_cal) / 24**2 + e["D"]**2 * 0.15**2))
    neg = est.net_estimate(0, 2.0, 30, 2.0, CAL)
    assert neg["r"] < 0 and neg["v_stat_r"] > 30 / 4        # signed; N+1 rule for zero counts


def test_cross_check_with_rrrad(repo):
    sys.path.insert(0, str(repo / "analysis" / "radiometry"))
    rr = pytest.importorskip("rrrad.model")
    c = rr.Calibration(k=CAL.k, b=CAL.b, u_k=CAL.u_k, u_b=CAL.u_b, cov_kb=CAL.cov_kb, K=CAL.K, u_rel_K=CAL.u_rel_K)
    ref = rr.estimate(40, 2.0, 30, 2.0, c)
    mine = est.net_estimate(40, 2.0, 30, 2.0, CAL)
    assert mine["D"] == pytest.approx(float(ref["D"]))
    assert mine["u_total_D"] == pytest.approx(float(ref["u_total_D"]))
    for U0, T in ((4.0, 2.3), (40.0, 10.0), (120.0, 30.0)):
        v0 = est.u0sq(U0, T, T, CAL)
        assert v0 == pytest.approx(float(rr.u0sq_comp(U0, T, T, CAL.k, CAL.b, CAL.u_k, CAL.u_b, CAL.cov_kb)))
        for a, b in ((0.05, 0.05), (0.01, 0.05)):
            rs, _ = est.decision_threshold(U0, T, T, CAL, a, force="normal")
            assert rs == pytest.approx(float(rr.decision_threshold(v0, a)))
            assert est.detection_limit_rate(rs, math.sqrt(v0), T, b) == pytest.approx(float(rr.detection_limit_rate(v0, T, a, b)))
            assert est.detection_limit_activity(rs / CAL.K, math.sqrt(v0) / CAL.K, 1 / (CAL.K * T), CAL.u_rel_K, b) == \
                pytest.approx(float(rr.detection_limit_activity(v0, T, CAL.K, CAL.u_rel_K, a, b)))
    assert est.sidak_alpha(0.05, 4480) == pytest.approx(float(rr.sidak_alpha(0.05, 4480)))
    assert est.sidak_alpha(0.05, 4480) == pytest.approx(1.14493e-05, rel=1e-4)   # demo profile example


@pytest.mark.parametrize("alpha", [0.05, 1e-3, 1.1e-5])
def test_exact_threshold_controls_false_alarm(alpha):
    cal = Cal(k=1.0, b=0.5, K=24.0)
    U0, T = 4.0, 2.3
    rs, method = est.decision_threshold(U0, T, T, cal, alpha)
    assert method == "poisson-exact"
    r, p = est._null_atoms(U0, T, T, cal)
    assert p[r > rs].sum() <= alpha * (1 + 1e-6)
    rn, _ = est.decision_threshold(U0, T, T, cal, alpha, force="normal")
    if alpha < 1e-3:
        assert rs > rn                           # normal quantile is anti-conservative at small alpha
    # Monte Carlo confirmation at alpha = 0.05
    if alpha == 0.05:
        rng = np.random.default_rng(5)
        nf = rng.poisson((cal.k * U0 + cal.b) * T, 400000); nu = rng.poisson(U0 * T, 400000)
        assert ((nf / T - nu / T - cal.b) > rs).mean() <= 0.052
    # detection limit: power 1-beta at r#
    rh = est.detection_limit_rate(rs, 0, T, 0.05, U0, T, cal, "poisson-exact")
    r2, p2 = est._null_atoms(U0, T, T, cal, rho=rh)
    assert p2[r2 > rs].sum() == pytest.approx(0.95, abs=0.01)


def test_exact_decision_approaches_the_closed_form_at_large_counts():
    """Revision 4: the exact threshold and detection limit agree with the section 3 closed forms (planning
    approximations) to a few percent when counts are large; revision 6: a single lane (m = 1) is ONE test at alpha."""
    cal = Cal(k=1.0, b=0.5, K=24.0, u_rel_K=0.15)
    d = est.combine([LaneStat(0, 2020, 20.0, 2000, 20.0, 100.0, "t", cal)], 0.05, 0.05)
    assert d.m == 1 and d.method.startswith("linear-exact/") and d.rule == est.RULE and d.check_ok
    assert d.alpha_comb == pytest.approx(0.05) and d.alpha_lane == pytest.approx(0.05)
    kap = est.kappa(0.05)
    v0 = (100.5) / 20 + 100 / 20
    assert d.D_star == pytest.approx(kap * math.sqrt(v0) / 24, rel=0.03)
    kb = est.kappa(0.05)
    assert d.D_hash == pytest.approx((kap * math.sqrt(v0) + kb * math.sqrt(v0) + kb ** 2 / 40) / (24 * (1 - kb ** 2 * 0.15 ** 2)), rel=0.05)


def test_lane_combination_keeps_common_terms():
    cal = Cal(k=1.0, b=0.5, u_k_common=0.03, K=24.0)
    one = est.combine([LaneStat(0, 1000, 100.0, 900, 100.0, 9.0, "t", cal)], 0.05, 0.05)
    four = est.combine([LaneStat(i, 1000, 100.0, 900, 100.0, 9.0, "t", cal) for i in range(4)], 0.05, 0.05)
    assert four.u_stat == pytest.approx(one.u_stat / 2)
    common = 9.0 * 0.03 / 24
    assert four.u_total**2 - four.u_stat**2 == pytest.approx(common**2, rel=1e-6)   # not averaged down
    assert one.u_total**2 - one.u_stat**2 == pytest.approx(common**2, rel=1e-6)


def test_demo_calibration_and_envelope():
    cal = Calibration.load(DATA / "demo_calibration.json")
    assert cal.field_use_approved is False and cal.synthetic is True
    c = cal.cal(1, "beta")
    assert c.k == 1.0293 and c.u_k == pytest.approx(0.03103, rel=2e-3)
    assert cal.check_envelope(0, "beta", 4.0, 10.0)[0]
    assert not cal.check_envelope(0, "beta", 400.0, 10.0)[0]
    assert not cal.check_envelope(0, "beta", 4.0, 60.0)[0]
    ok, why = cal.check_envelope(0, "beta", 120.0, 10.0, goal=0.2)       # R7 cap from u(k)
    assert not ok and "above qualified range" in why


def test_units_and_profile_permissions():
    assert to_bq_cm2(4, "Bq/m2") == pytest.approx(0.0004)
    with pytest.raises(ProfileError):
        to_bq_cm2(4, "Bq/dm2")
    store = ProfileStore.load(DATA / "demo_site_profile_ore.json")
    cal = Calibration.load(DATA / "demo_calibration.json")
    snap = store.snapshot("ore-floor-demo-synthetic", cal, "COMMISSIONING")
    assert snap["field_use_approved"] is False and snap["investigation_level_Bq_cm2"] == 0.3
    with pytest.raises(ProfileError):       # synthetic profile cannot be used for an operational survey
        store.snapshot("ore-floor-demo-synthetic", cal, "SURVEY")
    with pytest.raises(ProfileError):       # yellowcake stays present but unconfigured
        store.snapshot("uranium-concentrate-floor-template", cal, "COMMISSIONING")
    with pytest.raises(ProfileError):
        store.edit("ore-floor-demo-synthetic", {"investigation_level_Bq_cm2": 0.2}, "op1", "operator", unit="Bq/cm2")
    with pytest.raises(ProfileError):       # unit must be explicit
        store.edit("ore-floor-demo-synthetic", {"investigation_level_Bq_cm2": 0.2}, "rp1", "rp")
    with pytest.raises(ProfileError):       # not mid-run
        store.edit("ore-floor-demo-synthetic", {"investigation_level_Bq_cm2": 0.2}, "rp1", "rp", True, "Bq/cm2")
    with pytest.raises(ProfileError):
        store.change_unit("ore-floor-demo-synthetic", "Bq/m2")
    p = store.edit("ore-floor-demo-synthetic", {"investigation_level_Bq_cm2": 2500}, "rp1", "rp", unit="Bq/m2")
    assert p["investigation_level_Bq_cm2"] == pytest.approx(0.25) and p["revision"] == 2
    assert snap["investigation_level_Bq_cm2"] == 0.3 and store.history[0]["revision"] == 1
    assert [a["accepted"] for a in store.audit] == [False, False, True]
    prm = decision_parameters(snap, 4480)
    assert prm["alpha_scan"] == 0.05 and prm["alpha_recount"] == pytest.approx(1.14493e-05, rel=1e-4)
