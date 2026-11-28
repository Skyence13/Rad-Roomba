# Chassis link interface control document — RR-CHS 1.0

**Status: draft for design 0.4 (written against contract 0.4.0-draft4; IB-34 look-sensor set and the 0.290 m tail swept radius of 0.4.0-draft7 applied, the draft7 enum additions `LATCH_UNEXPLAINED` / `STOP_ESCALATED` used since the traction-inhibit review fixes). Owner: chassis firmware lead.** Board facts are those of RR-CHS-MAIN rev A stage 2 (`electronics/chassis_main/design/CONTRACT_CHANGE_REQUESTS.md` CCR-E02/E03, `electronics/analysis/chassis_safety_chain.md`), cross-checked against the netlist export by `firmware/chassis/tools/check_pinmap.py`. Expands `interface/system/contract.yaml › chassis_link`. Where this document and the contract disagree, the contract wins and the disagreement is a defect to report. Machine-readable companion: [`chassis_link.schema.json`](chassis_link.schema.json). Reference implementation: `firmware/chassis/core/` (the same code runs in the emulator `rr_chassis_sim` and on the STM32G474).

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
| Reply time | Design target ≤ 5 ms from the LF of the request to the first byte of the reply for every op except `BRAKE_TEST` (≤ 4 s) and `CONFIG_SET` (≤ 100 ms, flash write); not yet measured on hardware. Host timeout recommendation: 50 ms (cyclic ops), then retry with the same `id`. |

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
| `chain` | object | One bool per `safety_chain` id — `MODE_RUN`, `ESTOP`, `HANDS_ON`, `CHG_COVER`, `HEAD_DOCK`, `HEAD_LOOP`, `LAB_KEY_N`, `BODY_BUMPER`, `WDG_OK`, `ARM_PERMIT` — **live** readback, true = element **known closed**. false = open **or unknown** (an element behind an open one cannot be seen, §4.1a); `DIAG.chain_state` tells the two apart. `ESTOP` is true only if both poles are closed; `CHG_COVER` only if the cover is shut and the plug link absent; `ARM_PERMIT` from `CHAIN_END_RB`. |
| `hw_inhibit_reasons` | array of enum | **Latched** reasons (§5.2) |
| `protective_stop_reasons` | array of enum | **Latched** reasons (§5.3) |
| `head_presence` | enum `head_presence` | J1 pin-7 decode (§4.2) |
| `j2_present` | bool | J2 pin-7 link |
| `rails` | object | `vbat_v`, `vmot_v`, `ibat_a` (positive = discharge), `i_drive_a[2]` (left, right, magnitude), `i_head_a`, `i_head_htr_a`, `i_chs_htr_a`, `v5_v`. A value that could not be measured is `null`. |
| `battery` | object | `soc_pct` (0–100 or null), `temp_c[2]` (charger thermistor, pack NTC; null if faulty), `charge_state` (`NONE`, `PRECHARGE`, `CC`, `CV`, `DONE`, `TEMP_INHIBIT`, `FAULT`, `UNKNOWN`) |
| `temps` | object | `board_c`, `bay_c` |
| `tof` | array[11] | `{id, range_mm, status, age_ms}`; `id` ∈ `CLIFF_FL, CLIFF_FR, CLIFF_RL, CLIFF_RR, LOOK_FL, LOOK_RL, LOOK_RR, LOOK_FR, REAR_L, REAR_C, REAR_R` in this index order (IB-34: index 4 `LOOK_FL` J_TOF4 mux 0 ch 2, 5 `LOOK_RL` J_TOF5 mux 1 ch 2, 6 `LOOK_RR` J_TOF6 mux 0 ch 3, 7 `LOOK_FR` J_TOF7 mux 1 ch 3); `status` ∈ `OK, NO_TARGET, INVALID, STALE, OFFLINE`; `range_mm` null unless `OK`; `age_ms` saturates at 9999 |
| `bumpers` | object | `body_l`, `body_r`: bool, true = pressed/open. `head_loop`: `OK`, `OPEN`, `SHORT`. `head_loop_ohm`: analog estimate (null above 100 kΩ) |
| `panel` | object | `buttons`: `{rearm, pause}` bool pressed. `leds`: `{ready, moving, hold, fault, charge}` each `OFF`, `ON`, `BLINK_SLOW`, `BLINK_FAST`, `BLINK_2`. **(+)** `buzzer`: bool, `pattern`: requested host pattern |
| `heater` | object | `chassis_duty_pct` (0–100); **(+)** `chassis_setpoint_c` (number or null = off), `sensor_ok` |
| `faults` | array of string | Active internal fault and warning flags (§5.5) |
| `stationary` **(+)** | object | As in `DRIVE`, §6.10 |
| `rearm_nonce` **(+)** | u32 | §3.6 |
| `rearm_ready` **(+)** | bool | A press of the local REARM button will set the hardware latch now (stage 4: `SET_READY_RB` high ≥ 30 ms, loop self-test passed, chain closed, board ≤ 45 °C; §4.6) |
| `rearm_refusal` **(+)** | string or null | Why the last REARM press made with the latch down did **not** set it (also the `REARM_REFUSED` event): `NOT_READY` (SET_READY low: C_SET not yet charged, untouched), `SUPPLY_LOW` (charge or swap the pack), `COIL_HOT` (offered with the warning, did not set), `CHAIN_OPEN`, `REARM_HELD`, `REARM_HELD_AFTER_SET` (armed, then dropped because REARM was held 5 s), `PERMIT_WITHHELD` (ARM_PERMIT low: brake test, 50 ms drop hold, readback checks), `LOOP_TEST` (loop self-test running/pending), `FAULT_OR_MODE`, `TOO_SHORT` (set contact closed < 12 ms), `PARTIAL` (K1 closed without the hold path: released, not a weld), `SET_FAILED` (offered and nothing set). `null` while latched or after a successful set. Omitted with `rearm_ready` when the record is compacted |
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

Args: `chassis_setpoint_c`: number −10 … 30, or `null` = automatic thermal policy (contract `power.thermal_policy`, DEC-045). Default after every boot: automatic. A host set-point can only raise the policy floor. Body: `{chassis_setpoint_c, active_setpoint_c (+), duty_pct, bay_c, sensor_ok}`; `active_setpoint_c` is the set-point in force (policy floor or host value).

Regulation (§6.6) runs locally. The heater is forced off, whatever the set-point, on a temperature-sensor fault, above `heater.max_c`, on an eFuse fault, in `BOOT`/`FAULT`, and when the battery is below `batt.warn_v` without a charger. It is permitted in `SERVICE_CHARGE` (warming a cold pack before charging, the +5 °C policy floor).

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

Args: `{}`. Runs the stationary brake-relay and VMOT-drop self-test (§6.8) and replies when it has finished (typically 2.2 s — VMOT decays through the 1 kΩ bleed on 810 µF, τ 0.8 s, to 1 V — at most 3.7 s). The host keeps polling meanwhile (answers `BUSY`), which also keeps the link supervision of §5.3 satisfied. While it runs, any other request is answered `BUSY`; a retry of the `BRAKE_TEST` request itself with the same `id` returns the result when available.

Precondition: mode `ARMED_IDLE` (hardware latch set, at rest), or `PROTECTIVE_STOP` whose only latched reason is `BRAKE_TEST_FAIL` with the hardware latch set. Otherwise `REJECTED / NOT_ARMED_IDLE`.

**The test drops the hardware latch on purpose.** Afterwards the chassis is in `STANDBY` and the operator must press the local REARM button. A passed test satisfies `safety.require_brake_test` until the next MCU boot.

