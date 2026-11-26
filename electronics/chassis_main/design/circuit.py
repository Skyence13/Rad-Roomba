#!/usr/bin/env python3
"""RR-CHS-MAIN rev A -- complete net-level circuit definition (stage 1 output).

Tool-neutral plain Python data, no dependencies.  `python3 circuit.py` runs the self-check.

    PARTS        list of dict(ref, value, mpn, manufacturer, description, package, symbol_hint,
                 footprint_hint, pins={pin_number: (pin_name, net) | None}, block, dnp, rating,
                 tolerance, notes, verify, height_mm, area_mm2)
    NETS         {net: [(ref, pin_number, pin_name), ...]}          (derived)
    NET_CLASSES  class -> nets / patterns + layout constraints
    CONNECTORS   harness view of every board connector (mirrored in connectors.yaml)
    MECH         outline, mounting holes, zones (from mechanical/common/board_envelopes.yaml)

Conventions
  * verify=True  : MPN, pin numbers or a value could not be confirmed against the manufacturer's
                   datasheet in the stage-1 session (see `notes`).  The stage-2 engineer must check
                   these before creating symbols.  Pin NAMES are authoritative, pin NUMBERS of
                   verify=True parts are not.
  * [D] datasheet value read in stage 1, [C] calculated, [A] assumed, [U] unverified.
  * MCU pin assignment = firmware/chassis/pinmap.yaml (final).  Deviations: none in pin use;
    additions listed in ../design/CONTRACT_CHANGE_REQUESTS.md.
  * Not a certified safety system.  See electronics/analysis/chassis_safety_chain.md.
"""
import re

PARTS = []
_cnt = {}

# package -> (placed area mm2 incl. courtyard, height mm).  Honest estimates for the fit check.
PKG = {
    "0402": (1.6, 0.5), "0603": (3.2, 0.9), "0805": (5.0, 1.2), "1206": (8.5, 1.6), "1210": (11, 2.5),
    "1812": (20, 2.0), "2512": (26, 1.0), "SOD-123": (7, 1.2), "SOD-323": (4, 1.0), "SMB": (22, 2.4), "SMA": (14, 2.3),
    "SOT-23": (9, 1.1), "SOT-23-5": (9, 1.2), "SOT-23-6": (9, 1.2), "SOT-23-8": (9, 1.1), "SOT-363": (6, 1.0),
    "SOIC-8": (32, 1.75), "VSSOP-10": (16, 1.1), "TSSOP-16": (34, 1.2), "TSSOP-24": (52, 1.2), "SSOP-16": (32, 1.75),
    "SSOP-28": (82, 2.0), "HTSSOP-16": (36, 1.2), "LQFP-64": (160, 1.6), "QFN-28-4x5": (30, 0.8), "VQFN-24-4x4": (25, 1.0),
    "VQFN-16-4x4": (25, 1.0), "VQFN-HR-14": (20, 1.0), "VQFN-HR-10": (9, 1.0), "VSON-10": (14, 0.8), "LGA-16": (20, 1.0),
    "SON-5x6": (40, 1.1), "SON-3x3": (16, 1.0), "DPAK": (75, 2.4), "USON-10": (6, 0.6), "DIP4-SMD": (45, 4.0),
    "XTAL-3225": (12, 0.8), "IND-6x6": (50, 6.1), "IND-5x5": (36, 5.1), "IND-5x5x4": (36, 4.0), "ECAP-10x10": (125, 10.5),
    "RELAY-G2RL": (400, 15.7), "RELAY-G6S": (125, 9.4), "TP": (4, 1.5), "FID": (7, 0), "HOLE-M3": (38.5, 0),
    "MINIFIT-2x4-RA": (22.2 * 16, 12.8), "MICROFIT-2x1-RA": (9.6 * 13, 7.0), "MICROFIT-2x2-RA": (12.6 * 13, 7.0),
    "MICROFIT-2x3-RA": (15.6 * 13, 7.0), "MICROFIT-2x4-RA": (18.6 * 13, 7.0),
    "GH-V": None, "GH-H": None, "CLIK-V": None, "HDR-1.27-2x5": (70, 5.0), "PAD-2": (20, 0), "SJ": (4, 0),
}


def _area(pkg, npins):
    if pkg in ("GH-V", "GH-H"):
        return ((1.25 * (npins - 1) + 5.0) * (5.0 if pkg == "GH-V" else 7.0), 4.25)
    if pkg == "CLIK-V":
        return ((2.0 * (npins - 1) + 6.0) * 6.5, 6.0)
    return PKG[pkg]


def part(ref, value, mpn, mfr, desc, pkg, sym, fp, pins, block, dnp=False, rating=None, tol=None, notes="", verify=False):
    a, h = _area(pkg, len(pins))
    PARTS.append(dict(ref=ref, value=value, mpn=mpn, manufacturer=mfr, description=desc, package=pkg, symbol_hint=sym,
                      footprint_hint=fp, pins={str(k): v for k, v in pins.items()}, block=block, dnp=dnp, rating=rating,
                      tolerance=tol, notes=notes, verify=verify, height_mm=h, area_mm2=a))
    return ref


def _ref(prefix):
    _cnt[prefix] = _cnt.get(prefix, 0) + 1
    return "%s%d" % (prefix, _cnt[prefix])


def _rcode(val):
    """'10k' -> '10K', '4.7k' -> '4K7', '100' -> '100R', '2.2M' -> '2M2', '0.02' handled by caller."""
    m = re.match(r"^([0-9.]+)([kM]?)$", val)
    num, mult = m.group(1), m.group(2).upper() or "R"
    return num.replace(".", mult) if "." in num else num + mult


def R(val, a, b, block, tol="1%", pkg="0603", rating="0.1 W", notes="", dnp=False, mpn=None, mfr="Yageo", ref=None, verify=False):
    if mpn is None:
        size = {"0402": "0402", "0603": "0603", "0805": "0805", "1206": "1206"}[pkg]
        mpn = ("RT%sBRD07%sL" if tol == "0.1%" else "RC%sFR-07%sL") % (size, _rcode(val))
    return part(ref or _ref("R"), val, mpn, mfr, "Resistor %s %s" % (val, tol), pkg, "Device:R",
                "Resistor_SMD:R_%s" % {"0402": "0402_1005Metric", "0603": "0603_1608Metric", "0805": "0805_2012Metric",
                                       "1206": "1206_3216Metric", "2512": "2512_6332Metric", "1812": "1812_4532Metric"}[pkg],
                {1: ("1", a), 2: ("2", b)}, block, dnp=dnp, rating=rating, tol=tol, notes=notes, verify=verify)


_CAPS = {  # (value, voltage) -> (mpn, mfr, package, dielectric)
    ("10p", 50): ("CC0603JRNPO9BN100", "Yageo", "0603", "C0G"), ("47p", 50): ("CC0603JRNPO9BN470", "Yageo", "0603", "C0G"),
    ("100p", 50): ("CC0603JRNPO9BN101", "Yageo", "0603", "C0G"), ("1n", 50): ("CC0603JRNPO9BN102", "Yageo", "0603", "C0G"),
    ("3.3n", 50): ("CC0603KRX7R9BB332", "Yageo", "0603", "X7R"), ("10n", 50): ("CC0603KRX7R9BB103", "Yageo", "0603", "X7R"),
    ("22n", 50): ("CC0603KRX7R9BB223", "Yageo", "0603", "X7R"), ("100n", 50): ("CC0603KRX7R9BB104", "Yageo", "0603", "X7R"),
    ("1u", 50): ("GRM21BR71H105KA12L", "Murata", "0805", "X7R"), ("4.7u", 50): ("GRM31CR71H475KA12L", "Murata", "1206", "X7R"),
    ("10u", 50): ("GRM32ER71H106KA12L", "Murata", "1210", "X7R"), ("10u", 25): ("GRM31CR71E106KA12L", "Murata", "1206", "X7R"),
    ("22u", 25): ("GRM32ER71E226KE15L", "Murata", "1210", "X7R"), ("22u", 10): ("GRM31CR71A226KE15L", "Murata", "1206", "X7R"),
    ("2.2u", 16): ("GRM188R71C225KE11D", "Murata", "0603", "X7R"), ("4.7u", 16): ("GRM21BR71C475KA73L", "Murata", "0805", "X7R"),
    ("1u", 16): ("GRM188R71C105KA12D", "Murata", "0603", "X7R"),
}


def C(val, a, b, block, v=50, notes="", dnp=False, ref=None):
    mpn, mfr, pkg, diel = _CAPS[(val, v)]
    fp = {"0603": "0603_1608Metric", "0805": "0805_2012Metric", "1206": "1206_3216Metric", "1210": "1210_3225Metric"}[pkg]
    return part(ref or _ref("C"), val, mpn, mfr, "MLCC %sF %d V %s" % (val, v, diel), pkg, "Device:C", "Capacitor_SMD:C_" + fp,
                {1: ("1", a), 2: ("2", b)}, block, dnp=dnp, rating="%d V" % v, tol="10%" if diel == "X7R" else "5%", notes=notes,
                verify=mpn.startswith("GRM"))


def ECAP(val, v, mpn, a, b, block, notes=""):
    return part(_ref("C"), val, mpn, "Panasonic", "Hybrid polymer aluminium capacitor %sF %d V, -55..+125 C" % (val, v), "ECAP-10x10",
                "Device:C_Polarized", "Capacitor_SMD:CP_Elec_10x10.5", {1: ("+", a), 2: ("-", b)}, block, rating="%d V" % v,
                tol="20%", notes=notes, verify=True)


def NFET(ref, d, g, s, block, notes="", mpn="BSS138", mfr="onsemi"):
    return part(ref, mpn, mpn, mfr, "N-MOSFET 50 V 0.22 A logic level (Vgs(th) <= 1.5 V)", "SOT-23", "Device:Q_NMOS_GSD",
                "Package_TO_SOT_SMD:SOT-23", {1: ("G", g), 2: ("S", s), 3: ("D", d)}, block, notes=notes)


def PFET(ref, d, g, s, block, notes=""):
    return part(ref, "BSS84", "BSS84,215", "Nexperia", "P-MOSFET -50 V 0.13 A", "SOT-23", "Device:Q_PMOS_GSD",
                "Package_TO_SOT_SMD:SOT-23", {1: ("G", g), 2: ("S", s), 3: ("D", d)}, block, notes=notes)


def PWRFET(ref, d, g, s, block, kind="5x6", notes=""):
    if kind == "5x6":
        mpn, desc, pkg, fp = "CSD18540Q5B", "N-MOSFET 60 V 1.8 mohm typ [D csd18540q5b.pdf]", "SON-5x6", "Package_TO_SOT_SMD:TDSON-8-1"
    else:
        mpn, desc, pkg, fp = "CSD18543Q3A", "N-MOSFET 60 V 8 mohm class, 3.3x3.3 mm", "SON-3x3", "Package_SON:VSON-8_3.3x3.3mm_P0.65mm_NexFET"
    return part(ref, mpn, mpn, "Texas Instruments", desc, pkg, "Device:Q_NMOS_SGD", fp,
                {1: ("S", s), 2: ("S", s), 3: ("S", s), 4: ("G", g), 5: ("D", d), 6: ("D", d), 7: ("D", d), 8: ("D", d), 9: ("D_PAD", d)},
                block, notes=notes, verify=(kind != "5x6"))


def DIODE(a, k, block, kind="1N4148W", notes="", ref=None):
    tab = {"1N4148W": ("1N4148W-7-F", "Diodes Inc.", "Switching diode 100 V 0.3 A", "SOD-123", "Device:D", "Diode_SMD:D_SOD-123"),
           "BAT54": ("BAT54W-7-F", "Diodes Inc.", "Schottky 30 V 0.2 A", "SOD-123", "Device:D_Schottky", "Diode_SMD:D_SOD-123"),
           "Z24": ("BZT52C24-7-F", "Diodes Inc.", "Zener 24 V 0.5 W", "SOD-123", "Device:D_Zener", "Diode_SMD:D_SOD-123"),
           "Z12": ("BZT52C12-7-F", "Diodes Inc.", "Zener 12 V 0.5 W", "SOD-123", "Device:D_Zener", "Diode_SMD:D_SOD-123"),
           "Z5V1": ("BZT52C5V1-7-F", "Diodes Inc.", "Zener 5.1 V 0.5 W", "SOD-123", "Device:D_Zener", "Diode_SMD:D_SOD-123"),
           "SS34": ("SS34", "onsemi", "Schottky 40 V 3 A", "SMA", "Device:D_Schottky", "Diode_SMD:D_SMA")}
    mpn, mfr, desc, pkg, sym, fp = tab[kind]
    return part(ref or _ref("D"), kind, mpn, mfr, desc, pkg, sym, fp, {1: ("K", k), 2: ("A", a)}, block, notes=notes)


def TVS(net, block, mpn="SMBJ16CA", notes=""):
    tab = {"SMBJ16CA": ("SMB", "TVS 600 W bidirectional, 16 V stand-off, 26 V clamp", "Device:D_TVS", "Diode_SMD:D_SMB"),
           "SMBJ28A": ("SMB", "TVS 600 W unidirectional, 28 V stand-off, 45.4 V clamp", "Device:D_TVS_Filled", "Diode_SMD:D_SMB"),
           "SMAJ5.0A": ("SMA", "TVS 400 W unidirectional, 5 V stand-off", "Device:D_TVS_Filled", "Diode_SMD:D_SMA")}
    pkg, desc, sym, fp = tab[mpn]
    return part(_ref("D"), mpn, mpn, "Littelfuse", desc, pkg, sym, fp, {1: ("K", net), 2: ("A", "GND")}, block, notes=notes)


def ESD2(a, b, block, notes=""):
    return part(_ref("D"), "PESD15VL2BT", "PESD15VL2BT,215", "Nexperia", "Dual bidirectional ESD diode, 15 V", "SOT-23", "Device:D_TVS_Dual_AAC",
                "Package_TO_SOT_SMD:SOT-23", {1: ("K1", a), 2: ("K2", b), 3: ("COM", "GND")}, block, notes=notes, verify=True)


def ESD4(a, b, c, d, block, notes=""):
    return part(_ref("D"), "TPD4E05U06", "TPD4E05U06DQAR", "Texas Instruments", "4-channel ESD array 5.5 V, 0.5 pF", "USON-10",
                "Power_Protection:TPD4E05U06DQA", "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
                {1: ("IO1", a), 2: ("IO2", b), 3: ("GND", "GND"), 4: ("IO3", c), 5: ("IO4", d), 6: None, 7: None, 8: ("GND", "GND"), 9: None, 10: None},
                block, notes=notes or "pin use as on RR-TOF-A (pins 6, 7, 9, 10 are flow-through NC)")


def TP(net, block="test", notes=""):
    return part(_ref("TP"), net, "5019", "Keystone", "SMD test point loop", "TP", "Connector:TestPoint", "TestPoint:TestPoint_Keystone_5019_Minature",
                {1: ("1", net)}, block, notes=notes)


