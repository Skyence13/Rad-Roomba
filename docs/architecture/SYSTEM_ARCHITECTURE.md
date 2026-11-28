# Rad Roomba system architecture and interface contract — design 0.4 (draft)

Owner: integration lead. Baseline: system design 0.3, mechanical Rev D, head protocol 2.0, imported unmodified as commit `38d1010` on `main`.
Machine-readable companion: [`interface/system/contract.yaml`](../../interface/system/contract.yaml). Where this document and the YAML disagree, the YAML wins and the disagreement is a defect.

Every number here is a **design value** unless it carries an evidence class. Evidence classes used across the project: `calculated`, `simulated`, `tool-checked`, `physically-measured`, `pending`. Nothing in this revision is physically measured.

## 1. Inventory of the 0.3 baseline

| Area | Reusable as-is | Missing for a build | Critical dependency |
|---|---|---|---|
| Requirements, verification, risks, decisions (RQ-001…051, VT-001…035, DEC-001…020) | IDs, wording, gates. Carried forward unchanged; new rows are appended. | Evidence links; every VT starts open. | Site inputs DEC-001/002/004 (profile, patch size, access policy). |
| Head protocol 2.0 (`interface/`, `examples/`) | Command envelope, ACQ schema, descriptor schema, CRC codec, host validator, 15 passing tests. | Firmware that speaks it; host driver; clock fit; DIAG data for engineering counters. | None — implementable now. |
| Mechanical Rev D (`cad/`) | Datums, rounded body form, optical lane geometry, rail options, STEP envelopes, geometry checks. | Real part design: no fasteners, no printable splits, no purchased-part models, no electronics volume in the head, no battery cassette, no panel, no sensor mounts, no drawings. | Optical supplier section drawing (SiPM position, connector, thicknesses). |
| Electronics | Function allocations, candidate dev modules, power worksheet. | Everything: no schematic, PCB, harness, pinout or connector choice. | OEM SiPM type/count/capacitance, light yield at the SiPM, pulse shapes. |
| Firmware | None. | Head and chassis firmware, toolchains. | Pin maps (owned by electronics, proposed by firmware). |
| Robot software | Offline map demo (`software/map_demo.py`), operator workflow spec, guide demo page. | ROS 2 workspace, drivers, localization, coverage, processing, web service, replay/export. | Chassis link definition (§7), head emulator. |
| Radiometry | Compensation model r = F − kU − b and variance terms; site numbers 0.30 / 0.40 / <0.20 Bq/cm². | Detectability comparison, propagated uncertainty implementation, decision thresholds. | Site patch size, photon field envelope, calibration coefficients (all site/supplier inputs). |

Baseline checks reproduced before import: `sha256sum -c SHA256SUMS.txt` all OK; `software/map_demo.py --self-test` PASS; `interface/test_interface.py` 15 tests OK (`tool-checked`).

## 2. Product structure

Two independently buildable products plus the site profile, as in 0.3:

1. **Mobile base** — chassis, drive, power, safety chain, motion MCU, sensors, Linux host (CM5), operator panel.
2. **Detector head** — optical modules (OEM), acquisition board with its own MCU and event logic, heater, contact rails, pigtail cables J1/J2. Runs on a bench from 12 V and an RS-485 adapter with no robot.
3. **Site survey profile** — owned by radiation protection; ore example enabled as a demonstration profile, yellowcake left unconfigured.

Two mechanical builds of the same design: **X1C prototype** (printed on a stock Bambu Lab X1 Carbon, 256 × 256 × 256 mm) and **production** (assumed 5–25 units per year: CNC aluminium chassis plate and head frame, MJF PA12 shells, no hard tooling). They share datums, optical geometry, board outlines, connector positions and all purchased parts.

## 3. Board partition (DEC-022)

