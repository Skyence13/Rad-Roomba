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


def src():
    if _cache:
        return _cache
    sys.dont_write_bytecode = True
    chs = _load("rr_chs_circuit", "electronics/chassis_main/design/circuit.py")
    hd = _load("rr_head_circuit", "electronics/head_acq/design/circuit.py")
    pn = _load("rr_panel_circuit", "electronics/panel/design/circuit.py")
    _cache.update(
        chs=chs, hd=hd, pn=pn,
        chs_conn_yaml=_yaml("electronics/chassis_main/design/connectors.yaml"),
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
