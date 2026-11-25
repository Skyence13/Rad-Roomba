#!/usr/bin/env python3
"""Step 2 - analytic comparison of compensated and uncompensated detectability at equal dwell
(MODEL.md sections 3 and 4). All inputs are assumptions from common.py / report section 2."""
import numpy as np

from common import (ALPHA, ALPHA_SIDAK, B_OFF_ALPHA, B_OFF_BETA, BETA, C, DOSE_RATES, DWELLS, K_ALPHA_CASES,
                    K_CASES, K_NOM, K_REF, LAYOUT, LEVELS, MISSION_ALLOWANCE, REL_UK, REL_UK_NOM, S_ALPHA, S_BETA,
                    SIGMAS, T0, TU_RATIOS, U_B, U_REL_K, U_REL_K_ALPHA, bgamma, fmt, md_table, plt, savefig,
                    update_summary, write_csv)
from rrrad import model as m

CONFIGS = {   # name: (label, kind, parameters)
    "unc_s00": ("Uncompensated, σ_δ = 0 (uniform field)", "unc", dict(sigma_delta=0.0)),
    "unc_s10": ("Uncompensated, σ_δ = 10 %", "unc", dict(sigma_delta=0.10)),
    "unc_s30": ("Uncompensated, σ_δ = 30 %", "unc", dict(sigma_delta=0.30)),
    "comp_matched": ("Compensated, matched reference (k = 1)", "comp", dict(k=1.0, tu_over_tf=1.0, rel_u_k=REL_UK_NOM)),
    "comp_pool4": ("Compensated, k = 1, four references pooled (T_U/T_F = 4)", "comp",
                   dict(k=1.0, tu_over_tf=4.0, rel_u_k=REL_UK_NOM)),
    "comp_ref10x": ("Compensated, 10× more sensitive reference (k = 0.1)", "comp",
                    dict(k=0.1, tu_over_tf=1.0, rel_u_k=REL_UK_NOM)),
}


def dhash(cfg, H, T, K=K_NOM, alpha=ALPHA, beta=BETA, u_rel_K=U_REL_K, key="D_hash"):
    _, kind, p = CONFIGS[cfg] if isinstance(cfg, str) else cfg
    Bg = bgamma(H)
    if kind == "unc":
        return m.unc_limits(Bg + B_OFF_BETA, T, K, T0=T0, u_rel_K=u_rel_K, alpha=alpha, beta=beta, **p)[key]
    return m.comp_limits(Bg, T, K, b=B_OFF_BETA, u_b=U_B, u_rel_K=u_rel_K, alpha=alpha, beta=beta, **p)[key]


# ---------------- full grids (machine readable) ----------------
rows = []
for H in DOSE_RATES:
    for T in DWELLS:
        for kname, k in K_REF.items():
            for ruk in REL_UK:
                for tr in TU_RATIOS:
                    for an, a in (("0.05", ALPHA), ("sidak", ALPHA_SIDAK)):
                        o = m.comp_limits(bgamma(H), T, K_NOM, k=k, b=B_OFF_BETA, rel_u_k=ruk, u_b=U_B,
                                          tu_over_tf=tr, u_rel_K=U_REL_K, alpha=a, beta=BETA)
                        rows.append((H, T, kname, k, ruk, tr, an, f"{a:.4g}", *(f"{float(o[x]):.5g}" for x in
                                                                               ("u0sq", "r_star", "r_hash", "D_star", "D_hash"))))
write_csv("analytic_comp_grid.csv", ["dose_rate_uSv_h", "T_F_s", "reference", "k", "rel_u_k", "TU_over_TF", "alpha_mode",
                                     "alpha", "u0sq", "r_star_cps", "r_hash_cps", "D_star_Bq_cm2_K24", "D_hash_Bq_cm2_K24"], rows)
rows = []
for H in DOSE_RATES:
    for T in DWELLS:
        for s in SIGMAS:
            for t0 in (10.0, 60.0, 600.0):
                for an, a in (("0.05", ALPHA), ("sidak", ALPHA_SIDAK)):
                    o = m.unc_limits(bgamma(H) + B_OFF_BETA, T, K_NOM, sigma_delta=s, T0=t0, u_rel_K=U_REL_K, alpha=a, beta=BETA)
                    rows.append((H, T, s, t0, an, f"{a:.4g}", *(f"{float(o[x]):.5g}" for x in
                                                                ("u0sq", "r_star", "r_hash", "D_star", "D_hash"))))
