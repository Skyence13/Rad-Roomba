"""DXF flat patterns of the sheet / plate parts (mm, R2010). Layers: CUT (profile and holes), TAP (holes to be tapped, drawn at
tap-drill size), BEND (bend lines, bend UP unless the text says DOWN), ETCH (part number and notes).
Flat patterns are nominal developed lengths (inside dimensions + neutral axis at K = 0.4, inside radius = thickness);
the sheet-metal shop applies its own bend deduction.
"""
from __future__ import annotations

import math

import ezdxf

from . import hp as H
from . import parts as T
from .geom import HERE

PROTO, PROD, AUX = HERE / "prototype" / "dxf", HERE / "production" / "dxf", HERE / "aux" / "dxf"


def _doc():
    d = ezdxf.new("R2010")
    d.units = 4
    for name, col in (("CUT", 7), ("TAP", 1), ("BEND", 3), ("ETCH", 5)):
        d.layers.add(name, color=col)
    return d, d.modelspace()


def _poly(msp, pts, layer="CUT", close=True):
    msp.add_lwpolyline([(round(x, 4), round(y, 4)) for x, y in pts], close=close, dxfattribs={"layer": layer})


def _rect(msp, x0, x1, y0, y1, layer="CUT"):
    _poly(msp, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer)


def _txt(msp, s, xy, h=3.0):
    msp.add_text(s, dxfattribs={"layer": "ETCH", "height": h}).set_placement(xy)


def bend_allow(t, r=None, k=0.4):
    r = t if r is None else r
    return math.pi / 2 * (r + k * t)


def spreader(path):
    d, m = _doc()
    _poly(m, T.spreader_outline())
    for x, y, dia, why in T.spreader_holes():
        m.add_circle((x, y), dia / 2, dxfattribs={"layer": "TAP" if why.startswith("tap") else "CUT"})
    _txt(m, "RR-HD-S-121 SPREADER 2.0 AL 5052-H32 / 6061-T6  (coordinates = base_link x, y)", (90, -20), 3)
    _txt(m, "TAP layer: M2.5 through. Dia 4.2: clinch standoff M2.5 x 2.5 from this side (top). Dia 3.2: countersink 90 deg far side for M3.", (90, -26), 2.2)
    d.saveas(path)


def lid(path):
    d, m = _doc()
    i, r = H.LID_INSET, 3.0
    x0, x1, y0, y1 = H.XR + i, H.XF - i, -H.YW + i, H.YW - i
    m.add_lwpolyline([(x0 + r, y0, 0), (x1 - r, y0, 0.4142), (x1, y0 + r, 0), (x1, y1 - r, 0.4142), (x1 - r, y1, 0), (x0 + r, y1, 0.4142), (x0, y1 - r, 0), (x0, y0 + r, 0.4142)],
                     format="xyb", close=True, dxfattribs={"layer": "CUT"})
    for x, y in T.lid_all_holes():
        m.add_circle((x, y), 1.7, dxfattribs={"layer": "CUT"})
    a, b, c, e = T.j1_zone()
    _rect(m, a - 0.5, b + 0.5, c - 0.5, e + 0.5)
    _txt(m, "RR-HD-S-122 LID 2.0 AL 5052-H32; 35 x dia 3.4 for M3 + bonded sealing washer; J1 opening covered by RR-HD-S-123", (90, 20), 3)
    d.saveas(path)
    d, m = _doc()
    ba, bb, bc, bd = T.blister_rect()
    _rect(m, ba, bb, bc, bd)
    for yy in (bc + 3.0, bd - 3.0):
        m.add_circle((bb - 3.0, yy), 1.25, dxfattribs={"layer": "CUT"})
    for xx, yy in T.lid_all_holes():
        if ba < xx < bb and bc < yy < bd:
            m.add_circle((xx, yy), 1.7, dxfattribs={"layer": "CUT"})
    _txt(m, "RR-HD-S-123 J1 BLISTER 1.0 AL; 2 x dia 2.5 rivet (front), 3 x dia 3.4 lid screws (rear)", (ba, bc - 12), 2.5)
    d.saveas(path.with_name("RR-HD-S-123_j1_blister.dxf"))


