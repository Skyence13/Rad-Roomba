#!/usr/bin/env python3
"""RR-HEAD-ACQ rev A -- complete net-level circuit definition (tool-neutral, no dependencies).

Owner: head electronics lead (stage 1).  Consumers: stage-2 schematic/PCB flow, firmware, harness.

    import circuit            -> circuit.PARTS (list of dict), circuit.NETS, circuit.NET_CLASSES,
                                 circuit.CONNECTORS, circuit.MCU_PINMAP, circuit.BOARD
    python3 circuit.py        -> self-check report (must end with "SELF-CHECK PASS")

Part record: dict(ref, value, mpn, manufacturer, description, package, symbol_hint, footprint_hint,
                  pins={pin_number: (pin_name, net) | None for an intentional no-connect},
                  block, dnp, tolerance, rating, notes, verify)

Conventions
* One ground net "GND" (solid plane; analogue/digital separation is by placement, see layout_guidance.md).
  "BUS_GND" is the isolated RS-485 side.  "HTR_N" is the heater return and is NOT connected to GND on this board.
* Channel names: F0..F3 = floor lanes 0..3 (S0 = robot left), R0..R3 = reference lanes.  Firmware chain index
  0..7 = F0..F3, R0..R3.  Channel nets are prefixed "F0_", "R2_" ...
* Reference designators: channel c (0..7) uses 100*(c+1)+k, lane n uses 1000+100*n+k, board-level blocks
  use 2000 + 100*i + k.  The same generator function builds every lane, and the self-check proves that the
  four lanes are identical after renaming.
* symbol_hint / footprint_hint are KiCad stock library names where one with the same pinout is believed to
  exist; they are HINTS (not checked against an installed library) -- the pin dictionary is authoritative.
* verify=True marks a manufacturer part number, orderable suffix or pin-out that could not be confirmed
  against a manufacturer document from this machine.  Passive MPNs are built from the vendor series rules
  (Yageo RC/RT, Murata GRM) and carry mpn_rule=True.
* MCU pin assignment is copied from firmware/head/pinmap.yaml (FINAL, STM32G474VET6 LQFP100) and re-checked
  against that file by the self-check when PyYAML is available.
"""

PARTS = []
_REFS = {}
_COUNTERS = {}

FP_R = {"0402": "Resistor_SMD:R_0402_1005Metric", "0603": "Resistor_SMD:R_0603_1608Metric",
        "0805": "Resistor_SMD:R_0805_2012Metric", "1206": "Resistor_SMD:R_1206_3216Metric",
        "2512": "Resistor_SMD:R_2512_6332Metric"}
FP_C = {"0402": "Capacitor_SMD:C_0402_1005Metric", "0603": "Capacitor_SMD:C_0603_1608Metric",
        "0805": "Capacitor_SMD:C_0805_2012Metric", "1206": "Capacitor_SMD:C_1206_3216Metric",
        "1210": "Capacitor_SMD:C_1210_3225Metric"}
R_RATING = {"0402": "62.5 mW, 50 V", "0603": "100 mW, 75 V", "0805": "125 mW, 150 V", "1206": "250 mW, 200 V",
            "2512": "1 W"}

# name: (value, mpn, package, dielectric, voltage, tolerance)
CAPS = {
    "10p":     ("10pF", "GRM1555C1H100JA01D", "0402", "C0G", "50 V", "5%"),
    "100p_1":  ("100pF", "GRM1555C1H101FA01D", "0402", "C0G", "50 V", "1%"),
    "100p":    ("100pF", "GRM1555C1H101JA01D", "0402", "C0G", "50 V", "5%"),
    "220p":    ("220pF", "GRM1555C1H221JA01D", "0402", "C0G", "50 V", "5%"),
    "330p":    ("330pF", "GRM1555C1H331JA01D", "0402", "C0G", "50 V", "5%"),
    "1n":      ("1nF", "GRM1555C1H102JA01D", "0402", "C0G", "50 V", "5%"),
    "4n7":     ("4.7nF", "GRM155R71H472KA01D", "0402", "X7R", "50 V", "10%"),
    "10n":     ("10nF", "GRM155R71H103KA88D", "0402", "X7R", "50 V", "10%"),
    "22n":     ("22nF", "GRM155R71H223KA12D", "0402", "X7R", "50 V", "10%"),
    "100n":    ("100nF", "GRM155R71C104KA88D", "0402", "X7R", "16 V", "10%"),
    "100n_50": ("100nF", "GRM188R71H104KA93D", "0603", "X7R", "50 V", "10%"),
    "470n":    ("470nF", "GRM188R71C474KA88D", "0603", "X7R", "16 V", "10%"),
    "1u":      ("1uF", "GRM188R71C105KA12D", "0603", "X7R", "16 V", "10%"),
    "4u7":     ("4.7uF", "GRM188R61A475KE15D", "0603", "X5R", "10 V", "10%"),
    "10u":     ("10uF", "GRM21BR61C106KE15L", "0805", "X5R", "16 V", "10%"),
    "22u":     ("22uF", "GRM21BR61A226ME44L", "0805", "X5R", "10 V", "20%"),
    "4u7_50":  ("4.7uF", "GRM31CR71H475KA12L", "1206", "X7R", "50 V", "10%"),
    "10u_25":  ("10uF", "GRM31CR71E106KA12L", "1206", "X7R", "25 V", "10%"),
    "1n_100":  ("1nF", "GRM188R72A102KA01D", "0603", "X7R", "100 V", "10%"),
    "10n_100": ("10nF", "GRM188R72A103KA01D", "0603", "X7R", "100 V", "10%"),
    "100n_100": ("100nF", "GRM188R72A104KA35D", "0603", "X7R", "100 V", "10%"),
    "1u_100":  ("1uF", "GRM31CR72A105KA01L", "1206", "X7R", "100 V", "10%"),
    "2u2_100": ("2.2uF", "GRM32ER72A225KA35L", "1210", "X7R", "100 V", "10%"),
}


def _next(scope, prefix, base):
    key = (scope, prefix)
    _COUNTERS[key] = _COUNTERS.get(key, 0) + 1
    return "%s%d" % (prefix, base + _COUNTERS[key])


class Scope:
    """Reference-designator allocator for one block instance (channel, lane or board-level block)."""

    def __init__(self, name, base, block):
        self.name, self.base, self.block = name, base, block

    def ref(self, prefix):
        return _next(self.name, prefix, self.base)


def add(sc, prefix, value, mpn, mfr, desc, package, sym, fp, pins, dnp=False, notes="", verify=False,
        tolerance=None, rating=None, npins=None, **extra):
    ref = sc.ref(prefix)
    if ref in _REFS:
        raise ValueError("duplicate reference " + ref)
    p = dict(ref=ref, value=value, mpn=mpn, manufacturer=mfr, description=desc, package=package,
             symbol_hint=sym, footprint_hint=fp,
             pins={str(k): (v if (v is not None and v[1] is not None) else None) for k, v in pins.items()},
             block=sc.block,
             instance=sc.name, dnp=dnp, tolerance=tolerance, rating=rating, notes=notes, verify=verify,
             npins=npins if npins is not None else len(pins))
    p.update(extra)
    PARTS.append(p)
    _REFS[ref] = p
    return p


def _rcode(ohms):
    if ohms == 0:
        return "0R"
    for mult, letter in ((1e6, "M"), (1e3, "K"), (1.0, "R")):
        if ohms >= mult:
            v = ohms / mult
            s = ("%.3g" % v)
            if "." in s:
                a, b = s.split(".")
                return a + letter + b
            return s + letter
    return ("%.3g" % ohms).replace("0.", "R")


def _rtext(ohms):
    if ohms == 0:
        return "0R"
    if ohms >= 1e6:
        return ("%.3g" % (ohms / 1e6)) + "M"
    if ohms >= 1e3:
        return ("%.3g" % (ohms / 1e3)) + "k"
    return ("%.3g" % ohms) + "R"


def R(sc, ohms, a, b, pkg="0402", tol="1%", desc="", dnp=False, notes=""):
    if ohms == 0:
        mpn = "RC%sJR-070RL" % pkg
    elif tol == "0.1%":
        mpn = "RT%sBRD07%sL" % (pkg, _rcode(ohms))
    else:
        mpn = "RC%sFR-07%sL" % (pkg, _rcode(ohms))
    return add(sc, "R", _rtext(ohms), mpn, "Yageo", desc or "resistor", pkg, "Device:R", FP_R[pkg],
               {1: ("1", a), 2: ("2", b)}, dnp=dnp, notes=notes, tolerance=tol, rating=R_RATING[pkg], mpn_rule=True,
               ohms=ohms)


def C(sc, key, a, b, desc="", dnp=False, notes=""):
    value, mpn, pkg, diel, volt, tol = CAPS[key]
    return add(sc, "C", value, mpn, "Murata", desc or "capacitor", pkg, "Device:C", FP_C[pkg],
               {1: ("1", a), 2: ("2", b)}, dnp=dnp, notes=notes, tolerance=tol, rating="%s %s" % (diel, volt),
               mpn_rule=True)


def TP(sc, net, label):
    return add(sc, "TP", label, "5019", "Keystone (pad only when DNP)", "test point: " + label, "pad 1.0 mm",
               "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.0mm", {1: ("1", net)}, dnp=True,
               notes="bare pad; Keystone 5019 loop may be soldered for bring-up")


def FB(sc, a, b, kind="600R"):
    mpn = {"600R": "BLM18AG601SN1D", "220R": "BLM18PG221SN1D"}[kind]
    return add(sc, "FB", kind + " @100MHz", mpn, "Murata", "ferrite bead", "0603", "Device:FerriteBead",
               "Inductor_SMD:L_0603_1608Metric", {1: ("1", a), 2: ("2", b)},
               rating={"600R": "0.5 A", "220R": "1.4 A"}[kind])


def opamp_sot23_6(sc, mpn, out, inp, inn, vcc, desc):
    """OPA838 / OPA836 DBV-6: 1 VOUT, 2 VS-, 3 VIN+, 4 VIN-, 5 PD (high = on), 6 VS+ (datasheet SBOS867)."""
    return add(sc, "U", mpn[:6], mpn, "Texas Instruments", desc, "SOT-23-6", "Amplifier_Operational:OPA836xDBV",
               "Package_TO_SOT_SMD:SOT-23-6",
               {1: ("VOUT", out), 2: ("VS-", "GND"), 3: ("VIN+", inp), 4: ("VIN-", inn), 5: ("PD", vcc),
                6: ("VS+", vcc)})


def dual_diode(sc, mpn, low, high, common, desc):
    """BAV99 / BAT54S / BAV199 SOT-23: 1 = anode of D1, 2 = cathode of D2, 3 = common (K1/A2)."""
    sym = {"BAV99,215": "Diode:BAV99", "BAT54S,215": "Diode:BAT54S", "BAV199,215": "Diode:BAV99"}[mpn]
    return add(sc, "D", mpn.split(",")[0], mpn, "Nexperia", desc, "SOT-23", sym, "Package_TO_SOT_SMD:SOT-23",
               {1: ("A1", low), 2: ("K2", high), 3: ("COM", common)})


def nmos(sc, mpn, g, s, d, desc):
    return add(sc, "Q", mpn[:6], mpn, "onsemi", desc, "SOT-23", "Transistor_FET:" + mpn[:6],
               "Package_TO_SOT_SMD:SOT-23", {1: ("G", g), 2: ("S", s), 3: ("D", d)})


def gh(sc, n, nets, desc, names=None):
    """JST GH side-entry header SMnnB-GHS-TB, 1.25 mm, 1 A, 50 V, friction + positive lock, 4.05 mm high."""
    pins = {i + 1: ((names[i] if names else "P%d" % (i + 1)), nets[i]) if nets[i] is not None else None
            for i in range(n)}
    pins["MP"] = ("MP", "GND")
    return add(sc, "J", "GH-%d" % n, "SM%02dB-GHS-TB(LF)(SN)" % n, "JST", desc, "JST GH %d-pos side entry" % n,
               "Connector_Generic_MountingPin:Conn_01x%02d_MountingPin" % n,
               "Connector_JST:JST_GH_SM%02dB-GHS-TB_1x%02d-1MP_P1.25mm_Horizontal" % (n, n), pins)


def ufl(sc, net, desc):
    return add(sc, "J", "U.FL", "U.FL-R-SMT-1(10)", "Hirose", desc, "U.FL receptacle",
               "Connector:Conn_Coaxial", "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical",
               {1: ("SIG", net), 2: ("GND", "GND")},
               notes="1.25 mm high, mated 2.5 mm max; 60 V AC rated. Mate with I-PEX MHF I LK (locking) or U.FL-LP")


CHANNELS = ["F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"]


def chan_index(ch):
    return CHANNELS.index(ch)


