# Rad Roomba service documents (design 0.4, draft)

For the technicians, operators and the owner who will run, check, clean, repair and maintain the prototype. **No robot exists and no procedure here has been tried.** Every procedure is proposed from the design documents; every number carries its source file and evidence class (`calculated`, `simulated`, `tool-checked`, `design value`, `assumed`, `UNVERIFIED`; legend in [../build/README.md](../build/README.md)). Where the repository lacks a fact the file says "not yet defined" and lists it under "Open items" with the backlog (IB-xx), verification (VT-xxx), risk (RSK-xxx) or requirement (RQ-xxx) identifier if one exists. The authoritative open-item list is `docs/architecture/INTEGRATION_BACKLOG.md`.

**Not a certified safety system.** The hardwired traction chain, the contact rails and the software stops are design intent. The braking, personnel-protection, cold and radiometric trials are all pending. The calibration and site-profile data in the repository are synthetic and flagged `field_use_approved: false`. Nothing here authorises field use, a release decision or a performance claim; the survey profile, calibration authority, check-source program and contamination control belong to the site's radiation-protection program.

| File | Content |
|---|---|
| [01_operator_procedures.md](01_operator_procedures.md) | pre-use checks, start sequence, the three survey methods, long trailers with open doors, review queue (alarm-only default), pause/stop/re-arm, battery and charging rules including the +5 C charge inhibit, end of shift |
| [02_calibration_and_source_checks.md](02_calibration_and_source_checks.md) | what calibration the model needs (k, b with covariance, K and its source definition, leakage, validity envelope), how each would be measured, daily source and response check method with no band values, background and reference checks, records, what the site must define |
| [03_cleaning_and_contamination_control.md](03_cleaning_and_contamination_control.md) | wipe-down, wetted surfaces and seals, what can and cannot be decontaminated on the printed prototype, head window protection and replacement, handling and frisking; site items marked [SITE] |
| [04_fault_isolation.md](04_fault_isolation.md) | symptom, checks, likely cause tables: power, traction chain and inhibits (chain element names and reason codes of the chassis ICD), links, head faults and lane flags, localisation and coverage refusals, heaters and cold behaviour |
| [05_maintenance_and_spares.md](05_maintenance_and_spares.md) | periodic checks, wear parts, battery care, spares, firmware and software update procedure and version recording |

## Baseline documents these files carry forward (0.3)

`docs/Rad_Roomba_Design.pdf` / `.docx` (chapter 02 "Normal survey sequence", chapter 09 gates G0 to G4 and "Configuration control and handover"), `planning/Survey_Field_Checklist.md` (field worksheet, use together with 01), `software/Operator_Interface.md` (0.3) with `software/Operator_Interface_0.4_delta.md` (what the 0.4 software does), requirement, verification, risk and decision identifiers (RQ-, VT-, RSK-, DEC-).

Build, bring-up and first tests are in [../build/README.md](../build/README.md).

## Contradictions between sources that these documents had to choose between

Reported to the lead; each file names the choice it made.

| Topic | Sources | Choice here |
|---|---|---|
| Step-and-count station pitch | contract 0.080 m; `Operator_Interface_0.4_delta.md` "100 mm stations"; `power_budget.md` 0.10 m pitch | contract |
| Mission-time estimates for the same methods | architecture section 8a (46 min / 2.8 h / 5.5 to 9.7 h) against `ros2_ws/README.md` section 8.1 (59 min / 2.8 h / 12.2 h) | workspace planner, as the later and more detailed `calculated` result |
| `hw_inhibit_reason` enum | contract lists `LATCH_UNEXPLAINED`; chassis ICD section 4.4 and firmware do not | ICD list; flagged |
| Cold-charge gate | contract and architecture: the charger's thermistor qualification at 5 C; `chassis_design_notes.md`: hardware comparator at +5.3 C with 2 K hysteresis, firmware JEITA limit 5 C as a second layer (driver disabled, IB-05/06) | both described |
| SiPM coax pigtail length | 35 mm (RFQ, RQ-062); 45 to 50 mm (harness, IB-57); about 60 mm (head BOM) | flagged |
| PAHT-CF density | 1.06 g/cm3 (body plates) against 1.22 (head plates) | flagged |
| Safety-chain section 7 "VMOT under 1 V within 1 s" | against the 0.8 s bleed time constant and the 2.5 s limit in the ICD and firmware | firmware and ICD (IB-24) |
| Chassis design checklist HEAD_HTR 4.05 A | against contract draft7 3.96 A nominal | contract |
| Head board routing status | `electronics/head_acq/README.md` 1090 open connections; IB-51 340 unconnected | IB-51 |
