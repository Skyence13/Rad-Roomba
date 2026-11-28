"""J1 / J2 pigtails outside the head (review M6): exit boots on the lid, cable paths docked (mated), parked (unmated, plug in its holster)
and during the docking stroke, and the check against the body's nose solids.

Head side (this package): the pigtails leave the head VERTICALLY (+z) from two cable-breakout boots on the lid rear strip, forward of the nose-cowl
V (the cowl is behind / above the boots in the docked state). Inside the head the conductors run from the plug backs along the rear strip to the
boot and rise through a small lid slot; the jacket ends in the boot (potted), so the boot is the strain relief and the clip point: z 46..70, x 72..88,
outside datum A (x 65.7 plane), the shoe seating faces and the latch box. The AWG 18 / 20 change (if the harness keeps AWG 18 in the cable) is made
inside the J1 boot (static, potted, not in a bend); preferred: AWG 20 all the way to the M16 contacts (contact range UNVERIFIED).

Body side (read-only): receptacle pose = mechanical.common.params.J_RECEPTACLES (xyz, normal); mated-plug back point from the body's own
`J?_mated_plug.step` (cylinder fit of its bounding box along the receptacle normal); nose solids from mechanical/prototype_x1c/out/parts_base_link.
Cable data: mechanical/common/purchased/parts.yaml (J1 7.5 mm, R 40; J2 6.5 mm, R 35); harness/cables.csv W-101 / W-102.
Evidence: tool-checked (solid intersection on the body STEP files) + calculated (curve radius, length).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import hp as H
from .geom import box, compound, cyl, cyl2, fuse_all

REPO = Path(__file__).resolve().parents[2]
BODY_DIR = REPO / "mechanical" / "prototype_x1c" / "out" / "parts_base_link"
BODY_PARTS = ("nose_cowl", "lower_hull_FL", "lower_hull_FR", "shoulder_L", "shoulder_R", "front_bulkhead", "latch_arm", "head_latch", "chassis_plate",
              "receiver_channel_L", "receiver_channel_R", "J1_receptacle", "J2_receptacle", "J1_mated_plug", "J2_mated_plug")
DOCK_STROKE = 66.0          # mm: shoe engagement travel at the end of docking (review M6; channel x 2..65.7 against the shoe x 4..69.9)
CLEAR = 2.0                 # mm clearance required between a cable and any body solid
BOOT_TOP_Z = 70.0
# boot = cable-breakout housing on the lid (x0, x1, y0, y1, z0, z1), cable centre (x, y) at the boot top, lid slot for the conductors
BOOT = {n: {"box": H.BOOT_BOX[n], "cable_xy": H.BOOT_CABLE_XY[n], "slot": H.BOOT_SLOTS[n]} for n in ("J1", "J2")}
ENV_KEY = {"J1": "j1_receptacle", "J2": "j2_receptacle"}


def cable(name):
    e = L.env(ENV_KEY[name])
    return e["cable_d"], e["cable_bend_r"]


def plug_back(name):
    """Mated-plug back (cable end) point and the receptacle normal, from the body's mated-plug STEP (cylinder-along-normal fit of its bbox)."""
    import cadquery as cq
    n = np.array(P.J_RECEPTACLES[name]["normal"], float)
    n /= np.linalg.norm(n)
    bb = cq.importers.importStep(str(BODY_DIR / f"{name}_mated_plug.step")).val().BoundingBox()
    lo, hi = np.array([bb.xmin, bb.ymin, bb.zmin]), np.array([bb.xmax, bb.ymax, bb.zmax])
    f = np.sqrt(np.clip(1 - n ** 2, 0, 1))
    # span_i = Lp |n_i| + 2 r f_i  (two unknowns: least squares over the three axes)
    A = np.stack([np.abs(n), 2 * f], axis=1)
    Lp, r = np.linalg.lstsq(A, hi - lo, rcond=None)[0]
    start = np.where(n >= 0, lo + r * f, hi - r * f)
    return start + Lp * n, n, float(Lp), float(r)


def bezier(p0, t0, p3, t3, a, b, n=120):
    """Cubic from p0 (leaving along t0) to p3 (arriving along t3)."""
    p1, p2 = p0 + a * t0, p3 - b * t3
    s = np.linspace(0, 1, n)[:, None]
    pts = (1 - s) ** 3 * p0 + 3 * (1 - s) ** 2 * s * p1 + 3 * (1 - s) * s ** 2 * p2 + s ** 3 * p3
    d1 = 3 * (1 - s) ** 2 * (p1 - p0) + 6 * (1 - s) * s * (p2 - p1) + 3 * s ** 2 * (p3 - p2)
    d2 = 6 * (1 - s) * (p2 - 2 * p1 + p0) + 6 * s * (p3 - 2 * p2 + p1)
    rad = np.linalg.norm(d1, axis=1) ** 3 / np.maximum(np.linalg.norm(np.cross(d1, d2), axis=1), 1e-12)
    length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    return pts, float(rad.min()), length


