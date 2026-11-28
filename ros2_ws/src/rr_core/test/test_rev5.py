"""MODEL.md revision 5 and the data-path review (docs/reviews/REVIEW_head_data_to_map.md): regression tests.

Evidence: calculated / simulated with synthetic coefficients.  The reviewer's probes (C1, M1, C2/P3, P4) are kept here as
regression tests; analysis/radiometry/rrrad is imported by the cross-check tests only."""
import base64
import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from rr_core import estimator as est
from rr_core import geometry as geo
from rr_core import unull
from rr_core.descriptor import DescriptorError
from rr_core.estimator import Cal, Decider, LaneGates
from rr_core.processing import REASONS, SurveyConfig, SurveyProcessor
from rr_core.profiles import DATA, Calibration, CalibrationStore, ProfileStore
from rr_core.trajectory import TrajectoryBuffer

REPO = Path(os.environ.get("RR_REPO", Path(__file__).resolve().parents[4]))
MOUNT = {"xyz_m": [0.0657, 0.0, 0.032], "rpy_rad": [0, 0, 0]}          # option C (reviewer's probes)
DESC_BYTES = (DATA / "head_descriptor_demo.json").read_bytes()
BIND = {"calibration_id": "DEMO-CAL-SYNTH-0001", "demonstration": True}
MANIFEST = {"attachment_session_id": "a-1", "descriptor_b64": base64.b64encode(DESC_BYTES).decode(), "mount_transform": MOUNT,
            "calibration": BIND}
SXX = 0.005 ** 2


def make(length=3.0, width=1.0, manifest=MANIFEST, **kw):
    cal = Calibration.load(DATA / "demo_calibration.json")
    prof = ProfileStore.load(DATA / "demo_site_profile_ore.json").snapshot("ore-floor-demo-synthetic", cal, "COMMISSIONING")
    traj = TrajectoryBuffer()
    proc = SurveyProcessor(SurveyConfig(length, width, **kw), cal, prof, traj)
    proc.open_session(manifest)
    return proc, traj, cal


def drive(traj, t0, x0, x1, y, yaw=0.0, v=0.1, dt=0.02):
    n = int(round(abs(x1 - x0) / (v * dt)))
    for i in range(n + 1):
        traj.add(int(t0 + i * dt * 1e6), x0 + (x1 - x0) * i / n, y, yaw, sxx=SXX, syy=SXX)
    return int(t0 + n * dt * 1e6)


def gate_records(proc, cal, t0, t1, seq0, rng, hot=None, U=4.0, sat=None):
    out, seq, t = [], seq0, t0
    while t + 100_000 <= t1:
        lanes = []
        for n in range(4):
            cb = cal.cal(n, "beta")
            rate = cb.k * U + cb.b
            if hot is not None:
                p = proc.traj.at(t + 50_000)
                c = geo.transform((p["x"], p["y"], p["yaw"]), [proc.lane_center_base(0, n)])[0]
                fx = max(0.0, 1 - abs(c[0] - hot[0]) / 0.1)
                rate += cb.K * hot[2] * fx * (1.0 if abs(c[1] - hot[1]) < 0.04 else 0.0)
            nb, nu = int(rng.poisson(rate * 0.09991)), int(rng.poisson(U * 0.09997))
            flagged = sat is not None and sat(t, n)
            lanes.append({"id": n, "alpha": None if flagged else [0, 99910], "beta": None if flagged else [nb, 99910],
                          "ref": [nu, 99970], "flags": ["SATURATED"] if flagged else [],
                          "reasons": ["LANE_FLAG:SATURATED", "NULL:alpha", "NULL:beta_window"] if flagged else []})
        out.append({"attachment": "a-1", "sequence": seq, "start_us": 0, "span_us": 100000, "t0_us": float(t), "t1_us": float(t + 100_000),
                    "bound_us": 400.0, "fit_id": "f", "sync": {}, "thermal": {"head_c": 8.2}, "flags": [], "lanes": lanes})
        seq += 1
        t += 100_000
    return out, seq


