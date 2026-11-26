"""Cable assemblies (W-xxx) and their wires.  Geometry in base_link mm (frames.yaml, board_envelopes.yaml,
mechanical_interfaces.md, layout_report.md corridors).  Every length is ESTIMATED FROM LAYOUT, CONFIRM ON FIRST BUILD.
"""
import math

# ---------------------------------------------------------------- geometry helpers
def chs(u, v, z=85.0):
    """RR-CHS-MAIN board (u, v) -> base_link.  Origin (-67, 80, 83), +u -> -y, +v -> +x (board_envelopes.yaml); PCB top z = 84.6."""
    return (-67.0 + v, 80.0 - u, z)


def hdb(u, v, z=37.0):
    """RR-HEAD-ACQ board (u, v) -> base_link.  Origin (83.2, 163.0, 34.5)."""
    return (83.2 + v, 163.0 - u, z)


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def plen(pts):
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def dev_rear(centre, normal, depth=45.0):
    """Terminal end of a panel device: centre on the skin minus depth along the outward normal (mechanical_interfaces.md section 6: 50 mm free depth)."""
    return tuple(c - depth * n for c, n in zip(centre, normal))


# board connector positions: nominal (u, v) from connectors.yaml position text; inboard connectors are NOT yet placed (stage 2), +-20 mm
CHS_POS = {
    "J_PWR": chs(160, 19.5), "J_PAUX": chs(148, 20), "J_CM5": chs(0, 14.5), "J_LIDAR": chs(0, 28), "J_USB_MCU": chs(12, 14), "J_USB_HEAD": chs(12, 24),
    "J_HEAD1": chs(21.5, 100), "J_HEAD2": chs(132.5, 100), "J_MOT_L": chs(0, 82), "J_MOT_R": chs(160, 82), "J_HTR": chs(143, 0),
    "J_NTC": chs(150, 10), "J_ESTOP": chs(150, 10), "J_HANDS": chs(150, 10), "J_COVER": chs(150, 10),
    "J_PANEL": chs(10, 10), "J_MODE": chs(10, 10), "J_BTN": chs(10, 10), "J_BUMP_L": chs(10, 10), "J_BUMP_R": chs(10, 10),
    "J_DOCK": chs(80, 94), "J_TOF0": chs(60, 94), "J_TOF1": chs(100, 94), "J_TOF2": chs(10, 10), "J_TOF3": chs(10, 10), "J_TOF4": chs(8, 88),
    "J_TOF5": chs(8, 88), "J_TOF6": chs(152, 88), "J_TOF7": chs(152, 88), "J_TOF8": chs(10, 10), "J_TOF9": chs(10, 10), "J_TOF10": chs(10, 10),
}

SI = "SI"
FEP = "FEP"
COAX = "COAX"
DEV = "DEV"
INS = {
    "SI": "silicone-rubber insulated, tinned fine-strand copper (class value -60 C; supplier part TBD - not in sources; UNVERIFIED). PVC excluded (not rated -40 C)",
    "FEP": "FEP/ETFE insulated, tinned stranded copper (class value -65 C; supplier part TBD - not in sources; UNVERIFIED)",
    "COAX": "50 ohm micro-coax 1.13 mm class, FEP dielectric and jacket (class value -65 C; part TBD - not in sources; UNVERIFIED)",
    "DEV": "device lead as supplied by the device maker (insulation rating not in sources)",
}

COLOUR_SCHEME = [
    ("RD", "red", "positive supply of any voltage (VBAT_RAW, HEAD_PWR_P, V5_CM5, V12_LIDAR, V5_AUX, BUS_5V, ToF +3V3, encoder 5 V, VBUS, BTN_3V3, CHG_IN)"),
    ("BK", "black", "supply return / GND of every class except the heater return"),
    ("OG", "orange", "heater supply + (HEAD_HTR_P, CHS_HTR_P)"),
    ("BN", "brown", "heater return and the heater mid-node (HEAD_HTR_N, CHS_HTR_MID)"),
    ("YE", "yellow", "hardwired safety-chain conductor (CH_N*, COIL_RTN, EN_SRC/EN_SYS, SET_CAP/K1_SET, PLUG_LINK); matches the 'yellow wire' CLIK-Mate family"),
    ("PK", "pink", "second positive supply on a cable that already has RD (V12_AUX, lamp +, HANDS_LAMP_P)"),
    ("BU", "blue", "lamp return (switched low side), RS485_DN"),
    ("WH", "white", "first signal of a pair (RS485_DP, USB D-, SCL, button contact returns)"),
    ("GN", "green", "second signal (USB D+, SDA, SYNC_P, HEAD_LOOP_OUT, SiPM LED +)"),
    ("GY", "grey", "third signal (HEAD_LOOP_RET, SYNC_N, GPIO1)"),
    ("VT", "violet", "single-ended identity/status lines (HEAD_PRES_ID, J2_PRES, XSHUT)"),
    ("bare", "tinned drain", "shield drain wire (sleeved and numbered)"),
]

CABLES = []
BYID = {}


def w(frm, fp, to, tp, net, awg, col, ins=SI, pair="", note="", to_net=None, len_mm=None, double=False, kind="wire", idx=None):
    d = dict(frm=frm, fp=str(fp), to=to, tp=str(tp), net=net, to_net=to_net or net, awg=awg, col=col, ins=ins, pair=pair, note=note, len_mm=len_mm, double=double, kind=kind)
    if idx is not None:
        d["idx"] = idx
    return d


def cable(cid, title, group, wires, path=None, end=25.0, loop=50.0, extra=0.0, length=None, basis=None, budget=None, **meta):
    if length is None:
        pl = plen(path)
        raw = pl + 2 * end + loop + extra
        length = int(math.ceil(raw / 10.0) * 10)
        basis = basis or "routed path %.0f mm + 2 x %.0f mm termination/strain relief + %.0f mm service loop%s = %.0f mm, rounded up to %d mm" % (pl, end, loop, (" + %.0f mm fixed" % extra) if extra else "", raw, length)
    c = dict(id=cid, title=title, group=group, wires=wires, length_mm=length, basis=basis, budget_mm=budget, path=path)
    c.update(meta)
    for i, x in enumerate(wires, 1):
        x["wid"] = "%s.%s" % (cid, x.pop("idx", i))
        if x["len_mm"] is None:
            x["len_mm"] = length
    CABLES.append(c)
    BYID[cid] = c
    return c


# ---------------------------------------------------------------- protection text (power_budget.md section 5, contract power.rails)
PRO = dict(
    pack="Pack BMS (15 A continuous, 25 A/10 s, 30 A/3 s, short circuit 60 A/0.5 ms) [D 12120]; 20 A blade fuse (32 V, >= 1 kA) in the bay harness within 150 mm of the coupler; optional second 20 A fuse in the cassette. Board: LM74502 bidirectional switch (no current limit), OV cut-off 16.6 V",
    chg="External supply 24 V / 3.75 A (UNVERIFIED); on board F_CHG 5 A fuse then LTC4162 input limit 4.0 A [U]. Charger limit 3.0 A. Three interlock channels open the traction chain",
    mot="VMOT eFuse TPS25982 (RILIM 237 ohm) 6.5 A +/-8 %, bridges chop at 2.68 A each, DRV8874 OCP >= 6 A; latch removes VMOT; motor brake via K2/K3 NC + 1.0 ohm",
    head_pwr="HEAD_PWR eFuse TPS259470 (RILM 2.21 k) 1.51 A; contract limit 1.5 A; head side TPS26600 eFuse 1.0 A",
    head_htr="HEAD_HTR eFuse TPS259470 (RILM 825 ohm) 4.05 A (3.6-4.4 A), contract limit 4.0 A; independent low-side bimetal cut-out on the head heater",
    head_sig="No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]",
    bus5="BUS_5V: TPS2553 (RILIM 150 k [U]) 0.15-0.20 A, short-proof; contract limit 0.15 A",
    cm5="V5_CM5 eFuse TPS259470 (RILM 665 ohm) 5.0 A (4.5-5.5 A) on the 5 V side",
    lidar="V12_LIDAR eFuse TPS259470 (RILM 2.21 k) 1.51 A (+/-10 %)",
    chshtr="CHS_HTR eFuse TPS259470 (RILM 1.10 k) 3.04 A; series bimetal cut-out in this harness (rating TBD)",
    chain="Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched",
    aux12="V12_AUX PTC F_AUX 0.35 A hold (lamps, fan, external sounder)",
    logic="V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse",
    usb="No fuse; USB ESD array at the connector; VBUS to the FT230X bridge from the carrier port",
    enc="Encoder 5 V through a 0.1 A PTC on the board (modules sheet); 10 kohm pull-ups",
    ntc="No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)",
    none="None (passive sensor / device-internal)",
)

