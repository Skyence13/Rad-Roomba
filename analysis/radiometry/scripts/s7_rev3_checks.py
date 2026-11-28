#!/usr/bin/env python3
"""Step 7 - numerical checks of MODEL.md revision 3, section 6 (IB-31) and of a candidate revision-4 rule.

(A) weighted sums in the Poisson form; (B) any-lane decision at alpha/m; (C) one exact linear statistic;
low-count alpha channel (N+1 rule, 0.10 minimum weight).  Everything is `calculated` (exact lattice
convolution, Gil-Pelaez, saddlepoint) or `simulated` (Monte Carlo, fixed seeds) with the SYNTHETIC
demonstration coefficients; nothing is measured.  Writes results/rev3_*.csv, results/tables/rev3_*.md,
report/model_rev3_checks.md and summary values for the main report."""
import json
import time

import numpy as np

from common import ALPHA_SIDAK, ROOT, SEED, TABLES, bgamma, fmt, md_table, update_summary, write_csv
from rrrad import linstat as L
from rrrad import rev3 as R

t_start = time.time()
rng = np.random.default_rng(SEED + 7)
DOSES = [0.1, 1.0, 3.0]
DWELLS = [1.0, 10.0]
ALPHAS = [0.05, 1e-3, ALPHA_SIDAK]
BETA = 0.05
WINDOW = 20.0                              # U_null window, multiples of T_F (MODEL.md section 3 minimum)
SEAM = 0.04375                             # lateral offset of a lane centre from a cell centred on a seam
CAL = R.BETA_CAL
CAL0 = CAL.exact_cal()
ALPHA_CAL = R.ALPHA_CAL
REAL = {"realistic: lane centred": 0.0, "realistic: lane 30 mm off centre": 0.030,
        "realistic: cell centred on a seam": SEAM}
S = {}                                     # summary values for the report


def afmt(a):
    return {0.05: "0.05", 1e-3: "1e-3"}.get(a, f"{a:.3g}")


def lane_for(name, T):
    if name in R.PATTERNS:
        return R.pattern_lane(name, T)
    return R.cell_lane_weights(REAL[name], v=0.10 / T)


demo = json.loads((ROOT / "demo_calibration.json").read_text(encoding="utf-8"))
LANE_CALS = []
for ln in demo["lanes"]:
    c = ln["classes"]["beta_window"]
    LANE_CALS.append(R.Cal(k=1.0, b=c["b_cps"], u_k_lane=c["u_k_components"]["fit"],
                           u_k_common=c["u_k_components"]["spectral_mismatch_relative"], u_b=c["u_b_cps"],
                           cov_kb=c["cov_kb_cps"], K=c["K_cps_per_Bq_cm2"], u_rel_K=c["u_rel_K"]))

# =====================================================================================================
# (A1) achieved / nominal false-alarm probability, one lane, grid of survey conditions
# =====================================================================================================
names = list(R.PATTERNS) + list(REAL)
rows = []
base = {}
for H in DOSES:
    U = float(bgamma(H))
    for T in DWELLS:
        for name in names:
            lane = lane_for(name, T)
            for cname, cal in (("declared", CAL), ("none", CAL0)):
                for a in ALPHAS:
                    auto = R.select_method(a, U, lane.T, cal)
                    for meth in ("normal", "poisson-exact"):
                        fa, fa0, _ = R.lane_false_alarm(lane, cal, U, a, meth, WINDOW)
                        if name == "all 1":
                            base[(H, T, cname, a, meth)] = (fa / a, fa0 / a)
                        rows.append(dict(H=H, U=U, T=T, Tw=lane.T, pattern=name, cal=cname, alpha=a, method=meth,
                                         selected=(meth == auto), over=R.variance_overstatement(lane),
                                         r_win=fa / a, r_or=fa0 / a))
for r in rows:
    b = base[(r["H"], r["T"], r["cal"], r["alpha"], r["method"])]
    r["b_win"], r["b_or"] = b
write_csv("rev3_A_false_alarm.csv",
          ["dose_rate_uSv_h", "U_cps", "dwell_s", "T_F_weighted_s", "weight_pattern", "calibration_terms", "alpha",
           "method", "method_selected_by_section3", "poisson_form_variance_overstatement",
           "achieved_over_nominal_Unull_window20TF", "achieved_over_nominal_Unull_exact",
           "same_for_all_weights_1_window", "same_for_all_weights_1_Unull_exact"],
          [(r["H"], f"{r['U']:.4g}", r["T"], f"{r['Tw']:.4g}", r["pattern"], r["cal"], f"{r['alpha']:.3g}", r["method"],
            r["selected"], f"{r['over']:.4f}", f"{r['r_win']:.5f}", f"{r['r_or']:.5f}", f"{r['b_win']:.5f}",
            f"{r['b_or']:.5f}") for r in rows])
TOL_EXACT = 1e-4      # numerical tolerance of the lattice evaluation, relative (see tests/test_rev3.py)
# quadrature tolerance of the U_null window average: compare 40 quantile nodes with full enumeration
chk = []
for (H, T, name, a) in ((0.1, 1.0, "7 full + one 0.1", ALPHA_SIDAK), (1.0, 10.0, "all 1", ALPHA_SIDAK),
                        (0.1, 10.0, "realistic: cell centred on a seam", 1e-3)):
    lane, U = lane_for(name, T), float(bgamma(H))
    vals, probs = R.u0_nodes(U, WINDOW * lane.T, max_enum=10 ** 6)
    tl = R.truth_tail(lane, CAL, U)
    full = sum(p * float(tl(R.rule_threshold(u0, lane.T, lane.T, CAL, a, "poisson-exact")[0])[0]) for u0, p in zip(vals, probs))
    q = R.lane_false_alarm(lane, CAL, U, a, "poisson-exact", WINDOW)[0]
    chk.append(abs(q / full - 1.0))
TOL_WIN = max(0.02, 2 * max(chk))
S["rev3_tol_window"] = f"{100 * TOL_WIN:.0f} %"
S["rev3_tol_window_obs"] = f"{100 * max(chk):.1f} %"


def worst(sel, key):
    sel = [r for r in rows if sel(r)]
    return max(sel, key=lambda r: r[key]) if sel else None


def desc(r):
    return f"{r['pattern']}, {r['H']:g} µSv/h, {r['T']:g} s, α = {afmt(r['alpha'])}, calibration terms {r['cal']}"


