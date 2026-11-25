#!/usr/bin/env python3
"""Step 1 - representative fields and the assumption register (report section 2)."""
import json

import numpy as np

from common import (B_OFF_ALPHA, B_OFF_BETA, C, DOSE_RATES, K_ALPHA_CASES, K_ALPHA_NOM, K_CASES, K_NOM,
                    RESULTS, S_ALPHA, S_BETA, S_BETA_RANGE, U_REL_K, U_REL_K_ALPHA, fmt, md_table, plt,
                    savefig, update_summary, write_csv)
from rrrad import fields as f

FIELDS = f.representative_fields()

# ---- photon lines and field summaries ----
rows = [(name, n, e, i) for name, lines in FIELDS.items() for n, e, i in lines]
write_csv("photon_lines.csv", ["field", "nuclide_or_component", "energy_keV", "photons_per_100_U238_decays"],
          [(a, b, f"{c:.1f}", f"{d:.5g}") for a, b, c, d in rows])

cs = f.field_summary(FIELDS["Cs137_calibration"])
summ = []
for name, lines in FIELDS.items():
    s = f.field_summary(lines)
    rel = {thr: f.field_summary(lines, thr / 1e3)["counts_per_air_kerma_rel"]
           / f.field_summary(FIELDS["Cs137_calibration"], thr / 1e3)["counts_per_air_kerma_rel"] for thr in (10, 30, 60)}
    summ.append((name, s["photon_MeV_per_U238_decay"], s["kerma_weighted_mean_keV"], s["count_weighted_mean_keV"],
                 rel[10], rel[30], rel[60]))
hdr = ["field", "photon_MeV_per_U238_decay", "kerma_weighted_mean_keV", "count_weighted_mean_keV",
       "counts_per_kerma_rel_Cs137_thr10keV", "counts_per_kerma_rel_Cs137_thr30keV", "counts_per_kerma_rel_Cs137_thr60keV"]
write_csv("photon_fields.csv", hdr, [(r[0],) + tuple(f"{x:.4g}" for x in r[1:]) for r in summ])
md_table("photon_fields", ["Field (emission spectrum)", "Photon MeV per U-238 decay", "Kerma-weighted mean keV",
                           "Count-weighted mean keV", "Counts per air kerma rel. Cs-137, thr 10 / 30 / 60 keV"],
         [(r[0].replace("_", " "), "n/a" if r[0].startswith("Cs") else r[1], r[2], r[3],
           f"{fmt(r[4])} / {fmt(r[5])} / {fmt(r[6])}") for r in summ])

# ---- spectral dependence of k for matched tiles (shield attenuation only) ----
krows = []
for mat, x in (("Al", 1.1), ("PVT", 1.1), ("Fe", 1.1), ("Fe", 0.4)):
    for fb in (0.5, 1.0):
        for thr in (10, 30, 60):
            ks = {n: f.transfer_k_matched(L, mat, x, fb, thr / 1e3) for n, L in FIELDS.items()}
            krows.append((mat, x, fb, thr, ks["Cs137_calibration"], ks["ore_equilibrium"], ks["ore_through_5mm_steel"],
                          ks["concentrate_bare"], ks["concentrate_through_2mm_steel"],
                          ks["concentrate_bare"] / ks["ore_equilibrium"] - 1,
                          ks["concentrate_bare"] / ks["Cs137_calibration"] - 1,
                          ks["ore_equilibrium"] / ks["Cs137_calibration"] - 1))
write_csv("k_spectral_mismatch.csv",
          ["shield", "shield_g_cm2", "fraction_through_shield", "threshold_keV", "k_Cs137", "k_ore", "k_ore_5mmFe",
           "k_conc", "k_conc_2mmFe", "rel_dk_conc_vs_ore", "rel_dk_conc_vs_Cs137", "rel_dk_ore_vs_Cs137"],
          [tuple(r[:4]) + tuple(f"{v:.5f}" for v in r[4:]) for r in krows])
md_table("k_mismatch", ["Beta shield", "g/cm2", "Fraction of photons through shield", "Threshold keV",
                        "k Cs-137", "k ore", "k concentrate", "Δk/k conc. vs ore", "Δk/k conc. vs Cs-137"],
         [(r[0], r[1], r[2], r[3], f"{r[4]:.3f}", f"{r[5]:.3f}", f"{r[7]:.3f}", f"{100*r[9]:.1f} %", f"{100*r[10]:.1f} %")
          for r in krows if r[3] in (10, 30)])
dk = np.array([abs(r[9]) for r in krows])
dk_cs = np.array([abs(r[10]) for r in krows])

# ---- background rates vs dose rate ----
brow = [(h, S_BETA * h, S_BETA_RANGE[0] * h, S_BETA_RANGE[1] * h, S_BETA * h + B_OFF_BETA, S_ALPHA * h + B_OFF_ALPHA)
        for h in DOSE_RATES]
