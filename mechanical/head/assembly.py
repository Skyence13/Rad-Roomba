"""Assemblies: prototype (X1C printed housing), production (CNC 6061 housing) and the dummy head.

build(name, projection) returns a list of geom.Part in base_link coordinates (installed, rails at rest).
Part numbers: RR-HD-X-xxx prototype-only, RR-HD-P-xxx production-only, RR-HD-S-xxx shared fabricated parts,
PUR-xxx purchased items, OEM-/EL- envelopes owned by other work packages.
"""
from __future__ import annotations

from . import hp as H
from . import parts as T
from .geom import Part, box, mass_cg

COL = {"frame": "#344c51", "receiver": "#b5c6ca", "deck": "#c9d2d6", "emi": "#d9a441", "lane": "#278981", "optic": "#71acbb",
       "window": "#5d6f75", "rail": "#24393e", "switch": "#c0392b", "elec": "#2e7d32", "cable": "#222222", "seal": "#111111", "aux": "#8e6bbf", "fastener": "#9aa3a8"}
PRINT_MAT = {"frame": "PA-CF", "small": "PA-CF", "window": "PETG-CF", "cover": "PETG-CF", "insert": "PA-CF"}


def _p(lst, name, pn, shape, material, kind, group, desc, **kw):
    lst.append(Part(name=name, pn=pn, shape=shape, material=material, kind=kind, group=group, desc=desc, color=COL[group], **kw))


