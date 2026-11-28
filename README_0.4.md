# Rad Roomba — design revision 0.4 (work in progress)

A one-person-portable ROS 2 robot that surveys trailer and sea-container floors for alpha/beta surface contamination with a detachable four-lane scintillation head. This file is the entry point for revision 0.4. The frozen 0.3 baseline is described in `README.md` and protected by `SHA256SUMS.txt`; nothing listed there is edited.

**Nothing in this repository has been built, printed, ordered or measured.** Every result is `calculated`, `simulated` or `tool-checked` (a script or design-rule check ran and passed), or is marked `UNVERIFIED` (recalled, not confirmed against a manufacturer document). This is not a certified safety system; the limits of its protective functions are stated in `electronics/analysis/chassis_safety_chain.md` section 6 and `docs/service/01_operator_procedures.md`.

## Where to start

| You want to know | Read |
|---|---|
| What is decided, and why | `docs/architecture/SYSTEM_ARCHITECTURE.md` (decisions table), `planning/decisions_0.4.csv` |
| What is open | `docs/architecture/INTEGRATION_BACKLOG.md` — the authoritative list of open items (IB-xx) |
| What four independent reviews found | `docs/reviews/` |
| What can be ordered, printed, assembled or tested now | `docs/build/README.md` ("state of the design" table) |
| The machine-readable interface contract | `interface/system/contract.yaml` |
| How counts become activity, thresholds and decisions | `analysis/radiometry/MODEL.md` (normative), `analysis/radiometry/report/` |
| Requirements, verification tests (all pending), risks, BOM, detector RFQ | `planning/README_0.4.md` |
| How to procure, print, assemble, bring up, operate, calibrate, service | `docs/build/`, `docs/service/` |

## Layout

| Path | Content |
|---|---|
| `interface/` | Contract, head protocol 2.0 (baseline) with the 0.4 addendum, chassis link ICD and schema |
| `firmware/common`, `firmware/head`, `firmware/chassis` | Portable C11 cores, STM32G474 ports (PlatformIO), host emulators `rr_head_sim`, `rr_chassis_sim` |
| `electronics/` | Scripted KiCad 9 projects: `tof_carrier` and `panel` (complete), `chassis_main` and `head_acq` (schematic and placement; **not routed**), analysis documents |
| `tools/eda/` | The board generator (`rrkicad`): Python board definition → native schematic and board → autorouter → ERC/DRC with schematic parity → outputs |
| `harness/` | Connector and cable tables generated from the board data and frames, with a cross-check |
| `mechanical/common` | Parameters, frames, board envelopes, layout, mass and thermal calculations |
| `mechanical/head` | Detector head, prototype (printed) and production builds, drawings |
| `mechanical/prototype_x1c`, `mechanical/production` | Robot body for a Bambu Lab X1 Carbon (256 mm cube) and for 5–25 units per year |
| `ros2_ws/` | ROS 2 Jazzy workspace: head driver, chassis bridge, localisation, coverage, guidance, count processing (`rr_core`), operator web UI, simulation scenarios |
| `analysis/radiometry/` | Detectability study, the count-processing model and its numerical checks |
| `planning/` | 0.4 registers, BOM, detector RFQ and their checker |
| `docs/` | Architecture, reviews, build and service documents, Codex handoff notes |

## Prerequisites

Ubuntu 24.04 or similar with `gcc`, `cmake`, `ninja`, `make`, Python 3.12 (`pyyaml`, `jsonschema`, `numpy`, `scipy`, `matplotlib`), PlatformIO Core (`pip install platformio`), Docker with the images `kicad/kicad:9.0` and `ghcr.io/freerouting/freerouting:latest`, and `uv` for the CadQuery environment. The robot-software image `rad-roomba/ros2-ws:0.4` is built by `make ros-image` from `ros:jazzy-ros-base`.

## Build and check

Every check is a subsystem script; the top-level `Makefile` only names them.

```bash
make check-fast
```

runs the baseline regression, the register checker, the harness generator and cross-check, and both firmware checks (host tests under sanitizers, emulator integration tests, STM32 images).

```bash
make cq-venv
```

creates the CadQuery environment once (`mechanical/common/.venv`), after which

```bash
make check
```

adds the radiometry study, the two small boards, the four mechanical builds and the robot-software unit and scenario tests. Individual targets: `baseline`, `registers`, `harness`, `firmware-head`, `firmware-chassis`, `radiometry`, `boards-small`, `boards-large-noroute`, `mech-common`, `mech-head`, `mech-prototype`, `mech-production`, `ros-image`, `ros-unit`, `ros-scenarios`, `ros-native`.

Approximate run times on a 4-core machine: `check-fast` 5 min; radiometry 8 min; mechanical builds 5–30 min each (the first, uncached body build is the long one); robot-software scenarios 20–35 min; the native-emulator scenarios 10 min.

Things to know before trusting a green result:

- `boards-large-noroute` regenerates the two large boards without routing and exits non-zero on purpose (unconnected nets). Read `electronics/*/reports/summary.json`: ERC, DRC and schematic parity should be clean; the unconnected count is the routing still to do.
- `mech-head` deletes its generated outputs before rebuilding. Always pass a working CadQuery interpreter (`make CQ_PY=... mech-head`).
- A mechanical "all checks pass" covers only what the checks measure. An independent review showed that the body checks of 27 November could not see fasteners, board mounting, mated plugs or cable routes (`docs/reviews/REVIEW_cad_pcb_harness_fit.md`); read the backlog before relying on a body build.
- Emulator-based firmware tests are only as good as the emulator's agreement with the netlist; two review rounds found divergences at newly added parts. The firmware checks now compare pin maps and component values with the board data, but analog margins are modelled, not measured.
- All radiometric numbers use synthetic coefficients flagged `field_use_approved: false`.

## Evidence classes

| Class | Meaning |
|---|---|
| `calculated` | Closed-form or script result from stated inputs |
| `simulated` | Software run against an emulator, a fake or a Monte Carlo model |
| `tool-checked` | A build, test suite, ERC/DRC or geometric check ran and passed on the nominal design |
| `physically measured` | Not used anywhere yet |
| `UNVERIFIED` | Recalled value, or a part number, pinout or dimension not checked against a manufacturer document |
