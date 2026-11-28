"""Stand-alone head driver node (bench use and driver tests): head ICD 2.0 link master on
a transport URL, raw stream archived, gates published with the host attachment id.

  ros2 run rr_head_driver head_driver_node --ros-args -p url:=tcp://127.0.0.1:5540 \
      -p registry:=/path/registry.json -p mode:=BENCH -p run_dir:=/tmp/rr_runs/bench1

In the robot (rr_bringup robot_node) the same HeadLinkMaster runs inside the RobotApp.
"""
import json
import threading
import time

import rclpy
from rclpy.node import Node

from rr_core.archive import Archive
from rr_core.head_link import HeadLinkConfig, HeadLinkMaster
from rr_core.profiles import DATA, Calibration, CalibrationStore
from rr_core.transport import Clock, open_transport
from rr_interfaces.msg import AttachmentManifest, GateCounts, LaneCounts, SessionEvent


class HeadDriverNode(Node):
    def __init__(self):
        super().__init__("rr_head_driver")
        url = self.declare_parameter("url", "tcp://127.0.0.1:5540").value
        registry = json.load(open(self.declare_parameter("registry", "").value))
        mode = self.declare_parameter("mode", "BENCH").value
        run_dir = self.declare_parameter("run_dir", "/tmp/rr_runs/head_bench").value
        cfg = HeadLinkConfig(mode=mode, byte_time_us=0.0 if url.startswith("tcp") else 10.0)
        self.archive = Archive(run_dir)
        self.lock = threading.Lock()
        # review m8: calibrations from files (default: the synthetic demonstration record), strict identity binding unless
        # calibration_binding = DEMONSTRATION; a run.json describes the archive (head bench; no survey configuration)
        paths = self.declare_parameter("calibrations", [str(DATA / "demo_calibration.json")]).value
        binding = self.declare_parameter("calibration_binding", "STRICT").value
        cals = [Calibration.load(p) for p in paths]
        store = CalibrationStore(cals, demonstration=binding == "DEMONSTRATION")
        self.archive.write_run_manifest({"kind": "head_bench", "link_config": {"mode": mode, "url": url},
                                         "calibration_records": [c.record for c in cals], "calibration_binding": binding,
                                         "note": "head bench archive: raw head stream only; not a survey run (build_from_run needs a survey configuration)"})
        self.master = HeadLinkMaster(open_transport(url), Clock(), registry, cfg, resolve_calibration=store.resolve,
                                     sink=lambda e: self.archive.append(e, sync=e[1] == "C"))
        self.pub_gate = self.create_publisher(GateCounts, "head/gates", 50)
        self.pub_att = self.create_publisher(AttachmentManifest, "head/attachment", 1)
        self.pub_ev = self.create_publisher(SessionEvent, "head/events", 20)
        self.create_timer(0.02, self.publish)
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while rclpy.ok():
            with self.lock:
                self.master.step()
            time.sleep(0.0005)

    def publish(self):
        with self.lock:
            events = self.master.drain_events()
        now = self.get_clock().now().to_msg()
        for ev in events:
            kind = ev["ev"]
            if kind == "gate":
                g = ev["gate"]
                msg = GateCounts(attachment_session_id=g["attachment"], sequence=g["sequence"], start_us=g["start_us"],
                                 span_us=g["span_us"], fit_id=str(g["fit_id"] or ""), sync_state=g["sync"]["state"],
                                 flags=g["flags"], host_t0_us=int(g["t0_us"]) if g["t0_us"] is not None else -1,
                                 host_t1_us=int(g["t1_us"]) if g["t1_us"] is not None else -1,
                                 time_bound_us=float(g["bound_us"]) if g["bound_us"] is not None else -1.0,
                                 head_c=float(g["thermal"]["head_c"]) if g["thermal"]["head_c"] is not None else float("nan"))
                # review m8: the stamp is the GATE START on the host CLOCK_MONOTONIC (fit-mapped), not publication time
                if g["t0_us"] is not None:
                    msg.header.stamp.sec, msg.header.stamp.nanosec = int(g["t0_us"] // 1_000_000), int((g["t0_us"] % 1_000_000) * 1000)
                for i, ln in enumerate(g["lanes"]):
                    lc = LaneCounts(lane=ln["id"], flags=ln["flags"], eligible=not ln["reasons"], reasons=ln["reasons"])
                    if ln["alpha"]:
                        lc.has_alpha, lc.alpha_counts, lc.floor_live_us = True, ln["alpha"][0], ln["alpha"][1]
                    if ln["beta"]:
                        lc.has_beta, lc.beta_counts, lc.floor_live_us = True, ln["beta"][0], ln["beta"][1]
                    if ln["ref"]:
                        lc.has_ref, lc.ref_counts, lc.ref_live_us = True, ln["ref"][0], ln["ref"][1]
                    msg.lanes[i] = lc
                self.pub_gate.publish(msg)
            elif kind == "session_open":
                m = ev["manifest"]
                a = AttachmentManifest(manifest_json=json.dumps({k: v for k, v in m.items() if k != "descriptor_b64"}))
                for k in ("attachment_session_id", "head_id", "head_type", "boot_id", "firmware", "setup_id", "descriptor_id",
                          "descriptor_sha256", "geometry_id", "mode"):
                    setattr(a, k, str(m.get(k) or ""))
                a.header.stamp = now
                self.pub_att.publish(a)
            if kind in ("session_open", "session_close", "blocked", "gap", "fault", "link_down"):
                e = SessionEvent(kind=kind, attachment_session_id=str(ev.get("attachment") or ""), reason=str(ev.get("reason") or ev.get("fault") or ev.get("kind") or ""),
                                 last_seq=int(ev["last_seq"]) if ev.get("last_seq") is not None else -1,
                                 detail_json=json.dumps({k: v for k, v in ev.items() if k not in ("manifest", "gate")}, default=str))
                e.header.stamp = now
                self.pub_ev.publish(e)


def main():
    rclpy.init()
    node = HeadDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.archive.close()
        rclpy.try_shutdown()
