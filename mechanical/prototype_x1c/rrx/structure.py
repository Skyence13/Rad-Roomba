"""RR-X structure: fabricated chassis plate with the front beam, receiver channels (head datum), motor pods,
bridge tray, grip frame, caster mount, latch arm and front bulkhead.  All solids in base_link (assembled position)."""
from __future__ import annotations

import math

import cadquery as cq

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import dims as D
from .util import (Part, V, box, cut, cyl, fuse, loft, mirror_y, prism, prism_xz, ring_xy)

Z0, Z1 = D.PLATE_Z
RC = D.RC
SIDES = (("L", 1), ("R", -1))
RX_SCREWS = [(14.0, -17.0), (50.0, -17.0), (14.0, 17.0)]      # (x, dy from the channel centre; -dy = inboard)
RX_DOWELS = [(24.0, -17.0), (40.0, -17.0)]
CLIFF_SCREWS = [(30.5, 104.0), (30.5, 115.5), (54.5, 115.0)]       # rear pair + one ahead, all aft of the x-stop flange (x 59.7)


# ----------------------------------------------------------------------------------------------- plate holes
def plate_holes():
    """Every hole in the chassis plate: (x, y, d, kind, purpose). kind: thru | csk_bottom (countersunk from below) |
    tap | ream.  Generated from the same parameters as the parts that use them."""
    H = []
    for _, s in SIDES:
        yc = s * RC["shoe_y"]
        for x, dy in RX_SCREWS:                                    # receiver channel: 3 x M4 from above + 2 dowels
            H.append((x, yc + s * dy, D.CLEAR["M4"], "thru", "receiver channel M4 cap screw from above into the tapped ear"))
        for x, dy in RX_DOWELS:
            H.append((x, yc + s * dy, 4.0, "ream", "receiver locating dowel 4 m6 (plate hole 4 H7)"))
        for x in (-20.0, 20.0):                                    # motor pod feet, M4 countersunk from below into inserts
            for y in (D.POD_Y0 + 5.0, 112.0):
                H.append((x, s * y, D.CLEAR["M4"], "csk_bottom", "motor pod foot M4"))
        for x in (-48.0, -30.0):                                   # grip angle foot, through-bolted M5
            H.append((x, s * 71.0, D.CLEAR["M5"], "csk_bottom", "grip foot M5 through-bolt (proof-load path)"))
        H.append((46.0, s * 109.5, 0.0, "window 21.5x17.5", "front cliff ToF capsule collar"))
        for x, y in CLIFF_SCREWS:
            H.append((x, s * y, D.CLEAR["M3"], "thru", "cliff pod / deflector M3 (pan head from above into the pod insert)"))
        for x in (37.0, 47.0):
            H.append((x, s * 34.0, D.CLEAR["M5"], "csk_bottom", "latch arm pedestal M5 through-bolt"))
        H.append((-2.0, s * 80.0, 8.0, "thru", "grommet: dock switch / cliff ToF leads" if s > 0 else "grommet: cliff ToF lead"))
    for x, y in D.POSTS:
        H.append((x, y, D.CLEAR["M4"], "csk_bottom", "bridge post M4"))
    cx, cy = P.CASTER_SWIVEL
    for a in (45, 135, 225, 315):
        H.append((cx + 27.5 * math.cos(math.radians(a)), cy + 27.5 * math.sin(math.radians(a)), D.TAP["M3"], "tap", "caster disc M3"))
    for x in (-222.0, -190.0, -150.0, -110.0, -76.0):              # battery tunnel feet
        for s in (1, -1):
            H.append((x, s * 64.0, D.CLEAR["M3"], "csk_bottom", "battery tunnel foot M3"))
    for x, y in ((-140.0, 76.0), (-140.0, 88.0), (-83.0, 76.0), (-83.0, 88.0)):
        H.append((x, y, D.CLEAR["M3"], "csk_bottom", "CM5 tray M3"))
    for y in (-18.0, 18.0):
        H.append((34.5, y, D.TAP["M3"], "tap", "bus clamp resistor M3"))
    for x in (-60.0, -20.0):
        H.append((x, 0.0, D.CLEAR["M3"], "csk_bottom", "coupler cradle M3"))
    H.append((-215.0, 30.0, 3.0, "thru", "bay drain with duck-bill valve"))
    H.append((-215.0, -30.0, 3.0, "thru", "bay drain with duck-bill valve"))
    return H


