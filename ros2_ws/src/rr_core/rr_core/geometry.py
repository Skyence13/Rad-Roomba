"""Planar geometry for footprints and coverage (metres, radians, map frame of
contract.yaml `frames.map_frame`).  All head geometry comes from the DESCRIPTOR
(head_mount frame) and the mount transform of the attachment manifest /
mechanical/common/frames.yaml - never from literals (DEC-041).

No ROS imports.
"""
from __future__ import annotations

import math

import numpy as np


def rot(yaw: float) -> np.ndarray:
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def transform(pose, pts) -> np.ndarray:
    """Apply a planar pose (x, y, yaw) to Nx2 points."""
    pts = np.asarray(pts, dtype=float)
    return pts @ rot(pose[2]).T + np.array([pose[0], pose[1]])


def wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def polygon_area(poly) -> float:
    p = np.asarray(poly, dtype=float)
    if len(p) < 3:
        return 0.0
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def ensure_ccw(poly) -> np.ndarray:
    p = np.asarray(poly, dtype=float)
    return p if polygon_area(p) > 0 else p[::-1].copy()


def erode_convex(poly, margin: float) -> np.ndarray | None:
    """Inward offset of a convex polygon by `margin` (position-uncertainty
    allowance, design 0.3 ch.7 "shrink the footprint credited toward coverage").
    Returns None when nothing is left."""
    p = ensure_ccw(poly)
    if margin <= 0:
        return p
    n = len(p)
    lines = []
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        d = b - a
        length = math.hypot(*d)
        normal = np.array([-d[1], d[0]]) / length      # inward for CCW
        lines.append((a + normal * margin, d / length))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            return None
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append(p1 + d1 * t)
    out = np.array(out)
    if polygon_area(out) <= 0:
        return None
    # the offset polygon must keep the orientation of every edge
    for i in range(n):
        if np.dot(out[(i + 1) % n] - out[i], p[(i + 1) % n] - p[i]) <= 0:
            return None
    return out


def clip_convex(subject, clip) -> np.ndarray:
    """Sutherland-Hodgman: intersection of a polygon with a convex CCW clip polygon."""
    out = [tuple(q) for q in np.asarray(subject, dtype=float)]
    c = ensure_ccw(clip)
    for i in range(len(c)):
        a, b = c[i], c[(i + 1) % len(c)]
        inp, out = out, []
        if not inp:
            break
        ex, ey = b[0] - a[0], b[1] - a[1]

        def side(q):
            return ex * (q[1] - a[1]) - ey * (q[0] - a[0])
        prev = inp[-1]
        sp = side(prev)
        for cur in inp:
            sc = side(cur)
            if (sc >= 0) != (sp >= 0):
                f = sp / (sp - sc)
                out.append((prev[0] + f * (cur[0] - prev[0]), prev[1] + f * (cur[1] - prev[1])))
            if sc >= 0:
                out.append(cur)
            prev, sp = cur, sc
    return np.array(out, dtype=float).reshape(-1, 2)


def inside_convex(poly, X, Y) -> np.ndarray:
    """Boolean mask of points (arrays X, Y) inside a convex polygon (boundary counts)."""
    p = ensure_ccw(poly)
    mask = np.ones(np.shape(X), dtype=bool)
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        mask &= (b[0] - a[0]) * (Y - a[1]) - (b[1] - a[1]) * (X - a[0]) >= -1e-12
    return mask


def point_in_polygon(poly, x: float, y: float) -> bool:
    p = np.asarray(poly, dtype=float)
    inside = False
    j = len(p) - 1
    for i in range(len(p)):
        if (p[i, 1] > y) != (p[j, 1] > y):
            if x < (p[j, 0] - p[i, 0]) * (y - p[i, 1]) / (p[j, 1] - p[i, 1]) + p[i, 0]:
                inside = not inside
        j = i
    return inside


# ------------------------------------------------------------------ head / body
def mount_pose(mount: dict):
    """(x, y, yaw) of head_mount in base_link from {"xyz_m":[..], "rpy_rad":[..]}."""
    xyz = mount.get("xyz_m") or mount.get("xyz")
    rpy = mount.get("rpy_rad") or mount.get("rpy") or [0, 0, 0]
    return float(xyz[0]), float(xyz[1]), float(rpy[2])


def lane_polygons(descriptor: dict, mount: dict) -> list:
    """Aperture polygons of the four lanes in base_link (xy projection), from the
    transmitted descriptor through the robot-side mount transform."""
    pose = mount_pose(mount)
    return [ensure_ccw(transform(pose, [pt[:2] for pt in seg["sensitive_polygon_m"]]))
            for seg in descriptor["segments"]]


def lane_centers(descriptor: dict, mount: dict) -> np.ndarray:
    pose = mount_pose(mount)
    return transform(pose, [seg["center_m"][:2] for seg in descriptor["segments"]])


