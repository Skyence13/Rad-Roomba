#!/usr/bin/env python3
"""Step 8 - the null reference U_null (MODEL.md revision 4, section 3): window precision in counts, the
predictive threshold, pooled-window lane ratios, field gradients, stationary recounts.

Evidence class: calculated (exact lattice convolution over the Poisson window count) with SYNTHETIC
coefficients; nothing is measured.  Writes results/rev4_*.csv, results/tables/rev4_*.md and
report/model_rev4_unull.md (from its template)."""
import json
import re
import time

import numpy as np

from common import ALPHA_SIDAK, ROOT, TABLES, bgamma, fmt, md_table, update_summary, write_csv
from rrrad import rev3 as R
from rrrad import unull as N

t0 = time.time()
S = {}
DOSES = [0.1, 1.0, 3.0]
ALPHAS = [0.05, 0.01, 1e-3, ALPHA_SIDAK]
GRID = (25, 50, 100, 200, 400, 800, 1600, 3200, 6400)
V = 0.10                                   # survey speed, m/s
profile = json.loads((ROOT / "demo_site_profile_ore.json").read_text(encoding="utf-8"))
ALPHA_RECOUNT = 1.71e-4                    # demo two-stage profile value used by the ros2_ws scenarios (alpha_recount 0.000171)


def afmt(a):
    return {0.05: "0.05", 0.01: "0.01", 1e-3: "1e-3", ALPHA_RECOUNT: "1.71e-4"}.get(a, f"{a:.3g}")


def scan_case():
    return N.LaneCase(R.cell_lane_weights(0.0, v=V), R.BETA_CAL, 0.05)


def recount_case(T):
    return N.LaneCase(R.Lane(np.array([1.0]), np.array([float(T)])), R.BETA_CAL, 1.0)


CASES = [("scan cell, lane centred, 0.1 m/s", scan_case())] + [(f"recount {T:g} s", recount_case(T)) for T in (10, 30, 60)]

# ------------------------------------------------------------------ (1) minimum window count
rows, tab = [], []
curves = {}
for cname, case in CASES:
    alphas = ALPHAS + ([ALPHA_RECOUNT] if cname.startswith("recount") else [])
    for H in DOSES:
        U = float(bgamma(H))
        g = N.variance_elasticity(case, U)
        for a in sorted(alphas, reverse=True):
            res = {}
            for rule in ("plugin", "predictive"):
                tbl = {}
                for n in GRID:
                    tbl[n] = N.achieved_fast(case, U, n, a, rule)
                    if tbl[n] <= 1.04:
                        break
                for n in GRID:                       # fill the rest monotonically for the table
                    tbl.setdefault(n, min(tbl.values()))
                curves[(cname, H, a, rule)] = tbl
                res[rule] = (N.min_n_ref(case, U, a, 1.10, rule, GRID, tbl)[0], N.min_n_ref(case, U, a, 1.05, rule, GRID, tbl)[0], tbl)
            f10, f05 = N.n_ref_formula(a, g, 1.10), N.n_ref_formula(a, g, 1.05)
            rows.append((cname, H, f"{U:.4g}", f"{a:.3g}", f"{g:.3f}", f"{(case.cal.k * U + case.cal.b) * case.lane.T:.4g}",
                         *[f"{res[r][i]:.4g}" for r in ("plugin", "predictive") for i in (0, 1)], f"{f10:.4g}", f"{f05:.4g}",
                         *[f"{res['plugin'][2][n]:.4f}" for n in (25, 100, 400)], *[f"{res['predictive'][2][n]:.4f}" for n in (25, 100, 400)]))
            tab.append((cname, H, afmt(a), g, res["plugin"][0], res["plugin"][1], f10, res["predictive"][0], res["predictive"][1],
                        f"{fmt(res['plugin'][2][100])} / {fmt(res['predictive'][2][100])}"))
    print(f"s8: N_ref {cname} {time.time() - t0:.0f} s", flush=True)
