"""Detector-head parameters (mm, base_link frame). Every shared datum is IMPORTED from mechanical.common.params;
everything defined here is a head-internal design value (calculated / tool-checked by checks.py, nothing measured).

Naming: X = along travel (+x forward), Y = across (+y left), Z = up. S0 is the left outer lane.
"""
from __future__ import annotations

from mechanical.common import params as P

# ----------------------------------------------------------------------------- imported datums (never retyped)
ROW_X = P.ROW_X
SEG_Y = P.SEG_Y
PITCH = P.SEG_PITCH
ACT_X, ACT_Y = P.ACTIVE_X, P.ACTIVE_Y
FILM_Z = P.FILM_Z
XR, XF = P.HEAD_FRAME_X                      # frame rear / front face 70.2 / 188.2
Z_SPR0, Z_SPR1 = P.HEAD_STACK[1][1], P.HEAD_STACK[1][2]      # spreader 30..32
Z_LID0, Z_LID1 = P.HEAD_STACK[-1][1], P.HEAD_STACK[-1][2]    # lid 43..45
Z_REF_TOP = P.HEAD_REF_GUIDE_TOP_Z           # 28.5
RC = P.RECEIVER
ACQ = P.HEAD_ACQ
ENV = P.HEAD_ENV_E
ENV_CEIL = P.HEAD_ENV_E_CEILING
PORT = P.HEAD_PIGTAIL_EXIT
WIN_X0, WIN_X1 = ROW_X - ACT_X / 2, ROW_X + ACT_X / 2        # 81.2 .. 181.2

# ----------------------------------------------------------------------------- frame (tray) -- head design values
YW = 173.25            # frame outer half width (Rev D 172.5: +0.75 for the 0.5 mm module edge allowance; envelope 175)
Z_FB = 10.5            # frame underside (cassette gasket plane); film underside is FILM_Z = 10.0
Z_SEAT = 11.0          # module seat shoulder (floor screen underside, Rev D value)
EDGE = 0.5             # lane cavity allowance per side beyond the 80 x 100 window (module border / wrap)
CAV_X0, CAV_X1 = WIN_X0 - EDGE, WIN_X1 + EDGE                # 80.7 .. 181.7
CAV_HY = ACT_Y / 2 + EDGE                                    # 40.5
RIB_W = PITCH - ACT_Y - 2 * EDGE                             # 6.5 above the seat (7.5 below)
SIDE_WALL = YW - (SEG_Y[0] + CAV_HY)                         # 1.5
Z_WALL_TOP = 42.2      # gasket land of the upper wall (lid underside 43.0, gasket 1.2 -> 0.8)
BAY_X0, BAY_X1 = 72.8, 185.6      # inner faces of the upper walls (2.6 mm walls front and rear)
BAY_HY = 169.9
RIB_TOP_Z = 29.4       # rib top between the hard screw pads: 1.0 mm black gasket strip compressed to 0.6
LIP_GROOVE = (Z_SPR0, Z_SPR1 + 0.15, BAY_X1, BAY_X1 + 1.0)   # undercut in the front wall that holds the spreader front edge
CHIM_HY = 9.0          # chimney half width at each lane centre
CHIM_X0 = BAY_X0       # chimney rear face flush with the bay rear face
CHIM_STEP_X, CHIM_FLOOR_REAR, CHIM_FLOOR_FRONT = 76.0, 13.0, Z_SEAT
JOINT_Y = 0.0          # prototype split plane (centre of the 7.5 mm S1|S2 seam rib)
TONGUE_T, TONGUE_H = 1.2, 1.6     # tongue thickness (x or z) and projection across the joint (y)
LAP_T, LAP_H = 1.0, 2.0            # ship-lap of the upper walls across the joint (outer 1.0 mm, 2.0 mm overlap)
DOWEL_D = 4.0
ROD_PAD_X = (96.0, 116.0, 136.0, 156.0, 176.0)   # spreader screw stations on the y = +-87.5 ribs (hard pads, M2.5 inserts)
REAR_SCREW_X = 76.8
REAR_SCREW_Y = (8.0, 22.0, 153.0)                # spreader screws into the printed rear zone (each side), also comb-foot bond points
THEAD_SCREW_DY = (-24.0, -10.0, 10.0, 24.0)       # M3 low-head through the spreader tab into the aluminium T-head (about y = +-87.5)
THEAD_SCREW_X = 76.5   # (was M4 at 75.8: the 7 mm head overlapped the rear wall and the EMI comb; tool-checked with modelled heads)