| Body member | Meaning |
|---|---|
| `passed` | bool |
| `fail` | array of codes: `PRECOND_VMOT`, `PRECOND_RELAY`, `LATCH_NOT_DROPPED`, `RELAY_L`, `RELAY_R`, `VMOT_NOT_REMOVED`, `BRIDGE_CURRENT_L`, `BRIDGE_CURRENT_R`, `WHEEL_MOVED`, `K1_NOT_RELEASED`, `K1_WELDED` |
| `latch_drop_ms` | Time from ARM_PERMIT low to latch readback low (limit `brake.latch_drop_max_ms`) |
| `relay_ms` | Time until both brake relays read "braked" |
| `vmot_decay_ms`, `vmot_end_v` | Time until VMOT < `brake.vmot_off_v`, and the final value |
| `probe_i_a[2]` | Motor current while a probe duty is applied with the latch dropped (must be ≈ 0) |
| `moved_ticks[2]` | Encoder movement during the test |
| `mode` | Mode after the test |

Stage 3 adds a last step: with the latch down `LATCH_NC_RB` must read high (`K1_NOT_RELEASED` otherwise), then ARM_PERMIT is raised with every element closed and **no REARM**, and for 100 ms neither `LATCH_RUN_RB` nor the latch readback may rise (`K1_WELDED`). With the IOX_D readbacks a welded K1 is visible directly: pole A through its NC contact, pole B through K1_RUN. A failed test latches `PROTECTIVE_STOP / BRAKE_TEST_FAIL`; the cause stays active until a later test passes. If the latch does not drop with ARM_PERMIT low, the chassis additionally enters `FAULT` (`LATCH_STUCK`).

**What the test can and cannot show (review C1).** `HW_LATCH_RB` is the tap on RUN_12V, and RUN_12V is CHAIN_END switched by K1 pole B, so dropping ARM_PERMIT removes it whether or not K1 is welded: the test **cannot** see a welded K1 or a K1_SET short. It shows: the chain opens through U24 and RUN_12V goes (a stuck U24 or RUN_12V/CHAIN_END fed from elsewhere → `LATCH_STUCK`), both brake relays release (both NO contacts open), VMOT is removed, the probe moves nothing. A welded K1 is caught when ARM_PERMIT returns high after the test (and after every boot, the first time ARM_PERMIT goes high): the latch must then stay down until a qualified REARM, otherwise `LATCH_NO_REARM`.

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
| `readbacks` | String of 23 characters `0`/`1`: debounced inputs in this order — `MODE_RUN, ESTOP_A, ESTOP_B, HANDS_ON, CHG_COVER, CHG_PLUG_LINK, HEAD_DOCK, HEAD_LOOP_OK, HEAD_LOOP_SHORT, LAB_KEY_N, BODY_BUMPER_L, BODY_BUMPER_R, WDG_OK, BRAKE_L, BRAKE_R, HW_LATCH, J2_PRES, BTN_REARM, BTN_PAUSE, DRV_FAULT_L, DRV_FAULT_R, REARM_SET, CHAIN_END` (1 = node live / healthy / present / pressed; `HEAD_LOOP_SHORT`, `DRV_FAULT_x`: 1 = asserted; `REARM_SET` (stage 4 G4, IOX_A GPB6, was `BUS_CLAMP`): REARM set contact closed; `CHG_PLUG_LINK`: 1 = node CH_N4 live, i.e. plug link absent). The chain readbacks are **node** taps (§4.1a); `BRAKE_x` holds its last valid value while the bridges are awake. |
| `chain_state` **(+)** | One of `CLOSED`, `OPEN`, `UNKNOWN` per `safety_chain` id (§4.1a) |
| `chain_end` **(+)** | `CHAIN_END_RB` (IOX_B P17, node after the ARM_PERMIT element), `null` while IOX_B cannot be read |
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

### 4.1a Node semantics, ARM_PERMIT readback, brake-relay readback (IB-01, IB-02)

Electrical facts from the board (CCR-E02/E03, `chassis_safety_chain.md` §2.3/§2.4):

- The readbacks `MODE_RUN`, `ESTOP_A`, `HANDS_ON`, `CHG_COVER`, `CHG_PLUG_LINK`, `HEAD_DOCK`, `BODY_BUMPER_L`, `BODY_BUMPER_R`, `WDG_OK` are taps on the chain nodes CH_N1 … CH_N9: a tap reads "the chain is live up to and including this element". `HEAD_LOOP_OK`/`HEAD_LOOP_SHORT`/`LAB_KEY_N` are comparator outputs (the input condition of the photo-MOS U21/U22; CH_N6/CH_N7 have no readback). `ESTOP_B` is a separate detector on the coil return. `CHAIN_END_RB` (IOX_B P17, read over I²C at 100 Hz, never driven) is the node after the ARM_PERMIT element.
- **Element state.** An element is `CLOSED` if its node is live, `OPEN` if its upstream node is live and its own node dead, `UNKNOWN` if its upstream node is dead. `BODY_BUMPER_L` is known only while CH_N5 is live and both comparators say "closed". `ESTOP` = pole A (known while CH_N1 is live) and pole B (always known). `HEAD_LOOP`, `LAB_KEY_N` are always known (comparators + analog decode). `ARM_PERMIT` is known while CH_N9 is live and IOX_B is readable. Only `OPEN` elements become live causes (§4.4); a `CHAIN` event is logged when a known readback changes, never when it becomes unknown (so an E-stop press logs `ESTOP_A`/`ESTOP_B`, not every node behind it). With the selector in SERVICE the cover/plug elements are unknown; the charger is then recognised from its own telemetry (input power present), see `CHARGER` in §4.4.
- **Plausibility.** A node live behind a dead upstream node for 20 ms (harness short to a live conductor, readback fault, shorted U21/U22 — single-fault rows 8, 16, 23, 31, 32) enters `FAULT` with `CHAIN_IMPLAUSIBLE`. The E-stop pole comparison (`ESTOP_DISCREPANCY`) is made only while CH_N1 is live.
- **ARM_PERMIT readback.** Each `CHAIN_END_RB` sample is compared with the ARM_PERMIT output and the raw CH_N9 readback at the time of the sample, both stable for the 10 ms before it; three consecutive bad samples decide. `CHAIN_END` live with ARM_PERMIT low (U24 shorted / PB10 stuck, single-fault row 38) → `FAULT` `PERMIT_STUCK_ON` and the **watchdog strobe is withheld**, so the external watchdog opens the chain at WDG_OK upstream of the suspect element and (JP1 closed) resets the MCU; after the reset the check fails again during `BOOT`, so the chassis stays inhibited and shows the flag in the `BOOT` windows. `CHAIN_END` dead with ARM_PERMIT high and CH_N9 live → warning `PERMIT_STUCK_OFF`, cause `MCU_NOT_READY` (fails safe; no arming). `CHAIN_END` live behind a dead CH_N9 → `CHAIN_IMPLAUSIBLE`. While `CHAIN_END_RB` cannot be read for 100 ms (warning `IOX_B`) ARM_PERMIT is withheld: the element is never closed unsupervised. The check runs at boot (ARM_PERMIT low) and at every permit change.
- **Brake relays.** `BRAKE_x_RB` (OR over both poles) is valid only while the bridges sleep: it is evaluated after the bridges have been commanded asleep, or the latch readback has been low, for 3 ms; otherwise its last valid value is held. After the latch is set the bridges stay asleep until both relays read "connected", so both relay pick-ups are proven on every arming before any PWM (a relay that does not pick up within 200 ms is `VMOT_FAULT`).

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
| `CHARGER` | Charge-inlet cover element or plug-link element open (§4.1a), **or** the charger reports input power (needed when those nodes are dead upstream, e.g. selector in SERVICE) |
| `HEAD_UNDOCKED` | Dock switch open |
| `HEAD_LOOP_OPEN` | Loop above the window while J1 is present |
| `HEAD_LOOP_SHORT` | Loop below the window |
| `J1_ABSENT` | `head_presence` = `ABSENT` (a loop opening with J1 absent is attributed to the disconnect) |
| `LAB_KEY` | `head_presence` shows the LAB resistor, or the hardware `LAB_KEY_N` element is open |
| `BODY_BUMPER` | Either body bumper switch open |
| `WATCHDOG` | External watchdog output not OK |
| `MCU_NOT_READY` | Firmware is withholding `ARM_PERMIT` (boot, fault, charge/LAB mode, stop escalation, brake test, presence `FAULT`, `CHAIN_END_RB` unreadable), or the ARM_PERMIT element does not close (`PERMIT_STUCK_OFF`) |
| `VMOT_FAULT` | Latch set but VMOT below `brake.vmot_min_v` for > 100 ms; latch dropped but VMOT still present after the decay time (`brake.vmot_decay_max_ms`, 3500 ms); brake-relay readback (while valid, §4.1a) inconsistent with the latch for > 200 ms. While the condition is present the firmware also withholds ARM_PERMIT. |
| `LATCH_UNEXPLAINED` | (latched only) the latch dropped with no readback explaining it (contract draft7; was reported as `VMOT_FAULT`) |

