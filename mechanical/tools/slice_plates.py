#!/usr/bin/env python3
"""Plate manifest -> Bambu Studio project .3mf per plate -> headless slice -> per-plate JSON/CSV summary.

Usage (repository root; Python 3 with PyYAML, docker with the image `linuxserver/bambustudio:latest`):

    python3 mechanical/tools/slice_plates.py mechanical/prototype_x1c/plates.yaml            # all plates
    python3 mechanical/tools/slice_plates.py MANIFEST --plates P01,P07 --out DIR --no-slice   # project files only
    python3 mechanical/tools/slice_plates.py MANIFEST --precheck-only                         # no docker at all

For every plate the tool
  1. loads the listed meshes (binary/ASCII STL, already in print orientation unless `orient` is given), applies
     `orient` (Euler X, Y, Z deg), `rotation_z`, drops the part onto z = 0 and puts its bounding-box centre at
     `position` (bed mm, origin = front-left bed corner).  Parts without `position` are shelf-packed by the tool.
  2. pre-checks (tool-side, before the slicer): inside the 256 x 256 x 250 mm X1C volume with the edge margin, clear of
     the 18 x 28 mm front-left exclusion area, bounding boxes not overlapping, mesh watertight.
  3. writes `<id>.model.3mf` (plain 3MF, parts at the manifest positions) and flattened copies of the STOCK Bambu
     presets shipped in the image (the CLI does not resolve the `inherits` chain of system presets by itself), with
     the manifest `overrides` applied.
  4. runs Bambu Studio headless in the container: (a) `--export-3mf <id>.3mf` (project file that opens in Bambu
     Studio), (b) `--slice 0 --export-3mf <id>.gcode.3mf`.
  5. parses `result.json`, `Metadata/slice_info.config` and the G-code header -> `<id>.summary.json`, and finally
     writes `slice_summary.json` + `slice_summary.csv` for the whole manifest.

Nothing is reported as sliced unless the CLI returned 0 AND the .gcode.3mf contains G-code.  Exit status: 0 if every
selected plate sliced (or, with --no-slice / --precheck-only, passed that stage), 1 otherwise.
The manifest schema is documented in mechanical/tools/README.md (schema id `rr-plates/1`).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mesh_io as M  # noqa: E402

IMAGE = "linuxserver/bambustudio:latest"
BIN = "/opt/bambustudio/bin/bambu-studio"
PROFILES_IN_IMAGE = "/opt/bambustudio/resources/profiles"
DEFAULT_PRINTER = {"model": "Bambu Lab X1 Carbon", "nozzle": 0.4, "machine_profile": "Bambu Lab X1 Carbon 0.4 nozzle",
                   "bed": [256.0, 256.0, 250.0], "exclude_area": [0.0, 0.0, 18.0, 28.0], "edge_margin": 3.0}
DEFAULTS = {"plate_type": "Textured PEI Plate", "process": "0.20mm Standard @BBL X1C", "part_gap": 6.0}
PLATE_TYPES = ("Cool Plate", "Engineering Plate", "High Temp Plate", "Textured PEI Plate", "Supertack Plate")
NOISE = ("cli mode, Current BambuStudio Version", "no filament colors found", "update slice result", "Wayland", "glfwInit",
         "XDG_RUNTIME_DIR", "tree support default to organic")   # the last four: no display in the container -> no thumbnails; cosmetic


# ----------------------------------------------------------------------------------------------- presets
def profile_cache(image):
    root = Path(os.environ.get("RR_SLICE_CACHE", Path.home() / ".cache" / "rr_slice"))
    iid = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", image], capture_output=True, text=True)
    if iid.returncode != 0:
        raise RuntimeError(f"docker image {image} not available: {iid.stderr.strip()}")
    d = root / hashlib.sha1(iid.stdout.strip().encode()).hexdigest()[:12]
    if not (d / "BBL" / "machine").is_dir():
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o777)
        cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{d}:/out", "--entrypoint", "/bin/bash", image, "-c",
               f"cp -r {PROFILES_IN_IMAGE}/BBL /out/ && chmod -R a+rwX /out"]
        subprocess.run(cmd, check=True, capture_output=True)
    return d


def flatten(bbl, kind, name, _seen=()):
    """Resolve `inherits` and `include` of a stock preset -> one flat dict."""
    path = bbl / kind / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"stock {kind} preset not in the image: {name!r}")
    if name in _seen:
        raise RuntimeError(f"preset inheritance loop at {name}")
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    if d.get("inherits"):
        out.update(flatten(bbl, kind, d["inherits"], (*_seen, name)))
    inc = d.get("include") or []
    for i in ([inc] if isinstance(inc, str) else inc):
        out.update(flatten(bbl, kind, i, (*_seen, name)))
    out.update({k: v for k, v in d.items() if k not in ("inherits", "include")})
    return out


def apply_overrides(cfg, overrides):
    for k, v in (overrides or {}).items():
        if isinstance(v, bool):
            v = "1" if v else "0"
        if isinstance(v, (list, tuple)):
            cfg[k] = [str(x) for x in v]
        elif isinstance(cfg.get(k), list):
            cfg[k] = [str(v)] * len(cfg[k])
        else:
            cfg[k] = str(v)
    return cfg


# ----------------------------------------------------------------------------------------------- manifest
def load_manifest(path):
    man = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not str(man.get("schema", "")).startswith("rr-plates/1"):
        raise ValueError(f"{path}: schema must be rr-plates/1 (see mechanical/tools/README.md)")
    man["printer"] = {**DEFAULT_PRINTER, **(man.get("printer") or {})}
    man["defaults"] = {**DEFAULTS, **(man.get("defaults") or {})}
    man.setdefault("materials", {})
    ids = [p["id"] for p in man["plates"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate plate ids")
    return man


def shelf_pack(items, bed, margin, gap, exclude):
    """items: list of dict with w, d (bbox size).  Assigns centre positions to those without one."""
    x0, y0 = margin, margin
    x, y, row_h = x0, y0, 0.0
    for it in sorted([i for i in items if i["pos"] is None], key=lambda i: -i["d"]):
        while True:
            if x + it["w"] > bed[0] - margin:
                x, y, row_h = x0, y + row_h + gap, 0.0
            if y + it["d"] > bed[1] - margin:
                raise ValueError(f"auto-arrange: {it['name']} does not fit the plate")
            if x < exclude[2] + gap and y < exclude[3] + gap:      # keep clear of the exclusion corner
                x = exclude[2] + gap
                continue
            break
        it["pos"] = (x + it["w"] / 2, y + it["d"] / 2)
        x += it["w"] + gap
        row_h = max(row_h, it["d"])


def build_plate(plate, man, base_dir):
    pr, df = man["printer"], man["defaults"]
    bed, margin, ex = pr["bed"], float(plate.get("edge_margin", pr["edge_margin"])), pr["exclude_area"]
    gap = float(plate.get("part_gap", df["part_gap"]))
    items, problems = [], []
    for part in plate["parts"]:
        mesh_path = (base_dir / part["mesh"]).resolve()
        if not mesh_path.exists():
            problems.append(f"mesh missing: {part['mesh']}")
            continue
        tris = M.read_stl(mesh_path)
        o = part.get("orient") or {}
        rz = float(part.get("rotation_z", 0.0))
        tris = M.transform(tris, M.rot_matrix(float(o.get("rx", 0)), float(o.get("ry", 0)), float(o.get("rz", 0)) + rz))
        b = M.bbox(tris)
        tris = M.transform(tris, t=(-(b[0] + b[3]) / 2, -(b[1] + b[4]) / 2, -b[2]))
        qty = int(part.get("qty", 1))
        positions = part.get("positions") or ([part["position"]] if part.get("position") is not None else [])
        if positions and len(positions) != qty:
            problems.append(f"{part['part']}: {qty} off but {len(positions)} position(s)")
        oe = M.open_edges(tris)
        if oe:
            problems.append(f"{part['part']}: mesh not watertight ({oe} open/non-manifold edges)")
        for n in range(qty):
            items.append({"name": part["part"] + (f"#{n + 1}" if qty > 1 else ""), "part": part["part"], "tris": tris,
                          "w": b[3] - b[0], "d": b[4] - b[1], "h": b[5] - b[2], "vol": abs(M.volume(tris)),
                          "pos": tuple(positions[n]) if n < len(positions) else None, "tri_count": len(tris)})
    try:
        shelf_pack(items, bed, margin, gap, ex)
    except ValueError as e:
        problems.append(str(e))
    boxes = []
    for it in items:
        if it["pos"] is None:
            continue
        cx, cy = it["pos"]
        bx = (cx - it["w"] / 2, cy - it["d"] / 2, cx + it["w"] / 2, cy + it["d"] / 2)
        it["bbox_on_bed"] = [round(v, 2) for v in bx] + [round(it["h"], 2)]
        if bx[0] < margin - 1e-6 or bx[1] < margin - 1e-6 or bx[2] > bed[0] - margin + 1e-6 or bx[3] > bed[1] - margin + 1e-6:
            problems.append(f"{it['name']}: outside the plate (bbox {it['bbox_on_bed'][:4]}, margin {margin})")
        if it["h"] > bed[2]:
            problems.append(f"{it['name']}: taller than the build volume ({it['h']:.1f} > {bed[2]})")
        if bx[0] < ex[2] and bx[1] < ex[3]:
            problems.append(f"{it['name']}: bounding box enters the front-left exclusion area {ex}")
        for name, other in boxes:
            if bx[0] < other[2] and other[0] < bx[2] and bx[1] < other[3] and other[1] < bx[3]:
                problems.append(f"{it['name']} and {name}: bounding boxes overlap on the plate")
        boxes.append((it["name"], bx))
    return items, problems


# ----------------------------------------------------------------------------------------------- slicer run
def run_studio(work, image, script, timeout):
    (work / "run.sh").write_text("#!/bin/bash\nexport LD_LIBRARY_PATH=/opt/bambustudio/bin LC_ALL=C\ncd /work\n" + script + "\n", encoding="utf-8")
    os.chmod(work, 0o777)
    cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{work}:/work", "--entrypoint", "/bin/bash", image, "/work/run.sh"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr, time.time() - t0
    except subprocess.TimeoutExpired as e:
        subprocess.run("docker ps -q --filter ancestor=" + image + " | xargs -r docker kill", shell=True, capture_output=True)
        return -9, f"TIMEOUT after {timeout} s\n{(e.stdout or b'').decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or '')}", time.time() - t0


def log_messages(log):
    out = []
    for line in log.splitlines():
        m = re.search(r"\[(warning|error)\]\s+(?:\[[^\]]*\]\s*)?(.*)", line)
        if m and not any(n in line for n in NOISE):
            msg = f"{m.group(1)}: {m.group(2).strip()}"
            if msg not in out:
                out.append(msg)
    return out


def parse_time(text):
    s = 0
    for val, unit in re.findall(r"(\d+)\s*([dhms])", text):
        s += int(val) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return s


def parse_sliced(path):
    info = {"gcode_present": False}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        g = [n for n in names if n.endswith(".gcode")]
        if g:
            info["gcode_present"] = True
            info["gcode_bytes"] = z.getinfo(g[0]).file_size
            with z.open(g[0]) as fh:
                head = fh.read(20000).decode("utf-8", "replace")
            m = re.search(r"model printing time:\s*([^;]+);\s*total estimated time:\s*([^\n]+)", head)
            if m:
                info["model_time_s"], info["total_time_s"] = parse_time(m.group(1)), parse_time(m.group(2))
                info["total_time"] = m.group(2).strip()
            for key, pat in (("layers", r"total layer number:\s*(\d+)"), ("filament_mm", r"total filament length \[mm\]\s*:\s*([\d.,]+)"),
                             ("filament_cm3", r"total filament volume \[cm\^3\]\s*:\s*([\d.,]+)"), ("filament_g", r"total filament weight \[g\]\s*:\s*([\d.,]+)"),
                             ("max_z", r"max_z_height:\s*([\d.]+)")):
                m = re.search(pat, head)
                if m:
                    vals = [float(v) for v in m.group(1).split(",") if v]
                    info[key] = round(sum(vals), 2) if key != "layers" else int(vals[0])
            if "filament_cm3" in info:     # the header prints mm3 under a cm3 label
                info["filament_cm3"] = round(info["filament_cm3"] / 1000.0, 2)
        if "Metadata/slice_info.config" in names:
            txt = z.read("Metadata/slice_info.config").decode("utf-8", "replace")
            for key in ("prediction", "weight", "outside", "support_used", "nozzle_diameters", "label_object_enabled"):
                m = re.search(rf'<metadata key="{key}" value="([^"]*)"', txt)
                if m:
                    info[f"slice_info_{key}"] = m.group(1)
            info["slice_info_warnings"] = [dict(re.findall(r'(\w+)="([^"]*)"', w)) for w in re.findall(r"<warning ([^>]*)/>", txt)]
            info["filaments"] = [dict(re.findall(r'(\w+)="([^"]*)"', w)) for w in re.findall(r"<filament ([^>]*)/>", txt)]
    return info


def slice_plate(plate, man, base_dir, out_dir, bbl, args):
    pid = plate["id"]
    df, pr = man["defaults"], man["printer"]
    mat_key = plate.get("material")
    mat = man["materials"].get(mat_key, {}) if mat_key else {}
    filament_name = plate.get("filament_profile") or mat.get("filament_profile")
    process_name = plate.get("process") or mat.get("process") or df["process"]
    plate_type = plate.get("plate_type") or mat.get("plate_type") or df["plate_type"]
    S = {"plate": pid, "name": plate.get("name", ""), "material": mat_key, "machine_profile": pr["machine_profile"], "process_profile": process_name,
         "filament_profile": filament_name, "plate_type": plate_type, "overrides": {**(mat.get("overrides") or {}), **(plate.get("overrides") or {})},
         "status": "PENDING", "sliced": False, "project_3mf": None, "gcode_3mf": None, "pending_reason": None, "precheck": {}, "slicer": {}}
    items, problems = build_plate(plate, man, base_dir)
    density = mat.get("density_g_cm3")
    S["parts"] = [{"name": it["name"], "bbox_on_bed": it.get("bbox_on_bed"), "size": [round(it["w"], 1), round(it["d"], 1), round(it["h"], 1)],
                   "triangles": it["tri_count"], "solid_volume_cm3": round(it["vol"] / 1000, 2),
                   "solid_mass_g": round(it["vol"] / 1000 * density, 1) if density else None} for it in items]
    S["precheck"] = {"ok": not problems, "problems": problems}
    if plate_type not in PLATE_TYPES:
        problems.append(f"unknown plate type {plate_type!r} (one of {PLATE_TYPES})")
    if not filament_name:
        problems.append("no filament_profile (plate or materials entry)")
    if problems:
        S["status"], S["pending_reason"] = "PRECHECK_FAILED", "; ".join(problems)
        return S
    if args.precheck_only:
        S["status"], S["pending_reason"] = "PRECHECK_OK", "slicer not run (--precheck-only)"
        return S

    work = out_dir / "_work" / pid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    M.write_3mf(work / "plate.model.3mf", [(it["name"], it["tris"], (it["pos"][0], it["pos"][1], 0.0)) for it in items], title=f"{pid} {plate.get('name', '')}")
    try:
        machine = flatten(bbl, "machine", pr["machine_profile"])
        process = apply_overrides(flatten(bbl, "process", process_name), S["overrides"])
        filament = apply_overrides(flatten(bbl, "filament", filament_name), {**(mat.get("filament_overrides") or {}), **(plate.get("filament_overrides") or {})})
    except (FileNotFoundError, RuntimeError) as e:
        S["status"], S["pending_reason"] = "PROFILE_ERROR", str(e)
        return S
    for kind, cfg in (("process", process), ("filament", filament)):
        cp = cfg.get("compatible_printers")
        if isinstance(cp, list) and cp and pr["machine_profile"] not in cp:
            S["precheck"]["problems"].append(f"stock {kind} preset {cfg['name']!r} does not list {pr['machine_profile']!r} as compatible")
    for fn, cfg in (("machine.json", machine), ("process.json", process), ("filament.json", filament)):
        (work / fn).write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    common = f'--debug 2 --arrange 0 --load-settings "machine.json;process.json" --load-filaments "filament.json" --curr-bed-type "{plate_type}"'
    script = (f'{BIN} {common} --export-3mf project.3mf plate.model.3mf > project.log 2>&1; echo "rc=$?" >> project.log; '
              'mv -f result.json result_project.json 2>/dev/null\n')
    if not args.no_slice:
        script += (f'{BIN} {common} --slice 0 --export-3mf sliced.gcode.3mf plate.model.3mf > slice.log 2>&1; echo "rc=$?" >> slice.log\n')
    script += "chmod -R a+rwX /work\n"
    rc, log, dt = run_studio(work, args.image, script, args.timeout)
    S["slicer"]["wall_time_s"] = round(dt, 1)
    plog = (work / "project.log").read_text(errors="replace") if (work / "project.log").exists() else log
    if (work / "project.3mf").exists() and (work / "project.3mf").stat().st_size > 0:
        shutil.copyfile(work / "project.3mf", out_dir / f"{pid}.3mf")
        S["project_3mf"] = f"{pid}.3mf"
    else:
        S["status"], S["pending_reason"] = "PROJECT_EXPORT_FAILED", "; ".join(log_messages(plog)[-4:]) or plog[-400:]
        return S
    if args.no_slice:
        S["status"], S["pending_reason"] = "PROJECT_ONLY", "slice not requested (--no-slice)"
        return S
    slog = (work / "slice.log").read_text(errors="replace") if (work / "slice.log").exists() else log
    res = {}
    if (work / "result.json").exists():
        try:
            res = json.loads((work / "result.json").read_text())
        except json.JSONDecodeError:
            res = {}
    S["slicer"].update({"return_code": res.get("return_code"), "error_string": res.get("error_string"), "peak_rss_mb": res.get("peak_rss_mb"),
                        "layer_height": res.get("layer_height"), "wall_loops": res.get("wall_loops"), "sparse_infill_density": res.get("sparse_infill_density"),
                        "sliced_plates": res.get("sliced_plates"), "messages": log_messages(slog)})
    sliced = work / "sliced.gcode.3mf"
    if rc == -9:
        S["status"], S["pending_reason"] = "SLICE_TIMEOUT", f"slicer exceeded {args.timeout} s"
    elif sliced.exists() and res.get("return_code") == 0:
        info = parse_sliced(sliced)
        S["slicer"].update(info)
        for sp in res.get("sliced_plates") or []:
            for w in sp.get("warning_message", []) if isinstance(sp.get("warning_message"), list) else ([sp["warning_message"]] if sp.get("warning_message") else []):
                S["slicer"]["messages"].append(f"plate warning: {w}")
        if info["gcode_present"]:
            shutil.copyfile(sliced, out_dir / f"{pid}.gcode.3mf")
            S.update(status="SLICED", sliced=True, gcode_3mf=f"{pid}.gcode.3mf")
        else:
            S["status"], S["pending_reason"] = "SLICE_FAILED", "CLI returned 0 but the exported 3MF holds no G-code"
    else:
        S["status"] = "SLICE_FAILED"
        S["pending_reason"] = res.get("error_string") or "; ".join(log_messages(slog)[-4:]) or slog[-400:]
    if not args.keep_work:
        for f in ("plate_1.gcode", "sliced.gcode.3mf", "project.3mf"):
            (work / f).unlink(missing_ok=True)
    return S


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--out", help="output directory (default: <manifest dir>/out/slices)")
    ap.add_argument("--plates", help="comma-separated plate ids (default: all)")
    ap.add_argument("--no-slice", action="store_true", help="export the Bambu Studio project .3mf only")
    ap.add_argument("--precheck-only", action="store_true", help="tool-side fit/overlap/watertight checks only, no docker")
    ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--timeout", type=int, default=2400, help="seconds per plate")
    ap.add_argument("--keep-work", action="store_true")
    args = ap.parse_args(argv)
    mpath = Path(args.manifest).resolve()
    man = load_manifest(mpath)
    out_dir = Path(args.out).resolve() if args.out else mpath.parent / "out" / "slices"
    out_dir.mkdir(parents=True, exist_ok=True)
    want = set(args.plates.split(",")) if args.plates else None
    bbl = None if args.precheck_only else profile_cache(args.image) / "BBL"
    prev = {}
    if (out_dir / "slice_summary.json").exists() and want:
        try:
            prev = {s["plate"]: s for s in json.loads((out_dir / "slice_summary.json").read_text())["plates"]}
        except (json.JSONDecodeError, KeyError):
            prev = {}
    results = []
    for plate in man["plates"]:
        if want and plate["id"] not in want:
            if plate["id"] in prev:
                results.append(prev[plate["id"]])
            continue
        t0 = time.time()
        try:
            S = slice_plate(plate, man, mpath.parent, out_dir, bbl, args)
        except Exception as e:  # noqa: BLE001
            S = {"plate": plate["id"], "name": plate.get("name", ""), "status": "TOOL_ERROR", "sliced": False, "pending_reason": f"{type(e).__name__}: {e}",
                 "precheck": {}, "slicer": {}, "parts": []}
        (out_dir / f"{plate['id']}.summary.json").write_text(json.dumps(S, indent=1), encoding="utf-8")
        sl = S.get("slicer", {})
        print(f"{S['plate']:6s} {S['status']:22s} {sl.get('total_time', ''):>12s} {str(sl.get('filament_g', '')):>8s} g  "
              f"{(S.get('pending_reason') or '')[:110]}  [{time.time() - t0:.0f} s]", flush=True)
        results.append(S)
    summary = {"schema": "rr-slice-summary/1", "manifest": str(mpath), "image": args.image, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "machine_profile": man["printer"]["machine_profile"], "plates": results}
    (out_dir / "slice_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    with open(out_dir / "slice_summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["plate", "name", "status", "sliced", "material", "filament_profile", "process_profile", "plate_type", "print_time", "print_time_s",
                    "filament_g", "filament_m", "layers", "max_z_mm", "support_used", "parts", "slicer_messages", "pending_reason"])
        for S in results:
            sl = S.get("slicer", {})
            w.writerow([S["plate"], S.get("name", ""), S["status"], S["sliced"], S.get("material"), S.get("filament_profile"), S.get("process_profile"),
                        S.get("plate_type"), sl.get("total_time", ""), sl.get("total_time_s", ""), sl.get("filament_g", ""),
                        round(sl["filament_mm"] / 1000, 2) if sl.get("filament_mm") else "", sl.get("layers", ""), sl.get("max_z", ""),
                        sl.get("slice_info_support_used", ""), " ".join(p["name"] for p in S.get("parts", [])),
                        " | ".join(sl.get("messages", []) + [w_.get("msg", "") for w_ in sl.get("slice_info_warnings", [])]), S.get("pending_reason") or ""])
    ok_states = {"SLICED"} | ({"PROJECT_ONLY"} if args.no_slice else set()) | ({"PRECHECK_OK"} if args.precheck_only else set())
    bad = [S["plate"] for S in results if S["status"] not in ok_states]
    print(f"{len(results) - len(bad)}/{len(results)} plates OK; summary: {out_dir / 'slice_summary.json'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
