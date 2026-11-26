"""RR-X battery bay: tunnel with guide walls, insulated floor plug (heater carrier), removable cassette with cam bail,
coupler carrier, 9 Ah spacer.  Interface values come from P.BATTERY_BAY (identical in both builds)."""
from __future__ import annotations

import cadquery as cq

from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import dims as D
from .util import Part, box, cyl, fuse, prism_xz

B = P.BATTERY_BAY
Z1 = D.PLATE_Z[1]
CX0, CX1 = B["cassette_x"]
CHY = B["cassette_half_y"]
CZ0, CZ1 = B["cassette_z"]
WALL = 2.5
RIB_Y = (44.0, 50.0)                 # floor ribs the cassette runs on (top z = cassette underside)
KEY_Y = (18.0, 22.0)                 # off-centre key rib on the cassette floor (left of centre)
FEET_X = (-222.0, -190.0, -150.0, -110.0, -76.0)
PLUG = (-170.0, -74.0, 42.0)         # flange of the floor plug on the plate top
EAR_Y = (44.0, 48.5)
ARM_Y = (49.2, 53.8)
PIVOT = (-236.0, 80.0)               # bail pivot on the cassette rear ears (x, z)
BAIL_PIN = (-239.0, 71.0)            # bail cam pin, latched position (9.5 mm from the pivot)
DOOR_PEG = (-237.0, 100.0)           # fixed pegs in the upper jambs the door hangs on
CAM_Y = (55.2, 57.5)                 # cam ears on the hatch frame, outside the cassette width
BAIL_LEN = 46.0


def tunnel():
    x0, x1 = D.TUNNEL_X
    wy0, wy1 = D.TUNNEL_WALL_Y
    t = box(x0, x1 + 3.0, -wy1, wy1, Z1, Z1 + 1.0)                                    # 1 mm floor skin on the plate
    for s in (1, -1):
        t = t.fuse(box(x0, x1, s * wy0, s * wy1, Z1, B["hump_z"][0]))                 # guide walls
        t = t.fuse(box(x0, x1 - 2.5, s * RIB_Y[0], s * RIB_Y[1], Z1, CZ0))            # floor ribs (drain underneath)
        for x in FEET_X:
            t = t.fuse(box(x - 5.0, x + 5.0, s * wy1, s * 69.0, Z1, Z1 + 8.0))        # feet with M3 inserts
        for z in (48.0, 92.0):
            t = t.fuse(box(x0, x0 + 9.0, s * wy1, s * 63.5, z - 4.5, z + 4.5))        # bosses for the hatch-frame screws
    t = t.fuse(box(x1, x1 + 3.0, -wy1, wy1, Z1, B["hump_z"][0]))                      # front bulkhead
    gate = box(x0, x0 + 4.0, -38.0, 38.0, Z1, CZ0 - 0.2).cut(box(x0 - 1, x0 + 5, KEY_Y[0] - 0.5, KEY_Y[1] + 0.5, Z1 + 1.0, CZ0))
    cradle = fuse(box(x1 + 3.0, B["coupler_x"][1], -24.0, 24.0, Z1, B["coupler_z"][0] - 0.3),
                  box(-60.0, -22.0, B["coupler_half_y"] + 0.4, 24.0, Z1, 56.0), box(-60.0, -22.0, -24.0, -B["coupler_half_y"] - 0.4, Z1, 56.0))
    t = fuse(t, gate, cradle)
    t = t.cut(box(x1 - 1, x1 + 4, -B["coupler_half_y"] - 1.5, B["coupler_half_y"] + 1.5, B["coupler_z"][0] - 1.0, B["coupler_z"][1] + 1.5))
    t = t.cut(box(PLUG[0] - 0.3, PLUG[1] + 0.3, -PLUG[2] - 0.3, PLUG[2] + 0.3, Z1 - 1, Z1 + 1.01))        # floor plug seat
    cx, cy = P.CASTER_SWIVEL
    t = t.cut(cyl(31.2, 3.0, (cx, cy, Z1 - 0.5)))                                                           # caster disc
    for s in (1, -1):
        for x in FEET_X:
            t = t.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x, s * 64.0, Z1)))
        for z in (48.0, 92.0):
            t = t.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x0, s * 59.5, z), (1, 0, 0)))
        t = t.cut(box(x1 - 14.0, x1 - 2.0, s * wy0 - 1, s * wy1 + 1 if s > 0 else s * wy1 - 1, 70.0, 82.0))  # pack-lead / NTC slot
        t = t.cut(cyl(1.5, 4, (-215.0, s * 30.0, Z1 - 1)))                                                   # drains
    for x in (-60.0, -20.0):
        t = t.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x, 0.0, Z1)))
    for x in (-52.0, -30.0):                                                                               # coupler cross-pin (M4) bores
        t = t.cut(cyl(D.CLEAR["M4"] / 2, 60, (x, -30.0, 53.0), (0, 1, 0)))
    return t


