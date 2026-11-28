"""RR-CHS-MAIN placement, outline, net classes, zones and keep-outs (imported by board.py).

Frame: X = u (towards the robot's right), Y = v (forward), origin rear-left corner, top side up
(board_envelopes.yaml RR-CHS-MAIN, mapped 1:1).  All values mm.

Placement policy
  * explicit (PLACE): every connector, relay, inductor, electrolytic, power FET/shunt/TVS and IC.
    Edge connectors are aligned to the board edge from their real courtyard (edge_at()).
  * passives and small discretes: near= hint to the IC/connector pin they serve (auto_near()),
    bottom side where the envelope allows it (<= 3 mm, not in the THERMAL_TO_BRIDGE pad area).
  * the auto-arranger only fills in those passives; ICs it placed in an earlier iteration were
    frozen here as explicit coordinates.
"""
import re

# ----------------------------------------------------------------------------------- envelope
W, H = 160.0, 100.0
HOLES = {"H1": (4.0, 4.0), "H2": (80.0, 4.0), "H3": (156.0, 4.0), "H4": (4.0, 96.0), "H5": (80.0, 96.0), "H6": (156.0, 96.0)}
HOLE_KO = 7.0                                         # keep-out diameter, both sides
THERMAL = (50.0, 30.0, 110.0, 70.0)                   # bottom side: no parts (gap pad to the bridge tray)
FRONT_CORNERS = ((0.0, 88.0, 14.0, 100.0), (146.0, 88.0, 160.0, 100.0))   # top max 12 mm
IMU = (80.0, 67.0)
EDGE_GAP = 0.3                                        # courtyard to board edge for edge connectors

# courtyard bounding boxes of the edge-mounted footprints in the footprint frame (x right, y down),
# from the KiCad 9 stock library (measured with pcbnew; see README "Placement")
CY = {
    "MINIFIT_2x4": (-3.25, -14.45, 15.85, 7.89), "MINIFIT_2x5": (-3.25, -14.45, 20.05, 7.89),
    "MICROFIT_2x1": (-4.12, -9.46, 4.12, 4.29), "MICROFIT_2x2": (-4.12, -9.46, 7.12, 4.29),
    "MICROFIT_2x3": (-4.12, -9.46, 10.12, 4.29),
}


def edge_at(cy, edge, lo, gap=EDGE_GAP):
    """Origin (X, Y, rot) for a right-angle header whose mating side (footprint -y) faces *edge*,
    with the courtyard starting at coordinate *lo* along the edge (X for front/rear, Y for left/right)."""
    x0, y0, x1, y1 = cy
    if edge == "left":      # rot 90: board offset = (y, x)
        return (gap - y0, lo - x0, 90)
    if edge == "right":     # rot 270: board offset = (-y, -x)
        return (W - gap + y0, lo + x1, 270)
    if edge == "front":     # rot 0: board offset = (x, -y)
        return (lo - x0, H - gap + y0, 0)
    if edge == "rear":      # rot 180: board offset = (-x, y)
        return (lo + x1, gap - y0, 180)
    raise ValueError(edge)


def _e(cy, edge, lo, side="F"):
    x, y, r = edge_at(CY[cy], edge, lo)
    return (round(x, 3), round(y, 3), r, side)


