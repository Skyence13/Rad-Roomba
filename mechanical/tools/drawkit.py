"""Drawing kit for the body packages: hidden-line projection (OCCT HLR), filled plane sections, dimensions, datum flags and an
A3 sheet with a title block and general-tolerance block, plotted with matplotlib to multi-page PDF.

Method and helpers follow mechanical/head/draw.py and mechanical/head/drawings.py (copied here, not imported, so the body
builds do not depend on the head package's internals).
"""
from __future__ import annotations

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MP  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Curve  # noqa: E402
from OCP.BRepLib import BRepLib  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402
from OCP.HLRAlgo import HLRAlgo_Projector  # noqa: E402
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape  # noqa: E402

VIEWS = {  # name: (direction toward the viewer N, drawing X axis); drawing Y = N x X
    "top": ((0, 0, 1), (0, -1, 0)),          # forward up, robot right to the right
    "plan": ((0, 0, 1), (1, 0, 0)),          # forward to the right, robot left up
    "bottom": ((0, 0, -1), (1, 0, 0)),       # seen from the floor, forward to the right
    "rear": ((-1, 0, 0), (0, -1, 0)),        # seen from behind
    "front": ((1, 0, 0), (0, 1, 0)),
    "left": ((0, 1, 0), (-1, 0, 0)),         # seen from the left side, forward to the left
    "side": ((0, -1, 0), (1, 0, 0)),         # seen from the right side, forward to the right
}
SEC_VIEWS = {"y": ((0, -1, 0), (1, 0, 0)), "x": ((1, 0, 0), (0, 1, 0)), "z": ((0, 0, 1), (1, 0, 0))}
GENERAL_TOL = [
    "GENERAL TOLERANCES unless stated: machined ISO 2768-mK; sheet / laser ISO 2768-m on profile, +-0.5 deg on bends;",
    "SLS PA11: +-0.3 mm or +-0.3 % (larger), wall >= 1.2 mm; cast PU: +-0.3 mm. Break edges 0.2-0.4. Units mm. Dimensions in [ ] are base_link.",
]


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
    """(visible polylines, hidden polylines) in drawing coordinates."""
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


def section_faces(shape, origin, normal, view):
    """Cut faces of `shape` by a plane: list of (outer polygon, [hole polygons]) in drawing coordinates."""
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_REVERSED
    pl = cq.Face.makePlane(3000, 3000, cq.Vector(*origin), cq.Vector(*normal))
    try:
        cut = shape.intersect(pl)
    except Exception:      # noqa: BLE001
        return []
    out = []

    def wire_pts(w):
        ex = BRepTools_WireExplorer(w.wrapped)
        pts = []
        while ex.More():
            e = cq.Edge(ex.Current())
            p = _edge_pts(e, 10)
            if ex.Current().Orientation() == TopAbs_REVERSED:
                p = p[::-1]
            pts += [proj(view, q) for q in p]
            ex.Next()
        return pts

    for f in cut.Faces():
        try:
            out.append((wire_pts(f.outerWire()), [wire_pts(w) for w in f.innerWires()]))
        except Exception:      # noqa: BLE001
            continue
    return out


def fill_faces(ax, faces, color, alpha=0.85, lw=0.4, hatch=None, zorder=1):
    for outer, holes in faces:
        verts, codes = [], []
        for ring in [outer] + holes:
            if len(ring) < 3:
                continue
            verts += ring + [ring[0]]
            codes += [MP.MOVETO] + [MP.LINETO] * (len(ring) - 1) + [MP.CLOSEPOLY]
        if verts:
            ax.add_patch(PathPatch(MP(verts, codes), fc=color, ec="k", lw=lw, alpha=alpha, hatch=hatch, zorder=zorder))


def plot_lines(ax, lines, color="k", lw=0.5, ls="-", zorder=2):
    for ln in lines:
        xs, ys = zip(*ln)
        ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="round", zorder=zorder)


def dim(ax, p1, p2, text=None, off=8.0, horizontal=None, fmt="{:.1f}", fs=5.5, color="#0b3d91", tol=""):
    """Linear dimension between two drawing points; horizontal True measures x, False y, None the larger extent."""
    (x1, y1), (x2, y2) = p1, p2
    if horizontal is None:
        horizontal = abs(x2 - x1) >= abs(y2 - y1)
    if horizontal:
        yd = (max(y1, y2) + off) if off > 0 else (min(y1, y2) + off)
        ax.plot([x1, x1], [y1, yd], color=color, lw=0.25)
        ax.plot([x2, x2], [y2, yd], color=color, lw=0.25)
        ax.annotate("", (x1, yd), (x2, yd), arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.35, mutation_scale=4, shrinkA=0, shrinkB=0))
        ax.text((x1 + x2) / 2, yd + 0.6, (text or fmt.format(abs(x2 - x1))) + tol, ha="center", va="bottom", fontsize=fs, color=color)
    else:
        xd = (max(x1, x2) + off) if off > 0 else (min(x1, x2) + off)
        ax.plot([x1, xd], [y1, y1], color=color, lw=0.25)
        ax.plot([x2, xd], [y2, y2], color=color, lw=0.25)
        ax.annotate("", (xd, y1), (xd, y2), arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.35, mutation_scale=4, shrinkA=0, shrinkB=0))
        ax.text(xd - 0.6, (y1 + y2) / 2, (text or fmt.format(abs(y2 - y1))) + tol, ha="right", va="center", fontsize=fs, color=color, rotation=90)


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