| Board | Qty | Function | Why it is its own board |
|---|---:|---|---|
| **RR-HEAD-ACQ** | 1 / head | Eight SiPM front ends, programmable bias with temperature compensation, threshold DACs, discriminators with event latches, head MCU (STM32G474VET6) doing classification, counting and measured live time with its timers, isolated RS-485, heater switch, input protection and low-noise rails. No FPGA (DEC-037). | The head must be buildable and testable alone. One board spanning the four lanes removes inter-board connectors in the signal path; lane circuits are four identical blocks. |
| **RR-CHS-MAIN** | 1 | Pack input and main protection, charger with power path, branch eFuses, 5 V compute rail, hardwired traction chain (latch relay, brake relays, watchdog), motion MCU (STM32G474), dual H-bridge, encoder/IMU/ToF/bumper/panel I/O, host-side RS-485 with USB bridge, USB to the CM5, heater switches, telemetry. | One board keeps the safety chain, the drive stage and their monitoring on one copper reference with no harness between them; power and logic are zoned on a 4-layer stack. Fewer connectors matter at −25 °C. |
| **RR-TOF** | 11 | VL53L4ED carrier with local decoupling, ESD and a 6-pin cable. | Sensors sit at the body perimeter behind windows; identical boards, individually replaceable. |
| **RR-PANEL** | 1 | Five annunciator LEDs, buzzer, landing for the two program buttons and their indicators. | Sits in the top shell at the operator surface; one cable to the main board. |

Purchased modules (not redesigned): Raspberry Pi CM5 + compact carrier, 2D LiDAR, gearmotors with encoders, LiFePO₄ pack with BMS, external 24 V supply, E-stop and switches, optical modules. Each gets ordering details, an interface schematic and a prototype-to-production crosswalk in `electronics/modules/` and `planning/`.

## 4. Detector head electronics concept (DEC-023 as revised by DEC-037, DEC-024)

Signal chain per optical channel (8 channels: 4 floor, 4 reference):

```
SiPM (cathode at filtered HV, anode AC-coupled, anode DC return to a per-channel trim DAC)
  -> low-noise preamp at the board edge next to the SiPM pigtail
  -> fast path  (CR-RC, tens of ns)   -> comparators: floor BETA_LLD, BETA_ULD ; reference REF_LLD, REF_ULD
  -> slow path  (integrating, ~µs)    -> comparator: floor ALPHA      (ZnS(Ag) light is large and slow)
  -> buffered monitor mux -> 50 Ω test output and MCU ADC (triggered waveform capture with pre-trigger)
comparators -> edge-triggered latches (the low-threshold latch is BUSY: non-retriggerable until the MCU clears it)
BUSY -> MCU 32-bit timer input capture (event start time captured in hardware)
MCU service interrupt at a fixed 100 kHz: after the acceptance window, read the latches, classify, count,
               read the timer for the clear time, clear the latches; gate boundaries snapshot all counters
```

- Classification baseline is the amplitude-window method used by commercial dual-phosphor probes (beta window between two fast-path thresholds, alpha above a high threshold), strengthened by taking the alpha decision on the slow path so that large fast pulses (Cherenkov in the guide, high-energy electrons) land in a separate reject counter instead of the alpha counter. Pulse-shape development uses the waveform capture path; it does not change the wire format.
- Live time is measured, not modelled: each event's busy interval runs from the hardware-captured start time to the timer reading at which the MCU clears the latches, and the live time of a gate is its span minus those intervals. Expected rates are a few to about 2000 events per second per chain, so the dead fraction is a few percent at most. An FPGA was considered for this job and rejected as unnecessary at these rates (DEC-037); `contract.yaml › head_event_capture` has the detail. Floor alpha and beta share one acceptance gate and report the same live time; each reference channel reports its own. A chain whose live fraction or bias current leaves its window reports `SATURATED` and null counts, never zeros.
- Bias: one programmable low-noise supply (design range 20–60 V to cover onsemi, Hamamatsu and Broadcom devices) with per-channel anode trim (0–2.5 V) and a firmware temperature-compensation loop from sensors at the SiPMs. Coefficients, set-points and thresholds are part of the `setup_id`; changing them invalidates the binding as the ICD requires.
- Isolation is at the head end of the RS-485 link. The bus side of the head transceiver is powered from the chassis through J2, so the head contains no isolated DC-DC converter radiating next to the front ends, and the head's only DC ground connection to the robot is the J1 electronics return. The heater has its own feed and return pins on J1 (DEC-025) and switches only on gate boundaries with a slew-limited edge; the gate that contains a transition is marked in the diagnostic record.
- Unknown OEM values are handled as explicit design ranges with a named test point and the component selection each one drives; see `electronics/analysis/head_afe_budget.md` (owned by the head electronics lead).

