# Handoff for Codex — Milestone 2A: firmware and emulators, radiometry, EDA flow, mechanical layout

| | |
|---|---|
| Repository | https://github.com/Skyence13/Rad-Roomba |
| Pull request | https://github.com/Skyence13/Rad-Roomba/pull/1 |
| Base | `main` @ `38d101051d32b47e4b21657e2293ec92c63de9c4` |
| Previous milestone head | `8872c2f` (M1) |
| Reviewed commit | the commit that adds this file (stated in the pull-request comment) |

Everything here is `tool-checked`, `simulated` or `calculated`. Nothing has run on hardware and nothing is physically measured. Commits titled "Work-in-progress snapshot" contain unreviewed files from work still under way (ROS workspace, circuit designs); they are **not** part of this milestone.

## Scope of this milestone

| Path | Content | Lead verification |
|---|---|---|
| `firmware/common/` | Portable C11 library: record codec, JSON, REQ/RSP envelope with reply cache, CRC-32, SHA-256, base64, UUID. | Built and tested as part of both firmware checks. |
| `firmware/head/` | Head protocol 2.0 core, MCU event capture (no FPGA, DEC-037), `rr_head_sim`, STM32G474VET6 port, 100-pin pin map. | Clean rebuild + `check.sh` exit 0. |
| `interface/head_icd_addendum_0.4.md` | What 0.4 pins down or adds without changing protocol 2.0 (DIAG, STATUS, engineering ops, retry and holdover rules). | Read; baseline schemas untouched. |
| `firmware/chassis/`, `interface/chassis_icd.md`, `interface/chassis_link.schema.json` | RR-CHS 1.0 server, mode state machine, chain supervision, software stop latch, drive loops, `rr_chassis_sim` with plant model, STM32G474RE port, pin map. | Clean rebuild + `check.sh` exit 0. |
| `analysis/radiometry/` | `rrrad` library, detectability study, Monte Carlo, demo calibration/profile, `MODEL.md` rev 2, `MODEL_REVIEW.md`. | `run_all.sh` exit 0 (≈ 85 s). |
| `tools/eda/`, `tools/docker/`, `electronics/tof_carrier/` | Scripted KiCad 9 flow and the RR-TOF-A proof board (native project, routed, fabrication outputs). | Rebuilt from scratch with `--reroute`: PASS. |
| `mechanical/common/` | Parameters, frames, board envelopes, purchased-part library, envelope-level Rev E layout, mass/tip/deflection/gap/thermal calculations, gap measurement method. | `build.sh` exit 0. A head-mount trade study and the 12 Ah update are still in progress in this directory. |
| `interface/system/contract.yaml` (0.4.0-draft4), `docs/architecture/SYSTEM_ARCHITECTURE.md` | Decisions DEC-037…041 and accepted change requests. | — |

## Prerequisites

Ubuntu 24.04 or similar with `gcc`, `cmake`, `ninja`, `python3` (3.12+ with `pyyaml`, `jsonschema`), PlatformIO Core (`pip install platformio`), Docker with images `kicad/kicad:9.0` and `ghcr.io/freerouting/freerouting:latest`, and `uv` for the CadQuery environment.

## Reproduce

Head firmware (host tests under ASan/UBSan, baseline interoperability, STM32 image):

```bash
firmware/head/check.sh
```

Chassis firmware (unit tests, integration tests against the emulator, both STM32 variants):

```bash
firmware/chassis/check.sh
```

Radiometry (61 unit tests, all tables, figures and the report; deterministic):

```bash
cd analysis/radiometry && ./run_all.sh
```

EDA proof board from scratch (generate, route, ERC, DRC with schematic parity, outputs):

```bash
python3 tools/eda/rrkicad.py build electronics/tof_carrier/board.py --reroute
```

Mechanical layout and calculations:

```bash
cd mechanical/common && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt && RR_PY=.venv/bin/python ./build.sh
```

Baseline regression:

```bash
sha256sum -c SHA256SUMS.txt && python3 software/map_demo.py --self-test && python3 interface/test_interface.py
```

## Results observed by the lead

| Check | Result | Class |
|---|---|---|
| Head: 5 CTest groups (common unit, Python codec interop, core unit, event-capture unit, emulator interop with baseline host tools) | all pass | tool-checked |
| Head: baseline `interface/test_interface.py` | 15 OK | tool-checked |
| Head: STM32G474VE image | links; 35.0 kB flash, 84.5 kB RAM | tool-checked |
| Chassis: `test_chain` / `test_state_machine` / `test_drive` | 245 / 1160 / 2464 checks, 0 failures | tool-checked |
| Chassis: Python integration against `rr_chassis_sim` | 8 tests OK | simulated |
| Chassis: STM32G474RE image, 8 MHz and 24 MHz variants | link; 80.2 kB flash, 21.9 kB RAM | tool-checked |
| Radiometry `run_all.sh` | exit 0 | calculated / simulated |
| RR-TOF-A | ERC 0 errors 0 warnings; DRC 0 / 0; unconnected 0; schematic parity 0; no waivers | tool-checked |
| Mechanical `build.sh` | exit 0; interference, cavity, sight-line and access checks pass on nominal envelopes | tool-checked / calculated |

