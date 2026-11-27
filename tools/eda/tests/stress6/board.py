"""6-layer variant of the stress board (same circuit; F.Cu sig / In1 GND / In2 sig / In3 sig / In4 PWR / B.Cu sig)
with the MCU decoupling capacitors on the BOTTOM side, like the 4-layer base definition.

    python3 tools/eda/rrkicad.py build tools/eda/tests/stress6/board.py
"""
import os

_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stress", "board.py")).read()
_src = _src.replace('"STRESS-150"', '"STRESS-150-6L"').replace("layers=4", "layers=6").replace('["In2.Cu"]', '["In4.Cu"]')
# (the MCU decoupling is on the bottom side in the base definition as well)
assert 'side="B"' in _src and "layers=6" in _src and "In4.Cu" in _src
exec(compile(_src, "stress/board.py (6-layer variant)", "exec"))
