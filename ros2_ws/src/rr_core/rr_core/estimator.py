"""Count-processing estimator - analysis/radiometry/MODEL.md REVISION 4 (normative).

The closed-form / revision-2 functions (decision_threshold, detection_limit_*) are kept as planning
approximations and for cross-tests; the decisions of a survey come from `combine` (revision 4: exact
linear statistics, rr_core.linstat).

Section numbers in comments refer to MODEL.md.  Cross-tested against the
reference implementation analysis/radiometry/rrrad (tests/test_estimator.py).
Every coefficient is supplied by a calibration record; none is defined here.

No ROS imports.  Runtime dependencies: numpy, scipy.special.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.special import gammaln, ndtr, ndtri

from .linstat import Evaluator, LinStat

EXACT_ALPHA_BELOW = 1e-3      # section 3 (R2): exact thresholds for alpha below this ...
EXACT_COUNTS_BELOW = 30.0     # ... or expected floor counts in the dwell below this
MIN_LANE_GATE_WEIGHT = 0.10   # section 5 (R5)


@dataclass(frozen=True)
class Cal:
    """Calibration record of section 1 for one lane and class."""
    k: float
    b: float
    u_k_lane: float = 0.0       # lane-specific fit component of u(k)
    u_k_common: float = 0.0     # component common to all lanes (spectral mismatch)
    u_b: float = 0.0
    cov_kb: float = 0.0
    K: float = 1.0
    u_rel_K: float = 0.0
    eps: float | None = None    # leakage fraction (section 2); None = not measured

    @property
    def u_k(self) -> float:     # section 1: u^2(k) = u_lane^2 + u_common^2
        return math.hypot(self.u_k_lane, self.u_k_common)


def kappa(p: float) -> float:
    """kappa_p = z_{1-p} (section 3)."""
    return float(-ndtri(p))


def sidak_alpha(allowance: float, n: int) -> float:
    """Per-decision alpha_1 = 1 - (1 - P_m)^(1/n) (section 3, R3)."""
    if not 0 < allowance < 1 or n < 1:
        raise ValueError("allowance must be in (0,1) and n >= 1")
    return float(-math.expm1(math.log1p(-allowance) / n))


# ------------------------------------------------------------------ section 2
def net_estimate(N_F, T_F, N_U, T_U, cal: Cal) -> dict:
    """r, D and their uncertainties for one lane/class and one gate set (section 2).

    Signed values are kept.  Low counts: the variance estimate uses N+1 when N is
    zero (not r).  Returns variances split into counting, lane-specific
    calibration and common calibration parts so that lanes can be combined with
    the common terms added afterwards (section 6).
    """
    F, U = N_F / T_F, N_U / T_U
    r = F - cal.k * U - cal.b
    nf = N_F if N_F > 0 else N_F + 1.0
    nu = N_U if N_U > 0 else N_U + 1.0
    v_stat = nf / T_F ** 2 + cal.k ** 2 * nu / T_U ** 2
    v_lane = U ** 2 * cal.u_k_lane ** 2 + cal.u_b ** 2 + 2.0 * U * cal.cov_kb
    v_common = U ** 2 * cal.u_k_common ** 2
    D = r / cal.K
    v_total_r = v_stat + max(v_lane, 0.0) + v_common
    return {"F": F, "U": U, "r": r, "D": D, "v_stat_r": v_stat, "v_lane_r": max(v_lane, 0.0),
            "v_common_r": v_common, "u_stat_D": math.sqrt(v_stat) / cal.K,
            "u_total_D": math.sqrt(v_total_r / cal.K ** 2 + D ** 2 * cal.u_rel_K ** 2)}


# ------------------------------------------------------------------ section 3
def u0sq(U0, T_F, T_U, cal: Cal, parts: str = "all") -> float:
    """u~^2(0) at the null reference rate U0 (section 3).

    parts: "all" | "counting" | "lane" (counting + lane-specific calibration).
    """
    counting = (cal.k * U0 + cal.b) / T_F + cal.k ** 2 * U0 / T_U
    if parts == "counting":
        return counting
    lane = max(U0 ** 2 * cal.u_k_lane ** 2 + cal.u_b ** 2 + 2.0 * U0 * cal.cov_kb, 0.0)
    if parts == "lane":
        return counting + lane
    return counting + lane + U0 ** 2 * cal.u_k_common ** 2


def _pois_support(mu: float, tail: float = 1e-13):
    if mu <= 0:
        return np.array([0.0]), np.array([1.0])
    sd = math.sqrt(mu)
    lo = max(0, int(mu - 9.0 * sd - 5))
    hi = int(mu + 9.0 * sd + 12)
    n = np.arange(lo, hi + 1, dtype=float)
    p = np.exp(n * math.log(mu) - mu - gammaln(n + 1.0))
    keep = p > tail * p.max()
    return n[keep], p[keep] / p[keep].sum()


def _exact_tail(t, r_atoms, p_atoms, sigma):
    """P(r + N(0, sigma) > t) for a discrete r distribution."""
    if sigma <= 0:
        return float(p_atoms[r_atoms > t].sum())
    return float((p_atoms * ndtr((r_atoms - t) / sigma)).sum())


def _null_atoms(U0, T_F, T_U, cal: Cal, rho: float = 0.0):
    """Atoms of r = (N_F - (k T_F/T_U) N_U)/T_F - b with Poisson N_F, N_U (R2)."""
    nf, pf = _pois_support((cal.k * U0 + cal.b + rho) * T_F)
    nu, pu = _pois_support(U0 * T_U)
    r = (nf[:, None] / T_F - cal.k * nu[None, :] / T_U - cal.b).ravel()
    p = (pf[:, None] * pu[None, :]).ravel()
    return r, p


def decision_threshold(U0, T_F, T_U, cal: Cal, alpha: float, parts: str = "all", force: str | None = None):
    """r* and the method used (section 3, R2).

    `normal`: r* = kappa_alpha * u~(0).  `poisson-exact`: r* from the exact
    distribution of N_F - (k T_F/T_U) N_U under H0 with the calibration terms
    added as a Gaussian broadening; used when alpha < 1e-3 or expected floor
    counts < 30.
    """
    v0 = u0sq(U0, T_F, T_U, cal, parts)
    exact = alpha < EXACT_ALPHA_BELOW or (cal.k * U0 + cal.b) * T_F < EXACT_COUNTS_BELOW
    if force is not None:
        exact = force == "poisson-exact"
    if not exact:
        return kappa(alpha) * math.sqrt(v0), "normal"
    sigma = math.sqrt(max(v0 - u0sq(U0, T_F, T_U, cal, "counting"), 0.0))
    r, p = _null_atoms(U0, T_F, T_U, cal)
    if sigma <= 0:
        # discrete statistic: r* is the smallest attainable value a with P(r > a) <= alpha
        order = np.argsort(r)
        rs, ps = r[order], p[order]
        tail_above = np.concatenate((np.cumsum(ps[::-1])[::-1][1:], [0.0]))
        return float(rs[np.argmax(tail_above <= alpha)]), "poisson-exact"
    lo, hi = float(r.min()) - 8 * sigma - 1e-9, float(r.max()) + 8 * sigma + 1e-9
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _exact_tail(mid, r, p, sigma) > alpha:
            lo = mid
        else:
            hi = mid
    return hi, "poisson-exact"


def detection_limit_rate(r_star, sd0, T_F, beta: float, U0=None, T_U=None, cal: Cal | None = None,
                         method: str = "normal", parts: str = "all") -> float:
    """r# (section 3).  normal: positive root of r# = r* + kappa_beta*sqrt(sd0^2 + r#/T_F).
    poisson-exact: numeric solve of P(r > r* | rho) = 1 - beta on the exact distribution."""
    kb = kappa(beta)
    if method == "poisson-exact" and cal is not None:
        v0 = u0sq(U0, T_F, T_U, cal, parts)
        sigma = math.sqrt(max(v0 - u0sq(U0, T_F, T_U, cal, "counting"), 0.0))

        def power(rho):
            r, p = _null_atoms(U0, T_F, T_U, cal, rho)
            return _exact_tail(r_star, r, p, sigma)
        lo, hi = 0.0, max(2.0 * abs(r_star), 1.0 / T_F)
        while power(hi) < 1.0 - beta:
            hi *= 2.0
            if hi > 1e9:
                return math.inf
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if power(mid) < 1.0 - beta:
                lo = mid
            else:
                hi = mid
        return hi
    p_ = 2.0 * r_star + kb ** 2 / T_F
    q_ = r_star ** 2 - kb ** 2 * sd0 ** 2
    return 0.5 * (p_ + math.sqrt(max(p_ * p_ - 4.0 * q_, 0.0)))


def detection_limit_activity(y_star, sd0_D, c1, u_rel_K, beta: float) -> float:
    """D# with u_rel(K) (section 3): positive root of
    (1 - kb^2 u_rel^2) y^2 - (2 y* + kb^2 c1) y + (y*^2 - kb^2 sd0_D^2) = 0,
    c1 = 1/(K T_F) for one lane (generalised to a lane combination by the caller).
    inf when kappa_beta * u_rel(K) >= 1."""
    kb = kappa(beta)
    a = 1.0 - kb ** 2 * u_rel_K ** 2
    if a <= 0:
        return math.inf
    p_ = 2.0 * y_star + kb ** 2 * c1
    q_ = y_star ** 2 - kb ** 2 * sd0_D ** 2
    return (p_ + math.sqrt(max(p_ * p_ - 4.0 * a * q_, 0.0))) / (2.0 * a)


def u_k_floor(U, cal: Cal, alpha: float, beta: float) -> float:
    """Dwell-independent floor of D# from u(k) (section 3, R7), kappa_alpha = kappa_beta form."""
    ka, kb = kappa(alpha), kappa(beta)
    den = cal.K * (1.0 - kb ** 2 * cal.u_rel_K ** 2)
    return math.inf if den <= 0 else (ka + kb) * U * cal.u_k / den


