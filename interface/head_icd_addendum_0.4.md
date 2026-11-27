# Head ICD addendum 0.4

Owner: head firmware lead. Applies to `interface/head_icd.md` (system design 0.3, command envelope
2.0, acquisition format 2.0), which stays normative and unchanged. This addendum **adds** ops and
**pins down** behaviour the ICD leaves open; it changes no existing op, field, status or schema.
A 2.0 host that ignores this document interoperates with a 0.4 head, and a 0.4 host interoperates
with a head that lacks the additions (it answers `UNSUPPORTED`).

Firmware 0.5.0 adds board functions (IB-17), afterglow hold and idle-latch clearing (IB-18) and rev A rail-zone
"not available" reporting (IB-21 closed for rev A); all additions are additive DIAG/STATUS/ENG members, ACQ 2.0 is unchanged.
Evidence classes: `tool-checked` = exercised by `firmware/head/check.sh` on the emulator
(`rr_head_sim`, the firmware core compiled for Linux) with the unmodified baseline tools;
`simulated` = host model; `calculated`. Nothing is physically measured.

## 1. Connectors and electrical references

Pin numbering of J1 (M16 8-pole) and J2 (M12 A-coded 8-pole), which ICD §3 left open, is frozen in
`interface/system/contract.yaml › connectors` (DEC-025). The head firmware relies on: RS-485 pair
on J2 pins 1/2 (DP positive in the idle/mark state), bus-side 5 V on J2 3/4, 120 Ω termination at
both ends, fail-safe bias at the chassis end only; J2 5/6 reserved for a hardware time pulse (not
used by firmware 0.4). MCU-side pin allocation: `firmware/head/pinmap.yaml`.

Link timing implemented by the head (target values, calculated; emulator does not model them):
driver enabled 5 µs before the start bit and released 5 µs after the last stop bit; the head never
starts a reply earlier than 200 µs after the end of the request's LF; a partially received record
is dropped after 5 ms of line idle time.

## 2. Behaviour pinned down for protocol 2.0

All items are `tool-checked` unless noted.

