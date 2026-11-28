"""Cable routes as geometry (fit review M4 / o2): every robot cable of harness/cables.csv is routed through the real free space of
the assembled body and checked against all solids.

Method (tool-checked):
  1. occupancy: every hard solid (parts, purchased bodies, board components, mated plugs and wire exits, fastener solids) is
     ray-cast on a 1 mm column grid and binned into 3 mm voxels; the free space is the body cavity (inner skin lofts) plus a
     few stated passages outside it (seat reliefs, fairing channel, under-plate dock-lead strip), minus the occupancy dilated
     by the cable radius + 0.5 mm;
  2. path: breadth-first distance field from the far connector port, shortest voxel path from the near port (each port leaves
     its wire-exit volume along the mating direction), then line-of-sight smoothing to a polyline;
  3. check: the cable as a tube solid (polyline cylinders + joint spheres, the bundle diameter) intersected exactly with every
     part except the two connector plugs / device bodies it ends in; bend check at every vertex (fillet radius that fits the
     adjacent segments against the cable's minimum bend radius); clip points every <= 80 mm and at every bend, each with the
     nearest structural part (a free span > 80 mm without a part within 12 mm is reported);
  4. length = route + 2 x termination allowance + service loop; ToF cables must stay <= 270 mm (300 mm I2C limit - 30 mm margin).
Published to mechanical/common/out/cable_routes.yaml (prototype build) / out/cable_routes.yaml (production build).
Cable bundle diameters and bend radii are estimates from the conductor gauges (silicone wire OD by AWG), UNVERIFIED.
"""
from __future__ import annotations

import csv
import math
import time

import numpy as np

from mechanical.common import params as P

from . import boards_body as BB
from .interference import overlaps, z_intervals
from .util import CACHE, Part, box, compound, cyl

HV = 3.0                                    # voxel (mm)
RAY = 1.0                                   # ray pitch (mm)
X0, X1, Y0, Y1, Z0_, Z1_ = -300.0, 245.0, -168.0, 168.0, -2.0, 220.0
NX, NY, NZ = int((X1 - X0) / HV), int((Y1 - Y0) / HV), int((Z1_ - Z0_) / HV)
AWG_OD = {14: 3.4, 16: 2.9, 18: 2.5, 20: 2.1, 22: 1.8, 24: 1.5, 26: 1.25, 28: 1.1, 30: 1.0}   # silicone-insulated wire OD, estimate
TOF_LIMIT = 270.0
CLIP_STEP = 80.0
TOF = {0: "tof_cliff_fl", 1: "tof_cliff_fr", 2: "tof_cliff_rl", 3: "tof_cliff_rr", 4: "tof_look_fwd_left", 5: "tof_look_rev_left", 6: "tof_look_rev_right",
       7: "tof_look_fwd_right", 8: "tof_prox_rl", 9: "tof_prox_rc", 10: "tof_prox_rr"}
FIXED_OD = {"W-008": (7.5, 40.0), "W-009": (6.5, 35.0), "W-012": (5.0, 25.0)}      # shielded leads (harness / parts.yaml)
NO_ROUTE = {"W-002": "inside the battery cassette (pack to cassette coupler half)", "W-024": "optional external sounder, not fitted"}
# Cables whose route could not be closed in this pass (fit review M4): reported as OPEN in every report and in the yaml with the
# reason and the proposed fix; the route gate fails for any other cable that does not route.  An entry is only used if the cable
# actually fails; it never hides a cable that routes.
OPEN_ROUTES = {
    "W-032": "CLIFF_RL seat in the rear lower-hull boss: enclosed pocket (hull wall, tunnel wall, hatch jamb; about 90 free voxels); proposed: lead channel through the tunnel foot wall, or the seat 10 mm inboard",
    "W-033": "CLIFF_RR seat: as W-032 (mirror)",
    "W-039": "REAR_C in the hump brow: the hump is full (cassette top z 144 under the 147 roof), no inside passage; proposed: lead out of the brow over the hump to the left-deck LiDAR gland (external, clipped), or REAR_C moved to the hatch frame top",
    "W-041": "chassis heater: the pad lead end lies under the cassette inside the floor plug; no modelled lead exit from the tunnel floor; proposed: 4 x 3 groove in the floor plug + grommet through the tunnel front at x -74",
    "W-042": "bay NTC: as W-041",
    "W-036": "LOOK_RR: the route round the right-deck devices (E-stop, HANDS-ON, Pause/Stop, charge inlet) to J_TOF6 at the rear edge exceeds the 270 mm budget; proposed (electronics): land LOOK_RR on a right-corner connector or accept a 300 mm cable without margin",
    "W-040": "REAR_R: as W-036 (J_TOF10)",
}