write_csv("background_rates.csv", ["dose_rate_uSv_h", "B_gamma_beta_nominal_cps", "B_gamma_beta_low_cps",
                                   "B_gamma_beta_high_cps", "B_beta_total_nominal_cps", "B_alpha_total_nominal_cps"],
          [tuple(f"{v:.4g}" for v in r) for r in brow])
md_table("background_rates", ["Ambient dose rate µSv/h", "Floor beta-window photon rate B_γ, nominal (range) s⁻¹",
                              "Beta-window total B s⁻¹", "Alpha-channel total s⁻¹"],
         [(r[0], f"{fmt(r[1])} ({fmt(r[2])}–{fmt(r[3])})", r[4], r[5]) for r in brow])

# ---- K by measurand basis ----
g10, g3 = f.rect_geometry_factor(h=0.010), f.rect_geometry_factor(h=0.003)
Kb = {name: (v, f.K_beta_by_basis(geom=g10 / g3)[name], f.K_beta_by_basis(geom=1.0 / g3)[name])
      for name, v in f.K_beta_by_basis().items()}
ore_lo = f.K_beta_by_basis(geom=g10 / g3, radon_retention=0.7)["ore, per Bq of U-238 (chain in equilibrium)"]
write_csv("K_beta_basis.csv", ["measurand_basis_for_1_Bq_cm2", "K_nominal_geom1", "K_aperture_size_source_10mm",
                               "K_wide_source_10mm"], [(n,) + tuple(f"{x:.3g}" for x in v) for n, v in Kb.items()])
md_table("K_beta_basis", ["Meaning of “1 Bq/cm²”", "K at anchor geometry", "K, aperture-size source at 10 mm",
                          "K, wide source at 10 mm"], [(n,) + v for n, v in Kb.items()])

# ---- alpha efficiency vs standoff ----
arows = []
for nuc in ("U-238", "U-234", "Ra-226", "Po-210", "Po-214"):
    for h in (3, 5, 8, 10, 12, 15):
        for tc in (15, -20):
            arows.append((nuc, f.ALPHA_MEV[nuc], h, tc, f.alpha_eff_4pi(nuc, h, tc)))
write_csv("alpha_efficiency.csv", ["nuclide", "alpha_MeV", "standoff_mm", "air_temp_C", "eff_4pi_thin_source"],
          [(a, b, c, d, f"{e:.4f}") for a, b, c, d, e in arows])
eff = {(a, c, d): e for a, b, c, d, e in arows}
md_table("alpha_efficiency", ["Nuclide (α MeV)", "3 mm", "8 mm", "10 mm", "12 mm", "15 mm", "10 mm at −20 °C"],
         [(f"{n} ({f.ALPHA_MEV[n]})",) + tuple(eff[(n, h, 15)] for h in (3, 8, 10, 12, 15)) + (eff[(n, 10, -20)],)
          for n in ("U-238", "U-234", "Ra-226", "Po-210", "Po-214")])
unat10 = 0.5 * (eff[("U-238", 10, 15)] + eff[("U-234", 10, 15)])
unat12 = 0.5 * (eff[("U-238", 12, 15)] + eff[("U-234", 12, 15)])
unat10c = 0.5 * (eff[("U-238", 10, -20)] + eff[("U-234", 10, -20)])
unat3 = 0.5 * (eff[("U-238", 3, 15)] + eff[("U-234", 3, 15)])

