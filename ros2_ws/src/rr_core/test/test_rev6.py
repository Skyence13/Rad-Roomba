"""MODEL.md revision 6: exact multi-lane predictive null (analyst test vectors), one-sided local-linear reference, N_min per
test set, search-stage reference.  Evidence: calculated / simulated with synthetic coefficients."""
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from rr_core import linstat, unull
from rr_core.estimator import Cal

REPO = Path(os.environ.get("RR_REPO", Path(__file__).resolve().parents[4]))
VECTORS = REPO / "analysis" / "radiometry" / "results" / "rev5_predictive_vectors.json"


def _stat(case):
    units, mu = [], 0.0
    for ln in case["lanes"]:
        c = ln["cal"]
        cal = Cal(k=c["k"], b=c["b"], u_k_lane=c["u_k_lane"], u_k_common=c["u_k_common"], u_b=c["u_b"], cov_kb=c["cov_kb"], K=c["K"])
        post = ln.get("posterior")
        nodes = linstat.posterior_nodes(post["N"], post["T_s"], case.get("posterior_nodes", 12)) if post else (np.array([ln["U0"]]), np.array([1.0]))
        cK = ln["c"] / cal.K
        units.append(linstat.Unit(cK, cal, ln["w"], ln["t_s"], ln["t_s"], *nodes))
        mu -= cK * cal.b
    return linstat.PredictiveStat(units, mu, u_rel=0.0)


@pytest.mark.skipif(not VECTORS.exists(), reason="analyst vectors not present")
@pytest.mark.parametrize("i", range(6))
def test_predictive_null_equals_the_analyst_vectors(i):
    case = json.loads(VECTORS.read_text())["cases"][i]
    st = _stat(case)
    for r in case["results"]:
        t, ok, _ = st.threshold(r["alpha"])
        assert ok
        assert t == pytest.approx(r["t_star_exact"], rel=1e-6), (case["m"], r["alpha"])
        if r.get("D_hash_Bq_cm2_u_rel_K_0") is not None:
            d = st.detection_limit(t, 0.05, t * 2)
            assert d == pytest.approx(r["D_hash_Bq_cm2_u_rel_K_0"], rel=1e-5), (case["m"], r["alpha"])


def test_async_recorded_evaluation_equals_the_synchronous_one_and_reports_progress():
    """Lead task 3: the recorded evaluation on a worker thread (frozen copy at the journaled point) gives exactly the
    synchronous result, while the live processor keeps receiving gates."""
    import test_rev5 as T
    sync = T.survey(n_pass=2)
    sig_sync = T.recorded_signature(sync)
    live = T.survey(n_pass=2)                       # same data; survey() ends with finalize(): redo it asynchronously
    live.recorded = {ch: {} for ch in live.recorded}
    live.__dict__["_rec_members"] = {}
    live._recorded_version = None
    job = live.start_finalize_async()
    assert job["total"] == len(live.members)
    live.join_finalize_async()
    assert live.finalize_progress() is None and live.last_finalize["error"] is None
    assert T.recorded_signature(live) == sig_sync
    per_cell = live.last_finalize["seconds"] / max(1, job["total"])
    print(f"recorded evaluation: {job['total']} cells in {live.last_finalize['seconds']:.1f} s ({1e3 * per_cell:.0f} ms per cell)")


def test_one_sided_reference_local_linear_and_marked():
    from test_rev5 import _series
    s = _series(n=600, seed=3)
    rec = unull.u_null(s, 0, (0, 4), 0.01, exclude_seqs=set(range(5)))
    assert rec["one_sided"] and rec["status"] == "OK" and "gradient_per_m" in rec
    w1, w2 = rec["windows"]
    ext = 1.5 * w1["mean"] - 0.5 * w2["mean"]
    if ext > w1["mean"]:
        assert rec["U0"] == pytest.approx(ext) and rec["N_post"] == pytest.approx(1.0 / (2.25 / w1["n"] + 0.25 / w2["n"]))
    else:
        assert rec["U0"] == pytest.approx(w1["mean"]) and rec["N_post"] == w1["n"]


def test_search_reference_one_pooled_sub_window_and_reuse_limits():
    from test_rev5 import _series
    s = _series(n=300)
    assert unull.n_scan(0.05) == 25 and unull.n_scan(1e-3) == 50 and unull.n_scan(1e-5) == 105
    rec = unull.search_u_null(s, 2, (290, 299), 1e-5, lane_ratio=1.02, ratio_rel_u=0.01)
    assert rec["status"] == "OK" and rec["n"] >= 105 and rec["U0"] == pytest.approx(1.02 * rec["n"] / rec["t_s"])
    assert rec["N_post"] == pytest.approx(1.0 / (1.0 / rec["n"] + 1e-4))
    none = unull.search_u_null(s, 2, (290, 299), 1e-5, usable=lambda q: q > 280)     # reuse limited to the last 1 s
    assert none["status"] == "UNAVAILABLE"