# ----------------------------------------------------------------------------------------------- cable data
def cables():
    """{cable id: {from, to, title, n, od, bend_r, end, loop}} for every robot cable of harness/cables.csv."""
    rows = list(csv.DictReader(open(P.REPO / "harness" / "cables.csv", encoding="utf-8")))
    out = {}
    for r in rows:
        if r["group"] != "robot":
            continue
        c = out.setdefault(r["cable_id"], {"from": r["from_connector"], "to": r["to_connector"], "title": r["cable_title"], "awg": [], "shield": r["shield_and_bonding"]})
        try:
            c["awg"].append(int(r["awg"]))
        except ValueError:
            pass
        c.setdefault("ends", [])
        for e in (r["from_connector"], r["to_connector"]):
            if e and not e.startswith(("SPL", "FUSE")) and e not in c["ends"]:
                c["ends"].append(e)
    for cid, c in out.items():
        ends = c["ends"]
        board = [e for e in ends if e.startswith(("CHS.", "TOF", "PNL."))]
        other = [e for e in ends if e not in board]
        if board and other:
            c["from"], c["to"] = other[0], board[0]
        elif len(ends) >= 2:
            c["from"], c["to"] = ends[0], ends[1]
        d = [AWG_OD.get(a, 1.5) for a in c["awg"]] or [1.5]
        od = 1.25 * math.sqrt(sum(x * x for x in d)) + (0.6 if c["shield"] and not c["shield"].lower().startswith("none") else 0.0)
        od = max(od, max(d))
        if cid in FIXED_OD:
            od, br = FIXED_OD[cid]
        else:
            br = max(6.0, 4.0 * od)
        tof = any(e.startswith("TOF") for e in ends)
        c.update(od=round(od, 1), bend_r=round(br, 1), end=15.0 if tof else 25.0, loop=20.0 if tof else 40.0)   # ToF: crimped GH ends, short loop (300 mm I2C limit)
    return out


