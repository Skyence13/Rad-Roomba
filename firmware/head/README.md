# Rad Roomba detector-head firmware (`firmware/head`)

Firmware of the head MCU on board **RR-HEAD-ACQ** (STM32G474VET6, DEC-037: event capture by MCU
timers and discrete latches, no FPGA) and the **emulated head** `rr_head_sim`, which is the same
core compiled for Linux. It speaks head protocol 2.0 (`interface/head_icd.md`) plus the additive
0.4 ops (`interface/head_icd_addendum_0.4.md`).

**Evidence status.** Everything here is `tool-checked` (compiled, unit-tested, run against the
baseline host tools on the emulator) or `calculated`. **Nothing has run on hardware**: the STM32
image is compiled and linked only. Statements recalled from data sheets or reference manuals that
could not be checked on the build host are marked UNVERIFIED where they occur.

## Layout

| Path | Content |
|---|---|
| `../common/` | Portable C11 library shared with the chassis firmware: framing, CRC-32, JSON, envelope + reply cache, SHA-256, base64, UUID, ring buffer. Own README. |
| `core/rrh_core.c` | Protocol 2.0 state machine: HELLO, GET_DESCRIPTOR, BIND, TIME, SYNC, ARM, READ, DISARM; binding rules; reply cache. Read this file to audit binding/unbinding. |
| `core/rrh_acq.c` | `head_gate_record` → ACQ 2.0 frame mapping (null + flag rules), 160-frame buffer, sync-quality records, ACQ/DIAG serialisation. |
| `core/rrh_evtcap.c` | Event capture logic (classification, counters, measured live time, gate snapshots). Pure logic, used by the STM32 port and by host tests. |
| `core/rrh_setup.c` | Setup (thresholds, trims, bias law, heater law), `setup_id` hash, descriptor builder (Rev E concept geometry from `contract.yaml`). |
| `core/rrh_control.c` | Health and fault latching, bias temperature compensation, gate-aligned heater control. |
| `core/rrh_board.c/.h` | Board constants with circuit designators (resistors of `circuit.py`) and the pure conversions derived from them: bias law, monitor scales, anode current, NTC tables, straps. Checked against the circuit by `tools/check_circuit.py`. |
| `core/rrh_eng.c` | Additive ops: DIAG, STATUS, FAULT_CLEAR, ENG_FAULT, ENG_SETUP_GET/SET, ENG_WAVE_ARM/READ. |
| `hal/rrh_hal.h` | The only boundary between core and hardware (about 20 functions). |
| `port/host/` | `rr_head_sim`: HAL on a seeded Poisson source + sockets + fault injection. |
| `port/stm32g474/` | Target port: clocks, TIM2/TIM5 capture + 100 kHz service interrupt, RS-485 USART, DACs, ADC, I2C, flash, IWDG. |
| `tests/` | `test_core.c`, `test_evtcap.c` (host unit tests), `test_sim_interop.py` + `headsim.py` (emulator driven by the baseline tools). |
| `tools/` | `check_circuit.py` (constants and pins against `electronics/head_acq/design/circuit.py`), `check_pinmap.py`, `gen_pinmap.py`, ST pin-database subset, PlatformIO helper. |
| `pinmap.yaml` | Pin map proposal for the electronics lead (source of the table below). |
| `check.sh` | Builds and runs everything; non-zero exit on any failure. |

## Toolchain (pinned)

| Tool | Version used | Install |
|---|---|---|
| Host compiler | gcc 13.3.0 (Ubuntu 24.04) | `apt install build-essential` |
| CMake / Ninja | 3.28 / 1.11 (any CMake ≥ 3.16) | `apt install cmake ninja-build` |
| Python | 3.13 (≥ 3.9) with `jsonschema` ≥ 4.18, `PyYAML` | `pip install jsonschema pyyaml` |
| PlatformIO Core | 6.x | `pip install platformio` |
| PlatformIO platform | `platformio/ststm32@19.4.0` | fetched by `pio run` |
| ARM toolchain | `toolchain-gccarmnoneeabi@1.120301.0` (GCC 12.3.1) | fetched by `pio run` |
| CMSIS | `framework-cmsis@2.50501.200527`, `framework-cmsis-stm32g4@1.2.5`, `tool-ldscripts-ststm32@0.2.0` | fetched by `pio run` |

The versions are fixed in `platformio.ini`; the registry (`registry.platformio.org`,
`dl.registry.platformio.org`) must be reachable for the first target build.

## Build and test

```sh
firmware/head/check.sh               # everything (host build + all tests + STM32 image)
firmware/head/check.sh --no-target   # host only

# by hand
cmake -S firmware/head -B firmware/head/build/host -G Ninja      # ASan + UBSan, -Werror -Wconversion
cmake --build firmware/head/build/host -j2
ctest --test-dir firmware/head/build/host --output-on-failure    # 6 test programs
cd firmware/head && pio run -e rr_head_acq                       # .pio/build/rr_head_acq/firmware.{elf,bin}
```

Tests (all on the host):

- `common_unit`, `common_python_interop` — see `../common/README.md`.
- `head_core_unit` (`tests/test_core.c`, mock HAL): unbound answers, handshake rules, reset →
  fresh boot id + UNBOUND, reply cache, garbage on the link, frame mapping and every null rule,
  GAP/EMPTY and sequence continuity across DISARM/ARM, setup change invalidates the binding,
  LOCKED/HOLDOVER/UNSYNCED, heater control and fault latches, bias compensation, lost/bad gates.
- `head_board_unit` (`tests/test_board.c`): every conversion against an independent floating-point evaluation of the circuit equation; the budget's strap table (HV_RAW 37.1 / 49.1 / 52.7 / 65.1 V, OVP 31.5 / 42.8 / 47.5 / 60.6 V) reproduced from the resistor values; NTC tables within 0.25 degC.
- `head_evtcap_unit` (`tests/test_evtcap.c`): single events of each class, non-retriggering,
  acceptance window, forced clear, event straddling a gate boundary, Poisson rate sweep
  10 – 20000 s⁻¹, service-interrupt jitter, heater switching on boundaries, stop, FIFO overflow,
  pulse-width histogram (present and absent).
  Every gate record is compared exactly with an independent hardware model. Added for IB-18 and
  the review questions: afterglow hold, idle ALPHA latch (including the lagging-capture case),
  a latch clear whose blind interval crosses a gate boundary, services late by 37 us / 2.5 gates /
  2.9 gates, chains held by 0.6 / 0.9 / 2.3 ms tails, and the rate sweep repeated with the 300 us hold, the alpha width rule (bright beta, boundary tick, unmeasured width, lagging falling-edge capture).
- `head_sim_interop` (`tests/test_sim_interop.py`): launches `rr_head_sim` and drives it with the
  unmodified `interface/wire_codec.py`, `head_discovery.py`, `check_frames.py`: byte-exact
  reproduction of the 0.3 example handshake, descriptor chunking + SHA-256, BIND, TIME/SYNC, ARM,
  READ stream against the baseline schema, retry idempotence, CRC error retry, GAP with exact
  oldest/newest, EMPTY, UNBOUND after reset, reset between HELLO and BIND, stale BIND, head swap,
  null channel + flag, measured zero, counts conservation, equal gates, live ≤ span, determinism,
  real-clock mode, PTY, clean SIGTERM.

## Target image

| | |
|---|---|
| MCU | STM32G474VET6, 512 kB flash, 128 kB RAM (SRAM1 + SRAM2 + CCM mapped contiguously at 0x2000 0000 by the ST linker script) |
| Clock | 24 MHz TCXO → HSE bypass → PLL → 144 MHz SYSCLK (falls back to HSI16 and latches health `SOURCE` if the TCXO is absent) |
| Size (`rr_head_acq`, `-Os`, GCC 12.3.1) | flash 43 024 bytes (8.2 %), static RAM 97 460 bytes (74.4 %) — tool-checked with `arm-none-eabi-size` (firmware 0.5.2) |

Memory map (default ST script `STM32G474RETX_FLASH.ld`; the RE and VE parts share die and memory):

