"""Boards placed in the body FROM THE BOARD FILES (mechanical/common/boards.py): RR-CHS-MAIN, RR-PANEL, eleven RR-TOF-A carriers
and the CM5 carrier, each as PCB (with holes) + component bodies (courtyard x 3D height, both sides) + one mated plug and one
wire-exit volume per connector.  Replaces the 18 mm / 12 mm keep-out boxes and the 3.3 mm ToF slab of the earlier builds, so the
interference check sees connectors, plugs and wires.  Plug / exit sizes are family estimates + 1 mm margin (UNVERIFIED)."""
from __future__ import annotations

import cadquery as cq

from mechanical.common import boards as BD
from mechanical.common import params as P
from mechanical.common.purchased import library as L

from . import sensors as S
from .util import Part, box, compound, frame, to_frame

COL = {"pcb": "#2e7d4f", "comp": "#3a3f44", "plug": "#d8d2c4", "exit": "#e7b54a"}
PORTS = {}      # (board, ref, instance) -> {"xyz": base_link point where the wires leave the exit volume, "dir": unit, "bend_r"}


def _xf_chs(u, v, z):
    ox, oy, oz = P.CHS_MAIN["origin"]
    return ox + v, oy - u, oz + P.CHS_MAIN["thickness"] + z          # z from the PCB top