def sole_screw_xy():
    """M3 screws from below through the plate edge into the lower-hull sole ring (insert in the hull)."""
    row = P.BODY_ROWS["lower_inner"][0]
    pts = []
    for deg in (62, 80, 100, 120, 140, 158, 172):
        x, y, _ = P.ring_point(row, math.radians(deg))
        cx = (row[1] + row[2]) / 2
        r = math.hypot(x - cx, y)
        f = (r - D.PLATE_INSET - 6.0) / r
        pts.append((cx + (x - cx) * f, y * f))
    return pts + [(x, -y) for x, y in pts]


def plate_outline(inset=D.PLATE_INSET, n=96):
    row = P.BODY_ROWS["lower_inner"][0]
    cx = (row[1] + row[2]) / 2
    pts = []
    for i in range(n):
        x, y, _ = P.ring_point(row, 2 * math.pi * i / n)
        r = math.hypot(x - cx, y)
        f = max(0.0, (r - inset) / r) if r > 0 else 0
        pts.append((cx + (x - cx) * f, y * f))
    return pts


def plate_blank(grow=0.0, z0=Z0, z1=Z1):
    """Plan form of the plate (optionally grown, for pockets in the printed hull)."""
    body = prism(plate_outline(D.PLATE_INSET - grow), z0, z1)
    beam = box(D.BEAM_X[0] - grow, D.BEAM_X[1] + grow, -D.BEAM_HALF_Y - grow, D.BEAM_HALF_Y + grow, z0, z1)
    s = body.fuse(beam).cut(box(D.BEAM_X[1] + grow, 300, -300, 300, z0 - 1, z1 + 1))
    return s.clean()


def chassis_plate():
    s = plate_blank()
    cx, cy = P.CASTER_SWIVEL
    s = s.cut(cyl(D.CASTER_HOLE_R, 10, (cx, cy, Z0 - 1)))
    x0, x1, hy = D.BAY_WINDOW
    win = cq.Workplane("XY", origin=((x0 + x1) / 2, 0, Z0 - 1)).rect(x1 - x0, 2 * hy).extrude(6).edges("|Z").fillet(6).val()
    s = s.cut(win)
    for (x, y, d, kind, _) in plate_holes() + [(x, y, D.CLEAR["M3"], "csk_bottom", "hull sole") for x, y in sole_screw_xy()]:
        if kind.startswith("window"):
            s = s.cut(box(x - 10.75, x + 10.75, y - 8.75, y + 8.75, Z0 - 1, Z1 + 1))
            continue
        s = s.cut(cyl(d / 2, 6, (x, y, Z0 - 1)))
        if kind == "csk_bottom":
            m = min(D.CSK, key=lambda k: abs(D.CLEAR[k] - d))
            s = s.cut(cq.Solid.makeCone(D.CSK[m] / 2, d / 2, (D.CSK[m] - d) / 2, V(x, y, Z0)))
    return s


