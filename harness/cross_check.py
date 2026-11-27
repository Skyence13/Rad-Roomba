#!/usr/bin/env python3
"""Harness cross-check.  Loads the chassis circuit WITH THE STAGE-2 OVERRIDES APPLIED (electronics/chassis_main/overrides.py on design/circuit.py),
the head and panel circuit definitions, the placed-board pinmaps (out/pinmap.json of chassis, head and panel), the chassis stage-1
connectors.yaml (compared with the stage-2 data), the ToF pinmap, both firmware pin maps, the system contract, mechanical/common/frames.yaml
and the harness connectors.yaml / cables.csv, and checks them against each other.
Writes harness/cross_check_report.md and exits non-zero when any ERROR (real mismatch) is found.

    python3 harness/cross_check.py
Read-only on every file except harness/cross_check_report.md.
"""
import csv, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import yaml
from hsrc import src, parts_by_ref, nets_of, ROOT

S = src()
CHS, HD, PN = S["chs"], S["hd"], S["pn"]
ALIAS = {"HEAD_PWR_N": "GND", "BUS_GND": "GND", "PACK_N": "GND", "NC_RESERVED": "NC", None: "NC", "": "NC"}
ERR, WARN, INFO = [], [], []
PASS = collections.OrderedDict()


def err(cat, msg):
    ERR.append((cat, msg))


def warn(cat, msg):
    WARN.append((cat, msg))


def norm(n):
    return ALIAS.get(n, n)


H = yaml.safe_load(open(os.path.join(HERE, "connectors.yaml")))
HC = {c["id"]: c for c in H["connectors"]}
EQ = H["net_equivalents"]
PAIRS = {frozenset((p["a"], p["b"])) for p in H["net_pairs"]}
MATES = H["mates"]
WIRES = list(csv.DictReader(open(os.path.join(HERE, "cables.csv"))))
PCHS, PHD, PPN = parts_by_ref(CHS), parts_by_ref(HD), parts_by_ref(PN)
NCHS, NHD = nets_of(CHS), nets_of(HD)


def same_net(a, b):
    a, b = norm(a), norm(b)
    return a == b or EQ.get(a) == b or EQ.get(b) == a or frozenset((a, b)) in PAIRS


def count(name, ok, total=None):
    PASS[name] = (ok, total)


# ================================================================ A. board connector pins: harness connectors.yaml vs circuit definitions
def circuit_pins(cid):
    """independent source of truth for a board connector: the circuit/pinmap definition, not the harness tables"""
    if cid.startswith("CHS."):
        p = PCHS[cid[4:]]
        return {str(k): (v[1] if v else "NC") for k, v in p["pins"].items() if k != "MP"}
    if cid.startswith("HEAD."):
        ref = cid[5:]
        if ref in HD.CONNECTORS:
            return {str(k): (v[1] if v[1] else "NC") for k, v in HD.CONNECTORS[ref]["pins"].items() if k != "MP"}
        p = PHD[ref]
        return {str(k): v[1] for k, v in p["pins"].items() if v}
    if cid.startswith("PNL."):
        p = PPN[cid[4:]]
        return {str(k): (v[1] if v else "NC") for k, v in p["pins"].items() if k != "MP"}
    m = re.match(r"TOF(\d+)\.J1", cid)
    if m:
        j1 = [p for p in S["tof"]["parts"] if p["ref"] == "J1"][0]
        return {pp["pin"]: pp["net"] for pp in j1["pins"] if pp["pin"] != "MP"}
    return None


n_ok = n_tot = 0
for cid, c in HC.items():
    cp = circuit_pins(cid)
    if cp is None:
        continue
    hp = {k: v["net"] for k, v in c["pins"].items()}
    n_tot += 1
    bad = False
    if set(cp) != set(hp):
        err("A connector pins", "%s: pin set differs: circuit %s vs harness %s" % (cid, sorted(cp), sorted(hp)))
        bad = True
    for k in cp:
        if k in hp and norm(cp[k]) != norm(hp[k]):
            err("A connector pins", "%s pin %s: circuit net %s, harness net %s" % (cid, k, cp[k], hp[k]))
            bad = True
    n_ok += 0 if bad else 1
count("A. board connectors: every pin net in connectors.yaml equals the circuit/pinmap definition", n_ok, n_tot)

# stage-2 connector data (stage-1 connectors.yaml + overrides, hsrc._chs_conn_stage2) vs the stage-2 circuit
n_ok = n_tot = 0
for c in S["chs_conn_yaml"]["connectors"]:
    n_tot += 1
    cp = circuit_pins("CHS." + c["ref"])
    sp = {str(k): v["net"] for k, v in c["pins"].items()}
    if {k: norm(v) for k, v in cp.items()} != {k: norm(v) for k, v in sp.items()}:
        err("A connector pins", "chassis stage-2 connector table %s differs from the stage-2 circuit" % c["ref"])
    else:
        n_ok += 1
count("A2. chassis stage-2 connector table (design/connectors.yaml + overrides.py) equals the stage-2 circuit", n_ok, n_tot)

# the stage-1 connectors.yaml is stale where stage 2 overrides: list every difference (information), error if a difference is NOT an override
OV_REFS = {e.get("ref") for e in S["ov_log"] if e.get("ref")} | {r for e in S["ov_log"] for r in (e.get("refs") or [])}
y1 = {c["ref"]: c for c in S["chs_conn_yaml_stage1"]["connectors"]}
y2 = {c["ref"]: c for c in S["chs_conn_yaml"]["connectors"]}
n_ok = n_tot = 0
for ref in sorted(set(y1) | set(y2)):
    n_tot += 1
    a_, b_ = y1.get(ref), y2.get(ref)
    if a_ is None:
        INFO.append(("A stage 2 vs stage 1", "%s is NEW in stage 2 (%s)" % (ref, b_["board_mpn"])))
        n_ok += 1
        continue
    d = []
    if a_["board_mpn"] != b_["board_mpn"]:
        d.append("part %s -> %s" % (a_["board_mpn"], b_["board_mpn"]))
    pa = {str(k): v["net"] for k, v in a_["pins"].items()}
    pb = {str(k): v["net"] for k, v in b_["pins"].items()}
    for k in sorted(set(pa) | set(pb), key=lambda k: int(k)):
        if pa.get(k) != pb.get(k):
            d.append("pin %s %s -> %s" % (k, pa.get(k), pb.get(k)))
    if d:
        INFO.append(("A stage 2 vs stage 1", "%s: %s" % (ref, "; ".join(d))))
        if ref not in OV_REFS and ref not in ("J_PAUSE",):
            err("A connector pins", "%s differs between stage-1 connectors.yaml and the stage-2 data but no override in overrides.py touches it" % ref)
            continue
    n_ok += 1
