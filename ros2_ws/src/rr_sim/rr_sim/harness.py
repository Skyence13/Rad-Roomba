"""Deterministic in-process simulation harness (virtual clock, 1 ms tick):
RobotApp + Python protocol fakes + kinematic world.  Used by the end-to-end
scenario tests; the same RobotApp runs in real time against the native firmware
emulators (`rr_sim.native`)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from rr_bringup.app import RobotApp, merge
from rr_core.fakes.chassis import FakeChassis
from rr_core.fakes.head import FakeHead
from rr_core.geometry import lane_polygons
from rr_core.profiles import DATA, Calibration
from rr_core.transport import MemoryLink, VirtualClock
from rr_sim.world import World

from rr_bringup.geometry_config import load_robot_geometry

MOUNT = load_robot_geometry()["mount_transform"]      # frames.yaml head_mount (nominal design value)


from rr_bringup.runtime import demo_registry as _demo_registry


def demo_registry(descriptor_bytes=None, firmware="sim-1.0"):
    return _demo_registry()


class SimSystem:
    def __init__(self, run_dir, config=None, seed=1, head_delay=(200, 200), chassis_delay=(150, 150),
                 head_drift_ppm=20.0, chassis_drift_ppm=-15.0, resume=False, start_pose=None, clock=None, world=None):
        self.clock = clock or VirtualClock()
        self.seed = seed
        desc = (DATA / "head_descriptor_demo.json").read_bytes()
        self.hlink = MemoryLink(self.clock, "head", delay_us=head_delay, byte_time_us=10.0)
        self.clink = MemoryLink(self.clock, "chassis", delay_us=chassis_delay)
        self.head = FakeHead(self.clock, self.hlink.ends[1], desc, seed=seed, clock_drift_ppm=head_drift_ppm)
        cal = Calibration.load(DATA / "demo_calibration.json")
        cfg = merge({"link": {}}, config)
        n = [0]

        def uuid():
            n[0] += 1
            return f"00000000-0000-4000-8000-{seed:04d}{n[0]:08d}"
        self.app = RobotApp(self.clock, self.hlink.ends[0], self.clink.ends[0], run_dir, demo_registry(desc), cfg,
                            uuid_factory=uuid, resume=resume)
        tr = self.app.cfg["trailer"]
        lanes = lane_polygons(json.loads(desc), MOUNT)
        self.world = world or World(tr["length_m"], tr["width_m"], cal, lanes, seed=seed, door_closed=tr["door_closed"], door_target_x_m=tr.get("door_target_x_m"),
                                    lidar_xy=tuple(self.app.cfg["lidar"]["xy"]))
        self.chassis = FakeChassis(self.clock, self.clink.ends[1], seed=seed, pose=start_pose or (0.6, 0.0, 0.0),
                                   drift_ppm=chassis_drift_ppm)
        self.t0 = self.clock.now_us()
        self.script = []            # (t_s, callable) executed once when sim time passes t_s
        self.trace = []             # (t_s, true x, y, yaw, est x, y, yaw)
        self._tick = 0

    @property
    def t(self):
        return (self.clock.now_us() - self.t0) * 1e-6

    def at(self, t_s, fn):
        self.script.append([t_s, fn])
        self.script.sort(key=lambda s: s[0])

    def tick(self):
        self.clock.advance(1000)
        self._tick += 1
        while self.script and self.script[0][0] <= self.t:
            self.script.pop(0)[1]()
        self.head.step()
        self.chassis.step()
        if self._tick % 10 == 0:
            self.head.power(bool(self.chassis.head_power["electronics"]))     # J1 branch switched by the chassis
            truth = (self.chassis.x, self.chassis.y, self.chassis.yaw)
            self.head.set_rates(self.world.rates(truth))
            self.chassis.inputs["rear_blocked"] = self.world.rear_blocked(truth, self.app.outline)
        if self._tick % 100 == 0:
            truth = (self.chassis.x, self.chassis.y, self.chassis.yaw)
            angles, ranges = self.world.scan(truth)
            self.app.on_scan(self.clock.now_us(), angles, ranges)
            if self.app.loc.initialized:
                self.trace.append((self.t, *truth, *[float(v) for v in self.app.loc.x]))
        self.app.step()

    def run(self, seconds=None, until=None, timeout=3600.0):
        end = self.t + (seconds if seconds is not None else timeout)
        while self.t < end:
            self.tick()
            if until is not None and self._tick % 20 == 0 and until():
                return True
        return until is None

    # ---------------------------------------------------------------- helpers
    def bringup(self, pose_error=(0.0, 0.0, 0.0)):
        """Operator sequence up to ARMED: datum registration, local REARM, brake test, REARM, arm."""
        app = self.app
        assert self.run(until=lambda: app.plan is not None and app.head.state == "ARMED" and app.chassis.link_state == "UP", timeout=15)
        start = app.park_pose
        self.chassis.env("pose", start)
        est = (start[0] + pose_error[0], start[1] + pose_error[1], start[2] + pose_error[2])
        assert app.command("register_datum", {"pose": est})["accepted"]
        assert app.command("preflight")["accepted"]
        self.press_rearm()                                    # ICD 4.6: only when rearm_ready, one press
        assert app.command("preflight")["accepted"]          # now ARMED_IDLE -> brake test (drops the latch)
        assert self.run(until=lambda: app.mission.preflight_done
                        and app.chassis.drive.get("mode") == "STANDBY", timeout=12), (app.chassis.drive.get("mode"), app.chassis.state.get("brake_test"))
        self.press_rearm()
        out = app.command("arm")
        assert out["accepted"], out
        return out

    def press_rearm(self, timeout=10.0):
        """Operator action of the ICD: wait until the robot reports `rearm_ready`, press the local REARM button ONCE, and
        check that the latch was set; raises with the refusal reason if not."""
        app = self.app
        assert self.run(until=lambda: app.chassis.state.get("rearm_ready") is True, timeout=timeout), \
            ("rearm_ready never true", app.chassis.state.get("chain"), app.chassis.state.get("faults"), app.chassis.drive.get("mode"))
        self.chassis.press("REARM")
        assert self.run(until=lambda: app.chassis.drive.get("mode") == "ARMED_IDLE" or (app.chassis.state.get("hw_latch") is True), timeout=3.0), \
            ("REARM refused", self.chassis.last_rearm_refusal, app.chassis.drive.get("mode"))

    def truth(self):
        return (self.chassis.x, self.chassis.y, self.chassis.yaw)

    def loc_error(self):
        e = [abs(t[1] - t[4]) for t in self.trace[5:]], [abs(t[2] - t[5]) for t in self.trace[5:]]
        return {"max_x_m": max(e[0], default=0.0), "max_y_m": max(e[1], default=0.0)}
