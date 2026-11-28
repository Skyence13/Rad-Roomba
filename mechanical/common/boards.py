"""Boards from the board files: RR-CHS-MAIN, RR-PANEL and RR-TOF-A read from their KiCad PCBs (method of
mechanical/head/asbuilt.py: outline from Edge.Cuts, holes from the pads, every footprint's courtyard on BOTH sides and the 3D
envelope height that the electronics build attaches as `<fp>_h<h>.step`), plus mated-plug and wire-exit envelopes for every
board connector.

Board frame (u, v) = (X - aux_axis_origin_x, aux_axis_origin_y - Y), +z = component (top, F.Cu) side.  Placement in base_link
is done by the body builds.  Every geometric number about a board is READ from its file; the mated-plug and wire-exit sizes
are ESTIMATES per connector family (no manufacturer drawing in the repository, IB-35) and carry a margin: UNVERIFIED.

If a board file is being rewritten while we read it (another build running), the last complete parse is used from
out/boards_snapshot.json and the result says so.
"""
from __future__ import annotations

import json
import math
import re
import time
from functools import lru_cache
from pathlib import Path

from . import params as P

FILES = {"RR-CHS-MAIN": "electronics/chassis_main/RR-CHS-MAIN.kicad_pcb", "RR-PANEL": "electronics/panel/RR-PANEL.kicad_pcb",
         "RR-TOF-A": "electronics/tof_carrier/RR-TOF-A.kicad_pcb"}
SNAP = P.OUT / "boards_snapshot.json"
PLUG_MARGIN = 1.0    # mm added all round to every mated-plug / wire-exit estimate (UNVERIFIED family data)

# family -> (match in the footprint name, plug length beyond the header in the mating direction, straight wire run before a bend,
#            minimum wire bend radius of the conductors leaving the plug).  ESTIMATES, recalled family values: UNVERIFIED.
FAMILIES = [
    ("JST GH", "JST_GH", 3.0, 4.0, 3.0),
    ("Molex CLIK-Mate", "CLIK-Mate", 4.0, 6.0, 3.0),
    ("Molex Micro-Fit 3.0", "Micro-Fit", 12.0, 6.0, 6.0),
    ("Molex Mini-Fit Jr", "Mini-Fit", 15.0, 12.0, 8.0),
    ("pin header (debug)", "PinHeader", 6.0, 0.0, 0.0),
]


def _tokens(text):
    tok = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
    stack = [[]]
    for m in tok.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t[1:-1] if t.startswith('"') else t)
    return stack[0][0]


def _find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def _first(node, key):
    r = _find(node, key)
    return r[0] if r else None


def _xform(at, lx, ly):
    x, y, r = at
    a = math.radians(r)
    return x + lx * math.cos(a) + ly * math.sin(a), y - lx * math.sin(a) + ly * math.cos(a)


def _git_full(rel):
    """Newest committed revision of a board file that is complete (read-only git show), or (None, None)."""
    import subprocess
    try:
        revs = subprocess.run(["git", "-C", str(P.REPO), "log", "--format=%h", "-12", "--", rel], capture_output=True, text=True, timeout=60).stdout.split()
        for h in revs:
            t = subprocess.run(["git", "-C", str(P.REPO), "show", f"{h}:{rel}"], capture_output=True, text=True, timeout=120).stdout
            if "(footprint" in t and t.rstrip().endswith(")"):
                return h, t
    except (OSError, subprocess.SubprocessError):
        pass
    return None, None


