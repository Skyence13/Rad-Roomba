"""Headless renders for the documents: shaded painter's-algorithm views of part sets and true-size joint sections."""
from __future__ import annotations

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402

from .util import bounds, box

_TESS = {}


def tess(p, tol=0.6):
    if p.name not in _TESS:
        v, f = p.shape.tessellate(tol if p.group not in ("lid", "lower_hull", "hatch") else 1.2, 0.5)
        _TESS[p.name] = (np.array([(a.x, a.y, a.z) for a in v], dtype=float).reshape(-1, 3), np.array(f, dtype=int).reshape(-1, 3))
    return _TESS[p.name]


def _rgb(c):
    if isinstance(c, str):
        return np.array(to_rgb(c))
    t = c.toTuple()
    return np.array(t[:3])


def view(parts, path, highlight=None, title="", azim=-58.0, elev=24.0, size=(11, 7), ghost=()):
    """Shaded orthographic view.  highlight: names drawn in colour (others light grey); ghost: names drawn translucent."""
    a, e = math.radians(azim), math.radians(elev)
    right = np.array([-math.sin(a), math.cos(a), 0.0])
    fwd = np.array([math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)])       # from the scene towards the camera
    up = np.cross(fwd, right)
    light = np.array([0.35, -0.45, 0.82])
    light = light / np.linalg.norm(light)
    polys, cols, depth = [], [], []
    for p in parts:
        V, F = tess(p)
        if len(F) == 0:
            continue
        T = V[F]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ln[ln == 0] = 1
        shade = 0.55 + 0.45 * np.abs((n / ln[:, None]) @ light)
        base = _rgb(p.color)
        alpha = 1.0
        if highlight is not None and p.name not in highlight:
            base = 0.80 + 0.12 * base
        if p.name in ghost:
            alpha = 0.18
        rgba = np.concatenate([np.clip(base[None, :] * shade[:, None], 0, 1), np.full((len(F), 1), alpha)], axis=1)
        polys.append(np.stack([T @ right, T @ up], axis=2))
        cols.append(rgba)
        depth.append((T @ fwd).mean(axis=1))
    polys, cols, depth = np.concatenate(polys), np.concatenate(cols), np.concatenate(depth)
    order = np.argsort(depth)
    fig, ax = plt.subplots(figsize=size, dpi=110)
    ax.add_collection(PolyCollection(polys[order], facecolors=cols[order], edgecolors=cols[order] * np.array([0.82, 0.82, 0.82, 1.0]), linewidths=0.08))
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def section(parts, plane, pos, window, path, title, labels=None, px_per_mm=10, notes=()):
    """True-size section (1:1 at 254 dpi): parts cut by a 0.4 mm slab at `plane` = pos, drawn in the window
    (u0, u1, v0, v1) where (u, v) = (y, z) for plane 'x', (x, z) for 'y', (x, y) for 'z'."""
    u0, u1, v0, v1 = window
    h = 0.2
    slab = {"x": box(pos - h, pos + h, u0, u1, v0, v1), "y": box(u0, u1, pos - h, pos + h, v0, v1), "z": box(u0, u1, v0, v1, pos - h, pos + h)}[plane]
    ui, vi = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}[plane]
    sb = bounds(slab)
    fig, ax = plt.subplots(figsize=((u1 - u0) / 25.4 + 2.6, (v1 - v0) / 25.4 + 0.9), dpi=25.4 * px_per_mm)
    seen = []
    for p in parts:
        if any(p.bb[i] > sb[i + 3] or sb[i] > p.bb[i + 3] for i in range(3)):
            continue
        try:
            cutp = p.shape.intersect(slab)
            V, F = cutp.tessellate(0.05, 0.3)
        except Exception:  # noqa: BLE001
            continue
        if not F:
            continue
        P2 = np.array([(a.x, a.y, a.z) for a in V])[:, [ui, vi]]
        col = _rgb(p.color)
        ax.add_collection(PolyCollection(P2[np.array(F)], facecolors=[col], edgecolors=[col], linewidths=0.2))
        seen.append((p.name, col))
    ax.set_xlim(u0, u1)
    ax.set_ylim(v0, v1)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=4, length=2, width=0.3)
    ax.grid(True, lw=0.15, alpha=0.5)
    ax.set_xlabel({"x": "y [mm]", "y": "x [mm]", "z": "x [mm]"}[plane], fontsize=4)
    ax.set_ylabel({"x": "z [mm]", "y": "z [mm]", "z": "y [mm]"}[plane], fontsize=4)
    ax.set_title(f"{title}\nsection {plane} = {pos:g} mm, scale 1:1 at 254 dpi (grid = ticks in mm)", fontsize=4.5)
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in seen]
    ax.legend(hs, [n for n, _ in seen], fontsize=3.2, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    for i, t in enumerate(notes):
        ax.text(1.01, 0.02 + 0.05 * i, t, transform=ax.transAxes, fontsize=3.0)
    fig.tight_layout()
    fig.savefig(path)
    fig.savefig(str(path).replace(".png", ".pdf"))
    plt.close(fig)
    return [n for n, _ in seen]