# ----------------------------------------------------------------------------------------------- end points
def endpoint(name, byn):
    """(point, outward direction, own part patterns) of a cable end."""
    def far(pn, d, extra=3.0):
        b = byn[pn].bb
        c = ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)
        ext = max(abs(d[0]) * (b[3] - b[0]), abs(d[1]) * (b[4] - b[1]), abs(d[2]) * (b[5] - b[2])) / 2
        return tuple(c[i] + d[i] * (ext + extra) for i in range(3))
    if name.startswith("CHS."):
        ref = name[4:]
        p = BB.PORTS[("RR-CHS-MAIN", ref, "RR-CHS-MAIN")]
        return p["xyz"], p["dir"], [f"RR-CHS-MAIN_plug_{ref}"]
    if name.startswith("PNL."):
        p = BB.PORTS[("RR-PANEL", name[4:], "RR-PANEL")]
        return p["xyz"], p["dir"], [f"RR-PANEL_plug_{name[4:]}"]
    if name.startswith("TOF"):
        t = TOF[int(name[3:].split(".")[0])]
        p = BB.PORTS[("RR-TOF-A", "J1", "rr" + t)]
        return p["xyz"], [p["dir"], tuple(-c for c in P._unit(P.TOF_SENSORS[t]["dir"]))], [f"rr{t}_plug_J1", f"tof_clip_{t[4:]}"]
    if name.startswith("CM5-"):
        k = {"CM5-HDR": "hdr40", "CM5-RJ45": "rj45", "CM5-USB1": "usb_a", "CM5-USB2": "usb_a"}[name]
        p = BB.PORTS[("CM5", k, "CM5")]
        return p["xyz"], p["dir"], [f"CM5_plug_{k}"]
    if name == "CPL-B":
        return far("coupler_fixed", (1, 0, 0)), (1, 0, 0), ["coupler_fixed", "coupler_cassette"]
    if name in ("INLET", "COVER-DEV"):
        n = P.CHARGE_INLET["normal"]
        d = tuple(-c for c in n)
        return far("charge_inlet", d, 6.0), d, ["charge_inlet", "inlet_cover"]
    if name.startswith("MOTOR-"):
        s = 1 if name.endswith("L") else -1
        b = byn[f"motor_{'L' if s > 0 else 'R'}"].bb
        y = b[1] - 3.0 if s > 0 else b[4] + 3.0
        return (0.0, y, (b[2] + b[5]) / 2), (0, -s, 0), [f"motor_{'L' if s > 0 else 'R'}"]
    if name in ("J1R", "J2R"):
        j = P.J_RECEPTACLES[name[:2]]
        d = tuple(-c for c in j["normal"])
        return far(f"{name[:2]}_receptacle", d, 6.0), d, [f"{name[:2]}_receptacle"]
    dev = {"ESTOP-DEV": "estop", "MODE-DEV": "mode_selector", "HANDS-DEV": "hands_on", "REARM-DEV": "rearm_start", "PAUSE-DEV": "pause_stop"}
    if name in dev:
        c = P.PANEL_CONTROLS[dev[name]]
        d = tuple(-v for v in c["normal"])
        return far(f"{dev[name]}_body", d, 4.0), d, [f"{dev[name]}_body", f"{dev[name]}_operator"]
    if name == "DOCK-DEV":
        x, y, z = P.HEAD_DOCK_SWITCH
        return (-15.0, y, z), (-1, 0, 0), ["head_dock_switch", "dock_switch_bracket"]
    if name.startswith("BUMP-"):
        s = 1 if "-L-" in name else -1
        pn = next(n for n in byn if n.startswith("bumper_sw_") and (byn[n].bb[1] > 0) == (s > 0))
        b = byn[pn].bb
        return ((b[0] + b[3]) / 2 + 6.0, (b[1] + b[4]) / 2 - s * 6.0, (b[2] + b[5]) / 2), (0.7, -0.7 * s, 0), [pn]
    if name.startswith("LIDAR"):
        gx, gy = P.LIDAR_GLAND_XY
        n = P.roof_normal(gx, gy)
        g = (gx, gy, P.roof_z(gx, gy))
        return tuple(g[i] - n[i] * 8.0 for i in range(3)), tuple(-c for c in n), ["lidar"]
    if name in ("HTR-CHS", "NTC-BAY"):
        b = byn["chassis_heater_pad"].bb
        return (b[3] + 3.0, 0.0, b[5] + 1.0), (1, 0, 0), ["chassis_heater_pad", "floor_plug"]
    raise KeyError(name)


