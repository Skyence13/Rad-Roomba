"""Checks of MODEL.md revision 3, section 6 (IB-31) and of the candidate revision-4 rule.

* ``rule_threshold`` / ``rule_dhash`` reproduce what the processing code
  (ros2_ws/src/rr_core/rr_core/estimator.py, ``decision_threshold`` and ``_lane_limit``) computes
  from the footprint-weighted sums of one lane: the Poisson form of sections 2-3 evaluated with
  S_F = sum w N_F, T_F = sum w t (and the same for the reference), method ``normal`` or
  ``poisson-exact``.
* ``truth_stat`` is the statistic actually computed, r = S_F/T_F - k S_U/T_U - b, as a
  ``linstat.LinStat`` (weighted Poisson counts plus the Gaussian calibration term), so its tail is
  exact by lattice convolution.
* ``lane_false_alarm`` averages the achieved false-alarm probability over the independent U_null
  window of section 3 (window of 20 T_F excluding the gates under test, Poisson).
* ``cell_any_lane_false_alarm`` gives the cell-level false-alarm probability of the any-lane rule with
  the common calibration term (u_common(k)) integrated exactly; ``pooled_u0_lane_false_alarm`` the
  per-lane probability when U_null is the four-lane pooled reference over the same gates.
* ``Combined`` is the revision-4 candidate (task C): one linear statistic over all lanes, exact tail.

Calibration coefficients are the synthetic demonstration values; nothing is measured.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr
from scipy.stats import norm, poisson

from . import linstat as L
from . import patch as P

EXACT_ALPHA_BELOW = 1e-3     # estimator.py, MODEL.md section 3 (R2)
EXACT_COUNTS_BELOW = 30.0
MIN_W = 0.10                 # MODEL.md section 5 (R5)

__all__ = ["Cal", "Lane", "truth_tail", "kappa", "select_method", "rule_threshold", "rule_dhash", "truth_stat",
           "u0_nodes", "lane_false_alarm", "power_at", "true_rate_for_power", "exact_dhash_rate",
           "cell_any_lane_false_alarm", "pooled_u0_lane_false_alarm", "cell_lane_weights",
           "PATTERNS", "pattern_lane", "Combined", "variance_overstatement", "n_eff"]


def kappa(p):
    return float(norm.isf(p))


@dataclass(frozen=True)
class Cal:
    """One lane and class (MODEL.md section 1).  u_k split into lane and common parts."""
    k: float = 1.0
    b: float = 0.5
    u_k_lane: float = 0.003
    u_k_common: float = 0.03
    u_b: float = 0.054
    cov_kb: float = -7.6e-5
    K: float = 24.0
    u_rel_K: float = 0.15

    def var_lane(self, U):
        return max(U * U * self.u_k_lane ** 2 + self.u_b ** 2 + 2.0 * U * self.cov_kb, 0.0)

    def var_common(self, U):
        return U * U * self.u_k_common ** 2

    def sig(self, U):
        return float(np.sqrt(self.var_lane(U) + self.var_common(U)))

    def exact_cal(self) -> "Cal":
        return Cal(self.k, self.b, 0.0, 0.0, 0.0, 0.0, self.K, self.u_rel_K)


BETA_CAL = Cal()                                                     # demo beta window, lane-average
ALPHA_CAL = Cal(k=0.0047, b=0.0093, u_k_lane=1.5e-4, u_k_common=4.7e-4, u_b=0.0033, cov_kb=-2.4e-7,
                K=6.0, u_rel_K=0.35)                                 # demo alpha-like class


@dataclass(frozen=True)
class Lane:
    """Footprint weights w_j and raw live times t_j (s) of the gates of one lane in one cell."""
    w: np.ndarray
    t: np.ndarray

    @property
    def T(self) -> float:            # weighted live time, as accumulated by processing
        return float(np.sum(self.w * self.t))

    def kept(self, min_w=MIN_W) -> "Lane":
        m = self.w >= min_w - 1e-12
        return Lane(self.w[m], self.t[m])


def n_eff(lane: Lane) -> float:
    """Moment-matched effective live time (s): (sum w t)^2 / sum w^2 t."""
    return float(lane.T ** 2 / np.sum(lane.w ** 2 * lane.t))


def variance_overstatement(lane: Lane) -> float:
    """Poisson-form variance / true variance of S for equal rates in all gates: sum w t / sum w^2 t."""
    return float(np.sum(lane.w * lane.t) / np.sum(lane.w ** 2 * lane.t))


# --------------------------------------------------------------------------- the rule as processed
def select_method(alpha, U0, T_F, cal: Cal) -> str:
    return "poisson-exact" if alpha < EXACT_ALPHA_BELOW or (cal.k * U0 + cal.b) * T_F < EXACT_COUNTS_BELOW else "normal"


def _u0sq(U0, T_F, T_U, cal: Cal):
    return (cal.k * U0 + cal.b) / T_F + cal.k ** 2 * U0 / T_U + cal.var_lane(U0) + cal.var_common(U0)


def _poisson_model(U0, T_F, T_U, cal: Cal, rho=0.0) -> L.LinStat:
    """Section-3 model of the processing code: integer Poisson N_F, N_U at the weighted live times."""
    sig = cal.sig(U0)
    lam = [(cal.k * U0 + cal.b + rho) * T_F, U0 * T_U]
    if cal.k == 1.0 and T_F == T_U:
        return L.LinStat([1.0 / T_F, -1.0 / T_U], lam, -cal.b, sig, span=1.0 / T_F)
    return L.LinStat([1.0 / T_F, -cal.k / T_U], lam, -cal.b, sig)


def _pois_atoms(stat: L.LinStat, tail=1e-14):
    """Outer-product atoms (value, prob) for a two-count statistic (non-lattice case)."""
    vals, probs = [], []
    for aj, lj in zip(stat.a, stat.lam):
        if lj <= 0:
            vals.append(np.zeros(1)); probs.append(np.ones(1)); continue
        lo, hi = int(poisson.ppf(tail, lj)), int(poisson.isf(tail, lj)) + 1
        n = np.arange(lo, hi + 1)
        vals.append(aj * n); probs.append(poisson.pmf(n, lj))
    v = (vals[0][:, None] + vals[1][None, :]).ravel() + stat.mu
    p = (probs[0][:, None] * probs[1][None, :]).ravel()
    o = np.argsort(v)
    return v[o], p[o] / p.sum()


def _atom_tail(v, p, sig, x):
    if sig <= 0:
        return float(p[v > x].sum())
    return float(np.dot(p, ndtr((v - x) / sig)))


def rule_threshold(U0, T_F, T_U, cal: Cal, alpha, method="auto"):
    """r* (1/s) and method, as estimator.decision_threshold computes it from weighted sums."""
    if method == "auto":
        method = select_method(alpha, U0, T_F, cal)
    if method == "normal":
        return kappa(alpha) * np.sqrt(_u0sq(U0, T_F, T_U, cal)), method
    st = _poisson_model(U0, T_F, T_U, cal)
    if st.span is not None:
        return L.lattice_threshold(st, alpha), method
    v, p = _pois_atoms(st)
    if st.sig <= 0:
        tail_above = np.concatenate((np.cumsum(p[::-1])[::-1][1:], [0.0]))
        return float(v[np.argmax(tail_above <= alpha)]), method
    lo, hi = v[0] - 8 * st.sig, v[-1] + 8 * st.sig
    return float(brentq(lambda x: _atom_tail(v, p, st.sig, x) - alpha, lo, hi, xtol=1e-12)), method


def rule_dhash(U0, T_F, T_U, cal: Cal, alpha, beta, method="auto", with_K=True):
    """Detection limit as estimator._lane_limit quotes it: D# (Bq/cm2) if with_K else r# (1/s)."""
    r_star, method = rule_threshold(U0, T_F, T_U, cal, alpha, method)
    kb = kappa(beta)
    den = (cal.K * (1.0 - kb ** 2 * cal.u_rel_K ** 2)) if with_K else 1.0
    if method == "normal":
        v0 = _u0sq(U0, T_F, T_U, cal)
        p_ = 2.0 * r_star + kb ** 2 / T_F
        q_ = r_star ** 2 - kb ** 2 * v0
        r_hash = 0.5 * (p_ + np.sqrt(max(p_ * p_ - 4.0 * q_, 0.0)))
        if with_K:   # closed form with u_rel(K), section 3
            ys, sd0 = r_star / cal.K, np.sqrt(v0) / cal.K
            a = 1.0 - kb ** 2 * cal.u_rel_K ** 2
            p_ = 2.0 * ys + kb ** 2 / (cal.K * T_F)
            q_ = ys ** 2 - kb ** 2 * sd0 ** 2
            return float((p_ + np.sqrt(max(p_ * p_ - 4.0 * a * q_, 0.0))) / (2.0 * a))
        return float(r_hash)
    def power(rho):
        st = _poisson_model(U0, T_F, T_U, cal, rho)
        if st.span is not None:
            return float(L.tail_lattice(st, r_star)[0])
        v, p = _pois_atoms(st)
        return _atom_tail(v, p, st.sig, r_star)
    r_hash = L.solve_for_power(power, 1.0 - beta, hi=max(2.0 * abs(r_star), 1.0 / T_F))
    return float(r_hash / den)


