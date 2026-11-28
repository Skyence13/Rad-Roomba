#!/usr/bin/env python3
"""Independent cross-check of exported cells with the analysis library (lead task 5, 2026-11-28).

    python3 tools/crosscheck_rrrad.py <run_dir> <export_dir> [--cells N] [--max-lanes 2]

What is independent of rr_core:
  * the raw frames are read from the archived journal by a minimal parser here (record = JSON before the TAB; ACQ bodies;
    attachment from the SESSION_OPEN control entries) - not the rr_core head-stream interpreter;
  * the cell statistic is rebuilt here from the exported members (cell_members.csv: attachment, sequence, lane, weight) and
    those counts: coefficients c_i/K_i w/T_F and -c_i/K_i k w/T_U, c_i from the inverse null variances at U0;
  * tails come from analysis/radiometry/rrrad.linstat.tail_gp (Gil-Pelaez of rrrad) averaged over the PRODUCT of the lanes'
    posterior nodes (rrrad.unull.posterior_nodes), with the common calibration term at each node tuple;
  * thresholds and detection limits are solved here.
What is taken from the export (and checked only for consistency): the U_null of each lane (U0, N_post, T_post in
cells.csv `u0_windows`); the sub-window counts in that record are re-summed from the raw frames.
Cells with at most --max-lanes lanes (12^m node tuples) are used.  rr_core never imports rrrad; this tool does.
Evidence class: simulated (synthetic data), tool-checked.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtri

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS.parent / "analysis" / "radiometry"))
from rrrad import linstat as RL          # noqa: E402
from rrrad.unull import posterior_nodes  # noqa: E402


def read_frames(run_dir):
    """{(attachment, seq): frame} from the journal segments (E <t> <kind> <n>\\n payload \\n)."""
    jdir = Path(run_dir) / "journal"
    segs = sorted(list(jdir.glob("*.seg")) + list(jdir.glob("*.part")))
    frames, att = {}, None
    for seg in segs:
        data = seg.read_bytes()
        i = 0
        while i < len(data):
            j = data.find(b"\n", i)
            if j < 0:
                break
            head = data[i:j].split(b" ")
            if len(head) != 4 or head[0] != b"E":
                break
            kind, n = head[2].decode(), int(head[3])
            payload = data[j + 1:j + 1 + n]
            i = j + 1 + n + 1
            if kind == "C":
                c = json.loads(payload)
                if c.get("c") == "SESSION_OPEN":
                    att = c["manifest"]["attachment_session_id"]
            elif kind == "R" and att is not None:
                body = payload.split(b"\t")[0]
                try:
                    rec = json.loads(body)
                except ValueError:
                    continue
                b = rec.get("body") if isinstance(rec, dict) else None
                if isinstance(b, dict) and b.get("type") == "ACQ":
                    frames.setdefault((att, b["sequence"]), b)
    return frames


def lane_counts(frame, lane):
    seg = next(s for s in frame["segments"] if s["id"] == lane)
    bw, ref = seg["beta_window"], seg["photon_ref"]
    return bw["counts"], bw["live_us"] * 1e-6, ref["counts"], ref["live_us"] * 1e-6


class Cal:
    def __init__(self, c):
        comp = c.get("u_k_components", {})
        self.k, self.b, self.K = c["k"], c["b_cps"], c["K_cps_per_Bq_cm2"]
        self.u_common = comp.get("spectral_mismatch_relative", 0.0) * c["k"]
        self.u_lane = comp.get("fit") if comp.get("fit") is not None else max(c.get("u_k", 0.0) ** 2 - self.u_common ** 2, 0.0) ** 0.5
        self.u_b, self.cov = c.get("u_b_cps", 0.0), c.get("cov_kb_cps", 0.0)
        self.u_rel_K = c.get("u_rel_K", 0.0)

    def var_lane(self, U):
        return max(U * U * self.u_lane ** 2 + self.u_b ** 2 + 2.0 * U * self.cov, 0.0)


def parse_u0(text):
    """unit -> dict(U0, N_post, T_post, one_sided, windows[(lo, hi, N, T)]) from cells.csv u0_windows."""
    out = {}
    for part in text.split(";"):
        if not part:
            continue
        mt = re.match(r"^((?:A\d+:)?L\d+):([a-z-]+)", part)
        if mt is None or ":unavailable" in part:
            continue
        unit = mt.group(1)
        g = lambda key: re.search(key + r"=([^:]+)", part).group(1)  # noqa: E731
        wins = [(int(a), int(b), float(n), float(t)) for a, b, n, t in re.findall(r"\[(\d+)-(\d+)\]N=([\d.]+)/T=([\d.]+)s", part)]
        out[unit] = {"U0": float(g("U0x")), "N_post": float(g("Npost")), "T_post": float(g("Tpost")),
                     "source": mt.group(2), "windows": wins}
    return out


class CellStat:
    """S = sum_i c_i r_i / K_i with each lane's predictive U posterior, the lanes independent, common term per tuple."""

    def __init__(self, lanes, alpha, beta):
        self.lanes, self.alpha, self.beta = lanes, alpha, beta
        inv = []
        for L in lanes:
            cal, U0, w, tf, tu = L["cal"], L["U0"], L["w"], L["tf"], L["tu"]
            TF, TU = float(np.dot(w, tf)), float(np.dot(w, tu))
            var = ((cal.k * U0 + cal.b) * float(np.dot(w * w, tf)) / TF ** 2 + cal.k ** 2 * U0 * float(np.dot(w * w, tu)) / TU ** 2
                   + cal.var_lane(U0)) / cal.K ** 2
            inv.append(1.0 / var)
        self.c = np.array(inv) / sum(inv)
        self.nodes = [posterior_nodes(L["N_post"], L["T_post"], 12) for L in lanes]
        self.u_rel = float(sum(ci * L["cal"].u_rel_K for ci, L in zip(self.c, lanes)))

    def stats(self, c, D=0.0, idx=None):
        """[(prob, rrrad LinStat)] over the node tuples for coefficients c (lanes idx)."""
        import itertools
        idx = list(range(len(self.lanes))) if idx is None else idx
        out = []
        for combo in itertools.product(*[range(12) for _ in idx]):
            a, lam, mu, s2, gsum, p = [], [], 0.0, 0.0, 0.0, 1.0
            for ci, i, k in zip(c, idx, combo):
                L = self.lanes[i]
                cal, w, tf, tu = L["cal"], L["w"], L["tf"], L["tu"]
                U = self.nodes[i][0][k]
                p *= self.nodes[i][1][k]
                cK = ci / cal.K
                TF, TU = float(np.dot(w, tf)), float(np.dot(w, tu))
                a += list(cK * w / TF) + list(-cK * cal.k * w / TU)
                lam += list((cal.k * U + cal.b + cal.K * D) * tf) + list(U * tu)
                mu -= cK * cal.b
                s2 += cK * cK * cal.var_lane(U)
                gsum += cK * cal.u_common * U
            sig = math.sqrt(s2 + gsum * gsum + (self.u_rel * D) ** 2)
            out.append((p, RL.LinStat(np.array(a), np.array(lam), mu, sig)))
        return out

    @staticmethod
    def tail(mix, x):
        return sum(p * float(RL.tail_gp(st, x)[0]) for p, st in mix)

    def threshold(self, c, alpha, idx=None):
        mix = self.stats(c, 0.0, idx)
        sd = math.sqrt(max(st.var for _p, st in mix))
        m = sum(p * st.mean for p, st in mix)
        x0 = m - ndtri(alpha) * sd
        lo, hi = x0 - 3 * sd, x0 + 3 * sd
        while self.tail(mix, hi) > alpha:
            hi += 2 * sd
        while self.tail(mix, lo) < alpha:
            lo -= 2 * sd
        return float(brentq(lambda x: self.tail(mix, x) - alpha, lo, hi, xtol=1e-12 * sd, rtol=1e-11))

    def detection_limit(self, t):
        f = lambda D: self.tail(self.stats(self.c, D), t) - (1.0 - self.beta)  # noqa: E731
        hi = max(t, 1e-3) * 2
        while f(hi) < 0:
            hi *= 2
        return float(brentq(f, 0.0, hi, xtol=1e-10, rtol=1e-8))


