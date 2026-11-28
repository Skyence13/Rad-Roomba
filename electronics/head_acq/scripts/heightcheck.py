#!/usr/bin/env python3
"""Height / keep-out fit check of the placed board against mechanical/common/board_envelopes.yaml and the final head
mechanics (host, plain Python).  Heights = the 3D envelope heights the build attached (3d/<fp>_h<h>.step) or the
stock model (taken as 'stock' and listed).  Writes reports/fit_check.json.
    python3 electronics/head_acq/scripts/heightcheck.py"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); B = os.path.dirname(HERE)
pcb = open(os.path.join(B, "RR-HEAD-ACQ.kicad_pcb")).read()
m = re.search(r"\(aux_axis_origin ([-\d.]+) ([-\d.]+)\)", pcb); ox, oy = float(m.group(1)), float(m.group(2))
res = {"over_limit": [], "stock_models": [], "bottom_parts": [], "max_height_mm": 0.0, "parts": 0,
       "j1_zone_max": 0.0, "limits": "top 6.0 mm; 8.3 mm required clear in J1_LANDING u 50-100 v 0-18 (lid blister 8.9); bottom 2.0 mm"}
for blk in re.split(r"\n\t\(footprint ", pcb)[1:]:
    ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
    at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)", blk)
    u, v = float(at.group(1)) - ox, oy - float(at.group(2))
    side = "B" if '(layer "B.Cu")' in blk.split("\n")[1] else "F"
    mod = re.search(r'\(model "([^"]+)"', blk)
    if ref.startswith("H28") or ref.startswith("REF"):
        continue
    res["parts"] += 1
    if side == "B":
        res["bottom_parts"].append(ref)
    if not mod:
        continue
    hm = re.search(r"_h(\d+)p(\d+)\.step", mod.group(1))
    if not hm:
        res["stock_models"].append(ref); continue
    h = float("%s.%s" % hm.groups())
    res["max_height_mm"] = max(res["max_height_mm"], h)
    inj1 = 50 <= u <= 100 and v <= 18
    if inj1:
        res["j1_zone_max"] = max(res["j1_zone_max"], h)
    if h > (8.3 if inj1 else 6.0):
        res["over_limit"].append((ref, round(u, 2), round(v, 2), h))
json.dump(res, open(os.path.join(B, "reports", "fit_check.json"), "w"), indent=1)
print({k: (v if not isinstance(v, list) else len(v)) for k, v in res.items()}, res["over_limit"][:10])
