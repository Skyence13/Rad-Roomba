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
TOF_FRONT = 2.6                     # PCB front face (sensor side) behind the aperture plane: 1.1 window recess + 1.5 light-blocker foam


def _lbox(x, y, z0, z1):
    return box(-x / 2, x / 2, -y / 2, y / 2, z0, z1)


# Seat kinds.  std: 9.5 mm deep boss, clip behind it (hull, decks, hump).  look_f: shallow seat in the grip fairings (the
# grip bar and side plate stand 0.6 mm behind the clip).  look_r: shallow seat with the board long axis vertical, so the
# seat stays outside the battery hatch opening (|y| <= 58) next to the rear look-behind apertures.
SEAT = {"std": (28.0, 20.0, 9.5, 28.0), "look_f": (28.0, 18.0, 6.3, 27.0), "look_r": (28.0, 17.0, 6.3, 27.0)}   # boss x, y, depth, clip x
CLIP_W, CLIP_T, SCREW_X = 8.0, 1.6, 11.6


def seat_kind(name):
    return "look_f" if name.startswith("tof_look_fwd") else ("look_r" if name.startswith("tof_look_rev") else "std")


def seat_xdir(d, kind):
    """Local x (board long axis) of a seat: None = default of place(); look_f horizontal; look_r vertical."""
    if kind == "look_f":
        return P._unit((-d[1], d[0], 0.0)) if abs(d[0]) + abs(d[1]) > 1e-9 else (1.0, 0.0, 0.0)
    if kind == "look_r":
        u = (0.0, 0.0, 1.0)
        k = sum(a * b for a, b in zip(u, d))
        return P._unit(tuple(a - k * b for a, b in zip(u, d))) if abs(k) < 0.999 else (1.0, 0.0, 0.0)
    return None


TOF_FLIP = {"tof_look_rev_left", "tof_prox_rc"}     # fit review C3 (tool-checked): their J1 plug met the hatch door / frame the other way round; sensors whose carrier is turned 180 deg about the boresight (J1 / plug on the other side of the seat)


def seat_x(xyz, d, kind):
    """Local x of the seat of the sensor at xyz: seat_xdir, negated for the sensors in TOF_FLIP."""
    xd = seat_xdir(d, kind)
    name = next((n for n, t in P.TOF_SENSORS.items() if all(abs(t["xyz"][i] - xyz[i]) < 1e-6 for i in range(3))), None)
    if name not in TOF_FLIP:
        return xd
    if xd is None:
        z = P._unit(d)
        ref = (0, 0, 1) if abs(z[2]) < 0.9 else (1, 0, 0)
        xd = P._unit((ref[1] * z[2] - ref[2] * z[1], ref[2] * z[0] - ref[0] * z[2], ref[0] * z[1] - ref[1] * z[0]))
    return tuple(-c for c in xd)


def tof_boss(xyz, d, kind="std", grow=0.0, back=0.0):
    """Seat block for one RR-TOF: front face in the aperture plane, axis = boresight.  grow/back: envelope for relief cuts."""
    bx, by, bz, _ = SEAT[kind]
    return place(_lbox(bx + 2 * grow, by + 2 * grow, -bz - back - grow, grow), xyz, d, seat_x(xyz, d, kind))


def _tof_board():
    """RR-TOF-A outline and J1 (header + mated plug + wire exit) from the board file, in the seat frame (board u, v = local x, y)."""
    from mechanical.common import boards as BD
    b = BD.load("RR-TOF-A")
    return b["outline_uv"], BD.connector_mating("RR-TOF-A", "J1")


CLIP_Y = (-2.0, 4.4)            # clip bar and pads on the half of the board without the J1 header (header v -8.95..-2.55)
PAD_U = (7.0, 9.0)              # end pads |u| 7..9: clear of the bottom-side parts (|u| <= 3.7)