# ------------------------------------------------------------- revision 4: exact linear statistics
RULE = "linear-exact/combined+per-lane/0.8-0.2"
ALPHA_SPLIT_COMBINED = 0.8                      # combined test at 0.8 alpha; each lane at 0.2 alpha / m
WEIGHTED_SUM_VARIANCE = "exact_coefficients"
NO_DECISION_REF = "no decision \u2014 null reference unavailable"
NO_DECISION_EVAL = "no decision \u2014 evaluator check failed"
WEIGHT_STEP = 0.05                              # footprint weights are rounded to this lattice (rule and statistic)


class LaneGates:
    """Gates of one lane contributing to a decision cell (or one stationary count, w = 1)."""

    def __init__(self, lane, w, tf, N_F, tu, N_U, U0, u0_method, cal: Cal, envelope_ok=True, envelope_reason="",
                 u0_window_s=None, u0_window_counts=None):
        self.lane, self.cal = lane, cal
        self.w, self.tf, self.N_F = (np.asarray(x, float) for x in (w, tf, N_F))
        self.tu, self.N_U = np.asarray(tu, float), np.asarray(N_U, float)
        self.U0, self.u0_method = U0, u0_method
        self.envelope_ok, self.envelope_reason = envelope_ok, envelope_reason
        self.u0_window_s, self.u0_window_counts = u0_window_s, u0_window_counts

    @property
    def T_F(self): return float(np.dot(self.w, self.tf))

    @property
    def T_U(self): return float(np.dot(self.w, self.tu))


