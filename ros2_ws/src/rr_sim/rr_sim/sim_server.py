"""Stand-alone simulator with the operator UI (no ROS graph needed):

    python3 -m rr_sim.sim_server --port 8080 [--method STEP_AND_COUNT] [--auto]

Runs the deterministic harness (Python fakes, kinematic world) paced to real time and
serves the operator interface.  Demo accounts: viewer/viewer, operator/operator, rp/rp.
`--auto` performs the operator bring-up (datum, REARM, brake test, REARM, arm) at start."""
import argparse
import asyncio
import shutil
import threading
import time
from pathlib import Path

from aiohttp import web

from rr_bringup.runtime import load_users
from rr_core.transport import Clock
from rr_sim.harness import SimSystem
from rr_sim.sim_node import sim_action
from rr_web.control import ControlCenter
from rr_web.server import AppBackend, make_app


def build(run_dir, method="CONTINUOUS_SCAN", speed=0.10, length=3.0, width=1.2, seed=1, auto=False, patch=True):
    shutil.rmtree(run_dir, ignore_errors=True)
    sim = SimSystem(run_dir, {"trailer": {"id": f"SIM-SECTION-{length}x{width}", "length_m": length, "width_m": width},
                              "mission": {"method": method, "speed": speed, "station_preset_s": 3.0, "scaler_preset_s": 10.0,
                                          "ratemeter_alpha": 1e-5}}, seed=seed)
    if auto:
        sim.bringup()
    else:
        sim.run(until=lambda: sim.app.plan is not None, timeout=15)
        sim.chassis.env("pose", sim.app.park_pose)
    if patch and sim.app.plan:
        ya = sim.app.plan["tasks"][0]["y"]
        sim.world.add_patch(1.50, 1.59, ya - 0.03, ya + 0.03, 3.0)
    lock = threading.RLock()
    # sessions and the control lease are human-time concepts: wall clock, not the (sped-up) sim clock
    cc = ControlCenter(Clock(), load_users(), lease_ttl_s=5.0)
    sim.app.control_ok = cc.control_ok
    backend = AppBackend(sim.app, lock)
    hooks = lambda body: sim_action(sim.world, sim.chassis, sim.head, body, sim.truth())   # noqa: E731
    return sim, lock, cc, make_app(backend, cc, hooks)


def pace(sim, lock, speedup=1.0, stop=None):
    t_wall, t_sim = time.monotonic(), sim.t
    while stop is None or not stop.is_set():
        with lock:
            for _ in range(20):
                sim.tick()
        lag = (sim.t - t_sim) / speedup - (time.monotonic() - t_wall)
        if lag > 0:
            time.sleep(lag)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--run-dir", default="/tmp/rr_runs/sim_server")
    ap.add_argument("--method", default="CONTINUOUS_SCAN", choices=["CONTINUOUS_SCAN", "SEARCH_THEN_COUNT", "STEP_AND_COUNT"])
    ap.add_argument("--speed", type=float, default=0.10)
    ap.add_argument("--speedup", type=float, default=1.0)
    ap.add_argument("--auto", action="store_true")
    a = ap.parse_args()
    sim, lock, cc, app = build(Path(a.run_dir), a.method, a.speed, auto=a.auto)
    threading.Thread(target=pace, args=(sim, lock, a.speedup), daemon=True).start()
    print(f"operator UI: http://127.0.0.1:{a.port}/  (viewer/viewer, operator/operator, rp/rp) - SYNTHETIC data")
    web.run_app(app, host=a.host, port=a.port, print=None)


if __name__ == "__main__":
    main()
