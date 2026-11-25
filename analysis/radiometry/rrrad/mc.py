"""Monte Carlo of the decision rules of MODEL.md sections 3-5 with Poisson counts.

Truth and decision rule are kept apart:

* truth    - the photon field gives a reference rate U and a floor photon rate
             k_field*U (k_field = k*(1+m), m = spectral/model mismatch), plus the
             floor offset b and any surface signal rho; counts are Poisson.
* rule     - uses a calibration estimate (k_hat, b_hat) = truth + calibration
             error, and the *declared* u(k), u(b), cov(k,b); the threshold is
             evaluated at the observed reference rate (plug-in).

A calibration error is drawn once per simulated calibration and is therefore
common to everything processed with that calibration.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import model

__all__ = ["draw_calibration", "flag_comp", "flag_unc", "point_comp", "point_unc",
           "SurveyLayout", "relative_field", "survey_flags", "simulate_patch_gates",
           "patch_rule_oracle", "patch_rule_cells"]


def draw_calibration(rng, size, k, b, u_k, u_b=0.0, cov_kb=0.0):
    """Calibration estimates (k_hat, b_hat): bivariate normal about the truth."""
    cov = np.array([[u_k**2, cov_kb], [cov_kb, u_b**2]], dtype=float)
    if not np.any(cov):
        return np.full(size, float(k)), np.full(size, float(b))
    e = rng.multivariate_normal([0.0, 0.0], cov, size=size, method="eigh")
    return k + e[..., 0], b + e[..., 1]


def flag_comp(N_F, T_F, N_U, T_U, k_hat, b_hat, u_k, u_b, cov_kb, alpha, mode="plug_in", U_true=None):
    """Compensated decision r > r*. mode selects where u~(0) is evaluated
    (rrrad.model.null_reference_rate). Returns (flag, r, r_star)."""
    r = model.net_rate(N_F, T_F, N_U, T_U, k_hat, b_hat)
    U_obs = model.null_reference_rate(N_F, T_F, N_U, T_U, k_hat, b_hat, mode, U_true)
    v0 = model.u0sq_comp(U_obs, T_F, T_U, k_hat, b_hat, u_k, u_b, cov_kb)
    r_star = model.kappa(alpha) * np.sqrt(np.maximum(v0, 0.0))
    return r > r_star, r, r_star


def flag_unc(N_F, T_F, B0_hat, T0, sigma_assumed, alpha):
    """Uncompensated decision F - B0_hat > r*, with B0_hat plugged in for the local B."""
    r = np.asarray(N_F, float) / T_F - B0_hat
    r_star = model.kappa(alpha) * np.sqrt(model.u0sq_unc(B0_hat, T_F, B0_hat, T0, sigma_assumed))
    return r > r_star, r, r_star


def point_comp(rng, n, B_gamma, T_F, *, k=1.0, b=0.0, rel_u_k_fit=0.0, rel_u_spec=0.0, u_b=0.0,
               cov_kb=0.0, tu_over_tf=1.0, alpha=0.05, rho=0.0, eps=0.0, spectral_bias=None,
               declare_spec=True, mode="plug_in"):
    """n independent (calibration, measurement) trials of the compensated rule.

    B_gamma: nominal floor photon rate k*U. rho: true floor net rate from the
    surface. eps: fraction of rho that also appears in the reference (leakage).
    rel_u_spec: standard deviation of the relative mismatch m (drawn per trial)
    unless spectral_bias fixes m. declare_spec=False leaves the mismatch out of
    the u(k) the rule uses. Returns the fraction of trials flagged.
    """
    U = B_gamma / k
    T_U = T_F * tu_over_tf
    m = rng.normal(0.0, rel_u_spec, n) if spectral_bias is None else np.full(n, float(spectral_bias))
    k_hat, b_hat = draw_calibration(rng, n, k, b, rel_u_k_fit * k, u_b, cov_kb)
    N_F = rng.poisson(np.maximum((k * (1.0 + m) * U + b + rho) * T_F, 0.0))
    N_U = rng.poisson((U + eps * rho) * T_U, n)
    u_k_decl = k * np.hypot(rel_u_k_fit, rel_u_spec if declare_spec else 0.0)
    flag, _, _ = flag_comp(N_F, T_F, N_U, T_U, k_hat, b_hat, u_k_decl, u_b, cov_kb, alpha, mode, U + eps * rho)
    return float(np.mean(flag))


def point_unc(rng, n, B, T_F, *, T0=60.0, sigma_delta=0.0, sigma_assumed=None, alpha=0.05, rho=0.0):
    """n independent trials of the uncompensated rule.

    The local background is B*(1+delta), delta ~ N(0, sigma_delta) (clipped at -1);
    B0 is measured once per trial for T0 at the reference position (rate B).
    """
    sigma_assumed = sigma_delta if sigma_assumed is None else sigma_assumed
    delta = np.maximum(rng.normal(0.0, sigma_delta, n), -1.0) if sigma_delta > 0 else np.zeros(n)
    B0_hat = B * np.ones(n) if np.isinf(T0) else rng.poisson(B * T0, n) / T0
    N_F = rng.poisson((B * (1.0 + delta) + rho) * T_F)
    flag, _, _ = flag_unc(N_F, T_F, B0_hat, T0, sigma_assumed, alpha)
    return float(np.mean(flag))


# --------------------------------------------------------------------------
# Whole-trailer survey: false flags per survey in structured fields
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SurveyLayout:
    """Serpentine survey of a length x width floor by an n_lanes head; one decision cell per lane per cell_len."""
    length: float = 16.0
    width: float = 2.5
    v: float = 0.10
    cell_len: float = 0.10
    pitch: float = 0.0875
    n_lanes: int = 4
    turn_time: float = 20.0

    @property
    def n_tracks(self) -> int:
        return int(np.floor(self.width / self.pitch / self.n_lanes)) * self.n_lanes

    @property
    def n_x(self) -> int:
        return int(round(self.length / self.cell_len))

    @property
    def n_cells(self) -> int:
        return self.n_tracks * self.n_x

    @property
    def dwell(self) -> float:
        return self.cell_len / self.v

    def cells(self):
        """x (m), visit time t (s) and physical lane index of every cell, flattened."""
        x1 = (np.arange(self.n_x) + 0.5) * self.cell_len
        track = np.arange(self.n_tracks)
        p = track // self.n_lanes                               # pass index
        t_pass = self.length / self.v + self.turn_time
        along = np.where((p % 2 == 0)[:, None], x1[None, :], self.length - x1[None, :])
        t = p[:, None] * t_pass + along / self.v
        x = np.broadcast_to(x1[None, :], t.shape)
        lane = np.broadcast_to((track % self.n_lanes)[:, None], t.shape)
        return x.ravel(), t.ravel(), lane.ravel()


def relative_field(x, t, *, length=16.0, gradient=0.0, step=0.0, step_from=14.0,
                   time_amp=0.0, time_period=600.0, x_ref=None):
    """Photon field relative to its value at the reference position (x_ref, t = 0).

    gradient: fractional end-to-end linear change along the trailer.
    step: fractional step applied for x >= step_from (e.g. near the door).
    time_amp, time_period: sinusoidal time variation.
    """
    x_ref = length / 2.0 if x_ref is None else x_ref

    def spatial(xx):
        return 1.0 + gradient * (np.asarray(xx, float) / length - 0.5) + step * (np.asarray(xx, float) >= step_from)

    f = spatial(x) * (1.0 + time_amp * np.sin(2.0 * np.pi * np.asarray(t, float) / time_period))
    return f / spatial(x_ref)


def survey_flags(rng, n_surveys, layout: SurveyLayout, B_gamma, field: dict, *, k=1.0, b=0.0,
                 rel_u_k_fit=0.0, rel_u_spec=0.0, u_b=0.0, tu_over_tf=1.0, alpha=0.05,
                 T0=60.0, sigma_assumed=0.0, spectral_bias=None, mode="plug_in", chunk=200):
    """False flags per survey (clean floor) for both estimators in the same simulated fields.

    Per survey: one spectral mismatch m (common to all lanes) and one fit error
    per physical lane; one B0 measurement for the uncompensated rule.
    Returns dict with integer arrays 'comp' and 'unc' (flags per survey) and
    'sigma_delta_equiv', the rms relative deviation of the field from B0's.
    """
    x, t, lane = layout.cells()
    f = relative_field(x, t, length=layout.length, **field)
    T_F = layout.dwell
    T_U = T_F * tu_over_tf
    U_nom = B_gamma / k
    out_c, out_u = [], []
    done = 0
    while done < n_surveys:
        n = min(chunk, n_surveys - done)
        m = rng.normal(0.0, rel_u_spec, (n, 1)) if spectral_bias is None else np.full((n, 1), float(spectral_bias))
        e_fit = rng.normal(0.0, rel_u_k_fit, (n, layout.n_lanes)) if rel_u_k_fit > 0 else np.zeros((n, layout.n_lanes))
        k_hat = (k * (1.0 + e_fit))[:, lane]
        b_hat = b + (rng.normal(0.0, u_b, (n, layout.n_lanes))[:, lane] if u_b > 0 else 0.0)
        U = U_nom * f[None, :]
        N_U = rng.poisson(np.broadcast_to(U * T_U, (n, f.size)))
        N_F = rng.poisson((k * (1.0 + m) * U + b) * T_F)
        u_k_decl = k * np.hypot(rel_u_k_fit, rel_u_spec)
        fc, _, _ = flag_comp(N_F, T_F, N_U, T_U, k_hat, b_hat, u_k_decl, u_b, 0.0, alpha, mode, U)
        B0 = B_gamma * (1.0 + m) + b
        B0_hat = B0 if np.isinf(T0) else rng.poisson(np.broadcast_to(B0 * T0, (n, 1))) / T0
        fu, _, _ = flag_unc(N_F, T_F, B0_hat, T0, sigma_assumed, alpha)
        out_c.append(fc.sum(axis=1))
        out_u.append(fu.sum(axis=1))
        done += n
    Bloc = B_gamma * f + b
    return {"comp": np.concatenate(out_c), "unc": np.concatenate(out_u),
            "sigma_delta_equiv": float(np.sqrt(np.mean((Bloc / (B_gamma + b) - 1.0) ** 2)))}


# --------------------------------------------------------------------------
# Moving patch: gate-level counts
# --------------------------------------------------------------------------
def simulate_patch_gates(rng, n_trials, Wmat, edges, *, B_gamma, K, D_p, k=1.0, b=0.0, m=0.0, delta=0.0):
    """Gate-level Poisson counts N_F, N_U of shape (n_trials, n_lanes, n_gates).

    Wmat: gate weights from rrrad.patch.gate_weights (s). m: relative transfer
    mismatch; delta: relative field offset (scalar or array of n_trials) from
    the nominal B_gamma, seen by both floor and reference.
    """
    dur = np.diff(np.asarray(edges, float))[None, None, :]
    scale = (1.0 + np.asarray(delta, float)).reshape(-1, 1, 1)
    mm = np.asarray(m, float).reshape(-1, 1, 1)
    U = (B_gamma / k) * scale
    lam_F = (k * (1.0 + mm) * U + b) * dur + K * D_p * Wmat[None, :, :]
    shape = (n_trials,) + Wmat.shape
    N_F = rng.poisson(np.broadcast_to(lam_F, shape))
    N_U = rng.poisson(np.broadcast_to(U * dur, shape))
    return N_F, N_U


def patch_rule_oracle(N_F, N_U, edges, mask, *, estimator, alpha, k_hat=1.0, b_hat=0.0, u_k=0.0,
                      u_b=0.0, B0_hat=None, T0=np.inf, sigma_assumed=0.0, mode="plug_in"):
    """MODEL.md section 5 rule: one decision on the sum over the gates and lanes in mask."""
    dur = np.diff(np.asarray(edges, float))
    T_S = float(np.sum(mask * dur[None, :]))
    nf = np.sum(N_F * mask[None], axis=(1, 2))
    if estimator == "comp":
        nu = np.sum(N_U * mask[None], axis=(1, 2))
        return flag_comp(nf, T_S, nu, T_S, k_hat, b_hat, u_k, u_b, 0.0, alpha, mode)[0]
    return flag_unc(nf, T_S, B0_hat, T0, sigma_assumed, alpha)[0]


def patch_rule_cells(N_F, N_U, edges, Wmat, n, offset, *, estimator, alpha, k_hat=1.0, b_hat=0.0,
                     u_k=0.0, u_b=0.0, B0_hat=None, T0=np.inf, sigma_assumed=0.0, mode="plug_in"):
    """Fixed map-cell rule: per lane, consecutive cells of n gates; detected if any cell that
    overlaps the patch is flagged. Returns (detected, n_cells_tested)."""
    dur = np.diff(np.asarray(edges, float))
    g = (dur.size - offset) // n * n
    sl = slice(offset, offset + g)
    T_c = float(dur[sl][:n].sum())

    def cells(a):
        return a[..., sl].reshape(a.shape[:-1] + (-1, n)).sum(axis=-1)

    w_c = cells(Wmat)
    nf = cells(N_F)
    if estimator == "comp":
        kh = np.asarray(k_hat, float).reshape(-1, 1, 1)
        bh = np.asarray(b_hat, float).reshape(-1, 1, 1)
        fl = flag_comp(nf, T_c, cells(N_U), T_c, kh, bh, u_k, u_b, 0.0, alpha, mode)[0]
    else:
        fl = flag_unc(nf, T_c, np.asarray(B0_hat, float).reshape(-1, 1, 1), T0, sigma_assumed, alpha)[0]
    hit = w_c > 0
    return np.any(fl & hit[None], axis=(1, 2)), int(hit.sum())