def _box_uv(b, xf):
    u0, u1, v0, v1, z0, z1 = b
    pts = [xf(u, v, z) for u in (u0, u1) for v in (v0, v1) for z in (z0, z1)]
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    return box(min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _dir(d, xf):
    o, e = xf(0, 0, 0), xf(*d)
    return tuple(e[i] - o[i] for i in range(3))


def board_parts(name, tag, xf, pn, group, add, mass, extra_mates=()):
    """Add PCB, components and connector plug / exit solids of one board placed by xf(u, v, z_from_top)."""
    b = BD.load(name)
    u0, v0, u1, v1 = b["outline_uv"]
    th = b["thickness"]
    pcb = _box_uv((u0, u1, v0, v1, -th, 0.0), xf)
    for h in b["holes"]:
        c = xf(h["uv"][0], h["uv"][1], -th - 1)
        top = xf(h["uv"][0], h["uv"][1], 1)
        pcb = pcb.cut(cq.Solid.makeCylinder(h["d"] / 2, abs(top[2] - c[2]) + 0.01, cq.Vector(*c) if top[2] > c[2] else cq.Vector(*top), cq.Vector(0, 0, 1)))
    add(Part(pn, f"{tag}_pcb", pcb, "purchased", "FR4", group, color=COL["pcb"], mass=mass, internal=False, mpn=f"{name} (custom)",
             verified=f"tool-read from {b['file']} ({b['source']})", mates=set(extra_mates) | {f"{tag}_*"}))
    for side in ("F", "B"):
        comps = [_box_uv(bx, xf) for ref, s, bx in BD.components(name) if s == side and not BD.connector_mating(name, ref)]
        cons = [BD.connector_mating(name, ref) for ref, s, bx in BD.components(name) if s == side and BD.connector_mating(name, ref)]
        comps += [_box_uv(c["body"], xf) for c in cons if c]
        if comps:
            add(Part(pn, f"{tag}_{'top' if side == 'F' else 'bottom'}_parts", compound(comps), "purchased", "COMP", group, color=COL["comp"], mass=0.0, internal=False,
                     verified=f"courtyard x 3D height, tool-read from {b['file']}", mates={f"{tag}_*"} | set(extra_mates)))
    for ref in b["parts"]:
        m = BD.connector_mating(name, ref)
        if not m or m.get("debug"):
            continue
        add(Part(pn, f"{tag}_plug_{ref}", compound([_box_uv(m["plug"], xf), _box_uv(m["exit"], xf)]), "purchased", "PLUG", group, color=COL["plug"], mass=0.0, internal=False,
                 verified=m["status"], mates={f"{tag}_*"}))
        PORTS[(name, ref, tag)] = {"xyz": xf(*m["port"]), "dir": P._unit(_dir(m["dir"], xf)), "bend_r": m["bend_r"], "family": m["family"]}


def chs_main(add):
    board_parts("RR-CHS-MAIN", "RR-CHS-MAIN", _xf_chs, "RRX-E01", "chs_main", add, 0.22)


def panel(add):
    """RR-PANEL in its tray under the left deck: long axis along x, the v = 24 edge (J1 / J2 mating faces) inboard (-y),
    component side up (light pipes).  Orientation fixed here (panel README asks mechanical to fix it)."""
    pc = P.PANEL_CONTROLS["annunciator"]["xyz"]
    _, ztop = S.panel_tray()
    zb = ztop - 6.0                                       # tray pocket floor = PCB underside
    th = BD.load("RR-PANEL")["thickness"]
    xf = lambda u, v, z: (pc[0] - 35.0 + u, pc[1] + 12.0 - v, zb + th + z)
    board_parts("RR-PANEL", "RR-PANEL", xf, "RRX-E02", "controls", add, L.mass("panel_board"))


def tof_xf(name):
    """Seat frame -> board frame for one carrier: board (u, v) = seat local (x, y) with the sensor (board origin) on the boresight;
    PCB front (F side, sensor) at local z -S.TOF_FRONT (1.1 window recess + 1.5 foam), so local z = z_from_top - TOF_FRONT."""
    t = P.TOF_SENSORS[name]
    xdir = (1.0, 0.0, 0.0) if name.startswith("tof_cliff_f") else S.seat_xdir(t["dir"], S.seat_kind(name))
    loc = frame(t["xyz"], t["dir"], xdir)
    return lambda u, v, z: to_frame(loc, (u, v, z - S.TOF_FRONT))


def tof_carriers(add):
    for name in P.TOF_SENSORS:
        board_parts("RR-TOF-A", "rr" + name, tof_xf(name), "RRX-E03", "tof", add, L.mass("tof_board"))


CM5_PLUGS = {   # Waveshare CM5-IO-BASE-A, connector edge toward -x (orientation fixed by the body; connector positions UNVERIFIED)
    "rj45": ((0.0, 16.0, 6.0, 22.0, 0.0, 13.5), 22.0, 30.0),        # (u0, u1, v0, v1, z0, z1) on the carrier, plug length, cable straight run
    "usb_a": ((0.0, 15.0, 30.0, 45.0, 0.0, 16.0), 32.0, 25.0),
}


def cm5_carrier(add):
    """Carrier PCB 85 x 56 (VERIFIED), CM5 + heat-sink block, RJ45 and dual USB-A on the -x end, 40-pin header along the +y edge,
    each with its mated plug and wire exit (positions and heights UNVERIFIED; plugs + 1 mm margin)."""
    c = P.CM5_POSE
    e = L.env("cm5_carrier")
    x0, y0, zb = c["x"][0], c["y"][0], c["pcb_z"]
    xf = lambda u, v, z: (x0 + u, y0 + v, zb + z)
    pcb = box(x0, x0 + e["l"], y0, y0 + e["w"], zb, zb + e["pcb_t"])
    add(Part("RRX-H46", "CM5_carrier_pcb", pcb, "purchased", "PCB", "compute", color=COL["pcb"], mass=L.mass("cm5") + L.mass("cm5_carrier") + 0.04, internal=False,
             mpn="Waveshare CM5-IO-BASE-A + Raspberry Pi CM5104032 + heat sink", verified="outline VERIFIED; height, holes, connector positions UNVERIFIED", mates={"CM5_*"}))
    t = zb + e["pcb_t"]
    bodies = [box(x0 + 22, x0 + 80, y0 + 6, y0 + 48, t, zb + e["h_assembled"] - 3.0)]                   # CM5 + heat sink (assumed 24 mm assembled)
    for k, (bx, pl, run) in CM5_PLUGS.items():
        bodies.append(box(x0 + bx[0], x0 + bx[1], y0 + bx[2], y0 + bx[3], t, t + bx[5]))
        plug = box(x0 + bx[0] - pl - 1, x0 + bx[0], y0 + bx[2] - 1, y0 + bx[3] + 1, t - 1, t + bx[5] + 1)
        ex = box(x0 + bx[0] - pl - 1 - run, x0 + bx[0] - pl - 1, y0 + bx[2] - 1, y0 + bx[3] + 1, t - 1, t + bx[5] + 1)
        add(Part("RRX-H46", f"CM5_plug_{k}", compound([plug, ex]), "purchased", "PLUG", "compute", color=COL["plug"], mass=0.0, internal=False,
                 verified="RJ45 / USB-A plug + cable exit, estimate + 1 mm (UNVERIFIED)", mates={"CM5_*"}))
        PORTS[("CM5", k, "CM5")] = {"xyz": (x0 + bx[0] - pl - 1 - run, y0 + (bx[2] + bx[3]) / 2, t + bx[5] / 2), "dir": (-1.0, 0.0, 0.0), "bend_r": 25.0, "family": k}
    hdr = box(x0 + 26, x0 + 77, y0 + 50, y0 + 55, t, t + 8.5)                                          # 2 x 20 header along the +y edge
    bodies.append(hdr)
    add(Part("RRX-H46", "CM5_carrier_parts", compound(bodies), "purchased", "COMP", "compute", color=COL["comp"], mass=0.0, internal=False,
             verified="UNVERIFIED layout of the purchased carrier", mates={"CM5_*"}))
    plug = box(x0 + 37, x0 + 53, y0 + 49, y0 + 56, t + 8.5, t + 8.5 + 9.5)                             # 2 x 4 receptacle housing on the 5 V pins
    ex = box(x0 + 37, x0 + 53, y0 + 49, y0 + 56, t + 18.0, t + 18.0 + 8.0)
    add(Part("RRX-H46", "CM5_plug_hdr40", compound([plug, ex]), "purchased", "PLUG", "compute", color=COL["plug"], mass=0.0, internal=False,
             verified="2 x 4 Dupont-class housing on the 40-pin header + wire exit, estimate + 1 mm (UNVERIFIED)", mates={"CM5_*"}))
    PORTS[("CM5", "hdr40", "CM5")] = {"xyz": (x0 + 45, y0 + 52.5, t + 26.0), "dir": (0.0, 0.0, 1.0), "bend_r": 6.0, "family": "Dupont 2.54"}
