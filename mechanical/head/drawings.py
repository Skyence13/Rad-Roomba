"""Joint sections, fabrication drawings and assembly step images, all generated from the model.

Run: python -m mechanical.head.drawings [joints] [fab] [steps]
"""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from mechanical.common import params as P

from . import assembly as A
from . import draw as D
from . import hp as H
from . import parts as T
from .geom import HERE, compound

JOINTS, FAB, STEPS = HERE / "prototype" / "joints", HERE / "production" / "drawings", HERE / "prototype" / "assembly"
MAT_COL = {"frame": "#5b7f88", "receiver": "#b9c4c9", "deck": "#d9dee1", "emi": "#e2b65a", "lane": "#3aa39a", "optic": "#9fd0dc", "window": "#7d8f95",
           "rail": "#39525a", "switch": "#d05a4a", "elec": "#4c9a52", "cable": "#333333", "seal": "#1c1c1c", "aux": "#8e6bbf"}


def joint_fig(name, title, axis, value, region, parts, notes=(), dims=(), scale=4.0, exclude=(), travel_note=""):
    """Filled section through plane axis = value over region (drawing coordinates), at `scale`:1 (figure inches = mm * scale / 25.4)."""
    view = D.SEC_VIEWS[axis]
    origin = {"x": (value, 0, 0), "y": (0, value, 0), "z": (0, 0, value)}[axis]
    normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    (u0, u1), (v0, v1) = region
    fig = plt.figure(figsize=((u1 - u0) * scale / 25.4 + 0.6, (v1 - v0) * scale / 25.4 + 1.0))
    ax = fig.add_axes([0.02, 0.06, 0.96, 0.84])
    ax.set_aspect("equal"); ax.set_xlim(u0, u1); ax.set_ylim(v0, v1)
    used = {}
    for p in parts:
        if p.name in exclude or p.pn == "-":
            continue
        b = p.bb()
        k = "xyz".index(axis)
        if not (b[k] - 1e-6 <= value <= b[k + 3] + 1e-6):
            continue
        faces = D.section_faces(p.shape, origin, normal, view)
        if not faces:
            continue
        col = MAT_COL.get(p.group, "#999999")
        if p.material in ("AL6061", "AL5052", "SS304", "SS301", "STEEL", "BRASS") and p.group not in ("emi",):
            col = {"AL6061": "#cfd6da", "AL5052": "#cfd6da", "SS304": "#aeb7bd", "SS301": "#aeb7bd", "STEEL": "#9aa3a8", "BRASS": "#d9b65c"}[p.material]
        D.fill_faces(ax, faces, col, hatch="////" if p.kind == "envelope" else None)
        used[p.group if col == MAT_COL.get(p.group) else p.material] = col
    for (xy, text, xyt) in notes:
        D.note(ax, xy, text, xyt, fs=7)
    for d in dims:
        D.dim(ax, d[0], d[1], off=d[2], horizontal=d[3] if len(d) > 3 else None, fmt="{:.2f}", fs=6.5)
    ax.plot([u1 - 6, u1 - 1], [v0 + 0.5, v0 + 0.5], "k-", lw=2)
    ax.text(u1 - 3.5, v0 + 0.9, "5 mm", ha="center", fontsize=6.5)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{title}\nsection {axis} = {value:g} mm, drawn {scale:g}:1 (print at 100 %){travel_note}", fontsize=8, loc="left")
    hnd = [plt.Rectangle((0, 0), 1, 1, fc=c, ec="k", lw=0.4) for c in used.values()]
    fig.legend(hnd, list(used.keys()), fontsize=6, loc="lower center", ncol=min(len(used), 8), framealpha=0.9)
    JOINTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(JOINTS / f"{name}.png", dpi=220)
    fig.savefig(JOINTS / f"{name}.svg")
    plt.close(fig)


