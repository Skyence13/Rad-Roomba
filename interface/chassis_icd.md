# Chassis link interface control document — RR-CHS 1.0

**Status: draft for design 0.4 (written against contract 0.4.0-draft4). Owner: chassis firmware lead.** Expands `interface/system/contract.yaml › chassis_link`. Where this document and the contract disagree, the contract wins and the disagreement is a defect to report. Machine-readable companion: [`chassis_link.schema.json`](chassis_link.schema.json). Reference implementation: `firmware/chassis/core/` (the same code runs in the emulator `rr_chassis_sim` and on the STM32G474).

Evidence classes: every behaviour described here is implemented in the firmware core and exercised against the emulator (`simulated`, see `firmware/chassis/tests/`). **Nothing has run on hardware.** All distances, times and thresholds are design values pending the physical braking and protection trials (VT-003/004/005/035).

**The motion MCU is not a certified safety controller.** The hardwired traction chain (latch relay, brake relays, external window watchdog) removes traction energy without firmware. The firmware never opposes the chain, supervises it, reports it, and adds a software protective-stop layer.

Fields marked **(+)** are additive to the contract op table (present in 1.0, safe to ignore). No contract field has been renamed or removed.

---

## 1. Transport and framing

| Item | Value |
|---|---|
| Physical | USB 2.0 full-speed CDC-ACM device on the motion MCU; host is the CM5. Baud rate and control-line settings are ignored. |
| Emulator | The same byte stream on TCP `127.0.0.1:5550` (one client) or a PTY. |
| Record | One UTF-8 JSON object (no literal TAB/CR/LF inside), one TAB (0x09), 8 uppercase hex digits = CRC-32 (zlib/IEEE, as Python `zlib.crc32`) of exactly the JSON bytes, one LF (0x0A). Identical to head ICD §4. CRC-32 of ASCII `123456789` is `CBF43926`. |
| Maximum record | 2048 bytes including TAB, CRC and LF, both directions. |
| Discard rules | Malformed JSON, duplicate keys, bad CRC, wrong trailer, oversize: the record is discarded **without a reply**. An oversized/unfinished record is discarded through the next LF. |
| Dialogue | The host polls. One transaction outstanding. The chassis never transmits unsolicited records. |
| Reply time | Design target ≤ 5 ms from the LF of the request to the first byte of the reply for every op except `BRAKE_TEST` (≤ 3 s) and `CONFIG_SET` (≤ 100 ms, flash write); not yet measured on hardware. Host timeout recommendation: 50 ms (cyclic ops), then retry with the same `id`. |

### 1.1 Envelope

```
request   {"type":"REQ","v":"1.0","id":<u32>,"op":<string>,"args":{...}}
response  {"type":"RSP","v":"1.0","id":<u32>,"status":<string>,"body":{...}}
```

`id` is a 32-bit non-negative integer chosen by the host. `args` must be an object (may be empty). Unknown members of `args` are ignored. A request with a `v` whose major part is not `1` is answered `UNSUPPORTED`.

| `status` | Meaning | `body` |
|---|---|---|
| `OK` | The op was executed. **For `DRIVE` this does not mean the command was accepted** — see `accepted`. | op specific |
| `BAD_ARG` | Missing/ill-typed/out-of-range argument. Nothing was changed. | `{"reason": <text>}` |
| `UNSUPPORTED` | Unknown op or protocol version. | `{"reason": ...}` |
| `REJECTED` | Well-formed but not permitted in the present state. Nothing was changed, nothing is queued. | `{"reason": <code>, "mode": <chassis_mode>, ...}` |
| `BUSY` | A long op (`BRAKE_TEST`) is in progress. Retry later; retrying the long op's own `id` returns its result once finished. | `{"reason":"BRAKE_TEST","state":"RUNNING"}` |
| `FAULT` | The op could not be executed because of an internal fault (e.g. flash write failed). | `{"reason": <code>}` |

### 1.2 Retries and the reply cache

The chassis caches the last completed transaction. A request whose `id` and whose JSON bytes are identical to the cached request (same length and CRC) is not executed again; the cached reply bytes are re-sent. A different request that reuses an `id` is executed normally. `BUSY` replies are never cached. Consequences the host must respect:

- Every new command, including every cyclic `DRIVE`, uses a fresh `id`. Re-sending a `DRIVE` with the same `id` does **not** refresh the command time-to-live.
- A fresh `HELLO` (new `id`) discards the cache.
- An MCU reset discards the cache; the next `HELLO` shows a new `boot_id`.

### 1.3 Link session

`HELLO` opens a **link session** (counter `session`, starts at 1 after boot). Ops that can enable or change something (`DRIVE`, `REARM_SW`, `SET_OP_MODE`, `HEAD_POWER`, `HEATER`, `PANEL`, `CONFIG_SET`, `BRAKE_TEST`) are answered `REJECTED / NO_SESSION` (for `DRIVE`: `accepted:false, reject_reason:"NO_SESSION"`) until a `HELLO` has been answered in this boot. `HELLO`, `TIME`, `STATE`, `DIAG`, `EVENTS`, `CONFIG_GET` and `STOP` always work. A `HELLO` received while the robot is `MOVING` is treated as a change of controlling session: the motion is stopped and `HOST_LINK_LOST` is latched (§5.3).

---

## 2. Clocks and time synchronisation

- **Chassis clock**: unsigned 64-bit microseconds, monotonic since MCU boot, from the HSE crystal (hardware timer, 1 µs resolution). All `t_us`, `rx_us`, `tx_us` values are on this clock. It restarts at 0 on every MCU reset; a new `boot_id` tells the host to discard its fit.
- **`TIME` exchange** (same four-timestamp method as the head): the host records `t1` (host clock, just before writing the request) and `t4` (host clock, when the reply LF is read). The chassis returns `rx_us` = chassis time at which the LF of the request was taken from the USB endpoint and `tx_us` = chassis time at which the reply was handed to the USB endpoint. Offset sample = ((t1 + t4) − (rx_us + tx_us)) / 2, bound = ((t4 − t1) − (tx_us − rx_us)) / 2 + asymmetry allowance + drift × age, exactly as `contract.yaml › timing.sync_method`.
- Refresh every `sync_refresh_period_s` (2 s); a fit older than `sync_expiry_s` (10 s) is invalid. `TIME` may be interleaved with the 50 Hz `DRIVE` cycle.
- Odometry and IMU samples are stamped at the sampling instant in the 1 kHz control interrupt, never at USB transmission.

---

## 3. Operations

Units are SI unless the member name carries a suffix (`_ms`, `_us`, `_mm`, `_c`, `_pct`, `_v`, `_a`). Numbers are JSON numbers; booleans are `true`/`false`. Enumerations are those of `contract.yaml › enums`, spelled exactly.

### 3.1 HELLO

Args: `{}`.

| Body member | Type | Meaning |
|---|---|---|
| `fw` | string | Firmware version, e.g. `"rr-chassis 0.4.0+sim"` |
| `hw_rev` | string | Board revision (config `id.hw_rev`), `"A"`… |
| `serial` | string | `"RRC-"` + 6 digits (config `id.serial_no`) |
| `boot_id` | string | UUID (version 4), fresh at every MCU boot |
| `proto` | string | `"RR-CHS 1.0"` |
| `caps` | object | `encoder_cpr` (9600), `wheel_radius_nom_m` (0.052) and `track_nom_m` (0.270, Rev E body) — the nominal values, i.e. the defaults of `cal.wheel_radius_*_m` / `cal.track_m`; the calibrated values are read with `CONFIG_GET` — `max_v_mps` (0.20), `max_w_radps` (0.30); **(+)** `max_rev_mps` (0.05), `max_accel_mps2` (0.30), `ttl_ms_max` (250), `drive_hz` (50), `odom_hz` (100), `record_max` (2048), `events_retained` (128), `tof_count` (11) |
| `session` **(+)** | u32 | Link-session counter |
| `uptime_us` **(+)** | u64 | Chassis clock now |
| `reset` **(+)** | object | `cause` (`POWER_ON`, `BROWNOUT`, `PIN`, `WATCHDOG`, `SOFTWARE`, `UNKNOWN`), `boot_count` (persistent) |
| `config` **(+)** | object | `gen` (generation counter), `crc` (8 hex digits), `source` (`FLASH` or `DEFAULTS`) |

```json
{"type":"REQ","v":"1.0","id":1,"op":"HELLO","args":{}}
{"type":"RSP","v":"1.0","id":1,"status":"OK","body":{"fw":"rr-chassis 0.4.0+sim","hw_rev":"A","serial":"RRC-000001","boot_id":"6f1c2a7e-5d0b-4c3e-9a41-0d2f3b8c7e10","proto":"RR-CHS 1.0","caps":{"encoder_cpr":9600,"wheel_radius_nom_m":0.052,"track_nom_m":0.27,"max_v_mps":0.2,"max_w_radps":0.3,"max_rev_mps":0.05,"max_accel_mps2":0.3,"ttl_ms_max":250,"drive_hz":50,"odom_hz":100,"record_max":2048,"events_retained":128,"tof_count":11},"session":1,"uptime_us":1234567,"reset":{"cause":"POWER_ON","boot_count":7},"config":{"gen":3,"crc":"5A0F3C21","source":"FLASH"}}}
```

### 3.2 TIME

Args: `{}`. Body: `rx_us` (u64), `tx_us` (u64). See §2.

```json
{"type":"REQ","v":"1.0","id":2,"op":"TIME","args":{}}
{"type":"RSP","v":"1.0","id":2,"status":"OK","body":{"rx_us":2000431,"tx_us":2000612}}
```

### 3.3 DRIVE

The cyclic exchange, nominally 50 Hz. It carries one bounded velocity command and returns odometry, IMU and stop state in the same transaction. The telemetry part of the body is returned **whether or not the command is accepted**, so the host keeps its feedback while the robot is inhibited.

