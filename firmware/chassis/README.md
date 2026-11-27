# Rad Roomba chassis firmware (motion MCU, RR-CHS 1.0)

Firmware for the STM32G474RET6 on RR-CHS-MAIN and its emulator `rr_chassis_sim`. Interface: [`interface/chassis_icd.md`](../../interface/chassis_icd.md), schema [`interface/chassis_link.schema.json`](../../interface/chassis_link.schema.json), pin map [`pinmap.yaml`](pinmap.yaml), contract requests [`CONTRACT_CHANGE_REQUESTS.md`](CONTRACT_CHANGE_REQUESTS.md).

**This is not a certified safety controller.** The hardwired traction chain (latch relay, brake relays, external window watchdog) removes traction energy without firmware. The firmware never opposes the chain, supervises and reports it, and adds a software protective-stop layer.

**Status of evidence.** The hardware-independent core is exercised on a plant model: every number below is `simulated`. The pin map is `tool-checked` against ST pin data and against the RR-CHS-MAIN rev A netlist export (`electronics/chassis_main/out/pinmap.json`: every MCU pin, every expander pin, every ToF connector → mux channel). The INA228 and INA3221 register maps were checked against the TI datasheets (fetched 2026-11-27); the LTC4162-F register map is UNVERIFIED and its driver is disabled. The STM32 image compiles and links (`tool-checked`) and **has never run on hardware**. Device details recalled from memory are marked UNVERIFIED in the sources and in `pinmap.yaml`.

## Layout

| Path | Content |
|---|---|
| `core/` | Portable C11 core: `rrch_proto.c` (protocol server), `rrch_core.c` (mode state machine, software stop latch, brake test, panel, heater, watchdog cross-checks, event log), `rrch_chain.c` (chain supervision: node decode, ARM_PERMIT readback, presence decode), `rrch_motion.c` (protective fields, drive loops, odometry, stationarity), `rrch_cfg.c` (persistent configuration), `rrch_pwrdev.c` (INA228 / INA3221 register decode, UNVERIFIED LTC4162 table), `rrch.h` (types + HAL) |
| `port/host/` | `sim.c` plant model + HAL, `sim_main.c` → `rr_chassis_sim` (TCP link, UDP environment) |
| `port/stm32g474/` | PlatformIO project: `bsp.c`, `usb_cdc.c`, `main.c`, `tof_vl53l4ed.c` (stub), generated `board_pins.h` |
| `tests/` | C unit tests on the plant, Python integration tests, `rrchs_client.py` |
| `tools/` | `check_pinmap.py` (+ extracted LQFP64 pin facts; cross-check against the board netlist export), `look_geometry.py` (look-sensor defaults from `mechanical/common/frames.yaml`) |
| `../common/` | Shared library (framing, JSON, CRC, UUID) owned by the head firmware lead; used unmodified |

## Toolchain (pinned)

| Tool | Version used | Note |
|---|---|---|
| Host compiler | GCC 13 (Ubuntu 24.04), CMake ≥ 3.16, Ninja | `-std=c11 -Wall -Wextra -Werror`; unit tests with ASan + UBSan |
| Python | 3.13 (3.10+ should do), PyYAML 6, `jsonschema` 4 (optional: schema validation in the integration tests) | |
| PlatformIO Core | 6.x (6.2.0 used here) | |
| Platform | `ststm32@20.0.0` | pinned in `platformio.ini` |
| ARM toolchain | `toolchain-gccarmnoneeabi@1.120301.0` = arm-none-eabi-gcc 12.3.1 | pinned |
| HAL / USB library | `framework-stm32cubeg4@1.6.3` (STM32CubeG4 HAL, ST USB device library) | pinned |

## Build and test

```sh
cd firmware/chassis
./check.sh                # pin map check, host build, unit tests, integration tests, STM32 build; non-zero on failure
./check.sh --no-target    # without PlatformIO

# by hand
cmake -S . -B build -G Ninja && ninja -C build -j2
build/test_chain && build/test_state_machine && build/test_drive build/drive_report.txt
python3 tests/test_integration.py build/rr_chassis_sim
(cd port/stm32g474 && pio run -e rr_chs_main)        # 8 MHz crystal; -e rr_chs_main_24mhz for 24 MHz
```

Results observed on 2026-11-27 with the stage-3 board (`./check.sh`, exit 0): `test_chain` 329 checks, `test_state_machine` 1193, `test_review` 64 (review regressions, stage-3 checks, section-6.1 residual faults, thermal policy), `test_drive` 2476, 9 Python integration tests, all passing; netlist cross-check 110 items. Target image: flash 87 608 bytes (text 87 100 + data 508) of 524 288, static RAM 23 716 bytes of 131 072 (hard-float, `-Os` PlatformIO default).

### Simulated drive performance (plant model, not measurements)

