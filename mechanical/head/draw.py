"""Drawing and rendering tools: hidden-line projection (OCCT HLR) and plane sections plotted with matplotlib
(SVG / PDF / PNG), dimension helpers, and a small numpy z-buffer renderer for the assembly step images.
"""
from __future__ import annotations

import math

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepLib import BRepLib
from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from PIL import Image

VIEWS = {  # name: (direction toward the viewer N, drawing X axis); drawing Y = N x X
    "top": ((0, 0, 1), (0, -1, 0)),          # forward up, robot right to the right
    "bottom": ((0, 0, -1), (0, 1, 0)),       # seen from the floor, forward up
    "rear": ((-1, 0, 0), (0, -1, 0)),        # seen from behind
    "front": ((1, 0, 0), (0, 1, 0)),
    "left": ((0, 1, 0), (-1, 0, 0)),         # seen from the left side, forward to the left
}


def axes_of(view):
    n, x = VIEWS[view] if isinstance(view, str) else view
    n, x = np.array(n, float), np.array(x, float)
    return x, np.cross(n, x), n


def proj(view, p):
    x, y, _ = axes_of(view)
    p = np.array(p, float)
    return float(p @ x), float(p @ y)


def _edge_pts(edge, n=14):
    c = BRepAdaptor_Curve(edge.wrapped)
    a, b = c.FirstParameter(), c.LastParameter()
    k = 2 if c.GetType().name == "GeomAbs_Line" else n
    return [(c.Value(a + (b - a) * i / (k - 1)).X(), c.Value(a + (b - a) * i / (k - 1)).Y(), c.Value(a + (b - a) * i / (k - 1)).Z()) for i in range(k)]


def hlr(shape, view, hidden=False):
    """Returns (visible polylines, hidden polylines) in drawing coordinates."""
    n, x = VIEWS[view] if isinstance(view, str) else view
    algo = HLRBRep_Algo()
    algo.Add(shape.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*n), gp_Dir(*x))))
    algo.Update()
    algo.Hide()
    hs = HLRBRep_HLRToShape(algo)
    out = []
    for getters in ((hs.VCompound, hs.OutLineVCompound, hs.Rg1LineVCompound), (hs.HCompound, hs.OutLineHCompound) if hidden else ()):
        lines = []
        for g in getters:
            c = g()
            if c.IsNull():
                continue
            BRepLib.BuildCurves3d_s(c)
            for e in cq.Shape.cast(c).Edges():
                lines.append([(p[0], p[1]) for p in _edge_pts(e)])
        out.append(lines)
    return out[0], out[1]


def section(shape, origin, normal, view):
    """Edges of the cut of `shape` by a plane, as polylines in the drawing coordinates of `view`."""
    pl = gp_Pln(gp_Pnt(*origin), gp_Dir(*normal))
    s = BRepAlgoAPI_Section(shape.wrapped, pl, False)
    s.Approximation(False)
    s.Build()
    res = cq.Shape.cast(s.Shape())
    return [[proj(view, p) for p in _edge_pts(e)] for e in res.Edges()]


def plot_lines(ax, lines, color="k", lw=0.5, ls="-", zorder=2):
    for ln in lines:
        xs, ys = zip(*ln)
        ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="round", zorder=zorder)


def dim(ax, p1, p2, text=None, off=8.0, horizontal=None, fmt="{:.1f}", fs=5.5, color="#0b3d91", tol=""):
    """Linear dimension between two drawing points. horizontal=True measures x, False measures y, None = aligned by larger extent."""
    (x1, y1), (x2, y2) = p1, p2
    if horizontal is None:
        horizontal = abs(x2 - x1) >= abs(y2 - y1)
    if horizontal:
        yd = (max(y1, y2) + off) if off > 0 else (min(y1, y2) + off)
        val = abs(x2 - x1)
        ax.plot([x1, x1], [y1, yd], color=color, lw=0.25)
        ax.plot([x2, x2], [y2, yd], color=color, lw=0.25)
        ax.annotate("", (x1, yd), (x2, yd), arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.35, mutation_scale=4, shrinkA=0, shrinkB=0))
        ax.text((x1 + x2) / 2, yd + 0.6, (text or fmt.format(val)) + tol, ha="center", va="bottom", fontsize=fs, color=color)
    else:
        xd = (max(x1, x2) + off) if off > 0 else (min(x1, x2) + off)
        val = abs(y2 - y1)
        ax.plot([x1, xd], [y1, y1], color=color, lw=0.25)
        ax.plot([x2, xd], [y2, y2], color=color, lw=0.25)
        ax.annotate("", (xd, y1), (xd, y2), arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.35, mutation_scale=4, shrinkA=0, shrinkB=0))
        ax.text(xd - 0.6, (y1 + y2) / 2, (text or fmt.format(val)) + tol, ha="right", va="center", fontsize=fs, color=color, rotation=90)


