"""Hardware bring-up: the robot node on real transports. A LiDAR driver publishing
sensor_msgs/LaserScan on `scan` (frame lidar_link) is started separately.

  ros2 launch rr_bringup hardware.launch.py registry:=/etc/rad-roomba/head_registry.json \
      head_url:=serial:///dev/ttyUSB0?baud=1000000 chassis_url:=serial:///dev/ttyACM0
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    cfg = PathJoinSubstitution([FindPackageShare("rr_bringup"), "config", "hardware.yaml"])
    args = [DeclareLaunchArgument("head_url", default_value="serial:///dev/ttyUSB0?baud=1000000"),
            DeclareLaunchArgument("chassis_url", default_value="serial:///dev/ttyACM0"),
            DeclareLaunchArgument("config", default_value=cfg),
            DeclareLaunchArgument("registry"),                      # trusted head registry: required, no default
            DeclareLaunchArgument("users", default_value=""),
            DeclareLaunchArgument("run_dir", default_value=""),
            DeclareLaunchArgument("resume", default_value="false"),
            DeclareLaunchArgument("web_port", default_value="8080")]
    robot = Node(package="rr_bringup", executable="robot_node", name="rr_robot", output="screen",
                 parameters=[{"head_url": LaunchConfiguration("head_url"), "chassis_url": LaunchConfiguration("chassis_url"),
                              "config": LaunchConfiguration("config"), "registry": LaunchConfiguration("registry"),
                              "users": LaunchConfiguration("users"), "run_dir": LaunchConfiguration("run_dir"),
                              "resume": ParameterValue(LaunchConfiguration("resume"), value_type=bool),
                              "web_port": ParameterValue(LaunchConfiguration("web_port"), value_type=int),
                              "registry_source": "file"}])
    return LaunchDescription(args + [robot])
