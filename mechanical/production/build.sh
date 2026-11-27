#!/bin/bash
# Regenerate the RR-P production body (parts, STEP, DXF, drawings, BOM, checks, documents). Non-zero exit if a check fails.
# PY (or RR_PY) may point at any Python 3.12 with CadQuery 2.7 + ezdxf + matplotlib (default: the session venv, then python3).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="/tmp/claude-0/-home-user-Rad-Roomba/243ed1e7-dcf1-5450-82ee-f4f91fbe9462/scratchpad/cqenv/bin/python"
PY="${PY:-${RR_PY:-$([ -x "$VENV" ] && echo "$VENV" || echo python3)}}"
cd "$ROOT"
export RR_BUILD=production
exec "$PY" -m mechanical.production.build "$@"
