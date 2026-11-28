#!/usr/bin/env bash
# Run the simulator and the operator interface.
#
#   tools/run_sim.sh                 # stand-alone deterministic simulator + UI on http://127.0.0.1:8080/
#   tools/run_sim.sh --auto --method STEP_AND_COUNT --port 8081
#   tools/run_sim.sh ros [launch args]   # ROS 2 graph: rr_sim sim_node + rr_bringup robot_node (needs tools/build.sh)
#   tools/run_sim.sh ros native:=true    # against rr_head_sim / rr_chassis_sim already listening on 5540 / 5550
#
# Demo accounts (synthetic data only): viewer/viewer, operator/operator, operator2/operator2, rp/rp.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
rr_require_image
if [ "${1:-}" = "ros" ]; then
  shift
  rr_docker_run -- ros2 launch rr_bringup sim.launch.py "$@"
else
  PP="$(ls -d "$RR_WS"/src/*/ | tr '\n' ':')"
  rr_docker_run -e PYTHONPATH="$PP" -- python3 -m rr_sim.sim_server "$@"
fi