def tof_pocket(xyz, d, sight=14.0, kind="std"):
    """Cut for one RR-TOF (fit review C3): window recess and aperture on the sensor axis, board pocket on the REAL board outline
    (sensor 2.4 mm off the board centre, o1), relief for the J1 header, the mated GH plug and its wire exit, open to the rear,
    clip recess on the header-free half, two M2 insert bores."""
    (u0, v0, u1, v1), j1 = _tof_board()
    bx, by, bz, cx = SEAT[kind]
    m = 0.25
    deep = -40.0 if kind == "std" else -(bz + 4.5)
    c = fuse(_lbox(TOF_WIN[0] + 0.3, TOF_WIN[1] + 0.3, -(TOF_WIN[2] + 0.1), 0.0),
             _lbox(TOF_AP[0], TOF_AP[1], -3.0, 0.0),
             box(u0 - m, u1 + m, v0 - m, v1 + m, deep, -TOF_FRONT))
    pu0, pu1, pv0, pv1, pz0, pz1 = j1["plug"]
    eu0, eu1, ev0, ev1, ez0, ez1 = j1["exit"]
    c = c.fuse(box(min(pu0, eu0) - 0.5, max(pu1, eu1) + 0.5, min(pv0, ev0) - 0.5, v0, -TOF_FRONT - 0.2, -bz - 12.0))   # plug + wire-exit relief, open rearward
    cy0, cy1 = CLIP_Y
    c = c.fuse(box(-(cx + 0.4) / 2, (cx + 0.4) / 2, cy0 - 0.2, cy1 + 0.2, -bz - 12.0, -bz))            # clip recess and rear access
    for sx in (-1, 1):
        c = c.fuse(cyl(D.INSERT["M2"][0] / 2, D.INSERT["M2"][1], (sx * SCREW_X, (cy0 + cy1) / 2, -bz)))
    tunnel = cq.Workplane("XY").rect(TOF_WIN[0] + 0.3, TOF_WIN[1] + 0.3).workplane(offset=sight).rect(TOF_WIN[0] + 0.3 + 0.5 * sight, TOF_WIN[1] + 0.3 + 0.5 * sight).loft().val()
    return place(c.fuse(tunnel), xyz, d, seat_x(xyz, d, kind))


def tof_window(xyz, d, kind="std"):
    return place(_lbox(TOF_WIN[0], TOF_WIN[1], -TOF_WIN[2], 0.0), xyz, d, seat_x(xyz, d, kind))


def tof_clip(xyz, d, kind="std"):
    """Rear clip (fit review C3 / m9): bar on the header-free half of the board, two end pads that bear on the PCB back
    (local z -4.2), 2 x M2 into the seat inserts.  Nothing of the clip crosses the J1 header or its plug."""
    bx, by, bz, cx = SEAT[kind]
    cy0, cy1 = CLIP_Y
    c = box(-cx / 2, cx / 2, cy0, cy1, -bz - CLIP_T, -bz)
    back = -TOF_FRONT - 1.6
    for sx in (-1, 1):
        c = c.fuse(box(sx * PAD_U[0], sx * PAD_U[1], cy0, cy1, -bz, back))
        c = c.cut(cyl(D.CLEAR["M2"] / 2, 4, (sx * SCREW_X, (cy0 + cy1) / 2, -bz - 2.5)))
    return place(c.clean(), xyz, d, seat_x(xyz, d, kind))


def device_seat(xyz, n, hole_d=22.3, face_d=34.0, boss_d=38.0, notch=True, panel_t=4.5):
    """22 mm panel device: internal boss, flat spot face, through hole with anti-rotation notch. -> (add, cut)."""
    add = place(cyl(boss_d / 2, panel_t + 1.5, (0, 0, -(panel_t + 0.6))), xyz, n)
    c = fuse(cyl(face_d / 2, 14.0, (0, 0, -0.6)), cyl(hole_d / 2, 40.0, (0, 0, -20.0)))
    if notch:
        c = c.fuse(box(-1.6, 1.6, hole_d / 2 - 0.5, hole_d / 2 + 1.7, -20.0, 0.0))
    return add, place(c, xyz, n), place(cyl(60.0, 60.0, (0, 0, -(panel_t + 0.6) - 60.0)), xyz, n)