def joints():
    P_ = A.build("prototype")
    yL, yR = H.SEG_Y[1], H.SEG_Y[2]
    joint_fig("J1a_split_joint_plan_below_deck", "Split joint y = 0: U tongue-and-groove, dowel, bridge (plan below the deck)", "z", 19.0, ((66, 92), (-9, 9)), P_,
              notes=[((71.8, -0.8), "tongue 1.2 x 1.6 (left half)\nin groove, 0.15 clearance", (79, 6.5)), ((75.8, 0.5), "dowel 3 x 6", (84, -6.5)),
                     ((68.4, 3), "rear bridge 3 mm 6061\n(T-head to T-head)", (67, 7.5)), ((81.5, 5), "lane S1 cavity", (86, 3.5)), ((81.5, -5), "lane S2 cavity", (86, -3.5))],
              dims=[((80.7, -3.25), (80.7, 3.25), 2.5, False)], scale=6.0)
    joint_fig("J1b_split_joint_plan_front", "Split joint y = 0 at the front wall: tongue, dowel, centre bail block as front splice", "z", 19.0, ((176, 196), (-9, 9)), P_,
              notes=[((186.7, -0.8), "tongue", (178, 7)), ((184.0, 0.3), "dowel 3 x 6", (178, -7))], scale=6.0)
    joint_fig("J1c_split_joint_plan_upper_walls", "Split joint y = 0 in the upper walls: ship-lap under the lid gasket", "z", 36.0, ((66, 92), (-9, 9)), P_,
              notes=[((70.7, -1.0), "ship-lap 1.0 x 2.0\n(outer skin of the left half)", (78, 6.5)), ((69.0, 2), "bridge riser", (67, 7.5))], scale=6.0)
    joint_fig("J1d_split_joint_cross_section", "Split joint y = 0: cross-section at the row centre (rib halves, tongue, spreader, lid)", "x", H.ROW_X, ((-14, 14), (6, 47)), P_,
              notes=[((0.0, 13.1), "tongue (bottom run of the U)", (5.5, 8.2)), ((1.5, 29.7), "rib gasket strip 1.0 -> 0.6", (6, 31)), ((0, 31), "one-piece spreader 2 mm", (-13.5, 33)),
                     ((0, 44), "one-piece lid 2 mm", (-13.5, 46)), ((-2.2, 10.6), "cassette lip in groove", (-13.5, 12.5)), ((1.0, 20), "half rib 3.25", (6, 20))],
              dims=[((-3.25, 24), (3.25, 24), 2.0, True), ((-3.75, 9), (3.75, 9), -2.0, True)], scale=5.0)
    joint_fig("J2_cassette_and_seam_rib", "Window cassette at the S0 | S1 seam rib: lips, gasket lands, film, module seat, barrier", "x", H.ROW_X + 15, ((76, 99), (6.5, 33)), P_,
              notes=[((87.5, 9.2), "3.5 mm channel between cassettes", (89, 7.2)), ((85.25, 10.5), "lip 0.85 in groove", (77, 14)), ((84.3, 10.27), "gasket 0.8 -> 0.45", (77, 12)),
                     ((84.0, 10.02), "film on the cassette land, z 10.00", (77, 8.3)), ((84.0, 11.1), "module seat shoulder 0.5 (z 11.00)", (77, 16.5)),
                     ((87.5, 29.7), "rib gasket", (93, 30.6)), ((91.0, 19), "barrier plate + foam edge", (93, 21.5))],
              dims=[((83.75, 26), (91.25, 26), 1.5, True)], scale=6.0)
    joint_fig("J3_lid_wall_fence_front", "Lid, wall gasket, EMI fence and lid standoff at the front wall (y = 42, through a standoff)", "y", 42.0, ((172, 216), (5, 48)), P_,
              notes=[((186.9, 42.6), "lid gasket 1.2 -> 0.8", (192, 44.5)), ((183.0, 38), "M3 x 10.5 standoff on the fence foot\n(lid hard seat, fence bond)", (192, 38)), ((180.2, 37), "EMI fence 0.5 Al", (173, 40)),
                     ((179.0, 42.7), "conductive gasket", (173, 46)), ((186.0, 31), "spreader edge under the lip", (192, 32.5)), ((206.7, 15), "rail bar", (200, 26)), ((210.2, 15), "insert", (212, 26)),
                     ((185, 20), "front wall 6.5", (192, 20)), ((178, 35.3), "RR-HEAD-ACQ", (173, 33.5))],
              dims=[((188.2, 6.5), (205.2, 6.5), -0.8, True)], scale=4.0)
    joint_fig("J4_rail_guide_and_front_switch", "Leading rail guide rod, return spring, stop / switch pin and front rail switch (y = 87.0, 0.5 mm off the rod axis)", "y", H.SHOE_Y - 0.5, ((130, 216), (5, 48)), P_,
              notes=[((150, 14), "return spring in the blind bore", (140, 8)), ((175, 14), "guide rod 4 h6", (165, 8)), ((182.6, 22), "stop / switch pin 2.5", (160, 24)),
                     ((183.2, 37), "D2HW-C201M in the bay", (150, 40)), ((184.2, 15.2), "cam notch 1.3 deep, ramp 1.6", (194, 9)), ((206.7, 20), "bar 14 x 3", (196, 30)), ((210.2, 22), "insert (3 mm position)", (200, 36))],
              dims=[((188.2, 6.3), (205.2, 6.3), -0.6, True)], scale=3.0)
    joint_fig("J5_shoe_T_head_and_cable_port", "Receiver shoe T-head, isolator, spreader tab (y = 87.0; the J1 port is at y 76.2 since CR-M03, see the frame sheet)", "y", H.SHOE_Y - 0.5, ((60, 100), (8, 48)), P_,
              notes=[((66, 23), "x-stop shoulder x 65.7 (datum A)", (61, 12)), ((74.5, 23), "T-head 6061", (78, 12)), ((76, 29.75), "isolator 0.5 G10 (prototype)", (84, 26.5)), ((79, 31), "spreader tab, 4 x M3", (86, 34)),
                     ((71.5, 39), "rear wall (J1 port at y 76.2)", (84, 44)), ((90, 35.3), "RR-HEAD-ACQ", (90, 38.5))], scale=4.0)
    joint_fig("J6a_side_zone_tab_level", "Side zone, rear outer corner at the guide-tab level (z = 25.4): tabs in the slits, guide pins", "z", H.SLIT_Z[0] + 0.7, ((62, 84), (136, 178)), P_,
              notes=[((75.0, 168.5), "guide pin M3 in a 45 deg slot", (79, 176)), ((75.0, 145.7), "guide pin", (80, 150)), ((68.2, 160), "wing-tip return", (63, 156))], scale=5.0)
    joint_fig("J6b_side_zone_switch_level", "Side zone, rear outer corner at the switch level (z = 20.75): switch pocket, return plate, side strip", "z", H.SW_SIDE["z"], ((62, 84), (136, 178)), P_,
              notes=[((73.8, 156.75), "D2HW-C201M, plunger to the rear", (78, 164)), ((68.2, 150), "return plate 0.8 SS,\nadjusting screw on the plunger", (62.5, 140)), ((80, 174.6), "side strip 0.8, gap 0.95", (74, 177)),
                     ((81.5, 160), "lane S0 cavity", (79.5, 150))],
              dims=[((70.2, 138), (68.55, 138), -1.0, True)], scale=5.0)
    joint_fig("J7_chimney_coax_shield", "SiPM chimney: carriers, chimney insert, EMI liner, coax path to the board (lane S0 centre, y = 131.25)", "y", H.SEG_Y[0], ((68, 96), (8, 47)), P_,
              notes=[((73.15, 22), "EMI rear comb liner 0.5 Al", (69, 9.5)), ((74.9, 24), "chimney insert", (76, 9.5)), ((79.3, 13.7), "floor carrier", (86, 10)), ((79.3, 26), "reference carrier", (87, 21)),
                     ((79, 19), "light shelf + coax notch", (87, 17)), ((85, 35.3), "board rear edge", (90, 39)), ((77.5, 31), "coax: vertical run, R 6 bend\nto the rear-edge connector", (84, 44))], scale=5.0)
    # leading rail at full stroke
    Pf = A.build("prototype", travel=H.RAIL_GAP)
    joint_fig("J8_rail_full_stroke", "Leading rail on its positive stop: bar on the frame front face, bail arm folded into its groove (y = 160)", "y", H.BAIL_Y, ((172, 200), (5, 48)), Pf,
              notes=[((189.7, 29), "bail pivot wire 2.5", (194, 36)), ((187.2, 13), "arm in the 2.8 mm groove", (176, 8)), ((189.7, 15), "bar on the frame face", (194, 24))], scale=4.0, travel_note="; rail travel 17 mm")
    # lid fastening (shear panel) and the chimney drain
    yb = H.LID_BOSS_FRONT_Y[1]
    joint_fig("J9a_lid_front_boss", f"Lid screw into a front wall boss (y = {yb:g}): hard seat z 43.0 inside the gasket loop, M3 heat-set insert", "y", yb, ((172, 196), (26, 50)), P_,
              notes=[((H.LID_BOSS_FRONT_X, 39), "boss dia 6.6, M3 insert 4.0 x 6", (174, 47.5)), ((187.0, 42.6), "lid gasket 1.2 -> 0.8", (189, 48.5)),
                     ((H.LID_BOSS_FRONT_X, 46.5), "M3 button + bonded washer", (188, 31)), ((180.2, 36), "EMI fence", (173, 30))], scale=6.0)
    xb = H.LID_BOSS_SIDE_X[1]
    joint_fig("J9b_lid_side_boss", f"Lid screw into a side wall boss (x = {xb:g}): seat inside the gasket loop, side fence foot below", "x", xb, ((156, 178), (26, 50)), P_,
              notes=[((H.LID_BOSS_SIDE_Y, 39), "boss dia 6.6, M3 insert", (157, 47.5)), ((171.5, 42.6), "lid gasket", (172, 48.5)), ((164.0, 36), "side fence 0.5", (157, 29))], scale=6.0)
    joint_fig("J9c_lid_rear_standoff", "Rear lid line: M3 x 10.5 standoff clamping the EMI comb foot to the spreader (y = 0)", "y", 0.0, ((66, 92), (26, 50)), P_,
              notes=[((77.5, 38), "standoff M3 x 10.5 on the comb foot", (80, 47.5)), ((73.15, 37), "EMI comb 0.5", (67, 47.5)), ((76.8, 33), "rear spreader screw", (82, 29))], scale=6.0)
    yd = H.SEG_Y[0] + H.DRAIN["dy"]
    joint_fig("J10_chimney_drain", f"Light-trap drain of chimney S0 (y = {yd:g}): up, across, up -- three turns, no line of sight (tool-checked)", "y", yd, ((66, 84), (6, 20)), P_,
              notes=[((H.DRAIN["x_out"], 11.0), "outlet dia 1.2 (underside)", (66.5, 7.5)), ((73.0, 11.9), "channel 1.2 x 0.8", (76.5, 8.5)),
                     ((H.DRAIN["x_in"], 12.7), "inlet under the chimney insert", (76, 18.5)), ((76.5, 10), "cassette", (79, 7))], scale=8.0)
    return 15


# ------------------------------------------------------------------------------------------------ fabrication drawings
def _hlr_ax(fig, rect, shape, view, label, margin=14.0, hidden=False):
    vis, hid = D.hlr(shape, view, hidden)
    xs = [p[0] for ln in vis for p in ln]; ys = [p[1] for ln in vis for p in ln]
    w, h = max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin
    sc = min(rect[2] / w, rect[3] / h)
    ax = D.view_axes(fig, (rect[0], rect[1], w * sc, h * sc), (min(xs) - margin, max(xs) + margin), (min(ys) - margin, max(ys) + margin), label)
    if hid:
        D.plot_lines(ax, hid, color="#888", lw=0.25, ls=(0, (3, 2)))
    D.plot_lines(ax, vis, lw=0.45)
    return ax


def _sec_ax(fig, rect, shapes, axis, value, region, label, colors=None):
    view = D.SEC_VIEWS[axis]
    origin = {"x": (value, 0, 0), "y": (0, value, 0), "z": (0, 0, value)}[axis]
    normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    (u0, u1), (v0, v1) = region
    sc = min(rect[2] / (u1 - u0), rect[3] / (v1 - v0))
    ax = D.view_axes(fig, (rect[0], rect[1], (u1 - u0) * sc, (v1 - v0) * sc), (u0, u1), (v0, v1), label)
    for k, s in enumerate(shapes):
        D.fill_faces(ax, D.section_faces(s, origin, normal, view), (colors or ["#cfd6da"] * 9)[k], hatch="////" if k == 0 else None, lw=0.45)
    return ax