def LaneStat(lane, N_F, T_F, N_U, T_U, U0, u0_method, cal, envelope_ok=True, envelope_reason=""):
    """One gate of weight 1 (a stationary count or a test case)."""
    return LaneGates(lane, [1.0], [T_F], [N_F], [T_U], [N_U], U0, u0_method, cal, envelope_ok, envelope_reason)


class Decision:
    def __init__(self, **kw):
        self.D = self.u_stat = self.u_total = self.D_star = None
        self.T_F = 0.0
        self.detected = None
        self.method = ""
        self.rule = RULE
        self.status = "OK"
        self.status_text = ""
        self.m = 0
        self.alpha = self.beta = self.alpha_comb = self.alpha_lane = 0.0
        self.c = []
        self.flagged_by = []
        self.flagged_lanes = []
        self.u0_methods = []
        self.lanes = []
        self.excluded_lanes = []
        self.check_ok = True
        self.envelope_ok = True
        self.envelope_reason = ""
        self._D_hash = None
        self._hash_fn = None
        self.__dict__.update(kw)

    @property
    def D_hash(self):
        if self._D_hash is None and self._hash_fn is not None:
            self._D_hash = self._hash_fn()
            self._hash_fn = None
        return self._D_hash

    @D_hash.setter
    def D_hash(self, v):
        self._D_hash = v

    def as_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k not in ("_hash_fn", "_D_hash")}
        d["D_hash"] = self.D_hash
        return d


