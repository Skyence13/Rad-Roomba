# RR-HEAD-ACQ - ERC warning review

Source: `reports/erc.json` of `python3 tools/eda/rrkicad.py sch electronics/head_acq/board.py` (KiCad 9 ERC, all 31 sheets).
Result: **0 errors, 8 warnings**. Every warning is listed with the reason it is accepted; none is waived in the tool.

| # | Sheet | Type | Items | Reason accepted |
|---|---|---|---|---|
| 1-2 | /LANE0_LOGIC/ | pin_to_pin (bidirectional - power output) | U1007 pins 9 (S8) and 11 (S6) on GND; #FLG002 (PWR_FLAG on GND) | The unused inputs S6/S8 of the lane monitor mux TMUX1108 are tied to GND on purpose (mux codes 101/111 read ground, circuit.py `lane()`); the stock symbol types the switch terminals as bidirectional, and the tool's automatic PWR_FLAG on GND is a power output. A bidirectional analogue switch terminal on ground is correct. |
| 3-4 | /LANE1_LOGIC/ | same | U1107 pins 9, 11 | same (identical lane) |
| 5-6 | /LANE2_LOGIC/ | same | U1207 pins 9, 11 | same |
| 7-8 | /LANE3_LOGIC/ | same | U1307 pins 9, 11 | same |

ERC coverage notes
* All 1085 parts use symbols with typed pins: stock KiCad symbols for 1063 parts and eight project-local symbols (22 parts)
  (`libs.py`: TLV3502_DCN, LMR51606_DBV, TPS61391_RTE, DAC60508_RTE, ISO1430_DW, ISO7710_D, TMP117_DRV_EP and the
  pinless shield can) whose pin types were assigned from the datasheet pin functions, so ERC checks driver conflicts on
  every net (the previous import trial used 20 all-passive generated symbols and could not).
* Nets with power-input pins and no power-output pin get a PWR_FLAG on the root sheet (tool behaviour, listed in
  `reports/summary.json` -> `pwr_flags` after a build).
