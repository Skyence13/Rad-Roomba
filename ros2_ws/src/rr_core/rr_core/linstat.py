"""Exact distribution of S = sum_j a_j N_j + mu + Z (MODEL.md revision 4, sections 3 and 6).

N_j independent Poisson(lam_j), Z ~ N(0, sig^2).  Every decision statistic of the model has this form.
Self-contained port (numpy/scipy only) of the reference evaluators in analysis/radiometry/rrrad/linstat.py:

* Gil-Pelaez inversion of the characteristic function, midpoint rule with step h = 2 pi / P
  (exact tail of the distribution periodised with period P; needs sig > 0);
* lattice convolution (FFT) when sig = 0 and every coefficient is a multiple of one span.

The threshold root search is seeded with the normal quantile and polished with Newton steps on the exact
tail (the density comes from the same characteristic function); a bracketing fallback follows if Newton
leaves the bracket.  The saddlepoint form is not needed here.  Nothing is a measured property of a detector.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr, ndtri

EPS_PHI = 1e-15           # |phi| cut-off of the Gaussian factor
SD_SPAN = 40.0            # periodisation: mass beyond P/2 from x is negligible
CHECK_REL = 1e-3          # MODEL.md section 3: half-step tail must agree to 1e-3 relative


def aggregate(a, lam, decimals=12):
    """Merge counts with equal coefficients (a sum of independent Poisson counts of one weight is Poisson)."""
    a = np.asarray(a, float)
    lam = np.asarray(lam, float)
    keep = (lam > 0) & (a != 0)
    if not np.any(keep):
        return np.zeros(0), np.zeros(0)
    a, lam = a[keep], lam[keep]
    scale = float(np.max(np.abs(a)))
    key = np.round(a / scale, decimals)
    u, inv = np.unique(key, return_inverse=True)
    first = np.zeros(u.size, int)
    first[inv[::-1]] = np.arange(inv.size)[::-1]
    return a[first], np.bincount(inv, weights=lam, minlength=u.size)


class LinStat:
    """S = sum a_j N_j + mu + N(0, sig^2)."""

    def __init__(self, a, lam, mu=0.0, sig=0.0, span=None):
        a = np.atleast_1d(np.asarray(a, float))
        lam = np.broadcast_to(np.asarray(lam, float), a.shape).astype(float)
        if np.any(lam < 0):
            raise ValueError("Poisson means must be >= 0")
        self.a, self.lam = aggregate(a, lam)
        self.mu, self.sig, self.span = float(mu), float(sig), span

    @property
    def mean(self) -> float:
        return float(np.dot(self.a, self.lam) + self.mu)

    @property
    def var(self) -> float:
        return float(np.dot(self.a ** 2, self.lam) + self.sig ** 2)


class _GP:
    """Characteristic function of a statistic on the midpoint grid of the Gil-Pelaez integral."""

    def __init__(self, st: LinStat, half_step: bool = False, x_span_sd: float = 15.0):
        sd = math.sqrt(st.var)
        amax = float(np.max(np.abs(st.a))) if st.a.size else 0.0
        P = 2.0 * (x_span_sd * sd + SD_SPAN * sd + 40.0 * amax)
        if half_step:
            P *= 2.0
        self.h = 2.0 * math.pi / P
        n = int(math.ceil(math.sqrt(-2.0 * math.log(EPS_PHI)) / st.sig / self.h))
        self.u = (np.arange(n) + 0.5) * self.h
        lp = 1j * self.u * st.mu - 0.5 * (st.sig * self.u) ** 2
        for aj, lj in zip(st.a, st.lam):
            lp = lp + lj * np.expm1(1j * self.u * aj)
        self.phi = np.exp(lp)

    def tail_pdf(self, x):
        z = np.exp(-1j * self.u * x) * self.phi
        tail = 0.5 + self.h / math.pi * float(np.sum(z.imag / self.u))
        pdf = self.h / math.pi * float(np.sum(z.real))
        return min(max(tail, 0.0), 1.0), pdf


def _regularised(st: LinStat) -> LinStat:
    """sig = 0 without a common lattice: add a Gaussian of 1e-4 sd (recorded by the caller) so that
    the characteristic function decays.  Only used by tests that switch every calibration term off."""
    return LinStat(st.a, st.lam, st.mu, 1e-4 * math.sqrt(st.var))


def _common_span(st: LinStat):
    """Span s with a_j = m_j s (m_j integers) when sig = 0, else None."""
    if st.a.size == 0:
        return None
    s = float(np.min(np.abs(st.a)))
    for div in range(1, 41):
        span = s / div
        m = st.a / span
        if np.allclose(m, np.rint(m), rtol=0, atol=1e-7):
            return span
    return None


def lattice_tail_obj(st: LinStat, span: float, tail_sd=15.0, margin_terms=40):
    """(vals, sf_ge): lattice values and P(S >= value) for a sig = 0 statistic (pmf by FFT)."""
    m = np.rint(st.a / span).astype(np.int64)
    mean, sd = float(np.dot(m, st.lam)), float(np.sqrt(np.dot(m.astype(float) ** 2, st.lam)))
    mmax = int(np.max(np.abs(m)))
    hi = int(math.ceil(mean + tail_sd * sd + margin_terms * mmax)) if np.any(m > 0) else 0
    lo = int(math.floor(mean - tail_sd * sd - margin_terms * mmax)) if np.any(m < 0) else 0
    n = 1 << int(math.ceil(math.log2(hi - lo + 1)))
    theta = 2.0 * math.pi * np.arange(n) / n
    lg = np.zeros(n, complex)
    for mj, lj in zip(m, st.lam):
        lg += lj * (np.exp(1j * theta * mj) - 1.0)
    pmf = np.real(np.fft.fft(np.exp(lg - 1j * theta * lo))) / n
    pmf = np.where(pmf > 0, pmf, 0.0)[: hi - lo + 1]
    pmf /= pmf.sum()
    vals = (lo + np.arange(pmf.size)) * span + st.mu
    return vals, np.cumsum(pmf[::-1])[::-1]


class Evaluator:
    """Exact tail, threshold and detection limit of one statistic family.

    `stat_at(D)` returns the LinStat with the signal D added (D = 0: the null).  method is
    'linear-exact/gil-pelaez' or 'linear-exact/lattice'."""

    def __init__(self, stat_at):
        self.stat_at = stat_at
        s0 = stat_at(0.0)
        self.regularised = False
        self.span = None
        if s0.sig <= 0:
            self.span = _common_span(s0)
            if self.span is None:
                self.regularised = True
        self.method = "linear-exact/lattice" if self.span is not None else "linear-exact/gil-pelaez"
        self._s0 = _regularised(s0) if self.regularised else s0
        self._gp = None if self.span is not None else _GP(self._s0)

    # ----------------------------------------------------------------- threshold
    def threshold(self, alpha: float):
        """(t*, check_ok, achieved tail).  Flag when S > t*."""
        s0 = self._s0
        if self.span is not None:
            vals, sf_ge = lattice_tail_obj(s0, self.span)
            sf_gt = np.concatenate((sf_ge[1:], [0.0]))
            i = int(np.argmax(sf_gt <= alpha))
            return float(vals[i]), True, float(sf_gt[i])
        sd = math.sqrt(s0.var)
        m = s0.mean
        gp = self._gp
        x = m + float(-ndtri(alpha)) * sd
        lo, hi = m - 2.0 * sd, m + 14.0 * sd
        for _ in range(40):
            tail, pdf = gp.tail_pdf(x)
            if abs(tail - alpha) <= 1e-12 * max(alpha, 1e-300) + 1e-14:
                break
            if tail > alpha:
                lo = max(lo, x)
            else:
                hi = min(hi, x)
            step = (tail - alpha) / pdf if pdf > 0 else 0.0
            x_new = x + step
            if not (lo < x_new < hi):
                x_new = 0.5 * (lo + hi)
            if abs(x_new - x) < 1e-12 * sd:
                x = x_new
                break
            x = x_new
        tail, _ = gp.tail_pdf(x)
        half, _ = _GP(s0, half_step=True).tail_pdf(x)
        ok = abs(half - tail) <= CHECK_REL * max(tail, alpha)
        return float(x), bool(ok), float(tail)

    # ----------------------------------------------------------------- power / detection limit
    def power(self, t: float, D: float) -> float:
        st = self.stat_at(D)
        if self.span is not None and st.sig <= 0:
            vals, sf_ge = lattice_tail_obj(st, self.span)
            i = int(np.searchsorted(vals, t + 1e-9 * self.span, side="right"))
            return float(sf_ge[i]) if i < vals.size else 0.0
        if self.regularised:
            st = _regularised(st)
        return _GP(st).tail_pdf(t)[0]

    def detection_limit(self, t: float, beta: float, seed: float = None) -> float:
        """Smallest D >= 0 with P(S > t | D) = 1 - beta (inf if not reached below 1e9)."""
        target = 1.0 - beta
        hi = max(seed if seed and seed > 0 else 1.0, 1e-9)
        lo = 0.0
        n = 0
        while self.power(t, hi) < target:
            lo = hi
            hi *= 2.0
            n += 1
            if hi > 1e9:
                return math.inf
        if n == 0 and seed:
            lo = 0.5 * hi
            while lo > 1e-12 and self.power(t, lo) >= target:
                hi, lo = lo, 0.5 * lo
            if self.power(t, lo) >= target:
                lo = 0.0
        return float(brentq(lambda d: self.power(t, d) - target, lo, hi, xtol=1e-12 * hi, rtol=1e-7))
