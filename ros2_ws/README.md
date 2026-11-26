# ros2_ws — Rad Roomba robot software (design 0.4)

ROS 2 Jazzy workspace for the Rad Roomba floor-survey robot: head link, chassis link, wall-referenced
localisation, coverage planning and mission supervision for three survey methods, count-to-floor
mapping per `analysis/radiometry/MODEL.md` rev 2, hotspot flags, guided revisit (Next / Expose spot /
Park) and a browser operator interface. The real logic lives in ROS-free Python libraries; the ROS
nodes are thin adapters.

**Evidence classes.** Everything in this workspace is *calculated*, *simulated* or *tool-checked*.
Nothing is physically measured. All calibration and profile data are synthetic
(`field_use_approved: false`); every product and the UI banner say so. What is implemented, thin or
failing is listed in [`STATUS.md`](STATUS.md); this file says how to use it.

---

## 1. Prerequisites

| What | Version / note |
|---|---|
| Host | Linux x86-64 with Docker (tested: Ubuntu 24.04, Docker daemon running, 4 cores) |
| Image | `rad-roomba/ros2-ws:0.4` — ROS 2 Jazzy `ros-base` pinned by digest + Ubuntu-archive Python packages (`docker/Dockerfile`; resolved versions in `docker/versions.lock`). Built by `tools/build.sh` if missing (needs the Ubuntu archive once). No Nav2, no Gazebo. |
| Native emulators (optional, for `native`) | `cmake`, `ninja`, a C compiler on the host (see §3.2) |
| UI screenshots (optional) | Node.js with Playwright + headless Chromium on the host (`require('playwright')`) |

All tools run the code **inside the container** with the repository bind-mounted at the same absolute
path, `--network host`, as the invoking uid. Parallelism: `RR_PARALLEL` (default 2).

## 2. Build

```bash
cd ros2_ws
tools/build.sh              # image if missing, then colcon build --symlink-install (11 packages)
tools/build.sh --image      # force image rebuild first
tools/build.sh --clean      # remove build/ install/ log/ first
```

The unit, scenario and native suites run on the sources and do **not** need the colcon build; the
`ros` smoke test and `tools/run_sim.sh ros` do.

## 3. Test

One command runs everything and exits non-zero if any group fails:

```bash
tools/test.sh all           # unit + scenarios + native (if emulators built) + ros (if workspace built)
```

Groups individually:

| Command | What | Time (4 shared cores) |
|---|---|---|
| `tools/test.sh unit` | pytest on every package's `test/` except rr_sim | ~20 s |
| `tools/test.sh scenarios` | 15 end-to-end scenarios against the Python protocol fakes, deterministic seeds; rewrites `evidence/s*/` | ~10–20 min |
| `tools/test.sh native [n01] [n02]` | scenarios 1 and 2 against the native firmware emulators, real time; rewrites `evidence/native_*/` | ~20–30 min |
| `tools/test.sh ros [--native]` | ROS graph smoke test (launch, services, topics, web), real time; writes `evidence/ros_smoke/` | ~2 min |
| `tools/test.sh colcon` | `colcon test` on the built workspace | not part of `all` (see STATUS) |
| `node tools/ui_screenshots.js [url] [out]` | Playwright drive of the UI against a running simulator; writes `evidence/ui/` | ~5–15 min |

pytest arguments pass through: `tools/test.sh scenarios -k s01 -x`.

### 3.1 `all` skips

`all` prints `SKIPPED native` if `firmware/head/build/host/rr_head_sim` or
`firmware/chassis/build/rr_chassis_sim` is missing and `SKIPPED ros` if `install/setup.bash` is
missing; a skip is not a failure. Build both to run everything.

### 3.2 Native firmware emulators

```bash
cmake -S firmware/head -B firmware/head/build/host -G Ninja && cmake --build firmware/head/build/host -j2
cmake -S firmware/chassis -B firmware/chassis/build -G Ninja && ninja -C firmware/chassis/build -j2
```

`tools/test.sh native` starts and stops both itself (`rr_sim/native.py`). Ports: head serial-over-TCP
127.0.0.1:5540 + stimulus UDP 5541; chassis link TCP 5550 + environment UDP 5551. The Python fakes of
the ROS smoke test use the same TCP ports — do not run `native` and `ros` at the same time.

