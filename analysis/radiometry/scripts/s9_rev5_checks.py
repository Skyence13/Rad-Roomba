#!/usr/bin/env python3
"""Step 9 - questions on MODEL.md revision 5 from the software (CR-13 gradient guard, CR-14/CR-17 N_min and
search-stage reference time), the multi-lane predictive reference with test vectors, alpha channel and k != 1.

Evidence class: calculated (exact lattice / Gil-Pelaez evaluation, sums over Poisson window counts) and simulated
(Monte Carlo over window counts, fixed seed), SYNTHETIC coefficients; nothing is measured.
RRRAD_FULL=1 adds the slow alpha-channel / k != 1 cases (about 10 min more).
Writes results/rev5_*.csv, results/rev5_predictive_vectors.json, results/tables/rev5_*.md, report/model_rev5_checks.md."""
import csv
import json
import os
import re
import time

import numpy as np

from common import ALPHA_SIDAK, ROOT, SEED, TABLES, bgamma, fmt, md_table, update_summary, write_csv
from rrrad import predictive as P
from rrrad import rev3 as R
from rrrad import unull as N

t0 = time.time()
rng = np.random.default_rng(SEED + 9)
S = {}
V = 0.10
FULL = os.environ.get("RRRAD_FULL") == "1"
NMIN = {0.05: 30, 1e-3: 75, ALPHA_SIDAK: 200}          # MODEL.md rev 5 table, as the software applies it
ALPHA_RECOUNT = 1.71e-4


def afmt(a):
    return {0.05: "0.05 (α_scan)", 1e-3: "1e-3"}.get(a, f"{a:.3g}")


case = N.LaneCase(R.Lane(np.array([1.0]), np.array([1.0])), R.BETA_CAL, 1.0)

# ------------------------------------------------------------------ (1) CR-13: one-sided reference
FIELDS = []
for g in (0.0, 0.01, 0.05, 0.125, 0.20):
    FIELDS.append((f"{100 * g:g} %/m, rising toward the dwell", "lin", -g))
    if g:
        FIELDS.append((f"{100 * g:g} %/m, falling toward the dwell", "lin", +g))
FIELDS += [("step ×1.5 between the sub-windows, higher at the dwell", "stepAB", 1 / 1.5),
           ("step ×1.5 between the sub-windows, lower at the dwell", "stepAB", 1.5),
           ("step ×1.5 between near sub-window and dwell, higher at the dwell", "stepB0", 1 / 1.5),
           ("step ×1.5 between near sub-window and dwell, lower at the dwell", "stepB0", 1.5)]
EST = [("larger", "rev 5: larger of the two means"), ("larger+guard", "rev 5 with the 2 % guard"),
       ("linear+floor", "proposed: max(U_B, 1.5 U_B − 0.5 U_A), slope uncertainty in N_eff")]
orow = []
for H, src in ((0.1, "pooled"), (1.0, "lane")):
    U = float(bgamma(H))
    for a, n in NMIN.items():
        Lsub = V * n / ((4.0 if src == "pooled" else 1.0) * U)          # sub-window length in m
        for fname, kind, par in FIELDS:
            if kind == "lin":
                f = (lambda x, g=par, L=Lsub: 1.0 + g * L * x)
            elif kind == "stepAB":
                f = (lambda x, r=par: 1.0 if x < 1.0 else r)
            else:
                f = (lambda x, r=par: r)
            line = [H, src, f"{Lsub:.3g}", afmt(a), n, fname]
            for e, _ in EST:
                ach, lost, dh = N.one_sided_study(case, U, n, a, f, e)
                line += [ach, lost, dh]
            orow.append(line)
hdr = ["dose_rate_uSv_h", "source", "sub_window_length_m", "alpha", "N_sub", "field"]
for e, _ in EST:
    hdr += [f"{e}_fa_ratio", f"{e}_fraction_discarded", f"{e}_D_hash_ratio"]
