"""Null reference rate U_null (analysis/radiometry/MODEL.md REVISION 5, section 3 "Where U_null comes from").

U_null is estimated from reference counts that are not terms of the statistic under test: the lane's own reference
gates nearest in time to the dwell, from the attachment record, excluding every gate under test of the cell.  Two
adjacent sub-windows (one before and one after the dwell where both exist, otherwise both on the available side),
each holding at least N_min reference counts (N_min by alpha); U_null is the LARGER of the two sub-window means and
the predictive threshold uses that sub-window's count and live time.  Where the lane's sub-windows would span more
than 2 m of travel, the four-lane pooled reference over the same rule, scaled by the lane's reference-rate ratio over
the attachment, with the effective count 1/(1/N_pool + 1/n_lane + 1/n_all).  One-sided windows carry a gradient
guard (projected bias at the dwell > 2 % -> `sensitivity insufficient - reference gradient`).  Fewer than N_min counts
for every source -> `no decision - null reference unavailable`.

Also: the past-only reference of the search-stage ratemeter, and the recount reference (other three lanes during the
recount, ratio-scaled).  A head reset opens a new attachment, so a window never crosses one (each attachment has its
own `Series`).  Implementation choices that MODEL.md leaves open are stated in IMPL_NOTES and in the export manifest.
No ROS imports.
"""
from __future__ import annotations

import bisect
import math

import numpy as np

from .estimator import kappa

N_MIN_TABLE = ((1e-2, 30), (1e-3, 75), (1e-4, 125), (1e-6, 200))     # MODEL.md rev 5 section 3
MAX_SPAN_M = 2.0
GRADIENT_LIMIT = 0.02
IMPL_NOTES = {
    "dwell": "the dwell of a lane is the contiguous run of the cell's member gates (sequence numbers) holding the largest weight of that lane in the attachment; sub-windows are built outward from its edges, nearest first, with every member gate of the cell (any lane, any pass) contributing nothing",
    "n_min_alpha": "N_min is chosen for the smallest alpha of the decision's tests (0.2 alpha / m for the per-lane tests); below 1e-6: 200 (z_alpha / z_1e-6)^2 (computed)",
    "span": "span of a sub-window = travel distance (path length of the gate mid poses) from the dwell edge to its far end; the lane source is used only if every used sub-window spans <= 2 m",
    "gradient": "relative difference of the two sub-window means per metre between their centres; one-sided windows: bias = U_null / (linear extrapolation of the two means to the dwell centre) - 1, |bias| > 2 % -> sensitivity insufficient - reference gradient; zero separation -> no gradient (0)",
    "pool": "pooled: sum of the four lanes' valid reference counts and live times (a per-lane rate); lane ratio = (n_lane/t_lane)/(n_all/t_all) over the attachment outside the cell's dwell; U_null = ratio x pooled sub-window mean; posterior Gamma(N_eff + 1/2, scale U_null/N_eff)",
    "recount": "recount: the other three lanes' reference counts during the recount gates, ratio-scaled (ratio qualified when lane and other-lane counts over the attachment outside the recount are >= N_min each), N_eff = 1/(1/N_others + 1/n_lane + 1/n_others,att); otherwise the lane's own two-sub-window rule around the recount",
    "search": "search stage: two past sub-windows before the trailing dwell, larger mean (lane, else pooled); no gradient guard (provisional, controls recounts only)",
}


def n_min(alpha: float) -> int:
    for a, n in N_MIN_TABLE:
        if alpha >= a:
            return n
    return int(math.ceil(200.0 * (kappa(alpha) / kappa(1e-6)) ** 2))


