"""Netlist export (kicad-cli) and cross-check against the board definition.

The KiCad netlist exported from the *generated schematic* is the authority used
to assign pad nets on the PCB; it is compared pin-by-pin with the definition so a
schematic-generation bug can never silently change connectivity.
"""
import subprocess

from .sexpr import parse, find, find_all
from .model import DefinitionError


def export_netlist(root_sch, out_path):
    r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out_path, root_sch],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("netlist export failed:\n" + r.stdout + r.stderr)
    return out_path


class Netlist:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            tree = parse(f.read())
        self.components = {}   # ref -> dict
        self.pin_net = {}      # (ref, pin) -> net
        self.nets = {}         # net -> [(ref, pin, pinfunction, pintype)]
        for comp in find_all(find(tree, "components") or [], "comp"):
            ref = str(find(comp, "ref")[1])
            sp = find(comp, "sheetpath")
            ts = find(comp, "tstamps")
            fields = {}
            for f in find_all(find(comp, "fields") or [], "field"):
                fields[str(find(f, "name")[1])] = str(f[2]) if len(f) > 2 else ""
            props = {}
            for p in find_all(comp, "property"):
                nm = find(p, "name")
                vl = find(p, "value")
                if nm is not None:
                    props[str(nm[1])] = str(vl[1]) if vl is not None and len(vl) > 1 else ""
            self.components[ref] = {
                "value": str(find(comp, "value")[1]),
                "footprint": str((find(comp, "footprint") or [None, ""])[1]),
                "sheet_names": str(find(sp, "names")[1]) if sp else "/",
                "sheet_tstamps": str(find(sp, "tstamps")[1]) if sp else "/",
                "tstamps": [str(t) for t in ts[1:]] if ts else [],
                "fields": fields, "props": props,
            }
        for net in find_all(find(tree, "nets") or [], "net"):
            name = str(find(net, "name")[1])
            for node in find_all(net, "node"):
                ref = str(find(node, "ref")[1])
                pin = str(find(node, "pin")[1])
                pf = find(node, "pinfunction")
                pt = find(node, "pintype")
                self.pin_net[(ref, pin)] = name
                self.nets.setdefault(name, []).append((ref, pin, str(pf[1]) if pf else "", str(pt[1]) if pt else ""))


def crosscheck(board, nets, nl):
    """Compare the definition's pin->net map with the exported netlist."""
    errs = []
    refs = {p.ref for p in board.parts}
    for ref in sorted(refs - set(nl.components)):
        errs.append("%s missing from schematic netlist" % ref)
    for ref in sorted(set(nl.components) - refs):
        errs.append("%s in schematic netlist but not in definition" % ref)
    for part in board.parts:
        for num, net in part.pin_net.items():
            got = nl.pin_net.get((part.ref, num))
            if net is None:
                if got is not None and not got.startswith("unconnected-("):
                    errs.append("%s.%s declared NC but schematic net is '%s'" % (part.ref, num, got))
            elif got != net:
                errs.append("%s.%s: definition net '%s' != schematic net '%s'" % (part.ref, num, net, got))
    for (ref, pin), net in nl.pin_net.items():
        if ref in refs and pin not in board.part(ref).pin_net:
            errs.append("%s.%s in schematic netlist but unknown to definition" % (ref, pin))
    if errs:
        raise DefinitionError("schematic/definition netlist cross-check FAILED (generator bug or bad symbol):\n  - "
                              + "\n  - ".join(errs[:60]))
    return True
