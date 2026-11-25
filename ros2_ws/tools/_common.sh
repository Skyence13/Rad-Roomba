#!/usr/bin/env bash
# Shared helpers for the ros2_ws wrapper scripts. Source, do not execute.
#
# The workspace is bind-mounted at the SAME absolute path inside the container
# so paths in logs, evidence files and tracebacks are identical on both sides.
# Containers run with --network host (the firmware emulators and the operator
# UI use localhost TCP/UDP ports) and as the invoking uid:gid.
set -euo pipefail
RR_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RR_REPO="$(cd "$RR_WS/.." && pwd)"
RR_IMAGE="${RR_IMAGE:-rad-roomba/ros2-ws:0.4}"
RR_PARALLEL="${RR_PARALLEL:-2}"

rr_docker_run() {
  # usage: rr_docker_run [docker args ...] -- command ...
  local extra=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do extra+=("$1"); shift; done
  shift || true
  local tty=()
  [ -t 0 ] && [ -t 1 ] && tty=(-it)
  # shellcheck disable=SC2086
  docker run --rm "${tty[@]}" --network host \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp/rrhome \
    -e ROS_LOG_DIR=/tmp/rrhome/log \
    -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-77}" \
    -e ROS_LOCALHOST_ONLY=1 \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONHASHSEED=0 \
    -e LC_ALL=C.UTF-8 \
    -e RR_REPO="$RR_REPO" -e RR_WS="$RR_WS" \
    -v "$RR_REPO:$RR_REPO" -w "$RR_WS" \
    "${extra[@]}" ${RR_DOCKER_ARGS:-} \
    "$RR_IMAGE" bash -c 'mkdir -p "$HOME/log"; source /opt/ros/jazzy/setup.bash; if [ -f "$RR_WS/install/setup.bash" ]; then source "$RR_WS/install/setup.bash"; fi; exec "$@"' rr "$@"
}

rr_require_image() {
  if ! docker image inspect "$RR_IMAGE" >/dev/null 2>&1; then
    echo "image $RR_IMAGE not found; run tools/build.sh first" >&2
    exit 3
  fi
}
