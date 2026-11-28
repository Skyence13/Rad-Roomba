#!/usr/bin/env bash
# Regenerate every mechanical/head output and run the checks. Exit status = checks.py (non-zero if any check FAILS);
# everything else is regenerated even then, so the report shows the failure.
# Usage: mechanical/head/build.sh [--no-render]   (python: $RR_PY, else mechanical/common/.venv, else python3)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="${RR_PY:-}"
if [ -z "$PY" ]; then
  if [ -x "$REPO/mechanical/common/.venv/bin/python" ]; then PY="$REPO/mechanical/common/.venv/bin/python"; else PY="python3"; fi
fi
cd "$REPO"
set -e
echo "== python: $($PY -c 'import sys,cadquery,ezdxf;print(sys.version.split()[0], "cadquery", cadquery.__version__, "ezdxf", ezdxf.__version__)')"
# generated outputs only (sources, STATUS.md and the hand-written READMEs stay)
rm -rf "$HERE"/prototype/{step,print,dxf,joints,assembly} "$HERE"/production/{step,dxf,drawings,assembly} "$HERE"/aux/{step,dxf}
rm -f "$HERE"/prototype/*.step "$HERE"/production/*.step "$HERE"/aux/*.step "$HERE"/aux/*.png
set +e
echo "== 1/4 checks and calculations (out/checks.json, out/head_report.md)"
"$PY" -m mechanical.head.checks; CHK=$?
set -e
echo "== 2/4 STEP (parts, assemblies, print orientation), STL/3MF, DXF, plates.yaml"
"$PY" -m mechanical.head.export
echo "== 3/4 joint sections, fabrication drawings, assembly renders"
if [ "${1:-}" = "--no-render" ]; then "$PY" -m mechanical.head.drawings joints fab; else "$PY" -m mechanical.head.drawings joints fab steps steps_production; fi
echo "== 4/4 BOMs, print schedule, assembly instructions"
"$PY" -m mechanical.head.docs
if [ $CHK -ne 0 ]; then echo "== head outputs regenerated, but checks FAILED (see out/head_report.md)"; exit $CHK; fi
echo "== all mechanical/head outputs regenerated, all checks passed"
