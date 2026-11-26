# Harness status

All deliverables written and generated. Last full run: build.py then cross_check.py.

| File | State |
|---|---|
| connectors.yaml (145 connectors), pin_views.md | done (generated) |
| cables.csv (288 wires), cables.md (59 assemblies) | done (generated) |
| lab_extension.md | done |
| cross_check.py, cross_check_report.md | done; result FAIL with 6 real errors (AWG 18 vs Micro-Fit contact range), 27 warnings |
| parts_status.md | done (generated) |
| README.md | done (build order, tools, open items OI-01..OI-22, contradictions) |

Re-run: `python3 harness/build.py && python3 harness/cross_check.py`. Edit the data in hdata_conn.py / hdata_cables.py, never the generated outputs.
