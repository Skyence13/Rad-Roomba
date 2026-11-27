"""Adapters and a real-time harness for the NATIVE firmware emulators (the firmware cores
compiled for Linux): `rr_head_sim` (TCP 5540, stimulus UDP 5541) and `rr_chassis_sim`
(TCP 5550, environment UDP 5551).  The RobotApp runs unchanged on tcp:// transports with the
real clock; only the world model talks to the emulators' side sockets."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from rr_bringup.app import RobotApp, merge
from rr_bringup.geometry_config import load_robot_geometry
from rr_bringup.runtime import provision_registry_from_head
from rr_core.geometry import lane_polygons
from rr_core.profiles import DATA, Calibration
from rr_core.transport import Clock, open_transport
from rr_sim.world import World


class _Udp:
    def __init__(self, port):
        self.addr = ("127.0.0.1", port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    def send(self, obj):
        try:
            self.sock.sendto(json.dumps(obj).encode(), self.addr)
        except OSError:
            pass

    def drain(self):
        out = []
        while True:
            try:
                data, _ = self.sock.recvfrom(65536)
            except (BlockingIOError, OSError):
                return out
            try:
                out.append(json.loads(data))
            except ValueError:
                pass


class NativeHead:
    """Stimulus/fault socket of rr_head_sim (firmware/head/README.md)."""

    def __init__(self, port=5541):
        self.udp = _Udp(port)

    def set_rates(self, rates):
        self.udp.send({"cmd": "rates", "alpha": [rates[n]["alpha"] for n in range(4)],
                       "beta": [rates[n]["beta"] for n in range(4)], "ref": [rates[n]["ref"] for n in range(4)]})
        self.udp.drain()

    def reset(self):
        self.udp.send({"cmd": "fault", "kind": "mcu_reset"})

    def fault(self, kind, **kw):
        self.udp.send(dict(cmd="fault", kind=kind, **kw))

    def power(self, on):
        pass                      # the emulator process is always powered

    def step(self):
        pass


class NativeChassis:
    """Environment socket of rr_chassis_sim (firmware/chassis/README.md): inputs + TRUTH stream."""

    def __init__(self, port=5551):
        self.udp = _Udp(port)
        self._truth = {"x": 0.0, "y": 0.0, "yaw": 0.0, "v": 0.0, "w": 0.0}
        self.history = []                 # (chassis_us, x, y, yaw) of every TRUTH datagram (IB-47: compare by chassis time)
        self.emu_lag_max_us = 0
        self.emu_rebases = 0
        self.udp.send({})         # any datagram subscribes the sender to TRUTH

    def env(self, name, value):
        self.udp.send({name: value})

    def press(self, name):
        self.udp.send({"press": name})

    def poll(self):
        for msg in self.udp.drain():
            if msg.get("type") == "TRUTH":
                self._truth = msg
                if msg.get("chassis_us") is not None:
                    self.history.append((msg["chassis_us"], msg["x"], msg["y"], msg["yaw"]))
                    del self.history[:-20000]
                self.emu_lag_max_us = max(self.emu_lag_max_us, msg.get("emu_lag_us") or 0)
                self.emu_rebases = max(self.emu_rebases, msg.get("emu_rebases") or 0)

    def truth(self):
        self.poll()
        return self._truth

    def step(self):
        self.poll()


def find_binaries():
    repo = Path(os.environ.get("RR_REPO", Path(__file__).resolve().parents[4]))
    head = repo / "firmware/head/build/host/rr_head_sim"
    chassis = repo / "firmware/chassis/build/rr_chassis_sim"
    return (head if head.exists() else None), (chassis if chassis.exists() else None)


class NativeSystem:
    """Real-time counterpart of rr_sim.harness.SimSystem on the native emulators."""

    def __init__(self, run_dir, config=None, seed=1, log_dir=None):
        head_bin, chassis_bin = find_binaries()
        if not head_bin or not chassis_bin:
            raise FileNotFoundError("native emulators are not built (firmware/head/build/host, firmware/chassis/build)")
        shutil.rmtree(run_dir, ignore_errors=True)
        log_dir = Path(log_dir or run_dir).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        self.procs = [subprocess.Popen([str(head_bin), "--seed", str(seed)], stdout=open(log_dir / "rr_head_sim.log", "w"), stderr=subprocess.STDOUT),
                      subprocess.Popen([str(chassis_bin), "--seed", str(seed), "--quiet"], stdout=open(log_dir / "rr_chassis_sim.log", "w"), stderr=subprocess.STDOUT)]
        time.sleep(0.6)
        self.seed = seed
        self.clock = Clock()
        registry = provision_registry_from_head("tcp://127.0.0.1:5540")       # simulation-only provisioning
        self.registry = registry
        cfg = merge({"link": {"byte_time_us": 0.0, "reply_timeout_us": 60_000}, "chassis_thread": True}, config)
        self.app = RobotApp(self.clock, open_transport("tcp://127.0.0.1:5540"), open_transport("tcp://127.0.0.1:5550"),
                            run_dir, registry, cfg)
        self.head, self.chassis = NativeHead(), NativeChassis()
        geo = load_robot_geometry()
        tr = self.app.cfg["trailer"]
        self.world = None
        self._world_args = (tr, geo)
        self.t0 = time.monotonic()
        self._next_world = self._next_scan = 0.0
        self.trace = []

    def _ensure_world(self):
        if self.world is None and self.app.pipeline.sessions:
            import base64
            m = self.app.pipeline.sessions[-1]
            tr, geo = self._world_args
            lanes = lane_polygons(json.loads(base64.b64decode(m["descriptor_b64"])), m["mount_transform"])
            self.world = World(tr["length_m"], tr["width_m"], Calibration.load(DATA / "demo_calibration.json"), lanes,
                               seed=self.seed, door_closed=tr["door_closed"], door_target_x_m=tr.get("door_target_x_m"), lidar_xy=tuple(geo["lidar"]["xy"]))

    @property
    def t(self):
        return time.monotonic() - self.t0

    def truth(self):
        t = self.chassis.truth()
        return (t["x"], t["y"], t["yaw"])

    def tick(self):
        self.app.step()
        now = time.monotonic()
        self._ensure_world()
        if now >= self._next_world:
            self._next_world = now + 0.01
            self.chassis.poll()
            if self.world is not None:
                self.head.set_rates(self.world.rates(self.truth()))
        if now >= self._next_scan and self.world is not None:
            self._next_scan = now + 0.1
            pose = self.truth()
            angles, ranges = self.world.scan(pose)
            self.app.on_scan(self.clock.now_us(), angles, ranges)
            if self.app.loc.initialized:
                odom = (self.app.chassis.drive.get("odom") or {}).get("t_us")
                self.trace.append((self.t, *pose, *[float(v) for v in self.app.loc.x], odom,
                                   self.chassis._truth.get("emu_lag_us"), self.chassis._truth.get("emu_rebases")))
        time.sleep(0.0004)

    def run(self, seconds=None, until=None, timeout=600.0):
        end = time.monotonic() + (seconds if seconds is not None else timeout)
        n = 0
        while time.monotonic() < end:
            self.tick()
            n += 1
            if until is not None and n % 20 == 0 and until():
                return True
        return until is None

    def bringup(self):
        app = self.app
        assert self.run(until=lambda: app.plan is not None and app.head.state == "ARMED" and app.chassis.link_state == "UP", timeout=25), \
            (app.head.state, app.head.block_reason, app.head.block_detail, app.chassis.link_state)
        start = app.park_pose
        self.chassis.env("pose", list(start))
        self.run(0.3)
        assert app.command("register_datum", {"pose": list(start)})["accepted"]
        assert app.command("preflight")["accepted"]
        self.run(0.8)
        self.chassis.press("REARM")
        self.run(1.0)
        assert app.command("preflight")["accepted"]
        assert self.run(until=lambda: app.mission.preflight_done
                        and app.chassis.drive.get("mode") == "STANDBY", timeout=10), (app.chassis.drive.get("mode"), app.chassis.state.get("brake_test"))
        self.chassis.press("REARM")
        self.run(1.5)
        out = app.command("arm")
        assert out["accepted"], out
        return out

    def loc_error(self):
        e = [abs(t[1] - t[4]) for t in self.trace[5:]], [abs(t[2] - t[5]) for t in self.trace[5:]]
        return {"max_x_m": max(e[0], default=0.0), "max_y_m": max(e[1], default=0.0)}

    def truth_at_chassis_us(self, t_us):
        """TRUTH pose interpolated at a chassis timestamp (None outside the recorded history)."""
        import bisect
        h = self.chassis.history
        if not h or t_us is None or t_us < h[0][0] or t_us > h[-1][0]:
            return None
        i = bisect.bisect_left(h, (t_us,))
        if i == 0 or h[i][0] == t_us:
            return h[i][1:]
        (t0, *a), (t1, *b) = h[i - 1], h[i]
        f = (t_us - t0) / (t1 - t0)
        return tuple(x + f * (y - x) for x, y in zip(a, b))

    def loc_error_by_chassis_time(self):
        """IB-47: estimate (state of the last odometry sample, chassis time) against TRUTH at that chassis time, instead of
        against the newest datagram at host arrival time.  Returns the same keys as loc_error plus emulator pacing info."""
        ex, ey = [], []
        for row in self.trace[5:]:
            tr = self.truth_at_chassis_us(row[7]) if len(row) > 7 else None
            if tr is not None:
                ex.append(abs(tr[0] - row[4]))
                ey.append(abs(tr[1] - row[5]))
        return {"max_x_m": max(ex, default=None), "max_y_m": max(ey, default=None), "samples": len(ex),
                "emu_lag_max_us": self.chassis.emu_lag_max_us, "emu_rebases": self.chassis.emu_rebases}

    def close(self):
        try:
            self.app.shutdown()
            self.app.archive.close()
        except Exception:
            pass
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()
