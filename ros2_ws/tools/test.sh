#!/usr/bin/env bash
# Run the tests inside the container.
#
#   tools/test.sh                 # unit tests of every package (pytest on the sources)
#   tools/test.sh unit [pytest args...]
#   tools/test.sh scenarios [pytest args...]   # end-to-end scenarios (evidence/ is rewritten)
#   tools/test.sh native [n01|n02]       # scenarios 1 and 2 against the native firmware emulators (real time)
#   tools/test.sh ros                    # ROS graph smoke test (needs tools/build.sh)
#   tools/test.sh snapshot [--check]     # regenerate (or check) the packaged contract snapshot from interface/system/contract.yaml
#   tools/test.sh plan                   # calculated coverage plan / mission times for 16 x 2.5 m -> evidence/plan_2.5x16.json
#   tools/test.sh colcon          # colcon test on the built workspace (needs tools/build.sh)
#   tools/test.sh all             # unit + scenarios + native (if built) + ros (if built); non-zero exit on any failure
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
rr_require_image
what="${1:-unit}"; [ "$#" -gt 0 ] && shift
PYT=(python3 -m pytest -p no:cacheprovider -q)
unit_dirs() { ls -d "$RR_WS"/src/*/test | grep -v rr_sim/test; }
case "$what" in
  unit)      rr_docker_run -- "${PYT[@]}" $(unit_dirs) "$@" ;;
  scenarios) rr_docker_run -- "${PYT[@]}" "$RR_WS/src/rr_sim/test" "$@" ;;
  native)    PP="$(ls -d "$RR_WS"/src/*/ | tr '\n' ':')"
             # emulators built from the current firmware into ros2_ws/build/fw (README 3.2) take precedence
             HS="${RR_HEAD_SIM:-}"; CS="${RR_CHASSIS_SIM:-}"
             [ -z "$HS" ] && [ -x "$RR_WS/build/fw/head/rr_head_sim" ] && HS="$RR_WS/build/fw/head/rr_head_sim"
             [ -z "$CS" ] && [ -x "$RR_WS/build/fw/chassis/rr_chassis_sim" ] && CS="$RR_WS/build/fw/chassis/rr_chassis_sim"
             rr_docker_run -e PYTHONPATH="$PP" -e RR_HEAD_SIM="$HS" -e RR_CHASSIS_SIM="$CS" -- python3 -m rr_sim.native_scenarios "$@" ;;
  snapshot)  rr_docker_run -- python3 "$RR_WS/tools/snapshot_contract.py" "$@" ;;
  plan)      rr_docker_run -- python3 "$RR_WS/tools/plan_report.py" "$@" > "$RR_WS/evidence/plan_2.5x16.json.tmp" \
               && mv "$RR_WS/evidence/plan_2.5x16.json.tmp" "$RR_WS/evidence/plan_2.5x16.json" && echo "wrote evidence/plan_2.5x16.json" ;;
  ros)       rr_docker_run -- python3 "$RR_WS/tools/ros_smoke.py" "$@" ;;
  colcon)    rr_docker_run -- bash -c 'colcon test --parallel-workers '"$RR_PARALLEL"' --event-handlers console_cohesion+ && colcon test-result --verbose' ;;
  all)       rc=0
             "$0" unit || rc=1
             "$0" scenarios || rc=1
             if [ -x "$RR_REPO/firmware/head/build/host/rr_head_sim" ] && [ -x "$RR_REPO/firmware/chassis/build/rr_chassis_sim" ]; then
               "$0" native || rc=1
             else
               echo "SKIPPED native: emulators not built (see README: firmware build commands)"; fi
             if [ -f "$RR_WS/install/setup.bash" ]; then "$0" ros || rc=1
             else echo "SKIPPED ros: workspace not built (tools/build.sh)"; fi
             [ "$rc" = 0 ] && echo "ALL TEST GROUPS PASSED" || echo "AT LEAST ONE TEST GROUP FAILED"
             exit "$rc" ;;
  *) echo "usage: tools/test.sh [unit|scenarios|native|ros|plan|snapshot|colcon|all] [pytest args]" >&2; exit 2 ;;
esac
