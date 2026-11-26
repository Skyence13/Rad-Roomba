"""Auto-arrange helper for parts without an explicit ``at=``.

Greedy, connectivity-driven placement on an occupancy grid:
  * every part is a courtyard rectangle (per rotation), kept ``clearance`` away
    from other courtyards and ``edge_margin`` inside the outline, clear of
    cut-outs, mounting-hole keep-outs and footprint keep-out areas;
  * each functional group gets a region of the board (area-proportional slicing),
    parts are pulled towards pads they connect to (signal nets), towards their
    ``near=`` target, towards a board ``edge=``, and weakly towards their group
    region; rail-to-rail capacitors are spread over the supply pins of the ICs
    in their group;
  * ICs (>= 16 pads) keep a larger halo (``ic_halo``) from each other so that
    there is room for fan-out and decoupling.
It is a starting point for the engineer, not an optimiser: freeze good results
by copying reports/placement.txt values into ``at=``.
"""
import numpy as np
import pcbnew

from .model import DefinitionError

BIG_PADS = 16


def _point_in_poly(px, py, poly):
    inside = np.zeros(px.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        cond = ((y1 > py) != (y2 > py)) & (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1)
        inside ^= cond
    return inside


class Placer:
    def __init__(self, bld):
        self.bld = bld
        self.b = bld.b
        self.fr = bld.fr
        o = self.b.autoplace
        self.g = float(o["grid"])
        self.clear = float(o["clearance"])
        self.halo = float(o["ic_halo"])
        self.edge = float(o["edge_margin"])
        from .pcb import outline_bbox
        x0, y0, x1, y1 = outline_bbox(self.b)
        self.kx0, self.ky0 = self.fr.ox + x0, self.fr.oy - y1
        self.w, self.h = x1 - x0, y1 - y0
        self.nx = int(np.ceil(self.w / self.g))
        self.ny = int(np.ceil(self.h / self.g))
        cx = self.kx0 + (np.arange(self.nx) + 0.5) * self.g
        cy = self.ky0 + (np.arange(self.ny) + 0.5) * self.g
        PX, PY = np.meshgrid(cx, cy)
        kpoly = [self.fr.kmm(*p) for p in bld.outline_dense]
        outside = ~_point_in_poly(PX, PY, kpoly)
        for cp in bld.cutout_polys:
            outside |= _point_in_poly(PX, PY, [self.fr.kmm(*p) for p in cp])
        self.outside = outside
        self.PX, self.PY = PX, PY
        base = np.zeros((self.ny, self.nx), dtype=bool)
        for ko in self.b.keepouts:
            if ko.get("footprints") and "_pts" in ko:
                base |= _point_in_poly(PX, PY, [self.fr.kmm(*p) for p in ko["_pts"]])
        for h in self.b.holes:
            r = (h["keepout"] / 2.0) if h["keepout"] else (max(h["drill"], h["pad"] or 0) / 2.0 + 0.5)
            hx, hy = self.fr.kmm(h["x"], h["y"])
            base |= ((PX - hx) ** 2 + (PY - hy) ** 2) <= (r + self.g * 0.75) ** 2
        self.occA = {"F": base.copy(), "B": base.copy()}   # courtyards + clearance
        self.occB = {"F": base.copy(), "B": base.copy()}   # courtyards + IC halo
        self.net_pads = {}    # net -> [(x, y)] of placed pads (KiCad mm)
        self.pad_pos = {}     # (ref, padnumber) -> (x, y)
        self.centre = {}      # ref -> (x, y)
        self._sat = {}

    # ----------------------------------------------------------- measuring
    def measure(self, part, rot, side):
        """Courtyard bbox and pad offsets relative to the footprint origin (KiCad mm, y down)."""
        fp = self.bld.fps[part.ref]
        origin = pcbnew.VECTOR2I(0, 0)
        if side == "B" and not fp.IsFlipped():
            fp.SetPosition(origin)
            fp.Flip(origin, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(origin)
        fp.SetOrientationDegrees(rot)
        return self._measure_fp(fp)

    def _measure_fp(self, fp):
        fp.BuildCourtyardCaches()
        pos = fp.GetPosition()
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        tht = False
        pads = []
        xs, ys = [], []
        for pad in fp.Pads():
            p = pad.GetPosition()
            bb = pad.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
            if pad.GetDrillSize().x > 0:
                tht = True
            pads.append((pad.GetNumber(), pad.GetNetname(), pcbnew.ToMM(p.x - pos.x), pcbnew.ToMM(p.y - pos.y)))
        if cy.OutlineCount() > 0:
            bb = cy.BBox()
            rect = (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())
        elif xs:
            rect = (min(xs), min(ys), max(xs), max(ys))
        else:
            rect = (pos.x - MMI(1), pos.y - MMI(1), pos.x + MMI(1), pos.y + MMI(1))
        rect = (pcbnew.ToMM(rect[0] - pos.x), pcbnew.ToMM(rect[1] - pos.y),
                pcbnew.ToMM(rect[2] - pos.x), pcbnew.ToMM(rect[3] - pos.y))
        return rect, pads, tht

    # ------------------------------------------------------------ occupancy
    def _mark_arr(self, arr, x0, y0, x1, y1):
        g = self.g
        i0 = max(0, int(np.floor((x0 - self.kx0) / g)))
        i1 = min(self.nx, int(np.ceil((x1 - self.kx0) / g)))
        j0 = max(0, int(np.floor((y0 - self.ky0) / g)))
        j1 = min(self.ny, int(np.ceil((y1 - self.ky0) / g)))
        if i1 > i0 and j1 > j0:
            arr[j0:j1, i0:i1] = True

    def mark(self, ref, X, Y, rect, pads, tht, side, clearance=None):
        x0, y0, x1, y1 = X + rect[0], Y + rect[1], X + rect[2], Y + rect[3]
        sides = ("F", "B") if tht else (side,)
        for s in sides:
            c = self.clear if clearance is None else clearance
            self._mark_arr(self.occA[s], x0 - c, y0 - c, x1 + c, y1 + c)
            hb = self.halo
            self._mark_arr(self.occB[s], x0 - hb, y0 - hb, x1 + hb, y1 + hb)
        self._sat.clear()
        for num, net, dx, dy in pads:
            self.pad_pos[(ref, num)] = (X + dx, Y + dy)
            if net:
                self.net_pads.setdefault(net, []).append((X + dx, Y + dy))
        self.centre[ref] = (X + (rect[0] + rect[2]) / 2.0, Y + (rect[1] + rect[3]) / 2.0)

    def sat(self, key, arr):
        if key not in self._sat:
            s = np.zeros((self.ny + 1, self.nx + 1), dtype=np.int32)
            s[1:, 1:] = np.cumsum(np.cumsum(arr.astype(np.int32), axis=0), axis=1)
            self._sat[key] = s
        return self._sat[key]

    def free(self, S, rect, margin):
        """Boolean map over lattice origins (j, i): rect (expanded by margin) covers no blocked cell."""
        g = self.g
        a0 = int(np.floor((rect[0] - margin) / g + 1e-9))
        a1 = int(np.ceil((rect[2] + margin) / g - 1e-9))
        b0 = int(np.floor((rect[1] - margin) / g + 1e-9))
        b1 = int(np.ceil((rect[3] + margin) / g - 1e-9))
        out = np.zeros((self.ny + 1, self.nx + 1), dtype=bool)
        ilo, ihi = max(0, -a0), min(self.nx, self.nx - a1)
        jlo, jhi = max(0, -b0), min(self.ny, self.ny - b1)
        if ihi < ilo or jhi < jlo:
            return out
        J = slice(jlo, jhi + 1)
        I = slice(ilo, ihi + 1)

        def sh(sl, d):
            return slice(sl.start + d, sl.stop + d)
        tot = S[sh(J, b1), sh(I, a1)] - S[sh(J, b0), sh(I, a1)] - S[sh(J, b1), sh(I, a0)] + S[sh(J, b0), sh(I, a0)]
        out[J, I] = tot == 0
        return out

    # --------------------------------------------------------------- regions
    def regions(self, todo):
        groups = {}
        for part in todo:
            rect, _, _ = self.meas[part.ref][self.rots(part)[0]]
            groups.setdefault(part.group.name, 0.0)
            groups[part.group.name] += (rect[2] - rect[0] + 1.0) * (rect[3] - rect[1] + 1.0)
        order = [g.name for g in self.b.groups if g.name in groups]
        out = {}

        def split(names, x0, y0, x1, y1):
            if len(names) == 1:
                out[names[0]] = (x0, y0, x1, y1)
                return
            total = sum(groups[n] for n in names)
            acc, k = 0.0, 0
            for k, n in enumerate(names[:-1]):
                acc += groups[n]
                if acc >= total / 2.0:
                    break
            a, bnames = names[:k + 1], names[k + 1:]
            fa = sum(groups[n] for n in a) / total
            if (x1 - x0) >= (y1 - y0):
                xm = x0 + (x1 - x0) * fa
                split(a, x0, y0, xm, y1)
                split(bnames, xm, y0, x1, y1)
            else:
                ym = y0 + (y1 - y0) * fa
                split(a, x0, y0, x1, ym)
                split(bnames, x0, ym, x1, y1)
        if order:
            split(order, self.kx0, self.ky0, self.kx0 + self.w, self.ky0 + self.h)
        return out

    def rots(self, part):
        if getattr(part, "auto_rot", None) is not None:
            return (float(part.auto_rot),)
        return tuple(float(r) for r in self.b.autoplace["rotations"])

    # ------------------------------------------------------------------- run
    def run(self):
        b = self.b
        todo = [p for p in b.parts if not p.placed and not p.replica_of]
        # occupancy of explicitly placed parts
        for part in b.parts:
            if part.placed:
                fp = self.bld.fps[part.ref]
                rect, pads, tht = self._measure_fp(fp)
                pos = fp.GetPosition()
                self.mark(part.ref, pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), rect, pads, tht, part.side)
        if not todo:
            return []
        self.meas = {}
        npads = {}
        for part in todo:
            self.meas[part.ref] = {r: self.measure(part, r, part.side) for r in self.rots(part)}
            npads[part.ref] = len(self.meas[part.ref][self.rots(part)[0]][1])
        regions = self.regions(todo)
        self._assign_decoupling(todo, npads)
        # per-group spreading clearance: use ~"spread" of the group's region area
        spread = float(b.autoplace.get("spread", 0.35))
        gclear = {}
        for gname, reg in regions.items():
            dims = []
            for part in todo:
                if part.group.name == gname and not (part.near or getattr(part, "_auto_near", None)) \
                        and npads[part.ref] < BIG_PADS:
                    r = self.meas[part.ref][self.rots(part)[0]][0]
                    dims.append((r[2] - r[0], r[3] - r[1]))
            area = (reg[2] - reg[0]) * (reg[3] - reg[1]) * spread
            lo, hi = self.clear, 2.5
            for _ in range(20):
                mid = (lo + hi) / 2.0
                if sum((w + 2 * mid) * (h + 2 * mid) for w, h in dims) > area:
                    hi = mid
                else:
                    lo = mid
            gclear[gname] = lo
        fanout = {n: len(p) for n, p in b._nets.items()}
        order = ([p for p in todo if p.edge] +
                 sorted([p for p in todo if not p.edge and npads[p.ref] >= BIG_PADS], key=lambda p: -npads[p.ref]) +
                 [p for p in todo if not p.edge and npads[p.ref] < BIG_PADS])
        pending = list(order)
        placed = []
        gx = self.kx0 + np.arange(self.nx + 1) * self.g
        gy = self.ky0 + np.arange(self.ny + 1) * self.g
        guard = 0
        while pending:
            guard += 1
            progressed = False
            for part in list(pending):
                near = self._near_point(part)
                if near == "wait" and guard < 4:
                    continue
                if near == "wait":
                    near = None
                big = npads[part.ref] >= BIG_PADS
                best = None
                for rot in self.rots(part):
                    rect, pads, tht = self.meas[part.ref][rot]
                    sides = ("F", "B") if tht else (part.side,)
                    ok = self.free(self.sat("out", self.outside), rect, self.edge)
                    for s in sides:
                        occ = self.occB[s] if big else self.occA[s]
                        ok &= self.free(self.sat(("B" if big else "A") + s, occ), rect, 0.0)
                    if not ok.any():
                        continue
                    reg = regions.get(part.group.name)
                    if reg is not None and not part.edge and near is None:
                        cxo, cyo = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
                        inx = (gx + cxo >= reg[0]) & (gx + cxo <= reg[2])
                        iny = (gy + cyo >= reg[1]) & (gy + cyo <= reg[3])
                        okr = ok & (iny[:, None] & inx[None, :])
                        if okr.any():
                            ok = okr
                    fx = np.zeros(self.nx + 1)
                    fy = np.zeros(self.ny + 1)
                    cxo, cyo = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
                    wsum = 0.0
                    for num, net, dx, dy in pads:
                        if not net or net in b.rails or fanout.get(net, 0) > 12:
                            continue
                        pts = self.net_pads.get(net)
                        if not pts:
                            continue
                        tx = sum(p[0] for p in pts) / len(pts)
                        ty = sum(p[1] for p in pts) / len(pts)
                        fx += (gx + dx - tx) ** 2
                        fy += (gy + dy - ty) ** 2
                        wsum += 1.0
                    if near is not None:
                        (tx, ty), npad = near
                        dx, dy = cxo, cyo
                        if npad is not None:
                            for num, net, pdx, pdy in pads:
                                if net == npad:
                                    dx, dy = pdx, pdy
                                    break
                        fx += 4.0 * (gx + dx - tx) ** 2
                        fy += 4.0 * (gy + dy - ty) ** 2
                        wsum += 4.0
                    if reg is not None:
                        rw = 1.0 if wsum == 0 else (0.5 if part.edge else 0.03)
                        fx += rw * (gx + cxo - (reg[0] + reg[2]) / 2.0) ** 2
                        fy += rw * (gy + cyo - (reg[1] + reg[3]) / 2.0) ** 2
                    if part.edge:
                        e = part.edge.lower()
                        if e == "left":
                            fx += 50.0 * (gx + rect[0] - self.kx0) ** 2
                        elif e == "right":
                            fx += 50.0 * (gx + rect[2] - (self.kx0 + self.w)) ** 2
                        elif e == "top":
                            fy += 50.0 * (gy + rect[1] - self.ky0) ** 2
                        elif e == "bottom":
                            fy += 50.0 * (gy + rect[3] - (self.ky0 + self.h)) ** 2
                        else:
                            raise DefinitionError("%s: edge must be left/right/top/bottom" % part.ref)
                    cost = fy[:, None] + fx[None, :]
                    cost = np.where(ok, cost, np.inf)
                    idx = int(np.argmin(cost))
                    j, i = divmod(idx, self.nx + 1)
                    c = float(cost[j, i])
                    if best is None or c < best[0] - 1e-9:
                        best = (c, rot, i, j)
                if best is None:
                    raise DefinitionError(
                        "auto-arrange: no room for %s (%s) on side %s - enlarge the board, reduce "
                        "autoplace clearance/ic_halo, or place it explicitly" % (part.ref, part.footprint, part.side))
                _, rot, i, j = best
                X, Y = float(gx[i]), float(gy[j])
                rect, pads, tht = self.meas[part.ref][rot]
                self.bld.place(part, round(X - self.fr.ox, 4), round(self.fr.oy - Y, 4), rot, part.side)
                part.auto_placed = True
                tight = big or part.near or getattr(part, "_auto_near", None)
                self.mark(part.ref, X, Y, rect, pads, tht, part.side,
                          None if tight else gclear.get(part.group.name))
                placed.append(part.ref)
                pending.remove(part)
                progressed = True
            if not progressed and guard >= 4:
                raise DefinitionError("auto-arrange: unresolved near= targets: %s" % ", ".join(p.ref for p in pending))
        return placed

    def _near_point(self, part):
        """((x, y), net-or-None) | None | "wait" (target not placed yet)."""
        near = part.near or getattr(part, "_auto_near", None)
        if not near:
            return None
        if "." in near:
            ref, pad = near.split(".", 1)
            if ref not in self.b._refs:
                raise DefinitionError("%s: near='%s' - unknown part" % (part.ref, near))
            if (ref, pad) not in self.pad_pos:
                if ref in self.centre:
                    raise DefinitionError("%s: near='%s' - %s has no pad %s" % (part.ref, near, ref, pad))
                return "wait"
            net = self.b.part(ref).pin_net.get(pad)
            return (self.pad_pos[(ref, pad)], net)
        if near not in self.b._refs:
            raise DefinitionError("%s: near='%s' - unknown part" % (part.ref, near))
        if near not in self.centre:
            return "wait"
        return (self.centre[near], None)

    def _assign_decoupling(self, todo, npads):
        b = self.b
        gnd = {n for n, r in b.rails.items() if r["style"] == "gnd"}
        for g in b.groups:
            ics = [p for p in g.parts if len(p.pin_net) >= 8]
            if not ics:
                continue
            slots = {}   # supply net -> [[count, "REF.pad"]]
            for ic in ics:
                seen = set()
                for num, net in ic.pin_net.items():
                    if net in b.rails and net not in gnd and (net, num) not in seen:
                        seen.add((net, num))
                        slots.setdefault(net, []).append([0, "%s.%s" % (ic.ref, num)])
            for part in g.parts:
                if part.placed or part.near or len(part.pin_net) != 2:
                    continue
                ns = list(part.pin_net.values())
                if not all(n in b.rails for n in ns if n) or None in ns:
                    continue
                sup = [n for n in ns if n not in gnd]
                if len(sup) != 1 or sup[0] not in slots:
                    continue
                slot = min(slots[sup[0]], key=lambda s: s[0])
                slot[0] += 1
                part._auto_near = slot[1]


def MMI(v):
    return pcbnew.FromMM(v)


def autoplace(bld):
    """Place every part that has no explicit position.  Returns the refs placed."""
    placer = Placer(bld)
    placed = placer.run()
    return placed
