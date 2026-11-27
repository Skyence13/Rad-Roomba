"""Receiver thermal break (DEC-045, IB-64): conductance, datum-C tolerance stack, clamp preload / G10 creep, mount stiffness and
thread engagement.  Every result is evidence class `calculated`; material data are handbook-class values, UNVERIFIED for the
purchased stock.

Geometry (params.RECEIVER_BREAK, built in mechanical/prototype_x1c/rrx/structure.py):
plate underside z 33 | 4.0 mm ground G10 shim strips under the two ears | ears z 21.5..29.0 | land pins centre z 14, top = datum C z 16.
The two roof bridges at the land stations rise to z 33 inside 1.5 mm pockets milled in the plate underside (1.5 mm air gap); between
the stations the roof is open.  Screws M4 x 18 A2-70 with a DIN 6796 conical spring washer, an ISO 7089 washer and a G10 top-hat
bushing (flange on the plate top, sleeve in a 6.0 mm plate hole).  Location: two lower 4 m6 pins pressed into the ear engage reamed
holes in the shim only; two upper 4 m6 pins pressed into the plate pass through the shim and end in a 6.5 x 1.5 relief in the ear.
"""
from __future__ import annotations

import math

from .. import params as P
from . import f, inputs_table, table

RB, RC = P.RECEIVER_BREAK, P.RECEIVER
K_AIR, K_A2, K_STEEL, K_AL = 0.026, 15.0, 45.0, 167.0          # W/m K (air at ~0 C, A2 stainless, carbon steel pin, 6061-T6) -- handbook
E_A2, E_AL = 193000.0, 68900.0                                   # MPa
G10_FLATWISE_STRENGTH = 415.0     # MPa, flatwise compressive strength, NEMA LI-1 G-10 class value -- handbook, UNVERIFIED
MU_G10_AL = 0.20                  # dry static friction G10 on machined aluminium -- ASSUMED (lower-bound class value), UNVERIFIED
TAU_6061 = 207.0                  # MPa, shear strength 6061-T6 -- handbook
A2_70_RM, AS_M4, P_M4, D_M4 = 700.0, 8.78, 0.7, 4.0              # MPa, mm2, mm, mm (ISO 3506 / ISO 898 stress area)
LATCH_PRELOAD = (100.0, 200.0)    # N, mechanical/prototype_x1c report section 5 (draw latch on the head keeper, into datum A)
G_HEAD_SHOE_INTERFACE = 0.5       # W/K per shoe, shoe -> channel through the pins, pads and x-stop (metal contacts) -- ASSUMED order of magnitude
CHANNEL_EXT_AREA = 0.0045         # m2 per channel exposed below the plate (sides, underside, ends, ear undersides; from the model envelope)
H_EXT = {"still air": 12.0, "moving air": 25.0}                  # W/m2 K, IB-39 assumption set
HEAD_SUMMARY = P.REPO / "mechanical" / "head" / "out" / "thermal_summary.json"


def shim_area_mm2():
    """Shim strip area per channel (mm2): inboard strip x 8..56, outboard strip x 8..24, |dy| 12.5..21, minus the screw and pin holes."""
    w = RB["shim_dy"][1] - RB["shim_dy"][0]
    gross = (56.0 - 8.0) * w + (24.0 - 8.0) * w
    holes = 3 * math.pi * 2.25 ** 2 + 4 * math.pi * 2.0 ** 2
    return gross, gross - holes


def bridge_area_mm2():
    """Roof-bridge tops under the plate pockets (mm2): rear bridge x 2..13, front bridge x 56..62 (the plate ends at x 62)."""
    (a0, a1), (b0, _) = RB["bridge_x"]
    return (a1 - a0) * RC["channel_width"] + (RC["front_beam"][1] - b0) * RC["channel_width"]


