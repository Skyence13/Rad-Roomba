# Technician interface — changes in design 0.4 (delta to `Operator_Interface.md` 0.3)

Status: implemented in `ros2_ws` and exercised in simulation only (evidence class `simulated`).
`Operator_Interface.md` stays the 0.3 record; where the two differ, this file describes what the
0.4 software does. Nothing here is a qualified safety function.

## 1. Access, roles and control

| 0.3 text | 0.4 behaviour |
|---|---|
| Named accounts, HTTPS, session expiry | Named accounts with roles `viewer`, `operator`, `rp`; cookie session (HttpOnly, SameSite=Strict) with expiry and a per-session request-forgery token. **HTTP only in this build** — TLS, site identity and re-authentication for hand-off are not implemented. The shipped accounts are demonstration accounts. |
| One operator with a control lease | Exactly one session holds the lease. **Take control** and **Release control** are explicit buttons; the holder's name is shown on every client. Taking over a held lease asks for confirmation, is allowed only to an operator and is written to the audit log. The lease ends when its holder logs out or its page stops receiving the event stream for 5 s. |
| Command IDs, last committed result on retry | Every command carries a fresh id. The server executes an id once and returns the same receipt number on every retry; reusing an id for a different command is refused (409). |
| Event stream | Server-sent events. The first event after every (re)connection is the complete current state; while the stream is down the page shows the last state and disables every command button. |
| Journal accepted and rejected commands | Hash-chained audit log (login, take/lose control, every command with role, id, accepted/rejected and reason), also written to the run archive. |

## 2. What can be cleared from the page and what cannot

| Latched condition | Cleared by |
|---|---|
| Hardware latch dropped: E-stop, HANDS-ON, bumper/head loop, undocked head, charger, master switch | **Only the REARM button on the robot.** The page says so and refuses a remote re-arm (`LOCAL_REARM_REQUIRED`). |
| Software protective stop (cliff/rear field, command timeout, host-asserted `FIELD_*`, `HEAD_LINK`, `LOCALIZATION`) | **Re-arm (software)** by the controlling operator once the cause is gone, or the local button. |
| Controlled-stop hold (web Pause, lost controlling session during a guided move) and a **Pause pressed on the robot** | Re-arm (software) by the controlling operator, or the local button (owner decision 2026-11-26). |

Re-arming never moves the robot. After any hold the mission stays in HOLD until a fresh **Resume**
(survey) or a fresh **Next / Expose spot / Park** (review). A command sent while traction is
inhibited is rejected with the reason and is not kept.

## 3. Start sequence (replaces "Start / Resume" preflight detail)

0. **Along-trailer reference (long trailers, site rule IB-30, 2026-11-26).** If the trailer is longer than the configured LiDAR range, survey motion needs either the **doors closed** (`trailer.door_closed: true`) or a **removable flat target placed across the door end**, with its distance from the door threshold entered as `trailer.door_target_x_m`. The LiDAR treats the target as the door-end wall; the floor between the threshold and the target is reported as an unsurveyed residual. Without one of them, **Arm** is refused and the page lists `ALONG_TRACK_REFERENCE`. Independently, localisation still holds the mission (`LOCALIZATION`) whenever the position uncertainty exceeds its budget.
1. Robot on the surveyed start mark → **Register datum**. Required again after every restart or pack swap; arming is refused without it.
2. Press **REARM** on the robot → **Preflight / brake test** (selects the operating profile, switches head power on, runs the stationary brake test, which drops the latch on purpose) → press **REARM** again.
3. **Arm** is accepted only when the recorder is writing, the head is identified with a calibration, both clock fits are within 10 ms, the datum is registered and localisation is inside its budget. The page lists what is missing.
4. **Start**. The first motion after rest is preceded by the chassis' own 1.5 s alert.

## 4. Survey methods (new, DEC-038)

The method is fixed for a mission and shown with every result.