# ----------------------------------------------------------------------------------------------- receiver
def receiver_channel(s):
    """Machined 6061 channel: inverted-U slot, y/z fit pads at the two land stations, dowel-pin z lands, x-stop flange.
    s = +1 left (fitted in y), -1 right (floating)."""
    yc = s * RC["shoe_y"]
    x0, x1 = RC["channel_x"]
    zb, zt = RC["channel_z"]
    w = RC["channel_width"] / 2
    sz0, sz1 = RC["shoe_z"]
    hw = RC["shoe_width"] / 2
    blk = box(x0, x1, yc - w, yc + w, zb, zt)
    fx0, fx1 = D.RX_FLANGE_X
    flange = box(fx0, fx1, yc - hw - 0.5 - D.RX_PAD[0] - 1.0, yc + hw + 0.5 + D.RX_PAD[0] + 1.0, zb, zt)   # x-stop pads each side of the shoe
    ears = fuse(box(8.0, 56.0, yc - s * 21.0, yc - s * 11.0, zt - 6.0, zt),            # inboard ear, full length
                box(8.0, 24.0, yc + s * 11.0, yc + s * 21.0, zt - 6.0, zt))             # outboard ear, short (cliff pod ahead of it)
    blk = fuse(blk, flange, ears)
    c = D.RX_SLOT_CLEAR
    slot = box(x0 + 1.5, fx1 + 1, yc - hw - c, yc + hw + c, zb - 1, sz1 + c)     # open underneath and to the front
    blk = blk.cut(slot)
    fit_y = D.RX_FIT_Y_LEFT if s > 0 else D.RX_FLOAT_Y_RIGHT
    for xs in RC["land_x"]:                                          # station pads left standing when the slot is milled
        a, b = xs - D.RX_STATION_LEN / 2, min(xs + D.RX_STATION_LEN / 2, fx1)
        blk = blk.fuse(box(a, b, yc - hw - c, yc - hw - fit_y, sz0 + 0.5, sz1 + c))      # y pads start 0.5 above datum C (no tangency with the pin bore)
        blk = blk.fuse(box(a, b, yc + hw + fit_y, yc + hw + c, sz0 + 0.5, sz1 + c))
        blk = blk.fuse(box(a, b, yc - hw - c, yc + hw + c, sz1 + D.RX_FIT_Z, sz1 + c))     # roof pad = hold-down
        blk = blk.cut(cyl(D.RX_LAND_PIN_D / 2, 2 * w + 2, (xs, yc - w - 1, sz0 - D.RX_LAND_PIN_D / 2), (0, 1, 0)))   # reamed 4 H7 cross hole
    blk = blk.clean()
    for x, dy in RX_SCREWS:
        blk = blk.cut(cyl(D.TAP["M4"] / 2, 7, (x, yc + s * dy, zt - 6.5)))
    for x, dy in RX_DOWELS:
        blk = blk.cut(cyl(2.0, 5, (x, yc + s * dy, zt - 4.0)))
    if s > 0:                                                         # push-pin bore for the HEAD_DOCK switch
        blk = blk.cut(cyl(1.6, 4, (x0 - 1, yc, P.HEAD_DOCK_SWITCH[2]), (1, 0, 0)))
    return blk


def land_pins(s):
    yc = s * RC["shoe_y"]
    w = RC["channel_width"] / 2
    return [cyl(D.RX_LAND_PIN_D / 2, 2 * w, (xs, yc - w, RC["shoe_z"][0] - D.RX_LAND_PIN_D / 2), (0, 1, 0)) for xs in RC["land_x"]]


def dock_switch_bracket():
    """Printed holder under the plate behind the left channel: D2HW pocket, push pin guided in the channel end wall."""
    x, y, z = P.HEAD_DOCK_SWITCH
    b = box(-13.0, 1.8, y - 9.0, y + 9.0, z - 7.0, Z0)
    b = b.cut(box(x - 4.0, x + 3.2, y - 6.8, y + 6.8, z - 2.8, z + 2.8))      # switch pocket (plunger towards +x)
    b = b.cut(cyl(1.7, 6, (x + 3.0, y, z), (1, 0, 0)))                       # plunger / push-pin passage
    b = b.cut(box(-13.5, x - 4.0, y - 2.5, y + 2.5, z - 2.0, z + 2.0))        # lead exit
    for dy in (-5.5, 5.5):
        b = b.cut(cyl(D.INSERT["M3"][0] / 2, 6, (-9.5, y + dy, Z0 - 6.0)))    # M3 inserts, screws from above through the plate
    return b


