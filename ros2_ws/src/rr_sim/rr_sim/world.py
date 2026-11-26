"""Kinematic trailer world for simulation (no Gazebo).

Rectangular trailer walls and box obstacles -> simulated LaserScan with range
noise and dropouts; synthetic contamination patches and a spatially varying
photon background -> expected count rates per lane (stimulus for the head
emulator); a movable "person" box; rear-proximity occupancy for the chassis
emulator's environment input.  All numbers are simulation parameters.
"""
from __future__ import annotations

import math

import numpy as np

from rr_core.geometry import clip_convex, polygon_area, transform


class World:
    def __init__(self, length_m, width_m, calibration, lane_polys_base, seed=1, door_closed=True, door_target_x_m=None,
                 lidar_xy=(-0.15, 0.0), fov_deg=270.0, n_rays=541, range_sigma=0.005, dropout=0.02,
                 range_max=12.0, ref_rate=(4.0, 1.5, 0.0), alpha_bkg=0.02):
        self.L, self.W = length_m, width_m
        self.cal, self.lanes = calibration, [np.asarray(p) for p in lane_polys_base]
        self.rng = np.random.default_rng(seed)
        self.door_closed = door_closed
        self.door_target_x_m = door_target_x_m      # removable flat target across the door end (doors open)
        self.lidar_xy = lidar_xy
        self.angles = np.radians(np.linspace(-fov_deg / 2, fov_deg / 2, n_rays))
        self.range_sigma, self.dropout, self.range_max = range_sigma, dropout, range_max
        self.ref_rate = ref_rate            # U(x) = a + b*x/L + c*step(x < 0.5 m)  [1/s]
        self.alpha_bkg = alpha_bkg
        self.boxes = {}                     # name -> (x0, x1, y0, y1)
        self.patches = []                   # (x0, x1, y0, y1, D_beta, D_alpha)

    # ------------------------------------------------------------- scene
    def add_patch(self, x0, x1, y0, y1, d_beta, d_alpha=0.0):
        self.patches.append((x0, x1, y0, y1, d_beta, d_alpha))

    def set_box(self, name, rect=None):
        if rect is None:
            self.boxes.pop(name, None)
        else:
            self.boxes[name] = tuple(rect)

    def person(self, x, y, size=0.30):
        self.set_box("person", (x - size / 2, x + size / 2, y - size / 2, y + size / 2))

    # -------------------------------------------------------------- lidar
    def _segments(self):
        L, h = self.L, self.W / 2
        segs = [(0, h, L, h), (0, -h, L, -h), (L, -h, L, h)]
        if self.door_closed:
            segs.append((0, -h, 0, h))
        elif self.door_target_x_m is not None:
            xt = self.door_target_x_m
            segs.append((xt, -h, xt, h))
        for x0, x1, y0, y1 in self.boxes.values():
            segs += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
        return np.array(segs, dtype=float)

    def scan(self, pose):
        """(angles, ranges) in the LiDAR frame for the true base pose."""
        x, y, yaw = pose
        ox = x + math.cos(yaw) * self.lidar_xy[0] - math.sin(yaw) * self.lidar_xy[1]
        oy = y + math.sin(yaw) * self.lidar_xy[0] + math.cos(yaw) * self.lidar_xy[1]
        a = self.angles + yaw
        dx, dy = np.cos(a)[:, None], np.sin(a)[:, None]
        s = self._segments()
        ex, ey = (s[:, 2] - s[:, 0])[None, :], (s[:, 3] - s[:, 1])[None, :]
        den = dx * ey - dy * ex
        with np.errstate(divide="ignore", invalid="ignore"):
            t = ((s[:, 0][None, :] - ox) * ey - (s[:, 1][None, :] - oy) * ex) / den
            u = ((s[:, 0][None, :] - ox) * dy - (s[:, 1][None, :] - oy) * dx) / den
        t = np.where((np.abs(den) > 1e-12) & (t > 0.02) & (u >= 0) & (u <= 1), t, np.inf)
        r = t.min(axis=1)
        r = r + self.rng.normal(0, self.range_sigma, len(r))
        r[self.rng.random(len(r)) < self.dropout] = np.inf
        r[r > self.range_max] = np.inf
        return self.angles, r

    # --------------------------------------------------------------- rates
    def reference_rate(self, x):
        a, b, c = self.ref_rate
        return a + b * min(max(x / self.L, 0.0), 1.0) + (c if x < 0.5 else 0.0)

    def rates(self, pose):
        """Expected rates {lane: {alpha, beta, ref}} for the true pose (MODEL.md 5 forward model)."""
        out = {}
        for n, poly in enumerate(self.lanes):
            ap = transform(pose, poly)
            centre = ap.mean(axis=0)
            U = self.reference_rate(centre[0])
            cb, ca = self.cal.cal(n, "beta"), self.cal.cal(n, "alpha")
            beta, alpha = cb.k * U + cb.b, ca.k * U + ca.b + self.alpha_bkg * 0
            area = polygon_area(ap)
            for x0, x1, y0, y1, d_b, d_a in self.patches:
                if ap[:, 0].max() < x0 or ap[:, 0].min() > x1 or ap[:, 1].max() < y0 or ap[:, 1].min() > y1:
                    continue
                ov = clip_convex(ap, np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))
                w = abs(polygon_area(ov)) / area if len(ov) >= 3 else 0.0
                beta += cb.K * d_b * w
                alpha += ca.K * d_a * w
            # an object standing on the floor under the aperture hides the floor signal (not modelled further)
            out[n] = {"alpha": alpha, "beta": beta, "ref": U}
        return out

    def rear_blocked(self, pose, outline, zone_m=0.15):
        """Rear proximity field of the chassis (ToF) occupied by a box."""
        if not self.boxes:
            return False
        rect = np.array([[outline.rear - zone_m, -outline.body_half_width], [outline.rear, -outline.body_half_width],
                         [outline.rear, outline.body_half_width], [outline.rear - zone_m, outline.body_half_width]])
        zone = transform(pose, rect)
        for x0, x1, y0, y1 in self.boxes.values():
            if len(clip_convex(zone, np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))) >= 3:
                return True
        return False
