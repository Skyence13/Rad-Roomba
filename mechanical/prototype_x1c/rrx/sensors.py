"""RR-X sensor and control mounts: ToF capsule seats, panel-device seats, receptacle seats, RR-PANEL tray, charge inlet
cover, LiDAR adapter, CM5 tray, bumper segments.  Feature helpers return (add, cut) solids that shells.py applies."""
from __future__ import annotations

import math

import cadquery as cq

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import dims as D
from .util import Part, V, box, cut, cyl, fuse, mirror_y, place, prism

TOF_BOSS = (28.0, 20.0, 9.5)        # local x (board long axis), local y, depth along the boresight
TOF_WIN = (15.0, 11.0, 1.0)         # IR window blank (PMMA IR-pass), seated in a 1.1 mm recess
TOF_AP = (12.0, 8.0)                # clear aperture (interfaces: >= 12 x 8)


def _lbox(x, y, z0, z1):
    return box(-x / 2, x / 2, -y / 2, y / 2, z0, z1)


LOOK_BOSS = (22.0, 26.0, 6.6)       # shallow seat for the two look-ahead sensors in the grip fairings (grip bar 0.6 mm behind)
LOOK_SCREW_Y = 10.5                  # M2 clip screws above/below the board (local y) instead of beside it


def _look_xdir(d):
    """Local x of the look-ahead seats: horizontal, perpendicular to the boresight (board long axis across the cheek)."""
    return P._unit((-d[1], d[0], 0.0)) if abs(d[0]) + abs(d[1]) > 1e-9 else (1.0, 0.0, 0.0)


def tof_boss(xyz, d, look=False, grow=0.0):
    """Seat block for one RR-TOF: front face in the aperture plane, axis = boresight."""
    if look:
        bx, by, bz = LOOK_BOSS
        return place(_lbox(bx + 2 * grow, by + 2 * grow, -bz - grow, grow), xyz, d, _look_xdir(d))
    return place(_lbox(TOF_BOSS[0], TOF_BOSS[1], -TOF_BOSS[2], 0.0), xyz, d)


def tof_pocket(xyz, d, sight=14.0, look=False):
    """Cut for one RR-TOF: window recess, aperture, board pocket open to the rear, two M2 insert bores, sight tunnel."""
    e = L.env("tof_board")
    if look:
        bx, by, bz = LOOK_BOSS
        c = fuse(_lbox(TOF_WIN[0] + 0.3, TOF_WIN[1] + 0.3, -(TOF_WIN[2] + 0.1), 0.0),
                 _lbox(TOF_AP[0], TOF_AP[1], -3.0, 0.0),
                 _lbox(e["l"] + 0.5, e["w"] + 0.5, -bz, -2.6),
                 _lbox(bx - 2.0, by - 1.0, -14.0, -bz))                 # clip recess + rear access (bench assembly before the bar)
        for sy in (-1, 1):
            c = c.fuse(cyl(D.INSERT["M2"][0] / 2, D.INSERT["M2"][1], (0, sy * LOOK_SCREW_Y, -bz)))
        xd = _look_xdir(d)
    else:
        c = fuse(_lbox(TOF_WIN[0] + 0.3, TOF_WIN[1] + 0.3, -(TOF_WIN[2] + 0.1), 0.0),
                 _lbox(TOF_AP[0], TOF_AP[1], -3.0, 0.0),
                 _lbox(e["l"] + 0.5, e["w"] + 0.5, -40.0, -2.6))
        for sx in (-1, 1):
            c = c.fuse(cyl(D.INSERT["M2"][0] / 2, D.INSERT["M2"][1], (sx * 11.6, 0, -TOF_BOSS[2])))
        xd = None
    tunnel = cq.Workplane("XY").rect(TOF_WIN[0] + 0.3, TOF_WIN[1] + 0.3).workplane(offset=sight).rect(TOF_WIN[0] + 0.3 + 0.5 * sight, TOF_WIN[1] + 0.3 + 0.5 * sight).loft().val()
    return place(c.fuse(tunnel), xyz, d, xd)


def tof_window(xyz, d):
    return place(_lbox(TOF_WIN[0], TOF_WIN[1], -TOF_WIN[2], 0.0), xyz, d)


