"""Import a tool-neutral circuit definition (stage-1 ``circuit.py``) into a Board.

The module must expose ``PARTS``: a list of dicts with the keys
``ref, value, mpn, manufacturer, description, package, symbol_hint, footprint_hint,
pins={pin_number: (pin_name, net) | None}, block, dnp, notes`` (optional: ``verify``,
``height_mm``).  One schematic group is created per ``block``.

    from rrkicad import Board
    from rrkicad.importer import from_circuit
    board = Board("RR-CHS-MAIN", ...)
    report = from_circuit(board, "design/circuit.py",
                          footprints={"U7": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"},   # by ref or by package
                          symbols={"U7": "Amplifier_Operational:LM358"},              # by ref
                          place={"J_PWR": (10, 50, 90, "F")})                         # at= by ref
    # then: board.rail(...), board.netclass(...), outline, zones, placement ...

Symbol choice per part: ``symbols[ref]`` > ``symbol_hint`` if that stock symbol exists and
has every pin number the part uses > a generated local box symbol (all pins passive)
built from the pin list.  Parts without a footprint (no hint, nothing in ``footprints``)
are listed in ``report["missing_footprints"]`` and raise unless ``allow_missing=True``.
"""
import importlib.util
import os
import re

from .model import SymPin, DefinitionError
from .symlib import SymbolLibs


def _load(module_or_path):
    if isinstance(module_or_path, str):
        path = os.path.abspath(module_or_path)
        spec = importlib.util.spec_from_file_location("rr_circuit_%s" % abs(hash(path)), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    return module_or_path


def from_circuit(board, module_or_path, footprints=None, symbols=None, place=None, titles=None,
                 allow_missing=False, libs=None):
    mod = _load(module_or_path)
    footprints, symbols, place, titles = footprints or {}, symbols or {}, place or {}, titles or {}
    libs = libs or SymbolLibs()
    groups = {g.name: g for g in board.groups}
    report = {"parts": 0, "local_symbols": {}, "stock_symbols": 0, "missing_footprints": [], "hint_rejected": []}
    local_by_sig = {}
    for p in mod.PARTS:
        ref = p["ref"]
        block = re.sub(r"[^A-Za-z0-9_\-]", "_", str(p.get("block") or "misc"))
        if block not in groups:
            groups[block] = board.group(block, titles.get(block, block))
        pins, nc, names = {}, [], {}
        for num, v in p["pins"].items():
            num = str(num)
            if v is None or v[1] is None:
                nc.append(num)
                names[num] = (v[0] if v else num) or num
            else:
                pins[num] = v[1]
                names[num] = v[0] or num
        sym = symbols.get(ref)
        hint = p.get("symbol_hint")
        if sym is None and hint:
            try:
                sd = libs.get(hint)
                have = {q.number for q in sd.pins}
                stacked = {}
                for q in sd.pins:
                    stacked.setdefault((q.unit, round(q.x, 3), round(q.y, 3)), set()).add(pins.get(q.number))
                if any(len(v) > 1 for v in stacked.values()):
                    report["hint_rejected"].append("%s: %s has stacked pins that this part puts on different nets" % (ref, hint))
                elif set(names) <= have:
                    sym = hint
                else:
                    report["hint_rejected"].append("%s: %s lacks pin(s) %s" % (ref, hint, sorted(set(names) - have)))
            except KeyError as e:
                report["hint_rejected"].append("%s: %s" % (ref, e.args[0]))
        if sym is None:
            sig = tuple(sorted(names.items()))
            if sig not in local_by_sig:
                base = re.sub(r"[^A-Za-z0-9_\-\.]", "_", str(p.get("mpn") or p.get("value") or ref))[:40] or ref
                name = base
                k = 2
                while name in board.local_symbols:
                    name = "%s_%d" % (base, k)
                    k += 1
                order = sorted(names, key=lambda n: (0, int(n)) if n.isdigit() else (1, n))
                half = (len(order) + 1) // 2
                sp = [SymPin(n, names[n], "passive", "L" if i < half else "R") for i, n in enumerate(order)]
                local_by_sig[sig] = board.symbol(name, sp, ref_prefix=re.match(r"[A-Za-z]+", ref).group(0) if re.match(r"[A-Za-z]+", ref) else "U",
                                                 description=str(p.get("description") or ""))
                report["local_symbols"][name] = ref
            sym = local_by_sig[sig]
        else:
            report["stock_symbols"] += 1
        fp = footprints.get(ref) or p.get("footprint_hint") or footprints.get(p.get("package"))
        if not fp or ":" not in str(fp):
            report["missing_footprints"].append("%s (%s, package %s)" % (ref, p.get("value"), p.get("package")))
            if allow_missing:
                continue
        notes = str(p.get("notes") or "")
        groups[block].part(ref, sym, p.get("value") or "", fp, mpn=p.get("mpn") or "", mfr=p.get("manufacturer") or "",
                           pins=pins, nc=nc, unused="nc", dnp=bool(p.get("dnp")), notes=notes,
                           verify=bool(p.get("verify")), description=p.get("description"),
                           height=p.get("height_mm") or None, at=place.get(ref))
        report["parts"] += 1
    if report["missing_footprints"] and not allow_missing:
        raise DefinitionError("from_circuit: parts without a footprint (give footprints={ref or package: 'Lib:Name'}):\n  - "
                              + "\n  - ".join(report["missing_footprints"]))
    return report
