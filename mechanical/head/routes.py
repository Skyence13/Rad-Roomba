"""Every lead inside the head as a routed polyline (review M5 / M11): plug keep-outs with wire-exit volume for all board connectors, wire and
coax routes with bend radius, lengths for the harness (out/lead_routes.yaml) and tube solids for the interference check.

Coordinates base_link (mm). Routes are the AS-DESIGNED paths of this package: they follow the rear strip, the side strips and the front strip
at stated heights between the fasteners; lengths are centreline length with the corners filleted at the bend radius, plus the stated
termination allowance. Evidence: calculated on tool-checked positions (board file via asbuilt.py, head parameters via hp.py).
"""
from __future__ import annotations

import math

import numpy as np

from . import hp as H

PCB_TOP = H.ACQ["origin"][2] + H.ACQ["thickness"]        # 36.1
# GH plug keep-out (CR-M08 template, electronics: GHR housing ~4.5 + ~2 crimp / strain, recalled UNVERIFIED): from the courtyard edge on the
# mating side 7.25 mm outward, courtyard width, 4.3 mm above the PCB top
GH_DEPTH, GH_H = 7.25, 4.3
GH_REAR = ("J1001", "J1101", "J1201", "J1301", "J2501")
GH_FRONT = ("J2002", "J2003", "J2004", "J2201", "J2402")
TERM = {"micro-fit": 15.0, "gh": 8.0, "u.fl": 6.0, "d2hw": 10.0, "film": 10.0, "tco": 10.0, "ntc": 10.0, "tp": 5.0, "boot": 10.0}   # termination allowance mm
OD = {"20": 1.6, "24": 1.2, "26": 0.9, "28": 0.8, "coax": 1.13}    # thin-wall conductor ODs (UNVERIFIED); 1.13 mm micro-coax (U.FL class)


def to_base(u, v, z=0.0):
    return 83.2 + v, 163.0 - u, PCB_TOP + z


def gh_keepouts(fp):
    """{ref: (x0, x1, y0, y1, z0, z1)} of every mated GH plug incl. its wire-exit volume (rear-edge plugs toward -x, front-edge toward +x)."""
    out = {}
    for ref in GH_REAR + GH_FRONT:
        u0, v0, u1, v1 = fp[ref]["crtyd_uv"]
        va, vb = (v0 - GH_DEPTH, v0 + 0.05) if ref in GH_REAR else (v1 - 0.05, v1 + GH_DEPTH)
        x0, x1 = 83.2 + va, 83.2 + vb
        out[ref] = (x0, x1, 163.0 - u1, 163.0 - u0, PCB_TOP, PCB_TOP + GH_H)
    return out


def length(pts, r):
    """Polyline length with every corner filleted at radius r."""
    pts = np.asarray(pts, float)
    L = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    for i in range(1, len(pts) - 1):
        a, b = pts[i] - pts[i - 1], pts[i + 1] - pts[i]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            continue
        th = math.acos(float(np.clip(a @ b / (na * nb), -1, 1)))
        L -= (2 * math.tan(th / 2) - th) * r
    return L


def _pin_y(fp, ref, pins=None):
    ys = [163.0 - u for n, u, v in fp[ref]["pads_uv"] if n.isdigit() and (pins is None or n in pins)]
    return min(ys), max(ys)


