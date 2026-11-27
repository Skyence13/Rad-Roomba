#!/usr/bin/env python3
"""Independent cross-check of the generated KiCad netlist against the STAGE-1 circuit (design/circuit.py).

The rrkicad build already compares the KiCad netlist pin by pin with the board definition (= circuit.py +
overrides.py).  This script closes the loop to the reviewed baseline itself: every part record of circuit.py
must appear in out/RR-HEAD-ACQ.net with the same value, MPN, manufacturer and DNP state, and every pin must sit
on the same net.  The only accepted differences are the documented entries of overrides.py:
  * S2-01 RENUM (exposed pad 'EP' -> footprint pad number; same pin name, same net),
  * stage 3 (S3-xx): the NET entries (pin moved to the listed new net), VALUE entries (value / MPN as listed) and
    ADD entries (new part records, checked pin by pin like the baseline parts).
Any other difference - including an override that did not reach the KiCad netlist - is a problem.

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
    # stage 3: what the overrides are allowed to change, and the overridden record of every changed part
    new_parts, _log = overrides.apply(base.PARTS)
    newby = {p["ref"]: p for p in new_parts}
    moved = {(ref, pin): new for _id, ref, pin, _old, new, _why in overrides.NET}
    valued = {}
    for _id, refs, _old, fields, _why in overrides.VALUE:
        for r in refs:
            valued[r] = fields
    added = [rec["ref"] for _id, rec, _why in overrides.ADD]
    accepted = {"net": 0, "value": 0, "added": 0}
    nets_checked = set()
    npins = 0
    for p in base.PARTS:
        ref = p["ref"]
        c = comps.get(ref)
        if c is None:
            problems.append("%s missing from the KiCad netlist" % ref)
            continue
        q = p
        if ref in valued:
            q = newby[ref]
            accepted["value"] += 1
        for key, want in (("value", q["value"]), ("mpn", q["mpn"]), ("mfr", q["manufacturer"]), ("dnp", bool(q["dnp"]))):
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
                want = v[1]
                if (ref, num) in moved:
                    want = moved[(ref, num)][1]
                    accepted["net"] += 1
                nets_checked.add(want)
                if have != want:
                    problems.append("%s.%s (%s): net %r in KiCad, %r expected (circuit.py %r)" % (ref, num, v[0], have, want, v[1]))
    for ref in added:
        c = comps.get(ref)
        rec = newby[ref]
        if c is None:
            problems.append("added part %s missing from the KiCad netlist" % ref)
            continue
        accepted["added"] += 1
        for key, want in (("value", rec["value"]), ("mpn", rec["mpn"]), ("mfr", rec["manufacturer"]), ("dnp", bool(rec["dnp"]))):
            if c[key] != want:
                problems.append("%s %s: netlist %r, overrides.py %r" % (ref, key, c[key], want))
        for num, v in rec["pins"].items():
            npins += 1
            have = pins.get((ref, num))
            nets_checked.add(v[1])
            if have != v[1]:
                problems.append("%s.%s: net %r in KiCad, %r in overrides.py ADD" % (ref, num, have, v[1]))
    extra = sorted(set(comps) - {p["ref"] for p in base.PARTS} - set(added))
    if extra:
        problems.append("parts in KiCad but not in circuit.py: %s" % extra)
    res = {"netlist": os.path.relpath(NET, BOARD), "circuit_parts": len(base.PARTS), "kicad_parts": len(comps),
           "pins_compared": npins, "nets_compared": len(nets_checked), "accepted_renumbering": {k: v for k, v in renum.items()},
           "fitted": sum(1 for p in base.PARTS if not p["dnp"]), "dnp": sum(1 for p in base.PARTS if p["dnp"]),
           "accepted_stage3": accepted, "stage3_net_entries": len(moved), "stage3_value_refs": len(valued),
           "stage3_added": added,
           "problems": problems,
           "result": ("IDENTICAL" if not (moved or valued or added) else "IDENTICAL except the listed S3 overrides")
           if not problems else "DIFFERENT"}
    with open(os.path.join(BOARD, "reports", "netlist_vs_circuit.json"), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    print("parts: circuit.py %d + %d added, KiCad %d; pins compared %d on %d nets; accepted S3 differences: %s "
          "(of %d NET entries, %d VALUE refs); problems: %d -> %s" % (
              len(base.PARTS), len(added), len(comps), npins, len(nets_checked), accepted, len(moved), len(valued),
              len(problems), res["result"]))
    for pr in problems[:40]:
        print("  " + pr)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
