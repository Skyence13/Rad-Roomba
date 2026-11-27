"""Footprint geometry, trajectory, coverage accounting, cell estimates, flags (simulated).
Traces: RQ-012, RQ-013, RQ-014, RQ-021, RQ-023, RQ-027; VT-008, VT-020, VT-022."""
import base64, math
import numpy as np
import pytest
from rr_core import geometry as geo
from rr_core.trajectory import TrajectoryBuffer, PoseUnavailable
from rr_core.processing import SurveyProcessor, SurveyConfig, REASONS
from rr_core.profiles import Calibration, ProfileStore, DATA

MOUNT = {"xyz_m": [0.1385, 0.0, 0.032], "rpy_rad": [0, 0, 0]}
DESC_BYTES = (DATA / "head_descriptor_demo.json").read_bytes()
MANIFEST = {"attachment_session_id": "a-1", "descriptor_b64": base64.b64encode(DESC_BYTES).decode(), "mount_transform": MOUNT}


def make(length=3.0, width=1.0, **kw):
    cal = Calibration.load(DATA / "demo_calibration.json")
    prof = ProfileStore.load(DATA / "demo_site_profile_ore.json").snapshot("ore-floor-demo-synthetic", cal, "COMMISSIONING")
    traj = TrajectoryBuffer()
    proc = SurveyProcessor(SurveyConfig(length, width, **kw), cal, prof, traj)
    proc.open_session(MANIFEST)
    return proc, traj, cal


def drive(traj, t0, x0, x1, y, yaw=0.0, v=0.1, dt=0.02, credit=True):
    n = int(abs(x1 - x0) / (v * dt))
    for i in range(n + 1):
        traj.add(int(t0 + i * dt * 1e6), x0 + (x1 - x0) * i / n, y, yaw, credit=credit)
    return int(t0 + n * dt * 1e6)


def gates(proc, cal, t0, t1, seq0, rng, hot=None, pose_of=None, bad_lane=None, U=4.0):
    seq = seq0
    t = t0
    while t + 100_000 <= t1:
        lanes = []
        for n in range(4):
            cb = cal.cal(n, "beta")
            rate = cb.k * U + cb.b
            if hot is not None:
                p = proc.traj.at(t + 50_000)
                c = geo.transform((p["x"], p["y"], p["yaw"]), [proc.lane_center_base(0, n)])[0]
                frac = max(0.0, 1 - abs(c[0] - hot[0]) / 0.1) * (1.0 if abs(c[1] - hot[1]) < 0.04 else 0.0)
                rate += cb.K * hot[2] * frac
            reasons = ["LANE_FLAG:REFERENCE_FAULT"] if bad_lane == n else []
            lanes.append({"id": n, "alpha": [int(rng.poisson(0.003)), 99910], "beta": [int(rng.poisson(rate * 0.09991)), 99910],
                          "ref": None if bad_lane == n else [int(rng.poisson(U * 0.09997)), 99970], "flags": [], "reasons": reasons})
        proc.add_gate({"attachment": "a-1", "sequence": seq, "start_us": 0, "span_us": 100000, "t0_us": float(t),
                       "t1_us": float(t + 100_000), "bound_us": 400.0, "fit_id": "f", "sync": {}, "thermal": {"head_c": 8.2},
                       "flags": [], "lanes": lanes})
        seq += 1
        t += 100_000
    return seq


def test_lane_polygons_from_descriptor_and_mount():
    import json
    polys = geo.lane_polygons(json.loads(DESC_BYTES), MOUNT)
    assert polys[0][:, 0].min() == pytest.approx(0.154) and polys[0][:, 0].max() == pytest.approx(0.254)
    assert polys[0][:, 1].max() == pytest.approx(0.17125) and polys[3][:, 1].min() == pytest.approx(-0.17125)
    # a shorter axle-to-row distance (DEC-041) only needs a different mount transform
    p2 = geo.lane_polygons(json.loads(DESC_BYTES), {"xyz_m": [0.10, 0, 0.032], "rpy_rad": [0, 0, 0]})
    assert p2[1][:, 0].mean() == pytest.approx(0.1655)
    e = geo.erode_convex(polys[1], 0.010)
    assert geo.polygon_area(e) == pytest.approx(0.06 * 0.08)
    assert geo.erode_convex(polys[1], 0.041) is None
    # heading reversal moves the row to the other side of the axle
    c = geo.transform((1.0, 0.0, math.pi), [geo.lane_centers(json.loads(DESC_BYTES), MOUNT)[0]])[0]
    assert c[0] == pytest.approx(1.0 - 0.204) and c[1] == pytest.approx(-0.13125)