def routes(fp, pig):
    """[{cable_id, lead, from, to, awg, bundle_d, bend_r, points, term}] (pig: pigtail.evaluate() result or None)."""
    R = []
    zw = 39.0                                   # wire height in the rear strip (above the cut-out / screw heads, below the lid)
    xb = 76.6                                   # rear-strip run: plug back 81.8 - 2 straight - R 3.2 (calc.j1_fan_in)
    xp = 83.2 + H.PLUG_V[0]                     # Micro-Fit plug backs
    bx, by = 80.0, 79.5                         # J1 boot (pigtail.BOOT)
    y1a, y1b = _pin_y(fp, "J2001", {"1"}), _pin_y(fp, "J2001", {"7"})
    # W-101 inside the head: J2001 pin 1 (farthest) -> boot; then boot -> plug back (docked free length)
    R.append({"cable_id": "W-101", "lead": "inside head, J2001 -> J1 boot (pin 1, longest)", "from": "HEAD.J2001", "to": "J1 boot", "awg": "20/24",
              "bundle_d": 4.0, "bend_r": 3.2, "term": TERM["micro-fit"] + TERM["boot"],
              "points": [(xp, y1a[0], zw), (xb, y1a[0], zw), (xb, 82.5, zw), (xb, 82.5, H.Z_LID1 + 1.5), (bx, by, 60.0)], "ends_in_boot": True})
    # W-102 inside: J2501 -> J2 boot (wires rise right behind the GH plug, flange notch)
    gx = 83.2 + fp["J2501"]["crtyd_uv"][1] - GH_DEPTH
    g0, g1 = _pin_y(fp, "J2501")
    R.append({"cable_id": "W-102", "lead": "inside head, J2501 -> J2 boot", "from": "HEAD.J2501", "to": "J2 boot", "awg": "26", "bundle_d": 1.2, "bend_r": 1.8,
              "term": TERM["gh"] + TERM["boot"], "points": [(gx, g0, 38.5), (gx - 1.8, g0, 38.5), (gx - 1.8, g0, H.Z_LID1 + 1.5), (78.5, -99.3, 60.0)], "ends_in_boot": True})
    # W-103: J2601 -> heater film tail (S0 chimney notch), cut-out, NTC
    j26 = _pin_y(fp, "J2601")
    co = ((77.0 + 81.6) / 2, H.SHOE_Y - 3.25)
    R.append({"cable_id": "W-103", "lead": "heater element pair: J2601 -> film tail at the S0 chimney notch", "from": "HEAD.J2601", "to": "HEAD-HEATER film tail",
              "awg": "20", "bundle_d": 3.5, "bend_r": 3.2, "term": TERM["micro-fit"] + TERM["film"],
              "points": [(xp, j26[0], zw), (xb, j26[0], zw), (xb, 112.0, zw), (82.0, 113.5, zw), (82.0, 121.0, zw), (78.0, 125.0, zw), (78.0, 125.0, 31.0)]})
    R.append({"cable_id": "W-103", "lead": "cut-out pair: J2601 -> thermal cut-out", "from": "HEAD.J2601", "to": "TCO", "awg": "24", "bundle_d": 1.4, "bend_r": 2.4,
              "term": TERM["micro-fit"] + TERM["tco"], "points": [(xp, j26[0] + 3.0, zw), (xb, j26[0] + 3.0, zw), (xb, 94.0, zw), (74.3, 93.0, zw), (74.3, 88.0, zw),
                                                                   (co[0], co[1], H.Z_SPR1 + 3.4 + 1.2)]})
    R.append({"cable_id": "W-103", "lead": "NTC pair: J2601 -> spreader NTC", "from": "HEAD.J2601", "to": "NTC", "awg": "24", "bundle_d": 2.5, "bend_r": 2.4,
              "term": TERM["micro-fit"] + TERM["ntc"], "points": [(xp, j26[1], zw), (xb, j26[1], zw), (xb, 109.0, zw), (81.5, 109.0, H.Z_SPR1 + 1.6 + 1.2)]})
    # switch leads (W-104 front, W-105 right, W-106 left per harness/cables.csv; board: J2002 = F, J2003 = L, J2004 = R per design/circuit.py).
    # Run: UNDER the board edge (spreader top + 0.25 film to PCB underside = 2.25 mm; no bottom-side parts, checked) at x 178.0, z 33.4; side leads
    # come up from the potted side channel through a spreader / comb-foot hole at (76.0, +-148.75) and run diagonally to y +-161.5 under the board.
    # Front / lid switch leads pass the prototype front fence through 3 mm wall notches (FRONT_NOTCH_Y). The last leg from x 178 to the front
    # plug backs depends on CR-H17 (front GH headers) and is in the length, not in the solid check.
    zu, xu = 33.4, 178.0

    def conn(ref):
        u0, v0, u1, v1 = fp[ref]["crtyd_uv"]
        return 83.2 + v1 + GH_DEPTH, 163.0 - (u0 + u1) / 2
    for cid, ref, kind, s_ in (("W-104", "J2002", "front", 1), ("W-106", "J2003", "side", 1), ("W-105", "J2004", "side", -1), ("W-107", "J2201", "lid", -1)):
        cx, cy = conn(ref)
        tail = [(xu, cy, zu), (182.0, cy, zu), (182.0, cy, PCB_TOP + 2.0), (cx, cy, PCB_TOP + 2.0)]
        if kind == "front":
            yl = s_ * H.FRONT_NOTCH_Y[0]
            pts = [(183.25, yl, 33.8), (183.25, yl, 32.95), (181.0, yl, 32.95), (xu, yl, zu)] + tail
        elif kind == "lid":
            y_e, yh = s_ * (H.SHOE_Y - H.SW["l"] / 2 - 0.3), H.FRONT_NOTCH_Y[1]
            pts = [(183.25, y_e, 39.4), (182.5, y_e, 38.4), (182.5, yh, 38.4), (182.5, yh, 33.5), (181.0, yh, 33.5), (xu, yh, zu)] + tail
        else:
            pts = [(H.XR + 3.6, s_ * H.SW_SIDE["y"], H.SW_SIDE["z"]), (76.0, s_ * 149.2, H.SW_SIDE["z"]), (76.0, s_ * 149.2, zu), (79.8, s_ * 148.75, zu),
                   (88.0, s_ * 161.5, zu), (xu, s_ * 161.5, zu)] + tail
        R.append({"cable_id": cid, "lead": f"{'rail switch' if cid != 'W-107' else 'lid switch'} {kind} -> {ref}", "from": {"W-104": "RAIL-F", "W-105": "RAIL-R", "W-106": "RAIL-L", "W-107": "LID-SW"}[cid],
                  "to": f"HEAD.{ref}", "awg": "26", "bundle_d": 1.8, "bend_r": 4.0, "term": TERM["d2hw"] + TERM["gh"], "points": pts, "solid_upto": len(pts) - len(tail) + 1})
    # aux pigtails W-108..111 (GH-6 J1k01 -> SiPM carrier aux, down the chimney beside the coax) and coax W-112..119 (U.FL -> carrier top)
    for k in range(4):
        lc = 163.0 - (31.75 + 87.5 * k)
        ref = f"J1{k}01"
        gx = 83.2 + fp[ref]["crtyd_uv"][1] - GH_DEPTH
        gy = 163.0 - fp[ref]["u"]
        ctop = (H.STACK["ref_guide"][0] + H.STACK["ref_guide"][1]) / 2 + H.CARRIER["h"] / 2
        R.append({"cable_id": f"W-{108 + k}", "lead": f"lane {k} aux GH-6 -> carrier", "from": f"CARR-AUX{k}", "to": f"HEAD.{ref}", "awg": "28", "bundle_d": 2.0, "bend_r": 3.0,
                  "term": TERM["gh"] + 5.0, "points": [(gx, gy, 38.0), (76.0, gy, 38.0), (75.0, lc + 1.5 * (1 if gy > lc else -1), H.Z_SPR1), (75.0, lc, ctop + 1.0)]})
        for ch, base, du_list in (("F", 100, (-10.38, -15.47)), ("R", 500, (11.87, 6.78))):
            cid = f"W-{112 + k}" if ch == "F" else f"W-{116 + k}"
            zc = (H.STACK["floor_guide"][0] + H.STACK["floor_guide"][1]) / 2 if ch == "F" else (H.STACK["ref_guide"][0] + H.STACK["ref_guide"][1]) / 2
            for du, role in zip(du_list, ("anode", "bias")):
                jy = lc - du
                pts = [(87.1, jy, PCB_TOP + 2.5), (83.2 - 1.0, jy, PCB_TOP + 2.5), (74.75, lc + (1.0 if du < 0 else -1.0), H.Z_SPR1), (74.75, lc + (1.0 if du < 0 else -1.0), zc + H.CARRIER["h"] / 2 + 1.0)]
                R.append({"cable_id": cid, "lead": f"lane {k} {ch}{k} {role} coax: U.FL J{base + 100 * k + (1 if role == 'anode' else 2)} -> carrier",
                          "from": f"CARR-{ch}{k}", "to": f"HEAD.J{base + 100 * k + (1 if role == 'anode' else 2)}", "awg": "coax", "bundle_d": OD["coax"], "bend_r": 6.0,
                          "term": 2 * TERM["u.fl"], "points": pts})
    # cable shield drains (stage 3): W-101.S to TP2004, W-102.S to TP2501
    for cid, ref in (("W-101.S", "TP2004"), ("W-102.S", "TP2501")):
        r = fp[ref]
        tx, ty, _ = to_base(r["u"], r["v"])
        if cid == "W-101.S":
            pts = [(77.0, 84.5, 46.5), (77.0, 84.5, 42.0), (81.0, 84.5, 42.0), (83.0, 84.5, 44.0), (100.0, 84.0, 44.0), (tx, ty, PCB_TOP + 0.5)]
        else:
            pts = [(75.2, -95.0, 46.5), (75.2, -95.0, 42.0), (75.2, -90.5, 42.0), (tx, ty, PCB_TOP + 0.5)]
        R.append({"cable_id": cid, "lead": f"drain -> {ref}", "from": cid.split(".")[0] + " braid", "to": f"HEAD.{ref}", "awg": "24", "bundle_d": 1.2, "bend_r": 2.4,
                  "term": TERM["tp"] + TERM["boot"], "points": pts, "ends_in_boot": True})
    for r in R:
        r["route_mm"] = round(length(r["points"], r["bend_r"]), 1)
        r["length_mm"] = round(r["route_mm"] + r["term"], 0)
    if pig:
        for cid, n in (("W-101", "J1"), ("W-102", "J2")):
            R.append({"cable_id": cid, "lead": f"outside head, {n} boot top -> mated plug back (docked route, free length)", "from": f"{n} boot", "to": f"{n}P",
                      "awg": "cable", "bundle_d": pig[n]["cable_d"], "bend_r": pig[n]["bend_r"], "term": 0.0, "points": [], "route_mm": pig[n]["docked_length_mm"],
                      "length_mm": pig[n]["docked_length_mm"]})
    return R


def tube(pts, d):
    from .geom import compound, cyl2
    pts = np.asarray(pts, float)
    return compound([cyl2(d / 2, tuple(pts[i]), tuple(pts[i + 1])) for i in range(len(pts) - 1) if np.linalg.norm(pts[i + 1] - pts[i]) > 1e-6])


def write_yaml(R, path, meta):
    import yaml
    by = {}
    for r in R:
        by.setdefault(r["cable_id"], []).append({k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if k not in ("points", "cable_id")}
                                                | {"waypoints_base_link_mm": [[round(float(c), 1) for c in p] for p in r["points"]]})
    summary = {}
    for cid, leads in by.items():
        summary[cid] = {"longest_lead_mm": max(l["length_mm"] for l in leads), "leads": leads}
    doc = {"generated_by": "mechanical/head/checks.py (routes.py)", "evidence": "calculated route lengths on tool-checked positions (board file + head model); nothing measured",
           "length_rule": "length_mm = filleted centreline route + termination allowance (term); W-101 / W-102 total = inside + outside rows", **meta, "cables": summary}
    path.write_text(yaml.safe_dump(doc, sort_keys=False, width=160))
