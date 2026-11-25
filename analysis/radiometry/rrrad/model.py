"""Count-processing model of analysis/radiometry/MODEL.md, sections 2-4.

Every function is a direct transcription of an equation in MODEL.md; the
section is named in each docstring. All functions broadcast over numpy arrays.

Symbols (MODEL.md section 1)
    N_F, T_F   floor gross counts, floor live time (s)
    N_U, T_U   reference gross counts, reference live time (s)
    F, U       rates N_F/T_F, N_U/T_U (1/s)
    k, b       transfer coefficient (dimensionless) and offset (1/s)
    u_k, u_b, cov_kb   standard uncertainties and covariance of (k, b)
    K          response (1/s per Bq/cm2);  u_rel_K its relative standard uncertainty
    alpha, beta   per-decision error probabilities;  kappa(p) = k_{1-p}

Nothing here is a measured property of a detector.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

__all__ = [
    "Calibration", "kappa", "sidak_alpha", "net_rate", "u2_counting", "u2_transfer",
    "estimate", "u0sq_comp", "u0sq_unc", "null_reference_rate", "decision_threshold",
    "detection_limit_rate", "detection_limit_rate_numeric",
    "detection_limit_activity", "detection_limit_activity_numeric",
    "comp_limits", "unc_limits", "breakeven_sigma_delta", "highfield_floor_activity",
    "dwell_to_reach", "leak_detection_limit_rate",
]


@dataclass(frozen=True)
class Calibration:
    """Calibration record of MODEL.md section 1 for one lane and class."""
    k: float
    b: float
    u_k: float = 0.0
    u_b: float = 0.0
    cov_kb: float = 0.0
    K: float = 1.0
    u_rel_K: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def kappa(p):
    """Standard-normal quantile k_{1-p} (MODEL.md section 3)."""
    return norm.isf(np.asarray(p, dtype=float))


def sidak_alpha(allowance, n_decisions):
    """Per-decision alpha from a per-mission allowance (MODEL.md section 3).

    allowance = P(at least one false investigation in the mission) for
    n_decisions independent decision areas:  alpha = 1 - (1 - allowance)**(1/n).
    """
    allowance = np.asarray(allowance, dtype=float)
    n = np.asarray(n_decisions, dtype=float)
    if np.any((allowance <= 0) | (allowance >= 1)) or np.any(n < 1):
        raise ValueError("allowance must be in (0,1) and n_decisions >= 1")
    return -np.expm1(np.log1p(-allowance) / n)


# --------------------------------------------------------------------------
# Section 2: net rate and its uncertainty (compensated estimator)
# --------------------------------------------------------------------------
def net_rate(N_F, T_F, N_U, T_U, k, b):
    """r = F - k*U - b  (MODEL.md section 2). Signed; never clipped."""
    return np.asarray(N_F, float) / T_F - k * np.asarray(N_U, float) / T_U - b


def u2_counting(N_F, T_F, N_U, T_U, k):
    """Counting variance N_F/T_F^2 + k^2 N_U/T_U^2  (MODEL.md section 2)."""
    return np.asarray(N_F, float) / np.square(T_F) + np.square(k) * np.asarray(N_U, float) / np.square(T_U)


def u2_transfer(U, u_k, u_b=0.0, cov_kb=0.0):
    """Transfer-calibration variance U^2 u^2(k) + u^2(b) + 2 U cov(k,b)  (section 2)."""
    U = np.asarray(U, float)
    return np.square(U) * np.square(u_k) + np.square(u_b) + 2.0 * U * cov_kb


def estimate(N_F, T_F, N_U, T_U, cal: Calibration, cov_FU=0.0):
    """Full section-2 estimate. Returns a dict of arrays.

    u_stat_* contain the counting terms only; u_total_* add the transfer
    calibration and, for D, the response term D^2 u_rel^2(K).
    cov_FU is Cov(F,U) in (1/s)^2 (default zero, as in MODEL.md).
    """
    U = np.asarray(N_U, float) / T_U
    r = net_rate(N_F, T_F, N_U, T_U, cal.k, cal.b)
    v_stat = u2_counting(N_F, T_F, N_U, T_U, cal.k) - 2.0 * cal.k * cov_FU
    v_cal = u2_transfer(U, cal.u_k, cal.u_b, cal.cov_kb)
    D = r / cal.K
    u_stat_D = np.sqrt(v_stat) / cal.K
    u_total_D = np.sqrt((v_stat + v_cal) / cal.K**2 + np.square(D) * cal.u_rel_K**2)
    return {"r": r, "u_stat_r": np.sqrt(v_stat), "u_total_r": np.sqrt(v_stat + v_cal),
            "D": D, "u_stat_D": u_stat_D, "u_total_D": u_total_D}


# --------------------------------------------------------------------------
# Sections 3 and 4: null-hypothesis variance for both estimators
# --------------------------------------------------------------------------
def u0sq_comp(U, T_F, T_U, k, b=0.0, u_k=0.0, u_b=0.0, cov_kb=0.0):
    """u~^2(0) of the compensated estimator (MODEL.md section 3).

    (k U + b)/T_F + k^2 U/T_U + U^2 u^2(k) + u^2(b) + 2 U cov(k,b)
    """
    U = np.asarray(U, float)
    return (k * U + b) / T_F + np.square(k) * U / T_U + u2_transfer(U, u_k, u_b, cov_kb)


def u0sq_unc(B, T_F, B0=None, T0=np.inf, sigma_delta=0.0):
    """u~_unc^2(0) of the uncompensated estimator (MODEL.md section 4).

    B/T_F + B0/T0 + sigma_delta^2 B^2 ; B0 defaults to B.
    """
    B = np.asarray(B, float)
    B0 = B if B0 is None else np.asarray(B0, float)
    return B / T_F + B0 / T0 + np.square(sigma_delta) * np.square(B)


def null_reference_rate(N_F, T_F, N_U, T_U, k, b=0.0, mode="plug_in", U_true=None):
    """Reference rate at which u~^2(0) is evaluated when the true U is not known.

    MODEL.md section 3 writes u~^2(0) with U but does not say which estimate to use.
      "plug_in"  U = N_U/T_U from the same gate set (literal reading). The threshold then
                 moves with the same fluctuation as r, which inflates the false-alarm rate.
      "pooled"   U = (N_F - b T_F + N_U)/(k T_F + T_U), the estimate of U under the null
                 hypothesis from both streams (exact maximum likelihood for b = 0). The
                 first-order coupling between r and its threshold cancels.
      "true"     the true rate (simulation oracle).
    """
    if mode == "plug_in":
        return np.asarray(N_U, float) / T_U
    if mode == "pooled":
        return np.maximum(np.asarray(N_F, float) - b * T_F + np.asarray(N_U, float), 0.0) / (k * T_F + T_U)
    if mode == "true":
        return np.broadcast_to(np.asarray(U_true, float), np.shape(N_U)).astype(float)
    raise ValueError(f"unknown mode {mode!r}")


def decision_threshold(u0sq, alpha=0.05):
    """r* = k_{1-alpha} u~(0)  (MODEL.md section 3)."""
    return kappa(alpha) * np.sqrt(u0sq)


def detection_limit_rate(u0sq, T_F, alpha=0.05, beta=0.05):
    """r# solving r# = r* + k_{1-beta} sqrt(u~^2(0) + r#/T_F)  (section 3).

    Closed form for any alpha, beta (positive root of the quadratic); reduces
    to 2 r* + kappa^2/T_F when alpha == beta.
    """
    u0sq = np.asarray(u0sq, float)
    ka, kb = kappa(alpha), kappa(beta)
    rs = ka * np.sqrt(u0sq)
    p = 2.0 * rs + kb**2 / T_F
    q = rs**2 - kb**2 * u0sq
    return 0.5 * (p + np.sqrt(np.maximum(p * p - 4.0 * q, 0.0)))


def detection_limit_activity(u0sq, T_F, K, u_rel_K=0.0, alpha=0.05, beta=0.05):
    """D# (Bq/cm2) including u_rel(K)  (MODEL.md section 3, generalised to alpha != beta).

    Solves  y = y* + k_{1-beta} sqrt(u~^2(0)/K^2 + y/(K T_F) + y^2 u_rel^2(K)).
    For alpha == beta this is (2 r* + kappa^2/T_F) / (K (1 - kappa^2 u_rel^2)).
    Returns +inf where k_{1-beta} u_rel(K) >= 1 (limit not defined).
    """
    u0sq, T_F, K, u_rel_K = np.broadcast_arrays(*[np.asarray(a, float) for a in (u0sq, T_F, K, u_rel_K)])
    ka, kb = kappa(alpha), kappa(beta)
    ys = ka * np.sqrt(u0sq) / K
    a = 1.0 - kb**2 * u_rel_K**2
    p = 2.0 * ys + kb**2 / (K * T_F)
    q = ys**2 - kb**2 * u0sq / K**2
    with np.errstate(divide="ignore", invalid="ignore"):
        y = (p + np.sqrt(np.maximum(p * p - 4.0 * a * q, 0.0))) / (2.0 * a)
    return np.where(a > 0, y, np.inf)


def detection_limit_rate_numeric(u0sq, T_F, alpha=0.05, beta=0.05):
    """Scalar numerical solve of the section-3 implicit equation (cross-check)."""
    return float(detection_limit_activity_numeric(u0sq, T_F, 1.0, 0.0, alpha, beta))


def detection_limit_activity_numeric(u0sq, T_F, K, u_rel_K=0.0, alpha=0.05, beta=0.05):
    """Scalar numerical solve (Brent) of the implicit D# equation; inf if undefined."""
    ka, kb = float(kappa(alpha)), float(kappa(beta))
    if kb * u_rel_K >= 1.0:
        return float("inf")
    ys = ka * np.sqrt(u0sq) / K

    def f(y):
        return y - ys - kb * np.sqrt(u0sq / K**2 + y / (K * T_F) + (y * u_rel_K) ** 2)

    hi = max(ys, 1e-12) * 2 + 1.0 / (K * T_F)
    while f(hi) < 0:
        hi *= 2.0
        if hi > 1e30:
            return float("inf")
    return float(brentq(f, ys, hi, xtol=1e-14, rtol=1e-13))