def check_cell(row, members, frames, cals, alpha, beta, unit_names):
    units = parse_u0(row["beta_window.u0_windows"])
    by = {}
    for m in members:
        by.setdefault((m["attachment"], int(m["lane"])), []).append((int(m["sequence"]), float(m["weight"])))
    lanes, window_checks = [], []
    for (att, ln), rows in sorted(by.items(), key=lambda kv: (unit_names[kv[0][0]], kv[0][1])):
        unit = f"L{ln}" if unit_names[att] == 0 else f"A{unit_names[att]}:L{ln}"
        if unit not in units:
            continue
        rows.sort()
        cnt = [lane_counts(frames[(att, q)], ln) for q, _w in rows]
        u = units[unit]
        cell_seqs = {int(m["sequence"]) for m in members if m["attachment"] == att}
        for lo, hi, N, T in u["windows"]:                       # sub-window counts re-summed from the raw frames
            n_raw = 0.0
            for q in range(lo, hi + 1):
                f = frames.get((att, q))
                if f is None or q in cell_seqs or f["flags"] or f["sync"].get("state") != "LOCKED":
                    continue
                for s_ in f["segments"]:
                    if (u["source"] == "lane" and s_["id"] != ln) or s_["photon_ref"] is None:
                        continue
                    if "REFERENCE_FAULT" in s_["flags"] or "DISCRIMINATOR_FAULT" in s_["flags"]:
                        continue
                    n_raw += s_["photon_ref"]["counts"]
            window_checks.append(abs(n_raw - N) < 0.5)
        lanes.append({"unit": unit, "cal": cals[att][ln], "U0": u["U0"], "N_post": u["N_post"], "T_post": u["T_post"],
                      "w": np.array([w for _q, w in rows]), "tf": np.array([c[1] for c in cnt]), "NF": np.array([c[0] for c in cnt]),
                      "tu": np.array([c[3] for c in cnt]), "NU": np.array([c[2] for c in cnt])})
    if not lanes:
        raise ValueError(f"no lane of cell {row['ix']},{row['iy']} matched the exported U_null record")
    cs = CellStat(lanes, alpha, beta)
    r = []
    for L in lanes:
        cal = L["cal"]
        TF, TU = float(np.dot(L["w"], L["tf"])), float(np.dot(L["w"], L["tu"]))
        r.append((float(np.dot(L["w"], L["NF"])) / TF - cal.k * float(np.dot(L["w"], L["NU"])) / TU - cal.b) / cal.K)
    D = float(np.dot(cs.c, r))
    m = len(lanes)
    a_c = alpha if m == 1 else 0.8 * alpha
    t_c = cs.threshold(cs.c, a_c)
    flagged = D > t_c
    if m > 1:
        for i in range(m):
            t_i = cs.threshold(np.array([1.0]), 0.2 * alpha / m, idx=[i])
            flagged |= r[i] > t_i
    d_hash = cs.detection_limit(t_c)
    return {"cell": (row["ix"], row["iy"]), "m": m, "reference_windows_resummed_equal": all(window_checks), "n_windows": len(window_checks), "D": D, "D_star": t_c, "D_hash": d_hash, "detected": bool(flagged),
            "c": list(cs.c), "export": {k: row[f"beta_window.{k}"] for k in ("D", "D_star", "D_hash", "detected", "c_weights")}}


