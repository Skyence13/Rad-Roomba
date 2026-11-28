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
PRED_SD_SPAN = 15.0       # predictive evaluator: half period in standard deviations beyond |x - mean| (checked against rrrad)


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


# ====================================================================== revision 5: predictive threshold
def posterior_nodes(n_w: float, T_w: float, k: int = 12):
    """Gauss-Legendre-in-probability nodes of the Jeffreys posterior Gamma(n_w + 1/2, scale 1/T_w) of the reference
    rate given a window of n_w counts in live time T_w (MODEL.md rev 5 section 3, 12 nodes).  Identical to
    analysis/radiometry/rrrad/unull.posterior_nodes (gamma.ppf(q, a, scale) = gammaincinv(a, q) * scale)."""
    from scipy.special import gammaincinv
    x, w = np.polynomial.legendre.leggauss(k)
    q = 0.5 * (x + 1.0)
    return np.array([float(gammaincinv(n_w + 0.5, qq)) / T_w for qq in q]), 0.5 * w


def _lattice(a, step=None):
    """(base, integer multipliers) when every coefficient is an integer multiple (|m| <= 400) of one base, else None:
    the 0.05 weight lattice makes the floor and reference coefficients of a lane lattice-valued, so exp(i u a_j) are
    powers of one exp(i u base) on the quadrature grid (fast, exact to rounding)."""
    if a.size == 0:
        return None
    base = float(np.min(np.abs(a)))
    for div in (1, 2, 3, 4, 5, 6, 8, 10, 12, 20):
        b = base / div
        m = a / b
        mi = np.rint(m)
        if np.all(np.abs(m - mi) <= 1e-9 * np.maximum(1.0, np.abs(m))) and np.max(np.abs(mi)) <= 400:
            return b, mi.astype(int)
    return None


def _sum_exp(u, a, t, lat):
    """sum_j t_j expm1(i u a_j) on the grid u."""
    out = np.zeros(u.size, complex)
    if lat is None:
        for aj, tj in zip(a, t):
            out += tj * np.expm1(1j * u * aj)
        return out
    base, m = lat
    by_m = {}
    for mj, tj in zip(m, t):
        by_m[int(mj)] = by_m.get(int(mj), 0.0) + float(tj)
    z = np.exp(1j * u * base * np.sign(max(by_m, key=abs)))
    sgn = 1 if max(by_m, key=abs) > 0 else -1
    zk = np.ones(u.size, complex)
    for k in range(1, max(abs(x) for x in by_m) + 1):
        zk = zk * z
        tk = by_m.get(sgn * k, 0.0)
        if tk:
            out += tk * (zk - 1.0)
    for mj, tj in by_m.items():        # coefficients of the other sign (not expected within one lane)
        if mj * sgn < 0:
            out += tj * np.expm1(1j * u * base * mj)
    return out


class Unit:
    """One lane (of one attachment) inside a decision statistic S = sum_i c_i r_i / K_i.

    cK = c_i / K_i; floor coefficients cK w_j / T_F, reference coefficients -cK k w_j / T_U; null means
    (k U + b) t_f,j and U t_u,j; Gaussian lane term cK^2 var_lane(U) and the diagonal part of the common term
    (cK u_common U)^2, both evaluated at every posterior node U of the lane; the K D t_f,j signal is added to the
    floor means.  nodes_U / nodes_p: the posterior nodes (one node with weight 1 = U known / plug-in)."""

    def __init__(self, cK, cal, w, tf, tu, nodes_U, nodes_p):
        w, tf, tu = (np.asarray(x, float) for x in (w, tf, tu))
        self.cK, self.cal = float(cK), cal
        T_F, T_U = float(np.dot(w, tf)), float(np.dot(w, tu))
        self.aF, self.tF = aggregate(cK * w / T_F, tf)
        self.aU, self.tU = aggregate(-cK * cal.k * w / T_U, tu)
        self.latF = _lattice(self.aF)
        self.latU = _lattice(self.aU)
        self.U = np.asarray(nodes_U, float)
        self.p = np.asarray(nodes_p, float)
        self.s2 = np.array([cK * cK * max(u * u * cal.u_k_lane ** 2 + cal.u_b ** 2 + 2.0 * u * cal.cov_kb, 0.0)
                            + (cK * cal.u_k_common * u) ** 2 for u in self.U])

    def var(self, D=0.0):
        """Largest variance over the nodes (grid sizing)."""
        c = self.cal
        return float(max((c.k * u + c.b + c.K * D) * np.dot(self.aF ** 2, self.tF) + u * np.dot(self.aU ** 2, self.tU) + s2
                         for u, s2 in zip(self.U, self.s2)))

    def mean(self, D=0.0):
        c = self.cal
        return float(np.dot(self.p, [(c.k * u + c.b + c.K * D) * np.dot(self.aF, self.tF) + u * np.dot(self.aU, self.tU)
                                     for u in self.U]))

    def amax(self):
        return float(max(np.max(np.abs(self.aF)) if self.aF.size else 0.0, np.max(np.abs(self.aU)) if self.aU.size else 0.0))