# --------------------------------------------------------------------------
# Convenience wrappers used by the study
# --------------------------------------------------------------------------
def comp_limits(B_gamma, T_F, K, *, k=1.0, b=0.0, rel_u_k=0.0, u_b=0.0, cov_kb=0.0,
                tu_over_tf=1.0, u_rel_K=0.0, alpha=0.05, beta=0.05):
    """Compensated r*, r#, D*, D# for a floor photon rate B_gamma = k U (1/s).

    The reference rate is U = B_gamma / k ; rel_u_k = u(k)/k.
    """
    B_gamma = np.asarray(B_gamma, float)
    U = B_gamma / k
    v0 = u0sq_comp(U, T_F, np.asarray(T_F, float) * tu_over_tf, k, b, rel_u_k * k, u_b, cov_kb)
    rs = decision_threshold(v0, alpha)
    return {"u0sq": v0, "r_star": rs, "r_hash": detection_limit_rate(v0, T_F, alpha, beta),
            "D_star": rs / K, "D_hash": detection_limit_activity(v0, T_F, K, u_rel_K, alpha, beta)}


def unc_limits(B, T_F, K, *, sigma_delta=0.0, T0=np.inf, B0=None, u_rel_K=0.0, alpha=0.05, beta=0.05):
    """Uncompensated r*, r#, D*, D# (MODEL.md section 4) for local background B."""
    v0 = u0sq_unc(B, T_F, B0, T0, sigma_delta)
    rs = decision_threshold(v0, alpha)
    return {"u0sq": v0, "r_star": rs, "r_hash": detection_limit_rate(v0, T_F, alpha, beta),
            "D_star": rs / K, "D_hash": detection_limit_activity(v0, T_F, K, u_rel_K, alpha, beta)}


