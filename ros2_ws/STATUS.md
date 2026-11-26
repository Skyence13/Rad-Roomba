# ros2_ws status (robot software, design 0.4)

Evidence classes: calculated / simulated / tool-checked. Nothing here is physically measured.
All calibration and profile data are synthetic (`field_use_approved: false`); the yellowcake
profile is present and unconfigured. Observed results are in the verification log below and in
`evidence/*/evidence.json`; this file says what exists, what is thin and what is missing.

## Verification log (close-out, 2026-11-26; filled in as runs complete)

Observed by the close-out engineer, not copied from earlier notes. "simulated" = deterministic
Python fakes or real-time emulators; "tool-checked" = headless browser / unit tooling.

| Group | Command | Observed |
|---|---|---|
| Unit | `tools/test.sh unit` | **47 passed** (rr_core: wire/descriptor 12, estimator 9, head link 9, processing 7, clock fit 5; rr_web 4 incl. 2 added at close-out: server-side motion interlock, demo-account marking; rr_bringup 1 added: station-pitch default follows contract). Before the close-out additions: 44 passed. |
| Scenarios (Python fakes, simulated, deterministic) | `tools/test.sh scenarios` | **After the owner-decision work: 16 passed in 10 min 04 s** (adds s13_door_target, s14_wall_tracks; s01 now runs the default reverse-entry wall tracks: sim time 1082 s, valid exposure 0.804 vs 0.646, acceptable 0.630 vs 0.377, median D# 0.179, flag 27 mm from the patch, revisit error 1.7 mm est. / 2.2 mm true, Expose 0.350 m, park 0.8 mm). **Baseline before that work: 14 passed** in 11 min 42 s (s01, s02, s03, s04a/b, s05, s06, s07, s08, s09, s10, s11 INLINE/DEFERRED, s12). Key numbers (3.0 × 1.2 m section): s01 at 0.03 m/s — flag 20 mm from the injected patch, revisit error 1.7 mm estimated / **2.1 mm true**, Expose reverse 0.350 m, park error 0.9 mm, valid exposure 0.646 of the floor (wall/end strips are a large share of a 1.2 m floor), acceptable 0.377, **median D# 0.201 Bq/cm², best 0.172** (goal 0.20: met by the median only marginally); localisation error vs truth ≤ 1.1 mm (x) / 1.2 mm (y). s09 — true time error never exceeded the reported bound in 4 cases (0.2 ms: bound ≤ 0.82 ms; 3 ms + 80 ppm: ≤ 3.8 ms; asymmetric 0.2/6 ms: error 3.3 ms ≤ bound 3.8 ms; 12 ms: bound 12.8 ms → all 31 gates rejected, arming refused HEAD_CLOCK); moving hotspot mapped within 2.7 mm along track. s10 step-and-count (3 s preset) — interrupted station invalidated and repeated, only static gates credited, median D# 0.247. s08 — two replays bit-identical to the live export. |
| Native step-and-count (opt-in) | `tools/test.sh native n03` | **native_s10_step_and_count PASS (5/5)**, 8 min 28 s: 1.8 × 1.0 m, preset 3 s, station pitch **0.080 m** (contract default after CR-05), 68 stations, 0 invalid, only static scaler gates credited, hotspot flagged, median D# 0.213, time-sync bound ≤ 1.09 ms. Unvisited area 0.84 m² vs 0.97 m² in s10 (fakes, 0.10 m pitch): the 20 mm inter-station stripes are closed. |
| Native emulators (simulated, real time) | `tools/test.sh native` | **native_s01 PASS (11/11 checks), native_s02 PASS (10/10)**, 8 min 28 s (clean run after the two contaminated attempts, see change 4). s01: hotspot across a seam flagged 28 mm from the patch centre, revisit error 1.6 mm estimated / **1.8 mm true** (limit 10 mm), Expose reverse 0.350 m, time-sync bound max 1.14 ms / median 0.92 ms (limit 10 ms, 146 fits, 0 rejected), link 15 410 replies, 0 bad lines/gaps/retries, valid exposure 0.646. s02: MCU reset → HOLD HEAD_LINK, session closed, fresh handshake with new boot id, no counts attributed before the new BIND, resume only after re-arm, both bands complete. **Note:** max localisation error vs truth on the emulators was 12.4 mm (s01) / 15.7 mm (s02) in x, versus ≤ 1.7 mm on the Python fakes — larger than the 10 mm credit budget at some instant; not investigated further (the revisit, measured at rest, was within 2 mm). |
| ROS graph smoke (simulated, real time, Python fakes over TCP) | `tools/test.sh ros` | **3 of 3 clean runs passed** (13/13 checks each; ~2 min each; workspace built earlier with `tools/build.sh`, `--symlink-install`). No HOLD during the scan in any run (the only HOLD recorded is the test's own `OPERATOR_PAUSE` before export at ~42 s). Each run is appended to `evidence/ros_smoke/runs.ndjson`. The earlier flake (HOLD ~25 s into the scan, 1 of 2 runs) was **not reproduced** and its reason was never captured; the test now records every HOLD with its reason, so a recurrence will be diagnosable. One further run at close-out failed for a known external reason (it ran concurrently with a native run on the same ports — change 4) and was discarded. |
| UI (Playwright, tool-checked) | `tools/run_sim.sh --port 8090 --auto --method SEARCH_THEN_COUNT --speedup 6` + `node tools/ui_screenshots.js http://127.0.0.1:8090` | **14/14 checks passed** (2nd run; 1st run failed: lease lost under `--speedup`, fixed — change 3). 14 PNGs in `evidence/ui/` (desktop 1280 px `d01–d10`: login, status + coverage layer, activity layer, detection-limit layer, ratemeter/scaler, review queue, Next at spot, Expose spot, parked, Charge/Service + reports; phone 390 px `p01–p04`: viewer status, viewer review queue, viewer Charge/Service, second operator seeing control held), `ui_checks.json`. Observed: 27 review items on the 3.0 × 1.2 m section with one injected patch — the patch (INVESTIGATION_LEVEL, scaler-counted) plus `UNRESOLVED_EXCEEDANCE` cells whose search-stage D# (≈ 0.57–0.62 Bq/cm²) exceeds the 0.3 investigation level, so they cannot be cleared; expected with the synthetic calibration at 0.10 m/s, but a field queue would be long. |

### Changes made at close-out (small defects / hygiene only, no new features)

1. **Web: server-side motion interlock.** `rr_web/server.py` `interlock_refusal`: the web service
   itself refuses `start/resume/next/expose/park/repeat` (and in Charge/Service also `preflight/arm`)
   from the backend's reported chassis mode / safety state, independent of the backend's own checks.
   Before, the refusal in Charge/Service came only from `RobotApp`/the supervisor and the web test
   exercised it through a fake backend that refused by itself. New test
   `test_web_refuses_motion_in_charge_service_and_while_inhibited` uses a backend that accepts
   everything. Pause, abort, re-arm and export still pass.
2. **Demo accounts marked.** `users_demo.yaml` has `demo: true`; `rr_bringup.runtime.load_users`
   flags every account `demo` (also if any plain-text `password` is present) and prints
   `WARNING: DEMONSTRATION ACCOUNTS …` on stderr at start-up; the UI shows a DEMO ACCOUNTS banner
   and a sign-in note. Test `test_demo_accounts_are_marked_and_warned`.
3. **Stand-alone simulator lease clock.** `rr_sim/sim_server.py` ran the web sessions and control
   lease on the simulated clock; with `--speedup 6` the 5 s lease lasted < 1 s of wall time and was
   lost between two event-stream heartbeats (observed: `control_lost HEARTBEAT_LOST` 12 sim-s after
   Start, then Next refused in review). Sessions/lease now use the wall clock.
4. **Process finding (not a code defect): never edit `tools/test.sh` while it runs.** bash reads
   the script incrementally; an edit during a run made the running instance execute fragments
   (it launched the `ros` smoke test on TCP 5540/5550 while a `native` run was starting on the same
   ports — both failed: head stuck in `QUIET`, `link_down TRANSPORT:peer closed`). The previous
   engineer's `evidence/native_run.log` ("line 29: syntax error") shows the same thing. Those runs
   are discarded; results below are from clean runs.
5. **CR-05 accepted by the lead** (contract `station_pitch_m: 0.080`): the STEP_AND_COUNT default now
   comes from the contract (`geometry_config.survey_method_defaults`), fall-back defaults 0.08,
   packaged `contract_snapshot.yaml` refreshed; still a parameter. Test `rr_bringup/test/test_config.py`.
   s10 keeps an explicit 0.10 m (documents the 20 mm stripes). CR-08/09/11 logged by the lead
   (IB-31 and backlog), not implemented. CR-06 (IB-29) and CR-07 (IB-30) were then decided by the owner
   and implemented (items 6 and 7).
6. **Owner decision IB-30 (long trailers, doors open) implemented:** `trailer.door_target_x_m`
   (removable flat door-end target; null = none). The localiser uses the target line exactly like the
   closed door (`rr_localization.estimator.door_reference_x`); the planner moves the door end to the
   target; the simulator world draws it. New prerequisite `ALONG_TRACK_REFERENCE`: in a trailer longer
   than `lidar.range_max` with the doors open and no target, Arm/Start/Resume are refused. The
   LOCALIZATION hold is unchanged. Scenario **s13_door_target** (3.0 m section, LiDAR range set to
   2.0 m): refusal without target, accepted with target at 0.25 m, 232 x-updates from the target,
   x error vs truth 1.8 mm, no hold — passed. Rule stated in README §8.2 and in
   `software/Operator_Interface_0.4_delta.md` §3 step 0.
7. **Owner decision CR-06 / IB-29 implemented: reverse-entry wall tracks** (`plan.wall_track_entry:
   in_place | reverse_entry`, default `reverse_entry`). Planner (`rr_coverage/planner.py`
   `_wall_side`, `check_prims`): per side wall one extra track pair as close to the wall as the
   straight-motion outline allows (half-width 0.175 + wall margin 0.03 + tracking tolerance 0.005 m),
   outer +x / inner −x (offset p/2). Entry = reverse along a 0.09 rad diagonal from a pivot-clear point,
   small align pivot; exit = back-off along the track, small peel pivot, forward diagonal to the band.
   Every primitive incl. the pass is checked with the swept RECTANGLE outline (body + head + tail)
   against the floor shrunk by wall/door/front margins and the tracking tolerance; track starts are
   moved away from the end wall so the tail clears it through the whole align pivot. Reverse ≤ 0.05 m/s,
   forward ≤ 0.10 m/s, yaw ≤ 0.25 rad/s (contract max 0.30). No credit on manoeuvre primitives.
   Supervisor phases WALL_ENTRY / WALL_EXIT / WALL_RETURN: a stopped or refused reverse entry
   abandons the track (status `RESIDUAL`, blocked rectangle journaled), the robot drives back along
   the verified entry path, the track is not retried; a hold on the track recovers as a normal pass;
   a hold in the exit resumes the exit. Scenario **s14_wall_tracks** (3.0 × 1.0 m): predicted strip
   48.8 mm, **achieved 55 mm** both sides (5 mm sub-cells), min clearance of the true rectangle outline
   to the margins outside the pivot band **+0.5 mm**, no credit on the diagonals, rear-field stop of
   the entry → HOLD FIELD_REAR 0.25 m before the track, resume → back to the entry point, track
   RESIDUAL after 1 attempt, mission complete (left strip then 95 mm) — passed. 2.5 × 16 m (calculated,
   `evidence/plan_2.5x16.json`): wall strips 0.137 → **0.049 m**, covered fraction 0.881 → 0.951,
   extra time **+865 s at 0.10 m/s** (45 → 59 min), +2301 s at 0.03 m/s (2.2 → 2.8 h), +9745 s
   step-and-count 10 s (9.5 → 12.2 h).
   Scenarios s02–s13 and the native runs pin `in_place` to stay comparable with the baseline;
   s01 and s14 run the default.
   Finding: inside the pivot band the baseline in-place pivots are planned with the contract swept
   radius 0.278 m (rounded tail); the rectangle outline's corner radius is 0.309 m, so a rectangle
   check there shows −41 mm at the door-end pivots. This is the model difference, not a new excursion,
   but nobody has verified the rounded-tail assumption against the as-built tail (mechanical).
8. Tooling: `tools/replay.sh`, `tools/plan_report.py` (`tools/test.sh plan`),
   `tools/ui_screenshots.js`; `tools/ros_smoke.py` now records every transition into HOLD with
   its reason and appends each run to `evidence/ros_smoke/runs.ndjson`.

## Implemented and tested

| Area | Where | Tested by |
|---|---|---|
| Record framing, strict JSON, stream resync | `rr_core/wire.py` | `rr_core/test/test_wire_descriptor.py` (baseline examples byte-identical) |
| Transports `serial://`, `tcp://`, in-memory with latency/faults, TCP listen for fakes | `rr_core/transport.py` | link tests, scenarios (serial is untested: no device) |
| Clock fit (4-timestamp, offset+drift, bound, expiry, serialisation-length correction) | `rr_core/clockfit.py` | `test_clockfit.py`, scenario s09 |
| Descriptor/registry/frames (ports of the 0.3 host tools; registry use COMMISSIONING added) | `rr_core/descriptor.py`, `frames.py` | `test_wire_descriptor.py` |
| Head link master + passive stream interpreter (handshake, SYNC, ARM, READ, retry-same-id, CRC, GAP/EMPTY, dedup, UNBOUND, continuity loss → close/quiet/fresh ids/fresh handshake, DIAG per sequence) | `rr_core/head_link.py` | `test_head_link.py` (Python fake); native head emulator in `tools/test.sh native` |
| Chassis link (HELLO/session, TIME fit, 50 Hz DRIVE with TTL and fresh ids/seq, STATE, EVENTS with gap, REARM_SW nonce, STOP with reason, SET_OP_MODE, HEAD_POWER, CONFIG, BRAKE_TEST, stationary-window rule) | `rr_core/chassis_link.py` | scenarios (Python fake); native chassis emulator in `tools/test.sh native`. No stand-alone unit test file. |
| Python protocol fakes (independent of the firmware) | `rr_core/fakes/head.py`, `chassis.py` | used by all deterministic tests |
| Estimator per MODEL.md rev 2 (signed r/D, u_stat/u_total, U_null from an independent window, exact Poisson thresholds, D*, D#, lane combination with common terms kept, Šidák, two-stage) | `rr_core/estimator.py` | `test_estimator.py` incl. cross-test against `analysis/radiometry/rrrad` |
| Calibration records + validity envelope; site profiles, explicit units, RP-only versioned edits, mission snapshot | `rr_core/profiles.py` | `test_estimator.py`, scenario s06 |
| Trajectory buffer with epochs; footprint geometry from descriptor + mount; erosion; swept regions | `rr_core/trajectory.py`, `geometry.py` | `test_processing.py` |
| Coverage accounting on 5 mm sub-cells, decision cells (0.10 m), reason codes, flags with stable IDs and named locations, scaler observations, step-and-count station credit, residual rectangles | `rr_core/processing.py` | `test_processing.py`, scenarios |
| Append-only archive (atomic sealed segments with SHA-256, epochs), journal pipeline, export (CSV, GeoJSON-like, SVG, PNG, summary, manifest), replay | `rr_core/archive.py`, `pipeline.py`, `export.py` | scenarios s08, s12 |
| Wall-referenced localisation (wheel+gyro EKF, wall/bulkhead/door line fits, residual gate, slip flag, credit/hold budgets) | `rr_localization/estimator.py` | scenarios only (no unit test file) |
| Coverage planner, motion executor with route monitoring, mission supervisor with CONTINUOUS_SCAN / SEARCH_THEN_COUNT (INLINE, DEFERRED) / STEP_AND_COUNT (station pitch from contract) | `rr_coverage/` | scenarios s01–s04, s10–s12; `rr_bringup/test/test_config.py`; plan figures `tools/test.sh plan` (calculated) |
| Guided review (Next / Expose / Park / Repeat / Skip) | `rr_guidance/guidance.py` | scenarios s01, s05, s07, native_s01, UI run (Next/Expose/Park from the page). Repeat and Skip are not exercised by any test. |
| Operator web service + UI, roles, single control lease, idempotent receipts, hash-chained audit, SSE, server-side motion interlock (Charge/Service, traction inhibited), demo-account marking | `rr_web/`, `rr_bringup/runtime.py` | `rr_web/test/test_web.py` (4 tests), scenario s07 (lease logic), Playwright drive of the real page against the simulator (`tools/ui_screenshots.js`, 14 checks, `evidence/ui/`) |
| RobotApp composition, geometry from `frames.yaml` + contract | `rr_bringup/app.py`, `geometry_config.py` | all scenarios |
| ROS 2 workspace: 11 packages build with colcon; `rr_interfaces` (12 msg, 2 srv, 1 action); robot node, simulator node, stand-alone head driver and chassis bridge nodes; sim/hardware launch files | `src/*/`, `rr_bringup/launch/` | `tools/test.sh ros` (graph smoke test, real time) |

## Thin, stubbed or deviating — read before relying on it

- **One composed robot node.** Localisation, mapping, coverage, guidance and the web service run
  inside `rr_bringup robot_node` (one process). `rr_localization`, `rr_coverage`, `rr_guidance`,
  `rr_mapping`, `rr_web` are libraries without their own ROS nodes; `rr_mapping` is an empty
  package apart from its manifest. Only `rr_head_driver` and `rr_chassis_bridge` have stand-alone
  nodes, and those two nodes were built but **never run** (not covered by any test).
- **Startup ordering** is enforced by the mission prerequisites check, not by ROS lifecycle nodes.
- **TF**: the robot node publishes `map → base_link` only (no separate `odom` frame, CR-11, logged for a later decision).
- **Cell statistics** (CR-08/09 → IB-31): as described in CONTRACT_CHANGE_REQUESTS.md, decision deferred.
- **Along-trailer reference** (CR-07 → IB-30, implemented): rule enforced at arming; between end references x is odometry only and credit is withheld when the budget is exceeded.
- **The `GuidedVisit` action server** is implemented and builds; it was not called by a test
  (the scenarios and the smoke test use the command service / in-process calls).
- **Wall strips**: with the default reverse-entry wall tracks ~0.049 m per wall remains (0.137 m with
  `in_place`). Guided revisit and deferred counts plan their approach only inside the pivot band
  (`approach()`); a flag seen only by a wall track can be reported UNREACHABLE (not exercised by a test).
  A process restart in the middle of a wall manoeuvre (s12-type resume) was not tested. Keep-outs are excluded from the target but not planned around.
- **Blocked-strip replanning** is "defer the task, retry once after the other passes"; there is no
  path search around an obstacle.
- **Scan evidence at 0.10 m/s does not meet the 0.20 Bq/cm² goal** with the demo calibration
  (D# ≈ 0.35 per 0.1 m cell); s01 runs at 0.03 m/s where the median cell is at 0.18–0.20.
- **LiDAR**: no motion de-skew; range 12 m and noise are assumptions. Reverse moves rely on the
  chassis rear field (CR-10).
- **Replay** rebuilds every product from the journal (raw head wire stream, recorded poses and
  supervisor marks). The trajectory is replayed as recorded, not recomputed from LiDAR scans;
  raw scans are not archived.
- **Web**: plain HTTP, demo accounts with trivial passwords (now marked and warned), no TLS, no real
  authentication, no session re-authentication for hand-off — all **required before field use**.
  Browser-level evidence: one Playwright run (14 checks) against the stand-alone simulator, taken
  before the wall-track default was switched on (pages unaffected); no cross-browser or accessibility test.
- **Serial transports** are implemented with pyserial and untested (no hardware).
- **Head DIAG** bodies are archived; nothing consumes them. `STATUS`, `FAULT_CLEAR`, `ENG_*` are unused.
- **Multi-pack-swap step-and-count**: resume-as-new-epoch is tested once on a continuous scan
  (s12); a step-and-count mission across a restart was not run.
- **`colcon test`** was not run (not part of `tools/test.sh all`); the unit and scenario suites are run with
  pytest on the sources. The workspace was not rebuilt after the close-out edits (`--symlink-install`
  links the edited sources); `tools/build.sh` should be run once before the next ROS run.
- **Localisation unit tests**: `rr_localization` still has no unit test file; the door-target path is
  exercised by s13 only.

## Failed or flaky

- ROS graph smoke test (`tools/test.sh ros`): previous engineer: 2 runs, 1 passed, 1 ended in HOLD
  about 25 s into the scan (reason not captured). Close-out: 3 of 3 passed with HOLD capture in place
  (load average ~8–10 on 4 cores from other work). Status: **flake not reproduced, cause unknown**;
  treat the smoke test as timing-sensitive. Do not run it together with `native` (same TCP ports).
- Native emulators: passed at close-out (see verification log). Localisation error vs truth on the
  emulators reached 12–16 mm in x at some instant (fakes: < 2 mm) — not investigated.
