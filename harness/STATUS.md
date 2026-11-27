# Harness status

Stage-2 update done 2026-11-27 (IB-32..IB-37, IB-44). Last full run: `python3 harness/build.py` (exit 0) then `python3 harness/cross_check.py` (see below).

| File | State |
|---|---|
| connectors.yaml (143), pin_views.md | generated; chassis data = circuit.py + overrides.py (S2-xx), positions from the placed pinmaps |
| cables.csv (284 wires), cables.md (58 assemblies) | generated; W-044 removed, W-019 own cable, W-010 AWG 20, W-008 Mini-Fit Jr, look sensors renamed |
| cross_check.py, cross_check_report.md | extended (stage-2 netlist, pinmap.json checks A2..A2e, ToF length ERROR, look sensors, head stage 2); result FAIL with 2 errors, both OD-1 (ToF W-036/W-037 over 300 mm from the IB-34 mapping) |
| parts_status.md | generated; cables, contacts, tools, consumables added; nothing verified against a manufacturer page (web fetches failed) |
| README.md | stage-2 changes, IB-36 table, open decisions OD-1..OD-6 |

Re-run: `python3 harness/build.py && python3 harness/cross_check.py`. Edit the data in hdata_conn.py / hdata_cables.py / hdata_parts.py, never the generated outputs.
