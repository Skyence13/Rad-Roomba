"""RR-X running gear and exterior fittings: printed wheel + TPU tyre on a purchased clamping hub, front cliff pod with
debris deflector, three-segment body bumper, transport tray, small sensor/control parts."""
from __future__ import annotations

import math

import cadquery as cq

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import dims as D
from . import sensors as S
from .structure import CLIFF_SCREWS
from .util import Part, box, cyl, fuse, mirror_y, place, prism, ring_xy

Z0, Z1 = D.PLATE_Z
WY = P.WHEEL_Y
TW = P.TYRE_WIDTH
RIM_R = P.WHEEL_R - D.TYRE_T
HUB = {"d": 25.4, "t": 9.2, "y0": 122.0, "bcd": 19.05, "n": 6}
# Pololu #1999: 25.4 dia x 9.2 thick, 6 mm bore, six M3 tapped holes, 6.8 g -- VERIFIED (pololu.com/product/1999/specs, 2026-11-26);
# bolt circle 19.05 mm UNVERIFIED (recalled; dimension diagram not opened) -> rim holes 3.6 mm give +-0.2 mm of BCD tolerance.
WEB_Y = (HUB["y0"] + HUB["t"], HUB["y0"] + HUB["t"] + 5.0)
N_KEYS = 8


def _keys(r0, r1, w=4.0):
    out = None
    for i in range(N_KEYS):
        k = box(-w / 2, w / 2, WY - TW / 2 + 3.0, WY + TW / 2 - 3.0, r0, r1).rotate((0, 0, 0), (0, 1, 0), 360.0 * i / N_KEYS)
        out = k if out is None else out.fuse(k)
    return out.translate((0, 0, P.AXLE_Z))


def wheel_rim(s):
    y0 = WY - TW / 2
    rim = cyl(RIM_R, TW, (0, y0, P.AXLE_Z), (0, 1, 0)).cut(cyl(RIM_R - 4.0, TW + 2, (0, y0 - 1, P.AXLE_Z), (0, 1, 0)))
    web = cyl(RIM_R - 3.0, WEB_Y[1] - WEB_Y[0], (0, WEB_Y[0], P.AXLE_Z), (0, 1, 0))
    rim = rim.fuse(web).fuse(_keys(RIM_R - 1.0, RIM_R + 1.5)).clean()
    rim = rim.cut(cyl(3.6, 12, (0, WEB_Y[0] - 1, P.AXLE_Z), (0, 1, 0)))
    for i in range(HUB["n"]):
        a = math.radians(30 + 360.0 / HUB["n"] * i)
        rim = rim.cut(cyl(1.8, 12, (HUB["bcd"] / 2 * math.cos(a), WEB_Y[0] - 1, P.AXLE_Z + HUB["bcd"] / 2 * math.sin(a)), (0, 1, 0)))
    for i in range(6):                                                    # lightening / wash-out holes
        a = math.radians(60 * i)
        rim = rim.cut(cyl(7.0, 12, (27.0 * math.cos(a), WEB_Y[0] - 1, P.AXLE_Z + 27.0 * math.sin(a)), (0, 1, 0)))
    return rim if s > 0 else mirror_y(rim)


def tyre(s):
    y0 = WY - TW / 2
    t = cyl(P.WHEEL_R, TW, (0, y0, P.AXLE_Z), (0, 1, 0)).cut(cyl(RIM_R, TW + 2, (0, y0 - 1, P.AXLE_Z), (0, 1, 0)))
    t = t.cut(_keys(RIM_R - 1.0, RIM_R + 1.7, 4.4))
    return t if s > 0 else mirror_y(t)


def hub(s):
    h = cyl(HUB["d"] / 2, HUB["t"], (0, HUB["y0"], P.AXLE_Z), (0, 1, 0))
    h = h.cut(cyl(3.0, 20, (0, HUB["y0"] - 1, P.AXLE_Z), (0, 1, 0)))
    return h if s > 0 else mirror_y(h)