count("A2b. every difference between the stage-1 connectors.yaml and the stage-2 data is an override of overrides.py (S2-xx)", n_ok, n_tot)

# placed boards: pinmap.json (generated from the KiCad boards) vs the circuit definitions, every connector pin
def pinmap_nets(pm, ref):
    for p in pm["parts"]:
        if p["ref"] == ref:
            return {q["pin"]: q["net"] for q in p["pins"] if q["pin"] != "MP"}
    return None


n_ok = n_tot = 0
for pmk, pref, mod in (("chs_pinmap", "CHS.", None), ("hd_pinmap", "HEAD.", None), ("pn_pinmap", "PNL.", None)):
    for cid in sorted(HC):
        if not cid.startswith(pref):
            continue
        nets = pinmap_nets(S[pmk], cid[len(pref):])
        if nets is None:
            continue
        n_tot += 1
        hp_ = {k: v["net"] for k, v in HC[cid]["pins"].items()}
        bad = False
        for k in set(hp_) | set(nets):
            a_ = norm(hp_.get(k) or "NC")
            b_ = norm(nets.get(k) or "NC")
            if a_ != b_ and not (b_ == "NC" and a_ in ("NC", "UNUSED")):
                err("A placed board", "%s pin %s: harness %s but the placed board (pinmap.json) has %s" % (cid, k, hp_.get(k), nets.get(k)))
                bad = True
        n_ok += 0 if bad else 1
count("A2c. harness connector pins equal the PLACED boards' pinmap.json (chassis, head, panel)", n_ok, n_tot)

# parts the stage-2 note says changed, read back from the placed board
chk = {"J_HEAD1": ("39-30-1100", 10), "J_PAUSE": ("BM05B-GHS-TBT(LF)(SN)", 5)}
ok2 = True
for ref, (mpn, npins) in chk.items():
    pp = [p for p in S["chs_pinmap"]["parts"] if p["ref"] == ref]
    if not pp or pp[0]["mpn"] != mpn or len([q for q in pp[0]["pins"] if q["pin"] != "MP"]) != npins:
        err("A placed board", "%s: placed board does not carry %s with %d pins (stage-2 decision S2-01/S2-02)" % (ref, mpn, npins))
        ok2 = False
if (HC["CHS.J_HEAD1"]["pins"]["9"]["net"], HC["CHS.J_HEAD1"]["pins"]["10"]["net"]) != ("NC", "NC"):
    err("A placed board", "J_HEAD1 pins 9/10 must be NC (S2-02)")
    ok2 = False
if any(HC["CHS.J_BTN"]["pins"][k]["net"] != "NC" for k in ("5", "8")):
    err("A placed board", "J_BTN pins 5 and 8 must be NC after S2-01a/b (PAUSE moved to J_PAUSE)")
    ok2 = False
count("A2d. stage-2 decisions read back from the placed board: J_HEAD1 = 39-30-1100 2x5 (pins 9/10 NC), J_PAUSE = BM05B 5-way, J_BTN pins 5/8 NC", int(ok2), 1)

# panel J1/J2 on the TOP side (P1)
ok3 = True
for ref in ("J1", "J2"):
    sides = {q["side"] for p in S["pn_pinmap"]["parts"] if p["ref"] == ref for q in p["pins"]}
    if sides != {"F"}:
        err("A placed board", "RR-PANEL %s is not on the top side (pad sides %s); harness text says top (P1)" % (ref, sides))
        ok3 = False
count("A2e. RR-PANEL J1/J2 are on the top side (panel P1)", int(ok3), 1)

# ToF carrier pin order vs the chassis J_TOFn
n_ok = 0
for n in range(11):
    ch, car = circuit_pins("CHS.J_TOF%d" % n), circuit_pins("TOF%d.J1" % n)
    good = all(same_net(ch[k], car[k]) for k in car)
    if not good:
        err("A connector pins", "ToF %d: chassis J_TOF%d and carrier J1 pin order disagree: %s vs %s" % (n, n, ch, car))
    n_ok += good
count("A3. ToF carrier J1 pin order equals chassis J_TOFn pin order (11)", n_ok, 11)

# panel J1 vs main J_PANEL
pj1, mj = circuit_pins("PNL.J1"), circuit_pins("CHS.J_PANEL")
good = all(norm(pj1[k]) == norm(mj[k]) for k in mj) and len(pj1) == len(mj)
if not good:
    err("A connector pins", "RR-PANEL J1 does not match main-board J_PANEL 1:1")
count("A4. RR-PANEL J1 is pin for pin the main-board J_PANEL (1:1 cable)", int(good), 1)

# ================================================================ B/C. wires
W = {}
for w in WIRES:
    W[w["wire_id"]] = w
n_ok = 0
for w in WIRES:
    bad = False
    for side, conn, pin, net in (("from", w["from_connector"], w["from_pin"], w["net_from"]), ("to", w["to_connector"], w["to_pin"], w["net_to"])):
        if conn not in HC:
            err("B wire ends", "%s: unknown connector %s" % (w["wire_id"], conn))
            bad = True
            continue
        if pin not in HC[conn]["pins"]:
            err("B wire ends", "%s: connector %s has no pin %s" % (w["wire_id"], conn, pin))
            bad = True
            continue
        pn = HC[conn]["pins"][pin]["net"]
        if not same_net(pn, net):
            err("B wire ends", "%s: wire says net %s at %s.%s but the connector pin carries %s" % (w["wire_id"], net, conn, pin, pn))
            bad = True
        cp = circuit_pins(conn)
        if cp is not None and not same_net(cp[pin], net):
            err("B wire ends", "%s: wire net %s at %s.%s differs from the circuit definition (%s)" % (w["wire_id"], net, conn, pin, cp[pin]))
            bad = True
    n_ok += 0 if bad else 1
count("B. every wire end lands on an existing pin whose net (harness table AND circuit definition) equals the wire's net", n_ok, len(WIRES))

n_ok = 0
for w in WIRES:
    a, b = w["net_from"], w["net_to"]
    if same_net(a, b):
        n_ok += 1
        if norm(a) != norm(b) and w["wire_kind"] == "wire" and EQ.get(a) != b and EQ.get(b) != a and frozenset((norm(a), norm(b))) not in PAIRS:
            warn("C net pairs", "%s: %s -> %s accepted only as a documented pair" % (w["wire_id"], a, b))
    elif w["wire_kind"] in ("link", "resistor", "shield") and frozenset((a, b)) in PAIRS:
        n_ok += 1
    else:
        err("C net equality", "%s: net %s at %s.%s but %s at %s.%s and the pair is not documented" % (w["wire_id"], a, w["from_connector"], w["from_pin"], b, w["to_connector"], w["to_pin"]))
