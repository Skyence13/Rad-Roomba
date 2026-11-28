"""Fasteners as solids, with tool access, for both builds.

Every fastener listed here is generated from the same hole lists that cut the model (plate hole table, board holes, post list,
cover / perimeter / grip / ToF-clip stations) and becomes:
  * a solid: head (ISO 4762 / 7045 / 7380 / 10642), washers, shank (0.8 d so it fits tap drills and clearance holes) and nut;
    it takes part in the normal interference check against every part;
  * a tool column: a cylinder from the head (or nut) outward along the screw axis, the space the stated tool needs in the
    assembly state of the step that fits the fastener (parts of that step and earlier present).  Columns are checked by
    checks.fastener_access(); a blocked column is a failed check.
Head / nut / washer sizes are ISO values (recalled, standard parts).  Tools: hex key or bit driver (socket and button heads,
countersunk), Phillips / Torx driver (pan heads), socket wrench (nuts).  Column length 60 mm (hex key short arm / bit holder)
or 100 mm (screwdriver).
"""
from __future__ import annotations

import math

import cadquery as cq

from mechanical.common import params as P

from . import dims as D
from .util import Part, cyl, compound, frame, to_frame

HEADS = {   # kind -> {size: (head dia, head height)}
    "shcs": {"M2": (3.8, 2.0), "M2.5": (4.5, 2.5), "M3": (5.5, 3.0), "M4": (7.0, 4.0), "M5": (8.5, 5.0), "M6": (10.0, 6.0)},
    "pan": {"M2": (4.0, 1.6), "M2.5": (5.0, 1.75), "M3": (5.6, 2.4), "M4": (8.0, 3.1), "M5": (9.5, 3.7)},
    "button": {"M3": (5.7, 1.65), "M4": (7.6, 2.2), "M5": (9.5, 2.75)},
    "csk": {"M3": (6.3, 1.7), "M4": (8.4, 2.3), "M5": (10.4, 2.9)},     # = the countersinks cut in the model (dims.CSK), cone fits it
}
NUTS = {"M3": (5.5, 4.0), "M4": (7.0, 5.0), "M5": (8.0, 5.0), "M6": (10.0, 6.0)}       # ISO 10511 nyloc: AF, height
WASHERS = {"M3": (7.0, 0.5), "M4": (9.0, 0.8), "M5": (10.0, 1.0), "M6": (12.0, 1.6)}   # ISO 7089
TOOL = {"shcs": ("hex key / bit driver", 60.0), "button": ("hex key / bit driver", 60.0), "csk": ("hex / Torx bit driver", 60.0), "pan": ("Phillips / Torx screwdriver", 100.0)}
TOOL_D = {   # column diameter: key / bit / blade shank + 2 mm clearance (the head itself sits in its own recess or spot face)
    "shcs": {"M2": 3.5, "M2.5": 4.0, "M3": 4.5, "M4": 5.0, "M5": 6.0, "M6": 7.0}, "button": {"M3": 4.0, "M4": 4.5, "M5": 5.0},
    "csk": {"M3": 4.0, "M4": 4.5, "M5": 5.0}, "pan": {"M2": 4.0, "M2.5": 5.0, "M3": 6.0, "M4": 7.0, "M5": 8.0}}