weighted = lambda r: r["pattern"] != "all 1"
ex_or = worst(lambda r: weighted(r) and r["method"] == "poisson-exact" and r["selected"], "r_or")
ex_win = worst(lambda r: weighted(r) and r["method"] == "poisson-exact" and r["selected"], "r_win")
no_or = worst(lambda r: weighted(r) and r["method"] == "normal" and r["selected"], "r_or")
no_all = worst(lambda r: weighted(r) and r["method"] == "normal", "r_or")
base_ex = worst(lambda r: r["pattern"] == "all 1" and r["method"] == "poisson-exact" and r["selected"], "r_win")
falsify = [r for r in rows if r["selected"] and r["r_or"] > 1 + TOL_EXACT and weighted(r)]
falsify_win = [r for r in rows if r["selected"] and r["r_win"] > 1 + TOL_WIN]
S["rev3_A_n_falsify_win"] = str(len(falsify_win))
S["rev3_A_n_falsify_win_w1"] = str(sum(1 for r in falsify_win if r["pattern"] == "all 1"))
S.update(rev3_A_ex_or=fmt(ex_or["r_or"]), rev3_A_ex_or_case=desc(ex_or), rev3_A_ex_win=fmt(ex_win["r_win"]),
         rev3_A_ex_win_case=desc(ex_win), rev3_A_no_or=fmt(no_or["r_or"]), rev3_A_no_or_case=desc(no_or),
         rev3_A_no_all=fmt(no_all["r_or"]), rev3_A_no_all_case=desc(no_all),
         rev3_A_base_ex_win=fmt(base_ex["r_win"]), rev3_A_base_ex_case=desc(base_ex),
         rev3_A_n_falsify=str(len(falsify)), rev3_A_n_rows=str(len(rows)))

tab = []
for r in sorted(falsify, key=lambda r: -r["r_or"])[:12]:
    tab.append((r["pattern"], r["H"], r["T"], afmt(r["alpha"]), r["cal"], r["method"], r["r_or"], r["b_or"], r["r_win"], r["b_win"]))
md_table("rev3_A_falsify", ["Weights", "µSv/h", "Dwell (s)", "α", "Calibration terms", "Method (as §3 selects)",
                            "Achieved/nominal, U_null exact", "Same, all weights 1", "Achieved/nominal, U_null 20·T_F window",
                            "Same, all weights 1"], tab)
# compact grid view: method selected by section 3, declared calibration terms, window
tab = []
for name in names:
    for T in DWELLS:
        line = [name, T]
        for a in ALPHAS:
            vals = [r["r_win"] for r in rows if r["pattern"] == name and r["T"] == T and r["alpha"] == a and r["cal"] == "declared" and r["selected"]]
            vor = [r["r_or"] for r in rows if r["pattern"] == name and r["T"] == T and r["alpha"] == a and r["cal"] == "declared" and r["selected"]]
            line.append(f"{fmt(min(vor))}–{fmt(max(vor))} / {fmt(max(vals))}")
        line.append(fmt(next(r["over"] for r in rows if r["pattern"] == name and r["T"] == T)))
        tab.append(line)
md_table("rev3_A_grid", ["Weights", "Dwell (s)"] + [f"α = {afmt(a)}: range over 0.1/1/3 µSv/h, U_null exact / max with 20·T_F window" for a in ALPHAS]
         + ["Poisson-form variance ÷ true variance"], tab)
print(f"s7: A1 grid done ({len(rows)} cases) {time.time() - t_start:.0f} s", flush=True)

# (A2) dense scan of mean counts: the lattice effect of poisson-exact with mostly full and one small weight
scan = []
pats = {"1 full + one 0.1": [1.0, 0.1], "3 full + one 0.1": [1.0] * 3 + [0.1], "7 full + one 0.1": [1.0] * 7 + [0.1],
        "7 full + one 0.5": [1.0] * 7 + [0.5], "1 full + partials 0.1-0.9": [1.0] + [0.1 * i for i in range(1, 10)]}
for a in (0.05, 0.0125, 1e-3, ALPHA_SIDAK):
    for pn, w in pats.items():
        w = np.array(w)
        for cname, cal in (("declared", CAL), ("none", CAL0)):
            best = (0.0, None)
            for U in np.geomspace(1.0, 100.0, 25):
                for T in (1.0, 2.13, 10.0):
                    lane = R.Lane(w, np.full(w.size, T / w.sum()))
                    _, fa0, _ = R.lane_false_alarm(lane, cal, U, a, "poisson-exact", None)
                    if fa0 / a > best[0]:
                        best = (fa0 / a, (U, T))
            scan.append((afmt(a), pn, cname, f"{best[0]:.4f}", f"{best[1][0]:.3g}", best[1][1]))
write_csv("rev3_A_scan.csv", ["alpha", "weights", "calibration_terms", "max_achieved_over_nominal_Unull_exact", "at_U_cps", "at_T_F_s"], scan)
sc_w = max(scan, key=lambda r: float(r[3]))
S.update(rev3_A_scan_max=fmt(float(sc_w[3])), rev3_A_scan_case=f"{sc_w[1]}, α = {sc_w[0]}, U = {sc_w[4]} s⁻¹, T_F = {sc_w[5]} s, calibration terms {sc_w[2]}")
md_table("rev3_A_scan", ["α", "Weights", "Calibration terms", "Max achieved/nominal (U_null exact), U 1–100 s⁻¹, T_F 1–10 s", "at U (s⁻¹)", "at T_F (s)"],
         [r for r in scan if r[2] == "declared"])
print(f"s7: A2 scan done {time.time() - t_start:.0f} s", flush=True)

# (A3) U_null window length (all weights 1): the inflation is from section 3, not from the weights
win = []
for H, T in ((0.1, 1.0), (1.0, 1.0), (0.1, 10.0)):
    U = float(bgamma(H))
    lane = R.pattern_lane("all 1", T)
    for a in (1e-3, ALPHA_SIDAK):
        line = [H, T, afmt(a)]
        for fct in (20.0, 50.0, 100.0, 200.0, 1000.0):
            line.append(R.lane_false_alarm(lane, CAL, U, a, "poisson-exact", fct)[0] / a)
        win.append(line)
write_csv("rev3_A_window.csv", ["dose_rate_uSv_h", "dwell_s", "alpha", "x20", "x50", "x100", "x200", "x1000"],
          [[f"{v:.5g}" if isinstance(v, float) else v for v in r] for r in win])
