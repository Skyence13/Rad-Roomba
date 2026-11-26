#!/usr/bin/env python3
"""Rad Roomba power budget -- regenerates electronics/analysis/power_budget.md.

Run:  python3 electronics/analysis/power_budget.py
Every number is tagged: [D] datasheet (source named), [C] calculated here, [A] assumed design input,
[U] UNVERIFIED (could not be confirmed from a primary source in this session), [M] from another team's model.
Nothing here is measured.  Not a certified safety calculation.
"""
import os

# ----------------------------------------------------------------------------- inputs
V_NOM, V_MIN, V_FULL = 12.8, 10.0, 14.4          # [D] contract power.battery; 14.4 V = 3.60 V/cell charge
ETA_5V, ETA_AUX = 0.92, 0.85                     # [A] LM61460 12->5.12 V at 1.5-3 A (datasheet curves ~93 %), small bucks
PACKS = {                                        # name: (Ah, mass kg, Icont A, source tag)
    "8 Ah (0.3 trial value, no catalogue pack)": (8.0, None, None, "[A]"),
    "9 Ah Power-Sonic PSL-SC-1290":              (9.0, 1.00, 15.0, "[D] mass/dims mechanical parts.yaml; 15 A Power-Sonic technical document (search snippet) [U] BMS trip levels"),
    "12 Ah Power-Sonic PSL-SC-12120":            (12.0, 1.65, 15.0, "[D] psl-sc-12120.pdf: 15 A cont., 25 A/10 s, 30 A/3 s, SC 60 A/0.5 ms"),
}
AVAIL = {"+20 C": 1.00, "-20 C": 0.80, "-25 C": 0.75}   # [A] deliverable fraction of nameplate (0.3 worksheet used 0.80 cold)
RESERVE = 0.20                                          # [A] end-of-run reserve (0.3 worksheet)

# Loads at their own rail, W.  (typ, max).  eta = conversion efficiency from the pack terminals.
L = {
    #                     typ    max   eta      basis
    "cm5_idle":          (3.5,   3.5, ETA_5V,  "[U] CM5 + carrier idle; Raspberry Pi publishes no guaranteed figure"),
    "cm5_run":           (7.0,  12.0, ETA_5V,  "[A] ROS 2 survey load 7 W typ; 12 W = CM5 at full load plus 1 W USB-Ethernet adapter"),
    "lidar":             (3.5,   6.0, 0.99,    "[U] LakiBeam 1L typ ~3-4 W; 6.0 W is the 0.3 planning value used as max"),
    "logic":             (1.6,   2.2, ETA_AUX, "[C] MCU 0.15, 11 ToF 0.75, IMU/mux/expanders 0.1, RS-485+bridge 0.25, panel LEDs 0.2, BUS_5V 0.15"),
    "relays_armed":      (0.94,  1.25,1.00,    "[D] Omron G2RL-2 12 V 400 mW x2, G6S-2 140 mW; max at 14.4 V"),
    "protection_quies":  (0.15,  0.2, 1.00,    "[C] eFuses, monitors, dividers, charger standby"),
    "head_elec":         (5.0,  10.0, 0.98,    "[D] contract head_allocation_w: target 5, max 10"),
    "drive_warm":        (2.6,  15.0, 0.97,    "[C] see drive model below; 15 W = 0.3 planning value kept as max"),
    "drive_cold":        (5.5,  15.0, 0.97,    "[A] cold grease doubles friction current"),
    "drive_turn":        (4.0,  15.0, 0.97,    "[C] pivot at 0.30 rad/s with scrub"),
    "htr_head_-20":      (16.0, 30.0, 0.98,    "[M] mechanical lumped thermal model (CCR-10): head +10 C set-point"),
    "htr_bay_-20":       (6.0,  20.0, 0.98,    "[M] same model; 20 W = fitted element at 12 V"),
    "htr_total_-25":     (30.0, 50.0, 0.98,    "[M] same model, -25 C"),
}

def P(name, which=0):
    typ, mx, eta, _ = L[name]
    return (typ, mx)[which] / eta

def state(items, which=0):
    return sum(P(n, which) for n in items)

BASE_RUN = ["cm5_run", "lidar", "logic", "protection_quies", "head_elec"]
STATES = [
    # name, items (typ), note
    ("Idle / STANDBY (RUN selected, not armed)", ["cm5_idle", "lidar", "logic", "protection_quies", "head_elec"], "+20 C"),
    ("Survey 0.10 m/s, +20 C",                   BASE_RUN + ["relays_armed", "drive_warm"], "+20 C"),
    ("Turn (pivot), +20 C",                      BASE_RUN + ["relays_armed", "drive_turn"], "+20 C"),
    ("Stationary recount / scaler count, +20 C", BASE_RUN + ["relays_armed"], "+20 C"),
    ("Survey 0.10 m/s, -20 C, heaters",          BASE_RUN + ["relays_armed", "drive_cold", "htr_head_-20", "htr_bay_-20"], "-20 C"),
    ("Stationary count, -20 C, heaters",         BASE_RUN + ["relays_armed", "htr_head_-20", "htr_bay_-20"], "-20 C"),
    ("Survey 0.10 m/s, -25 C, heaters",          BASE_RUN + ["relays_armed", "drive_cold", "htr_total_-25"], "-25 C"),
    ("LAB (head on 2 m extension, +20 C)",       ["cm5_run", "logic", "protection_quies", "head_elec"], "+20 C"),
]

