#!/usr/bin/env python3
"""Step 3 - Monte Carlo and exact-Poisson validation of the decision rules (MODEL.md sections 3-5)."""
import numpy as np

from common import (ALPHA, ALPHA_SIDAK, B_OFF_BETA, BETA, C, K_NOM, LAYOUT, MISSION_ALLOWANCE, SEED, T0, U_B, U_REL_K,
                    bgamma, fmt, md_table, plt, savefig, update_summary, write_csv)
from rrrad import exact, mc, model as m, patch as p

rng = np.random.default_rng(SEED + 3)
N = 200_000
FIT, SPEC = 0.01, 0.03                 # relative fit uncertainty of k and spectral mismatch (standard deviations)
RUK = float(np.hypot(FIT, SPEC))
HH, TT = [0.1, 0.3, 1.0, 3.0], [1.0, 2.0, 10.0, 30.0, 100.0]
LAB = {"plug_in": "plug-in (same gates)", "true": "at true/smoothed U", "pooled": "pooled"}

# ------------------------------------------------------------------ (a) point validation, alpha = beta = 0.05
rows, tab = [], []
for H in HH:
    Bg = bgamma(H)
    for T in TT:
        for name, k in (("comp k=1", 1.0), ("comp k=0.1", 0.1)):
            kw = dict(k=k, b=B_OFF_BETA, rel_u_k_fit=FIT, rel_u_spec=SPEC, u_b=U_B)
            rho = float(m.comp_limits(Bg, T, 1.0, k=k, b=B_OFF_BETA, rel_u_k=RUK, u_b=U_B)["r_hash"])
            for mode in ("plug_in", "true", "pooled"):
                # the offset estimate carries u(b): draw_calibration handles it through u_b
                fa = mc.point_comp(rng, N, Bg, T, alpha=ALPHA, mode=mode, **kw)
                pd = mc.point_comp(rng, N, Bg, T, alpha=ALPHA, mode=mode, rho=rho, **kw)
                rows.append((H, T, name, mode, ALPHA, f"{fa:.5f}", 1 - BETA, f"{pd:.5f}", f"{rho:.5g}", N))
                if T in (1.0, 30.0) and H in (0.1, 1.0) and name == "comp k=1":
                    tab.append((H, T, f"compensated k = 1, ũ(0) {LAB[mode]}", f"{fa:.3f}", f"{pd:.3f}"))
        s = 0.20
        rho = float(m.unc_limits(Bg + B_OFF_BETA, T, 1.0, sigma_delta=s, T0=T0)["r_hash"])
        fa = mc.point_unc(rng, N, Bg + B_OFF_BETA, T, T0=T0, sigma_delta=s, alpha=ALPHA)
        pd = mc.point_unc(rng, N, Bg + B_OFF_BETA, T, T0=T0, sigma_delta=s, alpha=ALPHA, rho=rho)
        fa0 = mc.point_unc(rng, N, Bg + B_OFF_BETA, T, T0=T0, sigma_delta=s, sigma_assumed=0.0, alpha=ALPHA)
        rows.append((H, T, "unc sigma=0.2 declared", "B0 plug-in", ALPHA, f"{fa:.5f}", 1 - BETA, f"{pd:.5f}", f"{rho:.5g}", N))
        rows.append((H, T, "unc sigma=0.2 not declared", "B0 plug-in", ALPHA, f"{fa0:.5f}", "", "", "", N))
        if T in (1.0, 30.0) and H in (0.1, 1.0):
            tab.append((H, T, "uncompensated, σ_δ = 20 % declared", f"{fa:.3f}", f"{pd:.3f}"))
            tab.append((H, T, "uncompensated, σ_δ = 20 % present but not declared", f"{fa0:.3f}", "—"))
write_csv("mc_point_validation.csv", ["dose_rate_uSv_h", "T_F_s", "estimator", "u0_evaluation", "alpha_nominal", "alpha_achieved",
                                      "pdet_nominal", "pdet_achieved_at_analytic_r_hash", "r_hash_cps", "n_trials"], rows)
