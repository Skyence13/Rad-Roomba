"""Synthetic scale test for the rrkicad flow (NOT a deliverable design).

Resembles the real chassis/head boards more closely than STRESS-150: 160 x 100 mm, 6 layers,
~500 parts: LQFP-100 + LQFP-64 MCUs (0.5 mm), QFN-48, QFN-32, TSSOP-20, TSSOP-16,
40 SOT-23-class parts (24 low-side FET channels, 16 op-amp buffers), ~350 0402/0603 passives
with near= hints, 13 edge connectors, parts on both sides, 0.8-1.5 mm power nets.
ICs and connectors are placed explicitly, everything else is auto-arranged.

    python3 tools/eda/rrkicad.py build tools/eda/tests/scale500/board.py
"""
from rrkicad import Board, Rules
from rrkicad.symlib import SymbolLibs

L = SymbolLibs()
board = Board("SCALE-500", title="rrkicad scale test", rev="X", date="2026-11-27", docnum="RR-EL-TEST",
              company="Rad Roomba", layers=6, silk_refs=False,
              description="Synthetic generator/router scale test - not a product.")
board.rail("+3V3", "+5V", "GND")
board.netclass("HC", ["VBAT", "VBAT_F", "VBAT_S"], track=1.5, clearance=0.3, via_dia=0.8, via_drill=0.4)
board.netclass("MID", ["+12V", "VLED"], track=0.8, clearance=0.25, via_dia=0.8, via_drill=0.4)
board.netclass("PWR", ["+5V", "+3V3", "GND"], track=0.4, clearance=0.2, via_dia=0.8, via_drill=0.4)
board.outline_rect(160.0, 100.0, radius=2.0, origin="corner")
for i, (x, y) in enumerate(((4, 4), (156, 4), (4, 96), (156, 96))):
    board.hole("H%d" % (i + 1), x, y, drill=3.2, keepout=7.0)
board.zone("GND", ["In1.Cu"], connect="solid")
# In4: +3V3 everywhere except a +5V island in the lower-left power corner (non-overlapping polygons)
board.zone("+3V3", ["In4.Cu"], polygon=[(40.5, 0), (160, 0), (160, 100), (0, 100), (0, 30.5), (40.5, 30.5)], connect="solid")
board.zone("+5V", ["In4.Cu"], polygon=[(0, 0), (40, 0), (40, 30), (0, 30)], connect="solid")
board.text("{name} rev {rev} {date}", 80, 2.0, size=1.2)
board.route(passes=30, timeout=840, optimizer=False, retries=2,
            extra_args=["--router.autorouter.fallback_strategies=continue"])

C0402 = dict(mfr="Murata", mpn="GRM155R71C104KA88D")
R0402 = dict(mfr="Yageo", mpn="RC0402FR-0710KL")


def io_pins(sym):
    return [p.name for p in L.get(sym).pins if p.etype == "bidirectional"]


# ------------------------------------------------------------------ power
pw = board.group("power", "Battery input, fuse, shunt, regulators")
pw.part("J1", "Connector:Screw_Terminal_01x02", "VBAT IN", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
        mfr="Phoenix Contact", mpn="1711026", pins={"1": "VBAT", "2": "GND"}, at=(8, 18, 270), height=12.0)
pw.part("F1", "Device:Fuse", "10A", "Fuse:Fuse_1812_4532Metric", mfr="Littelfuse", mpn="1812L1000", pins={"1": "VBAT", "2": "VBAT_F"})
pw.R("RS1", "2m", "VBAT_F", "VBAT_S", pkg="2512", mfr="Vishay", mpn="WSL2512R0020FEA", near="F1")
for k in range(3):
    pw.C("C%d" % (1 + k), "22u", "VBAT_S", "GND", pkg="1210", mfr="Murata", mpn="GRM32ER71H226KE15L", near="RS1")