class Series:
    """Reference series of one attachment: per gate (sorted by sequence) the four lanes' valid reference counts and live
    times (zero where the lane's reference is null or flagged) and the travel distance of the gate mid pose."""

    def __init__(self, seqs, N, T, dist):
        self.seqs = list(seqs)
        self.N = np.asarray(N, float).reshape(4, -1)
        self.T = np.asarray(T, float).reshape(4, -1)
        self.dist = np.asarray(dist, float)
        z = np.zeros((4, 1))
        self.cN = np.concatenate((z, np.cumsum(self.N, axis=1)), axis=1)
        self.cT = np.concatenate((z, np.cumsum(self.T, axis=1)), axis=1)
        self.pN, self.pT = self.cN.sum(axis=0), self.cT.sum(axis=0)

    @classmethod
    def build(cls, ref: dict, geo: dict):
        """ref: seq -> [(N, T) or None] * 4 ; geo: seq -> (x, y) of the gate's mid pose (absent: no pose)."""
        seqs = sorted(ref)
        N = np.zeros((4, len(seqs)))
        T = np.zeros((4, len(seqs)))
        dist = np.zeros(len(seqs))
        last, d = None, 0.0
        for i, q in enumerate(seqs):
            for ln, v in enumerate(ref[q]):
                if v is not None:
                    N[ln, i], T[ln, i] = v
            p = geo.get(q)
            if p is not None:
                if last is not None:
                    d += math.hypot(p[0] - last[0], p[1] - last[1])
                last = p
            dist[i] = d
        return cls(seqs, N, T, dist)

    def __len__(self):
        return len(self.seqs)

    def masked(self, exclude_seqs):
        """The same series with the gates `exclude_seqs` (every gate under test of the cell) contributing no reference
        counts or live time; positions are kept."""
        idx = [i for i, q in ((bisect.bisect_left(self.seqs, q), q) for q in exclude_seqs) if i < len(self.seqs) and self.seqs[i] == q]
        if not idx:
            return self
        N, T = self.N.copy(), self.T.copy()
        N[:, idx] = 0.0
        T[:, idx] = 0.0
        return Series(self.seqs, N, T, self.dist)

    def _cum(self, lane):
        return (self.pN, self.pT) if lane is None else (self.cN[lane], self.cT[lane])

    def window(self, lane, i_lo, i_hi, side_seq):
        """Record of the sub-window of gate indices [i_lo, i_hi) (lane None = pooled)."""
        cN, cT = self._cum(lane)
        n, t = float(cN[i_hi] - cN[i_lo]), float(cT[i_hi] - cT[i_lo])
        return {"seq_lo": self.seqs[i_lo], "seq_hi": self.seqs[i_hi - 1], "n": n, "t_s": t,
                "mean": n / t if t > 0 else None, "centre_m": 0.5 * (self.dist[i_lo] + self.dist[i_hi - 1]), "side": side_seq}

    def before(self, lane, i0, need):
        """Largest j < i0 with counts in [j, i0) >= need, or None."""
        cN, _ = self._cum(lane)
        if cN[i0] - cN[0] < need:
            return None
        return int(np.searchsorted(cN, cN[i0] - need, side="right") - 1)

    def after(self, lane, i1, need):
        """Smallest j > i1 with counts in [i1, j) >= need, or None."""
        cN, _ = self._cum(lane)
        if cN[-1] - cN[i1] < need:
            return None
        return int(np.searchsorted(cN, cN[i1] + need, side="left"))

    def index_range(self, lo_seq, hi_seq):
        return bisect.bisect_left(self.seqs, lo_seq), bisect.bisect_right(self.seqs, hi_seq)

    def totals(self, lane, exclude=None):
        """(n, t) of a lane (None: all four) over the attachment, excluding the index range `exclude`."""
        cN, cT = self._cum(lane)
        n, t = float(cN[-1]), float(cT[-1])
        if exclude is not None:
            a, b = exclude
            n -= float(cN[b] - cN[a])
            t -= float(cT[b] - cT[a])
        return n, t


def _sub_windows(s: Series, lane, i0, i1, need, past_only=False):
    """Two adjacent sub-windows around the dwell [i0, i1): (w1, w2, two_sided) or None."""
    jb = s.before(lane, i0, need)
    ja = None if past_only else s.after(lane, i1, need)
    if jb is not None and ja is not None:
        return s.window(lane, jb, i0, "before"), s.window(lane, i1, ja, "after"), True
    if jb is not None:
        jb2 = s.before(lane, jb, need)
        if jb2 is not None:
            return s.window(lane, jb, i0, "before"), s.window(lane, jb2, jb, "before"), False
    if ja is not None and not past_only:
        ja2 = s.after(lane, ja, need)
        if ja2 is not None:
            return s.window(lane, i1, ja, "after"), s.window(lane, ja, ja2, "after"), False
    return None


def _span(s: Series, w, i0, i1):
    edge = s.dist[min(i0, len(s) - 1)] if w["side"] == "before" else s.dist[max(i1 - 1, 0)]
    lo, hi = s.index_range(w["seq_lo"], w["seq_hi"])
    far = s.dist[lo] if w["side"] == "before" else s.dist[hi - 1]
    return abs(edge - far)


def _gradient(w1, w2, dwell_centre, two_sided):
    """(gradient per m, projected relative bias of the selected (larger) mean at the dwell)."""
    m1, m2 = w1["mean"], w2["mean"]
    sep = abs(w2["centre_m"] - w1["centre_m"])
    mref = 0.5 * (m1 + m2)
    if sep <= 1e-9 or mref <= 0:
        return 0.0, 0.0
    g = (m2 - m1) / mref / (w2["centre_m"] - w1["centre_m"])
    if two_sided:
        return g, 0.0
    sel = max(m1, m2)
    proj = m1 + (m2 - m1) / (w2["centre_m"] - w1["centre_m"]) * (dwell_centre - w1["centre_m"])
    return g, (sel / proj - 1.0) if proj > 0 else math.inf


