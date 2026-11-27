# RR-HEAD-ACQ analogue front end, bias, timing and power budget — rev A design

Owner: head electronics lead (stage 1); **stage 3 (2026-11-27) corrections after `docs/reviews/REVIEW_head_interference.md`
are marked "S3" and summarised in section 13.** Companion files: `head_afe_calc.py` (regenerates every table),
`head_afe_calc_out.md` (its full output, tables T1–T11), `head_afe_pulses.png`,
`electronics/head_acq/design/circuit.py` (the circuit these numbers describe; table T12 of the calculator output confirms that the two files use the same values).

**Evidence labels.** *datasheet* = read from the manufacturer PDF named; *calculated* = derived in `head_afe_calc.py`
or by the arithmetic shown; *assumed* = a design range I chose because no measurement or supplier value exists;
*UNVERIFIED* = recalled, not confirmed against a manufacturer document from this machine. Nothing here is measured.
No SPICE simulation was run; the pulse shapes come from a linear transfer-function model of the same circuit (single-pole op-amp models).

**What the project actually has from an optical supplier: nothing.** `planning/Detector_Head_RFQ.md` asks for SiPM part number,
capacitance, breakdown spread, temperature coefficient and pulse data; no response, drawing or waveform is in the repository.
The Scionix documents in `docs/Sources.csv` (H5, B17) were not opened for this work and nothing from them is used.
Every optical quantity below is therefore a design range.

## 1. Optical / SiPM design ranges

Datasheet values of the candidate devices (T1; onsemi MICROJ-SERIES/D Rev. 9, Hamamatsu KAPD1064E and KAPD1052E, Broadcom AFBR-S4N66P024M-DS):

| device (operating point) | Vbr V | dVbr/dT mV/°C | gain | PDE % | DCR at 25 °C MHz typ / max | crosstalk % | Ct pF | recharge ns | operating °C |
|---|---|---|---|---|---|---|---|---|---|
| onsemi MicroFJ-60035 @ +2.5 V | 24.2–24.7 | 21.5 | 2.9e6 | 38 | 1.84 / 5.5 (50 / 150 kHz/mm²) | 8 | 4140 | 50 | −40…+85 |
| onsemi MicroFJ-60035 @ +6 V | same | 21.5 | 6.3e6 | 50 | 5.5 / — | 25 | 4140 | 50 | −40…+85 |
| onsemi MicroFJ-30035 @ +2.5 V | same | 21.5 | 2.9e6 | 38 | 0.47 / 1.4 | 8 | 1070 | 45 | −40…+85 |
| Hamamatsu S14160-6050HS @ +2.7 V | 38 | 34 | 2.5e6 | 50 | 5.8 / 17.5 (*calculated* from dark current 2.5 / 7.5 µA) | 7 | 2000 | not given (50 *assumed*) | −40…+85 |
| Hamamatsu S13360-6050 @ +3 V | 53 ± 5 | 54 | 1.7e6 | 40 | 2.0 / 6.0 | 3 | 1280 | not given (50 *assumed*) | −20…+60 *UNVERIFIED* |
| Broadcom AFBR-S4N66P024M element @ +12 V | 32.5 | 30 | 7.3e6 | 63 | 4.4 / — | 23 | 1550 | 55 | **−20…+60** (datasheet: operating *and* storage) |

Design ranges, how each is pinned down, and what it sets on the board (all selections are resistor/capacitor values or DAC codes — no board spin):

| Unknown OEM value | Design range and basis | Measurement that fixes it (test point) | Component / setting it drives |
|---|---|---|---|
| SiPM model, area, count per guide | one 3 × 3 mm device … four 6 × 6 mm in parallel (*assumed*) | supplier drawing; confirm by Ct and dark current below | everything in this table |
| Terminal capacitance per channel | 0.3 … 17 nF (*assumed* from the table above ×1…×4) | pulser step with SiPM connected vs. disconnected: decay constant = R_IN·Ct at `Fn PRE` pad | R_IN (R102/R103 class: 2 × 20 Ω fitted = 10 Ω; 5…49.9 Ω), pole-zero R_PZ |
| Breakdown voltage | 24 … 58 V (*datasheet* range of candidates) | I–V sweep per channel using HV_SET and `IMON_CH` (√I vs V intercept) with the lid closed | HV_RAW strap R2207 class (37 / 49 / 53 / 65 V), OVP strap, HV_SET code |
| Vbr spread between the 8 SiPMs | ≤ **2.0 V** (S2-05: trim range 2.4 V less 0.4 V reserve for the lane temperature difference and the I × 4.99 kΩ floor) | same sweep | TRIM_DAC codes; if the spread is larger (possible with S13360, ±5 V lot spread) the SiPMs must be binned — **not coverable on the board** |
| Vbr temperature coefficient β | 21.5 … 54 mV/°C (*datasheet*) | repeat the I–V sweep at two head temperatures | firmware coefficient in `setup_id` |
| Overvoltage | 1 … 12 V (*datasheet* recommended points 2.5–12 V) | chosen from the dark-rate / efficiency scan | HV_SET; gain resistors below |
| Gain (charge per p.e.) | 0.27 … 1.2 pC (*datasheet*, 1.7e6 … 7.3e6) | single-p.e. peak spacing in a BETA_LLD threshold scan of the dark rate (LED off, lid closed) | preamp/fast gain (R_F 499 Ω / R_G 24.9 Ω in each stage), threshold codes |
| PDE | 38 … 63 % (*datasheet*) | not measurable separately; folded into p.e. yield | — |
| Dark count rate vs T | 0.3 … 22 MHz at 25 °C (*datasheet* ×1…×4 devices); halving every 8 °C (*assumed*, range 7–10 °C) | dark threshold scan at +25, +10, 0 °C | lowest BETA_LLD / REF_LLD; head temperature set-point |
| Recharge time constant | 15 … 100 ns (*datasheet* 15–55 ns for the listed devices; margin *assumed*) | pulse tail at `Fn PRE` with the LED or a source | R_PZ = τ/220 pF (226 Ω fitted for 50 ns) |
| p.e. per beta event (0.25 mm plastic through the guide) | **4 … 120, typical 15 (*assumed*)**. Basis: 51 keV deposited by a minimum-ionising electron at normal incidence (*calculated*: 2 MeV·cm²/g × 1.02 g/cm³ × 0.025 cm), ~10⁴ photons/MeV for EJ-212-class plastic (*UNVERIFIED*), 0.5–8 % light collection × PDE (*assumed*) | pulse-height spectrum from a Sr-90/Y-90 or Tl-204 source by BETA_LLD scan and on the 50 Ω monitor | fast gain, BETA_LLD/BETA_ULD codes; decides whether the design works at all (see 3.2). **S3 RFQ requirement (T17): ≥ 18 p.e. at the most-probable deposit of a normally incident MIP at the worst point of the plate** (section 3.2) |
| p.e. and time profile of a 5 MeV-class alpha in ZnS(Ag) | 150 … 15 000 p.e. (*assumed*); 70 % with 200 ns decay, 30 % in a µs tail lumped at 5 µs (*assumed*, literature class) | Am-241 at the window: SLOW/FAST ratio and time-over-threshold on the monitor output | slow integrator R/C (1 kΩ / 1 nF), G3 (2.00 k / 499 Ω), ALPHA code, acceptance window W |
| Reference-tile yield | 10 … 600 p.e. (*assumed*: thicker tile, Compton electrons) | Cs-137 / ambient spectrum by REF_LLD scan | reference-channel gain resistors (same footprints), REF_LLD/REF_ULD |
| SiPM carrier wiring, temperature sensor | 2 coax + NTC assumed | supplier drawing | connectors J101/J102 class (U.FL), lane auxiliary connector (JST GH-6) |

## 2. Signal budget

### 2.1 Chain

`SiPM anode → R_IN 10 Ω to the trim node (AC ground) → 22 Ω + 100 nF → OPA838 ×21 (preamp, 14 MHz) → CR 220 pF/100 Ω with pole-zero 226 Ω → OPA838 ×21 (10 pF integration) → 330 Ω + Schottky clamp → TLV3502 (LLD, ULD)`;
floor channels add `preamp → 1 kΩ/1 nF (1 µs) → 4.7 nF/10 kΩ (52 µs) → OPA836 ×5 → clamp → TLV3501 (ALPHA)`.
Baseline 0.600 V (from the DAC reference). All stages non-inverting, pulses positive, single +5 V supply.

A resistive anode load with a non-inverting amplifier was chosen over a transimpedance stage because it is unconditionally stable for any
SiPM capacitance in the 0.3–17 nF range and it always removes the charge of a saturating pulse through R_IN in R_IN·Ct, whatever the amplifier does.
The price is signal amplitude; T5 shows the electronic noise stays below 0.3 p.e. for a single device.

### 2.2 Per photo-electron (T2, *calculated*)