def step_and_count(move_state, count_state, frac_count):
    return frac_count * count_state + (1 - frac_count) * move_state

# ----------------------------------------------------------------------------- drive model (Pololu #2828)
WHEEL_D = 0.104                      # [D] contract
RPM_NL, I_NL, I_STALL, V_RATED = 67.0, 0.2, 5.5, 12.0   # [D] Pololu #2828 specs page
T_STALL = 49 * 9.80665 / 100         # [D] 49 kg-cm -> N m (extrapolated by Pololu)
R_M = V_RATED / I_STALL              # [C] 2.18 ohm terminal resistance incl. brushes (from the extrapolated stall point)
v_nl = RPM_NL / 60 * 3.14159265 * WHEEL_D
KE = (V_RATED - I_NL * R_M) / v_nl   # [C] back-EMF per m/s of ground speed
KT_OUT = T_STALL / (I_STALL - I_NL)  # [C] output torque per amp (gearbox losses folded in)
def drive_w(v, f_roll_n, i_fric):
    """Electrical input of both motors at ground speed v with total rolling force f_roll_n."""
    i = i_fric + (f_roll_n / 2) * (WHEEL_D / 2) / KT_OUT
    u = KE * v + i * R_M
    return 2 * u * i, i, u

# ----------------------------------------------------------------------------- peak current allocation
R_HTR_HEAD = 12.0 ** 2 / 30.0        # [D] contract: 30 W at 12 V -> 4.8 ohm
R_HTR_BAY = 12.0 ** 2 / 20.0         # [A] 20 W / 12 V element -> 7.2 ohm
I_TRIP = 3.0 / (2490 * 450e-6)       # [C] DRV8874 ITRIP = VREF/(RIPROPI*AIPROPI); [D] AIPROPI 450 uA/A
def peak(vbus):
    rows = [
        ("V5_CM5 (12 W at the rail)",        12.0 / ETA_5V / vbus, 5.0 * 5.12 / ETA_5V / vbus, "eFuse 5.0 A on the 5 V side"),
        ("V12_LIDAR (6 W)",                  6.0 / vbus, 1.5, "eFuse 1.5 A"),
        ("V3V3_CHS + V5_AUX (2.2 W)",        2.2 / ETA_AUX / vbus, 1.0 * 3.3 / ETA_AUX / vbus + 0.6 * 5 / ETA_AUX / vbus, "buck current limits"),
        ("Relay coils",                      0.094 * vbus / 12.0, 0.15, "polyfuse 0.20 A hold"),
        ("HEAD_PWR (10 W)",                  10.0 / vbus, 1.5, "eFuse 1.5 A"),
        ("HEAD_HTR (4.8 ohm element)",       vbus / (R_HTR_HEAD + 0.18), 4.05, "eFuse 4.05 A"),
        ("CHS_HTR (7.2 ohm element)",        vbus / (R_HTR_BAY + 0.10), 3.04, "eFuse 3.04 A"),
        ("VMOT (2 bridges at ITRIP)",        2 * I_TRIP, 6.5, "eFuse 6.5 A; bridges chop at %.2f A each" % I_TRIP),
    ]
    return rows

# ----------------------------------------------------------------------------- resistances (milliohm) for the drop table
AWG = {12: 5.21, 14: 8.29, 16: 13.2, 18: 20.9, 20: 33.3, 22: 53.0, 24: 84.2}   # [D] copper, mohm/m at 20 C
def wire(awg, length_m, conductors=2):
    return AWG[awg] * length_m * conductors
