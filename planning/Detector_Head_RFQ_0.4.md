> **Design 0.4 version.** This file carries the system-design 0.3 request (`Detector_Head_RFQ.md`) forward unchanged below the line marked *Baseline text*; the section **Additions for design 0.4** at the end is new and takes precedence where it is stricter. Numbers in the additions come from the project files cited beside them. Values marked *assumed* or *calculated* are project design inputs, not measurements, and no supplier response exists in the repository.

---

*Baseline text (design 0.3, unchanged):*

# Request for quotation — OEM scintillation optics for a modular floor-survey head

**Project:** Rad Roomba engineering prototype  
**Requested commercial item:** Bonded scintillator, light guide and silicon photomultiplier (SiPM), supplied as an optical assembly with a passive electrical termination.  
**Response requested from:** Detector manufacturer or optical assembly integrator  
**Units:** mm, cm², ns, °C and SI electrical units unless stated otherwise.

## Application and quantities

A carryable robotic platform scans trailer and shipping-container floors at uranium facilities. Four independently measured floor lanes form the transverse survey swath. Each lane has a separately read upper reference to help estimate the photon contribution in elevated, variable gamma/X-ray fields. The project team will integrate the supplied optics into its own enclosure and heater system. During the attachment handshake, the head MCU supplies its identity, dimensions and optical geometry. Subsequent acquisition records carry raw counts, live times, timing and health. The host computer owns material calibration, background compensation and conversion to Bq/cm². The supplier scope is the optical assemblies with optional pulse discrimination.

Please quote **one prototype lane**, comprising a floor assembly and a reference assembly. Also quote **one four-lane head set** comprising four of each. Price non-recurring engineering, tooling, samples, optional readout, test data, and repeat sets separately. If four lanes require a common carrier, indicate the equivalent one-lane development article and whether its optical response is representative. Include availability to Canada, lead times, minimum order, pricing currency, drawing ownership and the process for reporting material or SiPM substitutions.

## Requested construction and data

| Item | Requested configuration or quotation deliverable |
|---|---|
| Floor assembly | Floor-facing ZnS(Ag) layer on thin active plastic, e.g. EJ-444 or characterized equivalent. Quote nominal 0.25 mm plastic as a starting point and identify any thickness needed to manufacture a rectangular tile. Specify plastic type, coating areal density and tolerances. |
| Readout | Polished low-profile guide with side-mounted SiPM or SiPM array, optical bond, opaque isolation and passive carrier. Give part number, active area, terminal assignment, polarity, recommended overvoltage, breakdown spread and temperature coefficient, capacitance, and mechanical strain relief. |
| Reference | Separately read, optically isolated upper tile. Quote a matched plastic geometry. Advise on alternatives and how spectral/angular response differs from the lower beta/gamma channel. Identify masses and materials between active layers that could affect reference response or attenuate the surface signal. |
| Geometry | Our trial active window is **80 mm across travel by 100 mm along travel**, repeated on **87.5 mm pitch** in a **350 mm carrier**. Submit a dimensioned cross-section and STEP envelope showing the active aperture, borders, collection optics, reference plane, wire exit, minimum bend radius, mass tolerances, centre-of-gravity location and allowable mounting loads. Report active window height relative to a reproducible mounting datum so we can verify the loaded 10 mm standoff. Mark proposed departures. |
| Window and guard | Our new trial geometry places the entrance film 10 mm above a level floor. A separate compliant bumper would sit 3 mm below the film (7 mm ground clearance). We will compare a 5 mm projection, leaving 5 mm clearance. Specify which face defines the entrance plane, permissible contact load and the mass and centre of gravity of the complete optical pair. Itemize any manufacturer-supplied protective film, reflective layers and grille, their areal density, open fraction, replacement method and effect on light tightness. |
| Winter | The assembled robot starts warm and works in −20 °C ambient, with −25 °C as a stretch condition. Supply operating and storage ratings of the **bonded assembly**, allowed thermal gradients or ramp rates where known, and any environmental test reports. Identify the temperatures used for the quoted response. |
| Readout option | As a separately priced option, quote alpha-like and beta/gamma-like event outputs, independent reference events, and analog waveform access. Specify thresholds, dead time, pile-up or overload indication, output levels, simultaneous access and sample waveforms. |
| Characterization | Provide available near-edge, centre, far-edge and corner response including measurement uncertainty, source, active source area, spacing, window, threshold and reference conditions. Identify measured inter-lane optical crosstalk, pulse distributions, and photon response by channel across available energies and angles. Clearly distinguish existing data from proposed characterization. |

