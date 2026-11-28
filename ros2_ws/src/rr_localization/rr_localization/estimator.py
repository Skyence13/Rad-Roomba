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

Position-credit model (2026-11-28, review M3/M4, IB-47):
* State [x, y, yaw, s]: s is the systematic wheel-scale error (true travel = (1 + s) x odometry travel), prior
  sigma `wheel_scale_sigma` (default 0.01 = 1 %, ASSUMED: tyre diameter tolerance, compression and wear; not measured,
  no chassis data) with a slow random walk.  The along-track error therefore grows LINEARLY with the distance since the
  last along-track (end wall / door target) fix and is reduced by every fix (s is estimated online).  White odometry
  noise stays as a small per-step term.
* Credit (`sample()["credit"]`) requires: 2 sigma at the farthest aperture corner <= credit budget (10 mm) from the full
  covariance incl. the scale state; y and yaw constrained within `max_constraint_age_us`; x constrained within
  `max_x_age_us` (freshness in x); no slip; the chassis clock fit valid (bound finite and <= `max_time_bound_us`); and
  no pose correction larger than `jump_credit_m` in the last scan update (`correction_m`; the trajectory buffer opens a new
  epoch on such a correction, so no gate spans it).
* Scans are applied at their own time stamp: the wall measurements are moved to the current time with the odometry
  increments recorded since the scan time (lag compensation).
* Gyro: the 10 ms mean rates of consecutive samples are averaged (trapezoid) over the 20 ms step; the unsampled part
  adds yaw process noise.

