# Harness status

Stage-2 update done 2026-11-27 (IB-32..IB-37, IB-44). Last full run: `python3 harness/build.py` (exit 0) then `python3 harness/cross_check.py` (see below).

| File | State |
|---|---|
| connectors.yaml (143), pin_views.md | generated; chassis data = circuit.py + overrides.py (S2-xx), positions from the placed pinmaps |
| cables.csv (284 wires), cables.md (58 assemblies) | generated; W-044 removed, W-019 own cable, W-010 AWG 20, W-008 Mini-Fit Jr, look sensors renamed |
| cross_check.py, cross_check_report.md | extended (stage-2 netlist, pinmap.json checks A2..A2e, ToF length ERROR, look sensors, head stage 2); result PASS, 0 errors, 34 warnings (OD-1 and OD-6 closed by the lead) |
| parts_status.md | generated; cables, contacts, tools, consumables added; nothing verified against a manufacturer page (web fetches failed) |
| README.md | stage-2 changes, IB-36 table, open decisions OD-2..OD-5 (OD-1, OD-6 closed) |

Re-run: `python3 harness/build.py && python3 harness/cross_check.py`. Edit the data in hdata_conn.py / hdata_cables.py / hdata_parts.py, never the generated outputs.

Stage-3 update (2026-11-27): W-018 relabelled and shorts analysed, W-019 (Pause at y -122), W-101/W-103 +7 mm and AWG 20 heater conductors with splices SPL-JH3/4, motor suppression assembly items, heater-insulation and E7 test notes (cables.md sections 6-8), cross-check reads the stage-3 netlist (IOX_D checks, D_RB hop) and no longer reads cable_lengths.json. Open: OD-2, OD-3 (heater protection gap), OD-5.
