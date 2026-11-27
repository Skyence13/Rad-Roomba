"""Pairwise interference of the RR-X parts (tool-checked).  Stage 1 screens every bounding-box-overlapping pair with
z-ray intervals of the tessellated solids on a 0.5 mm grid (seconds for all pairs).  Stage 2 re-evaluates every flagged
pair exactly with an OCC boolean common, one process per pair with a time limit (a pair that does not finish keeps its
screening volume, method 'mesh'); exact results are cached on the BREP digests so unchanged pairs cost nothing."""
from __future__ import annotations

import itertools
import os
import time
from pathlib import Path


PAIR_SCRIPT = r"""
import json, sys
import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
a = cq.Shape.importBrep(sys.argv[1]); b = cq.Shape.importBrep(sys.argv[2])
op = BRepAlgoAPI_Common(a.wrapped, b.wrapped)
v = sum(s.Volume() for s in cq.Shape.cast(op.Shape()).Solids()) if op.IsDone() else float("nan")
print(json.dumps({"v": v}))
"""


def _exact(pairs, folder, workers, timeout, log):
    """OCC boolean common of each pair in its own process (clean kill on timeout). Results cached on the BREP digests."""
    import hashlib
    import json
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor
    folder = Path(folder)
    cache_f = folder / "exact_cache.json"
    try:
        cache = json.loads(cache_f.read_text())
    except Exception:  # noqa: BLE001
        cache = {}
    dig = {}

    def digest(n):
        if n not in dig:
            dig[n] = hashlib.sha1((folder / f"{n}.brep").read_bytes()).hexdigest()[:16]
        return dig[n]

    def one(ab):
        a, b = ab
        key = digest(a) + digest(b)
        if key in cache:
            return ab, tuple(cache[key]) + (0.0,)
        t = time.time()
        try:
            r = subprocess.run([sys.executable, "-c", PAIR_SCRIPT, str(folder / f"{a}.brep"), str(folder / f"{b}.brep")],
                               capture_output=True, text=True, timeout=timeout)
            v = json.loads(r.stdout.strip().splitlines()[-1])["v"]
            res = (v, "boolean")
        except subprocess.TimeoutExpired:
            log(f"    pair {a} x {b}: boolean > {timeout:.0f} s, screening volume kept")
            res = (None, "timeout")
        except Exception as e:  # noqa: BLE001
            res = (None, f"error: {str(e)[:60]}")
        if res[1] == "boolean":
            cache[key] = list(res)
        return ab, res + (round(time.time() - t, 1),)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = dict(ex.map(one, pairs))
    cache_f.write_text(json.dumps(cache))
    return out


# ----------------------------------------------------------------------------------------------- mesh screening
H = 0.5                                   # column pitch (mm) of the z-ray screening grid
OFF = (0.2137 * H, 0.3291 * H)            # grid offset: no column runs exactly along a modelled face


def z_intervals(shape, tol=0.05):
    """Solid -> (column keys, z0, z1): inside-intervals along +z rays on a global H-pitch grid (mesh parity)."""
    import numpy as np
    v, f = shape.tessellate(tol, 0.2)
    V = np.array([(p.x, p.y, p.z) for p in v], dtype=float)
    F = np.array(f, dtype=np.int64).reshape(-1, 3)
    if len(F) == 0:
        return np.zeros(0, np.int64), np.zeros(0), np.zeros(0)
    T = V[F]
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    keep = np.abs(det) > 1e-12
    T, a, b, c, det = T[keep], a[keep], b[keep], c[keep], det[keep]
    ix0 = np.ceil((T[:, :, 0].min(1) - OFF[0]) / H).astype(np.int64)
    ix1 = np.floor((T[:, :, 0].max(1) - OFF[0]) / H).astype(np.int64)
    iy0 = np.ceil((T[:, :, 1].min(1) - OFF[1]) / H).astype(np.int64)
    iy1 = np.floor((T[:, :, 1].max(1) - OFF[1]) / H).astype(np.int64)
    nx, ny = np.maximum(ix1 - ix0 + 1, 0), np.maximum(iy1 - iy0 + 1, 0)
    cnt = nx * ny
    tot = int(cnt.sum())
    if tot == 0:
        return np.zeros(0, np.int64), np.zeros(0), np.zeros(0)
    tri = np.repeat(np.arange(len(T)), cnt)
    loc = np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    gx = ix0[tri] + loc % nx[tri]
    gy = iy0[tri] + loc // nx[tri]
    px, py = gx * H + OFF[0], gy * H + OFF[1]
    A, B, C, d = a[tri], b[tri], c[tri], det[tri]
    l1 = ((B[:, 1] - C[:, 1]) * (px - C[:, 0]) + (C[:, 0] - B[:, 0]) * (py - C[:, 1])) / d
    l2 = ((C[:, 1] - A[:, 1]) * (px - C[:, 0]) + (A[:, 0] - C[:, 0]) * (py - C[:, 1])) / d
    l3 = 1.0 - l1 - l2
    ok = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
    z = l1 * A[:, 2] + l2 * B[:, 2] + l3 * C[:, 2]
    key = (gx * 1000003 + gy)[ok]
    z = z[ok]
    order = np.lexsort((z, key))
    key, z = key[order], z[order]
    # drop duplicate hits (column through a shared mesh edge/vertex) and columns with odd parity
    dup = np.concatenate([[False], (key[1:] == key[:-1]) & (np.abs(z[1:] - z[:-1]) < 1e-7)])
    key, z = key[~dup], z[~dup]
    start = np.concatenate([[True], key[1:] != key[:-1]])
    grp = np.cumsum(start) - 1
    n_in = np.bincount(grp)
    good = (n_in % 2 == 0)[grp]
    key, z = key[good], z[good]
    start = np.concatenate([[True], key[1:] != key[:-1]]) if len(key) else np.zeros(0, bool)
    rank = np.arange(len(key)) - np.maximum.accumulate(np.where(start, np.arange(len(key)), 0))
    ev = rank % 2 == 0
    return key[ev], z[ev], z[np.flatnonzero(ev) + 1]


