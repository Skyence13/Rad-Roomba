"""Placement fit check on the generated PCB (run inside the KiCad container):
    tools/docker/kicad.sh python3 electronics/chassis_main/tools/fitcheck.py
Writes reports/fitcheck.json: courtyard area per side, parts in height zones, connector edge positions."""
import json, os, sys
import pcbnew
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import placement as P
b = pcbnew.LoadBoard(os.path.join(HERE, "RR-CHS-MAIN.kicad_pcb"))
ox, oy = [pcbnew.ToMM(v) for v in (b.GetDesignSettings().GetAuxOrigin().x, b.GetDesignSettings().GetAuxOrigin().y)]
def bf(x, y):
    return (round(pcbnew.ToMM(x) - ox, 2), round(oy - pcbnew.ToMM(y), 2))
area = {"F": 0.0, "B": 0.0}
recs = []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    side = "B" if fp.IsFlipped() else "F"
    fp.BuildCourtyardCaches()
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd)
    if cy.OutlineCount() == 0:
        continue
    a = cy.Area() / 1e12
    bb = cy.BBox()
    x0, y1 = bf(bb.GetLeft(), bb.GetTop()); x1, y0 = bf(bb.GetRight(), bb.GetBottom())
    tht = any(p.GetDrillSize().x > 0 for p in fp.Pads())
    if not ref.startswith("H"):
        area[side] += a
    recs.append(dict(ref=ref, side=side, bbox=[x0, y0, x1, y1], area=round(a, 1), tht=tht))
board_a = P.W * P.H - 6 * 3.14159 * (P.HOLE_KO / 2) ** 2
out = {"board_area_mm2": round(P.W * P.H), "usable_area_mm2_minus_hole_keepouts": round(board_a),
       "courtyard_area_mm2": {k: round(v) for k, v in area.items()},
       "utilisation_pct_of_board": {k: round(100 * v / (P.W * P.H), 1) for k, v in area.items()},
       "thermal_zone_bottom_parts": [r["ref"] for r in recs if r["side"] == "B" and r["bbox"][0] < P.THERMAL[2] and r["bbox"][2] > P.THERMAL[0]
                                     and r["bbox"][1] < P.THERMAL[3] and r["bbox"][3] > P.THERMAL[1]],
       "outside_outline": [r["ref"] for r in recs if r["bbox"][0] < -0.01 or r["bbox"][1] < -0.01 or r["bbox"][2] > P.W + 0.01 or r["bbox"][3] > P.H + 0.01],
       "parts": recs}
json.dump(out, open(os.path.join(HERE, "reports", "fitcheck.json"), "w"), indent=0)
print({k: v for k, v in out.items() if k != "parts"})
