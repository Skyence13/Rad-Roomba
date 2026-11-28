# Gearmotor with encoder: Pololu #2828 (W10)

| Item | Value | Tag |
|---|---|---|
| Ordering code | Pololu item **#2828**, "150:1 Metal Gearmotor 37Dx73L mm 12V with 64 CPR Encoder (Helical Pinion)" | [D] pololu.com/product/2828 |
| No-load | 67 rpm, 0.2 A at 12 V | [D] |
| Stall (extrapolated by Pololu) | 5.5 A, 49 kg·cm (4.8 N·m) at 12 V | [D] |
| Recommended limits | 100 kg·mm continuous, 250 kg·mm instantaneous; ≤ 25 % of stall current for normal running | [D] 37D datasheet |
| Encoder | 2-channel Hall, 64 counts per motor rev = 9600 per output rev; supply 3.5–20 V, ≤ 10 mA; outputs need pull-ups | [D] product text [U] pull-up detail |
| Temperature rating | none published | [U] cold grease and brush behaviour are test items |
| Derived model | R = 2.18 Ω; 31.7 V per m/s at the ground (104 mm wheel); 869 rpm/V at the motor; 0.907 N·m/A at the output | [C] |
| Not published | winding inductance (2.5 mH assumed), rotor inertia (0.5–2 × 10⁻⁶ kg·m² assumed) | [A][U] |

**Cable.** Six-wire pigtail, re-terminated to a Micro-Fit 2×3 receptacle (J_MOT_L / J_MOT_R): 1 motor A (red), 2 motor B (black), 3 encoder 5 V (blue), 4 encoder GND (green), 5 A (yellow), 6 B (white) [D colours from the product page; confirm on the part].

**Drive on the board.** DRV8874 per motor, 20 kHz PWM, hardware current limit 2.68 A (49 % of stall; stall thrust about 2 × 43 N [C], above the traction limit estimate), firmware limit lower. Encoder: 5 V through a 0.1 A PTC, 10 kΩ pull-ups, 34 kHz RC, Schmitt buffers to 3.3 V; maximum edge rate 10.7 kHz at no-load speed [C]. At a full 14.4 V pack the no-load speed is 0.44 m/s: firmware caps the duty.

**Braking.** 1.0 Ω brake resistor through the DPDT relay; see `electronics/analysis/chassis_safety_chain.md`.

**Prototype → production.** Same part for the prototype and first production units. Open: a gearmotor with a published temperature range and inertia (maxon/Faulhaber class) if the cold trial shows start-up or wear problems; the bridge and current limit cover up to 3.5 A continuous motors without a board change.
