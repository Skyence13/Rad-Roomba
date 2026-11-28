"""RR-HEAD-ACQ stage-2 layout: placement, lane replication, planes, net classes, keep-outs, pre-routes.

Board frame = envelope frame: X = u (toward robot right), Y = v (forward), origin rear-left corner, mm.
Lane block (identical x4): lane centre LC[k]; shield can du -18..+18, v CAN_V0..CAN_V1 (libs.py); rear connector strip
v 1.5..7.3; lane logic v 45..67 (in front of the HV_BUS trunk at v = V_TRUNK).

Inside the can each channel occupies a column of 18 mm local width ("x" from the column origin):
    floor column origin u = LC - 18.0, reference column origin u = LC + 4.25  (translation 22.25 mm, identical layout)
so both channels use one local placement table (CH) and one pre-route table.  The floor-only slow path sits in the
centre strip (du -4.75..+4.75).  Placement source of truth:
    * EXPLICIT entries below (connectors, ICs, HV parts, clamps, shield clips/can, holes) and
    * layout_frozen.json: positions of the remaining passives as produced by the tool's auto-arranger in pass 1 and
      then frozen (README "Placement workflow"); lane 0 only - lanes 1..3 are board.replicate() copies.
"""
import json
import os

import libs

HERE = os.path.dirname(os.path.abspath(__file__))
LC = [31.75, 119.25, 206.75, 294.25]
DU_LANE = 87.5
V_TRUNK = 43.0                     # HV_BUS trunk on F.Cu
V_LOGIC0 = 45.0                    # lane logic area starts here
F_ORG, R_ORG = -18.0, 4.25         # column origins (du) of the floor / reference channel
FROZEN = os.path.join(HERE, "layout_frozen.json")

# ------------------------------------------------------------------ channel table (local x, v, rot); key = prefix + k
# k = reference number - channel base (F0: 100, R0: 500); same k = same function in both channels (stage-1 generator).
CH = {
    "J1": (7.62, 3.9, 270),        # anode U.FL, centre pad toward the can (mouse hole at local x 7.62)
    "J2": (2.53, 3.9, 270),        # bias U.FL
    # HV filter cell (rear-left): HVF via (2.45, 9.6) / (2.54, 6.9) outside, HV_BUS via (5.0, 19.6)
    "C2": (4.5, 9.6, 0),           # HVF reservoir 100 nF / 100 V
    "R2": (2.45, 12.0, 270),       # 100 R  HVF <- HV1
    # anode input
    "D1": (10.5, 11.3, 180),       # BAV99 clamp, pin 3 (anode) toward the anode trace
    "R3": (7.0, 12.4, 90),         # R_IN 20 R
    "R4": (9.4, 14.05, 0),         # R_IN 20 R
    "C3": (8.6, 15.85, 0),         # 4.7 uF trim node
    "C4": (11.5, 16.05, 0),        # 100 nF trim node
    "U1": (10.3, 19.0, 0),         # 74LVC2G53 test-pulse switch
    "U2": (8.6, 24.0, 0),          # preamp OPA838
    "U3": (8.6, 30.6, 0),          # fast stage OPA838
    "D2": (3.4, 33.6, 0),          # BAT54S comparator clamp
    "U4": (8.6, 36.5, 0),          # TLV3502 LLD/ULD
}
# R1, C1 (HV filter) and C9, C10 (C_INJ) are seeded in layout_frozen.json and spaced by scripts/legalize.py
# (HV pad spacing >= 1.05 mm); the remaining cell parts above are fixed.
# floor-only slow path: local coordinates of the FLOOR column (local x 13.25..22.75 = centre strip du -4.75..+4.75)
CH_SLOW = {"U5": (18.0, 24.5, 0), "D3": (14.9, 30.6, 0), "U6": (18.0, 35.8, 0)}

# lane logic (du, v, rot) - outside the can, in front of the HV trunk
LANE = {
    "U1": (0.0, 49.0, 0),          # TLV9062 trim buffers
    "U2": (-9.5, 52.5, 0),         # 74LVC32 latch clocks
    "U3": (9.5, 52.5, 0),          # 74LVC1G32
    "U4": (-13.0, 61.0, 0),        # 74LVC74 latches
    "U5": (-3.5, 61.0, 0),
    "U6": (6.0, 61.0, 0),
    "U7": (14.0, 61.0, 0),         # TMUX1108 lane monitor mux
    "J1": (-1.80, 4.0, 0),         # JST GH-6 auxiliary pigtail, mating face to the rear edge
}


def lane0_ref(prefix, k, chan):
    base = {"F": 100, "R": 500, "L": 1000}[chan]
    return "%s%d" % (prefix, base + k)


def _split(key):
    i = 0
    while key[i].isalpha():
        i += 1
    return key[:i], int(key[i:])


