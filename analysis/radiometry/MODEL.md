# Count-processing model (normative for `ros2_ws` processing code and for `analysis/radiometry`)

Owner: integration lead. Status: design definition, `calculated`; no coefficient here is measured. Carries forward design 0.3 §5 "Photon compensation and uncertainty" and makes the decision quantities explicit. Symbols follow the 0.3 text; the transfer coefficient is *k* and coverage quantiles are κ (κ_α = z_{1−α}, κ_β = z_{1−β}).

**Revision 5 (2026-11-27).** After the analyst's second check (`MODEL_REVIEW_rev4.md`, `report/model_rev4_unull.md`) and the independent data-path review (`docs/reviews/REVIEW_head_data_to_map.md`): the null reference is specified by reference counts with a predictive threshold instead of a 200·T_F window; a cell's recorded decision is evaluated once, on complete data (earlier values are provisional); the search-stage ratemeter and stationary recounts are defined; the beta-window class is defined by the time-over-threshold cut in both chains; footprint weights, cell status, alarms and the records needed to reproduce a cell are specified (§6, §8). Validation limits are listed in §9.

**Revision 4 (2026-11-27, superseded in §3 U_null only).** Replaces the two revision-3 rules after the analyst's check (`MODEL_REVIEW_rev3.md`, `report/model_rev3_checks.md`): the Poisson form with weighted sums exceeded α with the exact method (up to 1.24 in the beta window and 4.4 in the alpha channel) and the any-lane rule cost a factor 1.3–2.4 in detection limit. Every decision statistic is now one fixed linear combination of Poisson gate counts with its threshold taken from the exact distribution (§3, §6); the null-reference window is lengthened; the N+1 rule is replaced. All supporting numbers are calculated or simulated with synthetic coefficients.

**Revision 3 (2026-11-27, superseded).** Closes the two questions raised by the processing software (integration backlog IB-31): the variance of footprint-weighted sums (§6, new paragraph "Weighted sums") and the decision rule for a cell fed by several lanes (§6, new paragraph "Cell decision with several lanes"). No formula of revision 2 changes.

**Revision 2 (2026-11-25).** Incorporates the independent review in `MODEL_REVIEW.md` (items R1–R9): where the null variance is evaluated, Poisson thresholds at small α, the meaning of the mission allowance, the patch statistic, the calibration-source definition of K, the split of u(k), and reference leakage ε. Revision 1 is in git history.

## 1. Quantities per lane *i* and class *w* (alpha-like, beta-window)

For a set *S* of gates (one gate, a dwell over a map cell, or a stationary recount) on **one attachment and one setup**:

- N_F = Σ N_f, T_F = Σ t_f — floor gross counts and floor live time (s)
- N_U = Σ N_u, T_U = Σ t_u — reference gross counts and reference live time (s)
- F = N_F / T_F, U = N_U / T_U (s⁻¹)
- Calibration record, per lane and class: k, b with u(b), cov(k,b); **u(k) split into a lane-specific fit component u_lane(k) and a component common to all lanes u_common(k)** (spectral mismatch between the calibration field and the site field is a fixed bias within a site and belongs in the common part); response K (s⁻¹ per Bq cm⁻²) with relative standard uncertainty u_rel(K) **and the calibration source stated (nuclide, emission basis, lateral extent, standoff)**; leakage fraction ε of floor surface signal reaching the reference, with the source used to measure it; validity envelope (reference-rate range with an upper cap, temperature, standoff, setup_id). **Revision 5:** the record is bound to one head by serial number, electronics revision, firmware version and `setup_id`, and names the per-board calibration identifier in force (`cal_id`); it carries the lane-to-lane reference-rate ratios with their validity, the time-over-threshold cut, and the qualified range of the rejected-event fraction. A calibration is never applied to data from another serial or `setup_id`; each attachment is processed with the calibration bound to it, and data without a matching calibration are archived and reported `no result — no calibration for this head and setup`. u²(k) = u_lane²(k) + u_common²(k) wherever a single u(k) appears below.
- U_null: the reference rate used for the null hypothesis (see §3). It is **not** the same-gate N_U/T_U.

Gates with a null channel, a lane flag, sync bound above the limit, or no qualified pose are excluded from *S* before summation and their floor area is not credited.