The robot’s proposed ore investigation setting is 0.30 Bq/cm². The project seeks moving-scan sensitivity below 0.20 Bq/cm² for a still-to-be-agreed hotspot size, standoff envelope, speed and site background. The project team will determine that system performance using calibrated complete heads. Supplier efficiencies should state their denominator, e.g. 2π surface emission rate or source disintegrations, and the applied source geometry. An answer listing the closest manufacturable construction, all departures, and optional tests is sufficient for engineering evaluation.

## Team bench record

The companion file `detector_bench_runs.csv` is a blank data-entry layout for project testing. Supplier equivalent formats are welcome. Record one row for **one physical lane during one acquisition interval**. Lanes 0–3 run from the robot’s left to right facing the direction of travel. Enter synchronized gross counts before compensation and a separate live time for each stream. Enter literal zero for a valid measured zero. Leave an unavailable field empty and record the reason under `quality_flags`.

Preserve traceability to the unmodified acquisition file and configuration. `test_type` can cover dark, clean photon field, known uniform source, spot traverse, seam traverse, repeated pass, thermal or heater/motor interference. `replicate_id` identifies independently repeated trials. `t0_head_s` and `t1_head_s` share a monotonic head clock within `boot_id`. Use `source_profile_id` to link the source identity, calibration date, activity basis and reference date. Populate `reference_activity_Bq_cm2` only for a known areal activity under that basis. Use `photon_field_id` for spectrum/geometry, and specify orientation in the field record. Define a right-handed coupon or floor frame and trajectory in the referenced `test_geometry_id` record. Enter `segment_x_mm` and `segment_y_mm` as the lane centre at bin midpoint expressed in that frame. Store source location, effective area, floor finish, beam angle and their uncertainties in the referenced record as applicable. Identify thresholds, bias, heater settings and any absorber in `configuration_id`. The host supplies the head and boot references and its own attachment_session_id to the worksheet from the connection manifest. This UUID distinguishes disconnect/reseat on the same controller boot. Ordinary count replies omit those identity fields. The runtime acquisition format and timing contract reside in the interface specification.


## Tethered laboratory use

The project will connect the detached head to the stationary base with a dedicated extension harness and place the head on a controlled geometry fixture. The project supplies the isolated data and protected power interface. The head-to-base mechanical mating and enabled field safety chain are independently checked. A dedicated lab state physically inhibits traction even when the head responds correctly. To support integration, please report electrical output loading, bonding/ground provisions, temperature-sensing options and sources of noise or drift. Include the mass of each proposed protective grille, window and guide when quoting.

In the worksheet, `source_response_check` is a repeatability or bump check with a known source, reproducible jig and site-established acceptance band. `efficiency_calibration` uses traceable areal activity, a measured gap and registered background to derive a response coefficient and uncertainty. `contact_bumper_function` is a mechanical/electrical stop-chain test and requires no radioactive source. Record the actual head configuration and active lane, harness and fixture IDs, setup mode, measured bumper projection, actual/swept standoff, and independent drive-inhibit state. Exercise the patch with the heater loaded and measure supply drop, data errors and any correlated count bias against the normal harness. A passed source-response bump check alone does not update calibration. Only a site-controlled review issues a new calibration revision.

---

## Additions for design 0.4

Each item below adds to the request above. Cited files are in the project repository (`electronics/analysis/head_afe_budget.md` is called the AFE budget; `mechanical/common/out/mechanical_interfaces.md` the mechanical interface file).

