#!/usr/bin/env python3
"""RR-PANEL rev A -- complete net-level circuit definition (stage 1 output).  Plain data, no dependencies.
`python3 circuit.py` runs the self-check.  Same record format as electronics/chassis_main/design/circuit.py.

Function: five annunciator LEDs under light pipes, a piezo sounder, landing for an optional external
22 mm panel sounder.  The 22 mm buttons are separate panel devices wired to RR-CHS-MAIN (J_BTN, J_HANDS,
J_ESTOP, J_MODE): the hardwired set path does not run through this board (deviation from the contract
wording 'button/LED harness landing', see chassis_main/design/CONTRACT_CHANGE_REQUESTS.md CCR-E04).

Drivers are on the main board (low-side FETs); this board is passive.  LED_FAULT is also lit by hardware
on the main board whenever the watchdog is not satisfied.
verify=True: MPN or data not confirmed against the manufacturer's datasheet in stage 1.
"""
PARTS = []


def part(ref, value, mpn, mfr, desc, pkg, sym, fp, pins, block, dnp=False, rating=None, tol=None, notes="", verify=False, h=1.0, area=5.0):
    PARTS.append(dict(ref=ref, value=value, mpn=mpn, manufacturer=mfr, description=desc, package=pkg, symbol_hint=sym, footprint_hint=fp,
                      pins={str(k): v for k, v in pins.items()}, block=block, dnp=dnp, rating=rating, tolerance=tol, notes=notes, verify=verify,
                      height_mm=h, area_mm2=area))


# Annunciators, left to right as seen by the operator.  Position, legend, symbol and flash pattern identify
# the state without relying on colour.  u = centre along the 70 mm axis.
LEDS = [
    # ref,  net_k,          colour,  mpn,               vf,   r,     u_mm, legend / symbol / pattern (pattern is firmware)
    ("LED1", "LED_READY_K",  "green", "150080GS75000",  3.2, "120", 9.0,  "READY - circle - steady"),
    ("LED2", "LED_MOVING_K", "amber", "150080YS75000",  2.0, "200", 21.0, "MOVING - arrow - 2 Hz flash, with the pre-motion tone"),
    ("LED3", "LED_HOLD_K",   "white", "158080227A",     3.0, "130", 33.0, "HOLD / WAITING FOR NEXT - two bars - slow 0.5 Hz pulse"),
    ("LED4", "LED_CHARGE_K", "blue",  "150080BS75000",  3.2, "120", 45.0, "CHARGE / SERVICE - plug - steady (charging: 1 Hz)"),
    ("LED5", "LED_FAULT_K",  "red",   "150080RS75000",  2.0, "200", 61.0, "FAULT / INHIBITED - triangle - steady or 4 Hz; set apart by a 16 mm gap"),
]
for ref, net, col, mpn, vf, r, u, legend in LEDS:
    part(ref, col, mpn, "Wurth Elektronik", "LED 0805 %s under a 3 mm light pipe at u = %.0f mm: %s" % (col, u, legend), "0805", "Device:LED", "LED_SMD:LED_0805_2012Metric",
         {1: ("K", net), 2: ("A", ref + "_A")}, "annunciator", verify=True,
         notes="I = (5.0 - %.1f) / %s ohm = %.0f mA [C]. Luminous intensity and daylight legibility through the light pipe are UNVERIFIED: test with the real pipe and bezel; "
               "resistor value is the adjustment." % (vf, r, (5.0 - vf) / float(r) * 1000))
    part("R" + ref[3:], r, "RC0805FR-07%sRL" % r, "Yageo", "Resistor %s ohm 1 %%" % r, "0805", "Device:R", "Resistor_SMD:R_0805_2012Metric",
         {1: ("1", "V5_AUX"), 2: ("2", ref + "_A")}, "annunciator", rating="0.125 W", tol="1%")