# =============================================================================================== per-channel AFE
def channel(ch):
    """One optical channel: SiPM connectors, bias filter, input network, test injection, preamp, fast shaper,
    discriminators; floor channels add the slow (alpha) path."""
    c = chan_index(ch)
    floor = ch[0] == "F"
    sc = Scope(ch, 100 * (c + 1), "AFE_FLOOR" if floor else "AFE_REF")
    n = lambda s: "%s_%s" % (ch, s)                                     # noqa: E731
    V5 = n("V5")
    VBL = n("VBL")

    # --- connectors (rear edge, centred on the lane) and bias filter
    ufl(sc, n("A"), "SiPM anode signal coax, %s" % ch)
    ufl(sc, n("HVF"), "SiPM cathode bias coax (centre = filtered HV, shield = ground return), %s" % ch)
    R(sc, 1000, "HV_BUS", n("HV1"), "0805", desc="bias filter stage 1 (1 k x 1 uF = 160 Hz)")
    C(sc, "1u_100", n("HV1"), "GND")
    R(sc, 100, n("HV1"), n("HVF"), "0603", desc="bias filter stage 2 (100 R x 100 nF)")
    C(sc, "100n_100", n("HVF"), "GND", desc="cathode charge reservoir at the connector")

    # --- anode load, clamp, trim node (anode DC return = trim buffer through the current-sense resistor)
    dual_diode(sc, "BAV99,215", "GND", "+5V_A", n("A"), "anode clamp (SiPM short / hot-plug)")
    R(sc, 20, n("A"), n("TRIM"), "0603", desc="anode load R_IN (2 x 20 R = 10 R)",
      notes="R_IN is a bring-up selection: 2x10 R .. 1x49.9 R, see head_afe_budget.md 2.2")
    R(sc, 20, n("A"), n("TRIM"), "0603", desc="anode load R_IN (second half)")
    C(sc, "4u7", n("TRIM"), "GND", desc="trim node AC ground")
    C(sc, "100n", n("TRIM"), "GND")
    R(sc, 4990, n("TRIMDRV"), n("TRIM"), "0402", "0.1%", desc="anode current sense: I = (V_TRIM - V_TRIMDRV)/4.99k")
    R(sc, 220e3, n("TRIM"), n("TRIMFB"), desc="trim buffer DC feedback (in-loop compensation)")
    C(sc, "100n", n("TRIMDRV"), n("TRIMFB"), desc="trim buffer AC feedback")
    R(sc, 1000, "TRIM_DAC_" + ch, n("TRIMIN"), desc="trim DAC filter")
    C(sc, "100n", n("TRIMIN"), "GND")
    R(sc, 10e3, n("TRIMDRV"), "IMON_" + ch, desc="per-channel bias current monitor to the IMON mux")

    # --- charge-injection test pulser (local switch, DC amplitude bus, one-of-eight enable)
    add(sc, "U", "74LVC2G53", "SN74LVC2G53DCUR", "Texas Instruments", "SPDT analogue switch with inhibit: test step",
        "VSSOP-8 (DCU)", "Analog_Switch:SN74LVC2G53", "Package_SO:VSSOP-8_2.3x2mm_P0.5mm",
        {1: ("COM", n("TPSW")), 2: ("INH", "TP_INH_%s_N" % ch), 3: ("GND", "GND"), 4: ("GND", "GND"),
         5: ("A", "PULSER_STROBE"), 6: ("Y2", n("TPV")), 7: ("Y1", n("TPG")), 8: ("VCC", "+3V3_EVT")},
        notes="A low: COM-Y1 (discharged), A high: COM-Y2 (amplitude). INH high = both off.")
    C(sc, "100n", "+3V3_EVT", "GND", desc="decoupling 74LVC2G53")
    R(sc, 1000, "PULSER_AMPL", n("TPV"), desc="pulser amplitude feed")
    C(sc, "100n", n("TPV"), "GND", desc="pulser charge reservoir (1000 x C_INJ)")
    R(sc, 100, n("TPG"), "GND", desc="pulser return-edge resistor (raise to slow the opposite-polarity edge)")
    R(sc, 49.9, n("TPSW"), n("TPI"), desc="pulser series resistor (R x C_INJ = 5 ns)")
    R(sc, 100e3, n("TPSW"), "GND", desc="defines the node when the switch is inhibited")
    C(sc, "100p_1", n("TPI"), n("A"), desc="C_INJ: Q = 100 pF x V(PULSER_AMPL), 250 pC full scale")
    C(sc, "1n", n("TPI"), n("A"), dnp=True, desc="optional C_INJ2 for alpha-scale charge (2.5 nC)")

    # --- channel supply and baseline
    FB(sc, "+5V_A", V5)
    C(sc, "4u7", V5, "GND", desc="channel supply bulk")
    R(sc, 100, "VBL", VBL, desc="baseline bus isolation")
    C(sc, "10u", VBL, "GND", desc="baseline AC ground")
    C(sc, "100n", VBL, "GND")

    # --- preamp: non-inverting x21, DC gain 1
    R(sc, 22, n("A"), n("PINA"), desc="preamp input protection")
    C(sc, "100n", n("PINA"), n("PIN"), desc="anode AC coupling (100 us with R bias)")
    R(sc, 1000, n("PIN"), VBL, desc="preamp input bias to baseline")
    opamp_sot23_6(sc, "OPA838IDBVR", n("PRE"), n("PIN"), n("PFB"), V5, "preamp, G = +21 (BW 14 MHz)")
    C(sc, "100n", V5, "GND", desc="decoupling preamp")
    R(sc, 499, n("PRE"), n("PFB"), desc="preamp R_F")
    R(sc, 24.9, n("PFB"), n("PG"), desc="preamp R_G (gain = 1 + 499/24.9)")
    C(sc, "10u", n("PG"), "GND", desc="preamp gain AC ground (640 Hz corner, DC gain 1)")
    R(sc, 453, n("PRE"), n("PRE_TP"), desc="10:1 probe resistor into a 50 ohm scope")
    TP(sc, n("PRE_TP"), ch + " PRE")
    R(sc, 1000, n("PRE"), n("MPRE"), desc="monitor tap: preamp")

    # --- fast shaper: CR 22 ns with pole-zero, x21, and comparator drive
    C(sc, "220p", n("PRE"), n("FS"), desc="fast CR: C_D")
    R(sc, 226, n("PRE"), n("FS"), desc="pole-zero R_PZ = t_recharge / C_D (226 R for 50 ns)",
      notes="bring-up selection from the measured SiPM recharge time; omit for no cancellation")
    R(sc, 100, n("FS"), VBL, desc="fast CR: R_D")
    opamp_sot23_6(sc, "OPA838IDBVR", n("FAST"), n("FS"), n("FFB"), V5, "fast shaper gain stage, G = +21")
    C(sc, "100n", V5, "GND", desc="decoupling fast stage")
    R(sc, 499, n("FAST"), n("FFB"), desc="fast R_F")
    C(sc, "10p", n("FAST"), n("FFB"), desc="fast integration pole (5 ns)")
    R(sc, 24.9, n("FFB"), VBL, desc="fast R_G to the baseline AC ground")
    R(sc, 330, n("FAST"), n("FCMP"), desc="comparator drive / clamp current limit (4 mA into the clamp at full overdrive)")
    dual_diode(sc, "BAT54S,215", "GND", "+3V3_EVT", n("FCMP"), "clamp to the comparator supply")
    R(sc, 1000, n("FCMP"), n("MFAST"), desc="monitor tap: fast")
    lld, uld = ("BETA_LLD", "BETA_ULD") if floor else ("REF_LLD", "REF_ULD")
    R(sc, 1000, "THR_LLD_" + ch, n("TL"), desc=lld + " threshold filter")
    C(sc, "100n", n("TL"), "GND")
    R(sc, 1000, "THR_ULD_" + ch, n("TU"), desc=uld + " threshold filter")
    C(sc, "100n", n("TU"), "GND")
    add(sc, "U", "TLV3502", "TLV3502AIDCNR", "Texas Instruments", "dual 4.5 ns comparator: %s (A), %s (B)" % (lld, uld),
        "SOT-23-8 (DCN)", "Comparator:TLV3502", "Package_TO_SOT_SMD:SOT-23-8",
        {1: ("+INA", n("FCMP")), 2: ("-INA", n("TL")), 3: ("+INB", n("FCMP")), 4: ("-INB", n("TU")),
         5: ("V-", "GND"), 6: ("OUTB", n("CULD")), 7: ("OUTA", n("CLLD")), 8: ("V+", "+3V3_EVT")})
    C(sc, "100n", "+3V3_EVT", "GND", desc="decoupling comparator")
    R(sc, 100, n("CLLD"), "LLD_" + ch, desc="raw (unlatched) LLD to the MCU timer capture pin, source series")

    # --- slow path (floor only): 1 us integrator, 52 us baseline CR, x5, ALPHA comparator
    if floor:
        R(sc, 1000, n("PRE"), n("SI"), desc="slow integrator R (1 us)")
        C(sc, "1n", n("SI"), "GND", desc="slow integrator C")
        C(sc, "4n7", n("SI"), n("SS"), desc="slow baseline CR (52 us)")
        R(sc, 10e3, n("SS"), VBL, desc="slow baseline CR")
        opamp_sot23_6(sc, "OPA836IDBVR", n("SLOW"), n("SS"), n("SFB"), V5, "slow shaper gain stage, G = +5")
        C(sc, "100n", V5, "GND", desc="decoupling slow stage")
        R(sc, 2000, n("SLOW"), n("SFB"), desc="slow R_F")
        R(sc, 499, n("SFB"), VBL, desc="slow R_G")
        R(sc, 330, n("SLOW"), n("SCMP"), desc="comparator drive / clamp current limit (4 mA into the clamp at full overdrive)")
        dual_diode(sc, "BAT54S,215", "GND", "+3V3_EVT", n("SCMP"), "clamp to the comparator supply")
        R(sc, 1000, n("SCMP"), n("MSLOW"), desc="monitor tap: slow")
        R(sc, 1000, "THR_ALPHA_" + ch, n("TA"), desc="ALPHA threshold filter")
        C(sc, "100n", n("TA"), "GND")
        add(sc, "U", "TLV3501", "TLV3501AIDBVR", "Texas Instruments", "4.5 ns comparator: ALPHA (slow path)",
            "SOT-23-6", "Comparator:TLV3501", "Package_TO_SOT_SMD:SOT-23-6",
            {1: ("-IN", n("TA")), 2: ("V-", "GND"), 3: ("+IN", n("SCMP")), 4: ("V+", "+3V3_EVT"),
             5: ("OUT", n("CALPHA")), 6: ("SHDN", "GND")},
            notes="SHDN low = enabled (disabled only within 0.9 V of V+)")
        C(sc, "100n", "+3V3_EVT", "GND", desc="decoupling ALPHA comparator")


# =============================================================================================== per-lane shared
def lane(k):
    """Parts shared by the floor and reference channel of lane k: trim buffer, event latches, monitor mux,
    auxiliary pigtail connector (NTC + optional LED pulser)."""
    f, r = "F%d" % k, "R%d" % k
    sc = Scope("L%d" % k, 1000 + 100 * k, "LANE")
    V33 = "+3V3_EVT"
    L = "L%d_" % k

    add(sc, "U", "TLV9062", "TLV9062IDR", "Texas Instruments", "dual RRIO op-amp: anode trim buffers (A floor, B ref)",
        "SOIC-8", "Amplifier_Operational:LM358", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("OUTA", f + "_TRIMDRV"), 2: ("-INA", f + "_TRIMFB"), 3: ("+INA", f + "_TRIMIN"), 4: ("V-", "GND"),
         5: ("+INB", r + "_TRIMIN"), 6: ("-INB", r + "_TRIMFB"), 7: ("OUTB", r + "_TRIMDRV"), 8: ("V+", "+5V_A")})
    C(sc, "100n", "+5V_A", "GND", desc="decoupling trim buffer")

    # latch clocks = comparator OR LATCH_TEST
    add(sc, "U", "74LVC32A", "SN74LVC32APWR", "Texas Instruments", "quad OR: latch clock = comparator | LATCH_TEST",
        "TSSOP-14", "74xx:74LS32", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        {1: ("1A", f + "_CLLD"), 2: ("1B", "LATCH_TEST"), 3: ("1Y", f + "_KLLD"),
         4: ("2A", f + "_CULD"), 5: ("2B", "LATCH_TEST"), 6: ("2Y", f + "_KULD"), 7: ("GND", "GND"),
         8: ("3Y", f + "_KALPHA"), 9: ("3A", f + "_CALPHA"), 10: ("3B", "LATCH_TEST"),
         11: ("4Y", r + "_KLLD"), 12: ("4A", r + "_CLLD"), 13: ("4B", "LATCH_TEST"), 14: ("VCC", V33)})
    C(sc, "100n", V33, "GND", desc="decoupling OR")
    add(sc, "U", "74LVC1G32", "SN74LVC1G32DCKR", "Texas Instruments", "OR: REF_ULD latch clock", "SC-70-5",
        "74xGxx:74LVC1G32", "Package_TO_SOT_SMD:SOT-353_SC-70-5",
        {1: ("A", r + "_CULD"), 2: ("B", "LATCH_TEST"), 3: ("GND", "GND"), 4: ("Y", r + "_KULD"), 5: ("VCC", V33)})
    C(sc, "100n", V33, "GND", desc="decoupling OR")

    def ff(desc, c1, clr1, q1, c2, clr2, q2):
        add(sc, "U", "74LVC74A", "SN74LVC74APWR", "Texas Instruments", "dual D latch, D = 1: " + desc, "TSSOP-14",
            "74xx:74HC74", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
            {1: ("1CLR_N", clr1), 2: ("1D", V33 if c1 != "GND" else "GND"), 3: ("1CLK", c1), 4: ("1PRE_N", V33),
             5: ("1Q", q1), 6: ("1Q_N", None), 7: ("GND", "GND"), 8: ("2Q_N", None), 9: ("2Q", q2),
             10: ("2PRE_N", V33), 11: ("2CLK", c2), 12: ("2D", V33 if c2 != "GND" else "GND"),
             13: ("2CLR_N", clr2), 14: ("VCC", V33)},
            notes="tw(CLK) >= 3.3 ns, tw(CLR) >= 3.3 ns at 3.3 V (datasheet)")
        C(sc, "100n", V33, "GND", desc="decoupling latch")

    clr_f, clr_r = "CLR_%s_N" % f, "CLR_%s_N" % r
    ff("BUSY(BETA_LLD) + BETA_ULD", f + "_KLLD", clr_f, L + "QBUSY_F", f + "_KULD", clr_f, L + "QULD_F")
    ff("ALPHA + BUSY(REF_LLD)", f + "_KALPHA", clr_f, L + "QALPHA_F", r + "_KLLD", clr_r, L + "QBUSY_R")
    ff("REF_ULD + spare", r + "_KULD", clr_r, L + "QULD_R", "GND", V33, None)
    for q, net in ((L + "QBUSY_F", "BUSY_" + f), (L + "QULD_F", "ULD_" + f), (L + "QALPHA_F", "ALPHA_" + f),
                   (L + "QBUSY_R", "BUSY_" + r), (L + "QULD_R", "ULD_" + r)):
        R(sc, 47, q, net, desc="latch output source series (long trace to the MCU)")
        R(sc, 100e3, net, "GND", desc="pull-down: missing latch supply reads idle (pinmap)")
    R(sc, 100e3, "LLD_" + f, "GND", desc="pull-down raw LLD (pinmap)")
    R(sc, 100e3, "LLD_" + r, "GND", desc="pull-down raw LLD (pinmap)")
    R(sc, 10e3, clr_f, "GND", desc="CLR pull-down: latches held clear in reset (pinmap)")
    R(sc, 10e3, clr_r, "GND", desc="CLR pull-down: latches held clear in reset (pinmap)")

    # lane monitor multiplexer (only the selected lane drives MON_BUS)
    add(sc, "U", "TMUX1108", "TMUX1108PWR", "Texas Instruments", "8:1 monitor mux of this lane", "TSSOP-16",
        "Analog_Switch:TMUX1108PW", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        {1: ("A0", "MON_MUX_A2"), 2: ("EN", "MON_EN_%d" % k), 3: ("VSS", "GND"), 4: ("S1", f + "_MFAST"),
         5: ("S2", r + "_MFAST"), 6: ("S3", f + "_MSLOW"), 7: ("S4", r + "_MPRE"), 8: ("D", "MON_BUS"),
         9: ("S8", "GND"), 10: ("S7", L + "MVBL"), 11: ("S6", "GND"), 12: ("S5", f + "_MPRE"), 13: ("VDD", "+5V_A"),
         14: ("GND", "GND"), 15: ("A2", "MON_EXT"), 16: ("A1", "MON_MUX_A3")},
        notes="code (EXT,A3,A2): 000 floor fast, 001 ref fast, 010 floor slow, 011 ref preamp, 100 floor preamp, "
              "110 baseline, 101/111 ground. 1.8 V-compatible logic at VDD = 5 V (datasheet)")
    C(sc, "100n", "+5V_A", "GND", desc="decoupling monitor mux")
    R(sc, 1000, f + "_VBL", L + "MVBL", desc="monitor tap: baseline")

    # auxiliary pigtail: NTC at the SiPM carriers, optional LED pulser, 3.3 V for an active sensor
    gh(sc, 6, ["NTC_SIPM%d" % k, "GND", L + "LED_A", L + "LED_K", L + "AUX3V3", "GND"],
       "lane %d SiPM auxiliary pigtail" % k, ["NTC", "NTC_RTN", "LED_A", "LED_K", "+3V3_AUX", "GND"])
    R(sc, 10e3, "VREF_ADC", "NTC_SIPM%d" % k, "0402", "0.1%", desc="NTC divider (10 k B3435-class NTC to GND)")
    C(sc, "100n", "NTC_SIPM%d" % k, "GND")
    add(sc, "D", "PESD5V0S1BA", "PESD5V0S1BA,115", "Nexperia", "ESD protection NTC line", "SOD-323", "Device:D_TVS",
        "Diode_SMD:D_SOD-323", {1: ("1", "NTC_SIPM%d" % k), 2: ("2", "GND")}, verify=True)
    R(sc, 100, "+3V3", L + "AUX3V3", desc="auxiliary 3.3 V feed (short-circuit limited)")
    C(sc, "100n", L + "AUX3V3", "GND")
    R(sc, 10e3, "V_LED", L + "LED_A", desc="LED pulser charge resistor")
    C(sc, "100p", L + "LED_A", "GND", desc="LED pulser storage capacitor (light ~ C x (V_LED - Vf))")
    nmos(sc, "BSS138LT1G", L + "LED_G", "GND", L + "LED_K", "LED pulser switch")
    R(sc, 100, "LED_STROBE", L + "LED_G", desc="LED gate series")
    R(sc, 100e3, L + "LED_G", "GND", desc="LED gate pull-down")