def explicit():
    """{ref: (x, y, rot, side)} of every explicitly placed part (lane 0 + board level)."""
    at = {}
    u0 = LC[0]
    for key, (x, v, rot) in CH.items():
        pre, k = _split(key)
        at[lane0_ref(pre, k, "F")] = (round(u0 + F_ORG + x, 3), v, rot, "F")
        at[lane0_ref(pre, k, "R")] = (round(u0 + R_ORG + x, 3), v, rot, "F")
    for key, (x, v, rot) in CH_SLOW.items():
        pre, k = _split(key)
        at[lane0_ref(pre, k, "F")] = (round(u0 + F_ORG + x, 3), v, rot, "F")
    for key, (du, v, rot) in LANE.items():
        pre, k = _split(key)
        at[lane0_ref(pre, k, "L")] = (round(u0 + du, 3), v, rot, "F")
    for i, (du, v, rot) in enumerate(libs.CLIPS):
        at["SH%d" % (1001 + i)] = (round(u0 + du, 3), round(v, 3), rot, "F")
    at["SH1013"] = (u0, libs.CAN_V0 + libs.CAN_D / 2, 0, "F")
    at.update(BOARD)
    return at


# --------------------------------------------------------------------------- board-level explicit placement
HOLES = {"H2801": (75.5, 30.0), "H2802": (163.0, 4.5), "H2803": (250.5, 4.5), "H2804": (75.5, 91.5),
         "H2805": (163.0, 91.5), "H2806": (250.5, 91.5), "H2807": (5.0, 48.0), "H2808": (321.0, 48.0)}
# H2801 = H1 moved from (75.5, 4.5) to (75.5, 30.0): CR-M02 (the J1 header must sit at the rear edge, centred on the
# J1 cable port).  All other holes at the envelope positions.
BOARD = {ref: (x, y, 0, "F") for ref, (x, y) in HOLES.items()}
BOARD.update({
    # J1 landing: two rear-facing Micro-Fit headers side by side (pin row at v 10.57, mating faces at v 1.5)
    "J2001": (97.34, 10.57, 180, "F"),   # J1 pigtail (8-way), pins 1..8 at u 97.34 .. 76.34
    "J2601": (68.58, 10.57, 180, "F"),   # heater / NTC (6-way), pins 1..6 at u 68.58 .. 53.58
    # power entry (right part of the J1 landing, near J2001 pins 1/2)
    "D2001": (96.0, 16.5, 90, "F"), "L2001": (96.5, 23.0, 90, "F"), "U2001": (94.0, 30.0, 270, "F"),
    "L2002": (95.5, 37.0, 0, "F"),
    # heater switch (middle of the J1 landing, between J2001 pins 3/4 and J2601 pins 1/2)
    "R2601": (84.0, 15.2, 0, "F"), "Q2601": (73.5, 17.0, 0, "F"), "D2601": (60.5, 16.2, 0, "F"),
    "U2601": (85.0, 20.5, 0, "F"), "D2602": (64.0, 22.5, 0, "F"), "Q2602": (62.0, 27.0, 0, "F"),
    "Q2603": (57.0, 31.0, 0, "F"), "D2603": (57.0, 36.0, 0, "F"), "D2604": (53.0, 22.0, 90, "F"),
    # regulators in front of the trunk
    "U2101": (58.0, 52.0, 0, "F"), "L2101": (64.5, 52.0, 0, "F"), "L2102": (72.0, 51.0, 90, "F"),
    "U2102": (77.5, 51.0, 0, "F"), "L2103": (84.0, 51.0, 90, "F"), "U2103": (89.5, 51.0, 0, "F"),
    "U2104": (95.5, 51.0, 0, "F"), "FB2101": (93.0, 58.5, 0, "F"), "U2105": (96.0, 63.0, 0, "F"),
    # SiPM bias (front, u 100..146)
    "FB2201": (104.0, 74.0, 90, "F"), "U2201": (108.0, 79.0, 0, "F"), "L2201": (108.0, 86.5, 0, "F"),
    "D2201": (114.5, 82.0, 90, "F"), "Q2201": (124.0, 81.0, 0, "F"), "D2202": (124.0, 86.5, 0, "F"),
    "Q2202": (130.0, 85.0, 0, "F"), "U2202": (132.0, 75.0, 0, "F"), "D2203": (126.0, 74.0, 0, "F"),
    "Q2203": (118.0, 75.0, 0, "F"), "Q2204": (118.0, 70.5, 0, "F"), "U2203": (139.0, 81.0, 0, "F"),
    "U2204": (139.0, 86.0, 0, "F"), "J2201": (122.0, 92.0, 180, "F"), "Q2205": (130.0, 91.0, 0, "F"),
    "JP2201": (116.0, 92.0, 0, "F"), "U2205": (142.0, 70.0, 0, "F"), "U2206": (142.0, 76.0, 0, "F"),
    # DACs between lane 1 and lane 2 logic
    "U2301": (146.0, 50.0, 0, "F"), "U2302": (155.0, 50.0, 0, "F"), "U2303": (164.0, 50.0, 0, "F"),
    "U2304": (173.0, 50.0, 0, "F"), "U2305": (150.0, 59.0, 0, "F"), "U2306": (182.0, 59.0, 0, "F"),
    # MCU (pin 1 rear-left), TCXO at pin 12, service connectors
    "U2401": (168.0, 77.5, 90, "F"), "Y2401": (163.5, 65.5, 0, "F"), "FB2401": (159.0, 65.5, 0, "F"),
    "J2401": (186.0, 89.0, 0, "F"), "J2402": (196.0, 92.0, 180, "F"), "D2401": (180.0, 93.0, 0, "F"),
    "D2402": (180.0, 90.4, 0, "F"), "U2402": (53.0, 39.0, 0, "F"), "U2403": (240.0, 34.0, 0, "F"),
    "U2404": (189.0, 80.0, 0, "F"), "U2405": (190.0, 72.0, 0, "F"),
    # monitor / selects
    "U2701": (203.0, 74.0, 0, "F"), "U2702": (213.0, 74.0, 0, "F"), "U2703": (182.0, 51.0, 0, "F"),
    "U2704": (208.0, 86.0, 0, "F"), "J2701": (214.0, 91.0, 90, "F"), "D2701": (199.0, 86.0, 0, "F"),
    # rail-switch connectors on the front edge (H5 keep-out splits the landing u 150..176)
    "J2002": (154.5, 92.0, 180, "F"), "J2003": (171.5, 92.0, 180, "F"), "J2004": (144.6, 92.0, 180, "F"),
    # isolated RS-485 (J2 landing): island u 230..272, v 0..13; barrier v 13..17; ISO1430 straddles it
    "J2501": (262.3, 4.0, 0, "F"), "U2501": (250.0, 15.0, 270, "F"), "FB2501": (243.0, 9.0, 0, "F"),
    "D2501": (262.0, 10.5, 0, "F"), "D2502": (240.5, 11.5, 0, "F"), "U2502": (236.0, 7.0, 0, "F"),
    "U2503": (236.0, 15.0, 270, "F"),
    # fiducials
    "FID2801": (4.0, 4.0, 0, "F"), "FID2802": (322.0, 4.0, 0, "F"), "FID2803": (4.0, 92.0, 0, "F"),
})