write_csv("analytic_unc_grid.csv", ["dose_rate_uSv_h", "T_F_s", "sigma_delta", "T0_s", "alpha_mode", "alpha", "u0sq",
                                    "r_star_cps", "r_hash_cps", "D_star_Bq_cm2_K24", "D_hash_Bq_cm2_K24"], rows)

# ---------------- headline table: D# at equal dwell ----------------
HH = [0.1, 0.3, 1.0, 3.0]
rows, csvrows = [], []
for cfg, (label, _, _) in CONFIGS.items():
    for T in DWELLS:
        vals = [float(dhash(cfg, H, T)) for H in HH]
        csvrows.append((cfg, T, "0.05", *(f"{v:.4g}" for v in vals)))
        csvrows.append((cfg, T, "sidak", *(f"{float(dhash(cfg, H, T, alpha=ALPHA_SIDAK)):.4g}" for H in HH)))
        if T in (1.0, 10.0, 100.0):
            rows.append((label, T, *vals))
write_csv("headline_dhash.csv", ["config", "T_F_s", "alpha_mode"] + [f"D_hash_at_{h}_uSv_h" for h in HH], csvrows)
md_table("headline", ["Estimator", "T_F (s)"] + [f"D# at {h} µSv/h" for h in HH], rows)
rows = [(CONFIGS[c][0], *(f"{fmt(dhash(c, H, 1.0))} / {fmt(dhash(c, H, 1.0, alpha=ALPHA_SIDAK))}" for H in HH)) for c in CONFIGS]
md_table("single_pass", ["Estimator (T_F = 1 s)"] + [f"{h} µSv/h" for h in HH], rows)
rows = [(CONFIGS[c][0], *(f"{fmt(dhash(c, H, 2.0))} / {fmt(dhash(c, H, 2.0, alpha=ALPHA_SIDAK))}" for H in HH)) for c in CONFIGS]
md_table("two_pass", ["Estimator (T_F = 2 s)"] + [f"{h} µSv/h" for h in HH], rows)

# ---------------- break-even sigma_delta ----------------
rows, csvrows = [], []
for T in (1.0, 10.0, 100.0):
    for kname, k in K_REF.items():
        for tr in (1.0, 4.0):
            for ruk in (0.0, 0.03, 0.10):
                v = [float(m.breakeven_sigma_delta(bgamma(H), T, k=k, b=B_OFF_BETA, rel_u_k=ruk, u_b=U_B, tu_over_tf=tr, T0=T0))
                     for H in DOSE_RATES]
                csvrows.append((T, kname, k, tr, ruk, *(f"{x:.4f}" for x in v)))
                if tr == 1.0 and ruk == REL_UK_NOM and T in (1.0, 100.0):
                    rows.append((T, k, *(f"{100*x:.0f} %" if x > 0 else "0 (always wins)" for x in v)))
write_csv("breakeven_sigma_delta.csv", ["T_F_s", "reference", "k", "TU_over_TF", "rel_u_k"]
          + [f"sigma_BE_at_{h}_uSv_h" for h in DOSE_RATES], csvrows)
md_table("breakeven", ["T_F (s)", "k"] + [f"{h} µSv/h" for h in DOSE_RATES], rows)

# ---------------- high-field floor set by u(k) ----------------
rows, csvrows = [], []
for ruk in (0.01, 0.03, 0.05, 0.10):
    fl = [float(m.highfield_floor_activity(bgamma(H), K_NOM, ruk, U_REL_K)) for H in DOSE_RATES]
    # floor is linear in H: dose rate at which the floor equals each level, for each K
    hmax = {K: {lv: val / float(m.highfield_floor_activity(bgamma(1.0), K, ruk, U_REL_K)) for lv, val in LEVELS.items()}
            for K in K_CASES}
    csvrows.append((ruk, *(f"{x:.4g}" for x in fl), *(f"{hmax[K][lv]:.4g}" for K in K_CASES for lv in LEVELS)))
    rows.append((f"{100*ruk:.0f} %", *fl[2:], hmax[K_NOM]["goal"], hmax[100.0]["goal"]))
write_csv("highfield_floor.csv", ["rel_u_k"] + [f"floor_D_hash_K24_at_{h}_uSv_h" for h in DOSE_RATES]
          + [f"max_uSv_h_for_{lv}_K{K:g}" for K in K_CASES for lv in LEVELS], csvrows)