md_table("rev3_A_window", ["µSv/h", "Dwell (s)", "α", "window 20·T_F", "50·T_F", "100·T_F", "200·T_F", "1000·T_F"], win)
S["rev3_win20_01_1"] = fmt(win[1][3])
S["rev3_win200_01_1"] = fmt(win[1][6])
S["rev3_win100_01_1"] = fmt(win[1][5])

# (A4) alpha channel (very low counts, k << 1, non-lattice exact by outer sum of two lattices)
arows = []
for H in DOSES:
    U = float(bgamma(H))
    for T in DWELLS:
        for name in names:
            lane = lane_for(name, T)
            for a in ALPHAS:
                fa, fa0, m = R.lane_false_alarm(lane, ALPHA_CAL, U, a, "poisson-exact", WINDOW, max_enum=40, n_quant=30)
                arows.append((H, T, name, afmt(a), f"{(ALPHA_CAL.k * U + ALPHA_CAL.b) * lane.T:.4g}",
                              f"{(ALPHA_CAL.k * U + ALPHA_CAL.b) * lane.t.sum():.4g}", f"{fa0 / a:.4f}", f"{fa / a:.4f}"))
write_csv("rev3_A_alpha_channel.csv", ["dose_rate_uSv_h", "dwell_s", "weights", "alpha", "floor_null_mean_weighted",
                                       "floor_null_mean_raw_gates", "achieved_over_nominal_Unull_exact",
                                       "achieved_over_nominal_window"], arows)
aw = max(arows, key=lambda r: float(r[6]))
aw_real = max([r for r in arows if r[2].startswith("realistic")], key=lambda r: float(r[6]))
S.update(rev3_alpha_max=fmt(float(aw[6])), rev3_alpha_case=f"{aw[2]}, {aw[0]:g} µSv/h, {aw[1]:g} s, α = {aw[3]} (weighted floor mean {aw[4]} counts)",
         rev3_alpha_real=fmt(float(aw_real[6])), rev3_alpha_real_case=f"{aw_real[2]}, {aw_real[0]:g} µSv/h, {aw_real[1]:g} s, α = {aw_real[3]}")
md_table("rev3_A_alpha", ["µSv/h", "Dwell (s)", "Weights", "α", "Null floor counts (weighted)", "(raw gates)", "Achieved/nominal, U_null exact", "with window"],
         sorted(arows, key=lambda r: -float(r[6]))[:10])
print(f"s7: A3-A4 done {time.time() - t_start:.0f} s", flush=True)

# (A5) the price: detection limits of the Poisson form against the exact-variance and moment-matched forms
drows = []
for H in DOSES:
    U = float(bgamma(H))
    for T in DWELLS:
        for name in ["all 1", "1 full + partials 0.1-0.9", "7 full + one 0.1", "all 0.5",
                     "realistic: lane centred", "realistic: cell centred on a seam"]:
            lane = lane_for(name, T)
            Te = R.n_eff(lane)
            tl = R.truth_tail(lane, CAL, U)
            for a in (0.05, ALPHA_SIDAK):
                m = R.select_method(a, U, lane.T, CAL)
                r_q = R.rule_dhash(U, lane.T, lane.T, CAL, a, BETA, m, with_K=False)        # quoted (u_rel_K excluded)
                r_star = R.rule_threshold(U, lane.T, lane.T, CAL, a, m)[0]
                r_true = R.true_rate_for_power(lane, CAL, U, r_star, BETA)
                out = {}
                for tag, meth in (("ev", "normal"), ("sp", "poisson-exact")):
                    rs = R.rule_threshold(U, Te, Te, CAL, a, meth)[0]
                    out[tag] = (R.rule_dhash(U, Te, Te, CAL, a, BETA, meth, with_K=False), float(tl(rs)[0]) / a,
                                R.true_rate_for_power(lane, CAL, U, rs, BETA))
                tC, rC = R.exact_dhash_rate(lane, CAL, U, a, BETA)
                drows.append(dict(H=H, T=T, name=name, a=a, m=m, Tw=lane.T, Te=Te, r_q=r_q, r_true=r_true,
                                  ev=out["ev"], sp=out["sp"], rC=rC))
write_csv("rev3_A_dhash.csv", ["dose_rate_uSv_h", "dwell_s", "weights", "alpha", "method", "T_F_s", "T_eff_s",
                               "r_hash_quoted_poisson_form", "r_hash_true_for_rule_threshold",
                               "r_hash_exact_variance_normal_quoted", "fa_ratio_exact_variance_normal", "r_hash_exact_variance_normal_true",
                               "r_hash_scaled_poisson_quoted", "fa_ratio_scaled_poisson", "r_hash_scaled_poisson_true",
                               "r_hash_exact_distribution"],
          [(d["H"], d["T"], d["name"], f"{d['a']:.3g}", d["m"], f"{d['Tw']:.4g}", f"{d['Te']:.4g}", f"{d['r_q']:.5g}", f"{d['r_true']:.5g}",
            f"{d['ev'][0]:.5g}", f"{d['ev'][1]:.4f}", f"{d['ev'][2]:.5g}", f"{d['sp'][0]:.5g}", f"{d['sp'][1]:.4f}", f"{d['sp'][2]:.5g}",
            f"{d['rC']:.5g}") for d in drows])
md_table("rev3_A_dhash", ["µSv/h", "Dwell (s)", "Weights", "α", "Quoted r# (Poisson form) ÷ exact-distribution r#",
                          "True r# of the Poisson-form threshold ÷ quoted", "Exact-variance normal: r# ÷ exact, achieved/nominal α",
                          "Scaled Poisson (N_eff): r# ÷ exact, achieved/nominal α"],
         [(d["H"], d["T"], d["name"], afmt(d["a"]), d["r_q"] / d["rC"], d["r_true"] / d["r_q"],
           f"{fmt(d['ev'][0] / d['rC'])}, {fmt(d['ev'][1])}", f"{fmt(d['sp'][0] / d['rC'])}, {fmt(d['sp'][1])}")
          for d in drows if d["H"] in (0.1, 1.0)])
real = [d for d in drows if d["name"].startswith("realistic")]
S.update(rev3_A_loss_real_min=fmt(min(d["r_q"] / d["rC"] for d in real)), rev3_A_loss_real_max=fmt(max(d["r_q"] / d["rC"] for d in real)),
         rev3_A_loss_max=fmt(max(d["r_q"] / d["rC"] for d in drows)),
         rev3_A_loss_ev_max=fmt(max(d["r_q"] / d["ev"][0] for d in drows)),
         rev3_A_loss_sp_max=fmt(max(d["r_q"] / d["sp"][0] for d in drows)),
         rev3_A_ev_fa_max=fmt(max(d["ev"][1] for d in drows)), rev3_A_sp_fa_max=fmt(max(d["sp"][1] for d in drows)),
         rev3_A_true_over_quoted_max=fmt(max(d["r_true"] / d["r_q"] for d in drows)))
