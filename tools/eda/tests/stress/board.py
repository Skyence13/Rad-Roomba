"""Synthetic stress board for the rrkicad flow (NOT a deliverable design).

4 layers, 100 x 80 mm, ~150 parts, mostly auto-arranged.  Exercises: big stock
symbols, a multi-unit symbol, project-local symbol + footprint, DNP, cut-out,
keep-out, pre-routed track, inner planes with a split, auto-arrange hints.

    python3 tools/eda/rrkicad.py build tools/eda/tests/stress/board.py
"""
from rrkicad import Board, Pad, SymPin
from rrkicad.symlib import SymbolLibs

L = SymbolLibs()
board = Board("STRESS-150", title="rrkicad stress test", rev="X", date="2026-11-25", docnum="RR-EL-TEST",
              company="Rad Roomba", layers=4, silk_refs=False, description="Synthetic generator/router stress test - not a product.")
board.rail("+5V", "+3V3", "GND")
board.netclass("PWR", ["+5V", "+3V3", "GND", "VIN"], track=0.4, clearance=0.2, via_dia=0.8, via_drill=0.4)
board.outline_rect(100.0, 80.0, radius=2.0, origin="corner")
for i, (x, y) in enumerate(((4, 4), (96, 4), (4, 76), (96, 76))):
    board.hole("H%d" % (i + 1), x, y, drill=3.2, keepout=7.0)
board.cutout_rect(50.0, 76.0, 12.0, 3.0, radius=1.0)
board.keepout("KO_ANT", polygon=[(80, 60), (92, 60), (92, 72), (80, 72)], footprints=True)
board.zone("GND", ["In1.Cu"], connect="solid")
board.zone("+3V3", ["In2.Cu"], connect="solid")
board.zone("+5V", ["In2.Cu"], polygon=[(0, 0), (30, 0), (30, 30), (0, 30)], priority=1, connect="solid")
board.zone("GND", ["F.Cu", "B.Cu"])
board.text("{name} rev {rev} {date}", 50, 2.0, size=1.2)
# measured: 25 passes ~6.5 min -> 4 connections left open; 40 passes / wider spacing was not better
board.route(passes=30, timeout=900, optimizer=False)

# ------------------------------------------------------------------- power
pw = board.group("power", "Power input and 3V3 regulator", notes="Screw terminal 5 V in, LDO to 3V3.")
pw.part("J1", "Connector:Screw_Terminal_01x02", "5V IN",
        "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
        mfr="Phoenix Contact", mpn="1715721", pins={"1": "+5V", "2": "GND"}, at=(10, 20, 270), height=10.0)
pw.part("U3", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", mfr="AMS", mpn="AMS1117-3.3",
        pins={"VI": "+5V", "GND": "GND", "VO": "+3V3"}, at=(28, 12, 0))
pw.C("C1", "10u", "+5V", "GND", pkg="0805", mfr="Murata", mpn="GRM21BR61C106KE15L", near="U3.3")
pw.C("C2", "22u", "+3V3", "GND", pkg="0805", mfr="Murata", mpn="GRM21BR60J226ME39L", near="U3.2")
pw.LED("D1", "green", "+3V3", "LED_K", mfr="Wurth", mpn="150060GS75000", near="U3")
pw.R("R1", "1k", "LED_K", "GND", mfr="Yageo", mpn="RC0402FR-071KL", near="D1")
pw.R("R2", "0R", "+5V", "VIN", mfr="Yageo", mpn="RC0402JR-070RL", dnp=True, notes="option", near="U3")
pw.C("C3", "100n", "VIN", "GND", mfr="Murata", mpn="GRM155R71C104KA88D", near="R2")

