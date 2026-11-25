""".kicad_pro generation (design rules, net classes, severities, text variables)."""
import copy
import json
import os

_TEMPLATE = os.path.join(os.path.dirname(__file__), "data", "project_template.json")


def build_project(board, sheets):
    """Return the .kicad_pro dict.  *sheets*: [(uuid, name)] with the root first."""
    with open(_TEMPLATE) as f:
        pro = json.load(f)
    r = board.rules
    ds = pro["board"]["design_settings"]
    ds["rules"].update({
        "min_clearance": r.min_clearance,
        "min_track_width": r.min_track,
        "min_via_diameter": r.min_via_dia,
        "min_through_hole_diameter": r.min_hole,
        "min_via_annular_width": r.min_annular,
        "min_copper_edge_clearance": r.edge_clearance,
        "min_hole_clearance": r.min_hole_clearance,
        "min_hole_to_hole": r.min_hole_to_hole,
        "min_text_height": r.min_silk_text,
        "min_text_thickness": r.min_silk_thickness,
        "min_silk_clearance": r.silk_clearance,
    })
    ds["defaults"]["zones"]["min_clearance"] = r.clearance
    # pre-defined sizes offered in the GUI
    widths = sorted({r.track} | {nc["track"] for nc in board.netclasses})
    ds["track_widths"] = [0.0] + widths
    vias = sorted({(r.via_dia, r.via_drill)} | {(nc["via_dia"], nc["via_drill"]) for nc in board.netclasses})
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}] + [{"diameter": d, "drill": h} for d, h in vias]

    def cls(name, track, clearance, via_dia, via_drill, prio, dw=None, dg=None):
        c = {"bus_width": 12, "clearance": clearance, "diff_pair_gap": dg or 0.25, "diff_pair_via_gap": 0.25,
             "diff_pair_width": dw or track, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
             "name": name, "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": prio,
             "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": track, "via_diameter": via_dia,
             "via_drill": via_drill, "wire_width": 6}
        return c
    classes = [cls("Default", r.track, r.clearance, r.via_dia, r.via_drill, 2147483647)]
    patterns = []
    for i, nc in enumerate(board.netclasses):
        classes.append(cls(nc["name"], nc["track"], nc["clearance"], nc["via_dia"], nc["via_drill"], i,
                           nc.get("diff_width"), nc.get("diff_gap")))
        for pat in nc["nets"]:
            patterns.append({"netclass": nc["name"], "pattern": pat})
    pro["net_settings"]["classes"] = classes
    pro["net_settings"]["netclass_patterns"] = patterns
    for s in board.severities:
        if s["check"] == "drc":
            ds["rule_severities"][s["rule"]] = s["level"]
        else:
            pro["erc"]["rule_severities"][s["rule"]] = s["level"]
    pro["meta"]["filename"] = board.name + ".kicad_pro"
    pro["sheets"] = [[u, n] for u, n in sheets]
    pro["text_variables"] = {"BOARD": board.name, "REV": board.rev, "DATE": board.date,
                             "DOCNUM": board.docnum, "TITLE": board.title}
    return pro


def write_project(path, pro):
    with open(path, "w") as f:
        json.dump(pro, f, indent=2, sort_keys=True)
        f.write("\n")
