"""Representative uranium-series photon fields and order-of-magnitude detector responses.

Everything in this module is an ASSUMPTION or a quantity DERIVED from stated
assumptions and published data for other instruments. Nothing here is a measured
property of the Rad Roomba head. Each constant carries its source and status:

    [NIST]   NIST XCOM / X-ray mass attenuation tables, fetched 2026-11-25
             (physics.nist.gov/PhysRefData/XrayMassCoef; Al, Fe, vinyltoluene, air)
    [H7]     Mirion CSPevo AB-100 datasheet SPC-651-EN-A (docs/Sources.csv H7), read 2026-11-25
    [DECAY]  evaluated decay data (DDEP / ENSDF-NuDat values), quoted from the analyst's
             memory and NOT re-fetched; a few per cent relative accuracy is all the
             study needs. Status: unverified transcription.
    [ASSUMED] engineering assumption with the stated range
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# [NIST] mass attenuation (mu/rho) and mass energy-absorption (mu_en/rho), cm2/g
# --------------------------------------------------------------------------
E_GRID = np.array([0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60,
                   0.80, 1.00, 1.25, 1.50, 2.00, 3.00])  # MeV
MU = {
    "Al": np.array([1.128, 0.5685, 0.3681, 0.2778, 0.2018, 0.1704, 0.1378, 0.1223, 0.1042,
                    0.09276, 0.08445, 0.07802, 0.06841, 0.06146, 0.05496, 0.05006, 0.04324, 0.03541]),
    "Fe": np.array([8.176, 3.629, 1.958, 1.205, 0.5952, 0.3717, 0.1964, 0.1460, 0.1099,
                    0.09400, 0.08414, 0.07704, 0.06699, 0.05995, 0.05350, 0.04883, 0.04265, 0.03621]),
    "PVT": np.array([0.2647, 0.2194, 0.1997, 0.1881, 0.1736, 0.1635, 0.1458, 0.1331, 0.1155,
                     0.1034, 0.09443, 0.08732, 0.07668, 0.06894, 0.06166, 0.05611, 0.04810, 0.03848]),
    "air": np.array([0.3538, 0.2485, 0.2080, 0.1875, 0.1662, 0.1541, 0.1356, 0.1233, 0.1067,
                     0.09549, 0.08712, 0.08055, 0.07074, 0.06358, 0.05687, 0.05175, 0.04447, 0.03581]),
}
MU_EN_AIR = np.array([0.1537, 0.06833, 0.04098, 0.03041, 0.02407, 0.02325, 0.02496, 0.02672,
                      0.02872, 0.02949, 0.02966, 0.02953, 0.02882, 0.02789, 0.02666, 0.02547,
                      0.02345, 0.02057])
RHO_PVT = 1.032  # g/cm3, vinyltoluene plastic scintillator [NIST material table]


def mu(material: str, E_MeV):
    """Log-log interpolated mu/rho (cm2/g). Valid 0.03-3 MeV; clipped outside."""
    E = np.clip(np.asarray(E_MeV, float), E_GRID[0], E_GRID[-1])
    return np.exp(np.interp(np.log(E), np.log(E_GRID), np.log(MU[material])))


def mu_en_air(E_MeV):
    E = np.clip(np.asarray(E_MeV, float), E_GRID[0], E_GRID[-1])
    return np.exp(np.interp(np.log(E), np.log(E_GRID), np.log(MU_EN_AIR)))


# --------------------------------------------------------------------------
# [DECAY] principal photon lines: (nuclide, energy keV, photons per 100 decays of the nuclide)
# --------------------------------------------------------------------------
U235_PER_U238 = 0.046  # activity ratio in natural uranium [DECAY]

_TH234 = [("Th-234", 63.3, 3.75), ("Th-234", 92.4, 2.18), ("Th-234", 92.8, 2.15)]
_PA234M = [("Pa-234m", 766.4, 0.323), ("Pa-234m", 1001.0, 0.847)]
_U235 = [("U-235", 143.8, 10.94), ("U-235", 163.4, 5.08), ("U-235", 185.7, 57.0), ("U-235", 205.3, 5.02)]
_TH231 = [("Th-231", 84.2, 6.6)]
_RA226 = [("Ra-226", 186.2, 3.56)]
_PB214 = [("Pb-214", 242.0, 7.27), ("Pb-214", 295.2, 18.42), ("Pb-214", 351.9, 35.60)]
_BI214 = [("Bi-214", 609.3, 45.49), ("Bi-214", 768.4, 4.89), ("Bi-214", 934.1, 3.10),
          ("Bi-214", 1120.3, 14.91), ("Bi-214", 1238.1, 5.83), ("Bi-214", 1377.7, 3.97),
          ("Bi-214", 1408.0, 2.39), ("Bi-214", 1509.2, 2.13), ("Bi-214", 1729.6, 2.84),
          ("Bi-214", 1764.5, 15.31), ("Bi-214", 1847.4, 2.03), ("Bi-214", 2204.2, 4.91),
          ("Bi-214", 2447.9, 1.55)]
_PB210 = [("Pb-210", 46.5, 4.25)]

PA234M_BETA_Q_MEV = 2.27       # dominant branch end point [DECAY]
PA234M_BETA_MEAN_MEV = 0.82    # mean beta energy [DECAY]


def _scaled(lines, factor=1.0):
    return [(n, e, i * factor) for n, e, i in lines]


def lines_ore():
    """Ore in secular equilibrium, photons per 100 decays of U-238.

    The U-235 series progeny (4.6 % activity) other than U-235 itself are omitted.
    """
    return _TH234 + _PA234M + _RA226 + _PB214 + _BI214 + _PB210 + _scaled(_U235, U235_PER_U238)


def lines_concentrate():
    """Chemically separated concentrate aged > ~6 months (Th-234/Pa-234m regrown, T1/2 24.1 d;
    Ra-226 and progeny absent), photons per 100 decays of U-238. Line emission only."""
    return _TH234 + _PA234M + _scaled(_U235, U235_PER_U238) + _scaled(_TH231, U235_PER_U238)


def bremsstrahlung_concentrate(z_eff: float = 85.0, kramers_k: float = 0.7e-3, n_bins: int = 24):
    """Thick-target bremsstrahlung of the Pa-234m beta in the concentrate itself. [ASSUMED]

    Kramers thick-target law for an electron of kinetic energy T (MeV):
    photon number spectrum dN/dE = 2 k Z (T - E)/E, radiated fraction k Z T. The
    default k = 0.7e-3 /MeV makes the radiated fraction of the Pa-234m beta energy
    about 7 %, the value of the textbook thick-target rule Y ~ 3.5e-4 Z E_max
    (range used in the literature: 0.7e-3 to 1.1e-3 /MeV; treat as +-50 %). The beta
    spectrum is the allowed shape without Fermi function. Returns pseudo-lines
    (label, energy keV, photons per 100 U-238 decays) on n_bins logarithmic bins
    from 30 keV to the end point. This is an order-of-magnitude construction.
    """
    Q, me = PA234M_BETA_Q_MEV, 0.511
    T = np.linspace(1e-3, Q, 2000)
    shape = np.sqrt(T * T + 2 * T * me) * (T + me) * (Q - T) ** 2
    shape /= np.trapezoid(shape, T)
    edges = np.geomspace(0.03, Q, n_bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        E = np.geomspace(lo, hi, 40)
        dn = np.array([np.trapezoid(shape * 2 * kramers_k * z_eff * np.maximum(T - e, 0.0) / e, T) for e in E])
        n_ph = np.trapezoid(dn, E)
        e_mean = np.trapezoid(dn * E, E) / n_ph
        out.append(("brems(Pa-234m)", 1e3 * e_mean, 100.0 * n_ph))
    return out


def filtered(lines, material: str, areal_density_g_cm2: float):
    """Narrow-beam attenuation of a line list by an absorber (no build-up)."""
    return [(n, e, i * float(np.exp(-mu(material, e / 1e3) * areal_density_g_cm2))) for n, e, i in lines]


def representative_fields():
    """Named photon fields used to span the spectral space (emission spectra; scatter not modelled)."""
    conc = lines_concentrate() + bremsstrahlung_concentrate()
    return {
        "ore_equilibrium": lines_ore(),
        "ore_through_5mm_steel": filtered(lines_ore(), "Fe", 0.5 * 7.87),
        "concentrate_bare": conc,
        "concentrate_through_2mm_steel": filtered(conc, "Fe", 0.2 * 7.87),
        "Cs137_calibration": [("Cs-137", 661.7, 85.1)],
    }


# --------------------------------------------------------------------------
# Thin-tile photon count weighting and transfer-coefficient spectral dependence
# --------------------------------------------------------------------------
def compton_tmax(E_MeV):
    E = np.asarray(E_MeV, float)
    return 2 * E * E / (0.511 + 2 * E)


def threshold_fraction(E_MeV, E_thr_MeV=0.03):
    """Fraction of Compton electrons above threshold, flat recoil spectrum 0..Tmax. [ASSUMED, crude]"""
    return np.clip(1.0 - E_thr_MeV / compton_tmax(E_MeV), 0.0, 1.0)


def count_weights(lines, thickness_cm=0.025, E_thr_MeV=0.03):
    """Relative count weight of each line in a thin PVT tile: I * P(interact) * P(above threshold)."""
    e = np.array([l[1] for l in lines]) / 1e3
    i = np.array([l[2] for l in lines])
    return i * (1.0 - np.exp(-mu("PVT", e) * RHO_PVT * thickness_cm)) * threshold_fraction(e, E_thr_MeV)


def field_summary(lines, E_thr_MeV=0.03):
    """Photon energy per decay, kerma- and count-weighted mean energies, counts per unit air kerma."""
    e = np.array([l[1] for l in lines]) / 1e3
    i = np.array([l[2] for l in lines]) / 100.0
    w = count_weights(lines, E_thr_MeV=E_thr_MeV)
    kerma = i * e * mu_en_air(e)
    return {
        "photon_MeV_per_U238_decay": float(np.sum(i * e)),
        "kerma_weighted_mean_keV": float(1e3 * np.sum(kerma * e) / np.sum(kerma)),
        "count_weighted_mean_keV": float(1e3 * np.sum(w * e) / np.sum(w)),
        "counts_per_air_kerma_rel": float(np.sum(w) / np.sum(kerma)),
    }


def transfer_k_matched(lines, shield_material="Al", shield_g_cm2=1.1, frac_from_below=0.5, E_thr_MeV=0.03):
    """Floor/reference photon count ratio k for two identical thin tiles when the fraction
    frac_from_below of the photons reaches the reference through the beta shield. [ASSUMED model]

    Only shield attenuation is modelled; wall electrons, scatter, thresholds and
    geometry differences are not.
    """
    e = np.array([l[1] for l in lines]) / 1e3
    w = count_weights(lines, E_thr_MeV=E_thr_MeV)
    trans = np.exp(-mu(shield_material, e) * shield_g_cm2)
    return float(np.sum(w) / np.sum(w * (frac_from_below * trans + 1.0 - frac_from_below)))


# --------------------------------------------------------------------------
# [H7] commercial dual-phosphor anchor (Mirion AB-100, ZnS(Ag) on 0.25 mm plastic)
# --------------------------------------------------------------------------
AB100 = {
    "area_cm2": 101.25,
    "gamma_beta_cps_per_uSv_h": 42.0,     # Cs-137
    "gamma_alpha_cps_per_uSv_h": 0.2,     # Cs-137
    "bkg_beta_cps_max": 5.0, "bkg_beta_cps_mda_basis": 4.0,     # at <= 0.1 uSv/h
    "bkg_alpha_cps_max": 0.05, "bkg_alpha_cps_mda_basis": 0.01,
    "window_mg_cm2": 0.84,                # 2 x 3 um aluminised Mylar (datasheet prints ug/cm2)
    "grid_transparency": 0.83,
    "crosstalk_alpha_to_beta_max": 0.05, "crosstalk_beta_to_alpha_max": 0.001,
    # typical response to activity, (c/s)/Bq, 100 cm2 ISO 8769 sources in contact
    "resp_cps_per_Bq": {"Am-241": 0.22, "Pu-239": 0.23, "Sr-90+Y-90": 0.62, "Cl-36": 0.30,
                        "Cs-137": 0.25, "Co-60": 0.13, "C-14": 0.02},
    "eff_2pi": {"Am-241": 0.46, "Pu-239": 0.49, "Sr-90+Y-90": 0.48, "Cl-36": 0.49,
                "Cs-137": 0.40, "Co-60": 0.25, "C-14": 0.06},
}
APERTURE_CM2 = 80.0


def photon_response_scaled(channel="beta"):
    """AB-100 Cs-137 photon response scaled by area to one 80 cm2 segment (1/s per uSv/h)."""
    key = "gamma_beta_cps_per_uSv_h" if channel == "beta" else "gamma_alpha_cps_per_uSv_h"
    return AB100[key] * APERTURE_CM2 / AB100["area_cm2"]


# --------------------------------------------------------------------------
# Geometry factor for a source the size of the aperture at standoff h
# --------------------------------------------------------------------------
def rect_geometry_factor(a=0.08, b=0.10, h=0.010, n=400_000, seed=20261125):
    """Fraction of isotropic 2*pi emissions from a uniform a x b source that cross a coaxial
    a x b plane at height h (no absorption). Deterministic Monte Carlo (fixed seed)."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-a / 2, a / 2, n)
    y = rng.uniform(-b / 2, b / 2, n)
    cos_t = rng.uniform(0.0, 1.0, n)
    phi = rng.uniform(0.0, 2 * np.pi, n)
    tan_t = np.sqrt(1 - cos_t**2) / np.maximum(cos_t, 1e-12)
    xh = x + h * tan_t * np.cos(phi)
    yh = y + h * tan_t * np.sin(phi)
    return float(np.mean((np.abs(xh) <= a / 2) & (np.abs(yh) <= b / 2)))