## 4. Run the simulator and open the UI

```bash
tools/run_sim.sh                                   # deterministic sim (Python fakes) + UI, http://127.0.0.1:8080/
tools/run_sim.sh --auto --method STEP_AND_COUNT --port 8081 --speedup 4
tools/run_sim.sh ros                               # ROS graph: rr_sim sim_node + rr_bringup robot_node (needs build)
tools/run_sim.sh ros native:=true                  # ROS graph against rr_head_sim / rr_chassis_sim already listening
```

`--auto` performs the operator bring-up (datum, REARM, brake test, REARM, Arm) so **Start** is
the next step. Without it, do it from the page: *Register datum → (REARM button in the simulation
panel) → Preflight / brake test → REARM → Arm → Start*. The simulation panel (visible after a page
reload once logged in) stands in for the robot's local controls: REARM, PAUSE, E-stop, charger,
person in path.

**Accounts (DEMONSTRATION ONLY).** `viewer/viewer` (read only), `operator/operator` and
`operator2/operator2` (mission commands; one control lease at a time), `rp/rp` (profiles,
disposition). Defined in `src/rr_bringup/rr_bringup/config/users_demo.yaml` (`demo: true`). Loading
that file prints a `WARNING: DEMONSTRATION ACCOUNTS …` line on stderr at start-up and the page shows
a *DEMO ACCOUNTS* banner and a note on the sign-in card.

**Before any field use** (not implemented, required): TLS on the operator interface (the service is
plain HTTP), site accounts with `password_hash` only and real authentication / identity, session
re-authentication for control hand-off, and network isolation of the robot's access point. See §12.

Server-side protections that *are* implemented: role checks, a single control lease, CSRF token,
exactly-once command ids with receipts, hash-chained audit, and **motion commands refused by the web
service itself in Charge/Service and while traction is inhibited** (`rr_web/server.py`
`interlock_refusal`; tested in `rr_web/test/test_web.py::test_web_refuses_motion_in_charge_service_and_while_inhibited`).

## 5. Transports (hardware vs emulators)

| Link | Hardware | Native emulator | Python fake (sim / ROS smoke) |
|---|---|---|---|
| Head | `serial:///dev/ttyUSB0?baud=1000000` (RS-485, 1 Mbaud; `link.byte_time_us: 10`) | `tcp://127.0.0.1:5540` (`rr_head_sim`) | `tcp://127.0.0.1:5540` (sim_node) or in-memory |
| Chassis | `serial:///dev/ttyACM0` | `tcp://127.0.0.1:5550` (`rr_chassis_sim`) | `tcp://127.0.0.1:5550` or in-memory |

```bash
ros2 launch rr_bringup hardware.launch.py registry:=/etc/rad-roomba/head_registry.json \
    head_url:=serial:///dev/ttyUSB0?baud=1000000 chassis_url:=serial:///dev/ttyACM0 users:=/etc/rad-roomba/users.yaml
```

The hardware launch requires a trusted head registry (no default). A LiDAR driver publishing
`sensor_msgs/LaserScan` on `scan` (frame `lidar_link`) is started separately. **The serial
transports are untested** (no hardware).

## 6. Package map

| Package | Content | ROS node |
|---|---|---|
| `rr_interfaces` | 12 msg, 2 srv (`MissionCommand`, `ExportSurvey`), 1 action (`GuidedVisit`) | — |
| `rr_core` | ROS-free core: wire framing, transports, clock fit, head link, chassis link, descriptor/registry/frames, estimator (MODEL.md rev 2), profiles/calibration, trajectory/geometry, coverage processing, archive, pipeline, export/replay, Python protocol fakes | — |
| `rr_head_driver` | stand-alone head driver node | `head_driver_node` (built, never run by a test) |
| `rr_chassis_bridge` | stand-alone chassis bridge node (publishes `odom → base_link`) | `chassis_bridge_node` (built, never run by a test) |
| `rr_localization` | wheel+gyro EKF with wall/bulkhead/door line fits, credit/hold budgets | library |
| `rr_coverage` | planner (`planner.py`), motion executor (`motion.py`), mission supervisor (`supervisor.py`) | library |
| `rr_guidance` | guided review: Next / Expose spot / Park / Repeat / Skip | library |
| `rr_mapping` | empty placeholder (mapping is in `rr_core/processing.py`) | — |
| `rr_web` | operator web service (aiohttp) + single-page UI (`static/`), control lease, audit | library |
| `rr_sim` | kinematic world + LiDAR, deterministic harness, scenarios, native-emulator harness, stand-alone sim server | `sim_node` |
| `rr_bringup` | `RobotApp` composition, runtime, config, launch files | `robot_node` (everything above in one process) |

