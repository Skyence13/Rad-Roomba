# Mechanical concept D

Open **Rad_Roomba_D.step** for the complete robot, **Detector_Head_D.step** for the head alone, and **Mechanical_layout_D.pdf** for dimensioned views, an optical section and ideal cliff sensor sightlines. The STEP solids describe the prototype envelope, datums and approximate signal-path layout. The approved rounded outer form from the earlier body study is retained. The neutral files open without the modelling software. Use the CAD for packaging, bench fixtures and design reviews. Fabrication requires controlled tolerances, detailed hardware, mass properties and test results.

## Datums and optical coverage

The origin is on a level floor below the midpoint of the drive axle. +X is forward toward the head, +Y is left and +Z is up. The drive axle is at z = 52 mm. The separate head STEP uses the vehicle coordinates for overlay. The head description gives geometry relative to the mount. Convert using the surveyed mount transform before mapping counts to the floor.

| Model quantity | Nominal value | Design implication |
|---|---:|---|
| Assembled length × width × height | 430 × 350 × 159 mm | The head sets the width. |
| Width across tires | 245 mm | Each outboard part of the head can encounter obstacles outside the tire paths. |
| Mount datum (x, y, z) | (138.5, 0, 32) mm | Nominal centre of the gap at the plug interface. Confirm installed geometry after assembly. |
| Removable head envelope | x 138.8…265, y −175…+175, z 7…42 mm | Ranges include the contact rails in their unloaded position. |
| Floor window row centre x | 204 mm | Axle to optical row is 204 mm. Receiver datum to row is 65.5 mm. |
| S0, S1, S2, S3 centre y | +131.25, +43.75, −43.75, −131.25 mm | S0 is at robot left. Each reference shares the corresponding floor channel’s nominal x and y. |
| One provisional active rectangle | 100 mm along x × 80 mm along y | 80 cm² per segment before shadowing and efficiency characterization. |
| Segment pitch | 87.5 mm across y | Nominal uninstrumented seams are 7.5 mm. Each outer edge margin is 3.75 mm. The planner needs measured masks and overlap or offset passes. |
| Floor to entrance film / floor-screen underside | 10.0 / 11.0 mm | All four films share the same datum. Confirm the calibrated operating range and surface response with the production guard and film. |
| Forward, side and wing-return rail undersides | 7 mm standard trial / 5 mm alternative | A 3 or 5 mm projection below the window. The bundled model shows the 3 mm trial. |
| Mass and centre of gravity | Weigh assembled prototype | The 12 kg design goal is a mass allocation. Printed and optical solids in this study have illustrative thicknesses. |

Each of the four optical lanes contains an entrance film, window guard webs, floor-sensitive element and light guide, barrier allowance, reference and guide, SiPM/carrier envelopes and upper heater provision. Hide the named cover and frame to inspect the stack. Vendor selection and measurements set the optical materials, film, screens, particle rejection, heating and effective active areas. Include cable, head MCU, discriminator board, temperature sensors and connector backshell space before manufacturing. The drawing uses the term entrance film for the radiologically exposed face.

## Receiver, bumper and floor clearance

Keep the keyed receiver stiff. The drawing introduces two separated bearing lands beside the tongue, with a captive retention envelope. Preload, play, pin proof strength, thermal fits and detachable cable details require design. The contact system has one leading rail, two side rails and two short returns around the outer rear wing tips. Design the switch triggering and overtravel independently of the optical supports. Take impact loads into the head frame and chassis. A raised lip outside an aperture and sparse guard webs across it are different protections. The guard design must be checked for shadowing, cleanability and window survival.

The leading rail's forward surface is 11 mm ahead of the forward film edge, and its rear surface is about 7.4 mm ahead. Run contact and braking trials to establish usable lead after switch travel, tolerances and deflection. Tolerances, vehicle pitch, roll, floor unevenness and flex can consume the small clearance. A point object already inside the perimeter can bypass the rails. Include low, narrow and off-centre obstructions, reverse and turning contacts and objects under a segment. Use sacrificial test windows. Compare 3 mm and 5 mm rail projections for interruption rate, film protection and loss of coverage before selection. Record guard condition and recheck spatial response following configuration changes.

