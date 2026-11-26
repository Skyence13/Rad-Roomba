"""Scenarios 1 and 2 against the native firmware emulators (real time, not deterministic).
Run:  tools/test.sh native [n01 n02 n03]   (default n01 n02; n03 = step-and-count, opt-in)
Evidence: ros2_ws/evidence/native_*/"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from rr_sim import scenarios as sc
from rr_sim.native import NativeSystem


def n01(tmp):
    sim = NativeSystem(Path(tmp) / "n01", sc._cfg(), seed=31)
    c = sc.Checks()
    extra = {}
    try:
        sim.bringup()
        app = sim.app
        patch = sc._seam_patch(sim, d=4.0)
        c.add("start accepted", app.command("start")["accepted"])
        sc._scan_to_end(sim, timeout=700)
        proc = app.pipeline.proc
        c.add("mission complete (REVIEW)", app.mission.state == "REVIEW" and app.mission.finish_reason == "COMPLETE",
              state=app.mission.state, hold=app.mission.hold_reason)
        flags = [f for f in proc.flags if f["kind"] == "INVESTIGATION_LEVEL" and math.hypot(f["x_m"] - patch[0], f["y_m"] - patch[1]) < 0.06]
        flags.sort(key=lambda f: -f["D"])
        c.add("hotspot across the seam flagged (independent findings are not merged; count reported)", len(flags) >= 1, n=len(flags))
        c.add("interior bands fully covered", min(sc._band_fraction(sim, p) for p in range(app.plan["n_pairs"])) == 1.0)
        if flags:
            flag = flags[0]
            extra["flag_position_error_vs_patch_m"] = math.hypot(flag["x_m"] - patch[0], flag["y_m"] - patch[1])
            c.add("Next accepted", app.command("next", {"flag": flag["id"]})["accepted"])
            sc._wait(sim, lambda: app.guidance.move is None, 240)
            st = app.guidance.status[flag["id"]]
            c.add("arrived AT_SPOT", st["status"] == "AT_SPOT", notes=st["notes"][-1:])
            if st["visits"]:
                tc = sc._true_lane_centre(sim, flag)
                extra["revisit_error_estimated_m"] = st["visits"][-1]["error_m"]
                extra["revisit_error_true_m"] = math.hypot(tc[0] - flag["x_m"], tc[1] - flag["y_m"])
                c.add("true lane centre within 10 mm of the saved footprint", extra["revisit_error_true_m"] <= 0.010, err=extra["revisit_error_true_m"])
            p0 = sim.truth()
            c.add("Expose accepted", app.command("expose")["accepted"])
            sc._wait(sim, lambda: app.guidance.move is None, 60)
            back = math.dist(p0[:2], sim.truth()[:2])
            extra["expose_reverse_m"] = back
            c.add("Expose reversed 0.35 m (+/- 10 mm)", abs(back - 0.35) < 0.010, back=back)
            c.add("Park accepted", app.command("park")["accepted"])
            sc._wait(sim, lambda: app.guidance.move is None, 240)
            c.add("parked", app.guidance.parked)
        ev = sc._finish("native_s01_survey_revisit", sim, c, extra)
    finally:
        sim.close()
    return ev


def n02(tmp):
    sim = NativeSystem(Path(tmp) / "n02", sc._cfg(), seed=32)
    c = sc.Checks()
    try:
        sim.bringup()
        app = sim.app
        app.command("start")
        sc._wait(sim, lambda: app.mission.task is not None and app.mission.task["name"] == "pair0:A+" and app.mission.phase == "PASS"
                 and sim.truth()[0] > 1.4, 300)
        n_sessions = len(app.pipeline.sessions)
        sim.head.reset()                                   # {"cmd":"fault","kind":"mcu_reset"}
        sc._wait(sim, lambda: app.mission.state == "HOLD", 8)
        c.add("mcu_reset: mission HOLD on head link loss", app.mission.state == "HOLD" and "HEAD_LINK" in str(app.mission.hold_reason), reason=app.mission.hold_reason)
        c.add("session closed with the last trusted boundary", len(app.pipeline.closes) == n_sessions and app.pipeline.closes[-1]["last_seq"] is not None,
              close=app.pipeline.closes[-1]["reason"] if app.pipeline.closes else None)
        sim.run(1.0)
        c.add("chassis latched PROTECTIVE_STOP/HEAD_LINK", "HEAD_LINK" in app.chassis.drive["stops"]["sw"], stops=app.chassis.drive["stops"])
        sc._wait(sim, lambda: app.head.state == "ARMED", 25)
        c.add("fresh handshake -> new attachment with a new boot id", len(app.pipeline.sessions) == n_sessions + 1
              and app.pipeline.sessions[-1]["boot_id"] != app.pipeline.sessions[-2]["boot_id"])
        close, opened = app.pipeline.closes[-1], app.pipeline.sessions[-1]
        between = [g for g in app.pipeline.proc.gate_log if g["t0_us"] is not None and g["t0_us"] > close["t_us"]
                   and g["attachment"] != opened["attachment_session_id"]]
        c.add("no counts attributed until the new BIND", not between)
        pose = sim.truth()
        c.add("resume rejected until deliberate re-arm", not app.command("resume")["accepted"])
        sim.run(2.0)
        c.add("no motion while latched", math.dist(pose[:2], sim.truth()[:2]) < 1e-3)
        app.command("rearm", actor="op1")
        sim.run(0.8)
        r = app.command("resume")
        c.add("resume accepted after re-arm", r["accepted"], result=r)
        sc._scan_to_end(sim, timeout=700, stop_on_hold=False)
        c.add("mission complete", app.mission.state == "REVIEW", state=app.mission.state, hold=app.mission.hold_reason)
        c.add("affected strip re-surveyed (bands complete)", min(sc._band_fraction(sim, p) for p in (0, 1)) == 1.0,
              bands=[sc._band_fraction(sim, p) for p in (0, 1)])
        ev = sc._finish("native_s02_head_reset", sim, c, {})
    finally:
        sim.close()
    return ev


def n03(tmp, preset_s=3.0):
    """Step-and-count on the native emulators (opt-in: `tools/test.sh native n03`): only static
    scaler gates earn credit; the hot spot is flagged from static counts."""
    cfg = sc._cfg(trailer={"id": "SIM-SECTION-1.8x1.0", "length_m": 1.8, "width_m": 1.0},
                  mission={"method": "STEP_AND_COUNT", "station_preset_s": preset_s})   # pitch: contract default (0.080 m, CR-05)
    sim = NativeSystem(Path(tmp) / "n03", cfg, seed=33)
    c = sc.Checks()
    try:
        sim.bringup()
        app = sim.app
        ya = next(t["y"] for t in app.plan["tasks"] if t["name"] == "pair0:A+")
        sim.world.add_patch(0.95, 1.04, ya + 0.04375 - 0.03, ya + 0.04375 + 0.03, 3.0)
        c.add("start accepted", app.command("start")["accepted"])
        sc._scan_to_end(sim, timeout=3000, stop_on_hold=False)
        proc = app.pipeline.proc
        c.add("mission complete", app.mission.state == "REVIEW", state=app.mission.state, hold=app.mission.hold_reason)
        stations = proc.stations
        moving = [g for g in proc.gate_log if g["stage"] is None and g["pose"] is not None]
        credited_stage = {g["stage"] for g in proc.gate_log if any(l["credited"] for l in g["lanes"])}
        c.add("only static SCALER gates earn credit; moving gates archived without credit", credited_stage == {"SCALER"} and len(moving) > 50,
              stages=sorted(map(str, credited_stage)), moving=len(moving))
        rows = [r for r in proc.cells_table() if r["n_lane_gates"]]
        c.add("every cell records method and stage", all(r["method"] == "STEP_AND_COUNT" and r["stage"] == "SCALER" for r in rows))
        flags = [f for f in proc.flags if f["kind"] == "INVESTIGATION_LEVEL"]
        c.add("hot spot flagged from static counts", any(abs(f["x_m"] - 0.995) < 0.06 for f in flags), flags=[(f["id"], f["x_m"], f["y_m"]) for f in flags])
        dh = sorted(d.D_hash for d in proc.decisions["beta"].values() if d.D is not None and math.isfinite(d.D_hash))
        ev = sc._finish("native_s10_step_and_count", sim, c, {"stations": len(stations), "stations_invalid": sum(1 for s in stations if not s["valid"]),
                                                             "station_preset_s": preset_s, "station_pitch_m": app.mission.cfg.station_pitch_m, "D_hash_median": dh[len(dh) // 2] if dh else None})
    finally:
        sim.close()
    return ev


if __name__ == "__main__":
    import json
    import tempfile
    which = sys.argv[1:] or ["n01", "n02"]
    ok = True
    for name in which:
        ev = globals()[name](tempfile.mkdtemp(prefix="rr_native_"))
        p = Path(sc.EVIDENCE) / ev["scenario"] / "evidence.json"
        data = json.loads(p.read_text())
        data["against"] = "native firmware emulators rr_head_sim + rr_chassis_sim (real time; world/LiDAR from rr_sim.world)"
        data["deterministic"] = False
        p.write_text(json.dumps(data, indent=1) + "\n")
        print(ev["scenario"], "PASS" if ev["passed"] else "FAIL")
        for chk in ev["checks"]:
            if not chk["ok"]:
                print("   FAILED:", chk)
                ok = False
    sys.exit(0 if ok else 1)
