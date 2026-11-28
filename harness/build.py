#!/usr/bin/env python3
"""Generates harness/connectors.yaml, harness/cables.csv, harness/pin_views.md and the tables of harness/cables.md
from the data modules hdata_conn.py / hdata_cables.py (which read the authoritative circuit definitions).
Run:  python3 harness/build.py        (writes only inside harness/)"""
import csv, os, sys, collections, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import yaml
import hdata_conn as hc
import hdata_cables as hk
import hdata_parts as hp

TBD = hc.TBD
CONN = hc.build_all()
CABLES = hk.CABLES

# ---------------------------------------------------------------- documented net pairs across inline series elements / links / shields
NET_PAIRS = [
    dict(a="PACK_P", b="VBAT_RAW", via="FUSE-MAIN", why="20 A blade fuse in series with the pack positive"),
    dict(a="PACK_P_CELL", b="PACK_P", via="FUSE-CASS", why="optional cassette fuse"),
    dict(a="PACK_PRES_N", b="GND", via="CPL-C link wire", why="presence link to pack negative inside the cassette"),
    dict(a="PLUG_LINK", b="GND", via="CHGPLUG link 2-4", why="charge-plug link; opens the chain contact when the plug is in"),
    dict(a="J2_PRES", b="BUS_GND", via="J2P plug link 7-4", why="contract: J2 mate detect linked to pin 4 inside the head plug"),
    dict(a="CHS_HTR_P", b="CHS_HTR_MID", via="HTR-CHS element", why="7.2 ohm element"),
    dict(a="CHS_HTR_MID", b="GND", via="CUT-CHS", why="series bimetal cut-out"),
    dict(a="HTR_SW", b="HTR_CUT", via="HEAD-HEATER element", why="4.8 ohm element"),
    dict(a="HTR_CUT", b="HEAD_HTR_N", via="HEAD-CUTOUT", why="low-side bimetal cut-out"),
    dict(a="CH_N0", b="CH_N1", via="MODE-DEV RUN contact", why="chain element MODE_RUN"),
    dict(a="CH_N1", b="CH_N2", via="ESTOP-DEV pole A", why="chain element ESTOP"),
    dict(a="CH_N2", b="CH_N3", via="HANDS-DEV NC", why="chain element HANDS_ON"),
    dict(a="CH_N3", b="CH_N4A", via="COVER-DEV NC", why="chain element CHG_COVER (cover)"),
    dict(a="CH_N4", b="CH_N5", via="DOCK-DEV NC", why="chain element HEAD_DOCK"),
    dict(a="CH_N7", b="CH_N8A", via="BUMP-L-DEV NC", why="chain element BODY_BUMPER (left)"),
    dict(a="CH_N8A", b="CH_N8", via="BUMP-R-DEV NC", why="chain element BODY_BUMPER (right)"),
    dict(a="EN_SRC", b="EN_SYS", via="MODE-DEV EN contact", why="master enable contact"),
    dict(a="REARM_SET_SRC", b="REARM_SET_RAW", via="REARM-DEV NO 1", why="REARM set contact (momentary): a 5 V signal into the on-board set stage (stage 3), no longer the K1 coil pulse"),
    dict(a="BTN_3V3", b="REARM_BTN_RAW", via="REARM-DEV NO 2", why="REARM_BTN contact"),
    dict(a="PAUSE_3V3", b="PAUSE_BTN_RAW", via="PAUSE-DEV NO", why="PAUSE contact (own supply through R_PAUSE 1 kohm, stage 2 S2-01f)"),
    dict(a="HEAD_LOOP_OUT", b="LOOP_A", via="RAIL-F NC", why="head rail switch front"),
    dict(a="LOOP_A", b="LOOP_B", via="RAIL-R NC", why="head rail switch right (on J2003, OD-6)"),
    dict(a="LOOP_B", b="LOOP_C", via="RAIL-L NC", why="head rail switch left (on J2004, OD-6)"),
    dict(a="LOOP_C", b="HEAD_LOOP_RET", via="R2019 1.00 kohm on the head board", why="loop resistor (on the board, not in the harness)"),
    dict(a="CHASSIS", b="SHLD_J1", via="mated J1 shells / LAB braid", why="shield: chassis bond at the receptacle, RC bond at the head"),
    dict(a="CHASSIS", b="SHLD_J2", via="mated J2 shells / LAB braid", why="shield: chassis bond at the receptacle, RC bond at the head"),
    dict(a="HEAD_PRES_ID", b="HEAD_PWR_N", via="R_LAB 1.50 kohm in J1X-P backshell", why="LAB resistor pin 7 to pin 2"),
]
EQUIV = {}   # per-board names of the same signal (documented): chassis net -> carrier net
for n in range(11):
    EQUIV.update({"TOF%d_3V3" % n: "+3V3", "TOF%d_SDA_C" % n: "SDA", "TOF%d_SCL_C" % n: "SCL", "TOF%d_XSHUT_C" % n: "XSHUT", "TOF%d_GPIO1" % n: "GPIO1"})
MATES = [
    dict(a="J1R", b="J1P", config="robot"), dict(a="J2R", b="J2P", config="robot"), dict(a="CPL-B", b="CPL-C", config="robot"), dict(a="INLET", b="CHGPLUG", config="charging"),
    dict(a="J1X-P", b="J1R", config="LAB"), dict(a="J1X-S", b="J1P", config="LAB"), dict(a="J2X-P", b="J2R", config="LAB"), dict(a="J2X-S", b="J2P", config="LAB"),
]
SERVICE = {"CHS.J_AUX": "spare fan/spare connector: no cable in rev A", "CHS.J_DBG": "debug UART service port: plug a lead when needed", "CHS.J_SWD": "SWD service port: ribbon only when programming",
           "MOTSUP-L": "assembly item soldered at the motor terminals (cables.md section 7): not a wire", "MOTSUP-R": "as MOTSUP-L", "CHS.W1": "DNP wire pads of the on-board clamp circuit: NO cable by decision (the board carries its own 2 x 9.1 ohm clamp resistors; no bolt-on 50 W part, IB-26 / IB-36)", "HEAD.J2401": "SWD pads (no component fitted): Tag-Connect cable only when programming", "HEAD.J2402": "debug UART service port", "HEAD.J2701": "monitor output test port: coax only on the bench",
           "HEAD.JP2201": "solder jumper (lid bypass): bench only", "CHGPLUG": "supply-side plug: belongs to the external 24 V supply, not to the robot harness"}
