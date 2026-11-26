"""Part geometry of the detector head (both builds), in base_link coordinates, installed position.

Families: frame (printed halves / CNC frame), receiver (shoes, bridge, keeper), deck (spreader, lid, EMI fences, gaskets),
lane kit (module envelopes, rings, barrier, chimney insert, pads), window (cassette, film), rails (leading rail, side
zones, switches), electronics envelopes, cables.  Small fasteners are not modelled as solids; they are in the BOM.
"""
from __future__ import annotations

import math

import cadquery as cq

from . import hp as H
from .geom import V, bounds, box, cyl, cyl2, compound, cut_all, fuse_all, prism_xz, cached, round_z

LANES = {"L": (0, 1), "R": (2, 3), "P": (0, 1, 2, 3)}
SIDES = {"L": (1,), "R": (-1,), "P": (1, -1)}


def _yz_prism(pts, x0, x1):
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline([tuple(p) for p in pts]).close().extrude(x1 - x0).val()


# =============================================================================================== frame
INS_R = {False: 1.85, True: 1.025}     # M2.5 heat-set insert hole dia 3.7 (prototype, maker data PARTIAL) / M2.5 tap drill 2.05 (production)


def _frame(kind):
    """kind: 'L' (left printed half, tongue), 'R' (right printed half, groove), 'P' (one-piece production frame)."""
    y0 = {"L": H.JOINT_Y, "R": -H.YW, "P": -H.YW}[kind]
    y1 = {"L": H.YW, "R": H.JOINT_Y, "P": H.YW}[kind]
    body = box(H.XR, H.XF, y0, y1, H.Z_FB, H.Z_WALL_TOP)
    sel = {"L": "|Z and >Y", "R": "|Z and <Y", "P": "|Z"}[kind]
    body = round_z(body, 3.0, sel)                       # radiused external corners (wipe-down)
    cuts = [box(H.BAY_X0, H.BAY_X1, y0 - 1 if kind == "R" else max(y0 - 1, -H.BAY_HY), min(y1 + 1, H.BAY_HY) if kind != "L" else H.BAY_HY,
                H.Z_SPR0, 60)]
    if kind == "R":
        cuts[0] = box(H.BAY_X0, H.BAY_X1, -H.BAY_HY, 1, H.Z_SPR0, 60)
    elif kind == "L":
        cuts[0] = box(H.BAY_X0, H.BAY_X1, -1, H.BAY_HY, H.Z_SPR0, 60)
    else:
        cuts[0] = box(H.BAY_X0, H.BAY_X1, -H.BAY_HY, H.BAY_HY, H.Z_SPR0, 60)
    bya, byb = max(y0, -H.BAY_HY), min(y1, H.BAY_HY)
    cuts.append(box(H.LIP_GROOVE[2] - 0.05, H.LIP_GROOVE[3], bya, byb, H.LIP_GROOVE[0], H.LIP_GROOVE[1]))   # spreader front lip groove
    for i in LANES[kind]:
        yc = H.SEG_Y[i]
        cuts += [box(H.WIN_X0, H.WIN_X1, yc - H.ACT_Y / 2, yc + H.ACT_Y / 2, 0, H.Z_SEAT + 0.02),                # 80 x 100 aperture
                 box(H.CAV_X0, H.CAV_X1, yc - H.CAV_HY, yc + H.CAV_HY, H.Z_SEAT, H.Z_SPR0 + 0.02),               # module cavity
                 box(H.CHIM_X0, H.CHIM_STEP_X, yc - H.CHIM_HY, yc + H.CHIM_HY, H.CHIM_FLOOR_REAR, H.Z_SPR0 + 0.02),
                 box(H.CHIM_STEP_X - 0.02, H.CAV_X0 + 0.02, yc - H.CHIM_HY, yc + H.CHIM_HY, H.CHIM_FLOOR_FRONT, H.Z_SPR0 + 0.02)]
        a, b, hgt = H.CAS_LIP_Y
        for s in (1, -1):                                                                                          # cassette lip grooves, y sides
            ya, yb = yc + s * (H.ACT_Y / 2 + a - 0.1), yc + s * (H.ACT_Y / 2 + b + 0.1)
            cuts.append(box(H.CAS_X0 - 0.1, H.XF + 1, ya, yb, 0, H.Z_SEAT))
        a, b, hgt = H.CAS_LIP_X
        cuts.append(box(H.WIN_X0 - b - 0.1, H.WIN_X0 - a + 0.1, yc - H.CAS_HY, yc + H.CAS_HY, 0, H.FILM_Z + hgt + 0.2))
        cuts.append(box(H.WIN_X1 + a - 0.1, H.XF + 1, yc - H.CAS_HY, yc + H.CAS_HY, 0, H.FILM_Z + hgt + 0.2))
        for dx, dy in H.CAS_SCREW:                                                                                 # M2.5 inserts for the cassette
            x = H.WIN_X0 + dx if dx < 0 else H.WIN_X1 + dx
            cuts.append(cyl(INS_R[kind == 'P'], 5.5 if dx > 0 else 5.0, (x, yc + dy, H.Z_FB - 1)))
    for s in SIDES[kind]:
        ys = s * H.SHOE_Y
        # 45 deg relief under the upper side wall (printable overhang; clears the module top corner)
        yo, yi = s * (H.SEG_Y[0] + H.CAV_HY), s * H.BAY_HY
        cuts.append(_yz_prism([(yo, H.Z_SPR0 - abs(yo - yi)), (yo, H.Z_SPR0 + 0.02), (yi, H.Z_SPR0 + 0.02)], H.CAV_X0, H.CAV_X1))
        c_ = H.THEAD_POCKET_CLR
        cuts.append(box(H.XR - 1, H.THEAD_X1 + c_, ys - H.THEAD_HY - c_, ys + H.THEAD_HY + c_, H.SHOE_Z0 - c_, H.Z_SPR0 + 0.02))  # T-head pocket, air gap all round
        cuts.append(cyl(H.ROD_D / 2 + 0.15, H.ROD_BORE_DEPTH + 1, (H.XF + 1, ys, H.ROD_Z), (-1, 0, 0)))                                   # guide rod bore
        cuts.append(cyl(H.PIN_D / 2 + 0.05, H.Z_SPR0 + 1 - H.ROD_Z, (H.PIN_X, ys, H.ROD_Z)))                                               # stop / switch pin
        cuts.append(box(H.XF - 2.8, H.XF + 1, s * H.BAIL_Y - 2.1, s * H.BAIL_Y + 2.1, 0, H.BAIL_Z + 1.5))                                  # bail arm groove
        for x in H.ROD_PAD_X:                                                                                                             # M2.5 inserts on the rib
            cuts.append(cyl(INS_R[kind == 'P'], 5.2, (x, ys, H.Z_SPR0 - 5)))
        xs = (H.CAV_X0,) + tuple(v for x in H.ROD_PAD_X for v in (x - 4, x + 4)) + (H.CAV_X1,)
        for xa, xb in zip(xs[0::2], xs[1::2]):                                                                                           # rib top relief for the gasket strip
            cuts.append(box(xa, xb, ys - H.RIB_W / 2 - 0.02, ys + H.RIB_W / 2 + 0.02, H.RIB_TOP_Z, H.Z_SPR0 + 0.02))
        for yy in H.REAR_SCREW_Y:
            cuts.append(cyl(INS_R[kind == 'P'], 5.2, (H.REAR_SCREW_X, s * yy, H.Z_SPR0 - 5)))
        # side-zone guide slits and pin holes
        (x1, yg1), (x3, yg3), (x2, yg2) = H.GUIDE_PINS
        cuts += [box(H.XR - 1, 78.3, s * 163.8, s * (H.YW + 1), *H.SLIT_Z), box(H.XR - 1, 78.3, s * 142.2, s * 148.8, *H.SLIT_Z),
                 box(183.2, H.XF + 1, s * 162.6, s * (H.YW + 1), *H.SLIT_Z)]
        for xg, yg in H.GUIDE_PINS:
            cuts.append(cyl(1.6, 14.0, (xg, s * yg, 17.0)))
        # side switch pocket (body 7.0 deep, plunger to the rear) and lead channel up to the bay floor
        cuts.append(box(H.XR - 1, H.XR + H.SW["h"] + 0.2, s * (H.SW_SIDE["y"] - H.SW["l"] / 2 - 0.1), s * (H.SW_SIDE["y"] + H.SW["l"] / 2 + 0.1),
                        H.SW_SIDE["z"] - H.SW["t"] / 2 - 0.1, H.SW_SIDE["z"] + H.SW["t"] / 2 + 0.1))
        cuts.append(box(74.6, H.XR + H.SW["h"] + 0.2, s * 148.3, s * 150.2, H.SW_SIDE["z"] - 2.0, H.Z_SPR0 + 0.02))
        cuts.append(box(H.XR - 1, H.BAY_X0 + 1, ys - H.PORT_SLOT_HY, ys + H.PORT_SLOT_HY, H.PORT_SLOT_Z0, 60))                             # cable port U-slot
        for dy in (-6.0, 6.0):                                                                                                            # bail block inserts (outer blocks)
            cuts.append(cyl(INS_R[kind == 'P'], 5.2, (H.XF + 0.02, s * 130.0 + dy, 25.7), (-1, 0, 0)))
        cuts.append(box(H.BAY_X1 - 0.02, H.BAY_X1 + 0.6, ys - 8.0, ys + 8.0, H.Z_SPR1 + 0.2, H.Z_WALL_TOP + 1))                            # switch relief (front rail switch left, lid switch right)
    # centre rib: gasket relief (no screws possible in a 3.25 mm half rib), bail centre block inserts
    cy0, cy1 = max(y0, -H.RIB_W / 2 - 0.02), min(y1, H.RIB_W / 2 + 0.02)
    cuts.append(box(H.CAV_X0, H.CAV_X1, cy0, cy1, H.RIB_TOP_Z, H.Z_SPR0 + 0.02))
    for s in SIDES[kind]:
        cuts.append(cyl(INS_R[kind == 'P'], 5.2, (H.XF + 0.02, s * 10.0, 25.7), (-1, 0, 0)))
    if kind in ("R", "P"):
        cuts.append(cyl(3.0, 6, (H.XR - 1, H.VENT[1], H.VENT[2]), (1, 0, 0)))                                                              # M6 breather vent
    body = cut_all(body, cuts)
    # lid bosses (hard seats z 43.0 inside the gasket loop): prototype M3 heat-set insert, production tapped M3
    ya_, yb_ = {"L": (0.0, 999), "R": (-999, 0.0), "P": (-999, 999)}[kind]
    bosses = [(x, y) for x, y in lid_boss_xy() if ya_ < y < yb_]
    clip = box(60, H.BAY_X1 + 0.3, -H.BAY_HY - 0.3, H.BAY_HY + 0.3, 0, 60)
    body = fuse_all([body] + [cyl(H.LID_BOSS_R, H.Z_LID0 - H.LID_BOSS_Z0, (x, y, H.LID_BOSS_Z0)).intersect(clip) for x, y in bosses])
    hole = (H.INSERT_M3["hole_d"] / 2, H.INSERT_M3["depth"]) if kind != "P" else (1.25, 8.0)
    cuts = [cyl(hole[0], hole[1] + 1, (x, y, H.Z_LID0 - hole[1])) for x, y in bosses]
    # light-trap drain at each chimney rear floor: up 0.6 (under the chimney insert), across 3.75 in the floor, down to the underside
    d = H.DRAIN
    for i in LANES[kind]:
        yd = H.SEG_Y[i] + d["dy"] * (1 if H.SEG_Y[i] > 0 else -1)
        cuts += [cyl(d["d"] / 2, H.CHIM_FLOOR_REAR - d["z_ch"][0] + 0.02, (d["x_in"], yd, d["z_ch"][0])),
                 box(d["x_out"] - d["d"] / 2, d["x_in"] + d["d"] / 2, yd - d["d"] / 2, yd + d["d"] / 2, *d["z_ch"]),
                 cyl(d["d"] / 2, d["z_ch"][1] - H.Z_FB + 0.5, (d["x_out"], yd, H.Z_FB - 0.5))]
    body = cut_all(body, cuts)
    if kind == "P":
        return body.clean()
    # ---- split joint: U tongue (left) / groove (right), two 3 mm dowels, see joints.md
    t = H.TONGUE_T
    legs = [(71.2, 71.2 + t, 12.5, H.Z_SPR0), (71.2, 187.3, 12.5, 12.5 + t), (187.3 - t, 187.3, 12.5, H.Z_SPR0)]
    laps = [(H.XR, H.XR + H.LAP_T), (H.XF - H.LAP_T, H.XF)]          # ship-lap of the upper walls, overlapping the tongue legs from z 29
    dowels = [(184.0, 19.0), (75.8, 19.0)]
    if kind == "L":
        body = fuse_all([body] + [box(xa, xb, -H.TONGUE_H, 0.01, za, zb) for xa, xb, za, zb in legs] + [box(xa, xb, -H.LAP_H, 0.01, 29.0, H.Z_WALL_TOP) for xa, xb in laps])
        body = cut_all(body, [cyl(1.52, 3.2, (x, 3.2, z), (0, -1, 0)) for x, z in dowels])
    else:
        c = 0.15
        body = cut_all(body, [box(xa - c, xb + c, -H.TONGUE_H - 0.2, 1, za - c, zb + c) for xa, xb, za, zb in legs]
                       + [box(xa - (c if xa > 100 else 1), xb + (c if xa < 100 else 1), -H.LAP_H - 0.2, 1, 29.0 - c, 60) for xa, xb in laps]
                       + [cyl(1.52, 3.2, (x, 0.01, z), (0, -1, 0)) for x, z in dowels])
    return body.clean()