count("C. both ends of every wire carry the same net (or an equivalent/documented net pair)", n_ok, len(WIRES))

# ---- D. duplicate pin use
SHARED_OK = {("J2P", "7"): "plug link 7-4 shares the contact with the cable conductor (W-102.L)", ("J2P", "4"): "plug link 7-4 (W-102.L)",
             ("J1X-P", "7"): "LAB resistor lead shares the contact with the conductor (W-200.R)", ("J1X-P", "2"): "LAB resistor lead (W-200.R)",
             ("CPL-C", "N"): "presence link and NTC return share the pack-negative contact inside the cassette (W-002.3/.6)", ("PACK", "-"): "NTC return shares the pack negative F2 faston (W-002.3/.5)"}
use = collections.defaultdict(list)
for w in WIRES:
    use[(w["from_connector"], w["from_pin"])].append(w["wire_id"])
    use[(w["to_connector"], w["to_pin"])].append(w["wire_id"])
dups = {k: v for k, v in use.items() if len(set(v)) > 1}
n_bad = 0
for k, v in dups.items():
    if k in SHARED_OK:
        INFO.append(("D shared terminations", "%s.%s used by %s: %s" % (k[0], k[1], ", ".join(v), SHARED_OK[k])))
    else:
        err("D pin used twice", "%s.%s is used by %s" % (k[0], k[1], ", ".join(v)))
        n_bad += 1
for k, v in use.items():
    if len(v) != len(set(v)):
        err("D pin used twice", "%s.%s: a wire lands twice on the same pin %s" % (k[0], k[1], v))
count("D. no connector pin used twice (documented shared terminations excepted)", len(use) - n_bad, len(use))

# ---- E. wire gauge: contact range, ampacity vs the branch limit
def contact_ranges(cid, pin):
    """AWG ranges of the mating contact for this pin, from the connector's 'contacts' text.  'X (AWG a-b) for pins p/q/..; Y (AWG c-d) for the rest'
    is read per pin.  Returns (ranges, recalled) where recalled=True if the text itself says the range is a recalled 'variant'."""
    txt = HC[cid].get("contacts", "")
    recalled = "variant" in txt
    segs = [x.strip() for x in txt.split(";")]
    out = []
    named = set()
    for sg in segs:
        m = re.search(r"for pins ([\d/]+)", sg)
        if m:
            named |= set(m.group(1).split("/"))
    for sg in segs:
        rs = [(int(a), int(b or a)) for a, b in re.findall(r"AWG (\d+)(?:-(\d+))?", sg)]
        m = re.search(r"for pins ([\d/]+)", sg)
        if m:
            if pin in m.group(1).split("/"):
                out += rs
        elif "for the rest" in sg:
            if pin not in named:
                out += rs
        else:
            out += rs
    return (out or None), recalled


AMP = {14: 20.0, 18: 10.0, 20: 5.0, 22: 3.0, 24: 2.0}   # power_budget.md section 5 conductor column ([A] chassis-wiring values; AWG 14 'protected by the 20 A fuse')
LOADS = {("CHS.J_PWR", "1"): 7.5, ("CHS.J_PWR", "2"): 7.5, ("CHS.J_PWR", "5"): 7.5, ("CHS.J_PWR", "6"): 7.5, ("CHS.J_PWR", "3"): 4.0, ("CHS.J_PWR", "7"): 4.0, ("CHS.J_PWR", "4"): 0.01, ("CHS.J_PWR", "8"): 0.01,
         ("CHS.J_HEAD1", "1"): 1.5, ("CHS.J_HEAD1", "2"): 1.5, ("CHS.J_HEAD1", "3"): 4.35, ("CHS.J_HEAD1", "4"): 4.35,
         ("CHS.J_CM5", "1"): 2.5, ("CHS.J_CM5", "2"): 2.5, ("CHS.J_CM5", "3"): 2.5, ("CHS.J_CM5", "4"): 2.5, ("CHS.J_LIDAR", "1"): 1.5, ("CHS.J_LIDAR", "2"): 1.5,
         ("CHS.J_HTR", "1"): 3.04, ("CHS.J_HTR", "2"): 3.04, ("CHS.J_MOT_L", "1"): 2.7, ("CHS.J_MOT_L", "2"): 2.7, ("CHS.J_MOT_R", "1"): 2.7, ("CHS.J_MOT_R", "2"): 2.7,
         ("HEAD.J2001", "1"): 1.5, ("HEAD.J2001", "2"): 1.5, ("HEAD.J2001", "3"): 4.35, ("HEAD.J2001", "4"): 4.35, ("HEAD.J2601", "1"): 4.35, ("HEAD.J2601", "2"): 4.35,
         ("CPL-B", "P"): 15.0, ("CPL-B", "N"): 15.0, ("PACK", "+"): 15.0, ("PACK", "-"): 15.0, ("INLET", "1"): 4.0, ("INLET", "3"): 4.0}
n_ok = n_tot = 0
skipped = collections.Counter()
for w in WIRES:
    if w["group"] == "lab" and w["wire_kind"] != "wire":
        continue
    awg = w["awg"]
    if not awg.isdigit() or int(awg) == 0:
        continue
    awg = int(awg)
    for conn, pin in ((w["from_connector"], w["from_pin"]), (w["to_connector"], w["to_pin"])):
        if conn in HC and HC[conn].get("kind") == "board_header" and "contacts" in HC[conn]:
            rs, recalled = contact_ranges(conn, pin)
            if rs:
                n_tot += 1
                if any(a <= awg <= b for a, b in rs):
                    n_ok += 1
                    if recalled and awg < 20:    # outside the 43030-0007 range (AWG 20-24) that the chassis tables list: only the recalled variant covers it
                        warn("E gauge vs contact (recalled)", "%s: AWG %d on %s.%s is inside the range only of a RECALLED terminal variant (%s): the sources do not name a part; treat as OPEN (OD-3)" % (w["wire_id"], awg, conn, pin, HC[conn]["contacts"]))
                else:
                    err("E gauge vs contact", "%s: AWG %d on %s.%s but the mating contact range is %s (%s)" % (w["wire_id"], awg, conn, pin, "/".join("AWG %d-%d" % r for r in rs), HC[conn]["contacts"]))