## 2. Net rate and its uncertainty (compensated estimator)

    r      = F − k·U − b
    u²(r)  = N_F/T_F² + k²·N_U/T_U²                  (counting)
           + U²·u²(k) + u²(b) + 2·U·cov(k,b)         (transfer calibration)
    D      = r / K
    u²(D)  = u²(r)/K² + D²·u_rel²(K)

Report `u_stat(D)` (counting terms only) and `u_total(D)` separately; calibration terms are common to all cells of a lane and must not be averaged down across cells. Signed values are kept; nothing is clipped at zero before averaging. If synchronized raw data show Cov(F,U) ≠ 0, add −2k·Cov(F,U); the default is zero and the assumption is recorded in the output manifest.

Low counts: the reported counting variance of a weighted sum is max(Σw²N, Σw²λ₀), with λ₀ the null means at U_null (not N+1); a zero-count result is never presented as certainty. The alpha and beta estimates of a lane share N_U and are therefore correlated; they are never summed without that covariance.

Leakage: with a fraction ε of the surface signal reaching the reference, E[r] = ρ·(1 − k·ε). K determined with compensation enabled already contains (1 − k·ε_cal) for the calibration source; an emitter with a different ε is biased by (1 − kε)/(1 − kε_cal) − 1. The bias is reported as a validity limit, not folded into u(D), until ε is measured per class.

## 3. Decision threshold and detection limit (ISO 11929 form)

The closed forms below define the quantities and remain the planning approximations (large counts, one lane, unit weights). From revision 4 the stored r*, D* and D# of a decision come from the exact evaluation described under "Thresholds".

Standard uncertainty of r when the true net rate is zero (expected floor rate k·U + b):

    ũ²(0)  = (k·U₀ + b)/T_F + k²·U₀/T_U + U₀²·u²(k) + u²(b) + 2·U₀·cov(k,b)        U₀ ≡ U_null
    ũ²(ρ)  = ũ²(0) + ρ/T_F                           (true net rate ρ)

    r*  = κ_α · ũ(0)                                  decision threshold
    r#  solves  r# = r* + κ_β · ũ(r#)
        with κ_α = κ_β = κ:   r# = 2·r* + κ²/T_F
    D*  = r*/K
    D#  = (2·r* + κ²/T_F) / ( K · (1 − κ²·u_rel²(K)) )     defined only while κ_β·u_rel(K) < 1

For κ_α ≠ κ_β, D# is the positive root of (1 − κ_β²u_rel²)·y² − (2y* + κ_β²/(K·T_F))·y + (y*² − κ_β²ũ²(0)/K²) = 0 with y* = D*.

**Where U_null comes from (R1, revision 5).** U_null is estimated from reference counts that are not terms of the statistic under test: by default the lane's own reference gates nearest in time to the dwell, from the complete attachment record, excluding every gate under test of the cell. The window is two adjacent sub-windows (one before and one after the dwell where both exist, otherwise both on the available side), each holding at least N_min reference counts: N_min = 30 for α ≥ 10⁻², 75 for α ≥ 10⁻³, 125 for α ≥ 10⁻⁴, 200 for α ≥ 10⁻⁶ (below that, computed). U_null is the larger of the two sub-window means, and the threshold uses that sub-window's count and live time (below). Where the lane's sub-windows would span more than 2 m of travel or cross a head reset, the four-lane pooled reference over the same rule is used, scaled by the lane's reference-rate ratio estimated over the attachment record, with the effective count 1/(1/N_pool + 1/n_lane + 1/n_all). A reference that includes a gate under test is never used. Stored with every decision: source (lane / pooled), sub-window counts, live times and spans (s, m), the gradient estimate (relative difference of the sub-window means per metre of separation), the lane ratio and its count where pooled. Where both sub-windows lie on one side and the gradient estimate projects a bias of more than 2 % at the dwell, the cell is reported `sensitivity insufficient — reference gradient`. Where fewer than N_min counts exist in the attachment record for every source, it is reported `no decision — null reference unavailable`.

**Threshold with a finite reference.** The threshold is that of the predictive null distribution: P₀(S > t*) averaged over U ~ Gamma(N + ½, scale 1/T) (N, T the count and live time of the U_null sub-window), evaluated with 12 posterior nodes (the average of the characteristic functions in the Gil-Pelaez evaluator). Method string `linear-exact/<evaluator>/predictive-U(N=…)`.

