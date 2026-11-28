"""ERC / DRC via kicad-cli, waiver handling and the summary JSON."""
import json
import os
import re
import subprocess


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def _text(v):
    return " | ".join([v.get("type", ""), v.get("description", "")] +
                      [i.get("description", "") for i in v.get("items", [])])


def _classify(violations, waivers, check):
    """Split violations into errors / warnings / waived.  Returns dict."""
    out = {"errors": 0, "warnings": 0, "waived": 0, "excluded": 0, "by_type": {}, "error_items": [], "waived_items": []}
    for v in violations:
        if v.get("excluded"):
            out["excluded"] += 1
            continue
        txt = _text(v)
        hit = None
        for w in waivers:
            if w["check"] == check and w["rule"] == v.get("type") and (w["match"] is None or re.search(w["match"], txt)):
                hit = w
                break
        if hit is not None:
            hit["count"] = hit.get("count", 0) + 1
            out["waived"] += 1
            out["waived_items"].append({"type": v.get("type"), "severity": v.get("severity"), "text": txt[:300]})
            continue
        sev = v.get("severity", "error")
        key = "errors" if sev == "error" else "warnings"
        out[key] += 1
        bt = out["by_type"].setdefault(v.get("type", "?"), {"errors": 0, "warnings": 0})
        bt[key] += 1
        if sev == "error":
            out["error_items"].append(txt[:400])
    return out


def run_erc(board, paths, waivers=None):
    os.makedirs(paths.reports, exist_ok=True)
    js = os.path.join(paths.reports, "erc.json")
    rpt = os.path.join(paths.reports, "erc.rpt")
    for fmt, outp in (("json", js), ("report", rpt)):
        rc, log = _run(["kicad-cli", "sch", "erc", "--format", fmt, "--severity-all", "--units", "mm", "-o", outp, paths.sch])
        if not os.path.exists(outp):
            raise RuntimeError("kicad-cli sch erc failed:\n" + log)
    _strip_dates(js, rpt)
    with open(js) as f:
        data = json.load(f)
    viol = []
    for sh in data.get("sheets", []):
        for v in sh.get("violations", []):
            v = dict(v)
            v["description"] = "%s [sheet %s]" % (v.get("description", ""), sh.get("path", "?"))
            viol.append(v)
    waivers = waivers if waivers is not None else [dict(w) for w in board.waivers]
    res = _classify(viol, waivers, "erc")
    res["report"] = os.path.relpath(js, paths.dir)
    return res


