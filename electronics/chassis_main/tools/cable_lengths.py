"""Re-estimate the harness cable lengths (harness/hdata_cables.py model, unchanged) with the stage-2
connector positions from out/pinmap.json.  Host Python:  python3 electronics/chassis_main/tools/cable_lengths.py
For a connector that moved to the rear-right cluster, leading waypoints of the old rear-left route that lie
left of base y = -40 mm (i.e. the board crossing) are dropped.  Estimates only, as in the harness model."""
import json, math, os, re, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ns = {}
src = open(os.path.join(REPO, "harness", "hdata_cables.py")).read()
exec(compile(src, "hdata_cables.py", "exec"), ns)
pm = json.load(open(os.path.join(HERE, "out", "pinmap.json")))
parts = {p["ref"]: p for p in pm["parts"]}
def pos(ref):
    xy = []
    for q in parts[ref]["pins"]:
        v = q.get("pad_xy_mm")
        if v:
            xy += v if isinstance(v[0], list) else [v]
    return sum(x for x, _ in xy) / len(xy), sum(y for _, y in xy) / len(xy)
MOVED_RIGHT = ("W-019", "W-022", "W-033", "W-040", "W-036")
TAILVIA = {"W-035": [(-95, 69, 105), (-118, 66, 105)], "W-036": [(-67, -72, 95), (-100, -80, 70), (-155, -85, 80)]}
rows = []
for c in ns["CABLES"]:
    path = c.get("path")
    if not path:
        continue
    js = sorted({w["frm"].split(".", 1)[1] for w in c["wires"] if w["frm"].startswith("CHS.")} |
                {w["to"].split(".", 1)[1] for w in c["wires"] if w["to"].startswith("CHS.")})
    if not js:
        continue
    j = "J_PAUSE" if c["id"] == "W-019" else js[0]
    if j not in parts:
        continue
    u, v = pos(j)
    start = ns["chs"](u, v)
    rest = list(path[1:])
    if c["id"] in ("W-035", "W-036"):     # look sensors at the tail (harness mapping): use the rear-corner corridor of W-038 / W-040
        rest = [p for p in TAILVIA[c["id"]]] + [path[-1]]
    if c["id"] in MOVED_RIGHT and u > 80:
        while rest and len(rest) > 1 and rest[0][1] > -40.0:
            rest.pop(0)
    m = re.search(r"\+ 2 x (\d+) mm termination/strain relief \+ (\d+) mm service loop", c.get("basis") or "")
    end, loop = (float(m.group(1)), float(m.group(2))) if m else (25.0, 50.0)
    pl = ns["plen"]([start] + rest)
    new = int(math.ceil((pl + 2 * end + loop) / 10.0) * 10)
    rows.append(dict(cable=c["id"], connector=j, board_uv=[round(u, 1), round(v, 1)], harness_mm=c["length_mm"], stage2_mm=new,
                     budget_mm=c.get("budget_mm"), over_budget=bool(c.get("budget_mm") and new > c["budget_mm"])))
json.dump(rows, open(os.path.join(HERE, "reports", "cable_lengths.json"), "w"), indent=1)
for r in rows:
    if r["budget_mm"] or r["cable"] in ("W-019", "W-022", "W-018", "W-021"):
        print("%-6s %-10s uv=%-14s harness %4d -> stage-2 %4d  budget %s %s" % (r["cable"], r["connector"], r["board_uv"], r["harness_mm"], r["stage2_mm"], r["budget_mm"], "OVER" if r["over_budget"] else ""))
