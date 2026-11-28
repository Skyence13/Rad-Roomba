# ros2_ws — Rad Roomba robot software (design 0.4)

ROS 2 Jazzy workspace for the Rad Roomba floor-survey robot: head link, chassis link, wall-referenced
localisation, coverage planning and mission supervision for three survey methods, count-to-floor
mapping per `analysis/radiometry/MODEL.md` **revision 5**, hotspot flags, guided revisit (Next / Expose spot /
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
| `tools/test.sh scenarios` | 16 end-to-end scenarios against the Python protocol fakes, deterministic seeds; rewrites `evidence/s*/` | ~10–20 min |
| `tools/test.sh native [n01] [n02] [n15] [n03]` | scenarios 1, 2 and 15 (default: n01 n02 n15) and step-and-count (`n03`, opt-in) against the native firmware emulators, real time; rewrites `evidence/native_*/`. Emulators are taken from `build/fw/{head,chassis}` when built there (below), else `firmware/*/build` | ~12 min for the default set, ~9 min for n03 |
| `tools/test.sh plan` | calculated 2.5 × 16 m plan and mission times → `evidence/plan_2.5x16.json` | seconds |
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
# into the workspace (git-ignored ros2_ws/build/fw; preferred by tools/test.sh native)
cmake -S firmware/head -B ros2_ws/build/fw/head -G Ninja && cmake --build ros2_ws/build/fw/head -j2
cmake -S firmware/chassis -B ros2_ws/build/fw/chassis -G Ninja && ninja -C ros2_ws/build/fw/chassis -j2
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
| `src/rr_bringup/rr_bringup/config/contract_snapshot.yaml`, `frames_snapshot.yaml` | snapshots of `interface/system/contract.yaml` and `mechanical/common/frames.yaml` used for geometry (outline, mount transform). The contract snapshot is **generated** (`tools/test.sh snapshot`, i.e. `tools/snapshot_contract.py`; `--check` reports staleness) and `rr_bringup/test/test_config.py` fails when any of its fields differs from the contract; the frames snapshot is still a plain copy (byte-identical to `mechanical/common/frames.yaml` at 2026-11-27; its header says draft4, as does the repository file) |
| `src/rr_core/rr_core/data/` | demo head descriptor, synthetic calibration, site profiles (ore demo profile; yellowcake present and unconfigured) |
| launch args | `head_url`, `chassis_url`, `config`, `registry`, `users`, `run_dir`, `resume`, `web_port`, `native` |

## 8. Survey methods and how to select them

Fixed per mission; stored with every result (`survey_methods` in `interface/system/contract.yaml`, DEC-038).

| Method | What it does | Select |
|---|---|---|
| `CONTINUOUS_SCAN` | constant-speed serpentine scan, no stops; each cell credited with its swept exposure | `mission: {method: CONTINUOUS_SCAN, speed: 0.10}` |
| `SEARCH_THEN_COUNT` | ratemeter search at survey speed; on alarm follow the peak ≤ 0.15 m, stop, centre the alarming lane and take a scaler count (`count_policy` INLINE) or queue the spot for after the pass (DEFERRED) | `mission: {method: SEARCH_THEN_COUNT, speed: 0.10, count_policy: INLINE, ratemeter_alpha: 1e-5, scaler_preset_s: 30}` |
| *(all methods)* | wall tracks along the side walls (§8.1) | `plan: {wall_track_entry: reverse_entry}` (default) or `in_place` |
| `STEP_AND_COUNT` | move one station, settle, verified-stationary scaler count, repeat; moving counts archived but uncredited. Station pitch default **0.080 m** from contract `survey_methods.STEP_AND_COUNT.station_pitch_m` (CR-05 accepted: aperture length 0.10 m − 2 × 10 mm erosion, so credited footprints abut) | `mission: {method: STEP_AND_COUNT, station_preset_s: 10}` (override `station_pitch_m` only deliberately) |

**Review queue** (site-profile field `review_queue_policy`): `ALARM_ONLY` (default) queues only
scan alarms at the profile's `alpha_scan`; non-alarming cells with D# above the goal are shown as
*insufficient sensitivity* and reported, not queued. `ALL_UNRESOLVED` queues every cell not cleared at
the investigation level (previous behaviour). Stored per cell in `cells.csv` and in the manifest.

Set it in the config YAML (`config:=` launch argument) or, for the stand-alone simulator,
`tools/run_sim.sh --method SEARCH_THEN_COUNT`.

### 8.1 Coverage pattern and mission time for a 2.5 × 16 m trailer (calculated)

From `rr_coverage/planner.py` with the demo descriptor geometry (4 lanes, 80 mm wide, pitch
87.5 mm, position allowance e = 10 mm) and the frames.yaml / contract outline (body half-width
0.146 m, head half-width 0.175 m, in-place turn radius 0.290 m, contract 0.4.0-draft7 `swept_radii_m.tail_corner`):

| Quantity | Value |
|---|---|
| Interior passes | 7 pairs; each pair = pass A (+x) and pass B (−x) offset by half a lane pitch **0.04375 m**, so every eroded seam of A lies under a lane centre of B; plus short end-cap passes (28 tasks) |
| Seam overlap | 16.25 mm per side (eroded lane 60 mm vs eroded seam 27.5 mm) |
| Pair stride / overlap | 0.306 m stride, 60 mm overlap between neighbouring pairs |
| Pivot-clear band | \|y\| ≤ 0.940 m (turn radius + 20 mm from the wall); every in-place pivot happens inside it |
| Wall tracks (`wall_track_entry: reverse_entry`, default) | per wall one more pair at \|y\| = **1.045 m** (outer, +x) and 1.001 m (inner, −x): head half-width 0.175 + wall margin 0.030 + tracking tolerance 0.005 m from the wall. Entered by **reversing along a 0.09 rad diagonal** from the band (about 1.0 m / 0.5 m long), small align pivot, pass, back-off, small peel pivot, forward diagonal back to the band. Every primitive is checked in the planner with the swept rectangle outline (body + head + tail) against the floor less the margins; min clearance 0.0 m by construction (the 5 mm tracking tolerance is reserved on top). No credit on the manoeuvre. |
| Residual strips | **left / right wall 0.049 m** each (0.137 m with `in_place`), door end 0.121 m, bulkhead end 0.051 m → predicted covered fraction **0.951** (0.881 with `in_place`); strips reported as residual rectangles |

Estimated mission time (planner estimate: passes + turns + retreats + lateral shifts + wall-track
manoeuvres; no recharge, no holds):

| Method | Setting | Default (`reverse_entry`) | `in_place` | Wall tracks add |
|---|---|---|---|---|
| CONTINUOUS_SCAN | 0.10 m/s | 3560 s ≈ **59 min** | 2695 s ≈ 45 min | +865 s |
| CONTINUOUS_SCAN | 0.03 m/s (meets the median D# goal in s01) | 10 061 s ≈ **2.8 h** | 7760 s ≈ 2.2 h | +2301 s |
| SEARCH_THEN_COUNT | 0.10 m/s search | ≈ **59 min + ~40–110 s per alarm** (30 s preset, ≤ 100 s adaptive, plus stop/reverse/realign) + a search-reference pre-roll of about 25 s per attachment at ratemeter alpha 1e-5 (CR-17, simulated) | ≈ 45 min + per alarm | +865 s |
| STEP_AND_COUNT | 10 s preset, 0.080 m pitch (contract default) | 43 848 s ≈ **12.2 h** | 34 103 s ≈ 9.5 h | +9745 s |

At 0.10 m/s the demo calibration does not reach the 0.20 Bq/cm² goal. STEP_AND_COUNT at the former
0.10 m pitch (in_place) was 27 824 s ≈ 7.7 h with 20 mm uncredited stripes between stations (CR-05).
Source: `evidence/plan_2.5x16.json`, regenerated by `tools/test.sh plan` (`tools/plan_report.py`).
Evidence class: calculated. Simulated check of the manoeuvre: scenario s14 (3.0 × 1.0 m: predicted
strip 48.8 mm, achieved 55 mm on 5 mm sub-cells, true outline ≥ +0.5 mm inside the margins).

Rear-field behaviour: the reverse entry relies on the chassis rear proximity field (the LiDAR is blind
behind). A refused or stopped reverse puts the mission in HOLD; after re-arm and Resume the robot
drives back to the entry point along the entry path, the wall track is marked `RESIDUAL`, its strip
is journaled as a residual rectangle and it is **not retried**.

**Assumptions behind the mission-time figures (calculated by `rr_coverage/planner.py`, `tools/test.sh plan`; for quoting in the architecture document).** Nothing here is measured.

| Input | Value used |
|---|---|
| Floor | 16.0 m long (door end x = 0, bulkhead x = 16 m) × 2.5 m wide, empty, no keep-outs, no blocked strips, doors closed |
| Head | 4 lanes, 80 mm wide, pitch 87.5 mm, aperture 100 mm along travel; credited footprint eroded by the 10 mm position allowance per side (eroded lane 60 mm); passes come in pairs offset by half a pitch (43.75 mm) |
| Robot outline | body half-width 0.146 m, head half-width 0.175 m, in-place turn radius 0.290 m (contract draft7); margins: wall 0.03 m, turn 0.02 m, front 0.03 m, door 0.10 m, tracking tolerance 0.005 m |
| Plan | 7 pass pairs (A +x, B −x) with end caps = 28 tasks, plus 4 reverse-entry wall tracks; no re-passes |
| Speeds | scan 0.10 m/s (or 0.03 m/s as stated); transit 0.10 m/s; reverse 0.05 m/s; yaw 0.25 rad/s (contract maximum 0.30) |
| Time model | passes at scan speed + one 180° pivot per pair and three half-pitch shifts per pair (π / yaw rate each) + one retreat per pass ((turn radius − front + 0.02 m) / 0.05 m/s + 2 s) + lateral shifts + wall-track manoeuvres + 1.5 s pre-motion alert once |
| Not in the time | recounts and Expose/Next visits, ratemeter alarm follow-ups, blocked-strip waits, holds and re-arms, charging / pack swaps, set-up, brake test, review |
| Step and count | station pitch 0.080 m (contract), settle 0.5 s, preset count 10 s, plus 1.0 s per station and pitch / speed travel |
| Search then count | search stage only (continuous at the search speed); each alarm adds its scaler count (30 s preset, ≤ 100 s adaptive) and a reverse/realign, not included |
| Results | continuous 0.10 m/s 3598 s (1.0 h); 0.03 m/s 10 099 s (2.8 h); step and count, 10 s preset, 43 886 s (12.2 h); breakdown at 0.10 m/s: passes 2171 s, turns 352 s, retreats 122 s, shifts 55 s, wall tracks 896 s |

### 8.2 Long trailers with open doors (site rule, IB-30)

The along-trailer (x) reference comes from an end wall seen by the LiDAR. If the trailer is longer
than `lidar.range_max` (default 12 m, an assumption), survey motion requires either
`trailer.door_closed: true` or a removable flat target placed across the door end with its distance
from the door threshold in `trailer.door_target_x_m` (the localiser treats it as the door wall, the
planner treats it as the door end, the floor behind it is a residual). Otherwise Arm/Start/Resume are
refused with `ALONG_TRACK_REFERENCE`. The LOCALIZATION hold (2σ budget exceeded) stays in force in
all cases. Scenario s13 (LiDAR range set to 2 m on a 3 m section).

## 9. Where data lands

| What | Where |
|---|---|
| Raw archive of a run | `run_dir` (launch arg / `--run-dir`; default `/tmp/rr_runs/run-<timestamp>` **inside the container** — pass a path under the repository or a mounted volume to keep it): `run.json`, `journal/e<epoch>-<n>.seg` (sealed, SHA-256 in `journal/index.ndjson`), `checkpoint.json` |
| Export | `<run_dir>/export/` (UI *Export survey*, `mission/export` service): `README.txt` (how to read it, what not to conclude), `cells.csv` (recorded results, status, provisional values beside them, uncertainty components, footprint dilution, U_null fields), `cell_members.csv` (every member lane-gate with weight and erosion), `cells.geojson`, `gates.csv` (incl. GATESTAT columns, erosion, speed), `poses.csv`, `flags.json`, `observations.json`, `residuals.json` (incl. `revisit`), `gaps.json`, `grid.json`, `transforms.json`, `calibration*.json`, `profile.json`, `map_activity.svg`, `map_coverage.svg`, `coverage.png`, `summary.txt`, `survey_manifest.json` (software identity of every package, model revision, `footprint_model`, binding per attachment), `MANIFEST.sha256.json`. Every file carries the run id, calibration id(s) and, while `field_use_approved` is false, the marker `synthetic — not for field use` |
| Test evidence | `evidence/<scenario>/evidence.json` + maps + `summary.txt`; `evidence/ui/` |

## 10. Replay

```bash
tools/replay.sh <run_dir> <out_dir>      # out_dir is replaced
```

Rebuilds every export product from the journal (raw head wire stream, recorded poses, supervisor
marks) under the archived profile/calibration. Scenario s08 checks that two replays reproduce the
live export bit for bit. The trajectory is replayed as recorded; the pose-estimate inputs (chassis odometry/IMU
samples `K`, LiDAR scans `S`) are archived as received since 2026-11-28 but not re-fused by the replay.

```bash
python3 tools/recompute_cell.py <run_dir> <ix> <iy> [--calibration cal.json ...] [--profile profile.json]
```

Recomputes one cell's D, D*, D#, decision and status from the archive plus calibration and profile (MODEL.md rev 5 §8;
`rr_core/recompute.py` says which parts are shared with the survey code). s08 checks it against the export.

## 11. Traceability

Requirement and verification IDs from `planning/requirements.csv` and `planning/verification.csv`.
"Exercised by" means the test exercises the behaviour in simulation; none of these closes a
verification item, which need the hardware and procedures listed in `verification.csv`.

| ID | Subject | Exercised by |
|---|---|---|
| RQ-012 / VT-007 | Localization and timing | s09_timing (clock-fit bound), s01/native_s01 (revisit error vs truth), **s13_door_target** (door-end target, ALONG_TRACK_REFERENCE), `test_clockfit.py` |
| RQ-013 / VT-008 | Whole-floor accounting | s01, s04a/b (blocked strip → residual), s10, `test_processing.py` (reason codes, residual rectangles) |
| RQ-014 / VT-008 | Seam, perimeter and wall strips | s01 / native_s01 (seam hotspot, interior bands fully covered), **s14_wall_tracks** (achieved wall strip, outline clearance, rear-field stop), `evidence/plan_2.5x16.json`, `test_processing.py` |
| RQ-021 / VT-020 | Map in Bq/cm² | `test_estimator.py` (incl. cross-test vs `analysis/radiometry/rrrad`), s01 exports |
| RQ-022 | Moving sensitivity | s01 (0.03 m/s, median D#), `test_estimator.py`; goal not met at 0.10 m/s (STATUS) |
| RQ-023 / VT-022 | Hotspot and uncertainty decisions | s01, s10, s11 INLINE/DEFERRED (scaler counts), `test_estimator.py`, `test_review_queue.py` (queue policy) |
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
- Wall strips: ~0.049 m per wall with the default reverse-entry wall tracks (CR-06 / IB-29, owner
  decision 2026-11-26), ~0.149 m with `in_place` (0.137 m at the old 0.278 m radius). A stopped reverse entry leaves the track as a residual.
  Flags seen only by a wall track may be UNREACHABLE for guided revisit / deferred counts (approaches
  are planned inside the pivot band only). Keep-outs are not planned around; blocked strips are deferred
  and retried once, no path search. In-place pivots are planned with the contract swept radius 0.290 m
  (as-built tail incl. rear bumper 0.2892 m, tool-checked on nominal CAD, rounded up; contract draft7); the rectangle
  outline used for route holds and the wall-track checks reaches 0.309 m. Not measured on a built robot.
- Continuous scan at 0.10 m/s does not meet the 0.20 Bq/cm² goal with the demo calibration.
- Cell statistics (**MODEL.md revision 5**, 2026-11-28; data-path review IB-72): S = sum a_j N_j + Z with the footprint
  weights (0.05 lattice) as exact coefficients; rule `linear-exact/combined+per-lane/0.8-0.2`; **predictive threshold**
  (12 posterior nodes of Gamma(N + 1/2, 1/T) of each lane's U_null sub-window, characteristic functions averaged; lanes
  independent; `rr_core/linstat.PredictiveStat`), agreement with `analysis/radiometry/rrrad` ~1e-11 (m = 1, beta and alpha
  classes; `test_rev5.py`). U_null (`rr_core/unull.py`): two sub-windows of >= N_min counts (30/75/125/200 by alpha) nearest to
  the dwell, larger mean; lane window unless it spans > 2 m, then the ratio-scaled four-lane pool; gradient guard (2 %);
  recounts from the other three lanes during the recount; search stage past-only at alpha_scan. **One recorded evaluation per
  cell** after the survey from the complete record (`SurveyProcessor.finalize`), independent of arrival order and live
  schedule; live values are provisional. Each attachment uses its **own bound calibration** (strict identity binding by default;
  `calibration_binding: DEMONSTRATION` for the synthetic record, marked everywhere). Cell status ALARM > NO DECISION >
  INCOMPLETE COVERAGE > SENSITIVITY INSUFFICIENT > ACCEPTABLE; alarms never suppressed; rate saturation (GATESTAT) is an alarm.
  Footprint: aperture eroded by the gate's credited 2 sigma, swept start to end, exact area weights (`footprint_model` in the
  manifest). Cost: about 0.1-0.2 s per cell for the recorded evaluation on this 4-core host (not measured on a CM5).
- Position credit (2026-11-28, review M3/M4): the localiser carries a wheel-scale state (1 % 1 sigma, ASSUMED - tyre tolerance,
  compression, wear; not measured), so the along-track error grows linearly with the distance since the last end-wall fix;
  credit needs x constrained within 3 s, the chassis clock fit valid, no correction above 5 mm (a new trajectory epoch); scans
  are applied at their own time stamp.
- TF: the robot node publishes `map → base_link` only, no separate continuous `odom` frame (CR-11, logged by
  the lead for a later decision).
- LiDAR: no de-skew; 12 m range and noise are assumptions. Along-trailer (x) position comes only from an end
  wall (or the door-end target) inside LiDAR range; between them x is odometry and credit is withheld once
  the budget is exceeded (CR-07 / IB-30 site rule implemented, §8.2).
- Replay uses the recorded trajectory (raw scans are not archived).
- Web: **plain HTTP, demonstration accounts, no TLS, no real authentication, no re-authentication on
  hand-off** — required before field use.
- Serial transports untested (no hardware). Head DIAG archived but unused.
- `colcon test` not part of the verified set.
- Real-time tests (`ros`, `native`) are timing-sensitive: on a host with load average ~9–10 native_s02
  failed 3 times with a chassis CMD_TIMEOUT (DRIVE cadence missed by the single-threaded loop) and
  passed 3 times at low load; the final `tools/test.sh all` under load therefore exited non-zero.
  IB-46 fix: the real-time hosts (`rr_bringup.runtime.Runtime`, `rr_sim.native.NativeSystem`) now run the chassis link
  on its own thread (`config chassis_thread`, `ChassisLink.start_thread`); the virtual-time harness is unchanged.
  Reproduced deterministically by an injected 0.5 s head stall (`rr_bringup/test/test_chassis_thread.py`); the native
  run under load has not been repeated enough to claim the flake is gone.
  Run them on an unloaded host; see STATUS "Failed or flaky".
- Never edit `tools/test.sh` while it is running (bash reads it incrementally; see STATUS).

Contract change requests: [`CONTRACT_CHANGE_REQUESTS.md`](CONTRACT_CHANGE_REQUESTS.md). UI changes vs
the 0.3 operator document: `software/Operator_Interface_0.4_delta.md`.

## 13. Observed results

See `STATUS.md` → "Verification log" for the counts and key numbers observed at close-out, and
`evidence/*/evidence.json` for every check.
