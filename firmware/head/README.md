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
| `core/rrh_eng.c` | Additive ops: DIAG, STATUS, FAULT_CLEAR, ENG_FAULT, ENG_SETUP_GET/SET, ENG_WAVE_ARM/READ. |
| `hal/rrh_hal.h` | The only boundary between core and hardware (about 20 functions). |
| `port/host/` | `rr_head_sim`: HAL on a seeded Poisson source + sockets + fault injection. |
| `port/stm32g474/` | Target port: clocks, TIM2/TIM5 capture + 100 kHz service interrupt, RS-485 USART, DACs, ADC, I2C, flash, IWDG. |
| `tests/` | `test_core.c`, `test_evtcap.c` (host unit tests), `test_sim_interop.py` + `headsim.py` (emulator driven by the baseline tools). |
| `tools/` | `check_pinmap.py`, `gen_pinmap.py`, ST pin-database subset, PlatformIO helper. |
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
ctest --test-dir firmware/head/build/host --output-on-failure    # 5 test programs
cd firmware/head && pio run -e rr_head_acq                       # .pio/build/rr_head_acq/firmware.{elf,bin}
```

Tests (all on the host):

- `common_unit`, `common_python_interop` — see `../common/README.md`.
- `head_core_unit` (`tests/test_core.c`, mock HAL): unbound answers, handshake rules, reset →
  fresh boot id + UNBOUND, reply cache, garbage on the link, frame mapping and every null rule,
  GAP/EMPTY and sequence continuity across DISARM/ARM, setup change invalidates the binding,
  LOCKED/HOLDOVER/UNSYNCED, heater control and fault latches, bias compensation, lost/bad gates.
- `head_evtcap_unit` (`tests/test_evtcap.c`): single events of each class, non-retriggering,
  acceptance window, forced clear, event straddling a gate boundary, Poisson rate sweep
  10 – 20000 s⁻¹, service-interrupt jitter, heater switching on boundaries, stop, FIFO overflow,
  pulse-width histogram (present and absent).
  Every gate record is compared exactly with an independent hardware model.
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
| Size (`rr_head_acq`, `-Os`, GCC 12.3.1) | flash 35 520 bytes (6.8 %), static RAM 86 044 bytes (65.6 %) — tool-checked with `arm-none-eabi-size` |

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

i.e. about 9.7 µs of measured dead time per event. With ±6 µs service jitter and 0.1 % of the
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
| 30 | PC4 | `MON_ADC` | ADC2 IN5 | - | analog | Buffered monitor mux output, 0-3 V, anti-alias RC ~ 1 MHz. |
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
| 51 | PB12 | `HTR_SENSE` | ADC1 IN11 | - | analog | Current-sense output of the heater high-side switch (scale by electronics). |
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
| `analog` | `sipm_c` (number, array or null), `heater_c`, `board_c`, `supply_v`, `bias_ua`, `bumper_zones` (bit mask), `cutout_ok`. |
| `swap` | `serial`, optional `variant`, `ms`: another head on the same cable (new identity, empty storage, new boot). |
| `advance` | `us` (manual clock only). |
| `stats` / `ping` / `quit` | `stats` returns identity, link state, gate count and the totals of drawn counts per lane and channel. |

Python helper for tests and benches: `tests/headsim.py` (`Sim`, `Link`, `Link.handshake()` built on
the baseline tools).

## Known gaps

- No hardware test of any kind. Analog scale factors in `port/stm32g474/hal_stm32.c` and the DAC
  transfer function of the bias converter are design placeholders.
- Monitor waveform capture is implemented in the protocol and the emulator but not in the STM32
  port (`ENG_WAVE_ARM` answers FAULT there).
- No per-channel front-end monitor exists on rev A, so `FLOOR_FAULT`/`REFERENCE_FAULT` can only
  come from a disabled chain or (emulator) injection; `BIAS_OUT_OF_RANGE` is global.
- The descriptor builder emits `geometry_basis: CONCEPT` only; an as-built descriptor needs
  measured geometry storage and a provisioning tool.
- Identity (serial) comes from the EUI EEPROM or the MCU UID; descriptor id, revisions and
  geometry id are compile-time defaults (`rrh_identity_defaults`) until a factory record exists.
- Threshold scans are a host procedure over `ENG_SETUP_SET` (every step is a new `setup_id` and
  needs a new handshake); there is no on-head scan op.
