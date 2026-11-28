"""The null reference rate U_null and its finite precision (MODEL.md revision 4, section 3).

The decision statistic S (rrrad.rev3: one lane, or the combined statistic) has a null mean of zero
whatever the reference rate U, because the same-gate reference is subtracted; U only fixes the SHAPE of
the null distribution (its Poisson means and the calibration term U^2 u^2(k)).  The threshold is therefore
a function t*(U_null), and a noisy U_null makes the threshold noisy.  Achieved false-alarm probability:

    P_achieved = sum_n  P(N_w = n | U)  *  P(S > t*(n) | U),      N_w ~ Poisson(rho * U * T_w)

with N_w the window count (rho = response of the window's detectors relative to the tested lane; 1 for
the lane's own window).  Threshold rules compared:

* ``plugin``      t* at U0 = N_w / (rho_hat T_w)       (revision 4 as written)
* ``predictive``  t* solves  E[ P(S > t | U') ] = alpha, U' ~ Gamma(N_w + 1/2, rho_hat T_w)
                  (the Jeffreys posterior of U given the window: the threshold of the predictive
                  null distribution; the analogue of replacing z by Student's t)
* ``upper``       t* at alpha - gamma with U at the (1 - gamma) upper Poisson bound of the window,
                  gamma = alpha/10: provably P_achieved <= alpha when P(S > t | U) increases with U.

Exact evaluation: lattice convolution for the statistic at each U, the window count enumerated (small
support) or by quantile nodes.  Nothing here is a measured property of a detector.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.stats import gamma as gamma_dist
from scipy.stats import norm, poisson

from . import linstat as L
from . import rev3 as R

__all__ = ["LaneCase", "window_nodes", "posterior_nodes", "threshold_rule", "achieved", "n_ref_formula",
           "variance_elasticity", "min_n_ref", "achieved_fast", "rate_for_power", "gradient_bias"]


@dataclass
class LaneCase:
    """One decision statistic: a lane (weights, gate times) and its calibration; k = 1 (lattice)."""
    lane: R.Lane
    cal: R.Cal = R.BETA_CAL
    span_w: float = 0.05

    def tail(self, U, rho_sig=None, D=0.0):
        """Exact tail object of S at reference rate U (with activity D in Bq/cm2 over the footprints)."""
        return R.truth_tail(self.lane, self.cal, U, rho=self.cal.K * D, span_w=self.span_w)

    def null_var(self, U):
        l, c = self.lane, self.cal
        s2 = np.sum(l.w ** 2 * l.t) / l.T ** 2
        return (c.k * U + c.b) * s2 + c.k ** 2 * U * s2 + c.var_lane(U) + c.var_common(U)


def variance_elasticity(case: LaneCase, U):
    """g = d ln Var0(S) / d ln U (1 for counting-dominated, up to 2 when U^2 u^2(k) dominates)."""
    h = 1e-4
    return float((np.log(case.null_var(U * (1 + h))) - np.log(case.null_var(U * (1 - h)))) / (np.log1p(h) - np.log1p(-h)))


def n_ref_formula(alpha, g, ratio):
    """Second-order prediction of the window count needed for achieved/nominal <= ratio with the plug-in
    threshold: with delta = relative error of U_null (variance 1/N), t* moves by z g delta / 2 standard
    deviations, the tail by exp(-z^2 g delta / 2), and E[...] = exp(z^4 g^2 / (8 N))."""
    z = norm.isf(alpha)
    return float(z ** 4 * g ** 2 / (8.0 * np.log(ratio)))


def window_nodes(mu, max_enum=200, n_quant=60):
    """Support (or equal-probability quantile nodes with conditional means) of N_w ~ Poisson(mu)."""
    lo, hi = int(poisson.ppf(1e-12, mu)), int(poisson.isf(1e-12, mu)) + 1
    n = np.arange(lo, hi + 1)
    p = poisson.pmf(n, mu)
    p /= p.sum()
    if n.size <= max_enum:
        return n.astype(float), p
    c = np.cumsum(p)
    idx = np.searchsorted(c, np.linspace(0, 1, n_quant + 1)[1:-1])
    groups = [g for g in np.split(np.arange(n.size), idx) if p[g].sum() > 0]
    return np.array([np.dot(n[g], p[g]) / p[g].sum() for g in groups]), np.array([p[g].sum() for g in groups])


def posterior_nodes(n_w, T_w, k=12):
    """Gauss-Legendre-in-probability nodes of the Jeffreys posterior Gamma(n_w + 1/2, scale 1/T_w) of U."""
    x, w = np.polynomial.legendre.leggauss(k)
    q = 0.5 * (x + 1.0)
    return gamma_dist.ppf(q, n_w + 0.5, scale=1.0 / T_w), 0.5 * w


def _root(fun, lo, hi, alpha):
    while fun(hi) > alpha:
        hi = hi + (hi - lo)
    while fun(lo) < alpha:
        lo = lo - (hi - lo)
    return float(brentq(lambda t: fun(t) - alpha, lo, hi, xtol=1e-12 * max(1.0, abs(hi)), rtol=1e-10))


def threshold_rule(case: LaneCase, n_w, T_w, alpha, rule="plugin", n_post=12, _cache=None):
    """t* from a window of n_w counts over live time T_w (already divided by rho_hat)."""
    U0 = max(n_w, 0.5) / T_w
    sd = np.sqrt(case.null_var(U0))
    if rule == "plugin":
        tl = case.tail(U0)
        return _root(lambda t: float(tl(t)[0]), 0.0, 8 * sd, alpha)
    if rule == "predictive":
        us, ws = posterior_nodes(n_w, T_w, n_post)
        tls = [case.tail(u) for u in us]
        return _root(lambda t: float(sum(w * tl(t)[0] for w, tl in zip(ws, tls))), 0.0, 8 * sd, alpha)
    if rule == "upper":
        g = alpha / 10.0
        Uup = gamma_dist.isf(g, n_w + 1.0, scale=1.0 / T_w)        # exact Poisson upper bound (Garwood)
        tl = case.tail(Uup)
        return _root(lambda t: float(tl(t)[0]), 0.0, 8 * np.sqrt(case.null_var(Uup)), alpha - g)
    raise ValueError(rule)


def achieved(case: LaneCase, U, n_ref, alpha, rule="plugin", rho=1.0, max_enum=200, n_quant=60):
    """Achieved false-alarm probability / alpha for a window with expected count n_ref = rho U T_w whose
    rate is converted with rho_hat = 1 while the true ratio is rho (rho != 1: biased window)."""
    T_w = n_ref / (rho * U)               # live time of the window
    tl = case.tail(U)
    ns, ps = window_nodes(n_ref, max_enum, n_quant)
    acc = 0.0
    for n_, p_ in zip(ns, ps):
        acc += p_ * float(tl(threshold_rule(case, n_, T_w, alpha, rule))[0])
    return acc / alpha


def achieved_fast(case: LaneCase, U, n_ref, alpha, rule="plugin", rho=1.0, n_nodes=11):
    """As `achieved`, with t*(n) computed exactly at n_nodes window counts spanning +-7 standard deviations
    and interpolated (cubic in n) at the other window counts; t*(n) is smooth because the calibration
    term makes the null distribution continuous.  Agreement with `achieved` is checked in the tests."""
    from scipy.interpolate import CubicSpline
    T_w = n_ref / (rho * U)
    tl = case.tail(U)
    if (case.cal.k * U + case.cal.b) * case.lane.T < 100.0:
        # quasi-discrete statistic: t*(n) has steps, so every window node is computed exactly
        return achieved(case, U, n_ref, alpha, rule, rho, max_enum=80, n_quant=60)
    ns, ps = window_nodes(n_ref, max_enum=10 ** 6)
    keep = ps > 1e-13 * ps.max()
    ns, ps = ns[keep], ps[keep]
    if ns.size <= n_nodes:
        ts = np.array([threshold_rule(case, n_, T_w, alpha, rule) for n_ in ns])
    else:
        grid = np.unique(np.round(np.linspace(ns.min(), ns.max(), n_nodes)))
        tg = np.array([threshold_rule(case, n_, T_w, alpha, rule) for n_ in grid])
        ts = CubicSpline(grid, tg)(ns)
    return float(np.dot(ps, tl(ts))) / alpha


def min_n_ref(case: LaneCase, U, alpha, ratio, rule="plugin", grid=(12, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400),
              table=None):
    """Smallest window count on a log grid (log-interpolated) with achieved/nominal <= ratio.
    table: optional precomputed {n: ratio}."""
    prev = None
    for n in grid:
        r = table[n] if table is not None else achieved_fast(case, U, n, alpha, rule)
        if r <= ratio:
            if prev is None:
                return float(n), r
            (n0, r0) = prev
            f = np.log(r0 / ratio) / np.log(r0 / r) if r0 != r else 1.0
            return float(np.exp(np.log(n0) + f * (np.log(n) - np.log(n0)))), r
        prev = (n, r)
    return float("inf"), prev[1]


def rate_for_power(case: LaneCase, U, t_star, beta=0.05):
    """Activity density (Bq/cm2, u_rel(K) = 0, activity over the footprints) with P(S > t*) = 1 - beta at U."""
    return L.solve_for_power(lambda D: float(case.tail(U, D=D)(t_star)[0]), 1.0 - beta, hi=1.0)


def gradient_bias(gradient_per_m=0.0, step=0.0, L_window_m=1.0, mode="centred", step_at_m=None):
    """Relative bias of a window mean reference rate against the rate at the cell, for a linear field
    1 + g x (x in m from the cell) and/or a step of `step` at x = step_at_m.  centred: window
    [-L/2, L/2]; past: [-L, 0] (one-sided).  Returns U_window / U_cell - 1."""
    a, b = (-L_window_m / 2, L_window_m / 2) if mode == "centred" else (-L_window_m, 0.0)
    mean_lin = gradient_per_m * 0.5 * (a + b)
    frac = 0.0
    if step and step_at_m is not None:
        frac = np.clip((b - max(a, step_at_m)) / (b - a), 0.0, 1.0)
    return float(mean_lin + step * frac)


# ====================================================================== one-sided reference (MODEL.md rev 5 CR-13)
def one_sided_study(case: LaneCase, U, N_sub, alpha, field, estimator, n_nodes=40, grid_pts=25, guard=0.02):
    """Achieved false-alarm probability / alpha and the expected D# ratio for a ONE-SIDED reference made of two adjacent
    sub-windows before the dwell (B adjacent to the dwell, A beyond it), each of expected count N_sub at the cell rate.

    field(x) -> rate relative to the cell, x in units of one sub-window length measured backwards from the dwell
    (B covers [0, 1], A covers [1, 2]); the sub-window means are field averages over those intervals.
    estimator: 'larger'      U_null = larger of the two means, predictive with that sub-window (rev 5 as written)
               'larger+guard' the same, cells with |U_null / (1.5 U_B - 0.5 U_A) - 1| > guard discarded (rev 5 guard)
               'linear'     local-linear extrapolation U0 = 1.5 U_B - 0.5 U_A, predictive with the extrapolation's
                            effective count N_eff = 1 / (2.25 / n_B + 0.25 / n_A)  (slope uncertainty in the posterior)
               'linear+floor' max(linear, U_B), effective count of whichever is used
    Returns (achieved/nominal over kept cells, fraction of cells discarded, D# at the expected estimate / D# with U known)."""
    from scipy.integrate import quad
    from scipy.interpolate import interp1d
    mB = quad(field, 0.0, 1.0)[0]
    mA = quad(field, 1.0, 2.0)[0]
    T_s = N_sub / U                                   # sub-window live time at the cell rate
    nB, pB = window_nodes(N_sub * mB, max_enum=0, n_quant=n_nodes)
    nA, pA = window_nodes(N_sub * mA, max_enum=0, n_quant=n_nodes)
    tl = case.tail(U)
    est = []                                          # (U0, N_post, weight, kept)
    for a_, wa in zip(nA, pA):
        for b_, wb in zip(nB, pB):
            uA, uB = a_ / T_s, b_ / T_s
            lin = 1.5 * uB - 0.5 * uA
            neff = 1.0 / (2.25 / max(b_, 0.5) + 0.25 / max(a_, 0.5))
            if estimator.startswith("larger"):
                u0, npost = (uB, b_) if uB >= uA else (uA, a_)
                kept = True
                if estimator == "larger+guard":
                    kept = lin > 0 and abs(u0 / lin - 1.0) <= guard
            elif estimator == "linear":
                u0, npost, kept = max(lin, 0.05 * uB), neff, True
            else:
                u0, npost, kept = (lin, neff, True) if lin >= uB else (uB, b_, True)
            est.append((u0, npost, wa * wb, kept))
    est = np.array(est)
    keep = est[:, 3] > 0
    if not np.any(keep):
        return float("nan"), 1.0, float("nan")
    # thresholds: smooth in (U0, N_post); N_post varies little, so interpolate in U0 at the median N_post
    npost_med = float(np.median(est[keep, 1]))
    lo, hi = np.percentile(est[keep, 0], [0.01, 99.99])
    if hi - lo < 1e-9 * max(hi, 1e-12):
        ts = np.full(int(keep.sum()), threshold_rule(case, npost_med, npost_med / lo, alpha, "predictive"))
    else:
        ug = np.linspace(lo, hi, grid_pts)
        tg = [threshold_rule(case, npost_med, npost_med / u, alpha, "predictive") for u in ug]
        tfun = interp1d(ug, tg, kind="cubic", fill_value="extrapolate")
        ts = tfun(est[keep, 0])
    w = est[keep, 2]
    ach = float(np.dot(w, tl(ts)) / w.sum()) / alpha
    lost = float(1.0 - w.sum() / est[:, 2].sum())
    u_mean = float(np.dot(w, est[keep, 0]) / w.sum())
    t_mean = threshold_rule(case, npost_med, npost_med / u_mean, alpha, "predictive")
    t_true = threshold_rule(case, 10 ** 7, 10 ** 7 / U, alpha, "plugin")
    dh = rate_for_power(case, U, t_mean) / rate_for_power(case, U, t_true)
    return ach, lost, dh