# --------------------------------------------------------------------------- the statistic actually computed
def truth_stat(lane: Lane, cal: Cal, U, rho=0.0, f=None, span_w=0.05, sig=None, T_F=None) -> L.LinStat:
    """r = S_F/T_F - k S_U/T_U - b with Poisson gate counts (T_U = T_F, same gates).

    rho: net surface rate (1/s) on a fully covered footprint; f_j the fraction of gate j's footprint
    over the activity (default 1, activity extending beyond the cell).  span_w: lattice step of the
    weights (k = 1 only).  sig: Gaussian calibration term (default the declared one at U)."""
    T = lane.T if T_F is None else T_F
    f = np.ones_like(lane.w) if f is None else np.asarray(f, float)
    a = np.concatenate((lane.w / T, -cal.k * lane.w / T))
    lam = np.concatenate(((cal.k * U + cal.b) * lane.t + rho * f * lane.t, U * lane.t))
    span = (span_w / T) if (span_w is not None and cal.k == 1.0) else None
    return L.LinStat(a, lam, -cal.b, cal.sig(U) if sig is None else sig, span)


def truth_tail(lane: Lane, cal: Cal, U, rho=0.0, f=None, span_w=0.05, sig=None) -> L.AtomTail:
    """Exact tail object of the weighted-sum statistic (see truth_stat).  k = 1: one lattice;
    k != 1: floor and reference lattices with incommensurate spans, combined by outer sum."""
    if cal.k == 1.0:
        return L._LatticeTail(truth_stat(lane, cal, U, rho, f, span_w, sig))
    T = lane.T
    f = np.ones_like(lane.w) if f is None else np.asarray(f, float)
    X = L.LinStat(lane.w / T, (cal.k * U + cal.b) * lane.t + rho * f * lane.t, 0.0, 0.0, span_w / T)
    Y = L.LinStat(-cal.k * lane.w / T, U * lane.t, 0.0, 0.0, cal.k * span_w / T)
    return L.two_lattice_tail(X, Y, cal.sig(U) if sig is None else sig, -cal.b)