# ----------------------------------------------------------------------------------------------- drive
def motor_pod(s):
    ax_z = P.MOTOR_AXIS_Z
    yf = P.MOTOR_FACE_Y
    r_o = P.DRIVE_POD["outer_r"]
    tube = cyl(r_o, yf + D.POD_FACE_T - D.POD_Y0, (0, D.POD_Y0, ax_z), (0, 1, 0))
    base = box(-26.0, 26.0, D.POD_Y0, yf + D.POD_FACE_T, Z1, Z1 + 9.0)
    web = box(-r_o, r_o, D.POD_Y0, yf + D.POD_FACE_T, Z1, ax_z)
    pod = fuse(tube, base, web).cut(box(-30.0, 30.0, D.POD_Y0 - 1, 130.0, Z0 - 5, Z1))   # tube bottom (z 35.5) trimmed to the plate top
    pod = pod.cut(cyl(D.POD_BORE_R, yf - D.POD_Y0 + 1, (0, D.POD_Y0 - 1, ax_z), (0, 1, 0)))
    e = L.env("motor")
    pod = pod.cut(cyl(e["boss_d"] / 2 + 0.5, 10, (0, yf - 1, P.AXLE_Z), (0, 1, 0)))        # shaft boss, 7 mm below the can axis
    for i in range(12):                                                                   # both clockings of the 6 x M3 pattern
        a = math.radians(30 * i)
        pod = pod.cut(cyl(D.CLEAR["M3"] / 2, 10, (D.MOTOR_BCD / 2 * math.cos(a), yf - 1, ax_z + D.MOTOR_BCD / 2 * math.sin(a)), (0, 1, 0)))
    for x in (-20.0, 20.0):
        for y in (D.POD_Y0 + 5.0, 112.0):
            pod = pod.cut(cyl(D.INSERT["M4"][0] / 2, D.INSERT["M4"][1], (x, y, Z1)))
    pod = pod.cut(box(-4.0, 4.0, D.POD_Y0 - 1, D.POD_Y0 + 6.0, ax_z + D.POD_BORE_R - 1, ax_z + r_o + 1))   # encoder-lead notch
    return pod if s > 0 else mirror_y(pod)


def screw_ring(s):
    """1 mm stainless load-spreading ring under the six motor screws."""
    yf = P.MOTOR_FACE_Y + D.POD_FACE_T
    ring = cyl(19.5, 1.0, (0, yf, P.MOTOR_AXIS_Z), (0, 1, 0)).cut(cyl(11.0, 3, (0, yf - 1, P.MOTOR_AXIS_Z), (0, 1, 0)))
    ring = ring.cut(cyl(L.env("motor")["boss_d"] / 2 + 1.0, 3, (0, yf - 1, P.AXLE_Z), (0, 1, 0)))
    for i in range(12):
        a = math.radians(30 * i)
        ring = ring.cut(cyl(D.CLEAR["M3"] / 2, 3, (D.MOTOR_BCD / 2 * math.cos(a), yf - 1, P.MOTOR_AXIS_Z + D.MOTOR_BCD / 2 * math.sin(a)), (0, 1, 0)))
    return ring if s > 0 else mirror_y(ring)


# ----------------------------------------------------------------------------------------------- bridge
def bridge_tray():
    bz = P.ELECTRONICS_BRIDGE_Z
    ex0, ex1 = P.ELECTRONICS_BRIDGE_X
    hy = P.SADDLE["half_y"]
    t = box(ex0, ex1, -hy, hy, *bz)
    for x, y in D.POSTS:
        t = t.cut(cyl(D.CLEAR["M4"] / 2, 4, (x, y, bz[0] - 1)))
    b = P.CHS_MAIN
    for u, v in b["holes_uv"]:
        px, py, _ = P.board_to_base(b["origin"], u, v)
        t = t.cut(cyl(D.CLEAR["M3"] / 2, 4, (px, py, bz[0] - 1)))
    for y in (-60.0, 60.0):                                       # harness pass-throughs under the board edges
        t = t.cut(box(ex0 + 14, ex0 + 30, y - 6, y + 6, bz[0] - 1, bz[1] + 1))
    return t


def bridge_post(x, y):
    return cyl(4.0, P.ELECTRONICS_BRIDGE_Z[0] - Z1, (x, y, Z1)).cut(cyl(D.TAP["M4"] / 2, 60, (x, y, Z1 - 1)))


def board_standoff(u, v):
    b = P.CHS_MAIN
    px, py, _ = P.board_to_base(b["origin"], u, v)
    z = P.ELECTRONICS_BRIDGE_Z[1]
    return cyl(2.75, b["origin"][2] - z, (px, py, z))


