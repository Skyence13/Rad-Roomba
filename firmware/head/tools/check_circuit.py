#!/usr/bin/env python3
"""Check the board constants of core/rrh_board.h and pinmap.yaml against electronics/head_acq/design/circuit.py.

* every `#define RRH_R<n>_OHM` / `RRH_C<n>_NF` names a reference designator; its value must equal the part
  value in circuit.py (the circuit is only imported, never written);
* every MCU pin of pinmap.yaml must carry the net name circuit.py gives that LQFP100 pin;
* the numbers quoted in the firmware documentation are recomputed (bias law, divider, OVP trip, current monitor).
Exit 0 = consistent. Skipped (exit 0, message) if the electronics tree is not present.
"""
import os
import re
import sys
from pathlib import Path

import yaml

HEAD = Path(__file__).resolve().parents[1]
REPO = HEAD.parents[1]
DESIGN = REPO / "electronics" / "head_acq" / "design"


def main():
    if not (DESIGN / "circuit.py").exists():
        print("check_circuit: electronics/head_acq/design/circuit.py not present, skipped")
        return 0
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(DESIGN))
    import circuit

    errors = []
    parts = {p["ref"]: p for p in circuit.PARTS}
    text = (HEAD / "core" / "rrh_board.h").read_text()
    n = 0
    for m in re.finditer(r"#define RRH_([RC])(\d+)_(OHM|NF|PF)\s+(\d+)u", text):
        kind, num, unit, val = m.group(1), m.group(2), m.group(3), int(m.group(4))
        ref = kind + num
        p = parts.get(ref)
        if p is None:
            errors.append(f"{ref}: not in circuit.py")
            continue
        if kind == "R":
            want = p.get("ohms")
            if want is None or abs(want - val) > 1e-6:
                errors.append(f"{ref}: header {val} ohm, circuit {want}")
        else:
            mult = {"NF": 1.0, "PF": 1.0}[unit]
            txt = p["value"].lower().replace(" ", "")
            circ = float(re.match(r"[\d.]+", txt).group(0)) * ({"pf": 1.0, "nf": 1000.0, "uf": 1e6}[re.search(r"[a-z]+$", txt).group(0)]) / 1000.0
            if unit == "NF" and abs(circ - val) > 1e-9:
                errors.append(f"{ref}: header {val} nF, circuit {p['value']}")
        n += 1
    # the channel-0 designators stand for all eight channels (same generator): check R205..R805, R208..R808, C209..C809
    for c in range(1, 8):
        for base in (105, 108):
            if parts[f"R{base + 100 * c}"]["ohms"] != parts[f"R{base}"]["ohms"]:
                errors.append(f"R{base + 100 * c} differs from R{base}")
        if parts[f"C{109 + 100 * c}"]["value"] != parts["C109"]["value"]:
            errors.append(f"C{109 + 100 * c} differs from C109")
    # pins
    pm = yaml.safe_load((HEAD / "pinmap.yaml").read_text())
    alias = {"VBAT": "+3V3", "GND": "GND", "+3V3": "+3V3", "AGND": "GND"}
    for e in pm["pins"]:
        port, net = circuit.MCU_PINMAP[e["lqfp100"]]
        want = alias.get(e["signal"], e["signal"])
        if port != e["pin"] or net != want:
            errors.append(f"pin {e['lqfp100']}: pinmap {e['pin']}/{e['signal']}, circuit {port}/{net}")
    # derived numbers
    r = lambda k: parts[k]["ohms"]  # noqa: E731
    ratio = (r("R2217") + r("R2218") + r("R2219")) / r("R2219")
    trip = 3.0 * r("R2223") / (r("R2222") + r("R2223")) * ratio
    raw = 1.2 * (1 + (r("R2201") + r("R2202")) / r("R2203"))
    law = (r("R2213") + r("R2214") + r("R2215")) / r("R2215")
    assert abs(law - 25.0) < 1e-9 and abs(ratio - 25.2233) < 1e-3
    if not (31.4 < trip < 31.7):
        errors.append(f"fitted OVP trip {trip:.3f} V, expected 31.5 V (IB-18c)")
    if not (36.9 < raw < 37.3):
        errors.append(f"fitted HV_RAW {raw:.2f} V, expected 37.1 V")
    # the defaults of the strap table in rrh_board.c must be the rev A parts
    if abs(r("R2203") - 71500) > 1e-6 or abs(r("R2223") - 7150) > 1e-6:
        errors.append("rev A straps changed: update rrh_straps and README")
    for e in errors:
        print("CIRCUIT ERROR:", e, file=sys.stderr)
    print(f"check_circuit: {n} component values and {len(pm['pins'])} MCU pins compared with circuit.py; "
          f"bias law x{law:.1f}, BIAS_VMON 1:{ratio:.4f}, OVP trip {trip:.2f} V, HV_RAW {raw:.1f} V, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