def placement():
    at = explicit()
    if os.path.exists(FROZEN):
        with open(FROZEN) as f:
            frozen = json.load(f)
        for ref, v in frozen.items():
            if ref not in at:
                at[ref] = tuple(v)
    return at


def apply(board, parts):
    """Everything after the netlist import: replication, outline items, zones, classes, keep-outs, routing."""
    groups = {g.name: g for g in board.groups}
    for k in (1, 2, 3):
        for s in ("FLOOR", "REF", "LOGIC"):
            board.replicate((groups["LANE0_%s" % s], groups["LANE%d_%s" % (k, s)]), dx=DU_LANE * k, dy=0.0)
    pass1 = not os.path.exists(FROZEN)
    if pass1:
        # pass 1 only: keep the auto-arranger out of the lane 1..3 block areas (their parts are copies placed later)
        for k in (1, 2, 3):
            c = LC[k]
            board.keepout("KO_PASS1_LANE%d" % k, polygon=[(c - 18.6, 0.5), (c + 18.6, 0.5), (c + 18.6, 67.5), (c - 18.6, 67.5)],
                          layers=("F.Cu",), tracks=False, vias=False, copper=False, footprints=True)
        # ... and keep lane-0 parts inside the lane-0 block (no overflow next to the can or into the rear strip)
        for name, poly in (("L", [(0.5, 0.5), (13.6, 0.5), (13.6, 41.3), (0.5, 41.3)]),
                           ("R", [(49.9, 12.3), (57.0, 12.3), (57.0, 41.3), (49.9, 41.3)]),
                           ("REAR", [(13.6, 0.5), (49.9, 0.5), (49.9, 8.1), (13.6, 8.1)])):
            board.keepout("KO_PASS1_LANE0_%s" % name, polygon=poly, layers=("F.Cu",), tracks=False, vias=False,
                          copper=False, footprints=True)
    _near_hints(board, parts)
    for p in board.parts:
        if p.ref.startswith(("TP", "H28", "FID", "JP")) or p.ref == "J2401":
            p.bom = False          # bare test pads: the stock pad footprint is excluded from the BOM; keep symbol in step
    _rules(board)
    _keepouts(board)
    _planes(board)
    if not pass1:
        notes, vias = preroutes(board)
        _hv_via_bands(board, vias)
        with open(os.path.join(HERE, "reports", "preroute_notes.json"), "w") as f:
            json.dump({"notes": notes, "hv_vias": vias}, f, indent=1)
    # tools/eda/tests/head_escape: copy of electronics/head_acq for the EDA work package - escape on
    # (LQFP-100 + WQFN-16 DACs), continue runs within a budget (CLI --budget), finisher on
    board.route(escape=True, finisher=True, plane_fanout=True, retries=2, timeout=900, passes=200, optimizer=False)
    board.autoplace_options(clearance=0.12, ic_halo=0.5, edge_margin=0.6, spread=0.0, grid=0.1)