def lane_shield(k):
    """Attachment pattern for one formed shield can per lane over the preamps, shapers and comparators.
    The prototype housing is printed plastic with no shielding (IB-09), so the can is part of the board design."""
    sc = Scope("L%d" % k, 1000 + 100 * k, "LANE")
    for i in range(12):
        add(sc, "SH", "shield clip", "S1711-46R", "Harwin", "SMT shield-can clip %d/12 (3 per side of the lane can)" % (i + 1),
            "shield clip", "Device:RF_Shield_One_Piece", "RF_Shielding:Harwin_S1711-46R (project-local footprint)",
            {1: ("1", "GND")}, verify=True,
            notes="clip size, wall thickness range and seated height UNVERIFIED; can outline in BOARD['lane_shield']")
    add(sc, "SH", "lane shield can", "RR-HEAD-SHLD-A", "(custom formed part)", "formed can 36.0 x 32.0 x 5.0 mm outside, 0.2 mm "
        "tin-plated steel or nickel silver, held by the 12 clips; mouse-holes for the two anode traces and the bias/threshold feeds",
        "custom shield can", "Device:RF_Shield_One_Piece", "none (mechanical part, held by clips)", {}, npins=0, verify=True,
        notes="custom mechanical part, drawing owed by head mechanical from layout_guidance.md section 4")


for _ch in CHANNELS:
    channel(_ch)
for _k in range(4):
    lane(_k)
    lane_shield(_k)

# =============================================================================================== board-level blocks
def decap(sc, net, what, key="100n"):
    return C(sc, key, net, "GND", desc="decoupling " + what)


def microfit(sc, n, nets, names, desc):
    """Molex Micro-Fit 3.0 single-row right-angle header 43650-nn00: 3.00 mm pitch, positive latch,
    8.5 A per circuit with 18 AWG (Molex series data, UNVERIFIED from this machine)."""
    pins = {i + 1: (names[i], nets[i]) if nets[i] is not None else None for i in range(n)}
    return add(sc, "J", "Micro-Fit 3.0 1x%d RA" % n, "43650-%02d00" % n, "Molex", desc,
               "Micro-Fit 3.0 right-angle THT, %d circuits" % n, "Connector_Generic:Conn_01x%02d" % n,
               "Connector_Molex:Molex_Micro-Fit_3.0_43650-%02d00_1x%02d_P3.00mm_Horizontal" % (n, n), pins,
               verify=True,
               notes="Mating: receptacle 43645-%02d00 + terminals 43030 (18-24 AWG variant for the heater pair). "
                     "Seated height of the right-angle header is close to the 6.0 mm limit and is UNVERIFIED: "
                     "see CONTRACT_CHANGE_REQUESTS.md CCR-HE-02 (local 8 mm zone or alternative)." % n)


def sj(sc, a, b, desc):
    return add(sc, "JP", "open", "solder jumper", "(PCB feature)", desc, "solder jumper 2-pad",
               "Jumper:SolderJumper_2_Open", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
               {1: ("A", a), 2: ("B", b)}, notes="PCB feature, not a purchased part")


# ----------------------------------------------------------------------------------------------- power entry
def block_power_in():
    sc = Scope("PWR_IN", 2000, "POWER_IN")
    microfit(sc, 8, ["HEAD_PWR_P", "HEAD_PWR_N", "HEAD_HTR_P", "HEAD_HTR_N", "HEAD_LOOP_OUT", "HEAD_LOOP_RET",
                     "HEAD_PRES_ID", None],
             ["HEAD_PWR_P", "HEAD_PWR_N", "HEAD_HTR_P", "HEAD_HTR_N", "HEAD_LOOP_OUT", "HEAD_LOOP_RET",
              "HEAD_PRES_ID", "NC_RESERVED"], "J1 pigtail landing (board pin n = contract J1 pin n)")
    R(sc, 4700, "HEAD_PRES_ID", "HEAD_PWR_N", "0603", "0.1%", desc="presence code 4.70 k J1.7 to J1.2 (contract)")
    add(sc, "D", "SMBJ16A", "SMBJ16A", "Littelfuse", "input TVS, 16 V stand-off, 26 V clamp", "SMB (DO-214AA)",
        "Device:D_TVS", "Diode_SMD:D_SMB", {1: ("K", "HEAD_PWR_P"), 2: ("A", "HEAD_PWR_N")})
    add(sc, "L", "900R CM", "ACM4520-901-2P-T000", "TDK", "common-mode choke on the electronics pair", "4.5x2.0 mm",
        "Device:L_Coupled_1423", "Inductor_SMD:L_CommonMode_TDK_ACM4520", {1: ("1", "HEAD_PWR_P"), 2: ("2", "VIN_CM"),
        3: ("3", "GND"), 4: ("4", "HEAD_PWR_N")}, verify=True, rating="~1.5 A",
        notes="pin pairing 1-2 / 4-3 and current rating UNVERIFIED")
    C(sc, "100n_50", "VIN_CM", "GND", desc="eFuse input bypass")
    add(sc, "U", "TPS26600", "TPS26600PWPR", "Texas Instruments",
        "60 V eFuse: reverse-polarity and reverse-current blocking, UVLO/OVP, current limit, inrush control",
        "HTSSOP-16 PowerPAD", "Power_Management:TPS26600PWP", "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm",
        {1: ("IN", "VIN_CM"), 2: ("IN", "VIN_CM"), 3: ("UVLO", "EF_UVLO"), 4: ("NC", None), 5: ("OVP", "EF_OVP"),
         6: ("MODE", "EF_MODE"), 7: ("SHDN", "EF_SHDN"), 8: ("RTN", "EF_RTN"), 9: ("GND", "GND"),
         10: ("IMON", "EF_IMON"), 11: ("ILIM", "EF_ILIM"), 12: ("dVdT", "EF_DVDT"), 13: ("NC", None),
         14: ("FLT", "EF_FLT_N"), 15: ("OUT", "VIN_EF"), 16: ("OUT", "VIN_EF"), "EP": ("PAD", "EF_RTN")},
        notes="PowerPAD and all programming parts return to EF_RTN, which is NOT tied to GND (datasheet pin table).")
    R(sc, 866e3, "VIN_CM", "EF_UVLO", "0603", desc="UVLO/OVP divider top: UVLO 8.8 V rising / 8.0 V falling")
    R(sc, 68.1e3, "EF_UVLO", "EF_OVP", desc="UVLO/OVP divider middle")
    R(sc, 66.5e3, "EF_OVP", "EF_RTN", desc="UVLO/OVP divider bottom: OVP 17.5 V")
    R(sc, 12e3, "EF_ILIM", "EF_RTN", desc="current limit 1.0 A (datasheet: 12 k = 1 A)")
    C(sc, "22n", "EF_DVDT", "EF_RTN", desc="output slew control (inrush)")
    R(sc, 30.1e3, "EF_IMON", "EF_RTN", desc="eFuse current monitor load (test point)")
    R(sc, 0, "EF_MODE", "EF_RTN", dnp=True, desc="MODE strap (open = default fault response; fit to change)")
    R(sc, 100e3, "+3V3", "EF_FLT_N", desc="FLT pull-up (open drain)")
    TP(sc, "EF_IMON", "EF_IMON")
    TP(sc, "EF_SHDN", "EF_SHDN")
    TP(sc, "EF_MODE", "EF_MODE")
    C(sc, "10u_25", "VIN_EF", "GND", desc="pi filter C1")
    add(sc, "L", "10uH", "XAL4040-103MEB", "Coilcraft", "input pi-filter inductor", "4.0x4.0x4.1 mm", "Device:L",
        "Inductor_SMD:L_Coilcraft_XAL4040-XXX", {1: ("1", "VIN_EF"), 2: ("2", "VIN_F")}, verify=True, rating="Isat ~3 A")
    C(sc, "10u_25", "VIN_F", "GND", desc="pi filter C2")
    C(sc, "10u_25", "VIN_F", "VIN_DMP", desc="pi filter damping branch C")
    R(sc, 1, "VIN_DMP", "GND", "0805", desc="pi filter damping branch R")
    R(sc, 56e3, "VIN_F", "VIN_MON", desc="VIN monitor divider 1:6.6")
    R(sc, 10e3, "VIN_MON", "GND", desc="VIN monitor divider")
    C(sc, "100n", "VIN_MON", "GND")
    # cable shield drain and frame bonding (contract: shield to head frame through 1 Mohm || 10 nF)
    TP(sc, "SHLD_J1", "J1 SHIELD")
    R(sc, 1e6, "SHLD_J1", "FRAME", "0603", desc="J1 shield to frame")
    C(sc, "10n_100", "SHLD_J1", "FRAME", desc="J1 shield to frame")
    # interlock loop: potential-free series chain J1.5 -> front -> left -> right rail switch -> 1.00 k -> J1.6
    loop = ["HEAD_LOOP_OUT", "LOOP_A", "LOOP_B", "LOOP_C"]
    for i, z in enumerate("FLR"):
        gh(sc, 4, [loop[i], loop[i + 1], "BZ_%s_IN" % z, "GND"], "rail switch zone %s (NC contact in the loop)" % z,
           ["LOOP_IN", "LOOP_OUT", "AUX_N", "AUX_GND"])
        R(sc, 1000, "BZ_%s_IN" % z, "BUMP_ZONE_%s_N" % z, desc="zone auxiliary contact series")
        R(sc, 10e3, "+3V3", "BUMP_ZONE_%s_N" % z, desc="zone pull-up (active low)")
        C(sc, "100n", "BUMP_ZONE_%s_N" % z, "GND")
        add(sc, "D", "PESD5V0S1BA", "PESD5V0S1BA,115", "Nexperia", "ESD protection zone input", "SOD-323",
            "Device:D_TVS", "Diode_SMD:D_SOD-323", {1: ("1", "BZ_%s_IN" % z), 2: ("2", "GND")}, verify=True)
    R(sc, 1000, "LOOP_C", "HEAD_LOOP_RET", "0603", "0.1%", desc="interlock loop resistor 1.00 k (contract)")


