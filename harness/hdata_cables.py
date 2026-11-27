"""Cable assemblies (W-xxx) and their wires.  Geometry in base_link mm (frames.yaml, board_envelopes.yaml,
mechanical_interfaces.md, layout_report.md corridors).  Every length is ESTIMATED FROM LAYOUT, CONFIRM ON FIRST BUILD.
"""
import math, os, json

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


# Board connector positions: STAGE-2 PLACEMENT, read from electronics/chassis_main/out/pinmap.json (centre of the pads of each connector,
# board frame (u, v) = RR-CHS-MAIN).  Stage 1 used nominal corner positions (+-20 mm); the rear-right cluster (J_PAUSE, J_TOF3, J_TOF10,
# J_BUMP_R, J_TOF6, ...) is a stage-2 decision (STAGE2_CHANGE_REQUESTS.md, IB-12 / IB-33).  The module also runs when exec()'d without
# __file__ by electronics/chassis_main/tools/cable_lengths.py (it then looks for the repository relative to the working directory).
def _repo_root():
    try:
        return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    except NameError:
        return os.getcwd()


def _read_json(rel):
    with open(os.path.join(_repo_root(), rel)) as f:
        return json.load(f)


def _centres(pm):
    out = {}
    for p in pm["parts"]:
        xy = []
        for q in p["pins"]:
            v = q.get("pad_xy_mm")
            if v:
                xy += v if isinstance(v[0], list) else [v]
        if xy:
            out[p["ref"]] = (round(sum(a for a, _ in xy) / len(xy), 1), round(sum(b for _, b in xy) / len(xy), 1))
    return out


CHS_UV = _centres(_read_json("electronics/chassis_main/out/pinmap.json"))
HEAD_UV = _centres(_read_json("electronics/head_acq/out/pinmap.json"))
CHS_POS = {ref: chs(u, v) for ref, (u, v) in CHS_UV.items() if ref.startswith("J_") or ref == "W1"}


def hpos(ref, dv=0.0, z=37.0):
    """head board connector centre (pinmap.json of RR-HEAD-ACQ) in base_link; dv moves the point in board v (towards the board interior)"""
    u, v = HEAD_UV[ref]
    return hdb(u, v + dv, z)


def _frames_tof():
    """sensor positions (mm, base_link) of the ToF sensors from mechanical/common/frames.yaml (re-read at every build), None if unreadable"""
    try:
        import yaml
        with open(os.path.join(_repo_root(), "mechanical/common/frames.yaml")) as f:
            t = yaml.safe_load(f)["tof"]
        return {k: tuple(round(x * 1000.0, 1) for x in v["xyz"]) for k, v in t.items()}
    except Exception:
        return None


FRAMES_TOF = _frames_tof()

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
], path=[(-16, 0, 53), (4, -30, 58), (-5, -102, 88), (CHS_POS["J_PWR"][0], -102, 88), (CHS_POS["J_PWR"][0], -82, 86), CHS_POS["J_PWR"]], end=30, loop=40, budget=300,
    construction="Two AWG 14 trunk conductors (twisted pair) coupler to splices, then 2 x AWG 16 per pole to the Mini-Fit Jr 2x4 J_PWR (stage-2 position u 142.5, v 24.1: 18 mm in from the right edge, 15 mm clear of the rear-right cluster). Corridors: under_bridge_right then right_gutter (layout_report.md section 7). Pair twisted P1 over the trunk.",
    shield="none (power, unshielded)", protection=PRO["pack"], strain=STRAIN["minifit"],
    notes="IB-36 CONTRADICTION (J_PWR gauge): power_budget.md assumes 2 x 0.30 m AWG 14 all the way to J_PWR, but electronics/chassis_main/design/connectors.yaml (unchanged by stage 2: overrides.py has no J_PWR entry) fits 39-00-0078 contacts for AWG 16 on pins 1/2/5/6. The harness FOLLOWS connectors.yaml (the board side is fixed): an AWG 14 trunk plus 2 x AWG 16 per pole through a crimp splice (about 1.3 mohm extra, not in the power budget). Splice, fuse holder and SBS50 contact wire range are TBD. The fuse position leaves <= 150 mm of unfused trunk.")

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
    notes="IB-37 (accepted offset): the NTC return and the presence link are made to PACK NEGATIVE inside the cassette, so the sense level rides the pack-negative power path (about 0.1 V at full load: NTC reads about 3.4 K warm while discharging, about 0.7 K cold while charging, both on the safe side; STAGE2_CHANGE_REQUESTS.md). J_PAUX pins 3/4 stay unwired unless the cassette provides a sense return ISOLATED from pack negative. Cassette half of the SBS50 coupler is UNVERIFIED; -20 C rating only in parts.yaml (IB-36, see open items).")

cable("W-003", "Pack coupler (bay half) auxiliary contacts to main board J_PAUX", "robot", [
    w("CPL-B", "A1", "CHS.J_PAUX", "1", "PACK_NTC", 26, "WH", ins=FEP, pair="P1"),
    w("CPL-B", "A2", "CHS.J_PAUX", "2", "PACK_PRES_N", 26, "VT", ins=FEP, pair="P1"),
], path=[(-16, 0, 53), (4, -30, 58), (-5, -102, 88), (CHS_POS["J_PAUX"][0], -102, 88), (CHS_POS["J_PAUX"][0], -82, 86), CHS_POS["J_PAUX"]], end=20, loop=40,
    construction="Two AWG 26 conductors, twisted pair, run in the same loom as W-001 (separate sleeve). J_PAUX pins 3 and 4 (GND) are NOT wired: the cassette returns NTC and presence to pack negative inside the cassette.",
    shield="none", protection=PRO["ntc"], strain=STRAIN["gh"],
    notes="IB-37 DECISION (chassis stage 2, accepted offset, no board change): the NTC/presence return flows through the pack-negative power path (up to 12.5 A): the J_PAUX GND level can differ from board GND by about 0.1 V at full load (NTC about 3.4 K warm on discharge, about 0.7 K cold on charge: safe side; PACK_PRES_N is logic level). J_PAUX pins 3/4 (GND) stay UNWIRED. They are wired ONLY if the cassette gets a sense return isolated from pack negative (W-002 change plus a third SBS50 auxiliary contact); wiring them to a return that is also tied to pack negative would put an AWG 26 wire in parallel with the pack return (about 1-2 % of pack current). J_PAUX is at u 118.0, v 21.8 (stage 2). AWG 26 for the aux contacts is a proposal; SBS50 auxiliary contact wire range is TBD.")

cable("W-004", "Charge inlet to main board J_PWR (24 V in, 0 V, plug-link pair)", "robot", [
    w("INLET", "1", "CHS.J_PWR", "3", "CHG_IN", 18, "RD", pair="P1", note="39-00-0038 crimp (AWG 18-24)"),
    w("INLET", "3", "CHS.J_PWR", "7", "GND", 18, "BK", pair="P1", note="39-00-0038 crimp"),
    w("INLET", "2", "CHS.J_PWR", "4", "PLUG_LINK", 24, "YE", pair="P2", note="chain input (CHG_COVER element): U20 plug-link channel"),
    w("INLET", "4", "CHS.J_PWR", "8", "GND", 24, "BK", pair="P2", note="LINK_B, 0 V at the board"),
], path=[(-191.6, -101.7, 88), (-155, -100, 80), (-100, -95, 72), (-60, -90, 85), (CHS_POS["J_PWR"][0], -82, 86), CHS_POS["J_PWR"]], budget=250,
    construction="4 conductors: power pair (AWG 18) twisted P1, link pair (AWG 24) twisted P2, in one jacket. Corridor right_bay then right_gutter. Inlet FE contact = chassis through the receptacle flange (no wire).",
    shield="none; FE on the inlet bonds to the chassis through the flange", protection=PRO["chg"], strain=STRAIN["minifit"] + "; inlet end: clamp behind the receptacle (25 mm depth available)",
    notes="Inlet pin assignment is a PROPOSAL (external_24v_supply.md [M][U]). Layout length exceeds the 0.25 m of power_budget.md only if it comes out above 250 mm (see length column). Plug link opens even with an unpowered cable: pins 2 and 4 are linked inside the charge plug.")

