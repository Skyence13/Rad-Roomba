#!/bin/bash
# Regenerate the RR-X prototype body (parts, exports, checks, documents). Non-zero exit if a check fails.
# PY may point at any Python 3.12 with the packages of requirements.txt (default: the session venv, then python3).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="/tmp/claude-0/-home-user-Rad-Roomba/243ed1e7-dcf1-5450-82ee-f4f91fbe9462/scratchpad/cqenv/bin/python"
PY="${PY:-$([ -x "$VENV" ] && echo "$VENV" || echo python3)}"
cd "$ROOT"
exec "$PY" -m mechanical.prototype_x1c.build "$@"