Figures reported by the subsystem owners and **not** independently re-derived by the lead: the event-capture rate sweep (corrected rate within 0.5 % of truth from 10 to 20 000 s⁻¹, ≈ 9.7 µs dead time per event, simulated), the simulated chassis stop distances (e.g. 14.8 mm from 0.20 m/s on latch drop with an assumed brake resistor and friction), and all radiometric detection limits (assumed response coefficients).

## Evidence for the important decisions

- **No FPGA (DEC-037).** Assumed rates are a few to about 2000 s⁻¹ per chain; the simulated capture logic stays unbiased to 20 000 s⁻¹ with measured dead time. `firmware/head/core/rrh_evtcap.c` and its tests.
- **Single pass does not reach 0.20 Bq/cm² (assumed K = 24 s⁻¹ per Bq/cm²).** `analysis/radiometry/report/detectability_report.md`; hence the survey methods of DEC-038 (ratemeter search then scaler count, step-and-count, continuous scan).
- **Null variance must not use the same-gate reference rate.** `MODEL_REVIEW.md` R1; fixed in `MODEL.md` rev 2 §3.
- **Rev D body cannot contain the hardware (DEC-039).** `mechanical/common/out/layout_report.md` §3: about 1.84 L cavity for 2.14 L of bare envelopes.
- **Forward tip margin is negative with the 9 Ah pack and heaviest head** under 0.4 m/s² braking on a 5° down-slope; 12 Ah pack adopted (DEC-040), head mount reopened (DEC-041). `mechanical/common/out/mech_calcs.md` §1.

## Questions for an independent engineer to challenge

1. **Event capture.** `rrh_evtcap.c`: is the live-time accounting exact when a clear crosses a gate boundary, when the service interrupt is late by more than one period, and when a chain is held busy by a long ZnS tail? Is a 100 kHz service interrupt at the top priority compatible with 1 Mbaud USART reception on the same MCU?
2. **Binding logic.** `rrh_core.c`: can any sequence of HELLO / reset / retry / stale BIND return counts on a binding the host did not complete? The interop tests cover the listed cases; look for unlisted ones.
3. **Chassis state machine.** `rrch_core.c` and ICD transition table: any path where a queued or stale DRIVE moves the robot after an inhibit clears; any software path that can assert `ARM_PERMIT` with a protective reason active; whether "local PAUSE can be released by `REARM_SW`" is acceptable.
4. **Watchdog strategy.** Is the three-context liveness cross-check sufficient to make `WDG_OK` meaningful, given that the window-watchdog timing is unverified?
5. **Chassis record size.** Limit raised to 4096 bytes and `STATE` self-truncates; is truncation of a state report acceptable at all, or should the report be split?
6. **MODEL.md rev 2.** U_null from a running window that excludes the gates under test: bias in a steep field gradient; the N+1 variance rule at zero counts; the 0.10 minimum lane-gate weight.
7. **Radiometric assumptions.** The K range and its dependence on the measurand definition; the Mirion AB-100 read-across for photon response; the alpha range model at 10 mm.
8. **EDA flow.** Open `electronics/tof_carrier/RR-TOF-A.kicad_pro` in the KiCad 9 GUI and re-run ERC/DRC there. Is a label-per-pin generated schematic acceptable as the editable source for the larger boards, and is the VL53L4ED footprint/pinout (flagged `verify`) right?
9. **Mechanical layout.** The receiver stiffness assumptions that dominate head deflection (1500 / 6000 N·m/rad); the 12 W/m²K film coefficient behind the heater sizing; the unverified purchased-part dimensions listed in `mechanical/common/purchased/parts.yaml`.

## Known gaps carried into the next milestone

- VL53L4ED driver is a stub (ST's driver could not be downloaded here); on hardware the chassis refuses motion until it is integrated.
- Charger, pack-monitor and branch-monitor drivers are not written.
- Head analog scale factors and the bias transfer function are placeholders until the circuit design is final; waveform capture is not implemented in the head target port.
- Protective-field geometry and stop-model inputs are placeholders pending VT-003/004/035.
- Decay data in the radiometry study were transcribed from memory.