def fab():
    FAB.mkdir(parents=True, exist_ok=True)
    figs = []
    fr = T.frame("P")
    tv = lambda p: D.proj("top", p)
    # ---------------- sheet 1: frame, top and rear views
    fig = D.sheet("FRAME, ONE-PIECE", "RR-HD-P-101 sheet 1/2", notes=[
        "MATERIAL 6061-T6 plate 35 mm. FINISH: black anodise MIL-A-8625 type II class 2, 10-20 um, matte (bead blast before anodise, Ra <= 1.6 inside the four lane cavities).",
        "MASK (no anodise; chromate conversion MIL-DTL-5541 type II class 3): spreader seat z 30.0 (ribs, front and rear zone), wall top land z 42.2 (lid gasket / EMI land), lid boss tops z 43.0. T-head pockets ANODISED (not masked): 0.3 air gap + anodise isolate the frame from the shoes.",
        "THREADS: M2.5-6H x 5 deep at the 26 spreader / cassette stations, M3-6H x 6 at the bail-block stations (helicoil-free; 2 x D minimum engagement in the parent metal).",
        "Datum A = spreader seat plane; datum B = rear face x 70.2; datum C = centre plane (mid-plane of the two guide-rod bores). Head-level datums (receiver) are on RR-HD-S-111.",
        "Dimensions in brackets [ ] are base_link coordinates for cross-reference with mechanical/common/params.py."])
    ax = _hlr_ax(fig, (14, 150, 392, 130), fr, "top", "TOP VIEW (forward up, robot right to the right)", margin=16)
    x0, x1 = H.XR, H.XF
    D.dim(ax, tv((x0, H.YW, 0)), tv((x0, -H.YW, 0)), off=-9, horizontal=True, tol="  +-0.1")
    D.dim(ax, tv((x0, -H.YW, 0)), tv((x1, -H.YW, 0)), off=9, horizontal=False, tol=" +-0.1")
    for i, yc in enumerate(P.SEG_Y):
        D.dim(ax, tv((H.WIN_X1, yc + 40, 0)), tv((H.WIN_X1, yc - 40, 0)), off=3.5, horizontal=True, text="80.00", tol=" +0.05/0")
        D.note(ax, tv((H.ROW_X, yc, 0)), f"WINDOW S{i}\n80 x 100 through at z 10.5..11.0\ncavity 81.0 x 101.0 above z 11.0\n[y {yc:+.2f}]", fs=4.8, ha="center")
    D.dim(ax, tv((H.WIN_X0, P.SEG_Y[3] - 40, 0)), tv((H.WIN_X1, P.SEG_Y[3] - 40, 0)), off=5, horizontal=False, text="100.00", tol=" +0.05/0")
    D.dim(ax, tv((H.XF + 4, P.SEG_Y[0], 0)), tv((H.XF + 4, P.SEG_Y[1], 0)), off=6, horizontal=True, text="87.50", tol=" +-0.03 (3x)")
    D.dim(ax, tv((H.XR, 60, 0)), tv((H.WIN_X0, 60, 0)), off=-4, horizontal=False, text="11.00", tol=" +-0.05")
    D.note(ax, tv((H.ROW_X, 0, 0)), "POS 0.1 | A | B | C\n(4 windows as a pattern)", tv((H.ROW_X + 30, 12, 0)), box=True, fs=5)
    D.note(ax, tv((H.PIN_X, H.SHOE_Y, 0)), "2x dia 2.55 H8 pin bore", tv((H.PIN_X - 8, H.SHOE_Y + 22, 0)), fs=5)
    D.datum(ax, tv((H.XR, -120, 0)), "B", tv((H.XR - 9, -120, 0)))
    D.datum(ax, tv((H.XF, 0, 0)), "C", tv((H.XF + 10, 0, 0)))
    ax = _hlr_ax(fig, (14, 52, 392, 80), fr, "rear", "REAR VIEW (seen from behind)", margin=12)
    rv = lambda p: D.proj("rear", p)
    D.dim(ax, rv((0, H.YW, H.Z_FB)), rv((0, H.YW, H.Z_WALL_TOP)), off=7, horizontal=False, fmt="{:.2f}", tol=" +-0.05")
    D.dim(ax, rv((0, -H.YW, H.Z_FB)), rv((0, -H.YW, H.Z_SPR0)), off=-7, horizontal=False, fmt="{:.2f}", tol=" +-0.03")
    for s in (1, -1):
        D.dim(ax, rv((0, s * (H.SHOE_Y - H.THEAD_HY - 0.15), 16)), rv((0, s * (H.SHOE_Y + H.THEAD_HY + 0.15), 16)), off=-4, horizontal=True, fmt="{:.2f}", tol=" +0.1/0")
        D.note(ax, rv((0, s * H.SHOE_Y, 23)), "T-HEAD POCKET\n8.65 deep, z 15.9..30.0", fs=4.8, ha="center")
        D.note(ax, rv((0, H.PORT_Y["J1" if s > 0 else "J2"], 38)), f"PORT SLOT 11.0 wide at y {H.PORT_Y['J1' if s > 0 else 'J2']:+.1f}\nfloor z 33.5", fs=4.8, ha="center")
    D.dim(ax, rv((0, H.SHOE_Y, 9)), rv((0, -H.SHOE_Y, 9)), off=-5, horizontal=True, text="175.00", tol=" +-0.05")
    D.note(ax, rv((0, H.VENT[1], H.VENT[2])), "M6 x 0.75 vent", rv((0, H.VENT[1] + 14, H.VENT[2] + 7)), fs=5)
    D.datum(ax, rv((0, 150, H.Z_SPR0)), "A", rv((0, 150, 49)))
    figs.append(("RR-HD-P-101_frame_sheet1", fig))
    # ---------------- sheet 2: frame sections
    fig = D.sheet("FRAME, ONE-PIECE: SECTIONS", "RR-HD-P-101 sheet 2/2", notes=[
        "Section A-A: lane centre S1 (y 43.75) through the chimney. Section B-B: seam rib S0|S1 (y 87.5) through the guide-rod bore, pin bore and T-head pocket. Section C-C: x 131.2 across the S0|S1 rib and the outer wall.",
        "Guide-rod bore dia 4.00 H8 x 52 deep, PAR 0.05 to datum A and to each other; reamed after anodise mask or anodise-free (mask bore).",
        "Spreader seat FLAT 0.08 over the whole part; module seat shoulders z 11.00 PAR 0.05 | A; underside z 10.50 PAR 0.05 | A (cassette seat = film plane datum)."])
    ax = _sec_ax(fig, (14, 196, 250, 80), [fr], "y", P.SEG_Y[1], ((64, 194), (6, 47)), "SECTION A-A  y = 43.75 (lane centre S1)")
    D.dim(ax, (H.CAV_X0, 20), (H.CAV_X1, 20), off=3, horizontal=True, fmt="{:.2f}", tol=" +0.1/0")
    D.dim(ax, (H.WIN_X0, 10.7), (H.WIN_X1, 10.7), off=-3.2, horizontal=True, fmt="{:.2f}", tol=" +0.05/0")
    D.dim(ax, (H.XF, H.Z_FB), (H.XF, H.Z_SPR0), off=4, horizontal=False, fmt="{:.2f}", tol=" +-0.03")
    D.dim(ax, (H.XR, H.Z_FB), (H.XR, H.Z_WALL_TOP), off=-4, horizontal=False, fmt="{:.2f}", tol=" +-0.05")
    D.dim(ax, (H.CAV_X1, 25), (H.XF, 25), off=2, horizontal=True, fmt="{:.2f}")
    D.dim(ax, (H.CHIM_X0, 16), (H.CAV_X0, 16), off=-2.5, horizontal=True, fmt="{:.2f}")
    D.note(ax, (H.BAY_X1 + 0.5, 31), "spreader lip groove\n1.0 x 2.15", (176, 36), fs=5)
    D.note(ax, ((H.CAV_X0 + H.CAV_X1) / 2, 30.0), "FLAT 0.08", ((H.CAV_X0 + H.CAV_X1) / 2 - 20, 38), box=True, fs=5)
    D.datum(ax, (120, 30.0), "A", (120, 40))
    D.note(ax, (150, 11.0), "PAR 0.05 | A  (seat z 11.00, 4 lanes)", (150, 8), box=True, fs=5)
    ax = _sec_ax(fig, (14, 104, 250, 80), [fr], "y", H.SHOE_Y, ((64, 194), (6, 47)), "SECTION B-B  y = 87.5 (seam rib, rod bore, pin bore, T-head pocket)")
    D.dim(ax, (H.XF - H.ROD_BORE_DEPTH, H.ROD_Z), (H.XF, H.ROD_Z), off=-5, horizontal=True, fmt="{:.1f}", tol=" +0.5/0")
    D.dim(ax, (H.XF, H.Z_FB), (H.XF, H.ROD_Z), off=5, horizontal=False, fmt="{:.2f}", tol=" +-0.03")
    D.note(ax, (150, H.ROD_Z), "dia 4.00 H8, PAR 0.05 | A", (140, 22), box=True, fs=5)
    D.note(ax, (H.PIN_X, 24), "dia 2.55 H8", (170, 38), fs=5)
    D.dim(ax, (H.XR, 16), (H.THEAD_X1 + 0.15, 16), off=-3.5, horizontal=True, fmt="{:.2f}", tol=" +0.05/0")
    D.dim(ax, (H.XR - 2, H.SHOE_Z0 - 0.1), (H.XR - 2, H.Z_SPR0), off=-2, horizontal=False, fmt="{:.2f}", tol=" +0.05/0")
    for x in H.ROD_PAD_X:
        D.note(ax, (x, 30.0), "", None)
    D.note(ax, (H.ROD_PAD_X[2], 28), "5x M2.5 x 5 on hard pads z 30.00;\nrib top between pads z 29.40 (gasket relief)", (120, 40), fs=5)
    ax = _sec_ax(fig, (275, 150, 130, 130), [fr], "x", H.ROW_X, ((76, 178), (6, 47)), "SECTION C-C  x = 131.2 (left half shown)")
    D.dim(ax, (P.SEG_Y[0] - H.CAV_HY, 22), (P.SEG_Y[0] + H.CAV_HY, 22), off=2.5, horizontal=True, fmt="{:.2f}", tol=" +0.1/0")
    D.dim(ax, (P.SEG_Y[0] - 40, 10.7), (P.SEG_Y[0] + 40, 10.7), off=-3, horizontal=True, fmt="{:.2f}", tol=" +0.05/0")
    D.dim(ax, (P.SEG_Y[0] + H.CAV_HY, 18), (H.YW, 18), off=3, horizontal=True, fmt="{:.2f}", tol=" +-0.05")
    D.dim(ax, (H.SHOE_Y - H.RIB_W / 2, 26), (H.SHOE_Y + H.RIB_W / 2, 26), off=2, horizontal=True, fmt="{:.2f}", tol=" +-0.05")
    D.note(ax, (H.SHOE_Y, 10.8), "cassette lip grooves\n1.1 wide x 0.5 deep", (H.SHOE_Y + 12, 7.5), fs=5)
    ax = _sec_ax(fig, (275, 60, 130, 80), [fr], "x", H.ROW_X, ((160, 178), (6, 47)), "DETAIL: outer wall (x = 131.2)")
    D.dim(ax, (P.SEG_Y[0] + H.CAV_HY, 20), (H.YW, 20), off=2, horizontal=True, fmt="{:.2f}", tol=" +-0.05")
    D.dim(ax, (H.BAY_HY, 36), (H.YW, 36), off=2, horizontal=True, fmt="{:.2f}")
    D.note(ax, (170.8, 29.2), "45 deg relief", (163, 33), fs=5)
    figs.append(("RR-HD-P-101_frame_sheet2", fig))
    # ---------------- sheet 3: receiver shoe
    sh = T.shoe(1)
    fig = D.sheet("RECEIVER SHOE WITH T-HEAD (LH shown; RH identical, part is symmetric)", "RR-HD-S-111", notes=[
        "MATERIAL 6061-T6. FINISH: hard anodise 25-40 um ALL OVER, both builds (insulating: the head frame must not touch chassis metal through the shoes); mask threads only. No chromate bond faces. 0.5 G10 isolator on the T-head top in both builds.",
        "Datum A = x-stop shoulder face (x 65.7); datum B = shoe side faces (mid-plane, y +-87.5 in the head); datum C = shoe underside (z 16.00). These are the head datums of mechanical_interfaces.md section 1.",
        "4 x M3-6H x 7 in the T-head (spreader tab; was M4, changed so the screw heads clear the rear wall), 2 x M4-6H x 8 in each rear ear (bridge). Lead-in chamfers 3 x 45 deg on the four tip edges; tip face flat (HEAD_DOCK switch target on the LH shoe)."])
    ax = _hlr_ax(fig, (14, 160, 300, 110), sh, "top", "TOP VIEW", margin=14, hidden=True)
    y0 = H.SHOE_Y
    D.dim(ax, tv((H.SHOE_X0, y0 - 8, 0)), tv((H.XSTOP, y0 - 8, 0)), off=-10, horizontal=False, fmt="{:.2f}", tol=" +-0.05")
    D.dim(ax, tv((H.XSTOP, y0 - 20, 0)), tv((H.XR, y0 - 20, 0)), off=-6, horizontal=False, fmt="{:.2f}", tol=" +-0.03")
    D.dim(ax, tv((H.XR, y0 - 30, 0)), tv((H.THEAD_X1, y0 - 30, 0)), off=-4, horizontal=False, fmt="{:.2f}", tol=" 0/-0.05")
    D.dim(ax, tv((30, y0 + 8, 0)), tv((30, y0 - 8, 0)), off=-8, horizontal=True, text="16.00", tol=" -0.02/-0.06 (f8 class fit to the fitted channel)")
    D.dim(ax, tv((H.THEAD_X1, y0 + 30, 0)), tv((H.THEAD_X1, y0 - 30, 0)), off=6, horizontal=True, fmt="{:.2f}", tol=" 0/-0.1")
    D.dim(ax, tv((H.XSTOP, y0 + 20, 0)), tv((H.XSTOP, y0 - 20, 0)), off=-14, horizontal=True, fmt="{:.2f}")
    D.datum(ax, tv((H.XSTOP, y0 + 14, 0)), "A", tv((H.XSTOP - 8, y0 + 26, 0)))
    D.datum(ax, tv((40, y0 - 8, 0)), "B", tv((40, y0 - 22, 0)))
    D.note(ax, tv((H.XSTOP, y0 - 14, 0)), "PERP 0.03 | C | B\nFLAT 0.02", tv((H.XSTOP - 6, y0 - 34, 0)), box=True, fs=5)
    ax = _hlr_ax(fig, (14, 60, 300, 90), sh, "left", "SIDE VIEW (from the left; forward to the left)", margin=12, hidden=True)
    lv = lambda p: D.proj("left", p)
    D.dim(ax, lv((H.SHOE_X0, 0, 16)), lv((H.SHOE_X0, 0, 30)), off=8, horizontal=False, text="14.00", tol=" -0.02/-0.06")
    D.dim(ax, lv((H.THEAD_X1, 0, 16)), lv((H.THEAD_X1, 0, 29.5)), off=-6, horizontal=False, fmt="{:.2f}", tol=" +-0.03")
    D.dim(ax, lv((P.RECEIVER["land_x"][0], 0, 16)), lv((P.RECEIVER["land_x"][1], 0, 16)), off=-7, horizontal=True, text="54.0 (land base in the channel)")
    D.datum(ax, lv((35, 0, 16)), "C", lv((35, 0, 6)))
    D.note(ax, lv((35, 0, 16)), "FLAT 0.03; PAR 0.03 to the T-head top", lv((50, 0, 8)), box=True, fs=5)
    ax = _hlr_ax(fig, (322, 150, 85, 120), sh, "rear", "REAR VIEW", margin=10)
    figs.append(("RR-HD-S-111_receiver_shoe", fig))
    # ---------------- sheet 4: spreader
    sp = T.spreader()
    fig = D.sheet("SPREADER PLATE (FRAME net plane)", "RR-HD-S-121", notes=[
        "MATERIAL 5052-H32 or 6061-T6 sheet 2.00 +-0.05, flatness 0.15 over 340. FINISH: chromate conversion (conductive) both sides; no anodise. Underside: heater film + rib gasket strips + lane pads bonded per assembly.md.",
        "Profile and holes per DXF RR-HD-S-121_spreader.dxf (base_link x, y). 8 x clinch standoff M2.5 x 2.5 at the board holes: top face of the standoffs z 34.50 +-0.05 above datum (PCB underside), POS dia 0.2.",
        "17 x dia 3.2 countersunk 90 deg on the UNDERSIDE for M3 x 6 (lid standoffs M3 x 11 production / x 10.5 prototype). 8 x dia 4.6 for M3 low-head with insulating shoulder washers (prototype) at the T-head tabs. 10 rib holes dia 2.8 countersunk 90 deg x dia 5.2 on TOP (ISO 10642 M2.5 flush: under the board).",
        "TAP M2.5 through at the fence-foot and switch-saddle stations (red in the DXF). Deburr both sides; no burr on the front edge (it slides under the frame lip)."])
    ax = _hlr_ax(fig, (14, 120, 392, 160), sp, "top", "TOP VIEW (forward up, robot right to the right)", margin=16)
    D.dim(ax, tv((H.SPR_X0, H.SPR_HY, 0)), tv((H.SPR_X0, -H.SPR_HY, 0)), off=-10, horizontal=True, fmt="{:.2f}", tol=" +-0.1")
    D.dim(ax, tv((H.SPR_X0, -H.SPR_HY, 0)), tv((H.SPR_X1, -H.SPR_HY, 0)), off=9, horizontal=False, fmt="{:.2f}", tol=" 0/-0.1")
    D.dim(ax, tv((H.SPR_X0, H.SEG_Y[3] - 9, 0)), tv((H.SPR_NOTCH_X, H.SEG_Y[3] - 9, 0)), off=4, horizontal=False, fmt="{:.2f}")
    D.dim(ax, tv((H.SPR_NOTCH_X, H.SEG_Y[0] + 9, 0)), tv((H.SPR_NOTCH_X, H.SEG_Y[0] - 9, 0)), off=5, horizontal=True, fmt="{:.2f}")
    for k, (x, y, _) in enumerate(T.board_holes(), start=1):
        D.note(ax, tv((x, y, 0)), f"H{k}", tv((x + 5, y + 4, 0)), fs=5, color="#8a0000")
    D.note(ax, tv((H.ROW_X, 0, 0)), "8x board standoff: POS dia 0.2 | A(plate) | H1 | H3", tv((H.ROW_X - 14, 30, 0)), box=True, fs=5)
    rows = {}
    for x, y, dia, why in T.spreader_holes():
        rows.setdefault((dia, why), []).append((x, y))
    bg = fig.axes[0]
    yy = 112
    bg.text(14, yy, "HOLE TABLE (base_link x, y; full coordinates in the DXF)", fontsize=6, weight="bold")
    for (dia, why), pts in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        yy -= 5.2
        bg.text(14, yy, f"{len(pts):2d} x dia {dia:g}  {why}:  " + "  ".join(f"({x:.1f}, {y:+.1f})" for x, y in pts[:9]) + (" ..." if len(pts) > 9 else ""), fontsize=4.6)
    figs.append(("RR-HD-S-121_spreader", fig))
    # ---------------- sheet 5: lid, blister, shield can
    fig = D.sheet("LID, J1 BLISTER AND LANE SHIELD CAN", "RR-HD-S-122 / RR-HD-S-123 / RR-HEAD-SHLD-A", notes=[
        f"LID: 5052-H32 2.00, chromate conversion inside (conductive), black anodise or powder coat outside. Flatness 0.2. {T.lid_count()} x dia 3.4 for M3 button head + bonded sealing washer: {len(T.lid_holes())} standoffs (labelled) + 18 frame bosses (front x 184.2, sides y +-168.4).",
        f"BLISTER: 1.0 aluminium, bonded with conductive epoxy bead + 2 x dia 2.4 blind rivets (front) and clamped by three lid screws (rear, y 57.0 / 90.3 / 117.5) over the {H.LID_OPENING[1] - H.LID_OPENING[0]:.1f} x {H.LID_OPENING[3] - H.LID_OPENING[2]:.1f} opening (J2001 / J2601 headers to v 20 and mated plugs from v -1.4, 8.9 mm above the PCB top; IB-19, IB-52, CR-M06).",
        "SHIELD CAN RR-HEAD-SHLD-A: 0.20 tin-plated steel (or C770 nickel silver), folded 5-sided can 36.0 x 32.0 x 5.0 outside (+0/-0.1), corners open <= 0.3; two mouse holes 2.0 x 1.2 in the rear wall for the anode traces;",
        "mouse holes at du -10.38 / +11.87 (CR-M04, anode U.FL pads); held by 12 SMT clips on board GND (side walls at v 23.5 / 29.0 / 34.75, CR-M07: dimples follow) -- not connected to the lid. Flat pattern: RR-HEAD-SHLD-A_lane_shield_can.dxf. Positions on the board: du -18..+18, v 8.25..40.25 about each lane centre (CR-M01)."])
    ld = T.lid().fuse(T.j1_blister())
    ax = _hlr_ax(fig, (14, 150, 392, 130), ld, "top", "LID WITH BLISTER, TOP VIEW", margin=16)
    i = H.LID_INSET
    D.dim(ax, tv((H.XR + i, H.YW - i, 0)), tv((H.XR + i, -H.YW + i, 0)), off=-10, horizontal=True, fmt="{:.2f}", tol=" +-0.1")
    D.dim(ax, tv((H.XR + i, -H.YW + i, 0)), tv((H.XF - i, -H.YW + i, 0)), off=9, horizontal=False, fmt="{:.2f}", tol=" +-0.1")
    for x, y in T.lid_holes():
        D.note(ax, tv((x, y, 0)), f"({x:.1f}, {y:+.1f})", tv((x - 6 if x > 100 else x + 6, y, 0)), fs=4.5)
    a, b, c, e = H.LID_OPENING
    D.dim(ax, tv((a, e, 0)), tv((a, c, 0)), off=-4, horizontal=True, fmt="{:.1f}")
    D.dim(ax, tv((a, c, 0)), tv((b, c, 0)), off=4, horizontal=False, fmt="{:.1f}")
    can = T.shield_can()
    ax = _hlr_ax(fig, (14, 62, 120, 75), can, "top", "SHIELD CAN, TOP", margin=8)
    D.dim(ax, tv((0, 18, 0)), tv((0, -18, 0)), off=-4, horizontal=True, fmt="{:.2f}", tol=" 0/-0.1")
    D.dim(ax, tv((0, -18, 0)), tv((32, -18, 0)), off=4, horizontal=False, fmt="{:.2f}", tol=" 0/-0.1")
    ax = _hlr_ax(fig, (150, 62, 120, 60), can, "rear", "SHIELD CAN, REAR WALL (mouse holes)", margin=6)
    D.dim(ax, D.proj("rear", (0, 18, 0)), D.proj("rear", (0, 18, 5)), off=-3, horizontal=False, fmt="{:.2f}", tol=" 0/-0.1")
    figs.append(("RR-HD-S-122_lid_blister_shield_can", fig))
    # ---------------- sheet 6: assembly with balloons and BOM
    Pp = A.build("production")
    fig = D.sheet("HEAD ASSEMBLY, PRODUCTION", "RR-HD-P-000", notes=[
        "Torques: M2.5 into aluminium 0.45 N m, M3 0.9 N m, M4 (bridge ears) 2.0 N m (A2-70, medium thread-lock on every screw that is not a service screw). Lid: 35 x M3 button + bonded washer, 0.6 N m, centre outward.",
        "Sealing: lid gasket = conductive silicone elastomer (Ni/graphite) in the wall-top land; cassette gaskets and rib strips = black closed-cell silicone; pigtails = potted cable-breakout boots on the lid (review M6); vent = ePTFE M6.",
        "End-of-line tests and service access: production/README.md. Datums A, B, C on the shoes (RR-HD-S-111); film plane and standoff GD&T on sheet RR-HD-P-000-ICD."])
    main = [p for p in Pp if p.group in ("frame", "receiver", "deck", "rail", "window") and p.kind != "purchased" or p.name in ("lid_standoffs",)]
    ax = _hlr_ax(fig, (14, 165, 250, 115), compound([p.shape for p in main if p.name not in ("lid", "j1_blister", "keeper")] + [T.pcb()]), "top", "TOP VIEW, LID AND KEEPER REMOVED", margin=14)
    items = [("frame", "RR-HD-P-101", "Frame, CNC 6061", 1, (150, -120)), ("shoe_L", "RR-HD-S-111", "Receiver shoe with T-head", 2, (30, 87.5)), ("bridge", "RR-HD-S-114", "Rear bridge / keeper hinge", 1, (68, 30)),
             ("spreader", "RR-HD-S-121", "Spreader plate 2 mm", 1, (100, -150)), ("pcb", "EL-RR-HEAD-ACQ", "Head acquisition board", 1, (140, 60)), ("rail_bar", "RR-HD-S-401", "Leading rail bar", 1, (206.5, -60)),
             ("rail_insert_0", "RR-HD-P-411", "Wear insert, reversible 3 / 5 mm", 4, (210.5, -130)), ("guide_rod_L", "RR-HD-S-402", "Guide rod 4 h6", 2, (196, 87.5)), ("bail", "RR-HD-S-403", "Anti-racking bail", 1, (189.7, 60)),
             ("side_rail_L", "RR-HD-S-431/432", "Side rail LH / RH", 2, (130, 174.6)), ("lid_standoffs", "PUR-SO-M3x11", "Lid standoff M3 x 11", len(T.lid_holes()), (183, 130)), ("sw_front", "PUR-D2HW", "D2HW-C201M (front, 2 side, lid)", 4, (183, 87.5)),
             ("S1_shield_can", "RR-HEAD-SHLD-A", "Lane shield can", 4, (104, 43.75)), ("boot_J1", "RR-HD-P-511/512", "Pigtail boot J1 / J2", 2, (80.0, 79.5))]
    offs = [(-20, -18), (-10, 16), (-14, -14), (-22, 12), (0, 22), (16, -8), (18, 10), (16, 14), (18, 22), (-6, 12), (12, 20), (22, 4), (-10, 20), (-14, 22)]
    for k, ((nm, pn, desc, qty, xy), o) in enumerate(zip(items, offs), start=1):
        p2 = tv((xy[0], xy[1], 0))
        D.balloon(ax, p2, k, (p2[0] + o[0], p2[1] + o[1]))
    ax = _sec_ax(fig, (14, 70, 250, 80), [p.shape for p in Pp if p.pn != "-" and p.bb()[1] <= P.SEG_Y[1] <= p.bb()[4]], "y", P.SEG_Y[1], ((60, 216), (4, 51)), "SECTION y = 43.75 (lane S1 centre)",
                  colors=["#cfd6da", "#b8c2c7", "#9fd0dc", "#3aa39a", "#e2b65a", "#7d8f95", "#4c9a52", "#39525a", "#aaaaaa"] * 12)
    lane_items = [("S1_cassette", "RR-HD-P-201", "Window cassette with film", 4, (131, 9)), ("S1_floor_module", "OEM-FLOOR", "OEM floor assembly", 4, (140, 13.5)), ("S1_barrier", "RR-HD-P-302", "Barrier plate + rings P-301/303", 4, (150, 19)),
                  ("S1_ref_module", "OEM-REF", "OEM reference assembly", 4, (160, 26)), ("S1_chimney_insert", "RR-HD-P-304", "Chimney insert", 4, (74.8, 22)), ("lid", "RR-HD-S-122", "Lid 2 mm + blister S-123", 1, (120, 44)),
                  ("keeper", "RR-HD-S-115", "Keeper plate, hinged", 1, (100, 46.6))]
    for k, (nm, pn, desc, qty, xy) in enumerate(lane_items, start=len(items) + 1):
        D.balloon(ax, xy, k, (xy[0] + (8 if xy[0] < 150 else -8), xy[1] + (9 if xy[1] > 20 else -7)))
    bg = fig.axes[0]
    bx, by = 275, 280
    bg.text(bx, by, "ITEM  PART NUMBER         DESCRIPTION                              QTY", fontsize=5.6, family="monospace", weight="bold")
    for k, (nm, pn, desc, qty, xy) in enumerate(items + lane_items, start=1):
        bg.text(bx, by - 5.2 * k, f"{k:>3}   {pn:<19} {desc:<40} {qty:>3}", fontsize=5.2, family="monospace")
    bg.text(bx, by - 5.2 * (len(items) + len(lane_items) + 2), "Complete variant BOM (fasteners, gaskets, purchased parts):\nproduction/bom_production.csv", fontsize=5.5)
    figs.append(("RR-HD-P-000_assembly", fig))
    # ---------------- sheet 7: interface control (datums, film plane, standoffs)
    fig = D.sheet("HEAD INTERFACE CONTROL: DATUMS, WINDOW PLANE, BOARD STANDOFFS", "RR-HD-P-000-ICD (applies to both builds)", notes=[
        "Datum A: x-stop shoulder faces of both shoes (x 65.70). Datum B: LH shoe side faces (y +87.50, fitted channel). Datum C: undersides of both shoes (z 16.00). Verified on the bench cradle, which reproduces A, B, C.",
        "Window plane (film underside): z 10.00 = 6.00 below datum C; PROFILE 0.6 | C (prototype), 0.3 | C (production) over the four windows; window pattern POS 0.3 | A | B | C.",
        "Board standoff tops: 18.50 above datum C (z 34.50), each +-0.10; pattern POS dia 0.3 | A | B. Lid top 29.00 above datum C (z 45.00) +-0.3. Rail underside 3.00 +-0.2 (or 5.00 +-0.2) below the window plane.",
        "Leading rail front face x 212.2 unloaded, 195.2 at full stroke (146.5 / 129.5 from datum A), inside the draft6 envelope x 212.5. Insulating jacket RR-HD-S-131/132: top z 48.0, front band to x 191.2.",
        "GROUNDING (both builds): head FRAME isolated from the receiver shoes (G10 isolators, insulating washers, anodised shoes and pockets); board R2801 fitted; cable shells to FRAME via 1 Mohm // 10 nF."])
    sub = [p for p in Pp if p.group in ("frame", "receiver", "window", "rail", "deck") and p.kind != "purchased"]
    ax = _hlr_ax(fig, (14, 150, 392, 130), compound([p.shape for p in sub]), "bottom", "VIEW FROM THE FLOOR (forward up)", margin=16)
    bv = lambda p: D.proj("bottom", p)
    for i_, yc in enumerate(P.SEG_Y):
        D.note(ax, bv((H.ROW_X, yc, 0)), f"S{i_}  80 x 100\ny {yc:+.2f}", fs=5.5, ha="center")
    D.dim(ax, bv((H.XSTOP, 60, 0)), bv((H.ROW_X, 60, 0)), off=-6, horizontal=False, text="65.50 (datum A to row centre)", fs=5)
    D.dim(ax, bv((H.XSTOP, -60, 0)), bv((H.WIN_X0, -60, 0)), off=6, horizontal=False, text="15.50", fs=5)
    D.dim(ax, bv((H.XF + 30, P.SEG_Y[0], 0)), bv((H.XF + 30, P.SEG_Y[3], 0)), off=6, horizontal=True, text="262.50 (3 x 87.50)")
    D.dim(ax, bv((H.XF + 30, -175, 0)), bv((H.XF + 30, 175, 0)), off=14, horizontal=True, text="350.0 over the leading rail and side rails")
    D.datum(ax, bv((H.XSTOP, 87.5 + 14, 0)), "A", bv((H.XSTOP - 10, 87.5 + 30, 0)))
    D.datum(ax, bv((30, 87.5 + 8, 0)), "B", bv((30, 87.5 + 26, 0)))
    D.note(ax, bv((H.ROW_X, 0, 0)), "POS 0.3 | A | B | C  (4 windows)", bv((H.ROW_X + 34, 0, 0)), box=True, fs=5.5)
    ax = _sec_ax(fig, (14, 62, 300, 78), [p.shape for p in Pp if p.group in ("frame", "receiver", "window", "deck", "rail", "elec") and p.pn != "-" and p.bb()[1] <= H.SHOE_Y <= p.bb()[4]], "y", H.SHOE_Y, ((0, 216), (2, 51)),
                  "SECTION y = 87.5 (LH shoe, datum C; film plane and standoff heights)", colors=["#cfd6da", "#b8c2c7", "#d9dee1", "#aaaaaa"] * 30)
    D.dim(ax, (40, 16), (40, 10), off=-30, horizontal=False, text="6.00 (C to film plane)", fs=5)
    D.dim(ax, (87.7, 16), (87.7, 34.5), off=16, horizontal=False, text="18.50 +-0.10 (C to standoff top)", fs=5)
    D.dim(ax, (H.XSTOP, 47), (212.2, 47), off=2, horizontal=True, text="146.5 (A to rail front, at rest)", fs=5)
    D.dim(ax, (205.2, 5), (H.XF, 5), off=-1.5, horizontal=True, text="17.0 stroke", fs=5)
    D.datum(ax, (30, 16), "C", (30, 6))
    D.datum(ax, (H.XSTOP, 23), "A", (56, 40))
    figs.append(("RR-HD-P-000-ICD_interface_control", fig))
    # ---------------- sheet 8: rail parts
    fig = D.sheet("RAIL PARTS: BAR, GUIDE ROD, BAIL, WEAR INSERT", "RR-HD-S-401 / -402 / -403 / RR-HD-P-411", notes=[
        "BAR RR-HD-S-401: 6061-T6 flat 14 x 3 x 350, hard anodise; 2 x dia 3.4 at y +-87.5 (rod screws), 8 x M3 tapped for the inserts at z 14.0, 2 x 2 dia 2.4 for the bail clips at y +-160.",
        "GUIDE ROD RR-HD-S-402: stainless 1.4305 dia 4.00 h6 x 67, crowned front end with M3 x 8 thread, cam notch 1.3 deep with a 39 deg ramp (see detail), ground Ra 0.4. BAIL RR-HD-S-403: spring wire 1.4310 dia 2.5, arms 16.5 at 90 deg.",
        "INSERT RR-HD-P-411: POM-C black (prototype: PA-CF printed), 87.3 x 16 x 4; hole row 7.0 from one long edge and 9.0 from the other: edge marked '3' down = 3 mm projection, flipped ('5' down) = 5 mm projection."])
    ax = _hlr_ax(fig, (14, 200, 392, 70), T.rail_bar().fuse(T.insert_segment(0)).fuse(T.insert_segment(3)), "front", "BAR WITH TWO OF FOUR INSERTS, FRONT VIEW", margin=10)
    fv = lambda p: D.proj("front", p)
    D.dim(ax, fv((0, -175, 8)), fv((0, 175, 8)), off=-6, horizontal=True, fmt="{:.1f}", tol=" +-0.2")
    D.dim(ax, fv((0, 175, 8)), fv((0, 175, 22)), off=6, horizontal=False, fmt="{:.1f}")
    D.dim(ax, fv((0, -175, 7)), fv((0, -175, 23)), off=-6, horizontal=False, fmt="{:.1f}")
    rod = T.guide_rod(1)
    ax = _sec_ax(fig, (14, 110, 250, 70), [rod], "y", H.SHOE_Y, ((160, 208), (9, 19)), "GUIDE ROD, LONGITUDINAL SECTION (cam notch)", colors=["#aeb7bd"])
    D.dim(ax, (163.2, 12), (205.2, 12), off=-1.5, horizontal=True, fmt="{:.1f}")
    D.dim(ax, (H.PIN_X - 1.3, 16), (H.PIN_X + 1.3, 16), off=1.2, horizontal=True, fmt="{:.2f}")
    D.dim(ax, (H.PIN_X + 4.5, 14.7), (H.PIN_X + 4.5, 16.0), off=2, horizontal=False, fmt="{:.2f}", tol=" +-0.03")
    bl, _ = T.bail()
    ax = _hlr_ax(fig, (275, 100, 130, 90), bl, "left", "BAIL, SIDE VIEW (rest position)", margin=6)
    figs.append(("RR-HD-S-40x_rail_parts", fig))
    with PdfPages(FAB / "RR-HD-P_fabrication_drawings.pdf") as pdf:
        for name, f in figs:
            f.savefig(FAB / f"{name}.svg")
            pdf.savefig(f)
            plt.close(f)
    return len(figs)