pw.part("J2", "Connector:Screw_Terminal_01x02", "VBAT OUT A", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
        mfr="Phoenix Contact", mpn="1711026", pins={"1": "VBAT_S", "2": "GND"}, at=(8, 45, 270), height=12.0)
pw.part("J3", "Connector:Screw_Terminal_01x02", "12V IN", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
        mfr="Phoenix Contact", mpn="1715721", pins={"1": "+12V", "2": "GND"}, at=(40, 7, 0), height=10.0)
pw.part("U7", "Regulator_Linear:AMS1117-3.3", "AMS1117-5.0", mfr="AMS", mpn="AMS1117-5.0",
        pins={"VI": "+12V", "GND": "GND", "VO": "+5V"}, at=(25, 20, 0))
pw.part("U8", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", mfr="AMS", mpn="AMS1117-3.3",
        pins={"VI": "+5V", "GND": "GND", "VO": "+3V3"}, at=(25, 36, 0))
pw.C("C4", "10u", "+12V", "GND", pkg="0805", mfr="Murata", mpn="GRM21BR61E106KA73L", near="U7.3")
pw.C("C5", "22u", "+5V", "GND", pkg="0805", mfr="Murata", mpn="GRM21BR61A226ME51L", near="U7.2")
pw.C("C6", "10u", "+5V", "GND", pkg="0805", mfr="Murata", mpn="GRM21BR61A106KE19L", near="U8.3")
pw.C("C7", "22u", "+3V3", "GND", pkg="0805", mfr="Murata", mpn="GRM21BR60J226ME39L", near="U8.2")
pw.R("R1", "0R", "+12V", "VLED", pkg="1206", mfr="Yageo", mpn="RC1206JR-070RL", near="U7")

# ------------------------------------------------------------------ main MCU (LQFP-100)
mcu = board.group("mcu", "STM32F407 main MCU (LQFP-100, 0.5 mm)")
f4 = "MCU_ST_STM32F4:STM32F407VETx"
pins = {"VDD": "+3V3", "VDDA": "+3V3", "VREF+": "+3V3", "VBAT": "+3V3", "VSS": "GND", "VSSA": "GND",
        "VCAP_1": "VCAP1", "VCAP_2": "VCAP2", "NRST": "NRST", "BOOT0": "BOOT0"}
pool = io_pins(f4)
used = {}


def take(net):
    name = pool.pop(0)
    pins[name] = net
    used[net] = name
    return name


for k in range(16):
    take("B2_%02d" % k)        # bus to U2 (LQFP-64), series R at U2
for k in range(12):
    take("B3_%02d" % k)        # bus to U3 (QFN-48)
for k in range(6):
    take("B4_%02d" % k)        # to U4 (QFN-32)
for k in range(4):
    take("B5_%02d" % k)        # to U5 (TSSOP-20)
for n in ("SR_SER", "SR_CLK", "SR_LAT"):
    take(n)                    # 74HC595
for k in range(24):
    take("FET_IN%02d" % k)     # FET gate drivers (via series R)
for n in ("SWDIO", "SWCLK", "I2C_SCL", "I2C_SDA", "UART_TX", "UART_RX"):
    take(n)
for k in range(10):
    take("DIN%02d" % k)
mcu.part("U1", f4, "STM32F407VET6", mfr="STMicroelectronics", mpn="STM32F407VET6", pins=pins, unused="nc", at=(72, 52, 0))
for k in range(10):
    mcu.C("C%d" % (10 + k), "100n", "+3V3", "GND", side="B", **C0402)
for i, net in enumerate(("VCAP1", "VCAP2")):
    pin = [p.number for p in L.get(f4).pins if p.name == ("VCAP_1", "VCAP_2")[i]][0]
    mcu.C("C%d" % (20 + i), "2u2", net, "GND", pkg="0603", mfr="Murata", mpn="GRM188R61A225KE34D", near="U1.%s" % pin)