STRAIN = dict(
    gh="Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board",
    clik="Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31)",
    mfit="Wires bundled and clipped (P-clip) within 50 mm of the housing; housing latch + board peg; heavier gauge fixed before the lighter ones; no cable weight on the header",
    minifit="Both AWG 16 wires per pole clipped within 50 mm of the housing; housing latch + board peg; cable support to the bridge tray within 80 mm",
    circ="Receptacle end: cable clamped and clipped within 50 mm of the backshell; plug end: backshell strain-relief clamp (supplier part TBD); bend radius >= 40 mm (J1) / 35 mm (J2) per parts.yaml",
    device="Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)",
)


def lbl(wire, side):
    if side == "from":
        return "%s %s > %s.%s" % (wire["wid"], wire["net"], wire["to"], wire["tp"])
    return "%s %s < %s.%s" % (wire["wid"], wire["to_net"], wire["frm"], wire["fp"])


# ================================================================ ROBOT: power and charging
cable("W-001", "Pack coupler (bay half) to main board J_PWR: pack feed with 20 A fuse and 1-to-2 splices", "robot", [
    w("CPL-B", "P", "FUSE-MAIN", "1", "PACK_P", 14, "RD", pair="P1", note="trunk, fuse within 150 mm of the coupler", len_mm=120),
    w("FUSE-MAIN", "2", "SPL-P", "1", "VBAT_RAW", 14, "RD", pair="P1", note="trunk after the fuse"),
    w("SPL-P", "2", "CHS.J_PWR", "1", "VBAT_RAW", 16, "RD", note="39-00-0078 crimp (AWG 16); 2 contacts in parallel per pole", len_mm=80),
    w("SPL-P", "3", "CHS.J_PWR", "2", "VBAT_RAW", 16, "RD", note="39-00-0078 crimp (AWG 16)", len_mm=80),
    w("CPL-B", "N", "SPL-N", "1", "GND", 14, "BK", pair="P1", note="trunk, pack negative"),
    w("SPL-N", "2", "CHS.J_PWR", "5", "GND", 16, "BK", note="39-00-0078 crimp (AWG 16)", len_mm=80),
    w("SPL-N", "3", "CHS.J_PWR", "6", "GND", 16, "BK", note="39-00-0078 crimp (AWG 16)", len_mm=80),
], path=[(-16, 0, 53), (4, -30, 58), (-5, -102, 88), (-47.5, -102, 88), (-47.5, -82, 85)], end=30, loop=40, budget=300,
    construction="Two AWG 14 trunk conductors (twisted pair) coupler to splices, then 2 x AWG 16 per pole to the Mini-Fit Jr 2x4. Corridors: under_bridge_right then right_gutter (layout_report.md section 7). Pair twisted P1 over the trunk.",
    shield="none (power, unshielded)", protection=PRO["pack"], strain=STRAIN["minifit"],
    notes="CONTRADICTION: power_budget.md assumes 2 x 0.30 m AWG 14 all the way to J_PWR, but connectors.yaml fits 39-00-0078 contacts for AWG 16 only. Resolved here as an AWG 14 trunk plus 2 x AWG 16 per pole through a crimp splice (about 1.3 mohm extra). Splice, fuse holder and SBS50 contact wire range are TBD. The fuse position leaves <= 150 mm of unfused trunk.")

cable("W-002", "Battery cassette internal wiring: pack F2 terminals to the cassette coupler half (NTC, presence link, optional cassette fuse)", "robot", [
    w("PACK", "+", "FUSE-CASS", "1", "PACK_P_CELL", 12, "RD", len_mm=150, note="insulated 6.35 mm faston, AWG 12 [modules sheet]"),
    w("FUSE-CASS", "2", "CPL-C", "P", "PACK_P", 12, "RD", len_mm=100, note="RECOMMENDED fuse, not adopted: if omitted jumper PACK_P_CELL to PACK_P"),
    w("PACK", "-", "CPL-C", "N", "GND", 12, "BK", len_mm=150, note="insulated 6.35 mm faston, AWG 12"),
    w("NTC-CASS", "a", "CPL-C", "A1", "PACK_NTC", 26, "WH", ins=FEP, len_mm=150, note="lead gauge is a PROPOSAL (not in sources)"),
    w("NTC-CASS", "b", "PACK", "-", "GND", 26, "BK", ins=FEP, len_mm=120, note="NTC returned to pack negative inside the cassette (modules sheet)"),
    w("CPL-C", "A2", "CPL-C", "N", "PACK_PRES_N", 26, "VT", ins=FEP, len_mm=60, to_net="GND", kind="link", note="presence link to pack negative inside the cassette: pulls PACK_PRES_N low when a cassette is fitted"),
], length=150, basis="cassette interior 156.5 x 109 x 104 mm (mechanical_interfaces.md section 5); lengths per wire are the cassette-internal runs (power_budget.md assumes 2 x 0.15 m AWG 12 cassette leads)", budget=150,
    construction="Purchased/assembled with the pack (BOM R01/R02). AWG 12 leads on insulated fastons. The wire list is the specification for the cassette assembler.",
    shield="none", protection="Optional cassette fuse (see FUSE-CASS); pack BMS (see W-001)", strain="Leads tied to the cassette wall within 40 mm of each terminal; terminals covered (insulated fastons); coupler half floats +-1 mm so keep 20 mm of slack",
    notes="Cassette half of the SBS50 coupler is UNVERIFIED; -20 C rating only in parts.yaml (see open items).")

cable("W-003", "Pack coupler (bay half) auxiliary contacts to main board J_PAUX", "robot", [
    w("CPL-B", "A1", "CHS.J_PAUX", "1", "PACK_NTC", 26, "WH", ins=FEP, pair="P1"),
    w("CPL-B", "A2", "CHS.J_PAUX", "2", "PACK_PRES_N", 26, "VT", ins=FEP, pair="P1"),
], path=[(-16, 0, 53), (4, -30, 58), (-5, -102, 88), (-47, -102, 88), (-47, -70, 85)], end=20, loop=40,
    construction="Two AWG 26 conductors, twisted pair, run in the same loom as W-001 (separate sleeve). J_PAUX pins 3 and 4 (GND) are NOT wired: the cassette returns NTC and presence to pack negative inside the cassette.",
    shield="none", protection=PRO["ntc"], strain=STRAIN["gh"],
    notes="OBSERVATION: the NTC/presence return then flows through the pack-negative power path (up to 12.5 A): the J_PAUX GND level can differ from board GND by about 0.1 V at full load, a few degC of NTC error. J_PAUX pins 3/4 could carry a Kelvin return if the coupler had spare aux contacts (it has two). AWG 26 for the aux contacts is a proposal; SBS50 auxiliary contact wire range is TBD.")

cable("W-004", "Charge inlet to main board J_PWR (24 V in, 0 V, plug-link pair)", "robot", [
    w("INLET", "1", "CHS.J_PWR", "3", "CHG_IN", 18, "RD", pair="P1", note="39-00-0038 crimp (AWG 18-24)"),
    w("INLET", "3", "CHS.J_PWR", "7", "GND", 18, "BK", pair="P1", note="39-00-0038 crimp"),
    w("INLET", "2", "CHS.J_PWR", "4", "PLUG_LINK", 24, "YE", pair="P2", note="chain input (CHG_COVER element): U20 plug-link channel"),
    w("INLET", "4", "CHS.J_PWR", "8", "GND", 24, "BK", pair="P2", note="LINK_B, 0 V at the board"),
], path=[(-191.6, -101.7, 88), (-155, -100, 80), (-100, -95, 72), (-60, -90, 85), (-47.5, -82, 85)], budget=250,
    construction="4 conductors: power pair (AWG 18) twisted P1, link pair (AWG 24) twisted P2, in one jacket. Corridor right_bay then right_gutter. Inlet FE contact = chassis through the receptacle flange (no wire).",
    shield="none; FE on the inlet bonds to the chassis through the flange", protection=PRO["chg"], strain=STRAIN["minifit"] + "; inlet end: clamp behind the receptacle (25 mm depth available)",
    notes="Inlet pin assignment is a PROPOSAL (external_24v_supply.md [M][U]). Layout length exceeds the 0.25 m of power_budget.md only if it comes out above 250 mm (see length column). Plug link opens even with an unpowered cable: pins 2 and 4 are linked inside the charge plug.")