def _parse(path, txt=None):
    txt = Path(path).read_text() if txt is None else txt
    if not (txt.rstrip().endswith(")") and "(aux_axis_origin" in txt and "(footprint" in txt):
        raise ValueError("incomplete")
    pcb = _tokens(txt)
    setup = _first(pcb, "setup")
    ao = _first(setup, "aux_axis_origin")
    ox, oy = float(ao[1]), float(ao[2])
    uv = lambda X, Y: (round(X - ox, 4), round(oy - Y, 4))
    pts = []
    for g in pcb:
        if isinstance(g, list) and g and g[0] in ("gr_line", "gr_rect", "gr_arc", "gr_poly") and (_first(g, "layer") or [None, ""])[1] == "Edge.Cuts":
            for k in ("start", "end", "mid"):
                s = _first(g, k)
                if s:
                    pts.append(uv(float(s[1]), float(s[2])))
            pp = _first(g, "pts")
            if pp:
                pts += [uv(float(q[1]), float(q[2])) for q in _find(pp, "xy")]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    gs = _first(pcb, "general")
    th = float(_first(gs, "thickness")[1]) if gs and _first(gs, "thickness") else 1.6
    parts, holes = {}, []
    for fp in _find(pcb, "footprint"):
        name = fp[1]
        at_ = _first(fp, "at")
        at = (float(at_[1]), float(at_[2]), float(at_[3]) if len(at_) > 3 else 0.0)
        side = "B" if _first(fp, "layer")[1] == "B.Cu" else "F"
        ref = next((p[2] for p in _find(fp, "property") if p[1] == "Reference"), None) or next((p[2] for p in _find(fp, "fp_text") if p[1] == "reference"), "?")
        h = None
        for m in _find(fp, "model"):
            hm = re.search(r"_h(\d+)p(\d+)\.step", m[1])
            if hm:
                h = float(f"{hm.group(1)}.{hm.group(2)}")
        boxes = {}
        for lay in ("F.CrtYd", "B.CrtYd", "F.Fab", "B.Fab"):
            q = []
            for g in fp:
                if isinstance(g, list) and g and g[0] in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc") and (_first(g, "layer") or [None, ""])[1] == lay:
                    for k in ("start", "end", "mid", "center"):
                        s = _first(g, k)
                        if s:
                            q.append(_xform(at, float(s[1]), float(s[2])))
                    pp = _first(g, "pts")
                    if pp:
                        q += [_xform(at, float(x[1]), float(x[2])) for x in _find(pp, "xy")]
            if q:
                bu = [uv(*p) for p in q]
                boxes[lay] = (min(p[0] for p in bu), min(p[1] for p in bu), max(p[0] for p in bu), max(p[1] for p in bu))
        pads = []
        for pd in _find(fp, "pad"):
            pa = _first(pd, "at")
            X, Y = _xform(at, float(pa[1]), float(pa[2]))
            dr = _first(pd, "drill")
            d = None
            if dr:
                nums = [float(v) for v in dr[1:] if isinstance(v, str) and re.match(r"^[\d.]+$", v)]
                d = nums[0] if nums else None
            pads.append({"num": pd[1], "type": pd[2], "uv": uv(X, Y), "drill": d})
            if d and ("MountingHole" in name or pd[2] == "np_thru_hole") and d >= 2.0:
                holes.append({"ref": ref, "uv": uv(X, Y), "d": d, "mounting": "MountingHole" in name})
        cy = boxes.get(f"{side}.CrtYd") or boxes.get(f"{side}.Fab")
        parts[ref] = {"fp": name, "side": side, "uv": uv(at[0], at[1]), "rot": at[2], "height": h, "box_uv": cy, "pads": pads}
    st = Path(path).stat()
    return {"file": str(Path(path).relative_to(P.REPO)), "bytes": st.st_size, "mtime_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(st.st_mtime)),
            "source": "board file", "outline_uv": (min(us), min(vs), max(us), max(vs)), "thickness": th, "holes": holes, "parts": parts}


@lru_cache(maxsize=None)
def load(name):
    """Parsed board (dict). Retries while the file is being rewritten; falls back to the last complete parse."""
    path = P.REPO / FILES[name]
    snap = json.loads(SNAP.read_text()) if SNAP.exists() else {}
    for attempt in range(3):
        try:
            b = _parse(path)
            snap[name] = b
            SNAP.parent.mkdir(exist_ok=True)
            SNAP.write_text(json.dumps(snap, indent=0))
            return b
        except (OSError, ValueError, IndexError, TypeError):
            time.sleep(5)
    h, txt = _git_full(FILES[name])
    if txt:
        b = _parse(path, txt)
        b["source"] = f"git revision {h} (the working-tree file is an incomplete stub at build time; newest complete committed board used)"
        return b
    if name in snap:
        b = dict(snap[name])
        b["source"] = f"SNAPSHOT of {b['mtime_utc']} (board file incomplete at build time: another build was rewriting it)"
        return b
    raise RuntimeError(f"{name}: board file unreadable and no snapshot")


def family(fp):
    return next((f for f in FAMILIES if f[1] in fp), None)