# ----------------------------------------------------------------------------------- explicit placement
PLACE = {
    # ---- edge connectors (right-angle, mating face at the edge)
    "J_PWR": _e("MINIFIT_2x4", "right", 14.5),          # right edge rear, v 14.5..33.6 (allocation v 4..34; H3 keep-out below)
    "J_HTR": _e("MICROFIT_2x1", "rear", 141.5),         # rear edge, u 141.5..149.7 (outside the u 20..140 ban)
    "J_CM5": _e("MICROFIT_2x2", "left", 9.0),           # left edge rear, v 9..20.2
    "J_LIDAR": _e("MICROFIT_2x1", "left", 23.0),        # left edge rear, v 23..31.2
    "J_MOT_L": _e("MICROFIT_2x3", "left", 74.0),        # left edge front, v 74..88.2
    "J_MOT_R": _e("MICROFIT_2x3", "right", 74.0),       # right edge front, v 74..88.2
    "J_HEAD1": _e("MINIFIT_2x5", "front", 14.5),        # front edge, u 14.5..37.8 (allocation u 8..40; out of the 12 mm corner u < 14)
    "J_HEAD2": (132.5, 96.45, 180, "F"),                # front edge, u 125.2..139.8, GH side entry facing +v
    # ---- rear-left cluster: CLIK-Mate safety row (v 1.7..11.2), GH signal rows (v 11.9..18.6, 19.3..26.0)
    "J_MODE": (23.8, 6.2, 0, "F"), "J_BTN": (44.8, 6.2, 0, "F"), "J_BUMP_L": (61.8, 6.2, 0, "F"),
    # GH row ordered by cable length: the longest runs (REAR_C, REAR_L) sit nearest the corner exit
    "J_TOF9": (21.05, 15.2, 0, "F"), "J_TOF8": (34.55, 15.2, 0, "F"), "J_TOF2": (48.05, 15.2, 0, "F"), "J_PANEL": (64.05, 15.2, 0, "F"),
    "J_TOF5": (21.05, 22.6, 0, "F"), "J_USB_MCU": (33.9, 22.6, 0, "F"), "J_USB_HEAD": (46.1, 22.6, 0, "F"),
    "J_DBG": (57.8, 22.6, 0, "F"), "J_AUX": (68.15, 22.6, 0, "F"),
    # ---- rear-right cluster (IB-12 / IB-33): CLIK-Mate safety row, GH signal rows
    "J_ESTOP": (91.8, 6.2, 0, "F"), "J_HANDS": (107.8, 6.2, 0, "F"), "J_COVER": (122.8, 6.2, 0, "F"), "J_BUMP_R": (134.8, 6.2, 0, "F"),
    "J_NTC": (89.8, 15.2, 0, "F"), "J_PAUSE": (101.4, 15.2, 0, "F"), "J_TOF3": (114.05, 15.2, 0, "F"), "J_TOF10": (127.55, 15.2, 0, "F"),
    "J_TOF6": (131.2, 22.6, 0, "F"), "J_PAUX": (118.0, 22.6, 0, "F"),
    # ---- front centre: cliff ToF and dock switch (v 89..98), clear of H5
    "J_TOF0": (58.0, 94.0, 0, "F"), "J_DOCK": (70.5, 93.5, 0, "F"), "J_TOF1": (96.0, 94.0, 0, "F"),
    # ---- look-ahead ToF (outer): inboard of the motor connectors, cable forward over J_MOT_x
    "J_TOF4": (8.0, 65.0, 90, "F"), "J_TOF7": (153.0, 69.0, 0, "F"),
    # ---- service
    "J_SWD": (20.0, 31.5, 0, "F"),
    # ---- relays (long axis along u, outside the front corners)
    "K2": (20.6, 65.3, 90, "F"),        # u 18.0..47.4, v 62.5..75.6; coil at u 20.6, NC u 35.6, COM u 40.6, NO u 45.6 (towards U5)
    "K3": (139.4, 72.8, 270, "F"),      # u 112.6..142.0, v 62.5..75.6; coil at u 139.4, NC u 124.4, COM u 119.4, NO u 114.4 (towards U6)
    "K1": (84.0, 28.0, 90, "F"),        # latch relay, u 82.6..98.0, v 26.5..34.5
    # ---- bulk capacitors (10 x 10.5 mm, top)
    "C7": (118.95, 33.0, 0, "F"),        # VBAT_SW bulk next to R_SH1 / J_PWR
    "C20": (149.0, 57.5, 0, "F"),       # VSYS bulk (charger)
    "C106": (66.0, 43.6, 0, "F"), "C105": (80.0, 44.0, 0, "F"), "C107": (94.0, 44.0, 0, "F"),   # VMOT bulk between U8 and the bridges
    "C_SET": (105.5, 32.5, 0, "F"),     # set-pulse capacitor next to K1
    # ---- power entry (pack current enters and leaves within 40 mm of J_PWR)
    "Q1": (133.5, 30.0, 90, "F"), "Q2": (133.5, 38.0, 90, "F"), "R_SH1": (127.7, 34.0, 90, "F"),
    "D1": (156.5, 38.0, 90, "F"), "U1": (128.5, 40.5, 0, "F"), "U2": (121.0, 40.6, 0, "F"), "NT1": (113.5, 41.5, 0, "F"),
    # ---- charger (straddles the pad's right edge)
    "F_CHG": (150.0, 36.5, 0, "F"), "D2": (150.0, 41.0, 0, "F"), "Q3": (150.0, 48.0, 0, "F"),
    "Q4": (137.0, 47.0, 0, "F"), "R_SNSI": (141.0, 47.0, 90, "F"), "U3": (128.0, 50.0, 0, "F"), "L1": (128.0, 57.5, 0, "F"),
    "R_SNSB": (133.5, 57.5, 90, "F"), "Q5": (118.0, 54.0, 0, "F"),
    # ---- rails (row v 27..38 on the pad)
    "U13": (51.0, 29.0, 0, "F"), "U10": (53.5, 34.5, 0, "F"), "L2": (60.5, 34.3, 0, "F"),
    "U11": (66.5, 29.5, 0, "F"), "L3": (67.5, 35.0, 0, "F"), "U12": (72.5, 29.5, 0, "F"), "L4": (73.5, 35.0, 0, "F"),
    "U14": (46.0, 39.5, 0, "F"),
    # ---- drive (on the gap pad)
    "U8": (79.5, 34.5, 0, "F"), "U5": (62.0, 56.0, 90, "F"), "U6": (98.0, 56.0, 90, "F"), "U9": (80.0, 56.0, 0, "F"),
    "U33": (106.0, 41.5, 0, "F"), "U34": (110.5, 46.0, 0, "F"), "Q40": (106.0, 47.5, 0, "F"),
    "R149": (106.0, 52.5, 0, "F"), "R150": (106.0, 57.0, 0, "F"), "F_CLAMP": (92.0, 66.5, 0, "F"), "W1": (100.0, 67.5, 0, "F"),
    "R161": (32.5, 69.05, 90, "B"), "R179": (127.5, 69.05, 90, "B"),   # brake resistors under the relays, next to the NC pads
    "U35": (54.0, 59.5, 0, "F"), "U36": (108.5, 67.6, 0, "F"),
    "U37": (12.0, 70.0, 0, "B"), "U38": (142.0, 81.0, 0, "B"),
    # ---- branches: head branch next to J_HEAD1 (front-left), chassis heater at J_HTR, LiDAR at J_LIDAR
    "R_SH2": (42.0, 79.5, 90, "F"), "R_SH3": (42.0, 87.0, 90, "F"), "U15": (47.0, 83.0, 0, "F"),
    "U16": (50.0, 78.0, 0, "F"), "L5": (55.0, 78.0, 0, "F"), "U17": (52.0, 86.0, 0, "F"),
    "D4": (42.0, 95.5, 0, "F"), "D5": (49.0, 92.0, 90, "F"),
    "U18": (152.5, 24.0, 0, "B"), "R_SH4": (156.5, 24.0, 90, "B"), "D7": (136.5, 11.0, 0, "B"),
    "U19": (17.0, 28.0, 0, "B"), "D6": (12.0, 35.0, 0, "B"),
    "U25": (115.0, 88.0, 0, "F"),
    # ---- safety chain logic
    "U23": (91.05, 22.6, 0, "F"), "U24": (104.55, 22.6, 0, "F"), "U20": (79.0, 78.0, 0, "F"),
    "U21": (20.0, 58.0, 0, "F"), "U22": (44.0, 58.0, 0, "F"),
    "U30": (20.0, 58.0, 0, "B"), "U31": (44.0, 58.5, 0, "B"), "U32": (31.0, 58.0, 0, "B"), "U40": (91.0, 23.0, 0, "B"),
    # ---- MCU block
    "U20M": (32.0, 47.0, 0, "F"), "Y1": (22.0, 49.0, 90, "F"), "U43": (18.0, 44.0, 0, "B"), "U44": (44.0, 51.0, 0, "B"),
    "U45": (44.0, 41.0, 0, "B"), "U42": (IMU[0], IMU[1], 0, "F"), "SW1": (32.0, 37.0, 0, "F"), "SW2": (44.0, 30.0, 0, "F"),
    "U41": (33.9, 27.5, 0, "B"),
    # ---- ToF muxes (front centre, either side of the IMU keep-clear)
    "U50": (66.0, 84.0, 0, "F"), "U51": (98.0, 84.0, 0, "F"),
    # ---- head link
    "U60": (46.1, 27.5, 0, "B"), "U61": (58.0, 27.0, 0, "B"),
    "U62": (132.0, 87.0, 0, "F"), "L60": (138.0, 90.0, 0, "F"), "D60": (126.0, 90.5, 0, "F"), "U63": (122.0, 84.0, 0, "F"),
    # ---- parts the guidance wants at the pins (placed by hand, top side):
    # bridge charge pump / VM decoupling (U5/U6 pins 9-16 face -v), crystal network, U10 boot / VCC capacitors
    "C115": (61.35, 61.6, 180, "F"), "C114": (63.5, 63.4, 0, "F"), "C116": (66.0, 61.6, 90, "F"), "C117": (68.4, 61.6, 90, "F"),
    "C127": (97.35, 61.6, 180, "F"), "C126": (99.5, 63.4, 0, "F"), "C128": (102.0, 61.6, 90, "F"), "C129": (104.4, 62.0, 90, "F"),
    "C145": (22.0, 45.4, 0, "F"), "C146": (22.0, 52.6, 0, "F"), "R191": (24.4, 52.8, 90, "F"),
    "C27": (53.2, 38.2, 0, "F"), "C26": (49.6, 35.3, 90, "F"),
    # ---- mechanical: holes at the envelope positions, fiducials as in circuit.py
    "H1": HOLES["H1"] + (0, "F"), "H2": HOLES["H2"] + (0, "F"), "H3": HOLES["H3"] + (0, "F"),
    "H4": HOLES["H4"] + (0, "F"), "H5": HOLES["H5"] + (0, "F"), "H6": HOLES["H6"] + (0, "F"),
    # ---- stage 3 (review M6): chain-node test points >= 10 mm (pad to pad) from each other and from the VBAT_SW / VSYS / VMOT /
    # V12_AUX test points, so one bench clip cannot bridge an element (checked by the DRC rule chain_tp_spacing)
    "TP38": (109.00, 10.00, 0, "B"), "TP39": (106.50, 25.50, 0, "B"), "TP40": (90.00, 3.00, 0, "B"), "TP50": (122.50, 3.00, 0, "B"), "TP60": (132.50, 78.50, 0, "B"), "TP61": (152.00, 53.50, 0, "B"), "TP62": (137.50, 57.50, 0, "B"), "TP8": (68.50, 82.00, 0, "B"), "TP9": (71.00, 3.00, 0, "B"),
    # ---- stage 5 (stage-4 review S1): top-side service pads SVC1-SVC10 (TP63-TP72), 2 x 5 at 2.54 mm, centre (133.0, 79.5);
    # SVC1 GND, SVC2 CHAIN_END, SVC3 K1_RUN, SVC4 RUN_HD, SVC5 RUN_12V (row v 80.77), SVC6 RELAY_RTN, SVC7 HOLD_A, SVC8 LS_A,
    # SVC9 CH_N6A, SVC10 SET_CAP (row v 78.23); every node behind 220 k (R_SV2-R_SV10)
    "TP63": (127.92, 80.77, 0, "F"), "TP64": (130.46, 80.77, 0, "F"), "TP65": (133.00, 80.77, 0, "F"), "TP66": (135.54, 80.77, 0, "F"), "TP67": (138.08, 80.77, 0, "F"),
    "TP68": (127.92, 78.23, 0, "F"), "TP69": (130.46, 78.23, 0, "F"), "TP70": (133.00, 78.23, 0, "F"), "TP71": (135.54, 78.23, 0, "F"), "TP72": (138.08, 78.23, 0, "F"),
    # ---- stage 5 (review S2): board NTC next to K1's coil end (was auto-placed at the left edge)
    "RT1": (80.5, 26.0, 0, "F"),
    "FID1": (12.0, 38.0, 0, "F"), "FID2": (157.5, 60.0, 0, "F"), "FID3": (12.0, 92.0, 0, "F"),
}