UNWIRED = {("CHS.J_PAUX", "3"): "no wire by decision (IB-37, chassis stage 2): NTC and presence return to pack negative inside the cassette (W-002/W-003); the accepted offset is about 0.1 V at full load (NTC about 3.4 K warm on discharge, about 0.7 K cold on charge, safe side). Wire pins 3/4 only if the cassette gets an isolated sense return", ("CHS.J_PAUX", "4"): "no wire by decision (IB-37, as pin 3)",
           ("HEAD.J2002", "3"): "no wire by decision: CCR-HE-04 (single-pole switch, NO throw not potential-free)", ("HEAD.J2002", "4"): "as pin 3",
           ("HEAD.J2003", "3"): "as J2002 pin 3", ("HEAD.J2003", "4"): "as J2002 pin 3", ("HEAD.J2004", "3"): "as J2002 pin 3", ("HEAD.J2004", "4"): "as J2002 pin 3",
           ("CM5-USB1", "1"): "VBUS left open: board pin J_USB_MCU 1 is NC", ("INLET", "FE"): "chassis bond through the receptacle flange (no wire)",
           ("J1R", "SH"): "shield bonded to the chassis through the receptacle shell (no wire)", ("J2R", "SH"): "as J1R", ("J1X-S", "SH"): "continuous braid (W-200)", ("J2X-S", "SH"): "continuous braid (W-201)",
           ("CM5-HDR", "*"): "only the four feed pins are used"}


def pin_wires():
    pw = collections.defaultdict(list)
    for c in CABLES:
        for x in c["wires"]:
            pw[(x["frm"], x["fp"])].append(x["wid"])
            pw[(x["to"], x["tp"])].append(x["wid"])
    return pw


PW = pin_wires()


def pin_sort(k):
    return (0, int(k)) if k.isdigit() else (1, k)


def unconnected():
    out = []
    for cid, c in CONN.items():
        for p in sorted(c["pins"], key=pin_sort):
            if (cid, p) in PW:
                continue
            net = c["pins"][p]
            if net in ("NC", "NC_RESERVED", "UNUSED"):
                why = "NC by design (net %s)" % net
            elif (cid, p) in UNWIRED:
                why = UNWIRED[(cid, p)]
            elif cid in SERVICE:
                why = SERVICE[cid]
            elif (cid, "*") in UNWIRED:
                why = UNWIRED[(cid, "*")]
            else:
                why = "NOT WIRED - no decision recorded (check)"
            out.append((cid, p, net, why))
    return out


# ================================================================ connectors.yaml
def write_connectors():
    lines = ["# harness/connectors.yaml -- GENERATED by harness/build.py from hdata_conn.py + the circuit definitions; do not edit by hand.",
             "# One row per connector, panel receptacle, inline half, splice, fuse and device end of the whole robot and head.",
             "# Status vocabulary: verified = not flagged as recalled in its source; UNVERIFIED = the source flags it; TBD - not in sources = no source gives it (open item).",
             "# Pin geometry (which physical position carries which number) is NOT verified against a manufacturer drawing for ANY family (no drawings in the sources): see pin_views.md.",
             "# Pin nets are copied from the board definitions; wires = the W-xxx.n wires of cables.csv that land on the pin.",
             "schema: 1", "net_aliases: %s" % yaml.safe_dump(hc.ALIASES.copy() if False else {"HEAD_PWR_N": "GND", "BUS_GND": "GND", "PACK_N": "GND", "NC_RESERVED": "NC"}, default_flow_style=True).strip(),
             "# documented equivalent signal names between boards (not inline connectors)",
             "net_equivalents: %s" % yaml.safe_dump(EQUIV, default_flow_style=True, width=10 ** 9).strip(),
             "net_pairs:"]
    for p in NET_PAIRS:
        lines.append("  - {a: %s, b: %s, via: %s, why: \"%s\"}" % (p["a"], p["b"], p["via"].replace(":", " "), p["why"]))
    lines.append("mates:")
    for m in MATES:
        lines.append("  - {a: %s, b: %s, config: %s}" % (m["a"], m["b"], m["config"]))
    lines.append("connectors:")
    for cid, c in CONN.items():
        lines.append("  - id: %s" % cid)
        for key in ("location", "function", "kind", "family", "mpn", "mpn_status", "mating", "mating_status", "contacts", "seal", "temp", "temp_status", "keying", "source", "notes"):
            v = c.get(key)
            if v in (None, ""):
                continue
            lines.append("    %s: %s" % ({"mating": "mating_half"}.get(key, key), yaml.safe_dump(str(v), default_flow_style=True, width=10 ** 9).strip().replace("\n...", "")))
        if c.get("board"):
            lines.append("    board: %s" % c["board"])
        if c.get("same_count_as"):
            lines.append("    same_count_as: %s" % yaml.safe_dump(c["same_count_as"], default_flow_style=True, width=10 ** 9).strip().replace("\n...", ""))
        lines.append("    pin_geometry_status: UNVERIFIED (no manufacturer drawing in the sources; see pin_views.md, geometry family '%s')" % c["geom"])
        mates = [m["b"] if m["a"] == cid else m["a"] for m in MATES if cid in (m["a"], m["b"])]
        if mates:
            lines.append("    mated_with: [%s]" % ", ".join(mates))
        lines.append("    pins:")
        for p in sorted(c["pins"], key=pin_sort):
            ws = PW.get((cid, p), [])
            awg = c["awg_rec"].get(p)
            lines.append("      \"%s\": {net: %s%s, wires: [%s]}" % (p, c["pins"][p], (", awg_rec: %s" % awg) if awg else "", ", ".join(ws)))
    un = unconnected()
    lines.append("unconnected_pins:   # connector pins with no wire in cables.csv, with the reason")
    for cid, p, net, why in un:
        lines.append("  - {connector: %s, pin: \"%s\", net: %s, reason: \"%s\"}" % (cid, p, net, why.replace('"', "'")))
    open(os.path.join(HERE, "connectors.yaml"), "w").write("\n".join(lines) + "\n")
    return un