| Arg | Type | Range | Meaning |
|---|---|---|---|
| `seq` | u32 | strictly increasing within a link session | Command sequence number. A `seq` ≤ the last accepted one is rejected (`SEQ`). |
| `v_mps` | number | −0.5 … 0.5 (else `BAD_ARG`) | Body-frame forward velocity at `base_link`. Positive = toward the head. |
| `w_radps` | number | −1.0 … 1.0 (else `BAD_ARG`) | Yaw rate about +z (counter-clockwise positive). |
| `ttl_ms` | integer | 1 … 250 (else `BAD_ARG`) | Time-to-live of this command. |
| `op_mode` | enum `op_mode` | must equal the selected op_mode | Guards against a host that believes it is in another profile. |
| `issued_us` **(+)** | u64, optional | — | Chassis-clock time at which the host issued the command (from its clock fit). If present, the TTL is counted from `issued_us`; if absent, from reception. A command already older than its TTL is rejected (`TTL`). `issued_us` more than 20 ms in the future is `BAD_ARG`. |

Acceptance rules, in this order. The first failing rule gives `accepted:false` and `reject_reason`; **a rejected command is discarded, never queued, and does not extend the life of the previous command**:

| `reject_reason` | Condition |
|---|---|
| `NO_SESSION` | No `HELLO` in this boot. |
| `SEQ` | `seq` not greater than the last accepted `seq` of this session. |
| `TTL` | Command older than `ttl_ms` when processed. |
| `BOOT`, `FAULT`, `SERVICE_CHARGE`, `LAB`, `STANDBY`, `HW_INHIBIT`, `PROTECTIVE_STOP`, `HOLD` | The chassis is in that mode (also for `v = w = 0`). |
| `OP_MODE` | `op_mode` differs from the selected op_mode. |
| `LIMIT` | \|v\| or \|w\| exceeds the cap of the selected op_mode (§6.1). The command is not clamped. |
| `BRAKE_TEST_REQUIRED` | Non-zero command, `safety.require_brake_test` = 1 and no passed brake test since boot. |
| `DIR_INHIBITED` | Non-zero command into a direction that a protective field currently inhibits (§6.3). `allow` shows which. |

An accepted command replaces the previous one and is valid until its TTL ends. `v = w = 0` is a valid keep-alive. If the TTL of a **non-zero** command ends without a newer accepted command, the chassis ramps to rest and latches `PROTECTIVE_STOP / CMD_TIMEOUT`. The ramp starts no later than `ttl_ms` + 1 ms after the command was issued/received.

Starting from rest (§6.11): the pre-motion alert (buzzer and MOVING indicator for `alert.premotion_ms`, default 1500 ms) precedes the first motion after arming, after any stop/hold/inhibit, and after the chassis has been idle at rest longer than `alert.rest_ms` (default 5 s). The wheels stay held until it ends; the host keeps sending `DRIVE`; `motion` reports `ALERT`. A start from rest inside the idle time (step-and-count hops) is not delayed and is announced by one short chirp. Commands are executed with the acceleration limits of §6.1.

| Body member | Type | Meaning |
|---|---|---|
| `accepted` | bool | Command taken as the active command |
| `reject_reason` | string or null | See table |
| `mode` | enum `chassis_mode` | Mode after processing this command |
| `odom` | object | `t_us`: chassis time of the encoder sample. `left_ticks`, `right_ticks`: signed 64-bit cumulative quadrature counts since boot, positive = wheel rolling the robot forward. `left_tps`, `right_tps`: tick rate (ticks/s) low-pass filtered (τ = 20 ms) at the same instant. **(+)** `seq`: odometry sample counter (100 Hz). |
| `imu` | object | `t_us`: centre time of the 10 ms averaging window. `gyro_rps[3]`, `accel_mps2[3]`: mean over that window, body axes x forward, y left, z up (accel reads +9.81 on z at rest). **(+)** `ok`: bool. |
| `stops` | object | `hw`: latched `hw_inhibit_reason`s. `sw`: latched `protective_stop_reason`s. Both arrays empty when nothing is latched. |
| `event_seq` | u32 | Newest event number (§7) |
| `stationary` **(+)** | object | `is_stationary` (bool), `since_us` (u64 or null): stationarity evidence for scaler counts, §6.10 |
| `applied` **(+)** | object | `v_mps`, `w_radps`: the set-point the wheel loops are following now (after caps and ramps) |
| `motion` **(+)** | string | `REST`, `ALERT`, `RUN`, `DECEL` |
| `allow` **(+)** | object | `fwd`, `rev`, `pivot`: bool — directions not inhibited by protective fields at this instant |
| `v_cap_mps` **(+)** | number | Current forward-speed cap from the look-ahead field (equals the op_mode cap when unrestricted) |
| `hold` **(+)** | array | Latched hold reasons: `LOCAL_PAUSE`, `HOST_STOP` |
| `rearm_nonce` **(+)** | u32 | Value to present in `REARM_SW` (§3.6) |

```json
{"type":"REQ","v":"1.0","id":120,"op":"DRIVE","args":{"seq":57,"v_mps":0.1,"w_radps":0.0,"ttl_ms":200,"op_mode":"SURVEY_SHARED"}}
{"type":"RSP","v":"1.0","id":120,"status":"OK","body":{"accepted":true,"reject_reason":null,"mode":"MOVING","odom":{"t_us":5230000,"left_ticks":18432,"right_ticks":18427,"left_tps":2937.5,"right_tps":2939.1,"seq":523},"imu":{"t_us":5225000,"gyro_rps":[0.0,0.0,0.001],"accel_mps2":[0.02,-0.01,9.81],"ok":true},"stops":{"hw":[],"sw":[]},"event_seq":14,"stationary":{"is_stationary":false,"since_us":null},"applied":{"v_mps":0.1,"w_radps":0.0},"motion":"RUN","allow":{"fwd":true,"rev":true,"pivot":true},"v_cap_mps":0.1,"hold":[],"rearm_nonce":0}}
```

Rejected while the e-stop is pressed (telemetry still present):

```json
{"type":"RSP","v":"1.0","id":121,"status":"OK","body":{"accepted":false,"reject_reason":"HW_INHIBIT","mode":"HW_INHIBIT","odom":{"t_us":5250000,"left_ticks":18490,"right_ticks":18485,"left_tps":0.0,"right_tps":0.0,"seq":525},"imu":{"t_us":5245000,"gyro_rps":[0.0,0.0,0.0],"accel_mps2":[0.0,0.0,9.81],"ok":true},"stops":{"hw":["ESTOP"],"sw":[]},"event_seq":17,"stationary":{"is_stationary":true,"since_us":5246003},"applied":{"v_mps":0.0,"w_radps":0.0},"motion":"REST","allow":{"fwd":true,"rev":true,"pivot":true},"v_cap_mps":0.1,"hold":[],"rearm_nonce":0}}
```

### 3.4 STATE

Args: `{}`. Snapshot for the UI and diagnostics; poll at ≤ 5 Hz.

**Size.** The contract content of `STATE` is about 1.8 kB in a normal state, so the 2048-byte record limit leaves room for roughly a dozen reason/flag names. When the record would exceed the limit the chassis compacts it and adds `"truncated":true`: first `faults` is sent empty; if that is not enough, `panel` is sent as `{}`, `heater` keeps only `chassis_duty_pct`, `protective_stop_reasons` is cut to its first 12 names and `rearm_ready`, `hold`, `event_seq`, `uptime_us` are omitted. `hw_inhibit_reasons`, `chain`, `tof`, `rails`, `stationary` and `rearm_nonce` are never cut. `DIAG` (§3.14), `DRIVE.stops` and the event log always carry the complete lists. A unit test forces every reason and flag at once and checks the record (1897 bytes).

| Body member | Type | Meaning |
|---|---|---|
| `mode` | enum `chassis_mode` | |
| `op_mode` | enum `op_mode` | Selected profile (boot default `SERVICE`) |
| `hw_latch` | bool | Hardware latch readback (true = traction energy available) |
| `chain` | object | One bool per `safety_chain` id — `MODE_RUN`, `ESTOP`, `HANDS_ON`, `CHG_COVER`, `HEAD_DOCK`, `HEAD_LOOP`, `LAB_KEY_N`, `BODY_BUMPER`, `WDG_OK`, `ARM_PERMIT` — **live** readback, true = closed/healthy. `ESTOP` is true only if both poles are closed; `CHG_COVER` only if the cover is shut and the plug link absent. |
| `hw_inhibit_reasons` | array of enum | **Latched** reasons (§5.2) |
| `protective_stop_reasons` | array of enum | **Latched** reasons (§5.3) |
| `head_presence` | enum `head_presence` | J1 pin-7 decode (§4.2) |
| `j2_present` | bool | J2 pin-7 link |
| `rails` | object | `vbat_v`, `vmot_v`, `ibat_a` (positive = discharge), `i_drive_a[2]` (left, right, magnitude), `i_head_a`, `i_head_htr_a`, `i_chs_htr_a`, `v5_v`. A value that could not be measured is `null`. |
| `battery` | object | `soc_pct` (0–100 or null), `temp_c[2]` (charger thermistor, pack NTC; null if faulty), `charge_state` (`NONE`, `PRECHARGE`, `CC`, `CV`, `DONE`, `TEMP_INHIBIT`, `FAULT`, `UNKNOWN`) |
| `temps` | object | `board_c`, `bay_c` |
| `tof` | array[11] | `{id, range_mm, status, age_ms}`; `id` ∈ `CLIFF_FL, CLIFF_FR, CLIFF_RL, CLIFF_RR, LOOK_LO, LOOK_LI, LOOK_RI, LOOK_RO, REAR_L, REAR_C, REAR_R`; `status` ∈ `OK, NO_TARGET, INVALID, STALE, OFFLINE`; `range_mm` null unless `OK`; `age_ms` saturates at 9999 |
| `bumpers` | object | `body_l`, `body_r`: bool, true = pressed/open. `head_loop`: `OK`, `OPEN`, `SHORT`. `head_loop_ohm`: analog estimate (null above 100 kΩ) |
| `panel` | object | `buttons`: `{rearm, pause}` bool pressed. `leds`: `{ready, moving, hold, fault, charge}` each `OFF`, `ON`, `BLINK_SLOW`, `BLINK_FAST`, `BLINK_2`. **(+)** `buzzer`: bool, `pattern`: requested host pattern |
| `heater` | object | `chassis_duty_pct` (0–100); **(+)** `chassis_setpoint_c` (number or null = off), `sensor_ok` |
| `faults` | array of string | Active internal fault and warning flags (§5.5) |
| `stationary` **(+)** | object | As in `DRIVE`, §6.10 |
| `rearm_nonce` **(+)** | u32 | §3.6 |
| `rearm_ready` **(+)** | bool | A press of the local REARM button would set the hardware latch now |
| `hold` **(+)** | array | Latched hold reasons |
| `event_seq` **(+)** | u32 | Newest event number |
| `uptime_us` **(+)** | u64 | |
| `truncated` **(+)** | bool | Present (true) only when the record was compacted, see above |

