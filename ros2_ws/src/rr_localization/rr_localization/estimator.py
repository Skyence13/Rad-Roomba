"""Wall-referenced localisation for a rectangular trailer (DEC-030).

Wheel + gyro dead reckoning fused (EKF on x, y, yaw in the map frame) with 2D
LiDAR line fits to the side walls, the front bulkhead and, when the doors are
closed, the door end -- or, with the doors open, a removable flat target placed
across the door end at `door_target_x_m` (site rule for long trailers, IB-30),
which is treated exactly like the door end wall at that x.  The trailer dimensions are the SURVEYED values entered
at configuration.  Outputs a pose sample with covariance, a quality figure, a
`credit` flag (uncertainty at the detector row within the mapping budget) and a
hold request when the uncertainty exceeds the hold budget.

Long parallel walls constrain y and yaw strongly and x not at all: x comes from
the end walls when one is inside the LiDAR field and range, otherwise from
odometry, whose growing variance withholds credit (design 0.3 ch.7).

No ROS imports.  Evidence class of the tuning values: simulated.
"""
from __future__ import annotations

import math

import numpy as np


class LocalizerConfig:
    def __init__(self, length_m, width_m, door_closed=True, lidar_xy=(-0.15, 0.0), lidar_yaw=0.0, door_target_x_m=None,
                 track_m=0.270, wheel_radius_m=0.052, cpr=9600, head_lever_m=0.32,
                 credit_budget_m=0.010, hold_budget_m=0.040, gate_m=0.08, corner_exclusion_m=0.12,
                 min_points=15, range_sigma_m=0.006, slip_yaw_rad=0.012, odo_scale_sigma=0.02,
                 max_constraint_age_us=1_500_000):
        self.__dict__.update(locals())
        del self.__dict__["self"]


def door_reference_x(cfg) -> float | None:
    """x of the door-end reference line: 0 with the doors closed, the removable target's x with the
    doors open and a target placed, else None (no door-end reference)."""
    if cfg.door_closed:
        return 0.0
    return None if cfg.door_target_x_m is None else float(cfg.door_target_x_m)


