# 01 Operator procedures

**Status of this document.** The robot does not exist yet. These procedures are written from the 0.3 operator documents and the 0.4 software and firmware as designed; they are **proposed** and have never been tried on a robot. The behaviour described for the operator page is `simulated` (ROS workspace on emulators). Nothing here authorises field use: the web service is plain HTTP with demonstration accounts, the shipped calibration and profile data are synthetic and flagged `field_use_approved: false`, braking, personnel-protection, cold and radiometric trials are pending, and the survey profile is owned by the site's radiation-protection program, not by this document.

Baseline documents kept as the reference: `docs/Rad_Roomba_Design.pdf` chapter 02 "Normal survey sequence" (steps 1 to 6), `planning/Survey_Field_Checklist.md` (the field worksheet; use it with this document), `software/Operator_Interface.md` (0.3) and `software/Operator_Interface_0.4_delta.md` (where they differ, the delta describes the 0.4 software). Evidence classes as in `docs/build/README.md`.

## 1. Preconditions that this document cannot supply

| Needed | Owner | State |
|---|---|---|
| Approved site survey profile: material, purpose, units in Bq/cm2, investigation and comparison levels, averaging area, minimum patch, required sensitivity, alpha/beta probabilities, mission allowance | site radiation protection (DEC-001, 002, 012, 015) | open; ore example is a demonstration profile, yellowcake unconfigured |
| Calibration for the head in use (k, b, K with uncertainty and validity envelope) | metrology / RP | none exists (see 02) |
| Operating mode approval and speed caps (shared space, unattended, commissioning) | site safety and operations (DEC-004, DEC-017) | provisional (`interface/chassis_icd.md` section 6.1) |
| Qualified personnel-protection and stopping margins | trials VT-003, VT-004, VT-005, VT-035 | pending |
| Site procedures for trailer immobilisation, door protection, edges, recovery, notification route | site | not defined here |

Until these exist, the robot may only be run supervised in commissioning mode on a guarded fixture. Unattended and shared-space operation are not available.

## 2. Roles and access

Roles `viewer` (read only), `operator` (mission commands, one control lease at a time) and `rp` (profiles and disposition). The operator takes control explicitly ("Take control", "Release control"); the holder's name is shown on every client; taking over a held lease asks for confirmation and is written to the audit log (`Operator_Interface_0.4_delta.md` section 1). The lease ends if the holder logs out or the page stops receiving the event stream for 5 s. Commands carry fresh ids; a retry returns the same receipt; a command sent while traction is inhibited is rejected with the reason and is not kept. Access is by phone, tablet or laptop on the site network or the robot's access point; Wi-Fi is the service path (IB-07). **Not implemented and required before field use:** TLS, site accounts with password hashes, re-authentication on hand-off (`ros2_ws/README.md` section 4; delta section 9).

## 3. Pre-use checks (every shift, proposed)

Follow `planning/Survey_Field_Checklist.md` "Setup and arming" for the site-side items. Robot-side checks:

| # | Check | Expected | Source |
|---|---|---|---|
| 1 | Trailer immobilised, floor inspected (snow, standing water, frost, debris, splinters, ridges), boundary and edges defined, exclusions marked | per site procedure | checklist; baseline step 1 |
| 2 | Robot lifted only with drive inhibited; integral grip, battery latch, charge inlet cap, plugs, tyres, caster, head mount, connector retention, low bumper, skids/guard, entrance window inspected; carry-over contamination checked | no damage, nothing loose | checklist |
| 3 | Warm start: pack and head temperatures recorded; the robot starts warm and stays warm in the cold (see section 8) | recorded in the run | baseline step 2; RQ-029 |
| 4 | Master selector to RUN; panel lights: boot shows all five LEDs and one chirp, then READY slow blink (STANDBY) | `chassis_icd.md` section 6.7 | |
| 5 | Local stops exercised separately: E-stop, HANDS-ON, PAUSE, each head rail zone and body bumper (on an approved fixture), dock and charge cover | each opens the chain or holds as designed; none restarts by itself | checklist; `chassis_icd.md` 5.7 |
| 6 | Head identity on the host: type, serial, geometry and calibration ID from the handshake; continuous valid link; raw counts and live time arriving; clock lock; local storage writing | all present; otherwise Arm is refused | delta section 3 step 3 |
| 7 | Detector source-response check and background (method in 02): record the result against the head's acceptance band | within the site band; a failed lane is withheld from survey | baseline step 2; `head_icd.md` section 7 |
| 8 | Window inspected for damage; standoff regular; contamination check of the robot (see 03) | no damage; clean | |
| 9 | Pack voltage and state; temperatures; reserve for the planned mission | above the stop threshold with reserve | section 8 |
| 10 | Local indications compared with the web page: ready/hold, stop, charger/service | match | checklist |
| 11 | Confirm that a network reconnect or reset leaves motion disarmed until deliberately enabled | disarmed | checklist |