def u0_nodes(U, T_window, max_enum=400, n_quant=60):
    """Distribution of the windowed U_null = N_w / T_w, N_w ~ Poisson(U T_w): exact enumeration when the
    support is small, else n_quant equal-probability quantile nodes (conditional means)."""
    if T_window is None or np.isinf(T_window):
        return np.array([float(U)]), np.ones(1)
    mu = U * T_window
    lo, hi = int(poisson.ppf(1e-10, mu)), int(poisson.isf(1e-10, mu)) + 1
    n = np.arange(lo, hi + 1)
    p = poisson.pmf(n, mu)
    p /= p.sum()
    if n.size <= max_enum:
        return n / T_window, p
    c = np.cumsum(p)
    edges = np.linspace(0, 1, n_quant + 1)
    idx = np.searchsorted(c, edges[1:-1])
    groups = np.split(np.arange(n.size), idx)
    vals = np.array([np.dot(n[g], p[g]) / p[g].sum() for g in groups if p[g].sum() > 0]) / T_window
    probs = np.array([p[g].sum() for g in groups if p[g].sum() > 0])
    return vals, probs / probs.sum()


def lane_false_alarm(lane: Lane, cal: Cal, U, alpha, method="auto", window_factor=20.0, span_w=0.05,
                     sig_truth=None, max_enum=400, n_quant=60):
    """Achieved P(r > r*) on a clean cell.  r from the weighted sums (exact); r* as processed, at the
    U_null of an independent window of window_factor*T_F (None: U_null = U exactly).
    Returns (achieved, achieved_with_U_null_exact, method)."""
    T = lane.T
    tl = truth_tail(lane, cal, U, span_w=span_w, sig=sig_truth)
    m = select_method(alpha, U, T, cal) if method == "auto" else method
    r0, _ = rule_threshold(U, T, T, cal, alpha, m)
    a0 = float(tl(r0)[0])
    if window_factor is None:
        return a0, a0, m
    vals, probs = u0_nodes(U, window_factor * T, max_enum, n_quant)
    acc = 0.0
    for U0, pr in zip(vals, probs):
        r_star, _ = rule_threshold(U0, T, T, cal, alpha, m)
        acc += pr * float(tl(r_star)[0])
    return acc, a0, m


