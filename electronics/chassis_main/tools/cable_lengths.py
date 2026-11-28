"""Board-side view of the harness cable lengths.  Host Python:  python3 electronics/chassis_main/tools/cable_lengths.py

Stage 3 (IB-57): the earlier version re-routed every cable itself and took the FIRST point of each harness path as the
board connector, which is wrong for cables whose path starts at the device (W-001/003/004/005/006/007).  The harness
generator (harness/hdata_cables.py) now computes every length from this board's out/pinmap.json itself, so this tool no
longer estimates anything: it lists, for each cable that ends on RR-CHS-MAIN, the board connector, its pad centre in the
board frame (u, v) from out/pinmap.json and the harness generator's length and budget.  reports/cable_lengths.json keeps
its fields (stage2_mm = the harness generator's length) because harness/cross_check.py reads it.
"""
import json
import os
import types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(REPO, "harness", "hdata_cables.py")
mod = types.ModuleType("hdata_cables")
mod.__file__ = SRC                                   # the generator finds the repository (and out/pinmap.json) from __file__
exec(compile(open(SRC).read(), SRC, "exec"), mod.__dict__)
pm = json.load(open(os.path.join(HERE, "out", "pinmap.json")))
parts = {p["ref"]: p for p in pm["parts"]}


def centre(ref):
    xy = []
    for q in parts[ref]["pins"]:
        v = q.get("pad_xy_mm")
        if v:
            xy += v if isinstance(v[0], list) else [v]
    return round(sum(x for x, _ in xy) / len(xy), 1), round(sum(y for _, y in xy) / len(xy), 1)


rows = []
for c in mod.CABLES:
    js = sorted({e.split(".", 2)[1] for w in c["wires"] for e in (w["frm"], w["to"]) if e.startswith("CHS.")})
    js = [j for j in js if j in parts]
    if not js:
        continue
    for j in js:
        rows.append(dict(cable=c["id"], connector=j, board_uv=list(centre(j)), harness_mm=c["length_mm"], stage2_mm=c["length_mm"],
                         budget_mm=c.get("budget_mm"), over_budget=bool(c.get("budget_mm") and c["length_mm"] > c["budget_mm"])))
json.dump(rows, open(os.path.join(HERE, "reports", "cable_lengths.json"), "w"), indent=1)
for r in rows:
    print("%-6s %-10s uv=%-14s harness %4d mm  budget %s %s" % (r["cable"], r["connector"], r["board_uv"], r["harness_mm"],
                                                             r["budget_mm"], "OVER" if r["over_budget"] else ""))
