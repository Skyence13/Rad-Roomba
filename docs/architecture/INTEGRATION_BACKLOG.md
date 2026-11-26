# Integration backlog (cross-subsystem items the lead is tracking)

Open items raised by one subsystem that another must act on. Closed items move to the bottom with the commit that closed them.

| # | Raised by | Item | Owner of the fix | Status |
|---|---|---|---|---|
| IB-01 | Chassis electronics CCR-E02 | Read IOX_B P17 as `CHAIN_END_RB`; without it `ARM_PERMIT` has no readback. | Chassis firmware | Open |
| IB-02 | Chassis electronics CCR-E03 | Firmware constants: VREF+ 3.000 V; IPROPI 1.1205 V/A with a 2.68 A hardware limit; chain readbacks are node voltages live up to and including the element; `BRAKE_x_RB` valid only while the bridges sleep. | Chassis firmware | Open |
| IB-03 | Chassis electronics §3 | Align the emulator plant with the electronics brake model: 1.0 Ω brake resistor, 3.22 Ω loop, 31.7 V per m/s per motor, friction 16 N, reflected rotor inertia 8.3 kg per motor, 10.5 ms dead time; report nominal and conservative stop distances. | Chassis firmware | Open |
| IB-04 | Chassis firmware gap 2 | VL53L4ED driver is a stub; ST's driver must be integrated before any motion on hardware. | Chassis firmware / owner supplies driver | Open (external) |
| IB-05 | Chassis firmware gap 3 | Charger (LTC4162-F), INA228 and INA3221 drivers not written. | Chassis firmware | Open |
| IB-06 | Chassis electronics | LTC4162-F pin map, cell-count strap and JEITA defaults unverified (analog.com unreachable from the build machine). Must be checked against the datasheet before fabrication. | Chassis electronics / owner | Open (external) |
| IB-07 | Chassis electronics CCR-E10 | Both carrier USB ports are used by the two links; no port for a wired service adapter. Wi-Fi is the service path unless a hub or another carrier is chosen. | Lead decision | Open |
| IB-08 | Chassis electronics CCR-E05 | JST GH recalled as rated to −25 °C only; confirm or change the signal-connector family for the −25 °C objective. | Chassis electronics / harness | Open |
| IB-09 | Mechanical | SiPM front ends are about 65 mm ahead of the gearmotor cans with mount option C; printed prototype head has no inherent shielding. Needs a shield over the front ends and motor suppression at the motor terminals. | Head electronics, head mechanical, chassis electronics | Open |
| IB-10 | Mechanical | Carry attitude: robot hangs 15–20° tail-down with a head fitted (about 42° without). Target ≤ 10°. | Prototype/production body mechanical | Open |
| IB-11 | Mechanical CCR-08 | Head rail needs designed stroke: calculated travel after contact at 0.10 m/s is 14.3 mm (conservative electronics model) to 27.5 mm (contract inputs) against 7.4–11 mm lead. | Head mechanical | Open |
| IB-12 | Mechanical | Rear-edge connector space on RR-CHS-MAIN is 18 mm each side of the battery hump (u 0…18, 142…160). | Chassis electronics stage 2 | Open |
| IB-13 | Chassis firmware | MCU has no front or side ranging; front/side personnel stops come from the host LiDAR layer and the contact rails only. Personnel-protection section of the architecture document must say so. | Lead | Open |
| IB-14 | EDA | Stress board (150 parts) does not route to completion with automatic placement; plane fan-out, block replication and 6-layer support requested. | EDA infrastructure | Open |
| IB-15 | Head firmware | Analog scale factors and bias DAC transfer function are placeholders until the head circuit is final; waveform capture missing in the target port. | Head firmware | Open |
| IB-16 | Chassis electronics | Undetected single faults in the traction chain (open brake path, head-loop comparator failing healthy, welded latch contact, chain wire shorted to +12 V, …): decide which get a second channel or a periodic dynamic brake check. | Lead + chassis electronics | Open |