write_csv("rev4_n_ref.csv", ["statistic", "dose_rate_uSv_h", "U_cps", "alpha", "variance_elasticity_g", "null_floor_counts",
                             "N_ref_plugin_ratio_1.10", "N_ref_plugin_ratio_1.05", "N_ref_predictive_ratio_1.10", "N_ref_predictive_ratio_1.05",
                             "formula_plugin_1.10", "formula_plugin_1.05", "plugin_ratio_at_25", "plugin_ratio_at_100", "plugin_ratio_at_400",
                             "predictive_ratio_at_25", "predictive_ratio_at_100", "predictive_ratio_at_400"], rows)
md_table("rev4_n_ref", ["Statistic", "µSv/h", "α", "g", "Plug-in N_ref for ≤ 1.10", "for ≤ 1.05", "Formula z⁴g²/(8 ln 1.10)",
                        "Predictive N_ref for ≤ 1.10", "for ≤ 1.05", "Achieved/nominal at N_ref = 100: plug-in / predictive"], tab)


def nmax(rule, i, pred):
    return max(float(r[6 + 2 * (rule == "predictive") + i]) for r in rows if pred(r))


is_scan = lambda r: r[0].startswith("scan")
is_rec = lambda r: r[0].startswith("recount")
mis = lambda r: float(r[3]) == float(f"{ALPHA_SIDAK:.3g}")
S.update(rev4_plug_scan_mis_10=fmt(nmax("plugin", 0, lambda r: is_scan(r) and mis(r))),
         rev4_plug_scan_mis_05=fmt(nmax("plugin", 1, lambda r: is_scan(r) and mis(r))),
         rev4_pred_scan_mis_10=fmt(nmax("predictive", 0, lambda r: is_scan(r) and mis(r))),
         rev4_pred_scan_mis_05=fmt(nmax("predictive", 1, lambda r: is_scan(r) and mis(r))),
         rev4_plug_rec_mis_05=fmt(nmax("plugin", 1, lambda r: is_rec(r) and mis(r))),
         rev4_pred_rec_mis_05=fmt(nmax("predictive", 1, lambda r: is_rec(r) and mis(r))),
         rev4_pred_rec_mis_10=fmt(nmax("predictive", 0, lambda r: is_rec(r) and mis(r))),
         rev4_pred_scan_005_05=fmt(nmax("predictive", 1, lambda r: is_scan(r) and float(r[3]) == 0.05)),
         rev4_plug_scan_005_05=fmt(nmax("plugin", 1, lambda r: is_scan(r) and float(r[3]) == 0.05)),
         rev4_pred_all_05=fmt(nmax("predictive", 1, lambda r: True)), rev4_plug_all_05=fmt(nmax("plugin", 1, lambda r: True)))
PRED_NMIN = {a: max(float(r[9]) for r in rows if abs(float(r[3]) - a) / a < 1e-2) for a in ALPHAS + [ALPHA_RECOUNT]}

# ------------------------------------------------------------------ (2) pooled four-lane window: lane-to-lane response ratio
prow = []
case = scan_case()
for H in (0.1, 1.0):
    U = float(bgamma(H))
    for a in (0.05, ALPHA_SIDAK):
        for n in (200, 3200):
            line = [H, afmt(a), n]
            for eps in (-0.05, -0.02, -0.01, 0.0, 0.02, 0.05):
                line.append(N.achieved_fast(case, U, n, a, "predictive", rho=1 + eps))
            prow.append(line)
write_csv("rev4_pooled_ratio.csv", ["dose_rate_uSv_h", "alpha", "N_ref", "eps_-0.05", "eps_-0.02", "eps_-0.01", "eps_0", "eps_+0.02", "eps_+0.05"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in prow])
md_table("rev4_pooled", ["µSv/h", "α", "N_ref (pooled)", "lane response 5 % below pool", "2 % below", "1 % below", "equal", "2 % above", "5 % above"], prow)
S["rev4_pool_m5_mis"] = fmt(max(r[3] for r in prow if r[1] != "0.05"))
S["rev4_pool_m2_mis"] = fmt(max(r[4] for r in prow if r[1] != "0.05"))
S["rev4_pool_m1_mis"] = fmt(max(r[5] for r in prow if r[1] != "0.05"))
print(f"s8: pooled {time.time() - t0:.0f} s", flush=True)

