#!/usr/bin/env python3
"""Independent cross-check of the generated KiCad netlist against the STAGE-1 circuit (design/circuit.py).

The rrkicad build already compares the KiCad netlist pin by pin with the board definition (= circuit.py +
overrides.py).  This script closes the loop to the reviewed baseline itself: every part record of circuit.py
must appear in out/RR-HEAD-ACQ.net with the same value, MPN, manufacturer and DNP state, and every pin must sit
on the same net.  The only accepted differences are the documented S2-01 RENUM entries of overrides.py
(exposed pad 'EP' -> footprint pad number; same pin name, same net).

    python3 electronics/head_acq/scripts/netcheck.py      (host, plain Python 3; exit 0 = identical)
Writes reports/netlist_vs_circuit.json.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
sys.path.insert(0, BOARD)
import overrides  # noqa: E402

NET = os.path.join(BOARD, "out", "RR-HEAD-ACQ.net")


def parse(path):
    text = open(path, encoding="utf-8").read()
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)(.*?)\(tstamps "[^"]*"\)\)', text, re.S):
        ref, body = m.group(1), m.group(2)
        val = re.search(r'\(value "((?:[^"\\]|\\.)*)"\)', body)
        fp = re.search(r'\(footprint "([^"]*)"\)', body)
        props = dict(re.findall(r'\(property \(name "([^"]+)"\) \(value "((?:[^"\\]|\\.)*)"\)\)', body))
        comps[ref] = dict(value=val.group(1) if val else None, footprint=fp.group(1) if fp else None,
                          mpn=props.get("MPN"), mfr=props.get("Manufacturer"),
                          dnp='(property (name "dnp"))' in body)
    pins = {}
    nets_start = text.find("(nets")
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "((?:[^"\\]|\\.)*)"\)(.*?)\)\s*(?=\(net \(code|\)\s*\)\s*$)',
                         text[nets_start:], re.S):
        name = m.group(1)
        for r, p in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2)):
            pins[(r, p)] = name
    return comps, pins


def main():
    base = overrides.load_circuit()
    renum = {}
    for _id, refs, mapping, _why in overrides.RENUM:
        for r in refs:
            renum[r] = mapping
    comps, pins = parse(NET)
    problems = []
    nets_checked = set()
    npins = 0
    for p in base.PARTS:
        ref = p["ref"]
        c = comps.get(ref)
        if c is None:
            problems.append("%s missing from the KiCad netlist" % ref)
            continue
        for key, want in (("value", p["value"]), ("mpn", p["mpn"]), ("mfr", p["manufacturer"]), ("dnp", bool(p["dnp"]))):
            have = c[key]
            if key == "value":
                have = have.replace('\\"', '"') if have else have
            if have != want:
                problems.append("%s %s: netlist %r, circuit.py %r" % (ref, key, have, want))
        for num, v in p["pins"].items():
            kn = renum.get(ref, {}).get(num, num)
            have = pins.get((ref, kn))
            npins += 1
            if v is None:
                if have is not None and not have.startswith("unconnected-"):
                    problems.append("%s.%s: NC in circuit.py, on net %s in KiCad" % (ref, num, have))
            else:
                nets_checked.add(v[1])
                if have != v[1]:
                    problems.append("%s.%s (%s): net %r in KiCad, %r in circuit.py" % (ref, num, v[0], have, v[1]))
    extra = sorted(set(comps) - {p["ref"] for p in base.PARTS})
    if extra:
        problems.append("parts in KiCad but not in circuit.py: %s" % extra)
    res = {"netlist": os.path.relpath(NET, BOARD), "circuit_parts": len(base.PARTS), "kicad_parts": len(comps),
           "pins_compared": npins, "nets_compared": len(nets_checked), "accepted_renumbering": {k: v for k, v in renum.items()},
           "fitted": sum(1 for p in base.PARTS if not p["dnp"]), "dnp": sum(1 for p in base.PARTS if p["dnp"]),
           "problems": problems, "result": "IDENTICAL" if not problems else "DIFFERENT"}
    with open(os.path.join(BOARD, "reports", "netlist_vs_circuit.json"), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    print("parts: circuit.py %d, KiCad %d; pins compared %d on %d nets; problems: %d -> %s" % (
        len(base.PARTS), len(comps), npins, len(nets_checked), len(problems), res["result"]))
    for pr in problems[:40]:
        print("  " + pr)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