def survey(order=None, schedule=None, seed=11, n_pass=3, hot=None):
    """Probe 3 of the review, shortened: non-overlapping passes; `order` permutes the gate arrival order, `schedule` is
    the list of times at which a live (provisional) evaluation runs."""
    rng = np.random.default_rng(seed)
    proc, traj, cal = make(length=4.0, width=2.0)
    t, sq, gates, marks = 1_000_000, 0, [], []
    for i, y in enumerate([-0.70, -0.35, 0.0, 0.35, 0.70][:n_pass]):
        x0, x1, yaw = (0.3, 3.7, 0.0) if i % 2 == 0 else (3.7 + 0.2624, 0.3 + 0.2624, math.pi)
        te = drive(traj, t, x0, x1, y, yaw=yaw)
        marks += [(t, dict(stage="SCAN", tag=f"P{i}")), (te, dict(stage=None, reason="TURN"))]
        g, sq = gate_records(proc, cal, t, te, sq, rng, hot=hot if i == 0 else None)
        gates += g
        traj.add(te + 1_000_000, x1, y, yaw, sxx=SXX, syy=SXX)
        traj.add(te + 2_000_000, x1, y, yaw, sxx=SXX, syy=SXX)
        g, sq = gate_records(proc, cal, te, te + 2_000_000, sq, rng)
        gates += g
        t = te + 2_000_000 + 20_000
    for tm, m in marks:
        proc.add_mark(tm, **m)
    if order is not None:
        gates = [gates[i] for i in order(len(gates))]
    sched = sorted(schedule or [])
    for g in gates:
        proc.add_gate(g)
        while sched and g["t1_us"] >= sched[0]:
            proc.advance(sched.pop(0))
            proc.evaluate()
    proc.finish()
    proc.finalize()
    return proc


def recorded_signature(proc):
    rows = proc.cells_table()
    keys = [k for k in rows[0] if not k.startswith("provisional.") and k not in ("flag", "alarm_bookkeeping")]
    return [tuple(r[k] for k in keys) for r in rows]


def test_C1_recorded_results_identical_for_any_arrival_order_and_live_schedule():
    """Review C1 / MODEL.md rev 5 section 3: one recorded evaluation per cell on complete data."""
    base = survey(n_pass=2)
    rs = np.random.default_rng(5)
    shuffled = survey(n_pass=2, order=lambda n: rs.permutation(n))
    live = survey(n_pass=2, schedule=list(range(1_000_000, 80_000_000, 5_000_000)))
    sig = recorded_signature(base)
    assert sig == recorded_signature(shuffled)
    assert sig == recorded_signature(live)
    # the provisional values of the live schedule DO differ (they are labelled provisional), the recorded ones do not
    nd_live = sum(1 for d in live.provisional["beta"].values() if d.status == "NO_DECISION_REF")
    nd_rec = sum(1 for d in live.recorded["beta"].values() if d.status == "NO_DECISION_REF")
    assert nd_rec == 0 and nd_live > 0
    rows = live.cells_table()
    assert all(r["provisional.beta_window.D"] is None or "provisional.beta_window.D" in r for r in rows)


def test_M1_alarm_below_half_coverage_is_reported_and_never_green():
    """Review M1 (probe 2): 3 Bq/cm2 under lane 0 at the edge of the swept band, cell coverage 0.4."""
    rng = np.random.default_rng(5)
    proc, traj, cal = make(length=3.0, width=1.0)
    t1 = drive(traj, 1_000_000, 0.3, 2.7, -0.02, v=0.015)
    proc.add_mark(1_000_000, stage="SCAN", tag="P0")
    g, _ = gate_records(proc, cal, 1_000_000, t1, 0, rng, hot=(1.55, 0.12, 3.0))
    for x in g:
        proc.add_gate(x)
    proc.add_mark(t1, stage=None, reason="END")
    proc.finish()
    proc.finalize()
    cy, cx = proc.cell_of(1.55, 0.12)
    cov = proc.cell_coverage(cy, cx)
    st, why, flag = proc.cell_status((cy, cx))
    assert cov < 0.5 and proc.recorded["beta"][(cy, cx)].detected
    assert st == "ALARM" and flag
    s = proc.sub_per_cell
    blk = proc.classify_subcells()[cy * s:(cy + 1) * s, cx * s:(cx + 1) * s]
    assert (blk == REASONS.index("ALARM")).all() and not (blk == REASONS.index("ACCEPTABLE")).any()