# ------------------------------------------------------------------------------------------------ assembly step images
def steps():
    STEPS.mkdir(parents=True, exist_ok=True)
    Pp = {p.name: p for p in A.build("prototype")}
    grey = "#b9c0c4"

    def img(n, title, new, old, explode=(0, 0, 30), azim=-58, elev=30, labels=(), per=None):
        items = [(Pp[k].shape, grey, (0, 0, 0)) for k in old if k in Pp]
        for k in new:
            if k in Pp:
                items.append((Pp[k].shape, Pp[k].color if Pp[k].color != "#111111" else "#444444", (per or {}).get(k, explode)))
        D.render(items, STEPS / f"step_{n:02d}.png", azim=azim, elev=elev, title=f"Step {n}: {title}", labels=labels, size=(1400, 880))

    lanes = lambda *keys: [f"S{i}_{k}" for i in range(4) for k in keys]
    s1 = ["frame_L", "frame_R", "shoe_L", "shoe_R", "shoe_isolator_L", "shoe_isolator_R", "bridge"]
    img(1, "join the frame halves, fit shoes, isolators and the rear bridge", s1, [], per={"frame_L": (0, 25, 0), "frame_R": (0, -25, 0), "shoe_L": (-40, 25, 0), "shoe_R": (-40, -25, 0),
        "shoe_isolator_L": (-40, 25, 12), "shoe_isolator_R": (-40, -25, 12), "bridge": (-60, 0, 0)}, azim=-125, elev=32,
        labels=["2 dowels 3 x 6 in the joint; tongue into groove; M4 x 10 bridge screws into the T-head ears (2.0 N m)"])
    s2 = ["side_rail_L", "side_rail_R", "guide_pins_L", "guide_pins_R", "sw_side_L", "sw_side_R", "guide_rod_L", "guide_rod_R", "rod_spring_L", "rod_spring_R", "stop_pin_L", "stop_pin_R"]
    img(2, "side rails, guide pins, side switches; rod springs, guide rods and stop pins", s2, s1, per={"side_rail_L": (-25, 25, 0), "side_rail_R": (-25, -25, 0), "guide_pins_L": (0, 0, 35), "guide_pins_R": (0, 0, 35),
        "sw_side_L": (-30, 0, 0), "sw_side_R": (-30, 0, 0), "guide_rod_L": (45, 0, 0), "guide_rod_R": (45, 0, 0), "rod_spring_L": (70, 0, 0), "rod_spring_R": (70, 0, 0), "stop_pin_L": (0, 0, 40), "stop_pin_R": (0, 0, 40)},
        azim=-125, elev=34, labels=["grease the rod bores; pins drop in from the top and are trapped by the spreader"])
    s3 = lanes("floor_module", "spacer_lower", "barrier", "spacer_upper", "ref_module", "floor_carrier", "ref_carrier", "floor_sipm", "ref_sipm", "chimney_insert")
    per = {}
    for i in range(4):
        for k, dz in (("floor_module", 25), ("floor_carrier", 25), ("floor_sipm", 25), ("spacer_lower", 45), ("barrier", 60), ("spacer_upper", 75), ("ref_module", 95), ("ref_carrier", 95), ("ref_sipm", 95), ("chimney_insert", 120)):
            per[f"S{i}_{k}"] = (0, 0, dz)
    img(3, "load the four lane kits from above", s3, s1 + s2, per=per, labels=["floor assembly on the seat shoulder, lower ring, barrier, upper ring, reference assembly, chimney insert; shims as needed"])
    s4 = ["spreader", "rib_gaskets", "board_standoffs", "lid_standoffs", "lid_standoffs_11"] + lanes("pad", "heater")
    img(4, "spreader with heater zones, pads and rib gaskets: front edge under the lip, then screw down", s4, s1 + s2 + s3, explode=(0, 0, 45), labels=["M2.5 x 8 into the rib and rear-zone inserts 0.35 N m; M3 x 8 low-head with insulating washers into the T-heads 0.9 N m"])
    s5 = ["fence_front", "fence_side_L", "fence_side_R", "fence_rear", "fence_gaskets", "pcb", "sw_front", "sw_front_saddle", "sw_lid", "sw_lid_saddle", "boot_J1", "boot_J2", "holster_J1", "holster_J2", "pigtail_J1", "pigtail_J2", "plug_J1", "plug_J2",
          "thermal_cutout", "ntc", "desiccant", "vent"] + [f"S{i}_shield_can" for i in range(4)]
    img(5, "EMI fences, board, shield cans, switches, pigtail boots and holsters", s5, s1 + s2 + s3 + s4, explode=(0, 0, 40), per={"fence_rear": (-20, 0, 55), "pcb": (0, 0, 70), **{f"S{i}_shield_can": (0, 0, 95) for i in range(4)},
        "pigtail_J1": (-30, 0, 20), "pigtail_J2": (-30, 0, 20), "plug_J1": (-30, 0, 20), "plug_J2": (-30, 0, 20)}, labels=["8 x M2.5 x 5 board screws 0.35 N m; coax pigtails up through the spreader notches (R >= 6 mm)"])
    s6 = ["lid", "lid_gasket", "lid_liner", "j1_blister", "keeper", "keeper_pin"]
    img(6, "lid with gasket (35 M3 + bonded washers), keeper plate swings down over it", s6, s1 + s2 + s3 + s4 + s5, explode=(0, 0, 40), per={"keeper": (-10, 0, 75), "keeper_pin": (-10, 40, 75)}, labels=["lid screws 0.6 N m, cross pattern from the centre"])
    allabove = s1 + s2 + s3 + s4 + s5 + s6
    s7 = lanes("cassette", "film", "cassette_gasket")
    img(7, "underside: window cassettes with film and gasket (4 x M2.5 countersunk each)", s7, [k for k in allabove if not k.startswith(("pigtail", "plug"))], explode=(0, 0, -45), azim=-58, elev=-32,
        labels=["cassettes are identical; change a window without opening the head (0.3 N m, hard seats set the film plane)"])
    s8 = ["bail", "bail_block_C", "bail_block_L", "bail_block_R", "rail_bar", "bail_clip_L", "bail_clip_R"] + [f"rail_insert_{k}" for k in range(4)]
    img(8, "leading rail: bail and bearing blocks, bar on the two rods, reversible inserts", s8, [k for k in allabove + s7 if not k.startswith(("pigtail", "plug"))],
        per={"bail": (18, 0, 0), "bail_block_C": (30, 0, 0), "bail_block_L": (30, 0, 0), "bail_block_R": (30, 0, 0), "rail_bar": (45, 0, 0), "bail_clip_L": (45, 0, 0), "bail_clip_R": (45, 0, 0),
             **{f"rail_insert_{k}": (70, 0, 0) for k in range(4)}}, azim=-40, elev=24, labels=["insert edge marked 3 down = 7 mm floor clearance; flipped (5 down) = 5 mm"])
    # transport cover and cradle
    done = [k for k in allabove + s7 + s8 if not k.startswith(("pigtail", "plug"))]
    items = [(Pp[k].shape, grey, (0, 0, 0)) for k in done] + [(T.transport_cover(1), "#8e6bbf", (0, 0, -40)), (T.transport_cover(-1), "#8e6bbf", (0, 0, -40))]
    D.render(items, STEPS / "step_09.png", azim=-58, elev=-28, title="Step 9: transport covers clip over the shoes and the rail (one per half)", size=(1400, 880),
             labels=["hook the front lip over the rail insert, swing up, snap the bridge over the shoe"])
    items = [(Pp[k].shape, grey, (0, 0, 0)) for k in done + ["pigtail_J1", "pigtail_J2", "plug_J1", "plug_J2"]] + [(s, "#8e6bbf" if m != "AL6061" else "#c9b98e", (0, 0, 0)) for n, s, m, kd, d in T.cradle_parts()]
    D.render(items, STEPS / "cradle.png", azim=-60, elev=26, title="Bench cradle: head on its two shoes and the front post, source deck 10.00 mm below the film", size=(1400, 880))
    D.render([(p.shape, p.color if p.color != "#111111" else "#444444", (0, 0, 0)) for p in Pp.values() if p.pn != "-"], STEPS / "overview_top.png", azim=-58, elev=30, title="Prototype head (RR-HD-X-000), rails at rest", size=(1400, 880))
    D.render([(p.shape, p.color if p.color != "#111111" else "#444444", (0, 0, 0)) for p in Pp.values() if p.pn != "-" and not p.name.startswith(("pigtail", "plug"))], STEPS / "overview_underside.png", azim=-58, elev=-30,
             title="Prototype head, underside: four 80 x 100 windows, cassettes, rails", size=(1400, 880))
    return 12


