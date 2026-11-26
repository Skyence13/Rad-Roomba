#!/usr/bin/env bash
# Regenerate every mechanical/common output and run the checks. Non-zero exit on any failed check.
# Usage: mechanical/common/build.sh            (uses $RR_PY, else ./.venv, else python3)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="${RR_PY:-}"
if [ -z "$PY" ]; then
  if [ -x "$HERE/.venv/bin/python" ]; then PY="$HERE/.venv/bin/python"; else PY="python3"; fi
fi
cd "$REPO"
echo "== python: $($PY -c 'import sys,cadquery;print(sys.version.split()[0], "cadquery", cadquery.__version__)')"
echo "== 1/4 parameters";            "$PY" -m mechanical.common.params > "$HERE/out/params_summary.json"
echo "== 2/4 interface files";       "$PY" -m mechanical.common.gen_interfaces
echo "== 3/4 master layout + checks"; "$PY" -m mechanical.common.layout "$@"
echo "== 4/4 calculations";          "$PY" -m mechanical.common.calc.run_all
echo "== all mechanical/common outputs regenerated, all checks passed"