class Decider:
    """Thresholds and detection limits of the exact linear statistics, with a cache.

    The statistic under the null depends only on the null means (U_null, weights, live times), not on the
    counts, so thresholds repeat between cells of equal footprint pattern.  With `quantise` the inputs of the
    NULL statistic (U_null on a 0.25 % log grid, live time per weight bin to 1 ms) are rounded before it is
    built, so a cache hit gives exactly the value a miss would compute (results do not depend on evaluation
    order; replay is bit-identical).  quantise = False uses the inputs as they are (cross-checks)."""

    def __init__(self, quantise=True, u0_step=0.0025, t_step=1e-3, max_entries=20000):
        self.quantise, self.u0_step, self.t_step, self.max_entries = quantise, u0_step, t_step, max_entries
        self._ev, self._thr, self._lim = {}, {}, {}
        self.stats = {"threshold_calls": 0, "threshold_computed": 0, "limit_calls": 0, "limit_computed": 0,
                      "seconds_threshold": 0.0, "seconds_limit": 0.0}

    def _q_u0(self, u):
        if not self.quantise or u <= 0:
            return float(u)
        return math.exp(round(math.log(u) / self.u0_step) * self.u0_step)

    def _lane_key(self, g: LaneGates):
        bins = {}
        for w, tf, tu in zip(g.w, g.tf, g.tu):
            b = bins.setdefault(round(float(w), 9), [0.0, 0.0])
            b[0] += tf
            b[1] += tu
        q = (lambda x: round(x / self.t_step) * self.t_step) if self.quantise else (lambda x: x)
        return (g.cal, self._q_u0(g.U0), tuple(sorted((w, q(a), q(b)) for w, (a, b) in bins.items())))

    @staticmethod
    def _family(keys):
        """c_i, and stat_at(D) for the lanes given by their keys (all with a reference)."""
        parts = []
        for cal, U0, bins in keys:
            w = np.array([b[0] for b in bins])
            tf = np.array([b[1] for b in bins])
            tu = np.array([b[2] for b in bins])
            T_F, T_U = float(np.dot(w, tf)), float(np.dot(w, tu))
            var = ((cal.k * U0 + cal.b) * float(np.dot(w * w, tf)) / T_F ** 2
                   + cal.k ** 2 * U0 * float(np.dot(w * w, tu)) / T_U ** 2
                   + max(U0 * U0 * cal.u_k_lane ** 2 + cal.u_b ** 2 + 2.0 * U0 * cal.cov_kb, 0.0)) / cal.K ** 2
            parts.append((cal, U0, w, tf, tu, T_F, T_U, var))
        inv = np.array([1.0 / p[7] for p in parts])
        c = inv / inv.sum()
        mu = -sum(ci / p[0].K * p[0].b for ci, p in zip(c, parts))
        var_lane = sum((ci / p[0].K) ** 2 * max(p[1] ** 2 * p[0].u_k_lane ** 2 + p[0].u_b ** 2 + 2.0 * p[1] * p[0].cov_kb, 0.0)
                       for ci, p in zip(c, parts))
        common = sum(ci / p[0].K * p[1] * p[0].u_k_common for ci, p in zip(c, parts))
        sig0 = math.sqrt(var_lane + common ** 2)
        u_rel = float(sum(ci * p[0].u_rel_K for ci, p in zip(c, parts)))

        def stat_at(D):
            a, lam = [], []
            for ci, (cal, U0, w, tf, tu, T_F, T_U, _v) in zip(c, parts):
                cp = ci / cal.K
                a += [cp * w / T_F, -cp * cal.k * w / T_U]
                lam += [(cal.k * U0 + cal.b + cal.K * D) * tf, U0 * tu]
            return LinStat(np.concatenate(a), np.concatenate(lam), mu, math.hypot(sig0, u_rel * D))
        return c, stat_at

    def _evaluator(self, keys):
        ev = self._ev.get(keys)
        if ev is None:
            if len(self._ev) > self.max_entries:
                self._ev.clear(); self._thr.clear(); self._lim.clear()
            c, stat_at = self._family(keys)
            ev = (c, Evaluator(stat_at))
            self._ev[keys] = ev
        return ev

    def threshold(self, keys, alpha):
        self.stats["threshold_calls"] += 1
        k = (keys, alpha)
        r = self._thr.get(k)
        if r is None:
            t0 = time.perf_counter()
            c, ev = self._evaluator(keys)
            t, ok, _ach = ev.threshold(alpha)
            r = (c, t, ok, ev.method + ("(regularised)" if ev.regularised else ""))
            self._thr[k] = r
            self.stats["threshold_computed"] += 1
            self.stats["seconds_threshold"] += time.perf_counter() - t0
        return r

    def limit(self, keys, alpha, beta):
        self.stats["limit_calls"] += 1
        k = (keys, alpha, beta)
        r = self._lim.get(k)
        if r is None:
            t0 = time.perf_counter()
            c, t, ok, _m = self.threshold(keys, alpha)
            ev = self._evaluator(keys)[1]
            s0 = ev.stat_at(0.0)
            seed = max(t + kappa(beta) * math.sqrt(s0.var), 1e-6)
            r = ev.detection_limit(t, beta, seed)
            self._lim[k] = r
            self.stats["limit_computed"] += 1
            self.stats["seconds_limit"] += time.perf_counter() - t0
        return r


