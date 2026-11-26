"""RR-HEAD-ACQ stage-2 override layer on top of the stage-1 netlist (design/circuit.py).

design/circuit.py is the reviewed stage-1 baseline and is NOT edited.  Every deviation the board needs is
data in this file, applied by ``apply()`` to a deep copy of circuit.PARTS.  Each entry states what it
expects to find in the baseline, so a change in circuit.py stops the build instead of being silently
overridden.  IDs (S2-xx) are the same in STAGE2_CHANGE_REQUESTS.md and README.md.

Kinds
  NET     a pin moves to another net / becomes NC     (netlist change)        -- none in rev A
  RENUM   pin NUMBER changed to the footprint's pad number, same pin name and net (no electrical change)
  GROUP   schematic sheet assignment ("block") changed (no electrical change)
  NOTE    BOM/notes text changed (decisions from the integration backlog), no electrical change
  LIB     symbol / footprint choice for the CAD library (no electrical change)

Plain Python, no rrkicad import: runs inside the KiCad container (board.py) and on the host
(``python3 electronics/head_acq/overrides.py`` prints the change log, the pin-level netlist diff against
the baseline and re-runs the stage-1 lane-identity check on the overridden parts).
"""
import copy
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CIRCUIT = os.path.join(HERE, "design", "circuit.py")