nrst = [p.number for p in L.get(f4).pins if p.name == "NRST"][0]
boot = [p.number for p in L.get(f4).pins if p.name == "BOOT0"][0]
mcu.R("R10", "10k", "+3V3", "NRST", near="U1.%s" % nrst, **R0402)
mcu.C("C22", "100n", "NRST", "GND", near="U1.%s" % nrst, **C0402)
mcu.R("R11", "10k", "BOOT0", "GND", near="U1.%s" % boot, **R0402)
mcu.C("C23", "4u7", "+3V3", "GND", pkg="0603", mfr="Murata", mpn="GRM188R61A475KE15D", near="U1")
f4num = {p.name: p.number for p in L.get(f4).pins}
# pull-ups on a few MCU pins (near= the pin: candidates for the direct escape pre-route)
for k, net in enumerate(("I2C_SCL", "I2C_SDA", "UART_RX", "SWDIO")):
    mcu.R("R%d" % (12 + k), "4k7", "+3V3", net, near="U1.%s" % f4num[used[net]], **R0402)

# ------------------------------------------------------------------ co-processor (LQFP-64)
cp = board.group("cop", "STM32G474 co-processor (LQFP-64) with analogue front-end inputs")
g4 = "MCU_ST_STM32G4:STM32G474RETx"
p2 = {"VDD": "+3V3", "VDDA": "+3V3", "VREF+": "+3V3", "VBAT": "+3V3", "VSS": "GND", "VSSA": "GND"}
pool2 = io_pins(g4)
for k in range(16):
    p2[pool2.pop(0)] = "B2R_%02d" % k
ain = []
for k in range(16):
    p2[pool2.pop(0)] = "AIN%02d" % k
for k in range(16):
    p2[pool2.pop(0)] = "OPIN%02d" % k
cp.part("U2", g4, "STM32G474RET6", mfr="STMicroelectronics", mpn="STM32G474RET6", pins=p2, unused="nc", at=(122, 55, 0))
g4num = {}
for p in L.get(g4).pins:
    g4num.setdefault(p2.get(p.name), p.number)
for k in range(16):      # series termination at the receiver
    cp.R("R%d" % (100 + k), "33R", "B2_%02d" % k, "B2R_%02d" % k, near="U2.%s" % g4num["B2R_%02d" % k], mfr="Yageo", mpn="RC0402FR-0733RL")
for k in range(8):
    cp.C("C%d" % (30 + k), "100n", "+3V3", "GND", **C0402)

# ------------------------------------------------------------------ U3 QFN-48, U4 QFN-32, U5 TSSOP-20, U6 TSSOP-16
px = board.group("periph", "Peripheral controllers")
f1 = "MCU_ST_STM32F1:STM32F103CBUx"
p3 = {}
io3 = []
for p in L.get(f1).pins:
    if p.etype == "power_in" or p.name.startswith("VSS") or p.name.startswith("VDD"):
        p3[p.number] = "GND" if p.name.startswith("VSS") else "+3V3"
    elif p.etype == "bidirectional":
        io3.append(p.name)
for k in range(12):
    p3[io3[k]] = "B3R_%02d" % k
for k in range(8):
    p3[io3[12 + k]] = "AUXH%02d" % k
p3[io3[20]] = "I2C_SCL"
p3[io3[21]] = "I2C_SDA"
px.part("U3", f1, "STM32F103CBU6", mfr="STMicroelectronics", mpn="STM32F103CBU6", pins=p3, unused="nc", at=(38, 72, 0))
for k in range(4):
    px.C("C%d" % (40 + k), "100n", "+3V3", "GND", **C0402)
g0 = "STM32G031K8Ux"
p4 = {"VDD": "+3V3", "VSS": "GND"}
io4 = io_pins("MCU_ST_STM32G0:" + g0)
for k in range(6):
    p4[io4[k]] = "B4R_%02d" % k
for k in range(6):
    p4[io4[6 + k]] = "GH%d" % k
