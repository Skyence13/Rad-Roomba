"""Position-credit model of the wall localiser (review M3/M4, IB-47).  Evidence: calculated / simulated."""
import math

import numpy as np

from rr_localization.estimator import LocalizerConfig, WallLocalizer

CPR, R = 9600, 0.052
K = 2 * math.pi * R / CPR


def straight(loc, t0, dist, v=0.1, dt=0.02, bound=500.0):
    n = int(round(dist / (v * dt)))
    ticks = v * dt / K
    t, acc = t0, 0.0
    out = None
    for _ in range(n):
        t += int(dt * 1e6)
        acc += ticks
        d = int(acc)
        acc -= d
        out = loc.predict({"t_us": t, "d_left_ticks": d, "d_right_ticks": d, "gyro_z": 0.0, "bound_us": bound})
    return t, out


def make(**kw):
    loc = WallLocalizer(LocalizerConfig(16.0, 2.5, **kw))
    loc.initialize(1.0, 0.0, 0.0, sigma_xy=0.001, sigma_yaw=0.001, t_us=0)
    loc.last_update = {"y": 0, "yaw": 0, "x": 0}
    return loc


def test_along_track_sigma_grows_linearly_with_distance_since_the_last_fix():
    loc = make(odo_scale_sigma=0.0)
    t, s1 = straight(loc, 0, 1.0)
    _, s3 = straight(loc, t, 2.0)
    sx1, sx3 = math.sqrt(s1["sxx"]), math.sqrt(s3["sxx"])
    assert sx1 == np.clip(sx1, 0.0095, 0.0106)          # 1 % of 1 m (plus the 1 mm datum)
    assert 2.7 < sx3 / sx1 < 3.1                          # linear in distance, not sqrt (the old white term gave sqrt(3))
    assert "2SIGMA" in s3["nocredit"]


def test_credit_needs_fresh_x_chassis_clock_and_no_big_correction():
    loc = make()
    loc.last_update = {"y": 10**12, "yaw": 10**12, "x": 10**12}
    _, s = straight(loc, 0, 0.05)
    loc.last_update = {"y": s["t_us"], "yaw": s["t_us"], "x": s["t_us"] - 4_000_000}
    assert "STALE_X" in loc.credit_reasons()
    loc.last_update["x"] = s["t_us"]
    loc.time_bound_us = math.inf
    assert "CHASSIS_TIME" in loc.credit_reasons()
    loc.time_bound_us = 500.0
    loc.correction_m = 0.008
    assert "CORRECTION" in loc.credit_reasons()


def test_scan_is_applied_at_its_own_time():
    """A bulkhead seen 100 ms ago at distance d: the update must use the pose 100 ms ago (10 mm behind at 0.1 m/s)."""
    loc = make(odo_scale_sigma=0.0, wheel_scale_sigma=1e-5)
    t, _ = straight(loc, 0, 0.5)
    x_now = loc.x[0]
    t_scan = t - 100_000
    x_scan = x_now - 0.010                                 # true position at the scan time
    d = 16.0 - (x_scan - 0.15)                             # range from a LiDAR 0.15 m behind base_link, straight ahead
    a = np.linspace(-0.3, 0.3, 61)
    r = d / np.cos(a)
    loc.cfg.lidar_xy = (-0.15, 0.0)
    loc.update_scan(t_scan, a, r)
    assert abs(loc.x[0] - x_now) < 0.003                   # without lag compensation it would be pulled 10 mm back