# frozen auto-arranged passives (tools/freeze_auto.py); explicit entries above win
try:
    from placement_auto import AUTO
    for _k, _v in AUTO.items():
        PLACE.setdefault(_k, _v)
except ImportError:
    AUTO = {}

# explicit near= hints for parts that are not passives of a single IC
NEAR = {}

# ----------------------------------------------------------------------------------- safety chain rules (stage 3, M6)
CHAIN_NETS = ["CH_N*", "CHAIN_END", "RUN_12V", "RUN_HD", "RELAY_RTN", "COIL_RTN", "K1_*", "SET_CAP", "SET_DIS", "RSET_A",
              "K?_CL", "HANDS_LAMP_*"]
# high-side chain nodes: a short of one of these to a supply bypasses elements (the coil returns COIL_RTN / RELAY_RTN, the clamp
# cathodes K?_CL and the lamp low side are excluded: a supply on them cannot energise a coil)
CHAIN_HIGH = ["CH_N0", "CH_N1", "CH_N2", "CH_N3", "CH_N4A", "CH_N4", "CH_N5", "CH_N6A", "CH_N6", "CH_N7", "CH_N8A", "CH_N8", "CH_N9",
              "CHAIN_END", "K1_RUN", "RUN_HD", "RUN_12V", "K1_COIL_P", "K1_SEAL_A", "K1_SET", "K1_NC1", "SET_CAP", "RSET_A", "HANDS_LAMP_P"]