| device | Q/p.e. pC | R_IN·Ct ns | node A µV | preamp mV | FAST mV | FAST peak / FWHM ns | SLOW mV (alpha profile) | SLOW peak µs |
|---|---|---|---|---|---|---|---|---|
| J60035 @2.5 V | 0.465 | 41 | 37.5 | 0.76 | 6.9 | 59 / 80 | 0.218 | 0.53 |
| J30035 @2.5 V | 0.465 | 11 | 65.6 | 1.21 | 12.2 | 43 / 51 | 0.219 | 0.49 |
| S14160-6050HS | 0.401 | 20 | 43.4 | 0.85 | 8.2 | 50 / 61 | 0.188 | 0.51 |
| S13360-6050 | 0.272 | 13 | 34.0 | 0.64 | 6.3 | 45 / 54 | 0.128 | 0.50 |
| NUV-MT @12 V | 1.169 | 16 | 129 | 2.49 | 24.0 | 47 / 57 | 0.548 | 0.51 |
| 4 × J60035 | 0.465 | 166 | 16.7 | 0.35 | 2.8 | 79 / 178 | 0.202 | 0.71 |

The mandated "tens of ns" fast path is met for a single device (FWHM 50–80 ns); with four 6 mm devices in parallel the input pole (166 ns at 10 Ω) dominates
and the fast pulse is 180 ns wide — fit 2 × 10 Ω (5 Ω) and raise the gain in that case.

### 2.3 Amplitudes for the assumed event classes (T3, J60035 @2.5 V, *calculated*; volts above baseline)

| pulse | p.e. | charge pC | SiPM peak mA | node A | preamp out | FAST out | SLOW out |
|---|---|---|---|---|---|---|---|
| single p.e. | 1 | 0.47 | 0.008 | 38 µV | 0.76 mV | 6.9 mV | 0.37 mV |
| beta minimum | 4 | 1.9 | 0.032 | 0.15 mV | 3.0 mV | 28 mV | 1.5 mV |
| beta typical | 15 | 7.0 | 0.12 | 0.56 mV | 11 mV | 104 mV | 5.5 mV |
| beta maximum | 120 | 56 | 0.96 | 4.5 mV | 91 mV | 0.83 V | 44 mV |
| alpha minimum | 150 | 70 | 0.16 | 1.5 mV | 31 mV | 0.22 V | 33 mV |
| alpha typical | 1500 | 700 | 1.6 | 15 mV | 0.31 V | 2.2 V | 0.33 V |
| alpha maximum | 15 000 | 7000 | 16 | 0.15 V | 3.05 V | clips (22 V linear) | clips (3.3 V linear) |

Limits: preamp linear to 4.25 V above baseline (*calculated* from the 5 V rail); FAST and SLOW are clamped at 3.0 V above baseline by the Schottky pair into the 3.3 V comparator rail;
thresholds reach 1.90 V above baseline (2.5 V DAC full scale). So BETA_ULD can be set up to 274 p.e. and ALPHA up to 8700 p.e. for this device (T4).
Dynamic range between a 5 p.e. beta threshold and the largest alpha: 3000:1 in charge; nothing upstream of the fast gain stage saturates over that range, and
only the fast stage and (for the largest alphas) the slow stage clip. Per the lead's instruction the alpha channel is a confirmation channel: no further dynamic range was added.
The NUV-MT at +12 V has 3.5× this gain: beta maximum reaches 2.9 V — reduce the fast gain (R_G 49.9 Ω) or the overvoltage.

**Recovery after a maximum alpha (*calculated* estimates):** OPA838 overdrive recovery 50 ns (*datasheet*); the anode charge leaves through R_IN in ≤ 0.2 µs.
**S3 correction (review m2):** the stage-1 statement "the 22 ns fast CR suppresses the 100 µs input-coupling undershoot by ~10⁻⁴" was wrong: the pole-zero
network (R_PZ 226 Ω from PRE to FS, R_D 100 Ω to VBL) passes DC with 100/326 = 0.307, so FAST saw 6.45 × PRE at low frequency. In addition the trim node
(4.8 µF) takes the alpha charge as a 1.5 mV step that recovers only in ~24 ms; through the 100 µs input coupling it becomes a long negative tail
that the review's model did not contain. T14 (*calculated*, 15 000 p.e. alpha, J60035): stage-1 network −2.6 p.e. at 150 µs, **−3.3 p.e. at 300 µs, −1.9 p.e. at 500 µs**
(the 300 µs firmware hold would not have been enough). **Fix S3-04:** 47 nF in series with R_PZ (C150-class, all eight channels): (R_PZ + R_D) × 47 nF = 15 µs,
1 Ω at 3 MHz, so the pulse and the pole-zero cancellation are unchanged (T2: 6.92 mV/p.e., FWHM 80 ns, undershoot 0.6 %); FAST tail −1.2 / −0.5 / −0.2 / +0.06 p.e.
at 100 / 150 / 200 / 300 µs, deepest −33 p.e. at 10 µs (inside the hold). After a 1500 p.e. alpha the tail is −0.05 p.e. at 150 µs.
The slow baseline is depressed by ~30 mV (≈ 140 p.e. of alpha scale) for ~100–200 µs (unchanged, slow path).
ZnS(Ag) afterglow can keep the LLD comparator busy for tens of µs: the firmware already waits for LLD low before clearing.
Not covered by any calculation: the real afterglow photo-electron rate — measure with Am-241 (bench test B7).

### 2.4 Monitor output and waveform capture — what they can and cannot do

* `J2701` (U.FL, 50 Ω): unity-gain OPA836 buffer behind a per-lane 8:1 multiplexer. **S3 (review M2/m4):** the stage-1 figure "1 kΩ × 12–15 pF → 10–15 MHz"
  ignored the bus: four TMUX1108 drains + ~300 mm of trace + buffer ≈ 50–150 pF (*assumed*), i.e. 1–3 MHz already in stage 1. The taps are now 10 kΩ at the
  op-amp OUTPUTS (FAST, SLOW, PRE; S3-01) and the lane muxes are OFF while counting (MON_LANE_EN = 0, S3-02), so **the monitor is a baseline / slow-signal monitor,
  0.1–0.3 MHz** (T15), gain 0.98 (10 kΩ into the 1 MΩ ∥ 1 MΩ bus bleeds). It shows FAST (op-amp output, not clamped), SLOW, preamp of the reference channels,
  preamp of the floor channel (page 2), baseline. Single-p.e. spacing and pulse shapes: use the PRE pads or threshold scans, not J2701. With the lane muxes off,
  MON_BUS carries the frame-potential monitor (0.300 V + V(FRAME)/2, S3-03, section 9).
  Un-multiplexed, full-bandwidth access: the `Fn PRE` / `Rn PRE` pads (453 Ω series = 10:1 into 50 Ω).
* MCU ADC2 on `MON_ADC` (1 MHz anti-alias): at ≤ 4 MS/s it **can** digitise the SLOW output (0.5 µs peaking, tens of µs tail: 2–4 samples on the rise) and baselines;
  it **cannot** resolve the FAST pulse (80 ns FWHM = one third of a sample period) — fast-pulse shape work needs an oscilloscope/digitiser on J2701 or the PRE pads.
  With the pulser (repetitive, MCU-timed) an equivalent-time scan in 6.9 ns timer steps can reconstruct the pulser response, not random scintillation pulses.
* Time over threshold of every event is available without any of this from the raw LLD lines on TIM4/TIM3 (section 4) - it is now the alpha/beta discriminator (2.5).

### 2.5 Alpha / beta separation (S3, review C1)

The ALPHA comparator looks at SLOW, and SLOW responds **more** per p.e. to fast plastic light than to ZnS light (T2: 0.369 vs 0.218 mV/p.e., J60035), so an
amplitude threshold alone cannot separate a bright beta from a weak alpha: with ALPHA = baseline + 30 mV every beta ≥ 81 p.e. is an "alpha". The
radiometry alpha background budget (0.01 s⁻¹) against ~33 s⁻¹ beta-window rate per µSv/h means a beta tail of 3 × 10⁻⁴ is already the whole budget.

*Time over threshold of the raw LLD* (firmware 0.5.1: alpha requires ALPHA and TOT ≥ 250 ns). T13 (*calculated*, FAST clamped at 3.0 V, ZnS decay 200 ns *assumed*):

| device | LLD | brightest beta (240 p.e.) TOT | weakest alpha (150 p.e.) TOT | gap | cut (mid-gap) |
|---|---|---|---|---|---|
| J60035 @2.5 V | 10 | 202 ns | 374 ns | 172 ns | ≈ 290 ns |
| J30035 @2.5 V | 10 | 115 ns | 246 ns | 131 ns | ≈ 180 ns |
| S14160-6050HS | 10 | 139 ns | 290 ns | 151 ns | ≈ 215 ns |
| S13360-6050 | 10 | 121 ns | 258 ns | 137 ns | ≈ 190 ns |
| NUV-MT @12 V | 10 | 129 ns | 272 ns | 143 ns | ≈ 200 ns |
| 4 × J60035 (R_IN 10 Ω) | 10 | 571 ns | 738 ns | 167 ns | ≈ 655 ns |

