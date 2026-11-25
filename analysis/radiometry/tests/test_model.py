"""Unit tests of rrrad.model against MODEL.md sections 2-4, including limiting cases."""
import numpy as np
import pytest

from rrrad import model as m

K95 = 1.6448536269514722


def test_kappa_and_sidak():
    assert m.kappa(0.05) == pytest.approx(K95, rel=1e-12)
    assert m.sidak_alpha(0.05, 1) == pytest.approx(0.05)
    a = m.sidak_alpha(0.05, 4480)
    assert 1 - (1 - a) ** 4480 == pytest.approx(0.05, rel=1e-9)
    assert a == pytest.approx(0.05 / 4480, rel=0.03)          # close to Bonferroni
    assert m.sidak_alpha(1e-6, 10**7) > 0                      # no cancellation
    with pytest.raises(ValueError):
        m.sidak_alpha(0.0, 10)


def test_design_text_worked_example():
    # Design 0.3 section 5: F = 8 1/s, U = 32 1/s, k = 0.25, b = 0, K = 8.
    # Counting variance (8 + 0.25^2 * 32)/t = 10/t; 0.28 Bq/cm2 at 2 s, 0.088 at 20 s.
    cal = m.Calibration(k=0.25, b=0.0, K=8.0)
    for t, expect in ((2.0, 0.28), (20.0, 0.088)):
        est = m.estimate(8 * t, t, 32 * t, t, cal)
        assert est["r"] == pytest.approx(0.0, abs=1e-12)
        assert est["u_stat_r"] ** 2 == pytest.approx(10.0 / t)
        assert est["u_stat_D"] == pytest.approx(expect, abs=0.005)
        assert est["u_total_D"] == pytest.approx(est["u_stat_D"])   # no calibration terms given


def test_estimate_terms_section2():
    cal = m.Calibration(k=0.4, b=0.3, u_k=0.02, u_b=0.05, cov_kb=-1e-4, K=20.0, u_rel_K=0.15)
    N_F, T_F, N_U, T_U = 37, 2.0, 52, 1.5
    est = m.estimate(N_F, T_F, N_U, T_U, cal)
    U = N_U / T_U
    r = N_F / T_F - 0.4 * U - 0.3
    v_stat = N_F / T_F**2 + 0.4**2 * N_U / T_U**2
    v_cal = U**2 * 0.02**2 + 0.05**2 + 2 * U * (-1e-4)
    assert est["r"] == pytest.approx(r)
    assert est["u_stat_r"] == pytest.approx(np.sqrt(v_stat))
    assert est["u_total_r"] == pytest.approx(np.sqrt(v_stat + v_cal))
    D = r / 20.0
    assert est["D"] == pytest.approx(D)
    assert est["u_total_D"] == pytest.approx(np.sqrt((v_stat + v_cal) / 400 + D**2 * 0.15**2))
    assert est["u_total_D"] > est["u_stat_D"]
    # signed values are kept
    neg = m.estimate(0, 1.0, 50, 1.0, cal)
    assert neg["r"] < 0 and neg["D"] < 0
    # optional Cov(F,U) term: -2 k Cov
    est_c = m.estimate(N_F, T_F, N_U, T_U, cal, cov_FU=1.0)
    assert est_c["u_stat_r"] ** 2 == pytest.approx(v_stat - 2 * 0.4 * 1.0)


def test_closed_form_equal_alpha_beta_matches_model_md():
    v0, T, K, ur = 7.1, 1.0, 20.0, 0.15
    rs = K95 * np.sqrt(v0)
    assert m.decision_threshold(v0) == pytest.approx(rs)
    assert m.detection_limit_rate(v0, T) == pytest.approx(2 * rs + K95**2 / T, rel=1e-12)
    expect = (2 * rs + K95**2 / T) / (K * (1 - K95**2 * ur**2))
    assert m.detection_limit_activity(v0, T, K, ur) == pytest.approx(expect, rel=1e-12)


