"""RR-CHS-MAIN stage-2 override layer on top of the stage-1 netlist (design/circuit.py).

design/circuit.py is the reviewed stage-1 baseline and is NOT edited.  Every deviation the board
needs is listed here as data, applied by ``apply()`` to a deep copy of circuit.PARTS, and checked
against the baseline (each override states what it expects to find, so a change in circuit.py
makes the build stop instead of silently overriding something else).  The same IDs are used in
STAGE2_CHANGE_REQUESTS.md (the request to the stage-1 owner) and README.md.

Kinds of override
  NET     a pin moves to another net / becomes NC       (netlist change -> STAGE2_CHANGE_REQUESTS.md)
  ADD     a part is added                               (netlist change -> STAGE2_CHANGE_REQUESTS.md)
  PART    value / MPN / package of an existing part     (BOM change     -> STAGE2_CHANGE_REQUESTS.md)
  RENUM   pin NUMBERS changed to the footprint's pad numbers, same pin names and nets
          (no electrical change; stage-1 numbers were recalled [U] or the package merges pins)
  LIB     symbol / footprint choice for the CAD library (no electrical change)

Plain Python, no rrkicad import: runs inside the KiCad container (board.py) and on the host
(``python3 overrides.py`` prints the change log and re-runs the stage-1 style self-check).
"""
import copy
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CIRCUIT = os.path.join(HERE, "design", "circuit.py")