- **Continuous scan** — constant speed. With the demonstration calibration the 0.20 Bq/cm² detection goal is not met at 0.10 m/s (simulated D# ≈ 0.35 per 10 cm cell); about 0.03 m/s was needed with the earlier combined statistic, and with the per-lane rule of MODEL.md rev 3 the simulated median D# at 0.03 m/s is 0.30 Bq/cm² (goal not met). Cells that miss the goal are drawn as *insufficient sensitivity*, never as clean.
- **Search then count** — ratemeter view per lane with the alarm set-point. On an alarm the robot follows the rate for up to 0.15 m to find the peak, then either stops, reverses to centre the alarming lane and counts (*inline*), or queues the spot and counts after the passes (*deferred*). Floor seen only by the search is reported at the search-stage limit.
- **Step and count** — 80 mm stations (contract default), settle, static count. Only static counts earn coverage; a count is discarded and repeated if the chassis did not report "stationary" for the whole count or any stop/inhibit event fell inside it. One full pre-motion alert at the start of a series and a chirp per hop (the supervisor raises `alert.rest_ms` with a logged setting change and restores it).
- A cell is flagged when any contributing lane exceeds its own threshold at alpha/m (m = lanes in the cell); the quoted D* and D# are the smallest per-lane values; `cells.csv` stores the rule `per-lane-exact/any-lane/alpha-over-m`, m, per-lane thresholds and flagging lanes.
- Scaler results list outcome, D ± u, D*, D#, live time and the threshold method. An outcome is *not detected* only when D# is below the goal; a marginal value is *inconclusive*.

## 5. Scan view

- Three separate layers: **coverage quality** (patterns: diagonal = unvisited, crosses = invalid data, dots = insufficient sensitivity, bars = blocked, solid = acceptable), **activity** (signed Bq/cm² per decision cell; the colour clips, the data do not), **detection limit**.
- Cells are 10 cm decision cells; nothing is interpolated between them. Coverage is accounted on 5 mm sub-cells with the footprint shrunk by the 10 mm position allowance; turns earn no coverage.
- Wall strips (~0.05 m per wall with the default reverse-entry wall tracks, ~0.15 m with `in_place`, in a 2.5 m trailer; calculated), the door-threshold strip and the bulkhead strip are planned residuals and are listed with position and area.
- **Blocked strip**: an object seen within 0.8 m in the swept path makes the robot wait without a latch; after the patience time the strip is deferred, marked *blocked*, and retried once after the other passes. A person stepping inside the protective zone (0.25 m look-ahead plus margin) latches a protective stop instead.
- A red banner marks synthetic calibration/profile data on the page and on every exported map and summary.

## 6. Review flagged areas

- **What enters the queue is a site-profile setting, `review_queue_policy` (owner decision 2026-11-27; contract `survey_methods.review_queue_policy`).** The queue header states the policy in force.
  - `ALARM_ONLY` (**default**, also when the profile does not carry the field): only cells whose statistic exceeds the decision threshold at the profile's scan-stage false-alarm rate (`alpha_scan` = the profile's `alpha_per_decision`, MODEL.md §3) are queued — investigation-level, unresolved and below-level alarms alike. In *search then count* only an alarm leads to a scaler count (the moving ratemeter alarm, evaluated at `mission.ratemeter_alpha`, which defaults to `alpha_scan`; CR-04). Cells that do not alarm but whose detection limit D# is above the detection goal are **not** queued: they are drawn with the existing *insufficient sensitivity* pattern, counted in the insufficient-sensitivity / residual area of the report and exported with their D#. The mission-level false-investigation allowance is controlled by the recount stage (`alpha_recount`).
  - `ALL_UNRESOLVED` (the behaviour before 2026-11-27): every cell that cannot be cleared at the investigation level is queued; below-level scan detections are reported but not queued.
  - The policy and the alpha used are stored with every cell (`cells.csv`: `review_queue_policy`, `alpha_decision`), in `survey_manifest.json` (`review_queue`, `decision_parameters`) and in `summary.txt`.
- **Next** drives one item: the lane that produced the flag is parked over the saved footprint in the original heading (or the opposite one if the first is unreachable) and arrival is verified against 10 mm with the localisation uncertainty shown. If the head has been changed since the scan, Next is refused.
- **Expose spot** reverses 0.35 m and states where the point is relative to the head's front edge and the centreline. It is refused if there is no room, and held by the chassis rear field if someone is behind (the LiDAR cannot see to the rear).
- **Repeat** takes a stationary count linked to the flag; **Skip** needs a reason; **Park** returns to the start mark and leaves unvisited items open.
- A route hold, blocked path, poor localisation or loss of the controlling session leaves the item open.

## 7. Charge/Service

With the charger connected the page shows CHARGE/SERVICE, all mission and review buttons are
disabled **and** the server and the chassis both refuse every traction command. Head power is
forced off, so the head attachment is closed. Export, the audit log and RP profile edits remain
available. Unplugging leaves the robot inactive until the start sequence is repeated.

## 8. Profiles and units

Activity limits are stored in Bq/cm². An edit needs the RP role, an explicit unit (Bq/cm² or
Bq/m²; 4 Bq/m² is stored as 0.0004 Bq/cm²) and creates a new revision; a running mission keeps
the snapshot it started with; a unit cannot be changed without re-entering the value. The
yellowcake profile cannot be selected until RP has filled it in.

## 9. Not yet done (carried open from 0.3)

TLS and site identity; phone/tablet layout trials with gloves; local indicator patterns (owned by
the chassis firmware); notification route for unattended runs; browser-level tests.