class WallLocalizer:
    def __init__(self, cfg: LocalizerConfig):
        self.cfg = cfg
        self.x = np.zeros(3)
        self.P = np.diag([1.0, 1.0, 1.0])
        self.initialized = False
        self.slip = False
        self._slip_acc = 0.0
        self._slip_hold_until = 0
        self.last_update = {"y": None, "yaw": None, "x": None}
        self.residuals = {}
        self.rejects = 0
        self.t_us = None
        self.dist_since_x = 0.0

    def initialize(self, x, y, yaw, sigma_xy=0.03, sigma_yaw=0.03, t_us=None):
        """Datum registration (operator places the robot at the surveyed start mark)."""
        self.x = np.array([x, y, yaw], dtype=float)
        self.P = np.diag([sigma_xy ** 2, sigma_xy ** 2, sigma_yaw ** 2])
        self.initialized = True
        self.last_update = {"y": None, "yaw": None, "x": None}
        self.rejects = 0
        self.t_us = t_us

    # --------------------------------------------------------------- predict
    def predict(self, s: dict):
        """One chassis sample (ticks delta, gyro) -> dead-reckoning step."""
        c = self.cfg
        k = 2 * math.pi * c.wheel_radius_m / c.cpr
        dl, dr = s["d_left_ticks"] * k, s["d_right_ticks"] * k
        dt = 0.0 if self.t_us is None else max(0.0, (s["t_us"] - self.t_us) * 1e-6)
        self.t_us = s["t_us"]
        ds = 0.5 * (dl + dr)
        dth_w = (dr - dl) / c.track_m
        dth_g = s["gyro_z"] * dt
        # wheel/gyro disagreement accumulated over ~1 s: slip detection
        self._slip_acc = 0.9 * self._slip_acc + (dth_w - dth_g)
        if abs(self._slip_acc) > c.slip_yaw_rad:
            self._slip_hold_until = s["t_us"] + 1_000_000
        self.slip = s["t_us"] < self._slip_hold_until
        dth = dth_g if s.get("imu_ok", True) and dt > 0 else dth_w
        th = self.x[2] + 0.5 * dth
        self.x += np.array([ds * math.cos(th), ds * math.sin(th), dth])
        self.x[2] = math.atan2(math.sin(self.x[2]), math.cos(self.x[2]))
        F = np.array([[1, 0, -ds * math.sin(th)], [0, 1, ds * math.cos(th)], [0, 0, 1]])
        ss = (c.odo_scale_sigma * abs(ds)) ** 2 + (1e-4 * dt) ** 2
        sl = (0.005 * abs(ds)) ** 2
        st = (0.02 * abs(dth)) ** 2 + (0.002 * dt) ** 2 + (0.05 * abs(dth_w - dth_g)) ** 2
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        Q = np.zeros((3, 3))
        Q[:2, :2] = R @ np.diag([ss, sl]) @ R.T
        Q[2, 2] = st
        self.P = F @ self.P @ F.T + Q
        self.dist_since_x += abs(ds)
        return self.sample()

    # ----------------------------------------------------------------- update
    def _scalar_update(self, idx, z, r, name, angle=False):
        innov = z - self.x[idx]
        if angle:
            innov = math.atan2(math.sin(innov), math.cos(innov))
        s = self.P[idx, idx] + r
        nis = innov * innov / s
        self.residuals[name] = {"innovation": float(innov), "sigma": float(math.sqrt(s)), "nis": float(nis)}
        if nis > 16.0:                       # 4-sigma gate: residual monitoring, measurement refused
            self.rejects += 1
            return False
        K = self.P[:, idx] / s
        self.x = self.x + K * innov
        self.x[2] = math.atan2(math.sin(self.x[2]), math.cos(self.x[2]))
        self.P = self.P - np.outer(K, self.P[idx, :])
        self.P = 0.5 * (self.P + self.P.T)
        return True

    def update_scan(self, t_us, angles, ranges, range_max=12.0):
        """LaserScan (sensor frame) -> wall line fits -> EKF updates.  Returns the
        base-frame points NOT explained by a wall (for route-hold / blocked-strip logic)."""
        c = self.cfg
        angles, ranges = np.asarray(angles, float), np.asarray(ranges, float)
        ok = np.isfinite(ranges) & (ranges > 0.05) & (ranges < range_max)
        a, r = angles[ok] + c.lidar_yaw, ranges[ok]
        pb = np.column_stack((c.lidar_xy[0] + r * np.cos(a), c.lidar_xy[1] + r * np.sin(a)))     # base frame
        cy, sy = math.cos(self.x[2]), math.sin(self.x[2])
        pm = np.column_stack((self.x[0] + cy * pb[:, 0] - sy * pb[:, 1], self.x[1] + sy * pb[:, 0] + cy * pb[:, 1]))
        L, W = c.length_m, c.width_m
        gate = max(c.gate_m, 3.0 * math.sqrt(max(self.P[0, 0], self.P[1, 1])))
        ce = c.corner_exclusion_m
        walls = {"left": (np.abs(pm[:, 1] - W / 2) < gate) & (pm[:, 0] > ce) & (pm[:, 0] < L - ce),
                 "right": (np.abs(pm[:, 1] + W / 2) < gate) & (pm[:, 0] > ce) & (pm[:, 0] < L - ce),
                 "front": (np.abs(pm[:, 0] - L) < gate) & (np.abs(pm[:, 1]) < W / 2 - ce)}
        xd = door_reference_x(c)
        if xd is not None:
            walls["door"] = (np.abs(pm[:, 0] - xd) < gate) & (np.abs(pm[:, 1]) < W / 2 - ce)
        explained = np.zeros(len(pb), dtype=bool)
        for m in walls.values():
            explained |= m
        near_any = ((np.abs(np.abs(pm[:, 1]) - W / 2) < gate) | (np.abs(pm[:, 0] - L) < gate) | (np.abs(pm[:, 0]) < gate)
                    | (np.abs(pm[:, 1]) > W / 2) | (pm[:, 0] > L) | (pm[:, 0] < 0)
                    | ((np.abs(pm[:, 0] - xd) < gate) if xd is not None else False))
        self.residuals = {}
        for name, mask in walls.items():
            pts = pb[mask]
            if len(pts) < c.min_points:
                continue
            for _ in range(2):               # total-least-squares line with residual trimming
                mean = pts.mean(axis=0)
                u, sv, vt = np.linalg.svd(pts - mean, full_matrices=False)
                normal = vt[1]
                res = (pts - mean) @ normal
                rms = float(np.sqrt(np.mean(res ** 2)))
                keep = np.abs(res) < max(2.5 * rms, 0.004)
                if keep.all() or keep.sum() < c.min_points:
                    break
                pts = pts[keep]
            direction = vt[0]
            span = float(np.ptp((pts - mean) @ direction))
            if span < 0.25 or rms > 4 * c.range_sigma_m:
                continue
            n = len(pts)
            d = abs(float(mean @ normal))                            # distance base origin -> wall line
            phi = math.atan2(direction[1], direction[0])             # wall direction in the base frame
            sig_d = math.hypot(max(rms, c.range_sigma_m) / math.sqrt(n), 0.002)
            sig_phi = max(rms, c.range_sigma_m) / (span * math.sqrt(n / 12.0)) + 0.001
            self.residuals[name + "_fit"] = {"n": int(n), "rms": rms, "span": span}
            if name in ("left", "right"):
                yaw = -phi                                            # wall runs along map x
                yaw = min((yaw, yaw + math.pi, yaw - math.pi), key=lambda v: abs(math.atan2(math.sin(v - self.x[2]), math.cos(v - self.x[2]))))
                if self._scalar_update(2, yaw, sig_phi ** 2, name + "_yaw", angle=True):
                    self.last_update["yaw"] = t_us
                y = (W / 2 - d) if name == "left" else (-W / 2 + d)
                if self._scalar_update(1, y, sig_d ** 2, name + "_y"):
                    self.last_update["y"] = t_us
            else:
                x = (L - d) if name == "front" else xd + d
                if self._scalar_update(0, x, sig_d ** 2, name + "_x"):
                    self.last_update["x"] = t_us
                    self.dist_since_x = 0.0
        return pb[~near_any]

    # ------------------------------------------------------------------ output
    def head_uncertainty_m(self) -> float:
        """2-sigma position uncertainty at the detector row (lever arm on yaw)."""
        return 2.0 * math.sqrt(max(self.P[0, 0], 0) + max(self.P[1, 1], 0)
                               + (self.cfg.head_lever_m ** 2) * max(self.P[2, 2], 0))

    def sample(self) -> dict:
        c = self.cfg
        u = self.head_uncertainty_m()
        t = self.t_us or 0
        fresh = all(self.last_update[k] is not None and t - self.last_update[k] <= c.max_constraint_age_us
                    for k in ("y", "yaw"))
        credit = bool(self.initialized and u <= c.credit_budget_m and not self.slip and fresh)
        return {"t_us": self.t_us, "x": float(self.x[0]), "y": float(self.x[1]), "yaw": float(self.x[2]),
                "sxx": float(self.P[0, 0]), "syy": float(self.P[1, 1]), "syaw": float(self.P[2, 2]),
                "q": float(max(0.0, 1.0 - u / c.hold_budget_m)), "credit": credit}

    def status(self) -> dict:
        u = self.head_uncertainty_m()
        return {"initialized": self.initialized, "head_uncertainty_2s_m": u, "slip": self.slip,
                "hold_request": bool(self.initialized and (u > self.cfg.hold_budget_m)),
                "credit": self.sample()["credit"], "rejects": self.rejects, "residuals": self.residuals,
                "constraint_age_us": {k: (None if v is None or self.t_us is None else self.t_us - v)
                                      for k, v in self.last_update.items()},
                "sigma": [float(math.sqrt(max(self.P[i, i], 0))) for i in range(3)]}
