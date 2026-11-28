"""Production build (RR_BUILD=production): process, material, tooling and part-number mapping applied to the shared RR-X model.

The geometry comes from the same rrx modules with dims.PROD switched on (one-piece SLS skins, tapped machined pods). This module
re-labels every part for production: RRP- part number, process class, material, tooling class, minimum feature / tolerance
assumption, sealing approach and what is carried over unchanged.  Process capabilities are typical supplier values: UNVERIFIED
until a supplier quotes against the drawings.
"""
from __future__ import annotations

import fnmatch

# process classes ---------------------------------------------------------------------------------------------------------
SLS = "SLS PA11 (large-frame laser sintering)"
SLS_SMALL = "SLS PA11 (nested in the skin builds)"
CNC = "CNC machined 6061-T6"
CNC_PLATE = "waterjet / laser blank + CNC (one fixture) 6061-T6"
SHEET = "laser cut + press-brake bent sheet"
LASER = "laser / waterjet cut sheet"
GROUND = "sheet cut + surface ground"
CAST = "cast polyurethane (open / two-part mould)"
TURNED = "turned / milled bar"
X1C = "FFF print on the X1C (shop aid, not a robot part)"
BUY = "purchased"

PROCESS = {   # class -> (tooling, min feature / tolerance assumption, typical capability source)
    SLS: ("none", "wall >= 1.2 mm (1.0 local), holes >= 1.5 mm, +-0.3 mm or +-0.3 % (larger) as sintered; machine or ream datum bores", "typical SLS PA11 service-bureau data, UNVERIFIED"),
    SLS_SMALL: ("none", "as SLS: wall >= 1.0 mm, +-0.25 mm on small parts", "UNVERIFIED"),
    CNC: ("soft (vice jaws / fixture plate)", "+-0.05 general on machined faces, bores H7 reamed, ISO 2768-mK", "standard 3-axis job-shop capability"),
    CNC_PLATE: ("soft (vacuum or pin fixture for the blank)", "profile +-0.2 (waterjet) / +-0.1 (laser); machined holes and pockets +-0.05, reamed 4 H7", "standard"),
    SHEET: ("none (standard brake tooling)", "bend radius >= 1 t, hole to bend >= 2 t + r, +-0.2 flat, +-0.5 deg bends", "standard sheet-metal shop"),
    LASER: ("none", "kerf compensated +-0.1, holes >= t", "standard"),
    GROUND: ("none", "thickness +-0.02, flatness 0.01; profile +-0.1", "G-10 surface grinding, UNVERIFIED shop capability"),
    CAST: ("soft (machined aluminium or 3D-printed master + silicone mould, about 50 shots)", "+-0.3 mm, shrink-compensated mould; 85 Shore A", "typical cast-PU shop, UNVERIFIED"),
    TURNED: ("none", "+-0.05", "standard"),
    X1C: ("none", "see the prototype package", "-"),
    BUY: ("-", "supplier data", "-"),
}

AL_FINISH = "clear anodise MIL-A-8625 type II (chromate conversion on contact faces)"
SEAL_SKIN = "one perimeter closed-cell silicone gasket on the hull tongue land (-55 C rated), compressed by the M3 perimeter screws; device seats with flat gaskets / O-rings as in the prototype"

