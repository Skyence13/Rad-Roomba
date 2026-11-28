"""RR-HEAD-ACQ stage-2 override layer on top of the stage-1 netlist (design/circuit.py).

design/circuit.py is the reviewed stage-1 baseline and is NOT edited.  Every deviation the board needs is
data in this file, applied by ``apply()`` to a deep copy of circuit.PARTS.  Each entry states what it
expects to find in the baseline, so a change in circuit.py stops the build instead of being silently
overridden.  IDs (S2-xx) are the same in STAGE2_CHANGE_REQUESTS.md and README.md.

Kinds
  NET     a pin moves to another net / becomes NC     (netlist change)        -- stage 3: S3-01..S3-04
  VALUE   value / MPN of existing parts changed        (netlist change)        -- stage 3: S3-01, S3-03
  ADD     new part record                               (netlist change)        -- stage 3: S3-02..S3-04
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
# (id, ref, pin number, expected (name, net) in circuit.py, new (name, net), reason)
# Stage 3 (review REVIEW_head_interference.md fixes); every entry is listed in STAGE2_CHANGE_REQUESTS.md "Stage 3".
CH_ALL = ["F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"]
CH_BASE = {ch: 100 * (i + 1) for i, ch in enumerate(CH_ALL)}
NET = []
for _ch in CH_ALL:
    _b = CH_BASE[_ch]
    # S3-01 (M2): FAST monitor tap from the comparator input FCMP to the op-amp output FAST
    NET.append(("S3-01", "R%d" % (_b + 25), "1", ("1", _ch + "_FCMP"), ("1", _ch + "_FAST"),
                "M2: monitor tap at the OPA838 output, not at the comparator input"))
    # S3-04 (m2): capacitor in series with R_PZ removes the DC path PRE -> FAST
    NET.append(("S3-04", "R%d" % (_b + 20), "2", ("2", _ch + "_FS"), ("2", _ch + "_PZ"),
                "m2: R_PZ now ends on the new series capacitor C(base+50)"))
    if _ch[0] == "F":
        NET.append(("S3-01", "R%d" % (_b + 34), "1", ("1", _ch + "_SCMP"), ("1", _ch + "_SLOW"),
                    "M2: slow monitor tap at the OPA836 output, not at the ALPHA comparator input"))
NET += [
    ("S3-02", "U2701", "6", ("E3", "+3V3"), ("E3", "MON_LANE_EN"),
     "M2: lane-monitor decoder enable from the expander, so that all lane muxes can be switched off"),
    ("S3-02", "U2405", "12", ("P7", "EXP_P7"), ("P7", "MON_LANE_EN"), "M2: spare expander bit P7 = lane-monitor enable"),
    ("S3-02", "TP2402", "1", ("1", "EXP_P7"), ("1", "MON_LANE_EN"), "test pad follows the renamed net"),
    ("S3-03", "R2801", "1", ("1", "FRAME"), ("1", "FRAME_F"), "M5: frame bond in series with the new fuse F2801"),
    ("S3-03", "R2802", "2", ("2", "GND"), ("2", "MON_BUS"),
     "M5: frame bleed becomes the top of a 1 M / 1 M frame-potential divider onto the (idle) monitor bus"),
    ("S3-03", "R2702", "2", ("2", "GND"), ("2", "VBL"),
     "M5: monitor-bus bleed to VBL (0.6 V) so that the frame monitor reads both polarities"),
]
# S3-05 (M3): the frame is ONE conductor only through the spreader; on the board every hole pad and its bond parts are
# a separate copper island.  Name them per hole so that the board copper is checkable (no false 'unconnected' FRAME):
# H1 keeps 'FRAME' (DC bond F2801/R2801, bleed R2802, J1 shield parts); C2801/C2803/C2804 at H2/H5/H6; C2802 moves to H8
# because H3 lies inside the isolated RS-485 island (no GND there); H3 carries the J2 shield parts R2505/C2504.
FRAME_NET = {"H2802": "FRAME_H2", "H2803": "FRAME_H3", "H2804": "FRAME_H4", "H2805": "FRAME_H5", "H2806": "FRAME_H6",
             "H2807": "FRAME_H7", "H2808": "FRAME_H8"}
for _h, _n in sorted(FRAME_NET.items()):
    NET.append(("S3-05", _h, "1", ("PAD", "FRAME"), ("PAD", _n), "M3: per-hole frame copper island"))
for _ref, _pin, _n in (("C2801", "1", "FRAME_H2"), ("C2802", "1", "FRAME_H8"), ("C2803", "1", "FRAME_H5"),
                       ("C2804", "1", "FRAME_H6"), ("C2504", "2", "FRAME_H3"), ("R2505", "2", "FRAME_H3")):
    NET.append(("S3-05", _ref, _pin, (_pin, "FRAME"), (_pin, _n), "M3: bond part on the copper island of its own hole"))

# ----------------------------------------------------------------------------------------- VALUE
# (id, refs, expected value, new fields, reason)
_R10K = dict(value="10k", mpn="RC0402FR-0710KL", ohms=10e3)
VALUE = [
    ("S3-01", tuple("R%d" % (CH_BASE[c] + k) for c in CH_ALL for k in (19, 25)) +
     tuple("R%d" % (CH_BASE[c] + 34) for c in CH_ALL if c[0] == "F"), "1k", _R10K,
     "M2: lane-monitor taps 1 k -> 10 k (loading and switch charge absorbed by the op-amp output)"),
    ("S3-03", ("R2702",), "100k", dict(value="1M", mpn="RC0402FR-071ML", ohms=1e6),
     "M5: monitor-bus bleed 1 M (equal to R2802) = frame divider 1:2; injection into the bus limited to uA"),
]
# description text replaced for parts whose function changed (no electrical effect)
DESC = {
    "R2702": "monitor bus bleed to VBL; with all lane muxes off MON_BUS = VBL/2 + V(FRAME)/2 (frame-fault monitor, S3-03)",
    "R2802": "frame bleed and top of the frame-potential divider onto MON_BUS (S3-03)",
    "R2801": "single-point DC frame bond (0 R) at H1, in series with fuse F2801 (S3-03)",
    "C2801": "HF frame bond at H2 (FRAME_H2, S3-05)", "C2802": "HF frame bond at H8 (FRAME_H8; H3 is inside the isolated island, S3-05)",
    "C2803": "HF frame bond at H5 (FRAME_H5, S3-05)", "C2804": "HF frame bond at H6 (FRAME_H6, S3-05)",
    "C2504": "J2 shield to frame at H3 (FRAME_H3, S3-05)", "R2505": "J2 shield to frame at H3 (FRAME_H3, S3-05)",
}
for _c in CH_ALL:
    DESC["R%d" % (CH_BASE[_c] + 25)] = "monitor tap: fast (op-amp output, 10 k, S3-01)"
    DESC["R%d" % (CH_BASE[_c] + 19)] = "monitor tap: preamp (10 k, S3-01)"
    DESC["R%d" % (CH_BASE[_c] + 20)] = ("pole-zero R_PZ = t_recharge / C_D (226 R for 50 ns), in series with the 47 nF DC block "
                                       "C%d (S3-04)" % (CH_BASE[_c] + 50))
    if _c[0] == "F":
        DESC["R%d" % (CH_BASE[_c] + 34)] = "monitor tap: slow (op-amp output, 10 k, S3-01)"

# ----------------------------------------------------------------------------------------- ADD
# new part records (same schema as circuit.py); block/instance decide the sheet (lane parts by instance)


def _rec(ref, value, mpn, mfr, desc, package, sym, fp, pins, block, instance, **kw):
    p = dict(ref=ref, value=value, mpn=mpn, manufacturer=mfr, description=desc, package=package, symbol_hint=sym,
             footprint_hint=fp, pins={str(k): v for k, v in pins.items()}, block=block, instance=instance, dnp=False,
             tolerance=None, rating=None, notes="", verify=False, npins=len(pins))
    p.update(kw)
    return p


ADD = []
for _c in CH_ALL:
    ADD.append(("S3-04", _rec(
        "C%d" % (CH_BASE[_c] + 50), "47nF", "GRM155R71C473KA01D", "Murata",
        "pole-zero DC block in series with R_PZ: (R_PZ + R_D) x 47 nF = 15 us; 1 ohm at 3 MHz (no effect on the pulse)",
        "0402", "Device:C", "Capacitor_SMD:C_0402_1005Metric", {1: ("1", _c + "_PZ"), 2: ("2", _c + "_FS")},
        "AFE_FLOOR" if _c[0] == "F" else "AFE_REF", _c, tolerance="10%", rating="X7R 16 V", mpn_rule=True,
        notes="S3-04 (review m2): removes the DC transmission 0.307 of the PZ divider; post-alpha FAST undershoot at "
              "300 us 0.06 p.e. instead of 3.3 p.e. (head_afe_calc.py T14)"),
        "m2: post-alpha baseline dip"))
ADD += [
    ("S3-02", _rec("R2418", "100k", "RC0402FR-07100KL", "Yageo",
                   "MON_LANE_EN pull-down: lane monitor off in reset / expander absent (S3-02)", "0402", "Device:R",
                   "Resistor_SMD:R_0402_1005Metric", {1: ("1", "MON_LANE_EN"), 2: ("2", "GND")}, "MCU", "MCU",
                   tolerance="1%", rating="62.5 mW, 50 V", mpn_rule=True, ohms=100e3), "M2: true off state"),
    ("S3-03", _rec("F2801", "0.5A fast", "0466.500NR", "Littelfuse",
                   "frame-bond fuse 0.5 A very fast-acting, 1206: opens on a heater-domain fault into the spreader before the "
                   "J1 common-mode choke L2001 or the plane is overloaded (S3-03, review M5)", "1206", "Device:Fuse",
                   "Fuse:Fuse_1206_3216Metric", {1: ("1", "FRAME"), 2: ("2", "FRAME_F")}, "MECH", "MECH", verify=True,
                   rating="0.5 A, 63 V (series data UNVERIFIED)",
                   notes="Littelfuse 466 series ordering code, I2t and cold resistance (~0.3 ohm) UNVERIFIED; any 0.5 A "
                         "very fast 1206 chip fuse >= 32 V DC with I2t >= 0.01 A2s fits. Place within 3 mm of H2801."),
     "M5: frame-bond fault protection"),
]

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
NOTE_REPLACE = {"R2801": "single-point DC bond of the spreader/frame to GND at H1 (within 3 mm of H2801), in series with the "
                          "0.5 A fuse F2801 (S3-03). FITTED IN BOTH BUILDS (IB-38)."}

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
    for oid, refs, old, fields, why in VALUE:
        for ref in refs:
            p = need(ref)
            if p["value"] != old:
                raise OverrideError("%s: %s value is %r in circuit.py, override expects %r" % (oid, ref, p["value"], old))
            p.update(fields)
        log.append(dict(id=oid, kind="VALUE", refs=list(refs), old=old, new=fields, reason=why))
    for ref, text in DESC.items():
        need(ref)["description"] = text
    for oid, rec, why in ADD:
        if rec["ref"] in byref:
            raise OverrideError("%s: new part %s already exists in circuit.py" % (oid, rec["ref"]))
        rec = copy.deepcopy(rec)
        parts.append(rec)
        byref[rec["ref"]] = rec
        log.append(dict(id=oid, kind="ADD", ref=rec["ref"], value=rec["value"], mpn=rec["mpn"],
                        pins={k: v for k, v in rec["pins"].items()}, reason=why))
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


def self_check_overridden(parts, verbose=True):
    """Re-run the stage-1 self-check of design/circuit.py on the OVERRIDDEN parts (fresh module instance).

    Three documented adaptations, nothing else: (1) single-pin whitelist: EXP_P7 dropped because S3-02 gives that bit a
    function (renamed MON_LANE_EN); FRAME_H4 / FRAME_H7 added (S3-05 hole pads without bond parts); (2) CR-H9: pinmap.yaml may name U_DAC0/U_DAC1 output 7 'LED_AMPL' /
    'DAC1_SPARE' as well as 'SPARE' (the stage-1 check maps the board names to SPARE already); (3) the S2-01 RENUM
    entries are undone for the check (exposed pad back to 'EP', as circuit.py names it)."""
    import types
    parts = copy.deepcopy(parts)
    inv = {}
    for _id, refs, mapping, _why in RENUM:
        for r in refs:
            inv[r] = {v: k for k, v in mapping.items()}
    for p in parts:
        if p["ref"] in inv:
            p["pins"] = {inv[p["ref"]].get(k, k): v for k, v in p["pins"].items()}
    mod = load_circuit()
    mod.PARTS[:] = parts
    mod._REFS.clear()
    mod._REFS.update({p["ref"]: p for p in parts})
    raw = mod.build_nets()
    mod.NETS.clear()
    mod.NETS.update({n: dict(net_class=mod.net_class(n), pins=sorted(v)) for n, v in sorted(raw.items())})
    mod.SINGLE_PIN_WHITELIST.pop("EXP_P7", None)
    for n in ("FRAME_H4", "FRAME_H7"):
        mod.SINGLE_PIN_WHITELIST[n] = "S3-05: mounting-hole pad without bond parts (joined to the frame by the spreader)"
    real_yaml = None
    try:
        import yaml as real_yaml
    except ImportError:
        pass
    if real_yaml is not None:
        def safe_load(stream):
            d = real_yaml.safe_load(stream)
            if isinstance(d, dict) and "dac_map" in d:
                for v in d["dac_map"].values():
                    v["outputs"] = ["SPARE" if o in ("LED_AMPL", "DAC1_SPARE") else o for o in v["outputs"]]
            return d
        shim = types.ModuleType("yaml")
        shim.safe_load = safe_load
        sys.modules["yaml"] = shim
    try:
        return mod.self_check(verbose=verbose)
    finally:
        if real_yaml is not None:
            sys.modules["yaml"] = real_yaml


def expected_diff():
    """The pin-level changes S3 NET / ADD entries are allowed to make: set of (ref, pin name, net) removed / added."""
    rem, add = set(), set()
    for _id, ref, _pin, old, new, _why in NET:
        rem.add((ref, old[0], old[1]))
        add.add((ref, new[0], new[1]))
    for _id, rec, _why in ADD:
        for v in rec["pins"].values():
            if v:
                add.add((rec["ref"], v[0], v[1]))
    return rem, add


if __name__ == "__main__":
    base = load_circuit()
    new, log = apply(base.PARTS)
    for e in log:
        print("%-6s %-6s %s" % (e["id"], e["kind"], e.get("refs") or e.get("ref") or e.get("count", "")))
    rem, add = netlist_diff(base.PARTS, new)
    erem, eadd = expected_diff()
    print("pins removed from a net: %d (expected S3 entries %d)" % (len(rem), len(erem)))
    print("pins added to a net:     %d (expected S3 entries %d)" % (len(add), len(eadd)))
    bad = sorted(set(rem) ^ erem) + sorted(set(add) ^ eadd)
    print("pin changes NOT listed in overrides.py:", bad or "none")
    print("part records:", len(new), "(baseline %d + %d added)" % (len(base.PARTS), len(ADD)))
    groups = {}
    for p in new:
        groups[p["block"]] = groups.get(p["block"], 0) + 1
    print("groups:", groups)
    print("--- stage-1 self-check re-run on the overridden netlist ---")
    ok = self_check_overridden(new)
    sys.exit(1 if (bad or len(new) != len(base.PARTS) + len(ADD) or not ok) else 0)
