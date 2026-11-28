"""Bill of hardware of the RR-X build (screws, inserts, pins, gaskets, pads, foam ...) by sub-assembly.

Quantities are derived from the same lists that cut the holes in the model wherever such a list exists.  Fasteners are
ISO metric A2 stainless unless stated.  `status`: STD = standard part (any supplier), UNVERIFIED = supplier part number
or a dimension it depends on was not opened/confirmed in this session, DESIGN = defined by this model.
"""
from __future__ import annotations

import math

from mechanical.common import params as P

from . import dims as D
from .shells import COVER_SCREWS, HUMP_SCREW_X, perim_stations
from .structure import CLIFF_SCREWS, RX_PINS_LOWER, RX_PINS_UPPER, RX_SCREWS, sole_screw_xy

N_SOLE = len(sole_screw_xy())
N_PERIM = len(perim_stations())
N_PERIM_HULL = sum(1 for g, s, p, n in perim_stations() if p[0] < P.RECEIVER["chin_cut"][0])


def perimeter_len():
    row = P.BODY_ROWS["upper_outer"][0]
    pts = [P.ring_point(row, 2 * math.pi * i / 400) for i in range(401)]
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:]))


def rows():
    R = []

    def add(sub, item, spec, qty, where, status="STD", torque="", note=""):
        R.append({"subassembly": sub, "item": item, "spec": spec, "qty": qty, "where": where, "status": status, "torque_Nm": torque, "note": note})

    # A  chassis plate, receiver, caster, front sensors
    add("A chassis", "socket cap screw", "M4 x 18 ISO 4762 A2-70", 2 * len(RX_SCREWS), "FROM BELOW: spring washer + washer + G10 bushing (in the ear) -> ear -> shim -> tapped 4 mm plate (3.6 mm engagement)",
        torque="1.2", note="thermal break joint: 1500 N preload, medium thread-lock; re-check torque at the first service")
    add("A chassis", "conical spring washer", "DIN 6796 4 A2", 2 * len(RX_SCREWS), "under each receiver screw head", "UNVERIFIED", note="keeps the preload against G10 creep (loss 6 % vs 57 % without, calculated)")
    add("A chassis", "flat washer", "ISO 7089 4 A2", 2 * len(RX_SCREWS), "between the spring washer and the G10 bushing flange")
    add("A chassis", "top-hat bushing", "G-10, flange 10 x 1.0, sleeve 6.0 x 3.5, bore 4.3 (machined; PEEK-GF30 alternative)", 2 * len(RX_SCREWS),
        "6.1 mm bore in the receiver ear, flange under the ear", "UNVERIFIED", note="insulates the screw head from the channel; stock item not confirmed, make from G10 tube/rod if needed")
    add("A chassis", "dowel pin (lower)", "4 m6 x 8 ISO 8734", 2 * len(RX_PINS_LOWER), "pressed 5.5 into the channel ear (4 H7 blind), 2.5 into the G10 shim",
        note="second shim hole of each pair is a 4.6 x 4.0 slot; pin top 1.5 below the plate")
    add("A chassis", "dowel pin (upper)", "4 m6 x 8 ISO 8734", 2 * len(RX_PINS_UPPER), "pressed flush into the plate (4 H7), through the shim; tip in a 6.5 x 1.5 ear relief",
        note="no metal path across the shim: each pin set touches metal on one side only")
    add("A chassis", "push pin (dock switch)", "3 h8 x 6 stainless dowel, ends rounded", 1, "left channel end wall, between shoe tip and D2HW plunger", "DESIGN")
    add("A chassis", "pan head screw", "M3 x 8 ISO 7045 A2", 2, "plate -> dock switch bracket inserts", torque="0.6")
    add("A chassis", "pan head screw", "M3 x 10 ISO 7045 A2", 2 * len(CLIFF_SCREWS), "plate -> cliff pod inserts", torque="0.6")
    add("A chassis", "countersunk screw", "M3 x 6 ISO 10642 A2", 4, "caster disc -> tapped plate", torque="0.8", note="thread-lock")
    add("A chassis", "pan head screw", "M4 x 6 ISO 7045 A2", 4, "caster top plate -> tapped caster disc (through the shim)", torque="1.5", note="thread-lock; must not stand above the disc")
    add("A chassis", "countersunk screw", "M5 x 25 ISO 10642 A2-70", 4, "plate (from below) -> bulkhead pedestals -> tapped latch arm", torque="3.0", note="latch reaction path")
    add("A chassis", "socket cap screw", "M4 x 10 ISO 4762 A2", 4, "draw latch -> chin floor -> tapped latch arm", torque="2.0", status="UNVERIFIED", note="latch hole pattern depends on the selected latch")
    add("A chassis", "snap-action switch", "Omron D2HW-C201M", 1, "CHG_COVER (HEAD_DOCK and the 2 BODY_BUMPER switches are RRX-H53 in the parts list)", "UNVERIFIED", note="dimensions PARTIAL in parts.yaml")
    add("A chassis", "pan head screw + insert", "M2 x 10 ISO 7045 A2 + M2 heat-set insert", 8, "D2HW retention in the four printed pockets", "UNVERIFIED", "0.15")
    add("A chassis", "cable grommet", "8 mm hole, 5 mm bore, silicone", 1, "dock-switch lead pass-through at (28, 58) (fit review C4); the cliff leads rise through the pod window bays", "UNVERIFIED")
    # B  lower hull
    add("B lower hull", "countersunk screw", "M3 x 8 ISO 10642 A2", N_SOLE, "plate (from below) -> sole-ring inserts", torque="0.6")
    add("B lower hull", "membrane vent", "M12 x 1.5 ePTFE protective vent + nut, IP67", 1, "right rear quarter (12.2 mm hole)", "UNVERIFIED")
    add("B lower hull", "duck-bill drain valve", "3 mm stem, silicone", 2, "plate drain holes beside the caster", "UNVERIFIED")
    add("B lower hull", "sealant bead", "neutral-cure RTV silicone, -50 C", 1, "plate edge / hull wrap, floor plug, pod notches, cheek slots", note="one 80 ml tube")
    # C  drive
    add("C drive", "countersunk screw", "M4 x 12 ISO 10642 A2", 8, "plate (from below) -> motor pod inserts", torque="1.5")
    add("C drive", "button head screw", "M3 x 6 ISO 7380 A2", 12, "screw ring + pod end face -> gearbox (<= 3 mm engagement)", "UNVERIFIED", "0.5", "Pololu thread depth and pattern clocking UNVERIFIED: pod has both clockings")
    add("C drive", "wheel-to-hub screw", "M3 x 8 ISO 7380 A2 button head (not supplied with the hub)", 12, "wheel web -> tapped hub holes (6 per wheel)", "STD", "0.6", "medium thread-lock; check <= 5 mm engagement against the 9.2 mm hub")
    add("C drive", "tyre adhesive", "flexible cyanoacrylate or polyurethane adhesive", 1, "tyre keys on the rim", note="tyre is also keyed (8 ribs)")
    # D  battery bay and cassette
    add("D battery bay", "countersunk screw", "M3 x 8 ISO 10642 A2", 12, "plate (from below) -> tunnel feet (10) and coupler cradle (2)", torque="0.6")
    add("D battery bay", "socket cap screw + nyloc nut", "M4 x 55 ISO 4762 A2 + M4 ISO 10511", 2, "cross pins through the cradle cheeks and the fixed SBS50 half", "UNVERIFIED", "1.0", "SBS50 mounting-hole positions UNVERIFIED")
    add("D battery bay", "pan head screw", "M3 x 10 ISO 7045 A2", 6, "hatch frame -> tunnel end bosses (4) and hump end (2)", torque="0.6")
    add("D battery bay", "polyimide heater pad", "90 x 70 mm, 12 V 20 W, PSA", 1, "on the floor plug", "UNVERIFIED")
    add("D battery bay", "NTC + bimetal cut-out", "10 k NTC bead x 2, 60 C normally-closed disc thermostat", 1, "beside the pad / on the plate under the tunnel foot", "UNVERIFIED")
    add("D battery bay", "blind-mate coupler", "Anderson SBS50 housing pair, 2 power + 2 auxiliary contacts each", 1, "cradle (fixed) / cassette carrier (floating)", "UNVERIFIED")
    add("D cassette", "shoulder screw", "M3 thread, 4 mm shoulder x 4", 2, "handle hinges -> M3 inserts in the cassette lugs", "UNVERIFIED", "0.5")
    add("D cassette", "spring index plunger", "M10 x 1 body, 5 mm pin, pull knob with rest position, stainless + M10 nut + O-ring", 1, "hump roof at x -215 -> hole in the cassette lid", "UNVERIFIED", "4.0", "GN 617 / Kipp K0338 class: confirm pin stroke >= 6 mm and -25 C grease")
    add("D cassette", "pan head screw", "M3 x 8 ISO 7045 A2", 2, "cassette lid", torque="0.5")
    add("D cassette", "shoulder screw", "M3 thread, 4 mm shoulder x 5", 4, "floating coupler carrier (+-1 mm)", "UNVERIFIED", "0.5")
    add("D cassette", "foam pads", "closed-cell EPDM 3 mm, PSA", 1, "pack sides/top inside the cassette (retention under shock)", note="1 sheet 200 x 300")
    add("D cassette", "pack leads", "2.5 mm2 silicone wire, 6.3 mm insulated receptacles", 1, "pack F2 tabs -> SBS50 contacts", "UNVERIFIED")
    # E  bridge / electronics
    add("E bridge", "countersunk screw", "M4 x 10 ISO 10642 A2", 4, "plate (from below) -> bridge posts", torque="1.5")
    add("E bridge", "countersunk screw", "M3 x 8 ISO 10642 A2", 4, "tray (from above, flush) -> M3 tapped bridge posts", torque="0.8", note="fit review C1: flush, nothing above the tray under the PCB")
    add("E bridge", "pan head screw", "M3 x 6 ISO 7045 A2", 6, "RR-CHS-MAIN -> self-clinching standoffs in the tray", torque="0.5", note="H1, H3 hard chassis bond; fit review C1 (no nuts under the tray)")
    add("E bridge", "self-clinching standoff", D.CLINCH_SO["spec"], 6, "pressed into the tray at the six board holes", "UNVERIFIED", note="tray holes 4.2; press before the tray is fitted")
    add("E bridge", "thermal gap pad", "60 x 40 x 2 mm, >= 3 W/mK", 1, "board underside zone u 50..110, v 30..70 -> tray", "UNVERIFIED")
    add("E bridge", "countersunk screw", "M3 x 8 ISO 10642 A2", 4, "plate -> CM5 tray inserts", torque="0.6")
    add("E bridge", "pan head screw", "M2.5 x 6 ISO 7045 A2", 4, "CM5 carrier -> tray inserts", "UNVERIFIED", "0.3", "carrier hole pattern UNVERIFIED")
    # F  grip
    add("F grip", "countersunk screw + nyloc nut + washer", "M5 x 16 ISO 10642 A2-70", 4, "plate (from below) -> angle feet", torque="4.0", note="proof-load path, through-bolted")
    add("F grip", "socket cap screw + washer", "M5 x 10 ISO 4762 A2-70 + ISO 7089", 4, "angle feet (from inboard) -> M5 tapped side plates", torque="4.0", note="proof-load path; medium thread-lock; fit review: heads inboard so they are reachable at stage 5 and in service")
    add("F grip", "socket cap screw + washer", "M6 x 16 ISO 4762 A2-70 + ISO 7089", 2, "side plates -> tapped ends of the 14 mm bar (in the fairing pockets)", torque="6.0", note="medium thread-lock; proof-load path")
    add("F grip", "pan head screw + nyloc nut", "M3 x 20 ISO 7045 A2", 4, "cheek fairings through the side plates", torque="0.5")
    add("F grip", "end cap", "push-in cap 11 mm, PE", 2, "screw-head pockets of the fairings", "UNVERIFIED")
    # G  lid
    add("G lid", "button head screw + bonded sealing washer", "M3 x 10 ISO 7380-2 A2 (flanged) + 2.5 x 1 silicone O-ring under the flange", N_PERIM, "lid/nose skirt -> tongue inserts (radial)", torque="0.5")
    add("G lid", "pan head screw", "M3 x 12 ISO 7045 A2", 4 + 4, "nose/shoulder (2 per side) and shoulder/deck (2 per side: flank z 100 + roof) flanges", torque="0.6")
    add("G lid", "dowel pin", "3 m6 x 8 ISO 2338", 2 + 4, "lid joint alignment", note="1 per side at x = 47, 2 per side at x = %.0f" % D.X_DECK)
    add("G lid", "countersunk screw", "M3 x 8 ISO 10642 A2", 2 * len(HUMP_SCREW_X), "hump walls (from inside) -> deck curb inserts", torque="0.5")
    add("G lid", "captive panel screw", "M3 x 10 reduced-shank captive screw + retaining washer", len(COVER_SCREWS), "saddle service cover", "UNVERIFIED", "0.5")
    add("G lid", "light pipe", "3 mm rigid press-fit light pipe, 20 mm", 5, "left deck over RR-PANEL", "UNVERIFIED")
    add("G lid", "acoustic vent", "8 mm adhesive ePTFE acoustic membrane", 1, "sounder port behind the left deck", "UNVERIFIED")
    add("G lid", "pan head screw", "M3 x 8 ISO 7045 A2", 2, "RR-PANEL tray -> deck bosses", torque="0.5")
    add("G lid", "pan head screw", "M2 x 6 ISO 7045 A2", 18, "ToF rear clips (9 seats)", torque="0.15")
    add("G lid", "light-blocker gasket", "black closed-cell foam 1.5 mm, die-cut 14 x 10 with two apertures", 11, "between VL53L4ED and window", "DESIGN", note="crosstalk barrier; assumption, see report")
    add("G lid", "LiDAR screws + gasket", "M3 x 8 x 4, 60 x 60 x 1 silicone gasket; M12 x 1.5 cable gland in the LEFT REAR DECK beside the hump (fit review M4: no room inside the hump)", 1, "hump pad / left deck", "UNVERIFIED", note="LiDAR hole pattern UNVERIFIED: pad drilled 4 x 3.4 on a 50 mm square")
    add("G lid", "set screw (door peg)", "M4 x 10 dog point ISO 4028 A2", 2, "upper jamb bosses", torque="1.0")
    add("G lid", "hinge pin", "2 mm x 40 stainless pin", 1, "charge inlet cover", note="torsion spring optional")
    add("G lid", "draw-latch screws", "M4 x 8 ISO 7045 A2", 4, "hatch latch on the hump roof, catch plate on the door", "UNVERIFIED", "1.0")
    add("G lid", "lanyard", "1.5 mm stainless wire rope, 150 mm, 2 eyelets", 1, "door -> hump (captive door)")
    add("G bumper", "guide screw + sleeve + spring", "M3 x 25 ISO 4762 + 5 x 0.75 x 14 PTFE-lined sleeve + compression spring 6 OD x 12, ~0.5 N/mm", 6, "2 per bumper segment", "UNVERIFIED", "0.5")
    add("G bumper", "push pin + spring", "3 mm pin x 10 + spring 4 OD x 8", 2, "side segments -> D2HW plungers", "DESIGN")
    # heat-set inserts
    ins = {"M2": 18 + 8, "M2.5": 4, "M3": N_SOLE + 2 + 12 + 6 + N_PERIM_HULL + (N_PERIM - N_PERIM_HULL) * 0 + 4 + 6 + 2 * len(HUMP_SCREW_X) + len(COVER_SCREWS) + 2 + 2 * len(CLIFF_SCREWS) + 2 + 4 + 2 + 4 + 6 + 2,
           "M4": 8 + 2}
    for m, n in ins.items():
        add("H inserts", "heat-set insert", f"{m} brass, knurled, for {D.INSERT[m][0]} mm hole x {D.INSERT[m][1]} deep", n, "all printed parts", "UNVERIFIED", note="brand to choose; hole sizes in dims.INSERT")
    # gaskets, foam
    add("J seals", "perimeter gasket", D.GASKET["perimeter"], round(perimeter_len() / 1000 + 0.1, 2), "lid / lower hull land (m)", "UNVERIFIED")
    add("J seals", "flat gasket sheet", "closed-cell silicone 1.0 mm, 300 x 300", 1, "lid flange joints, hump curb, hull splice, bulkhead/nose", "UNVERIFIED")
    add("J seals", "cover gasket", D.GASKET["cover"], 0.62, "saddle cover ledge (m)", "UNVERIFIED")
    add("J seals", "hatch gasket", "silicone sponge strip 3 x 2 mm, PSA", 0.5, "hatch frame land (m)", "UNVERIFIED")
    add("J seals", "O-ring cord", "silicone 2 mm", 0.4, "motor pod notches (m)", "UNVERIFIED")
    add("J seals", "insulation liner", "closed-cell foam 5 mm, PSA, -40 C (EPDM/NBR or PE)", 0.25, "inside of every shell piece and the door (m2)", "UNVERIFIED")
    add("J seals", "desiccant + indicator", "10 g silica gel bag + humidity card", 1, "under the saddle cover")
    # K  transport tray
    add("K tray", "wood screw", "3.5 x 16 countersunk", 17, "chocks, caster cup, head guards -> base board")
    add("K tray", "pad", "EVA foam 3 mm, 380 x 140", 1, "on the base under the head (clean, soft surface 7 mm below the rails)")
    add("K tray", "strap", "25 mm cam-buckle strap 1.2 m", 2, "through the base slots over the saddle / hump")
    return R