No ROS imports.  Evidence class of the tuning values: simulated / assumed (stated per parameter).
"""
from __future__ import annotations

import math

import numpy as np


class LocalizerConfig:
    def __init__(self, length_m, width_m, door_closed=True, lidar_xy=(-0.15, 0.0), lidar_yaw=0.0, door_target_x_m=None,
                 track_m=0.270, wheel_radius_m=0.052, cpr=9600, head_lever_m=0.32,
                 credit_budget_m=0.010, hold_budget_m=0.040, gate_m=0.08, corner_exclusion_m=0.12,
                 min_points=15, range_sigma_m=0.006, slip_yaw_rad=0.012, odo_scale_sigma=0.005,
                 max_constraint_age_us=1_500_000, wheel_scale_sigma=0.01, wheel_scale_walk_per_m=1e-4,
                 max_x_age_us=3_000_000, jump_credit_m=0.005, max_time_bound_us=10_000.0, history_us=1_000_000,
                 x_reject_reset=3):
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
        self.x = np.zeros(4)
        self.P = np.diag([1.0, 1.0, 1.0, cfg.wheel_scale_sigma ** 2])
        self._hist = []                      # (t_us, dx, dy, dyaw) odometry increments (scan lag compensation)
        self._prev_gyro = None
        self.correction_m = 0.0
        self._corr_pending = 0.0
        self.time_bound_us = math.inf
        self.stats = {"x_fixes": 0, "x_rejects": 0, "big_corrections": 0, "max_correction_m": 0.0}
        self._pending_scan = None
        self.last_chassis_us = None
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
        s_keep = float(self.x[3]) if self.initialized else 0.0      # the scale estimate survives a datum re-registration
        p_keep = float(self.P[3, 3]) if self.initialized else self.cfg.wheel_scale_sigma ** 2
        self.x = np.array([x, y, yaw, s_keep], dtype=float)
        self.P = np.diag([sigma_xy ** 2, sigma_xy ** 2, sigma_yaw ** 2, p_keep])
        self._hist = []
        self.initialized = True
        self.last_update = {"y": None, "yaw": None, "x": None}
        self.rejects = 0
        self.t_us = t_us

    # --------------------------------------------------------------- predict
    def predict(self, s: dict):
        """One chassis sample (ticks delta, gyro) -> dead-reckoning step with the wheel-scale state."""
        c = self.cfg
        k = 2 * math.pi * c.wheel_radius_m / c.cpr
        dl, dr = s["d_left_ticks"] * k, s["d_right_ticks"] * k
        dt = 0.0 if self.t_us is None else max(0.0, (s["t_us"] - self.t_us) * 1e-6)
        self.t_us = s["t_us"]
        self.last_chassis_us = s.get("chassis_us")
        self.time_bound_us = s.get("bound_us", 0.0) if s.get("bound_us") is not None else math.inf
        ds_odo = 0.5 * (dl + dr)
        scale = 1.0 + self.x[3]
        ds = ds_odo * scale
        dth_w = (dr - dl) / c.track_m
        g = s["gyro_z"]
        g_prev = g if self._prev_gyro is None else self._prev_gyro
        self._prev_gyro = g
        dth_g = 0.5 * (g + g_prev) * dt          # trapezoid over the step from two 10 ms window means
        # wheel/gyro disagreement accumulated over ~1 s: slip detection
        self._slip_acc = 0.9 * self._slip_acc + (dth_w - dth_g)
        if abs(self._slip_acc) > c.slip_yaw_rad:
            self._slip_hold_until = s["t_us"] + 1_000_000
        self.slip = s["t_us"] < self._slip_hold_until
        dth = dth_g if s.get("imu_ok", True) and dt > 0 else dth_w
        th = self.x[2] + 0.5 * dth
        inc = np.array([ds * math.cos(th), ds * math.sin(th), dth])
        self.x[:3] += inc
        self.x[2] = math.atan2(math.sin(self.x[2]), math.cos(self.x[2]))
        F = np.eye(4)
        F[0, 2], F[1, 2] = -ds * math.sin(th), ds * math.cos(th)
        F[0, 3], F[1, 3] = ds_odo * math.cos(th), ds_odo * math.sin(th)
        ss = (c.odo_scale_sigma * abs(ds)) ** 2 + (1e-4 * dt) ** 2
        sl = (0.005 * abs(ds)) ** 2
        st = ((0.02 * abs(dth)) ** 2 + (0.002 * dt) ** 2 + (0.05 * abs(dth_w - dth_g)) ** 2
              + (0.25 * abs(g - g_prev) * dt) ** 2)
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        Q = np.zeros((4, 4))
        Q[:2, :2] = R @ np.diag([ss, sl]) @ R.T
        Q[2, 2] = st
        Q[3, 3] = (c.wheel_scale_walk_per_m * abs(ds)) ** 2
        self.P = F @ self.P @ F.T + Q
        self.dist_since_x += abs(ds)
        self._hist.append((self.t_us, inc[0], inc[1], inc[2]))
        while self._hist and self._hist[0][0] < self.t_us - c.history_us:
            self._hist.pop(0)
        self.correction_m, self._corr_pending = self._corr_pending, 0.0
        if self._pending_scan is not None and self.t_us >= self._pending_scan[0]:
            # a scan newer than the odometry it arrived with: applied now that the state has reached its time stamp
            t_s, a_s, r_s, rm = self._pending_scan
            self._pending_scan = None
            self.update_scan(t_s, a_s, r_s, rm)
            self.correction_m, self._corr_pending = max(self.correction_m, self._corr_pending), 0.0
        return self.sample()

    def _unexplained(self, angles, ranges, range_max):
        """Base-frame points not near a wall for the current pose (obstacle input while a scan is deferred)."""
        c = self.cfg
        angles, ranges = np.asarray(angles, float), np.asarray(ranges, float)
        ok = np.isfinite(ranges) & (ranges > 0.05) & (ranges < range_max)
        a, r = angles[ok] + c.lidar_yaw, ranges[ok]
        pb = np.column_stack((c.lidar_xy[0] + r * np.cos(a), c.lidar_xy[1] + r * np.sin(a)))
        cy, sy = math.cos(self.x[2]), math.sin(self.x[2])
        pm = np.column_stack((self.x[0] + cy * pb[:, 0] - sy * pb[:, 1], self.x[1] + sy * pb[:, 0] + cy * pb[:, 1]))
        L, W = c.length_m, c.width_m
        g = c.gate_m
        near = ((np.abs(np.abs(pm[:, 1]) - W / 2) < g) | (np.abs(pm[:, 0] - L) < g) | (np.abs(pm[:, 0]) < g)
                | (np.abs(pm[:, 1]) > W / 2) | (pm[:, 0] > L) | (pm[:, 0] < 0))
        return pb[~near]

    def _since(self, t_us):
        """Odometry motion (dx, dy, dyaw) recorded after time t_us (scan lag compensation)."""
        if t_us is None:
            return 0.0, 0.0, 0.0
        dx = dy = dyaw = 0.0
        for t, a, b, c in self._hist:
            if t > t_us:
                dx, dy, dyaw = dx + a, dy + b, dyaw + c
        return dx, dy, dyaw

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
        if t_us is not None and self.t_us is not None and t_us > self.t_us + 25_000:
            # the state is OLDER than the scan (odometry samples still queued): keep the newest such scan and apply it when
            # the odometry has caught up (IB-47: applying it to the old state gave ~30 mm innovations and rejected fixes)
            self._pending_scan = (t_us, angles, ranges, range_max)
            self.stats["deferred_scans"] = self.stats.get("deferred_scans", 0) + 1
            return self._unexplained(angles, ranges, range_max)
        x_before = self.x.copy()
        lag = self._since(t_us)                  # motion between the scan time and the current state
        self.scan_lag_us = None if t_us is None or self.t_us is None else self.t_us - t_us
        angles, ranges = np.asarray(angles, float), np.asarray(ranges, float)
        ok = np.isfinite(ranges) & (ranges > 0.05) & (ranges < range_max)
        a, r = angles[ok] + c.lidar_yaw, ranges[ok]
        pb = np.column_stack((c.lidar_xy[0] + r * np.cos(a), c.lidar_xy[1] + r * np.sin(a)))     # base frame
        xs = self.x[:3] - np.array(lag)          # predicted pose at the scan time
        cy, sy = math.cos(xs[2]), math.sin(xs[2])
        pm = np.column_stack((xs[0] + cy * pb[:, 0] - sy * pb[:, 1], xs[1] + sy * pb[:, 0] + cy * pb[:, 1]))
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
                yaw = -phi + lag[2]                                   # wall runs along map x; moved to the current time
                yaw = min((yaw, yaw + math.pi, yaw - math.pi), key=lambda v: abs(math.atan2(math.sin(v - self.x[2]), math.cos(v - self.x[2]))))
                if self._scalar_update(2, yaw, sig_phi ** 2, name + "_yaw", angle=True):
                    self.last_update["yaw"] = t_us
                y = ((W / 2 - d) if name == "left" else (-W / 2 + d)) + lag[1]
                if self._scalar_update(1, y, sig_d ** 2, name + "_y"):
                    self.last_update["y"] = t_us
            else:
                x = ((L - d) if name == "front" else xd + d) + lag[0]
                if self._scalar_update(0, x, sig_d ** 2, name + "_x"):
                    self.last_update["x"] = t_us
                    self.dist_since_x = 0.0
                    self.stats["x_fixes"] += 1
                    self.x_reject_run = 0
                else:
                    # an end-wall fix that disagrees with the estimate beyond 4 sigma: the pose is inconsistent with its own
                    # covariance.  Credit is withheld at once (X_RESIDUAL); after `x_reject_reset` consecutive rejections the
                    # x covariance is inflated by the innovation and the fix accepted (a correction -> new trajectory epoch).
                    self.stats["x_rejects"] += 1
                    self.x_reject_run = getattr(self, "x_reject_run", 0) + 1
                    if self.x_reject_run >= c.x_reject_reset:
                        innov = self.residuals[name + "_x"]["innovation"]
                        self.P[0, 0] += innov * innov
                        if self._scalar_update(0, x, sig_d ** 2, name + "_x"):
                            self.last_update["x"] = t_us
                            self.dist_since_x = 0.0
                            self.stats["x_resets"] = self.stats.get("x_resets", 0) + 1
                        self.x_reject_run = 0
        corr = float(math.hypot(self.x[0] - x_before[0], self.x[1] - x_before[1]))
        self._corr_pending = max(self._corr_pending, corr)
        self.stats["max_correction_m"] = max(self.stats["max_correction_m"], corr)
        if corr > c.jump_credit_m:
            self.stats["big_corrections"] += 1
        return pb[~near_any]

    # ------------------------------------------------------------------ output
    def head_uncertainty_m(self) -> float:
        """2-sigma position uncertainty at the detector row (lever arm on yaw); the scale state is inside P[0:2, 0:2]."""
        return 2.0 * math.sqrt(max(self.P[0, 0], 0) + max(self.P[1, 1], 0)
                               + (self.cfg.head_lever_m ** 2) * max(self.P[2, 2], 0))

    def credit_reasons(self) -> list:
        c = self.cfg
        t = self.t_us or 0
        why = []
        if not self.initialized:
            why.append("NOT_INITIALIZED")
        if self.head_uncertainty_m() > c.credit_budget_m:
            why.append("2SIGMA")
        if self.slip:
            why.append("SLIP")
        for k in ("y", "yaw"):
            if self.last_update[k] is None or t - self.last_update[k] > c.max_constraint_age_us:
                why.append("STALE_" + k.upper())
        if self.last_update["x"] is None or t - self.last_update["x"] > c.max_x_age_us:
            why.append("STALE_X")
        if not (self.time_bound_us is not None and math.isfinite(self.time_bound_us) and self.time_bound_us <= c.max_time_bound_us):
            why.append("CHASSIS_TIME")
        if self.correction_m > c.jump_credit_m:
            why.append("CORRECTION")
        if getattr(self, "x_reject_run", 0) > 0:
            why.append("X_RESIDUAL")
        return why

    def sample(self) -> dict:
        c = self.cfg
        u = self.head_uncertainty_m()
        why = self.credit_reasons()
        return {"t_us": self.t_us, "x": float(self.x[0]), "y": float(self.x[1]), "yaw": float(self.x[2]),
                "sxx": float(self.P[0, 0]), "syy": float(self.P[1, 1]), "syaw": float(self.P[2, 2]),
                "q": float(max(0.0, 1.0 - u / c.hold_budget_m)), "credit": not why,
                "tb_us": float(self.time_bound_us) if math.isfinite(self.time_bound_us) else None,
                "corr_m": float(self.correction_m), "nocredit": "|".join(why) if why else ""}

    def status(self) -> dict:
        u = self.head_uncertainty_m()
        return {"initialized": self.initialized, "head_uncertainty_2s_m": u, "slip": self.slip,
                "hold_request": bool(self.initialized and (u > self.cfg.hold_budget_m)),
                "credit": self.sample()["credit"], "rejects": self.rejects, "residuals": self.residuals,
                "constraint_age_us": {k: (None if v is None or self.t_us is None else self.t_us - v)
                                      for k, v in self.last_update.items()},
                "sigma": [float(math.sqrt(max(self.P[i, i], 0))) for i in range(3)],
                "wheel_scale": {"estimate": float(self.x[3]), "sigma": float(math.sqrt(max(self.P[3, 3], 0)))},
                "credit_reasons": self.credit_reasons(), "stats": dict(self.stats)}
