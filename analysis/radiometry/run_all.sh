#!/usr/bin/env bash
# Regenerates every result, figure, demo file and the report, then runs the unit tests.
# Deterministic: fixed seeds in scripts/common.py. Exits non-zero on any failure.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if python3 -c "import numpy, scipy, matplotlib, pytest" 2>/dev/null; then
    PY=python3
  else
    VENV="${RRRAD_VENV:-.venv}"
    if [ ! -x "$VENV/bin/python" ]; then
      python3 -m venv "$VENV"
    fi
    if ! "$VENV/bin/python" -c "import numpy, scipy, matplotlib, pytest" 2>/dev/null; then
      "$VENV/bin/python" -m pip install -q -r requirements.txt
    fi
    PY="$VENV/bin/python"
  fi
fi
echo "Using $($PY --version) at $PY"
export MPLBACKEND=Agg PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

rm -f results/summary.json
$PY -m pytest -q tests
$PY scripts/s1_parameter_space.py
$PY scripts/s2_analytic.py
$PY scripts/s3_montecarlo.py
$PY scripts/s4_leakage.py
$PY scripts/s5_demo_files.py
$PY scripts/s7_rev3_checks.py
$PY scripts/s8_unull.py
$PY scripts/s9_rev5_checks.py
$PY scripts/s6_report.py
echo "run_all: OK"