PATHS = {
  "Pack -> VBAT_SW (board)": dict(i=[4.0, 13.0], parts=[
      ("cassette leads 2 x 0.15 m AWG 12", wire(12, 0.15)), ("SBS50 power contacts x2", 0.5), ("main fuse 20 A blade", 3.5),
      ("harness 2 x 0.30 m AWG 14", wire(14, 0.30)), ("Mini-Fit Jr HCS, 2 contacts in parallel per pole", 1.5),
      ("back-to-back FETs 2 x 2.2", 4.4), ("INA228 shunt", 1.0), ("board copper", 2.0)]),
  "VBAT_SW -> head heater, head docked": dict(i=[2.5, 4.0], parts=[
      ("INA3221 shunt", 5.0), ("TPS25947 FET", 28.0), ("board copper", 3.0), ("Micro-Fit contacts x2", 10.0),
      ("harness to J1 2 x 0.25 m AWG 18", wire(18, 0.25)), ("M16 contacts x2", 10.0), ("head pigtail 2 x 0.35 m AWG 18", wire(18, 0.35))]),
  "ADDED by LAB extension, heater pair, AWG 18": dict(i=[2.5, 4.0], parts=[
      ("2 x 2.0 m AWG 18", wire(18, 2.0)), ("extra M16 contact pair x2", 10.0)]),
  "ADDED by LAB extension, heater pair, AWG 20": dict(i=[2.5, 4.0], parts=[
      ("2 x 2.0 m AWG 20", wire(20, 2.0)), ("extra M16 contact pair x2", 10.0)]),
  "ADDED by LAB extension, heater pair, AWG 24 (moulded cordset)": dict(i=[2.5, 4.0], parts=[
      ("2 x 2.0 m AWG 24", wire(24, 2.0)), ("extra M16 contact pair x2", 10.0)]),
  "VBAT_SW -> head electronics, head docked": dict(i=[0.4, 1.0], parts=[
      ("INA3221 shunt", 20.0), ("TPS25947 FET", 28.0), ("board copper", 3.0), ("Micro-Fit contacts x2", 10.0),
      ("harness 2 x 0.25 m AWG 20", wire(20, 0.25)), ("M16 contacts x2", 10.0), ("pigtail 2 x 0.35 m AWG 20", wire(20, 0.35))]),
  "ADDED by LAB extension, electronics pair, AWG 20": dict(i=[0.4, 1.0], parts=[
      ("2 x 2.0 m AWG 20", wire(20, 2.0)), ("extra M16 contact pair x2", 10.0)]),
  "V5_CM5 buck -> CM5 carrier": dict(i=[1.5, 5.0], parts=[
      ("TPS25947 FET", 28.0), ("board copper", 2.0), ("Micro-Fit, 2 contacts in parallel per pole", 5.0),
      ("cable 2 x 0.25 m, two AWG 18 in parallel per pole", wire(18, 0.25) / 2), ("carrier header contacts", 10.0)]),
  "VBAT_SW -> LiDAR": dict(i=[0.3, 0.6], parts=[
      ("TPS25947 FET", 28.0), ("Micro-Fit contacts x2", 10.0), ("cable 2 x 0.40 m AWG 22", wire(22, 0.40))]),
  "VBAT_SW -> bay heater": dict(i=[1.7, 3.0], parts=[
      ("INA3221 shunt", 5.0), ("TPS25947 FET", 28.0), ("Micro-Fit contacts x2", 10.0), ("cable 2 x 0.30 m AWG 20", wire(20, 0.30)), ("thermal cut-out contact", 30.0)]),
  "VBAT_SW -> motor (one bridge, both legs)": dict(i=[0.5, I_TRIP], parts=[
      ("TPS25982 FET", 2.7), ("DRV8874 HS+LS (25 C typ)", 200.0), ("brake relay contacts x2", 20.0),
      ("Micro-Fit contacts x2", 10.0), ("motor lead 2 x 0.25 m AWG 22", wire(22, 0.25))]),
  "Charge inlet -> charger VIN": dict(i=[2.5, 4.0], parts=[
      ("M12 L-coded contacts x2", 6.0), ("harness 2 x 0.25 m AWG 18", wire(18, 0.25)), ("Mini-Fit contacts x2", 6.0),
      ("input fuse 5 A", 20.0), ("reverse-blocking FET", 10.0), ("RSNSI", 8.0)]),
}

