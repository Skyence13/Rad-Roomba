# 02 Calibration and source checks

**Status.** No detector exists and no calibration has ever been measured. Everything in this file is a method, proposed from `analysis/radiometry/MODEL.md` (revision 3, normative for the processing code), `analysis/radiometry/report/detectability_report.md`, `interface/head_icd.md` section 7 and the verification register. **No acceptance band, check-source activity, check frequency or calibration value is established anywhere in the repository**; each is listed as "not yet defined" or as a site-RP decision. Evidence classes as in `docs/build/README.md`.

## 1. What must not be presented as usable

- Every coefficient shipped in the repository is **synthetic** and flagged `field_use_approved: false`: `analysis/radiometry/demo_calibration.json` (calibration id `DEMO-CAL-SYNTH-0001`; its own notice: "Not measured on any detector. For the simulator and software tests only; never use for a survey, a release decision or a performance claim") and `demo_site_profile_ore.json`, plus the copies in `ros2_ws/src/rr_core/rr_core/data/`. The ore example levels (investigation 0.30, comparison 0.40, detection goal below 0.20 Bq/cm2) are demonstration levels; the yellowcake profile is present, disabled and carries no numbers. The page and every export carry a red banner for synthetic data; if the banner is on, the numbers are not field numbers. In SURVEY binding mode the head attachment refuses a calibration that is not approved for field use (`CALIBRATION_NOT_APPROVED`, `ros2_ws/src/rr_core/rr_core/profiles.py`); unknown calibrations give `CALIBRATION_UNKNOWN` and, with strict setup checking, a different `setup_id` gives `CALIBRATION_SETUP_MISMATCH`.
- **Detection capability beyond what the study says must not be stated.** `detectability_report.md` (`calculated`; assumed response K = 24 s-1 per Bq/cm2, Cl-36-equivalent, u_rel(K) 15 %, alpha = beta = 0.05, 1 s dwell, uniform deposit over one 80 cm2 aperture, no detector data): a **single 1 s pass does not reach 0.20 Bq/cm2** with either estimator (D# 0.408 uncompensated in a uniform field, 0.510 compensated with a matched reference, at natural background of 0.1 uSv/h); and **alpha is not a scanning channel at 10 mm standoff** in that study (0.20 Bq/cm2 gives about 1.2 counts per second, below the three needed for 95 % detection with zero background; usable at best as a stationary confirmation channel with controlled standoff). A per-decision alpha of 0.05 gives about 224 false flags per trailer (4480 cells); a 5 % per-mission allowance needs 1.14e-5 per decision, which raises the single-pass D# to 0.902 Bq/cm2. If the site defines activity so that K is near 100, one pass reaches about 0.122 Bq/cm2 at 0.1 uSv/h; K depends by more than a factor of ten on what "1 Bq/cm2" means for ore. The measurement-based replacement of these assumptions is VT-015 to VT-018 and VT-044 (pending).

## 2. What the processing model needs from a calibration

Per lane i and class (alpha-like, beta-window), MODEL.md section 1:

| Quantity | Meaning | Notes |
|---|---|---|
| k | floor to reference photon count ratio (transfer coefficient): net rate r = F - kU - b | |
| b, u(b) | offset: floor rate not tracked by the reference | |
| cov(k,b) | covariance, enters u²(r) as 2U cov(k,b) | demo record carries it per lane |
| u(k) = sqrt(u_lane(k)² + u_common(k)²) | lane fit component and a component common to all lanes (spectral mismatch between the calibration field and the site field is a fixed bias within a site) | the common part is not averaged down across cells |
| K, u_rel(K), calibration source | response in s-1 per Bq/cm2 **with the source stated**: nuclide, emission basis (2 pi surface emission, per Bq of which nuclide, gross alpha, total chain), lateral extent, standoff | K defined for a **wide planar source extending at least three standoff distances beyond the aperture on every side** at the calibrated standoff; an aperture-size source delivers materially less at 10 mm (about 0.65 of the wide-source value for isotropic emission in the review's geometry calculation) and needs a documented geometry correction (MODEL.md section 5) |
| epsilon | fraction of floor surface signal reaching the reference (leakage), with the source used to measure it | E[r] = rho (1 - k eps); an emitter with a different epsilon is biased; reported as a validity limit, not folded into u(D), until epsilon is measured per class; with a matched reference epsilon must be known to about 1 % absolute for a 1 % bias (report section 7) |
| Validity envelope | reference-rate range with an upper cap, head temperature, standoff, `setup_id` (and speed, photon-field description in the demo record) | the cap: D# is bounded below by 2 kappa U u(k) / (K (1 - kappa² u_rel²(K))) at any dwell, so above the reference rate where this equals the detection goal a cell is reported "sensitivity insufficient, reference rate above qualified range" |
| U_null method and window | the reference rate used for thresholds; default running mean over at least 20 T_F centred on the dwell excluding the gates under test, falling back to the four-lane pooled rate | stored with every decision; it is not the same-gate N_U/T_U |

A new calibration revision is required whenever the setup changes: thresholds, anode trims, bias set-point, temperature coefficient, heater set-point and the firmware version are part of `setup_id`; a setup change invalidates the binding (`interface/head_icd_addendum_0.4.md`) and starts a new acquisition epoch (RQ-019). The 0.3 baseline also reopens calibration, compensation, seam and speed verification for a change to tile size, standoff, grille, absorber or discrimination settings (`docs/Rad_Roomba_Design.pdf` chapter 09, "Configuration control").

## 3. How each would be measured (proposed; from the study's section 8 and `head_icd.md` section 7)

| Quantity | Measurement | Set-up facts from the sources |
|---|---|---|
| K and u_rel(K), per lane and class | Traceable planar sources (Cl-36, Sr-90/Y-90, natural uranium) at the loaded 10 mm gap, a source **wider than** and one **equal to** the aperture, on representative floor finishes; counts and live time per channel at documented standoff; source ID, geometry, temperature, check date, uncertainty recorded; include the normal window, guard and extra protective hardware; coefficients determined on the robot or a calibration workstation; the moving survey configuration qualified separately | `head_icd.md` section 7 "Detector efficiency measurement"; VT-016 (source certificate basis, backscatter, self-absorption, comparison with an independent instrument under compatible geometry); VT-031 (efficiency at the intended 10 mm nominal geometry; bench data never receives field coverage credit) |
| Definition of "1 Bq/cm2" | site decision, not a measurement | DEC-012, DEC-015 |
| k, b, cov(k,b), u(k) | clean-floor F against U over the intended reference-rate range in **at least two photon spectra and several directions**, with held-out validation; compare gross and corrected results on held-out blank and seeded runs; vary angle, overlap, dose rate, temperature, gradients, absorber | report section 8; VT-017 |
| Reference tile and shield options | the same data with candidate reference tiles (0.25, 2, 5 mm) and shield options | report section 8 |
| epsilon | F and U with and without surface sources, per shield option, by beta energy | report section 6, 8 |
| Spatial response, seam loss | raster of small sources across the face, corners and seam at the working gap | report section 8; replaces the top-hat response of MODEL.md section 5 |
| K_alpha and its dependence on standoff and temperature | thin natural-uranium and Am-241 sources at 6 to 14 mm, at +20 and -20 C | report section 8; VT-044; the study's model gives about 9.6 % efficiency at 10 mm for thin natural uranium, 32 % lower at 12 mm, 22 % lower at -20 C (`calculated`, assumed) |
| Field non-uniformity sigma_delta, ambient dose-rate range | dose-rate or reference-rate map along representative empty trailers at the site | report section 8; decides whether compensation is needed |
| Dead time and gate timing | pulser rate sweep (see `docs/build/05_first_bench_tests.md` T4) | VT-037 |
| Standoff and gap band | loaded gap measured statically and dynamically (T10) | `gap_measurement_method.md`; RQ-018, RQ-047 |
| Interference (heater, motors) | T5 and T6 | VT-041, RQ-081 |

Calibration conditions that the validity envelope must record: standoff range, head temperature, reference-rate range, speed, `setup_id`, the floor finish and the photon field of the calibration. Samples whose gap leaves the calibrated interval are flagged and the host withholds that coverage (RQ-047).

Quantitative corrections that do not exist yet: self-absorption and radon loss for ore dust (30 % radon loss lowers the per-U-238 K for the aperture-size geometry from about 79 to about 68 in the study), backscatter, source-certificate basis. They are "not yet defined".

## 4. Daily source and response checks (method only)

Purpose: verify stability **between** calibrations. A passed response check alone does not update the calibration; only a site-controlled review issues a new calibration revision (`head_icd.md` section 7; RFQ 0.4 "Tethered laboratory use").

Method (from `head_icd.md` section 7, with the statistical details proposed):

1. Under the RP procedure, use the designated check fixture and source at a reproducible position; reference planes and separation as in the approved calibration method; the normal window and guard fitted. The source, activity, nuclide, fixture, position and check count time are **not yet defined**.
2. Acquire counts and live time by channel and lane for a fixed live time; also a blank. Use the same acquisition path as the survey (raw gates, setup unchanged: confirm `setup_id`).
3. Correct the source for decay to the reference date; compute the net rate per lane and channel.
4. Compare with the control limits for that serial and channel; record drift; withhold a failed lane from survey and affected calibration from use.
5. Record the result against the head serial, the calibration revision and the profile revision.

**Acceptance band.** `head_icd.md` calls it "allowable control limits"; RFQ 0.4 calls it "a site-established acceptance band" (`check_acceptance_reference` in `planning/detector_bench_runs.csv`). **No value exists.** Proposed way to establish it (not validated): at commissioning take several independent check measurements on the calibrated head, derive the mean and the repeatability for each lane and channel, make the band wide enough to be insensitive to counting statistics at the chosen check time and narrow enough to catch the drift that would change a decision (the sensitivity of D# to K, 1/K scaling, is in the study), and let the RP program approve the band and the check interval; separate bands for the alpha-like and beta-window classes. The count time should make the Poisson uncertainty of the check a small fraction of the band: with N counts the relative uncertainty is 1/sqrt(N).

**Other pre-use checks that belong with the source check:** lid-closed dark rate per lane (a rise indicates a light leak, a rise with temperature indicates bias or temperature-compensation drift); reference-channel health (section 5); bias current and bias voltage within the window (`BIAS_OUT_OF_RANGE`); lane flags; heater and temperatures; clock lock. A check source must be returned to its controlled storage; handling of the sources is under the site's program.

## 5. Background and reference-channel checks

| Check | Method (proposed) | What it detects |
|---|---|---|
| Clean-floor background in the survey location | blank measurements at the centre, ends and near walls in the facility, per lane (baseline sequence step 1 of "Practical sequence for the next build") | local photon field and its variation; sets D# context |
| F against kU + b on clean floor | per lane and class, per shift, over the observed reference-rate range | drift of k or b; a changed head, window or temperature |
| Reference rate U within the validity envelope | continuously, flagged per cell | cells above the qualified range are "sensitivity insufficient" |
| Reference live fraction and reject counts | DIAG and ACQ: `ref_reject_counts`, live ticks; a reference below 50 % live is `SATURATED` with null counts | overload, afterglow, interference |
| Leakage monitoring | step in F/U ratio with and without a surface source nearby (the leakage test of section 3) | epsilon changes (shield, window, standoff) |
| Four-lane consistency | compare lanes' k U + b against each other | one lane with a drifting reference or bias |
| Temperature dependence | record head temperature with every gate; compare dark rate and k at the operating temperature | cold-start behaviour; calibration outside the envelope |
| Dark threshold (lid closed) rate at the operating thresholds | per shift | bias or gain drift; light leak |

Reference lane reading null or flagged excludes that lane's gates from the cell sums; the floor area is not credited (MODEL.md section 1).

## 6. Records to keep

Per calibration revision: calibration id, head serial and descriptor id/digest, `setup_id`, firmware version, source certificates (nuclide, emission basis, activity, reference date, uncertainty, lateral extent), fixture and harness IDs, geometry and standoff, temperature, floor finish, photon field id, raw counts and live times per lane and channel (the original acquisition files, unmodified), coefficient fits with covariance, validity envelope, validation results on held-out data, the independent instrument comparison, reviewer and approval date. Use `planning/detector_bench_runs.csv` as the lane-level record layout for bench runs (test_type values include dark, clean photon field, known uniform source, spot traverse, seam traverse, repeated pass, thermal or heater/motor interference, source_response_check, efficiency_calibration, contact_bumper_function).

Per daily check: date, operator, head serial, calibration and profile revision, source ID and decay-corrected activity, fixture and position, counts and live time per lane/channel, blank, result against the band, disposition (accept, withhold lane, recalibrate), temperatures.

Per mission: the machine-readable manifest of the run (mission, head, calibration, profile, software and geometry IDs; clock synchronisation; raw interval counts and live time; pose and uncertainty; applied algorithms; digests), including the method and window used for U_null and the decision rule (`per-lane-exact/any-lane/alpha-over-m`). Copy original data and identities forward when reprocessing, preserve the first report and show the reason for each superseding result (baseline "Configuration control and handover"). Laboratory data are bench records with no floor coverage, geolocation or Bq/cm2 release status.

## 7. What the site radiation-protection program must define

| Item | Why |
|---|---|
| What "1 Bq/cm2" means for each material (nuclide, emission basis, e.g. per Bq of U-238 or gross alpha) | K differs by more than a factor of ten with the definition |
| Release basis, averaging area, smallest patch, detection goal, investigation and comparison levels, alpha, beta, mission false-investigation allowance and recount rule | every threshold and every sensitivity claim |
| Photon-field envelope at the survey locations | validity envelope; whether 0.20 Bq/cm2 is attainable on site |
| Calibration sources, traceability, laboratory, interval and approval authority for a calibration revision | VT-016, VT-031 |
| Daily check source, fixture, count time, acceptance band and action on failure; check interval | section 4 |
| Retention periods, custody, disposition and who signs | baseline operator display table |
| Handling and storage of check and calibration sources, and the hot-spot follow-up (wipes, hand probe) | site procedures |
| Which survey method (search then count, step and count, continuous scan) is permitted for which purpose | DEC-038 |
| Standoff band and floor envelope inside which results are valid | RQ-018, RQ-047 |

## 8. Open items

| Item | ID | Status |
|---|---|---|
| All calibration coefficients, the validity envelope, epsilon, spatial response | VT-015, VT-016, VT-017, VT-018, VT-044; RSK-037 | pending; no measurement |
| Meaning of 1 Bq/cm2; patch size; photon-field envelope; alpha, beta, mission allowance | DEC-001, 002, 012, 015 | site inputs open |
| Check-source acceptance band, source, fixture, interval | not yet defined | site RP |
| Monte Carlo confirmation of the Poisson-exact method with fractional weights: the test is not clean (clean-cell false-alarm ratio up to 1.16 for m = 2 and 1.24 for m = 4 with weights 1 except one 0.1 gate per lane at low counts; `xfail` in `rr_core/test/test_cell_decision.py`) | IB-31 | Outstanding; reported to the radiometry owner |
| Photon-spectrum dependence of k: 0.4 to 19.0 % mismatch in the shield-attenuation model | `detectability_report.md` section 2.1 | needs measurement |
| Decay data in the study were transcribed from memory and not re-verified | `detectability_report.md` section 9 | UNVERIFIED |
| Dead time, Cov(F,U), pose error, standoff variation in motion, heater and motor interference are not in the study | `detectability_report.md` section 9 | not modelled |
| The reference tile leakage: shield option not selected | report section 6 | Open |
| Calibration of the alpha channel at standoff and temperature | VT-044, RSK-021 | pending |