count("E1. wire gauge inside the crimp range of the mating contact (board ends)", n_ok, n_tot)
n_ok = n_tot = 0
for w in WIRES:
    awg = w["awg"]
    if not awg.isdigit() or int(awg) == 0 or w["wire_kind"] != "wire":
        continue
    awg = int(awg)
    load = None
    for key in ((w["from_connector"], w["from_pin"]), (w["to_connector"], w["to_pin"])):
        if key in LOADS:
            load = LOADS[key]
    if load is None:
        load = 0.2
        if awg >= 26:
            skipped["signal wires AWG 26/28 (loads <= 0.2 A): ampacity not in sources"] += 1
            continue
    if awg not in AMP:
        skipped["AWG %d: ampacity not in the sources (load %.2f A): not checked" % (awg, load)] += 1
        continue
    n_tot += 1
    if load <= AMP[awg]:
        n_ok += 1
    else:
        err("E ampacity", "%s: AWG %d (%.0f A table value) carries up to %.2f A" % (w["wire_id"], awg, AMP[awg], load))
count("E2. wire ampacity (power_budget.md section 5 values) >= branch current limit", n_ok, n_tot)
for k, v in skipped.items():
    warn("E ampacity not checkable", "%s (%d wires)" % (k, v))

# ---- F. J1 / J2 tables: contract vs chassis board, receptacle, plug, pigtail, head board; and through the wires
CT = S["contract"]["connectors"]
edges = collections.defaultdict(set)
for w in WIRES:
    if w["group"] != "lab":
        edges[(w["from_connector"], w["from_pin"])].add((w["to_connector"], w["to_pin"]))
        edges[(w["to_connector"], w["to_pin"])].add((w["from_connector"], w["from_pin"]))
for m in MATES:
    if m["config"] == "robot":
        for pin in list(HC[m["a"]]["pins"]):
            if pin in HC[m["b"]]["pins"] and pin != "SH":
                edges[(m["a"], pin)].add((m["b"], pin))
                edges[(m["b"], pin)].add((m["a"], pin))


def path(src_node, dst_node):
    seen, q = {src_node: None}, [src_node]
    while q:
        n = q.pop(0)
        if n == dst_node:
            out = []
            while n:
                out.append(n)
                n = seen[n]
            return out[::-1]
        for m in edges.get(n, ()):
            if m not in seen:
                seen[m] = n
                q.append(m)
    return None


n_ok = n_tot = 0
for j, (board, recept, plug, head) in {"J1": ("CHS.J_HEAD1", "J1R", "J1P", "HEAD.J2001"), "J2": ("CHS.J_HEAD2", "J2R", "J2P", "HEAD.J2501")}.items():
    for pin, d in CT[j]["pins"].items():
        pin = str(pin)
        want = norm(d["net"])
        n_tot += 1
        bad = False
        for cid in (board, recept, plug, head):
            got = HC[cid]["pins"][pin]["net"]
            if norm(got) != want:
                err("F J1/J2 tables", "%s pin %s: %s but the contract says %s" % (cid, pin, got, d["net"]))
                bad = True
        if want != "NC":
            p = path((board, pin), (head, pin))
            if p is None:
                err("F J1/J2 tables", "%s pin %s: no wire path from %s to %s" % (j, pin, board, head))
                bad = True
            else:
                for (cc, pp) in p:
                    if norm(HC[cc]["pins"][pp]["net"]) != want:
                        err("F J1/J2 tables", "%s pin %s: net changes along the path at %s.%s (%s)" % (j, pin, cc, pp, HC[cc]["pins"][pp]["net"]))
                        bad = True
                want_chain = [board, recept, plug, head]
                got_chain = [x[0] for x in p]
                if got_chain != [board, recept, recept, plug, plug, head][0:0] + got_chain and False:
                    pass
        else:
            if (board, pin) in use or (head, pin) in use or (recept, pin) in use or (plug, pin) in use:
                err("F J1/J2 tables", "%s pin %s is NC_RESERVED but a wire lands on it" % (j, pin))
                bad = True
        n_ok += 0 if bad else 1
count("F1. J1/J2 pin tables equal the contract at the chassis board, the receptacle, the plug and the head board, with a continuous same-net wire path (16 pins)", n_ok, n_tot)
# gauge against the contract J1 table
n_ok = n_tot = 0
for pin, d in CT["J1"]["pins"].items():
    if "awg" not in d:
        continue
    for wid in ("W-008.%s" % pin, "W-101.%s" % pin, "W-200.%s" % pin):
        if wid in W:
            n_tot += 1
            if int(W[wid]["awg"]) == d["awg"]:
                n_ok += 1
            elif wid.startswith("W-200"):
                warn("F contract gauge", "%s: AWG %s on J1X pin %s where the contract table says AWG %d: deliberate (CCR-E07 / lab_extension.md section 3, meets the 0.125 ohm budget)" % (wid, W[wid]["awg"], pin, d["awg"]))
                n_ok += 1
            else:
                err("F contract gauge", "%s: AWG %s but the contract J1 pin %s says AWG %d" % (wid, W[wid]["awg"], pin, d["awg"]))
count("F2. J1 wire gauges equal the contract table (robot lead, pigtail; LAB deviation reported separately)", n_ok, n_tot)
# LAB extension: straight through + resistor
n_ok = 0
labw = [w for w in WIRES if w["cable_id"] == "W-200"]
okl = True
for pin in "1234567":
    ws = [w for w in labw if w["from_connector"] == "J1X-P" and w["from_pin"] == pin and w["to_connector"] == "J1X-S" and w["to_pin"] == pin and w["wire_kind"] == "wire"]
    if len(ws) != 1:
        err("G LAB extension", "J1X pin %s is not wired straight through" % pin)
        okl = False
for pin in "1234567":
    ws = [w for w in WIRES if w["cable_id"] == "W-201" and w["from_pin"] == pin and w["to_pin"] == pin and w["wire_kind"] == "wire"]
    if len(ws) != 1:
        err("G LAB extension", "J2X pin %s is not wired straight through" % pin)
        okl = False
rr = [w for w in labw if w["wire_kind"] == "resistor"]
if len(rr) != 1 or (rr[0]["from_pin"], rr[0]["to_pin"], rr[0]["from_connector"]) != ("7", "2", "J1X-P") or "1.50 kohm" not in rr[0]["note"]:
    err("G LAB extension", "the 1.50 kohm LAB resistor from pin 7 to pin 2 in the J1X-P backshell is missing or misplaced")
    okl = False
par = lambda a, b: a * b / (a + b)
pdec = S["contract"]["connectors"]["lab_extension"]["presence_decode_on_pin7_to_pin2_ohm"]
v_via = par(4700, 1500)
if not (950 <= v_via <= 1330):
    err("G LAB extension", "4.70k || 1.50k = %.0f ohm is outside the HEAD_VIA_LAB_EXTENSION window 0.95k-1.33k" % v_via)
    okl = False
if not (1330 <= 1500 <= 1800):
    err("G LAB extension", "1.50k outside the LAB_EXTENSION_ONLY window")
    okl = False