Conclusions: (1) with the 6.94 ns capture tick (±7 ns per TOT) every candidate has a gap of 130–170 ns = 19–25 ticks: **TOT on the raw LLD is robust, provided the
cut is a per-device setup value placed mid-gap**; a fixed 250 ns is wrong for two candidates (J30035 and S13360 weakest alphas at 246 / 258 ns would be lost,
and for a 4-device array every beta would pass as alpha). Recommended firmware defaults per device type: the "cut" column; confirm with Sr-90/Y-90 alone and
Am-241 alone (T3 extension). (2) This model gives the weakest J60035 alpha 374 ns at LLD 10 (428 ns at LLD 8), not the review's "≥ 280 ns" lower bound,
so the margin of the 250 ns cut is ~120 ns, not 27 ns as firmware estimated from the review; the cut should still move to ~290 ns for J60035.
(3) The physics risk is the ZnS(Ag) decay time: every alpha TOT above scales with it; if the OEM's ZnS layer is faster than 200 ns the gap shrinks - measure.
(4) The C_PZ of S3-04 does not change the TOT (the 200 ns ZnS light is far above the 10 kHz C_PZ corner).

Circuit options considered (decision: **no hardware change in rev A**):
* ALPHA-width or LLD-to-ALPHA-delay capture: needs a timer-capture input for an OR of the four floor ALPHA comparator outputs. PF1 (the only free pin) has no
  timer channel (pin DB: ADC2_IN10, COMP3_INM, SPI2_SCK, GPIO); a capture pin can only be freed by moving PULSER_A0 from PF2 (TIM20_CH3) to PF1, which takes the
  contract-reserved SYNC_IN pin, plus a board-wide 4-lane OR chain (new event line through all four lanes, breaks lane identity). The SLOW width is in any case a
  weak discriminator (both populations are dominated by the 52 µs baseline CR). Rev-B request (S3-R1).
* Second slow comparator level: needs four more MCU inputs - none free. Not done.
* Slow-path shaping: any linear shaper with a positive impulse response gives betas at least as much per p.e. as ZnS alphas (beta light is a delta at this time
  scale), so no shaping change alone separates them; a bipolar "tail-minus-prompt" shaper would, but its beta cancellation depends on R_IN·Ct (11–166 ns across
  candidates) and is not robust - not done.
* Amplitude-ratio aid with existing comparators (firmware option, no hardware): FAST/SLOW per p.e. is 18.8–31.8 for betas and 6.7–8.4 for alphas (T13, single
  devices). Setting BETA_ULD ≈ 12 × the ALPHA level (FAST mV vs SLOW mV) makes "ALPHA and not ULD" a clean alpha region for the weakest alphas, and "ALPHA and ULD"
  the TOT-decided region. Cost: ALPHA = ULD/12 raises the lowest detectable alpha (ULD 150 p.e. = 1.04 V → ALPHA 86 mV → 395 alpha p.e.). Offered as option.
* ALPHA threshold range: up to 1.9 V above baseline (8700 alpha p.e. for J60035) - sufficient; the default must follow SLOW(beta max) × 1.3 only if no TOT rule is used.
* 4-device arrays: fit R_IN = 5 Ω (2 × 10 Ω) - halves τ_in, restores the single-device TOT gap.

## 3. Noise budget

### 3.1 Electronic noise (T5, *calculated*)

Input-referred 2.0 nV/√Hz (OPA838 1.8 nV/√Hz *datasheet*, 22 Ω protection resistor, 23.7 Ω feedback network; current noise 1 pA/√Hz *assumed*); FAST output noise 1.7 mV rms:

| device | ENC p.e. rms |
|---|---|
| J60035 @2.5 V | 0.25 |
| S14160-6050HS | 0.21 |
| S13360-6050 | 0.27 |
| NUV-MT @12 V | 0.07 |
| 4 × J60035 | 0.61 |

A 5 p.e. threshold is ≥ 18 σ of electronic noise for a single device: electronics is not the limit. Pin-compatible upgrade if a large array needs it: LMH6629 (SOT-23-5 version differs — *UNVERIFIED* drop-in; treat as a rev-B option).

### 3.2 Dark-count pile-up → lowest usable BETA_LLD (T6, *calculated* from *datasheet* DCR/crosstalk and *assumed* temperature law)

