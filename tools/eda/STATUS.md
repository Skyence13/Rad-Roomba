# rrkicad status (EDA infrastructure work package)

Last update: 2026-11-27. All results below were tool-checked (KiCad 9.0.9 DRC/ERC, Freerouting 2.6.0)
unless marked "not yet run".

## Implemented
| feature | where | state |
|---|---|---|
| Fine-pitch escape (fan-out) for IC pads, locked pre-routes, exported to the DSN as fixed wiring of the net | `rrkicad/escape.py`, `rrkicad/geom.py` | implemented; generation tested on STRESS-150 (101 of 101 connected pads of U1 LQFP-64 + U2 QFN-48 escaped, 0 DRC errors before routing) |
| Via in the exposed pad (thermal pad) of plane nets in the plane fan-out | `rrkicad/fanout.py` | implemented, **not yet tested** in a routed build |
| Wider auto-arrange keep-away around escaped ICs (`autoplace_options(escape_keepaway=2.0)`) | `rrkicad/autoplace.py` | implemented, used by STRESS-150 |
| Finisher: grid A* maze router for connections still open after Freerouting (exact re-check, stored in `route/finish.json`, re-applied on cached builds) | `rrkicad/finisher.py`, `cli.py` stage `_finish` | implemented; a via-map inversion bug was found and fixed; on the OLD STRESS-150-6L result (no escape) it routed 0 of 4 (no free path without rip-up) |
| `summary.json` → `routing.escape`, `routing.plane_fanout`, `routing.finisher` | `checks.py` | implemented |

API added (backwards compatible): `board.route(escape="auto"|True|False, escape_pitch=0.65,
escape_layers=None, escape_via=None, escape_track=None, escape_direct=True, finisher=True)`,
`part(..., escape=None|True|False)`, `board.autoplace_options(escape_keepaway=2.0)`.
`escape="auto"` = on for 4/6-layer boards only, so 2-layer boards (RR-TOF-A, RR-PANEL) are unchanged.

## Measured
* STRESS-150 (4 layers), one fresh route with escape (before the exposed-pad via change):
  Freerouting run 1 608 s (timeout) -> 1 open (U2 exposed pad GND), continue run 2 29 s -> 0 open.
  **PASS**: ERC 0, DRC 0 errors / 27 warnings (via_dangling: unused escape vias), unconnected 0, parity 0.
  Total build 822 s. Repeat run: not yet done.
* STRESS-150-6L with escape: not yet run.
* Scale test (~500 parts, 160 x 100 mm, 6 layers): not yet built.
* Regressions RR-TOF-A / RR-PANEL after these changes: not yet run.

## Next
1. Regressions (RR-TOF-A, RR-PANEL). 2. STRESS-150 + STRESS-150-6L twice each from a fresh route.
3. Scale test. 4. README update.