# ---- assumption register ----
reg = [
    ("A_a", "aperture area", 80.0, "80", "cm2", "design 0.3 Rev D layout (80 mm x 100 mm)", "design value"),
    ("L/v", "dwell of an interior point, one pass", 1.0, "1 (0.10 m/s)", "s", "MODEL.md section 5", "design value"),
    ("H", "ambient dose rate on the trailer floor", 0.1, "0.05-5 (stress case 10)", "uSv/h",
     "natural background ~0.1; elevated near ore, loaded conveyances and mill yards; no site data",
     "ASSUMED - needs site survey"),
    ("S_beta", "floor beta-window photon response", S_BETA, f"{S_BETA_RANGE[0]:g}-{S_BETA_RANGE[1]:g}", "1/s per uSv/h",
     "Mirion AB-100 42 (1/s)/(uSv/h) for Cs-137, 101.25 cm2 [H7], scaled by area to 80 cm2; range covers spectrum "
     "(x0.8 ore-like to x1.8 concentrate-like in the thin-tile model), housing and threshold", "ASSUMED from another product"),
    ("S_alpha", "floor alpha-channel photon response", S_ALPHA, "0.05-0.5", "1/s per uSv/h",
     "AB-100 0.2 (1/s)/(uSv/h) [H7] scaled by area", "ASSUMED from another product"),
    ("b_beta", "beta-window rate not tracked by the reference", B_OFF_BETA, "0-2", "1/s",
     "AB-100 background <= 5 1/s at <= 0.1 uSv/h, 4.0 used for its MDA [H7]; 4.2 predicted from S alone", "ASSUMED"),
    ("b_alpha", "alpha-channel intrinsic background", B_OFF_ALPHA, "0.005-0.05", "1/s",
     "AB-100 <= 0.05 1/s, 0.01 used for MDA [H7], scaled", "ASSUMED from another product"),
    ("k", "floor/reference photon count ratio", 1.0, "1 (matched tile); 0.3; 0.1 (reference 3x/10x more sensitive)", "-",
     "matched thin tile gives k ~ 1; a thicker reference tile raises photon interactions roughly in proportion to "
     "thickness (NIST mu for vinyltoluene)", "ASSUMED - design variable"),
    ("u(k)/k", "relative uncertainty of k incl. spectral mismatch", 0.03, "0-0.10", "-",
     f"fit component ~1 %; spectral component between ore-like and concentrate-like fields {100*dk.min():.1f}-"
     f"{100*dk.max():.1f} % in the shield-attenuation model (results/k_spectral_mismatch.csv); other mechanisms unmodelled",
     "ASSUMED - needs measurement"),
    ("u(b)", "uncertainty of the offset", 0.05, "0-0.2", "1/s", "long clean-floor run", "ASSUMED"),
    ("T_U/T_F", "reference live time per floor live time", 1.0, "1; 4 (four lanes pooled); 10 (running mean)", "-",
     "design choice; pooling/averaging assumes the field is uniform over the pooled extent", "design variable"),
    ("sigma_delta", "relative non-uniformity of the photon field (uncompensated)", 0.2, "0-0.5", "-",
     "gradients along a 16 m trailer, door end, neighbouring loads, time variation; no site data", "ASSUMED - needs site survey"),
    ("T_0", "background count time, uncompensated", 60.0, "10-600", "s", "procedure choice", "ASSUMED"),
    ("K_beta", "beta-window response", K_NOM, f"{K_CASES[0]:g}-{K_CASES[-1]:g}", "1/s per Bq/cm2",
     "AB-100 contact responses [H7] x 80 cm2 x geometry; the value depends on what 1 Bq/cm2 means "
     "(results/K_beta_basis.csv); nominal = Cl-36-equivalent", "ASSUMED - dominated by the undefined measurand"),
    ("u_rel(K_beta)", "relative uncertainty of K_beta", U_REL_K, "0.10-0.30", "-",
     "source certificate, standoff, self-absorption, floor finish", "ASSUMED"),
    ("K_alpha", "alpha-channel response at 10 mm", K_ALPHA_NOM, f"{K_ALPHA_CASES[0]:g}-{K_ALPHA_CASES[-1]:g}", "1/s per Bq/cm2 (alpha)",
     f"range model anchored to AB-100 Pu-239 [H7]: thin natural U {80*unat10:.1f}, all ore alphas ~13, "
     "thick/dusty deposits lower", "ASSUMED - model, not data"),
    ("u_rel(K_alpha)", "relative uncertainty of K_alpha", U_REL_K_ALPHA, "0.3-0.6", "-",
     "standoff (-15 to -30 %/mm for U-238), air density, self-absorption", "ASSUMED"),
    ("alpha,beta", "per-decision error probabilities", 0.05, "0.05; Sidak value for the mission", "-",
     "MODEL.md section 3 default; site profile owns them", "site decision"),
    ("A_mission", "per-mission false-investigation allowance", 0.05, "0.05 (P>=1); also expected counts 1-20", "-",
     "not defined by the site", "site decision"),
    ("n", "independent decision areas per trailer", 4480, "1333-5000", "-",
     "2.5 m x 16 m; 28 lane tracks x 160 cells of 0.1 m", "derived"),
    ("eps", "fraction of floor surface signal appearing in the reference", 0.0, "0-0.2", "-",
     "depends on the beta shield between the tiles (Pa-234m 2.27 MeV, Bi-214 3.27 MeV end points)", "ASSUMED - needs measurement"),
]
keys = ["symbol", "quantity", "nominal", "range", "unit", "basis_and_source", "status"]
(RESULTS / "parameter_space.json").write_text(json.dumps(
    {"note": "Assumption register. No entry is a measured property of the Rad Roomba detector.",
     "sources": {"H7": "Mirion CSPevo AB-100 datasheet SPC-651-EN-A (docs/Sources.csv H7)",
                 "NIST": "NIST X-ray mass attenuation coefficient tables (Al, Fe, vinyltoluene, air)",
                 "DECAY": "evaluated decay data (DDEP/ENSDF), transcribed from memory, not re-verified"},
     "assumptions": [dict(zip(keys, r)) for r in reg]}, indent=1) + "\n", encoding="utf-8")