print(f"s7: A5 detection limits done {time.time() - t_start:.0f} s", flush=True)

# =====================================================================================================
# (B) several lanes: any lane at alpha/m
# =====================================================================================================
def geometry(kind, v):
    """Lanes of one cell (lists of Lane, Cal).  m2: one pass, cell centred on a seam (lanes 1, 2).
    m4: two passes, each with a seam centred on the cell (lanes 0-3, four lane indices)."""
    if kind == "m2":
        return [R.cell_lane_weights(+SEAM, v=v), R.cell_lane_weights(-SEAM, v=v)], [LANE_CALS[1], LANE_CALS[2]]
    ls = [R.cell_lane_weights(s, v=v) for s in (+SEAM, -SEAM, +SEAM, -SEAM)]
    return ls, [LANE_CALS[i] for i in (1, 2, 3, 0)]


brows, btab = [], []
for kind in ("m2", "m4"):
    for H in (0.15, 1.0, 3.0):
        U = float(bgamma(H))
        for v in (0.10, 0.03):
            lanes, cals = geometry(kind, v)
            for a in (0.05, ALPHA_SIDAK):
                m = len(lanes)
                pc, per, ub = R.cell_any_lane_false_alarm(lanes, cals, U, a)
                pc_nc, _, _ = R.cell_any_lane_false_alarm(lanes, cals, U, a, common=False)
                lim = R.any_lane_limits(lanes, cals, U, a, BETA)
                Dq = min(x[2] for x in lim)
                Dmax = max(x[2] for x in lim)
                p_wide = R.cell_any_lane_false_alarm(lanes, cals, U, a, D=Dq)[0]
                p_cell = R.cell_any_lane_false_alarm(lanes, cals, U, a, D=Dq, f=[l.w for l in lanes])[0]
                i_best = int(np.argmin([x[2] for x in lim]))
                p_one = R.cell_any_lane_false_alarm(lanes, cals, U, a, D=lim[i_best][2], active=[j == i_best for j in range(m)])[0]
                # seam patch (100 cm2 square centred on the seam = the cell): lanes see fractions w; claim uses max D#_i
                if kind == "m2":
                    p_seam = R.cell_any_lane_false_alarm(lanes, cals, U, a, D=Dmax, f=[l.w for l in lanes])[0]
                    D_seam = L.solve_for_power(lambda D: R.cell_any_lane_false_alarm(lanes, cals, U, a, D=D, f=[l.w for l in lanes])[0], 1 - BETA)
                else:
                    p_seam, D_seam = float("nan"), float("nan")
                D_cell = L.solve_for_power(lambda D: R.cell_any_lane_false_alarm(lanes, cals, U, a, D=D, f=[l.w for l in lanes])[0], 1 - BETA)
                brows.append(dict(kind=kind, H=H, U=U, v=v, a=a, m=m, T=[l.T for l in lanes], pc=pc, pc_nc=pc_nc, per=per, ub=ub,
                                  Dq=Dq, Dmax=Dmax, p_wide=p_wide, p_cell=p_cell, p_one=p_one, p_seam=p_seam, D_seam=D_seam,
                                  D_cell=D_cell, meth=sorted({x[1] for x in lim})))
write_csv("rev3_B_cell.csv", ["geometry", "dose_rate_uSv_h", "U_cps", "speed_m_s", "alpha_cell", "m", "T_F_per_lane_s",
                              "methods", "P_cell_false_alarm", "P_cell_without_common_term", "per_lane_P", "union_bound",
                              "quoted_D_hash_min_lane", "max_lane_D_hash", "P_detect_wide_uniform_at_quoted",
                              "P_detect_cell_confined_at_quoted", "P_detect_one_lane_at_its_D_hash",
                              "P_detect_seam_patch_at_max_lane_D_hash", "D_hash_seam_patch_true", "D_hash_cell_confined_true"],
          [(b["kind"], b["H"], f"{b['U']:.4g}", b["v"], f"{b['a']:.3g}", b["m"], "|".join(f"{t:.3g}" for t in b["T"]), "|".join(b["meth"]),
            f"{b['pc']:.4g}", f"{b['pc_nc']:.4g}", "|".join(f"{p:.4g}" for p in b["per"]), f"{b['ub']:.4g}", f"{b['Dq']:.4g}",
            f"{b['Dmax']:.4g}", f"{b['p_wide']:.4f}", f"{b['p_cell']:.4f}", f"{b['p_one']:.4f}", f"{b['p_seam']:.4f}",
            f"{b['D_seam']:.4g}", f"{b['D_cell']:.4g}") for b in brows])
md_table("rev3_B_cell", ["Lanes", "µSv/h", "Speed (m/s)", "α (cell)", "Achieved/nominal cell false alarm (with u_common)",
                         "Union bound / α", "Quoted D# = min D#ᵢ (Bq/cm², u_rel(K)=0)", "P(detect) at quoted D#: activity wide / confined to cell",
                         "P(detect), activity over one lane at its D#ᵢ", "Seam patch (= cell): P at max D#ᵢ; true limit ÷ max D#ᵢ"],
         [(b["m"], b["H"], b["v"], afmt(b["a"]), b["pc"] / b["a"], b["ub"] / b["a"], b["Dq"], f"{b['p_wide']:.3f} / {b['p_cell']:.3f}",
           f"{b['p_one']:.3f}", "—" if b["kind"] == "m4" else f"{b['p_seam']:.3f}; {fmt(b['D_seam'] / b['Dmax'])}") for b in brows])
S.update(rev3_B_fa_max=fmt(max(b["pc"] / b["a"] for b in brows)), rev3_B_ub_max=fmt(max(b["ub"] / b["a"] for b in brows)),
         rev3_B_pcell_min=f"{min(b['p_cell'] for b in brows):.2f}", rev3_B_pcell_max=f"{max(b['p_cell'] for b in brows):.2f}",
         rev3_B_pwide_min=f"{min(b['p_wide'] for b in brows):.3f}",
         rev3_B_pone_min=f"{min(b['p_one'] for b in brows):.3f}",
         rev3_B_pseam_min=f"{min(b['p_seam'] for b in brows if b['kind'] == 'm2'):.2f}",
         rev3_B_pseam_max=f"{max(b['p_seam'] for b in brows if b['kind'] == 'm2'):.2f}",
         rev3_B_seam_ratio=fmt(max(b["D_seam"] / b["Dmax"] for b in brows if b["kind"] == "m2")),
         rev3_B_cell_ratio_max=fmt(max(b["D_cell"] / b["Dq"] for b in brows)))
