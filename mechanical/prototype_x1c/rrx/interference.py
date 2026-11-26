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


def overlaps(parts, folder, workers=3, timeout=60.0, log=print):
    """-> list of (name_a, name_b, volume, method, seconds) for every bounding-box-overlapping pair of `parts`."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for p in parts:
        p.shape.exportBrep(str(folder / f"{p.name}.brep"))
    pairs = [(a.name, b.name) for a, b in itertools.combinations(parts, 2)
             if not any(a.bb[i] > b.bb[i + 3] - 0.01 or b.bb[i] > a.bb[i + 3] - 0.01 for i in range(3))]
    workers = max(1, min(workers, (os.cpu_count() or 2) - 1))
    out, slow = _run(pairs, folder, workers, timeout, False, log)
    if slow:
        out2, slow2 = _run([pairs[k] for k in slow], folder, workers, 6 * timeout, True, log)
        for j, k in enumerate(slow):
            out[k] = out2.get(j, (float("nan"), "timeout in sampling too", 0.0))
    return [(pairs[k][0], pairs[k][1]) + tuple(out[k]) for k in range(len(pairs))]