px.part("U4", "MCU_ST_STM32G0:" + g0, "STM32G031K8U6", mfr="STMicroelectronics", mpn="STM32G031K8U6", pins=p4, unused="nc", at=(48, 30, 0))
px.C("C44", "100n", "+3V3", "GND", **C0402)
px.C("C45", "1u", "+3V3", "GND", mfr="Murata", mpn="GRM155R61A105KE15D")
p5 = {"VDD": "+3V3", "VSS": "GND"}
io5 = io_pins("MCU_ST_STM32G0:STM32G031F8Px")
for k in range(4):
    p5[io5[k]] = "B5R_%02d" % k
for k in range(8):
    p5[io5[4 + k]] = "AUXT%02d" % k
px.part("U5", "MCU_ST_STM32G0:STM32G031F8Px", "STM32G031F8P6", mfr="STMicroelectronics", mpn="STM32G031F8P6", pins=p5, unused="nc", at=(100, 22, 0))
px.C("C46", "100n", "+3V3", "GND", **C0402)
px.part("U6", "74xx:74HC595", "74HC595", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", mfr="Texas Instruments", mpn="SN74HC595PWR",
        pins={"SER": "SR_SER", "SRCLK": "SR_CLK", "RCLK": "SR_LAT", "~{SRCLR}": "+3V3", "~{OE}": "GND", "VCC": "+3V3", "GND": "GND",
              "QA": "SRQ0", "QB": "SRQ1", "QC": "SRQ2", "QD": "SRQ3", "QE": "SRQ4", "QF": "SRQ5", "QG": "SRQ6", "QH": "SRQ7"},
        nc=["QH'"], at=(88, 84, 0))
px.C("C47", "100n", "+3V3", "GND", near="U6.16", **C0402)
for pre, cnt, u, base in (("B3", 12, "U3", 800), ("B4", 6, "U4", 820), ("B5", 4, "U5", 830)):
    for k in range(cnt):
        px.R("R%d" % (base + k), "33R", "%s_%02d" % (pre, k), "%sR_%02d" % (pre, k), near=u, mfr="Yageo", mpn="RC0402FR-0733RL")
for k in range(8):
    px.R("R%d" % (840 + k), "33R", "AUXH%02d" % k, "AUXHC%02d" % k, near="U3", mfr="Yageo", mpn="RC0402FR-0733RL")
    px.R("R%d" % (850 + k), "33R", "AUXT%02d" % k, "AUXTC%02d" % k, near="U5", mfr="Yageo", mpn="RC0402FR-0733RL")
for k in range(6):
    px.R("R%d" % (860 + k), "33R", "GH%d" % k, "GHC%d" % k, near="U4", mfr="Yageo", mpn="RC0402FR-0733RL")
    px.C("C%d" % (860 + k), "47p", "GHC%d" % k, "GND", mfr="Murata", mpn="GRM1555C1H470JA01D", near="R%d" % (860 + k))
for k in range(8):
    px.R("R%d" % (200 + k), "1k", "SRQ%d" % k, "SRL%d" % k, near="U6", mfr="Yageo", mpn="RC0402FR-071KL")
    px.LED("D%d" % (200 + k), "green", "SRL%d" % k, "GND", mfr="Wurth", mpn="150060GS75000", near="R%d" % (200 + k))

