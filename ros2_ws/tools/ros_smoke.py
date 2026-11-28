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
holds = []                      # every transition into HOLD with its reason (flaky-run diagnosis)


def on_mission(m):
    prev = seen["mission"]
    if m.state == "HOLD" and (prev is None or prev.state != "HOLD" or prev.hold_reason != m.hold_reason):
        holds.append({"t_wall": round(time.time() - T0, 2), "reason": m.hold_reason, "task": m.task, "phase": m.phase})
        print("HOLD", holds[-1], flush=True)
    seen.update(mission=m)


T0 = time.time()
n.create_subscription(MissionState, "mission/state", on_mission, latched)
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
    t_scan = time.time()
    spin(25)
    check("no HOLD during the first 25 s of the scan", not holds, holds=holds, state=seen["mission"].state if seen["mission"] else None,
          safety=None if seen["safety"] is None else {"traction_inhibited": seen["safety"].traction_inhibited,
                                                      "hw": list(seen["safety"].hw_inhibit_reasons), "sw": list(seen["safety"].protective_stop_reasons), "hold": list(seen["safety"].hold)})
    check("credited coverage grows", spin(15, lambda: seen["coverage"] is not None and seen["coverage"].valid_exposure_fraction > 0.01),
          fraction=seen["coverage"].valid_exposure_fraction if seen["coverage"] else None)
    check("eligible lane-gates received", seen["eligible"] > 200, eligible=seen["eligible"], gates=seen["gates"])
    check("coverage flagged not approved for field use", seen["coverage"] is not None and not seen["coverage"].field_use_approved)
    req = urllib.request.Request("http://127.0.0.1:8097/api/login", data=json.dumps({"user": "viewer", "password": "viewer"}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        cookie = resp.headers["Set-Cookie"].split(";")[0]
    st = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8097/api/state", headers={"Cookie": cookie}), timeout=5))
    check("web interface serves the live state", st["mission"]["state"] == "SCAN" and st["banner"], mission=st["mission"]["state"], hold=st["mission"].get("hold_reason"),
          events=[(e.get("ev"), e.get("reason"), e.get("step_ms"), e.get("lock_wait_ms")) for e in st["events"][-12:]])
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

# ---- IB-49: the stand-alone head-driver and chassis-bridge nodes against the Python fakes of sim_node (no robot_node)
if not NATIVE:
    from nav_msgs.msg import Odometry
    from rr_interfaces.msg import AttachmentManifest, ChassisState
    from rr_sim.harness import demo_registry
    for name in ("robot_node", "sim_node"):                    # the launch's children must be gone (ports 5540 / 5550)
        subprocess.run(["pkill", "-f", name], check=False)
    time.sleep(2.0)
    reg = Path("/tmp/rrhome/smoke_registry.json")
    reg.write_text(json.dumps(demo_registry()))
    time.sleep(2.0)
    procs = [subprocess.Popen(["ros2", "run", "rr_sim", "sim_node"], stdout=open(out / "standalone_sim.log", "w"), stderr=subprocess.STDOUT)]
    time.sleep(3.0)
    procs += [subprocess.Popen(["ros2", "run", "rr_head_driver", "head_driver_node", "--ros-args", "-p", f"registry:={reg}",
                                "-p", "mode:=COMMISSIONING", "-p", f"run_dir:=/tmp/rrhome/head_bench_{int(time.time())}"],
                               stdout=open(out / "standalone_head_driver.log", "w"), stderr=subprocess.STDOUT),
              subprocess.Popen(["ros2", "run", "rr_chassis_bridge", "chassis_bridge_node"],
                               stdout=open(out / "standalone_chassis_bridge.log", "w"), stderr=subprocess.STDOUT)]
    from rr_interfaces.msg import SessionEvent
    sa = {"gates": 0, "att": None, "odom": 0, "chassis": 0, "stamp_ok": None, "stamp": None, "events": []}

    def on_gate(m):
        sa["gates"] += 1
        if m.host_t0_us >= 0:
            st_us = m.header.stamp.sec * 1_000_000 + m.header.stamp.nanosec // 1000
            ok = abs(st_us - m.host_t0_us) <= 1
            sa["stamp_ok"] = ok if sa["stamp_ok"] is None else (sa["stamp_ok"] and ok)
            sa["stamp"] = (st_us, m.host_t0_us)
    n.create_subscription(SessionEvent, "head/events", lambda m: sa["events"].append((m.kind, m.reason)), 20)
    n.create_subscription(GateCounts, "head/gates", on_gate, 50)
    n.create_subscription(AttachmentManifest, "head/attachment", lambda m: sa.update(att=m), 5)
    n.create_subscription(Odometry, "odom", lambda m: sa.update(odom=sa["odom"] + 1), 20)
    n.create_subscription(ChassisState, "chassis/state", lambda m: sa.update(chassis=sa["chassis"] + 1), 5)
    ccmd = n.create_client(MissionCommand, "chassis/command")
    try:
        if ccmd.wait_for_service(timeout_sec=20):
            call(ccmd, "activate", {"on": True})         # the bridge drives (zeros) and reads odometry only when active
            call(ccmd, "head_power", {"electronics": True, "heater_enable": False})   # the fake head is powered by the chassis
        spin(40, lambda: sa["gates"] > 20 and sa["odom"] > 20 and sa["chassis"] > 2)
        check("stand-alone head_driver_node: binds (strict calibration binding) and publishes gates stamped with the gate start",
              sa["gates"] > 20 and sa["att"] is not None and sa["stamp_ok"] is True, gates=sa["gates"],
              attachment=None if sa["att"] is None else sa["att"].head_id, stamp_ok=sa["stamp_ok"], stamp=sa["stamp"], events=sa["events"][-6:])
        check("stand-alone chassis_bridge_node: publishes odom and chassis state", sa["odom"] > 20 and sa["chassis"] > 2,
              odom=sa["odom"], chassis=sa["chassis"])
    finally:
        for p_ in procs:
            p_.terminate()
        for p_ in procs:
            try:
                p_.wait(10)
            except subprocess.TimeoutExpired:
                p_.kill()
    ev = {"scenario": "ros_smoke", "evidence_class": "simulated", "against": "native emulators" if NATIVE else "Python protocol fakes over TCP 5540/5550",
          "real_time": True, "deterministic": False, "checks": checks, "holds": holds, "passed": bool(checks) and all(c["ok"] for c in checks)}
    (out / "evidence.json").write_text(json.dumps(ev, indent=1) + "\n")
    with open(out / "runs.ndjson", "a") as f:      # history of every run (pass and fail), newest last
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "passed": ev["passed"], "holds": holds,
                            "failed": [c for c in checks if not c["ok"]]}) + "\n")
    rclpy.try_shutdown()
sys.exit(0 if ev["passed"] else 1)
