"""MODEL.md revision 3 section 6 checks (rrrad.rev3) and the linear-statistic evaluators (rrrad.linstat).

Deterministic: exact calculations, and Monte Carlo with fixed seeds where used."""
import numpy as np
import pytest
from scipy.stats import norm, poisson, skellam

from rrrad import linstat as L
from rrrad import rev3 as R


# ------------------------------------------------------------------ linstat evaluators
def test_lattice_pmf_matches_poisson_and_skellam():
    s = L.LinStat([1.0], [3.3], span=1.0)
    x = np.array([0, 3, 10, 15])
    assert L.tail_lattice(s, x) == pytest.approx(poisson.sf(x, 3.3), rel=1e-9)
    d = L.LinStat([1.0, -1.0], [30.0, 25.0], span=1.0)
    x = np.array([5, 20, 30])
    assert L.tail_lattice(d, x) == pytest.approx(skellam.sf(x, 30.0, 25.0), rel=1e-6)


def test_weighted_poisson_lattice_matches_monte_carlo():
    s = L.LinStat([1.0, 0.1], [3.0, 2.0], span=0.1)
    rng = np.random.default_rng(1)
    n = 400_000
    x = rng.poisson(3.0, n) + 0.1 * rng.poisson(2.0, n)
    for v in (5.0, 8.0):
        p = float(L.tail_lattice(s, v)[0])
        assert float(np.mean(x > v + 1e-9)) == pytest.approx(p, abs=4 * np.sqrt(p * (1 - p) / n))


def test_gil_pelaez_equals_lattice_with_gaussian_term():
    s = L.LinStat([1.0, -1.0, 0.35], [30.0, 25.0, 4.0], mu=-0.4, sig=0.7, span=0.05)
    x = np.array([-5.0, 10.0, 25.0, 33.0])
    ex = L.tail_lattice(s, x)
    assert L.tail_gp(s, x) == pytest.approx(ex, rel=1e-7, abs=1e-14)


def test_gil_pelaez_needs_a_gaussian_term():
    with pytest.raises(ValueError):
        L.tail_gp(L.LinStat([1.0], [2.0]), 3.0)


def test_saddlepoint_continuous_accurate_at_moderate_counts():
    s = L.LinStat([1.0, -1.0], [30.0, 25.0], sig=0.7, span=1.0)
    x = np.array([20.0, 30.0])
    assert L.tail_spa(s, x) == pytest.approx(L.tail_lattice(s, x), rel=2e-3)


def test_threshold_exact_and_gp_agree():
    s = L.LinStat([1.0, -1.0], [30.0, 25.0], sig=0.7, span=1.0)
    t_l = L.threshold(s, 1e-5, "lattice")
    t_g = L.threshold(s, 1e-5, "gp")
    assert t_g == pytest.approx(t_l, rel=1e-7)
    assert float(L.tail_lattice(s, t_l)[0]) == pytest.approx(1e-5, rel=1e-6)


def test_lattice_threshold_without_gaussian_is_attainable_and_conservative():
    s = L.LinStat([1.0], [3.3], span=1.0)
    t = L.lattice_threshold(s, 1e-3)
    assert poisson.sf(t, 3.3) <= 1e-3 < poisson.sf(t - 1, 3.3)


def test_two_lattice_tail_equals_monte_carlo():
    X = L.LinStat([0.5], [4.0], span=0.5)
    Y = L.LinStat([-0.013], [40.0], span=0.013)
    tl = L.two_lattice_tail(X, Y, 0.0, mu=-0.1)
    rng = np.random.default_rng(3)
    n = 400_000
    z = 0.5 * rng.poisson(4.0, n) - 0.013 * rng.poisson(40.0, n) - 0.1
    for v in (2.0, 3.5):
        p = float(tl(v)[0])
        assert float(np.mean(z > v)) == pytest.approx(p, abs=4 * np.sqrt(p * (1 - p) / n))


# ------------------------------------------------------------------ rule replica and checks of revision 3
def test_rule_threshold_normal_is_section_3_with_weighted_times():
    cal = R.BETA_CAL
    U, T = 33.2, 0.7
    v0 = (U + cal.b) / T + U / T + cal.var_lane(U) + cal.var_common(U)
    r, m = R.rule_threshold(U, T, T, cal, 0.05, "normal")
    assert m == "normal" and r == pytest.approx(norm.isf(0.05) * np.sqrt(v0))


