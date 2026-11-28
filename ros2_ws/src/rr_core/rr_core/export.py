"""Survey export (design 0.3 ch.2 "machine readable report" and ch.7).

Writes, deterministically (no wall-clock values inside the products):
    survey_manifest.json   run/head/calibration/profile/software/geometry ids, method, time sync
    gates.csv              parsed counts and live times per lane with qualification reasons
    gaps.json              sequence/time gap record and session closes
    clock_fits.ndjson      every clock fit (offset, drift, anchors, residuals, bound)
    poses.csv              trajectory with uncertainty, quality, epoch
    transforms.json        mount transform, lane polygons (base_link), robot outline
    calibration.json, profile.json
    grid.json + cells.csv  decision-cell grid (origin, axes, cell size, indexing) and values
    cells.geojson          GeoJSON-like FeatureCollection in LOCAL METRIC coordinates
    coverage.png           coverage-quality raster (one pixel per sub-cell block), legend in manifest
    map_activity.svg, map_coverage.svg   plan views with patterns, flags, banner
    residuals.json         unresolved floor rectangles with reason codes
    flags.json, observations.json
    summary.txt            human-readable summary
    raw/                   copy of the journal segments (original packet stream) when run_dir is given
    MANIFEST.sha256.json   file manifest with SHA-256

Synthetic calibration/profile => `field_use_approved: false` and a visible banner
in every human-readable product.  No ROS imports.
"""
from __future__ import annotations

import csv
import io
import json
import math
import shutil
import struct
import zlib
from pathlib import Path

import numpy as np

from .archive import file_manifest
from .processing import REASONS
from .profiles import CLASS_OF_CHANNEL

MODEL_REVISION = "analysis/radiometry/MODEL.md revision 5 (2026-11-27)"
COLORS = {"UNVISITED": (255, 255, 255), "ACCEPTABLE": (46, 139, 87), "INSUFFICIENT_SENSITIVITY": (240, 173, 78),
          "INVALID_DATA": (120, 60, 60), "BLOCKED": (120, 90, 160), "EXCLUDED": (90, 90, 90), "NO_DECISION": (170, 170, 200),
          "INCOMPLETE_COVERAGE": (250, 230, 150), "ALARM": (230, 0, 120), "ACQUISITION_GAP": (200, 200, 200)}
BANNER = "SYNTHETIC CALIBRATION/PROFILE - field_use_approved: false - NOT FOR SURVEY OR RELEASE DECISIONS"
MARKER = "synthetic \u2014 not for field use"


def software_identity() -> dict:
    """MODEL.md rev 5 section 8: version and source revision of every package, the model revision, the interpreter and the
    numerical libraries.  The source revision is a SHA-256 over the package's Python sources as they are on disk (the
    git commit is added when the tree is a git checkout; a dirty tree is stated)."""
    import hashlib
    import platform
    import subprocess
    import sys
    from pathlib import Path as _P
    src = _P(__file__).resolve().parents[2]
    pkgs = {}
    for d in sorted(p for p in src.iterdir() if p.is_dir() and (p / "package.xml").exists()):
        h = hashlib.sha256()
        for f in sorted(d.rglob("*.py")) + sorted(d.rglob("*.yaml")) + sorted(d.rglob("*.json")):
            if "__pycache__" in f.parts or "test" in f.relative_to(d).parts[:1]:
                continue
            h.update(str(f.relative_to(d)).encode() + b"\0" + f.read_bytes())
        ver = None
        try:
            import re as _re
            m = _re.search(r"<version>([^<]+)</version>", (d / "package.xml").read_text())
            ver = m.group(1) if m else None
        except OSError:
            pass
        pkgs[d.name] = {"version": ver, "source_sha256": h.hexdigest()}
    git = {"commit": None, "dirty": None}
    try:
        git["commit"] = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or None
        st = subprocess.run(["git", "-C", str(src), "status", "--porcelain", "--", "."], capture_output=True, text=True, timeout=5).stdout
        git["dirty"] = bool(st.strip()) if git["commit"] else None
    except (OSError, subprocess.SubprocessError):
        pass
    import scipy
    return {"name": "rad-roomba ros2_ws", "version": "0.4.0-dev", "model": MODEL_REVISION, "packages": pkgs, "git": git,
            "python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.machine()}


def _json(path: Path, obj, indent=1):
    path.write_text(json.dumps(_clean(obj), indent=indent, sort_keys=True, allow_nan=False) + "\n")


def _clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, np.integer, np.bool_)):
        return _clean(v.item())
    if isinstance(v, np.ndarray):
        return _clean(v.tolist())
    if isinstance(v, set):
        return sorted(v)
    return v


