# 04 Fault isolation

**Status.** Nothing has been built, so no fault has ever been observed. Every "likely cause" below is a deduction from the design documents (circuit descriptions, the single-fault table, the ICDs, the firmware READMEs, the ROS workspace); it is a place to look first, not a diagnosis from experience. Reason codes are quoted from `interface/chassis_icd.md`, `interface/head_icd.md` and its addendum, and the code in `ros2_ws/`. Evidence classes as in `docs/build/README.md`. Always stop and inhibit the robot (E-stop or HANDS-ON, verify traction stopped) before touching anything near the wheels or head. This is not a certified safety system; do not bypass a chain element to make a fault go away.

**Updated 2026-11-28** for the traction-inhibit reviews and the stage-5 firmware (fatal and non-fatal flags, REARM refusals, latent faults), head stage 3 and firmware 0.6.0, MODEL.md revision 5 statuses and the thermal policy. Likely causes remain deductions from the design documents; nothing has been observed on a robot.

How to read the state: the operator page shows chassis `mode`, `hw_inhibit_reasons`, `protective_stop_reasons`, `faults`; the panel shows the pattern (see 01 section 3); `DIAG` and `EVENTS` over the link carry the details. The chassis event log latches every chain-element transition, presence change, button press, mode change, brown-out and reset cause independently of polling (`chassis_icd.md` section 7).

## 1. Power

