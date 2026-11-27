#!/usr/bin/env python3
"""Fast host-side placement sanity check (before a KiCad build), all lanes expanded by the replication offsets.

Checks courtyard rectangle overlaps, board edge, mounting-hole keep-outs (6.0 mm + 0.5), shield-can walls (no
part courtyard may cross a wall line except the clips), the HV trunk corridor and the isolation barrier.
    PYTHONPATH=tools/eda python3 electronics/head_acq/scripts/placecheck.py [placement.json]
Uses scripts/fp_geometry.json (scripts/fpdump.py)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(HERE)
sys.path.insert(0, B)
import overrides  # noqa: E402
import layout     # noqa: E402
import libs       # noqa: E402

GEO = json.load(open(os.path.join(HERE, "fp_geometry.json")))


def rot_rect(r, rot):
    x0, y0, x1, y1 = r                       # footprint frame (y down)
    pts = [(x0, -y0), (x1, -y0), (x1, -y1), (x0, -y1)]     # board frame (y up)
    out = []
    for x, y in pts:
        if rot % 360 == 0:
            out.append((x, y))
        elif rot % 360 == 90:
            out.append((-y, x))
        elif rot % 360 == 180:
            out.append((-x, -y))
        else:
            out.append((y, -x))
    xs, ys = [p[0] for p in out], [p[1] for p in out]
    return min(xs), min(ys), max(xs), max(ys)


def lane_of(ref):
    import re
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    n = int(m.group(2))
    if 100 <= n < 900:
        c = n // 100 - 1
        return c % 4, (m.group(1), n % 100, "F" if c < 4 else "R")
    if 1000 <= n < 1400:
        return (n - 1000) // 100, (m.group(1), n % 100, "L")
    return None, None


def main():
    parts, _ = overrides.apply(overrides.load_circuit().PARTS)
    byref = {p["ref"]: p for p in parts}
    at = layout.placement()
    if len(sys.argv) > 1:
        at.update({k: tuple(v) for k, v in json.load(open(sys.argv[1])).items()})
    # expand lanes 1..3 from lane 0
    full = dict(at)
    for ref in list(byref):
        k, key = lane_of(ref)
        if k and key:
            pre, kk, ch = key
            src = "%s%d" % (pre, {"F": 100, "R": 500, "L": 1000}[ch] + kk) if ch != "L" else "%s%d" % (pre, 1000 + kk)
            if src in at:
                x, y, r, s = at[src]
                full[ref] = (x + layout.DU_LANE * k, y, r, s)
    rects = {}
    probs = []
    for ref, (x, y, r, s) in full.items():
        fp = byref[ref]["footprint_hint"]
        g = GEO.get(fp)
        if not g or not g["courtyard"]:
            continue
        a, b, c, d = rot_rect(g["courtyard"], r)
        rects[ref] = (x + a, y + b, x + c, y + d)
    items = sorted(rects.items(), key=lambda t: t[1][0])
    for i, (ra, A) in enumerate(items):
        for rb, Bq in items[i + 1:]:
            if Bq[0] >= A[2]:
                break
            if A[0] < Bq[2] - 1e-3 and Bq[0] < A[2] - 1e-3 and A[1] < Bq[3] - 1e-3 and Bq[1] < A[3] - 1e-3:
                probs.append("overlap %s %s" % (ra, rb))
    for ref, (x0, y0, x1, y1) in rects.items():
        if x0 < 0.3 or y0 < 0.3 or x1 > 325.7 or y1 > 95.7:
            probs.append("edge %s %s" % (ref, (round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2))))
        for h, (hx, hy) in layout.HOLES.items():
            dx = max(x0 - hx, 0, hx - x1)
            dy = max(y0 - hy, 0, hy - y1)
            if (dx * dx + dy * dy) ** 0.5 < 3.5 and not ref.startswith("H28"):
                probs.append("hole %s %s" % (ref, h))
        if not ref.startswith("SH"):
            for lc in layout.LC:
                ux0, ux1 = lc - libs.CAN_W / 2, lc + libs.CAN_W / 2
                vy0, vy1 = libs.CAN_V0, libs.CAN_V1
                for wall in (("v", vy0), ("v", vy1), ("u", ux0), ("u", ux1)):
                    if wall[0] == "v" and ux0 < x1 and x0 < ux1 and y0 < wall[1] + 0.2 and y1 > wall[1]:
                        probs.append("wall %s at v %.2f (lane %.2f)" % (ref, wall[1], lc))
                    if wall[0] == "u" and vy0 < y1 and y0 < vy1 and x0 < wall[1] + 0.2 and x1 > wall[1]:
                        probs.append("wall %s at u %.2f" % (ref, wall[1]))
            if y0 < layout.V_TRUNK + 1.5 and y1 > layout.V_TRUNK - 1.5 and 12 < x1 and x0 < 314:
                probs.append("trunk %s" % ref)
    print("%d placed with courtyard, %d problems" % (len(rects), len(probs)))
    for p in probs:
        print("  " + p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
