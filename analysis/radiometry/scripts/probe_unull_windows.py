#!/usr/bin/env python3
"""Probe (NOT run by run_all.sh): run ros2_ws simulator scenarios with the rr_core processing code and record,
for every call of Processor._u_null, the cell, lane, T_F, the window count and live time assembled, the test
gates' sequence numbers and the attachment series.  Needs the ros2_ws Python sources and their dependencies
(aiohttp).  Usage:  python3 scripts/probe_unull_windows.py OUT_DIR s02_head_reset_and_disconnect [...]
Then:               python3 scripts/probe_unull_windows.py --summarise OUT_DIR   -> results/rev4_window_probe.csv
Evidence class: simulated (the scenarios' synthetic photon field and calibration)."""
import collections
import csv
import glob
import pickle
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parents[1] / "ros2_ws" / "src"


def probe(out, names):
    for d in glob.glob(str(WS) + "/*/"):
        sys.path.insert(0, d)
    from rr_core import processing as P
    from rr_sim import scenarios as S
    cls = [v for v in vars(P).values() if isinstance(v, type) and hasattr(v, "_u_null")][0]
    o, oc, cur, log, procs, phase = cls._u_null, cls._cell_decision, [None], [], [], ["live"]

    def wrap(self, lane, members, T_F, span_s=0.1):
        r = o(self, lane, members, T_F, span_s)
        if self not in procs:
            procs.append(self)
        seqs = sorted({(a, s) for a, s, ln, w in members if ln == lane})
        series = [(a, min(self._ref[a][lane]) if self._ref[a][lane] else None,
                   max(self._ref[a][lane]) if self._ref[a][lane] else None) for a in range(len(self._ref))]
        atts = {a for a, s_, ln, w in members if ln == lane}
        excl = {(a, s_) for a, s_, ln, w in members}
        lane_all = sum(v[0] for a in atts for q, v in self._ref[a][lane].items() if (a, q) not in excl)
        pool_all = sum(v[0] for a in atts for ln in range(4) for q, v in self._ref[a][ln].items() if (a, q) not in excl)
        log.append(dict(lane_all=lane_all, pool_all=pool_all, phase=phase[0], cell=cur[0], gtimes=sorted(s for a, s in seqs), lane=lane, T_F=T_F, U0=r[0], method=r[1], T=r[2], N=r[3],
                        n_att=len({a for a, s in seqs}), series=series))
        return r

    def wc(self, cy, cx, channel, alpha):
        cur[0] = (cy, cx, channel)
        return oc(self, cy, cx, channel, alpha)
    cls._u_null, cls._cell_decision = wrap, wc
    for name in names:
        log.clear(); procs.clear(); phase[0] = "live"
        getattr(S, name)(tempfile.mkdtemp())
        # one final evaluation of every cell with all reference data received (MODEL.md: window centred on the dwell)
        phase[0] = "final"
        for proc in procs:
            for (cy, cx) in list(proc.members):
                try:
                    proc._cell_decision(cy, cx, "beta", proc.params["alpha_scan"])
                except Exception as err:      # noqa: BLE001 - probe only
                    print("final evaluation failed", (cy, cx), err)
        pickle.dump(list(log), open(Path(out) / f"{name}.pkl", "wb"))
        print(name, len(log))


def summarise(out):
    import numpy as np
    rows = []
    for f in sorted(glob.glob(str(Path(out) / "*.pkl"))):
        L = pickle.load(open(f, "rb"))
        for phase in ("live", "final"):
          last = {}
          for l in L:
            if l.get("phase", "live") == phase:
                last[(l["cell"], l["lane"])] = l
          if not last:
            continue
          rows.append(_summ(Path(f).stem, phase, last, L, np))
    _write(rows)


def _summ(name, phase, last, L, np):
    if True:
        cells = collections.defaultdict(list)
        for (c, _ln), l in last.items():
            if c and c[2] == "beta":
                cells[c].append(l)
        und = [c for c in cells if any(l["method"] == "unavailable" for l in cells[c])]
        fail = [l for c in cells for l in cells[c] if l["method"] == "unavailable"]
        nmin = np.array([min(l["N"] for l in cells[c]) for c in cells])
        near = 0
        for l in fail:
            half = max(100, int(np.ceil(1000 * l["T_F"])))
            e = max(s[2] for s in l["series"] if s[2] is not None)
            near += (min(l["gtimes"]) < half) or (e - max(l["gtimes"]) < half)
        und_cell = [c for c in cells if all(l["method"] == "unavailable" for l in cells[c])]
        return (name, phase, len(cells), len(und), len(und_cell), len(L[-1]["series"]), f"{np.median([l['T_F'] for c in cells for l in cells[c]]):.2f}",
                f"{np.median([l['T_F'] for l in fail]):.2f}" if fail else "", int(min(l["N"] for l in fail)) if fail else "",
                int(np.median([l["N"] for l in fail])) if fail else "", near, len(fail),
                *[int(np.sum(nmin < n)) for n in (50, 100, 200)],
                *[int(sum(min(max(l.get("lane_all", 0), l.get("pool_all", 0)) for l in cells[c]) < n for c in cells)) for n in (100, 200)],
                *[int(sum(min(l.get("lane_all", 0) for l in cells[c]) < n for c in cells)) for n in (100, 200)])


def _write(rows):
    with open(ROOT / "results" / "rev4_window_probe.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["scenario", "evaluation", "beta_cells", "cells_with_a_lane_without_window_rev4", "cells_without_any_lane_window_rev4", "attachment_series", "T_F_median_s", "T_F_median_failing_lanes_s",
                    "failing_lanes_window_counts_min", "failing_lanes_window_counts_median",
                    "failing_lanes_within_half_window_of_series_start_or_end", "failing_lanes",
                    "cells_window_lt_50_counts", "cells_window_lt_100_counts", "cells_window_lt_200_counts",
                    "cells_lt_100_counts_whole_attachment_lane_or_pooled", "cells_lt_200_counts_whole_attachment_lane_or_pooled",
                    "cells_lt_100_counts_whole_attachment_lane_only", "cells_lt_200_counts_whole_attachment_lane_only"])
        w.writerows(rows)
    print("wrote results/rev4_window_probe.csv")


if __name__ == "__main__":
    if sys.argv[1] == "--summarise":
        summarise(sys.argv[2])
    else:
        probe(sys.argv[1], sys.argv[2:])
