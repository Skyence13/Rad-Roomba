# Rad Roomba chassis firmware (motion MCU, RR-CHS 1.0)

Firmware for the STM32G474RET6 on RR-CHS-MAIN and its emulator `rr_chassis_sim`. Interface: [`interface/chassis_icd.md`](../../interface/chassis_icd.md), schema [`interface/chassis_link.schema.json`](../../interface/chassis_link.schema.json), pin map [`pinmap.yaml`](pinmap.yaml), contract requests [`CONTRACT_CHANGE_REQUESTS.md`](CONTRACT_CHANGE_REQUESTS.md).

**This is not a certified safety controller.** The hardwired traction chain (latch relay, brake relays, external window watchdog) removes traction energy without firmware. The firmware never opposes the chain, supervises and reports it, and adds a software protective-stop layer.

**Status of evidence.** The hardware-independent core is exercised on a plant model: every number below is `simulated`. The pin map is `tool-checked` against ST pin data. The STM32 image compiles and links (`tool-checked`) and **has never run on hardware**. Device details recalled from memory are marked UNVERIFIED in the sources and in `pinmap.yaml`.

## Layout

| Path | Content |
|---|---|
| `core/` | Portable C11 core: `rrch_proto.c` (protocol server), `rrch_core.c` (mode state machine, software stop latch, brake test, panel, heater, watchdog cross-checks, event log), `rrch_chain.c` (chain supervision, presence decode), `rrch_motion.c` (protective fields, drive loops, odometry, stationarity), `rrch_cfg.c` (persistent configuration), `rrch.h` (types + HAL) |
| `port/host/` | `sim.c` plant model + HAL, `sim_main.c` → `rr_chassis_sim` (TCP link, UDP environment) |
| `port/stm32g474/` | PlatformIO project: `bsp.c`, `usb_cdc.c`, `main.c`, `tof_vl53l4ed.c` (stub), generated `board_pins.h` |
| `tests/` | C unit tests on the plant, Python integration tests, `rrchs_client.py` |
| `tools/` | `check_pinmap.py` (+ extracted LQFP64 pin facts) |
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

Results observed on 2026-11-26 (`./check.sh`, exit 0): `test_chain` 245 checks, `test_state_machine` 1160 checks, `test_drive` 2464 checks, 8 Python integration tests — all passing. Target image: flash 80 648 bytes (text 80 140 + data 508) of 524 288, static RAM 23 436 bytes of 131 072 (hard-float, `-Os` PlatformIO default).

### Simulated drive performance (plant model, not measurements)

Plant: two 150:1 gearmotors (R 2.2 Ω, L 2.3 mH, k_e 1.65 V·s/rad at the wheel, effective k_t 1.0 N·m/A, reflected inertia 0.012 kg·m², 67 rpm no load ≈ 0.36 m/s), 12 kg, 104 mm wheels, 270 mm track, Coulomb + viscous friction, 4.7 Ω brake resistors, 10 kHz integration. These are datasheet-level estimates; VT-003 replaces them.