def frame(kind):
    return cached(f"frame_{kind}", lambda: _frame(kind))


# =============================================================================================== receiver
def shoe(side):
    y = side * H.SHOE_Y
    w = H.SHOE_W / 2
    xe = H.XR - H.THEAD_POCKET_CLR          # bar and shoulder stop 0.3 short of the frame rear face (FRAME isolation); only the T-head neck enters the pocket
    bar = cq.Workplane("XY").add(box(H.SHOE_X0, xe, y - w, y + w, H.SHOE_Z0, H.SHOE_Z1)).faces("<X").edges().chamfer(3.0).val()
    return fuse_all([bar, box(H.XSTOP, xe, y - H.SHOULDER_HY, y + H.SHOULDER_HY, H.SHOE_Z0, H.SHOE_Z1),
                     box(xe, H.THEAD_X1, y - H.THEAD_HY, y + H.THEAD_HY, H.SHOE_Z0, H.Z_SPR0 - 0.5)])


def shoe_isolator(side):
    y = side * H.SHOE_Y
    return box(H.XR, H.THEAD_X1, y - H.THEAD_HY, y + H.THEAD_HY, H.Z_SPR0 - 0.5, H.Z_SPR0)


def bridge():
    """Rear bridge: ties the two aluminium T-heads across the split and carries the keeper hinge."""
    x0, x1 = H.XR - H.BRIDGE_T - 0.3, H.XR - 0.3                 # 0.3 mm air gap to the frame rear face (FRAME isolation, prototype)
    parts = [box(x0, x1, -H.BRIDGE_HY + 0.2, H.BRIDGE_HY - 0.2, 16.5, 29.5), box(x0, x1, -20, 20, 29.4, 44.0)]
    for s in (1, -1):
        parts.append(box(66.4, x1, s * 15.6, s * 20.0, 44.0, 49.0))
    return cut_all(fuse_all(parts), [cyl(1.55, 42, (HINGE_X, -21, 46.6), (0, 1, 0))])


HINGE_X = 68.3


def keeper():
    plate = fuse_all([box(67.2, 108.0, -15.0, 15.0, 45.6, 47.6), box(102.5, 105.5, -15.0, 15.0, 47.5, 49.8),
                      cyl(2.1, 30.0, (HINGE_X, -15.0, 46.6), (0, 1, 0))])
    holes = [cyl(4.25, 5, (x, y, 44.0)) for x, y in lid_all_holes() if 67.2 < x < 108.0 and abs(y) < 15.0]   # clearance over the lid screw head
    return cut_all(plate, [cyl(1.55, 42, (HINGE_X, -21, 46.6), (0, 1, 0))] + holes)


def keeper_pin():
    return cyl(1.5, 40.0, (HINGE_X, -20.0, 46.6), (0, 1, 0))