cable("W-005", "Inlet cover switch to main board J_COVER", "robot", [
    w("COVER-DEV", "COM", "CHS.J_COVER", "1", "CH_N3", 24, "YE", pair="P1", note="502438-0000 crimp (AWG 24-30)"),
    w("COVER-DEV", "NC", "CHS.J_COVER", "2", "CH_N4A", 24, "YE", pair="P1", note="NC contact closed with the cover shut"),
], path=[(-191.6, -101.7, 88), (-155, -100, 80), (-100, -95, 72), (-62, -85, 85), CHS_POS["J_COVER"]], end=20,
    construction="2 x AWG 24 twisted pair, yellow safety loom. J_COVER pin 3 NC (not wired). D2HW NO lead cut back and insulated.",
    shield="none", protection=PRO["chain"], strain=STRAIN["clik"],
    notes="Chain element CHG_COVER: opens when the cover is open. Switch lead gauge/length not in sources (TBD): splice or direct crimp decided on the first build.")

# ================================================================ ROBOT: drive
for s, side, sg in (("L", "Left", 1), ("R", "Right", -1)):
    cid = "W-006" if s == "L" else "W-007"
    cable(cid, "%s gearmotor and encoder to main board J_MOT_%s" % (side, s), "robot", [
        w("MOTOR-" + s, "1", "CHS.J_MOT_" + s, "1", "MOTC_%s_A" % s, 22, "RD", ins=DEV, pair="M", note="Pololu red; motor A. AWG 22 follows power_budget.md (the lead gauge is the motor maker's, not published); connectors.yaml recommends AWG 20 (IB-36)"),
        w("MOTOR-" + s, "2", "CHS.J_MOT_" + s, "2", "MOTC_%s_B" % s, 22, "BK", ins=DEV, pair="M", note="Pololu black; motor B"),
        w("MOTOR-" + s, "3", "CHS.J_MOT_" + s, "3", "ENC_%s_5V" % s, 26, "BU", ins=DEV, pair="E", note="Pololu blue; encoder 5 V"),
        w("MOTOR-" + s, "4", "CHS.J_MOT_" + s, "4", "GND", 26, "GN", ins=DEV, pair="E", note="Pololu green; encoder GND"),
        w("MOTOR-" + s, "5", "CHS.J_MOT_" + s, "5", "ENCC_%s_A" % s, 26, "YE", ins=DEV, pair="E", note="Pololu yellow; encoder A"),
        w("MOTOR-" + s, "6", "CHS.J_MOT_" + s, "6", "ENCC_%s_B" % s, 26, "WH", ins=DEV, pair="E", note="Pololu white; encoder B"),
    ], path=[(0, sg * 42.5, 59), (8, sg * 70, 72), (15, sg * 96, 86), (CHS_POS["J_MOT_" + s][0], sg * 82, 85), CHS_POS["J_MOT_" + s]], budget=250,
        construction="The motor's own six-wire pigtail re-terminated into a Micro-Fit 3.0 2x3 plug housing (43025-0600). Lead length and gauge are NOT published (TBD): if the pigtail is shorter than the length column, extend with an in-line splice at the motor, never with a connector. Colours are Pololu's, not this scheme (modules sheet [D], confirm on the part).",
        shield="none (motor leads and encoder lines unshielded; ferrite + 1 nF at the board connector, layout_guidance.md)", protection=PRO["mot"] + "; " + PRO["enc"],
        strain=STRAIN["mfit"] + "; motor end: leads clipped to the motor mount within 30 mm of the exit",
        notes="IB-36 (motor lead gauge): the harness assumes AWG 22 as in power_budget.md (motor leads AWG 22, 0.25 m) because the leads are the maker's captive pigtail and its gauge is not published (gearmotor_pololu_2828.md); electronics/chassis_main/design/connectors.yaml J_MOT recommends AWG 20 for pins 1/2. Both fit the 43030-0007 contact (AWG 20-24). If the real pigtail is thinner than AWG 22 the 2.7 A pins are under-rated: measure on the first motor. Motor pins 1-2 max 2.7 A on AWG 22 (3 A table value): little margin. Motor terminals face y = %s115 (gearbox) with the cable leaving the encoder end at y = %s42.5 (parts.yaml envelope). Left/right swap is found by the first wheel-up test (connectors.yaml same_count_as)." % ("+" if s == "L" else "-", "+" if s == "L" else "-"))

# ================================================================ ROBOT: head interface (chassis side)
rcpt1 = (72.0 - 22 * 0.6246, 32.0 - 22 * 0.2901, 116.9 - 22 * 0.7251)
rcpt2 = (72.0 - 18 * 0.6246, -32.0 + 18 * 0.2901, 116.9 - 18 * 0.7251)
J1COL = [("1", "HEAD_PWR_P", 20, "RD", "P1"), ("2", "HEAD_PWR_N", 20, "BK", "P1"), ("3", "HEAD_HTR_P", 18, "OG", "P2"), ("4", "HEAD_HTR_N", 18, "BN", "P2"),
         ("5", "HEAD_LOOP_OUT", 24, "GN", "P3"), ("6", "HEAD_LOOP_RET", 24, "GY", "P3"), ("7", "HEAD_PRES_ID", 24, "VT", "")]
cable("W-008", "J1 chassis lead: main board J_HEAD1 (Mini-Fit Jr 2x5) to the J1 receptacle", "robot",
      [w("CHS.J_HEAD1", p, "J1R", p, n, a, c, pair=pr, to_net=n, note="Mini-Fit Jr 2x5 terminal 39-00-0038 (AWG 18-24) [UNVERIFIED, recalled]: fits AWG %d (stage 2, S2-02)" % a) for p, n, a, c, pr in J1COL],
      path=[CHS_POS["J_HEAD1"], (33, 56, 88), (45, 45, 95), rcpt1], end=30, loop=40, budget=250,
      construction="Custom shielded multicore: individually insulated conductors AWG 20/20/18/18/24/24/24 (pin 8 not fitted), twisted pairs P1 (1-2 power), P2 (3-4 heater), P3 (5-6 loop), pin 7 single; overall tinned-copper braid (>= 85 % coverage is a PROPOSAL) and TPE/PUR jacket rated to <= -40 C (TBD), OD <= 7.5 mm to match the receptacle backshell. Pins 3-4 must be kept out of the electronics return (contract).",
      shield="Overall braid terminated 360 degrees on the J1R receptacle shell/ground tag = chassis (contract). OPEN at the J_HEAD1 end: Mini-Fit Jr has no shield pin; cut back and insulate the braid, no drain wire to the board.",
      protection=PRO["head_pwr"] + " (pins 1-2); " + PRO["head_htr"] + " (pins 3-4); " + PRO["head_sig"] + " (pins 5-7)", strain=STRAIN["circ"],
      notes="STAGE 2 (IB-32 / IB-44, S2-02): J_HEAD1 is now a Mini-Fit Jr 2x5 right-angle header 39-30-1100 (pins 1-8 = J1 pins 1-8, pins 9/10 not connected); the mating housing is 39-01-2100 class with 5556 terminals for AWG 18-24 (all seven wires fit, the heater pair AWG 18 included); this clears the AWG 18 on Micro-Fit error at the chassis end. The 10-way housing cannot mate the 8-way J_PWR. All of the Mini-Fit Jr numbers are recalled, not confirmed (stage-2 file: [U]). Lead length: the layout gives the length column (stage 1 said 150 mm; the board connector is now at u 26.1, v 82.5, 15 mm inside the front edge). J1 receptacle terminals sit about 22 mm behind the skin (parts.yaml depth_behind_panel). M16 8-pole contacts may accept only 0.5 mm2 (power_budget.md [U]): open (OI-06).")
