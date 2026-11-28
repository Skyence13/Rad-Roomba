# Gap measurement method for uneven floors (VT-032, RQ-018, RQ-047, RQ-048)

Status: proposed procedure, nothing measured yet. Numbers in brackets come from `out/mech_calcs.md` (calculated).

## 1. What is measured

| Quantity | Symbol | Where (base_link mm) | Why |
|---|---|---|---|
| Film-plane to floor gap | g1..g4 | outer window corners (181, +-171.25) and (81, +-171.25) | the four points that bound pitch, roll and wing deflection |
| Film-plane to floor gap | g0 | row centre (131, 0) | heave reference, separates wing deflection from roll |
| Head relative to chassis | r1, r2 | head cover top at (150, +-150) against a chassis-fixed arm | receiver compliance and play, independent of the floor |
| Rail clearance | c1..c3 | leading rail at y = 0, +-170 | direct check of the 7 mm / 5 mm clearance, both rail inserts |
| Chassis pitch and roll | theta, phi | IMU on RR-CHS-MAIN | cross-check of g against the three-point model |

## 2. Equipment

1. **Instrumented dummy head** (the BOM W34 dummy with matched mass and CG). It carries five gap followers in the window
   positions: spring-loaded ball-tip plungers (3 mm PTFE ball, < 0.3 N preload, 12 mm stroke) on linear potentiometers or
   LVDTs, 0.02 mm resolution, 4..16 mm range, sampled at >= 200 Hz by a logger that also records the chassis odometry
   and IMU stream (same clock as the head link). The plunger tip is set flush with the film plane on a surface plate
   with the 10.00 mm setting block, so a reading is the gap directly. Contact followers are chosen over optical sensors
   because wood, steel, frost and wet film change the optical return but not a ball tip.
2. **Two relative-motion followers** r1, r2 of the same type on a rigid arm bolted to the chassis grip yokes.
3. **Setting and check gauges**: 10.00 mm setting block; stepped go/no-go wedge 4..16 mm in 0.5 mm steps (machined
   aluminium, traceable micrometer check) for manual static readings at the corners and under the rails; 1.5 / 3 / 5 mm
   ground shims.
4. **Guarded floor rig** (BOM W36/E14): a 1.2 x 2.4 m panel of the real trailer floor material on a flat frame with
   interchangeable features: seam steps 1.5 / 3 / 5 mm up and down across the full width, a 40 mm wide cleat 4 mm high,
   a 2 mm debris shim for one wheel track, a 300 mm pitch cross-member dish of 2 mm, a threshold plate. Edge guards and
   a fall restraint independent of the robot.
5. Thermocouples on tyre, caster, receiver and head; cold chamber or controlled outdoor exposure for the cold runs.

## 3. Procedure

**A. Static, level plate (every configuration: each approved pack x each approved head, both rail inserts).**
1. Weigh the three contacts (three scales, level within 0.2 mm) -> record wheel and caster reactions and x_CG.
2. On the surface plate read g0..g4 with the followers and independently with the wedge gauge; read c1..c3.
3. Apply 20 N downward at each front outer corner and at the row centre; record the deflection and the return to zero
   (hysteresis = play). Calculated expectation: see `mech_calcs.md` section 4.
4. Repeat steps 2-3 after three head remove/refit cycles (repeatability of the indexed mount).

**B. Quasi-static features.** Place each wheel and the caster in turn on the 1.5 and 3 mm shims; record g0..g4 and
compare with the sensitivity table (calculated 1.58 mm per mm worst corner). A deviation above 0.3 mm means
compliance or play not in the model.

**C. Dynamic passes** on the floor rig at 0.05, 0.10 and 0.20 m/s, forward and reverse, straight and during a pivot turn,
over every feature, three passes each: log g0..g4, r1, r2, IMU, odometry, HEAD_LOOP state. Include a commanded stop,
a protective stop and a power-loss stop on the flat panel and on the 3 mm seam.

**D. Cold repeat** of A.2-A.3 and of C at survey speed, at -20 C after 30 min exposure (tyre and receiver stiffness,
caster swivel drag), and once at -25 C.

## 4. Reduction

For every pass: minimum, maximum and 0.5 / 99.5 percentile of each g; the same for c; position along the pass where
the extreme occurred; head-to-chassis motion r; whether HEAD_LOOP opened. Present per feature and speed. The gap band of
a configuration is the union over all approved features and speeds.

## 5. Acceptance (proposed, to be confirmed by radiometry and the lead)

| Item | Proposed limit | Basis |
|---|---|---|
| Static loaded gap, each corner | 10.0 +- 0.5 mm | static term budget (+-1.58 mm worst case calculated) |
| Static corner-to-corner spread | <= 0.6 mm | head flatness + roll set-up |
| 20 N corner deflection | <= 1.0 mm, returns within 0.1 mm | receiver stiffness target |
| Head refit repeatability | <= 0.2 mm at any corner | RQ-015 |
| Dynamic gap on the approved floor envelope | within the calibrated interval; proposal 7.0 .. 13.0 mm | calculated band 5.3 .. 14.7 mm for 2 mm features |
| Rail clearance, 3 mm insert | never below 1.0 mm on approved features, no HEAD_LOOP trip | nuisance stops |
| Rail clearance, 5 mm insert | report trips per feature; expected to touch at about 3.1 mm features | calculated |

Samples whose gap leaves the calibrated interval are flagged and the host withholds that coverage (RQ-047). If the
3 mm seam cannot be passed inside the interval, the options in order are: restrict the floor envelope, stiffen the
receiver, move the caster further back, lower the speed.