# =============================================================================================== deck: spreader, lid, fences
def spreader_outline():
    """Closed outline (x, y) of the spreader plate, counter-clockwise, with the four pigtail notches."""
    pts = [(H.SPR_X1, -H.SPR_HY), (H.SPR_X1, H.SPR_HY), (H.SPR_X0, H.SPR_HY)]
    for yc in H.SEG_Y:
        pts += [(H.SPR_X0, yc + H.CHIM_HY), (H.SPR_NOTCH_X, yc + H.CHIM_HY), (H.SPR_NOTCH_X, yc - H.CHIM_HY), (H.SPR_X0, yc - H.CHIM_HY)]
    pts.append((H.SPR_X0, -H.SPR_HY))
    return pts


def board_holes():
    return [P_board(u, v) for u, v in H.ACQ["holes_uv"]]


def P_board(u, v):
    from mechanical.common import params as P
    return P.board_to_base(H.ACQ["origin"], u, v)


FENCE_FRONT_Y = (20.0, 64.0, 112.0, 152.0)     # 112 (was 108): screw head clear of the boss at 104.5
FENCE_SIDE_X = (100.0, 162.0)
COMB_FOOT_X1 = 80.0       # rear comb feet reach under the rear lid-standoff row (standoffs clamp the feet: bond points)
COMB_CHIM_MARGIN = 7.5    # feet stop 7.5 mm beyond each chimney notch (one-piece flat pattern: the liner side flanges develop into that space)


def spreader_holes():
    """(x, y, diameter, purpose) of every hole in the spreader plate."""
    h = [(x, y, 4.2, "board standoff M2.5 x 2.5 (clinch)") for x, y, _ in board_holes()]
    for x, y in H.LID_STANDOFFS:
        for s in ((1, -1) if y else (1,)):
            h.append((x, s * y, 3.2, "lid standoff M3 x 11, M3 CSK from below"))
    for s in (1, -1):
        h += [(x, s * H.SHOE_Y, 2.8, "M2.5 into rib insert, countersunk 90 deg x dia 5.2 on top (ISO 10642 head flush: under the board)") for x in H.ROD_PAD_X]
        h += [(H.REAR_SCREW_X, s * y, 2.8, "M2.5 into rear-zone insert (also rear comb foot)") for y in H.REAR_SCREW_Y]
        h += [(H.THEAD_SCREW_X, s * H.SHOE_Y + dy, 4.6, "M3 into T-head, insulating shoulder washer (prototype) / plain washer (production)") for dy in H.THEAD_SCREW_DY]
        h += [(183.0, s * y, 2.05, "tap M2.5: front fence foot") for y in FENCE_FRONT_Y]
        h += [(x, s * 166.9, 2.05, "tap M2.5: side fence foot") for x in FENCE_SIDE_X]
        h += [(H.PIN_X, s * H.SHOE_Y, 3.2, "rail stop/switch pin clearance"), (183.1, s * H.SHOE_Y + 10.5, 2.05, "tap M2.5: switch saddle"),
              (183.1, s * H.SHOE_Y - 10.5, 2.05, "tap M2.5: switch saddle")]
    return h


def spreader():
    def build():
        plate = cq.Workplane("XY", origin=(0, 0, H.Z_SPR0)).polyline(spreader_outline()).close().extrude(H.Z_SPR1 - H.Z_SPR0).val()
        return cut_all(plate, [cyl(d / 2, 4, (x, y, H.Z_SPR0 - 1)) for x, y, d, _ in spreader_holes()])
    return cached("spreader", build)


J1_OPENING = None


def j1_zone():
    """J1 landing zone (u 50..100, v 0..18) in base coordinates: x0, x1, y0, y1."""
    a, b = P_board(50, 0), P_board(100, 18)
    return (a[0], b[0], b[1], a[1])


def lid_holes():
    """Lid standoff positions (on the spreader)."""
    return [(x, s * y) for x, y in H.LID_STANDOFFS for s in ((1, -1) if y else (1,))]


def lid_boss_xy():
    """Lid boss positions on the frame walls (front line and both side lines)."""
    out = [(H.LID_BOSS_FRONT_X, s * y) for y in H.LID_BOSS_FRONT_Y for s in (1, -1)]
    out += [(x, s * H.LID_BOSS_SIDE_Y) for x in H.LID_BOSS_SIDE_X for s in (1, -1)]
    return out


def lid_all_holes():
    return lid_holes() + lid_boss_xy()


BLISTER = (74.5, None, 53.0, None)      # J1 blister rear / left edges extended so three rear-line lid screws pass through it (clamp + bond)


def lid_loop():
    """All lid fasteners ordered round the closed loop (for the pitch check)."""
    import math as _m
    pts = lid_all_holes()
    cx, cy = (H.XR + H.XF) / 2, 0.0
    return sorted(pts, key=lambda p: _m.atan2(p[1] - cy, p[0] - cx))


def lid():
    def build():
        i = H.LID_INSET
        pl = round_z(box(H.XR + i, H.XF - i, -H.YW + i, H.YW - i, H.Z_LID0, H.Z_LID1), 3.0)
        x0, x1, y0, y1 = j1_zone()
        cuts = [cyl(1.7, 4, (x, y, H.Z_LID0 - 1)) for x, y in lid_all_holes()] + [box(x0 - 0.5, x1 + 0.5, y0 - 0.5, y1 + 0.5, 40, 50)]
        return cut_all(pl, cuts)
    return cached("lid", build)


def blister_rect():
    x0, x1, y0, y1 = j1_zone()
    return (BLISTER[0], x1 + 5.5, BLISTER[2], y1 + 5.5)


def j1_blister():
    a, b, c, d = blister_rect()
    pl = box(a, b, c, d, H.Z_LID1, H.Z_LID1 + 1.0)
    return pl.cut(compound([cyl(1.7, 3, (x, y, H.Z_LID1 - 1)) for x, y in lid_all_holes() if a < x < b and c < y < d]))


def lid_gasket():
    g = box(H.XR + 0.5, H.XF - 0.5, -H.YW + 0.5, H.YW - 0.5, H.Z_WALL_TOP, H.Z_LID0).cut(
        box(H.BAY_X0 - 0.3, H.BAY_X1 + 0.3, -H.BAY_HY - 0.3, H.BAY_HY + 0.3, 40, 50))
    for s in (1, -1):          # the grommets close the two port slots
        g = g.cut(box(H.XR - 1, H.BAY_X0 + 1, s * H.SHOE_Y - H.PORT_SLOT_HY, s * H.SHOE_Y + H.PORT_SLOT_HY, 40, 50))
    return g


FENCE_FRONT_X = 180.0     # inner face of the front fence wall (board front edge 179.2)
FENCE_SIDE_Y = 163.8      # inner face of the side fence walls (board edge 163.0)
FENCE_TOP = H.Z_LID0 - 0.7
FENCE_REAR_X = H.BAY_X0 + 0.1


def fence_front():
    t, x = H.FENCE_T, FENCE_FRONT_X
    hy = FENCE_SIDE_Y + t
    s = fuse_all([box(x, x + t, -hy, hy, H.Z_SPR1, FENCE_TOP), box(x, H.BAY_X1 - 0.1, -hy, hy, H.Z_SPR1, H.Z_SPR1 + t),
                  box(x - 2.5, x + t, -hy, hy, FENCE_TOP - t, FENCE_TOP)])
    cuts = [cyl(1.7, 3, (xx, yy, H.Z_SPR1 - 1)) for xx, yy in lid_holes() if xx > 150]      # standoff clamps the foot
    for sgn in (1, -1):                      # openings in the foot for the rail-switch saddle stations and the pin
        cuts.append(box(x + t + 0.01, H.BAY_X1, sgn * H.SHOE_Y - 13.5, sgn * H.SHOE_Y + 13.5, H.Z_SPR1 - 1, H.Z_SPR1 + 2))
    return cut_all(s, cuts)


def fence_side(side):
    t, y = H.FENCE_T, FENCE_SIDE_Y
    xa, xb = 79.2, FENCE_FRONT_X - 2.7
    s = fuse_all([box(xa, xb, y, y + t, H.Z_SPR1, FENCE_TOP), box(xa, xb, y, H.SPR_HY - 0.1, H.Z_SPR1, H.Z_SPR1 + t),
                  box(xa, xb, y - 2.5, y + t, FENCE_TOP - t, FENCE_TOP)])
    s = cut_all(s, [cyl(1.7, 3, (xx, yy, H.Z_SPR1 - 1)) for xx, yy in lid_holes() if abs(yy) > 160])
    return s if side == 1 else s.mirror("XZ")