cable("W-009", "J2 chassis lead: main board J_HEAD2 to the J2 receptacle", "robot",
      [w("CHS.J_HEAD2", "1", "J2R", "1", "RS485_DP", 26, "WH", ins=FEP, pair="P1"), w("CHS.J_HEAD2", "2", "J2R", "2", "RS485_DN", 26, "BU", ins=FEP, pair="P1"),
       w("CHS.J_HEAD2", "3", "J2R", "3", "BUS_5V", 26, "RD", ins=FEP, pair="P2"), w("CHS.J_HEAD2", "4", "J2R", "4", "GND", 26, "BK", ins=FEP, pair="P2", to_net="BUS_GND"),
       w("CHS.J_HEAD2", "5", "J2R", "5", "SYNC_P", 26, "GN", ins=FEP, pair="P3", note="reserved hardware time pulse, not fitted in rev A boards"),
       w("CHS.J_HEAD2", "6", "J2R", "6", "SYNC_N", 26, "GY", ins=FEP, pair="P3"), w("CHS.J_HEAD2", "7", "J2R", "7", "J2_PRES", 26, "VT", ins=FEP, pair="P4")],
      path=[CHS_POS["J_HEAD2"], (33, -52.5, 88), (45, -45, 95), rcpt2], end=25, loop=40,
      construction="Custom shielded 4-pair cable: P1 RS-485 (120 ohm twisted pair, 1 Mbaud), P2 BUS_5V/BUS_GND, P3 SYNC (reserved), P4 J2_PRES + one spare core (pin 8, trimmed and insulated at both ends). Overall braid + jacket as W-008, OD <= 6.5 mm (parts.yaml).",
      shield="Overall braid 360 degrees on the J2R shell = chassis; OPEN at the J_HEAD2 end (GH has no shield pin).", protection=PRO["bus5"] + "; " + PRO["head_sig"], strain=STRAIN["circ"],
      notes="Termination 120 ohm is on the boards at both ends, bias at the chassis end only: this cable must not add any. AWG 26 matches connectors.yaml; ampacity for AWG 26 is not in sources (load <= 0.2 A).")

# ================================================================ ROBOT: compute, LiDAR
cm5 = (-111, 87, 66)
cable("W-010", "CM5 5.1 V feed: main board J_CM5 to the CM5 carrier 40-pin header", "robot", [
    w("CHS.J_CM5", "1", "CM5-HDR", "2", "V5_CM5", 20, "RD", pair="P1", note="two wires per pole; 43030-0007 crimp (AWG 20-24) takes AWG 20 (stage 2, S2-02 / IB-32)"),
    w("CHS.J_CM5", "2", "CM5-HDR", "4", "V5_CM5", 20, "RD", pair="P1"),
    w("CHS.J_CM5", "3", "CM5-HDR", "6", "GND", 20, "BK", pair="P2"),
    w("CHS.J_CM5", "4", "CM5-HDR", "9", "GND", 20, "BK", pair="P2"),
], path=[CHS_POS["J_CM5"], (-52.5, 84, 87), (-75, 85, 88), (-100, 80, 86), cm5], budget=250,
    construction="4 x AWG 20 silicone (two per pole), twisted as two pairs: J_CM5 stays Micro-Fit 3.0 and the harness goes to AWG 20 (chassis stage 2, STAGE2_CHANGE_REQUESTS.md IB-32: 2.5 A per contact, 80 mV total drop at 5.0 A for a 180 mm cable: 6 mohm conductors + 10 mohm contacts per pole at 5.0 A, contact figure [U]). The earlier AWG 18 needed a terminal that the 43025 housing does not take. Corridors left_gutter / left_bay_over_cm5. Carrier-end termination of AWG 20 on 0.1 inch header contacts is UNRESOLVED (TBD): alternative USB-C power-only pigtail (modules sheet).",
    shield="none", protection=PRO["cm5"], strain=STRAIN["mfit"],
    notes="power_budget.md assumed 2 x AWG 18 per pole (5.2 mohm for 0.25 m): AWG 20 is 3.8 -> 6.0 mohm for this length, 11 mV more at 5 A (accepted by chassis stage 2, follow electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md). Check on the bench before the harness is drawn: carrier back-feed/protection behaviour and usb_max_current_enable (modules sheet [U]). Pi header pins 2/4 = 5 V, 6/9 = GND per the modules sheet.")
cable("W-011", "LiDAR supply: main board J_LIDAR to the LiDAR", "robot", [
    w("CHS.J_LIDAR", "1", "LIDAR-PWR", "1", "V12_LIDAR", 22, "RD", pair="P1"),
    w("CHS.J_LIDAR", "2", "LIDAR-PWR", "2", "GND", 22, "BK", pair="P1"),
], path=[CHS_POS["J_LIDAR"], (-39.0, 82, 86), (-95, 69, 108), (-118, 62, 116), (-140, 45, 150), (-150, 10, 152)], budget=400,
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
for cid, nm, jb, pins, pos in (("W-013", "chassis link (MCU CDC)", "CHS.J_USB_MCU", [("2", "2", "MCUC_USB_DM", "WH"), ("3", "3", "MCUC_USB_DP", "GN"), ("4", "4", "GND", "BK")], CHS_POS["J_USB_MCU"]),
                               ("W-014", "head link (FT230X)", "CHS.J_USB_HEAD", [("1", "1", "HUSB_VBUS", "RD"), ("2", "2", "HUSBC_DM", "WH"), ("3", "3", "HUSBC_DP", "GN"), ("4", "4", "GND", "BK")], CHS_POS["J_USB_HEAD"])):
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
], path=[CHS_POS["J_ESTOP"], (-67, -78, 90), pe],
    construction="4 x AWG 24 in two twisted pairs (pole A, pole B), yellow, in the safety loom. An external stop provision (E10) goes in series with BOTH poles at the J_ESTOP end (CCR/E10), no board change.",
    shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="Each pole is its own pair so a short between poles needs two failures. Chain wire short to +12 V is an undetected latent fault: keep this loom away from VBAT conductors (chassis_safety_chain.md #8, #31). Contact-block terminal numbers TBD.")