| Symptom | Checks | Likely cause |
|---|---|---|
| Nothing lights, selector in RUN | pack seated and latched (cassette plunger engaged), coupler mated, main fuse (20 A class, not yet selected), selector position, pack voltage at the coupler | pack not home; fuse open; the pack switch (LM74502 + MOSFETs) is off because VBAT_SW is below UVLO (9.0 V) or above OV (16.5 V) or the selector's second contact holds enable low |
| Resets at start or under load; boot banner repeats with a new `boot_id`; `BROWNOUT` event | log VBAT at the reset; `reset=` cause in the banner; `BROWNOUT` event with `vbat_v` | pack sag below 9.5 V (cold pack, high resistance contact, SBS50 coupler, fuse); watchdog window or supply; in the cold check pack deliverable capacity (VT-040) |
| `BATTERY_LOW` protective stop | VBAT, SoC (null until the charger driver exists) | VBAT below 11.2 V for 5 s; cold pack; reserve exhausted; threshold `batt.stop_v` |
| `VMOT_FAULT` hardware reason | readbacks VMOT_SENSE, HW_LATCH_RB, BRAKE_x_RB; latch set but VMOT below `brake.vmot_min_v` (9.0 V) for over 100 ms; or latch dropped but VMOT still present after the decay time; or brake-relay readback inconsistent with the latch for over 200 ms | VMOT eFuse (6.5 A class) tripped or stuck (fault rows 50, 51, 54); bridge fault; brake relay stuck; wiring. The firmware withholds ARM_PERMIT while it persists |
| `EFUSE_HEAD_PWR`, `EFUSE_HEAD_HTR`, `EFUSE_CHS_HTR`, `EFUSE_LIDAR`, `EFUSE_V5` warning; branch off | branch current (INA3221 channel, drivers never run on hardware), short on the branch, harness chafe; `HEAD_POWER` request retries | a branch limit exceeded: HEAD_PWR 1.5 A (the head's own eFuse trips at 1.0 A first), HEAD_HTR 3.96 A nominal (band 3.56 to 4.35 A), CHS_HTR 3.04 A, LiDAR 1.5 A, V5 5 A, BUS_5V 0.15 A (up to 0.20 A) per contract draft7 and `chassis_design_review_checklist.md` (IB-28) |
| CM5 does not boot; no host link | V5 rail at the carrier (at least 4.85 V at 5 A expected), `V5_PGOOD`, `EFUSE_V5`; USB to the CDC device | 5 V buck or its eFuse; J_CM5 contacts (AWG 20 on Micro-Fit, 80 mV drop at 5 A calculated); the CM5 back-feeding through the 40-pin header is unresolved (OI-14) |
| `BUS_CLAMP` warning; VMOT near 15.6 V after a stop | `BUS_CLAMP_ACTIVE` | regeneration into a pack that refuses charge (BMS open, cold): the hardware clamp (on at 15.6 V, off at 15.0 V) is holding the bus; check the pack and BMS |
| Charger does not start | cover shut and plug link; pack-surface NTC temperature; inlet voltage 24 V; `CHARGER_COMM` is always raised until the LTC4162-F driver exists (IB-05, IB-06) | pack below +5 C (hardware gate, about +5.3 C with 2 K hysteresis); BMS refusing below 0 C; BMS under-voltage latch the charger cannot wake; cover switch |
| Heater branch dead, `HEATER_SENSOR` | bay NTC and pack NTC readings differ by more than 15 C for 60 s, or an open or short NTC (out of -45 to +90 C) | the firmware forced the heater off on a sensor fault; the independent bimetal cut-out may also have opened |
| `BATTERY_REARM_LOW` warning | resting pack voltage (at or below 12.0 V for 10 s, 0.2 V hysteresis) | the pack can no longer be relied on to re-arm (needs about 11.7 V at the pack, calculated) while the battery-low stop is at 11.2 V: change or charge the pack before the next stop |
| `COIL_HOT` warning, or a press refused `COIL_HOT` | board temperature (thermistor next to K1 on the stage-5 board), time armed, ambient | the K1 set margin is guaranteed only to a coil temperature of +45 C (estimate: board NTC plus 10 K self-heating, tau 300 s); armed for long in a warm trailer or driven hard; let it cool |
| REARM press refused with `SUPPLY_LOW` | VBAT at rest | pack under about 11.7 V: charge or swap |
| Pack will not charge after standing in the cold | pack-surface temperature | below +5 C the charge gate is closed (hardware, about +5.3 C with 2 K hysteresis); pre-heat on external power takes 95 to 200 min from a -25 C soak with the pad on the pack skin (calculated; coupling 0.6 W/K assumed); the bay is not heated above its -10 C hold on pack power (thermal policy) |

## 2. Traction chain and inhibits

Chain elements in order (contract `safety_chain`): MODE_RUN, ESTOP (two poles), HANDS_ON, CHG_COVER, HEAD_DOCK, HEAD_LOOP, LAB_KEY_N, BODY_BUMPER, WDG_OK, ARM_PERMIT. The hardware latch is set only by the local REARM button with every element healthy and ARM_PERMIT high; nothing remote sets it. Latched hardware reasons stay reported until the latch is set again, so a brief unplug or tap stays visible.

| `hw_inhibit_reason` | Meaning (`chassis_icd.md` section 4.4) | Checks | Likely cause |
|---|---|---|---|
| `MODE_NOT_RUN` | selector not in RUN | selector | selector in OFF or SERVICE; contact block fault |
| `ESTOP` | either pole open | release the mushroom (turn); `ESTOP_A_RB` and `ESTOP_B_RB` | pressed; one pole's wire broken. A discrepancy lasting over 200 ms enters `FAULT` (`ESTOP_DISCREPANCY`), cleared only by an MCU reset |
| `HANDS_ON` | maintained button engaged | button lamp (driven from the real chain state) | button latched on; contact fault |
| `CHARGER` | cover open or charge-plug link present | cover, plug, inlet | cover not closed; plug connected (also forces Charge/Service) |
| `HEAD_UNDOCKED` | dock switch open | head seated to the x-stop; draw latch closed; dock switch actuated by the push pin in the left channel (clicks in the last 1.5 mm of gauge travel) | head not fully seated; latch open; switch or bracket misaligned |
| `HEAD_LOOP_OPEN` | loop above the 0.6 to 1.6 kohm window with J1 present | press state of the three head rail switches (front, left, right); measure J1 pins 5 and 6 (1.00 kohm expected) | a rail zone is pressed or stuck (debris, bent insert, the front rail not returned); a loop wire open; J1 not fully mated |
| `HEAD_LOOP_SHORT` | loop below the window | resistance of J1 5/6 below 0.6 kohm | wiring short in the head or pigtail; a bypass |
| `J1_ABSENT` | no head presence on J1 pin 7 | J1 mated; 4.70 kohm pin 7 to pin 2 | J1 unplugged or broken; presence resistor |
| `LAB_KEY` | the LAB resistor (1.50 kohm) is present, or hardware `LAB_KEY_N` is open | whether the LAB extension is fitted | extension fitted: traction is inhibited by design |
| `BODY_BUMPER` | either body bumper switch open | bumper segments, D2HW switches, wiring | segment pressed or sticking; switch failed |
| `WATCHDOG` | external watchdog not OK | strobe on `WDG_STROBE` (one edge every 10 ms) | firmware stalled or halted in a debugger; supervision task or background loop did not make progress; `TIMING` fault |
| `MCU_NOT_READY` | firmware withholds ARM_PERMIT | `faults`, `mode` | boot, a fault, Charge/Service or LAB, stop escalation, brake test in progress, presence `FAULT`, `VMOT_FAULT` active |

Faults that enter `FAULT` mode (left only by an MCU reset): `ESTOP_DISCREPANCY`, `LATCH_STUCK` (latch readback high with ARM_PERMIT low: wiring or relay, **stop**), `IOX_A` (SPI expander or its sentinel wiring), `ADC`, `TIMING`, `PERMIT_STUCK_ON` (CHAIN_END live with ARM_PERMIT low: the firmware stops strobing the watchdog), `CHAIN_IMPLAUSIBLE` (a chain node live behind a dead one: a readback tap or harness short). `IOX_B` / `PERMIT_STUCK_OFF` means CHAIN_END_RB cannot be read or reads low with every element closed: no arming possible (`firmware/chassis/README.md`).

Warnings (not `FAULT`): `CONFIG_DEFAULTED`, `LOOP_DISCREPANCY` (comparator and analog decode disagree for 200 ms), `J1_PRES_FAULT`, `CHARGER_COMM` (always, until the charger driver exists), `PMON_COMM` (the INA228 or its identity check failed), `TOF_BUS`, `HEATER_SENSOR`, `EFUSE_*`, `BRIDGE_L`, `BRIDGE_R`, `BUS_CLAMP`, `BATTERY_WARN`.

**New flags since the reviews** (`interface/chassis_icd.md` sections 4.6 and 9; `firmware/chassis/README.md`):

- **Fatal, `FAULT`: power cycle and inspect the chain hardware before use** (do not return the robot to service until the hardware fault is found): `K1_WELD` (K1 operated or welded: `LATCH_NC_RB` low or `LATCH_RUN_RB` high with ARM_PERMIT low), `RUN_SHORT` (RUN_12V or RUN_HD fed from something other than the latch), `LOOP_SW_SHORT` (a shorted loop photo-MOS), `LOOP_FAIL` (a loop channel provably stuck healthy, or the self-test failed; `DIAG.loop_cause`: `A_STUCK_HEALTHY`, `B_STUCK_HEALTHY`, `TEST_PATH_A`, `SELF_TEST_A`, `SELF_TEST_B`, `A_ANALOG_DISAGREE`), `LATCH_NO_REARM` (a latch rise with no qualified REARM press, or at boot), `LATCH_NO_DROP` (an element open while the latch stays set 30 ms), `LATCH_STUCK`, `PERMIT_STUCK_ON`, `CHAIN_IMPLAUSIBLE`, `PIN_CONFIG`, `IOX_A`, `IOX_D`, `ADC`, `TIMING`, `ESTOP_DISCREPANCY`. With JP1 closed the strobe-stopping flags reset the MCU repeatedly; JP1 stays open until the first-strobe timing is measured (VT-055).
- **Non-fatal, local action**: `REARM_HELD` (hardware reason; release the button), `REARM_DISCREPANCY` (the two REARM contact lines disagree for 200 ms: W-018 wiring), `LOOP_DISCREPANCY` (arming withheld until the channels agree), `LOOP_HIGH_R` (loop between the two channel thresholds: 1.65 kohm to `loop.b_stuck_ohm`, 2050 ohm), `PERMIT_STUCK_OFF`, `IOX_B`, `SET_STAGE_FAULT` (SET_READY high while CHAIN_END was dead over 1 s: comparator stuck; reset after repair), `REARM_RB_FAULT` (one REARM contact line missed on an accepted press: the latch is kept and every later arming is withheld until reset; `DIAG.rearm.rb_fault` = `SET_LINE_MISSED` or `AUX_LINE_MISSED`), `COIL_HOT`, `BATTERY_REARM_LOW`.
- **REARM refusals** (`STATE.rearm_refusal`; never a fault): `NOT_READY`, `SUPPLY_LOW`, `COIL_HOT`, `CHAIN_OPEN`, `REARM_HELD`, `PERMIT_WITHHELD`, `LOOP_TEST`, `FAULT_OR_MODE`, `TOO_SHORT`, `PARTIAL`, `SET_FAILED`; the operator actions are in [01_operator_procedures.md](01_operator_procedures.md) section 4.

| Symptom | Checks | Likely cause |
|---|---|---|
| Press accepted by the hardware but the robot does not arm | refusal reason; `PARTIAL`; `REARM_RB_FAULT`; K1 and U_HOLD operate; C_SET at the press | a partial set (press of 3 to 15 ms; K1 sealed by its own contact without U_HOLD); a weak set stage (service test S3 steps a to e, h); coil too hot |
| Refused with `NOT_READY` although the lamp blinks | `SET_READY_RB`, C_SET (service pad SVC10, 10.6 to 11.0 V at ready) | pressed before the lamp was steady; supply low; C_SET leaking |
| Latch drops 5 s after arming with `REARM_HELD` | whether the REARM contact is still closed | button held or stuck; W-018 crush (both contact lines closed) |
| Brake relays do not release after a drop; no dynamic braking | RUN_HD voltage after the drop, `BRAKE_x_RB` | D_RUN reverse leakage hot keeping U_LS lit (VT-081); latent shorted D_RUN or RELAY_RTN; service tests S5a, S5b |
| Robot keeps moving with a rail zone or a bumper pressed | which element; P1.3 | a welded rail switch, head-internal bypass, welded bumper switch or a LOOP_SNS leak: **no hardware barrier for that zone** (`chassis_safety_chain.md` section 6.1); stop it with the E-stop or selector OFF and report |

| Symptom | Checks | Likely cause |
|---|---|---|
| Robot will not arm after clearing everything | `rearm_ready`, REARM lamp blinking; `STATE.chain` (false now means open or unknown; `DIAG.chain_state` distinguishes); 5 s lock-out after a brake test; the REARM button held over 2 s is refused | a latched hardware reason remains (the latch has to be set again); an element is open behind another one (readbacks are node voltages: an element behind an open one is reported unknown); `MCU_NOT_READY`; REARM contact held or welded (fault rows 42, 43) |
| Chain drops with no obvious cause | `EVENTS` list: `HW_LATCH`, `CHAIN`, `PERMIT`, `J1`, `J2`, `BUTTON`; latched reasons | intermittent connector (JST GH, CLIK-Mate, J1/J2 shell), bumper bounce, vibration on a rail switch; a brief unplug always leaves an event |
| `STOP_ESCALATED` (software reason) with a latched `MCU_NOT_READY` and a `PERMIT` event | `PERMIT` event cause | the permit was withdrawn after a wheel kept turning above the standstill threshold later than the ramp plus 300 ms, movement with no command, or the head-loop rule (an opening seen by a loop channel while latched): drive or encoder fault, or a real rail or loop opening (`LATCH_UNEXPLAINED` is a hardware reason for a drop no readback explains) |
| Brake test fails | `BRAKE_TEST` reply `fail` codes: `PRECOND_VMOT`, `PRECOND_RELAY`, `LATCH_NOT_DROPPED`, `RELAY_L`, `RELAY_R`, `VMOT_NOT_REMOVED`, `BRIDGE_CURRENT_L`, `BRIDGE_CURRENT_R`, `WHEEL_MOVED`; timings `latch_drop_ms`, `relay_ms`, `vmot_decay_ms` | `LATCH_NOT_DROPPED` also enters `FAULT` (K1 weld, wiring); `RELAY_x`: a brake relay NO contact welded (fault rows 44, 45); `VMOT_NOT_REMOVED`: VMOT eFuse or bleed; `BRIDGE_CURRENT_x`: the bridge is not isolated. The test proves switching elements only; an open brake-resistor path is not detectable at standstill (fault 46) |
| `BRAKE_TEST_REQUIRED` on a `DRIVE` | passed brake test since boot | no passed test since the last MCU boot |
| Robot stops and holds when nothing is wrong at the hardware; `HOST_LINK_LOST` | host polling at least every `link.timeout_ms` (1000 ms) while armed; USB configured and not suspended; a new `HELLO` while moving | host process stalled (the composed node is single-process; IB-46), USB, or arming with no host connected (becomes a protective stop after 1 s: expected) |
| `CMD_TIMEOUT` | the TTL of a non-zero `DRIVE` (at most 250 ms) ended without a newer accepted command | host cadence below 50 Hz or a stall; under host load on the emulators it was observed (IB-46) |
| `DRIVE` rejected: `reject_reason` | table in `chassis_icd.md` section 3.3: `NO_SESSION`, `SEQ`, `TTL`, the mode names (`BOOT`, `FAULT`, `SERVICE_CHARGE`, `LAB`, `STANDBY`, `HW_INHIBIT`, `PROTECTIVE_STOP`, `HOLD`), `OP_MODE`, `LIMIT`, `BRAKE_TEST_REQUIRED`, `DIR_INHIBITED` | the reason names the cause; `DIR_INHIBITED` means a protective field blocks that direction (see `allow`) |
| `PROTECTIVE_STOP` reasons | `protective_stop_reasons`; cause present or cleared | `CLIFF_FL/FR/RL/RR` (cliff sensor reads a drop for 3 samples, or invalid/stale while moving that way), `LOOKAHEAD_L/R` (the look-ahead speed cap reached zero), `FIELD_REAR`, `FIELD_FRONT/LEFT/RIGHT` and `HOST_REQUEST`, `HEAD_LINK`, `LOCALIZATION` (host-asserted; the MCU has no front or side ranging), `TOF_STALE` (a guarding sensor delivered nothing for 100 ms), `TOF_DISAGREE` (a cliff sensor below 8 mm: blocked window), `CMD_TIMEOUT`, `HOST_LINK_LOST`, `STALL` (wheel at current limit with under 10 % of set speed for 500 ms), `ENCODER_FAULT` (swapped phases, no counts, over 0.33 m/s, uncommanded motion), `IMU_FAULT`, `TILT`, `BATTERY_LOW`, `TEMP_RANGE`, `BRAKE_TEST_FAIL`. The set cannot clear by itself; `REARM_SW` with the current nonce and the cause gone, or the local button. `CAUSE_ACTIVE` reply = a cause is still present; `NONCE` = stale request |
| Look sensors: pair names | firmware, ICD and contract use LOOK_FL / LOOK_FR (forward, grip cheeks), LOOK_RL / LOOK_RR (rearward, tail) after DEC-043; J_TOF4 = FL, J_TOF5 = RL, J_TOF6 = RR, J_TOF7 = FR | the stop reasons keep the names `LOOKAHEAD_L` / `LOOKAHEAD_R`; **electronics text, net labels and the ICD section 6.3 table may still show LOOK_LO/LI/RI/RO** (IB-34): use the index and connector |
| On hardware every direction refused, all ToF OFFLINE | `STATE.tof` | VL53L4ED driver stub (IB-04); not a wiring fault |

## 3. Links

| Symptom | Checks | Likely cause |
|---|---|---|
| Head not found; no handshake | cable J2, BUS_5V on pins 3/4, isolation, the host RS-485 adapter, A/B polarity (DP/DN), 120 ohm termination at each end (about 60 ohm across the pair when both are present; about 40 ohm means a third termination) | wrong polarity; missing bus 5 V; the L60 common-mode choke winding pairing on the chassis board (a wrong pairing shorts A to B: IB-43); LAB extension adding a termination |
| Handshake works, `UNBOUND` on every op | `HELLO`, `GET_DESCRIPTOR` (compare descriptor SHA-256), `BIND` with the current `boot_id` | a head reset (every reset gives a new `boot_id` and clears the binding); a setup change; stale `descriptor_id`; `WRONG_BOOT` |
| `HEAD_IDENTITY:` in the arm refusal list; `block_reason` | the trusted head registry; descriptor schema; serial/calibration mismatch (`CALIBRATION_UNKNOWN`, `CALIBRATION_NOT_APPROVED`, `CALIBRATION_SETUP_MISMATCH`) | head not in the registry; descriptor corrupt or out of envelope; calibration not approved for field use (all shipped values are synthetic) |
| Gaps in the stream (`GAP` with `oldest_seq`/`newest_seq`) | buffer retains 160 frames; polling cadence | reads paused longer than 160 gates; link drops; the exact gap is archived and the floor flagged unresolved |
| CRC errors, retries | error counters during PWM and heater activity (see `docs/build/05_first_bench_tests.md` T11) | noise on the J2 pair; termination; shield bonding; a request is a retry only with an identical id and bytes |
| Clock: `HEAD_CLOCK` or `CHASSIS_CLOCK` in the arm refusal list; sync `HOLDOVER` / `UNSYNCED` | time bound against 10 ms (target 2 ms); sync refresh 2 s, expiry 10 s; head holdover grows 200 ppm, `UNSYNCED` 60 s after expiry | host load, USB adapter latency, link drops; the head TCXO absent (health code `SOURCE`, clock falls back to HSI16) |
| `CHASSIS_LINK` | USB enumeration (CDC-ACM), `HELLO` | USB cable/connector, MCU in FAULT/reset loop; both carrier USB-A ports are used (no wired service port: IB-07) |
| Operator page: commands disabled, last state shown | event stream down for over 5 s | Wi-Fi or server; the control lease ended; refresh; the page re-reads the full state on reconnect |
| `LOCAL_REARM_REQUIRED` | the latched condition is a hardware one | press REARM on the robot |
| Web page refuses motion `interlock_refusal` | Charge/Service or traction inhibited | charger connected, or a hardware reason is latched |

## 4. Head faults and lane flags

Global flags (`head_icd_addendum_0.4.md` section 2): `ACQ_FAULT` (latched: capture fault, gate timing, lost gate, gate timeout), `HEATER_FAULT` (latched: plate sensor, cut-out, plate over-temperature, heater stuck on), `OVERTEMP` (latched: cut-out or plate over-temperature), `BIAS_OUT_OF_RANGE` (latched over-current trip, or live tracking error above 0.5 V), `HEAD_TEMP_OUT_OF_RANGE` and `UNDERVOLTAGE` (supply under 9.5 V; live, per gate). A head reset gives a new `boot_id`, restarts the head clock at 0, and clears binding, arming, frames, sync records and the reply cache.

Lane flags in the ACQ frame and what is nulled:

| Condition | Channels nulled | Flag | Likely cause / check |
|---|---|---|---|
| floor chain saturated, or floor live fraction under 50 % | alpha and beta window | `SATURATED` | very high floor rate (source, photon field), chain held busy over 1 ms, afterglow, pickup (T5); a chain with its comparator high while the latch is clear is treated as saturated |
| reference chain saturated, or reference live under 50 % | photon reference | `SATURATED` | high photon field above the validity envelope; interference |
| live ticks 0 or more than the gate | that chain | `DEAD_TIME_UNKNOWN` | capture fault; lost gate |
| lane `BASELINE_SHIFT` | all three | `DISCRIMINATOR_FAULT` | baseline of a front end moved: temperature, bias, supply, pickup |
| lane `BIAS_OUT_OF_RANGE` | all three | `FLOOR_FAULT` and `REFERENCE_FAULT` | per-lane anode current above 200 uA or trim buffer at its rail (stage-2 firmware), a SiPM short or light leak; a dead channel is not detected (the anode monitor sees only over-current and an unheld anode: `firmware/head/README.md` Known gaps; IB-58) |
| chain disabled in the setup or front-end fault | that chain | `FLOOR_FAULT` / `REFERENCE_FAULT` | setup, or injected fault |
| `HEATER_FAULT`, `HEAD_TEMP_OUT_OF_RANGE` | affects thermal field | global | NTC open or short; independent cut-out tripped (`HTR_CUTOUT_OK` low); heater stuck on; carrier NTC missing |
| `heater: FAULT` always with duty 0 | | | true on-time is in DIAG |
| Zero counts reported as zero on a dead lane | | | not detected by hardware alone: firmware must use the monitors; check the pulser self-test and the dark rate |

A measured zero is `{"counts":0,"live_us":n}`; a null with a flag is an unusable channel. The host excludes a gate with a null channel, a lane flag, a sync bound above the limit or no qualified pose from cell sums and does not credit the floor area. Rail-zone identification is not available in rev A (IB-21): `bumper_zones` is null in DIAG, and the idle zone labels of the two side rails are swapped against the physical rails (IB-57); read the head loop at J1, not the zone labels.

**Head stage 3 and firmware 0.6.0 additions** (`firmware/head/README.md`; `interface/head_icd_addendum_0.4.md`):

| Symptom | Checks | Likely cause |
|---|---|---|
| `ARM` answers `FAULT` with reason `device_type_unset` or `placeholder_thresholds` | STATUS `device`, `thresholds_confirmed` | the SiPM device type has not been set and the thresholds written or confirmed (VT-077); set them (changes `setup_id`) |
| `FRAME_FAULT` (latched; heater forced off) | STATUS `frame{mv, fault}`, MON_ADC (0.300 V + V_FRAME/2) | frame potential up more than 30 mV from the value at arming or outside -60 to +60 mV: an open frame bond or blown F2801 (the frame floats to VBL, MON_ADC 0.6 V), a heater return-side contact with the spreader while the heater draws current (+70 to +90 mV); **it cannot see** a contact while the heater is off or a rise under 30 mV |
| `HEATER_OVERCURRENT` and `HEATER_FAULT` | HTR_SENSE (0.5 V/A; gain recalled), `heater.oc_ma` 3200 mA and `heater.oc_ms` 300 ms | heater current above 3.2 A for 300 ms (a partial short or a wrong supply); the Micro-Fit contact rating is UNVERIFIED (about 3.13 A) and between 3.13 and 3.56 A no hardware current protection acts (IB-69) |
| `BIAS_PERMIT` health code | HV_EN, the permit latch, BIAS_VMON | HV_EN high but the permit is low or BIAS_VMON below 1 V after the ramp |
| BIAS_VMON reads `UNCALIBRATED` | STATUS `bias.vmon` | the per-board ratio has not been written (`bias.vmon_ratio_e4`; it is not part of `setup_id`) |
| Per-lane `BIAS_OUT_OF_RANGE` | anode current above 200 uA or the trim buffer at its rail; the scan runs only disarmed, so supervision is paused while armed | SiPM short or light leak; a dead channel is not detected |
| SATURATED gate: which kind? | `GATESTAT` for the gate: `sc` bits (1 floor forced or blind, 2 floor live under 50 %, 4 reference forced or blind, 8 reference live under 50 %), forced clears `ff`/`rf`, live per mille | low live fraction **without** forced clears = rate too high to count (the host raises `ALARM - rate above counting range`); forced clears = a stuck comparator or a light leak (a detector fault: the gate is removed) |
| Missing gates (sequence numbers skip) | `ACQ_FAULT` in the next frame; STATUS `gates_lost`, `fault_events` | one lost record: `ACQ_FAULT` is per gate now and clears itself; a lost gate has no frame and its floor area is not credited; STATUS must be read at session open for `WATCHDOG_RESET`, `ENTROPY`, `STORAGE`, which reach no ACQ flag |
| `alpha_short` / `alpha_ambig` counts high | `GATESTAT` per gate | bright betas rejected by the time-over-threshold cut or a pile-up with no measurable width (never called alpha); a rate rise means pile-up or a changed cut; the rejected-event fraction must stay inside the calibrated range |
| Alpha-class events with Sr-90 alone | TOT histogram, cut | the cut is mid-gap only if it was set from Am-241 and Sr-90/Y-90 histograms (VT-050); the default per-device cut rests on an assumed 200 ns ZnS decay |

First-line checks for a head problem: lid closed and light tight (E1 repeated if anything was opened); bias and bias current (BIAS_VMON/IMON); head temperature and heater duty; thresholds (`setup_id` unchanged); pigtails and coax seated (U.FL); lane shield cans fitted; dark rate against the last record.

## 5. Localisation and coverage refusals (ROS workspace)

The arm and start refusal is `PREREQUISITES` with a `missing` list (`ros2_ws/src/rr_coverage/rr_coverage/supervisor.py`). The list can contain:

| Code | Meaning | Operator action |
|---|---|---|
| `RECORDER` | archive not writing or recorder error | free disk space, check the run directory |
| `HEAD_IDENTITY:<reason>` | head not armed/bound or identity or calibration blocked | check the head, registry, calibration approval |
| `HEAD_CLOCK` | head clock bound above the limit (10 ms) | wait for sync; check the link |
| `CHASSIS_LINK` | chassis link not UP | USB; chassis state |
| `CHASSIS_CLOCK` | chassis clock bound above the limit | wait; link load |
| `ALONG_TRACK_REFERENCE: ...` | trailer longer than the LiDAR range with doors open and no `trailer.door_target_x_m` | close the doors or place the door-end target and enter its distance (01 section 6) |
| `TRANSFORMS:datum not registered` | no datum | **Register datum** at the surveyed mark; needed after every restart or pack swap |
| `LOCALIZATION` | position uncertainty above the credit budget (0.010 m) | wait; improve wall view; hold above 0.040 m (hold request) |
| `CHASSIS_MODE:<mode>` | the chassis is not `ARMED_IDLE` or `MOVING` | REARM, brake test, clear the reason |
| `OP_MODE` | chassis op_mode differs from the mission's | select the matching profile (`SET_OP_MODE`, accepted only when stationary) |

Mission holds and refusals during a survey (`supervisor.py`, `motion.py`, `rr_web/server.py`): `START_REFUSED:<why>`; `HOLD:<reason>`; `ROUTE_HOLD:<reason>` (LiDAR returns inside the swept region of the commanded move); `BLOCKED_WAIT`, then `STRIP_BLOCKED` (strip deferred after the patience time, 10 s default); `DRIVE_REJECTED:<reject_reason>` (for example `DIR_INHIBITED` from the rear field); `WALL_ENTRY_STOPPED:<reason>` (reverse wall entry refused or stopped, the track becomes a residual and is not retried); `NO_ROOM_TO_REVERSE`; `NOT_AT_SPOT`; `ARRIVAL_NOT_VERIFIED`; `PARK_NOT_VERIFIED`; `UNREACHABLE` (a flag seen only by a wall track); `HEAD_CHANGED` (Next refused after a head change); `REASON_REQUIRED` (Skip needs a reason); `EVENTS_NOT_READ`; `CHARGE_REFUSED`, `LOCAL_REARM_REQUIRED`, `BRAKE_TEST_REQUIRED`, `IDEMPOTENCY_KEY_REQUIRED`, `UNKNOWN_COMMAND`, `NOT_LOGGED_IN`, `CSRF`, `ROLE` (web service).

**MODEL.md revision 5 cell statuses and reasons** (`software/Operator_Interface_0.4_delta.md` section 5a; implementation in progress, `ros2_ws/STATUS.md`): `ALARM` (precedence over everything; also `ALARM - rate above counting range` for a gate saturated by rate), `NO DECISION` with its reason (`null reference unavailable`, `evaluator check failed`, `no calibration for this head and setup`, the last as `NO_CALIBRATION` at the head binding), `INCOMPLETE COVERAGE` (coverage under the profile minimum, no credited gate, or a gate excluded for a fault), `SENSITIVITY INSUFFICIENT` with its reason (D# above the goal; `reference rate above qualified range`; `reference gradient`), `ACCEPTABLE` only when none of those applies, and `ACQUISITION GAP` for floor swept while records were lost. Calibration refusals at binding: `CALIBRATION_UNKNOWN`, `CALIBRATION_NOT_APPROVED`, `CALIBRATION_SETUP_MISMATCH`. Provisional live values may differ from the recorded ones (labelled); *provisional alarm not confirmed* and *alarm found at final evaluation* are normal outcomes of the one-evaluation rule, not faults. Likely causes of `NO DECISION`: too little reference data for N_min (short scenarios and stationary recounts without a usable window; simulated about 12 % of cells in 230 to 460 s scenarios, VT-065), a failed evaluator check, a head or setup without a bound calibration.

Per-gate and per-cell reasons in the data: `NO_HOST_TIME`, `NO_CREDIT:<reason>` (a gate outside a credited stage), `POSE_UNCERTAIN`, `NO_POSE:<reason>`, `HEAD_FLAG...`, `LANE_FLAG...`. Floor classes in the map and residual list: `UNVISITED`, `ACCEPTABLE`, `INSUFFICIENT_SENSITIVITY`, `INVALID_DATA`, `BLOCKED`, `EXCLUDED`. Slip or an LiDAR scene without a usable wall makes `LOCALIZATION` hold; wall-track strips, the door strip and the bulkhead strip are residuals by design.

## 6. Heaters and cold behaviour

| Symptom | Checks | Likely cause |
|---|---|---|
| Head does not reach the +5 C set-point at -20 C | heater duty, jacket fitted, draught, NTC and cut-out | calculated demand at +5 C (`mechanical/head/out/head_report.md` section 9, still air, jacket): 15.2 W (prototype) / 15.5 W (production) at -20 C and 18.4 / 18.7 W at -25 C, 23.3 to 28.8 W in moving air, plus body-side conduction; against 20.8 W at 10 V and 30 W at 12 V from the film (19.9 W and 28.7 W delivered after wire drop, `harness/cables.md` section 6); the thermal calculations disagree (IB-39, IB-62); the optics supplier's limits at +5 C are unknown |
| `HEATER_FAULT` / `OVERTEMP` | `HTR_CUTOUT_OK`, plate NTC, `HTR_SENSE` current (0.5 V/A) | bimetal cut-out open (45 C class, UNVERIFIED), heater stuck on (the P-FET is not current limited; the chassis 4 A branch limit is the second protection), NTC open |
| Counts change at heater switching | the gate with the transition is marked in DIAG | coupling (T6); the host can exclude the gate |
| Bay heater never turns on | `HEATER {chassis_setpoint_c}` set (default off after every boot, 0 to 30 C); battery above `batt.warn_v` without a charger; `HEATER_SENSOR`; `EFUSE_CHS_HTR` | set-point not sent; forced off by the safety conditions; heater branch fault |
| `TEMP_RANGE` stop | pack, bay or board temperature | outside -25 to +60 C (config limits) or board above 85 C |
| Wheels slip, robot cannot hold the line | tyre and floor temperature; floor contamination | TPU stiffens below about -10 C; traction below -10 C and the caster below -20 C are not assumed (IB-55) |
| Sluggish or erratic controls, brake or connector faults after a cold soak | connector seating (JST GH -25 C recalled), coupler (-20 C recalled), relay pick-up at 10.5 V | components below their recalled ratings (IB-08, OI-04, OI-05); relays picking up at 10.5 V is a design check item not yet tested |
| Fogging or frost on the window or inside; leakage in the dark rate | dew point on return to warmth; desiccant indicator; lid and vent | condensation (no humidity sensor is fitted; a firmware dew-point gate is not possible); a light-leak or wet creepage; HV bias 62.5 V full scale |
| Pack delivers less than expected in the cold | pack surface and cell temperatures; BMS trips | deliverable fraction below the assumed 0.80 at -20 C (VT-040); the BMS behaviour below -20 C cell temperature is not confirmed |
| Head does not hold +5 C in moving air at -25 C on a low pack | heater duty, supply at the branch, `heater` flags | calculated: the fitted heater delivers 19.9 W at 10 V (28.7 W at 12 V after wire drop) while the demand at +5 C in moving air at -25 C is about 28 W (prototype, jacket, `mechanical/head/out/head_report.md` section 9) plus body-side conduction: short of capacity at 10 V; the dark rate and the optics' bond-line limits then matter |
| Head heater power far above the table | thermal break shims fitted, jacket fitted | metal receiver channels bolted to a cold chassis without the G-10 break demand 43 to 66 W (calculated); one with the shim 0.081 W/K per channel (calculated, G-10 UNVERIFIED) |
| Bay does not warm before charging | bay NTC, pad on the pack skin, external power | pre-heat to +5 C takes 95 to 200 min from a -25 C soak (assumed coupling); the bay is held at or above -10 C only on pack power (contract thermal policy) |

## 7. When to stop and escalate

Stop the run and report if: the latch sets with an element open; any `LATCH_STUCK`, `PERMIT_STUCK_ON`, `CHAIN_IMPLAUSIBLE`; the robot moves with no command; a head rail or bumper fails to open the chain; any reading outside the bring-up expectation of `docs/build/04_bring_up.md`. Do not repair a safety-chain fault in place without the chain procedure and the lead's agreement.

## 8. Open items

| Item | ID | Status |
|---|---|---|
| Fault behaviour observed on hardware | all | none observed |
| Undetected single faults of the chain (open brake path, K1 weld, loop comparator failing healthy) | IB-16, RSK-022 | open |
| `LATCH_UNEXPLAINED` / `STOP_ESCALATED` enums not used; contract and ICD differ | IB-60 | open |
| ICD section 6.3 and `pinmap.yaml` text still partly name the old look sensors | IB-34 | cosmetic, open |
| ToF driver absent | IB-04 | open |
| Charger and SoC | IB-05, IB-06 | open |
| Head dead-channel detection | IB-58 | open |
| Host handling of the new DIAG/STATUS members and renamed `look.*` keys | IB-59, IB-60 | open |
| Procedure for a robot stopped in a trailer (retrieval) | DEC-004 | site |
| Re-arm limits (11.7 V, +45 C coil), no hardware speed or force limit, no holding brake, residual single faults of section 6.1 of the chain analysis | IB-74, IB-16 | accepted limits pending the hazard owner's disposition |
| Latent faults covered only by the service tests (U_HOLD, U_LS, D_RUN, RELAY_RTN, R_RHD, set-stack faults); service pads reachable in the body unconfirmed | IB-74 | open |
| Watchdog first-strobe timing, boot watchdog test, dynamic brake check | VT-055, IB-74 | open |
| Head stage 3 firmware items: dead-channel detection, monitor-scan disturbance with the muxes off, frame monitor limits, heater cut at 3.2 A against an UNVERIFIED contact rating | IB-58, IB-69, VT-078, VT-079, VT-071 | open |
| Host handling of the new head DIAG/STATUS/GATESTAT members and renamed `look.*` keys; revision-5 statuses | IB-59, IB-60, IB-72 | partly landed; in progress |