def floor_plug():
    """Insulating plug in the plate window: 4 mm body flush with the underside, 1 mm flange on the plate; carries the heater pad."""
    x0, x1, hy = D.BAY_WINDOW
    body = cq.Workplane("XY", origin=((x0 + x1) / 2, 0, D.PLATE_Z[0])).rect(x1 - x0 - 0.6, 2 * hy - 0.6).extrude(4.0).edges("|Z").fillet(5.7).val()
    return body.fuse(box(PLUG[0], PLUG[1], -PLUG[2], PLUG[2], Z1, Z1 + 1.0)).clean()


def cassette():
    c = box(CX0, CX1, -CHY, CHY, CZ0, CZ1)
    px0, px1 = B["pack_x"]
    c = c.cut(box(px0 - 0.0, px1 + 0.5, -CHY + WALL, CHY - WALL, B["pack_z"][0], CZ1 + 1))      # pack pocket, open top
    c = c.fuse(box(CX0, CX1, KEY_Y[0], KEY_Y[1], CZ0 - 1.3, CZ0))                               # key rib (interface)
    for s in (1, -1):
        ear = prism_xz([(CX0, PIVOT[1] - 20.0), (CX0 - 12.0, PIVOT[1] - 8.0), (CX0 - 12.0, PIVOT[1] + 8.0), (CX0, PIVOT[1] + 8.0)], EAR_Y[0], EAR_Y[1])
        ear = ear if s > 0 else ear.mirror("XZ")
        c = c.fuse(ear)
    for x in (px0 + 12.0, px1 - 12.0):                                                           # lid-screw bosses beside the terminals (+y)
        c = c.fuse(box(x - 4.5, x + 4.5, CHY - WALL - 5.5, CHY - WALL, CZ1 - 16.0, CZ1 - 2.5))
    c = c.clean()
    for x in (px0 + 12.0, px1 - 12.0):
        c = c.cut(cyl(D.INSERT["M3"][0] / 2, D.INSERT["M3"][1], (x, CHY - WALL - 2.6, CZ1 - 2.5 - D.INSERT["M3"][1])))
    c = c.cut(box(CX0 + 20.0, CX1 - 20.0, -CHY - 1, -CHY + WALL + 1, CZ1 - 6.0, CZ1 - 2.5))      # slot for the lid tongue (-y)
    c = c.cut(box(CX1 - WALL - 1, CX1 + 1, 24.0, 40.0, 60.0, 76.0))                              # lead exit to the coupler
    for s in (1, -1):
        c = c.cut(cyl(D.INSERT["M5"][0] / 2, 6.0, (PIVOT[0], s * EAR_Y[0] - (0 if s > 0 else 6.0), PIVOT[1]), (0, 1, 0)))
        for z in (48.0, 60.0):
            c = c.cut(cyl(D.INSERT["M3"][0] / 2, 4.0, (CX1 - 3.0, s * 12.0, z), (1, 0, 0)))       # coupler carrier screws
    return c


def cassette_lid():
    px0, px1 = B["pack_x"]
    lid = box(CX0 + WALL + 0.3, CX1 - WALL - 0.3, -CHY + WALL + 0.3, CHY - WALL - 0.3, CZ1 - 2.5, CZ1)
    lid = lid.fuse(box(CX0 + 21.0, CX1 - 21.0, -CHY + 0.4, -CHY + WALL + 1.5, CZ1 - 5.6, CZ1 - 2.4)).clean()
    for x in (px0 + 12.0, px1 - 12.0):
        lid = lid.cut(cyl(D.CLEAR["M3"] / 2, 5, (x, CHY - WALL - 2.6, CZ1 - 3.5)))
    return lid


def coupler_carrier():
    """Cassette-side coupler bracket: 2 shoulder screws in 2 mm oversize holes give the +-1 mm float."""
    cz0, cz1 = B["coupler_z"]
    b = box(CX1, CX1 + 4.0, -26.0, 26.0, cz0 - 2.0, cz1 + 2.0).cut(box(CX1 - 1, CX1 + 5, -B["coupler_half_y"] - 0.4, B["coupler_half_y"] + 0.4, cz0 - 0.4, cz1 + 0.4))
    for s in (1, -1):
        for z in (48.0, 60.0):
            b = b.cut(cyl(2.7, 6, (CX1 - 1, s * 23.0, z), (1, 0, 0)))
    return b