def _rules(board):
    hv = ["HV_BUS", "HV_RAW", "HV_RAWF", "HV_SW", "HV_MIR", "HV_G", "HV_BLD", "HV_BFBM", "HV_FBM", "HV_MDM", "HV_CAP",
          "[FR]?_HV1", "[FR]?_HVF"]
    board.netclass("HV", hv, track=0.25, clearance=1.0, via_dia=0.6, via_drill=0.3)
    board.netclass("HEATER", ["HEAD_HTR_P", "HEAD_HTR_N", "HTR_PS", "HTR_SW"], track=1.0, clearance=1.0, via_dia=1.0, via_drill=0.5)
    board.netclass("POWER", ["GND", "+5V_A", "+3V3", "+3V3_EVT", "+5V6", "+5V6_A", "+5V6_E", "+3V3A", "+3V3_HV", "VIN_*",
                             "HEAD_PWR_*", "BK_SW", "TCXO_VDD", "EF_RTN", "[FR]?_V5", "FRAME"],
                   track=0.4, clearance=0.15, via_dia=0.6, via_drill=0.3)
    board.netclass("ISOLATED", ["BUS_*", "J2_PRES", "SYNC_RX_B"], track=0.4, clearance=0.25)
    board.netclass("DIFF", ["RS485_DP", "RS485_DN", "SYNC_P", "SYNC_N"], track=0.25, clearance=0.25, diff_width=0.25, diff_gap=0.25)
    board.netclass("SENSITIVE", ["[FR]?_A", "[FR]?_PINA", "[FR]?_PIN", "[FR]?_PFB", "[FR]?_PG", "[FR]?_FS", "[FR]?_FFB",
                                 "[FR]?_TRIM", "[FR]?_TPI", "[FR]?_SI", "[FR]?_SS", "[FR]?_SFB"],
                   track=0.2, clearance=0.3, via_dia=0.6, via_drill=0.3)
    board.waive("drc", "items_not_allowed",
                "GND copper (plane fan-out stubs/vias of the clip pads and of parts next to the wall) under a shield-can "
                "wall: the can is on GND, so GND copper under it is harmless; the wall keep-outs exist to keep every OTHER "
                "net off F.Cu under the walls.", match=r"KO_WALL_[^|]*\| (Track|Via) \[GND\]")
    # waiver: pads of ONE component closer than its own net-class clearance (U.FL centre pin to shell 0.45 mm,
    # 0603/0805/1206 HV capacitor and resistor terminals): the spacing is the part's rated spacing, not a layout choice.
    board.waive("drc", "clearance",
                "Pad-to-pad clearance inside one component (U.FL centre/shell, two-terminal HV parts) is set by the "
                "part itself; the HV/SENSITIVE class clearances apply between different components and to copper.",
                match=r"\| Pad [^|]*\bof ([A-Z]+\d+) on [^|]*\| Pad [^|]*\bof \1 on")


def _keepouts(board):
    _wall_keepouts(board)
    # mounting holes: standoff + screw head 6.0 mm (envelope) + 0.5 mm, all copper layers, no tracks/vias/pour
    for ref, (x, y) in HOLES.items():
        board.keepout("KO_" + ref, circle=(x, y, 7.0), layers=("*.Cu",), tracks=True, vias=True, copper=True,
                      pads=False, footprints=False)
    # U.FL receptacles: keep the plane fan-out vias off the connector body (the stock footprint carries a rule area)
    for k in range(4):
        for org in (F_ORG, R_ORG):
            for key in ("J1", "J2"):
                x, v, _r = CH[key]
                board.keepout("KO_UFL_%d_%s_%s" % (k, "F" if org == F_ORG else "R", key),
                              circle=(LC[k] + org + x, v, 4.8), layers=("*.Cu",), tracks=False, vias=True, copper=False,
                              pads=False, footprints=False)
    board.keepout("KO_UFL_J2701", circle=(BOARD["J2701"][0], BOARD["J2701"][1], 5.6), layers=("*.Cu",), tracks=False,
                  vias=True, copper=False, pads=False, footprints=False)
    # tool work-around: the plane fan-out checks its own net-class clearance only, so a GND via/stub could land
    # inside the 1.0 mm HV / heater clearance.  Via keep-outs around the HV and heater pads of the board-level
    # blocks keep the fan-out vias away (those GND pads connect through the outer GND pour or the autorouter).
    for i, (x, y, r) in enumerate(_hv_pad_circles()):
        board.keepout("KO_HVVIA_%d" % i, circle=(x, y, 2 * r), layers=("*.Cu",), tracks=False, vias=True, copper=False,
                      pads=False, footprints=False)
    # HV trunk corridor: no footprints within +-1.5 mm of the trunk (parts kept clear; the trunk is a pre-route)
    board.keepout("KO_TRUNK", polygon=[(12.0, V_TRUNK - 1.6), (314.0, V_TRUNK - 1.6), (314.0, V_TRUNK + 1.6), (12.0, V_TRUNK + 1.6)],
                  layers=("F.Cu",), tracks=False, vias=False, copper=False, footprints=True)