def conductance():
    """Channel -> plate conductance per channel (W/K), by path."""
    t = RB["shim_t"] / 1000
    k = RB["k_shim_w_mk"]
    _, a_net = shim_area_mm2()
    g_shim = k * a_net / 1e6 / t
    b = RB["bushing"]
    # per screw: plate -> (G10 flange under the washer || G10 sleeve wall, half contact) -> A2 screw -> ear thread
    a_fl = math.pi / 4 * (9.0 ** 2 - b["sleeve_od"] ** 2) / 1e6                    # washer OD 9 over the flange, outside the sleeve bore
    g_fl = k * a_fl / (b["flange_t"] / 1000)
    a_sl = 0.5 * math.pi * b["sleeve_od"] * b["sleeve_len"] / 1e6
    g_sl = k * a_sl / ((b["sleeve_od"] - b["id"]) / 2 / 1000)
    g_screw_metal = K_A2 * AS_M4 / 1e6 / ((b["flange_t"] + 4.0 + RB["shim_t"]) / 1000)
    g_per_screw = 1 / (1 / (g_fl + g_sl) + 1 / g_screw_metal)
    g_screws = 3 * g_per_screw
    # pins: the metal pin ends face the other part across an air gap; the G10 fringe round each pin end is counted as a 1 mm band
    a_pin = math.pi * 2.0 ** 2 / 1e6
    g_lower = 2 * (K_AIR * a_pin / 0.0015 + k * (math.pi * 4.0 * 1.0 / 1e6) / 0.0015)
    rd, rh = RB["pin_relief"]
    g_upper = 2 * (K_AIR * (a_pin + math.pi * 4.0 * 1.0 / 1e6) / ((rd - 4.0) / 2 / 1000) + k * (math.pi * 4.0 * 1.0 / 1e6) / 0.0015)
    g_bridge = K_AIR * bridge_area_mm2() / 1e6 / (RB["plate_pocket_depth"] / 1000)
    wall = 2 * 3.5 * (RB["bridge_x"][1][0] - RB["bridge_x"][0][1])             # wall tops between the stations, 4 mm below the plate
    g_walls = K_AIR * wall / 1e6 / (RB["shim_t"] / 1000)
    g_rad = 4 * 5.67e-8 * 0.1 * 263.0 ** 3 * (a_net + bridge_area_mm2()) / 1e6   # machined aluminium, e about 0.1 (handbook)
    paths = {"G10 shim strips": g_shim, "3 screws through G10 top-hat bushings": g_screws, "2 lower pins (air + G10 fringe)": g_lower,
             "2 upper pins (ear relief air + G10 fringe)": g_upper, "roof bridges under the plate pockets (1.5 mm air)": g_bridge,
             "wall tops between the stations (4 mm air)": g_walls, "radiation across the gaps": g_rad}
    paths["total"] = sum(paths.values())
    detail = {"shim_area_net_mm2": a_net, "per_screw": g_per_screw, "flange": g_fl, "sleeve": g_sl, "screw_metal": g_screw_metal}
    return paths, detail


def conductance_before():
    """The as-built metal-to-metal joint (aba8818): order of magnitude, contact conductance 3000 W/m2K over the ear + spine face."""
    return 3000.0 * (640.0 + 63.7 * 24.0) / 1e6


def body_side_per_shoe(g_plate, h, boot=False):
    """Receiver metal -> ambient sinks per shoe, plate taken at ambient (conservative, the head model's convention): the shoe-to-channel
    metal contacts in series with (plate path || the channel's own exposed surface).  boot: 3 mm closed-cell foam over the exposed
    channel surface (option, not built)."""
    u = 1 / (1 / h + (0.003 / 0.035 if boot else 0.0))
    g_conv = u * CHANNEL_EXT_AREA
    sinks = g_plate + g_conv
    return 1 / (1 / G_HEAD_SHOE_INTERFACE + 1 / sinks), g_conv