# ------------------------------------------------------------------ 24 low-side FET channels (SOT-23)
for bank in range(3):
    g = board.group("fet%d" % bank, "Low-side switch bank %d" % bank)
    hdr = {}
    for k in range(8):
        n = bank * 8 + k
        g.R("R%d" % (300 + n), "100R", "FET_IN%02d" % n, "G%02d" % n, mfr="Yageo", mpn="RC0402FR-07100RL", near="Q%d.1" % (300 + n))
        g.R("R%d" % (330 + n), "100k", "G%02d" % n, "GND", mfr="Yageo", mpn="RC0402FR-07100KL", near="Q%d.1" % (300 + n), side="B")
        g.part("Q%d" % (300 + n), "Transistor_FET:AO3400A", "AO3400A", mfr="AOS", mpn="AO3400A",
               pins={"1": "G%02d" % n, "2": "GND", "3": "SW%02d" % n})
        g.LED("D%d" % (300 + n), "red", "VLED", "LK%02d" % n, mfr="Wurth", mpn="150060RS75000", near="Q%d" % (300 + n))
        g.R("R%d" % (360 + n), "2k2", "LK%02d" % n, "SW%02d" % n, mfr="Yageo", mpn="RC0402FR-072K2L", near="D%d" % (300 + n))
        g.R("R%d" % (900 + n), "47R", "SW%02d" % n, "SN%02d" % n, pkg="0603", mfr="Yageo", mpn="RC0603FR-0747RL", near="Q%d.3" % (300 + n), side="B")
        g.C("C%d" % (900 + n), "1n", "SN%02d" % n, "GND", pkg="0603", mfr="Murata", mpn="GRM188R71H102KA01D", near="R%d" % (900 + n), side="B")
        hdr[str(2 * k + 1)] = "SW%02d" % n
        hdr[str(2 * k + 2)] = "+12V"
    hdr.update({"17": "GND", "18": "GND", "19": "GND", "20": "GND"})
    g.part("J%d" % (10 + bank), "Connector_Generic:Conn_02x10_Odd_Even", "OUT%d" % bank,
           "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical", mfr="Samtec", mpn="TSW-110-07-G-D",
           pins=hdr, at=(60 + 30 * bank, 94.5, 90))

# ------------------------------------------------------------------ 16 op-amp buffers (SOT-23-5)
for bank in range(2):
    g = board.group("amp%d" % bank, "Op-amp buffer bank %d" % bank)
    hdr = {}
    for k in range(8):
        n = bank * 8 + k
        ref = 400 + n
        g.R("R%d" % ref, "1k", "OPIN%02d" % n, "OPB%02d" % n, mfr="Yageo", mpn="RC0402FR-071KL", near="U%d.3" % ref)
        g.C("C%d" % ref, "1n", "OPB%02d" % n, "GND", mfr="Murata", mpn="GRM155R71H102KA01D", near="U%d.3" % ref, side="B")
        g.part("U%d" % ref, "Amplifier_Operational:MCP6001-OT", "MCP6001", mfr="Microchip", mpn="MCP6001T-I/OT",
               pins={"3": "OPB%02d" % n, "4": "OPO%02d" % n, "1": "OPO%02d" % n, "5": "+3V3", "2": "GND"})
        g.C("C%d" % (ref + 100), "100n", "+3V3", "GND", near="U%d.5" % ref, **C0402)
        g.R("R%d" % (ref + 100), "100R", "OPO%02d" % n, "AO%02d" % n, mfr="Yageo", mpn="RC0402FR-07100RL", near="U%d.1" % ref)
        g.C("C%d" % (ref + 200), "100p", "AO%02d" % n, "GND", mfr="Murata", mpn="GRM1555C1H101JA01D", near="R%d" % (ref + 100))
        hdr[str(2 * k + 1)] = "AO%02d" % n
        hdr[str(2 * k + 2)] = "GND"
    hdr.update({"17": "GND", "18": "GND", "19": "+3V3", "20": "+5V"})
    g.part("J%d" % (20 + bank), "Connector_Generic:Conn_02x10_Odd_Even", "AOUT%d" % bank,
           "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical", mfr="Samtec", mpn="TSW-110-07-G-D",
           pins=hdr, at=(153, 37 + 26 * bank, 0))

