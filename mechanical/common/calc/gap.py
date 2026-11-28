"""Gap error budget at the four outer window corners and rail-touch limits for the 3 mm and 5 mm rails (calculated).

Quasi-static three-point kinematics: the chassis plane goes through the two wheel contacts (0, +-T/2) and the caster
contact (-L, 0).  gap(x, y) = film_z + plane(x, y) - floor(x, y) - deflection.
"""
from __future__ import annotations

from .. import params as P
from ..purchased import library as L
from . import f, inputs_table, table

T = P.TRACK
LC = -(P.CASTER_SWIVEL[0] - L.env("caster")["offset"])     # caster contact behind the axle, forward travel
YC = P.SEG_Y[0] + P.ACTIVE_Y / 2
XF, XR = P.ROW_X + P.ACTIVE_X / 2, P.ROW_X - P.ACTIVE_X / 2
CORNERS = {"front-left": (XF, YC), "front-right": (XF, -YC), "rear-left": (XR, YC), "rear-right": (XR, -YC)}
XRAIL, XWING = 263.2 + P.HEAD_DX, 142.3 + P.HEAD_DX     # Rev D rail centre lines, shifted with the head
RAIL_PTS = {"leading rail corner L": (XRAIL, 175.0), "leading rail corner R": (XRAIL, -175.0), "leading rail centre": (XRAIL, 0.0),
            "wing return L": (XWING, 174.0), "wing return R": (XWING, -174.0)}


def sensitivities(row_x, lc=None, track=None):
    """Gap change per mm of (caster rise, single wheel drop) at the row centre, front outer corner and leading rail corner."""
    lc, track = lc or LC, track or T
    pts = {"row centre": (row_x, 0.0), "front outer corner": (row_x + P.ACTIVE_X / 2, YC), "rail corner": (row_x + 59.2, 175.0)}
    return {k: {"caster": x / lc, "wheel": 0.5 * (1 + x / lc) + y / track} for k, (x, y) in pts.items()}
STATIC = [   # (term, +- mm at the outer corners, basis)
    ("Tyre radius / compression / wear", 0.5, "assumed +-0.5 mm on a 52 mm solid tyre; calibrate loaded"),
    ("Caster height tolerance x 254/L", 0.3 * XF / LC, "assumed +-0.3 mm caster height"),
    ("Receiver seating and play (front corner)", 0.25, "section 4, prototype assumption"),
    ("Head frame flatness and film plane", 0.3, "assumed print/machining tolerance over 350 mm"),
    ("Static cantilever deflection (self weight)", 0.1, "section 4"),
]
from .receiver_break import tolerance_stack as _rx_tol    # noqa: E402  (body-side datum-C term, IB-64)
_RX = _rx_tol()
STATIC.append(("Body-side datum-C height: plate -> land pins, incl. the G10 break (front corner)", _RX["after"]["corner_worst"], "section 9 (was +-%.2f before the break)" % _RX["before"]["corner_worst"]))


def plane(hl, hr, hc):
    a = (hl + hr) / 2
    return lambda x, y: a + (a - hc) / LC * x + (hl - hr) / T * y


def cases(s):
    """Floor features of size s (mm). Each returns (description, plane heights hL, hR, hC, floor height under the head)."""
    return {
        "step up: head over the step, base still below": (0, 0, 0, s),
        "step up: wheels up, caster still below": (s, s, 0, s),
        "step down: head over the drop, base still above": (0, 0, 0, -s),
        "step down: wheels down, caster still above": (-s, -s, 0, -s),
        "left wheel on a bump / debris": (s, 0, 0, 0),
        "left wheel in a dip": (-s, 0, 0, 0),
        "caster on a bump": (0, 0, s, 0),
        "caster in a dip": (0, 0, -s, 0),
    }