# ----------------------------------------------------------------------------------------------- grip frame
def grip_side_plate(s):
    """6 mm 6061 laser-cut side plate: foot, leg behind the motor, cheek. Flat part (profile in x-z)."""
    G = P.GRIP
    top = G["bar_top_z"]
    pts = [(D.FOOT_X[0], Z1), (D.FOOT_X[1], Z1), (D.FOOT_X[1], 78.0), (-1.0, 104.0), (-1.0, 146.0), (-7.0, 150.0), (-7.0, top - 1.0),
           (-21.0, top - 1.0), (-21.0, 112.0), (-31.0, 98.0), (-31.0, Z1 + 26.0), (D.FOOT_X[0], Z1 + 26.0)]
    y0, y1 = D.GRIP_PLATE_Y
    pl = prism_xz(pts, y0, y1)
    pl = pl.cut(cyl(D.CLEAR["M8"] / 2, 10, (D.GRIP_TUBE_X, y0 - 1, D.GRIP_TUBE_Z), (0, 1, 0)))
    for x in (-48.0, -30.0):
        pl = pl.cut(cyl(D.CLEAR["M5"] / 2, 10, (x, y0 - 1, Z1 + 16.0), (0, 1, 0)))
    for z in (118.0, 140.0):
        pl = pl.cut(cyl(D.CLEAR["M3"] / 2, 10, (-11.0, y0 - 1, z), (0, 1, 0)))
    return pl if s > 0 else mirror_y(pl)


def grip_foot(s):
    """25 x 25 x 3 aluminium angle, 34 long: horizontal leg through-bolted to the plate, vertical leg to the side plate."""
    y1 = D.GRIP_PLATE_Y[0]
    a = fuse(box(D.FOOT_X[0], D.FOOT_X[1], y1 - 25.0, y1, Z1, Z1 + 3.0), box(D.FOOT_X[0], D.FOOT_X[1], y1 - 3.0, y1, Z1, Z1 + 25.0))
    for x in (-48.0, -30.0):
        a = a.cut(cyl(D.CLEAR["M5"] / 2, 6, (x, 71.0, Z1 - 1)))
        a = a.cut(cyl(D.CLEAR["M5"] / 2, 6, (x, y1 - 4, Z1 + 16.0), (0, 1, 0)))
    return a if s > 0 else mirror_y(a)


def grip_tube():
    od, t = D.GRIP_TUBE
    y = D.GRIP_PLATE_Y[0]
    return cyl(od / 2, 2 * y, (D.GRIP_TUBE_X, -y, D.GRIP_TUBE_Z), (0, 1, 0)).cut(cyl(od / 2 - t, 2 * y + 2, (D.GRIP_TUBE_X, -y - 1, D.GRIP_TUBE_Z), (0, 1, 0)))


def grip_tie_rod():
    y = D.GRIP_PLATE_Y[1] + 9.0
    return cyl(4.0, 2 * y, (D.GRIP_TUBE_X, -y, D.GRIP_TUBE_Z), (0, 1, 0))


def grip_sleeve():
    """Printed hand sleeve 25 x 22 over the tube between the cheek fairings."""
    G = P.GRIP
    x0, x1 = G["center_x"] - G["bar_x"] / 2, G["center_x"] + G["bar_x"] / 2
    hy = G["half_span_y"] - 0.5
    sl = cq.Workplane("XZ", origin=((x0 + x1) / 2, hy, D.GRIP_TUBE_Z)).rect(G["bar_x"], G["bar_z"]).extrude(2 * hy).edges("|Y").fillet(8.0).val()
    return sl.cut(cyl(D.GRIP_TUBE[0] / 2 + 0.2, 2 * hy + 2, (D.GRIP_TUBE_X, -hy - 1, D.GRIP_TUBE_Z), (0, 1, 0)))