def crosscheck(run_dir, export_dir, n_cells=4, max_lanes=2):
    export = Path(export_dir)
    rows = list(csv.DictReader(open(export / "cells.csv")))
    mem = {}
    for m in csv.DictReader(open(export / "cell_members.csv")):
        mem.setdefault((m["ix"], m["iy"]), []).append(m)
    man = json.loads((export / "survey_manifest.json").read_text())
    prof = json.loads((export / "profile.json").read_text())
    alpha, beta = prof["alpha_per_decision"], prof["beta_per_decision"]
    cal_files = {p.name: json.loads(p.read_text()) for p in export.glob("calibration*.json")}
    by_id = {c["calibration_id"]: c for c in cal_files.values()}
    cals, unit_names = {}, {}
    for i, a in enumerate(man["attachments"]):
        rec = by_id[a["processing_calibration"]]
        cals[a["attachment_session_id"]] = {l["lane_index"]: Cal(l["classes"]["beta_window"]) for l in rec["lanes"]}
        unit_names[a["attachment_session_id"]] = i
    frames = read_frames(run_dir)
    pick = []
    for st in ("ALARM", "ACCEPTABLE", "SENSITIVITY INSUFFICIENT", "INCOMPLETE COVERAGE"):
        pick += [r for r in rows if r["status"] == st and r["beta_window.m_lanes"] and int(r["beta_window.m_lanes"]) <= max_lanes][:max(1, n_cells // 4)]
    out = []
    for r in pick[:n_cells]:
        res = check_cell(r, mem[(r["ix"], r["iy"])], frames, cals, alpha, beta, unit_names)
        ex = res["export"]
        rel = {k: abs(res[k] - float(ex[k])) / max(1e-12, abs(float(ex[k]))) for k in ("D", "D_star", "D_hash") if ex[k] not in ("", None)}
        res["rel_diff"] = rel
        res["agree"] = (all(v <= 1e-5 for v in rel.values()) and str(res["detected"]) == ex["detected"]
                        and res["reference_windows_resummed_equal"])
        out.append(res)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("export_dir")
    ap.add_argument("--cells", type=int, default=4)
    ap.add_argument("--max-lanes", type=int, default=2)
    a = ap.parse_args(argv)
    res = crosscheck(a.run_dir, a.export_dir, a.cells, a.max_lanes)
    print(json.dumps(res, indent=1, default=str))
    return 0 if res and all(r["agree"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
