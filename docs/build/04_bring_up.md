# 04 Bring-up: from bare boards to a driving robot

**Updated 2026-11-28** for the traction-inhibit reviews (IB-66, IB-70, IB-74), chassis stage-5 netlist and firmware, head stage 3 and firmware 0.6.0, the interference and data-path reviews (IB-67, IB-72) and the registers. **Status.** No board exists, no firmware has run on hardware, no value below has been measured. Every "expected" value is a design value, a calculation or a simulation, with its source. The sequence of stages is **proposed** by combining the procedures in the sources; the procedures inside each stage (`layout_guidance.md` section 7, `chassis_safety_chain.md` section 8, the "first power-up observation list" of the chassis firmware README) are the engineers' own and are quoted, not validated.

**This is not a certified safety system.** The hardwired traction chain is a relay circuit with diagnostics, built from standard (not force-guided) relays, photo-MOS relays, comparators and one microcontroller, single-channel for most elements (two channels only for the head-rail loop and the REARM set stage, after the traction-inhibit reviews), with no performance level, category or SIL (`electronics/analysis/chassis_safety_chain.md` header; `docs/architecture/SYSTEM_ARCHITECTURE.md` section 6; `firmware/chassis/README.md`). Undetected dangerous single faults exist and are listed in the chain document section 6 (for example an open brake path, a welded K1 contact, a loop comparator failing "healthy"); their disposition by the hazard owner is open (IB-16, RSK-022). Section 9 states what the personnel-protection layers do and do not do.

Rules for every stage: stop at the first deviation, record every reading with units, and change one thing at a time. A failure that you cannot explain stops the project at that stage; do not continue "to see what happens".

## 0. What blocks what

| Block | Effect on this file | Source |
|---|---|---|
| RR-CHS-MAIN and RR-HEAD-ACQ are not fabricable: placed but **not routed** (chassis about 1260 connections open, head 1468), layout review pending; the head board front-edge connectors need a change (CR-H17) | stages B1 to B6 and everything after cannot start; stage S0 can | IB-74, IB-75, IB-71 (C-12), VT-048 |
| VL53L4ED driver is a stub | on hardware every ToF sensor is OFFLINE and the firmware refuses every motion direction: **no first motion on blocks (stage M1) until IB-04 is closed**; the way to test motion without the driver is not defined | IB-04; `firmware/chassis/README.md` Known gaps |
| LTC4162-F driver disabled, register map UNVERIFIED | `CHARGER_COMM` stays raised; SoC and charge state null; charge inhibit is hardware only; charger bring-up (stage C1) cannot be done through firmware | IB-05, IB-06 |
| Boot-time watchdog self-test not implemented; JP1 stays open until the first-strobe timing is measured | the section-7 step-5 test of `chassis_safety_chain.md` is not in firmware; the dynamic brake check is not implemented either | IB-60, IB-74, VT-055 |
| LATCH_UNEXPLAINED and STOP_ESCALATED are now used by the firmware (contract draft7 enums; `REARM_HELD` added in draft11) | none; note the hardware reason list in the ICD | `chassis_icd.md` section 10 |
| Head waveform capture not in the STM32 port; no on-head threshold-scan op | threshold scans are a host procedure over `ENG_SETUP_SET`, each step a new `setup_id` and a new handshake; monitor waveforms are viewed on the 50 ohm output with a scope | `firmware/head/README.md` Known gaps |
| Fit review: neither body can be assembled as modelled (rework in progress); the service pads SVC1-SVC10 must be reachable in the body | stages that need the robot (M1, M2, H attach) wait for the rework; board-level stages do not | IB-73, IB-74, IB-75 |
| No optical lane | stage H3 and every detector test in [05_first_bench_tests.md](05_first_bench_tests.md) wait for RFQ delivery | RFQ 0.4 |

## 1. Stage overview and bench-supply limits

Limits marked "source" are in the cited procedure; limits marked "proposed" are mine, with the calculated load they are based on. Raise a limit only to the next stage's value.