# --------------------------------------------------------------------------
# Alpha channel at standoff: continuous-slowing-down range model  [ASSUMED model]
# --------------------------------------------------------------------------
ALPHA_MEV = {"U-238": 4.20, "U-235": 4.40, "U-234": 4.77, "Th-230": 4.69, "Ra-226": 4.78,
             "Po-210": 5.30, "Rn-222": 5.49, "Po-218": 6.00, "Po-214": 7.69,
             "Pu-239": 5.16, "Am-241": 5.49}  # principal alpha energies [DECAY]


def alpha_range_air_cm(E_MeV):
    """Mean range in air at 15 C, 1 atm: 0.56 E (E < 4 MeV), 1.24 E - 2.62 (4-8 MeV).
    Standard empirical range-energy relation (e.g. Cember & Johnson, Introduction to
    Health Physics); few-per-cent accuracy."""
    E = np.asarray(E_MeV, float)
    return np.where(E < 4.0, 0.56 * E, 1.24 * E - 2.62)


def alpha_2pi_fraction(E_MeV, standoff_mm, *, window_air_eq_mm=7.0, temp_C=15.0, E_thr_MeV=1.0):
    """Fraction of the 2*pi surface emission of a thin, wide source that reaches the ZnS with
    more than E_thr residual energy. Straight tracks; path = (air gap + window)/cos(theta)."""
    rho_rel = 288.15 / (273.15 + temp_C)
    budget = alpha_range_air_cm(E_MeV) - alpha_range_air_cm(E_thr_MeV)
    need = (standoff_mm * rho_rel + window_air_eq_mm) / 10.0
    return float(np.clip(1.0 - need / np.maximum(budget, 1e-9), 0.0, 1.0))