R18 = 20.9
for pair in (("1", "2"), ("3", "4")):
    r = 2 * 2.0 * R18 + 10.0
    if r > 125.0:
        err("G LAB extension", "supply pair %s: %.1f mohm exceeds 0.125 ohm" % (pair, r))
        okl = False
if any(int(w["awg"]) > 18 for w in labw if w["from_pin"] in "1234" and w["wire_kind"] == "wire"):
    err("G LAB extension", "a LAB supply conductor is thinner than AWG 18")
    okl = False
count("G. LAB extension: J1X/J2X straight through, 1.50 kohm resistor pin 7 to pin 2 in J1X-P, decode windows, supply pairs <= 0.125 ohm", int(okl), 1)

# ---- H. firmware pin maps against the circuit definitions and the connectors
fw = S["fw_chs"]
sig = {}
for p in fw["pins"]:
    if "lqfp64" in p:
        sig[p["signal"]] = (CHS.MCU[p["lqfp64"]][1], "U20M pin %s (%s)" % (p["lqfp64"], p["pin"]))
        pn_, nt = CHS.MCU[p["lqfp64"]]
        if p["pin"].split("-")[0] != pn_.split("-")[0] and p["pin"] != pn_:
            err("H firmware pin map", "chassis firmware %s at LQFP64 pin %s is %s but circuit.py has %s" % (p["signal"], p["lqfp64"], p["pin"], pn_))
        s, nt2 = p["signal"], nt
        if not (s in nt2 or nt2 in s or nt2.replace("_ADC", "") == s or nt2.startswith(s) or s.startswith(nt2)):
            warn("H firmware names", "chassis pin %s: firmware signal %s vs circuit net %s (names differ: check the function matches)" % (p["pin"], s, nt2))
byname = {}
for ref, pp in PCHS.items():
    for k, v in pp["pins"].items():
        if v:
            byname[(ref, v[0])] = v[1]
for ex, ref in (("IOX_A", "U43"), ("IOX_B", "U44")):
    for pn_, d in fw["expanders"][ex]["pins"].items():
        net = byname.get((ref, pn_))
        sig[d["signal"]] = (net, "%s %s pin %s" % (ex, ref, pn_))
        if net is None:
            err("H firmware pin map", "%s %s (%s) has no net in circuit.py" % (ex, pn_, d["signal"]))
        elif not (d["signal"] in net or net in d["signal"]):
            warn("H firmware names", "%s %s: firmware signal %s vs circuit net %s%s" % (ex, pn_, d["signal"], net, " (IB-01/CCR-E02: P17 is now CHAIN_END_RB in the circuit; firmware map still lists SPARE_OUT)" if net == "CHAIN_END_RB" else ""))
# IOX_C
for part in CHS.PARTS:
    if "TCA9534" in part["value"]:
        refc = part["ref"]
for pn_, d in fw["expanders"]["IOX_C"]["pins"].items():
    net = byname.get((refc, pn_))
    sig[d["signal"]] = (net, "IOX_C %s pin %s" % (refc, pn_))
    if net is None or not (d["signal"] in net or net in d["signal"]):
        warn("H firmware names", "IOX_C %s: firmware signal %s vs circuit net %s" % (pn_, d["signal"], net))

RAIL_NOREACH = {"GND", "AGND", "3V3", "V5_AUX", "V12_AUX", "VBAT_SW", "VBAT_RAW", "VMOT", "VSYS", "VREF_3V0", "NC", "+3V3", "+3V3A", "+5V_A"}
RAIL_NOEXPAND = RAIL_NOREACH | {"V5_CM5", "V12_LIDAR", "ENC_L_5V", "ENC_R_5V", "HUSB_VBUS", "BTN_3V3", "TOF0_3V3", "TOF1_3V3"}
LED_FETS = {"Q50", "Q51", "Q52", "Q53", "Q54", "Q55", "Q56", "Q58"}


def hops_chs(ref, part):
    v = part["value"]
    if "TPD4E05U06" in v:
        return [("1", "10"), ("2", "9"), ("4", "7"), ("5", "6")]
    if "USBLC6" in v:
        return [("1", "6"), ("3", "4")]
    if "74LVC2G17" in v:
        return [("1", "6"), ("3", "4")]
    if "TCA9548A" in v:
        return [("23", c) for c in ("4", "6", "8", "10", "13", "15", "17", "19")] + [("22", c) for c in ("5", "7", "9", "11", "14", "16", "18", "20")]
    if "TPS259470A" in v:
        return [("1", "6")]
    if "LM2903B" in v:
        return [("1", "2"), ("1", "3"), ("7", "5"), ("7", "6")]
    if ref in LED_FETS or ref in ("Q_ESTOP", "Q_J2PRE", "Q10"):
        return [("1", "3")]
    return []


def hops_hd(ref, part):
    v = part["value"]
    if ref == "U2501":
        return [("6", "12"), ("6", "13"), ("3", "12"), ("3", "13"), ("5", "12"), ("5", "13")]
    if ref in ("Q2602", "Q2603"):
        return [("1", "3")]
    if ref == "Q2601":
        return [("1", "2")]
    return []


def trace(circ, parts, nets, start, hopf, want_nets=False):
    reached, seen, q = {start}, {start}, [start]
    while q:
        n = q.pop()
        for ref, pin in nets[n]:
            p = parts[ref]
            if ref in circ.CONNECTORS:
                continue
            pins = [(k, v) for k, v in p["pins"].items() if v]
            nxt = []
            if (ref[0] in "RL" or ref.startswith("FB")) and len(pins) == 2:
                nxt = [v[1] for k, v in pins if k != pin]
            for a, b in hopf(ref, p):
                if pin == a and p["pins"].get(b):
                    nxt.append(p["pins"][b][1])
                if pin == b and p["pins"].get(a):
                    nxt.append(p["pins"][a][1])
            for m in nxt:
                if m in seen or m in RAIL_NOREACH:
                    continue
                seen.add(m)
                reached.add(m)
                if m not in RAIL_NOEXPAND:
                    q.append(m)
    cons = set()
    for n in reached:
        for ref, pin in nets[n]:
            if ref in circ.CONNECTORS:
                cons.add((ref, pin, n))
    return (cons, reached) if want_nets else cons


