# Compute: Raspberry Pi CM5 + carrier (W06, W07)

| Item | Value | Tag |
|---|---|---|
| Module | Raspberry Pi Compute Module 5, **CM5104032** (4 GB RAM, 32 GB eMMC, Wi-Fi) | 0.3 BOM |
| Supplier | Raspberry Pi approved resellers | — |
| Operating temperature | −20…+85 °C | [M][U] no margin at the −25 °C objective: lives in the heated bay |
| Supply | 5 V ±5 %, up to 5 A at the carrier input | [U] exact clause of the CM5 datasheet |
| Carrier | **Waveshare CM5-IO-BASE-A**, 85 × 56 mm; 1 × Gigabit RJ45, 2 × USB 3.2 Gen1 Type-A, 2 × USB 2.0 on FFC, M.2 | [M] |
| Carrier temperature rating | not published | [U] test item |

**Power.** From RR-CHS-MAIN J_CM5 (Micro-Fit 2×2, two contacts per pole): 5.12 V nominal, eFuse limit 5.0 A, 50 mΩ to the carrier → 5.04 V at 1.5 A, 4.87 V at 5 A [C]. Feed point on the carrier: the 40-pin header 5 V pins (2, 4) and ground (6, 9), two wires per pole, **or** a USB-C power-only pigtail. [U]: whether this carrier back-feeds or protects the header input, and whether the CM5 limits downstream USB current without a 5 A-capable USB-C source (`usb_max_current_enable=1` in `config.txt` is the known remedy on Pi 5-family boards). Check both on the bench before the harness is drawn. The rail stays up across motion-MCU resets; the MCU can power-cycle it deliberately (IOX_B P12).

**Interfaces used.** RJ45 → LiDAR. USB-A 1 → RR-CHS-MAIN J_USB_MCU (chassis link, CDC). USB-A 2 → J_USB_HEAD (FT230X, head link). A wired service port then needs one of the FFC USB 2.0 ports broken out for a USB-Ethernet adapter (CCR-E10). Wi-Fi antenna: external U.FL antenna outside the aluminium tray [A].

**Mounting.** Left rear bay per the mechanical layout; heat sink to the bay wall or tray [M].

**Budget.** 3.5 W idle [U], 7 W typical [A], 12 W maximum with one USB adapter [A].

**Prototype → production.** Bench: Raspberry Pi CM5 IO Board (160 × 90 mm) on a 5 V / 5 A supply. Installed: the Waveshare carrier above. Production: same module; carrier to be re-confirmed for temperature and lifecycle, or replaced by a custom carrier if the −25 °C trial fails.
