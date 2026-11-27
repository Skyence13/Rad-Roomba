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
TP = P.POWER_C["thermal_policy"]               # contract draft8: bay_min_discharge_c -10, bay_precharge_c +5, head_setpoint_c +10
PAD_W = 20.0                                   # fitted bay pad, 12 V polyimide 90 x 70 mm (prototype BOM), UNVERIFIED part data
C_PACK = 1.65 * 1050 + 0.30 * 1300             # J/K: PSL-SC-12120 1.65 kg x c_p LiFePO4 cell about 1050 J/kg K (handbook class) + cassette/tunnel 0.30 kg polymer
G_PACK_BODY = 0.6                              # W/K pack node -> rest of body: 0.08 m2 pack surface x 6 W/m2K inside + rib contact -- ASSUMED, UNVERIFIED


def two_node_hold(ua, t_amb, t_pack=None, g=None):
    """Pad power (W) to hold the pack skin at t_pack with the pad on the pack, no self-heat: series pack -> body -> ambient."""
    t_pack = TP["bay_precharge_c"] if t_pack is None else t_pack
    g = G_PACK_BODY if g is None else g
    return (t_pack - t_amb) / (1 / g + 1 / ua)


def preheat_time(ua, p_w, g, t0=-25.0, t_end=None, dt=10.0, t_max=6 * 3600):
    """Minutes from a uniform t0 soak until the pack node reaches t_end (explicit Euler, two nodes); None if not reached in t_max."""
    t_end = TP["bay_precharge_c"] if t_end is None else t_end
    tp = tb = t0
    c_b = C_BODY - C_PACK
    t = 0.0
    while t < t_max:
        q_pb = g * (tp - tb)
        tp += dt * (p_w - q_pb) / C_PACK
        tb += dt * (q_pb - ua * (tb - t0)) / c_b
        t += dt
        if tp >= t_end:
            return t / 60
    return None


def head_reference():
    """The head heater figure is owned by the head engineer (real head geometry, same assumption set): quote
    mechanical/head/out/thermal_summary.json, never recompute it here."""
    import json
    f = P.REPO / "mechanical" / "head" / "out" / "thermal_summary.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = ["| Build | Ambient (C) | Air (W/m2K) | Jacket | Receiver boundary | Heater (W) |", "|---|---|---|---|---|---|"]
    for c in d.get("cases", []):
        if c.get("set_point_c") == TP["head_setpoint_c"] and c.get("jacket") and str(c.get("receiver_boundary", "")).startswith("body"):
            rows.append(f"| {c['build']} | {c['ambient_c']:.0f} | {c['h_ext_w_m2k']:.0f} | yes | {c['receiver_boundary']} | {c['heater_power_w']} |")
    return rows if len(rows) > 2 else None