Topics of `robot_node`: `head/gates`, `head/attachment`, `head/events`, `chassis/state`, `safety/state`,
`localization/status`, `localization/pose`, `coverage/status`, `mission/state`, `mission/flags`,
TF `map → base_link`; subscribes `scan`; services `mission/command`, `mission/export`; action
`guided_visit`.

## 7. Configuration files

| File | Content |
|---|---|
| `src/rr_bringup/rr_bringup/config/sim.yaml` | simulation RobotApp config: trailer, profile id, mode (COMMISSIONING), survey grid, **mission method/speed**, mover, link, LiDAR |
| `src/rr_bringup/rr_bringup/config/hardware.yaml` | hardware template; every `SITE` value must be entered/confirmed (default trailer 16.0 × 2.5 m) |
| `src/rr_bringup/rr_bringup/config/users_demo.yaml` | demonstration accounts (replace before use; `users:=` launch argument) |
| `src/rr_bringup/rr_bringup/config/contract_snapshot.yaml`, `frames_snapshot.yaml` | snapshots of `interface/system/contract.yaml` and `mechanical/common/frames.yaml` used for geometry (outline, mount transform) |
| `src/rr_core/rr_core/data/` | demo head descriptor, synthetic calibration, site profiles (ore demo profile; yellowcake present and unconfigured) |
| launch args | `head_url`, `chassis_url`, `config`, `registry`, `users`, `run_dir`, `resume`, `web_port`, `native` |

## 8. Survey methods and how to select them

Fixed per mission; stored with every result (`survey_methods` in `interface/system/contract.yaml`, DEC-038).

| Method | What it does | Select |
|---|---|---|
| `CONTINUOUS_SCAN` | constant-speed serpentine scan, no stops; each cell credited with its swept exposure | `mission: {method: CONTINUOUS_SCAN, speed: 0.10}` |
| `SEARCH_THEN_COUNT` | ratemeter search at survey speed; on alarm follow the peak ≤ 0.15 m, stop, centre the alarming lane and take a scaler count (`count_policy` INLINE) or queue the spot for after the pass (DEFERRED) | `mission: {method: SEARCH_THEN_COUNT, speed: 0.10, count_policy: INLINE, ratemeter_alpha: 1e-5, scaler_preset_s: 30}` |
| `STEP_AND_COUNT` | move one station, settle, verified-stationary scaler count, repeat; moving counts archived but uncredited. Station pitch default **0.080 m** from contract `survey_methods.STEP_AND_COUNT.station_pitch_m` (CR-05 accepted: aperture length 0.10 m − 2 × 10 mm erosion, so credited footprints abut) | `mission: {method: STEP_AND_COUNT, station_preset_s: 10}` (override `station_pitch_m` only deliberately) |

Set it in the config YAML (`config:=` launch argument) or, for the stand-alone simulator,
`tools/run_sim.sh --method SEARCH_THEN_COUNT`.

### 8.1 Coverage pattern and mission time for a 2.5 × 16 m trailer (calculated)

From `rr_coverage/planner.py` with the demo descriptor geometry (4 lanes, 80 mm wide, pitch
87.5 mm, position allowance e = 10 mm) and the frames.yaml outline (in-place turn radius 0.278 m):

| Quantity | Value |
|---|---|
| Passes | 7 pairs; each pair = pass A (+x) and pass B (−x) offset by half a lane pitch **0.04375 m**, so every eroded seam of A lies under a lane centre of B; plus short end-cap passes (28 tasks) |
| Seam overlap | 16.25 mm per side (eroded lane 60 mm vs eroded seam 27.5 mm) |
| Pair stride / overlap | 0.310 m stride, 56 mm overlap between neighbouring pairs |
| Outermost track | |y| = 0.952 m (turn radius + 20 mm margin from the wall) |
| Residual strips | left wall 0.137 m, right wall 0.137 m, door end 0.121 m, bulkhead end 0.051 m → predicted covered fraction **0.881** of the floor; strips reported as residual rectangles (CR-06) |