**When a decision is evaluated.** The recorded decision of a cell (D, D*, D#, flag, reason code) is evaluated once, after the cell's U_null sub-windows are complete or at the end of the attachment record, whichever comes first, from all qualifying data and independently of the order in which the gates arrived. Values computed earlier are provisional, are labelled `provisional` wherever they are shown or exported, and may drive the live display and the search stage only. The record keeps, per cell, the time and value of the first provisional alarm and of the recorded decision. A provisional alarm not confirmed by the recorded decision is recorded as `provisional alarm not confirmed`. A recorded alarm without a provisional one is recorded as `alarm found at final evaluation` and enters the residual list for revisit.

**Search stage.** The scan-stage ratemeter that triggers recounts uses the statistic of §6 over the trailing dwell with a past-only U_null under the same rule (two past sub-windows, larger mean, predictive threshold) at α_scan. Its alarms are provisional.

**Recounts.** A stationary recount (m = 1) takes U_null from the other three lanes' reference counts during the recount, scaled by their reference-rate ratios to the tested lane (estimated over the attachment record, uncertainty in the effective count), with the predictive threshold. If a lane ratio is not qualified, the lane's own reference is counted for at least N_min/U before or after the recount, at the same position.

**Thresholds (R2, revision 4).** Every decision statistic is a fixed linear combination of independent Poisson gate counts plus a Gaussian calibration term, S = Σⱼ aⱼNⱼ + Z (§6). The threshold t* is the value with P₀(S > t*) = α under the null means computed from U_null, evaluated from the exact distribution: by numerical inversion of the characteristic function (Gil-Pelaez), or by lattice convolution when all aⱼ are integer multiples of one span (always when Z = 0). Saddlepoint and normal approximations may seed the root search but are not used for the decision. The detection limit is the activity D at which P(S > t* | D) = 1 − β, with the signal added to the floor means and u_rel(K) as a Gaussian term proportional to the signal. The stored method is `linear-exact/gil-pelaez` or `linear-exact/lattice`; a numerical check (the tail at t* recomputed with half the quadrature step must agree to 10⁻³ relative) is stored, and a cell failing it is reported `no decision — evaluator check failed`.

**Floor from u(k) (R7).** D# ≥ 2κ·U·u(k) / (K·(1 − κ²u_rel²(K))) regardless of dwell. The calibration validity envelope caps U at the value where this floor equals the profile's detection goal; above it the cell is reported `sensitivity insufficient — reference rate above qualified range`.

Defaults for the demonstration profile: α = β = 0.05 per decision (κ = 1.645). The site profile owns α, β and the per-mission allowance.

**Mission allowance (R3).** The allowance P_m is the probability of **at least one** false investigation in a survey with a clean floor. The number of decisions n is the number of fixed, non-overlapping decision cells of the profile's averaging area in the surveyed floor (sliding windows and display cells are not decisions). Per-decision α₁ = 1 − (1 − P_m)^(1/n) (Šidák; conservative under the positive correlation caused by common calibration terms, which also makes false flags arrive in clusters). A two-stage rule is the default operating rule: a scan-stage flag at α_scan triggers a stationary recount of stated duration evaluated at α_recount, with n·α_scan expected recounts per clean survey and P_m controlled by the recount stage; α_scan, α_recount, recount duration and the β of each stage are profile fields and are stored with the result.

A cell or patch is reported as "sensitivity sufficient" only when D# ≤ the profile's detection goal (ore example: 0.20 Bq/cm²) **and** the calibration validity envelope holds. A standard uncertainty is never presented as a detection limit.

## 4. Uncompensated estimator (for comparison only)

Background B₀ = N₀/T₀ measured once at a reference position; the photon field at the measurement position differs by an unknown relative amount with standard deviation σ_δ (field non-uniformity along the trailer, neighbouring loads, time variation):

    r_unc      = F − B₀
    ũ_unc²(0)  = B/T_F + B₀/T₀ + σ_δ²·B²              with B the local true background rate
    ũ_unc²(ρ)  = ũ_unc²(0) + ρ/T_F

The same r*, r#, D# expressions apply. The comparison of interest is D#(compensated) against D#(uncompensated) **at equal dwell T_F**, as a function of background rate, σ_δ, k, u(k)/k and T_U/T_F. B is unobservable; a decision rule can only use B₀ in its place, and a Gaussian σ_δ does not describe structured fields (a step near the door defeats the uncompensated rule even with σ_δ declared at its rms value). Both are limits of this comparator, not of the compensated estimator.

## 5. Moving patch

K is defined for a uniform planar source **extending at least three standoff distances beyond the aperture on every side** (a "wide" source) at the calibrated standoff, per unit activity density of the stated calibration nuclide and emission basis; an aperture-size source delivers materially less at 10 mm standoff (about 0.65 of the wide-source value for isotropic emission in the review's geometry calculation) and needs a documented geometry correction. A_a is the aperture area, nominally 80 cm². For a patch of activity density D_p the expected net counts in a gate are

    E[N_net] = K · D_p · ∫_gate  w(t) dt ,   w(t) = (response-weighted overlap of patch and aperture at time t) / (response-weighted aperture area)

with a uniform (top-hat) response used until a measured spatial response exists; the top-hat ignores an edge blur of about one standoff. Dwell for an interior floor point on a straight pass is L/v (L = 0.100 m along travel).

**Patch and cell statistic (R5).** A survey does not know where a patch is, so decisions are made on the profile's fixed decision cells (§3). For a cell, each lane-gate contributes with weight equal to the fraction of its eroded aperture footprint inside the cell, applied to counts and live time together (§6); lane-gates whose weight is below 0.10 are excluded from the decision statistic (they add background and almost no signal) but stay in the archive. Detectability for a hypothetical patch of given size and position is evaluated with that same statistic on the cell(s) containing it, and is quoted for the least favourable alignment (patch straddling a cell boundary and a lane seam) as well as the most favourable.

## 6. Map cell estimate

For cell *c*, lane *i*: sum N and t over gates weighted by the fraction of the gate's eroded aperture footprint lying in *c* (weights applied to **live time and counts together**, so rates are footprint averages, never divided by pixel area again). Lanes are combined by inverse-variance weighting of D with the common calibration terms added after combination. Each cell stores: D, u_stat, u_total, D*, D#, T_F, coverage fraction, contributing gate keys (attachment, sequence, lane), reason codes.

**Weighted sums.** Footprint weights enter the decision statistic as coefficients of the individual gate counts: a floor count of lane i in gate j has coefficient wⱼ/T_F,ᵢ and its variance contribution wⱼ²λⱼ. The revision-3 treatment (Poisson form evaluated with weighted sums) is withdrawn: with `poisson-exact` it exceeds α by up to 1.24 in the beta window and 4.4 in the alpha channel (calculated, synthetic coefficients, `analysis/radiometry/MODEL_REVIEW_rev3.md`), and where it is conservative it costs 1.1–1.7 in r#. The moment-matched scaled-Poisson form is not used either (it exceeds α by up to 1.33). The export manifest records `weighted_sum_variance: exact_coefficients`. Rates remain footprint averages: activity confined to a cell is reported, and detected, as its footprint average, which for a cell traversed by partial footprints is Σw²t/Σwt of the cell's activity (0.44–0.74 for the 0.4 geometry: lane centred 0.74, cell centred on a seam 0.44).

**Cell decision with several lanes.** For the m contributing lanes (decision weight ≥ 0.10) the cell statistic is S = Σᵢ cᵢ rᵢ/Kᵢ, with cᵢ proportional to the inverse null variance of Dᵢ (exact coefficients, evaluated at U_null before the counts under test are used) and Σcᵢ = 1; the common calibration terms enter Z fully correlated across lanes: Var(Z) = Σcᵢ²σ²_lane,ᵢ/Kᵢ² + (Σcᵢ U_null,ᵢ u_common,ᵢ(k)/Kᵢ)². The cell is flagged when S exceeds its threshold at 0.8α **or** any lane's own statistic (the same construction with m = 1) exceeds its threshold at 0.2α/m; by the union bound the cell false-alarm probability is at most α. The quoted cell D# is that of the combined test for activity covering every contributing footprint. A patch claim uses the detection limit of the same rule with the patch's footprint fractions in the alternative, at the least favourable alignment (straddling a lane seam and a cell boundary); maxᵢ D#ᵢ of the lanes is not a patch limit. The reported D, u_stat and u_total are the same combination (estimate), with the common terms added after combination. Stored per cell: m, cᵢ, U_null and its window per lane, t* and the evaluator of the combined test, the per-lane thresholds, the α split (0.8/0.2), which test(s) flagged, and the rule string `linear-exact/combined+per-lane/0.8-0.2`. A stationary recount is the same rule with m = 1.

U_null is evaluated per lane under §3; the combined statistic's null distribution uses each lane's predictive U_null (the posterior nodes of the lanes are combined as independent). The stored per-lane fields of §3 are part of the cell record.

**Footprint weights (normative, revision 5).** The footprint of a lane-gate is the lane aperture (nominally 80 mm across travel × 100 mm along travel) eroded on every side by the 2σ position uncertainty credited for that gate, swept between the poses at gate start and gate end. Its weight in a cell is the fraction of that swept, eroded area lying inside the cell, rounded to the nearest 0.05; weights below 0.10 are excluded from the decision statistic (§5). The software states the footprint model it implements in the export manifest (`footprint_model`), and a cell record lists its member gates with their weights.

**Cell status and alarms (revision 5).** An alarm is never suppressed by coverage or by a display rule: a cell whose recorded decision flags is reported `ALARM` whatever its coverage, and `ALARM` takes precedence over every other status. `ACCEPTABLE` requires all of: no flag; coverage fraction at or above the profile minimum; D# ≤ the detection goal; calibration validity envelope satisfied (reference rate, temperature, standoff, speed, setup); no member gate excluded for a fault. Otherwise the status is one of `INCOMPLETE COVERAGE`, `SENSITIVITY INSUFFICIENT` (with its reason), `NO DECISION` (with its reason) — each still carrying the flag state. A gate whose floor chain is saturated by rate (low live fraction without forced clears, as reported by the head's per-gate statistics) raises `ALARM — rate above counting range` for the cells it covers; saturation with forced clears is a detector fault and removes the gate. A detected cell is never shown in the colour of an acceptable one.

**Beta-window class (revision 5).** The beta-window class is "pulses between the lower and upper level that are not classified alpha-like by time over threshold", with the same cut applied in the floor and the reference chain; K, k, b and ε are calibrated in that definition and are valid only for the same `setup_id` (thresholds, cut, upper levels). The per-gate count of rejected events (`alpha_short`, `alpha_ambig`) is not an input of §2; its fraction per class is a validity-envelope quantity, and a gate outside the calibrated range is flagged. The remaining spectral dependence is carried by u_common(k).

## 7. Demonstration coefficients

All coefficients shipped in this repository are synthetic, flagged `field_use_approved: false`, and exist to exercise the code path. Ore example levels: investigation 0.30, comparison 0.40, detection goal < 0.20 Bq/cm². The yellowcake profile is present but disabled and carries no numbers.

## 8. Records needed to reproduce a cell (revision 5)

A third party must be able to recompute D, D*, D#, the decision and the status of any cell from the mission archive and the calibration and profile files alone. The archive therefore holds: every head frame as received, with sequence numbers and the head's per-gate statistics; skipped sequence numbers recorded as missing gates (their floor area is not credited); the time-synchronisation records; the inputs of the pose estimate (odometry, inertial and range data as received, with their time stamps) and the pose used for each gate with its credited uncertainty; the head's identity, build identifier, setup blob and `cal_id`; the calibration and profile files by content hash; the software identity (version and source revision of every package, and this model's revision); and, per cell, the member gates with weights, the U_null fields of §3, the coefficients cᵢ, thresholds, evaluator and check values. Exported tables carry, in every file, the calibration identifier and a `synthetic — not for field use` marker whenever `field_use_approved` is false. To allow averaging over cells, the export gives per cell the counting variance and each calibration component (lane and common parts of k, b, K) separately, and states that D is a footprint average (§6).

## 9. Validation status (2026-11-27)

Calculated or simulated with synthetic coefficients; nothing measured. Validated numerically: the exact linear statistic and the Gil-Pelaez evaluator (tail error 5.7e-8 against exact references); the α split 0.8/0.2; N_min with the predictive threshold for the beta window with k = 1. Not yet validated: the alpha channel and k ≠ 1 under the predictive threshold; the two-sub-window rule end to end (bias only); lateral gradients across the head and time-varying fields; real lane-ratio stability; the pile-up dependence of the time-over-threshold cut; the footprint model against a measured spatial response; everything that needs detector data.
