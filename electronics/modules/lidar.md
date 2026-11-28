# 2D LiDAR (W15 baseline, W16 alternative, W17 harness)

| | Richbeam LakiBeam 1L (baseline) | SICK picoScan150 PICS150-01000 Prime-1, #1134609 (alternative) |
|---|---|---|
| Field of view | 270° | 276° [U] |
| Interface | Ethernet (UDP), 100BASE-TX | Ethernet |
| Supply | 9–36 V DC | 9–30 V DC [U] |
| Power | about 3–4 W typical [U]; 6 W used as the maximum | about 3.5 W [U] |
| Operating temperature | −25…+60 °C [M] | −33…+50 °C (design text; [M] lists it as unverified) |
| Envelope | 60 × 60 × 80 mm [M partial] | 60 × 60 × 82 mm [M] |
| ROS 2 driver | Richbeam driver published for Foxy/Humble; Jazzy build to be qualified | SICK `sick_scan_xd` |

**Supply from the board.** V12_LIDAR = switched VBAT_SW (10.0–14.6 V) through eFuse U19, 1.51 A limit, default ON without the MCU (the enable holds across MCU resets), fault to IOX_C P3. Connector J_LIDAR (Micro-Fit 2×1): pin 1 +, pin 2 return; AWG 22, 0.4 m: 0.05 V drop at 0.6 A [C]. The scanner's 9 V minimum is met down to the pack's 10 V limit with 0.9 V margin [C]; check the scanner's inrush against the 1.5 A limit (10 nF DVDT capacitor gives a soft start [U]).

**Data.** Scanner RJ45/M12 pigtail directly to the carrier's RJ45. Not routed through RR-CHS-MAIN.

**Not a safety device.** Neither scanner is used for a protective function (design text §4; BOM R12 stays open).

**Prototype → production.** Same part. Substituting the SICK unit changes the connector (M12 system plug) and the supply check only; the J_LIDAR pinout is unchanged.
