#!/usr/bin/env bash
# Run the tests inside the container.
#
#   tools/test.sh                 # unit tests of every package (pytest on the sources)
#   tools/test.sh unit [pytest args...]
#   tools/test.sh scenarios [pytest args...]   # end-to-end scenarios (evidence/ is rewritten)
#   tools/test.sh colcon          # colcon test on the built workspace (needs tools/build.sh)
#   tools/test.sh all             # unit + scenarios + colcon
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
rr_require_image
what="${1:-unit}"; [ "$#" -gt 0 ] && shift
PYT=(python3 -m pytest -p no:cacheprovider -q)
unit_dirs() { ls -d "$RR_WS"/src/*/test | grep -v rr_sim/test; }
case "$what" in
  unit)      rr_docker_run -- "${PYT[@]}" $(unit_dirs) "$@" ;;
  scenarios) rr_docker_run -- "${PYT[@]}" "$RR_WS/src/rr_sim/test" "$@" ;;
  colcon)    rr_docker_run -- bash -c 'colcon test --parallel-workers '"$RR_PARALLEL"' --event-handlers console_cohesion+ && colcon test-result --verbose' ;;
  all)       "$0" unit && "$0" scenarios && "$0" colcon ;;
  *) echo "usage: tools/test.sh [unit|scenarios|colcon|all] [pytest args]" >&2; exit 2 ;;
esac