pm = dev_rear((-135, 98, 130.3), (-0.0793, 0.4098, 0.9087))
cable("W-016", "Mode selector OFF/SERVICE/RUN to main board J_MODE", "robot", [
    w("MODE-DEV", "EN-a", "CHS.J_MODE", "1", "EN_SRC", 24, "YE", pair="P1", note="EN contact: NC block, closed in SERVICE and RUN; opens the pack switch and regulators in OFF"),
    w("MODE-DEV", "EN-b", "CHS.J_MODE", "2", "EN_SYS", 24, "YE", pair="P1"),
    w("MODE-DEV", "RUN-a", "CHS.J_MODE", "3", "CH_N0", 24, "YE", pair="P2", note="RUN contact: NO block, closed in RUN only (chain element MODE_RUN)"),
    w("MODE-DEV", "RUN-b", "CHS.J_MODE", "4", "CH_N1", 24, "YE", pair="P2"),
], path=[CHS_POS["J_MODE"], (-67, 76, 90), pm],
    construction="4 x AWG 24, two twisted pairs, yellow safety loom. J_MODE pins 5, 6 not wired.", shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="The selector assembly XB5AD33 has 2 NO blocks: the OFF-side block must be exchanged for a ZBE-102 NC (UNVERIFIED, modules sheet).")
