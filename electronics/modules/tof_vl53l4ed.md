# Near-field ranging: ST VL53L4ED on RR-TOF (W19, W20, W21)

| Item | Value | Tag |
|---|---|---|
| Sensor | STMicroelectronics **VL53L4ED** (extended-temperature VL53L4CD), ordering code VL53L4EDV0DH/1 | [U] ordering suffix (RR-TOF-A notes it unchecked) |
| Temperature | −40…+105 °C | design text §8 [U] |
| Supply | 2.6–3.5 V; about 20 mA average while ranging, 40 mA peak | [U] |
| Interface | I²C up to 1 MHz, fixed address 0x29; XSHUT, GPIO1 | [U] |
| Carrier | RR-TOF-A, 18 × 14 mm, JST GH 6-pin: 1 +3V3, 2 GND, 3 SDA, 4 SCL, 5 XSHUT, 6 GPIO1 | `electronics/tof_carrier/board.py` |
| Quantity | 11: 4 cliff, 4 look-ahead, 3 rear | contract |
| Evaluation | SATEL-VL53L4ED (two breakouts), room temperature only | 0.3 BOM W19 |

**On the main board.** Two TCA9548A muxes (0x70, 0x71) on the dedicated I2C_TOF bus; pair partners on different muxes (pin map). Per branch: 2.2 kΩ pull-ups, 100 Ω series resistors, a 4-line ESD array at the connector, ferrite + 100 nF on the 3.3 V feed. XSHUT in three groups (cliff, look-ahead, rear) with 1 kΩ per sensor so one shorted cable cannot hold a group in reset. GPIO1 ends on a test pad.

**Bus speed.** 400 kHz. One branch: ≤ 300 mm of cable (about 30 pF) + sensor 10 pF + mux 10 pF + board 15 pF ≈ 65 pF; rise time 0.85 × 2.2 kΩ × 65 pF = 120 ns against 300 ns allowed [C]. The series resistors lift the low level to about 0.14 V at 1.4 mA [C]. A read of one sensor is about 0.4 ms at 400 kHz, so all 11 fit a 10 ms cycle; 100 kHz would not. Noise margin near the motors comes from the mux isolating each short branch, not from a lower clock.

**Prototype → production.** Evaluation kit on the bench → RR-TOF behind real windows for the cold trial → same carrier in production. Open: GH connector temperature rating (CCR-E05), window crosstalk calibration per position.