def cheek_fairing(s):
    """Printed fairing over the side plate above the shoulder; carries the look-ahead ToF capsule seat on its front face."""
    G = P.GRIP
    y0, y1 = G["cheek_y"]
    x0, x1 = G["center_x"] - G["bar_x"] / 2, G["center_x"] + G["bar_x"] / 2
    zb = 109.0
    f = cq.Workplane("XY").add(box(x0, x1, y0, y1, zb, G["bar_top_z"] + 2.0)).edges("|Z").fillet(3.0).val()
    t = P.TOF_SENSORS["tof_look_fl"]
    d = (t["dir"][0], t["dir"][1], t["dir"][2])
    from .sensors import tof_boss, tof_pocket
    f = f.fuse(tof_boss((t["xyz"][0], t["xyz"][1], t["xyz"][2]), d)).clean()
    f = f.cut(box(-21.4, -0.6, D.GRIP_PLATE_Y[0] - 0.3, D.GRIP_PLATE_Y[1] + 0.3, zb - 1, 147.0))       # slot for the plate cheek
    f = f.cut(box(-21.4, -6.6, D.GRIP_PLATE_Y[0] - 0.3, D.GRIP_PLATE_Y[1] + 0.3, 146.0, G["bar_top_z"] - 0.6))
    f = f.cut(cyl(D.GRIP_TUBE[0] / 2 + 0.3, 6, (D.GRIP_TUBE_X, y0 - 1, D.GRIP_TUBE_Z), (0, 1, 0)))        # tube enters the inner wall
    f = f.cut(cyl(8.0, 5, (D.GRIP_TUBE_X, y1 - 3.5, D.GRIP_TUBE_Z), (0, 1, 0)))                           # nut pocket (cap plug)
    f = f.cut(cyl(D.CLEAR["M8"] / 2, 20, (D.GRIP_TUBE_X, y0, D.GRIP_TUBE_Z), (0, 1, 0)))
    for z in (118.0, 140.0):
        f = f.cut(cyl(D.CLEAR["M3"] / 2, 20, (-11.0, y0 - 1, z), (0, 1, 0)))
        f = f.cut(cyl(3.2, 2.2, (-11.0, y1 - 2.0, z), (0, 1, 0)))
    f = f.cut(tof_pocket((t["xyz"][0], t["xyz"][1], t["xyz"][2]), d))
    f = f.cut(box(-6.0, -1.5, y0 + 2.5, y1 - 2.5, 112.0, 152.0))                                          # ToF lead channel down the front
    return f if s > 0 else mirror_y(f)


# ----------------------------------------------------------------------------------------------- caster, latch
def caster_disc():
    cx, cy = P.CASTER_SWIVEL
    d = cyl(30.5, 2.5, (cx, cy, Z1))
    e = L.env("caster")
    for sx in (-1, 1):
        for sy in (-1, 1):
            d = d.cut(cyl(D.TAP["M4"] / 2 if False else 1.65, 4, (cx + sx * e["plate_holes"][0] / 2, cy + sy * e["plate_holes"][1] / 2, Z1 - 1)))
    for a in (45, 135, 225, 315):
        d = d.cut(cyl(D.CLEAR["M3"] / 2, 4, (cx + 27.5 * math.cos(math.radians(a)), cy + 27.5 * math.sin(math.radians(a)), Z1 - 1)))
    return d


def caster_shim():
    cx, cy = P.CASTER_SWIVEL
    return cyl(23.0, Z1 - P.CASTER_MOUNT_Z, (cx, cy, P.CASTER_MOUNT_Z)).cut(cyl(8.0, 3, (cx, cy, P.CASTER_MOUNT_Z - 1)))


LATCH_ARM_Z = (52.0, 56.0)


def latch_arm():
    """4 mm 6061 T-plate: carries the draw latch under the nose tip back to the front beam (latch reaction path)."""
    lb = RC["latch_box"]
    pts = [(33.0, -40.0), (51.0, -40.0), (60.0, -12.5), (lb[1] - 6.0, -12.5), (lb[1] - 6.0, 12.5), (60.0, 12.5), (51.0, 40.0), (33.0, 40.0)]
    a = prism(pts, *LATCH_ARM_Z)
    for x in (37.0, 47.0):
        for y in (-34.0, 34.0):
            a = a.cut(cyl(D.TAP["M5"] / 2, 6, (x, y, LATCH_ARM_Z[0] - 1)))
    for x in (lb[0] + 3.0, lb[1] - 11.0):
        for y in (-7.0, 7.0):
            a = a.cut(cyl(D.TAP["M4"] / 2, 6, (x, y, LATCH_ARM_Z[0] - 1)))
    return a


