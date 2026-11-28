"""MODEL.md revision 4 (sections 2, 3, 6): exact linear statistics, combined + per-lane cell rule, U_null window.

Evidence: calculated / simulated (synthetic coefficients).  The reference implementation analysis/radiometry/rrrad is imported
in the cross-check test only; rr_core itself never imports it."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from rr_core import estimator as est
from rr_core import linstat
from rr_core.estimator import Cal, Decider, LaneGates

import os
REPO = Path(os.environ.get("RR_REPO", Path(__file__).resolve().parents[4]))
CAL = Cal(k=1.0, b=0.5, u_k_lane=0.003, u_k_common=0.03, u_b=0.054, cov_kb=0.0, K=24.0, u_rel_K=0.15)
CAL0 = Cal(k=1.0, b=0.5, K=24.0)                      # no calibration terms: lattice evaluator


def lane_gates(lane, w, tf, U0, cal=CAL, N=None):
    w, tf = np.asarray(w, float), np.asarray(tf, float)
    z = np.zeros_like(w)
    return LaneGates(lane, w, tf, z if N is None else N[0], tf, z if N is None else N[1], U0, "t", cal)


def test_rule_constants():
    assert est.RULE == "linear-exact/combined+per-lane/0.8-0.2"
    assert est.WEIGHTED_SUM_VARIANCE == "exact_coefficients"


# ------------------------------------------------------------------ cross-check with the reference implementation
def _rr():
    sys.path.insert(0, str(REPO / "analysis" / "radiometry"))
    return pytest.importorskip("rrrad.rev3"), pytest.importorskip("rrrad.linstat")


@pytest.mark.parametrize("offsets,U0,alpha", [
    ((0.04375,), 5.0, 0.04), ((0.04375, -0.04375), 5.0, 0.04), ((0.04375, -0.04375), 33.0, 1.14e-5),
    ((0.0, 0.04375, -0.04375, 0.0), 3.3, 0.04), ((0.0,), 0.3, 1e-3)])
def test_thresholds_and_detection_limits_equal_the_reference(offsets, U0, alpha):
    R, L = _rr()
    rc = R.Cal(k=1.0, b=0.5, u_k_lane=0.003, u_k_common=0.03, u_b=0.054, cov_kb=0.0, K=24.0, u_rel_K=0.15)
    lanes = [R.cell_lane_weights(y, v=0.03) for y in offsets]
    C = R.Combined(lanes, [rc] * len(lanes), U0)
    t_ref, d_ref = C.dhash(alpha, 0.05, "gp", u_rel_K=0.15)
    dec = Decider(quantise=False)
    keys = tuple(dec._lane_key(lane_gates(i, l.w, l.t, U0)) for i, l in enumerate(lanes))
    c, t, ok, method = dec.threshold(keys, alpha)
    assert ok and method.startswith("linear-exact/gil-pelaez")
    assert t == pytest.approx(t_ref, rel=1e-6) and list(c) == pytest.approx(list(C.c), rel=1e-9)
    assert dec.limit(keys, alpha, 0.05) == pytest.approx(d_ref, rel=1e-6)
    # lane test (m = 1)
    l0 = lanes[0]
    C1 = R.Combined([l0], [rc], U0)
    assert dec.threshold((keys[0],), alpha / 5)[1] == pytest.approx(C1.threshold(alpha / 5, "gp"), rel=1e-6)


def test_lattice_evaluator_equals_the_reference_without_calibration_terms():
    R, L = _rr()
    rc = R.Cal(k=1.0, b=0.5, u_k_lane=0.0, u_k_common=0.0, u_b=0.0, cov_kb=0.0, K=24.0, u_rel_K=0.0)
    lane = R.Lane(np.array([1.0] * 7 + [0.1]), np.full(8, 0.3))
    ref = R.Combined([lane], [rc], 3.0)
    stat = ref.stat()
    t_ref = L.lattice_threshold(L.LinStat(stat.a, stat.lam, stat.mu, 0.0, span=0.1 / lane.T / 24.0), 0.04)
    cal = Cal(k=1.0, b=0.5, K=24.0)
    dec = Decider(quantise=False)
    key = dec._lane_key(lane_gates(0, lane.w, lane.t, 3.0, cal))
    _c, t, ok, method = dec.threshold((key,), 0.04)
    assert method.startswith("linear-exact/lattice") and ok
    assert t == pytest.approx(t_ref, rel=1e-9)


# ------------------------------------------------------------------ decisions, statuses, fields
def test_combine_fields_rule_and_flags():
    w, tf = [1.0, 1.0, 0.5, 0.25], [0.1] * 4
    lanes = [lane_gates(i, w, tf, 5.0, N=([0.55] * 4, [0.5] * 4)) for i in range(3)]
    d = est.combine(lanes, 0.05, 0.05)
    assert d.m == 3 and d.rule == est.RULE and d.method.startswith("linear-exact/gil-pelaez") and d.check_ok and d.status == "OK"
    assert d.alpha_comb == pytest.approx(0.04) and d.alpha_lane == pytest.approx(0.01 / 3)
    assert sum(d.c) == pytest.approx(1.0) and len(d.lanes) == 3 and {"lane", "c", "D_star", "method", "U0", "u0_window_s"} <= set(d.lanes[0])
    assert d.D_hash > d.D_star > 0 and d.detected is False
    # a clear excess in one lane flags the cell by the lane test and by the combined test
    big = [lane_gates(0, w, tf, 5.0, N=([40] * 4, [0.5] * 4))] + lanes[1:]
    d2 = est.combine(big, 0.05, 0.05)
    assert d2.detected and "lane0" in d2.flagged_by and d2.flagged_lanes == [0]


def test_no_decision_without_a_null_reference():
    g = lane_gates(0, [1.0], [1.0], None, N=([5], [5]))
    d = est.combine([g], 0.05, 0.05)
    assert d.status == "NO_DECISION_REF" and d.status_text == est.NO_DECISION_REF and d.detected is None
    assert d.D is not None and d.D_star is None and d.D_hash is None                  # the estimate exists, the decision does not


def test_no_decision_when_the_evaluator_check_fails(monkeypatch):
    monkeypatch.setattr(linstat, "CHECK_REL", -1.0)
    d = est.combine([lane_gates(0, [1.0, 0.5], [1.0, 1.0], 5.0, N=([5, 5], [5, 5]))], 0.05, 0.05, decider=Decider())
    assert d.status == "NO_DECISION_EVAL" and d.status_text == est.NO_DECISION_EVAL and d.detected is None


def test_low_count_variance_is_not_n_plus_one():
    g = lane_gates(0, [1.0, 0.5], [1.0, 1.0], 5.0, N=([0, 0], [0, 0]))
    e = est._lane_estimate(g)
    lam0 = (CAL.k * 5.0 + CAL.b) * np.array([1.0, 1.0])
    assert e["v_stat_r"] == pytest.approx(np.dot(np.array([1.0, 0.5]) ** 2, lam0) / 1.5 ** 2 + CAL.k ** 2 * 5.0 * 1.25 / 1.5 ** 2)


def test_cache_is_order_independent_and_hits_repeat_patterns():
    w, tf = [1.0, 0.5, 0.25], [0.1, 0.1, 0.0999]
    a = [lane_gates(0, w, tf, 5.003), lane_gates(1, w, tf, 5.004)]
    b = [lane_gates(0, w, [0.1, 0.1, 0.1], 5.0), lane_gates(1, w, [0.1, 0.1, 0.1], 5.001)]
    d1, d2 = Decider(), Decider()
    r1 = [est.combine(a, 0.05, 0.05, decider=d1).D_hash, est.combine(b, 0.05, 0.05, decider=d1).D_hash]
    r2 = [est.combine(b, 0.05, 0.05, decider=d2).D_hash, est.combine(a, 0.05, 0.05, decider=d2).D_hash]
    assert r1[0] == r2[1] and r1[1] == r2[0]                                         # exact keys: order independent
    assert r1[0] != r1[1] and d1.stats["limit_computed"] == 2                        # rev 5: no quantisation of the recorded result
    dq = Decider(quantise=True)                                                      # provisional (live) cache only
    q = [est.combine(a, 0.05, 0.05, decider=dq).D_hash, est.combine(b, 0.05, 0.05, decider=dq).D_hash]
    assert q[0] == q[1] and dq.stats["limit_computed"] == 1


def test_evaluation_cost_per_cell_is_reported(capsys):
    """Not an assertion of speed: prints the per-cell cost on this machine (cold cache, 4 lanes, 20 gates each)."""
    import time
    rng = np.random.default_rng(1)
    t0 = time.perf_counter()
    for k in range(10):
        lanes = [lane_gates(i, rng.choice([1.0, 0.5, 0.25, 0.15], 20), np.full(20, 0.1), 5.0 * (1 + 0.1 * k)) for i in range(4)]
        d = est.combine(lanes, 0.05, 0.05, decider=Decider())
        _ = d.D_hash
    dt = (time.perf_counter() - t0) / 10
    print(f"cold-cache cost per 4-lane cell (threshold + 4 lane thresholds + D#): {dt * 1e3:.1f} ms")
    assert dt < 2.0


# ------------------------------------------------------------------ Monte Carlo: clean-cell false alarm of the whole rule
MC_SEED, MC_N, MC_ALPHA = 20261127, 400_000, 0.05


def cell_false_alarm(m, cal, U, w, tf, seed=MC_SEED, n=MC_N, with_cal_noise=True):
    """P(flag) of the combined + per-lane rule on a clean cell: m lanes with gate weights w and live times tf,
    true null reference rate U (= U_null), calibration errors drawn from the declared u(k) (lane and common), u(b)."""
    rng = np.random.default_rng(seed)
    w, tf = np.asarray(w, float), np.asarray(tf, float)
    G = w.size
    dec = Decider(quantise=False)
    gl = [lane_gates(i, w, tf, U, cal) for i in range(m)]
    keys = tuple(dec._lane_key(g) for g in gl)
    c, t_c, _ok, _m = dec.threshold(keys, 0.8 * MC_ALPHA)
    t_l = dec.threshold((keys[0],), 0.2 * MC_ALPHA / m)[1]
    T = float(np.dot(w, tf))
    common = rng.normal(0.0, cal.u_k_common, n) if with_cal_noise else 0.0
    S = np.zeros(n)
    lane_hit = np.zeros(n, bool)
    for i in range(m):
        NF = (rng.poisson((cal.k * U + cal.b) * tf, (n, G)) * w).sum(1)
        NU = (rng.poisson(U * tf, (n, G)) * w).sum(1)
        err = (rng.normal(0.0, cal.u_k_lane, n) * U + rng.normal(0.0, cal.u_b, n)) if with_cal_noise else 0.0
        r = NF / T - cal.k * NU / T - cal.b + err + common * U
        S += c[i] * r / cal.K
        lane_hit |= (r / cal.K) > t_l
    return float(np.mean((S > t_c) | lane_hit))


CASES = {
    "calibration terms, U=5": (CAL, 5.0, [1.0, 0.75, 0.5, 0.25, 0.15, 1.0, 1.0, 0.5], np.full(8, 0.1)),
    "low counts, calibration terms": (CAL, 1.0, [1.0, 1.0, 0.5, 0.25], np.full(4, 0.1)),
    "former xfail case, no calibration terms (lattice)": (CAL0, 3.0, [1.0] * 7 + [0.1], np.full(8, 0.3)),
}


@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("m", [1, 2, 4])
def test_cell_false_alarm_not_above_alpha(m, case):
    """Tolerance: observed fraction <= alpha + 4 binomial SE (n = 400 000, seed 20261127: 4 SE = 0.0014).  The 'former xfail'
    case is the revision-3 failure (achieved/nominal 1.160 for m = 2, 1.239 for m = 4); it must now hold."""
    cal, U, w, tf = CASES[case]
    f = cell_false_alarm(m, cal, U, w, tf, with_cal_noise=cal is not CAL0)
    se = math.sqrt(MC_ALPHA * (1 - MC_ALPHA) / MC_N)
    print(f"m={m} {case}: cell false alarm {f:.5f}, achieved/nominal {f / MC_ALPHA:.3f}")
    assert f <= MC_ALPHA + 4 * se