def build(build="prototype", projection=3.0, travel=0.0):
    proto, prod, dummy = build == "prototype", build == "production", build == "dummy"
    printed_frame = proto or dummy
    P = []
    X = "X" if printed_frame else "P"
    # ---------------- frame
    if printed_frame:
        _p(P, "frame_L", "RR-HD-X-101", T.frame("L"), PRINT_MAT["frame"], "printed", "frame", "printed frame half, left (S0, S1), joint tongue", proc="FDM PA-CF, upright, 0.2 mm")
        _p(P, "frame_R", "RR-HD-X-102", T.frame("R"), PRINT_MAT["frame"], "printed", "frame", "printed frame half, right (S2, S3), joint groove", proc="FDM PA-CF, upright, 0.2 mm")
    else:
        _p(P, "frame", "RR-HD-P-101", T.frame("P"), "AL6061", "fab", "frame", "one-piece frame, CNC 6061-T6, black anodise, bond lands masked", proc="3-axis CNC, 2 set-ups + front/rear drilling")
    # ---------------- receiver (aluminium, both builds)
    for s, tag in ((1, "L"), (-1, "R")):
        _p(P, f"shoe_{tag}", "RR-HD-S-111", T.shoe(s), "AL6061", "fab", "receiver", "receiver shoe with T-head and x-stop shoulder (datums A, B, C)", proc="CNC 6061-T6, hard anodise, shoulder + tab face masked")
        _p(P, f"shoe_isolator_{tag}", "RR-HD-S-113", T.shoe_isolator(s), "FR4", "fab", "receiver",
           "0.5 mm G10 isolator, selectable 0.40 / 0.50 / 0.60 (FRAME isolated from the shoes in both builds)")
    _p(P, "bridge", "RR-HD-S-114", T.bridge(), "AL6061", "fab", "receiver", "rear bridge: ties both T-heads across the split, keeper hinge ears")
    _p(P, "keeper", "RR-HD-S-115", T.keeper(), "SS304", "fab", "receiver", "hinged latch keeper plate with hook at x 104 (flips back to release the lid)")
    _p(P, "keeper_pin", "PUR-DP3x40", T.keeper_pin(), "SS304", "purchased", "receiver", "hinge pin 3 x 40, retained by circlips")
    # ---------------- deck
    _p(P, "spreader", "RR-HD-S-121", T.spreader(), "AL6061", "fab", "deck", "one-piece 2 mm spreader / stiffener / FRAME plane (laser cut + tapped)", proc="laser cut 5052-H32 or 6061-T6 2.0 mm, DXF")
    _p(P, "lid", "RR-HD-S-122", T.lid(), "AL6061", "fab", "deck", "2 mm aluminium lid (shear panel, EMI top), 34 x M3 + bonded washers (<= 40 mm pitch except the J1 bay, CR-M03)", proc="laser cut 2.0 mm, DXF")
    _p(P, "j1_blister", "RR-HD-S-123", T.j1_blister(), "AL6061", "fab", "deck", "1 mm blister plate over the J1 landing opening (8.9 mm internal height)", proc="laser cut 1.0 mm, conductive-bonded + 4 rivets")
    if not dummy:
        _p(P, "jacket_top", "RR-HD-S-131", T.jacket_top(), "EPDM-FOAM", "fab", "deck", "insulating jacket cap 3 mm closed-cell foam, wipeable skin, PSA on the lid (standard cold configuration)", hard=False)
        _p(P, "jacket_front", "RR-HD-S-132", T.jacket_front(), "EPDM-FOAM", "fab", "deck", "insulating jacket front band 3 mm, PSA on the frame front face above the bail blocks", hard=False)
    _p(P, "lid_gasket", "PUR-GSK-LID", T.lid_gasket(), "SIL-FOAM", "purchased", "seal", "lid perimeter gasket, closed-cell silicone 1.2 mm (0.8 installed)", hard=False)
    nso = len(T.lid_holes())
    if proto:
        nf = sum(1 for x, y in T.lid_holes() if T.standoff_on_foot(x, y))
        _p(P, "lid_standoffs", "PUR-SO-M3x10.5", T.lid_standoffs(True, "foot"), "AL6061", "purchased", "deck", f"{nf} x M3 x 10.5 round female spacer on the fence feet (lid hard seat, lid-spreader tie, fence bond)")
        _p(P, "lid_standoffs_11", "PUR-SO-M3x11", T.lid_standoffs(True, "spreader"), "AL6061", "purchased", "deck", f"{nso - nf} x M3 x 11 round female spacer in the chimney zones (no fence foot)")
    else:
        _p(P, "lid_standoffs", "PUR-SO-M3x11", T.lid_standoffs(False), "AL6061", "purchased", "deck", f"{nso} x M3 x 11 round female spacer (lid hard seats, lid-spreader tie)")
    _p(P, "board_standoffs", "PUR-SO-M2.5x2.5", T.board_standoffs(), "BRASS", "purchased", "deck", "8 x M2.5 x 2.5 clinch standoff (FRAME net)")
    _p(P, "rib_gaskets", "PUR-GSK-RIB", T.rib_gaskets(), "SIL-FOAM", "purchased", "seal", "rib-top light gasket strips 5.4 x 1.0 (0.6 installed)", hard=False)
    if not dummy:
        _p(P, "lid_liner", "PUR-FOAM-LINER", T.lid_liner(), "EPDM-FOAM", "purchased", "seal", "0.5 mm closed-cell insulation liner under the lid", hard=False)
    if proto:
        _p(P, "fence_front", "RR-HD-X-124", T.fence_front(), "AL5052", "fab", "emi", "EMI fence, front (0.5 mm, laser cut + 2 bends)")
        _p(P, "fence_side_L", "RR-HD-X-125", T.fence_side(1), "AL5052", "fab", "emi", "EMI fence, side (0.5 mm)")
        _p(P, "fence_side_R", "RR-HD-X-125", T.fence_side(-1), "AL5052", "fab", "emi", "EMI fence, side (0.5 mm, mirrored use)")
        _p(P, "fence_rear", "RR-HD-X-126", T.fence_rear(), "AL5052", "fab", "emi", "EMI rear comb with four chimney liners (0.5 mm)")
        _p(P, "fence_gaskets", "PUR-GSK-EMI", T.fence_gaskets(), "SIL-FOAM", "purchased", "emi", "conductive fabric-over-foam strip on the fence flanges", hard=False)
    # ---------------- lanes
    for i in range(4):
        _p(P, f"S{i}_cassette", f"RR-HD-{X}-201", T.cassette(i), "PETG-CF" if printed_frame else "AL6061", "printed" if printed_frame else "fab", "window",
           "window cassette: 80 x 100 aperture, three guard webs, film land, lips", proc="FDM flat" if printed_frame else "CNC from 4 mm 6061, black anodise")
        if not dummy:
            _p(P, f"S{i}_film", "PUR-FILM", T.film(i), "PET", "purchased", "window", "entrance film (aluminised PET, areal density per radiometry) bonded to the cassette", mass_g=0.1)
        _p(P, f"S{i}_cassette_gasket", "PUR-GSK-CAS", T.cassette_gasket(i), "SIL-FOAM", "purchased", "seal", "cassette gasket, black closed-cell 0.8 mm (0.45 installed)", hard=False)
        if dummy:
            continue
        for nm, (shape, mat, kind, desc) in T.lane_parts(i).items():
            pn = {"floor_module": "OEM-FLOOR", "ref_module": "OEM-REF", "floor_carrier": "OEM-CARRIER", "ref_carrier": "OEM-CARRIER", "floor_sipm": "OEM-SIPM", "ref_sipm": "OEM-SIPM",
                  "spacer_lower": f"RR-HD-{X}-301", "barrier": f"RR-HD-{X}-302", "spacer_upper": f"RR-HD-{X}-303", "chimney_insert": f"RR-HD-{X}-304",
                  "pad": "PUR-PAD", "heater": "PUR-HEATER"}[nm]
            if kind == "printed" and prod:
                mat, kind = "PA12-MJF", "fab"
            mg = {"floor_module": 50.0, "ref_module": 52.0}.get(nm)
            _p(P, f"S{i}_{nm}", pn, shape, mat, kind, "optic" if kind == "envelope" else "lane", desc, mass_g=mg, hard=nm not in ("pad",),
               allow={f"S{i}_floor_module"} if nm == "floor_sipm" else ({f"S{i}_ref_module"} if nm == "ref_sipm" else set()))
    # ---------------- leading rail (front zone)
    _p(P, "rail_bar", "RR-HD-S-401", T.rail_bar(travel), "AL6061", "fab", "rail", "leading rail bar 350 x 14 x 3", proc="6061-T6 flat bar, drilled / tapped M3, hard anodise")
    for k in range(4):
        _p(P, f"rail_insert_{k}", f"RR-HD-{X}-411", T.insert_segment(k, projection, travel), "PA-CF" if printed_frame else "POM", "printed" if printed_frame else "fab", "rail",
           "reversible wear insert segment (3 mm / 5 mm projection by flipping)", proc="FDM flat" if printed_frame else "CNC POM-C black")
    for s, tag in ((1, "L"), (-1, "R")):
        _p(P, f"guide_rod_{tag}", "RR-HD-S-402", T.guide_rod(s, travel), "SS304", "fab", "rail", "guide rod 4 h6 x 67 with cam notch and M3 tapped end")
        _p(P, f"rod_spring_{tag}", "PUR-SPR-ROD", T.rod_spring(s), "SS304", "purchased", "rail", "compression spring 3.6 OD x 27 free, about 0.3 N/mm", mass_g=0.4, hard=False)
        _p(P, f"stop_pin_{tag}", "PUR-DP2.5", T.stop_pin(s), "SS304", "purchased", "rail", "2.5 mm dowel: rod forward stop" + (" and front switch actuator" if s == 1 else ""))
        _p(P, f"bail_clip_{tag}", "RR-HD-S-404", T.bail_clip(s, travel), "SS304", "fab", "rail", "bail capture clip (0.5 mm), riveted to the bar")
    _p(P, "bail", "RR-HD-S-403", T.bail(travel)[0], "SS304", "fab", "rail", "anti-racking bail, 2.5 mm spring wire, 19 mm arms")
    for y, tag in zip(H.BAIL_BLOCK_Y, ("C", "L", "R")):
        _p(P, f"bail_block_{tag}", f"RR-HD-{X}-405", T.bail_block(y), "PA-CF" if printed_frame else "POM", "printed" if printed_frame else "fab", "rail",
           "bail bearing block (centre block = front splice of the halves and cradle foot pad)")
    b, pl = T.front_switch()
    _p(P, "sw_front", "PUR-D2HW", b.fuse(pl), "MIXED", "purchased", "switch", "Omron D2HW-C201M, front zone (in the bay, pin actuated)", mass_g=4.0)
    _p(P, "sw_front_saddle", f"RR-HD-{X}-421", T.switch_saddle(H.SHOE_Y, 0, H.Z_SPR1 + 9.0), "PA-CF" if printed_frame else "POM", "printed" if printed_frame else "fab", "switch",
       "switch saddle (shim-adjustable trip point)", allow={"sw_front"})
    b, pl = T.lid_switch()
    _p(P, "sw_lid", "PUR-D2HW", b.fuse(pl), "MIXED", "purchased", "switch", "Omron D2HW-C201M, lid interlock (J2201)", mass_g=4.0)
    _p(P, "sw_lid_saddle", f"RR-HD-{X}-422", T.switch_saddle(H.LID_SW[1], 0, H.Z_SPR1 + 3.85).cut(T.cyl(1.4, 12, (182.5, H.FRONT_NOTCH_Y[1], H.Z_SPR1 - 1))).cut(
           T.box(180.6, 183.9, H.FRONT_NOTCH_Y[1] - 1.4, H.FRONT_NOTCH_Y[1] + 1.4, H.Z_SPR1 - 1, H.Z_SPR1 + 2.6)), "PA-CF" if printed_frame else "POM", "printed" if printed_frame else "fab", "switch",
       "lid switch riser saddle", allow={"sw_lid"})
    # ---------------- side zones
    for s, tag in ((1, "L"), (-1, "R")):
        pn = {3.0: ("RR-HD-S-431", "RR-HD-S-432"), 5.0: ("RR-HD-S-433", "RR-HD-S-434")}[projection][0 if s == 1 else 1]
        _p(P, f"side_rail_{tag}", pn, T.side_rail(s, 0.0, projection), "SS301", "fab", "rail",
           f"side contact rail + wing-tip return + guide tabs (0.8 mm 301 half hard, laser cut, 4 bends), {projection:g} mm projection")
        _p(P, f"guide_pins_{tag}", "PUR-M3x16-SHCS", T.guide_pins(s), "SS304", "purchased", "rail", "3 x M3 guide pins for the 45 deg slots", allow={f"side_rail_{tag}"})
        b, pl = T.side_switch(s)
        _p(P, f"sw_side_{tag}", "PUR-D2HW", b.fuse(pl), "MIXED", "purchased", "switch", "Omron D2HW-C201M, side zone", mass_g=4.0)
    # ---------------- electronics and cables
    if dummy:
        _p(P, "dummy_board", "RR-HD-D-501", T.dummy_board(), "AL6061", "fab", "elec", "dummy board plate 326 x 96 x 2 on the eight standoffs")
        _p(P, "resistor_block", "RR-HD-D-502", T.resistor_block(), "MIXED", "fab", "elec", "terminal block: 1.00 kOhm in the loop, 4.70 kOhm presence, J1/J2 landing", mass_g=12.0)
    else:
        _p(P, "pcb", "EL-RR-HEAD-ACQ", T.pcb(), "FR4", "envelope", "elec", "RR-HEAD-ACQ populated (envelope)", mass_g=145.0)
        for i in range(4):
            _p(P, f"S{i}_shield_can", "RR-HEAD-SHLD-A", T.shield_can(i), "STEEL", "fab", "emi", "lane shield can 36 x 32 x 5, 0.2 mm tin-plated steel", allow={"pcb"})
        for ref, ko in T.microfit_plugs():
            _p(P, f"plug_ko_{ref}", f"EL-KO-{ref}", ko, "MIXED", "envelope", "elec",
               f"keep-out of the mated {ref} Micro-Fit plug over the rear strip (CR-M03 v -8.4..1.5, {H.MICROFIT_H_ALLOW:g} mm IB-19 height; UNVERIFIED plug drawing)", mass_g=0.0)
        _p(P, "plug_ko_J2501", "EL-KO-J2501", T.gh8_plug(), "MIXED", "envelope", "elec", "keep-out of the mated J2501 GH-8 plug (CR-M08, UNVERIFIED housing data)", mass_g=0.0)
        _p(P, "thermal_cutout", "PUR-TCO", T.thermal_cutout(), "MIXED", "purchased", "elec", "bimetal thermal cut-out in series with the heater, on the spreader tab", mass_g=1.5)
        _p(P, "desiccant", "PUR-DES-1G", T.desiccant(), "MIXED", "purchased", "elec", "4 desiccant pouches (about 0.5 g each) + indicator card, front strip between the lid bosses", mass_g=3.0, hard=False)
        _p(P, "ntc", "PUR-NTC-10K", T.ntc(), "MIXED", "purchased", "elec", "10 k NTC ring-lug sensor on the spreader (heater regulation, board J-heater connector)", mass_g=0.5)
    for nm in ("J1", "J2"):
        k = 1 if nm == "J1" else 2
        _p(P, f"boot_{nm}", f"RR-HD-{X}-51{k}", T.boot(nm), "PA-CF" if printed_frame else "PA12-MJF", "printed" if printed_frame else "fab", "cable",
           f"{nm} cable-breakout boot on the lid: jacket clamp + potting, strain relief and clip point (review M6)", mass_g=8.0 if nm == "J1" else 6.0)
        _p(P, f"holster_{nm}", f"RR-HD-{X}-51{k + 2}", T.holster(nm), "PA-CF" if printed_frame else "PA12-MJF", "printed" if printed_frame else "fab", "cable",
           f"{nm} plug parking cup on the lid (unmated / docking state)", allow={f"plug_{nm}"})
        c, plug = T.pigtail(nm)
        _p(P, f"pigtail_{nm}", f"PUR-CABLE-{nm}", c, "MIXED", "purchased", "cable", f"{nm} pigtail cable (parked shape; docked route checked against the body)", mass_g=25.0,
           allow={f"boot_{nm}", f"holster_{nm}"})
        _p(P, f"plug_{nm}", "PUR-" + ("M16-8" if nm == "J1" else "M12-8"), plug, "MIXED", "purchased", "cable", f"{nm} cable plug envelope (parked in its holster)",
           mass_g=40.0 if nm == "J1" else 30.0, allow={f"holster_{nm}"})
    _p(P, "vent", "PUR-VENT-M6", T.vent(), "MIXED", "purchased", "seal", "ePTFE breather vent M6 with internal light baffle", mass_g=1.0)
    # ---------------- lumped small items (mass only, at the head centre)
    for nm, pn, shape, desc in T.fastener_heads(build):
        _p(P, nm, pn, shape, "SS304", "purchased", "fastener", desc, mass_g=0.0)
    _p(P, "fasteners_lumped", "-", box(H.ROW_X - 1, H.ROW_X + 1, -1, 1, 60, 62), "MIXED", "purchased", "deck", "screws, inserts, washers, wiring (lumped mass estimate)", mass_g=48.0 if printed_frame else 40.0)
    return P


