"""ROS 2 node hosting the RobotApp (head driver, chassis bridge, localisation, mapping,
coverage supervisor, guidance and the operator web service in one process).

Subscribes   scan (sensor_msgs/LaserScan)          - simulator or a real LiDAR driver
Publishes    head/gates, head/attachment, head/events, chassis/state, safety/state,
             localization/status, localization/pose, coverage/status, mission/state,
             mission/flags, tf map->base_link
Services     mission/command (rr_interfaces/MissionCommand), mission/export
Action       guided_visit (rr_interfaces/GuidedVisit)

Startup ordering: nothing here can command motion until the mission prerequisites hold
(recorder, head identity/calibration, clock fits, registered datum, chassis armed) - see
rr_coverage.supervisor.Mission.prerequisites.  The chassis bridge starts inactive.
"""
import json
import math
import time
from pathlib import Path

import rclpy
import yaml
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped
from rclpy.action import ActionServer
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from tf2_ros import TransformBroadcaster

from rr_interfaces.action import GuidedVisit
from rr_interfaces.msg import (AttachmentManifest, ChassisState, CoverageStatus, Flag, FlagArray, GateCounts,
                               LaneCounts, LocalizationStatus, MissionState, SafetyState, SessionEvent)
from rr_interfaces.srv import ExportSurvey, MissionCommand

from .geometry_config import CONFIG
from .runtime import Runtime, demo_registry, load_registry, load_users, provision_registry_from_head