def tof_clip(xyz, d, look=False):
    """Rear clip that holds the board against the light-blocker gasket (2 x M2)."""
    if look:
        bx, by, bz = LOOK_BOSS
        c = _lbox(bx - 2.6, by - 1.6, -bz - 1.6, -bz)
        for sy in (-1, 1):
            c = c.cut(cyl(D.CLEAR["M2"] / 2, 4, (0, sy * LOOK_SCREW_Y, -bz - 2.5)))
        return place(c, xyz, d, _look_xdir(d))
    c = _lbox(TOF_BOSS[0], 8.0, -TOF_BOSS[2] - 1.6, -TOF_BOSS[2])
    for sx in (-1, 1):
        c = c.cut(cyl(D.CLEAR["M2"] / 2, 4, (sx * 11.6, 0, -TOF_BOSS[2] - 2.5)))
    return place(c, xyz, d)


def device_seat(xyz, n, hole_d=22.3, face_d=34.0, boss_d=38.0, notch=True, panel_t=4.5):
    """22 mm panel device: internal boss, flat spot face, through hole with anti-rotation notch. -> (add, cut)."""
    add = place(cyl(boss_d / 2, panel_t + 1.5, (0, 0, -(panel_t + 0.6))), xyz, n)
    c = fuse(cyl(face_d / 2, 14.0, (0, 0, -0.6)), cyl(hole_d / 2, 40.0, (0, 0, -20.0)))
    if notch:
        c = c.fuse(box(-1.6, 1.6, hole_d / 2 - 0.5, hole_d / 2 + 1.7, -20.0, 0.0))
    return add, place(c, xyz, n), place(cyl(60.0, 60.0, (0, 0, -(panel_t + 0.6) - 60.0)), xyz, n)


def lightpipe_xy():
    cx, cy = P.PANEL_BOARD["center"]
    return [(cx - 16.0 + 8.0 * i, cy) for i in range(5)]


def panel_tray():
    """Printed tray that carries RR-PANEL 21 mm under the left deck; screwed to two deck bosses."""
    pc = P.PANEL_CONTROLS["annunciator"]["xyz"]
    e = L.env("panel_board")
    zt = pc[2] - P.PANEL_BOARD["below_skin"]
    zb = zt - e["h"]
    t = box(pc[0] - e["l"] / 2 - 2.5, pc[0] + e["l"] / 2 + 2.5, pc[1] - e["w"] / 2 - 2.5, pc[1] + e["w"] / 2 + 2.5, zb - 2.0, zb + 6.0)
    t = t.cut(box(pc[0] - e["l"] / 2 - 0.3, pc[0] + e["l"] / 2 + 0.3, pc[1] - e["w"] / 2 - 0.3, pc[1] + e["w"] / 2 + 0.3, zb, zb + 10))
    t = t.cut(box(pc[0] - e["l"] / 2 + 4, pc[0] + e["l"] / 2 - 4, pc[1] - e["w"] / 2 + 3, pc[1] + e["w"] / 2 - 3, zb - 3, zb + 1))
    for sy in (-1, 1):
        ear = box(pc[0] - 6.0, pc[0] + 6.0, pc[1] + sy * (e["w"] / 2 + 2.5), pc[1] + sy * (e["w"] / 2 + 11.0), zb + 3.0, zb + 6.0)
        t = t.fuse(ear).cut(cyl(D.CLEAR["M3"] / 2, 10, (pc[0], pc[1] + sy * PANEL_BOSS_DY, zb)))
    return t.clean(), zb + 6.0


PANEL_BOSS_DY = 19.0


CM5_TRAY_SCREWS = [(-140.0, 76.0), (-140.0, 88.0), (-83.0, 76.0), (-83.0, 88.0)]


