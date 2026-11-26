#!/usr/bin/env bash
# Offline replay: rebuild every survey product (cells, maps, flags, summary, manifest) from the
# append-only journal of a run directory, under the archived profile/calibration versions.
#
#   tools/replay.sh <run_dir> <out_dir>        # out_dir is REPLACED (deleted and rewritten)
#
# Both paths must be visible inside the container (anything under the repository is; the
# simulator and robot node write runs to /tmp/rr_runs/... INSIDE their container, so pass
# run_dir:=<path under the repo> / --run-dir <path under the repo> when you want to replay later).
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
rr_require_image
[ "$#" -eq 2 ] || { echo "usage: tools/replay.sh <run_dir> <out_dir>" >&2; exit 2; }
run_dir="$(cd "$1" && pwd)"; mkdir -p "$2"; out_dir="$(cd "$2" && pwd)"
PP="$(ls -d "$RR_WS"/src/*/ | tr '\n' ':')"
rr_docker_run -e PYTHONPATH="$PP" -- python3 -c '
import json, sys
from rr_core.pipeline import replay
out = replay(sys.argv[1], sys.argv[2])
print("replayed products written to", out["dir"], "(%d files)" % len(out["files"]))' "$run_dir" "$out_dir"
