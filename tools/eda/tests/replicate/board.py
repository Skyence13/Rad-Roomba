"""Tiny generator test: Board.replicate() (two identical lanes), waive() and severity().  Not a product."""
from rrkicad import Board

board = Board("REPL-TEST", title="replicate/waiver test", rev="X", date="2026-11-26", docnum="RR-EL-TEST2", layers=2)
board.rail("+3V3", "GND")
board.outline_rect(40, 20, radius=1, origin="corner")
board.zone("GND", ["F.Cu", "B.Cu"])
lanes = []
for k in range(2):
    g = board.group("lane%d" % (k + 1), "Lane %d" % (k + 1))
    g.part("U%d" % (k + 1), "Amplifier_Operational:MCP6001-OT", "MCP6001", mfr="Microchip", mpn="MCP6001T-I/OT",
           pins={"3": "IN%d" % k, "4": "OUT%d" % k, "1": "OUT%d" % k, "5": "+3V3", "2": "GND"},
           at=(8, 10, 0) if k == 0 else None)
    g.C("C%d" % (k + 1), "100n", "+3V3", "GND", mfr="Murata", mpn="GRM155R71C104KA88D", near="U%d.5" % (k + 1))
    g.R("R%d" % (k + 1), "1k", "IN%d" % k, "SRC%d" % k, mfr="Yageo", mpn="RC0402FR-071KL")
    g.R("R%d" % (k + 11), "1k", "SRC%d" % k, "GND", mfr="Yageo", mpn="RC0402FR-071KL")
    g.R("R%d" % (k + 21), "1k", "OUT%d" % k, "GND", mfr="Yageo", mpn="RC0402FR-071KL")
    lanes.append(g)
board.replicate((lanes[0], lanes[1]), dx=20.0, dy=0.0)   # lane 2 = lane 1 shifted 20 mm in X
board.waive("drc", "silk_overlap", "Test board only: reference texts may overlap, assembly uses the Fab layer.")
board.severity("drc", "silk_over_copper", "ignore", "Test board only: fab clips silkscreen with the mask opening.")