class Fastener:
    def __init__(self, fid, size, kind, length, surface, axis, *, step, washers=(), nut_at=None, service=None, note="", tool_d=None, later=()):
        """surface: point of the first clamped face (where head or washer stack bears); axis: insertion direction (unit)."""
        self.fid, self.size, self.kind, self.length, self.surface, self.axis = fid, size, kind, length, tuple(surface), P._unit(axis)
        self.step, self.washers, self.nut_at, self.service, self.note, self.later = step, list(washers), nut_at, service, note, tuple(later)
        d = float(size[1:])
        self.d = d
        hd, hk = HEADS[kind][size]
        self.tool_name, self.tool_len = TOOL[kind]
        self.tool_d = tool_d or TOOL_D[kind][size]
        self.hd, self.hk = hd, hk

    def _loc(self):
        return frame(self.surface, self.axis)

    def solid(self):
        """Local frame: z = insertion axis, origin on the clamped surface; head on the -z side (csk: cone into +z)."""
        parts = []
        wt = sum(t for _, t in self.washers)
        z = 0.0
        for od, t in self.washers:
            parts.append(cyl(od / 2, t, (0, 0, -z - t)).cut(cyl(self.d / 2 + 0.2, t + 1, (0, 0, -z - t - 0.5))))
            z += t
        if self.kind == "csk":
            parts.append(cq.Solid.makeCone(self.hd / 2 * 0.97, self.d / 2 * 0.97, self.hk * 0.97, cq.Vector(0, 0, 0.02), cq.Vector(0, 0, 1)))
            shank0, shank_l = self.hk, self.length - self.hk
        else:
            parts.append(cyl(self.hd / 2, self.hk, (0, 0, -wt - self.hk)))
            shank0, shank_l = -wt, self.length
        parts.append(cyl(0.4 * self.d, shank_l, (0, 0, shank0 + 0.02)))
        if self.nut_at is not None:
            af, h = NUTS[self.size]
            parts.append(cq.Workplane("XY").polygon(6, af / math.cos(math.radians(30))).extrude(h).val().translate((0, 0, self.nut_at)))
        return compound(parts).moved(self._loc())

    def tool(self):
        """Tool column(s) outward from the head (and from the nut)."""
        wt = sum(t for _, t in self.washers)
        top = 0.0 if self.kind == "csk" else -wt - self.hk
        cols = [cyl(self.tool_d / 2, self.tool_len, (0, 0, top - self.tool_len - 0.05))]
        if self.nut_at is not None:
            af, h = NUTS[self.size]
            cols.append(cyl(af / 2 + 2.5, 40.0, (0, 0, self.nut_at + h + 0.05)))
        return compound(cols).moved(self._loc())

    def head_point(self):
        return to_frame(self._loc(), (0, 0, -1.0))


# parts fitted later in stage 05 than the grip feet / side plates (stage order of the work instruction)
LATER_IN_04 = ("grip_side_plate_*", "grip_foot_*", "battery_tunnel", "floor_plug", "chassis_heater_pad", "coupler_fixed", "hatch_frame")
LATER_IN_05 = ("grip_side_plate_*", "grip_foot_*", "bridge_*", "board_standoff_*", "RR-CHS-MAIN_*", "cm5_tray", "CM5_*")