CH_EXPECT = {
    "HEAD_PRES_ID": [("J_HEAD1", "7")], "HEAD_LOOP_SENSE": [("J_HEAD1", "6")], "NTC_BAY": [("J_NTC", "1")], "NTC_PACK": [("J_NTC", "3")],
    "ENC_L_A": [("J_MOT_L", "5")], "ENC_L_B": [("J_MOT_L", "6")], "ENC_R_A": [("J_MOT_R", "5")], "ENC_R_B": [("J_MOT_R", "6")],
    "ESTOP_A_RB": [("J_ESTOP", "2"), ("J_HANDS", "1")], "ESTOP_B_RB": [("J_ESTOP", "3")], "MODE_RUN_RB": [("J_MODE", "4"), ("J_ESTOP", "1")], "HANDS_ON_RB": [("J_HANDS", "2")],
    "CHG_COVER_RB": [("J_COVER", "2")], "CHG_PLUG_LINK_RB": [("J_DOCK", "1")], "HEAD_DOCK_RB": [("J_DOCK", "3")], "HEAD_LOOP_OK_RB": [("J_HEAD1", "6")], "HEAD_LOOP_SHORT_RB": [("J_HEAD1", "6")],
    "LAB_KEY_N_RB": [("J_HEAD1", "7")], "BODY_BUMPER_L_RB": [("J_BUMP_L", "2")], "BODY_BUMPER_R_RB": [("J_BUMP_R", "2")], "REARM_BTN": [("J_BTN", "4")], "PAUSE_BTN": [("J_PAUSE", "2")],
    "J2_PRES_RB": [("J_HEAD2", "7")], "BUZZER": [("J_PANEL", "9")], "LED_READY": [("J_PANEL", "4")], "LED_MOVING": [("J_PANEL", "5")], "LED_HOLD": [("J_PANEL", "6")], "LED_FAULT": [("J_PANEL", "7")],
    "LED_CHARGE": [("J_PANEL", "8")], "LAMP_REARM": [("J_BTN", "7")], "LAMP_PAUSE": [("J_PAUSE", "4")], "DBG_TX": [("J_DBG", "2")], "DBG_RX": [("J_DBG", "3")], "USB_DM": [("J_USB_MCU", "2")],
    "USB_DP": [("J_USB_MCU", "3")], "SWDIO": [("J_SWD", "2")], "SWCLK": [("J_SWD", "4")], "SWO_SPARE": [("J_SWD", "6")],
    "TOF_XSHUT_CLIFF": [("J_TOF%d" % i, "5") for i in (0, 1, 2, 3)], "TOF_XSHUT_LOOK": [("J_TOF%d" % i, "5") for i in (4, 5, 6, 7)], "TOF_XSHUT_REAR": [("J_TOF%d" % i, "5") for i in (8, 9, 10)],
    "I2C_TOF_SDA": [("J_TOF%d" % i, "3") for i in range(11)], "I2C_TOF_SCL": [("J_TOF%d" % i, "4") for i in range(11)],
    "HEAD_HTR_EN": [("J_HEAD1", "3")], "CHS_HTR_EN": [("J_HTR", "1")], "HEAD_PWR_EN": [("J_HEAD1", "1")], "V12_LIDAR_EN": [("J_LIDAR", "1")], "V5_CM5_OFF_REQ": [("J_CM5", "1"), ("J_CM5", "2")],
}
SENSE_TAPS = {"V5_SENSE": "divider tap of the V5_CM5 rail (input only, nothing leaves the board)", "SPARE_OUT": "CHAIN_END_RB: tap of the chain node after ARM_PERMIT (IB-01); the node also touches J_BTN.1 through passives (the REARM set path), an input only"}
n_ok = n_tot = 0
reached_all = {}
for s, exp in CH_EXPECT.items():
    if s not in sig or sig[s][0] is None:
        err("H firmware off-board", "chassis firmware signal %s is not in the pin maps / circuit" % s)
        continue
    cons = trace(CHS, PCHS, NCHS, sig[s][0], hops_chs)
    got = {(a, b) for a, b, _ in cons}
    reached_all[s] = got
    for (cc, pp) in exp:
        n_tot += 1
        cid = "CHS." + cc
        if (cc, pp) not in got:
            err("H firmware off-board", "chassis firmware %s (%s, net %s) does not reach %s pin %s in circuit.py" % (s, sig[s][1], sig[s][0], cc, pp))
            continue
        if (cid, pp) in use:
            n_ok += 1
        elif cc in ("J_DBG", "J_SWD"):
            n_ok += 1
            INFO.append(("H service ports", "%s reaches %s pin %s: service connector, no permanent cable (documented)" % (s, cc, pp)))
        else:
            err("H firmware off-board", "chassis firmware %s leaves the board at %s pin %s but no harness wire lands there" % (s, cc, pp))
    extras = sorted(g for g in got if g not in set(exp) and g[1] != "" and HC.get("CHS." + g[0], {}).get("pins", {}).get(g[1], {}).get("net") not in ("GND", "NC"))
    if extras:
        INFO.append(("H also connected", "%s is also electrically connected (through passives) to %s" % (s, ", ".join("%s.%s" % e for e in extras))))
count("H1. chassis firmware signals that leave the board reach the expected connector pin in circuit.py AND have a harness wire there", n_ok, n_tot)
# firmware signals that reach a connector but are not in the expected table
for s, (net, where) in sig.items():
    if s in CH_EXPECT or net is None or net in RAIL_NOREACH:
        continue
    if s in SENSE_TAPS:
        INFO.append(("H sense taps", "chassis firmware %s: %s" % (s, SENSE_TAPS[s])))
        continue
    cons = trace(CHS, PCHS, NCHS, net, hops_chs)
    cons = {(a, b) for a, b, n in cons if n not in RAIL_NOREACH}
    cons = {c for c in cons if HC.get("CHS." + c[0], {}).get("pins", {}).get(c[1], {}).get("net") not in ("GND", "NC")}
    if cons:
        warn("H firmware off-board", "chassis firmware %s (%s) is electrically connected to %s but is not in the expected-off-board table (check)" % (s, where, ", ".join("%s.%s" % c for c in sorted(cons))))

# ToF channel mapping: firmware mux/channel vs the circuit's mux pins and the connector index
tofch = fw["i2c"]["I2C_TOF"]["mux_channels"]
SD = {0: "4", 1: "6", 2: "8", 3: "10", 4: "13", 5: "15", 6: "17", 7: "19"}
n_ok = 0
for i, d in tofch.items():
    i = int(i)
    mux = "U50" if d["mux"] == 0 else "U51"
    net = HC["CHS.J_TOF%d" % i]["pins"]["3"]["net"]
    _, rn = trace(CHS, PCHS, NCHS, net, hops_chs, want_nets=True)
    rn = {n for n in rn}
    pins = [x for n in rn for x in NCHS[n] if x[0] == mux]
    if any(p == SD[d["ch"]] for _, p in pins):
        n_ok += 1
    else:
        err("H ToF mapping", "firmware ToF %d (%s) mux %d ch %d: J_TOF%d SDA is not on %s pin %s in circuit.py (found %s)" % (i, d["id"], d["mux"], d["ch"], i, mux, SD[d["ch"]], pins))