# ------------------------------------------------------------------ 16 filtered analogue inputs
ai = board.group("ain", "Analogue inputs: RC filter + clamp resistor per channel")
for blk in range(2):
    hdr = {}
    for k in range(8):
        n = blk * 8 + k
        ai.R("R%d" % (700 + n), "10k", "AIN_X%02d" % n, "AIN%02d" % n, mfr="Yageo", mpn="RC0402FR-0710KL")
        ai.C("C%d" % (700 + n), "10n", "AIN%02d" % n, "GND", mfr="Murata", mpn="GRM155R71H103KA88D", near="R%d" % (700 + n))
        ai.R("R%d" % (730 + n), "100k", "AIN_X%02d" % n, "GND", mfr="Yageo", mpn="RC0402FR-07100KL", near="R%d" % (700 + n), side="B")
        hdr[str(k + 1)] = "AIN_X%02d" % n
    for k in range(8, 20):
        hdr[str(k + 1)] = "GND"
    ai.part("J%d" % (30 + blk), "Connector_Generic:Conn_02x10_Odd_Even", "AIN%d" % blk,
            "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical", mfr="Samtec", mpn="TSW-110-07-G-D",
            pins=hdr, at=(96 + 28 * blk, 3.5, 90))

# ------------------------------------------------------------------ misc connectors
ms = board.group("conn", "Debug, UART/I2C and expansion connectors")
ms.part("J40", "Connector_Generic:Conn_02x05_Odd_Even", "SWD", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
        mfr="Samtec", mpn="FTSH-105-01-L-DV", pins={"1": "+3V3", "2": "SWDIO", "3": "GND", "4": "SWCLK", "5": "GND",
                                                     "6": "NRST", "7": "GND", "8": "UART_TX", "9": "GND", "10": "UART_RX"},
        at=(3, 62, 0))
ms.part("J41", "Connector_Generic_MountingPin:Conn_01x08_MountingPin", "GH8", "Connector_JST:JST_GH_SM08B-GHS-TB_1x08-1MP_P1.25mm_Horizontal",
        mfr="JST", mpn="SM08B-GHS-TB", pins={"1": "+3V3", "2": "GND"} | {str(3 + k): "GHC%d" % k for k in range(6)} | {"MP": "GND"},
        at=(30, 96, 180))
ms.part("J42", "Connector_Generic_MountingPin:Conn_01x04_MountingPin", "GH4", "Connector_JST:JST_GH_SM04B-GHS-TB_1x04-1MP_P1.25mm_Horizontal",
        mfr="JST", mpn="SM04B-GHS-TB", pins={"1": "+3V3", "2": "I2C_SCL", "3": "I2C_SDA", "4": "GND", "MP": "GND"}, at=(3, 82, 270))
hx = {str(k + 1): "AUXHC%02d" % k for k in range(8)}
hx.update({str(9 + k): "AUXTC%02d" % k for k in range(8)})
hx.update({"17": "GND", "18": "GND", "19": "+3V3", "20": "+5V"})
ms.part("J43", "Connector_Generic:Conn_02x10_Odd_Even", "EXP", "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
        mfr="Samtec", mpn="TSW-110-07-G-D", pins=hx, at=(148, 90, 0))

din = board.group("din", "Digital inputs: series R, pull-down, filter C")
dh = {}
for k in range(10):
    din.R("R%d" % (870 + k), "1k", "DIN_X%02d" % k, "DIN%02d" % k, mfr="Yageo", mpn="RC0402FR-071KL")
    din.R("R%d" % (880 + k), "100k", "DIN_X%02d" % k, "GND", mfr="Yageo", mpn="RC0402FR-07100KL", near="R%d" % (870 + k), side="B")
    din.C("C%d" % (880 + k), "1n", "DIN%02d" % k, "GND", mfr="Murata", mpn="GRM155R71H102KA01D", near="R%d" % (870 + k))
    dh[str(k + 1)] = "DIN_X%02d" % k
dh.update({str(k + 1): "GND" for k in range(10, 20)})
din.part("J32", "Connector_Generic:Conn_02x10_Odd_Even", "DIN", "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
         mfr="Samtec", mpn="TSW-110-07-G-D", pins=dh, at=(66, 3.5, 90))
