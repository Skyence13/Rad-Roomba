"""Count-processing estimator - analysis/radiometry/MODEL.md REVISION 3 (normative).

Section numbers in comments refer to MODEL.md.  Cross-tested against the
reference implementation analysis/radiometry/rrrad (tests/test_estimator.py).
Every coefficient is supplied by a calibration record; none is defined here.

No ROS imports.  Runtime dependencies: numpy, scipy.special.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.special import gammaln, ndtr, ndtri

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


# ------------------------------------------------------------- lane combination
@dataclass
class LaneStat:
    """Weighted sums for one lane and class over a gate set (sections 1, 6)."""
    lane: int
    N_F: float
    T_F: float
    N_U: float
    T_U: float
    U0: float                 # U_null (section 3, R1)
    u0_method: str
    cal: Cal
    envelope_ok: bool = True
    envelope_reason: str = ""


RULE = "per-lane-exact/any-lane/alpha-over-m"    # MODEL.md rev 3 section 6 (IB-31, CR-09)
WEIGHTED_SUM_VARIANCE = "poisson_form_conservative"   # MODEL.md rev 3 section 6 (IB-31, CR-08)


@dataclass
class Decision:
    D: float | None = None
    u_stat: float | None = None
    u_total: float | None = None
    D_star: float | None = None       # min over the contributing lanes of r*_i / K_i (each at alpha/m)
    D_hash: float | None = None       # min over the contributing lanes of D#_i solved at (alpha/m, beta)
    T_F: float = 0.0
    detected: bool | None = None      # any contributing lane above its own threshold
    method: str = ""                  # m = 1: the lane method of section 3; m > 1: RULE
    rule: str = RULE
    m: int = 0
    alpha: float = 0.0
    alpha_lane: float = 0.0           # alpha / m
    beta: float = 0.0
    flagged_lanes: list = field(default_factory=list)
    u0_methods: list = field(default_factory=list)
    lanes: list = field(default_factory=list)     # per lane: w, r, D, r_star, D_star, D_hash, method, flagged ...
    envelope_ok: bool = True
    envelope_reason: str = ""

    def as_dict(self):
        return dict(self.__dict__)


def _lane_limit(s: LaneStat, alpha_lane: float, beta: float, exact_detection_limit: bool):
    """Threshold r*, method and detection limit D# of ONE lane at (alpha_lane, beta), section 3
    (all calibration terms of the lane, common ones included, belong to the lane's own test)."""
    cal = s.cal
    r_star, method = decision_threshold(s.U0, s.T_F, s.T_U, cal, alpha_lane, parts="all")
    kb = kappa(beta)
    den = cal.K * (1.0 - kb ** 2 * cal.u_rel_K ** 2)
    if method == "poisson-exact" and exact_detection_limit:
        r_hash = detection_limit_rate(r_star, 0.0, s.T_F, beta, s.U0, s.T_U, cal, "poisson-exact", "all")
        D_hash = math.inf if den <= 0 else r_hash / den
    else:
        sd0 = math.sqrt(u0sq(s.U0, s.T_F, s.T_U, cal, "all"))
        D_hash = detection_limit_activity(r_star / cal.K, sd0 / cal.K, 1.0 / (cal.K * s.T_F), cal.u_rel_K, beta)
    return r_star, method, D_hash


def combine(stats: list, alpha: float, beta: float, exact_detection_limit: bool = True) -> Decision:
    """Section 6 (revision 3).

    Estimate: inverse-variance combination of the lanes' D with the common calibration terms added
    after combination (weights use the NULL variance of each lane, so they do not depend on the
    floor counts under test).  The sums N, T are footprint-weighted and enter the Poisson form
    unchanged (`WEIGHTED_SUM_VARIANCE`, conservative).

    Decision (IB-31 / CR-09): m = number of contributing lanes.  The cell is flagged when ANY lane
    exceeds its own threshold evaluated at alpha/m (method per lane from section 3); by the union
    bound the cell false-alarm probability is <= alpha.  Quoted D* and D# are the minima over the
    lanes of D*_i and D#_i (solved at alpha/m, beta).  With one lane m = 1 and this is section 3
    directly.  `exact_detection_limit=False` replaces the numerical exact D# of an exact-method lane
    by the normal-form solve with the exact threshold (cheaper; used for nothing in production).
    """
    stats = [s for s in stats if s.T_F > 0 and s.T_U > 0]
    if not stats:
        return Decision(alpha=alpha, beta=beta)
    m = len(stats)
    alpha_lane = alpha / m
    rows = []
    for s in stats:
        est = net_estimate(s.N_F, s.T_F, s.N_U, s.T_U, s.cal)
        rows.append((s, est, u0sq(s.U0, s.T_F, s.T_U, s.cal, "lane")) + _lane_limit(s, alpha_lane, beta, exact_detection_limit))
    wsum = sum(s.cal.K ** 2 / v0 for s, _, v0, *_ in rows)
    D = v_stat = v_lane = common_k = T = u_rel = 0.0
    lanes, flagged = [], []
    for s, est, v0, r_star, method, D_hash in rows:
        w = (s.cal.K ** 2 / v0) / wsum
        D += w * est["D"]
        v_stat += w ** 2 * est["v_stat_r"] / s.cal.K ** 2
        v_lane += w ** 2 * est["v_lane_r"] / s.cal.K ** 2
        common_k += w * est["U"] * s.cal.u_k_common / s.cal.K        # fully correlated: linear sum
        u_rel += w * s.cal.u_rel_K
        T += s.T_F
        hit = bool(est["r"] > r_star)
        if hit:
            flagged.append(s.lane)
        lanes.append({"lane": s.lane, "w": w, "N_F": s.N_F, "T_F": s.T_F, "N_U": s.N_U, "T_U": s.T_U,
                      "U0": s.U0, "r": est["r"], "D": est["D"], "r_star": r_star, "D_star": r_star / s.cal.K,
                      "D_hash": D_hash, "method": method, "flagged": hit})
    methods = sorted({r[4] for r in rows})
    ok = all(s.envelope_ok for s in stats)
    return Decision(
        D=D, u_stat=math.sqrt(v_stat),
        u_total=math.sqrt(v_stat + v_lane + common_k ** 2 + D ** 2 * u_rel ** 2),
        D_star=min(l["D_star"] for l in lanes), D_hash=min(l["D_hash"] for l in lanes), T_F=T,
        detected=bool(flagged), method=methods[0] if m == 1 else RULE, m=m, alpha=alpha, alpha_lane=alpha_lane,
        beta=beta, flagged_lanes=flagged, u0_methods=sorted({s.u0_method for s in stats}), lanes=lanes,
        envelope_ok=ok, envelope_reason="; ".join(sorted({s.envelope_reason for s in stats if s.envelope_reason})))
