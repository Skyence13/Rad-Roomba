"""Exact (Poisson) probabilities of the decision rule, without the Gaussian approximation.

MODEL.md section 3 sets thresholds with normal quantiles. Counts in one gate
or one 1 s cell are small integers, so the achieved error probabilities differ
from the nominal ones. These functions sum the Poisson distributions exactly
for a calibration that is taken as exact (k, b as used by the decision rule);
the Monte Carlo in rrrad.mc adds the calibration draws.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import poisson

from . import model

__all__ = ["comp_flag_probability", "unc_flag_probability"]


def _support(mu, tail=1e-14):
    lo = int(poisson.ppf(tail, mu)) if mu > 0 else 0
    hi = int(poisson.isf(tail, mu)) + 1 if mu > 0 else 0
    return np.arange(max(lo, 0), hi + 1)


def comp_flag_probability(floor_rate, U, T_F, T_U, k, b, alpha, *, u_k=0.0, u_b=0.0, cov_kb=0.0,
                          mode="plug_in") -> float:
    """P(r > r*) for the compensated rule with exact Poisson counts.

    floor_rate: true mean floor rate (blank: k_true*U + b_true; with signal add rho).
    U: true mean reference rate. k, b, u_k, u_b, cov_kb: values used by the rule.
    mode: where u~(0) is evaluated, see rrrad.model.null_reference_rate
    ("plug_in", "pooled" or "true").
    """
    ka = float(model.kappa(alpha))
    n_u = _support(U * T_U)
    p_u = poisson.pmf(n_u, U * T_U) if U * T_U > 0 else np.ones(1)
    if mode != "pooled":
        U_obs = n_u / T_U
        U_thr = model.null_reference_rate(None, T_F, n_u, T_U, k, b, mode, U_true=U)
        r_star = ka * np.sqrt(np.maximum(model.u0sq_comp(U_thr, T_F, T_U, k, b, u_k, u_b, cov_kb), 0.0))
        n_thr = T_F * (k * U_obs + b + r_star)           # flag when N_F > n_thr
        p_flag = poisson.sf(np.floor(n_thr + 1e-12), floor_rate * T_F)
        return float(np.sum(p_u * p_flag) / np.sum(p_u))
    # pooled: the threshold depends on N_F as well, so enumerate the joint distribution
    n_f = _support(floor_rate * T_F)
    p_f = poisson.pmf(n_f, floor_rate * T_F) if floor_rate * T_F > 0 else np.ones(1)
    NF, NU = np.meshgrid(n_f, n_u, indexing="ij")
    U_thr = model.null_reference_rate(NF, T_F, NU, T_U, k, b, "pooled")
    r_star = ka * np.sqrt(np.maximum(model.u0sq_comp(U_thr, T_F, T_U, k, b, u_k, u_b, cov_kb), 0.0))
    flag = model.net_rate(NF, T_F, NU, T_U, k, b) > r_star
    return float(np.sum(np.outer(p_f, p_u) * flag) / (np.sum(p_f) * np.sum(p_u)))


def unc_flag_probability(floor_rate, T_F, B0, T0, alpha, *, sigma_assumed=0.0) -> float:
    """P(F - B0_hat > r*) for the uncompensated rule with exact Poisson counts.

    floor_rate: true mean floor rate at the measurement position (B(1+delta) + rho).
    B0: true rate at the reference position, measured for T0 (np.inf: known exactly).
    The rule plugs the measured B0_hat in for B (the local B is not observable).
    """
    ka = float(model.kappa(alpha))
    if np.isinf(T0):
        b0_hat, p0 = np.array([float(B0)]), np.ones(1)
    else:
        n0 = _support(B0 * T0)
        b0_hat, p0 = n0 / T0, poisson.pmf(n0, B0 * T0)
    r_star = ka * np.sqrt(model.u0sq_unc(b0_hat, T_F, b0_hat, T0, sigma_assumed))
    n_thr = T_F * (b0_hat + r_star)
    p_flag = poisson.sf(np.floor(n_thr + 1e-12), floor_rate * T_F)
    return float(np.sum(p0 * p_flag) / np.sum(p0))