def connector_mating(name, ref):
    """Mating data of one board connector (board frame): {family, vertical, dir (du, dv, dz), body box, plug box, exit box,
    port (u, v, z) where the wires leave the exit volume, bend_r}.  Boxes are (u0, u1, v0, v1, z0, z1), z from the PCB top
    (F side) or PCB bottom (B side, negative z).  None for parts that are not connectors."""
    b = load(name)
    p = b["parts"][ref]
    fam = family(p["fp"])
    if not fam or not p["box_uv"]:
        return None
    u0, v0, u1, v1 = p["box_uv"]
    h = p["height"] or 5.0
    sgn = 1.0 if p["side"] == "F" else -1.0
    zb = 0.0 if sgn > 0 else -b["thickness"]
    body = (u0, u1, v0, v1) + tuple(sorted((zb, zb + sgn * h)))
    m = PLUG_MARGIN
    vertical = "Vertical" in p["fp"] or "_BM" in p["fp"] or ("CLIK-Mate" in p["fp"] and "Horizontal" not in p["fp"])
    label, _, plug_l, run, bend = fam
    if fam[0].startswith("pin header"):
        return {"family": label, "debug": True, "body": body}
    if vertical:
        z_top = zb + sgn * h
        plug = (u0 - m, u1 + m, v0 - m, v1 + m) + tuple(sorted((z_top, z_top + sgn * (plug_l + m))))
        z2 = z_top + sgn * (plug_l + m)
        exit_ = (u0 - m, u1 + m, v0 - m, v1 + m) + tuple(sorted((z2, z2 + sgn * run)))
        port = ((u0 + u1) / 2, (v0 + v1) / 2, z2 + sgn * run)
        d = (0.0, 0.0, sgn)
    else:
        bu0, bv0, bu1, bv1 = b["outline_uv"]
        cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
        dists = {(-1, 0): cu - bu0, (1, 0): bu1 - cu, (0, -1): cv - bv0, (0, 1): bv1 - cv}
        du, dv = min(dists, key=dists.get)
        zz = tuple(sorted((zb - sgn * m, zb + sgn * (h + m))))
        if du:
            face = u1 if du > 0 else u0
            plug = tuple(sorted((face, face + du * plug_l))) + (v0 - m, v1 + m) + zz
            e = face + du * plug_l
            exit_ = tuple(sorted((e, e + du * run))) + (v0 - m, v1 + m) + zz
            port = (e + du * run, cv, zb + sgn * h / 2)
        else:
            face = v1 if dv > 0 else v0
            plug = (u0 - m, u1 + m) + tuple(sorted((face, face + dv * plug_l))) + zz
            e = face + dv * plug_l
            exit_ = (u0 - m, u1 + m) + tuple(sorted((e, e + dv * run))) + zz
            port = (cu, e + dv * run, zb + sgn * h / 2)
        d = (float(du), float(dv), 0.0)
    return {"family": label, "vertical": vertical, "dir": d, "body": body, "plug": plug, "exit": exit_, "port": port, "bend_r": bend,
            "status": "plug and wire-exit sizes are family ESTIMATES + %.1f mm margin (UNVERIFIED, IB-35)" % m}


def components(name):
    """[(ref, side, box (u0, u1, v0, v1, z0, z1))] for every footprint with a courtyard and a height (both sides)."""
    b = load(name)
    out = []
    for ref, p in b["parts"].items():
        if not p["box_uv"] or not p["height"] or p["height"] < 0.2 or "MountingHole" in p["fp"] or "Fiducial" in p["fp"]:
            continue
        u0, v0, u1, v1 = p["box_uv"]
        if p["side"] == "F":
            out.append((ref, "F", (u0, u1, v0, v1, 0.0, p["height"])))
        else:
            out.append((ref, "B", (u0, u1, v0, v1, -b["thickness"] - p["height"], -b["thickness"])))
    return out


def summary():
    out = {}
    for n in FILES:
        b = load(n)
        cons = [r for r in b["parts"] if connector_mating(n, r)]
        out[n] = {"file": b["file"], "source": b["source"], "mtime_utc": b["mtime_utc"], "outline_uv": b["outline_uv"], "holes": len(b["holes"]),
                  "footprints": len(b["parts"]), "bottom_side_parts": sum(1 for p in b["parts"].values() if p["side"] == "B"), "connectors": cons}
    return out


if __name__ == "__main__":
    print(json.dumps(summary(), indent=1))
