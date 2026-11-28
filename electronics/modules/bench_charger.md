# Spare-pack bench charger (R10)

| Item | Value | Tag |
|---|---|---|
| Purpose | Charge a second cassette off the robot so step-and-count missions can swap packs | contract `survey_methods` |
| Candidate | Power-Sonic **PSC-124000-LIFE**, 4-series LiFePO₄ charger, 4 A | [D] named on the PSL-SC-12120 sheet; [U] input range, temperature range, connector |
| Charge time, 12 Ah from reserve | about 2.9 h | [C] |
| Cradle | Mating half of the cassette coupler (SBS50 with auxiliaries) on a bench cradle; the cradle wires the charger to the main contacts and leaves the auxiliaries open | design intent |
| Temperature gating | The pack BMS refuses charge below 0 °C [D]; the bench charger has no access to the cassette NTC unless a qualified charger with an NTC input is chosen | **gap**: cold packs must warm to room temperature before bench charging (procedure) |

Also needed for recovery of a pack whose BMS has latched on under-voltage: the on-board charger cannot reach a pack through the open main switch.

**Prototype → production.** Same unit; label the charger/pack pairing and fit a contact cover on the cradle.
