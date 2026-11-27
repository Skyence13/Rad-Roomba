# rrkicad status (EDA infrastructure work package)

Last update: 2026-11-27. Every result below was tool-checked (KiCad 9.0.9 ERC/DRC with schematic parity,
Freerouting 2.6.0) on a shared 4-core machine; nothing here is estimated unless it says so.

## What the flow does now (additions in this work package)
| feature | where | API |
|---|---|---|
| Fine-pitch escape: stub + via ring (two staggered, fanned rows), plane pads under QFPs, direct pre-route to a nearby passive, local search; locked pre-routes exported to the DSN as fixed wiring of the net | `rrkicad/escape.py`, `rrkicad/geom.py` | `route(escape="auto"/True/False, escape_pitch=0.65, escape_min_pads=16, escape_via, escape_track, escape_layers, escape_direct)`, `part(escape=...)`, `autoplace_options(escape_keepaway=2.0)` |
| Plane fan-out: pairwise clearance, footprint rule areas + net-tie copper as obstacles, via in exposed pads, **extended fan-out** (via spot up to 4 mm, straight/L stub), **long fan-out** (maze route to a via inside the own plane, incl. through-hole pins outside their plane) | `fanout.py`, `finisher.plane_connect` | `long_fanout_seconds=600` |
| Zone nets never autorouted on 4/6 layers (DSN classes `RR_ZONE_*` ignored by Freerouting) | `pcb.export_dsn` | `route(zone_nets="auto"/"exclude"/"route")` |
| Routing session: first run, seeded continue runs from the routed board, fresh restarts with another seed, wall-clock budget with capped chunks, quick imports, best SES always on disk (`.ses.best`), `route/progress.log`; no more runs when only zone-net pads are open | `cli._Router` | `build --budget SEC`, `route(retries=2, restarts=1, budget, chunk=900, stall=2, fr_fallback="none")` |
| Finisher: grid A* (0.05/0.1 mm), cluster start/goal, smoothing, exact re-check, rip-up-and-reroute of autorouter copper (bounded, all-or-nothing), stored in `route/finish.json` and replayed on cached builds | `rrkicad/finisher.py` | `route(finisher=True, finisher_ripup=True, finisher_seconds=900)` |
| Reports: unconnected = connectivity count (not capped at 499), `reports/open_connections.txt`, `routing.escape / plane_fanout / finisher` in summary.json | `checks.py` | - |

## Defects reported by the board engineers (IB-45, IB-54)
| # | defect | fix | verified |
|---|---|---|---|
| 1 | continue run crashes in `_edge_guard` ('SwigPyObject' ... 'NewOutline') | root cause: objects created after `BOARD.Remove()` in the same pcbnew process get broken SWIG proxies; export_dsn adds rule areas first, removes last | yes: head copy ran 2 continue runs on a board with outer pours |
| 2 | post-stage crash in the unused-escape clean-up; finisher then ran on an un-imported board | same root cause: victims collected first, removed in one step; finisher replay moved into the import subprocess; `_post` records the imported SES hash and the host checks it before the finisher | yes: all builds since (stress, head copy, cached replays) |
| 3 | fan-out vias checked with their own net-class clearance only | pairwise clearance (larger class) | yes: head copy, no fan-out clearance errors |
| 4 | fan-out ignores footprint rule areas and net-tie copper (via through NT1) | both are obstacles for fan-out / escape / finisher; DSN gets via keep-outs (+ same-layer track keep-outs minus the tie's pads) over net-tie copper | code; the chassis copy (has NT1) is in the running chain |
| 5 | "no parts" rule area exported as a full B.Cu routing keep-out | rule areas banning neither tracks nor vias are not exported | code (the chassis engineer had removed that area) |
| 6 | summary unconnected capped at 499 | connectivity count + `unconnected_listed` | yes: head copy 707 / 958 reported |
| 7 | replicated block vias co-located with fan-out vias (66-199 warnings) | replay skips copper already on the board; save stores only router copper + definition pre-routes, de-duplicated | yes: head copy 0 `holes_co_located` (original: 199) |
| 8 | local footprints need >= 1 pad | pad-less allowed with body=/courtyard= | code only |
| 9 | importer ignores local symbol hints | `rr_local:NAME` hints accepted | code only |
| 10 | auto-arranger ignores replicate destinations | copies' spots must be free and are reserved | code only (both real boards place explicitly) |
| - | BOM-excluded footprints need `bom=False` for parity | unchanged, documented KiCad behaviour | - |
| open | replicated copies not checked against keep-outs (head copy: 1 via in a lane-1 keep-out) | - | open |
| open | footprint-level clearance overrides not passed to Freerouting (head copy: 1 clearance error at U2001) | - | open |

## Measured
Regressions (current code): RR-TOF-A PASS, RR-PANEL PASS (both 2 layers, DSN unchanged, cached SES).

| board | flow | result |
|---|---|---|
| STRESS-150 (4 L) | before this work package | FAIL, 6 of 377 open after 25 min |
| STRESS-150 (4 L) | escape + continues + restart, runs A/B | PASS x2, 18 min each (restart needed) |
| STRESS-150 (4 L) | final code (zone nets excluded, long fan-out, fallback none) | **PASS**, first run 274 s -> 0 open, 337 s total, DRC 0 err, parity 0 |
| STRESS-150-6L | before | FAIL, 4 open after 22 min |
| STRESS-150-6L | escape, runs A/B | PASS x2, 90 s each |
| STRESS-150-6L | final code | **PASS**: 84 s -> 2 open (zone-net pads), finisher routed both; 335 s total (before the "no runs for zone-only leftovers" change: 4 futile runs included) |
| finisher test | 6L copy, copper of 7 nets deleted (8 open) | 8/8 routed in 36 s, PASS |
| rip-up test | 4L, 4 open | 2/4 routed with rip-up (7 / 13 nets rerouted), DRC 0 errors |
| RR-HEAD-ACQ copy (`tests/head_escape`) | escape on, zone nets excluded, `--budget 2400` (before the extended fan-out) | 1041 items; 930 s -> 795, 945 s -> 741, 378 s -> 712; finisher 6 routed in 900 s; **FAIL 707 open**, DRC 2 errors, parity 0, 71 min |
| RR-HEAD-ACQ original (lead) | escape off, zone nets autorouted, no continue runs | 1 h 45 min -> 340 open, 3 DRC errors |
| scale500 | 493 parts, 6 L | generation only (0 DRC errors from escape, 199 escape vias + 4 direct); not routed - the real boards were the better evidence |

Running (unattended, `tools/eda/tests/run_real_boards.sh`, results appended to
`tools/eda/tests/real_boards_results.jsonl`): head copy `--budget 3000`, then chassis copy `--budget 3000`.

## Honest assessment
* 150-part boards with 0.5 mm ICs: complete automatically (6 layers in 1.5-6 min, 4 layers in 6-18 min).
* 770-1090-part boards: the flow runs them without crashes and keeps its best state, but Freerouting reduces
  the open count by only ~50 per 15-minute run late in the job; zero needs placement changes (room for plane
  vias and escape rings), hand pre-routes for power/HV/analogue, frozen lane routes, several long runs and a
  final manual pass in KiCad. See README "Real boards".