# ----------------------------------------------------------------------------------------------- voxels
def _vox(shape):
    """Boolean voxel grid of one solid (ray columns at RAY pitch binned into HV voxels)."""
    k, z0, z1 = z_intervals(shape, tol=0.1, h=RAY, off=(0.37, 0.41))
    g = np.zeros((NX, NY, NZ + 2), np.int32)
    if not len(k):
        return np.zeros((NX, NY, NZ), bool)
    gx = k // 1000003
    gy = k - gx * 1000003
    gy = np.where(gy > 500000, gy - 1000003, gy)
    gx = np.where(gy < -500000, gx - 1, gx)
    x, y = gx * RAY + 0.37, gy * RAY + 0.41
    ix, iy = ((x - X0) // HV).astype(int), ((y - Y0) // HV).astype(int)
    iz0, iz1 = np.clip(((z0 - Z0_) // HV).astype(int), 0, NZ), np.clip(((z1 - Z0_) // HV).astype(int) + 1, 0, NZ + 1)
    ok = (ix >= 0) & (ix < NX) & (iy >= 0) & (iy < NY) & (iz1 > iz0)
    np.add.at(g, (ix[ok], iy[ok], iz0[ok]), 1)
    np.add.at(g, (ix[ok], iy[ok], iz1[ok]), -1)
    return np.cumsum(g, axis=2)[:, :, :NZ] > 0


def _box_vox(b):
    m = np.zeros((NX, NY, NZ), bool)
    i0, i1 = int((b[0] - X0) // HV), int((b[1] - X0) // HV) + 1
    j0, j1 = int((b[2] - Y0) // HV), int((b[3] - Y0) // HV) + 1
    k0, k1 = int((b[4] - Z0_) // HV), int((b[5] - Z0_) // HV) + 1
    m[max(i0, 0):max(i1, 0), max(j0, 0):max(j1, 0), max(k0, 0):max(k1, 0)] = True
    return m


def _dilate(m, r):
    out = m.copy()
    for ax in range(3):
        cur = out.copy()
        for k in range(1, r + 1):
            sh = np.zeros_like(cur)
            sl_a, sl_b = [slice(None)] * 3, [slice(None)] * 3
            sl_a[ax], sl_b[ax] = slice(k, None), slice(None, -k)
            sh[tuple(sl_a)] |= cur[tuple(sl_b)]
            sh[tuple(sl_b)] |= cur[tuple(sl_a)]
            out |= sh
    return out


def _idx(p):
    return (int((p[0] - X0) // HV), int((p[1] - Y0) // HV), int((p[2] - Z0_) // HV))


def _ctr(i):
    return (X0 + (i[0] + 0.5) * HV, Y0 + (i[1] + 0.5) * HV, Z0_ + (i[2] + 0.5) * HV)


def _bfs(free, goal):
    """Breadth-first distance field (26-connected) from goal through free voxels."""
    dist = np.full(free.shape, -1, np.int32)
    dist[goal] = 0
    front = np.zeros(free.shape, bool)
    front[goal] = True
    d = 0
    sh = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) != (0, 0, 0)]
    while front.any():
        d += 1
        nb = np.zeros_like(front)
        for a, b, c in sh:
            src = front[max(-a, 0):front.shape[0] - max(a, 0), max(-b, 0):front.shape[1] - max(b, 0), max(-c, 0):front.shape[2] - max(c, 0)]
            nb[max(a, 0):front.shape[0] - max(-a, 0), max(b, 0):front.shape[1] - max(-b, 0), max(c, 0):front.shape[2] - max(-c, 0)] |= src
        nb &= free & (dist < 0)
        dist[nb] = d
        front = nb
        if d > 400:
            break
    return dist


def _descend(dist, start):
    if dist[start] < 0:
        return None
    path = [start]
    cur = start
    while dist[cur] > 0:
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    n = (cur[0] + dx, cur[1] + dy, cur[2] + dz)
                    if not (0 <= n[0] < NX and 0 <= n[1] < NY and 0 <= n[2] < NZ) or dist[n] < 0:
                        continue
                    key = (dist[n], abs(dx) + abs(dy) + abs(dz))
                    if best is None or key < best[0]:
                        best = (key, n)
        if best is None or best[0][0] >= dist[cur]:
            return None
        cur = best[1]
        path.append(cur)
    return path


def _los(free, a, b):
    n = int(max(abs(b[i] - a[i]) for i in range(3)) * 3) + 1
    for t in np.linspace(0, 1, n + 1):
        q = tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))
        if not free[q]:
            return False
    return True


def _smooth(free, path):
    out = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and not _los(free, path[i], path[j]):
            j -= 1
        out.append(path[j])
        i = j
    return out


def occ_hard_core(occ_by, own):
    """Voxels of the big structural skins and the plate (never opened by a stub)."""
    m = np.zeros((NX, NY, NZ), bool)
    for n, v in occ_by.items():
        if n.startswith(("chassis_plate", "battery_tunnel", "battery_cassette", "battery_pack")):
            m |= v
    return m


# ----------------------------------------------------------------------------------------------- main
PASSAGES = [   # stated passages outside the inner-skin cavity (x0, x1, y0, y1, z0, z1); mirrored where marked
    ((-17.0, 1.0, 86.0, 95.5, 90.0, 158.0), True),          # fairing nose channel + shoulder roof slot (M3)
    ((-18.0, 32.0, 54.0, 92.0, 20.0, 33.0), False),         # under-plate dock-lead strip (clipped to the plate underside) to the grommet
    ((24.0, 32.0, 54.0, 62.0, 20.0, 62.0), False),          # dock grommet (28, 58) through the plate and the hull notch above it
    ((35.0, 57.0, 88.0, 101.5, 33.0, 63.0), True),          # front cliff pod bay (plate window) and the hull notch above it
]


def route_all(parts, log=print, only=None):
    t0 = time.time()
    hard = [p for p in parts if p.hard and p.group not in ("tray", "head_placeholder", "tool")]
    byn = {p.name: p for p in parts}
    occ_by = {}
    for p in hard:
        occ_by[p.name] = _vox(p.shape)
    from . import shells
    cav = _vox(shells.UI()) | _vox(shells.LI())
    for b, mir in PASSAGES:
        cav |= _box_vox(b)
        if mir:
            cav |= _box_vox((b[0], b[1], -b[3], -b[2], b[4], b[5]))
    from .fitchecks import SVC_BOX_UV, SVC_H                       # keep the SVC test-pad probe zone free of cables (stage 5 board)
    from .boards_body import _xf_chs
    q = [_xf_chs(u, v, z) for u in SVC_BOX_UV[:2] for v in SVC_BOX_UV[2:] for z in (0.0, SVC_H)]
    occ_by["_svc_probe_zone"] = _box_vox((min(a[0] for a in q) - 2, max(a[0] for a in q) + 2, min(a[1] for a in q) - 2, max(a[1] for a in q) + 2, min(a[2] for a in q), max(a[2] for a in q)))
    log(f"  routes: voxelised {len(hard)} solids in {time.time() - t0:.0f} s")
    occ_all = np.zeros((NX, NY, NZ), bool)
    for v in occ_by.values():
        occ_all |= v
    C = cables()
    res = {}
    tubes = []
    for cid, c in sorted(C.items()):
        if only and cid not in only:
            continue
        if cid in NO_ROUTE:
            res[cid] = {"status": "not routed: " + NO_ROUTE[cid]}
            continue
        try:
            pa, da, own_a = endpoint(c["from"], byn)
            pb, db, own_b = endpoint(c["to"], byn)
        except (KeyError, StopIteration) as e:
            res[cid] = {"status": f"FAIL: end point not modelled ({e})", "ok": False}
            continue
        import fnmatch
        own = own_a + own_b
        occ = np.zeros((NX, NY, NZ), bool)
        for n, v in occ_by.items():
            if not any(fnmatch.fnmatch(n, q) for q in own):
                occ |= v
        r = int(math.ceil((c["od"] / 2 + 0.5) / HV))
        hard_core = occ_hard_core(occ_by, own)
        cands = []
        for rr in (r + 1, r, 0):                                    # candidate paths: wide clearance first, centre line last
            free = cav & ~(_dilate(occ, rr) if rr else occ)
            ends = []
            for p, d in ((pa, da), (pb, db)):
                dl = d if isinstance(d[0], (tuple, list)) else [d]
                cur = p
                i = _idx(p)
                for m, dd in enumerate(dl):                        # stub(s) out of the plug / seat, forced free
                    for k in range(0, (2 if m == 0 else 9) if len(dl) > 1 else 3):
                        q = _idx(tuple(cur[j] + dd[j] * k * HV for j in range(3)))
                        if all(0 <= q[j] < s for j, s in enumerate((NX, NY, NZ))) and not hard_core[q]:
                            free[q] = True
                            i = q
                    cur = _ctr(i)
                ends.append(i)
            for e in ends:
                free[e] = True
            dist = _bfs(free, ends[1])
            vp = _descend(dist, ends[0])
            if vp is not None:
                cands.append((rr, free, vp))
        if not cands:
            da = _bfs(free, ends[0])
            res[cid] = {"status": "FAIL: no collision-free route in the free space", "ok": False, "from": c["from"], "to": c["to"], "od_mm": c["od"],
                        "diag": {"reach_from_far_end_voxels": int((dist >= 0).sum()), "reach_from_near_end_voxels": int((da >= 0).sum()),
                                 "near_end": [round(v, 1) for v in pa], "far_end": [round(v, 1) for v in pb]}}
            continue
        rr, free, vp = cands[0]
        alts = []
        for rr2, fr2, vp2 in cands[1:]:
            sm2 = _smooth(fr2, vp2)
            alts.append([tuple(round(v, 1) for v in pa)] + [tuple(round(v, 1) for v in _ctr(q)) for q in sm2[1:-1]] + [tuple(round(v, 1) for v in pb)])
        sm = _smooth(free, vp)
        pts = [tuple(round(v, 1) for v in pa)] + [tuple(round(v, 1) for v in _ctr(q)) for q in sm[1:-1]] + [tuple(round(v, 1) for v in pb)]
        L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        bends = []
        for a, b, cpt in zip(pts, pts[1:], pts[2:]):
            u = np.subtract(b, a); w = np.subtract(cpt, b)
            la, lb = np.linalg.norm(u), np.linalg.norm(w)
            if la < 1e-6 or lb < 1e-6:
                continue
            th = math.acos(max(-1.0, min(1.0, float(np.dot(u, w) / la / lb))))
            if th < math.radians(3):
                continue
            rfit = min(la, lb) / 2 / math.tan(th / 2)
            bends.append({"at": b, "turn_deg": round(math.degrees(th)), "fits_radius_mm": round(rfit, 1), "ok": rfit >= c["bend_r"]})
        total = L + 2 * c["end"] + c["loop"]
        tof = c["to"].startswith("TOF") or c["from"].startswith("TOF")
        res[cid] = {"from": c["from"], "to": c["to"], "title": c["title"], "od_mm": c["od"], "min_bend_r_mm": c["bend_r"], "polyline": [list(p) for p in pts],
                    "route_mm": round(L, 1), "termination_mm": 2 * c["end"], "service_loop_mm": c["loop"], "length_mm": int(math.ceil(total / 10.0) * 10),
                    "bends": bends, "own_parts": own, "tof_limit_ok": (total <= TOF_LIMIT) if tof else None, "_alts": alts, "_c": c}
        segs = [cyl(c["od"] / 2, math.dist(a, b), a, tuple(np.subtract(b, a))) for a, b in zip(pts, pts[1:]) if math.dist(a, b) > 0.5]
        import cadquery as cq
        joints = [cq.Solid.makeSphere(c["od"] / 2, cq.Vector(*q)) for q in pts[1:-1]]
        if not segs:
            res[cid]["collisions"] = []
            continue
        tubes.append((cid, Part("ROUTE", f"route_{cid}", compound(segs + joints), "purchased", "-", "route"), own))
    # docked J1 / J2 pigtail corridors (fit review M6): fixed polylines from params, docked and at the start of the docking slide
    import cadquery as cq
    PC = P.PIGTAIL_CORRIDOR
    for jn in ("J1", "J2"):
        for state, dx in (("docked", 0.0), ("docking start (head 66 mm forward, plug not mated)", PC["docking_slide"])):
            pts = [tuple(p_) for p_ in PC[jn]]
            if dx:
                pts = [(x + dx, y, z) for x, y, z in pts[:3]]
            d = PC["od"][jn] + PC["margin"]
            segs = [cyl(d / 2, math.dist(a, b), a, tuple(np.subtract(b, a))) for a, b in zip(pts, pts[1:])]
            joints = [cq.Solid.makeSphere(d / 2, cq.Vector(*q)) for q in pts[1:-1]]
            cid = f"PIGTAIL-{jn} {state}"
            own = [f"{jn}_receptacle", f"{jn}_mated_plug", "head_*"]
            cm = cone_margin(pts, PC["od"][jn] / 2)
            lz = P.LIDAR_POSE["base_z"] + P.LIDAR_SCAN_PLANE_ABOVE_BASE
            res[cid] = {"from": f"head boot {jn} (top z 70)", "to": f"{jn} plug on the receptacle", "od_mm": PC["od"][jn], "min_bend_r_mm": PC["bend_r"][jn], "polyline": [list(q) for q in pts],
                        "route_mm": round(sum(math.dist(a, b) for a, b in zip(pts, pts[1:])), 1), "free_length_mm": PC.get("free_length_mm", {}).get(jn),
                        "max_z_mm": round(max(q[2] for q in pts) + PC["od"][jn] / 2, 1), "tof_cone_margin": cm, "lidar_plane_z": lz,
                        "lidar_plane_gap_mm": round(lz - max(q[2] for q in pts) - PC["od"][jn] / 2, 1),
                        "tof_limit_ok": None, "bends": [], "own_parts": own, "corridor": True, "cones_ok": cm["ok"] or bool(dx)}
            tubes.append((cid, Part("ROUTE", f"route_{cid}", compound(segs + joints), "purchased", "-", "route"), own))
    # exact check of every tube against every part (except its own end parts)
    if tubes:
        rows = overlaps([t[1] for t in tubes] + hard, CACHE.parent / "_interference", log=lambda *a: None)
        own = {f"route_{cid}": o for cid, _, o in tubes}
        hits = {k: [] for k in own}
        import fnmatch
        for a, b, v, method, dt in rows:
            ra, rb = a in own, b in own
            if ra == rb:
                continue
            rn, other = (a, b) if ra else (b, a)
            if v > 1.0 and not any(fnmatch.fnmatch(other, q) for q in own[rn]):
                hits[rn].append((other, round(v, 1)))
        for cid, _, _ in tubes:
            res[cid]["collisions"] = hits[f"route_{cid}"]
    # retry: a cable whose first path touches a part takes the first collision-free alternative (narrower clearance search)
    import fnmatch as _fn
    for level in (0, 1):
        retry = [(cid, r) for cid, r in res.items() if r.get("collisions") and r.get("_alts") and len(r["_alts"]) > level]
        if not retry:
            break
        alt_parts = []
        for cid, r in retry:
            pts = r["_alts"][level]
            od = r["od_mm"]
            segs = [cyl(od / 2, math.dist(a, b), a, tuple(np.subtract(b, a))) for a, b in zip(pts, pts[1:]) if math.dist(a, b) > 0.5]
            if segs:
                alt_parts.append((cid, Part("ROUTE", f"route_{cid}_alt{level}", compound(segs + [cq.Solid.makeSphere(od / 2, cq.Vector(*q)) for q in pts[1:-1]]), "purchased", "-", "route"), pts))
        rows = overlaps([a[1] for a in alt_parts] + hard, CACHE.parent / "_interference", log=lambda *a: None)
        for cid, prt, pts in alt_parts:
            own = res[cid]["own_parts"]
            hit = [(b if a == prt.name else a, round(v, 1)) for a, b, v, m_, dt in rows if prt.name in (a, b) and v > 1.0]
            hit = [h for h in hit if not h[0].startswith("route_") and not any(_fn.fnmatch(h[0], q) for q in own)]
            if not hit:
                c = res[cid]["_c"]
                L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
                total = L + 2 * c["end"] + c["loop"]
                res[cid].update(polyline=[list(q) for q in pts], route_mm=round(L, 1), length_mm=int(math.ceil(total / 10.0) * 10), collisions=[],
                                tof_limit_ok=(total <= TOF_LIMIT) if res[cid]["tof_limit_ok"] is not None else None, path_choice=f"alternative {level + 1} (narrower clearance)")
    for r in res.values():
        r.pop("_alts", None)
        r.pop("_c", None)
    # clip points: every <= CLIP_STEP along the route and at bends, nearest structural part
    struct = [p for p in hard if p.kind in ("printed", "fabricated")]
    import cadquery as cq
    for cid, r in res.items():
        if "polyline" not in r:
            continue
        pts = r["polyline"]
        clips, run = [], 0.0
        for a, b in zip(pts, pts[1:]):
            seg = math.dist(a, b)
            n = max(1, int(math.ceil(seg / CLIP_STEP)))
            for k in range(1, n + 1):
                q = tuple(a[i] + (b[i] - a[i]) * k / n for i in range(3))
                v = cq.Vertex.makeVertex(*q)
                best = min(((p.shape.distance(v), p.name) for p in struct if all(p.bb[i] - 15 <= q[i] <= p.bb[i + 3] + 15 for i in range(3))), default=(999.0, "-"))
                clips.append({"at": [round(c_, 1) for c_ in q], "to_part": best[1], "gap_mm": round(best[0], 1), "ok": best[0] <= 12.0})
        r["clips"] = clips[:-1] if not r.get("corridor") else []
        r["ok"] = not r.get("collisions") and (r["tof_limit_ok"] is not False) and r.get("cones_ok", True)
        r["status"] = "routed" if r["ok"] else "FAIL"
    for cid, r in res.items():
        if r.get("ok") is False and cid in OPEN_ROUTES:
            r["status"] = "OPEN FINDING: " + OPEN_ROUTES[cid]
            r["open"] = True
    log(f"  routes: {sum(1 for r in res.values() if r.get('ok'))}/{sum(1 for r in res.values() if 'ok' in r)} cables routed collision-free, {time.time() - t0:.0f} s")
    return res


def cone_margin(pts, radius, need_mm=20.0, need_deg=10.0):
    """Smallest clearance of a polyline tube (radius) to every ToF field-of-view cone (18 deg full angle, UNVERIFIED FoV):
    mm (perpendicular to the cone surface) and degrees off the cone edge; ok if >= need_mm OR >= need_deg everywhere."""
    half = math.radians(9.0)
    worst = (1e9, 1e9, None)
    for a, b in zip(pts, pts[1:]):
        n = max(2, int(math.dist(a, b) / 2.0))
        for k in range(n + 1):
            q = [a[i] + (b[i] - a[i]) * k / n for i in range(3)]
            for name, t in P.TOF_SENSORS.items():
                o, d = t["xyz"], P._unit(t["dir"])
                v = [q[i] - o[i] for i in range(3)]
                s_ = sum(v[i] * d[i] for i in range(3))
                if s_ <= 0:
                    continue
                perp = math.sqrt(max(sum(c * c for c in v) - s_ * s_, 0.0))
                mm = (perp - s_ * math.tan(half)) * math.cos(half) - radius
                deg = math.degrees(math.atan2(perp, s_) - half) - math.degrees(math.atan2(radius, math.hypot(perp, s_)))
                if mm < worst[0]:
                    worst = (mm, deg, name)
    ok = worst[0] >= need_mm or worst[1] >= need_deg
    return {"min_mm": round(worst[0], 1), "deg_at_min": round(worst[1], 1), "sensor": worst[2], "ok": ok, "rule": f">= {need_mm:.0f} mm or >= {need_deg:.0f} deg"}


def write_yaml(res, path, build):
    import yaml
    doc = {"schema": "rr-cable-routes/1", "build": build, "evidence": "tool-checked: voxel route through the body free space, then exact tube-vs-solid "
           "intersection with every part; lengths = route + 2 x termination + service loop (calculated). Bundle OD and bend radius are estimates (UNVERIFIED).",
           "generated_by": "mechanical/prototype_x1c/rrx/routes.py", "tof_length_limit_mm": TOF_LIMIT, "cables": res}
    import json
    doc = json.loads(json.dumps(doc, default=lambda o: list(o) if isinstance(o, tuple) else str(o)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, width=200), encoding="utf-8")
