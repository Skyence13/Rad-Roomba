"""Real-time runtime shared by the ROS robot node and stand-alone tools: RobotApp on
real transports (serial:// or tcp://), the app loop thread and the web server thread."""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from pathlib import Path

import yaml

from rr_core.transport import Clock, open_transport
from rr_web.control import ControlCenter, hash_password
from rr_web.server import AppBackend, make_app

from .app import RobotApp
from .geometry_config import CONFIG, load_robot_geometry


DEMO_ACCOUNTS_WARNING = ("WARNING: DEMONSTRATION ACCOUNTS loaded ({names}); passwords are trivial or stored in plain "
                         "text and the operator interface is plain HTTP without TLS. NOT for field use: replace the "
                         "accounts (password_hash only) and put TLS + real authentication in front of the service first.")


def load_users(path=None, warn=True):
    """Accounts file -> {name: {role, password_hash, demo}}.  A file marked `demo: true`, or any
    account given with a plain-text `password`, is a DEMO account set: every account is flagged
    `demo`, and a warning is printed on stderr at load (i.e. at service start-up)."""
    import sys
    doc = yaml.safe_load(Path(path or CONFIG / "users_demo.yaml").read_text())
    demo = bool(doc.get("demo")) or any("password" in u for u in doc["users"].values())
    users = {}
    for name, u in doc["users"].items():
        users[name] = {"role": u["role"], "password_hash": u.get("password_hash") or hash_password(u["password"], name),
                       "demo": demo}
    if demo and warn:
        print(DEMO_ACCOUNTS_WARNING.format(names=", ".join(sorted(users))), file=sys.stderr, flush=True)
    return users


def load_registry(path, mount=None):
    reg = json.loads(Path(path).read_text())
    for rec in reg["records"]:
        rec.setdefault("mount_transform", mount or load_robot_geometry()["mount_transform"])
    return reg


def demo_registry():
    """SIMULATION ONLY: registry record for the packaged demo descriptor (the baseline
    examples/head_descriptor.json served by the Python head fake)."""
    from rr_core.profiles import DATA
    data = (DATA / "head_descriptor_demo.json").read_bytes()
    desc = json.loads(data)
    return {"records": [{"serial": desc["serial"], "descriptor_id": desc["descriptor_id"], "head_type": desc["head_type"],
                         "geometry_id": desc["geometry_id"], "setup_id": desc["setup_id"],
                         "descriptor_sha256": hashlib.sha256(data).hexdigest(), "firmware": "sim-1.0",
                         "authorized_uses": ["BENCH", "COMMISSIONING"], "calibration_id": "DEMO-CAL-SYNTH-0001",
                         "mount_transform": load_robot_geometry()["mount_transform"]}]}


def provision_registry_from_head(url, calibration_id="DEMO-CAL-SYNTH-0001", timeout_s=5.0):
    """LAB/SIMULATION ONLY: read HELLO + descriptor from the attached head or emulator and
    write a COMMISSIONING registry record for it (the step a qualified person performs when
    a head is approved).  Never used on the survey path."""
    import base64
    from rr_core import wire
    tr = open_transport(url)
    t_end = time.monotonic() + timeout_s
    while not tr.reopen():
        if time.monotonic() > t_end:
            raise IOError(f"cannot open {url}")
        time.sleep(0.1)
    dec = wire.StreamDecoder()
    tid = [int(time.monotonic() * 1000) & 0xFFFFFF]

    def tx(op, args):
        tid[0] += 1
        tr.write(wire.encode(wire.make_request("2.0", tid[0], op, args)))
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            tr.wait(0.05)
            for _raw, rec, _e in dec.feed(tr.read()):
                if rec and rec.get("id") == tid[0]:
                    return rec
        raise IOError(f"no reply to {op}")
    hello = tx("HELLO", {})["body"]
    data = b""
    while len(data) < hello["descriptor_bytes"]:
        body = tx("GET_DESCRIPTOR", {"boot_id": hello["boot_id"], "descriptor_id": hello["descriptor_id"],
                                     "offset": len(data), "count": min(768, hello["descriptor_bytes"] - len(data))})["body"]
        data += base64.b64decode(body["bytes_b64"])
    tr.close()
    desc = json.loads(data)
    return {"records": [{"serial": desc["serial"], "descriptor_id": desc["descriptor_id"], "head_type": desc["head_type"],
                         "geometry_id": desc["geometry_id"], "setup_id": desc["setup_id"],
                         "descriptor_sha256": hashlib.sha256(data).hexdigest(), "firmware": hello["firmware"],
                         "authorized_uses": ["BENCH", "COMMISSIONING"], "calibration_id": calibration_id,
                         "mount_transform": load_robot_geometry()["mount_transform"],
                         "provisioned": "automatically from the attached emulator (simulation only)"}]}


class Runtime:
    def __init__(self, head_url, chassis_url, run_dir, config=None, registry=None, users=None, web_port=8080,
                 web_host="0.0.0.0", resume=False, sim_hooks=None):
        self.clock = Clock()
        self.lock = threading.RLock()
        cfg = dict(config or {})
        if head_url.startswith("tcp://"):
            cfg.setdefault("link", {}).setdefault("byte_time_us", 0.0)       # emulator: no UART serialisation
        self.app = RobotApp(self.clock, open_transport(head_url), open_transport(chassis_url), run_dir, registry, cfg,
                            resume=resume)
        self.cc = ControlCenter(self.clock, users or load_users(),
                                audit_sink=lambda rec: self.app._aux_sink((self.clock.now_us(), "X", {"x": "web_audit", **rec})))
        self.app.control_ok = self.cc.control_ok
        self.backend = AppBackend(self.app, self.lock)
        self.web_host, self.web_port, self.sim_hooks = web_host, web_port, sim_hooks
        self._stop = threading.Event()
        self.threads = []

    def start(self, web=True):
        t = threading.Thread(target=self._loop, name="rr-app", daemon=True)
        t.start()
        self.threads.append(t)
        if web:
            t = threading.Thread(target=self._web, name="rr-web", daemon=True)
            t.start()
            self.threads.append(t)

    def stop(self):
        self._stop.set()
        time.sleep(0.05)
        with self.lock:
            self.app.archive.close()

    def _loop(self):
        while not self._stop.is_set():
            with self.lock:
                self.app.step()
            time.sleep(0.0005)

    def _web(self):
        from aiohttp import web
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app(self.backend, self.cc, self.sim_hooks))
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, self.web_host, self.web_port).start())
        loop.run_forever()