Annunciator codes (`interface/chassis_icd.md` section 6.7; pattern and colour both): READY steady = armed idle; READY slow blink = standby; MOVING fast blink with 4 Hz buzzer = pre-motion alert (1500 ms default) then steady; HOLD/WAITING steady = hold, fast blink = protective stop, two flashes per 2 s = hardware inhibit; FAULT steady = chassis fault, slow blink in any mode while a warning flag is active; CHARGE/SERVICE steady or slow blink while charging; two flashes = LAB. The REARM lamp blinks when a press would have an effect. The HANDS-ON lamp comes from the hardware chain state.

## 4. Start sequence (delta section 3)

0. **Along-trailer reference** (section 6 below).
1. Place the robot on the surveyed start mark and **Register datum**. It is required again after every restart or pack swap; arming is refused without it.
2. Press **REARM** on the robot. Run **Preflight / brake test** (selects the profile, switches head power on, runs the stationary brake test, which drops the latch on purpose; takes about 2.2 s). Press **REARM** again.
3. **Arm** is accepted only when the recorder is writing, the head is identified with a calibration, both clock fits are within 10 ms, the datum is registered and localisation is inside its budget. The page lists what is missing (codes in [04_fault_isolation.md](04_fault_isolation.md)).
4. **Start.** The first motion after rest is preceded by the chassis' own 1.5 s alert (buzzer, MOVING indicator flashing, wheels held).

The brake test proves that the switching elements work; it does not prove braking torque or that the brake resistor path conducts (`chassis_safety_chain.md` section 7). A passed test counts only until the next MCU boot.

## 5. Survey methods

The method is fixed for a mission and shown with every result (contract `survey_methods`, DEC-038). Times are `calculated` by the planner for a 2.5 x 16 m floor, no recharge and no holds (`ros2_ws/README.md` section 8.1, `evidence/plan_2.5x16.json`): the architecture document gives other figures for the same methods because it used different inputs (`docs/architecture/SYSTEM_ARCHITECTURE.md` section 8a: 46 min search, 2.8 h continuous scan, 5.5 to 9.7 h step-and-count); use the workspace numbers for the current planner, and expect them to change.

| Method | What the operator does | Default parameters | Estimated time |
|---|---|---|---|
| **Search then count** (ratemeter search, then scaler count) | Select `SEARCH_THEN_COUNT`, policy INLINE or DEFERRED. The ratemeter alarms at the profile's set-point; on an alarm the robot follows the rate up to 0.15 m to the peak. INLINE: stops, reverses to centre the alarming lane and takes a scaler count. DEFERRED: queues the spot and counts after the pass or the scan. | search 0.10 m/s, ratemeter window 1 s, scaler preset 30 s, adaptive maximum 100 s | about 59 min plus 40 to 110 s per alarm (default wall tracks); floor seen only by the search is reported at the search-stage detection limit |
| **Step and count** | Select `STEP_AND_COUNT`. The robot moves one station, settles, takes a static scaler count when the chassis reports stationary, repeats. Only static counts earn coverage; moving counts are archived, uncredited. A count is discarded and repeated if the chassis did not report stationary for the whole count or a stop/inhibit event fell inside it. | station pitch 0.080 m (aperture 0.100 m less 2 x 10 mm erosion allowance), settle 0.5 s, preset 10 s, adaptive maximum 60 s | about 12.2 h at 10 s preset (calculated; `ros2_ws/README.md`); several pack swaps |
| **Continuous scan** | Select `CONTINUOUS_SCAN`. Constant speed, no stops. | 0.02 to 0.20 m/s; speed chosen so the dwell meets the goal | 59 min at 0.10 m/s; about 2.8 h at 0.03 m/s |