# ----------------------------------------------------------------------------------------------- regulators
def block_regulators():
    sc = Scope("REG", 2100, "POWER_REG")
    C(sc, "4u7_50", "VIN_F", "GND", desc="buck input")
    C(sc, "100n_50", "VIN_F", "GND", desc="buck input HF")
    add(sc, "U", "LMR51606YF", "LMR51606YFDBVR", "Texas Instruments", "65 V 0.6 A buck, 1.1 MHz forced PWM",
        "SOT-23-6", "Regulator_Switching:LMR51606", "Package_TO_SOT_SMD:SOT-23-6",
        {1: ("CB", "BK_CB"), 2: ("GND", "GND"), 3: ("FB", "BK_FB"), 4: ("EN", "BK_EN"), 5: ("VIN", "VIN_F"),
         6: ("SW", "BK_SW")})
    C(sc, "100n_50", "BK_CB", "BK_SW", desc="bootstrap")
    R(sc, 100e3, "VIN_F", "BK_EN", desc="enable (eFuse UVLO is the system UVLO)")
    add(sc, "L", "10uH", "LPS4018-103MRB", "Coilcraft", "buck inductor", "4.0x4.0x1.8 mm", "Device:L",
        "Inductor_SMD:L_Coilcraft_LPS4018", {1: ("1", "BK_SW"), 2: ("2", "+5V6")}, verify=True, rating="Isat ~1.3 A")
    C(sc, "22u", "+5V6", "GND", desc="buck output")
    C(sc, "22u", "+5V6", "GND", desc="buck output")
    R(sc, 60.4e3, "+5V6", "BK_FB", desc="buck feedback: 0.8 V x (1 + 60.4/10.0) = 5.63 V")
    R(sc, 10e3, "BK_FB", "GND", desc="buck feedback")
    C(sc, "10p", "+5V6", "BK_FB", dnp=True, desc="feed-forward (fit if transient response needs it)")
    # analogue 5 V: LC + low-noise LDO
    for tag, out, mpn, load in (("A", "+5V_A", "TPS7A2050PDBVR", "op-amps, DACs, muxes"),):
        add(sc, "L", "10uH", "LQH32CN100K53L", "Murata", "post-filter inductor (10 uH / 22 uF = 10.7 kHz)", "1210",
            "Device:L", "Inductor_SMD:L_1210_3225Metric", {1: ("1", "+5V6"), 2: ("2", "+5V6_" + tag)}, rating="450 mA")
        C(sc, "22u", "+5V6_" + tag, "GND", desc="post-filter capacitor")
        add(sc, "U", "TPS7A2050", mpn, "Texas Instruments", "300 mA low-noise LDO 5.0 V (7 uVrms, 95 dB PSRR at 1 kHz): " + load,
            "SOT-23-5", "Regulator_Linear:TPS7A2050PDBV", "Package_TO_SOT_SMD:SOT-23-5",
            {1: ("IN", "+5V6_" + tag), 2: ("GND", "GND"), 3: ("EN", "+5V6_" + tag), 4: ("NC", None), 5: ("OUT", out)},
            verify=True, notes="input range 1.6-6.0 V (datasheet); DBV pin-out and orderable suffix UNVERIFIED")
        C(sc, "4u7", out, "GND", desc="LDO output")
    # digital 3.3 V and event-logic 3.3 V
    for tag, out, load in (("D", "+3V3", "MCU, bias boost, isolator logic side"), ("E", "+3V3_EVT", "comparators, latches")):
        src = "+5V6"
        if tag == "E":
            add(sc, "L", "10uH", "LQH32CN100K53L", "Murata", "post-filter inductor", "1210", "Device:L",
                "Inductor_SMD:L_1210_3225Metric", {1: ("1", "+5V6"), 2: ("2", "+5V6_E")}, rating="450 mA")
            C(sc, "22u", "+5V6_E", "GND", desc="post-filter capacitor")
            src = "+5V6_E"
        else:
            C(sc, "10u", "+5V6", "GND", desc="LDO input")
        add(sc, "U", "TLV76733", "TLV76733DRVR", "Texas Instruments", "1 A LDO 3.3 V: " + load, "WSON-6 2x2 (DRV)",
            "Regulator_Linear:TLV76733DRV", "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
            {1: ("OUT", out), 2: ("SNS", out), 3: ("GND", "GND"), 4: ("EN", src), 5: ("GND", "GND"), 6: ("IN", src),
             "EP": ("PAD", "GND")}, verify=True, notes="fixed-output DRV pin-out from datasheet; orderable suffix UNVERIFIED")
        C(sc, "10u", out, "GND", desc="LDO output")
    FB(sc, "+3V3", "+3V3A", "600R")
    C(sc, "1u", "+3V3A", "GND", desc="VDDA filter")
    C(sc, "10n", "+3V3A", "GND", desc="VDDA filter")
    add(sc, "U", "REF3030", "REF3030AIDBZR", "Texas Instruments", "3.0 V reference for the MCU ADC and the supervisors",
        "SOT-23-3", "Reference_Voltage:REF3030", "Package_TO_SOT_SMD:SOT-23",
        {1: ("IN", "+3V3A"), 2: ("OUT", "VREF_ADC"), 3: ("GND", "GND")}, verify=True,
        notes="fed from 3.3 V so that it is valid before +5V_A; 0.3 V headroom; pin-out from memory")
    C(sc, "1u", "VREF_ADC", "GND", desc="reference output")
    C(sc, "100n", "VREF_ADC", "GND")
    for net, lab in (("VIN_F", "VIN_F"), ("+5V6", "+5V6"), ("+5V_A", "+5V_A"), ("+3V3", "+3V3"), ("+3V3_EVT", "+3V3_EVT"),
                     ("VREF_ADC", "VREF_ADC"), ("GND", "GND"), ("GND", "GND"), ("GND", "GND"), ("GND", "GND")):
        TP(sc, net, lab)


# ----------------------------------------------------------------------------------------------- SiPM bias
def block_bias():
    sc = Scope("HV", 2200, "BIAS")
    V = "+3V3_HV"
    FB(sc, "+3V3", V, "220R")
    C(sc, "10u", V, "GND", desc="boost input")
    decap(sc, V, "boost AVCC")
    add(sc, "U", "TPS61391", "TPS61391RTER", "Texas Instruments",
        "85 V boost for APD/SiPM bias with current mirror (0.8 x I) and programmable output current limit",
        "WQFN-16 3x3 (RTE)", "Regulator_Switching:TPS61391RTE", "Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm",
        {1: ("NC", None), 2: ("NC", None), 3: ("MON2", "HV_MON2"), 4: ("MON1", "BIAS_IMON_R"), 5: ("APD", "HV_MIR"),
         6: ("MONIN", "HV_RAWF"), 7: ("GND", "GND"), 8: ("SW", "HV_SW"), 9: ("CAP", "HV_CAP"), 10: ("VIN", V),
         11: ("ISHORT", "HV_ISHORT"), 12: ("FB", "HV_BFB"), 13: ("EN", "HV_ON"), 14: ("AVCC", V), 15: ("AVCC", V),
         16: ("AGND", "GND"), "EP": ("PAD", "GND")}, verify=True,
        notes="pin table, VREF 1.2 V, 700 kHz, mirror gain 0.8 +/-5 % (5-200 uA), mirror drop 2.5 V, ISHORT 50 k = 2 mA "
              "from datasheet SLVSFE7; package suffix and CAP-pin capacitor connection UNVERIFIED")
    add(sc, "L", "10uH", "LPS4018-103MRB", "Coilcraft", "boost inductor (shielded)", "4.0x4.0x1.8 mm", "Device:L",
        "Inductor_SMD:L_Coilcraft_LPS4018", {1: ("1", V), 2: ("2", "HV_SW")}, verify=True, rating="Isat ~1.3 A")
    add(sc, "D", "PMEG10010ELR", "PMEG10010ELRX", "Nexperia", "boost rectifier 100 V 1 A Schottky", "SOD-123W",
        "Device:D_Schottky", "Diode_SMD:D_SOD-123F", {1: ("K", "HV_RAW"), 2: ("A", "HV_SW")}, verify=True)
    C(sc, "2u2_100", "HV_RAW", "GND", desc="boost output")
    R(sc, 1.07e6, "HV_RAW", "HV_BFBM", "0805", desc="boost feedback top (2 in series for voltage rating)")
    R(sc, 1.07e6, "HV_BFBM", "HV_BFB", "0805", desc="boost feedback top")
    R(sc, 71.5e3, "HV_BFB", "GND", "0402", desc="boost feedback bottom = HV_RAW STRAP: 71.5 k -> 37 V (onsemi J/C)",
      notes="strap table (head_afe_budget.md 5.2): 71.5 k 37 V (Vbr 24.5 V class); 53.6 k 49 V (Hamamatsu S14160); "
            "49.9 k 52.7 V (Broadcom NUV-MT); 40.2 k 65 V (Hamamatsu S13360). Fit ONLY the value for the installed SiPM.")
    R(sc, 100, "HV_RAW", "HV_RAWF", "0805", desc="boost ripple filter")
    C(sc, "1u_100", "HV_RAWF", "GND", desc="boost ripple filter")
    C(sc, "100n_100", "HV_CAP", "GND", desc="current-mirror noise capacitor")
    R(sc, 49.9e3, "HV_ISHORT", "GND", desc="output current limit 2.0 mA")
    R(sc, 10e3, "BIAS_IMON_R", "GND", "0402", "0.1%", desc="total bias current monitor: 8.0 mV/uA (0.8 x I x 10 k)")
    C(sc, "10n", "BIAS_IMON_R", "GND")
    R(sc, 1000, "BIAS_IMON_R", "BIAS_IMON", desc="ADC series")
    C(sc, "10n", "BIAS_IMON", "GND")
    R(sc, 2490, "HV_MON2", "GND", desc="high-range monitor 0.2 x I (test point)")
    TP(sc, "HV_MON2", "HV_MON2")
    # linear post-regulator: N-MOSFET follower inside a slow precision loop, HV = 25 x HV_SET
    nmos(sc, "BSS123LT1G", "HV_G", "HV_BUS", "HV_MIR", "bias pass follower (100 V)")
    R(sc, 470e3, "HV_RAWF", "HV_G", "0805", desc="gate pull-up (taken before the current mirror)")
    C(sc, "1n_100", "HV_G", "GND", desc="gate filter (0.47 ms)")
    add(sc, "D", "BZX84-C12", "BZX84-C12,215", "Nexperia", "gate-source clamp", "SOT-23", "Device:D_Zener",
        "Package_TO_SOT_SMD:SOT-23", {1: ("A", "HV_BUS"), 2: ("NC", None), 3: ("K", "HV_G")})
    add(sc, "Q", "MMBTA42", "MMBTA42LT1G", "onsemi", "level shifter (300 V NPN)", "SOT-23", "Transistor_BJT:MMBTA42",
        "Package_TO_SOT_SMD:SOT-23", {1: ("B", "HV_B"), 2: ("E", "HV_E"), 3: ("C", "HV_G")})
    R(sc, 10e3, "HV_E", "GND", desc="level shifter emitter resistor (stage gain -47)")
    R(sc, 10e3, "HV_DRV", "HV_B", desc="base series")
    add(sc, "U", "OPA2333", "OPA2333AIDR", "Texas Instruments", "zero-drift dual op-amp: A = bias error integrator, B = monitor buffer",
        "SOIC-8", "Amplifier_Operational:LM358", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("OUTA", "HV_DRV"), 2: ("-INA", "HV_SUM"), 3: ("+INA", "HV_FB"), 4: ("V-", "GND"),
         5: ("+INB", "HV_MDIV"), 6: ("-INB", "BIAS_VMON_B"), 7: ("OUTB", "BIAS_VMON_B"), 8: ("V+", "+5V_A")})
    decap(sc, "+5V_A", "bias op-amp")
    R(sc, 100e3, "HV_SET", "HV_SUM", desc="integrator input (100 k x 470 nF)")
    C(sc, "470n", "HV_DRV", "HV_SUM", desc="integrator capacitor")
    C(sc, "100n", "HV_SET", "GND", desc="set-point filter")
    R(sc, 1.2e6, "HV_BUS", "HV_FBM", "0805", "0.1%", desc="feedback divider top (25.0:1)")
    R(sc, 1.2e6, "HV_FBM", "HV_FB", "0805", "0.1%", desc="feedback divider top")
    R(sc, 100e3, "HV_FB", "GND", "0603", "0.1%", desc="feedback divider bottom")
    C(sc, "470n", "HV_FB", "GND", desc="cancels the integrator zero (96 k x 470 nF)")
    R(sc, 10e3, "HV_OFF", "HV_OFFR", desc="soft-start preset: forces the integrator high while the bias is off")
    dual_diode(sc, "BAV199,215", "HV_OFFR", "+5V_A", "HV_FB", "low-leakage preset diode + input clamp")
    C(sc, "1u_100", "HV_BUS", "GND", desc="bias bus capacitor")
    R(sc, 4.99e6, "HV_BUS", "HV_MDM", "0805", desc="independent monitor divider top (1:25.22)")
    R(sc, 4.99e6, "HV_MDM", "HV_MDIV", "0805", desc="independent monitor divider top")
    R(sc, 412e3, "HV_MDIV", "GND", "0402", "0.1%", desc="monitor divider bottom")
    C(sc, "10n", "HV_MDIV", "GND")
    R(sc, 1000, "BIAS_VMON_B", "BIAS_VMON", desc="ADC series")
    C(sc, "10n", "BIAS_VMON", "GND")
    nmos(sc, "BSS123LT1G", "HV_OFF", "GND", "HV_G", "bias shutdown: pulls the pass gate low")
    R(sc, 47e3, "HV_BUS", "HV_BLD", "1206", desc="bias bleeder (0.4 s with 9 uF)")
    nmos(sc, "BSS123LT1G", "HV_OFF", "GND", "HV_BLD", "bleeder switch")
    # permit chain: over-voltage comparator, analogue-rail supervisor, light-leak (lid) interlock -> latch
    for nm, inp, inn, desc in (("OVP", "HV_OVP_SET", "BIAS_VMON_B", "bias over-voltage: trips when V(mon) > strap"),
                               ("PG5", "HV_PG_DIV", "VREF_ADC", "+5V_A supervisor: trips below 4.60 V")):
        add(sc, "U", "TLV7021", "TLV7021DBVR", "Texas Instruments", "open-drain comparator, " + desc, "SOT-23-5",
            "Comparator:TLV7021DBV", "Package_TO_SOT_SMD:SOT-23-5",
            {1: ("OUT", "HV_INH_N"), 2: ("V-", "GND"), 3: ("IN+", inp), 4: ("IN-", inn), 5: ("V+", "+3V3")},
            verify=True, notes="DBV pin-out (OUT, V-, IN+, IN-, V+) UNVERIFIED")
        decap(sc, "+3V3", "comparator")
    R(sc, 10e3, "VREF_ADC", "HV_OVP_SET", "0402", "0.1%", desc="OVP strap divider top")
    R(sc, 7150, "HV_OVP_SET", "GND", "0402", "0.1%", desc="OVP STRAP: 7.15 k -> 31.5 V (onsemi J/C)",
      notes="OVP = 25.22 x 3.0 V x Rb/(10k + Rb): 7.15 k 31.5 V; 13.0 k 42.8 V (S14160); 16.9 k 47.5 V (NUV-MT); "
            "40.2 k 60.6 V (S13360)")
    C(sc, "100n", "HV_OVP_SET", "GND")
    R(sc, 10e3, "+5V_A", "HV_PG_DIV", desc="supervisor divider")
    R(sc, 18.7e3, "HV_PG_DIV", "GND", desc="supervisor divider")
    R(sc, 10e3, "+3V3", "HV_INH_N", desc="inhibit bus pull-up (wired-AND, active low)")
    gh(sc, 2, ["LID_IN", "GND"], "light-leak (housing/lid) interlock switch: closed = light-tight", ["LID_IN", "GND"])
    R(sc, 100e3, "+3V3", "LID_IN", desc="lid input pull-up: open or unplugged = inhibit")
    R(sc, 10e3, "LID_IN", "LID_G", desc="lid input filter")
    C(sc, "100n", "LID_G", "GND")
    nmos(sc, "BSS138LT1G", "LID_G", "GND", "HV_INH_N", "lid open -> inhibit bus low")
    sj(sc, "LID_IN", "GND", "bench bypass of the lid interlock (close deliberately; record in the build sheet)")
    add(sc, "U", "74LVC74A", "SN74LVC74APWR", "Texas Instruments", "bias permit latch: set by HV_EN rising edge, cleared by any inhibit",
        "TSSOP-14", "74xx:74HC74", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        {1: ("1CLR_N", "HV_INH_N"), 2: ("1D", "+3V3"), 3: ("1CLK", "HV_EN"), 4: ("1PRE_N", "+3V3"), 5: ("1Q", "HV_PERMIT"),
         6: ("1Q_N", None), 7: ("GND", "GND"), 8: ("2Q_N", None), 9: ("2Q", None), 10: ("2PRE_N", "+3V3"),
         11: ("2CLK", "GND"), 12: ("2D", "GND"), 13: ("2CLR_N", "+3V3"), 14: ("VCC", "+3V3")})
    decap(sc, "+3V3", "permit latch")
    add(sc, "U", "74LVC00A", "SN74LVC00APWR", "Texas Instruments", "NAND: HV_OFF = !(PERMIT & HV_EN), HV_ON = !HV_OFF",
        "TSSOP-14", "74xx:74LS00", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        {1: ("1A", "HV_PERMIT"), 2: ("1B", "HV_EN"), 3: ("1Y", "HV_OFF"), 4: ("2A", "HV_OFF"), 5: ("2B", "HV_OFF"),
         6: ("2Y", "HV_ON"), 7: ("GND", "GND"), 8: ("3Y", None), 9: ("3A", "GND"), 10: ("3B", "GND"), 11: ("4Y", None),
         12: ("4A", "GND"), 13: ("4B", "GND"), 14: ("VCC", "+3V3")})
    decap(sc, "+3V3", "NAND")
    R(sc, 10e3, "HV_EN", "GND", desc="HV_EN pull-down: bias off in reset (pinmap)")
    R(sc, 100e3, "HV_ON", "GND", desc="boost enable pull-down (rail not yet up)")
    add(sc, "RT", "10k NTC", "NCP15XH103F03RC", "Murata", "board NTC next to the bias converter", "0402",
        "Device:Thermistor_NTC", FP_R["0402"], {1: ("1", "NTC_BOARD"), 2: ("2", "GND")}, tolerance="1%, B 3380")
    R(sc, 10e3, "VREF_ADC", "NTC_BOARD", "0402", "0.1%", desc="NTC divider")
    C(sc, "100n", "NTC_BOARD", "GND")
    for net in ("HV_BUS", "HV_RAW", "HV_SET", "HV_DRV", "HV_INH_N", "HV_PERMIT", "BIAS_VMON", "BIAS_IMON"):
        TP(sc, net, net)


