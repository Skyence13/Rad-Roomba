# Development alternatives from the 0.3 BOM and where each maps in the custom design

| 0.3 item | Use during development | Replaced on RR-CHS-MAIN by | What must match |
|---|---|---|---|
| ST **NUCLEO-G474RE** (W08) | Firmware bring-up before boards exist; same MCU and LQFP64 pin names | U20M STM32G474RET6, Y1 (8 MHz; the Nucleo's 24 MHz MCO/8 MHz option per `RR_HSE_HZ`), J_SWD | Pin map `firmware/chassis/pinmap.yaml`; the Nucleo's on-board ST-LINK occupies PA2/PA3 (LPUART) unless the solder bridges are opened, and those pins are VMOT_SENSE/VBAT_SENSE in the final map [U bridge names] |
| Basicmicro **RoboClaw 2×15A** (W11) | Motor bring-up and a fallback if the on-board bridges fail qualification | U5/U6 DRV8874, U8, K2/K3, clamp | RoboClaw closes its own loops: with it, the MCU sends setpoints over a UART instead of PWM; the brake relays must still sit between the RoboClaw outputs and the motors, and its supply must come from VMOT so the latch removes it |
| Pololu **D24V90F5** (#2866) (E02) | 5 V / 9 A bench regulator for the CM5 before the board exists | U10 LM61460 + U13 eFuse | Output set-point (5.0 V on the Pololu part against 5.12 V), no current-limit fault output on the Pololu module |
| Analog Devices **EVAL-ADM2582EEBZ** (E06) | Isolated RS-485 at both ends of a bench link | Chassis end: U61 FT230X + U62 THVD1450 (not isolated). Head end keeps the isolation (DEC-024) | Polarity (A = non-inverting = RS485_DP), 120 Ω at both ends, bias at the chassis end only, 1 Mbaud |
| ST **SATEL-VL53L4ED** (W19) | Two-sensor ranging tests at room temperature | RR-TOF ×11 | Same sensor; different connector |
| Bench supply, current-limited (W36) | First power-up of every block | Pack + J_PWR | Procedure in `electronics/analysis/chassis_safety_chain.md` §8 |