def power_at(lane: Lane, cal: Cal, U, r_star, rho, f=None, span_w=0.05):
    return float(truth_tail(lane, cal, U, rho, f, span_w)(r_star)[0])


def true_rate_for_power(lane: Lane, cal: Cal, U, r_star, beta, f=None, span_w=0.05):
    """Net rate rho at which the weighted-sum statistic exceeds r* with probability 1 - beta (exact)."""
    return L.solve_for_power(lambda x: power_at(lane, cal, U, r_star, x, f, span_w), 1.0 - beta,
                             hi=max(abs(r_star), 1.0 / lane.T) * 2.0)


def exact_dhash_rate(lane: Lane, cal: Cal, U, alpha, beta, span_w=0.05, f=None):
    """Optimal (exact-distribution) threshold and r# of the weighted-sum statistic: method (C), one lane."""
    tl = truth_tail(lane, cal, U, span_w=span_w)
    t = _atom_threshold(tl, alpha)
    return t, true_rate_for_power(lane, cal, U, t, beta, f, span_w)


def _atom_threshold(tl: L.AtomTail, alpha):
    if tl.sig <= 0:
        return float(tl.vals[int(np.argmax(tl.sf_gt <= alpha))])
    lo, hi = tl.vals[0] - 10 * tl.sig, tl.vals[-1] + 10 * tl.sig
    return float(brentq(lambda x: float(tl(x)[0]) - alpha, lo, hi, xtol=1e-12 * (hi - lo)))


# --------------------------------------------------------------------------- several lanes
def _gh(n=64):
    x, w = np.polynomial.hermite_e.hermegauss(n)
    return x, w / w.sum()


def any_lane_limits(lanes, cals, U, alpha, beta, method="auto", with_K=False):
    """Per-lane (r*, method, D#) of the revision-3 rule at alpha/m (U_null = U).  D# in Bq/cm2 with the
    section-3 u_rel(K) factor if with_K, else with u_rel(K) = 0."""
    m = len(lanes)
    out = []
    for lane, cal in zip(lanes, cals):
        c = cal if with_K else Cal(cal.k, cal.b, cal.u_k_lane, cal.u_k_common, cal.u_b, cal.cov_kb, cal.K, 0.0)
        meth = select_method(alpha / m, U, lane.T, cal) if method == "auto" else method
        r_star, _ = rule_threshold(U, lane.T, lane.T, cal, alpha / m, meth)
        out.append((r_star, meth, rule_dhash(U, lane.T, lane.T, c, alpha / m, beta, meth, with_K=True)))
    return out


