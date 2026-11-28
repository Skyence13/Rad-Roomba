"""Reference implementation of the predictive threshold for one or several lanes (MODEL.md revision 5, sections 3, 6).

Statistic S = sum_i c_i r_i / K_i (rrrad.rev3.Combined), each lane i with its OWN U_null posterior
U_i ~ Gamma(N_i + 1/2, scale 1/T_i), the lanes' posteriors independent.  The predictive null tail is

    P(S > x) = E_{U_1..U_m} [ P(S > x | U_1..U_m) ] .

The common calibration term Z_c = e * sum_i g_i U_i (e ~ N(0,1), g_i = c_i u_common,i(k) / K_i) couples the lanes
through U_i.  Conditioning on e makes the characteristic function separable:

    phi(u) = E_e [ prod_i E_{U_i} [ phi_i(u | U_i) exp(i u e g_i U_i) ] ] ,

with phi_i the exact characteristic function of lane i's counts and lane calibration term at U_i.  e is integrated
exactly by summing over the product of the lanes' 12 Gauss-Legendre-in-probability posterior nodes (as MODEL.md
states; 12^m terms, with the characteristic function computed once on a fixed grid), and the tail by Gil-Pelaez.  `approx_common=True` reproduces the simplification of
ros2_ws rr_core.linstat.PredictiveStat (diagonal parts of the common term at the lane's nodes, cross terms
2 sum_{i<j} g_i g_j U0_i U0_j at point values U0_i) so that the two can be compared.
Nothing here is a measured property of a detector.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from . import linstat as L
from . import rev3 as R
from .unull import posterior_nodes

__all__ = ["LanePost", "PredictiveCombined", "thresholds"]


@dataclass
class LanePost:
    """One lane: gate weights and live times, calibration, combination weight c_i, and its U_null posterior
    (N, T).  N = None means U known (= U0)."""
    lane: R.Lane
    cal: R.Cal
    c: float
    U0: float
    N: float | None = None
    T: float | None = None


class PredictiveCombined:
    def __init__(self, lanes: list, n_post=12, n_e=32, approx_common=False, u_rel_K=0.0):
        self.lanes, self.n_post, self.n_e, self.approx, self.u_rel_K = lanes, n_post, n_e, approx_common, u_rel_K
        self.e, w = np.polynomial.hermite_e.hermegauss(n_e)
        self.we = w / w.sum()
        self.nodes = []
        for lp in lanes:
            if lp.N is None:
                self.nodes.append((np.array([lp.U0]), np.array([1.0])))
            else:
                self.nodes.append(posterior_nodes(lp.N, lp.T, n_post))
        self._grid_cache = {}

    # -------------------------------------------------------------- moments (grid sizing)
    def _lane_terms(self, lp):
        cK = lp.c / lp.cal.K
        T = lp.lane.T
        return cK, cK * lp.lane.w / T, -cK * lp.cal.k * lp.lane.w / T

    def mean_var(self, D=0.0):
        m = v = 0.0
        g_sum_mean = 0.0
        for lp, (Us, ps) in zip(self.lanes, self.nodes):
            cK, aF, aU = self._lane_terms(lp)
            c = lp.cal
            Um = float(np.dot(ps, Us))
            U2 = float(np.dot(ps, Us ** 2))
            lamF = (c.k * Um + c.b) * lp.lane.t + c.K * D * lp.lane.t
            m += float(np.dot(aF, lamF) + np.dot(aU, Um * lp.lane.t)) - cK * c.b
            v += float(np.dot(aF ** 2, lamF) + np.dot(aU ** 2, Um * lp.lane.t)) + cK ** 2 * c.var_lane(Um)
            v += (cK * c.k) ** 2 * 0.0 + (U2 - Um ** 2) * (np.dot(aF, c.k * lp.lane.t) + np.dot(aU, lp.lane.t)) ** 2
            g_sum_mean += cK * c.u_k_common * Um
        v += g_sum_mean ** 2
        gain = sum(lp.c for lp in self.lanes) * D
        return m, v + (self.u_rel_K * gain) ** 2

    def _sig_min(self):
        s2 = 0.0
        for lp, (Us, _) in zip(self.lanes, self.nodes):
            cK = lp.c / lp.cal.K
            s2 += cK ** 2 * min(lp.cal.var_lane(u) for u in Us)
        return math.sqrt(max(s2, 1e-30))

    # -------------------------------------------------------------- characteristic function
    def _node_parts(self, u, D):
        """Per lane: (g_i, U nodes, p nodes, B[k, u] = node characteristic function without the common term)."""
        out = []
        for lp, (Us, ps) in zip(self.lanes, self.nodes):
            cK, aF, aU = self._lane_terms(lp)
            c = lp.cal
            AF = np.expm1(1j * np.outer(u, aF)) @ lp.lane.t        # sum_j t_j (e^{i u a_j} - 1)
            AU = np.expm1(1j * np.outer(u, aU)) @ lp.lane.t
            B = np.array([np.exp((c.k * U + c.b + c.K * D) * AF + U * AU - 1j * u * cK * c.b
                                 - 0.5 * cK ** 2 * c.var_lane(U) * u * u) for U in Us])
            out.append((cK * c.u_k_common, Us, ps, B))
        return out

    def _phi(self, u, D=0.0):
        parts = self._node_parts(u, D)
        u2 = u * u
        gain = sum(lp.c for lp in self.lanes) * D
        extra = np.exp(-0.5 * u2 * (self.u_rel_K * gain) ** 2)
        if self.approx:
            cross = 0.0
            for i in range(len(parts)):
                for j in range(i + 1, len(parts)):
                    cross += 2.0 * parts[i][0] * parts[j][0] * self.lanes[i].U0 * self.lanes[j].U0
            phi = np.exp(-0.5 * u2 * cross) * extra
            for g, Us, ps, B in parts:
                phi = phi * (ps[:, None] * B * np.exp(-0.5 * u2[None, :] * (g * Us)[:, None] ** 2)).sum(axis=0)
            return phi
        # exact: sum over the product of the lanes' posterior nodes; the common term (sum_i g_i U_i)^2 couples them
        import itertools
        head, last = parts[:-1], parts[-1]
        gL, UL, pL, BL = last
        phi = np.zeros(u.size, complex)
        for combo in itertools.product(*[range(len(pt[1])) for pt in head]):
            pre = np.ones(u.size, complex)
            w = 1.0
            sgu = 0.0
            for (g, Us, ps, B), k in zip(head, combo):
                pre = pre * B[k]
                w *= ps[k]
                sgu += g * Us[k]
            tot = sgu + gL * UL                                      # per node of the last lane
            phi += w * pre * (pL[:, None] * BL * np.exp(-0.5 * u2[None, :] * tot[:, None] ** 2)).sum(axis=0)
        return phi * extra

    def _grid(self, x_lo, x_hi, D=0.0):
        m, v = self.mean_var(D)
        sd = math.sqrt(v)
        amax = max(float(np.max(np.abs(self._lane_terms(lp)[1]))) for lp in self.lanes)
        P = 2.0 * (max(abs(x_lo - m), abs(x_hi - m)) + 40.0 * sd + 40.0 * amax)
        h = 2.0 * math.pi / P
        n = int(math.ceil(math.sqrt(-2.0 * math.log(1e-15)) / self._sig_min() / h))
        return h, (np.arange(n) + 0.5) * h

    def tail_fn(self, x_lo, x_hi, D=0.0):
        """Callable x -> P(S > x | D), exact for x in [x_lo, x_hi] (one characteristic-function evaluation)."""
        h, u = self._grid(x_lo, x_hi, D)
        phi = np.concatenate([self._phi(u[c0:c0 + 20000], D) for c0 in range(0, u.size, 20000)])

        def f(x):
            return min(max(0.5 + h * float(np.sum((np.exp(-1j * u * x) * phi).imag / u)) / math.pi, 0.0), 1.0)
        return f

    def tail(self, x, D=0.0):
        return self.tail_fn(x, x, D)(x)

    def threshold(self, alpha):
        m, v = self.mean_var()
        sd = math.sqrt(v)
        lo, hi = m - sd, m + 12.0 * sd
        f = self.tail_fn(lo, hi)
        while f(hi) > alpha:
            hi += 6.0 * sd
            f = self.tail_fn(lo, hi)
        return float(brentq(lambda x: f(x) - alpha, lo, hi, xtol=1e-10 * sd, rtol=1e-11))

    def detection_limit(self, t, beta=0.05):
        return L.solve_for_power(lambda D: self.tail(t, D), 1.0 - beta, hi=1.0, tol=1e-6)


def thresholds(pc: PredictiveCombined, alphas):
    """Thresholds for several alphas from one characteristic-function evaluation."""
    m, v = pc.mean_var()
    sd = math.sqrt(v)
    lo, hi = m - sd, m + 12.0 * sd
    f = pc.tail_fn(lo, hi)
    out = []
    for a in alphas:
        h = hi
        while f(h) > a:
            h += 6.0 * sd
            f = pc.tail_fn(lo, h)
        out.append(float(brentq(lambda x: f(x) - a, lo, h, xtol=1e-10 * sd, rtol=1e-11)))
    return out