| Region | Address | Use |
|---|---|---|
| Flash | 0x0800 0000 … | vector table, code, constants (image ends near 0x0800 8AC0) |
| Flash, last 2 kB | 0x0807 F800 – 0x0807 FFFF | persisted setup (`ENG_SETUP_SET {"persist":true}`): magic, length, image + CRC-32. `bsp_nv_save()` refuses to write if the program image reaches this page. Page numbering for erase is recalled from RM0440 (UNVERIFIED). |
| RAM | 0x2000 0000 – 0x2001 FFFF | `.data/.bss` 86 kB of which `rrh_core_t` about 77 kB (160 retained frames with their DIAG data about 51 kB, 8 kB receive buffer, 4 kB transmit/reply cache, 4 kB descriptor, 4 kB sync records); stack from the top |

Interrupts: `USART1` (priority 0: byte receive, LF timestamp, transmit) and `TIM6` (priority 1:
100 kHz event-capture service, gate boundaries, heater switching, release of scheduled replies).
Everything else runs in the main loop. The independent watchdog (≈ 1 s) is serviced by
`rrh_core_poll()`; the reset cause is captured at boot and reported by `STATUS`.

There is no bitstream any more (DEC-037): the image is a single artefact, and `setup_id` is the
hash of the setup image and the firmware version only.

### Flash and debug

SWD on PA13/PA14 + NRST (PG10); BOOT0 (PB8) strapped low. SWO is not available (PB3 is a BUSY
capture input). None of the commands below has been run against hardware.

```sh
cd firmware/head
pio run -e rr_head_acq -t upload            # ST-LINK/V2 or V3 via OpenOCD (upload_protocol = stlink)
# or, with the ST tool:  STM32_Programmer_CLI -c port=SWD -w .pio/build/rr_head_acq/firmware.bin 0x08000000 -v -rst
pio debug -e rr_head_acq --interface=gdb    # GDB through the ST-LINK
```

Debug console: UART4 on PC10 (TX) / PC11 (RX), 115200 8N1: prints the firmware version and the
boot id at start-up.

**NUCLEO-G474RE bring-up path** (64-pin part, protocol/link/housekeeping only): build
`-e nucleo_bringup` (`-DRRH_BOARD_NUCLEO`: HSE crystal instead of bypass), flash through the
on-board ST-LINK (`pio run -e nucleo_bringup -t upload`), connect a 3.3 V RS-485 transceiver to
PA9 (DI), PA10 (RO), PA12 (DE) and a USB-UART to PC10/PC11. Ports D and E do not exist on that
package: the latch read-backs read zero, so the start-up latch self-test fails and health shows
`SOURCE` — expected there. Jumper a pulse generator to PA15 (BUSY_F0) to see beta counts.
Nucleo solder-bridge details are not checked (UNVERIFIED).

## Event capture on the target

Per chain: BUSY latch → 32-bit timer input capture (TIM2 CH1-4 floor, TIM5 CH1-4 reference, both
at 144 MHz = 6.94 ns per tick). The 100 kHz TIM6 interrupt reads the capture flags, GPIOD and
GPIOE once, calls `rrh_evtcap_service()`, which for every chain that has been BUSY for ≥ 4 µs and
whose LLD comparator is low again classifies it, asks the port to pulse CLR and takes the timer
reading of that moment as the end of the event's dead time. Gate boundaries are computed
arithmetically (`g0 + n · gate_ticks`), busy intervals are split at them exactly, and an event
is counted in the gate that contains its clear time. A chain BUSY for more than 1 ms, or with its
comparator high while the latch is clear, is flagged saturated (→ `SATURATED`, null counts).

Afterglow hold and idle latches (IB-18, firmware 0.5): an event classified alpha is not cleared at
once. The chain stays BUSY for `afterglow.alpha_hold_us` (default 300 us since 0.5.1, setup member, 0 = off, at most
500) counted from the service that found it ready, and is cleared by the first service after that with the
comparator low. Class and pulse width are fixed when the event first becomes ready; the hold is inside
[captured start, clear) and therefore inside the measured busy time, so live time stays exact (rate
sweep below). An ALPHA latch found set on an idle floor chain is cleared after two consecutive services
(one is not enough: the capture flag of a real event can lag the latch read-back by one service) and
counted per gate (`alpha_idle_clears`, DIAG); its blind CLR interval is booked as dead time.

Pulse width (optional engineering data): the raw, unlatched LLD comparator outputs are also on
capture channels (TIM4 CH1-4 floor, TIM3 CH1-4 reference, falling edge). Falling capture minus
BUSY start is the time over threshold of the triggering pulse (6.94 ns resolution, valid up to
about 340 µs). `rrh_evtcap` puts it into a 4-bin histogram per chain and gate (edges 150 ns,
400 ns, 2 µs) that `DIAG` reports; classification stays amplitude-based and does not use it. A
port that does not provide widths (`width_mask` 0) simply produces no histogram.

Measured on the host model (`head_evtcap_unit`, simulated, 8 chains):

| true rate s⁻¹ | counted s⁻¹ | live-time-corrected s⁻¹ | dead |
|---:|---:|---:|---:|
| 10 | 10.01 | 10.01 | 0.010 % |
| 100 | 100.41 | 100.51 | 0.098 % |
| 1000 | 990.15 | 999.87 | 0.972 % |
| 5000 | 4772.5 | 5006.4 | 4.67 % |
| 20000 | 16738.6 | 19994.2 | 16.3 % |

With the 300 us hold (default, 5 % alpha events on the floor chains in the model) the corrected rate stays
within the same tolerance at every rate (10 ... 20000 s⁻¹: 10.01, 100.48, 1000.12, 5005.7, 19979 s⁻¹; dead 24.8 % at 20000 s⁻¹ against
16.3 % without the hold; simulated). i.e. about 9.7 µs of measured dead time per event without the hold. With ±6 µs service jitter and 0.1 % of the
services 50 µs late the corrected rate stays unbiased (5003 s⁻¹ at 5000 s⁻¹); only the dead time
grows. Deviation from the contract wording: the gate snapshot is taken by the service interrupt
that follows the boundary (≤ 10 µs later) with exact arithmetic splitting, not by a separate
compare interrupt; the result is the same and one interrupt source is saved.

## Hardware mapping (generated from `pinmap.yaml`)

`tools/check_pinmap.py` verifies every pin number, alternate function and ADC channel against
ST's open pin database (`tools/stm32g474ve_lqfp100_pindb.json`); `tools/gen_pinmap.py` writes this
table and `port/stm32g474/rrh_pins.h`.