def lightpipe_xy():
    """Light-pipe axes over the RR-PANEL LEDs, read from the board file (board rotated: x = cx + 35 - u, y = cy - 12 + v)."""
    from mechanical.common import boards as BD
    cx, cy = P.PANEL_BOARD["center"]
    leds = sorted((p["uv"] for r, p in BD.load("RR-PANEL")["parts"].items() if "LED" in p["fp"]), key=lambda q: q[0])
    if not leds:
        return [(cx - 16.0 + 8.0 * i, cy) for i in range(5)]
    return [(round(cx + 35.0 - u, 2), round(cy - 12.0 + v, 2)) for u, v in leds]


def panel_tray():
    """Printed tray that carries RR-PANEL 21 mm under the left deck; screwed to two deck bosses."""
    pc = P.PANEL_CONTROLS["annunciator"]["xyz"]
    e = L.env("panel_board")
    zt = pc[2] - P.PANEL_BOARD["below_skin"]
    zb = zt - e["h"]
    t = box(pc[0] - e["l"] / 2 - 1.5, pc[0] + e["l"] / 2 + 1.0, pc[1] - e["w"] / 2 - 2.5, pc[1] + e["w"] / 2 + 2.5, zb - 2.0, zb + 6.0)
    t = t.cut(box(pc[0] - e["l"] / 2 - 0.3, pc[0] + e["l"] / 2 + 0.3, pc[1] - e["w"] / 2 - 0.3, pc[1] + e["w"] / 2 + 0.3, zb, zb + 10))
    # fit review M7: board orientation fixed (long axis x with u = -x, v = 24 edge with J1 / J2 OUTBOARD (+y), parts up); window
    # under the bottom-side parts (v 2.4..22, u 2..68 of the board file), two M2.5 bosses at the board holes H1 / H2 (thread-
    # forming screws, bosses end 2 mm under the floor), notches for the plugs in the outboard wall
    X = lambda u: pc[0] + e["l"] / 2 - u
    Y = lambda v: pc[1] - e["w"] / 2 + v
    t = t.cut(box(X(68.0), X(2.0), Y(2.4), Y(22.0), zb - 3, zb + 1))
    for hu, hv in ((3.5, 20.5), (66.5, 20.5)):
        t = t.fuse(cyl(3.2, 4.0, (X(hu), Y(hv), zb - 4.0))).cut(cyl(1.1, 4.5, (X(hu), Y(hv), zb - 4.2)))
    for nu0, nu1 in ((20.0, 40.0), (44.5, 54.5)):
        t = t.cut(box(X(nu1), X(nu0), Y(24.0) - 1.0, Y(24.0) + 12.0, zb + 0.5, zb + 7.0))
    for sy in (-1, 1):
        ex = pc[0] + (PANEL_EAR_DX if sy > 0 else 0.0)                    # outboard ear moved clear of the J1 / J2 plugs; inboard ear stays behind the cover
        ear = box(ex - 6.0, ex + 6.0, pc[1] + sy * (e["w"] / 2 + 2.5), pc[1] + sy * (PANEL_BOSS_DY + 3.5), zb + 3.0, zb + 6.0)   # ear stays out of the hump_side_left corridor
        t = t.fuse(ear).cut(cyl(D.CLEAR["M3"] / 2, 10, (ex, pc[1] + sy * PANEL_BOSS_DY, zb)))

    sw = D.WELL_WALL
    t = t.cut(box(P.SADDLE["x"][0] - sw - 0.5, 0.0, P.SADDLE["half_y"] - 0.5, P.SADDLE["half_y"] + sw + 0.4, 102.3, 120.0))   # under the saddle-well wall
    return t.clean(), zb + 6.0