def _arc(p, a, b, R, n=24):
    """Arc of radius R starting at p heading a and ending heading b; returns points and end point."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    c = float(np.clip(a @ b, -1, 1))
    th = math.acos(c)
    if th < 1e-9:
        return [p], p, 0.0
    m = b - c * a
    m /= np.linalg.norm(m)
    pts = [p + R * (math.sin(th * k / n) * a + (1 - math.cos(th * k / n)) * m) for k in range(n + 1)]
    return pts, pts[-1], th


def csc(p0, t0, p3, t3, R, iters=200):
    """3-D curve-straight-curve path (both arcs of radius R): leaves p0 along t0, arrives at p3 along t3. Fixed-point on the straight's
    direction; returns (points, length) or None."""
    u = (p3 - p0) / np.linalg.norm(p3 - p0)
    for _ in range(iters):
        _, e1, _ = _arc(p0, t0, u, R)
        # arc 2 run backwards from p3: starts at p3 heading -t3, ends heading -u
        _, s2, _ = _arc(p3, -t3, -u, R)
        v = s2 - e1
        if np.linalg.norm(v) < 1e-6:
            return None
        un = v / np.linalg.norm(v)
        if np.linalg.norm(un - u) < 1e-9:
            break
        u = 0.5 * u + 0.5 * un
        u /= np.linalg.norm(u)
    a1, e1, th1 = _arc(p0, t0, u, R)
    a2r, s2, th2 = _arc(p3, -t3, -u, R)
    if (s2 - e1) @ u <= 0:
        return None
    pts = np.array(a1 + list(reversed(a2r)))
    return pts, R * th1 + float(np.linalg.norm(s2 - e1)) + R * th2


def docked_path(name, straight_end=10.0):
    """From the boot top (leaving +z) into the plug back (arriving along -n after `straight_end` of straight behind the backshell): curve-
    straight-curve at the catalogue bend radius + 5 mm; a free vertical rise is added if it shortens nothing but clears the nose."""
    d, rb = cable(name)
    B, n, Lp, r = plug_back(name)
    x, y = BOOT[name]["cable_xy"]
    R = rb + 5.0
    best = None
    for rise in (0.0, 10.0, 20.0, 30.0, 45.0, 60.0):
        p0 = np.array([x, y, BOOT_TOP_Z + rise])
        sol = csc(p0, np.array([0, 0, 1.0]), B + straight_end * n, -n, R)
        if sol and (best is None or sol[1] + rise < best[1]):
            best = (rise, sol[1] + rise, sol[0])
    rise, length, pts = best
    pts = np.vstack([[x, y, BOOT_TOP_Z], pts, B])
    return {"points": pts, "length_mm": length + straight_end, "min_radius_mm": R, "rise_mm": rise, "plug_back": B, "normal": n,
            "plug_len_fit": Lp, "plug_r_fit": r, "cable_d": d, "bend_r": rb}


def parked_path(name, length):
    """Unmated, plug stowed head-down in a holster cup on the lid: up from the boot, a 180-degree loop forward at the bend radius, down into the
    plug back. Same cable length as the docked route."""
    d, rb = cable(name)
    plug_len = 62.0 + 15.0 if name == "J1" else 55.0 + 12.0          # plug_l + backshell (parts.yaml, backshell UNVERIFIED)
    x, y = BOOT[name]["cable_xy"]
    z_back = H.Z_LID1 + 2.0 + plug_len                              # plug standing head-down in the holster cup (floor 2 mm)
    R = (H.HOLSTER_XY[name][0] - x) / 2
    rise = (length - math.pi * R + z_back - BOOT_TOP_Z) / 2       # length = rise + pi R + drop, drop = (BOOT_TOP_Z + rise) - z_back
    zt = BOOT_TOP_Z + rise
    pts = [np.array([x, y, BOOT_TOP_Z]), np.array([x, y, zt])]
    for k in range(1, 37):
        a = math.pi * k / 36
        pts.append(np.array([x + R - R * math.cos(a), y, zt + R * math.sin(a)]))
    pts.append(np.array([x + 2 * R, y, z_back]))
    holster_xy = H.HOLSTER_XY[name]
    return {"points": np.array(pts), "rise_mm": rise, "loop_r_mm": R, "holster_xy": holster_xy, "plug_len": plug_len, "z_back": z_back, "apex_z": zt + R,
            "cable_d": d}


def tube(points, d):
    r = d / 2
    segs = [cyl2(r, tuple(points[i]), tuple(points[i + 1])) for i in range(len(points) - 1) if np.linalg.norm(points[i + 1] - points[i]) > 1e-6]
    return compound(segs)


def plug_solid(back, axis, length, dia):
    """Plug envelope from its back point along `axis` (toward the mating end)."""
    return cyl(dia / 2, length, tuple(back), tuple(axis))


def boot_solid(name):
    x0, x1, y0, y1, z0, z1 = BOOT[name]["box"]
    return box(x0, x1, y0, y1, z0, z1)




_BODY = {}


def body_solids():
    """Body nose / receiver solids (read-only STEP). Missing files raise: the check must not pass silently."""
    import cadquery as cq
    if not _BODY:
        for n in BODY_PARTS:
            f = BODY_DIR / f"{n}.step"
            if not f.exists():
                raise FileNotFoundError(f"body solid {f} missing: run mechanical/prototype_x1c/build.sh")
            _BODY[n] = cq.importers.importStep(str(f)).val()
    return _BODY


def _classifiers():
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    if "_cls" not in _BODY:
        cl = []
        for n, b in body_solids().items():
            for so in b.Solids():
                bb = so.BoundingBox()
                cl.append((n, so, (bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax), BRepClass3d_SolidClassifier(so.wrapped)))
        _BODY["_cls"] = cl
    return _BODY["_cls"]


def _inside(p, exclude=()):
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN
    for n, so, b, c in _classifiers():
        if n in exclude or not (b[0] <= p[0] <= b[3] and b[1] <= p[1] <= b[4] and b[2] <= p[2] <= b[5]):
            continue
        c.Perform(gp_Pnt(*map(float, p)), 1e-4)
        if c.State() == TopAbs_IN:
            return n
    return None


def _rings(points, radius, step=6.0, k=8):
    """Points on circles of `radius` round the centreline (every `step` mm)."""
    pts = np.asarray(points, float)
    out = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        L = np.linalg.norm(b - a)
        if L < 1e-9:
            continue
        t = (b - a) / L
        ref = np.array([0, 0, 1.0]) if abs(t[2]) < 0.9 else np.array([1.0, 0, 0])
        e1 = np.cross(t, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(t, e1)
        for s in np.arange(0, L, step):
            c = a + s * t
            out += [c] + [c + radius * (math.cos(2 * math.pi * j / k) * e1 + math.sin(2 * math.pi * j / k) * e2) for j in range(k)]
    return out


def clash(points, d, exclude=(), shift=0.0, extra=()):
    """Body solids hit by the cable (sampled: centreline + surface rings every 4 mm) or by the extra sample points; head shifted +shift in x."""
    hits = {}
    for p in list(_rings(points, d / 2)) + list(extra):
        q = np.array(p, float) + np.array([shift, 0, 0])
        n = _inside(q, exclude)
        if n:
            hits[n] = hits.get(n, 0) + 1
    return sorted(hits.items())


def min_gap(points, d, exclude=()):
    """Largest tested clearance ring (0.5 .. 8 mm beyond the cable surface) with no sample inside a body solid."""
    ok = 0.0
    for g in (CLEAR, 5.0):
        if any(_inside(p, exclude) for p in _rings(points, d / 2 + g)):
            return ok
        ok = g
    return ok


def _box_samples(b, step=3.0):
    x0, x1, y0, y1, z0, z1 = b
    xs, ys, zs = np.arange(x0, x1 + 1e-6, step), np.arange(y0, y1 + 1e-6, step), np.arange(z0, z1 + 1e-6, step)
    return [(x, y, z) for x in xs for y in ys for z in zs if x in (xs[0], xs[-1]) or y in (ys[0], ys[-1]) or z in (zs[0], zs[-1])]


def _cyl_samples(c, axis, r, L, step=3.0):
    c, axis = np.array(c, float), np.array(axis, float)
    return _rings([c, c + L * axis], r, step)


def evaluate():
    """Cached wrapper: the sampled body check takes minutes, so the result is cached on the body STEP files' content hash + the head inputs."""
    import hashlib
    import inspect
    import json
    from .geom import CACHE
    h = hashlib.sha1()
    for n in BODY_PARTS:
        h.update((BODY_DIR / f"{n}.step").read_bytes())
    h.update(inspect.getsource(inspect.getmodule(evaluate)).encode())
    h.update(json.dumps([H.BOOT_BOX, H.BOOT_CABLE_XY, H.HOLSTER_XY, H.HOLSTER_H, H.Z_LID1, P.J_RECEPTACLES], sort_keys=True, default=str).encode())
    f = CACHE / f"pigtail_{h.hexdigest()[:16]}.json"
    if f.exists():
        res = json.loads(f.read_text())
    else:
        res = _evaluate()
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({k: ({kk: vv for kk, vv in v.items() if not kk.startswith("_")} if isinstance(v, dict) and k in ("J1", "J2") else v)
                                 for k, v in res.items()}, default=float))
        res = json.loads(f.read_text())
    for name in ("J1", "J2"):
        res[name]["_docked_points"] = docked_path(name)["points"]
        res[name]["_parked_points"] = parked_path(name, docked_path(name)["length_mm"])["points"]
    return res