<!-- BEGIN PINMAP (generated by tools/gen_pinmap.py) -->
| LQFP100 | Pin | Signal | Peripheral | AF | Dir | Electrical note |
|---:|---|---|---|---|---|---|
| 1 | PE2 | `LLD_R0` | TIM3 | 2 | in | RAW REF_LLD comparator output, reference lane 0, on TIM3_CH1 input capture (as LLD_F): time over threshold; level read through GPIOE->IDR. 100 k ext PD. |
| 2 | PE3 | `LLD_R1` | TIM3 | 2 | in | RAW REF_LLD comparator output, reference lane 1, on TIM3_CH2 input capture (as LLD_F): time over threshold; level read through GPIOE->IDR. 100 k ext PD. |
| 3 | PE4 | `LLD_R2` | TIM3 | 2 | in | RAW REF_LLD comparator output, reference lane 2, on TIM3_CH3 input capture (as LLD_F): time over threshold; level read through GPIOE->IDR. 100 k ext PD. |
| 4 | PE5 | `LLD_R3` | TIM3 | 2 | in | RAW REF_LLD comparator output, reference lane 3, on TIM3_CH4 input capture (as LLD_F): time over threshold; level read through GPIOE->IDR. 100 k ext PD. |
| 5 | PE6 | `CLR_F2_N` | GPIO | - | out | Clear of all three latches of floor lane 2, active low pulse (>= 20 ns, firmware gives ~100 ns). 10 k ext PD: latches are held cleared (chain idle, BUSY low) while the MCU is in reset. |
| 6 | VBAT | `VBAT` | power | - | power | Tie to +3V3 (no backup domain use). |
| 7 | PC13 | `BUMP_ZONE_F_N` | GPIO | - | in | Front zone auxiliary contact to GND, active low, 10 k ext PU + 1 k series + 100 nF + TVS. Backup-domain pin: input only. |
| 8 | PC14 | `BUMP_ZONE_L_N` | GPIO | - | in | Left zone, as front. Backup-domain pin: input only. |
| 9 | PC15 | `BUMP_ZONE_R_N` | GPIO | - | in | Right zone, as front. Backup-domain pin: input only. |
| 10 | PF9 | `PULSER_A1` | GPIO | - | out | Test-pulse channel select bit 1. 100 k ext PD. |
| 11 | PF10 | `PULSER_A2` | GPIO | - | out | Test-pulse channel select bit 2. 100 k ext PD. |
| 12 | PF0 | `HSE_IN_24M` | RCC | - | in | RCC_OSC_IN, HSE bypass, from the 24 MHz TCXO. |
| 13 | PF1 | `SYNC_IN` | GPIO | - | in | RESERVED hardware time-pulse input (J2 pins 5/6 via the DNP ISO7710 U2503). Not used by firmware 0.5; configured as an input with the board's 100 k pull-down (R2414). Usable as GPIO only because HSE runs in bypass mode. |
| 14 | PG10 | `NRST` | SYS | - | bidir | 100 nF to GND, to SWD header pin 10. No other driver. |
| 15 | PC0 | `NTC_SIPM0` | ADC1 IN6 | - | analog | 10 k B3435-class NTC at lane 0 SiPMs to AGND, 10.0 k 0.1 % to VREF_ADC, 100 nF. |
| 16 | PC1 | `NTC_SIPM1` | ADC1 IN7 | - | analog | 10 k B3435-class NTC at lane 1 SiPMs to AGND, 10.0 k 0.1 % to VREF_ADC, 100 nF. |
| 17 | PC2 | `NTC_SIPM2` | ADC1 IN8 | - | analog | 10 k B3435-class NTC at lane 2 SiPMs to AGND, 10.0 k 0.1 % to VREF_ADC, 100 nF. |
| 18 | PC3 | `NTC_SIPM3` | ADC1 IN9 | - | analog | 10 k B3435-class NTC at lane 3 SiPMs to AGND, 10.0 k 0.1 % to VREF_ADC, 100 nF. |
| 19 | PF2 | `PULSER_A0` | GPIO | - | out | Test-pulse channel select bit 0 (74LVC138 U2702 A0): pulsed chain = PULSER_A[2:0], 0-3 = F0-F3, 4-7 = R0-R3. 100 k ext PD (default F0). |
| 20 | PA0 | `BUSY_R0` | TIM5 | 2 | in | TIM5_CH1 input capture, rising edge. Q of the REF_LLD (BUSY) latch of reference lane 0. 100 k ext PD. |
| 21 | PA1 | `BUSY_R1` | TIM5 | 2 | in | TIM5_CH2 input capture, rising edge. Q of the REF_LLD (BUSY) latch of reference lane 1. 100 k ext PD. |
| 22 | PA2 | `BIAS_VMON` | ADC1 IN3 | - | analog | SiPM bias voltage BIAS_VMON (circuit: R2217 + R2218 = 2 x 4.99 M, R2219 = 412 k, 1:25.2233 = 2.478 V at 62.5 V), 1 k series R2220, 10 nF at the pin, source < 10 k. The divider top resistors are 1 % parts. |
| 23 | VSS | `GND` | power | - | power | Also pins 48, 63, 74, 99. |
| 24 | VDD | `+3V3` | power | - | power | Also pins 49, 64, 75, 100. 100 nF each + 4.7 uF bulk. |
| 25 | PA3 | `BIAS_IMON` | ADC1 IN4 | - | analog | Total bias current BIAS_IMON = 0.8 x I x R2206 (10 k) = 8.0 mV per uA, 250 uA at 2.0 V (budget 5.1); includes the two bias dividers (about 30 uA at 60 V). 1 k series R2207. |
| 26 | PA4 | `DAC_CS0_N` | GPIO | - | out | U_DAC0 /CS. 10 k ext PU. |
| 27 | PA5 | `DAC_SCK` | SPI1 | 5 | out | SPI1_SCK. DACs are written only while disarmed (and HV set-point between gates). |
| 28 | PA6 | `DAC_MISO` | SPI1 | 5 | in | SPI1_MISO, DAC SDO wired-OR (SDO high-Z when /CS is high; DAC60508 behaviour UNVERIFIED), 100 k ext PU. |
| 29 | PA7 | `DAC_MOSI` | SPI1 | 5 | out | SPI1_MOSI. |
| 30 | PC4 | `MON_ADC` | ADC2 IN5 | - | analog | Buffered monitor output (ADC2_IN5). With all lane muxes off (MON_LANE_EN = 0, always) it reads 0.300 V + V(FRAME)/2 (stage 3 S3-03: R2702 1 M to VBL, R2802 1 M to FRAME): frame-potential check. Anti-alias RC ~ 1 MHz. |
| 31 | PC5 | `DAC_CS1_N` | GPIO | - | out | U_DAC1 /CS. 10 k ext PU. |
| 32 | PB0 | `NTC_HTR` | ADC1 IN15 | - | analog | Heater-plate NTC (same network). Open/short detection in firmware. |
| 33 | PB1 | `VIN_MON` | ADC1 IN12 | - | analog | HEAD_PWR after input protection, divider 1:6.6 (19.8 V full scale at 3.0 V reference), 100 nF. |
| 34 | PB2 | `DAC_CS2_N` | GPIO | - | out | U_DAC2 /CS. 10 k ext PU. |
| 35 | VSSA | `AGND` | power | - | power | Star point to GND at the MCU. |
| 36 | VREF+ | `VREF_ADC` | power | - | power | External 3.0 V reference preferred; else VDDA through 0 R. 1 uF + 100 nF. |
| 37 | VDDA | `+3V3A` | power | - | power | Filtered from +3V3 (ferrite + 1 uF + 10 nF). |
| 38 | PE7 | `CLR_F3_N` | GPIO | - | out | Clear of all three latches of floor lane 3, active low pulse (>= 20 ns, firmware gives ~100 ns). 10 k ext PD: latches are held cleared (chain idle, BUSY low) while the MCU is in reset. |
| 39 | PE8 | `BUSY_R2` | TIM5 | 1 | in | TIM5_CH3 input capture, rising edge. Q of the REF_LLD (BUSY) latch of reference lane 2. 100 k ext PD. |
| 40 | PE9 | `BUSY_R3` | TIM5 | 1 | in | TIM5_CH4 input capture, rising edge. Q of the REF_LLD (BUSY) latch of reference lane 3. 100 k ext PD. |
| 41 | PE10 | `CLR_R0_N` | GPIO | - | out | Clear of both latches of reference lane 0, active low pulse. 10 k ext PD. All eight CLR lines are on GPIOE so one BSRR write can clear several chains. |
| 42 | PE11 | `CLR_R1_N` | GPIO | - | out | Clear of both latches of reference lane 1, active low pulse. 10 k ext PD. All eight CLR lines are on GPIOE so one BSRR write can clear several chains. |
| 43 | PE12 | `CLR_R2_N` | GPIO | - | out | Clear of both latches of reference lane 2, active low pulse. 10 k ext PD. All eight CLR lines are on GPIOE so one BSRR write can clear several chains. |
| 44 | PE13 | `CLR_R3_N` | GPIO | - | out | Clear of both latches of reference lane 3, active low pulse. 10 k ext PD. All eight CLR lines are on GPIOE so one BSRR write can clear several chains. |
| 45 | PE14 | `LATCH_TEST` | GPIO | - | out | Latch self-test: a rising edge clocks every latch through an OR gate in each clock path (no analog signal involved). Idle low, 10 k ext PD. |
| 46 | PE15 | `IMON_CH` | ADC4 IN2 | - | analog | Per-chain anode current monitor: V(TRIMDRV) of the chain selected by MON_MUX_A[2:0] through U2703 (TMUX1108), 10 k R108 + 100 nF C2704 (1 ms), unity buffer U2306B, 1 k R2701 + 10 nF C2705. I = (V_trim - V) / 4.99 k (R105). 147 nA per LSB at 3.0 V. |
| 47 | PB10 | `BUSY_F2` | TIM2 | 1 | in | TIM2_CH3 input capture, rising edge. Q of the BETA_LLD (BUSY) latch of floor lane 2. 100 k ext PD so a missing latch supply reads idle. |
| 50 | PB11 | `BUSY_F3` | TIM2 | 1 | in | TIM2_CH4 input capture, rising edge. Q of the BETA_LLD (BUSY) latch of floor lane 3. 100 k ext PD so a missing latch supply reads idle. |
| 51 | PB12 | `HTR_SENSE` | ADC1 IN11 | - | analog | Heater current: R2601 10 mohm shunt x INA180A2 (gain 50) = 0.5 V/A, 1 k R2602 + 100 nF C2603 (stage 3: over-current cut-off in firmware). |
| 52 | PB13 | `HV_EN` | GPIO | - | out | SiPM bias converter enable, active high, 10 k ext PD (bias off in reset). |
| 53 | PB14 | `NTC_BOARD` | ADC1 IN5 | - | analog | Board NTC near the bias converter (same network). |
| 54 | PB15 | `HTR_EN` | GPIO | - | out | Heater high-side switch input, active high, 10 k ext PD (heater off in reset). Changed by firmware only in the service interrupt that follows a gate boundary (<= 10 us after it); the switch itself is slew-limited. The hardware thermal cut-out is in series and cannot be overridden. |
| 55 | PD8 | `ULD_R0` | GPIO | - | in | REF_ULD latch Q, reference lane 0. |
| 56 | PD9 | `ULD_R1` | GPIO | - | in | REF_ULD latch Q, reference lane 1. |
| 57 | PD10 | `ULD_R2` | GPIO | - | in | REF_ULD latch Q, reference lane 2. |
| 58 | PD11 | `ULD_R3` | GPIO | - | in | REF_ULD latch Q, reference lane 3. |
| 59 | PD12 | `LLD_F0` | TIM4 | 2 | in | RAW (unlatched) BETA_LLD comparator output, floor lane 0, on TIM4_CH1 input capture (either or both edges selectable; firmware captures the falling edge, the rising edge is the BUSY capture): time over threshold of the triggering pulse. The level is still read through GPIOD->IDR (must be low before the chain is cleared). 100 k ext PD. |
| 60 | PD13 | `LLD_F1` | TIM4 | 2 | in | RAW (unlatched) BETA_LLD comparator output, floor lane 1, on TIM4_CH2 input capture (either or both edges selectable; firmware captures the falling edge, the rising edge is the BUSY capture): time over threshold of the triggering pulse. The level is still read through GPIOD->IDR (must be low before the chain is cleared). 100 k ext PD. |
| 61 | PD14 | `LLD_F2` | TIM4 | 2 | in | RAW (unlatched) BETA_LLD comparator output, floor lane 2, on TIM4_CH3 input capture (either or both edges selectable; firmware captures the falling edge, the rising edge is the BUSY capture): time over threshold of the triggering pulse. The level is still read through GPIOD->IDR (must be low before the chain is cleared). 100 k ext PD. |
| 62 | PD15 | `LLD_F3` | TIM4 | 2 | in | RAW (unlatched) BETA_LLD comparator output, floor lane 3, on TIM4_CH4 input capture (either or both edges selectable; firmware captures the falling edge, the rising edge is the BUSY capture): time over threshold of the triggering pulse. The level is still read through GPIOD->IDR (must be low before the chain is cleared). 100 k ext PD. |
| 65 | PC6 | `PULSER_STROBE` | TIM8 | 4 | out | TIM8_CH1: strobe of the charge-injection test pulser (amplitude from the PULSER_AMPL DAC output). Idle low, 10 k ext PD. |
| 66 | PC7 | `DAC_CS3_N` | GPIO | - | out | U_DAC3 /CS. 10 k ext PU. |
| 67 | PC8 | `MON_MUX_A3` | GPIO | - | out | Monitor mux select bit 3 (0 = fast path, 1 = slow path). |
| 68 | PC9 | `I2C_SDA` | I2C3 | 8 | bidir | I2C3_SDA, 2.2 k ext PU. |
| 69 | PA8 | `I2C_SCL` | I2C3 | 2 | bidir | I2C3_SCL, 2.2 k ext PU. TMP117 x2 + 24AA025E64. |
| 70 | PA9 | `RS485_TX` | USART1 | 7 | out | USART1_TX to the isolator DI. Idle high. |
| 71 | PA10 | `RS485_RX` | USART1 | 7 | in | USART1_RX from the isolator RO. 10 k ext PU so a disabled receiver reads mark. |
| 72 | PA11 | `HTR_CUTOUT_OK` | GPIO | - | in | Status of the independent thermal cut-out: high = closed/healthy, low = tripped or heater supply absent. Level-shifted from the heater domain, 100 k ext PD. |
| 73 | PA12 | `RS485_DE` | USART1 | 7 | out | USART1_DE, active high, 10 k ext PD. Tie the transceiver /RE to DE so the head does not hear its own transmission. |
| 76 | PA13 | `SWDIO` | SYS | 0 | bidir | SWD header (ARM 10-pin 1.27 mm / TC2030). |
| 77 | PA14 | `SWCLK` | SYS | 0 | in | SWD header. |
| 78 | PA15 | `BUSY_F0` | TIM2 | 1 | in | TIM2_CH1 input capture, rising edge. Q of the BETA_LLD (BUSY) latch of floor lane 0. 100 k ext PD so a missing latch supply reads idle. PA15 is JTDI with a pull-up at reset: harmless for an input. |
| 79 | PC10 | `DBG_TX` | UART4 | 5 | out | UART4_TX to a 3-pin debug header. |
| 80 | PC11 | `DBG_RX` | UART4 | 5 | in | UART4_RX, 100 k ext PU. |
| 81 | PC12 | `LED_STROBE` | TIM8 | 4 | out | TIM8_CH3N: strobe of the LED pulser (BSS138 Q1001/1101/1201/1301 via 100 R each), all four lanes together; amplitude V_LED = 2 x U_DAC0 output 7. Idle low, 100 k ext PD (R2413). Pulse ~200 ns: held high it feeds the LED through R1018 (10 k) continuously. |
| 82 | PD0 | `ULD_F0` | GPIO | - | in | BETA_ULD latch Q, floor lane 0. All 16 PD inputs are read with one GPIOD->IDR access in the service interrupt; 100 k ext PD each. |
| 83 | PD1 | `ULD_F1` | GPIO | - | in | BETA_ULD latch Q, floor lane 1. All 16 PD inputs are read with one GPIOD->IDR access in the service interrupt; 100 k ext PD each. |
| 84 | PD2 | `ULD_F2` | GPIO | - | in | BETA_ULD latch Q, floor lane 2. All 16 PD inputs are read with one GPIOD->IDR access in the service interrupt; 100 k ext PD each. |
| 85 | PD3 | `ULD_F3` | GPIO | - | in | BETA_ULD latch Q, floor lane 3. All 16 PD inputs are read with one GPIOD->IDR access in the service interrupt; 100 k ext PD each. |
| 86 | PD4 | `ALPHA_F0` | GPIO | - | in | ALPHA (slow path) latch Q, floor lane 0. |
| 87 | PD5 | `ALPHA_F1` | GPIO | - | in | ALPHA (slow path) latch Q, floor lane 1. |
| 88 | PD6 | `ALPHA_F2` | GPIO | - | in | ALPHA (slow path) latch Q, floor lane 2. |
| 89 | PD7 | `ALPHA_F3` | GPIO | - | in | ALPHA (slow path) latch Q, floor lane 3. |
| 90 | PB3 | `BUSY_F1` | TIM2 | 1 | in | TIM2_CH2 input capture, rising edge. Q of the BETA_LLD (BUSY) latch of floor lane 1. 100 k ext PD so a missing latch supply reads idle. PB3 is the only SWO pin: trace is given up. |
| 91 | PB4 | `LED_STATUS_N` | GPIO | - | out | Green, active low to +3V3 through 1 k. PB4 is JTRST at reset and UCPD1_CC2 (dead-battery pull-down behaviour UNVERIFIED): LED only. |
| 92 | PB5 | `MON_MUX_A0` | GPIO | - | out | Mux select bit 0. Shared: (a) per-chain anode current mux U2703, channel = MON_MUX_A[2:0] (0-3 = F0-F3, 4-7 = R0-R3); (b) lane monitor decoder U2701 A0 (enables lane A[1:0]). |
| 93 | PB6 | `LED_FAULT_N` | GPIO | - | out | Red, active low to +3V3 through 1 k. PB6 is UCPD1_CC1 (dead-battery pull-down behaviour UNVERIFIED): LED only. |
| 94 | PB7 | `MON_MUX_A1` | GPIO | - | out | Mux select bit 1 (same shared use as bit 0). |
| 95 | PB8 | `BOOT0` | SYS | - | in | 10 k ext PD + test point / jumper to +3V3 for the ROM bootloader. Not used as GPIO. |
| 96 | PB9 | `MON_MUX_A2` | GPIO | - | out | Mux select bit 2: U2703 A2 and the lane mux address A0 of the waveform monitor (shared). |
| 97 | PE0 | `CLR_F0_N` | GPIO | - | out | Clear of all three latches of floor lane 0, active low pulse (>= 20 ns, firmware gives ~100 ns). 10 k ext PD: latches are held cleared (chain idle, BUSY low) while the MCU is in reset. |
| 98 | PE1 | `CLR_F1_N` | GPIO | - | out | Clear of all three latches of floor lane 1, active low pulse (>= 20 ns, firmware gives ~100 ns). 10 k ext PD: latches are held cleared (chain idle, BUSY low) while the MCU is in reset. |
<!-- END PINMAP -->

