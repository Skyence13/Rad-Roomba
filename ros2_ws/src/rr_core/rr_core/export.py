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

SOFTWARE = {"name": "rad-roomba ros2_ws", "version": "0.4.0-dev", "model": "analysis/radiometry/MODEL.md rev 2"}
COLORS = {"UNVISITED": (255, 255, 255), "ACCEPTABLE": (46, 139, 87), "INSUFFICIENT_SENSITIVITY": (240, 173, 78),
          "INVALID_DATA": (200, 60, 60), "BLOCKED": (120, 90, 160), "EXCLUDED": (90, 90, 90)}
BANNER = "SYNTHETIC CALIBRATION/PROFILE - field_use_approved: false - NOT FOR SURVEY OR RELEASE DECISIONS"


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
    for name in ("INSUFFICIENT_SENSITIVITY", "INVALID_DATA", "BLOCKED", "UNVISITED"):     # increasing priority
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
         '</defs>',
         f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/>']
    title = {"activity": "Activity estimate (Bq/cm2, signed; colour clips, data do not)",
             "coverage": "Coverage quality (patterns: unvisited / invalid / insufficient sensitivity / blocked / acceptable)"}[layer]
    o.append(f'<text x="20" y="16" font-size="13" font-weight="bold">{title}</text>')
    o.append(f'<text x="20" y="32">run {run.get("run_id", "")} | profile {proc.profile["id"]} rev {proc.profile.get("revision")} | '
             f'calibration {proc.cal.calibration_id} | method {proc.method["name"]} | map frame: origin door-threshold centre, +x to bulkhead, +y left</text>')
    if synthetic:
        o.append(f'<text x="20" y="48" fill="#b00020" font-weight="bold">{BANNER}</text>')
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
        if f.get("x_m") is None or f["kind"] == "SCAN_DETECTION":
            continue
        if f.get("footprint"):
            pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in f["footprint"])
            o.append(f'<polygon points="{pts}" fill="none" stroke="#000" stroke-width="1.5" stroke-dasharray="4 2"/>')
        o.append(f'<text x="{px(f["x_m"]) + 6:.1f}" y="{py(f["y_m"]) - 6:.1f}" font-weight="bold">{f["id"]}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def _diag_cols(d, lane):
    """alpha_short, alpha_idle_clears, imon_na of one lane from the gate's DIAG record ('' where no DIAG was read for the gate)."""
    if not d:
        return ["", "", "", ""]
    def pick(key):
        v = d.get(key)
        v = v[lane] if isinstance(v, list) and lane < len(v) else None
        return json.dumps(v) if isinstance(v, (list, dict)) else ("" if v is None else v)
    return [pick("alpha_short"), pick("alpha_idle_clears"), pick("imon_na"), "" if d.get("dac_writes") is None else d["dac_writes"]]


def export_survey(pipe, run: dict, out_dir, run_dir=None) -> dict:
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    proc = pipe.proc
    rows = proc.cells_table()
    summary = proc.coverage_summary()
    fua = bool(proc.profile.get("field_use_approved")) and bool(proc.cal.field_use_approved)
    run = dict(run, field_use_approved=fua)
    bounds = [g["bound_us"] for g in proc.gate_log if g["bound_us"] is not None]
    manifest = {
        "run_id": run.get("run_id"), "software": SOFTWARE, "field_use_approved": fua,
        "notice": None if fua else BANNER, "survey_method": proc.method,
        "trailer": {"length_m": proc.cfg.length_m, "width_m": proc.cfg.width_m, "id": run.get("trailer_id")},
        "frame": proc.cfg.as_dict()["frame"], "survey_config": _clean(proc.cfg.as_dict()),
        "profile": {"id": proc.profile["id"], "revision": proc.profile.get("revision"), "sha256": proc.profile.get("sha256"),
                    "unit": "Bq/cm2", "decision_class": proc.profile["decision_class"]},
        "calibration": proc.cal.summary(), "decision_parameters": _clean(proc.params),
        "review_queue": {"policy": proc.params["review_queue_policy"], "alpha_scan": proc.params["alpha_scan"],
                         "rule": "contract survey_methods.review_queue_policy; per cell also in cells.csv"},
        "assumptions": {"cov_FU": proc.cal.cov_FU_assumed, "spatial_response": "uniform top-hat (MODEL.md 5)",
                        "weighted_sum_variance": "exact_coefficients",
                        "cell_variance": "MODEL.md rev 4 sections 2 and 6: footprint weights (0.05 lattice) are coefficients of the individual gate counts; variance contribution w^2 lambda; reported low-count variance max(sum w^2 N, sum w^2 lambda0)",
                        "cell_decision": "linear-exact/combined+per-lane/0.8-0.2 (MODEL.md rev 4 section 6): combined statistic at 0.8 alpha or any contributing lane's own statistic at 0.2 alpha / m; thresholds and D# from the exact distribution (Gil-Pelaez / lattice, rr_core.linstat); D* and D# are those of the combined test; cell value and uncertainties are the inverse-null-variance combination; stationary recounts are the same rule with m = 1",
                        "evaluator": {"methods": ["linear-exact/gil-pelaez", "linear-exact/lattice"], "check": "tail at t* recomputed with half the quadrature step agrees to 1e-3 relative, else `no decision \u2014 evaluator check failed`",
                                      "cache_quantisation": {"u_null_log_step": proc.decider.u0_step, "live_time_step_s": proc.decider.t_step}},
                        "u0": "MODEL.md 3 R1 rev 4: window >= %g T_F excluding the gates under test (lane window, else four-lane pooled window); never a same-gate pool; otherwise `no decision \u2014 null reference unavailable`" % proc.cfg.u0_window_factor},
        "attachments": [{k: v for k, v in m.items() if k != "descriptor_b64"} for m in pipe.sessions],
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
    with open(out / "gates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["attachment", "sequence", "lane", "t0_us", "t1_us", "bound_us", "stage", "tag", "epoch",
                    "beta_counts", "floor_live_s", "alpha_counts", "ref_counts", "ref_live_s", "credited", "reasons",
                    "marks", "heater", "alpha_short", "alpha_idle_clears", "imon_na", "dac_writes"])
        for g in proc.gate_log:
            a_idx = proc.a_index(g["attachment"])
            for lane in g["lanes"]:
                c = proc._gate_counts.get((a_idx, g["sequence"], lane["id"]), ("", "", "", "", ""))
                w.writerow([g["attachment"], g["sequence"], lane["id"], repr(g["t0_us"]), repr(g["t1_us"]), repr(g["bound_us"]),
                            g["stage"] or "", g.get("tag") or "", g["pose"][3] if g["pose"] else "",
                            c[0], repr(c[1]), c[2], c[3], repr(c[4]), int(lane["credited"]), "|".join(lane["reasons"]),
                            "|".join(g.get("marks") or []), g.get("heater") or "",
                            *_diag_cols(proc.diag.get((a_idx, g["sequence"])), lane["id"])])
    _json(out / "gaps.json", _clean({"gaps": proc.gaps, "session_closes": pipe.closes, "link_notes": pipe.link_notes[:2000],
                                      "blocked_regions": proc.blocked_regions}))
    with open(out / "clock_fits.ndjson", "w") as f:
        for fit in pipe.fits:
            f.write(json.dumps(_clean(fit), sort_keys=True) + "\n")
    with open(out / "poses.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_us", "x_m", "y_m", "yaw_rad", "var_x", "var_y", "var_yaw", "quality", "credit", "epoch"])
        for p in pipe.traj.samples:
            w.writerow([p["t_us"], repr(p["x"]), repr(p["y"]), repr(p["yaw"]), repr(p["sxx"]), repr(p["syy"]),
                        repr(p["syaw"]), repr(p["q"]), int(p["credit"]), p["epoch"]])
    _json(out / "transforms.json", _clean({
        "chain": "map -> odom -> base_link -> head_mount -> seg{0..3}_aperture",
        "attachments": [{"attachment": m["attachment_session_id"], "mount_transform": m["mount_transform"],
                         "geometry_id": m.get("geometry_id"), "geometry_basis": m.get("geometry_basis"),
                         "lane_polygons_base_link_m": [p.round(5).tolist() for p in proc._geom[i][0]],
                         "eroded_m": proc.cfg.position_allowance_m} for i, m in enumerate(proc.sessions)],
        "robot_outline": run.get("robot_outline")}))
    _json(out / "calibration.json", proc.cal.record)
    _json(out / "profile.json", proc.profile)
    _json(out / "grid.json", {"origin_m": [proc.x0, proc.y0], "axes": "ix along +x (door to bulkhead), iy along +y (right wall to left wall)",
                              "cell_m": proc.cfg.cell_m, "nx": proc.ncx, "ny": proc.ncy, "sub_cell_m": proc.cfg.sub_res,
                              "bounds_m": [0.0, proc.cfg.length_m, proc.y0, -proc.y0], "unit": "Bq/cm2",
                              "note": "cell values are footprint averages (MODEL.md 6); cell size is the decision cell, not a resolution claim"})
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
             for r in rows if r["n_lane_gates"]]
    _json(out / "cells.geojson", {"type": "FeatureCollection", "crs_note": "LOCAL METRIC map frame (metres), not geographic",
                                   "features": feats}, indent=None)
    blocks = coverage_blocks(proc)
    rgb = np.zeros(blocks.shape + (3,), dtype=np.uint8)
    for i, name in enumerate(REASONS):
        rgb[blocks == i] = COLORS[name]
    write_png(out / "coverage.png", rgb[::-1])
    (out / "map_activity.svg").write_text(_svg(proc, run, "activity"))
    (out / "map_coverage.svg").write_text(_svg(proc, run, "coverage"))
    residuals = proc.residuals(min_area_m2=0.0)
    _json(out / "residuals.json", {"unit": "m (local map frame)", "count": len(residuals), "rectangles": residuals}, indent=None)
    _json(out / "flags.json", _clean(proc.flags))
    _json(out / "observations.json", _clean(proc.observations))
    ch = proc._decision_channel()
    decs = [d for d in proc.decisions[ch].values() if d.D is not None]
    suff = sum(1 for d in decs if proc.sensitivity_ok(d))
    by_reason = {}
    for q in residuals:
        by_reason[q["reason"]] = by_reason.get(q["reason"], 0.0) + q["area_m2"]
    t = io.StringIO()
    t.write("RAD ROOMBA FLOOR SURVEY SUMMARY\n")
    if not fua:
        t.write(BANNER + "\n")
    t.write(f"run {run.get('run_id')}  trailer {run.get('trailer_id')}  floor {proc.cfg.length_m:g} x {proc.cfg.width_m:g} m (floor only)\n")
    t.write(f"method {proc.method['name']}  profile {proc.profile['id']} rev {proc.profile.get('revision')}  calibration {proc.cal.calibration_id}\n")
    t.write(f"unit Bq/cm2  investigation level {proc.profile['investigation_level_Bq_cm2']}  detection goal < {proc.profile['detection_goal_Bq_cm2']}\n")
    t.write(f"review queue policy {proc.params['review_queue_policy']}\n")
    t.write(f"alpha_scan {proc.params['alpha_scan']:.3g}  alpha_recount {proc.params['alpha_recount']:.3g}  beta {proc.params['beta']:.3g}  decision cells {proc.params['n_decision_cells']}\n\n")
    t.write("WHERE THE ROBOT MEASURED\n")
    t.write(f"  valid exposure on {100 * summary['valid_exposure_fraction']:.1f} % of the target floor ({summary['target_area_m2']:.3f} m2)\n")
    for name in REASONS:
        t.write(f"  {name:<26s} {summary['areas_m2'][name]:8.4f} m2\n")
    t.write("\nHOW SENSITIVE IT WAS\n")
    if decs:
        dh = sorted(d.D_hash for d in decs if d.D_hash is not None and math.isfinite(d.D_hash))
        t.write(f"  decision cells with data {len(decs)}; sensitivity sufficient (D# < goal, envelope ok) {suff}\n")
        if dh:
            t.write(f"  D# median {dh[len(dh) // 2]:.3f}  best {dh[0]:.3f}  worst {dh[-1]:.3f} Bq/cm2 ({CLASS_OF_CHANNEL[ch]})\n")
    t.write(f"  time sync: max gate bound {manifest['time_sync']['max_gate_bound_us']} us (limit {pipe.interp.cfg.max_bound_us:g})\n")
    t.write("\nWHAT STILL NEEDS ATTENTION\n")
    for f in proc.flags:
        if f["kind"] == "SCAN_DETECTION":
            continue
        t.write(f"  {f['id']} {f['kind']} lane {f['source_lane']} D={f['D']:.3f} +/- {f['u_total']:.3f} Bq/cm2 at {f['location']['text']} status {f['status']}\n")
    n_scan = sum(1 for f in proc.flags if f["kind"] == "SCAN_DETECTION")
    t.write(f"  scan-stage detections below the investigation level awaiting a recount under the two-stage rule: {n_scan}\n")
    for obs in proc.observations.values():
        r = obs["result"]
        t.write(f"  scaler count {obs['id']} (flag {obs['flag']}, lane {obs['lane']}): {obs['outcome']}"
                + (f" D={r['D']:.3f} +/- {r['u_total']:.3f}, D*={r['D_star']:.3f}, D#={r['D_hash']:.3f}, T={r['T_F']:.1f} s\n" if r else "\n"))
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
    _json(out / "MANIFEST.sha256.json", {"files": fm})
    return {"dir": str(out), "files": fm, "manifest": manifest}


def compare_exports(a: dict, b: dict, ignore_prefix=("raw/",)) -> list:
    """Names of product files whose digests differ between two exports."""
    fa = {k: v["sha256"] for k, v in a["files"].items() if not k.startswith(ignore_prefix)}
    fb = {k: v["sha256"] for k, v in b["files"].items() if not k.startswith(ignore_prefix)}
    return sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))
