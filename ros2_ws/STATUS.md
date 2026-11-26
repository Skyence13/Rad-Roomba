# ros2_ws status (robot software, design 0.4)

Evidence classes: calculated / simulated / tool-checked. Nothing here is physically measured.
All calibration and profile data are synthetic (`field_use_approved: false`); the yellowcake
profile is present and unconfigured. Observed results are in `README.md` §"Observed results"
and in `evidence/*/evidence.json`; this file says what exists, what is thin and what is missing.

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
| Coverage planner, motion executor with route monitoring, mission supervisor with CONTINUOUS_SCAN / SEARCH_THEN_COUNT (INLINE, DEFERRED) / STEP_AND_COUNT | `rr_coverage/` | scenarios s01–s04, s10–s12 |
| Guided review (Next / Expose / Park / Repeat / Skip) | `rr_guidance/guidance.py` | scenarios s01, s05, s07 (Repeat and Skip are not exercised by a scenario) |
| Operator web service + UI, roles, single control lease, idempotent receipts, hash-chained audit, SSE | `rr_web/` | `rr_web/test/test_web.py` (fake backend), scenario s07 (lease logic) |
| RobotApp composition, geometry from `frames.yaml` + contract | `rr_bringup/app.py`, `geometry_config.py` | all scenarios |
| ROS 2 workspace: 11 packages build with colcon; `rr_interfaces` (12 msg, 2 srv, 1 action); robot node, simulator node, stand-alone head driver and chassis bridge nodes; sim/hardware launch files | `src/*/`, `rr_bringup/launch/` | `tools/test.sh ros` (graph smoke test, real time) |

## Thin, stubbed or deviating — read before relying on it

- **One composed robot node.** Localisation, mapping, coverage, guidance and the web service run
  inside `rr_bringup robot_node` (one process). `rr_localization`, `rr_coverage`, `rr_guidance`,
  `rr_mapping`, `rr_web` are libraries without their own ROS nodes; `rr_mapping` is an empty
  package apart from its manifest. Only `rr_head_driver` and `rr_chassis_bridge` have stand-alone
  nodes, and those two nodes were built but **never run** (not covered by any test).
- **Startup ordering** is enforced by the mission prerequisites check, not by ROS lifecycle nodes.
- **TF**: the robot node publishes `map → base_link` only (no separate `odom` frame, CR-11).
- **The `GuidedVisit` action server** is implemented and builds; it was not called by a test
  (the scenarios and the smoke test use the command service / in-process calls).
- **Wall strips**: outer tracks are limited by in-place turns (CR-06): ~0.14 m per wall remains
  unsurveyed in a 2.5 m trailer. Keep-outs are excluded from the target but not planned around.
- **Blocked-strip replanning** is "defer the task, retry once after the other passes"; there is no
  path search around an obstacle.
- **Scan evidence at 0.10 m/s does not meet the 0.20 Bq/cm² goal** with the demo calibration
  (D# ≈ 0.35 per 0.1 m cell); s01 runs at 0.03 m/s where the median cell is at 0.20.
- **LiDAR**: no motion de-skew; range 12 m and noise are assumptions. Reverse moves rely on the
  chassis rear field (CR-10).
- **Replay** rebuilds every product from the journal (raw head wire stream, recorded poses and
  supervisor marks). The trajectory is replayed as recorded, not recomputed from LiDAR scans;
  raw scans are not archived.
- **Web**: plain HTTP, demo accounts with trivial passwords, no TLS, no session re-authentication
  for hand-off. Browser-level tests and screenshots were **not** made (`evidence/ui/` is empty).
- **Serial transports** are implemented with pyserial and untested (no hardware).
- **Head DIAG** bodies are archived; nothing consumes them. `STATUS`, `FAULT_CLEAR`, `ENG_*` are unused.
- **Multi-pack-swap step-and-count**: resume-as-new-epoch is tested once on a continuous scan
  (s12); a step-and-count mission across a restart was not run.
- **`colcon test`** was not run; the unit and scenario suites are run with pytest on the sources.

## Failed or flaky

- ROS graph smoke test (`tools/test.sh ros`): 2 complete runs, 1 passed, 1 ended with the mission
  in HOLD about 25 s into the scan (cause not captured; real-time run on a loaded 4-core host).
- Native emulators: see `README.md` for the last result of `tools/test.sh native`.