def fence_rear():
    """Rear comb: bay rear wall + feet on the spreader tabs + U-shaped liners hanging into the four chimneys."""
    t, x = H.FENCE_T, FENCE_REAR_X
    hy = FENCE_SIDE_Y + t
    parts = [box(x, x + t, -hy, hy, H.Z_SPR1, FENCE_TOP), box(x, x + 2.0, -hy, hy, FENCE_TOP - t, FENCE_TOP)]
    edges = [-hy] + [v for yc in sorted(H.SEG_Y) for v in (yc - H.CHIM_HY - COMB_CHIM_MARGIN, yc + H.CHIM_HY + COMB_CHIM_MARGIN)] + [hy]
    for ya, yb in zip(edges[0::2], edges[1::2]):                              # feet between the chimneys
        parts.append(box(x, COMB_FOOT_X1, ya, yb, H.Z_SPR1, H.Z_SPR1 + t))
    for yc in H.SEG_Y:                                                        # chimney liners (rear + two sides)
        parts.append(box(x, x + t, yc - H.CHIM_HY + 0.2, yc + H.CHIM_HY - 0.2, H.CHIM_FLOOR_REAR + 0.5, H.Z_SPR1 + 0.01))
        for s in (1, -1):
            ya = yc + s * (H.CHIM_HY - 0.2)
            parts.append(box(x, H.CAV_X0 - 0.5, ya - s * t, ya, H.CHIM_FLOOR_REAR + 0.5, H.Z_SPR0 - 0.3))
    s = fuse_all(parts)
    cuts = [box(x - 1, x + 3, sg * H.SHOE_Y - H.PORT_SLOT_HY, sg * H.SHOE_Y + H.PORT_SLOT_HY, H.PORT_SLOT_Z0, 50) for sg in (1, -1)]
    cuts += [cyl(2.5, 4, (x - 1, H.VENT[1], H.VENT[2]), (1, 0, 0))]
    cuts += [cyl(1.7, 3, (xx, yy, H.Z_SPR1 - 1)) for xx, yy in lid_holes() if xx < 90]                     # standoffs clamp the feet (where there is one)
    cuts += [cyl(1.45, 3, (H.REAR_SCREW_X, sg * yy, H.Z_SPR1 - 1)) for sg in (1, -1) for yy in H.REAR_SCREW_Y]  # rear spreader screws clamp the feet
    cuts += [cyl(3.3, 3, (H.THEAD_SCREW_X, sg * H.SHOE_Y + dy, H.Z_SPR1 - 1)) for sg in (1, -1) for dy in H.THEAD_SCREW_DY]   # insulating washer clearance
    a = bounds(thermal_cutout())
    cuts.append(box(a[0] - 0.3, a[3] + 0.3, a[1] - 0.3, a[4] + 0.3, H.Z_SPR1 - 1, H.Z_SPR1 + 1))                      # window: cut-out on the spreader
    return cut_all(s, cuts)


def fence_gaskets():
    """Conductive fabric-over-foam strips on the fence top flanges (compressed 1.0 -> 0.7)."""
    t = H.FENCE_T
    hy = FENCE_SIDE_Y + t
    rear = box(FENCE_REAR_X, FENCE_REAR_X + 2.0, -hy, hy, FENCE_TOP, H.Z_LID0)
    for s in (1, -1):
        rear = rear.cut(box(70, 80, s * H.SHOE_Y - H.PORT_SLOT_HY, s * H.SHOE_Y + H.PORT_SLOT_HY, 40, 50))
    out = [box(FENCE_FRONT_X - 2.3, FENCE_FRONT_X + t, -hy, hy, FENCE_TOP, H.Z_LID0), rear]
    for s in (1, -1):
        ya, yb = sorted((s * (FENCE_SIDE_Y - 2.3), s * (FENCE_SIDE_Y + t)))
        out.append(box(FENCE_REAR_X + 2.3, FENCE_FRONT_X - 2.8, ya, yb, FENCE_TOP, H.Z_LID0))
    return compound(out)


def standoff_on_foot(x, y):
    """True where a lid standoff stands on an EMI fence foot (prototype)."""
    if x < 90:
        return all(abs(y - yc) >= H.CHIM_HY + COMB_CHIM_MARGIN + H.LID_STANDOFF_D / 2 for yc in H.SEG_Y)
    return True


def lid_standoffs(prototype=False, which=None):
    """Prototype: 10.5 mm where the standoff stands on (and clamps) a fence foot, 11 mm elsewhere. Production: 11 mm on the spreader.
    which: None (all), 'foot' or 'spreader'."""
    out = []
    for x, y in lid_holes():
        foot = prototype and standoff_on_foot(x, y)
        if which == "foot" and not foot or which == "spreader" and foot:
            continue
        z0 = H.Z_SPR1 + (H.FENCE_T if foot else 0.0)
        out.append(cyl(H.LID_STANDOFF_D / 2, H.Z_LID0 - z0, (x, y, z0)))
    return compound(out)


def board_standoffs():
    return compound([cyl(2.25, H.STANDOFF_BOARD_H, (x, y, H.Z_SPR1)) for x, y, _ in board_holes()])


def rib_gaskets():
    """Black closed-cell strips on the spreader underside along the three seam ribs (1.0 -> 0.6 mm)."""
    out = []
    for yr in (H.SHOE_Y, -H.SHOE_Y):
        xs = (H.CAV_X0,) + tuple(v for x in H.ROD_PAD_X for v in (x - 4, x + 4)) + (H.CAV_X1,)
        out += [box(xa + 0.3, xb - 0.3, yr - 2.7, yr + 2.7, H.RIB_TOP_Z, H.Z_SPR0) for xa, xb in zip(xs[0::2], xs[1::2])]
    out.append(box(H.CAV_X0 + 0.3, H.CAV_X1 - 0.3, -2.7, 2.7, H.RIB_TOP_Z, H.Z_SPR0))
    return compound(out)


# =============================================================================================== lane kit
def lane_parts(i):
    """Returns dict name -> (shape, material, kind, desc). Envelope items are the OEM assembly (dimensions UNKNOWN)."""
    yc = H.SEG_Y[i]
    hx0, hx1, hy = H.WIN_X0, H.WIN_X1, H.ACT_Y / 2
    S = H.STACK
    out = {}
    out["floor_module"] = (box(hx0, hx1, yc - hy, yc + hy, S["floor_screen"][0], S["floor_guide"][1]), "PMMA", "envelope", "OEM floor assembly envelope (screen + 5 mm guide)")
    out["ref_module"] = (box(hx0, hx1, yc - hy, yc + hy, S["ref_tile"][0], S["ref_guide"][1]), "PMMA", "envelope", "OEM reference assembly envelope (tile + 5 mm guide)")
    ring = lambda z0, z1: box(H.CAV_X0 + 0.1, H.CAV_X1 - 0.1, yc - H.CAV_HY + 0.1, yc + H.CAV_HY - 0.1, z0, z1).cut(
        box(hx0 + 2.0, hx1 - 2.0, yc - hy + 2.0, yc + hy - 2.0, z0 - 1, z1 + 1))
    out["spacer_lower"] = (ring(S["floor_guide"][1], S["barrier"][0]), "PA-CF", "printed", "lane spacer ring 1.75 mm (floor guide to barrier)")
    out["barrier"] = (box(H.CAV_X0 + 0.1, H.CAV_X1 - 0.1, yc - H.CAV_HY + 0.1, yc + H.CAV_HY - 0.1, *S["barrier"]), "PA-CF", "printed", "opaque barrier plate 2 mm with foam edge")
    out["spacer_upper"] = (ring(S["barrier"][1], S["ref_tile"][0]), "PA-CF", "printed", "lane spacer ring 3 mm (barrier to reference tile)")
    out["pad"] = (box(hx0, hx1, yc - hy, yc + hy, H.Z_REF_TOP, H.Z_REF_TOP + H.PAD_T), "SIL-FOAM", "purchased", "retention / thermal pad 1.5 mm free, 1.2 mm installed")
    out["heater"] = (box(hx0 + 2, hx1 - 2, yc - hy + 2, yc + hy - 2, H.Z_SPR0 - H.HEATER_T, H.Z_SPR0), "PI", "purchased", "polyimide heater zone 7.5 W, bonded under the spreader")
    for nm, zc in (("floor", (S["floor_guide"][0] + S["floor_guide"][1]) / 2), ("ref", (S["ref_guide"][0] + S["ref_guide"][1]) / 2)):
        c, sp = H.CARRIER, H.SIPM
        out[f"{nm}_carrier"] = (box(c["x"][0], c["x"][1], yc - c["hy"], yc + c["hy"], zc - c["h"] / 2, zc + c["h"] / 2), "FR4", "envelope", "SiPM carrier envelope (OEM)")
        out[f"{nm}_sipm"] = (box(sp["x"][0], sp["x"][1], yc - sp["hy"], yc + sp["hy"], zc - sp["h"] / 2, zc + sp["h"] / 2), "FR4", "envelope", "SiPM envelope (OEM)")
    # chimney insert: retains both carriers with foam-faced fingers, light shelf at barrier height, coax channel
    xb0, xb1 = FENCE_REAR_X + H.FENCE_T + 0.2, 76.0
    w = H.CHIM_HY - 0.2 - H.FENCE_T - 0.2
    body = [box(xb0, xb1, yc - w, yc + w, H.CHIM_FLOOR_REAR + 0.6, H.Z_SPR0 - 0.4)]
    for s in (1, -1):
        ya, yb = sorted((yc + s * 5.2, yc + s * w))
        body.append(box(xb1 - 0.01, H.CARRIER["x"][0] - 0.2, ya, yb, H.CHIM_FLOOR_FRONT + 0.3, H.Z_SPR0 - 0.4))
    body.append(box(xb1 - 0.01, H.CAV_X0 - 0.1, yc - 5.3, yc + 5.3, S["barrier"][0] + 0.2, S["barrier"][1] - 0.2))
    ins = cut_all(fuse_all(body), [box(xb1 - 2.5, H.CARRIER["x"][0] + 0.2, yc - 2.5, yc + 2.5, S["barrier"][0] - 1, S["barrier"][1] + 1),
                                   box(xb1 - 2.5, xb1 + 0.01, yc - 4.0, yc + 4.0, H.CHIM_FLOOR_REAR, 60)])
    out["chimney_insert"] = (ins, "PA-CF", "printed", "chimney insert: carrier retention fingers, floor/reference light shelf, coax channel")
    return out