The step-and-count station pitch appears as 0.080 m in the contract and the ROS workspace, as "100 mm stations" in `Operator_Interface_0.4_delta.md` section 4 and as 0.10 m in `electronics/analysis/power_budget.md`; the contract wins (reported to the lead).

**Sensitivity statements the operator may rely on (and no others).** With the *demonstration* calibration (synthetic, not usable for decisions): continuous scan at 0.10 m/s does not meet the 0.20 Bq/cm2 detection goal (simulated D# about 0.35 per 10 cm cell); about 0.03 m/s is needed (delta section 4). The detectability study (`analysis/radiometry/report/detectability_report.md` section 1; `calculated`, assumed response K = 24 s-1 per Bq/cm2, 80 cm2 aperture, no detector exists): a single 1 s pass does not reach 0.20 Bq/cm2, compensated or not; the alpha channel is not a scanning channel at 10 mm standoff and is at best a stationary confirmation channel with controlled standoff. Cells that miss the goal are drawn as "insufficient sensitivity", never as clean.

**Ratemeter search at a low false-alarm setting.** The moving ratemeter alarm is evaluated at the mission's `ratemeter_alpha` (scenario default 1e-5), which defaults to the profile's scan-stage alpha. A detection-limit figure or a per-decision alpha is a site-profile quantity (02).

**Pre-motion alert in step-and-count.** `alert.rest_ms` defaults to 5 s, shorter than a station (0.5 s settle plus 10 s count), so each hop would be preceded by the full 1.5 s alert. The mission supervisor raises `alert.rest_ms` by a logged `CONFIG_SET` for the series: one full alert at the start and a short chirp per hop (owner decision 2026-11-26). Whether that is acceptable with people in the trailer is an operating decision (RQ-051), not a firmware one.

**Scan view** (delta section 5): coverage quality, activity (signed Bq/cm2 per 10 cm decision cell, colour clipped, data not) and detection limit are separate layers; nothing is interpolated between cells; turns earn no coverage; wall strips (about 0.049 m per wall with reverse-entry wall tracks, 0.149 m in place), the door threshold strip and the bulkhead strip are planned residuals listed with position and area. A red banner marks synthetic calibration or profile data on the page and on every export.

**Blocked strip.** An object within 0.8 m in the swept path makes the robot wait without a latch; after the patience time the strip is deferred, marked blocked and retried once after the other passes. A person inside the protective zone (0.25 m look-ahead plus margin) latches a protective stop.

## 6. Long trailers with open doors

If the trailer is longer than the configured LiDAR range (default 12 m, an assumption) the along-trailer position needs a reference: **doors closed** (`trailer.door_closed: true`) or a **removable flat target across the door end**, with its distance from the door threshold entered as `trailer.door_target_x_m`. The LiDAR treats the target as the door-end wall; the floor between the threshold and the target is reported as an unsurveyed residual. Without either, Arm, Start and Resume are refused with `ALONG_TRACK_REFERENCE`. Independently, localisation holds the mission (`LOCALIZATION`) whenever position uncertainty exceeds its budget (hold above 0.040 m at the detector row; credit only below 0.010 m: `rr_localization/estimator.py` defaults). Operator action: place the target flat and square across the door end, measure its distance from the threshold and enter it before arming; do not trust the LiDAR range figure (12 m is an assumption, IB-30). The target must not be an obstruction to the swept head; its stability is not defined.

## 7. Review queue

The queue policy is a site-profile setting `review_queue_policy`, shown in the queue header and stored with every cell.

- `ALARM_ONLY` (default, also when the profile lacks the field): only cells whose statistic exceeds the decision threshold at the profile's scan-stage false-alarm rate are queued. Cells that do not alarm but whose detection limit D# is above the detection goal are drawn "insufficient sensitivity", counted in the residual area and exported with their D#, but not queued. In search-then-count only an alarm leads to a scaler count.
- `ALL_UNRESOLVED`: every cell that cannot be cleared at the investigation level is queued.

Review actions (delta section 6): **Next** parks the lane that produced the flag over the saved footprint (verified against 10 mm with the localisation uncertainty shown) and refuses if the head has been changed since the scan; **Expose spot** reverses 0.35 m and states where the point is relative to the head's front edge and the centreline, refused if there is no room, and held by the rear field if someone is behind (LiDAR is blind to the rear); **Repeat** takes a linked stationary count; **Skip** needs a reason; **Park** returns to the start mark and leaves unvisited items open. A route hold, blocked path, poor localisation or loss of the control lease leaves the item open. Flags seen only by a wall track may be unreachable (IB-29).

For hands-on work (wipe, hand probe, marking) the operator uses the HANDS-ON inhibit and verifies by the prescribed local means that traction is stopped **before** reaching within reach of the head, wheels or moving path (checklist "Survey and holds"; baseline guided review step 4). Releasing the inhibit, clearing the field or reconnecting a browser never restarts motion; a fresh Next, Expose spot or Park is required.

## 8. Pause, stop, re-arm

| Event | Robot response | Cleared by |
|---|---|---|
| **E-stop**, HANDS-ON, master selector out of RUN, charge cover open or plug link, head undocked, head loop open/short or J1 unplugged, LAB extension, body bumper, watchdog, ARM_PERMIT withdrawn | hardware latch drops: VMOT removed, motors across brake resistors (no power or firmware needed); reasons latched (MODE_NOT_RUN, ESTOP, HANDS_ON, CHARGER, HEAD_UNDOCKED, HEAD_LOOP_OPEN, HEAD_LOOP_SHORT, J1_ABSENT, LAB_KEY, BODY_BUMPER, WATCHDOG, MCU_NOT_READY, VMOT_FAULT) | **only the REARM button on the robot**, with every element healthy; the page refuses a remote re-arm (`LOCAL_REARM_REQUIRED`) |
| Software protective stop: cliff, rear field, look-ahead, stale or disagreeing sensor, command timeout, host link lost, stall, encoder or IMU fault, tilt, low battery, temperature, brake-test failure, host-asserted FIELD_*/HEAD_LINK/LOCALIZATION | ramps to rest, latches the reason, three beeps | `REARM_SW` by the controlling operator once the cause is gone, or the local REARM button; never clears by itself |
| **Pause** pressed on the robot, or web Pause or lost controlling session during a guided move | controlled stop (0.40 m/s2), HOLD, one beep | `REARM_SW` by the controlling operator, or the local button (owner decision 2026-11-26; a program control, not a hardwired inhibit; RSK-034) |

Re-arming never moves the robot. After any hold the mission stays in HOLD until a fresh **Resume** (survey) or a fresh Next/Expose/Park (review). The hardware latch and the E-stop/HANDS-ON are local only: a bumper or E-stop trip in an unattended mission ends it until someone attends (DEC-026). Local-only means a person must go to the robot; plan retrieval for the mode in use. After an E-stop: clear people and tools from the movement envelope, release the E-stop (it never restarts motion), re-register the datum if the pose is lost, then the full start sequence.

An E-stop is not a "protective function" in the sense of a certified system, and the layered protection has limits stated in `docs/build/04_bring_up.md` section 9 (the MCU has no forward or sideways personnel ranging; stopping inside the rail travel is not demonstrated).

## 9. Battery and charging, including the cold

Pack: LiFePO4 12.8 V nominal, 12 Ah (Power-Sonic PSL-SC-12120); discharge range -20 to +60 C, **charge range 0 to +45 C** (pack datasheet, `electronics/modules/battery_pack_and_coupler.md`).

- **Charge inhibit below +5 C.** On-board charging is refused when the pack-surface NTC is below about +5 C (calculated threshold +5.3 C with 2 K hysteresis in `electronics/analysis/chassis_design_notes.md` section 1 and `circuit_description.md`; the contract says 5 C): a hardware gate that works independently of firmware, with the pack's own BMS as a backstop at 0 C. The charger's firmware limit is not active yet (the LTC4162-F driver is disabled until its register map is verified: IB-05, IB-06; `CHARGER_COMM` is raised). A cold pack must be warmed before it is charged; the bay heater is permitted in Charge/Service for that purpose. The bench charger R10 has no access to the cassette NTC: cold packs must reach room temperature first. A pack with its BMS latched under-voltage may not be woken by the on-board charger (design assumes not; VT-040).
- **Charge/Service.** Opening the inlet cover (or a plug link in the plug) opens the chain; charging has priority over LAB. In Charge/Service the page disables every mission and review button and **both the server and the chassis refuse every traction command**; head power is forced off. Export, audit log and RP profile edits remain. Unplugging leaves the robot inactive until the start sequence is repeated.
- **Charge current and time.** 3.0 A (0.25 C) to 14.4 V; about 3.7 h from the 20 % reserve (`calculated`).
- **Runtime** (`electronics/analysis/power_budget.md` section 3, `calculated`, 12 Ah, 20 % reserve): survey at +20 C 337 min, at -20 C with heaters 125 min; step-and-count at -20 C 139 min; survey at -25 C 100 min. Assumed deliverable fraction 0.80 at -20 C and 0.75 at -25 C: not measured (VT-040, VT-012). The planning rule: keep the motivating 60 min case until measured mission data replace it.
- **Cold rules.** Start warm; -20 C ambient is a warm-start objective, -25 C is a separate stretch test (RQ-029); no overnight cold-soak capability is assumed. TPU tyre traction below -10 C and the caster below -20 C are not assumed (IB-55). The brake relays, the CM5 (lower limit -20 C recalled), JST GH connectors (-25 C recalled) and the SBS50 coupler (-20 C recalled) are unverified in the cold. The chassis stops with `TEMP_RANGE` outside -25 to +60 C (config `temp.min_c`, `temp.max_c`). Battery low: `BATTERY_LOW` when VBAT is below 11.2 V for 5 s (state of charge is not available until the charger driver exists), brown-out logged at 9.5 V.
- **Pack swap.** Park, checkpoint and close the run, isolate the load (selector to OFF is a functional switch-off through MOSFETs, **not isolation**; isolation is removing the pack through the blind-mate coupler and the charge plug), unlatch the pack (open the hatch latch, lift the door off its pegs, pull the plunger knob, unfold the handle, pull back 165 mm: `mechanical/prototype_x1c/assembly.md` removal procedures), cap and segregate the removed pack as prescribed by the site, check the replacement pack's temperature, identity, engagement and latch, restore power deliberately. **Re-register the trailer datum after every pack swap**; a multi-pack survey continues as one record with separate epochs. Do not swap a live or cold pack (RSK-017). Pack shipping needs UN 38.3 documentation (open).

## 10. End of shift

1. Park at the designated safe location; **Park** leaves unvisited review items open.
2. Export the original scan, follow-up notes and unresolved locations (the export carries a manifest and digest); retain per the site's rule (not defined here).
3. Record: head ID, profile, calibration and software revisions, check-source results, pack IDs, temperatures, holds and gaps, flags, residual area.
4. Stop and inhibit drives (E-stop or selector) before retrieval or handling; handle the head window, wheels, skids and tray under contamination control (03); frisk the robot before it leaves a controlled area.
5. Connect the charger only on a warm pack; confirm the charge indication and the drive lockout (checklist "Recovery, battery and disposition").
6. RP disposition and reviewer sign-off: site responsibility.

## 11. Open items

| Item | ID | Status |
|---|---|---|
| Site profile values; mission allowance; recount rule; K definition | DEC-001, 002, 012, 015 | open |
| Calibration, check-source acceptance bands | VT-016; see 02 | not yet defined |
| TLS, accounts, re-authentication; notification route for unattended runs; phone/tablet glove trials; browser-level tests | `Operator_Interface_0.4_delta.md` section 9; IB-49 | open |
| Whether a local pause should require local release | `chassis_icd.md` section 10; RQ-056, RSK-034 | open |
| Pre-motion alert in step-and-count with people present | RQ-051 | operating decision pending |
| Step-and-count pitch stated as 0.080 m, 100 mm and 0.10 m in different documents | contradiction | reported |
| LiDAR range assumption 12 m; target stability | IB-30 | open |
| Charger firmware limit; SoC | IB-05, IB-06 | open |
| Retrieval procedure for a robot stopped in a trailer; edge/doorway protection | DEC-004 | site |
| Planner results to be re-run with the 0.290 m tail radius | IB-48 | pending |