# receiver shoe + T-head (aluminium, both builds)
SHOE_Y = RC["shoe_y"]
SHOE_W = RC["shoe_width"]
SHOE_Z0, SHOE_Z1 = RC["shoe_z"]
SHOE_X0 = RC["shoe_x"][0]
XSTOP = RC["x_stop"]                # 65.7 datum A
THEAD_HY = 30.0                     # T-head half length in y (between the chimneys of the two adjacent lanes)
THEAD_X1 = 78.7                     # T-head front face (pocket depth 8.5; 2.0 mm web to the cavities)
SHOULDER_HY = 20.0                  # x-stop shoulder boss half width about the shoe

# spreader plate (detail of the lead's nominal 82.2..184.7 x +-168.5 rectangle)
SPR_X0, SPR_X1 = 73.5, BAY_X1 + 0.8      # rear comb edge / front edge tucked 0.8 mm under the lip
SPR_HY = 169.6
SPR_NOTCH_X = P.HEAD_SPREADER_X[0]       # 82.2: bottom of the four pigtail notches (lead's rear edge)
STANDOFF_BOARD_H = 2.5
# Lid (cover) fastening: the cover is a shear panel screwed at <= 40 mm pitch round a closed loop (requirement). Rear line: M3 standoffs on the
# spreader (the 2.6 mm rear wall cannot take an insert and the rear strip is full); front and side lines: hard bosses on the wall inner faces
# (prototype: M3 heat-set inserts; production: tapped M3), inside the gasket loop, top = lid seat z 43.0.
LID_STANDOFFS = [(183.0, 42.0), (183.0, 130.0), (77.5, 0.0), (77.5, 31.5), (77.5, 57.0), (77.5, 70.5), (77.5, 104.5), (77.5, 144.5), (ROW_X, 166.9)]
LID_STANDOFF_D = 4.5   # +- y -> 17 off; prototype: M3 x 10.5 where it stands on (and clamps) a 0.5 mm EMI fence foot, M3 x 11 in the chimney zones; production M3 x 11
LID_BOSS_FRONT_X = 184.2                         # front bosses (centre x), lid hole edge = gasket inner edge 185.9
LID_BOSS_FRONT_Y = (6.0, 35.0, 70.5, 104.5, 137.0, 168.4)   # +- y (none on the y = 0 split); 168.4 = front corner boss
LID_BOSS_SIDE_Y = 168.4                          # side bosses (centre |y|), lid hole edge 170.1 < gasket inner edge 170.2
LID_BOSS_SIDE_X = (106.0, 140.0, 174.0)
LID_BOSS_R, LID_BOSS_Z0 = 3.3, 34.0             # boss radius, underside (above the fence feet and their screw heads)
INSERT_M3 = {"hole_d": 4.0, "depth": 6.0}       # heat-set M3 x 5.7 class (hole dia per insert maker, UNVERIFIED)
LID_PITCH_MAX = 40.0
FENCE_T = 0.5

# lid
LID_T = Z_LID1 - Z_LID0
LID_INSET = 0.3

# optics (Rev D stack, z from cad/source/build_concept.py with STACK_LIFT = 4)
STACK = {"floor_screen": (11.0, 11.25), "floor_guide": (11.25, 16.25), "barrier": (18.0, 20.0),
         "ref_tile": (23.0, 23.5), "ref_guide": (23.5, 28.5)}
PAD_T, HEATER_T = 1.2, 0.3
CARRIER = {"x": (78.6, 80.1), "hy": 6.5, "h": 5.0}     # SiPM carrier 13 x 5 x 1.5 at the rear guide edge (Rev D, shifted)
SIPM = {"x": (80.1, 81.2), "hy": 3.5, "h": 4.3}

# window cassette
CAS_Z0 = 8.0
CAS_X0, CAS_X1 = WIN_X0 - 6.8, WIN_X1 + 6.8     # 74.4 .. 188.0 (symmetric about the window so one part fits all four lanes)
CAS_HY = ACT_Y / 2 + 2.0             # 2.0 mm long-side border: flush with the outer wall on S0 / S3, 3.5 mm channel under each seam rib
CAS_WEB_X = (-30.0, 0.0, 30.0)
CAS_WEB_W, CAS_WEB_T = 0.8, 0.8
CAS_LIP_Y = (1.05, 1.95, 0.85)     # start, end beyond the aperture edge; height above the cassette top (y sides)
CAS_LIP_X = (5.9, 6.7, 1.3)        # same for the front and rear borders
CAS_SCREW = [(-3.4, 30.0), (-3.4, -30.0), (3.1, 30.0), (3.1, -30.0)]   # offsets (beyond window rear/front edge, about lane centre)
FOOT_NOTCH = 7.0                    # cassette corner notch at y = 0 front: exposes the frame foot pad for the bench cradle
FOOT_XY = (185.9, 0.0)