md_table("floor", ["u(k)/k"] + [f"Floor at {h} µSv/h" for h in DOSE_RATES[2:]]
         + ["Max µSv/h for floor ≤ 0.20 (K = 24)", "Max µSv/h for floor ≤ 0.20 (K = 100)"], rows)

# ---------------- dwell required ----------------
rows, csvrows = [], []
for cfg, (label, _, _) in CONFIGS.items():
    for K in K_CASES:
        for lv, val in LEVELS.items():
            for an, a in (("0.05", ALPHA), ("sidak", ALPHA_SIDAK)):
                tt = [m.dwell_to_reach(val, lambda T: float(dhash(cfg, H, T, K=K, alpha=a))) for H in HH]
                csvrows.append((cfg, K, lv, val, an, *(f"{t:.4g}" for t in tt)))
                if lv == "goal" and an == "0.05" and K in (24.0, 100.0):
                    rows.append((label, K, *tt))
write_csv("dwell_required.csv", ["config", "K", "level", "level_Bq_cm2", "alpha_mode"] + [f"dwell_s_at_{h}_uSv_h" for h in HH], csvrows)
md_table("dwell", ["Estimator", "K"] + [f"T_F (s) at {h} µSv/h" for h in HH], rows)

# ---------------- K required for a single / double pass ----------------
rows, csvrows = [], []
for cfg, (label, _, _) in CONFIGS.items():
    for T in (1.0, 2.0):
        for an, a in (("0.05", ALPHA), ("sidak", ALPHA_SIDAK)):
            kk = [K_NOM * float(dhash(cfg, H, T, alpha=a)) / LEVELS["goal"] for H in HH]   # D# is exactly proportional to 1/K
            csvrows.append((cfg, T, an, *(f"{x:.4g}" for x in kk)))
            if an == "0.05" and T == 1.0:
                rows.append((label, *kk))
write_csv("K_required.csv", ["config", "T_F_s", "alpha_mode"] + [f"K_for_D_hash_0.20_at_{h}_uSv_h" for h in HH], csvrows)
md_table("K_required", ["Estimator (T_F = 1 s)"] + [f"K needed at {h} µSv/h" for h in HH], rows)

# ---------------- scan + stationary recount (two-stage rule) ----------------
n = LAYOUT.n_cells
a_total = -np.expm1(np.log1p(-MISSION_ALLOWANCE) / n)       # allowed per-cell probability of a confirmed false flag
rows, csvrows = [], []
for cfg in ("unc_s00", "comp_matched", "comp_ref10x"):
    for H in (0.1, 1.0):
        for n_rc in (5.0, 20.0, 100.0):
            a1 = n_rc / n
            a2 = min(a_total / a1, 0.5)
            for T2 in (10.0, 30.0):
                d1 = float(dhash(cfg, H, 1.0, alpha=a1, beta=0.025))
                d2 = float(dhash(cfg, H, T2, alpha=a2, beta=0.025))
                csvrows.append((cfg, H, n_rc, f"{a1:.4g}", f"{a2:.4g}", T2, f"{d1:.4g}", f"{d2:.4g}", f"{max(d1, d2):.4g}",
                                f"{n_rc * T2:.0f}"))
                if T2 == 30.0 and cfg == "comp_matched":
                    rows.append((CONFIGS[cfg][0], H, n_rc, f"{a1:.2g}", d1, d2, max(d1, d2), n_rc * T2 / 60.0))
write_csv("two_stage.csv", ["config", "dose_rate_uSv_h", "expected_false_recounts", "alpha_scan", "alpha_recount", "T_recount_s",
                            "D_hash_scan", "D_hash_recount", "D_hash_overall", "expected_recount_dwell_s"], csvrows)
md_table("two_stage", ["Estimator", "µSv/h", "Expected false recounts per trailer", "α scan", "D# scan (1 s)",
                       "D# recount (30 s)", "D# overall", "Recount dwell (min)"], rows)