def cm5_tray():
    """Printed deck for the CM5 carrier in the left bay: pedestal on the plate, deck under the carrier, four M2.5 bosses
    (carrier hole pattern UNVERIFIED -> bosses are drilled/inserted to the purchased board), strap slots."""
    c = P.CM5_POSE
    x0, x1 = c["x"]
    y0, y1 = c["y"]
    zb = c["pcb_z"] - 3.0
    Z1 = D.PLATE_Z[1]
    t = fuse(box(x0 - 2, x1 + 2, 70.0, 92.0, Z1, Z1 + 2.5), box(x0, x1, y0 + 1.0, y1 - 1.0, zb - 2.5, zb))
    for x in (x0 + 4, x1 - 4):
        t = t.fuse(box(x - 4, x + 4, 71.0, 91.0, Z1, zb - 2.5))
    t = t.clean()
    for x, y in CM5_TRAY_SCREWS:
        t = t.cut(cyl(D.INSERT["M3"][0] / 2, 4, (x, y, Z1 - 1)))
    t = t.cut(box(x0 + 14, x1 - 14, y0 + 12, y1 - 12, zb - 3, zb + 1))                 # air / strap window under the carrier
    for x in (x0 + 8, x1 - 8):
        for y in (y0 + 6, y1 - 6):
            t = t.cut(cyl(D.INSERT["M2.5"][0] / 2, 3, (x, y, zb - 2.6)))
    return t


INLET_COVER_T = 5.0     # cover height above the receptacle nose (parts.yaml candidate value 8.0 reduced: 3 mm air over the nose,
                        # keeps the closed cover inside the 295 mm tyre width)


def inlet_cover():
    """Hinged cap over the charge inlet (hinge at the top, 2 mm stainless pin), finger tab, tongue that presses the cover switch pin."""
    e = L.env("charge_inlet")
    cw, ch, _ = e["cover"]
    ct = INLET_COVER_T
    z0 = e["front_projection"]
    c = box(-cw / 2, cw / 2, -ch / 2, ch / 2, z0 + ct - 2.0, z0 + ct)                    # lid plate
    skirt = box(-cw / 2, cw / 2, -ch / 2, ch / 2, 1.0, z0 + ct).cut(box(-cw / 2 + 2, cw / 2 - 2, -ch / 2 + 2, ch / 2 - 2, 0, z0 + ct - 2.0))
    c = c.fuse(skirt)
    c = c.fuse(box(-9, 9, -ch / 2 - 9, -ch / 2, z0 + ct - 2.0, z0 + ct))                 # glove tab at the bottom edge
    c = c.fuse(cyl(3.0, cw - 8, (-cw / 2 + 4, ch / 2 + 1.0, z0 + ct - 3.0), (1, 0, 0)))  # hinge barrel at the top
    c = c.clean().cut(cyl(1.1, cw, (-cw / 2, ch / 2 + 1.0, z0 + ct - 3.0), (1, 0, 0)))
    return c


def inlet_seat():
    """-> (add, cut) in the inlet frame (origin on the skin, +z outward, +y up)."""
    e = L.env("charge_inlet")
    cw, ch, _ = e["cover"]
    ct = INLET_COVER_T
    add = fuse(cyl(e["body_d"] / 2 + 6.0, 6.0, (0, 0, -5.5)),
               box(-cw / 2, cw / 2, 8.0, ch / 2 + 4.0, -5.5, 0.5),                                                 # hinge pad joining the lugs to the boss
               box(-cw / 2, -cw / 2 + 3.6, ch / 2 - 2.0, ch / 2 + 4.0, -3.0, e["front_projection"] + ct),      # hinge lugs
               box(cw / 2 - 3.6, cw / 2, ch / 2 - 2.0, ch / 2 + 4.0, -3.0, e["front_projection"] + ct),
               box(-8.0, 8.0, -ch / 2 - 1.0, -ch / 2 + 9.0, -14.0, -2.0))                                         # cover-switch pocket block
    c = fuse(cyl(e["body_d"] / 2 - 2 + 0.15, 40, (0, 0, -30)), cyl(e["body_d"] / 2 + 3.0, 12.0, (0, 0, -0.5)),
             cyl(1.1, cw + 2, (-cw / 2 - 1, ch / 2 + 1.0, e["front_projection"] + ct - 3.0), (1, 0, 0)),
             box(-6.8, 6.8, -ch / 2 + 1.2, -ch / 2 + 6.6, -15.0, -5.0),                                           # D2HW pocket (plunger +z)
             cyl(1.6, 8.0, (0, -ch / 2 + 3.9, -6.0)))                                                              # push-pin bore
    return add, c