md_table("mc_points", ["µSv/h", "T_F (s)", "Rule", "Achieved false-alarm probability (nominal 0.050)",
                       "Achieved detection probability at analytic r# (nominal 0.950)"], tab)
arr = np.array([(float(r[5]), float(r[7])) for r in rows if r[2].startswith("comp") and r[3] == "true"])
arr_p = np.array([(float(r[5]), float(r[7])) for r in rows if r[2].startswith("comp") and r[3] == "plug_in"])
arr_u = np.array([(float(r[5]), float(r[7])) for r in rows if r[2] == "unc sigma=0.2 declared"])

# ------------------------------------------------------------------ (b) exact Poisson at mission-level alpha
rows, tab = [], []
for H in HH:
    Bg = bgamma(H)
    B = Bg + B_OFF_BETA
    for T in (1.0, 2.0, 10.0):
        r = {mode: exact.comp_flag_probability(B, Bg, T, T, 1.0, B_OFF_BETA, ALPHA_SIDAK, mode=mode) / ALPHA_SIDAK
             for mode in ("plug_in", "true", "pooled")}
        ru = exact.unc_flag_probability(B, T, B, T0, ALPHA_SIDAK) / ALPHA_SIDAK
        # nominal alpha that restores the mission-level false-alarm probability, and the exact detectable rate
        fa_c = lambda a: exact.comp_flag_probability(B, Bg, T, T, 1.0, B_OFF_BETA, a, mode="true")
        fa_u = lambda a: exact.unc_flag_probability(B, T, B, T0, a)
        ac, au = exact.calibrated_nominal_alpha(ALPHA_SIDAK, fa_c), exact.calibrated_nominal_alpha(ALPHA_SIDAK, fa_u)
        rho_c = exact.detection_rate_exact(lambda x: exact.comp_flag_probability(B + x, Bg, T, T, 1.0, B_OFF_BETA, ac, mode="true"))
        rho_u = exact.detection_rate_exact(lambda x: exact.unc_flag_probability(B + x, T, B, T0, au))
        g_c = float(m.comp_limits(Bg, T, 1.0, b=B_OFF_BETA, alpha=ALPHA_SIDAK)["r_hash"])
        g_u = float(m.unc_limits(B, T, 1.0, T0=T0, alpha=ALPHA_SIDAK)["r_hash"])
        rows.append((H, T, *(f"{r[x]:.4g}" for x in ("plug_in", "true", "pooled")), f"{ru:.4g}", f"{ac:.3g}", f"{au:.3g}",
                     f"{rho_c:.5g}", f"{g_c:.5g}", f"{rho_u:.5g}", f"{g_u:.5g}"))
        tab.append((H, T, r["plug_in"], r["true"], r["pooled"], ru, rho_c / g_c, rho_u / g_u))
write_csv("exact_mission_alpha.csv", ["dose_rate_uSv_h", "T_F_s", "achieved_over_nominal_comp_plug_in",
                                      "achieved_over_nominal_comp_true_U", "achieved_over_nominal_comp_pooled",
                                      "achieved_over_nominal_unc", "nominal_alpha_restoring_comp", "nominal_alpha_restoring_unc",
                                      "r_hash_exact_comp_cps", "r_hash_gaussian_comp_cps", "r_hash_exact_unc_cps",
                                      "r_hash_gaussian_unc_cps"], rows)
md_table("exact_mission", ["µSv/h", "T_F (s)", "Comp., ũ(0) plug-in", "Comp., ũ(0) at true/smoothed U", "Comp., ũ(0) pooled",
                           "Uncompensated", "Exact r# / formula r#, compensated", "Exact r# / formula r#, uncompensated"], tab)
ex = np.array([[float(x) for x in r[2:6]] for r in rows])
ex_ratio = np.array([[float(r[8]) / float(r[9]), float(r[10]) / float(r[11])] for r in rows])