def breakeven_sigma_delta(B_gamma, T_F, *, k=1.0, b=0.0, rel_u_k=0.0, u_b=0.0, cov_kb=0.0,
                          tu_over_tf=1.0, T0=np.inf):
    """sigma_delta at which u~_unc^2(0) == u~_comp^2(0) at equal T_F.

    With B = B_gamma + b on both sides the floor term cancels, leaving
    sigma^2 B^2 + B/T0 = k B_gamma/T_U + B_gamma^2 rel_u_k^2 + u_b^2 + 2 U cov_kb.
    Returns 0 where the uncompensated variance is already larger at sigma = 0.
    """
    B_gamma = np.asarray(B_gamma, float)
    B = B_gamma + b
    U = B_gamma / k
    extra_comp = np.square(k) * U / (np.asarray(T_F, float) * tu_over_tf) + u2_transfer(U, rel_u_k * k, u_b, cov_kb)
    extra_unc0 = B / T0
    return np.sqrt(np.maximum(extra_comp - extra_unc0, 0.0)) / B


def highfield_floor_activity(B_gamma, K, rel_u_k, u_rel_K=0.0, alpha=0.05, beta=0.05):
    """Limit of D# for T_F, T_U -> infinity: only B_gamma * u(k)/k remains (u_b = 0)."""
    v0 = np.square(np.asarray(B_gamma, float) * rel_u_k)
    return detection_limit_activity(v0, np.inf, K, u_rel_K, alpha, beta)