print(f"s7: B cell rule done {time.time() - t_start:.0f} s", flush=True)

# (B2) pooled four-lane U_null fallback (same gates): per-lane false-alarm probability, exact, weights 1
prow = []
for H in DOSES:
    U = float(bgamma(H))
    for T in DWELLS:
        for m, a in ((1, 0.05), (4, 0.05), (1, ALPHA_SIDAK), (4, ALPHA_SIDAK)):
            al = a / m
            meth = R.select_method(al, U, T, CAL)
            pp = R.pooled_u0_lane_false_alarm(T, CAL, U, al, meth)
            pw = R.lane_false_alarm(R.pattern_lane("all 1", T), CAL, U, al, meth, WINDOW)[0]
            prow.append((H, T, m, afmt(a), meth, pp / al, pw / al))
write_csv("rev3_B_pooled.csv", ["dose_rate_uSv_h", "dwell_s", "m", "alpha_cell", "method", "lane_achieved_over_nominal_pooled_same_gates",
                                "lane_achieved_over_nominal_window20TF"], [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in prow])
md_table("rev3_B_pooled", ["µSv/h", "Dwell (s)", "m", "α (cell)", "Method", "Per-lane achieved/nominal, pooled U_null (same gates)",
                           "Per-lane achieved/nominal, 20·T_F window"], prow)
S["rev3_B_pooled_max"] = fmt(max(r[5] for r in prow))
S["rev3_B_pooled_case"] = (lambda r: f"{r[0]:g} µSv/h, {r[1]:g} s, m = {r[2]}, α = {r[3]}")(max(prow, key=lambda r: r[5]))
# Monte Carlo: cell-level probability with the pooled fallback shared by four lanes (positive correlation)
NMC = 400_000
T, H = 1.0, 0.1
U = float(bgamma(H))
cal = CAL
nf = rng.poisson((cal.k * U + cal.b) * T, (NMC, 4))
nu = rng.poisson(U * T, (NMC, 4))
e_c = rng.normal(0.0, cal.u_k_common, (NMC, 1)) * U
e_l = rng.normal(0.0, np.sqrt(cal.var_lane(U)), (NMC, 4))
r = (nf - nu) / T - cal.b + e_c + e_l
U0 = nu.sum(axis=1) / (4 * T)
meth = R.select_method(0.05 / 4, U, T, cal)
thr = {M: R.rule_threshold(M / (4 * T), T, T, cal, 0.05 / 4, meth)[0] for M in np.unique(nu.sum(axis=1))}
rs = np.array([thr[M] for M in nu.sum(axis=1)])
p_any = float(np.mean(np.any(r > rs[:, None], axis=1)))
p_lane = float(np.mean(r > rs[:, None]))
se = np.sqrt(p_any * (1 - p_any) / NMC)
S.update(rev3_B_mc_pooled_any=fmt(p_any / 0.05), rev3_B_mc_pooled_lane=fmt(p_lane / 0.0125), rev3_B_mc_se=fmt(se / 0.05),
         rev3_B_mc_n=f"{NMC:,}".replace(",", " "))
print(f"s7: B pooled done {time.time() - t_start:.0f} s", flush=True)

# (B3) sensitivity cost against the inverse-variance combined test (large counts, normal form valid)
crow = []
for kind in ("m2", "m4"):
    for H, v in ((3.0, 0.01), (1.0, 0.01), (1.0, 0.10)):
        U = float(bgamma(H))
        lanes, cals = geometry(kind, v)
        for a in (0.05, ALPHA_SIDAK):
            lim = R.any_lane_limits(lanes, cals, U, a, BETA)
            d_any = min(x[2] for x in lim)
            _, d_rev2, _, _ = R.rev2_combined(lanes, cals, U, a, BETA)
            C = R.Combined(lanes, cals, U)
            _, d_C = C.dhash(a, BETA, "gp")
            d_one = R.rule_dhash(U, lanes[0].T, lanes[0].T, R.Cal(**{**cals[0].__dict__, "u_rel_K": 0.0}), a, BETA, with_K=True)
            crow.append((len(lanes), H, v, afmt(a), np.mean([l.T for l in lanes]), d_one, d_any, d_rev2, d_C, d_any / d_rev2, d_any / d_C))
write_csv("rev3_B_combined.csv", ["m", "dose_rate_uSv_h", "speed_m_s", "alpha", "T_F_per_lane_s", "D_hash_one_lane_at_alpha",
                                  "D_hash_any_lane_alpha_over_m", "D_hash_normal_combined", "D_hash_exact_combined_C",
                                  "cost_any_over_normal_combined", "cost_any_over_C"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in crow])
md_table("rev3_B_combined", ["m", "µSv/h", "Speed (m/s)", "α", "T_F per lane (s)", "One lane at α", "Any lane at α/m (rev 3)",
                             "Normal inverse-variance combination (Poisson-form variances)", "Exact combined statistic (C)",
                             "Cost: rev 3 ÷ normal combination", "Cost: rev 3 ÷ C"], crow)
S.update(rev3_B_cost_m2=fmt(max(r[10] for r in crow if r[0] == 2)), rev3_B_cost_m4=fmt(max(r[10] for r in crow if r[0] == 4)),
         rev3_B_cost_min=fmt(min(r[10] for r in crow)),
         rev3_B_costn_m2=f"{fmt(min(r[9] for r in crow if r[0] == 2))}–{fmt(max(r[9] for r in crow if r[0] == 2))}",
         rev3_B_costn_m4=f"{fmt(min(r[9] for r in crow if r[0] == 4))}–{fmt(max(r[9] for r in crow if r[0] == 4))}")
print(f"s7: B combined done {time.time() - t_start:.0f} s", flush=True)

# =====================================================================================================
# (C1) validation of the evaluators for S = sum a_j N_j + Gaussian
# =====================================================================================================
def lane_part(lane, cal, U, ci):
    a = np.concatenate((ci * lane.w / lane.T, -ci * cal.k * lane.w / lane.T))
    lam = np.concatenate(((cal.k * U + cal.b) * lane.t, U * lane.t))
    return L.LinStat(a, lam, -ci * cal.b, 0.0, span=ci * 0.05 / lane.T)


