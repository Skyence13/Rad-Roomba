"""RR-X prototype-specific parameters. Everything that is an interface is IMPORTED from mechanical.common.params (P);
only prototype design values (wall, fits, fastener sizes, split stations) are defined here.  Units mm, base_link."""
from __future__ import annotations

from mechanical.common import params as P

HEAD_X1 = max(P.HEAD_ENV_E["x"][1], float(P.C["frames"]["head_envelope_rev_e_mm"]["x"][1]))   # 212.5: sprung leading rail (contract draft6)
BED = (256.0, 256.0, 250.0)          # stock X1C: 256 x 256 plate, 250 mm printable height in the stock preset
BED_MARGIN = 3.0

# ---- materials used in this build (density g/cm3, effective printed fill of the envelope volume)
MAT = {
    "ASA": {"rho": 1.07, "fill": 0.72, "color": "#d5d9db", "profile": "Bambu ASA @BBL X1C 0.4 nozzle"},
    "PAHT-CF": {"rho": 1.06, "fill": 0.85, "color": "#2c3034", "profile": "Bambu PAHT-CF @BBL X1C"},
    "TPU95A": {"rho": 1.22, "fill": 0.80, "color": "#17191b", "profile": "Bambu TPU 95A HF @BBL X1C"},
    "AL6061": {"rho": 2.70, "fill": 1.0, "color": "#b9bdc1"},
    "AL5052": {"rho": 2.68, "fill": 1.0, "color": "#b9bdc1"},
    "SS304": {"rho": 7.9, "fill": 1.0, "color": "#8f959a"},
    "STEEL": {"rho": 7.85, "fill": 1.0, "color": "#70767b"},
    "PMMA": {"rho": 1.19, "fill": 1.0, "color": "#3b1d1d"},
    "FOAM": {"rho": 0.06, "fill": 1.0, "color": "#e9e2c8"},
    "SIL": {"rho": 0.35, "fill": 1.0, "color": "#c7533f"},
}

