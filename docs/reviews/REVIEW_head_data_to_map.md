# Independent review: head data contract against map reconstruction

Reviewer: independent second engineer (radiation-measurement instrumentation and data systems), 2026-11-27. I designed none of
this. Evidence labels as in the project: *calculated* = arithmetic shown here; *simulated* = my synthetic gate streams pushed
through the unmodified `rr_core` code; *tool-checked* = the project's own test commands. Nothing here is measured; every
coefficient involved is synthetic (`field_use_approved: false`).

Reader: the health physicist who will be asked to defend a survey result produced by this chain. The question throughout is
whether every quantity the map needs is defined, produced, transported, time-stamped, archived and used with one meaning from
the discriminator latches to `cells.csv`, and whether a third party can reproduce a cell result from the archive.

## 1. Scope and method

**Interface reviewed.** Head discriminator latches and live-time accounting → `head_gate_record` → ACQ 2.0 frame and DIAG
record → serial link and host clock fit → archive journal → gate interpretation, pose association, footprint weighting →
MODEL.md revision 4 decision statistic → exported products (`survey_manifest.json`, `gates.csv`, `cells.csv`, `cells.geojson`,
`coverage.png`, `flags.json`, `observations.json`, `summary.txt`).

**Read (code first, then documents).**
* Head: `firmware/head/core/rrh_evtcap.c/.h` (classification, live time, gate split, FIFO), `rrh_acq.c` (gate → frame
  mapping, sync evaluation, ACQ/DIAG serialisation), `rrh_core.c` (HELLO/BIND/ARM/READ/DISARM, retry cache, epoch),
  `rrh_setup.c` (setup image, `setup_id`, descriptor), `rrh_control.c` (bias loop, BIAS_VMON use, IMON, heater, global flags),
  `rrh_config.h`, `port/stm32g474/bsp.c` (64-bit tick extension), `port/stm32g474/evt_port.c` (capture, width measurement,
  clear), `firmware/head/README.md`, `CONTRACT_CHANGE_REQUESTS.md`; `interface/head_icd.md`, `head_icd_addendum_0.4.md`,
  `acquisition.schema.json`, `head_descriptor.schema.json`.
* Contract and model: `interface/system/contract.yaml` (timing, frames, optics, `head_gate_record`, `acq_mapping`,
  `survey_methods`), `docs/architecture/INTEGRATION_BACKLOG.md` (IB-31, 46, 47, 49, 50, 59, 60, 67), `analysis/radiometry/MODEL.md`
  rev 4, `MODEL_REVIEW_rev3.md`, `demo_calibration.json`, `demo_site_profile_ore.json`.
* Host: `ros2_ws/src/rr_core/rr_core/head_link.py`, `clockfit.py`, `frames.py`, `descriptor.py`, `chassis_link.py`,
  `trajectory.py`, `geometry.py`, `processing.py`, `estimator.py`, `linstat.py`, `profiles.py`, `pipeline.py`, `archive.py`,
  `export.py`; `rr_localization/estimator.py`; `rr_coverage/supervisor.py` (ratemeter); `rr_bringup/app.py`, `runtime.py`,
  `geometry_config.py`; `rr_head_driver/node.py`; `rr_sim/scenarios.py` (s08); `ros2_ws/STATUS.md`, `README.md`;
  `software/Operator_Interface_0.4_delta.md`; `interface/chassis_icd.md` §2 (clocks), §3.3 (odom/IMU stamps), §4.1 (events).
  `chassis_link.py` and `native_scenarios.py` carried another engineer's uncommitted edits while I read them; the edits
  (DRIVE statistics) do not touch anything I rely on.

**Run.**
* `firmware/head/check.sh` → `ALL CHECKS PASSED` (tool-checked).
* `ros2_ws/tools/test.sh unit` → `79 passed in 112 s` (tool-checked).
* Throwaway probes (simulated) in
  `/tmp/claude-0/-home-user-Rad-Roomba/243ed1e7-dcf1-5450-82ee-f4f91fbe9462/scratchpad/review_data/`
  (`probe1.py`, `probe2.py`, `probe3.py`, outputs `probe1.out`, `probe2.out`, `probe3.out`). They build a `SurveyProcessor`
  with the packaged demo descriptor, the option-C mount transform (0.0657, 0, 0.032) m, the demo calibration and the ore demo
  profile, feed straight-line trajectories and Poisson gate streams (U = 4 s⁻¹, 0.1 s gates, live 99 910 / 99 970 µs), and
  compare the code's cell results with a hand recomputation from MODEL.md §2/§3/§6.

**Not done.** Native emulator scenarios and the scenario suite were not run (another engineer is editing the native harness
and chassis fake). No hardware, no detector data.

## 2. Summary

| Severity | Count | Headline |
|---|---:|---|
| Critical | 3 | C1 exported decisions depend on when a cell was last evaluated, not on the data; C2 a calibration is applied to another head or setup without refusal; C3 a cell result cannot be reproduced from archived raw data |
| Major | 10 | alarms dropped below 50 % cell coverage and hot cells painted ACCEPTABLE; two different scan-stage statistics; pose credit asserted by a covariance that misses correlated errors (IB-47); pose time unbounded; one lost record voids the rest of a boot; `alpha_short` and alpha classification not monitored and rate-dependent; calibration envelope only partly checked; `field_use_approved` ignores commissioning/concept geometry; exported uncertainties cannot be aggregated; saturating hot spots become "invalid data" |
| Minor | 11 | see section 5 |
| Observation | 6 | see section 6 |

## 3. Critical findings

### C1. A cell's exported D\*, D#, decision and "no decision" status depend on the evaluation schedule, not on the archived data

