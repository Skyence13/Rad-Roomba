# RR-PANEL rev A — annunciator panel (stage 2, KiCad 9)

| | |
|---|---|
| Netlist source | `design/circuit.py` (stage 1, reviewed baseline — not edited) |
| Board definition | `board.py` (the only hand-edited file; everything else is generated) |
| Board | 70 × 24 mm, 2 layers, 1.6 mm, 24 parts (19 fitted + 2 holes, 2 fiducials, 3 test pads), 15 nets |
| Result | **PASS** — ERC 0 errors / 0 warnings, DRC 0 errors / 0 warnings, 0 unconnected, schematic parity 0, netlist cross-check OK (24 components, 15 nets) |

## Commands

```
python3 electronics/panel/design/circuit.py                 # stage-1 self-check
python3 tools/eda/rrkicad.py build electronics/panel/board.py   # schematic, PCB, route (cached SES), ERC, DRC, all outputs (~25 s)
python3 tools/eda/rrkicad.py build electronics/panel/board.py --reroute   # force a fresh Freerouting run (~15 s routing)
python3 tools/eda/rrkicad.py check electronics/panel/board.py   # re-run ERC/DRC on the existing files
```

Outputs (`out/`): `RR-PANEL-schematic.pdf`, `gerber/` (Gerbers, PTH/NPTH Excellon, drill maps, job file),
`RR-PANEL-pos.csv`, `RR-PANEL-bom.csv`, `RR-PANEL-fab.pdf`, `RR-PANEL-assembly-top.pdf` / `-bottom.pdf`,
`RR-PANEL-copper.pdf`, `RR-PANEL.step`, `RR-PANEL-render-top.png` / `-bottom.png`, `pinmap.json`, `RR-PANEL.net`.
Reports: `reports/summary.json` (status, counts, BOM verify list), `reports/erc.*`, `reports/drc.*`,
`reports/import_report.json` (importer: 24 stock symbols, 0 local, 0 rejected hints, 0 missing footprints).
The routing result is `route/RR-PANEL.ses` + `route/route_meta.json` (keep under version control: the build re-uses it).

## Frame mapping

`circuit.py` / envelope board frame (u, v) → tool board frame (X, Y) = (u, v), no rotation, no offset.
Origin = lower-left corner seen from the top (component) side; X along the 70 mm axis in the LED order
READY (u 9) … FAULT (u 61); Y along the 24 mm axis. Pick-and-place, `pinmap.json`, the STEP model and
the drill origin use this frame. The board's orientation in the robot (`board_envelopes.yaml` RR-PANEL:
long axis along base y, component side up) does not say which end of u points to +y: **mechanical to
confirm** which edge the J1 cable leaves over (see below).

## What is tool-checked

ERC (0/0), DRC with schematic parity (0/0, 0 unconnected), pin-by-pin netlist cross-check of the generated
schematic against the definition (which is `circuit.py` imported 1:1), courtyards, edge clearance, hole
keep-outs (6 mm copper keep-out around H1/H2). **Not** checked by a tool: light-pipe alignment, the
mechanical fit in the shell, LED brightness, sounder level.

## Deviations from stage 1 (placement only — no net or part changes)

| # | What | Why |
|---|---|---|
| P1 | J1 and J2 are on the **top** side (stage 1: bottom side), at (30, 20.6) and (49.5, 20.6), mating face towards the v = 24 edge; the cable leaves over that long edge, not along the long axis | Envelope: bottom 3 mm max, GH side-entry header 4.25 mm. CCR-E08(d) offered "allow 4.5 mm or move them to the top"; no 4.5 mm allowance was granted (`board_envelopes.yaml` still says 3 mm), top allows 8 mm. A 10-pin GH (17 mm with pegs) cannot face a short edge: with H2's keep-out only 16 mm of the 24 mm edge is free. `harness/cables.md` W-023 / `harness/connectors.yaml` PNL.J1 still say "bottom side" — harness to update. |
| P2 | Holes, fiducials and test pads (`(pcb feature)` MPN) are excluded from the BOM | The stock footprints carry "exclude from BOM"; matching the symbol avoids a parity mismatch. They remain in the schematic and the PCB. |
| P3 | Silkscreen legend per LED (READY, MOVING, HOLD, CHARGE, FAULT) next to each LED on the top side | Assembly/service aid only. |

## Open items / UNVERIFIED

* `verify=True` from stage 1 (BOM notes): LED1–LED5 (Würth MPNs, intensity through the light pipe), BZ1 (Murata PKLCS1212E data recalled; sound level probably too low — fit the external sounder on J2).
* Mounting-hole positions (3.5, 20.5) / (66.5, 20.5) are the stage-1 proposal; mechanical gave none.
* Cable exit over the v = 24 edge (P1) and which board end faces +y in the robot: mechanical/harness to confirm.
* JST GH −25 °C rating (CCR-E05) unchanged.
* Only two top-side fiducials (as in `circuit.py`); the bottom side has no fiducials — acceptable for 0603/0805/SOD-123 and the 12 mm buzzer, add two if the assembler asks.