@pytest.mark.parametrize("alpha,beta", [(0.05, 0.05), (1e-5, 0.05), (0.01, 0.1), (0.2, 0.001)])
@pytest.mark.parametrize("v0,T,K,ur", [(7.1, 1.0, 20.0, 0.0), (0.3, 30.0, 8.0, 0.15), (1e-4, 100.0, 5.0, 0.3),
                                         (400.0, 1.0, 50.0, 0.1)])
def test_closed_form_equals_numerical_solve(alpha, beta, v0, T, K, ur):
    cf = float(m.detection_limit_activity(v0, T, K, ur, alpha, beta))
    num = m.detection_limit_activity_numeric(v0, T, K, ur, alpha, beta)
    assert cf == pytest.approx(num, rel=1e-9)
    # the solution satisfies the implicit equation of MODEL.md section 3
    ystar = m.kappa(alpha) * np.sqrt(v0) / K
    rhs = ystar + m.kappa(beta) * np.sqrt(v0 / K**2 + cf / (K * T) + cf**2 * ur**2)
    assert cf == pytest.approx(rhs, rel=1e-9)
    assert float(m.detection_limit_rate(v0, T, alpha, beta)) == pytest.approx(
        m.detection_limit_rate_numeric(v0, T, alpha, beta), rel=1e-9)


def test_detection_limit_undefined_when_kappa_urel_ge_1():
    assert np.isinf(m.detection_limit_activity(1.0, 1.0, 5.0, 0.61))        # 1.645*0.61 > 1
    assert np.isinf(m.detection_limit_activity_numeric(1.0, 1.0, 5.0, 0.61))
    assert np.isfinite(m.detection_limit_activity(1.0, 1.0, 5.0, 0.60))


def test_limit_U_to_zero_is_classical_paired_blank():
    # U -> 0: no reference counts; with b measured as a blank of the same duration,
    # u(b)^2 = b/T, the result is the classical paired-blank (Currie) expression
    # r# = kappa^2/T + 2 kappa sqrt(2 b/T), i.e. in counts 2.71 + 4.65 sqrt(b T).
    b, T = 4.0, 10.0
    v0 = m.u0sq_comp(0.0, T, T, k=0.7, b=b, u_k=0.05, u_b=np.sqrt(b / T))
    assert v0 == pytest.approx(2 * b / T)
    counts = m.detection_limit_rate(v0, T) * T
    assert counts == pytest.approx(K95**2 + 2 * K95 * np.sqrt(2 * b * T), rel=1e-12)
    assert counts == pytest.approx(2.71 + 4.65 * np.sqrt(b * T), rel=2e-3)
    # U -> 0 with a well-known b: identical to the uncompensated estimator with known background
    assert m.u0sq_comp(0.0, T, T, k=0.7, b=b) == pytest.approx(m.u0sq_unc(b, T))


def test_limit_matched_reference_equals_paired_blank():
    # k = 1, b = 0, T_U = T_F, exact calibration: F - U is a paired measurement, variance 2B/T.
    B, T = 33.0, 1.0
    assert m.u0sq_comp(B, T, T, 1.0) == pytest.approx(2 * B / T)
    assert m.u0sq_comp(B, T, T, 1.0) == pytest.approx(m.u0sq_unc(B, T, B0=B, T0=T))


def test_limit_u_k_to_zero_and_long_TU():
    B, T, k = 50.0, 2.0, 0.5
    U = B / k
    full = m.u0sq_comp(U, T, T, k, 0.2, u_k=0.03 * k, u_b=0.1, cov_kb=-1e-3)
    no_cal = m.u0sq_comp(U, T, T, k, 0.2)
    assert no_cal == pytest.approx((k * U + 0.2) / T + k * k * U / T)
    assert full - no_cal == pytest.approx(U**2 * (0.03 * k) ** 2 + 0.01 - 2e-3 * U)
    # long T_U and exact calibration: the reference costs nothing -> known-background limit
    assert m.u0sq_comp(U, T, 1e12, k, 0.2) == pytest.approx(m.u0sq_unc(B + 0.2, T), rel=1e-9)
    # u(k) -> 0 continuously
    assert m.u0sq_comp(U, T, T, k, 0.2, u_k=1e-9) == pytest.approx(no_cal, rel=1e-9)


