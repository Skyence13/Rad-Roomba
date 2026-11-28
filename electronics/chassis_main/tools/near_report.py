"""Distance of every near=-placed part from its anchor pad (host python, after a build).  Writes reports/near_report.json."""
import json, math, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
pm = json.load(open(os.path.join(HERE, "out", "pinmap.json")))
P = {x["ref"]: x for x in pm["parts"]}
def pads(ref):
    out = []
    for q in P[ref]["pins"]:
        v = q.get("pad_xy_mm")
        if v:
            out += v if isinstance(v[0], list) else [v]
    return out
def anchor_xy(a):
    r, _, pn = a.partition(".")
    for q in P[r]["pins"]:
        if q["pin"] == pn:
            v = q["pad_xy_mm"]; return v[0] if isinstance(v[0], list) else v
    xy = pads(r); return [sum(x for x, _ in xy) / len(xy), sum(y for _, y in xy) / len(xy)]
anchors = json.load(open(os.path.join(HERE, "reports", "near_anchors.json")))
rows = []
for ref, a in anchors.items():
    if ref not in P or a.split(".")[0] not in P:
        continue
    ax, ay = anchor_xy(a)
    d = min(math.hypot(x - ax, y - ay) for x, y in pads(ref))
    rows.append((round(d, 1), ref, a))
rows.sort(reverse=True)
json.dump(rows, open(os.path.join(HERE, "reports", "near_report.json"), "w"), indent=0)
far = [r for r in rows if r[0] > float(sys.argv[1] if len(sys.argv) > 1 else 10)]
print(len(rows), "near-placed parts;", len(far), "farther than threshold")
for r in far: print(r)