def test_clip_and_sweep():
    sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    assert geo.polygon_area(geo.clip_convex(sq + 0.5, sq)) == pytest.approx(0.25)
    out = geo.RobotOutline(body_x=(-0.2718, 0.1388), body_half_width=0.1464, head_x=(0.1388, 0.265), head_half_width=0.175)
    parts = geo.swept_parts(out, (0, 0, 0), {"kind": "straight", "dist": -0.35}, 0.05)
    assert geo.points_in_parts(parts, [[-0.6, 0.0]])[0] and not geo.points_in_parts(parts, [[-0.6, 0.3]])[0]
    parts = geo.swept_parts(out, (0, 0, 0), {"kind": "pivot", "angle": math.pi / 2}, 0.03)
    assert geo.points_in_parts(parts, [[0.0, 0.25]])[0] and not geo.points_in_parts(parts, [[0.36, -0.2]])[0]
    assert out.turn_radius == pytest.approx(math.hypot(0.265, 0.175), abs=1e-3)
    assert geo.RobotOutline((-0.27, 0.07), 0.146, (0.07, 0.19), 0.175, turn_radius=0.301).turn_radius == 0.301   # arbitrary value: the parameter is passed through


def test_trajectory_epochs_and_gaps():
    t = TrajectoryBuffer()
    for i in range(10):
        t.add(i * 20_000, 0.002 * i, 0, 0)
    assert t.at(50_000)["x"] == pytest.approx(0.005)
    t.add(200_000, 0.5, 0, 0)                      # jump -> new epoch
    with pytest.raises(PoseUnavailable) as e:
        t.interval(170_000, 200_000)
    assert e.value.reason == "EPOCH_BOUNDARY"
    t.add(600_000, 0.5, 0, 0)
    with pytest.raises(PoseUnavailable) as e:
        t.at(400_000)
    assert e.value.reason == "POSE_GAP"
    with pytest.raises(PoseUnavailable):
        t.at(700_000)


def test_single_pass_seams_not_credited_and_offset_pass_closes_them():
    proc, traj, cal = make()
    rng = np.random.default_rng(1)
    t1 = drive(traj, 1_000_000, 0.3, 2.5, 0.0)
    proc.add_mark(1_000_000, stage="SCAN", tag="P0")
    seq = gates(proc, cal, 1_000_000, t1, 0, rng)
    proc.add_mark(t1, stage=None, reason="TURN")
    proc.advance(t1)
    cls = proc.classify_subcells()
    r = proc.cfg.sub_res
    ix = int(1.5 / r)
    row = cls[:, ix]
    y = proc.y0 + (np.arange(proc.ny) + 0.5) * r
    covered = np.isin(row, [1, 2])
    # eroded lanes: 60 mm wide at +/-43.75, +/-131.25; seams (27.5 mm with erosion) stay UNVISITED
    for c in (0.13125, 0.04375, -0.04375, -0.13125):
        assert covered[np.abs(y - c) < 0.027].all()
    for s in (0.0, 0.0875, -0.0875):
        assert not covered[np.abs(y - s) < 0.012].any()
    assert not covered[np.abs(y) > 0.165].any()
    width1 = covered.sum() * r
    assert width1 == pytest.approx(4 * 0.06, abs=4 * 2 * r)
    # second pass offset +43.75 mm in the opposite heading closes the interior seams
    t2 = drive(traj, t1 + 5_000_000, 2.5 + 0.408, 0.3 + 0.408, 0.04375, yaw=math.pi)
    proc.add_mark(t1 + 5_000_000, stage="SCAN", tag="P1")
    gates(proc, cal, t1 + 5_000_000, t2, seq, rng)
    proc.add_mark(t2, stage=None, reason="END")
    proc.finish()
    cls = proc.classify_subcells()
    covered = np.isin(cls[:, ix], [1, 2])
    band = (y > -0.131) & (y < 0.175)
    assert covered[band].all()
    res = proc.residuals()
    assert all(q["reason"] in REASONS for q in res) and any(q["reason"] == "UNVISITED" for q in res)
    s = proc.coverage_summary()
    assert sum(s["areas_m2"].values()) == pytest.approx(3.0, abs=1e-6)


def test_invalid_lane_and_uncertain_pose_earn_no_credit():
    proc, traj, cal = make()
    rng = np.random.default_rng(2)
    t1 = drive(traj, 1_000_000, 0.3, 1.3, 0.0)
    t2 = drive(traj, t1 + 20_000, 1.3, 2.3, 0.0, credit=False)
    proc.add_mark(1_000_000, stage="SCAN", tag="P0")
    gates(proc, cal, 1_000_000, t2, 0, rng, bad_lane=2)
    proc.finish()
    cls = proc.classify_subcells()
    r = proc.cfg.sub_res
    iy = lambda yv: int((yv - proc.y0) / r)
    assert cls[iy(-0.04375), int(0.9 / r)] == REASONS.index("INVALID_DATA")      # reference lost on lane 2
    assert cls[iy(0.04375), int(0.9 / r)] in (1, 2)
    assert cls[iy(0.04375), int(2.0 / r)] == REASONS.index("INVALID_DATA")       # pose outside budget
    log = proc.gate_log[-1]
    assert not any(l["credited"] for l in log["lanes"]) and "POSE_UNCERTAIN" in log["lanes"][0]["reasons"]
    assert proc.acc["beta"]["T_F"][:, int(2.0 / 0.1), :].sum() == 0


