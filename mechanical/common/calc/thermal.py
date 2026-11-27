"""Lumped steady-state heater sizing for the head and the chassis/battery bay, and condensation provisions (calculated)."""
from __future__ import annotations

import math

from .. import params as P
from . import f, inputs_table, table
from .mass_cg import A_LO, A_UP

K_FOAM, K_PLASTIC, K_AIR = 0.035, 0.25, 0.024       # W/m K (closed-cell foam, printed polymer, air) -- handbook values
H_EXT = {"still air (closed trailer, 0.1 m/s travel)": 12.0, "draught 3 m/s (open door)": 25.0}   # W/m2 K incl. ~4.5 radiation, assumed
P_HEAD_ELEC = P.POWER_C["head_allocation_w"]["electronics_target"]
P_HEAD_HTR_PEAK = P.POWER_C["head_allocation_w"]["heater_peak_at_12v"]
P_CHS_INTERNAL = 10.0 * 0.9 + 3.0 + 15.0 * 0.35      # compute + logic + drive-stage/motor losses inside the shell (from contract average budget)
P_CHS_HTR_LIMIT = P.POWER_C["rails"]["CHS_HTR"]["limit_a"] * 12.0
HTR_AVG_BUDGET = P.POWER_C["average_budget_w"]["heaters_combined"]


def u_value(h, layers):
    return 1.0 / (1.0 / h + sum(t / k for t, k in layers))


def head_ua(h, side_foam):
    lx, ly, lz = (P.HEAD_COVER_X[1] - P.HEAD_COVER_X[0]) / 1000, 2 * P.HEAD_COVER_HALF_Y / 1000, (P.HEAD_TOP_Z - 9.6) / 1000
    a_top, a_side = lx * ly, 2 * (lx + ly) * lz
    a_win = 4 * P.ACTIVE_X * P.ACTIVE_Y / 1e6
    a_bot = a_top - a_win
    u_top = u_value(h, [(0.002, K_PLASTIC), (0.003, K_FOAM)])
    u_side = u_value(h, [(0.003, K_PLASTIC)] + ([(0.003, K_FOAM)] if side_foam else []))
    h_floor = K_AIR / 0.010 + 4.5                    # 10 mm air gap to the floor + radiation
    u_win = u_value(h_floor, [(0.001, K_AIR)])       # film + 1 mm internal air gap to the screen
    u_bot = u_value(h_floor, [(0.002, K_PLASTIC)])
    ua = a_top * u_top + a_side * u_side + a_win * u_win + a_bot * u_bot + 0.06   # + receiver tongue and pigtails
    return ua, {"top": a_top * u_top, "sides": a_side * u_side, "windows": a_win * u_win, "bottom frame": a_bot * u_bot, "mount + cables": 0.06}


def body_ua(h, foam_mm):
    area = (A_UP + A_LO) / 1e6 + 0.06                # skins + underside plate
    layers = [(0.003, K_PLASTIC)] + ([(foam_mm / 1000, K_FOAM)] if foam_mm else [])
    return area * u_value(h, layers) + 0.15, area    # + wheels/shafts, caster, neck


C_HEAD = 0.41 * 1470 + 0.25 * 900 + 0.55 * 1300 + 0.15 * 1000 + 0.3 * 900   # J/K: PMMA, Al, polymer, PCB, misc
C_BODY = 1.0 * 1100 + 1.2 * 900 + 2.0 * 1300 + 1.2 * 500 + 0.8 * 1000       # pack, Al, polymer, steel/motors, electronics


# ---- one assumption set for every thermal calculation (IB-39)
T_SET_C = 10.0                 # regulated set-point at the controlled point (bay: battery-pack skin NTC; head: SiPM carrier)
H_STILL, H_MOVING = 12.0, 25.0  # W/m2 K: still air (primary), moving air (sensitivity)
# chassis self-heat inside the shell at the TYPICAL budget (electronics/analysis/power_budget.md section 1, pack terminals):
# cm5_run 7.61 + logic 1.88 + relays_armed 0.94 + protection_quies 0.15 + 35 % of drive_cold 5.67 (motor/bridge losses inside
# the shell); the LiDAR (3.54 W) sits outside on the hump and is not credited.
P_CHS_TYP = 7.61 + 1.88 + 0.94 + 0.15 + 0.35 * 5.67
HEAD_ELEC_TYP = 1.2            # W, electronics/analysis/head_afe_budget.md ("1.20 W typical, 2.10 W maximum")
HEAD_REPORT = P.REPO / "mechanical" / "head" / "out" / "head_report.md"