| Stage | Object | Supply and limit | Source |
|---|---|---|---|
| S0 | Software only (emulators, ROS simulation) | none | READMEs |
| B1 | Head board, unpowered checks | none | `layout_guidance.md` step 0 |
| B2 | Head board, first power, no SiPMs, no heater, lid input open, no pigtails | 12.0 V, **0.3 A** | `layout_guidance.md` section 7 (source) |
| B3 | Head board, bus side: isolated RS-485 adapter powering J2501 pins 3/4 with 5 V | 5 V from the adapter; BUS_5V draw under 80 mA transmitting expected | `layout_guidance.md` step 5 |
| B4 | Head board heater switch with a 4.7 ohm 50 W dummy on J2601 pins 1/2 from a second supply | second supply current limit not stated; the dummy draws about 2.6 A at 12 V (12 / 4.7, my arithmetic) | step 13; proposed limit 3 A |
| B5 | Chassis board, logic rails only, selector in SERVICE, no CM5, no LiDAR, no motors, no head | 12.0 V, **0.5 A** | `chassis_safety_chain.md` section 8 step 2 (source) |
| B6 | Chassis board, chain tests, then VMOT with motors fitted wheels free | 12.0 V; raise to **3 A** for the VMOT step | safety chain section 8 steps 7 to 10 (source) |
| B7 | Chassis board with CM5 and LiDAR running | proposed 2 A at 12.8 V; typical idle load 14.5 W (1.13 A) and all-maximum stack at idle 22.9 W (1.8 A) from `electronics/analysis/power_budget.md` section 2 (`calculated`) | proposed |
| C1 | Charger | laboratory 24 V supply, 3 A limit | `electronics/modules/external_24v_supply.md`; BOM W29a; blocked by IB-06 |
| PK1 | Pack connected for the first time | pack through the 20 A fuse (fuse not yet selected); pack max continuous 15 A, BMS over-current 25 A / 10 s, short-circuit 60 A / 0.5 ms (source: pack sheet [D]); the re-arm needs the pack at 11.7 V or more | `battery_pack_and_coupler.md`; proposed that the pack is first connected only after B6 passes on the bench supply |
| M1 | First motion on blocks | supply or pack; no source limit; proposed 3 A (the two motors draw 0.2 A each no-load, `power_budget.md`) | proposed |
| M2 | First motion on the floor, reduced speed | pack | proposed |
| H1 to H4 | Head attach, binding, detector tests | head from the chassis HEAD_PWR branch (1.5 A limit; head's own eFuse 1.0 A) | contract power rails; `head_afe_budget.md` section 6 |

## 2. Stage S0: software and emulators (can start now)

Commands are from the READMEs and were reported as run by their authors (`tool-checked`/`simulated`); I have not run them.

```sh
firmware/head/check.sh               # host build (ASan/UBSan), 6 ctest programs, STM32 image
firmware/head/check.sh --no-target   # without PlatformIO
firmware/chassis/check.sh            # pin map, host build, unit tests (2026-11-28: test_chain 337, test_state_machine 1195, test_review 65, test_rearm 65, test_drive 2476 checks), 10 integration tests, both STM32 images
firmware/chassis/check.sh --no-target
cd analysis/radiometry && ./run_all.sh
python3 interface/test_interface.py  # 15 baseline interoperability tests
python3 planning/check_registers_0.4.py
make check-fast                      # baseline, registers, harness, both firmwares (Makefile; about 3 min)
make check                           # check-fast + radiometry + small boards + mechanical + robot software
```

Run the robot software on the emulators (`ros2_ws/README.md`, needs Docker and the image `rad-roomba/ros2-ws:0.4`):

```sh
ros2_ws/tools/build.sh
ros2_ws/tools/run_sim.sh --auto           # deterministic sim, UI at http://127.0.0.1:8080/
ros2_ws/tools/run_sim.sh ros native:=true # against rr_head_sim and rr_chassis_sim already listening
```

Emulators: `firmware/head/build/host/rr_head_sim --seed 1` (TCP 127.0.0.1:5540, stimulus UDP 5541); `firmware/chassis/build/rr_chassis_sim` (TCP 5550, environment UDP 5551). They run the same C cores as the target (DEC-035). Known weakness of the composed node: the native scenario `native_s02` can fail under host load (IB-46, a fix for the chassis thread is in; "the flake is not claimed gone"); run on an unloaded host.

## 3. Emulator-in-the-loop arrangements (proposed)

The aim: each real unit is exercised against the emulated other half, so a failure is attributed to one side.

| Arrangement | Real | Emulated | How | Status |
|---|---|---|---|---|
| E1 Real chassis board, emulated head | RR-CHS-MAIN over USB CDC (`/dev/ttyACM0`) | `rr_head_sim` | `ros2 launch rr_bringup hardware.launch.py registry:=... head_url:=tcp://127.0.0.1:5540 chassis_url:=serial:///dev/ttyACM0 users:=...` (transports are URLs; the hardware launch needs a trusted head registry file, no default) | **proposed**: the serial transports are "untested (no hardware)" (`ros2_ws/README.md` section 5) |
| E2 Real head board, emulated chassis | RR-HEAD-ACQ over RS-485 at 1 Mbaud through an isolated USB-RS-485 adapter powering J2 pins 3/4 | `rr_chassis_sim` | `head_url:=serial:///dev/ttyUSB0?baud=1000000 chassis_url:=tcp://127.0.0.1:5550`; the emulated chassis has a simulated head-presence input (`pres_ohm`) so the host sees a head | proposed |
| E3 Head protocol alone | RR-HEAD-ACQ | host tools only | `firmware/head/tests/headsim.py` `Link` and the baseline tools `interface/wire_codec.py`, `head_discovery.py`, `check_frames.py` (examples in `interface/head_icd.md` section 9) | the Python helper was built for the emulator; use on a real serial port is not shown in any source |
| E4 Chassis protocol alone | RR-CHS-MAIN | host tools only | `firmware/chassis/tests/rrchs_client.py`: "needs a serial-port variant of the client" (chassis README item 9) | the serial variant is not written |
| E5 Development boards | NUCLEO-G474RE with the chassis image (protocol bring-up; with nothing connected every readback reads open and the mode is HW_INHIBIT/FAULT; USB on PA11/PA12 must be wired); head image `-e nucleo_bringup` with a 3.3 V RS-485 transceiver on PA9/PA10/PA12 and a pulse generator on PA15 (BUSY_F0) to see beta counts | host or emulator on the other side | per firmware READMEs | Nucleo solder-bridge details unchecked (UNVERIFIED) |

Dependencies introduced by the arrangement: with a real chassis and an emulated head, the stop reason `HEAD_LINK` and `HOST_LINK_LOST` behave as for a real link; the emulated head's identity (`--serial`, `--variant concept-e`) must exist in the registry. The emulated head advertises a `CONCEPT` geometry basis; an as-built descriptor needs a provisioning tool that does not exist (`firmware/head/README.md` Known gaps).

## 4. Stage B1 and B2: head board alone (proposed that this precedes any chassis work if the optics are the critical path)

Follow `electronics/head_acq/design/layout_guidance.md` section 7 step by step; the table below lists the expected values (design, `calculated`) and the stop condition. Bench supply 12.0 V, 0.3 A limit, no SiPMs, no heater, lid input open, no pigtails.

| Step | Expect | Stop if |
|---|---|---|
| 0 unpowered: resistance J2001.1-.2, HV_BUS-GND, +5V_A-GND, +3V3-GND; J2001.7-.2; J2001.5-.6 with three rail-switch connectors shorted pin 1-2; J2001.4 to GND | over 10 kohm; over 1 Mohm; over 100 ohm; over 100 ohm; 4.70 kohm +-0.1 %; 1.00 kohm +-0.1 %; open | any short; presence or loop resistor wrong; heater return connected to GND |
| 1 reverse polarity -12 V, 10 mA limit | under 1 mA | current flows |
| 2 +12 V, 0.3 A limit | 60 to 110 mA with the MCU blank; VIN_F 11.9 V; +5V6 5.63 +-0.11 V; +5V_A 5.00 +-0.10 V; +3V3 and +3V3_EVT 3.30 +-0.07 V; VREF_ADC 3.000 +-0.006 V; VBL 0.600 +-0.004 V | any rail out; **input current above 0.25 A**; a part warm to the touch |
| 3 sweep input 15 -> 7 -> 15 V | rails hold above 8.0 V; drop out at 8.0 +-0.3 V; return at 8.8 +-0.3 V | UVLO outside the window |
| 4 scope +5V6, +5V_A, VBL | +5V6 ripple under 30 mV p-p at 1.1 MHz; +5V_A and VBL under 1 mV p-p | visible switching ripple on +5V_A |
| 5 program the MCU over SWD; HELLO over RS-485 through an isolated adapter powering J2501.3/.4 with 5 V | reply; BUS_5V current under 80 mA transmitting; isolation J2501.4 to GND over 10 Mohm | no link: check DP/DN polarity (the ICD asks for a scope capture) |
| 6 latch self-test (LATCH_TEST), CLR lines, read-backs | all 20 latches set and clear; BUSY captures on TIM2/TIM5 | any latch stuck |
| 7 DACs mid-scale; baseline scan of every comparator | FAST baselines 0.60 V +-30 mV; noise edge width about 2 x 1.7 mV rms; raw LLD shows no chatter | baseline outside 0.45 to 0.80 V; oscillation |
| 8 pulser on each channel, amplitude scan, rate sweep 10 Hz to 200 kHz | counts = strobes at low rate; live time measured; FAST amplitude about linear in PULSER_AMPL; record mV at FAST per pC | missing or double counts; crosstalk counts on other channels at 5 p.e. equivalent |
| 9 **bias, no SiPM, straps as built (37 V boost, 31.5 V OVP).** Lid input closed (or bypass jumper recorded); HV_SET = 0, HV_EN high | HV_RAW 37 +-1 V; HV_BUS under 0.5 V; HV_SET 0.4 V gives HV_BUS 10.0 V; 1.0 V gives 25.0 +-0.2 V; step response without overshoot above 0.3 V; BIAS_VMON = HV_BUS/25.22; BIAS_IMON about 0.25 to 0.35 V | **HV_BUS above the set-point by more than 1 V at any time**; oscillation; HV present with HV_EN low |
| 10 interlocks: open the lid input; pull +5V_A down through its test pad current-limited; raise HV_SET until OVP | bias under 1 V in under 2 s each time and stays off until HV_EN is toggled; OVP at 31.5 +-0.7 V (firmware refuses set-points above 30.5 V: IB-18) | bias recovers by itself |
| 11 output short: 10 kohm, 1 kohm, then a short from a channel bias connector to ground | current limited at 2.0 +-0.3 mA; firmware flags; no part hot | current above 3 mA |
| 12 trim: each TRIM DAC 0.1 to 2.5 V, read the trim node on the anode U.FL centre and IMON_CH with a 100 kohm test load | node = code +-3 mV; IMON_CH = (25 V - trim)/100 kohm within 3 % | trim buffer oscillation |
| 13 heater: 4.7 ohm 50 W dummy on J2601.1/.2 with the cut-out sense wired, HEAD_HTR_P from a second supply; toggle HTR_EN | edges about 0.6 ms on, 3 ms off; HTR_SENSE 0.5 V/A; HTR_CUTOUT_OK follows the cut-out link in both states; dark-channel counts unchanged | edge faster than 0.2 ms; FET hot after 100 cycles at 1 Hz |

Firmware programming: SWD on PA13/PA14 with NRST (PG10); BOOT0 (PB8) strapped low; SWO unavailable (PB3 is a BUSY input). **None of the commands has been run against hardware.**

```sh
cd firmware/head
pio run -e rr_head_acq                      # build (platform ststm32@19.4.0 pinned; registry must be reachable the first time)
pio run -e rr_head_acq -t upload            # ST-LINK/V2 or V3 via OpenOCD
# or: STM32_Programmer_CLI -c port=SWD -w .pio/build/rr_head_acq/firmware.bin 0x08000000 -v -rst
pio debug -e rr_head_acq --interface=gdb
```

Debug console: UART4 on PC10 TX / PC11 RX, 115200 8N1, prints the firmware version and boot id at start. Image: flash 35 520 bytes, static RAM 86 044 bytes at the earlier build; the stage-2 firmware reports 92.7 kB of 128 kB (IB-58); use the numbers from your own `arm-none-eabi-size`. Persisted setup occupies the last 2 kB of flash; the page numbering for erase is recalled from the reference manual (UNVERIFIED).

Analog scale factors in `port/stm32g474/hal_stm32.c` and the DAC transfer function of the bias converter are placeholders (IB-15): treat all firmware-reported voltages and currents as uncalibrated until stage B2 steps 9 and 12 have produced the calibration.

Step 14 (fit the straps for the SiPM family, I-V sweep at 10 uA limit by firmware, dark scans) belongs to [05_first_bench_tests.md](05_first_bench_tests.md) tests T1 and T2. Then bench tests B1 to B12 of `head_afe_budget.md` section 11; conformal coat last.

IB-58 flags two things to watch in the first bring-up: scanning the anode-current monitor while counting may inject charge through the monitor taps (bench test needed), and the current monitor cannot see a dead or disconnected channel at -25 C.

## 5. Stage B5: chassis board, rails, programming, first power

Evidence: `electronics/analysis/chassis_safety_chain.md` section 8 (rewritten for the stage-5 netlist), `firmware/chassis/README.md` "First power-up observation list", `electronics/analysis/chassis_design_review_checklist.md`. The stage-5 chassis netlist self-check, ERC 0/0, DRC 0 errors and schematic parity are `tool-checked`; the board is **not routed** (about 1260 connections open, IB-74), so none of this can start until it is.

### B5a Logic rails

Bench supply 12.0 V, 0.5 A limit, selector in SERVICE (`chassis_safety_chain.md` section 8 step 2). Unpowered continuity first (HP-6): each switch loop under 1 ohm; CH_N0 to ground over 30 kohm (the source lowered this from 50 kohm); COIL_RTN to ground under 1 ohm with the E-stop released and open with it pressed; K2/K3 motor terminal A to B about 0.7 ohm; motor terminals to bridge outputs open. Then: expect 3V3, V5_AUX, VREF 3.000 V; CH_N1 = 0 V; all readbacks low; `LATCH_NC_RB` high; VMOT 0 V. Selector in RUN: operate each device in turn and note the node that falls and the readback bit.

Further rail and branch checks (`chassis_design_review_checklist.md` section B, all open): 5 V compute rail at the carrier at least 4.85 V at 5 A and surviving an MCU reset; each eFuse limit measured (the checklist lists 5.0, 1.5, 4.05, 3.04, 1.5 A and VMOT 6.5 A; the HEAD_HTR value is **3.96 A nominal, trip band 3.56 to 4.35 A** in the contract, C-13); branch defaults with the MCU held in reset (5 V on, LiDAR on, head and heaters off); head branches forced off with 24 V on the inlet; inrush at selector-on into 500 uF below 5 A peak. Heater pair: the Micro-Fit contact is recalled at about 3.13 A continuous (UNVERIFIED) and the head firmware cuts at 3.2 A for 300 ms against a chassis trip of 3.56 to 4.35 A: a gap in hardware protection (IB-69, VT-071); do not run the heater at 12 V for long until the contact rating is read from the manufacturer document.

### B5b Programming

```sh
cd firmware/chassis/port/stm32g474
pio run -e rr_chs_main                      # 8 MHz crystal; -e rr_chs_main_24mhz for 24 MHz
pio run -e rr_chs_main -t upload            # ST-LINK, SWD 10-pin Cortex header
pio debug -e rr_chs_main
# USB DFU (UNVERIFIED for this part, check AN2606): hold BOOT0 during reset, then
# dfu-util -a 0 -s 0x08000000:leave -D .pio/build/rr_chs_main/firmware.bin
```

Debug UART: USART3 PC10/PC11 115200 8N1, 3.3 V. Do not hold the MCU halted in a debugger while traction is armed: the watchdog opens the chain (intended). **JP1 (watchdog output to NRST) stays open until the first-strobe timing has been measured (VT-055)**: the port toggles WDI during init, but the HSE start-up timeout and the I2C probes before the first control tick are not covered by a guaranteed WDI edge within the TPS3430 window (23 ms of reset release); with JP1 open the watchdog still opens the chain through WDG_OK, and only the MCU's own IWDG resets the MCU (`firmware/chassis/README.md` Known gaps; `chassis_icd.md` section 10). With JP1 closed the strobe-stopping fault flags reset the MCU every few hundred ms. The boot-time watchdog self-test is not implemented (IB-60).

### B5c First-power observation list (wheels off the ground, current-limited supply, debug UART connected before power)

From `firmware/chassis/README.md` (simulated expectations; check.sh results on 2026-11-28: `test_chain` 337, `test_state_machine` 1195, `test_review` 65, `test_rearm` 65, `test_drive` 2476 checks, 10 integration tests):

1. MCU erased or in reset: ARM_PERMIT low, REARM cannot set the latch, bridges asleep, head and heater branches off, 5 V rail up, FAULT annunciator lit. **Stop if the latch can be set or any branch is on.**
2. Banner within 0.5 s: `rr-chassis 0.4.0+stm32g474 RR-CHS 1.0 ...`, `reset=POWER_ON clock=HSE config=DEFAULTS boot_id=<uuid>`; `clock=HSI-FALLBACK` = crystal not running; a changing boot_id = reset loop.
3. Status line once a second; heartbeat LED; five annunciators for 0.2 s at boot, one chirp.
4. Dummy head docked, J1/J2 mated, E-stop released, covers shut: `mode=STANDBY`, `live=00000000`, `pres_ohm` 4500 to 4900, `vbat_mV` within 2 % of the supply, `vmot_mV` under 1000. Expected faults on this revision: `CONFIG_DEFAULTED`, `CHARGER_COMM`, `TOF_BUS`. `IOX_B`/`PERMIT_STUCK_OFF`: CHAIN_END_RB cannot be read: no arming.
5. `mode=FAULT` means `ESTOP_DISCREPANCY`, `IOX_A`, `ADC`, `LATCH_STUCK` (**stop**), `PERMIT_STUCK_ON` (**stop**), `CHAIN_IMPLAUSIBLE` (**stop**), and since the reviews also `K1_WELD`, `RUN_SHORT`, `LOOP_SW_SHORT`, `LOOP_FAIL`, `LATCH_NO_REARM`, `LATCH_NO_DROP`, `PIN_CONFIG`, `IOX_D`, `TIMING` (`chassis_icd.md` section 9): a **power cycle and an inspection of the chain hardware** before use; do not return a latch, loop or permit fault to service until the hardware fault is found.
6. Operate each chain element in turn (section 6 table).
7. Scope WDG_STROBE: a 5 ms high pulse every 10 ms (the TPS3430 is falling-edge triggered, tWDL at most 2.22 ms, tWDU at least 23.375 ms, calculated from the datasheet read 2026-11-27); WDG_OK high. Check the first edge comes within 23 ms of reset release before closing JP1. Halt the CPU: WDG_OK must drop and the latch must not be settable.
8. **Re-arm** (section 6a). With no host connected the mode becomes `PROTECTIVE_STOP` (`HOST_LINK_LOST`) after 1 s: expected.
9. Connect USB: CDC-ACM enumerates (placeholder VID:PID 1209:0001); `HELLO` returns the banner's boot_id.
10. `BRAKE_TEST` (about 2.2 s; keep polling; host reply timeout at least 3 s): `passed:true`, latch drop under 50 ms, VMOT below 1 V after about 2.1 s (tau 0.8 s bleed; the limit `brake.vmot_decay_max_ms` is now 3500 ms; worst case 2.65 s calculated), probe currents about 0. The brake test now also checks that K1 is not welded (LATCH_NC_RB high; no latch rise after ARM_PERMIT is raised again for 120 ms with no REARM). Press REARM again when ready.
11. First motion: stage M1.
12. Press E-stop while turning: wheels stop at once without firmware action, `mode=HW_INHIBIT hw=00000002`, nothing restarts on release.

## 6. Stage B6: hardwired traction chain tests (VT-039, VT-053, VT-054, VT-080, VT-081)

**Procedure source:** `electronics/analysis/chassis_safety_chain.md` section 8 (stage-5 rewrite), VT-039 and the register tests above; evidence `calculated` and `simulated` (the emulator follows the stage-5 netlist; it is not hardware). Wheels off the ground, current-limited supply, a record of every drop time with scope on RUN_HD, RUN_12V and a brake-relay NC contact. **Stop at the first deviation.** The hardware latch is set only by the local REARM button, with every element healthy and ARM_PERMIT high; no protocol op, including `REARM_SW`, can set it.

### 6a Re-arm as the firmware now behaves (read before the first REARM press)

- **Press briefly, and only when the robot reports ready.** `rearm_ready` (REARM lamp blinking; `STATE.rearm_ready`) means the set stage's comparator SET_READY has been high for 30 ms: about 3.2 s after the chain closes at 12.8 V (worst case 4.2 s; simulated 2.8 to 4.6 s over pack 11.6 to 13.4 V and C_SET 80 to 120 uF). A press while not ready does nothing to the set reservoir and is refused with a reason within 300 ms. Hold the button for less than 2 s; the buzzer beeps fast from 1 s of holding; a contact still closed **5 s** after the latch rose drops the latch again (`REARM_HELD`). A press shorter than 3.2 ms cannot set; presses of 2 to 6 ms are refused or `PARTIAL`, 8 ms set or `PARTIAL`, 12 ms and longer always set (simulated tap sweep).
- **Every press gets an outcome**: the latch rises, or `REARM_REFUSED` with a reason (`STATE.rearm_refusal`; the REARM lamp blinks fast for 2 s). A refusal is never a fault and never needs a power cycle.

| Refusal reason | Meaning | What to do |
|---|---|---|
| `NOT_READY` | the set stage is not charged | wait for the lamp to blink, press again |
| `SUPPLY_LOW` | pack below about 11.7 V and not ready (`"action":"CHARGE_OR_SWAP_PACK"`) | charge or swap the pack; on the bench raise the supply |
| `COIL_HOT` | the coil estimate is above 45 C (a warning also exists) | let the robot cool; the press is still offered and may be refused |
| `CHAIN_OPEN` | an element is open | find and close it (live reasons on the page) |
| `REARM_HELD` | button held, or held 5 s after the rise | release the button, press briefly |
| `PERMIT_WITHHELD` | firmware is withholding ARM_PERMIT | read the faults and mode |
| `LOOP_TEST` | the loop self-test is running or pending (about 90 ms) | press again |
| `FAULT_OR_MODE` | fatal fault, BOOT/FAULT/LAB/SERVICE_CHARGE | power cycle and inspect for a fatal fault |
| `TOO_SHORT` | set contact closed under 12 ms: nothing happened | press for longer (but under 2 s) |
| `PARTIAL` | the set did not complete (K1 sealed by its own contact without U_HOLD); ARM_PERMIT dipped for 30 ms | press again at once; repeated `PARTIAL` after service tests means S3 |
| `SET_FAILED` | the hardware did not set although offered | check the set stage (S3), the coil temperature |

**Operating limits created by the chain** (one statement for all documents; `chassis_safety_chain.md` section 6.1, `chassis_icd.md` section 4.6, all `calculated`/`simulated`): re-arm needs the pack at **at least 11.7 V** worst case (11.4 V nominal) while the battery-low protective stop is at 11.2 V, so between 11.7 and 11.2 V an armed robot drives on but cannot re-arm after a stop; the firmware warns `BATTERY_REARM_LOW` at 12.0 V resting (for at least 10 s); re-arm is **not guaranteed above a coil temperature of +45 C** (`COIL_HOT`, board NTC at K1 plus 10 K self-heating with tau 300 s); there is **no hardware speed or force limit** (0.44 m/s no-load, 93 to 170 N at stall; firmware caps only) and **no holding brake** (the braked robot is calculated to stop on downhill slopes only up to about 3 to 6 degrees, 6 to 10 degrees at nominal friction; beyond that it creeps at 12 to 36 mm/s). Never describe the robot as holding on a slope.

### 6b Bench procedure (`chassis_safety_chain.md` section 8, steps 1 to 15)

| Step | Action | Expect | Source class |
|---|---|---|---|
| 1 to 2 | Unpowered continuity; logic rails (B5a) | as B5a | |
| 3 | Decade box on J1 pins 5-6: channel A (U21) on between 0.59 and 1.55 kohm (+-5 %), off at 0 ohm, open, and either pin to ground or 12 V through 1 kohm; channel B (U21B) on below 1.89 kohm (+-3 %), off above and open. With 1.0 kohm fitted assert LOOP_TEST_A (test firmware): CHN6A_RB must fall and the chain open; repeat with LOOP_TEST_B (BODY_BUMPER_L_RB must fall). Bridge U21's output with a wire and repeat TEST_A: the chain must still open (U21B) and CHN6A_RB stay high; same for U21B with TEST_B. Log HEAD_LOOP_SENSE at 0.6, 1.0, 1.6 kohm (1.79, 1.56, 1.32 V expected) | as stated | calculated |
| 4 | Decade box on J1 pins 7-2: U22 on only between 3.92 and 5.64 kohm; 1.137 kohm, 1.50 kohm, open and short give off | | contract |
| 5 | Plug link J_PWR 4-8: CH_N4 falls; 24 V through 1 kohm on the inlet pins: CH_N4 falls | | |
| 6 | Watchdog and permit (test firmware): no strobe -> CH_N9 low; falling edge every 10 ms -> high; every 1 ms and every 40 ms -> low; ARM_PERMIT low/high -> CHAIN_END follows; MCU held in reset: CHAIN_END low; drive IOX_A GPB7 as an output with PB11 high-impedance: WDI must stay below 1 V | | |
| 7 | Latch and set stage: log SET_READY_RB and C_SET from chain closure: SET_READY must rise at 10.6 to 11.0 V and the time must agree with T12 (`chassis_braking_tables.md`) at the bench voltage; a press 1 s before SET_READY: nothing happens and C_SET keeps charging; a press at SET_READY: arms; at 11.5 V supply SET_READY must not come; a 2 ms tap of set and aux together: no set. Armed: K1, U_HOLD, U_LS, K2, K3 pick up; RUN_12V = supply minus under 0.8 V; chain current 85 to 110 mA. Then each of these must **not** set the latch (all elements closed, C_SET charged): (a) V12_AUX on J_BTN pin 2 without the aux contact; (b) J_BTN 3-4 bridged permanently, cycle an element; (c) LAMP_REARM_K on J_BTN pin 2 with the lamp blinking; (d) J_BTN 1-2 shorted permanently, cycle an element; (e) press REARM while an element is open and close the element within 0.1 s. (f) Hold REARM and open any element: everything drops and does not return while held. (g) With Q_SETB's gate tied low, then Q_SETA's: a press must not set | as stated; firmware must fault within 0.2 s where it sees a latch rise | calculated; VT-053, VT-080 |
| 8 | Each element drops the latch (each E-stop pole alone by lifting one wire); scope RUN_HD, RUN_12V and a brake-relay NC contact | time to NC closure at most 10.8 ms (13.3 ms for the loop channels and PRES_ID); pulse-width test: open ARM_PERMIT for 0.5, 1, 2, 5 ms: expect the shortest that drops the latch at most 2 ms (assumed) | calculated |
| 9 | Weld simulation: arm, drop, bridge K1 pins 9-8 (pole B): re-close without REARM: RUN_HD and RUN_12V stay dead, LATCH_RUN_RB high; repeat with pins 4-5 (pole A): K1 picks up, RUN_HD stays dead, LATCH_NC_RB low | | VT-053 |
| 10 | RUN_12V short: latch dropped; RUN_12V (TP39) to VBAT_SW through 10 ohm: K2/K3 stay released, VMOT 0 V | | VT-081 covers D_RUN leakage |
| 11 | VMOT: limit 3 A; arm: VMOT rises in 2 to 5 ms; drop: eFuse off within 1.5 ms, VMOT under 1 V within 3 s | | |
| 12 | Brake readback: dropped: BRAKE_x_RB low; jumper one bridge output to its motor terminal: high | | |
| 13 | Braking: motors fitted, wheels free; spin-down at the 0.20 m/s equivalent with the brake resistor and once lifted (coast); repeat with the motors warm | time constants replace the inertia and friction assumptions | VT-045, VT-056 |
| 14 | Bus clamp: pack disconnected, series diode; back-drive a wheel | VMOT at most 16.0 V; BUS_CLAMP_ACTIVE pulses | |
| 15 | On the floor, restrained: stopping trials at 0.05, 0.10, 0.20 m/s for every initiating element; a holding test on the steepest ramp in the operating envelope | | VT-003, VT-004 |

Each chain element, how to open it, and what the chassis must report (`chassis_icd.md` section 4.4; bit order in `firmware/chassis/README.md` item 6; elements behind an open one read "unknown", not as a second cause):

| Element | How to open it | `hw_inhibit_reason` | live bit |
|---|---|---|---:|
| MODE_RUN | selector out of RUN | MODE_NOT_RUN | 0 |
| ESTOP | press the mushroom; then each pole alone by lifting one wire | ESTOP | 1 |
| HANDS_ON | engage the maintained button | HANDS_ON | 2 |
| CHG_COVER | open the inlet cover; separately insert the plug link | CHARGER | 3 |
| HEAD_DOCK | release the dock switch | HEAD_UNDOCKED | 4 |
| HEAD_LOOP | open the loop (press a rail switch or the decade box above 1.9 kohm); short it; unplug J1 | HEAD_LOOP_OPEN; HEAD_LOOP_SHORT; J1_ABSENT | 5, 6, 7 |
| LAB_KEY_N | present the LAB code (1.50 kohm in the PRES_ID position) | LAB_KEY | 8 |
| BODY_BUMPER | press each bumper switch | BODY_BUMPER | 9 |
| WDG_OK | stop the strobe (test firmware) | WATCHDOG | 10 |
| ARM_PERMIT | firmware withholds it | MCU_NOT_READY (stop escalation or the head-loop rule: STOP_ESCALATED) | 11 |
| (VMOT checks) | VMOT absent while latched, or present after the drop | VMOT_FAULT | 12 |
| (REARM contact held) | hold the button | REARM_HELD (new in contract draft11) | |

A lifted single E-stop pole opens the chain in hardware; a pole discrepancy over 200 ms enters `FAULT` (`ESTOP_DISCREPANCY`), cleared only by an MCU reset. Latched hardware reasons stay reported until the next successful local REARM.

### 6c What the stage cannot show: the residual single faults in plain words

`electronics/analysis/chassis_safety_chain.md` section 6.1 (calculated and simulated; the hazard owner's disposition is open, IB-16, IB-74): the robot **will not stop for** these single faults, because no hardware barrier is left for that zone:

1. A **welded head-rail switch** (that zone) or a head-internal bypass of the switch string that leaves the 1.00 kohm in circuit. Not detectable at the chassis. Simulated: the robot keeps moving, 182 mm in a 2 s REARM press case. The pre-use rail press is the only check.
2. A **welded or shorted body-bumper switch**, or its wiring, left or right (single contact per side): simulated 95 mm when reversing; rear and quarter contact then rests on the firmware rear ToF only.
3. A kohm-level **leak from the shared loop sense node LOOP_SNS to a 3.3 or 5 V supply**: both loop channels share the sense resistor pair.
4. A **board short of RUN_HD, K1_RUN or CHAIN_END to a supply**: only E-stop pole B (RUN_HD at once; K1_RUN and CHAIN_END after the next REARM) and DRV_NSLEEP remain; detected and the bridges kept asleep (simulated 11.9 mm), but the relays and VMOT are live.
5. A **multi-conductor crush of W-018** (both REARM lines at once): it arms the robot once, for 5 s; every element still drops it.
6. A **welded HANDS-ON contact** or the W-017 lamp-to-contact short: the person at the wheels has no hardware barrier; procedure: never work at the wheels unless the HANDS-ON lamp is lit.
7. A **welded selector RUN contact**: SERVICE no longer opens the chain; procedure: use OFF, not SERVICE; P1.4 checks it.
8. A **multi-conductor crush of W-015** that shorts both E-stop pairs without taking CH_N1 to ground: the E-stop is lost.

Also not shown: an open brake path (fault 46) is not detectable at standstill (dynamic check requested, not implemented); a shorted U_HOLD, U_LS, D_RUN or RELAY_RTN path and an open R_RHD are latent and are covered only by the six-monthly service tests S3 to S8 of [../service/05_maintenance_and_spares.md](../service/05_maintenance_and_spares.md); the watchdog-device boot test and the dynamic brake check are not implemented. Where **D_RUN reverse leakage** at 60 to 100 C could keep U_LS lit so that K2 and K3 do not release after a drop (no dynamic braking for that stop; calculated 38 to 114 mm instead of about 10 mm from 0.20 m/s), VT-081 measures it.

## 7. Stages after the board: M1, M2

### M1 first motion on blocks (wheels free) and the brake characterisation

Preconditions: B5 and B6 pass; the robot is assembled and the fit-review rework is verified (IB-73); IB-04 closed (otherwise the firmware refuses every direction); dummy head docked and J1/J2 mated, so HEAD_DOCK, HEAD_LOOP and PRES_ID are healthy; E-stop and HANDS-ON within reach; REARM and brake test done. Mode `COMMISSIONING`, 0.02 m/s (firmware README item 11):

- Arm with the re-arm procedure of section 6a (press briefly when the lamp says ready). After any hardware inhibit, FAULT or reset the host must not resume by itself: the robot software must wait for an explicit operator decision (`chassis_icd.md` section 9, VT-067).
- Buzzer for 1.5 s (pre-motion alert), then both wheels turn **forward** and both tick counters count **up**. Stop if a wheel runs away or turns the wrong way (`ENCODER_FAULT` within 0.1 s is the expected reaction to swapped encoder phases or a reversed motor), or the current reads zero while the wheel turns (IPROPI scaling).
- Left/right: the motor connectors are not coded; a wheel-up test finds a swap (`harness/README.md`).
- Run each wheel at the 0.20 m/s equivalent and open the E-stop; record the encoder spin-down with the brake resistor fitted and once with it lifted (coast): rotor inertia and friction replace the assumptions (VT-045, safety chain step 12). Calculated stopping distances to compare, from 0.20 m/s: 8.8 mm nominal and 28.6 mm conservative, 57 mm MCU-failure case; from 0.10 m/s 3.8 / 14.3 mm; with 100 C windings 9.8 / 34.2 mm (`chassis_safety_chain.md` sections 1 and 4; chain step 12 is now step 13 of the stage-5 procedure). The emulator after IB-03 reports 8.5 / 28.5 mm at 0.20 m/s and 3.6 / 14.2 mm at 0.10 m/s (`simulated`). Rotor inertia is the dominant unverified input.
- Command timeout: stop sending `DRIVE`; `CMD_TIMEOUT` latches within the TTL (VT-046). Withhold requests for 1 s: `HOST_LINK_LOST`.
- Look/cliff/rear sensors: see test T9 in 05 (requires IB-04).
- Slope holding (6 degrees calculated, 3 degrees at half friction) is measured later with the robot on the floor; no parking brake is fitted.

### M2 first motion on the floor at reduced speed (proposed)

Not defined in any source as one procedure; the elements are VT-003, VT-004, VT-005 and the guarded floor rig of `gap_measurement_method.md`. Proposed: guarded rig with edge guards and an independent fall restraint, dummy head, 0.05 m/s then 0.10 m/s, then 0.20 m/s only in `COMMISSIONING`, stop-distance measurement for every initiating element at 0.05, 0.10, 0.20 m/s (safety chain step 14), each with the E-stop within reach and the robot never within reach of a person's feet for those trials (use test targets). Speed caps by mode are provisional (`chassis_icd.md` section 6.1): COMMISSIONING 0.20 forward / 0.05 reverse, SURVEY_SHARED 0.10 / 0.05, GUIDED 0.10 / 0.05, LAB and SERVICE 0.

## 8. Stage H: head attach, detach and binding

1. **Detached bench use** (LAB): build and accept the LAB extension first (`harness/lab_extension.md` section 7, nine tests: continuity, 1.485 to 1.515 kohm resistor, presence decode, 0.125 ohm loop budget with 0.094 ohm expected, insulation, shield, no third termination, pull test, heated run). With the extension fitted traction is hard-inhibited by two independent conditions (undocked and LAB code); head power is permitted.
2. **Attach** the head: shoes into the channels from the front, push to the x-stops, close the draw latch, plug J1 and J2. HEAD_DOCK must read closed only with the latch closed and the head fully seated (VT-009).
3. **Power**: `HEAD_POWER {electronics, heater_enable}`; the branches are forced off at every MCU boot and in SERVICE_CHARGE; request is rejected with `HEAD_ABSENT` or `PRES_FAULT` if the presence code is wrong.
4. **Handshake and binding** (protocol 2.0): `HELLO` from any state aborts acquisition; `GET_DESCRIPTOR` (1972 bytes for the concept head, chunked, SHA-256 checked), `BIND`, `TIME`/`SYNC`, `ARM`, `READ`. A setup change invalidates the binding; the head swap, MCU reset between HELLO and BIND, stale BIND and CRC retry cases are the VT-033 list. Time bound for mapping at most 10 ms (target 2 ms).
5. **Detach**: park, disable head power, verify power off, remove J1/J2, open the latch, slide the head 66 mm forward (`assembly.md` removal procedures); fit the protective cover on the downward window and use a designated handling surface (`head_icd.md` section 2).

## 9. Before the robot may move near a person

This list defines the minimum, not a certification. **None of it is satisfied today.** All are pending trials: braking, personnel protection, cold, radiometric.

| Condition | Evidence required | Status |
|---|---|---|
| Hardwired chain passes VT-039 on the assembled robot, with each element opened and the drop time recorded | VT-039 | pending |
| Stop distances measured (not calculated) at 0.05, 0.10, 0.20 m/s for every initiating element, in both directions and in turns, on the approved floors | VT-003, VT-045, IB-03 inputs measured | pending |
| Head rail and body bumper stroke after trip at least equal to the measured stopping travel at the permitted approach speed (calculated travel after contact at 0.10 m/s is 14.3 to 27.5 mm; designed rail stroke 15.6 mm calculated) | VT-005, IB-11, RQ-061 | pending: "stopping inside the rail travel is not demonstrated at any survey speed" (architecture section 6) |
| Edge and look-ahead behaviour with dark, wet, shiny and missing returns; ToF driver integrated | VT-004, IB-04 | pending |
| Occupied-area detection and measured stopping margin | VT-035 | pending |
| Site decisions on edge, access and recovery policy, unattended protections, alert route | DEC-004, DEC-017 | open |
| Hazard-owner disposition of the residual single faults (section 6c) and the latent faults | IB-16, IB-71, IB-74, RSK-022 | open |
| Chain re-arm, latent-fault controls (loop self-test at every arming, P1 per shift, service tests S3 to S8 every six months) in operation, including the reachability of the service pads in the body | IB-74, `chassis_safety_chain.md` section 6.2 | pending |
| Watchdog first-strobe timing measured and JP1 decision; dynamic brake check implemented | VT-055, IB-74 | pending / not implemented |
| Cold: head heater short of capacity at 10 V in moving air at -25 C (calculated); bay pre-heat 95 to 200 min from a -25 C soak (pack-to-body coupling 0.6 W/K assumed); caster and tyre below -20 and -10 C | IB-62, IB-64, VT-057, VT-059, VT-072 | pending |

Limits of the layers (as `docs/architecture/SYSTEM_ARCHITECTURE.md` section 6 states them):

0. Hardware limits created by the chain itself (section 6a): no hardware speed or force limit and no holding brake; re-arm needs 11.7 V; no guaranteed re-arm above +45 C at the coil. The reviewers would sign the chain description, the single-fault list and the operating limits, **not** the latent-fault control until the service-test reachability and S1/S6 fixes are accepted (`REVIEW_traction_inhibit_stage4.md`).
1. Inherent limitation: at most 12 kg, 0.20 m/s forward, 0.05 m/s reverse, yaw rate limited so the outer head corner stays under 0.10 m/s, wheel current limit, rounded surfaces. Push force "expected to be traction-limited; to be measured".
2. Contact detection wired into the chain: head rail (front, left, right) and body bumper. The rail must give at least 15 mm of stroke after it trips; Rev D had none. Until measured, stopping inside the rail travel is not demonstrated.
3. Near-field ranging in the motion MCU: 4 downward cliff, forward look pair, rearward look pair, 3 rear proximity sensors. **The MCU has no forward or sideways personnel ranging.** In those directions the only protection that does not depend on the Linux host is contact (head rail) plus the speed and force limits (IB-13).
4. Route hold in the host from LiDAR returns inside the swept region of the commanded move. The LiDAR is not a protective device and the host software runs on Linux; it can fail.
5. Hands-on work: the HANDS-ON button and the E-stop, both hardwired.

Two further limits: the Pause button on the robot is a program control that the controlling operator can clear remotely (`REARM_SW`); only E-stop and HANDS-ON are local-only (owner decision 2026-11-26, RSK-034). A bumper or E-stop trip ends an unattended mission until someone attends (DEC-026, RSK-035).

Until those conditions are met: first motion only on blocks or on the guarded rig with no person within reach; the robot unattended is not permitted by this document.

## 10. Open items

| Item | ID | Status |
|---|---|---|
| VL53L4ED driver | IB-04 | Open (external); blocks M1 |
| LTC4162-F pin map, driver | IB-05, IB-06 | Open |
| Boot-time watchdog self-test and dynamic brake check not implemented; JP1 open until VT-055 | IB-60, IB-74 | Open |
| Contract `hw_inhibit_reason` (draft11) and the ICD section 4.4 now both list LATCH_UNEXPLAINED; REARM_HELD is described in ICD section 4.6 and in the contract; the earlier contradiction (IB-63) is closed on this point | `chassis_icd.md` sections 4.4, 4.6 | closed |
| Undetected single faults | IB-16 | Open |
| Brake resistor text and clamp wording (1.0 ohm against 4.7 ohm in older text, clamp 2 x 9.1 ohm) | IB-24 | Open in the electronics text |
| ToF cliff and rear thresholds are placeholders; look tolerances 60 / 40 mm are an engineer's choice | IB-60 | Open |
| Head analog scale factors, bias DAC transfer function (placeholders) | IB-15 | Open |
| Head: monitor-scan charge injection; dead-channel detection at -25 C; BIAS_VMON divider tolerance; late service interrupt FIFO overflow | IB-58 | Open |
| Serial transports of the ROS workspace untested; stand-alone nodes never run | IB-49 | Open |
| Emulator-in-the-loop mixed arrangements E1, E2 are my proposal | not yet defined | no backlog ID |
| A single procedure for first motion on the floor | not yet defined | VT-003, VT-004, VT-005, VT-035 pending |
| Procedure for a first pack connection (current limit, fuse) | not yet defined | no backlog ID |
| Reply-time and control-tick execution-time budgets unmeasured | VT-046 | Pending |
| Head stage 3: monitor-scan disturbance with the muxes off; frame monitor limits; heater over-current cut at 3.2 A (contact rating UNVERIFIED) | VT-078, VT-079, VT-071 | pending |
| MODEL.md revision 5 host implementation in progress (`ros2_ws/STATUS.md`); IB-72 fixes being assigned | IB-72 | open |