def test_C2_calibration_identity_binding_strict_by_default_and_demonstration_marked():
    cal = Calibration.load(DATA / "demo_calibration.json")
    verified = {"calibration_id": cal.calibration_id, "mode": "COMMISSIONING", "descriptor": {"electronics_revision": "bench-A"}}
    hello = {"head_id": "HEAD-DEMO-001", "firmware": "sim-1.0", "setup_id": "S1-0123456789abcdef"}
    with pytest.raises(DescriptorError) as e:
        CalibrationStore([cal]).resolve(verified, hello)                    # probe P3: refused now
    assert e.value.reason == "CALIBRATION_IDENTITY_MISMATCH"
    b = CalibrationStore([cal], demonstration=True).resolve(verified, hello)
    assert b["demonstration"] is True and b["identity_match"] is False and "DEMONSTRATION" in b["notice"]
    rec = dict(cal.record, calibration_id="BOUND-CAL", identity={"head_serial": "HEAD-DEMO-001", "electronics_revision": "bench-A",
                                                                   "firmware": "sim-1.0", "setup_id": "S1-0123456789abcdef", "cal_id": "B-1"},
               validity_envelope=dict(cal.envelope, setup_id="S1-0123456789abcdef"))
    bound = Calibration(rec)
    v2 = dict(verified, calibration_id="BOUND-CAL")
    b2 = CalibrationStore([bound]).resolve(v2, hello, {"identity": {"cal_id": "B-1"}})
    assert b2["identity_match"] is True and not b2["demonstration"]
    with pytest.raises(DescriptorError):
        CalibrationStore([bound]).resolve(v2, hello, {"identity": {"cal_id": "B-2"}})       # another board calibration
    with pytest.raises(DescriptorError):
        CalibrationStore([bound]).resolve(v2, dict(hello, head_id="HEAD-OTHER"))
    with pytest.raises(DescriptorError):
        CalibrationStore([cal], demonstration=True).resolve(dict(verified, mode="SURVEY"), hello)


def test_C2_each_attachment_processed_with_its_own_bound_calibration():
    """Probe P4: a second attachment bound to an unknown calibration is refused (no credit, NO_CALIBRATION reason),
    one bound to a second known calibration is processed with that calibration."""
    proc, traj, cal = make()
    a2 = proc.open_session(dict(MANIFEST, attachment_session_id="a-2", calibration={"calibration_id": "OTHER-HEAD-CAL", "demonstration": True}))
    assert proc.att[a2]["calibration"] is None and "not available" in proc.att[a2]["refused"]
    other = Calibration(dict(cal.record, calibration_id="SECOND-CAL"))
    proc2 = SurveyProcessor(SurveyConfig(3.0, 1.0), cal, proc.profile, TrajectoryBuffer(), calibrations=[cal, other])
    proc2.open_session(MANIFEST)
    i2 = proc2.open_session(dict(MANIFEST, attachment_session_id="a-2", calibration={"calibration_id": "SECOND-CAL", "demonstration": True}))
    assert proc2.cal_of(i2) is other and proc2.cal_of(0) is cal
    i3 = proc2.open_session(dict(MANIFEST, attachment_session_id="a-3", calibration=None))
    assert proc2.cal_of(i3) is None


def test_M10_rate_saturation_raises_an_alarm_forced_clears_do_not():
    rng = np.random.default_rng(3)
    proc, traj, cal = make()
    t1 = drive(traj, 1_000_000, 0.3, 2.7, 0.0)
    proc.add_mark(1_000_000, stage="SCAN", tag="P0")
    sat = lambda t, n: n == 1 and 14_000_000 <= t < 15_000_000
    g, _ = gate_records(proc, cal, 1_000_000, t1, 0, rng, sat=sat)
    for x in g:
        proc.add_gate(x)
        q = x["sequence"]
        sc = [0, 2, 0, 0] if sat(x["t0_us"], 1) else [0] * 4
        proc.add_gatestat({"attachment": "a-1", "gate": {"seq": q, "sc": sc, "ff": [0] * 4, "lf": [999, 300 if sc[1] else 999, 999, 999]}})
    proc.finish()
    proc.finalize()
    alarm = [c for c in proc.members if proc.cell_status(c)[0] == "ALARM" and "rate above" in proc.cell_status(c)[1]]
    assert alarm and any(f["kind"] == "RATE_SATURATION" for f in proc.flags)
    for x in g:                                      # the same gates with forced clears: detector fault, no alarm
        if sat(x["t0_us"], 1):
            proc.add_gatestat({"attachment": "a-1", "gate": {"seq": x["sequence"], "sc": [0, 1, 0, 0], "ff": [0, 4, 0, 0], "lf": [999] * 4}})
    assert not [c for c in proc.members if "rate above" in proc.cell_status(c)[1]]