### A. Guaranteed and tested photoelectron yield per beta event

The head's beta channel can work only if the optical assembly delivers enough photoelectrons (p.e.) at the SiPM for a beta event to stand above the SiPM's dark and crosstalk pile-up. Please state, guarantee and test a **minimum and a typical p.e. yield per beta event at the SiPM output**, for the full-size floor lane, at your stated overvoltage and at a stated temperature, with the source, energy spectrum, threshold and p.e. calibration method used.

Threshold context (AFE budget sections 1, 3.2 and 12; *calculated* from datasheet dark rate and crosstalk with an *assumed* temperature law of a halving every 8 degrees C, good to about +/-1 p.e.):

| Device and condition | Lowest usable beta threshold, p.e. (dark trigger rate below 1 per second) |
|---|---|
| One 6 mm device (onsemi MicroFJ-60035 at +2.5 V overvoltage, typical dark rate) | 10 at +25 C, 8 at +10 C, 8 at 0 C, 7 at -20 C |
| One 3 mm device (MicroFJ-30035) | 8 at +25 C, 7 at +10 C, 7 at 0 C, 6 at -20 C |
| Four 6 mm devices in parallel (MicroFJ-60035 at +2.5 V) | 14 at +25 C, 11 at +10 C, 9 at 0 C, 8 at -20 C |
| Hamamatsu S13360-6050 (low crosstalk) | 7 at +25 C, 6 at +10 C, 6 at 0 C, 5 at -20 C |
| High-overvoltage operation (MicroFJ-60035 at +6 V) | 25 at +25 C, 21 at +10 C, 20 at 0 C, 17 at -20 C |

Against these thresholds the project's own assumption for the beta signal is 4 to 120 p.e. with 15 typical (*assumed*: 51 keV deposited by a minimum-ionising electron in 0.25 mm plastic, about 10^4 photons per MeV for an EJ-212-class plastic (*unverified*), 0.5 to 8 % light collection times SiPM photon detection efficiency; no measurement exists). The margin is thin and does not exist if the real yield is at the low end of that range; this is the head's principal risk (AFE budget section 12). The project will therefore accept a quotation only with a stated minimum yield, and will repeat the measurement on delivered lanes (pulse-height spectrum from a Sr-90/Y-90 or Tl-204 source by threshold scan and on the 50 ohm monitor; dark threshold scan at +25, +10 and 0 degrees C; verification test VT-042). The margin the project requires between the guaranteed yield and the lowest usable threshold is not fixed in the project files and is set by the head electronics lead before an order.

Please also state, for the reference tile, the p.e. yield for photon-induced (Compton) events (project design range 10 to 600 p.e., *assumed*), and, for the ZnS(Ag) alpha layer, the p.e. and time profile of a 5 MeV-class alpha (project design range 150 to 15 000 p.e., *assumed*; about 70 % with 200 ns decay and 30 % in a microsecond tail, *assumed*).

### B. Two coaxial connections per SiPM

Bring out **both SiPM terminals (anode and bias/cathode) on separate 50 ohm micro-coax leads** (U.FL/MHF class; the head board uses Hirose U.FL-R-SMT-1(10) receptacles; locking MHF-LK plugs fit the same receptacle; 1.13 mm coax is accepted), with the shield as signal return, a bias decoupling capacitor of at least 10 nF on the carrier, and a free length of about 35 mm from the carrier to the board connectors. Reason (AFE budget section 3.4, *calculated*): the SiPM front ends are about 65 mm ahead of brushed gearmotors driven by a 20 kHz-class PWM bridge, and an open 0.5 cm2 pigtail loop picks up about 10 p.e. at every PWM edge, which fails; coaxial leads reduce this to about 0.4 p.e. before any shield. Please state coax type, length, connector, minimum bend radius and the loop area left at the launch.

### C. Temperature sensor on the carrier

