"""Fabrication drawings of the RR-P production body: one multi-sheet A3 PDF generated from the model.

Method of mechanical/head/drawings.py (hidden-line views, filled sections, dimensions, datum flags, FCFs as text), via
mechanical/tools/drawkit.py.  Every made part gets a sheet (three views, overall size, auto hole / thread / insert table,
material, finish, process, tolerance class); the datum parts (receiver channel, shim, chassis plate) get extra sheets
with the critical dimensions and tolerances of the receiver interface.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from mechanical.common import params as P
from mechanical.prototype_x1c.rrx import dims as D

from .docs import callout

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import drawkit as K  # noqa: E402

RC, RB = P.RECEIVER, P.RECEIVER_BREAK
BIG = ("lower_hull", "upper_shell")


def holes_3d(shape):
    """Cylindrical hole faces (normal toward the axis): [(diameter, axis label, centre)] de-duplicated."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec
    out = {}
    for f in shape.Faces():
        if f.geomType() != "CYLINDER":
            continue
        ad = BRepAdaptor_Surface(f.wrapped)
        cy = ad.Cylinder()
        r = cy.Radius()
        if r > 15:
            continue
        ax = cy.Axis()
        u0, u1, v0, v1 = ad.FirstUParameter(), ad.LastUParameter(), ad.FirstVParameter(), ad.LastVParameter()
        pnt, nrm = gp_Pnt(), gp_Vec()
        BRepGProp_Face(f.wrapped).Normal((u0 + u1) / 2, (v0 + v1) / 2, pnt, nrm)
        loc = ax.Location()
        d = ax.Direction()
        w = gp_Vec(loc, pnt)
        radial = w - gp_Vec(d) * w.Dot(gp_Vec(d))
        if radial.Magnitude() < 1e-9 or radial.Dot(nrm) >= 0:
            continue                                                  # outward normal: boss, not a hole
        axis = max((abs(d.X()), "x"), (abs(d.Y()), "y"), (abs(d.Z()), "z"))[1]
        c = (loc.X(), loc.Y(), loc.Z())
        key = (round(2 * r, 2), axis) + tuple(round(c[i], 0) for i in range(3) if "xyz"[i] != axis)
        out.setdefault(key, (round(2 * r, 2), axis, c))
    return list(out.values())


def hole_rows(p):
    metal = not p.material.startswith(("PA", "PU", "G10"))
    groups = {}
    for dia, axis, c in holes_3d(p.shape):
        k = (callout(dia, metal), axis)
        groups.setdefault(k, []).append(c)
    rows = []
    for (co, axis), cs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        pos = "; ".join(f"[{c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f}]" for c in cs[:3]) + (" ..." if len(cs) > 3 else "")
        rows.append((len(cs), co, f"axis {axis}", pos))
    return rows[:18]


def generic_sheet(p, rec, n_sheet):
    notes = [f"PROCESS: {p.process_class}; TOOLING: {p.tooling}. Tolerance class per process (title block) unless stated.",
             f"SEALING: {getattr(p, 'sealing', '-')}"[:200],
             f"CARRIED OVER UNCHANGED FROM THE X1C BUILD: {getattr(p, 'carried', '-')}; replaces {getattr(p, 'replaces', '-')} ({p.x1c_pn}).",
             "Geometry: STEP step/%s_%s.step (base_link) is the master; basic dimensions from the STEP; views below are hidden-line projections." % (p.pn, rec["file"])]
    if p.material.startswith("PA"):
        notes.append("SLS PA11: datum / mating bores ream after sintering where H-class fits are called; insert bores sized for heat-set brass inserts (dims.INSERT).")
    if p.material.startswith("AL"):
        notes.append("Threads ISO 965 6H, engagement >= 1.5 d; mask threads and reamed bores from anodise; break edges 0.2-0.4.")
    fig = K.sheet(rec["file"].replace("_", " ").upper(), p.pn, n_sheet, notes=notes, material=p.material, finish=p.finish)
    hidden = p.name not in BIG and p.volume < 4e5
    b = p.bb
    try:
        ax = K.hlr_ax(fig, (14, 160, 190, 118), p.shape, "plan", "PLAN (forward to the right, robot left up)", hidden=hidden)
        K.dim(ax, (b[0], b[1]), (b[3], b[1]), off=-6, horizontal=True, tol="  (ref)")
        K.dim(ax, (b[3], b[1]), (b[3], b[4]), off=6, horizontal=False, tol="  (ref)")
        ax = K.hlr_ax(fig, (214, 160, 190, 118), p.shape, "side", "SIDE (seen from the right, forward to the right)", hidden=hidden)
        K.dim(ax, (b[0], b[2]), (b[0], b[5]), off=-6, horizontal=False, tol="  (ref)")
        K.hlr_ax(fig, (14, 62, 150, 88), p.shape, "front", "FRONT (seen from ahead)", hidden=hidden)
    except Exception as e:  # noqa: BLE001
        fig.text(0.05, 0.5, f"view failed: {e}", fontsize=6)
    rows = hole_rows(p) if p.name not in BIG else []
    if rows:
        K.table_ax(fig, (172, 62, 232, 88), rows, ["Qty", "Call-out", "Axis", "Positions [base_link]"], "HOLE / THREAD / INSERT TABLE (tool-extracted from the solid)", fs=4.4)
    else:
        fig.text(172 / 420, 140 / 297, f"Overall size {b[3] - b[0]:.1f} x {b[4] - b[1]:.1f} x {b[5] - b[2]:.1f} mm; volume {p.volume / 1000:.0f} cm3.\n"
                 + ("Holes, seats and bosses: see the STEP and the prototype seat definitions (sensors.py); inserts per hardware_production.md." if p.name in BIG else "No holes."),
                 fontsize=6, va="top")
    return fig