def cliff_pod(s):
    """Bezel under the horn end with the ToF collar through the plate window, plus the debris deflector ahead of the tyre."""
    t = P.TOF_SENSORS["tof_cliff_fl"]
    x, y, z = t["xyz"]
    e = L.env("tof_board")
    xb = D.RX_FLANGE_X[0] - 0.5                                            # stops 0.5 mm short of the receiver x-stop flange
    bez = box(26.0, xb, 100.0, D.BEAM_HALF_Y, z, Z0)
    collar = box(x - 10.5, x + 10.5, y - 8.5, y + 8.5, Z0, Z1 + 1.5)
    ym = P.WHEEL_Y + P.TYRE_WIDTH / 2 - 0.5                               # deflector stays inside the 295 mm tyre width
    arm = box(53.0, 59.0, 104.0, ym, 25.0, Z0)
    blade = prism([(55.0, 119.6), (59.0, 119.6), (57.0, ym), (53.0, ym)], 8.0, Z0)
    lugs = fuse(*[box(cx - 4.0, min(cx + 4.0, xb), cy - 4.0, min(cy + 4.0, D.BEAM_HALF_Y), Z0 - 7.0, Z0) for cx, cy in CLIFF_SCREWS])
    p = fuse(bez, collar, arm, blade, lugs)
    p = p.cut(box(x - e["l"] / 2 - 0.25, x + e["l"] / 2 + 0.25, y - e["w"] / 2 - 0.25, y + e["w"] / 2 + 0.25, z + 2.6, Z1 + 3))    # board pocket (long axis x)
    p = p.cut(box(x - S.TOF_AP[0] / 2, x + S.TOF_AP[0] / 2, y - S.TOF_AP[1] / 2, y + S.TOF_AP[1] / 2, z - 1, z + 3))
    p = p.cut(box(x - S.TOF_WIN[0] / 2 - 0.15, x + S.TOF_WIN[0] / 2 + 0.15, y - S.TOF_WIN[1] / 2 - 0.15, y + S.TOF_WIN[1] / 2 + 0.15, z - 1, z + 1.1))
    for cx, cy in CLIFF_SCREWS:
        p = p.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (cx, cy, Z0 - D.INSERT["M3"][1])))
    return p if s > 0 else mirror_y(p)


# ----------------------------------------------------------------------------------------------- bumper
BUMP_IN, BUMP_OUT, WING_OUT = 9.5, 15.0, 18.5
BUMP_FRONT_X = -228.0          # side segments end behind the charge-inlet cover (x -224..-186 incl. its finger tab)


def _band(d_in, d_out, z0=None, z1=None):
    z0 = D.BUMPER_Z[0] if z0 is None else z0
    z1 = D.BUMPER_Z[1] if z1 is None else z1
    z, t, n, b = P._interp_row(P.BODY_ROWS["upper_outer"], 66.8)
    return prism(ring_xy((z, t - d_out, n + d_out, b + d_out)), z0, z1).cut(prism(ring_xy((z, t - d_in, n + d_in, b + d_in)), z0 - 1, z1 + 1))


def bumper_side(s):
    seg = _band(BUMP_IN, BUMP_OUT).intersect(box(-400, BUMP_FRONT_X, 61.5, 200, 0, 200))
    sw = P.BODY_BUMPER_SWITCHES["bumper_sw_l"]
    d = D.BUMPER_DIR["L"]
    n = (-d[0], -d[1], 0.0)
    for off in (-14.0, 14.0):                                             # guide-pin bosses (M4 inserts), pins slide in the skin bushings
        seg = seg.fuse(place(cyl(4.5, BUMP_OUT - BUMP_IN + 2.5, (off, 0, BUMP_IN - 1.0)), sw, n))
    seg = seg.fuse(place(cyl(3.5, BUMP_OUT - BUMP_IN + 2.5, (0, 0, BUMP_IN - 1.0)), sw, n)).clean()     # actuator boss (carries the sprung push pin)
    seg = seg.intersect(_band(BUMP_IN - 1.0, BUMP_OUT))
    for off in (-14.0, 14.0):
        seg = seg.cut(place(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (off, 0, BUMP_IN - 1.1)), sw, n))
    seg = seg.cut(place(cyl(1.6, 6.0, (0, 0, BUMP_IN - 1.1)), sw, n))
    seg = seg.intersect(box(-400, 0, 0, P.WHEEL_Y + P.TYRE_WIDTH / 2 - 0.5, 0, 200))     # stays inside the 295 mm tyre width
    return seg if s > 0 else mirror_y(seg)


def bumper_centre():
    seg = _band(BUMP_IN, BUMP_OUT).intersect(box(-400, -200.0, -59.5, 59.5, 0, 200))
    wings = _band(BUMP_OUT + 0.6, WING_OUT).intersect(box(-400, -200.0, -84.0, 84.0, 0, 200)).cut(box(-400, 0, -52.0, 52.0, 0, 200))
    link = _band(BUMP_IN, WING_OUT).intersect(box(-400, -200.0, -59.5, 59.5, 0, 200)).cut(box(-400, 0, -52.0, 52.0, 0, 200))
    seg = fuse(seg, wings, link)
    for y in (-30.0, 30.0):
        seg = seg.fuse(cyl(4.5, BUMP_OUT - BUMP_IN + 0.5, (P.BODY_TAIL_X - BUMP_OUT + 0.5, y, 66.0), (1, 0, 0)))
    seg = seg.clean()
    for y in (-30.0, 30.0):
        seg = seg.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (P.BODY_TAIL_X - BUMP_IN + 1.1, y, 66.0), (-1, 0, 0)))
    return seg