## Emulator: `rr_head_sim`

```sh
firmware/head/build/host/rr_head_sim --seed 1                      # TCP 127.0.0.1:5540, UDP 127.0.0.1:5541
firmware/head/build/host/rr_head_sim --pty /tmp/rr-head --gate-range 10000,1000000 --truth-log gates.ndjson
```

It prints `rr_head_sim ready tcp=… stim=… seed=…` on stdout when it is listening and exits with
status 0 on SIGTERM/SIGINT (or `{"cmd":"quit"}`).

| Option | Meaning |
|---|---|
| `--tcp HOST:PORT` | Serial side: exactly the RS-485 bytes (records of ICD §4). One client; a new connection replaces the old one. Default `127.0.0.1:5540`. |
| `--pty PATH` | Additionally serve the same byte stream on a pseudo-terminal; `PATH` becomes a symlink to it. |
| `--stim HOST:PORT` | Physics / fault-injection socket, UDP, one JSON object per datagram, one JSON reply per datagram. Default `127.0.0.1:5541`. |
| `--seed N` | Seeds counts and boot ids → byte-identical runs. Without it a random seed is used and printed. |
| `--clock real\|manual` | `real` (default): head clock = CLOCK_MONOTONIC since start. `manual`: the head clock moves only on `{"cmd":"advance","us":N}` (deterministic tests, faster than real time). |
| `--serial S`, `--variant concept-e\|concept-e-5mm` | Identity of the emulated head (3 mm or 5 mm rail projection in the descriptor). |
| `--gate-range MIN,MAX` | Accepted `ARM.span_us` and descriptor `gate_range_us` (default `100000,100000`). |
| `--descriptor-file F --descriptor-id S --setup-id S --firmware S --boot-id UUID` | Baseline replica: serve the given descriptor bytes and identifiers (used to reproduce `examples/head_transactions.ndjson` byte for byte). |
| `--tau-floor-us X`, `--tau-ref-us X` | Dead time per recorded event (default 10 µs each, the figure measured for the event-capture logic). |
| `--truth-log FILE` | One JSON line per generated gate with the drawn counts and live ticks. |
| `--no-width-hist` | Emulate a head without pulse-width measurement. By default DIAG carries a synthetic width histogram (beta/reference events in the 150 – 400 ns bin, rejects in 0.4 – 2 µs, alpha ≥ 2 µs). |