# ---------------- alpha channel ----------------
rows, csvrows = [], []
k_alpha = S_ALPHA / S_BETA      # alpha-channel photon counts per reference count for a matched reference tile
for Ka in K_ALPHA_CASES:
    for H in (0.1, 1.0):
        v = []
        for T in DWELLS:
            o = m.comp_limits(S_ALPHA * H, T, Ka, k=k_alpha, b=B_OFF_ALPHA, rel_u_k=0.10, u_b=0.003,
                              u_rel_K=U_REL_K_ALPHA, alpha=ALPHA, beta=BETA)
            v.append(float(o["D_hash"]))
        csvrows.append((Ka, H, *(f"{x:.4g}" for x in v)))
        rows.append((Ka, H, *v))
write_csv("alpha_channel.csv", ["K_alpha", "dose_rate_uSv_h"] + [f"D_hash_T{t:g}s" for t in DWELLS], csvrows)
md_table("alpha_channel", ["K_α", "µSv/h"] + [f"D# at {t:g} s" for t in DWELLS], rows)
counts_02 = K_ALPHA_CASES[1] * 0.20 * 1.0

# ---------------- figures ----------------
Hx = np.geomspace(0.05, 10, 60)
style = {"unc_s00": (C["unc"], "-"), "unc_s10": (C["unc"], "--"), "unc_s30": (C["unc"], ":"),
         "comp_matched": (C["comp"], "-"), "comp_pool4": (C["sky"], "-"), "comp_ref10x": (C["comp2"], "-")}
fig, axs = plt.subplots(1, 3, figsize=(11, 3.5), sharey=True)
for ax, T in zip(axs, (1.0, 10.0, 100.0)):
    for cfg, (label, _, _) in CONFIGS.items():
        ax.plot(Hx, dhash(cfg, Hx, T), color=style[cfg][0], ls=style[cfg][1], lw=1.6, label=label)
    for val in LEVELS.values():
        ax.axhline(val, color=C["level"], lw=0.8, ls="-.")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_ylim(0.03, 30)
    ax.set_title(f"T_F = {T:g} s"); ax.set_xlabel("ambient dose rate (µSv/h)")
axs[0].set_ylabel("D#  (Bq/cm², K = 24, α = β = 0.05)")
axs[0].text(0.052, 0.41, "0.40", fontsize=7, color=C["level"]); axs[0].text(0.052, 0.305, "0.30", fontsize=7, color=C["level"])
axs[0].text(0.052, 0.155, "0.20", fontsize=7, color=C["level"])
axs[2].legend(fontsize=7, loc="upper left")
savefig(fig, "fig03_dhash_vs_field.png")

fig, axs = plt.subplots(1, 2, figsize=(9.2, 3.4))
for (kname, k), col in zip(K_REF.items(), (C["comp"], C["alt"], C["comp2"])):
    for T, ls in ((1.0, "-"), (30.0, "--")):
        axs[0].plot(Hx, 100 * m.breakeven_sigma_delta(bgamma(Hx), T, k=k, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, T0=T0),
                    color=col, ls=ls, label=f"k = {k:g}, T_F = {T:g} s")
axs[0].set_xscale("log"); axs[0].set_yscale("log"); axs[0].set_ylim(1, 200)
axs[0].set_xlabel("ambient dose rate (µSv/h)"); axs[0].set_ylabel("break-even σ_δ (%)")
axs[0].set_title("Compensation wins above the line (u(k)/k = 3 %)"); axs[0].legend(fontsize=7)
kk = np.geomspace(0.03, 1.5, 50)
ideal = float(dhash("unc_s00", 1.0, 1.0))
for tr, col in zip(TU_RATIOS, (C["comp"], C["sky"], C["comp3"])):
    d = [float(m.comp_limits(bgamma(1.0), 1.0, K_NOM, k=x, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, tu_over_tf=tr,
                             u_rel_K=U_REL_K)["D_hash"]) / ideal for x in kk]
    axs[1].plot(1 / kk, d, color=col, label=f"T_U/T_F = {tr:g}")
axs[1].axhline(1.0, color=C["unc"], lw=1); axs[1].text(0.7, 0.975, "uncompensated, uniform field", fontsize=7, color=C["unc"])
axs[1].set_ylim(0.95, 1.55)
axs[1].set_xscale("log"); axs[1].set_xlabel("reference counts per floor photon count (1/k)")
axs[1].set_ylabel("D# compensated / D# uncompensated (σ_δ = 0)")
axs[1].set_title("Value of a more sensitive reference (1 µSv/h, 1 s)"); axs[1].legend(fontsize=7)
savefig(fig, "fig04_breakeven_reference.png")

