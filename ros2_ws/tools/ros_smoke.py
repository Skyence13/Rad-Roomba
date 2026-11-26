#!/usr/bin/env python3
"""ROS graph smoke test (real time, not deterministic): launches sim.launch.py, performs
the operator bring-up through ROS services, starts a scan and checks that gates, coverage,
state and the web interface are live.  Writes evidence/ros_smoke/evidence.json."""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from rr_interfaces.msg import CoverageStatus, GateCounts, MissionState, SafetyState
from rr_interfaces.srv import ExportSurvey, MissionCommand

NATIVE = "--native" in sys.argv
out = Path(os.environ["RR_WS"]) / "evidence" / ("ros_smoke_native" if NATIVE else "ros_smoke")
out.mkdir(parents=True, exist_ok=True)
launch = subprocess.Popen(["ros2", "launch", "rr_bringup", "sim.launch.py", "web_port:=8097", f"run_dir:=/tmp/rrhome/ros_smoke_{int(time.time())}"]
                          + (["native:=true"] if NATIVE else []), stdout=open(out / "launch.log", "w"), stderr=subprocess.STDOUT)
rclpy.init()
n = Node("rr_smoke")
latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
seen = {"gates": 0, "eligible": 0, "mission": None, "coverage": None, "safety": None}
n.create_subscription(GateCounts, "head/gates", lambda m: seen.update(gates=seen["gates"] + 1, eligible=seen["eligible"] + sum(l.eligible for l in m.lanes)), 50)
n.create_subscription(MissionState, "mission/state", lambda m: seen.update(mission=m), latched)
n.create_subscription(CoverageStatus, "coverage/status", lambda m: seen.update(coverage=m), latched)
n.create_subscription(SafetyState, "safety/state", lambda m: seen.update(safety=m), 5)
cmd, simc, exp = n.create_client(MissionCommand, "mission/command"), n.create_client(MissionCommand, "sim/control"), n.create_client(ExportSurvey, "mission/export")
checks = []


def spin(sec, cond=None):
    end = time.time() + sec
    while time.time() < end:
        rclpy.spin_once(n, timeout_sec=0.05)
        if cond and cond():
            return True
    return cond is None


def call(client, command, args=None, key=""):
    req = MissionCommand.Request(command=command, args_json=json.dumps(args or {}), operator_id="smoke", role="operator", idempotency_key=key)
    fut = client.call_async(req)
    rclpy.spin_until_future_complete(n, fut, timeout_sec=10)
    return fut.result()


def check(name, ok, **info):
    checks.append({"check": name, "ok": bool(ok), **info})
    print(("PASS " if ok else "FAIL ") + name, info)

try:
    check("services available", cmd.wait_for_service(timeout_sec=40) and simc.wait_for_service(timeout_sec=10))
    check("head bound and armed: gates published", spin(40, lambda: seen["gates"] > 20), gates=seen["gates"])
    r = call(cmd, "start")
    check("start refused before bring-up (prerequisites)", r is not None and not r.accepted, reason=r.reason if r else None)
    pose = json.loads(call(simc, "").result_json)["truth"]
    call(cmd, "register_datum", {"pose": pose})
    call(cmd, "preflight"); spin(1.0)
    call(simc, "rearm_button"); spin(1.0)
    call(cmd, "preflight"); spin(4.5)
    call(simc, "rearm_button"); spin(1.5)
    r = call(cmd, "arm")
    check("arm accepted after datum, REARM, brake test, REARM", r.accepted, result=r.result_json)
    r1, r2 = call(cmd, "start", key="smoke-start-1"), call(cmd, "start", key="smoke-start-1")
    check("start accepted; repeated idempotency key returns the same receipt", r1.accepted and r2.result_json == r1.result_json)
    check("mission SCAN", spin(10, lambda: seen["mission"] is not None and seen["mission"].state == "SCAN"),
          state=seen["mission"].state if seen["mission"] else None)
    spin(25)
    check("credited coverage grows", spin(15, lambda: seen["coverage"] is not None and seen["coverage"].valid_exposure_fraction > 0.01),
          fraction=seen["coverage"].valid_exposure_fraction if seen["coverage"] else None)
    check("eligible lane-gates received", seen["eligible"] > 200, eligible=seen["eligible"], gates=seen["gates"])
    check("coverage flagged not approved for field use", seen["coverage"] is not None and not seen["coverage"].field_use_approved)
    req = urllib.request.Request("http://127.0.0.1:8097/api/login", data=json.dumps({"user": "viewer", "password": "viewer"}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        cookie = resp.headers["Set-Cookie"].split(";")[0]
    st = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8097/api/state", headers={"Cookie": cookie}), timeout=5))
    check("web interface serves the live state", st["mission"]["state"] == "SCAN" and st["banner"], mission=st["mission"]["state"], hold=st["mission"].get("hold_reason"), loc=st["localization"],
          events=[(e.get("ev"), e.get("reason")) for e in st["events"][-8:]], head=st["head"], chassis=st["chassis"])
    call(cmd, "pause"); spin(2.0)
    fut = exp.call_async(ExportSurvey.Request(directory=""))
    rclpy.spin_until_future_complete(n, fut, timeout_sec=60)
    check("export service wrote the product set", fut.result() is not None and fut.result().success and "cells.csv" in fut.result().manifest_sha256_json)
finally:
    launch.terminate()
    try:
        launch.wait(10)
    except subprocess.TimeoutExpired:
        launch.kill()
    ev = {"scenario": "ros_smoke", "evidence_class": "simulated", "against": "native emulators" if NATIVE else "Python protocol fakes over TCP 5540/5550",
          "real_time": True, "deterministic": False, "checks": checks, "passed": bool(checks) and all(c["ok"] for c in checks)}
    (out / "evidence.json").write_text(json.dumps(ev, indent=1) + "\n")
    rclpy.try_shutdown()
sys.exit(0 if ev["passed"] else 1)