def write_png(path: Path, rgb: np.ndarray):
    """Minimal deterministic 8-bit RGB PNG writer (no external dependency)."""
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def coverage_blocks(proc, block: int = 4):
    """Coverage classes reduced to blocks of sub-cells WITHOUT hiding gaps: a block is
    ACCEPTABLE only if every target sub-cell in it is; otherwise it shows the worst class."""
    cls = proc.classify_subcells()
    ny, nx = (cls.shape[0] // block) * block, (cls.shape[1] // block) * block
    c = cls[:ny, :nx].reshape(ny // block, block, nx // block, block).transpose(0, 2, 1, 3).reshape(ny // block, nx // block, -1)
    out = np.full(c.shape[:2], REASONS.index("ACCEPTABLE"), dtype=np.uint8)
    for name in ("INSUFFICIENT_SENSITIVITY", "INCOMPLETE_COVERAGE", "NO_DECISION", "ACQUISITION_GAP", "INVALID_DATA", "BLOCKED",
                 "UNVISITED", "ALARM"):     # increasing priority: an alarm is never hidden
        out[(c == REASONS.index(name)).any(axis=2)] = REASONS.index(name)
    out[(c == REASONS.index("EXCLUDED")).all(axis=2)] = REASONS.index("EXCLUDED")
    return out


def activity_color(D, level):
    """Documented scale: blue (<= 0) -> white (0) -> red (>= investigation level). Colour clips; data do not."""
    if D is None:
        return None
    f = max(-1.0, min(1.0, D / level))
    if f >= 0:
        return (255, int(255 * (1 - f)), int(255 * (1 - f)))
    return (int(255 * (1 + 0.6 * f)), int(255 * (1 + 0.6 * f)), 255)


def _svg(proc, run, layer: str) -> str:
    cfg = proc.cfg
    s = 400.0                                   # px per metre
    W, H = cfg.length_m * s + 40, cfg.width_m * s + 110
    px = lambda x: 20 + x * s
    py = lambda y: 60 + (cfg.width_m / 2 - y) * s
    synthetic = not run.get("field_use_approved", False)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" font-family="sans-serif" font-size="11">',
         '<defs>'
         '<pattern id="p-UNVISITED" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#fff"/><path d="M0 8L8 0" stroke="#888" stroke-width="1"/></pattern>'
         '<pattern id="p-INVALID_DATA" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#f6d5d5"/><path d="M0 0L8 8M0 8L8 0" stroke="#c83c3c" stroke-width="1"/></pattern>'
         '<pattern id="p-INSUFFICIENT_SENSITIVITY" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#fdebc8"/><circle cx="3" cy="3" r="1.2" fill="#b9770e"/></pattern>'
         '<pattern id="p-BLOCKED" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#e4dcf0"/><path d="M0 4H8" stroke="#785aa0" stroke-width="2"/></pattern>'
         '<pattern id="p-EXCLUDED" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#5a5a5a"/></pattern>'
         '<pattern id="p-ACCEPTABLE" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#2e8b57"/></pattern>'
         '<pattern id="p-NO_DECISION" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#e6e6f2"/><path d="M0 4H8M4 0V8" stroke="#6a6aa0" stroke-width="1"/></pattern>'
         '<pattern id="p-INCOMPLETE_COVERAGE" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#faeec0"/><path d="M0 0L8 8" stroke="#a08020" stroke-width="1"/></pattern>'
         '<pattern id="p-ALARM" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#e60078"/><path d="M0 8L8 0" stroke="#000" stroke-width="1.5"/></pattern>'
         '<pattern id="p-ACQUISITION_GAP" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#ddd"/><circle cx="4" cy="4" r="2" fill="#666"/></pattern>'
         '</defs>',
         f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/>']
    title = {"activity": "Activity estimate (Bq/cm2, signed; colour clips, data do not)",
             "coverage": "Cell status (patterns: ALARM / no decision / incomplete coverage / insufficient sensitivity / invalid / gap / blocked / unvisited; solid green = ACCEPTABLE only)"}[layer]
    o.append(f'<text x="20" y="16" font-size="13" font-weight="bold">{title}</text>')
    o.append(f'<text x="20" y="32">run {run.get("run_id", "")} | profile {proc.profile["id"]} rev {proc.profile.get("revision")} | '
             f'calibration {proc.cal.calibration_id} | method {proc.method["name"]} | map frame: origin door-threshold centre, +x to bulkhead, +y left</text>')
    if synthetic:
        o.append(f'<text x="20" y="48" fill="#b00020" font-weight="bold">{BANNER} ({MARKER})</text>')
    if layer == "coverage":
        blocks = coverage_blocks(proc)
        b = proc.cfg.sub_res * 4
        for i, name in enumerate(REASONS):
            for iy in range(blocks.shape[0]):
                row = np.flatnonzero(np.diff(np.concatenate(([0], (blocks[iy] == i).view(np.int8), [0]))))
                for a, e in zip(row[::2], row[1::2]):
                    o.append(f'<rect x="{px(a * b):.1f}" y="{py(proc.y0 + (iy + 1) * b):.1f}" width="{(e - a) * b * s:.1f}" height="{b * s:.1f}" fill="url(#p-{name})"/>')
    else:
        ch = proc._decision_channel()
        level = proc.profile["investigation_level_Bq_cm2"]
        c = cfg.cell_m
        for (cy, cx), d in sorted(proc.decisions[ch].items()):
            col = activity_color(d.D, level)
            if col is None:
                continue
            x, y = proc.x0 + cx * c, proc.y0 + cy * c
            o.append(f'<rect x="{px(x):.1f}" y="{py(y + c):.1f}" width="{c * s:.1f}" height="{c * s:.1f}" fill="rgb{col}" stroke="#ddd" stroke-width="0.3"/>')
    o.append(f'<rect x="{px(0):.1f}" y="{py(cfg.width_m / 2):.1f}" width="{cfg.length_m * s:.1f}" height="{cfg.width_m * s:.1f}" fill="none" stroke="#000" stroke-width="2"/>')
    o.append(f'<text x="{px(0):.1f}" y="{py(-cfg.width_m / 2) + 14:.1f}">DOOR (x = 0)</text>')
    o.append(f'<text x="{px(cfg.length_m) - 90:.1f}" y="{py(-cfg.width_m / 2) + 14:.1f}">BULKHEAD (x = {cfg.length_m:g} m)</text>')
    o.append(f'<line x1="{px(0.1):.1f}" y1="{py(-cfg.width_m / 2) + 26:.1f}" x2="{px(0.6):.1f}" y2="{py(-cfg.width_m / 2) + 26:.1f}" stroke="#000" stroke-width="2"/>'
             f'<text x="{px(0.1):.1f}" y="{py(-cfg.width_m / 2) + 40:.1f}">0.5 m | +y = {cfg.wall_names[0]} (top)</text>')
    for f in proc.flags:
        if f.get("x_m") is None or (f["kind"] == "SCAN_DETECTION" and f.get("recorded") != "recorded alarm"):
            continue
        if f.get("footprint"):
            pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in f["footprint"])
            o.append(f'<polygon points="{pts}" fill="none" stroke="#000" stroke-width="1.5" stroke-dasharray="4 2"/>')
        o.append(f'<text x="{px(f["x_m"]) + 6:.1f}" y="{py(f["y_m"]) - 6:.1f}" font-weight="bold">{f["id"]}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def _f3(v):
    return "n/a (no decision)" if v is None else (f"{v:.3f}" if math.isfinite(v) else "inf")


def _diag_cols(d, lane):
    """alpha_short, alpha_idle_clears, imon_na of one lane from the gate's DIAG record ('' where no DIAG was read for the gate)."""
    if not d:
        return ["", "", "", ""]
    def pick(key):
        v = d.get(key)
        v = v[lane] if isinstance(v, list) and lane < len(v) else None
        return json.dumps(v) if isinstance(v, (list, dict)) else ("" if v is None else v)
    return [pick("alpha_short"), pick("alpha_idle_clears"), pick("imon_na"), "" if d.get("dac_writes") is None else d["dac_writes"]]


EXPORT_README = """RAD ROOMBA SURVEY EXPORT - HOW TO READ IT (and what not to conclude)

Every file of this export carries the run id, the calibration identifier(s) and, while field_use_approved is false, the
marker "synthetic — not for field use".  Values are calculated / simulated with SYNTHETIC coefficients.

Cell results.  cells.csv, cells.geojson and flags.json carry the RECORDED result of each decision cell: evaluated once, after
the survey, from the complete attachment record (MODEL.md rev 5 section 3).  Columns prefixed `provisional.` are the live
values shown during the survey; they are labelled provisional and are never the result.  `alarm_bookkeeping` states whether a
live alarm was confirmed ("recorded alarm"), not confirmed ("provisional alarm not confirmed") or found only at the final
evaluation ("alarm found at final evaluation"; also listed under `revisit` in residuals.json).

Status (column `status`, precedence ALARM > NO DECISION > INCOMPLETE COVERAGE > SENSITIVITY INSUFFICIENT > ACCEPTABLE):
  ALARM                     the recorded decision flagged the cell, or a gate over it saturated by rate - whatever its coverage.
  NO DECISION               no decision could be made (reason in status_reason), e.g. no null reference, evaluator check failed,
                            no calibration bound to this head and setup.  Not "clean".
  INCOMPLETE COVERAGE       coverage below the profile minimum, no credited gate, or a gate over the cell excluded for a fault.
  SENSITIVITY INSUFFICIENT  D# above the detection goal, calibration envelope not met, or a reference gradient.
  ACCEPTABLE                none of the above: no flag, coverage >= minimum, D# <= goal, envelope met, no fault exclusion.
ACCEPTABLE is a statement about the measurement (sensitivity and coverage), not a release decision.

Do NOT conclude (data-path review section 7 Q8; each item is either removed by the format or stated here):
 1. that green floor is clean: green = status ACCEPTABLE only; an alarming cell is never green (format changed).
 2. that a high-D cell without a flag exists unnoticed: an alarm is never suppressed by coverage (format changed).
 3. that D is the mean activity of the 100 cm2 cell: D is a FOOTPRINT AVERAGE; activity confined to the cell is reported
    as sum(w^2 t)/sum(w t) of its value (column `*.footprint_dilution`, per lane), and D# assumes activity covering every
    contributing footprint (for cell-confined activity the limit is larger by 1/footprint_dilution).
 4. that averaging N cells reduces u_total by sqrt(N): only u_stat averages down; u_cal_lane, u_cal_common_k and u_cal_K
    (exported separately, standard uncertainties k = 1, Bq/cm2) are common to the cells of a lane / of all lanes.
 5. that `no decision` floor was undecidable from the data because of when it was evaluated: the recorded result is
    independent of the evaluation schedule (format changed); see status_reason for the real cause.
 6. that D* and D# hold at the mission alpha: they hold at alpha_combined = 0.8 alpha_scan (columns alpha_combined,
    alpha_lane) for the scan stage; the two-stage detection probability is lower than 1 - beta.
 7. that INVALID_DATA is only an instrument problem: a rate saturation is reported as ALARM (rate above counting range),
    a forced-clear saturation as INVALID_DATA (format changed).
 8. that a credited footprint is good to 10 mm by measurement: the erosion is the localiser's credited 2 sigma (a model
    with an ASSUMED wheel-scale uncertainty, manifest `position_credit`), simulated only.
 9. that one calibration was applied to every head: each attachment is processed with its own bound calibration
    (manifest `attachments[].calibration`); a DEMONSTRATION binding means the identity was NOT checked.
10. that re-running the archive gives other numbers: tools/recompute_cell.py recomputes a named cell from the archive,
    calibration and profile.
11. that UNVISITED floor was not driven over: floor swept during missing gates is ACQUISITION_GAP.
12. that field_use_approved true implies more than: approved calibration and profile, every attachment in SURVEY mode
    with AS_BUILT geometry and a checked (not demonstration) calibration binding.
Also: T_F is the weighted floor live time summed over lanes (s), not a dwell time; uncertainties are k = 1.
"""


def _att_cal_ids(proc, cells=None):
    return sorted({(a.get("calibration_id") or "NONE") for a in proc.att}) or ["NONE"]


def export_survey(pipe, run: dict, out_dir, run_dir=None) -> dict:
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    proc = pipe.proc
    rows = proc.cells_table()
    summary = proc.coverage_summary()
    att_ok = bool(proc.att) and all(
        a["calibration"] is not None and a["calibration"].field_use_approved and not (a["binding"] or {}).get("demonstration")
        and m.get("mode") == "SURVEY" and m.get("geometry_basis") == "AS_BUILT" for a, m in zip(proc.att, proc.sessions))
    fua = bool(proc.profile.get("field_use_approved")) and att_ok      # review M8
    run = dict(run, field_use_approved=fua)
    marker = "" if fua else MARKER
    run_id = run.get("run_id")
    cal_ids = "|".join(_att_cal_ids(proc))
    tag = {"run_id": run_id, "calibration_ids": cal_ids, "field_use_approved": fua, "marker": marker}
    demo = any((a["binding"] or {}).get("demonstration") for a in proc.att)
    bounds = [g["bound_us"] for g in proc.gate_log if g["bound_us"] is not None]
    from . import unull
    from .processing import FOOTPRINT_MODEL, FOOTPRINT_MODEL_BEFORE, STATUS_PRECEDENCE
    manifest = {
        "run_id": run_id, "software": software_identity(), "model_revision": MODEL_REVISION, "field_use_approved": fua,
        "marker": marker, "notice": None if fua else BANNER,
        "calibration_binding_notice": "DEMONSTRATION calibration binding: head identity NOT checked" if demo else None,
        "field_use_rule": "profile approved AND every attachment: calibration approved, binding identity checked (not demonstration), mode SURVEY, geometry AS_BUILT",
        "survey_method": proc.method,
        "trailer": {"length_m": proc.cfg.length_m, "width_m": proc.cfg.width_m, "id": run.get("trailer_id")},
        "frame": proc.cfg.as_dict()["frame"], "survey_config": _clean(proc.cfg.as_dict()),
        "profile": {"id": proc.profile["id"], "revision": proc.profile.get("revision"), "sha256": proc.profile.get("sha256"),
                    "unit": "Bq/cm2", "decision_class": proc.profile["decision_class"],
                    "minimum_cell_coverage": proc.min_cell_coverage()},
        "calibration_mission": proc.cal.summary() if proc.cal is not None else None,
        "decision_parameters": _clean(proc.params),
        "review_queue": {"policy": proc.params["review_queue_policy"], "alpha_scan": proc.params["alpha_scan"],
                         "rule": "contract survey_methods.review_queue_policy; per cell also in cells.csv; RATE_SATURATION flags are queued under every policy"},
        "evaluation": {"recorded": "once per cell from the complete attachment record, members and reference windows sorted, a fresh exact evaluator (no cache quantisation) - independent of gate arrival order and of the live schedule (MODEL.md rev 5 section 3)",
                       "provisional": "live evaluations on the reference data received so far, threshold cache quantised (U0 0.25 % log grid, window count to 1, live time 1 ms); labelled provisional; drive the live display and the review queue during the survey only",
                       "decision_class_only": "only the profile's decision class is evaluated as a decision (the other class is not exported as one)"},
        "status": {"precedence": list(STATUS_PRECEDENCE), "rate_saturation": "GATESTAT sc bit 2 (floor live < 50 %) without forced clears -> ALARM - rate above counting range; forced clears -> detector fault (gate removed); no GATESTAT -> treated as possible rate alarm"},
        "footprint_model": FOOTPRINT_MODEL, "footprint_model_before_2026_11_28": FOOTPRINT_MODEL_BEFORE,
        "assumptions": {"cov_FU": proc.cal.cov_FU_assumed if proc.cal is not None else None, "spatial_response": "uniform top-hat (MODEL.md 5)",
                        "weighted_sum_variance": "exact_coefficients",
                        "cell_decision": "linear-exact/combined+per-lane/0.8-0.2 (MODEL.md rev 5 section 6); predictive threshold over 12 posterior nodes of each lane's U_null sub-window (Gamma(N + 1/2, scale 1/T)); lanes of different attachments are separate terms, each with its own bound calibration; common k terms fully correlated (diagonal parts at the nodes, cross terms at the point values)",
                        "evaluator": {"method": "linear-exact/gil-pelaez/predictive-U(N=...)", "check": "tail at t* recomputed with half the quadrature step agrees to 1e-3 relative, else `no decision — evaluator check failed`"},
                        "u0": {"rule": "MODEL.md rev 5 section 3: two sub-windows of >= N_min reference counts nearest to the dwell (before / after, else both on one side), larger mean; lane window unless it spans > 2 m, then the ratio-scaled four-lane pool; gradient guard 2 %; recounts: other three lanes during the recount",
                               "n_min_table": unull.N_MIN_TABLE, "max_span_m": unull.MAX_SPAN_M, "gradient_limit": unull.GRADIENT_LIMIT,
                               "implementation_choices": unull.IMPL_NOTES},
                        "uncertainty_components": "per cell: u_stat (counting), u_cal_lane (lane-specific k, b terms), u_cal_common_k (spectral part of k, common to all lanes), u_cal_K (|D| u_rel(K)); standard (k = 1), Bq/cm2; only u_stat averages down"},
        "position_credit": run.get("position_credit"),
        "archive_records": {"head": "every head request and reply as received (T/R), control entries (C)", "pose_inputs": "chassis odometry/IMU samples as received with chassis and host time stamps and the chassis clock bound (K entries)", "range_data": "LiDAR scans with time stamps (S entries, ranges in mm uint16)", "poses": "the pose used for each gate with its covariance, credit flag and reasons (P entries)"},
        "attachments": [{**{k: v for k, v in m.items() if k not in ("descriptor_b64", "head_status_at_open")},
                         "head_status_at_open": m.get("head_status_at_open"),
                         "processing_calibration": a["calibration_id"], "refused": a["refused"], "standoff": a["standoff"]}
                        for m, a in zip(pipe.sessions, proc.att)],
        "calibrations": {c.calibration_id: c.summary() for c in proc.cal_by_id.values()},
        "missing_gates": getattr(proc, "missing_gates", []),
        "head_health": pipe.head_health[-50:],
        "session_closes": [{k: c[k] for k in ("attachment", "reason", "last_seq", "t_us")} for c in pipe.closes],
        "trajectory_epochs": pipe.traj.epochs, "epoch_log": pipe.epoch_log,
        "time_sync": {"limit_us": pipe.interp.cfg.max_bound_us, "fits": len(pipe.fits),
                      "max_gate_bound_us": max(bounds) if bounds else None,
                      "median_gate_bound_us": float(np.median(bounds)) if bounds else None},
        "link_stats": pipe.interp.stats, "processing_stats": proc.stats,
        "coverage": summary, "scope": "floor only; walls, door and other surfaces are not surveyed",
        "coverage_png_legend": {name: list(COLORS[name]) for name in REASONS},
        "evidence_class": "simulated" if run.get("simulated", True) else "pending",
    }
    _json(out / "survey_manifest.json", _clean(manifest))
    (out / "README.txt").write_text((BANNER + "\n" + MARKER + "\n\n" if not fua else "") + f"run {run_id}  calibration(s) {cal_ids}\n\n" + EXPORT_README)
    head = list(tag)
    with open(out / "gates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(head + ["attachment", "sequence", "lane", "t0_us", "t1_us", "bound_us", "stage", "tag", "epoch", "erosion_m", "speed_mps",
                    "beta_counts", "floor_live_s", "alpha_counts", "ref_counts", "ref_live_s", "credited", "reasons",
                    "marks", "heater", "alpha_short", "alpha_idle_clears", "imon_na", "dac_writes",
                    "gs_alpha_short", "gs_alpha_ambig", "gs_floor_reject", "gs_idle_clears", "gs_floor_forced", "gs_ref_forced",
                    "gs_sat_cause", "gs_floor_live_permille", "gs_ref_live_permille", "gs_gross_alpha", "gs_gross_beta", "gs_gross_ref",
                    "gate_calibration_id"])
        for g in proc.gate_log:
            a_idx = proc.a_index(g["attachment"])
            gs = proc.gatestat.get((a_idx, g["sequence"])) or {}
            for lane in g["lanes"]:
                c = proc._gate_counts.get((a_idx, g["sequence"], lane["id"]), ("", "", "", "", ""))
                gsv = [("" if not gs else (gs.get(k) or [""] * 4)[lane["id"]]) for k in ("as", "am", "fr", "ic", "ff", "rf", "sc", "lf", "lr", "ga", "gb", "gr")]
                w.writerow([run_id, cal_ids, fua, marker, g["attachment"], g["sequence"], lane["id"], repr(g["t0_us"]), repr(g["t1_us"]), repr(g["bound_us"]),
                            g["stage"] or "", g.get("tag") or "", g["pose"][3] if g["pose"] else "",
                            "" if lane.get("erosion_m") is None else repr(lane["erosion_m"]), "" if g.get("speed_mps") is None else repr(g["speed_mps"]),
                            c[0], repr(c[1]), c[2], c[3], repr(c[4]), int(lane["credited"]), "|".join(lane["reasons"]),
                            "|".join(g.get("marks") or []), g.get("heater") or "",
                            *_diag_cols(proc.diag.get((a_idx, g["sequence"])), lane["id"]), *gsv, proc.att[a_idx]["calibration_id"] or ""])
    with open(out / "cell_members.csv", "w", newline="") as f:
        w = csv.writer(f)
        mem = proc.cell_members_table()
        w.writerow(head + ["ix", "iy", "attachment", "sequence", "lane", "weight", "erosion_m"])
        for r in mem:
            w.writerow([run_id, cal_ids, fua, marker, r["ix"], r["iy"], r["attachment"], r["sequence"], r["lane"], repr(r["weight"]),
                        "" if r["erosion_m"] is None else repr(r["erosion_m"])])
    _json(out / "gaps.json", _clean({**tag, "gaps": proc.gaps, "missing_gates": getattr(proc, "missing_gates", []), "session_closes": pipe.closes,
                                      "link_notes": pipe.link_notes[:2000], "blocked_regions": proc.blocked_regions}))
    with open(out / "clock_fits.ndjson", "w") as f:
        f.write(json.dumps(_clean(tag), sort_keys=True) + "\n")
        for fit in pipe.fits:
            f.write(json.dumps(_clean(fit), sort_keys=True) + "\n")
    with open(out / "poses.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(head + ["t_us", "x_m", "y_m", "yaw_rad", "var_x", "var_y", "var_yaw", "quality", "credit", "epoch", "time_bound_us", "correction_m", "no_credit_reasons"])
        for p in pipe.traj.samples:
            w.writerow([run_id, cal_ids, fua, marker, p["t_us"], repr(p["x"]), repr(p["y"]), repr(p["yaw"]), repr(p["sxx"]), repr(p["syy"]),
                        repr(p["syaw"]), repr(p["q"]), int(p["credit"]), p["epoch"], "" if p.get("tb_us") is None else repr(p["tb_us"]),
                        repr(p.get("corr_m", 0.0)), p.get("nocredit", "")])
    _json(out / "transforms.json", _clean({**tag,
        "chain": "map -> odom -> base_link -> head_mount -> seg{0..3}_aperture",
        "attachments": [{"attachment": m["attachment_session_id"], "mount_transform": m["mount_transform"],
                         "geometry_id": m.get("geometry_id"), "geometry_basis": m.get("geometry_basis"),
                         "lane_polygons_base_link_m": [p.round(5).tolist() for p in proc._geom[i][0]],
                         "erosion": "per gate: credited 2 sigma (gates.csv erosion_m)", "max_erosion_m": proc.cfg.position_allowance_m}
                        for i, m in enumerate(proc.sessions)],
        "robot_outline": run.get("robot_outline")}))
    for cid, c in proc.cal_by_id.items():
        if cid == (proc.cal.calibration_id if proc.cal else None):
            _json(out / "calibration.json", dict(c.record, export_marker=marker))
        else:
            _json(out / f"calibration_{cid}.json", dict(c.record, export_marker=marker))
    _json(out / "profile.json", dict(proc.profile, export_marker=marker))
    _json(out / "grid.json", {**tag, "origin_m": [proc.x0, proc.y0], "axes": "ix along +x (door to bulkhead), iy along +y (right wall to left wall)",
                              "cell_m": proc.cfg.cell_m, "nx": proc.ncx, "ny": proc.ncy, "sub_cell_m": proc.cfg.sub_res,
                              "bounds_m": [0.0, proc.cfg.length_m, proc.y0, -proc.y0], "unit": "Bq/cm2",
                              "note": "cell values are footprint averages (MODEL.md 6); cell size is the decision cell, not a resolution claim"})
    rows = [dict(tag, **r) for r in rows]
    cols = list(rows[0].keys())
    with open(out / "cells.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else (repr(r[c]) if isinstance(r[c], float) else r[c]) for c in cols])
    c = proc.cfg.cell_m
    feats = [{"type": "Feature", "properties": _clean(r),
              "geometry": {"type": "Polygon", "coordinates": [[[round(r["x_m"] - c / 2, 4), round(r["y_m"] - c / 2, 4)],
                                                               [round(r["x_m"] + c / 2, 4), round(r["y_m"] - c / 2, 4)],
                                                               [round(r["x_m"] + c / 2, 4), round(r["y_m"] + c / 2, 4)],
                                                               [round(r["x_m"] - c / 2, 4), round(r["y_m"] + c / 2, 4)],
                                                               [round(r["x_m"] - c / 2, 4), round(r["y_m"] - c / 2, 4)]]]}}
             for r in rows if r["n_lane_gates"] or r["status"] == "ALARM"]
    _json(out / "cells.geojson", {"type": "FeatureCollection", "crs_note": "LOCAL METRIC map frame (metres), not geographic",
                                   **tag, "features": feats}, indent=None)
    blocks = coverage_blocks(proc)
    rgb = np.zeros(blocks.shape + (3,), dtype=np.uint8)
    for i, name in enumerate(REASONS):
        rgb[blocks == i] = COLORS[name]
    write_png(out / "coverage.png", rgb[::-1])
    (out / "map_activity.svg").write_text(_svg(proc, run, "activity"))
    (out / "map_coverage.svg").write_text(_svg(proc, run, "coverage"))
    residuals = proc.residuals(min_area_m2=0.0)
    _json(out / "residuals.json", {**tag, "unit": "m (local map frame)", "count": len(residuals), "rectangles": residuals,
                                    "revisit": proc.revisit}, indent=None)
    _json(out / "flags.json", _clean({**tag, "flags": proc.flags}))
    _json(out / "observations.json", _clean({**tag, "observations": proc.observations}))
    ch = proc._decision_channel()
    decs = [d for d in proc.decisions[ch].values() if d.D is not None]
    from collections import Counter
    st_count = Counter(r["status"] for r in rows if r["n_lane_gates"] or r["status"] == "ALARM")
    book = Counter(r["alarm_bookkeeping"] for r in rows if r["alarm_bookkeeping"])
    by_reason = {}
    for q in residuals:
        by_reason[q["reason"]] = by_reason.get(q["reason"], 0.0) + q["area_m2"]
    t = io.StringIO()
    t.write("RAD ROOMBA FLOOR SURVEY SUMMARY\n")
    if not fua:
        t.write(BANNER + "\n" + MARKER + "\n")
    if demo:
        t.write("DEMONSTRATION CALIBRATION BINDING - head identity NOT checked\n")
    t.write(f"run {run_id}  trailer {run.get('trailer_id')}  floor {proc.cfg.length_m:g} x {proc.cfg.width_m:g} m (floor only)\n")
    t.write(f"method {proc.method['name']}  profile {proc.profile['id']} rev {proc.profile.get('revision')}  calibration(s) {cal_ids}\n")
    t.write(f"model {MODEL_REVISION}; recorded results (evaluated once on the complete record); README.txt says how to read them\n")
    t.write(f"unit Bq/cm2  investigation level {proc.profile['investigation_level_Bq_cm2']}  detection goal < {proc.profile['detection_goal_Bq_cm2']}\n")
    t.write(f"review queue policy {proc.params['review_queue_policy']}\n")
    t.write(f"alpha_scan {proc.params['alpha_scan']:.3g}  alpha_recount {proc.params['alpha_recount']:.3g}  beta {proc.params['beta']:.3g}  decision cells {proc.params['n_decision_cells']}\n\n")
    t.write("WHERE THE ROBOT MEASURED\n")
    t.write(f"  valid exposure on {100 * summary['valid_exposure_fraction']:.1f} % of the target floor ({summary['target_area_m2']:.3f} m2)\n")
    for name in REASONS:
        t.write(f"  {name:<26s} {summary['areas_m2'][name]:8.4f} m2\n")
    t.write("\nCELL STATUS (cells with data)\n")
    for k in STATUS_PRECEDENCE:
        t.write(f"  {k:<26s} {st_count.get(k, 0)}\n")
    for k, v in sorted(book.items()):
        t.write(f"  {k}: {v}\n")
    t.write("\nHOW SENSITIVE IT WAS\n")
    if decs:
        dh = sorted(d.D_hash for d in decs if d.D_hash is not None and math.isfinite(d.D_hash))
        t.write(f"  decision cells with data {len(decs)}; ACCEPTABLE {st_count.get('ACCEPTABLE', 0)}\n")
        if dh:
            t.write(f"  D# median {dh[len(dh) // 2]:.3f}  best {dh[0]:.3f}  worst {dh[-1]:.3f} Bq/cm2 ({CLASS_OF_CHANNEL[ch]}, alpha_combined {0.8 * proc.params['alpha_scan']:.3g})\n")
    t.write(f"  time sync: max gate bound {manifest['time_sync']['max_gate_bound_us']} us (limit {pipe.interp.cfg.max_bound_us:g})\n")
    t.write("\nWHAT STILL NEEDS ATTENTION\n")
    for f in proc.flags:
        if f["kind"] == "SCAN_DETECTION" and f.get("recorded") != "recorded alarm":
            continue
        dtxt = "" if f.get("D") is None else f" D={f['D']:.3f} +/- {f['u_total']:.3f} Bq/cm2"
        t.write(f"  {f['id']} {f['kind']} lane {f.get('source_lane')}{dtxt} at {f.get('location', {}).get('text')} [{f.get('recorded', 'provisional')}]\n")
    n_scan = sum(1 for f in proc.flags if f["kind"] == "SCAN_DETECTION")
    t.write(f"  scan-stage detections below the investigation level awaiting a recount under the two-stage rule: {n_scan}\n")
    for obs in proc.observations.values():
        r = obs["result"]
        t.write(f"  scaler count {obs['id']} (flag {obs['flag']}, lane {obs['lane']}): {obs['outcome']}"
                + (f" D={r['D']:.3f} +/- {r['u_total']:.3f}, D*={_f3(r['D_star'])}, D#={_f3(r['D_hash'])}, T={r['T_F']:.1f} s"
                                                         + ("" if r.get("status", "OK") == "OK" else f" [{r['status']}]") + "\n" if r else "\n"))
    for reason, area in sorted(by_reason.items()):
        t.write(f"  unresolved floor {reason}: {area:.4f} m2 (rectangles in residuals.json)\n")
    for gap in proc.gaps:
        t.write(f"  acquisition gap {gap['kind']} attachment {gap['attachment']} missing {gap.get('first_missing')}..{gap.get('last_missing')}\n")
    t.write("\nA release-status entry is a radiation-protection decision under the site procedure; this report is not one.\n")
    (out / "summary.txt").write_text(t.getvalue())
    if run_dir is not None:
        raw = out / "raw"
        raw.mkdir()
        for p in sorted((Path(run_dir) / "journal").glob("*")):
            if p.suffix in (".seg", ".ndjson", ".part"):
                shutil.copyfile(p, raw / p.name)
        if (Path(run_dir) / "run.json").exists():
            shutil.copyfile(Path(run_dir) / "run.json", raw / "run.json")
    fm = file_manifest(out)
    _json(out / "MANIFEST.sha256.json", {**tag, "files": fm})
    return {"dir": str(out), "files": fm, "manifest": manifest}


def compare_exports(a: dict, b: dict, ignore_prefix=("raw/",)) -> list:
    """Names of product files whose digests differ between two exports."""
    fa = {k: v["sha256"] for k, v in a["files"].items() if not k.startswith(ignore_prefix)}
    fb = {k: v["sha256"] for k, v in b["files"].items() if not k.startswith(ignore_prefix)}
    return sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))