block_power_in()
block_regulators()
block_bias()

# ----------------------------------------------------------------------------------------------- DACs, baseline
DAC_MAP = {   # identical to firmware/head/pinmap.yaml dac_map; SPARE outputs get the board functions noted
    "U_DAC0": ["THR_LLD_F0", "THR_ULD_F0", "THR_ALPHA_F0", "THR_LLD_F1", "THR_ULD_F1", "THR_ALPHA_F1", "HV_SET",
               "LED_AMPL"],
    "U_DAC1": ["THR_LLD_F2", "THR_ULD_F2", "THR_ALPHA_F2", "THR_LLD_F3", "THR_ULD_F3", "THR_ALPHA_F3", "PULSER_AMPL",
               "DAC1_SPARE"],
    "U_DAC2": ["THR_LLD_R0", "THR_ULD_R0", "THR_LLD_R1", "THR_ULD_R1", "THR_LLD_R2", "THR_ULD_R2", "THR_LLD_R3",
               "THR_ULD_R3"],
    "U_DAC3": ["TRIM_DAC_F0", "TRIM_DAC_F1", "TRIM_DAC_F2", "TRIM_DAC_F3", "TRIM_DAC_R0", "TRIM_DAC_R1",
               "TRIM_DAC_R2", "TRIM_DAC_R3"],
}
DAC_REFS = {}


def block_dacs():
    sc = Scope("DAC", 2300, "DAC")
    for i, (name, outs) in enumerate(DAC_MAP.items()):
        ref = "DAC%d_REF" % i
        p = add(sc, "U", "DAC60508Z", "DAC60508ZRTER", "Texas Instruments",
                "%s: 8-channel 12-bit DAC, internal 2.5 V reference (DAC80508ZRTER is the 16-bit drop-in)" % name,
                "WQFN-16 3x3 (RTE)", "Analog_DAC:DAC60508xRTE", "Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm",
                {1: ("REF", ref), 2: ("OUT0", outs[0]), 3: ("OUT1", outs[1]), 4: ("OUT2", outs[2]), 5: ("OUT3", outs[3]),
                 6: ("GND", "GND"), 7: ("VDD", "+5V_A"), 8: ("OUT4", outs[4]), 9: ("OUT5", outs[5]),
                 10: ("OUT6", outs[6]), 11: ("OUT7", outs[7]), 12: ("CS", "DAC_CS%d_N" % i), 13: ("SCLK", "DAC_SCK"),
                 14: ("SDI", "DAC_MOSI"), 15: ("SDO", "DAC%d_SDO" % i), 16: ("VIO", "+3V3"), "EP": ("PAD", "GND")},
                firmware_name=name, notes="pin table from datasheet SLASEL1D; zero-scale reset variant")
        DAC_REFS[name] = p["ref"]
        C(sc, "100n", ref, "GND", desc="DAC reference capacitor (150 nF class)")
        C(sc, "1u", "+5V_A", "GND", desc="DAC VDD decoupling")
        decap(sc, "+3V3", "DAC VIO")
        R(sc, 330, "DAC%d_SDO" % i, "DAC_MISO", dnp=(i != 0), desc="SDO to MISO",
          notes="only U_DAC0 fitted until the SDO high-Z behaviour with CS high is confirmed (pinmap UNVERIFIED item)")
        R(sc, 10e3, "+3V3", "DAC_CS%d_N" % i, desc="chip-select pull-up (pinmap)")
    R(sc, 100e3, "+3V3", "DAC_MISO", desc="MISO pull-up (pinmap)")
    TP(sc, "DAC1_SPARE", "DAC1 OUT7")
    # baseline: 0.600 V derived from the reference of U_DAC1 (the threshold DAC of lanes 2/3), buffered
    add(sc, "U", "TLV9062", "TLV9062IDR", "Texas Instruments", "A = reference buffer, B = baseline (VBL) driver", "SOIC-8",
        "Amplifier_Operational:LM358", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("OUTA", "REF_BUF"), 2: ("-INA", "REF_BUF"), 3: ("+INA", "DAC1_REF"), 4: ("V-", "GND"),
         5: ("+INB", "VBL_DIV"), 6: ("-INB", "VBL_DRV"), 7: ("OUTB", "VBL_DRV"), 8: ("V+", "+5V_A")})
    decap(sc, "+5V_A", "baseline op-amp")
    R(sc, 10e3, "REF_BUF", "VBL_DIV", "0402", "0.1%", desc="baseline divider: 2.5 V x 3.16/13.16 = 0.600 V")
    R(sc, 3160, "VBL_DIV", "GND", "0402", "0.1%", desc="baseline divider")
    C(sc, "1u", "VBL_DIV", "GND", desc="baseline noise filter")
    R(sc, 10, "VBL_DRV", "VBL", desc="baseline bus driver isolation")
    TP(sc, "VBL", "VBL")
    # LED pulser amplitude x2 and per-channel bias-current monitor buffer
    add(sc, "U", "TLV9062", "TLV9062IDR", "Texas Instruments", "A = LED pulser amplitude x2, B = IMON_CH buffer", "SOIC-8",
        "Amplifier_Operational:LM358", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("OUTA", "V_LED"), 2: ("-INA", "LED_FB"), 3: ("+INA", "LED_AMPL"), 4: ("V-", "GND"),
         5: ("+INB", "IMON_MUX"), 6: ("-INB", "IMON_BUF"), 7: ("OUTB", "IMON_BUF"), 8: ("V+", "+5V_A")})
    decap(sc, "+5V_A", "misc op-amp")
    R(sc, 10e3, "V_LED", "LED_FB", desc="LED amplitude gain 2")
    R(sc, 10e3, "LED_FB", "GND", desc="LED amplitude gain 2")
    R(sc, 100e3, "LED_AMPL", "GND", desc="defines LED amplitude = 0 when the DAC output is off")
    R(sc, 100e3, "PULSER_AMPL", "GND", desc="defines pulser amplitude = 0 when the DAC output is off")


# ----------------------------------------------------------------------------------------------- MCU
# lqfp100 pin: (port pin, net).  Copy of firmware/head/pinmap.yaml (FINAL); spare pins carry the board functions
# proposed by electronics (marked *), see circuit_description.md section 9.
MCU_PINMAP = {
    1: ("PE2", "LLD_R0"), 2: ("PE3", "LLD_R1"), 3: ("PE4", "LLD_R2"), 4: ("PE5", "LLD_R3"), 5: ("PE6", "CLR_F2_N"),
    6: ("VBAT", "+3V3"), 7: ("PC13", "BUMP_ZONE_F_N"), 8: ("PC14", "BUMP_ZONE_L_N"), 9: ("PC15", "BUMP_ZONE_R_N"),
    10: ("PF9", "PULSER_A1"), 11: ("PF10", "PULSER_A2"), 12: ("PF0", "HSE_IN_24M"), 13: ("PF1", "SYNC_IN"),
    14: ("PG10", "NRST"), 15: ("PC0", "NTC_SIPM0"), 16: ("PC1", "NTC_SIPM1"), 17: ("PC2", "NTC_SIPM2"),
    18: ("PC3", "NTC_SIPM3"), 19: ("PF2", "PULSER_A0"), 20: ("PA0", "BUSY_R0"), 21: ("PA1", "BUSY_R1"),
    22: ("PA2", "BIAS_VMON"), 23: ("VSS", "GND"), 24: ("VDD", "+3V3"), 25: ("PA3", "BIAS_IMON"),
    26: ("PA4", "DAC_CS0_N"), 27: ("PA5", "DAC_SCK"), 28: ("PA6", "DAC_MISO"), 29: ("PA7", "DAC_MOSI"),
    30: ("PC4", "MON_ADC"), 31: ("PC5", "DAC_CS1_N"), 32: ("PB0", "NTC_HTR"), 33: ("PB1", "VIN_MON"),
    34: ("PB2", "DAC_CS2_N"), 35: ("VSSA", "GND"), 36: ("VREF+", "VREF_ADC"), 37: ("VDDA", "+3V3A"),
    38: ("PE7", "CLR_F3_N"), 39: ("PE8", "BUSY_R2"), 40: ("PE9", "BUSY_R3"), 41: ("PE10", "CLR_R0_N"),
    42: ("PE11", "CLR_R1_N"), 43: ("PE12", "CLR_R2_N"), 44: ("PE13", "CLR_R3_N"), 45: ("PE14", "LATCH_TEST"),
    46: ("PE15", "IMON_CH"), 47: ("PB10", "BUSY_F2"), 48: ("VSS", "GND"), 49: ("VDD", "+3V3"), 50: ("PB11", "BUSY_F3"),
    51: ("PB12", "HTR_SENSE"), 52: ("PB13", "HV_EN"), 53: ("PB14", "NTC_BOARD"), 54: ("PB15", "HTR_EN"),
    55: ("PD8", "ULD_R0"), 56: ("PD9", "ULD_R1"), 57: ("PD10", "ULD_R2"), 58: ("PD11", "ULD_R3"),
    59: ("PD12", "LLD_F0"), 60: ("PD13", "LLD_F1"), 61: ("PD14", "LLD_F2"), 62: ("PD15", "LLD_F3"),
    63: ("VSS", "GND"), 64: ("VDD", "+3V3"), 65: ("PC6", "PULSER_STROBE"), 66: ("PC7", "DAC_CS3_N"),
    67: ("PC8", "MON_MUX_A3"), 68: ("PC9", "I2C_SDA"), 69: ("PA8", "I2C_SCL"), 70: ("PA9", "RS485_TX"),
    71: ("PA10", "RS485_RX"), 72: ("PA11", "HTR_CUTOUT_OK"), 73: ("PA12", "RS485_DE"), 74: ("VSS", "GND"),
    75: ("VDD", "+3V3"), 76: ("PA13", "SWDIO"), 77: ("PA14", "SWCLK"), 78: ("PA15", "BUSY_F0"), 79: ("PC10", "DBG_TX"),
    80: ("PC11", "DBG_RX"), 81: ("PC12", "LED_STROBE"), 82: ("PD0", "ULD_F0"), 83: ("PD1", "ULD_F1"),
    84: ("PD2", "ULD_F2"), 85: ("PD3", "ULD_F3"), 86: ("PD4", "ALPHA_F0"), 87: ("PD5", "ALPHA_F1"),
    88: ("PD6", "ALPHA_F2"), 89: ("PD7", "ALPHA_F3"), 90: ("PB3", "BUSY_F1"), 91: ("PB4", "LED_STATUS_N"),
    92: ("PB5", "MON_MUX_A0"), 93: ("PB6", "LED_FAULT_N"), 94: ("PB7", "MON_MUX_A1"), 95: ("PB8", "BOOT0"),
    96: ("PB9", "MON_MUX_A2"), 97: ("PE0", "CLR_F0_N"), 98: ("PE1", "CLR_F1_N"), 99: ("VSS", "GND"),
    100: ("VDD", "+3V3"),
}
# firmware "SPARE_*" pins and the board function given to each (firmware may leave them as inputs with pull-down)
SPARE_PIN_USE = {"PE15": "IMON_CH", "PC12": "LED_STROBE", "PF1": "SYNC_IN", "PF2": "PULSER_A0", "PF9": "PULSER_A1",
                 "PF10": "PULSER_A2"}