| Quantity | Simulated | Reference |
|---|---|---|
| Step to 0.10 m/s: rise 10–90 % / overshoot / steady-state error | 238 ms / 3.2 % / < 0.01 % | set-point ramp alone 267 ms (0.30 m/s²) |
| Step to 0.20 m/s | 513 ms / 1.7 % / < 0.01 % | ramp alone 533 ms |
| Stop from 0.20 m/s, controlled (0.40 m/s² ramp) | 50.6 mm, 500 ms | contract stop model 100 mm (0.15 s, 0.40 m/s², 20 mm) |
| Stop from 0.20 m/s, software protective stop (1.0 m/s² ramp) | 21.0 mm, 202 ms | 100 mm |
| Stop from 0.20 m/s, latch drop (E-stop / bumper, brake resistors, no firmware) | 14.8 mm, 182 ms | 100 mm |
| Host stops sending at 0.20 m/s (last command ttl 200 ms) | 56.8 mm and 381 ms from the moment the host went silent to rest | v·ttl + model |
| `CMD_TIMEOUT` latch after the last accepted `DRIVE` (ttl 200 ms) | 200 ms | ≤ ttl + 1 ms |
| Cliff sample at 0.20 m/s → rest | 21.8 mm | 100 mm |
| Look-ahead floor loss at 0.20 m/s → rest | 100–102 mm of the 120 mm assumed | `look.ahead_m` |
| Encoder dropout at 0.20 m/s → rest | 43.9 mm | — |
| MCU reset at 0.20 m/s → rest (latch drop) | 14.6 mm | — |
| Tick odometry vs ground truth (straight, arc, pivot, reverse) | ≤ 0.03 mm, ≤ 0.0001 rad | quantisation only; 5 % wheel slip shows as 27 mm / 0.09 rad over 0.5 m, as it must |
| Blocked wheels: current after fold-back / `STALL` latch | 2.53 A / 547 ms | limit 2.5 A, 500 ms |
| Brake test: latch drop / relays / VMOT decay | 6 ms / 13 ms / 107 ms | emulator relay model |

The latch-drop distance is shorter than the controlled stop only because the model's brake resistor and gearbox friction are generous; do not carry these numbers into a clearance argument.

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
| `tof` | `{"CLIFF_FL": 31, "REAR_C": null, "LOOK_LO": "INVALID"}` | range in mm, `null` = no target, any string = invalid. Ids as in the ICD |
| `tof_stale` | `["LOOK_RI", …]` or `["ALL"]` or `[]` | sensors that stop delivering samples (the list replaces the previous one) |
| `vbat`, `soc`, `temp_bay`, `temp_pack`, `temp_board`, `tilt_deg` | number | battery, temperatures, floor pitch |
| `enc_dropout`, `block` | `"L"`, `"R"`, `"BOTH"`, `"NONE"` | encoder stops counting / wheel mechanically blocked |
| `slip` | `[left, right]` 0…0.95 | wheel slip fraction |
| `usb_stall`, `usb_down` | bool | host bytes are held back (delivered late on release) / USB reports not configured |
| `imu_off`, `iox_fail`, `latch_weld`, `estop_a_stuck`, `nv_fail`, `efuse_fault` (bit mask) | | sensor and hardware faults |
| `freeze_control`, `freeze_supervisor`, `freeze_background` | bool | stop one firmware context (watchdog tests) |
| `mcu_reset` | `"PIN"`, `"WATCHDOG"`, `"SOFTWARE"`, `"BROWNOUT"`, `"POWER_ON"` | reset the MCU now (plant keeps moving/braking) |