# ------------------------------------------------------------------ (c) false flags per trailer survey
SCEN = {
    "uniform": {},
    "gradient 60 % end to end": {"gradient": 0.6},
    "step +50 % in last 2 m (door)": {"step": 0.5},
    "time variation ±10 %, 10 min": {"time_amp": 0.10, "time_period": 600.0},
    "gradient + step + time": {"gradient": 0.6, "step": 0.5, "time_amp": 0.10, "time_period": 600.0},
}
NS = 1000
rows, tab = [], []
stat = lambda a: (float(a.mean()), float(np.median(a)), float(np.percentile(a, 95)), float(np.mean(a >= 1)))
for H in (0.3, 1.0):
    Bg = bgamma(H)
    for sname, fld in SCEN.items():
        kw = dict(k=1.0, b=B_OFF_BETA, rel_u_k_fit=FIT, rel_u_spec=SPEC, u_b=0.0, T0=T0)
        sig = mc.survey_flags(rng, 1, LAYOUT, Bg, fld, alpha=ALPHA, **kw)["sigma_delta_equiv"]
        runs = [("alpha 0.05; ũ(0) plug-in; unc sigma_delta assumed 0", ALPHA, "plug_in", 0.0),
                ("alpha 0.05; ũ(0) smoothed; unc sigma_delta declared", ALPHA, "true", sig),
                ("alpha Sidak; ũ(0) smoothed; unc sigma_delta declared", ALPHA_SIDAK, "true", sig)]
        for rname, a, mode, sa in runs:
            o = mc.survey_flags(rng, NS, LAYOUT, Bg, fld, alpha=a, mode=mode, sigma_assumed=sa, **kw)
            sc, su = stat(o["comp"]), stat(o["unc"])
            rows.append((H, sname, f"{sig:.4f}", rname, f"{a:.4g}", f"{a * LAYOUT.n_cells:.4g}",
                         *(f"{x:.4g}" for x in sc), *(f"{x:.4g}" for x in su), NS))
            if H == 1.0:
                tab.append((sname, f"{100*sig:.0f} %", rname.replace("alpha", "α").replace("sigma_delta", "σ_δ").replace("unc", "uncomp."),
                            a * LAYOUT.n_cells, sc[0], sc[2], sc[3], su[0], su[2], su[3]))
write_csv("mc_survey_flags.csv", ["dose_rate_uSv_h", "field_scenario", "sigma_delta_equivalent", "rule", "alpha_per_decision",
                                  "expected_flags_nominal", "comp_mean", "comp_median", "comp_p95", "comp_P_ge_1",
                                  "unc_mean", "unc_median", "unc_p95", "unc_P_ge_1", "n_surveys"], rows)
md_table("survey_flags", ["Field along the trailer (1 µSv/h)", "σ_δ equiv.", "Rule", "Nominal expected flags",
                          "Comp. mean", "Comp. 95th pct", "Comp. P(≥1)", "Uncomp. mean", "Uncomp. 95th pct", "Uncomp. P(≥1)"], tab)
srows = rows