class RobotNode(Node):
    def __init__(self):
        super().__init__("rr_robot")
        p = self.declare_parameter
        head_url = p("head_url", "tcp://127.0.0.1:5540").value            # serial:///dev/ttyUSB0?baud=1000000 on hardware
        chassis_url = p("chassis_url", "tcp://127.0.0.1:5550").value      # serial:///dev/ttyACM0 on hardware
        run_dir = p("run_dir", "").value or f"/tmp/rr_runs/run-{time.strftime('%Y%m%d-%H%M%S')}"
        config_path = p("config", str(CONFIG / "sim.yaml")).value
        registry_path = p("registry", "").value
        source = p("registry_source", "file").value                        # file | demo | head (demo/head: simulation or lab only)
        web_port = p("web_port", 8080).value
        users = p("users", "").value
        resume = p("resume", False).value
        cfg = yaml.safe_load(Path(config_path).read_text())
        if registry_path:
            registry = load_registry(registry_path)
        elif source == "demo":
            self.get_logger().warn("demo registry for the packaged synthetic head descriptor: SIMULATION ONLY")
            registry = demo_registry()
        elif source == "head":
            self.get_logger().warn("registry provisioned from the attached head/emulator: SIMULATION/LAB ONLY")
            registry = provision_registry_from_head(head_url)
        else:
            raise RuntimeError("a trusted head registry file is required (parameter 'registry')")
        self.rt = Runtime(head_url, chassis_url, run_dir, cfg, registry, load_users(users or None), web_port, resume=resume)
        self.app = self.rt.app
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.pub_gate = self.create_publisher(GateCounts, "head/gates", 50)
        self.pub_att = self.create_publisher(AttachmentManifest, "head/attachment", latched)
        self.pub_ev = self.create_publisher(SessionEvent, "head/events", 20)
        self.pub_ch = self.create_publisher(ChassisState, "chassis/state", 5)
        self.pub_sf = self.create_publisher(SafetyState, "safety/state", 5)
        self.pub_loc = self.create_publisher(LocalizationStatus, "localization/status", 5)
        self.pub_pose = self.create_publisher(PoseWithCovarianceStamped, "localization/pose", 5)
        self.pub_cov = self.create_publisher(CoverageStatus, "coverage/status", latched)
        self.pub_ms = self.create_publisher(MissionState, "mission/state", latched)
        self.pub_flags = self.create_publisher(FlagArray, "mission/flags", latched)
        self.tf = TransformBroadcaster(self)
        self.create_subscription(LaserScan, "scan", self.on_scan, 5)
        self.create_service(MissionCommand, "mission/command", self.on_command)
        self.create_service(ExportSurvey, "mission/export", self.on_export)
        self.action = ActionServer(self, GuidedVisit, "guided_visit", self.on_guided)
        self._gates_seen = 0
        self._sessions_seen = 0
        self._receipts = {}
        self.create_timer(0.1, self.publish_fast)
        self.create_timer(1.0, self.publish_slow)
        self.rt.start(web=True)
        self.get_logger().info(f"RobotApp running: head {head_url}, chassis {chassis_url}, run {run_dir}, UI http://<robot>:{web_port}/")

    # ------------------------------------------------------------------ inputs
    def on_scan(self, msg: LaserScan):
        import numpy as np
        angles = msg.angle_min + np.arange(len(msg.ranges)) * msg.angle_increment
        with self.rt.lock:
            self.app.on_scan(self.rt.clock.now_us(), angles, np.asarray(msg.ranges, dtype=float))

    def on_command(self, req, resp):
        key = req.idempotency_key
        if key and key in self._receipts:
            out = self._receipts[key]
        else:
            with self.rt.lock:
                out = self.app.command(req.command, json.loads(req.args_json or "{}"), req.operator_id or "ros", req.role or "operator")
            if key:
                self._receipts[key] = out
        resp.accepted, resp.reason, resp.result_json = bool(out.get("accepted")), str(out.get("reason") or ""), json.dumps(out, default=str)
        return resp

    def on_export(self, req, resp):
        with self.rt.lock:
            out = self.app.export(req.directory or (self.app.run_dir / "export"))
        resp.success, resp.directory = True, out["dir"]
        resp.manifest_sha256_json = json.dumps({k: v["sha256"] for k, v in out["files"].items()})
        return resp

    def on_guided(self, goal_handle):
        g = goal_handle.request
        with self.rt.lock:
            out = self.app.command(g.command, {"flag": g.flag_id} if g.flag_id else {}, g.operator_id or "ros", "operator")
        res = GuidedVisit.Result()
        if not out.get("accepted"):
            goal_handle.abort()
            res.success, res.status, res.detail = False, "REJECTED", str(out.get("reason"))
            return res
        while rclpy.ok():
            with self.rt.lock:
                gd = self.app.guidance
                busy = gd.move is not None or gd.count is not None
                fid = out.get("flag") or gd.current
                st = gd.status.get(fid, {}) if fid else {}
            if not busy:
                break
            goal_handle.publish_feedback(GuidedVisit.Feedback(state=str(self.app.mover.state)))
            time.sleep(0.2)
        res.status = "PARKED" if g.command == "park" and self.app.guidance.parked else str(st.get("status", ""))
        res.success = res.status in ("AT_SPOT", "EXPOSED", "PARKED")
        visits = st.get("visits") or []
        res.error_m = float(visits[-1]["error_m"]) if visits else float("nan")
        res.detail = "; ".join(st.get("notes", [])[-2:])
        goal_handle.succeed() if res.success else goal_handle.abort()
        return res

    # ----------------------------------------------------------------- outputs
    def publish_fast(self):
        now = self.get_clock().now().to_msg()
        with self.rt.lock:
            new_gates, self.app.gate_feed = self.app.gate_feed, []
            sessions = self.app.pipeline.sessions[self._sessions_seen:]
            self._sessions_seen = len(self.app.pipeline.sessions)
            snap = self.app.snapshot()
            P = self.app.loc.P.copy()
        for m in sessions:
            a = AttachmentManifest()
            a.header.stamp = now
            for k in ("attachment_session_id", "head_id", "head_type", "boot_id", "firmware", "setup_id", "descriptor_id",
                      "descriptor_sha256", "geometry_id", "mode"):
                setattr(a, k, str(m.get(k) or ""))
            a.geometry_basis, a.calibration_id = str(m.get("geometry_basis") or ""), str(m.get("calibration_id") or "")
            a.field_use_approved = bool((m.get("calibration") or {}).get("field_use_approved", False))
            a.manifest_json = json.dumps({k: v for k, v in m.items() if k != "descriptor_b64"})
            self.pub_att.publish(a)
            self.pub_ev.publish(SessionEvent(kind="session_open", attachment_session_id=a.attachment_session_id))
        for g in new_gates:
            msg = GateCounts(attachment_session_id=g["attachment"], sequence=int(g["sequence"]), start_us=int(g["start_us"]),
                             span_us=int(g["span_us"]), fit_id=str(g["fit_id"] or ""), sync_state=g["sync"]["state"], flags=g["flags"])
            msg.header.stamp, msg.header.frame_id = now, "head_mount"
            msg.host_t0_us = int(g["t0_us"]) if g["t0_us"] is not None else -1
            msg.host_t1_us = int(g["t1_us"]) if g["t1_us"] is not None else -1
            msg.time_bound_us = float(g["bound_us"]) if g["bound_us"] is not None else -1.0
            msg.head_c = float(g["thermal"]["head_c"]) if g["thermal"]["head_c"] is not None else float("nan")
            for i, ln in enumerate(g["lanes"]):
                lc = LaneCounts(lane=ln["id"], flags=ln["flags"], eligible=not ln["reasons"], reasons=[str(r) for r in ln["reasons"]])
                if ln["alpha"]:
                    lc.has_alpha, lc.alpha_counts, lc.floor_live_us = True, int(ln["alpha"][0]), int(ln["alpha"][1])
                if ln["beta"]:
                    lc.has_beta, lc.beta_counts, lc.floor_live_us = True, int(ln["beta"][0]), int(ln["beta"][1])
                if ln["ref"]:
                    lc.has_ref, lc.ref_counts, lc.ref_live_us = True, int(ln["ref"][0]), int(ln["ref"][1])
                msg.lanes[i] = lc
            self.pub_gate.publish(msg)
        ch, sf, loc = snap["chassis"], snap["safety"], snap["localization"]
        c = ChassisState(link_state=str(ch["link"]), mode=str(ch["mode"]), op_mode=str(ch["op_mode"]), motion=str(ch["motion"]),
                         drive_accepted=bool(ch["accepted"]), reject_reason=str(ch["reject_reason"] or ""),
                         is_stationary=bool((ch["stationary"] or {}).get("is_stationary", False)),
                         head_presence=str(ch["head_presence"] or ""), time_bound_us=float(ch["time_bound_us"] or -1.0))
        c.header.stamp = now
        if ch["applied"]:
            c.applied_v_mps, c.applied_w_radps = float(ch["applied"]["v_mps"]), float(ch["applied"]["w_radps"])
        self.pub_ch.publish(c)
        s = SafetyState(hw_latch=bool(sf["hw_latch"]), traction_inhibited=bool(sf["traction_inhibited"]),
                        charge_service=bool(sf["charge_service"]), hw_inhibit_reasons=sf["hw_inhibit_reasons"],
                        protective_stop_reasons=sf["protective_stop_reasons"], hold=sf["hold"],
                        chain_open=[k for k, v in (sf["chain"] or {}).items() if not v], rearm_ready=bool(sf["rearm_ready"]))
        s.header.stamp = now
        self.pub_sf.publish(s)
        ls = LocalizationStatus(initialized=loc["pose"] is not None, credit=bool(loc["credit"]), slip=bool(loc["slip"]),
                                hold_request=bool(loc["hold_request"]), head_uncertainty_2s_m=float(loc["uncertainty_2s_m"]),
                                sigma=[float(v) for v in loc["sigma"]], epoch=int(self.app.pipeline.traj.epoch))
        ls.header.stamp = now
        self.pub_loc.publish(ls)
        if loc["pose"] is not None:
            x, y, yaw = loc["pose"]
            pose = PoseWithCovarianceStamped()
            pose.header.stamp, pose.header.frame_id = now, "map"
            pose.pose.pose.position.x, pose.pose.pose.position.y = float(x), float(y)
            pose.pose.pose.orientation.z, pose.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            cov = [0.0] * 36
            cov[0], cov[7], cov[35] = float(P[0, 0]), float(P[1, 1]), float(P[2, 2])
            pose.pose.covariance = cov
            self.pub_pose.publish(pose)
            t = TransformStamped()
            t.header.stamp, t.header.frame_id, t.child_frame_id = now, "map", "base_link"
            t.transform.translation.x, t.transform.translation.y = float(x), float(y)
            t.transform.rotation.z, t.transform.rotation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            self.tf.sendTransform(t)

    def publish_slow(self):
        now = self.get_clock().now().to_msg()
        with self.rt.lock:
            snap = self.app.snapshot()
            proc = self.app.pipeline.proc
            summ = proc.coverage_summary()          # no evaluation inside (provisional values of the last journaled evaluate)
            flags = [dict(f) for f in proc.flags]
        m = snap["mission"]
        ms = MissionState(state=str(m["state"]), hold_reason=str(m.get("hold_reason") or ""), phase=str(m.get("phase") or ""),
                          method=str(m.get("method") or ""), task=str(m.get("task") or ""), tasks_done=int(m.get("tasks_done") or 0),
                          tasks_total=int(m.get("tasks_total") or 0), prerequisites_missing=[str(x) for x in m.get("prerequisites_missing", [])],
                          control_holder=str((self.rt.cc.lease_state() or {}).get("user", "")), detail_json=json.dumps(m, default=str))
        ms.header.stamp = now
        self.pub_ms.publish(ms)
        if summ:
            a = summ["areas_m2"]
            cs = CoverageStatus(target_area_m2=summ["target_area_m2"], acceptable_m2=a["ACCEPTABLE"],
                                insufficient_sensitivity_m2=a["INSUFFICIENT_SENSITIVITY"], invalid_data_m2=a["INVALID_DATA"],
                                blocked_m2=a["BLOCKED"], unvisited_m2=a["UNVISITED"], excluded_m2=a["EXCLUDED"],
                                valid_exposure_fraction=summ["valid_exposure_fraction"], field_use_approved=bool(snap["field_use_approved"]))
            cs.header.stamp = now
            self.pub_cov.publish(cs)
        fa = FlagArray()
        fa.header.stamp, fa.header.frame_id = now, "map"
        for f in flags:
            if f.get("x_m") is None:
                continue
            fa.flags.append(Flag(id=f["id"], kind=f["kind"], activity_class=f["class"], status=f["status"], x_m=float(f["x_m"]),
                                 y_m=float(f["y_m"]), heading_rad=float(f["heading_rad"]),
                                 distance_from_door_m=float(f["location"]["distance_from_door_m"]), wall=f["location"]["wall"],
                                 distance_from_wall_m=float(f["location"]["distance_from_wall_m"]),
                                 source_lane=int(f["source_lane"] if f["source_lane"] is not None else -1),
                                 activity_bq_cm2=float(f["D"]), u_total_bq_cm2=float(f["u_total"]),
                                 decision_threshold_bq_cm2=float(f["D_star"]),
                                 detection_limit_bq_cm2=float(f["D_hash"]) if math.isfinite(f["D_hash"]) else -1.0,
                                 position_uncertainty_m=float(f["position_uncertainty_m"]),
                                 attachment_session_id=str(f.get("attachment") or "")))
        self.pub_flags.publish(fa)


def main():
    rclpy.init()
    node = RobotNode()
    try:
        from rclpy.executors import MultiThreadedExecutor
        ex = MultiThreadedExecutor(num_threads=3)
        ex.add_node(node)
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.rt.stop()
        rclpy.try_shutdown()