def run_drc(board, paths, waivers=None, state=None):
    js = os.path.join(paths.reports, "drc.json")
    rpt = os.path.join(paths.reports, "drc.rpt")
    for fmt, outp in (("json", js), ("report", rpt)):
        rc, log = _run(["kicad-cli", "pcb", "drc", "--format", fmt, "--schematic-parity", "--severity-all",
                        "--units", "mm", "-o", outp, paths.pcb])
        if not os.path.exists(outp):
            raise RuntimeError("kicad-cli pcb drc failed:\n" + log)
    _strip_dates(js, rpt)
    with open(js) as f:
        data = json.load(f)
    waivers = waivers if waivers is not None else [dict(w) for w in board.waivers]
    res = _classify(data.get("violations", []), waivers, "drc")
    unconn = data.get("unconnected_items", [])
    parity = data.get("schematic_parity", [])
    res["unconnected"] = len(unconn)
    # KiCad's DRC report lists at most 499 unconnected items: take the real count from the board
    res["unconnected_listed"] = len(unconn)
    try:
        import pcbnew
        b_ = pcbnew.LoadBoard(paths.pcb)
        b_.BuildConnectivity()          # zones as saved (finish_pcb saves them filled)
        res["unconnected"] = max(len(unconn), int(b_.GetConnectivity().GetUnconnectedCount(True)))
    except Exception as e:              # never hide a count: keep the listed one and say why
        res["unconnected_count_error"] = str(e)[:200]
    nets = set()
    for u in unconn:
        for it in u.get("items", []):
            m = re.search(r"\[([^\]]+)\]", it.get("description", ""))
            if m:
                nets.add(m.group(1))
    res["unrouted_nets"] = sorted(nets)
    res["unconnected_items"] = [_text(u)[:300] for u in unconn[:200]]
    ox, oy = (state or {}).get("pcb_page_origin") or (0.0, 0.0)
    detail = []
    for u in unconn[:200]:
        ends = []
        for it in u.get("items", []):
            pos = it.get("pos") or {}
            ends.append({"item": it.get("description", ""),
                         "xy_mm": [round(pos.get("x", 0) - ox, 3), round(oy - pos.get("y", 0), 3)]})
        m = re.search(r"\[([^\]]+)\]", ends[0]["item"]) if ends else None
        detail.append({"net": m.group(1) if m else "?", "ends": ends})
    res["unrouted"] = detail
    # the full list KiCad gives (it stops at 499) with board coordinates, one line per open connection
    with open(os.path.join(paths.reports, "open_connections.txt"), "w") as f:
        f.write("# %d open connection(s) by the board's connectivity count; KiCad's DRC lists %d.\n" % (
            max(len(unconn), res.get("unconnected", 0)), len(unconn)))
        for u in unconn:
            ends = []
            for it in u.get("items", []):
                pos = it.get("pos") or {}
                ends.append("%s @(%.3f, %.3f)" % (it.get("description", ""), pos.get("x", 0) - ox, oy - pos.get("y", 0)))
            f.write("  <->  ".join(ends) + "\n")
    par = _classify(parity, waivers, "drc")
    res["parity"] = par["errors"] + par["warnings"]
    res["parity_items"] = [_text(p)[:300] for p in parity if not p.get("excluded")][:200]
    res["waived"] += par["waived"]
    res["waived_items"] += par["waived_items"]
    res["report"] = os.path.relpath(js, paths.dir)
    return res


def _strip_dates(*files):
    """Remove wall-clock dates from reports so reruns produce identical files."""
    for fn in files:
        with open(fn, encoding="utf-8") as f:
            s = f.read()
        s2 = re.sub(r'("date"\s*:\s*)"[^"]*"', r'\1""', s)
        s2 = re.sub(r"(?m)^(\*\* (?:Created on|Report generated on|Created at)).*$", r"\1 (date removed for reproducibility) **", s2)
        s2 = re.sub(r"(?m)^(ERC report \().*?(, Encoding)", r"\1date removed\2", s2)
        if s2 != s:
            with open(fn, "w", encoding="utf-8") as f:
                f.write(s2)


def bom_issues(board):
    missing, verify = [], []
    for p in board.parts:
        if not p.bom:
            continue
        if not p.mpn or not p.mfr:
            missing.append(p.ref)
        if p.verify:
            verify.append(p.ref)
    return {"missing_mpn": missing, "verify": verify}