def note(ax, xy, text, xytext=None, fs=5.5, color="#111", box=False, ha="left"):
    kw = dict(fontsize=fs, color=color, ha=ha, va="center")
    if box:
        kw["bbox"] = dict(boxstyle="square,pad=0.25", fc="white", ec=color, lw=0.4)
    if xytext is None:
        ax.text(xy[0], xy[1], text, **kw)
    else:
        ax.annotate(text, xy, xytext, arrowprops=dict(arrowstyle="-|>", color=color, lw=0.35, mutation_scale=4), **kw)


def datum(ax, xy, letter, xytext):
    ax.annotate(letter, xy, xytext, fontsize=6.5, ha="center", va="center", color="#8a0000", bbox=dict(boxstyle="square,pad=0.3", fc="white", ec="#8a0000", lw=0.5),
                arrowprops=dict(arrowstyle="-|>", color="#8a0000", lw=0.5, mutation_scale=6))


def balloon(ax, xy, n, xytext):
    ax.annotate(str(n), xy, xytext, fontsize=6, ha="center", va="center", bbox=dict(boxstyle="circle,pad=0.25", fc="white", ec="k", lw=0.5),
                arrowprops=dict(arrowstyle="-", color="k", lw=0.4))
    ax.plot([xy[0]], [xy[1]], "k.", ms=2)


def sheet(title, pn, size=(420, 297), scale_note="", notes=()):
    """A3 landscape sheet (mm) with border and title block; returns (fig, title-block-free layout helper)."""
    fig = plt.figure(figsize=(size[0] / 25.4, size[1] / 25.4))
    bg = fig.add_axes([0, 0, 1, 1])
    bg.set_xlim(0, size[0]); bg.set_ylim(0, size[1]); bg.axis("off")
    bg.plot([8, size[0] - 8, size[0] - 8, 8, 8], [8, 8, size[1] - 8, size[1] - 8, 8], "k-", lw=0.8)
    bx, by, bw, bh = size[0] - 8 - 150, 8, 150, 30
    bg.plot([bx, bx + bw, bx + bw, bx, bx], [by, by, by + bh, by + bh, by], "k-", lw=0.6)
    bg.text(bx + 3, by + bh - 6, title, fontsize=9, weight="bold", va="center")
    bg.text(bx + 3, by + bh - 13, f"{pn}   Rad Roomba Rev E detector head   {scale_note}", fontsize=6.5, va="center")
    bg.text(bx + 3, by + bh - 19, "Units mm. Generated from the CadQuery model (mechanical/head/drawings.py); model = master, basic dimensions from STEP.", fontsize=5, va="center")
    bg.text(bx + 3, by + bh - 24, "General tolerance ISO 2768-mK unless stated. Break edges 0.2-0.4. First-angle-free: every view is labelled. NOT RELEASED: design-stage drawing.", fontsize=5, va="center")
    bg.text(bx + 3, by + 2.5, "Feature control frames are written as text: FLAT / PAR / PERP / POS / PROFILE (ISO 1101), datums in red boxes.", fontsize=5, va="center")
    for k, t in enumerate(notes):
        bg.text(12, 12 + 4.2 * (len(notes) - 1 - k), t, fontsize=5.2, va="bottom")
    return fig


def view_axes(fig, rect_mm, xlim, ylim, label, size=(420, 297)):
    """Axes placed at rect (x, y, w, h in sheet mm) showing model range xlim/ylim with equal scale."""
    ax = fig.add_axes([rect_mm[0] / size[0], rect_mm[1] / size[1], rect_mm[2] / size[0], rect_mm[3] / size[1]])
    ax.set_aspect("equal")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.axis("off")
    sc = rect_mm[2] / (xlim[1] - xlim[0])
    ax.set_title(f"{label}   (scale {sc:.2f}:1)" if sc >= 1 else f"{label}   (scale 1:{1 / sc:.2f})", fontsize=6.5, loc="left", pad=2)
    return ax