# ------------------------------------------------------------------ (d) moving patch, 0.10 m/s, 100 ms gates
head = p.Head()
V, GATE, NT = 0.10, 0.10, 100_000
H = 0.1
Bg = bgamma(H)
seam_y = 0.5 * (head.lane_centres[1] + head.lane_centres[2])
rows, tab = [], []
for area in (10.0, 100.0, 300.0):
    for pos, y in (("lane centre", head.lane_centres[1]), ("seam", seam_y)):
        for ph_name, phase in (("gate edge at patch centre", 0.0), ("patch centre mid-gate", GATE / 2)):
            pt = p.Patch.square(area, y=y)
            ed = p.gate_edges_for_pass(head, pt, V, GATE, phase, margin_gates=8)
            W = p.gate_weights(head, pt, V, ed)
            mask = p.select(W)
            T_S, W_S = p.patch_sum(W, ed, mask)
            mask10 = p.select(W, 0.10 * W.max()) & (W.sum(axis=1, keepdims=True) > 0.10 * W.sum(axis=1).max())
            T_S10, W_S10 = p.patch_sum(W, ed, mask10)
            v_c = m.u0sq_comp(Bg, T_S, T_S, 1.0, B_OFF_BETA, RUK, U_B)
            v_u = m.u0sq_unc(Bg + B_OFF_BETA, T_S, T0=T0)
            d_c, d_u = p.patch_dhash(T_S, W_S, v_c, K_NOM), p.patch_dhash(T_S, W_S, v_u, K_NOM)
            d_c10 = p.patch_dhash(T_S10, W_S10, m.u0sq_comp(Bg, T_S10, T_S10, 1.0, B_OFF_BETA, RUK, U_B), K_NOM)
            # Monte Carlo: gate-level counts; one calibration and one B0 per trial
            k_hat, b_hat = mc.draw_calibration(rng, NT, 1.0, B_OFF_BETA, FIT, U_B)
            mm = rng.normal(0.0, SPEC, NT)
            B0_hat = rng.poisson((Bg + B_OFF_BETA) * T0, NT) / T0
            res = {}
            for tag, Dp in (("fa", 0.0), ("det", d_c)):
                N_F, N_U = mc.simulate_patch_gates(rng, NT, W, ed, B_gamma=Bg, K=K_NOM, D_p=Dp, k=1.0, b=B_OFF_BETA, m=mm)
                res["c_" + tag] = mc.patch_rule_oracle(N_F, N_U, ed, mask, estimator="comp", alpha=ALPHA, k_hat=k_hat,
                                                       b_hat=b_hat, u_k=RUK, u_b=U_B, mode="true", U_true=Bg).mean()
                if tag == "det":      # fixed 1 s map cells per lane, all ten alignments of the cell grid
                    pc = [mc.patch_rule_cells(N_F, N_U, ed, W, 10, off, estimator="comp", alpha=ALPHA, k_hat=k_hat, b_hat=b_hat,
                                              u_k=RUK, u_b=U_B, mode="true", U_true=Bg)[0].mean() for off in range(10)]
                    res["cells_min"], res["cells_max"] = min(pc), max(pc)
            for tag, Dp in (("fa", 0.0), ("det", d_u)):
                N_F, _ = mc.simulate_patch_gates(rng, NT, W, ed, B_gamma=Bg, K=K_NOM, D_p=Dp, k=1.0, b=B_OFF_BETA)
                res["u_" + tag] = mc.patch_rule_oracle(N_F, None, ed, mask, estimator="unc", alpha=ALPHA, B0_hat=B0_hat, T0=T0).mean()
            rows.append((area, pos, ph_name, int(mask.any(axis=1).sum()), int(mask.any(axis=0).sum()), f"{T_S:.3g}", f"{W_S:.4g}",
                         f"{d_c:.4g}", f"{d_c * area * W_S / (pt.lx * pt.ly * 1e4 / 80.0 * head.L / V) :.4g}", f"{d_c * area:.4g}",
                         f"{d_u:.4g}", f"{d_c10:.4g}", f"{res['c_fa']:.4f}", f"{res['c_det']:.4f}", f"{res['cells_min']:.4f}",
                         f"{res['cells_max']:.4f}", f"{res['u_fa']:.4f}", f"{res['u_det']:.4f}", NT))
            tab.append((area, pos, ph_name, f"{int(mask.any(axis=1).sum())} × {int(mask.any(axis=0).sum())}", T_S, W_S, d_c, d_c * area,
                        d_u, d_c10, f"{res['c_fa']:.3f} / {res['c_det']:.3f}", f"{res['cells_min']:.2f}–{res['cells_max']:.2f}",
                        f"{res['u_fa']:.3f} / {res['u_det']:.3f}"))