# ----------------------------------------------------------------------------------------------- the fastener list
def fasteners():
    """All modelled fasteners (positions read from the lists that cut the holes)."""
    from . import shells, structure
    from .boards_body import _xf_chs
    from mechanical.common import boards as BD
    Z0, Z1 = D.PLATE_Z
    F = []
    up, down = (0, 0, 1), (0, 0, -1)
    rb = P.RECEIVER_BREAK
    # plate hole table: countersunk from below, through from above, tapped
    for i, (x, y, d, kind, why) in enumerate(structure.plate_holes()):
        w = why.lower()
        if kind == "csk_bottom":
            size = "M5" if "m5" in w else ("M4" if "m4" in w else "M3")
            if "motor pod" in w:
                F.append(Fastener(f"pod_{i}", "M4", "csk", 12.0, (x, y, Z0), up, step="03_drive", note="plate -> tapped / insert motor pod"))
            elif "grip foot" in w:
                F.append(Fastener(f"gripfoot_{i}", "M5", "csk", 16.0, (x, y, Z0), up, step="04_battery_bay", nut_at=4.0 + 3.0, note="through-bolt, nyloc on the angle leg (grip frame before the bay)",
                                  later=LATER_IN_04))
            elif "latch arm" in w:
                F.append(Fastener(f"latch_{i}", "M5", "csk", 25.0, (x, y, Z0), up, step="06_nose", note="plate -> pedestal -> tapped latch arm"))
            elif "bridge post" in w:
                F.append(Fastener(f"post_{i}", "M4", "csk", 10.0, (x, y, Z0), up, step="05_bridge_grip", note="plate -> tapped post", later=("RR-CHS-MAIN_*", "CM5_*")))
            elif "tunnel" in w:
                F.append(Fastener(f"tunnel_{i}", "M3", "csk", 8.0, (x, y, Z0), up, step="04_battery_bay"))
            elif "cm5" in w:
                F.append(Fastener(f"cm5tray_{i}", "M3", "csk", 8.0, (x, y, Z0), up, step="05_bridge_grip"))
            elif "coupler" in w:
                F.append(Fastener(f"cradle_{i}", "M3", "csk", 8.0, (x, y, Z0), up, step="04_battery_bay"))
        elif kind == "tap" and "caster disc" in w:
            F.append(Fastener(f"casterdisc_{i}", "M3", "csk", 6.0, (x, y, Z1 + 2.5), down, step="01_chassis"))
        elif kind == "csk_top" and "cliff pod" in w:
            F.append(Fastener(f"cliff_{i}", "M3", "csk", 8.0, (x, y, Z1), down, step="01_chassis", note="plate -> cliff pod insert (countersunk from above, flush)"))
        elif kind == "tap" and "receiver" in w:
            F.append(Fastener(f"rx_{i}", "M4", "shcs", 18.0, (x, y, rb["ear_top_z"] - rb["ear_t"]), up, step="01_chassis",
                              washers=[(rb["bushing"]["flange_od"], rb["bushing"]["flange_t"]), WASHERS["M4"], (9.0, 1.3)],
                              service="receiver re-torque (robot on its back, head removed)", note="from below: ear -> tapped plate (thermal break)"))
        elif kind == "tap" and "dock switch" in w:
            F.append(Fastener(f"dock_{i}", "M3", "pan", 8.0, (x, y, Z1), down, step="01_chassis"))
    for i, (x, y) in enumerate(structure.sole_screw_xy()):
        F.append(Fastener(f"sole_{i}", "M3", "csk", 8.0, (x, y, Z0), up, step="02_lower_hull", note="plate -> hull sole-ring insert"))
    # bridge tray -> posts (countersunk flush, C1) and RR-CHS-MAIN -> clinch standoffs (C1)
    bz = P.ELECTRONICS_BRIDGE_Z
    for i, (x, y) in enumerate(D.POSTS):
        F.append(Fastener(f"tray_{i}", "M3", "csk", 8.0, (x, y, bz[1]), down, step="05_bridge_grip", note="tray -> tapped post, flush (before the board)", later=("RR-CHS-MAIN_*", "CM5_*")))
    for h in [h for h in BD.load("RR-CHS-MAIN")["holes"] if h.get("mounting", True) and h["ref"].startswith("H")]:
        x, y, z = _xf_chs(h["uv"][0], h["uv"][1], 0.0)
        F.append(Fastener(f"board_{h['ref']}", "M3", "pan", 6.0, (x, y, z), down, step="05_bridge_grip", service="board service (lid off)", note="RR-CHS-MAIN -> clinch standoff in the tray"))
    # saddle cover captive screws
    for i, (x, y) in enumerate(shells.COVER_SCREWS):
        F.append(Fastener(f"cover_{i}", "M3", "pan", 8.0, (x, y, P.SADDLE["floor_z"][1]), down, step="08_grip_cover", service="cover (routine)"))
    # lid perimeter screws (radial into the tongue inserts)
    for i, (g, sgn, pt, n) in enumerate(shells.perim_stations()):
        sf = tuple(pt[k] + 4.2 * n[k] for k in range(3))                   # bottom of the 7.2 mm spot face (shells.perim_screws)
        F.append(Fastener(f"perim_{i}", "M3", "button", 10.0, sf, tuple(-c for c in n), step="07_lid", note="ISO 7380-2 flanged button head, O-ring under the flange in the spot face (no washer: width rule)"))
    # grip: foot -> side plate, M5 cap screw from INBOARD into the tapped 6 mm side plate (fit review: the outboard heads could not be
    # reached once the hull and wheels are on); bar screws M6 are modelled as parts (grip_screw_*)
    y0, y1 = D.GRIP_PLATE_Y
    for s in (1, -1):
        for x in (-48.0, -30.0):
            F.append(Fastener(f"gripplate_{'L' if s > 0 else 'R'}{x:.0f}", "M5", "shcs", 10.0, (x, s * (y0 - 3.0), Z1 + 16.0), (0, s, 0), step="04_battery_bay",
                              note="angle foot -> tapped side plate (from inboard, before the battery tunnel)", later=LATER_IN_04[2:]))
    return F


def as_parts(F):
    """Fastener solids as Parts (purchased, group 'fastener')."""
    return [Part("HW", f"fx_{f.fid}", f.solid(), "purchased", "SS304", "fastener", color="#9aa3a8", mass=0.0, internal=False,
                 verified="ISO standard dimensions (recalled)", note=f.note) for f in F]
