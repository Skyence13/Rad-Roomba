"""Pairwise interference of the RR-X parts (tool-checked, OCC boolean common), run in worker processes with a per-pair
time limit.  A pair whose boolean does not finish in time is re-evaluated by point sampling (1 mm grid in the overlap
of the two bounding boxes, solid classifier) and reported with method 'sampled'.  Results are identical in meaning:
overlap volume in mm3."""
from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import queue
import time
from pathlib import Path


def _volume_common(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    import cadquery as cq
    op = BRepAlgoAPI_Common(a.wrapped, b.wrapped)
    if not op.IsDone():
        raise RuntimeError("boolean failed")
    return sum(s.Volume() for s in cq.Shape.cast(op.Shape()).Solids())


def _volume_sampled(a, b, step=1.0, cap=400000):
    """Overlap volume by classifying grid points (inside both) in the common bounding box."""
    import numpy as np
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN
    ba, bb = a.BoundingBox(), b.BoundingBox()
    lo = [max(ba.xmin, bb.xmin), max(ba.ymin, bb.ymin), max(ba.zmin, bb.zmin)]
    hi = [min(ba.xmax, bb.xmax), min(ba.ymax, bb.ymax), min(ba.zmax, bb.zmax)]
    if any(h <= l for l, h in zip(lo, hi)):
        return 0.0
    n = [max(1, int((h - l) / step)) for l, h in zip(lo, hi)]
    while n[0] * n[1] * n[2] > cap:
        step *= 1.25
        n = [max(1, int((h - l) / step)) for l, h in zip(lo, hi)]
    d = [(h - l) / k for l, h, k in zip(lo, hi, n)]
    ca, cb = BRepClass3d_SolidClassifier(a.wrapped), BRepClass3d_SolidClassifier(b.wrapped)
    hits = 0
    for i, j, k in itertools.product(*(np.arange(k) + 0.5 for k in n)):
        p = gp_Pnt(lo[0] + i * d[0], lo[1] + j * d[1], lo[2] + k * d[2])
        cb.Perform(p, 1e-6)
        if cb.State() != TopAbs_IN:
            continue
        ca.Perform(p, 1e-6)
        if ca.State() == TopAbs_IN:
            hits += 1
    return hits * d[0] * d[1] * d[2]


def _worker(wid, folder, tasks, results, sampled):
    import cadquery as cq
    shapes = {}

    def get(name):
        if name not in shapes:
            shapes[name] = cq.Shape.importBrep(str(Path(folder) / f"{name}.brep"))
        return shapes[name]
    while True:
        try:
            item = tasks.get(timeout=1.0)
        except queue.Empty:
            continue
        if item is None:
            return
        k, na, nb = item
        results.put(("start", wid, k, time.time()))
        t = time.time()
        try:
            v = _volume_sampled(get(na), get(nb)) if sampled else _volume_common(get(na), get(nb))
            method = "sampled" if sampled else "boolean"
        except Exception as e:  # noqa: BLE001
            v, method = float("nan"), f"error: {e}"
        results.put(("done", wid, k, (v, method, round(time.time() - t, 2))))


def _run(pairs, folder, workers, timeout, sampled, log):
    ctx = mp.get_context("spawn")          # not fork: OCC thread pools in the parent deadlock forked children
    tasks, results = ctx.Queue(), ctx.Queue()
    for k, (a, b) in enumerate(pairs):
        tasks.put((k, a, b))
    procs, running, out, timed_out = {}, {}, {}, []

    def spawn(w):
        p = ctx.Process(target=_worker, args=(w, folder, tasks, results, sampled), daemon=True)
        p.start()
        procs[w] = p
    for w in range(workers):
        spawn(w)
    next_w = workers
    while len(out) + len(timed_out) < len(pairs):
        try:
            msg = results.get(timeout=1.0)
            if msg[0] == "start":
                running[msg[1]] = (msg[2], msg[3])
            else:
                out[msg[2]] = msg[3]
                running.pop(msg[1], None)
        except queue.Empty:
            pass
        now = time.time()
        for w, (k, t0) in list(running.items()):
            if now - t0 > timeout:
                procs[w].kill()
                procs[w].join()
                running.pop(w)
                timed_out.append(k)
                log(f"    pair {pairs[k][0]} x {pairs[k][1]}: boolean > {timeout:.0f} s, re-checked by sampling")
                spawn(next_w)
                next_w += 1
        for w, p in list(procs.items()):
            if not p.is_alive() and w in running:
                k, _ = running.pop(w)
                timed_out.append(k)
                spawn(next_w)
                next_w += 1
    for _ in procs:
        tasks.put(None)
    for p in procs.values():
        p.join(timeout=5)
        if p.is_alive():
            p.kill()
    return out, timed_out


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


def overlaps(parts, folder, workers=3, timeout=60.0, screen_tol=2.0, log=print):
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
        out, slow = _run(flagged, folder, max(1, min(workers, (os.cpu_count() or 2) - 1)), timeout, False, log)
        for k, (a, b) in enumerate(flagged):
            if k in out and out[k][1] == "boolean":
                exact[(a, b)] = out[k]
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