part("J1", "JST GH 10p side", "SM10B-GHS-TB(LF)(SN)", "JST", "To RR-CHS-MAIN J_PANEL, straight 1:1 cable (bottom side, cable leaves along the long axis)", "GH-H",
     "Connector_Generic_MountingPin:Conn_01x10_MountingPin", "Connector_JST:JST_GH_SM10B-GHS-TB_1x10-1MP_P1.25mm_Horizontal",
     {1: ("1", "V5_AUX"), 2: ("2", "V12_AUX"), 3: ("3", "GND"), 4: ("4", "LED_READY_K"), 5: ("5", "LED_MOVING_K"), 6: ("6", "LED_HOLD_K"), 7: ("7", "LED_FAULT_K"),
      8: ("8", "LED_CHARGE_K"), 9: ("9", "BUZ_N"), 10: ("10", "GND"), "MP": ("MP", "GND")}, "connector", rating="1 A/contact",
     notes="JST GH rated -25..+85 C [U]", h=4.25, area=17 * 7)
part("BZ1", "piezo 4 kHz", "PKLCS1212E4001-R1", "Murata", "SMD piezo sounder 12 x 12 x 3 mm, 4 kHz", "12x12", "Device:Buzzer", "Buzzer_Beeper:Buzzer_Murata_PKLCS1212E",
     {1: ("1", "BUZ_P"), 2: ("2", "BUZ_N")}, "sounder", verify=True, h=3.0, area=160,
     notes="Recalled data [U]: >= 75 dB at 10 cm with 3 Vp-p, -40..+85 C. Driven single-ended 5 Vp-p at 4 kHz by the main-board FET (TIM5_CH1). Expected about 80 dB at 10 cm, "
           "i.e. about 60 dB at 1 m: NOT enough as a pre-motion alert in a noisy trailer. Fit the external sounder on J2 unless a sound-level test says otherwise.")
part("D1", "BAT54", "BAT54W-7-F", "Diodes Inc.", "Schottky: stops the external 12 V sounder back-feeding V5_AUX", "SOD-123", "Device:D_Schottky", "Diode_SMD:D_SOD-123",
     {1: ("K", "BUZ_P"), 2: ("A", "V5_AUX")}, "sounder", area=7)
part("R6", "1k", "RC0805FR-071KL", "Yageo", "Piezo discharge resistor", "0805", "Device:R", "Resistor_SMD:R_0805_2012Metric", {1: ("1", "BUZ_P"), 2: ("2", "BUZ_N")}, "sounder", rating="0.125 W", tol="1%")
part("J2", "JST GH 2p side", "SM02B-GHS-TB(LF)(SN)", "JST", "Optional external 22 mm panel sounder, 12 V self-driven, <= 100 mA (firmware then drives BUZZER as a level, not a tone)", "GH-H",
     "Connector_Generic_MountingPin:Conn_01x02_MountingPin", "Connector_JST:JST_GH_SM02B-GHS-TB_1x02-1MP_P1.25mm_Horizontal",
     {1: ("1", "V12_AUX"), 2: ("2", "BUZ_N"), "MP": ("MP", "GND")}, "sounder", rating="1 A/contact", h=4.25, area=7 * 7,
     notes="Candidate: Schneider Harmony XB5KSB/XB5KS2 class buzzer [U part, level and temperature]. Requirement: >= 85 dB(A) at 30 cm, -25 C.")
part("C1", "100n", "CC0603KRX7R9BB104", "Yageo", "MLCC 100 nF 50 V X7R", "0603", "Device:C", "Capacitor_SMD:C_0603_1608Metric", {1: ("1", "V5_AUX"), 2: ("2", "GND")}, "connector", rating="50 V", tol="10%", area=3.2)
part("C2", "100n", "CC0603KRX7R9BB104", "Yageo", "MLCC 100 nF 50 V X7R", "0603", "Device:C", "Capacitor_SMD:C_0603_1608Metric", {1: ("1", "V12_AUX"), 2: ("2", "GND")}, "connector", rating="50 V", tol="10%", area=3.2)
MECH = {"outline_mm": (70.0, 24.0), "layers": 2, "thickness_mm": 1.6, "max_height_top_mm": 8.0, "max_height_bottom_mm": 3.0,
        "holes_uv_mm": {"H1": (3.5, 20.5), "H2": (66.5, 20.5)}, "hole_diameter_mm": 2.7,
        "note": "LEDs on the top side on the line v = 8 mm; J1, J2, BZ1 and passives on the bottom side (all <= 3 mm except the GH headers at 4.25 mm: "
                "request 4.5 mm bottom clearance at J1/J2 or move them to the top side between the light pipes). Hole positions are a proposal: the mechanical lead gave none."}
