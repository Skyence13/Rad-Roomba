"""RR-HEAD-ACQ project-local symbols and footprints (stage 2).

Only parts that have no usable stock KiCad 9 symbol / footprint are defined here.  Geometry and pin sources:

  symbols (pin NUMBERS and NAMES are those of design/circuit.py, which stage 1 took from the datasheets listed in
  head_design_review_checklist.md B1; only the electrical pin TYPES are added here so that ERC can check them):
    TLV3502_DCN      TI TLV3502 SOT-23-8 (DCN), dual comparator         stage 1: datasheet-read
    LMR51606_DBV     TI LMR51606 SOT-23-6 buck                         stage 1: datasheet-read
    TPS61391_RTE     TI TPS61391 WQFN-16 boost / current mirror        stage 1: datasheet-read (SLVSFE7)
    DAC60508_RTE     TI DAC60508 WQFN-16 8-channel DAC                 stage 1: datasheet-read (SLASEL1D)
    ISO1430_DW       TI ISO1430 SOIC-16W isolated RS-485                stage 1: datasheet-read (SLLSF22I)
    ISO7710_D        TI ISO7710 SOIC-8 single-channel isolator (DNP)    stage 1: FROM MEMORY (verify)
    TMP117_DRV_EP    TI TMP117 WSON-6 with exposed pad                  stage 1: FROM MEMORY (verify)
    RR-HEAD-SHLD-A   lane shield can (mechanical part, no pins)

  footprints:
    Harwin_S1711-46R_ShieldClip   single SMT pad 4.2 x 1.6 mm, clip body 3.9 x 1.3 x 1.5 mm.
                                  FROM MEMORY of the Harwin S1711-46R drawing - VERIFY before ordering.
    L_CommonMode_TDK_ACM4520      4 pads, body 4.5 x 2.0 mm (stage-1 package text "4.5x2.0 mm"); pad layout
                                  from memory of the TDK ACM series - VERIFY against the TDK drawing.
    RR-HEAD-SHLD-A_LaneShieldCan  no pads: F.Fab = can outline 36.0 x 32.0 mm (outside), mouse holes and the 12
                                  clip positions as drawn in mechanical/head/production/drawings
                                  (RR-HD-S-122 sheet, RR-HEAD-SHLD-A) with the stage-2 changes CR-M01 (can shifted
                                  +2.0 mm in v) and CR-M04 (mouse holes at the anode positions).  Written by
                                  ``can_footprint_text()`` because the tool's footprint generator needs >= 1 pad.
"""
from rrkicad import Pad, SymPin
from rrkicad.model import stable_uuid

# ------------------------------------------------------------------------------------- lane shield can geometry
CAN_W, CAN_D, CAN_H, CAN_WALL = 36.0, 32.0, 5.0, 0.2       # outside u-width, v-depth, height, wall
CAN_V0 = 8.25                                               # rear outer face (v); stage 1 / mech drawing: 5.5 (CR-M01)
CAN_V1 = CAN_V0 + CAN_D                                     # front outer face 39.5
MOUSE_W, MOUSE_H = 2.0, 1.2                                 # mouse hole in the rear wall (mech drawing)
# anode mouse holes (du about the lane centre) - follow the anode U.FL positions of the lane block (CR-M04)
MOUSE_DU = (-10.38, 11.87)
# clip positions (du, v, rot): 3 per side, on the wall centre line
CLIPS = ([(du, CAN_V0 + 0.1, 0) for du in (-6.5, 2.5, 15.0)] +
         [(du, CAN_V1 - 0.1, 0) for du in (-12.0, 0.0, 12.0)] +
         [(-CAN_W / 2 + 0.1, v, 90) for v in (CAN_V0 + 7.0, CAN_V0 + 16.0, CAN_V0 + 25.0)] +
         [(CAN_W / 2 - 0.1, v, 90) for v in (CAN_V0 + 7.0, CAN_V0 + 16.0, CAN_V0 + 25.0)])


