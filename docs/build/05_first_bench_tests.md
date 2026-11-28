# 05 First bench tests: observation sheets

**Updated 2026-11-28** after the independent interference and data-path reviews (`docs/reviews/REVIEW_head_interference.md`, IB-67; `REVIEW_head_data_to_map.md`, IB-72), head electronics stage 3, head firmware 0.6.0 and the registers (VT-049 to VT-081). The review finding M7 states that the earlier count-rate-delta tests (T5 in its first form) **cannot expose most coupling mechanisms**: sheets T12 to T14 add the missing measurements. **Status.** None of these tests has been run. Every pass criterion is a design value, a calculation or a simulation, quoted with its source; where a source says the acceptance limit is to be set by someone, the sheet says so. A test that fails does not change the criterion: record the failure and take it to the owner of the source named (section "What a failure most likely means" is my interpretation of the source's own analysis, labelled as such). Tests marked "proposed sheet" have a procedure in the sources but the record layout is mine.

Common header for every sheet (copy once per run): run ID ______  date ______  operator ______  head ID/serial ______  board revision ______  firmware version string (from the boot banner or `STATUS`) ______  `setup_id` (head) ______  `boot_id` ______  ambient / head / SiPM temperature (degC) ______ / ______ / ______  supply voltage at the unit (V) ______  source ID and calibration date (if any) ______ (sources only under the site's radiation-protection controls)  fixture / harness IDs ______  notes ______.

`planning/detector_bench_runs.csv` is the project's blank data-entry layout for lane-level runs (one row per physical lane per acquisition interval: run, head, boot, lane index, standoff, counts, live times, temperatures, heater power, motors state, quality flags, harness length, traction-inhibit verified). Use it for T2, T3, T5, T6 as the archive record; the sheets below are the bench notebook.

**Lab grounding and probing (review M7 item 9; record on every head sheet):** the scope earth on J2701 or the PRE pads, a debug-UART adapter on J2402, SWD and a dark-box metal each add an earth connection to head GND. State on every sheet whether the scope was isolated or differential, the probe type and where its earth went, whether a debug adapter or ST-LINK was connected, whether the dark box was bonded to anything, and whether the head ran from the chassis, a bench supply or the LAB extension. Do the threshold scans of T1/T2 with the lane monitor parked (MON_LANE_EN = 0) and the anode-current scan frozen, and take the single-p.e. spacing from the PRE pads or the threshold scan, not from J2701 (review m4).

Lane numbering: lanes 0 to 3 run from the robot's left to right facing the direction of travel (RFQ 0.4); floor chains F0 to F3 and reference chains R0 to R3.

| Test | Title | Requirement / VT | Needs |
|---|---|---|---|
| T1 | SiPM breakdown, bias and dark-count threshold scan | VT-043, VT-042 | optical lane, RR-HEAD-ACQ, dark box, temperature chamber |
| T2 | Beta photoelectron yield | VT-042, RQ-063 | T1, Sr-90/Y-90 or Tl-204 source |
| T3 | Alpha/beta discrimination and post-alpha hold | VT-010, VT-044 | Am-241 source, T1 |
| T4 | Live-time and dead-time check with a pulser | VT-037, RQ-053 | RR-HEAD-ACQ with firmware |
| T5 | Motor-PWM pickup into the front ends (bench test B11) | VT-041, RQ-062, RQ-032 | head on the robot |
| T6 | Heater switching: counts versus heater transitions (bench test B10) | RQ-081, VT-011, VT-014 | T1 |
| T7 | Heater power versus temperature in a cold box | VT-013, RQ-072, IB-39 | head, chamber |
| T8 | Stop distance and brake check | VT-003, VT-045, VT-005 | robot, guarded rig |
| T9 | ToF cliff and look-sensor response | VT-004 | IB-04 closed |
| T10 | Head gap and film-plane measurement | RQ-015, RQ-018, VT-032, E4 | bench cradle / dummy head |
| T11 | USB and RS-485 link error rates | `chassis_design_review_checklist.md` E, VT-019, VT-046 | both boards |
| T12 | Averaged waveform at the comparator input, triggered on each aggressor | VT-049, VT-063, VT-078 | head on the robot, averaging scope |
| T13 | Cable common-mode injection and lab grounding set-up | `REVIEW_head_interference.md` M7 items 5, 9; VT-049 | current clamp, head counting |
| T14 | Heater-circuit insulation, frame bond and frame monitor, cut-out event | VT-062, VT-079, VT-071; head checklist E1, E2 | assembled head |
| T15 | Re-arm set stage and the per-shift / six-monthly service-test record (P1, S3 to S8) | VT-053, VT-080, VT-081; `chassis_safety_chain.md` section 6.2 | chassis board |
| T16 | Receiver thermal break, pack-to-body coupling and bay pre-heat | VT-058, VT-059, VT-060 | chamber, robot body |

## T1 SiPM breakdown, bias and dark-count threshold scan

**Purpose.** Find each SiPM's breakdown voltage and the spread across the eight devices; fit the straps; set the device type; measure the dark trigger rate versus threshold, and find the lowest usable BETA_LLD for the dark-rate criterion of **at most 0.05 per second per chain** (10 % of the radiometry beta-window background of 0.5 per second; the former 1 per second criterion is withdrawn: `head_afe_budget.md` section 3.2, RFQ section A, VT-051).

**Setup.** One real optical lane (later all four) connected through coax to RR-HEAD-ACQ, lid closed, in the dark box. Bring-up (04 stage B2 steps 0 to 13 and the stage-3 additions) must have passed. Bias off before touching the pigtails (head review B14). **Set the device type (`device`) before ARM; ARM is refused with `device_type_unset` / `placeholder_thresholds` until the device and thresholds are set or confirmed** (VT-077); changing them changes `setup_id`. Threshold scans are a host procedure over `ENG_SETUP_SET` (each change a new `setup_id` and a new handshake; no on-head scan op). Bias range 20 to 60 V (62.5 V hardware full scale); trip 31.55 V as fitted (set-points above 30.5 V refused until the straps are changed). Temperature chamber for **+25, +10, +5 (operating set-point) and 0, -20 C**. Lane monitor parked, anode-current scan frozen, lab grounding recorded (above).

**Record.**

| Quantity | Unit | Lane 0 F | 0 R | 1 F | 1 R | 2 F | 2 R | 3 F | 3 R |
|---|---|---|---|---|---|---|---|---|---|
| Breakdown voltage V_br (sqrt-current intercept, I-V sweep at 10 uA limit) at ______ degC | V | | | | | | | | |
| V_br at second temperature ______ degC | V | | | | | | | | |
| Temperature coefficient (dV_br/dT) | mV/degC | | | | | | | | |
| TRIM_DAC code to equalise | LSB | | | | | | | | |
| Operating overvoltage chosen | V | | | | | | | | |
| Dark current at the operating point (IMON_CH) | uA | | | | | | | | |
| BIAS_VMON calibration factor (written to `bias.vmon_ratio_e4`) | ratio | | | | | | | | |
| Single-p.e. spacing at FAST | mV per p.e. | | | | | | | | |

Dark trigger rate versus threshold (one table per temperature and per chain; LED off, lid closed, at least 100 s, and long enough that 0.05 per second is resolved: about 20 events need 400 s):

| BETA_LLD / REF_LLD (DAC code) | Threshold (p.e.) | Counts | Live time (s) | Rate (1/s) | Notes |
|---|---|---|---|---|---|

Derived: lowest threshold with a dark rate of at most 0.05 1/s: ______ p.e. at +25 / +10 / +5 / 0 / -20 C. Measured temperature law (replaces the assumed halving every 8 C): ______.

**Pass criterion and source.**

- Spread of V_br across the eight devices within the anode trim range, **2.0 V** (stage-2 decision S2-06/IB-25; trim range 2.4 V less 0.4 V reserve; VT-043); no device above 56.5 V (S13360 family).
- **Calculated lowest usable threshold at a dark rate of at most 0.05 per second** (`head_afe_budget.md` T6, `calculated` from datasheet dark rate and crosstalk with an **assumed** halving per 8 C, good to about +-1 p.e.; RFQ section A table): one 6 mm MicroFJ-60035 at +2.5 V: **10 p.e. typical, 11 p.e. maximum dark rate at +10 C** (11/13 at +25 C, 9/10 at 0 C, 8/9 at -20 C); one 3 mm 9/10 at +10 C; S13360-6050PE 7/8; four 6 mm in parallel 12/15; +6 V overvoltage 26/29. The value at +5 C is "not stated" in the sources (below the +10 C value by assumption). The default LLD of the firmware is 10 p.e. for the J60035; **the value for the 11 p.e. maximum-dark case is not applied by default; a person decides** (`firmware/head/README.md`).
- VT-051: lowest usable threshold found per chain with a dark rate of at most 0.05 1/s; beta efficiency at the worst plate point at least 90 % with that threshold (RQ-063 basis); the measured temperature law replaces the assumption.

**What a failure most likely means** (interpretation of `head_afe_budget.md` sections 3.2 and 12). Measured threshold well above the calculation: more crosstalk or overvoltage than assumed, a light leak (repeat E1), pickup (T12), or a different dark rate law. Dark current above the datasheet range: light leak or wrong strap. V_br spread above 2.0 V: needs matching at purchase (RFQ section D).

## T2 Beta photoelectron yield (the key detector risk)

**Purpose.** Measure the photoelectrons per beta event at the SiPM and decide whether the beta channel works at all. The requirement is no longer the earlier assumed 4 to 120 p.e. (15 typical): **at least 18 p.e. at the most-probable (MPV) energy deposit of a normally incident minimum-ionising particle, at the worst point of the 80 x 100 mm active plate, at +10 C and the stated overvoltage, with a position map of at least 9 points (corners and centre)**, and the plate-average mean is compared with the calculated about 51 p.e. (RFQ section A; VT-042; RQ-063; calculated basis: 90 % efficiency at the 10 to 11 p.e. threshold from the 0.05 per second dark criterion, MPV = 0.7 x mean, MicroFJ-60035, +-50 % light-collection non-uniformity assumed). The independent review asked for at least 15 p.e. (about 30 p.e. mean); the two figures differ (C-07).

**Setup.** One real optical lane on RR-HEAD-ACQ; Sr-90/Y-90, Cl-36 or Tl-204 source under site control, fixed geometry at the 10 mm standoff, **moved over at least 9 plate points**; the 50 ohm monitor output on a scope; BETA_LLD scan by `ENG_SETUP_SET` steps; temperature chamber at +10 C and +5 C; dark scans from T1. Waveform capture is not in the STM32 port: use the monitor output and the threshold scan.

**Record.**

| Quantity | Unit | Value |
|---|---|---|
| Source, nuclide, activity, reference date, geometry, source-to-film gap | | ______ |
| Single-p.e. calibration | mV per p.e. | ______ |
| Plate point map: yield at the MPV for points 1 to 9 (corners, edge midpoints, centre) | p.e. | ______ |
| Plate-average mean yield | p.e. | ______ |
| Worst-point MPV yield | p.e. | ______ |
| Lowest usable BETA_LLD (T1, same temperature) | p.e. | ______ |
| Beta efficiency at the worst point with that threshold | fraction | ______ |
| Reference-tile yield (Cs-137 or ambient spectrum, REF_LLD scan; assumed 10 to 600 p.e.) | p.e. | ______ |

**Pass criterion and source.** VT-042: worst-point MPV yield at least 18 p.e. at +10 C; efficiency at the worst point at least 90 %; if not, change overvoltage, set-point, device or optics **before ordering four lanes**. Calculated beta efficiency at LLD 10: 0.68 at 10 p.e., 0.88 at 15, 0.95 at 20, 0.99 at 30 (T17). RQ-063's margin to be confirmed.

**What a failure most likely means.** Yield below 18 p.e.: light collection or optical bond poorer than assumed, plastic or ZnS thickness giving less light, gap or window attenuation. The levers are overvoltage (high overvoltage costs a factor of two or more in threshold), head temperature (the dark rate falls with temperature, so +5 C is on the safe side for dark counts but the optics supplier's bond-line limits at +5 C are unknown), a low-crosstalk SiPM, and a different optical assembly (RSK-019).

## T3 Alpha/beta discrimination (time-over-threshold cut), post-alpha hold and afterglow

**Purpose.** The alpha decision is no longer the ALPHA latch alone: a bright beta can cross the slow-path alpha threshold (a fast pulse of 81 p.e. or more at the assumed levels; review C1, IB-67), so the firmware (0.5.1 onward) requires a **time over threshold of the slow comparator of at least a per-device cut** for alpha (`afterglow.alpha_min_tot_ns`; 290 / 180 / 215 / 190 / 200 / 655 ns for J60035 / J30035 / S14160 / S13360 / NUV-MT / 4 x J60035, `calculated` on an **assumed 200 ns ZnS decay**, T13 `head_afe_calc_out.md`). **The cut must be set from Am-241 and Sr-90/Y-90 time-over-threshold histograms** (VT-050); with the J60035 numbers it leaves 84 ns to the weakest alpha (374 ns) and 88 ns to the brightest beta (202 ns), about 12 capture ticks each side. The beta-window class is defined by this cut in both chains and calibrated in that definition (MODEL.md revision 5, `rrrad`).

**Setup.** Am-241 alone, then Sr-90/Y-90 alone, at the window at fixed standoff; operating threshold; monitor output on a scope; the TOT histogram per chain per gate in DIAG (4 bins, edges 150, 400, 2000 ns) and the finer capture width (6.94 ns tick, falling edge capture; valid to about 340 us); `GATESTAT` per gate (`alpha_short`, `alpha_ambig`, floor rejects). Repeat at the +5 C set-point and at +25 C, and again if the SiPM device or the ZnS layer changes. Post-alpha hold: 300 us default (150 us possible); pulser at 2.5 nC (C_INJ2) and Am-241 for the baseline tail.

**Record.**

| Quantity | Unit | Lane 0 | 1 | 2 | 3 |
|---|---|---|---|---|---|
| TOT of the Am-241 population: lower edge, median | ns | | | | |
| TOT of the Sr-90/Y-90 population: upper edge, median | ns | | | | |
| Gap between the populations | ns | | | | |
| Cut chosen (`alpha_min_tot_ns`, mid-gap) and effective cut (STATUS `alpha_tot_ns`) | ns | | | | |
| Alpha-class events per 10^6 beta-window events, Sr-90/Y-90 alone | ratio | | | | |
| `alpha_short`, `alpha_ambig`, floor rejects per gate (GATESTAT) with each source | counts | | | | |
| FAST baseline at 5, 50, 150, 300, 500 us after a 2.5 nC alpha pulse | p.e. | | | | |
| 10 p.e. pulse recovery at 20 to 500 us delay | fraction of nominal | | | | |
| Retriggers after alphas, hold on / hold off | counts | | | | |
| Dead time added by the hold (at the survey rate) | % | | | | |
| Alpha counts, beta-window counts, floor rejects for a fixed live time with Am-241 | counts, s | | | | |
| Standoff, air temperature, ALPHA / BETA_LLD / BETA_ULD codes | mm, degC, LSB | | | | |

**Pass criterion and source.** VT-050: cut at least 14 ns (2 ticks) from the edge of both populations; **alpha-class events per 10^6 beta-window events at most 1e-4 with Sr-90/Y-90 alone** (head checklist E8; radiometry to confirm; alpha background budget 0.01 per second). VT-052 and head checklist E7: criterion for the hold length is "not yet defined"; the checklist asks for the FAST baseline within 0.3 p.e. after 150 us; calculated (T14, J60035, with the 47 nF pole-zero capacitor): -0.49 p.e. at 150 us and +0.06 p.e. at 300 us after 15 000 p.e. Calculated margin of the cut against a pile-up: a bright beta followed by a second pulse before classification is never called alpha (width of the first falling edge is kept; `width_multi`): residual false-alpha rate 1.8e-4 per second at 2000 1/s, against the 0.01 per second budget up to about 14 000 1/s (calculated, not simulated). The cut is marginal on the alpha side (27 ns below the weakest assumed alpha in the review's figures, C-11).

**What a failure most likely means.** Populations overlapping: the ZnS decay time differs from the assumed 200 ns (RFQ section J asks for it), the threshold is too low or high, or the pulse shape at the SiPM differs from the model; a robust fix (capturing the slow comparator width) needs an MCU pin (rev B). Beta-window counts after alphas that vanish with the hold: afterglow retriggering. A long tail beyond 300 us: the trim-node time constant (T14).

## T4 Live-time and dead-time check with a pulser

**Purpose.** Verify the measured live time and the corrected rate against pulser truth over the rate range, and the handling of saturation. This is also bring-up step 8; here it is the quantitative record.

**Setup.** On-board charge-injection pulser (100 pF switched, Q = 100 pF x V; 250 pC full scale = 538 p.e. for J60035; 0.13 p.e. per DAC LSB; +-1.5 % charge accuracy; the return edge injects the opposite charge one strobe-width later; strobe at least 20 us for alpha-scale tests), strobed by a timer output, periodic and pseudo-random, channel selected by the pulser select lines. Floor and reference chains in turn. Rate sweep to 1e5 1/s. Exercise: a late service interrupt, a clear crossing a gate boundary, a chain held busy by a long tail.

**Record.**

| True pulser rate (1/s) | Chain | Counted rate (1/s) | Live fraction (measured, %) | Corrected rate = counted / live fraction (1/s) | Dead time per event (us) | Flags | Notes |
|---|---|---|---|---|---|---|---|
| 10, 100, 1000, 5000, 20000, 1e5 (periodic, then random) | F0 ... R3 | | | | | | |

Also: gate span (default 100 000 us); heater transition in gate (yes/no); chain flagged SATURATED at ______ 1/s (counts must read null, never zero).

**Per-gate evidence:** read `GATESTAT` (counters per gate keyed by the ACQ sequence number: forced clears, saturation cause, live per mille, gross counts) for every gate; "rate too high to count" is a low live fraction without forced clears, "stuck comparator or light leak" is forced clears. `ACQ_FAULT` is per gate now (a lost record sets it once in the next frame and clears itself; a lost gate has no frame and its floor area is not credited).

**Pass criterion and source.** VT-037: corrected rate versus pulser truth and the measured dead time compared with the **simulated reference**: within 0.5 % from 10 to 20 000 1/s, about 9.7 us per event (`firmware/head/README.md` simulated table: dead fraction 0.010 % at 10 1/s, 0.972 % at 1000, 4.67 % at 5000, 16.3 % at 20 000 before the post-alpha hold). **The acceptance limits are not stated in the sources and are set by the head electronics lead before the test.** SATURATED handling with null counts is required (RQ-053): live fraction below 50 % or a chain busy over 1 ms gives SATURATED with null counts.

**What a failure most likely means.** A systematic live-time error that grows with rate: service-interrupt latency different from the host model (unflagged blind time up to 30 us after a forced clear and a FIFO overflow if the interrupt is more than 3 gates late are known limits, IB-58); crosstalk counts on other chains at 5 p.e. equivalent: layout.

## T5 Motor-PWM pickup into the front ends (bench test B11): count-rate check

**Purpose.** The final system check that the motor states do not change the count rate. **It is no longer the pass criterion for pickup**: the interference review (M7 items 1 and 2) shows that a count-rate test at 3 p.e. has a 3-sigma resolution of about 63 per second (the dark crossing rate at 2.5 p.e. is about 4.5 x 10^4 per second), so pickup of tens of events per second passes while it could be many times the dark budget at the operating threshold, and that the shortest time-over-threshold bin (under 150 ns) holds essentially every dark and beta event near threshold (FAST FWHM 80 ns), so an excess there is not a diagnostic. The pass criterion for each aggressor is the averaged waveform of **T12**.

**Setup.** Head in the prototype plastic housing on the robot, bias on, lid closed, coaxial pigtails, lane cans and EMI cover fitted and removed; BETA_LLD at the operating threshold (and at 3 p.e. only to compare); dark. Robot on blocks; motors driven by the chassis firmware (needs M1 of 04 and IB-04), and from a DC bench supply at 100 % duty. Record the **coax pigtail length actually fitted** per lane (35 mm in the RFQ and RQ-062, 45 to 50 mm in the harness, floor 44 / 47 mm and reference 33 / 30 mm as routed in `mechanical/head/out/lead_routes.yaml`, about 60 mm in the head BOM: C-02; the stage-3 calculation says the coax case does not depend on length, `head_afe_budget.md` section 3.4).

**Record.** (pigtail lengths ____ ; cans fitted / removed ; EMI cover fitted / removed ; motor-terminal suppression fitted yes / no, with C_X ____ nF, C_Y ____ nF, strap resistance ____ ohm)

| Motor state | Threshold | Counts in 100 s | Rate (1/s) | Deviation from motors-off (sigma of a 100 s count) |
|---|---|---|---|---|
| motors off | operating / 3 p.e. | | | 0 |
| 20 kHz PWM, 0 %, 50 %, 100 % duty, free-running | | | | |
| the same, stalled at the current limit (2.5 A) | | | | |
| direction reversal | | | | |
| DC bench supply at 100 % (brushes, no PWM edges) | | | | |
| wheels back-driven with the bridges asleep (brush noise only) | | | | |
| brake relay K2/K3 transitions | | | | |
| head undocked on the J1X/J2X extension, motors running | | | | |

**Pass criterion and source.** VT-041 (as in the register, unchanged): count rate at the operating threshold changes by less than 3 sigma of a 100 s count in every motor state **and** no excess in the shortest time-over-threshold bin; given M7 this is a necessary, not a sufficient, check; the sufficient one is the amplitude in photoelectrons in T12 (VT-049, bound set by the head electronics lead). On failure: fit the cover or cans, then add chassis-side motor-terminal suppression (IB-09, N09 to N11).

**What a failure most likely means.** A rate change with duty: magnetic edge coupling into a pigtail or loop; a change only when stalled or at reversal: brush arcing or current-limit chopping; a change with the head on the extension: common-mode current in the cable shields (T13). Calculated aggressor amplitudes (`head_afe_calc_out.md` T15, T16, J60035, geometry and currents **assumed**): motor PWM 0.01 to 0.28 p.e. with coax; brush arc 0.11 p.e. coax and 2.76 open (the review: 0.6 and about 20; a factor of about 7 that only measurement decides: C-01).

## T6 Heater switching: counts versus heater transitions (bench test B10) and a cut-out event

**Purpose.** The head heater switches only on gate boundaries with a slew-limited edge; show that counts in the gate containing a transition match neighbouring gates, and that a thermal cut-out opening (a heater current interruption) does not corrupt the data unflagged.

**Setup.** RR-HEAD-ACQ with the heater on a dummy or the real film; counting dark at 3 p.e. and with the pulser at 10 p.e.; 10^4 transitions; scope on +5V_A and the FAST monitor. **Cut-out event (review M7 item 7):** heat the cut-out with a hot-air tool while counting and let it open and close. Heater over-current cut-off: with a current-limited fault load, check the firmware cut at `heater.oc_ma` 3200 mA for `heater.oc_ms` 300 ms (health `HEATER_OVERCURRENT`, flag `HEATER_FAULT`) and the chassis branch trip at 3.56 to 4.35 A (VT-071).

**Record.**

| Quantity | Unit | Value |
|---|---|---|
| Transitions performed | | |
| Mean counts per gate, transition gates / neighbouring gates; difference in sigma | counts, sigma | |
| Largest step at FAST on the scope | mV | |
| Switch edge times (turn-on, turn-off) | ms | |
| FET temperature after 100 cycles at 1 Hz | degC | |
| Data in the gate containing a cut-out opening: flags, `heater_transition_in_gate`, counts | | |
| Over-current cut: current at cut, hold time, terminal temperature rise after 1 h at the maximum heater current | A, ms, K | |

**Pass criterion and source.** RQ-081, `head_afe_budget.md` section 9: counts agree within 3 sigma over 10^4 transitions and no step above 0.5 mV at FAST; the edge is about 0.6 ms on and 3 ms off (`calculated`, plateau assumed). The gate with a transition is marked in DIAG; a mid-gate force-off gives a partial on-time and `heater_transition_in_gate` true. The pass bound for the aggressor amplitude is in T12 (heater edges). VT-071: terminal rating (manufacturer document) at least the maximum heater current plus a margin set by the head electronics lead; the Micro-Fit rating is recalled at about 3.13 A (UNVERIFIED) against a maximum draw of 3.04 A.

**What a failure most likely means.** A step at FAST: supply or ground coupling through +5V_A or the heater return; a data glitch at a cut-out opening: the transient is not flagged beyond the transition marker (the cut-out status is read by `HTR_CUTOUT_OK` only).

## T7 Heater power versus temperature in a cold box (+5 C set-point)

**Purpose.** Replace the calculated heater demand by a measured one, at the owner's **+5 C set-point at the SiPM carrier** (decided 2026-11-27; contract `power.thermal_policy.head_setpoint_c`), and compare with the delivered power; reconcile the thermal calculations (IB-39, IB-62, C-03, C-04).

**Setup.** Head in the prototype housing in the standard cold configuration (3 mm jacket RR-HD-S-131/132, 0.5 mm liner), **receiver channels on the G-10 thermal-break shim**, ambient from the chamber at +20, 0, -10, -20 and -25 C (the last a separate stretch test), still air and a 3 m/s draught; loggers on spreader, SiPM carriers, board and ambient; set-points +5 C and +10 C (comparison); current and voltage at the head (HTR_SENSE 0.5 V/A with the INA180A2 gain UNVERIFIED, and the chassis INA3221); supply voltages 10, 12 and 14.6 V at the chassis branch. Also warm-up from a -25 C soak.

**Record.**

| Ambient (degC) | Draught | Set-point (degC) | Supply at the branch (V) | Heater duty over 30 min (%) | Mean heater power (W) | Electronics power (W) | Spreader, carrier, board temps (degC) | Warm-up time to set-point (min) | Cut-out / NTC readings |
|---|---|---|---|---|---|---|---|---|---|

**Pass criterion and source.** No limit is stated; compare with the calculated values. `mechanical/head/out/head_report.md` section 9 (still air, jacket, electronics credited at the typical 1.2 W only, +5 C baseline): prototype **15.2 W at -20 C and 18.4 W at -25 C**; at 25 W/m2K 23.3 and 28.2 W; production 15.5 / 18.7 and 23.8 / 28.8 W; plus the body-side conduction (0.11 / 0.14 W/K per shoe against the 0.07 W/K assumed: +1.6 / +2.9 W at -25 C). The contract and VT-057 quote 13.8 to 14.0 W at -20 C and 16.7 to 17.0 W at -25 C (the difference is not reconciled in the sources; C-04). **Against the heater actually delivered** after wire drop: 19.9 W at 10 V and 28.7 W at 12 V (`harness/cables.md` section 6, `calculated`), margins in `head_report.md`: at -25 C in moving air the demand is above the 10 V capability (**the heater is short of capacity at 10 V, end of discharge, in moving air at -25 C**), and with conductive receiver channels and no thermal break the demand would be 43 to 66 W. Warm-up from a -25 C soak (lumped): 52 to 56 min at 30 W and 117 to 131 min at 20.8 W (head report); the RFQ text quotes 49 to 105 min. VT-014: independent zone control and protective cut-out act as designed; set-points and insulation are chosen only after measured temperature and count stability. RQ-072: the contract budget carries the measured demand or the set-point is lowered.

**What a failure most likely means.** Measured power above the table: jacket coverage, draught, the thermal break not achieving 0.081 W/K per channel (calculated, G-10 0.30 W/m K handbook, UNVERIFIED), printed-frame conductivity, body-side conduction above the assumption, or a worse pack voltage than 10 V; the head will not reach +5 C at -25 C in moving air at low pack voltage and the dark-rate criterion and the bond-line limits are then unmet (the OEM limits are unknown).

## T8 Stop distance and brake check

**Purpose.** Replace the calculated and simulated stopping distances by measurements, for every initiating element, and check the dynamic brake path.

**Setup.** Stage M1/M2 of [04_bring_up.md](04_bring_up.md): guarded floor rig, dummy head, wheel-up first and then on the floor, independent position and stop-distance instrumentation (stopwatch or acquisition trace, `VT-005` prerequisites), encoder log. Initiators: E-stop, HANDS-ON, each bumper and rail switch, head unplug (HEAD_LOOP), undock, cover open, selector out of RUN, watchdog stop, ARM_PERMIT withdrawal; software: controlled stop, protective stop, command timeout. Surfaces: the floor materials of the site (wood, steel, wet, frost): not yet defined.

**Record (one row per run).**

| Run | Initiator | Direction | Speed (m/s) | Surface | Slope (deg) | Mass (kg) | Time from initiation to NC closure (ms) | Stop distance (mm) | Yaw (deg) | Rollback after stop (mm) |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | 0.05 / 0.10 / 0.20 | | | | | | | |

Wheel-up spin-down: wheel speed at E-stop (m/s equivalent) ____; time constant with brake resistor fitted ____ ms; with resistor lifted (coast) ____ ms; rotor inertia derived ____ kg m2; friction ____ N; slope holding angle ____ deg.

**Additions (VT-056, VT-045, VT-053):** brake from 0.05, 0.10 and 0.20 m/s on the level and on slopes in steps up to 10 degrees downhill and uphill, with cold windings and with windings heated to about 100 C and after the magnets were warmed; record stop distance, creep speed after the stop and the hold angle. Calculated for comparison: from 0.20 m/s level 8.8 / 28.6 mm (nominal / conservative), with 100 C windings 9.8 / 34.2 mm (12.0 / 47.5 mm with magnet derating); MCU failure 57 mm; the braked robot stops on a downhill slope only up to about 3 to 6 degrees (half friction) or 6 to 10 degrees (nominal) and creeps beyond at 12 to 36 mm/s; **no holding brake and no hardware speed or force limit** (the pass limit on distance and slope is "not yet defined": chassis electronics and motion controls). Also check the dynamic effect of D_RUN reverse leakage hot (VT-081): if K2/K3 do not release after a drop the stop has no dynamic braking (calculated 38 to 114 mm instead of about 10 mm from 0.20 m/s).

**Pass criterion and source.** VT-003/VT-005: every authorised motion stops inside a **measured** protective margin at its declared speed; recorded stop latency meets the verified brake budget; no uncommanded restart or movement on unplug; reset needs a deliberate operator command. `calculated` comparison values: NC closure at most 10.8 ms (13.3 ms for the loop and presence elements); stopping distance from 0.20 m/s 8.8 mm nominal and 28.6 mm conservative; from 0.10 m/s 3.8 and 14.3 mm; from 0.05 m/s 1.6 and 7.1 mm; one motor braked and the other coasting 55 / 27 / 14 mm; MCU failure with full torque 57 / 39 / 30 mm (`chassis_safety_chain.md` sections 1 and 4; NC closure at most 10.8 ms, 13.3 ms for the loop channels). Simulated latch-drop distances after the plant alignment: 3.6 / 14.2 mm at 0.10 m/s, 8.5 / 28.5 mm at 0.20 m/s (IB-03). The contract stop model with its example inputs gives 100 mm at 0.20 m/s (0.15 s delay, 0.40 m/s2, 20 mm margin). VT-045: an open brake path is detected by the dynamic check. The head rail needs at least 15 mm of stroke after it trips at 0.10 m/s (RQ-061, IB-11); until measured, stopping inside the rail travel is not demonstrated.

**What a failure most likely means.** Longer than calculated: rotor inertia above the assumed 1 to 2 x 10^-6 kg m2 per motor (the dominant unpublished input), lower friction, or slip on the surface; a failed brake-resistor path (fault 46) gives the one-motor-coasting distances; a slow K1/K2/K3 release (the release times are UNVERIFIED) or a shorted coil-clamp Zener adds 2 to 3 mm at 0.20 m/s. Slope rollback: no parking brake is fitted; gearbox friction holds about 6 degrees calculated.

## T9 ToF cliff and look-sensor response

**Purpose.** Check the eleven VL53L4ED sensors and the protective-field logic: 4 downward cliff sensors, the forward look pair LOOK_FL/LOOK_FR (grip cheeks), the rearward pair LOOK_RL/LOOK_RR (tail), 3 rear proximity sensors (REAR_L, REAR_C, REAR_R). Requires the ToF driver (IB-04). The pair in the direction of travel acts; the pair partners' floor spots do not overlap (286 mm apart against about 166 mm spot forward; 217 against 85 mm rearward), so a pair-disagreement stop was removed (IB-34).

**Setup.** Robot on blocks first, then floor fixture; each sensor exposed to dark, wet, shiny and missing returns (VT-004), stale and stuck sensors injected (cover a sensor or unplug its cable), a floor-level drop simulator with physical catch for any approach test. Read `STATE.tof` (`range_mm`, `status`, `age_ms`) and `allow` / `v_cap_mps` in `DRIVE`.

**Record.**

| Sensor | Floor range (mm, nominal) | Range over dark / wet / shiny floor (mm) | Range with drop (mm) | Status | Age (ms) | Stop reason on cover / unplug | Motion refused direction |
|---|---|---|---|---|---|---|---|
| CLIFF_FL, CLIFF_FR, CLIFF_RL, CLIFF_RR | | | | | | | |
| LOOK_FL, LOOK_FR, LOOK_RL, LOOK_RR | | | | | | | |
| REAR_L, REAR_C, REAR_R | | | | | | | |

Approach tests: speed ____ m/s, direction ____, distance travelled after the first abnormal sample to rest ____ mm; floor edge margin ____ mm.

**Pass criterion and source.** VT-004: in every permitted direction all support points stay within the protected surface including worst delay and uncertainty; an invalid sensor inhibits the affected motion; independent physical protection for elevated trials. Defaults to compare (`chassis_icd.md` section 6.3, section 8; design values): `cliff.drop_mm` 60, `cliff.floor_min_mm` 8, `cliff.confirm_n` 3, `look.nominal_mm` 150 +- 40, `look.ahead_m` 0.12, `rear.stop_mm` 120, `rear.slow_mm` 300, `tof.max_age_ms` 100 (the cliff and rear thresholds are placeholders, the look tolerances are an engineer's choice: IB-60). Simulated stopping with the forward look sensors: floor loss at 0.20 m/s stops after 267 mm of the 285 mm available (18 mm margin on the nominal brake model); rearward at 0.05 m/s after 182 of 201 mm (IB-34; `simulated`).

**What a failure most likely means.** `TOF_STALE`: a sensor not delivering for 100 ms in the direction of travel (bus, mux, XSHUT, cable; the two TCA9548A muxes). A cliff sensor reading below 8 mm: blocked window or debris. Wet or shiny floors changing the range: the sensor class (VL53L4ED, 940 nm) is expected to be affected, which is why the test is in the VT. A latched stop that is never raised on a real drop: field logic or geometry.

## T10 Head gap and film-plane measurement

**Purpose.** Measure the entrance-film-to-floor gap, its repeatability on re-fit, and the 20 N corner deflection; this fixes the calibration standoff.

**Setup.** Static part of `mechanical/common/out/gap_measurement_method.md` section 3 A (proposed procedure, nothing measured): weigh the three contacts (three scales level within 0.2 mm), read g0 to g4 with spring-loaded ball-tip followers (0.02 mm resolution) and independently with a stepped wedge gauge 4 to 16 mm in 0.5 mm steps, read rail clearance c1 to c3, apply 20 N at each front outer corner and at the row centre, repeat after three head remove/refit cycles. Head alone on the bench cradle: end-of-line test E4 (`mechanical/head/production/README.md` section 9). Points (base_link mm): g1 to g4 at (181, +-171.25) and (81, +-171.25); g0 at (131, 0). The cradle and gauges are part of the head package in flux; use the files that exist at the time.

**Record.**

| Quantity | Unit | g0 | g1 | g2 | g3 | g4 | c1 | c2 | c3 |
|---|---|---|---|---|---|---|---|---|---|
| Gap, follower | mm | | | | | | | | |
| Gap, wedge | mm | | | | | | | | |
| After 20 N at each corner, deflection and return | mm | | | | | | | | |
| After refit 1, 2, 3 | mm | | | | | | | | |
| Wheel and caster reactions; x_CG | N; mm | | | | | | | | |

**Pass criterion and source** (proposed, to be confirmed by radiometry and the lead; `gap_measurement_method.md` section 5): static loaded gap 10.0 +-0.5 mm at each corner; corner-to-corner spread at most 0.6 mm; 20 N corner deflection at most 1.0 mm and returning within 0.1 mm; head refit repeatability at most 0.2 mm (RQ-015); dynamic gap within the calibrated interval, proposal 7.0 to 13.0 mm. Head end-of-line E4: 10.00 +-0.30 mm at the four outer window corners and the row centre (production stack +-0.25 mm worst case `calculated`); 3 mm rail inserts give 7 mm clearance, 5 mm inserts 5 mm. Calculated worst-corner sensitivity 1.58 mm per mm of wheel/caster step; the head 20 N deflection is calculated in `mech_calcs.md` section 4 and `head_report.md` section 4.

**What a failure most likely means.** Gap off by more than the tolerance: isolator thickness selection (0.40/0.50/0.60 mm G10 trims the prototype), cassette seat boss height, printed frame warp or elevation, receiver play; poor repeatability: mount play or tolerance of the dock datums; large corner deflection: printed receiver or frame stiffness different from the calculated (first mode 84 Hz and 0.19 mm under 20 N with option C, `calculated`).

## T11 USB and RS-485 link error rates

**Purpose.** Verify the two links under realistic noise: head link RS-485 at 1 Mbaud (host master, CRC-32 framing, retry with identical bytes), and chassis link USB CDC.

**Setup.** RR-CHS-MAIN with RR-HEAD-ACQ on the real harness (W-008 and W-009; and later the LAB extension), motors driven and heaters active; head polled at the gate cadence (default gate 100 000 us). Count records sent, CRC failures, retries, `GAP`s and `UNBOUND` events. Chassis side: `DRIVE` at 50 Hz with TTL for at least the run length; USB enumeration through the 0.3 m GH-to-USB-A cables.

**Record.**

| Condition | Duration (s) | Records sent | CRC / framing errors | Retries | GAP events | Bit-error estimate | Reply time, min / median / max (ms) |
|---|---|---|---|---|---|---|---|
| idle, heaters off | | | | | | | |
| motors at 0.10 m/s, heater on | | | | | | | |
| with LAB extension 2 m | | | | | | | |
| ESD and bus clamp events | | | | | | | |

**Pass criterion and source.** `chassis_design_review_checklist.md` E: 10^7 error-free records with motors and heaters active; both USB devices enumerate through the 0.3 m cables; presence events latched. Head link: VT-019 and `head_icd.md` section 8; VT-031 for the extended harness (error rates, clock quality, heater interference, counts). Reply-time and control-tick budgets are currently unmeasured and are to be recorded (VT-046); the time bound for mapping is at most 10 ms (target 2 ms).

**What a failure most likely means.** Errors that correlate with PWM or heater events: common-mode noise on the J2 pair, termination (120 ohm at each end, fail-safe bias at the chassis end only; a third termination in the extension gives about 40 ohm instead of about 60 ohm), a wrong A/B polarity of the L60 common-mode choke pairing (a wrong pairing shorts RS-485 A to B: IB-43), or DE/RE timing. Link drops at the USB connector: shield termination or cable.

## T12 Averaged waveform at the comparator input, triggered on each aggressor (VT-049, VT-063, VT-078)

**Purpose.** The missing measurement of the interference review (M7 item 3): random dark pulses average out, coherent pickup stays, with a sensitivity far below 0.1 p.e. It replaces count-rate deltas as the pass criterion for each aggressor; count rates (T5) remain the final system check.

**Setup.** Scope with a probe of 1 pF or less at the comparator input FCMP, or the `Fn PRE` pad through its 453 ohm, and at the FAST output; average **at least 10^4 sweeps** synchronised to the aggressor; head on the robot, bias on, lid closed, coaxial pigtails; each aggressor with and without the lane cans and the EMI cover; lab grounding recorded (above). Aggressors and triggers:

| Aggressor | Trigger |
|---|---|
| Heater edges (on and off) | HTR_GATE |
| Motor PWM at 0, 50, 100 % duty, free-running and stalled at the current limit | bridge output node, or a commutator-noise current probe on a motor lead |
| Brush-only states: motors on a DC bench supply at 100 %; back-driven with the bridges asleep; brake-relay K2/K3 transitions | the same probe |
| Monitor scan with MON_LANE_EN = 0 and 1 (the lane monitor muxes are off whenever armed; MON_LANE_EN = 1 is for this test only) | MON_MUX_A0 |
| Bias converter | its switch node or HV_SET write |
| Pulser strobe, LED strobe | PULSER_STROBE, LED_STROBE |
| RS-485 and USB traffic | a link frame start |
| Cut-out event | the cut-out opening |

**Record per aggressor:** trigger, state, cans / cover, averaged amplitude in mV and in p.e. (single-p.e. spacing from T1), duration, number of sweeps, noise floor of the average, calculated reference.

**Pass criterion and source.** VT-049: **the pass bound in photoelectrons per aggressor is defined by the head electronics lead before the test (not yet defined)**. Each measured amplitude is recorded next to its calculated figure (T15, T16, J60035, aggressors **assumed**): motor PWM 0.01 to 0.28 p.e. with coax; brush arc 0.11 p.e. coax and 2.76 open (review 0.6 and about 20); monitor tap 0.013 to 0.13 p.e. with the monitor enabled and zero with MON_LANE_EN = 0; **a difference of more than a factor of 3 is investigated**. VT-063 judges motor-terminal suppression by the measured ratio with and without the parts. VT-078: all four lane muxes off whenever armed, with U2405 absent, unconfigured or in reset.

**What a failure most likely means.** Edge-synchronous amplitude at the comparator: pickup into a loop (pigtail, ground bounce of the shield loop 0.27 p.e. at the SiPM carrier calculated, review m1); only with the muxes enabled: monitor tap injection (IB-58); only with cans removed: shielding.

## T13 Cable common-mode injection and lab grounding set-up

**Purpose.** Show how common-mode current on the J1 and J2 cables (1 to 30 MHz) and an ESD event affect counting; fix a grounding arrangement for all other head tests (`REVIEW_head_interference.md` M7 items 5 and 9, m3: at DC the J2 side is isolated, above about 1 MHz head GND reaches the chassis through four parallel paths).

**Setup.** Head counting dark and with the pulser; a current clamp injection on the J1 cable and on the J2 cable (frequency steps 1 to 30 MHz, level steps from zero), then an ESD gun to the cover and spreader with the head counting (check the frame-bond placement of stage 3: R2801 with F2801 at H1, four HF capacitors at H2, H5, H6, H8; the pre-stage-3 layout placed them beside lane 3, M3). Record the grounding: scope, debug adapter, SWD, dark-box metal, LAB extension, the supply earth.

**Record:** injection frequency and level (mA), counts in 100 s and the T12 amplitude per chain, bit errors on the head link, resets, `UNDERVOLTAGE`, `BIAS_OUT_OF_RANGE`; ESD level and result.

**Pass criterion and source.** Not defined (head electronics lead); the register carries it under VT-049 and the noise-immunity requirement RQ-032 (heater/drive PWM, braking and current peaks leave counts and timing within approved budgets; controlled overload leads to a safe stop or explicit invalidation).

## T14 Heater-circuit insulation, frame bond, frame monitor (VT-062, VT-079, head checklist E1, E2)

**Purpose.** Exclude the case in which a live heater-domain part touching the spreader returns up to about 1.5 A of heater current through R2801 and the board ground plane (review M5), and verify the stage-3 frame fuse and frame monitor.

**Procedure and record.**

| Step | Method | Expect | Reading |
|---|---|---|---|
| E7 (harness label) | J1/J2 unmated, head on the receiver or bench with the receiver metal contacted: frame (spreader) to receiver metal at 100 V DC | at least 10 Mohm | |
| W-103.HTR-ISO | assembled head, spreader bolted to the board, board disconnected: J2601 pins 1, 2, 3 and NTC pins 4/5 to FRAME and to GND at 100 V | at least 10 Mohm | |
| Cut-out case | isolated-case cut-out case to terminals at 100 V | at least 100 Mohm | |
| E7M | mated: four-wire frame to chassis GND at the J1 receptacle shell at 100 mA or less; record the fuse resistance | expected well under 2 ohm, dominated by F2801 (UNVERIFIED); at least 1 Mohm if the chassis board GND is not bonded to chassis metal | |
| MON_ADC heater test | F2801 fitted, heater cycling, MON_LANE_EN = 0: MON_ADC against its heater-off value | within +-5 mV | |
| Frame monitor | store MON_ADC at arm; insert a return-side leak (heater on): read the shift | +35 to +45 mV expected (calculated); firmware threshold 30 mV rise and +-60 mV window (derived, not measured) | |
| Feed-side contact | insert a feed-side contact | F2801 opens (limits the sneak to about 0.24 A, calculated) and the monitor sees it | |

**Pass criterion and source.** VT-062: E7 at least 10 Mohm; heater circuit to frame at least 10 Mohm at 100 V; isolated-case cut-out at least 100 Mohm. VT-079: a return-side leak raises MON_ADC by more than 15 mV and the heater turns off with the frame-fault code; a feed-side contact opens F2801; the firmware thresholds are replaced by measured values. **Never run the 100 V tester mated.** Test labels: use the harness labels E7, E7M, W-103.HTR-ISO; the checklist's E7 is the post-alpha tail and its E9 the waveform-capture rule (C-09).

## T15 Re-arm set stage and the service-test record sheets (P1, S3 to S8)

**Purpose.** Verify the REARM behaviour of the set stage and record the per-shift check P1 and the six-monthly service tests S3 to S8 on the assembled chassis. The procedures, the instruments and the pass and fail bands are in [../service/05_maintenance_and_spares.md](../service/05_maintenance_and_spares.md) section 6; the first execution is part of stage B6 of 04 and the bands below are `calculated` (`chassis_braking_tables.md` T15), some only 10 to 15 % apart, and **the resistance bands assume the meter's lowest-voltage resistance range keeps the tap clamp diodes off (node voltages under 0.2 V): UNVERIFIED for the meter in use; record the meter model and the test voltage.**

**Re-arm record (VT-080).** Close the chain and press REARM at the moment `rearm_ready` appears and at 2.5, 3.5 and 5 s; record C_SET, whether the set pulse reaches the K1 coil, whether K1 and U_HOLD operate, the events raised; press every 0.9 s for 8 s; taps of 3, 4, 6, 9, 11 and 20 ms at several phases against the 100 Hz sampling; supply 10, 11.4, 11.7, 12.0, 12.8, 14.6 V and board temperature 0 to 50 C (simulated: 36 of 36 combinations of pack 11.6 to 13.4 V, board 0 to 50 C and C_SET 80 to 120 uF arm at the first ready millisecond; set threshold C_SET 9.0 V at 23 C, about 9.9 V at 50 C by the follow-up review). Expect: SET_READY rises at 10.6 to 11.0 V about 3.2 s after the chain closes at 12.8 V; taps of 12 ms and longer always set; shorter ones are refused or `PARTIAL`, never fatal.

| Supply (V) | Board (C) | Time to `rearm_ready` (s) | C_SET at ready (V) | Press (ms, phase) | Outcome (latch / REARM_REFUSED reason) | Events |
|---|---|---|---|---|---|---|

**P1 record (every shift, 2 min):** P1.1 E-stop pressed, released, re-armed only when ready; P1.2 HANDS-ON pressed and held: lamp lit, latch drops; P1.3 each body bumper and each head-rail zone pressed in turn, re-armed between: latch drops and the element is named; P1.4 selector to SERVICE then RUN: MODE_RUN shown open in SERVICE; P1.5 brief REARM press when ready arms. Result: pass / fail (reason).

**S-test record (readings, each with units; fail bands are the fault's expected reading):**

| Test | Pads | Healthy band (T15) | Fault reading (T15) | Reading | Pass |
|---|---|---|---|---|---|
| S4a U_HOLD (pack removed, E-stop released) | SVC3 (red) to SVC4, ohm | 593 to 617 kohm | 431 to 449 kohm: U_HOLD shorted | | |
| S4b Q_HSET / HOLD_A (pack fitted, RUN, latch down) | SVC7 to SVC1, DC volts | under 0.05 V | 1.05 to 1.28 V: U_HOLD LED lit | | |
| S5a U_LS / RELAY_RTN (pack removed) | SVC6 (red) to SVC1 | 252 to 262 kohm | 216 to 224 kohm | | |
| S5b D_RUN (pack removed) | SVC5 (red) to SVC4 | 476 to 495 kohm | 431 to 449 kohm | | |
| S5c R_RHD (pack removed) | SVC4 (red) to SVC1 | 224 to 233 kohm | 283 to 294 kohm | | |
| S5d LS_A (pack fitted, RUN, latch down) | SVC8 to SVC1 | under 0.05 V | 1.05 to 1.28 V: U_LS LED lit | | |
| S3 set stage a, b, c, d, e, h (RTP-1 on J_BTN, W-018 unplugged, DMM on SVC10) | SVC10 | a), b): no set; c) no set and SVC10 keeps rising; d) sets; e) SVC10 under 0.5 V; h) no set | a) sets: Q_SETB short; b) sets: Q_SETA short; c) sets or SVC10 drops: Q_SETC short / SET_READY stuck; d) no set: set stage faulty; e) over 1 V: Q_SDIS open; h) sets: C_SC short or R_SG open | | |
| S6 U23 / U9 (JP1 open, test firmware) | WDG_OK_RB, CH_N9, U5/U6 pin 3 | stop the strobe: WDG_OK_RB and CH_N9 fall within 35 ms; DRV_NSLEEP high with latch down: nSLEEP stays low | CH_N9 stays live: U40/Q23/U23; nSLEEP high: U9 | | |
| S7 braking (scope with x10 probe on SVC4/SVC5 and a K2/K3 NC pin) | | RUN_HD falls under 1 ms; NC closed within 10.8 ms; spin-down tau at most 2 x the commissioning value | slower: clamp or relay; tau high: brake path | | |
| S8 plug channels | | CH_N4 falls with the link and with 24 V on the inlet | no fall | | |

