"""Envelope solids for the purchased parts (CadQuery). Local frames are stated per function; layout.py places them."""
from __future__ import annotations

from pathlib import Path

import cadquery as cq
import yaml

PARTS = yaml.safe_load((Path(__file__).with_name("parts.yaml")).read_text(encoding="utf-8"))


def env(key):
    return PARTS[key]["envelope"]


def mass(key):
    return float(PARTS[key]["mass_kg"])


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def cyl(r, h, base=(0, 0, 0), axis=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, h, cq.Vector(*base), cq.Vector(*axis))


def fuse(*solids):
    out = solids[0]
    for s in solids[1:]:
        out = out.fuse(s)
    return out.clean()


def motor(side):
    """Gearbox face at local origin on the SHAFT axis, shaft along +y*side. Can centre is +shaft_offset in z."""
    e = env("motor")
    can = cyl(e["can_d"] / 2, e["body_l"], (0, 0, e["shaft_offset"]), (0, -side, 0))
    boss = cyl(e["boss_d"] / 2, e["boss_l"], (0, 0, 0), (0, side, 0))
    shaft = cyl(e["shaft_d"] / 2, e["boss_l"] + e["shaft_l"], (0, 0, 0), (0, side, 0))
    return fuse(can, boss, shaft)


def wheel(side):
    """Tyre centre at local origin, axis y. Hub inboard."""
    e = env("wheel")
    tyre = cyl(e["d"] / 2, e["width"], (0, -side * e["width"] / 2, 0), (0, side, 0))
    hub = cyl(e["hub_d"] / 2, e["hub_l"], (0, -side * e["width"] / 2, 0), (0, -side, 0))
    return fuse(tyre, hub)


def caster():
    """Local origin on the swivel axis at the mounting face, -z down; wheel trails at -x (forward travel)."""
    e = env("caster")
    plate = box(-e["plate"][0] / 2, e["plate"][0] / 2, -e["plate"][1] / 2, e["plate"][1] / 2, -2.0, 0)
    dome = cyl(12.25, 9.0, (0, 0, -11.0))
    wheel_ = cyl(e["wheel_d"] / 2, e["wheel_w"], (-e["offset"], -e["wheel_w"] / 2, -e["overall_h"] + e["wheel_d"] / 2), (0, 1, 0))
    fork = box(-e["offset"] - 6, 6, -e["caster_w"] / 2, e["caster_w"] / 2, -e["overall_h"] + e["wheel_d"] / 2 - 3, -11.0)
    return fuse(plate, dome, fork, wheel_)


def caster_swept():
    """Swivel envelope (wheel anywhere around the swivel axis)."""
    e = env("caster")
    return cyl(e["swivel_radius"], e["overall_h"], (0, 0, -e["overall_h"]))


def battery(key="battery_8ah"):
    """Pack lying on its L x H side: L along x, total height along y, W along z. Origin at the min corner."""
    e = env(key)
    return box(0, e["l"], 0, e["h_total"], 0, e["w"])


def simple_box(key, dims=("l", "w", "h")):
    e = env(key)
    return box(0, e[dims[0]], 0, e[dims[1]], 0, e[dims[2]])


def lidar(key="lidar"):
    e = env(key)
    return box(-e["l"] / 2, e["l"] / 2, -e["w"] / 2, e["w"] / 2, 0, e["h"])


def panel_device(key):
    """22 mm panel device: origin on the panel outer face, +z outward. Returns (head, rear_body)."""
    e = env(key)
    head = cyl(e["head_d"] / 2, e["head_h"], (0, 0, 0))
    body = cyl(e["body_d"] / 2, e["depth_behind_panel"], (0, 0, 0), (0, 0, -1))
    return head, body


def receptacle(key):
    """Panel receptacle: origin on the panel outer face, +z = mating axis.
    Returns (receptacle solid, mated plug solid incl. straight cable stub, coupling-nut cylinder)."""
    e = env(key)
    rec = fuse(cyl(e["flange_d"] / 2, e["front_projection"], (0, 0, 0)), cyl(e["flange_d"] / 2 - 2, e["depth_behind_panel"], (0, 0, 0), (0, 0, -1)))
    z0 = 2.0
    nut = cyl(e["plug_nut_d"] / 2, e["plug_nut_l"], (0, 0, z0))
    plug = fuse(cyl(e["plug_nut_d"] / 2 - 1.0, e["plug_l"], (0, 0, z0)), cyl(e["cable_d"] / 2, 25.0, (0, 0, z0 + e["plug_l"])))
    return rec, plug, nut


def inlet():
    e = env("charge_inlet")
    rec = fuse(cyl(e["body_d"] / 2, e["front_projection"], (0, 0, 0)), cyl(e["body_d"] / 2 - 2, e["depth_behind_panel"], (0, 0, 0), (0, 0, -1)))
    c = e["cover"]
    cover = box(-c[0] / 2, c[0] / 2, -c[1] / 2, c[1] / 2, e["front_projection"], e["front_projection"] + c[2])
    return rec, cover


def switch():
    e = env("bumper_switch")
    return box(-e["l"] / 2, e["l"] / 2, -e["w"] / 2, e["w"] / 2, 0, e["h"])


def tof():
    """Origin at the sensor aperture on the skin, +z = boresight (outward). Board sits behind the window."""
    e = env("tof_board")
    return box(-e["l"] / 2, e["l"] / 2, -e["w"] / 2, e["w"] / 2, -e["depth"], 0)
