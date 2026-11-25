"""Manufacturing / documentation outputs (all via kicad-cli, plus BOM and pin map)."""
import csv
import json
import os
import re
import shutil
import subprocess

from .netlist import Netlist


def _run(cmd, results, label, must=None):
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0 and (must is None or os.path.exists(must))
    entry = {"output": label, "ok": bool(ok)}
    if not ok:
        entry["error"] = (r.stdout + r.stderr).strip()[-600:]
    results.append(entry)
    return ok, r.stdout + r.stderr


def schematic_pdf(paths, results=None):
    results = results if results is not None else []
    os.makedirs(paths.out, exist_ok=True)
    out = os.path.join(paths.out, paths.name + "-schematic.pdf")
    _run(["kicad-cli", "sch", "export", "pdf", "-o", out, paths.sch], results, _rel(paths, out), out)
    return results


def _rel(paths, p):
    return os.path.relpath(p, paths.dir)


def copper_layers(board):
    return ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] if board.layers == 4 else ["F.Cu", "B.Cu"]


def generate(board, paths, summary):
    res = []
    name = paths.name
    out = paths.out
    schematic_pdf(paths, res)
    # --- Gerbers + drill -------------------------------------------------------
    gdir = os.path.join(out, "gerber")
    os.makedirs(gdir, exist_ok=True)
    for fn in os.listdir(gdir):
        os.remove(os.path.join(gdir, fn))
    layers = copper_layers(board) + ["F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts"]
    _run(["kicad-cli", "pcb", "export", "gerbers", "-o", gdir + "/", "--layers", ",".join(layers),
          "--use-drill-file-origin", "--subtract-soldermask", paths.pcb], res, _rel(paths, gdir) + "/*.g*")
    _run(["kicad-cli", "pcb", "export", "drill", "-o", gdir + "/", "--format", "excellon", "--drill-origin", "plot",
          "--excellon-units", "mm", "--excellon-separate-th", "--generate-map", "--map-format", "pdf",
          "--generate-report", "--report-path", os.path.join(gdir, name + "-drill-report.txt"), paths.pcb],
         res, _rel(paths, gdir) + "/*.drl + drill map")
    _normalise_dates(gdir, board.date)
    # --- pick and place ----------------------------------------------------------
    pos = os.path.join(out, name + "-pos.csv")
    _run(["kicad-cli", "pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "both",
          "--use-drill-file-origin", "--exclude-dnp", paths.pcb], res, _rel(paths, pos), pos)
    # --- BOM / pin map -------------------------------------------------------------
    bom = os.path.join(out, name + "-bom.csv")
    write_bom(board, bom)
    res.append({"output": _rel(paths, bom), "ok": True})
    pm = os.path.join(out, "pinmap.json")
    write_pinmap(board, paths, pm)
    res.append({"output": _rel(paths, pm), "ok": True})
    res.append({"output": _rel(paths, paths.netlist), "ok": os.path.exists(paths.netlist)})
    # --- drawings ------------------------------------------------------------------
    fab = os.path.join(out, name + "-fab.pdf")
    _run(["kicad-cli", "pcb", "export", "pdf", "-o", fab, "--mode-single", "--ibt", "--black-and-white",
          "--layers", "Edge.Cuts,Cmts.User,Dwgs.User", "--drill-shape-opt", "2", paths.pcb], res, _rel(paths, fab), fab)
    asm_t = os.path.join(out, name + "-assembly-top.pdf")
    _run(["kicad-cli", "pcb", "export", "pdf", "-o", asm_t, "--mode-single", "--ibt", "--black-and-white",
          "--layers", "F.Fab,F.SilkS,Edge.Cuts", "--cdnp", paths.pcb], res, _rel(paths, asm_t), asm_t)
    asm_b = os.path.join(out, name + "-assembly-bottom.pdf")
    _run(["kicad-cli", "pcb", "export", "pdf", "-o", asm_b, "--mode-single", "--ibt", "--black-and-white", "--mirror",
          "--layers", "B.Fab,B.SilkS,Edge.Cuts", "--cdnp", paths.pcb], res, _rel(paths, asm_b), asm_b)
    cu = os.path.join(out, name + "-copper.pdf")
    tmpd = os.path.join(out, "_copper_tmp")
    if os.path.isdir(cu):
        shutil.rmtree(cu)
    _run(["kicad-cli", "pcb", "export", "pdf", "-o", tmpd, "--mode-multipage", "--ibt",
          "--layers", ",".join(copper_layers(board)), "--cl", "Edge.Cuts", paths.pcb], res, _rel(paths, cu))
    if os.path.isdir(tmpd):
        pdfs = [f for f in os.listdir(tmpd) if f.endswith(".pdf")]
        if pdfs:
            os.replace(os.path.join(tmpd, pdfs[0]), cu)
        shutil.rmtree(tmpd, ignore_errors=True)
    elif os.path.isfile(tmpd):
        os.replace(tmpd, cu)
    res[-1]["ok"] = res[-1]["ok"] and os.path.isfile(cu)
    # --- 3D ------------------------------------------------------------------------
    step = os.path.join(out, name + ".step")
    ok, log = _run(["kicad-cli", "pcb", "export", "step", "-o", step, "--force", "--drill-origin", "--subst-models",
                    "--no-dnp", paths.pcb], res, _rel(paths, step), step)
    missing = sorted(set(re.findall(r"(?:Could not add|missing|not found).*?([\w\-\.]+\.(?:step|stp|wrl))", log, re.I)))
    if os.path.exists(step):
        _normalise_step(step, board.date)
    if missing:
        res[-1]["note"] = "3D models not available (board body exported without these component bodies): " + ", ".join(missing[:40])
    for side in ("top", "bottom"):
        png = os.path.join(out, "%s-render-%s.png" % (name, side))
        _run(["kicad-cli", "pcb", "render", "-o", png, "--side", side, "--width", "1600", "--height", "1200",
              "--background", "opaque", paths.pcb], res, _rel(paths, png), png)
    return res