## Mass distribution, gap and service integration

Locate the removable battery low behind the drive axle. Use a captive, glove-operable latch, supported guides, a keyed touch-protected interface and pack-presence indication. Define the retention load and removal path with real pack geometry. Select the service-side charge receptacle and controls together with users wearing gloves. Check charging/service mode, carry grip, charger access, pack extraction, connector segregation and ability to clean the body and head. The retained shell illustrates the grip and local emergency stop. The battery drawer, power switch, separate Start/Resume and Pause/Stop pushbuttons, state annunciators, charge receptacle, charging interlock and head electronics remain to be packaged. Component placement and enclosure cutouts require the selected hardware.

For longitudinal level static balance with both drive contacts at x = 0 and caster at x = −L, the caster carries a fraction −x_CG/L of total weight. Weigh all three contacts, check the support polygon and traction, and test starts, braking and turn reversals at the permitted speeds. Include the lightest and heaviest approved packs and heads and the supported stationary configuration during a pack swap. A rear battery can keep the caster loaded while the head still bounces. At the row, one degree of pitch about the axle produces about 3.6 mm of vertical motion. Roll changes the two outside lanes in opposite directions. For small angles the possible gap error includes chassis heave, pitch times the axle-to-row distance, roll times lateral offset, receiver compliance and local floor height. These terms can add during a seam crossing.

On a guarded floor rig, measure corner-to-floor gaps directly and monitor chassis-to-head motion across representative seams, ridges, crown, debris and braking events over a speed range, both warm and cold. Include temperature, speed, wheel load, screen height and counts in the test record. Compare both contact projections and approved configurations. Establish permitted speed and floor condition from measured clearances, switch response and detector response across the measured gap band. Increase support stiffness, shorten overhang, adjust tire compliance or restrict speed and retest where necessary. Evaluate any floor-following device for sample transfer, cleanability and radiological shadowing.

## Verification and rebuild

The two exported STEP files were re-imported and checked for solid count and extents. The assembly contains 161 solids and the removable head 68. The geometry checker verifies individual solid validity, nominal centre-ray clearance for eight cliff sensor locations, clearances between each optical lane and the principal housing, four film elevations and five contact rail elevations. Full optical fields, offset drop-offs outside the sensor tracks, adverse floor reflectivity, icing, connector strength and braking require restrained tests. Static CAD alone cannot establish unattended open-door safety. Use the project's operating and verification requirements.

From this directory, with Python 3.12 and CadQuery 2.7 available, run

    python source/build_concept.py --check
    python source/verify_geometry.py

The first command uses the bundled body reference at **../reference/revision_B/Rad_Roomba_Body_Concept_B.step**. Specify **--base /path/to/body.step** if the reference has moved. **source/body_shell.py** and **source/body_chassis.py** retain editable geometry for the rounded platform. To regenerate it from source, use

    python source/build_concept.py --rebuild-body --check
    python source/verify_geometry.py

Modify the head in **source/build_concept.py**. The 5 mm trial projection is an alternative geometry selectable via **BUMPER_PROJECTION**. Confirm ray and interface clearance after changing the model. **previous_C/** contains the preceding head and assembly with the superseded floor gap and its drawings, for comparison with the reviewed concept only.

## Rendered views

Open **renders/Rad_Roomba_Rev_D_Assembly.png** for the assembled Rev D robot and **renders/Rad_Roomba_Rev_D_Detector_Head.png** for the four window and guard arrangement. The editable STEP files and three-sheet drawing above provide dimensions. Future control-panel cutouts, the battery drawer and any additional personnel-protection hardware depend on component selection.
