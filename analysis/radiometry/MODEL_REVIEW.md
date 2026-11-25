# Review of `MODEL.md` by the radiometry analyst

Scope: `analysis/radiometry/MODEL.md` as read on 2026-11-25. `MODEL.md` was not edited. Evidence for each item is in `report/detectability_report.md` and `results/`; every number comes from assumed, not measured, coefficients.

## Verified, no change needed

- §2: the variance terms and signs of u²(r) and u²(D), including the +2·U·cov(k,b) term and the optional −2k·Cov(F,U) term. The design-text worked example (F = 8, U = 32, k = 0.25, K = 8: 0.28 Bq/cm² at 2 s, 0.088 at 20 s) is reproduced (`tests/test_model.py`).
- §3: the closed form D# = (2r\* + κ²/T_F)/(K(1 − κ²u_rel²(K))) follows from the implicit equation; checked algebraically and against a numerical solve to 1e-9.
- Limiting cases: U → 0 with u²(b) = b/T gives the classical paired-blank result 2.71 + 4.65·√(bT) counts; k = 1, T_U = T_F gives variance 2B/T; u(k) → 0 and T_U → ∞ give the known-background limit.
- With true (or independently smoothed) reference rates, Monte Carlo reproduces α and β for both estimators, including the calibration terms, to within the integer-count effects described below (report §5.1).

## Findings

### R1. §3 does not say at which U the null variance ũ²(0) is evaluated (substantive)

ũ²(0) is written with U. If software evaluates it at N_U/T_U of the same gate set, a low reference count lowers the threshold and raises r together. Achieved ÷ nominal false-alarm probability for a matched reference, exact Poisson sums (`results/exact_mission_alpha.csv`, report §5.2):

| Case | α = 0.05 | α = 1.14e-5 (Šidák, n = 4480) |
|---|---|---|
| 0.1 µSv/h, 1 s | about 2.4 | about 1900 |
| 1 µSv/h, 1 s | about 1.4 | about 41 |
| 3 µSv/h, 10 s | about 1.06 | about 2.3 |

First-order explanation: the effective quantile is κ/√((1 + (1 + κ/√(2B))²)/2) for k = 1. Proposed text: evaluate ũ²(0) at a reference rate that is statistically independent of the gates under test or much better determined than they are (a running mean over a window much longer than T_F, or the pooled lanes), and record which was used. A pooled null estimate from N_F and N_U holds α but loses power at small α and is not recommended.

### R2. Normal quantiles are not valid at the mission-level α for 1 s counts (substantive)

Even with ũ²(0) at the true U, the achieved false-alarm probability at α = 1.14e-5 is up to 4.9 times nominal for the compensated rule and up to 31 times for the uncompensated rule at 0.1 µSv/h and 1 s, because the Poisson tail is heavier than the normal tail at 4 to 40 counts. With a threshold recalibrated to hold α, the exact r# exceeds the §3 formula by up to 9 % (compensated) and 19 % (uncompensated). The compensated rule (a difference of two similar counts, nearly symmetric) is within about 30 % of nominal above roughly 30 counts per cell; the uncompensated rule is still 1.6 times nominal at 1000 counts. Proposed text: at mission-level α, thresholds are taken from the Poisson distribution or from a validated simulation unless the normal approximation has been shown adequate for the expected counts, and the stored result names the method.

### R3. Šidák and the meaning of the per-mission allowance (ambiguity)

- "Allowance" could be a probability of at least one false investigation or an expected number; Šidák implies the first. The profile should say which.
- "Number of independent decision areas" is undefined when cells overlap, when a sliding window is used, or when a recount stage follows.
- The calibration terms are common to all cells of a lane and a survey, so decisions are positively correlated. Šidák then remains conservative for P(≥1) but false flags arrive in clusters; the simulated 95th percentile of the flag count is well above its mean (report §5.3).
- A scan-plus-recount rule needs α₁, α₂ and the β split stated; report §4.4 gives an example.

### R4. §4 uses the unobservable local background B (ambiguity)

ũ_unc²(0) = B/T_F + B₀/T₀ + σ_δ²B² is written with "B the local true background rate". A decision rule can only use B₀. This study plugs B₀ in for B. Separately, a Gaussian σ_δ does not describe structured fields: with a +50 % step near the door and σ_δ declared at its rms value, the uncompensated rule still gives P(≥1 false flag) of 0.95 at the mission-level α (report §5.3). This strengthens the case for the comparison but should be stated as a limit of §4.

### R5. §5 patch rule: "sum over the gates and lanes whose apertures overlap it" (substantive ambiguity)

- Taken literally, any overlap counts. A 100 cm² square centred on a lane overlaps both neighbours by 2.5 mm, tripling the summed background for 6 % more signal: patch limit 0.96 instead of 0.61 Bq/cm² in the nominal case (report §5.4). A minimum-overlap criterion or weights proportional to w are needed.
- The rule presupposes a known patch position. For a survey the statistic has to be defined on fixed cells or a sliding window, with its own multiplicity; the grid alignment then changes the detection probability (report §5.4).

### R6. §5 definition of K: extent of the calibration source (ambiguity)

"A uniform source covering the whole aperture" does not fix the source size. At 10 mm standoff an aperture-size source delivers about 0.65 of its 2π emission to the aperture for isotropic emission without absorption, a wide source 1.0 (`rrrad.fields.rect_geometry_factor`). K differs accordingly, by up to about 35 %. The definition should state the source extent, and the top-hat w(t) should be flagged as ignoring a blur of about one standoff at the aperture edges.

### R7. u(k) as a random term (ambiguity)

A spectral mismatch between the calibration field and the site field is a fixed bias within a site, common to every cell and lane. Including it in U²u²(k) gives the right ensemble α but for one site all cells shift together. Consequences that §2–§3 could state: (i) the term sets a floor D# ≥ 2κ·U·u(k)/(K(1 − κ²u_rel²)) that no dwell removes; (ii) the validity envelope should cap U at the value where that floor equals the detection goal; (iii) the calibration record needs u(k) split into a lane-specific fit part and a part common to all lanes, otherwise §6 ("common calibration terms added after combination") cannot be applied. `demo_calibration.json` carries such a split (`u_k_components`).

### R8. Reference-channel leakage is absent from the model (omission)

If a fraction ε of the floor surface signal reaches the reference, E[r] = ρ(1 − kε). K calibrated with compensation enabled absorbs (1 − k·ε_cal); emitters with a different ε are biased by (1 − kε)/(1 − kε_cal) − 1 (report §6). The calibration record should carry ε per class with the source used.

### R9. Minor

- §3: for α ≠ β the condition for D# to exist is k_{1−β}·u_rel(K) < 1; the general closed form is the positive root of (1 − κ_β²u_rel²)·y² − (2y\* + κ_β²/(K·T_F))·y + (y\*² − κ_β²ũ²(0)/K²) = 0.
- §3 uses k for both the transfer coefficient and the quantile k_{1−α}, and κ appears without definition.
- §1–§2: the same N_U enters the alpha and the beta estimate of a lane, so the two classes are correlated; relevant only if they are ever combined.
- §2: at very low counts the observed-count variance N_F/T_F² + k²N_U/T_U² is zero when both counts are zero; an alpha-channel u_stat of zero should not be read as certainty.