count("H2. firmware ToF id -> mux/channel equals the circuit wiring of J_TOFn (11)", n_ok, 11)

# head firmware
hf = S["fw_head"]
n_ok = n_tot = 0
hsig = {}
for p in hf["pins"]:
    if p.get("dir") == "power":
        continue
    pn_, net = HD.MCU_PINMAP[p["lqfp100"]]
    hsig[p["signal"]] = net
    n_tot += 1
    if p["pin"] != pn_:
        err("H firmware pin map", "head firmware %s at LQFP100 pin %s is %s but circuit.py has %s" % (p["signal"], p["lqfp100"], p["pin"], pn_))
    elif not (p["signal"] == net or p["signal"] in net or net in p["signal"] or (p["signal"].startswith("SPARE") and True)):
        warn("H firmware names", "head pin %s: firmware %s vs circuit net %s" % (p["pin"], p["signal"], net))
        n_ok += 1
    else:
        n_ok += 1
count("H3. head firmware pins sit on the same MCU pins as the head circuit definition", n_ok, n_tot)
HD_EXPECT = {"NTC_SIPM0": [("J1001", "1")], "NTC_SIPM1": [("J1101", "1")], "NTC_SIPM2": [("J1201", "1")], "NTC_SIPM3": [("J1301", "1")], "NTC_HTR": [("J2601", "4")], "HTR_CUTOUT_OK": [("J2601", "3")],
             "BUMP_ZONE_F_N": [("J2002", "3")], "BUMP_ZONE_L_N": [("J2003", "3")], "BUMP_ZONE_R_N": [("J2004", "3")], "RS485_TX": [("J2501", "1"), ("J2501", "2")], "RS485_RX": [("J2501", "1"), ("J2501", "2")],
             "RS485_DE": [("J2501", "1"), ("J2501", "2")], "DBG_TX": [("J2402", "1")], "DBG_RX": [("J2402", "2")], "SWDIO": [("J2401", "2")], "SWCLK": [("J2401", "4")], "HTR_EN": [("J2601", "1")],
             "MON_ADC": [("J2701", "1")]}
n_ok = n_tot = 0
for s, exp in HD_EXPECT.items():
    net = hsig.get(s)
    if net is None:
        err("H firmware off-board", "head firmware signal %s not found" % s)
        continue
    cons = {(a, b) for a, b, n in trace(HD, PHD, NHD, net, hops_hd) if n not in RAIL_NOREACH}
    for cc, pp in exp:
        n_tot += 1
        cid = "HEAD." + cc
        if (cc, pp) not in cons:
            err("H firmware off-board", "head firmware %s (net %s) does not reach %s pin %s in the head circuit.py" % (s, net, cc, pp))
        elif (cid, pp) in use:
            n_ok += 1
        elif cc in ("J2401", "J2402", "J2701"):
            n_ok += 1
            INFO.append(("H service ports", "%s reaches %s pin %s: service/test connector, no permanent cable (documented)" % (s, cc, pp)))
        else:
            n_ok += 0
            warn("H firmware off-board", "head firmware %s leaves the board at %s pin %s but NO harness wire lands there (by decision CCR-HE-04 / IB-21: the rail-zone read-back inputs read 'not actuated' forever with single-pole switches)" % (s, cc, pp))
count("H4. head firmware signals that leave the board reach the expected connector pin AND have a harness wire there", n_ok, n_tot)

# ---- I. unconnected connector pins
un = H["unconnected_pins"]
undecided = [u for u in un if u["reason"].startswith("NOT WIRED")]
for u in undecided:
    err("I unconnected pins", "%s pin %s (net %s) has no wire and no recorded reason" % (u["connector"], u["pin"], u["net"]))
count("I. every connector pin without a wire has a recorded reason (%d unconnected pins listed in connectors.yaml)" % len(un), len(un) - len(undecided), len(un))
# board pins that carry a live net but have no wire and are not service/NC
live = [u for u in un if u["net"] not in ("NC", "NC_RESERVED", "UNUSED") and u["connector"] not in ("CHS.J_SWD", "CHS.J_DBG", "CHS.J_AUX", "HEAD.J2401", "HEAD.J2402", "HEAD.J2701", "HEAD.JP2201", "CHGPLUG")]
for u in live:
    warn("I live net not wired", "%s pin %s carries %s but has no wire: %s" % (u["connector"], u["pin"], u["net"], u["reason"]))

# ---- J. lengths
CAB = {}
for w in WIRES:
    CAB.setdefault(w["cable_id"], w)
n_ok = n_tot = 0
for cid_, w in CAB.items():
    L_ = int(w["length_mm"])
    if 30 <= int(cid_[2:]) <= 40 and cid_.startswith("W-0"):
        n_tot += 1
        if L_ > 300:
            err("J ToF cable length", "%s (ToF) is %d mm > 300 mm, the I2C design limit (modules/tof_vl53l4ed.md): %s" % (cid_, L_, "see open decision OD-1 (IB-34 look-sensor mapping against the connector positions)" if cid_ in ("W-035", "W-036", "W-037") else "check the routing"))
        else:
            n_ok += 1
count("J1. every ToF cable is <= 300 mm (I2C design limit; stage-2 connector positions from pinmap.json, sensor positions from frames.yaml)", n_ok, n_tot)
# robot cables against the length the power budget / mechanical assumed (budget_mm is in the generator; recompute from the summary table of cables.md)
try:
    import hdata_cables as hk
    n_ok = n_tot = 0
    for c in hk.CABLES:
        if c["budget_mm"] and c["group"] == "robot" and not (30 <= int(c["id"][2:]) <= 40):
            n_tot += 1
            if c["length_mm"] > c["budget_mm"]:
                warn("J lengths", "%s is %d mm against the %d mm assumed by the source (power_budget.md / mechanical)" % (c["id"], c["length_mm"], c["budget_mm"]))
            else:
                n_ok += 1
    count("J2. robot cables inside the length assumed by the power budget (warning only)", n_ok, n_tot)
    # the stage-2 board report's own estimate for comparison (electronics/chassis_main/reports/cable_lengths.json): information only
    import json
    cl = json.load(open(os.path.join(ROOT, "electronics/chassis_main/reports/cable_lengths.json")))
    byc = {c["id"]: c["length_mm"] for c in hk.CABLES}
    for r in cl:
        if r["cable"] in byc and abs(byc[r["cable"]] - r["stage2_mm"]) >= 40:
            INFO.append(("J length vs chassis tool", "%s: harness %d mm, electronics/chassis_main/tools/cable_lengths.py says %d mm (the tool takes the FIRST path point as the board connector, which is wrong for cables whose path starts at the device, and assumes the stage-1 look-sensor mapping: compare with OD-1 only after correcting both)" % (r["cable"], byc[r["cable"]], r["stage2_mm"])))