# =============================================================================================== window cassette
def cassette(i):
    def build():
        yc = 0.0
        hx0, hx1, hy = H.WIN_X0, H.WIN_X1, H.ACT_Y / 2
        fr = box(H.CAS_X0, H.CAS_X1, yc - H.CAS_HY, yc + H.CAS_HY, H.CAS_Z0, H.FILM_Z).cut(box(hx0, hx1, -hy, hy, 0, 20))
        add = [box(H.ROW_X + dx - H.CAS_WEB_W / 2, H.ROW_X + dx + H.CAS_WEB_W / 2, -hy - 0.01, hy + 0.01, H.CAS_Z0, H.FILM_Z) for dx in H.CAS_WEB_X]
        a, b, h = H.CAS_LIP_Y
        ax, bx, hxx = H.CAS_LIP_X
        for s in (1, -1):
            ya, yb = sorted((s * (hy + a), s * (hy + b)))
            add.append(box(hx0 - bx, hx1 + bx, ya, yb, H.FILM_Z - 0.01, H.FILM_Z + h))
        add += [box(hx0 - bx, hx0 - ax, -hy - b, hy + b, H.FILM_Z - 0.01, H.FILM_Z + hxx), box(hx1 + ax, hx1 + bx, -hy - b, hy + b, H.FILM_Z - 0.01, H.FILM_Z + hxx)]
        holes = []
        for dx, dy in H.CAS_SCREW:                      # hard seat bosses: cassette top to frame underside = 0.50 (film plane datum)
            x = hx0 + dx if dx < 0 else hx1 + dx
            add.append(cyl(2.6, H.Z_FB - H.FILM_Z + 0.01, (x, dy, H.FILM_Z - 0.01)))
            holes.append(cyl(1.45, 5, (x, dy, H.CAS_Z0 - 1)))
        s = fuse_all([fr] + add)
        return cut_all(s, holes)
    return cached("cassette", build).translate(V(0, H.SEG_Y[i], 0))


def film(i):
    yc, hy = H.SEG_Y[i], H.ACT_Y / 2
    f = box(H.WIN_X0 - 5.0, H.WIN_X1 + 5.0, yc - hy - 0.9, yc + hy + 0.9, H.FILM_Z, H.FILM_Z + 0.05)
    for dx, dy in H.CAS_SCREW:
        x = H.WIN_X0 + dx if dx < 0 else H.WIN_X1 + dx
        f = f.cut(cyl(3.0, 3, (x, yc + dy, 9)))
    return f


def cassette_gasket(i):
    yc, hy = H.SEG_Y[i], H.ACT_Y / 2
    g = box(H.WIN_X0 - 5.7, H.WIN_X1 + 5.7, yc - hy - 1.0, yc + hy + 1.0, H.FILM_Z + 0.05, H.Z_FB).cut(box(H.WIN_X0, H.WIN_X1, yc - hy, yc + hy, 0, 20))
    for dx, dy in H.CAS_SCREW:
        x = H.WIN_X0 + dx if dx < 0 else H.WIN_X1 + dx
        g = g.cut(cyl(3.0, 3, (x, yc + dy, 9)))
    return g


def transport_cover(side):
    """Clip-on transport / protection cover, one per head half (two windows each)."""
    def build():
        x0, x1 = H.XSTOP - 2.2, H.XF + H.RAIL_GAP + H.BAR_T + H.INS_T + 2.5      # rear wall behind the x-stop shoulders and the wing returns
        y1 = 177.5
        tray = box(x0, x1, 0.2, y1, 1.5, 4.0)
        walls = [box(x0, x0 + 2, 0.2, y1, 4.0, 9.0), box(x1 - 2, x1, 0.2, y1, 4.0, 24.6), box(x0, x1, y1 - 2, y1, 4.0, 9.0),
                 box(x1 - 6.5, x1, 0.2, y1, 23.4, 24.6),                                  # front lip resting over the rail insert top
                 box(x0, x0 + 2, H.SHOE_Y - 12, H.SHOE_Y - 8.8, 4.0, 32.0), box(x0, x0 + 2, H.SHOE_Y + 8.8, H.SHOE_Y + 12, 4.0, 32.0),
                 box(x0, x0 + 2, H.SHOE_Y - 12, H.SHOE_Y + 12, 30.6, 32.0)]                # snap bridge over the shoe top, behind the shoulder
        # four soft-faced rests that touch only the cassette borders (never the film)
        rests = [box(x, x + 4, y - 2, y + 2, 4.0, H.CAS_Z0 - 0.3) for x in (75.5, 183.5) for y in (23.75, 63.75, 111.25, 151.25)]
        return fuse_all([tray] + walls + rests)
    s = cached("transport_cover", build)
    return s if side == 1 else s.mirror("XZ")


# =============================================================================================== rails: front zone
def rail_x(travel=0.0):
    return H.XF + H.RAIL_GAP - travel


def rail_bar(travel=0.0):
    x = rail_x(travel)
    return box(x, x + H.BAR_T, -H.BAR_HY, H.BAR_HY, H.BAR_Z0, H.BAR_Z1)


def insert_segment(k, projection=3.0, travel=0.0):
    x = rail_x(travel) + H.BAR_T
    zb = H.rail_underside(projection)
    w = 2 * H.BAR_HY / 4
    y0 = -H.BAR_HY + k * w
    s = box(x, x + H.INS_T, y0 + 0.1, y0 + w - 0.1, zb, zb + H.INS_H)
    zs = zb + H.INS_HOLE_OFFSETS[projection]
    return cut_all(s, [cyl(1.7, 6, (x - 1, y0 + f * w, zs), (1, 0, 0)) for f in (0.2, 0.8)])


def guide_rod(side, travel=0.0):
    x1 = rail_x(travel)
    x0 = H.XF - H.ROD_ENGAGE - travel
    y = side * H.ROD_Y
    r = cyl(H.ROD_D / 2, x1 - x0, (x0, y, H.ROD_Z), (1, 0, 0))
    px = H.PIN_X - travel
    notch = prism_xz([(px - H.PIN_D / 2 - 0.05, H.ROD_Z + 3), (px - H.PIN_D / 2 - 0.05, H.ROD_Z + H.ROD_D / 2 - H.CAM_RISE),
                      (px + H.PIN_D / 2 + 0.05, H.ROD_Z + H.ROD_D / 2 - H.CAM_RISE), (px + H.PIN_D / 2 + 0.05 + H.CAM_RAMP, H.ROD_Z + H.ROD_D / 2 + 0.01),
                      (px + H.PIN_D / 2 + 3, H.ROD_Z + 3)], y - 3, y + 3)
    return r.cut(notch)