cable("W-005", "Inlet cover switch to main board J_COVER", "robot", [
    w("COVER-DEV", "COM", "CHS.J_COVER", "1", "CH_N3", 24, "YE", pair="P1", note="502438-0000 crimp (AWG 24-30)"),
    w("COVER-DEV", "NC", "CHS.J_COVER", "2", "CH_N4A", 24, "YE", pair="P1", note="NC contact closed with the cover shut"),
], path=[(-191.6, -101.7, 88), (-155, -100, 80), (-100, -95, 72), (-62, -85, 85), (-57, -70, 85)], end=20,
    construction="2 x AWG 24 twisted pair, yellow safety loom. J_COVER pin 3 NC (not wired). D2HW NO lead cut back and insulated.",
    shield="none", protection=PRO["chain"], strain=STRAIN["clik"],
    notes="Chain element CHG_COVER: opens when the cover is open. Switch lead gauge/length not in sources (TBD): splice or direct crimp decided on the first build.")

# ================================================================ ROBOT: drive
for s, side, sg in (("L", "Left", 1), ("R", "Right", -1)):
    cid = "W-006" if s == "L" else "W-007"
    cable(cid, "%s gearmotor and encoder to main board J_MOT_%s" % (side, s), "robot", [
        w("MOTOR-" + s, "1", "CHS.J_MOT_" + s, "1", "MOTC_%s_A" % s, 22, "RD", ins=DEV, pair="M", note="Pololu red; motor A. AWG 22 is an assumption (power_budget.md); connectors.yaml recommends AWG 20"),
        w("MOTOR-" + s, "2", "CHS.J_MOT_" + s, "2", "MOTC_%s_B" % s, 22, "BK", ins=DEV, pair="M", note="Pololu black; motor B"),
        w("MOTOR-" + s, "3", "CHS.J_MOT_" + s, "3", "ENC_%s_5V" % s, 26, "BU", ins=DEV, pair="E", note="Pololu blue; encoder 5 V"),
        w("MOTOR-" + s, "4", "CHS.J_MOT_" + s, "4", "GND", 26, "GN", ins=DEV, pair="E", note="Pololu green; encoder GND"),
        w("MOTOR-" + s, "5", "CHS.J_MOT_" + s, "5", "ENCC_%s_A" % s, 26, "YE", ins=DEV, pair="E", note="Pololu yellow; encoder A"),
        w("MOTOR-" + s, "6", "CHS.J_MOT_" + s, "6", "ENCC_%s_B" % s, 26, "WH", ins=DEV, pair="E", note="Pololu white; encoder B"),
    ], path=[(0, sg * 42.5, 59), (8, sg * 70, 72), (15, sg * 96, 86), (15, sg * 82, 85)], budget=250,
        construction="The motor's own six-wire pigtail re-terminated into a Micro-Fit 3.0 2x3 plug housing (43025-0600). Lead length and gauge are NOT published (TBD): if the pigtail is shorter than the length column, extend with an in-line splice at the motor, never with a connector. Colours are Pololu's, not this scheme (modules sheet [D], confirm on the part).",
        shield="none (motor leads and encoder lines unshielded; ferrite + 1 nF at the board connector, layout_guidance.md)", protection=PRO["mot"] + "; " + PRO["enc"],
        strain=STRAIN["mfit"] + "; motor end: leads clipped to the motor mount within 30 mm of the exit",
        notes="Motor pins 1-2 max 2.7 A on AWG 22 (3 A table value): little margin. Motor terminals face y = %s115 (gearbox) with the cable leaving the encoder end at y = %s42.5 (parts.yaml envelope). Left/right swap is found by the first wheel-up test (connectors.yaml same_count_as)." % ("+" if s == "L" else "-", "+" if s == "L" else "-"))

# ================================================================ ROBOT: head interface (chassis side)
rcpt1 = (72.0 - 22 * 0.6246, 32.0 - 22 * 0.2901, 116.9 - 22 * 0.7251)
rcpt2 = (72.0 - 18 * 0.6246, -32.0 + 18 * 0.2901, 116.9 - 18 * 0.7251)
J1COL = [("1", "HEAD_PWR_P", 20, "RD", "P1"), ("2", "HEAD_PWR_N", 20, "BK", "P1"), ("3", "HEAD_HTR_P", 18, "OG", "P2"), ("4", "HEAD_HTR_N", 18, "BN", "P2"),
         ("5", "HEAD_LOOP_OUT", 24, "GN", "P3"), ("6", "HEAD_LOOP_RET", 24, "GY", "P3"), ("7", "HEAD_PRES_ID", 24, "VT", "")]
cable("W-008", "J1 chassis lead: main board J_HEAD1 to the J1 receptacle (150 mm lead)", "robot",
      [w("CHS.J_HEAD1", p, "J1R", p, n, a, c, pair=pr, to_net=n, note=("43030 crimp for AWG 18 not in the chassis table (AWG 20-24 only): see open items" if a == 18 else "")) for p, n, a, c, pr in J1COL],
      path=[(33, 58.5, 85), (45, 45, 95), rcpt1], end=30, loop=40, budget=250,
      construction="Custom shielded multicore: individually insulated conductors AWG 20/20/18/18/24/24/24 (pin 8 not fitted), twisted pairs P1 (1-2 power), P2 (3-4 heater), P3 (5-6 loop), pin 7 single; overall tinned-copper braid (>= 85 % coverage is a PROPOSAL) and TPE/PUR jacket rated to <= -40 C (TBD), OD <= 7.5 mm to match the receptacle backshell. Pins 3-4 must be kept out of the electronics return (contract).",
      shield="Overall braid terminated 360 degrees on the J1R receptacle shell/ground tag = chassis (contract). OPEN at the J_HEAD1 end: Micro-Fit has no shield pin; cut back and insulate the braid, no drain wire to the board.",
      protection=PRO["head_pwr"] + " (pins 1-2); " + PRO["head_htr"] + " (pins 3-4); " + PRO["head_sig"] + " (pins 5-7)", strain=STRAIN["circ"],
      notes="Lead length: connectors.yaml says 150 mm; layout gives the length column. J1 receptacle terminals sit about 22 mm behind the skin (parts.yaml depth_behind_panel). Pin 3/4 AWG 18 and the 43030-0007 (AWG 20-24) crimp range disagree: see open items. M16 8-pole contacts may accept only 0.5 mm2 (power_budget.md [U]).")
cable("W-009", "J2 chassis lead: main board J_HEAD2 to the J2 receptacle", "robot",
      [w("CHS.J_HEAD2", "1", "J2R", "1", "RS485_DP", 26, "WH", ins=FEP, pair="P1"), w("CHS.J_HEAD2", "2", "J2R", "2", "RS485_DN", 26, "BU", ins=FEP, pair="P1"),
       w("CHS.J_HEAD2", "3", "J2R", "3", "BUS_5V", 26, "RD", ins=FEP, pair="P2"), w("CHS.J_HEAD2", "4", "J2R", "4", "GND", 26, "BK", ins=FEP, pair="P2", to_net="BUS_GND"),
       w("CHS.J_HEAD2", "5", "J2R", "5", "SYNC_P", 26, "GN", ins=FEP, pair="P3", note="reserved hardware time pulse, not fitted in rev A boards"),
       w("CHS.J_HEAD2", "6", "J2R", "6", "SYNC_N", 26, "GY", ins=FEP, pair="P3"), w("CHS.J_HEAD2", "7", "J2R", "7", "J2_PRES", 26, "VT", ins=FEP, pair="P4")],
      path=[(33, -52.5, 85), (45, -45, 95), rcpt2], end=25, loop=40,
      construction="Custom shielded 4-pair cable: P1 RS-485 (120 ohm twisted pair, 1 Mbaud), P2 BUS_5V/BUS_GND, P3 SYNC (reserved), P4 J2_PRES + one spare core (pin 8, trimmed and insulated at both ends). Overall braid + jacket as W-008, OD <= 6.5 mm (parts.yaml).",
      shield="Overall braid 360 degrees on the J2R shell = chassis; OPEN at the J_HEAD2 end (GH has no shield pin).", protection=PRO["bus5"] + "; " + PRO["head_sig"], strain=STRAIN["circ"],
      notes="Termination 120 ohm is on the boards at both ends, bias at the chassis end only: this cable must not add any. AWG 26 matches connectors.yaml; ampacity for AWG 26 is not in sources (load <= 0.2 A).")