def block_mcu():
    sc = Scope("MCU", 2400, "MCU")
    add(sc, "U", "STM32G474VET6", "STM32G474VET6", "STMicroelectronics", "head MCU, LQFP100, 512 KB flash", "LQFP-100 14x14",
        "MCU_ST_STM32G4:STM32G474VETx", "Package_QFP:LQFP-100_14x14mm_P0.5mm",
        {k: (v[0], v[1]) for k, v in MCU_PINMAP.items()}, verify=True,
        notes="pin numbers and functions from firmware/head/pinmap.yaml (tool-checked against ST's open pin database); "
              "st.com datasheet not reachable from this machine")
    for _ in range(5):
        decap(sc, "+3V3", "MCU VDD")
    C(sc, "4u7", "+3V3", "GND", desc="MCU bulk")
    decap(sc, "+3V3A", "MCU VDDA")
    C(sc, "100n", "NRST", "GND", desc="reset capacitor (pinmap)")
    R(sc, 10e3, "BOOT0", "GND", desc="BOOT0 pull-down (pinmap)")
    TP(sc, "BOOT0", "BOOT0")
    add(sc, "Y", "24.000 MHz TCXO", "ECS-TXO-2520MV-240-AN-TR", "ECS Inc.", "24 MHz TCXO, CMOS output, +/-2.5 ppm class, -40..85 C",
        "2.5x2.0 mm 4-pad", "Oscillator:TCXO-14", "Oscillator:Oscillator_SMD_ECS_2520MV-xxx-xx-4Pin_2.5x2.0mm",
        {1: ("EN", "TCXO_VDD"), 2: ("GND", "GND"), 3: ("OUT", "TCXO_OUT"), 4: ("VDD", "TCXO_VDD")}, verify=True,
        notes="exact ordering code, stability grade and pad 1 function UNVERIFIED; any 24 MHz CMOS TCXO <= 2.5 ppm, "
              "-40 C, 2.5x2.0 mm fits")
    FB(sc, "+3V3", "TCXO_VDD", "600R")
    decap(sc, "TCXO_VDD", "TCXO")
    R(sc, 33, "TCXO_OUT", "HSE_IN_24M", desc="clock source series")
    add(sc, "J", "TC2030-NL", "TC2030-IDC-NL (cable)", "Tag-Connect", "SWD footprint (no component fitted)", "TC2030 no-legs",
        "Connector:Conn_ARM_SWD_TagConnect_TC2030-NL", "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",
        {1: ("VCC", "+3V3"), 2: ("SWDIO", "SWDIO"), 3: ("NRST", "NRST"), 4: ("SWCLK", "SWCLK"), 5: ("GND", "GND"),
         6: ("SWO", None)}, notes="PCB feature; no SWO (PB3 is BUSY_F1)")
    gh(sc, 3, ["DBG_TX", "DBG_RX", "GND"], "debug UART4 115200 8N1", ["TX", "RX", "GND"])
    R(sc, 100e3, "+3V3", "DBG_RX", desc="debug RX pull-up (pinmap)")
    for col, mpn, net in (("green", "LTST-C191KGKT", "LED_STATUS_N"), ("red", "LTST-C191KRKT", "LED_FAULT_N")):
        a = "LEDA_" + col.upper()
        R(sc, 1000, "+3V3", a, desc="%s LED resistor" % col)
        add(sc, "D", col, mpn, "Lite-On", "%s status LED, active low" % col, "0603", "Device:LED", "LED_SMD:LED_0603_1608Metric",
            {1: ("K", net), 2: ("A", a)})
    R(sc, 2200, "+3V3", "I2C_SCL", desc="I2C pull-up")
    R(sc, 2200, "+3V3", "I2C_SDA", desc="I2C pull-up")
    for i, addr in enumerate(("GND", "+3V3")):
        add(sc, "U", "TMP117", "TMP117AIDRVR", "Texas Instruments",
            "board temperature reference, I2C 0x%02X (place at the rear edge between lanes %s)" % (0x48 + i, "0/1" if i == 0 else "2/3"),
            "WSON-6 2x2 (DRV)", "Sensor_Temperature:TMP117xDRV", "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
            {1: ("SCL", "I2C_SCL"), 2: ("GND", "GND"), 3: ("ALERT", None), 4: ("ADD0", addr), 5: ("V+", "+3V3"),
             6: ("SDA", "I2C_SDA"), "EP": ("PAD", "GND")}, verify=True, notes="pin-out from memory")
        decap(sc, "+3V3", "TMP117")
    add(sc, "U", "24AA025E64", "24AA025E64T-I/SN", "Microchip", "EEPROM with EUI-64 (head identity), I2C 0x50", "SOIC-8",
        "Memory_EEPROM:24LC02", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("A0", "GND"), 2: ("A1", "GND"), 3: ("A2", "GND"), 4: ("VSS", "GND"), 5: ("SDA", "I2C_SDA"), 6: ("SCL", "I2C_SCL"),
         7: ("WP", "GND"), 8: ("VCC", "+3V3")}, verify=True, notes="pins 3 and 7 may be NC on this device; tying to GND is harmless")
    decap(sc, "+3V3", "EEPROM")
    add(sc, "U", "TCA9534", "TCA9534PWR", "Texas Instruments",
        "I2C 0x20 expander: MON_EXT (out), bias permit / inhibit / lid / eFuse fault read-back, board revision",
        "TSSOP-16", "Interface_Expansion:TCA9534PWR", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        {1: ("A0", "GND"), 2: ("A1", "GND"), 3: ("A2", "GND"), 4: ("P0", "MON_EXT"), 5: ("P1", "HV_PERMIT"),
         6: ("P2", "HV_INH_N"), 7: ("P3", "LID_G"), 8: ("GND", "GND"), 9: ("P4", "EF_FLT_N"), 10: ("P5", "HWREV0"),
         11: ("P6", "HWREV1"), 12: ("P7", "EXP_P7"), 13: ("INT", None), 14: ("SCL", "I2C_SCL"), 15: ("SDA", "I2C_SDA"),
         16: ("VCC", "+3V3")}, verify=True,
        notes="optional for firmware: with all pins left as inputs the board works (MON_EXT pulled low). Pin-out from memory.")
    decap(sc, "+3V3", "expander")
    R(sc, 100e3, "MON_EXT", "GND", desc="monitor page select default 0")
    R(sc, 10e3, "HWREV0", "GND", desc="board revision strap bit 0 = 0 (rev A)")
    R(sc, 10e3, "HWREV1", "GND", desc="board revision strap bit 1 = 0")
    TP(sc, "EXP_P7", "EXP P7")
    R(sc, 10e3, "PULSER_STROBE", "GND", desc="pull-down (pinmap)")
    R(sc, 10e3, "LATCH_TEST", "GND", desc="pull-down (pinmap)")
    R(sc, 100e3, "LED_STROBE", "GND", desc="pull-down, firmware spare PC12")
    R(sc, 100e3, "SYNC_IN", "GND", desc="pull-down, firmware spare PF1 (hardware time pulse, DNP path)")
    TP(sc, "SYNC_IN", "SYNC_IN")
    for i in range(3):
        R(sc, 100e3, "PULSER_A%d" % i, "GND", desc="pulser channel select pull-down (default channel F0)")


# ----------------------------------------------------------------------------------------------- RS-485
def block_comm():
    sc = Scope("COMM", 2500, "COMM_ISOLATED")
    gh(sc, 8, ["RS485_DP", "RS485_DN", "BUS_5V", "BUS_GND", "SYNC_P", "SYNC_N", "J2_PRES", None],
       "J2 pigtail landing (board pin n = contract J2 pin n)",
       ["RS485_DP", "RS485_DN", "BUS_5V", "BUS_GND", "SYNC_P", "SYNC_N", "J2_PRES", "NC_RESERVED"])
    PARTS[-1]["pins"]["MP"] = ("MP", "BUS_GND")
    add(sc, "U", "ISO1430B", "ISO1430BDWR", "Texas Instruments", "isolated half-duplex RS-485, 12 Mbps, no integrated DC-DC",
        "SOIC-16W", "Interface_UART:ISO1430", "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
        {1: ("VCC1", "+3V3"), 2: ("GND1", "GND"), 3: ("R", "RS485_RX"), 4: ("RE_N", "RS485_DE"), 5: ("DE", "RS485_DE"),
         6: ("D", "RS485_TX"), 7: ("NC", None), 8: ("GND1", "GND"), 9: ("GND2", "BUS_GND"), 10: ("NC", None),
         11: ("NC", None), 12: ("A", "RS485_DP"), 13: ("B", "RS485_DN"), 14: ("NC", None), 15: ("GND2", "BUS_GND"),
         16: ("VCC2", "BUS_5VF")},
        notes="half-duplex pin diagram from datasheet SLLSF22I. A = non-inverting = RS485_DP; confirm polarity on the "
              "bench against the chassis transceiver (ICD requirement). RE_N tied to DE (pinmap).")
    decap(sc, "+3V3", "isolator logic side")
    FB(sc, "BUS_5V", "BUS_5VF", "220R")
    add(sc, "C", "10uF", "GRM21BR61C106KE15L", "Murata", "bus-side bulk", "0805", "Device:C", FP_C["0805"],
        {1: ("1", "BUS_5VF"), 2: ("2", "BUS_GND")}, tolerance="10%", rating="X5R 16 V", mpn_rule=True)
    add(sc, "C", "100nF", "GRM155R71C104KA88D", "Murata", "bus-side decoupling", "0402", "Device:C", FP_C["0402"],
        {1: ("1", "BUS_5VF"), 2: ("2", "BUS_GND")}, tolerance="10%", rating="X7R 16 V", mpn_rule=True)
    add(sc, "D", "SM712", "SM712.TCT", "Semtech", "RS-485 line TVS (-7/+12 V)", "SOT-23", "Device:D_TVS_Dual_AAC",
        "Package_TO_SOT_SMD:SOT-23", {1: ("1", "RS485_DP"), 2: ("2", "RS485_DN"), 3: ("3", "BUS_GND")})
    R(sc, 120, "RS485_DP", "RS485_DN", "0805", desc="bus termination 120 R (contract: at each end)")
    R(sc, 0, "J2_PRES", "BUS_GND", "0402", dnp=True,
      desc="J2 presence link on the board (contract places it in the plug; fit only if the harness omits it)")
    add(sc, "D", "PESD5V0S1BA", "PESD5V0S1BA,115", "Nexperia", "ESD protection BUS_5V", "SOD-323", "Device:D_TVS",
        "Diode_SMD:D_SOD-323", {1: ("1", "BUS_5V"), 2: ("2", "BUS_GND")}, verify=True)
    R(sc, 10e3, "+3V3", "RS485_RX", desc="RX pull-up: disabled receiver reads mark (pinmap)")
    R(sc, 10e3, "RS485_DE", "GND", desc="DE pull-down (pinmap)")
    TP(sc, "SHLD_J2", "J2 SHIELD")
    R(sc, 1e6, "SHLD_J2", "FRAME", "0603", desc="J2 shield to frame")
    C(sc, "10n_100", "SHLD_J2", "FRAME", desc="J2 shield to frame")
    # reserved hardware time pulse (contract: footprints DNP in rev A)
    add(sc, "U", "THVD1420", "THVD1420DR", "Texas Instruments", "RS-422 receiver for the reserved sync pair (DNP)", "SOIC-8",
        "Interface_UART:THVD1420D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("R", "SYNC_RX_B"), 2: ("RE_N", "BUS_GND"), 3: ("DE", "BUS_GND"), 4: ("D", "BUS_GND"), 5: ("GND", "BUS_GND"),
         6: ("A", "SYNC_P"), 7: ("B", "SYNC_N"), 8: ("VCC", "BUS_5VF")}, dnp=True, verify=True)
    add(sc, "U", "ISO7710", "ISO7710DR", "Texas Instruments", "single-channel digital isolator for the sync pulse (DNP)", "SOIC-8",
        "Isolator:ISO7710D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        {1: ("VCC1", "BUS_5VF"), 2: ("INA", "SYNC_RX_B"), 3: ("NC", None), 4: ("GND1", "BUS_GND"), 5: ("GND2", "GND"),
         6: ("OUT", "SYNC_IN"), 7: ("NC", None), 8: ("VCC2", "+3V3")}, dnp=True, verify=True,
        notes="narrow-body SOIC gives basic isolation only; pin-out from memory")
    R(sc, 120, "SYNC_P", "SYNC_N", "0805", dnp=True, desc="sync pair termination (DNP)")


# ----------------------------------------------------------------------------------------------- heater
def block_heater():
    sc = Scope("HTR", 2600, "HEATER")
    microfit(sc, 6, ["HTR_SW", "HEAD_HTR_N", "HTR_CUT", "NTC_HTR", "GND", None],
             ["HTR_SW", "HTR_RET", "CUTOUT_SENSE", "NTC", "NTC_RTN", "SPARE"],
             "heater film tail + spreader NTC. Heater assembly: HTR_SW -> element 4.8 R -> CUTOUT_SENSE -> "
             "bimetal cut-out (low side) -> HTR_RET")
    add(sc, "D", "SMBJ16A", "SMBJ16A", "Littelfuse", "heater feed TVS", "SMB (DO-214AA)", "Device:D_TVS", "Diode_SMD:D_SMB",
        {1: ("K", "HEAD_HTR_P"), 2: ("A", "HEAD_HTR_N")})
    C(sc, "10u_25", "HEAD_HTR_P", "HEAD_HTR_N", desc="heater feed local bypass (returns to the HEATER return)")
    add(sc, "R", "10mR", "CRA2512-FZ-R010ELF", "Bourns", "heater current shunt", "2512", "Device:R", FP_R["2512"],
        {1: ("1", "HEAD_HTR_P"), 2: ("2", "HTR_PS")}, tolerance="1%", rating="3 W", verify=True, ohms=0.010)
    add(sc, "U", "INA180A2", "INA180A2IDBVR", "Texas Instruments", "heater current sense, gain 50: 0.5 V/A", "SOT-23-5",
        "Amplifier_Current:INA180A2", "Package_TO_SOT_SMD:SOT-23-5",
        {1: ("OUT", "HTR_SENSE_R"), 2: ("GND", "GND"), 3: ("IN+", "HEAD_HTR_P"), 4: ("IN-", "HTR_PS"), 5: ("VS", "+3V3")},
        verify=True, notes="common-mode range -0.2..26 V; 'A' pin-out from memory")
    decap(sc, "+3V3", "INA180")
    R(sc, 1000, "HTR_SENSE_R", "HTR_SENSE", desc="ADC series")
    C(sc, "100n", "HTR_SENSE", "GND")
    add(sc, "Q", "SUD50P04-08", "SUD50P04-08-GE3", "Vishay", "heater high-side switch, P-channel 40 V, linear slew-limited edges",
        "TO-252 (DPAK)", "Device:Q_PMOS_GDS", "Package_TO_SOT_SMD:TO-252-2",
        {1: ("G", "HTR_GATE"), 2: ("D", "HTR_SW"), 3: ("S", "HTR_PS")}, verify=True,
        notes="SOA for a 3 ms, 15 V x 3 A linear transition must be checked against the datasheet curve")
    R(sc, 68e3, "HTR_PS", "HTR_GATE", desc="gate-source resistor (turn-off slew)")
    add(sc, "D", "BZX84-C12", "BZX84-C12,215", "Nexperia", "gate clamp", "SOT-23", "Device:D_Zener", "Package_TO_SOT_SMD:SOT-23",
        {1: ("A", "HTR_GATE"), 2: ("NC", None), 3: ("K", "HTR_PS")})
    C(sc, "10n", "HTR_GATE", "HTR_SW", desc="Miller capacitor: sets dV/dt (0.6 ms on, ~3 ms off)")
    R(sc, 47e3, "HTR_GATE", "HTR_GD", desc="gate drive resistor (turn-on slew)")
    nmos(sc, "BSS138LT1G", "HTR_ENG", "GND", "HTR_GD", "heater gate driver")
    R(sc, 1000, "HTR_EN", "HTR_ENG", desc="gate series")
    R(sc, 10e3, "HTR_EN", "GND", desc="HTR_EN pull-down: heater off in reset (pinmap)")
    R(sc, 47e3, "HEAD_HTR_P", "HTR_SW", "0603", desc="0.26 mA continuity current through element and cut-out when off")
    # cut-out status: high = HTR supply present AND cut-out closed
    R(sc, 100e3, "HTR_CUT", "HTR_CQB", desc="cut-out sense (high-impedance link between heater and logic domains)")
    R(sc, 47e3, "HTR_CQB", "GND", desc="cut-out sense")
    add(sc, "Q", "MMBT3904", "MMBT3904LT1G", "onsemi", "cut-out open detector", "SOT-23", "Transistor_BJT:MMBT3904",
        "Package_TO_SOT_SMD:SOT-23", {1: ("B", "HTR_CQB"), 2: ("E", "GND"), 3: ("C", "HTR_CX")})
    R(sc, 100e3, "HEAD_HTR_P", "HTR_CX", desc="status pull-up from the heater feed")
    R(sc, 33e3, "HTR_CX", "HTR_CUTOUT_OK", desc="status series")
    R(sc, 100e3, "HTR_CUTOUT_OK", "GND", desc="status pull-down (pinmap)")
    dual_diode(sc, "BAT54S,215", "GND", "+3V3", "HTR_CUTOUT_OK", "status clamp")
    C(sc, "10n", "HTR_CUTOUT_OK", "GND")
    R(sc, 10e3, "VREF_ADC", "NTC_HTR", "0402", "0.1%", desc="heater NTC divider")
    C(sc, "100n", "NTC_HTR", "GND")
    add(sc, "D", "PESD5V0S1BA", "PESD5V0S1BA,115", "Nexperia", "ESD protection heater NTC", "SOD-323", "Device:D_TVS",
        "Diode_SMD:D_SOD-323", {1: ("1", "NTC_HTR"), 2: ("2", "GND")}, verify=True)
    TP(sc, "HTR_SW", "HTR_SW")
    TP(sc, "HTR_GATE", "HTR_GATE")


