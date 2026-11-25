"""RR-TOF-A  ToF sensor carrier (VL53L4ED) - board definition (single source of truth).

Build:  python3 tools/eda/rrkicad.py build electronics/tof_carrier/board.py
"""
from rrkicad import Board

board = Board(
    "RR-TOF-A", title="ToF sensor carrier (VL53L4ED)", rev="A", date="2026-11-25",
    docnum="RR-EL-0101", company="Rad Roomba", layers=2, thickness=1.6, silk_refs=False,
    description="VL53L4ED time-of-flight ranging sensor on a small carrier; used 11x on the robot\n"
                "(cliff, look-ahead, rear proximity). I2C pull-ups are on the main board, not here.\n"
                "Sensor on the top side, connector on the bottom side (mounts flush behind a window).")

board.rail("+3V3", "+3V3_TOF", "GND")
board.netclass("PWR", ["+3V3", "+3V3_TOF", "GND"], track=0.3, clearance=0.15, via_dia=0.6, via_drill=0.3)

# ---------------------------------------------------------------- connector
con = board.group("connector", "Harness connector, ESD protection, supply filter",
                  notes="J1 pinout (JST GH 6-pin): 1 +3V3, 2 GND, 3 SDA, 4 SCL, 5 XSHUT, 6 GPIO1 (interrupt, open drain).\n"
                        "D1 clamps all four signal lines at the connector. FB1 + C1/C2 filter the sensor supply.\n"
                        "R1/R2 are series damping resistors; the I2C pull-ups live on the main board.")
con.part("J1", "Connector_Generic_MountingPin:Conn_01x06_MountingPin", "JST GH 6p",
         "Connector_JST:JST_GH_SM06B-GHS-TB_1x06-1MP_P1.25mm_Horizontal",
         mfr="JST", mpn="SM06B-GHS-TB(LF)(SN)",
         pins={"1": "+3V3", "2": "GND", "3": "SDA", "4": "SCL", "5": "XSHUT", "6": "GPIO1", "MP": "GND"},
         at=(0.0, -5.75, 0, "B"))
con.part("D1", "Power_Protection:TPD4E05U06DQA", "TPD4E05U06",
         mfr="Texas Instruments", mpn="TPD4E05U06DQAR",
         pins={"1": "SDA", "2": "SCL", "4": "XSHUT", "5": "GPIO1", "3": "GND", "8": "GND"},
         nc=["6", "7", "9", "10"],
         notes="4-ch 0.5 pF ESD array; pins 6/7/9/10 are flow-through NC", at=(-1.25, -1.4, 90, "B"))
con.FB("FB1", "600R@100MHz", "+3V3", "+3V3_TOF", pkg="0603", mfr="Murata", mpn="BLM18AG601SN1D",
       at=(2.2, 1.0, 0, "B"))
con.R("R1", "22R", "SDA", "TOF_SDA", mfr="Yageo", mpn="RC0402FR-0722RL", at=(1.6, -1.2, 90, "B"))
con.R("R2", "22R", "SCL", "TOF_SCL", mfr="Yageo", mpn="RC0402FR-0722RL", at=(2.8, -1.2, 90, "B"))

# ------------------------------------------------------------------- sensor
sen = board.group("sensor", "VL53L4ED time-of-flight sensor",
                  notes="U1 uses the stock VL53L1 symbol/footprint: VL53L4ED is the same 12-pin optical LGA (4.4 x 2.4 mm)\n"
                        "and is pin-compatible with VL53L1X / VL53L4CD. AVDD range 2.6 - 3.5 V. DNC (pin 8) left open.\n"
                        "XSHUT and GPIO1 are pulled up to the filtered sensor rail (inputs are not 5 V tolerant).")
sen.part("U1", "Sensor_Distance:VL53L1CXV0FY1", "VL53L4ED", "Sensor_Distance:ST_VL53L1x",
         mfr="STMicroelectronics", mpn="VL53L4EDV0DH/1", verify=True,
         datasheet="https://www.st.com/resource/en/datasheet/vl53l4ed.pdf",
         description="Time-of-flight high-accuracy proximity sensor with extended temperature capability, LGA-12",
         pins={"AVDD": "+3V3_TOF", "AVDDVCSEL": "+3V3_TOF", "AVSSVCSEL": "GND", "GND": "GND",
               "SDA": "TOF_SDA", "SCL": "TOF_SCL", "XSHUT": "XSHUT", "GPIO1": "GPIO1"},
         notes="ordering code not checked against the ST datasheet", at=(0.0, 0.0, 0, "F"))
sen.C("C1", "4u7", "+3V3_TOF", "GND", pkg="0603", mfr="Murata", mpn="GRM188R61A475KE15D", at=(-1.2, 3.5, 0, "F"))
sen.C("C2", "100n", "+3V3_TOF", "GND", pkg="0402", mfr="Murata", mpn="GRM155R71C104KA88D", at=(-1.2, 2.25, 0, "F"))
sen.R("R3", "10k", "+3V3_TOF", "XSHUT", mfr="Yageo", mpn="RC0402FR-0710KL", at=(-1.6, 0.6, 0, "B"))
sen.R("R4", "10k", "+3V3_TOF", "GPIO1", mfr="Yageo", mpn="RC0402FR-0710KL", at=(-1.6, 1.8, 0, "B"))

# -------------------------------------------------------------------- board
board.outline_poly([(-9.0, -9.4), (9.0, -9.4), (9.0, 4.6), (-9.0, 4.6)], radius=1.0)
board.hole("H1", -6.5, 0.0, drill=2.2, keepout=5.0)
board.hole("H2", 6.5, 0.0, drill=2.2, keepout=5.0)
board.zone("GND", ["F.Cu", "B.Cu"])
board.text("{name} rev {rev}", 0.0, -5.6, layer="F.SilkS", size=1.0)
board.text("{date}", 0.0, -7.4, layer="F.SilkS", size=0.9)
