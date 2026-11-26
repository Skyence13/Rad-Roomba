# Planning registers, design 0.4 (README)

Design 0.4 is the system design after the 0.3 baseline (commit `38d1010`), built on the architecture in `docs/architecture/SYSTEM_ARCHITECTURE.md` and the contract `interface/system/contract.yaml` (0.4.0-draft5). Every file here is **new**; none of the 0.3 baseline files was changed. Nothing in 0.4 is physically measured: evidence classes are the contract's `calculated`, `simulated`, `tool-checked`, `physically-measured`, `pending`, and every verification test is still `Planned`.

## What each file is

| File | Relation to its 0.3 baseline | What is new |
|---|---|---|
| `decisions_0.4.csv` | All 20 rows of `decisions.csv` with the same columns and IDs, then DEC-021 to DEC-041 from the architecture document. | Columns `changed_in_0_4`, `interfaces_affected`, `reversible`, `evidence_class`, `answers_or_changes_baseline`. Baseline rows DEC-003, 004, 006 to 010, 016 to 020 have updated status and resolution text; DEC-002, 005, 011 to 014 only carry a pointer; the rest are unchanged. No baseline decision is closed. Target gate and most dates are "not stated" in the source. |
| `requirements_0.4.csv` | All 51 rows of `requirements.csv`, same IDs and wording. | RQ-052 to RQ-083 (32 new requirements) with `source_decision_0_4`; column `design_response_0_4` (files that implement or analyse each requirement) and `changed_in_0_4`. `verification_status` stays "Open — evidence pending" for every row. Baseline `verification_ids` are only extended with new VT IDs. |
| `verification_0.4.csv` | All 35 rows of `verification.csv`, same IDs, procedures and criteria. | VT-036 to VT-048 (13 new tests). Columns `evidence_class_now` (every row is `pending`: no test has been run as written), `evidence_reference` (file, and the handoff note where the lead reproduced it), `supporting_analysis` (what exists in calculated, simulated or tool-checked form, kept separate), `changed_in_0_4`. The pending cold, braking, personnel-protection and radiometric trials (VT-003, 004, 005, 013, 015 to 018, 032, 035, 045) are unchanged. |
| `risks_0.4.csv` | All 18 rows of `risks.csv`. | RSK-019 to RSK-040 (22 new), columns `source_file_0_4`, `current_mitigation_0_4`, `changed_in_0_4`. Baseline statuses unchanged. |
| `bom_0.4/procurement_bom.csv` | Consolidates `prototype_bom.csv` (every W, E, R ID is kept or marked replaced) with the purchased modules and custom boards. | Quantities per robot; verification status as stated in `mechanical/common/purchased/parts.yaml` and `electronics/modules/`; new lines B01 to B03, N01 to N08. Not priced. |
| `bom_0.4/RR-*_bom.csv`, `bom_0.4/extract_board_boms.py` | New. | Per-board BOMs collapsed by MPN, regenerated from the three `circuit.py` files by `python3 planning/bom_0.4/extract_board_boms.py`; `RR-TOF-A_bom.csv` is a copy of the fabrication BOM. |
| `Detector_Head_RFQ_0.4.md` | `Detector_Head_RFQ.md` carried forward verbatim, then a marked section "Additions for design 0.4" (A to I). | Photoelectron yield guarantee, coaxial leads, carrier NTC, breakdown matching, -25 C rating, lane-cavity envelope, higher-sensitivity reference options, leakage tests, data to return. |
| `README_0.4.md` | New (this file). | |

Conventions: all CSVs are UTF-8 with a byte-order mark, as the baseline files. `|` separates multiple IDs inside a cell. "not stated" means the source does not say; no value was supplied by judgement. Files under `mechanical/head/`, `mechanical/prototype_x1c/` and `ros2_ws/` were still in progress: they are cited only as "in progress" and are not accepted as evidence.

BOM verification column: `VERIFIED`, `PARTIAL` or `UNVERIFIED` follow the wording of `parts.yaml` and the module sheets; `NOT STATED` means the source gives no part number or verification; `CUSTOM` is an in-house part. Quantity 0 means the item is counted inside a board, or is a development or test item, or an alternative.

## Open owner and site decisions and external dependencies