def steps_production():
    """Production assembly sequence (same order as the prototype, CNC frame, no fences) + dummy head view."""
    out = HERE / "production" / "assembly"
    out.mkdir(parents=True, exist_ok=True)
    Pp = {p.name: p for p in A.build("production")}
    col = lambda k: Pp[k].color if Pp[k].color != "#111111" else "#444444"
    grey = "#b8c0c4"
    heads = [k for k in Pp if k.startswith("hd_")]
    seq = [
        ("frame, shoes with G10 isolators and insulating washers, rear bridge", ["frame", "shoe_L", "shoe_R", "shoe_isolator_L", "shoe_isolator_R", "bridge"], {"shoe_L": (-40, 0, 0), "shoe_R": (-40, 0, 0), "bridge": (-60, 0, 0)}),
        ("side rails, guide pins, switches; guide rods, springs, stop pins", ["side_rail_L", "side_rail_R", "guide_pins_L", "guide_pins_R", "sw_side_L", "sw_side_R", "guide_rod_L", "guide_rod_R",
                                                                            "rod_spring_L", "rod_spring_R", "stop_pin_L", "stop_pin_R"], {"guide_rod_L": (45, 0, 0), "guide_rod_R": (45, 0, 0), "guide_pins_L": (0, 0, 35), "guide_pins_R": (0, 0, 35)}),
        ("lane kits (MJF rings, barrier, chimney insert) from above", [f"S{i}_{k}" for i in range(4) for k in ("floor_module", "spacer_lower", "barrier", "spacer_upper", "ref_module", "floor_carrier", "ref_carrier",
                                                                                                                "floor_sipm", "ref_sipm", "chimney_insert")], {}),
        ("spreader with heater, pads, rib gaskets; standoffs; board, cans, switches, cables", ["spreader", "rib_gaskets", "board_standoffs", "lid_standoffs", "pcb", "sw_front", "sw_front_saddle", "sw_lid", "sw_lid_saddle",
                                                                                            "boot_J1", "boot_J2", "holster_J1", "holster_J2", "thermal_cutout", "ntc", "desiccant", "vent"] + [f"S{i}_{k}" for i in range(4) for k in ("pad", "heater", "shield_can")]
         + [h for h in heads if not h.startswith("hd_lid")], {"pcb": (0, 0, 50), **{f"S{i}_shield_can": (0, 0, 70) for i in range(4)}}),
        ("lid (35 x M3 + bonded washers), blister, keeper, insulating jacket", ["lid", "lid_gasket", "lid_liner", "j1_blister", "keeper", "keeper_pin", "jacket_top", "jacket_front"] + [h for h in heads if h.startswith("hd_lid")], {"keeper": (-10, 0, 60), "keeper_pin": (-10, 0, 60)}),
        ("cassettes and leading rail", [f"S{i}_{k}" for i in range(4) for k in ("cassette", "film", "cassette_gasket")] + ["bail", "bail_block_C", "bail_block_L", "bail_block_R", "rail_bar", "bail_clip_L", "bail_clip_R"]
         + [f"rail_insert_{k}" for k in range(4)], {**{f"S{i}_{k}": (0, 0, -40) for i in range(4) for k in ("cassette", "film", "cassette_gasket")}, "rail_bar": (40, 0, 0), **{f"rail_insert_{k}": (60, 0, 0) for k in range(4)}}),
    ]
    done = []
    for n, (title, new, per) in enumerate(seq, start=1):
        items = [(Pp[k].shape, grey, (0, 0, 0)) for k in done if not k.startswith(("pigtail", "plug"))]
        default = (0, 0, 35) if n in (3, 4, 5) else (0, 0, 0)
        items += [(Pp[k].shape, col(k), per.get(k, default)) for k in new if k in Pp]
        elev = -30 if n == 6 else 30
        D.render(items, out / f"step_{n:02d}.png", azim=-58 if n != 1 else -125, elev=elev, title=f"Production step {n}: {title}", size=(1400, 880))
        done += new
    D.render([(p.shape, col(k), (0, 0, 0)) for k, p in Pp.items() if p.pn != "-"], out / "overview.png", azim=-58, elev=30, title="Production head RR-HD-P-000 (CNC 6061 frame)", size=(1400, 880))
    Pd, t = A.build_dummy(sum(p.mass() for p in A.build("prototype")))
    D.render([(p.shape, p.color if p.color != "#111111" else "#444444", (0, 0, 0)) for p in Pd if p.pn != "-" and p.name not in ("lid", "keeper", "keeper_pin", "j1_blister") and not p.name.startswith("hd_lid")],
             HERE / "aux" / "dummy_head_lid_off.png", azim=-58, elev=34, title=f"Dummy head RR-HD-D-000, lid off: steel ballast {t:.2f} mm per lane, plate on the 8 standoffs, resistor block", size=(1400, 880))
    return 8


if __name__ == "__main__":
    what = sys.argv[1:] or ["joints", "fab", "steps", "steps_production"]
    for w in what:
        print("==", w, {"joints": joints, "fab": fab, "steps": steps, "steps_production": steps_production}[w]())