ph = dev_rear((-172, -97, 125.2), (-0.1899, -0.415, 0.8898))
cable("W-017", "HANDS-ON button and lamp to main board J_HANDS", "robot", [
    w("HANDS-DEV", "NC-a", "CHS.J_HANDS", "1", "CH_N2", 24, "YE", pair="P1"),
    w("HANDS-DEV", "NC-b", "CHS.J_HANDS", "2", "CH_N3", 24, "YE", pair="P1"),
    w("HANDS-DEV", "LAMP+", "CHS.J_HANDS", "3", "HANDS_LAMP_P", 24, "PK", pair="P2", note="lamp fed from the chain node CH_N2 (lit = upstream live, contact open)"),
    w("HANDS-DEV", "LAMP-", "CHS.J_HANDS", "4", "HANDS_LAMP_K", 24, "BU", pair="P2"),
], path=[CHS_POS["J_HANDS"], (-67, -78, 90), ph],
    construction="4 x AWG 24; contact pair yellow (safety loom), lamp pair PK/BU in the same loom (lamp +12 V comes from the chain node: keep it in the safety loom). J_HANDS pin 5 not wired.", shield="none",
    protection=PRO["chain"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"], notes="Lamp 12 V, <= 20 mA. Exact XB5 reference TBD (UNVERIFIED).")
pr = dev_rear((-172, 97, 125.2), (-0.1899, 0.415, 0.8898))
pz = dev_rear((-84, -112, 122), (0.0491, -0.5205, 0.8524))
cable("W-018", "REARM/Start button and lamp: main board J_BTN to the REARM button (left deck)", "robot", [
    w("REARM-DEV", "SET-a", "CHS.J_BTN", "1", "SET_CAP", 24, "YE", pair="P1", note="NO 1: capacitor-coupled latch set path (SAFETY)"),
    w("REARM-DEV", "SET-b", "CHS.J_BTN", "2", "K1_SET", 24, "YE", pair="P1"),
    w("REARM-DEV", "AUX-a", "CHS.J_BTN", "3", "BTN_3V3", 24, "RD", note="NO 2 supply side (BTN_3V3 is now local to the REARM button: PAUSE has its own supply, R_PAUSE)"),
    w("REARM-DEV", "AUX-b", "CHS.J_BTN", "4", "REARM_BTN_RAW", 24, "WH", note="NO 2: REARM_BTN to the MCU (isolated from the set path)"),
    w("REARM-DEV", "LAMP+", "CHS.J_BTN", "6", "V12_AUX", 24, "PK", note="lamp supply; the PAUSE lamp has its own conductor on J_PAUSE pin 3"),
    w("REARM-DEV", "LAMP-", "CHS.J_BTN", "7", "LAMP_REARM_K", 24, "BU"),
], path=[CHS_POS["J_BTN"], (-67, 76, 90), pr],
    construction="6 x AWG 24, direct to the REARM button, no splices (stage 2, S2-01: the Y-loom with SPL-BTN3 / SPL-BTN6 is gone). Yellow safety loom for pins 1-2. J_BTN pins 5 and 8 are not connected on the board any more (the PAUSE signals moved to J_PAUSE): leave those housing cavities empty.",
    shield="none", protection=PRO["chain"] + "; lamps: " + PRO["aux12"], strain=STRAIN["clik"] + "; device end: " + STRAIN["device"],
    notes="A short between J_BTN 1-2 permanently sets the set path: the latch must still not set after an element cycles (chassis_safety_chain.md procedure 7). J_BTN stays an 8-way CLIK-Mate so that its circuit count stays unique among the safety headers (S2-01a/b).")
cable("W-019", "PAUSE/Stop button and lamp: main board J_PAUSE (JST GH 5-way) to the PAUSE button (right deck)", "robot", [
    w("PAUSE-DEV", "NO-a", "CHS.J_PAUSE", "1", "PAUSE_3V3", 26, "RD", ins=FEP, note="contact supply through R_PAUSE 1 kohm on the board (S2-01f): a short cannot load 3V3"),
    w("PAUSE-DEV", "NO-b", "CHS.J_PAUSE", "2", "PAUSE_BTN_RAW", 26, "WH", ins=FEP, note="PAUSE contact to the MCU input; ESD at D_PAUSE next to the connector"),
    w("PAUSE-DEV", "LAMP+", "CHS.J_PAUSE", "3", "V12_AUX", 26, "PK", ins=FEP, note="lamp supply, <= 20 mA"),
    w("PAUSE-DEV", "LAMP-", "CHS.J_PAUSE", "4", "LAMP_PAUSE_K", 26, "BU", ins=FEP, note="switched low side"),
], path=[CHS_POS["J_PAUSE"], (-70, -55, 92), (-78, -82, 88), pz], end=20,
    construction="4 x AWG 26 (JST GH contacts take AWG 26-30: was AWG 24 on the CLIK-Mate Y-branch), own cable, no splices, no crossing of the board (stage 2, S2-01e). J_PAUSE pin 5 not connected. PAUSE is program control, not a chain element (CCR-E12), so it is a signal-family connector and the cable is not in the yellow safety loom.",
    shield="none", protection=PRO["aux12"] + "; contact supply current-limited by R_PAUSE 1 kohm", strain=STRAIN["gh"] + "; device end: " + STRAIN["device"],
    notes="STAGE 2 (IB-33): J_PAUSE (BM05B-GHS-TBT) is in the rear-right GH row at u 101.4, v 14.2, next to the PAUSE button on the right deck. 5 circuits: the same count as J_USB_MCU / J_USB_HEAD (rear-left), so a mis-plug would put V12_AUX on a USB pin: separate by 80 mm on the board and by the printed label. The stage-1 290 mm Y-branch from J_BTN is replaced by this own cable.")
cable("W-020", "Head dock switch to main board J_DOCK", "robot", [
    w("DOCK-DEV", "COM", "CHS.J_DOCK", "1", "CH_N4", 24, "YE", pair="P1"),
    w("DOCK-DEV", "NC", "CHS.J_DOCK", "3", "CH_N5", 24, "YE", pair="P1"),
], path=[CHS_POS["J_DOCK"], (40, 0, 75), (40, 87.5, 40), (-3, 87.5, 23)],
    construction="2 x AWG 24 twisted pair, yellow. Corridor front_bay then along the left receiver channel to the switch behind the channel (-3, 87.5, 23). J_DOCK pin 2 not wired. Switch NC wired so the loop is closed only when the shoe presses it.",
    shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; switch end: clip to the channel within 30 mm, keep clear of the shoe sweep (head removal sweep +x is free per layout_report.md)",
    notes="Dock switch is in the head-removal path region: protect the leads from the shoe tip (x = 4.0).")
for cid, side, jc, dev, a, b, cpt, sg in (("W-021", "L", "CHS.J_BUMP_L", "BUMP-L-DEV", "CH_N7", "CH_N8A", (-236.6, 103, 66), 1), ("W-022", "R", "CHS.J_BUMP_R", "BUMP-R-DEV", "CH_N8A", "CH_N8", (-236.6, -103, 66), -1)):
    if sg == 1:
        pth = [CHS_POS["J_BUMP_L"], (-70, 60, 95), (-95, 69, 105), (-118, 66, 105), cpt]
    else:
        pth = [CHS_POS["J_BUMP_R"], (-67, -72, 95), (-100, -80, 70), (-155, -85, 65), cpt]
    cable(cid, "Body bumper %s to main board J_BUMP_%s" % ("left" if sg == 1 else "right", side), "robot", [
        w(dev, "COM", jc, "1", a, 24, "YE", pair="P1"), w(dev, "NC", jc, "2", b, 24, "YE", pair="P1")], path=pth,
        construction="2 x AWG 24 twisted pair, yellow. %s" % ("Along the rear edge of the board to the left corner, corridor hump_side_left, then the left rear quarter." if sg == 1 else "Stage 2: J_BUMP_R is in the rear-right CLIK-Mate row, so the cable goes straight to the right corner and right_bay to the right rear quarter without crossing the board."),
        shield="none", protection=PRO["chain"], strain=STRAIN["clik"] + "; switch end: clip to the bumper band bracket within 30 mm with a service loop that allows the band stroke (>= 8 mm)",
        notes=("STAGE 2 (IB-33): J_BUMP_R moved to the rear-right cluster (u 134.8, v 3.7); the stage-1 430 mm board crossing is gone. J_BUMP_L/R are interchangeable (series contacts) and now on opposite sides. Bumper switch D2HW NO lead cut back and insulated." if sg == -1 else "Bumper switch D2HW NO lead cut back and insulated. J_BUMP_L is at u 61.8, v 3.7 (centre-left of the rear edge): the cable runs 45 mm along the rear edge to the left corridor."))

# ================================================================ ROBOT: panel board and sounder
cable("W-023", "RR-PANEL: main board J_PANEL to RR-PANEL J1 (straight 1:1)", "robot",
      [w("CHS.J_PANEL", str(i), "PNL.J1", str(i), n, 26, c, ins=FEP, pair=pr)
       for i, n, c, pr in ((1, "V5_AUX", "RD", ""), (2, "V12_AUX", "PK", ""), (3, "GND", "BK", ""), (4, "LED_READY_K", "GN", ""), (5, "LED_MOVING_K", "BU", ""), (6, "LED_HOLD_K", "VT", ""),
                           (7, "LED_FAULT_K", "GY", ""), (8, "LED_CHARGE_K", "WH", ""), (9, "BUZ_N", "BN", ""), (10, "GND", "BK", ""))],
      path=[CHS_POS["J_PANEL"], (-70, 73, 100), (-80, 97, 110)], end=20,
      construction="10 x AWG 26, round multicore jacket, pin n to pin n (circuit.py checks the 1:1 order). The two GND conductors (3 and 10) share one colour: distinguished by the printed wire numbers. Corridor hump_side_left.",
      shield="none", protection=PRO["aux12"] + "; " + PRO["logic"], strain=STRAIN["gh"],
      notes="STAGE 2 (panel P1): RR-PANEL J1 (SM10B-GHS-TB side entry) and J2 are fitted on the TOP side at (30, 20.6) and (49.5, 20.6), mating face toward the v = 24 edge, so the cable leaves over that long edge (not along the long axis as in stage 1; the top allows 8 mm, the bottom only 3 mm, CCR-E08(d) option b). Which end of the panel (u) faces +y in the robot, and so which long edge (fore or aft) the cable leaves over, is NOT confirmed by mechanical: the 45 mm of end allowance and 50 mm service loop cover either choice (the difference is about 24 mm).")
cable("W-024", "OPTIONAL external 22 mm sounder: RR-PANEL J2 to the panel sounder", "robot", [
    w("PNL.J2", "1", "SOUNDER-EXT", "+", "V12_AUX", 26, "PK", pair="P1"), w("PNL.J2", "2", "SOUNDER-EXT", "-", "BUZ_N", 26, "BU", pair="P1")],
    path=[(-80, 97, 110), (-80, 97, 128)], end=20, loop=40,
    construction="2 x AWG 26 twisted pair (JST GH contacts take AWG 26-30). The sounder position is not in the sources (assumed within 100 mm of the annunciator).", shield="none", protection=PRO["aux12"] + "; sounder <= 100 mA", strain=STRAIN["gh"] + "; " + STRAIN["device"],
    notes="Recommended by the panel circuit (on-board piezo about 60 dB at 1 m). No part verified (TBD).")

# ================================================================ ROBOT: ToF carriers
# IB-34 (lead decision): the four oblique look-ahead sensors are two FORWARD-looking (grip cheeks) and two REARWARD-looking (tail),
# as placed in mechanical/common/frames.yaml (tof_look_fl, _fr, _rl, _rr).  Same connectors J_TOF4..J_TOF7, new names (old LOOK_LO/LI/RI/RO gone).
# LOOK_MAP: firmware id -> frames.yaml sensor.  To change the mapping change ONLY this table.
# (harness name, zone, frames.yaml keys: the mechanical engineer renamed tof_look_fl/fr/rl/rr to tof_look_fwd_left/... on 2026-11-27, both are accepted)
LOOK_MAP = {4: ("LOOK_FL", "fl", ("tof_look_fwd_left", "tof_look_fl")), 5: ("LOOK_FR", "fr", ("tof_look_fwd_right", "tof_look_fr")),
            6: ("LOOK_RL", "rl", ("tof_look_rev_left", "tof_look_rl")), 7: ("LOOK_RR", "rr", ("tof_look_rev_right", "tof_look_rr"))}
_FALLBACK = {"tof_cliff_fl": (46.0, 109.5, 31.0), "tof_cliff_fr": (46.0, -109.5, 31.0), "tof_cliff_rl": (-241.7, 78.3, 41.0), "tof_cliff_rr": (-241.7, -78.3, 41.0),
             "tof_look_fl": (1.5, 91.0, 162.0), "tof_look_fr": (1.5, -91.0, 162.0), "tof_look_rl": (-247.6, 65.6, 100.0), "tof_look_rr": (-247.6, -65.6, 100.0),
             "tof_prox_rl": (-249.3, 82.0, 80.0), "tof_prox_rc": (-236.0, 0.0, 158.0), "tof_prox_rr": (-249.3, -82.0, 80.0)}


def tofpos(keys):
    """sensor aperture position: frames.yaml (re-read at every build; first key found) else the values recorded when this table was written"""
    keys = (keys,) if isinstance(keys, str) else tuple(keys)
    for k in keys:
        if FRAMES_TOF and k in FRAMES_TOF:
            return FRAMES_TOF[k]
    return _FALLBACK[keys[-1]]


# routes: via points between the board connector and the sensor (corridors of layout_report.md section 7; the board top may be crossed
# under the saddle cover at z 85..105).  Key = (zone of the board connector, zone of the sensor); connector zones from the stage-2 placement:
# J_TOF4 front-left edge, J_TOF5 rear-left GH row, J_TOF6 rear-right GH row, J_TOF7 front-right edge.
_CONN_ZONE = {4: "FL", 5: "RL", 6: "RR", 7: "FR"}
_LOOK_VIA = {
    ("FL", "fl"): [(10, 85, 110)],
    ("FL", "fr"): [(0, 0, 100), (10, -85, 110)],
    ("FL", "rl"): [(-5, 100, 88), (-69, 102, 90), (-118, 66, 105)],
    ("FL", "rr"): [(-30, 0, 100), (-70, -60, 95), (-100, -80, 70), (-155, -85, 80)],
    ("FR", "fr"): [(10, -85, 110)],
    ("FR", "fl"): [(0, 0, 100), (10, 85, 110)],
    ("FR", "rr"): [(-5, -100, 88), (-69, -102, 90), (-118, -66, 105)],
    ("FR", "rl"): [(-30, 0, 100), (-70, 60, 95), (-95, 69, 105), (-118, 66, 105)],
    ("RL", "rl"): [(-70, 60, 95), (-95, 69, 105), (-118, 66, 105)],
    ("RL", "rr"): [(-60, 0, 95), (-67, -72, 95), (-100, -80, 70), (-155, -85, 80)],
    ("RL", "fl"): [(-20, 85, 100), (10, 85, 110)],
    ("RL", "fr"): [(-30, 0, 100), (10, -85, 110)],
    ("RR", "rr"): [(-67, -72, 95), (-100, -80, 70), (-155, -85, 80)],
    ("RR", "rl"): [(-60, 0, 95), (-70, 60, 95), (-95, 69, 105), (-118, 66, 105)],
    ("RR", "fr"): [(-20, -85, 100), (10, -85, 110)],
    ("RR", "fl"): [(-30, 0, 100), (10, 85, 110)],
}
TOFMAP = {  # firmware id -> (name, frames.yaml key, via points between the board connector and the sensor)
    0: ("CLIFF_FL", "tof_cliff_fl", [(45, 20, 70), (46, 100, 40)]),
    1: ("CLIFF_FR", "tof_cliff_fr", [(45, -20, 70), (46, -100, 40)]),
    2: ("CLIFF_RL", "tof_cliff_rl", [(-95, 69, 105), (-118, 66, 100)]),
    3: ("CLIFF_RR", "tof_cliff_rr", [(-67, -72, 95), (-100, -80, 70), (-155, -85, 60)]),
    8: ("REAR_L", "tof_prox_rl", [(-95, 69, 105), (-118, 66, 100)]),
    9: ("REAR_C", "tof_prox_rc", [(-95, 69, 108), (-118, 62, 116), (-140, 40, 150)]),
    10: ("REAR_R", "tof_prox_rr", [(-67, -72, 95), (-100, -80, 70), (-155, -85, 65)]),
}
for _i, (_nm, _zone, _keys) in LOOK_MAP.items():
    TOFMAP[_i] = (_nm, _keys, _LOOK_VIA[(_CONN_ZONE[_i], _zone)])
TOFCOL = [("1", "3V3", "+3V3", "RD", "P1"), ("2", "GND", "GND", "BK", "P1"), ("3", "SDA_C", "SDA", "GN", "P2"), ("4", "SCL_C", "SCL", "WH", "P2"), ("5", "XSHUT_C", "XSHUT", "VT", "P3"), ("6", "GPIO1", "GPIO1", "GY", "P3")]
for n in range(11):
    nm, skey, via = TOFMAP[n]
    spos = tofpos(skey)
    cid = "W-%03d" % (30 + n)
    wires = []
    for pin, sfx, cname, col, pr in TOFCOL:
        wires.append(w("CHS.J_TOF%d" % n, pin, "TOF%d.J1" % n, pin, "TOF%d_%s" % (n, sfx) if sfx != "GND" else "GND", 28, col, ins=FEP, pair=pr, to_net=cname,
                       double=(pin == "2"), note=("drain wire shares this crimp (shield bonded at the board end only)" if pin == "2" else "")))
    note = "ToF %s (firmware id %d). " % (nm, n)
    if n in LOOK_MAP:
        note += "IB-34 (lead decision): the four oblique look-ahead sensors are two forward-looking (grip cheeks: tof_look_fl, tof_look_fr) and two rearward-looking (tail: tof_look_rl, tof_look_rr) as placed in frames.yaml; same connectors J_TOF4..J_TOF7, names LOOK_FL / LOOK_FR / LOOK_RL / LOOK_RR (the old names LOOK_LO / LI / RI / RO are retired). The contract and firmware pinmap still carry the old names until the firmware owner renames them. Sensor position from frames.yaml %s. " % (skey if isinstance(skey, str) else skey[0],)
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
], path=[CHS_POS["J_HTR"], (-67, -72, 88), (-100, -70, 76), (-120, -70, 50), (-119, -40, 41)], budget=300,
    construction="3 x AWG 20 silicone. The independent bimetal cut-out is in series in this harness, on the heater plate (CCR-E08(e)); element 7.2 ohm, 20 W. The cut-out must be rated for >= 3.04 A at 14.4 V DC (TBD part).",
    shield="none", protection=PRO["chshtr"], strain=STRAIN["mfit"] + "; plate end: leads secured with high-temperature tape/clips to the plate within 30 mm",
    notes="Heater pad leads are not in the sources. The return conductor goes to GND (not a separate heater return net on this board).")