PANEL_BOSS_DY = 16.0          # inboard boss stays out of the hump_side_left corridor (y <= 76)
PANEL_EAR_DX = 25.0           # tray ears / deck bosses at x = annunciator x + 25: clear of the J1 / J2 plugs on the outboard edge (fit review M7)


CM5_TRAY_SCREWS = [(-140.0, 76.0), (-140.0, 88.0), (-83.0, 76.0), (-83.0, 88.0)]


def cm5_tray():
    """Printed deck for the CM5 carrier in the left bay: pedestal on the plate, deck under the carrier, four M2.5 bosses
    (carrier hole pattern UNVERIFIED -> bosses are drilled/inserted to the purchased board), strap slots."""
    c = P.CM5_POSE
    x0, x1 = c["x"]
    y0, y1 = c["y"]
    zb = c["pcb_z"] - 3.0
    Z1 = D.PLATE_Z[1]
    t = fuse(box(x0 - 2, x1 - 1.5, 70.0, 92.0, Z1, Z1 + 2.5), box(x0, x1 - 2.5, y0 + 11.0, y1 - 9.0, zb - 2.5, zb))   # base stops short of bridge post 0; deck clear of the tunnel wall (y <= 69)
    for x in (x0 + 4, x1 - 4):
        t = t.fuse(box(x - 4, x + 4, 71.0, 91.0, Z1, zb - 2.5))
    t = t.clean()
    for x, y in CM5_TRAY_SCREWS:
        t = t.cut(cyl(D.INSERT["M3"][0] / 2, 4, (x, y, Z1 - 1)))
    t = t.cut(box(x0 + 14, x1 - 14, y0 + 12, y1 - 12, zb - 3, zb + 1))                 # air / strap window under the carrier
    for x in (x0 + 8, x1 - 8):
        for y in (y0 + 15, y1 - 6):
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


def inlet_xdir():
    n = P.CHARGE_INLET["normal"]
    return P._unit((-n[1], n[0], 0.0))


def inlet_seat():
    """-> (add, cut, spot) in the inlet frame (origin on the skin, +z outward, +y up).  spot: skin removed above the seat
    plane over the cover footprint (the cover must not dig into the tumblehome); add: flat plinth, hinge pad and lugs."""
    e = L.env("charge_inlet")
    cw, ch, _ = e["cover"]
    ct = INLET_COVER_T
    spot = box(-cw / 2 - 4.5, cw / 2 + 4.5, -ch / 2 - 10.5, ch / 2 + 5.5, 0.5, 40.0)
    add = fuse(box(-cw / 2 - 4.5, cw / 2 + 4.5, -ch / 2 - 10.5, ch / 2 + 5.5, -6.0, 0.5),                            # flat plinth (spot face)
               cyl(e["body_d"] / 2 + 6.0, 6.0, (0, 0, -5.5)),
               box(-cw / 2 - 4.0, -cw / 2 - 0.4, ch / 2 - 2.0, ch / 2 + 4.0, -3.0, e["front_projection"] + ct),     # hinge lugs outside the cover
               box(cw / 2 + 0.4, cw / 2 + 4.0, ch / 2 - 2.0, ch / 2 + 4.0, -3.0, e["front_projection"] + ct),
               box(-8.0, 8.0, -ch / 2 - 1.0, -ch / 2 + 9.0, -14.0, -2.0))                                         # cover-switch pocket block
    c = fuse(cyl(e["body_d"] / 2 - 2 + 0.15, 40, (0, 0, -30)), cyl(e["body_d"] / 2 + 3.0, 12.0, (0, 0, -0.5)),
             cyl(1.1, cw + 10, (-cw / 2 - 5, ch / 2 + 1.0, e["front_projection"] + ct - 3.0), (1, 0, 0)),
             box(-6.8, 6.8, -ch / 2 + 1.2, -ch / 2 + 6.6, -15.0, -5.0),                                           # D2HW pocket (plunger +z)
             cyl(1.6, 8.0, (0, -ch / 2 + 3.9, -6.0)))                                                              # push-pin bore
    return add, c, spot
