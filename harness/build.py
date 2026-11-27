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
    dict(a="SET_CAP", b="K1_SET", via="REARM-DEV NO 1", why="latch set contact (momentary)"),
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
           "CHS.W1": "DNP wire pads of the on-board clamp circuit: NO cable by decision (the board carries its own 2 x 9.1 ohm clamp resistors; no bolt-on 50 W part, IB-26 / IB-36)", "HEAD.J2401": "SWD pads (no component fitted): Tag-Connect cable only when programming", "HEAD.J2402": "debug UART service port", "HEAD.J2701": "monitor output test port: coax only on the bench",
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