def alpha_derating_from_ab100(contact_gap_mm=3.0, **kw):
    """Factor that makes the range model reproduce the AB-100 Pu-239 2*pi efficiency (0.49),
    assuming the 'contact' source sits contact_gap_mm from the window. Absorbs grid
    transparency, grid collimation and pulse-height losses."""
    return AB100["eff_2pi"]["Pu-239"] / alpha_2pi_fraction(ALPHA_MEV["Pu-239"], contact_gap_mm, **kw)


def alpha_eff_4pi(nuclide, standoff_mm, temp_C=15.0, contact_gap_mm=3.0, **kw):
    """Order-of-magnitude 4*pi alpha efficiency (counts per alpha decay) of a thin clean deposit."""
    d = alpha_derating_from_ab100(contact_gap_mm, **kw)
    return 0.5 * d * alpha_2pi_fraction(ALPHA_MEV[nuclide], standoff_mm, temp_C=temp_C, **kw)


# --------------------------------------------------------------------------
# Beta-window response K by measurand basis  [ASSUMED, anchored to H7 contact efficiencies]
# --------------------------------------------------------------------------
# Counts per decay of each beta emitter for a thin source near contact, read across
# from the AB-100 values by beta end-point energy (C-14 0.156 MeV: 0.02; Co-60 0.318: 0.13;
# Cl-36 0.709: 0.30; Y-90 2.28: ~0.33 = 0.62 minus an Sr-90 share of ~0.29).
BETA_EFF_4PI = {
    "Th-234": (0.05, "E_max 0.20 MeV, between C-14 and Co-60; conversion electrons add"),
    "Pa-234m": (0.33, "E_max 2.27 MeV, as Y-90"),
    "Pb-214": (0.28, "E_max 0.67-1.02 MeV, as Cl-36"),
    "Bi-214": (0.32, "E_max up to 3.27 MeV"),
    "Bi-210": (0.31, "E_max 1.16 MeV"),
    "Pb-210": (0.00, "E_max 0.017/0.063 MeV, below window"),
}