write_csv("mc_patch.csv", ["patch_area_cm2", "position", "gate_phase", "lanes_summed", "gates_summed", "T_S_s", "W_S_s",
                           "D_hash_patch_comp_Bq_cm2", "activity_seen_at_limit_Bq", "patch_activity_at_limit_Bq",
                           "D_hash_patch_unc_Bq_cm2", "D_hash_patch_comp_excl_minor_overlap", "mc_comp_false_alarm",
                           "mc_comp_detect_at_limit", "mc_comp_cells_detect_min_over_alignment", "mc_comp_cells_detect_max_over_alignment",
                           "mc_unc_false_alarm", "mc_unc_detect_at_limit", "n_trials"], rows)
md_table("patch", ["Patch cm²", "Position", "Gate phase", "Lanes × gates summed", "T_S (s)", "W_S (s)", "D#_p comp. (Bq/cm²)",
                   "Patch activity at D#_p (Bq)", "D#_p uncomp.", "D#_p comp., minor overlaps excluded",
                   "MC comp. false alarm / detection at D#_p", "MC fixed 1 s cells: detection at D#_p over grid alignments",
                   "MC uncomp. false alarm / detection"], tab)
pr = {(float(r[0]), r[1], r[2]): r for r in rows}

# ------------------------------------------------------------------ figures
fig, axs = plt.subplots(1, 2, figsize=(9.6, 3.5))
Bx = np.geomspace(1.0, 400, 40)
for mode, col, lab in (("plug_in", C["unc"], "ũ(0) plug-in (same gates)"), ("true", C["comp"], "ũ(0) at smoothed U"),
                       ("pooled", C["comp2"], "ũ(0) pooled")):
    axs[0].plot(Bx, [exact.comp_flag_probability(b + B_OFF_BETA, b, 1.0, 1.0, 1.0, B_OFF_BETA, ALPHA, mode=mode) / ALPHA for b in Bx],
                color=col, label=lab)
    axs[1].plot(Bx, [max(exact.comp_flag_probability(b + B_OFF_BETA, b, 1.0, 1.0, 1.0, B_OFF_BETA, ALPHA_SIDAK, mode=mode) / ALPHA_SIDAK, 1e-3)
                     for b in Bx], color=col, label=lab)
for ax, a in zip(axs, (ALPHA, ALPHA_SIDAK)):
    ax.plot(Bx, [exact.unc_flag_probability(b + B_OFF_BETA, 1.0, b + B_OFF_BETA, T0, a) / a for b in Bx], color=C["level"], ls="--",
            label="uncompensated")
    ax.axhline(1.0, color="k", lw=0.8)
    ax.set_xscale("log"); ax.set_xlabel("floor photon counts in the 1 s cell (B_γ·T_F)")
axs[1].set_yscale("log")
axs[0].set_ylabel("achieved / nominal false-alarm probability")
axs[0].set_title("nominal α = 0.05"); axs[1].set_title(f"mission-level α = {ALPHA_SIDAK:.2g} (Šidák, n = {LAYOUT.n_cells})")
axs[0].legend(fontsize=7)
savefig(fig, "fig06_achieved_alpha.png")

fig, ax = plt.subplots(figsize=(7.4, 3.6))
names = list(SCEN)
y = np.arange(len(names))
for off, key, col, lab in ((-0.2, "comp_mean", C["comp"], "compensated"), (0.2, "unc_mean", C["unc"], "uncompensated, σ_δ assumed 0")):
    idx = 6 if key == "comp_mean" else 10
    vals = [float([r for r in srows if float(r[0]) == 1.0 and r[1] == n and "plug-in" in r[3]][0][idx]) for n in names]
    ax.barh(y + off, vals, height=0.38, color=col, label=lab)
    for yy, v in zip(y + off, vals):
        ax.text(v * 1.05, yy, f"{v:.0f}", va="center", fontsize=7)
