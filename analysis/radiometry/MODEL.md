# Count-processing model (normative for `ros2_ws` processing code and for `analysis/radiometry`)

Owner: integration lead. Status: design definition, `calculated`; no coefficient here is measured. Carries forward design 0.3 §5 "Photon compensation and uncertainty" and makes the decision quantities explicit. Symbols follow the 0.3 text; the transfer coefficient is *k* and coverage quantiles are κ (κ_α = z_{1−α}, κ_β = z_{1−β}).

**Revision 4 (2026-11-27).** Replaces the two revision-3 rules after the analyst's check (`MODEL_REVIEW_rev3.md`, `report/model_rev3_checks.md`): the Poisson form with weighted sums exceeded α with the exact method (up to 1.24 in the beta window and 4.4 in the alpha channel) and the any-lane rule cost a factor 1.3–2.4 in detection limit. Every decision statistic is now one fixed linear combination of Poisson gate counts with its threshold taken from the exact distribution (§3, §6); the null-reference window is lengthened; the N+1 rule is replaced. All supporting numbers are calculated or simulated with synthetic coefficients.

**Revision 3 (2026-11-27, superseded).** Closes the two questions raised by the processing software (integration backlog IB-31): the variance of footprint-weighted sums (§6, new paragraph "Weighted sums") and the decision rule for a cell fed by several lanes (§6, new paragraph "Cell decision with several lanes"). No formula of revision 2 changes.

**Revision 2 (2026-11-25).** Incorporates the independent review in `MODEL_REVIEW.md` (items R1–R9): where the null variance is evaluated, Poisson thresholds at small α, the meaning of the mission allowance, the patch statistic, the calibration-source definition of K, the split of u(k), and reference leakage ε. Revision 1 is in git history.

## 1. Quantities per lane *i* and class *w* (alpha-like, beta-window)

For a set *S* of gates (one gate, a dwell over a map cell, or a stationary recount) on **one attachment and one setup**:

- N_F = Σ N_f, T_F = Σ t_f — floor gross counts and floor live time (s)
- N_U = Σ N_u, T_U = Σ t_u — reference gross counts and reference live time (s)
- F = N_F / T_F, U = N_U / T_U (s⁻¹)
- Calibration record, per lane and class: k, b with u(b), cov(k,b); **u(k) split into a lane-specific fit component u_lane(k) and a component common to all lanes u_common(k)** (spectral mismatch between the calibration field and the site field is a fixed bias within a site and belongs in the common part); response K (s⁻¹ per Bq cm⁻²) with relative standard uncertainty u_rel(K) **and the calibration source stated (nuclide, emission basis, lateral extent, standoff)**; leakage fraction ε of floor surface signal reaching the reference, with the source used to measure it; validity envelope (reference-rate range with an upper cap, temperature, standoff, setup_id). u²(k) = u_lane²(k) + u_common²(k) wherever a single u(k) appears below.
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

**Where U_null comes from (R1).** Evaluating ũ²(0) at the same-gate N_U/T_U couples the threshold to the fluctuation being tested and inflates false alarms (about 2.4× at α = 0.05 and three orders of magnitude at mission-level α for 1 s dwell at 0.1 µSv/h in the review's exact calculation). U_null is therefore a reference rate that is statistically independent of the gates under test or much better determined than they are: by default U_null is the mean reference rate of the lane over a window of at least 200·T_F centred on the dwell **excluding the gates under test** (20·T_F is sufficient only for per-decision α ≥ 0.01). Where the lane window is shorter, the four-lane pooled reference rate over a window of the same length, also excluding the gates under test, is used. A reference that includes the gates under test (for example the four-lane pool over the same gates) is never used for U_null; where no qualifying window exists the cell is reported `no decision — null reference unavailable`. The method and the window length (s, and reference counts) are stored with every decision. **Open (revision 4):** the 200·T_F figure was established for scan dwells; the requirement should be restated in reference counts and checked for stationary recounts, where the window has to come from reference data taken before and after the count; a long window also averages over field gradients, which biases U_null (a reason to prefer the four-lane pooled window).

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

## 7. Demonstration coefficients

All coefficients shipped in this repository are synthetic, flagged `field_use_approved: false`, and exist to exercise the code path. Ore example levels: investigation 0.30, comparison 0.40, detection goal < 0.20 Bq/cm². The yellowcake profile is present but disabled and carries no numbers.