def head_receiver_side():
    """Head interior -> receiver metal (W/K, both shoes) back-calculated from the head engineer's two published cases at -25 C,
    +10 C, still air, jacket: UA(bound) - UA(0.07/shoe) = G - G B / (G + B), B = 0.14."""
    import json
    try:
        d = json.loads(HEAD_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    pick = lambda rb: next((c for c in d.get("cases", []) if c["build"] == "prototype" and c["ambient_c"] == -25.0 and c["set_point_c"] == 10.0
                             and c["h_ext_w_m2k"] == 12.0 and c["jacket"] and c["receiver_boundary"].startswith(rb)), None)
    base, bound = pick("body"), pick("BOUND")
    if not (base and bound):
        return None, None
    du, b = bound["ua_w_per_k"] - base["ua_w_per_k"], 2 * 0.07
    g = (du + math.sqrt(du * du + 4 * du * b)) / 2
    return g, base


def head_delta_w(g_head, b_total, t_set=10.0, t_amb=-25.0):
    """Extra head heater power (W) against the 0.07 W/K-per-shoe case for a body side of b_total (W/K, both shoes)."""
    ua = lambda b: g_head * b / (g_head + b)
    return (ua(b_total) - ua(0.14)) * (t_set - t_amb)


# ---------------------------------------------------------------------------------------------------------- tolerance stack
def tolerance_stack():
    """Body-side contribution to the datum-C height (plate underside -> land-pin top), worst case and RSS, before and after."""
    before = [("Ear/top face to land-pin bore centre, one machining set-up (19.00)", 0.03, "drawing +-0.03"),
              ("Land pin 4 m6 radius (+0.004..+0.012 on d)", 0.004, "ISO 8734"),
              ("Plate underside flatness over the ear footprint", 0.02, "4 mm 6061, local 0.04 over 60 mm"),
              ("Joint seating (metal-metal, two faces)", 0.003, "embedding, VDI 2230 class")]
    e_shim = RB["shim_t"] * (P.RECEIVER_BREAK["screw_preload_n"] * 3 / shim_area_mm2()[1]) / RB["e_shim_flatwise_mpa"]
    cte = (55e-6 - 23.6e-6) * RB["shim_t"] * 45.0        # G10 through-thickness CTE about 55e-6/K (handbook, UNVERIFIED) vs Al, +20 -> -25 C
    after = [("Ear top face to land-pin bore centre, one set-up (15.00)", 0.03, "drawing +-0.03"),
             ("Land pin 4 m6 radius", 0.004, "ISO 8734"),
             ("Plate underside flatness over the ear footprint", 0.02, "as before"),
             (f"G10 shim thickness {RB['shim_t']:.2f} (pair ground together)", RB["shim_t_tol"], "drawing; mismatch L/R <= 0.01"),
             ("G10 shim flatness / parallelism", RB["shim_flatness"] / 2, "drawing 0.01"),
             (f"Shim compression under the clamp (nominal {e_shim * 1000:.1f} um, varies +-30 %)", 0.3 * e_shim, "E flatwise ASSUMED"),
             ("Shim creep after preload (10 years, RT)", (RB["shim_creep_factor"] - 1) * e_shim, "creep factor ASSUMED"),
             ("Shim thermal contraction vs aluminium, +20 -> -25 C", cte, "CTE handbook, UNVERIFIED"),
             ("Joint seating (four faces incl. G10)", 0.006, "embedding, VDI 2230 class")]
    res = {}
    for tag, rows in (("before", before), ("after", after)):
        tol = [r[1] for r in rows]
        res[tag] = {"rows": rows, "worst": sum(tol), "rss": math.sqrt(sum(t * t for t in tol))}
    # amplification to the front outer window corner: heave 1:1 + pitch from a front/rear difference over the land base.  Front/rear
    # difference terms: flatness/parallelism, plate flatness (half each); lever from the land midpoint to the corner over e.
    e = RC["land_x"][1] - RC["land_x"][0]
    x_corner = P.ROW_X + P.ACTIVE_X / 2
    lever = (x_corner - sum(RC["land_x"]) / 2) / e
    for tag in res:
        par = [r[1] for r in res[tag]["rows"] if "flatness" in r[0]]
        res[tag]["corner_worst"] = res[tag]["worst"] + lever * sum(par)
        res[tag]["corner_rss"] = math.sqrt(res[tag]["rss"] ** 2 + (lever * math.sqrt(sum(p * p for p in par))) ** 2)
    res["lever"] = lever
    return res


# ---------------------------------------------------------------------------------------------------------- preload / creep
def preload():
    b = RB["bushing"]
    F = RB["screw_preload_n"]
    a_wash = math.pi / 4 * (9.0 ** 2 - b["id"] ** 2)
    a_fl_plate = math.pi / 4 * (b["flange_od"] ** 2 - b["sleeve_od"] ** 2)
    _, a_shim = shim_area_mm2()
    p_shim_avg = 3 * F / a_shim
    p_shim_local = F / (math.pi / 4 * (12.0 ** 2 - 4.5 ** 2))       # under the screw, 12 mm pressure cone
    E = RB["e_shim_flatwise_mpa"]
    el_shim, el_fl = p_shim_local / E * RB["shim_t"], (F / a_fl_plate) / E * b["flange_t"]
    creep = (RB["shim_creep_factor"] - 1) * (el_shim + el_fl)
    embed = 0.011                                                    # mm: thread 3 + head 3 + 5 interfaces 1 um each (VDI 2230 class, ASSUMED)
    grip_unloaded = 1.3 + 0.8 + b["flange_t"] + 4.0 + RB["shim_t"]
    l_eff = grip_unloaded + 0.4 * D_M4 + 0.5 * D_M4
    k_b = E_A2 * AS_M4 / l_eff
    a_cone = math.pi / 4 * (12.0 ** 2 - 4.5 ** 2)
    k_m = 1 / (b["flange_t"] / (E * a_wash) + 4.0 / (E_AL * a_cone) + RB["shim_t"] / (E * a_cone) + 3.5 / (E_AL * a_cone))
    k_joint = 1 / (1 / k_b + 1 / k_m)
    k_disc = 2000.0 / 0.3                                            # DIN 6796 4: about 2 kN at flat over h0 = 0.3 mm (UNVERIFIED, linearised)
    k_with_disc = 1 / (1 / k_joint + 1 / k_disc)
    loss_rigid, loss_disc = k_joint * (creep + embed), k_with_disc * (creep + embed)
    slip_cap = MU_G10_AL * 3 * (F - loss_disc)
    torque = 0.2 * F * D_M4 / 1000
    return {"F": F, "torque": torque, "p_washer": F / a_wash, "p_flange_plate": F / a_fl_plate, "p_shim_avg": p_shim_avg, "p_shim_local": p_shim_local,
            "util_max": max(F / a_wash, F / a_fl_plate, p_shim_local) / G10_FLATWISE_STRENGTH, "creep_mm": creep, "embed_mm": embed,
            "k_b": k_b, "k_m": k_m, "k_joint": k_joint, "k_disc": k_disc, "loss_rigid": loss_rigid, "loss_disc": loss_disc,
            "residual": F - loss_disc, "slip_capacity_per_channel": slip_cap, "latch_per_channel": LATCH_PRELOAD[1] / 2,
            "slip_margin": slip_cap / (LATCH_PRELOAD[1] / 2), "grip_unloaded": grip_unloaded}


def thread():
    b = RB["bushing"]
    disc_loaded = 1.0 + 0.3 * (1 - 1500.0 / 2000.0)                 # disc height at the preload (linearised)
    grip = disc_loaded + 0.8 + b["flange_t"] + 4.0 + RB["shim_t"]
    le = 18.0 - grip
    a_strip = 0.6 * math.pi * D_M4 * le                              # internal-thread shear area, conservative 0.6 pi d Le
    f_strip = a_strip * TAU_6061
    f_bolt = AS_M4 * A2_70_RM
    return {"screw": RB["screw"], "grip": grip, "engagement": le, "engagement_d": le / D_M4, "ear_t": RB["ear_t"], "tip_inside_ear": RB["ear_t"] - le,
            "strip_n": f_strip, "bolt_n": f_bolt, "ratio": f_strip / f_bolt, "before": {"screw": "M4 x 10", "engagement": 6.0, "engagement_d": 1.5}}


# ---------------------------------------------------------------------------------------------------------- stiffness
def stiffness():
    """Series springs added per land: shim compression (each land carries into half the shim) and, for the up-loaded rear land, the roof
    bridge in bending (fixed-fixed beam, centre load, +10 % shear; the end wall is ignored, conservative)."""
    from . import structure as S
    _, a_shim = shim_area_mm2()
    k_shim_land = RB["e_shim_flatwise_mpa"] * (a_shim / 2) / RB["shim_t"]
    (a0, a1), _ = RB["bridge_x"]
    span, t_br = RC["shoe_width"] + 2 * RC["channel_clear"], RB["bridge_top_z"] - (RC["shoe_z"][1] + RC["channel_clear"])
    I = (a1 - a0) * t_br ** 3 / 12
    k_bridge = 192 * E_AL * I / span ** 3 / 1.1
    out = {"k_shim_land": k_shim_land, "k_bridge": k_bridge, "bridge_t": t_br, "builds": {}}
    for build in ("prototype PA-CF (dry)", "production 6061"):
        mat, t, mass, k_c, ef = S.BUILDS[build]
        k_dn = 1 / (1 / k_c + 1 / k_shim_land)
        k_up = 1 / (1 / k_c + 1 / k_shim_land + 1 / k_bridge)
        k_eff = (k_dn + k_up) / 2
        d0, s0 = S.evaluate("C", build)
        S.BUILDS["_tmp"] = (mat, t, mass, k_eff, ef)
        d1, s1 = S.evaluate("C", "_tmp")
        del S.BUILDS["_tmp"]
        key = "20 N at front outer corner, cover screwed as shear panel (closed cell)"
        out["builds"][build] = {"k_c": k_c, "k_eff": k_eff, "corner0": d0[key]["front outer corner"], "corner1": d1[key]["front outer corner"],
                                "f1_0": s0["f1"], "f1_1": s1["f1"], "pitch0": s0["f"]["pitch"], "pitch1": s1["f"]["pitch"]}
    return out


def run():
    md, key = [], {}
    paths, det = conductance()
    g = paths["total"]
    md.append("## 9. Receiver thermal break (DEC-045 / IB-64, calculated)\n")
    md.append("Each receiver channel hangs under the chassis plate on a ground G10 shim; no metal part crosses the shim. Datum C (z 16.0) and the land pins "
              "(centre z 14.0) are unchanged; the ears drop by the shim thickness and the two roof bridges at the land stations stand up into 1.5 mm pockets "
              "in the plate underside. Built in `mechanical/prototype_x1c` (RRX-F02L/R channels, RRX-F05L/R shims) and carried unchanged into `mechanical/production`.\n")
    md.append(inputs_table([
        ("Shim", f"{RB['shim_material']}, {RB['shim_t']:.2f} +-{RB['shim_t_tol']:.2f} mm, flatness {RB['shim_flatness']}", "-", "params.RECEIVER_BREAK"),
        ("G10 conductivity through the laminate", RB["k_shim_w_mk"], "W/m K", "handbook class value for G-10/FR4 (0.25..0.30, upper end used) -- UNVERIFIED for the purchased sheet"),
        ("G10 flatwise modulus / strength", f"{RB['e_shim_flatwise_mpa']:.0f} / {G10_FLATWISE_STRENGTH:.0f}", "MPa", "handbook class (NEMA LI-1 G-10) -- ASSUMED, UNVERIFIED"),
        ("Air / A2 / pin steel conductivity", f"{K_AIR} / {K_A2} / {K_STEEL}", "W/m K", "handbook"),
        ("Screw clamp", f"{RB['screw']}, {RB['screw_preload_n']:.0f} N preload", "-", f"torque {0.2 * RB['screw_preload_n'] * 4 / 1000:.1f} N m at K = 0.2 (ASSUMED nut factor)"),
        ("Latch preload into datum A", f"{LATCH_PRELOAD[0]:.0f}..{LATCH_PRELOAD[1]:.0f}", "N", "prototype report section 5"),
    ]))
    md.append("\n**Conductance channel -> plate, per channel (calculated):**\n")
    md.append(table(["Path", "W/K"], [(k, f(v, 4)) for k, v in paths.items()]))
    md.append(f"\nResult: **{g:.3f} W/K per channel** against the {RB['target_w_per_k']:.2f} W/K target (shim net area {det['shim_area_net_mm2']:.0f} mm2; one screw "
              f"{det['per_screw']:.4f} W/K). The joint it replaces (metal to metal, about 2200 mm2 at an assumed 3000 W/m2K contact conductance) is about "
              f"{conductance_before():.1f} W/K, i.e. the channel ran at plate temperature.")
    gh, base = head_receiver_side()
    rows, key_rows = [], {}
    for hn, h in H_EXT.items():
        for boot in (False, True):
            bs, gconv = body_side_per_shoe(g, h, boot)
            dw = head_delta_w(gh, 2 * bs) if gh else None
            rows.append((hn, "3 mm foam boot (option)" if boot else "bare (as built)", f(gconv, 3), f(bs, 3), f(dw, 1) if dw is not None else "n/a"))
            key_rows[f"{hn}{' boot' if boot else ''}"] = {"per_shoe": bs, "head_delta_w": dw}
    md.append("\n**What the head sees (calculated, plate taken at ambient as in the head model).** The break removes the plate as a sink, but the aluminium channel "
              f"itself hangs in the outside air under the plate ({CHANNEL_EXT_AREA * 1e4:.0f} cm2 exposed), and the shoe reaches it through metal contacts "
              f"(taken as {G_HEAD_SHOE_INTERFACE} W/K per shoe, ASSUMED). Head interior -> receiver metal back-calculated from the head engineer's two published cases: "
              + (f"{gh:.2f} W/K for both shoes." if gh else "head summary not found.") + "\n")
    md.append(table(["Air", "Channel exterior", "Channel convection (W/K)", "Body side per shoe (W/K)", "Head heater vs the 0.07 W/K case at -25 C, +10 C (W)"], rows))
    md.append("\nReading: with the break the body side per shoe is close to the head's 0.07 W/K assumption and the head heater moves by a few watts at most, "
              "against 43..66 W without it. The head rows quoted in section 7 are therefore valid **only with this break fitted**; the residual is the channel's own "
              "exposed surface, which a 3 mm closed-cell foam boot over the channel sides would halve (option, not built: it would cover the wipe-down surfaces).")
    tol = tolerance_stack()
    md.append("\n**Datum-C height, body-side tolerance stack (plate underside -> land-pin top, calculated):**\n")
    for tag in ("before", "after"):
        md.append("\n*" + {"before": "Before (metal-to-metal joint, commit aba8818)", "after": "After (G10 thermal break)"}[tag] + ":*\n")
        md.append(table(["Contributor", "+- mm", "Basis"], [(a, f(b, 3), c) for a, b, c in tol[tag]["rows"]]))
        md.append(f"\nTotal at datum C: +-{tol[tag]['worst']:.3f} worst case / +-{tol[tag]['rss']:.3f} RSS; at the front outer window corner (front/rear flatness terms "
                  f"x {tol['lever']:.2f} lever): +-{tol[tag]['corner_worst']:.3f} / +-{tol[tag]['corner_rss']:.3f}.")
    md.append(f"\nEffect on the gap budget (section 6): the body-side datum-C term at the front outer corner grows from +-{tol['before']['corner_worst']:.2f} to "
              f"+-{tol['after']['corner_worst']:.2f} mm worst case; it is carried as its own row in the static band (it was not listed before). "
              "The head's own contribution (datum C to film plane) is unchanged.")
    pl = preload()
    md.append("\n**Clamp preload, latch preload and G10 creep (calculated):**\n")
    md.append(table(["Quantity", "Value"], [
        ("Preload per screw / torque", f"{pl['F']:.0f} N / {pl['torque']:.1f} N m (dry, K 0.2 ASSUMED)"),
        ("Bearing pressure: washer on flange / flange on plate / shim under the screw / shim mean", f"{pl['p_washer']:.0f} / {pl['p_flange_plate']:.0f} / {pl['p_shim_local']:.0f} / {pl['p_shim_avg']:.0f} MPa"),
        ("Utilisation of the G10 flatwise strength (max)", f"{pl['util_max'] * 100:.0f} %"),
        ("Creep (shim + flange, factor ASSUMED) + embedding", f"{pl['creep_mm'] * 1000:.1f} + {pl['embed_mm'] * 1000:.0f} um"),
        ("Bolt / member / joint stiffness", f"{pl['k_b'] / 1000:.0f} / {pl['k_m'] / 1000:.0f} / {pl['k_joint'] / 1000:.0f} kN/mm"),
        ("Preload loss without / with the DIN 6796 spring washer", f"{pl['loss_rigid']:.0f} N ({pl['loss_rigid'] / pl['F'] * 100:.0f} %) / {pl['loss_disc']:.0f} N ({pl['loss_disc'] / pl['F'] * 100:.0f} %)"),
        ("Friction capacity per channel (mu 0.20 ASSUMED) vs latch preload per channel", f"{pl['slip_capacity_per_channel']:.0f} N vs {pl['latch_per_channel']:.0f} N (margin {pl['slip_margin']:.1f}); the pins locate, they are not the shear path"),
    ]))
    md.append("\nThe latch preload (100..200 N into datum A) loads the shim joint in shear only; the head weight and a 20 N corner load add less than 60 N of normal "
              "force per land against 4.5 kN of clamp, so the shim never unloads. Without the conical spring washer the joint would lose about half its preload to creep "
              "and embedding; with it the loss is a few per cent. Re-torque check at the first service (assembly note).")
    th = thread()
    md.append("\n**Thread engagement (calculated):** " + f"{th['screw']} through spring washer, washer, bushing flange, 4 mm plate and {RB['shim_t']:.0f} mm shim: grip "
              f"{th['grip']:.2f} mm, engagement {th['engagement']:.2f} mm = {th['engagement_d']:.2f} d in the {th['ear_t']:.1f} mm ear (tip {th['tip_inside_ear']:.2f} mm "
              f"inside the ear); 6061-T6 internal-thread strip strength {th['strip_n'] / 1000:.1f} kN against the A2-70 screw {th['bolt_n'] / 1000:.1f} kN (ratio "
              f"{th['ratio']:.1f}, the screw fails first). Before: M4 x 10, 6.0 mm = 1.5 d in a 6 mm ear.")
    st = stiffness()
    md.append(f"\n**Mount stiffness (calculated):** shim per land {st['k_shim_land'] / 1000:.0f} kN/mm, roof bridge ({st['bridge_t']:.1f} mm, fixed-fixed) "
              f"{st['k_bridge'] / 1000:.0f} kN/mm in series with the up-loaded rear land.\n")
    md.append(table(["Head build", "k per land before / after (N/mm)", "20 N front corner deflection before / after (mm)", "First mode before / after (Hz)", "Change"],
                    [(b, f"{v['k_c']:.0f} / {v['k_eff']:.0f}", f"{v['corner0']:.3f} / {v['corner1']:.3f}", f"{v['f1_0']:.0f} / {v['f1_1']:.0f}",
                      f"{(v['corner1'] / v['corner0'] - 1) * 100:+.1f} % / {(v['f1_1'] / v['f1_0'] - 1) * 100:+.1f} %") for b, v in st["builds"].items()]))
    md.append("\nNot material: the shim is three orders stiffer than a land; the bridge costs a few per cent on the aluminium build and nothing visible on the printed one. "
              "The 20 N corner target (<= 1.0 mm) and the mode ranking are unchanged.")
    key.update(g_per_channel=g, paths=paths, target=RB["target_w_per_k"], body_side=key_rows, head_g=gh, tolerance={k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in tol.items() if k != "lever"},
               preload=pl, thread=th, stiffness=st)
    return "\n".join(md), key