ax.axvline(ALPHA * LAYOUT.n_cells, color="k", lw=0.8)
ax.text(ALPHA * LAYOUT.n_cells * 1.03, len(names) - 0.55, "nominal α·n = 224", fontsize=7)
ax.set_yticks(y, names, fontsize=8); ax.invert_yaxis(); ax.set_xscale("log")
ax.set_xlabel("mean false flags per trailer survey (4480 cells, α = 0.05, 1 µSv/h, clean floor)")
ax.legend(fontsize=7, loc="lower right")
savefig(fig, "fig07_false_flags_per_trailer.png")

fig, axs = plt.subplots(1, 2, figsize=(9.6, 3.3))
for area, col in ((10.0, C["unc"]), (100.0, C["comp"]), (300.0, C["comp2"])):
    pt = p.Patch.square(area, y=head.lane_centres[1])
    t = np.linspace(-1.6, 1.6, 641)
    axs[0].plot(t, p.overlap_length(pt.x + V * t, pt, head.L) * p.lateral_overlap(head, pt)[1] / (head.L * head.W), color=col,
                label=f"{area:g} cm², lane centre")
    pts = p.Patch.square(area, y=seam_y)
    axs[0].plot(t, p.overlap_length(pts.x + V * t, pts, head.L) * p.lateral_overlap(head, pts)[1] / (head.L * head.W), color=col,
                ls="--", lw=1)
axs[0].set_xlabel("time relative to patch centre (s)"); axs[0].set_ylabel("w(t) in the most-covered lane")
axs[0].set_title("Overlap weight, solid: lane centre, dashed: seam"); axs[0].legend(fontsize=7)
lab = [f"{int(a)} cm²\n{pos}" for a in (10.0, 100.0, 300.0) for pos in ("lane centre", "seam")]
dc = [float(pr[(a, pos, "gate edge at patch centre")][7]) for a in (10.0, 100.0, 300.0) for pos in ("lane centre", "seam")]
d10 = [float(pr[(a, pos, "gate edge at patch centre")][11]) for a in (10.0, 100.0, 300.0) for pos in ("lane centre", "seam")]
x = np.arange(len(lab))
axs[1].bar(x - 0.2, dc, 0.38, color=C["comp"], label="sum over all overlapping gates and lanes (MODEL.md §5)")
axs[1].bar(x + 0.2, d10, 0.38, color=C["sky"], label="minor overlaps (< 10 % of peak) excluded")
for val in (0.2, 0.3, 0.4):
    axs[1].axhline(val, color=C["level"], lw=0.8, ls="-.")
axs[1].set_yscale("log"); axs[1].set_xticks(x, lab, fontsize=7)
axs[1].set_ylim(0.15, 60)
axs[1].set_ylabel("patch D#_p (Bq/cm²)")
axs[1].set_title("One pass, 0.1 µSv/h, K = 24, compensated (k = 1)"); axs[1].legend(fontsize=6.5, loc="upper right")
fig.subplots_adjust(wspace=0.3)
savefig(fig, "fig08_moving_patch.png")

gp = lambda a, pos, i: fmt(float(pr[(a, pos, "gate edge at patch centre")][i]))


def sflag(H, scen, rule_key, idx):
    return fmt(float([r for r in srows if float(r[0]) == H and r[1] == scen and rule_key in r[3]][0][idx]))