def test_cell_estimate_weights_and_hotspot_flag_with_location():
    proc, traj, cal = make()
    rng = np.random.default_rng(3)
    hot = (1.55, 0.04375, 2.4)                 # Bq/cm2 under lane 1 on the first pass
    t1 = drive(traj, 1_000_000, 0.3, 2.5, 0.0)
    proc.add_mark(1_000_000, stage="SCAN", tag="P0")
    seq = gates(proc, cal, 1_000_000, t1, 0, rng, hot=hot)
    proc.add_mark(t1, stage=None, reason="TURN")
    t2 = drive(traj, t1 + 5_000_000, 2.5 + 0.408, 0.3 + 0.408, 0.04375, yaw=math.pi)
    proc.add_mark(t1 + 5_000_000, stage="SCAN", tag="P1")
    gates(proc, cal, t1 + 5_000_000, t2, seq, rng)
    proc.finish()
    flags = proc.evaluate()
    top = [f for f in proc.flags if f["kind"] == "INVESTIGATION_LEVEL"]
    assert len(top) == 1
    f = top[0]
    assert f["id"].startswith("HS-") and f["source_lane"] == 1
    assert abs(f["x_m"] - 1.55) < 0.04 and abs(f["y_m"] - 0.04375) < 0.01
    assert f["location"]["wall"] == "left wall" and f["location"]["distance_from_door_m"] == pytest.approx(f["x_m"], abs=1e-3)
    assert f["contributing_gates"] and f["footprint"] and f["recommendation"]["action"] == "STATIONARY_COUNT"
    # weights: an interior cell sees ~ (cell area x transit) / aperture area of live time per pass
    cy, cx = proc.cell_of(1.05, 0.04375)
    T = proc.acc["beta"]["T_F"][cy, cx, :].sum()
    assert 0.5 < T < 2.6
    d = proc.decisions["beta"][(cy, cx)]
    assert d.method.startswith("poisson-exact") and all(m.startswith("lane-window-excluding-test") for m in d.u0_methods)
    assert d.D_hash > d.D_star > 0 and abs(d.D) < 0.25
    rows = proc.cells_table()
    row = next(q for q in rows if q["ix"] == cx and q["iy"] == cy)
    assert row["stage"] == "SCAN" and row["beta_window.threshold_method"]
    assert any(q["beta_window.D"] is not None and q["beta_window.D"] < 0 for q in rows)     # signed values kept
    assert all(q["beta_window.D"] is None for q in rows if q["n_lane_gates"] == 0)          # no synthetic values


def test_scaler_observation_two_stage():
    proc, traj, cal = make()
    rng = np.random.default_rng(4)
    for i in range(0, 1600):
        traj.add(1_000_000 + i * 20_000, 1.0, 0.0, 0.0)
    proc.add_mark(1_000_000, stage="COUNT", obs="OBS-1", tag="count")
    gates(proc, cal, 1_000_000, 31_000_000, 0, rng, hot=(1.204, 0.04375, 0.6))
    proc.advance(31_000_000)
    live = proc.live_count_state("OBS-1", 1, 31_000_000)
    assert live.T_F == pytest.approx(30.0, rel=0.01)
    proc.add_mark(31_000_000, stage=None, reason="COUNT_DONE", count_end=True, obs="OBS-1", lane=1, valid=True, mode="PRESET_TIME")
    o = proc.observations["OBS-1"]
    assert o["valid"] and o["outcome"] == "EXCEEDS_INVESTIGATION_LEVEL" and o["result"]["method"] == "poisson-exact"
    assert o["alpha"] < 1e-3 and abs(o["result"]["D"] - 0.6) < 0.15
    assert next(l for l in o["lanes"] if l["lane"] == 3)["D"] < 0.2
    # an invalidated count (motion/stop inside) never yields an outcome
    proc.add_mark(31_100_000, stage="COUNT", obs="OBS-2")
    proc.add_mark(31_200_000, stage=None, count_end=True, obs="OBS-2", lane=1, valid=False, reason="NOT_STATIONARY")
    assert proc.observations["OBS-2"]["outcome"] == "INVALID"
