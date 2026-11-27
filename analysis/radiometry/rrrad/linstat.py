"""Tail probabilities of a linear combination of independent Poisson counts plus a Gaussian term.

    S = sum_j a_j N_j + mu + Z,   N_j ~ Poisson(lam_j) independent,   Z ~ N(0, sig^2)

Every decision statistic of MODEL.md sections 2, 3 and 6 has this form: footprint weights,
reference subtraction and a fixed linear lane combination only change the coefficients a_j;
the calibration terms are the Gaussian part (MODEL.md section 3, "Gaussian broadening").
Its cumulant generating function is closed form,

    K(s) = sum_j lam_j (exp(a_j s) - 1) + mu s + sig^2 s^2 / 2 .

Three evaluators of P(S > x):

* ``tail_lattice``  exact (to floating point) when every a_j is an integer multiple of a span
                    delta: the pmf on the lattice is obtained by FFT of the characteristic
                    function, then combined with the Gaussian term in closed form.
* ``tail_gp``       Gil-Pelaez inversion of the characteristic function (midpoint rule with a
                    step chosen so that periodisation is negligible).  Exact up to quadrature for
                    any coefficients **provided sig > 0** (otherwise the integrand does not decay).
* ``tail_spa``      Lugannani-Rice saddlepoint approximation, continuous form, or lattice form
                    with the second continuity correction when ``span`` is given and sig = 0.

``threshold`` finds the decision threshold t* with P(S > t*) <= alpha for any evaluator.
Nothing here is a measured property of a detector.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr

__all__ = ["LinStat", "AtomTail", "two_lattice_tail", "aggregate", "lattice_pmf", "tail_lattice", "tail_gp", "tail_spa", "tail",
           "threshold", "lattice_threshold", "solve_for_power"]


@dataclass(frozen=True)
class LinStat:
    """S = sum a_j N_j + mu + N(0, sig^2), N_j ~ Poisson(lam_j)."""
    a: np.ndarray
    lam: np.ndarray
    mu: float = 0.0
    sig: float = 0.0
    span: float | None = None       # lattice span of the Poisson part, if every a_j/span is an integer

    def __post_init__(self):
        a = np.atleast_1d(np.asarray(self.a, float))
        lam = np.broadcast_to(np.asarray(self.lam, float), a.shape).astype(float)
        if np.any(lam < 0):
            raise ValueError("Poisson means must be >= 0")
        object.__setattr__(self, "a", a)
        object.__setattr__(self, "lam", lam)

    @property
    def mean(self) -> float:
        return float(np.dot(self.a, self.lam) + self.mu)

    @property
    def var(self) -> float:
        return float(np.dot(self.a ** 2, self.lam) + self.sig ** 2)

    def shifted(self, d_lam=None, d_mu=0.0, sig=None) -> "LinStat":
        lam = self.lam if d_lam is None else self.lam + d_lam
        return replace(self, lam=lam, mu=self.mu + d_mu, sig=self.sig if sig is None else sig)

    @staticmethod
    def concat(parts, mu=0.0, sig=0.0, span=None) -> "LinStat":
        return LinStat(np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts]), mu, sig, span)


def aggregate(a, lam, decimals=12):
    """Merge counts with equal coefficients (a sum of Poisson counts with one weight is Poisson)."""
    a = np.asarray(a, float)
    lam = np.asarray(lam, float)
    keep = (lam > 0) & (a != 0)
    if not np.any(keep):
        return np.zeros(0), np.zeros(0)
    scale = float(np.max(np.abs(a[keep])))
    key = np.round(a[keep] / scale, decimals)          # relative rounding: merges float noise only
    u, inv = np.unique(key, return_inverse=True)
    first = np.zeros(u.size, int)
    first[inv[::-1]] = np.arange(inv.size)[::-1]
    return a[keep][first], np.bincount(inv, weights=lam[keep], minlength=u.size)


# --------------------------------------------------------------------------- exact lattice evaluator
def lattice_pmf(stat: LinStat, span: float | None = None, tail_sd: float = 15.0, margin_terms: int = 40):
    """Exact pmf of the Poisson part sum a_j N_j on the lattice span*n, by FFT.

    Returns (lo, span, pmf) with pmf[i] = P(sum a_j N_j = (lo + i) * span).  The window covers the
    mean +- tail_sd standard deviations plus margin_terms times the largest step, so aliased mass is
    far below the probabilities of interest (>= 1e-12)."""
    span = stat.span if span is None else span
    if span is None:
        raise ValueError("lattice_pmf needs a lattice span")
    a, lam = aggregate(stat.a, stat.lam)
    if a.size == 0:
        return 0, span, np.ones(1)
    m = np.rint(a / span)
    if not np.allclose(m * span, a, rtol=1e-9, atol=1e-12 * np.max(np.abs(a))):
        raise ValueError("coefficients are not on the lattice")
    m = m.astype(np.int64)
    mean, sd = float(np.dot(m, lam)), float(np.sqrt(np.dot(m.astype(float) ** 2, lam)))
    mmax = int(np.max(np.abs(m)))
    hi = int(np.ceil(mean + tail_sd * sd + margin_terms * mmax)) if np.any(m > 0) else 0
    lo = int(np.floor(mean - tail_sd * sd - margin_terms * mmax)) if np.any(m < 0) else 0
    n = 1 << int(np.ceil(np.log2(hi - lo + 1)))
    theta = 2.0 * np.pi * np.arange(n) / n
    logphi = np.zeros(n, complex)
    for mj, lj in zip(m, lam):                 # few distinct coefficients after aggregation
        logphi += lj * (np.exp(1j * theta * mj) - 1.0)
    psi = np.exp(logphi - 1j * theta * lo)
    pmf = np.real(np.fft.fft(psi)) / n
    pmf = np.where(pmf > 0, pmf, 0.0)[: hi - lo + 1]
    return lo, span, pmf / pmf.sum()


class AtomTail:
    """P(S > x) for a discrete distribution (sorted atoms vals, probabilities pmf) plus N(0, sig^2)."""

    def __init__(self, vals, pmf, sig=0.0, span=None):
        o = np.argsort(vals, kind="stable")
        self.vals, self.pmf, self.sig = np.asarray(vals, float)[o], np.asarray(pmf, float)[o], float(sig)
        self.span = span if span is not None else (float(np.min(np.diff(self.vals))) if self.vals.size > 1 else 1.0)
        self._cum()

    def _cum(self):
        rc = np.cumsum(self.pmf[::-1])[::-1]
        self.sf_ge = rc
        self.sf_gt = np.concatenate((rc[1:], [0.0]))
        # sf_strict[i] = P(value > vals[i])
    def __call__(self, x):
        x = np.atleast_1d(np.asarray(x, float))
        out = np.empty(x.shape)
        if self.sig <= 0:
            # strict inequality S > x on the lattice (half-span tolerance for rounding)
            i = np.searchsorted(self.vals, x + 1e-9 * self.span, side="right")
            out = np.where(i < self.vals.size, self.sf_ge[np.minimum(i, self.vals.size - 1)], 0.0)
            return out
        w = 12.0 * self.sig
        for k, xx in enumerate(x):
            i0 = np.searchsorted(self.vals, xx - w, side="left")
            i1 = np.searchsorted(self.vals, xx + w, side="right")
            above = self.sf_ge[i1] if i1 < self.vals.size else 0.0
            seg = slice(i0, i1)
            out[k] = above + float(np.dot(self.pmf[seg], ndtr((self.vals[seg] - xx) / self.sig)))
        return out

    def atoms_above(self, x):
        """Smallest lattice value > x (for a strict-inequality decision)."""
        i = np.searchsorted(self.vals, x + 1e-9 * self.span, side="right")
        return self.vals[min(i, self.vals.size - 1)]


class _LatticeTail(AtomTail):
    """Exact tail of a lattice LinStat (pmf by FFT)."""

    def __init__(self, stat: LinStat, span=None, **kw):
        self.lo, span, pmf = lattice_pmf(stat, span, **kw)
        AtomTail.__init__(self, (self.lo + np.arange(pmf.size)) * span + stat.mu, pmf, stat.sig, span)


def two_lattice_tail(X: LinStat, Y: LinStat, sig: float, mu: float = 0.0, min_p: float = 1e-20) -> AtomTail:
    """Exact tail of X + Y + mu + N(0, sig^2) for two independent lattice statistics with different
    (incommensurate) spans, by the outer sum of their atoms (atoms below min_p dropped)."""
    lx, sx, px = lattice_pmf(X)
    ly, sy, py = lattice_pmf(Y)
    vx = (lx + np.arange(px.size)) * sx + X.mu
    vy = (ly + np.arange(py.size)) * sy + Y.mu
    kx, ky = px > min_p, py > min_p
    v = (vx[kx][:, None] + vy[ky][None, :]).ravel() + mu
    p = (px[kx][:, None] * py[ky][None, :]).ravel()
    return AtomTail(v, p / p.sum(), sig, span=min(sx, sy))


def tail_lattice(stat: LinStat, x, span=None, **kw):
    """Exact P(S > x) for a lattice Poisson part (strict inequality when sig = 0)."""
    return _LatticeTail(stat, span, **kw)(x)


# --------------------------------------------------------------------------- Gil-Pelaez evaluator
def _logphi(stat_a, stat_lam, mu, sig, u):
    lp = 1j * u * mu - 0.5 * (sig * u) ** 2
    for aj, lj in zip(stat_a, stat_lam):
        lp = lp + lj * np.expm1(1j * u * aj)
    return lp


def tail_gp(stat: LinStat, x, eps: float = 1e-15, sd_span: float = 40.0):
    """Gil-Pelaez: P(S > x) = 1/2 + (1/pi) int_0^inf Im[exp(-iux) phi(u)] / u du  (sig > 0 required).

    Midpoint rule with step h = 2 pi / P, P = 2 (|x - mean| + sd_span sd + 40 max|a|): the rule is the
    exact tail of the distribution periodised with period P, so the error is the mass farther than
    P/2 from x.  Upper limit where |phi| < eps (Gaussian factor)."""
    if stat.sig <= 0:
        raise ValueError("Gil-Pelaez needs sig > 0 (a Gaussian calibration term); use tail_lattice for sig = 0")
    a, lam = aggregate(stat.a, stat.lam)
    x = np.atleast_1d(np.asarray(x, float))
    sd = np.sqrt(stat.var)
    amax = float(np.max(np.abs(a))) if a.size else 0.0
    out = np.empty(x.shape)
    u_max = np.sqrt(-2.0 * np.log(eps)) / stat.sig
    for k, xx in enumerate(x):
        P = 2.0 * (abs(xx - stat.mean) + sd_span * sd + 40.0 * amax)
        h = 2.0 * np.pi / P
        n = int(np.ceil(u_max / h))
        out[k] = 0.0
        for c0 in range(0, n, 200_000):                     # chunks keep memory bounded
            u = (np.arange(c0, min(n, c0 + 200_000)) + 0.5) * h
            ph = np.exp(_logphi(a, lam, stat.mu - xx, stat.sig, u))
            out[k] += np.sum(ph.imag / u)
        out[k] = 0.5 + h * out[k] / np.pi
    return np.clip(out, 0.0, 1.0)


# --------------------------------------------------------------------------- saddlepoint evaluator
def _cgf(a, lam, mu, sig, s):
    e = np.exp(np.outer(s, a))
    K0 = (e - 1.0) @ lam + mu * s + 0.5 * sig ** 2 * s ** 2
    K1 = e @ (lam * a) + mu + sig ** 2 * s
    K2 = e @ (lam * a * a) + sig ** 2
    return K0, K1, K2


def tail_spa(stat: LinStat, x, span: float | None = None):
    """Lugannani-Rice approximation to P(S > x).

    span given and sig = 0: lattice form for P(S >= x+) where x+ is the next lattice value above x,
    with Daniels' second continuity correction (saddlepoint at x+ - span/2, u = 2 sinh(s span/2)/span
    * sqrt(K'')).  Otherwise the continuous form.  Returns nan where the saddlepoint equation has
    no solution (x outside the convex hull of the support)."""
    a, lam = aggregate(stat.a, stat.lam)
    x = np.atleast_1d(np.asarray(x, float))
    lattice = span is not None and stat.sig <= 0
    out = np.empty(x.shape)
    for k, xx in enumerate(x):
        if lattice:
            n_up = np.floor((xx - stat.mu) / span + 1e-9) + 1.0     # first lattice index strictly above x
            xt = (n_up - 0.5) * span + stat.mu
        else:
            xt = xx
        # bounds of K' : if all a > 0 and sig == 0 the support is bounded below by mu
        f = lambda s: float(_cgf(a, lam, stat.mu, stat.sig, np.array([s]))[1][0]) - xt
        lo, hi = -1.0, 1.0
        try:
            while f(lo) > 0:
                lo *= 2.0
                if lo < -1e6:
                    raise ValueError
            while f(hi) < 0:
                hi *= 2.0
                if hi > 1e6:
                    raise ValueError
        except ValueError:
            out[k] = np.nan
            continue
        sh = brentq(f, lo, hi, xtol=1e-14, rtol=1e-14)
        K0, K1, K2 = (float(v[0]) for v in _cgf(a, lam, stat.mu, stat.sig, np.array([sh])))
        mean = stat.mean
        if abs(xt - mean) < 1e-8 * np.sqrt(stat.var):
            out[k] = 0.5
            continue
        w = np.sign(sh) * np.sqrt(max(2.0 * (sh * xt - K0), 0.0))
        uu = (2.0 * np.sinh(0.5 * sh * span) / span if lattice else sh) * np.sqrt(K2)
        from scipy.stats import norm
        out[k] = norm.sf(w) + norm.pdf(w) * (1.0 / uu - 1.0 / w)
    return out


def tail(stat: LinStat, x, method: str = "auto"):
    """Dispatch: 'lattice' (exact), 'gp' (exact to quadrature, sig > 0), 'spa' (approximation),
    'auto' = lattice if a span is set, else gp if sig > 0, else error."""
    if method == "auto":
        method = "lattice" if stat.span is not None else ("gp" if stat.sig > 0 else "none")
    if method == "lattice":
        return tail_lattice(stat, x)
    if method == "gp":
        return tail_gp(stat, x)
    if method == "spa":
        return tail_spa(stat, x, stat.span)
    raise ValueError("no exact evaluator: non-lattice coefficients and sig = 0")


# --------------------------------------------------------------------------- thresholds and power
def lattice_threshold(stat: LinStat, alpha: float) -> float:
    """Exact decision threshold t* (flag S > t*) with P(S > t*) <= alpha, lattice evaluator.

    sig = 0: t* is the smallest lattice value with P(S > t*) <= alpha (the achieved probability is
    the largest attainable value not above alpha).  sig > 0: root of P(S > t) = alpha."""
    lt = _LatticeTail(stat)
    if stat.sig <= 0:
        i = int(np.argmax(lt.sf_gt <= alpha))
        return float(lt.vals[i])
    return _root_tail(lambda t: float(lt(t)[0]), stat, alpha)


def _root_tail(fun, stat, alpha):
    m, sd = stat.mean, np.sqrt(stat.var)
    lo, hi = m - 2.0 * sd, m + 6.0 * sd
    while fun(hi) > alpha:
        hi += 4.0 * sd
    while fun(lo) < alpha:
        lo -= 2.0 * sd
    return float(brentq(lambda t: fun(t) - alpha, lo, hi, xtol=1e-10 * sd, rtol=1e-12))


def threshold(stat: LinStat, alpha: float, method: str = "auto") -> float:
    """Decision threshold t* with P(S > t*) = alpha (or <= alpha on a lattice without Gaussian term)."""
    if method == "auto":
        method = "lattice" if stat.span is not None else "gp"
    if method == "lattice":
        return lattice_threshold(stat, alpha)
    if method == "gp":
        return _root_tail(lambda t: float(tail_gp(stat, t)[0]), stat, alpha)
    if method == "spa":
        if stat.span is not None and stat.sig <= 0:
            # step function: scan lattice values upward from the continuous root
            t = _root_tail(lambda t: float(tail_spa(replace(stat, span=None), t)[0]), stat, alpha)
            n = np.floor((t - stat.mu) / stat.span) - 3
            while float(tail_spa(stat, (n * stat.span) + stat.mu, stat.span)[0]) > alpha:
                n += 1
            while n > 0 and float(tail_spa(stat, ((n - 1) * stat.span) + stat.mu, stat.span)[0]) <= alpha:
                n -= 1
            return float(n * stat.span + stat.mu)
        return _root_tail(lambda t: float(tail_spa(stat, t)[0]), stat, alpha)
    raise ValueError(method)


def solve_for_power(power_of, target: float, hi: float = 1.0, tol: float = 1e-7) -> float:
    """Smallest amplitude x >= 0 with power_of(x) = target (power_of increasing)."""
    while power_of(hi) < target:
        hi *= 2.0
        if hi > 1e9:
            return float("inf")
    return float(brentq(lambda x: power_of(x) - target, 0.0, hi, xtol=tol * hi, rtol=1e-10))