def sheet(title, pn, sheet_no, product="Rad Roomba Rev E body, production build", notes=(), material="", finish="", size=(420, 297)):
    """A3 landscape sheet with border, title block (material / finish / sheet), general-tolerance block and numbered notes."""
    fig = plt.figure(figsize=(size[0] / 25.4, size[1] / 25.4))
    bg = fig.add_axes([0, 0, 1, 1])
    bg.set_xlim(0, size[0]); bg.set_ylim(0, size[1]); bg.axis("off")
    bg.plot([8, size[0] - 8, size[0] - 8, 8, 8], [8, 8, size[1] - 8, size[1] - 8, 8], "k-", lw=0.8)
    bx, by, bw, bh = size[0] - 8 - 170, 8, 170, 40
    bg.plot([bx, bx + bw, bx + bw, bx, bx], [by, by, by + bh, by + bh, by], "k-", lw=0.6)
    bg.plot([bx, bx + bw], [by + 14, by + 14], "k-", lw=0.4)
    bg.text(bx + 3, by + bh - 5, title, fontsize=8.5, weight="bold", va="center")
    bg.text(bx + 3, by + bh - 11, f"{pn}   sheet {sheet_no}   {product}", fontsize=6.2, va="center")
    bg.text(bx + 3, by + bh - 16, f"MATERIAL: {material}"[:120], fontsize=5.4, va="center")
    bg.text(bx + 3, by + bh - 21, f"FINISH: {finish}"[:120], fontsize=5.4, va="center")
    bg.text(bx + 3, by + 10.5, GENERAL_TOL[0], fontsize=4.4, va="center")
    bg.text(bx + 3, by + 7.0, GENERAL_TOL[1], fontsize=4.4, va="center")
    bg.text(bx + 3, by + 3.0, "Generated from the CadQuery model (mechanical/production/drawings.py); model = master. FCFs as text (ISO 1101). NOT RELEASED.", fontsize=4.4, va="center")
    for k, t in enumerate(notes):
        bg.text(12, 12 + 4.2 * (len(notes) - 1 - k), f"{k + 1}. {t}", fontsize=5.0, va="bottom")
    return fig


def view_axes(fig, rect_mm, xlim, ylim, label, size=(420, 297)):
    ax = fig.add_axes([rect_mm[0] / size[0], rect_mm[1] / size[1], rect_mm[2] / size[0], rect_mm[3] / size[1]])
    ax.set_aspect("equal")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.axis("off")
    sc = rect_mm[2] / (xlim[1] - xlim[0])
    ax.set_title(f"{label}   (scale {sc:.2f}:1)" if sc >= 1 else f"{label}   (scale 1:{1 / sc:.2f})", fontsize=6.5, loc="left", pad=2)
    return ax


def hlr_ax(fig, rect, shape, view, label, margin=10.0, hidden=False):
    vis, hid = hlr(shape, view, hidden)
    xs = [p[0] for ln in vis for p in ln]; ys = [p[1] for ln in vis for p in ln]
    w, h = max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin
    sc = min(rect[2] / w, rect[3] / h)
    ax = view_axes(fig, (rect[0], rect[1], w * sc, h * sc), (min(xs) - margin, max(xs) + margin), (min(ys) - margin, max(ys) + margin), label)
    if hid:
        plot_lines(ax, hid, color="#888", lw=0.22, ls=(0, (3, 2)))
    plot_lines(ax, vis, lw=0.4)
    return ax


def sec_ax(fig, rect, shapes, axis, value, region, label, colors=None):
    view = SEC_VIEWS[axis]
    origin = {"x": (value, 0, 0), "y": (0, value, 0), "z": (0, 0, value)}[axis]
    normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    (u0, u1), (v0, v1) = region
    sc = min(rect[2] / (u1 - u0), rect[3] / (v1 - v0))
    ax = view_axes(fig, (rect[0], rect[1], (u1 - u0) * sc, (v1 - v0) * sc), (u0, u1), (v0, v1), label)
    for k, s in enumerate(shapes):
        fill_faces(ax, section_faces(s, origin, normal, view), (colors or ["#cfd6da"] * 12)[k], hatch="////" if k == 0 else None, lw=0.4)
    return ax


def table_ax(fig, rect, rows, headers, label, fs=4.6, size=(420, 297)):
    """A plain table (e.g. hole table) drawn as text in a box."""
    ax = fig.add_axes([rect[0] / size[0], rect[1] / size[1], rect[2] / size[0], rect[3] / size[1]])
    ax.axis("off")
    ax.set_title(label, fontsize=6.5, loc="left", pad=2)
    tb = ax.table(cellText=[[str(c) for c in r] for r in rows], colLabels=headers, loc="upper left", cellLoc="left", colLoc="left")
    tb.auto_set_font_size(False)
    tb.set_fontsize(fs)
    tb.scale(1.0, 0.9)
    return ax
