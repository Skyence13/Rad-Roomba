| Symbol | Quantity | Nominal | Range studied | Unit | Basis / source | Status |
|---|---|---|---|---|---|---|
| A_a | aperture area | 80.0 | 80 | cm2 | design 0.3 Rev D layout (80 mm x 100 mm) | design value |
| L/v | dwell of an interior point, one pass | 1.00 | 1 (0.10 m/s) | s | MODEL.md section 5 | design value |
| H | ambient dose rate on the trailer floor | 0.100 | 0.05-5 (stress case 10) | uSv/h | natural background ~0.1; elevated near ore, loaded conveyances and mill yards; no site data | ASSUMED - needs site survey |
| S_beta | floor beta-window photon response | 33.2 | 15-90 | 1/s per uSv/h | Mirion AB-100 42 (1/s)/(uSv/h) for Cs-137, 101.25 cm2 [H7], scaled by area to 80 cm2; range covers spectrum (x0.8 ore-like to x1.8 concentrate-like in the thin-tile model), housing and threshold | ASSUMED from another product |
| S_alpha | floor alpha-channel photon response | 0.158 | 0.05-0.5 | 1/s per uSv/h | AB-100 0.2 (1/s)/(uSv/h) [H7] scaled by area | ASSUMED from another product |
| b_beta | beta-window rate not tracked by the reference | 0.500 | 0-2 | 1/s | AB-100 background <= 5 1/s at <= 0.1 uSv/h, 4.0 used for its MDA [H7]; 4.2 predicted from S alone | ASSUMED |
| b_alpha | alpha-channel intrinsic background | 0.0100 | 0.005-0.05 | 1/s | AB-100 <= 0.05 1/s, 0.01 used for MDA [H7], scaled | ASSUMED from another product |
| k | floor/reference photon count ratio | 1.00 | 1 (matched tile); 0.3; 0.1 (reference 3x/10x more sensitive) | - | matched thin tile gives k ~ 1; a thicker reference tile raises photon interactions roughly in proportion to thickness (NIST mu for vinyltoluene) | ASSUMED - design variable |
| u(k)/k | relative uncertainty of k incl. spectral mismatch | 0.0300 | 0-0.10 | - | fit component ~1 %; spectral component between ore-like and concentrate-like fields 0.4-19.0 % in the shield-attenuation model (results/k_spectral_mismatch.csv); other mechanisms unmodelled | ASSUMED - needs measurement |
| u(b) | uncertainty of the offset | 0.0500 | 0-0.2 | 1/s | long clean-floor run | ASSUMED |
| T_U/T_F | reference live time per floor live time | 1.00 | 1; 4 (four lanes pooled); 10 (running mean) | - | design choice; pooling/averaging assumes the field is uniform over the pooled extent | design variable |
| sigma_delta | relative non-uniformity of the photon field (uncompensated) | 0.200 | 0-0.5 | - | gradients along a 16 m trailer, door end, neighbouring loads, time variation; no site data | ASSUMED - needs site survey |
| T_0 | background count time, uncompensated | 60.0 | 10-600 | s | procedure choice | ASSUMED |
| K_beta | beta-window response | 24.0 | 8-100 | 1/s per Bq/cm2 | AB-100 contact responses [H7] x 80 cm2 x geometry; the value depends on what 1 Bq/cm2 means (results/K_beta_basis.csv); nominal = Cl-36-equivalent | ASSUMED - dominated by the undefined measurand |
| u_rel(K_beta) | relative uncertainty of K_beta | 0.150 | 0.10-0.30 | - | source certificate, standoff, self-absorption, floor finish | ASSUMED |
| K_alpha | alpha-channel response at 10 mm | 6.00 | 1.5-13 | 1/s per Bq/cm2 (alpha) | range model anchored to AB-100 Pu-239 [H7]: thin natural U 7.7, all ore alphas ~13, thick/dusty deposits lower | ASSUMED - model, not data |
| u_rel(K_alpha) | relative uncertainty of K_alpha | 0.350 | 0.3-0.6 | - | standoff (-15 to -30 %/mm for U-238), air density, self-absorption | ASSUMED |
| alpha,beta | per-decision error probabilities | 0.0500 | 0.05; Sidak value for the mission | - | MODEL.md section 3 default; site profile owns them | site decision |
| A_mission | per-mission false-investigation allowance | 0.0500 | 0.05 (P>=1); also expected counts 1-20 | - | not defined by the site | site decision |
| n | independent decision areas per trailer | 4.48e+03 | 1333-5000 | - | 2.5 m x 16 m; 28 lane tracks x 160 cells of 0.1 m | derived |
| eps | fraction of floor surface signal appearing in the reference | 0 | 0-0.2 | - | depends on the beta shield between the tiles (Pa-234m 2.27 MeV, Bi-214 3.27 MeV end points) | ASSUMED - needs measurement |