def run():
    md, key = [], {}
    md.append("## 7. Heater sizing at -20 / -25 C (lumped, steady state) and condensation management\n")
    md.append("**Assumption set used by every thermal calculation of the project (IB-39, contract draft8 thermal policy):** ambient -20 C and -25 C; "
              f"head set-point +{TP['head_setpoint_c']:.0f} C at the SiPM carrier; bay: pack skin >= {TP['bay_min_discharge_c']:+.0f} C on pack power, pre-heat to {TP['bay_precharge_c']:+.0f} C on external power; electronics self-heat credited at the *typical* "
              f"budget only (head {HEAD_ELEC_TYP} W from `electronics/analysis/head_afe_budget.md`; chassis {P_CHS_TYP:.1f} W inside the shell from "
              "`electronics/analysis/power_budget.md`); external film coefficient 12 W/m2K (still air, primary) with the sensitivity at 25 W/m2K (moving air); "
              "the 3 mm head jacket is fitted below 0 C. The head heater figure belongs to the head engineer (computed on the real head geometry) and is quoted, not recomputed, here.\n")
    md.append(inputs_table([
        ("Ambient cases", f"{P.T_OPERATING_C:.0f} / {P.T_QUAL_C:.0f}", "C", "RQ-029"),
        ("Bay: pack-skin floor on pack power / pre-charge target", f"{TP['bay_min_discharge_c']:+.0f} / {TP['bay_precharge_c']:+.0f}", "C", "contract draft8 power.thermal_policy"),
        ("Bay pad fitted", PAD_W, "W", "12 V polyimide 90 x 70 mm, prototype BOM (UNVERIFIED part data)"),
        ("Pack + cassette heat capacity / pack-to-body coupling", f"{C_PACK:.0f} / {G_PACK_BODY}", "J/K / W/K", "handbook c_p / ASSUMED, UNVERIFIED"),
        ("External film coefficient, primary / sensitivity", f"{H_STILL:.0f} / {H_MOVING:.0f}", "W/m2 K", "ASSUMED, includes radiation"),
        ("Conductivity foam / printed polymer / air", f"{K_FOAM} / {K_PLASTIC} / {K_AIR}", "W/m K", "handbook"),
        ("Chassis self-heat inside the shell (typical)", f(P_CHS_TYP), "W", "power_budget.md: CM5 7.61 + logic 1.88 + relays 0.94 + protection 0.15 + 35 % of drive_cold 5.67"),
        ("Chassis heater branch limit", f(P_CHS_HTR_LIMIT, 0), "W", "contract CHS_HTR 3 A x 12 V"),
        ("Average heater budget (both zones)", HTR_AVG_BUDGET, "W", "contract average_budget_w.heaters_combined"),
        ("Body skin area", f((A_UP + A_LO) / 1e6 + 0.06, 3), "m2", "calculated from the Rev E section tables"),
        ("Heat capacity body", f"{C_BODY:.0f}", "J/K", "calculated from the mass budget, handbook c_p"),
    ]))
    md.append("\n### Chassis and battery bay: contract thermal policy (draft8 `power.thermal_policy`)\n")
    md.append(f"Policy: on pack power the bay heater holds the **pack skin >= {TP['bay_min_discharge_c']:+.0f} C** only (no regulation to +10 C while discharging); "
              f"on external power it **pre-heats the pack to {TP['bay_precharge_c']:+.0f} C** before charge is enabled. Self-heat credit: {P_CHS_TYP:.1f} W typical while running "
              f"on the pack; **0 W** during the pre-heat on external power (robot parked, conservative). Steady values use the one-node bay model (pack = bay mean, conservative "
              "for a pad bonded to the pack); the pre-heat time uses a two-node model (pack node with the pad | rest of the body) with the pack-to-body coupling ASSUMED.\n")
    rows = []
    for hname, h in (("still air (primary)", H_STILL), ("moving air 25 W/m2K (sensitivity)", H_MOVING)):
        for foam in (0, 5):
            ua, area = body_ua(h, foam)
            r = [hname, foam, f(ua, 2)]
            for ta in (P.T_OPERATING_C, P.T_QUAL_C):
                r.append(f(max(ua * (TP["bay_min_discharge_c"] - ta) - P_CHS_TYP, 0)))
            for ta in (P.T_OPERATING_C, P.T_QUAL_C):
                r.append(f(ua * (TP["bay_precharge_c"] - ta)) + f" ({f(two_node_hold(ua, ta), 1)})")
            rows.append(r)
    md.append(table(["Air", "Foam liner (mm)", "UA (W/K)", f"Discharge hold {TP['bay_min_discharge_c']:+.0f} C at -20 C (W)", "... at -25 C (W)",
                     f"Pre-heat hold {TP['bay_precharge_c']:+.0f} C at -20 C, whole bay (pack skin only) (W)", "... at -25 C (W)"], rows))
    uab, _ = body_ua(H_STILL, 5)
    uam, _ = body_ua(H_MOVING, 5)
    dis = {(hn, ta): max(u * (TP["bay_min_discharge_c"] - ta) - P_CHS_TYP, 0) for hn, u in (("still", uab), ("moving", uam)) for ta in (P.T_OPERATING_C, P.T_QUAL_C)}
    pre = {(hn, ta): u * (TP["bay_precharge_c"] - ta) for hn, u in (("still", uab), ("moving", uam)) for ta in (P.T_OPERATING_C, P.T_QUAL_C)}
    pre2 = {(hn, ta): two_node_hold(u, ta) for hn, u in (("still", uab), ("moving", uam)) for ta in (P.T_OPERATING_C, P.T_QUAL_C)}
    warm = {}
    for hn, u in (("still", uab), ("moving", uam)):
        for pw in (PAD_W, P_CHS_HTR_LIMIT):
            for g in (G_PACK_BODY, 2 * G_PACK_BODY):
                warm[(hn, pw, g)] = preheat_time(u, pw, g)
    key.update(body_ua=uab, body_ua_moving=uam, discharge_hold_w={f"{k[0]} {k[1]:.0f}C": v for k, v in dis.items()}, preheat_hold_bay_w={f"{k[0]} {k[1]:.0f}C": v for k, v in pre.items()},
               preheat_hold_packskin_w={f"{k[0]} {k[1]:.0f}C": v for k, v in pre2.items()}, preheat_time_min={f"{k[0]} {k[1]:.0f}W G{k[2]:.1f}": v for k, v in warm.items()},
               chs_htr_m20=dis[("still", P.T_OPERATING_C)], chs_htr_m25=dis[("still", P.T_QUAL_C)], chs_htr_m25_moving=dis[("moving", P.T_QUAL_C)],
               chs_internal_typ_w=P_CHS_TYP, set_point_c=T_SET_C, pad_w=PAD_W)
    def tm(v):
        return "not reached (steady limit below +5 C)" if v is None else f"{v:.0f} min"
    md.append(f"\nWith the 5 mm liner UA = {uab:.2f} W/K still / {uam:.2f} W/K moving air; time constant {C_BODY / uab / 60:.0f} min still air. "
              f"**Discharge hold (pack skin >= {TP['bay_min_discharge_c']:+.0f} C, pack power):** {dis[('still', -20.0)]:.1f} W at -20 C and {dis[('still', -25.0)]:.1f} W at -25 C in still air; "
              f"{dis[('moving', -20.0)]:.1f} / {dis[('moving', -25.0)]:.1f} W at 25 W/m2K -- the fitted {PAD_W:.0f} W pad **covers every discharge case**.")
    md.append(f"\n**Pre-heat hold (+{TP['bay_precharge_c']:.0f} C, external power, no self-heat):** whole-bay (one node) {pre[('still', -20.0)]:.1f} / {pre[('still', -25.0)]:.1f} W at -20 / -25 C still air, "
              f"{pre[('moving', -20.0)]:.1f} / {pre[('moving', -25.0)]:.1f} W at 25 W/m2K: **above the {PAD_W:.0f} W pad** in every case and above the {P_CHS_HTR_LIMIT:.0f} W branch in moving air at -25 C. "
              f"Pack skin only (two-node, pad on the pack, pack-to-body coupling {G_PACK_BODY} W/K ASSUMED): {pre2[('still', -20.0)]:.1f} / {pre2[('still', -25.0)]:.1f} W still air, "
              f"{pre2[('moving', -20.0)]:.1f} / {pre2[('moving', -25.0)]:.1f} W moving air -- the pad covers these. The policy is met at the pack skin, not as a warm bay; "
              "the cell core lags the skin NTC, so charge enable should add a soak (below).")
    md.append(f"\n**Pre-heat time, -25 C soak -> pack skin +{TP['bay_precharge_c']:.0f} C (two-node, calculated; pack C {C_PACK:.0f} J/K, rest of body {C_BODY - C_PACK:.0f} J/K):**\n")
    md.append(table(["Air", "Heater", f"Coupling pack-body {G_PACK_BODY} W/K", f"Coupling {2 * G_PACK_BODY} W/K"],
                    [(hn, f"{pw:.0f} W" + (" (fitted pad)" if pw == PAD_W else " (branch limit, larger pad)"), tm(warm[(hn, pw, G_PACK_BODY)]), tm(warm[(hn, pw, 2 * G_PACK_BODY)]))
                     for hn in ("still", "moving") for pw in (PAD_W, P_CHS_HTR_LIMIT)]))
    md.append(f"\nOne-node bound (whole body to +5 C with {PAD_W:.0f} W): steady limit {-25 + PAD_W / uab:+.1f} C still air, i.e. not reachable; the pad has to sit on the pack "
              "with the cassette as the insulation. Recommendation: charge enable at pack skin >= +5 C **and** a hold of at least 20 min after first reaching it (the cell core lags "
              f"the skin; pack-node time constant C/G = {C_PACK / G_PACK_BODY / 60:.0f} min at the assumed coupling); the pack-body coupling is the critical unknown -- measure it in the cold chamber (VT-0xx) before fixing the firmware threshold.")
    ref = head_reference()
    md.append("\n### Head (reference only)\n")
    if ref:
        md.append("Head heater power from `mechanical/head/out/thermal_summary.json` (head engineer, real head geometry, same assumption set), "
                  "**0.07 W/K-per-shoe receiver case only. These figures depend on the receiver thermal break (section 9, DEC-045 / IB-64):** "
                  "without it the channels run at plate temperature and the head's 'receiver metal at ambient' bound applies (43..66 W, above the 30 W fitted). "
                  "With the break as built the calculated body side is 0.11 W/K per shoe in still air (0.14 at 25 W/m2K), i.e. up to +1.8 / +3.3 W on the rows below (section 9).\n")
        md += ref
        key["head_htr"] = "see mechanical/head/out/thermal_summary.json"
    else:
        md.append("Head heater power: **pending head recalculation** (the head engineer recomputes it on the real head geometry with this assumption set; "
                  "the current `mechanical/head/out/head_report.md` still credits 5 W of electronics heat). This file carries no head figure of its own.")
        key["head_htr"] = "pending head recalculation"
    md.append(f"\nThe pack's published discharge limit is -20 C (UNVERIFIED recall): the {TP['bay_min_discharge_c']:+.0f} C discharge floor keeps 10 K of margin; at the -25 C objective the bay stays above it only while the electronics run or the pad is on (no cold-soak capability, consistent with RQ-029).")
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