DEFAULT_DECIDER = Decider()


def _lane_estimate(g: LaneGates):
    cal = g.cal
    T_F, T_U = g.T_F, g.T_U
    NF, NU = float(np.dot(g.w, g.N_F)), float(np.dot(g.w, g.N_U))
    F, U = NF / T_F, NU / T_U
    r = F - cal.k * U - cal.b
    w2 = g.w ** 2
    if g.U0 is not None:       # low counts: max(sum w^2 N, sum w^2 lambda0), never N + 1
        sf = max(float(np.dot(w2, g.N_F)), float(np.dot(w2, (cal.k * g.U0 + cal.b) * g.tf)))
        su = max(float(np.dot(w2, g.N_U)), float(np.dot(w2, g.U0 * g.tu)))
    else:
        sf, su = float(np.dot(w2, g.N_F)), float(np.dot(w2, g.N_U))
    v_stat = sf / T_F ** 2 + cal.k ** 2 * su / T_U ** 2
    v_lane = max(U * U * cal.u_k_lane ** 2 + cal.u_b ** 2 + 2.0 * U * cal.cov_kb, 0.0)
    return {"r": r, "D": r / cal.K, "U": U, "v_stat_r": v_stat, "v_lane_r": v_lane, "T_F": T_F, "T_U": T_U,
            "NF": NF, "NU": NU}


