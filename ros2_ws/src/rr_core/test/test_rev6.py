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