Plant (IB-03/IB-24, constants taken from `electronics/analysis/chassis_braking.py`, the electronics' brake model): two Pololu #2828 150:1 gearmotors, R 2.18 Ω (12 V / 5.5 A), back-EMF 31.7 V per m/s per motor (1.648 V·s/rad at the wheel), L 2.3 mH (emulator assumption), 12 kg, 104 mm wheels, 270 mm track. *Nominal* set (default): force constant = back-EMF constant (31.7 N/A, lossless gear), rotor inertia 1 × 10⁻⁶ kg m² = 8.3 kg reflected per motor, Coulomb friction 16.2 N total (3.5 N rolling + 2 × 0.2 A × 31.7). *Conservative* set: 17.4 N/A (catalogue stall torque), 2 × 10⁻⁶ kg m² (16.6 kg per motor), no friction. Brake loop 3.22 Ω (1.0 Ω resistor + 0.04 Ω contacts + winding). Hardwired chain timing from `chassis_braking_tables.md` T2: brake-relay coils lose supply at once, NO contacts open at 7.5 ms, NC contacts close on the resistor at 10.5 ms; K1 releases at 4 ms (bridges asleep, VMOT eFuse off); VMOT bleeds with τ 0.81 s; bridges chop at 2.68 A; IPROPI saturates at 2.68 A. 10 kHz integration.

| Quantity | Simulated | Reference |
|---|---|---|
| Step to 0.10 m/s: rise 10–90 % / overshoot / steady-state error | 240 ms / 3.0 % / < 0.01 % | set-point ramp alone 267 ms (0.30 m/s²) |
| Step to 0.20 m/s | 515 ms / 1.6 % / < 0.01 % | ramp alone 533 ms |
| Stop from 0.20 m/s, controlled (0.40 m/s² ramp) | 50.3 mm, 499 ms | contract stop model 100 mm (0.15 s, 0.40 m/s², 20 mm) |
| Stop from 0.20 m/s, software protective stop (1.0 m/s² ramp) | 20.6 mm, 200 ms | 100 mm |
| Host stops sending at 0.20 m/s (last command ttl 200 ms) | 56.4 mm and 379 ms from the moment the host went silent to rest | v·ttl + model |
| `CMD_TIMEOUT` latch after the last accepted `DRIVE` (ttl 200 ms) | 200 ms | ≤ ttl + 1 ms |
| Cliff sample at 0.20 m/s → rest | 23.8 mm | 100 mm |
| Encoder dropout at 0.20 m/s → rest | 45.2 mm | — |
| MCU reset at 0.20 m/s → rest (latch drop) | 8.4 mm | — |
| Bumper trip at 0.20 m/s over the emulator sockets → rest | 8.9 mm (incl. UDP delivery) | — |
| Look-ahead floor loss at 0.20 m/s (forward pair) → rest | 266–267 mm of the 285 mm to the rail | `look.fwd_ahead_m` |
| Look-behind floor loss at −0.05 m/s (tail pair) → rest | 182 mm of the 201 mm behind the 0.290 m radius | `look.rev_ahead_m` |
| Tick odometry vs ground truth (straight, arc, pivot, reverse) | ≤ 0.03 mm, ≤ 0.0001 rad | quantisation only; 5 % wheel slip shows as 27 mm / 0.09 rad over 0.5 m, as it must |
| Blocked wheels: current after fold-back / `STALL` latch | 2.68 A (hardware chop) / 547 ms | limit 2.5 A, 500 ms |
| Brake test: latch drop / relays / VMOT decay to 1 V | 5 ms / 9 ms / 2069 ms | emulator relay model; τ 0.8 s bleed |

**Latch drop (E-stop or any contact element), distance from the chain opening to rest** (`test_drive`, plant alone, bridges driving the steady-state duty until K1 releases):

| v0 | Nominal, simulated | Nominal, electronics | Conservative, simulated | Conservative, electronics |
|---:|---:|---:|---:|---:|
| 0.10 m/s | 3.6 mm (88 ms) | 3.8 mm | 14.2 mm | 14.3 mm |
| 0.20 m/s | 8.5 mm (115 ms) | 8.7 mm | 28.5 mm | 28.5 mm |
| 0.30 m/s | 13.7 mm (132 ms) | 13.9 mm | 42.7 mm | 42.8 mm |

Electronics values: `chassis_braking.py` (`chassis_braking_tables.md` T3 for 0.10/0.20 m/s; 0.30 m/s computed with the same `brake()` function and 10.5 ms dead time — 0.30 m/s is above the 0.20 m/s contract ceiling and is a runaway case). All differences are below 4 %; the nominal simulation is slightly shorter because the plant also applies friction during the dead time and the 5 ms of driving before K1 releases are modelled, whereas the calculation coasts at v0 for the whole 10.5 ms. The conservative case has no friction and decays exponentially (time to 10⁻⁵ m/s ≈ 1.3 s). The firmware closed-loop E-stop case in `drive_report.txt` (8.5 mm from 0.20 m/s) agrees. These are `simulated` from `calculated` inputs; the rotor inertia is not published and dominates (spin-down test, `chassis_safety_chain.md` §8 step 12). Do not use the nominal column for clearance arguments.

## Emulator `rr_chassis_sim`

```sh
build/rr_chassis_sim [--port 5550] [--env-port 5551] [--bind 127.0.0.1] [--seed N] [--speed X] [--duration S] [--pty] [--quiet]
python3 tests/rrchs_client.py STATE          # one-shot client
```

- **Host link**: TCP server, default `127.0.0.1:5550`, one client, carries exactly the CDC byte stream of the ICD (`--pty` additionally offers it on a pseudo-terminal). A new connection replaces the old one; the session state lives in the firmware, not in the socket.
- **Time**: simulated time runs at `--speed` × real time (default 1; tests use 2). The chassis clock restarts at 0 on every simulated MCU reset. Deterministic for a given `--seed` and input timing.
- **Environment socket**: UDP JSON, default `127.0.0.1:5551`. Every datagram is one JSON object; it is answered with `{"type":"ACK","ok":true|false}` and subscribes its sender (up to 4) to the ground-truth stream sent every 10 ms of simulated time:

```json
{"type":"TRUTH","t_us":5230000,"chassis_us":5230000,"x":0.4312,"y":0.0021,"yaw":0.0102,"v":0.1,"w":0.0,"wheel_l_rad":8.29,"wheel_r_rad":8.31,"i_a":[0.31,0.3],"vmot":13.0,"latch":true,"arm_permit":true,"wdg_ok":true,"bridge_awake":true,"buzzer":false,"leds":3,"head_pwr":false,"head_htr":false,"chs_htr":false,"mode":"MOVING","boot_id":"…","mcu_resets":0}
```

Pose is of `base_link` in the simulator's world frame (starts at 0,0,0; `{"pose":[x,y,yaw]}` teleports). Inputs (all optional, combine freely):

| Key | Value | Meaning |
|---|---|---|
| `estop`, `hands_on`, `bumper_l`, `bumper_r` | bool | true = pressed / engaged (chain opens) |
| `mode_run`, `head_docked`, `j2` | bool | true = RUN / docked / J2 mated |
| `chg_cover_open`, `chg_plug` | bool | charger cover open / plug link present |
| `pres_ohm`, `loop_ohm` | number | J1 pin-7 code resistor (4700 head, 1137 head via LAB extension, 1500 extension only, 1e9 unplugged) and interlock loop (1000 healthy) |
| `press`, `press_ms` | `"REARM"` \| `"PAUSE"`, ms (default 200) | local buttons; REARM also sets the latch relay if the chain is healthy |
| `tof` | `{"CLIFF_FL": 31, "REAR_C": null, "LOOK_FL": "INVALID"}` | range in mm, `null` = no target, any string = invalid. Ids as in the ICD. Defaults: cliff 30, `LOOK_FL`/`LOOK_FR` 524, `LOOK_RL`/`LOOK_RR` 267 (level floor), rear no target |
| `tof_stale` | `["LOOK_RR", …]` or `["ALL"]` or `[]` | sensors that stop delivering samples (the list replaces the previous one) |
| `vbat`, `soc`, `temp_bay`, `temp_pack`, `temp_board`, `tilt_deg` | number | battery, temperatures, floor pitch |
| `enc_dropout`, `block` | `"L"`, `"R"`, `"BOTH"`, `"NONE"` | encoder stops counting / wheel mechanically blocked |
| `slip` | `[left, right]` 0…0.95 | wheel slip fraction |
| `usb_stall`, `usb_down` | bool | host bytes are held back (delivered late on release) / USB reports not configured |
| `imu_off`, `iox_fail`, `latch_weld`, `estop_a_stuck`, `nv_fail`, `efuse_fault` (bit mask) | | sensor and hardware faults |
| `iox_b_fail`, `permit_short`, `permit_open` | bool | IOX_B (CHAIN_END_RB) not answering; ARM_PERMIT photo-MOS U24 shorted / open |
| `k1_fault` | `"SEAL_WELD"`, `"NONE"` | K1 pole A NO welded (coil follows CHAIN_END, NC open); `latch_weld` = both K1 poles welded |
| `rearm_aux_short`, `rearm_set_short` | bool | REARM aux / set contact line held closed (welded contact, W-018 short; both = §6.1 case 5) |
| `rail_weld`, `loop_sns_leak`, `bumper_l_weld` | bool | §6.1 residual faults: loop reads healthy on every channel / left bumper cannot open |
| `run_hd_short`, `k1_run_short`, `chain_end_short`, `uhold_short` | bool | board shorts to a supply (§6.1 case 4) / U_HOLD shorted |
| `loop_b_stuck_ok`, `loop_b_stuck_open`, `iox_d_fail`, `iox_d_bad_pattern` | bool | channel B faults; IOX_D not answering / pattern wrong |
| `run12_short`, `loop_cmp_stuck`, `iox_drive_loop`, `io_cfg_fault` | bool | review M6 RUN_12V fed from a supply; C2 U30A cannot pull HEAD_LOOP_OK_RB low; M2 IOX_A GPA5 driven as an output; M2/M3 pin configuration wrong |
| `cset_diode`, `cset_energy` | bool | stage-3 D_RSET + Q_SDIS (default true = current netlist; false = stage-2 back-feed model); REARM needs C_SET above 9 V (off by default) |
| `wdi_edge`, `jp1_open`, `vmot_tau_s` | `"FALLING"`/`"RISING"`/`"BOTH"`, bool, number | edges the TPS3430 model counts; JP1 open (WDO does not reset the MCU); VMOT bleed time constant |
| `chain_short` | `"CH_N1"`…`"CH_N9"`, `"CH_N4A"`, `"CH_N8A"`, `"CHAIN_END"`, `"NONE"` | chain node shorted to a live conductor (plausibility tests) |
| `pmon_fail`, `branch_fail`, `charger_fail` | bool | INA228 / INA3221 / charger telemetry lost |
| `freeze_control`, `freeze_supervisor`, `freeze_background` | bool | stop one firmware context (watchdog tests) |
| `mcu_reset` | `"PIN"`, `"WATCHDOG"`, `"SOFTWARE"`, `"BROWNOUT"`, `"POWER_ON"` | reset the MCU now (plant keeps moving/braking) |

The emulator models the stage-3 chain (`electronics/analysis/chassis_safety_chain.md` §2.1, S3 overrides) as node voltages: series elements incl. the two head-loop channels (U21 → CH_N6A → U21B), K1 (seal-in, 10 ms pick-up, 4 ms release), the on-board set stage (closing edge of the set contact → 110 ms gate pulse, AND the level of the aux contact → U_SET dumps C_SET into the K1 coil and lights U_HOLD), C_SET charged only from CHAIN_END through D_RSET (τ 2.2 s) and emptied by Q_SDIS (τ 0.1 s) when CHAIN_END is dead, K1 must-operate 7.5 V [A] (so REARM works only after ≈ 2 s of closed chain), U_HOLD self-holding from RUN_HD, D_RUN, U_LS in the K2/K3 return, VMOT eFuse and U9 from RUN_HD, `HW_LATCH_RB` = RUN_12V tap, IOX_D (U47) readbacks with the fixed pattern, comparator windows as built (A 0.59–1.55 kΩ, B < 2.70 kΩ, LAB 3.92–5.64 kΩ), the TPS3430 (falling edges, 2.2–23.4 ms, WDO 200 ms holding NRST with JP1), K2/K3 NO open 7.8 ms / NC closed 10.8 ms, `BRAKE_x_RB` garbage while the bridges are awake, VMOT bleed `vmot_tau_s`, 2.68 A chop, INA228/INA3221 register images. `cset_diode:false` keeps the stage-2 C_SET back-feed model (only that part of stage 2). TRUTH carries `run12`, `k1`, `k1_run`, `c_set_v`, `emu_lag_us`, `emu_rebases`. The unit-test harness waits for C_SET before a REARM press when the chain is closed (an operator waits for the REARM lamp).

## Flash and debug (hardware)

Nothing here has been done on a board; these are the intended procedures.

- **SWD / ST-LINK**: `cd port/stm32g474 && pio run -e rr_chs_main -t upload` (or `-e rr_chs_main_24mhz`). Debug: `pio debug -e rr_chs_main` (ST-LINK GDB server). The 10-pin Cortex header carries SWDIO, SWCLK, SWO, NRST.
- **USB DFU** (UNVERIFIED for this part, check AN2606): hold the BOOT0 button during reset, then `dfu-util -a 0 -s 0x08000000:leave -D .pio/build/rr_chs_main/firmware.bin`. In the ROM bootloader all outputs are high-Z, so ARM_PERMIT is low and the chain is open.
- **Debug UART**: USART3, PC10 TX / PC11 RX, 115200 8N1, 3.3 V.
- Do not hold the MCU halted in a debugger with the external watchdog fitted and traction armed: the watchdog will open the chain (intended).
- A NUCLEO-G474RE runs the same image for protocol bring-up (USB on the user connector PA11/PA12 must be wired; with nothing connected every readback reads open and the mode is `HW_INHIBIT`/`FAULT`).

## Hardware mapping (generated from `pinmap.yaml`)

`tools/check_pinmap.py --readme README.md` regenerates this section; `check.sh` fails if it is stale.

<!-- HARDWARE_MAPPING_BEGIN -->
<!-- GENERATED by tools/check_pinmap.py from pinmap.yaml - do not edit. -->

| Pin | LQFP64 | Signal | Function | AF | Dir | Reset state / note |
|---|---:|---|---|---|---|---|
| PC13 | 2 | `WDG_OK_RB` | GPIO | GPIO | in | Tap on chain node CH_N9 (after U23 WDG_OK): HIGH = chain live up to and including WDG_OK (CCR-E03 d). Low a... |
| PC14 | 3 | `BRAKE_L_RB` | GPIO | GPIO | in | Left brake relay K2 (G2RL-2): HIGH = at least one motor terminal connected to the bridge, LOW = both poles ... |
| PC15 | 4 | `BRAKE_R_RB` | GPIO | GPIO | in | Right brake relay, as above. |
| PF0 | 5 | `OSC_IN` | RCC_OSC_IN | ANALOG | in | HSE crystal. |
| PF1 | 6 | `OSC_OUT` | RCC_OSC_OUT | ANALOG | out |  |
| PC0 | 8 | `HEAD_PRES_ID` | ADC1_IN6 | ANALOG | in | J1 pin 7 (J_HEAD1 pin 7). 4.70 kOhm 0.1 % pull-up (R77) to VREF+ directly on the connector node; no series ... |
| PC1 | 9 | `HEAD_LOOP_SENSE` | ADC1_IN7 | ANALOG | in | Analog copy of the J1 5/6 loop sense voltage (lower 1.00 kOhm R71), 10 kOhm series (R76), BAT54 clamp, 10 n... |
| PC2 | 10 | `NTC_BAY` | ADC1_IN8 | ANALOG | in | 10 kOhm B3435-class NTC (J_NTC pin 1) in the battery bay, 10.0 kOhm pull-up (R215) to VREF+ 3.000 V, 1 kOhm... |
| PC3 | 11 | `NTC_PACK` | ADC1_IN9 | ANALOG | in | Second NTC on the pack surface (J_NTC pin 3, R217 pull-up, R218 series; heater plausibility + battery.temp_... |
| PA0 | 12 | `IPROPI_L` | ADC1_IN1 | ANALOG | in | DRV8874 IPROPI left bridge. RIPROPI 2.49 kOhm (R153) -> 1.1205 V/A, i.e. 0.8925 A/V (CCR-E03 b); 1 kOhm ser... |
| PA1 | 13 | `IPROPI_R` | ADC2_IN2 | ANALOG | in | As IPROPI_L, right bridge. ADC1+ADC2 dual simultaneous sampling at PWM centre. |
| PA2 | 14 | `VMOT_SENSE` | ADC1_IN3 | ANALOG | in | VMOT divider 47k/10k (16.0 V -> 2.81 V; full scale 17.1 V at VREF+ 3.000 V), 100 nF. Safety-relevant readba... |
| PA3 | 17 | `VBAT_SENSE` | ADC1_IN4 | ANALOG | in | VBAT_SW divider 47k/10k. Fast brown-out logging and I2C-independent low-battery check (INA228 is the accura... |
| PA4 | 18 | `IMU_CS_ACC_N` | GPIO | GPIO | out | high via 10k pull-up. BMI088 (U42) accelerometer CSB1 (pin 14). Stage 2 S2-05: U42 pin 2 tied to GND (GNDA ... |
| PA5 | 19 | `SPI1_SCK` | SPI1_SCK | AF5 | out | SPI mode 3, <= 5 MHz. Shared: BMI088 accel, BMI088 gyro, IOX_A. |
| PA6 | 20 | `SPI1_MISO` | SPI1_MISO | AF5 | in | 33 Ohm series at sources. |
| PA7 | 21 | `SPI1_MOSI` | SPI1_MOSI | AF5 | out |  |
| PC4 | 22 | `NTC_BOARD` | ADC2_IN5 | ANALOG | in | NTC next to the H-bridges. MCU internal temperature sensor is the cross-check. |
| PC5 | 23 | `IMU_CS_GYR_N` | GPIO | GPIO | out | high via 10k pull-up. BMI088 gyro CSB2. |
| PB0 | 24 | `IOX_A_CS_N` | GPIO | GPIO | out | high via 10k pull-up. Chip select of the fast SPI expander IOX_A (chain readbacks, 1 kHz). |
| PB1 | 25 | `V5_SENSE` | ADC1_IN12 | ANALOG | in | V5_CM5 divider 10k/10k. |
| PB2 | 26 | `BUZZER` | TIM5_CH1 | AF2 | out | low via 10k pull-down (silent). Pre-motion alert. Low-side FET to a self-oscillating buzzer (GPIO level) or... |
| PB10 | 30 | `ARM_PERMIT` | GPIO | GPIO | out | LOW via 4.7k pull-down (chain open). Chain element ARM_PERMIT, active high. Must not be bridged by any debu... |
| PB11 | 33 | `WDG_STROBE` | GPIO | GPIO | out | static (no edges) -> watchdog times out. WDI of the external window watchdog (TPS3430 class). Firmware stro... |
| PB12 | 34 | `ESTOP_A_RB` | GPIO | GPIO | in | Tap on chain node CH_N2 (after E-stop pole A): 100k/56k (R99/R100) + 22 nF + Schottky clamp. HIGH = chain l... |
| PB13 | 35 | `ESTOP_B_RB` | GPIO | GPIO | in | E-stop pole B (COIL_RTN, low side of all three coils) through a P-MOSFET detector: HIGH = pole closed. Inde... |
| PB14 | 36 | `HEAD_HTR_EN` | GPIO | GPIO | out | low via 10k pull-down (off). J1 3/4 heater branch eFuse U17 enable (TPS259470). Stage 2: limit 3343/845 = 3... |
| PB15 | 37 | `CHS_HTR_EN` | GPIO | GPIO | out | low via 10k pull-down (off). Chassis/bay heater eFuse enable; slow PWM (1 s period) from the heater regulat... |
| PC6 | 38 | `MOT_L_IN1` | TIM8_CH1 | AF4 | out | low via 10k pull-down. DRV8874-class IN1, 20 kHz centre-aligned PWM. |
| PC7 | 39 | `MOT_L_IN2` | TIM8_CH2 | AF4 | out | low via 10k pull-down. IN2. |
| PC8 | 40 | `MOT_R_IN1` | TIM8_CH3 | AF4 | out | low via 10k pull-down |
| PC9 | 41 | `MOT_R_IN2` | TIM8_CH4 | AF4 | out | low via 10k pull-down |
| PA8 | 42 | `I2C_SYS_SDA` | I2C2_SDA | AF4 | bidir | System bus 400 kHz, 2.2k pull-up: charger, pack monitor, branch monitor, IOX_B, IOX_C. |
| PA9 | 43 | `I2C_SYS_SCL` | I2C2_SCL | AF4 | bidir | As above. |
| PA10 | 44 | `DRV_NSLEEP` | GPIO | GPIO | out | low via 10k pull-down (bridges asleep). Both bridges. Recommend hardware AND with HW_LATCH so the bridges s... |
| PA11 | 45 | `USB_DM` | USB_DM | ANALOG | bidir | USB FS device to the CM5 carrier. ESD array at connector. No external pull-up (internal DP pull-up). |
| PA12 | 46 | `USB_DP` | USB_DP | ANALOG | bidir |  |
| PA13 | 49 | `SWDIO` | SYS_JTMS-SWDIO | AF0 | bidir | 10-pin 1.27 mm Cortex debug header (SWDIO, SWCLK, SWO, NRST, 3V3, GND). |
| PA14 | 50 | `SWCLK` | SYS_JTCK-SWCLK | AF0 | in |  |
| PA15 | 51 | `I2C_TOF_SCL` | I2C1_SCL | AF4 | bidir | ToF bus 400 kHz, 2.2k pull-up: two TCA9548A (0x70, 0x71) -> 11 x VL53L4ED. Separate from the system bus so ... |
| PC10 | 52 | `DBG_TX` | USART3_TX | AF7 | out | Debug console 115200 8N1, 3.3 V, 3-pin header + GND. |
| PC11 | 53 | `DBG_RX` | USART3_RX | AF7 | in | 10k pull-up. |
| PC12 | 54 | `J2_PRES_RB` | GPIO | GPIO | in | J2 pin 7 (linked to BUS_GND in the head plug) through a comparator/inverter: HIGH = J2 mated. 1 ms sampling... |
| PD2 | 55 | `HW_LATCH_RB` | GPIO | GPIO | in | Tap on RUN_12V (R117/R118; RUN_12V = CHAIN_END through K1 pole B): HIGH = chain live AND K1 closed, not the... |
| PB3 | 56 | `SWO_SPARE` | SYS_JTDO-SWO | AF0 | out | SWO trace by default. Spare GPIO on a test point; solder-jumper option to IOX_A INTA/INTB (interrupt-on-cha... |
| PB4 | 57 | `ENC_R_A` | TIM3_CH1 | AF2 | in | Right encoder A after 5 V->3.3 V Schmitt buffer (encoder outputs need 5 V pull-ups). 100 pF. UNVERIFIED: PB... |
| PB5 | 58 | `ENC_R_B` | TIM3_CH2 | AF2 | in | Right encoder B. |
| PB6 | 59 | `ENC_L_A` | TIM4_CH1 | AF2 | in | Left encoder A. Same UCPD dead-battery remark as PB4 (UNVERIFIED). |
| PB7 | 60 | `ENC_L_B` | TIM4_CH2 | AF2 | in | Left encoder B. 16-bit counters extended in software (max 10.7 kcounts/s -> 0.011 counts per 1 us; wrap eve... |
| PB8 | 61 | `BOOT0_LED_STAT` | GPIO | GPIO | out | low via status LED + 1k to GND (BOOT0 = 0). BOOT0 sampled at reset: DFU push-button to 3V3 through 1k force... |
| PB9 | 62 | `I2C_TOF_SDA` | I2C1_SDA | AF4 | bidir | As above. |

**IOX_A** - MCP23S17 class (16-bit, SPI, 10 MHz) on SPI1, CS PB0

| Expander pin | Signal | Note |
|---|---|---|
| GPA0 | `MODE_RUN_RB` | Node CH_N1: selector in RUN = HIGH |
| GPA1 | `HANDS_ON_RB` | Node CH_N3: live through HANDS-ON (not pressed) |
| GPA2 | `CHG_COVER_RB` | Node CH_N4A: live through the inlet cover switch (shut) |
| GPA3 | `CHG_PLUG_LINK_RB` | Node CH_N4: live through U20 (plug link absent and inlet dead) |
| GPA4 | `HEAD_DOCK_RB` | Node CH_N5: live through the dock switch |
| GPA5 | `HEAD_LOOP_OK_RB` | Comparator U30 output (drives U21): loop 0.59-1.55 kOhm = HIGH. Not a node; CH_N6/CH_N7 have test points only |
| GPA6 | `HEAD_LOOP_SHORT_RB` | Comparator U32A (diverse from U30): loop below window (short) = HIGH |
| GPA7 | `LAB_KEY_N_RB` | Comparator U31 output (drives U22): PRES_ID 3.92-5.64 kOhm (head, no LAB resistor) = HIGH |
| GPB0 | `BODY_BUMPER_L_RB` | Node CH_N8A (after U21, U22 and J_BUMP_L); known only while CH_N5 is live and GPA5/GPA7 are HIGH |
| GPB1 | `BODY_BUMPER_R_RB` | Node CH_N8 (after J_BUMP_R, rear-right corner since stage 2) |
| GPB2 | `REARM_BTN` | Local REARM/Start pressed = HIGH (second, isolated contact of the button or opto across the set path; the first contact is in the latch set path) |
| GPB3 | `PAUSE_BTN` | Local PAUSE/Stop pressed = HIGH. Stage 2 (S2-01): button on its own connector J_PAUSE (JST GH 5-way, rear-right): pin 1 PAUSE_3V3 (own 1 kOhm supply R_PAUSE), pin 2 PAUSE_BTN_RAW -> R131 -> here, pin 3 V12_AUX lamp +, pin 4 LAMP_PAUSE_K (Q56 from IOX_B P06); ESD D_PAUSE. J_BTN pins 5/8 no longer used |
| GPB4 | `DRV_L_NFAULT` | LOW = left bridge fault (open drain, 10k pull-up) |
| GPB5 | `DRV_R_NFAULT` | LOW = right bridge fault |
| GPB6 | `BUS_CLAMP_ACTIVE` | Brake chopper / bus clamp conducting = HIGH |
| GPB7 | `SENTINEL` | Wired to the WDG_STROBE net (PB11): firmware checks that this bit follows the strobe it generates, which proves the expander read path is live. |

**IOX_B** - TCA9535 (U44, TCA9535PWR) on I2C_SYS, address 0x20

| Expander pin | Signal | Note |
|---|---|---|
| P00 | `LED_READY` | Annunciator, active high via driver |
| P01 | `LED_MOVING` |  |
| P02 | `LED_HOLD` |  |
| P03 | `LED_FAULT` | Additionally OR-ed in hardware with NOT WDG_OK so a dead MCU shows FAULT |
| P04 | `LED_CHARGE` |  |
| P05 | `LAMP_REARM` | REARM button illumination |
| P06 | `LAMP_PAUSE` | Q56 low side -> J_PAUSE pin 4 (stage 2) |
| P07 | `LED_STAT2` | Second on-board status LED (protocol activity) |
| P10 | `HEAD_PWR_EN` | default off (pull-down). J1 1/2 (J_HEAD1 1/2) eFuse U16 enable, 1.5 A. Forced off by firmware in SERVICE_CHARGE and in hardware while the charge inlet is live. |
| P11 | `V12_LIDAR_EN` | default on (pull-up). Holds across MCU reset |
| P12 | `V5_CM5_OFF_REQ` | default not asserted (pull-down) = rail ON. Only asserted for a deliberate compute power cycle; the 5 V rail stays up across MCU resets and with the MCU unprogrammed. |
| P13 | `TOF_XSHUT_CLIFF` | default low (sensors held in reset). Shared XSHUT of the 4 cliff sensors |
| P14 | `TOF_XSHUT_LOOK` | default low. Shared XSHUT of the 4 look-ahead sensors |
| P15 | `TOF_XSHUT_REAR` | default low. Shared XSHUT of the 3 rear sensors |
| P16 | `TOF_MUX_NRST` | default low. Reset of both TCA9548A (bus recovery) |
| P17 | `CHAIN_END_RB` | INPUT, never driven (CCR-E02, IB-01): tap on node CHAIN_END after the ARM_PERMIT photo-MOS U24 (100k/56k, BAT54 clamp). HIGH = whole chain live except E-stop pole B. Read at 100 Hz; compared with the ARM_PERMIT output (PERMIT_STUCK_ON / PERMIT_STUCK_OFF). |

**IOX_C** - TCA9534 / PCA9534 class (8-bit, I2C) on I2C_SYS, address 0x21

| Expander pin | Signal | Note |
|---|---|---|
| P0 | `HEAD_PWR_NFLT` | LOW = eFuse fault/tripped |
| P1 | `HEAD_HTR_NFLT` |  |
| P2 | `CHS_HTR_NFLT` |  |
| P3 | `V12_LIDAR_NFLT` |  |
| P4 | `V5_CM5_NFLT` |  |
| P5 | `CHG_NSMBALERT` | Charger alert |
| P6 | `PMON_NALERT` | Pack monitor alert |
| P7 | `V5_PGOOD` |  |

**IOX_D** - TCA9534 (U47, TCA9534PWR) - stage 3 S3-F1 on I2C_SYS, address 0x22

| Expander pin | Signal | Note |
|---|---|---|
| P0 | `LATCH_NC_RB` | Tap on K1 pole A NC (K1_SEAL_A biased from 3V3): HIGH = K1 pole A released, valid with the chain dead. LOW with HW_LATCH_RB low > 30 ms -> K1_WELD |
| P1 | `LATCH_RUN_RB` | Tap on K1_RUN (K1 pole B output, before U_HOLD): HIGH = CHAIN_END live AND K1 pole B closed. HIGH with HW_LATCH_RB low -> K1_WELD; HW_LATCH_RB high with this low -> RUN_SHORT |
| P2 | `HEAD_LOOP2_OK_RB` | Head-loop channel B (U46 TLV3201, drives U21B between CH_N6A and CH_N6): HIGH = loop closed (< 2.70 kOhm); detects open only |
| P3 | `REARM_SET_RB` | REARM set contact (J_BTN 1-2, 5 V signal into the on-board edge-triggered set stage): HIGH = closed. Must agree with REARM_BTN (aux) within 200 ms |
| P4 | `IOXD_P4` | tied to 3V3: reads 1 (pattern) |
| P5 | `IOXD_P5` | tied to GND: reads 0 (pattern) |
| P6 | `IOXD_P6` | tied to GND: reads 0 |
| P7 | `IOXD_P7` | tied to GND: reads 0 |

**ToF sensors** (I2C_TOF, two TCA9548A)

| Index | Id | Mux | Channel | XSHUT group | Role |
|---:|---|---:|---:|---|---|
| 0 | `CLIFF_FL` | 0 | 0 | TOF_XSHUT_CLIFF | downward cliff, front-left wheel/head corner |
| 1 | `CLIFF_FR` | 1 | 0 | TOF_XSHUT_CLIFF | downward cliff, front-right |
| 2 | `CLIFF_RL` | 0 | 1 | TOF_XSHUT_CLIFF | downward cliff, rear-left |
| 3 | `CLIFF_RR` | 1 | 1 | TOF_XSHUT_CLIFF | downward cliff, rear-right |
| 4 | `LOOK_FL` | 0 | 2 | TOF_XSHUT_LOOK | oblique, forward over the head from the left grip cheek; guards forward travel (pair partner LOOK_FR on mux 1) |
| 5 | `LOOK_RL` | 1 | 2 | TOF_XSHUT_LOOK | oblique, rearward from the tail, left; guards reverse travel (pair partner LOOK_RR on mux 0) |
| 6 | `LOOK_RR` | 0 | 3 | TOF_XSHUT_LOOK | oblique, rearward from the tail, right |
| 7 | `LOOK_FR` | 1 | 3 | TOF_XSHUT_LOOK | oblique, forward over the head from the right grip cheek |
| 8 | `REAR_L` | 0 | 4 | TOF_XSHUT_REAR | rear proximity left |
| 9 | `REAR_C` | 1 | 4 | TOF_XSHUT_REAR | rear proximity centre |
| 10 | `REAR_R` | 0 | 5 | TOF_XSHUT_REAR | rear proximity right |
<!-- HARDWARE_MAPPING_END -->

**Expander decision.** All 51 I/O are used by timing-critical or safety-relevant signals (PWM, encoders, ten analog inputs, both E-stop poles, latch, brake relays, watchdog, ARM_PERMIT, J2 presence, heater enables). The remaining slow signals use three expanders: IOX_A (16-bit **SPI**, read in full every millisecond inside the control tick, so the other chain readbacks and the buttons keep 1 kHz event latching with a bounded transfer time; its read path is proven every tick by a sentinel bit wired to the watchdog strobe), IOX_B (16-bit I²C, outputs: annunciators and enables that must hold across MCU resets), IOX_C (8-bit I²C, eFuse faults and alerts). Branch currents come from a 3-channel I²C monitor instead of three ADC pins. None of the expanders is in the hardwired chain.

## Configuration keys

Complete table with defaults, limits and units: ICD §8 (`CONFIG_GET {"key":"_keys"}` enumerates them on a live unit). Groups: `id.*`, `cal.*` (wheel radii, track — nominal 0.052 m / 0.270 m), `caps.<op_mode>.*`, `drive.*`, `link.*`, `alert.*`, `stationary.*`, `tof.*`, `cliff.*`, `look.*`, `rear.*`, `stop.*`, `safety.*`, `imu.*`, `batt.*`, `temp.*`, `heater.*`, `chain.*`, `brake.*`. Stored in two alternating flash copies with layout version, generation counter and CRC-32; keyed by name hash so keys can be added without losing calibration. Board-dependent analog scalings (dividers, IPROPI gain, NTC constants, pull-up values) are compile-time constants in `port/stm32g474/include/bsp.h`.

## First power-up observation list (bench, wheels off the ground, current-limited supply)

Connect the debug UART before applying power. Expected on a first successful test, in this order:

1. **Before any firmware runs** (MCU erased or held in reset): ARM_PERMIT test point low, latch cannot be set with the REARM button, bridges asleep (nSLEEP low), heater and head branches off, 5 V compute rail up, FAULT annunciator lit by the hardware watchdog path. *Stop and investigate if the latch can be set or any branch is on.*
2. **Banner** on the UART within 0.5 s of reset: `rr-chassis 0.4.0+stm32g474 RR-CHS 1.0 …`, then `reset=POWER_ON clock=HSE config=DEFAULTS boot_id=<uuid>`. *Investigate:* `clock=HSI-FALLBACK` (crystal not running), no banner (clock, UART pin, or the image is not running), a different `boot_id` appearing repeatedly (reset loop: watchdog window or supply).
3. **Status line every second**: `t=<s> mode=… latch=0 permit=… hw=… live=… sw=… flt=… di=… vbat_mV=… vmot_mV=… pres_ohm=… usb=…`. Heartbeat LED (BOOT0/LED_STAT) flashes 100 ms per second; all five annunciators light for 0.2 s at boot, one chirp.
4. With the dummy head docked, J1/J2 mated, E-stop released, covers shut: `mode=STANDBY`, `live=00000000`, READY blinking slowly, REARM lamp blinking, `pres_ohm` 4500–4900, `vbat_mV` equal to the supply within 2 %, `vmot_mV` < 1000. Expect `flt` to show `CONFIG_DEFAULTED`, `CHARGER_COMM` (LTC4162 driver disabled, register map unverified) and `TOF_BUS` (VL53L4ED driver missing) in this firmware revision — FAULT LED blinks slowly. `PMON_COMM` here means the INA228 or its identity check failed. `IOX_B` / `PERMIT_STUCK_OFF` here mean the CHAIN_END_RB read on IOX_B P17 is not working or reads low with every element closed: no arming is possible until it is fixed.
5. `mode=FAULT` at this point means: `ESTOP_DISCREPANCY` (one pole readback wrong), `IOX_A` (SPI expander or its sentinel wiring), `ADC`, `LATCH_STUCK` (latch readback high with ARM_PERMIT low — **stop: wiring fault in the chain**), `PERMIT_STUCK_ON` (CHAIN_END live with ARM_PERMIT low: U24 or PB10 — **stop**; the firmware also stops strobing, so with JP1 closed the board resets every few hundred ms) or `CHAIN_IMPLAUSIBLE` (a chain node live behind a dead one: readback tap or harness short — **stop**). Read `DIAG` over USB for the flag names.
6. Operate each chain element in turn and watch `live` change by exactly one bit and return (readbacks are node voltages: an element behind an open one is reported unknown, not as a second cause) (bit order: `MODE_NOT_RUN`=0, `ESTOP`=1, `HANDS_ON`=2, `CHARGER`=3, `HEAD_UNDOCKED`=4, `HEAD_LOOP_OPEN`=5, `HEAD_LOOP_SHORT`=6, `J1_ABSENT`=7, `LAB_KEY`=8, `BODY_BUMPER`=9, `WATCHDOG`=10, `MCU_NOT_READY`=11, `VMOT_FAULT`=12). *Investigate* any element that does not show, shows inverted, or shows together with another.
7. Scope WDG_STROBE: a 5 ms high pulse every 10 ms (one rising and one falling edge per 10 ms); WDG_OK high. During boot the port toggles WDI every ~5 ms through the init steps; check the first edge comes within 23 ms of reset release (CCR-E11) before closing JP1. Halt the CPU with the debugger: WDG_OK must drop and the latch must not be settable.
8. Press REARM: `latch=1`, `vmot_mV` ≈ `vbat_mV`, both brake relays click. With no host connected the mode becomes `PROTECTIVE_STOP` (`HOST_LINK_LOST`) after 1 s — expected. *Stop if* the latch sets with any element open, or `vmot_mV` stays low (`VMOT_FAULT`).
9. Connect USB: the device enumerates as CDC-ACM (placeholder VID:PID 1209:0001). `python3 tests/rrchs_client.py --port … STATE` needs a serial-port variant of the client; `HELLO` must return the banner's `boot_id`.
10. Run `BRAKE_TEST` (keep polling, it takes about 2.2 s): expect `passed:true`, latch drop < 50 ms, VMOT below 1 V after about 2.1 s (τ 0.8 s bleed; limit 2.5 s), probe currents ≈ 0. *Stop and investigate any failure before commanding motion.* Press REARM again.
11. First motion, wheels free, `COMMISSIONING`, 0.02 m/s: buzzer 1.5 s, then both wheels turn forward and both tick counters count **up**. *Stop if* a wheel runs away, turns the wrong way (`ENCODER_FAULT` within 0.1 s is the expected reaction to swapped encoder phases or a reversed motor), or the current reads zero while the wheel turns (IPROPI scaling).
12. Press E-stop while turning: wheels stop at once without firmware action, `mode=HW_INHIBIT hw=00000002`, and nothing restarts on release.

## Known gaps (this revision)

- No hardware test of anything. USB, ADC, timers, SPI/I²C device drivers, flash layout and the retained-RAM section are unproven; several register-level details are UNVERIFIED (listed in `bsp.c`, `pinmap.yaml`).
- VL53L4ED driver is a stub (ST's ULD could not be obtained, IB-04): on hardware all ToF sensors are OFFLINE and the firmware refuses every motion direction. INA228 (pack current, bus voltage) and INA3221 (branch currents) drivers are written against the TI datasheets but never run. The LTC4162-F driver is disabled because its register map is UNVERIFIED (IB-06): `CHARGER_COMM` stays raised, SoC and charge state are null/UNKNOWN; charge inhibit is hardware. With the selector in SERVICE the cover/plug chain nodes are dead, so on hardware SERVICE_CHARGE is recognised only once a verified charger driver reports input power (until then the mode shows HW_INHIBIT/MODE_NOT_RUN while charging; head power is forced off in hardware anyway).
- Traction-inhibit review (`docs/reviews/REVIEW_traction_inhibit.md`): C1, C2, M2 (firmware side), M3, m1, m2, m3, m4, m7 are addressed in firmware (ICD §4.6, `tests/test_review.c`). Not implemented: the boot watchdog (U23) self-test (needs a persistent test record and a guaranteed first WDI edge within 23 ms of reset — the port toggles WDI during init but the HSE start-up timeout and I²C probes are not covered, so keep JP1 open until measured and rely on the IWDG); the dynamic brake-deceleration check (row 46); supervision of IOX_B output writes (m8). The current netlist has the stage-3 R_SET diode (`chain.backfeed_ms` = 0, emulator default `cset_diode`); on a stage-2 board set 12 000 (the `PERMIT_STUCK_ON`/`CHAIN_IMPLAUSIBLE` checks then wait 12 s after the chain was last live, U24 is not verified at boot). Stage 3 (F1–F18) is implemented in firmware and emulator (ICD §4.6). Not implemented: the U23 boot watchdog test, the dynamic deceleration check, IOX_B output-write supervision; U_HOLD / U_LS / D_RUN shorts are latent (not observable).
- The ARM_PERMIT/CHAIN_END check is implemented (IB-01).
- Contract 0.4.0-draft7 enum additions `LATCH_UNEXPLAINED` / `STOP_ESCALATED` are not yet used.
- Look-sensor geometry (`look.*`) comes from `mechanical/common/frames.yaml` (checked by `tools/look_geometry.py`); `cliff.*` and `rear.*` thresholds are still placeholders.
- Stop-escalation by ARM_PERMIT withdrawal is tested for uncommanded motion; the "ramp did not finish in time" path has no fault injection in the plant.
- The brake test proves the switching elements, not braking torque.
- Motor current is not sampled synchronously with the PWM; TIM8 break input is not used.
- The boot counter erases one flash page per boot (10 k boots).
- Reply-time and control-tick execution-time budgets are not measured.

## IB-47 note: localisation error on the native emulators (analysis, no fix)

Within this package odometry is exact: ticks and `odom.t_us` are taken in the same control tick, a sample is at most 10 ms old when a `DRIVE` reply leaves, and the host-side integration of ticks matches truth to 0.03 mm (`test_drive`). A 10 ms age is 1–2 mm at 0.10–0.20 m/s, so the firmware cannot produce 12–16 mm. A transient offset of 60–100 ms between the chassis clock and the host clock would (0.20 m/s × 60–100 ms = 12–20 mm; 6–10 mm at 0.10 m/s). The emulator can create exactly that under host load: it paces simulated time against wall time and, when more than 100 ms behind, gives up catching up and resets its time base (`sim_main.c`); simulated time then stops for the length of the stall while the host clock runs on, the host's TIME fit is stepped by the stall, and DRIVE/TIME replies queued during a catch-up burst leave up to 100 ms of simulated time late. The host compares its estimate with the newest TRUTH datagram at its own wall time, so a stepped fit shows up directly as an x error until the fit is refreshed (2 s). The machine is shared with routing jobs (load averages of 11–19 on 4 cores were logged by the electronics build), which makes such stalls likely. This is a probable cause, not a proven one: re-run the scenario and log `emu_lag_us` / `emu_rebases` from TRUTH next to the error; if the error coincides with `emu_rebases` increments or `emu_lag_us` > 50 ms the cause is the emulator pacing and the remedy is on the test side (run with `--speed` < 1 on a loaded machine, or compare against truth by `chassis_us` instead of arrival time), not in the firmware.