Fit a **10 kohm NTC within 5 mm of the SiPM** on each carrier (the head board reads it through a lane auxiliary connector, JST GH-6, which also carries an optional LED pulser line and 3.3 V for an active sensor; CCR-HE-06 of `electronics/head_acq/design/CONTRACT_CHANGE_REQUESTS.md`). Please state the sensor part, its location relative to the SiPM junction, its thermal lag and its tolerance: the sensor lag sets the residual gain error for the high-temperature-coefficient devices (AFE budget section 12, item 6).

### D. Breakdown-voltage matching across the eight SiPMs

Please report the **breakdown voltage of every SiPM** of a head set at a stated temperature and match the eight devices of one head. The head board can trim the anode of each channel over 0 to 2.5 V; the AFE budget (section 1) uses a design limit of 2.4 V for the spread between the eight devices and notes that a larger spread cannot be covered by the board and would require binning at purchase. The head electronics request (CCR-HE-06) asks for a match within 2 V. The two figures are not yet reconciled; please quote against 2 V and state what you can guarantee. Please also state the V_br temperature coefficient (datasheet range of the candidates 21.5 to 54 mV per degree C), the recommended overvoltage, and note that the bias supply covers 20 to 60 V (62.5 V hardware full scale): devices with V_br above 56.5 V (Hamamatsu S13360 family) are outside that range; request V_br of 56 V or less if that family is offered (CCR-HE-05).

### E. Rating to -25 degrees C

The project works at -20 C ambient with -25 C as a stretch condition (see *Winter* above). Please state operating and storage ratings to **-25 C for the SiPM, wire bonds, optical bond, film, adhesives and carrier**, and the allowed ramp rates. Two candidate SiPM families in the AFE budget are rated only to -20 C in their datasheets (Broadcom AFBR-S4N66P024M, -20 to +60 C; Hamamatsu S13360, -20 to +60 C, *unverified*); the head board sits above a heated spreader at about +10 C in normal use, but the SiPM and carrier see the optical stack temperature. If your device does not reach -25 C, say so and give the lowest temperature you will warrant.

### F. Mechanical envelope and connector exit against the current lane cavity

Design 0.4 changes the head mounting (twin-shoe receiver, DEC-041), so the head moves rearward and the optics row sits at x = 131.2 mm in the robot frame (contract `interface/system/contract.yaml`, `frames.optics`). The values the supplier's assembly must fit are:

| Item | Value | Source |
|---|---|---|
| Entrance film above a level floor (nominal) | 10.0 mm | `contract.yaml` frames.optics.entrance_film_z_mm |
| Active window, along travel by across travel | 100 mm by 80 mm per lane | `contract.yaml` frames.optics |
| Lane pitch; lane centres (robot-left first) | 87.5 mm; y = +131.25, +43.75, -43.75, -131.25 mm | `contract.yaml` frames.optics |
| Nominal seam between windows; outer margin | 7.5 mm; 3.75 mm | `contract.yaml` frames.optics |
| Optical stack | everything below z = 28.5 mm (head frame top / module retention pad underside); the module retention pad and heater film occupy z 28.5 to 30.0 mm; the one-piece 2.0 mm spreader plate z 30.0 to 32.0 mm | `mechanical/common/out/mechanical_interfaces.md` sections 0 and 2 |
| Rear chimney for the SiPM carriers and pigtails | 9 mm deep behind the spreader at the lane centres | `mechanical/common/out/mechanical_interfaces.md` section 2 |
| Rail projection options below the film | 3 mm (7 mm floor clearance) or 5 mm (5 mm clearance) | `contract.yaml` frames.optics.rail_projection_options_mm |
| Board-side landing of the SiPM leads | per lane, floor-channel anode and bias U.FL at 11 and 6 mm left of the lane centre line, reference-channel pair at 6 and 11 mm right, 4.5 mm minimum centre-to-centre, at the rear edge of the board | `electronics/head_acq/design/layout_guidance.md` section 1 |