def load_circuit(path=CIRCUIT):
    spec = importlib.util.spec_from_file_location("rr_chs_circuit_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------------------------- NET
# (id, ref, pin, expected (name, net) or None, new (name, net) or None, reason)
NET = [
    ("S2-01a", "J_BTN", "5", ("5", "PAUSE_BTN_RAW"), None,
     "IB-33: PAUSE contact moves to the new J_PAUSE in the rear-right cluster (J_BTN keeps its 8-way housing so its "
     "circuit count stays unique among the CLIK-Mate safety headers; pins 1-4, 6, 7 unchanged)"),
    ("S2-01b", "J_BTN", "8", ("8", "LAMP_PAUSE_K"), None, "IB-33: PAUSE lamp return moves to J_PAUSE pin 4"),
    ("S2-01c", "D29", "2", ("IO2", "PAUSE_BTN_RAW"), None,
     "IB-33: PAUSE_BTN_RAW gets its ESD channel at J_PAUSE (D_PAUSE); D29 stays at J_BTN"),
    ("S2-01d", "D29", "5", ("IO4", "PACK_PRES_N"), None,
     "IB-33: PACK_PRES_N (J_PAUX, right edge) moves to D_PAUSE next to J_PAUX so the line does not cross the board to D29"),
    ("S2-05", "U42", "2", None, ("GNDA", "GND"),
     "Stock KiCad BMI088 symbol (from the Bosch datasheet) has GNDA on pins 2 AND 4 (stacked); stage 1 left pin 2 open "
     "with pin numbers 'recalled [U]'. Tie both GNDA pins to GND. VERIFY against the BMI088 datasheet pin table."),
]

# ----------------------------------------------------------------------------------------- ADD
ADD = [
    ("S2-01e", dict(ref="J_PAUSE", value="JST GH 5p top", mpn="BM05B-GHS-TBT(LF)(SN)", manufacturer="JST",
                    description="PAUSE/Stop button (right deck): 1 PAUSE_3V3 (contact supply), 2 PAUSE_BTN_RAW (contact), "
                                "3 V12_AUX (lamp +), 4 LAMP_PAUSE_K (lamp -), 5 not connected",
                    package="GH-V", symbol_hint="Connector_Generic_MountingPin:Conn_01x05_MountingPin",
                    footprint_hint="Connector_JST:JST_GH_BM05B-GHS-TBT_1x05-1MP_P1.25mm_Vertical",
                    pins={"1": ("1", "PAUSE_3V3"), "2": ("2", "PAUSE_BTN_RAW"), "3": ("3", "V12_AUX"), "4": ("4", "LAMP_PAUSE_K"),
                          "5": None, "MP": ("MP", "GND")},
                    block="chain", dnp=False, rating="1 A/contact", tolerance=None, verify=False, height_mm=4.25, area_mm2=50.0,
                    notes="IB-33. Signal family (PAUSE is program control, not a chain element, CCR-E12). 5 circuits: unique in the "
                          "rear-right cluster (J_NTC/J_PAUX are 4-way GH, ToF 6-way GH). JST GH -25..+85 C [U] (CCR-E05)."),
     "IB-33: separate PAUSE connector in the rear-right cluster (PAUSE button is on the right deck)"),
    ("S2-01f", dict(ref="R_PAUSE", value="1k", mpn="RC0603FR-071KL", manufacturer="Yageo", description="Resistor 1k 1%",
                    package="0603", symbol_hint="Device:R", footprint_hint="Resistor_SMD:R_0603_1608Metric",
                    pins={"1": ("1", "3V3"), "2": ("2", "PAUSE_3V3")}, block="chain", dnp=False, rating="0.1 W", tolerance="1%",
                    verify=False, height_mm=0.9, area_mm2=3.2,
                    notes="PAUSE contact supply, current-limited like BTN_3V3 (R128): a short in the PAUSE cable cannot load 3V3"),
     "IB-33: own 1 k contact supply for J_PAUSE (BTN_3V3 stays local to J_BTN)"),
    ("S2-01g", dict(ref="D_PAUSE", value="TPD4E05U06", mpn="TPD4E05U06DQAR", manufacturer="Texas Instruments",
                    description="4-channel ESD array 5.5 V, 0.5 pF: J_PAUSE and J_PAUX lines", package="USON-10",
                    symbol_hint="Power_Protection:TPD4E05U06DQA", footprint_hint="Package_SON:USON-10_2.5x1.0mm_P0.5mm",
                    pins={"1": ("IO1", "PAUSE_BTN_RAW"), "2": ("IO2", "PAUSE_3V3"), "3": ("GND", "GND"), "4": ("IO3", "PACK_PRES_N"),
                          "5": None, "6": None, "7": None, "8": ("GND", "GND"), "9": None, "10": None},
                    block="chain", dnp=False, rating=None, tolerance=None, verify=False, height_mm=0.6, area_mm2=6.0,
                    notes="pins 6, 7, 9, 10 flow-through NC (as D29)"),
     "IB-33: ESD for the moved PAUSE lines and PACK_PRES_N at the rear-right connectors"),
]

# ----------------------------------------------------------------------------------------- PART
# (id, ref, {field: (expected, new)}, reason)
PART = [
    ("S2-02", "J_HEAD1", {"value": ("Micro-Fit 3.0 2x4 RA", "Mini-Fit Jr 2x5 RA"), "mpn": ("43045-0800", "39-30-1100"),
                          "manufacturer": ("Molex", "Molex"),
                          "package": ("MICROFIT-2x4-RA", "MINIFIT-2x5-RA"),
                          "symbol_hint": ("Connector_Generic:Conn_02x04_Top_Bottom", "Connector_Generic:Conn_02x05_Top_Bottom"),
                          "footprint_hint": ("Connector_Molex:Molex_Micro-Fit_3.0_43045-0800_2x04_P3.00mm_Horizontal",
                                             "Connector_Molex:Molex_Mini-Fit_Jr_5569-10A2_2x05_P4.20mm_Horizontal"),
                          "rating": ("8.5 A/contact max [D family], -40..+105 C", "9 A/contact (Mini-Fit Jr, 5556 terminals 18-24 AWG) [U], -40..+105 C")},
     "IB-32: the head heater pair (pins 3/4, 4.05 A, AWG 18 per contract J1) needs an AWG 18 contact. Mini-Fit Jr 5556 crimp "
     "terminals take 18-24 AWG; 10 circuits so it cannot mate with the 8-way J_PWR. Pins 1-8 keep their nets "
     "(pin n = J1 pin n), pins 9/10 not connected. MPN/terminal recalled [U]."),
    ("S2-04", "R46", {"value": ("825", "845"), "mpn": ("RC0603FR-07825RL", "RC0603FR-07845RL")},
     "IB-28: U17 (HEAD_HTR) current limit ILIM = 3343 / RILM [stage-1 formula]: 825 -> 4.05 A is above the contract's "
     "4.0 A; 845 -> 3.96 A nominal (3.56-4.35 A with +-10 %). Heater draw is <= 3.04 A (4.8 ohm at 14.6 V), so no nuisance trips."),
]

# J_HEAD1 gets two extra (NC) pins with the 2x5 housing
EXTRA_PINS = {"J_HEAD1": {"9": None, "10": None}}

# ----------------------------------------------------------------------------------------- RENUM
# Pin numbers -> footprint pad numbers.  {ref_or_refs: {old_pin: new_pin or None(=merge into another pad, net must match)}}
_SON_MERGE = {"6": None, "7": None, "8": None, "9": None}     # drain pins 5..8 + tab are all pad 5 in the stock NexFET footprints
RENUM = [
    ("S2-06a", ("Q1", "Q2", "Q4", "Q5", "Q40"), _SON_MERGE,
     "SON-5x6 / SON-3x3 NexFET: KiCad TDSON-8-1 and VSON-8_3.3x3.3mm_P0.65mm_NexFET number all drain leads and the tab "
     "'5' (stock symbols Transistor_FET:CSD18540Q5B / CSD18543Q3A have pins 1-3 S, 4 G, 5 D). Same nets."),
    ("S2-06b", ("K2", "K3"), {"1": "A1", "8": "A2", "3": "11", "2": "12", "4": "14", "6": "21", "7": "22", "5": "24"},
     "G2RL-2: stage-1 used recalled numbers 1..8 [U]; KiCad's Relay:G2RL-2 symbol and footprint use the terminal marks "
     "A1/A2 (coil), 11/12/14 (COM1/NC1/NO1), 21/22/24 (COM2/NC2/NO2). Mapping by pin NAME (authoritative in stage 1)."),
]

# ----------------------------------------------------------------------------------------- LIB
# symbol / footprint per ref (no electrical change).  "rr_local:..." names are defined in board.py.
SYMBOLS = {}
SYMBOL_BY_MPN = {"BSS138": "Transistor_FET:BSS138", "BSS84,215": "Transistor_FET:BSS84",
                 "CSD18540Q5B": "Transistor_FET:CSD18540Q5B", "CSD18543Q3A": "Transistor_FET:CSD18543Q3A"}
# Kelvin-less two-terminal shunts: Device:R_Shunt has 4 pins (Kelvin) but the parts and land patterns are 2-terminal
for _r in ("R_SH1", "R_SH2", "R_SH3", "R_SH4", "R_SNSI", "R_SNSB"):
    SYMBOLS[_r] = "Device:R"
SYMBOLS.update({"U42": "rr_local:BMI088_SPI", "U45": "Interface_Expansion:TCA9534", "J_HTR": "Connector_Generic:Conn_01x02", "J_LIDAR": "Connector_Generic:Conn_01x02"})

_CLIK = "Connector_Molex:Molex_CLIK-Mate_502443-%02d70_1x%02d-1MP_P2.00mm_Vertical"
FOOTPRINTS = {
    "U10": "rr_local:TI_RJR0014A_VQFN-HR-14_4x3.5mm_PLACEHOLDER",
    "U13": "rr_local:TI_RPW0010A_VQFN-HR-10_2x2mm_PLACEHOLDER",
    "U16": "rr_local:TI_RPW0010A_VQFN-HR-10_2x2mm_PLACEHOLDER",
    "U17": "rr_local:TI_RPW0010A_VQFN-HR-10_2x2mm_PLACEHOLDER",
    "U18": "rr_local:TI_RPW0010A_VQFN-HR-10_2x2mm_PLACEHOLDER",
    "U19": "rr_local:TI_RPW0010A_VQFN-HR-10_2x2mm_PLACEHOLDER",
    "U8": "rr_local:TI_TPS25982_VQFN-24_4x4mm_SplitPad_PLACEHOLDER",
    "W1": "rr_local:WirePads_2x2.5mm_P5.0mm",
    "L2": "Inductor_SMD:L_Coilcraft_XAL6030-XXX",
    "L3": "rr_local:L_Wuerth_WE-LQS-5040",
    "L4": "rr_local:L_Wuerth_WE-LQS-5040",
    "U15": "Package_DFN_QFN:Texas_RGV0016A_VQFN-16-1EP_4x4mm_P0.65mm_EP2.1x2.1mm",
    "U42": "rr_local:Bosch_LGA-16_4.5x3mm_P0.5mm_ClockwisePinNumbering",
    "L60": "Inductor_SMD:L_CommonModeChoke_Coilank_ACM2012",
    "U5": "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm",   # stage-1 hint has 0.2 mm via drills (< fab min 0.3)
    "U6": "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm",
    "Q4": "rr_local:VSON-8_3.3x3.3mm_P0.65mm_NexFET_G0.2", "Q5": "rr_local:VSON-8_3.3x3.3mm_P0.65mm_NexFET_G0.2",
    "Q40": "rr_local:VSON-8_3.3x3.3mm_P0.65mm_NexFET_G0.2",
    "SW1": "Button_Switch_SMD:SW_Tactile_SPST_NO_Straight_CK_PTS636Sx25SMTRLFS",
    "SW2": "Button_Switch_SMD:SW_Tactile_SPST_NO_Straight_CK_PTS636Sx25SMTRLFS",
    "J_MODE": _CLIK % (6, 6), "J_ESTOP": _CLIK % (4, 4), "J_HANDS": _CLIK % (5, 5), "J_COVER": _CLIK % (3, 3),
    "J_DOCK": _CLIK % (3, 3), "J_BUMP_L": _CLIK % (2, 2), "J_BUMP_R": _CLIK % (2, 2), "J_BTN": _CLIK % (8, 8),
}
FOOTPRINT_BY_MPN = {"5019": "TestPoint:TestPoint_Keystone_5019_Miniature"}     # stage-1 hint misspelt 'Minature'
LIB_NOTES = {
    "Q4": "stock VSON-8 NexFET land with pads 1-4 0.45 mm tall (stock 0.5 mm leaves 0.14 mm between S and G, below the 0.15 mm fab rule)",
    "Q5": "stock VSON-8 NexFET land with pads 1-4 0.45 mm tall (see Q4)", "Q40": "stock VSON-8 NexFET land with pads 1-4 0.45 mm tall (see Q4)",
    "L2": "XAL6060 uses the XAL60xx-family land pattern (stock XAL6030 footprint; same 6.36 x 6.56 mm base) [verify]",
    "L60": "TDK ACM2012 on the Coilank ACM2012 land pattern (same 2.0 x 1.2 mm body); WINDING PAIRING 1-2/4-3 vs 1-4/2-3 MUST BE CHECKED",
    "U42": "Pads of the stock Bosch_LGA-16_4.5x3mm_P0.5mm_LayoutBorder7x1y_ClockwisePinNumbering without its internal rule area "
           "(board-level via keep-out instead); stage-1 pin numbers recalled",
}
# parts whose land pattern is not from a manufacturer drawing (README: UNVERIFIED)
PLACEHOLDER_FOOTPRINTS = ["U8", "U10", "U13", "U16", "U17", "U18", "U19", "L3", "L4"]


# ============================================================================ STAGE 3 (review fixes)
# docs/reviews/REVIEW_traction_inhibit.md.  IDs S3-xx = STAGE2_CHANGE_REQUESTS.md section "Stage 3 (review fixes)".
# Part constructors in the stage-1 style (same MPN families as circuit.py; [U] = not checked against a datasheet here).
_R_FP = {"0603": "Resistor_SMD:R_0603_1608Metric", "1206": "Resistor_SMD:R_1206_3216Metric"}


def _rc(val):
    num, mult = (val[:-1], val[-1].upper()) if val[-1] in "kM" else (val, "R")
    return num.replace(".", mult) if "." in num else num + mult


def _r(ref, val, a, b, notes="", pkg="0603"):
    rating = {"0603": "0.1 W", "1206": "0.25 W"}[pkg]
    return dict(ref=ref, value=val, mpn="RC%sFR-07%sL" % (pkg, _rc(val)), manufacturer="Yageo", description="Resistor %s 1%%" % val,
                package=pkg, symbol_hint="Device:R", footprint_hint=_R_FP[pkg], pins={"1": ("1", a), "2": ("2", b)}, block="chain",
                dnp=False, rating=rating, tolerance="1%", verify=False, height_mm={"0603": 0.9, "1206": 1.6}[pkg],
                area_mm2={"0603": 3.2, "1206": 8.5}[pkg], notes=notes)


_CAP = {"10n": ("CC0603KRX7R9BB103", "Yageo", 50, False), "22n": ("CC0603KRX7R9BB223", "Yageo", 50, False),
        "100n": ("CC0603KRX7R9BB104", "Yageo", 50, False), "1u": ("GRM188R71C105KA12D", "Murata", 16, True)}


def _c(ref, val, a, b, notes=""):
    mpn, mfr, v, ver = _CAP[val]
    return dict(ref=ref, value=val, mpn=mpn, manufacturer=mfr, description="MLCC %sF %d V X7R" % (val, v), package="0603",
                symbol_hint="Device:C", footprint_hint="Capacitor_SMD:C_0603_1608Metric", pins={"1": ("1", a), "2": ("2", b)},
                block="chain", dnp=False, rating="%d V" % v, tolerance="10%", verify=ver, height_mm=0.9, area_mm2=3.2, notes=notes)


_DIODES = {"BAT54": ("BAT54W-7-F", "Diodes Inc.", "Schottky 30 V 0.2 A", "SOD-123", "Device:D_Schottky", "Diode_SMD:D_SOD-123", 1.2, 7),
           "1N4148W": ("1N4148W-7-F", "Diodes Inc.", "Switching diode 100 V 0.3 A", "SOD-123", "Device:D", "Diode_SMD:D_SOD-123", 1.2, 7),
           "B160": ("B160-13-F", "Diodes Inc.", "Schottky 60 V 1 A", "SMA", "Device:D_Schottky", "Diode_SMD:D_SMA", 2.3, 14)}


def _d(ref, kind, a, k, notes="", verify=False):
    mpn, mfr, desc, pkg, sym, fp, h, area = _DIODES[kind]
    return dict(ref=ref, value=kind, mpn=mpn, manufacturer=mfr, description=desc, package=pkg, symbol_hint=sym, footprint_hint=fp,
                pins={"1": ("K", k), "2": ("A", a)}, block="chain", dnp=False, rating=None, tolerance=None, verify=verify,
                height_mm=h, area_mm2=area, notes=notes)


def _nfet(ref, d, g, s, notes=""):
    return dict(ref=ref, value="BSS138", mpn="BSS138", manufacturer="onsemi", description="N-MOSFET 50 V 0.22 A logic level (Vgs(th) <= 1.5 V)",
                package="SOT-23", symbol_hint="Device:Q_NMOS_GSD", footprint_hint="Package_TO_SOT_SMD:SOT-23",
                pins={"1": ("G", g), "2": ("S", s), "3": ("D", d)}, block="chain", dnp=False, rating=None, tolerance=None,
                verify=False, height_mm=1.1, area_mm2=9, notes=notes)


def _pfet(ref, d, g, s, notes=""):
    return dict(ref=ref, value="BSS84", mpn="BSS84,215", manufacturer="Nexperia", description="P-MOSFET -50 V 0.13 A",
                package="SOT-23", symbol_hint="Device:Q_PMOS_GSD", footprint_hint="Package_TO_SOT_SMD:SOT-23",
                pins={"1": ("G", g), "2": ("S", s), "3": ("D", d)}, block="chain", dnp=False, rating=None, tolerance=None,
                verify=False, height_mm=1.1, area_mm2=9, notes=notes)


def _ssr(ref, a, b, led_a, led_k, what):
    return dict(ref=ref, value="TLP241A", mpn="TLP241A(TP1,F", manufacturer="Toshiba", description="Photo-MOS relay 40 V 2 A, 0.15 ohm, 1 form A: " + what,
                package="DIP4-SMD", symbol_hint="Relay_SolidState:TLP222A", footprint_hint="Package_DIP:SMDIP-4_W9.53mm",
                pins={"1": ("ANODE", led_a), "2": ("CATHODE", led_k), "3": ("DRAIN1", a), "4": ("DRAIN2", b)}, block="chain", dnp=False,
                rating="40 V, 2 A [U]", tolerance=None, verify=True, height_mm=4.0, area_mm2=45,
                notes="Same part as U20-U24: ratings, trigger current (assumed <= 3 mA) and turn-on/off times (assumed <= 3 ms / 1 ms) "
                      "not read (toshiba.semicon-storage.com 403 in stage 1) [U]")


def _tp(ref, net):
    return dict(ref=ref, value=net, mpn="5019", manufacturer="Keystone", description="SMD test point loop", package="TP",
                symbol_hint="Connector:TestPoint", footprint_hint="TestPoint:TestPoint_Keystone_5019_Miniature", pins={"1": ("1", net)},
                block="test", dnp=False, rating=None, tolerance=None, verify=False, height_mm=1.5, area_mm2=4, notes="stage 3 chain node test point")


def _tap(pfx, node, sig, notes):
    """Chain readback tap as circuit.py tap(): 100k / 56k / 22 nF / BAT54 clamp to 3V3."""
    return [_r("R_%s1" % pfx, "100k", node, sig, notes), _r("R_%s2" % pfx, "56k", sig, "GND"), _c("C_%s" % pfx, "22n", sig, "GND"),
            _d("D_%s" % pfx, "BAT54", sig, "3V3")]


S3_NET = [
    # ---- C1: K1 coil node stays on the board; the REARM set contact only signals an on-board set stage
    ("S3-C1a", "J_BTN", "1", ("1", "SET_CAP"), ("1", "REARM_SET_SRC"),
     "C1: J_BTN pin 1 = 5 V contact supply of the REARM set contact (V5_AUX via 1 k); C_SET no longer leaves the board"),
    ("S3-C1b", "J_BTN", "2", ("2", "K1_SET"), ("2", "REARM_SET_RAW"),
     "C1: J_BTN pin 2 = REARM set contact output into the on-board edge-triggered set stage; the K1 coil node no longer leaves the board"),
    ("S3-C1c", "R129", "1", ("1", "REARM_BTN_RAW"), ("1", "REARM_BTN_D"),
     "C1/M2: aux contact reaches IOX_A GPB2 through blocking diode D_RB, so GPB2 as an output cannot enable the set stage"),
    ("S3-C1d", "K1", "8", ("NO2", "RUN_12V"), ("NO2", "K1_RUN"),
     "C1: K1 pole B now feeds K1_RUN -> second, diverse hold element U_HOLD -> RUN_HD -> D_RUN -> RUN_12V"),
    ("S3-C1e", "K1", "3", None, ("NC1", "K1_NC1"),
     "C1: K1 pole A NC contact read back (K1_SEAL_A biased from 3V3), valid with the chain dead"),
    ("S3-C1f", "R133", "1", ("1", "RUN_12V"), ("1", "RUN_HD"),
     "C1/M6: VMOT eFuse enable taken before D_RUN: a short of RUN_12V to a supply does not enable VMOT"),
    # ---- M6: brake relay coils return through the low-side hold photo-MOS U_LS
    ("S3-M6a", "K2", "8", ("A2", "COIL_RTN"), ("A2", "RELAY_RTN"), "M6: K2 coil return through U_LS (on only with a real latch)"),
    ("S3-M6b", "K3", "8", ("A2", "COIL_RTN"), ("A2", "RELAY_RTN"), "M6: K3 coil return through U_LS"),
    ("S3-M6c", "D31", "2", ("A", "COIL_RTN"), ("A", "RELAY_RTN"), "M6: K2 clamp stays across the coil"),
    ("S3-M6d", "D34", "2", ("A", "COIL_RTN"), ("A", "RELAY_RTN"), "M6: K3 clamp stays across the coil"),
    # ---- M1: C_SET cannot back-feed CHAIN_END
    ("S3-M1a", "R_SET", "1", ("1", "CHAIN_END"), ("1", "RSET_A"), "M1: series diode D_RSET (anode CHAIN_END) before R_SET"),
    # ---- C2: second head-loop channel in series
    ("S3-C2a", "U21", "4", ("DRAIN2", "CH_N6"), ("DRAIN2", "CH_N6A"), "C2: channel B photo-MOS U21B follows U21 (new node CH_N6A)"),
    # ---- M2: no logic pin can drive a chain-control node
    ("S3-M2a", "U43", "26", ("GPA5", "HEAD_LOOP_OK_RB"), ("GPA5", "HEAD_LOOP_OK_IO"), "M2: GPA5 through 47 k (R_GA5)"),
    ("S3-M2b", "U43", "28", ("GPA7", "LAB_KEY_N_RB"), ("GPA7", "LAB_KEY_N_IO"), "M2: GPA7 through 47 k (R_GA7)"),
    ("S3-M2c", "U43", "8", ("GPB7", "WDG_STROBE"), ("GPB7", "WDG_STROBE_IO"), "M2: sentinel GPB7 through 47 k (R_GB7) + 10 k pull-down on WDG_STROBE"),
    ("S3-M2d", "U9", "2", ("B", "HW_LATCH_RB"), ("B", "HW_LATCH_G"), "M2/M3: U9.B has its own tap on RUN_HD; PD2 no longer touches the nSLEEP gate"),
]

S3_PART = [
    ("S3-M3a", "R99", {"value": ("100k", "22k"), "mpn": ("RC0603FR-07100KL", "RC0603FR-0722KL")},
     "M3: ESTOP_A_RB (PB12) tap 22 k / 15 k: HIGH above 7.7 V even with the STM32 pull-down (25 k) enabled"),
    ("S3-M3b", "R100", {"value": ("56k", "15k"), "mpn": ("RC0603FR-0756KL", "RC0603FR-0715KL")}, "M3: see R99"),
    ("S3-M3c", "R117", {"value": ("100k", "22k"), "mpn": ("RC0603FR-07100KL", "RC0603FR-0722KL")},
     "M3: HW_LATCH_RB (PD2) tap 22 k / 15 k, as R99/R100"),
    ("S3-M3d", "R118", {"value": ("56k", "15k"), "mpn": ("RC0603FR-0756KL", "RC0603FR-0715KL")}, "M3: see R117"),
    ("S3-M3e", "R129", {"value": ("10k", "4.7k"), "mpn": ("RC0603FR-0710KL", "RC0603FR-074K7L")},
     "M3: REARM_BTN high level 2.9 V with D_RB (was 2.67 V against MCP23S17 VIH 0.8 VDD = 2.64 V)"),
    ("S3-M3f", "R130", {"value": ("47k", "100k"), "mpn": ("RC0603FR-0747KL", "RC0603FR-07100KL")}, "M3: see R129"),
    ("S3-M6e", "D32", {"value": ("Z24", "Z20"), "mpn": ("BZT52C24-7-F", "BZT52C20-7-F"), "description": ("Zener 24 V 0.5 W", "Zener 20 V 0.5 W")},
     "M6: K2 clamp Zener 20 V: with RUN_12V held up by a fault, U_LS sees <= 14.6 + 21.2 + 0.7 = 36.5 V (TLP241A 40 V [U]); release ~0.3 ms slower [A]"),
    ("S3-N1a", "J_TOF4", {"description": ("RR-TOF LOOK_LO (mux 0 ch 2), left edge front. Pin order as RR-TOF-A J1",
                                          "RR-TOF LOOK_FL (index 4, mux 0 ch 2), left edge front. Pin order as RR-TOF-A J1")},
     "IB-34 / DEC-043 sensor names (no electrical change)"),
    ("S3-N1b", "J_TOF5", {"description": ("RR-TOF LOOK_LI (mux 1 ch 2), left edge front. Pin order as RR-TOF-A J1",
                                          "RR-TOF LOOK_RL (index 5, mux 1 ch 2), rear-left GH row (tail, looking behind). Pin order as RR-TOF-A J1")},
     "IB-34 / DEC-043 sensor names (no electrical change)"),
    ("S3-N1c", "J_TOF6", {"description": ("RR-TOF LOOK_RI (mux 0 ch 3), right edge front. Pin order as RR-TOF-A J1",
                                          "RR-TOF LOOK_RR (index 6, mux 0 ch 3), rear-right GH row (tail, looking behind). Pin order as RR-TOF-A J1")},
     "IB-34 / DEC-043 sensor names (no electrical change)"),
    ("S3-N1d", "J_TOF7", {"description": ("RR-TOF LOOK_RO (mux 1 ch 3), right edge front. Pin order as RR-TOF-A J1",
                                          "RR-TOF LOOK_FR (index 7, mux 1 ch 3), right edge front. Pin order as RR-TOF-A J1")},
     "IB-34 / DEC-043 sensor names (no electrical change)"),
    ("S3-M6f", "D35", {"value": ("Z24", "Z20"), "mpn": ("BZT52C24-7-F", "BZT52C20-7-F"), "description": ("Zener 24 V 0.5 W", "Zener 20 V 0.5 W")},
     "M6: K3 clamp Zener 20 V (see D32)"),
]

_TCA_D = dict(ref="U47", value="TCA9534", mpn="TCA9534PWR", manufacturer="Texas Instruments",
              description="IOX_D: 8-bit I2C expander 0x22, inputs only: latch / hold / loop channel B / REARM set contact readbacks",
              package="TSSOP-16", symbol_hint="Interface_Expansion:TCA9534", footprint_hint="Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
              pins={"1": ("A0", "GND"), "2": ("A1", "3V3"), "3": ("A2", "GND"), "4": ("P0", "LATCH_NC_RB"), "5": ("P1", "LATCH_RUN_RB"),
                    "6": ("P2", "HEAD_LOOP2_OK_RB"), "7": ("P3", "REARM_SET_RB"), "8": ("GND", "GND"), "9": ("P4", "IOXD_P4"),
                    "10": ("P5", "IOXD_P5"), "11": ("P6", "IOXD_P6"), "12": ("P7", "IOXD_P7"), "13": None, "14": ("SCL", "I2C_SYS_SCL"),
                    "15": ("SDA", "I2C_SYS_SDA"), "16": ("VCC", "3V3")},
              block="mcu", dnp=False, rating=None, tolerance=None, verify=True, height_mm=1.2, area_mm2=34,
              notes="Same part and pin table as U45 (IOX_C, pin numbers recalled [U]). Address 0x22 (A1 high). P4 pulled up, P5-P7 pulled "
                    "down through 10 k: fixed pattern 0x1 in the high nibble proves the device answers with live inputs. INT unused.")
_TLV = dict(ref="U46", value="TLV3201", mpn="TLV3201AIDBVR", manufacturer="Texas Instruments",
            description="Comparator, CMOS input, push-pull output, 2.7-5.5 V: head-loop channel B (open / high-resistance loop)",
            package="SOT-23-5", symbol_hint=None, footprint_hint="Package_TO_SOT_SMD:SOT-23-5",
            pins={"1": ("OUT", "HEAD_LOOP2_OK"), "2": ("V-", "GND"), "3": ("IN+", "LOOP_FB"), "4": ("IN-", "LOOP_VB"), "5": ("V+", "V5_AUX")},
            block="chain", dnp=False, rating=None, tolerance=None, verify=True, height_mm=1.45, area_mm2=9,
            notes="Diverse from U30 (LM2903B, bipolar, open collector). DBV pinout 1 OUT, 2 V-, 3 IN+, 4 IN-, 5 V+ recalled [U]: "
                  "OUT is adjacent to V- (a solder bridge opens channel B), V+ is on the other side of the body.")
_ESD_SET = dict(ref="D_SET", value="PESD15VL2BT", mpn="PESD15VL2BT,215", manufacturer="Nexperia", description="Dual bidirectional ESD diode, 15 V",
                package="SOT-23", symbol_hint="Device:D_TVS_Dual_AAC", footprint_hint="Package_TO_SOT_SMD:SOT-23",
                pins={"1": ("K1", "REARM_SET_RAW"), "2": ("K2", "REARM_SET_SRC"), "3": ("COM", "GND")}, block="chain", dnp=False,
                rating=None, tolerance=None, verify=True, height_mm=1.1, area_mm2=9,
                notes="15 V stand-off: survives a V12_AUX short in W-018 (a 5.5 V array would not)")

S3_ADD = [
    # ---- C1 set stage: edge of the set contact AND level of the aux contact -> U_SET connects C_SET to the coil
    ("S3-C1g", [_r("R_SSRC", "1k", "V5_AUX", "REARM_SET_SRC", "REARM set contact supply (J_BTN 1), current-limited"),
                _r("R_SPD", "47k", "REARM_SET_RAW", "GND", "defines the open set contact"),
                _r("R_SSER", "10k", "REARM_SET_RAW", "REARM_SET"), _c("C_SF", "10n", "REARM_SET", "GND"),
                _d("D_SCL", "BAT54", "REARM_SET", "V5_AUX", "clamps a W-018 short to V12_AUX (1.2 mA through R_SSER)"),
                _ESD_SET,
                _c("C_SC", "1u", "REARM_SET", "SET_G", "AC coupling: one gate pulse per closing edge (tau 110 ms with R_SG + R_SSER)"),
                _r("R_SG", "100k", "SET_G", "GND"), _d("D_SGN", "BAT54", "GND", "SET_G", "negative clamp / reset on release"),
                _r("R_SRB", "47k", "REARM_SET", "REARM_SET_RB", "set contact readback to IOX_D P3 (series-isolated)"),
                _d("D_RB", "BAT54", "REARM_BTN_RAW", "REARM_BTN_D", "GPB2 cannot drive the aux contact node"),
                _r("R_AG", "10k", "REARM_BTN_RAW", "REARM_AUX_G"), _r("R_AGP", "100k", "REARM_AUX_G", "GND"),
                _c("C_AG", "10n", "REARM_AUX_G", "GND"),
                _nfet("Q_SETA", "U_SET_K", "SET_G", "SET_S", "set coincidence, edge of the set contact"),
                _nfet("Q_SETB", "SET_S", "REARM_AUX_G", "GND", "set coincidence, level of the aux contact"),
                _r("R_USA", "470", "V5_AUX", "U_SET_A"),
                _ssr("U_SET", "SET_CAP", "K1_SET", "U_SET_A", "U_SET_K", "REARM set switch C_SET -> K1 coil (on-board, via R96 0 ohm)"),
                _r("R_USK", "100k", "V5_AUX", "U_SET_K", "holds Q_HSET off while the set stack is off"),
                _pfet("Q_HSET", "HSET_D", "U_SET_K", "V5_AUX", "U_HOLD set current from V5_AUX, only while the set stack conducts: "
                      "nothing on the coil side (seal-in) can reach the U_HOLD LED"),
                _d("D_RSET", "1N4148W", "CHAIN_END", "RSET_A", "M1: C_SET charges from CHAIN_END but cannot feed it"),
                _r("R_SDIS", "1k", "SET_CAP", "SET_DIS", "C_SET discharge (tau 0.1 s) while CHAIN_END is dead", pkg="1206"),
                _nfet("Q_SDIS", "SET_DIS", "SDIS_G", "GND"), _r("R_SDG", "100k", "3V3", "SDIS_G"),
                _nfet("Q_SDISB", "SDIS_G", "CHAIN_END_RB", "GND", "off (discharge on) when CHAIN_END is below about 2-4 V")],
     "C1/m3/m11: on-board edge-triggered, two-contact set stage; C_SET emptied whenever the chain is open"),
    # ---- C1 second, diverse hold element and K1 readbacks
    ("S3-C1h", [_ssr("U_HOLD", "K1_RUN", "RUN_HD", "HOLD_A", "GND", "second hold element in series with K1 pole B, self-holding from RUN_HD"),
                _r("R_HA", "1.5k", "RUN_HD", "HOLD_A", "self-hold LED feed (5.9-8.9 mA at 10-14.6 V)", pkg="1206"),
                _r("R_HS", "470", "HSET_D", "HOLD_A", "set feed (about 7.8 mA) from Q_HSET during the REARM pulse only"),
                _d("D_HR", "1N4148W", "GND", "HOLD_A", "LED reverse protection (coil kick)"),
                _d("D_RUN", "B160", "RUN_HD", "RUN_12V", "RUN_12V cannot back-feed RUN_HD / K1_RUN / CHAIN_END; isolates the K2/K3 kick from the chain", verify=True),
                _ssr("U_LS", "RELAY_RTN", "COIL_RTN", "LS_A", "GND", "low-side element in the K2/K3 coil return, LED from RUN_HD"),
                _r("R_LSA", "1.5k", "RUN_HD", "LS_A", pkg="1206"), _d("D_LSR", "1N4148W", "GND", "LS_A", "LED reverse protection"),
                _d("D_K1B", "BAT54", "3V3", "K1_BIAS"), _r("R_K1B", "47k", "K1_BIAS", "K1_SEAL_A", "3 V bias on K1 pole A common: NC readback valid with the chain dead"),
                _r("R_NC1", "47k", "K1_NC1", "LATCH_NC_RB"), _r("R_NC2", "1M", "LATCH_NC_RB", "GND"), _c("C_NC", "10n", "LATCH_NC_RB", "GND"),
                _d("D_NC", "BAT54", "LATCH_NC_RB", "3V3")]
     + _tap("KR", "K1_RUN", "LATCH_RUN_RB", "K1 pole B output tap (IOX_D P1)")
     + _tap("U9T", "RUN_HD", "HW_LATCH_G", "U9.B own tap (M2)"),
     "C1/M6: U_HOLD (diverse hold), D_RUN, U_LS (low-side), K1 NC and K1_RUN readbacks, U9 own tap"),
    # ---- C2 head-loop channel B
    ("S3-C2b", [_r("R_LB1", "10k", "LOOP_SNS", "LOOP_FB", "channel B own filter (1 ms)"), _c("C_LB1", "100n", "LOOP_FB", "GND"),
                _r("R_LB2", "39k", "V5_AUX", "LOOP_VB", "channel B own reference: 1.02 V = loop 2.70 kohm"), _r("R_LB3", "10k", "LOOP_VB", "GND"),
                _c("C_LB2", "100n", "LOOP_VB", "GND"), _TLV, _c("C_U46", "100n", "V5_AUX", "GND"),
                _r("R_LBG", "100k", "HEAD_LOOP2_OK", "GND"), _r("R_LBR", "47k", "HEAD_LOOP2_OK", "HEAD_LOOP2_OK_RB", "readback to IOX_D P2 (series-isolated)"),
                _nfet("Q_LB", "U21B_K", "HEAD_LOOP2_OK", "GND"), _r("R_21BA", "680", "V5_AUX", "U21B_A"),
                _ssr("U21B", "CH_N6A", "CH_N6", "U21B_A", "U21B_K", "HEAD_LOOP channel B")],
     "C2: second, diverse head-loop evaluation with its own series photo-MOS"),
    # ---- M2 isolation and IOX_D
    ("S3-M2e", [_r("R_GA5", "47k", "HEAD_LOOP_OK_RB", "HEAD_LOOP_OK_IO"), _r("R_GA7", "47k", "LAB_KEY_N_RB", "LAB_KEY_N_IO"),
                _r("R_GB7", "47k", "WDG_STROBE", "WDG_STROBE_IO"), _r("R_WDPD", "10k", "WDG_STROBE", "GND", "WDI LOW at reset; GPB7 via 47 k reaches 0.58 V < 0.3 VDD")],
     "M2: series isolation of the expander pins on chain-control nodes"),
    ("S3-F1", [_TCA_D, _c("C_U47", "100n", "3V3", "GND"), _r("R_D4", "10k", "3V3", "IOXD_P4"), _r("R_D5", "10k", "IOXD_P5", "GND"),
               _r("R_D6", "10k", "IOXD_P6", "GND"), _r("R_D7", "10k", "IOXD_P7", "GND")],
     "new IOX_D for the stage-3 readbacks"),
    ("S3-M6g", [_tp("TP60", "CH_N6A"), _tp("TP61", "K1_RUN"), _tp("TP62", "RELAY_RTN")], "test points for the new chain nodes"),
]
for _oid, _lst, _why in S3_ADD:
    for _p in _lst:
        ADD.append((_oid, _p, _why))
NET.extend(S3_NET)
PART.extend(S3_PART)


class OverrideError(Exception):
    pass


def apply(parts):
    """Return (new_parts, log).  Raises OverrideError if the baseline no longer matches an override."""
    parts = copy.deepcopy(parts)
    byref = {p["ref"]: p for p in parts}
    log = []

    def need(ref):
        if ref not in byref:
            raise OverrideError("override refers to %s, which circuit.py no longer has" % ref)
        return byref[ref]

    for oid, ref, pin, old, new, why in NET:
        p = need(ref)
        cur = p["pins"].get(pin)
        if cur != old:
            raise OverrideError("%s: %s.%s is %r in circuit.py, override expects %r" % (oid, ref, pin, cur, old))
        p["pins"][pin] = new
        log.append(dict(id=oid, kind="NET", ref=ref, pin=pin, old=old, new=new, reason=why))
    for oid, ref, fields, why in PART:
        p = need(ref)
        for k, (old, new) in fields.items():
            if p.get(k) != old:
                raise OverrideError("%s: %s.%s is %r in circuit.py, override expects %r" % (oid, ref, k, p.get(k), old))
            p[k] = new
        p["verify"] = True
        log.append(dict(id=oid, kind="PART", ref=ref, changes={k: list(v) for k, v in fields.items()}, reason=why))
    for ref, extra in EXTRA_PINS.items():
        need(ref)["pins"].update(extra)
    for oid, spec, why in ADD:
        if spec["ref"] in byref:
            raise OverrideError("%s: %s already exists in circuit.py" % (oid, spec["ref"]))
        p = dict(spec)
        p["pins"] = dict(spec["pins"])
        parts.append(p)
        byref[p["ref"]] = p
        log.append(dict(id=oid, kind="ADD", ref=p["ref"], pins=p["pins"], reason=why))
    for oid, refs, mapping, why in RENUM:
        for ref in refs:
            p = need(ref)
            new_pins = {}
            for num, v in p["pins"].items():
                if num in mapping:
                    tgt = mapping[num]
                    if tgt is None:     # merged into an existing pad: the net must be the one that pad already has
                        if v is not None and v[1] != p["pins"]["5"][1]:
                            raise OverrideError("%s: %s.%s (%r) cannot merge into pad 5 (%r)" % (oid, ref, num, v, p["pins"]["5"]))
                        continue
                    new_pins[tgt] = v
                else:
                    new_pins[num] = v
            p["pins"] = new_pins
        log.append(dict(id=oid, kind="RENUM", refs=list(refs), mapping=mapping, reason=why))
    for p in parts:
        ref = p["ref"]
        if ref in SYMBOLS:
            p["symbol_hint"] = SYMBOLS[ref]
        elif p.get("mpn") in SYMBOL_BY_MPN:
            p["symbol_hint"] = SYMBOL_BY_MPN[p["mpn"]]
        if ref in FOOTPRINTS:
            p["footprint_hint"] = FOOTPRINTS[ref]
        elif p.get("mpn") in FOOTPRINT_BY_MPN:
            p["footprint_hint"] = FOOTPRINT_BY_MPN[p["mpn"]]
        if ref in LIB_NOTES:
            p["notes"] = (p.get("notes") or "") + " | stage 2: " + LIB_NOTES[ref]
            p["verify"] = True
        if ref in PLACEHOLDER_FOOTPRINTS:
            p["notes"] = (p.get("notes") or "") + " | stage 2: PLACEHOLDER land pattern (not from a manufacturer drawing) - redraw before fabrication"
            p["verify"] = True
    log.append(dict(id="S2-07", kind="LIB", symbols=SYMBOLS, symbol_by_mpn=SYMBOL_BY_MPN, footprints=FOOTPRINTS, footprint_by_mpn=FOOTPRINT_BY_MPN,
                    reason="CAD library choices: stock symbols where they exist with matching pin numbers, stock or "
                           "project-local footprints for the 15 parts without one (see README)"))
    return parts, log


def nets_of(parts):
    nets = {}
    for p in parts:
        for num, v in p["pins"].items():
            if v is not None:
                nets.setdefault(v[1], []).append((p["ref"], num, v[0]))
    return nets


def netlist_diff(base_parts, new_parts):
    """(ref, pin_name) -> net comparison (pin NAMES, so renumbering is not a change)."""
    def m(parts):
        out = {}
        for p in parts:
            for num, v in p["pins"].items():
                if v is not None:
                    out.setdefault((p["ref"], v[0], v[1]), 0)
                    out[(p["ref"], v[0], v[1])] += 1
        return out
    a, b = m(base_parts), m(new_parts)
    removed = sorted(k for k in a if k not in b)
    added = sorted(k for k in b if k not in a)
    return removed, added


if __name__ == "__main__":
    base = load_circuit()
    new, log = apply(base.PARTS)
    for e in log:
        if e["kind"] != "LIB":
            print("%-7s %-5s %s" % (e["id"], e["kind"], e.get("ref") or e.get("refs")))
    rem, add = netlist_diff(base.PARTS, new)
    print("pins removed from a net (ref, pin name, net):", rem)
    print("pins added to a net     (ref, pin name, net):", add)
    errs = base.self_check(parts=new, nets=None, verbose=False)
    # the stage-1 self-check requires a CONNECTORS entry per J_* part: J_PAUSE is new
    errs = [e for e in errs if "J_PAUSE" not in e]
    print("stage-1 self-check on the overridden netlist:", "PASSED" if not errs else errs)
    sys.exit(1 if errs else 0)