# --------------------------------------------------------------------- mcu
mcu = board.group("mcu", "STM32G474 microcontroller", notes="All free I/O is brought to the opamp buffers and headers.")
g4 = L.get("MCU_ST_STM32G4:STM32G474RETx")
io = [p.name for p in g4.pins if p.etype == "bidirectional"]
pins = {"VDD": "+3V3", "VDDA": "+3V3", "VREF+": "+3V3", "VBAT": "+3V3", "VSS": "GND", "VSSA": "GND"}
io_net = {}
for k, name in enumerate(io):
    io_net[name] = "IO%02d" % k
    pins[name] = io_net[name]
mcu.part("U1", "MCU_ST_STM32G4:STM32G474RETx", "STM32G474RET6", mfr="STMicroelectronics", mpn="STM32G474RET6", pins=pins)
for k in range(8):
    mcu.C("C%d" % (10 + k), "100n", "+3V3", "GND", mfr="Murata", mpn="GRM155R71C104KA88D")
mcu.C("C18", "4u7", "+3V3", "GND", pkg="0603", mfr="Murata", mpn="GRM188R61A475KE15D")
mcu.C("C19", "1u", "+3V3", "GND", mfr="Murata", mpn="GRM155R61A105KE15D")

# --------------------------------------------------------------------- aux MCU (QFN48)
aux = board.group("aux", "STM32F103 auxiliary controller (QFN-48, 0.5 mm)")
f1 = L.get("MCU_ST_STM32F1:STM32F103CBUx")
apins = {}
aio = []
for p in f1.pins:
    if p.etype == "power_in" or p.name.startswith("VSS") or p.name.startswith("VDD"):
        apins[p.number] = "GND" if p.name.startswith("VSS") else "+3V3"
    elif p.etype == "bidirectional":
        aio.append(p.name)
# link the first 16 aux I/Os to the main MCU (bus), the next 12 to header J4, leave the rest NC
for k, name in enumerate(aio[:16]):
    apins[name] = "IO%02d" % (36 + k)
for k, name in enumerate(aio[16:28]):
    apins[name] = "AUX%02d" % k
aux.part("U2", "MCU_ST_STM32F1:STM32F103CBUx", "STM32F103CBU6", mfr="STMicroelectronics", mpn="STM32F103CBU6",
         pins=apins, unused="nc")
for k in range(5):
    aux.C("C%d" % (30 + k), "100n", "+3V3", "GND", mfr="Murata", mpn="GRM155R71C104KA88D")
aux.part("J4", "Connector_Generic:Conn_02x10_Odd_Even", "AUX", "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
         mfr="Samtec", mpn="TSW-110-07-G-D", edge="right",
         pins=dict([(str(k + 1), "AUX%02d" % k) for k in range(12)] + [(str(k), "GND") for k in range(13, 19)] +
                   [("19", "+3V3"), ("20", "+5V")]))

# ----------------------------------------------------------------- buffers
for blk in range(2):
    g = board.group("buf%d" % (blk + 1), "Analogue buffer bank %d" % (blk + 1),
                    notes="10 unity-gain buffers: MCU pin -> series R -> opamp -> header.")
    hdr = {}
    for k in range(10):
        n = blk * 10 + k
        ref = 100 + n
        src = "IO%02d" % n
        g.R("R%d" % ref, "1k", src, "BIN%02d" % n, mfr="Yageo", mpn="RC0402FR-071KL")
        g.part("U%d" % ref, "Amplifier_Operational:MCP6001-OT", "MCP6001", mfr="Microchip", mpn="MCP6001T-I/OT",
               pins={"3": "BIN%02d" % n, "4": "BUF%02d" % n, "1": "BUF%02d" % n, "5": "+3V3", "2": "GND"})
        g.C("C%d" % ref, "100n", "+3V3", "GND", mfr="Murata", mpn="GRM155R71C104KA88D", near="U%d.5" % ref)
        g.R("R%d" % (ref + 100), "100R", "BUF%02d" % n, "OUT%02d" % n, mfr="Yageo", mpn="RC0402FR-07100RL",
            near="U%d.1" % ref)
        hdr[str(2 * k + 1)] = "OUT%02d" % n
        hdr[str(2 * k + 2)] = "GND"
    g.part("J%d" % (blk + 2), "Connector_Generic:Conn_02x10_Odd_Even", "OUT%d" % (blk + 1),
           "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical", mfr="Samtec", mpn="TSW-110-07-G-D",
           pins=hdr, edge="top" if blk == 0 else "bottom")