def run_checks(board, paths, state):
    waivers = [dict(w, count=0) for w in board.waivers]
    erc = run_erc(board, paths, waivers)
    have_pcb = os.path.exists(paths.pcb)
    drc = run_drc(board, paths, waivers, state) if have_pcb else None
    reasons = []
    if erc["errors"]:
        reasons.append("ERC: %d error(s)" % erc["errors"])
    if drc is None:
        reasons.append("no PCB file")
    else:
        if drc["errors"]:
            reasons.append("DRC: %d error(s)" % drc["errors"])
        if drc["unconnected"]:
            reasons.append("DRC: %d unconnected item(s)%s on nets: %s" % (
                drc["unconnected"], (" (%d listed by KiCad)" % drc["unconnected_listed"]) if drc["unconnected_listed"] < drc["unconnected"] else "",
                ", ".join(drc["unrouted_nets"][:30])))
        if drc["parity"]:
            reasons.append("schematic parity: %d issue(s)" % drc["parity"])
    bi = bom_issues(board)
    notes = []
    if bi["missing_mpn"]:
        notes.append("BOM lines without MPN/manufacturer: " + ", ".join(bi["missing_mpn"]))
    for w in waivers:
        if not w["count"]:
            notes.append("waiver matched nothing: %s/%s %s" % (w["check"], w["rule"], w["match"] or ""))
    for n in state.get("gen_warnings", []):
        notes.append(n)
    summary = {
        "board": board.name, "title": board.title, "rev": board.rev, "date": board.date, "docnum": board.docnum,
        "status": "pass" if not reasons else "fail",
        "fail_reasons": reasons,
        "notes": notes,
        "erc": {k: erc[k] for k in ("errors", "warnings", "waived", "excluded", "by_type", "error_items", "report")},
        "drc": None if drc is None else {k: drc[k] for k in (
            "errors", "warnings", "unconnected", "unconnected_listed", "parity", "waived", "excluded", "by_type", "error_items",
            "unrouted_nets", "unrouted", "unconnected_items", "parity_items", "report")},
        "waivers": [{"check": w["check"], "rule": w["rule"], "match": w["match"], "reason": w["reason"],
                     "matched": w["count"], "kind": "violation waiver (tool-level; the KiCad GUI still lists these)"}
                    for w in waivers] +
                   [{"check": s["check"], "rule": s["rule"], "match": None, "reason": s["reason"],
                     "kind": "project severity set to '%s' (applies in the KiCad GUI too)" % s["level"]}
                    for s in board.severities],
        "waived_items": erc["waived_items"] + (drc["waived_items"] if drc else []),
        "pwr_flags": state.get("pwr_flags", []),
        "single_pin_nets": state.get("single_pin_nets", []),
        "counts": state.get("counts", {}),
        "bom": bi,
        "routing": {"routed": state.get("routed", False), "autorouter": state.get("route_info"),
                    "stats": state.get("route_stats"), "escape": state.get("escape"),
                    "plane_fanout": state.get("plane_fanout"), "finisher": state.get("finisher")},
        "autoplaced": state.get("autoplaced", []),
        "board_bbox_mm": state.get("board_bbox"),
        "tools": _versions(),
    }
    return summary


def _versions():
    rc, out = _run(["kicad-cli", "version"])
    return {"kicad": out.strip().split("\n")[-1] if rc == 0 else "?"}


def write_summary(paths, summary):
    with open(os.path.join(paths.reports, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")


def print_summary(s):
    e, d = s["erc"], s["drc"]
    print("=" * 72)
    print("%s rev %s : %s" % (s["board"], s["rev"], s["status"].upper()))
    print("  ERC  errors=%d warnings=%d waived=%d" % (e["errors"], e["warnings"], e["waived"]))
    if d:
        print("  DRC  errors=%d warnings=%d unconnected=%d parity=%d waived=%d" % (
            d["errors"], d["warnings"], d["unconnected"], d["parity"], d["waived"]))
        for t, c in sorted(d["by_type"].items()):
            print("       %-28s errors=%d warnings=%d" % (t, c["errors"], c["warnings"]))
    for t, c in sorted(e["by_type"].items()):
        print("  ERC  %-28s errors=%d warnings=%d" % (t, c["errors"], c["warnings"]))
    for r in s["fail_reasons"]:
        print("  FAIL: " + r)
    for u in (d or {}).get("unrouted", [])[:25]:
        print("  OPEN  %-12s %s" % (u["net"], "  <->  ".join(
            "%s @(%.2f, %.2f)" % (e["item"][:38], e["xy_mm"][0], e["xy_mm"][1]) for e in u["ends"])))
    for n in s["notes"]:
        print("  note: " + n)
    for w in s["waivers"]:
        print("  waiver: %s/%s -> %s" % (w["check"], w["rule"], w["reason"]))
    print("=" * 72)