def _evaluate():
    """Both pigtails: docked (mated) path, parked path, stroke sweep; returns a dict for checks / report / lead_routes."""
    res = {"stroke_mm": DOCK_STROKE, "body_dir": str(BODY_DIR.relative_to(REPO)),
           "body_files": {n: __import__("time").strftime("%Y-%m-%d %H:%M", __import__("time").gmtime((BODY_DIR / f"{n}.step").stat().st_mtime)) for n in BODY_PARTS}}
    for name in ("J1", "J2"):
        dk = docked_path(name)
        d = dk["cable_d"]
        e = L.env(ENV_KEY[name])
        pts = dk["points"]
        dock_clash = clash(pts[:-2], d, exclude=(f"{name}_mated_plug",))
        gap = min_gap(pts[1:-3], d, exclude=(f"{name}_mated_plug", f"{name}_receptacle"))
        pk = parked_path(name, dk["length_mm"])
        hx, hy = pk["holster_xy"]
        extra = _box_samples(BOOT[name]["box"]) + _cyl_samples(pk["points"][-1], (0, 0, -1), e["plug_nut_d"] / 2, pk["plug_len"]) + \
            _cyl_samples((hx, hy, H.Z_LID1), (0, 0, 1), 12.0, H.HOLSTER_H)
        sweep = {s: clash(pk["points"], d, shift=s, extra=extra) for s in (DOCK_STROKE, DOCK_STROKE / 2, 0.0)}
        res[name] = {"cable_d": d, "bend_r": dk["bend_r"], "boot_top": (BOOT[name]["cable_xy"][0], BOOT[name]["cable_xy"][1], BOOT_TOP_Z),
                     "plug_back": tuple(round(float(v), 1) for v in dk["plug_back"]), "docked_length_mm": round(dk["length_mm"], 0),
                     "docked_min_radius_mm": round(dk["min_radius_mm"], 1), "docked_rise_mm": dk["rise_mm"], "docked_clash": dock_clash, "docked_min_gap_mm": gap,
                     "docked_apex_z": round(float(pts[:, 2].max()), 0), "docked_x_range": (round(float(pts[:, 0].min()), 0), round(float(pts[:, 0].max()), 0)),
                     "docked_y_range": (round(float(pts[:, 1].min()), 0), round(float(pts[:, 1].max()), 0)),
                     "parked": {"loop_r_mm": round(pk["loop_r_mm"], 1), "rise_mm": round(pk["rise_mm"], 1), "apex_z": round(pk["apex_z"], 0),
                                "holster_xy": tuple(round(v, 1) for v in pk["holster_xy"]), "clash_by_stroke_position": {f"{s:g}": v for s, v in sweep.items()}},
                     "swept_volume": f"parked set (boot, loop, plug, holster) translated x +{DOCK_STROKE:g}..0 with the head: x "
                                     f"{BOOT[name]['box'][0]:.0f}..{hx + 12 + DOCK_STROKE:.0f}, y {hy - 12:.0f}..{hy + 12:.0f}, z {H.Z_LID1:.0f}..{pk['apex_z'] + d / 2:.0f}",
                     "_docked_points": pts, "_parked_points": pk["points"], "_parked": pk}
        res[name]["ok"] = not dock_clash and gap >= CLEAR and dk["min_radius_mm"] >= dk["bend_r"] and not any(sweep.values())
    return res