def test_missing_gates_are_painted_as_acquisition_gap():
    rng = np.random.default_rng(4)
    proc, traj, cal = make()
    t1 = drive(traj, 1_000_000, 0.3, 2.7, 0.0)
    proc.add_mark(1_000_000, stage="SCAN", tag="P0")
    g, _ = gate_records(proc, cal, 1_000_000, t1, 0, rng)
    for x in g:
        if not 100 <= x["sequence"] < 105:                          # five lost gate records (head 0.6.0)
            proc.add_gate(x)
    proc.finish()
    cls = proc.classify_subcells()
    r = proc.cfg.sub_res
    x_mid = 0.3 + 0.1 * 10.25 + 0.2                                  # where the head was during gates 100-104 (lane row ahead of base)
    assert (cls[:, int(x_mid / r)] == REASONS.index("ACQUISITION_GAP")).any()
    assert proc.missing_gates and proc.missing_gates[0]["first_missing"] == 100 and proc.missing_gates[0]["last_missing"] == 104


# ------------------------------------------------------------------ U_null rules (MODEL.md rev 5 section 3)
def _series(n=400, rate=(4.0, 4.0, 4.0, 4.0), v=0.1, seed=1, step_at=None, step=1.0):
    rng = np.random.default_rng(seed)
    ref, geo_ = {}, {}
    for q in range(n):
        f = step if (step_at is not None and q >= step_at) else 1.0
        ref[q] = [(int(rng.poisson(r * f * 0.1)), 0.1) for r in rate]
        geo_[q] = (q * v * 0.1, 0.0)
    return unull.Series.build(ref, geo_)


def test_n_min_table():
    assert [unull.n_min(a) for a in (0.05, 0.01, 0.005, 1e-3, 5e-4, 1e-4, 1e-5, 1e-6)] == [30, 30, 75, 75, 125, 125, 200, 200]
    assert unull.n_min(1e-7) > 200


def test_two_sub_windows_larger_mean_and_exclusion():
    s = _series()
    rec = unull.u_null(s, 1, (200, 209), 0.01, exclude_seqs=set(range(200, 210)))
    assert rec["status"] == "OK" and rec["source"] == "lane" and rec["two_sided"]
    w1, w2 = rec["windows"]
    assert w1["seq_hi"] < 200 and w2["seq_lo"] > 209 and min(w1["n"], w2["n"]) >= 30
    assert rec["U0"] == pytest.approx(max(w1["mean"], w2["mean"])) and rec["N_post"] == rec["windows"][rec["selected"]]["n"]


def test_one_sided_window_gradient_guard_and_pooled_beyond_2m():
    s = _series(step_at=60, step=1.5)                                   # a 50 % step 6 s after the dwell, robot at 0.1 m/s
    rec = unull.u_null(s, 0, (0, 4), 0.01, exclude_seqs=set(range(5)))
    assert not rec["two_sided"] and rec["status"] in ("OK", "GRADIENT")
    flat = _series(n=1400, seed=7)
    deep = unull.u_null(flat, 0, (1395, 1399), 1e-6, exclude_seqs=set(range(1395, 1400)))   # 2 x 200 counts on one side: 10 m
    assert deep["source"] == "pooled" and "lane_rejected" in deep and deep["lane_ratio"] == pytest.approx(1.0, abs=0.1)
    assert deep["N_post"] < deep["windows"][deep["selected"]]["n"]                      # effective count of the ratio-scaled pool