The project holds the lane cavity as a parametric design range; **a per-lane section drawing from the supplier (SiPM position, carrier outline, connector exit direction and position, thicknesses, mass and centre of gravity, allowable mounting loads) is still outstanding** and gates the lane cavity dimensions, the SiPM pigtail connector and the thermal sensor position (`docs/architecture/SYSTEM_ARCHITECTURE.md` section 11). Please submit a dimensioned section and a STEP envelope against the limits above and mark any departure. Note for the supplier: head-internal coordinates in `layout_guidance.md` section 4 (rear chimney position in robot coordinates) still carry Rev D neck-mount values and are superseded by the mechanical interface file; use the head-frame dimensions above.

### G. Reference tile options with higher photon sensitivity

The radiometry study (`analysis/radiometry/report/detectability_report.md`, conclusions 2 and 3, *calculated* with assumed coefficients) finds that a matched reference tile raises the detection limit by a factor 1.36 in a uniform photon field (1 uSv/h, 1 s pass), whereas a reference with ten times the photon count rate of the floor tile reduces the penalty to 1.05, and pooling the four references to 1.11, provided the more sensitive reference does not bring a larger spectral mismatch. Photon interactions in thin plastic scale nearly linearly with thickness, so a reference tile several millimetres thick is expected to give a floor-to-reference count ratio k of 0.1 to 0.3. Please **quote reference-tile options of 0.25 mm (matched), 2 mm and 5 mm thickness** (the thicknesses the study proposes to measure), and state for each: whether it fits the optical stack envelope above, the light yield, and how its photon response differs in energy and angle from the floor tile. Constraints from the study: the reference must be shielded from floor betas up to 2.27 MeV (Pa-234m) and 3.27 MeV (Bi-214), about 1.1 g/cm2 of absorber, and a low-Z absorber (aluminium or the plastic light guide) keeps the spectral mismatch smaller than steel; a thicker tile adds wall-electron and threshold differences that the model does not capture and that must be measured.

### H. Leakage tests

Please report, or quote as an option, these leakage measurements on the offered construction:

1. **Floor-signal leakage into the reference channel**: the fraction of a floor-facing beta signal (planar source on the floor side, beta end points up to 3.27 MeV) that appears in the reference channel, per absorber option, stated as a fraction of the floor-channel response. The study shows that a fraction epsilon of surface signal reaching the reference suppresses the true signal by k times epsilon, so epsilon must be known to about 1 % absolute for a 1 % activity bias (detectability_report.md section 6 and conclusion 8).
2. **Lane-to-lane optical crosstalk** and **floor-to-reference optical isolation**, as asked in the baseline *Characterization* row. The project's electrical crosstalk limit is that a 15 000 p.e. alpha in one channel stays below 5 p.e. in every other channel (AFE budget section 3.3); optical crosstalk adds to it and should be stated in p.e.
3. **Light tightness** of the assembly after film or guard replacement.

### I. Data the supplier must return

With the quotation, or as a stated deliverable with the samples:

1. The dimensioned section drawing and STEP envelope of section F, including mass tolerance and centre of gravity.
2. SiPM part number and count per guide; active area; terminal capacitance per channel; V_br per device and its temperature coefficient; recommended overvoltage; gain; photon detection efficiency; dark count rate against temperature; crosstalk; recharge time constant; operating and storage temperature range (design ranges the head board needs fixed are listed in AFE budget section 1).
3. The p.e. yield data of section A (floor beta, reference photon, alpha), with source, threshold, overvoltage and temperature; sample pulse waveforms for single p.e., beta and alpha events.
4. Carrier wiring: coax type and length, connector type, NTC part and position, any LED pulser or fibre port per guide if available (CCR-HE-06 item f).
5. Leakage and isolation results of section H; response maps requested in the baseline *Characterization* row, separating existing data from proposed characterization.
6. Cold qualification of the bonded assembly to the lowest temperature you will warrant (section E).
7. Lot and device traceability, and the process for reporting any SiPM or material substitution.

All of these are inputs to the design ranges that the head electronics lead has held open (AFE budget section 1) and to the calibration the host will bind to each head.