## T16 Receiver thermal break, pack-to-body coupling and bay pre-heat (VT-058, VT-059, VT-060)

**Purpose.** Measure what the thermal policy (DEC-045; `interface/system/contract.yaml power.thermal_policy`) assumes: the receiver channels are on a 4.00 mm ground G-10 shim with G-10 bushings (calculated 0.081 W/K per channel to the plate; G-10 0.30 W/m K handbook, UNVERIFIED), the pack skin is held at or above -10 C on pack power (no regulation to +10 C), and on external power the pack is pre-heated to +5 C for charging (the pad on the pack skin 10 to 12.5 W, 95 to 200 min from a -25 C soak; pack-to-body coupling 0.6 W/K **assumed**).

**Procedure.** (a) Heat a channel above the plate and measure the heat flow through each shim joint (W/K per channel) and the body-side conductance per shoe at still air and 25 W/m2K; repeat after 100 latch cycles and after a hot-cold cycle (VT-058). (b) Tighten the M4 screws to 1.2 N m (about 1500 N preload); measure preload and datum-C gap after 1 h, 24 h, 1 week and 20 cycles between -25 and +50 C, with and without the spring washers (VT-060). (c) Soak at -25 and -20 C; measure pack-to-body coupling with the pad on; pre-heat from the soak on external power to +5 C and record time and power; run the -10 C hold on pack power and record the bay power; repeat in moving air (VT-059).