def dwell_to_reach(target_D, dhash_of_T, t_lo=1e-2, t_hi=1e6):
    """Smallest T_F (s) with D#(T_F) <= target_D, for a decreasing callable; inf if unreachable."""
    if dhash_of_T(t_hi) > target_D:
        return float("inf")
    if dhash_of_T(t_lo) <= target_D:
        return t_lo
    log_t = brentq(lambda lt: float(dhash_of_T(10.0 ** lt)) - target_D,
                   np.log10(t_lo), np.log10(t_hi), xtol=1e-10)
    return float(10.0 ** log_t)


def leak_detection_limit_rate(U, T_F, T_U, k, b=0.0, u_k=0.0, u_b=0.0, cov_kb=0.0, eps=0.0,
                              alpha=0.05, beta=0.05):
    """True floor net rate rho# that is detected with probability 1-beta when a fraction eps of the
    floor surface signal also appears in the reference (rate eps*rho), scalar numerical solve.

    Mean of r:      rho (1 - k eps)
    Variance of r:  (k U + b + rho)/T_F + k^2 (U + eps rho)/T_U + transfer terms at U + eps rho
    Threshold:      k_{1-alpha} u~(0) evaluated at the reference rate actually present, U + eps rho
    Returns inf when k*eps >= 1 (the subtraction removes the whole signal).
    """
    ka, kb = float(kappa(alpha)), float(kappa(beta))
    if k * eps >= 1.0:
        return float("inf")

    def f(rho):
        Ur = U + eps * rho
        v0 = u0sq_comp(Ur, T_F, T_U, k, b, u_k, u_b, cov_kb)
        return rho * (1.0 - k * eps) - ka * np.sqrt(v0) - kb * np.sqrt(v0 + rho / T_F)

    hi = 1.0
    while f(hi) < 0:
        hi *= 2.0
        if hi > 1e12:
            return float("inf")
    return float(brentq(f, 0.0, hi, xtol=1e-12, rtol=1e-12))