def cell_any_lane_false_alarm(lanes, cals, U, alpha, method="auto", span_w=0.05, common=True, n_gh=64,
                              D=0.0, f=None, active=None):
    """P(any lane flags), every lane tested at alpha/m with its own processed threshold (U_null = U).
    The common calibration term U*e, e ~ N(0, u_common(k)), is shared by all lanes and integrated by
    Gauss-Hermite; counts and lane calibration terms are independent.  With D > 0 (Bq/cm2) the lanes in
    `active` (default all) see activity with footprint fractions f[i] (default 1): detection probability.
    Returns (P_cell, [per-lane P], union bound)."""
    m = len(lanes)
    a_l = alpha / m
    xs, ws = _gh(n_gh)
    per, cond = [], []
    for i, (lane, cal) in enumerate(zip(lanes, cals)):
        sig_lane = np.sqrt(cal.var_lane(U))
        on = active is None or active[i]
        fi = None if f is None else f[i]
        tl = truth_tail(lane, cal, U, rho=cal.K * D if on else 0.0, f=fi, span_w=span_w, sig=0.0)
        meth = select_method(a_l, U, lane.T, cal) if method == "auto" else method
        r_star, _ = rule_threshold(U, lane.T, lane.T, cal, a_l, meth)
        sc = U * cal.u_k_common if common else 0.0
        if sig_lane > 0:
            sel = tl.pmf > 1e-300
            v, p = tl.vals[sel], tl.pmf[sel]
            c = np.array([float(np.dot(p, ndtr((v + sc * e - r_star) / sig_lane))) for e in xs])
        else:
            c = np.array([float(tl(r_star - sc * e)[0]) for e in xs])
        cond.append(c)
        per.append(float(np.dot(ws, c)))
    pc = float(np.dot(ws, 1.0 - np.prod([1.0 - c for c in cond], axis=0)))
    return pc, per, float(np.sum(per))


def pooled_u0_lane_false_alarm(T, cal: Cal, U, alpha, method, n_lanes=4):
    """One lane, all weights 1 (live time T): U_null = four-lane pooled reference over the SAME gates
    (MODEL.md section 3 fallback), so the lane's own reference count is a quarter of the pool.
    Exact: sum over own reference count n and the other lanes' count o."""
    lam_f, lam_u = (cal.k * U + cal.b) * T, U * T
    sig = cal.sig(U)
    nu = np.arange(int(poisson.ppf(1e-13, lam_u)), int(poisson.isf(1e-13, lam_u)) + 2)
    pu = poisson.pmf(nu, lam_u)
    lam_o = (n_lanes - 1) * lam_u
    no = np.arange(int(poisson.ppf(1e-12, lam_o)), int(poisson.isf(1e-12, lam_o)) + 2)
    po = poisson.pmf(no, lam_o)
    nf = np.arange(int(poisson.ppf(1e-14, lam_f)), int(poisson.isf(1e-14, lam_f)) + 2)
    pf = poisson.pmf(nf, lam_f)
    cache = {}
    tot = 0.0
    for n_, p_ in zip(nu, pu):
        Ms = n_ + no
        thr = np.empty(Ms.size)
        for i, M in enumerate(Ms):
            if M not in cache:
                cache[M] = rule_threshold(M / (n_lanes * T), T, T, cal, alpha, method)[0]
            thr[i] = cache[M]
        # r = (N_F - k n)/T - b  > thr  <=>  N_F > T (thr + b) + k n
        x = T * (thr + cal.b) + cal.k * n_
        if sig > 0:
            pr = np.array([np.dot(pf, ndtr((nf - xx) / (T * sig))) for xx in x])
        else:
            pr = poisson.sf(np.floor(x + 1e-9), lam_f)
        tot += p_ * float(np.dot(po, pr))
    return tot


