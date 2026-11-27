# RR-CHS-MAIN ERC warnings review

Run: `python3 tools/eda/rrkicad.py sch electronics/chassis_main/board.py` (also part of every `build`), KiCad 9.0.9 ERC.

Result: **0 errors, 0 warnings, 0 waived** (`reports/erc.json`). Nothing to review.

What was fixed on the way (stage 2):

| Item | Fix |
|---|---|
| `pin_to_pin` error: U42 BMI088 SDO1 (pin 15) and SDO2 (pin 10) are both type *output* and share IMU_SDO (stage-1 design: one SDO line, the inactive CSB tri-states its SDO) | Local symbol `rr_local:BMI088_SPI` (pin numbers/names as the stock `Sensor_Motion:BMI088`) with SDO1/SDO2 typed *tri_state*, which is what the device does. No netlist change. |
| The 112 warnings of the earlier importer trial (`tools/eda/tests/import_chassis`) | Not reproduced: the rails are declared with `board.rail()` (power symbols), the stock symbols for the SOT-23/SON FETs, TCA9534, G2RL-2, BMI088 are now used with matching pin numbers, and 2-terminal shunts use `Device:R`. |

Limitation (not an ERC finding): 12 parts use generated box symbols with all pins *passive*
(LM74502, LTC4162-F, LM61460, LMR51610, TPS259470, INA3221, TPS2553, TPS3430, TPS25982, DRV8874, SM712, AOD4185),
so ERC cannot check pin directions on them. Their pin names/numbers are the stage-1 tables (several marked [U]).