cable("W-042", "Bay NTC and pack-surface NTC to main board J_NTC", "robot", [
    w("NTC-BAY", "a", "CHS.J_NTC", "1", "NTC_BAY", 26, "WH", ins=FEP, pair="P1"), w("NTC-BAY", "b", "CHS.J_NTC", "2", "GND", 26, "BK", ins=FEP, pair="P1"),
    w("NTC-PACKSURF", "a", "CHS.J_NTC", "3", "NTC_PACK", 26, "GN", ins=FEP, pair="P2"), w("NTC-PACKSURF", "b", "CHS.J_NTC", "4", "GND", 26, "BK", ins=FEP, pair="P2")],
    path=[CHS_POS["J_NTC"], (-67, -72, 90), (-100, -70, 76), (-120, -57, 65)], end=20,
    construction="2 twisted pairs AWG 26. NTCs 10 kohm B3435 (parts TBD). The two GND returns stay separate (pins 2 and 4) so the pair stays Kelvin.", shield="none", protection=PRO["ntc"], strain=STRAIN["gh"],
    notes="NTC positions are not given beyond 'beside the heater' and 'pack surface'; length is for the bay near the heater plate.")
# W-044 (optional external bus-clamp resistor on the DNP pads CHS.W1) is REMOVED (IB-26 / IB-36 decision): the board carries its own clamp
# resistors (R 9.1 ohm 2512 x 2 in parallel = 4.55 ohm, 2 W pulse-rated, in the VMOT brake-chopper circuit of circuit.py), so there is no
# bolt-on part, no CLAMP-EXT device and no cable. The two DNP wire pads W1 stay on the board with no harness wire.