def GH(ref, n, nets, block, desc, side=False, notes=""):
    mpn = ("SM%02dB-GHS-TB(LF)(SN)" if side else "BM%02dB-GHS-TBT(LF)(SN)") % n
    fp = ("Connector_JST:JST_GH_SM%02dB-GHS-TB_1x%02d-1MP_P1.25mm_Horizontal" if side else "Connector_JST:JST_GH_BM%02dB-GHS-TBT_1x%02d-1MP_P1.25mm_Vertical") % (n, n)
    pins = {i + 1: ((str(i + 1), nets[i]) if nets[i] else None) for i in range(n)}
    pins["MP"] = ("MP", "GND")
    return part(ref, "JST GH %dp %s" % (n, "side" if side else "top"), mpn, "JST", desc, "GH-H" if side else "GH-V",
                "Connector_Generic_MountingPin:Conn_01x%02d_MountingPin" % n, fp, pins, block,
                notes=notes or "JST GH is rated -25..+85 C [U]: no margin at the -25 C objective (CCR-E05)", rating="1 A/contact")


def CLIK(ref, n, nets, block, desc, notes=""):
    pins = {i + 1: ((str(i + 1), nets[i]) if nets[i] else None) for i in range(n)}
    return part(ref, "CLIK-Mate 2.0 %dp top" % n, "502443-%02d70" % n, "Molex", desc, "CLIK-V", "Connector_Generic:Conn_01x%02d" % n,
                "Molex CLIK-Mate 2.00 mm vertical SMT header, %d circuits (502443 series)" % n, pins, block, rating="3 A/contact, -40..+105 C [U]",
                notes=notes or "SAFETY family. Series number recalled, not confirmed [U].", verify=True)