def run():
    md, key = [], {}
    md.append("## 6. Gap error budget at the four outer window corners\n")
    md.append(inputs_table([("Film gap nominal", P.FILM_Z, "mm", "contract"), ("Rail projections", str(P.RAIL_PROJECTIONS), "mm", "contract -> 7 / 5 mm rail clearance"),
                            ("Track T", T, "mm", "params (CCR-01)"), ("Caster contact behind axle L", LC, "mm", "params (CCR-02) + caster offset"),
                            ("Outer window corners", f"x {XR:.0f} / {XF:.0f}, y +-{YC}", "mm", "contract optics"), ("Leading rail centreline x", f(XRAIL), "mm", "Rev D model shifted by HEAD_DX")]))
    md.append("\nSensitivities (mm of gap change per mm of contact height change; calculated from the three-point plane):\n")
    rows = []
    for n, (x, y) in {**CORNERS, "row centre": (P.ROW_X, 0.0), **RAIL_PTS}.items():
        rows.append((n, f(plane(1, 0, 0)(x, y), 3), f(plane(0, 1, 0)(x, y), 3), f(plane(0, 0, 1)(x, y), 3)))
    md.append(table(["Point", "left wheel +1", "right wheel +1", "caster +1"], rows))
    md.append(f"\nPitch arm: 1 mm at the caster moves the row centre by {P.ROW_X / LC:.2f} mm (Rev D: row 204, caster -116: {204 / 116:.2f} mm). "
              f"Roll: 1 mm at one wheel moves the outer corners by +-{YC / T:.2f} mm (Rev D track 220: +-{YC / 220:.2f}).\n")
    md.append("### Static (always present) terms\n")
    md.append(table(["Term", "+- mm at an outer corner", "Basis"], [(a, f(b, 2), c) for a, b, c in STATIC]))
    worst = sum(b for _, b, _ in STATIC)
    rss = sum(b * b for _, b, _ in STATIC) ** 0.5
    md.append(f"\nStatic band at an outer corner: +-{worst:.2f} mm worst case, +-{rss:.2f} mm RSS.\n")
    w0 = worst - _RX["after"]["corner_worst"] + _RX["before"]["corner_worst"]
    r0 = (rss ** 2 - _RX["after"]["corner_worst"] ** 2 + _RX["before"]["corner_worst"] ** 2) ** 0.5
    md.append(f"Body-side datum-C row before / after the receiver thermal break: +-{_RX['before']['corner_worst']:.2f} / +-{_RX['after']['corner_worst']:.2f} mm; "
              f"static band with the pre-break value +-{w0:.2f} worst / +-{r0:.2f} RSS (the row was not carried before IB-64).\n")
    key.update(static_worst=worst, static_rss=rss, static_worst_prebreak=w0, rx_body_before=_RX["before"]["corner_worst"], rx_body_after=_RX["after"]["corner_worst"])
    md.append("### Floor features (quasi-static, one feature at a time)\n")
    sizes = (1.5, 3.0, 5.0)
    rows = []
    for s in sizes:
        for name, (hl, hr, hc, hf) in cases(s).items():
            p = plane(hl, hr, hc)
            gaps = [P.FILM_Z + p(x, y) - hf for x, y in CORNERS.values()]
            rail = min(p(x, y) - hf for x, y in RAIL_PTS.values())
            rows.append((s, name, f(min(gaps), 1), f(max(gaps), 1), f(7 + rail, 1), f(5 + rail, 1),
                         "TOUCH" if 7 + rail <= 0 else "clear", "TOUCH" if 5 + rail <= 0 else "clear"))
    md.append(table(["Feature (mm)", "Situation", "Min corner gap", "Max corner gap", "3 mm rail clearance left", "5 mm rail clearance left", "3 mm rail", "5 mm rail"], rows))
    # limits
    lim = []
    for name, (hl, hr, hc, hf) in cases(1.0).items():
        p = plane(hl, hr, hc)
        k = min(p(x, y) - hf for x, y in RAIL_PTS.values())     # mm of rail clearance lost per mm of feature (negative)
        if k < 0:
            lim.append((name, f(-k, 2), f(7 / -k, 1), f(5 / -k, 1), f((7 - worst) / -k, 1), f((5 - worst) / -k, 1)))
    md.append("\n### When does the rail touch?\n")
    md.append(table(["Situation", "Rail clearance lost per mm of feature", "3 mm rail touches at (mm)", "5 mm rail touches at (mm)", "... with the static worst case used up: 3 mm rail", "5 mm rail"], lim))
    kmax = max(float(r[1]) for r in lim)
    key.update(touch_3mm=7 / kmax, touch_5mm=5 / kmax, touch_3mm_static=(7 - worst) / kmax, touch_5mm_static=(5 - worst) / kmax, static_wc=worst, static_rss=rss)
    # band for representative floor
    rep = 2.0
    lo = hi = 0.0
    for name, (hl, hr, hc, hf) in cases(rep).items():
        p = plane(hl, hr, hc)
        g = [p(x, y) - hf for x, y in CORNERS.values()]
        lo, hi = min(lo, min(g)), max(hi, max(g))
    key.update(band_lo=P.FILM_Z + lo - worst, band_hi=P.FILM_Z + hi + worst, rep_feature=rep)
    md.append(f"\n**Gap band (calculated).** For a floor whose single features stay within {rep:.0f} mm (seam step, debris under one wheel, cross-member dishing over the wheelbase) the film gap at the outer corners stays within "
              f"**{P.FILM_Z + lo - worst:.1f} .. {P.FILM_Z + hi + worst:.1f} mm** including the static worst case ({P.FILM_Z + lo:.1f} .. {P.FILM_Z + hi:.1f} mm without it). "
              f"The most sensitive situation is one drive wheel dropping while the same-side front corner leads ({kmax:.2f} mm per mm). "
              f"The 3 mm rail (7 mm clearance) touches at a {7 / kmax:.1f} mm single feature ({(7 - worst) / kmax:.1f} mm with the static band used up); the 5 mm rail (5 mm clearance) at {5 / kmax:.1f} mm ({(5 - worst) / kmax:.1f} mm). "
              "A rail touch opens HEAD_LOOP, so these are nuisance-stop thresholds as well as protection thresholds: on a 3 mm seam the 3 mm rail keeps about 3 mm of clearance, while the 5 mm rail keeps about 1 mm nominally and touches once the static band or an oblique crossing (one wheel first) is included. "
              "Floor crown is negligible (5 mm sag over a 2.4 m wide floor changes the corner gap by < 0.1 mm). Dynamic terms (braking pitch on 40 N/mm tyres < 0.05 mm, receiver bounce at 0.5 g < 0.1 mm) are small against the kinematic terms; they must be confirmed on the rig.")
    md.append("\nThe measurement method that replaces these assumptions with data is in `out/gap_measurement_method.md`.")
    return "\n".join(md), key