# ------------------------------------------------------------------ (3) sensitivity cost of the predictive threshold
crow = []
for cname, case in (CASES[0], CASES[2]):
    for H in DOSES:
        U = float(bgamma(H))
        for a in (0.05, ALPHA_SIDAK):
            T_true = N.threshold_rule(case, 10 ** 7, 10 ** 7 / U, a, "plugin")          # U known
            r_true = N.rate_for_power(case, U, T_true)
            line = [cname, H, afmt(a)]
            for n in (50, 100, 400):
                tp = N.threshold_rule(case, n, n / U, a, "predictive")
                line.append(N.rate_for_power(case, U, tp) / r_true)
            crow.append(line)
write_csv("rev4_cost.csv", ["statistic", "dose_rate_uSv_h", "alpha", "D_hash_ratio_N50", "D_hash_ratio_N100", "D_hash_ratio_N400"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in crow])
md_table("rev4_cost", ["Statistic", "µSv/h", "α", "D# predictive ÷ D# with U known, N_ref = 50", "N_ref = 100", "N_ref = 400"], crow)
S["rev4_cost_100_max"] = fmt(max(r[4] for r in crow))
S["rev4_cost_50_max"] = fmt(max(r[3] for r in crow))
S["rev4_cost_400_max"] = fmt(max(r[5] for r in crow))
print(f"s8: cost {time.time() - t0:.0f} s", flush=True)

# ------------------------------------------------------------------ (4) field gradients at 0.1 m/s
NG = int(round(max(PRED_NMIN[ALPHA_SIDAK], 50)))          # window count used for the gradient study
EPS = np.array([-0.5, -0.3, -0.2, -0.1, -0.05, -0.02, 0.0, 0.05, 0.1, 0.25, 0.5])
case = scan_case()
fa_eps, dh_eps = {}, {}
for H in DOSES:
    U = float(bgamma(H))
    for a in (0.05, ALPHA_SIDAK):
        fa_eps[(H, a)] = np.array([N.achieved_fast(case, U, NG, a, "predictive", rho=1 + e) for e in EPS])
        T_true = N.threshold_rule(case, 10 ** 7, 10 ** 7 / U, a, "plugin")
        r_true = N.rate_for_power(case, U, T_true)
        dh_eps[(H, a)] = np.array([N.rate_for_power(case, U, N.threshold_rule(case, 10 ** 7, 10 ** 7 / (U * (1 + e)), a, "plugin")) / r_true
                                   for e in EPS])
SCEN = [("linear 1 %/m", 0.01, 0.0), ("linear 5 %/m", 0.05, 0.0), ("linear 20 %/m", 0.20, 0.0), ("step ×1.5 at the cell edge", 0.0, 0.5),
        ("step ×0.5 at the cell edge", 0.0, -0.5)]
MODES = ["centred mean", "past-only mean", "larger of past and future half-window means"]


def bias(mode, g, step, L):
    """Worst-case relative bias U_window/U_cell - 1.  Linear field 1 + g x increasing along travel (a past-only
    window then under-estimates).  Step: rates 1 and (1 + step) on the two sides of a boundary at the cell edge,
    the cell on either side and the window on either side; the worst (lowest) window estimate is returned.
    'larger of halves' uses the larger of the past and future half-window means (each half needs N_ref)."""
    if step == 0.0:
        return {"centred mean": 0.0, "past-only mean": -g * L / 2}.get(mode, +g * L / 4)
    low = min(1.0 + step, 1.0 / (1.0 + step))          # far-side rate relative to the cell, worst orientation
    return {"centred mean": 0.5 * (low - 1.0), "past-only mean": low - 1.0}.get(mode, 0.0)


grow = []
for H in DOSES:
    U = float(bgamma(H))
    for wname, mult in (("lane window", 1.0), ("pooled four-lane window", 4.0)):
        L = V * NG / (mult * U)
        for sname, g, step in SCEN:
            for mode in MODES:
                e = bias(mode, g, step, L)
                line = [H, wname, f"{L:.3g}", sname, mode, f"{100 * e:+.1f} %"]
                for a in (0.05, ALPHA_SIDAK):
                    line.append(float(np.interp(e, EPS, fa_eps[(H, a)])))
                line.append(float(np.interp(e, EPS, dh_eps[(H, 0.05)])))
                grow.append(line)