# ----------------------------------------------------------------------------------------------- transport tray
TRAY = {"x": (-305.0, 255.0), "half_y": 212.0, "t": 9.0}


def tray_base():
    b = box(TRAY["x"][0], TRAY["x"][1], -TRAY["half_y"], TRAY["half_y"], -TRAY["t"], 0.0)
    for x in (-270.0, 70.0):
        for y in (-185.0, 185.0):
            b = b.cut(cq.Workplane("XY", origin=(x, y, -TRAY["t"] - 1)).slot2D(60, 25, 90).extrude(TRAY["t"] + 2).val())      # hand slots / strap slots
    return b


def tray_chock(s):
    c = box(-46.0, 46.0, WY - 17.0, WY + 17.0, 0.0, 16.0).cut(cyl(P.WHEEL_R + 0.5, 40, (0, WY - 20, P.AXLE_Z), (0, 1, 0)))
    c = c.fuse(box(-46.0, 46.0, WY + 14.0, WY + 17.0, 0.0, 30.0)).clean()
    for x in (-38.0, 38.0):
        c = c.cut(cyl(2.3, 20, (x, WY, -1)))
    return c if s > 0 else mirror_y(c)


def tray_caster_cup():
    cx, cy = P.CASTER_SWIVEL
    c = cyl(34.0, 10.0, (cx, cy, 0)).cut(cyl(26.0, 12, (cx, cy, 2.0)))
    for a in (0, 120, 240):
        c = c.cut(cyl(2.3, 6, (cx + 30 * math.cos(math.radians(a)), cy + 30 * math.sin(math.radians(a)), -1)))
    return c


def tray_head_guard(s):
    he = P.HEAD_ENV_E
    x1, hy = D.HEAD_X1 + 4.0, he["y"][1] + 4.0
    g = fuse(box(x1, x1 + 8.0, hy - 110.0, hy + 8.0, 0, 55.0), box(x1 - 115.0, x1 + 8.0, hy, hy + 8.0, 0, 55.0),
             box(x1 - 115.0, x1 + 8.0, hy - 6.0, hy + 26.0, 0, 4.0), box(x1 - 18.0, x1 + 26.0, hy - 110.0, hy + 8.0, 0, 4.0)).cut(
        box(x1 - 115.0, x1, hy - 110.0, hy, 0.6, 60.0))
    for x, y in ((x1 + 18.0, hy - 90.0), (x1 + 18.0, hy - 10.0), (x1 - 100.0, hy + 18.0), (x1 - 30.0, hy + 18.0)):
        g = g.cut(cyl(2.3, 8, (x, y, -1)))
    return g if s > 0 else mirror_y(g)


