#!/usr/bin/env bash
# Run a command inside the KiCad 9 container with the repository bind-mounted
# at the SAME absolute path as on the host (so paths are identical inside/outside).
#
#   tools/docker/kicad.sh kicad-cli version
#   tools/docker/kicad.sh python3 -c 'import pcbnew; print(pcbnew.Version())'
#
# - No network is used inside the container (--network none).
# - Runs as the invoking host uid:gid so generated files are owned by the caller.
# - HOME is a throw-away dir seeded with KiCad's stock global sym/fp-lib-tables,
#   so ERC/DRC library checks resolve the stock libraries under /usr/share/kicad.
# Env: RR_KICAD_IMAGE (default kicad/kicad:9.0), RR_DOCKER_ARGS (extra docker args).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${RR_KICAD_IMAGE:-kicad/kicad:9.0}"
WORK="$PWD"
case "$WORK/" in "$REPO"/*) ;; *) WORK="$REPO" ;; esac
TTY=()
[ -t 0 ] && [ -t 1 ] && TTY=(-it)
# shellcheck disable=SC2086
exec docker run --rm "${TTY[@]}" --network none \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/rrhome \
  -e PYTHONPATH="$REPO/tools/eda" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONHASHSEED=0 \
  -e LC_ALL=C.UTF-8 \
  -e RR_REPO="$REPO" \
  -v "$REPO:$REPO" -w "$WORK" \
  ${RR_DOCKER_ARGS:-} \
  "$IMAGE" bash -c '
    mkdir -p "$HOME/.config/kicad/9.0" &&
    cp /usr/share/kicad/template/sym-lib-table /usr/share/kicad/template/fp-lib-table "$HOME/.config/kicad/9.0/" &&
    exec "$@"' rrkicad "$@"