Tx = np.geomspace(0.5, 3000, 80)
fig, axs = plt.subplots(1, 3, figsize=(11, 3.5), sharey=True)
for ax, H in zip(axs, (0.1, 1.0, 3.0)):
    ax.plot(Tx, dhash("unc_s00", H, Tx), color=C["unc"], lw=1.6, label="uncompensated, σ_δ = 0")
    ax.plot(Tx, dhash("unc_s10", H, Tx), color=C["unc"], lw=1.6, ls="--", label="uncompensated, σ_δ = 10 %")
    for ruk, ls in ((0.0, ":"), (0.01, "-."), (0.03, "-"), (0.10, "--")):
        ax.plot(Tx, m.comp_limits(bgamma(H), Tx, K_NOM, k=1.0, b=B_OFF_BETA, rel_u_k=ruk, u_b=U_B, u_rel_K=U_REL_K)["D_hash"],
                color=C["comp"], ls=ls, lw=1.4, label=f"compensated k = 1, u(k)/k = {100*ruk:g} %")
    for val in LEVELS.values():
        ax.axhline(val, color=C["level"], lw=0.8, ls="-.")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_ylim(0.01, 30)
    ax.set_title(f"{H:g} µSv/h"); ax.set_xlabel("dwell T_F (s)")
axs[0].set_ylabel("D#  (Bq/cm², K = 24)"); axs[0].legend(fontsize=7, loc="lower left")
savefig(fig, "fig05_dhash_vs_dwell.png")

