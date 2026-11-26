"""Deterministic fine-pitch escape ("fan-out") for IC pads, done before autorouting.

Why: Freerouting reliably fails on a handful of 0.5 mm-pitch pins - it boxes a pad in
with its neighbours' escape vias and never recovers.  Here every pad of a fine-pitch
IC that needs to leave the package gets its escape up front, as locked copper:

* signal pads -> short stub + via on a ring outside the package, alternating between
  two staggered radii (row 0 / row 1).  The ring is *fanned* (lateral via pitch
  slightly larger than the pad pitch) so that the stub of a row-1 via passes between
  two row-0 vias with full clearance even with 0.6 mm vias at 0.5 mm pad pitch;
* plane-net pads of packages without an exposed pad -> stub + via *under* the package
  (keeps the ring free); otherwise they take a ring position whose via lies inside
  their own plane polygon;
* pads whose net reaches a two-pad passive (pull-up, series R, ...) a few mm away ->
  a direct short pre-route to that passive instead of a via, when one or two straight
  segments do it with clearance;
* pads whose planned position is blocked -> a local search over further radii and
  lateral offsets, then (packages without exposed pad) under the package.

Everything is checked with exact geometry against all copper, holes, board edge,
cut-outs, via keep-outs and other parts' courtyards (geom.Obstacles, which adds the
DSN's 25 um margin).  Generated items are locked pre-routes: they are exported to the
DSN as fixed wiring of their net, so the autorouter starts from the escape vias.
"""
import math

import pcbnew

from .geom import Obstacles, MM, T, pt_seg

TAN_FAN = math.tan(math.radians(40.0))     # max angle of a stub from the pad axis
DIRECT_MAX = 4.0                           # mm, pad tip -> passive pad centre


def settings(b):
    """Effective escape settings of a board (None when disabled)."""
    o = b.routing
    mode = o.get("escape", "auto")
    on = (b.layers >= 4) if mode == "auto" else bool(mode)
    if not on:
        return None
    r = b.rules
    via = o.get("escape_via") or (max(r.min_via_dia, r.min_via_drill + 2 * r.min_annular), r.min_via_drill)
    dia, drill = float(via[0]), float(via[1])
    tw = float(o.get("escape_track") or r.min_track)
    return {"pitch": float(o.get("escape_pitch", 0.65)), "via_dia": dia, "via_drill": drill, "track": tw,
            "layers": list(o.get("escape_layers") or [l for l in b.copper_layers if l not in b.plane_layers and l != "F.Cu"]),
            "direct": bool(o.get("escape_direct", True))}