def fences(folder):
    t = H.FENCE_T
    ba = bend_allow(t)
    wall_h = T.FENCE_TOP - H.Z_SPR1 - 2 * t            # straight wall between the two bends
    # front fence: strip along y; bands across: top flange 2.5 | bend | wall | bend | foot
    d, m = _doc()
    hy = T.FENCE_SIDE_Y + t
    foot = H.BAY_X1 - 0.1 - T.FENCE_FRONT_X - t
    w = [2.5 - t, ba, wall_h, ba, foot - t]
    ys = [0]
    for v in w:
        ys.append(ys[-1] + v)
    _rect(m, -hy, hy, 0, ys[-1])
    for yb in (ys[1] + ba / 2, ys[3] + ba / 2):
        m.add_line((-hy, yb), (hy, yb), dxfattribs={"layer": "BEND"})
    x_foot = lambda xb: ys[4] - t + (xb - T.FENCE_FRONT_X - t)       # base x -> developed coordinate on the foot
    for xx, yy in T.lid_holes():
        if xx > 150:
            m.add_circle((-yy, x_foot(xx)), 2.7, dxfattribs={"layer": "CUT"})
    for s in (1, -1):
        for yy in T.FENCE_FRONT_Y:
            m.add_circle((s * yy, x_foot(183.0)), 1.4, dxfattribs={"layer": "CUT"})
        _rect(m, s * H.SHOE_Y - 13.5, s * H.SHOE_Y + 13.5, ys[4] - t + 0.01, ys[-1] + 0.01)
    _txt(m, "RR-HD-X-124 EMI FENCE FRONT 0.5 AL 5052-H32; bend 1 (flange) DOWN 90, bend 2 (foot) UP 90; developed, K 0.4", (-150, -8), 2.5)
    d.saveas(folder / "RR-HD-X-124_fence_front.dxf")
    # side fence
    d, m = _doc()
    xa, xb = 79.2, T.FENCE_FRONT_X - 2.7
    foot = H.SPR_HY - 0.1 - T.FENCE_SIDE_Y - t
    w = [2.5 - t, ba, wall_h, ba, foot - t]
    ys = [0]
    for v in w:
        ys.append(ys[-1] + v)
    _rect(m, xa, xb, 0, ys[-1])
    for yb in (ys[1] + ba / 2, ys[3] + ba / 2):
        m.add_line((xa, yb), (xb, yb), dxfattribs={"layer": "BEND"})
    yf = ys[4] - t + (166.9 - T.FENCE_SIDE_Y - t)
    m.add_circle((H.ROW_X, yf), 2.7, dxfattribs={"layer": "CUT"})
    for xx in T.FENCE_SIDE_X:
        m.add_circle((xx, yf), 1.4, dxfattribs={"layer": "CUT"})
    _txt(m, "RR-HD-X-125 EMI FENCE SIDE 0.5 AL 5052-H32 (2 off, second one bent mirrored)", (xa, -8), 2.5)
    d.saveas(folder / "RR-HD-X-125_fence_side.dxf")
    # rear comb: wall along y; above the wall the top flange; below it either a foot (between chimneys) or a chimney liner with two side flanges
    d, m = _doc()
    top = 2.0 - t
    y_wall0 = 0.0
    y_wall1 = wall_h
    liner = H.Z_SPR1 - (H.CHIM_FLOOR_REAR + 0.5)          # liner length below the spreader top
    foot = T.COMB_FOOT_X1 - T.FENCE_REAR_X - t
    pts = [(-hy, y_wall1 + ba + top), (hy, y_wall1 + ba + top), (hy, y_wall0)]
    edges = [-hy] + [v for yc in sorted(H.SEG_Y) for v in (yc - H.CHIM_HY - T.COMB_CHIM_MARGIN, yc + H.CHIM_HY + T.COMB_CHIM_MARGIN)] + [hy]
    segs = list(zip(edges[0::2], edges[1::2]))
    prof = [(hy, y_wall1 + ba + top), (hy, -ba - foot)]
    for (ya, yb), yc in zip(reversed(segs), [None] + sorted(H.SEG_Y, reverse=True)):
        if yc is not None:
            w_l = H.CHIM_HY - 0.2
            side = (H.CAV_X0 - 0.5) - T.FENCE_REAR_X - t
            prof += [(yc + w_l + 7.5, -ba - foot), (yc + w_l + 7.5, 0.0), (yc + w_l + ba + side, 0.0), (yc + w_l + ba + side, -liner), (yc - w_l - ba - side, -liner),
                     (yc - w_l - ba - side, 0.0), (yc - w_l - 7.5, 0.0), (yc - w_l - 7.5, -ba - foot)]
            m.add_line((yc + w_l + ba / 2, 0), (yc + w_l + ba / 2, -liner), dxfattribs={"layer": "BEND"})
            m.add_line((yc - w_l - ba / 2, 0), (yc - w_l - ba / 2, -liner), dxfattribs={"layer": "BEND"})
        m.add_line((ya, -ba / 2), (yb, -ba / 2), dxfattribs={"layer": "BEND"})
    prof += [(-hy, -ba - foot), (-hy, y_wall1 + ba + top)]
    _poly(m, prof)
    m.add_line((-hy, y_wall1 + ba / 2), (hy, y_wall1 + ba / 2), dxfattribs={"layer": "BEND"})
    zdev = lambda z: z - H.Z_SPR1 - t                    # height on the wall above the foot bend
    for s in (1, -1):
        _rect(m, s * H.SHOE_Y - H.PORT_SLOT_HY, s * H.SHOE_Y + H.PORT_SLOT_HY, zdev(H.PORT_SLOT_Z0), y_wall1 + ba + top + 0.01)
    m.add_circle((H.VENT[1], zdev(H.VENT[2])), 2.5, dxfattribs={"layer": "CUT"})
    _txt(m, "RR-HD-X-126 EMI REAR COMB 0.5 AL 5052-H32; feet UP 90, top flange UP 90, chimney liner side flanges UP 90 (toward the lanes); foot holes: match-drill from RR-HD-S-121",
         (-160, y_wall1 + 8), 2.2)
    d.saveas(folder / "RR-HD-X-126_fence_rear_comb.dxf")


