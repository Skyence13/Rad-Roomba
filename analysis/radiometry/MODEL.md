# Count-processing model (normative for `ros2_ws` processing code and for `analysis/radiometry`)

Owner: integration lead. Status: design definition, `calculated`; no coefficient here is measured. Carries forward design 0.3 §5 "Photon compensation and uncertainty" and makes the decision quantities explicit. Symbols follow the 0.3 text.

## 1. Quantities per lane *i* and class *w* (alpha-like, beta-window)

For a set *S* of gates (one gate, a dwell over a map cell, or a stationary recount) on **one attachment and one setup**:

- N_F = Σ N_f, T_F = Σ t_f — floor gross counts and floor live time (s)
- N_U = Σ N_u, T_U = Σ t_u — reference gross counts and reference live time (s)
- F = N_F / T_F, U = N_U / T_U (s⁻¹)
- Calibration record: k, b with u(k), u(b), cov(k,b); response K (s⁻¹ per Bq cm⁻²) with relative standard uncertainty u_rel(K); validity envelope (reference-rate range, temperature, standoff, setup_id).

Gates with a null channel, a lane flag, sync bound above the limit, or no qualified pose are excluded from *S* before summation and their floor area is not credited.

## 2. Net rate and its uncertainty (compensated estimator)

    r      = F − k·U − b
    u²(r)  = N_F/T_F² + k²·N_U/T_U²                  (counting)
           + U²·u²(k) + u²(b) + 2·U·cov(k,b)         (transfer calibration)
    D      = r / K
    u²(D)  = u²(r)/K² + D²·u_rel²(K)

Report `u_stat(D)` (counting terms only) and `u_total(D)` separately; calibration terms are common to all cells of a lane and must not be averaged down across cells. Signed values are kept; nothing is clipped at zero before averaging. If synchronized raw data show Cov(F,U) ≠ 0, add −2k·Cov(F,U); the default is zero and the assumption is recorded in the output manifest.

## 3. Decision threshold and detection limit (ISO 11929 form)

Standard uncertainty of r when the true net rate is zero (expected floor rate k·U + b):

    ũ²(0)  = (k·U + b)/T_F + k²·U/T_U + U²·u²(k) + u²(b) + 2·U·cov(k,b)
    ũ²(ρ)  = ũ²(0) + ρ/T_F                           (true net rate ρ)

    r*  = k_{1−α} · ũ(0)                              decision threshold
    r#  solves  r# = r* + k_{1−β} · ũ(r#)
        with k_{1−α} = k_{1−β} = κ:   r# = 2·r* + κ²/T_F
    D*  = r*/K
    D#  = (2·r* + κ²/T_F) / ( K · (1 − κ²·u_rel²(K)) )     defined only while κ·u_rel(K) < 1

Defaults for the demonstration profile: α = β = 0.05 per decision (κ = 1.645). The site profile owns α, β and the per-mission false-investigation allowance; the per-decision α is derived from the allowance and the number of independent decision areas (Šidák) and is stored with the result.

A cell or patch is reported as "sensitivity sufficient" only when D# ≤ the profile's detection goal (ore example: 0.20 Bq/cm²) **and** the calibration validity envelope holds. A standard uncertainty is never presented as a detection limit.

## 4. Uncompensated estimator (for comparison only)

Background B₀ = N₀/T₀ measured once at a reference position; the photon field at the measurement position differs by an unknown relative amount with standard deviation σ_δ (field non-uniformity along the trailer, neighbouring loads, time variation):

    r_unc      = F − B₀
    ũ_unc²(0)  = B/T_F + B₀/T₀ + σ_δ²·B²              with B the local true background rate
    ũ_unc²(ρ)  = ũ_unc²(0) + ρ/T_F

The same r*, r#, D# expressions apply. The comparison of interest is D#(compensated) against D#(uncompensated) **at equal dwell T_F**, as a function of background rate, σ_δ, k, u(k)/k and T_U/T_F.

## 5. Moving patch

K is defined for a uniform source covering the whole aperture (area A_a, nominally 80 cm²) at the calibrated standoff. For a patch of activity density D_p the expected net counts in a gate are

    E[N_net] = K · D_p · ∫_gate  w(t) dt ,   w(t) = (response-weighted overlap of patch and aperture at time t) / (response-weighted aperture area)

with a uniform response used until a measured spatial response exists. Dwell for an interior floor point on a straight pass is L/v (L = 0.100 m along travel). Detectability for a patch is evaluated on the sum over the gates and lanes whose apertures overlap it, using the expressions above with the summed N and T.

## 6. Map cell estimate

For cell *c*, lane *i*: sum N and t over gates weighted by the fraction of the gate's eroded aperture footprint lying in *c* (weights applied to **live time and counts together**, so rates are footprint averages, never divided by pixel area again). Lanes are combined by inverse-variance weighting of D with the common calibration terms added after combination. Each cell stores: D, u_stat, u_total, D*, D#, T_F, coverage fraction, contributing gate keys (attachment, sequence, lane), reason codes.

## 7. Demonstration coefficients

All coefficients shipped in this repository are synthetic, flagged `field_use_approved: false`, and exist to exercise the code path. Ore example levels: investigation 0.30, comparison 0.40, detection goal < 0.20 Bq/cm². The yellowcake profile is present but disabled and carries no numbers.