def channel_sheets(parts, n0):
    ch = next(p for p in parts if p.name == "receiver_channel_L")
    figs = []
    yc = RC["shoe_y"]
    fig = K.sheet("RECEIVER CHANNEL, CRITICAL DIMENSIONS (LH shown, RH mirror)", ch.pn + " / " + ch.pn[:-1] + "R", n0, material="6061-T6 bar",
                  finish="hard anodise type III 25 um, mask the four 4 H7 cross bores, tapped ears and ear top faces (thermal-break seat)", notes=[
                      "DATUM A = x-stop face x 65.70 (front faces of the flange pads, coplanar 0.05 across both channels via the plate pin holes). DATUM B = left channel slot mid-plane y +87.50 "
                      "(fitted channel; RH floats +-0.30). DATUM C = land-pin tops z 16.00 (pins 4 m6 hardened in the 4 H7 cross bores).",
                      f"Ear top faces z {RB['ear_top_z']:.2f} = seat on the {RB['shim_t']:.2f} mm G10 shim: FLAT 0.01, PAR 0.01 | C; ear top to cross-bore centre 15.00 +-0.03 (one set-up).",
                      "Roof pads at the two bridges: 14.06 +0.04/-0.02 above datum C (z fit of the 14.00 mm shoe). Bridges 2.5 thick stand 1.5 into the plate pockets (no contact).",
                      "Threads: 3 x M4-6H through the 7.5 mm ears (engagement 7.1 mm); 2 x 4 H7 blind 6 (lower pins); 2 x 6.5 x 1.5 reliefs (upper-pin tips). Cross bores 4 H7 POS 0.02 | A | B | C."])
    ax = K.sec_ax(fig, (14, 150, 250, 120), [ch.shape], "y", yc, ((0, 70), (8, 36)), "SECTION A-A  y = 87.5 (slot centre)")
    K.dim(ax, (RC["land_x"][0], 16), (RC["land_x"][1], 16), off=-5, horizontal=True, fmt="{:.2f}", tol=" +-0.02")
    K.dim(ax, (RC["land_x"][1], 16), (RC["x_stop"], 16), off=-8, horizontal=True, fmt="{:.2f}", tol=" +-0.02")
    K.dim(ax, (2, 12), (2, RB["ear_top_z"]), off=-3, horizontal=False, fmt="{:.2f}")
    K.dim(ax, (60, 16), (60, 30.06), off=4, horizontal=False, fmt="{:.2f}", tol=" +0.04/-0.02")
    K.datum(ax, (RC["x_stop"], 25), "A", (69, 33))
    K.datum(ax, (RC["land_x"][0], 16), "C", (4, 10))
    ax = K.sec_ax(fig, (275, 150, 130, 120), [ch.shape], "x", RC["land_x"][0], ((yc - 26, yc + 26), (8, 36)), "SECTION B-B  x = 8.0 (rear land station)")
    K.dim(ax, (yc - 8.05, 22), (yc + 8.05, 22), off=6, horizontal=True, fmt="{:.2f}", tol=" +0.05/0")
    K.dim(ax, (yc - 21, RB["ear_top_z"]), (yc + 21, RB["ear_top_z"]), off=3, horizontal=True, fmt="{:.1f}")
    K.datum(ax, (yc, 16), "B", (yc + 14, 11))
    ax = K.hlr_ax(fig, (14, 52, 250, 88), ch.shape, "plan", "PLAN (from above): ears, screws, pins")
    figs.append(fig)
    return figs


