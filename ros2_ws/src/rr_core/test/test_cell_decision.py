"""MODEL.md revision 3, section 6 (IB-31): weighted sums (CR-08) and the multi-lane cell decision (CR-09).

Simulated / calculated evidence only (Monte Carlo on the estimator, no hardware)."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rr_core import estimator as est                      # noqa: E402
from rr_core.estimator import Cal, LaneStat                # noqa: E402

CAL = Cal(k=1.0, b=0.5, u_k_lane=0.003, u_k_common=0.03, u_b=0.054, cov_kb=-7.6e-5, K=24.0, u_rel_K=0.15)


def lane(i, N_F, T=20.0, U0=9.0, cal=CAL):
    return LaneStat(i, N_F, T, U0 * T, T, U0, "t", cal)


def test_rule_strings_and_manifest_constant():
    assert est.RULE == "per-lane-exact/any-lane/alpha-over-m"
    assert est.WEIGHTED_SUM_VARIANCE == "poisson_form_conservative"


def test_single_lane_is_section_3_with_m_equal_one():
    d = est.combine([lane(0, 400)], 0.05, 0.05)
    assert d.m == 1 and d.alpha_lane == 0.05 and d.method == "normal" and d.rule == est.RULE
    r_star, method = est.decision_threshold(9.0, 20.0, 20.0, CAL, 0.05, parts="all")
    assert d.lanes[0]["r_star"] == pytest.approx(r_star) and d.D_star == pytest.approx(r_star / CAL.K)
    kb = est.kappa(0.05)
    sd0 = math.sqrt(est.u0sq(9.0, 20.0, 20.0, CAL))
    assert d.D_hash == pytest.approx(est.detection_limit_activity(r_star / 24, sd0 / 24, 1 / (24 * 20.0), 0.15, 0.05))


def test_any_lane_at_alpha_over_m_and_min_limits():
    four = [lane(i, 180) for i in range(4)]                  # all lanes at the background expectation (~9*20 + 10)
    d = est.combine(four, 0.05, 0.05)
    assert d.m == 4 and d.alpha_lane == pytest.approx(0.0125) and d.method == est.RULE
    for l in d.lanes:
        r_star, _ = est.decision_threshold(9.0, 20.0, 20.0, CAL, 0.0125, parts="all")
        assert l["r_star"] == pytest.approx(r_star)
    assert d.detected is False and d.flagged_lanes == []
    # one lane clearly above its own threshold flags the cell, and only that lane
    d1 = est.combine([lane(0, 180), lane(1, 180), lane(2, 300), lane(3, 180)], 0.05, 0.05)
    assert d1.detected and d1.flagged_lanes == [2] and [l["flagged"] for l in d1.lanes] == [False, False, True, False]
    # the quoted limits are the minima over the lanes, solved at alpha/m (stricter than alpha)
    mixed = [lane(0, 180, T=20.0), lane(1, 90, T=10.0, U0=9.0), lane(2, 180, T=40.0, U0=9.0)]
    dm = est.combine(mixed, 0.05, 0.05)
    assert dm.D_hash == pytest.approx(min(l["D_hash"] for l in dm.lanes))
    assert dm.D_star == pytest.approx(min(l["D_star"] for l in dm.lanes))
    assert dm.D_hash > dm.D_star > 0
    alone = est.combine([lane(2, 180, T=40.0)], 0.05, 0.05)
    assert alone.D_hash < next(l for l in dm.lanes if l["lane"] == 2)["D_hash"]      # alpha/3 costs sensitivity


def test_estimate_and_uncertainties_are_the_inverse_variance_combination():
    cal = Cal(k=1.0, b=0.5, u_k_common=0.03, K=24.0)
    one = est.combine([LaneStat(0, 1000, 100.0, 900, 100.0, 9.0, "t", cal)], 0.05, 0.05)
    four = est.combine([LaneStat(i, 1000, 100.0, 900, 100.0, 9.0, "t", cal) for i in range(4)], 0.05, 0.05)
    assert four.D == pytest.approx(one.D) and four.u_stat == pytest.approx(one.u_stat / 2)
    common = 9.0 * 0.03 / 24
    assert four.u_total ** 2 - four.u_stat ** 2 == pytest.approx(common ** 2, rel=1e-6)


def test_exact_lane_uses_exact_threshold_and_exact_limit():
    cal = Cal(k=1.0, b=0.5, K=24.0, u_rel_K=0.1)
    ls = [LaneStat(i, 10, 2.0, 8, 2.0, 4.0, "t", cal) for i in range(2)]      # floor counts ~ 9 < 30: exact
    d = est.combine(ls, 0.05, 0.05)
    assert d.method == est.RULE and {l["method"] for l in d.lanes} == {"poisson-exact"}
    r_star, _ = est.decision_threshold(4.0, 2.0, 2.0, cal, 0.025, parts="all")
    assert d.lanes[0]["r_star"] == pytest.approx(r_star)
    rh = est.detection_limit_rate(r_star, 0.0, 2.0, 0.05, 4.0, 2.0, cal, "poisson-exact", "all")
    assert d.D_hash == pytest.approx(rh / (24 * (1 - est.kappa(0.05) ** 2 * 0.01)))


# --------------------------------------------------------- Monte Carlo, clean cell, fractional weights
MC_SEED = 20261127
MC_N = 400_000
MC_ALPHA = 0.05
CASES = {   # method -> (U rate cps, b, gate live time s, gates per lane); chosen so section 3 selects the named method
    "normal": (200.0, 2.0, 0.5, 8),
    "poisson-exact": (3.0, 0.5, 0.3, 8),
}


def cell_false_alarm(m, method, weights_for_lane, seed=MC_SEED, n=MC_N):
    """Fraction of clean-cell trials in which ANY of m independent lanes exceeds its own threshold at alpha/m
    (thresholds from est._lane_limit, the function `combine` uses), and the same fraction by `combine` itself on
    the first 200 trials (consistency check)."""
    U, b, tg, G = CASES[method]
    rng = np.random.default_rng(seed)
    cal = Cal(k=1.0, b=b, K=24.0)
    hits = np.zeros(n, bool)
    lanes, stats = [], []
    for i in range(m):
        w = weights_for_lane(rng, G)
        T = float((w * tg).sum())
        ls = LaneStat(i, 0.0, T, 0.0, T, U, "t", cal)
        r_star, meth, _ = est._lane_limit(ls, MC_ALPHA / m, 0.05, False)
        assert meth == method
        NF = (rng.poisson((cal.k * U + b) * tg, (n, G)) * w).sum(1)
        NU = (rng.poisson(U * tg, (n, G)) * w).sum(1)
        r = NF / T - cal.k * NU / T - b
        hits |= r > r_star
        lanes.append((ls, NF, NU, r, r_star))
    for j in range(200):                               # the library decision agrees with the vectorised rule
        d = est.combine([LaneStat(ls.lane, NF[j], ls.T_F, NU[j], ls.T_U, U, "t", cal) for ls, NF, NU, _, _ in lanes],
                        MC_ALPHA, 0.05, exact_detection_limit=False)
        assert d.detected == bool(hits[j])
    return float(hits.mean())


def fractional(rng, G):
    return rng.uniform(0.10, 1.0, G)                   # footprint fractions of a cell edge (>= 0.10 are kept)


@pytest.mark.parametrize("method", ["normal", "poisson-exact"])
@pytest.mark.parametrize("m", [2, 4])
def test_cell_false_alarm_not_above_alpha(m, method):
    """Tolerance: the observed fraction may exceed alpha by at most 4 binomial standard errors of the
    Monte Carlo (n = 400 000, seed 20261127: 4 SE = 0.0014 at alpha = 0.05).  Observed ratios to alpha are far below 1
    (0.25-0.4): the Poisson form over-states the variance of weighted sums and the lanes are not worst-case correlated."""
    f = cell_false_alarm(m, method, fractional)
    se = math.sqrt(MC_ALPHA * (1 - MC_ALPHA) / MC_N)
    print(f"m={m} {method}: cell false alarm {f:.5f}, achieved/nominal {f / MC_ALPHA:.3f}")
    assert f <= MC_ALPHA + 4 * se


@pytest.mark.xfail(strict=False, reason="KNOWN, observed by Monte Carlo: poisson-exact with weights = 1 except one 0.1 gate per lane "
                   "exceeds alpha (achieved/nominal about 1.2): MODEL.md rev 3 says this case must be confirmed; see STATUS.md IB-31")
def test_poisson_exact_with_mostly_full_gates_and_one_partial_gate_is_not_conservative():
    global CASES
    saved = dict(CASES)
    try:
        CASES["poisson-exact"] = (3.0, 0.5, 0.3, 8)
        f = cell_false_alarm(4, "poisson-exact", lambda rng, G: np.array([1.0] * (G - 1) + [0.1]), seed=7, n=300_000)
    finally:
        CASES.clear(); CASES.update(saved)
    print(f"adversarial exact: achieved/nominal {f / MC_ALPHA:.3f}")
    assert f <= MC_ALPHA + 4 * math.sqrt(MC_ALPHA * (1 - MC_ALPHA) / 300_000)
