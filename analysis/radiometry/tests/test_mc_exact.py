"""Monte Carlo and exact-Poisson machinery: consistency with each other and with MODEL.md."""
import numpy as np
import pytest

from rrrad import exact, fields, mc, model, patch as p


def test_exact_matches_gaussian_at_high_counts():
    B, T = 400.0, 10.0
    a = exact.comp_flag_probability(B, B, T, T, 1.0, 0.0, 0.05, mode="true")
    assert a == pytest.approx(0.05, abs=0.004)
    rho = float(model.comp_limits(B, T, 1.0)["r_hash"])
    assert exact.comp_flag_probability(B + rho, B, T, T, 1.0, 0.0, 0.05, mode="true") == pytest.approx(0.95, abs=0.004)
    assert exact.unc_flag_probability(B, T, B, np.inf, 0.05) == pytest.approx(0.05, abs=0.004)
    rho = float(model.unc_limits(B, T, 1.0, T0=60.0)["r_hash"])
    assert exact.unc_flag_probability(B + rho, T, B, 60.0, 0.05) == pytest.approx(0.95, abs=0.004)


def test_mc_matches_exact_low_counts():
    rng = np.random.default_rng(1)
    B, T = 3.3, 1.0
    ex = exact.comp_flag_probability(B + 0.5, B, T, T, 1.0, 0.5, 0.05)
    sim = mc.point_comp(rng, 400_000, B, T, k=1.0, b=0.5, alpha=0.05)
    assert sim == pytest.approx(ex, abs=4 * np.sqrt(ex * (1 - ex) / 400_000))
    ex_u = exact.unc_flag_probability(B, T, B, 60.0, 0.05)
    sim_u = mc.point_unc(rng, 400_000, B, T, T0=60.0, alpha=0.05)
    assert sim_u == pytest.approx(ex_u, abs=4 * np.sqrt(ex_u * (1 - ex_u) / 400_000))


def test_mc_calibration_term_reproduces_analytic_alpha_and_beta():
    # high counts so that discreteness is negligible; calibration term dominant
    rng = np.random.default_rng(2)
    kw = dict(k=0.5, b=1.0, rel_u_k_fit=0.02, rel_u_spec=0.03, u_b=0.05, tu_over_tf=1.0)
    B, T = 300.0, 30.0
    fa = mc.point_comp(rng, 200_000, B, T, alpha=0.05, **kw)
    assert fa == pytest.approx(0.05, abs=0.004)
    lim = model.comp_limits(B, T, 1.0, k=0.5, b=1.0, rel_u_k=np.hypot(0.02, 0.03), u_b=0.05)
    det = mc.point_comp(rng, 200_000, B, T, alpha=0.05, rho=float(lim["r_hash"]), **kw)
    assert det == pytest.approx(0.95, abs=0.004)
    # an undeclared mismatch inflates the false-alarm rate
    fa_bad = mc.point_comp(rng, 200_000, B, T, alpha=0.05, declare_spec=False, **kw)
    assert fa_bad > 0.15


def test_mc_unc_sigma_delta():
    rng = np.random.default_rng(3)
    B, T, s = 300.0, 10.0, 0.2
    assert mc.point_unc(rng, 200_000, B, T, T0=600.0, sigma_delta=s, alpha=0.05) == pytest.approx(0.05, abs=0.006)
    rho = float(model.unc_limits(B, T, 1.0, sigma_delta=s, T0=600.0)["r_hash"])
    assert mc.point_unc(rng, 200_000, B, T, T0=600.0, sigma_delta=s, alpha=0.05, rho=rho) == pytest.approx(0.95, abs=0.006)
    # ignoring a real 20 % non-uniformity: the nominal 5 % becomes tens of per cent
    assert mc.point_unc(rng, 100_000, B, T, T0=600.0, sigma_delta=s, sigma_assumed=0.0, alpha=0.05) > 0.3


def test_leakage_bias():
    # E[r] = rho (1 - k eps)
    rng = np.random.default_rng(4)
    k, eps, rho, B, T = 0.8, 0.10, 20.0, 50.0, 1000.0
    n = 4000
    N_F = rng.poisson((B + rho) * T, n)
    N_U = rng.poisson((B / k + eps * rho) * T, n)
    r = model.net_rate(N_F, T, N_U, T, k, 0.0)
    assert r.mean() == pytest.approx(rho * (1 - k * eps), rel=0.002)


def test_survey_layout_and_field():
    lay = mc.SurveyLayout()
    assert lay.n_tracks == 28 and lay.n_x == 160 and lay.n_cells == 4480 and lay.dwell == pytest.approx(1.0)
    x, t, lane = lay.cells()
    assert x.size == 4480 and set(np.unique(lane)) == {0, 1, 2, 3}
    assert t.max() == pytest.approx(7 * 160 + 6 * lay.turn_time - 0.5, abs=1.0)
    assert np.allclose(mc.relative_field(x, t), 1.0)
    f = mc.relative_field(x, t, gradient=0.6)
    assert f.min() == pytest.approx(0.7, abs=0.01) and f.max() == pytest.approx(1.3, abs=0.01)
    assert np.std(f) == pytest.approx(0.6 / np.sqrt(12), rel=0.01)
    fs = mc.relative_field(np.array([1.0, 15.0]), 0.0, step=0.5)
    assert np.allclose(fs, [1.0, 1.5])