def plate_sheets(parts, n0):
    from mechanical.prototype_x1c.rrx.structure import plate_holes, sole_screw_xy
    pl = next(p for p in parts if p.name == "chassis_plate")
    holes = plate_holes() + [(x, y, D.CLEAR["M3"], "csk_bottom", "lower-hull sole ring M3") for x, y in sole_screw_xy()]
    figs = []
    fig = K.sheet("CHASSIS PLATE", pl.pn, n0, material="6061-T6 plate 4.0 mm", finish="chromate conversion MIL-DTL-5541 type II class 3 (conductive)", notes=[
        "Blank waterjet / laser (profile +-0.2); all holes, countersinks (90 deg, from BELOW where marked csk_bottom), taps, reams and the four receiver-bridge pockets on one CNC fixture.",
        "DATUMS: A = plate top face (FLAT 0.3 overall, 0.04 over each receiver ear footprint); B, C = the two 4 H7 upper-pin holes of the LEFT channel (receiver datum chain).",
        f"Receiver: 4 pockets {RB['plate_pocket_depth']} +0.2/0 deep from below over the channel bridges; screw holes dia 6.0 +0.1/0 for the G10 top-hat bushings; 4 H7 upper-pin holes POS 0.02 | A | B | C.",
        "Hole table: sheet(s) following and dxf/RRP-F01_chassis_plate.dxf (+ _holes.csv). Coordinates base_link (x forward, y left)."])
    ax = K.hlr_ax(fig, (14, 60, 392, 200), pl.shape, "plan", "PLAN (from above, forward to the right)")
    for x, y, d, kind, why in holes:
        if kind == "ream":
            ax.plot([x], [y], "r+", ms=4)
    K.datum(ax, (RC["x_stop"] - 30, RC["shoe_y"] - 17), "B", (RC["x_stop"] - 10, RC["shoe_y"] + 30))
    figs.append(fig)
    per = 46
    for k in range(0, len(holes), per):
        fig = K.sheet("CHASSIS PLATE: HOLE TABLE", pl.pn, n0 + 1 + k // per, material="6061-T6 plate 4.0 mm", finish="chromate conversion")
        rows = [(i + 1, f"{x:.2f}", f"{y:.2f}", (f"{d:.2f}" if d else "-"), kind, why[:80]) for i, (x, y, d, kind, why) in enumerate(holes) if k <= i < k + per]
        K.table_ax(fig, (14, 52, 392, 228), rows, ["#", "x", "y", "dia", "operation", "purpose"], "HOLE TABLE (base_link mm)", fs=4.6)
        figs.append(fig)
    return figs


def shim_sheet(parts, n0):
    sh = next(p for p in parts if p.name == "receiver_shim_L_in")
    fig = K.sheet("RECEIVER THERMAL-BREAK SHIM (inboard strip; outboard strip RRP-F13 same notes)", sh.pn + " / RRP-F13", n0, material="NEMA G-10 sheet (FR4 class), 4.8 nominal ground to size",
                  finish="none; ground faces clean, no sealant", notes=[
                      f"THICKNESS {RB['shim_t']:.2f} +-{RB['shim_t_tol']:.2f}; FLAT {RB['shim_flatness']}; both faces PAR 0.01; the four strips of one robot ground in one set-up (L/R within 0.01), marked as a set.",
                      "Holes: 3 x 4.5 screw clearance; lower / upper pin holes 4.0 H8, the second hole of each pair a 4.6 x 4.0 slot along the pair line.",
                      "Thermal function (DEC-045): k 0.30 W/m K handbook class (UNVERIFIED) -> 0.081 W/K per channel calculated incl. screws, pins and air gaps (mech_calcs.md section 9).",
                      "Laminate orientation: plies parallel to the faces (compression normal to the laminate)."])
    K.hlr_ax(fig, (14, 120, 392, 150), sh.shape, "plan", "PLAN")
    return [fig]


def fab(parts, made):
    out = HERE / "drawings"
    out.mkdir(exist_ok=True)
    figs = []
    figs += plate_sheets(parts, len(figs) + 1)
    figs += channel_sheets(parts, len(figs) + 1)
    figs += shim_sheet(parts, len(figs) + 1)
    for rec in made:
        p = rec["part"]
        figs.append(generic_sheet(p, rec, len(figs) + 1))
        print(f"    sheet {len(figs)}: {p.pn} {rec['file']}", flush=True)
    with PdfPages(out / "RRP_fabrication_drawings.pdf") as pdf:
        for i, fig in enumerate(figs, 1):
            fig.text(0.97, 0.975, f"sheet {i} / {len(figs)}", ha="right", fontsize=6)
            pdf.savefig(fig)
            plt.close(fig)
    return len(figs)