ISLAND = [(230.0, 0.0), (272.0, 0.0), (272.0, 13.0), (230.0, 13.0)]
BARRIER_OUT = [(226.0, 0.0), (276.0, 0.0), (276.0, 17.0), (226.0, 17.0)]


def _planes(board):
    W, H = 326.0, 96.0
    # In1 = GND everywhere except the isolated island + barrier (one polygon with a rectangular notch at the rear edge)
    gnd = [(0.0, 0.0), (226.0, 0.0), (226.0, 17.0), (276.0, 17.0), (276.0, 0.0), (W, 0.0), (W, H), (0.0, H)]
    board.zone("GND", ["In1.Cu"], polygon=gnd, connect="solid", name="GND_In1")
    board.zone("BUS_GND", ["In1.Cu"], polygon=ISLAND, connect="solid", name="BUS_GND_In1")
    # In4 power split (non-overlapping): +5V_A under the AFE strip, +3V3_EVT under the lane logic, +5V6 at J1 / REG,
    # +3V3 for the rest (MCU, DAC, bias, front strip)
    board.zone("+5V_A", ["In4.Cu"], polygon=[(0, 0), (49.9, 0), (49.9, 41.5), (0, 41.5)], connect="solid", name="P5VA_0")
    board.zone("+5V_A", ["In4.Cu"], polygon=[(101.1, 0), (226, 0), (226, 17.0), (276, 17.0), (276, 0), (W, 0), (W, 41.5),
                                             (101.1, 41.5)], connect="solid", name="P5VA_1")
    for k, c in enumerate(LC):
        board.zone("+3V3_EVT", ["In4.Cu"], polygon=[(c - 18, 41.5), (c + 18, 41.5), (c + 18, 67.5), (c - 18, 67.5)],
                   connect="solid", name="P3V3EVT_%d" % k)
    board.zone("+5V6", ["In4.Cu"], polygon=[(49.9, 0), (101.1, 0), (101.1, 67.5), (49.9, 67.5)], connect="solid", name="P5V6")
    l = LC
    p3 = [(0, 41.5), (l[0] - 18, 41.5), (l[0] - 18, 67.5), (l[1] + 18, 67.5), (l[1] + 18, 41.5), (l[2] - 18, 41.5),
          (l[2] - 18, 67.5), (l[2] + 18, 67.5), (l[2] + 18, 41.5), (l[3] - 18, 41.5), (l[3] - 18, 67.5), (l[3] + 18, 67.5),
          (l[3] + 18, 41.5), (W, 41.5), (W, H), (0, H)]
    board.zone("+3V3", ["In4.Cu"], polygon=p3, connect="solid", name="P3V3")
    # outer layers: GND pour (added after routing), BUS_GND in the island; isolation barrier = keep-out on all layers
    board.zone("GND", ["F.Cu", "B.Cu"], polygon=gnd, connect="solid", name="GND_outer", clearance=0.3)
    board.zone("BUS_GND", ["F.Cu", "B.Cu"], polygon=ISLAND, connect="solid", name="BUS_GND_outer")
    for name, poly in (("KO_BARRIER_L", [(226, 0), (230, 0), (230, 13), (226, 13)]),
                       ("KO_BARRIER_R", [(272, 0), (276, 0), (276, 13), (272, 13)]),
                       ("KO_BARRIER_F", [(226, 13), (276, 13), (276, 17), (226, 17)])):
        board.keepout(name, polygon=poly, layers=("*.Cu",), tracks=True, vias=True, copper=True, pads=False, footprints=False)


RAILS = {"GND", "+3V3", "+5V_A", "+3V3_EVT", "+5V6", "+3V3A", "BUS_GND", "FRAME", "VREF_ADC", "VBL"}