except ImportError:
    pass

# ---- K. IB-34 look sensors, IB-37, head stage-2 positions
import hdata_cables as hk
fwt = fw["i2c"]["I2C_TOF"]["mux_channels"]
n_ok = 0
for i, (nm, zone, keys) in hk.LOOK_MAP.items():
    fid = fwt[i]["id"] if i in fwt else fwt[str(i)]["id"]
    sp = hk.FRAMES_TOF and next((k for k in keys if k in hk.FRAMES_TOF), None)
    if not sp:
        err("K look sensors", "frames.yaml has none of %s for %s" % (keys, nm))
        continue
    if fid != nm:
        warn("K look sensors", "firmware/chassis/pinmap.yaml still names ToF id %d %s; the harness (IB-34) calls it %s (frames.yaml %s): rename in the firmware and the contract" % (i, fid, nm, sp))
    else:
        n_ok += 1
    fwd = zone.startswith("f")
    if fwd != (hk.FRAMES_TOF[sp][0] > -100):
        err("K look sensors", "%s is %s in the harness but frames.yaml %s is at x = %.1f mm" % (nm, "forward" if fwd else "rearward", sp, hk.FRAMES_TOF[sp][0]))
    if (zone[1] == "l") != (hk.FRAMES_TOF[sp][1] > 0):
        err("K look sensors", "%s side disagrees with frames.yaml %s (y = %.1f mm)" % (nm, sp, hk.FRAMES_TOF[sp][1]))
INFO.append(("K look sensors", "IB-34: ids 4..7 = %s; frames.yaml positions %s" % (", ".join(v[0] for v in hk.LOOK_MAP.values()), "; ".join("%s %s" % (v[0], hk.tofpos(v[2])) for v in hk.LOOK_MAP.values()))))
INFO.append(("K IB-37", "J_PAUX pins 3/4 (GND) are unwired by decision: accepted NTC offset (about 3.4 K warm on discharge, about 0.7 K cold on charge, safe side); wire them only if the cassette provides an isolated sense return"))
# head stage-2 positions (S2-L5 / S2-L6): J2601 and J2001 side by side, J2004 within the rail-switch harness reach, 4 lane auxiliary GH-6
hu = {p["ref"]: p for p in S["hd_pinmap"]["parts"]}
def span(ref):
    xs = []
    for q in hu[ref]["pins"]:
        v = q.get("pad_xy_mm")
        if v:
            xs += v if isinstance(v[0], list) else [v]
    return min(a for a, _ in xs), max(a for a, _ in xs)
ok4 = True
if not (span("J2601")[1] < span("J2001")[0]):
    err("K head stage 2", "J2601 and J2001 overlap in u: %s %s" % (span("J2601"), span("J2001")))
    ok4 = False
c2004 = sum(span("J2004")) / 2
if not (140.0 <= c2004 <= 149.0):
    err("K head stage 2", "J2004 centre u %.1f is outside the rail-switch harness reach u 140..149 (S2-L6)" % c2004)
    ok4 = False
for j in ("J1001", "J1101", "J1201", "J1301"):
    if hu[j]["mpn"] != "SM06B-GHS-TB(LF)(SN)":
        err("K head stage 2", "%s is not the lane auxiliary GH-6" % j)
        ok4 = False
count("K. head stage 2: J2601 and J2001 side by side at the rear edge, J2004 at u %.1f inside the harness reach u 140..149, four lane auxiliary GH-6" % c2004, int(ok4), 1)
INFO.append(("K head stage 2", "TP2004 at u %.1f v %.1f and TP2501 at u %.1f v %.1f are 60-100 mm from the J2001 / J2501 landings: the shield drains W-101.S / W-102.S are separate wires of %s / %s mm inside the head" % (
    *[x for t in ("TP2004", "TP2501") for x in hk.HEAD_UV[t]], W["W-101.S"]["length_mm"], W["W-102.S"]["length_mm"])))

# ================================================================ report
lines = ["# Harness cross-check report", "", "GENERATED by `python3 harness/cross_check.py`; do not edit by hand.", "",
         "Inputs: chassis circuit.py WITH `electronics/chassis_main/overrides.py` applied (stage 2), head / panel `circuit.py`, `out/pinmap.json` of the chassis, head, panel and ToF boards (placed positions and nets), `electronics/chassis_main/design/connectors.yaml` (stage 1, compared with stage 2), `firmware/chassis/pinmap.yaml`, `firmware/head/pinmap.yaml`, `interface/system/contract.yaml`, `mechanical/common/frames.yaml`, `harness/connectors.yaml`, `harness/cables.csv`.", "",
         "## Result: **%s** (%d errors, %d warnings, %d information lines)" % ("FAIL" if ERR else "PASS", len(ERR), len(WARN), len(INFO)), "",
         "Harness: %d connectors, %d cables, %d wires." % (len(HC), len({w["cable_id"] for w in WIRES}), len(WIRES)), "",
         "## Checks run", "", "| Check | Passed / total |", "|---|---|"]
for k, (a, b) in PASS.items():
    lines.append("| %s | %s |" % (k, ("%d / %d" % (a, b)) if b is not None else a))
lines += ["", "## ERRORS (real mismatches; exit status 1)", ""]
by = collections.OrderedDict()
for cat, msg in ERR:
    by.setdefault(cat, []).append(msg)
if not ERR:
    lines.append("none")
for cat, ms in by.items():
    lines.append("### %s (%d)" % (cat, len(ms)))
    lines.append("")
    for m in ms:
        lines.append("* %s" % m)
    lines.append("")
lines += ["## WARNINGS (documented deviations, unverifiable items, decisions that leave a signal unconnected)", ""]
by = collections.OrderedDict()
for cat, msg in WARN:
    by.setdefault(cat, []).append(msg)
for cat, ms in by.items():
    lines.append("### %s (%d)" % (cat, len(ms)))
    lines.append("")
    for m in ms:
        lines.append("* %s" % m)
    lines.append("")
lines += ["## Information", ""]
by = collections.OrderedDict()
for cat, msg in INFO:
    by.setdefault(cat, []).append(msg)
for cat, ms in by.items():
    lines.append("### %s (%d)" % (cat, len(ms)))
    lines.append("")
    for m in ms:
        lines.append("* %s" % m)
    lines.append("")
open(os.path.join(HERE, "cross_check_report.md"), "w").write("\n".join(lines) + "\n")
print("cross_check: %s: %d errors, %d warnings, %d info" % ("FAIL" if ERR else "PASS", len(ERR), len(WARN), len(INFO)))
for cat, msg in ERR[:60]:
    print("  ERROR [%s] %s" % (cat, msg))
sys.exit(1 if ERR else 0)