SUPPLY_NETS = ["VBAT_RAW", "PSW_SRC", "VBAT_PROT", "VBAT_SW", "VSYS", "VMOT", "V12_AUX", "V12_LIDAR", "CHG_IN", "CHG_VIN",
               "HEAD_PWR_P", "HEAD_HTR_P", "CHS_HTR_P", "OUT1_L", "OUT2_L", "OUT1_R", "OUT2_R"]
# Stage 4 (follow-up review N4): logic supplies are aggressors too (3.3 V on a chain node holds an energised K1 and can light
# U_HOLD / U_LS); the LED and driver-gate nodes of every photo-MOS element are protected.
LOGIC_SUPPLIES = ["3V3", "3V3A", "V5_AUX", "V5_BUCK", "V5_CM5", "BUS_5V", "VREF_3V0"]
LED_HOLD = ["HOLD_A", "LS_A", "HSET_D"]       # LED anodes with the cathode on GND: a supply on them lights the element
CTRL_NETS = ["U20_A", "U20_K", "U21_A", "U21_K", "U21B_A", "U21B_K", "U22_A", "U22_K", "U23_A", "U23_K", "U24_A", "U24_K",
             "U_SET_A", "U_SET_K", "HOLD_A", "LS_A", "HSET_D", "CHG_GATE", "ARM_PERMIT_G", "SET_G", "SETC_G", "REARM_AUX_G", "SET_S",
             "SET_S2", "SDIS_G", "SDISB_G", "HEAD_LOOP_OK_RB", "LAB_KEY_N_RB"]     # net class CHAIN_CTRL (0.5 mm)