write_csv("rev4_gradients.csv", ["dose_rate_uSv_h", "window", "window_length_m", "field", "window_estimate", "bias_of_U_null",
                                 "fa_ratio_alpha_0.05", "fa_ratio_alpha_mission", "D_hash_ratio_alpha_0.05"],
          [[f"{x:.4g}" if isinstance(x, float) else x for x in r] for r in grow])
md_table("rev4_gradients", ["µSv/h", "Window", "Length (m)", "Field", "U_null estimate", "Bias of U_null",
                            "Achieved/nominal α = 0.05", "Achieved/nominal mission α", "D# ÷ unbiased D# (α = 0.05)"], grow)
S.update(rev4_NG=str(NG),
         rev4_grad_centred_max=fmt(max(r[7] for r in grow if r[4] == "centred mean")),
         rev4_grad_past_max=fmt(max(r[7] for r in grow if r[4] == "past-only mean")),
         rev4_grad_max_halves=fmt(max(r[7] for r in grow if r[4].startswith("larger"))),
         rev4_grad_max_halves_dh=fmt(max(r[8] for r in grow if r[4].startswith("larger"))),
         rev4_grad_step_centred=fmt(max(r[7] for r in grow if r[4] == "centred mean" and r[3].startswith("step"))),
         rev4_L_lane_01=fmt(V * NG / bgamma(0.1)), rev4_L_pool_01=fmt(V * NG / (4 * bgamma(0.1))),
         rev4_L_lane_1=fmt(V * NG / bgamma(1.0)), rev4_L_pool_1=fmt(V * NG / (4 * bgamma(1.0))))
print(f"s8: gradients {time.time() - t0:.0f} s", flush=True)

# ------------------------------------------------------------------ (5) recounts: where the null reference comes from
rrow = []
for T in (10, 30, 60):
    for H in DOSES:
        U = float(bgamma(H))
        for a in (ALPHA_RECOUNT, ALPHA_SIDAK):
            nmin = max(float(r[9]) for r in rows if r[0] == f"recount {T:g} s" and float(r[1]) == H and abs(float(r[3]) - a) / a < 1e-2)
            nmin = max(nmin, 25.0)
            n_other = 3.0 * U * T                                    # the other three lanes' references during the recount
            t_br = max(0.0, nmin - n_other) / (4.0 * U)              # extra bracketing time, all four references
            t_br_own = nmin / U                                      # bracketing with the tested lane's reference only
            rrow.append((T, H, afmt(a), nmin, n_other, t_br, t_br_own))
write_csv("rev4_recount.csv", ["recount_s", "dose_rate_uSv_h", "alpha", "N_ref_min_predictive_1.05", "counts_other_three_lanes_during_recount",
                               "extra_bracketing_s_four_lanes", "bracketing_s_own_lane_only"],
          [[f"{x:.4g}" if isinstance(x, float) else x for x in r] for r in rrow])
md_table("rev4_recount", ["Recount (s)", "µSv/h", "α", "N_ref needed (predictive, ≤ 1.05)", "Other three lanes' reference counts during the recount",
                          "Extra bracketing time with all four references (s)", "Bracketing time with the lane's own reference only (s)"], rrow)
S["rev4_rec_br_max"] = fmt(max(r[5] for r in rrow))
S["rev4_rec_own_max"] = fmt(max(r[6] for r in rrow))
S["rev4_rec_own_min"] = fmt(min(r[6] for r in rrow))
S["rev4_runtime"] = f"{time.time() - t0:.0f} s"
S["rev4_alpha_recount"] = afmt(ALPHA_RECOUNT)
update_summary(**S)

# ------------------------------------------------------------------ report fragment
summary = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
tpl = (ROOT / "report" / "model_rev4_unull.template.md").read_text(encoding="utf-8")
missing = []


def sub(m):
    kind, key = m.group(1), m.group(2)
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
    raise SystemExit("model_rev4_unull template refers to missing results: " + ", ".join(missing))
(ROOT / "report" / "model_rev4_unull.md").write_text(
    "<!-- GENERATED by scripts/s8_unull.py from model_rev4_unull.template.md and results/. Edit the template. -->\n" + text, encoding="utf-8")
print(f"s8: U_null study written ({time.time() - t0:.0f} s)")