**Evidence.** `processing.SurveyProcessor.evaluate()` re-evaluates only `self.dirty` cells (cells that received a new member).
`_u_null()` builds the reference window from `self._ref`, i.e. from the gates **received so far**. The robot app journals an
`evaluate` op every 5 s (`rr_bringup/app.py` `step()`, lines 263–270) and once more at export (`app.export()`), and
`cells_table()` calls `evaluate()` again, which again touches only dirty cells. A cell evaluated a few seconds after its
pass therefore gets a window that is one-sided and truncated at the present; if that window is shorter than 200·T_F (lane
and pooled) the cell is stored as `no decision — null reference unavailable`. Unless a later pass adds a member, it is never
evaluated again, although minutes of qualifying reference data follow it in the archive.

**Simulated example** (`probe3.py`, 4 × 2 m floor, five non-overlapping passes at 0.10 m/s, 180 s; identical gate streams,
same seed). Live schedule (evaluate every 5 s, as `app.py`) against one evaluation at the end:

| | live schedule | single final evaluation |
|---|---:|---:|
| cells with data | 630 | 630 |
| `no decision — null reference unavailable` | **121** (every cell of the first pass: y = −0.85 … −0.55 m, x = 0.45 … 3.75 m) | **0** |
| cells whose `detected` differs | 123 | — |
| D\* relative to final evaluation (cells decided in both) | −4.4 % … **+44 %** | 0 |
| D# relative to final evaluation | −3.7 % … **+52 %** | 0 |

The live D\* and D# are what the export carries. Replay reproduces them bit-for-bit (s08) only because the `evaluate` ops are
journaled at the same positions; s08 compares the software with itself, not with MODEL.md.

**Why critical.** MODEL.md §3 defines U_null as the reference rate over a window of ≥ 200·T_F **centred on the dwell**,
excluding the gates under test. The stored thresholds are not that quantity, and a third party who applies MODEL.md to the
archive obtains different D\*, D# and decisions, and none of the "no decision" cells. This also sharpens IB-31: the reported
"about 12 % of cells end as no decision" in 230–460 s runs is at least partly this artefact (my non-overlapping case gives
19 %, zero after a final evaluation); "0 in the 580–1100 s scenarios" is consistent with overlapping passes re-dirtying cells.

**Proposed change.**
* Host software: before any export, mark every cell with members dirty and re-evaluate with the complete attachment record;
  keep the live evaluation as a separately labelled *provisional / scan-stage* record (it legitimately drives the review
  queue and scaler counts), and record for every lane of every decision the first and last sequence of its U_null window.
* MODEL.md (owner: integration lead): state that the reported decision is computed from the complete record of the attachment
  after the survey, and how a window is formed at the start/end of an attachment; state what a live decision is.
* Test: s08 must compare live-then-final export with an independent batch evaluation of the same journal, not only live with
  replay.

### C2. A calibration is applied to data from another head or another setup without the software refusing

**Evidence.**
* `profiles.CalibrationStore.resolve()` compares the calibration's `validity_envelope.setup_id` with the head's `setup_id` only
  if `strict_setup` is true; the default is false and `rr_bringup/app.py` constructs `CalibrationStore(self.calibrations)`
  without it. The demo calibration carries `setup_id: "DEMO-SETUP-0"`, which no head can report; the probe (P3) shows it is
  accepted for head setup `S1-0123456789abcdef` with `setup_match: false` written into the manifest and nothing else.
