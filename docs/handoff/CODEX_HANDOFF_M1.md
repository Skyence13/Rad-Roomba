# Handoff for Codex — Milestone 1: architecture and interface contract

| | |
|---|---|
| Repository | https://github.com/Skyence13/Rad-Roomba |
| Base | `main` @ `38d101051d32b47e4b21657e2293ec92c63de9c4` (verbatim 0.3 baseline import) |
| Branch | `claude/elegant-mendel-s1qy1u` |
| Reviewed commit | the commit that adds this file (see the pull request for the exact SHA) |

## What changed

| File | Content |
|---|---|
| `docs/architecture/SYSTEM_ARCHITECTURE.md` | Baseline inventory, product structure, board partition, head and chassis electronics concepts, personnel-protection concept, host interfaces, software architecture, file ownership, decisions DEC-021…036, external dependencies. |
| `interface/system/contract.yaml` | Machine-readable contract: frames/datums, motion envelope, timing, power rails, traction chain elements, shared enumerations, board envelopes, J1/J2 pin tables with presence/LAB coding, head gate record, chassis link `RR-CHS 1.0` op table. |
| `analysis/radiometry/MODEL.md` | Normative count-processing model: compensated estimator, uncertainty with reference counting statistics and calibration covariance, ISO 11929-form decision threshold and detection limit, uncompensated comparator, moving patch, cell estimate. |

No hardware, firmware or software is delivered in this milestone; it is the agreement the parallel subsystem work is built against.

## Reproduce

```bash
git fetch origin && git checkout claude/elegant-mendel-s1qy1u
```

```bash
python3 -c "import yaml; yaml.safe_load(open('interface/system/contract.yaml')); print('contract parses')"
```

```bash
sha256sum -c SHA256SUMS.txt && python3 software/map_demo.py --self-test && python3 interface/test_interface.py
```

The last line reproduces the 0.3 baseline checks (all OK, PASS, 15 tests OK on Python 3.13 with jsonschema 4.26; `tool-checked`).

## Evidence for the important decisions

All `calculated` or design reasoning; nothing is measured.

- **Head height (DEC-021).** `cad/source/build_concept.py` puts the reference guide top at z = 28.5 mm and the cover underside at 33.6 mm; an acquisition board with parts needs about 12 mm.
- **Detection-limit closed form.** With κ = k₁₋α = k₁₋β and ũ²(ρ) = ũ²(0) + ρ/T_F, solving r# = r* + κ·ũ(r#) gives r# = 2r* + κ²/T_F (MODEL.md §3).
- **Outer head corner speed.** Corner radius √(265² + 175²) = 318 mm; 0.30 rad/s gives 0.095 m/s.
- **LAB presence code.** 4.70 kΩ ∥ 1.50 kΩ = 1.137 kΩ; the four decode windows in the contract do not overlap for 1 % resistors.

## Questions I would like an independent engineer to challenge

1. **Traction chain.** Is a self-holding relay latch with DPDT brake relays (motor shorted through a resistor when de-energised) and single-channel monitoring adequate for a ≤ 12 kg, ≤ 0.2 m/s machine working beside people, given that it is explicitly not a certified safety function? Which single faults are undetected (welded brake-relay contact, shorted bumper loop before the window comparator, stuck `ARM_PERMIT`)?
2. **Local-only hardware re-arm.** Does requiring a physical button after every hardware trip conflict with the unattended mode in the 0.3 operating concept?
3. **Front-end choice.** Discriminators with hardware live time versus a digitising front end: is amplitude-window classification with a slow-path alpha decision sufficient before any pulse data exist, or does it lock in the wrong architecture?
4. **Isolation placement.** Bus side of the head transceiver powered from the chassis over J2: any failure mode where a J2 fault back-feeds or defeats the isolation?
5. **J1 presence coding by resistor.** Robustness of a resistor-coded presence/LAB pin against contamination, moisture and contact resistance at −25 °C, compared with dedicated pins.
6. **MODEL.md.** Is omitting Cov(F,U) by default defensible? Is inverse-variance lane combination with common calibration terms added afterwards correct for overlapping footprints?
7. **`base_link` on the floor.** Any conflict with ROS tooling assumptions (REP-105 expects `base_link` rigidly on the robot; it is, but at z = 0)?
8. **No Nav2.** Is the purpose-built localization/coverage stack a reasonable reduction, or does it discard recovery behaviours the team will need?