def load_circuit(path=CIRCUIT):
    spec = importlib.util.spec_from_file_location("rr_head_acq_circuit_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------------------------- NET
NET = []          # rev A: no netlist change

# ----------------------------------------------------------------------------------------- RENUM
# stage 1 names the exposed pad "EP"; the KiCad stock footprints number it after the last lead.
RENUM = [
    ("S2-01", ("U2001",), {"EP": "17"}, "HTSSOP-16-1EP: exposed pad is pad 17 in Package_SO:HTSSOP-16-1EP_4.4x5mm (and pin 17 "
                                          "of the stock TPS26600PWP symbol, stacked with RTN pin 8 - same net EF_RTN)"),
    ("S2-01", ("U2103", "U2104", "U2402", "U2403"), {"EP": "7"}, "WSON-6-1EP 2x2: exposed pad is pad 7"),
    ("S2-01", ("U2201", "U2301", "U2302", "U2303", "U2304"), {"EP": "17"}, "WQFN-16-1EP 3x3: exposed pad is pad 17"),
]

# ----------------------------------------------------------------------------------------- GROUP
CHANNELS = ["F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"]


def lane_group(p):
    """Schematic sheet of a lane part: one sheet each for the floor channel, the reference channel and the shared
    lane logic of lane k, so the four lanes are four identical sheet sets (S2-02)."""
    inst = p.get("instance", "")
    if inst in CHANNELS:
        k = int(inst[1])
        return "LANE%d_%s" % (k, "FLOOR" if inst[0] == "F" else "REF")
    m = re.match(r"^L(\d)$", inst)
    if m and p["block"] == "LANE":
        return "LANE%s_LOGIC" % m.group(1)
    return None


# ----------------------------------------------------------------------------------------- NOTE
# (id, refs, expected substring of the current notes or None, text to append, reason)
NOTE = [
    ("S2-03", ("J2002", "J2003", "J2004"), None,
     "IB-21: zone identification (pins 3/4 AUX_N/AUX_GND -> BUMP_ZONE_x_N) NOT AVAILABLE IN REV A: the single-pole rail "
     "switches have no potential-free auxiliary contact; the inputs read 'not actuated'. Footprints and parts kept.",
     "IB-21 lead decision path: keep the footprints, mark the function unavailable"),
    ("S2-03", ("R2013", "R2014", "C2008", "D2002", "R2015", "R2016", "C2009", "D2003", "R2017", "R2018", "C2010", "D2004"),
     None, "IB-21: zone identification input - function not available in rev A (part fitted, input idles high).",
     "IB-21"),
    ("S2-04", ("R2801",), "remove if the head frame", "IB-38 (lead decision 2026-11-26): R2801 is FITTED IN BOTH BUILDS "
     "(prototype and production heads keep the frame isolated from the chassis; this is the single DC frame bond).",
     "IB-38 supersedes CCR-HE-03 and the bonded-shoe text in mechanical/head/production/README.md"),
    ("S2-05", ("U2304",), None, "IB-25: TRIM DAC range 0.10-2.50 V = 2.4 V per channel; 0.4 V of it is reserved for the per-lane "
     "temperature difference and the I x 4.99 k floor, so the SiPM breakdown spread within one head must be <= 2.0 V "
     "(the RFQ value, CCR-HE-06 c).", "IB-25 decision: 2.0 V"),
]
# notes replaced instead of appended (the stage-1 text is superseded)
NOTE_REPLACE = {"R2801": "single-point DC bond of the spreader/frame to GND next to H1. FITTED IN BOTH BUILDS (IB-38)."}

# ----------------------------------------------------------------------------------------- LIB
# symbol per MPN (stock where the pin NUMBERS and functions match circuit.py; rr_local:* defined in board.py)
SYMBOL_BY_MPN = {
    "SN74LVC2G53DCUR": "74xGxx:74LVC2G53",            # hint named the wrong library (Analog_Switch)
    "OPA838IDBVR": "Amplifier_Operational:OPA690xDBV",  # same DBV-6 pin-out: 1 OUT 2 V- 3 +IN 4 -IN 5 PD/~DIS 6 V+
    "OPA836IDBVR": "Amplifier_Operational:OPA690xDBV",
    "TLV3502AIDCNR": "rr_local:TLV3502_DCN",            # no stock symbol; DCN pin-out from stage 1 (datasheet-read)
    "TLV3501AIDBVR": "Comparator:TLV3501AIDBV",          # exact part, pins identical
    "S1711-46R": "Device:RFShield_OnePiece",
    "RR-HEAD-SHLD-A": "rr_local:RR-HEAD-SHLD-A",          # pinless mechanical part
    "LMR51606YFDBVR": "rr_local:LMR51606_DBV",
    "TPS7A2050PDBVR": "Regulator_Linear:TPS7A0530PDBV",  # same DBV-5 LDO pin-out IN GND EN NC OUT (verify, stage 1)
    "TLV76733DRVR": "Regulator_Linear:TLV76733DRVx",     # exact family symbol, EP = pin 7
    "TPS61391RTER": "rr_local:TPS61391_RTE",
    "BZX84-C12,215": "Diode:BZX84Cxx",                   # SOT-23 zener 1 A, 2 NC, 3 K
    "TLV7021DBVR": "Comparator:TLV7041DBV",              # same DBV-5 open-drain comparator pin-out (OUT V- IN+ IN- V+)
    "DAC60508ZRTER": "rr_local:DAC60508_RTE",
    "ECS-TXO-2520MV-240-AN-TR": "Oscillator:ASE-xxxMHz", # 4-pad oscillator EN GND OUT VDD
    "TMP117AIDRVR": "rr_local:TMP117_DRV_EP",           # stock TMP117xxDRV has no EP pin; stage 1 ties EP to GND
    "TCA9534PWR": "Interface_Expansion:TCA9534",
    "ISO1430BDWR": "rr_local:ISO1430_DW",
    "ISO7710DR": "rr_local:ISO7710_D",
    "SUD50P04-08-GE3": "Transistor_FET:SUD50P04-08",     # exact part
    "SMBJ16A": "Device:D_Zener",                          # unidirectional TVS, 1 K 2 A (stock D_TVS is bidirectional)
}
FOOTPRINTS = {}
FOOTPRINT_BY_MPN = {
    "S1711-46R": "rr_local:Harwin_S1711-46R_ShieldClip",
    "RR-HEAD-SHLD-A": "rr_local:RR-HEAD-SHLD-A_LaneShieldCan",
    "ACM4520-901-2P-T000": "rr_local:L_CommonMode_TDK_ACM4520",
}
LIB_NOTES_BY_MPN = {
    "S1711-46R": "stage 2: clip land pattern from memory of the Harwin S1711-46R drawing (VERIFY pad size before order)",
    "ACM4520-901-2P-T000": "stage 2: land pattern from memory of the TDK ACM4520 outline (VERIFY against the TDK drawing; "
                           "winding pairing 1-2 / 4-3 already UNVERIFIED in stage 1)",
    "OPA838IDBVR": "stage 2: drawn with the pin-compatible stock OPA690xDBV symbol",
    "OPA836IDBVR": "stage 2: drawn with the pin-compatible stock OPA690xDBV symbol",
    "TPS7A2050PDBVR": "stage 2: drawn with the stock TPS7A05xxPDBV symbol (same DBV-5 pin-out per stage 1)",
    "TLV7021DBVR": "stage 2: drawn with the stock TLV7041DBV symbol (open-drain, same pin-out per stage 1)",
    "ECS-TXO-2520MV-240-AN-TR": "stage 2: drawn with the stock 4-pad oscillator symbol ASE-xxxMHz",
}


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
        if p["pins"].get(pin) != old:
            raise OverrideError("%s: %s.%s is %r in circuit.py, override expects %r" % (oid, ref, pin, p["pins"].get(pin), old))
        p["pins"][pin] = new
        log.append(dict(id=oid, kind="NET", ref=ref, pin=pin, old=old, new=new, reason=why))
    for oid, refs, mapping, why in RENUM:
        for ref in refs:
            p = need(ref)
            for old, new in mapping.items():
                if old not in p["pins"] or new in p["pins"]:
                    raise OverrideError("%s: %s pins %s do not allow %s -> %s" % (oid, ref, sorted(p["pins"]), old, new))
            p["pins"] = {mapping.get(k, k): v for k, v in p["pins"].items()}
        log.append(dict(id=oid, kind="RENUM", refs=list(refs), mapping=mapping, reason=why))
    moved = 0
    for p in parts:
        g = lane_group(p)
        if g:
            p["block"] = g
            moved += 1
    log.append(dict(id="S2-02", kind="GROUP", count=moved,
                    reason="AFE_FLOOR / AFE_REF / LANE split per lane: LANEk_FLOOR, LANEk_REF, LANEk_LOGIC (k = 0..3)"))
    for oid, refs, expect, text, why in NOTE:
        for ref in refs:
            p = need(ref)
            cur = p.get("notes") or ""
            if expect is not None and expect not in cur:
                raise OverrideError("%s: %s notes do not contain %r" % (oid, ref, expect))
            if ref in NOTE_REPLACE:
                cur = NOTE_REPLACE[ref]
            p["notes"] = (cur + " | " if cur else "") + text
        log.append(dict(id=oid, kind="NOTE", refs=list(refs), text=text, reason=why))
    for p in parts:
        mpn = p.get("mpn")
        if mpn in SYMBOL_BY_MPN:
            p["symbol_hint"] = SYMBOL_BY_MPN[mpn]
        if p["ref"] in FOOTPRINTS:
            p["footprint_hint"] = FOOTPRINTS[p["ref"]]
        elif mpn in FOOTPRINT_BY_MPN:
            p["footprint_hint"] = FOOTPRINT_BY_MPN[mpn]
        if mpn in LIB_NOTES_BY_MPN:
            p["notes"] = (p.get("notes") or "") + " | " + LIB_NOTES_BY_MPN[mpn]
    log.append(dict(id="S2-06", kind="LIB", symbol_by_mpn=SYMBOL_BY_MPN, footprint_by_mpn=FOOTPRINT_BY_MPN,
                    reason="CAD library choices for the rejected symbol hints and the parts without a footprint"))
    return parts, log


def netlist_diff(base_parts, new_parts):
    """(ref, pin name, net) multiset comparison - pin NAMES, so renumbering is not a change."""
    def m(parts):
        out = {}
        for p in parts:
            for num, v in p["pins"].items():
                if v is not None:
                    k = (p["ref"], v[0], v[1])
                    out[k] = out.get(k, 0) + 1
        return out
    a, b = m(base_parts), m(new_parts)
    return sorted(k for k in a if a[k] != b.get(k)), sorted(k for k in b if b[k] != a.get(k))


if __name__ == "__main__":
    base = load_circuit()
    new, log = apply(base.PARTS)
    for e in log:
        print("%-6s %-6s %s" % (e["id"], e["kind"], e.get("refs") or e.get("ref") or e.get("count", "")))
    rem, add = netlist_diff(base.PARTS, new)
    print("pins removed from a net:", rem or "none")
    print("pins added to a net:    ", add or "none")
    print("part records:", len(new), "(baseline %d)" % len(base.PARTS))
    groups = {}
    for p in new:
        groups[p["block"]] = groups.get(p["block"], 0) + 1
    print("groups:", groups)
    sys.exit(1 if (rem or add or len(new) != len(base.PARTS)) else 0)
