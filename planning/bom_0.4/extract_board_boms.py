#!/usr/bin/env python3
"""Regenerate the per-board BOM CSVs of design 0.4 from the three circuit definitions.

Run from anywhere:  python3 planning/bom_0.4/extract_board_boms.py

Inputs  (imported, not edited; PARTS lists are plain module-level data):
  electronics/chassis_main/design/circuit.py + overrides.py (stage 2 and 3)  -> RR-CHS-MAIN_bom.csv
  electronics/head_acq/design/circuit.py + overrides.py (stage 2 and 3)      -> RR-HEAD-ACQ_bom.csv
  electronics/panel/design/circuit.py          -> RR-PANEL_bom.csv
RR-TOF-A is not regenerated here: its fabrication BOM is electronics/tof_carrier/out/RR-TOF-A-bom.csv
(copied verbatim as RR-TOF-A_bom.csv together with a count check).

Rows are grouped by (MPN, manufacturer, value, DNP, verify).  A row with verify = TRUE carries a part
whose pin-out, orderable code or footprint the board owner has marked as not yet confirmed against a
manufacturer document.  Nothing here is priced and nothing here is checked against stock.
Column `purchasable` is FALSE for PCB features (mounting holes, fiducials, solder jumpers, net ties, wire pads),
CUSTOM for the formed lane shield can (RR-HEAD-SHLD-A, drawing owned by head mechanical) and TRUE otherwise.
"""
import collections, csv, importlib.util, os, shutil, sys

sys.dont_write_bytecode = True
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(os.path.abspath(__file__))

BOARDS = [
    ("RR-CHS-MAIN", "electronics/chassis_main/design/circuit.py"),
    ("RR-HEAD-ACQ", "electronics/head_acq/design/circuit.py"),
    ("RR-PANEL", "electronics/panel/design/circuit.py"),
]
HEADERS = ["board", "mpn", "manufacturer", "value", "description", "package", "rating", "tolerance",
           "quantity", "dnp", "verify", "purchasable", "blocks", "refs", "notes"]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def purchasable(p):
    """FALSE = PCB feature (hole, fiducial, solder jumper, net tie, wire pads, bare test pad); CUSTOM = formed
    part drawn by the mechanical/head work package; TRUE = bought component (including SMD test-point loops)."""
    mfr = str(p.get("manufacturer", "")).lower()
    pkg = str(p.get("package", "")).lower()
    if "pcb feature" in mfr or "pcb feature" in str(p.get("mpn", "")).lower():
        return "FALSE"
    if "custom" in pkg and "shield can" in pkg:
        return "CUSTOM"
    return "TRUE"


def refkey(r):
    import re
    m = re.match(r"([A-Za-z_]+)(\d*)(.*)", r)
    return (m.group(1), int(m.group(2) or 0), m.group(3))


def collapse(parts):
    groups = collections.OrderedDict()
    for p in parts:
        key = (str(p.get("mpn", "")), str(p.get("manufacturer", "")), str(p.get("value", "")),
               bool(p.get("dnp")), bool(p.get("verify")))
        g = groups.setdefault(key, dict(p=p, refs=[], blocks=set(), notes=set(), desc=set(), pkg=set(), rating=set(), tol=set()))
        g["refs"].append(str(p["ref"]))
        if p.get("block"):
            g["blocks"].add(str(p["block"]))
        for k, s in (("notes", "notes"), ("description", "desc"), ("package", "pkg"), ("rating", "rating"), ("tolerance", "tol")):
            if p.get(k):
                g[s].add(str(p[k]))
    rows = []
    for (mpn, mfr, val, dnp, ver), g in groups.items():
        refs = sorted(g["refs"], key=refkey)
        join = lambda s, n=3: " | ".join(sorted(s)[:n]) + (" | ..." if len(s) > n else "")
        rows.append(dict(mpn=mpn, manufacturer=mfr, value=val, description=join(g["desc"], 2), package=join(g["pkg"], 2),
                         rating=join(g["rating"], 2), tolerance=join(g["tol"], 2), quantity=len(refs),
                         dnp="DNP" if dnp else "", verify="VERIFY" if ver else "",
                         purchasable=purchasable(g["p"]), blocks=",".join(sorted(g["blocks"])),
                         refs=" ".join(refs), notes=join(g["notes"], 2)))
    rows.sort(key=lambda r: (r["mpn"].lower(), r["dnp"], r["verify"]))
    return rows


def main():
    summary = []
    for board, path in BOARDS:
        mod = load(path, "circ_" + board.replace("-", "_"))
        parts = mod.PARTS
        ovp = os.path.join(ROOT, os.path.dirname(os.path.dirname(path)), "overrides.py")
        if os.path.exists(ovp):
            # stage-2/3 overrides (S2-xx, S3-xx) are applied exactly as electronics/*/board.py applies them
            ov = load(os.path.relpath(ovp, ROOT), "ovr_" + board.replace("-", "_"))
            parts, _log = ov.apply(mod.PARTS)
        rows = collapse(parts)
        fn = os.path.join(OUT, board + "_bom.csv")
        with open(fn, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS)
            w.writeheader()
            for r in rows:
                r["board"] = board
                w.writerow({k: r.get(k, "") for k in HEADERS})
        n_dnp = sum(1 for p in parts if p.get("dnp"))
        n_ver = sum(1 for p in parts if p.get("verify"))
        n_nobuy = sum(1 for p in parts if purchasable(p) != "TRUE")
        summary.append((board, len(parts), len(rows), n_dnp, n_ver, n_nobuy))
    # RR-TOF-A: copy the fabrication BOM as is and count
    src = os.path.join(ROOT, "electronics/tof_carrier/out/RR-TOF-A-bom.csv")
    dst = os.path.join(OUT, "RR-TOF-A_bom.csv")
    shutil.copyfile(src, dst)
    with open(src, newline="", encoding="utf-8-sig") as f:
        tof = list(csv.DictReader(f))
    n_tof = sum(int(r["Qty"]) for r in tof)
    summary.append(("RR-TOF-A", n_tof, len(tof), sum(1 for r in tof if r.get("DNP")), sum(1 for r in tof if "verify" in r.get("Notes", "").lower()), 0))
    for board, out in (("RR-CHS-MAIN", "chassis_main"), ("RR-HEAD-ACQ", "head_acq"), ("RR-PANEL", "panel")):
        with open(os.path.join(ROOT, "electronics", out, "out", board + "-bom.csv"), newline="", encoding="utf-8-sig") as f:
            gen = sum(int(r["Qty"]) for r in csv.DictReader(f))
        mine = [x for x in summary if x[0] == board][0][1]
        print("cross-check %-12s records here %d, generated fabrication BOM Qty sum %d (differences are PCB features / DNP handling: inspect if large)" % (board, mine, gen))
    print("%-12s %8s %8s %6s %7s %9s" % ("board", "records", "lines", "DNP", "verify", "non-buy"))
    for s in summary:
        print("%-12s %8d %8d %6d %7d %9d" % s)


if __name__ == "__main__":
    main()
