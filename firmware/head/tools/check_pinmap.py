#!/usr/bin/env python3
"""Check firmware/head/pinmap.yaml against ST's pin database subset (tool-checked evidence).

Verifies for every entry: the LQFP64 pin number, that no pin or signal is used twice, that the
claimed alternate function exists on that pin with that AF number, and that ADC channel numbers
match. Exit status 0 = consistent.
"""
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PINMAP = HERE.parent / "pinmap.yaml"
DB = json.loads((HERE / "stm32g474re_lqfp64_pindb.json").read_text())["pins"]

# signal name in pinmap -> exact signal name in the ST database (only for AF / analog functions)
EXPECT = {
    "SWDIO": "SYS_JTMS-SWDIO", "SWCLK": "SYS_JTCK-SWCLK", "FPGA_SYNC": "TIM2_CH2",
    "RS485_TX": "USART1_TX", "RS485_RX": "USART1_RX", "RS485_DE": "USART1_DE",
    "DBG_TX": "LPUART1_TX", "DBG_RX": "LPUART1_RX",
    "DAC_SCK": "SPI1_SCK", "DAC_MISO": "SPI1_MISO", "DAC_MOSI": "SPI1_MOSI",
    "FPGA_SCK": "SPI3_SCK", "FPGA_MISO": "SPI3_MISO", "FPGA_MOSI": "SPI3_MOSI",
    "FPGA_GATE": "TIM2_CH3", "I2C_SCL": "I2C3_SCL", "I2C_SDA": "I2C3_SDA",
    "HSE_IN_24M": "RCC_OSC_IN",
}


def main():
    doc = yaml.safe_load(PINMAP.read_text())
    errors = []
    seen_pins, seen_signals, seen_pos = set(), set(), set()
    for e in doc["pins"]:
        pin, pos, sig = e["pin"], e["lqfp64"], e["signal"]
        if pin in seen_pins and pin not in ("VSS", "VDD"):
            errors.append(f"{pin}: used twice")
        if sig in seen_signals:
            errors.append(f"{sig}: assigned twice")
        if pos in seen_pos:
            errors.append(f"LQFP64 pin {pos}: used twice")
        seen_pins.add(pin); seen_signals.add(sig); seen_pos.add(pos)
        db = DB.get(pin)
        if db is None:
            errors.append(f"{pin}: not in the STM32G474RET6 LQFP64 database")
            continue
        if pos not in db["positions"]:
            errors.append(f"{pin}: pin number {pos} != database {db['positions']}")
        want = EXPECT.get(sig)
        if want:
            if want not in db["signals"]:
                errors.append(f"{pin}: {want} is not available on this pin")
            elif db["signals"][want] is not None and db["signals"][want] != e["af"]:
                errors.append(f"{pin}: {want} is AF{db['signals'][want]}, pinmap says {e['af']}")
            elif db["signals"][want] is None and e["af"] != "-":
                errors.append(f"{pin}: {want} has no AF number, pinmap says {e['af']}")
        if e["peripheral"] in ("ADC1", "ADC2"):
            name = f"{e['peripheral']}_IN{e['channel']}"
            if name not in db["signals"]:
                errors.append(f"{pin}: {name} is not available on this pin")
        if e["peripheral"] in ("GPIO",) or e["peripheral"].startswith("EXTI"):
            if "GPIO" not in db["signals"]:
                errors.append(f"{pin}: not a GPIO")
        if e["peripheral"] not in ("power", "SYS", "RCC", "GPIO") and not e["peripheral"].startswith("EXTI") \
                and e["peripheral"] not in doc["peripherals"]:
            errors.append(f"{pin}: peripheral {e['peripheral']} is not described under 'peripherals'")
    io_pins = {p for p, d in DB.items() if d["type"] == "I/O"}
    unused = sorted(io_pins - seen_pins)
    if unused != sorted(doc.get("unused_pins", [])):
        errors.append(f"unused I/O pins {unused} differ from 'unused_pins' in pinmap.yaml")
    for err in errors:
        print("PINMAP ERROR:", err, file=sys.stderr)
    print(f"pinmap: {len(doc['pins'])} entries, {len(io_pins)} I/O pins in package, "
          f"{len(io_pins) - len(unused)} assigned, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
