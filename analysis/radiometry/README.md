# Radiometry: compensated versus uncompensated detectability

Study of the count-processing model in `MODEL.md` (normative, owned by the integration lead) for the Rad Roomba floor-survey head. **No detector exists. Every coefficient is an assumption with a range; nothing here is a measured property of the head.**

## Run

```sh
cd analysis/radiometry
./run_all.sh
```

`run_all.sh` runs the unit tests, regenerates every file under `results/`, the figures, the two demo JSON files and the report, and exits non-zero on any failure. It uses `python3` if numpy, scipy, matplotlib and pytest are importable; otherwise it creates `.venv` here and installs `requirements.txt` (PyPI access needed once). Override with `PYTHON=/path/to/python ./run_all.sh` or `RRRAD_VENV=/path/to/venv`. Tested with Python 3.13 and the pinned versions in `requirements.txt`. Run time is about six minutes on one core. Seeds are fixed in `scripts/common.py` (`SEED`), so results are reproducible for the same numpy version.

Individual steps:

```sh
.venv/bin/python -m pytest -q tests          # unit tests
.venv/bin/python scripts/s1_parameter_space.py   # assumption register, spectra, K, alpha model
.venv/bin/python scripts/s2_analytic.py          # analytic comparison (MODEL.md sections 3-4)
.venv/bin/python scripts/s3_montecarlo.py        # Monte Carlo and exact-Poisson validation, moving patch
.venv/bin/python scripts/s4_leakage.py           # reference-channel leakage
.venv/bin/python scripts/s5_demo_files.py        # demo_calibration.json, demo_site_profile_ore.json
.venv/bin/python scripts/s7_rev3_checks.py       # MODEL.md rev 3 section 6 checks, candidate rev 4 rule (report/model_rev3_checks.md)
.venv/bin/python scripts/s8_unull.py             # U_null window in counts, predictive threshold, gradients, recounts (report/model_rev4_unull.md)
.venv/bin/python scripts/s6_report.py            # report from template + results (fails on a missing value)
```

Run the steps in this order after deleting `results/summary.json`; each one adds its values to that file.

## Contents

| Path | Content |
|---|---|
| `MODEL.md` | Normative model definition (not edited by this study) |
| `MODEL_REVIEW.md` | Errors and ambiguities found in `MODEL.md`, with evidence |
| `MODEL_REVIEW_rev3.md` | Verdicts on MODEL.md revision 3 section 6 (weighted sums, multi-lane cell rule) and proposed revision-4 wording |
| `report/model_rev3_checks.md` | Numbers behind `MODEL_REVIEW_rev3.md` (generated from `model_rev3_checks.template.md`) |
| `report/detectability_report.md` | The report (generated; edit `detectability_report.template.md`) |
| `report/figures/` | PNG figures |
| `results/*.csv`, `results/*.json` | Machine-readable results; `parameter_space.json` is the assumption register, `summary.json` the scalars quoted in the report, `tables/` the report tables |
| `rrrad/model.py` | MODEL.md §2–§4: net rate, uncertainties, r\*, r#, D\*, D# (closed form and numerical), Šidák, break-even, floor, leakage |
| `rrrad/patch.py` | MODEL.md §5: overlap integral of a rectangular patch crossing rectangular apertures, gate by gate |
| `rrrad/exact.py` | Exact Poisson error probabilities of the decision rules |
| `rrrad/linstat.py` | Tail probabilities of Σ aⱼNⱼ + Gaussian: exact lattice FFT, Gil-Pelaez, saddlepoint; thresholds |
| `rrrad/unull.py` | U_null precision: achieved α for a finite window (plug-in, predictive, upper-bound thresholds), gradient bias |
| `scripts/probe_unull_windows.py` | Probe of the ros2_ws processing windows (not run by `run_all.sh`; writes `results/rev4_window_probe.csv`) |
| `MODEL_REVIEW_rev4.md` | U_null rule: verdict on revision 4 and proposed revision-5 wording |
| `rrrad/rev3.py` | Replica of the rev-3 processing rule (weighted sums, any lane at α/m), exact checks, combined statistic |
| `rrrad/mc.py` | Monte Carlo: point trials, whole-trailer surveys in structured fields, gate-level moving patch |
| `rrrad/fields.py` | Uranium-series photon lines, NIST attenuation data, AB-100 anchor values, K and alpha-efficiency models (all assumptions) |
| `tests/` | Unit tests including limiting cases |
| `demo_calibration.json`, `demo_site_profile_ore.json` | **Synthetic** inputs for the robot simulator, `field_use_approved: false` |

## Demo files

`demo_calibration.json` gives, per lane (0–3) and class (`beta_window`, `alpha_like`): `k`, `b_cps`, `u_k`, `u_b_cps`, `cov_kb_cps`, `K_cps_per_Bq_cm2`, `u_rel_K`, plus `u_k_components` (fit part and common spectral part) and one `validity_envelope`. The transfer coefficients come from a simulated clean-floor fit so that the covariance is consistent. `demo_site_profile_ore.json` carries the ore example levels (0.30 investigation, 0.40 comparison, detection goal 0.20 Bq/cm²), α, β and the per-mission allowance with the Šidák rule; the yellowcake profile is present, disabled and empty. Neither file may be used for a survey.

## Conventions

- Rates in s⁻¹, times in s, activity density in Bq/cm², dose rate in µSv/h, lengths in m inside `rrrad.patch`.
- `B_gamma` is the floor photon rate k·U; the reference rate is U = B_gamma/k.
- `mode` in `rrrad.mc`/`rrrad.exact` selects where ũ(0) is evaluated: `plug_in` (same gates), `true` (true or independently smoothed U), `pooled` (null estimate from both streams). See `MODEL_REVIEW.md` R1.
