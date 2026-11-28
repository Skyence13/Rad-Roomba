#!/bin/bash
# Long unattended routing runs on the copies of the real boards (one Freerouting job at a time).
# Results: <dir>/reports/summary.json, <dir>/reports/open_connections.txt, <dir>/route/progress.log,
# and one summary line per board in tools/eda/tests/real_boards_results.jsonl.
cd "$(dirname "$0")/../../.."
BUDGET=${BUDGET:-3000}
for d in head_escape chassis_escape; do
  rm -f tools/eda/tests/$d/route/progress.log tools/eda/tests/$d/.rrkicad.lock
  t0=$(date +%s)
  python3 tools/eda/rrkicad.py build tools/eda/tests/$d/board.py --budget $BUDGET > tools/eda/tests/$d/build.log 2>&1
  rc=$?
  t1=$(date +%s)
  python3 - "$d" "$rc" "$((t1-t0))" "$BUDGET" >> tools/eda/tests/real_boards_results.jsonl <<'PY'
import json, sys, time
d, rc, dt, budget = sys.argv[1:]
try:
    s = json.load(open("tools/eda/tests/%s/reports/summary.json" % d))
    r = s["routing"]
    fan = r.get("plane_fanout") or {}
    out = {"board": d, "date": time.strftime("%Y-%m-%d %H:%M"), "rc": int(rc), "wall_s": int(dt), "budget_s": int(budget),
           "status": s["status"], "unconnected": s["drc"]["unconnected"], "drc_errors": s["drc"]["errors"],
           "drc_warnings": s["drc"]["warnings"], "drc_by_type": s["drc"]["by_type"], "parity": s["drc"]["parity"],
           "erc_errors": s["erc"]["errors"], "attempts": (r.get("autorouter") or {}).get("attempts"),
           "finisher": {k: (len(v) if isinstance(v, list) else v) for k, v in (r.get("finisher") or {}).items()},
           "escape_vias": (r.get("escape") or {}).get("vias"), "escape_direct": (r.get("escape") or {}).get("direct"),
           "fanout_vias": fan.get("vias"), "extended": len(fan.get("extended", [])),
           "long_fanout": len(fan.get("long_fanout", [])), "plane_pads_unconnected": len(fan.get("failed", []))}
except Exception as e:
    out = {"board": d, "rc": int(rc), "wall_s": int(dt), "error": str(e)}
print(json.dumps(out, sort_keys=True))
PY
done
