# IMU: Bosch BMI088 (W18)

| Item | Value | Tag |
|---|---|---|
| Part | Bosch Sensortec **BMI088**, 16-pin LGA 3.0 × 4.5 × 0.95 mm | [U] package dimensions recalled |
| Temperature | −40…+85 °C | design text §8 |
| Supply | 2.4–3.6 V, about 5 mA | [U] |
| Interface | SPI mode 0 or 3, separate chip selects for accelerometer (CSB1) and gyro (CSB2); PS pin low selects SPI | [U] pin numbers in `circuit.py` are recalled |
| Position | On RR-CHS-MAIN at board (80, 67) mm = directly above `base_link` (yaw centre) | mechanical envelope |

**On the board.** Shares SPI1 (≤ 5 MHz, mode 3) with the IOX_A expander; chip selects PA4, PC5 with 10 kΩ pull-ups; both SDO pins through one 33 Ω resistor to MISO; interrupts not connected (polled at 1 kHz, pin map). Accelerometer dummy-byte read behaviour is a firmware matter.

**Layout.** No part within 4 mm, no vias under the package, switching nodes ≥ 10 mm away; the board is screwed to the aluminium tray at six points, so board flex at the IMU is small [A]. Thermal gradients from the bridges change the gyro bias: log board temperature (RT1) with the bias in the cold trial.

**Prototype → production.** Breakout board on the Nucleo → on-board part. No change for production.