def K_beta_by_basis(geom=1.0, area_cm2=APERTURE_CM2, radon_retention=1.0):
    """K (1/s per Bq/cm2) of the beta window for different meanings of '1 Bq/cm2'.

    geom: geometry/standoff factor relative to the contact anchor (0.8-1.0).
    radon_retention: fraction of Rn-222 progeny (Pb-214, Bi-214) retained in the deposit.
    """
    e = {n: v[0] for n, v in BETA_EFF_4PI.items()}
    ore = e["Th-234"] + e["Pa-234m"] + radon_retention * (e["Pb-214"] + e["Bi-214"]) + e["Bi-210"]
    conc = e["Th-234"] + e["Pa-234m"]
    a = geom * area_cm2
    r = AB100["resp_cps_per_Bq"]
    return {
        "Cl-36 equivalent (calibration source basis)": r["Cl-36"] * a,
        "Sr-90/Y-90 equivalent, per Bq of Sr-90": r["Sr-90+Y-90"] * a,
        "ore, per Bq of U-238 (chain in equilibrium)": ore * a,
        "ore, per Bq of gross alpha (8 alpha per U-238 decay)": ore * a / 8.0,
        "ore, per Bq of total chain activity (14 decays)": ore * a / 14.0,
        "aged concentrate, per Bq of U-238": conc * a,
        "aged concentrate, per Bq of gross alpha (U-238 + U-234 + U-235)": conc * a / 2.046,
    }
