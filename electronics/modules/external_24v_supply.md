# External 24 V charge supply and inlet (W29, R03)

| Item | Value | Tag |
|---|---|---|
| Requirement | 24 V DC ±5 %, ≥ 60 W continuous, SELV, isolated output, operating at the lowest temperature at which charging is attempted (pack ≥ +5 °C, room may be colder) | [C] 56 W demand, `power_budget.md` §2 |
| Candidate | Mean Well **GST90A24-P1M** desktop adapter, 24 V / 3.75 A, 90 W, Level VI | [U] rating, −30…+70 °C operating range and output plug recalled; confirm on the Mean Well sheet |
| Board input | 4.5–35 V at the charger; reverse-polarity protected (Q3), 5 A fuse, 28 V TVS; input current limit 4.0 A | [D] LTC4162 input range; [U] limit resistor |
| Inlet on the robot | M12 **L-coded**, 4 + FE, male panel receptacle under a hinged cover (mechanical candidate, adopted) | [M][U] part number with the harness lead |
| Inlet pins | 1: +24 V; 2: LINK_A; 3: 0 V; 4: LINK_B (0 V at the board); FE: chassis | proposal |
| Plug (on the supply's lead) | M12 L-coded female, pins 2–4 linked inside the plug | touch-safe source side |
| Cover switch | Omron D2HW-C201M, NC contact closed with the cover shut, to J_COVER | [M] |

**Interlock.** Three hardware channels open the traction chain when charging: the cover switch (element CHG_COVER), the plug link (opens photo-MOS U20 even with an unpowered cable), and inlet voltage above about 10 V (Q21, same photo-MOS). The same inlet-voltage signal forces the head branches off. L-coding cannot mate with the A-coded J2 or the M16 J1.

**Harness.** Inlet → J_PWR pins 3 (+), 7 (0 V), 4 (LINK_A), 8 (LINK_B); AWG 18 for power, AWG 24 for the link; 60 mΩ total path, 0.24 V at 4 A [C].

**Prototype → production.** Bench: laboratory supply at 24 V, 3 A limit. Installed: the adapter above with its DC plug replaced by the M12 plug. Production: same, with a strain-relieved moulded lead.