for h, (u, v) in MECH["holes_uv_mm"].items():
    part(h, "M2.5", "MOUNTING-HOLE-M2.5", "(pcb feature)", "Mounting hole 2.7 mm at (%.1f, %.1f) mm, unplated" % (u, v), "HOLE", "Mechanical:MountingHole", "MountingHole:MountingHole_2.7mm_M2.5",
         {}, "mech", area=20, h=0)
for i, (u, v) in enumerate([(14.0, 20.0), (56.0, 20.0)]):
    part("FID%d" % (i + 1), "fiducial", "FIDUCIAL", "(pcb feature)", "Fiducial 1 mm", "FID", "Mechanical:Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", {}, "mech", area=7, h=0)
for i, n in enumerate(["V5_AUX", "GND", "BUZ_N"]):
    part("TP%d" % (i + 1), n, "TP-PAD-1.5", "(pcb feature)", "Test pad 1.5 mm", "TP", "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.5mm", {1: ("1", n)}, "test", area=4, h=0)

NET_CLASSES = {"POWER": dict(amps=0.15, nets=["V5_AUX", "V12_AUX", "GND"], rule=">= 0.4 mm"), "SIGNAL": dict(nets=["*"], rule="0.25 mm, 0.2 mm clearance")}
CONNECTORS = {"J1": dict(function="RR-CHS-MAIN J_PANEL, 1:1", awg=26, max_a=0.15), "J2": dict(function="external sounder", awg=24, max_a=0.1)}
MAIN_J_PANEL = ["V5_AUX", "V12_AUX", "GND", "LED_READY_K", "LED_MOVING_K", "LED_HOLD_K", "LED_FAULT_K", "LED_CHARGE_K", "BUZ_N", "GND"]


def build_nets(parts):
    nets = {}
    for p in parts:
        for num, v in p["pins"].items():
            if v is not None:
                nets.setdefault(v[1], []).append((p["ref"], num, v[0]))
    return nets


NETS = build_nets(PARTS)


def self_check():
    errs = []
    refs = [p["ref"] for p in PARTS]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    if dup:
        errs.append("duplicate refs %s" % dup)
    single = sorted(n for n, c in NETS.items() if len(c) < 2)
    if single:
        errs.append("nets with fewer than two connections %s" % single)
    j1 = [p for p in PARTS if p["ref"] == "J1"][0]
    for i, n in enumerate(MAIN_J_PANEL):
        if j1["pins"][str(i + 1)][1] != n:
            errs.append("J1 pin %d does not match main-board J_PANEL (%s)" % (i + 1, n))
    for p in PARTS:
        for num, v in p["pins"].items():
            if v is not None and not (isinstance(v, tuple) and len(v) == 2 and v[1]):
                errs.append("undefined pin %s.%s" % (p["ref"], num))
        if not p["mpn"]:
            errs.append("no MPN " + p["ref"])
    blocks = {}
    for p in PARTS:
        blocks[p["block"]] = blocks.get(p["block"], 0) + 1
    area = sum(p["area_mm2"] for p in PARTS)
    board = MECH["outline_mm"][0] * MECH["outline_mm"][1]
    print("RR-PANEL circuit definition")
    print("  parts: %d, verify=True on %d; by block: %s" % (len(PARTS), sum(1 for p in PARTS if p["verify"]), blocks))
    print("  nets: %d" % len(NETS))
    print("  placed area estimate: %.0f mm2 of %.0f mm2 = %.0f %% (two sides available)" % (area, board, 100 * area / board))
    print("  nets with fewer than two connections: %s" % (single or "none"))
    print("  duplicate refs: %s" % (dup or "none"))
    print("  SELF-CHECK %s" % ("FAILED" if errs else "PASSED"))
    for e in errs:
        print("   ERROR:", e)
    return errs


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_check() else 0)