write_csv("rev5_one_sided.csv", hdr, [[f"{x:.4g}" if isinstance(x, float) else x for x in r] for r in orow])
md_table("rev5_one_sided", ["µSv/h", "Source", "Sub-window (m)", "α", "Field",
                            "rev 5 larger-mean: achieved/nominal, D# ratio", "rev 5 + 2 % guard: achieved/nominal, cells discarded",
                            "proposed: achieved/nominal, D# ratio"],
         [(r[0], r[1], r[2], r[3], r[5], f"{fmt(r[6])}, {fmt(r[8])}", f"{fmt(r[9])}, {100 * r[10]:.0f} %", f"{fmt(r[12])}, {fmt(r[14])}")
          for r in orow])
det = [r for r in orow if "near sub-window and dwell" not in r[5]]
S.update(rev5_os_prop_max=fmt(max(r[12] for r in det)), rev5_os_prop_dh_max=fmt(max(r[14] for r in det)),
         rev5_os_rev5_max=fmt(max(r[6] for r in det)), rev5_os_guard_lost_min=f"{100 * min(r[10] for r in orow if r[5].startswith('0 %')):.0f} %",
         rev5_os_guard_lost_max=f"{100 * max(r[10] for r in orow if r[5].startswith('0 %')):.0f} %",
         rev5_os_undet_max=fmt(max(max(r[6], r[12]) for r in orow if "near sub-window and dwell" in r[5] and "higher at the dwell" in r[5])),
         rev5_os_undet_005=fmt(max(max(r[6], r[12]) for r in orow if "near sub-window and dwell" in r[5] and "higher at the dwell" in r[5]
                                   and r[3].startswith("0.05"))),
         rev5_os_rev5_005=fmt(max(r[6] for r in det if r[3].startswith("0.05"))),
         rev5_os_prop_max_case=(lambda r: f"{r[5]}, {r[0]:g} µSv/h {r[1]}, α = {r[3]}")(max(det, key=lambda r: r[12])))
print(f"s9: one-sided {time.time() - t0:.0f} s", flush=True)