| Topic | Head behaviour |
|---|---|
| Records the head cannot answer | Bad framing/CRC, invalid JSON, duplicate keys, nesting > 6, a string > 256 bytes, more than 96 JSON tokens, `type` ≠ `REQ`, or an `id` that is not an integer 0 … 2³²−1: discarded silently. |
| Wrong `v` with a usable `id` | `UNSUPPORTED` (this is how 1.x endpoints are rejected). Missing/ill-typed `op` or `args`: `BAD_ARG`. Unknown `op`: `UNSUPPORTED`. |
| Error bodies | `{}` or `{"reason": "<short code>"}` (informative only). `GAP` always carries `oldest_seq` and `newest_seq`. `UNBOUND`, `EMPTY` and `WRONG_BOOT` bodies are `{}` except `UNBOUND` to a handshake op (`{"reason":"hello_required"}`). |
| Retry detection | A request is a retry when its `id` **and** its exact JSON bytes equal those of the last completed transaction; the stored reply bytes are sent again unchanged. A different request that reuses the id is executed. |
| `TIME` and the cache | `TIME` is never answered from the cache: every `TIME` request is timestamped afresh (it changes no state). Hosts should still use a new id per exchange. |
| `TIME` timestamps | `rx_us` = head clock when the request's LF was received; `tx_us` = head clock at which the head starts transmitting the reply. Target: the reply is scheduled 1000 µs after `rx_us` and released by a 100 kHz interrupt, so the true start is `tx_us` + 0 … 10 µs (calculated). The host must subtract the serialisation times (10 µs per byte) as ICD §6 says. |
| `HELLO` | From any state: aborts acquisition at once (the gate in progress is dropped), heater off, frames / sync records / sequence counter discarded, link → handshake. `boot_id` is constant for one MCU boot and new at every boot. |
| `GET_DESCRIPTOR`, `BIND` status order | ill-typed `boot_id` → `BAD_ARG`; other boot → `WRONG_BOOT`; no `HELLO` since boot or since the binding was invalidated → `UNBOUND`; `GET_DESCRIPTOR` while bound → `BUSY`; stale `descriptor_id` / `setup_id` / `descriptor_sha256`, bad `offset`/`count` → `BAD_ARG`. A repeated matching `BIND` on a bound link answers `{"bound":true}` and changes nothing. The final chunk may be shorter than `count`. |
| Descriptor bytes | Compact JSON plus one LF (1972 bytes for the Rev E concept head). `geometry_basis` is `CONCEPT`; geometry from `contract.yaml` (head_mount frame). |
| `setup_id` | `S1-` + first 16 hex digits of SHA-256 over thresholds (20), anode trims (8), pulser, chain enables, bias set-point / temperature coefficient / reference temperature, heater enable / set-point / duty limit, and the firmware version string. No bitstream (DEC-037). |
| Setup change | Only possible while disarmed (`ENG_SETUP_SET`, §4). The binding is invalidated **before** the new values reach the hardware: link → unbound, frames discarded, `TIME/SYNC/ARM/READ/DISARM/DIAG` answer `UNBOUND` until a new HELLO/GET_DESCRIPTOR/BIND; `boot_id` stays, `setup_id` and `descriptor_sha256` change. |
| `ARM` | `span_us` must lie in the descriptor's `gate_range_us`, else `BAD_ARG`. Matching repeat: same `first_seq`, acquisition untouched. Other span while armed, or the final gate of a DISARM still pending: `BUSY`. Capture hardware unavailable: `FAULT`. The first gate starts ≤ 2 ms after ARM. |
| `READ` | Returns the first retained frame with `sequence > after_seq`. `after_seq + 1 <` oldest retained → `GAP`; nothing newer → `EMPTY` (also when `after_seq` is ahead of the head). `after_seq` must be an integer −1 … 2⁵³−1. The head retains **160** frames (≥ 128 required). |
| `DISARM` | Body `{"last_seq": n \| null, "complete": bool}`. The gate in progress is completed; `last_seq` is its number and `complete` is false until that frame is retrievable (READ answers `EMPTY` meanwhile, at most one span). `null` if no gate was ever produced in this attachment. Heater off with the end of the final gate. A later `ARM` continues at `last_seq + 1`. |
| Lost gates | If the head itself loses gate records, the corresponding sequence numbers are skipped (the host sees a sequence and time gap inside the stream) and `ACQ_FAULT` is latched. |
| `SYNC` | `sync_id` must match the ACQ schema pattern, `bound_us` 0 … 10 000 000, `expiry_us` 1 … 3 600 000 000. The record takes effect at the receipt time of the request and applies to every gate that **starts** at or after it. `LOCKED` while `age_us ≤ expiry_us`; then `HOLDOVER` with `bound_us` grown by 200 ppm of the time past expiry; `UNSYNCED` (null fields) from 60 s past expiry, when the bound would exceed 10 s, and before the first SYNC of an attachment. The head keeps 32 records; if all are still referenced by retained frames a further SYNC answers `BUSY` (more than about one SYNC per five gates sustained). |
| Thermal fields | `head_c` = mean of the valid SiPM temperature sensors, one decimal; `null` + `HEAD_TEMP_OUT_OF_RANGE` if none is valid. The heater switches only on gate boundaries, so `duty_pct` is 0 or 100 per gate; `heater:"FAULT"` always comes with `duty_pct` 0 and `HEATER_FAULT` (true on-time is in DIAG). |
| Reset | Every reset (power, pin, watchdog, software) gives a new `boot_id`, clears binding, arming, frames, sync records and the reply cache, and restarts the head clock at 0. |

### ACQ mapping from `head_gate_record` (contract `acq_mapping`, `tool-checked`)

`live_us = floor(live_ticks × 10⁶ / tick_hz)`; alpha and beta_window share the floor chain's live
time; photon_ref has its own. A channel is `null`, with the segment flag shown, when:

| Condition | Channels nulled | Segment flag |
|---|---|---|
| `FLOOR_SATURATED`, or floor live fraction < 50 % | alpha, beta_window | `SATURATED` |
| `REF_SATURATED`, or reference live fraction < 50 % | photon_ref | `SATURATED` |
| live ticks = 0 or > gate ticks | that chain | `DEAD_TIME_UNKNOWN` |
| lane `BASELINE_SHIFT` | all three | `DISCRIMINATOR_FAULT` |
| lane `BIAS_OUT_OF_RANGE` (reported by the capture source) | all three | `FLOOR_FAULT`, `REFERENCE_FAULT` |
| anode current monitor (IMON_CH) of the floor chain out of window | alpha, beta_window | `FLOOR_FAULT` (lane DIAG flag `BIAS_OUT_OF_RANGE`) |
| anode current monitor of the reference chain out of window | photon_ref | `REFERENCE_FAULT` (lane DIAG flag `BIAS_OUT_OF_RANGE`) |
| chain disabled in the setup, or front-end fault of a chain | that chain | `FLOOR_FAULT` or `REFERENCE_FAULT` |