# -------------------------------------------------------------------- misc
ms = board.group("misc", "Misc: dual opamp (multi-unit), local parts, sensors")
ms.part("U4", "Amplifier_Operational:LM358", "LM358", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        mfr="Texas Instruments", mpn="LM358DR",
        pins={"3": "IO20", "2": "FB_A", "1": "FB_A", "5": "IO21", "6": "FB_B", "7": "FB_B", "8": "+5V", "4": "GND"})
ms.C("C40", "100n", "+5V", "GND", mfr="Murata", mpn="GRM155R71C104KA88D", near="U4.8")
board.symbol("HALL4", [SymPin(1, "VCC", "power_in", "T"), SymPin(2, "OUT", "output", "R"),
                       SymPin(3, "GND", "power_in", "B"), SymPin(4, "TEST", "no_connect", "L")],
             description="Local test symbol")
board.footprint("HALL4_SMD", [Pad(1, -1.0, -0.8, 0.6, 0.9), Pad(2, 1.0, -0.8, 0.6, 0.9),
                              Pad(3, 1.0, 0.8, 0.6, 0.9), Pad(4, -1.0, 0.8, 0.6, 0.9)], body=(2.0, 1.2))
for k in range(4):
    ms.part("U%d" % (50 + k), "rr_local:HALL4", "HALL4", "rr_local:HALL4_SMD", mfr="TestCo", mpn="HALL4-T",
            verify=True, pins={"1": "+3V3", "2": "IO%02d" % (22 + k), "3": "GND"})
    ms.C("C%d" % (50 + k), "100n", "+3V3", "GND", mfr="Murata", mpn="GRM155R71C104KA88D", near="U%d.1" % (50 + k))
    ms.R("R%d" % (50 + k), "10k", "+3V3", "IO%02d" % (22 + k), mfr="Yageo", mpn="RC0402FR-0710KL", near="U%d.2" % (50 + k))
for k in range(2):
    ms.part("J%d" % (5 + k), "Connector_Generic_MountingPin:Conn_01x06_MountingPin", "GH6",
            "Connector_JST:JST_GH_SM06B-GHS-TB_1x06-1MP_P1.25mm_Horizontal", mfr="JST", mpn="SM06B-GHS-TB(LF)(SN)",
            pins={"1": "+3V3", "2": "GND", "3": "IO%02d" % (26 + 2 * k), "4": "IO%02d" % (27 + 2 * k),
                  "5": "IO%02d" % (30 + k), "6": "IO%02d" % (32 + k), "MP": "GND"}, edge="left")
for k in range(4):
    ms.R("R%d" % (60 + k), "4k7", "+3V3", "IO%02d" % (26 + k), mfr="Yageo", mpn="RC0402FR-074K7L")
for k in range(20):   # extra pull-downs to reach ~150 parts
    ms.R("R%d" % (300 + k), "100k", "BIN%02d" % k, "GND", mfr="Yageo", mpn="RC0402FR-07100KL", near="U%d.3" % (100 + k))
# two explicitly placed parts with a pre-routed (fixed) track between them
ms.R("R70", "10k", "IO34", "PRE_A", mfr="Yageo", mpn="RC0402FR-0710KL", at=(40.0, 70.0, 0))
ms.R("R71", "10k", "PRE_A", "IO35", mfr="Yageo", mpn="RC0402FR-0710KL", at=(44.0, 70.0, 0))
board.track("PRE_A", [(40.51, 70.0), (43.49, 70.0)], layer="F.Cu", width=0.25)