class PredictiveStat:
    """Exact tail of the predictive null (and alternatives) of S = sum_i Unit_i + mu + Z (MODEL.md rev 5 sections 3, 6).

    Characteristic function: exp(i u mu - u^2 (s_x^2 + (u_rel D)^2) / 2) * prod_i sum_k p_ik phi_i(u; U_ik, D): the posterior
    nodes of the lanes are combined as independent.  The common calibration term (sum_i cK_i u_common,i U_i)^2 is fully
    correlated across lanes: its diagonal parts are evaluated at the nodes of each lane, the cross terms
    2 sum_{i<j} g_i g_j U0_i U0_j at the point values U0 (s_x^2 = `cross_var`); with one lane the evaluation is exact.
    Gil-Pelaez inversion, midpoint rule with step h = 2 pi / P (the exact tail of the distribution periodised with
    period P), as `_GP`.  The A_F(u) = sum_j t_j expm1(i u a_j) sums are computed once per grid; nodes and alternatives
    only rescale them."""

    def __init__(self, units, mu, cross_var=0.0, u_rel=0.0):
        self.units, self.mu, self.cross_var, self.u_rel = units, float(mu), max(float(cross_var), 0.0), float(u_rel)
        self.sig_min2 = sum(float(np.min(u.s2)) for u in units) + self.cross_var
        self.regularised = self.sig_min2 <= 0
        if self.regularised:            # no Gaussian term at all (tests that switch every calibration term off)
            self.cross_var = 1e-8 * self.var(0.0)
            self.sig_min2 = self.cross_var
        self._grids = {}

    def var(self, D=0.0):
        return sum(u.var(D) for u in self.units) + self.cross_var + (self.u_rel * D) ** 2

    def mean(self, D=0.0):
        return sum(u.mean(D) for u in self.units) + self.mu

    def _grid(self, span, half_step=False):
        """(h, u, [(A_F, A_U) per unit]) for a period covering `span` (|x - mean| + 40 sd + 40 max|a|)."""
        key = (round(span, 12), half_step)
        g = self._grids.get(key)
        if g is None:
            P = 2.0 * span * (2.0 if half_step else 1.0)
            h = 2.0 * math.pi / P
            n = int(math.ceil(math.sqrt(-2.0 * math.log(EPS_PHI)) / math.sqrt(self.sig_min2) / h))
            u = (np.arange(n) + 0.5) * h
            parts = [(_sum_exp(u, un.aF, un.tF, un.latF), _sum_exp(u, un.aU, un.tU, un.latU)) for un in self.units]
            g = (h, u, parts)
            if len(self._grids) > 6:
                self._grids.clear()
            self._grids[key] = g
        return g

    def _phi(self, grid, D):
        h, u, parts = grid
        lp = 1j * u * self.mu - 0.5 * u * u * (self.cross_var + (self.u_rel * D) ** 2)
        phi = np.exp(lp)
        for un, (AF, AU) in zip(self.units, parts):
            c = un.cal
            mix = np.zeros(u.size, complex)
            for U, p, s2 in zip(un.U, un.p, un.s2):
                mix += p * np.exp((c.k * U + c.b + c.K * D) * AF + U * AU - 0.5 * s2 * u * u)
            phi = phi * mix
        return phi

    def span_for(self, x, D=0.0):
        """Half period: |x - mean| + 15 sd + 20 max|a| (the periodised mass beyond it is negligible)."""
        sd = math.sqrt(self.var(D))
        amax = max(un.amax() for un in self.units)
        return abs(x - self.mean(D)) + PRED_SD_SPAN * sd + 20.0 * amax

    @staticmethod
    def _tail_pdf(grid, phi, x):
        h, u, _ = grid
        z = np.exp(-1j * u * x) * phi
        tail = 0.5 + h / math.pi * float(np.sum(z.imag / u))
        pdf = h / math.pi * float(np.sum(z.real))
        return min(max(tail, 0.0), 1.0), pdf

    def tail(self, x, D=0.0, half_step=False):
        g = self._grid(self.span_for(x, D), half_step)
        return self._tail_pdf(g, self._phi(g, D), x)[0]

    def threshold(self, alpha: float):
        """(t*, check_ok, achieved tail): P(S > t*) = alpha under the predictive null; half-step check (1e-3)."""
        sd = math.sqrt(self.var(0.0))
        m = self.mean(0.0)
        g = self._grid(self.span_for(m, 0.0) + 14.0 * sd)
        phi = self._phi(g, 0.0)
        x = m + float(-ndtri(alpha)) * sd
        lo, hi = m - 2.0 * sd, m + 14.0 * sd
        for _ in range(60):
            tail, pdf = self._tail_pdf(g, phi, x)
            if abs(tail - alpha) <= 1e-12 * alpha + 1e-15:
                break
            if tail > alpha:
                lo = max(lo, x)
            else:
                hi = min(hi, x)
            step = (tail - alpha) / pdf if pdf > 0 else 0.0
            x_new = x + step
            if not (lo < x_new < hi):
                x_new = 0.5 * (lo + hi)
            if abs(x_new - x) < 1e-13 * sd:
                x = x_new
                break
            x = x_new
        tail, _ = self._tail_pdf(g, phi, x)
        gh = self._grid(self.span_for(x, 0.0), half_step=True)
        half, _ = self._tail_pdf(gh, self._phi(gh, 0.0), x)
        ok = abs(half - tail) <= CHECK_REL * max(tail, alpha)
        return float(x), bool(ok), float(tail)

    def detection_limit(self, t: float, beta: float, seed: float = None) -> float:
        """Smallest D >= 0 with P(S > t | D) = 1 - beta under the predictive distribution (signal on the floor means,
        u_rel(K) D as a Gaussian term); inf if not reached below 1e9.  One grid serves every trial D up to 4 x the
        bracket (rebuilt when the bracket grows)."""
        target = 1.0 - beta
        hi = max(seed if seed and seed > 0 else 1.0, 1e-9)
        state = {"grid": None, "Dmax": -1.0}

        def power(D):
            if D > state["Dmax"]:
                state["Dmax"] = 4.0 * max(D, hi)
                state["grid"] = self._grid(self.span_for(t, state["Dmax"]) + abs(self.mean(state["Dmax"]) - self.mean(0.0)))
            g = state["grid"]
            return self._tail_pdf(g, self._phi(g, D), t)[0]
        lo, n = 0.0, 0
        while power(hi) < target:
            lo, hi, n = hi, 2.0 * hi, n + 1
            if hi > 1e9:
                return math.inf
        if n == 0 and seed:
            lo = 0.5 * hi
            while lo > 1e-12 and power(lo) >= target:
                hi, lo = lo, 0.5 * lo
            if power(lo) >= target:
                lo = 0.0
        return float(brentq(lambda d: power(d) - target, lo, hi, xtol=1e-12 * hi, rtol=1e-9))