update_summary(
    mc_true_fa_min=f"{arr[:,0].min():.3f}", mc_true_fa_max=f"{arr[:,0].max():.3f}",
    mc_true_pd_min=f"{arr[:,1].min():.3f}", mc_true_pd_max=f"{arr[:,1].max():.3f}",
    mc_plug_fa_min=f"{arr_p[:,0].min():.3f}", mc_plug_fa_max=f"{arr_p[:,0].max():.3f}",
    mc_plug_pd_min=f"{arr_p[:,1].min():.3f}", mc_plug_pd_max=f"{arr_p[:,1].max():.3f}",
    mc_unc_fa_min=f"{arr_u[:,0].min():.3f}", mc_unc_fa_max=f"{arr_u[:,0].max():.3f}",
    mc_unc_pd_min=f"{arr_u[:,1].min():.3f}", mc_unc_pd_max=f"{arr_u[:,1].max():.3f}",
    ex_plug_max=fmt(ex[:, 0].max()), ex_plug_min=fmt(ex[:, 0].min()), ex_true_max=fmt(ex[:, 1].max()),
    ex_unc_max=fmt(ex[:, 3].max()), ex_plug_01_1=fmt(ex[0, 0]), ex_true_01_1=fmt(ex[0, 1]), ex_unc_01_1=fmt(ex[0, 3]),
    ex_flags_plug_01_1=fmt(ex[0, 0] * ALPHA_SIDAK * LAYOUT.n_cells),
    ex_pooled_pd_01_1=f"{exact.comp_flag_probability(bgamma(0.1) + B_OFF_BETA + float(m.comp_limits(bgamma(0.1), 1.0, 1.0, b=B_OFF_BETA, alpha=ALPHA_SIDAK)['r_hash']), bgamma(0.1), 1.0, 1.0, 1.0, B_OFF_BETA, ALPHA_SIDAK, mode='pooled'):.2f}",
    ex_ratio_c_max=fmt(ex_ratio[:, 0].max()), ex_ratio_u_max=fmt(ex_ratio[:, 1].max()),
    ex_ratio_c_min=fmt(ex_ratio[:, 0].min()), ex_ratio_u_min=fmt(ex_ratio[:, 1].min()),
    sv_uni_comp=sflag(1.0, "uniform", "plug-in", 6), sv_uni_unc=sflag(1.0, "uniform", "plug-in", 10),
    sv_uni_comp_true=sflag(1.0, "uniform", "0.05; ũ(0) smoothed", 6),
    sv_grad_comp=sflag(1.0, "gradient 60 % end to end", "plug-in", 6), sv_grad_unc=sflag(1.0, "gradient 60 % end to end", "plug-in", 10),
    sv_all_comp=sflag(1.0, "gradient + step + time", "plug-in", 6), sv_all_unc=sflag(1.0, "gradient + step + time", "plug-in", 10),
    sv_grad_unc_decl=sflag(1.0, "gradient 60 % end to end", "0.05; ũ(0) smoothed", 10),
    sv_sidak_comp_mean=sflag(1.0, "uniform", "Sidak", 6), sv_sidak_comp_p1=sflag(1.0, "uniform", "Sidak", 9),
    sv_sidak_unc_p1=sflag(1.0, "uniform", "Sidak", 13), sv_sidak_comp_p1_03=sflag(0.3, "uniform", "Sidak", 9),
    sv_sidak_unc_p1_03=sflag(0.3, "uniform", "Sidak", 13),
    sv_sidak_comp_p1_all=sflag(1.0, "gradient + step + time", "Sidak", 9), sv_sidak_unc_p1_all=sflag(1.0, "gradient + step + time", "Sidak", 13),
    p10_lane=gp(10.0, "lane centre", 7), p10_lane_Bq=gp(10.0, "lane centre", 9), p10_seam=gp(10.0, "seam", 7),
    p100_lane=gp(100.0, "lane centre", 7), p100_lane_excl=gp(100.0, "lane centre", 11), p100_seam=gp(100.0, "seam", 7),
    p300_lane=gp(300.0, "lane centre", 7), p300_seam=gp(300.0, "seam", 7), p300_lane_excl=gp(300.0, "lane centre", 11),
    p10_lane_excl=gp(10.0, "lane centre", 11),
    n_trials=f"{N:,}".replace(",", " "), n_surveys=str(NS), n_patch_trials=f"{NT:,}".replace(",", " "),
)
print("s3: Monte Carlo written")