def test_rule_threshold_exact_is_skellam_quantile_without_calibration_terms():
    cal = R.BETA_CAL.exact_cal()
    U, T = 3.3, 1.0
    r, m = R.rule_threshold(U, T, T, cal, 1e-3)
    assert m == "poisson-exact"
    n = r * T + cal.b * T                     # threshold on N_F - N_U
    assert skellam.sf(np.round(n), (U + cal.b) * T, U * T) <= 1e-3


def test_all_weights_one_with_exact_U_null_holds_alpha():
    lane = R.pattern_lane("all 1", 1.0)
    for a in (0.05, 1e-3, 1.14e-5):
        _, fa0, m = R.lane_false_alarm(lane, R.BETA_CAL, 3.32, a, "poisson-exact", None)
        assert fa0 <= a * (1 + 1e-6)


def test_reproduces_processing_engineer_adversarial_case():
    """weights 1 x 7 + 0.1, U = 3 /s, b = 0.5, 0.3 s gates, no calibration terms: the ros2_ws Monte Carlo
    reported cell achieved/nominal 1.16 (m = 2) and 1.24 (m = 4); the exact values are 1.160 and 1.239."""
    cal = R.Cal(k=1.0, b=0.5, u_k_lane=0.0, u_k_common=0.0, u_b=0.0, cov_kb=0.0)
    lane = R.Lane(np.array([1.0] * 7 + [0.1]), np.full(8, 0.3))
    p2, per2, ub2 = R.cell_any_lane_false_alarm([lane] * 2, [cal] * 2, 3.0, 0.05, span_w=0.1)
    p4, _, ub4 = R.cell_any_lane_false_alarm([lane] * 4, [cal] * 4, 3.0, 0.05, span_w=0.1)
    assert p2 / 0.05 == pytest.approx(1.160, abs=0.002)
    assert p4 / 0.05 == pytest.approx(1.239, abs=0.002)
    assert p2 <= ub2 + 1e-15 and p4 <= ub4 + 1e-15


def test_variance_overstatement_and_n_eff():
    lane = R.pattern_lane("all 0.5", 1.0)
    assert R.variance_overstatement(lane) == pytest.approx(2.0)
    assert R.n_eff(lane) == pytest.approx(2.0)          # (sum w t)^2 / sum w^2 t with sum w t = 1


def test_cell_weights_geometry():
    l = R.cell_lane_weights(0.0, v=0.10)
    assert l.T == pytest.approx(1.0, abs=0.02) and l.w.max() == pytest.approx(1.0)
    ls = R.cell_lane_weights(0.04375, v=0.10)
    assert ls.w.max() == pytest.approx(0.6, abs=0.03) and ls.w.min() >= 0.10


def test_u0_nodes_normalised_and_unbiased():
    v, p = R.u0_nodes(5.0, 40.0)
    assert p.sum() == pytest.approx(1.0) and np.dot(v, p) == pytest.approx(5.0, rel=1e-6)
    v, p = R.u0_nodes(100.0, 200.0)
    assert p.sum() == pytest.approx(1.0) and np.dot(v, p) == pytest.approx(100.0, rel=1e-6)


def test_combined_two_lane_gp_equals_exact():
    cal1, cal2 = R.BETA_CAL, R.Cal(b=0.43, K=23.3)
    l1, l2 = R.cell_lane_weights(0.04375, v=0.03), R.cell_lane_weights(-0.04375, v=0.03)
    C = R.Combined([l1, l2], [cal1, cal2], 5.0)
    st = C.stat()

    def part(l, cal, ci):
        return L.LinStat(np.concatenate((ci * l.w / l.T, -ci * l.w / l.T)), np.concatenate(((cal.k * 5 + cal.b) * l.t, 5 * l.t)),
                         -ci * cal.b, 0.0, span=ci * 0.05 / l.T)
    ex = L.two_lattice_tail(part(l1, cal1, C.c[0] / cal1.K), part(l2, cal2, C.c[1] / cal2.K), st.sig)
    for a in (0.05, 1.14e-5):
        t = L.threshold(st, a, "gp")
        assert float(ex(t)[0]) == pytest.approx(a, rel=1e-5)


def test_rev2_combination_reduces_to_one_lane():
    cal = R.Cal(u_rel_K=0.0)
    lane = R.pattern_lane("all 1", 10.0)
    ys, d, c, sd0 = R.rev2_combined([lane], [cal], 33.2, 0.05, 0.05)
    assert d == pytest.approx(R.rule_dhash(33.2, 10.0, 10.0, cal, 0.05, 0.05, "normal"), rel=1e-9)