def rod_spring(side):
    return cyl(1.8, H.ROD_BORE_DEPTH - H.ROD_ENGAGE - 0.4, (H.XF - H.ROD_BORE_DEPTH + 0.2, side * H.ROD_Y, H.ROD_Z), (1, 0, 0))


def stop_pin(side):
    z0 = H.ROD_Z + H.ROD_D / 2 - H.CAM_RISE
    z1 = H.Z_SPR1 + 0.3 if side == 1 else H.Z_SPR0 - 0.2
    return cyl(H.PIN_D / 2, z1 - z0, (H.PIN_X, side * H.ROD_Y, z0))


def bail_angle(travel=0.0):
    tip_x = rail_x(travel) - H.BAIL_D / 2
    return math.asin((tip_x - H.BAIL_X) / H.BAIL_L)


def bail(travel=0.0):
    th = bail_angle(travel)
    tx, tz = H.BAIL_X + H.BAIL_L * math.sin(th), H.BAIL_Z - H.BAIL_L * math.cos(th)
    r = H.BAIL_D / 2
    parts = [cyl(r, 2 * H.BAIL_Y + 2 * r, (H.BAIL_X, -H.BAIL_Y - r, H.BAIL_Z), (0, 1, 0))]
    for s in (1, -1):
        parts.append(cyl2(r, (H.BAIL_X, s * H.BAIL_Y, H.BAIL_Z), (tx, s * H.BAIL_Y, tz)))
    return fuse_all(parts), (tx, tz)


def bail_clip(side, travel=0.0):
    x = rail_x(travel)
    y = side * H.BAIL_Y
    return compound([box(x - 2.6, x, y + s * 1.45, y + s * 1.95, 11.8, H.BAR_Z1 - 0.5) for s in (1, -1)])


BLOCK_T = 4.0


def bail_block(y):
    s = box(H.XF, H.XF + BLOCK_T, y - 15.0, y + 15.0, 23.2, 32.0)
    return s.cut(cyl(H.BAIL_D / 2 + 0.15, 32, (H.BAIL_X, y - 16, H.BAIL_Z), (0, 1, 0)))


def switch_body(center, axis_len, axis_thk, axis_h, plunger_dir, pressed=0.0):
    """D2HW envelope: body l x t x h with the plunger (free length 1.5) along +plunger_dir from the body face."""
    sw = H.SW
    half = {"l": sw["l"] / 2, "t": sw["t"] / 2, "h": sw["h"] / 2}
    ext = [0.0, 0.0, 0.0]
    for ax, key in ((axis_len, "l"), (axis_thk, "t"), (axis_h, "h")):
        ext["xyz".index(ax)] = half[key]
    b = box(center[0] - ext[0], center[0] + ext[0], center[1] - ext[1], center[1] + ext[1], center[2] - ext[2], center[2] + ext[2])
    d = V(*plunger_dir)
    base = V(*center) + d * half["h"]
    return b, cyl(0.9, sw["plunger"] - pressed, (base.x, base.y, base.z), plunger_dir)


def front_switch():
    c = (183.25, H.SHOE_Y, 37.3)             # body z 33.8..40.8, plunger down onto the pin
    return switch_body(c, "y", "x", "z", (0, 0, -1), pressed=0.2)


def switch_saddle(yc, z0, z1, x0=180.75, x1=185.5):
    """Printed saddle clamping a switch by its ends; two M2.5 screws into the spreader."""
    l = H.SW["l"] / 2
    return fuse_all([box(x0, x1, yc + s * (l + 0.15) if s > 0 else yc - 13.3, yc + 13.3 if s > 0 else yc - l - 0.15, H.Z_SPR1, z1) for s in (1, -1)]
                    + [box(x0, x1, yc - 13.3, yc + 13.3, z1 - 0.01, z1 + 1.2)])


def lid_switch():
    c = (183.25, H.LID_SW[1], 39.4)          # body z 35.9..42.9, plunger up, pressed 1.4 mm by the lid
    return switch_body(c, "y", "x", "z", (0, 0, 1), pressed=1.4)


# =============================================================================================== rails: side zones
def side_rail(side, travel=0.0, projection=3.0):
    """L-shaped stainless strip (side strip + wing-tip return + three guide tabs). travel = slide along the 45 deg guide.
    projection 3 mm -> RR-HD-S-431/432 (strip 13 mm tall), 5 mm -> RR-HD-S-433/434 (15 mm tall, same tabs and holes)."""
    d = travel / math.sqrt(2)
    t = H.SIDE_T
    z0 = H.rail_underside(projection)
    xr1, xr0 = H.RET_X1, H.RET_X1 - t
    parts = [box(xr0, 187.6, H.SIDE_Y0, H.SIDE_Y0 + t, z0, H.SIDE_Z1), box(xr0, xr1, H.RET_Y0, H.SIDE_Y0 + t, z0, H.SIDE_Z1)]
    zt = (H.SLIT_Z[0] + 0.3, H.SLIT_Z[0] + 0.3 + t)
    (x1, y1), (x3, y3), (x2, y2) = H.GUIDE_PINS
    parts += [box(xr0, xr1, 165.0, 172.0, H.SIDE_Z1 - 0.01, zt[1]), box(xr1 - 0.01, 77.0, 165.0, 172.0, *zt),
              box(xr0, xr1, 143.4, 148.0, H.SIDE_Z1 - 0.01, zt[1]), box(xr1 - 0.01, 77.0, 143.4, 148.0, *zt),
              box(183.7, 187.3, H.SIDE_Y0, H.SIDE_Y0 + t, H.SIDE_Z1 - 0.01, zt[1]), box(183.7, 187.3, 164.0, H.SIDE_Y0 + 0.01, *zt)]
    s = cut_all(fuse_all(parts), [cyl(2.5, 3, (xg, yg, zt[0] - 1)) for xg, yg in H.GUIDE_PINS])
    s = s.translate(V(d, -d, 0))
    return s if side == 1 else s.mirror("XZ")


def guide_pins(side):
    return compound([cyl(1.5, 13.0, (x, side * y, 17.0)) for x, y in H.GUIDE_PINS])


def side_switch(side):
    c = (H.XR + 0.1 + H.SW["h"] / 2, side * H.SW_SIDE["y"], H.SW_SIDE["z"])
    return switch_body(c, "y", "z", "x", (-1, 0, 0))


# =============================================================================================== electronics envelopes
def pcb():
    ox, oy, oz = H.ACQ["origin"]
    w, h = H.ACQ["outline"]
    b = box(ox, ox + h, oy - w, oy, oz, oz + H.ACQ["thickness"])
    return b.cut(compound([cyl(H.ACQ["hole_d"] / 2, 4, (x, y, oz - 1)) for x, y, _ in board_holes()]))


def pcb_keepouts():
    ox, oy, oz = H.ACQ["origin"]
    w, h = H.ACQ["outline"]
    top = box(ox, ox + h, oy - w, oy, oz + H.ACQ["thickness"], oz + H.ACQ["thickness"] + H.ACQ["max_top"])
    bot = box(ox, ox + h, oy - w, oy, oz - H.ACQ["max_bottom"], oz)
    x0, x1, y0, y1 = j1_zone()
    j1 = box(x0, x1, y0, y1, oz + H.ACQ["thickness"], oz + H.ACQ["thickness"] + 8.3)
    return top, bot, j1


def shield_can(i=None):
    """RR-HEAD-SHLD-A lane shield can 36.0 x 32.0 x 5.0, 0.2 mm wall (drawing owed to head electronics)."""
    w = 0.2
    can = box(0, 32.0, -18.0, 18.0, 0, 5.0).cut(box(w, 32.0 - w, -18.0 + w, 18.0 - w, -1, 5.0 - w))
    can = can.cut(compound([box(-1, 1, s * 6.0 - 1.0, s * 6.0 + 1.0, -1, 1.2) for s in (1, -1)]))      # two 2 mm mouse holes, rear wall
    if i is None:
        return can
    oz = H.ACQ["origin"][2] + H.ACQ["thickness"]
    return can.translate(V(H.ACQ["origin"][0] + 5.5, H.SEG_Y[i], oz))