### 4.6 Latch, REARM and head-loop rules after the traction-inhibit review (C1, C2, M1, m3, m4, m7)

Review: `docs/reviews/REVIEW_traction_inhibit.md`. All behaviour below is `simulated` (`tests/test_review.c`) on the emulator's netlist-aligned chain model.

- **Qualified REARM.** A rise of `HW_LATCH_RB` (RUN_12V) is accepted only within 250 ms (+ the 50 ms close debounce) after a `REARM_BTN` rising edge that the firmware saw while every chain element read `CLOSED` (§4.1a), ARM_PERMIT was high and the latch was down. Any other rise — latch set with no REARM (welded K1 seal-in, K1_SET shorted to V12_AUX or LAMP_REARM_K in W-018), latch high at boot, RUN_12V fed from a supply — is `FAULT` `LATCH_NO_REARM`: ARM_PERMIT low (U24 is upstream of K1 pole B, so RUN_12V goes even with K1 welded), strobe stopped (§5.5), latched hardware reasons kept.
- **Early or held REARM is refused.** A REARM edge seen while the chain is not closed (and the latch down) holds ARM_PERMIT low for 300 ms, longer than the C_SET set pulse can hold K1 (≈ 245 ms above must-release), so pressing REARM just before releasing a bumper or HANDS-ON does not latch. REARM held > 2 s (`REARM_HELD`) withholds ARM_PERMIT while the latch is down, until released, and (W-018, stage 5 H6) withdraws it when held 5 s after the latch rose. The early press is reported (`REARM_REFUSED`, `CHAIN_OPEN`).
- **Latch that does not drop.** An element known `OPEN` while the latch still reads set for 30 ms (K1 needs 4 ms) is `FAULT` `LATCH_NO_DROP`.
- **Short openings are completed.** Any fall of the latch readback holds ARM_PERMIT low for 50 ms, and every firmware permit withdrawal lasts at least 50 ms: an opening shorter than K1's release time (it removes RUN_12V at once but K1 may hold) cannot let RUN_12V come back without REARM.
- **Head-rail loop (C2).** The analog copy is decoded with bands around the U30 window (0.59–1.55 kΩ): OK 620–1500 Ω, OPEN > 1650 Ω, SHORT < 560 Ω, marginal in between. While the latch is set, an opening or short seen by either channel (analog: two consecutive 1 kHz samples, i.e. 2 ms; comparator: first sample) withdraws ARM_PERMIT and latches `STOP_ESCALATED` — no longer filter, so a real rail press is never filtered out. A comparator/analog disagreement that began while latched and lasts 5 ms (the comparator lags the analog copy by about 1.5 ms) is `FAULT` `LOOP_FAIL`. With the latch down a disagreement for 200 ms is `LOOP_DISCREPANCY`, which withholds ARM_PERMIT.
- **C_SET back-feed (M1).** The current netlist (stage 3, F12) has the diode D_RSET in series with R_SET and the C_SET discharge Q_SDIS: no back-feed, so `chain.backfeed_ms` = 0 and `PERMIT_STUCK_ON`/`CHAIN_IMPLAUSIBLE` act at once, including at boot. On a stage-2 board without D_RSET, C_SET holds CHAIN_END and the nodes behind an opened element up for up to ≈ 10 s; set `chain.backfeed_ms` = 12 000: those two checks are then suspended for that time after CHAIN_END was last really live, and after every boot. During that window a stuck U24 is still caught when it matters: a latch rise with ARM_PERMIT low is `LATCH_STUCK`/`LATCH_NO_REARM` at once, and the mandatory brake test fails `LATCH_STUCK`. Because Q_SDIS empties C_SET whenever the chain is open, REARM can set only after the chain has been closed for a few seconds; `rearm_ready` follows the set stage's `SET_READY_RB` (stage 4, below); since stage 4 the discharge starts only 41–64 ms after CHAIN_END dies, so short permit dips keep the charge.
- **IOX_B reads (m7).** One or a few failed I²C reads of `CHAIN_END_RB` do not drop the latch while it is set: the last good sample is used up to 50 ms old (≥ 4 consecutive failures at 100 Hz). Arming needs the last read to have succeeded. The port re-initialises I²C2 after three consecutive failures.
- **Configuration read-back (M2, M3).** The chain-tap pins carry no internal pull resistors; every 100 ms the port reads back their GPIO mode/pull registers (PD2 must be the TIM8_BKIN alternate function, the rest plain inputs) and the IOX_A IODIRA/IODIRB registers (must be 0xFF: GPA5/GPA7 are the U21/U22 gate nodes); any difference is `FAULT` `PIN_CONFIG`.
- **Watchdog strobe (m2).** WDI is a 5 ms high pulse every 10 ms (raised by the supervisor, lowered by the control tick): falling edges every 10 ms (the TPS3430 is falling-edge triggered, tWDL ≤ 2.22 ms, tWDU ≥ 23.375 ms, stage 3 F9 [D]); also safe if both edges counted (5 ms apart). A hung MCU is caught ≤ 31.6 ms after the last falling edge.
- **Stage 3 board (S3, `electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md` §3.1 F1–F18).** New expander IOX_D (U47, TCA9534, 0x22, read at 100 Hz, configuration register read back = 0xFF, fixed pattern P4..P7 = 1,0,0,0 checked on every read; unknown → `IOX_D`, no arming; while latched the 50 ms / several-failures rule of m7). Readbacks: `LATCH_NC_RB` (K1 pole A released), `LATCH_RUN_RB` (K1_RUN = CHAIN_END through K1 pole B, before U_HOLD), `HEAD_LOOP2_OK_RB` (loop channel B, U46 → U21B, between CH_N6A and CH_N6), `REARM_SET_RB` (REARM set contact). `DIAG.iox_d` reports them. Rules:
  - **`K1_WELD`** (fatal): with the latch readback low for ≥ 20 ms and a fresh sample taken ≥ 10 ms after that, `LATCH_NC_RB` low (pole A operated or welded, NC open) or `LATCH_RUN_RB` high (pole B passing CHAIN_END), on two consecutive samples, with ARM_PERMIT low for ≥ 30 ms (round 4: with CHAIN_END possibly live the same readback is first treated as a PARTIAL set and ARM_PERMIT is withdrawn for 200 ms, see below); not judged within 300 ms of a REARM edge (the 110 ms set pulse may hold K1 alone). U_HOLD is the hardware barrier; this is detection. ARM_PERMIT is never raised while `LATCH_NC_RB` does not read high (boot check "K1 not welded").
  - **`RUN_SHORT`** (fatal): latch readback (RUN_12V tap) high with `LATCH_RUN_RB` low on a sample ≥ 10 ms after the rise: RUN_12V or RUN_HD fed from something other than the latch. FAULT keeps DRV_NSLEEP low.
  - **REARM**: the latch rise is accepted only when both contact lines (aux `REARM_BTN`, set `REARM_SET_RB`) showed closing edges within 110 ms of each other (or, round 4, a tap too short for the set line's sampling) and the rise follows within the window of §4.6; the two lines disagreeing for 200 ms is `REARM_DISCREPANCY` (arming withheld, not fatal); either held > 2 s is `REARM_HELD`.
  - **Head loop, two hardware channels + analog copy.** While latched, an opening seen by channel A, channel B or the analog copy withdraws ARM_PERMIT at once (never filtered). Channels A and B disagreeing about "open" for 20 ms (A reporting a short is not a disagreement): the analog copy arbitrates — it reads open beyond the other channel's threshold → the channel saying "closed" is stuck healthy, a hardware barrier is lost → **`LOOP_FAIL` (fatal)** (round 4 N6: between the two thresholds A open / B closed is `LOOP_HIGH_R`, below); it reads OK or marginal → the channel saying "open" is wrong in the safe direction (it holds the chain open itself) → **`LOOP_DISCREPANCY`** (arming withheld, clears when they agree). The analog copy alone disagreeing with two agreeing hardware channels is `LOOP_DISCREPANCY` (diagnostic third view, F6).
  - **C_SET**: D_RSET and Q_SDIS: no back-feed (`chain.backfeed_ms` = 0), C_SET empty within ≈ 0.3 s whenever CHAIN_END is dead. `rearm_ready`: see "Round 4 / stage 4" below (the stage-3 "2 s of `CHAIN_END_RB` high" was early: ≈ 60 % charge, review N1).
  - `HW_LATCH_RB` (PD2) is still the RUN_12V tap; U9 and the VMOT eFuse take RUN_HD; the TIM8 break input on PD2 is configured (an extra path; it no longer influences U9).
- **Round 4 / stage 4 board (follow-up review `docs/reviews/REVIEW_traction_inhibit_followup.md`; `electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md` §4.1 G1–G12, in the netlist; simulated in `tests/test_rearm.c`).** Supersedes the stage-3 items above where they differ.
  - **IOX_D map (G6):** P0 `LATCH_NC_RB`, P1 `LATCH_RUN_RB`, P2 `HEAD_LOOP2_OK_RB`, P3 `BUS_CLAMP_ACTIVE` (diagnostic → `BUS_CLAMP`), P4 `LOOP_TEST_A` (output), P5 `SET_READY_RB`, P6 `CHN6A_RB`, P7 `LOOP_TEST_B` (output). Integrity: configuration 0x03 = 0x6F and output 0x01 read back every 10th read; input bits 4/7 must read what was written on every read (replaces the stage-3 fixed pattern); otherwise `IOX_D`. Read every 10 ms, every 1 ms during the loop self-test.
  - **`rearm_ready` (N1, G1/G2):** latch down, no fatal flag, no `SET_STAGE_FAULT` / `REARM_RB_FAULT`, mode not BOOT/FAULT/LAB/SERVICE_CHARGE, no REARM held, loop self-test passed, every element closed, ARM_PERMIT high and its element closed, **`SET_READY_RB` high for ≥ 30 ms** (stage 5 H2: the coil temperature is a warning, `COIL_HOT`, not a condition) (the set stage's own comparator: C_SET ≥ 10.8 V; Q_SETC conducts 13–28 ms after it rises). A press while SET_READY is low does not touch C_SET (G1). No fixed delay: ≈ 3.2 s after the chain closes at 12.8 V (T12); simulated 2.8–4.6 s for pack 11.6–13.4 V and C_SET 80–120 µF; in all 36 combinations of pack, board 0–50 °C and C_SET a 200 ms press at the first ready millisecond set the latch (since stage 5 H2 every combination is offered; COIL_HOT is a warning). `SET_READY_RB` high while CHAIN_END has been dead > 1 s is **`SET_STAGE_FAULT`** (comparator stuck; warning, sticky until reset, arming withheld).
  - **Every press gets an outcome (N1, G3).** A REARM aux edge with the latch down is followed within 300 ms by the latch rise or by `REARM_REFUSED` (`STATE.rearm_refusal`) with the reason that applied at the press: `NOT_READY` (SET_READY low: press again when ready), `SUPPLY_LOW` (VBAT < 11.7 V and SET_READY low), `COIL_HOT`, `CHAIN_OPEN`, `REARM_HELD`, `PERMIT_WITHHELD`, `LOOP_TEST` (self-test running or pending), `FAULT_OR_MODE`; if it was offered: `TOO_SHORT` (set contact closed < 12 ms, shorter than the 3.2–11.2 ms set qualification: nothing happened), `PARTIAL` (below) or `SET_FAILED`. A refused press is never a fault. The REARM lamp blinks fast for 2 s after a refusal.
  - **Short taps (N2, G4).** The set contact is read on IOX_A GPB6 at 1 kHz with the aux contact (GPB2), edges from the undebounced lines; the set stage cannot start a pulse before 3.2 ms of closure, so every press that can set shows both edges (≥ 3 samples). The latch rise is accepted with both edges within 110 ms and the rise within the window above, else `LATCH_NO_REARM`. Simulated phase sweep (taps 2/4/6/8/12/20/40 ms × 10 phases of the IOX_D read, K1 operate 3 and 4 ms): every tap either set and was recognised or was refused and reported (`TOO_SHORT`, `PARTIAL`), none fatal; taps ≥ 12 ms always set.
  - **Partial set (N2, G3).** `LATCH_NC_RB` low or `LATCH_RUN_RB` high with the latch down while CHAIN_END may be live (ARM_PERMIT not low for 30 ms) is first a set that did not complete (K1 sealed in by its own contact without U_HOLD; presses of 3–15 ms): ARM_PERMIT withdrawn for 30 ms (stage 5 H4; was 200 ms) (K1 releases in 4 ms), press reported `PARTIAL`, not fatal. `K1_WELD` (fatal) needs the same readback with ARM_PERMIT low for ≥ 30 ms.
  - **Loop self-test before every arming (N3, G5).** With the latch down, every element (but ARM_PERMIT) closed for 100 ms, ARM_PERMIT and CHAIN_END high, no REARM contact closed, no brake test: `LOOP_TEST_A` 30 ms (channel A on GPA5 and `CHN6A_RB` must read open/dead), 20 ms gap, `LOOP_TEST_B` 30 ms (`HEAD_LOOP2_OK_RB` and `BODY_BUMPER_L_RB` must read open/dead, channel A closed), then the outputs off; never both at once, never while latched. Any failure: `LOOP_FAIL` (fatal). For those ≈ 90 ms the chain decode keeps its pre-test view (no events, no latched reasons, no loop-disagreement rules; the latch is down and the test holds the chain open). Repeated after every latch rise and after any element opened. `DIAG.rearm.loop_test` / `loop_tests_passed`.
  - **Shorted loop photo-MOS (N3, G5): `LOOP_SW_SHORT` (fatal).** Channel A open > 10 ms with `CHN6A_RB` high on two samples (U21/Q22), or channel B low > 10 ms with `BODY_BUMPER_L_RB` high on two samples (U21B/Q_LB). Simulated: U21 shorted while armed, rail pressed → channel B drops the latch, `LOOP_SW_SHORT` at once.
  - **Head loop between the channel thresholds (N6, G7).** Channel A opens above 1.55 kΩ, channel B above 1.89 kΩ (stage 4): with the analog copy in 1.65 kΩ – `loop.b_stuck_ohm` (default 2050 Ω; 2900 for a stage-3 board) and A open / B closed, the loop is `HEAD_LOOP_OPEN` plus the warning **`LOOP_HIGH_R`**, not `LOOP_FAIL`. `LOOP_FAIL` only for a channel provably stuck healthy: A closed with the analog copy > 1650 Ω, or B closed with it > `loop.b_stuck_ohm`.
  - **REARM held after the rise (W-018, G11).** Superseded by stage 5 H6 below: 5 s, latched reason `REARM_HELD`.
  - **IOX_B (G8, m8).** P17 no longer gates the C_SET discharge (own RC); the port reads back the IOX_B configuration registers (P17 must stay an input, else `PIN_CONFIG`) and the output registers (rewritten on a mismatch).
- **Stage-4 review (`docs/reviews/REVIEW_traction_inhibit_stage4.md`) and stage 5 (`electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md` "Stage 5", H1–H7, IN NETLIST; the emulator defaults follow the stage-5 netlist; `tests/test_rearm.c`).**
  - **Operating limits created by the chain** (numbers as in `electronics/analysis/chassis_safety_chain.md` §6.1, stage 5):

    | Limit | Value | What the robot does |
    |---|---|---|
    | Re-arm needs the pack at | **≥ 11.7 V** worst case (11.4 V nominal) | below: SET_READY never comes; `REARM_REFUSED` `SUPPLY_LOW` ("charge or swap the pack") |
    | Battery-low protective stop | **11.2 V** (`batt.stop_v`) | stops; between 11.7 and 11.2 V an armed robot drives on but cannot re-arm after a stop |
    | Low-battery re-arm warning | **12.0 V** resting (`rearm.vbat_warn_v`, ≥ 10 s) | warning `BATTERY_REARM_LOW`: end the mission or swap the pack |
    | Guaranteed re-arm | coil (RT1 at K1 + self-heating) ≤ **+45 °C** | above: warning `COIL_HOT`, the press is still offered and may be refused (`REARM_REFUSED` `COIL_HOT`) |
    | REARM press | ≥ **3.2 ms** to be able to set; hold limit **5 s** after the latch rose | buzzer from 1 s; at 5 s the latch drops (`REARM_HELD`, `REARM_HELD_AFTER_SET`); operator procedure: press briefly (< 2 s) |
    | Partial set | ARM_PERMIT dip **30 ms** | `REARM_REFUSED` `PARTIAL`, non-fatal; C_SET kept, press again at once |
  - **Held press (S5, H6).** The hardware sets the latch 7–15 ms into a press, so the firmware cannot know a press will be long before the latch rises, and it cannot defer the set (the set pulse ends ≤ 170 ms after the closure; ARM_PERMIT low during it only makes the press fail). A long press is therefore not refused before the rise; instead the buzzer beeps fast from 1 s of holding after the rise ("release"), and a REARM contact still closed **5 s** (was 2 s) after the rise withdraws ARM_PERMIT: latched reason **`REARM_HELD`** (new `hw_inhibit_reasons` value, was `MCU_NOT_READY`), `REARM_REFUSED` `{"why":"REARM_HELD_AFTER_SET","latch_dropped":true,"action":"RELEASE_REARM_PRESS_BRIEFLY"}`, `STATE.rearm_refusal` = `REARM_HELD_AFTER_SET`. A W-018 crush on both REARM lines now arms for 5 s. While ARM_PERMIT is withheld because a REARM contact is held with the latch down, the live reason is `REARM_HELD` too. Operator procedure: press briefly (< 2 s).
  - **Set-contact readback missed (S3, H1).** A latch rise is legitimate (as before) with both contact lines showing qualified closing edges within 110 ms and the rise within the window. If exactly **one** line shows a qualified press — its edge seen while every element read closed, ARM_PERMIT was high and the latch was down, within the 250 ms (+ debounce) window, and that contact still closed or released < 20 ms before the rise — and the other line shows nothing, the latch is kept and **`REARM_RB_FAULT`** is set (warning, sticky until reset; every later arming withheld; `DIAG.rearm.rb_fault` = `SET_LINE_MISSED`/`AUX_LINE_MISSED`). A rise with **neither** line showing a qualified press is still `LATCH_NO_REARM` (fatal). This does not reopen C1: C1's faults (welded K1 seal-in, K1_SET shorted to a supply, RUN_12V fed) raise the latch without any press, so neither contact line shows a qualified closing edge at the time of the rise and the rule stays fatal for them; a single stuck contact line gives no edge (it is `REARM_HELD`/`REARM_DISCREPANCY`), and a fault that coincides with a genuine operator press (the only case the relaxation admits) is armed exactly as a legitimate press would arm it and then blocks every later arming. H1 (R_SRB 10 k + BAT54 clamp: high level ≥ 3.5 V against VIH(max) 2.73 V) fixes the margin; the rule stays as defence in depth. The emulator models the GPB6 level against VIH(max) = 0.8 × `v3v3`: stage 5 default `v3v3` + 0.2 V (clamp), stage-4 divider selectable (`set_rb_v` 2.80).
  - **Loop diagnosis (S4, H3).** `DIAG.loop_cause` names the cause of a `LOOP_FAIL` or B-only/A-only opening: `A_STUCK_HEALTHY`, `B_STUCK_HEALTHY`, `TEST_PATH_A` (loop self-test path fault, channel A side: Q_LTA stuck on or LOOP_F grounded), `SELF_TEST_A`/`SELF_TEST_B`, `A_ANALOG_DISAGREE`, `B_OPEN_OR_TEST_PATH_B` (B or Q_LTB stuck on; non-fatal `LOOP_DISCREPANCY`), `A_OPEN_OR_TEST_PATH_A` (stage 5: analog copy from LOOP_SNS). Stage 5 (H3, current netlist) takes the analog copy from LOOP_SNS (port: two 1 kHz samples averaged, ≥ 1 ms): a stuck-on Q_LTA reads "A open, analog OK, B closed" = `LOOP_DISCREPANCY` (non-fatal, chain held open by A) with cause `A_OPEN_OR_TEST_PATH_A`, never "B stuck" (simulated). On a stage-4 board (emulator `analog_from_loop_f`) the analog copy shares LOOP_F with channel A, so "A open, analog open, B closed" is ambiguous: `LOOP_FAIL` at once (fail-safe), `loop_cause` = `CHECKING_B`, then with the latch down one 30 ms `LOOP_TEST_B` pulse decides — B goes open → `TEST_PATH_A`, B stays closed → `B_STUCK_HEALTHY`.
  - **Coil temperature (S2, H2).** `COIL_HOT` is now a **warning** flag (coil estimate > 45 °C), no longer a not-ready reason: the press is offered and the hardware decides; a press that then fails is reported `COIL_HOT`. Estimate = board NTC − `rearm.ntc_coil_offset_k` (0) + `rearm.coil_selfheat_k` (10 K) × f, f = latch-set state filtered with τ 300 s (H2: RT1 is next to K1 on stage 5, offset 0; on a stage-4 board, where RT1 is beside the bridges, the offset can be set). The emulator models the coil self-heating (10 K, τ 300 s; simulated: board 38 °C, armed 10 min → estimate 46.6 °C, `COIL_HOT`) and, selectable, a stage-4 NTC above the coil (`board_ntc_rise_k`).
  - **PARTIAL-set dip (H4).** ARM_PERMIT is withdrawn for **30 ms** (not 200 ms, and exempt from the general 50 ms minimum): K1 releases in ≤ 4 ms and the C_SET discharge cannot start before 41 ms, so the operator can press again at once. The ≥ 50 ms rule after a latch drop stays.
  - **Low battery (H5).** Warning **`BATTERY_REARM_LOW`** at VBAT ≤ `rearm.vbat_warn_v` (12.0 V) for ≥ 10 s (0.2 V hysteresis): re-arming may become impossible below 11.7 V, while the `BATTERY_LOW` stop stays at 11.2 V. A `SUPPLY_LOW` refusal carries `"action":"CHARGE_OR_SWAP_PACK"`.
  - **U_HOLD / U_LS.** Stage 5 adds no readback for them (a U_LS readback was rejected by electronics); they stay latent and covered by the service tests through the new top-side header J_SVC (H7). No firmware check is possible.
- **What the firmware still cannot see** (stage 3): a shorted U_HOLD, U_LS or D_RUN (latent; K1 is still a barrier); a welded head-rail switch, head-internal bypass, a welded body-bumper switch, leakage onto LOOP_SNS (no barrier at the chassis for that zone, section 6.1 of the safety-chain analysis); a board short of RUN_HD (`RUN_SHORT`, bridges kept asleep, but relays and VMOT are live: only E-stop pole B and DRV_NSLEEP remain) or of CHAIN_END (the latch can no longer be dropped by the elements; firmware faults and keeps the bridges asleep, the robot coasts without the brake resistor); a supply on both REARM lines at once (arms once like a press, for 2 s since round 4). Also not implemented: the boot watchdog self-test, the dynamic deceleration check. Earlier list: a welded K1 while the robot stays armed (it shows at the next drop/re-close); a brake path that is open or degraded (no dynamic deceleration check); U23 failing closed (no boot watchdog test); a short of CHAIN_END/RUN_12V to a supply when the latch is legitimately set (it shows at the next drop as `LATCH_NO_DROP`); a welded head-rail switch or head-internal bypass.

### 4.5 Board constants behind the readings (IB-02)

From RR-CHS-MAIN rev A (CCR-E03; netlist export `electronics/chassis_main/out/pinmap.json`). Tool-checked against the netlist; not measured on a board.

| Quantity | Value | Source |
|---|---|---|
| ADC reference VREF+ | 3.000 V ±0.2 % (REF3030, U14); also feeds the NTC and PRES_ID pull-ups and the DRV8874 VREF pins | CCR-E03 (a) |
| Bridge current sense IPROPI | 2.49 kΩ → 1.1205 V/A (0.8925 A/V); the bridges chop in hardware at 2.68 A = VREF+/1.1205 V/A, which is also the ADC full scale (readings saturate there). `drive.i_limit_a` (2.5 A, max 2.6 A) folds back below it | CCR-E03 (b), CCR-E06 |
| PRES_ID | 4.70 kΩ 0.1 % pull-up to VREF+ directly on J1 pin 7, no series resistance in the measured path | CCR-E03 (c) |
| Interlock-loop analog copy | V = V5_AUX·1000/(2200 + R_loop) (1.00 kΩ source, 2 × 100 Ω, 1.00 kΩ sense); V5_AUX taken as 5.0 V nominal (UNVERIFIED tolerance; only the diverse analog copy depends on it, the comparator window is ratiometric) | `chassis_safety_chain.md` §2.2 |
| Chain readbacks | node voltages, live up to and including the element (§4.1a); tap reads high above 7.4 V | CCR-E03 (d), §2.3 |
| `BRAKE_x_RB` | OR over both relay poles, valid only with the bridges asleep | CCR-E03 (e), §2.4 |
| VMOT after a latch drop | 1 kΩ bleed on 810 µF, τ 0.8 s | §2.1, §7 step 4 |
| Watchdog window | TPS3430, CWD = NC, SET0 = 0, SET1 = 1: next strobe 2.2–23.4 ms after the previous one; firmware strobes every 10 ms; WDO → NRST through JP1 (normally closed): first strobe due within 23 ms of reset release | §2.2, CCR-E11 |
| Latch-drop dead time to the brake resistor | 10.5 ms (contact element), brake loop 3.22 Ω | `chassis_braking_tables.md` T2/T1 |

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
| `LOOKAHEAD_L`, `LOOKAHEAD_R` | The look-ahead speed cap of the left / right sensor of the pair in the direction of travel (forward: `LOOK_FL`/`LOOK_FR`, reverse: `LOOK_RL`/`LOOK_RR`) reached zero while moving that way | All look sensors on that side report nominal floor |
| `FIELD_REAR` | Rear proximity inside the stop distance while reversing | Rear ranges outside the stop distance |
| `FIELD_FRONT`, `FIELD_LEFT`, `FIELD_RIGHT` | Host `STOP PROTECTIVE` with that reason (the MCU has no front/side ranging; head-rail contact is in the hardwired chain) | Immediately (host owns the cause) |
| `TOF_STALE` | A sensor guarding the direction of travel delivered no valid new sample for `tof.max_age_ms` while moving in that direction | All sensors fresh |
| `TOF_DISAGREE` | A cliff sensor reads below `cliff.floor_min_mm` (blocked window) for `tof.disagree_ms` while moving in a guarded direction (no look-pair comparison, §6.3) | Reading back above the limit |
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

Entered on: K1 welded (`K1_WELD`) or RUN_12V/RUN_HD fed from a supply (`RUN_SHORT`), stage 3 (§4.6); a shorted loop photo-MOS (`LOOP_SW_SHORT`) or a failed loop self-test (`LOOP_FAIL`), stage 4 (§4.6); latch readback rising without a qualified local REARM, or high at boot (`LATCH_NO_REARM`, §4.6); an element known open while the latch still reads set for 30 ms (`LATCH_NO_DROP`); head-loop comparator and analog copy disagreeing for 5 ms while latched (`LOOP_FAIL`, §4.6); a chain-tap pin or an expander pin not configured as a plain input (`PIN_CONFIG`); E-stop pole discrepancy > 200 ms while CH_N1 is live (`ESTOP_DISCREPANCY`), ARM_PERMIT element closed while commanded open (`PERMIT_STUCK_ON`, §4.1a), a chain node live behind a dead one (`CHAIN_IMPLAUSIBLE`), latch readback high while ARM_PERMIT has been low > 100 ms (`LATCH_STUCK`, also the result of a brake test whose latch does not drop), expander read path dead for 5 ms (`IOX_A`), ADC not converting for 5 ms (`ADC`), supervision task not seen by the control tick for 50 ms (`TIMING`). Left only by an MCU reset (power cycle or NRST). In `FAULT` the chassis keeps answering the protocol and keeps strobing the watchdog (ARM_PERMIT low already holds the chain open), so the host can read the cause; `TIMING`, `PERMIT_STUCK_ON`, `LATCH_STUCK`, `LATCH_NO_REARM` and `LATCH_NO_DROP` stop the strobe, and the watchdog then opens the chain at WDG_OK (upstream of K1 and of the ARM_PERMIT element) and, with JP1 closed, resets the MCU; a persistent hardware fault then shows again after each reset. `faults` lists the active flags.

Warnings that do **not** enter `FAULT` (also listed in `faults`): `PERMIT_STUCK_OFF`, `IOX_B`, `IOX_D`, `REARM_HELD`, `REARM_DISCREPANCY`, `LOOP_DISCREPANCY` (all withhold ARM_PERMIT while present), `CONFIG_DEFAULTED`, `LOOP_DISCREPANCY`, `J1_PRES_FAULT`, `CHARGER_COMM`, `PMON_COMM`, `TOF_BUS`, `HEATER_SENSOR`, `EFUSE_HEAD_PWR`, `EFUSE_HEAD_HTR`, `EFUSE_CHS_HTR`, `EFUSE_LIDAR`, `EFUSE_V5`, `BRIDGE_L`, `BRIDGE_R`, `BUS_CLAMP`, `BATTERY_WARN`, `LOOP_HIGH_R` (round 4 N6: head loop between the channel thresholds; `HEAD_LOOP_OPEN` holds the chain open), `SET_STAGE_FAULT` (stage 4 G1: SET_READY comparator stuck high; sticky until reset, arming withheld), `REARM_RB_FAULT` (stage-4 review S3: one REARM contact line missed a press that set the latch; sticky until reset, arming withheld), `COIL_HOT` (stage 5 H2: K1 coil estimate > 45 °C, the set margin is not guaranteed), `BATTERY_REARM_LOW` (stage 5 H5).

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
| `LOOK_FL`, `LOOK_FR` (grip cheeks, looking forward over the head) | `fwd` | Forward speed cap from the stop model, see below; stale → forward refused | Cap reaches zero while moving forward → `LOOKAHEAD_L` (`LOOK_FL`) / `LOOKAHEAD_R` (`LOOK_FR`). Stale while moving forward → `TOF_STALE` |
| `LOOK_RL`, `LOOK_RR` (tail, looking rearward) | `rev` | Reverse speed cap from the stop model; stale → reverse refused | Cap reaches zero while reversing → `LOOKAHEAD_L` (`LOOK_RL`) / `LOOKAHEAD_R` (`LOOK_RR`). Stale while reversing → `TOF_STALE` |
| `REAR_L`, `REAR_C`, `REAR_R` | `rev` | Range < `rear.stop_mm` (or invalid/stale) → reverse refused; below `rear.slow_mm` the reverse cap follows the stop model | Inside stop distance while reversing → `FIELD_REAR`; stale while reversing → `TOF_STALE` |

**Stop model** (contract): d(v) = v·t_delay + v²/(2·a_min) + m with `stop.t_delay_ms` = 150, `stop.a_min_mps2` = 0.40, `stop.margin_m` = 0.020. The largest speed that stops within an available distance D is v_cap(D) = −a·t + √(a²t² + 2a(D − m)) for D > m, else 0.

**Look-ahead (IB-34).** Two oblique sensors look forward from the grip cheeks over the head (`LOOK_FL`, `LOOK_FR`) and two look rearward from the tail (`LOOK_RL`, `LOOK_RR`); poses from `mechanical/common/frames.yaml` (`tof_look_fwd_left/right`, `tof_look_rev_left/right`). Each pair acts only on motion in its own direction: the forward pair caps and stops forward travel, the tail pair reverse travel; `LOOKAHEAD_L`/`LOOKAHEAD_R` name the robot-left (+y) / robot-right sensor of the pair in the direction of travel, so the host enum is unchanged. The pair that is not in the direction of travel never stops the robot but is evaluated every tick: a stale sensor refuses its direction (`allow`), an abnormal reading caps it, and both show in `DIAG.sw_active` and the `TOF` events.

Each sensor normally sees the level floor at its nominal range ± tolerance (`look.fwd_*` / `look.rev_*`). A longer, no-target or invalid reading means the floor ends (or cannot be seen) at most `ahead` beyond the leading rail (forward) or beyond the 0.290 m tail swept radius (rear); from the first abnormal sample the remaining distance is tracked with odometry (travel in the pair's direction): D = `ahead` − distance travelled since. A shorter reading means something stands in the field at D = `ahead` − (nominal − range)·`cos`. The cap of that direction is the minimum of the op_mode cap and v_cap(D) over its pair; it is released when both sensors read nominal again. When the cap reaches zero while moving that way the reason is latched.

| Pair | Nominal floor range | Tolerance | `ahead` | `cos` (x share of the range) | Spot separation / spot diameter |
|---|---:|---:|---:|---:|---|
| forward (x 0.0015, z 0.162, 18° down) | 524 mm | 60 mm (≈ ±2° pitch, 18 mm drop) | 0.285 m beyond the rail (x 0.2125) | 0.946 | 286 mm / ≈ 166 mm |
| rear (x −0.248, z 0.100, 22° down) | 267 mm | 40 mm (≈ ±3.5° pitch, 15 mm drop) | 0.201 m beyond the 0.290 m tail radius | 0.913 | 217 mm / ≈ 85 mm |

Values are computed from frames.yaml by `firmware/chassis/tools/look_geometry.py` (`check.sh` fails if the defaults drift). The tolerances are a firmware choice (calculated from the ray elevation, not measured). With these geometries the full 0.20 m/s forward cap survives a detection at the nominal distance (v_cap(0.285 m) = 0.40 m/s); a stop latches before the edge reaches the rail (simulated: 267 mm of 285 mm travelled at 0.20 m/s).

**No pair cross-comparison.** `TOF_DISAGREE` is not raised from the look pairs: the floor spots of the two partners are 286 mm (forward) / 217 mm (rear) apart against spot diameters of about 166 / 85 mm (18° full field), so their fields do not overlap and a real edge seen by one sensor only is legitimate. Each sensor is instead checked against its own expected range. `TOF_DISAGREE` remains for a blocked cliff window.

There is no automatic retreat and no degraded running: a stale or invalid sensor in the direction of travel always ends in a latched stop.

### 6.4 Odometry

`left_ticks`/`right_ticks` are the 16-bit hardware quadrature counters extended to signed 64 bits in the 1 kHz interrupt, 9600 counts per wheel revolution at the gearbox output, sign positive for forward rolling on both sides. Every 10th tick (100 Hz) the pair is latched together with the chassis clock read in the same interrupt (`odom.t_us`; jitter < 20 µs on target, exact in the emulator). The host integrates differences of cumulative ticks, so skipped polls lose nothing. Wheel radius and track live in the configuration (`cal.*`, nominal defaults 0.052 m and 0.270 m for the Rev E body) and are applied by the host for odometry and by the chassis for command conversion; neither side may use literals. The chassis firmware contains no dimension of the head or of the head mount: the look-ahead and cliff geometry is expressed relative to the sensors themselves through `look.*`, `cliff.*` and `rear.*` (the `look.*` defaults are derived offline from frames.yaml, including the leading-rail position and the 0.290 m tail swept radius, §6.3).

### 6.5 IMU and tilt

BMI088, gyro and accelerometer sampled at 1 kHz, rotated to body axes, averaged over each 10 ms window for `DRIVE`. Tilt = angle between the low-passed (τ = 0.5 s) acceleration vector and +z.

### 6.6 Chassis heater

Thermal policy (contract `power.thermal_policy`, DEC-045). With no host set-point the heater holds the pack at or above `heater.min_discharge_c` (−10 °C) on pack power and at `heater.precharge_c` (+5 °C) while an external supply is present (charging pre-heat: mode `SERVICE_CHARGE` or the charger reporting input power); a host set-point (−10…30 °C) can only raise that floor. Time-proportional output (2 s period) from a proportional band of `heater.band_c` below the set-point, limited to `heater.max_duty_pct`. Regulation input is the colder of the bay and pack NTCs. Still forced off below `batt.warn_v` on pack power. The hardware +5 °C cold-charge inhibit is unchanged and independent of this. Sensor fault (open/short/out of −45…+90 °C, or bay and pack NTC differing by more than `heater.disagree_c` for 60 s) forces the output off and raises `HEATER_SENSOR`. The firmware is not the over-temperature protection; an independent thermal cut-out is required in hardware.

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

`BLINK_SLOW` 1 Hz, `BLINK_FAST` 4 Hz, `BLINK_2` two flashes per 2 s. FAULT additionally blinks slowly in any mode while a warning flag is active. The REARM button lamp blinks when a press would have an effect (`rearm_ready`, or a clearable software latch/hold). After a refused press (`REARM_REFUSED`) it blinks fast (4 Hz) for 2 s. The HANDS-ON lamp is driven by hardware from the chain.

### 6.8 Stationary brake test

1. Preconditions: at rest, latch set, VMOT ≥ `brake.vmot_min_v`, both brake relays read "driving".
2. ARM_PERMIT low. Measure the time to latch readback low (limit `brake.latch_drop_max_ms`, 50), to both relay readbacks "braked" (same limit; the readback is valid because the bridges are asleep) and to VMOT < `brake.vmot_off_v` (1.0 V; limit `brake.vmot_decay_max_ms`, 3500). The ARM_PERMIT low phase also exercises the `CHAIN_END_RB` check (§4.1a).
3. With the latch down, command the bridges awake (the board's U9 gate keeps them asleep without RUN_12V) and apply `brake.probe_duty_pct` (10 %) to each side for 100 ms. Motor current must stay below `brake.probe_i_max_a` (0.1 A) and the wheels must not move (< 10 ticks): the bridges are isolated from the motors and from VMOT.
4. Bridges asleep, ARM_PERMIT high again, result logged as `BRAKE_TEST` event.

The test proves the switching elements, not the braking torque; the stopping distance under dynamic braking is established by the moving trial VT-003.

### 6.9 Watchdog

The external window watchdog is strobed only by the 100 Hz supervision task (WDI 5 ms high pulse every 10 ms, §4.6; the STM32 port also refreshes the MCU's own IWDG, ≈ 250 ms, with it), and only when, since its previous run, (a) the 1 kHz control tick ran 10 ± 2 times, (b) the control tick passed all of its program-flow checkpoints, (c) the control tick itself reports that the supervisor is on time, (d) the background loop (protocol, sensor buses) made progress within 500 ms, (e) no `TIMING` fault is latched. A stopped or runaway control loop, a stopped supervisor or a stalled background loop therefore stops the strobe, the watchdog opens `WDG_OK`, the latch drops and the MCU is reset (the reset path through NRST is a board decision).

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
| `CHAIN` | `el` (`MODE_RUN`, `ESTOP_A`, `ESTOP_B`, `HANDS_ON`, `CHG_COVER`, `CHG_PLUG_LINK`, `HEAD_DOCK`, `HEAD_LOOP_OK`, `HEAD_LOOP_SHORT`, `LAB_KEY_N`, `BODY_BUMPER_L`, `BODY_BUMPER_R`, `WDG_OK`, `BRAKE_L`, `BRAKE_R`), `closed` (bool) | Debounced transition of that readback while its element is known (§4.1a) |
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
| `REARM_REFUSED` **(+)** | `why` (reasons of `STATE.rearm_refusal`); `latch_dropped` (true for `REARM_HELD_AFTER_SET`); `action` (`CHARGE_OR_SWAP_PACK` for `SUPPLY_LOW`, `RELEASE_REARM_PRESS_BRIEFLY` for the held press) | A local REARM press with the latch down that did not set it within 300 ms (round 4 N1: never silent) |
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
| `drive.i_limit_a` | 2.5 | 0.5 | 2.6 | A | Per-motor current limit (fold-back below the 2.68 A hardware chop of the bridges, CCR-E03 b) |
| `drive.stall_ms` | 500 | 100 | 2000 | ms | |
| `drive.enc_fault_ms` | 100 | 20 | 500 | ms | |
| `drive.uncmd_ticks` | 600 | 50 | 5000 | ticks | ≈ 20 mm of uncommanded travel at the nominal radius |
| `drive.motor_r_ohm` | 2.18 | 0.5 | 10 | Ω | Motor model (encoder plausibility, feed-forward) |
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
| `look.fwd_nominal_mm` | 524 | 50 | 1000 | mm | Forward pair: range to the level floor (frames.yaml) |
| `look.fwd_tol_mm` | 60 | 10 | 200 | mm | |
| `look.fwd_ahead_m` | 0.285 | 0.03 | 0.60 | m | Floor point beyond the leading rail |
| `look.fwd_cos` | 0.946 | 0.3 | 1.0 | — | x share of the oblique range |
| `look.rev_nominal_mm` | 267 | 50 | 1000 | mm | Tail pair: range to the level floor |
| `look.rev_tol_mm` | 40 | 10 | 200 | mm | |
| `look.rev_ahead_m` | 0.201 | 0.03 | 0.60 | m | Floor point beyond the 0.290 m tail swept radius |
| `look.rev_cos` | 0.913 | 0.3 | 1.0 | — | |
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
| `heater.min_discharge_c` | −10 | −20 | 10 | °C | Thermal-policy floor on pack power (contract `bay_min_discharge_c`) |
| `heater.precharge_c` | 5 | 0 | 15 | °C | Floor with an external supply present (contract `bay_precharge_c`) |
| `chain.close_debounce_ms` | 50 | 5 | 500 | ms | |
| `chain.pres_settle_ms` | 20 | 5 | 500 | ms | |
| `brake.latch_drop_max_ms` | 50 | 5 | 500 | ms | |
| `brake.vmot_min_v` | 9.0 | 5 | 12 | V | |
| `brake.vmot_off_v` | 1.0 | 0.2 | 5 | V | |
| `brake.vmot_decay_max_ms` | 3500 | 50 | 6000 | ms | 1 kΩ bleed on 3 × 270 µF: nominal τ 0.83 s (≈ 2.1 s to 1 V from 13 V); with +20 % capacitance and 14.6 V ≈ 2.66 s (review m1) |
| `chain.backfeed_ms` | 0 | 0 | 20000 | ms | C_SET back-feed window (§4.6): 0 with the stage-3 diode D_RSET (current netlist), 12 000 for a stage-2 board |
| `rearm.vbat_warn_v` | 12.0 | 11.5 | 13.0 | V | `BATTERY_REARM_LOW` threshold (stage 5 H5) |
| `rearm.ntc_coil_offset_k` | 0 | 0 | 30 | K | Board NTC above the K1 coil (0 with RT1 at K1, stage 5 H2) |
| `rearm.coil_selfheat_k` | 10 | 0 | 30 | K | K1 coil self-heating at full latch-set duty (H2) |
| `loop.b_stuck_ohm` | 2050 | 1900 | 3500 | Ω | Head loop (§4.6 round 4, N6): above this analog reading a closed channel B is stuck healthy (`LOOP_FAIL`); below it, A open / B closed is `LOOP_HIGH_R`. 2050 for the stage-4 channel B (1.89 kΩ, G7, current netlist), 2900 for a stage-3 board (2.70 kΩ) |
| `brake.probe_duty_pct` | 10 | 2 | 30 | % | |
| `brake.probe_i_max_a` | 0.1 | 0.02 | 1.0 | A | |

---

## 9. Host obligations (summary)

**After any hardware inhibit, FAULT or MCU reset the host must not resume motion by itself.** When the mode returns from `HW_INHIBIT`/`STANDBY`/`FAULT` to `ARMED_IDLE`, the host treats the previous mission segment as aborted: it does not re-send the interrupted `DRIVE` stream, it waits for an explicit operator decision in the host UI (in addition to the local REARM that set the latch), and it re-plans from the current pose. A stop caused by a contact element (bumper, head rail, HANDS-ON) is a person or object at the robot; resuming automatically drives into it again (review C1).

| Condition | Needs |
|---|---|
| Hardware inhibit (`HW_INHIBIT`, any `hw_inhibit_reasons`) | Cause removed, then the **local REARM** button (no network op can set the latch), pressed after `rearm_ready` is true: a press before the chain reads closed or before C_SET is charged is refused and reported (`REARM_REFUSED`, `STATE.rearm_refusal`, §4.6); show the reason to the operator. A refusal never needs a power cycle |
| Software protective stop / hold | `REARM_SW` with the current nonce, or the local REARM button, causes clear |
| `FAULT` with `K1_WELD`, `RUN_SHORT`, `LOOP_SW_SHORT`, `ESTOP_DISCREPANCY`, `LATCH_STUCK`, `LATCH_NO_REARM`, `LATCH_NO_DROP`, `LOOP_FAIL`, `PERMIT_STUCK_ON`, `CHAIN_IMPLAUSIBLE`, `PIN_CONFIG`, `IOX_A`, `ADC`, `TIMING` | A **power cycle** (or NRST) and an inspection of the chain hardware before use; for the latch, loop and permit flags do not return to service until the hardware fault is found (review C1/C2). With JP1 closed the five strobe-stopping flags reset the MCU repeatedly; the host sees new `boot_id`s and `BOOT` events with `prev_mode` `FAULT` |
| `REARM_HELD`, `REARM_DISCREPANCY`, `LOOP_DISCREPANCY`, `LOOP_HIGH_R`, `PERMIT_STUCK_OFF`, `IOX_B`, `IOX_D`, `SET_STAGE_FAULT`, `REARM_RB_FAULT` (these two need a reset after the set stage / readback is repaired), `COIL_HOT`, `BATTERY_REARM_LOW` (charge or swap the pack) | Local action: release the button / fix the loop, REARM wiring or bus; they clear when the condition goes |

The fault flag word is 64 bits internally; `faults` is a list of names and may contain names a host does not know yet (hosts tolerate unknown names).


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
- Contract 0.4.0-draft7 adds `LATCH_UNEXPLAINED` (hw) and `STOP_ESCALATED` (sw); this revision uses both (a latch drop no readback explains; the permit withdrawal of the stop escalation and of the latched head-loop rule).
- Stage 4 (`electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md` §4.1 G1–G12) is in the netlist and adopted (§4.6); G1's coil limit (+45 °C) is applied to the board NTC, not to a coil temperature (there is no coil sensor).
- The boot-time watchdog self-test of `chassis_safety_chain.md` §7 step 2 (withhold the strobe, expect WDG_OK to fall) is not implemented: with JP1 closed it resets the MCU and needs a persistent test record and a verified boot timing (the port does not yet guarantee the first WDI edge within 23 ms of reset release on every boot path).