# --------------------------------------------------------------------------- weight patterns
def cell_lane_weights(y_lane, v=0.10, gate=0.10, cell=0.10, L_ap=0.080, W_ap=0.060, phase=0.0, min_w=MIN_W,
                      round_to=0.05):
    """Gate weights of one lane crossing a cell: fraction of the ERODED footprint (100 x 80 mm aperture
    eroded by 10 mm per side = 80 x 60 mm) inside a cell x cell square, averaged over each gate, for a
    straight pass at speed v; y_lane = lateral offset of the lane centre from the cell centre (m).
    Weights below min_w are dropped (section 5); kept weights are rounded to round_to so that the
    weighted sum is on a lattice (rule and truth both use the rounded weights)."""
    head = P.Head(L=L_ap, W=W_ap, pitch=1.0, n_lanes=1)
    cellp = P.Patch(0.0, -y_lane, cell, cell)
    edges = P.gate_edges_for_pass(head, cellp, v, gate, phase, margin_gates=1)
    Wm = P.gate_weights(head, cellp, v, edges)[0] / np.diff(edges)
    w = Wm[Wm >= min_w - 1e-12]
    if round_to:
        w = np.round(w / round_to) * round_to
    return Lane(w, np.full(w.size, gate))


def _scaled(w, T_target, gate=0.1):
    """Gate times chosen so that sum w t = T_target (equal weights split freely: only multiplicities matter)."""
    w = np.asarray(w, float)
    return Lane(w, np.full(w.size, T_target / w.sum()))


PATTERNS = {
    "all 1": lambda T: _scaled([1.0] * 10, T),
    "1 full + partials 0.1-0.9": lambda T: _scaled([1.0] + [0.1 * i for i in range(1, 10)], T),
    "7 full + one 0.1": lambda T: _scaled([1.0] * 7 + [0.1], T),
    "all 0.5": lambda T: _scaled([0.5] * 10, T),
    "all 0.10": lambda T: _scaled([0.1] * 10, T),
}


def pattern_lane(name, T):
    return PATTERNS[name](T)


# --------------------------------------------------------------------------- task C: one combined statistic
@dataclass
class Combined:
    """S = sum_i c_i r_i / K_i over the contributing lanes, c_i fixed from the null variances
    (inverse null variance of D_i, normalised to sum 1), r_i from the weighted sums.  The common
    calibration term is fully correlated across lanes and enters as (sum c_i U u_common,i / K_i)^2."""
    lanes: list
    cals: list
    U0: float
    c: np.ndarray = field(default=None)

    def __post_init__(self):
        if self.c is None:
            v = np.array([((cal.k * self.U0 + cal.b) * np.sum(l.w ** 2 * l.t) / l.T ** 2
                           + cal.k ** 2 * self.U0 * np.sum(l.w ** 2 * l.t) / l.T ** 2 + cal.var_lane(self.U0)) / cal.K ** 2
                          for l, cal in zip(self.lanes, self.cals)])
            c = 1.0 / v
            self.c = c / c.sum()

    def stat(self, U=None, D=0.0, f=None, lane_mask=None, sig=None) -> L.LinStat:
        """Combined statistic at true reference rate U (default U0) with activity density D (Bq/cm2)
        seen with footprint fractions f[i][j] (default 1) in the lanes of lane_mask (default all)."""
        U = self.U0 if U is None else U
        a, lam = [], []
        var_lane, common = 0.0, 0.0
        mu = 0.0
        for i, (l, cal) in enumerate(zip(self.lanes, self.cals)):
            ci = self.c[i] / cal.K
            on = lane_mask is None or lane_mask[i]
            fi = np.ones_like(l.w) if (f is None or f[i] is None) else np.asarray(f[i], float)
            a += [ci * l.w / l.T, -ci * cal.k * l.w / l.T]
            lam += [(cal.k * U + cal.b) * l.t + (cal.K * D * fi * l.t if on else 0.0), U * l.t]
            mu -= ci * cal.b
            var_lane += ci ** 2 * cal.var_lane(U)
            common += ci * U * cal.u_k_common
        s = np.sqrt(var_lane + common ** 2) if sig is None else sig
        return L.LinStat(np.concatenate(a), np.concatenate(lam), mu, s)

    def threshold(self, alpha, method="gp"):
        return L.threshold(self.stat(), alpha, method)

    def dhash(self, alpha, beta, method="gp", f=None, lane_mask=None, u_rel_K=0.0):
        """Activity density at which P(S > t*) = 1 - beta; u_rel_K (common to the lanes) enters as a
        Gaussian term D * u_rel_K * E[S]/D in the alternative."""
        t = self.threshold(alpha, method)
        s0 = self.stat()

        def power(D):
            st = self.stat(D=D, f=f, lane_mask=lane_mask)
            gain = st.mean - s0.mean
            st = L.LinStat(st.a, st.lam, st.mu, float(np.hypot(st.sig, u_rel_K * gain)))
            return float(L.tail(st, t, method)[0])
        return t, L.solve_for_power(power, 1.0 - beta, hi=1.0)


