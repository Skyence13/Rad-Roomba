"""RR-CHS-MAIN rev A - chassis main board (power entry, charger, rails, branches, safety chain,
drive, motion MCU, ToF buses, head link, panel drivers).

Board definition (stage 2).  Single source of truth for the KiCad project in this directory.

    python3 tools/eda/rrkicad.py sch   electronics/chassis_main/board.py              # schematic + ERC + PDF
    python3 tools/eda/rrkicad.py build electronics/chassis_main/board.py --no-route   # + placed PCB, DRC, outputs
    python3 tools/eda/rrkicad.py build electronics/chassis_main/board.py              # + autorouter

Netlist = design/circuit.py (stage 1, reviewed baseline, not edited) + overrides.py (every stage-2
deviation, with IDs matching STAGE2_CHANGE_REQUESTS.md).  The applied overrides are written to
reports/overrides_applied.json on every run.

Frame mapping (see README.md):
    board_envelopes.yaml RR-CHS-MAIN (u, v)  ->  tool board frame (X, Y) = (u, v)
    origin = rear-left corner seen from above (top side up), X = u = towards the robot's right
    (base_link -y), Y = v = forward (base_link +x).  No rotation, no offset.
    base_link = (-67 + Y, 80 - X, 83 + z) mm.
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from rrkicad import Board, Pad, Rules          # noqa: E402
from rrkicad.importer import from_circuit      # noqa: E402
import overrides                               # noqa: E402
import placement                               # noqa: E402

board = Board(
    "RR-CHS-MAIN", title="Chassis main board", rev="A", date="2026-11-26", docnum="RR-EL-0100",
    company="Rad Roomba", layers=6, thickness=1.6, silk_refs=True, paper="A3",
    rules=Rules(),
    description="Chassis main board: pack entry and switch, LiFePO4 charger and power path, 5.12 V / 3.3 V / 5 V rails,\n"
                "eFuse branches (head power, head heater, chassis heater, LiDAR, bus 5 V), hardwired traction safety chain\n"
                "with latch relay, VMOT eFuse, two DRV8874 H-bridges with DPDT brake relays, STM32G474 motion MCU with IMU,\n"
                "expanders, 11 ToF branches, USB/RS-485 head link and panel drivers.\n"
                "Netlist: design/circuit.py (stage 1) + overrides.py (stage 2 deviations S2-xx, see STAGE2_CHANGE_REQUESTS.md).\n"
                "NOT A SAFETY-RATED CIRCUIT.")

# ----------------------------------------------------------------- project-local footprints
# Land patterns NOT available in the KiCad 9 stock library.  Geometry source given per footprint.
# PLACEHOLDER = drawn from memory of the package outline only, NOT from the manufacturer's drawing:
# electrically complete (every pin has a pad) so the board can be placed and routed, but each one
# must be redrawn from the TI / Wurth land-pattern drawing before fabrication (README: UNVERIFIED).
board.footprint("TI_RPW0010A_VQFN-HR-10_2x2mm_PLACEHOLDER",
                [Pad(1, -0.85, -0.75, 0.5, 0.25), Pad(2, -0.85, -0.25, 0.5, 0.25), Pad(3, -0.85, 0.25, 0.5, 0.25),
                 Pad(4, -0.85, 0.75, 0.5, 0.25), Pad(5, -0.25, 0.0, 0.3, 1.5), Pad(6, 0.25, 0.0, 0.3, 1.5),
                 Pad(7, 0.85, 0.75, 0.5, 0.25), Pad(8, 0.85, 0.25, 0.5, 0.25), Pad(9, 0.85, -0.25, 0.5, 0.25),
                 Pad(10, 0.85, -0.75, 0.5, 0.25)],
                body=(2.0, 2.0), height=1.0,
                description="PLACEHOLDER for TI RPW0010A (TPS259470): 2 x 2 mm VQFN-HR-10; pad shapes NOT from the TI drawing")
board.footprint("TI_RJR0014A_VQFN-HR-14_4x3.5mm_PLACEHOLDER",
                [Pad(1, -1.55, -1.25, 0.6, 0.3), Pad(2, -1.55, -0.75, 0.6, 0.3), Pad(3, -1.55, -0.25, 0.6, 0.3),
                 Pad(4, -1.55, 0.25, 0.6, 0.3), Pad(5, -1.55, 0.75, 0.6, 0.3), Pad(6, -1.55, 1.25, 0.6, 0.3),
                 Pad(7, -0.6, 1.8, 0.3, 0.6), Pad(8, 1.35, 1.2, 0.8, 0.85), Pad(9, 1.35, 0.35, 0.8, 0.5),
                 Pad(10, 0.3, 0.0, 0.9, 2.0), Pad(11, 1.35, -0.35, 0.8, 0.5), Pad(12, 1.35, -1.2, 0.8, 0.85),
                 Pad(13, -0.6, -1.8, 0.3, 0.6), Pad(14, 0.0, -1.8, 0.3, 0.6)],
                body=(3.5, 4.0), height=1.0,
                description="PLACEHOLDER for TI RJR0014A (LM61460): 3.5 x 4 mm VQFN-HR-14; pad shapes NOT from the TI drawing")
_q24 = []
for _i in range(6):
    _q24 += [Pad(1 + _i, -1.95, -1.25 + 0.5 * _i, 0.8, 0.25), Pad(7 + _i, -1.25 + 0.5 * _i, 1.95, 0.25, 0.8),
             Pad(13 + _i, 1.95, 1.25 - 0.5 * _i, 0.8, 0.25), Pad(19 + _i, 1.25 - 0.5 * _i, -1.95, 0.25, 0.8)]
_q24 += [Pad(25, -0.6, 0.0, 1.0, 2.4), Pad(26, 0.65, 0.0, 1.0, 2.4)]
board.footprint("TI_TPS25982_VQFN-24_4x4mm_SplitPad_PLACEHOLDER", _q24, body=(4.0, 4.0), height=1.0,
                description="PLACEHOLDER for TPS25982 24-pin 4 x 4 mm 0.5 mm-pitch package with split exposed pad "
                            "(25 = IN pad, 26 = GND pad); perimeter = generic QFN-24 4x4, split pad NOT from the TI drawing")
board.footprint("L_Wuerth_WE-LQS-5040", [Pad(1, -1.8, 0.0, 1.4, 4.2, shape="rect"), Pad(2, 1.8, 0.0, 1.4, 4.2, shape="rect")],
                body=(5.0, 5.0), height=4.0,
                description="Wurth WE-LQS 5040 (74404054220) 5 x 5 x 4 mm: two-terminal land, pad size estimated from the "
                            "5 x 5 mm body [verify against the Wurth land pattern]")
board.footprint("VSON-8_3.3x3.3mm_P0.65mm_NexFET_G0.2",
                [Pad(1, -1.44, -0.975, 0.63, 0.45), Pad(2, -1.44, -0.325, 0.63, 0.45), Pad(3, -1.44, 0.325, 0.63, 0.45),
                 Pad(4, -1.44, 0.975, 0.63, 0.45), Pad(5, 0.6, 0.0, 2.3, 2.45, shape="rect")],
                body=(3.3, 3.3), height=1.0,
                description="TI NexFET SON 3.3 x 3.3 (CSD18543Q3A): KiCad stock VSON-8_3.3x3.3mm_P0.65mm_NexFET with pads 1-4 "
                            "0.45 mm tall (stock 0.5 mm) and the drain fingers merged into pad 5")
_lga = [Pad(1 + i, -1.5 + 0.5 * i, -1.26, 0.25, 0.68) for i in range(7)] + [Pad(8, 2.01, 0.0, 0.68, 0.25)] + \
       [Pad(9 + i, 1.5 - 0.5 * i, 1.26, 0.25, 0.68) for i in range(7)] + [Pad(16, -2.01, 0.0, 0.68, 0.25)]
board.footprint("Bosch_LGA-16_4.5x3mm_P0.5mm_ClockwisePinNumbering", _lga, body=(4.5, 3.0), height=1.0,
                description="Bosch BMI088 LGA-16: pad geometry copied from the KiCad stock footprint "
                            "Bosch_LGA-16_4.5x3mm_P0.5mm_LayoutBorder7x1y_ClockwisePinNumbering, without its internal keep-out")
board.footprint("WirePads_2x2.5mm_P5.0mm", [Pad(1, -2.5, 0.0, 2.5, 2.5, shape="rect", paste=False),
                                             Pad(2, 2.5, 0.0, 2.5, 2.5, shape="rect", paste=False)],
                body=None, height=0.1, pin1=False,
                description="Two 2.5 x 2.5 mm wire pads (W1, optional external clamp resistor, DNP)")

# ----------------------------------------------------------------- project-local symbols
# BMI088 with the stock pin numbers/names but SDO1/SDO2 typed tri-state (they are high-impedance while the
# corresponding CSB is high, which is what lets stage 1 share one IMU_SDO line).  The stock symbol types them
# 'output', which makes ERC report output-to-output.  Source: KiCad Sensor_Motion:BMI088 + BMI088 SPI description.
from rrkicad import SymPin                     # noqa: E402
board.symbol("BMI088_SPI", [
    SymPin(14, "~{CSB1}", "input", "L"), SymPin(5, "~{CSB2}", "input", "L"), SymPin(8, "SCK/SCL", "input", "L"),
    SymPin(9, "SDI/SDA", "bidirectional", "L"), SymPin(7, "PS", "input", "L"),
    SymPin(15, "SDO1", "tri_state", "R"), SymPin(10, "SDO2", "tri_state", "R"), SymPin(16, "INT1", "bidirectional", "R"),
    SymPin(1, "INT2", "bidirectional", "R"), SymPin(12, "INT3", "bidirectional", "R"), SymPin(13, "INT4", "bidirectional", "R"),
    SymPin(3, "VDD", "power_in", "T"), SymPin(11, "VDDIO", "power_in", "T"),
    SymPin(2, "GNDA", "power_in", "B"), SymPin(4, "GNDA", "power_in", "B"), SymPin(6, "GNDIO", "power_in", "B")],
    ref_prefix="U", description="Bosch BMI088 6-axis IMU (SPI); SDO1/SDO2 tri-state")

# ----------------------------------------------------------------- netlist: circuit.py + overrides
base = overrides.load_circuit()
parts, override_log = overrides.apply(base.PARTS)
circuit = types.SimpleNamespace(PARTS=parts)

TITLES = {
    "power_entry": "Power entry: pack switch (LM74502), OV cut-off, pack metering (INA228)",
    "charger": "Charger LTC4162 and power path",
    "rails": "Rails: 5.12 V buck (LM61460), V5_CM5 eFuse, 3.3 V and 5 V_AUX bucks, 3.000 V reference",
    "branches": "Switched branches: eFuses, INA3221, heaters, LiDAR, BUS_5V",
    "chain": "Hardwired safety chain, latch K1, readback taps, watchdog",
    "drive": "Drive: VMOT eFuse, H-bridges, brake relays, bus clamp, encoders",
    "mcu": "Motion MCU STM32G474, IMU, expanders, USB, debug",
    "tof": "ToF branches (2 x TCA9548A, 11 connectors)",
    "head_link": "Head link: FT230X, RS-485, J1/J2 landings",
    "panel_io": "Panel LED / lamp / sounder drivers",
    "test": "Test points",
    "mech": "Mounting holes, chassis bonds, fiducials",
}
report = from_circuit(board, circuit, titles=TITLES, place=placement.PLACE)
os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
with open(os.path.join(HERE, "reports", "import_report.json"), "w") as f:
    json.dump(report, f, indent=1, sort_keys=True)
with open(os.path.join(HERE, "reports", "overrides_applied.json"), "w") as f:
    json.dump(override_log, f, indent=1, sort_keys=True, default=list)

NOTES = {
    "chain": "NOT A SAFETY-RATED CIRCUIT. Element order: F_CHAIN - J_MODE - J_ESTOP - J_HANDS - J_COVER - U20 - J_DOCK - U21 - U22 -\n"
             "J_BUMP_L - J_BUMP_R - U23 - U24 - K1. S2-01: PAUSE moved from J_BTN pins 5/8 to J_PAUSE (rear-right cluster).\n"
             "Stage 3 (review fixes): HEAD_LOOP = U21 (channel A, U30) + U21B (channel B, U46); latch = K1 AND U_HOLD (set only by the\n"
             "on-board REARM set stage U_SET: set-contact edge AND aux-contact level); D_RUN; K2/K3 coil return through U_LS; D_RSET.",
    "head_link": "S2-02: J_HEAD1 is a Mini-Fit Jr 2x5 (AWG 18 contacts for the heater pair); pins 1-8 = J1 pins 1-8, pins 9/10 NC.",
    "mcu": "S2-05: U42 (BMI088) GNDA on pins 2 and 4 (stock symbol). Pin use = firmware/chassis/pinmap.yaml.",
    "branches": "S2-04: R46 (U17 ILM) 845 ohm -> HEAD_HTR limit 3.96 A nominal (contract 4.0 A).",
}
for g in board.groups:
    if g.name in NOTES:
        g.notes = NOTES[g.name]

# PCB features: stock footprints are excluded from the BOM -> symbols too (schematic parity)
for p in board.parts:
    if p.mpn in ("MOUNTING-HOLE-M3", "FIDUCIAL", "NET-TIE", "SOLDER-JUMPER", "WIRE-PADS", "TEST-PAD"):
        p.bom = False
    if p.ref.startswith(("H", "FID")) and p.mpn in ("MOUNTING-HOLE-M3", "FIDUCIAL"):
        p.silk_ref = False
        p.height = 0.1
    # reference designators on silk only for connectors, ICs, relays, inductors, fuses, switches, jumpers
    # (the 600 passives are identified on the assembly drawings / Fab layer)
    if not p.ref.startswith(("J", "U", "K", "L", "F_", "SW", "JP", "Q", "H")) or p.ref.startswith("LED"):
        p.silk_ref = False
    # stage 5: the service pads carry their reference on silk (the service tests name them)
    if p.ref in ["TP%d" % n for n in range(63, 73)]:
        p.silk_ref = True

# ----------------------------------------------------------------- rails, classes, outline, copper, placement
placement.setup(board)
placement.routing(board)

# ----------------------------------------------------------------- custom DRC rules (stage 3, review M6)
# rrkicad has no custom-rule API; KiCad (kicad-cli pcb drc, used by the tool's DRC step) loads <project>.kicad_dru from the
# project directory, so the functional clearances of layout_guidance.md section 5 are written here and checked by DRC.
with open(os.path.join(HERE, "RR-CHS-MAIN.kicad_dru"), "w") as f:
    f.write(placement.chain_rules())