def dummy_ballast(target_g, parts):
    """Steel ballast thickness per lane so that the dummy matches target mass; returns (t_mm, extra parts)."""
    m0, _ = mass_cg(parts)
    area = (H.CAV_X1 - H.CAV_X0 - 0.4) * (2 * H.CAV_HY - 0.4) - 5 * 3.14159 * 16.0
    spacer_g_per_mm = 0.0
    need = target_g - m0
    # iterate: ballast (steel) + printed spacer above it
    t = 3.0
    for _ in range(6):
        extra = []
        for i in range(4):
            extra.append(Part(f"S{i}_ballast", "RR-HD-D-301", T.ballast(i, t), "STEEL", "fab", "lane", "steel ballast / follower plate", color=COL["aux"]))
            extra.append(Part(f"S{i}_dummy_spacer", "RR-HD-D-302", T.dummy_spacer(i, t), "PETG-CF", "printed", "lane", "printed lane spacer for the dummy", color=COL["lane"]))
            extra.append(Part(f"S{i}_pad", "PUR-PAD", T.lane_parts(i)["pad"][0], "SIL-FOAM", "purchased", "lane", "retention pad", color=COL["lane"], hard=False))
        m, _ = mass_cg(extra)
        err = need - m
        if abs(err) < 0.5:
            break
        t += err / (4 * area * (H.MATERIAL_DENSITY["STEEL"] - 0.35) / 1000.0)
        t = max(1.0, min(t, 15.0))
    return t, extra


def build_dummy(target_g, projection=3.0):
    base = build("dummy", projection)
    t, extra = dummy_ballast(target_g, base)
    return base + extra, t