```json
{"type":"REQ","v":"1.0","id":7,"op":"STATE","args":{}}
{"type":"RSP","v":"1.0","id":7,"status":"OK","body":{"mode":"ARMED_IDLE","op_mode":"SURVEY_SHARED","hw_latch":true,"chain":{"MODE_RUN":true,"ESTOP":true,"HANDS_ON":true,"CHG_COVER":true,"HEAD_DOCK":true,"HEAD_LOOP":true,"LAB_KEY_N":true,"BODY_BUMPER":true,"WDG_OK":true,"ARM_PERMIT":true},"hw_inhibit_reasons":[],"protective_stop_reasons":[],"head_presence":"HEAD_DIRECT","j2_present":true,"rails":{"vbat_v":13.1,"vmot_v":13.0,"ibat_a":1.42,"i_drive_a":[0.0,0.0],"i_head_a":0.38,"i_head_htr_a":0.0,"i_chs_htr_a":0.0,"v5_v":5.09},"battery":{"soc_pct":82,"temp_c":[18.5,18.9],"charge_state":"NONE"},"temps":{"board_c":24.0,"bay_c":19.2},"tof":[{"id":"CLIFF_FL","range_mm":31,"status":"OK","age_ms":12},{"id":"CLIFF_FR","range_mm":30,"status":"OK","age_ms":4}],"bumpers":{"body_l":false,"body_r":false,"head_loop":"OK","head_loop_ohm":1003},"panel":{"buttons":{"rearm":false,"pause":false},"leds":{"ready":"ON","moving":"OFF","hold":"OFF","fault":"OFF","charge":"OFF"},"buzzer":false,"pattern":"AUTO"},"heater":{"chassis_duty_pct":0,"chassis_setpoint_c":null,"sensor_ok":true},"faults":[],"stationary":{"is_stationary":true,"since_us":90411003},"rearm_nonce":0,"rearm_ready":false,"hold":[],"event_seq":21,"uptime_us":96000123}}
```

(The example `tof` array is shortened to two of the eleven entries.)

### 3.5 EVENTS

Args: `after_seq` (u32). Returns the retained events with `seq` > `after_seq`, oldest first, at most as many as fit in one record (`more` tells the host to ask again). `after_seq = 0` returns from the oldest retained event.

| Body member | Type | Meaning |
|---|---|---|
| `events` | array | `{seq, t_us, kind, detail}`; `detail` is a small object, see §7 |
| `newest_seq` | u32 | Newest event number in the log (0 if none) |
| `oldest_seq` | u32 | Oldest retained event number |
| `more` | bool | More events after the last one returned |
| `gap` | bool | `after_seq + 1 < oldest_seq`: events were overwritten before the host read them (the log keeps the newest 128). The host must record the loss. |

```json
{"type":"REQ","v":"1.0","id":40,"op":"EVENTS","args":{"after_seq":14}}
{"type":"RSP","v":"1.0","id":40,"status":"OK","body":{"events":[{"seq":15,"t_us":5241003,"kind":"CHAIN","detail":{"el":"ESTOP_A","closed":false}},{"seq":16,"t_us":5241003,"kind":"CHAIN","detail":{"el":"ESTOP_B","closed":false}},{"seq":17,"t_us":5246003,"kind":"HW_LATCH","detail":{"set":false,"reasons":["ESTOP"]}},{"seq":18,"t_us":5246003,"kind":"MODE","detail":{"from":"MOVING","to":"HW_INHIBIT"}}],"newest_seq":18,"oldest_seq":1,"more":false,"gap":false}}
```

### 3.6 REARM_SW

Args: `nonce` (u32), `operator` (string, 1–32 printable ASCII characters; the first 15 are recorded in the event log).

`nonce` must equal the `rearm_nonce` currently reported by `STATE`/`DRIVE`. The chassis draws a new random non-zero nonce every time a software stop or hold is latched and every time a `REARM_SW` clears something or is rejected for a present cause, so a re-arm request that was composed before the latest stop (cached page, queued request, replay) cannot clear it.

Effect when accepted: clears the software `PROTECTIVE_STOP` latch **and** the hold latch. It never changes the hardware latch (`hw_latch` in the reply shows its state; only the local REARM button can set it). It does not start motion: the next motion needs a new accepted `DRIVE`, and the pre-motion alert runs.

| Outcome | Reply |
|---|---|
| Latch(es) cleared, or nothing was latched | `OK` `{cleared:[reasons], hold_cleared:[...], mode, hw_latch, rearm_nonce}` (`cleared` empty if nothing was latched) |
| A cause is still present | `REJECTED` `{reason:"CAUSE_ACTIVE", active:[reasons], mode}` — nothing is cleared |
| Wrong nonce | `REJECTED` `{reason:"NONCE", mode, rearm_nonce}` |
| No session / in `BOOT` or `FAULT` | `REJECTED` `{reason:"NO_SESSION" \| "BOOT" \| "FAULT"}` |

The local REARM button has the same software effect (operator recorded as `LOCAL`), with no nonce.

```json
{"type":"REQ","v":"1.0","id":60,"op":"REARM_SW","args":{"nonce":2917334021,"operator":"a.tech"}}
{"type":"RSP","v":"1.0","id":60,"status":"OK","body":{"cleared":["CMD_TIMEOUT"],"hold_cleared":[],"mode":"ARMED_IDLE","hw_latch":true,"rearm_nonce":771204518}}
```

### 3.7 STOP

Args: `kind` = `CONTROLLED` or `PROTECTIVE`; **(+)** `reason` (optional, `PROTECTIVE` only): one of `HOST_REQUEST` (default), `FIELD_FRONT`, `FIELD_LEFT`, `FIELD_RIGHT`, `FIELD_REAR`, `HEAD_LINK`, `LOCALIZATION` — lets the host label a stop that originates from its own protective functions (route hold, head link supervision, localisation loss).

`STOP` is accepted in every mode and needs no session.

- `CONTROLLED`: ramp to rest with `drive.decel_mps2` (0.40 m/s²), then latch **HOLD** (`HOST_STOP`). `DRIVE` is rejected with `HOLD` until `REARM_SW` or the local REARM button.
- `PROTECTIVE`: ramp to rest with `drive.pstop_decel_mps2`, latch **PROTECTIVE_STOP** with the given reason.

Body: `{mode, stops:{hw,sw}, hold, rearm_nonce}`.

```json
{"type":"REQ","v":"1.0","id":70,"op":"STOP","args":{"kind":"PROTECTIVE","reason":"FIELD_FRONT"}}
{"type":"RSP","v":"1.0","id":70,"status":"OK","body":{"mode":"PROTECTIVE_STOP","stops":{"hw":[],"sw":["FIELD_FRONT"]},"hold":[],"rearm_nonce":1193046}}
```

### 3.8 SET_OP_MODE

Args: `op_mode` (enum). Selects the speed/field profile enforced locally (§6.1). `REJECTED / NOT_STATIONARY` unless the wheels are at rest and no non-zero command is active. Body: `{op_mode, caps:{v_fwd_mps, v_rev_mps, w_radps}}`. The boot default is `SERVICE` (all caps zero), so the host must select a profile deliberately. The change is logged as an event.

```json
{"type":"REQ","v":"1.0","id":80,"op":"SET_OP_MODE","args":{"op_mode":"SURVEY_SHARED"}}
{"type":"RSP","v":"1.0","id":80,"status":"OK","body":{"op_mode":"SURVEY_SHARED","caps":{"v_fwd_mps":0.1,"v_rev_mps":0.05,"w_radps":0.3}}}
```

### 3.9 HEAD_POWER

Args: `electronics` (bool), `heater_enable` (bool). Switches the J1 branches (pins 1/2 and 3/4). Body: `{electronics, heater_enable, head_presence}` — the actual switch state after the request.

Rules (first match):

| Condition | Result |
|---|---|
| Mode `SERVICE_CHARGE`, `BOOT` or `FAULT` | Both branches are forced off. A request to switch anything on is `REJECTED` with that mode as `reason`. |
| `head_presence` is `ABSENT`, `LAB_EXTENSION_ONLY` or `FAULT` | On-request `REJECTED / HEAD_ABSENT` (or `PRES_FAULT`). |
| `heater_enable` true with `electronics` false | `BAD_ARG` |
| Branch eFuse reports a fault | Branch is switched off, fault flag `EFUSE_HEAD_PWR` / `EFUSE_HEAD_HTR`, event. A new request retries. |
| otherwise (including `LAB`, where traction is hard-inhibited but head power is permitted) | `OK` |

Both branches are switched off automatically, and stay off until a new request, when J1 presence leaves `HEAD_DIRECT`/`HEAD_VIA_LAB_EXTENSION`, on entering `SERVICE_CHARGE`, and at every MCU boot.

```json
{"type":"REQ","v":"1.0","id":90,"op":"HEAD_POWER","args":{"electronics":true,"heater_enable":true}}
{"type":"RSP","v":"1.0","id":90,"status":"OK","body":{"electronics":true,"heater_enable":true,"head_presence":"HEAD_DIRECT"}}
```

### 3.10 HEATER

Args: `chassis_setpoint_c`: number 0 … 30, or `null` = heater off. Default after every boot: off. Body: `{chassis_setpoint_c, duty_pct, bay_c, sensor_ok}`.

Regulation (§6.6) runs locally. The heater is forced off, whatever the set-point, on a temperature-sensor fault, above `heater.max_c`, on an eFuse fault, in `BOOT`/`FAULT`, and when the battery is below `batt.warn_v` without a charger. It is permitted in `SERVICE_CHARGE` (warming a cold pack before charging).