# ----------------------------------------------------------------------------- coordination table
COORD = [
 # branch, source capability, protective device, electronic limit, conductor, connector rating, verdict
 ("Pack feed", "BMS 15 A cont., 25 A / 10 s, 30 A / 3 s, SC 60 A / 0.5 ms [D 12120; U 1290]", "20 A blade fuse within 150 mm of the coupler (32 V, >= 1 kA interrupt)", "none on the board (bidirectional switch has no current limit); OV cut-off 16.6 V",
  "AWG 14 (PVC-free, 105 C): 20 A fuse protects it", "Mini-Fit Jr HCS 2 x 13 A in parallel, derated 20 % -> 20.8 A [D Molex family rating, U exact terminal]", "OK. BMS trips first on a hard short; fuse clears a welded BMS"),
 ("VMOT", "VBAT_SW", "TPS25982 eFuse, RILIM 237 ohm", "6.5 A (+/-8 %%), fast trip ~2x; bridges chop at %.2f A each; DRV8874 OCP >= 6 A [D]" % I_TRIP,
  "motor leads AWG 22 (Pololu), 0.25 m: 7 A bundle rating at 30 K rise [A]", "Micro-Fit 3.0: 8.5 A [D family], 5 A with AWG 22-20", "OK. Contract ceiling 12 A not used"),
 ("V5_CM5", "LM61460 buck, HS limit 8.9-11.5 A [D]", "TPS259470 on the 5 V output, RILM 665 ohm", "5.0 A (4.5-5.5 A)", "2 x AWG 18 per pole", "Micro-Fit 2 contacts per pole (17 A)", "OK"),
 ("V12_LIDAR", "VBAT_SW", "TPS259470, RILM 2.21 k", "1.51 A (+/-10 %)", "AWG 22 (3 A)", "Micro-Fit 8.5 A", "OK"),
 ("V3V3_CHS / V5_AUX", "VSYS", "LMR51610 cycle-by-cycle limit (1 A device)", "1.0 A rated; peak limit ~1.4 A [U]", "board only", "-", "OK"),
 ("HEAD_PWR", "VBAT_SW", "TPS259470, RILM 2.21 k", "1.51 A", "AWG 20 (5 A)", "M16 8-pole 5 A/contact [contract]; Micro-Fit 8.5 A", "OK"),
 ("HEAD_HTR", "VBAT_SW", "TPS259470, RILM 825 ohm, dV/dt 10 nF", "4.05 A (3.6-4.4 A)", "AWG 18 (10 A)", "M16 5 A/contact: 4.4 A max trip leaves 12 % margin", "OK, tight on the M16 contact"),
 ("CHS_HTR", "VBAT_SW", "TPS259470, RILM 1.10 k + series bimetal cut-out in the heater harness", "3.04 A", "AWG 20 (5 A)", "Micro-Fit 8.5 A", "OK"),
 ("BUS_5V (J2)", "V5_AUX", "TPS2553, RILIM 150 k [U value]", "0.15-0.20 A", "AWG 24/26 pair", "M12 A-coded 8-pole 2 A/contact", "OK, short-proof"),
 ("Safety chain / relay coils", "VBAT_SW", "PTC resettable fuse 0.20 A hold / 0.40 A trip", "-", "AWG 24 (2 A)", "CLIK-Mate 2.0: 3 A", "OK"),
 ("Bus clamp", "VMOT", "4.7 ohm resistor, PTC 1.1 A hold in series", "3.4 A peak, tens of ms", "board", "-", "OK; PTC limits a stuck-on clamp"),
 ("Charge inlet", "24 V 3.75 A supply (90 W)", "5 A fuse + LTC4162 input current limit 4.0 A (RSNSI 8 mohm) [U]", "4.0 A", "AWG 18", "M12 L-coded 16 A; Mini-Fit 9 A", "OK"),
]

# ----------------------------------------------------------------------------- report
def fmt(x, n=1):
    return ("%%.%df" % n) % x

