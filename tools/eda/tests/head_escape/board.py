"""COPY for tools/eda tests (escape + budgeted continue runs) of electronics/head_acq/board.py - not the deliverable.

RR-HEAD-ACQ rev A - detector-head acquisition board (8 SiPM front ends in 4 identical lanes, 0-62.5 V bias,
4 DACs, STM32G474VET6, isolated RS-485, heater switch, power entry).

Board definition (stage 2).  Single source of truth for the KiCad project in this directory.

    python3 tools/eda/rrkicad.py sch   electronics/head_acq/board.py              # schematic + ERC + PDF
    python3 tools/eda/rrkicad.py build electronics/head_acq/board.py --no-route   # + placed PCB, DRC, outputs
    python3 tools/eda/rrkicad.py build electronics/head_acq/board.py              # + autorouter

Netlist = design/circuit.py (stage 1, reviewed baseline, NOT edited) + overrides.py (every stage-2 deviation,
IDs S2-xx = STAGE2_CHANGE_REQUESTS.md).  Library additions: libs.py.  Placement / copper: layout.py.

Frame mapping (README.md section 2):
    board_envelopes.yaml RR-HEAD-ACQ (u, v)  ->  tool board frame (X, Y) = (u, v), no rotation, no offset.
    origin = rear-left corner seen from above (top side up); X = u = toward the robot's right (base_link -y);
    Y = v = forward (base_link +x).   base_link = (83.2 + Y, 163.0 - X, 34.5 + z) mm (PCB underside z = 34.5).
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from rrkicad import Board, Rules                 # noqa: E402
from rrkicad.importer import from_circuit        # noqa: E402
import overrides                                 # noqa: E402
import libs                                      # noqa: E402

board = Board(
    "RR-HEAD-ACQ", title="Detector-head acquisition board", rev="A", date="2026-11-26", docnum="RR-EL-0103",
    company="Rad Roomba", layers=6, thickness=1.6, silk_refs=True, paper="A3",
    rules=Rules(min_track=0.15, min_clearance=0.15, track=0.2, clearance=0.15, via_dia=0.6, via_drill=0.3,
                edge_clearance=0.5),
    description="Detector-head acquisition board: eight SiPM front ends in four identical lanes (floor + reference channel:\n"
                "preamp, fast/slow shaping, comparators, event latches), programmable 0-62.5 V bias with per-channel trim,\n"
                "four DACs, STM32G474VET6, isolated RS-485, heater switch, input protection and low-noise rails.\n"
                "Netlist: design/circuit.py (stage 1) + overrides.py (stage 2: S2-xx, see STAGE2_CHANGE_REQUESTS.md).\n"
                "Lanes: sheets LANEk_FLOOR / LANEk_REF / LANEk_LOGIC are identical for k = 0..3 (renamed nets only).")

libs.define(board)
libs.install_can_footprint_hook()

# ----------------------------------------------------------------------------------- netlist import
base = overrides.load_circuit()
parts, override_log = overrides.apply(base.PARTS)

# body heights for the generated 3D envelopes (mm above the board; mated height where a plug sits on it)
HEIGHT_BY_MPN = {
    "43650-0800": 6.0, "43650-0600": 6.0,          # Micro-Fit RA header: seated height UNVERIFIED (CCR-HE-02)
    "U.FL-R-SMT-1(10)": 2.5,                        # mated with an MHF/U.FL plug
    "SM06B-GHS-TB(LF)(SN)": 4.25, "SM08B-GHS-TB(LF)(SN)": 4.25, "SM04B-GHS-TB(LF)(SN)": 4.25,
    "SM03B-GHS-TB(LF)(SN)": 4.25, "SM02B-GHS-TB(LF)(SN)": 4.25,
    "RR-HEAD-SHLD-A": 5.0, "S1711-46R": 1.5,
    "XAL4040-103MEB": 4.1, "LPS4018-103MRB": 1.8, "LQH32CN100K53L": 2.0, "ACM4520-901-2P-T000": 2.0,
    "SUD50P04-08-GE3": 2.4, "SMBJ16A": 2.4, "STM32G474VET6": 1.6, "ISO1430BDWR": 2.65,
    "CRA2512-FZ-R010ELF": 0.7, "TC2030-IDC-NL (cable)": 0.1,
}
for p in parts:
    if p.get("mpn") in HEIGHT_BY_MPN:
        p["height_mm"] = HEIGHT_BY_MPN[p["mpn"]]

# sheet order: power and bias first, then the four lane sheet sets, then the rest
ORDER = ["POWER_IN", "POWER_REG", "HEATER", "BIAS", "DAC", "MONITOR", "MCU", "COMM_ISOLATED"] + \
        ["LANE%d_%s" % (k, s) for k in range(4) for s in ("FLOOR", "REF", "LOGIC")] + ["MECH"]
TITLES = {"POWER_IN": "J1 power entry: TVS, CM choke, eFuse, pi filter, interlock loop",
          "POWER_REG": "Rails: 5.63 V buck, +5V_A / +3V3_EVT / +3V3 LDOs, ADC reference",
          "HEATER": "Heater high-side switch, current sense, cut-out status, heater NTC",
          "BIAS": "SiPM bias 0-62.5 V: boost, current mirror, linear post-regulator, permit chain",
          "DAC": "DACs (thresholds, HV_SET, trims), baseline VBL, LED amplitude, IMON buffer",
          "MONITOR": "Monitor and pulser selects, monitor buffer, IMON mux",
          "MCU": "STM32G474VET6, TCXO, SWD, debug UART, temperature, EEPROM, expander",
          "COMM_ISOLATED": "J2: isolated RS-485 (ISO1430B), reserved sync receiver (DNP)",
          "MECH": "Mounting holes (FRAME), frame bond, fiducials"}
for k in range(4):
    TITLES["LANE%d_FLOOR" % k] = "Lane %d floor channel F%d: SiPM inputs, bias filter, preamp, fast + slow shaper, comparators" % (k, k)
    TITLES["LANE%d_REF" % k] = "Lane %d reference channel R%d: SiPM inputs, bias filter, preamp, fast shaper, comparators" % (k, k)
    TITLES["LANE%d_LOGIC" % k] = "Lane %d logic: trim buffers, event latches, monitor mux, aux pigtail, shield can" % k
NOTES = {"LANE%d_%s" % (k, s): "Identical for lanes 0..3 (stage-1 self-check: lanes identical after renaming). "
         "PCB: lane 0 is placed, lanes 1..3 are copies at du = +87.5 mm steps." for k in range(4) for s in ("FLOOR", "REF", "LOGIC")}
NOTES["POWER_IN"] = ("IB-21: zone identification inputs (J2002..J2004 pins 3/4 -> BUMP_ZONE_x_N) are NOT AVAILABLE in rev A "
                     "(single-pole rail switches); parts kept, inputs idle high.")
NOTES["MECH"] = "IB-38: R2801 (FRAME-GND 0 ohm bond at H1) is fitted in BOTH builds."
NOTES["DAC"] = "IB-25: SiPM breakdown spread within one head <= 2.0 V (trim range 2.4 V less 0.4 V reserve)."
groups = {}
for name in ORDER:
    groups[name] = board.group(name, TITLES.get(name, name), notes=NOTES.get(name, ""))

# project-local symbols are passed per ref (the importer only resolves stock symbol hints itself)
local_syms = {p["ref"]: p["symbol_hint"] for p in parts if str(p.get("symbol_hint", "")).startswith("rr_local:")}
circuit = types.SimpleNamespace(PARTS=parts)
HAVE_LAYOUT = os.path.exists(os.path.join(HERE, "layout.py"))
if HAVE_LAYOUT:
    import layout                                 # noqa: E402
place = layout.placement() if HAVE_LAYOUT else {}
report = from_circuit(board, circuit, symbols=local_syms, titles=TITLES, place=place)
os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
with open(os.path.join(HERE, "reports", "import_report.json"), "w") as f:
    json.dump(report, f, indent=1, sort_keys=True)
with open(os.path.join(HERE, "reports", "overrides_applied.json"), "w") as f:
    json.dump(override_log, f, indent=1, sort_keys=True)

# ----------------------------------------------------------------------------------- nets
board.rail("GND", "+3V3", "+5V_A", "+3V3_EVT", "+5V6", "+3V3A", "BUS_GND")
board.rail("FRAME", style="gnd")

board.outline_rect(326.0, 96.0, radius=1.0, origin="corner")

if HAVE_LAYOUT:                                    # replication, zones, net classes, keep-outs, pre-routes
    layout.apply(board, parts)