def define(board):
    S = board.symbol
    S("TLV3502_DCN", [SymPin(1, "+INA", "input", "L"), SymPin(2, "-INA", "input", "L"),
                      SymPin(3, "+INB", "input", "L"), SymPin(4, "-INB", "input", "L"),
                      SymPin(7, "OUTA", "output", "R"), SymPin(6, "OUTB", "output", "R"),
                      SymPin(8, "V+", "power_in", "T"), SymPin(5, "V-", "power_in", "B")],
      ref_prefix="U", description="TLV3502 dual 4.5 ns comparator, SOT-23-8 (DCN) pin-out per design/circuit.py")
    S("LMR51606_DBV", [SymPin(5, "VIN", "power_in", "L"), SymPin(4, "EN", "input", "L"), SymPin(3, "FB", "input", "L"),
                       SymPin(1, "CB", "passive", "R"), SymPin(6, "SW", "passive", "R"), SymPin(2, "GND", "power_in", "B")],
      ref_prefix="U", description="LMR51606 65 V 0.6 A buck, SOT-23-6")
    S("TPS61391_RTE", [SymPin(10, "VIN", "power_in", "L"), SymPin(14, "AVCC", "power_in", "L"), SymPin(15, "AVCC", "power_in", "L"),
                       SymPin(13, "EN", "input", "L"), SymPin(12, "FB", "input", "L"), SymPin(11, "ISHORT", "passive", "L"),
                       SymPin(9, "CAP", "passive", "L"), SymPin(1, "NC", "no_connect", "L"), SymPin(2, "NC", "no_connect", "L"),
                       SymPin(8, "SW", "passive", "R"), SymPin(6, "MONIN", "passive", "R"), SymPin(5, "APD", "passive", "R"),
                       SymPin(4, "MON1", "output", "R"), SymPin(3, "MON2", "output", "R"),
                       SymPin(7, "GND", "power_in", "B"), SymPin(16, "AGND", "power_in", "B"), SymPin(17, "PAD", "passive", "B")],
      ref_prefix="U", description="TPS61391 85 V boost with APD current mirror, WQFN-16 3x3 (RTE)")
    S("DAC60508_RTE", [SymPin(7, "VDD", "power_in", "T"), SymPin(16, "VIO", "power_in", "T"),
                       SymPin(12, "~{CS}", "input", "L"), SymPin(13, "SCLK", "input", "L"), SymPin(14, "SDI", "input", "L"),
                       SymPin(15, "SDO", "tri_state", "L"), SymPin(1, "REF", "passive", "L"),
                       SymPin(2, "OUT0", "output", "R"), SymPin(3, "OUT1", "output", "R"), SymPin(4, "OUT2", "output", "R"),
                       SymPin(5, "OUT3", "output", "R"), SymPin(8, "OUT4", "output", "R"), SymPin(9, "OUT5", "output", "R"),
                       SymPin(10, "OUT6", "output", "R"), SymPin(11, "OUT7", "output", "R"),
                       SymPin(6, "GND", "power_in", "B"), SymPin(17, "PAD", "passive", "B")],
      ref_prefix="U", description="DAC60508 8-channel 12-bit DAC with 2.5 V reference, WQFN-16 3x3 (RTE)")
    S("ISO1430_DW", [SymPin(1, "VCC1", "power_in", "L"), SymPin(6, "D", "input", "L"), SymPin(5, "DE", "input", "L"),
                     SymPin(4, "~{RE}", "input", "L"), SymPin(3, "R", "output", "L"), SymPin(2, "GND1", "power_in", "L"),
                     SymPin(8, "GND1", "power_in", "L"), SymPin(7, "NC", "no_connect", "L"),
                     SymPin(16, "VCC2", "power_in", "R"), SymPin(12, "A", "bidirectional", "R"), SymPin(13, "B", "bidirectional", "R"),
                     SymPin(9, "GND2", "power_in", "R"), SymPin(15, "GND2", "power_in", "R"), SymPin(10, "NC", "no_connect", "R"),
                     SymPin(11, "NC", "no_connect", "R"), SymPin(14, "NC", "no_connect", "R")],
      ref_prefix="U", description="ISO1430 isolated half-duplex RS-485 transceiver, SOIC-16W")
    S("ISO7710_D", [SymPin(1, "VCC1", "power_in", "L"), SymPin(2, "INA", "input", "L"), SymPin(3, "NC", "no_connect", "L"),
                    SymPin(4, "GND1", "power_in", "L"), SymPin(8, "VCC2", "power_in", "R"), SymPin(6, "OUT", "output", "R"),
                    SymPin(7, "NC", "no_connect", "R"), SymPin(5, "GND2", "power_in", "R")],
      ref_prefix="U", description="ISO7710 single-channel digital isolator, SOIC-8 (pin-out from memory, verify)")
    S("TMP117_DRV_EP", [SymPin(1, "SCL", "input", "L"), SymPin(6, "SDA", "bidirectional", "L"), SymPin(4, "ADD0", "input", "L"),
                        SymPin(3, "ALERT", "open_collector", "R"), SymPin(5, "V+", "power_in", "T"),
                        SymPin(2, "GND", "power_in", "B"), SymPin(7, "PAD", "passive", "B")],
      ref_prefix="U", description="TMP117 digital temperature sensor, WSON-6 with exposed pad (pin-out from memory, verify)")
    S("RR-HEAD-SHLD-A", [], ref_prefix="SH",
      description="RR-HEAD-SHLD-A lane shield can 36 x 32 x 5 mm, held by 12 S1711-46R clips (mechanical part, no pins)")

    F = board.footprint
    F("Harwin_S1711-46R_ShieldClip", [Pad(1, 0.0, 0.0, 4.2, 1.6)], body=(3.9, 1.3), height=1.5, pin1=False,
      description="Harwin S1711-46R SMT shield-can clip, single pad 4.2 x 1.6 mm, centred on the can wall "
                  "(geometry FROM MEMORY - verify against the Harwin drawing)")
    F("L_CommonMode_TDK_ACM4520", [Pad(1, -1.6, -0.6, 0.9, 0.7), Pad(2, 1.6, -0.6, 0.9, 0.7),
                                   Pad(3, 1.6, 0.6, 0.9, 0.7), Pad(4, -1.6, 0.6, 0.9, 0.7)],
      body=(4.5, 2.0), height=2.0,
      description="TDK ACM4520 common-mode choke 4.5 x 2.0 mm, pads 1/4 input side, 2/3 output side "
                  "(geometry FROM MEMORY - verify against the TDK drawing)")
    # placeholder entry so the tool lists the can footprint; its file is replaced by can_footprint_text()
    F("RR-HEAD-SHLD-A_LaneShieldCan", [Pad(1, 0.0, 0.0, 0.1)], body=(CAN_W, CAN_D), height=CAN_H, pin1=False,
      description="lane shield can outline (replaced at generation time)")


