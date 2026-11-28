#!/usr/bin/env python3
"""Placement legaliser for the FROZEN (formerly auto-arranged) parts - host side, no KiCad needed.

The tool's auto-arranger knows nothing about the four-lane replication, so in pass 1 some lane-0 parts land outside
the lane-0 block (their copies would hit J1/DAC/J2 areas) and some board-level parts land where a lane copy goes.
This script moves every frozen part that
  * belongs to lane 0 but lies outside its region (channel parts: inside the shield can; trim network and lane logic:
    the lane-logic area or the can), or whose copies at +87.5/175/262.5 mm would overlap anything,
  * is board-level but sits in a lane block, the HV trunk corridor, a hole keep-out, the isolation barrier, or
    outside/inside the isolated island against its nets,
  * overlaps any other courtyard (0.1 mm spacing),
to the nearest legal grid position (0.25 mm) close to the parts it connects to.  Explicit parts are never moved.
    PYTHONPATH=tools/eda python3 electronics/head_acq/scripts/legalize.py      (rewrites layout_frozen.json)
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(HERE)
sys.path.insert(0, B)
sys.path.insert(0, HERE)
import overrides            # noqa: E402
import layout               # noqa: E402
import libs                 # noqa: E402
from placecheck import rot_rect   # noqa: E402

GEO = json.load(open(os.path.join(HERE, "fp_geometry.json")))
GAP = 0.1
TRIM = {5, 6, 7, 8}          # R5 R6 C5 R7 C6 R8: k values per prefix -> see is_trim()


def lane_info(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    pre, n = m.group(1), int(m.group(2))
    if 100 <= n < 900:
        c = n // 100 - 1
        return c % 4, pre, n % 100, ("F" if c < 4 else "R")
    if 1000 <= n < 1400:
        return (n - 1000) // 100, pre, n % 100, "L"
    return None, pre, n, None


def is_trim(pre, k):
    return (pre == "R" and k in (5, 6, 7, 8)) or (pre == "C" and k in (5, 6))


def rect_of(fp, x, y, r):
    g = GEO.get(fp)
    if not g or not g["courtyard"]:
        return None
    a, b, c, d = rot_rect(g["courtyard"], r)
    return (x + a, y + b, x + c, y + d)


def overl(A, Bq, g=GAP):
    return A[0] < Bq[2] + g and Bq[0] < A[2] + g and A[1] < Bq[3] + g and Bq[1] < A[3] + g


def inside(A, R):
    return A[0] >= R[0] and A[1] >= R[1] and A[2] <= R[2] and A[3] <= R[3]


import fnmatch

HV_PATS = ["HV_BUS", "HV_RAW", "HV_RAWF", "HV_SW", "HV_MIR", "HV_G", "HV_BLD", "HV_BFBM", "HV_FBM", "HV_MDM", "HV_CAP",
           "[FR]?_HV1", "[FR]?_HVF", "HEAD_HTR_P", "HEAD_HTR_N", "HTR_PS", "HTR_SW"]


def is_hv(net):
    return bool(net) and any(fnmatch.fnmatchcase(net, p) for p in HV_PATS)


def pad_rects(p, x, y, r):
    g = GEO.get(p["footprint_hint"])
    out = []
    if not g:
        return out
    for pad in g["pads"]:
        num, px, py, pw, ph, prot = pad[0], pad[1], pad[2], pad[3], pad[4], pad[5]
        if prot % 180:
            pw, ph = ph, pw
        a, b, c, d = rot_rect((px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2), r)
        v = p["pins"].get(num)
        out.append(((x + a, y + b, x + c, y + d), v[1] if v else None))
    return out


def rdist(A, Bq):
    dx = max(Bq[0] - A[2], A[0] - Bq[2], 0)
    dy = max(Bq[1] - A[3], A[1] - Bq[3], 0)
    return math.hypot(dx, dy)


def main():
    parts, _ = overrides.apply(overrides.load_circuit().PARTS)
    pd = {p["ref"]: p for p in parts}
    exp = layout.explicit()
    frozen = json.load(open(layout.FROZEN))
    at = dict(exp)
    at.update({k: tuple(v) for k, v in frozen.items() if k not in exp})
    lc0 = layout.LC[0]
    CAN_IN = (lc0 - 17.65, libs.CAN_V0 + 0.25, lc0 + 17.65, libs.CAN_V1 - 0.25)
    LOGIC = (lc0 - 17.9, layout.V_LOGIC0 - 0.3, lc0 + 17.9, 67.4)
    BLOCKS = [(lc - 18.3, 0.0, lc + 18.3, 67.6) for lc in layout.LC]
    TRUNK = (12.0, layout.V_TRUNK - 1.55, 314.0, layout.V_TRUNK + 1.55)
    ISL = (230.2, 0.6, 271.8, 12.8)
    BAR = (226.0, 0.0, 276.0, 17.0)

    # corridors kept free for the lane pre-routes (anode entry stub, HVF via pair) in both channel columns
    CORR = []
    for org in (layout.F_ORG, layout.R_ORG):
        ux = lc0 + org
        CORR += [(ux + 7.62 - 0.7, 8.0, ux + 7.62 + 0.7, 11.2), (ux + 2.45 - 1.0, 8.4, ux + 2.45 + 1.0, 10.4)]

    def region_ok(ref, R):
        k, pre, kk, ch = lane_info(ref)
        if ch is not None:
            if k != 0:
                return False
            if any(overl(R, C, 0.0) for C in CORR):
                return False
            if ch in "FR":
                return inside(R, LOGIC) if is_trim(pre, kk) else inside(R, CAN_IN)
            return inside(R, LOGIC) or inside(R, CAN_IN)
        if not (R[0] >= 0.6 and R[1] >= 0.6 and R[2] <= 325.4 and R[3] <= 95.4):
            return False
        if any(overl(R, Bk, 0.0) for Bk in BLOCKS) or overl(R, TRUNK, 0.0):
            return False
        for (hx, hy) in layout.HOLES.values():
            dx = max(R[0] - hx, 0, hx - R[2])
            dy = max(R[1] - hy, 0, hy - R[3])
            if math.hypot(dx, dy) < 3.6:
                return False
        iso = any(v and (v[1].startswith("BUS_") or v[1] in ("RS485_DP", "RS485_DN", "SYNC_P", "SYNC_N", "J2_PRES", "SYNC_RX_B"))
                  for v in pd[ref]["pins"].values()) and not any(v and v[1] in ("GND", "+3V3") for v in pd[ref]["pins"].values())
        if iso:
            return inside(R, ISL)
        return not overl(R, BAR, 0.0)

    def copies(ref, R):
        k, pre, kk, ch = lane_info(ref)
        if ch is not None:
            return [(R[0] + layout.DU_LANE * j, R[1], R[2] + layout.DU_LANE * j, R[3]) for j in range(4)]
        return [R]

    # obstacle list: every placed part incl. lane copies
    rects = {}
    for ref, (x, y, r, s) in at.items():
        R = rect_of(pd[ref]["footprint_hint"], x, y, r)
        if R:
            rects[ref] = R

    def all_obstacles(skip):
        out = []
        for ref, R in rects.items():
            if ref == skip:
                continue
            out.extend(copies(ref, R))
        return out

    pads = {ref: pad_rects(pd[ref], *at[ref][:3]) for ref in at}

    def hv_ok(ref, x, y, r):
        mine = pad_rects(pd[ref], x, y, r)
        k = lane_info(ref)[3]
        shifts = [layout.DU_LANE * j for j in range(4)] if k is not None else [0.0]
        for sh in shifts:
            for (A, na) in mine:
                A2 = (A[0] + sh, A[1], A[2] + sh, A[3])
                for o, (ox, oy, orr, _s) in at.items():
                    if o == ref:
                        continue
                    if abs(ox - (x + sh)) > 9 and lane_info(o)[3] is None:
                        continue
                    for (Bq, nb) in pads[o]:
                        if lane_info(o)[3] is not None:
                            cand = [(Bq[0] + layout.DU_LANE * j, Bq[1], Bq[2] + layout.DU_LANE * j, Bq[3]) for j in range(4)]
                        else:
                            cand = [Bq]
                        for B2 in cand:
                            if abs(B2[0] - A2[0]) > 8 or abs(B2[1] - A2[1]) > 8:
                                continue
                            if na != nb and (is_hv(na) or is_hv(nb)) and rdist(A2, B2) < 1.05:
                                return False
        return True

    def ok(ref, R, xyr=None):
        if not region_ok(ref, R):
            return False
        obs = all_obstacles(ref)
        for C in copies(ref, R):
            for O in obs:
                if overl(C, O):
                    return False
        if xyr is not None and not hv_ok(ref, *xyr):
            return False
        return True

    by_net = {}
    for p in parts:
        for num, v in p["pins"].items():
            if v and v[1] not in layout.RAILS:
                by_net.setdefault(v[1], []).append(p["ref"])

    def target(ref, x, y):
        pts = []
        for v in pd[ref]["pins"].values():
            if v and v[1] in by_net:
                for o in by_net[v[1]]:
                    if o != ref and o in at:
                        k1 = lane_info(ref)[0]
                        k2 = lane_info(o)[0]
                        ox = at[o][0] - (layout.DU_LANE * k2 if (k2 and k1 == 0) else 0)
                        pts.append((ox, at[o][1]))
        if lane_info(ref)[3] is not None:
            pts = [p for p in pts if lc0 - 18 <= p[0] <= lc0 + 18] or [(lc0, 25.0)]
        if not pts:
            return x, y
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    moved = []
    order = sorted([r for r in at if r in frozen and r not in exp], key=lambda r: r)
    for it in range(2):
        for ref in order:
            x, y, r, s = at[ref]
            R = rects.get(ref)
            if R is None or ok(ref, R, (x, y, r)):
                continue
            tx, ty = target(ref, x, y) if it == 0 else (x, y)
            best = None
            for rad in [i * 0.25 for i in range(0, 260)]:
                n = max(1, int(2 * math.pi * rad / 0.25)) if rad else 1
                for j in range(n):
                    a = 2 * math.pi * j / n
                    cx, cy = round((tx + rad * math.cos(a)) * 4) / 4, round((ty + rad * math.sin(a)) * 4) / 4
                    for rr in (r, (r + 90) % 360):
                        C = rect_of(pd[ref]["footprint_hint"], cx, cy, rr)
                        if ok(ref, C, (cx, cy, rr)):
                            best = (cx, cy, rr, C)
                            break
                    if best:
                        break
                if best:
                    break
            if best:
                at[ref] = (best[0], best[1], best[2], s)
                rects[ref] = best[3]
                pads[ref] = pad_rects(pd[ref], best[0], best[1], best[2])
                frozen[ref] = [best[0], best[1], best[2], s]
                moved.append(ref)
            else:
                print("no legal position for", ref)
    json.dump(frozen, open(layout.FROZEN, "w"), indent=0, sort_keys=True)
    bad = [r for r in exp if r in pd and not hv_ok(r, *at[r][:3])]
    print("explicit parts with HV/heater pad spacing < 1.05 mm to another part:", bad)
    print("moved %d parts: %s" % (len(moved), " ".join(moved)))


if __name__ == "__main__":
    main()