## 5. Chassis electronics concept (DEC-026, DEC-027, DEC-028)

- **Traction chain.** Traction energy exists only while a self-holding relay latch is set. Series elements, in order: `MODE_RUN`, `ESTOP` (two poles), `HANDS_ON`, `CHG_COVER`, `HEAD_DOCK`, `HEAD_LOOP`, `LAB_KEY_N`, `BODY_BUMPER`, `WDG_OK`, `ARM_PERMIT`. When the latch drops, VMOT is removed and each motor is connected across a brake resistor by the normally-closed contacts of its DPDT relay, so braking needs neither power nor firmware. The latch can be set only by the local REARM button with every element healthy. The motion MCU reads back every element, the latch, VMOT and the brake-relay state, and runs a stationary brake test before the first motion of a mission.
- **Two stop levels.** Hardware inhibit (`HW_INHIBIT`) for chain elements; software `PROTECTIVE_STOP` latch in the motion MCU for field intrusion, cliff, stale sensors and command timeout. Neither clears by itself. The software latch clears on a deliberate REARM by the controlling operator or the local button; the hardware latch only by the local button.
- **Drive.** Two integrated H-bridges on the main board; the motion MCU closes the wheel speed loops and limits current. The RoboClaw in the 0.3 BOM remains a bring-up alternative only.
- **Charge/service.** On-board buck charger with power path (LTC4162-F class) from an external 24 V supply. The service load is fed from the input side so charge termination is not disturbed. Charging is refused below +5 °C pack temperature by the charger's thermistor qualification; the pack's own BMS is a lower backstop (the baseline pack's datasheet charge range starts at 0 °C), not a second +5 °C channel. Opening the inlet cover opens `CHG_COVER`; a link in the charge plug is the second channel. Charge/Service has priority over LAB.
- **Head presence.** J1 pin 7 carries a resistor code that distinguishes no head, head, head through the LAB extension, and extension alone; J2 pin 7 detects the data connector. Transitions are latched by hardware-timed sampling in the motion MCU event log independently of serial polling, so a brief unplug always leaves an event. In LAB (extension present) the chain is open by two independent conditions: undocked and LAB code.

## 6. Personnel protection concept (DEC-032) — design intent, all trials pending

1. Inherent limitation: ≤ 12 kg, ≤ 0.20 m/s forward, ≤ 0.05 m/s reverse, yaw rate limited so the outer head corner stays under 0.10 m/s, wheel current limit, rounded contact surfaces. Push force is expected to be traction-limited; to be measured.
2. Contact detection wired into the traction chain: head rail (front, left, right with rear returns) and body bumper. The rail must provide at least 15 mm of stroke after it trips: the calculated travel after contact at 0.10 m/s is 14.3 mm with the conservative brake model and 27.5 mm with the 0.3 stop-model inputs, against 7–11 mm of lead in Rev D, which had no designed stroke. Until that stroke exists in the head design and is measured, stopping inside the rail travel is not demonstrated at any survey speed.
3. Near-field ranging in the motion MCU: 4 downward cliff, 4 oblique look-ahead, 3 rear proximity sensors; stale or disagreeing samples stop the affected motion. The MCU has **no forward or sideways personnel ranging**: in those directions the only protection that does not depend on the Linux host is contact (head rail) plus the inherent speed and force limits; the LiDAR route hold of item 4 runs in the host.
4. Route hold in the host: LiDAR returns inside the swept region of the commanded move (body plus projecting head, forward, reverse and turning) hold the move and leave the obscured floor open for a return pass.
5. Hands-on work: HANDS-ON maintained button or E-stop, both hardwired, both indicated from the real chain state.

This is not a certified safety function. The verification register keeps the braking, personnel-protection and occupied-area trials (VT-003/004/005/035) open.

## 7. Host interfaces

- **Head link**: protocol 2.0 exactly as `interface/head_icd.md`. The host is link master over a USB-UART bridge and RS-485 transceiver on RR-CHS-MAIN. Additive `DIAG` op for engineering counters.
- **Chassis link**: `RR-CHS 1.0`, same record framing over USB CDC; op table in `contract.yaml › chassis_link`, full text in `interface/chassis_icd.md` (owner: chassis firmware lead). The cyclic `DRIVE` exchange carries the bounded command with a time-to-live and returns odometry, IMU and stop state in the same transaction.
- **Time**: both device clocks are fitted against the host monotonic clock with the four-timestamp exchange; counts are mapped only while the bound is ≤ 10 ms (target ≤ 2 ms). Odometry is stamped on the chassis clock at the encoder sample, not at USB arrival.

## 8. Software architecture (DEC-030, DEC-035)

- Firmware is portable C: a hardware-independent core per MCU plus thin ports (`stm32g4`, `host`). The **emulated head** and **emulated chassis** are the real firmware cores compiled for Linux, so the handshake, binding, buffering and stop logic exercised in simulation are the shipped code paths.
- ROS 2 Jazzy workspace `ros2_ws/`: `rr_interfaces`, `rr_head_driver`, `rr_chassis_bridge`, `rr_localization`, `rr_coverage`, `rr_mapping`, `rr_web`, `rr_sim`, `rr_bringup`. Localization and coverage are purpose-built for a rectangular trailer (wall-referenced estimator, straight serpentine passes with offset recovery lanes); Nav2 is not a dependency in 0.4 and stays available as an alternative behind the same `DRIVE` interface.
- Count processing lives in a ROS-free Python library so it can be replayed offline and tested without the middleware.

## 8a. Survey methods (DEC-038)

Definitions are in `contract.yaml › survey_methods`. Mission-time estimates below are `calculated` for a 2.5 × 16 m floor with the 175 mm effective swath per pass that closes the 7.5 mm seams (15 passes, 240 m of travel, about 6 min of turns), an 80 mm station pitch (aperture length less the position-erosion allowance on each side, so credited footprints abut), move-and-settle of about 1.6 s per station, and no allowance for holds or pack swaps.

| Method | Parameters | Estimated time | Comment |
|---|---|---:|---|
| Search then count | 0.10 m/s search; scaler counts only at alarms | 46 min + (count time + ~10 s) per alarm | Fits one pack if alarms are few. Floor without an alarm is credited at the search-stage detection limit. |
| Continuous scan | 0.025 m/s (4 s dwell) | about 2.8 h | Speed set by the dwell the detection goal needs. |
| Step and count | 3000 stations, 5 s counts | about 5.5 h | Static counts everywhere; several pack swaps. |
| Step and count | 3000 stations, 10 s counts | about 9.7 h | |

These are the first planning estimates (0.10 m pitch, turns and wall tracks not counted). The planner's calculated figures for a 2.5 × 16 m trailer with the contract's 0.080 m station pitch and the reverse-entry wall tracks supersede them and are kept in `ros2_ws/README.md` section 8.1 with their assumptions: search at 0.10 m/s about 1.0 h, continuous scan at 0.03 m/s about 2.8 h, step and count with 10 s counts about 12.2 h (calculated/simulated).
| Step and count, single pass family | 1600 stations, 10 s counts | about 5.2 h | 8 passes; the 7.5 mm seams between windows are reported unresolved. |

Pack swaps require the trailer datum to be re-registered (0.3 rule, retained); the mission supervisor checkpoints so a multi-pack survey continues as one record with separate epochs.

## 9. File ownership for parallel work

| Path | Owner |
|---|---|
| `interface/system/`, `docs/architecture/`, root `README.md`, `Makefile`, `release/` | Integration lead |
| `tools/eda/`, `tools/docker/`, `electronics/tof_carrier/` | EDA infrastructure |
| `electronics/head_acq/`, `electronics/analysis/head_*` | Head electronics |
| `electronics/chassis_main/`, `electronics/panel/`, `electronics/modules/`, `electronics/analysis/chassis_*`, `electronics/analysis/power_budget.md` | Chassis electronics |
| `harness/` | Harness (after board connectors freeze) |
| `firmware/common/`, `firmware/head/`, `interface/head_*` additions | Head firmware |
| `firmware/chassis/`, `interface/chassis_icd.md` | Chassis firmware |
| `ros2_ws/`, `software/` additions | Robot software |
| `mechanical/common/` | Mechanical lead (master layout) |
| `mechanical/head/` | Head mechanical (both builds) |
| `mechanical/prototype_x1c/` | Prototype mechanical |
| `mechanical/production/` | Production mechanical |
| `analysis/radiometry/` | Radiometry |
| `planning/`, `docs/build/`, `docs/service/` | Documentation and registers |

Baseline directories (`cad/`, `examples/`, `reference/`, `docs/Rad_Roomba_Design.*`, `software/map_demo.py`) stay as the 0.3 record; new work goes in the new paths and supersedes them explicitly.

## 10. Decisions taken in this revision (appended to `planning/decisions.csv`)

| ID | Decision | Reason | Interfaces affected | Reversible? |
|---|---|---|---|---|
| DEC-021 | Head envelope ceiling raised from z = 42 to ≤ 50 mm | Rev D has ~4 mm above the reference guides; the acquisition board needs ~12 mm. | Look-ahead sightlines, head mass/CG, descriptor envelope, body nose clearance. | Yes |
| DEC-022 | Board partition of §3 | See §3. | Harness, CAD mounts, firmware pin maps. | Costly after layout |
| DEC-023 | Discriminators + event logic + MCU; amplitude windows with slow-path alpha. *The FPGA part of this decision is withdrawn by DEC-037.* | Low power; PSD development path kept. | Head firmware, descriptor `setup_id`. | Yes (digitiser later) |
| DEC-024 | RS-485 isolation at the head, bus side powered from chassis | No isolated DC-DC next to the front ends; single DC ground path. | J2 pinout, both boards. | Yes |
| DEC-025 | J1 = M16 8-pole with separate heater pair and presence code; J2 = M12 A-coded 8-pole with presence link and reserved sync pair | Heater current out of the electronics return; connector families cannot cross-mate; off-the-shelf shielded extensions. | Head ICD §3 (pin numbering now defined), harness, LAB extension. | Before harness build |
| DEC-026 | Self-holding latch + DPDT brake relays; local-only hardware re-arm; HANDS-ON button | Defined stop on any power loss or inhibit, independent of firmware. | Chassis board, panel, operator procedure. | Yes |
| DEC-027 | H-bridges on the main board, loops in the motion MCU | One loop owner; removes a second firmware and a module. | Chassis firmware, BOM W11. | Yes (RoboClaw fallback) |
| DEC-028 | On-board power-path charger, external 24 V supply | Service load must not defeat termination; cold-charge gate in hardware. | Charge inlet, BOM W29/R03/R04. | Yes |
| DEC-029 | `base_link` on the floor under the axle (= CAD origin) | Removes the axle-height offset as an error source. | All transforms. | Before data collection |
| DEC-030 | Purpose-built localization and coverage; no Nav2 dependency in 0.4 | Rectangular known space, straight precise passes; smaller qualification surface. | Robot software only. | Yes |
| DEC-031 | Chassis link `RR-CHS 1.0` reusing head framing | One codec, one test set. | Chassis firmware, bridge node. | Yes |
| DEC-032 | Layered personnel protection of §6 | Protective stop must not depend on ROS or the browser. | Sensors, firmware, procedures, VT-035. | Trials decide |
| DEC-033 | Production: CNC aluminium + MJF PA12, 5–25 units/year | No tooling; metal head frame gives stiffness, shielding and heat spreading. | Production drawings, requalification list. | Yes |
| DEC-034 | Printed head housing split at the y = 0 rib with full-width stiffening rods and a one-piece spreader plate | 350 mm exceeds the X1C plate; the joint sits in an inactive seam. | Head mechanical, light-tightness test. | Prototype only |
| DEC-035 | Portable firmware cores; emulators are native builds of them | Full path testable before optics or boards exist. | Firmware, simulation. | — |
| DEC-036 | Software time sync now; hardware pulse pair reserved on J2 | Meets the 10 ms bound by calculation; keeps an upgrade path. | J2, both boards (DNP parts). | Yes |

| DEC-037 | No FPGA in the head. Event classification, counting and live time use discrete latches and the MCU's 32-bit timer captures; head MCU becomes the 100-pin STM32G474VET6. Raised by Morgan's challenge on 2026-11-26. | At the expected rates (≤ ~2000 s⁻¹ per chain) measured dead time is a few percent; programmable logic added a toolchain, a second firmware artefact, a 1.2 V rail and a skill requirement for no measurable benefit. | Head board, head firmware pin map, `gateware/` removed from the tree (kept in git history). | Yes |
| DEC-038 | Three selectable survey methods: ratemeter search then scaler count (inline or deferred), step-and-count scaler survey, continuous scan. Requested by Morgan on 2026-11-26. | Matches how direct measurements are specified in RP procedures; lets the site trade mission time against a static, well-defined count. | Mission supervisor, processing, UI, site profile, report. | — |

| DEC-039 | Rev E body: Rev D section law scaled 1.40 long, 1.30 wide and high, growth rearward and upward; track 270 mm, caster 204 mm behind the axle; transverse bridge grip over the CG; LiDAR aft. Overall about 537 × 350 × 216 mm as accepted by Morgan on 2026-11-26 with the Rev D neck; 464 × 350 × 230 mm after the head mount change (DEC-041) and the 12 Ah hump (DEC-040). | The Rev D body has about 1.84 L of cavity for 2.14 L of bare component envelopes and its hand well occupies the battery location. | Frames, footprint, sight lines, both mechanical builds, transport tray. | Parametric |
| DEC-040 | 12 Ah pack (Power-Sonic PSL-SC-12120 class) is the baseline; tail height grows to suit. Accepted by Morgan 2026-11-26. | Multi-hour step-and-count surveys, ~21 W heater load at −20 °C, and aft mass that restores the forward tip margin. | Battery bay, cassette, power budget, mass/CG. | Yes |
| DEC-041 | Head mount: option C adopted — twin-shoe receiver on the lane seams (y = ±87.5) under a chassis front beam, one draw latch, neck deleted, optics row moved from x = 204 to 131.2 mm. Opened by Morgan 2026-11-26; closed by the trade study `mechanical/common/out/head_mount_trade_study.md` (calculated). | Against the Rev D neck (printed build): corner deflection under 20 N 0.74 → 0.19 mm, first mode 45 → 84 Hz, gap sensitivity to caster height 1.00 → 0.64, forward tip margin +5.8 → +26.6 mm with the 12 Ah pack, overall length 537 → 464 mm. A floor-following head was rejected (floor contact ahead of counting, new calibration concept) and kept as fallback. | Head mount datum, optics row x, head envelope, head board origin, body nose, sensor positions, descriptor mount transform. | Parametric |
| DEC-042 | Carry grip bar moved aft to x = −30 mm (was −11); software tail swept radius 0.290 m (rear bumper included). Lead decision 2026-11-27 on the prototype-body change requests CR-04 and CR-09. | Calculated hang angle with a head fitted about −21° tail-down with the bar at −11, about −10° at −30 (target ≤ 10°, IB-10); as-built tail incl. bumper 289.2 mm from the axle centre against 278 mm assumed (IB-48). | Grip side plates, saddle cover, look-sensor fairing; contract draft7; planner wall strip and door-end margin (to be re-run). |
| DEC-043 | Oblique look sensors: two forward (LOOK_FL, LOOK_FR, grip cheeks, over the head) and two rearward (LOOK_RL, LOOK_RR, tail). Lead decision 2026-11-27 (IB-34). The pair facing the direction of travel acts; stop reasons LOOKAHEAD_L/R keep their names. | Contract and firmware named four forward sensors while the mechanical frames placed two forward and two rearward; reversing toward a threshold or dock edge needs a floor check behind the tail. | Chassis firmware IDs and field logic, ICD, harness names and lengths, frames. |
| DEC-044 | Cell decision (MODEL.md revision 5, IB-31): every decision statistic is one fixed linear combination of Poisson gate counts with its threshold from the exact distribution (Gil-Pelaez inversion), averaged over the uncertainty of the null reference (predictive threshold); a cell is flagged by the combined test at 0.8α or by any contributing lane's own test at 0.2α/m; the null reference is specified by reference counts in two sub-windows; each cell has one recorded evaluation on complete data and earlier values are provisional; an alarm is never suppressed by coverage. Revisions 3 and 4 of the same day are superseded. | The analyst's checks refuted revision 3 (false-alarm excess up to 1.24, 4.4 in the alpha channel; detection-limit penalty 1.3–2.4) and showed the revision-4 window rule left cells undecidable; the independent data-path review showed exported decisions depended on evaluation timing. Calculated and simulated with synthetic coefficients. | Processing code, export and archive formats, calibration records, detectability study. |
| DEC-045 | Thermal policy: the battery bay is not regulated to +10 °C on pack power (hold ≥ −10 °C when discharging, pre-heat to ≥ +5 °C on external power for charging); a thermal break between the head receiver channels and the chassis plate is required. Lead decision 2026-11-27; head set-point +5 °C at the SiPM carrier by owner decision 2026-11-27 (was +10 °C). | Calculated: holding the pack skin at +10 °C needs 22 W at −20 °C, more than the capacity it recovers; metal receiver channels at plate temperature raise head heater demand to 43–66 W against 30 W fitted. | Chassis firmware heater set-points, power budget and runtime tables, receiver channel mounting in both body builds, operator cold procedures. |

Confirmed by Morgan on 2026-11-27 (later the same day): head heater set-point +5 °C at the SiPM carrier instead of +10 °C (contract draft9 `power.thermal_policy.head_setpoint_c`; DEC-045). Calculated demand in still air with the jacket: about 14 W at −20 °C and 17 W at −25 °C; the optics supplier's temperature limits remain unknown.

Confirmed by Morgan on 2026-11-27: (1) the review queue takes only cells that alarm at the profile's scan-stage false-alarm rate; cells that merely cannot be cleared are shown as "sensitivity insufficient" and reported as residual area (`survey_methods.review_queue_policy`, default `ALARM_ONLY`, a site-profile setting); (2) for the two large boards, keep iterating with the routing tool and long unattended runs, then deliver schematic, placement, planes and partial routing with an exact list of open connections for a person to finish in KiCad; both boards need a layout engineer's review before fabrication in any case.

Confirmed by Morgan on 2026-11-26 (later the same day): build the reverse-entry lane change so the unsurveyed strip along each side wall shrinks from about 0.14 m toward about 44 mm; and, for long trailers, require closed doors or a removable flat target across the door end as the along-trailer reference (preflight condition).

Confirmed by Morgan on 2026-11-26: (1) during step-and-count the pre-motion alert is one full alert at the start of a series of hops and a short chirp per hop (host raises `alert.rest_ms` above the station time by a logged `CONFIG_SET`); (2) a Pause pressed on the robot may be cleared remotely by the controlling operator (`REARM_SW`); it is a program control, not a hardwired inhibit — the E-stop and HANDS-ON button remain local-only.

Confirmed by Morgan on 2026-11-25: local-only hardware re-arm is accepted for the unattended mode (a bumper or E-stop trip ends an unattended mission until someone attends) — DEC-026; the 5–25 units/year production assumption — DEC-033; navigation left to the lead's recommendation, which is to keep DEC-030 (no Nav2 dependency in 0.4, with Nav2 remaining a possible alternative behind the same `DRIVE` interface).

## 11. Open external dependencies

| Dependency | Blocks | Work that proceeds without it |
|---|---|---|
| Optical supplier section drawing, SiPM model/count/capacitance, connector, pulse data | Final front-end component values, SiPM pigtail connector, lane cavity dimensions, thermal sensor position | Board with documented design ranges and selectable values; housing with a parametric lane cavity; firmware; all software. |
| Site patch size, photon field envelope, decision probabilities (DEC-001/002/012) | Any sensitivity claim, enabled field profile | Parametric detectability study, demonstration ore profile, processing code. |
| Traceable calibration (K, k, b with covariance) | Bq/cm² reporting for release decisions | Pipeline with synthetic coefficients flagged `field_use_approved: false`. |
| Physical trials: braking, personnel protection, cold, radiometric | Operating envelope, speeds, unattended mode | Everything up to fabrication review. |