def _normalise_dates(gdir, date):
    stamp = (date or "1970-01-01") + "T00:00:00+00:00"
    for fn in sorted(os.listdir(gdir)):
        p = os.path.join(gdir, fn)
        if fn.endswith(".pdf"):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                s = f.read()
        except UnicodeDecodeError:
            continue
        s2 = re.sub(r"(TF\.CreationDate,)[^*\n]*", r"\g<1>" + stamp, s)
        s2 = re.sub(r"(Created by KiCad[^\n]*? date )[^*\n]*", r"\g<1>" + stamp, s2)
        s2 = re.sub(r"(DRILL file \{[^}]*\} date )[^\n]*", r"\g<1>" + stamp, s2)
        s2 = re.sub(r'("CreationDate"\s*:\s*)"[^"]*"', r'\1"' + stamp + '"', s2)
        s2 = re.sub(r"(?m)^(Drill report for .*?)$", r"\1", s2)
        s2 = re.sub(r"(?m)^(Created on ).*$", r"\g<1>" + stamp, s2)
        if s2 != s:
            with open(p, "w", encoding="utf-8") as f:
                f.write(s2)


def _normalise_step(path, date):
    with open(path, encoding="utf-8", errors="replace") as f:
        s = f.read()
    s2 = re.sub(r"(FILE_NAME\('[^']*',')[^']*(')", r"\g<1>" + (date or "1970-01-01") + "T00:00:00" + r"\2", s, count=1)
    if s2 != s:
        with open(path, "w", encoding="utf-8") as f:
            f.write(s2)


def _refkey(ref):
    m = re.match(r"^([A-Za-z#]+)(\d+)(.*)$", ref)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (ref, 0, "")


def write_bom(board, path):
    groups = {}
    for p in board.parts:
        if not p.bom:
            continue
        key = (p.value, p.footprint, p.mfr, p.mpn, bool(p.dnp))
        g = groups.setdefault(key, {"refs": [], "notes": [], "verify": False})
        g["refs"].append(p.ref)
        if p.notes and p.notes not in g["notes"]:
            g["notes"].append(p.notes)
        g["verify"] = g["verify"] or bool(p.verify)
    rows = []
    for (value, fp, mfr, mpn, dnp), g in groups.items():
        refs = sorted(g["refs"], key=_refkey)
        notes = "; ".join(g["notes"])
        if g["verify"]:
            notes = (notes + "; " if notes else "") + "verify: true"
        rows.append((_refkey(refs[0]), [" ".join(refs), len(refs), value, fp, mfr, mpn, "DNP" if dnp else "", notes]))
    rows.sort(key=lambda r: r[0])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Refs", "Qty", "Value", "Footprint", "Manufacturer", "MPN", "DNP", "Notes"])
        for _, r in rows:
            w.writerow(r)


def write_pinmap(board, paths, path):
    nl = Netlist(paths.netlist)
    try:
        from .pcb import pad_positions
        padpos = pad_positions(paths.pcb, board) if os.path.exists(paths.pcb) else {}
    except ImportError:
        padpos = {}
    parts = []
    for p in sorted(board.parts, key=lambda q: _refkey(q.ref)):
        pins = []
        for pin in sorted(p.sym.pins, key=lambda q: _refkey("P" + q.number) if q.number.isdigit() else ("~", 0, q.number)):
            net = nl.pin_net.get((p.ref, pin.number))
            nc = net is None or net.startswith("unconnected-(")
            entry = {"pin": pin.number, "name": pin.name, "net": None if nc else net, "type": pin.etype}
            pp = padpos.get((p.ref, pin.number))
            if pp:
                entry["pad_xy_mm"] = [pp[0][0], pp[0][1]] if len(pp) == 1 else [[q[0], q[1]] for q in pp]
                entry["side"] = pp[0][2]
            pins.append(entry)
        parts.append({"ref": p.ref, "value": p.value, "group": p.group.name, "symbol": p.symbol,
                      "footprint": p.footprint, "mpn": p.mpn, "dnp": bool(p.dnp), "pins": pins})
    nets = {}
    for part in parts:
        for pin in part["pins"]:
            if pin["net"]:
                nets.setdefault(pin["net"], []).append("%s.%s" % (part["ref"], pin["pin"]))
    with open(path, "w") as f:
        json.dump({"board": board.name, "rev": board.rev,
                   "coordinates": "pad_xy_mm: board frame, X right / Y up, origin = drill/place origin, viewed from the top",
                   "parts": parts,
                   "nets": {k: nets[k] for k in sorted(nets)}}, f, indent=1)
        f.write("\n")