# ------------------------------------------------------------------------------------------------ z-buffer renderer
def _hex(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float)


def render(items, path, azim=-55.0, elev=28.0, size=(1500, 950), tol=0.35, bg=(245, 247, 248), title=None, labels=()):
    """items: list of (shape, hex colour, (dx, dy, dz) explode offset). Orthographic, flat shaded, with depth edges."""
    a, e = math.radians(azim), math.radians(elev)
    right = np.array([-math.sin(a), math.cos(a), 0.0])
    fwd = np.array([math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)])      # toward the viewer
    up = np.cross(fwd, right)
    light = np.array([0.35, -0.45, 0.82]); light /= np.linalg.norm(light)
    tris_all = []
    for shape, col, off in items:
        v, f = shape.tessellate(tol, 0.5)
        if not f:
            continue
        pts = np.array([(p.x, p.y, p.z) for p in v]) + np.array(off, float)
        tri = pts[np.array(f)]
        nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        ln = np.linalg.norm(nrm, axis=1)
        ok = ln > 1e-9
        tri, nrm = tri[ok], nrm[ok] / ln[ok][:, None]
        shade = 0.38 + 0.62 * np.abs(nrm @ light) * 0.75 + 0.15 * np.abs(nrm @ fwd)
        tris_all.append((tri, np.clip(shade[:, None] * _hex(col)[None, :], 0, 255)))
    tri = np.concatenate([t for t, _ in tris_all]); colr = np.concatenate([c for _, c in tris_all])
    X, Y, Z = tri @ right, tri @ up, tri @ fwd
    W, Hh = size
    m = 40
    sc = min((W - 2 * m) / (X.max() - X.min()), (Hh - 2 * m - (40 if title else 0)) / (Y.max() - Y.min()))
    px = (X - X.min()) * sc + (W - (X.max() - X.min()) * sc) / 2
    py = Hh - m - (Y - Y.min()) * sc - (Hh - 2 * m - (40 if title else 0) - (Y.max() - Y.min()) * sc) / 2
    img = np.empty((Hh, W, 3), float); img[:] = bg
    zb = np.full((Hh, W), -1e18)
    for k in range(len(tri)):
        x0, x1 = int(max(math.floor(px[k].min()), 0)), int(min(math.ceil(px[k].max()), W - 1))
        y0, y1 = int(max(math.floor(py[k].min()), 0)), int(min(math.ceil(py[k].max()), Hh - 1))
        if x1 < x0 or y1 < y0:
            continue
        ax_, ay_, bx_, by_, cx_, cy_ = px[k, 0], py[k, 0], px[k, 1], py[k, 1], px[k, 2], py[k, 2]
        den = (by_ - cy_) * (ax_ - cx_) + (cx_ - bx_) * (ay_ - cy_)
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((by_ - cy_) * (gx - cx_) + (cx_ - bx_) * (gy - cy_)) / den
        w1 = ((cy_ - ay_) * (gx - cx_) + (ax_ - cx_) * (gy - cy_)) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * Z[k, 0] + w1 * Z[k, 1] + w2 * Z[k, 2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z > sub)
        sub[upd] = z[upd]
        img[y0:y1 + 1, x0:x1 + 1][upd] = colr[k]
    # depth-discontinuity edges
    d = np.where(zb < -1e17, np.nan, zb)
    gx_ = np.abs(np.diff(d, axis=1, prepend=d[:, :1])); gy_ = np.abs(np.diff(d, axis=0, prepend=d[:1, :]))
    edge = (np.nan_to_num(gx_, nan=99) > 1.2 / 1) | (np.nan_to_num(gy_, nan=99) > 1.2)
    edge &= ~np.isnan(d) | np.roll(~np.isnan(d), 1, axis=1) | np.roll(~np.isnan(d), 1, axis=0)
    img[edge] *= 0.35
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if title or labels:
        from PIL import ImageDraw, ImageFont
        dr = ImageDraw.Draw(im)
        try:
            f1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26); f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except Exception:      # noqa: BLE001
            f1 = f2 = ImageFont.load_default()
        if title:
            dr.text((24, 14), title, fill=(20, 40, 46), font=f1)
        for k, t in enumerate(labels):
            dr.text((24, Hh - 30 - 24 * (len(labels) - 1 - k)), t, fill=(40, 60, 66), font=f2)
    im.save(path)