# leading rail (front zone)
RAIL_GAP = 17.0        # rail bar rear face to frame front face at rest = total stroke to the positive stop
RAIL_TRIP_MAX = 2.0    # required pre-travel to trip
BAR_T, BAR_Z0, BAR_Z1 = 3.0, 8.0, 22.0
BAR_HY = 175.0
INS_T, INS_H = 4.0, 16.0
INS_HOLE_OFFSETS = {3.0: 7.0, 5.0: 9.0}    # projection below film -> distance of the screw row above the insert bottom edge
INS_SCREW_Z = 14.0
ROD_D, ROD_Y, ROD_Z = 4.0, SHOE_Y, 14.0
ROD_ENGAGE, ROD_BORE_DEPTH = 25.0, 52.0
SPRING = {"free": 32.0, "rate": 0.30, "od": 3.6, "solid": 8.5}     # guide-rod return spring (N/mm), UNVERIFIED catalogue item
PIN_X, PIN_D = 182.6, 2.5
CAM_RISE, CAM_RAMP = 1.3, 1.6      # rod notch depth and ramp length (39 deg)
BAIL_D, BAIL_X, BAIL_Z, BAIL_L, BAIL_Y = 2.5, 189.7, 29.0, 16.5, 160.0
BAIL_BLOCK_Y = (0.0, 130.0, -130.0)

# side zones
SIDE_T = 0.8
SIDE_Y0 = 175.0 - SIDE_T            # inner face of the side strip
SIDE_GAP = SIDE_Y0 - YW             # 0.95 mm travel to the positive stop (side wall)
RET_X1 = XR - 1.65                  # front face of the wing return plate (gap to the frame rear face)
RET_Y0 = 110.0
SIDE_Z0, SIDE_Z1 = 7.0, 20.0     # SIDE_Z0 is the 3 mm-projection strip; the 5 mm strip (RR-HD-S-433/434) uses FILM_Z - 5
SLIT_Z = (24.7, 26.1)
GUIDE_PINS = [(75.0, 168.5), (75.0, 145.7), (185.4, 168.3)]   # vertical guide pins (M3 shanks) in 45 deg slots
SW_SIDE = {"x": XR, "y": 156.75, "z": 20.75}                  # side switch pocket centre (plunger toward -x)

# switch (Omron D2HW-C201M, PARTIAL data: see purchased_and_fabricated.csv)
SW = {"l": 13.3, "t": 5.3, "h": 7.0, "plunger": 1.5, "pt_max": 1.0, "ot_min": 1.1, "md": 0.25, "of_max_n": 0.75}

# ports, vent
PORT_SLOT_HY, PORT_SLOT_Z0 = 5.5, 33.5
CABLE_D = {"J1": 7.5, "J2": 6.5}
VENT = (XR, -65.0, 37.5)
DRAIN = {"dy": 6.5, "x_in": 75.0, "x_out": 71.0, "d": 1.2, "z_ch": (11.5, 12.3)}   # light-trap drain per chimney: up-across-up, 3 turns
LID_SW = (183.0, -SHOE_Y)           # lid interlock switch on the front strip (x, y): mirror position of the front rail switch

# keeper
KEEPER = RC["latch_keeper"]         # (104, 0, 45)
BRIDGE_T = 3.0
BRIDGE_HY = 67.5

MATERIAL_DENSITY = {  # g/cm3
    "PA-CF": P.MATERIALS["PA-CF"]["rho"], "PETG-CF": P.MATERIALS["PETG-CF"]["rho"], "ASA": P.MATERIALS["ASA"]["rho"],
    "AL6061": P.MATERIALS["AL6061"]["rho"], "AL5052": 2.68, "PA12-MJF": P.MATERIALS["PA12-MJF"]["rho"], "PMMA": 1.19, "FR4": 1.85,
    "SS304": 7.93, "SS301": 7.93, "STEEL": 7.85, "POM": 1.41, "TPU": 1.21, "SIL-FOAM": 0.25, "EPDM-FOAM": 0.15, "PVT": 1.03,
    "COPPER": 8.9, "PI": 1.42, "PET": 1.39, "BRASS": 8.5, "MIXED": 1.0,
}


def lane_y(i):
    return SEG_Y[i]


def rail_underside(projection):
    return FILM_Z - projection