Estimated mission time (planner estimate: passes + turns + retreats + lateral shifts; no recharge, no holds):

| Method | Setting | Estimate |
|---|---|---|
| CONTINUOUS_SCAN | 0.10 m/s | 2695 s ≈ **45 min** (does not meet the 0.20 Bq/cm² goal with the demo calibration) |
| CONTINUOUS_SCAN | 0.03 m/s | 7760 s ≈ **2.2 h** |
| SEARCH_THEN_COUNT | 0.10 m/s search | ≈ **45 min + ~40–110 s per alarm** (30 s preset, ≤ 100 s adaptive, plus stop/reverse/realign) |
| STEP_AND_COUNT | 10 s preset, 0.080 m pitch (contract default) | 34 103 s ≈ **9.5 h** (pack swaps expected; at the former 0.10 m pitch: 27 824 s ≈ 7.7 h with 20 mm uncredited stripes) |

Source: `evidence/plan_2.5x16.json`, regenerated by `tools/test.sh plan` (`tools/plan_report.py`). Evidence class: calculated.

## 9. Where data lands

| What | Where |
|---|---|
| Raw archive of a run | `run_dir` (launch arg / `--run-dir`; default `/tmp/rr_runs/run-<timestamp>` **inside the container** — pass a path under the repository or a mounted volume to keep it): `run.json`, `journal/e<epoch>-<n>.seg` (sealed, SHA-256 in `journal/index.ndjson`), `checkpoint.json` |
| Export | `<run_dir>/export/` (UI *Export survey*, `mission/export` service): `cells.csv`, `cells.geojson`, `gates.csv`, `poses.csv`, `flags.json`, `observations.json`, `residuals.json`, `gaps.json`, `grid.json`, `transforms.json`, `calibration.json`, `profile.json`, `map_activity.svg`, `map_coverage.svg`, `coverage.png`, `summary.txt`, `survey_manifest.json`, `MANIFEST.sha256.json` |
| Test evidence | `evidence/<scenario>/evidence.json` + maps + `summary.txt`; `evidence/ui/` |

## 10. Replay

```bash
tools/replay.sh <run_dir> <out_dir>      # out_dir is replaced
```

Rebuilds every export product from the journal (raw head wire stream, recorded poses, supervisor
marks) under the archived profile/calibration. Scenario s08 checks that two replays reproduce the
live export bit for bit. The trajectory is replayed as recorded; LiDAR scans are not archived.

## 11. Traceability

Requirement and verification IDs from `planning/requirements.csv` and `planning/verification.csv`.
"Exercised by" means the test exercises the behaviour in simulation; none of these closes a
verification item, which need the hardware and procedures listed in `verification.csv`.