def test_survey_flags_mean_matches_alpha():
    rng = np.random.default_rng(5)
    lay = mc.SurveyLayout()
    out = mc.survey_flags(rng, 100, lay, 200.0, {}, alpha=0.05, T0=np.inf, mode="pooled")
    for key in ("comp", "unc"):
        assert out[key].mean() == pytest.approx(0.05 * lay.n_cells, rel=0.08)
    assert out["sigma_delta_equiv"] == 0.0
    # literal plug-in threshold: mean count follows the exact (inflated) probability
    out_p = mc.survey_flags(rng, 100, lay, 200.0, {}, alpha=0.05, T0=np.inf)
    p_exact = exact.comp_flag_probability(200.0, 200.0, 1.0, 1.0, 1.0, 0.0, 0.05, mode="plug_in")
    assert p_exact > 0.055
    assert out_p["comp"].mean() == pytest.approx(p_exact * lay.n_cells, rel=0.05)
    # gradient: compensated unaffected, uncompensated (sigma assumed 0) floods
    out_g = mc.survey_flags(rng, 50, lay, 200.0, {"gradient": 0.6}, alpha=0.05, T0=np.inf, mode="pooled")
    assert out_g["comp"].mean() == pytest.approx(0.05 * lay.n_cells, rel=0.1)
    assert out_g["unc"].mean() > 5 * out_g["comp"].mean()


def test_threshold_evaluation_modes():
    # MODEL.md section 3 ambiguity: where is u~(0) evaluated?
    B, T = 33.0, 1.0
    a_true = exact.comp_flag_probability(B, B, T, T, 1.0, 0.0, 0.05, mode="true")
    a_plug = exact.comp_flag_probability(B, B, T, T, 1.0, 0.0, 0.05, mode="plug_in")
    a_pool = exact.comp_flag_probability(B, B, T, T, 1.0, 0.0, 0.05, mode="pooled")
    assert a_plug > a_true and a_plug > 0.06          # inflated
    assert abs(a_pool - 0.05) < abs(a_plug - 0.05)    # pooled is closer to nominal
    # first-order prediction: z_eff = kappa / sqrt((1 + (1 + kappa/sqrt(2 B))^2)/2)
    from scipy.stats import norm
    kap = model.kappa(0.05)
    z = kap / np.sqrt((1 + (1 + kap / np.sqrt(2 * B)) ** 2) / 2)
    assert a_plug == pytest.approx(norm.sf(z), rel=0.15)
    # the inflation grows as alpha shrinks (Sidak-level thresholds)
    a_small = 1e-4
    ratio_plug = exact.comp_flag_probability(B, B, T, T, 1.0, 0.0, a_small, mode="plug_in") / a_small
    assert ratio_plug > 5
    # mc agrees with exact for the pooled mode
    rng = np.random.default_rng(11)
    sim = mc.point_comp(rng, 400_000, B, T, alpha=0.05, mode="pooled")
    assert sim == pytest.approx(a_pool, abs=4 * np.sqrt(a_pool * (1 - a_pool) / 400_000))


def test_patch_gate_simulation_sums():
    rng = np.random.default_rng(6)
    H = p.Head()
    pt = p.Patch.square(100.0, y=H.lane_centres[1])
    ed = p.gate_edges_for_pass(H, pt, 0.1, 0.1)
    W = p.gate_weights(H, pt, 0.1, ed)
    N_F, N_U = mc.simulate_patch_gates(rng, 20_000, W, ed, B_gamma=10.0, K=24.0, D_p=2.0, b=0.5)
    assert N_F.shape == (20_000,) + W.shape
    mask = p.select(W)
    T_S, W_S = p.patch_sum(W, ed, mask)
    mean_sum = (N_F * mask[None]).sum(axis=(1, 2)).mean()
    assert mean_sum == pytest.approx(10.5 * T_S + 24.0 * 2.0 * W_S, rel=0.01)
    assert (N_U * mask[None]).sum(axis=(1, 2)).mean() == pytest.approx(10.0 * T_S, rel=0.01)
    det = mc.patch_rule_oracle(N_F, N_U, ed, mask, estimator="comp", alpha=0.05, b_hat=0.5)
    assert 0.0 < det.mean() <= 1.0
    detc, n_cells = mc.patch_rule_cells(N_F, N_U, ed, W, 10, 0, estimator="comp", alpha=0.05,
                                        k_hat=np.ones(20_000), b_hat=np.full(20_000, 0.5))
    assert n_cells >= 2 and 0.0 < detc.mean() <= 1.0


def test_fields_sanity():
    f = fields.representative_fields()
    ore, conc = fields.field_summary(f["ore_equilibrium"]), fields.field_summary(f["concentrate_bare"])
    assert ore["photon_MeV_per_U238_decay"] > 10 * conc["photon_MeV_per_U238_decay"]
    assert ore["kerma_weighted_mean_keV"] > conc["kerma_weighted_mean_keV"]
    assert fields.photon_response_scaled("beta") == pytest.approx(42 * 80 / 101.25)
    # NIST interpolation returns the tabulated points
    assert fields.mu("Al", 0.6) == pytest.approx(0.07802) and fields.mu("PVT", 1.0) == pytest.approx(0.06894)
    # alpha efficiency falls with standoff and with cold (denser) air; U-238 is the weakest
    e = [fields.alpha_eff_4pi("U-238", h) for h in (3, 6, 10, 14)]
    assert all(a > b for a, b in zip(e, e[1:]))
    assert fields.alpha_eff_4pi("U-238", 10, temp_C=-20) < fields.alpha_eff_4pi("U-238", 10)
    assert fields.alpha_eff_4pi("Pu-239", 3.0) == pytest.approx(0.5 * 0.49)       # anchor reproduced
    g = fields.rect_geometry_factor()
    assert 0.5 < g < 0.8 and fields.rect_geometry_factor(h=1e-6) == pytest.approx(1.0, abs=1e-3)
    K = fields.K_beta_by_basis()
    assert K["Cl-36 equivalent (calibration source basis)"] == pytest.approx(24.0)