def u_null(s: Series, lane: int, dwell_seqs, alpha: float, past_only=False, max_span_m=MAX_SPAN_M, exclude_seqs=None):
    """U_null record of one lane for a dwell given by its sequence range (lo, hi) in this attachment.

    Returns a dict: status OK | GRADIENT | UNAVAILABLE, source lane | pooled, U0, N_post, T_post (posterior inputs),
    windows (both sub-windows with counts, live times, spans), selected, gradient_per_m, projected_bias, lane ratio and
    its counts where pooled, n_min."""
    need = n_min(alpha)
    lo, hi = dwell_seqs
    if exclude_seqs:
        s = s.masked(exclude_seqs)
    i0, i1 = s.index_range(lo, hi)
    out = {"n_min": need, "dwell_seq": [lo, hi], "past_only": bool(past_only)}
    dwell_c = 0.5 * (s.dist[min(i0, len(s) - 1)] + s.dist[max(i1 - 1, 0)]) if len(s) else 0.0
    found = None
    sw = _sub_windows(s, lane, i0, i1, need, past_only)
    if sw is not None:
        spans = [_span(s, w, i0, i1) for w in sw[:2]]
        for w, sp in zip(sw[:2], spans):
            w["span_m"] = sp
        if max(spans) <= max_span_m:
            found = ("lane", sw)
        else:
            out["lane_rejected"] = f"sub-windows span {max(spans):.2f} m > {max_span_m:g} m"
    if found is None:
        sw = _sub_windows(s, None, i0, i1, need, past_only)
        if sw is not None:
            for w in sw[:2]:
                w["span_m"] = _span(s, w, i0, i1)
            found = ("pooled", sw)
    if found is None:
        out.update(status="UNAVAILABLE", source=None, U0=None, N_post=None, T_post=None)
        return out
    source, (w1, w2, two) = found
    sel = w1 if (w1["mean"] or 0) >= (w2["mean"] or 0) else w2
    g, bias = _gradient(w1, w2, dwell_c, two)
    out.update(source=source, windows=[w1, w2], two_sided=two, selected=0 if sel is w1 else 1,
               gradient_per_m=g, projected_bias=bias)
    if source == "lane":
        U0 = sel["mean"]
        out.update(U0=U0, N_post=sel["n"], T_post=sel["t_s"])
    else:
        n_l, t_l = s.totals(lane, None if exclude_seqs else (i0, i1))
        n_a, t_a = s.totals(None, None if exclude_seqs else (i0, i1))
        if n_l <= 0 or t_l <= 0 or n_a <= 0:
            out.update(status="UNAVAILABLE", source=None, U0=None, N_post=None, T_post=None)
            return out
        ratio = (n_l / t_l) / (n_a / t_a)
        U0 = ratio * sel["mean"]
        n_eff = 1.0 / (1.0 / sel["n"] + 1.0 / n_l + 1.0 / n_a)
        out.update(U0=U0, N_post=n_eff, T_post=n_eff / U0, lane_ratio=ratio, ratio_counts=[n_l, n_a])
    out["status"] = "GRADIENT" if (not two and not past_only and abs(bias) > GRADIENT_LIMIT) else "OK"
    return out


def recount_u_null(s: Series, lane: int, count_seqs, alpha: float):
    """Recount reference (MODEL.md rev 5 section 3 "Recounts"): the other three lanes during the recount gates,
    scaled by their reference-rate ratio to the tested lane over the attachment outside the recount; else the lane's
    own two-sub-window rule."""
    need = n_min(alpha)
    lo, hi = min(count_seqs), max(count_seqs)
    i0, i1 = s.index_range(lo, hi)
    idx = [s.seqs.index(q) for q in sorted(count_seqs) if q in s.seqs]
    others = [ln for ln in range(4) if ln != lane]
    n_o = float(sum(s.N[ln, i] for ln in others for i in idx))
    t_o = float(sum(s.T[ln, i] for ln in others for i in idx))
    n_l, t_l = s.totals(lane, (i0, i1))
    n_oa = sum(s.totals(ln, (i0, i1))[0] for ln in others)
    t_oa = sum(s.totals(ln, (i0, i1))[1] for ln in others)
    out = {"n_min": need, "dwell_seq": [lo, hi], "source": None}
    if n_o >= need and n_l >= need and n_oa >= need and t_o > 0 and t_l > 0 and t_oa > 0:
        ratio = (n_l / t_l) / (n_oa / t_oa)
        U0 = ratio * n_o / t_o
        n_eff = 1.0 / (1.0 / n_o + 1.0 / n_l + 1.0 / n_oa)
        out.update(status="OK", source="other-lanes-during-recount", U0=U0, N_post=n_eff, T_post=n_eff / U0,
                   lane_ratio=ratio, ratio_counts=[n_l, n_oa], windows=[{"n": n_o, "t_s": t_o, "seq_lo": lo, "seq_hi": hi,
                                                                        "side": "during", "span_m": 0.0, "mean": n_o / t_o}],
                   selected=0, gradient_per_m=0.0, projected_bias=0.0, two_sided=True)
        return out
    rec = u_null(s, lane, (lo, hi), alpha)
    rec["fallback"] = "own-lane (ratio not qualified or too few counts in the other lanes)"
    return rec