METHOD = """# Gap measurement method for uneven floors (VT-032, RQ-018, RQ-047, RQ-048)

Status: proposed procedure, nothing measured yet. Numbers in brackets come from `out/mech_calcs.md` (calculated).

## 1. What is measured

| Quantity | Symbol | Where (base_link mm) | Why |
|---|---|---|---|
| Film-plane to floor gap | g1..g4 | outer window corners ({xf:.0f}, +-{yc}) and ({xr:.0f}, +-{yc}) | the four points that bound pitch, roll and wing deflection |
| Film-plane to floor gap | g0 | row centre ({rowx:.0f}, 0) | heave reference, separates wing deflection from roll |
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
compare with the sensitivity table (calculated {sens:.2f} mm per mm worst corner). A deviation above 0.3 mm means
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
| Static loaded gap, each corner | 10.0 +- 0.5 mm | static term budget (+-{wc:.2f} mm worst case calculated) |
| Static corner-to-corner spread | <= 0.6 mm | head flatness + roll set-up |
| 20 N corner deflection | <= 1.0 mm, returns within 0.1 mm | receiver stiffness target |
| Head refit repeatability | <= 0.2 mm at any corner | RQ-015 |
| Dynamic gap on the approved floor envelope | within the calibrated interval; proposal 7.0 .. 13.0 mm | calculated band {lo:.1f} .. {hi:.1f} mm for 2 mm features |
| Rail clearance, 3 mm insert | never below 1.0 mm on approved features, no HEAD_LOOP trip | nuisance stops |
| Rail clearance, 5 mm insert | report trips per feature; expected to touch at about {t5:.1f} mm features | calculated |

Samples whose gap leaves the calibrated interval are flagged and the host withholds that coverage (RQ-047). If the
3 mm seam cannot be passed inside the interval, the options in order are: restrict the floor envelope, stiffen the
receiver, move the caster further back, lower the speed.
"""


def method(key):
    return METHOD.format(xf=XF, xr=XR, yc=YC, rowx=P.ROW_X, sens=max(abs(plane(1, 0, 0)(x, y)) for x, y in CORNERS.values()),
                         wc=key["static_wc"], lo=key["band_lo"], hi=key["band_hi"], t5=key["touch_5mm"])
