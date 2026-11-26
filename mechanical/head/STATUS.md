# mechanical/head status

## Done (on disk)
- `hp.py` (parameters, datums imported from mechanical.common.params), `geom.py`, `parts.py` (all part families, both builds, dummy, cradle, gauges),
  `assembly.py` (prototype / production / dummy part lists), `calc.py` (deflection, modes, rails, light paths, tolerance stack, thermal),
  `checks.py` + `report.py` (out/checks.json, out/head_report.md), `export.py` (STEP / print-orientation STEP+STL+3MF / plates.yaml).
- Design decisions taken for the board requests: J1 blister (8.9 mm), FRAME bonding scheme, coax chimney, lane shield can, lid interlock switch.

## In progress
- Clearing the last interference findings, then first full export of STEP files.

## Not started
- DXF + drawings (production fabrication drawings, joint sections), assembly renders and assembly.md, BOM csv, production docs, README, build.sh.