# ================================================================ ROBOT: compute, LiDAR
cm5 = (-111, 87, 66)
cable("W-010", "CM5 5.1 V feed: main board J_CM5 to the CM5 carrier 40-pin header", "robot", [
    w("CHS.J_CM5", "1", "CM5-HDR", "2", "V5_CM5", 18, "RD", pair="P1", note="two wires per pole; 43030 crimp range vs AWG 18 see open items"),
    w("CHS.J_CM5", "2", "CM5-HDR", "4", "V5_CM5", 18, "RD", pair="P1"),
    w("CHS.J_CM5", "3", "CM5-HDR", "6", "GND", 18, "BK", pair="P2"),
    w("CHS.J_CM5", "4", "CM5-HDR", "9", "GND", 18, "BK", pair="P2"),
], path=[chs(0, 14.5), (-75, 85, 88), (-100, 80, 86), cm5], budget=250,
    construction="4 x AWG 18 (two per pole, power_budget.md), twisted as two pairs. Corridors left_gutter / left_bay_over_cm5. Carrier-end termination of AWG 18 on 0.1 inch header contacts is UNRESOLVED (TBD): alternative USB-C power-only pigtail (modules sheet).",
    shield="none", protection=PRO["cm5"], strain=STRAIN["mfit"],
    notes="Check on the bench before the harness is drawn: carrier back-feed/protection behaviour and usb_max_current_enable (modules sheet [U]). Pi header pins 2/4 = 5 V, 6/9 = GND per the modules sheet.")
cable("W-011", "LiDAR supply: main board J_LIDAR to the LiDAR", "robot", [
    w("CHS.J_LIDAR", "1", "LIDAR-PWR", "1", "V12_LIDAR", 22, "RD", pair="P1"),
    w("CHS.J_LIDAR", "2", "LIDAR-PWR", "2", "GND", 22, "BK", pair="P1"),
], path=[chs(0, 28), (-95, 69, 108), (-118, 62, 116), (-140, 45, 150), (-150, 10, 152)], budget=400,
    construction="2 x AWG 22 twisted pair. Corridor hump_side_left, over the hump side to the LiDAR pad (-150, 0, 150). LiDAR connector exit and pinout are UNVERIFIED (parts.yaml): TBD.",
    shield="none", protection=PRO["lidar"], strain=STRAIN["mfit"] + "; LiDAR end: strain relief per the LiDAR connector (TBD)",
    notes="power_budget.md assumes 2 x 0.40 m AWG 22. Inrush against the 1.5 A limit is an open item (lidar.md).")
cable("W-012", "LiDAR Ethernet: LiDAR pigtail to the CM5 carrier RJ45 (purchased)", "robot", [
    w("LIDAR-ETH", "TXP", "CM5-RJ45", "1", "ETH_TXP", 26, "per pigtail", ins=DEV, pair="P1"),
    w("LIDAR-ETH", "TXN", "CM5-RJ45", "2", "ETH_TXN", 26, "per pigtail", ins=DEV, pair="P1"),
    w("LIDAR-ETH", "RXP", "CM5-RJ45", "3", "ETH_RXP", 26, "per pigtail", ins=DEV, pair="P2"),
    w("LIDAR-ETH", "RXN", "CM5-RJ45", "6", "ETH_RXN", 26, "per pigtail", ins=DEV, pair="P2"),
], path=[(-150, 0, 152), (-140, 45, 150), (-118, 62, 116), (-102, 75, 90), cm5],
    construction="Purchased LiDAR pigtail (RJ45 or M12, TBD) straight to the carrier RJ45; not routed through the main board (lidar.md). Wire colours and gauge are the vendor's (TBD). If the pigtail is shorter than the length column, use a shielded Cat5e/6 RJ45 coupler is NOT allowed (no extra connector in the chain): order the longer pigtail.",
    shield="Vendor cable shield (TBD)", protection=PRO["none"], strain="LiDAR end: per pigtail; RJ45 end: boot plus tie to the carrier bracket within 50 mm",
    notes="Length is the minimum pigtail length needed along corridors hump_side_left and left_bay_over_cm5. Pigtail length is not in the sources.")
for cid, nm, jb, pins, pos in (("W-013", "chassis link (MCU CDC)", "CHS.J_USB_MCU", [("2", "2", "MCUC_USB_DM", "WH"), ("3", "3", "MCUC_USB_DP", "GN"), ("4", "4", "GND", "BK")], chs(12, 14)),
                               ("W-014", "head link (FT230X)", "CHS.J_USB_HEAD", [("1", "1", "HUSB_VBUS", "RD"), ("2", "2", "HUSBC_DM", "WH"), ("3", "3", "HUSBC_DP", "GN"), ("4", "4", "GND", "BK")], chs(12, 24))):
    tgt = "CM5-USB1" if cid == "W-013" else "CM5-USB2"
    ws = [w(jb, fp, tgt, tp, n, 28, c, ins=FEP, pair=("P1" if n.endswith(("DM", "DP")) else "")) for fp, tp, n, c in pins]
    ws.append(w(jb, "5", tgt, "SH", "USB_SHLD", 28, "bare", ins=FEP, kind="shield", note="drain wire to the board pin 5 (USB_SHLD: 1 Mohm || 10 nF to GND on the board, R200/C148) and to the USB-A plug shell"))
    cable(cid, "USB 2.0 FS %s: main board %s to the CM5 carrier USB-A" % (nm, jb.split(".")[1]), "robot", ws,
          path=[pos, (-75, 75, 88), (-100, 80, 86), cm5], end=20,
          construction="USB 2.0 full-speed shielded cable: D+/D- 90 ohm twisted pair, %s, AWG 28 conductors (connectors.yaml), foil/braid + drain. USB-A plug (part TBD) on the carrier end. %s" % (
              "VBUS conductor NOT fitted (board pin 1 is NC; the MCU is self-powered): leave the plug VBUS pin unconnected" if cid == "W-013" else "VBUS and GND conductors included",
              "No hub: one cable per port so a fault on one link cannot take the other down."),
          shield="Foil/braid: drain to board pin 5 (USB_SHLD -> 1 Mohm || 10 nF), plug shell bonds to the carrier shell. Two terminations by design: one DC-isolated by the RC at the board.",
          protection=PRO["usb"], strain=STRAIN["gh"] + "; USB-A end: boot plus tie within 50 mm",
          notes="Both USB-A ports of the CM5-IO-BASE-A are used: no port for a wired service adapter (CCR-E10, IB-07 open).")

# ================================================================ ROBOT: chain and operator
pe = dev_rear((-120, -98, 130.9), (-0.0173, -0.3413, 0.9398))
cable("W-015", "E-stop (two poles) to main board J_ESTOP", "robot", [
    w("ESTOP-DEV", "NC1-a", "CHS.J_ESTOP", "1", "CH_N1", 24, "YE", pair="P1", note="pole A, chain high side"),
    w("ESTOP-DEV", "NC1-b", "CHS.J_ESTOP", "2", "CH_N2", 24, "YE", pair="P1"),
    w("ESTOP-DEV", "NC2-a", "CHS.J_ESTOP", "3", "COIL_RTN", 24, "YE", pair="P2", note="pole B, coil return"),
    w("ESTOP-DEV", "NC2-b", "CHS.J_ESTOP", "4", "GND", 24, "YE", pair="P2"),
], path=[chs(150, 10), (-67, -78, 90), pe],
    construction="4 x AWG 24 in two twisted pairs (pole A, pole B), yellow, in the safety loom. An external stop provision (E10) goes in series with BOTH poles at the J_ESTOP end (CCR/E10), no board change.",
    shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="Each pole is its own pair so a short between poles needs two failures. Chain wire short to +12 V is an undetected latent fault: keep this loom away from VBAT conductors (chassis_safety_chain.md #8, #31). Contact-block terminal numbers TBD.")
pm = dev_rear((-135, 98, 130.3), (-0.0793, 0.4098, 0.9087))
cable("W-016", "Mode selector OFF/SERVICE/RUN to main board J_MODE", "robot", [
    w("MODE-DEV", "EN-a", "CHS.J_MODE", "1", "EN_SRC", 24, "YE", pair="P1", note="EN contact: NC block, closed in SERVICE and RUN; opens the pack switch and regulators in OFF"),
    w("MODE-DEV", "EN-b", "CHS.J_MODE", "2", "EN_SYS", 24, "YE", pair="P1"),
    w("MODE-DEV", "RUN-a", "CHS.J_MODE", "3", "CH_N0", 24, "YE", pair="P2", note="RUN contact: NO block, closed in RUN only (chain element MODE_RUN)"),
    w("MODE-DEV", "RUN-b", "CHS.J_MODE", "4", "CH_N1", 24, "YE", pair="P2"),
], path=[chs(10, 10), (-67, 76, 90), pm],
    construction="4 x AWG 24, two twisted pairs, yellow safety loom. J_MODE pins 5, 6 not wired.", shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="The selector assembly XB5AD33 has 2 NO blocks: the OFF-side block must be exchanged for a ZBE-102 NC (UNVERIFIED, modules sheet).")