def MICROFIT(ref, n, nets, block, desc, notes=""):
    pins = {i + 1: ((str(i + 1), nets[i]) if nets[i] else None) for i in range(n)}
    return part(ref, "Micro-Fit 3.0 2x%d RA" % (n // 2), "43045-%02d00" % n, "Molex", desc, "MICROFIT-2x%d-RA" % (n // 2),
                "Connector_Generic:Conn_02x%02d_Top_Bottom" % (n // 2),
                "Connector_Molex:Molex_Micro-Fit_3.0_43045-%02d00_2x%02d_P3.00mm_Horizontal" % (n, n // 2), pins, block,
                rating="8.5 A/contact max [D family], -40..+105 C", notes=notes or "POWER family. Suffix for plating/pegs to be chosen with the harness lead.", verify=True)


# =============================================================================================== POWER ENTRY
B = "power_entry"
part("J_PWR", "Mini-Fit Jr 2x4 RA", "39-30-1080", "Molex", "Power entry: pack feed (2 contacts per pole), charge inlet feed, plug link", "MINIFIT-2x4-RA",
     "Connector_Generic:Conn_02x04_Top_Bottom", "Connector_Molex:Molex_Mini-Fit_Jr_5569-08A2_2x04_P4.20mm_Horizontal",
     {1: ("PACK_P1", "VBAT_RAW"), 2: ("PACK_P2", "VBAT_RAW"), 3: ("CHG_P", "CHG_IN"), 4: ("LINK_A", "PLUG_LINK"),
      5: ("PACK_N1", "GND"), 6: ("PACK_N2", "GND"), 7: ("CHG_N", "GND"), 8: ("LINK_B", "GND")}, B,
     rating="9 A/contact standard, 13 A HCS [D family]; pack poles use 2 contacts each", notes="Only 8-circuit Mini-Fit on the board: cannot be cross-mated.", verify=True)
GH("J_PAUX", 4, ["PACK_NTC", "PACK_PRES_N", "GND", "GND"], B, "Pack auxiliary: cassette NTC (10 k) and presence link, both returned to pack negative inside the cassette")
TVS("VBAT_RAW", B, "SMBJ16CA", "bidirectional: survives a reversed pack")
C("100n", "VBAT_RAW", "GND", B)
part("U1", "LM74502-Q1", "LM74502QDDFRQ1", "Texas Instruments", "Reverse-polarity protection controller for back-to-back N-FETs, no reverse-current blocking (charge and regeneration flow back), OV cut-off, EN",
     "SOT-23-8", None, "Package_TO_SOT_SMD:SOT-23-8", {1: ("EN/UVLO", "EN_SYS"), 2: ("GND", "GND"), 3: None, 4: ("VCAP", "U1_VCAP"), 5: ("VS", "VBAT_RAW"),
     6: ("GATE", "U1_GATE"), 7: ("OV", "U1_OV"), 8: ("SRC", "PSW_SRC")}, B,
     notes="Pin table [D lm74502-q1.pdf]. EN and OV thresholds not read [U]: R values below assume ~1.2 V; check.", verify=True)
PWRFET("Q1", "VBAT_RAW", "Q1_G", "PSW_SRC", B, notes="blocks a reversed pack (body diode points to the pack)")
PWRFET("Q2", "VBAT_PROT", "Q2_G", "PSW_SRC", B, notes="master switch / inrush control")
R("100", "U1_GATE", "Q1_G", B); R("100", "U1_GATE", "Q2_G", B)
R("10k", "U1_GATE", "U1_SLEW", B, notes="with C: output slew ~ 0.5 V/ms -> < 1 A inrush into 500 uF [C][U]")
C("22n", "U1_SLEW", "PSW_SRC", B)
C("100n", "U1_VCAP", "VBAT_RAW", B, notes="charge-pump capacitor: check the reference node in the datasheet (VS or SRC) [U]")
R("100k", "VBAT_RAW", "U1_OVT", B); R("8.06k", "U1_OV", "GND", B, notes="OV cut-off ~16.6 V with a 1.23 V threshold [U]")
R("0", "U1_OVT", "U1_OV", B, notes="OV ladder top; fit 0 ohm, value in R above")
R("100k", "VBAT_RAW", "EN_SRC", B, notes="feeds the selector EN contact; limits current into a reversed pack")
R("15.8k", "EN_SYS", "GND", B, notes="UVLO ~9.0 V at the pack with a 1.23 V threshold [U]; EN_SYS also enables U10, U11, U12")
C("100n", "EN_SYS", "GND", B)
part("R_SH1", "1m", "WSL25121L000FEA", "Vishay", "Current shunt 1 mohm 1 % 3 W", "2512", "Device:R_Shunt", "Resistor_SMD:R_2512_6332Metric",
     {1: ("1", "VBAT_PROT"), 2: ("2", "VBAT_SW")}, B, rating="3 W", tol="1%", notes="Kelvin to U2", verify=True)
part("U2", "INA228", "INA228AIDGSR", "Texas Instruments", "20-bit power/energy monitor, I2C 0x40", "VSSOP-10", "Sensor_Energy:INA228", "Package_SO:VSSOP-10_3x3mm_P0.5mm",
     {1: ("A1", "GND"), 2: ("A0", "GND"), 3: ("ALERT", "PMON_NALERT"), 4: ("SDA", "I2C_SYS_SDA"), 5: ("SCL", "I2C_SYS_SCL"), 6: ("VS", "3V3"),
      7: ("GND", "GND"), 8: ("VBUS", "VBAT_SW"), 9: ("IN-", "U2_INN"), 10: ("IN+", "U2_INP")}, B, notes="Pin table [D ina228.pdf]. Positive current = discharge.")
R("10", "VBAT_PROT", "U2_INP", B); R("10", "VBAT_SW", "U2_INN", B); C("100n", "U2_INP", "U2_INN", B); C("100n", "3V3", "GND", B)
ECAP("270u", 35, "EEHZA1V271P", "VBAT_SW", "GND", B, "VBAT_SW bulk")
C("10u", "VBAT_SW", "GND", B, v=25); C("10u", "VBAT_SW", "GND", B, v=25)
R("47k", "VBAT_SW", "VBAT_SENSE", B); R("10k", "VBAT_SENSE", "GND", B); C("100n", "VBAT_SENSE", "GND", B)
# pack NTC / presence
R("10k", "3V3", "PACK_PRES_N", B, notes="presence link pulls low; read by the charger-cold comparator block only as a test point (no MCU pin free)")
TP("PACK_PRES_N", B)

# =============================================================================================== CHARGER (LTC4162-F) + POWER PATH
B = "charger"
part("F3", "5A", "0453005.MR", "Littelfuse", "Fuse 5 A fast, 125 V, Nano2 SMD", "1812", "Device:Fuse", "Fuse:Fuse_Littelfuse-NANO2-451_453", {1: ("1", "CHG_IN"), 2: ("2", "CHG_F")}, B, rating="5 A")
TVS("CHG_F", B, "SMBJ28A")
part("Q3", "AOD4185", "AOD4185", "Alpha & Omega", "P-MOSFET -40 V 15 mohm, inlet reverse-polarity protection", "DPAK", "Device:Q_PMOS_GDS", "Package_TO_SOT_SMD:TO-252-2",
     {1: ("G", "Q3_G"), 2: ("D", "CHG_F"), 3: ("S", "CHG_VIN")}, B, notes="tab = drain", verify=True)
R("100k", "Q3_G", "GND", B); DIODE("Q3_G", "CHG_VIN", B, "Z12", notes="gate clamp")
C("10u", "CHG_VIN", "GND", B); C("100n", "CHG_VIN", "GND", B)
part("U3", "LTC4162-FAD", "LTC4162EUFD-FAD#PBF", "Analog Devices", "35 V / 3.2 A LiFePO4 buck charger with PowerPath and I2C telemetry (0x68)", "QFN-28-4x5", None,
     "Package_DFN_QFN:QFN-28-1EP_4x5mm_P0.5mm_EP2.65x3.65mm",
     {1: ("VIN", "CHG_VIN"), 2: ("INFET", "U3_INFET"), 3: ("CLP", "U3_CLP"), 4: ("CLN", "VSYS"), 5: ("VOUT", "VSYS"), 6: ("BATFET", "U3_BATFET"),
      7: ("CSP", "U3_CSP"), 8: ("CSN", "VBAT_SW"), 9: ("BATSENS+", "VBAT_SW"), 10: ("SW", "U3_SW"), 11: ("SW", "U3_SW"), 12: ("PGND", "GND"), 13: ("PGND", "GND"),
      14: ("BOOST", "U3_BOOST"), 15: ("INTVCC", "U3_INTVCC"), 16: ("VCC2P5", "U3_V2P5"), 17: ("DVCC", "3V3"), 18: ("SDA", "I2C_SYS_SDA"), 19: ("SCL", "I2C_SYS_SCL"),
      20: ("SMBALERT", "CHG_NSMBALERT"), 21: ("NTCBIAS", "U3_NTCBIAS"), 22: ("NTC", "U3_NTC"), 23: ("RT", "U3_RT"), 24: ("SYNC", "GND"), 25: ("VC", "U3_VC"),
      26: ("CELLS0", "U3_CELLS0"), 27: ("CELLS1", "U3_CELLS1"), 28: ("SGND", "GND"), 29: ("EP", "GND")}, B, verify=True,
     notes="PIN NUMBERS AND SEVERAL PIN NAMES ARE NOT VERIFIED: analog.com was unreachable from the stage-1 environment (HTTP 503). Net-level intent: "
           "VIN -> INFET ideal diode (Q4) -> RSNSI (R_SNSI, CLP-CLN) -> VSYS (service loads); buck SW -> L1 -> RSNSB (R_SNSB, CSP-CSN) -> VBAT_SW; "
           "BATFET ideal diode (Q5) VBAT_SW -> VSYS when no input. 4 cells selected by CELLS1/CELLS0 straps (coding unverified: both pins have GND/INTVCC/VCC2P5 strap resistors, fit per datasheet). "
           "Variant -FAD = I2C-adjustable charge voltage, MPPT off [U default 3.6 V/cell]. Rebuild this symbol from the datasheet before layout.")
PWRFET("Q4", "U3_CLP", "U3_INFET", "CHG_VIN", B, kind="3x3", notes="input ideal diode: source at the inlet side [U orientation per datasheet figure]")
PWRFET("Q5", "VSYS", "U3_BATFET", "VBAT_SW", B, kind="3x3", notes="battery ideal diode: source at the battery")
part("R_SNSI", "8m", "WSL12068L000FEA", "Vishay", "Input current sense 8 mohm: 32 mV / 8 mohm = 4.0 A input limit [U full-scale]", "1206", "Device:R_Shunt", "Resistor_SMD:R_1206_3216Metric",
     {1: ("1", "U3_CLP"), 2: ("2", "VSYS")}, B, rating="0.5 W", tol="1%", verify=True)
part("R_SNSB", "10m", "WSL1206R0100FEA", "Vishay", "Charge current sense 10 mohm: 32 mV / 10 mohm = 3.2 A full scale; 3.0 A set by I2C/default [U]", "1206", "Device:R_Shunt",
     "Resistor_SMD:R_1206_3216Metric", {1: ("1", "U3_CSP"), 2: ("2", "VBAT_SW")}, B, rating="0.5 W", tol="1%", verify=True)
part("L1", "4.7u", "XAL5050-472MEC", "Coilcraft", "Shielded inductor 4.7 uH, Isat > 6 A", "IND-5x5", "Device:L", "Inductor_SMD:L_Coilcraft_XAL5050-XXX",
     {1: ("1", "U3_SW"), 2: ("2", "U3_CSP")}, B, notes="value for ~1.5 MHz switching [U]; ripple ~1 A at 24 V in, 14.4 V out [C]", verify=True)
C("100n", "U3_BOOST", "U3_SW", B); C("4.7u", "U3_INTVCC", "GND", B, v=16); C("1u", "U3_V2P5", "GND", B, v=16); C("100n", "3V3", "GND", B)
C("10u", "VSYS", "GND", B); C("10u", "VSYS", "GND", B); C("100n", "VSYS", "GND", B)
ECAP("100u", 50, "EEHZA1H101P", "VSYS", "GND", B, "VSYS bulk (24 V while charging)")
C("22u", "VBAT_SW", "GND", B, v=25); C("22u", "VBAT_SW", "GND", B, v=25)
R("100k", "U3_RT", "GND", B, notes="only if the device has an RT pin [U]", dnp=True); R("10k", "U3_VC", "U3_VCC", B, dnp=True, notes="compensation, only if the device has a VC pin [U]")
C("10n", "U3_VCC", "GND", B, dnp=True)
for n in ("0", "1"):
    R("0", "U3_CELLS" + n, "GND", B, notes="cell-count strap option A", dnp=True)
    R("0", "U3_CELLS" + n, "U3_INTVCC", B, notes="cell-count strap option B", dnp=True)
    R("0", "U3_CELLS" + n, "U3_V2P5", B, notes="cell-count strap option C", dnp=True)
R("10k", "U3_NTCBIAS", "U3_NTC", B, notes="bias for a 10 k B3490-class NTC; JEITA cold limit is raised to +5 C by firmware over I2C (default threshold [U])")
NFET("Q6", "U3_NTC", "CHG_TEMP_OK", "PACK_NTC", B, notes="series switch in the NTC line: off (cold or logic unpowered) inserts R below -> charger reads 'too cold' and pauses")
R("220k", "U3_NTC", "PACK_NTC", B, notes="makes the charger see < -30 C when Q6 is off: hardware +5 C inhibit independent of the charger registers")
C("100n", "PACK_NTC", "GND", B)
R("10k", "3V3", "CHG_NSMBALERT", B)
R("100k", "CHG_VIN", "CHG_VIN_DIV", B); R("22k", "CHG_VIN_DIV", "GND", B); C("100n", "CHG_VIN_DIV", "GND", B, notes="inlet-voltage detect for Q21 (chain) and Q31/Q32 (head branches off while charging)")

# =============================================================================================== RAILS
B = "rails"
part("U10", "LM61460-Q1", "LM61460AASQRJRRQ1", "Texas Instruments", "36 V 6 A synchronous buck, V5_CM5 5.12 V", "VQFN-HR-14", None, "TI RJR VQFN-HR-14 4x3.5 mm (see datasheet land pattern)",
     {1: ("BIAS", "V5_BUCK"), 2: ("VCC", "U10_VCC"), 3: ("AGND", "GND"), 4: ("FB", "U10_FB"), 5: ("PGOOD", "V5_PGOOD"), 6: ("RT", "U10_RT"), 7: ("EN/SYNC", "EN_SYS"),
      8: ("VIN1", "VSYS"), 9: ("PGND1", "GND"), 10: ("SW", "U10_SW"), 11: ("PGND2", "GND"), 12: ("VIN2", "VSYS"), 13: ("RBOOT", "U10_RBOOT"), 14: ("CBOOT", "U10_CBOOT")}, B,
     notes="Pin table [D lm61460-q1.pdf]. FB reference 1.0 V [U]; orderable suffix [U]. Enabled by EN_SYS only: stays up across MCU resets.", verify=True)
R("33.2k", "U10_RT", "GND", B, notes="400 kHz [D]"); C("1u", "U10_VCC", "GND", B, v=16); C("100n", "U10_CBOOT", "U10_RBOOT", B, notes="CBOOT-RBOOT 0 ohm = fastest edge; raise RBOOT to slow the SW edge if EMI requires")
R("0", "U10_RBOOT", "U10_SW", B, notes="boot resistor path: verify CBOOT/RBOOT/SW arrangement against the datasheet figure [U]")
part("L2", "6.8u", "XAL6060-682MEC", "Coilcraft", "Shielded inductor 6.8 uH, Isat > 9 A, 6.1 mm high", "IND-6x6", "Device:L", "Inductor_SMD:L_Coilcraft_XAL60xx_6.36x6.56mm",
     {1: ("1", "U10_SW"), 2: ("2", "V5_BUCK")}, B, notes="ripple 1.1 A at 12.8 V in, 1.5 A at 26 V in [C]", verify=True)
R("41.2k", "V5_BUCK", "U10_FB", B); R("10k", "U10_FB", "GND", B); C("10p", "V5_BUCK", "U10_FB", B)
for _ in range(3):
    C("22u", "V5_BUCK", "GND", B, v=10)
C("10u", "VSYS", "GND", B); C("10u", "VSYS", "GND", B); C("100n", "VSYS", "GND", B); C("100n", "VSYS", "GND", B)
R("10k", "3V3", "V5_PGOOD", B)
R("10k", "V5_BUCK", "V5_SENSE", B); R("10k", "V5_SENSE", "GND", B); C("100n", "V5_SENSE", "GND", B)


def efuse(ref, vin, vout, en, flt, rilm, cdvdt, block, what):
    part(ref, "TPS259470A", "TPS259470ARPWR", "Texas Instruments", "eFuse 2.7-23 V, 5.5 A, 28 mohm, adjustable limit, reverse-current blocking: " + what, "VQFN-HR-10", None,
         "TI RPW VQFN-HR-10 2x2 mm (see datasheet land pattern)",
         {1: ("EN/UVLO", en), 2: ("OVLO", "GND"), 3: ("AUXOFF", None) if False else None, 4: ("FLT", flt), 5: ("IN", vin), 6: ("OUT", vout),
          7: ("DVDT", ref + "_DVDT"), 8: ("GND", "GND"), 9: ("ILM", ref + "_ILM"), 10: ("ITIMER", ref + "_ITMR")}, block,
         notes="Pins 1, 2, 5-10 [D tps25947.pdf]; pins 3 (AUXOFF) and 4 (FLT) for the 470x variant read from a garbled table [U]. ILIM = 3343 / RILM [C from D table]. "
               "Auto-retry variant (A).", verify=True)
    R(rilm, ref + "_ILM", "GND", block, notes="current limit; ILM also carries the analogue current monitor")
    C(cdvdt, ref + "_DVDT", "GND", block, notes="output slew control")
    C("10n", ref + "_ITMR", "GND", block, notes="over-current blanking")
    C("100n", vin, "GND", block)
    R("10k", "3V3", flt, block)
    TP(ref + "_ILM", block, "current monitor")


efuse("U13", "V5_BUCK", "V5_CM5", "U13_EN", "V5_CM5_NFLT", "665", "3.3n", B, "V5_CM5 5.0 A")
R("100k", "V5_BUCK", "U13_EN", B, notes="default ON without the MCU"); R("47k", "U13_EN", "GND", B)
NFET("Q10", "U13_EN", "V5_CM5_OFF_REQ", "GND", B, notes="IOX_B P12 high = deliberate compute power cycle")
R("100k", "V5_CM5_OFF_REQ", "GND", B)
C("22u", "V5_CM5", "GND", B, v=10)
for ref, vout, fb_top, lref, what in (("U11", "3V3", "31.6k", "L3", "V3V3_CHS 3.33 V"), ("U12", "V5_AUX", "52.3k", "L4", "V5_AUX 4.98 V (encoders, RS-485, BUS_5V, panel, comparators)")):
    part(ref, "LMR51610X", "LMR51610XDBVR", "Texas Instruments", "65 V 1 A synchronous buck 400 kHz PFM: " + what, "SOT-23-6", None, "Package_TO_SOT_SMD:SOT-23-6",
         {1: ("CB", ref + "_CB"), 2: ("GND", "GND"), 3: ("FB", ref + "_FB"), 4: ("EN", "EN_SYS"), 5: ("VIN", "VSYS"), 6: ("SW", ref + "_SW")}, B,
         notes="Pin table and 0.8 V reference [D lmr51610.pdf].")
    part(lref, "22u", "74404054220", "Wurth Elektronik", "Shielded inductor 22 uH, >= 1.3 A", "IND-5x5x4", "Device:L", "Inductor_SMD:L_Wuerth_WE-LQS-5040",
         {1: ("1", ref + "_SW"), 2: ("2", vout)}, B, verify=True)
    C("100n", ref + "_CB", ref + "_SW", B); R(fb_top, vout, ref + "_FB", B); R("10k", ref + "_FB", "GND", B)
    C("4.7u", "VSYS", "GND", B); C("22u", vout, "GND", B, v=10); C("22u", vout, "GND", B, v=10)
part("U14", "REF3030", "REF3030AIDBZR", "Texas Instruments", "3.000 V 0.2 % reference: MCU VREF+, ratiometric pull-ups, DRV8874 VREF", "SOT-23", "Reference_Voltage:REF3030",
     "Package_TO_SOT_SMD:SOT-23", {1: ("IN", "V5_AUX"), 2: ("OUT", "VREF_3V0"), 3: ("GND", "GND")}, B, notes="pin numbers recalled [U]", verify=True)
C("1u", "V5_AUX", "GND", B, v=16); C("1u", "VREF_3V0", "GND", B, v=16); C("100n", "VREF_3V0", "GND", B)
part("FB1", "600R", "BLM18KG601SN1D", "Murata", "Ferrite bead 600 ohm at 100 MHz, 1.3 A", "0603", "Device:FerriteBead", "Inductor_SMD:L_0603_1608Metric",
     {1: ("1", "3V3"), 2: ("2", "3V3A")}, B, verify=True)
C("1u", "3V3A", "GND", B, v=16); C("100n", "3V3A", "GND", B)

# =============================================================================================== BRANCHES (VBAT_SW side)
B = "branches"
part("U15", "INA3221", "INA3221AIRGVR", "Texas Instruments", "3-channel shunt/bus monitor, I2C 0x41: ch1 HEAD_PWR, ch2 HEAD_HTR, ch3 CHS_HTR", "VQFN-16-4x4", "Sensor_Energy:INA3221",
     "Package_DFN_QFN:VQFN-16-1EP_4x4mm_P0.65mm_EP2.1x2.1mm",
     {1: ("IN-3", "CHS_HTR_F"), 2: ("IN+3", "VBAT_SW"), 3: ("GND", "GND"), 4: ("VS", "3V3"), 5: ("A0", "3V3"), 6: ("SCL", "I2C_SYS_SCL"), 7: ("SDA", "I2C_SYS_SDA"),
      8: ("WARNING", None) if False else None, 9: None, 10: None, 11: ("IN-1", "HEAD_PWR_F"), 12: ("IN+1", "VBAT_SW"), 13: None, 14: ("IN-2", "HEAD_HTR_F"),
      15: ("IN+2", "VBAT_SW"), 16: ("VPU", "3V3"), 17: ("EP", "GND")}, B, notes="Pin table [D ina3221.pdf]; A0 = VS -> 0x41 [D]. Shunts measured on the supply side of each eFuse.")
C("100n", "3V3", "GND", B)
for ref, val, mpn, pkg, out in (("R_SH2", "20m", "WSL1206R0200FEA", "1206", "HEAD_PWR_F"), ("R_SH3", "5m", "WSL25125L000FEA", "2512", "HEAD_HTR_F"), ("R_SH4", "5m", "WSL25125L000FEA", "2512", "CHS_HTR_F")):
    part(ref, val, mpn, "Vishay", "Current shunt %sohm 1 %%" % val, pkg, "Device:R_Shunt", "Resistor_SMD:R_%s" % ("1206_3216Metric" if pkg == "1206" else "2512_6332Metric"),
         {1: ("1", "VBAT_SW"), 2: ("2", out)}, B, rating="0.5 W" if pkg == "1206" else "2 W", tol="1%", verify=True)
efuse("U16", "HEAD_PWR_F", "HEAD_PWR_P", "HEAD_PWR_EN_G", "HEAD_PWR_NFLT", "2.21k", "10n", B, "HEAD_PWR 1.5 A")
efuse("U17", "HEAD_HTR_F", "HEAD_HTR_P", "HEAD_HTR_EN_G", "HEAD_HTR_NFLT", "825", "22n", B, "HEAD_HTR 4.05 A, slew-limited turn-on (~1 V/ms [U])")
efuse("U18", "CHS_HTR_F", "CHS_HTR_P", "CHS_HTR_EN_G", "CHS_HTR_NFLT", "1.1k", "22n", B, "CHS_HTR 3.04 A")
efuse("U19", "VBAT_SW", "V12_LIDAR", "LIDAR_EN_G", "V12_LIDAR_NFLT", "2.21k", "10n", B, "V12_LIDAR 1.5 A")
# enable networks: MCU/expander -> 10k -> EN node, pull resistor gives the default, hardware clamps pull EN low
for en_src, en_g, pull in (("HEAD_PWR_EN", "HEAD_PWR_EN_G", "GND"), ("HEAD_HTR_EN", "HEAD_HTR_EN_G", "GND"), ("CHS_HTR_EN", "CHS_HTR_EN_G", "GND"), ("V12_LIDAR_EN", "LIDAR_EN_G", "3V3")):
    R("10k", en_src, en_g, B); R("100k", en_g, pull, B, notes="default %s with the expander/MCU pin floating" % ("ON" if pull == "3V3" else "OFF"))
NFET("Q31", "HEAD_PWR_EN_G", "CHG_VIN_DIV", "GND", B, notes="hardware: head electronics off while the charge inlet is live")
NFET("Q32", "HEAD_HTR_EN_G", "CHG_VIN_DIV", "GND", B, notes="hardware: head heater off while the charge inlet is live")
NFET("Q33", "HEAD_HTR_EN_G", "WDG_FAULT", "GND", B, notes="hardware: heater off when the watchdog is not satisfied")
NFET("Q34", "CHS_HTR_EN_G", "WDG_FAULT", "GND", B, notes="hardware: heater off when the watchdog is not satisfied")
C("10u", "HEAD_PWR_P", "GND", B, v=25); C("10u", "HEAD_HTR_P", "GND", B, v=25); C("10u", "V12_LIDAR", "GND", B, v=25); C("10u", "CHS_HTR_P", "GND", B, v=25)
TVS("HEAD_PWR_P", B); TVS("HEAD_HTR_P", B); TVS("V12_LIDAR", B); TVS("CHS_HTR_P", B)
part("U25", "TPS2553", "TPS2553DBVR", "Texas Instruments", "Current-limited switch 75 mA-1.7 A, active-high enable: BUS_5V to J2", "SOT-23-6", "Power_Management:TPS2553DBV", "Package_TO_SOT_SMD:SOT-23-6",
     {1: ("IN", "V5_AUX"), 2: ("GND", "GND"), 3: ("EN", "V5_AUX"), 4: ("FAULT", "BUS5V_NFLT"), 5: ("ILIM", "U25_ILIM"), 6: ("OUT", "BUS_5V")}, B,
     notes="pin numbers recalled [U]; always on with V5_AUX (no MCU pin allocated)", verify=True)
R("133k", "U25_ILIM", "GND", B, notes="~0.17 A typ [U formula]; contract limit 0.15 A nominal"); R("10k", "3V3", "BUS5V_NFLT", B); TP("BUS5V_NFLT", B)
C("1u", "V5_AUX", "GND", B, v=16); C("4.7u", "BUS_5V", "GND", B, v=16)

# =============================================================================================== SAFETY CHAIN
B = "chain"
part("F2", "0.2A", "1206L020YR", "Littelfuse", "PTC resettable fuse 0.20 A hold / 0.40 A trip, 30 V", "1206", "Device:Polyfuse", "Fuse:Fuse_1206_3216Metric",
     {1: ("1", "VBAT_SW"), 2: ("2", "CH_N0")}, B, rating="0.2 A hold", verify=True)
CLIK("J_MODE", 6, ["EN_SRC", "EN_SYS", "CH_N0", "CH_N1", None, None], B, "Selector OFF/SERVICE/RUN: pins 1-2 EN contact (closed in SERVICE and RUN), pins 3-4 RUN contact (closed in RUN only)")
CLIK("J_ESTOP", 4, ["CH_N1", "CH_N2", "COIL_RTN", "GND"], B, "E-stop XB5AS8444, 2 NC: pole A pins 1-2 (chain high side), pole B pins 3-4 (coil return)")
CLIK("J_HANDS", 5, ["CH_N2", "CH_N3", "HANDS_LAMP_P", "HANDS_LAMP_K", None], B, "HANDS-ON maintained NC button pins 1-2; lamp pins 3 (+) and 4 (-)")
CLIK("J_COVER", 3, ["CH_N3", "CH_N4A", None], B, "Charge inlet cover switch (D2HW NC contact closed with the cover shut), pins 1-2")
CLIK("J_DOCK", 3, ["CH_N4", None, "CH_N5"], B, "Head dock switch (D2HW), pins 1-3: a plug swapped with J_COVER leaves the chain open")
CLIK("J_BUMP_L", 2, ["CH_N7", "CH_N8A"], B, "Body bumper switch left (D2HW NC)")
CLIK("J_BUMP_R", 2, ["CH_N8A", "CH_N8"], B, "Body bumper switch right (D2HW NC); interchangeable with J_BUMP_L without loss of function")
CLIK("J_BTN", 8, ["SET_CAP", "K1_SET", "BTN_3V3", "REARM_BTN_RAW", "PAUSE_BTN_RAW", "V12_AUX", "LAMP_REARM_K", "LAMP_PAUSE_K"], B,
     "REARM set contact pins 1-2 (safety), REARM aux contact pins 3-4, PAUSE contact pins 3-5, lamps pins 6-7 and 6-8")


def ssr(ref, a, b, led_a, led_k, what):
    part(ref, "TLP241A", "TLP241A(TP1,F", "Toshiba", "Photo-MOS relay 40 V 2 A, 0.15 ohm, 1 form A: " + what, "DIP4-SMD", "Relay_SolidState:TLP222A",
         "Package_DIP:SMDIP-4_W9.53mm", {1: ("ANODE", led_a), 2: ("CATHODE", led_k), 3: ("DRAIN1", a), 4: ("DRAIN2", b)}, B,
         notes="Ratings, trigger current (assumed <= 3 mA) and turn-off time (assumed <= 1 ms) not read: toshiba.semicon-storage.com returned 403 [U].", verify=True)


def tap(node, sig, block=B):
    """Chain readback: 100k / 56k / 22 nF, Schottky clamp to 3V3.  HIGH = node live."""
    R("100k", node, sig, block); R("56k", sig, "GND", block); C("22n", sig, "GND", block); DIODE(sig, "3V3", block, "BAT54")


# U20: plug link / inlet voltage
R("680", "V5_AUX", "U20_A", B); ssr("U20", "CH_N4A", "CH_N4", "U20_A", "U20_K", "CHG plug link absent and inlet dead")
NFET("Q20", "U20_K", "CHG_GATE", "GND", B)
R("100k", "V5_AUX", "CHG_GATE", B); R("10k", "CHG_GATE", "PLUG_LINK", B, notes="link to GND in the charge plug pulls the gate to 0.45 V"); C("10n", "CHG_GATE", "GND", B)
DIODE("GND", "CHG_GATE", B, "Z5V1", notes="clamps the gate if LINK_A is shorted to +24 V at the inlet")
NFET("Q21", "CHG_GATE", "CHG_VIN_DIV", "GND", B, notes="inlet voltage present -> open the chain")
ESD2("PLUG_LINK", "PACK_NTC", B)
# U21: HEAD_LOOP window
R("1k", "V5_AUX", "LOOP_SRC", B, tol="0.1%"); R("100", "LOOP_SRC", "HEAD_LOOP_OUT", B)
R("100", "HEAD_LOOP_RET", "LOOP_SNS", B); R("1k", "LOOP_SNS", "GND", B, tol="0.1%")
R("10k", "LOOP_SNS", "LOOP_F", B); C("100n", "LOOP_F", "GND", B, notes="1 ms"); ESD2("HEAD_LOOP_OUT", "HEAD_LOOP_RET", B)
R("24.3k", "V5_AUX", "LOOP_VHI", B, tol="0.1%"); R("3.57k", "LOOP_VHI", "LOOP_VLO", B, tol="0.1%"); R("10k", "LOOP_VLO", "GND", B, tol="0.1%")
R("2.2M", "V5_AUX", "LOOP_VLO", B, notes="keeps the open-loop threshold above zero if the middle divider resistor opens")
C("100n", "LOOP_VHI", "GND", B); C("100n", "LOOP_VLO", "GND", B)


def lm2903(ref, a_p, a_n, a_o, b_p, b_n, b_o, vcc, what):
    part(ref, "LM2903B", "LM2903BIDR", "Texas Instruments", "Dual comparator, open collector, 2-36 V: " + what, "SOIC-8", "Comparator:LM2903", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
         {1: ("1OUT", a_o), 2: ("1IN-", a_n), 3: ("1IN+", a_p), 4: ("GND", "GND"), 5: ("2IN+", b_p), 6: ("2IN-", b_n), 7: ("2OUT", b_o), 8: ("VCC", vcc)}, B)
    C("100n", vcc, "GND", B)


lm2903("U30", "LOOP_F", "LOOP_VLO", "HEAD_LOOP_OK_RB", "LOOP_VHI", "LOOP_F", "HEAD_LOOP_OK_RB", "V5_AUX", "J1 loop window (outputs wired-AND)")
R("10k", "3V3", "HEAD_LOOP_OK_RB", B, notes="HIGH = loop 0.59-1.55 kohm; drives Q22 and IOX_A GPA5")
R("680", "V5_AUX", "U21_A", B); ssr("U21", "CH_N5", "CH_N6", "U21_A", "U21_K", "HEAD_LOOP"); NFET("Q22", "U21_K", "HEAD_LOOP_OK_RB", "GND", B)
R("10k", "LOOP_F", "HEAD_LOOP_SENSE", B); C("10n", "HEAD_LOOP_SENSE", "GND", B); DIODE("HEAD_LOOP_SENSE", "3V3A", B, "BAT54")
# U22: LAB_KEY_N window on PRES_ID
R("4.7k", "VREF_3V0", "HEAD_PRES_ID", B, tol="0.1%", notes="firmware constant chain.pres_pullup_ohm; no series resistance in the measured path")
R("1k", "HEAD_PRES_ID", "PRES_F", B); C("10n", "PRES_F", "GND", B); ESD2("HEAD_PRES_ID", "J2_PRES", B)
R("10k", "VREF_3V0", "LAB_VHI", B, tol="0.1%"); R("2k", "LAB_VHI", "LAB_VLO", B, tol="0.1%"); R("10k", "LAB_VLO", "GND", B, tol="0.1%")
C("100n", "LAB_VHI", "GND", B); C("100n", "LAB_VLO", "GND", B)
lm2903("U31", "PRES_F", "LAB_VLO", "LAB_KEY_N_RB", "LAB_VHI", "PRES_F", "LAB_KEY_N_RB", "V5_AUX", "PRES_ID window 3.92-5.64 kohm (outputs wired-AND)")
R("10k", "3V3", "LAB_KEY_N_RB", B, notes="HIGH = head without LAB resistor; drives Q28 and IOX_A GPA7")
R("680", "V5_AUX", "U22_A", B); ssr("U22", "CH_N6", "CH_N7", "U22_A", "U22_K", "LAB_KEY_N"); NFET("Q28", "U22_K", "LAB_KEY_N_RB", "GND", B)
R("1k", "PRES_F", "HEAD_PRES_ID_ADC", B, notes="to MCU PC0"); C("1n", "HEAD_PRES_ID_ADC", "GND", B)
# U32: loop-short indicator + cold-charge inhibit
lm2903("U32", "LOOP_F", "LOOP_VHI", "HEAD_LOOP_SHORT_RB", "COLD_THR", "NTC_PACK_ADC", "CHG_TEMP_OK", "V5_AUX", "A: loop short indicator (diverse from U30B); B: charge permitted above +5 C")
R("10k", "3V3", "HEAD_LOOP_SHORT_RB", B, notes="HIGH = loop below window; IOX_A GPA6")
R("4.42k", "VREF_3V0", "COLD_THR", B); R("10k", "COLD_THR", "GND", B, notes="2.08 V = 22.6 kohm = +5.3 C on a 10 k B3435 NTC with 10.0 k pull-up to 3.000 V [C]")
R("1M", "CHG_TEMP_OK", "COLD_THR", B, notes="~2 K hysteresis"); R("10k", "V5_AUX", "CHG_TEMP_OK", B, notes="HIGH = warm enough; gate of Q6. Open sensor reads cold -> no charge")
# U23: watchdog, U24: ARM_PERMIT
part("U40", "TPS3430", "TPS3430WDRCR", "Texas Instruments", "Window watchdog, presets CWD=NC SET0=0 SET1=1: window 2.2-23.4 ms, WDO 200 ms", "VSON-10", None, "Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm",
     {1: ("VDD1", "3V3"), 2: None, 3: ("SET0", "GND"), 4: None, 5: ("GND", "GND"), 6: ("SET1", "3V3"), 7: ("WDI", "WDG_STROBE"), 8: ("WDO", "WDG_OK"), 9: None, 10: ("VDD2", "3V3"), 11: ("EP", "GND")}, B,
     notes="Pin table and timing [D tps3430.pdf]. CWD (2) and CRST (4) open = factory presets. Firmware strobes every 10 ms.")
C("100n", "3V3", "GND", B); R("10k", "3V3", "WDG_OK", B)
R("330", "3V3", "U23_A", B); ssr("U23", "CH_N8", "CH_N9", "U23_A", "U23_K", "WDG_OK"); NFET("Q23", "U23_K", "WDG_OK", "GND", B)
R("10k", "3V3", "WDG_FAULT", B); NFET("Q29", "WDG_FAULT", "WDG_OK", "GND", B, notes="inverter: WDG_FAULT high when WDO is low (heater clamps, FAULT LED)")
DIODE("NRST", "WDG_RST", B, "BAT54", notes="WDO also resets the MCU (firmware request)")
part("JP1", "SJ closed", "SOLDER-JUMPER", "(pcb feature)", "Solder jumper, normally closed: open for SWD halts and ROM-bootloader DFU (the watchdog would reset the MCU every 230 ms)", "SJ",
     "Jumper:SolderJumper_2_Bridged", "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm", {1: ("A", "WDG_RST"), 2: ("B", "WDG_OK")}, B)
R("330", "3V3", "U24_A", B); ssr("U24", "CH_N9", "CHAIN_END", "U24_A", "U24_K", "ARM_PERMIT"); NFET("Q24", "U24_K", "ARM_PERMIT_G", "GND", B)
R("4.7k", "ARM_PERMIT", "GND", B, notes="chain open with the MCU in reset / bootloader / unprogrammed"); R("1k", "ARM_PERMIT", "ARM_PERMIT_G", B)
# latch
part("K1", "G6S-2 DC12", "G6S-2 DC12", "Omron", "Signal relay DPDT 2 A, 12 V coil 1028 ohm 140 mW: LATCH", "RELAY-G6S", "Relay:G6S-2", "Relay_THT:Relay_DPDT_Omron_G6S-2",
     {1: ("COIL+", "K1_COIL_P"), 12: ("COIL-", "COIL_RTN"), 4: ("COM1", "K1_SEAL_A"), 5: ("NO1", "K1_COIL_P"), 3: ("NC1", None) if False else None,
      9: ("COM2", "CHAIN_END"), 8: ("NO2", "RUN_12V"), 10: None}, B,
     notes="Contact pin numbers (COM/NO/NC) recalled, not read [U]. Pole 1 = seal-in, pole 2 = RUN_12V. Operate/release 4 ms max [U].", verify=True)
DIODE("CHAIN_END", "K1_SEAL_A", B, "BAT54", ref="D30", notes="stops C60 feeding the brake relays through the seal-in contact")
R("22k", "CHAIN_END", "SET_CAP", B, ref="R60", notes="a held REARM passes < 0.65 V to the coil"); ECAP("100u", 50, "EEHZA1H101P", "SET_CAP", "GND", B, "C60 set-pulse capacitor (-55 C rated)")
R("0", "K1_SET", "K1_COIL_P", B, notes="REARM contact return")


def coil_clamp(coil_p, coil_n, tag):
    DIODE(coil_n, tag + "_CL", B, "1N4148W"); DIODE(coil_p, tag + "_CL", B, "Z24", notes="coil clamp: diode + 24 V Zener")


coil_clamp("K1_COIL_P", "COIL_RTN", "K1")
tap("CH_N1", "MODE_RUN_RB"); tap("CH_N2", "ESTOP_A_RB"); tap("CH_N3", "HANDS_ON_RB"); tap("CH_N4A", "CHG_COVER_RB"); tap("CH_N4", "CHG_PLUG_LINK_RB")
tap("CH_N5", "HEAD_DOCK_RB"); tap("CH_N8A", "BODY_BUMPER_L_RB"); tap("CH_N8", "BODY_BUMPER_R_RB"); tap("CH_N9", "WDG_OK_RB"); tap("CHAIN_END", "CHAIN_END_RB")
tap("RUN_12V", "HW_LATCH_RB")
for n in ("CH_N6", "CH_N7"):
    TP(n, B, "chain node without a dedicated readback (inferred from the next node)")
# E-stop pole B detector and J2 presence detector: P-FET, HIGH = contact closed to ground
for node, sig, r in (("COIL_RTN", "ESTOP_B_RB", "100k"), ("J2_PRES", "J2_PRES_RB", "10k")):
    g = sig + "_G"
    R(r, node, g, B); R("1M" if node == "COIL_RTN" else "10k", "3V3", g, B, notes="open/unplugged reads LOW"); DIODE(g, "3V3", B, "BAT54"); C("10n", g, "GND", B)
    PFET("Q_" + sig[:6].replace("_", ""), sig, g, "3V3", B); R("10k", sig, "GND", B)
# HANDS-ON lamp from the real chain state
R("0", "CH_N2", "HANDS_LAMP_P", B, notes="lamp supply = chain node upstream of the button; replace by a series resistor if the lamp block needs it")
NFET("Q27", "HANDS_LAMP_K", "LAMP_G", "GND", B); R("100k", "CH_N2", "LAMP_G", B); R("100k", "LAMP_G", "GND", B)
NFET("Q25", "LAMP_G", "HANDS_ON_RB", "GND", B, notes="lamp off while the node after the button is live"); NFET("Q26", "LAMP_G", "HW_LATCH_RB", "GND", B, notes="lamp off while latched")
# REARM / PAUSE auxiliary contacts to IOX_A
R("1k", "3V3", "BTN_3V3", B)
for raw, sig in (("REARM_BTN_RAW", "REARM_BTN"), ("PAUSE_BTN_RAW", "PAUSE_BTN")):
    R("10k", raw, sig, B); R("47k", sig, "GND", B); C("100n", sig, "GND", B)
ESD4("REARM_BTN_RAW", "PAUSE_BTN_RAW", "BTN_3V3", "PACK_PRES_N", B)

# =============================================================================================== DRIVE
B = "drive"
part("U8", "TPS25982", "TPS259822ONRGER", "Texas Instruments", "eFuse 2.7-24 V 15 A 2.7 mohm with current monitor: VMOT switch, enabled only by RUN_12V", "VQFN-24-4x4", None,
     "Package_DFN_QFN:VQFN-24-1EP_4x4mm_P0.5mm (split pad per datasheet)",
     {1: ("IN", "VBAT_SW"), 2: ("IN", "VBAT_SW"), 3: ("IN", "VBAT_SW"), 16: ("IN", "VBAT_SW"), 25: ("IN_PAD", "VBAT_SW"), 4: ("GND", "GND"), 5: ("GND", "GND"), 14: ("GND", "GND"),
      26: ("GND_PAD", "GND"), 6: ("EN/UVLO", "U8_EN"), 7: ("ITIMER", "U8_ITMR"), 8: ("ILIM", "U8_ILIM"), 9: ("IMON", "U8_IMON"), 10: ("RETRY_DLY", "GND"), 11: ("NRETRY", "GND"),
      12: ("LDSTRT", "GND"), 13: ("PG", "VMOT_PG"), 15: ("dVdt", "U8_DVDT"), 17: ("OUT", "VMOT"), 18: ("OUT", "VMOT"), 19: ("OUT", "VMOT"), 20: ("OUT", "VMOT"), 21: ("OUT", "VMOT"),
      22: ("OUT", "VMOT"), 23: ("OUT", "VMOT"), 24: ("OUT", "VMOT")}, B,
     notes="Pin table [D tps25982.pdf]. RETRY_DLY = GND: latch-off after a fault, cleared by re-arming (EN cycle). ILIM = 1546 / R [C from D]. Orderable suffix [U].", verify=True)
R("100k", "RUN_12V", "U8_EN", B); R("22k", "U8_EN", "GND", B, notes="on above ~6.8 V on RUN_12V with a 1.2 V threshold [U]"); C("1n", "U8_EN", "GND", B)
R("237", "U8_ILIM", "GND", B, notes="6.5 A"); R("1.5k", "U8_IMON", "GND", B, notes="0.37 V/A, test point only"); TP("U8_IMON", B)
C("10n", "U8_ITMR", "GND", B); C("10n", "U8_DVDT", "GND", B, notes="soft start a few ms into 810 uF [U]"); R("10k", "3V3", "VMOT_PG", B); TP("VMOT_PG", B)
for _ in range(3):
    ECAP("270u", 35, "EEHZA1V271P", "VMOT", "GND", B, "VMOT bulk, ripple-rated, -55 C")
R("1k", "VMOT", "GND", B, pkg="1206", rating="0.25 W", notes="bleed: 0.21 W at 14.6 V; tau 0.8 s")
R("47k", "VMOT", "VMOT_SENSE", B); R("10k", "VMOT_SENSE", "GND", B); C("100n", "VMOT_SENSE", "GND", B)
part("U9", "74LVC1G08", "SN74LVC1G08DBVR", "Texas Instruments", "AND gate: bridges awake only if MCU DRV_NSLEEP and hardware latch", "SOT-23-5", "74xGxx:74LVC1G08", "Package_TO_SOT_SMD:SOT-23-5",
     {1: ("A", "DRV_NSLEEP"), 2: ("B", "HW_LATCH_RB"), 3: ("GND", "GND"), 4: ("Y", "DRV_NSLEEP_G"), 5: ("VCC", "3V3")}, B)
C("100n", "3V3", "GND", B); R("10k", "DRV_NSLEEP", "GND", B); R("10k", "DRV_NSLEEP_G", "GND", B)
# bus clamp
part("U33", "LM2903B", "LM2903BIDR", "Texas Instruments", "Comparator: bus clamp (A); B unused", "SOIC-8", "Comparator:LM2903", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     {1: ("1OUT", "CLAMP_G"), 2: ("1IN-", "CLAMP_REF"), 3: ("1IN+", "CLAMP_DIV"), 4: ("GND", "GND"), 5: ("2IN+", "GND"), 6: ("2IN-", "CLAMP_REF"), 7: None, 8: ("VCC", "VBAT_SW")}, B,
     notes="powered from VBAT_SW so the clamp works with the logic rails down")
C("100n", "VBAT_SW", "GND", B)
part("U34", "LM4040-2.5", "LM4040C25IDBZR", "Texas Instruments", "Shunt reference 2.5 V 0.5 %", "SOT-23", "Reference_Voltage:LM4040DBZ-2.5", "Package_TO_SOT_SMD:SOT-23",
     {1: ("K", "CLAMP_REF"), 2: ("A", "GND"), 3: None}, B, notes="pin 3 must float", verify=True)
R("10k", "VBAT_SW", "CLAMP_REF", B); C("100n", "CLAMP_REF", "GND", B)
R("100k", "VMOT", "CLAMP_DIV", B); R("19.1k", "CLAMP_DIV", "GND", B, notes="on at 15.6 V"); R("3.3M", "CLAMP_G", "CLAMP_DIV", B, notes="hysteresis ~0.5 V"); C("1n", "CLAMP_DIV", "GND", B)
R("10k", "CLAMP_VG", "CLAMP_G", B); R("4.7k", "VBAT_SW", "CLAMP_VG", B); DIODE("GND", "CLAMP_VG", B, "Z12", notes="10-12 V gate supply")
PWRFET("Q40", "CLAMP_R", "CLAMP_G", "GND", B, kind="3x3", notes="brake chopper switch")
for _ in range(2):
    R("9.1", "CLAMP_F", "CLAMP_R", B, tol="5%", pkg="2512", rating="2 W pulse-rated", mpn="CRM2512-JW-9R1ELF", mfr="Bourns", verify=True, notes="2 in parallel = 4.55 ohm")
part("F4", "1.1A", "1812L110/33GR", "Littelfuse", "PTC 1.1 A hold, 33 V: trips if the clamp sticks on", "1812", "Device:Polyfuse", "Fuse:Fuse_1812_4532Metric",
     {1: ("1", "VMOT"), 2: ("2", "CLAMP_F")}, B, verify=True)
part("W1", "pads", "WIRE-PADS", "(pcb feature)", "Two 2.5 mm wire pads for an optional external clamp resistor (in parallel with the on-board pair)", "PAD-2", "Connector_Generic:Conn_01x02",
     "2 x TestPoint_Pad_2.5x2.5mm", {1: ("1", "CLAMP_F"), 2: ("2", "CLAMP_R")}, B, dnp=True)
R("100k", "CLAMP_G", "BUS_CLAMP_ACTIVE", B); R("33k", "BUS_CLAMP_ACTIVE", "GND", B, notes="HIGH = clamp conducting; IOX_A GPB6")


def bridge(u, side, in1, in2, ipropi, nflt, relay, jref):
    o1, o2, ma, mb = "OUT1_" + side, "OUT2_" + side, "MOT_%s_A" % side, "MOT_%s_B" % side
    part(u, "DRV8874", "DRV8874PWPR", "Texas Instruments", "H-bridge 37 V 6 A peak, 200 mohm, current mirror 450 uA/A", "HTSSOP-16", "Driver_Motor:DRV8874PWPR",
         "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm_ThermalVias",
         {1: ("EN/IN1", in1), 2: ("PH/IN2", in2), 3: ("nSLEEP", "DRV_NSLEEP_G"), 4: ("nFAULT", nflt), 5: ("VREF", "VREF_3V0"), 6: ("IPROPI", ipropi + "_RAW"), 7: ("IMODE", u + "_IMODE"),
          8: ("OUT1", o1), 9: ("PGND", "GND"), 10: ("OUT2", o2), 11: ("VM", "VMOT"), 12: ("VCP", u + "_VCP"), 13: ("CPH", u + "_CPH"), 14: ("CPL", u + "_CPL"), 15: ("GND", "GND"),
          16: ("PMODE", "3V3"), 17: ("EP", "GND")}, B, notes="Pin table and electrical data [D drv8874.pdf]. PMODE high = PWM (IN/IN) mode [D]. IMODE level for fixed-off-time chopping with auto-retry: set per datasheet table [U].")
    R("2.49k", ipropi + "_RAW", "GND", B, tol="0.1%", notes="ITRIP = 3.000 V / (2490 x 450 uA/A) = 2.68 A; 1.1205 V/A")
    R("1k", ipropi + "_RAW", ipropi, B); C("10n", ipropi, "GND", B)
    R("0", u + "_IMODE", "GND", B, notes="IMODE strap (GND); replace per datasheet table"); R("10k", "3V3", nflt, B)
    C("100n", u + "_VCP", "VMOT", B); C("22n", u + "_CPH", u + "_CPL", B); C("100n", "VMOT", "GND", B); C("10u", "VMOT", "GND", B, v=25)
    for n in (in1, in2):
        R("10k", n, "GND", B)
    R("4.7k", o1, "GND", B, pkg="0805", rating="0.125 W", notes="defines the isolated bridge output for the brake readback"); R("4.7k", o2, "GND", B, pkg="0805", rating="0.125 W")
    part(relay, "G2RL-2 DC12", "G2RL-2 DC12", "Omron", "Power relay DPDT 8 A, 12 V coil 360 ohm 400 mW: BRAKE relay %s (de-energised = motor on the brake resistor)" % side, "RELAY-G2RL",
         "Relay:G2RL-2", "Relay_THT:Relay_DPDT_Omron_G2RL-2",
         {1: ("A1", "RUN_12V"), 8: ("A2", "COIL_RTN"), 3: ("COM1", ma), 4: ("NO1", o1), 2: ("NC1", "BRK_%s_A" % side), 6: ("COM2", mb), 5: ("NO2", o2), 7: ("NC2", "BRK_%s_B" % side)}, B,
         notes="Coil data, 15 ms operate / 5 ms release [D en-g2rl.pdf]. Contact pin numbers recalled [U]. 15.7 mm high.", verify=True)
    coil_clamp("RUN_12V", "COIL_RTN", relay)
    R("1", "BRK_%s_A" % side, "BRK_%s_B" % side, B, pkg="2512", rating="2 W pulse-rated", mpn="CRM2512-FX-1R00ELF", mfr="Bourns", verify=True, notes="brake resistor")
    # readback: bias on the motor side, comparators on the bridge side
    DIODE("3V3", "BIAS_" + side, B, "BAT54"); R("2.2k", "BIAS_" + side, ma, B, pkg="0805", rating="0.125 W", notes="motor-side bias for the contact readback")
    cmp_ref = "U35" if side == "L" else "U36"
    R("10k", o1, cmp_ref + "_A", B); R("10k", o2, cmp_ref + "_B", B)
    lm2903(cmp_ref, "BRK_THR", cmp_ref + "_A", "BRAKE_%s_ISO" % side, "BRK_THR", cmp_ref + "_B", "BRAKE_%s_ISO" % side, "V5_AUX",
           "brake relay %s: output HIGH only if both bridge outputs are below 0.2 V (both poles isolated)" % side)
    R("10k", "3V3", "BRAKE_%s_ISO" % side, B)
    NFET("Q4" + ("1" if side == "L" else "2"), "BRAKE_%s_RB" % side, "BRAKE_%s_ISO" % side, "GND", B, notes="inverter: BRAKE_x_RB HIGH = at least one pole connects the motor to the bridge")
    R("10k", "3V3", "BRAKE_%s_RB" % side, B)
    # motor connector: EMI parts at the connector
    for net, pin in ((ma, "MOTC_%s_A" % side), (mb, "MOTC_%s_B" % side)):
        part(_ref("FB"), "50R 6A", "BLM31SN500SN1L", "Murata", "Ferrite bead 50 ohm at 100 MHz, high current", "1206", "Device:FerriteBead", "Inductor_SMD:L_1206_3216Metric",
             {1: ("1", net), 2: ("2", pin)}, B, verify=True)
        C("1n", pin, "GND", B)
    enc5, ea, eb = "ENC_%s_5V" % side, "ENCC_%s_A" % side, "ENCC_%s_B" % side
    MICROFIT(jref, 6, ["MOTC_%s_A" % side, "MOTC_%s_B" % side, enc5, "GND", ea, eb], B,
             "Gearmotor %s: motor pins 1-2, encoder 5 V / GND / A / B pins 3-6 (Pololu #2828 pigtail re-terminated)" % side)
    part(_ref("F"), "0.1A", "1206L010YR", "Littelfuse", "PTC 0.10 A hold: encoder supply", "1206", "Device:Polyfuse", "Fuse:Fuse_1206_3216Metric", {1: ("1", "V5_AUX"), 2: ("2", enc5)}, B, verify=True)
    C("100n", enc5, "GND", B)
    sch = "U37" if side == "L" else "U38"
    part(sch, "74LVC2G17", "SN74LVC2G17DBVR", "Texas Instruments", "Dual Schmitt buffer, 5 V-tolerant inputs: encoder %s" % side, "SOT-23-6", "74xGxx:74LVC2G17", "Package_TO_SOT_SMD:SOT-23-6",
         {1: ("1A", sch + "_A"), 2: ("GND", "GND"), 3: ("2A", sch + "_B"), 4: ("2Y", "ENC_%s_B" % side), 5: ("VCC", "3V3"), 6: ("1Y", "ENC_%s_A" % side)}, B, notes="[D sn74lvc2g17.pdf not re-read; standard pinout]")
    C("100n", "3V3", "GND", B)
    for raw, f in ((ea, sch + "_A"), (eb, sch + "_B")):
        R("10k", enc5, raw, B, notes="5 V pull-up"); R("4.7k", raw, f, B); C("1n", f, "GND", B, notes="tau 4.7 us; max edge rate 10.7 kHz")
    return ea, eb


ea_l, eb_l = bridge("U5", "L", "MOT_L_IN1", "MOT_L_IN2", "IPROPI_L", "DRV_L_NFAULT", "K2", "J_MOT_L")
ea_r, eb_r = bridge("U6", "R", "MOT_R_IN1", "MOT_R_IN2", "IPROPI_R", "DRV_R_NFAULT", "K3", "J_MOT_R")
ESD4(ea_l, eb_l, ea_r, eb_r, B, notes="encoder lines (5 V)")
R("14k", "V5_AUX", "BRK_THR", B); R("590", "BRK_THR", "GND", B, notes="0.20 V threshold"); C("100n", "BRK_THR", "GND", B)

# =============================================================================================== MCU
B = "mcu"
MCU = {1: ("VBAT", "3V3"), 2: ("PC13", "WDG_OK_RB"), 3: ("PC14", "BRAKE_L_RB"), 4: ("PC15", "BRAKE_R_RB"), 5: ("PF0-OSC_IN", "OSC_IN"), 6: ("PF1-OSC_OUT", "OSC_OUT"),
       7: ("PG10-NRST", "NRST"), 8: ("PC0", "HEAD_PRES_ID_ADC"), 9: ("PC1", "HEAD_LOOP_SENSE"), 10: ("PC2", "NTC_BAY_ADC"), 11: ("PC3", "NTC_PACK_ADC"), 12: ("PA0", "IPROPI_L"),
       13: ("PA1", "IPROPI_R"), 14: ("PA2", "VMOT_SENSE"), 15: ("VSS", "GND"), 16: ("VDD", "3V3"), 17: ("PA3", "VBAT_SENSE"), 18: ("PA4", "IMU_CS_ACC_N"), 19: ("PA5", "SPI1_SCK"),
       20: ("PA6", "SPI1_MISO"), 21: ("PA7", "SPI1_MOSI"), 22: ("PC4", "NTC_BOARD_ADC"), 23: ("PC5", "IMU_CS_GYR_N"), 24: ("PB0", "IOX_A_CS_N"), 25: ("PB1", "V5_SENSE"),
       26: ("PB2", "BUZZER"), 27: ("VSSA", "GND"), 28: ("VREF+", "VREF_3V0"), 29: ("VDDA", "3V3A"), 30: ("PB10", "ARM_PERMIT"), 31: ("VSS", "GND"), 32: ("VDD", "3V3"),
       33: ("PB11", "WDG_STROBE"), 34: ("PB12", "ESTOP_A_RB"), 35: ("PB13", "ESTOP_B_RB"), 36: ("PB14", "HEAD_HTR_EN"), 37: ("PB15", "CHS_HTR_EN"), 38: ("PC6", "MOT_L_IN1"),
       39: ("PC7", "MOT_L_IN2"), 40: ("PC8", "MOT_R_IN1"), 41: ("PC9", "MOT_R_IN2"), 42: ("PA8", "I2C_SYS_SDA"), 43: ("PA9", "I2C_SYS_SCL"), 44: ("PA10", "DRV_NSLEEP"),
       45: ("PA11", "MCU_USB_DM"), 46: ("PA12", "MCU_USB_DP"), 47: ("VSS", "GND"), 48: ("VDD", "3V3"), 49: ("PA13", "SWDIO"), 50: ("PA14", "SWCLK"), 51: ("PA15", "I2C_TOF_SCL"),
       52: ("PC10", "DBG_TX"), 53: ("PC11", "DBG_RX"), 54: ("PC12", "J2_PRES_RB"), 55: ("PD2", "HW_LATCH_RB"), 56: ("PB3", "SWO_SPARE"), 57: ("PB4", "ENC_R_A"), 58: ("PB5", "ENC_R_B"),
       59: ("PB6", "ENC_L_A"), 60: ("PB7", "ENC_L_B"), 61: ("PB8-BOOT0", "BOOT0_LED_STAT"), 62: ("PB9", "I2C_TOF_SDA"), 63: ("VSS", "GND"), 64: ("VDD", "3V3")}
part("U20M", "STM32G474RET6", "STM32G474RET6", "STMicroelectronics", "Motion MCU, LQFP64", "LQFP-64", "MCU_ST_STM32G4:STM32G474RETx", "Package_QFP:LQFP-64_10x10mm_P0.5mm", MCU, B,
     notes="Pin assignment = firmware/chassis/pinmap.yaml (tool-checked by the firmware lead against ST open pin data). LQFP64 pin numbers as in that file.")
for _ in range(4):
    C("100n", "3V3", "GND", B)
C("4.7u", "3V3", "GND", B, v=16); C("100n", "VREF_3V0", "GND", B); C("1u", "VREF_3V0", "GND", B, v=16)
part("Y1", "8MHz", "NX3225GD-8.000M-STD-CRA-3", "NDK", "Crystal 8 MHz, 8 pF, 3.2x2.5 mm, -40..+125 C", "XTAL-3225", "Device:Crystal_GND24", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
     {1: ("1", "OSC_IN"), 2: ("GND", "GND"), 3: ("3", "OSC_XO"), 4: ("GND", "GND")}, B, verify=True)
C("10p", "OSC_IN", "GND", B); C("10p", "OSC_XO", "GND", B); R("220", "OSC_OUT", "OSC_XO", B)
C("100n", "NRST", "GND", B); R("10k", "3V3", "NRST", B)
part("SW1", "RESET", "PTS636 SM25F SMTR LFS", "C&K", "Tactile switch 2.5 mm high", "SOT-23", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_PTS636", {1: ("1", "NRST"), 2: ("2", "GND")}, B, verify=True)
part("SW2", "DFU", "PTS636 SM25F SMTR LFS", "C&K", "Tactile switch: hold at reset for the ROM bootloader (open JP1 first)", "SOT-23", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_PTS636",
     {1: ("1", "3V3"), 2: ("2", "BOOT0_SW")}, B, verify=True)
R("1k", "BOOT0_SW", "BOOT0_LED_STAT", B); R("1k", "BOOT0_LED_STAT", "LED_STAT_A", B)
part("LED1", "green", "150060GS75000", "Wurth Elektronik", "LED 0603 green: heartbeat (also holds BOOT0 low)", "0603", "Device:LED", "LED_SMD:LED_0603_1608Metric", {1: ("K", "GND"), 2: ("A", "LED_STAT_A")}, B)
part("J_SWD", "Cortex debug 2x5 1.27", "FTSH-105-01-L-DV-K", "Samtec", "SWD: 1 VTref, 2 SWDIO, 3 GND, 4 SWCLK, 5 GND, 6 SWO, 7 key, 8 NC, 9 GND, 10 NRST", "HDR-1.27-2x5",
     "Connector:Conn_ARM_JTAG_SWD_10", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
     {1: ("VTref", "3V3"), 2: ("SWDIO", "SWDIO"), 3: ("GND", "GND"), 4: ("SWCLK", "SWCLK"), 5: ("GND", "GND"), 6: ("SWO", "SWO_SPARE"), 7: None, 8: None, 9: ("GNDDetect", "GND"), 10: ("nRESET", "NRST")}, B)
GH("J_DBG", 4, ["DBG_3V3", "DBG_TX_C", "DBG_RX_C", "GND"], B, "Debug UART 115200 8N1, 3.3 V")
R("100", "3V3", "DBG_3V3", B); R("220", "DBG_TX", "DBG_TX_C", B); R("220", "DBG_RX_C", "DBG_RX", B); R("10k", "3V3", "DBG_RX", B)
# USB FS to the CM5 (chassis link)
GH("J_USB_MCU", 5, [None, "MCUC_USB_DM", "MCUC_USB_DP", "GND", "USB_SHLD"], B, "USB FS device (MCU) to a CM5 carrier host port: 1 VBUS (unused), 2 D-, 3 D+, 4 GND, 5 shield")
part("U41", "USBLC6-2SC6", "USBLC6-2SC6", "STMicroelectronics", "USB ESD protection", "SOT-23-6", "Power_Protection:USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
     {1: ("I/O1", "MCUC_USB_DM"), 2: ("GND", "GND"), 3: ("I/O2", "MCUC_USB_DP"), 4: ("I/O2", "MCU_USB_DP"), 5: ("VBUS", "3V3"), 6: ("I/O1", "MCU_USB_DM")}, B)
R("1M", "USB_SHLD", "GND", B); C("10n", "USB_SHLD", "GND", B)
# IMU
part("U42", "BMI088", "BMI088", "Bosch Sensortec", "6-axis IMU, SPI, -40..+85 C; centre at board (80, 67) mm = yaw centre", "LGA-16", "Sensor_Motion:BMI088", "Package_LGA:Bosch_LGA-16_4.5x3mm_P0.5mm",
     {1: None, 2: None, 3: ("VDD", "3V3"), 4: ("GNDA", "GND"), 5: ("CSB2", "IMU_CS_GYR_N"), 6: ("GNDIO", "GND"), 7: ("PS", "GND"), 8: ("SCK", "SPI1_SCK"), 9: ("SDI", "SPI1_MOSI"),
      10: ("SDO2", "IMU_SDO"), 11: ("VDDIO", "3V3"), 12: None, 13: None, 14: ("CSB1", "IMU_CS_ACC_N"), 15: ("SDO1", "IMU_SDO"), 16: None}, B,
     notes="Pin numbers recalled from the Bosch datasheet [U]. Interrupt pins unused (polled at 1 kHz per pin map).", verify=True)
R("33", "IMU_SDO", "SPI1_MISO", B); C("100n", "3V3", "GND", B); C("100n", "3V3", "GND", B)
R("10k", "3V3", "IMU_CS_ACC_N", B); R("10k", "3V3", "IMU_CS_GYR_N", B); R("10k", "3V3", "IOX_A_CS_N", B)
# expanders
IOXA = ["MODE_RUN_RB", "HANDS_ON_RB", "CHG_COVER_RB", "CHG_PLUG_LINK_RB", "HEAD_DOCK_RB", "HEAD_LOOP_OK_RB", "HEAD_LOOP_SHORT_RB", "LAB_KEY_N_RB",
        "BODY_BUMPER_L_RB", "BODY_BUMPER_R_RB", "REARM_BTN", "PAUSE_BTN", "DRV_L_NFAULT", "DRV_R_NFAULT", "BUS_CLAMP_ACTIVE", "WDG_STROBE"]
pa = {21 + i: ("GPA%d" % i, IOXA[i]) for i in range(8)}
pa.update({1 + i: ("GPB%d" % i, IOXA[8 + i]) for i in range(8)})
pa.update({9: ("VDD", "3V3"), 10: ("VSS", "GND"), 11: ("CS", "IOX_A_CS_N"), 12: ("SCK", "SPI1_SCK"), 13: ("SI", "SPI1_MOSI"), 14: ("SO", "IOXA_SO"), 15: ("A0", "GND"), 16: ("A1", "GND"),
           17: ("A2", "GND"), 18: ("RESET", "NRST"), 19: None, 20: None})
part("U43", "MCP23S17", "MCP23S17-E/SS", "Microchip", "IOX_A: 16-bit SPI expander, all inputs, read every 1 ms", "SSOP-28", "Interface_Expansion:MCP23S17_SS", "Package_SO:SSOP-28_5.3x10.2mm_P0.65mm", pa, B,
     notes="Pin numbers recalled (same as MCP23017 with SPI pins) [U]. INTA/INTB unused.", verify=True)
R("33", "IOXA_SO", "SPI1_MISO", B); C("100n", "3V3", "GND", B)
IOXB = ["LED_READY", "LED_MOVING", "LED_HOLD", "LED_FAULT", "LED_CHARGE", "LAMP_REARM", "LAMP_PAUSE", "LED_STAT2",
        "HEAD_PWR_EN", "V12_LIDAR_EN", "V5_CM5_OFF_REQ", "TOF_XSHUT_CLIFF", "TOF_XSHUT_LOOK", "TOF_XSHUT_REAR", "TOF_MUX_NRST", "CHAIN_END_RB"]
pb = {4 + i: ("P0%d" % i, IOXB[i]) for i in range(8)}
pb.update({13 + i: ("P1%d" % i, IOXB[8 + i]) for i in range(8)})
pb.update({1: None, 2: ("A1", "GND"), 3: ("A2", "GND"), 12: ("GND", "GND"), 21: ("A0", "GND"), 22: ("SCL", "I2C_SYS_SCL"), 23: ("SDA", "I2C_SYS_SDA"), 24: ("VCC", "3V3")})
part("U44", "TCA9535", "TCA9535PWR", "Texas Instruments", "IOX_B: 16-bit I2C expander 0x20, outputs; no reset pin (outside the NRST domain)", "TSSOP-24", "Interface_Expansion:TCA9535PWR",
     "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm", pb, B, notes="Pin numbers recalled [U]. P17 (SPARE_OUT in the pin map) carries CHAIN_END_RB as an INPUT: see CCR-E02.", verify=True)
C("100n", "3V3", "GND", B)
for n in ("TOF_XSHUT_CLIFF", "TOF_XSHUT_LOOK", "TOF_XSHUT_REAR", "TOF_MUX_NRST"):
    R("100k", n, "GND", B, notes="default low")
IOXC = ["HEAD_PWR_NFLT", "HEAD_HTR_NFLT", "CHS_HTR_NFLT", "V12_LIDAR_NFLT", "V5_CM5_NFLT", "CHG_NSMBALERT", "PMON_NALERT", "V5_PGOOD"]
pc = {4: ("P0", IOXC[0]), 5: ("P1", IOXC[1]), 6: ("P2", IOXC[2]), 7: ("P3", IOXC[3]), 9: ("P4", IOXC[4]), 10: ("P5", IOXC[5]), 11: ("P6", IOXC[6]), 12: ("P7", IOXC[7]),
      1: ("A0", "3V3"), 2: ("A1", "GND"), 3: ("A2", "GND"), 8: ("GND", "GND"), 13: None, 14: ("SCL", "I2C_SYS_SCL"), 15: ("SDA", "I2C_SYS_SDA"), 16: ("VCC", "3V3")}
part("U45", "TCA9534", "TCA9534PWR", "Texas Instruments", "IOX_C: 8-bit I2C expander 0x21, inputs", "TSSOP-16", "Interface_Expansion:TCA9534PWR", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", pc, B,
     notes="Pin numbers recalled [U].", verify=True)
C("100n", "3V3", "GND", B); R("10k", "3V3", "PMON_NALERT", B)
for n in ("I2C_SYS_SDA", "I2C_SYS_SCL", "I2C_TOF_SDA", "I2C_TOF_SCL"):
    R("2.2k", "3V3", n, B)
# NTC inputs
for sig, src in (("NTC_BAY_ADC", "NTC_BAY"), ("NTC_PACK_ADC", "NTC_PACK"), ("NTC_BOARD_ADC", "NTC_BOARD_ADC")):
    R("10k", "VREF_3V0", src, B, tol="0.1%")
    if src != sig:
        R("1k", src, sig, B)
    C("100n", sig, "GND", B)
part("RT1", "10k NTC", "NCP18XH103F03RB", "Murata", "NTC 10 k 1 % B3380, 0603: board temperature next to the H-bridges", "0603", "Device:Thermistor_NTC", "Resistor_SMD:R_0603_1608Metric",
     {1: ("1", "NTC_BOARD_ADC"), 2: ("2", "GND")}, B, verify=True)
GH("J_NTC", 4, ["NTC_BAY", "GND", "NTC_PACK", "GND"], B, "Bay air NTC and pack-surface NTC (10 k, B3435)")
ESD4("NTC_BAY", "NTC_PACK", "DBG_TX_C", "DBG_RX_C", B)
MICROFIT("J_HTR", 2, ["CHS_HTR_P", "GND"], "branches", "Chassis/bay heater (20 W, 7.2 ohm). The independent bimetal cut-out is in series in this harness, on the heater plate")
MICROFIT("J_LIDAR", 2, ["V12_LIDAR", "GND"], "branches", "LiDAR supply 10-14.6 V, 1.5 A limit")
MICROFIT("J_CM5", 4, ["V5_CM5", "V5_CM5", "GND", "GND"], "rails", "CM5 carrier 5.1 V feed, two contacts per pole")
GH("J_AUX", 3, ["V12_AUX", "GND", "SPARE_IO"], B, "Fan / spare: 12 V (0.35 A PTC), GND, spare 3.3 V I/O (PB3 through JP2)")
part("F5", "0.35A", "1206L035YR", "Littelfuse", "PTC 0.35 A hold: V12_AUX (lamps, fan, external sounder)", "1206", "Device:Polyfuse", "Fuse:Fuse_1206_3216Metric", {1: ("1", "VBAT_SW"), 2: ("2", "V12_AUX")}, B, verify=True)
part("JP2", "SJ open", "SOLDER-JUMPER", "(pcb feature)", "Solder jumper, normally open: PB3 (SWO) to the spare I/O pin", "SJ", "Jumper:SolderJumper_2_Open",
     "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", {1: ("A", "SWO_SPARE"), 2: ("B", "SPARE_IO_R")}, B)
R("1k", "SPARE_IO_R", "SPARE_IO", B)

# =============================================================================================== ToF buses
B = "tof"
TOF = [  # firmware id, mux, channel, xshut group, connector zone
    ("CLIFF_FL", 0, 0, "CLIFF", "front edge"), ("CLIFF_FR", 1, 0, "CLIFF", "front edge"), ("CLIFF_RL", 0, 1, "CLIFF", "rear-left corner"), ("CLIFF_RR", 1, 1, "CLIFF", "rear-left corner"),
    ("LOOK_LO", 0, 2, "LOOK", "left edge front"), ("LOOK_LI", 1, 2, "LOOK", "left edge front"), ("LOOK_RI", 0, 3, "LOOK", "right edge front"), ("LOOK_RO", 1, 3, "LOOK", "right edge front"),
    ("REAR_L", 0, 4, "REAR", "rear-left corner"), ("REAR_C", 1, 4, "REAR", "rear-left corner"), ("REAR_R", 0, 5, "REAR", "rear-left corner")]
for m in (0, 1):
    pins = {1: ("A0", "3V3" if m else "GND"), 2: ("A1", "GND"), 3: ("RESET", "TOF_MUX_NRST"), 12: ("GND", "GND"), 21: ("A2", "GND"), 22: ("SCL", "I2C_TOF_SCL"), 23: ("SDA", "I2C_TOF_SDA"), 24: ("VCC", "3V3")}
    chpins = {0: (4, 5), 1: (6, 7), 2: (8, 9), 3: (10, 11), 4: (13, 14), 5: (15, 16), 6: (17, 18), 7: (19, 20)}
    used = {c for (_i, mm, c, _g, _z) in TOF if mm == m}
    for ch, (sd, sc) in chpins.items():
        if ch in used:
            pins[sd], pins[sc] = ("SD%d" % ch, "TOF%d%d_SDA" % (m, ch)), ("SC%d" % ch, "TOF%d%d_SCL" % (m, ch))
        else:
            pins[sd], pins[sc] = None, None
    part("U5%d" % m, "TCA9548A", "TCA9548APWR", "Texas Instruments", "8-channel I2C switch, 0x7%d" % m, "TSSOP-24", "Interface_Expansion:TCA9548APWR", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm", pins, B,
         notes="Pin table [D tca9548a.pdf]. Unused channels left open.")
    C("100n", "3V3", "GND", B)
for i, (tid, m, ch, grp, zone) in enumerate(TOF):
    j = "J_TOF%d" % i
    v, sda, scl, xs, g1 = "TOF%d_3V3" % i, "TOF%d_SDA_C" % i, "TOF%d_SCL_C" % i, "TOF%d_XSHUT_C" % i, "TOF%d_GPIO1" % i
    GH(j, 6, [v, "GND", sda, scl, xs, g1], B, "RR-TOF %s (mux %d ch %d), %s. Pin order as RR-TOF-A J1" % (tid, m, ch, zone))
    part(_ref("FB"), "600R", "BLM18KG601SN1D", "Murata", "Ferrite bead: ToF supply", "0603", "Device:FerriteBead", "Inductor_SMD:L_0603_1608Metric", {1: ("1", "3V3"), 2: ("2", v)}, B, verify=True)
    C("100n", v, "GND", B)
    R("100", "TOF%d%d_SDA" % (m, ch), sda, B); R("100", "TOF%d%d_SCL" % (m, ch), scl, B)
    R("2.2k", "3V3", "TOF%d%d_SDA" % (m, ch), B); R("2.2k", "3V3", "TOF%d%d_SCL" % (m, ch), B)
    R("1k", "TOF_XSHUT_" + grp, xs, B, notes="a shorted cable cannot pull the group low")
    ESD4(sda, scl, xs, g1, B)
    TP(g1, B, "GPIO1 interrupt: not used by firmware, pad only")

# =============================================================================================== HEAD LINK (USB-UART + RS-485) and J1/J2 landings
B = "head_link"
GH("J_USB_HEAD", 5, ["HUSB_VBUS", "HUSBC_DM", "HUSBC_DP", "GND", "USB_SHLD"], B, "USB FS device (FT230X) to a second CM5 carrier host port: 1 VBUS, 2 D-, 3 D+, 4 GND, 5 shield")
part("U60", "USBLC6-2SC6", "USBLC6-2SC6", "STMicroelectronics", "USB ESD protection", "SOT-23-6", "Power_Protection:USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
     {1: ("I/O1", "HUSBC_DM"), 2: ("GND", "GND"), 3: ("I/O2", "HUSBC_DP"), 4: ("I/O2", "HUSB_DP_R"), 5: ("VBUS", "HUSB_VBUS"), 6: ("I/O1", "HUSB_DM_R")}, B)
part("FB_U", "600R", "BLM18KG601SN1D", "Murata", "Ferrite bead: FT230X supply from host VBUS", "0603", "Device:FerriteBead", "Inductor_SMD:L_0603_1608Metric", {1: ("1", "HUSB_VBUS"), 2: ("2", "FT_VCC")}, B, verify=True)
part("U61", "FT230XS", "FT230XS-R", "FTDI", "USB FS to UART bridge, bus-powered, CBUS0 = TXDEN (RS-485 direction), 1 Mbaud = 3 MHz / 3 exact", "SSOP-16", "Interface_USB:FT230XS", "Package_SO:SSOP-16_3.9x4.9mm_P0.635mm",
     {1: ("TXD", "FT_TXD"), 2: None, 3: ("VCCIO", "FT_3V3"), 4: ("RXD", "FT_RXD"), 5: ("GND", "GND"), 6: ("CTS#", "GND"), 7: ("CBUS2", "FT_LED_N"), 8: ("USBDP", "FT_DP"), 9: ("USBDM", "FT_DM"),
      10: ("3V3OUT", "FT_3V3"), 11: ("RESET#", "FT_VCC"), 12: ("VCC", "FT_VCC"), 13: ("GND", "GND"), 14: None, 15: ("CBUS0", "FT_TXDEN"), 16: None}, B,
     notes="Pin numbers recalled [U]; CBUS0 = TXDEN is the factory default [U], confirm or program the EEPROM (FT_PROG). TXDEN timing taken from the FT232R description (one bit before the start bit, released at the end of the stop bit) [U]. "
           "Host: set latency_timer to 1 ms (ftdi_sio sysfs).", verify=True)
R("27", "HUSB_DP_R", "FT_DP", B); R("27", "HUSB_DM_R", "FT_DM", B); C("47p", "FT_DP", "GND", B); C("47p", "FT_DM", "GND", B)
C("4.7u", "FT_VCC", "GND", B, v=16); C("100n", "FT_VCC", "GND", B); C("100n", "FT_3V3", "GND", B)
R("1k", "FT_3V3", "FT_LED_A", B); part("LED2", "green", "150060GS75000", "Wurth Elektronik", "LED 0603: head-link traffic", "0603", "Device:LED", "LED_SMD:LED_0603_1608Metric", {1: ("K", "FT_LED_N"), 2: ("A", "FT_LED_A")}, B)
part("U62", "THVD1450", "THVD1450DR", "Texas Instruments", "RS-485 transceiver 3-5.5 V, 50 Mbit/s, +/-18 kV IEC contact ESD; powered from V5_AUX", "SOIC-8", "Interface_UART:THVD1450D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     {1: ("R", "RS_RO"), 2: ("RE", "FT_TXDEN_R"), 3: ("DE", "FT_TXDEN_R"), 4: ("D", "FT_TXD_R"), 5: ("GND", "GND"), 6: ("A", "RS_A"), 7: ("B", "RS_B"), 8: ("VCC", "V5_AUX")}, B,
     notes="Timing [D thvd1450.pdf]: enable <= 500 ns class, disable <= 200 ns. A = non-inverting = RS485_DP.")
C("100n", "V5_AUX", "GND", B); R("1k", "FT_TXD", "FT_TXD_R", B, notes="limits back-feed when only one side is powered"); R("1k", "FT_TXDEN", "FT_TXDEN_R", B); R("10k", "FT_TXDEN_R", "GND", B, notes="receive by default")
R("10k", "V5_AUX", "FT_TXD_R", B, notes="idle mark when the bridge is unpowered")
R("10k", "RS_RO", "FT_RXD", B); R("20k", "FT_RXD", "GND", B, notes="5 V -> 3.3 V; with the receiver disabled during transmit RXD idles LOW: see note"); R("47k", "V5_AUX", "RS_RO", B, notes="keeps RXD at mark while RE is high")
R("120", "RS_A", "RS_B", B, pkg="0805", rating="0.125 W", notes="termination (chassis end)")
R("560", "V5_AUX", "RS_A", B, pkg="0805", rating="0.125 W", notes="fail-safe bias, chassis end only: 254 mV into 60 ohm [C]"); R("560", "RS_B", "GND", B, pkg="0805", rating="0.125 W")
R("10", "RS_A", "RS_A_L", B, pkg="0805", rating="0.125 W", notes="pulse-proof series"); R("10", "RS_B", "RS_B_L", B, pkg="0805", rating="0.125 W")
part("L60", "CMC 90R", "ACM2012-900-2P-T002", "TDK", "Common-mode choke 90 ohm at 100 MHz, 0805", "0805", "Device:L_Coupled_1243", "Inductor_SMD:L_CommonModeChoke_TDK_ACM2012",
     {1: ("1", "RS_A_L"), 2: ("2", "RS485_DP"), 3: ("3", "RS485_DN"), 4: ("4", "RS_B_L")}, B, notes="pin pairing 1-2 / 4-3 to be confirmed against the footprint [U]", verify=True)
part("D60", "SM712", "SM712.TCT", "Semtech", "RS-485 TVS, asymmetric +12 / -7 V", "SOT-23", "Power_Protection:SM712_SOT23", "Package_TO_SOT_SMD:SOT-23", {1: ("IO1", "RS485_DP"), 2: ("IO2", "RS485_DN"), 3: ("GND", "GND")}, B)
# reserved sync driver (DNP)
part("U63", "THVD1450", "THVD1450DR", "Texas Instruments", "RESERVED hardware time-pulse driver for J2 pins 5/6 (DNP in rev A)", "SOIC-8", "Interface_UART:THVD1450D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     {1: None, 2: ("RE", "V5_AUX"), 3: ("DE", "V5_AUX"), 4: ("D", "SYNC_TTL"), 5: ("GND", "GND"), 6: ("A", "SYNC_P"), 7: ("B", "SYNC_N"), 8: ("VCC", "V5_AUX")}, B, dnp=True)
R("120", "SYNC_P", "SYNC_N", B, pkg="0805", dnp=True); R("10k", "SYNC_TTL", "GND", B, dnp=True); TP("SYNC_TTL", B, "reserved")
GH("J_HEAD2", 8, ["RS485_DP", "RS485_DN", "BUS_5V", "GND", "SYNC_P", "SYNC_N", "J2_PRES", None], B, "J2 HEAD DATA landing: pin n = J2 pin n (M12 A-coded 8-pole receptacle on a 150 mm lead)", side=True)
MICROFIT("J_HEAD1", 8, ["HEAD_PWR_P", "GND", "HEAD_HTR_P", "HEAD_HTR_N", "HEAD_LOOP_OUT", "HEAD_LOOP_RET", "HEAD_PRES_ID", None], B,
         "J1 HEAD POWER / INTERLOCK landing: pin n = J1 pin n (M16 8-pole receptacle on a 150 mm lead)")
part("NT1", "net tie", "NET-TIE", "(pcb feature)", "Net tie: heater return joins GND only at the VBAT_SW bulk capacitor", "SJ", "Device:NetTie_2", "NetTie:NetTie-2_SMD_Pad2.0mm",
     {1: ("1", "HEAD_HTR_N"), 2: ("2", "GND")}, B)

# =============================================================================================== PANEL / LAMP DRIVERS
B = "panel_io"
GH("J_PANEL", 10, ["V5_AUX", "V12_AUX", "GND", "LED_READY_K", "LED_MOVING_K", "LED_HOLD_K", "LED_FAULT_K", "LED_CHARGE_K", "BUZ_N", "GND"], B, "RR-PANEL: supplies, five LED cathodes, buzzer low side")
for i, sig in enumerate(["LED_READY", "LED_MOVING", "LED_HOLD", "LED_FAULT", "LED_CHARGE", "LAMP_REARM", "LAMP_PAUSE"]):
    NFET("Q5%d" % i, sig + "_K", sig, "GND", B); R("100k", sig, "GND", B)
NFET("Q57", "LED_FAULT_K", "WDG_FAULT", "GND", B, notes="FAULT LED lit by hardware whenever the watchdog is not satisfied")
NFET("Q58", "BUZ_N", "BUZZER", "GND", B); R("10k", "BUZZER", "GND", B)
R("1k", "3V3", "LED_STAT2_A", B); part("LED3", "red", "150060RS75000", "Wurth Elektronik", "LED 0603: protocol activity (IOX_B P07, active low sink)", "0603", "Device:LED", "LED_SMD:LED_0603_1608Metric",
                                        {1: ("K", "LED_STAT2"), 2: ("A", "LED_STAT2_A")}, B)

# =============================================================================================== TEST POINTS, HOLES, FIDUCIALS
for n in ("WDG_STROBE", "WDG_OK", "ARM_PERMIT", "HW_LATCH_RB", "VMOT_SENSE", "IPROPI_L", "IPROPI_R", "SPI1_SCK", "SPI1_MISO", "SPI1_MOSI", "I2C_SYS_SDA", "I2C_SYS_SCL", "I2C_TOF_SDA",
          "I2C_TOF_SCL", "CHAIN_END", "RUN_12V", "COIL_RTN", "VBAT_SW", "VSYS", "V5_CM5", "3V3", "V5_AUX", "VREF_3V0", "VMOT", "GND", "GND", "CH_N0", "EN_SYS", "LOOP_F", "PRES_F",
          "CHG_TEMP_OK", "CLAMP_G", "FT_TXDEN", "RS_RO", "U3_NTC", "V12_AUX"):
    TP(n)
MECH = {
    "outline_mm": (160.0, 100.0), "corner_radius_mm": 2.0, "thickness_mm": 1.6, "layers": 4,
    "frame": "origin rear-left corner seen from above, +u toward robot right, +v forward (mechanical/common/board_envelopes.yaml)",
    "holes_uv_mm": {"H1": (4.0, 4.0), "H2": (80.0, 4.0), "H3": (156.0, 4.0), "H4": (4.0, 96.0), "H5": (80.0, 96.0), "H6": (156.0, 96.0)},
    "hole_diameter_mm": 3.2, "hole_keepout_diameter_mm": 7.0, "max_height_top_mm": 18.0, "max_height_bottom_mm": 3.0,
    "front_corner_low_zones": {"u": [(0, 14), (146, 160)], "v": (88, 100), "top_max_mm": 12.0},
    "thermal_zone_uv": {"u": (50, 110), "v": (30, 70)}, "imu_centre_uv": (80.0, 67.0),
}
for h, (u, v) in MECH["holes_uv_mm"].items():
    part(h, "M3", "MOUNTING-HOLE-M3", "(pcb feature)", "Mounting hole 3.2 mm, plated pad, at (%.0f, %.0f) mm; H1/H3 tie GND to the bridge tray, others isolated via 1 Mohm || 10 nF option" % (u, v),
         "HOLE-M3", "Mechanical:MountingHole_Pad", "MountingHole:MountingHole_3.2mm_M3_Pad_Via", {1: ("1", "GND" if h in ("H1", "H3") else "CHASSIS_" + h)}, "mech")
    if h not in ("H1", "H3"):
        R("1M", "CHASSIS_" + h, "GND", "mech"); C("10n", "CHASSIS_" + h, "GND", "mech")
for i, (u, v) in enumerate([(12.0, 12.0), (148.0, 12.0), (12.0, 84.0)]):
    part("FID%d" % (i + 1), "fiducial", "FIDUCIAL", "(pcb feature)", "Fiducial 1 mm at (%.0f, %.0f)" % (u, v), "FID", "Mechanical:Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", {}, "mech")

# =============================================================================================== NETS, CLASSES, CONNECTOR TABLES
def build_nets(parts):
    nets = {}
    for p in parts:
        for num, v in p["pins"].items():
            if v is None:
                continue
            nets.setdefault(v[1], []).append((p["ref"], num, v[0]))
    return nets


NETS = build_nets(PARTS)

NET_CLASSES = {
    "HC_PACK": dict(amps=20, nets=["VBAT_RAW", "PSW_SRC", "VBAT_PROT", "VBAT_SW", "GND"], rule="polygon pours on L1+L4 stitched, >= 12 mm equivalent width on 35 um outer copper (20 A, 20 K rise); shortest path J_PWR -> Q1/Q2 -> R_SH1"),
    "HC_VMOT": dict(amps=8, nets=["VMOT", "OUT1_L", "OUT2_L", "OUT1_R", "OUT2_R", "MOT_*", "MOTC_*", "BRK_*", "CLAMP_F", "CLAMP_R"], rule=">= 2.5 mm, pours preferred; bridge-relay-connector path short and paired"),
    "HC_BRANCH": dict(amps=5, nets=["HEAD_HTR_F", "HEAD_HTR_P", "HEAD_HTR_N", "CHS_HTR_F", "CHS_HTR_P", "V5_BUCK", "V5_CM5", "VSYS", "CHG_IN", "CHG_F", "CHG_VIN", "U3_CLP", "U3_CSP"], rule=">= 1.5 mm (5 A, outer layer)"),
    "PWR_1A5": dict(amps=1.5, nets=["HEAD_PWR_F", "HEAD_PWR_P", "V12_LIDAR", "3V3", "V5_AUX", "3V3A", "V12_AUX", "BUS_5V", "TOF*_3V3", "ENC_*_5V"], rule=">= 0.5 mm"),
    "SAFETY_CHAIN": dict(amps=0.2, nets=["CH_N*", "CHAIN_END", "RUN_12V", "COIL_RTN", "K1_*", "SET_CAP", "K?_CL", "HANDS_LAMP_*"],
                         rule="0.4 mm, >= 0.5 mm clearance to every other net, >= 1.0 mm to VBAT_SW/VMOT/VSYS copper (a bridge to +12 V bypasses elements); route as one visible group on L1, no vias under relays; no pours between chain pads"),
    "SWITCHING": dict(nets=["U3_SW", "U3_BOOST", "U10_SW", "U10_CBOOT", "U10_RBOOT", "U11_SW", "U11_CB", "U12_SW", "U12_CB", "U5_CPH", "U5_CPL", "U6_CPH", "U6_CPL", "U5_VCP", "U6_VCP"],
                      rule="minimum copper area, component side only, hot loops (VIN cap - IC - PGND) < 5 mm, no signal routed underneath on L2"),
    "DIFF_USB": dict(nets=[("MCU_USB_DP", "MCU_USB_DM"), ("MCUC_USB_DP", "MCUC_USB_DM"), ("HUSBC_DP", "HUSBC_DM"), ("HUSB_DP_R", "HUSB_DM_R"), ("FT_DP", "FT_DM")], rule="90 ohm differential, length match 2 mm, < 60 mm on board"),
    "DIFF_RS485": dict(nets=[("RS485_DP", "RS485_DN"), ("RS_A", "RS_B"), ("RS_A_L", "RS_B_L"), ("SYNC_P", "SYNC_N")], rule="120 ohm differential, keep > 5 mm from motor and heater copper"),
    "SENSITIVE_ANALOG": dict(nets=["IPROPI_*", "VREF_3V0", "HEAD_PRES_ID*", "PRES_F", "LOOP_*", "HEAD_LOOP_SENSE", "NTC_*", "VMOT_SENSE", "VBAT_SENSE", "V5_SENSE", "U2_IN*", "LAB_V*", "COLD_THR", "BRK_THR", "CLAMP_DIV", "CLAMP_REF", "OSC_*"],
                             rule="0.2 mm, over unbroken GND on L2, away from SWITCHING and HC_VMOT; Kelvin routing for every shunt"),
    "DIGITAL": dict(nets=["*"], rule="0.15-0.2 mm, 0.15 mm clearance; I2C and SPI over GND"),
}

# Harness view.  Mirrored (with mating parts) in connectors.yaml.  awg = recommended wire gauge.
CONNECTORS = {
    "J_PWR": dict(function="Pack feed + charge inlet feed + plug link", edge="right edge rear (u=160, v 8..31)", awg={1: 16, 2: 16, 5: 16, 6: 16, 3: 18, 7: 18, 4: 24, 8: 24}, max_a=15),
    "J_PAUX": dict(function="Pack NTC and presence (coupler auxiliary contacts)", edge="inboard of J_PWR", awg=26, max_a=0.01),
    "J_MOT_L": dict(function="Left gearmotor + encoder", edge="left edge front (u=0, v 74..90)", awg={1: 20, 2: 20, 3: 26, 4: 26, 5: 26, 6: 26}, max_a=2.7),
    "J_MOT_R": dict(function="Right gearmotor + encoder", edge="right edge front (u=160, v 74..90)", awg={1: 20, 2: 20, 3: 26, 4: 26, 5: 26, 6: 26}, max_a=2.7),
    "J_HEAD1": dict(function="J1 landing (HEAD POWER / INTERLOCK)", edge="front edge (v=100, u 12..31)", awg={1: 20, 2: 20, 3: 18, 4: 18, 5: 24, 6: 24, 7: 24}, max_a=4.4),
    "J_HEAD2": dict(function="J2 landing (HEAD DATA)", edge="front edge (v=100, u 125..140)", awg=26, max_a=0.2),
    "J_CM5": dict(function="5.1 V to the CM5 carrier", edge="left edge rear (u=0, v 8..21)", awg=18, max_a=5.0),
    "J_LIDAR": dict(function="LiDAR supply", edge="left edge rear (u=0, v 23..33)", awg=22, max_a=1.5),
    "J_USB_MCU": dict(function="USB FS chassis link", edge="inboard, left rear", awg=28, max_a=0.0),
    "J_USB_HEAD": dict(function="USB FS head link bridge", edge="inboard, left rear", awg=28, max_a=0.1),
    "J_HTR": dict(function="Bay heater", edge="rear-right corner (v=0, u 138..148)", awg=20, max_a=3.0),
    "J_NTC": dict(function="Bay and pack-surface NTC", edge="inboard, rear-right corner", awg=26, max_a=0.001),
    "J_ESTOP": dict(function="E-stop, 2 poles", edge="inboard, rear-right corner", awg=24, max_a=0.1),
    "J_HANDS": dict(function="HANDS-ON button + lamp", edge="inboard, rear-right corner", awg=24, max_a=0.1),
    "J_COVER": dict(function="Inlet cover switch", edge="inboard, rear-right corner", awg=24, max_a=0.1),
    "J_MODE": dict(function="Selector OFF/SERVICE/RUN", edge="inboard, rear-left corner", awg=24, max_a=0.1),
    "J_BTN": dict(function="REARM + PAUSE buttons and lamps", edge="inboard, rear-left corner", awg=24, max_a=0.1),
    "J_BUMP_L": dict(function="Body bumper left", edge="inboard, rear-left corner", awg=24, max_a=0.1),
    "J_BUMP_R": dict(function="Body bumper right", edge="inboard, rear-left corner", awg=24, max_a=0.1),
    "J_DOCK": dict(function="Head dock switch", edge="inboard, front edge centre", awg=24, max_a=0.1),
    "J_PANEL": dict(function="RR-PANEL", edge="inboard, rear-left corner", awg=26, max_a=0.15),
    "J_DBG": dict(function="Debug UART", edge="inboard, service", awg=28, max_a=0.03),
    "J_SWD": dict(function="SWD", edge="inboard, service", awg=None, max_a=0.0),
    "J_AUX": dict(function="Fan / spare", edge="inboard", awg=26, max_a=0.35),
}
for i, (tid, m, ch, grp, zone) in enumerate(TOF):
    CONNECTORS["J_TOF%d" % i] = dict(function="RR-TOF %s" % tid, edge="inboard, " + zone, awg=28, max_a=0.04)

CONTRACT_J1 = {1: "HEAD_PWR_P", 2: "HEAD_PWR_N", 3: "HEAD_HTR_P", 4: "HEAD_HTR_N", 5: "HEAD_LOOP_OUT", 6: "HEAD_LOOP_RET", 7: "HEAD_PRES_ID", 8: None}
CONTRACT_J2 = {1: "RS485_DP", 2: "RS485_DN", 3: "BUS_5V", 4: "BUS_GND", 5: "SYNC_P", 6: "SYNC_N", 7: "J2_PRES", 8: None}
NET_ALIASES = {"HEAD_PWR_N": "GND", "BUS_GND": "GND"}     # contract names that are the board's GND

# Nets that legitimately have a single connection (test pads, straps that are DNP on one side are still counted).
SINGLE_PIN_OK = {"CHASSIS_H2", "CHASSIS_H4", "CHASSIS_H5", "CHASSIS_H6"}


def self_check(parts=PARTS, nets=None, verbose=True):
    nets = nets or build_nets(parts)
    errs = []
    refs = [p["ref"] for p in parts]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    if dup:
        errs.append("duplicate refs: %s" % dup)
    power_names = re.compile(r"^(VCC|VDD\d?|VDDA|VDDIO|VS|VIN\d?|VM|IN|GND|VSS|VSSA|PGND\d?|AGND|SGND|VBAT|VCCIO|DVCC|VREF\+|EP)$")
    for p in parts:
        for num, v in p["pins"].items():
            if v is None:
                continue
            if not (isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], str) and v[1]):
                errs.append("undefined pin %s.%s: %r" % (p["ref"], num, v))
        if p["ref"].startswith("U"):
            for num, v in p["pins"].items():
                if v is None:
                    continue
                if power_names.match(v[0]) and not v[1]:
                    errs.append("unconnected power pin %s.%s" % (p["ref"], num))
        if not p["mpn"]:
            errs.append("no MPN: " + p["ref"])
    single = sorted(n for n, c in nets.items() if len(c) < 2 and n not in SINGLE_PIN_OK)
    if single:
        errs.append("nets with fewer than two connections: %s" % single)
    byref = {p["ref"]: p for p in parts}
    for jref, table in (("J_HEAD1", CONTRACT_J1), ("J_HEAD2", CONTRACT_J2)):
        for pin, name in table.items():
            v = byref[jref]["pins"][str(pin)]
            want = NET_ALIASES.get(name, name)
            if (v is None) != (want is None) or (v is not None and v[1] != want):
                errs.append("%s pin %d is %r, contract says %r" % (jref, pin, v, name))
    for num, (name, net) in MCU.items():
        pass
    for j in CONNECTORS:
        if j not in byref:
            errs.append("CONNECTORS entry without a part: " + j)
    for p in parts:
        if p["ref"].startswith("J") and p["ref"] not in CONNECTORS:
            errs.append("connector without a CONNECTORS entry: " + p["ref"])
    if verbose:
        blocks = {}
        for p in parts:
            blocks[p["block"]] = blocks.get(p["block"], 0) + 1
        fitted = [p for p in parts if not p["dnp"]]
        print("RR-CHS-MAIN circuit definition")
        print("  parts: %d (%d fitted, %d DNP), verify=True on %d" % (len(parts), len(fitted), len(parts) - len(fitted), sum(1 for p in parts if p["verify"])))
        for b in sorted(blocks):
            print("    %-12s %4d" % (b, blocks[b]))
        print("  nets: %d" % len(nets))
        area = sum(p["area_mm2"] for p in parts)
        big = sum(p["area_mm2"] for p in parts if p["area_mm2"] >= 100)
        tall = sorted({(p["ref"], p["height_mm"]) for p in parts if p["height_mm"] and p["height_mm"] > 10})
        board = MECH["outline_mm"][0] * MECH["outline_mm"][1]
        print("  placed area estimate: %.0f mm2 of %.0f mm2 one side = %.0f %%  (parts >= 100 mm2: %.0f mm2; rest can go on either side: %.0f mm2)"
              % (area, board, 100 * area / board, big, area - big))
        print("  two-sided utilisation (top + bottom, bottom limited to 3 mm parts): %.0f %%" % (100 * area / (2 * board)))
        print("  parts over 10 mm high: %s (limit 18 mm, 12 mm in the front corners)" % tall)
        print("  nets with fewer than two connections: %s" % (single or "none"))
        print("  duplicate refs: %s" % (dup or "none"))
        print("  SELF-CHECK %s" % ("FAILED" if errs else "PASSED"))
        for e in errs:
            print("   ERROR:", e)
    return errs


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_check() else 0)