def interval_overlap(ia, ib):
    """Overlap volume (mm3) of two z-interval sets on the same grid."""
    import numpy as np
    ka, a0, a1 = ia
    kb, b0, b1 = ib
    if not len(ka) or not len(kb):
        return 0.0
    lo, hi = np.searchsorted(ka, kb, "left"), np.searchsorted(ka, kb, "right")
    n = hi - lo
    if n.sum() == 0:
        return 0.0
    j = np.repeat(np.arange(len(kb)), n)
    i = np.repeat(lo, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
    ov = np.minimum(a1[i], b1[j]) - np.maximum(a0[i], b0[j])
    return float(np.clip(ov, 0, None).sum() * H * H)


def overlaps(parts, folder, workers=3, timeout=150.0, screen_tol=2.0, log=print):
    """Two stages.  (1) mesh screening of every bounding-box-overlapping pair: z-ray intervals on a 0.5 mm grid
    (touching faces give zero, curved fits give at most a few mm3 of chord error).  (2) every pair the screening
    flags above `screen_tol` mm3 is re-evaluated exactly with an OCC boolean in a worker process (per-pair time limit;
    a pair that does not finish keeps its screening volume, method 'mesh').
    -> list of (name_a, name_b, volume, method, seconds)."""
    t0 = time.time()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pairs = [(a, b) for a, b in itertools.combinations(parts, 2)
             if not any(a.bb[i] > b.bb[i + 3] - 0.01 or b.bb[i] > a.bb[i + 3] - 0.01 for i in range(3))]
    need = {p.name for ab in pairs for p in ab}
    iv = {p.name: z_intervals(p.shape) for p in parts if p.name in need}
    screened = [(a.name, b.name, interval_overlap(iv[a.name], iv[b.name])) for a, b in pairs]
    log(f"    screening: {len(pairs)} pairs in {time.time() - t0:.0f} s, {sum(1 for r in screened if r[2] > screen_tol)} flagged")
    flagged = [(a, b) for a, b, v in screened if v > screen_tol]
    byn = {p.name: p for p in parts}
    for n in {x for ab in flagged for x in ab}:
        byn[n].shape.exportBrep(str(folder / f"{n}.brep"))
    exact = {}
    if flagged:
        res = _exact(flagged, folder, max(1, min(workers, (os.cpu_count() or 2) - 1)), timeout, log)
        exact = {ab: r for ab, r in res.items() if r[1] == "boolean"}
    rows = []
    for a, b, v in screened:
        if (a, b) in exact:
            rows.append((a, b) + tuple(exact[(a, b)]))
        else:
            rows.append((a, b, round(v, 1), "mesh" if v > screen_tol else "mesh screen", 0.0))
    return rows


def overlap_region(ia, ib):
    """Bounding box (x0, x1, y0, y1, z0, z1) of the overlapping columns of two interval sets (diagnostics)."""
    import numpy as np
    ka, a0, a1 = ia
    kb, b0, b1 = ib
    lo, hi = np.searchsorted(ka, kb, "left"), np.searchsorted(ka, kb, "right")
    n = hi - lo
    if n.sum() == 0:
        return None
    j = np.repeat(np.arange(len(kb)), n)
    i = np.repeat(lo, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
    z0, z1 = np.maximum(a0[i], b0[j]), np.minimum(a1[i], b1[j])
    m = z1 - z0 > 1e-6
    if not m.any():
        return None
    k = kb[j[m]]
    gx, gy = k // 1000003, k % 1000003
    gy = np.where(gy > 500000, gy - 1000003, gy)
    gx = np.where(gy < 0, gx + 1, gx) if False else gx
    x, y = gx * H + OFF[0], gy * H + OFF[1]
    return (round(float(x.min()), 1), round(float(x.max()), 1), round(float(y.min()), 1), round(float(y.max()), 1),
            round(float(z0[m].min()), 1), round(float(z1[m].max()), 1))
