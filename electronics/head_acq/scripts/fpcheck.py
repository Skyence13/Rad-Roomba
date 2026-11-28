"""List every footprint hint of circuit.py, check it exists in the stock library and that every pin key has a pad."""
import importlib.util, os, pcbnew
spec = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(__file__), "../design/circuit.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
D = "/usr/share/kicad/footprints/"
seen = {}
for p in c.PARTS:
    fp = p["footprint_hint"]
    key = (fp, tuple(sorted(p["pins"])))
    if key in seen: continue
    seen[key] = p["ref"]
    if ":" not in fp:
        print("NOFP  %-8s %s" % (p["ref"], fp)); continue
    lib, name = fp.split(":", 1)
    f = pcbnew.FootprintLoad(D + lib + ".pretty", name) if os.path.isdir(D + lib + ".pretty") else None
    if f is None:
        print("MISS  %-8s %s" % (p["ref"], fp)); continue
    pads = sorted({q.GetNumber() for q in f.Pads()})
    miss = [k for k in p["pins"] if k not in pads]
    extra = [k for k in pads if k not in p["pins"] and k]
    if miss or extra:
        print("PADS  %-8s %-60s missing=%s extra=%s" % (p["ref"], fp, miss, extra))
print("checked", len(seen))