def front_bulkhead():
    """Printed wall closing the hull mouth at the chin cut, with the two pedestals that carry the latch arm."""
    xc = RC["chin_cut"][0]
    lo = loft(P.BODY_ROWS["lower_outer"])
    wall = box(xc - 4.0, xc, -120, 120, Z1, LATCH_ARM_Z[0]).intersect(lo)
    out = wall
    for s in (1, -1):
        ped = box(33.0, 51.0, s * 28.0, s * 40.0, Z1, LATCH_ARM_Z[0])
        rib = box(51.0, xc - 4.0, s * 28.0, s * 32.0, Z1, LATCH_ARM_Z[0])
        out = out.fuse(ped).fuse(rib)
        for x in (37.0, 47.0):
            out = out.cut(cyl(D.CLEAR["M5"] / 2, 30, (x, s * 34.0, Z1 - 1)))
    out = out.clean()
    for y in (-50.0, 0.0, 50.0):
        pass
    return out


# ----------------------------------------------------------------------------------------------- assembly of this module
def build(add):
    AL = D.MAT["AL6061"]["color"]
    add(Part("RRX-F01", "chassis_plate", chassis_plate(), "fabricated", "AL6061", "chassis", color=AL, internal=False,
             note="4 mm 6061-T6 laser/waterjet blank, countersunk and tapped per holes table; DXF in out/dxf", mates={"*"}))
    for tag, s in SIDES:
        add(Part(f"RRX-F02{tag}", f"receiver_channel_{tag}", receiver_channel(s), "fabricated", "AL6061", "receiver", color=AL, internal=False,
                 note="machined 6061 (printed PAHT-CF copy RRX-P02x for fit check only)", mates={"chassis_plate", f"land_pin_{tag}", "dock_switch_bracket", f"head_shoe_{tag}"}))
        for i, pin in enumerate(land_pins(s)):
            add(Part("RRX-H01", f"land_pin_{tag}{i}", pin, "purchased", "STEEL", "receiver", color="#5d6166", internal=False,
                     mpn="ISO 8734 4 m6 x 24 hardened dowel pin", verified="standard part", mates={f"receiver_channel_{tag}", f"head_shoe_{tag}"}))
        add(Part(f"RRX-P01{tag}", f"motor_pod_{tag}", motor_pod(s), "printed", "PAHT-CF", "drive", color=D.MAT["PAHT-CF"]["color"], internal=False,
                 orient=(90 if s > 0 else -90, 0, 0), print_note="end face on the bed, tube axis vertical; no supports",
                 mates={"chassis_plate", f"motor_{tag}", f"screw_ring_{tag}"}))
        add(Part("RRX-F03", f"screw_ring_{tag}", screw_ring(s), "fabricated", "SS304", "drive", color=D.MAT["SS304"]["color"], internal=False,
                 note="1 mm 304 laser-cut ring", mates={f"motor_pod_{tag}", f"motor_{tag}"}))
        add(Part("RRX-F05", f"grip_side_plate_{tag}", grip_side_plate(s), "fabricated", "AL6061", "grip", color=AL, internal=False,
                 note="6 mm 6061-T6 laser cut; same blank both sides", mates={f"grip_foot_{tag}", "grip_tube", "grip_tie_rod", f"cheek_fairing_{tag}", "chassis_plate"}))
        add(Part("RRX-F06", f"grip_foot_{tag}", grip_foot(s), "fabricated", "AL6061", "grip", color=AL,
                 note="25 x 25 x 3 6060 angle cut to 34 mm, 4 holes", mates={f"grip_side_plate_{tag}", "chassis_plate"}))
        add(Part(f"RRX-P03{tag}", f"cheek_fairing_{tag}", cheek_fairing(s), "printed", "ASA", "grip", color=D.MAT["ASA"]["color"], internal=False,
                 orient=(0, 0, 0), print_note="upright as fitted; supports only under the ToF nose",
                 mates={f"grip_side_plate_{tag}", "grip_tube", "grip_tie_rod", "grip_sleeve", f"tof_look_f{tag.lower()}"}))
    add(Part("RRX-P04", "dock_switch_bracket", dock_switch_bracket(), "printed", "PAHT-CF", "receiver", color=D.MAT["PAHT-CF"]["color"], internal=False,
             orient=(180, 0, 0), print_note="plate face on the bed", mates={"chassis_plate", "receiver_channel_L", "head_dock_switch"}))
    add(Part("RRX-F04", "bridge_tray", bridge_tray(), "fabricated", "AL5052", "bridge", color=AL, note="2 mm 5052 laser cut; gap pad zone u 50..110, v 30..70",
             mates={"RR-CHS-MAIN_bottom_parts", "*post*", "*standoff*"}))
    for i, (x, y) in enumerate(D.POSTS):
        add(Part("RRX-F07", f"bridge_post_{i}", bridge_post(x, y), "fabricated", "AL6061", "bridge", color=AL, note="8 mm round bar x 41, M4 tapped both ends",
                 mates={"bridge_tray", "chassis_plate"}))
    for i, (u, v) in enumerate(P.CHS_MAIN["holes_uv"]):
        add(Part("RRX-H02", f"board_standoff_{i}", board_standoff(u, v), "purchased", "AL6061", "bridge", color="#c9a24a", mpn="M3 x 3 mm round spacer + M3x10 screw + nyloc nut under the tray",
                 verified="standard part", mates={"bridge_tray", "RR-CHS-MAIN_pcb", "RR-CHS-MAIN_bottom_parts"}))
    add(Part("RRX-F08", "grip_tube", grip_tube(), "fabricated", "AL6061", "grip", color=AL, internal=False, note="16 x 2 6060 tube cut to 176 mm",
             mates={"grip_side_plate_L", "grip_side_plate_R", "grip_tie_rod", "grip_sleeve", "cheek_fairing_L", "cheek_fairing_R"}))
    add(Part("RRX-H03", "grip_tie_rod", grip_tie_rod(), "purchased", "SS304", "grip", color=D.MAT["SS304"]["color"], internal=False, mpn="M8 A2 threaded rod 206 mm + 2 nyloc nuts + 2 washers",
             verified="standard part", mates={"grip_tube", "grip_side_plate_L", "grip_side_plate_R", "cheek_fairing_L", "cheek_fairing_R", "grip_sleeve"}))
    add(Part("RRX-P05", "grip_sleeve", grip_sleeve(), "printed", "ASA", "grip", color="#394046", internal=False, orient=(90, 0, 0),
             print_note="standing on one end (166 mm tall), brim", mates={"grip_tube", "cheek_fairing_L", "cheek_fairing_R"}))
    add(Part("RRX-F09", "caster_disc", caster_disc(), "fabricated", "SS304", "caster", color=D.MAT["SS304"]["color"], note="2.5 mm 304 laser cut, 4 x M4 tapped",
             mates={"chassis_plate", "caster_shim", "caster"}, internal=False))
    add(Part("RRX-F10", "caster_shim", caster_shim(), "fabricated", "SS304", "caster", color=D.MAT["SS304"]["color"], note="1 mm 304 shim",
             mates={"caster_disc", "caster", "chassis_plate"}, internal=False))
    add(Part("RRX-F11", "latch_arm", latch_arm(), "fabricated", "AL6061", "receiver", color=AL, internal=False, note="4 mm 6061 laser cut, tapped M5 / M4",
             mates={"front_bulkhead", "nose_cowl", "head_latch"}))
    add(Part("RRX-P06", "front_bulkhead", front_bulkhead(), "printed", "PAHT-CF", "chassis", color=D.MAT["PAHT-CF"]["color"], internal=False, orient=(0, 0, 0),
             print_note="as fitted, plate face on the bed", mates={"chassis_plate", "latch_arm", "lower_hull_FL", "lower_hull_FR", "nose_cowl"}))