# ----------------------------------------------------------------------------------------------- build
def build(add):
    PA, ASA, TPU = D.MAT["PAHT-CF"]["color"], D.MAT["ASA"]["color"], D.MAT["TPU95A"]["color"]
    for tag, s in (("L", 1), ("R", -1)):
        add(Part("RRX-P30", f"wheel_rim_{tag}", wheel_rim(s), "printed", "PAHT-CF", "wheel", color="#4a5258", internal=False, orient=(-90 if s > 0 else 90, 0, 0),
                 print_note="outboard face on the bed, axis vertical; no supports (web bridges 8 holes)", mates={f"tyre_{tag}", f"wheel_hub_{tag}", f"motor_{tag}"}))
        add(Part("RRX-P31", f"tyre_{tag}", tyre(s), "printed", "TPU95A", "wheel", color=TPU, internal=False, orient=(-90 if s > 0 else 90, 0, 0),
                 print_note="axis vertical; 4 walls, 20 % gyroid; print slow and dry", mates={f"wheel_rim_{tag}"}))
        add(Part("RRX-H20", f"wheel_hub_{tag}", hub(s), "purchased", "AL6061", "wheel", color="#c9a24a", internal=False,
                 mpn="Pololu #1999 universal aluminium mounting hub, 6 mm shaft, M3 holes (2-pack)", verified="VERIFIED 25.4 x 9.2, 6 x M3, 6.8 g (pololu.com specs); bolt circle 19.05 UNVERIFIED", mass=0.0068,
                 mates={f"wheel_rim_{tag}", f"motor_{tag}"}))
        add(Part(f"RRX-P32{tag}", f"cliff_pod_{tag}", cliff_pod(s), "printed", "PAHT-CF", "front_sensors", color=PA, internal=False, orient=(180, 0, 0),
                 print_note="plate face on the bed (upside-down); supports under the bezel step only", mates={"chassis_plate", f"tof_cliff_f{tag.lower()}", f"receiver_channel_{tag}"}))
        add(Part(f"RRX-P33{tag}", f"bumper_side_{tag}", bumper_side(s), "printed", "ASA", "bumper", color="#22262a", internal=False, orient=(0, 0, 0),
                 print_note="as fitted (band edge on the bed); bosses need small supports", mates={f"rear_deck_{tag}", "bumper_centre", f"bumper_sw_{tag.lower()}"}))
        add(Part(f"RRX-P40{tag}", f"tray_chock_{tag}", tray_chock(s), "printed", "ASA", "tray", color="#6b767c", hard=False, internal=False, orient=(0, 0, 0), print_note="flat"))
        add(Part(f"RRX-P41{tag}", f"tray_head_guard_{tag}", tray_head_guard(s), "printed", "ASA", "tray", color="#6b767c", hard=False, internal=False, orient=(0, 0, 0), print_note="flat, no supports"))
    add(Part("RRX-P34", "bumper_centre", bumper_centre(), "printed", "ASA", "bumper", color="#22262a", internal=False, orient=(0, 0, 0),
             print_note="as fitted; no supports", mates={"hatch_door", "bumper_side_L", "bumper_side_R"}))
    add(Part("RRX-F20", "tray_base", tray_base(), "fabricated", "PLY", "tray", color="#c8b48a", hard=False, internal=False, note="9 mm birch plywood or HDPE, 560 x 424, CNC/jigsaw; DXF"))
    add(Part("RRX-P42", "tray_caster_cup", tray_caster_cup(), "printed", "ASA", "tray", color="#6b767c", hard=False, internal=False, orient=(0, 0, 0), print_note="flat"))
    # small sensor / control parts
    pt, _ = S.panel_tray()
    add(Part("RRX-P50", "panel_tray", pt, "printed", "ASA", "controls", color=ASA, orient=(180, 0, 0), print_note="ears on the bed (upside-down)", mates={"RR-PANEL", "rear_deck_L"}))
    add(Part("RRX-P51", "cm5_tray", S.cm5_tray(), "printed", "ASA", "compute", color=ASA, orient=(0, 0, 0), print_note="base on the bed; deck bridges between the four legs (supports under the deck)",
             mates={"chassis_plate", "CM5_carrier_pcb", "battery_tunnel"}))
    ci = P.CHARGE_INLET
    xd = S.inlet_xdir()
    add(Part("RRX-P52", "inlet_cover", place(S.inlet_cover(), ci["xyz"], ci["normal"], xd), "printed", "ASA", "charge", color="#da9745", internal=False, orient=(180, 0, 0),
             local=S.inlet_cover(), print_note="lid face on the bed (upside-down); no supports", mates={"rear_deck_R", "charge_inlet"}))
    for name, t in P.TOF_SENSORS.items():
        front_cliff = name.startswith("tof_cliff_f")
        kind = S.seat_kind(name)
        xdir = (1.0, 0.0, 0.0) if front_cliff else S.seat_xdir(t["dir"], kind)
        if kind != "std":
            add(Part("RRX-P54", f"tof_clip_{name[4:]}", S.tof_clip(t["xyz"], t["dir"], kind), "printed", "ASA", "tof", color=ASA, orient=(0, 0, 0), internal=False,
                     local=S.tof_clip((0, 0, 0), (0, 0, 1), "look_r"), print_note="flat; 4 off (shallow look-ahead / look-behind seats)"))
        elif not front_cliff:
            add(Part("RRX-P53", f"tof_clip_{name[4:]}", S.tof_clip(t["xyz"], t["dir"]), "printed", "ASA", "tof", color=ASA, orient=(0, 0, 0), internal=False,
                     local=S.tof_clip((0, 0, 0), (0, 0, 1)), print_note="flat; 5 off"))
        add(Part("RRX-H30", f"tof_window_{name[4:]}", place(S._lbox(S.TOF_WIN[0], S.TOF_WIN[1], -S.TOF_WIN[2], 0.0), t["xyz"], t["dir"], xdir), "purchased", "PMMA", "tof", color="#3b1d1d",
                 internal=False, mpn="IR-pass PMMA 1.0 mm, laser cut 15 x 11 (e.g. Plexiglas IR acrylic 1146 class)", verified="UNVERIFIED material/supplier; >= 85 % at 940 nm assumed"))
