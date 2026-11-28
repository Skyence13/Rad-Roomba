#!/usr/bin/env python3
"""Regenerate the mechanical BOM files of design 0.4 from the mechanical work packages' own BOM tables.

Run:  python3 planning/bom_0.4/extract_mech_boms.py

Inputs (read only):
  mechanical/prototype_x1c/purchased_and_fabricated.csv   -> body_prototype_bom.csv
  mechanical/production/bom_production.csv + hardware_production.csv -> body_production_bom.csv
  mechanical/head/prototype/purchased_and_fabricated.csv  -> head_mech_prototype_bom.csv
  mechanical/head/production/bom_production.csv           -> head_mech_production_bom.csv

Every output row keeps the source status text in `source_status_text` and gets one normalised
`verification_class` (the only values used):
  VERIFIED          a figure the source marks VERIFIED against a manufacturer datasheet or drawing
  PARTIAL           some dimensions verified, others not (source word PARTIAL, or a mixed VERIFIED/UNVERIFIED text)
  UNVERIFIED        recalled, assumed or not checked against a manufacturer document (source word UNVERIFIED)
  STANDARD_ISO_DIN  catalogue fastener or pin given only by its ISO / DIN designation; no supplier part selected,
                    nothing checked against a manufacturer document
  IN_HOUSE          part made in-house or by a job shop from our own drawing or STEP file (design status; not a purchase)
  NOT_SELECTED      a design value or a contract outline with no part chosen
  NOT_STATED        the source gives no status ("-") for a purchased or standard item
Nothing here is priced and nothing has been checked against stock.
"""
import csv, os, sys

sys.dont_write_bytecode = True
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(os.path.abspath(__file__))
HEAD = ["source_file", "subassembly", "part_number", "item", "qty", "make_or_buy", "material", "spec_or_supplier_part",
        "verification_class", "source_status_text", "note"]


def classify(status, make):
    s = (status or "").strip()
    u = s.upper()
    if s in ("-", ""):
        return "IN_HOUSE" if make.upper().startswith(("MAKE", "PRINT", "MACHINED", "FABRIC")) or make.lower() in ("printed (x1c)",) else "NOT_STATED"
    if u.startswith("DESIGN") and "VALUE" not in u:
        return "IN_HOUSE"
    if u.startswith("CONTRACT OUTLINE"):
        return "IN_HOUSE"          # custom board of this project (envelope only here; its BOM is B01 / B02 / B03 / W21)
    if u in ("DESIGN VALUE",):
        return "NOT_SELECTED"
    if u.startswith("STD") or u.startswith("STANDARD PART"):
        return "STANDARD_ISO_DIN"
    if "PARTIAL" in u:
        return "PARTIAL"
    if "UNVERIFIED" in u and "VERIFIED" in u.replace("UNVERIFIED", ""):
        return "PARTIAL"
    if "UNVERIFIED" in u:
        return "UNVERIFIED"
    if "VERIFIED" in u:
        return "PARTIAL" if ("ENVELOPE" in u or "OUTLINE" in u or "'" in u) else "VERIFIED"
    return "NOT_STATED"


def rd(p):
    with open(os.path.join(ROOT, p), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(name, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HEAD)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["verification_class"]] = counts.get(r["verification_class"], 0) + 1
    print("%-30s %3d lines  %s" % (name, len(rows), dict(sorted(counts.items()))))


def body_proto():
    src = "mechanical/prototype_x1c/purchased_and_fabricated.csv"
    rows = []
    for r in rd(src):
        cat = r["category"]
        make = {"printed": "PRINT", "fabricated": "MAKE", "hardware": "BUY", "purchased": "BUY"}.get(cat, cat)
        rows.append(dict(source_file=src, subassembly=r["subassembly"], part_number=r["part_number"], item=r["item"], qty=r["qty"],
                         make_or_buy=make, material=r["material"], spec_or_supplier_part=r["supplier_pn_or_spec"],
                         verification_class=classify(r["status"], make), source_status_text=r["status"], note=r["note"]))
    return rows


def body_prod():
    rows = []
    src = "mechanical/production/bom_production.csv"
    for r in rd(src):
        make = r["make_buy"]
        rows.append(dict(source_file=src, subassembly="", part_number=r["part_number"], item=r["part"], qty=r["qty"], make_or_buy=make,
                         material=r["material"], spec_or_supplier_part=r["process"], verification_class=classify(r["status"], make),
                         source_status_text=r["status"], note="replaces " + r["x1c_pn"] if r["x1c_pn"] else ""))
    src = "mechanical/production/hardware_production.csv"
    for r in rd(src):
        rows.append(dict(source_file=src, subassembly=r["subassembly"], part_number="", item=r["item"], qty=r["qty"], make_or_buy="BUY",
                         material="", spec_or_supplier_part=r["spec"], verification_class=classify(r["status"], "BUY"),
                         source_status_text=r["status"], note=r["where"] + ("; " + r["note"] if r["note"] else "")))
    return rows


def head(src):
    rows = []
    for r in rd(src):
        make = r["make"]
        rows.append(dict(source_file=src, subassembly="head", part_number=r["pn"], item=r["description"], qty=r["qty"], make_or_buy=make,
                         material=r["material"], spec_or_supplier_part=r["supplier_part"],
                         verification_class=classify(r["verification"], make) if r["verification"] != "-" or make != "purchased" else "NOT_STATED",
                         source_status_text=r["verification"], note=r["note"]))
    return rows


if __name__ == "__main__":
    write("body_prototype_bom.csv", body_proto())
    write("body_production_bom.csv", body_prod())
    write("head_mech_prototype_bom.csv", head("mechanical/head/prototype/purchased_and_fabricated.csv"))
    write("head_mech_production_bom.csv", head("mechanical/head/production/bom_production.csv"))