vrows = []
cases = []
for H in (0.03, 0.1, 1.0, 3.0):          # 0.03 uSv/h: about 1-2 expected floor counts per second
    U = float(bgamma(H))
    for T in DWELLS:
        cases.append(("1 lane beta, " + "realistic seam", H, U, T, "lane"))
        if T == 1.0:                     # exact outer-sum reference kept to manageable supports
            cases.append(("2 lanes beta (combined)", H, U, T, "two"))
        cases.append(("1 lane alpha channel", H, U, T, "alpha"))
for label, H, U, T, kind in cases:
    v = 0.10 / T
    if kind == "lane":
        lane = R.cell_lane_weights(SEAM, v=v)
        tl = R.truth_tail(lane, CAL, U)
        st = R.truth_stat(lane, CAL, U)
        mu_f = (CAL.k * U + CAL.b) * lane.T
    elif kind == "alpha":
        lane = R.cell_lane_weights(SEAM, v=v)
        tl = R.truth_tail(lane, ALPHA_CAL, U)
        st = L.LinStat(np.concatenate((lane.w / lane.T, -ALPHA_CAL.k * lane.w / lane.T)),
                       np.concatenate(((ALPHA_CAL.k * U + ALPHA_CAL.b) * lane.t, U * lane.t)), -ALPHA_CAL.b, ALPHA_CAL.sig(U))
        mu_f = (ALPHA_CAL.k * U + ALPHA_CAL.b) * lane.T
    else:
        lanes, cals = geometry("m2", v)
        Cm = R.Combined(lanes, cals, U)
        st = Cm.stat()
        tl = L.two_lattice_tail(lane_part(lanes[0], cals[0], U, Cm.c[0] / cals[0].K),
                                lane_part(lanes[1], cals[1], U, Cm.c[1] / cals[1].K), st.sig)
        mu_f = sum((c.k * U + c.b) * l.T for l, c in zip(lanes, cals))
    for a in ALPHAS:
        t_gp = L.threshold(st, a, "gp")
        t_sp = L.threshold(st, a, "spa")
        e_gp, e_sp = float(tl(t_gp)[0]), float(tl(t_sp)[0])
        p_gp = a / e_gp - 1.0                                # GP tail (= alpha at its root) vs exact, same point
        p_sp = float(L.tail_spa(st, t_gp)[0]) / e_gp - 1.0
        vrows.append((label, H, T, f"{mu_f:.3g}", afmt(a), f"{st.sig / np.sqrt(st.var):.3g}", p_gp, p_sp,
                      e_gp / a, e_sp / a))
# lattice-only (no Gaussian term) saddlepoint, single lane with mixed weights: where it breaks
for H in (0.03, 0.1, 1.0):
    U = float(bgamma(H))
    for pn in ("7 full + one 0.1", "realistic: cell centred on a seam", "all 1"):
        lane = lane_for(pn, 1.0)
        st = R.truth_stat(lane, CAL0, U, span_w=0.05)
        tl = R.truth_tail(lane, CAL0, U)
        for a in ALPHAS:
            t_ex = R._atom_threshold(tl, a)
            p_true = float(tl(t_ex)[0])
            p_sp = float(L.tail_spa(st, t_ex, st.span)[0])
            t_sp = L.threshold(st, a, "spa")
            vrows.append((f"1 lane beta, {pn}, no calibration term (lattice SPA)", H, 1.0, f"{(U + 0.5) * lane.T:.3g}", afmt(a), "0",
                          float("nan"), p_sp / p_true - 1.0, float("nan"), float(tl(t_sp)[0]) / a))
write_csv("rev3_C_validation.csv", ["statistic", "dose_rate_uSv_h", "dwell_s", "null_floor_counts", "alpha", "sig_cal_over_sd",
                                    "GP_tail_rel_error_at_GP_threshold", "SPA_tail_rel_error_at_GP_threshold",
                                    "exact_achieved_over_nominal_GP_threshold", "exact_achieved_over_nominal_SPA_threshold"],
          [[f"{x:.4g}" if isinstance(x, float) else x for x in r] for r in vrows])
gp_err = max(abs(r[6]) for r in vrows if np.isfinite(r[6]))
gp_ach = max(r[8] for r in vrows if np.isfinite(r[8]))
sp_cont = [r for r in vrows if r[5] != "0"]
sp_lat = [r for r in vrows if r[5] == "0"]
S.update(rev3_C_gp_err=f"{gp_err:.1e}", rev3_C_gp_ach=f"{gp_ach:.6f}",
         rev3_C_sp_err_cont=fmt(max(abs(r[7]) for r in sp_cont)), rev3_C_sp_ach_cont=fmt(max(r[9] for r in sp_cont)),
         rev3_C_sp_case_cont=(lambda r: f"{r[0]}, {r[1]:g} µSv/h, {r[2]:g} s, α = {r[4]}")(max(sp_cont, key=lambda r: abs(r[7]))),
         rev3_C_sp_err_lat=fmt(max(abs(r[7]) for r in sp_lat)), rev3_C_sp_ach_lat=fmt(max(r[9] for r in sp_lat)),
         rev3_C_sp_case_lat=(lambda r: f"{r[0]}, {r[1]:g} µSv/h, α = {r[4]}")(max(sp_lat, key=lambda r: r[9])))
md_table("rev3_C_validation", ["Statistic", "µSv/h", "Dwell (s)", "Null floor counts", "α", "σ_cal ÷ sd",
                               "GP tail error (at GP t*)", "SPA tail error (at GP t*)", "Achieved/nominal, GP threshold",
                               "Achieved/nominal, SPA threshold"], vrows)
# Monte Carlo for four lanes combined (no exact reference): GP and SPA against simulation at alpha = 0.05, 1e-3
mrows = []
NM = 1_000_000
for H, v in ((0.15, 0.03), (1.0, 0.10)):
    U = float(bgamma(H))
    lanes, cals = geometry("m4", v)
    Cm = R.Combined(lanes, cals, U)
    st = Cm.stat()
    sim = np.full(NM, st.mu)
    for aj, lj in zip(*L.aggregate(st.a, st.lam)):
        sim += aj * rng.poisson(lj, NM)
    sim += rng.normal(0.0, st.sig, NM)
    for a in (0.05, 1e-3):
        t = L.threshold(st, a, "gp")
        p = float(np.mean(sim > t))
        mrows.append((H, v, afmt(a), p / a, np.sqrt(p * (1 - p) / NM) / a, float(L.tail_spa(st, t)[0]) / a))