def combine(stats: list, alpha: float, beta: float, decider: Decider | None = None, **_unused) -> Decision:
    """MODEL.md revision 4, sections 3 and 6.

    Estimate D, u_stat, u_total: inverse-null-variance combination of the lanes (exact coefficients,
    common calibration terms added after combination).  Decision: S = sum_i c_i r_i / K_i (c_i from the null
    variances at U_null) is flagged at 0.8 alpha, or any lane's own statistic (m = 1) at 0.2 alpha / m;
    thresholds from the exact distribution (rr_core.linstat).  D* and D# are those of the combined test
    (D# solved lazily on first use).  Lanes without a U_null are not used for the decision; none left:
    status NO_DECISION_REF.  A failed numerical check gives NO_DECISION_EVAL."""
    decider = decider or DEFAULT_DECIDER
    lanes = [g for g in stats if g.T_F > 0 and g.T_U > 0]
    if not lanes:
        return Decision(alpha=alpha, beta=beta, status="NO_DATA", status_text="no gates")
    est = [_lane_estimate(g) for g in lanes]
    # estimate weights: null variances at U_null (the lane's own N_U/T_U where none is available: weights only)
    keys_w = []
    for g, e in zip(lanes, est):
        gg = g if g.U0 is not None else LaneGates(g.lane, g.w, g.tf, g.N_F, g.tu, g.N_U, e["U"], "estimate-only", g.cal)
        keys_w.append(decider._lane_key(gg))
    cw, _ = Decider._family(keys_w)
    D = float(sum(ci * e["D"] for ci, e in zip(cw, est)))
    v_stat = sum(ci ** 2 * e["v_stat_r"] / g.cal.K ** 2 for ci, e, g in zip(cw, est, lanes))
    v_lane = sum(ci ** 2 * e["v_lane_r"] / g.cal.K ** 2 for ci, e, g in zip(cw, est, lanes))
    common = sum(ci * e["U"] * g.cal.u_k_common / g.cal.K for ci, e, g in zip(cw, est, lanes))
    u_rel = sum(ci * g.cal.u_rel_K for ci, g in zip(cw, lanes))
    dec = Decision(D=D, u_stat=math.sqrt(v_stat), u_total=math.sqrt(v_stat + v_lane + common ** 2 + D * D * u_rel * u_rel),
                   T_F=float(sum(e["T_F"] for e in est)), alpha=alpha, beta=beta,
                   u0_methods=sorted({g.u0_method for g in lanes}),
                   envelope_ok=all(g.envelope_ok for g in lanes),
                   envelope_reason="; ".join(sorted({g.envelope_reason for g in lanes if g.envelope_reason})))
    use = [(g, e) for g, e in zip(lanes, est) if g.U0 is not None]
    dec.excluded_lanes = [g.lane for g in lanes if g.U0 is None]
    if not use:
        dec.status, dec.status_text = "NO_DECISION_REF", NO_DECISION_REF
        return dec
    m = len(use)
    dec.m = m
    dec.alpha_comb = ALPHA_SPLIT_COMBINED * alpha
    dec.alpha_lane = (1.0 - ALPHA_SPLIT_COMBINED) * alpha / m
    keys = tuple(decider._lane_key(g) for g, _ in use)
    c, t_c, ok_c, meth_c = decider.threshold(keys, dec.alpha_comb)
    dec.c, dec.D_star, dec.method, dec.check_ok = [float(x) for x in c], float(t_c), meth_c, bool(ok_c)
    S = float(sum(ci / g.cal.K * e["r"] for ci, (g, e) in zip(c, use)))
    flagged = ["combined"] if S > t_c else []
    lane_rows = []
    for ci, (g, e), key in zip(c, use, keys):
        _c1, t_i, ok_i, meth_i = decider.threshold((key,), dec.alpha_lane)
        dec.check_ok = dec.check_ok and bool(ok_i)
        hit = e["D"] > t_i
        if hit:
            flagged.append(f"lane{g.lane}")
            dec.flagged_lanes.append(g.lane)
        lane_rows.append({"lane": g.lane, "c": float(ci), "N_F": float(e["NF"]), "T_F": e["T_F"], "N_U": float(e["NU"]),
                          "T_U": e["T_U"], "U0": g.U0, "u0_method": g.u0_method, "u0_window_s": g.u0_window_s,
                          "u0_window_counts": g.u0_window_counts, "r": e["r"], "D": e["D"], "D_star": float(t_i),
                          "method": meth_i, "flagged": bool(hit)})
    dec.lanes, dec.flagged_by = lane_rows, flagged
    dec.S = S
    if not dec.check_ok:
        dec.status, dec.status_text, dec.detected = "NO_DECISION_EVAL", NO_DECISION_EVAL, None
        dec.D_star = None
        return dec
    dec.detected = bool(flagged)
    dec._hash_fn = lambda: float(decider.limit(keys, dec.alpha_comb, beta))
    return dec
