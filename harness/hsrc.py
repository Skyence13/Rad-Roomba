"""Source loaders for the harness generator and the cross-check.  Read-only access to the other engineers' files.
Nothing here writes outside harness/."""
import importlib.util, json, os, sys, collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _load(name, rel):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _yaml(rel):
    import yaml
    with open(os.path.join(ROOT, rel)) as f:
        return yaml.safe_load(f)


_cache = {}

# Mating data per connector family, as in electronics/chassis_main/design/gen_connectors.py (stage 1).  Duplicated here because
# gen_connectors.py writes a file when imported.  verify=True: mating part numbers recalled, not confirmed in stage 1.
MATE = {
    "Mini-Fit": dict(family="Molex Mini-Fit Jr 4.20 mm (POWER ENTRY)", housing="39-01-2080", contacts="39-00-0078 (AWG 16) for pins 1/2/5/6; 39-00-0038 (AWG 18-24) for the rest", verify=True),
    "Micro-Fit": dict(family="Molex Micro-Fit 3.0 (POWER)", housing="43025-%02d00", contacts="43030-0007 (AWG 20-24) / 43030-0010 (AWG 26-30)", verify=True),
    "CLIK-Mate": dict(family="Molex CLIK-Mate 2.00 mm (SAFETY, yellow wire)", housing="502439-%02d00", contacts="502438-0000 (AWG 24-30)", verify=True),
    "JST GH": dict(family="JST GH 1.25 mm (SIGNAL)", housing="GHR-%02dV-S", contacts="SSHL-002T-P0.2 (AWG 26-30)", verify=False),
    "Cortex": dict(family="1.27 mm IDC (SERVICE)", housing="Samtec FFSD-05-D-06.00-01-N ribbon", contacts="-", verify=True),
}
# Stage-2 mating data that differs from the family table (STAGE2_CHANGE_REQUESTS.md S2-02): J_HEAD1 is a Mini-Fit Jr 2x5.
# 39-01-2100 'class' and 5556 terminals 18-24 AWG are quoted by the stage-2 file as [U, part numbers recalled]; the terminal number
# used here is the one stage 1 lists for the 18-24 AWG Mini-Fit Jr contact on J_PWR (same file, same status).
MATE_STAGE2 = {"J_HEAD1": dict(family="Molex Mini-Fit Jr 4.20 mm (POWER ENTRY)", housing="39-01-2100", contacts="39-00-0038 (AWG 18-24)", verify=True)}
# Connector info for parts the overrides ADD (circuit.py CONNECTORS has no entry for them)
STAGE2_ADDED_INFO = {"J_PAUSE": dict(function="PAUSE button and lamp (right deck)", edge="rear-right GH row", awg=26, max_a=0.05)}


def _stage2(chs, ov):
    """Stage-2 view of the chassis circuit: circuit.py PARTS with electronics/chassis_main/overrides.py applied (S2-xx)."""
    import types
    parts, log = ov.apply(chs.PARTS)
    ns = types.SimpleNamespace(**{k: getattr(chs, k) for k in dir(chs) if not k.startswith("__")})
    ns.PARTS = parts
    ns.CONNECTORS = dict(chs.CONNECTORS)
    for oid, spec, why in ov.ADD:
        if spec["ref"].startswith("J_") and spec["ref"] not in ns.CONNECTORS:
            ns.CONNECTORS[spec["ref"]] = dict(STAGE2_ADDED_INFO[spec["ref"]])
    return ns, log


def _pinmap_centres(pm):
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


