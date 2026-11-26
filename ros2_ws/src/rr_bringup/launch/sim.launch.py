"""Simulation bring-up: simulator (world + emulators) and the robot node.

  ros2 launch rr_bringup sim.launch.py                      # Python fakes on tcp 5540/5550
  ros2 launch rr_bringup sim.launch.py native:=true         # native rr_head_sim / rr_chassis_sim already running
  ros2 launch rr_bringup sim.launch.py head_url:=serial:///dev/ttyUSB0?baud=1000000   # real head on the bench
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    cfg = PathJoinSubstitution([FindPackageShare("rr_bringup"), "config", "sim.yaml"])
    args = [DeclareLaunchArgument("head_url", default_value="tcp://127.0.0.1:5540"),
            DeclareLaunchArgument("chassis_url", default_value="tcp://127.0.0.1:5550"),
            DeclareLaunchArgument("config", default_value=cfg),
            DeclareLaunchArgument("native", default_value="false"),
            DeclareLaunchArgument("web_port", default_value="8080"),
            DeclareLaunchArgument("run_dir", default_value="")]
    sim = Node(package="rr_sim", executable="sim_node", name="rr_sim", output="screen",
               parameters=[{"config": LaunchConfiguration("config"),
                            "native": ParameterValue(LaunchConfiguration("native"), value_type=bool)}])
    robot = Node(package="rr_bringup", executable="robot_node", name="rr_robot", output="screen",
                 parameters=[{"head_url": LaunchConfiguration("head_url"), "chassis_url": LaunchConfiguration("chassis_url"),
                              "config": LaunchConfiguration("config"), "run_dir": LaunchConfiguration("run_dir"),
                              "web_port": ParameterValue(LaunchConfiguration("web_port"), value_type=int),
                              "registry_source": PythonExpression(["'head' if '", LaunchConfiguration("native"), "' == 'true' else 'demo'"])}])
    # the emulators must listen before the robot node provisions its (simulation-only) registry
    return LaunchDescription(args + [sim, TimerAction(period=1.5, actions=[robot])])