# ----------------------------------------------------------------------------------------------- monitor, selects
def block_monitor():
    sc = Scope("MON", 2700, "MONITOR")
    add(sc, "U", "74HC238", "CD74HC238PWR", "Texas Instruments", "3-to-8 decoder, active-high: monitor lane enable", "TSSOP-16",
        "74xx:74HC238", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        {1: ("A0", "MON_MUX_A0"), 2: ("A1", "MON_MUX_A1"), 3: ("A2", "GND"), 4: ("E1_N", "GND"), 5: ("E2_N", "GND"),
         6: ("E3", "+3V3"), 7: ("Y7", None), 8: ("GND", "GND"), 9: ("Y6", None), 10: ("Y5", None), 11: ("Y4", None),
         12: ("Y3", "MON_EN_3"), 13: ("Y2", "MON_EN_2"), 14: ("Y1", "MON_EN_1"), 15: ("Y0", "MON_EN_0"), 16: ("VCC", "+3V3")})
    decap(sc, "+3V3", "decoder")
    chs = CHANNELS
    add(sc, "U", "74LVC138A", "SN74LVC138APWR", "Texas Instruments", "3-to-8 decoder, active-low: test-pulser channel select",
        "TSSOP-16", "74xx:74LS138", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        {1: ("A0", "PULSER_A0"), 2: ("A1", "PULSER_A1"), 3: ("A2", "PULSER_A2"), 4: ("E1_N", "GND"), 5: ("E2_N", "GND"),
         6: ("E3", "+3V3_EVT"), 7: ("Y7_N", "TP_INH_%s_N" % chs[7]), 8: ("GND", "GND"), 9: ("Y6_N", "TP_INH_%s_N" % chs[6]),
         10: ("Y5_N", "TP_INH_%s_N" % chs[5]), 11: ("Y4_N", "TP_INH_%s_N" % chs[4]), 12: ("Y3_N", "TP_INH_%s_N" % chs[3]),
         13: ("Y2_N", "TP_INH_%s_N" % chs[2]), 14: ("Y1_N", "TP_INH_%s_N" % chs[1]), 15: ("Y0_N", "TP_INH_%s_N" % chs[0]),
         16: ("VCC", "+3V3_EVT")}, notes="pulsed channel = PULSER_A[2:0] (0..7 = F0..F3, R0..R3), independent of the monitor select")
    decap(sc, "+3V3_EVT", "decoder")
    add(sc, "U", "TMUX1108", "TMUX1108PWR", "Texas Instruments", "8:1 mux: per-channel anode current monitor", "TSSOP-16",
        "Analog_Switch:TMUX1108PW", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        {1: ("A0", "MON_MUX_A0"), 2: ("EN", "+3V3"), 3: ("VSS", "GND"), 4: ("S1", "IMON_F0"), 5: ("S2", "IMON_F1"),
         6: ("S3", "IMON_F2"), 7: ("S4", "IMON_F3"), 8: ("D", "IMON_MUX"), 9: ("S8", "IMON_R3"), 10: ("S7", "IMON_R2"),
         11: ("S6", "IMON_R1"), 12: ("S5", "IMON_R0"), 13: ("VDD", "+5V_A"), 14: ("GND", "GND"), 15: ("A2", "MON_MUX_A2"),
         16: ("A1", "MON_MUX_A1")}, notes="selected channel = MON_MUX_A[2:0]")
    decap(sc, "+5V_A", "IMON mux")
    C(sc, "100n", "IMON_MUX", "GND", desc="IMON filter (10 k x 100 nF = 1 ms)")
    R(sc, 1000, "IMON_BUF", "IMON_CH", desc="ADC series (PE15 = ADC4_IN2)")
    C(sc, "10n", "IMON_CH", "GND")
    R(sc, 100e3, "MON_BUS", "GND", desc="monitor bus bleed")
    opamp_sot23_6(sc, "OPA836IDBVR", "MON_DRV", "MON_BUS", "MON_DRV", "+5V_A", "monitor buffer, unity gain, drives 50 ohm")
    decap(sc, "+5V_A", "monitor buffer")
    R(sc, 49.9, "MON_DRV", "MON_OUT", desc="50 ohm back termination (scope sees half amplitude into 50 ohm)")
    ufl(sc, "MON_OUT", "buffered analogue monitor output, 50 ohm")
    R(sc, 1000, "MON_DRV", "MON_ADC", desc="ADC anti-alias (1 k x 150 pF ~ 1 MHz)")
    C(sc, "100p", "MON_ADC", "GND")
    C(sc, "100p", "MON_ADC", "GND", dnp=True, desc="second anti-alias capacitor (fit for 0.8 MHz)")
    dual_diode(sc, "BAT54S,215", "GND", "+3V3A", "MON_ADC", "ADC input clamp")
    TP(sc, "MON_BUS", "MON_BUS")
    TP(sc, "PULSER_AMPL", "PULSER_AMPL")
    TP(sc, "PULSER_STROBE", "PULSER_STROBE")
    TP(sc, "LATCH_TEST", "LATCH_TEST")


# ----------------------------------------------------------------------------------------------- mechanical
BOARD = dict(
    name="RR-HEAD-ACQ", rev="A", outline_mm=(326.0, 96.0), thickness_mm=1.6, layers=4,
    frame="origin rear-left corner, +u toward robot right, +v forward (mechanical/common/board_envelopes.yaml)",
    max_height_top_mm=6.0, max_height_bottom_mm=2.0,
    mounting_holes_uv_mm={"H1": (75.5, 4.5), "H2": (163.0, 4.5), "H3": (250.5, 4.5), "H4": (75.5, 91.5),
                          "H5": (163.0, 91.5), "H6": (250.5, 91.5), "H7": (5.0, 48.0), "H8": (321.0, 48.0)},
    lane_centre_u_mm={"S0": 31.75, "S1": 119.25, "S2": 206.75, "S3": 294.25},
    lane_shield=dict(outline_du_mm=(-18.0, 18.0), outline_v_mm=(5.5, 37.5), height_mm=5.0, wall_mm=0.2,
                     note="one can per lane centred on the lane centre u; U.FL and auxiliary connectors stay outside "
                          "(v < 5.5); +/-18 mm keeps clear of J1_LANDING (u 50..100) and J2_LANDING (u 226..276) for all lanes"),
    zones=dict(AFE_STRIP="v 0..30", J1_LANDING="u 50..100, v 0..18", J2_LANDING="u 226..276, v 0..18",
               RAIL_SWITCH_LANDING="u 150..176, v 84..96", DIGITAL_POWER="v 30..84", SERVICE="u 100..226, v 84..96"),
)


def block_mech():
    sc = Scope("MECH", 2800, "MECH")
    for h in sorted(BOARD["mounting_holes_uv_mm"]):
        add(sc, "H", h, "M2.5 plated hole", "(PCB feature)", "mounting hole %s at (u, v) = %s mm" % (h, BOARD["mounting_holes_uv_mm"][h]),
            "2.7 mm hole, 6 mm pad", "Mechanical:MountingHole_Pad", "MountingHole:MountingHole_2.7mm_M2.5_Pad_Via",
            {1: ("PAD", "FRAME")}, uv_mm=BOARD["mounting_holes_uv_mm"][h])
    R(sc, 0, "FRAME", "GND", "0603", desc="single-point DC bond of the spreader/frame to GND (next to H1)",
      notes="remove if the head frame turns out to be in metallic contact with the chassis (CCR-HE-03)")
    R(sc, 1e6, "FRAME", "GND", "0603", desc="frame bleed")
    for _ in range(4):
        C(sc, "10n_100", "FRAME", "GND", desc="HF frame bond (one near each of H2, H3, H5, H6)")
    for i in range(3):
        add(sc, "FID", "fiducial", "fiducial", "(PCB feature)", "global fiducial", "1 mm copper, 2 mm mask",
            "Mechanical:Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", {}, npins=0)


block_dacs()
block_mcu()
block_comm()
block_heater()
block_monitor()
block_mech()


# =============================================================================================== nets and classes
import re as _re


def build_nets():
    nets = {}
    for p in PARTS:
        for num, v in p["pins"].items():
            if v is None:
                continue
            nets.setdefault(v[1], []).append((p["ref"], num, v[0]))
    return nets


NET_CLASSES = {
    "HV": dict(
        desc="SiPM bias, 20-62.5 V DC, <= 2 mA (current limited)", width_mm=0.25, clearance_mm=1.5,
        rules="Outer layers only where possible; 1.5 mm to any other copper and to board edges, mounting pads and "
              "connector shells; GND guard trace/pour gap ring around the per-channel filter nodes; no solder-mask "
              "slivers between HV and GND pads; conformal coat. Parts on these nets rated >= 100 V."),
    "ANALOG_SENSITIVE": dict(
        desc="SiPM anode, preamp inputs/feedback, fast-CR and slow-integrator nodes (uV-level, 10 ohm source)",
        width_mm=0.2, clearance_mm=0.3,
        rules="Shortest possible (< 10 mm from the U.FL to R_IN and the preamp); layer 1 only, unbroken GND on layer 2 "
              "underneath; no other signal may cross on any layer; ground-stitch fence toward neighbouring channel and "
              "toward the digital zone; keep >= 5 mm from comparator outputs, latch clocks and the pulser strobe."),
    "ANALOG": dict(
        desc="shaper outputs, comparator inputs, thresholds, trim, baseline, monitor and housekeeping analogue",
        width_mm=0.2, clearance_mm=0.2,
        rules="Thresholds/trim/baseline are DC: route on layer 4 or 1 over GND, away from clocks; every RC filter at the "
              "destination pin. MON_BUS and IMON_x run along v = 30..34 in a GND-flanked corridor."),
    "POWER": dict(
        desc="supply rails", width_mm=0.5, clearance_mm=0.2,
        rules="VIN/5V6: >= 0.6 mm (0.5 A). +5V_A, +3V3, +3V3_EVT: layer-3 plane islands. Heater path HEAD_HTR_P/HTR_PS/"
              "HTR_SW/HEAD_HTR_N: >= 2.5 mm on 1 oz outer copper (3.2 A), feed and return routed as a tight pair, "
              "confined to the J1 landing zone, never under or over the AFE strip."),
    "DIFF": dict(
        desc="RS-485 pair and reserved sync pair on the isolated side", width_mm=0.25, clearance_mm=0.25,
        rules="120 ohm differential, length matched within 2 mm, entirely inside the BUS_GND island."),
    "ISOLATED": dict(
        desc="bus-side supply and reference", width_mm=0.4, clearance_mm=0.25,
        rules="BUS_GND island under J2 landing only; >= 4 mm copper-free barrier (all layers) between island and the rest, "
              "crossed only by the isolator packages."),
    "EVENT": dict(
        desc="comparator outputs, latch clocks, BUSY/ULD/ALPHA/LLD lines to the MCU, CLR, pulser strobe",
        width_mm=0.15, clearance_mm=0.2,
        rules="Comparator-to-OR-to-latch nets stay inside the lane (< 25 mm). Series resistor at the source for every "
              "line that leaves the lane. Route to the MCU on layer 4 in v > 34; BUSY lines of the 8 chains matched "
              "within 20 mm (0.1 ns, irrelevant against the 6.9 ns timer tick). Keep 5 mm from ANALOG_SENSITIVE."),
    "DIGITAL": dict(desc="SPI, I2C, UART, GPIO, clock", width_mm=0.15, clearance_mm=0.15,
                    rules="SPI to the DACs is quiet during acquisition; clock trace < 20 mm with series resistor at the TCXO."),
}

_SENS = ("_A", "_PINA", "_PIN", "_PFB", "_PG", "_FS", "_FFB", "_TRIM", "_TPI", "_SI", "_SS", "_SFB")
_EVT = ("_CLLD", "_CULD", "_CALPHA", "_KLLD", "_KULD", "_KALPHA")


def net_class(net):
    if net.startswith("HV_") and net not in ("HV_EN", "HV_ON", "HV_OFF", "HV_OFFR", "HV_PERMIT", "HV_INH_N", "HV_SET",
                                             "HV_SUM", "HV_DRV", "HV_FB", "HV_B", "HV_E", "HV_MDIV", "HV_OVP_SET",
                                             "HV_PG_DIV", "HV_BFB", "HV_ISHORT", "HV_MON2"):
        return "HV"
    if _re.match(r"^[FR]\d_", net):
        suf = net[2:]
        if suf in ("_HV1", "_HVF"):
            return "HV"
        if suf in _SENS:
            return "ANALOG_SENSITIVE"
        if suf in _EVT:
            return "EVENT"
        return "ANALOG"
    if net in ("RS485_DP", "RS485_DN", "SYNC_P", "SYNC_N"):
        return "DIFF"
    if net.startswith("BUS_") or net in ("J2_PRES", "SYNC_RX_B"):
        return "ISOLATED"
    if net in ("GND", "FRAME", "EF_RTN") or net.startswith(("+", "VIN_", "HEAD_PWR", "HEAD_HTR", "HTR_PS", "HTR_SW",
                                                              "BK_SW", "TCXO_VDD")):
        return "POWER"
    if net.startswith(("BUSY_", "ULD_", "ALPHA_", "LLD_", "CLR_", "TP_INH_")) or net in ("LATCH_TEST", "PULSER_STROBE",
                                                                                         "LED_STROBE") \
            or _re.match(r"^L\d_Q", net):
        return "EVENT"
    if net.startswith(("THR_", "TRIM_DAC_", "IMON_", "NTC_", "BIAS_", "MON_BUS", "MON_DRV", "MON_OUT", "MON_ADC", "VBL",
                       "VREF", "REF_BUF", "DAC", "PULSER_AMPL", "LED_AMPL", "V_LED", "HV_", "VIN_MON", "HTR_SENSE")) \
            and not net.startswith(("DAC_", "MON_MUX", "MON_EN", "MON_EXT")) and "_SDO" not in net:
        return "ANALOG"
    return "DIGITAL"