The emulator contains the hardwired chain: latch relay with 5 ms release / 10 ms pull-in, brake relays 8 ms, VMOT decay 40 ms, a window watchdog (trip if no strobe for 35 ms or two strobes within 3 ms, MCU reset 50 ms later).

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
| PC13 | 2 | `WDG_OK_RB` | GPIO | GPIO | in | Watchdog output state as seen by the chain: HIGH = watchdog satisfied. |
| PC14 | 3 | `BRAKE_L_RB` | GPIO | GPIO | in | Left DPDT brake relay: HIGH = motor connected to bridge (relay energised), LOW = motor across brake resisto... |
| PC15 | 4 | `BRAKE_R_RB` | GPIO | GPIO | in | Right brake relay, as above. |
| PF0 | 5 | `OSC_IN` | RCC_OSC_IN | ANALOG | in | HSE crystal. |
| PF1 | 6 | `OSC_OUT` | RCC_OSC_OUT | ANALOG | out |  |
| PC0 | 8 | `HEAD_PRES_ID` | ADC1_IN6 | ANALOG | in | J1 pin 7. 4.70 kOhm 0.1% pull-up to VREF+, 1 kOhm series + 10 nF + TVS at the connector. Code resistor retu... |
| PC1 | 9 | `HEAD_LOOP_SENSE` | ADC1_IN7 | ANALOG | in | Analog copy of the J1 5/6 interlock-loop measurement (loop resistance), diverse from the hardware window co... |
| PC2 | 10 | `NTC_BAY` | ADC1_IN8 | ANALOG | in | 10 kOhm B3435-class NTC in the battery bay air/plate, 10.0 kOhm 0.1% pull-up to VREF+. Used for heater regu... |
| PC3 | 11 | `NTC_PACK` | ADC1_IN9 | ANALOG | in | Second NTC on the pack surface (heater plausibility + battery.temp_c[1]). The charger measures its own pack... |
| PA0 | 12 | `IPROPI_L` | ADC1_IN1 | ANALOG | in | DRV8874-class IPROPI left bridge. RIPROPI to AGND sized for 3.0 V at 6.5 A; RC 1 kOhm/10 nF at pin. Scale i... |
| PA1 | 13 | `IPROPI_R` | ADC2_IN2 | ANALOG | in | As IPROPI_L, right bridge. ADC1+ADC2 dual simultaneous sampling at PWM centre. |
| PA2 | 14 | `VMOT_SENSE` | ADC1_IN3 | ANALOG | in | VMOT (after latch relay) divider 47k/10k (16.0 V -> 2.81 V), 100 nF. Safety-relevant readback: must read ~0... |
| PA3 | 17 | `VBAT_SENSE` | ADC1_IN4 | ANALOG | in | VBAT_SW divider 47k/10k. Fast brown-out logging and I2C-independent low-battery check (INA228 is the accura... |
| PA4 | 18 | `IMU_CS_ACC_N` | GPIO | GPIO | out | high via 10k pull-up. BMI088 accelerometer CSB1. |
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
| PB12 | 34 | `ESTOP_A_RB` | GPIO | GPIO | in | E-stop pole A (high side of latch coil) closed = HIGH. Opto/level-shifted, 10k pull-down, 1 ms RC. |
| PB13 | 35 | `ESTOP_B_RB` | GPIO | GPIO | in | E-stop pole B (low side). A/B disagreement > 100 ms is reported as a fault. |
| PB14 | 36 | `HEAD_HTR_EN` | GPIO | GPIO | out | low via 10k pull-down (off). J1 3/4 heater branch eFuse enable. |
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
| PD2 | 55 | `HW_LATCH_RB` | GPIO | GPIO | in | Latch relay state (auxiliary contact or coil-voltage opto): HIGH = latched. Also usable as TIM8 break input... |
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
| GPA0 | `MODE_RUN_RB` | Master switch in RUN = HIGH |
| GPA1 | `HANDS_ON_RB` | HANDS-ON inhibit NOT pressed (contact closed) = HIGH |
| GPA2 | `CHG_COVER_RB` | Charge inlet cover shut = HIGH |
| GPA3 | `CHG_PLUG_LINK_RB` | Charge plug link ABSENT (chain contact closed) = HIGH |
| GPA4 | `HEAD_DOCK_RB` | Dock switch: head seated and latched = HIGH |
| GPA5 | `HEAD_LOOP_OK_RB` | Window comparator: loop 0.6-1.6 kOhm = HIGH |
| GPA6 | `HEAD_LOOP_SHORT_RB` | Comparator: loop below window (short) = HIGH |
| GPA7 | `LAB_KEY_N_RB` | Hardware PRES_ID comparator says 'no LAB resistor' (chain contact closed) = HIGH |
| GPB0 | `BODY_BUMPER_L_RB` | Left/rear-left body bumper NC switch closed = HIGH |
| GPB1 | `BODY_BUMPER_R_RB` | Right/rear-right body bumper closed = HIGH |
| GPB2 | `REARM_BTN` | Local REARM/Start pressed = HIGH (second, isolated contact of the button or opto across the set path; the first contact is in the latch set path) |
| GPB3 | `PAUSE_BTN` | Local PAUSE/Stop pressed = HIGH |
| GPB4 | `DRV_L_NFAULT` | LOW = left bridge fault (open drain, 10k pull-up) |
| GPB5 | `DRV_R_NFAULT` | LOW = right bridge fault |
| GPB6 | `BUS_CLAMP_ACTIVE` | Brake chopper / bus clamp conducting = HIGH |
| GPB7 | `SENTINEL` | Wired to the WDG_STROBE net (PB11): firmware checks that this bit follows the strobe it generates, which proves the expander read path is live. |

**IOX_B** - TCA9535 / PCA9535 class (16-bit, I2C) on I2C_SYS, address 0x20

| Expander pin | Signal | Note |
|---|---|---|
| P00 | `LED_READY` | Annunciator, active high via driver |
| P01 | `LED_MOVING` |  |
| P02 | `LED_HOLD` |  |
| P03 | `LED_FAULT` | Additionally OR-ed in hardware with NOT WDG_OK so a dead MCU shows FAULT |
| P04 | `LED_CHARGE` |  |
| P05 | `LAMP_REARM` | REARM button illumination |
| P06 | `LAMP_PAUSE` |  |
| P07 | `LED_STAT2` | Second on-board status LED (protocol activity) |
| P10 | `HEAD_PWR_EN` | default off (pull-down). J1 1/2 eFuse enable. Forced off by firmware in SERVICE_CHARGE; recommend also gating in hardware with the charger-present signal. |
| P11 | `V12_LIDAR_EN` | default on (pull-up). Holds across MCU reset |
| P12 | `V5_CM5_OFF_REQ` | default not asserted (pull-down) = rail ON. Only asserted for a deliberate compute power cycle; the 5 V rail stays up across MCU resets and with the MCU unprogrammed. |
| P13 | `TOF_XSHUT_CLIFF` | default low (sensors held in reset). Shared XSHUT of the 4 cliff sensors |
| P14 | `TOF_XSHUT_LOOK` | default low. Shared XSHUT of the 4 look-ahead sensors |
| P15 | `TOF_XSHUT_REAR` | default low. Shared XSHUT of the 3 rear sensors |
| P16 | `TOF_MUX_NRST` | default low. Reset of both TCA9548A (bus recovery) |
| P17 | `SPARE_OUT` |  |

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

**ToF sensors** (I2C_TOF, two TCA9548A)

| Index | Id | Mux | Channel | XSHUT group | Role |
|---:|---|---:|---:|---|---|
| 0 | `CLIFF_FL` | 0 | 0 | TOF_XSHUT_CLIFF | downward cliff, front-left wheel/head corner |
| 1 | `CLIFF_FR` | 1 | 0 | TOF_XSHUT_CLIFF | downward cliff, front-right |
| 2 | `CLIFF_RL` | 0 | 1 | TOF_XSHUT_CLIFF | downward cliff, rear-left |
| 3 | `CLIFF_RR` | 1 | 1 | TOF_XSHUT_CLIFF | downward cliff, rear-right |
| 4 | `LOOK_LO` | 0 | 2 | TOF_XSHUT_LOOK | oblique look-ahead, left outer |
| 5 | `LOOK_LI` | 1 | 2 | TOF_XSHUT_LOOK | oblique look-ahead, left inner (pair partner of LOOK_LO) |
| 6 | `LOOK_RI` | 0 | 3 | TOF_XSHUT_LOOK | oblique look-ahead, right inner |
| 7 | `LOOK_RO` | 1 | 3 | TOF_XSHUT_LOOK | oblique look-ahead, right outer (pair partner of LOOK_RI) |
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
4. With the dummy head docked, J1/J2 mated, E-stop released, covers shut: `mode=STANDBY`, `live=00000000`, READY blinking slowly, REARM lamp blinking, `pres_ohm` 4500–4900, `vbat_mV` equal to the supply within 2 %, `vmot_mV` < 1000. Expect `flt` to show `CONFIG_DEFAULTED`, `CHARGER_COMM`, `PMON_COMM`, `TOF_BUS` in this firmware revision (drivers not implemented) — FAULT LED blinks slowly.
5. `mode=FAULT` at this point means: `ESTOP_DISCREPANCY` (one pole readback wrong), `IOX_A` (SPI expander or its sentinel wiring), `ADC`, or `LATCH_STUCK` (latch readback high with ARM_PERMIT low — **stop: wiring fault in the chain**). Read `DIAG` over USB for the flag names.
6. Operate each chain element in turn and watch `live` change by exactly one bit and return (bit order: `MODE_NOT_RUN`=0, `ESTOP`=1, `HANDS_ON`=2, `CHARGER`=3, `HEAD_UNDOCKED`=4, `HEAD_LOOP_OPEN`=5, `HEAD_LOOP_SHORT`=6, `J1_ABSENT`=7, `LAB_KEY`=8, `BODY_BUMPER`=9, `WATCHDOG`=10, `MCU_NOT_READY`=11, `VMOT_FAULT`=12). *Investigate* any element that does not show, shows inverted, or shows together with another.
7. Scope WDG_STROBE: one edge every 10 ms; WDG_OK high. Halt the CPU with the debugger: WDG_OK must drop and the latch must not be settable.
8. Press REARM: `latch=1`, `vmot_mV` ≈ `vbat_mV`, both brake relays click. With no host connected the mode becomes `PROTECTIVE_STOP` (`HOST_LINK_LOST`) after 1 s — expected. *Stop if* the latch sets with any element open, or `vmot_mV` stays low (`VMOT_FAULT`).
9. Connect USB: the device enumerates as CDC-ACM (placeholder VID:PID 1209:0001). `python3 tests/rrchs_client.py --port … STATE` needs a serial-port variant of the client; `HELLO` must return the banner's `boot_id`.
10. Run `BRAKE_TEST`: expect `passed:true`, latch drop < 50 ms, VMOT below 1 V within the configured time, probe currents ≈ 0. *Stop and investigate any failure before commanding motion.* Press REARM again.
11. First motion, wheels free, `COMMISSIONING`, 0.02 m/s: buzzer 1.5 s, then both wheels turn forward and both tick counters count **up**. *Stop if* a wheel runs away, turns the wrong way (`ENCODER_FAULT` within 0.1 s is the expected reaction to swapped encoder phases or a reversed motor), or the current reads zero while the wheel turns (IPROPI scaling).
12. Press E-stop while turning: wheels stop at once without firmware action, `mode=HW_INHIBIT hw=00000002`, and nothing restarts on release.

## Known gaps (this revision)

- No hardware test of anything. USB, ADC, timers, SPI/I²C device drivers, flash layout and the retained-RAM section are unproven; several register-level details are UNVERIFIED (listed in `bsp.c`, `pinmap.yaml`).
- VL53L4ED driver is a stub (ST's ULD could not be obtained): on hardware all ToF sensors are OFFLINE and the firmware refuses every motion direction. Charger, pack monitor and branch monitor drivers are not written (battery voltage comes from the ADC; SoC, charge state and branch currents are null).
- Protective fields use placeholder geometry (`look.*`, `cliff.*`, `rear.*`); the sensor mounting is not final.
- Stop-escalation by ARM_PERMIT withdrawal is tested for uncommanded motion; the "ramp did not finish in time" path has no fault injection in the plant.
- The brake test proves the switching elements, not braking torque.
- Motor current is not sampled synchronously with the PWM; TIM8 break input is not used.
- The boot counter erases one flash page per boot (10 k boots).
- Reply-time and control-tick execution-time budgets are not measured.