# ------------------------------------------------------------------ (2) CR-14 / CR-17: N_min and reference-acquisition time
scan_need = {}
with (ROOT / "results" / "rev4_n_ref.csv").open(encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        if r["statistic"].startswith("scan"):
            a = float(r["alpha"])
            scan_need[a] = max(scan_need.get(a, 0.0), float(r["N_ref_predictive_ratio_1.05"]))
prow = []
for H in (0.1, 1.0, 3.0):
    U = float(bgamma(H))
    for a_scan in (0.05, 1e-3, 1e-5):
        n_rule = 30 if a_scan >= 1e-2 else 75 if a_scan >= 1e-3 else 125 if a_scan >= 1e-4 else 200
        a_key = min(scan_need, key=lambda x: abs(np.log(x) - np.log(a_scan)))
        n_scan = int(np.ceil(scan_need[a_key] * (1.0 if a_scan >= 1e-4 else 1.05)))
        prow.append((H, f"search, α_scan = {a_scan:g}", n_rule, (2 * n_rule + 20) / (4 * U), n_scan, n_scan / (4 * U), 2 * n_rule / U))
    for T_r in (10, 30, 60):
        n_soft = 200                                   # software: N_min(0.2 alpha_recount) = N_min(3.4e-5)
        n_rec = 125                                    # proposed: N_min(alpha_recount), m = 1 has one test
        prow.append((H, f"recount {T_r} s, α_recount = 1.71e-4", n_soft, n_soft / (3 * U), n_rec, n_rec / (3 * U), max(0.0, n_rec / (3 * U) - T_r)))
write_csv("rev5_reference_time.csv", ["dose_rate_uSv_h", "stage", "N_min_rev5_as_implemented", "time_rev5_s", "N_min_proposed",
                                      "time_proposed_s", "lane_only_two_subwindows_s__or__recount_extra_s"],
          [[f"{x:.4g}" if isinstance(x, float) else x for x in r] for r in prow])
md_table("rev5_reference_time", ["µSv/h", "Stage", "N_min as implemented", "Reference time as implemented (s)", "N_min proposed",
                                 "Reference time proposed (s)", "Search: lane-only two sub-windows (s) / recount: extra time beyond the count (s)"], prow)
S["rev5_pre_1e5_01"] = fmt(next(r[3] for r in prow if r[0] == 0.1 and "1e-05" in r[1]))
S["rev5_pre_1e5_01_prop"] = fmt(next(r[5] for r in prow if r[0] == 0.1 and "1e-05" in r[1]))
S["rev5_pre_1e5_1_prop"] = fmt(next(r[5] for r in prow if r[0] == 1.0 and "1e-05" in r[1]))
S["rev5_pre_1e5_n"] = str(next(r[4] for r in prow if "1e-05" in r[1]))
print(f"s9: reference time {time.time() - t0:.0f} s", flush=True)

# ------------------------------------------------------------------ (3) multi-lane predictive reference, test vectors, achieved alpha
demo = json.loads((ROOT / "demo_calibration.json").read_text(encoding="utf-8"))
LC = []
for ln in demo["lanes"]:
    c = ln["classes"]["beta_window"]
    LC.append(R.Cal(k=1.0, b=c["b_cps"], u_k_lane=c["u_k_components"]["fit"], u_k_common=c["u_k_components"]["spectral_mismatch_relative"],
                    u_b=c["u_b_cps"], cov_kb=c["cov_kb_cps"], K=c["K_cps_per_Bq_cm2"], u_rel_K=c["u_rel_K"]))
geo = [R.cell_lane_weights(s, v=0.03) for s in (0.04375, -0.04375, 0.04375, -0.04375)]
vectors, vrow = [], []
for m in (1, 2, 4):
    for U, Nw in ((5.0, 100), (33.2, 200)):
        lanes, cals = geo[:m], LC[:m]
        C = R.Combined(lanes, cals, U)
        lps = [P.LanePost(l, c, ci, U, Nw, Nw / U) for l, c, ci in zip(lanes, cals, C.c)]
        ex = P.PredictiveCombined(lps)
        ap = P.PredictiveCombined(lps, approx_common=True)
        alphas = [0.05, 1e-3, ALPHA_SIDAK]
        te, ta = P.thresholds(ex, alphas), P.thresholds(ap, alphas)
        m_, v_ = ex.mean_var()
        f = ex.tail_fn(m_ - np.sqrt(v_), m_ + 12 * np.sqrt(v_))
        dh = [ex.detection_limit(t) for t in te] if m <= 2 else [None] * 3
        for a, t1, t2, d in zip(alphas, te, ta, dh):
            vrow.append((m, U, Nw, f"{a:.3g}", t1, t2, f(t2) / a, d))
        vectors.append({"m": m, "lanes": [{"w": l.w.tolist(), "t_s": l.t.tolist(), "c": float(ci),
                                           "cal": {"k": c.k, "b": c.b, "u_k_lane": c.u_k_lane, "u_k_common": c.u_k_common, "u_b": c.u_b,
                                                   "cov_kb": c.cov_kb, "K": c.K}, "U0": U, "posterior": {"N": Nw, "T_s": Nw / U}}
                                          for l, c, ci in zip(lanes, cals, C.c)],
                        "posterior_nodes": 12, "statistic": "S = sum_i c_i r_i / K_i; r_i = S_F,i/T_F,i - k S_U,i/T_U,i - b",
                        "results": [{"alpha": a, "t_star_exact": t1, "t_star_common_cross_terms_at_point_values": t2,
                                     "exact_tail_at_approx_t_star": f(t2), "D_hash_Bq_cm2_u_rel_K_0": d}
                                    for a, t1, t2, d in zip(alphas, te, ta, dh)]})
(ROOT / "results" / "rev5_predictive_vectors.json").write_text(json.dumps(
    {"note": "calculated with synthetic coefficients (analysis/radiometry rrrad.predictive, exact over the product of the lanes' "
             "posterior nodes); tolerance for software agreement: t* relative 1e-6 (exact form) or 1e-3 (cross-term approximation)",
     "cases": vectors}, indent=1) + "\n", encoding="utf-8")
write_csv("rev5_predictive_multilane.csv", ["m", "U_cps", "N_window", "alpha", "t_star_exact", "t_star_cross_terms_at_point_values",
                                            "exact_tail_at_approx_t_over_alpha", "D_hash_Bq_cm2"],
          [[f"{x:.8g}" if isinstance(x, float) else ("" if x is None else x) for x in r] for r in vrow])
md_table("rev5_multilane", ["m", "U (s⁻¹)", "N per lane", "α", "t* exact", "t* with cross terms at point values",
                            "Exact predictive tail at the approximate t* ÷ α", "D# (Bq/cm², u_rel(K)=0)"], vrow, sig=6)
S["rev5_ml_approx_max"] = fmt(max(r[6] for r in vrow), 4)
# achieved alpha with the windows drawn (truth = true U for every lane), m = 2, Monte Carlo over the window counts
NDRAW = 80
arow = []
for U, Nw in ((5.0, 100),):
    lanes, cals = geo[:2], LC[:2]
    C = R.Combined(lanes, cals, U)
    st = C.stat()
    alphas = [1e-3, ALPHA_SIDAK]
    tails = {a: [] for a in alphas}
    for _ in range(NDRAW):
        n = rng.poisson(Nw, 2)
        lps = [P.LanePost(l, c, ci, U, float(ni), Nw / U) for l, c, ci, ni in zip(lanes, cals, C.c, n)]
        ts = P.thresholds(P.PredictiveCombined(lps), alphas)
        for a, t in zip(alphas, ts):
            tails[a].append(float(R.L.tail_gp(st, t)[0]))
    for a in alphas:
        x = np.array(tails[a]) / a
        arow.append((2, U, Nw, f"{a:.3g}", float(x.mean()), float(x.std(ddof=1) / np.sqrt(x.size)), NDRAW))
write_csv("rev5_multilane_achieved.csv", ["m", "U_cps", "N_window", "alpha", "achieved_over_nominal", "mc_standard_error", "draws"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in arow])
md_table("rev5_multilane_achieved", ["m", "U (s⁻¹)", "N per lane", "α", "Achieved/nominal (windows drawn, exact tail at true U)",
                                     "Monte Carlo standard error", "Draws"], arow)
S["rev5_ml_ach"] = "; ".join(f"α = {r[3]}: {r[4]:.3f} ± {r[5]:.3f}" for r in arow)
print(f"s9: multi-lane {time.time() - t0:.0f} s", flush=True)

# ------------------------------------------------------------------ (4) alpha channel and k != 1 under the predictive threshold
krow = []
KCASES = [("alpha channel", R.ALPHA_CAL, 1.0), ("beta, k = 0.3 (reference 3× floor)", R.Cal(k=0.3), 1 / 0.3)]
for name, cal, Uf in KCASES:
    for T in (1.0, 30.0):
        for H in (0.1, 1.0):
            slow = (T == 30.0 and H == 1.0) or (name.startswith("beta") and (H == 1.0 or T == 30.0))
            if slow and not FULL:
                continue
            cs = N.LaneCase(R.Lane(np.array([1.0]), np.array([T])), cal, 1.0)
            U = float(bgamma(H)) * Uf
            for a, n in NMIN.items():
                krow.append((name, T, H, f"{a:.3g}", n, N.achieved_fast(cs, U, n, a, "predictive")))
write_csv("rev5_alpha_k.csv", ["statistic", "dwell_s", "dose_rate_uSv_h", "alpha", "N_min", "achieved_over_nominal_predictive"],
          [[f"{x:.5g}" if isinstance(x, float) else x for x in r] for r in krow])
md_table("rev5_alpha_k", ["Statistic", "Dwell (s)", "µSv/h", "α", "N_min (table)", "Achieved/nominal, predictive"], krow)
S["rev5_ak_max"] = fmt(max(r[5] for r in krow), 4)
S["rev5_ak_full"] = "all cases" if FULL else "fast subset (RRRAD_FULL=1 for all)"
S["rev5_runtime"] = f"{time.time() - t0:.0f} s"
update_summary(**S)

# ------------------------------------------------------------------ report
summary = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
tpl = (ROOT / "report" / "model_rev5_checks.template.md").read_text(encoding="utf-8")
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
    raise SystemExit("model_rev5_checks template refers to missing results: " + ", ".join(missing))
(ROOT / "report" / "model_rev5_checks.md").write_text(
    "<!-- GENERATED by scripts/s9_rev5_checks.py from model_rev5_checks.template.md and results/. Edit the template. -->\n" + text,
    encoding="utf-8")
print(f"s9: rev-5 checks written ({time.time() - t0:.0f} s)")