_RAW_NETS = build_nets()
NETS = {n: dict(net_class=net_class(n), pins=sorted(v)) for n, v in sorted(_RAW_NETS.items())}

CONNECTORS = {p["ref"]: dict(description=p["description"], mpn=p["mpn"], manufacturer=p["manufacturer"],
                             pins={k: (v[0], v[1]) if v else ("NC", None) for k, v in p["pins"].items()})
              for p in PARTS if p["ref"].startswith("J")}

# nets that intentionally have fewer than two FITTED connections (DNP parts and bare test pads do not count)
SINGLE_PIN_WHITELIST = {
    "EF_SHDN": "eFuse SHDN left open (internal pull-up, UNVERIFIED) with a test pad",
    "EF_MODE": "eFuse MODE open = default fault response; DNP strap + test pad",
    "DAC1_SPARE": "spare DAC output on a test pad",
    "EXP_P7": "spare expander bit on a test pad",
    "DAC1_SDO": "SDO series resistor DNP until the DAC SDO behaviour is confirmed",
    "DAC2_SDO": "as DAC1_SDO", "DAC3_SDO": "as DAC1_SDO",
    "SYNC_P": "reserved hardware sync pair: receiver DNP in rev A (contract)", "SYNC_N": "as SYNC_P",
    "SYNC_RX_B": "DNP sync receiver only", "J2_PRES": "presence link is made in the J2 plug (contract); board link DNP",
}
for _ch in CHANNELS:
    SINGLE_PIN_WHITELIST[_ch + "_PRE_TP"] = "probe resistor to a bare test pad"

SUPPLY_PIN_NAMES = {"VCC", "VDD", "V+", "VS+", "VS", "VIN", "VDDA", "VREF+", "VBAT", "VIO", "AVCC", "VCC1", "VCC2", "IN"}
GROUND_PIN_NAMES = {"GND", "VSS", "V-", "VS-", "VSSA", "GND1", "GND2", "AGND", "RTN", "PAD"}
PKG_PINS = {"SOT-23": 3, "SOT-23-3": 3, "SOT-23-5": 5, "SOT-23-6": 6, "SOT-23-8 (DCN)": 8, "SC-70-5": 5, "SOIC-8": 8,
            "SOIC-16W": 16, "TSSOP-14": 14, "TSSOP-16": 16, "VSSOP-8 (DCU)": 8, "LQFP-100 14x14": 100,
            "HTSSOP-16 PowerPAD": 16, "WQFN-16 3x3 (RTE)": 16, "WSON-6 2x2 (DRV)": 6, "TO-252 (DPAK)": 3}
# placed area per package incl. courtyard, mm^2 (estimate for the fit check)
PKG_AREA = {"0402": 2.0, "0603": 4.0, "0805": 6.5, "1206": 10.0, "1210": 14.5, "2512": 28.0, "SOT-23": 10.0,
            "SOT-23-3": 10.0, "SOT-23-5": 11.0, "SOT-23-6": 11.0, "SOT-23-8 (DCN)": 11.0, "SC-70-5": 7.0, "SOD-323": 5.0,
            "SOD-123W": 8.5, "SMB (DO-214AA)": 26.0, "SOIC-8": 36.0, "SOIC-16W": 121.0, "TSSOP-14": 38.0, "TSSOP-16": 38.0,
            "VSSOP-8 (DCU)": 10.0, "LQFP-100 14x14": 272.0, "HTSSOP-16 PowerPAD": 38.0, "WQFN-16 3x3 (RTE)": 16.0,
            "WSON-6 2x2 (DRV)": 9.0, "TO-252 (DPAK)": 75.0, "U.FL receptacle": 16.0, "4.0x4.0x4.1 mm": 22.0,
            "4.0x4.0x1.8 mm": 20.0, "4.5x2.0 mm": 14.0, "2.5x2.0 mm 4-pad": 9.0, "TC2030 no-legs": 24.0,
            "2.7 mm hole, 6 mm pad": 36.0, "shield clip": 14.0, "custom shield can": 0.0, "pad 1.0 mm": 2.3, "1 mm copper, 2 mm mask": 9.0, "solder jumper 2-pad": 4.0}


def _area(p):
    pk = p["package"]
    if pk in PKG_AREA:
        return PKG_AREA[pk]
    m = _re.match(r"JST GH (\d+)-pos", pk)
    if m:
        return (int(m.group(1)) * 1.25 + 3.5) * 5.0
    m = _re.match(r"Micro-Fit 3.0 right-angle THT, (\d+)", pk)
    if m:
        return (int(m.group(1)) * 3.0 + 3.5) * 10.0
    raise KeyError("no area for package " + pk)


def _lane_signature(k):
    """Normalised (ref offset, value, mpn, pins) list of everything generated for lane k."""
    out = []

    def norm(s):
        s = _re.sub(r"(?<![A-Z0-9])([FRL])%d(?![0-9])" % k, r"\1#", s)
        s = _re.sub(r"(_[FR])%d(?![0-9])" % k, r"\1#", s)
        s = _re.sub(r"(SIPM|MON_EN_)%d(?![0-9])" % k, r"\1#", s)
        return s
    bases = {"F%d" % k: 100 * (k + 1), "R%d" % k: 100 * (k + 5), "L%d" % k: 1000 + 100 * k}
    for p in PARTS:
        if p["instance"] in bases:
            m = _re.match(r"([A-Z]+)(\d+)$", p["ref"])
            off = int(m.group(2)) - bases[p["instance"]]
            pins = tuple(sorted((n, v[0], norm(v[1])) if v else (n, None, None) for n, v in p["pins"].items()))
            out.append((p["instance"][0], m.group(1), off, norm(p["value"]), p["mpn"], p["dnp"], pins))
    return sorted(out)


def self_check(verbose=True):
    errors, warnings = [], []
    say = print if verbose else (lambda *a, **k: None)
    blocks = {}
    for p in PARTS:
        blocks.setdefault(p["block"], [0, 0])
        blocks[p["block"]][0] += 1
        blocks[p["block"]][1] += 1 if p["dnp"] else 0
    purchased = [p for p in PARTS if not p["dnp"] and "(PCB feature)" not in p["manufacturer"]
                 and "(custom" not in p["manufacturer"]
                 and p["ref"][:2] not in ("TP",) and p["ref"][:3] != "FID"]
    say("RR-HEAD-ACQ rev A circuit definition")
    say("  part records: %d   (fitted purchased parts: %d, DNP/pads/PCB features: %d)" %
        (len(PARTS), len(purchased), len(PARTS) - len(purchased)))
    for b in sorted(blocks):
        say("    %-14s %4d records (%d DNP or pad-only)" % (b, blocks[b][0], blocks[b][1]))
    say("  distinct manufacturer part numbers (fitted): %d" % len({p["mpn"] for p in purchased}))
    say("  nets: %d   by class: %s" % (len(NETS), ", ".join(
        "%s %d" % (c, sum(1 for n in NETS.values() if n["net_class"] == c)) for c in NET_CLASSES)))

    # 1. duplicate references (also enforced when parts are added)
    refs = [p["ref"] for p in PARTS]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    say("  duplicate references: %s" % (dup or "none"))
    if dup:
        errors.append("duplicate references")

    # 2. nets with fewer than two fitted connections
    fitted = {}
    for p in PARTS:
        if p["dnp"]:
            continue
        for num, v in p["pins"].items():
            if v:
                fitted.setdefault(v[1], 0)
                fitted[v[1]] += 1
    single = sorted(n for n in NETS if fitted.get(n, 0) < 2)
    bad = [n for n in single if n not in SINGLE_PIN_WHITELIST]
    say("  nets with < 2 fitted connections: %d, all whitelisted: %s" % (len(single), "yes" if not bad else "NO " + str(bad)))
    for n in single:
        if n in SINGLE_PIN_WHITELIST:
            say("      %-12s %s" % (n, SINGLE_PIN_WHITELIST[n]))
    unused_wl = sorted(set(SINGLE_PIN_WHITELIST) - set(single))
    if unused_wl:
        warnings.append("whitelist entries not needed: %s" % unused_wl)
    if bad:
        errors.append("single-pin nets: %s" % bad)

    # 3. IC power pins
    nopwr = []
    for p in PARTS:
        if not p["ref"].startswith("U"):
            continue
        sup = [v for v in p["pins"].values() if v and v[0] in SUPPLY_PIN_NAMES]
        gnd = [v for v in p["pins"].values() if v and v[0] in GROUND_PIN_NAMES]
        named_unconnected = [n for n, v in p["pins"].items() if v is None]
        if not sup or not gnd:
            nopwr.append(p["ref"])
        for v in sup:
            if not (v[1].startswith("+") or v[1] in ("VIN_F", "VIN_CM", "BUS_5VF", "VREF_ADC", "TCXO_VDD")
                    or v[1].endswith("_V5")):
                nopwr.append("%s:%s->%s" % (p["ref"], v[0], v[1]))
        for v in gnd:
            if v[1] not in ("GND", "BUS_GND", "EF_RTN"):
                nopwr.append("%s:%s->%s" % (p["ref"], v[0], v[1]))
        del named_unconnected
    say("  IC power pins: %d ICs checked, problems: %s" % (sum(1 for p in PARTS if p["ref"].startswith("U")), nopwr or "none"))
    if nopwr:
        errors.append("IC power pins: %s" % nopwr)

    # 4. undefined pins (every pin of a known package must be present in the pin dictionary, NC as None)
    undefined = []
    for p in PARTS:
        want = PKG_PINS.get(p["package"])
        nums = {int(k) for k in p["pins"] if k.isdigit()}
        if want is not None and nums != set(range(1, want + 1)):
            undefined.append("%s (%s): missing %s" % (p["ref"], p["package"], sorted(set(range(1, want + 1)) - nums)))
        elif want is None and nums and nums != set(range(1, max(nums) + 1)):
            undefined.append("%s: gap in pin numbers" % p["ref"])
    say("  parts with undefined pins: %s" % (undefined or "none"))
    if undefined:
        errors.append("undefined pins")
    nc = sum(1 for p in PARTS for v in p["pins"].values() if v is None)
    say("  explicit no-connect pins: %d" % nc)

    # 5. the four lanes are identical
    sig0 = _lane_signature(0)
    same = all(_lane_signature(k) == sig0 for k in (1, 2, 3))
    say("  lanes 0..3 identical after renaming: %s (%d records per lane)" % ("yes" if same else "NO", len(sig0)))
    if not same:
        errors.append("lanes differ")

    # 6. every part has an MPN; list the ones to verify
    nompn = [p["ref"] for p in PARTS if not p["mpn"]]
    ver = sorted({(p["mpn"], p["manufacturer"]) for p in PARTS if p["verify"]})
    say("  parts without MPN: %s" % (nompn or "none"))
    say("  MPNs / pin-outs marked verify=True: %d distinct" % len(ver))
    for m in ver:
        say("      %-26s %s" % m)
    say("  passive MPNs built from series rules (mpn_rule): %d records, %d distinct" %
        (sum(1 for p in PARTS if p.get("mpn_rule")), len({p["mpn"] for p in PARTS if p.get("mpn_rule")})))
    if nompn:
        errors.append("missing MPN")

    # 7. cross-checks against the firmware pin map and the contract (need PyYAML; skipped otherwise)
    try:
        import os
        import yaml
        root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
        pm = yaml.safe_load(open(os.path.join(root, "firmware", "head", "pinmap.yaml")))
        alias = {"VBAT": "+3V3", "GND": "GND", "+3V3": "+3V3", "AGND": "GND", "VREF_ADC": "VREF_ADC", "+3V3A": "+3V3A"}
        mism = []
        for e in pm["pins"]:
            port, net = MCU_PINMAP[e["lqfp100"]]
            want = alias.get(e["signal"], e["signal"])
            if e["signal"].startswith("SPARE_"):
                want = SPARE_PIN_USE[e["pin"]]
            if port != e["pin"] or net != want:
                mism.append((e["lqfp100"], e["pin"], e["signal"], port, net))
        dm = {k: [("SPARE" if o in ("LED_AMPL", "DAC1_SPARE") else o.replace("THR_LLD_F", "BETA_LLD_").replace(
            "THR_ULD_F", "BETA_ULD_").replace("THR_ALPHA_F", "ALPHA_").replace("THR_LLD_R", "REF_LLD_").replace(
            "THR_ULD_R", "REF_ULD_").replace("TRIM_DAC_F", "TRIM_FLOOR_").replace("TRIM_DAC_R", "TRIM_REF_"))
            for o in v] for k, v in DAC_MAP.items()}
        dmis = [k for k in dm if dm[k] != pm["dac_map"][k]["outputs"]]
        say("  firmware/head/pinmap.yaml: %d MCU pins compared, mismatches: %s; DAC map mismatches: %s" %
            (len(pm["pins"]), mism or "none", dmis or "none"))
        if mism or dmis:
            errors.append("pin map mismatch")
        ct = yaml.safe_load(open(os.path.join(root, "interface", "system", "contract.yaml")))
        cm = []
        for jn, ref in (("J1", "J2001"), ("J2", "J2501")):
            for num, d in ct["connectors"][jn]["pins"].items():
                have = _REFS[ref]["pins"][str(num)]
                if d["net"] == "NC_RESERVED":
                    ok = have is None
                else:
                    ok = have is not None and have[1] == d["net"]
                if not ok:
                    cm.append((jn, num, d["net"], have))
        say("  contract J1/J2 pin tables vs board connectors J2001/J2501: %s" % (cm or "match"))
        if cm:
            errors.append("connector mismatch")
    except ImportError:
        say("  (PyYAML not installed: pin map and contract cross-checks skipped)")

    # 8. placement area estimate
    area = sum(_area(p) for p in PARTS)
    w, h = BOARD["outline_mm"]
    usable = (w - 3.0) * (h - 3.0)
    say("  placed area estimate (courtyards, top side): %.0f mm2 = %.0f %% of the usable %.0f mm2 (%.0f x %.0f mm less 1.5 mm edge)"
        % (area, 100 * area / usable, usable, w, h))
    if area / usable > 0.45:
        errors.append("placement density above 45 %")

    for wmsg in warnings:
        say("  WARNING: " + wmsg)
    for e in errors:
        say("  ERROR: " + e)
    say("SELF-CHECK %s" % ("PASS" if not errors else "FAIL"))
    return not errors


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_check() else 1)