A measured zero stays `{"counts":0,"live_us":n}`. Global flags: `ACQ_FAULT` (latched: capture
fault, gate timing, lost gate, gate timeout, deliberate fault), `HEATER_FAULT` (latched: plate
sensor, cut-out, plate over-temperature, heater stuck on), `OVERTEMP` (latched: cut-out, plate
over-temperature), `BIAS_OUT_OF_RANGE` (latched over-current trip or `BIAS_PERMIT`, live tracking error
> 0.5 V, or any chain's anode monitor out of window), `HEAD_TEMP_OUT_OF_RANGE` and `UNDERVOLTAGE` (< 9.5 V) (live, per gate).

## 3. `DIAG` — engineering record per sequence (additive)

`{"op":"DIAG","args":{"seq": n}}`, bound only. Same retention as the frames: `OK`, `EMPTY`
(not produced yet), `GAP` with `oldest_seq`/`newest_seq` (expired, or that gate was lost),
`UNBOUND`, `BAD_ARG`. Body (`"type":"DIAG","diag":"1.0"`), no identity fields:

| Field | Meaning |
|---|---|
| `sequence`, `tick_hz`, `gate_start_tick`, `gate_ticks` | The gate on the capture-timer tick scale (144 MHz on RR-HEAD-ACQ). |
| `heater.on_us`, `heater.transition`, `heater.plate_c` | Heater on-time in the gate, **true if the heater state changed at the start of this gate** (the gate that contains the slew-limited edge), plate temperature (°C or null). |
| `bias.set_v`, `bias.v`, `bias.ua`, `bias.dac_writes` | Commanded and measured SiPM bias, total bias current, number of HV_SET DAC writes during the gate (temperature tracking while armed; mark for exclusion studies). |
| `temps.sipm_c[4]`, `temps.board_c` | Sensor temperatures, °C with 3 decimals or null. |
| `supply_v`, `bumper_zones` | Head supply; bumper zones (`FRONT`, `LEFT`, `RIGHT`) seen closed during the gate (identification only — the series interlock loop never reaches the MCU). **Rev A has no rail-zone identification (IB-21 closed): the value is `null` = not available, not an empty list = no zone actuated.** |
| `health` | Latched health codes at the end of the gate (§4 `FAULT_CLEAR`). |
| `lanes[4]` | `id`, `alpha_raw`, `beta_raw`, `floor_reject`, `floor_live_ticks`, `ref_raw`, `ref_reject`, `ref_live_ticks`, `alpha_short` (ALPHA latch set but time over threshold short or unmeasured: counted in `floor_reject`, not in alpha), `alpha_idle_clears` (ALPHA latches found set on the idle floor chain and cleared in this gate), `imon_na` (anode current of the floor and reference chain in nA, `null` = not measured; I = (V_trim - V)/4.99 k, 147 nA resolution), `flags` (`FLOOR_SATURATED`, `REF_SATURATED`, `BIAS_OUT_OF_RANGE`, `BASELINE_SHIFT`, `FLOOR_INVALID`, `REF_INVALID`). Raw counters are reported even where the ACQ frame is null. |
| `width_bins_ns[3]` (optional) | Upper edges, in ns, of bins 0 … 2 of the pulse-width histograms (default 150, 400, 2000); bin 3 is open-ended. Present only if the head measures pulse widths. |
| `lanes[n].floor_width_hist[4]`, `lanes[n].ref_width_hist[4]` (optional) | Number of classified events of that chain in the gate per bin of **time over threshold of the triggering low-threshold pulse** (raw comparator falling edge minus hardware-captured start). All classes together (floor: alpha + beta + reject); each count saturates at 65535; events whose width could not be measured are in no bin. Engineering pulse-shape handle only: classification is amplitude-based and does not use it. A field is absent for a chain without width capture. |

Hosts archive DIAG beside the raw frames; it never substitutes for a frame.

## 4. Other additive ops

| Op | When | Args → body |
|---|---|---|
| `STATUS` | any state | `{clear_bumper?: bool}` → `link` (`UNBOUND`/`HANDSHAKE`/`BOUND`), `armed`, `draining`, `uptime_us`, `reset_cause` (`POWER_ON`, `PIN`, `WATCHDOG`, `SOFTWARE`, `BROWNOUT`, `OTHER`), `span_us`, `next_seq`, `oldest_seq`, `newest_seq`, `buffer_frames`, `health[]`, `flags[]` (global ACQ flags as of now), `heater{enabled,on,plate_c,cutout_ok}`, `bias{on,set_v,v,ua}`, `temps{head_c,sipm_c[4],board_c}`, `supply_v`, `bumper{available, now[]|null, latched[]|null}` (`available` false on rev A: not available), `expander{present, hv_permit, hv_inhibit, lid_open, efuse_fault, hw_rev}` (optional TCA9534; every field but `present` is `null` when absent, so lid state is then unknown), `imon{scan, na[8], fault[]}` (chains F0..F3, R0..R3; `scan` is `RUNNING` or `PAUSED_ARMED`: per-chain supervision does not run while armed, `na` is then null and `fault` is the verdict of the last scan before ARM), `bias.out_v` (ramped command), `link_stats{requests,retries,discarded}`. No counts, no identity. |
| `FAULT_CLEAR` | any state | `{codes?: [..]}` (default all) → `{cleared[], health[]}`. Clears only latched codes whose cause is gone. Codes: `BIAS_PERMIT` (permit latch tripped with HV_EN high: lid open, over-voltage or +5V_A low; clearable only with the inhibit bus released when the expander is present; the next control period then raises HV_EN again, ramping from 0), `SOURCE`, `GATE_TIMING`, `RECORD_LOST`, `GATE_TIMEOUT`, `INJECTED`, `HEATER_SENSOR`, `HEATER_CUTOUT`, `HEATER_OVERTEMP`, `HEATER_STUCK`, `BIAS_TRIP`, `ENTROPY`, `STORAGE`, `WATCHDOG_RESET`. Latches never clear by themselves; the clearance procedure is the site's. |
| `ENG_FAULT` | any state | `{}` → `{health[]}`. Deliberately latches `INJECTED` (→ `ACQ_FAULT` in every following frame) to test the fault path end to end. |
| `ENG_SETUP_GET` | any state | `{}` → `{setup:{thresholds{beta_lld[4],beta_uld[4],alpha[4],ref_lld[4],ref_uld[4]}, trim{floor[4],ref[4]}, bias{ref_mv,tc_uv_per_c,t_ref_mc}, pulser{enable,code,channel,width_us,led_enable,led_code}, afterglow{alpha_hold_us}, heater{enable,setpoint_mc,max_duty_pct}, chain_enable}}` (DAC codes 0 … 4095). `bias.ref_mv` must lie in 20 000 … (fitted over-voltage trip - 1 V) = 30 500 on rev A. `afterglow.alpha_min_tot_ns` 0 … 5000 (default 250, part of `setup_id`): a floor event is alpha only if the ALPHA latch is set AND the raw-LLD time over threshold (6.94 ns resolution) is at least this; otherwise it is a floor reject, counted in DIAG `alpha_short` (never alpha, never beta window); 0 = no width condition. `afterglow.alpha_hold_us` 0 … 500 (default 300): after an alpha event the chain is held busy that long; counted as dead time in the live time (exact). `pulser.channel` 0 … 7 = F0 … F3, R0 … R3; `width_us` 1 … 100. |
| `ENG_SETUP_SET` | not armed | Any subset of the `setup` members, plus `persist?: bool` → `{changed, bound, persisted}`. `BUSY` while armed, `BAD_ARG` on unknown members or out-of-range / inconsistent values, `UNSUPPORTED` on a head with a fixed descriptor. A change invalidates the binding (§2). |
| `ENG_WAVE_ARM` | not armed | `{channel 0-7, samples 16-4096, pretrigger, slow_path?, trigger? 0\|1}` → `{}`; arms one monitor waveform capture. `FAULT` where the port has no capture (RR-HEAD-ACQ firmware 0.4). |
| `ENG_WAVE_READ` | any state | `{offset, count ≤ 384}` → `{samples, period_ns, trigger_index, offset, count, format:"u16le", bytes_b64}`; `EMPTY` while waiting for the trigger. |

Threshold scans are a host procedure: `ENG_SETUP_SET` per step, new handshake, ARM, READ. Every
step has its own `setup_id`, so scan data cannot be mistaken for survey data. Survey methods
(ratemeter search, scaler counts, step-and-count) are host-side; the head only reports gates.

### Bias sequence and limits (CCR-HE-09, IB-18c)

HV_SET is 0 when HV_EN rises, then ramps at 12.5 V per 100 ms (5 V/s at the DAC output); set-point law
HV_BUS = 25 x V(HV_SET), 62.5 V full scale, 15.26 mV per step; BIAS_VMON read-back 1:25.2233; total current monitor
8.0 mV/uA with a trip at 200 uA. Over-voltage trip as fitted on rev A: 31.55 V (calculated from R2217/R2218/R2219,
R2222/R2223 and the 3.0 V reference of `circuit.py`; the budget quotes 31.5 V) - tool-checked against the circuit, not measured.
BIAS_VMON uses 1 % divider resistors: +-1 % before calibration.

### Heater transition marker

ACQ 2.0 has no member for it. It travels in DIAG `heater.transition` (per retained gate). The same information is in every ACQ
frame: the heater switches only on gate boundaries, so `thermal.heater` is `ON` or `OFF` with `duty_pct` 100 or 0 for the whole
gate, and the transition gate is the first gate whose state differs from the previous frame (tool-checked against the DIAG marker).
After a sequence gap treat the next gate as marked.

## 5. Descriptor additions

No new descriptor fields. `capabilities` gains the strings `diag`, `status`, `fault_clear`,
`eng_setup`, `eng_wave` next to the baseline `raw_counts`, `per_channel_live_time`,
`head_temperature`, `heater_status`. The baseline schema `head_descriptor.schema.json` accepts
them unchanged.

## 6. Sizes and bus load at 1 Mbaud

Measured on the emulator (firmware 0.5.0: DIAG grew by `alpha_idle_clears` and `imon_na`) with `firmware/head/tests/test_sim_interop.py` (`tool-checked`; sizes are
complete wire records including TAB, CRC and LF; rates 0.5 – 4 / 80 / 60 s⁻¹ alpha / beta / ref):

| Record | Bytes | Time on the wire |
|---|---:|---:|
| `READ` request (6-digit id and sequence) | 86 | 0.86 ms |
| ACQ reply, typical | 859 – 867 (mean 864) | 8.6 ms |
| ACQ reply, worst case (all fields at schema maximum, 96-char sync id, all flags) — calculated | 1576 | 15.8 ms |
| `EMPTY` reply | 73 | 0.73 ms |
| `DIAG` reply, typical (with the width histograms) | 1404 | 14.0 ms |
| `TIME` request / reply | 68 / 107 | 0.68 / 1.07 ms |
| `SYNC` request / reply | 126 / 73 | 1.26 / 0.73 ms |
| Descriptor transfer (1972 bytes in 3 chunks of ≤ 768; requests + replies ≈ 3.7 kB, calculated) | 1972 payload | ≈ 37 ms in total |

Bus load for the default 100 ms gate (calculated from the sizes above, 10 µs per byte):

| Traffic per gate | Load |
|---|---:|
| one `READ` + ACQ reply | 9.5 % |
| + one `EMPTY` poll per gate | 11.1 % |
| + `TIME` and `SYNC` every 2 s | 11.3 % |
| + `DIAG` for every gate | 26.2 % (calculated from 1404 bytes; 24.4 % in 0.4) |
| + one retried `READ` (request and ACQ reply sent twice) in the same gate | 33.9 % |

A 50 Hz host poll loop measured 15.9 % on the emulator in real-clock mode (12 gates, 68
transactions, 19 447 bytes in 1.22 s; no DIAG). All figures leave the ICD's < 50 % target with
margin for one retry. The largest reply the head can produce is below 2 kB; the head's transmit
buffer is 4096 bytes and a reply that would not fit is replaced by `FAULT`.

## 7. Emulator

`rr_head_sim` (TCP byte stream, UDP stimulus/fault socket, options, physics model) is documented
in `firmware/head/README.md`. Its TIME timestamps reflect the host's scheduler, not RS-485
timing; do not use them to characterise the link.
