"""Dump courtyard bbox + pads (footprint frame, y down) of every footprint the board uses -> scripts/fp_geometry.json.
Run in the KiCad container after a schematic/build run (needs rr_local.pretty):
    tools/docker/kicad.sh python3 electronics/head_acq/scripts/fpdump.py"""
import json, os, sys, pcbnew
HERE = os.path.dirname(os.path.abspath(__file__)); B = os.path.dirname(HERE)
sys.path.insert(0, B)
import overrides
parts, _ = overrides.apply(overrides.load_circuit().PARTS)
out = {}
for p in parts:
    fp = p["footprint_hint"]
    if fp in out or ":" not in fp: continue
    lib, name = fp.split(":", 1)
    d = os.path.join(B, "rr_local.pretty") if lib == "rr_local" else "/usr/share/kicad/footprints/%s.pretty" % lib
    f = pcbnew.FootprintLoad(d, name)
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount():
        bb = cy.BBox(); c = [bb.GetLeft()/1e6, bb.GetTop()/1e6, bb.GetRight()/1e6, bb.GetBottom()/1e6]
    else:
        c = None
    pads = []
    for q in f.Pads():
        pos = q.GetPosition(); s = q.GetSize()
        pads.append([q.GetNumber(), round(pos.x/1e6, 4), round(pos.y/1e6, 4), round(s.x/1e6, 4), round(s.y/1e6, 4),
                     q.GetOrientationDegrees(), round(q.GetDrillSize().x/1e6, 3)])
    out[fp] = {"courtyard": c, "pads": pads}
json.dump(out, open(os.path.join(HERE, "fp_geometry.json"), "w"), indent=0)
print(len(out), "footprints")