def grommet(name):
    s = 1 if name == "J1" else -1
    y = s * H.SHOE_Y
    g = fuse_all([box(H.XR + 0.05, H.BAY_X0 - 0.05, y - H.PORT_SLOT_HY + 0.05, y + H.PORT_SLOT_HY - 0.05, H.PORT_SLOT_Z0, H.Z_LID0),
                  box(H.XR - 1.5, H.XR + 0.051, y - 7.5, y + 7.5, H.PORT_SLOT_Z0 - 2, H.Z_LID0)])
    g = g.cut(box(H.XR, H.XR + 0.06, y - 8, y + 8, 30, H.PORT_SLOT_Z0)).cut(box(H.XR, H.XR + 0.06, y + H.PORT_SLOT_HY - 0.05, y + 8, 30, 50)).cut(box(H.XR, H.XR + 0.06, y - 8, y - H.PORT_SLOT_HY + 0.05, 30, 50))
    return g.cut(cyl(H.CABLE_D[name] / 2 - 0.15, 12, (H.XR - 3, y, H.PORT[name][2]), (1, 0, 0)))


def pigtail(name):
    """Cable from the internal clamp through the port, rearward and up 150 mm, with the plug envelope at the end."""
    from mechanical.common.purchased import library as L
    s = 1 if name == "J1" else -1
    y = s * H.SHOE_Y
    z = H.PORT[name][2]
    r = H.CABLE_D[name] / 2
    e = L.env("j1_receptacle" if name == "J1" else "j2_receptacle")
    p0, p1 = (76.0, y, z), (H.XR - 12.0, y, z)
    d = V(-0.55, -0.25 * s, 0.80).normalized()
    p2 = (p1[0] + d.x * 120, p1[1] + d.y * 120, p1[2] + d.z * 120)
    cable = fuse_all([cyl2(r, p0, p1), cq.Solid.makeSphere(r, V(*p1)), cyl2(r, p1, p2)])
    plug = cyl(e["plug_nut_d"] / 2, e["plug_l"], p2, (d.x, d.y, d.z))
    return cable, plug


def vent():
    return fuse_all([cyl(4.5, 2.5, (H.XR - 2.5, H.VENT[1], H.VENT[2]), (1, 0, 0)), cyl(2.9, 2.6, (H.XR - 0.01, H.VENT[1], H.VENT[2]), (1, 0, 0))])


DESICCANT_Y = ((9.8, 31.2), (45.0, 66.8))


def desiccant():
    """Four 0.5-0.6 g silica pouches in the front strip between the lid bosses (above the fence-foot screws), 3.0 cm3 in total."""
    return compound([box(181.0, 185.4, s * a, s * b, H.Z_SPR1 + 2.5, H.Z_SPR1 + 9.5) for a, b in DESICCANT_Y for s in (1, -1)])


def ntc():
    """Heater-control NTC (10 k, epoxy bead in a ring lug) screwed / bonded to the spreader top beside the cut-out."""
    return box(80.4, 82.6, 107.8, 110.2, H.Z_SPR1, H.Z_SPR1 + 1.6)


def thermal_cutout():
    return box(77.0, 81.6, H.SHOE_Y + 28.0, H.SHOE_Y + 34.5, H.Z_SPR1, H.Z_SPR1 + 3.4)      # on the spreader through a window in the comb foot


LINER_T = 0.5


def lid_liner():
    """0.5 mm closed-cell liner under the lid, inside the fence line (the 0.9 mm cover clearance allows no more)."""
    return box(84.0, FENCE_FRONT_X - 3.0, -FENCE_SIDE_Y + 3.0, FENCE_SIDE_Y - 3.0, H.Z_LID0 - LINER_T, H.Z_LID0).cut(
        box(j1_zone()[0] - 1, j1_zone()[1] + 1, j1_zone()[2] - 1, j1_zone()[3] + 1, 30, 50))


# =============================================================================================== dummy head, cradle, gauges
def ballast(i, t):
    """Steel ballast / follower plate that replaces the optical stack of one lane in the dummy head."""
    yc = H.SEG_Y[i]
    pl = box(H.CAV_X0 + 0.2, H.CAV_X1 - 0.2, yc - H.CAV_HY + 0.2, yc + H.CAV_HY - 0.2, H.Z_SEAT, H.Z_SEAT + t)
    holes = [cyl(4.0, t + 2, (H.ROW_X + dx, yc + dy, H.Z_SEAT - 1)) for dx, dy in ((0, 0), (-40, -30), (-40, 30), (40, -30), (40, 30))]
    return cut_all(pl, holes)


def dummy_spacer(i, t):
    """Printed spacer block that fills the lane above the ballast so the standard pad clamps it."""
    yc = H.SEG_Y[i]
    z0 = H.Z_SEAT + t
    s = box(H.CAV_X0 + 0.3, H.CAV_X1 - 0.3, yc - H.CAV_HY + 0.3, yc + H.CAV_HY - 0.3, z0, H.Z_REF_TOP)
    return s.cut(box(H.CAV_X0 + 3.3, H.CAV_X1 - 3.3, yc - H.CAV_HY + 3.3, yc + H.CAV_HY - 3.3, z0 + 1.2, 60)).cut(
        compound([cyl(4.5, 30, (H.ROW_X + dx, yc + dy, 0)) for dx, dy in ((0, 0), (-40, -30), (-40, 30), (40, -30), (40, 30))]))


def dummy_board():
    """Aluminium ballast plate on the eight board standoffs, same outline and holes as RR-HEAD-ACQ, carries the resistor block."""
    ox, oy, oz = H.ACQ["origin"]
    w, h = H.ACQ["outline"]
    b = box(ox, ox + h, oy - w, oy, oz, oz + 2.0)
    return b.cut(compound([cyl(1.4, 4, (x, y, oz - 1)) for x, y, _ in board_holes()]))


def resistor_block():
    x, y, z = P_board(75.0, 14.0)
    return box(x - 6, x + 6, y - 14, y + 14, z + 2.0, z + 8.0)


CRADLE = {"deck_t": 6.0, "x": (0.0, 232.0), "hy": 195.0, "shoe_pin_x": (12.0, 58.0), "source_pocket_d": 50.6, "source_pocket_h": 3.2}


def cradle_deck():
    """Cast aluminium tooling plate; top face = z 0 (the 'floor'): 10.00 mm below the film plane when the head is seated."""
    c = CRADLE
    d = round_z(box(c["x"][0], c["x"][1], -c["hy"], c["hy"], -c["deck_t"], 0.0), 6.0)
    cuts = [cyl(c["source_pocket_d"] / 2, c["source_pocket_h"] + 1, (H.ROW_X, yc, -c["source_pocket_h"])) for yc in H.SEG_Y]
    cuts += [box(H.WIN_X0, H.WIN_X1, -176, 176, -1.2, 1) .cut(box(H.WIN_X0 + 8, H.WIN_X1 - 8, -200, 200, -5, 5))]       # two source-slide guide grooves
    return cut_all(d, cuts)