GATE_FINE = ["HEAD_LOOP2_OK", "WDG_OK", "HW_LATCH_G"]   # driver gates on fine-pitch ICs: rule only (pads of the IC exempt)
LED_K = ["U20_K", "U21_K", "U21B_K", "U22_K", "U23_K", "U24_K", "U_SET_K", "SET_S", "SET_S2", "RELAY_RTN"]   # a GND short closes the element
CTRL_CLEARANCE = 0.5
SUPPLY_PLANE_CLEARANCE = 1.0          # In4 VBAT_SW / VMOT / VSYS splits keep 1.0 mm from every foreign pad / via
CHAIN_SUPPLY_CLEARANCE = 1.0          # layout_guidance.md section 5: chain to VBAT_SW / VMOT / VSYS / V12_AUX copper
CHAIN_TP_SPACING = 10.0               # a chain test point and a supply / other chain test point cannot share one bench clip
LOOP_HEATER_CLEARANCE = 2.0           # layout_guidance.md section 5: loop sense to heater copper


def chain_rules():
    """KiCad custom DRC rules (.kicad_dru next to the project; kicad-cli DRC loads it) for the functional clearances of
    layout_guidance.md section 5 that a net-class clearance cannot express."""
    def anyof(side, names):
        return "(" + " || ".join("%s.NetName == '%s'" % (side, n) for n in names) + ")"
    chain_tp = ["TP8", "TP9", "TP38", "TP39", "TP40", "TP50", "TP60", "TP61", "TP62"]
    tps = "(" + " || ".join("B.memberOfFootprint('%s')" % t for t in chain_tp) + ")"
    tpa = "(" + " || ".join("A.memberOfFootprint('%s')" % t for t in chain_tp) + ")"
    sup_tp = "(" + " || ".join("B.memberOfFootprint('%s')" % t for t in ("TP41", "TP42", "TP47", "TP59", "TP44", "TP45")) + ")"
    same_fp = "!(A.Type == 'Pad' && B.Type == 'Pad' && A.Parent == B.Parent)"     # pads of one footprint: inherent to its pinout
    heater = ["HEAD_HTR_F", "HEAD_HTR_P", "HEAD_HTR_N", "CHS_HTR_F", "CHS_HTR_P"]
    loop = ["LOOP_SRC", "LOOP_SNS", "LOOP_F", "LOOP_FB", "LOOP_VHI", "LOOP_VLO", "LOOP_VB", "HEAD_LOOP_OUT", "HEAD_LOOP_RET"]
    return "\n".join([
        "(version 1)",
        "# Generated by placement.chain_rules() (board.py). RR-CHS-MAIN stage 3 (review M6) + stage 4 (follow-up N4). Do not edit by hand.",
        "(rule \"chain_to_supply\"",
        "  (constraint clearance (min %.2fmm))" % CHAIN_SUPPLY_CLEARANCE,
        "  (condition \"%s && %s && %s\"))" % (anyof("A", CHAIN_HIGH + LED_HOLD), anyof("B", SUPPLY_NETS), same_fp),
        "(rule \"hold_led_to_logic\"",
        "  (constraint clearance (min %.2fmm))" % CHAIN_SUPPLY_CLEARANCE,
        "  (condition \"%s && %s && %s\"))" % (anyof("A", LED_HOLD), anyof("B", LOGIC_SUPPLIES), same_fp),
        "# a logic supply (<= 5.25 V) on a high-side chain node cannot energise K1/K2/K3 (must-operate >= 7.3 V) or VMOT/nSLEEP (RUN_HD dividers):",
        "# 0.5 mm, the guidance's chain-to-anything value. On the U_HOLD / U_LS LED nodes it lights the element: 1.0 mm (stage 4, N4).",
        "(rule \"chain_to_logic\"",
        "  (constraint clearance (min %.2fmm))" % CTRL_CLEARANCE,
        "  (condition \"%s && %s && %s\"))" % (anyof("A", CHAIN_HIGH), anyof("B", LOGIC_SUPPLIES), same_fp),
        "(rule \"ctrl_to_supply\"",
        "  (constraint clearance (min %.2fmm))" % CTRL_CLEARANCE,
        "  (condition \"%s && %s && %s\"))" % (anyof("A", CTRL_NETS + GATE_FINE), anyof("B", SUPPLY_NETS + LOGIC_SUPPLIES), same_fp),
        "(rule \"led_cathode_to_gnd\"",
        "  (constraint clearance (min %.2fmm))" % CTRL_CLEARANCE,
        "  (condition \"%s && B.NetName == 'GND' && %s\"))" % (anyof("A", LED_K), same_fp),
        "(rule \"chain_tp_spacing\"",
        "  (constraint clearance (min %.1fmm))" % CHAIN_TP_SPACING,
        "  (condition \"%s && (%s || %s) && A.NetName != B.NetName\"))" % (tpa, tps, sup_tp),
        "(rule \"loop_to_heater\"",
        "  (constraint clearance (min %.1fmm))" % LOOP_HEATER_CLEARANCE,
        "  (condition \"%s && %s && !(A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('J_HEAD1') && B.memberOfFootprint('J_HEAD1'))\"))"
        % (anyof("A", loop), anyof("B", heater)),
        "# J_HEAD1 pins 4 (HEAD_HTR_N) and 5 (HEAD_LOOP_OUT) are adjacent by contract J1 (Mini-Fit Jr 4.2 mm pitch: 1.5 mm pad gap); copper outside the header keeps 2 mm",
        ""])