def bail():
    """Cam bail (ejector handle).  Folded UP = latched: the two cam pins sit at the bottom of the vertical slots of the
    hatch-frame cam ears.  Swinging the bar rearward/down by 90 deg lifts the pins 6 mm and jacks the cassette 12 mm
    rearward (coupler unmated); the pins then leave through the exit legs.  Bar 46 mm from the pivot -> >= 45 mm
    gloved finger gap when horizontal.  Nominal cam geometry: needs a fit-check print before the latch force is trusted."""
    px, pz = PIVOT
    out = None
    for s in (1, -1):
        arm = prism_xz([(px - 5.0, pz - 12.0), (px + 5.0, pz - 12.0), (px + 5.0, pz + BAIL_LEN + 4.0), (px - 5.0, pz + BAIL_LEN + 4.0)], ARM_Y[0], ARM_Y[1])
        arm = arm.cut(cyl(2.6, 8, (px, ARM_Y[0] - 1, pz), (0, 1, 0)))
        arm = arm.cut(cyl(1.98, 8, (BAIL_PIN[0], ARM_Y[0] - 1, BAIL_PIN[1]), (0, 1, 0)))        # press fit for the 4 mm cam pin
        arm = arm if s > 0 else arm.mirror("XZ")
        out = arm if out is None else out.fuse(arm)
    bar = cq.Workplane("XZ", origin=(px, ARM_Y[1], pz + BAIL_LEN)).rect(10.0, 8.0).extrude(2 * ARM_Y[1]).edges("|Y").fillet(3.0).val()
    return out.fuse(bar).clean()


def spacer_9ah():
    e12, e9 = L.env("battery_12ah"), L.env("battery_8ah")
    h = e12["w"] - e9["w"]
    px0, px1 = B["pack_x"]
    z0 = B["pack_z"][0] + e9["w"]
    s = box(px0 + 1, px1 - 1, -CHY + WALL + 1, CHY - WALL - 8.0, z0, z0 + h - 0.5)
    return s.cut(box(px0 + 3.5, px1 - 3.5, -CHY + WALL + 3.5, CHY - WALL - 10.5, z0 + 2.5, z0 + h + 1))


def build(add):
    ASA, PA = D.MAT["ASA"]["color"], D.MAT["PAHT-CF"]["color"]
    add(Part("RRX-P10", "battery_tunnel", tunnel(), "printed", "ASA", "battery_bay", color="#aeb6ba", orient=(0, 0, 0),
             print_note="as fitted (floor on the bed); no supports except the coupler window bridge",
             mates={"chassis_plate", "floor_plug", "battery_cassette", "caster_disc", "coupler_fixed", "coupler_carrier", "cm5_tray"}))
    add(Part("RRX-P11", "floor_plug", floor_plug(), "printed", "ASA", "battery_bay", color="#aeb6ba", orient=(180, 0, 0), internal=False,
             print_note="flange on the bed; 15 % gyroid infill (insulation)", mates={"chassis_plate", "battery_tunnel", "chassis_heater_pad"}))
    add(Part("RRX-P12", "battery_cassette", cassette(), "printed", "ASA", "cassette", color="#e0a23a", orient=(0, 0, 0),
             print_note="open top up; supports under nothing (ears are gusseted)", mates={"battery_pack", "battery_tunnel", "cassette_lid", "coupler_carrier", "bail", "coupler_cassette"}))
    add(Part("RRX-P13", "cassette_lid", cassette_lid(), "printed", "ASA", "cassette", color="#e0a23a", orient=(180, 0, 0),
             print_note="top face on the bed; tongue prints as a 3 mm ledge", mates={"battery_cassette", "battery_pack"}))
    add(Part("RRX-P14", "coupler_carrier", coupler_carrier(), "printed", "PAHT-CF", "cassette", color=PA, orient=(0, 90, 0),
             print_note="flat", mates={"battery_cassette", "coupler_cassette", "battery_tunnel", "coupler_fixed"}))
    add(Part("RRX-P15", "bail", bail(), "printed", "PAHT-CF", "cassette", color=PA, orient=(0, 90, 0), internal=False,
             print_note="lying on its back (bar and arms on the bed)", mates={"battery_cassette", "bail_pin_L", "bail_pin_R", "hatch_frame"}))
    for tag, s in (("L", 1), ("R", -1)):
        add(Part("RRX-H10", f"bail_pin_{tag}", cyl(2.0, 7.6, (BAIL_PIN[0], s * ARM_Y[0], BAIL_PIN[1]), (0, s, 0)), "purchased", "STEEL", "cassette", color="#5d6166",
                 mpn="ISO 8734 4 m6 x 8 hardened dowel pin, pressed into the bail arm", verified="standard part", internal=False, mates={"bail", "hatch_frame"}))
        add(Part("RRX-H11", f"door_peg_{tag}", cyl(2.0, 2.4, (DOOR_PEG[0], s * 57.5, DOOR_PEG[1]), (0, -s, 0)), "purchased", "SS304", "hatch", color="#8f959a",
                 mpn="M4 x 10 A2 dog-point set screw in the M4 insert of the upper jamb boss (dog protrudes 2.4 mm)", verified="standard part", internal=False,
                 mates={"hatch_door", f"rear_deck_{tag}"}))
    add(Part("RRX-P16", "spacer_9ah", spacer_9ah().translate((0, 0, 0)), "printed", "ASA", "cassette_option", color="#e9cf9a", orient=(0, 0, 0),
             print_note="open side up", hard=False, note="only with the 9 Ah PSL-SC-1290 pack; shown for reference, not in the interference set"))