# ================================================================ HEAD: pigtails
# J1 cable port (stage 2, CR-M03(a)): y = 76.2 = board u 86.8 = the centre of J2001; J2 port unchanged at y = -87.5 (params.HEAD_PIGTAIL_EXIT)
hp = (71.7, 76.2, 39.0)
hp2 = (71.7, -87.5, 39.0)
# the shield drain goes from the port to the SHLD pad (TP2004 / TP2501), which stage 2 placed far from the landings: separate wire inside the head
_dr1 = int(math.ceil((plen([(80.0, hp[1], 39.0), hdb(*HEAD_UV["TP2004"])]) + 30.0) / 10.0) * 10)
_dr2 = int(math.ceil((plen([(80.0, hp2[1], 39.0), hdb(*HEAD_UV["TP2501"])]) + 30.0) / 10.0) * 10)
cable("W-101", "Head J1 captive pigtail: head board J2001 to the J1 plug", "head", [
    w("HEAD.J2001", p, "J1P", p, n, a, c, pair=pr, note=("terminal: Micro-Fit 43030 'AWG 18-24 variant' (head circuit.py note, recalled, UNVERIFIED): the same open question that chassis stage 2 closed at J_HEAD1 by moving to Mini-Fit Jr (IB-32); open for the head board (OD-3)" if a == 18 else "")) for p, n, a, c, pr in J1COL] +
    [w("HEAD.TP2004", "1", "J1P", "SH", "SHLD_J1", 24, "bare", kind="shield", idx="S", len_mm=_dr1, note="shield drain to the board pad TP2004 (SHLD_J1: 1 Mohm || 10 nF to FRAME); braid also 360 degrees in the plug backshell. TP2004 is at u 23.5, v 70.5 (stage 2), far from J2001 (u 86.8, v 10.6): the drain is a separate wire of %d mm inside the head (about 100 mm of path), not the cable length" % _dr1)],
    path=[hpos("J2001", dv=-4.6), hp], end=25, loop=20, extra=200.0,
    basis="inside the head: board J2001 (u 86.8, v 10.6, mating face rearward, stage 2) to the rear-wall port = 17.6 mm path + 2 x 25 mm + 20 mm; outside: 200 mm free length (mechanical_interfaces.md allows 150..200; straight-line port to plug rear is 142 mm, plus bends at 40 mm radius, so 150 mm is too short)", budget=350,
    construction="Same construction as W-008 (shielded multicore, twisted pairs P1 power, P2 heater, P3 loop), captive: sealed strain relief in the head rear wall at (71.7, 76.2, 39) (CR-M03, moved from y 87.5), cable leaves toward -x/+z, clipped to the shoe root. OD <= 7.5 mm.",
    shield="Braid: 360 degrees to the J1 plug backshell (-> chassis through the mated shell) AND drain wire to the head board pad TP2004. This is the contract: hard bond at the chassis, 1 Mohm || 10 nF at the head.",
    protection=PRO["head_pwr"] + " (pins 1-2); " + PRO["head_htr"] + " (pins 3-4); " + PRO["head_sig"], strain="Sealed strain-relief gland in the rear wall (inside the head wall); plug backshell clamp; clip to the shoe root; head cover 0.9 mm clearance must not trap the cable",
    notes="IB-36 (head pigtail length): the harness specifies 200 mm free length outside the head plus about 90 mm inside = 290 mm, against the 2 x 0.35 m of the head power_budget.md (head side calculation); the geometry-based 200 mm follows mechanical_interfaces.md (150..200 mm) and the 142 mm straight-line check: the shorter pigtail lowers the resistance (conservative for the budget). The loop is potential-free: no conductor of pins 5-6 may touch the shield or any other pin. J2001 and J2601 sit side by side at the rear edge (stage 2, S2-L5: J2601 u 50.2..72.0, J2001 u 73.0..100.7) with the mating faces rearward; this needs CR-M02/CR-M03 (not yet accepted by head mechanical, IB-52). CCR-HE-02: J2001 header height 8 mm zone open.")
cable("W-102", "Head J2 captive pigtail: head board J2501 to the J2 plug (plug link pin 7 to pin 4)", "head", [
    w("HEAD.J2501", "1", "J2P", "1", "RS485_DP", 26, "WH", ins=FEP, pair="P1"), w("HEAD.J2501", "2", "J2P", "2", "RS485_DN", 26, "BU", ins=FEP, pair="P1"),
    w("HEAD.J2501", "3", "J2P", "3", "BUS_5V", 26, "RD", ins=FEP, pair="P2"), w("HEAD.J2501", "4", "J2P", "4", "BUS_GND", 26, "BK", ins=FEP, pair="P2"),
    w("HEAD.J2501", "5", "J2P", "5", "SYNC_P", 26, "GN", ins=FEP, pair="P3"), w("HEAD.J2501", "6", "J2P", "6", "SYNC_N", 26, "GY", ins=FEP, pair="P3"),
    w("HEAD.J2501", "7", "J2P", "7", "J2_PRES", 26, "VT", ins=FEP, pair="P4"),
    w("J2P", "7", "J2P", "4", "J2_PRES", 26, "VT", ins=FEP, to_net="BUS_GND", kind="link", idx="L", len_mm=20, note="J2_PRES plug link inside the plug (contract); keep R2502 DNP"),
    w("HEAD.TP2501", "1", "J2P", "SH", "SHLD_J2", 26, "bare", ins=FEP, kind="shield", idx="S", len_mm=_dr2, note="shield drain to pad TP2501 (SHLD_J2); braid 360 degrees in the plug backshell. TP2501 is at u 252.7, v 69.8 (stage 2), 60 mm from the J2501 landing: separate drain wire of %d mm inside the head" % _dr2)],
    path=[hpos("J2501", dv=0.8), hp2], end=25, loop=20, extra=200.0,
    basis="inside the head: board J2501 (u 262.3, v 5.2) to the rear-wall port (u 250.5) = about 21 mm + 2 x 25 mm + 20 mm; outside: 200 mm free length (150..200 allowed; port to plug rear 142 mm straight)",
    construction="Same as W-009: shielded 4-pair, 7 conductors + link. Captive, sealed strain relief at (71.7, -87.5, 39).", shield="As W-101 with TP2501 / J2P backshell.", protection=PRO["bus5"] + "; " + PRO["head_sig"],
    strain="Sealed strain-relief gland in the rear wall; plug backshell clamp; clip to the shoe root", notes="J2_PRES link: pin 7 and pin 4 are linked inside the plug; the chassis sees J2_PRES low when mated.")