# ------------------------------------------------------------------ analysis
def analyse(pads):
    """pads: geom pad items of one footprint -> dict(pitch, centre, ep, perim) or None."""
    smd = [p for p in pads if not p["drill"]]
    if len(smd) < 4 or len(smd) != len(pads):
        return None
    areas = sorted((p["rect"][2] - p["rect"][0]) * (p["rect"][3] - p["rect"][1]) for p in smd)
    med = areas[len(areas) // 2]
    ep = [p for p in smd if (p["rect"][2] - p["rect"][0]) * (p["rect"][3] - p["rect"][1]) > 4.0 * med]
    perim = [p for p in smd if p not in ep]
    if len(perim) < 4:
        return None
    nn = []
    for p in perim:
        d = min(math.hypot(p["cx"] - q["cx"], p["cy"] - q["cy"]) for q in perim if q is not p)
        nn.append(d)
    nn.sort()
    pitch = nn[len(nn) // 2]
    xs = [p["cx"] for p in perim]
    ys = [p["cy"] for p in perim]
    centre = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    return {"pitch": pitch, "centre": centre, "ep": ep, "perim": perim}


def is_candidate(part, info, st):
    if st is None or info is None or part.escape is False:
        return False
    if part.escape is True:
        return True
    return info["pitch"] < st["pitch"] - 1e-6 and len(info["perim"]) >= 8


def footprint_info(bld, part):
    """analyse() for a footprint as it currently sits on the board."""
    from .geom import pad_item
    fp = bld.fps[part.ref]
    lid = {l: bld.pcb.GetLayerID(l) for l in bld.b.copper_layers}
    items = [it for it in (pad_item(p, part.ref, lid) for p in fp.Pads()) if it is not None]
    return analyse(items)


# ------------------------------------------------------------------- planner
class Side:
    def __init__(self, axis, sign):
        self.axis, self.sign = axis, sign
        self.pads = []

    def xy(self, tip, lat, rad):
        """(lateral, radial) relative to the pad tip line -> KiCad mm."""
        if self.axis == "x":
            return (tip + self.sign * rad, lat)
        return (lat, tip + self.sign * rad)


def escape(bld):
    """Generate the escape copper on bld.pcb.  Returns (stats dict, set of handled pad keys)."""
    b, pcb, fr = bld.b, bld.pcb, bld.fr
    st = settings(b)
    stats = {"enabled": st is not None, "parts": {}, "vias": 0, "direct": 0, "inward": 0, "skipped": [],
             "skipped_by_reason": {}}
    handled = set()
    if st is None:
        return stats, handled
    stats.update({"pitch_limit": st["pitch"], "via": [st["via_dia"], st["via_drill"]], "track": st["track"],
                  "layers": st["layers"]})
    obs = Obstacles(bld)
    zones = []
    for zd in b.zones:
        for lname in zd["layers"]:
            if lname in b.plane_layers:
                zones.append((lname, zd["priority"], zd["net"], [fr.kmm(*p) for p in (zd["polygon"] or b.outline["pts"])]))
    plane_nets = {z[2] for z in zones} if b.routing.get("plane_fanout", True) else set()
    from .geom import pip

    def in_plane(net, x, y):
        for ln in sorted({z[0] for z in zones}):
            best = None
            for (l, prio, n, poly) in zones:
                if l == ln and pip(x, y, poly) and (best is None or prio > best[0]):
                    best = (prio, n)
            if best is not None and best[1] == net:
                return True
        return False
    vr, vdr, tw = st["via_dia"] / 2.0, st["via_drill"], st["track"]
    rr = b.rules
    if st["via_dia"] < rr.min_via_dia - 1e-9 or vdr < rr.min_via_drill - 1e-9 or tw < rr.min_track - 1e-9:
        from .model import DefinitionError
        raise DefinitionError("escape_via/escape_track below the board's minimum rules")
    layer_rr = [0]

    def skip(ref, it, why):
        stats["skipped"].append("%s.%s [%s]: %s" % (ref, it["num"], it["net"] or "-", why))
        stats["skipped_by_reason"][why] = stats["skipped_by_reason"].get(why, 0) + 1
        ps = stats["parts"].setdefault(ref, {})
        ps["skipped"] = ps.get("skipped", 0) + 1

    def commit(ref, it, path, via, layer, kind):
        net = it["net"]
        ni = bld.net(net)
        lid = pcbnew.F_Cu if layer == "F.Cu" else pcbnew.B_Cu
        for a, c in zip(path[:-1], path[1:]):
            if math.hypot(a[0] - c[0], a[1] - c[1]) < 1e-4:
                continue
            tr = pcbnew.PCB_TRACK(pcb)
            tr.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
            tr.SetEnd(pcbnew.VECTOR2I(MM(c[0]), MM(c[1])))
            tr.SetLayer(lid)
            tr.SetWidth(MM(path_w[0]))
            tr.SetNet(ni)
            tr.SetLocked(True)
            pcb.Add(tr)
            obs.add_seg(a, c, path_w[0], layer, net)
        if via is not None:
            v = pcbnew.PCB_VIA(pcb)
            v.SetPosition(pcbnew.VECTOR2I(MM(via[0]), MM(via[1])))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetWidth(pcbnew.F_Cu, MM(2 * vr))
            v.SetDrill(MM(vdr))
            v.SetNet(ni)
            v.SetLocked(True)
            pcb.Add(v)
            obs.add_via(via[0], via[1], vr, vdr, net)
        handled.add(pad_key(ref, it))
        ps = stats["parts"].setdefault(ref, {})
        ps[kind] = ps.get(kind, 0) + 1
        if kind in ("ring", "inward"):
            stats["vias"] += 1
            if kind == "inward":
                stats["inward"] += 1
            tl = st["layers"][layer_rr[0] % len(st["layers"])] if st["layers"] else "B.Cu"
            layer_rr[0] += 1
            stats.setdefault("via_target_layers", {})
            stats["via_target_layers"][tl] = stats["via_target_layers"].get(tl, 0) + 1
        else:
            stats["direct"] += 1

    path_w = [tw]

    def path_ok(path, layer, net, own):
        for a, c in zip(path[:-1], path[1:]):
            if math.hypot(a[0] - c[0], a[1] - c[1]) < 1e-4:
                continue
            if not obs.seg_ok(a, c, path_w[0], layer, net, own=own):
                return False
        return True

    pin_count = {n: len(p) for n, p in b._nets.items()}
    two_pad = {p.ref for p in b.parts if len([n for n in p.pin_net.values()]) == 2}
    for part in b.parts:
        ref = part.ref
        pads = obs.pads_by_ref.get(ref, [])
        info = analyse(pads)
        if not is_candidate(part, info, st):
            continue
        layer = "B.Cu" if part.side == "B" else "F.Cu"
        cx, cy = info["centre"]
        pitch = info["pitch"]
        has_ep = bool(info["ep"])
        ps = stats["parts"].setdefault(ref, {})
        ps.update({"pitch": round(pitch, 3), "pads": len(pads), "exposed_pad": has_ep})
        sides = {}
        for it in info["perim"]:
            w, h = it["rect"][2] - it["rect"][0], it["rect"][3] - it["rect"][1]
            if w > 1.3 * h:
                axis, sign = "x", (1 if it["cx"] > cx else -1)
            elif h > 1.3 * w:
                axis, sign = "y", (1 if it["cy"] > cy else -1)
            else:
                skip(ref, it, "no escape direction (square/round pad)")
                continue
            sides.setdefault((axis, sign), Side(axis, sign)).pads.append(it)
        queue = []      # (side, index, item, kind)
        for key in sorted(sides):
            sd = sides[key]
            lat = (lambda it: it["cy"]) if sd.axis == "x" else (lambda it: it["cx"])
            sd.pads.sort(key=lat)
            sd.lat = lat
            if sd.axis == "x":
                sd.tip = max(it["rect"][2] for it in sd.pads) if sd.sign > 0 else min(it["rect"][0] for it in sd.pads)
                sd.itip = min(it["rect"][0] for it in sd.pads) if sd.sign > 0 else max(it["rect"][2] for it in sd.pads)
            else:
                sd.tip = max(it["rect"][3] for it in sd.pads) if sd.sign > 0 else min(it["rect"][1] for it in sd.pads)
                sd.itip = min(it["rect"][1] for it in sd.pads) if sd.sign > 0 else max(it["rect"][3] for it in sd.pads)
            sd.c = sum(lat(it) for it in sd.pads) / len(sd.pads)
            for k, it in enumerate(sd.pads):
                queue.append((sd, k, it))
        # per-side stub geometry (clearance of the widest net class present on the side)
        for sd in sides.values():
            nets = sorted({it["net"] for it in sd.pads})
            sd.clr = max(obs.clr(n1, n2) for n1 in nets for n2 in nets) + 0.005
            sd.e1 = tw / 2.0 + sd.clr + 0.01
        own_court = (ref,)

        def ring_path(sd, it, V, R):
            L = sd.lat(it)
            p0 = (it["cx"], it["cy"])
            p1 = sd.xy(sd.tip, L, sd.e1)
            rb = sd.e1 + abs(V - L) / TAN_FAN
            if rb > R + 1e-9:
                return None
            pts = [p0, p1]
            if abs(V - L) > 1e-6:
                pts.append(sd.xy(sd.tip, V, rb))
            pts.append(sd.xy(sd.tip, V, R))
            return pts

        def inward_path(sd, it, V, R):
            L = sd.lat(it)
            p0 = (it["cx"], it["cy"])
            e1 = sd.e1
            # radial coordinate measured from the inner tip towards the package centre
            def ixy(lat, rad):
                if sd.axis == "x":
                    return (sd.itip - sd.sign * rad, lat)
                return (lat, sd.itip - sd.sign * rad)
            rb = e1 + abs(V - L) / TAN_FAN
            if rb > R + 1e-9:
                return None
            pts = [p0, ixy(L, e1)]
            if abs(V - L) > 1e-6:
                pts.append(ixy(V, rb))
            pts.append(ixy(V, R))
            return pts

        def try_via(it, path, plane):
            if path is None:
                it["_why"] = "stub angle"
                return False
            vx, vy = path[-1]
            if plane and not in_plane(it["net"], vx, vy):
                it["_why"] = "outside own plane"
                return False
            if not obs.via_ok(vx, vy, vr, vdr, it["net"], courtyard_ignore=own_court):
                it["_why"] = obs.why
                return False
            if not path_ok(path, layer, it["net"], {id(it)}):
                it["_why"] = obs.why
                return False
            return True

        # classify pads
        work = []
        for sd, k, it in queue:
            net = it["net"]
            if not net:
                skip(ref, it, "no net (not connected)")
                continue
            if pin_count.get(net, 0) < 2:
                skip(ref, it, "not connected (single-pin net)")
                continue
            members = b._nets.get(net, [])
            if all(r2 == ref for r2, _ in members):
                others = [p for p in pads if p["net"] == net and p is not it]
                if others and all(math.hypot(o["cx"] - it["cx"], o["cy"] - it["cy"]) < 1.6 * pitch for o in others):
                    skip(ref, it, "connects only to an adjacent pad of the same part")
                    continue
            plane = net in plane_nets
            work.append((sd, k, it, plane))
        # 1) plane pads under the package (no exposed pad)
        rest = []
        for sd, k, it, plane in work:
            if plane and not has_ep:
                done = False
                L = sd.lat(it)
                for R in (sd.e1 + vr + 0.25, sd.e1 + vr + 0.6, sd.e1 + vr + 1.0, sd.e1 + vr + 1.5, sd.e1 + vr + 2.0):
                    for dv in (0.0, 0.25, -0.25, 0.5, -0.5):
                        path_w[0] = tw
                        p = inward_path(sd, it, L + dv, R)
                        if try_via(it, p, True):
                            commit(ref, it, p, p[-1], layer, "inward")
                            done = True
                            break
                    if done:
                        break
                if done:
                    continue
            rest.append((sd, k, it, plane))
        # 2) direct short pre-route to an adjacent two-pad passive
        ring = []
        for sd, k, it, plane in rest:
            if plane or not st["direct"]:
                ring.append((sd, k, it, plane))
                continue
            done = False
            tip = sd.xy(sd.tip, sd.lat(it), 0.0)
            cands = []
            for r2, pin in b._nets.get(it["net"], []):
                if r2 == ref or r2 not in two_pad:
                    continue
                for tp in obs.pads_by_ref.get(r2, []):
                    if tp["num"] == pin and tp["net"] == it["net"] and layer in tp["layers"]:
                        d = math.hypot(tp["cx"] - tip[0], tp["cy"] - tip[1])
                        if d <= DIRECT_MAX:
                            cands.append((d, r2, tp))
            cands.sort(key=lambda c: (c[0], c[1]))
            for d, r2, tp in cands:
                p0 = (it["cx"], it["cy"])
                p1 = sd.xy(sd.tip, sd.lat(it), sd.e1)
                tq = (tp["cx"], tp["cy"])
                # straight on, or radial-then-diagonal, or one 90-degree corner
                opts = [[p0, p1, tq]]
                if sd.axis == "x":
                    opts.append([p0, p1, (tq[0], p1[1]), tq])
                    opts.append([p0, p1, (p1[0], tq[1]), tq])
                    dxy = abs(tq[1] - p1[1])
                    opts.append([p0, p1, (tq[0] - sd.sign * dxy, p1[1]), tq])
                else:
                    opts.append([p0, p1, (p1[0], tq[1]), tq])
                    opts.append([p0, p1, (tq[0], p1[1]), tq])
                    dxy = abs(tq[0] - p1[0])
                    opts.append([p0, p1, (p1[0], tq[1] - sd.sign * dxy), tq])
                for pth in opts:
                    path_w[0] = tw
                    if path_ok(pth, layer, it["net"], {id(it), id(tp)}):
                        commit(ref, it, pth, None, layer, "direct")
                        it["_direct"] = "%s.%s" % (r2, tp["num"])
                        done = True
                        break
                if done:
                    break
            if not done:
                ring.append((sd, k, it, plane))
        # 3) ring.  Row = pad index parity on its side.  Lateral via positions are spread
        #    (fanned) so that the stub of a row-1 via passes between its two row-0 neighbours
        #    with full clearance: spacing q between neighbours = via radius + half stub +
        #    clearance of the two nets (pairs where one pad needs no ring via keep the pad pitch).
        in_ring = {id(w[2]) for w in ring}
        for sd in sides.values():
            n = len(sd.pads)
            need = [id(it) in in_ring for it in sd.pads]
            pos = [0.0]
            qmin = None
            for k in range(1, n):
                a, c2 = sd.pads[k - 1], sd.pads[k]
                gap = sd.lat(c2) - sd.lat(a)
                if need[k - 1] and need[k]:
                    qk = vr + tw / 2.0 + obs.clr(a["net"], c2["net"]) + 0.01
                    qmin = qk if qmin is None else min(qmin, qk)
                    gap = max(gap, qk)
                pos.append(pos[-1] + gap)
            shift = (sum(sd.lat(it) for it in sd.pads) / n) - (sum(pos) / n)
            sd.V = {id(it): pos[k] + shift for k, it in enumerate(sd.pads)}
            # row 0 radius: fan angle limit, pad clearance, and the start of every row-1 stub
            # (at the pad, before it turns) must clear the neighbouring row-0 vias
            r0 = max(vr + sd.clr + 0.02, sd.e1 + max(abs(sd.V[id(it)] - sd.lat(it)) for it in sd.pads) / TAN_FAN)
            for k, it in enumerate(sd.pads):
                if k % 2 == 1 and need[k]:
                    L, V = sd.lat(it), sd.V[id(it)]
                    rb = sd.e1 + abs(V - L) / TAN_FAN
                    for j in (k - 1, k + 1):
                        if 0 <= j < n and need[j]:
                            nd = vr + tw / 2.0 + obs.clr(it["net"], sd.pads[j]["net"]) + 0.005
                            Vj = sd.V[id(sd.pads[j])]
                            # smallest r0 at which via j clears the slanted part of stub k
                            # (the radial part passes at the lateral spacing q >= nd)
                            while r0 < sd.e1 + 4.0 and pt_seg(Vj, r0, L, sd.e1, V, rb) < nd:
                                r0 += 0.01
            sd.r0 = r0
            q = qmin if qmin is not None else pitch
            sd.dr = max(math.sqrt(max(0.0, (2 * vr + sd.clr) ** 2 - q * q)), vdr + rr.min_hole_to_hole) + 0.03
        path_w[0] = tw
        left = []
        for parity in (0, 1):
            for sd, k, it, plane in ring:
                if k % 2 != parity:
                    continue
                V = sd.V[id(it)]
                R = sd.r0 + parity * sd.dr
                p = ring_path(sd, it, V, R)
                if try_via(it, p, plane):
                    commit(ref, it, p, p[-1], layer, "ring")
                else:
                    it["_why0"] = "%s path=%s r0=%.3f dr=%.3f e1=%.3f" % (it.get("_why"), [(round(a, 3), round(c, 3)) for a, c in (p or [])], sd.r0, sd.dr, sd.e1)
                    left.append((sd, k, it, plane))
        left.sort(key=lambda w: (w[0].axis, w[0].sign, w[1]))
        for sd, k, it, plane in left:
            Vp = sd.V[id(it)]
            cands = []
            for m in range(0, 6):
                R = sd.r0 + m * sd.dr * 0.5
                for j in range(-12, 13):
                    V = Vp + j * 0.1
                    cands.append((R - sd.r0 + 0.6 * abs(j * 0.1), round(R, 4), round(V, 4)))
            cands.sort()
            done = False
            for _, R, V in cands:
                p = ring_path(sd, it, V, R)
                if try_via(it, p, plane):
                    commit(ref, it, p, p[-1], layer, "ring")
                    done = True
                    break
            if not done and not has_ep:
                L = sd.lat(it)
                for R in (sd.e1 + vr + 0.25, sd.e1 + vr + 0.6, sd.e1 + vr + 1.0, sd.e1 + vr + 1.5, sd.e1 + vr + 2.0, sd.e1 + vr + 2.5):
                    for dv in (0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75):
                        p = inward_path(sd, it, L + dv, R)
                        if try_via(it, p, plane):
                            commit(ref, it, p, p[-1], layer, "inward")
                            done = True
                            break
                    if done:
                        break
            if not done:
                skip(ref, it, "no legal escape position" + (" inside its own plane polygon" if plane else ""))
                stats.setdefault("debug", []).append("%s.%s planned: %s; last: %s" % (ref, it["num"], it.get("_why0"), it.get("_why")))
    return stats, handled


def pad_key(ref, it):
    return (ref, it["num"], round(it["cx"], 3), round(it["cy"], 3))