def _chs_conn_stage2(chs1, chs2, y1, pm):
    """connectors.yaml-equivalent table of the chassis board AFTER the stage-2 overrides, with the placed positions of pinmap.json."""
    P2 = {p["ref"]: p for p in chs2.PARTS}
    cen = _pinmap_centres(pm)
    out = []
    seen = set()
    for c in y1["connectors"]:
        ref = c["ref"]
        seen.add(ref)
        p = P2[ref]
        d = dict(c)
        if ref in MATE_STAGE2:
            m = MATE_STAGE2[ref]
            d.update(family=m["family"], mating_housing=m["housing"], mating_contacts=m["contacts"], verify=True)
        d["board_mpn"] = "%s %s" % (p["manufacturer"], p["mpn"])
        pins = {}
        for k in sorted((k for k in p["pins"] if k != "MP"), key=lambda k: int(k)):
            v = p["pins"][k]
            old = c["pins"].get(int(k)) or c["pins"].get(str(k)) or {}
            awg = old.get("awg") if (v and old.get("net") == (v[1] if v else None)) else None
            if v and awg is None and ref == "J_HEAD1":
                awg = None
            pins[int(k)] = dict(net=(v[1] if v else "NC"), awg=awg)
        d["pins"] = pins
        if ref in cen:
            d["position"] = "stage-2 placement: centre (u, v) = (%.1f, %.1f) mm of RR-CHS-MAIN (out/pinmap.json); stage-1 zone was: %s" % (cen[ref][0], cen[ref][1], c["position"])
            d["uv"] = cen[ref]
        out.append(d)
    for ref, p in ((p["ref"], p) for p in chs2.PARTS):
        if ref.startswith("J_") and ref not in seen and ref in chs2.CONNECTORS:
            info = chs2.CONNECTORS[ref]
            fam = next(k for k in MATE if k in p["value"] or k in p["description"])
            m = MATE[fam]
            n = len([k for k in p["pins"] if k != "MP"])
            d = dict(ref=ref, function=info["function"], detail=p["description"], family=m["family"], board_mpn="%s %s" % (p["manufacturer"], p["mpn"]),
                     mating_housing=(m["housing"] % n if "%" in m["housing"] else m["housing"]), mating_contacts=m["contacts"], verify=(m["verify"] or p["verify"]),
                     position="stage-2 placement: centre (u, v) = (%.1f, %.1f) mm of RR-CHS-MAIN (out/pinmap.json); added by stage 2 (%s)" % (cen[ref][0], cen[ref][1], info["edge"]),
                     uv=cen[ref], max_current_a=info["max_a"],
                     pins={int(k): dict(net=(p["pins"][k][1] if p["pins"][k] else "NC"), awg=(info["awg"] if p["pins"][k] else None)) for k in p["pins"] if k != "MP"})
            out.append(d)
    return dict(board=y1["board"], revision=y1["revision"], connectors=sorted(out, key=lambda c: c["ref"]))


def src():
    if _cache:
        return _cache
    sys.dont_write_bytecode = True
    chs1 = _load("rr_chs_circuit", "electronics/chassis_main/design/circuit.py")
    ov = _load("rr_chs_overrides", "electronics/chassis_main/overrides.py")
    chs, ov_log = _stage2(chs1, ov)
    hd = _load("rr_head_circuit", "electronics/head_acq/design/circuit.py")
    pn = _load("rr_panel_circuit", "electronics/panel/design/circuit.py")
    y1 = _yaml("electronics/chassis_main/design/connectors.yaml")
    chs_pm = json.load(open(os.path.join(ROOT, "electronics/chassis_main/out/pinmap.json")))
    _cache.update(
        chs=chs, chs_stage1=chs1, ov_log=ov_log, hd=hd, pn=pn,
        chs_pinmap=chs_pm, hd_pinmap=json.load(open(os.path.join(ROOT, "electronics/head_acq/out/pinmap.json"))),
        pn_pinmap=json.load(open(os.path.join(ROOT, "electronics/panel/out/pinmap.json"))),
        chs_conn_yaml_stage1=y1,
        chs_conn_yaml=_chs_conn_stage2(chs1, chs, y1, chs_pm),
        contract=_yaml("interface/system/contract.yaml"),
        frames=_yaml("mechanical/common/frames.yaml"),
        fw_chs=_yaml("firmware/chassis/pinmap.yaml"),
        fw_head=_yaml("firmware/head/pinmap.yaml"),
        tof=json.load(open(os.path.join(ROOT, "electronics/tof_carrier/out/pinmap.json"))),
    )
    return _cache


def parts_by_ref(mod):
    return {p["ref"]: p for p in mod.PARTS}


def nets_of(mod):
    """net -> [(ref, pin)] from PARTS (None pins skipped)."""
    n = collections.defaultdict(list)
    for p in mod.PARTS:
        for k, v in p["pins"].items():
            if v:
                n[v[1]].append((p["ref"], str(k)))
    return n
