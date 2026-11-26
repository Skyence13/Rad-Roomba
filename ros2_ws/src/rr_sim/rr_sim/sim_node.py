"""ROS 2 simulator node: kinematic trailer world + Python protocol fakes served on the
emulator TCP ports (head 5540, chassis 5550), LaserScan on `scan`, ground truth on
`sim/truth`, and `sim/control` (MissionCommand) for the local controls and the scene.
With `native: true` the fakes are not started and the world talks to the native firmware
emulators through their UDP sockets (rr_sim.native)."""
import json
import math
import threading
import time

import rclpy
import yaml
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

from rr_interfaces.srv import MissionCommand
from rr_bringup.geometry_config import CONFIG, load_robot_geometry
from rr_core.geometry import RobotOutline, lane_polygons
from rr_core.profiles import DATA, Calibration
from rr_core.transport import Clock, TcpListenTransport
from rr_sim.world import World


class SimNode(Node):
    def __init__(self):
        super().__init__("rr_sim")
        cfg = yaml.safe_load(open(self.declare_parameter("config", str(CONFIG / "sim.yaml")).value))
        self.native = self.declare_parameter("native", False).value
        seed = self.declare_parameter("seed", 1).value
        start = self.declare_parameter("start_pose", [0.6, 0.0, 0.0]).value
        geo = load_robot_geometry()
        self.outline = RobotOutline(**geo["outline"])
        self.clock = Clock()
        tr = cfg["trailer"]
        desc = (DATA / "head_descriptor_demo.json").read_bytes()
        cal = Calibration.load(DATA / "demo_calibration.json")
        self.world = World(tr["length_m"], tr["width_m"], cal, lane_polygons(json.loads(desc), geo["mount_transform"]), seed=seed,
                           door_closed=tr["door_closed"], lidar_xy=tuple(geo["lidar"]["xy"]))
        if self.native:
            from rr_sim.native import NativeChassis, NativeHead
            self.head, self.chassis = NativeHead(), NativeChassis()
            self.chassis.env("pose", list(start))
        else:
            from rr_core.fakes.chassis import FakeChassis
            from rr_core.fakes.head import FakeHead
            self.head = FakeHead(self.clock, TcpListenTransport("127.0.0.1", 5540), desc, seed=seed)
            self.chassis = FakeChassis(self.clock, TcpListenTransport("127.0.0.1", 5550), seed=seed, pose=tuple(start))
        self.lock = threading.Lock()
        self.pub_scan = self.create_publisher(LaserScan, "scan", 5)
        self.pub_truth = self.create_publisher(PoseStamped, "sim/truth", 5)
        self.create_service(MissionCommand, "sim/control", self.on_control)
        self.create_timer(0.1, self.publish_scan)
        threading.Thread(target=self.loop, daemon=True).start()

    def truth(self):
        t = self.chassis.truth()
        return (t["x"], t["y"], t["yaw"])

    def loop(self):
        n = 0
        while rclpy.ok():
            with self.lock:
                n += 1
                if not self.native:
                    self.head.step()
                    self.chassis.step()
                    if n % 10 == 0:
                        self.head.power(bool(self.chassis.head_power["electronics"]))
                if n % 10 == 0:
                    pose = self.truth()
                    self.head.set_rates(self.world.rates(pose))
                    self.chassis.env("rear_blocked", self.world.rear_blocked(pose, self.outline)) if not self.native else None
            time.sleep(0.001)

    def publish_scan(self):
        with self.lock:
            pose = self.truth()
            angles, ranges = self.world.scan(pose)
        msg = LaserScan()
        msg.header.stamp, msg.header.frame_id = self.get_clock().now().to_msg(), "lidar_link"
        msg.angle_min, msg.angle_max = float(angles[0]), float(angles[-1])
        msg.angle_increment = float(angles[1] - angles[0])
        msg.range_min, msg.range_max = 0.05, float(self.world.range_max)
        msg.ranges = [float(r) for r in ranges]
        self.pub_scan.publish(msg)
        p = PoseStamped()
        p.header.stamp, p.header.frame_id = msg.header.stamp, "map"
        p.pose.position.x, p.pose.position.y = float(pose[0]), float(pose[1])
        p.pose.orientation.z, p.pose.orientation.w = math.sin(pose[2] / 2), math.cos(pose[2] / 2)
        self.pub_truth.publish(p)

    def on_control(self, req, resp):
        args = json.loads(req.args_json or "{}")
        with self.lock:
            resp.accepted, resp.reason = True, ""
            resp.result_json = json.dumps(sim_action(self.world, self.chassis, self.head, dict(args, action=req.command), self.truth()))
        return resp


def sim_action(world, chassis, head, body, truth):
    """Local controls and scene changes shared by the ROS node and the stand-alone sim server."""
    a = body.get("action")
    if a == "rearm_button":
        chassis.press("REARM")
    elif a == "pause_button":
        chassis.press("PAUSE")
    elif a in ("estop_on", "estop_off"):
        chassis.env("estop", a == "estop_on")
    elif a in ("charger_on", "charger_off"):
        chassis.env("chg_plug", a == "charger_on")
    elif a == "person_path":
        world.person(truth[0] + math.cos(truth[2]) * 0.55, truth[1] + math.sin(truth[2]) * 0.55, 0.2)
    elif a == "person_clear":
        world.set_box("person", None)
    elif a == "head_reset":
        head.reset()
    elif a == "pose":
        chassis.env("pose", body["pose"])
    elif a == "patch":
        world.add_patch(*body["rect"], body.get("d_beta", 2.4))
    elif a:
        return {"ok": False, "reason": "unknown action"}
    return {"ok": True, "truth": list(truth)}


def main():
    rclpy.init()
    node = SimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()