ph = dev_rear((-172, -97, 125.2), (-0.1899, -0.415, 0.8898))
cable("W-017", "HANDS-ON button and lamp to main board J_HANDS", "robot", [
    w("HANDS-DEV", "NC-a", "CHS.J_HANDS", "1", "CH_N2", 24, "YE", pair="P1"),
    w("HANDS-DEV", "NC-b", "CHS.J_HANDS", "2", "CH_N3", 24, "YE", pair="P1"),
    w("HANDS-DEV", "LAMP+", "CHS.J_HANDS", "3", "HANDS_LAMP_P", 24, "PK", pair="P2", note="lamp fed from the chain node CH_N2 (lit = upstream live, contact open)"),
    w("HANDS-DEV", "LAMP-", "CHS.J_HANDS", "4", "HANDS_LAMP_K", 24, "BU", pair="P2"),
], path=[chs(150, 10), (-67, -78, 90), ph],
    construction="4 x AWG 24; contact pair yellow (safety loom), lamp pair PK/BU in the same loom (lamp +12 V comes from the chain node: keep it in the safety loom). J_HANDS pin 5 not wired.", shield="none",
    protection=PRO["chain"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"], notes="Lamp 12 V, <= 20 mA. Exact XB5 reference TBD (UNVERIFIED).")
pr = dev_rear((-172, 97, 125.2), (-0.1899, 0.415, 0.8898))
pz = dev_rear((-84, -112, 122), (0.0491, -0.5205, 0.8524))
cable("W-018", "REARM/Start button and lamp: main board J_BTN to the REARM button (Y-loom trunk, left deck)", "robot", [
    w("REARM-DEV", "SET-a", "CHS.J_BTN", "1", "SET_CAP", 24, "YE", pair="P1", note="NO 1: capacitor-coupled latch set path (SAFETY)"),
    w("REARM-DEV", "SET-b", "CHS.J_BTN", "2", "K1_SET", 24, "YE", pair="P1"),
    w("SPL-BTN3", "1", "CHS.J_BTN", "3", "BTN_3V3", 24, "RD", len_mm=60, note="shared by REARM aux contact and PAUSE contact"),
    w("REARM-DEV", "AUX-a", "SPL-BTN3", "2", "BTN_3V3", 24, "RD", note="NO 2 supply side"),
    w("REARM-DEV", "AUX-b", "CHS.J_BTN", "4", "REARM_BTN_RAW", 24, "WH", note="NO 2: REARM_BTN to the MCU (isolated from the set path)"),
    w("SPL-BTN6", "1", "CHS.J_BTN", "6", "V12_AUX", 24, "PK", len_mm=60, note="shared lamp supply of REARM and PAUSE"),
    w("REARM-DEV", "LAMP+", "SPL-BTN6", "2", "V12_AUX", 24, "PK"),
    w("REARM-DEV", "LAMP-", "CHS.J_BTN", "7", "LAMP_REARM_K", 24, "BU"),
], path=[chs(10, 10), (-67, 76, 90), pr],
    construction="8 x AWG 24, yellow safety loom for pins 1-2; splices SPL-BTN3 and SPL-BTN6 sit 60 mm from the J_BTN housing and branch to the PAUSE button (W-019). Pins 3 and 6 each carry ONE wire at the connector; the splice does the 1-to-2. J_BTN pin 5 and 8 go to the PAUSE branch.",
    shield="none", protection=PRO["chain"] + "; lamps: " + PRO["aux12"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="A short between J_BTN 1-2 permanently sets the set path: the latch must still not set after an element cycles (chassis_safety_chain.md procedure 7). Splice parts TBD.")
cable("W-019", "PAUSE/Stop button and lamp: Y-loom branch from the J_BTN splices to the PAUSE button (right deck)", "robot", [
    w("PAUSE-DEV", "NO-a", "SPL-BTN3", "3", "BTN_3V3", 24, "RD", note="branch from the shared BTN_3V3 splice"),
    w("PAUSE-DEV", "NO-b", "CHS.J_BTN", "5", "PAUSE_BTN_RAW", 24, "WH", note="runs the full length from J_BTN"),
    w("PAUSE-DEV", "LAMP+", "SPL-BTN6", "3", "V12_AUX", 24, "PK", note="branch from the shared lamp splice"),
    w("PAUSE-DEV", "LAMP-", "CHS.J_BTN", "8", "LAMP_PAUSE_K", 24, "BU", note="runs the full length from J_BTN"),
], path=[chs(10, 10), (-57, 0, 100), (-67, -72, 98), pz], loop=60,
    construction="4 x AWG 24 branch: the board-end conductors (pins 5, 8) run the whole way, the splice stubs branch off 60 mm from J_BTN. Route over the board top under the saddle cover (z 85..105, 20.4 mm free): the battery hump front wall blocks every other crossing.",
    shield="none", protection=PRO["aux12"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="LAYOUT FINDING: the PAUSE button is on the RIGHT deck but J_BTN (REARM + PAUSE share one connector) is in the REAR-LEFT corner, so a PAUSE branch must cross the whole board. Recommendation to the board layout (stage 2): put the PAUSE contacts on a separate connector in the rear-right cluster.")
cable("W-020", "Head dock switch to main board J_DOCK", "robot", [
    w("DOCK-DEV", "COM", "CHS.J_DOCK", "1", "CH_N4", 24, "YE", pair="P1"),
    w("DOCK-DEV", "NC", "CHS.J_DOCK", "3", "CH_N5", 24, "YE", pair="P1"),
], path=[chs(80, 94), (40, 0, 75), (40, 87.5, 40), (-3, 87.5, 23)],
    construction="2 x AWG 24 twisted pair, yellow. Corridor front_bay then along the left receiver channel to the switch behind the channel (-3, 87.5, 23). J_DOCK pin 2 not wired. Switch NC wired so the loop is closed only when the shoe presses it.",
    shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; switch end: clip to the channel within 30 mm, keep clear of the shoe sweep (head removal sweep +x is free per layout_report.md)",
    notes="Dock switch is in the head-removal path region: protect the leads from the shoe tip (x = 4.0).")
for cid, side, jc, dev, a, b, cpt, sg in (("W-021", "L", "CHS.J_BUMP_L", "BUMP-L-DEV", "CH_N7", "CH_N8A", (-236.6, 103, 66), 1), ("W-022", "R", "CHS.J_BUMP_R", "BUMP-R-DEV", "CH_N8A", "CH_N8", (-236.6, -103, 66), -1)):
    if sg == 1:
        pth = [chs(10, 10), (-95, 69, 105), (-118, 66, 105), cpt]
    else:
        pth = [chs(10, 10), (-57, 0, 100), (-67, -72, 95), (-100, -80, 70), (-155, -85, 65), cpt]
    cable(cid, "Body bumper %s to main board J_BUMP_%s" % ("left" if sg == 1 else "right", side), "robot", [
        w(dev, "COM", jc, "1", a, 24, "YE", pair="P1"), w(dev, "NC", jc, "2", b, 24, "YE", pair="P1")], path=pth,
        construction="2 x AWG 24 twisted pair, yellow. %s" % ("Corridor hump_side_left then the left rear quarter." if sg == 1 else "Crosses the board top (z 85..105) to the rear-right corner, then right_bay to the right rear quarter."),
        shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; switch end: clip to the bumper band bracket within 30 mm with a service loop that allows the band stroke (>= 8 mm)",
        notes=("LAYOUT FINDING: J_BUMP_R sits in the rear-LEFT corner but its switch is on the right: the cable crosses the board. J_BUMP_L/R are interchangeable (series contacts) but both are in the same corner; move one to the rear-right cluster in stage 2." if sg == -1 else "Bumper switch D2HW NO lead cut back and insulated."))

# ================================================================ ROBOT: panel board and sounder
cable("W-023", "RR-PANEL: main board J_PANEL to RR-PANEL J1 (straight 1:1)", "robot",
      [w("CHS.J_PANEL", str(i), "PNL.J1", str(i), n, 26, c, ins=FEP, pair=pr)
       for i, n, c, pr in ((1, "V5_AUX", "RD", ""), (2, "V12_AUX", "PK", ""), (3, "GND", "BK", ""), (4, "LED_READY_K", "GN", ""), (5, "LED_MOVING_K", "BU", ""), (6, "LED_HOLD_K", "VT", ""),
                           (7, "LED_FAULT_K", "GY", ""), (8, "LED_CHARGE_K", "WH", ""), (9, "BUZ_N", "BN", ""), (10, "GND", "BK", ""))],
      path=[chs(10, 10), (-70, 73, 100), (-80, 97, 110)], end=20,
      construction="10 x AWG 26, round multicore jacket, pin n to pin n (circuit.py checks the 1:1 order). The two GND conductors (3 and 10) share one colour: distinguished by the printed wire numbers. Corridor hump_side_left.",
      shield="none", protection=PRO["aux12"] + "; " + PRO["logic"], strain=STRAIN["gh"],
      notes="RR-PANEL J1 is JST SM10B-GHS-TB side entry on the bottom side (4.25 mm against the 3 mm bottom limit, CCR-E08(d)).")
cable("W-024", "OPTIONAL external 22 mm sounder: RR-PANEL J2 to the panel sounder", "robot", [
    w("PNL.J2", "1", "SOUNDER-EXT", "+", "V12_AUX", 26, "PK", pair="P1"), w("PNL.J2", "2", "SOUNDER-EXT", "-", "BUZ_N", 26, "BU", pair="P1")],
    path=[(-80, 97, 110), (-80, 97, 128)], end=20, loop=40,
    construction="2 x AWG 26 twisted pair (JST GH contacts take AWG 26-30). The sounder position is not in the sources (assumed within 100 mm of the annunciator).", shield="none", protection=PRO["aux12"] + "; sounder <= 100 mA", strain=STRAIN["gh"] + "; " + STRAIN["device"],
    notes="Recommended by the panel circuit (on-board piezo about 60 dB at 1 m). No part verified (TBD).")

# ================================================================ ROBOT: ToF carriers
TOFMAP = {  # firmware id -> (carrier id, frames name, sensor position, via points from the board connector)
    0: ("CLIFF_FL", (46.0, 109.5, 31.0), [(45, 20, 70), (46, 100, 40)]),
    1: ("CLIFF_FR", (46.0, -109.5, 31.0), [(45, -20, 70), (46, -100, 40)]),
    2: ("CLIFF_RL", (-241.7, 78.3, 41.0), [(-95, 69, 105), (-118, 66, 100)]),
    3: ("CLIFF_RR", (-241.7, -78.3, 41.0), [(-57, 0, 100), (-67, -72, 95), (-100, -80, 70), (-155, -85, 60)]),
    4: ("LOOK_LO", (1.5, 91.0, 162.0), [(10, 85, 110)]),
    5: ("LOOK_LI", (-247.6, 65.6, 100.0), [(-5, 100, 88), (-69, 102, 90), (-118, 66, 105)]),
    6: ("LOOK_RI", (-247.6, -65.6, 100.0), [(-5, -100, 88), (-69, -102, 90), (-118, -66, 105)]),
    7: ("LOOK_RO", (1.5, -91.0, 162.0), [(10, -85, 110)]),
    8: ("REAR_L", (-249.3, 82.0, 80.0), [(-95, 69, 105), (-118, 66, 100)]),
    9: ("REAR_C", (-236.0, 0.0, 158.0), [(-95, 69, 108), (-118, 62, 116), (-140, 40, 150)]),
    10: ("REAR_R", (-249.3, -82.0, 80.0), [(-57, 0, 100), (-67, -72, 95), (-100, -80, 70), (-155, -85, 65)]),
}
TOFCOL = [("1", "3V3", "+3V3", "RD", "P1"), ("2", "GND", "GND", "BK", "P1"), ("3", "SDA_C", "SDA", "GN", "P2"), ("4", "SCL_C", "SCL", "WH", "P2"), ("5", "XSHUT_C", "XSHUT", "VT", "P3"), ("6", "GPIO1", "GPIO1", "GY", "P3")]
for n in range(11):
    nm, spos, via = TOFMAP[n]
    cid = "W-%03d" % (30 + n)
    wires = []
    for pin, sfx, cname, col, pr in TOFCOL:
        wires.append(w("CHS.J_TOF%d" % n, pin, "TOF%d.J1" % n, pin, "TOF%d_%s" % (n, sfx) if sfx != "GND" else "GND", 28, col, ins=FEP, pair=pr, to_net=cname,
                       double=(pin == "2"), note=("drain wire shares this crimp (shield bonded at the board end only)" if pin == "2" else "")))
    note = "ToF %s (firmware id %d). " % (nm, n)
    if n in (5, 6):
        note += "ASSUMED sensor position: frames.yaml has only two look-AHEAD sensors (tof_look_fl/fr at the grip cheeks) and two look-BEHIND sensors (tof_look_rl/rr at the tail), while the contract and firmware define four look-ahead sensors (LOOK_LO/LI/RI/RO). LOOK_LO/RO are mapped to look_fl/fr and LOOK_LI/RI to look_rl/rr (the only remaining 'look' positions): resolve before the harness is cut. "
    cable(cid, "ToF carrier %s (RR-TOF #%d): main board J_TOF%d to the carrier J1" % (nm, n, n), "robot", wires, path=[CHS_POS["J_TOF%d" % n]] + via + [spos], end=15, loop=30, budget=300,
          construction="6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).",
          shield="Foil + drain: drain crimped in J_TOF%d pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD)." % n,
          protection=PRO["logic"], strain=STRAIN["gh"] + "; carrier end: cable clamp to the window bracket within 30 mm", notes=note +
          "CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.")

# ================================================================ ROBOT: heaters, sensors, clamp
cable("W-041", "Chassis/bay heater with its bimetal cut-out: main board J_HTR to the heater plate", "robot", [
    w("CHS.J_HTR", "1", "HTR-CHS", "1", "CHS_HTR_P", 20, "OG", note="43030-0007 crimp (AWG 20-24)"),
    w("HTR-CHS", "2", "CUT-CHS", "1", "CHS_HTR_MID", 20, "BN", note="element end to the cut-out, on the plate (low side)"),
    w("CUT-CHS", "2", "CHS.J_HTR", "2", "GND", 20, "BN", note="return through the cut-out"),
], path=[chs(143, 0), (-100, -70, 76), (-120, -70, 50), (-119, -40, 41)], budget=300,
    construction="3 x AWG 20 silicone. The independent bimetal cut-out is in series in this harness, on the heater plate (CCR-E08(e)); element 7.2 ohm, 20 W. The cut-out must be rated for >= 3.04 A at 14.4 V DC (TBD part).",
    shield="none", protection=PRO["chshtr"], strain=STRAIN["mfit"] + "; plate end: leads secured with high-temperature tape/clips to the plate within 30 mm",
    notes="Heater pad leads are not in the sources. The return conductor goes to GND (not a separate heater return net on this board).")
cable("W-042", "Bay NTC and pack-surface NTC to main board J_NTC", "robot", [
    w("NTC-BAY", "a", "CHS.J_NTC", "1", "NTC_BAY", 26, "WH", ins=FEP, pair="P1"), w("NTC-BAY", "b", "CHS.J_NTC", "2", "GND", 26, "BK", ins=FEP, pair="P1"),
    w("NTC-PACKSURF", "a", "CHS.J_NTC", "3", "NTC_PACK", 26, "GN", ins=FEP, pair="P2"), w("NTC-PACKSURF", "b", "CHS.J_NTC", "4", "GND", 26, "BK", ins=FEP, pair="P2")],
    path=[chs(150, 10), (-100, -70, 76), (-120, -57, 65)], end=20,
    construction="2 twisted pairs AWG 26. NTCs 10 kohm B3435 (parts TBD). The two GND returns stay separate (pins 2 and 4) so the pair stays Kelvin.", shield="none", protection=PRO["ntc"], strain=STRAIN["gh"],
    notes="NTC positions are not given beyond 'beside the heater' and 'pack surface'; length is for the bay near the heater plate.")
cable("W-044", "OPTIONAL external bus-clamp resistor: DNP pads W1 to the resistor", "robot", [
    w("CHS.W1", "1", "CLAMP-EXT", "1", "CLAMP_F", 20, "RD"), w("CHS.W1", "2", "CLAMP-EXT", "2", "CLAMP_R", 20, "BK")],
    path=[chs(80, 50), (40, 0, 80), (49, -10, 70)], end=20, loop=40,
    construction="2 x AWG 20 soldered to the 2.5 mm pads. Resistor value TBD (in parallel with the on-board 2 x 9.1 ohm = 4.55 ohm; the F_CLAMP PTC 1.1 A hold sits in series).",
    shield="none", protection="F_CLAMP PTC 1.1 A hold, 33 V (circuit.py); peak 3.4 A for tens of ms (power_budget.md s5)", strain=STRAIN["device"],
    notes="CONTRADICTION: parts.yaml puts a 50 W bus-clamp resistor in the front bay, board_envelopes.yaml lists a 'bus-clamp resistor' on the right edge rear, power_budget.md treats the clamp as on-board, and circuit.py has only DNP wire pads W1. Not fitted unless the electronics lead decides.")

# ================================================================ HEAD: pigtails
hp = (71.7, 87.5, 39.0)
cable("W-101", "Head J1 captive pigtail: head board J2001 to the J1 plug", "head", [
    w("HEAD.J2001", p, "J1P", p, n, a, c, pair=pr, note=("terminal: Micro-Fit 43030 'AWG 18-24 variant' (head circuit.py note)" if a == 18 else "")) for p, n, a, c, pr in J1COL] +
    [w("HEAD.TP2004", "1", "J1P", "SH", "SHLD_J1", 24, "bare", kind="shield", idx="S", note="shield drain to the board pad TP2004 (SHLD_J1: 1 Mohm || 10 nF to FRAME); braid also 360 degrees in the plug backshell")],
    path=[hdb(75.5, 6.0), hp], end=25, loop=20, extra=200.0,
    basis="inside the head: board J2001 to the rear-wall port = 17.6 mm path + 2 x 25 mm + 20 mm; outside: 200 mm free length (mechanical_interfaces.md allows 150..200; straight-line port to plug rear is 142 mm, plus bends at 40 mm radius, so 150 mm is too short)", budget=350,
    construction="Same construction as W-008 (shielded multicore, twisted pairs P1 power, P2 heater, P3 loop), captive: sealed strain relief in the head rear wall at (71.7, 87.5, 39), cable leaves toward -x/+z, clipped to the shoe root. OD <= 7.5 mm.",
    shield="Braid: 360 degrees to the J1 plug backshell (-> chassis through the mated shell) AND drain wire to the head board pad TP2004. This is the contract: hard bond at the chassis, 1 Mohm || 10 nF at the head.",
    protection=PRO["head_pwr"] + " (pins 1-2); " + PRO["head_htr"] + " (pins 3-4); " + PRO["head_sig"], strain="Sealed strain-relief gland in the rear wall (inside the head wall); plug backshell clamp; clip to the shoe root; head cover 0.9 mm clearance must not trap the cable",
    notes="power_budget.md assumes 2 x 0.35 m of pigtail. The loop is potential-free: no conductor of pins 5-6 may touch the shield or any other pin. CCR-HE-02: J2001 header height 8 mm zone open.")
cable("W-102", "Head J2 captive pigtail: head board J2501 to the J2 plug (plug link pin 7 to pin 4)", "head", [
    w("HEAD.J2501", "1", "J2P", "1", "RS485_DP", 26, "WH", ins=FEP, pair="P1"), w("HEAD.J2501", "2", "J2P", "2", "RS485_DN", 26, "BU", ins=FEP, pair="P1"),
    w("HEAD.J2501", "3", "J2P", "3", "BUS_5V", 26, "RD", ins=FEP, pair="P2"), w("HEAD.J2501", "4", "J2P", "4", "BUS_GND", 26, "BK", ins=FEP, pair="P2"),
    w("HEAD.J2501", "5", "J2P", "5", "SYNC_P", 26, "GN", ins=FEP, pair="P3"), w("HEAD.J2501", "6", "J2P", "6", "SYNC_N", 26, "GY", ins=FEP, pair="P3"),
    w("HEAD.J2501", "7", "J2P", "7", "J2_PRES", 26, "VT", ins=FEP, pair="P4"),
    w("J2P", "7", "J2P", "4", "J2_PRES", 26, "VT", ins=FEP, to_net="BUS_GND", kind="link", idx="L", len_mm=20, note="J2_PRES plug link inside the plug (contract); keep R2502 DNP"),
    w("HEAD.TP2501", "1", "J2P", "SH", "SHLD_J2", 26, "bare", ins=FEP, kind="shield", idx="S", note="shield drain to pad TP2501 (SHLD_J2); braid 360 degrees in the plug backshell")],
    path=[hdb(250.5, 6.0), (71.7, -87.5, 39.0)], end=25, loop=20, extra=200.0,
    basis="inside the head: board J2501 to the rear-wall port = 17.6 mm + 2 x 25 mm + 20 mm; outside: 200 mm free length (150..200 allowed; port to plug rear 142 mm straight)",
    construction="Same as W-009: shielded 4-pair, 7 conductors + link. Captive, sealed strain relief at (71.7, -87.5, 39).", shield="As W-101 with TP2501 / J2P backshell.", protection=PRO["bus5"] + "; " + PRO["head_sig"],
    strain="Sealed strain-relief gland in the rear wall; plug backshell clamp; clip to the shoe root", notes="J2_PRES link: pin 7 and pin 4 are linked inside the plug; the chassis sees J2_PRES low when mated.")

# ================================================================ HEAD: internal
cable("W-103", "Head heater film, bimetal cut-out and spreader NTC: head board J2601 to the heater assembly", "head", [
    w("HEAD.J2601", "1", "HEAD-HEATER", "1", "HTR_SW", 18, "OG", note="43030 'AWG 18-24 variant' crimp; up to 4.4 A trip"),
    w("HEAD.J2601", "3", "SPL-HCUT", "1", "HTR_CUT", 24, "VT", note="cut-out sense (CUTOUT_SENSE node between element and cut-out)"),
    w("HEAD-HEATER", "2", "SPL-HCUT", "2", "HTR_CUT", 18, "BN", note="element end to the junction"),
    w("SPL-HCUT", "3", "HEAD-CUTOUT", "1", "HTR_CUT", 18, "BN"),
    w("HEAD-CUTOUT", "2", "HEAD.J2601", "2", "HEAD_HTR_N", 18, "BN", note="heater return through the low-side cut-out; HEAD_HTR_N never touches ground on the board"),
    w("NTC-SPR", "a", "HEAD.J2601", "4", "NTC_HTR", 24, "WH", ins=FEP, pair="P1"), w("NTC-SPR", "b", "HEAD.J2601", "5", "GND", 24, "BK", ins=FEP, pair="P1")],
    path=[hdb(88, 8), (76, 87.5, 30), (74, 87.5, 24)], end=20, loop=30, budget=350,
    construction="Heater circuit AWG 18 pair (supply and return twisted) plus AWG 24 sense and an AWG 26 NTC pair. Assembly (per J2601): HTR_SW -> 4.8 ohm element -> CUTOUT_SENSE -> bimetal cut-out (low side) -> HEAD_HTR_N. Tail comes up the rear chimney at y = +87.5. J2601 pin 6 not wired.",
    shield="none inside the shielded head", protection=PRO["head_htr"] + "; cut-out status reads 'tripped' when the feed is off (by design)", strain="Leads clipped to the spreader with Kapton/high-temperature tape within 20 mm of the film tail",
    notes="Heater film, cut-out and NTC parts are not in the sources (TBD). CCR-HE-02 (connector height) open.")
for cid, nm, jref, dev, sw in (("W-104", "front", "J2002", "RAIL-F", (184.2, 0.0, 21.0)), ("W-105", "left", "J2003", "RAIL-L", (131.2, 168.5, 21.0)), ("W-106", "right", "J2004", "RAIL-R", (131.2, -168.5, 21.0))):
    pos = {"J2002": hdb(163, 90), "J2003": hdb(155, 90), "J2004": hdb(171, 90)}[jref]
    via = {"front": [], "left": [(180, 8, 30), (180, 160, 25)], "right": [(180, -8, 30), (180, -160, 25)]}[nm]
    nets = {"J2002": ("HEAD_LOOP_OUT", "LOOP_A"), "J2003": ("LOOP_A", "LOOP_B"), "J2004": ("LOOP_B", "LOOP_C")}[jref]
    cable(cid, "Head rail switch %s (series element of the interlock loop): head board %s to the switch" % (nm, jref), "head", [
        w(dev, "COM", "HEAD." + jref, "1", nets[0], 26, "GN", ins=FEP, pair="P1"), w(dev, "NC", "HEAD." + jref, "2", nets[1], 26, "GY", ins=FEP, pair="P1")],
        path=[pos] + via + [sw], end=15, loop=30,
        construction="2 x AWG 26 twisted pair in the front wall channel (JST GH contacts take AWG 26-30). Connector pins 3 and 4 (AUX_N/AUX_GND zone read-back) are NOT wired: the D2HW is single-pole and its NO throw is not potential-free from the loop (CCR-HE-04). The NO lead is cut back and insulated.",
        shield="none (inside the shielded head)", protection=PRO["head_sig"], strain="Clip in the front wall channel every 50 mm; switch end clipped within 20 mm",
        notes="Loop is a potential-free series chain; see the loop diagram in cables.md.")
cable("W-107", "Head lid (light-leak) interlock switch: head board J2201 to the lid switch", "head", [
    w("LID-SW", "a", "HEAD.J2201", "1", "LID_IN", 26, "WH", ins=FEP, pair="P1"), w("LID-SW", "b", "HEAD.J2201", "2", "GND", 26, "BK", ins=FEP, pair="P1")],
    length=200, basis="PLACEHOLDER: switch position and part are not in the sources; 200 mm assumed (J2201 is on the front edge, board_envelopes BIAS zone)",
    construction="2 x AWG 26 twisted pair. Bench bypass is the solder jumper JP2201 on the board (record in the build sheet).", shield="none", protection=PRO["head_sig"], strain="Clip every 50 mm; switch end clipped within 20 mm",
    notes="Switch type/location TBD - not in sources.")
for k in range(4):
    jr = "J%d01" % (10 + k)
    cable("W-%d" % (108 + k), "Head lane %d auxiliary pigtail: head board %s to the SiPM carrier aux" % (k, jr), "head", [
        w("CARR-AUX%d" % k, "1", "HEAD." + jr, "1", "NTC_SIPM%d" % k, 28, "WH", ins=FEP, pair="P1"), w("CARR-AUX%d" % k, "2", "HEAD." + jr, "2", "GND", 28, "BK", ins=FEP, pair="P1"),
        w("CARR-AUX%d" % k, "3", "HEAD." + jr, "3", "L%d_LED_A" % k, 28, "GN", ins=FEP, pair="P2"), w("CARR-AUX%d" % k, "4", "HEAD." + jr, "4", "L%d_LED_K" % k, 28, "BN", ins=FEP, pair="P2"),
        w("CARR-AUX%d" % k, "5", "HEAD." + jr, "5", "L%d_AUX3V3" % k, 28, "RD", ins=FEP, pair="P3"), w("CARR-AUX%d" % k, "6", "HEAD." + jr, "6", "GND", 28, "BK", ins=FEP, pair="P3")],
        length=35, basis="mechanical interfaces: pigtails < 35 mm from the rear edge into the chimney (drop 17-25 mm + 11 mm lateral = at most 28 mm routed + 7 mm termination): 35 mm cut length is the maximum",
        construction="6 x AWG 28 flat/round micro-cable, 3 twisted pairs (NTC, LED, 3V3). The lane SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06) is the lane temperature sensor. LED and 3V3 pins feed an optional pulser/active sensor.",
        shield="none; inside the lane shield can region: keep leads < 35 mm", protection=PRO["ntc"], strain="Adhesive/tack at the carrier end; no loop > 10 mm (pickup, IB-23)",
        notes="Carrier connector TBD (not in sources).")
LANE_CH = ["F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"]
for c, ch in enumerate(LANE_CH):
    ja, jb = "J%d01" % (c + 1), "J%d02" % (c + 1)
    cable("W-%d" % (112 + c), "SiPM coaxial pair %s (anode signal + bias): head board %s/%s to SiPM carrier %s" % (ch, ja, jb, ch), "head", [
        w("CARR-" + ch, "A", "HEAD." + ja, "1", "%s_A" % ch, 0, "coax centre", ins=COAX, pair="X1", note="anode signal: coax centre"),
        w("CARR-" + ch, "A-SH", "HEAD." + ja, "2", "GND", 0, "coax shield", ins=COAX, pair="X1", note="anode coax shield = signal return, bonded at both ends by design"),
        w("CARR-" + ch, "B", "HEAD." + jb, "1", "%s_HVF" % ch, 0, "coax centre", ins=COAX, pair="X2", note="bias (filtered HV, up to 62.5 V full scale): coax centre"),
        w("CARR-" + ch, "B-SH", "HEAD." + jb, "2", "GND", 0, "coax shield", ins=COAX, pair="X2", note="bias coax shield = bias return")],
        length=35, basis="rear-edge U.FL to the carrier in the chimney: < 35 mm (board_envelopes.yaml AFE_STRIP); at most 28 mm routed (drop 17-25 mm + 11 mm lateral) + 7 mm termination = 35 mm maximum", budget=35,
        construction="Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.",
        shield="Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.", protection="Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse",
        strain="Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle",
        notes="Anode pair: F at du -11/-6, R at +6/+11 around the lane centre (layout_guidance.md). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23).")

# ================================================================ LAB extension (not in the robot BOM)
LABCOL = [("1", "HEAD_PWR_P", 18, "RD", "P1"), ("2", "HEAD_PWR_N", 18, "BK", "P1"), ("3", "HEAD_HTR_P", 18, "OG", "P2"), ("4", "HEAD_HTR_N", 18, "BN", "P2"),
          ("5", "HEAD_LOOP_OUT", 24, "GN", "P3"), ("6", "HEAD_LOOP_RET", 24, "GY", "P3"), ("7", "HEAD_PRES_ID", 24, "VT", "")]
cable("W-200", "LAB ONLY: J1X extension, 2 m, M16 plug (robot end) to M16 socket (head end), straight through + 1.50 kohm LAB resistor", "lab", [
    w("J1X-P", p, "J1X-S", p, n, a, c, pair=pr, note=("AWG 18 REQUIRED for the heater pair (CCR-E07)" if a == 18 and p in "34" else "AWG 18 recommended: meets 0.125 ohm") if a == 18 else "") for p, n, a, c, pr in LABCOL] +
    [w("J1X-P", "SH", "J1X-S", "SH", "CHASSIS", 24, "bare", kind="shield", to_net="SHLD_J1", idx="S", note="braid continuous, 360 degrees in both backshells, no third termination or stub"),
     w("J1X-P", "7", "J1X-P", "2", "HEAD_PRES_ID", 24, "VT", to_net="HEAD_PWR_N", kind="resistor", idx="R", len_mm=30, note="R_LAB 1.50 kohm 1 % in the chassis-end plug backshell (part TBD - not in sources): pin 7 to pin 2")],
    length=2000, basis="2.0 m by the head ICD section 7 ('2 m as a harness design trial'); 1.7 m fallback in CCR-E07", budget=2000,
    construction="See lab_extension.md.", shield="Continuous braid end to end.", protection="Same upstream protection as W-008/W-101 (eFuses 1.51 A and 4.05 A); LAB mode adds no fuse",
    strain="Strain-relief clamps in both backshells; support the head and cable independently of the entrance window (head_icd.md section 7)", notes="LAB ONLY. Mark both plugs with the LAB label. Not part of the robot BOM.")
cable("W-201", "LAB ONLY: J2X extension, 2 m, M12 plug (robot end) to M12 socket (head end), straight through", "lab", [
    w("J2X-P", "1", "J2X-S", "1", "RS485_DP", 26, "WH", ins=FEP, pair="P1"), w("J2X-P", "2", "J2X-S", "2", "RS485_DN", 26, "BU", ins=FEP, pair="P1"),
    w("J2X-P", "3", "J2X-S", "3", "BUS_5V", 26, "RD", ins=FEP, pair="P2"), w("J2X-P", "4", "J2X-S", "4", "BUS_GND", 26, "BK", ins=FEP, pair="P2"),
    w("J2X-P", "5", "J2X-S", "5", "SYNC_P", 26, "GN", ins=FEP, pair="P3"), w("J2X-P", "6", "J2X-S", "6", "SYNC_N", 26, "GY", ins=FEP, pair="P3"),
    w("J2X-P", "7", "J2X-S", "7", "J2_PRES", 26, "VT", ins=FEP, pair="P4"),
    w("J2X-P", "SH", "J2X-S", "SH", "CHASSIS", 26, "bare", ins=FEP, kind="shield", to_net="SHLD_J2", idx="S", note="braid continuous, no third termination")],
    length=2000, basis="2.0 m (head ICD section 7)", budget=2000, construction="See lab_extension.md. 120 ohm twisted pair P1 straight through: NO terminator, NO stub; the two terminations stay at the chassis board and the head board.",
    shield="Continuous braid end to end.", protection="As W-009/W-102", strain="Strain-relief clamps in both backshells", notes="LAB ONLY.")