**Pass criterion and source.** At most about 0.10 W/K per channel to the plate (the proposal figure of IB-64); body-side per shoe compared with 0.11 / 0.14 W/K calculated against the 0.07 W/K the head model assumes (if higher, the head heater demand rises by about 1.6 / 2.9 W at -25 C); preload loss at most about 6 % with the spring washers (calculated; 57 % without) and datum-C gap change within +-1.58 mm; bay -10 C hold 0 to 7.8 W; pre-heat time compared with 95 to 200 min, **the maximum acceptable pre-heat time is "not yet defined" (operations)**.

## Open items

| Item | ID | Status |
|---|---|---|
| Margin required between the guaranteed beta yield and the lowest usable threshold | VT-042, RQ-063 | not yet defined (head electronics lead) |
| Acceptance limits for the live-time rate sweep | VT-037 | not yet defined |
| Numeric acceptance for alpha/beta discrimination and post-alpha hold | VT-010, B7 | not yet defined |
| Breakdown spread: 2.0 V (stage-2 decision) against 2.4 V in the AFE budget and VT-043 text | IB-25, IB-53 | Closed at 2.0 V; the budget and VT text not updated |
| Coax pigtail length: 35, 45 to 50 or 60 mm | IB-57, IB-23 | Open |
| Heater demand: three thermal calculations with different assumptions | IB-39, RQ-072 | Open |
| Stop-model inputs not measured (rotor inertia, friction); head rail stroke | RSK-033, IB-11 | Pending VT-003/045 |
| ToF driver; cliff/rear placeholders | IB-04, IB-60 | Open |
| Floor materials and surfaces for stop tests | not yet defined | site input (DEC-004) |
| Gap acceptance numbers are proposed only | `gap_measurement_method.md` | proposed |
| Monitor waveform capture missing on the target; scan-while-counting charge injection | IB-58 | Open |
| Step-and-count station pitch: contract 0.080 m, operator delta text "100 mm stations", power budget 0.10 m | contradiction | reported to the lead |
| Pass bound in photoelectrons for each aggressor (T12, T13) | VT-049, VT-063, VT-078 | not yet defined (head electronics lead) |
| Alpha/beta cut from real histograms; ZnS decay data (assumed 200 ns); margin 27 ns on the alpha side | VT-050, RFQ section J, C-11 | pending |
| Yield requirement 18 p.e. (electronics) against 15 p.e. (review, about 30 p.e. mean) | C-07, VT-042 | the registers use 18 |
| Heater: head report 15.2 / 18.4 W (+5 C, -20 / -25 C, still air) against 13.8 to 14.0 / 16.7 to 17.0 W in the contract and VT-057; short of capacity at 10 V in moving air at -25 C | IB-62, C-04, VT-057 | open |
| Service-test bands calculated; some 10 to 15 % apart; the meter's test voltage assumption unverified | IB-74, `chassis_braking_tables.md` T15 | open |
| Pass limits of 19 register tests are "criterion not yet defined" with a named owner | IB-71 | open |
| Test labels E7 / E9 used differently in harness and checklist | C-09 | this file uses the harness labels |