def build():
    o = []
    A = o.append
    A("# Rad Roomba power budget (design 0.4)\n")
    A("Owner: chassis electronics. **Generated by `electronics/analysis/power_budget.py` - edit the script, not this file.**\n")
    A("Evidence class of the whole document: `calculated`. Nothing here is measured. Tags: **[D]** datasheet value (source named in the script), **[C]** calculated here, "
      "**[A]** assumed design input, **[M]** from the mechanical thermal model, **[U]** UNVERIFIED (not confirmed from a primary source in this session).\n")
    A("All powers are at the **pack terminals** (conversion losses included), so the 0.3 worksheet's 90 % aggregate efficiency is *not* applied a second time.\n")

    A("## 1. Load inventory\n")
    A("| Load | Typ at rail (W) | Max at rail (W) | Efficiency from pack | Typ at pack (W) | Basis |\n|---|---:|---:|---:|---:|---|")
    for k, (typ, mx, eta, basis) in L.items():
        A("| %s | %s | %s | %.2f | %s | %s |" % (k, fmt(typ, 2), fmt(mx, 1), eta, fmt(typ / eta, 2), basis))
    pw, i, u = drive_w(0.10, 3.5, 0.20)
    pc, ic, uc = drive_w(0.10, 3.5, 0.50)
    p2, i2, u2 = drive_w(0.20, 3.5, 0.20)
    A("\n**Drive model [C]** (Pololu #2828 [D]: 67 rpm and 0.2 A no-load, 5.5 A / 49 kg-cm extrapolated stall at 12 V; 104 mm wheel): "
      "R = %.2f ohm, back-EMF %.1f V per m/s, %.3f N m/A at the output shaft. Rolling force 3.5 N total [A] (Crr 0.03 x 12 kg). "
      "0.10 m/s warm: %.2f A and %.1f V per motor, %.1f W for both. Cold [A, friction current 0.5 A]: %.1f W. 0.20 m/s warm: %.1f W. "
      "The 0.3 worksheet reserved 15 W average for drive; the model gives %.0f-%.0f W. The difference is the single largest change in this budget and is UNVERIFIED until a wheel-up and on-floor current log exists.\n"
      % (R_M, KE, KT_OUT, i, u, pw, pc, p2, pw, pc))

    A("## 2. Power by operating state (pack terminals)\n")
    A("| State | Typical (W) | Current at 12.8 V (A) | All-maximum stack (W) |\n|---|---:|---:|---:|")
    res = {}
    for name, items, t in STATES:
        typ, mx = state(items, 0), state(items, 1)
        res[name] = (typ, mx, t)
        A("| %s | %s | %s | %s |" % (name, fmt(typ), fmt(typ / V_NOM, 2), fmt(mx)))
    chg_out = 3.0 * 14.4
    chg_in = chg_out / 0.93 + state(["cm5_run", "logic", "protection_quies"], 0) / 0.98
    A("| Charge / Service (from the 24 V supply, pack receives 3.0 A) | %s from the adapter | %s A at 24 V | %s |"
      % (fmt(chg_in), fmt(chg_in / 24.0, 2), fmt(3.2 * 14.4 / 0.9 + state(["cm5_run", "logic", "protection_quies"], 1))))
    A("\nThe all-maximum column adds every maximum at once (CM5 12 W, LiDAR 6 W, head 10 W, drive 15 W, heaters at element rating). It is a bound for fuse and pack-current checks, not an operating point.\n")
    sac = {}
    for f in (0.70, 0.85):
        sac[f] = (step_and_count(res["Survey 0.10 m/s, +20 C"][0], res["Stationary recount / scaler count, +20 C"][0], f),
                  step_and_count(res["Survey 0.10 m/s, -20 C, heaters"][0], res["Stationary count, -20 C, heaters"][0], f))
    A("**Step-and-count duty profile (contract `survey_methods.STEP_AND_COUNT`, stationary 70-85 %% of the time) [C]:** "
      "+20 C: %s W (70 %% stationary) / %s W (85 %%). -20 C: %s W / %s W. Standing still saves only the drive power (%.1f-%.1f W): the mission is dominated by compute, head and heaters.\n"
      % (fmt(sac[0.70][0]), fmt(sac[0.85][0]), fmt(sac[0.70][1]), fmt(sac[0.85][1]), P("drive_warm"), P("drive_cold")))

    A("### Comparison with the 0.3 worksheet\n")
    old = {"drive": 15.0, "compute": 10.0, "lidar": 6.0, "chassis logic and sensors": 3.0, "heaters combined": 15.0, "detector interface": 1.0}
    new = {"drive": P("drive_cold"), "compute": P("cm5_run"), "lidar": P("lidar"), "chassis logic and sensors": P("logic") + P("relays_armed") + P("protection_quies"),
           "heaters combined": P("htr_head_-20") + P("htr_bay_-20"), "detector interface": P("head_elec")}
    A("| Line | 0.3 worksheet, load side (W) | 0.3 at pack (/0.90) (W) | This budget at pack, -20 C survey (W) | Difference (W) |\n|---|---:|---:|---:|---:|")
    so = sn = 0
    for k in old:
        A("| %s | %s | %s | %s | %+.1f |" % (k, fmt(old[k]), fmt(old[k] / 0.9), fmt(new[k]), new[k] - old[k] / 0.9))
        so += old[k] / 0.9; sn += new[k]
    A("| **Total** | **50.0** | **%s** | **%s** | **%+.1f** |" % (fmt(so), fmt(sn), sn - so))
    A("\nHeaters rise from 15 to %.0f W [M] and the head from 1 to 5 W, but the drive falls from 15 W to about %.0f W [C]. Net: about %.0f W lower than the 0.3 total at the pack.\n"
      % (new["heaters combined"], new["drive"], so - sn))

    A("## 3. Runtime to reserve\n")
    A("Usable energy = nameplate x deliverable fraction [A: 1.00 at +20 C, 0.80 at -20 C, 0.75 at -25 C] x (1 - %.0f %% reserve [A]). The 0.3 worksheet used the same 0.80 and 20 %% and a 90 %% conversion factor "
      "(8 Ah: 59.0 Wh at the loads, 70.8 min at 50 W); here the conversion is inside the loads.\n" % (RESERVE * 100))
    cases = [
        ("Survey +20 C", res["Survey 0.10 m/s, +20 C"][0], "+20 C"),
        ("Step-and-count +20 C (85 % stationary)", sac[0.85][0], "+20 C"),
        ("Survey -20 C with heaters", res["Survey 0.10 m/s, -20 C, heaters"][0], "-20 C"),
        ("Step-and-count -20 C (85 % stationary)", sac[0.85][1], "-20 C"),
        ("Survey -25 C with heaters", res["Survey 0.10 m/s, -25 C, heaters"][0], "-25 C"),
        ("0.3 worksheet case, 50 W load side = 55.6 W at pack, -20 C", 50 / 0.9, "-20 C"),
        ("Pessimistic -20 C: 0.3 drive 15 W, CM5 10 W, LiDAR 6 W, head 10 W, heaters 22 W", 15/.97 + 10/ETA_5V + 6 + P("logic") + P("relays_armed") + P("protection_quies") + 10/.98 + 22/.98, "-20 C"),
    ]
    hdr = "| Case | Pack power (W) |" + "".join(" %s (min) |" % k.split(" Power")[0].split(" (")[0] for k in PACKS)
    A(hdr); A("|---|---:|" + "---:|" * len(PACKS))
    rt = {}
    for name, p, t in cases:
        row = "| %s | %s |" % (name, fmt(p))
        for k, (ah, *_r) in PACKS.items():
            m = ah * V_NOM * AVAIL[t] * (1 - RESERVE) / p * 60
            rt[(name, k)] = m
            row += " %s |" % fmt(m, 0)
        A(row)
    A("")
    # mission example
    stations = (12.0 / 0.10) * 7
    for cnt in (10, 30):
        tt = stations * (cnt + 0.5 + 2.0) / 3600.0
        e_w, e_c = tt * sac[0.85][0], tt * sac[0.85][1]
        A("Step-and-count example [A: 12 m x 2.4 m floor, 7 lanes, 0.10 m pitch = %d stations, %d s preset + 0.5 s settle + 2 s move]: %.1f h; "
          "energy %.0f Wh at +20 C, %.0f Wh at -20 C -> packs needed (9 Ah / 12 Ah): +20 C %.1f / %.1f, -20 C %.1f / %.1f."
          % (stations, cnt, tt, e_w, e_c, e_w / (9 * V_NOM * 0.8), e_w / (12 * V_NOM * 0.8), e_c / (9 * V_NOM * 0.64), e_c / (12 * V_NOM * 0.64)))
    A("")

    A("## 4. Peak current allocation\n")
    for vb in (V_MIN, V_NOM, V_FULL):
        rows = peak(vb)
        A("**Bus %.1f V**\n" % vb)
        A("| Branch | Worst simultaneous demand (A) | Branch limit referred to the bus (A) | Limiter |\n|---|---:|---:|---|")
        tot = totl = 0
        for n, i, lim, how in rows:
            A("| %s | %s | %s | %s |" % (n, fmt(i, 2), fmt(lim, 2), how)); tot += i; totl += lim
        A("| **Sum** | **%s** | **%s** | pack BMS 15 A continuous [D], main fuse 20 A |\n" % (fmt(tot, 1), fmt(totl, 1)))
    A("Both heaters fully on while both motors sit at the hardware current limit and the CM5 is at 12 W gives 12.0-12.5 A: inside the 15 A continuous rating of either Power-Sonic pack [D] "
      "with 17 %% margin, and inside the 20 A fuse. The sum of all branch *limits* (about 19-21 A) exceeds the BMS continuous rating, so two simultaneous branch faults can trip the BMS (25 A / 10 s): "
      "that is a total power loss, which the safety chain treats as a stop (relays drop, motors on brake resistors). Firmware should shed the bay heater while drive current exceeds 2 A (recommended, not relied on).\n")

    A("## 5. Fuse / eFuse coordination\n")
    A("| Branch | Source capability | Protective device | Electronic limit | Conductor | Connector rating | Verdict |\n|---|---|---|---|---|---|---|")
    for r in COORD:
        A("| " + " | ".join(r) + " |")
    A("")

    A("## 6. Voltage drops\n")
    A("Copper at 20 C [D]; at -20 C copper is 16 % lower. Contact resistances are assumed values [A] (5 mohm per signal-power contact pair, 0.25 mohm for the SBS50) unless stated.\n")
    A("| Path (supply + return) | Resistance (mohm) | Drop at typical (V @ A) | Drop at limit (V @ A) | Loss at limit (W) |\n|---|---:|---:|---:|---:|")
    tot_r = {}
    for name, d in PATHS.items():
        r = sum(x[1] for x in d["parts"]); tot_r[name] = r
        i1, i2 = d["i"]
        A("| %s | %s | %.3f @ %.1f | %.3f @ %.1f | %.2f |" % (name, fmt(r), r * i1 / 1000, i1, r * i2 / 1000, i2, r * i2 * i2 / 1000))
    A("")
    for name, d in PATHS.items():
        A("- *%s*: " % name + "; ".join("%s %.1f" % x for x in d["parts"]) + " mohm.")
    ext18 = tot_r["ADDED by LAB extension, heater pair, AWG 18"]; ext20 = tot_r["ADDED by LAB extension, heater pair, AWG 20"]; ext24 = tot_r["ADDED by LAB extension, heater pair, AWG 24 (moulded cordset)"]
    A("\n**LAB extension against the head ICD section 7 budget (0.125 ohm added, 0.5 V at 4 A) [C]:** AWG 18 heater cores: %.0f mohm, %.2f V -> **meets** the budget with %.0f %% margin. "
      "AWG 20: %.0f mohm, %.2f V -> **exceeds** it by %.0f %%. A moulded AWG 24 cordset: %.0f mohm, %.2f V -> **fails by a factor %.1f**. "
      "Consequence: the 2 m extension must be a custom cable with >= 0.75 mm2 (AWG 18) heater cores, and the M16 8-pole contacts must accept that wire [U - binder 8-pole solder cups may be limited to 0.5 mm2; "
      "harness lead to confirm]. If only 0.5 mm2 fits, limit the extension to 1.7 m or raise the budget to 0.15 ohm (the heater is resistive; 0.57 V at 4 A costs 9 %% of heater power at 12 V and nothing else).\n"
      % (ext18, ext18 * 4 / 1000, (125 - ext18) / 125 * 100, ext20, ext20 * 4 / 1000, (ext20 - 125) / 125 * 100, ext24, ext24 * 4 / 1000, ext24 / 125))
    hd = tot_r["VBAT_SW -> head electronics, head docked"]; he = tot_r["ADDED by LAB extension, electronics pair, AWG 20"]; pk = tot_r["Pack -> VBAT_SW (board)"]
    A("**Head supply floor [C]:** at 1.0 A (10 W at 10 V) the head sees pack - %.2f V docked and pack - %.2f V through the extension (pack path %.0f mohm at 4 A included). "
      "The head's 10 V minimum therefore needs >= %.1f V at the pack in LAB at full head load; the BATTERY_LOW stop (reserve, about 12.6 V at rest) is far above it.\n"
      % ((hd + pk * 4) / 1000 * 1.0 if False else (hd * 1.0 + pk * 4.0) / 1000, ((hd + he) * 1.0 + pk * 4.0) / 1000, pk, 10.0 + ((hd + he) * 1.0 + pk * 4.0) / 1000))
    r5 = tot_r["V5_CM5 buck -> CM5 carrier"]
    A("**CM5 feed [C]:** buck regulated to 5.12 V +/-1.5 %% at the eFuse input; %.0f mohm to the carrier -> %.2f V at 1.5 A, %.2f V at 5 A (Raspberry Pi 5 V +/-5 %% = 4.75-5.25 V [D CM5 datasheet, U exact clause]).\n"
      % (r5, 5.12 - r5 * 1.5 / 1000, 5.12 - r5 * 5 / 1000))

    A("## 7. Dissipation on RR-CHS-MAIN\n")
    def brd(i_bus, i_htr_h, i_htr_b, p5, i_mot, charging):
        rows = [
            ("Main switch FETs + shunt + copper (7.4 mohm)", i_bus ** 2 * 7.4e-3),
            ("5.12 V buck LM61460 (1 - eta)", p5 * (1 / ETA_5V - 1)),
            ("V5 eFuse", (p5 / 5.12) ** 2 * 0.028),
            ("3.3 V and 5 V_AUX bucks", 0.35),
            ("Logic on the board (3.3 V, 5 V loads)", 1.0),
            ("Head branches: shunts + eFuses", i_htr_h ** 2 * 0.033 + 0.5 ** 2 * 0.048),
            ("Bay heater branch", i_htr_b ** 2 * 0.033),
            ("DRV8874 x2 (I2R at 0.2 ohm + 36 mW quiescent each)", 2 * (i_mot ** 2 * 0.2 + 0.036)),
            ("Brake + latch relay coils", 0.94),
            ("Charger LTC4162 + inductor (7 % of 43 W)", 3.2 if charging else 0.03),
        ]
        return rows
    cases7 = [("Survey +20 C", brd(1.7, 0, 0, 7.0, 0.3, False)), ("Survey -20 C, heaters at average duty (rms of on/off cycling)", brd(4.0, 2.5 * (16 / 30.0) ** 0.5, 1.67 * (6 / 20.0) ** 0.5, 7.0, 0.6, False)),
              ("Worst sustained: all heaters on, CM5 12 W, motors 1.5 A", brd(11.0, 2.9, 2.0, 12.0, 1.5, False)), ("Charge / Service", brd(3.0, 0, 0, 7.0, 0, True))]
    A("| Source | " + " | ".join(c[0] for c in cases7) + " |\n|---|" + "---:|" * len(cases7))
    for k in range(len(cases7[0][1])):
        A("| %s | " % cases7[0][1][k][0] + " | ".join(fmt(c[1][k][1], 2) for c in cases7) + " |")
    A("| **Total (W)** | " + " | ".join("**%s**" % fmt(sum(x[1] for x in c[1]), 1) for c in cases7) + " |")
    A("\nMotor stall at the hardware limit (%.2f A, firmware stall timer 2 s [A]): DRV8874 at 150 C junction has roughly 1.7x the 25 C resistance [A; TI gives only 25 C values] -> %.1f W per bridge for the duration of the stall. "
      "Board steady-state is 3-6 W spread over 160 x 100 mm with the bridges, buck and charger on the gap pad to the aluminium bridge tray (mechanical THERMAL_TO_BRIDGE zone): "
      "about 0.3-0.5 W per 10 cm2, no forced air needed [C, order of magnitude]. The charger is the local hot spot (3.2 W in a 4 x 5 mm QFN and one inductor) and must sit on the pad.\n"
      % (I_TRIP, I_TRIP ** 2 * 0.34))

    A("## 8. Pack sizing: 12 Ah baseline (DEC-040), 9 Ah shown for comparison\n")
    k9 = "9 Ah Power-Sonic PSL-SC-1290"; k12 = "12 Ah Power-Sonic PSL-SC-12120"
    pess = "Pessimistic -20 C: 0.3 drive 15 W, CM5 10 W, LiDAR 6 W, head 10 W, heaters 22 W"
    A("The owner has fixed the 12 Ah pack (Power-Sonic PSL-SC-12120 class, 1.65 kg, 15 A continuous [D]) as the baseline. Charger current, main fuse, coupler and the tables above are sized for it; "
      "the 9 Ah PSL-SC-1290 column is a comparison only and the 8 Ah column carries the 0.3 worksheet forward.\n")
    A("| Headline (12 Ah baseline) | Value | 9 Ah comparison | Tag |\n|---|---:|---:|---|")
    for lab, key in [("Continuous survey at -20 C with 22 W heaters, minutes to 20 % reserve", "Survey -20 C with heaters"),
                     ("Continuous survey at -25 C with 30 W heaters", "Survey -25 C with heaters"),
                     ("Pessimistic -20 C stack (68 W)", pess),
                     ("Step-and-count at -20 C (85 % stationary), minutes per pack", "Step-and-count -20 C (85 % stationary)"),
                     ("Step-and-count at +20 C, minutes per pack", "Step-and-count +20 C (85 % stationary)"),
                     ("Continuous survey at +20 C", "Survey +20 C")]:
        A("| %s | %.0f | %.0f | [C] |" % (lab, rt[(key, k12)], rt[(key, k9)]))
    A("| Margin on the one-hour cold deployment (typical / pessimistic) | %+.0f %% / %+.0f %% | %+.0f %% / %+.0f %% | [C] |"
      % ((rt[("Survey -20 C with heaters", k12)] / 60 - 1) * 100, (rt[(pess, k12)] / 60 - 1) * 100, (rt[("Survey -20 C with heaters", k9)] / 60 - 1) * 100, (rt[(pess, k9)] / 60 - 1) * 100))
    A("| Worst simultaneous pack current against the 15 A continuous BMS rating | 12.5 A (17 % margin) | same rating [U for the 1290] | [C]/[D] |")
    A("| Charge time at 3.0 A from 20 %% reserve (CC to ~95 %%, then taper) | about %.1f h | about %.1f h | [C] |" % (12 * 0.8 / 3.0 + 0.5, 9 * 0.8 / 3.0 + 0.5))
    A("| Charge rate | 0.25 C | 0.33 C | [C]; Power-Sonic's own charger for the 12120 is a 4 A unit [D] |")
    A("")
    A("Sizing consequences of the 12 Ah baseline [C]: charge current stays at the contract 3.0 A (LTC4162 maximum 3.2 A [D]); the external supply must deliver %.0f W -> a 90 W / 24 V unit; "
      "main fuse 20 A and the 50 A-class coupler are set by the 15 A BMS rating and the 12.5 A peak, not by capacity; mass +0.65 kg over the 9 Ah pack counts against the 12 kg lift allowance [D]. "
      "Step-and-count missions of several hours still need pack swaps in the cold (%.1f h per pack at -20 C).\n" % (chg_in, rt[("Step-and-count -20 C (85 % stationary)", k12)] / 60))
    A("What would make even 12 Ah insufficient for the one-hour cold case: a measured -20 C average above about %.0f W at the pack, or a deliverable fraction below %.2f at the real cell temperature at the typical load. "
      "Both are bench measurements on the first pack.\n" % (12 * V_NOM * 0.64, 60 * 47.3 / (12 * V_NOM * 0.8 * 60)))
    A("## 9. Unknowns that move these numbers\n")
    A("| Unknown | Design range used | How it is closed |\n|---|---|---|")
    for r in [
        ("Drive power on real floors, cold grease", "2.6-5.5 W typical, 15 W bound", "Wheel-up and on-floor current log from IPROPI and INA228 at +20 and -20 C"),
        ("CM5 + carrier average under the real ROS graph", "7 W typ, 12 W max", "INA228 delta with the 5 V rail cycled; V5 eFuse ILM test point"),
        ("LiDAR power, cold start", "3.5 W typ, 6 W max", "Bench supply measurement at 10 V and 14.4 V, -20 C"),
        ("Heater duty", "22 W at -20 C, 30 W at -25 C [M]", "Thermal coupon and first cold soak; INA3221 channels log both heaters"),
        ("Head electronics", "5 W target, 10 W ceiling", "Head board bring-up"),
        ("Deliverable capacity at the real cell temperature", "0.80 / 0.75", "Discharge test of the selected pack in the heated bay at -20 C ambient"),
        ("PSL-SC-1290 BMS trip thresholds", "assumed equal to the 12120 sheet", "Read the 1290 technical document; confirm with Power-Sonic"),
        ("Contact resistances", "5 mohm per contact pair", "Four-wire measurement on the first harness"),
    ]:
        A("| %s | %s | %s |" % r)
    return "\n".join(o) + "\n"

if __name__ == "__main__":
    md = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "power_budget.md")
    with open(out, "w") as f:
        f.write(md)
    print("wrote", out, len(md.splitlines()), "lines")
