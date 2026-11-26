# Contract change requests from the head firmware lead

To the integration lead (`interface/system/contract.yaml`, `docs/architecture/`). None of these
blocks the firmware; each records where the firmware had to decide something the contract leaves
open. Status: open until answered.

| # | Section | Request | What the firmware does today |
|---|---|---|---|
| CR-H1 | `head_gate_record.per_lane_fields.flags` | Add two flags, `FLOOR_INVALID` and `REF_INVALID` (chain disabled or front end known unusable), or name another carrier for "this chain delivers no valid data". | `firmware/head/hal/rrh_hal.h` defines them as extension bits 0x10/0x20; they map to `FLOOR_FAULT`/`REFERENCE_FAULT` + null. |
| CR-H2 | `head_gate_record.acq_mapping` | Freeze the lane-flag → ACQ mapping table (addendum 0.4 §2): in particular `BASELINE_SHIFT` → `DISCRIMINATOR_FAULT` with all three channels null, lane `BIAS_OUT_OF_RANGE` → `FLOOR_FAULT` + `REFERENCE_FAULT`, live fraction < 50 % → `SATURATED`. | Implemented as listed; the 50 % limit is `RRH_MIN_LIVE_PERCENT`. |
| CR-H3 | `head_event_capture.gates` | Reword "timer compare interrupt at the gate boundary" to allow the snapshot to be taken by the service interrupt that follows the boundary, with arithmetic splitting at the exact boundary tick. | Done that way (≤ 10 µs after the boundary, result identical, tested). |
| CR-H4 | `head_event_capture.mcu` | State the tick: TIM2/TIM5 at 144 MHz (SYSCLK), 144 ticks/µs; and that a chain whose comparator is high while its latch is clear is treated as saturated. Record the measured dead time (≈ 9.7 µs/event, simulated) in place of "10-20 us". | Implemented; emulator default dead time 10 µs. |
| CR-H5 | `timing` | Add the holdover rule (200 ppm growth, UNSYNCED 60 s after expiry) or the values the host wants instead; they are compile-time constants in `rrh_config.h`. | As in addendum 0.4 §2. |
| CR-H6 | `boards.RR-HEAD-ACQ` / pin map | Electronics to confirm `firmware/head/pinmap.yaml` (LQFP100): CLR active-low with pull-downs (latches held clear in reset), LLD comparator outputs routed to the MCU, LATCH_TEST OR-ed into every latch clock, no SWO. A per-channel front-end/bias monitor does not exist in rev A, so lane-level `BIAS_OUT_OF_RANGE` cannot be produced. | Pins assigned; frontend_fault is always 0 on the target. |
| CR-H8 | `head_gate_record` | Record the optional engineering extension added on the owner's request: per-chain pulse-width (time over threshold) histogram, 4 bins, with `width_mask` saying which chains provide it; and in `head_event_capture` that the raw LLD comparator outputs are on TIM4 (floor) / TIM3 (reference) capture channels. | Implemented in `rrh_hal.h`, `rrh_evtcap.c`, DIAG (addendum 0.4 §3); absent data = absent fields. |
| CR-H7 | head ICD (baseline, not editable) | The baseline ICD does not name the DISARM body field; addendum 0.4 uses `last_seq` + `complete`. Host driver to confirm. | Implemented. |