def can_footprint_text(name="RR-HEAD-SHLD-A_LaneShieldCan"):
    """KiCad 9 footprint of the lane shield can: outline only, no pads, no courtyard.

    Origin = can centre.  Footprint frame: x = +u, y = -v (y down).  Rear wall at y = +CAN_D/2."""
    u = lambda *k: stable_uuid("fp", name, *k)            # noqa: E731
    hw, hd = CAN_W / 2.0, CAN_D / 2.0
    L = []

    def line(x0, y0, x1, y1, layer, w, k):
        L.append('\t(fp_line (start %.3f %.3f) (end %.3f %.3f) (stroke (width %.2f) (type solid)) (layer "%s") (uuid "%s"))'
                 % (x0, y0, x1, y1, w, layer, u("l", k)))

    def rect(x0, y0, x1, y1, layer, w, k):
        L.append('\t(fp_rect (start %.3f %.3f) (end %.3f %.3f) (stroke (width %.2f) (type solid)) (fill no) (layer "%s") (uuid "%s"))'
                 % (x0, y0, x1, y1, w, layer, u("r", k)))
    rect(-hw, -hd, hw, hd, "F.Fab", 0.1, "outer")
    rect(-hw + CAN_WALL, -hd + CAN_WALL, hw - CAN_WALL, hd - CAN_WALL, "F.Fab", 0.05, "inner")
    for i, du in enumerate(MOUSE_DU):
        rect(du - MOUSE_W / 2, hd - CAN_WALL - 0.3, du + MOUSE_W / 2, hd, "F.Fab", 0.05, "mouse%d" % i)
    # silkscreen: corner marks only (the walls sit on bare laminate / clip pads)
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        cx, cy = sx * (hw + 0.3), sy * (hd + 0.3)
        line(cx, cy, cx - sx * 2.0, cy, "F.SilkS", 0.12, "cx%d" % i)
        line(cx, cy, cx, cy - sy * 2.0, "F.SilkS", 0.12, "cy%d" % i)
    for i, (du, v, rot) in enumerate(CLIPS):
        x, y = du, -(v - (CAN_V0 + hd))
        if rot == 0:
            rect(x - 2.1, y - 0.8, x + 2.1, y + 0.8, "Dwgs.User", 0.05, "clip%d" % i)
        else:
            rect(x - 0.8, y - 2.1, x + 0.8, y + 2.1, "Dwgs.User", 0.05, "clip%d" % i)
    body = "\n".join(L)
    return ('(footprint "%s"\n\t(version 20241229)\n\t(generator "rrkicad")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n'
            '\t(descr "RR-HEAD-SHLD-A lane shield can 36.0 x 32.0 x 5.0 mm outside, 0.2 mm wall, held by 12 Harwin S1711-46R clips '
            '(separate parts SHxx01..12). Outline per mechanical drawing RR-HD-S-122 with stage-2 changes CR-M01/CR-M04. No pads.")\n'
            '\t(property "Reference" "REF**" (at 0 %.2f 0) (layer "F.Fab") (uuid "%s") (effects (font (size 1 1) (thickness 0.15))))\n'
            '\t(property "Value" "%s" (at 0 %.2f 0) (layer "F.Fab") (hide yes) (uuid "%s") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
            '\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "%s") (effects (font (size 1 1) (thickness 0.15))))\n'
            '\t(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "%s") (effects (font (size 1 1) (thickness 0.15))))\n'
            '\t(attr exclude_from_pos_files allow_missing_courtyard)\n%s\n'
            '\t(fp_text user "${REFERENCE}" (at 0 0 0) (layer "F.Fab") (uuid "%s") (effects (font (size 1 1) (thickness 0.15))))\n'
            '\t(embedded_fonts no)\n)\n') % (
                name, -hd - 1.0, u("ref"), name, hd + 1.0, u("val"), u("ds"), u("de"), body, u("rt"))


def install_can_footprint_hook():
    """Tool work-around (no change in tools/eda): rrkicad's local-footprint writer requires >= 1 pad, so the
    placeholder entry is swapped for the pad-less can footprint when the .kicad_mod files are written."""
    from rrkicad import locallib
    if getattr(locallib, "_rr_head_can_hook", False):
        return
    orig = locallib.make_footprint

    def make_footprint(name, spec):
        if name == "RR-HEAD-SHLD-A_LaneShieldCan":
            return can_footprint_text(name)
        return orig(name, spec)
    locallib.make_footprint = make_footprint
    locallib._rr_head_can_hook = True