def test_recount_reference_from_the_other_three_lanes():
    """Ratio-scaled other-lane reference during a 30 s recount (360 counts >= N_min 200 at 0.2 alpha_recount); unbiased
    over 20 seeds (simulated)."""
    recs = [unull.recount_u_null(_series(n=900, rate=(4.0, 4.4, 4.0, 3.6), seed=k), 1, list(range(250, 550)), 1.71e-4 * 0.2)
            for k in range(20)]
    assert all(r["source"] == "other-lanes-during-recount" for r in recs)
    assert np.mean([r["U0"] for r in recs]) == pytest.approx(4.4, rel=0.04)
    short = unull.recount_u_null(_series(n=900, rate=(4.0, 4.4, 4.0, 3.6)), 1, list(range(250, 350)), 1.71e-4 * 0.2)
    assert short.get("fallback")                     # 10 s: too few other-lane counts -> own-lane rule


# ------------------------------------------------------------------ predictive threshold against the reference implementation
def _rr():
    sys.path.insert(0, str(REPO / "analysis" / "radiometry"))
    return pytest.importorskip("rrrad.rev3"), pytest.importorskip("rrrad.unull")


@pytest.mark.parametrize("cls,v,nw,alpha", [("beta", 0.03, 50, 0.01), ("beta", 0.10, 30, 0.04), ("beta", 0.03, 200, 1e-3),
                                             ("alpha", 0.03, 75, 0.0025)])
def test_predictive_threshold_and_detection_limit_equal_rrrad(cls, v, nw, alpha):
    R, N = _rr()
    from scipy.optimize import brentq
    rc = R.BETA_CAL if cls == "beta" else R.ALPHA_CAL
    cal = Cal(k=rc.k, b=rc.b, u_k_lane=rc.u_k_lane, u_k_common=rc.u_k_common, u_b=rc.u_b, cov_kb=rc.cov_kb, K=rc.K, u_rel_K=rc.u_rel_K)
    lane = R.cell_lane_weights(0.04375, v=v)
    U = 4.0
    Tw = nw / U
    t_rr = N.threshold_rule(N.LaneCase(lane, rc), nw, Tw, alpha, "predictive")
    g = LaneGates(0, lane.w, lane.t, np.zeros_like(lane.w), lane.t, np.zeros_like(lane.w), nw / Tw, "t", cal, N_post=nw, T_post=Tw)
    dec = Decider()
    key = dec._lane_key(g)
    _c, t, ok, method = dec.threshold((key,), alpha)
    assert ok and method == f"linear-exact/gil-pelaez/predictive-U(N={nw:.1f})"
    assert t == pytest.approx(t_rr / rc.K, rel=1e-6)
    us, ws = N.posterior_nodes(nw, Tw, 12)

    def pw(D):
        return sum(w * float(R.truth_tail(lane, rc, u, rho=rc.K * D, sig=np.hypot(rc.sig(u), rc.u_rel_K * rc.K * D))(t_rr)[0]) for u, w in zip(us, ws))
    d_rr = brentq(lambda D: pw(D) - 0.95, 1e-4, 50, xtol=1e-12, rtol=1e-10)
    assert dec.limit((key,), alpha, 0.05) == pytest.approx(d_rr, rel=1e-6)


def test_uncertainty_components_and_footprint_dilution_exported():
    lanes = [LaneGates(i, [1.0, 0.5, 0.25], [0.1] * 3, [0.6] * 3, [0.1] * 3, [0.4] * 3, 4.0, "t",
                       Cal(k=1.0, b=0.5, u_k_lane=0.003, u_k_common=0.03, u_b=0.054, K=24.0, u_rel_K=0.15), N_post=100, T_post=25.0)
             for i in range(2)]
    d = est.combine(lanes, 0.05, 0.05, decider=Decider())
    u = d.u_components
    assert u["u_total" if False else "u_stat"] == pytest.approx(d.u_stat)
    assert math.sqrt(u["u_stat"] ** 2 + u["u_cal_lane"] ** 2 + u["u_cal_common_k"] ** 2 + u["u_cal_K"] ** 2) == pytest.approx(d.u_total)
    assert d.footprint_dilution[0] == pytest.approx((1 + 0.25 + 0.0625) / 1.75)