**Physics model.** For each gate and chain the expected counts are the integral of the stimulus
rate over the gate (rate changes inside a gate are honoured), multiplied by the non-paralyzable
factor 1/(1 + R·τ) with R the total true rate of the chain; the recorded counts are Poisson draws
with that mean and the live time is `gate − τ × recorded events`. Floor alpha, beta and reject
share one chain; each reference chain is separate. The same record type (`head_gate_record`)
enters the same core as on the target.

**Stimulus and control commands** (`{"cmd": …}`; every reply has `ok`, `cmd`, `head_us`, `boot_count`, and `error` if refused):

| Command | Fields |
|---|---|
| `rates` | `alpha`, `beta`, `ref`, `floor_reject`, `ref_reject`: s⁻¹, a number (all lanes) or an array of 4 (lane 0 = robot left). Optional `from_us` (head clock) or `from_mono_ns` (host CLOCK_MONOTONIC, real clock only); default now. Channels not named keep their rate. Up to 2048 pending changes. |
| `fault` `kind:"mcu_reset"` | `ms` boot time, `cause` `"watchdog"`/`"brownout"`/pin. New boot id, UNBOUND, clock restarts at 0. |
| `fault` `kind:"link_drop"` | `ms`: bytes in both directions are lost; the head is not reset. |
| `fault` `kind:"pause_reads"` | `ms`: READ requests get no reply (buffer overflow → GAP afterwards). |
| `fault` `kind:"corrupt_crc"` / `"delay_reply"` | `count` next replies with one flipped bit / delayed by `ms`. |
| `fault` `kind:"null_channel"` / `"saturate"` | `lane` 0-3 (omit = all), `chain` `"floor"`/`"ref"` (omit = both), `on` (default true). |
| `fault` `kind:"thermal"` | `what`: `sipm_open`, `heater_sensor_open`, `cutout`, `overtemp`; `on`. |
| `fault` `kind:"lost_gates"` / `"source_fail"` | `count` gate records dropped inside the head / ARM answers FAULT. |
| `analog` | `sipm_c` (number, array or null), `heater_c`, `board_c`, `supply_v`, `bias_ua`, `bumper_zones` (bit mask), `cutout_ok`; board functions: `imon_ua` (number or array of 8: anode current per chain, default 1.0), `imon_valid` (mask), `imon_offset_uv`, `expander` (present), `lid_open`, `inhibit`, `efuse_fault`, `hw_rev`, `zones_available` (default false = rev A). The permit latch is modelled (set by a HV_EN edge without inhibit, cleared by any inhibit). |
| `swap` | `serial`, optional `variant`, `ms`: another head on the same cable (new identity, empty storage, new boot). |
| `advance` | `us` (manual clock only). |
| `stats` / `ping` / `quit` | `stats` returns identity, link state, gate count, the totals of drawn counts per lane and channel, and `board` (pulser, LED, hold, bias/permit as the model sees them). |

Python helper for tests and benches: `tests/headsim.py` (`Sim`, `Link`, `Link.handshake()` built on
the baseline tools).

## Board functions added by IB-17 / IB-18 / IB-15 (firmware 0.5.0)