# name pattern -> (process, material, finish, sealing, carried over unchanged, replaces in the X1C build)
RULES = [
    ("lower_hull", SLS, "PA11", "dyed black + 2K PU topcoat (UV)", SEAL_SKIN, "Rev E skin law, tongue, sole ring, perimeter stations, cliff / bumper seats", "4 printed pieces RRX-P20L/R, P21L/R (x -71 and y 0 splits)"),
    ("upper_shell", SLS, "PA11", "dyed black + 2K PU topcoat (UV)", SEAL_SKIN, "Rev E skin law, every ToF / control / inlet / receptacle seat, saddle well, hump, latch pocket", "6 printed pieces RRX-P22..P25 (x 47 / x -38 / hump joints)"),
    ("saddle_cover", SLS_SMALL, "PA11", "dyed black", "flat gasket under the cover, 6 captive M3 into inserts (as prototype)", "geometry, screw pattern", "RRX-P26 PAHT-CF print"),
    ("hatch_frame", SLS_SMALL, "PA11", "dyed black", "frame ring = door gasket land (as prototype)", "geometry", "RRX-P27"),
    ("hatch_door", SLS_SMALL, "PA11", "dyed black + PU topcoat", "door skirt gasket on the frame ring", "geometry", "RRX-P28"),
    ("motor_pod_*", CNC, "AL6061", AL_FINISH, "sealed notch in the hull as prototype", "envelope and interfaces; M4 heat-set inserts -> tapped M4", "RRX-P01L/R PAHT-CF print"),
    ("wheel_rim_*", CNC, "AL6061", "black anodise type II", "-", "envelope, hub bolt circle, tyre keys", "RRX-P30 PAHT-CF print"),
    ("tyre_*", CAST, "PU85A", "-", "-", "profile, keys (cast onto the rim keys with primer)", "RRX-P31 TPU 95A print"),
    ("chassis_plate", CNC_PLATE, "AL6061", AL_FINISH, "RTV bead at the hull sole ring (as prototype)", "hole table, pockets, thermal-break holes", "same part (laser blank + manual ops in the X1C build)"),
    ("receiver_channel_*", CNC, "AL6061", "hard anodise MIL-A-8625 type III 25 um, mask reamed bores", "-", "all geometry (datum part)", "same part"),
    ("receiver_shim_*", GROUND, "G10", "-", "-", "all geometry", "same part"),
    ("grip_side_plate_*", LASER, "AL6061", AL_FINISH, "-", "geometry", "same part"),
    ("grip_foot_*", CNC, "AL6061", AL_FINISH, "-", "geometry (machined from 6061 angle / bar)", "6060 angle cut to length"),
    ("grip_bar", TURNED, "AL6061", "hard anodise", "-", "geometry", "same part"),
    ("bridge_tray", LASER, "AL5052", "chromate conversion (EMI / gap pad contact)", "-", "geometry (flat 2 mm plate with six pressed-in clinch standoffs, review m7)", "same part"),
    ("bridge_post_*", TURNED, "AL6061", AL_FINISH, "-", "geometry", "same part"),
    ("screw_ring_*", LASER, "SS304", "passivate", "-", "geometry", "same part"),
    ("caster_disc", LASER, "SS304", "passivate", "-", "geometry", "same part"),
    ("caster_shim", LASER, "SS304", "passivate", "-", "geometry", "same part"),
    ("latch_arm", CNC, "AL6061", AL_FINISH, "-", "geometry", "same part"),
    ("tray_*", X1C, None, "-", "-", "transport tray, unchanged", "same part"),
    # everything else that was printed: SLS PA11 nested in the skin builds, same geometry
    ("*", SLS_SMALL, "PA11", "dyed black", "as prototype", "geometry unchanged", "X1C print"),
]
PN_MAP = {"RRX-P20": "RRP-S01", "RRX-P22": "RRP-S02"}
MATERIAL_MAP = {"PA11": "PA11-SLS", "PU85A": "PU85A-CAST"}


def rule_for(name):
    return next(r for r in RULES if fnmatch.fnmatch(name, r[0]))


def apply(parts):
    """Re-label the parts of a production build in place (geometry untouched). Returns the process table rows."""
    rename = {"nose_cowl": "upper_shell", "shoulder_L": "upper_shell", "shoulder_R": "upper_shell", "rear_deck_L": "upper_shell", "rear_deck_R": "upper_shell",
              "battery_hump": "upper_shell", "lower_hull_FL": "lower_hull", "lower_hull_FR": "lower_hull", "lower_hull_RL": "lower_hull", "lower_hull_RR": "lower_hull"}
    rows = []
    for p in parts:
        p.mates = {rename.get(m, m) for m in p.mates}
        p.x1c_pn, p.x1c_kind, p.x1c_material = p.pn, p.kind, p.material
        if p.kind in ("purchased", "placeholder"):
            p.process_class, p.tooling, p.finish = BUY, "-", "-"
            p.pn = p.pn.replace("RRX-", "RRP-")
            continue
        pat, proc, mat, finish, seal, carried, replaces = rule_for(p.name)
        if proc == X1C:
            p.process_class, p.tooling, p.finish = X1C, "none", "-"
            continue
        if pat == "*" and p.kind == "fabricated":                      # fabricated parts without an explicit rule: same part, same process
            proc, mat, finish, carried, replaces = CNC, p.material, AL_FINISH if p.material.startswith("AL") else "-", "geometry", "same part"
        p.kind = "fabricated"
        if mat:
            p.material = MATERIAL_MAP.get(mat, mat)
        base = p.pn[:7] if p.pn[:7] in PN_MAP else None
        p.pn = PN_MAP[base] if base else p.pn.replace("RRX-", "RRP-")
        p.process_class, p.tooling, p.finish = proc, PROCESS[proc][0], finish
        p.sealing, p.carried, p.replaces = seal, carried, replaces
        p.note = f"{proc}; {finish}"
        rows.append(p)
    return rows
