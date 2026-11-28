"""U_null precision and the predictive threshold (rrrad.unull).  Exact calculations, deterministic."""
import numpy as np
import pytest

from rrrad import rev3 as R
from rrrad import unull as N

CASE = N.LaneCase(R.Lane(np.array([1.0]), np.array([1.0])), R.BETA_CAL, 1.0)   # one lane, 1 s, weights 1
U = 3.32                                                                       # 0.1 uSv/h equivalent
A_MIS = 1.14e-5


def test_plugin_inflates_with_few_window_counts_and_converges():
    r25 = N.achieved(CASE, U, 25, A_MIS, "plugin")
    r1600 = N.achieved(CASE, U, 1600, A_MIS, "plugin")
    assert r25 > 2.0 and r1600 < 1.03 and r25 > N.achieved(CASE, U, 100, A_MIS, "plugin") > r1600


def test_predictive_threshold_holds_alpha_with_a_short_window():
    for a in (0.05, 1e-3, A_MIS):
        assert N.achieved(CASE, U, 100, a, "predictive") <= 1.03
    assert N.achieved(CASE, U, 25, A_MIS, "predictive") <= 1.10


def test_upper_bound_rule_is_conservative():
    assert N.achieved(CASE, U, 100, 1e-3, "upper") <= 1.0


def test_fast_evaluator_agrees_with_direct_sum():
    c = N.LaneCase(R.Lane(np.array([1.0]), np.array([30.0])), R.BETA_CAL, 1.0)
    for rule in ("plugin", "predictive"):
        f = N.achieved_fast(c, 33.2, 200, 1e-3, rule)
        d = N.achieved(c, 33.2, 200, 1e-3, rule)
        assert f == pytest.approx(d, rel=5e-3)


def test_formula_is_the_right_order_of_magnitude():
    g = N.variance_elasticity(CASE, U)
    assert 0.8 < g < 1.2
    n = N.n_ref_formula(A_MIS, g, 1.10)
    # exact plug-in ratio at the formula's N is close to 1.10 (formula is second order)
    assert 1.0 < N.achieved(CASE, U, n, A_MIS, "plugin") < 1.15


def test_biased_low_window_inflates_and_biased_high_is_conservative():
    lo = N.achieved_fast(CASE, U, 3200, A_MIS, "predictive", rho=0.95)
    hi = N.achieved_fast(CASE, U, 3200, A_MIS, "predictive", rho=1.05)
    assert lo > 1.05 and hi < 1.0


def test_gradient_bias_geometry():
    assert N.gradient_bias(0.2, L_window_m=2.0, mode="centred") == pytest.approx(0.0)
    assert N.gradient_bias(0.2, L_window_m=2.0, mode="past") == pytest.approx(-0.2)


def test_realistic_footprint_behaves_like_weights_one():
    real = N.LaneCase(R.cell_lane_weights(0.0, v=0.10), R.BETA_CAL, 0.05)
    a = N.achieved_fast(real, 33.2, 50, A_MIS, "predictive")
    b = N.achieved_fast(N.LaneCase(R.Lane(np.array([1.0]), np.array([1.0])), R.BETA_CAL, 1.0), 33.2, 50, A_MIS, "predictive")
    assert abs(a - b) < 0.02 and a <= b + 1e-3