write_csv("rev3_C_mc4.csv", ["dose_rate_uSv_h", "speed_m_s", "alpha", "mc_achieved_over_nominal_at_GP_threshold", "mc_se", "SPA_tail_over_nominal"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in mrows])
md_table("rev3_C_mc4", ["µSv/h", "Speed (m/s)", "α", "MC achieved/nominal at GP threshold (four lanes)", "MC standard error", "SPA tail/nominal"], mrows)
S["rev3_C_mc4_dev"] = fmt(max(abs(r[3] - 1) / r[4] for r in mrows))
S["rev3_C_mc_n"] = f"{NM:,}".replace(",", " ")
# C with the U_null window: the threshold of C is exact at U0; window noise as for any rule
wrow = []
for H, T in ((0.1, 1.0), (1.0, 1.0), (0.1, 10.0)):
    U = float(bgamma(H))
    lanes, cals = geometry("m2", 0.10 / T)
    for a in (0.05, ALPHA_SIDAK):
        for fct in (20.0, 200.0):
            vals, probs = R.u0_nodes(U, fct * np.mean([l.T for l in lanes]), max_enum=40, n_quant=24)
            truth = R.Combined(lanes, cals, U)
            acc = 0.0
            for u0, pr in zip(vals, probs):
                Cu = R.Combined(lanes, cals, float(u0), c=truth.c)
                acc += pr * float(L.tail_gp(truth.stat(), Cu.threshold(a, "gp"))[0])
            wrow.append((H, T, afmt(a), fct, acc / a))
md_table("rev3_C_window", ["µSv/h", "Dwell (s)", "α", "U_null window (× T_F)", "Achieved/nominal, combined statistic C (m = 2)"], wrow)
write_csv("rev3_C_window.csv", ["dose_rate_uSv_h", "dwell_s", "alpha", "window_factor", "achieved_over_nominal"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in wrow])
S["rev3_C_win20_max"] = fmt(max(r[4] for r in wrow if r[3] == 20.0))
S["rev3_C_win200_max"] = fmt(max(r[4] for r in wrow if r[3] == 200.0))
print(f"s7: C validation done {time.time() - t_start:.0f} s", flush=True)

# (C2) rules compared on the s01-like plan: two passes offset by half a pitch, 0.03 m/s, U = 5 1/s, alpha 0.05
def s01_cell(yc, v=0.03, U=5.0):
    """Lanes contributing to a cell whose centre is at lateral position yc (m) for two passes, the second
    shifted by half a pitch (plan offset 0.04375 m); the same lane index from both passes accumulates."""
    centres = (1.5 - np.arange(4)) * 0.0875
    lanes, cals = [], []
    for i in range(4):
        parts = [R.cell_lane_weights(c - yc, v=v) for c in (centres[i], centres[i] + 0.04375)]
        parts = [p for p in parts if p.w.size]
        if parts:
            lanes.append(R.Lane(np.concatenate([p.w for p in parts]), np.concatenate([p.t for p in parts])))
            cals.append(LANE_CALS[i])
    return lanes, cals


s01 = []
for yc in np.arange(-0.04375, 0.04375, 0.0875 / 4):
    lanes, cals = s01_cell(yc)
    U = 5.0
    lim = R.any_lane_limits(lanes, cals, U, 0.05, BETA, with_K=True)
    d3 = min(x[2] for x in lim)
    _, d2, _, _ = R.rev2_combined(lanes, cals, U, 0.05, BETA, with_K=True)
    uK = float(np.mean([c.u_rel_K for c in cals]))
    sp = {s: R.split_rule_dhash(lanes, cals, U, 0.05, BETA, s, u_rel_K=uK) for s in (0.0, 0.2, 0.5)}
    s01.append(dict(yc=yc, m=len(lanes), d2=d2, d3=d3, dmax3=max(x[2] for x in lim), sp=sp, T=[l.T for l in lanes]))
write_csv("rev3_C_s01.csv", ["cell_centre_lateral_m", "m", "T_F_per_lane_s", "D_hash_rev2_normal_combined", "D_hash_rev3_any_lane_min",
                             "D_hash_rev3_any_lane_max", "D_hash_C_uniform", "D_hash_C_worst_single_lane", "D_hash_C80_lane20_uniform",
                             "D_hash_C80_lane20_worst_single_lane", "D_hash_C50_lane50_uniform", "D_hash_C50_lane50_worst_single_lane"],
          [(f"{d['yc']:.5f}", d["m"], "|".join(f"{t:.3g}" for t in d["T"]), f"{d['d2']:.4g}", f"{d['d3']:.4g}", f"{d['dmax3']:.4g}",
            *[f"{x:.4g}" for s in (0.0, 0.2, 0.5) for x in (d["sp"][s]["uniform"], max(d["sp"][s][f"lane{i}"] for i in range(d["m"])))])
           for d in s01])


def med(xs):
    return float(np.median(xs))


md_rows = [("rev 2: normal inverse-variance combination", med([d["d2"] for d in s01]), "—"),
           ("rev 3: any lane at α/m (quoted min D#ᵢ)", med([d["d3"] for d in s01]), med([d["dmax3"] for d in s01])),
           ("C: exact combined statistic only", med([d["sp"][0.0]["uniform"] for d in s01]), med([max(d["sp"][0.0][f"lane{i}"] for i in range(d["m"])) for d in s01])),
           ("C at 0.8α + exact per-lane at 0.2α/m", med([d["sp"][0.2]["uniform"] for d in s01]), med([max(d["sp"][0.2][f"lane{i}"] for i in range(d["m"])) for d in s01])),
           ("C at 0.5α + exact per-lane at 0.5α/m", med([d["sp"][0.5]["uniform"] for d in s01]), med([max(d["sp"][0.5][f"lane{i}"] for i in range(d["m"])) for d in s01]))]
md_table("rev3_C_s01", ["Rule (α = 0.05, β = 0.05, u_rel(K) = 0.15)", "Median D#, activity uniform over the footprints (Bq/cm²)",
                        "Median D#, activity over one lane's footprint only (worst lane)"], md_rows)
S.update(rev3_s01_rev2=fmt(md_rows[0][1]), rev3_s01_rev3=fmt(md_rows[1][1]), rev3_s01_rev3_one=fmt(md_rows[1][2]),
         rev3_s01_C=fmt(md_rows[2][1]), rev3_s01_C_one=fmt(md_rows[2][2]), rev3_s01_C80=fmt(md_rows[3][1]), rev3_s01_C80_one=fmt(md_rows[3][2]),
         rev3_s01_C50=fmt(md_rows[4][1]), rev3_s01_C50_one=fmt(md_rows[4][2]),
         rev3_s01_m=f"{min(d['m'] for d in s01)}–{max(d['m'] for d in s01)}")