class RobotOutline:
    """Plan-view outline of body + projecting head in base_link, as convex parts.

    Source of the numbers: mechanical/common/frames.yaml `footprint`
    (body_x_m, head_envelope_m) and contract `frames.body_rev_e.shell_envelope_mm`.
    Parameterised; nothing downstream uses literals.
    """

    def __init__(self, body_x, body_half_width, head_x, head_half_width, turn_radius=None, source="caller"):
        self.body_x, self.body_half_width = tuple(body_x), float(body_half_width)
        self.head_x, self.head_half_width = tuple(head_x), float(head_half_width)
        self.source = source
        bw, hw = self.body_half_width, self.head_half_width
        self.parts = [
            np.array([[body_x[0], -bw], [body_x[1], -bw], [body_x[1], bw], [body_x[0], bw]]),
            np.array([[head_x[0], -hw], [head_x[1], -hw], [head_x[1], hw], [head_x[0], hw]]),
        ]
        self.points = np.vstack(self.parts)
        # In-place turn clearance: the contract swept radius when given (rounded tail), else the
        # bounding rectangles (conservative).  Route-hold sweeps always use the rectangles.
        self.rect_radius = float(np.max(np.hypot(self.points[:, 0], self.points[:, 1])))
        self.turn_radius = float(turn_radius) if turn_radius else self.rect_radius
        self.front, self.rear = float(head_x[1]), float(body_x[0])
        self.half_width = max(bw, hw)

    def at(self, pose, margin: float = 0.0) -> list:
        """Convex parts at a pose, each grown by `margin` (rectangles: exact for axis growth)."""
        out = []
        for part in self.parts:
            p = part.copy()
            if margin:
                c = p.mean(axis=0)
                p = p + np.sign(p - c) * margin
            out.append(transform(pose, p))
        return out

    def as_dict(self):
        return {"body_x": list(self.body_x), "body_half_width": self.body_half_width,
                "head_x": list(self.head_x), "head_half_width": self.head_half_width,
                "turn_radius": self.turn_radius, "rect_radius": self.rect_radius, "source": self.source}


def swept_parts(outline: RobotOutline, pose, move: dict, margin: float, step: float = 0.02) -> list:
    """Convex pieces covering the region swept by a commanded primitive.

    move = {"kind": "straight", "dist": signed metres}  or  {"kind": "pivot", "angle": signed rad}.
    Sampling pitch `step` (m, or the equivalent arc at the turn radius); each
    sample is the grown outline, so the union over-covers by < step.
    """
    x, y, yaw = pose
    poses = []
    if move["kind"] == "straight":
        dist = move["dist"]
        n = max(1, int(math.ceil(abs(dist) / step)))
        for i in range(n + 1):
            d = dist * i / n
            poses.append((x + d * math.cos(yaw), y + d * math.sin(yaw), yaw))
    else:
        ang = move["angle"]
        n = max(1, int(math.ceil(abs(ang) * outline.rect_radius / step)))
        for i in range(n + 1):
            poses.append((x, y, yaw + ang * i / n))
    parts = []
    for p in poses:
        parts += outline.at(p, margin)
    return parts


def points_in_parts(parts, pts) -> np.ndarray:
    pts = np.asarray(pts, dtype=float).reshape(-1, 2)
    mask = np.zeros(len(pts), dtype=bool)
    if len(pts) == 0:
        return mask
    for part in parts:
        lo, hi = part.min(axis=0), part.max(axis=0)
        cand = (pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) & (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1])
        if cand.any():
            idx = np.nonzero(cand)[0]
            mask[idx[inside_convex(part, pts[idx, 0], pts[idx, 1])]] = True
    return mask


def convex_hull(points) -> np.ndarray:
    """CCW convex hull (Andrew's monotone chain) of Nx2 points."""
    pts = sorted(set((round(float(p[0]), 12), round(float(p[1]), 12)) for p in np.asarray(points, float)))
    if len(pts) <= 2:
        return np.array(pts, float)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1], float)


def rect_clip_area(poly, x0, x1, y0, y1) -> float:
    """Area of a convex polygon inside the axis-aligned rectangle [x0, x1] x [y0, y1] (exact, Sutherland-Hodgman)."""
    p = [tuple(q) for q in np.asarray(poly, float)]
    for axis, bound, keep_ge in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        if not p:
            return 0.0
        out = []
        for i in range(len(p)):
            a, b = p[i - 1], p[i]
            ina = (a[axis] >= bound) if keep_ge else (a[axis] <= bound)
            inb = (b[axis] >= bound) if keep_ge else (b[axis] <= bound)
            if inb:
                if not ina:
                    f = (bound - a[axis]) / (b[axis] - a[axis])
                    out.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
                out.append(b)
            elif ina:
                f = (bound - a[axis]) / (b[axis] - a[axis])
                out.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
        p = out
    return abs(polygon_area(p)) if len(p) >= 3 else 0.0