# ================================================================ HEAD: internal
cable("W-103", "Head heater film, bimetal cut-out and spreader NTC: head board J2601 to the heater assembly", "head", [
    w("HEAD.J2601", "1", "HEAD-HEATER", "1", "HTR_SW", 18, "OG", note="43030 'AWG 18-24 variant' crimp (head circuit.py note, recalled, UNVERIFIED: OD-3); up to 4.35 A trip, element draw <= 3.04 A"),
    w("HEAD.J2601", "3", "SPL-HCUT", "1", "HTR_CUT", 24, "VT", note="cut-out sense (CUTOUT_SENSE node between element and cut-out)"),
    w("HEAD-HEATER", "2", "SPL-HCUT", "2", "HTR_CUT", 18, "BN", note="element end to the junction"),
    w("SPL-HCUT", "3", "HEAD-CUTOUT", "1", "HTR_CUT", 18, "BN"),
    w("HEAD-CUTOUT", "2", "HEAD.J2601", "2", "HEAD_HTR_N", 18, "BN", note="heater return through the low-side cut-out; HEAD_HTR_N never touches ground on the board"),
    w("NTC-SPR", "a", "HEAD.J2601", "4", "NTC_HTR", 24, "WH", ins=FEP, pair="P1"), w("NTC-SPR", "b", "HEAD.J2601", "5", "GND", 24, "BK", ins=FEP, pair="P1")],
    path=[hpos("J2601", dv=-2.6), (76, 87.5, 30), (74, 87.5, 24)], end=20, loop=30, budget=350,
    construction="Heater circuit AWG 18 pair (supply and return twisted) plus AWG 24 sense and an AWG 26 NTC pair. Assembly (per J2601): HTR_SW -> 4.8 ohm element -> CUTOUT_SENSE -> bimetal cut-out (low side) -> HEAD_HTR_N. Tail comes up the rear chimney at y = +87.5. J2601 pin 6 not wired.",
    shield="none inside the shielded head", protection=PRO["head_htr"] + "; cut-out status reads 'tripped' when the feed is off (by design)", strain="Leads clipped to the spreader with Kapton/high-temperature tape within 20 mm of the film tail",
    notes="Heater film, cut-out and NTC parts are not in the sources (TBD). CCR-HE-02 (connector height) open.")
for cid, nm, jref, dev, sw in (("W-104", "front", "J2002", "RAIL-F", (184.2, 0.0, 21.0)), ("W-105", "left", "J2003", "RAIL-L", (131.2, 168.5, 21.0)), ("W-106", "right", "J2004", "RAIL-R", (131.2, -168.5, 21.0))):
    # stage-2 positions (head pinmap.json): J2002 u 154.5, J2003 u 171.5, J2004 u 144.6 (S2-L6: outside RAIL_SWITCH_LANDING, harness reach u 140..149),
    # all at v 91.2 on the front edge.  base y = 163 - u: J2004 (RIGHT rail) is LEFT of centre (y +18.4) and J2003 (LEFT rail) is RIGHT of centre (y -8.5):
    # the two cables cross in the front wall channel.
    pos = hpos(jref, dv=-1.2)
    via = {"front": [], "left": [(180, 10, 30), (180, 160, 25)], "right": [(180, -10, 30), (180, -160, 25)]}[nm]
    nets = {"J2002": ("HEAD_LOOP_OUT", "LOOP_A"), "J2003": ("LOOP_A", "LOOP_B"), "J2004": ("LOOP_B", "LOOP_C")}[jref]
    cable(cid, "Head rail switch %s (series element of the interlock loop): head board %s to the switch" % (nm, jref), "head", [
        w(dev, "COM", "HEAD." + jref, "1", nets[0], 26, "GN", ins=FEP, pair="P1"), w(dev, "NC", "HEAD." + jref, "2", nets[1], 26, "GY", ins=FEP, pair="P1")],
        path=[pos] + via + [sw], end=15, loop=30,
        construction="2 x AWG 26 twisted pair in the front wall channel (JST GH contacts take AWG 26-30). Connector pins 3 and 4 (AUX_N/AUX_GND zone read-back) are NOT wired: the D2HW is single-pole and its NO throw is not potential-free from the loop (CCR-HE-04). The NO lead is cut back and insulated.",
        shield="none (inside the shielded head)", protection=PRO["head_sig"], strain="Clip in the front wall channel every 50 mm; switch end clipped within 20 mm",
        notes="Loop is a potential-free series chain; see the loop diagram in cables.md. Stage 2: the connector order on the board (J2004 at u 144.6, J2002 at u 154.5, J2003 at u 171.5) puts the RIGHT-rail connector on the left of the centre line and the LEFT-rail connector on the right, so cables W-105 and W-106 cross once in the front channel (about 30 mm of extra length); the zone read-back is not available in rev A, so swapping the left and right switch cables between J2003 and J2004 would cost nothing functionally (it would only exchange the idle BUMP_ZONE_L/R labels) and avoids the crossing: decision for head electronics, not taken here.")
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
        length=35, basis="mechanical interfaces: pigtails < 35 mm from the rear edge into the chimney (drop 17-25 mm + lateral offset from the GH-6 at lane du -1.80 to the carrier at the lane centre = 1.8 mm, so at most 27 mm routed + 7 mm termination): 35 mm cut length is the maximum (stage 2: JST GH-6 J1001/J1101/J1201/J1301 at the rear edge, u 29.9 / 117.5 / 204.9 / 292.4, v 5.0, S2-L3)",
        construction="6 x AWG 28 flat/round micro-cable, 3 twisted pairs (NTC, LED, 3V3). The lane SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06) is the lane temperature sensor. LED and 3V3 pins feed an optional pulser/active sensor.",
        shield="none; inside the lane shield can region: keep leads < 35 mm", protection=PRO["ntc"], strain="Adhesive/tack at the carrier end; no loop > 10 mm (pickup, IB-23)",
        notes="Carrier connector TBD (not in sources).")
LANE_CH = ["F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"]
# Stage-2 U.FL positions (head README / STAGE2 S2-L3), du from the lane centre where the carrier sits (head_report.md: lane centre):
# F anode -10.38, F bias -15.47, R bias +6.78, R anode +11.87; drop up the chimney 17..25 mm (assume the 25 mm worst case) + 7 mm termination.
_DU = {"F": (-10.38, -15.47), "R": (11.87, 6.78)}
for c, ch in enumerate(LANE_CH):
    ja, jb = "J%d01" % (c + 1), "J%d02" % (c + 1)
    du_a, du_b = _DU[ch[0]]
    la = int(math.ceil((25.0 + abs(du_a) + 7.0) / 5.0) * 5)
    lb = int(math.ceil((25.0 + abs(du_b) + 7.0) / 5.0) * 5)
    cable("W-%d" % (112 + c), "SiPM coaxial pair %s (anode signal + bias): head board %s/%s to SiPM carrier %s" % (ch, ja, jb, ch), "head", [
        w("CARR-" + ch, "A", "HEAD." + ja, "1", "%s_A" % ch, 0, "coax centre", ins=COAX, pair="X1", len_mm=la, note="anode signal: coax centre"),
        w("CARR-" + ch, "A-SH", "HEAD." + ja, "2", "GND", 0, "coax shield", ins=COAX, pair="X1", len_mm=la, note="anode coax shield = signal return, bonded at both ends by design"),
        w("CARR-" + ch, "B", "HEAD." + jb, "1", "%s_HVF" % ch, 0, "coax centre", ins=COAX, pair="X2", len_mm=lb, note="bias (filtered HV, up to 62.5 V full scale): coax centre"),
        w("CARR-" + ch, "B-SH", "HEAD." + jb, "2", "GND", 0, "coax shield", ins=COAX, pair="X2", len_mm=lb, note="bias coax shield = bias return")],
        length=max(la, lb), basis="rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du %+.2f -> %d mm, bias du %+.2f -> %d mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax %d mm" % (du_a, la, du_b, lb, max(la, lb)), budget=35,
        construction="Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.",
        shield="Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.", protection="Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse",
        strain="Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle",
        notes="Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.")

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
