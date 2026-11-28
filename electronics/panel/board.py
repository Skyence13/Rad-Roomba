"""RR-PANEL rev A - annunciator panel (5 LEDs, piezo sounder, external-sounder landing).

Board definition (stage 2).  Netlist source: design/circuit.py (stage 1, reviewed baseline,
imported unchanged through rrkicad.importer.from_circuit - this board has no net or part overrides).

    python3 tools/eda/rrkicad.py build electronics/panel/board.py

Frame mapping (documented, see README.md):
    envelope / circuit.py board frame (u, v)  ->  tool board frame (X, Y) = (u, v)
    origin = lower-left corner seen from the component (top) side, X along the 70 mm axis
    (u, the LED order READY..FAULT), Y along the 24 mm axis (v), top side up.
    The pick-and-place file, pinmap.json and the STEP model use the same coordinates.

Stage-2 placement decisions (no netlist change):
  * LEDs on the top side on the line v = 8 mm at the u positions of circuit.py (light pipes).
  * J1 and J2 moved from the bottom to the TOP side: the GH side-entry header is 4.25 mm high and
    the envelope allows 3 mm on the bottom but 8 mm on the top (board_envelopes.yaml RR-PANEL,
    CCR-E08(d) option "move them to the top side").  They sit in the band v 16..23 above the
    LED line, mating face towards the v = 24 edge; the cable leaves over that long edge.
  * BZ1 (3.0 mm), D1, the resistors and capacitors on the bottom side (all <= 3 mm).
  * Holes H1/H2 at the stage-1 proposal (3.5, 20.5) / (66.5, 20.5), 6 mm copper keep-out.
"""
import json
import os

from rrkicad import Board
from rrkicad.importer import from_circuit

HERE = os.path.dirname(os.path.abspath(__file__))

board = Board(
    "RR-PANEL", title="Annunciator panel", rev="A", date="2026-11-26", docnum="RR-EL-0102",
    company="Rad Roomba", layers=2, thickness=1.6, silk_refs=True,
    description="Five annunciator LEDs under 3 mm light pipes, SMD piezo sounder, landing for an optional\n"
                "external 22 mm panel sounder.  Passive board: the low-side drivers are on RR-CHS-MAIN (J_PANEL).\n"
                "Netlist = electronics/panel/design/circuit.py (stage 1), imported without overrides.")

# ------------------------------------------------------------------ placement (X = u, Y = v)
LED_U = {"LED1": 9.0, "LED2": 21.0, "LED3": 33.0, "LED4": 45.0, "LED5": 61.0}   # circuit.py LEDS table
PLACE = {}
for ref, u in LED_U.items():
    PLACE[ref] = (u, 8.0, 0, "F")                        # top, under the light pipe
    PLACE["R" + ref[3:]] = (u, 3.6, 0, "B")              # series resistor on the bottom, off the LED pads
PLACE.update({
    "J1": (30.0, 20.6, 180, "F"),    # top, mating face to the v = 24 edge
    "J2": (49.5, 20.6, 180, "F"),
    "BZ1": (53.0, 11.0, 0, "B"),
    "D1": (44.0, 15.0, 0, "B"),
    "R6": (44.0, 11.5, 90, "B"),
    "C1": (24.0, 16.0, 0, "B"),
    "C2": (36.0, 16.0, 0, "B"),
    "H1": (3.5, 20.5, 0, "F"),
    "H2": (66.5, 20.5, 0, "F"),
    "FID1": (14.0, 20.0, 0, "F"),
    "FID2": (58.0, 20.0, 0, "F"),
    "TP1": (12.0, 15.5, 0, "B"),     # V5_AUX
    "TP2": (16.0, 15.5, 0, "B"),     # GND
    "TP3": (40.0, 19.5, 0, "B"),     # BUZ_N
})

report = from_circuit(board, os.path.join(HERE, "design", "circuit.py"), place=PLACE,
                      titles={"annunciator": "Annunciator LEDs", "connector": "Harness connector (to RR-CHS-MAIN J_PANEL)",
                              "sounder": "Piezo sounder and external-sounder landing", "mech": "Mounting holes and fiducials",
                              "test": "Test pads"})
os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
with open(os.path.join(HERE, "reports", "import_report.json"), "w") as f:
    json.dump(report, f, indent=1, sort_keys=True)

# J1/J2 heights as fitted (top side now); used for the STEP envelope
board.part("J1").height = 4.25
board.part("J2").height = 4.25
# PCB features ("(pcb feature)" MPN in circuit.py): the stock footprints are excluded from the BOM,
# so the symbols are too (otherwise schematic parity reports an attribute mismatch).
for ref in ("H1", "H2", "FID1", "FID2", "TP1", "TP2", "TP3"):
    board.part(ref).bom = False
    board.part(ref).height = 0.1
for ref in ("H1", "H2", "FID1", "FID2"):
    board.part(ref).silk_ref = False
board.part("D1").silk_ref = (44.0, 17.4)

# ------------------------------------------------------------------ nets
board.rail("V5_AUX", "V12_AUX", "GND")
board.netclass("POWER", ["V5_AUX", "V12_AUX", "GND"], track=0.4, clearance=0.2, via_dia=0.6, via_drill=0.3)
board.netclass("SIGNAL", ["LED_*", "BUZ_*"], track=0.25, clearance=0.2)

# ------------------------------------------------------------------ outline, holes, copper
board.outline_rect(70.0, 24.0, radius=1.0, origin="corner")
for ref in ("H1", "H2"):
    x, y = PLACE[ref][:2]
    board.keepout("KO_" + ref, circle=(x, y, 6.0), tracks=True, vias=True, copper=True, pads=False, footprints=False)
board.zone("GND", ["F.Cu", "B.Cu"])
for _x, _y in ((2.0, 2.0), (68.0, 2.0), (2.0, 14.0), (68.0, 14.0), (15.0, 2.0), (27.0, 2.0), (39.0, 2.0),
               (51.0, 2.0), (63.0, 2.0), (15.0, 12.0), (27.0, 12.5), (39.0, 12.5), (62.0, 16.5), (20.0, 22.5), (42.0, 22.5)):
    board.via("GND", _x, _y)
board.text("{name} rev {rev}", 10.0, 12.6, layer="B.SilkS", size=1.0)
board.text("{date}", 10.0, 10.8, layer="B.SilkS", size=0.9)
for _ref, _lbl in (("LED1", "READY"), ("LED2", "MOVING"), ("LED3", "HOLD"), ("LED4", "CHARGE"), ("LED5", "FAULT")):
    board.text(_lbl, LED_U[_ref], 5.0, layer="F.SilkS", size=0.8)
board.fab_note("J1/J2 are fitted on the TOP side (4.25 mm), bottom side parts <= 3.0 mm (BZ1 3.0 mm).")
board.route(passes=60, timeout=300)
