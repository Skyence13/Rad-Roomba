"""Shared constants and helpers for the study scripts. All numbers are assumptions (see report section 2)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from rrrad import fields, mc, model  # noqa: E402

RESULTS = ROOT / "results"
TABLES = RESULTS / "tables"
FIGS = ROOT / "report" / "figures"
for d in (RESULTS, TABLES, FIGS):
    d.mkdir(parents=True, exist_ok=True)

SEED = 20261125          # every script derives its generators from this seed

# ---- nominal study point and ranges (ASSUMPTIONS; report section 2) ----
S_BETA = fields.photon_response_scaled("beta")      # 33.2 1/s per uSv/h, AB-100 Cs-137 scaled to 80 cm2
S_ALPHA = fields.photon_response_scaled("alpha")    # 0.158 1/s per uSv/h
S_BETA_RANGE = (15.0, 90.0)
B_OFF_BETA = 0.5                                    # floor beta-window rate not tracked by the reference, 1/s
B_OFF_ALPHA = 0.01
DOSE_RATES = [0.05, 0.1, 0.3, 1.0, 3.0, 10.0]       # uSv/h
DWELLS = [1.0, 2.0, 10.0, 30.0, 100.0]              # s: one pass, two passes, stationary recounts
K_CASES = [8.0, 13.0, 24.0, 50.0, 100.0]            # 1/s per Bq/cm2, see K_beta_by_basis
K_NOM = 24.0
U_REL_K = 0.15
K_REF = {"matched": 1.0, "ref3x": 0.3, "ref10x": 0.1}   # k = floor/reference photon count ratio
REL_UK = [0.0, 0.01, 0.03, 0.05, 0.10]
REL_UK_NOM = 0.03
U_B = 0.05
TU_RATIOS = [1.0, 4.0, 10.0]
SIGMAS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50]
T0 = 60.0                                            # uncompensated background count, s
ALPHA = BETA = 0.05
MISSION_ALLOWANCE = 0.05
LAYOUT = mc.SurveyLayout()
ALPHA_SIDAK = float(model.sidak_alpha(MISSION_ALLOWANCE, LAYOUT.n_cells))
LEVELS = {"goal": 0.20, "investigation": 0.30, "comparison": 0.40}
K_ALPHA_CASES = [1.5, 6.0, 13.0]
K_ALPHA_NOM = 6.0
U_REL_K_ALPHA = 0.35


def bgamma(dose_rate, s=S_BETA):
    return s * np.asarray(dose_rate, float)


def write_csv(name, header, rows):
    path = RESULTS / name
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return path


def fmt(x, sig=3):
    """Compact number formatting for tables."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    x = float(x)
    if np.isnan(x):
        return "n/a"
    if np.isinf(x):
        return "not reachable" if x > 0 else "-inf"
    if x == 0:
        return "0"
    ax = abs(x)
    if ax >= 1000 or ax < 1e-3:
        return f"{x:.{sig - 1}e}"
    digits = max(sig - 1 - int(np.floor(np.log10(ax))), 0)
    return f"{x:.{digits}f}"


def md_table(name, header, rows, sig=3):
    """Write a GitHub-markdown table fragment to results/tables/<name>.md."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(fmt(c, sig) for c in r) + " |")
    (TABLES / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_summary(**kv):
    """Merge pre-formatted scalar results into results/summary.json (used by the report template)."""
    path = RESULTS / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.update(kv)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def savefig(fig, name):
    fig.savefig(FIGS / name, dpi=130, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


# colour-blind-safe palette (Okabe-Ito), used consistently: same entity = same colour
C = {"unc": "#D55E00", "comp": "#0072B2", "comp2": "#009E73", "comp3": "#CC79A7",
     "level": "#555555", "ideal": "#000000", "alt": "#E69F00", "sky": "#56B4E9"}
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
                     "axes.spines.right": False, "legend.frameon": False, "figure.dpi": 100})
