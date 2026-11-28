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
    # stage 3 changes the netlist through electronics/head_acq/overrides.py (design/ is not edited): check the OVERRIDDEN parts
    sys.path.insert(0, str(DESIGN.parent))
    import copy
    import overrides
    s3_parts, _log = overrides.apply(copy.deepcopy(circuit.PARTS))
    circuit.PARTS = s3_parts

    errors = []
    parts = {p["ref"]: p for p in circuit.PARTS}
    text = (HEAD / "core" / "rrh_board.h").read_text()
    n = 0
    for m in re.finditer(r"#define RRH_([RC])(\d+)_(OHM|NF|PF|MOHM)\s+(\d+)u", text):
        kind, num, unit, val = m.group(1), m.group(2), m.group(3), int(m.group(4))
        ref = kind + num
        p = parts.get(ref)
        if p is None:
            errors.append(f"{ref}: not in circuit.py")
            continue
        if kind == "R" and unit == "MOHM":
            if p["value"].lower() != "%dmr" % val:
                errors.append(f"{ref}: header {val} mohm, circuit {p['value']}")
        elif kind == "R":
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
    # stage 3 nets and parts the firmware relies on (S3-01 ... S3-04)
    def pin_net(ref, pin):
        v = parts_by_ref()[ref]["pins"].get(pin)
        return v[1] if v else None

    def parts_by_ref():
        return {p["ref"]: p for p in circuit.PARTS}

    pr = parts_by_ref()
    want = [("U2405", "12", "MON_LANE_EN"), ("U2701", "6", "MON_LANE_EN"), ("R2418", "1", "MON_LANE_EN"), ("R2418", "2", "GND"),
            ("TP2402", "1", "MON_LANE_EN"), ("U2405", "4", "MON_EXT"), ("U2405", "5", "HV_PERMIT"), ("U2405", "6", "HV_INH_N"),
            ("U2405", "7", "LID_G"), ("U2405", "9", "EF_FLT_N"), ("U2405", "10", "HWREV0"), ("U2405", "11", "HWREV1"),
            ("R2802", "2", "MON_BUS"), ("R2802", "1", "FRAME"), ("R2702", "1", "MON_BUS"), ("R2702", "2", "VBL"),
            ("F2801", "1", "FRAME"), ("F2801", "2", "FRAME_F"), ("R2801", "1", "FRAME_F"), ("R2801", "2", "GND")]
    for ref, pin, net in want:
        if pin_net(ref, pin) != net:
            errors.append(f"{ref}.{pin} is on {pin_net(ref, pin)}, firmware expects {net} (stage 3)")
    if pr["F2801"]["value"] != "0.5A fast":
        errors.append("F2801 value changed: " + pr["F2801"]["value"])
    for c in range(8):
        b = 100 * (c + 1)
        ch = ["F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"][c]
        if pin_net(f"R{b + 25}", "1") != ch + "_FAST" or pr[f"R{b + 25}"]["ohms"] != 10e3:
            errors.append(f"R{b + 25}: FAST monitor tap not on {ch}_FAST / 10 k")
        if pin_net(f"R{b + 19}", "1") != ch + "_PRE" or pr[f"R{b + 19}"]["ohms"] != 10e3:
            errors.append(f"R{b + 19}: preamp monitor tap not on {ch}_PRE / 10 k")
        if c < 4 and (pin_net(f"R{b + 34}", "1") != ch + "_SLOW" or pr[f"R{b + 34}"]["ohms"] != 10e3):
            errors.append(f"R{b + 34}: SLOW monitor tap not on {ch}_SLOW / 10 k")
        if pr[f"C{b + 50}"]["value"] != "47nF":
            errors.append(f"C{b + 50}: pole-zero capacitor is {pr[f'C{b + 50}']['value']}, expected 47nF")
    # heater current sense: 0.5 V/A = 10 mohm x gain 50 (INA180A2); the firmware's sense scale
    if "INA180A2" not in pr["U2601"]["mpn"] or pr["R2601"]["value"].lower() != "10mr":
        errors.append("heater sense changed (R2601 / U2601): the firmware assumes 10 mohm x gain 50")
    if pin_net("U2601", "1") != "HTR_SENSE_R" or pin_net("R2602", "2") != "HTR_SENSE":
        errors.append("heater sense path to PB12 changed")
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
    print(f"check_circuit (stage-3 netlist): {n} component values and {len(pm['pins'])} MCU pins compared with circuit.py; "
          f"bias law x{law:.1f}, BIAS_VMON 1:{ratio:.4f}, OVP trip {trip:.2f} V, HV_RAW {raw:.1f} V, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
