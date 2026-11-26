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


def run():
    md, key = [], {}
    md.append("## 7. Heater sizing at -20 / -25 C (lumped, steady state) and condensation management\n")
    md.append(inputs_table([
        ("External film coefficient, still / draught", "12 / 25", "W/m2 K", "ASSUMED, includes radiation"),
        ("Conductivity foam / printed polymer / air", f"{K_FOAM} / {K_PLASTIC} / {K_AIR}", "W/m K", "handbook"),
        ("Head insulation", "3 mm closed-cell foam under the cover; side walls with or without 3 mm foam", "", "layout decision / option"),
        ("Head window path", "10 mm air gap to floor + radiation, 1 mm internal air gap", "", "Rev D optical stack"),
        ("Head electronics dissipation", P_HEAD_ELEC, "W", "contract head_allocation_w.electronics_target"),
        ("Head heater peak / J1 limit", f"{P_HEAD_HTR_PEAK} / {P.POWER_C['rails']['HEAD_HTR']['limit_a'] * 12:.0f}", "W", "contract"),
        ("Chassis internal dissipation", f(P_CHS_INTERNAL), "W", "contract average budget: 90 % compute + logic + 35 % of drive"),
        ("Chassis heater branch limit", f(P_CHS_HTR_LIMIT, 0), "W", "contract CHS_HTR 3 A x 12 V"),
        ("Average heater budget (both zones)", HTR_AVG_BUDGET, "W", "contract average_budget_w.heaters_combined"),
        ("Body skin area", f((A_UP + A_LO) / 1e6 + 0.06, 3), "m2", "calculated from the Rev E section tables"),
        ("Heat capacity head / body", f"{C_HEAD:.0f} / {C_BODY:.0f}", "J/K", "calculated from the mass budget, handbook c_p"),
    ]))
    md.append("\n### Head\n")
    rows = []
    for hname, h in H_EXT.items():
        for foam in (False, True):
            ua, parts = head_ua(h, foam)
            for tset in (5.0, 10.0):
                r = [hname, "yes" if foam else "no", f(ua, 2), tset]
                for ta in (P.T_OPERATING_C, P.T_QUAL_C):
                    need = ua * (tset - ta) - P_HEAD_ELEC
                    r.append(f(max(need, 0)) + (" (> peak)" if need > P_HEAD_HTR_PEAK else ""))
                rows.append(r)
            if foam and h == 12.0:
                key["head_ua"] = ua
                key["head_parts"] = parts
    md.append(table(["Air", "Side-wall foam", "UA (W/K)", "Set-point (C)", "Heater at -20 C (W)", "Heater at -25 C (W)"], rows))
    ua0, _ = head_ua(12.0, True)
    tau = C_HEAD / ua0 / 60
    t_inf = P.T_OPERATING_C + P_HEAD_ELEC / ua0
    md.append(f"\nWith side foam in still air UA = {ua0:.2f} W/K ({', '.join(f'{k} {v:.2f}' for k, v in key['head_parts'].items())}); time constant {tau:.0f} min. "
              f"Unheated, a head started at +20 C settles at {t_inf:.0f} C and passes 0 C after {-tau * math.log((0 - t_inf) / (20 - t_inf)):.0f} min, so the heater is needed for any mission longer than that. "
              f"Sizing: **{ua0 * (10 - P.T_QUAL_C) - P_HEAD_ELEC:.0f} W** holds +10 C at -25 C in still air; the 30 W peak allocation covers draught only with the side-wall foam. Use a 4-zone film of 30 W total at 12 V (7.5 W per lane, 2.4 kOhm... see electronics) on the spreader underside.")
    key.update(head_htr_m20=ua0 * (10 - P.T_OPERATING_C) - P_HEAD_ELEC, head_htr_m25=ua0 * (10 - P.T_QUAL_C) - P_HEAD_ELEC)
    md.append("\n### Chassis and battery bay\n")
    rows = []
    for hname, h in H_EXT.items():
        for foam in (0, 5):
            ua, area = body_ua(h, foam)
            for tset in (0.0, 10.0):
                r = [hname, foam, f(ua, 2), tset]
                for ta in (P.T_OPERATING_C, P.T_QUAL_C):
                    need = ua * (tset - ta) - P_CHS_INTERNAL
                    r.append(f(max(need, 0)) + (" (> branch)" if need > P_CHS_HTR_LIMIT else ""))
                rows.append(r)
            if foam == 5 and h == 12.0:
                key["body_ua"] = ua
    md.append(table(["Air", "Foam liner (mm)", "UA (W/K)", "Bay set-point (C)", "Heater at -20 C (W)", "Heater at -25 C (W)"], rows))
    uab, _ = body_ua(12.0, 5)
    key.update(chs_htr_m20=max(uab * (0 - P.T_OPERATING_C) - P_CHS_INTERNAL, 0), chs_htr_m25=max(uab * (0 - P.T_QUAL_C) - P_CHS_INTERNAL, 0),
               chs_htr_m25_10=max(uab * (10 - P.T_QUAL_C) - P_CHS_INTERNAL, 0))
    tot = key["head_htr_m20"] + key["chs_htr_m20"]
    md.append(f"\nWith the 5 mm liner UA = {uab:.2f} W/K, time constant {C_BODY / uab / 60:.0f} min; the {P_CHS_INTERNAL:.0f} W dissipated inside the shell holds the bay {P_CHS_INTERNAL / uab:.0f} K above ambient by itself. "
              f"Heater needed to hold the pack bay at 0 C: {key['chs_htr_m20']:.0f} W at -20 C, {key['chs_htr_m25']:.0f} W at -25 C (at +10 C: {key['chs_htr_m25_10']:.0f} W at -25 C). "
              f"Sizing: one **20 W, 12 V polyimide pad** (90 x 70 mm) on the bay floor under the cassette with a bay NTC and an independent bimetal cut-out; without the liner the bay needs more than the 36 W branch in a draught. "
              f"Average heater power at -20 C in still air: head {key['head_htr_m20']:.0f} W + chassis {key['chs_htr_m20']:.0f} W = **{tot:.0f} W** against the {HTR_AVG_BUDGET:.0f} W planning budget"
              + (" -> the budget is exceeded: lower the head set-point to +5 C or raise the budget (flag to the power-budget owner)." if tot > HTR_AVG_BUDGET else "."))
    md.append("The pack's published discharge limit is -20 C: the pack must stay above ambient at the -25 C objective, which this model supports only while the electronics run (no cold-soak capability, consistent with RQ-029).")
    md.append("\n### Condensation management provisions (layout decisions)\n")
    for line in [
        "**Gasket lines**: one perimeter seal at the shell split (z = {:.1f}), O-ring/flat gaskets at every panel device, the saddle service cover, the tail-cap hatch and the head cover; closed-cell silicone foam rated -40 C.".format(P.BODY_SPLIT_Z),
        "**Breather**: one ePTFE membrane vent (M12 class) in the lower hull at the rear right quarter and one in the head rear wall beside the J2 port, so pressure equalises on the warm-room return without pumping moist air past the seals.",
        "**Desiccant**: 10 g replaceable pack with humidity indicator inside the saddle cover (visible when the cover is lifted) and a 5 g pack in the head chimney; change on indicator.",
        "**Drain paths**: the bay floor is the chassis plate; two 3 mm drain holes with duck-bill valves at the lowest points beside the caster bracket; the battery cassette sits on 2 mm ribs so melt water runs under it; the LiDAR pad and grip saddle slope outward; no pocket faces upward without a drain.",
        "**Head**: the window films are the cold face; the heater on the spreader keeps the optical stack above the film temperature so condensation forms outside, not between film and screen; the chimney is the low point and gets the membrane vent.",
        "**Warm-room return**: bag or cover the robot before entering the warm room, keep it closed until the bay NTC is within 5 K of the room (about 2 time constants = {:.0f} min for the body, {:.0f} min for the head), keep the heaters off and the electronics on during the soak; charge only above +5 C pack temperature (contract).".format(2 * C_BODY / uab / 60, 2 * tau),
        "**Connectors**: J1/J2 and the charge inlet face upward-forward / outward and are capped when unmated; receptacles are above the split line so pooled water cannot reach them.",
    ]:
        md.append(f"- {line}")
    return "\n".join(md), key