g = lambda c, H, T, **kw: fmt(dhash(c, H, T, **kw))
update_summary(
    alpha_sidak=f"{ALPHA_SIDAK:.3g}", kappa_sidak=fmt(m.kappa(ALPHA_SIDAK)), n_cells=str(n),
    d1_unc_01=g("unc_s00", 0.1, 1), d1_comp_01=g("comp_matched", 0.1, 1), d1_ref10_01=g("comp_ref10x", 0.1, 1),
    d1_unc_1=g("unc_s00", 1, 1), d1_comp_1=g("comp_matched", 1, 1), d1_ref10_1=g("comp_ref10x", 1, 1),
    d1_unc30_1=g("unc_s30", 1, 1), d1_unc10_1=g("unc_s10", 1, 1),
    d1s_unc_01=g("unc_s00", 0.1, 1, alpha=ALPHA_SIDAK), d1s_comp_01=g("comp_matched", 0.1, 1, alpha=ALPHA_SIDAK),
    d30_comp_1=g("comp_matched", 1, 30), d100_comp_1=g("comp_matched", 1, 100), d30_ref10_1=g("comp_ref10x", 1, 30),
    d30_comp_01=g("comp_matched", 0.1, 30), d10_comp_01=g("comp_matched", 0.1, 10), d10_unc_01=g("unc_s00", 0.1, 10),
    d30_unc10_1=g("unc_s10", 1, 30), d30_unc30_1=g("unc_s30", 1, 30), d100_comp_3=g("comp_matched", 3, 100),
    penalty_matched=fmt(float(dhash("comp_matched", 1, 1)) / float(dhash("unc_s00", 1, 1))),
    penalty_ref10=fmt(float(dhash("comp_ref10x", 1, 1)) / float(dhash("unc_s00", 1, 1))),
    penalty_pool4=fmt(float(dhash("comp_pool4", 1, 1)) / float(dhash("unc_s00", 1, 1))),
    be_01_k1=f"{100*float(m.breakeven_sigma_delta(bgamma(0.1), 1, k=1, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, T0=T0)):.0f}",
    be_1_k1=f"{100*float(m.breakeven_sigma_delta(bgamma(1), 1, k=1, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, T0=T0)):.0f}",
    be_3_k1=f"{100*float(m.breakeven_sigma_delta(bgamma(3), 1, k=1, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, T0=T0)):.0f}",
    be_1_k01=f"{100*float(m.breakeven_sigma_delta(bgamma(1), 1, k=0.1, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, T0=T0)):.1f}",
    be_1_k1_T100=f"{100*float(m.breakeven_sigma_delta(bgamma(1), 100, k=1, b=B_OFF_BETA, rel_u_k=REL_UK_NOM, u_b=U_B, T0=T0)):.1f}",
    floor_3pc_1=fmt(m.highfield_floor_activity(bgamma(1), K_NOM, 0.03, U_REL_K)),
    floor_3pc_3=fmt(m.highfield_floor_activity(bgamma(3), K_NOM, 0.03, U_REL_K)),
    hmax_3pc_K24=fmt(0.20 / float(m.highfield_floor_activity(bgamma(1.0), K_NOM, 0.03, U_REL_K))),
    hmax_1pc_K24=fmt(0.20 / float(m.highfield_floor_activity(bgamma(1.0), K_NOM, 0.01, U_REL_K))),
    hmax_3pc_K100=fmt(0.20 / float(m.highfield_floor_activity(bgamma(1.0), 100.0, 0.03, U_REL_K))),
    T02_unc_01=fmt(m.dwell_to_reach(0.2, lambda T: float(dhash("unc_s00", 0.1, T)))),
    T02_comp_01=fmt(m.dwell_to_reach(0.2, lambda T: float(dhash("comp_matched", 0.1, T)))),
    T02_ref10_01=fmt(m.dwell_to_reach(0.2, lambda T: float(dhash("comp_ref10x", 0.1, T)))),
    T02_comp_1=fmt(m.dwell_to_reach(0.2, lambda T: float(dhash("comp_matched", 1.0, T)))),
    T02_ref10_1=fmt(m.dwell_to_reach(0.2, lambda T: float(dhash("comp_ref10x", 1.0, T)))),
    T02_comp_03=fmt(m.dwell_to_reach(0.2, lambda T: float(dhash("comp_matched", 0.3, T)))),
    Kreq_unc_01=fmt(K_NOM * float(dhash("unc_s00", 0.1, 1)) / 0.2), Kreq_comp_01=fmt(K_NOM * float(dhash("comp_matched", 0.1, 1)) / 0.2),
    Kreq_comp_1=fmt(K_NOM * float(dhash("comp_matched", 1, 1)) / 0.2),
    Kreq_comp_01_2pass=fmt(K_NOM * float(dhash("comp_matched", 0.1, 2)) / 0.2),
    urelK_factor=fmt(1 / (1 - m.kappa(0.05) ** 2 * U_REL_K**2)),
    v02_unc_01=fmt(0.1 / m.dwell_to_reach(0.2, lambda T: float(dhash("unc_s00", 0.1, T)))),
    v02_comp_01=fmt(0.1 / m.dwell_to_reach(0.2, lambda T: float(dhash("comp_matched", 0.1, T)))),
    d2_unc_01=g("unc_s00", 0.1, 2), d2_comp_01=g("comp_matched", 0.1, 2), d2_ref10_01=g("comp_ref10x", 0.1, 2),
    d1_K100_comp_01=g("comp_matched", 0.1, 1, K=100.0), d1_K100_comp_1=g("comp_matched", 1, 1, K=100.0),
    d1_K8_comp_01=g("comp_matched", 0.1, 1, K=8.0), d1_K50_comp_01=g("comp_matched", 0.1, 1, K=50.0),
    d30_K100_comp_1=g("comp_matched", 1, 30, K=100.0),
    T03_comp_01=fmt(m.dwell_to_reach(0.3, lambda T: float(dhash("comp_matched", 0.1, T)))),
    T04_comp_01=fmt(m.dwell_to_reach(0.4, lambda T: float(dhash("comp_matched", 0.1, T)))),
    T03_comp_1=fmt(m.dwell_to_reach(0.3, lambda T: float(dhash("comp_matched", 1.0, T)))),
    T04_comp_1=fmt(m.dwell_to_reach(0.4, lambda T: float(dhash("comp_matched", 1.0, T)))),
    alpha_d10=fmt(float(m.comp_limits(S_ALPHA * 0.1, 10.0, 6.0, k=k_alpha, b=B_OFF_ALPHA, rel_u_k=0.10, u_b=0.003, u_rel_K=U_REL_K_ALPHA)["D_hash"])),
    alpha_d1=fmt(float(m.comp_limits(S_ALPHA * 0.1, 1.0, 6.0, k=k_alpha, b=B_OFF_ALPHA, rel_u_k=0.10, u_b=0.003, u_rel_K=U_REL_K_ALPHA)["D_hash"])),
    urelK_alpha_factor=fmt(1 / (1 - m.kappa(0.05) ** 2 * U_REL_K_ALPHA**2)),
    alpha_counts_02=fmt(counts_02), k_alpha=fmt(k_alpha, 2),
)
print("s2: analytic study written")