```json
{"type":"REQ","v":"1.0","id":91,"op":"HEATER","args":{"chassis_setpoint_c":10.0}}
{"type":"RSP","v":"1.0","id":91,"status":"OK","body":{"chassis_setpoint_c":10.0,"duty_pct":100,"bay_c":-4.5,"sensor_ok":true}}
```

### 3.11 PANEL

Args: `pattern`: `AUTO` (default), `ARRIVED` (READY double-blink + one chirp), `ATTENTION` (two beeps every 5 s), `LOCATE` (all five LEDs chase + chirp), `QUIET` (suppress host-requested and informational beeps only). Body: `{pattern, leds:{...}, buzzer}`.

The MCU owns the indicators for safety states: the pre-motion alert, `MOVING`, `HOLD`, `PROTECTIVE_STOP`, `HW_INHIBIT`, `FAULT` and charge indications of §6.7 cannot be suppressed or altered by the host. A host pattern is shown only in `STANDBY`/`ARMED_IDLE`/`HOLD` and reverts to `AUTO` on any mode change.

```json
{"type":"REQ","v":"1.0","id":92,"op":"PANEL","args":{"pattern":"ARRIVED"}}
{"type":"RSP","v":"1.0","id":92,"status":"OK","body":{"pattern":"ARRIVED","leds":{"ready":"BLINK_2","moving":"OFF","hold":"OFF","fault":"OFF","charge":"OFF"},"buzzer":false}}
```

### 3.12 CONFIG_GET / CONFIG_SET

`CONFIG_GET` args: `key` (string). Body: `{key, value, default, min, max, unit, rw}`. **(+)** The pseudo-key `"_keys"` with optional `offset` (default 0) enumerates: body `{keys:[...up to 24 names...], total, offset}`.

`CONFIG_SET` args: `key`, `value` (number; booleans are 0/1). Range-checked (`BAD_ARG`), read-only keys `REJECTED / READ_ONLY`, and `REJECTED / NOT_STATIONARY` while `MOVING`. On success the complete configuration is written to flash (two alternating copies, each with layout version, generation counter and CRC-32) before the reply. Body: `{key, value, old, gen, crc}`. Every change is logged as a `CONFIG` event. A flash write failure answers `FAULT / NV_WRITE` and the old value stays in force.

Keys are listed in §8.

```json
{"type":"REQ","v":"1.0","id":95,"op":"CONFIG_SET","args":{"key":"cal.track_m","value":0.2713}}
{"type":"RSP","v":"1.0","id":95,"status":"OK","body":{"key":"cal.track_m","value":0.2713,"old":0.27,"gen":4,"crc":"9C01D2AB"}}
{"type":"REQ","v":"1.0","id":96,"op":"CONFIG_GET","args":{"key":"cal.track_m"}}
{"type":"RSP","v":"1.0","id":96,"status":"OK","body":{"key":"cal.track_m","value":0.2713,"default":0.27,"min":0.2,"max":0.34,"unit":"m","rw":true}}
```

### 3.13 BRAKE_TEST

Args: `{}`. Runs the stationary brake-relay and VMOT-drop self-test (§6.8) and replies when it has finished (typically 0.8 s, at most 3 s). While it runs, any other request is answered `BUSY`; a retry of the `BRAKE_TEST` request itself with the same `id` returns the result when available.

Precondition: mode `ARMED_IDLE` (hardware latch set, at rest), or `PROTECTIVE_STOP` whose only latched reason is `BRAKE_TEST_FAIL` with the hardware latch set. Otherwise `REJECTED / NOT_ARMED_IDLE`.

**The test drops the hardware latch on purpose.** Afterwards the chassis is in `STANDBY` and the operator must press the local REARM button. A passed test satisfies `safety.require_brake_test` until the next MCU boot.

| Body member | Meaning |
|---|---|
| `passed` | bool |
| `fail` | array of codes: `PRECOND_VMOT`, `PRECOND_RELAY`, `LATCH_NOT_DROPPED`, `RELAY_L`, `RELAY_R`, `VMOT_NOT_REMOVED`, `BRIDGE_CURRENT_L`, `BRIDGE_CURRENT_R`, `WHEEL_MOVED` |
| `latch_drop_ms` | Time from ARM_PERMIT low to latch readback low (limit `brake.latch_drop_max_ms`) |
| `relay_ms` | Time until both brake relays read "braked" |
| `vmot_decay_ms`, `vmot_end_v` | Time until VMOT < `brake.vmot_off_v`, and the final value |
| `probe_i_a[2]` | Motor current while a probe duty is applied with the latch dropped (must be ≈ 0) |
| `moved_ticks[2]` | Encoder movement during the test |
| `mode` | Mode after the test |

A failed test latches `PROTECTIVE_STOP / BRAKE_TEST_FAIL`; the cause stays active until a later test passes. If the latch does not drop with ARM_PERMIT low, the chassis additionally enters `FAULT` (`LATCH_STUCK`).

```json
{"type":"REQ","v":"1.0","id":99,"op":"BRAKE_TEST","args":{}}
{"type":"RSP","v":"1.0","id":99,"status":"OK","body":{"passed":true,"fail":[],"latch_drop_ms":6,"relay_ms":9,"vmot_decay_ms":142,"vmot_end_v":0.31,"probe_i_a":[0.0,0.0],"moved_ticks":[0,0],"mode":"STANDBY"}}
```

### 3.14 DIAG **(+)**

Args: `{}`. Additive op (a chassis without it answers `UNSUPPORTED`). Complete reason and flag lists and engineering detail that does not fit in `STATE`; never truncated. Needs no session.

| Body member | Meaning |
|---|---|
| `mode` | |
| `hw_inhibit_reasons`, `protective_stop_reasons` | Latched sets, complete |
| `hw_active` | Hardware inhibit causes present now (§4.4) |
| `sw_active` | Protective-stop causes present now, latched or not. `REARM_SW` succeeds only if no latched reason is in this list (retreat-permitted causes excepted, §5.3). |
| `faults` | Complete flag list (§5.5) |
| `estop` | `a`, `b`: E-stop pole readbacks, true = closed |
| `readbacks` | String of 22 characters `0`/`1`: debounced inputs in this order — `MODE_RUN, ESTOP_A, ESTOP_B, HANDS_ON, CHG_COVER, CHG_PLUG_LINK, HEAD_DOCK, HEAD_LOOP_OK, HEAD_LOOP_SHORT, LAB_KEY_N, BODY_BUMPER_L, BODY_BUMPER_R, WDG_OK, BRAKE_L, BRAKE_R, HW_LATCH, J2_PRES, BTN_REARM, BTN_PAUSE, DRV_FAULT_L, DRV_FAULT_R, BUS_CLAMP` (1 = closed/healthy/present/pressed; `HEAD_LOOP_SHORT`, `DRV_FAULT_x`, `BUS_CLAMP`: 1 = asserted; `CHG_PLUG_LINK`: 1 = plug link absent) |
| `pres_ohm` | J1 pin 7 resistance (saturates at 999999) |
| `head_power` | `electronics`, `heater_enable`: actual switch state |
| `brake_test` | `state` (`NONE`, `RUNNING`, `PASSED`, `FAILED`), `age_s` (null if never run), `passed_since_boot` |
| `tilt_deg` | Tilt estimate (§6.5) |
| `drive` | `duty[2]`, `v_meas_mps`, `w_meas_radps`, `v_cap_fwd_mps`, `v_cap_rev_mps`, `bridge_awake` |
| `link` | `session`, `requests`, `discarded` (records dropped for framing/JSON errors) |
| `sw_acknowledged` | Present only with retreat: causes acknowledged by a re-arm while still present |

```json
{"type":"REQ","v":"1.0","id":101,"op":"DIAG","args":{}}
{"type":"RSP","v":"1.0","id":101,"status":"OK","body":{"mode":"ARMED_IDLE","hw_inhibit_reasons":[],"hw_active":[],"protective_stop_reasons":[],"sw_active":[],"faults":["CONFIG_DEFAULTED"],"estop":{"a":true,"b":true},"readbacks":"1111111101111111100000","pres_ohm":4698,"head_power":{"electronics":false,"heater_enable":false},"brake_test":{"state":"PASSED","age_s":0,"passed_since_boot":true},"tilt_deg":0,"drive":{"duty":[0,0],"v_meas_mps":0,"w_meas_radps":0,"v_cap_fwd_mps":0.2,"v_cap_rev_mps":0.05,"bridge_awake":true},"link":{"session":1,"requests":7,"discarded":0}}}
```

---

## 4. Chain supervision

### 4.1 Sampling, debounce, event latching

All chain readbacks, the two connector-presence inputs and the buttons are sampled in the 1 kHz control interrupt (native pins and the SPI expander in the same tick). Each input has a debounced state:

- A change toward **open / unhealthy / absent / pressed** is taken on the **first** sample that shows it (≤ 1 ms after the edge; 2 consecutive samples for the analog J1 presence code) and immediately latched as an event.
- A change toward **closed / healthy / present / released** is taken only after the input has been stable for `chain.close_debounce_ms` (default 50 ms; J1 class changes: `chain.pres_settle_ms`, default 20 ms).

So an opening of any element, or an unplug of J1 or J2, lasting ≥ 2 ms always produces a pair of events (open, later closed) with chassis-clock timestamps, independent of host polling; shorter openings produce events whenever a 1 kHz sample falls inside them. Unit test: a 5 ms unplug pulse on J1 and on J2 yields the event pair.

### 4.2 Head presence (J1 pin 7 to pin 2)

