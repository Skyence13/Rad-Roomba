import sys, importlib.util, re, os, glob
sys.path.insert(0, "/home/user/Rad-Roomba/tools/eda")
from rrkicad.symlib import SymbolLibs
spec = importlib.util.spec_from_file_location("c", "/home/user/Rad-Roomba/electronics/head_acq/design/circuit.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
L = SymbolLibs()
seen = {}
for p in c.PARTS:
    key = (p["symbol_hint"], p["mpn"])
    if key in seen: continue
    seen[key] = p["ref"]
    names = {k: (v[0] if v else None) for k, v in p["pins"].items()}
    try:
        sd = L.get(p["symbol_hint"])
    except KeyError as e:
        print("REJ %-8s %-28s %s" % (p["ref"], p["mpn"], p["symbol_hint"])); continue
    st = {q.number: (q.name, q.etype) for q in sd.pins}
    diff = []
    for k, n in sorted(names.items()):
        if k not in st: diff.append("%s:missing" % k); continue
        if n and st[k][0].replace("~","").replace("{","").replace("}","").upper() != n.upper().replace("_N",""):
            diff.append("%s:%s/%s(%s)" % (k, n, st[k][0], st[k][1]))
    extra = sorted(set(st) - set(names))
    print("OK  %-8s %-28s %-50s %s %s" % (p["ref"], p["mpn"], p["symbol_hint"], " ".join(diff), ("extra:" + ",".join(extra)) if extra else ""))