def head_reference():
    """The head heater figure is owned by the head engineer (real head geometry): quote it, never recompute it here."""
    try:
        txt = HEAD_REPORT.read_text(encoding="utf-8")
    except OSError:
        return None
    i = txt.find("## 9. Thermal")
    if i < 0:
        return None
    sec = txt[i:txt.find("\n## ", i + 5) if txt.find("\n## ", i + 5) > 0 else len(txt)]
    if "1.2 W" not in sec:      # still on the old 5 W credit: not the reconciled assumption set
        return None
    return [ln for ln in sec.splitlines() if ln.startswith("|")]


def run():
    md, key = [], {}
    md.append("## 7. Heater sizing at -20 / -25 C (lumped, steady state) and condensation management\n")
    md.append("**Assumption set used by every thermal calculation of the project (IB-39):** ambient -20 C and -25 C; regulated set-point "
              f"+{T_SET_C:.0f} C at the controlled point (bay: battery-pack skin; head: SiPM carrier); electronics self-heat credited at the *typical* "
              f"budget only (head {HEAD_ELEC_TYP} W from `electronics/analysis/head_afe_budget.md`; chassis {P_CHS_TYP:.1f} W inside the shell from "
              "`electronics/analysis/power_budget.md`); external film coefficient 12 W/m2K (still air, primary) with the sensitivity at 25 W/m2K (moving air); "
              "the 3 mm head jacket is fitted below 0 C. The head heater figure belongs to the head engineer (computed on the real head geometry) and is quoted, not recomputed, here.\n")
    md.append(inputs_table([
        ("Ambient cases", f"{P.T_OPERATING_C:.0f} / {P.T_QUAL_C:.0f}", "C", "RQ-029"),
        ("Bay set-point (battery-pack skin)", f"+{T_SET_C:.0f}", "C", "IB-39 assumption set"),
        ("External film coefficient, primary / sensitivity", f"{H_STILL:.0f} / {H_MOVING:.0f}", "W/m2 K", "ASSUMED, includes radiation"),
        ("Conductivity foam / printed polymer / air", f"{K_FOAM} / {K_PLASTIC} / {K_AIR}", "W/m K", "handbook"),
        ("Chassis self-heat inside the shell (typical)", f(P_CHS_TYP), "W", "power_budget.md: CM5 7.61 + logic 1.88 + relays 0.94 + protection 0.15 + 35 % of drive_cold 5.67"),
        ("Chassis heater branch limit", f(P_CHS_HTR_LIMIT, 0), "W", "contract CHS_HTR 3 A x 12 V"),
        ("Average heater budget (both zones)", HTR_AVG_BUDGET, "W", "contract average_budget_w.heaters_combined"),
        ("Body skin area", f((A_UP + A_LO) / 1e6 + 0.06, 3), "m2", "calculated from the Rev E section tables"),
        ("Heat capacity body", f"{C_BODY:.0f}", "J/K", "calculated from the mass budget, handbook c_p"),
    ]))
    md.append("\n### Chassis and battery bay\n")
    rows = []
    for hname, h in (("still air (primary)", H_STILL), ("moving air (sensitivity)", H_MOVING)):
        for foam in (0, 5):
            ua, area = body_ua(h, foam)
            r = [hname, foam, f(ua, 2)]
            for ta in (P.T_OPERATING_C, P.T_QUAL_C):
                need = ua * (T_SET_C - ta) - P_CHS_TYP
                r.append(f(max(need, 0)) + (" (> branch)" if need > P_CHS_HTR_LIMIT else ""))
            rows.append(r)
    md.append(table(["Air", "Foam liner (mm)", "UA (W/K)", f"Bay heater at -20 C, +{T_SET_C:.0f} C set-point (W)", f"Bay heater at -25 C (W)"], rows))
    uab, _ = body_ua(H_STILL, 5)
    uam, _ = body_ua(H_MOVING, 5)
    key.update(body_ua=uab, chs_htr_m20=max(uab * (T_SET_C - P.T_OPERATING_C) - P_CHS_TYP, 0), chs_htr_m25=max(uab * (T_SET_C - P.T_QUAL_C) - P_CHS_TYP, 0),
               chs_htr_m25_moving=max(uam * (T_SET_C - P.T_QUAL_C) - P_CHS_TYP, 0), chs_internal_typ_w=P_CHS_TYP, set_point_c=T_SET_C)
    md.append(f"\nWith the 5 mm liner UA = {uab:.2f} W/K (still air), time constant {C_BODY / uab / 60:.0f} min; the {P_CHS_TYP:.1f} W typical self-heat holds the bay {P_CHS_TYP / uab:.0f} K above ambient by itself. "
              f"Bay heater to hold the pack skin at +{T_SET_C:.0f} C: **{key['chs_htr_m20']:.0f} W at -20 C, {key['chs_htr_m25']:.0f} W at -25 C** in still air "
              f"({key['chs_htr_m25_moving']:.0f} W at -25 C in moving air). The fitted 20 W, 12 V polyimide pad (90 x 70 mm) with a bay NTC and an independent bimetal cut-out "
              + ("covers the still-air cases" if key["chs_htr_m25"] <= 20 else "does NOT cover the -25 C still-air case: raise the pad rating (branch limit 36 W)") + "; without the liner the bay needs more in moving air.")
    ref = head_reference()
    md.append("\n### Head (reference only)\n")
    if ref:
        md.append("Head heater power from `mechanical/head/out/head_report.md` section 9 (head engineer, same assumption set):\n")
        md += ref
        key["head_htr"] = "see mechanical/head/out/head_report.md section 9"
    else:
        md.append("Head heater power: **pending head recalculation** (the head engineer recomputes it on the real head geometry with this assumption set; "
                  "the current `mechanical/head/out/head_report.md` still credits 5 W of electronics heat). This file carries no head figure of its own.")
        key["head_htr"] = "pending head recalculation"
    md.append(f"\nThe pack's published discharge limit is -20 C: the pack must stay above ambient at the -25 C objective, which this model supports only while the electronics run (no cold-soak capability, consistent with RQ-029).")
    md.append("\n### Condensation management provisions (layout decisions)\n")
    for line in [
        "**Gasket lines**: one perimeter seal at the shell split (z = {:.1f}), O-ring/flat gaskets at every panel device, the saddle service cover, the tail-cap hatch and the head cover; closed-cell silicone foam rated -40 C.".format(P.BODY_SPLIT_Z),
        "**Breather**: one ePTFE membrane vent (M12 class) in the lower hull at the rear right quarter and one in the head rear wall beside the J2 port, so pressure equalises on the warm-room return without pumping moist air past the seals.",
        "**Desiccant**: 10 g replaceable pack with humidity indicator inside the saddle cover (visible when the cover is lifted) and a 5 g pack in the head chimney; change on indicator.",
        "**Drain paths**: the bay floor is the chassis plate; two 3 mm drain holes with duck-bill valves at the lowest points beside the caster bracket; the battery cassette sits on 2 mm ribs so melt water runs under it; the LiDAR pad and grip saddle slope outward; no pocket faces upward without a drain.",
        "**Head**: the window films are the cold face; the heater on the spreader keeps the optical stack above the film temperature so condensation forms outside, not between film and screen; the chimney is the low point and gets the membrane vent.",
        "**Warm-room return**: bag or cover the robot before entering the warm room, keep it closed until the bay NTC is within 5 K of the room (about 2 time constants = {:.0f} min for the body; head: see the head report), keep the heaters off and the electronics on during the soak; charge only above +5 C pack temperature (contract).".format(2 * C_BODY / uab / 60),
        "**Connectors**: J1/J2 and the charge inlet face upward-forward / outward and are capped when unmated; receptacles are above the split line so pooled water cannot reach them.",
    ]:
        md.append(f"- {line}")
    return "\n".join(md), key