RAILS = ("GND", "3V3", "3V3A", "V5_AUX", "V5_BUCK", "V5_CM5", "VSYS", "VBAT_SW", "VMOT", "V12_AUX", "VREF_3V0")
SMALL_BOTTOM_OK = re.compile(r"^(R_0402|R_0603|R_0805|R_1206|C_0402|C_0603|C_0805|C_1206|C_1210|L_0603|D_SOD-123|SOT-23|"
                             r"LED_0603|Fuse_1206|TestPoint_Keystone_5019|USON-10)")


def _fpname(p):
    return p.footprint.split(":", 1)[1] if p.footprint else ""


def auto_near(board):
    """near= for every unplaced part: the placed part pin it shares a non-rail net with (same group first)."""
    placed = {p.ref: p for p in board.parts if p.ref in PLACE}
    pin_index = {}
    for p in placed.values():
        for num, net in p.pins.items():
            if net and net not in RAILS:
                pin_index.setdefault(net, []).append((p, num))
    unplaced = [p for p in board.parts if p.ref not in PLACE]
    # passes: a passive whose nets reach only other passives inherits their anchor in a later pass
    anchor = {}
    for _ in range(4):
        for p in unplaced:
            if p.ref in anchor or p.ref in NEAR:
                continue
            cands = []
            for num, net in p.pins.items():
                if not net or net in RAILS:
                    continue
                for q, qn in pin_index.get(net, []):
                    if q.ref == p.ref:
                        continue
                    big = len(q.pins) >= 3 and not q.ref.startswith(("R", "C", "D", "FB", "TP", "F"))
                    cands.append((0 if q.group is p.group else 1, 0 if big else 1, q.ref, qn))
            if cands:
                cands.sort()
                anchor[p.ref] = "%s.%s" % (cands[0][2], cands[0][3])
        for ref, a in list(anchor.items()):
            p = board.part(ref)
            for num, net in p.pins.items():
                if net and net not in RAILS:
                    pin_index.setdefault(net, []).append((p, num))
    try:
        import json as _json, os as _os
        _d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "reports")
        _os.makedirs(_d, exist_ok=True)
        with open(_os.path.join(_d, "near_anchors.json"), "w") as _f:
            _json.dump(dict(sorted(dict(anchor, **NEAR).items())), _f, indent=0)
    except OSError:
        pass
    for p in unplaced:
        if p.ref in NEAR:
            p.near = NEAR[p.ref]
        elif p.ref in anchor:
            p.near = anchor[p.ref]
        a = (NEAR.get(p.ref) or anchor.get(p.ref) or "").split(".")[0]
        # follow the anchor chain to an explicitly placed part
        seen = set()
        while a and a not in PLACE and a not in seen:
            seen.add(a)
            a = (NEAR.get(a) or anchor.get(a) or "").split(".")[0]
        # side: same side as the explicitly placed anchor part (decoupling and series parts next to their pins);
        # bottom for anchors that are through-hole (relays, Micro-Fit/Mini-Fit) or on the bottom; test points bottom
        side = "B"
        if a in PLACE:
            aside = PLACE[a][3]
            fp = board.part(a).footprint or ""
            tht = any(t in fp for t in ("Relay_THT", "Mini-Fit", "Micro-Fit", "MountingHole"))
            side = aside if not (tht or a.startswith("J")) else "B"
        if p.ref.startswith("TP"):
            side = "B"
            p.near = None
        if not SMALL_BOTTOM_OK.match(_fpname(p)):
            side = "F"
        p.side = side
    return anchor