md_table("assumptions", ["Symbol", "Quantity", "Nominal", "Range studied", "Unit", "Basis / source", "Status"], reg)

# ---- figure 1: spectra and k ----
fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.3))
bins = np.geomspace(30, 3000, 25)
for name, col in (("ore_equilibrium", C["comp"]), ("concentrate_bare", C["unc"])):
    L = FIELDS[name]
    e = np.array([l[1] for l in L])
    w = f.count_weights(L)
    ax[0].hist(e, bins=bins, weights=w / w.sum(), histtype="step", lw=1.6, color=col,
               label=name.replace("_", " ").replace("bare", "(aged, bare)"))
ax[0].axvline(661.7, color=C["level"], ls=":", lw=1)
ax[0].text(690, 0.42, "Cs-137", fontsize=8, color=C["level"])
ax[0].set_xscale("log")
ax[0].set_xlabel("photon energy (keV)")
ax[0].set_ylabel("share of thin-tile photon counts per bin")
ax[0].set_title("Count-weighted emission spectra (30 keV threshold)")
ax[0].legend(loc="upper left")
lab = [f"{r[0]} {r[1]:g} g/cm²\n{int(100*r[2])} % via shield" for r in krows if r[3] == 30]
vals = [(r[5], r[7], r[4]) for r in krows if r[3] == 30]
x = np.arange(len(lab))
ax[1].plot(x, [v[0] for v in vals], "o", color=C["comp"], label="ore")
ax[1].plot(x, [v[1] for v in vals], "s", color=C["unc"], label="concentrate")
ax[1].plot(x, [v[2] for v in vals], "^", color=C["level"], label="Cs-137")
ax[1].set_xticks(x, lab, rotation=60, ha="right", fontsize=7)
ax[1].set_ylabel("k = floor / reference photon counts")
ax[1].set_title("Matched tiles: k depends on the field spectrum")
ax[1].legend()
savefig(fig, "fig01_spectra_k.png")

# ---- figure 2: alpha efficiency vs standoff ----
fig, ax = plt.subplots(figsize=(4.8, 3.3))
hh = np.linspace(0, 20, 81)
for nuc, col in (("U-238", C["unc"]), ("U-234", C["alt"]), ("Po-210", C["comp2"]), ("Po-214", C["comp"])):
    ax.plot(hh, [f.alpha_eff_4pi(nuc, h) for h in hh], color=col, label=f"{nuc} ({f.ALPHA_MEV[nuc]} MeV)")
    ax.plot(hh, [f.alpha_eff_4pi(nuc, h, -20) for h in hh], color=col, ls="--", lw=1)
ax.axvline(10, color=C["level"], ls=":", lw=1)
ax.text(10.3, 0.33, "design standoff", fontsize=8, color=C["level"])
ax.set_xlabel("entrance film to floor (mm)")
ax.set_ylabel("counts per α decay (thin, clean deposit)")
ax.set_title("Alpha range model: solid 15 °C, dashed −20 °C")
ax.legend(fontsize=8)
savefig(fig, "fig02_alpha_standoff.png")

update_summary(
    S_beta=fmt(S_BETA), S_alpha=fmt(S_ALPHA), geom10=fmt(g10), geom3=fmt(g3), geom_ratio=fmt(g10 / g3),
    dk_min=f"{100*dk.min():.1f}", dk_max=f"{100*dk.max():.1f}", dkcs_max=f"{100*dk_cs.max():.1f}",
    ore_MeV=fmt(summ[0][1]), conc_MeV=fmt(summ[2][1]), ore_conc_ratio=fmt(summ[0][1] / summ[2][1], 2),
    rel_ore=fmt(summ[0][5], 2), rel_conc=fmt(summ[2][5], 2),
    eff_u238_10=f"{100*eff[('U-238',10,15)]:.1f}", eff_u238_12=f"{100*eff[('U-238',12,15)]:.1f}",
    eff_u238_10c=f"{100*eff[('U-238',10,-20)]:.1f}", eff_u234_10=f"{100*eff[('U-234',10,15)]:.1f}",
    eff_unat_10=f"{100*unat10:.1f}", eff_unat_3=f"{100*unat3:.1f}", K_alpha_unat10=fmt(80 * unat10, 2),
    K_alpha_unat12=fmt(80 * unat12, 2), K_alpha_unat10c=fmt(80 * unat10c, 2),
    alpha_drop_2mm=f"{100*(1-unat12/unat10):.0f}", alpha_drop_cold=f"{100*(1-unat10c/unat10):.0f}",
    alpha_derate=fmt(f.alpha_derating_from_ab100(), 2), K_ore_lo=fmt(ore_lo, 2),
)
print("s1: parameter space written")
