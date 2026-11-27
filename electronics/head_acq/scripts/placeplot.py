#!/usr/bin/env python3
"""Placement plot from reports/placement.txt + scripts/fp_geometry.json (host, matplotlib).

    PYTHONPATH=tools/eda python3 electronics/head_acq/scripts/placeplot.py [out.png] [u0 u1 v0 v1]
Courtyards coloured by sheet group, pads grey, shield cans / walls, HV trunk, holes with their 7 mm keep-outs,
isolation island and barrier.  Default output: out/RR-HEAD-ACQ-placement.png (whole board)."""
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                         # noqa: E402
from matplotlib.patches import Rectangle, Circle, Polygon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(HERE)
sys.path.insert(0, B)
sys.path.insert(0, HERE)
import overrides            # noqa: E402
import layout               # noqa: E402
import libs                 # noqa: E402
from placecheck import rot_rect   # noqa: E402

GEO = json.load(open(os.path.join(HERE, "fp_geometry.json")))
COL = {"FLOOR": "#1f77b4", "REF": "#2ca02c", "LOGIC": "#9467bd", "POWER_IN": "#d62728", "POWER_REG": "#ff7f0e",
       "HEATER": "#8c564b", "BIAS": "#e377c2", "DAC": "#17becf", "MCU": "#bcbd22", "COMM_ISOLATED": "#7f7f7f",
       "MONITOR": "#393b79", "MECH": "#000000"}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(B, "out", "RR-HEAD-ACQ-placement.png")
    win = [float(a) for a in sys.argv[2:6]] if len(sys.argv) >= 6 else [0, 326, 0, 96]
    parts, _ = overrides.apply(overrides.load_circuit().PARTS)
    pd = {p["ref"]: p for p in parts}
    at = {}
    if os.environ.get("RR_FROM_LAYOUT"):
        from legalize import lane_info
        lay = layout.placement()
        for ref in pd:
            k, pre, kk, ch = lane_info(ref)
            if ref in lay:
                at[ref] = lay[ref]
            elif ch is not None:
                src = "%s%d" % (pre, {"F": 100, "R": 500, "L": 1000}[ch] + kk)
                if src in lay:
                    x, y, r, s_ = lay[src]
                    at[ref] = (x + layout.DU_LANE * k, y, r, s_)
    for line in ([] if at else open(os.path.join(B, "reports", "placement.txt"))):
        m = re.match(r'(\S+)\s+at=\(([-\d.]+), ([-\d.]+), ([-\d.]+), "([FB])"\)', line)
        if m:
            at[m.group(1)] = (float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5))
    w = win[1] - win[0]
    h = win[3] - win[2]
    fig, ax = plt.subplots(figsize=(max(8, w / 326 * 40), max(4, h / 326 * 40 * 1.0 + 1)), dpi=110)
    ax.add_patch(Rectangle((0, 0), 326, 96, fill=False, lw=1.2, ec="k"))
    for lc in layout.LC:
        ax.add_patch(Rectangle((lc - libs.CAN_W / 2, libs.CAN_V0), libs.CAN_W, libs.CAN_D, fill=False, lw=1.0, ec="#555", ls="--"))
    ax.plot([12, 314], [layout.V_TRUNK] * 2, color="red", lw=0.8, alpha=0.6)
    for ref, (x, y) in layout.HOLES.items():
        ax.add_patch(Circle((x, y), 3.5, fill=False, ec="k", lw=0.6))
        ax.add_patch(Circle((x, y), 1.35, color="k"))
    ax.add_patch(Polygon(layout.ISLAND, closed=True, fc="#ffff99", ec="none", alpha=0.5))
    ax.add_patch(Polygon(layout.BARRIER_OUT, closed=True, fill=False, ec="orange", lw=0.8))
    for ref, (x, y, r, s) in at.items():
        p = pd.get(ref)
        if not p:
            continue
        g = GEO.get(p["footprint_hint"])
        blk = p["block"].split("_")[-1] if p["block"].startswith("LANE") else p["block"]
        c = COL.get(blk, "#333333")
        if g and g["courtyard"]:
            a, b, cc, d = rot_rect(g["courtyard"], r)
            ax.add_patch(Rectangle((x + a, y + b), cc - a, d - b, fill=False, ec=c, lw=0.5))
        if g:
            for pad in g["pads"]:
                px, py, pw, ph = pad[1], pad[2], pad[3], pad[4]
                a, b, cc, d = rot_rect((px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2), r)
                ax.add_patch(Rectangle((x + a, y + b), cc - a, d - b, fc="#999999", ec="none", alpha=0.8))
        if w < 120:
            ax.text(x, y, ref, fontsize=3.0, ha="center", va="center", color=c)
    ax.set_xlim(win[0] - 1, win[1] + 1)
    ax.set_ylim(win[2] - 1, win[3] + 1)
    ax.set_aspect("equal")
    ax.set_xlabel("u = X (mm)")
    ax.set_ylabel("v = Y (mm)")
    ax.set_title("RR-HEAD-ACQ placement (top, board frame = envelope frame)  %s" % ("" if w >= 300 else "window %s" % win))
    fig.tight_layout()
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
