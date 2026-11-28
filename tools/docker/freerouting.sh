#!/usr/bin/env bash
# Run Freerouting headless (no GUI, no API server, no network) on a Specctra DSN.
#
#   tools/docker/freerouting.sh <in.dsn> <out.ses> [max_passes] [threads] [extra freerouting args...]
#
# Both files must live inside the repository (it is bind-mounted at the same path).
# Runs as the invoking host uid:gid; Freerouting's user-data dir is a throw-away /tmp dir.
# Env: RR_FREEROUTING_IMAGE (default ghcr.io/freerouting/freerouting:latest),
#      RR_FREEROUTING_JAVA_OPTS (default -Xmx3g), RR_DOCKER_ARGS.
set -euo pipefail
if [ $# -lt 2 ]; then
  sed -n '2,10p' "$0"; exit 2
fi
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${RR_FREEROUTING_IMAGE:-ghcr.io/freerouting/freerouting:latest}"
DSN="$(realpath "$1")"; SES="$(realpath -m "$2")"
PASSES="${3:-100}"; THREADS="${4:-$(nproc)}"
shift 2; [ $# -gt 0 ] && shift; [ $# -gt 0 ] && shift
# shellcheck disable=SC2086
exec docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/frhome \
  -v "$REPO:$REPO" -w "$(dirname "$DSN")" \
  ${RR_DOCKER_ARGS:-} \
  --entrypoint java "$IMAGE" \
  ${RR_FREEROUTING_JAVA_OPTS:--Xmx3g} -Djava.awt.headless=true \
  -jar /app/freerouting-executable.jar \
  --user_data_path=/tmp/frhome \
  --gui.enabled=false --api_server.enabled=false \
  --usage_and_diagnostic_data.disable_analytics=true \
  --logging.file.enabled=false \
  -de "$DSN" -do "$SES" -mp "$PASSES" -mt "$THREADS" "$@"