| `head_presence` | Resistance window (Ω) |
|---|---|
| `ABSENT` | R > 20 000 |
| `HEAD_DIRECT` | 3 900 ≤ R ≤ 5 600 (nominal 4 700) |
| `HEAD_VIA_LAB_EXTENSION` | 950 ≤ R < 1 330 (nominal 1 137) |
| `LAB_EXTENSION_ONLY` | 1 330 ≤ R ≤ 1 800 (nominal 1 500) |
| `FAULT` | R < 950, 1 800 < R < 3 900, 5 600 < R ≤ 20 000 (includes the contract's "< 0.8 k" short band) |

Every change of the debounced class is an event `J1` with `from`, `to` and the measured `ohm`. J2 presence is the digital link on J2 pin 7; every change is an event `J2`.

### 4.3 Interlock loop (J1 pins 5/6)

The hardware window comparator (healthy 600–1600 Ω) is in the chain. The firmware reads its two outputs and, separately, an analog measurement of the loop resistance. `bumpers.head_loop` is `OK`, `OPEN` or `SHORT`. A disagreement between comparator and analog decode for more than 200 ms raises the warning flag `LOOP_DISCREPANCY`; the worse of the two is reported.

### 4.4 Live cause decode → `hw_inhibit_reason`

| Reason | Live condition |
|---|---|
| `MODE_NOT_RUN` | `MODE_RUN` readback open |
| `ESTOP` | Either E-stop pole open |
| `HANDS_ON` | HANDS-ON button engaged (contact open) |
| `CHARGER` | Charge-inlet cover open **or** charge-plug link present |
| `HEAD_UNDOCKED` | Dock switch open |
| `HEAD_LOOP_OPEN` | Loop above the window while J1 is present |
| `HEAD_LOOP_SHORT` | Loop below the window |
| `J1_ABSENT` | `head_presence` = `ABSENT` (a loop opening with J1 absent is attributed to the disconnect) |
| `LAB_KEY` | `head_presence` shows the LAB resistor, or the hardware `LAB_KEY_N` element is open |
| `BODY_BUMPER` | Either body bumper switch open |
| `WATCHDOG` | External watchdog output not OK |
| `MCU_NOT_READY` | Firmware is withholding `ARM_PERMIT` (boot, fault, charge/LAB mode, stop escalation, brake test, presence `FAULT`) |
| `VMOT_FAULT` | Latch set but VMOT below `brake.vmot_min_v` for > 100 ms; latch dropped but VMOT still present after the decay time; brake-relay readback inconsistent with the latch for > 200 ms; or the latch dropped with no readback explaining it. While the condition is present the firmware also withholds ARM_PERMIT. |

---

## 5. Mode state machine

### 5.1 Modes

| Mode | Meaning | ARM_PERMIT | Bridges | `DRIVE` |
|---|---|---|---|---|
| `BOOT` | Start-up self-checks (≤ 2 s) | low | asleep | rejected |
| `FAULT` | Internal fault that makes supervision untrustworthy (§5.5) | low | asleep | rejected |
| `SERVICE_CHARGE` | Charger cover open or plug link present. Priority over `LAB`. Head power forced off. | low | asleep | rejected |
| `LAB` | LAB extension resistor detected or `LAB_KEY_N` open. Head power allowed, traction hard-inhibited. | low | asleep | rejected |
| `HW_INHIBIT` | Hardware latch not set and at least one hardware reason latched | high unless `MCU_NOT_READY` | asleep | rejected |
| `STANDBY` | Hardware latch not set, no hardware reason latched, no software latch: waiting for the local REARM button | high | asleep | rejected |
| `PROTECTIVE_STOP` | Software latch set (hardware latch set, or not set with no hardware reason) | high | ramp to rest, then braking (both low-side on) | rejected |
| `HOLD` | Hold latch set (local PAUSE or `STOP CONTROLLED`), hardware latch set | high | ramp to rest, then braking | rejected |
| `MOVING` | A non-zero command is active or the wheels have not yet come to rest (includes the pre-motion alert and the final ramp) | high | driving | accepted |
| `ARMED_IDLE` | Hardware latch set, nothing latched, at rest | high | braking | accepted |

The mode is re-evaluated every millisecond with this priority (first match): `FAULT` → `BOOT` → `SERVICE_CHARGE` → `LAB` → (latch not set: `HW_INHIBIT` if any hardware reason is latched, else `PROTECTIVE_STOP` if the software latch is set, else `STANDBY`) → (latch set: `PROTECTIVE_STOP` → `HOLD` → `MOVING` → `ARMED_IDLE`).

### 5.2 Hardware latch and latched hardware reasons

- The hardware latch is a relay circuit. The firmware can only **open** the chain (ARM_PERMIT low, or by stopping the watchdog strobe); it has no output that can set the latch. **Only the local REARM button sets it**, and only with every element healthy and ARM_PERMIT high. No protocol op, including `REARM_SW`, can set it.
- When the latch readback goes low, the live hardware causes of §4.4 (those present in that millisecond and in the one before) are captured as the **latched hardware reasons**. While the latch stays down, further causes that appear are added. The set is cleared only when the latch readback goes high again (i.e. after a successful local REARM). Therefore a momentary cause (bumper tap, brief unplug) stays reported until an operator has re-armed at the robot.
- At boot the latch is always down (ARM_PERMIT is low through reset). If no cause is present after `BOOT`, the mode is `STANDBY`.

### 5.3 Software protective stop

A latched set of `protective_stop_reason`s. Setting any reason: the wheel set-points ramp to rest with `drive.pstop_decel_mps2` (encoder-consistency faults: immediate zero duty), the active command is discarded, `DRIVE` is rejected, a new `rearm_nonce` is drawn, an event `PSTOP` is logged, the buzzer sounds three beeps. The hardware latch is left set (so a remote re-arm is possible) unless the stop does not come to rest in time, in which case ARM_PERMIT is withdrawn (§5.4).

Cleared only by `REARM_SW` or the local REARM button, and only when no cause is still present. **Nothing clears automatically** — not link recovery, not the cause disappearing, not an MCU-visible timeout. (An MCU reset discards the software latch but always ends in `HW_INHIBIT`/`STANDBY` with the hardware latch down.)

Sensor-derived reasons are latched only while the hardware latch is set (`ARMED_IDLE`, `MOVING`, `HOLD`, `PROTECTIVE_STOP`); in other modes they are shown in `DIAG.sw_active` and will latch immediately after arming if still present. `HOST_LINK_LOST` and `CMD_TIMEOUT` are latched only in those modes too. `STOP PROTECTIVE` and `BRAKE_TEST_FAIL` latch in any mode.

| Reason | Set when | Cause considered cleared when |
|---|---|---|
| `CLIFF_FL`, `CLIFF_FR`, `CLIFF_RL`, `CLIFF_RR` | Confirmed cliff at that sensor (§6.3), or an unconfirmed drop/invalid/stale sample at that sensor while moving in a direction it guards | Sensor reports floor in range again |
| `LOOKAHEAD_L`, `LOOKAHEAD_R` | The look-ahead speed cap for that side reached zero while moving forward | Both sensors of that side report nominal floor |
| `FIELD_REAR` | Rear proximity inside the stop distance while reversing | Rear ranges outside the stop distance |
| `FIELD_FRONT`, `FIELD_LEFT`, `FIELD_RIGHT` | Host `STOP PROTECTIVE` with that reason (the MCU has no front/side ranging; head-rail contact is in the hardwired chain) | Immediately (host owns the cause) |
| `TOF_STALE` | A sensor guarding the direction of travel delivered no valid new sample for `tof.max_age_ms` while moving in that direction | All sensors fresh |
| `TOF_DISAGREE` | Both sensors of a look-ahead side read "nominal floor" yet differ by more than `look.pair_tol_mm`, or a cliff sensor reads below `cliff.floor_min_mm` (blocked window), for `tof.disagree_ms`, while moving in a guarded direction | Agreement restored |
| `CMD_TIMEOUT` | TTL of a non-zero command ended without a newer accepted command | Immediately |
| `HOST_LINK_LOST` | While armed: no valid request of any kind for `link.timeout_ms`, USB not configured/suspended, or a new `HELLO` while `MOVING`. Consequence: arming with no host connected ends in `PROTECTIVE_STOP` after `link.timeout_ms`, and the local button cannot clear it until a host is polling. | A valid request has been received within `link.timeout_ms` |
| `STALL` | Wheel at the current limit with speed below 10 % of set-point for `drive.stall_ms` | At rest |
| `ENCODER_FAULT` | Encoder/drive consistency: no counts while the motor model says the wheel turns, counts opposite to the drive direction, wheel speed above 0.33 m/s, or movement beyond `drive.uncmd_ticks` with no command (uncommanded motion). Stop is by zero duty (bridge brake) and, for uncommanded motion, ARM_PERMIT withdrawal. | At rest |
| `IMU_FAULT` | IMU samples missing > 20 ms, or acceleration norm outside 5–15 m/s² for 1 s | IMU healthy |
| `TILT` | Tilt from the gravity vector above `imu.tilt_max_deg` for `imu.tilt_ms` | Tilt below limit − 2° |
| `BATTERY_LOW` | VBAT below `batt.stop_v` for 5 s, or SoC below `batt.stop_soc_pct` | VBAT above `batt.stop_v` + 0.4 V |
| `TEMP_RANGE` | Pack, bay or board temperature outside `temp.min_c` … `temp.max_c` (or board above 85 °C) | Back in range by 2 °C |
| `HOST_REQUEST`, `HEAD_LINK`, `LOCALIZATION` | Host `STOP PROTECTIVE` | Immediately |
| `BRAKE_TEST_FAIL` | `BRAKE_TEST` failed | A later `BRAKE_TEST` passed |

**Retreat.** By default (`safety.allow_retreat` = 0) a latch whose cause is still present cannot be cleared: the robot is moved by hand (≤ 12 kg). With `safety.allow_retreat` = 1 a deliberate re-arm is accepted while direction-specific causes (`CLIFF_*`, `LOOKAHEAD_*`, `FIELD_REAR`, `TOF_STALE`, `TOF_DISAGREE`) persist; the guarded directions stay inhibited (`allow`), so only motion away from the hazard is accepted, capped at `safety.retreat_v_mps`. There is never an automatic retreat.

### 5.4 Stop escalation

If, after any stop was demanded (protective stop, hold, command timeout, hardware inhibit), a wheel is still turning faster than the standstill threshold later than the ramp time + `stop.escalate_ms` (300 ms), or if the robot moves more than `drive.uncmd_ticks` while no motion is commanded, the firmware withdraws ARM_PERMIT. The hardware latch drops, the motors are connected to the brake resistors, the hardware reason `MCU_NOT_READY` is latched and an event `PERMIT` records the cause. ARM_PERMIT returns high after the wheels have been at rest for 1 s so that a local re-arm is possible.

### 5.5 FAULT

Entered on: E-stop pole discrepancy > 200 ms (`ESTOP_DISCREPANCY`), latch readback high while ARM_PERMIT has been low > 100 ms (`LATCH_STUCK`, also the result of a brake test whose latch does not drop), expander read path dead for 5 ms (`IOX_A`), ADC not converting for 5 ms (`ADC`), supervision task not seen by the control tick for 50 ms (`TIMING`). Left only by an MCU reset (power cycle or NRST). In `FAULT` the chassis keeps answering the protocol and keeps strobing the watchdog (ARM_PERMIT low already holds the chain open), so the host can read the cause; only `TIMING` stops the strobe, and the watchdog then resets the MCU. `faults` lists the active flags.

Warnings that do **not** enter `FAULT` (also listed in `faults`): `CONFIG_DEFAULTED`, `LOOP_DISCREPANCY`, `J1_PRES_FAULT`, `CHARGER_COMM`, `PMON_COMM`, `TOF_BUS`, `HEATER_SENSOR`, `EFUSE_HEAD_PWR`, `EFUSE_HEAD_HTR`, `EFUSE_CHS_HTR`, `EFUSE_LIDAR`, `EFUSE_V5`, `BRIDGE_L`, `BRIDGE_R`, `BUS_CLAMP`, `BATTERY_WARN`.

### 5.6 Transition table

"Latch" = hardware latch readback. Every transition is logged as a `MODE` event.

| From | To | Trigger | Firmware action |
|---|---|---|---|
| (reset) | `BOOT` | MCU reset of any cause | ARM_PERMIT low, bridges asleep, head branches and heater off, new `boot_id`, `BOOT` event with reset cause |
| `BOOT` | `SERVICE_CHARGE` / `LAB` / `HW_INHIBIT` / `STANDBY` | Self-checks done, inputs valid (≥ 200 ms) | Live hardware causes captured as latched reasons; ARM_PERMIT per mode |
| `BOOT` | `FAULT` | Self-check failed | — |
| any | `FAULT` | §5.5 condition | ARM_PERMIT low, zero duty, bridges asleep |
| any except `FAULT`/`BOOT` | `SERVICE_CHARGE` | Charger cover opens or plug link appears | ARM_PERMIT low (latch drops), head branches forced off, `CHARGER` latched |
| any except `FAULT`/`BOOT`/`SERVICE_CHARGE` | `LAB` | LAB code on J1 pin 7 or `LAB_KEY_N` open | ARM_PERMIT low, `LAB_KEY` latched |
| `SERVICE_CHARGE` | `LAB` / `HW_INHIBIT` | Cover shut and link absent for the debounce time | ARM_PERMIT high unless `LAB`; `CHARGER` stays latched until local REARM |
| `LAB` | `HW_INHIBIT` | LAB code gone (direct head or absent) | ARM_PERMIT high; `LAB_KEY` stays latched until local REARM |
| `ARMED_IDLE`, `MOVING`, `HOLD`, `PROTECTIVE_STOP` | `HW_INHIBIT` | Latch readback goes low (any chain element, watchdog, ARM_PERMIT withdrawal) | Zero duty immediately (the relays have already disconnected the motors), bridges asleep, command discarded, causes latched, `HW_LATCH` event |
| `STANDBY` | `HW_INHIBIT` | A chain element opens while the latch is down | Cause latched |
| `HW_INHIBIT` | `HW_INHIBIT` | Cause disappears | No change: the reason stays latched; `rearm_ready` becomes true when all elements are healthy |
| `HW_INHIBIT`, `STANDBY` | `ARMED_IDLE` | Local REARM pressed with all elements healthy → latch readback high, no software latch remaining (the same press clears the software latch and hold if their causes are clear) | Latched hardware reasons cleared, `HW_LATCH` event |
| `HW_INHIBIT`, `STANDBY` | `PROTECTIVE_STOP` | As above but a software cause is still present | Software latch stays |
| `STANDBY` | `PROTECTIVE_STOP` | `STOP PROTECTIVE` or failed brake test while the latch is down | — |
| `PROTECTIVE_STOP` (latch down) | `STANDBY` | `REARM_SW` with causes clear | — |
| `ARMED_IDLE` | `MOVING` | Accepted non-zero `DRIVE` | Pre-motion alert per §6.11, then ramp |
| `MOVING` | `ARMED_IDLE` | Command zero (or zero-command TTL ended) and wheels at rest | Bridges braking |
| `MOVING` | `PROTECTIVE_STOP` | Any reason of §5.3 (incl. `CMD_TIMEOUT`, `HOST_LINK_LOST`) | Ramp to rest, latch reason, new nonce |
| `ARMED_IDLE`, `HOLD` | `PROTECTIVE_STOP` | Any latching reason of §5.3 | Latch reason |
| `MOVING`, `ARMED_IDLE` | `HOLD` | Local PAUSE button or `STOP CONTROLLED` | Ramp to rest with `drive.decel_mps2`, hold latched |
| `HOLD` | `ARMED_IDLE` | `REARM_SW` or local REARM button | Hold cleared; motion needs a new `DRIVE` |
| `PROTECTIVE_STOP` (latch set) | `ARMED_IDLE` / `HOLD` is never entered directly | `REARM_SW` or local REARM with causes clear → `ARMED_IDLE` (hold is cleared by the same action) | Latch cleared, event `PSTOP_CLEAR` with operator |
| `PROTECTIVE_STOP` | `PROTECTIVE_STOP` | `REARM_SW` with a cause present, or wrong nonce | Rejected, nothing cleared |
| `ARMED_IDLE` | `STANDBY` | `BRAKE_TEST` completed and passed (latch dropped by the test) | Local REARM required |
| `ARMED_IDLE` | `PROTECTIVE_STOP` | `BRAKE_TEST` failed | `BRAKE_TEST_FAIL` latched |

### 5.7 What clears what — summary

| Latched thing | Cleared by | Not cleared by |
|---|---|---|
| Hardware latch dropped | Local REARM button with all chain elements healthy and ARM_PERMIT high | Any protocol op, link recovery, cause disappearing, MCU reset, power cycle |
| Latched hardware reasons | The latch being set again | — |
| Software protective stop | `REARM_SW` (current nonce) or local REARM button, causes clear | Cause disappearing, link recovery, `DRIVE`, `STOP`, `HELLO` |
| Hold | `REARM_SW` or local REARM button | `DRIVE` |
| `FAULT` | MCU reset | Everything else |
| Direction inhibit (unlatched, §6.3) | The sensor condition ending — it never moved the robot, so nothing restarts | — |

---

## 6. Local functions

### 6.1 Speed, yaw and acceleration caps per op_mode

Hard ceilings come from `contract.yaml › motion` and cannot be configured higher: 0.20 m/s forward, 0.05 m/s reverse, 0.30 rad/s, 0.30 m/s² acceleration. The per-profile defaults below are a chassis-firmware proposal (configuration keys `caps.*`) pending confirmation by the integration lead.

| op_mode | Forward (m/s) | Reverse (m/s) | Yaw (rad/s) | Note |
|---|---:|---:|---:|---|
| `COMMISSIONING` | 0.20 | 0.05 | 0.30 | Full envelope, supervised |
| `SURVEY_SHARED` | 0.10 | 0.05 | 0.30 | Survey speed; technicians may be present |
| `SURVEY_UNATTENDED` | 0.20 | 0.05 | 0.30 | Secured empty trailer |
| `GUIDED` | 0.10 | 0.05 | 0.30 | Close approach |
| `LAB` | 0 | 0 | 0 | No traction |
| `SERVICE` | 0 | 0 | 0 | Boot default |

Ramps: linear acceleration `drive.accel_mps2` (0.30), deceleration `drive.decel_mps2` (0.40 = `controlled_decel_mps2`), protective deceleration `drive.pstop_decel_mps2` (default 1.0), yaw acceleration `drive.yaw_accel_radps2` (1.5). The commanded pair (v, w) is converted to wheel speeds with the calibrated radii and track; each wheel set-point is additionally limited to the profile cap.

### 6.2 Wheel loops

1 kHz speed loop per wheel: feed-forward from the motor model, proportional term on the filtered tick rate, integral term on the accumulated wheel-angle error (so the wheels follow the ramped set-point tick for tick), anti-windup by conditional integration against the duty limit. With the set-point at zero and the wheel below 5 mm/s the bridge is switched to brake (zero-speed clamp) instead of regulating. Current limit `drive.i_limit_a` (default 2.5 A) by duty fold-back from the bridge current measurement. Stall, encoder-consistency and uncommanded-motion supervision as in §5.3. Simulated step response and stopping distances are reported in `firmware/chassis/README.md` and regenerated by the test-suite.

### 6.3 Protective fields from the ToF sensors

Sample validity: a sample is **valid** if its status is OK and it is younger than `tof.max_age_ms` (100 ms). Otherwise it is **invalid** (bad status) or **stale** (too old / sensor offline).

Direction classes of a command: `fwd` (v > 0), `rev` (v < 0), `pivot` (v = 0, w ≠ 0).

| Sensors | Guard | Unlatched inhibit (robot not moving that way) | Latched stop |
|---|---|---|---|
| `CLIFF_FL`, `CLIFF_FR` | `fwd`, `pivot` | Range > `cliff.drop_mm`, invalid, stale or < `cliff.floor_min_mm` → those directions are refused (`DIR_INHIBITED`) | Same condition while moving in a guarded direction → `CLIFF_x` (drop/invalid), `TOF_STALE` or `TOF_DISAGREE`. Drop on `cliff.confirm_n` consecutive valid samples = **confirmed cliff** → `CLIFF_x` latched whenever armed, moving or not |
| `CLIFF_RL`, `CLIFF_RR` | `rev`, `pivot` | as above | as above |
| `LOOK_LO`+`LOOK_LI` (left), `LOOK_RI`+`LOOK_RO` (right) | `fwd` | Speed cap from the stop model, see below | Cap reaches zero while moving forward → `LOOKAHEAD_L` / `LOOKAHEAD_R`. Stale → `TOF_STALE`; pair disagreement (both nominal, see §5.3) → `TOF_DISAGREE` |
| `REAR_L`, `REAR_C`, `REAR_R` | `rev` | Range < `rear.stop_mm` (or invalid/stale) → reverse refused; below `rear.slow_mm` the reverse cap follows the stop model | Inside stop distance while reversing → `FIELD_REAR`; stale while reversing → `TOF_STALE` |

**Stop model** (contract): d(v) = v·t_delay + v²/(2·a_min) + m with `stop.t_delay_ms` = 150, `stop.a_min_mps2` = 0.40, `stop.margin_m` = 0.020. The largest speed that stops within an available distance D is v_cap(D) = −a·t + √(a²t² + 2a(D − m)) for D > m, else 0.

**Look-ahead.** Each oblique sensor normally sees the floor at `look.nominal_mm` ± `look.tol_mm`. A longer or invalid reading means the floor ends (or cannot be seen) at most `look.ahead_m` ahead of the leading support point; a shorter reading means something stands on the floor at range × `look.cos_fwd` ahead. From the first abnormal sample the remaining distance is tracked with odometry: D = distance at detection − distance travelled since. The forward cap is the minimum of the op_mode cap and v_cap(D) over all four sensors; it is released when all sensors read nominal again. When the cap reaches zero during forward motion the reason is latched.

There is no automatic retreat and no degraded running: a stale or invalid sensor in the direction of travel always ends in a latched stop.

### 6.4 Odometry

`left_ticks`/`right_ticks` are the 16-bit hardware quadrature counters extended to signed 64 bits in the 1 kHz interrupt, 9600 counts per wheel revolution at the gearbox output, sign positive for forward rolling on both sides. Every 10th tick (100 Hz) the pair is latched together with the chassis clock read in the same interrupt (`odom.t_us`; jitter < 20 µs on target, exact in the emulator). The host integrates differences of cumulative ticks, so skipped polls lose nothing. Wheel radius and track live in the configuration (`cal.*`, nominal defaults 0.052 m and 0.270 m for the Rev E body) and are applied by the host for odometry and by the chassis for command conversion; neither side may use literals. The chassis firmware contains no dimension of the head or of the head mount: the look-ahead and cliff geometry is expressed relative to the sensors themselves through `look.*`, `cliff.*` and `rear.*`.

### 6.5 IMU and tilt

BMI088, gyro and accelerometer sampled at 1 kHz, rotated to body axes, averaged over each 10 ms window for `DRIVE`. Tilt = angle between the low-passed (τ = 0.5 s) acceleration vector and +z.

### 6.6 Chassis heater

Default off. With a set-point: time-proportional output (2 s period) from a proportional band of `heater.band_c` below the set-point, limited to `heater.max_duty_pct`. Regulation input is the bay NTC. Sensor fault (open/short/out of −45…+90 °C, or bay and pack NTC differing by more than `heater.disagree_c` for 60 s) forces the output off and raises `HEATER_SENSOR`. The firmware is not the over-temperature protection; an independent thermal cut-out is required in hardware.

### 6.7 Panel and buzzer

| State | READY | MOVING | HOLD/WAITING | FAULT | CHARGE/SERVICE | Buzzer |
|---|---|---|---|---|---|---|
| `BOOT` | ON | ON | ON | ON | ON | one chirp |
| `STANDBY` | BLINK_SLOW | OFF | OFF | OFF | OFF | — |
| `ARMED_IDLE` | ON | OFF | OFF | OFF | OFF | — |
| `MOVING`, alert phase | ON | BLINK_FAST | OFF | OFF | OFF | beep 4 Hz for `alert.premotion_ms` |
| `MOVING` | ON | ON | OFF | OFF | OFF | one chirp at a start from rest without alert |
| `HOLD` | OFF | OFF | ON | OFF | OFF | one beep on entry |
| `PROTECTIVE_STOP` | OFF | OFF | BLINK_FAST | OFF | OFF | three beeps on entry |
| `HW_INHIBIT` | OFF | OFF | BLINK_2 | OFF | OFF | — |
| `FAULT` | OFF | OFF | OFF | ON | OFF | long beep on entry |
| `SERVICE_CHARGE` | OFF | OFF | OFF | OFF | ON (BLINK_SLOW while charging) | — |
| `LAB` | OFF | OFF | OFF | OFF | BLINK_2 | — |

`BLINK_SLOW` 1 Hz, `BLINK_FAST` 4 Hz, `BLINK_2` two flashes per 2 s. FAULT additionally blinks slowly in any mode while a warning flag is active. The REARM button lamp blinks when a press would have an effect (`rearm_ready`, or a clearable software latch/hold). The HANDS-ON lamp is driven by hardware from the chain.

### 6.8 Stationary brake test

1. Preconditions: at rest, latch set, VMOT ≥ `brake.vmot_min_v`, both brake relays read "driving".
2. ARM_PERMIT low. Measure the time to latch readback low (limit `brake.latch_drop_max_ms`, 50), to both relay readbacks "braked" (same limit) and to VMOT < `brake.vmot_off_v` (1.0 V; limit `brake.vmot_decay_max_ms`, 1000).
3. With the latch down, wake the bridges and apply `brake.probe_duty_pct` (10 %) to each side for 100 ms. Motor current must stay below `brake.probe_i_max_a` (0.1 A) and the wheels must not move (< 10 ticks): the bridges are isolated from the motors and from VMOT.
4. Bridges asleep, ARM_PERMIT high again, result logged as `BRAKE_TEST` event.

The test proves the switching elements, not the braking torque; the stopping distance under dynamic braking is established by the moving trial VT-003.

### 6.9 Watchdog

The external window watchdog is strobed only by the 100 Hz supervision task, and only when, since its previous run, (a) the 1 kHz control tick ran 10 ± 2 times, (b) the control tick passed all of its program-flow checkpoints, (c) the control tick itself reports that the supervisor is on time, (d) the background loop (protocol, sensor buses) made progress within 500 ms, (e) no `TIMING` fault is latched. A stopped or runaway control loop, a stopped supervisor or a stalled background loop therefore stops the strobe, the watchdog opens `WDG_OK`, the latch drops and the MCU is reset (the reset path through NRST is a board decision).

### 6.10 Stationarity evidence for scaler counts

`stationary` in `DRIVE` and `STATE` supports the contract rule that a scaler count is valid only while both wheel encoders and the gyro confirm zero motion (`survey_methods.common`).

- Every millisecond the firmware tests: left encoder increment = 0 **and** right encoder increment = 0 **and** the IMU delivered a sample **and** |gyro| < `stationary.gyro_max_radps` (default 0.05 rad/s) on all three axes.
- `since_us` is the chassis-clock time of the first millisecond of the current unbroken run of such samples; it is `null` while the test fails. One encoder count (34 µm of travel) or one gyro sample over the threshold restarts the run.
- `is_stationary` is true once the run has lasted `stationary.min_ms` (default 100 ms).

Host rule for a count window [t_a, t_b] on the chassis clock: valid if a `stationary` sample taken at or after t_b shows `is_stationary` true and `since_us` ≤ t_a (the same run covers the whole window), **and** no event of kind `MODE`, `PSTOP`, `HOLD`, `HW_LATCH`, `CHAIN`, `PERMIT`, `J1`, `J2`, `BUTTON` or `BOOT` has `t_us` inside the window (§7; `event_seq` in every `DRIVE` reply tells the host when to read the log). All stop and inhibit transitions are in that list. A count that spans an MCU reset is invalid by the changed `boot_id`.

Limits: an uncalibrated gyro zero-rate offset (BMI088: up to about 0.02 rad/s, UNVERIFIED) counts against the threshold; with the IMU failed `is_stationary` is always false. Evidence class of the function: simulated.

### 6.11 Pre-motion alert and idle time

| Start from rest | Alert |
|---|---|
| First motion after arming, after any latched stop, hold or hardware inhibit, after an MCU boot | Full alert `alert.premotion_ms` (default 1500 ms, minimum 500 ms): buzzer 4 Hz, MOVING indicator flashing, wheels held |
| Chassis idle at rest longer than `alert.rest_ms` (default 5000 ms) | Full alert |
| Idle at rest for less than `alert.rest_ms` (short hops of a step-and-count survey, direction changes) | No delay; one 120 ms chirp when the wheels start |

"Idle" is measured from the moment the wheels came to rest with a zero set-point. With the contract defaults for `STEP_AND_COUNT` (0.5 s settle + 10 s count) each station exceeds the 5 s default, so every hop would be preceded by the full 1.5 s alert; a host that runs step-and-count sets `alert.rest_ms` above its longest count (up to 600 000 ms) — a deliberate, logged `CONFIG_SET` — and then gets one full alert at the start of the series and a chirp per hop. Whether that is acceptable with technicians present is an operating decision (RQ-051), not a firmware one.

---

## 7. Event log

128 newest events in RAM, numbered from 1 after each boot. Event 1 is always `BOOT`. Events are created in the 1 kHz interrupt at the time of the transition, independently of polling.

| `kind` | `detail` members | Created when |
|---|---|---|
| `BOOT` | `reset` (cause), `boot_count`, `fw`, `prev_mode`, `prev_uptime_s`, `brownout` (bool) | Start-up. `prev_*` come from a reset-surviving RAM record of the previous run (null after power-on). |
| `BROWNOUT` | `vbat_v` | VBAT fell below `batt.brownout_v` (9.5 V) — also logged from the retained record after the reset it caused |
| `CHAIN` | `el` (`MODE_RUN`, `ESTOP_A`, `ESTOP_B`, `HANDS_ON`, `CHG_COVER`, `CHG_PLUG_LINK`, `HEAD_DOCK`, `HEAD_LOOP_OK`, `HEAD_LOOP_SHORT`, `LAB_KEY_N`, `BODY_BUMPER_L`, `BODY_BUMPER_R`, `WDG_OK`, `BRAKE_L`, `BRAKE_R`), `closed` (bool) | Debounced transition of that readback |
| `HW_LATCH` | `set` (bool), `reasons` (latched set at that moment) | Latch readback transition |
| `PERMIT` | `on` (bool), `why` (`NORMAL`, `UNCOMMANDED_MOTION`, `STOP_ESCALATION`, `BRAKE_TEST`, `MODE`) | ARM_PERMIT output change |
| `J1` | `from`, `to` (`head_presence`), `ohm` | J1 presence class change |
| `J2` | `present` (bool) | J2 presence change |
| `BUTTON` | `name` (`REARM`, `PAUSE`), `pressed` (bool) | Button transition |
| `MODE` | `from`, `to` | Mode change |
| `PSTOP` | `reason`, `v_mps` (speed at the trigger) | A protective-stop reason is latched |
| `PSTOP_CLEAR` | `by` (`REARM_SW`, `LOCAL`), `operator` (first 15 characters), `cleared` | Software latch cleared |
| `HOLD` | `on` (bool), `why` | Hold latched/cleared |
| `REARM_REJECT` | `why` (`CAUSE_ACTIVE`, `NONCE`), `operator`, `active` | Rejected re-arm |
| `OP_MODE` | `from`, `to` | Profile change |
| `CONFIG` | `key`, `old`, `new`, `gen` | Configuration change (also `key:"_defaults"` when flash was invalid at boot) |
| `HEAD_POWER` | `electronics`, `heater_enable`, `why` (`HOST`, `PRESENCE`, `CHARGE`, `EFUSE`, `BOOT`) | Head branch switch change |
| `FAULT` | `flag`, `on` (bool) | Fault/warning flag change |
| `BRAKE_TEST` | `passed`, `fail` | Test finished |
| `LINK` | `up` (bool), `session` | Session opened by `HELLO` / link supervision lost the host |
| `TOF` | `id`, `status` | A sensor changed between valid and not valid (rate-limited to one per sensor per second) |

---

## 8. Configuration keys

Stored as 32-bit values in flash with CRC. `rw` = settable with `CONFIG_SET`. Calibration keys are those the contract lists (wheel radius, track, field distances, speed caps); the others are engineering values.

| Key | Default | Min | Max | Unit | Meaning |
|---|---:|---:|---:|---|---|
| `id.serial_no` | 1 | 0 | 999999 | — | Serial number |
| `id.hw_rev` | 1 | 1 | 26 | — | 1 = "A" |
| `cal.wheel_radius_l_m` | 0.0520 | 0.045 | 0.060 | m | Left rolling radius |
| `cal.wheel_radius_r_m` | 0.0520 | 0.045 | 0.060 | m | Right rolling radius |
| `cal.track_m` | 0.2700 | 0.20 | 0.34 | m | Effective track (nominal: Rev E body, contract `frames.wheel.track_mm`) |
| `caps.commissioning.v_fwd_mps` | 0.20 | 0 | 0.20 | m/s | |
| `caps.commissioning.v_rev_mps` | 0.05 | 0 | 0.05 | m/s | |
| `caps.commissioning.w_radps` | 0.30 | 0 | 0.30 | rad/s | |
| `caps.survey_shared.v_fwd_mps` | 0.10 | 0 | 0.20 | m/s | |
| `caps.survey_shared.v_rev_mps` | 0.05 | 0 | 0.05 | m/s | |
| `caps.survey_shared.w_radps` | 0.30 | 0 | 0.30 | rad/s | |
| `caps.survey_unattended.v_fwd_mps` | 0.20 | 0 | 0.20 | m/s | |
| `caps.survey_unattended.v_rev_mps` | 0.05 | 0 | 0.05 | m/s | |
| `caps.survey_unattended.w_radps` | 0.30 | 0 | 0.30 | rad/s | |
| `caps.guided.v_fwd_mps` | 0.10 | 0 | 0.20 | m/s | |
| `caps.guided.v_rev_mps` | 0.05 | 0 | 0.05 | m/s | |
| `caps.guided.w_radps` | 0.30 | 0 | 0.30 | rad/s | |
| `drive.accel_mps2` | 0.30 | 0.05 | 0.30 | m/s² | |
| `drive.decel_mps2` | 0.40 | 0.20 | 1.0 | m/s² | Controlled stop |
| `drive.pstop_decel_mps2` | 1.0 | 0.40 | 2.0 | m/s² | Protective stop ramp |
| `drive.yaw_accel_radps2` | 1.5 | 0.2 | 3.0 | rad/s² | |
| `drive.kp` | 0.12 | 0 | 2.0 | duty·s/rad | Wheel loop proportional gain (wheel angular speed) |
| `drive.ki` | 2.5 | 0 | 50 | duty/rad | Wheel loop integral gain |
| `drive.i_limit_a` | 2.5 | 0.5 | 5.0 | A | Per-motor current limit |
| `drive.stall_ms` | 500 | 100 | 2000 | ms | |
| `drive.enc_fault_ms` | 100 | 20 | 500 | ms | |
| `drive.uncmd_ticks` | 600 | 50 | 5000 | ticks | ≈ 20 mm of uncommanded travel at the nominal radius |
| `drive.motor_r_ohm` | 2.2 | 0.5 | 10 | Ω | Motor model (encoder plausibility, feed-forward) |
| `drive.motor_ke` | 1.65 | 0.5 | 5 | V·s/rad | Back-EMF constant at the wheel |
| `link.timeout_ms` | 1000 | 300 | 5000 | ms | Host link supervision while armed |
| `alert.premotion_ms` | 1500 | 500 | 5000 | ms | Pre-motion alert |
| `alert.rest_ms` | 5000 | 0 | 600000 | ms | Idle time at rest after which the full alert is required again (§6.11) |
| `stationary.gyro_max_radps` | 0.05 | 0.005 | 0.5 | rad/s | §6.10 |
| `stationary.min_ms` | 100 | 0 | 2000 | ms | §6.10 |
| `tof.max_age_ms` | 100 | 40 | 250 | ms | |
| `tof.disagree_ms` | 200 | 50 | 1000 | ms | |
| `cliff.drop_mm` | 60 | 20 | 200 | mm | Downward range above this = drop |
| `cliff.floor_min_mm` | 8 | 0 | 50 | mm | Below this = blocked window |
| `cliff.confirm_n` | 3 | 1 | 10 | samples | |
| `look.nominal_mm` | 150 | 50 | 600 | mm | Oblique range to nominal floor |
| `look.tol_mm` | 40 | 10 | 200 | mm | |
| `look.ahead_m` | 0.12 | 0.03 | 0.50 | m | Floor intersection ahead of the leading support point |
| `look.cos_fwd` | 0.80 | 0.3 | 1.0 | — | Horizontal forward fraction of the oblique range |
| `look.pair_tol_mm` | 60 | 10 | 300 | mm | |
| `rear.stop_mm` | 120 | 40 | 500 | mm | |
| `rear.slow_mm` | 300 | 60 | 1000 | mm | |
| `stop.t_delay_ms` | 150 | 20 | 500 | ms | Stop model |
| `stop.a_min_mps2` | 0.40 | 0.1 | 2.0 | m/s² | Stop model |
| `stop.margin_m` | 0.020 | 0 | 0.2 | m | Stop model |
| `stop.escalate_ms` | 300 | 100 | 2000 | ms | §5.4 |
| `safety.allow_retreat` | 0 | 0 | 1 | bool | §5.3 |
| `safety.retreat_v_mps` | 0.05 | 0.01 | 0.05 | m/s | |
| `safety.require_brake_test` | 1 | 0 | 1 | bool | |
| `imu.tilt_max_deg` | 15 | 3 | 45 | ° | |
| `imu.tilt_ms` | 200 | 20 | 2000 | ms | |
| `batt.stop_v` | 11.2 | 10.0 | 13.0 | V | |
| `batt.warn_v` | 12.0 | 10.0 | 13.5 | V | |
| `batt.stop_soc_pct` | 5 | 0 | 50 | % | |
| `batt.brownout_v` | 9.5 | 8.0 | 11.0 | V | |
| `temp.min_c` | −25 | −40 | 10 | °C | |
| `temp.max_c` | 60 | 30 | 80 | °C | |
| `heater.band_c` | 2.0 | 0.5 | 10 | °C | |
| `heater.max_duty_pct` | 100 | 0 | 100 | % | |
| `heater.max_c` | 35 | 10 | 50 | °C | |
| `heater.disagree_c` | 15 | 2 | 40 | °C | |
| `chain.close_debounce_ms` | 50 | 5 | 500 | ms | |
| `chain.pres_settle_ms` | 20 | 5 | 500 | ms | |
| `brake.latch_drop_max_ms` | 50 | 5 | 500 | ms | |
| `brake.vmot_min_v` | 9.0 | 5 | 12 | V | |
| `brake.vmot_off_v` | 1.0 | 0.2 | 5 | V | |
| `brake.vmot_decay_max_ms` | 1000 | 50 | 2500 | ms | |
| `brake.probe_duty_pct` | 10 | 2 | 30 | % | |
| `brake.probe_i_max_a` | 0.1 | 0.02 | 1.0 | A | |

---

## 9. Host obligations (summary)

1. `HELLO` after every connect; compare `boot_id`; discard clock fit, sequence state and transaction ids when it changes.
2. Fresh `id` for every request; fresh, increasing `seq` for every `DRIVE`.
3. Treat `accepted:false` as "the robot is not executing my command" and stop integrating planned motion; never resend old commands after a stall — issue a new one with a new TTL.
4. Read `EVENTS` whenever `event_seq` advances; archive them; act on `gap`. Validate scaler counts with §6.10.
5. Present `REARM_SW` only on a deliberate operator action, with the nonce read after the stop.
6. Use `STOP PROTECTIVE` with a reason for stops that originate in host protective functions.

## 10. Open points

- Per-op_mode cap table (§6.1) and `rearm_nonce` semantics (§3.6) are proposals of this document; the contract op table lists `nonce` without semantics.
- The contract `STATE` content does not always fit in the 2048-byte record (§3.4). A larger chassis record limit (4096) would remove the compaction rules; requested in `firmware/chassis/CONTRACT_CHANGE_REQUESTS.md`.
- `alert.rest_ms` default (5 s) versus the step-and-count station time (§6.11).
- A local PAUSE can at present be released remotely by `REARM_SW`; whether local pauses should require local release is an operating-procedure decision.
- All field distances and the stop-model inputs are design values; VT-003/004/005/035 replace them.
