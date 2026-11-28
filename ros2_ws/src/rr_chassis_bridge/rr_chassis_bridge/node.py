"""Stand-alone chassis bridge node: RR-CHS 1.0 host side on a transport URL.

Cyclic DRIVE at 50 Hz with a TTL; the newest `cmd_drive` only (expires after 150 ms, never
queued); starts INACTIVE (zeros) until `chassis/command activate`; odometry from encoder
ticks with the radii/track reported by the chassis (HELLO caps / calibration), stamped at
the encoder sample through the clock fit; IMU; state, safety state and events.

  ros2 run rr_chassis_bridge chassis_bridge_node --ros-args -p url:=tcp://127.0.0.1:5550
  ros2 service call /chassis/command rr_interfaces/srv/MissionCommand "{command: rearm_sw, operator_id: a.tech}"
"""
import json
import math
import threading
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu

from rr_core.chassis_link import ChassisLink
from rr_core.transport import Clock, open_transport
from rr_interfaces.msg import ChassisState, DriveCommand, SafetyState
from rr_interfaces.srv import MissionCommand


class ChassisBridgeNode(Node):
    def __init__(self):
        super().__init__("rr_chassis_bridge")
        url = self.declare_parameter("url", "tcp://127.0.0.1:5550").value
        self.link = ChassisLink(open_transport(url), Clock())
        self.lock = threading.Lock()
        self.x = self.y = self.yaw = 0.0
        self.pub_odom = self.create_publisher(Odometry, "odom", 20)
        self.pub_imu = self.create_publisher(Imu, "imu", 20)
        self.pub_state = self.create_publisher(ChassisState, "chassis/state", 5)
        self.pub_safety = self.create_publisher(SafetyState, "safety/state", 5)
        self.create_subscription(DriveCommand, "cmd_drive", self.on_cmd, 1)
        self.create_service(MissionCommand, "chassis/command", self.on_command)
        self.create_timer(0.02, self.publish)
        self.create_timer(0.25, self.publish_state)
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while rclpy.ok():
            with self.lock:
                self.link.step()
            time.sleep(0.0005)

    def on_cmd(self, msg):
        with self.lock:
            self.link.set_command(msg.v_mps, msg.w_radps, msg.source or "ros")     # replaces, never queues

    def on_command(self, req, resp):
        args = json.loads(req.args_json or "{}")
        with self.lock:
            c = req.command
            if c == "activate":
                self.link.activate(bool(args.get("on", True)))
            elif c == "rearm_sw":
                self.link.rearm_sw(req.operator_id or "operator")
            elif c == "stop":
                self.link.stop(args.get("kind", "PROTECTIVE"), args.get("reason", "HOST_REQUEST"))
            elif c in ("set_op_mode", "head_power", "brake_test", "panel", "config_set", "config_get"):
                self.link.request(c.upper(), args)
            else:
                resp.accepted, resp.reason = False, "UNKNOWN_COMMAND"
                return resp
        resp.accepted = True
        return resp

    def publish(self):
        with self.lock:
            samples = list(self.link.samples)
            self.link.samples.clear()
            caps = (self.link.hello or {}).get("caps", {})
        k = 2 * math.pi * caps.get("wheel_radius_nom_m", 0.052) / caps.get("encoder_cpr", 9600)
        track = caps.get("track_nom_m", 0.27)
        for s in samples:
            dl, dr = s["d_left_ticks"] * k, s["d_right_ticks"] * k
            dth = (dr - dl) / track
            self.x += 0.5 * (dl + dr) * math.cos(self.yaw + 0.5 * dth)
            self.y += 0.5 * (dl + dr) * math.sin(self.yaw + 0.5 * dth)
            self.yaw += dth
            stamp = self.get_clock().now().to_msg()      # host receive time; s["t_us"] is the fitted sample time (monotonic)
            o = Odometry()
            o.header.stamp, o.header.frame_id, o.child_frame_id = stamp, "odom", "base_link"
            o.pose.pose.position.x, o.pose.pose.position.y = self.x, self.y
            o.pose.pose.orientation.z, o.pose.pose.orientation.w = math.sin(self.yaw / 2), math.cos(self.yaw / 2)
            self.pub_odom.publish(o)
            i = Imu()
            i.header.stamp, i.header.frame_id = stamp, "imu_link"
            i.angular_velocity.z = float(s["gyro_z"])
            self.pub_imu.publish(i)

    def publish_state(self):
        with self.lock:
            d, st = dict(self.link.drive), dict(self.link.state)
            bound = self.link.time_bound_us()
        now = self.get_clock().now().to_msg()
        mode = d.get("mode") or st.get("mode") or ""
        c = ChassisState(link_state=self.link.link_state, mode=mode, op_mode=self.link.op_mode, motion=str(d.get("motion") or ""),
                         drive_accepted=bool(d.get("accepted")), reject_reason=str(d.get("reject_reason") or ""),
                         is_stationary=bool((d.get("stationary") or {}).get("is_stationary", False)),
                         head_presence=str(st.get("head_presence") or ""), j2_present=bool(st.get("j2_present", False)),
                         time_bound_us=bound if math.isfinite(bound) else -1.0, boot_id=str(self.link.boot_id or ""))
        c.header.stamp = now
        self.pub_state.publish(c)
        stops = d.get("stops", {})
        s = SafetyState(hw_latch=bool(st.get("hw_latch", False)), traction_inhibited=mode not in ("ARMED_IDLE", "MOVING"),
                        charge_service=mode == "SERVICE_CHARGE", hw_inhibit_reasons=stops.get("hw", []),
                        protective_stop_reasons=stops.get("sw", []), hold=d.get("hold", []),
                        chain_open=[k for k, v in (st.get("chain") or {}).items() if not v], rearm_ready=bool(st.get("rearm_ready", False)))
        s.header.stamp = now
        self.pub_safety.publish(s)


def main():
    rclpy.init()
    node = ChassisBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()
