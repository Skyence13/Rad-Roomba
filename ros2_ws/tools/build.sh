#!/usr/bin/env bash
# Build the derived Docker image (if missing or --image given) and the colcon
# workspace.
#
#   tools/build.sh            # image if missing, then colcon build
#   tools/build.sh --image    # force image rebuild first
#   tools/build.sh --clean    # remove build/ install/ log/ first
#
# Env: RR_IMAGE (default rad-roomba/ros2-ws:0.4), RR_PARALLEL (default 2).
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

FORCE_IMAGE=0; CLEAN=0
for a in "$@"; do
  case "$a" in
    --image) FORCE_IMAGE=1 ;;
    --clean) CLEAN=1 ;;
    *) echo "unknown argument $a" >&2; exit 2 ;;
  esac
done

if [ "$FORCE_IMAGE" = 1 ] || ! docker image inspect "$RR_IMAGE" >/dev/null 2>&1; then
  echo "== building image $RR_IMAGE"
  # --network host: the build needs the Ubuntu archive (plain HTTP mirror).
  docker build --network host -t "$RR_IMAGE" -f "$RR_WS/docker/Dockerfile" "$RR_WS/docker"
fi

# Version drift check (informational; the lock file is the recorded set).
if docker run --rm "$RR_IMAGE" cat /opt/rr/versions.lock > /tmp/rr_versions.$$ 2>/dev/null; then
  if [ -f "$RR_WS/docker/versions.lock" ]; then
    if ! diff -u "$RR_WS/docker/versions.lock" /tmp/rr_versions.$$; then
      echo "WARNING: image package versions differ from docker/versions.lock (shown above)" >&2
    fi
  else
    cp /tmp/rr_versions.$$ "$RR_WS/docker/versions.lock"
    echo "wrote docker/versions.lock"
  fi
  rm -f /tmp/rr_versions.$$
fi

if [ "$CLEAN" = 1 ]; then
  rm -rf "$RR_WS/build" "$RR_WS/install" "$RR_WS/log"
fi

echo "== colcon build (parallel workers: $RR_PARALLEL)"
rr_docker_run -- colcon build --symlink-install \
  --parallel-workers "$RR_PARALLEL" \
  --executor parallel \
  --event-handlers console_cohesion+ status- \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
echo "== build finished"
