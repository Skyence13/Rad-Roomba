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

## Measured (tool-checked)
Regressions with the new code: RR-TOF-A PASS (2 layers, escape off, DSN unchanged -> cached SES);
RR-PANEL PASS (rerouted by its engineer with this code, 2 layers, escape off).

| run | code state | Freerouting | result |
|---|---|---|---|
| STRESS-150 #1 | escape, before EP via | run 1 608 s (timeout) -> 1 open (QFN exposed pad), continue 29 s -> 0 | PASS, DRC 0 err / 27 warn (via_dangling), parity 0, 822 s total |
| STRESS-150 #2 | + via in exposed pad, fallback=continue | run 1 243 s -> 0 open | PASS, DRC 0 err / 24 warn, 286 s total |
| STRESS-150-6L #1 | same as #2 (+ paste-aperture fix) | run 1 112 s -> 0 open | PASS, DRC 0 err / 6 warn, 166 s total |

| STRESS-150 #3 | final escape code, before seeded continues / rip-up | run 1 549 s -> 1 open (IO46), continue 47 s -> 1 | **FAIL**, 1 open; finisher (no rip-up then): no free path - region walled off by autorouter tracks (flood-fill plot) |

Bugs found and fixed on the way: SES-import result corrupted by SWIG leak notices on stdout (import step
"failed"; now passed through a file); unused-escape clean-up removed escapes of still-open nets (now only
on a fully connected board); finisher via map inverted.

Since then: continue runs use a different item-order seed each and do not stop at the first
non-improving run; finisher got cluster start/goal sets, path smoothing, a coarse grid for big windows,
and rip-up-and-reroute (bounded cascade, all-or-nothing). On the STRESS-150 #3 leftover the rip-up
cascade ran 264 s and was undone (AUX06 could not be reconnected) - so the 4-layer stress board is
borderline: 2 of 3 fresh runs passed.

Finisher test (scratch copy of a passing STRESS-150-6L, routed copper of 7 nets deleted -> 8 open):
8 of 8 routed in 36 s, PASS, DRC 0 errors (1 track_dangling warning).

Formal repeatability series with the current code (2x 4-layer, 2x 6-layer, fresh route each): running.

Scale test `tests/scale500/` (493 parts, 160 x 100 mm, 6 layers, LQFP-100 + LQFP-64 + 2 QFN + 2 TSSOP,
40 SOT-23(-5), 13 connectors): generates; escape 199 vias + 4 direct on U1-U4, 1 pad without a legal
position; not yet routed.

Feedback from RR-CHS-MAIN (its engineer's `--no-route` build, read-only look): escape made 133 vias but
153 pads had no legal position - mostly vias that would land in courtyards of tightly placed neighbours,
and many small 10-pad 0.5 mm parts (USON-10 ESD arrays). Since then `escape_min_pads=16` (default)
leaves small packages to the autorouter.

## Next
1. Finish the repeatability series. 2. Route the scale test. 3. README results section.