def cradle_parts():
    """Returns list of (name, shape, material, kind, desc)."""
    out = [("cradle_deck", cradle_deck(), "AL6061", "fab", "cradle deck, 6 mm cast tooling plate, top = source plane")]
    for s, tag in ((1, "L"), (-1, "R")):
        y = s * H.SHOE_Y
        saddle = fuse_all([box(8.0, 62.0, y - 14.0, y + 14.0, 0.0, H.SHOE_Z0 - 4.0),
                           box(8.0 + 0, 16.0, y - 8.0, y + 8.0, H.SHOE_Z0 - 4.01, H.SHOE_Z0), box(54.0, 62.0, y - 8.0, y + 8.0, H.SHOE_Z0 - 4.01, H.SHOE_Z0),
                           box(8.0, 62.0, y - 14.0, y - 8.6, H.SHOE_Z0 - 4.01, H.SHOE_Z1 - 4.0), box(8.0, 62.0, y + 8.6 if s < 0 else y + 8.25, y + 14.0, H.SHOE_Z0 - 4.01, H.SHOE_Z1 - 4.0),
                           box(62.0 - 0.01, H.XSTOP, y - 14.0, y - 8.6, 0.0, H.SHOE_Z1 - 4.0), box(62.0 - 0.01, H.XSTOP, y + 8.6, y + 14.0, 0.0, H.SHOE_Z1 - 4.0)])
        out.append((f"cradle_saddle_{tag}", saddle, "AL6061", "fab", "shoe saddle: two 8 mm lands at z 16.00 (datum C), side guides, x-stop faces at x 65.7 (datum A)"))
    out.append(("cradle_front_post", fuse_all([cyl(9.0, 6.0, (H.XF + 2.1, 0, 0.0)), cyl(4.0, 23.2, (H.XF + 2.1, 0, 0.0))]), "AL6061", "fab",
                "front post: pad at z 23.20 under the centre bail block (third support point)"))
    for s, tag in ((1, "L"), (-1, "R")):
        y = s * 187.0
        out.append((f"cradle_fence_{tag}", fuse_all([box(60.0, 226.0, min(y - 4, y + 4), max(y - 4, y + 4), 0.0, 30.0),
                                                     box(214.5 + 3, 226.0, min(s * 100, y), max(s * 100, y), 0.0, 30.0)]), "PETG-CF", "printed",
                    "side / front fence: keeps hands and tools off the window zone, carries the check-source slide stop"))
        out.append((f"cradle_cable_rest_{tag}", fuse_all([box(8.0, 20.0, s * H.SHOE_Y + s * 30 - 6, s * H.SHOE_Y + s * 30 + 6, 0.0, 70.0),
                                                          box(8.0, 20.0, s * H.SHOE_Y + s * 30 - 14, s * H.SHOE_Y + s * 30 + 14, 70.0, 74.0)]), "PETG-CF", "printed",
                    "pigtail rest with plug cradle (cables supported, plugs off the bench)"))
    slide = cut_all(box(H.WIN_X0 + 0.3, H.WIN_X1 - 0.3, -30.0, 30.0, 0.0, 3.0).fuse(box(H.WIN_X0 + 0.3, H.WIN_X0 + 7.7, -30, 30, -1.0, 0.01)).fuse(
        box(H.WIN_X1 - 7.7, H.WIN_X1 - 0.3, -30, 30, -1.0, 0.01)), [cyl(12.85, 5, (H.ROW_X, 0, 0.8))])
    out.append(("cradle_source_slide", slide, "AL6061", "fab", "source slide: 25.4 mm check source 0.8 mm recessed pocket floor... top of source at slide top z 3.0 (alternative 7.0 mm standoff position)"))
    return out


def gauge_parts():
    out = []
    out.append(("gauge_setting_block", box(0, 40, 0, 25, 0, 10.0), "STEEL", "fab", "10.00 mm setting block (ground, +-0.005)"))
    for name, lo in (("gauge_step_4_10", 4.0), ("gauge_step_10_16", 10.0)):
        steps = [box(k * 9.0, k * 9.0 + 9.01, 0, 20, 0, lo + 0.5 * k) for k in range(13)]
        out.append((name, fuse_all(steps + [box(-25, 0.01, 0, 20, 0, 4.0)]), "AL6061", "fab", f"stepped go/no-go wedge {lo:g}..{lo + 6:g} mm in 0.5 mm steps, 9 mm lands, handle"))
    for t in (1.5, 3.0, 5.0):
        out.append((f"gauge_shim_{t:g}".replace(".", "p"), box(0, 60, 0, 30, 0, t), "STEEL", "fab", f"{t:g} mm ground shim (floor-feature simulation)"))
    return out


# =============================================================================================== fastener heads (interference check only)
HEADS = {"M2.5_pan": (2.25, 1.65), "M3_button": (2.85, 1.65), "M3_bonded_washer": (3.6, 1.0), "M3_low": (2.75, 2.0), "M3_iso_washer": (3.0, 0.8), "M3_washer": (3.5, 0.5)}


def _head(x, y, z, *stack):
    out, zz = [], z
    for k in stack:
        r, h = HEADS[k]
        out.append(cyl(r, h, (x, y, zz)))
        zz += h
    return fuse_all(out) if len(out) > 1 else out[0]


def fastener_heads(build):
    """(name, pn, shape, desc) for every screw head that stands proud of a surface. Countersunk heads (spreader rib screws ISO 10642,
    cassette screws, lid-standoff screws from below) are flush and not modelled. Dimensions are ISO nominal maxima (UNVERIFIED vs supplier)."""
    proto = build == "prototype"            # EMI fences only in the prototype (production: the CNC frame is the enclosure)
    foot = H.FENCE_T if proto else 0.0
    out = []
    for s in (1, -1):
        for y in H.REAR_SCREW_Y:
            out.append((f"hd_rear_{s * y:+.0f}", "PUR-M2.5x8-PAN", _head(H.REAR_SCREW_X, s * y, H.Z_SPR1 + foot, "M2.5_pan"), "ISO 7045 M2.5 x 8 A2, spreader to rear-zone insert"))
        for dy in H.THEAD_SCREW_DY:
            y = s * H.SHOE_Y + dy
            st = ("M3_iso_washer", "M3_low")              # insulating shoulder washer in both builds (FRAME isolated from the receiver)
            out.append((f"hd_thead_{y:+.0f}", "PUR-M3x8-LOW", _head(H.THEAD_SCREW_X, y, H.Z_SPR1, *st), "DIN 7984 M3 x 8 A2 + insulating shoulder washer (prototype) / plain washer"))
        if proto:
            for y in FENCE_FRONT_Y:
                out.append((f"hd_ffoot_{s * y:+.0f}", "PUR-M2.5x5-PAN", _head(183.0, s * y, H.Z_SPR1 + foot, "M2.5_pan"), "ISO 7045 M2.5 x 5, front fence foot into tapped spreader"))
            for x in FENCE_SIDE_X:
                out.append((f"hd_sfoot_{x:.0f}_{s:+d}", "PUR-M2.5x5-PAN", _head(x, s * 166.9, H.Z_SPR1 + foot, "M2.5_pan"), "ISO 7045 M2.5 x 5, side fence foot"))
    pcb_top = H.ACQ["origin"][2] + (2.0 if build == "dummy" else H.ACQ["thickness"])
    for k, (x, y, _) in enumerate(board_holes()):
        out.append((f"hd_board_{k}", "PUR-M2.5x5-PAN-SW", _head(x, y, pcb_top, "M2.5_pan"), "ISO 7045 M2.5 x 5 + serrated washer, board to standoff (FRAME bond)"))
    a, b, c, d = blister_rect()
    for x, y in lid_all_holes():
        z = H.Z_LID1 + (1.0 if a < x < b and c < y < d else 0.0)
        out.append((f"hd_lid_{x:.0f}_{y:+.0f}", "PUR-M3x8-BUT", _head(x, y, z, "M3_bonded_washer", "M3_button"), "ISO 7380 M3 button head + bonded sealing washer, lid"))
    return out


# =============================================================================================== insulating jacket (standard cold configuration)
LATCH_CUT = (60.0, 110.5, -17.0, 17.0)      # keeper plate and the body's latch box (x 88..108, |y| <= 12, z 46..60) stay free


def jacket_top():
    """RR-HD-S-131: 3 mm closed-cell foam cap with a wipeable skin, PSA-bonded on the lid; rides over the J1 blister (2 mm there),
    9 mm holes give the lid screws through it (the lid comes off with the cap on it), cut out round the keeper and the latch box."""
    i, t = H.LID_INSET, H.JACKET_T
    cap = round_z(box(H.XR + i, H.XF - i, -H.YW + i, H.YW - i, H.Z_LID1, H.Z_LID1 + t), 3.0)
    a, b, c, d = blister_rect()
    x0, x1, y0, y1 = LATCH_CUT
    cuts = [box(a - 0.3, b + 0.3, c - 0.3, d + 0.3, H.Z_LID1 - 1, H.Z_LID1 + 1.3), box(x0, x1, y0, y1, 40, 60)]
    cuts += [cyl(4.5, t + 2, (x, y, H.Z_LID1 - 1)) for x, y in lid_all_holes()]
    return cut_all(cap, cuts)


def jacket_front():
    """RR-HD-S-132: 3 mm foam band PSA-bonded on the frame front face above the bail blocks (clear of the rail at full stroke and the bail)."""
    return box(H.XF, H.XF + H.JACKET_T, -170.0, 170.0, *H.JACKET_FRONT_Z)