def rev2_combined(lanes, cals, U0, alpha, beta, with_K=False):
    """Revision-2 style cell test: inverse-variance combination of the lanes' D with a NORMAL threshold,
    variances in the Poisson form of the weighted sums (as processing evaluated them) and the common
    calibration term added after combination.  Returns (D*, D#, c, sd0)."""
    v_lane = np.array([((cal.k * U0 + cal.b) / l.T + cal.k ** 2 * U0 / l.T + cal.var_lane(U0)) / cal.K ** 2
                       for l, cal in zip(lanes, cals)])
    c = (1.0 / v_lane) / np.sum(1.0 / v_lane)
    common = float(np.sum([ci * U0 * cal.u_k_common / cal.K for ci, cal in zip(c, cals)]))
    sd0 = float(np.sqrt(np.sum(c ** 2 * v_lane) + common ** 2))
    c1 = float(np.sum([ci ** 2 / (cal.K * l.T) for ci, l, cal in zip(c, lanes, cals)]))
    ka, kb = kappa(alpha), kappa(beta)
    u = float(np.dot(c, [cal.u_rel_K for cal in cals])) if with_K else 0.0
    ys = ka * sd0
    a = 1.0 - kb ** 2 * u ** 2
    p_ = 2.0 * ys + kb ** 2 * c1
    q_ = ys ** 2 - kb ** 2 * sd0 ** 2
    return ys, float((p_ + np.sqrt(max(p_ * p_ - 4.0 * a * q_, 0.0))) / (2.0 * a)), c, sd0


def split_rule_dhash(lanes, cals, U0, alpha, beta, s_lane, method="gp", u_rel_K=0.0, n_gh=48):
    """Candidate revision-4 rule with a parallel per-lane test: flag when the combined statistic exceeds its
    exact threshold at (1 - s_lane)*alpha OR any lane exceeds its exact lane threshold at s_lane*alpha/m
    (union bound: cell false alarm <= alpha).  s_lane = 0: combined test only.
    Returns dict: D# for activity uniform over all footprints ("uniform") and, for each lane i, for activity
    over that lane's footprint only ("lane<i>").  P(detect) of the OR rule is at least the larger of the two
    tests' probabilities, so solving max(P_combined, P_lane) = 1 - beta gives an upper (conservative)
    detection limit."""
    m = len(lanes)
    C = Combined(lanes, cals, U0)
    a_c = (1.0 - s_lane) * alpha
    res = {}
    t_c = C.threshold(a_c, method)
    s0 = C.stat()

    def p_comb(D, mask):
        st = C.stat(D=D, lane_mask=mask)
        gain = st.mean - s0.mean
        st = L.LinStat(st.a, st.lam, st.mu, float(np.hypot(st.sig, u_rel_K * gain)))
        return float(L.tail(st, t_c, method)[0])

    lane_thr = []
    if s_lane > 0:
        for l, cal in zip(lanes, cals):
            tl = truth_tail(l, cal, U0)
            lane_thr.append(_atom_threshold(tl, s_lane * alpha / m))

    def p_lane(i, D):
        if s_lane <= 0:
            return 0.0
        l, cal = lanes[i], cals[i]
        tl = truth_tail(l, cal, U0, rho=cal.K * D, sig=float(np.hypot(cal.sig(U0), u_rel_K * D)))
        return float(tl(lane_thr[i])[0])

    res["uniform"] = L.solve_for_power(lambda D: max(p_comb(D, None), max(p_lane(i, D) for i in range(m))), 1 - beta)
    for i in range(m):
        mask = [j == i for j in range(m)]
        res[f"lane{i}"] = L.solve_for_power(lambda D: max(p_comb(D, mask), p_lane(i, D)), 1 - beta)
    res["c"] = C.c
    return res
