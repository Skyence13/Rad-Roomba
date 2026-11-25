# Rad Roomba prototype design package

**System design revision 0.3 · 25 November 2026**  
An engineering baseline for a one-person-portable ROS 2 robot that surveys semitrailer and seacan floors at uranium facilities. The removable four-segment scintillation head is an independent hardware and firmware project. A dummy head lets the mobile platform proceed in parallel.

## Start here

1. Read **docs/Rad_Roomba_Design.pdf** for the full design, operating concept, decisions and gated development plan. Use **docs/Rad_Roomba_Design.docx** to revise it. The source register is in **docs/Sources.csv** and citations are clickable in both documents.
2. View **cad/renders/Rad_Roomba_Rev_D_Assembly.png** for the assembled robot and **cad/renders/Rad_Roomba_Rev_D_Detector_Head.png** for the detector detail. Open **cad/Mechanical_layout_D.pdf** for the three proposed mechanical views. Open **cad/Rad_Roomba_D.step** for the entire assembly or **cad/Detector_Head_D.step** for the removable head. Native source, dimensions, rebuild and geometry checks are in **cad/**.
3. Use **planning/requirements.csv** and **planning/verification.csv** together. Filter by owner and gate, attach evidence to a test, and update the linked requirement. **planning/risks.csv** and **planning/decisions.csv** track unresolved hazards and choices. Gate assignments run from G0 site inputs to G4 controlled pilot.
4. Use **planning/Detector_Head_RFQ.md** to request one full-size optical pair and comparable pricing for four. Use **planning/detector_bench_runs.csv** to capture test results; the RFQ explains its fields. Use **planning/Rad_Roomba_Current_BOM.xlsx** or **planning/prototype_bom.csv** for the current parts. Use **planning/Survey_Field_Checklist.md** for commissioning, shared-space scanning and guided follow-up, the separate secured unattended option, and charge service.
5. Read **interface/head_icd.md** before integrating the head. The samples under **examples/** show the wire and frame formats, geometry and site settings. **software/** contains a separate end-to-end mapping example for already-decoded data and the resulting map. Its input CSV is a simulation fixture. Read **software/Operator_Interface.md** for the operator workflow and open **software/guide_demo.html** in a browser to try the offline review queue.

## Project files

| Path | Use |
|---|---|
| docs/ | Full design in Word and PDF. Primary sources are indexed by ID in Sources.csv. |
| cad/ | Rev D editable assembly source, neutral STEP models, three-sheet PDF, dimensions and geometry checks. Coordinate units in the models are millimetres. |
| interface/ | Proposed modular head mechanical, power, independent bumper and isolated RS-485 contract. Includes the head descriptor, discovery, acquisition schema, CRC codec, host validation and tests. |
| examples/ | Normal and degraded frame, decoded transactions, a CRC-framed response, a head descriptor and bench registry, a concept geometry manifest and disabled site-profile examples. Units are explicit in files and in the ICD. |
| software/ | Python offline map demonstration, raw synthetic counts, poses, calculated cell estimates, valid exposure and a portable SVG. Also includes the operator web specification and an offline guided-tour demo with personnel present. |
| planning/ | Procurement crosswalk, OEM RFQ, operator checklist, detector run sheet, requirements, verification, risks and decisions. CSV files open in a spreadsheet editor. |
| reference/ | Original hardware workbook, user-supplied concept sketches, first concept and the preceding Revision B models. The current models are in cad/. Superseded Rev C models are in cad/previous_C/. |
| SHA256SUMS.txt | SHA-256 digest of each distributed file, excluding the checksum list itself. |

## Reproduce the included checks

From the unpacked **Rad_Roomba_Design_Package** directory:

```sh
python3 software/map_demo.py --self-test
python3 software/map_demo.py --out local_demo
```

The map example uses the Python standard library. The head interface tests additionally require the Python package **jsonschema** supporting Draft 2020-12. In an environment with it installed, run:

```sh
python3 interface/test_interface.py
```

For CAD, follow **cad/README.md**. The neutral STEP models and mechanical PDF are usable without rebuilding the CadQuery sources. On systems with GNU coreutils, check extracted file integrity from this directory with `sha256sum -c SHA256SUMS.txt`.

## Changes in revision 0.3

**Technicians in the trailer.** The intended shared-space mode permits technicians to stay in the trailer through a scan and while the robot moves between flagged areas. A person can stand alongside or behind the robot where there is sufficient clearance for the requested move. Determine the protected region from the body and projecting head throughout that move, detection latency, measured braking on the actual floor and a person's possible approach. A blocked route holds. For a hands-on check, inhibit traction, perform the check and step clear of the local motion envelope before deliberately restoring permission. The design also retains a separate secured, unattended option. Shared-space operation requires demonstration of personnel protection on the assembled robot. See the operator workflow and verification register.

**Head identity and acquisition.** Each attachment establishes the head type, serial, boot and descriptor once during discovery and binding. Subsequent count traffic carries interval measurements, timing, sequence and health. The host saves an attachment record and links every stored count to that record. Disconnection, reset, or loss of confidence in continuity requires re-establishing the binding. Recoverable packet loss on an intact connection uses the existing binding. The example transactions and tests in interface/ and examples/ show the distinction.

**CAD views.** The two standalone studio views in cad/renders/ come from the existing mechanical Rev D assembly and head. They share the same nominal dimensions as the engineering drawings.

## Changes introduced in revision 0.2

| Design review topic | Current location | Requirement |
|---|---|---|
| Shared web interface, gloved local controls, deliberate command authority | Design §2 and §7, software/Operator_Interface.md | RQ-041, RQ-042 |
| Qualified unattended scans, protective access controls and guided hotspot visits | Design §2, §4 and §7, offline guide_demo.html, operator field checklist | RQ-010, RQ-039, RQ-040, RQ-043 |
| Swappable packs, charge inlet, limited settings/data service | Design §4 and §8, current BOM workbook and rows R01–R06 | RQ-044, RQ-045 |
| Head-mounted MCU, identity, geometry and laboratory patch harness | Design §5–6, interface/head_icd.md, examples/head_descriptor.json | RQ-046, RQ-049 |
| 10 mm entrance gap, 3 or 5 mm rail projection and cantilever dynamics | Design §4–5, cad/Mechanical_layout_D.pdf, planning/detector_bench_runs.csv | RQ-047, RQ-048 |
| Pose at acquisition and saved locations for hand surveys | Design §1, §2 and §7, operator field checklist | RQ-050 |

The offline guide uses synthetic flags and no hardware connection. The proposed production web service, motion system and protective interlocks require implementation and field qualification.

## Baseline and use

The original workbook provides the 12.8 V / 8 Ah trial pack, warm-start power worksheet and prototype parts. The current procurement workbook adds the detector MCU, connector and bench kit, removable battery and charging hardware. Its sizing sheet models average consumption separately from peak supply allocation. The Rev B survey bar is a narrow placeholder. Rev C lengthened the head for four 80 × 100 mm apertures and separate upper references. Rev D retains that footprint, sets the entrance 10 mm above a level floor, and models a 7 mm clearance under the compliant contact rails. A 12 kg all-up packaging allowance and a one-hour energy scenario are trial assumptions. Weigh and qualify the real system for the actual site workflow.

The ore profile carries the stated 0.30 Bq/cm² investigation level and 0.40 Bq/cm² comparison criterion. A moving detection limit below 0.20 Bq/cm² is a proposed qualification target for a yet-to-be-specified minimum patch and field. The yellowcake profile awaits the radiation protection team's procedure and calibration. Raw counts and source, timing, location, coverage and sensitivity evidence remain essential to interpreting a reported Bq/cm² value.

All planning-register tests begin open. The software fixtures and CAD checks can be reproduced now. The build still requires component qualification, physical stopping and cold tests, radiometric calibration, independent field comparison and site authorization. Follow the evidence gates before treating the robot as an operational survey instrument.