* Processing never uses the per-attachment binding. `SurveyPipeline` receives one `Calibration` (the mission profile's
  `head_calibration_id`, `app.py` line 89) and `SurveyProcessor` applies `self.cal.cal(lane, channel)` to every attachment.
  `open_session()` does not compare `manifest["calibration_id"]` with `self.cal.calibration_id` (probe P4: a second attachment
  bound to `OTHER-HEAD-CAL` is accepted and processed with `DEMO-CAL-SYNTH-0001`). A head swap during a mission (allowed: a new
  HELLO/BIND opens a new attachment; the registry resolves head B's own calibration) therefore applies head A's k, b, K to head
  B's counts.
* `setup_id` (`rrh_setup.c` `rrh_setup_compute_id`) hashes the setup image and the firmware string but not the head serial, so
  two heads with the same setup have the same `setup_id`; the calibration record (`demo_calibration.json`) has no serial field.
  The only serial binding is the registry entry (`descriptor.evaluate`) that points to a calibration id; nothing checks the
  calibration record itself.
* `Calibration.check_envelope()` accepts a `setup_id` argument and never uses it (see also M7).

**Why critical.** k, b and K are per-head, per-lane, per-setup quantities; applying the wrong set makes r = F − k·U − b and
D = r/K wrong while every product looks normal.

**Proposed change.** Host software: per-attachment calibration in `SurveyProcessor` (look up by the manifest binding); refuse
`open_session` (no credit, reason code `CALIBRATION_MISMATCH`) when the bound calibration differs from the mission's or when
`setup_match` is not `true`; make `strict_setup` unconditional outside BENCH. Calibration record format (MODEL.md §1 owner):
add head serial, firmware and `setup_id` as identity fields, not only an envelope entry. Head firmware (optional): include the
serial in the `setup_id` preimage, or document that `setup_id` identifies settings, not a unit.

### C3. A cell result cannot be reproduced from the archived raw data

**Evidence.**
* Poses: the journal holds `P` entries that are the localiser's *output* (`app.py` line 223, `self.loc.predict(s)`); raw
  odometry and IMU replies are not archived (`chassis_link.py` logs only `chassis_hello`, `chassis_fit`, ops and events as `X`,
  which replay ignores) and LiDAR scans (`app.on_scan`) are not archived at all. The pose of every gate is therefore a processed
  product that cannot be re-derived or audited.
* Software identity: `export.SOFTWARE = {"version": "0.4.0-dev", "model": "MODEL.md rev 2"}` — no commit, no source digest, no
  Python/numpy/scipy versions, and the model revision is stale (the code implements rev 4). The decision depends on numerical
  details of those libraries (FFT lattice, `brentq`, Gil-Pelaez quadrature).
* Cell membership: MODEL.md §6 requires each cell to store its contributing gate keys; `cells.csv` stores only
  `n_lane_gates`; `flags.json` stores up to 400 keys and only for flagged cells; the footprint weights are exported nowhere.
  Recomputing them requires the exact raster algorithm (5 mm sub-cells, "all four corners inside" rule, three quadrature poses
  at 1/6, 1/2, 5/6 of the gate, cut at 0.10, rounding to a 0.05 lattice) which is in no specification.
* The thresholds are computed on quantised inputs (`Decider`: U_null on a 0.25 % log grid, live time per weight bin to 1 ms)
  and depend on the evaluation schedule (C1).

**Worked check of what *can* be reproduced** (`probe2.py`, cell (iy 5, ix 15) centred on lane 1, one pass at 0.10 m/s, lane 1
only, m = 1). From the processor's members and `gates.csv` counts:

| quantity | value |
|---|---|
| gates, weights | 16 gates (seq 104–119), w = 0.20, 0.30, 0.45, 0.60, 0.70, 0.85, 1.0, 1.0, 1.0, 0.95, 0.80, 0.70, 0.55, 0.40, 0.30, 0.15 |
| Σw·N_F, Σw·t_F | 2.55 counts, 0.994105 s |
| Σw·N_U, Σw·t_U | 3.35 counts, 0.994701 s |
| k, b, K (lane 1, beta window) | 1.0293, 0.5342 s⁻¹, 24.48 s⁻¹ per Bq cm⁻² |
| r = 2.55/0.994105 − 1.0293·3.35/0.994701 − 0.5342 | 2.5651 − 3.4665 − 0.5342 = **−1.4356 s⁻¹** |
| D = r/K | **−0.05864 Bq/cm²** (code −0.058643778104840; hand −0.058643778104840) |
| U_null | 3.7511 s⁻¹, lane window ±100 gates, 19.99 s, 75 counts |
| D\* (combined, 0.8α = 0.04), lane threshold (0.2α = 0.01), D# | 0.1811, 0.2436, 0.4591 Bq/cm² |

So the estimate is reproducible *given the weights and the code's U_null*. For a two-lane cell (`probe1.py`, cell (5, 4)) the
hand c-weights (0.47914, 0.52086) differ from the code's (0.47933, 0.52067) because of the `Decider` quantisation, and D
differs by 1.4 × 10⁻⁴ relative (−0.094632 vs −0.094619 Bq/cm²): immaterial numerically, but it means the stored value is not
the MODEL.md value and can be matched only with the same code.

**Why critical.** Reproduction today means "re-run the same, unidentified code over the journal, trusting the pose stream".
That is a regression test, not an independent check, and it is what a health physicist would be asked to provide.

**Proposed change.** Host software: archive every chassis DRIVE/STATE reply as raw `T`/`R` lines like the head stream, and
LiDAR scans (or a per-scan digest plus an external bag reference); write the commit, a digest of `rr_core`, the dependency
versions and the actual MODEL revision into `survey_manifest.json`; export a `cell_members.csv` (cell, attachment, sequence,
lane, weight). MODEL.md: specify the footprint raster, the 0.05 lattice and the `Decider` quantisation (or remove the
quantisation from the decision and keep it as a cache key only).

## 4. Major findings

### M1. Alarms in cells with coverage below 0.5 are dropped, and a hot cell can be painted ACCEPTABLE

**Evidence.** `processing._update_flag()` returns `None` when `cell_coverage(cy, cx) < cfg.min_cell_coverage` (0.5, in no
document). `classify_subcells()` paints covered sub-cells ACCEPTABLE when `sensitivity_ok(d)` (D# < goal and envelope ok),
independent of D, `detected` or a flag. The operator document says solid = acceptable and "never as clean" only for cells
that miss the goal.

**Simulated example** (`probe2.py`, one pass at y = −0.02 m, 3 Bq/cm² source under lane 0 at (1.55, 0.12) m): hot cell
(iy 6, ix 15) has coverage 0.40, D = 1.95 Bq/cm² (6.5 × the 0.30 investigation level), `detected = true`, D# = 0.18 at 0.015
m/s, **no flag**, and its 160 covered sub-cells are **ACCEPTABLE** (green) in `coverage.png`; `cells.csv` shows D = 1.95 with
an empty `flag` column. Here the alarm survived in the neighbour cell (5, 15) (D = 0.94, coverage 0.65, INVESTIGATION_LEVEL),
because lane 0's footprint straddles both; where the neighbour is invalid, blocked, excluded or also below 0.5 (end strips,
keep-out edges, a band whose adjacent pass failed) nothing is queued.

**Proposed change.** Host software: never suppress a `detected` cell; queue it with the coverage stated. Rename the
coverage class ACCEPTABLE to `SENSITIVITY_SUFFICIENT` (and never use it for a detected or flagged cell). MODEL.md: state any
coverage rule for decisions.

### M2. The scan stage that triggers scaler counts is not the MODEL.md revision-4 statistic

**Evidence.** In SEARCH_THEN_COUNT the ratemeter (`rr_coverage/supervisor.py` `on_gate()`) decides where to count: it uses
`est.decision_threshold()` (the revision-2 normal/Poisson form), U_null from older gates of the window or, failing 5 s of
them, **the four-lane pool over the same gates** (forbidden by MODEL.md §3 rev 4 and shown by `MODEL_REVIEW_rev3.md` to break
the union bound), the beta channel regardless of the profile's decision class, and U0 rounded to 0.1 s⁻¹ for its cache
(±1.25 % at U0 = 4 s⁻¹). The cells are decided separately by `estimator.combine()`. The stage record per cell
(`cells.csv.stage`) does not say which statistic produced the count request. Sharpens IB-50: besides the queue length, the
statistic that sends the robot to count is a third rule, and with ALARM_ONLY it is the only path to a scaler count.

**Proposed change.** Host software: drive the ratemeter alarm with `estimator.combine` on the window gates (m = 1, U_null from
older gates only, no same-gate pool, decision class from the profile) and store the alarm statistic, threshold and U_null with
the search alarm record. MODEL.md: define the ratemeter as the scan stage of §3.

### M3. Pose credit is asserted by the localiser's covariance, which cannot see the errors IB-47 measured

**Evidence** (`rr_localization/estimator.py`, `rr_core/trajectory.py`):
* `sample()` grants `credit` when the 2σ uncertainty at the row is ≤ 10 mm and **y and yaw** were updated within 1.5 s; x has
  no freshness requirement, although x is constrained only when an end wall is in LiDAR range.
* Odometry scale error is modelled as white noise per 20 ms step, `ss = (0.02·|ds|)²`: variance grows with distance, not with
  its square. Calculated at 0.10 m/s (ds = 2 mm per step): σ_x after 3 m = 0.02·√(3 × 0.002) m = **1.55 mm**; the reported 2σ
  reaches the 10 mm budget only after about **31 m** of travel without an end-wall fix (ignoring y and yaw terms). A
  systematic wheel-radius error of 1 % (0.52 mm on 52 mm, tyre compression) gives **30 mm** after 3 m, the size of the
  27–34 mm transients of IB-47, while credit stays true.
* `update_scan(t_us, …)` applies a scan to the current state; `t_us` is used only for book-keeping, so scan latency is not
  compensated (10 mm per 100 ms at 0.10 m/s in x).
* The gyro is integrated as `gyro_z × dt` with dt = 20 ms (DRIVE at 50 Hz) from a 10 ms mean stamped 5 ms before the odometry
  sample (chassis ICD §3.3): half the yaw-rate record is never read.
* `TrajectoryBuffer.add()` opens a new epoch only for a jump above 50 mm + 0.5 m/s × dt; a 30 mm correction is interpolated
  as motion.

Sharpens IB-47: the open question is not only "why the transient" but that, by construction, no transient below 50 mm can
withdraw credit, so the 10 mm (2σ) erosion is not demonstrated. The 80 mm step-and-count pitch (abutting credited footprints
with 2 × 10 mm erosion) inherits this.

**Proposed change.** Robot software: an x-freshness condition (or a correlated scale-error state) in the credit rule;
time-aligned scan updates; read the IMU at 100 Hz or integrate the reported mean over its own window; log `credit` with the
truth error in the native scenarios and report the fraction of credited gates whose true error exceeds 10 mm; until then
state in the manifest that the position allowance is a design value, not a verified bound.

### M4. Only the head clock has a checked bound; the pose time does not

**Evidence.** Head gates are converted with `clockfit.interval_to_host()` and rejected above 10 ms (`HOST_BOUND`,
`FIT_EXPIRED`). Odometry samples are converted with `ChassisLink.to_host()` = `fit.current.to_host()` with **no expiry**;
`bound_us` is put in the sample but `WallLocalizer.predict()` drops it and `TrajectoryBuffer` has no time-quality field.
With the chassis fit stale (TIME failing) a 200 ppm nominal drift gives 12 ms after 60 s, i.e. 1.2 mm at 0.10 m/s and growing
without a flag. ICD §6 requires the bound over the mapped interval; the gate-to-pose association has two clocks and one bound.

**Proposed change.** Host software: carry the chassis bound into each pose sample, treat an expired chassis fit as
`POSE_UNCERTAIN`, and check `head bound + chassis bound` (scaled by translational and angular speed at the outer lane) against
the position budget.

### M5. One lost head record removes every later gate of that boot; nothing reacts

**Evidence.** `rrh_acq.c` `on_gate()` latches `RRH_H_RECORD_LOST` (or `GATE_TIMING`, `GATE_TIMEOUT`, `SOURCE`); these map to
`ACQ_FAULT` in every following frame (`rrh_control_acq_flags`). Health latches clear only by `FAULT_CLEAR`
(`rrh_eng.c` line 280) or reset; `op_hello()` does not clear them, so a re-handshake keeps the flag. The host never sends
`FAULT_CLEAR` and never polls `STATUS`; `frames.lane_status()` turns `ACQ_FAULT` into `HEAD_FLAG:ACQ_FAULT` and
`processing._process()` excludes every gate. IB-58 already notes that a service interrupt more than 3 gates late overflows the
4-slot FIFO: from then on the robot keeps surveying and the rest of the boot is INVALID_DATA, with no operator message. The
health codes `WATCHDOG_RESET`, `ENTROPY` (boot UUID may not be random) and `STORAGE` reach no ACQ flag at all and are visible
only in DIAG (sampled) or STATUS (never read).

**Proposed change.** Head firmware/ICD: make `ACQ_FAULT` a per-gate condition for the gate(s) affected by a lost record or
timing fault and keep the latch for STATUS. Host: poll `STATUS` at session open and on any `ACQ_FAULT`, archive it, raise an
operator hold; map `ENTROPY` to a handshake refusal.

### M6. `alpha_short` and the alpha class are not monitored, and their losses are rate- and spectrum-dependent

**Evidence.**
* `rrh_evtcap_service()`: a floor event with the ALPHA latch set is alpha only if the measured time over threshold is ≥ the
  device cut (J60035: 290 ns); otherwise it is a floor reject counted in `alpha_short` — removed from both alpha and beta window.
  The reference chain has no ALPHA comparator (ULD → reject, else count). Bright photon-induced events are therefore removed
  from the floor beta window but kept in the reference: the transfer coefficient k depends on the fraction of bright Compton
  events, i.e. on the site photon spectrum and on pile-up, not only through the declared `spectral_mismatch_relative` (3 %).
* Width capture (`evt_port.c` service ISR): each new falling-edge capture on a busy chain **overwrites** `width_ticks`. A second
  pulse that ends before classification (4 µs window, 10 µs service) makes a bright beta look long and classifies it as alpha
  — the C1 failure of `REVIEW_head_interference.md` returns at a rate proportional to pile-up. Calculated with IB-67's 3 × 10⁻⁴
  bright-beta fraction and a 10 µs pile-up window: at 2000 s⁻¹ floor rate 2000 × 3 × 10⁻⁴ × 0.02 = **0.012 s⁻¹** of false
  alphas, against the 0.01 s⁻¹ alpha background budget; at 100 s⁻¹ it is 3 × 10⁻⁵ s⁻¹.
* `alpha_short` reaches the host only in DIAG, read once per second for `last_seq` (`head_link.py` `_run`, `diag_period_us =
  1 000 000`): about 1 gate in 10. `processing.add_diag()` stores it; nothing uses it. It is not corrected anywhere; it is in K
  and k only if the calibration was taken with the same `setup_id` and a matching spectrum and rate, which no check enforces (C2).
* A single K, k, b per lane cannot represent an efficiency that changes with rate (pile-up) and spectrum.

Sharpens IB-59/IB-67: even when host logic is added, the record is incomplete by design; and the TOT fix is undone by
pile-up in the port's width bookkeeping.

**Proposed change.** Head firmware: keep the width of the *first* falling edge after the BUSY start (do not overwrite while
`width_valid`), and flag (or reject) events with a second edge before classification; add cumulative per-lane counters
(`alpha_short`, `floor_reject`, `alpha_idle_clears`, forced clears) to DIAG so a 1 Hz poll gives complete totals, or poll DIAG
per gate (26.2 % bus load, addendum §6). Calibration/MODEL.md: record the `alpha_short` and reject fractions of the calibration
source and photon field, and add a validity condition on the survey's fractions per lane.

### M7. The calibration validity envelope is only partly checked

**Evidence.** `profiles.Calibration.check_envelope()` checks the reference-rate range, the R7 floor and the cell's mean head
temperature. The demo envelope also states `standoff_mm` 8–12, `speed_m_s` 0–0.1 and `setup_id`; none is checked. Contract
`survey_methods.CONTINUOUS_SCAN.speed_mps` allows up to 0.20 m/s and the 0.10 m/s search speed sits at the envelope edge; the
standoff is never measured (descriptor `qualified_standoff_m: null`). The calibration's `u0_evaluation: "smoothed_reference"`
is summarised into the manifest but the decisions use the rev-4 window method.

**Proposed change.** Host software: per-gate speed from the pose interval against the envelope (reason `OUTSIDE_ENVELOPE:speed`),
standoff once it is measured or declared, `setup_id` (C2); remove or correct `u0_evaluation`.

### M8. `field_use_approved` in an export ignores commissioning mode and concept geometry; detached files carry no marker

**Evidence.** `export.export_survey()`: `fua = profile.field_use_approved and cal.field_use_approved`. `ProfileStore.snapshot()`
allows an approved profile in COMMISSIONING; the registry accepts CONCEPT geometry and a synthetic calibration in
COMMISSIONING (`descriptor.evaluate`). An export of a COMMISSIONING attachment with CONCEPT geometry and an approved
calibration/profile has `field_use_approved: true` and no banner; the attachment's `mode` and `geometry_basis` are listed but
not used. The banner appears in `summary.txt`, the SVGs and the manifest only: `cells.csv`, `cells.geojson`, `gates.csv`,
`flags.json` and `observations.json` contain no calibration id, `synthetic` flag or mode.

**Proposed change.** Host software: `fua` also requires every attachment `mode == "SURVEY"` and `geometry_basis == "AS_BUILT"`;
add `calibration_id`, `field_use_approved` and `run_id` columns/properties to every tabular product.

### M9. Exported cell values invite averaging and interpretation errors

**Evidence and calculated consequence.**
* Only `u_stat` and `u_total` are exported per cell (`processing.cells_table`). The common calibration terms
  (U·u_common(k), u_rel(K)) are fully correlated between cells of a lane (MODEL.md §2: "must not be averaged down"). An RP
  who averages N cells to meet a larger averaging area with u_total/√N underestimates the systematic part by √N; the
  components needed to do it correctly are not exported. Demo numbers: u_common(k) = 3 % of k ≈ 0.03 at U = 4 s⁻¹ gives
  0.12 s⁻¹ → 0.005 Bq/cm² per cell, not reducible; u_rel(K) = 15 % of D is not reducible either.
* D is a footprint average (MODEL.md §6): activity confined to a 100 mm cell is reported as Σw²t/Σwt of its value (0.44–0.74
  for the 0.4 geometry). D# is quoted for activity covering every contributing footprint; for contamination confined to the
  cell the effective limit is larger by 1/0.74 … 1/0.44 = 1.35–2.3 (`MODEL_REVIEW_rev3.md` (B)). `grid.json` carries a one-line
  note; `cells.csv` does not.
* `T_F` in `cells.csv` is the sum over lanes of the weight-scaled floor live time, not a dwell time; uncertainties are standard
  (k = 1); D\* and D# are at α_comb = 0.8·α_scan (scan stage), not at the profile's per-decision α and not at the mission
  allowance. None of this is in the column names; only `grid.json` states the unit.

**Proposed change.** Host software: export per cell `u_lane_cal`, `u_common_cal` (per lane and combined), `footprint_dilution`
(Σw²t/Σwt per lane), the α at which D\*/D# hold and units in the header; add a `README` to the export. MODEL.md: state the
aggregation rule across cells.

### M10. A saturating hot spot is reported as "invalid data", not as an alarm

**Evidence.** `rrh_acq.c` `map_lane()`: a forced clear in the gate (`FLOOR_SATURATED`) or floor live fraction below 50 % nulls
alpha and beta window with `SATURATED`. The host excludes the lane (`LANE_FLAG:SATURATED`) and paints the full footprint
INVALID_DATA (`processing._process`). No flag, no queue entry; the residual appears as "unresolved floor INVALID_DATA". Live
fraction 50 % (non-paralysable, m·τ = 0.5) corresponds to about 1600 s⁻¹ counted alphas (3200 s⁻¹ true) with the 300 µs hold
plus ~10 µs per event, or about 5 × 10⁴ s⁻¹ counted betas (10⁵ s⁻¹ true) at 9.7 µs each (calculated); a single forced clear
(BUSY > 1 ms) nulls the gate at any rate. These are exactly the cells a survey must not miss.

**Proposed change.** Host software: a gate with `SATURATED` (or a live fraction below a profile limit) raises a
`SATURATION` flag at its footprint and enters the review queue regardless of policy. ICD: keep the gross counts and live time
of a saturated chain available (DIAG already has `alpha_raw`/`beta_raw`/`floor_live_ticks`; per gate only if DIAG is per gate).

## 5. Minor findings

| # | Finding (evidence) | Proposed change (owner) |
|---|---|---|
| m1 | Weights are rounded to a 0.05 lattice in the estimate and the statistic (`processing._credit`, `estimator.WEIGHT_STEP`), and the code comment cites MODEL.md rev 4, which does not say so (only the rev-3 review's limits mention it). Rounding 0.33/0.33/0.34 gives 1.05 of a gate's live time across cells. | State it in MODEL.md §6 or use exact weights (MODEL.md owner, host) |
| m2 | `_u_null()` hard-codes `span_s = 0.1` to turn a window length into a number of gates, and counts the window in sequence numbers, which continue across DISARM/ARM time gaps. | Window in host time from the gate intervals (host) |
| m3 | The addendum says the true heater on-time of a faulted gate is in DIAG; `rrh_evtcap.c close_gate()` sets `heater_on_ticks` from the state at gate close, so DIAG `heater.on_us` is 0 for a gate whose heater was forced off mid-gate. | Accumulate on-time at the switch edges, or correct the addendum (head firmware) |
| m4 | `bias.vmon_ratio_e4` is outside `setup_id` and writing it does not invalidate the binding; bias is open-loop, but the ratio sets the BIAS_OUT_OF_RANGE judgement (±0.5 V tolerance against ±1 % divider = ±0.30 V at 30 V before calibration). It is archived only if the host happens to run `ENG_SETUP_GET`. | Report `vmon_ratio_e4`/`vmon_calibrated` in DIAG or HELLO and archive them (head firmware, host) |
| m5 | Calibration `lane_order` reads "0-3 from the robot's left to right facing the direction of travel"; with reverse-entry tracks (IB-29) the direction of travel is backwards. ICD/contract define lanes in the robot frame (S0 = robot left). | "robot frame, +y = robot left, independent of travel direction" (calibration owner) |
| m6 | HEATER_TRANSITION and AFTER_GAP marks and DIAG `bias.dac_writes` exclude nothing (no rule exists); a bias step inside a gate shifts gain mid-gate. | Define an exclusion or a test that shows none is needed (MODEL.md owner) |
| m7 | Areas swept during a sequence gap appear UNVISITED, not as an acquisition gap; `gaps.json` gives head times only, no host time or map extent. | Map the gap interval through the trajectory and paint it (host) |
| m8 | Sharpens IB-49: the stand-alone `rr_head_driver` hard-codes the demo calibration as its only store, writes no `run.json` (its archive is not replayable by `build_from_run`), and stamps `GateCounts.header` with publication time, not gate time. | Fix before any bench result is quoted (host) |
| m9 | `no decision` cells are drawn with the insufficient-sensitivity pattern (`classify_subcells`); the operator document says they are shown as no decision. | Own class/pattern (host) |
| m10 | `HeadStreamInterpreter._prev_heater` and `_marked_next` are not reset at SESSION_OPEN: the first gate of a new attachment is compared with the previous attachment's heater state. | Reset with the session (host) |
| m11 | A lane with a floor-only fault is also removed from the U_null reference series (`_process`: any `LANE_FLAG`), although its reference is valid (ICD §6: preserve; withhold only the compensated contribution). Conservative; shortens windows. | Use `photon_ref` when non-null (host) |

## 6. Observations

| # | Observation |
|---|---|
| O1 | For m = 1 the combined test (0.8α) and the lane test (0.2α) are the same statistic: the effective false-alarm probability is 0.8α, not α (consistent with STATUS.md's Monte Carlo 0.79–0.91). Harmless; worth stating. |
| O2 | With the demo profile, α_scan = 0.05 per decision cell means about 0.05 × 4480 = **224** expected scan alarms (recount requests) on a clean 16 × 2.8 m floor under ALARM_ONLY (sharpens IB-50). |
| O3 | Time chain arithmetic: 144 MHz × 0.1 s = 14 400 000 ticks = 100 000 µs exactly; `start_us = ⌊tick/144⌋` (≤ 1 µs truncation); the 10 ms mapping limit is 1 mm at 0.10 m/s, 2 mm at 0.20 m/s and 0.75 mm at 0.30 rad/s on the 0.25 m outer-lane corner. The fixed 10 ms limit therefore satisfies the ICD's speed-scaled rule at contract speeds. |
| O4 | The heater transition is derivable from consecutive ACQ frames because the heater switches only at gate boundaries (`close_gate`); the host does this. |
| O5 | IB-46 / IB-60: no data-contract consequence found. The continuity hooks in `app.py` use event names the chassis firmware emits (`J1`, `J2`, `HEAD_POWER`, `CHAIN` with `HEAD_DOCK`/`HEAD_LOOP_OK`); a loaded host loop inflates the TIME residual and therefore the bound (conservative, costs coverage). |
| O6 | `localizer.head_lever_m = 0.32` is the Rev D lever; with option C the outer-lane corner is at about 0.25 m. Conservative. |

## 7. Answers to the eight questions

**1. Gate identity and time.** Identity is (host `attachment_session_id`, head `sequence`), sequence from 0 at HELLO and
continuous across DISARM/ARM (`rrh_core.c`); a head reset gives a new `boot_id` and a new attachment; the 32-bit TIM2 is
extended to 64 bits in the 100 kHz ISR (`bsp.c`), so no wrap within a boot. Start and length: `start_us = epoch.us +
⌊(gate_start_tick − epoch.tick)/144⌋`, span checked to equal the armed span, contiguity checked (`on_gate`). Host time:
`interval_to_host()` maps both ends with the current fit, bound = max over endpoints of (anchor half-residual + |fit residual|
+ drift uncertainty × age) + 150 µs asymmetry; above 10 ms the gate is `HOST_BOUND` and earns nothing; HOLDOVER and UNSYNCED
gates are excluded too. Pose interval: five poses (ends for validity, three quadrature poses for the footprint) from one
trajectory epoch. Duplicates are dropped by sequence with a digest; conflicting duplicates and overlapping frames end the
session; retries return cached bytes (TIME excepted, and a retried TIME is not fitted). Sequence and time gaps are recorded
(m7 for how they are mapped). No path found by which one gate is credited twice; gates without host time or pose are
logged and not credited, and remain UNVISITED rather than INVALID (m7). Gaps: the pose time has no checked bound (M4); a lost
record voids the rest of the boot (M5).

**2. Live time.** Firmware live time is per chain (floor, reference), gate span minus measured busy intervals, split exactly
at the boundary; alpha and beta window share the floor chain's live time, the reference has its own: this matches MODEL.md's
T_F (per lane, same for both classes) and T_U. The 300 µs post-alpha hold and idle-latch clears are inside the measured busy
time; forced clears null the floor channels (SATURATED) instead of being corrected; below 50 % live fraction the channel is
null. Dead-time correction is the ratio N/T_live, done consistently in `estimator._lane_estimate`, the ratemeter and the flag
locator (three places, one definition). `alpha_short` is neither corrected nor monitored, and the alpha class and k depend on
rate and spectrum in ways one K cannot represent (M6). Heater and monitor markers: marked, not excluded (m6).

**3. Channel semantics.** Alpha = ALPHA latch with TOT ≥ device cut; beta window = BETA_LLD set, ULD and ALPHA not set;
reference = REF_LLD set, REF_ULD not set (`rrh_evtcap.c`, contract `head_event_capture`). `setup_id` covers thresholds, trims,
pulser, chain enables, bias law, heater law, hold, device, TOT override, confirmation and the firmware string; it excludes the
BIAS_VMON ratio (m4), the head serial (C2) and compile-time constants except through the firmware string. A calibration can be
applied to another setup or head without refusal (C2).

**4. Geometry.** Lane order and signs are consistent from the descriptor (lane 0 at +131.25 mm, robot left; `validate_geometry`
enforces left-to-right order) through `lane_polygons()` to the map (+y = left wall); descriptor x 65.5 mm + mount 65.7 mm =
131.2 mm = contract optics row; aperture 100 × 80 mm (x × y), eroded to 80 × 60 mm. The swept footprint is represented by
three interior poses per gate (sweep 10 mm at 0.10 m/s); weights are fractions of the eroded raster on 5 mm sub-cells, cut at
0.10, rounded to 0.05 (m1). The grid is aligned to (0, −W/2) with partial last rows. The 10 mm position allowance is not
demonstrated (M3).

**5. Flags.** Every global flag (ACQ_FAULT, HEAD_TEMP_OUT_OF_RANGE, UNDERVOLTAGE, BIAS_OUT_OF_RANGE, HEATER_FAULT, OVERTEMP)
excludes the whole gate; every lane flag (FLOOR_FAULT, REFERENCE_FAULT, SATURATED, DEAD_TIME_UNKNOWN, DISCRIMINATOR_FAULT) and
any null channel excludes the lane; excluded credited-stage footprints are painted INVALID_DATA and not credited. Raw bytes are
archived unchanged; per-lane reasons reach `gates.csv`; `cells.csv` carries no per-cell exclusion summary. Dropped or
reinterpreted: SATURATED becomes "invalid" not "possible hot spot" (M10); latched ACQ_FAULT outlives its cause (M5); DIAG
health and lane flags are sampled 1 in 10 and unused.

**6. Decision chain.** Matches MODEL.md rev 4 in structure: exact coefficients (floor +cᵢwⱼ/(KᵢT_F), reference
−cᵢkᵢwⱼ/(KᵢT_U)), null means at U_null, Z with lane terms and the fully correlated common term, Gil-Pelaez/lattice evaluator
with the half-step check, α split 0.8/0.2, `no decision` codes, signed values, u_stat and u_total. Hand check of one cell: agreement to
4 × 10⁻¹⁶ relative (m = 1) and 1.4 × 10⁻⁴ (m = 2, quantisation) in section 3, C3. Deviations: U_null window truncated by the evaluation
schedule (C1); the scan stage that triggers counts is another statistic (M2); undocumented 0.5 coverage rule (M1) and 0.05
lattice (m1); review-queue policy ALARM_ONLY implemented as specified, with the consequences in O2. Units: Bq/cm² for D, u,
D\*, D#; s for T_F (weighted, summed); none in the column names (M9).

**7. Reproducibility and records.** Not reproducible from raw data alone (C3); reproducible bit-for-bit only by replaying the
same code over the journal, which also reproduces C1. Not archived: raw odometry/IMU and LiDAR, software identity, DIAG for 9
gates in 10, STATUS, the head setup when no `head_setup` is configured, cell members and weights. The demo calibration is
labelled (`DEMO-CAL-SYNTH-0001`, `synthetic`, `field_use_approved: false`, banner) but the label is lost on detached tabular
files and can be absent on a COMMISSIONING export with approved records (M8).

**8. What a health physicist must not conclude from an export as it stands.**
1. That green / ACCEPTABLE floor is clean or meets the release criterion: it means only D# < goal; a cell at 6.5 × the
   investigation level can be ACCEPTABLE (M1).
2. That every cell with a high D has a flag: cells below 0.5 coverage are never flagged (M1).
3. That the cell D is the mean activity of the 100 cm² cell: it is a footprint average, 0.44–0.74 of a cell-confined activity,
   and D# assumes activity covering every footprint (M9).
4. That averaging N cells reduces u_total by √N: the calibration part does not average down and is not exported (M9).
5. That `no decision` floor was undecidable from the data: much of it is an evaluation-timing artefact (C1).
6. That D\* and D# hold at the profile's per-decision or mission α: they are at 0.8·α_scan for the scan stage, and the
   two-stage detection probability is lower than 1 − β (M9, O2).
7. That INVALID_DATA is an instrument problem only: saturation from a very hot spot is reported the same way (M10).
8. That the spatial position of a credited footprint is good to 10 mm: the credit rule cannot detect the 27–34 mm transients
   seen on the emulators (M3, M4).
9. That the calibration in the manifest is the one applied to every head and setup in the run (C2).
10. That re-running the archive with MODEL.md gives the exported numbers (C1, C3).
11. That UNVISITED area was not driven over: acquisition gaps and gates without pose or host time are shown that way (m7).
12. That a `field_use_approved: true` export came from an as-built, survey-mode attachment (M8).

## 8. Checked and found consistent

* ACQ live time = ⌊live_ticks × 10⁶/tick_hz⌋ per chain; zero or over-long live time → null + DEAD_TIME_UNKNOWN; a measured zero
  stays `{"counts":0,"live_us":n}`; disabled chains never report a valid zero (`close_gate`, `map_lane`).
* Busy intervals split arithmetically at the gate boundary; counts attributed by clear time (≤ 1 ms later; 0.1 mm at 0.10 m/s).
* ARM → epoch at tick 0 = µs 0; TIME `rx_us`/`tx_us` and gate times on the same 144 MHz-derived clock; the head echoes the
  host's SYNC bound and grows it at 200 ppm in HOLDOVER.
* Head retry cache keyed by id and exact bytes; TIME never cached; host fits only first-transmission TIME replies; fresh ids
  after a session change (`tid_stride`).
* HELLO discards frames, sync records and sequence; a setup change invalidates the binding before reaching the hardware.
* Duplicate/conflict/overlap handling and gap events per ICD §6 table; SESSION_OPEN archived with fsync before the first frame.
* Descriptor digest over exact bytes, identity cross-check, registry check; descriptor bytes archived in the manifest.
* Lane order and sign conventions, optics row 131.2 mm, aperture 80 × 100 mm, erosion 10 mm (section 7, Q4).
* Estimator coefficients, null means, Z, α split and stored decision fields against MODEL.md rev 4 §3/§6 (hand check, C3).
* Archive: append-only sealed segments with SHA-256, torn final entries tolerated, every process start a new epoch; replay
  feeds the same interpreter (bit identity is plausible; I did not rerun s08).
* Signed D kept, negative values exported; D# = ∞ exported as blank rather than a number.

## 9. Cannot be assessed until detector data exist

* `alpha_short`, reject and idle-clear fractions per lane for calibration sources (Am-241, Sr-90/Y-90, Cl-36, Tc-99) and for
  ore photon fields; the TOT cut margin (27 ns below the weakest assumed alpha, IB-67).
* Dependence of k on photon spectrum and rate through the floor/reference classification asymmetry (M6); leakage ε per class.
* Pile-up probability within the classification window at real pulse shapes (M6 width overwrite).
* Dead-time model and live-time accuracy under pulser rate sweeps including the 300 µs hold and forced clears.
* Spatial response (top-hat assumption), edge blur, standoff dependence, and therefore the footprint dilution factors (M9).
* True localisation error at the detector row on the chassis with real LiDAR latency and wheel/tyre behaviour (M3).
* Heater-transition and bias-step artefacts in counts (m6); monitor-tap injection (IB-58/67 M2).
* Whether 200·T_F windows are adequate in real, non-stationary photon fields (MODEL.md open point).