# ================================================================ cables.csv
HDR = ["wire_id", "cable_id", "cable_title", "group", "from_connector", "from_pin", "to_connector", "to_pin", "net_from", "net_to", "wire_kind", "awg", "colour", "conductor_insulation",
       "twisted_pair", "shield_and_bonding", "length_mm", "length_status", "protection_upstream", "label_from_end", "label_to_end", "strain_relief", "note"]


def write_csv():
    with open(os.path.join(HERE, "cables.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(HDR)
        for c in CABLES:
            for x in c["wires"]:
                wr.writerow([x["wid"], c["id"], c["title"], c["group"], x["frm"], x["fp"], x["to"], x["tp"], x["net"], x["to_net"], x["kind"], x["awg"] if x["awg"] else "n/a (micro-coax)",
                             x["col"], hk.INS[x["ins"]], x["pair"], c["shield"], x["len_mm"], "estimated from layout, confirm on first build", c["protection"], hk.lbl(x, "from"), hk.lbl(x, "to"),
                             c["strain"], x["note"]])


# ================================================================ pin views
def box(rows, width=5):
    """rows = list of lists (top row first) of strings; returns text lines of a simple box."""
    w = max(len(r) for r in rows)
    out = ["  +" + "-" * (w * (width + 1) + 1) + "+"]
    for r in rows:
        cells = "".join(("%s" % x).center(width) + " " for x in r + [""] * (w - len(r)))
        out.append("  | " + cells + "|")
    out.append("  +" + "-" * (w * (width + 1) + 1) + "+")
    return out


def layout(c):
    """returns (rows_for_wire_entry_view, key_note) ; mating view = mirror."""
    pins = [p for p in sorted(c["pins"], key=pin_sort)]
    nums = [p for p in pins if p.isdigit()]
    n = len(nums)
    g = c["geom"]
    if g in ("single", "single_ra"):
        rows = [nums]
        key = "polarised housing profile; latch/key side shown UP (convention)"
    elif g == "dual":
        m = n // 2 if n > 2 else 1
        rows = [nums[m:], nums[:m]] if n > 2 else [[nums[1]], [nums[0]]]
        key = "latch/polarising side shown UP; circuits 1..%d bottom row, %d..%d top row, pin 1 at the left of the MATING view (convention)" % (m, m + 1, n)
    elif g == "idc":
        rows = [["2", "4", "6", "8", "10"], ["1", "3", "5", "key", "9"]]
        key = "shrouded keyed 2x5 1.27 mm header (FTSH ... K): key at position 7; pin 1 at the shroud notch/marker (convention)"
    else:
        rows = None
        key = ""
    return rows, key


def mirror(rows):
    return [list(reversed(r)) for r in rows]


def circ_view(c, mirrored):
    g = c["geom"]
    if g in ("circ_m16", "circ_m12"):
        ring = ["1", "2", "3", "4", "5", "6", "7"]
        o = ["            key",
             "             v",
             "        .--- ^ ---.",
             "      /   %s     %s   \\" % (ring[6 if not mirrored else 0], ring[0 if not mirrored else 6]),
             "     |  %s    8    %s  |" % (ring[5 if not mirrored else 1], ring[1 if not mirrored else 5]),
             "      \\   %s     %s   /" % (ring[4 if not mirrored else 2], ring[2 if not mirrored else 4]),
             "        '--- %s ---'" % (ring[3])]
        return o
    if g == "circ_m12l":
        return ["            key", "             v", "        .--- ^ ---.", "      /  %s       %s  \\" % ("4" if not mirrored else "1", "1" if not mirrored else "4"),
                "     |       FE      |", "      \\  %s       %s  /" % ("3" if not mirrored else "2", "2" if not mirrored else "3"), "        '---------'"]
    return []


def write_views():
    L = ["# Pin views of every connector", "",
         "GENERATED by `harness/build.py`; do not edit by hand. Every diagram shows two views of the same connector body and says which is which.", "",
         "## Read this first", "",
         "* **MATING FACE view**: you look at the face that meets the other half.",
         "* **WIRE-ENTRY view**: you look at the opposite face: for a crimp housing this is the face the crimped contacts are pushed into; for a panel receptacle with solder cups it is the cup side; for a board header it is the PCB side. The wire-entry view is the **mirror image** of the mating-face view.",
         "* For a **board header** the diagram shows the **cable-side housing** that the technician builds (the plug that mates with the header). The header's own mating face, seen from outside, has the same arrangement as the plug's WIRE-ENTRY view.",
         "* **EVERY pin position and key orientation drawn here is a CONVENTION, UNVERIFIED**: the sources contain no manufacturer drawings (no Molex, JST, binder, Anderson or Hirose drawing was available). The **pin numbers and their nets are authoritative** (they come from the board definitions); the geometric placement of those numbers on the housing must be checked against the manufacturer drawing before the first crimp. Where the housing carries moulded circuit numbers, those win.",
         "* A plug's MATING FACE view is the mirror image of its receptacle's MATING FACE view (so J1P mating face = mirror of J1R mating face).",
         "* Devices (switches, heaters, NTCs, modules) have no standard pin geometry in the sources: they are listed as terminal tables only.", ""]
    for cid, c in CONN.items():
        L.append("## %s" % cid)
        L.append("")
        L.append("%s. Part: %s [%s]. Mating half: %s [%s]." % (c["function"], c["mpn"], c["mpn_status"], c["mating"], c["mating_status"]))
        L.append("")
        g = c["geom"]
        rows, key = layout(c)
        if rows:
            L.append("**MATING FACE view** (cable-side housing, looking at the face that meets the %s)" % ("board header / receptacle" if c["kind"] == "board_header" else "mating half"))
            L.append("```")
            L += box(mirror(rows) if False else rows)
            L.append("```")
            L.append("**WIRE-ENTRY view** (looking at the rear of the housing, where the crimped wires go in; mirror image)")
            L.append("```")
            L += box(mirror(rows))
            L.append("```")
            L.append("Keying / coding: %s. Geometry: %s [UNVERIFIED]." % (c["keying"], key))
        elif g.startswith("circ"):
            pm = c["kind"] == "cable_plug"   # a plug's mating face is the mirror image of the receptacle's mating face
            L.append("**MATING FACE view** (looking at the contact face of this %s)" % ("plug" if pm else "receptacle/socket"))
            L.append("```")
            L += circ_view(c, pm)
            L.append("```")
            L.append("**WIRE-ENTRY view** (looking at the solder-cup / crimp side; mirror image of the mating face)")
            L.append("```")
            L += circ_view(c, not pm)
            L.append("```")
            L.append("Keying / coding: %s. Generic %s layout, key at the top (convention, UNVERIFIED against the binder/IEC drawing; pin 8 is the centre position for the 8-pole A-coded M12 arrangement, and is NC_RESERVED here so a position error cannot move a live net)." % (
                c["keying"], "7 + 1 centre" if g != "circ_m12l" else "4 + FE"))
        elif g == "usba":
            L.append("**MATING FACE view** (USB-A plug, contacts toward you)")
            L.append("```")
            L += box([["1", "2", "3", "4"]])
            L.append("```")
            L.append("**WIRE-ENTRY view** (cable side, mirror image)")
            L.append("```")
            L += box([["4", "3", "2", "1"]])
            L.append("```")
            L.append("Keying: rectangular USB-A shell (polarised). Pin order 1 VBUS, 2 D-, 3 D+, 4 GND per the USB specification; SH = shell.")
        elif g == "coax":
            L.append("**MATING FACE view**: U.FL jack: centre pin = signal (pin 1), outer shell/ground = pin 2. Snap-on; no polarisation against other U.FL jacks.")
            L.append("**WIRE-ENTRY view**: plug side: micro-coax centre conductor soldered to the plug centre contact, braid to the outer shell.")
        else:
            L.append("Device / module / pad: no standard pin geometry in the sources. Terminal table below.")
        L.append("")
        L.append("| Pin | Net | Wire(s) |")
        L.append("|---|---|---|")
        for p in sorted(c["pins"], key=pin_sort):
            L.append("| %s | %s | %s |" % (p, c["pins"][p], ", ".join(PW.get((cid, p), [])) or "-"))
        L.append("")
    open(os.path.join(HERE, "pin_views.md"), "w").write("\n".join(L) + "\n")


# ================================================================ cables.md
def resist_awg(a):
    return {12: 5.21, 14: 8.29, 16: 13.2, 18: 20.9, 20: 33.3, 22: 53.0, 24: 84.2}.get(a)



def _poly_dist(a, b, step=2.0):
    """minimum distance (mm) between two polylines, sampled every `step` mm"""
    def pts(p):
        out = []
        for i in range(len(p) - 1):
            n = max(1, int(hk.dist(p[i], p[i + 1]) / step))
            out += [tuple(p[i][k] + (p[i + 1][k] - p[i][k]) * j / n for k in range(3)) for j in range(n)]
        return out + [p[-1]]
    A, B = pts(a), pts(b)
    return min(hk.dist(x, y) for x in A for y in B)


def heater_section():
    """sections 6-8 of cables.md: heater-pair drop with AWG 20 at the head end, motor suppression, test notes"""
    R = {18: 20.9, 20: 33.3}
    byid = {c["id"]: c for c in CABLES}
    w8 = byid["W-008"]["length_mm"] / 1000.0
    wx = {x["wid"]: x for x in byid["W-101"]["wires"]}
    l18 = wx["W-101.3"]["len_mm"] / 1000.0
    l20 = wx["W-101.3H"]["len_mm"] / 1000.0
    l103 = byid["W-103"]["length_mm"] / 1000.0
    def loop(head_awg):
        wires = 2 * (w8 * R[18] + l18 * R[18] + (l20 * R[head_awg] if head_awg == 20 else (0)) + l103 * R[head_awg])
        if head_awg == 18:      # all-AWG 18 reference: the 30 mm + inside run in AWG 18, no splice
            wires = 2 * (w8 * R[18] + (l18 + l20) * R[18] + l103 * R[18])
        return wires
    contacts = 4 * 5.0 * 2       # 4 mated contact pairs per pole x 5 mohm [A, power_budget.md] x 2 poles
    splices = 2 * 1.0            # 1 mohm per splice: ASSUMPTION (not in any source)
    board = 5.0 + 28.0 + 3.0     # INA3221 shunt + eFuse FET + board copper (power_budget.md section 6)
    rows = []
    for tag, awg in (("head end AWG 20 (stage 3)", 20), ("all AWG 18 (stage 2, reference)", 18)):
        rw = loop(awg)
        rt = (rw + contacts + (splices if awg == 20 else 0.0) + board) / 1000.0
        for vs in (10.0, 12.0, 14.6):
            i = vs / (4.8 + rt)
            p = i * i * 4.8
            rows.append((tag, vs, rw, rt * 1000.0, i, i * 4.8, p, vs * vs / 4.8))
    L = ["## 6. Head heater pair: AWG 20 at the head end (stage 3, H-03 / IB-61)", "",
         "Gauge change: the contract J1 table keeps AWG 18 on pins 3/4 at the M16 plug; each heater pole is AWG 18 from the M16 plug to a sealed crimp splice (SPL-JH3 / SPL-JH4) %.0f mm outside the head gland, and AWG 20 from there through the gland to the Micro-Fit 43030-0007 terminal of J2001 (%.0f mm) and on through W-103 (%.0f mm) to the heater film and cut-out. One conductor cannot change gauge, so the splice is a wire-to-wire crimp splice (part TBD); it cannot sit inside the head (9 mm between plug backs and wall).  The chassis lead W-008 (%.0f mm) stays AWG 18 in the Mini-Fit Jr terminal." % (hk._SPL_OUT, l20 * 1000, l103 * 1000, w8 * 1000), "",
         "Loop resistance at 20 C: wires from the table below, 4 mated contact pairs per pole at 5 mohm each [A, power_budget.md], splices 1 mohm each [ASSUMPTION], board part 36 mohm (INA3221 shunt 5, eFuse FET 28, copper 3; power_budget.md). Heater 4.8 ohm (head circuit.py: 3.04 A at 14.6 V). Calculated, not measured.", "",
         "| Case | Supply at the chassis branch (V) | Wire loop (mohm) | Series total (mohm) | Heater current (A) | Voltage at the heater (V) | Power delivered (W) | Ideal, no series R (W) |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %.1f | %.0f | %.0f | %.2f | %.2f | %.2f | %.2f |" % r)
    r20 = [r for r in rows if r[0].startswith("head end") and r[1] == 12.0][0]
    r18 = [r for r in rows if r[0].startswith("all") and r[1] == 12.0][0]
    L += ["", "AWG 20 against AWG 18 at the head end costs %.0f mohm of loop resistance (%.2f W at 12 V). The stage-3 head file quotes about 7 mohm for 2 x 0.29 m; the figure here follows the real lengths of this generator." % (r20[3] - r18[3], r18[6] - r20[6]), "",
         "**Protection gap (stated honestly).** Heater draw is up to 3.04 A at 14.6 V; the 43030-0007 terminal is rated about 3.13 A continuous [UNVERIFIED, recalled; the Molex fetch failed], i.e. 3 %% margin at 14.6 V and 1.6x only against the AWG 20 wire (5 A table value). Protection layers: (1) head firmware cuts the heater at 3.2 A sustained for 300 ms (software, head MCU); (2) the independent bimetal cut-out in series acts on TEMPERATURE, not current; (3) the chassis HEAD_HTR eFuse trips only at 3.56-4.35 A (R46 845 ohm, 3.96 A nominal), i.e. 14-39 %% above the terminal rating. Between 3.13 A and 3.56 A no hardware current protection acts at all; between 3.2 A and 3.56 A only the head firmware does, and a fault that also disables the head MCU (or a stuck heater FET with a hung MCU) leaves the terminal at up to 4.35 A until the eFuse trips (eFuse reaction time not in the sources). A rise of the terminal temperature is not covered by any figure in the sources. Mitigations not taken here (they need the lead): lower the chassis limit (R46 value, IB-28) to about 3.3 A nominal, or split each heater pole over two contacts (head L-02 / J1 contract revision).", ""]
    # motor routing distance to the head pigtails
    hpg = {}
    for sd, tag in (("L", "W-006"), ("R", "W-007")):
        mp = byid[tag]["path"]
        pig = [hk.hp, hk.rcpt1] if sd == "L" else [hk.hp2, hk.rcpt2]
        hpg[sd] = _poly_dist(mp, pig)
    L += ["## 7. Motor-terminal suppression (review M4, head S3-H H-01): assembly item of W-006 / W-007", "",
          "Brush arcs (about 5 ns edges) and PWM edges put 1-100 MHz noise on the motor leads; the BLM31 bead + 1 nF at the chassis connector only acts above about 50 MHz and only at the board end. Fit at EACH motor, soldered AT the motor terminals:", "",
          "| Item | Value / type | Notes |", "|---|---|---|",
          "| C_X, across the two motor terminals | 47-100 nF, X7R >= 50 V in 1206 (or a film capacitor) | motor bus is limited to 16.6 V (OV cut-off) and clamped near 15.6 V: 50 V is a 3x margin; part TBD, no source names one |",
          "| C_Y1, C_Y2, one from EACH terminal to the motor can | 4.7-10 nF, X7R >= 100 V | the can is the shield return; part TBD |",
          "| Lead length of all three capacitors | <= 5 mm | short leads or the capacitor soldered directly across the tabs |",
          "| Temperature | X7R is -55..+125 C by EIA code: covers the -25 C objective; capacitance change within +-15 %% over that range plus the DC-bias loss at 12 V: verify on the chosen part (a class value, no datasheet fetched) | film capacitors: check the -25 C rating of the part |",
          "| Can strap to the chassis plate | braid or tab, <= 30 mm, >= 2.5 mm wide, to the chassis plate | HOW on the Pololu 37D-class gearmotor: the motor can is the cylindrical shell behind the gearbox; the strap needs a bonded point on it: either a ring terminal clamped under the gearmotor bracket screw if the bracket touches the can, or a solder tab on the can (tin-plated steel can: heat-sink the can, short iron time so the brushes and magnets are not heated). UNVERIFIED mechanical detail: no Pololu drawing in the sources of how the can is finished or whether the mounting bracket makes metal contact with it; confirm on the first motor |",
          "| Test label | W-006.SUP / W-007.SUP | after fitting: can to chassis plate < 0.1 ohm (4-wire); capacitance of C_X and each C_Y (LCR meter, 1 kHz) within -20..+20 %% of the nominal; motor terminals to can still insulated (no short from a terminal to the can: > 10 Mohm at 50 V with C_Y fitted is dominated by the capacitors: check with the capacitors DISCONNECTED during assembly); bench B11: motors on a DC supply at 100 %% duty, back-driven with the bridges asleep, and through brake-relay transitions while counting head events |", "",
          "Routing: twist the motor pair (W-006.1/.2, W-007.1/.2) from the motor to the board connector (they are specified as pair M); route the encoder pairs away from the head side. Calculated clearance between the motor cable path and the head pigtail path in this generator: LEFT %.0f mm, RIGHT %.0f mm (centre-line distance, model accuracy +-20 mm); require >= 50 mm in the build and keep the motor leads on the OUTBOARD side of the chassis gutters, the head pigtails inboard." % (hpg["L"], hpg["R"]), ""]
    L += ["## 8. Test notes (harness)", "",
          "* **Head isolation test E7 (>= 10 Mohm, frame to receiver)**: run with J1 and J2 UNMATED (plugs removed, head on the receiver or on the bench with the receiver metal contacted): with J1/J2 mated a DC path exists by design: frame - F2801 (0.5 A fuse, stage 3) - R2801 (0 ohm) - head GND - J1 pin 2 (W-101.2, W-008.2) - chassis board GND, and the drain network (1 Mohm || 10 nF to FRAME). Test voltage 100 V DC, unmated only. **Mated check** (separate step, label E7M): measure the expected BOND resistance frame to chassis GND at the J1 receptacle shell with a four-wire meter at <= 100 mA (below the 0.5 A fuse rating): expected = F2801 + R2801 + about 0.44 m of AWG 20/18 conductor + contact pairs, dominated by the fuse; the fuse DC resistance is not in any source (record the real value, expect well under 2 ohm, UNVERIFIED) and it holds only if the chassis board GND is bonded to the chassis metal (not stated in the sources: if it is not, the mated reading is >= 1 Mohm through the drain network). Never run the 100 V insulation tester mated.",
          "* **Heater circuit insulation (review M5)**: assembled head, spreader bolted to the board, board disconnected: heater circuit (J2601 plug pins 1, 2, 3, NTC 4/5) to FRAME >= 10 Mohm at 100 V; label W-103.HTR-ISO. Isolated-case cut-out (>= 100 Mohm at 100 V) and isolated NTC lug or polyimide pad are BOM requirements (parts TBD).",
          "* **W-018 after routing**: continuity pin to pin, insulation between all six conductors (label W-018.ISO), no supply conductor between the two contact pairs.",
          "* **Motor suppression**: see section 7 (labels W-006.SUP, W-007.SUP).", ""]
    return [x.replace("%%", "%") for x in L]


def write_cables_md(un):
    L = ["# Cable assemblies", "",
         "GENERATED tables (by `harness/build.py` from `hdata_cables.py`) plus fixed text. One numbered item per assembly (W-xxx); each wire is W-xxx.n. Machine-readable form: `cables.csv`.", "",
         "**Every length in this document is estimated from layout, confirm on first build.** Board connector positions are the stage-2 PLACED positions (`out/pinmap.json` of the chassis and head boards, +-20 mm until the boards are routed and the shell is built); sensor and device positions are from `frames.yaml` / `mechanical_interfaces.md`.", "",
         "## 1. Rules for every assembly", "",
         "### Colour scheme (colour is a class aid, not an identifier)", "", "| Code | Colour | Used for |", "|---|---|---|"]
    for code, name, use in hk.COLOUR_SCHEME:
        L.append("| %s | %s | %s |" % (code, name, use))
    L += ["", "Duplicate colours on one cable (for example two BK conductors) are told apart by the wire number printed on every conductor at both ends and every 100 mm (heat-shrink or laser-printed sleeve): **W-xxx.n**. Motor leads keep the maker's colours (Pololu, modules sheet [D]).", "",
          "### Conductor and insulation (cold-flexible, rated to at least -40 C)", "",
          "| Code | Insulation | Where |", "|---|---|---|",
          "| SI | %s | all power, chain, heater and general conductors |" % hk.INS["SI"],
          "| FEP | %s | AWG 24-28 signal conductors, USB, ToF, NTC |" % hk.INS["FEP"],
          "| COAX | %s | SiPM anode and bias pigtails |" % hk.INS["COAX"],
          "| DEV | %s | motor pigtails, device leads |" % hk.INS["DEV"], "",
          "No source names a specific cable or wire part number; the class values are generic, UNVERIFIED, and the technician needs a supplier datasheet showing the rating at -40 C before purchase (open item OI-01). The outer jacket of external multicores is PUR or TPE rated to <= -40 C (type TBD). **PVC is excluded.** `power_budget.md` assumed 'PVC-free, 105 C' AWG 14: that rating is not a cold rating.", "",
          "### Length method", "",
          "Routed path along the reserved corridors (`layout_report.md` section 7) between the placed connector positions (stage 2) and the device positions in `frames.yaml` / `mechanical_interfaces.md`; plus 2 x end allowance for termination and strain relief (25 mm, 30 mm on large connectors, 15 mm on ToF) plus a service loop (50 mm, 30 mm on ToF), rounded up to 10 mm. Panel devices are reached at 45 mm behind the skin along the control axis. The path points are in `hdata_cables.py` (`path=`). Where the power budget assumed a length, it is shown for comparison.", "",
          "### Labels", "",
          "At **both ends** of every cable, within 30 mm of the connector: a sleeve with `W-xxx`, the connector ID (as in `connectors.yaml`) and pin 1 marker; on every conductor the wire number `W-xxx.n` and the net (`label_from_end` / `label_to_end` columns of `cables.csv` give the exact text). Chain (yellow) looms additionally carry a SAFETY CHAIN sleeve every 150 mm. LAB items carry a LAB ONLY sleeve (see `lab_extension.md`).", ""]
    L += ["## 2. Summary", "", "| Cable | Title | Wires | Length (mm) | Budget assumed (mm) | Flag |", "|---|---|---|---|---|---|"]
    flags = []
    for c in CABLES:
        fl = ""
        if c["id"].startswith("W-0") and 30 <= int(c["id"][2:].replace("-", "")) <= 40 and c["length_mm"] > 300:
            fl = "ToF cable exceeds 300 mm"
            flags.append((c["id"], c["length_mm"], "ToF cable exceeds the 300 mm I2C design limit (modules/tof_vl53l4ed.md)"))
        if c["budget_mm"] and c["length_mm"] > c["budget_mm"] and c["group"] != "lab" and not fl:
            fl = "exceeds length assumed by the source (%d mm)" % c["budget_mm"]
            flags.append((c["id"], c["length_mm"], "exceeds the length assumed in power_budget.md / mechanical (%d mm)" % c["budget_mm"]))
        L.append("| %s | %s | %d | %d | %s | %s |" % (c["id"], c["title"], len(c["wires"]), c["length_mm"], c["budget_mm"] or "-", fl))
    nw = sum(len(c["wires"]) for c in CABLES)
    L += ["", "Totals: **%d cable assemblies, %d wires** (%d robot, %d head, %d LAB extension wires)." % (len(CABLES), nw, sum(len(c["wires"]) for c in CABLES if c["group"] == "robot"),
                                                                                                  sum(len(c["wires"]) for c in CABLES if c["group"] == "head"), sum(len(c["wires"]) for c in CABLES if c["group"] == "lab")), ""]
    L += ["### Lengths that exceed a limit", "", "| Cable | Length (mm) | Why flagged |", "|---|---|---|"]
    for f in flags:
        L.append("| %s | %d | %s |" % f)
    L += ["", "Where lengths come from (stage 2): the board connector positions are the PLACED positions in `electronics/chassis_main/out/pinmap.json` (rear-right cluster J_PAUSE, J_TOF3, J_TOF10, J_BUMP_R, J_TOF6; J_PWR at u 142.5, v 24.1; J_HEAD1 Mini-Fit Jr at u 26.1, v 82.5), the head connector positions are those of `electronics/head_acq/out/pinmap.json`, the sensor positions are those of `mechanical/common/frames.yaml` read at the time of the build. The stage-1 rear-left allocation of the right-hand cables (W-022 430 mm, W-033 400 mm, W-040 400 mm, W-019 290 mm) is gone.", "",
          "Open length items: (a) **IB-34 mapping (lead decision, OD-1 closed)**: J_TOF4 = LOOK_FL, J_TOF5 = LOOK_RL, J_TOF6 = LOOK_RR, J_TOF7 = LOOK_FR: W-034 150, W-035 270, W-036 290, W-037 150 mm. (b) W-004 is 30 mm over the 250 mm of the power budget (about 1 mohm: no consequence). (c) The eight SiPM coax pairs (W-112..W-119) are 45-50 mm against the 35 mm of `board_envelopes.yaml` because the stage-2 translated channel layout (S2-L3) moved the U.FL jacks (bias at du -15.47 / +6.78, anode at -10.38 / +11.87).", ""]
    L += ["## 3. Per-assembly detail", ""]
    for c in CABLES:
        L.append("### %s  %s" % (c["id"], c["title"]))
        L.append("")
        L.append("* **Length:** %d mm (%s). *Estimated from layout, confirm on first build.*" % (c["length_mm"], c["basis"]))
        L.append("* **Construction:** %s" % c["construction"])
        L.append("* **Shield / bonding:** %s" % c["shield"])
        L.append("* **Protection upstream:** %s" % c["protection"])
        L.append("* **Strain relief:** %s" % c["strain"])
        L.append("* **Labels:** both ends, `%s` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`)." % c["id"])
        if c["notes"]:
            L.append("* **Notes:** %s" % c["notes"])
        L.append("")
        L.append("| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for x in c["wires"]:
            net = x["net"] if x["net"] == x["to_net"] else "%s -> %s" % (x["net"], x["to_net"])
            L.append("| %s | %s.%s | %s.%s | %s | %s | %s | %s | %s | %s |" % (x["wid"], x["frm"], x["fp"], x["to"], x["tp"], net, x["awg"] or "coax", x["col"], x["ins"], x["pair"] or "-", x["len_mm"]))
        L.append("")
    # loop diagram
    L += ["## 4. The head interlock loop (potential-free pair): J1 pins 5 and 6", "",
          "```",
          "  chassis                     J1 cable (W-008 / W-101)                          head board                       head rail switches (D2HW-C201M, NC)",
          "  ------                      ------------------------                          ----------                       -----------------------------------",
          "  RR-CHS-MAIN                                                                   RR-HEAD-ACQ",
          "  J_HEAD1.5 HEAD_LOOP_OUT ==== J1R.5 -- J1P.5 ==== W-101.5 ====> J2001.5 ----+",
          "     (source: ~chassis loop sense)                                              |",
          "                                                                                +--> J2002.1 --[ RAIL-F  COM-NC ]--> J2002.2 = LOOP_A",
          "                                                                                                                         |",
          "                                                                                +--> J2003.1 <-----------------------LOOP_A",
          "                                                                                     J2003.1 --[ RAIL-R  COM-NC ]--> J2003.2 = LOOP_B",
          "                                                                                                                         |",
          "                                                                                     J2004.1 <-----------------------LOOP_B",
          "                                                                                     J2004.1 --[ RAIL-L  COM-NC ]--> J2004.2 = LOOP_C",
          "                                                                                                                         |",
          "                                                                                                               R2019 1.00 kohm 0.1 %",
          "                                                                                                                         |",
          "  J_HEAD1.6 HEAD_LOOP_RET ==== J1R.6 -- J1P.6 ==== W-101.6 <==== J2001.6 <------------- HEAD_LOOP_RET ----------------+",
          "",
          "  Healthy = 0.6 .. 1.6 kohm (window comparator, contract); open = rail pressed or J1 unplugged; short < 0.6 kohm = wiring fault.",
          "  The pair shares no conductor with power or data. Shield and every other pin stay isolated from pins 5 and 6.",
          "  The J2002/3/4 pins 3 and 4 (zone read-back) are NOT wired, and the D2HW NO lead stays cut back: using the NO throw would tie the loop to head logic (CCR-HE-04).",
          "```", "",
          "The 1.00 kohm resistor is on the head board at the FAR end of the switch string (chassis_safety_chain.md fault #24): do not move it into the harness.", ""]
    L += heater_section()
    L += ["## 5. Unconnected connector pins", "", "(The complete list with reasons is also in `connectors.yaml: unconnected_pins`.)", "", "| Connector | Pin | Net | Reason |", "|---|---|---|---|"]
    for cid, p, net, why in un:
        L.append("| %s | %s | %s | %s |" % (cid, p, net, why))
    L.append("")
    open(os.path.join(HERE, "cables.md"), "w").write("\n".join(L) + "\n")
    return flags


def write_parts_status():
    """parts_status.md: every distinct part number with its verification status and where it is used."""
    by = collections.OrderedDict()
    for cid, c in CONN.items():
        for kind, mpn, st in (("fixed half", c["mpn"], c["mpn_status"]), ("mating half", c["mating"], c["mating_status"]), ("contacts", c["contacts"], c["mating_status"])):
            if mpn in ("-", "n/a", "") or str(mpn).startswith("n/a"):
                continue
            by.setdefault((mpn, kind, st), []).append(cid)
    L = ["# Part-number status (generated)", "", "GENERATED by `harness/build.py` (connector tables) and `hdata_parts.py` (the rest). Status words: \"verified (not flagged in source)\" means only that no source flags the number as recalled; it was NOT checked against a manufacturer document. UNVERIFIED = recalled/unconfirmed. TBD / \"no part number in any source - to be selected\" = open.", "",
         "| Part number / description | Role | Status | Used at |", "|---|---|---|---|"]
    for (mpn, kind, st), ids in sorted(by.items(), key=lambda kv: (0 if kv[0][2].startswith("TBD") or "TBD" in kv[0][0] else 1 if kv[0][2] == "UNVERIFIED" else 2, kv[0][0])):
        tag = "TBD" if mpn.startswith(TBD) or st == "TBD" else ("UNVERIFIED" if "UNVERIFIED" in st else "verified")
        L.append("| %s | %s | %s | %s |" % (mpn.replace("|", "/"), kind, tag if tag != "verified" else st, ", ".join(ids[:12]) + (" ... (%d)" % len(ids) if len(ids) > 12 else "")))
    cnt = collections.Counter()
    for c in CONN.values():
        cnt["mpn " + ("TBD" if c["mpn"].startswith(TBD) or c["mpn_status"] == "TBD" else "UNVERIFIED" if "UNVERIFIED" in c["mpn_status"] else "verified")] += 1
    L += ["", "Connector rows by status of the fixed-half part: " + ", ".join("%s = %d" % kv for kv in sorted(cnt.items())) + "."]
    def tab(title, rows, hdr="| Item | Used at | Part number | Source document | Flag |\n|---|---|---|---|---|"):
        L.extend(["", "## " + title, "", hdr])
        for r in rows:
            L.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    L.extend(["", "## Web check of the highest-consequence items (what could and could not be verified)", "",
              "Outbound access was limited. Attempts made (three, no more): molex.com part page for 39-00-0038 (HTTP 503), JST GH catalogue PDF eGH.pdf (downloaded, no readable text: fonts missing), Anderson SBS50 product page (HTTP 404). **Not verified, therefore all still open:** M16 8-pole J1 contact wire range against 0.75 mm2 (heater pair); M12 A-coded 8-pole contact; Mini-Fit Jr and Micro-Fit terminal wire ranges and temperature range; JST GH temperature range for the -25 C objective (IB-08, recalled as -25..+85 C); Anderson SBS50 temperature range (parts.yaml -20..+105 C, UNVERIFIED). No recalled figure in this repository has been confirmed by the harness engineer.", ""])
    tab("Cables and wire", hp.CABLES)
    tab("Contacts, housings, splices", hp.CONTACTS)
    tab("Protection devices", hp.PROTECT)
    tab("Devices", hp.DEVICES)
    tab("Tools (no source names any tool or tool part number)", [(a, b, hp.NONE, "none", "TBD") for a, b in hp.TOOLS])
    tab("Consumables", [(a, b, hp.NONE, "none", "TBD") for a, b in hp.CONSUMABLES])
    open(os.path.join(HERE, "parts_status.md"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    write_parts_status()
    un = write_connectors()
    write_csv()
    write_views()
    fl = write_cables_md(un)
    print("connectors %d, cables %d, wires %d, unconnected pins %d, flagged lengths %d" % (len(CONN), len(CABLES), sum(len(c["wires"]) for c in CABLES), len(un), len(fl)))
    for f in fl:
        print("  flag", f)
    bad = [u for u in un if u[3].startswith("NOT WIRED")]
    for b in bad:
        print("  UNDECIDED:", b)