| Function | Pin / part (circuit.py) | Firmware | Evidence |
|---|---|---|---|
| Per-chain anode current monitor | PE15 `IMON_CH` = ADC4_IN2; TMUX1108 U2703 addressed by MON_MUX_A[2:0] (PB5/PB7/PB9); R105 4.99 k sense; R108 10 k + C2704 100 nF | Background scan, 10 ms settle per step (10 x R108 C2704), I = (V_trim - V_TRIMDRV)/R105, 147 nA per LSB. Window: `RRH_IMON_MAX_NA` 200 uA (low end of the budget's 0.2 - 0.5 mA soft limit) or trim buffer at its rail; flagged after 200 ms (`RRH_IMON_HOLD_US`). Low-side window disabled (see placeholders) | pin and net tool-checked against circuit.py; scale calculated; logic tested on mock and emulator; ADC4 driver compiled only |
| Per-lane `BIAS_OUT_OF_RANGE` | from the above | Per chain: floor chain out of window nulls alpha + beta_window with `FLOOR_FAULT`, reference chain nulls photon_ref with `REFERENCE_FAULT` (the meaning matches: that chain's SiPM is not held at its overvoltage); lane DIAG flag `BIAS_OUT_OF_RANGE`; global ACQ flag `BIAS_OUT_OF_RANGE`. Live, not latched. Currents in DIAG (`lanes[n].imon_na`) and STATUS (`imon`) | tested |
| Test-pulse channel select | PF2/PF9/PF10 `PULSER_A0..2` -> 74LVC138 U2702 | `pulser.channel` (setup, hashed); GPIO outputs; `pulser.width_us` 1..100 | pins tool-checked; port compiled only |
| LED pulser | PC12 `LED_STROBE` = TIM8_CH3N (AF4, checked in the ST pin database); amplitude U_DAC0 out 7 -> U2306A x2 | `pulser.led_enable`, `pulser.led_code`; 1 kHz, ~208 ns, same TIM8 period as the charge pulser; amplitude forced to 0 when disabled | compiled only; width UNVERIFIED (LED not chosen) |
| Reserved sync input | PF1 `SYNC_IN` | input with pull-down, not used (J2 pins 5/6 hardware pulse stays unused) | pin tool-checked |
| Expander (optional) | TCA9534 U2405 at 0x20: P0 MON_EXT (out, held 0), P1 HV_PERMIT, P2 HV_INH_N, P3 LID_G, P4 EF_FLT_N, P5/P6 HWREV | Read each control period and gate; STATUS `expander`; permit trip detected directly; absent -> fields null | circuit bits tool-checked; register map UNVERIFIED; emulator model tested |
| Bias set-point law | U_DAC0 out 6 -> HV_SET; R2213 + R2214 + R2215 over R2215 = 25.0 | `code = mV x 4096 / 62500` (full scale 62.5 V, 15.26 mV per step); 0.4 used 0 ... 60 V over 4095 codes | calculated, tested; DAC output gain 1 UNVERIFIED |
| Bias read-back | R2217 + R2218 + R2219 over R2219 = 25.2233 | firmware 0.4 divided by 25 (1 % error) | calculated, tested |
| Bias limits | OVP R2222 10 k / R2223 7.15 k with VREF 3.0 V -> 31.55 V trip (`circuit.py`, budget 31.5 V); HV_RAW strap R2203 71.5 k -> 37.1 V | Set-points above trip - 1 V (30.5 V) are refused (`BAD_ARG`) and the temperature law is clamped there; per-family strap table in `rrh_straps`, `-DRRH_SIPM_FAMILY=n` | tool-checked against circuit.py |
| Bias-on sequence (CCR-HE-09) | permit latch U2205 | HV_SET 0 -> HV_EN up -> ramp 500 mV per 100 ms (= 5 V/s at HV_BUS since 0.5.2, S3-07); `BIAS_PERMIT` health code when HV_EN is high and the permit is low (expander) or BIAS_VMON < 1 V after the ramp; recovery by `FAULT_CLEAR` (allowed only when the inhibit bus is released if the expander is present), which makes the next period raise HV_EN again | tested |
| Lid interlock, rail zones | J2201 lid switch -> LID_G; rail-zone inputs | Lid state only through the expander (`lid_open`, `hv_inhibit`); without the expander "unknown" (null). **Rail zones: not available on rev A (IB-21 closed)**: DIAG `bumper_zones` is `null`, STATUS `bumper.available` is `false` with null lists, `clear_bumper` is a no-op. The HAL field `zones_available` is false in the STM32 port. | tested |

### Placeholders and unverified constants

| Constant | Where | Status / depends on |
|---|---|---|
| Default thresholds (per device type since 0.5.2: LLD 10 p.e. for J60035, ULD 250 p.e., ALPHA 0.9 x weakest alpha SLOW) | `rrh_config.h` `RRH_FAST_UV_PER_PE` 6900, `RRH_DEFAULT_*` | ASSUMED: 6.9 mV per p.e. is the budget's J60035 figure (2.2); baseline 0.600 V from R2310/R2311 (circuit). Firmware 0.4 defaults (code 200 = 0.12 V) were below the baseline: comparators permanently high. ALPHA overlaps the beta maximum in the budget |
| `RRH_IMON_MAX_NA` 200 uA | `rrh_config.h` | electronics number (budget 5.1, 0.2 - 0.5 mA, low end); R105 |
| `RRH_IMON_SAT_UV` 50 mV | `rrh_config.h` | UNVERIFIED: output swing of the trim buffer TLV9062 (U1001) near the rail |
| `RRH_IMON_MIN_NA` 0 (disabled) | `rrh_config.h` | placeholder: healthy dark current at -25 degC (about 10 nA, calculated from 0.9 uA at 25 degC halving per 8 degC) is below the 147 nA resolution and the 0.3 uA offset of U1001 + ADC. A dead or disconnected channel is therefore NOT detected by this monitor |
| `RRH_BIAS_CURRENT_MAX_UA` 200 uA | `rrh_config.h` | 80 % of the 250 uA monitor range (BIAS_IMON 8.0 mV/uA, R2206); 0.4 used 500 uA, which the monitor cannot reach. TPS61391 mirror gain 0.8 +-5 % and MON1 compliance (checklist B2) are datasheet figures, UNVERIFIED |
| `RRH_BIAS_OVP_MARGIN_MV` 1000, `RRH_BIAS_TOLERANCE_MV` 500 | `rrh_config.h` | The BIAS_VMON divider top resistors R2217/R2218 are **1 %** parts (the budget assumes 0.1 %): +-0.3 V at 31 V before calibration; trip accuracy likewise. Comparator offset (U2203) and REF3030 accuracy UNVERIFIED |
| `RRH_BIAS_RAMP_STEP_MV` 500 | `rrh_config.h` | 5 V/s at HV_BUS (electronics S3-07; 12500 in 0.5.0/0.5.1 was a mis-reading) |
| DAC output gain / reference | `bsp_dac_init` (GAIN register 0), `RRH_DAC_VREF_MV` 2500 | UNVERIFIED (DAC60508 datasheet SLASEL1D not readable here); every threshold, trim, HV_SET, PULSER and LED value depends on it |
| ADC clock / sample time, TMUX settling, I2C timing, TCA9534 registers, TIM8 complementary-output rule | `bsp.c` | UNVERIFIED, compiled only |
| NTC curves for the SiPM carriers (R1016 ... R1316) and the heater plate (R2613) | `RRH_NTC_B3435` | ASSUMED B3435-class: the parts are supplied by others. The board NTC RT2201 is B3380 (circuit) |
| Heater current (INA180A2 gain 50, 10 mOhm shunt = 0.5 V/A), supply divider 6.6 | derivable | divider used; heater current derivable but not read by the firmware |
| Pulser charge model in the emulator (0.465 pC per p.e., 6.9 mV per p.e.) | `sim_hal.c` | SIMULATED constants of a J60035 |

**Waveform capture** in the target port stays out of scope (ADC2 + DMA, arbitration with the IMON scan
on the shared MON_MUX lines would be needed): `ENG_WAVE_ARM` answers `FAULT` on the target, as before.

### Open electronics questions (see CONTRACT_CHANGE_REQUESTS.md)

MON_MUX_A[2:0] drive both the IMON mux and the lane-monitor decoder U2701/lane muxes, so scanning IMON
while counting repeatedly connects shaper taps (through 1 kohm) to MON_BUS; charge injection into the comparator
inputs was not analysed. Since 0.5.1 the scan does NOT run while armed (`RRH_IMON_SCAN_WHILE_ARMED` 0, review M2); see the 0.5.1 section.

## Interference review follow-up (firmware 0.5.1, `docs/reviews/REVIEW_head_interference.md`)

| Finding | Change |
|---|---|
| **C1** alpha decided by the ALPHA latch alone | Checked and confirmed: `head_afe_calc_out.md` T2 gives FAST/SLOW = 6.93/0.369 = 18.8 per p.e. for plastic light and 1.467/0.218 = 6.7 for ZnS, and budget 2.3 puts the beta maximum (120 p.e., SLOW 44 mV) above the alpha minimum (150 p.e., 33 mV); the 0.5.0 default ALPHA level (30 mV) is crossed by every beta above ~81 p.e. and `rrh_evtcap.c` tested ALPHA before ULD. New rule: alpha = ALPHA latch AND measured raw-LLD time over threshold >= `afterglow.alpha_min_tot_ns` (setup member, hashed, default 250 ns, 0 = old rule, max 5000). ALPHA with a shorter or unmeasured width is a floor **reject** (never alpha, never beta window) and is counted in DIAG `alpha_short`. A falling-edge capture that lags the comparator level by one service is waited for (max 2 services) instead of being called short. Emulator: new stimulus `bright_beta` (+ `bright_pe`, `alpha_pe`) with the T2 amplitudes and TOT shapes (plastic Gaussian FWHM 80 ns, ZnS 200 ns decay). Tests fail on the old rule (`test_bright_beta_is_not_alpha`, `test_bright_beta_is_not_counted_as_alpha`). |
| **M2** IMON scan while armed | Default off. The scan runs only while disarmed (gates are contiguous, there is no gap between gates in which a scan step could run without touching live time). On ARM the address lines are parked on R3 (`RRH_IMON_PARK_CHAIN`). While armed: per-chain readings are reported null (STATUS `imon.scan` = `PAUSED_ARMED`), the verdict of the last scan before ARM stays and keeps nulling its chains, nothing new is detected and nothing is cleared. **Coverage lost while armed:** onset of a per-chain over-current or unheld anode during a run is not seen per chain; it is still seen by the total BIAS_IMON trip (200 uA), by saturation/live fraction, and at the next disarm. One reference tap (R3) stays connected to MON_BUS through 1 kohm (loading of that reference channel, review M2 numbers) until the circuit gives a way to disable the lane muxes. |
| **m2** hold | Default 300 us. Circuit check: R_PZ 226 ohm / R_D 100 ohm give a DC transmission 100/326 = 0.307 (FAST sees 6.45 x PRE at low frequency), so the booked 150 us is indeed short of the input-coupling undershoot (C 100 nF with 1 kohm bias); I agree with the argument. I did not re-derive the -3.1 p.e. figure (no low-frequency model of the preamp in the repository); the zero crossing at 314 us is the reviewer's. Live-time sweep repeated: unbiased at every rate. Cost: 24.8 % dead at 20000 s⁻¹ against 21.0 % with 150 us (5 % alphas, simulated). |
| **m6** heater marker | Where it travels: DIAG `heater.transition` per retained gate (addendum 3) and nowhere in ACQ 2.0. End to end on the head side: the same information is in every ACQ frame as `thermal.heater` (ON/OFF) with `duty_pct` 0 or 100 (the heater switches only on gate boundaries), and the transition gate is exactly the first gate whose state differs from the previous frame. Test `test_heater_transition_marker_is_derivable_from_acq` compares the derivation with the DIAG marker over a heater on and off cycle. A gap in sequence numbers hides the edge: the host should then treat the gate after the gap as marked. |
| **m7** DAC writes while armed | Not deferred: deferring would freeze temperature tracking for hours of a survey (0.2 - 1.8 %/degC gain). Instead each write is counted per gate (DIAG `bias.dac_writes`, saturating at 255) so the host can exclude or study those gates; the writes are at most 20 mV per 100 ms control period and happen only while the target moves by more than 5 mV. The reviewer's numbers (about 3 nA at the anode, 0.007 p.e. DAC crosstalk on the shared package) are calculated, not measured; bench test B8 with tracking active decides. |
| O2 | Cut-out actuation nulling the gate: not done; there is no ACQ lane flag whose meaning matches. `HEATER_FAULT` + `OVERTEMP` flag the frame (global) and the host should exclude flagged gates. |
| O6 | Refusing ARM with placeholder thresholds: not done; the firmware has no device-type setting. Defaults stay flagged ASSUMED; STATUS does not yet say "placeholder". |

**Time over threshold: what the capture clock resolves.** Tick 6.94 ns (144 MHz, TIM4/TIM3 16-bit for the falling edge, TIM2/TIM5 for the BUSY rising edge). Each edge is quantised to +-1 tick, so a width has +-2 ticks = +-14 ns; the two timers' offset is measured once with reads a few cycles apart (<= 3 ticks = 21 ns systematic, sign unknown); the comparator delay (4.5 ns) cancels between the edges, the 6 mV hysteresis widens the pulse slightly. Total about +-35 ns worst case. The calculated classes are bright beta 120 p.e. ~ 120 - 170 ns and ZnS alpha 150 p.e. ~ 277 ns (1500 p.e. ~ 737 ns): the 250 ns limit is 80 - 130 ns (12 - 19 ticks) above the beta side, which the clock resolves comfortably, but only 27 ns (4 ticks) below the weakest assumed alpha, which is **marginal**: alphas of 150 p.e. can fall on either side; alphas above ~300 p.e. (~416 ns) are robust. The larger uncertainty is the pulse shape itself (ZnS decay 200 ns is assumed; +-30 % moves the 150 p.e. alpha between 190 and 360 ns). The DIAG width histogram (edges 150/400/2000 ns) already shows both populations; set the limit from an Am-241 and Sr-90 measurement. Circuit change that would make it robust: bring the raw ALPHA (SLOW) comparator output of each floor chain to a capture channel and use its time over threshold (microseconds for ZnS, a fraction of that for plastic) or the delay between the LLD and ALPHA edges; no MCU pin is free (the reserved PF1 `SYNC_IN` could serve one chain only), so this needs the pin budget revisited (rev B).

## Stage 3 adoption (firmware 0.5.2; `electronics/head_acq/STAGE2_CHANGE_REQUESTS.md` "Stage 3", S3-01 ... S3-10)

`tools/check_circuit.py` now imports `overrides.apply()` (the stage-3 netlist; `design/` is not edited) and checks: MON_LANE_EN on U2405 P7 / U2701 E3 / R2418 100 k, the expander bit map, F2801 0.5 A in the frame bond, R2702/R2802 1 M onto MON_BUS, the 10 k taps on FAST / SLOW / PRE of all channels, C150 ... C850 = 47 nF, and the heater sense (R2601 10 mohm, U2601 INA180A2, path to PB12).

| Item | Firmware 0.5.2 |
|---|---|
| Lane monitor muxes (S3-01/02) | MON_LANE_EN (TCA9534 P7, active high, 100 k pull-down) is written 0 BEFORE P7 becomes an output (config 0x7E: P0 and P7 outputs) and is never set: the lane muxes are off at all times, armed or not (also with the expander absent or in reset). IMON scan while armed stays OFF by default (`RRH_IMON_SCAN_WHILE_ARMED` 0, address parked on R3): the electronics' T15 shows zero tap loading and zero switch charge with the muxes off, but T15 does not cover the digital address edges (MON_MUX_A0..2, up to 100 Hz) next to analogue nets or the ADC4 sampling on PE15, so I cannot show the disturbance is below budget; the option `-DRRH_IMON_SCAN_WHILE_ARMED=1` exists, with a per-gate marker (DIAG `bias.imon_steps`, number of mux steps in the gate). Monitor gain 0.98 and settle 2 ms are constants (`RRH_MON_GAIN_PCT`, `RRH_MON_SETTLE_US`); the monitor waveform capture itself is still not in the port. |
| Frame monitor (S3-03) | MON_ADC (PC4, ADC2_IN5) = 0.300 V + V_FRAME/2 (derived from R2310/R2311, R2702, R2802: `rrh_board_frame_mv`). Read at every control period and every gate; reference = last quiet disarmed reading. Health `FRAME_FAULT` (latched, heater forced off at once) when the frame rises > 30 mV (15 mV at MON_ADC) above the reference or lies outside -60 ... +60 mV. STATUS `frame{mv, fault}`. **Can detect:** open bond / blown F2801 (frame floats to VBL: MON_ADC 0.6 V), a return-side heater contact while the heater draws current (+70 - 90 mV), out-of-window at boot. **Cannot detect:** a contact while the heater is off or drawing no current, rises below 30 mV, a feed-side contact before the fuse has opened (the fuse opening is what is seen), a second ground path, or an event that clears between samples (100 ms). Clearing needs the reading back in its window. |
| Device type and TOT cut (S3-09) | Setup member `device` (`J60035` default, `J30035`, `S14160`, `S13360`, `NUVMT`, `4xJ60035`, `NONE`) and `afterglow.alpha_min_tot_ns` = explicit override (0 = follow the device: 290 / 180 / 215 / 190 / 200 / 655 ns). Both are in `setup_id`; the effective cut is in STATUS `alpha_tot_ns`. Choosing a device re-derives the placeholder thresholds (LLD per T6: 10 / 9 / 10 / 7 / 23 / 12 p.e.; ULD 250 p.e. or 1.8 V; ALPHA 0.9 x the weakest alpha SLOW; FAST per p.e. from T2) and clears `thresholds_confirmed`. **ARM is refused** (`FAULT`, reason `device_type_unset` / `placeholder_thresholds`) until the device is set and the thresholds are written or confirmed (`thresholds_confirmed: true`, in `setup_id`); the emulator allows placeholders unless started with `--strict-placeholders`. Closes O6. Emulator pulse model now interpolates the electronics' T13 table (all six devices, LLD 8/10 p.e. rows). With the J60035 numbers the 290 ns cut leaves 84 ns to the weakest alpha (374 ns) and 88 ns to the brightest beta (202 ns): about 12 ticks each side. I found one problem in my 0.5.1 default: a fixed ALPHA level of 30 mV is above the weakest S13360 alpha (25.6 mV) and 4 x J60035 (19.8 mV); the level is now per device. |
| Defaults (S3-10, S3-07, S3-06) | LLD 10 p.e. (J60035, +10 degC, 0.05 1/s; 11 p.e. at maximum DCR is not applied: a person decides); ramp 500 mV per 100 ms at HV_BUS; BIAS_VMON ratio is a per-board calibration `bias.vmon_ratio_e4` (default 252233 = 25.2233) stored in the non-volatile setup but NOT in `setup_id` (it changes no sample, a write does not invalidate the binding); STATUS `bias.vmon` reads `UNCALIBRATED` until it is written. The core now receives the ADC pin voltage (`bias_vmon_adc_uv`) and applies the ratio. |
| Post-alpha hold (S3-04) | Kept at 300 us. The electronics' T14 gives -0.49 p.e. at 150 us and +0.06 p.e. at 300 us (stage-1 network: -2.6 / -3.3), so 150 us would now suffice for the baseline. 300 us stays because the other reason for the hold, ZnS afterglow of 100 - 200 us (budget 4), is untouched by the capacitor, and the cost (24.8 % against 21.0 % dead at 20 000 s-1) is irrelevant at survey rates. The setup member allows 150 us for a bench comparison. |
| Heater over-current (IB-32/IB-61) | HAL `rrh_hal_heater_force_off()` (opens HTR_EN at once, not on the gate boundary; the gate containing the edge is marked). Core: head sense I = V(PB12) / (R2601 x 50) = 0.5 V/A (checked against the netlist by `check_circuit.py`; INA180A2 gain 50 is recalled from the part suffix, UNVERIFIED). Cut-off when above `heater.oc_ma` (default 3200) for `heater.oc_ms` (default 300, i.e. three control samples): switch opened, health `HEATER_OVERCURRENT` (latched, clearable when the current is below the limit), global ACQ flag `HEATER_FAULT`. The sense is read at the control period and every gate (100 ms at the default span), so a cut happens at most one sample after the hold expires. 3.2 A is 2 % above the contact's UNVERIFIED 3.13 A continuous rating and 5 % above the 3.04 A maximum draw: it protects against a partial short between the contact's rating and the chassis trip (3.56 - 4.35 A) only if the hold time is shorter than the contact's thermal time constant, which is also unknown. Limits are hashed setup members (range 0.5 - 4.5 A, 50 ms - 5 s). |

Placeholders added or still open: INA180A2 gain (recalled), the frame thresholds (30 mV rise, +-60 mV window: derived from the electronics' +35 ... +45 mV at MON_ADC and VBL +-20 mV, not measured), the per-device defaults (ASSUMED optics; confirm with Sr-90 and Am-241), `RRH_HEATER_OC_*` (contact rating UNVERIFIED), TCA9534 output-register power-up value and register map (recalled), ADC2 sample time.

## Review of the event-capture questions (item 5)

| Question | Result |
|---|---|
| Live-time accounting when a latch clear crosses a gate boundary | Event clears were already tested (reference chain, exaggerated latency). New: the blind CLR interval of an idle-latch clear and a held alpha both split exactly at the boundary; counts go to the gate containing the clear. Exact against the independent model, no defect. |
| Service interrupt late by more than one period | Busy time runs to the actual clear, so lateness only adds dead time that is measured. Tested at 37 us, 2.5 and 2.9 gates (1 ms gates), boundaries inside the late service: exact. **Finding (not a defect of accounting):** a service late by more than 3 gates overflows the 4-slot FIFO and loses records (shown as a sequence gap + `RECORD_LOST`); at 100 ms gates that is 300 ms, far beyond any interrupt latency. |
| Chain held busy by a long tail | 0.6 and 0.9 ms tails are counted once and fully booked as busy; a 2.3 ms tail is forced at 1 ms, flagged `SATURATED`, and the chain is flagged blind while the comparator stays high. Exact. A comparator that falls only after a forced clear leaves up to 3 services (30 us) in which a chain is blind but not flagged and not booked; the gate is flagged by the forced event anyway. |
| **Defect found and fixed in 0.5 while adding IB-18a** | The first idle-latch implementation used the latch levels sampled before the service, so an alpha event cleared in the same service looked like an idle ALPHA latch. Fixed (`busy_at_entry`); covered by the sweep tests, which showed spurious idle clears before the fix. |
| Defect found in 0.4 (not event capture) | The descriptor builder carried the pre-IB-11 envelope (x max 192.2 mm) while `contract.yaml` says 212.5 mm: `check.sh` failed on this checkout. Fixed. `RRH_BIAS_CURRENT_MAX_UA` = 500 uA and the default thresholds below the baseline were also unreachable / wrong, see placeholders. |

## Known gaps

- No hardware test of any kind. DAC gain, ADC4 scan, I2C expander, TIM8 outputs are compile-checked only.
- Monitor waveform capture is implemented in the protocol and the emulator but not in the STM32 port.
- Per-chain `FLOOR_FAULT`/`REFERENCE_FAULT` from the anode monitor cover over-current and an unheld anode only; a dead chain is not detected (placeholder above). `frontend_fault` stays 0 on the target.
- The descriptor builder emits `geometry_basis: CONCEPT` only; an as-built descriptor needs measured geometry storage and a provisioning tool.
- Identity (serial) comes from the EUI EEPROM or the MCU UID; descriptor id, revisions and geometry id are compile-time defaults (`rrh_identity_defaults`) until a factory record exists.
- Threshold scans are a host procedure over `ENG_SETUP_SET` (every step is a new `setup_id` and needs a new handshake); there is no on-head scan op.