| Item | Who | Blocks | Source |
|---|---|---|---|
| Site survey profile, release use, smallest patch, photon-field envelope, alpha and beta probabilities, mission false-investigation allowance and its meaning (DEC-001, 002, 012, 015) | Site RP | Any sensitivity claim; enabled field profile; recount rule; K definition (K differs by more than a factor of ten with the meaning of 1 Bq/cm2 for ore) | `analysis/radiometry/report/detectability_report.md` sections 1, 2.4 and 8; `docs/architecture/SYSTEM_ARCHITECTURE.md` section 11 |
| Edge, access and recovery policy (DEC-004), unattended-mode protections and alert route (DEC-017) | Site safety + operations | Speed caps per op_mode; shared-space and unattended modes | `interface/chassis_icd.md` section 6.1 (provisional) |
| OEM optical drawing: SiPM model, count, capacitance, connector exit, pulse data; guaranteed p.e. yield | Optical supplier (RFQ 0.4) | Final front-end component values, SiPM pigtail connector, lane cavity dimensions, thermal sensor position, whether the beta channel works at all (RSK-019) | `planning/Detector_Head_RFQ_0.4.md`; `electronics/analysis/head_afe_budget.md` section 1 |
| Traceable calibration (K, k, b with covariance) | Metrology | Bq/cm2 reporting for release decisions; until then all products are flagged `field_use_approved: false` | `docs/architecture/SYSTEM_ARCHITECTURE.md` section 11 |
| Physical trials: braking, personnel protection, cold, radiometric (VT-003, 004, 005, 013, 015 to 018, 032, 035, 045) | Project test team | Operating envelope, speeds, rail stroke value, unattended mode; replaces every `calculated` and `simulated` stop distance | `docs/architecture/SYSTEM_ARCHITECTURE.md` sections 6 and 11 |
| Hazard-owner disposition of the undetected single faults in the traction chain (IB-16) | Integration lead + chassis electronics | Any statement beyond "not a certified safety function" | `electronics/analysis/chassis_safety_chain.md` section 6 |
| LTC4162-F pin map, cell-count strap, JEITA defaults checked against the datasheet (IB-06); ST VL53L4ED driver (IB-04) | Chassis electronics / owner supplies driver | Fabrication of RR-CHS-MAIN; any motion on hardware | `docs/architecture/INTEGRATION_BACKLOG.md` |
| Wired service port or Wi-Fi-only service (IB-07); signal-connector family for -25 C (IB-08) | Integration lead / chassis electronics | Carrier choice; RR-TOF connector family | `electronics/chassis_main/design/CONTRACT_CHANGE_REQUESTS.md` CCR-E05, CCR-E10 |
| Rail-zone identification: isolated auxiliary contact per zone or dropped in rev A (IB-21); head-frame bonding scheme (IB-20); J1 landing connector height (IB-19) | Integration lead; head mechanical | Head rev A fit and function | `electronics/head_acq/design/CONTRACT_CHANGE_REQUESTS.md` CCR-HE-02 to CCR-HE-04 |
| Rail stroke value and carry attitude (IB-10, IB-11) | Head and body mechanical; owner | Forward survey speed near obstacles; one-person carry | `mechanical/common/out/mech_calcs.md` sections 3 and 8 |
| Breakdown-voltage matching figure: 2 V or 2.4 V; heater budget reconciliation (contract 15 W against 21 to 30 W) | Head electronics lead; power budget owner | RFQ acceptance; cold runtime claim | see contradictions in the hand-off report; `interface/system/contract.yaml` power.average_budget_w |
| Pack BMS behaviour below -20 C cell temperature; UN 38.3 shipping documentation | Pack supplier | Cold mission duration; pack shipping | `electronics/modules/battery_pack_and_coupler.md` |
| Detailed mechanical design (head, X1C body, production body) and the ROS 2 workspace | Respective work packages (in progress) | Fit of purchased parts, light tightness, all host-side verification tests | `mechanical/*/STATUS.md`, `ros2_ws/STATUS.md` |
| Baseline decisions still open: DEC-001, 002, 005, 011 to 015 | as in `decisions.csv` | as in `decisions.csv` | `decisions_0.4.csv` |

## Reproduce the consistency checks

```bash
python3 planning/bom_0.4/extract_board_boms.py
python3 planning/check_registers_0.4.py
```

`check_registers_0.4.py` (read-only) checks that every ID is unique, that baseline rows and columns are preserved (only the documented fields differ), that every requirement, test, decision and risk reference resolves, that requirement and test links are two-way, that every test carries an enum evidence class and reference, that every baseline BOM item is present, and that every file path cited in the new files exists.