def test_wrappers_and_monotonicity():
    c = m.comp_limits(33.0, 1.0, 20.0, k=1.0, b=0.5, rel_u_k=0.03, u_rel_K=0.15)
    u = m.unc_limits(33.5, 1.0, 20.0, sigma_delta=0.0, u_rel_K=0.15)
    assert c["D_hash"] > u["D_hash"]                   # counting penalty in a uniform field
    assert c["D_star"] == pytest.approx(c["r_star"] / 20.0)
    T = np.array([1.0, 10.0, 100.0, 1e4])
    d = m.comp_limits(33.0, T, 20.0, rel_u_k=0.03)["D_hash"]
    assert np.all(np.diff(d) < 0)
    # more sensitive reference (smaller k) always helps at fixed floor photon rate
    dk = [float(m.comp_limits(33.0, 1.0, 20.0, k=k)["D_hash"]) for k in (1.0, 0.3, 0.1)]
    assert dk[0] > dk[1] > dk[2]
    # D# scales as 1/K when u_rel(K) is fixed
    assert m.comp_limits(33.0, 1.0, 40.0)["D_hash"] == pytest.approx(m.comp_limits(33.0, 1.0, 20.0)["D_hash"] / 2)


def test_highfield_floor_and_dwell():
    Bg, K, ruk = 165.0, 20.0, 0.03
    floor = float(m.highfield_floor_activity(Bg, K, ruk))
    assert floor == pytest.approx(2 * K95 * Bg * ruk / K, rel=1e-12)
    d_long = float(m.comp_limits(Bg, 1e9, K, rel_u_k=ruk)["D_hash"])
    assert d_long == pytest.approx(floor, rel=1e-6)
    f = lambda T: float(m.comp_limits(Bg, T, K, rel_u_k=ruk)["D_hash"])
    assert np.isinf(m.dwell_to_reach(0.2, f))          # floor 0.81 > 0.2: unreachable by dwell
    g = lambda T: float(m.unc_limits(3.8, T, K)["D_hash"])
    T02 = m.dwell_to_reach(0.2, g)
    assert g(T02) == pytest.approx(0.2, rel=1e-6) and 3.0 < T02 < 5.0


def test_breakeven_sigma_delta():
    Bg, T, k, ruk, b = 33.0, 1.0, 1.0, 0.03, 0.5
    s = float(m.breakeven_sigma_delta(Bg, T, k=k, b=b, rel_u_k=ruk))
    vc = m.comp_limits(Bg, T, 1.0, k=k, b=b, rel_u_k=ruk)["u0sq"]
    vu = m.unc_limits(Bg + b, T, 1.0, sigma_delta=s)["u0sq"]
    assert vc == pytest.approx(vu, rel=1e-12)
    # closed form with b = 0 and long T0: sqrt(u_k^2 + k/(B T_U))
    assert float(m.breakeven_sigma_delta(Bg, T, k=k, rel_u_k=ruk)) == pytest.approx(np.sqrt(ruk**2 + k / (Bg * T)))
    # a short background count can make the uncompensated estimator worse even at sigma = 0
    assert float(m.breakeven_sigma_delta(Bg, 10.0, k=0.1, T0=1.0)) == 0.0


def test_broadcasting():
    B = np.array([[1.0], [10.0], [100.0]])
    T = np.array([1.0, 10.0])
    out = m.comp_limits(B, T, 20.0, rel_u_k=0.02, u_rel_K=0.1)
    assert out["D_hash"].shape == (3, 2)
    assert np.all(out["D_hash"] > out["D_star"])