Model: dark pulses are Poisson with a Borel-distributed crosstalk multiplicity; a trigger is an upward crossing of (n − 0.5) p.e. when a new pulse lands on the pile-up of
earlier ones inside the resolving time. The resolving time is 0.50 × (area/peak) of the shaped pulse, the factor fitted to a Monte-Carlo with the real pulse shape
(agreement within 10 % at n = 3…5 in a 0.2 s Monte-Carlo; the extrapolation to 1 s⁻¹ is model, not Monte-Carlo).
Integer n such that the dark trigger rate is < 1 s⁻¹ (in brackets < 0.1 s⁻¹). **S3 (review M1): the design criterion is now ≤ 0.05 s⁻¹ per chain**
(10 % of the radiometry's total untracked beta-window background b_beta = 0.5 s⁻¹; 1 s⁻¹ alone was twice that budget); the 0.05 s⁻¹ column is in T6
of `head_afe_calc_out.md` (J60035 typ: 11 / **10** / 9 / 8 p.e. at +25 / +10 / 0 / −20 °C; max DCR: 13 / **11** / 10 / 9).

| device | DCR | +25 °C | +10 °C | 0 °C | −20 °C |
|---|---|---|---|---|---|
| J60035 @2.5 V | typ | 10 (11) | 8 (10) | 8 (9) | 7 (8) |
| J60035 @2.5 V | max | 11 (13) | 9 (11) | 8 (10) | 7 (9) |
| J30035 @2.5 V | typ | 8 (9) | 7 (9) | 7 (8) | 6 (7) |
| S14160-6050HS | typ | 10 (12) | 9 (10) | 8 (9) | 7 (8) |
| S14160-6050HS | max | 13 (15) | 10 (11) | 9 (10) | 8 (9) |
| S13360-6050 | typ | 7 (8) | 6 (7) | 6 (6) | 5 (6) |
| NUV-MT @12 V | typ | 21 (25) | 19 (22) | 17 (21) | 15 (18) |
| J60035 @6 V | typ | 25 (29) | 21 (25) | 20 (23) | 17 (20) |
| 4 × J60035 @2.5 V | typ | 14 (16) | 11 (12) | 9 (11) | 8 (9) |

Reading: **for a single 6 mm device at its low-overvoltage point the lowest usable BETA_LLD is about 7–8 p.e. at −20 °C, 8–9 at the +10 °C heater set-point and 10–11 at +25 °C** (low-crosstalk S13360: 5 / 6 / 7).
Below about 0 °C the limit is set by crosstalk, not by pile-up, so cooling further buys little; high-overvoltage operation (crosstalk 23–25 %) costs a factor of two or more in threshold.
Sensitivity to the assumed halving temperature (7–10 °C): ±1 p.e. at −20 °C.
Consequence against the *assumed* 15 p.e. typical beta signal: the margin is thin, and it does not exist if the real yield is at the low end of the range.

**Minimum photoelectron yield for the optics RFQ (S3, T17, *calculated*).** Model: N ~ Poisson(μ·x), x = E/E_MPV ~ Moyal (MPV = 0.70 × mean, *assumed* for
0.25 mm plastic), μ = p.e. at the most-probable deposit of a normally incident MIP at one point of the plate. Efficiency at that point: μ = 10 → 0.68,
15 → 0.88, 20 → 0.95, 30 → 0.99 at LLD 10. **Requirement: ≥ 90 % at the worst point of the plate at LLD(0.05 s⁻¹, +10 °C) gives μ_worst ≥ 16.2 p.e.
(J60035 typ DCR, LLD 10) and ≥ 17.7 p.e. (max DCR, LLD 11) → RFQ: "guaranteed ≥ 18 p.e. at the MPV deposit of a normally incident MIP at the worst point of
the 80 × 100 mm plate, at the stated overvoltage and +10 °C, position map ≥ 9 points", equivalently μ_worst ≥ 1.6 × LLD(0.05 s⁻¹, +10 °C, DCR max) for another
device (T6 gives its LLD).** The plate-average value follows from the OEM's light-collection map; with the *assumed* ±50 % uniform variation it is
2 × 18 = 36 p.e. at the MPV (mean deposit 36/0.70 ≈ 51 p.e.) - the review's "plate-average mean ≥ ~30" equates MPV and mean and is low by that factor.
This sharpens IB-22 (thresholds there were at the 1 s⁻¹ criterion). Interaction with C1: optics that bright put the beta tail well above the 30 mV ALPHA level,
so the alpha decision must use TOT (2.5).
This is the principal risk of the head (section 11). Electronics cannot remove it; the selectable items that help are overvoltage, head temperature set-point (+10 °C is better than room temperature by 1–2 p.e.), R_IN/pole-zero (shorter resolving time) and the choice of a low-crosstalk SiPM.
Dark triggers are also a temperature-dependent background term in r = F − kU − b: the radiometry lead should take the dark rate at the chosen threshold as a measured input.

### 3.3 Other contributions and their allowances

| Source | Estimate | Evidence | Allowance / requirement | Bench pass/fail test |
|---|---|---|---|---|
| Threshold DAC step (DAC60508, 2.5 V/4096) | 0.61 mV = 0.09 p.e. (J60035) | calculated (T4) | ≤ 0.25 p.e. | B3: threshold scan of the pulser edge, step visible, monotonic |
| DAC reference drift (5 ppm/°C max, *datasheet*) | 12 µV/°C on 2.5 V | calculated | negligible | — |
| Comparator offset (±6.5 mV max, *datasheet*) | ±0.94 p.e. static | calculated | calibrated per channel by the baseline scan; drift 5 µV/°C negligible | B3: noise-edge (baseline) scan per comparator, stored in `setup_id` |
| Comparator hysteresis (6 mV typ, *datasheet*) | 0.87 p.e. | calculated | accepted; sets the minimum useful threshold step | B3 |
| Baseline shift of FAST from preamp bias current drift (7.8 nA/°C avg × 1 kΩ × 0.31 × 21) | 0.05 mV/°C = 0.007 p.e./°C | calculated | ≤ 0.02 p.e./°C | B9: baseline scan at two temperatures |
| Bias ripple → gain | ΔG/G = ΔV/Vov: 1 mV → 0.04 % (2.5 V) | calculated | ≤ 0.1 % | B5: HV_BUS ripple < 2 mV p-p in 10 Hz–100 kHz at the TP |
| Bias ripple → direct injection through Ct into R_IN (fast band; coupling ≈ 1 above ~4 MHz) | boost 700 kHz ripple ~20 mV (*assumed*) at HV_RAW; filters: 100 Ω/1 µF, follower gate 0.47 ms, 1 kΩ/1 µF, 100 Ω/100 nF: > 150 dB nominal at 700 kHz | calculated (ideal parts) | **required ≥ 82 dB** from HV_RAW to the cathode (20 mV → 1.6 µV = 0.05 p.e. at node A) | B5: dark rate at a 3 p.e. threshold with the boost running vs. external quiet bias on HV_BUS: ratio 1.00 ± 0.05 |
| Bias regulator noise (zero-drift op-amp, 2.4 MΩ divider, ×25) | < 0.2 mV rms in the 6 Hz loop band; out of band it is filtered by 1 kΩ/1 µF (160 Hz) | calculated estimate | ≤ 1 mV rms | B5 |
| Lane-to-lane electrical crosstalk | — | — | a 15 000 p.e. alpha in one channel must stay < 5 p.e. in every other: **≤ −70 dB at FAST** | B6: pulser at full scale on one channel (PULSER_A), all other LLD at 5 p.e.: zero counts in 10⁵ pulses; repeat with C_INJ2 fitted |
| Comparator / latch edges into another channel's anode | 3.3 V in 1.5 ns | datasheet | stray capacitance to a foreign anode node **< 15 fF** (0.05 pC = 0.1 p.e.) — layout rule | B6 with the aggressor at high rate |
| Feedback of a channel's own comparator edge | harmless: BUSY is non-retriggerable until CLR | by construction | LLD must not oscillate at threshold | B3: no chatter on raw LLD at the noise edge (hysteresis) |
| SPI/I²C activity | **S3 (review m7): not true** - bias tracking writes HV_SET (U_DAC0 OUT6) while armed, ≤ 20 mV per 100 ms step; *calculated* ≈ 3 nA at the anode and ≈ 50 µV (0.007 p.e.) DAC glitch on the lane 0/1 thresholds (5 nV·s *assumed*) - harmless, but B8 must run with tracking active | calculated | I²C temperature reads during gates must not add counts | B8: dark rate at 3 p.e. with housekeeping on/off, ratio 1.00 ± 0.05 |
| MCU 144 MHz, service ISR, CLR pulses | — | — | same criterion | B8 |
| Heater edge, magnetic | 26 µV for 1.2 ms in a pigtail loop for M = 10 nH (*assumed*) → 7 × 10⁻⁵ p.e. at FAST | calculated (T9) | ≤ 0.1 p.e. | B10 |
| Heater edge, supply step | 3.1 A in the heater pair only; shared chassis-side impedance gives ≤ 0.3 V step in ≥ 0.6 ms on HEAD_PWR (*assumed*) → buck + LC + LDO: µV on +5V_A | calculated estimate | ≤ 0.1 p.e. | B10: counts in gates with a heater transition vs. without (DIAG marker), 10⁴ transitions, difference < 3 σ; scope +5V_A |
| Lane-monitor scan while armed (S3, review M2) | stage 1: 1 kΩ tap at FCMP, −14…−18 % amplitude while connected and +0.7…+7 p.e. per switch event, 25 s⁻¹ per channel; S3: taps 10 kΩ at the op-amp outputs and all lane muxes OFF while armed (MON_LANE_EN = 0) → 0; with the monitor enabled for engineering: ≤ 0.13 p.e. at FAST, ≤ 1.2 p.e. at a PRE tap for 3 pC switch charge (T15) | calculated (switch charge, bus C, Z_out *assumed*) | firmware parks MON_LANE_EN = 0 whenever armed | B8 with the IMON scan on/off and MON_LANE_EN 0/1, averaged capture at FCMP triggered on MON_MUX_A0 |
| Motor PWM conducted on HEAD_PWR | 1 V p-p at 20 kHz, 2 V spikes in 1–30 MHz (*assumed*; chassis lead to supply measured values) | assumed | **required: ≥ 100 dB J1 → +5V_A over 1–30 MHz** (2 V → 20 µV at an op-amp with ~20 dB PSRR at 10 MHz = 0.05 p.e.); at 20 kHz ≥ 40 dB is enough (slow path only, threshold ≥ 100 p.e.). Provided nominally: CM choke + π (10 µH/20 µF), buck, LC 10 µH/22 µF (10.7 kHz), TPS7A20 (95 dB at 1 kHz *datasheet*; MHz PSRR *UNVERIFIED*), per-channel bead + 4.7 µF | calculated (ideal parts > 150 dB; real limit is layout) | B11: inject 1 V p-p 10 kHz–30 MHz onto HEAD_PWR through a LISN/bias-tee: dark rate at 3 p.e. unchanged within 5 %; then with the real motors reversing (ICD §8 item 2) |
| Radiated / capacitive pickup at the pigtails | not calculable without the mechanical design | — | spreader plate and cover form a closed screen bonded to GND; pigtails < 35 mm coax | B11, B12 (cover off vs. on) |

### 3.4 Motor noise with an unshielded prototype housing (IB-09)

Situation (contract 0.4.0-draft5): the SiPM front ends are about 65 mm ahead of two brushed gearmotor cans driven by a 20 kHz-class PWM bridge, and the prototype head
housing is printed plastic. **No shielding credit is taken from the enclosure**; what the design relies on is listed after the estimates. All geometry below is *assumed* — none of it is measured.

| Coupling path | Assumption | Estimate (*calculated*) | Against threshold |
|---|---|---|---|
| Magnetic, PWM ripple at 20 kHz | 1 A ripple in a 10 cm² motor-lead loop at 65 mm → B = μ0·I·A/(2πr³) = 0.73 µT; victim loop 0.5 cm² (an **unshielded** SiPM carrier/pigtail loop) | EMF = ωBA = 4.6 µV at 20 kHz. Fast path rejects 20 kHz by 2.8 × 10⁻³ → nothing. Slow path is in band: ≈ 0.24 mV at SLOW | ALPHA threshold ≥ 20 mV: margin ×80 |
| Magnetic, PWM edges - **S3 (review M4): the stage-1 aggressor "1 A in 100 ns in a 10 cm² motor-lead loop" does not exist** (the winding inductance keeps the lead current continuous); re-derived with the physical aggressors in T16 (*calculated*, J60035, coaxial-dipole mutual inductance, most favourable orientation; geometry and currents *assumed*) | stage-1 case reproduced: 0.36 mV EMF = 7.1 p.e. open pigtail (stage-1 text said ≈ 10) / 0.28 p.e. coax. Physical terms: differential lead ripple 60 mA p-p in 150 ns 0.28 / 0.01; bridge hot loop on RR-CHS-MAIN (2.68 A / 150 ns, 2 cm² at 90 mm) 0.95 / 0.04; common-mode lead current from 80 V/µs into ~1 nF 0.25 / 0.01; **brush commutation arc (~0.1 A CM in ~5 ns, PWM-independent: present at 100 % duty, coasting, back-driven, brake relay K2/K3) 2.8 / 0.11 p.e.** (open 0.5 cm² at 35 mm / coax 2 mm² launch) | open pigtail: every term is below the LLD but the arc is 3-4 p.e. and adds to dark pile-up - coax mandatory (IB-23 stands); with coax every motor term ≤ 0.3 p.e., plus the shield-loop term of review m1 (~0.3 p.e., not bounded above a few MHz) |
| same, longer pigtails (IB-57: 45-50 mm instead of 35 mm) | open loop area × 1.36: 0.68 cm² at 47.5 mm | open-loop terms × 1.36 (T16 column 2); **the coax column is independent of the pigtail length** (only the U.FL launch and the carrier pads remain open) | the 35 mm figure is not a requirement for the coax case: the RFQ / budget pigtail-length limit is replaced by "coax, both ends terminated, anode/bias/aux bundle tight" |
| with the lane can and a 0.3 mm aluminium cover | edge spectrum ≥ 3 MHz: skin depth in aluminium ≈ 50 µm | ≥ 40 dB more for the part of the loop inside the screen | negligible |
| Capacitive, motor can / leads swinging 12 V in 100 ns | 2 fF from a motor can to an exposed anode node at 65 mm | Q = C·ΔV = 24 fC = 0.05 p.e. | negligible even unshielded; 20 fF would still be 0.5 p.e. |
| Brush arcing (broadband) | conducted on the motor supply and radiated from the leads | radiated term in T16 (order of magnitude; the review's ≈ 20 p.e. ignored the 14 MHz preamp and 5 ns integration pole); conducted term: J1 → +5V_A filter chain | coax + motor-terminal suppression (requirement to the harness owner: `electronics/head_acq/STAGE2_CHANGE_REQUESTS.md` Stage 3, H-01); test M7 items 3-4 |
| Common-mode current on the J1/J2 cables | head-to-chassis capacitance is large when docked; chassis ground bounce at PWM edges 0.1–1 V | flows in the cable shields and through the 1 MΩ ∥ 10 nF shield bonds and the J1 common-mode choke (900 Ω class at 100 MHz). **S3 (review m3): "the J2 side is galvanically isolated" holds at DC only** - above ~1 MHz head GND reaches the chassis through four parallel paths: J1 pin 2 through L2001; J1 shield 10 nF → H1 → spreader → F2801/R2801; J2 shield 10 nF → H3 → spreader → the HF bonds; and the heater films' 9-18 nF to the spreader, closing through J1 pins 3/4 which have no common-mode element (10 nF = 16 Ω at 1 MHz) | covered by test (CM clamp injection 1-30 MHz, M7 item 5); option if sensitive: 4 A CM choke on the heater pair at J2601 or a grounded screen layer in the heater film (OEM) |

What the board provides, with no help from the housing: (1) coaxial connections for both anode and bias of every SiPM (shield = signal return); (2) a clip-on shield can per lane
over preamp, shapers and comparators (36 × 32 × 5 mm, 12 clips to board ground); (3) S3 stack-up: solid GND planes on In1 AND In4 (every signal layer next to a GND
plane), the aluminium spreader plate 2.5 mm below the board, bonded to board ground at ONE DC point at H1 (0.5 A fuse F2801 + 0 Ω R2801 within 1 mm of the H2801 pad)
and by four 10 nF capacitors at H2, H5, H6 and H8 (H3 lies inside the isolated RS-485 island, which has no GND); (4) 10 Ω anode load impedance; (5) common-mode choke and π filter on the supply.

**Common-mode current path after S3 (review M3; placement, not measured).** Stage 2 had R2801 and all four 10 nF frame capacitors auto-placed beside the lane 3
can (u 316-321) and FRAME had no copper: every shield/ESD current crossed the whole 316 mm spreader under all four lanes and entered GND beside lane 3. Now:
J1 braid → drain W-101.S → TP2004 (83.0, 29.1), 9 mm in front of J2001 → C2007 ∥ R2012 (80.3, 29.0 / 32.4) → 0.6 mm FRAME track into the H2801 pad
(75.5, 30.0) → standoff → spreader → back up the same standoff → F2801 → R2801 → GND at H1, 20 mm from J2001 pin 2 (u 94.3) where L2001 returns to the
chassis: the J1 CM loop closes inside the J1 landing, between lanes 0 and 1, not under any lane. J2 braid → TP2501 (241.5, 2.5) → C2504 ∥ R2505 → H2803 pad →
spreader → the nearest GND bonds C2801 at H2 (87.5 mm, along the rear edge under lane 2's U.FL strip) and C2804 at H6 (87 mm, along the lane 2|3 seam) - this
residual path remains because H3 is inside the isolated island (no GND there); HF only (10 nF), and the J2 CM current is the RS-485 pair's, small. Every frame
bond part is now within its rule distance (`scripts/placecheck.py`).
What it cannot provide: screening of the SiPM carriers and pigtails in the rear chimney, which are outside the board — the head mechanical EMI cover must close that volume (requirement in `layout_guidance.md` §4).

Bench test B11 (extended): head in the prototype plastic housing on the robot, bias on, lid closed, BETA_LLD at 3 p.e. and at the operating threshold. Record dark rate and the time-over-threshold histogram for:
motors off; motors at 20 kHz PWM, 0/50/100 % duty, free-running and stalled at the current limit; direction reversal; each with and without the lane cans and the EMI cover.
Pass (S3, review M7): **averaged, aggressor-synchronised waveform capture at the comparator input** (FCMP with a ≤ 1 pF active probe, or the PRE pad), ≥ 10⁴ triggers on
each aggressor (bridge output node, HTR_GATE, MON_MUX_A0, PULSER_STROBE, LED_STROBE, a current probe on a motor lead for commutation): coherent pickup < 0.3 p.e. at FAST;
then the count rate at the operating threshold within 3 σ of a 100 s count in every motor state (DC bench supply at 100 %, back-driven with bridges asleep, brake relay
transitions, head undocked on the extension). The shortest TOT bin is not a diagnostic (FAST FWHM is 80 ns: every near-threshold dark pulse lands there), and count
rates at 3 p.e. resolve only ~63 s⁻¹ (3 σ of 4.5 × 10⁴ s⁻¹). Fail: fit the cover/cans, then add chassis-side motor filtering (integration backlog).

Chassis-side facts adopted (from the chassis design, not verified here): electronics feed through a TPS259470 eFuse at 1.5 A (the head's own limit is 1.0 A, so the head trips first);
heater feed is a slew-limited 4 A branch (the head's slew limit is then the second one in series); BUS_5V limited to 150 mA; host transceiver THVD1450 with 120 Ω termination and the fail-safe bias at the chassis end
(the head fits 120 Ω and no bias, as the contract requires).

## 4. Timing budget (T7)

| Item | Value | Evidence |
|---|---|---|
| FAST peaking / FWHM (J60035) | 59 / 80 ns | calculated |
| SLOW peaking for the ZnS profile | 0.53 µs (0.7 µs for 4 devices) | calculated, profile assumed |
| Comparator propagation delay | 4.5 ns at 100 mV overdrive, 7.5 ns at 5 mV (12 ns max over temperature) → 3 ns dispersion (7.5 ns worst) | datasheet TLV3501 |
| OR gate + latch clock-to-Q | ~3 + ~4 ns at 3.3 V | UNVERIFIED typical LVC values |
| Latch minimum clock pulse (SN74LVC74A, 3.3 V) | 3.3 ns | datasheet |
| Comparator minimum output pulse vs. latch | a pulse only 0.3 % above threshold already gives ≥ 4.3 ns over threshold | calculated; effective threshold shift +0.3 %, constant, absorbed by calibration |
| Comparator output loading | OR-gate input (~4 pF) directly at the pin; the raw LLD copy leaves through 100 Ω into a 150–250 mm trace + MCU pin + 100 kΩ (≈ 30–45 pF): 3–4.5 ns RC at the MCU, the latch clock is not slowed | calculated estimate |
| Timer capture resolution (TIM2/TIM5 BUSY, TIM4/TIM3 raw LLD, 144 MHz) | 6.94 ns | calculated |
| Smallest time-over-threshold the timers resolve | 1 tick quantisation on each edge (two different timers): ±7 ns; pulses shorter than ~2 ticks (14 ns) may lose the falling capture — they are the events within ~3 % of threshold | calculated |
| Fast/slow skew vs. acceptance window | ALPHA crosses ≤ 0.6 µs after LLD (≤ 1 µs with 4 devices); W = 4 µs leaves ≥ 3 µs for late ZnS light | calculated |
| Acceptance window W / service interval | 4 µs / 10 µs (100 kHz) | contract |
| Dead time per event | W + U(0, 10 µs) + ISR ≈ **10.5 µs mean, 15.5 µs max** (ISR allowance 1.5 µs *assumed*); firmware simulation reports ≈ 9.7 µs | calculated; **measured per event in operation, not modelled** |
| Live fraction | 0.9990 at 100 s⁻¹, 0.979 at 2000 s⁻¹, 0.905 at 10⁴ s⁻¹ | calculated |
| Maximum useful rate | live fraction 0.5 at 9.5 × 10⁴ s⁻¹; hard ceiling 10⁵ s⁻¹ (one event per service tick) | calculated |
| Pile-up at the highest design rate (2000 s⁻¹, *assumed* by radiometry) | second event inside W: 0.8 %; two events inside the fast resolving time: 0.02 % | calculated |
| Gate boundary | timer compare; busy intervals are split exactly at the boundary, so the boundary adds no jitter to live time; an event is attributed to the gate in which it is classified (≤ 15.5 µs late) | contract / firmware |
| Clock (24 MHz TCXO, ±2.5 ppm class *UNVERIFIED* part) | live fraction is a ratio of ticks: unaffected. Absolute live time and span: ±2.5 ppm. Time sync: 2.5 ppm × 10 s expiry = 25 µs against the 2 ms target | calculated |

Hardware notes for firmware: (1) an ALPHA latch can in principle be set without BUSY (slow light with a fast amplitude below BETA_LLD); it then stays set and would be read with the next beta. Check the ALPHA latches of idle chains in the service tick and clear them (count as "alpha without LLD" in DIAG).
(2) After an alpha, hold the chain a further ~100–200 µs (ZnS afterglow, slow-baseline undershoot) — the dead time is measured, the alpha rate is tiny.

## 5. Bias and temperature compensation

### 5.1 Topology

`+3V3 → bead → TPS61391 boost (700 kHz) → 100 Ω/1 µF → current mirror of the TPS61391 (0.8 × I to BIAS_IMON, 2.0 mA limit) → BSS123 source follower inside a slow precision loop (OPA2333 integrator, MMBTA42 level shifter, 0.1 % 25:1 divider) → HV_BUS → per channel 1 kΩ/1 µF + 100 Ω/100 nF → U.FL → cathode`;
anode returns through R_IN and a 4.99 kΩ sense resistor to the per-channel trim buffer (TLV9062), which is driven by its TRIM DAC output.

| Parameter | Value | Evidence |
|---|---|---|
| Bias-on ramp (S3, IB-58) | "ramp ≤ 5 V/s" means **5 V/s at HV_BUS** (0.2 V/s at HV_SET, 0.5 V per 100 ms period): charging the ~9.8 µF on the bias bus (1 µF + 8 × 1.1 µF) then takes 49 µA, well inside the 2.0 mA limit and the BIAS_IMON window; at 125 V/s (5 V/s at the DAC output) it would be 1.2 mA and the 12.5 V staircase steps would hit ISHORT | calculated |
| Set-point law | V(HV_BUS) = 25.0 × V(HV_SET); 0 … 62.5 V in 15.3 mV steps (12-bit DAC60508). DAC80508 in U_DAC0 is the 16-bit drop-in (0.95 mV) if a finer common step is wanted | calculated |
| Per-channel bias | V(SiPM) = V(HV_BUS) − V(TRIM) − I·1.1 kΩ; trim 0.10 … 2.50 V usable, 0.61 mV steps = 0.024 % gain at 2.5 V overvoltage | calculated |
| Absolute accuracy before calibration | DAC reference ±0.2 %, divider 0.1 %, op-amp offset negligible → ±0.2 V at 60 V; calibrate once against a DMM at the HV_BUS pad | datasheet + calculated |
| Independent read-back | second divider 1:25.22 → buffer → BIAS_VMON (ADC, 3.0 V reference of its own). **S3 (IB-58): the tops R2217/R2218 (2 × 4.99 MΩ) are 1 % parts** (only the bottom R2219 412 kΩ is 0.1 %), so the read-back and the OVP trip are ±1.2 % worst case (±0.4 V at 31.5 V), not 0.1 %; firmware calibrates BIAS_VMON per board against the HV_BUS pad at bring-up step 9 (no orderable 4.99 MΩ 0.1 % 0805 thin-film part could be verified from this machine). The regulation divider (2 × 1.2 MΩ + 100 kΩ) is 0.1 % as stated | by design |
| Loop | integrator 100 kΩ/470 nF, divider node 96 kΩ/470 nF (cancels the integrator zero), stage gain −47, crossover ≈ 6 Hz, phase margin ≈ 70° (*calculated* with an assumed follower gm of ~1 mS; **not simulated** — bench step test B5) | calculated |
| Load regulation | DC: integrator → zero error at HV_BUS. Per-channel 1.1 kΩ: 1 mV per µA (J60035 dark 0.9 µA → 0.04 % gain; 8 mV at 7.5 µA). Firmware can correct with IMON_CH. Signal current at 2000 s⁻¹ × 15 p.e. is 14 nA — irrelevant | calculated (T8) |
| Output noise / ripple | section 3.3 | — |
| Total current monitor | BIAS_IMON = 8.0 mV/µA (0.8 × 10 kΩ), 250 µA full scale at 2.0 V; includes the two dividers (24 + 6 µA at 60 V, known from the voltage) and the mirror bias; ±5 % (*datasheet* 0.76–0.84 for 5–200 µA) | datasheet + calculated |
| Per-channel current monitor (**new provision, spare pin PE15 = ADC4_IN2 `IMON_CH`**) | (V_TRIM − V_TRIMDRV)/4.99 kΩ through an 8:1 mux addressed by MON_MUX_A[2:0]; 0.15 µA per ADC LSB at 3.0 V/12 bit. Gives the per-lane BIAS_OUT_OF_RANGE that firmware CR-H6 says is missing, light-leak detection per channel, and Σ(channels) vs. BIAS_IMON = leakage on a damp board | calculated |
| Current limits | 2.0 mA total (TPS61391 ISHORT 49.9 kΩ, *datasheet* point) → worst-case dissipation in the SiPMs 2 mA × 60 V = 120 mW. Per channel a soft limit: when I > V_TRIM/4.99 kΩ (0.2–0.5 mA) the trim buffer runs out of range, the anode rises and the overvoltage collapses | datasheet + calculated |

### 5.2 Compensation law and fault limits

`V_bias(T) = V_br(T0) + β·(T − T0) + V_ov`, evaluated per lane from the NTC on the SiPM carrier (10 kΩ, in the lane auxiliary pigtail); the common part moves HV_SET, the per-lane difference moves the trims.

| device | V_bias 25 °C | −25 °C | +40 °C | gain change uncompensated %/°C | inside 20–60 V |
|---|---|---|---|---|---|
| J60035 @2.5 V | 26.95 | 25.88 | 27.27 | 0.86 | yes |
| J60035 @6 V | 30.45 | 29.38 | 30.77 | 0.36 | yes |
| S14160-6050HS | 40.70 | 39.00 | 41.21 | 1.26 | yes |
| S13360-6050 | 56.0 (53 ± 5 + 3) | 53.3 | 56.8 | 1.80 | **only for V_br ≤ 56.5 V**: the upper tail of the ±5 V lot spread needs 61.8 V |
| NUV-MT @12 V | 44.50 | 43.00 | 44.95 | 0.25 | yes |

Residual gain error budget (*calculated*, per °C of temperature knowledge error): 0.25–1.8 %/°C from the table. Contributions: NTC interchangeability ±0.5 °C class (*assumed* part), sensor-to-junction gradient and lag on a carrier we have not seen (*assumed* ≤ 1 °C steady, the lag is unknown until the OEM drawing exists), β tolerance (measure per device type), set-point resolution (0.024 %), IR drop (≤ 0.1 % if uncorrected).
Budget: **≤ 2 % gain for S14160-class, ≤ 3 % for S13360, ≤ 1 % for J-series at 2.5 V** with ±1 °C; the test is B9 (LED pulser or source peak vs. head temperature over the heater cycle).
Sensor placement: on the SiPM carrier (supplier), not on our board; two TMP117 on the board rear edge and one NTC at the bias converter are references only.

Protection straps — **fit for the installed SiPM family before the first bias-on**; rev A is populated for the lowest-breakdown candidate so that an unconfigured board cannot over-bias it:

| SiPM family | HV_RAW strap (boost feedback bottom) | boost output | highest regulated bias (≈ HV_RAW − 5.5 V) | OVP strap | OVP trip |
|---|---|---|---|---|---|
| onsemi J/C (V_br 24.5 V) — **fitted** | 71.5 kΩ | 37.1 V | 31.6 V | 7.15 kΩ | 31.5 V |
| Hamamatsu S14160 | 53.6 kΩ | 49.1 V | 43.6 V | 13.0 kΩ | 42.8 V |
| Broadcom NUV-MT | 49.9 kΩ | 52.7 V | 47.2 V | 16.9 kΩ | 47.5 V |
| Hamamatsu S13360 | 40.2 kΩ | 65.1 V | 59.6 V | 40.2 kΩ | 60.6 V |

(*calculated*: 1.2 V × (1 + 2.14 MΩ/R); 25.22 × 3.0 V × R/(10 kΩ + R).) A shorted pass transistor therefore applies at most HV_RAW − 2.5 V, and the comparator then removes the boost.

Sequencing and interlocks (hardware, independent of firmware):
* The boost is enabled only by `HV_ON = PERMIT AND HV_EN`. PERMIT is a latch set by a rising edge of HV_EN and held cleared while any of: bias over-voltage, +5V_A below 4.60 V (front end unpowered), lid switch open or unplugged. After a trip the MCU must lower and raise HV_EN with the cause gone.
* Off state: pass gate pulled to ground, 47 kΩ bleeder (0.4 s), and the integrator is preset high so that the bias rises under loop control at turn-on (no overshoot toward HV_RAW).
* Light-leak interlock: `J2201` (2-pin) takes a normally-closed lid/housing switch; a solder jumper bypasses it for bench work. A light leak with the lid nominally closed shows as BIAS_IMON / IMON_CH out of window → SATURATED.
* Power-down: +5V_A falling clears PERMIT before the op-amps lose regulation; HV_EN has a pull-down, so an MCU reset removes the bias.

## 6. Saturation handling end to end

1. **SiPM**: total current limited to 2.0 mA; per-channel soft limit through the trim sense resistor; the ISHORT limit also bounds the charge-up current at turn-on.
2. **Input**: BAV99 clamp at the anode (to ground and +5 V), 22 Ω into the preamp; a shorted SiPM dumps ≤ 1.1 µF × 60 V through 100 Ω + R_IN — the clamp and R_IN (2 × 0603) take the pulse (*calculated* peak 0.55 A for ~100 µs; resistor pulse rating *UNVERIFIED*).
3. **Preamp / shapers**: recover in ≤ 1 µs (fast) and ~100–200 µs (slow baseline) after the largest alpha, section 2.3.
4. **Comparator stuck high** (light leak, oscillation, baseline above threshold): the raw LLD line stays high; firmware waits for low up to its maximum hold, then flags the chain saturated and clears.
5. **Live fraction**: measured; below the configured limit (recommend 0.5) the chain reports `SATURATED` with null counts.
6. **Bias current**: BIAS_IMON (total) or IMON_CH (per channel) outside its window → `SATURATED` / `BIAS_OUT_OF_RANGE`, null counts; persistent over-current → firmware drops HV_EN. Hardware over-voltage → PERMIT cleared, BIAS_VMON reads ~0 → all lanes null.
7. Nothing in the chain can produce authoritative zeros from a dead front end: a channel with no bias or no +5V_A gives no BUSY edges *and* an out-of-window bias current/voltage, which firmware must treat as fault, not as zero counts (the latch self-test line proves the digital half; the pulser proves the analogue half).

## 7. Test and monitor provisions

| Provision | Detail | Evidence |
|---|---|---|
| Charge-injection pulser | per channel: 74LVC2G53 switches a 100 pF 1 % C0G capacitor between ground and PULSER_AMPL (U_DAC1 OUT6); strobe = TIM8_CH1 (PC6); channel selected by PULSER_A[2:0] (firmware spare pins PF2, PF9, PF10 → 74LVC138). Q = 100 pF × V: 250 pC full scale = 538 p.e. (J60035), 0.13 p.e. per DAC LSB; stray capacitance ~0.5 pF and 1 % tolerance → ±1.5 % charge accuracy. DNP 1 nF footprint for 2.5 nC | calculated (T11) |
| Pulser limitation | the return edge injects the opposite charge 1 strobe-width later (through 100 Ω); negative pulses do not fire the comparators but the strobe must stay high ≥ 20 µs for alpha-scale tests | by design |
| Latch self-test | LATCH_TEST (PE14) OR-ed into all 20 latch clocks | contract |
| LED pulser (optional) | per lane: 100 pF charged to V_LED (2 × U_DAC0 OUT7, 0–5 V) dumped through the LED by a BSS138 on LED_STROBE (firmware spare PC12); pins 3/4 of the lane auxiliary connector | by design; light output not calculable without the LED |
| Monitor mux, 50 Ω output, ADC path | section 2.4 | — |
| Bias monitors | BIAS_VMON, BIAS_IMON, IMON_CH | section 5 |
| I²C expander (optional for firmware) | TCA9534 at 0x20: MON_EXT page bit, PERMIT, inhibit bus, lid state, eFuse fault, board revision | by design |

Test points and expected values (bare 1 mm pads; `circuit.py` lists all 43):

| Pad | Expected |
|---|---|
| VIN_F | bus voltage − ≤ 0.1 V |
| +5V6 / +5V_A / +3V3 / +3V3_EVT / VREF_ADC | 5.63 ± 0.11 V / 5.00 ± 0.10 V / 3.30 ± 0.07 V / 3.30 ± 0.07 V / 3.000 ± 0.006 V |
| VBL | 0.600 ± 0.004 V |
| HV_RAW (bias on, J strap) | 37.1 ± 1.0 V |
| HV_BUS | 25.0 × HV_SET ± 0.2 V before calibration; < 1 V within 2 s of bias-off |
| HV_SET | DAC code × 0.61 mV |
| HV_DRV | 0.7–1.6 V in regulation; ~5 V when off |
| BIAS_VMON / BIAS_IMON | HV_BUS/25.22 / 8.0 mV per µA (≈ 0.2–0.4 V with dividers only) |
| HV_INH_N / HV_PERMIT | high when no inhibit / high after HV_EN rising edge |
| `Fn PRE`, `Rn PRE` (through 453 Ω) | baseline 0.60–0.63 V; 0.76 mV per p.e. (J60035) |
| MON_BUS | MON_LANE_EN = 1: 0.98 × selected node (FAST baseline 0.60 V ± 20 mV); MON_LANE_EN = 0 (S3): 0.300 V + V(FRAME)/2 (frame monitor) |
| PULSER_AMPL / PULSER_STROBE / LATCH_TEST | DAC code × 0.61 mV / logic |
| HTR_SW / HTR_GATE | 0 V off (0.26 mA test current into 4.8 Ω), bus voltage on / bus − 7 V on |
| EF_IMON | eFuse current monitor (scale per datasheet, *UNVERIFIED*) |

## 8. Power budget (T10)

| Rail | Source | Loads | I typ / max mA | Dissipation typ / max |
|---|---|---|---|---|
| HEAD_PWR 10–15 V (9 V brown-out) | J1.1/J1.2 | TVS SMBJ16A, CM choke, TPS26600 eFuse (150 mΩ), π filter | 93 @12.8 V / 234 @9 V | ≤ 15 mW in the eFuse |
| +5V6 pre-regulator | LMR51606 buck, 1.1 MHz forced PWM | three LDO branches | 184 / 299 | efficiency 88 % typ / 82 % min (*assumed*, datasheet-class) |
| +5V_A | 10 µH/22 µF + TPS7A2050 | 16 OPA838, 5 OPA836, 6 dual op-amps, 4 DACs, muxes | 39 / 53 | 24 / 33 mW |
| +3V3_EVT | 10 µH/22 µF + TLV76733 | 20 comparators, latches, gates | 67 / 108 | 156 / 252 mW |
| +3V3 (+3V3A through a bead) | TLV76733 | MCU at 144 MHz (45/70 mA *assumed*), bias boost input, isolator logic side, sensors | 78 / 138 | 182 / 322 mW |
| HV | TPS61391 from +3V3 | dividers 30 µA, SiPM dark current 10–70 µA, mirror bias | < 0.25 | ≈ 60 mW from the 3.3 V rail (included above) |
| BUS_5V (isolated side) | J2.3/J2.4 from the chassis | ISO1430 bus side: ~60 mA while driving 60 Ω, < 10 mA idle (*UNVERIFIED*) | not in the head total | contract limit 150 mA |
| Heater | J1.3/J1.4 | 4.8 Ω element | 2.5 A @12 V, 3.1 A @15 V | section 9 |

**Total at J1 pins 1/2: 1.20 W typical, 2.10 W maximum** (*calculated* from datasheet quiescent currents and an assumed MCU current) against the 5 W target and 10 W limit.

* Brown-out: eFuse UVLO 8.8 V rising / 8.0 V falling (*calculated* from the datasheet thresholds); the buck regulates down to ~6.3 V input, so every rail is in regulation at 9 V; below 8.0 V the eFuse opens, +5V_A collapses, PERMIT clears (bias off), the MCU resets through its own brown-out reset and boots with a fresh boot UUID.
* Inrush / hot-plug: only 100 nF sits on the cable side of the eFuse; the 35 µF behind it is charged with the eFuse dV/dt control (22 nF; resulting slew *UNVERIFIED*, set at bring-up for ≤ 0.1 A inrush); TVS 16 V stand-off / 26 V clamp, all downstream parts rated ≥ 50 V; reverse polarity is blocked by the eFuse (to −60 V, *datasheet*). Current limit 1.0 A (12 kΩ), below the chassis 1.5 A branch limit.
* J1 extension drop (ICD: 0.125 Ω round trip for 0.5 V at 4 A): the electronics pair carries ≤ 0.25 A → ≤ 31 mV. The heater pair carries 3.1 A → 0.39 V, but only in the heater conductors and return, which is why DEC-025 split them.
* Common-mode choke: both electronics conductors pass through it, so the board ground is J1 pin 2 through 50 mΩ-class winding resistance (*UNVERIFIED* part data); the presence resistor and TVS sit on the cable side.

## 9. Heater

| Item | Design | Evidence |
|---|---|---|
| Element | 4.8 Ω → 30.0 W at 12.0 V (allocation), 34.1 W at 12.8 V, 44.4 W at 14.6 V, **46.9 W / 3.13 A at 15.0 V**, 20.8 W at 10.0 V | calculated (T9) |
| Duty for the thermal model (16 W at −20 °C, 19 W at −25 °C) | 53 % / 63 % at 12 V; **77 % / 91 % at 10 V** — at end of discharge the −25 °C case has 9 % margin | calculated |
| Switch | P-channel SUD50P04-08 high side on HEAD_HTR_P; gate driven through 47 kΩ with a 10 nF Miller capacitor: ≈ 0.6 ms turn-on, ≈ 3 ms turn-off (asymmetric, plateau voltage *assumed* 3 V) | calculated |
| Switching loss | ≈ 50 mJ per on/off cycle at 12 V → 50 mW at 1 Hz, 0.5 W at the 10 Hz worst case | calculated; SOA check against the datasheet curve open |
| Current sense | 10 mΩ shunt + INA180A2: 0.5 V/A → 1.56 V at 3.13 A on HTR_SENSE | calculated |
| Independent cut-out | bimetal thermostat on the heater assembly in series on the **low side** of the element (heater connector: HTR_SW, HTR_RET, CUTOUT_SENSE, NTC, NTC_RTN); cannot be overridden by any electronics | by design; part and trip temperature belong to head mechanical |
| Status read-back | a 0.26 mA continuity current flows through element and cut-out when the switch is off. HTR_CUTOUT_OK is high only if the heater feed is present **and** the element/cut-out junction is at return potential, in both switch states; open element shows as zero current when on | by design |
| Gate-synchronous switching | HTR_EN (PB15) is changed by firmware only in the service interrupt after a gate boundary; hardware adds the slew limit | contract |
| Fault behaviour | MCU reset → off (pull-down); NTC open/short → firmware off + thermal fault; switch shorted → cut-out; over-current → chassis 4 A branch limit (the head has no heater eFuse; the P-FET is not current limited) | by design |
| Coupling estimate | section 3.3 rows "heater" | calculated with assumed geometry |
| Heater domain vs frame / ground (S3, review M5, m5) | **Electrical requirement (to head mechanical / BOM):** heater films, the bimetal cut-out (case and terminals) and the regulation NTC (lug) must be insulated from the spreader: cut-out with an electrically isolated case, ≥ 100 MΩ case-to-terminals at 100 V (stated in the BOM line), NTC with an isolated lug or both on a 0.1 mm polyimide pad. Without it, a cut-out case or film edge touching the spreader returns up to ~1.2 A of heater current through the frame bond and the In1 plane (2-4 mV gradient, 0.3-0.6 p.e. threshold steps per heater edge). Circuit measure (S3-03): 0.5 A fuse F2801 in series with the bond (opens on a feed-side fault before L2001 or the plane are overloaded; limits a return-side sneak to ~0.24 A) and a frame-potential monitor on the idle MON_BUS (MON_ADC = 0.300 V + V(FRAME)/2: return-side contact ≈ +35-45 mV, feed-side contact after the fuse opens up to ~3.5 V clamped). Other heater-domain links to ground (m5): gate driver 47 kΩ → Q2602 (≈ 0.2 mA while on), R2610 100 kΩ + R2611 33 kΩ into +3V3 through D2603 (≈ 50 µA whenever the feed is present and the cut-out closed; it back-powers +3V3 when the head is unpowered), and the film capacitance 9-18 nF to the spreader; all harmless for counting. Not a heater-to-frame check: comparing HTR_SENSE with the chassis INA3221 HEAD_HTR channel (review M5 item 3) - both shunts are in the FEED (R2601 before Q2601; chassis R_SH3 high side), so a sneak return changes neither | by design |
| Bench test B10 | 10⁴ heater transitions while counting dark at 3 p.e. and with the pulser at 10 p.e.: counts in transition gates vs. neighbours agree within 3 σ; +5V_A and FAST monitor scoped, no step > 0.5 mV at FAST | — |

## 10. Condensation and cold

* Coating: conformal coat (acrylic or urethane, 25–75 µm) on the whole top side after bring-up selections are final. Keep-outs: U.FL, JST GH and Micro-Fit contact areas, TC2030 pads, test pads used in production test, mounting-hole pads, the lid-bypass solder jumper. The bottom side carries no parts; coat it too (it faces the spreader through a 0.25 mm film).
* HV creepage when damp: 62.5 V maximum. Rule used: **1.5 mm** between HV-class copper and anything else on outer layers, ground guard ring around each per-channel filter and the HV_BUS feed, no HV on the bottom layer, coating over all of it. (IPC-2221B asks 0.6 mm uncoated / 0.13 mm coated for 51–100 V — *UNVERIFIED* recall.) Breakdown is not the issue at 60 V; leakage is: 1 µA across a wet gap is 1 mV on a channel and corrupts the current monitors. The guard rings turn surface leakage into "BIAS_IMON − Σ IMON_CH", which firmware can watch as a dampness indicator.
* The ICD asks that bias is not applied when moisture could invalidate operation: firmware gate on dew-point margin is not possible without a humidity sensor (none fitted; one I²C footprint could be added in rev B if the trials ask for it).
* Temperature grades: all ICs on the board are −40 °C or better by family (*datasheet* for the TI parts opened; STM32G474VET6 is the −40…+85 °C "6" grade). Exceptions and unknowns: JST GH connectors −25 °C (*UNVERIFIED*); X5R capacitors lose capacitance cold (bulk only); LEDs −30 °C class (*UNVERIFIED*); TCXO grade *UNVERIFIED*; **the SiPM itself for Broadcom NUV-MT and Hamamatsu S13360 is rated only to −20 °C**. The board normally sits above the heated spreader at about +10 °C.

## 11. Bench verification list (referenced above)

B1 rails and sequencing · B2 latch self-test and pulser counting, live-time vs. rate sweep to 10⁵ s⁻¹ · B3 threshold/baseline scans per comparator · B4 pulser linearity and charge calibration, Ct from the pulser decay ·
B5 bias accuracy, step response, ripple, OVP/PG/lid trips · B6 crosstalk · B7 alpha recovery and afterglow (Am-241) · B8 digital activity vs. dark rate · B9 gain vs. temperature with compensation ·
B10 heater transitions · B11 conducted susceptibility on HEAD_PWR, motors · B12 light-tightness / cover. Sequence and stop conditions: `electronics/head_acq/design/layout_guidance.md` §7.

## 12. What threatens the design, in order

1. **Beta light yield vs. dark-limited threshold** (3.2): unknown by a factor of 30; the board can only choose shaping, overvoltage and temperature.
2. **SiPM capacitance / array size**: covered by R_IN, pole-zero and gain resistors; a 4 × 6 mm array costs threshold (+3 p.e. at +10 °C) and noise.
3. **Breakdown spread across the 8 devices > 2.4 V** (S13360 lots): not coverable; must be a purchasing requirement.
4. **S13360 with V_br > 56.5 V** or NUV-MT above +14 V overvoltage: outside the 60 V range.
5. **ZnS afterglow** retriggering the beta channel after alphas: handled by firmware hold, magnitude unknown.
6. **Temperature sensor lag on the supplier's carrier**: sets the residual gain error for the high-β devices.

## 13. Stage 3 corrections (2026-11-27, after `docs/reviews/REVIEW_head_interference.md`)

| Review item | What was wrong here | Now | Where |
|---|---|---|---|
| C1 | alpha channel "cannot be confused" | TOT discriminator with per-device cut (gaps 130-170 ns); amplitude-ratio option; no new pin in rev A | 2.5, T13 |
| M1 | LLD at the 1 s⁻¹ dark criterion | ≤ 0.05 s⁻¹: LLD 10 (typ) / 11 (max) p.e. for J60035 at +10 °C; RFQ ≥ 18 p.e. at the MPV at the worst point | 3.2, T6, T17 |
| M2 | monitor taps 1 kΩ at the comparator inputs, one lane mux always on | 10 kΩ at op-amp outputs; MON_LANE_EN off state | 2.4, 3.3, T15 |
| M3 | "bonded at one DC point at H1 and by four 10 nF" - not as placed | placed and pre-routed at H1/H2/H5/H6/H8; CM path stated | 3.4 |
| M4 | 1 A/100 ns motor-lead aggressor, "≈ 10 p.e." | physical aggressors; coax independent of pigtail length; brush arc 2.8 / 0.11 p.e. | 3.4, T16 |
| M5 | heater domain links listed incompletely, no frame-fault detection | insulation requirement, fuse + frame monitor | 9 |
| M6 | (board stack-up) | F / GND / sig / PWR / GND / B | `electronics/head_acq/README.md` |
| m2 | "suppressed by ~10⁻⁴" | wrong; C_PZ 47 nF; trim-node tail found | 2.3, T14 |
| m3 | "J2 side galvanically isolated" | DC only; four HF paths | 3.4 |
| m4 | monitor 10-15 MHz | 0.1-0.3 MHz (baseline monitor) | 2.4 |
| m5 | heater-ground links | complete list | 9 |
| m7 | DACs written only when disarmed | HV_SET tracking writes while armed (harmless, B8 with tracking) | 3.3 |
| IB-58 | read-back divider 0.1 %; ramp meaning | 1 % (calibrate); 5 V/s at HV_BUS | 5.1 |

Where this file and the review disagree (with the calculation): T16 brush arc 2.8 p.e. open / 0.11 coax (review ≈ 20 / 0.6: no preamp bandwidth); T13 weakest
J60035 alpha 374 ns (review ≥ 280 ns); T14 post-alpha tail lasts beyond 300 µs without C_PZ because of the trim node (review: zero crossing at 314 µs); T17
plate-average mean ≈ 51 p.e. for the worst-point requirement under ±50 % non-uniformity (review ≈ 30).