def side_rail(path):
    """Flat pattern of the left side rail (mirror for the right): return | bend | side strip, tabs on the top edge."""
    d, m = _doc()
    t = H.SIDE_T
    ba = bend_allow(t)
    ret = (H.SIDE_Y0 + t) - H.RET_Y0 - t
    side = 187.6 - H.RET_X1
    hgt = H.SIDE_Z1 - H.SIDE_Z0
    L = ret + ba + side
    _rect(m, 0, L, 0, hgt)
    m.add_line((ret + ba / 2, 0), (ret + ba / 2, hgt), dxfattribs={"layer": "BEND"})
    rise = H.SLIT_Z[0] + 0.3 - H.SIDE_Z1
    for (u0, u1, depth) in ((ret - (172.0 - H.RET_Y0), ret - (165.0 - H.RET_Y0), 77.0 - H.RET_X1), (ret - (148.0 - H.RET_Y0), ret - (143.4 - H.RET_Y0), 77.0 - H.RET_X1),
                            (ret + ba + (183.7 - H.RET_X1), ret + ba + (187.3 - H.RET_X1), H.SIDE_Y0 - 164.0)):
        _rect(m, u0, u1, hgt, hgt + rise + ba + depth)
        m.add_line((u0, hgt + rise + ba / 2), (u1, hgt + rise + ba / 2), dxfattribs={"layer": "BEND"})
        cx = (u0 + u1) / 2
        m.add_lwpolyline([(cx - 1.2, hgt + rise + ba + depth * 0.35), (cx + 1.2, hgt + rise + ba + depth * 0.35 + 2.4)], dxfattribs={"layer": "ETCH"})
    m.add_circle((ret - (H.SW_SIDE["y"] - H.RET_Y0), H.SW_SIDE["z"] - H.SIDE_Z0), 2.1, dxfattribs={"layer": "CUT"})
    _txt(m, "RR-HD-S-431 SIDE RAIL LH 0.8 SS 301 1/2H (RR-HD-S-432 = mirrored bends). Tabs: 3.2 wide slot at 45 deg x 4.6 long (ETCH line = slot axis); dia 4.2: clinch nut M3 for the adjusting screw",
         (0, -8), 2.2)
    d.saveas(path)


def shield_can(path):
    d, m = _doc()
    L, W, Hc = 32.0, 36.0, 5.0
    pts = [(0, 0), (L, 0), (L, -Hc), (L + 0, -Hc)]
    prof = [(-Hc, 0), (0, 0), (0, -Hc), (L, -Hc), (L, 0), (L + Hc, 0), (L + Hc, W), (L, W), (L, W + Hc), (0, W + Hc), (0, W), (-Hc, W)]
    _poly(m, prof)
    for a, b in (((0, 0), (L, 0)), ((L, 0), (L, W)), ((L, W), (0, W)), ((0, W), (0, 0))):
        m.add_line(a, b, dxfattribs={"layer": "BEND"})
    for s in (1, -1):
        _rect(m, -Hc - 0.01, -Hc + 1.2, W / 2 + s * 6.0 - 1.0, W / 2 + s * 6.0 + 1.0)
    _txt(m, "RR-HEAD-SHLD-A LANE SHIELD CAN 0.2 tin-plated steel (or nickel silver C770); fold 4 walls DOWN 90; 36.0 x 32.0 x 5.0 outside; two 2 x 1.2 mouse holes on the rear wall (v = 5.5 side)",
         (-5, -12), 1.6)
    d.saveas(path)


def cradle_deck(path):
    d, m = _doc()
    c = T.CRADLE
    _rect(m, c["x"][0], c["x"][1], -c["hy"], c["hy"])
    for yc in H.SEG_Y:
        m.add_circle((H.ROW_X, yc), c["source_pocket_d"] / 2, dxfattribs={"layer": "ETCH"})
    _txt(m, "RR-HD-C-601 CRADLE DECK 6.0 cast tooling plate (MIC-6 class); pockets and tapped holes per STEP", (10, -c["hy"] - 10), 3)
    d.saveas(path)


def run():
    for f in (PROTO, PROD, AUX):
        f.mkdir(parents=True, exist_ok=True)
    n = 0
    for folder in (PROTO, PROD):
        spreader(folder / "RR-HD-S-121_spreader.dxf")
        lid(folder / "RR-HD-S-122_lid.dxf")
        side_rail(folder / "RR-HD-S-431_side_rail_lh.dxf")
        shield_can(folder / "RR-HEAD-SHLD-A_lane_shield_can.dxf")
        n += 5
    fences(PROTO)
    cradle_deck(AUX / "RR-HD-C-601_cradle_deck.dxf")
    return n + 4
