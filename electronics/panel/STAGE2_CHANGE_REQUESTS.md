# RR-PANEL stage 2: change requests

No netlist or BOM change: `board.py` imports `design/circuit.py` unchanged (24 parts, 15 nets).

| ID | Type | To | Item |
|---|---|---|---|
| P1 | placement | mechanical, harness | J1 and J2 (JST GH side entry, 4.25 mm) are fitted on the **top** side, mating face towards the v = 24 edge (cable leaves over that long edge), because the envelope allows 3 mm on the bottom and 8 mm on the top (CCR-E08(d) option b). `harness/cables.md` W-023 and `harness/connectors.yaml` PNL.J1 still say "bottom side, cable leaves along the long axis": please update, and confirm which board end faces +y in the robot. |
| P2 | BOM | — | Holes, fiducials and test pads (MPN "(pcb feature)") are marked "exclude from BOM" (matches the stock footprints). |
| P3 | note | mechanical | Mounting holes kept at the stage-1 proposal (3.5, 20.5) / (66.5, 20.5), M2.5, 6 mm copper keep-out: still to be confirmed by mechanical. |