def _domain(ref):
    import re
    m = re.match(r"[A-Z]+(\d+)$", ref)
    n = int(m.group(1))
    if 100 <= n < 900:
        return "lane%d" % ((n // 100 - 1) % 4)
    if 1000 <= n < 1400:
        return "lane%d" % ((n - 1000) // 100)
    return None


def _near_hints(board, parts):
    """near= for every part that is neither explicit nor a lane copy: the pad of an explicitly placed part it shares a
    (non-rail) net with - an IC/connector of the same lane or sheet first.  Pure rail-to-GND capacitors are left to the
    tool's decoupling assignment (spread over the supply pins of the ICs of their sheet)."""
    at = placement()
    pd = {p["ref"]: p for p in parts}
    by_net = {}
    for p in parts:
        for num, v in p["pins"].items():
            if v:
                by_net.setdefault(v[1], []).append((p["ref"], num))
    for part in board.parts:
        if part.ref in at or part.replica_of:
            continue
        p = pd[part.ref]
        nets = [v[1] for v in p["pins"].values() if v and v[1] not in RAILS]
        best = None
        for net in nets:
            for ref, num in by_net.get(net, []):
                if ref == part.ref:
                    continue
                q = pd[ref]
                score = 0
                if ref in at:
                    score += 100
                if _domain(ref) == _domain(part.ref):
                    score += 50
                if q["block"] == p["block"]:
                    score += 20
                if ref[0] in "UJQ":
                    score += 10
                if _domain(part.ref) and _domain(ref) and _domain(ref) != _domain(part.ref):
                    score -= 200
                if best is None or score > best[0]:
                    best = (score, ref, num)
        if best and best[0] >= 100:
            part.near = "%s.%s" % (best[1], best[2])


def _hv_pad_circles():
    import fnmatch
    import overrides
    geo = json.load(open(os.path.join(HERE, "scripts", "fp_geometry.json")))
    pats = ["HV_BUS", "HV_RAW", "HV_RAWF", "HV_SW", "HV_MIR", "HV_G", "HV_BLD", "HV_BFBM", "HV_FBM", "HV_MDM", "HV_CAP",
            "HEAD_HTR_P", "HEAD_HTR_N", "HTR_PS", "HTR_SW"]
    parts, _ = overrides.apply(overrides.load_circuit().PARTS)
    at = placement()
    out = []
    for p in parts:
        if p["block"] not in ("BIAS", "HEATER", "POWER_IN") or p["ref"] not in at:
            continue
        x, y, r, _s = at[p["ref"]]
        g = geo.get(p["footprint_hint"])
        if not g:
            continue
        import math
        has_hv = any(v and any(fnmatch.fnmatchcase(v[1], q) for q in pats) for v in p["pins"].values())
        for pad in g["pads"]:
            v = p["pins"].get(pad[0])
            hvpad = bool(v) and any(fnmatch.fnmatchcase(v[1], q) for q in pats)
            if not hvpad and not (has_hv and v and v[1] == "GND"):
                continue
            px, py = pad[1], -pad[2]
            a = math.radians(r)
            bx, by = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
            rad = 0.5 * math.hypot(pad[3], pad[4]) + (1.0 + 0.35 if hvpad else 3.6)
            out.append((round(x + bx, 3), round(y + by, 3), round(rad, 3)))
    return out


# =============================================================================================== pre-routes
def _geometry():
    """Pad rectangles of every placed part, lanes 1..3 expanded: [(ref, num, net, (x0, y0, x1, y1), (cx, cy))]."""
    import math
    import re
    import overrides
    geo = json.load(open(os.path.join(HERE, "scripts", "fp_geometry.json")))
    parts, _ = overrides.apply(overrides.load_circuit().PARTS)
    pd = {p["ref"]: p for p in parts}
    at = placement()
    full = dict(at)
    for ref in pd:
        m = re.match(r"([A-Z]+)(\d+)$", ref)
        n = int(m.group(2))
        if 200 <= n < 500 or 600 <= n < 900 or 1100 <= n < 1400:
            k = ((n // 100 - 1) % 4) if n < 900 else (n - 1000) // 100
            base = n - 100 * k
            src = "%s%d" % (m.group(1), base)
            if src in at:
                x, y, r, s = at[src]
                full[ref] = (x + DU_LANE * k, y, r, s)
    out = []
    for ref, (x, y, r, _s) in full.items():
        g = geo.get(pd[ref]["footprint_hint"])
        if not g:
            continue
        a = math.radians(r)
        for pad in g["pads"]:
            num, px, py, pw, ph, prot = pad[:6]
            if (prot + r) % 180:
                pw, ph = ph, pw
            bx, by = px * math.cos(a) + py * math.sin(a), px * math.sin(a) - py * math.cos(a)
            cx, cy = x + bx, y + by
            v = pd[ref]["pins"].get(num)
            out.append((ref, num, v[1] if v else None, (cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2), (cx, cy)))
    return out


def _dist_pt_rect(px, py, R):
    import math
    dx = max(R[0] - px, 0, px - R[2])
    dy = max(R[1] - py, 0, py - R[3])
    return math.hypot(dx, dy)


def _seg_rect(p, q, R, n=24):
    return min(_dist_pt_rect(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n, R) for i in range(n + 1))


def _free_via(pads, net, cx, cy, clr, rmin=1.2, rmax=4.0, avoid=()):
    """Nearest via position to (cx, cy) at >= clr from every pad of another net (and stub clear too)."""
    import math
    best = None
    r = rmin
    while r <= rmax and best is None:
        for j in range(24):
            a = 2 * math.pi * j / 24 + math.pi / 2
            vx, vy = round(cx + r * math.cos(a), 3), round(cy + r * math.sin(a), 3)
            if any(abs(vy - w) < 0.9 for w in avoid):
                continue
            ok = True
            for (_ref, _n, pn, R, _c) in pads:
                if pn == net or abs(R[0] - vx) > 6 or abs(R[1] - vy) > 6:
                    continue
                if _dist_pt_rect(vx, vy, R) < clr + 0.3 or _seg_rect((cx, cy), (vx, vy), R) < clr + 0.15:
                    ok = False
                    break
            if ok:
                best = (vx, vy)
                break
        r += 0.25
    return best


RISER = []


def preroutes(board):
    """HV_BUS trunk + per-channel drops, HVF connector links, anode entry stubs (all four lanes)."""
    pads = _geometry()
    bypad = {(r, n): (net, R, c) for (r, n, net, R, c) in pads}
    notes = []
    vias = []          # (x, y) of HV pre-route vias (gaps in the via keep-out bands)
    drops = []
    for k in range(4):
        for ch, base in (("F", 100), ("R", 500)):
            cb = base + 100 * k
            r1 = "R%d" % (cb + 1)
            net, R, (px, py) = bypad[(r1, "1")]
            assert net == "HV_BUS"
            v = _free_via(pads, "HV_BUS", px, py, 1.0, avoid=(libs.CAN_V0 + 0.1, libs.CAN_V1 - 0.1))
            if v is None:
                notes.append("no HV_BUS drop via position at %s" % r1)
                continue
            board.track("HV_BUS", [(px, py), v], layer="F.Cu", width=0.25)
            board.via("HV_BUS", v[0], v[1])
            board.track("HV_BUS", [v, (v[0], V_TRUNK)], layer="In2.Cu", width=0.25)
            board.via("HV_BUS", v[0], V_TRUNK)
            vias += [v, (v[0], V_TRUNK)]
            drops.append(v[0])
            # HVF: connector centre pad -> via in front of it -> In2 under the rear wall -> via -> C2 / R2
            j2 = "J%d" % (cb + 2)
            hvf = "%s%d_HVF" % (ch, k)
            _n, _R, (jx, jy) = bypad[(j2, "1")]
            c2 = bypad[("C%d" % (cb + 2), "1")][2]
            r2 = bypad[("R%d" % (cb + 2), "2")][2]
            vo = (round(jx, 3), round(jy + 1.95, 3))
            vi = (round(jx - 0.08, 3), 9.6)
            board.track(hvf, [(jx, jy), vo], layer="F.Cu", width=0.25)
            board.via(hvf, *vo)
            board.track(hvf, [vo, vi], layer="In2.Cu", width=0.25)
            board.via(hvf, *vi)
            board.track(hvf, [vi, c2], layer="F.Cu", width=0.25)
            board.track(hvf, [vi, r2], layer="F.Cu", width=0.25)
            # anode: U.FL centre pad -> straight through the mouse hole -> R_IN (R3) pad 1
            j1 = "J%d" % (cb + 1)
            an = "%s%d_A" % (ch, k)
            _n, _R, (ax, ay) = bypad[(j1, "1")]
            r3 = bypad[("R%d" % (cb + 3), "1")][2]
            board.track(an, [(ax, ay), (ax, r3[1] - 0.95), (r3[0], r3[1] - 0.33), r3], layer="F.Cu", width=0.2)
    # trunk: F.Cu along v = V_TRUNK over all drops, plus the riser to the bias block on In3
    xs = sorted(drops)
    xr = 138.6
    board.track("HV_BUS", [(xs[0], V_TRUNK), (xs[-1], V_TRUNK)], layer="F.Cu", width=0.3)
    board.via("HV_BUS", xr, V_TRUNK)
    vias.append((xr, V_TRUNK))
    tgt = bypad[("C2213", "1")]
    circ = _hv_pad_circles()
    vb = None
    for rmin in (1.2, 1.8, 2.4, 3.0, 3.6):
        vb = _free_via(pads, "HV_BUS", tgt[2][0], tgt[2][1], 1.0, rmin=rmin, rmax=rmin + 0.5)
        if vb and not any(((vb[0] - cx) ** 2 + (vb[1] - cy) ** 2) ** 0.5 < cr + 0.35 for cx, cy, cr in circ):
            break
        vb = None
    if vb:
        board.track("HV_BUS", [tgt[2], vb], layer="F.Cu", width=0.25)
        board.via("HV_BUS", *vb)
        mid = (xr, vb[1] - (xr - vb[0]) if xr - vb[0] < vb[1] - V_TRUNK else V_TRUNK)
        board.track("HV_BUS", [(xr, V_TRUNK), mid, vb], layer="In3.Cu", width=0.25)
        RISER[:] = [((xr, V_TRUNK), mid), (mid, vb)]
        vias.append(vb)
    else:
        notes.append("no via position next to C2213")
    return notes, vias


def _hv_via_bands(board, vias):
    """Via keep-outs along the HV inner-layer tracks and the trunk (the plane fan-out and the autorouter must not put
    a foreign via within the 1.0 mm HV clearance; the tool's fan-out only checks its own net class)."""
    w = 1.0 + 0.3 + 0.125 + 0.15
    i = 0
    xs = sorted({round(x, 3) for (x, y) in vias if abs(y - V_TRUNK) < 0.01})
    edges = [12.0] + [e for x in xs for e in (x - 0.9, x + 0.9)] + [314.0]
    for a, b in zip(edges[0::2], edges[1::2]):
        if b - a > 0.2:
            board.keepout("KO_HVBAND_%d" % i, polygon=[(a, V_TRUNK - w), (b, V_TRUNK - w), (b, V_TRUNK + w), (a, V_TRUNK + w)],
                          layers=("*.Cu",), tracks=False, vias=True, copper=False, pads=False, footprints=False)
            i += 1
    for seg in RISER:
        (ax, ay), (bx, by) = seg
        import math
        L = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = -uy * w, ux * w
        a0 = (ax + ux * 0.9, ay + uy * 0.9)
        b0 = (bx - ux * 0.9, by - uy * 0.9)
        board.keepout("KO_HVBAND_%d" % i, polygon=[(a0[0] + nx, a0[1] + ny), (b0[0] + nx, b0[1] + ny), (b0[0] - nx, b0[1] - ny),
                                                    (a0[0] - nx, a0[1] - ny)],
                      layers=("*.Cu",), tracks=False, vias=True, copper=False, pads=False, footprints=False)
        i += 1
    for (x, y) in vias:
        if abs(y - V_TRUNK) < 0.01 or y > V_TRUNK:
            continue
        y0, y1 = y + 0.9, V_TRUNK - w
        if y1 - y0 > 0.3:
            board.keepout("KO_HVBAND_%d" % i, polygon=[(x - w, y0), (x + w, y0), (x + w, y1), (x - w, y1)],
                          layers=("*.Cu",), tracks=False, vias=True, copper=False, pads=False, footprints=False)
            i += 1


def _wall_keepouts(board):
    """No F.Cu tracks or vias under the shield-can walls, except the anode mouse holes."""
    hw = 0.35
    for k, c in enumerate(LC):
        x0, x1 = c - libs.CAN_W / 2, c + libs.CAN_W / 2
        y0, y1 = libs.CAN_V0, libs.CAN_V1
        segs = [("F", [(x0, y1 - 0.2 - hw), (x1, y1 - 0.2 - hw), (x1, y1 + hw), (x0, y1 + hw)]),
                ("L", [(x0 - hw, y0), (x0 + 0.2 + hw, y0), (x0 + 0.2 + hw, y1), (x0 - hw, y1)]),
                ("Rt", [(x1 - 0.2 - hw, y0), (x1 + hw, y0), (x1 + hw, y1), (x1 - 0.2 - hw, y1)])]
        holes = sorted(c + d for d in libs.MOUSE_DU)
        edges = [x0] + [e for h in holes for e in (h - libs.MOUSE_W / 2, h + libs.MOUSE_W / 2)] + [x1]
        for j, (a, b) in enumerate(zip(edges[0::2], edges[1::2])):
            segs.append(("B%d" % j, [(a, y0 - hw), (b, y0 - hw), (b, y0 + 0.2 + hw), (a, y0 + 0.2 + hw)]))
        cut = []
        for name, poly in segs:
            xs_ = [p[0] for p in poly]
            ys_ = [p[1] for p in poly]
            bx0, bx1, by0, by1 = min(xs_), max(xs_), min(ys_), max(ys_)
            horiz = (bx1 - bx0) > (by1 - by0)
            gaps = sorted((c + du) if horiz else v for (du, v, rot) in libs.CLIPS
                          if (rot == 0) == horiz and (by0 - 0.5 <= v <= by1 + 0.5 if horiz else bx0 - 0.5 <= c + du <= bx1 + 0.5))
            lo, hi = (bx0, bx1) if horiz else (by0, by1)
            pieces, cur = [], lo
            for g in gaps:
                if not (lo - 2.6 < g < hi + 2.6):
                    continue
                if g - 2.6 > cur:
                    pieces.append((cur, min(hi, g - 2.6)))
                cur = max(cur, g + 2.6)
            if hi > cur:
                pieces.append((cur, hi))
            for j, (a, b) in enumerate(pieces):
                cut.append(("%s_%d" % (name, j), [(a, by0), (b, by0), (b, by1), (a, by1)] if horiz else
                            [(bx0, a), (bx1, a), (bx1, b), (bx0, b)]))
        for name, poly in cut:
            board.keepout("KO_WALL_%d_%s" % (k, name), polygon=poly, layers=("F.Cu",), tracks=True, vias=True,
                          copper=False, pads=False, footprints=False)