# achieved alpha of the rev-2 normal combination at low counts and small alpha (exact, m = 2)
r2 = []
for H, T in ((0.1, 1.0), (1.0, 1.0), (3.0, 10.0)):
    U = float(bgamma(H))
    lanes, cals = geometry("m2", 0.10 / T)
    for a in (0.05, ALPHA_SIDAK):
        ys, _, c, sd0 = R.rev2_combined(lanes, cals, U, a, BETA)
        Cm = R.Combined(lanes, cals, U, c=c)
        st = Cm.stat()
        if T == 1.0:      # exact outer sum of the two lane lattices
            tl = L.two_lattice_tail(lane_part(lanes[0], cals[0], U, c[0] / cals[0].K), lane_part(lanes[1], cals[1], U, c[1] / cals[1].K), st.sig)
            p_fa = float(tl(ys)[0])
        else:             # the outer sum would need several GB: Gil-Pelaez (validated to < 1e-7 in section 3.1)
            p_fa = float(L.tail_gp(st, ys)[0])
        r2.append((H, T, afmt(a), p_fa / a))
md_table("rev3_C_rev2_alpha", ["µSv/h", "Dwell (s)", "α", "Rev-2 normal combination: achieved/nominal (exact, m = 2, seam cell)"], r2)
S["rev3_rev2_fa_max"] = fmt(max(r[3] for r in r2))
S["rev3_rev2_fa_min"] = fmt(min(r[3] for r in r2))
print(f"s7: C rules compared {time.time() - t_start:.0f} s", flush=True)

# =====================================================================================================
# (D) low-count alpha channel: N+1 variance rule and the 0.10 minimum weight
# =====================================================================================================
lrows = []
for H in (0.1, 1.0, 3.0):
    U = float(bgamma(H))
    for T in DWELLS:
        for name in ("all 1", "7 full + one 0.1", "realistic: cell centred on a seam", "all 0.10"):
            lane = lane_for(name, T)
            Tw = lane.T
            X = L.LinStat(lane.w, (ALPHA_CAL.k * U + ALPHA_CAL.b) * lane.t, 0.0, 0.0, 0.05)
            lo, sp, pmf = L.lattice_pmf(X)
            s_vals = (lo + np.arange(pmf.size)) * sp
            nu = U * Tw
            v_true = (ALPHA_CAL.k * U + ALPHA_CAL.b) * np.sum(lane.w ** 2 * lane.t) / Tw ** 2 + ALPHA_CAL.k ** 2 * U * np.sum(lane.w ** 2 * lane.t) / Tw ** 2
            nf_rep = np.where(s_vals > 0, s_vals, s_vals + 1.0)
            v_rep = nf_rep / Tw ** 2 + ALPHA_CAL.k ** 2 * nu / Tw ** 2
            r = s_vals / Tw - ALPHA_CAL.k * U - ALPHA_CAL.b
            Er = float(np.dot(pmf, r))
            cover = float(np.dot(pmf, np.abs(r - Er) <= 2.0 * np.sqrt(v_rep)))
            p0 = float(pmf[np.argmin(np.abs(s_vals))]) if s_vals[0] <= 1e-12 else 0.0
            small = float(np.dot(pmf, (s_vals > 1e-12) & (s_vals < 1.0 - 1e-12)))
            lrows.append((H, T, name, (ALPHA_CAL.k * U + ALPHA_CAL.b) * Tw, p0, small, float(np.dot(pmf, v_rep)) / v_true,
                          float(np.sqrt(np.dot(pmf, v_rep)) / np.sqrt(v_true)), cover))
write_csv("rev3_lowcount.csv", ["dose_rate_uSv_h", "dwell_s", "weights", "alpha_null_floor_counts_weighted", "P_S_F_zero",
                                "P_0_lt_S_F_lt_1", "E_reported_var_over_true_var", "rms_reported_u_over_true_u", "coverage_r_pm_2u_stat"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in lrows])
md_table("rev3_lowcount", ["µSv/h", "Dwell (s)", "Weights", "Null floor counts (weighted)", "P(S_F = 0)", "P(0 < S_F < 1)",
                           "E[reported u_stat²] ÷ true variance", "rms reported u_stat ÷ true u", "Coverage of r ± 2u_stat"], lrows)
S.update(rev3_lc_over_max=fmt(max(r[6] for r in lrows)), rev3_lc_over_min=fmt(min(r[6] for r in lrows)),
         rev3_lc_cov_min=f"{min(r[8] for r in lrows):.3f}", rev3_lc_small_max=f"{max(r[5] for r in lrows):.2f}",
         rev3_lc_over_10=fmt(next(r[6] for r in lrows if r[0] == 1.0 and r[1] == 10.0 and r[2] == "all 1")),
         rev3_lc_over_1=fmt(next(r[6] for r in lrows if r[0] == 1.0 and r[1] == 1.0 and r[2] == "all 1")))

# =====================================================================================================
# report fragment
# =====================================================================================================
S["rev3_runtime"] = f"{time.time() - t_start:.0f} s"
S["rev3_alpha_sidak"] = f"{ALPHA_SIDAK:.3g}"
update_summary(**S)
tpl = (ROOT / "report" / "model_rev3_checks.template.md").read_text(encoding="utf-8")
import re  # noqa: E402

summary = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
missing = []


def sub(mm):
    kind, key = mm.group(1), mm.group(2)
    if kind == "V":
        if key not in summary:
            missing.append(key)
            return "??"
        return summary[key]
    p = TABLES / f"{key}.md"
    if not p.exists():
        missing.append(key)
        return "??"
    return p.read_text(encoding="utf-8").rstrip("\n")


text = re.sub(r"\{\{([VT]):([A-Za-z0-9_]+)\}\}", sub, tpl)
if missing:
    raise SystemExit("model_rev3_checks template refers to missing results: " + ", ".join(missing))
(ROOT / "report" / "model_rev3_checks.md").write_text(
    "<!-- GENERATED by scripts/s7_rev3_checks.py from model_rev3_checks.template.md and results/. Edit the template. -->\n" + text,
    encoding="utf-8")
print(f"s7: rev-3 checks written ({time.time() - t_start:.0f} s)")
