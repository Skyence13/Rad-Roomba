# Rad Roomba service documents (design 0.4, draft)

For the technicians, operators and the owner who will run, check, clean, repair and maintain the prototype. **No robot exists and no procedure here has been tried.** Every procedure is proposed from the design documents; every number carries its source file and evidence class (`calculated`, `simulated`, `tool-checked`, `design value`, `assumed`, `UNVERIFIED`; legend in [../build/README.md](../build/README.md)). Where the repository lacks a fact the file says "not yet defined" and lists it under "Open items" with the backlog (IB-xx), verification (VT-xxx), risk (RSK-xxx) or requirement (RQ-xxx) identifier if one exists. The authoritative open-item list is `docs/architecture/INTEGRATION_BACKLOG.md`.

**Updated 2026-11-28.** Revised for the independent reviews of the traction chain (three rounds), of the head interference and of the data path to the map; chassis stage-5 firmware (the REARM procedure, the operating limits, the per-shift check P1, the six-monthly service tests S3 to S8), head stage 3 and firmware 0.6.0, MODEL.md revision 5 (the software implementation is in progress, `ros2_ws/STATUS.md`), contract draft11 thermal policy, and the backlog to IB-75. **Neither body can be assembled as modelled (IB-73); the rework is in progress**, so everything about the body is as modelled and may change.

**Not a certified safety system.** The hardwired traction chain, the contact rails and the software stops are design intent. The braking, personnel-protection, cold and radiometric trials are all pending. The calibration and site-profile data in the repository are synthetic and flagged `field_use_approved: false`. Nothing here authorises field use, a release decision or a performance claim; the survey profile, calibration authority, check-source program and contamination control belong to the site's radiation-protection program.

| File | Content |
|---|---|
| [01_operator_procedures.md](01_operator_procedures.md) | pre-use checks, start sequence, the three survey methods, long trailers with open doors, review queue (alarm-only default), pause/stop/re-arm, battery and charging rules including the +5 C charge inhibit, end of shift |
| [02_calibration_and_source_checks.md](02_calibration_and_source_checks.md) | what calibration the model needs (k, b with covariance, K and its source definition, leakage, validity envelope), how each would be measured, daily source and response check method with no band values, background and reference checks, records, what the site must define |
| [03_cleaning_and_contamination_control.md](03_cleaning_and_contamination_control.md) | wipe-down, wetted surfaces and seals, what can and cannot be decontaminated on the printed prototype, head window protection and replacement, handling and frisking; site items marked [SITE] |
| [04_fault_isolation.md](04_fault_isolation.md) | symptom, checks, likely cause tables: power, traction chain and inhibits (chain element names and reason codes of the chassis ICD), links, head faults and lane flags, localisation and coverage refusals, heaters and cold behaviour |
| [05_maintenance_and_spares.md](05_maintenance_and_spares.md) | periodic checks, **P1 and service tests S3 to S8 with instruments, pads and pass/fail bands (section 6)**, wear parts, battery care, spares, firmware and software update procedure and version recording |

## Baseline documents these files carry forward (0.3)

`docs/Rad_Roomba_Design.pdf` / `.docx` (chapter 02 "Normal survey sequence", chapter 09 gates G0 to G4 and "Configuration control and handover"), `planning/Survey_Field_Checklist.md` (field worksheet, use together with 01), `software/Operator_Interface.md` (0.3) with `software/Operator_Interface_0.4_delta.md` (what the 0.4 software does), requirement, verification, risk and decision identifiers (RQ-, VT-, RSK-, DEC-).

Build, bring-up and first tests are in [../build/README.md](../build/README.md).

## Contradictions between sources that these documents had to choose between

Reported to the lead; each file names the choice it made. The numbering C-xx is that of `planning/README_0.4.md`; "closed" means the repository changed after the first version of these documents.

| Topic | Sources | Choice here |
|---|---|---|
| Step-and-count station pitch (C-13) | contract 0.080 m; `Operator_Interface_0.4_delta.md` "100 mm stations"; `power_budget.md` 0.10 m | contract |
| Mission-time estimates (C-13) | `SYSTEM_ARCHITECTURE.md` section 8a against `ros2_ws/README.md` section 8.1 | workspace planner |
| `hw_inhibit_reason`: LATCH_UNEXPLAINED | contract and (now) ICD section 4.4 list it | closed |
| Cold-charge gate wording (C-13) | contract: charger thermistor at 5 C; electronics: hardware comparator at about 5.3 C with 2 K hysteresis, firmware limit as a second layer | both described |
| SiPM coax pigtail length (C-02) | 35 mm (RFQ, RQ-062); 45 to 50 mm (harness); about 60 mm (head BOM); routed 44 / 47 and 33 / 30 mm (`lead_routes.yaml`); stage 3 says the coax case does not depend on length | flagged |
| PAHT-CF density | 1.06 (body plates) against 1.22 (head plates) | flagged |
| Safety-chain "VMOT under 1 V within 1 s" | now 3.5 s required / 2.65 s worst case in the chain analysis, 3500 ms in the ICD | closed |
| HEAD_HTR limit 4.05 A in the chassis checklist (C-13) | contract 3.96 A nominal | contract |
| Head board routing status (C-12) | 1090 / 340 / 1468 | 1468 (stage 3) |
| Head heater demand at +5 C | head report 15.2 / 18.4 W (-20 / -25 C, still air); contract draft11 and VT-057 13.8 to 14.0 / 16.7 to 17.0 W | head report as the newer source; flagged (C-04) |
| Beta yield requirement (C-07) | review 15 p.e. (about 30 p.e. mean); electronics and RFQ 18 p.e. at the MPV, plate mean about 51 p.e. | 18 p.e. |
| Brush-arc pickup (C-01) | review about 20 / 0.6 p.e.; electronics 2.76 / 0.11 p.e. (open loop / coax) | measurement decides (VT-063) |
| Test labels (C-09) | "E7": frame isolation in the harness, post-alpha tail in the head checklist; "E9" is not the heater test | harness labels E7, E7M, W-103.HTR-ISO |
| Re-arm acceptance window (C-06) | 150 ms (electronics) against 250 ms plus 50 ms debounce (ICD) | ICD |
| Head-loop windows (C-14) | contract 0.6 to 1.6 kohm; chain analysis 0.59 to 1.55 kohm; channel B 1.89 kohm (stage 4) | chain analysis and ICD values |
| JP1 | ICD section 4.5 table: "normally closed"; firmware README and IB-74: keep open until the first-strobe timing is measured | open |
