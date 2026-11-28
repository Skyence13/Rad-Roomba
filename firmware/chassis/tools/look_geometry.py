#!/usr/bin/env python3
"""Look-ahead ToF geometry (IB-34) from mechanical/common/frames.yaml -> firmware defaults.

Computes, for the forward pair (grip cheeks, LOOK_FL/LOOK_FR) and the rear pair (tail, LOOK_RL/LOOK_RR):
  nominal_mm  oblique range to a level floor (z = 0 in base_link)
  ahead_m     horizontal x distance of that floor point beyond the leading rail (forward: head envelope x max
              in frames.yaml footprint) or beyond the tail swept radius (rear: contract
              frames.body_rev_e.swept_radii_m.tail_corner, 0.290 m)
  cos         x component of the ray direction (range -> horizontal distance along x)
and the floor-spot separation of the two partners versus the spot size (18 deg full field), which decides
whether a pair cross-comparison (TOF_DISAGREE) is meaningful.
With --check it compares the results with the X(LOOK_...) defaults in core/rrch.h and exits 1 on drift.
Evidence class: calculated (from the nominal CAD frames). Reads files only.
"""
import argparse
import math
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(ROOT, "..", ".."))
FRAMES = os.path.join(REPO, "mechanical", "common", "frames.yaml")
CONTRACT = os.path.join(REPO, "interface", "system", "contract.yaml")
# frame names: current (2026-11-27) and the earlier ones, same poses
NAMES = {"FL": ("tof_look_fwd_left", "tof_look_fl"), "FR": ("tof_look_fwd_right", "tof_look_fr"),
         "RL": ("tof_look_rev_left", "tof_look_rl"), "RR": ("tof_look_rev_right", "tof_look_rr")}
TOL = {"nominal_mm": 2.0, "ahead_m": 0.003, "cos": 0.003}


def sensor(tof, key):
    for n in NAMES[key]:
        if n in tof:
            return n, tof[n]
    raise SystemExit(f"look_geometry: no frame for {key} in {FRAMES} (tried {NAMES[key]})")


def floor_hit(f):
    (x, y, z), (dx, dy, dz) = f["xyz"], f["dir"]
    if dz >= 0:
        raise SystemExit("look_geometry: a look sensor does not point at the floor")
    r = z / -dz
    return r, x + r * dx, y + r * dy, abs(dx), f.get("fov_full_deg", 18.0)


def compute():
    with open(FRAMES) as fh:
        fr = yaml.safe_load(fh)
    with open(CONTRACT) as fh:
        ct = yaml.safe_load(fh)
    rail_x = fr["footprint"]["head_envelope_m"]["x"][1]
    tail_r = ct["frames"]["body_rev_e"]["swept_radii_m"]["tail_corner"]
    out = {}
    for pair, (a, b) in (("fwd", ("FL", "FR")), ("rev", ("RL", "RR"))):
        hits = []
        for k in (a, b):
            name, f = sensor(fr["tof"], k)
            hits.append((name,) + floor_hit(f))
        r = 0.5 * (hits[0][1] + hits[1][1])
        hx = 0.5 * (hits[0][2] + hits[1][2])
        ahead = hx - rail_x if pair == "fwd" else -hx - tail_r
        sep = abs(hits[0][3] - hits[1][3])
        spot = 2.0 * r * math.tan(math.radians(hits[0][5] / 2.0))
        out[pair] = {"names": (hits[0][0], hits[1][0]), "nominal_mm": r * 1000.0, "ahead_m": ahead, "cos": 0.5 * (hits[0][4] + hits[1][4]),
                     "asym_mm": abs(hits[0][1] - hits[1][1]) * 1000.0, "sep_m": sep, "spot_m": spot}
    return out, rail_x, tail_r


def defaults():
    with open(os.path.join(ROOT, "core", "rrch.h")) as fh:
        txt = fh.read()
    d = {}
    for m in re.finditer(r'X\(LOOK_(FWD|REV)_(NOMINAL_MM|AHEAD_M|COS)\s*,\s*"[^"]+"\s*,\s*([-0-9.]+)', txt):
        d[(m.group(1).lower(), {"NOMINAL_MM": "nominal_mm", "AHEAD_M": "ahead_m", "COS": "cos"}[m.group(2)])] = float(m.group(3))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    g, rail_x, tail_r = compute()
    print(f"look geometry from {os.path.relpath(FRAMES, REPO)} (leading rail x = {rail_x:.4f} m, tail swept radius {tail_r:.3f} m):")
    for pair, v in g.items():
        print(f"  {pair}: {v['names'][0]}/{v['names'][1]}: floor range {v['nominal_mm']:.1f} mm (L/R differ {v['asym_mm']:.1f} mm), "
              f"floor point {v['ahead_m'] * 1000:.1f} mm beyond the {'rail' if pair == 'fwd' else 'tail radius'}, cos_x {v['cos']:.4f}; "
              f"partner spots {v['sep_m'] * 1000:.0f} mm apart, spot diameter ~{v['spot_m'] * 1000:.0f} mm -> "
              f"{'overlap' if v['sep_m'] < v['spot_m'] else 'no overlap'}")
    if not a.check:
        return 0
    d, bad = defaults(), []
    for pair, v in g.items():
        for k, tol in TOL.items():
            have = d.get((pair, k))
            if have is None or abs(have - v[k]) > tol:
                bad.append(f"look.{pair}_{k}: firmware default {have}, frames.yaml gives {v[k]:.4f} (tolerance {tol})")
    for b in bad:
        print("LOOK GEOMETRY DRIFT:", b)
    if bad:
        print("update the X(LOOK_...) defaults in core/rrch.h and ICD section 8, or check frames.yaml")
        return 1
    print("firmware look.* defaults match frames.yaml: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