# ---- heat-set inserts (brass, knurled, for 3D-printed parts; hole = pilot diameter x depth) -- generic, UNVERIFIED brand
INSERT = {"M2": (3.2, 4.0), "M2.5": (3.8, 5.0), "M3": (4.0, 5.7), "M4": (5.6, 8.1), "M5": (6.4, 9.5)}
CLEAR = {"M2": 2.4, "M2.5": 2.9, "M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 8.5}
TAP = {"M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0}
CSK = {"M3": 6.3, "M4": 8.4, "M5": 10.4}     # 90 deg countersink major diameter

# ---- chassis plate (fabricated, 4 mm 6061-T6, laser/waterjet + countersink/tap)
PLATE_Z = P.CHASSIS_PLATE_Z                    # (33, 37)
PLATE_INSET = 3.0                              # from the lower inner skin row (same law as layout.plate_outline)
BEAM_X = (-26.0, P.RECEIVER["front_beam"][1])  # front beam extended aft to carry the motor pods (deviation D-01)
BEAM_HALF_Y = P.DRIVE_POD["end_y"]             # 119.5: horns widened to carry the cliff pods / deflectors (deviation D-01)
BAY_WINDOW = (-166.0, -78.0, 38.0)             # x0, x1, half_y of the insulated window under the heater pad
CASTER_HOLE_R = 24.0

# ---- receiver (datum for the head) -- all positions from P.RECEIVER
RC = P.RECEIVER
RX_SLOT_CLEAR = RC["channel_clear"]            # 0.5 each side / above away from the lands
RX_FIT_Y_LEFT = 0.05                           # per side at the two land stations of the fitted (left) channel
RX_FLOAT_Y_RIGHT = 0.30                        # per side, right channel
RX_FIT_Z = 0.06                                # total: dowel land to roof pad = shoe height + 0.06 (+0.04/-0.02)
RX_LAND_PIN_D = 4.0                            # hardened dowel pins ISO 8734 4 m6 x 24 as replaceable z lands
RX_STATION_LEN = 8.0
RX_FLANGE_X = (59.7, RC["x_stop"])             # x-stop flange (pads 16 x 14 each side of the shoe) ends at datum A
RX_PAD = (16.0, 14.0)

# ---- motor pod (printed PAHT-CF, carries the gearmotor; shaft eccentricity: can centre 7 mm above the axle)
POD_BORE_R = 19.0                              # 37 mm can + 0.5 radial
POD_Y0 = 98.5                                  # inboard end of the tube (clear of the grip side plates)
POD_FACE_T = 2.5
MOTOR_BCD = 31.0                               # UNVERIFIED (Pololu 37D drawing): 6 x M3 on 31 mm about the can axis

# ---- bridge / board
TRAY_T = 2.0
POSTS = [(-64.0, 76.0), (-64.0, -76.0), (30.0, 45.0), (30.0, -45.0)]

# ---- grip frame (fabricated): two 6 mm 6061 side plates, 14 mm solid 6061 bar with M6 tapped ends, 25 x 25 x 3 angle feet
GRIP_PLATE_Y = (88.0, 94.0)                    # inside the cheek envelope 84..98
GRIP_BAR_D = 14.0                              # solid round bar (was a 16 x 2 tube on an M8 rod: it collided with the look-ahead ToF seats)
GRIP_BAR_X = -15.0                             # bar axis x: front of the bar x -8.0 stays behind the look-ahead ToF clips
GRIP_BAR_Z = (P.GRIP["bar_bottom_z"] + P.GRIP["bar_top_z"]) / 2
GRIP_BAR_SCREW = "M6"
GRIP_PLATE_FRONT_X = -8.0                      # cheek front edge of the side plate (z >= 150)
GRIP_DESIGN_MASS = 9.0                         # kg (task: 3 x the 9 kg robot)
GRIP_FACTOR = 3.0
FOOT_X = (-56.0, -22.0)

# ---- shells
SPLIT_Z_LOWER_TOP = P.BODY_ROWS["lower_outer"][-1][0]    # 61.9: top land of the lower hull
SPLIT_Z_UPPER_BOT = P.BODY_SPLIT_Z                        # 63.68: bottom land of the lid; 1.78 mm gasket between
X_NOSE = P.SADDLE["x"][1]                      # 47: nose cowl / shoulder split
X_DECK = -45.0                                 # shoulder / rear deck split (ahead of RR-PANEL and its light pipes, behind the grip slots)
X_LOWER = -71.0                                # lower hull front / rear split
WELL_WALL = 3.0
FLANGE_T = 4.0                                 # joint flange thickness each side
FLANGE_DEPTH = 9.0                             # inward depth of the bolted joint flanges
TONGUE = (0.3, 3.0, 9.0)                       # perimeter tongue: clearance, thickness, height above the lower land
HATCH_JAMB = (57.5, 60.5)

# ---- battery bay
B = P.BATTERY_BAY
TUNNEL_WALL_Y = (55.5, 58.0)
TUNNEL_X = (-230.0, B["cassette_x"][1])        # guide walls; front bulkhead ahead of the cassette
FLOOR_RIB_Y = 42.0
KEY_RIB_Y = 50.5                               # off-centre key (left side only): reversed cassette is blocked

# ---- wheels: printed hub on a purchased 6 mm clamping hub + printed TPU tyre
TYRE_T = 9.0

# ---- bumper
BUMPER_Z = (56.0, 76.0)
BUMPER_STROKE = 9.0
BUMPER_DIR = {"L": (0.819, -0.574, 0.0), "R": (0.819, 0.574, 0.0)}   # inward travel of the quarter segments

GASKET = {"perimeter": "closed-cell silicone foam strip 4 x 2.5 mm, -40 C", "cord": "silicone sponge cord 3 mm", "cover": "silicone foam strip 6 x 2 mm"}
