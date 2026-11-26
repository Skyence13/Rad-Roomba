# Battery pack and coupler (W28, E01, R01, R02)

| | Baseline: Power-Sonic **PSL-SC-12120** (DEC-040) | Comparison: Power-Sonic PSL-SC-1290 |
|---|---|---|
| Nominal | 12.8 V, 12 Ah, 153.6 Wh | 12.8 V, 9 Ah, 115.2 Wh |
| Dimensions, mass | 151 × 99 × 95 (101 over terminals) mm, 1.65 kg [D] | 151 × 65 × 94 (99) mm, 1.0 kg [M] |
| Max continuous discharge | 15 A [D] | 15 A [U: Power-Sonic technical document via search result] |
| BMS over-current | 25 A / 10 s, 30 A / 3 s; short circuit 60 A / 0.5 ms; over-charge current 20 A / 10 s [D] | assumed equal [U] |
| Temperature | discharge −20…+60 °C, charge 0…+45 °C [D] | same [M partial] |
| Terminals | F2 (6.35 mm faston) [M] | F2 |
| Maker's charger | PSC-124000-LIFE (4 A) [D] | — |

The −20 °C discharge limit equals the operating target and −25 °C is outside it: the bay heater and a warm start are mandatory, and Power-Sonic must confirm the BMS behaviour below −20 °C cell temperature [M].

**Cassette.** The monobloc sits in a removable cassette carrying: one half of the coupler, a 10 kΩ NTC (B ≈ 3435–3490) bonded to the case and returned to pack negative, and a presence link to pack negative. F2 terminals are not a field connection: they are wired once, inside the cassette, with insulated fastons and AWG 12 leads.

**Coupler.** Candidate: Anderson Power **SBS50** with two auxiliary contacts (finger-proof, keyed, 50 A class) [M][U: housing colour/key code, auxiliary contact kit and −40 °C rating not confirmed]. Main contacts: pack +/−. Auxiliary 1: PACK_NTC; auxiliary 2: PACK_PRES_N. Board side: J_PWR pins 1/2 (+), 5/6 (−); J_PAUX pins 1, 2.

**Main fuse.** 20 A blade fuse (32 V, ≥ 1 kA interrupting rating), in the bay harness within 150 mm of the bulkhead half of the coupler; a second, identical fuse inside the cassette at the positive terminal is recommended so a detached cassette is also protected [A]. Peak design current 12.5 A [C].

**Charging on the robot.** 3.0 A (0.25 C) from the on-board LTC4162-F to 14.4 V (3.60 V/cell), about 3.7 h from the 20 % reserve [C]. The pack's own BMS remains the last line for over-voltage, low temperature and over-current.

**Runtime.** `electronics/analysis/power_budget.md` §3 and §8: 125 min continuous survey at −20 °C, 139 min step-and-count, 337 min at +20 °C [C].

**Prototype → production.** Same pack. Each pack is marked with an ID and tracked (R02). Open before purchase: UN 38.3 documentation for shipping, low-temperature discharge confirmation, and whether the pack can be woken by the on-board charger after a BMS under-voltage latch (the design assumes not).