| ID | Subject | Exercised by |
|---|---|---|
| RQ-012 / VT-007 | Localization and timing | s09_timing (clock-fit bound), s01/native_s01 (revisit error vs truth), s04 (localisation hold), `test_clockfit.py` |
| RQ-013 / VT-008 | Whole-floor accounting | s01, s04a/b (blocked strip → residual), s10, `test_processing.py` (reason codes, residual rectangles) |
| RQ-014 / VT-008 | Seam, perimeter and wall strips | s01 / native_s01 (seam hotspot, interior bands fully covered), `evidence/plan_2.5x16.json`, `test_processing.py` |
| RQ-021 / VT-020 | Map in Bq/cm² | `test_estimator.py` (incl. cross-test vs `analysis/radiometry/rrrad`), s01 exports |
| RQ-022 | Moving sensitivity | s01 (0.03 m/s, median D#), `test_estimator.py`; goal not met at 0.10 m/s (STATUS) |
| RQ-023 / VT-022 | Hotspot and uncertainty decisions | s01, s10, s11 INLINE/DEFERRED (scaler counts), `test_estimator.py` |
| RQ-024 / VT-019, VT-033 | Host/time contract, handshake, identity | `test_head_link.py`, `test_wire_descriptor.py`, s02, native_s02, s09 |
| RQ-025 / VT-019 | Acquisition loss and overload | `test_head_link.py` (CRC, duplicate, gap, reset), s02 / native_s02 |
| RQ-026 / VT-020 | Replay and raw records | s08_replay, s12 |
| RQ-027 | Heat map and report | s01, s08 exports (CSV, GeoJSON-like, SVG, PNG, summary, manifest) |
| RQ-035 / VT-021 | Profile units and change control | s06 (RP-only versioned edits, mission snapshot), `test_estimator.py`, `test_web.py` (RP role) |
| RQ-036 | Pilot and release authority | `field_use_approved: false` banner/products (all scenarios, `ros` smoke); governance itself not software |
| RQ-037 / VT-025, VT-033 | Head independence and emulation | native_s01/s02 (native emulators), all scenarios (Python fakes), `ros` smoke |
| RQ-038 / VT-026 | Data continuity and resume | s12_reboot_resume, s02 (new epoch / attachment), `test_processing.py` |
| RQ-039 / VT-027 | Guided hotspot tour | s01 / native_s01 (Next, AT_SPOT, Expose 0.35 m, Park), s05, s07, UI screenshots |
| RQ-040 / VT-029 | Technician close approach | s05 (person beside / in path), s03 |
| RQ-041 / VT-028 | Shared browser UI | `test_web.py` (roles, lease, exactly-once, SSE, server-side interlock, demo marking), s07, `ros` smoke (web), `evidence/ui/` |
| RQ-042 / VT-028 | Local controls and indications | s03 (protective stop, local REARM only), s06 (Charge/Service), simulated local panel |
| RQ-043 / VT-029 | Unattended survey | s01, s03, s04 (complete scan with holds); qualification not in software scope |
| RQ-050 / VT-034 | Findable revisit marks, pose literacy | s01 (named locations, revisit error), UI status page (pose in trailer frame, uncertainty) |
| RQ-051 / VT-029, VT-034 | Shared-space scanning and guidance | s05, s03 |
| VT-025 | ROS and platform independence | `ros` smoke (ROS graph), native runs (no ROS in the loop) |

## 12. Known limitations

Carried from `STATUS.md` (read that file for the current, complete list):

- One composed robot node; localisation, mapping, coverage, guidance and web are libraries inside
  `robot_node`. The stand-alone `rr_head_driver` / `rr_chassis_bridge` nodes and the `GuidedVisit`
  action server are built but not exercised by any test. No lifecycle nodes.
- Wall strips ~0.14 m per wall stay unsurveyed (outer tracks limited by in-place turns, swept radius
  0.278 m; CR-06, logged by the lead as **IB-29**, decision deferred — a peel-off / reverse-entry lane
  change would cut it to ~44 mm). Keep-outs are not planned around; blocked strips are deferred and
  retried once, no path search.
- Continuous scan at 0.10 m/s does not meet the 0.20 Bq/cm² goal with the demo calibration.
- Cell statistics (CR-08/CR-09, **IB-31**, MODEL.md owner to decide): footprint-weighted sums use the Poisson
  form, which is conservative; lane combinations use the exact per-lane threshold combined in normal form
  (method string `poisson-exact-per-lane/normal-combination` stored per cell).
- TF: the robot node publishes `map → base_link` only, no separate continuous `odom` frame (CR-11, logged by
  the lead for a later decision).
- LiDAR: no de-skew; 12 m range and noise are assumptions. Along-trailer (x) position comes only from an end
  wall inside LiDAR range; with doors open and the bulkhead out of range x is odometry only and credit is
  withheld once the budget is exceeded (CR-07, **IB-30**: site rule — closed doors or a removable target).
- Replay uses the recorded trajectory (raw scans are not archived).
- Web: **plain HTTP, demonstration accounts, no TLS, no real authentication, no re-authentication on
  hand-off** — required before field use.
- Serial transports untested (no hardware). Head DIAG archived but unused.
- `colcon test` not part of the verified set.
- Real-time tests (`ros`, `native`) are timing-sensitive on a loaded host; see STATUS "Failed or flaky".

Contract change requests: [`CONTRACT_CHANGE_REQUESTS.md`](CONTRACT_CHANGE_REQUESTS.md). UI changes vs
the 0.3 operator document: `software/Operator_Interface_0.4_delta.md`.

## 13. Observed results

See `STATUS.md` → "Verification log" for the counts and key numbers observed at close-out, and
`evidence/*/evidence.json` for every check.