def setup(board):
    # ------------------------------------------------------------------ nets
    board.rail(*RAILS)
    # first matching class wins: most specific first
    # Clearances: KiCad applies a class clearance also between the pads of one footprint, and rrkicad's plane
    # fan-out places a via with its OWN class clearance (not the neighbour's).  Hence: every class keeps the
    # fab clearance 0.15 mm except SAFETY_CHAIN (0.2 mm, see README "Clearances": the 0.5 / 1.0 mm functional
    # clearances of layout_guidance.md section 5 are a review item, not DRC-enforced).
    # Stage 3 (review M6): class clearance 0.5 mm (the tool's plane fan-out now honours pairwise class clearance, tools/eda
    # STATUS defect 3), plus the custom DRC rules of chain_rules() (1.0 mm chain-to-supply copper, test-point spacing).
    board.netclass("SAFETY_CHAIN", CHAIN_NETS, track=0.4, clearance=0.5, via_dia=0.8, via_drill=0.4)
    board.netclass("CHAIN_CTRL", CTRL_NETS, track=0.25, clearance=CTRL_CLEARANCE, via_dia=0.6, via_drill=0.3)
    board.netclass("HC_PACK", ["VBAT_RAW", "PSW_SRC", "VBAT_PROT", "VBAT_SW"], track=1.0, clearance=0.15, via_dia=0.8, via_drill=0.4)
    board.netclass("HC_VMOT", ["VMOT", "OUT1_L", "OUT2_L", "OUT1_R", "OUT2_R", "MOT_L_A", "MOT_L_B", "MOT_R_A", "MOT_R_B",
                               "MOTC_*", "BRK_*", "CLAMP_F", "CLAMP_R"], track=0.8, clearance=0.15, via_dia=0.8, via_drill=0.4)
    board.netclass("HC_BRANCH", ["HEAD_HTR_F", "HEAD_HTR_P", "HEAD_HTR_N", "CHS_HTR_F", "CHS_HTR_P", "V5_BUCK", "V5_CM5", "VSYS",
                                 "CHG_IN", "CHG_F", "CHG_VIN", "U3_CLP", "U3_CSP", "U3_SW", "U10_SW"],
                   track=0.8, clearance=0.15, via_dia=0.8, via_drill=0.4)
    board.netclass("PWR_1A5", ["HEAD_PWR_F", "HEAD_PWR_E", "HEAD_PWR_P", "V12_LIDAR", "3V3", "V5_AUX", "3V3A", "V12_AUX", "BUS_5V",
                               "TOF*_3V3", "ENC_*_5V", "U11_SW", "U12_SW"], track=0.4, clearance=0.15, via_dia=0.6, via_drill=0.3)
    board.netclass("SIG", ["*"], track=0.2, clearance=0.15, via_dia=0.6, via_drill=0.3)

    # ------------------------------------------------------------------ outline, holes, keep-outs
    board.outline_rect(W, H, radius=2.0, origin="corner")
    for h, (x, y) in HOLES.items():
        # parts and vias out of the 7 mm screw-head area; tracks may leave the hole pad (H1/H3 GND bond, others via 1M||10n)
        board.keepout("KO_" + h, circle=(x, y, HOLE_KO), tracks=False, vias=True, copper=False, pads=False, footprints=False)
    # Bottom-side parts ban on the gap pad: needed only while the auto-arranger runs.  rrkicad exports this
    # footprint-only rule area to Freerouting as a full B.Cu keep-out (tool defect), which would block all bottom
    # routing on 60 x 40 mm, so it is left out once the placement is frozen (tools/fitcheck.py checks the rule).
    # Stage 3: always present again (tools/eda STATUS defect 5 fixed: a footprint-only rule area is no longer exported to the DSN);
    # without it the auto-arranger put stage-3 passives on the gap pad.
    if True:
      board.keepout("KO_THERMAL_BOTTOM", polygon=[(THERMAL[0], THERMAL[1]), (THERMAL[2], THERMAL[1]), (THERMAL[2], THERMAL[3]), (THERMAL[0], THERMAL[3])],
                    layers=("B.Cu",), tracks=False, vias=False, copper=False, pads=False, footprints=True)

    # IMU: no vias under the package (layout_guidance.md section 6.11; replaces the stock footprint's own rule area)
    board.keepout("KO_IMU_VIAS", polygon=[(IMU[0] - 2.6, IMU[1] - 1.9), (IMU[0] + 2.6, IMU[1] - 1.9), (IMU[0] + 2.6, IMU[1] + 1.9), (IMU[0] - 2.6, IMU[1] + 1.9)],
                  tracks=False, vias=True, copper=False, pads=False, footprints=False)
    # NT1 is the single heater-return-to-GND point: no plane fan-out via on its GND pad (routed to the bulk capacitor)
    board.part("NT1").zone_connect = "none"

    # ------------------------------------------------------------------ planes (6 layers: In1 GND, In4 power splits)
    board.zone("GND", ["In1.Cu"], connect="solid")
    # In4.Cu power splits: non-overlapping polygons (Freerouting rejects overlapping plane areas)
    board.zone("3V3", ["In4.Cu"], polygon=[(0.5, 27.0), (50.0, 27.0), (50.0, 62.0), (0.5, 62.0)], connect="solid", name="P_3V3")
    board.zone("VMOT", ["In4.Cu"], polygon=[(58.0, 37.0), (102.0, 37.0), (102.0, 62.0), (58.0, 62.0)], connect="solid", clearance=SUPPLY_PLANE_CLEARANCE, name="P_VMOT")
    board.zone("VSYS", ["In4.Cu"], polygon=[(104.0, 42.0), (159.5, 42.0), (159.5, 60.0), (104.0, 60.0)], connect="solid", clearance=SUPPLY_PLANE_CLEARANCE, name="P_VSYS")
    board.zone("VBAT_SW", ["In4.Cu"], polygon=[(52.0, 0.5), (159.5, 0.5), (159.5, 41.0), (103.0, 41.0), (103.0, 36.0), (52.0, 36.0)],
               connect="solid", clearance=SUPPLY_PLANE_CLEARANCE, name="P_VBAT_SW")
    board.zone("VBAT_SW", ["In4.Cu"], polygon=[(0.5, 63.0), (57.0, 63.0), (57.0, 99.5), (0.5, 99.5)], connect="solid", clearance=SUPPLY_PLANE_CLEARANCE, name="P_VBAT_SW_FL")

    board.autoplace_options(clearance=0.25, spread=0.2, ic_halo=1.5)
    auto_near(board)


def routing(board):
    """Autorouter settings for the long unattended run (tools/eda/README.md "Recommended recipe"): plane nets stay
    routable because 111 plane pads have no fan-out via (zone_nets="route"); fine-pitch escape off (56 of 139 escapes had
    no legal position); run with `build board.py --budget 7200` in 40-minute chunks so that an interrupted job keeps its
    best result on disk (a single uninterrupted job routes more per hour but leaves nothing if it is killed)."""
    board.route(passes=500, threads=3, timeout=7200, retries=2, restarts=0, optimizer=False, zone_nets="route",
                escape=False, finisher=True, chunk=2400, stall=3)
