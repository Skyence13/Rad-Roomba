#!/usr/bin/env python3
"""Step 4 - leakage of floor surface signal into the reference channel (report section 6)."""
import numpy as np

from common import (ALPHA, B_OFF_BETA, BETA, C, K_REF, REL_UK_NOM, SEED, U_B, bgamma, fmt, md_table, plt, savefig,
                    update_summary, write_csv)
from rrrad import mc, model as m

rng = np.random.default_rng(SEED + 4)
EPS = [0.0, 0.01, 0.02, 0.05, 0.10, 0.20]
CASES = [(0.1, 1.0), (1.0, 30.0)]        # (uSv/h, T_F)


def rho_hash(H, T, k, eps):
    return m.leak_detection_limit_rate(bgamma(H) / k, T, T, k, B_OFF_BETA, REL_UK_NOM * k, U_B, 0.0, eps, ALPHA, BETA)


rows, tab = [], []
for kname, k in K_REF.items():
    for eps in EPS:
        ratios = [rho_hash(H, T, k, eps) / rho_hash(H, T, k, 0.0) for H, T in CASES]
        rows.append((kname, k, eps, f"{1 - k * eps:.4f}", *(f"{x:.4f}" for x in ratios)))
        if eps > 0:
            tab.append((k, f"{100*eps:g} %", f"{100*(k*eps):.1f} %", *ratios))
write_csv("leakage.csv", ["reference", "k", "eps", "signal_retained_1_minus_k_eps"]
          + [f"true_detectable_over_no_leak_{H}uSvh_{T:g}s" for H, T in CASES], rows)
md_table("leakage", ["k", "ε", "Signal removed by subtraction (k·ε)", "Detectable activity ÷ no-leak value, 0.1 µSv/h, 1 s",
                     "Same, 1 µSv/h, 30 s"], tab)

# calibration: K fitted with compensation enabled absorbs eps_cal; a field emitter with another eps is biased
cal_rows = []
for k in (1.0, 0.1):
    for eps_cal in (0.0, 0.02):
        for eps_field in (0.02, 0.05, 0.10):
            cal_rows.append((k, eps_cal, eps_field, (1 - k * eps_field) / (1 - k * eps_cal) - 1.0))
write_csv("leakage_calibration_bias.csv", ["k", "eps_calibration_source", "eps_field_emitter", "relative_bias_of_reported_D"],
          [(a, b, c, f"{d:.4f}") for a, b, c, d in cal_rows])
md_table("leakage_cal", ["k", "ε of calibration source", "ε of field emitter", "Bias of reported D"],
         [(a, f"{100*b:g} %", f"{100*c:g} %", f"{100*d:+.1f} %") for a, b, c, d in cal_rows if a == 1.0])

# precision of the test: eps_hat = (U_on - U_off)/(F_on - F_off), equal times T with and without a surface source
test_rows = []
for H in (0.1, 1.0):
    for src in (20.0, 100.0, 500.0):
        for eps in (0.02, 0.10):
            U0, F0 = bgamma(H), bgamma(H) + B_OFF_BETA
            var_T = (2 * U0 + eps * src) + eps**2 * (2 * F0 + src)        # variance * T * src^2
            T_need = var_T / (0.005 * src) ** 2
            test_rows.append((H, src, eps, T_need))
write_csv("leakage_test_time.csv", ["dose_rate_uSv_h", "source_net_floor_rate_cps", "eps", "time_each_s_for_u_eps_0.005"],
          [(a, b, c, f"{d:.4g}") for a, b, c, d in test_rows])
md_table("leakage_test", ["µSv/h", "Source net floor rate (s⁻¹)", "ε", "Count time with and without source for u(ε) = 0.005 (s each)"],
         [(a, b, f"{100*c:g} %", d) for a, b, c, d in test_rows if b > 20.0])

# Monte Carlo check of the bias and of the detection probability at the computed limit
H, T, k, eps = 1.0, 30.0, 1.0, 0.10
rho = rho_hash(H, T, k, eps)
pd = mc.point_comp(rng, 200_000, bgamma(H), T, k=k, b=B_OFF_BETA, rel_u_k_fit=REL_UK_NOM, u_b=U_B, alpha=ALPHA,
                   rho=rho, eps=eps, mode="true")
rho0 = rho_hash(H, T, k, 0.0)
pd_naive = mc.point_comp(rng, 200_000, bgamma(H), T, k=k, b=B_OFF_BETA, rel_u_k_fit=REL_UK_NOM, u_b=U_B, alpha=ALPHA,
                         rho=rho0, eps=eps, mode="true")

fig, ax = plt.subplots(figsize=(5.2, 3.4))
ee = np.linspace(0, 0.25, 26)
for (kname, k), col in zip(K_REF.items(), (C["comp"], C["alt"], C["comp2"])):
    ax.plot(100 * ee, [rho_hash(1.0, 30.0, k, e) / rho_hash(1.0, 30.0, k, 0.0) for e in ee], color=col, label=f"k = {k:g}")
    ax.plot(100 * ee, 1 / (1 - k * ee), color=col, ls=":", lw=1)
ax.set_xlabel("ε: reference counts per floor count from the surface source (%)")
ax.set_ylabel("true detectable activity ÷ no-leak value")
ax.set_title("Leakage into the reference (1 µSv/h, 30 s); dotted: 1/(1−kε)")
ax.legend(fontsize=8)
savefig(fig, "fig09_leakage.png")

update_summary(leak_pd=f"{pd:.3f}", leak_pd_naive=f"{pd_naive:.3f}", leak_ratio_k1_10=fmt(rho / rho0),
               leak_T_100_2pc=fmt([r[3] for r in test_rows if r[0] == 0.1 and r[1] == 100.0 and r[2] == 0.02][0]))
print("s4: leakage written")
