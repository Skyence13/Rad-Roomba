"""Generated documents: BOM csv files, print schedule, assembly instructions, production pack, dummy/cradle notes.

Run after checks.py and export.py (python -m mechanical.head.docs). Every number below is read from the model, from
out/checks.json or from prototype/plates.yaml; nothing measured. Supplier part numbers are candidates and carry a
verification column (VERIFIED / PARTIAL / UNVERIFIED).
"""
from __future__ import annotations

import csv
import json
from collections import OrderedDict

import yaml

from . import assembly as A
from . import hp as H
from . import parts as T
from .geom import HERE, OUT

PROTO, PROD, AUX = HERE / "prototype", HERE / "production", HERE / "aux"

# ------------------------------------------------------------------------------------------------ supplier data
# pn -> (candidate supplier part, verification, note). Only items that drive geometry were searched (switch, inserts).
SUPPLIER = {
    "PUR-D2HW": ("Omron D2HW-C201M (pin plunger, M3 screw mount, molded leads), wired NC", "PARTIAL",
                 "FP 11.2 max / OP 10.4 +-0.2 / TTP 9.1 max / MD 0.25 / OF 0.75 N from two secondary datasheet extracts (official Omron PDF not opened); body 13.3 x 5.3 x 7.0 PARTIAL"),
    "PUR-INS-M2.5": ("brass heat-set insert M2.5 x 4 (Ruthex / CNC Kitchen class)", "PARTIAL", "hole dia 3.7 per distributor data (Albany County Fasteners spec sheet); maker's own figure not opened"),
    "PUR-INS-M3": ("brass heat-set insert M3 x 5.7 (Ruthex RX-M3x5.7 class)", "PARTIAL", "hole dia 4.0, min boss dia 6.5 per McMaster 94459A / distributor data; boss modelled 6.6"),
    "PUR-SO-M2.5x2.5": ("PEM SO-M2.5-2.5 class clinch standoff, thru-thread, steel/zinc or aluminium", "UNVERIFIED", "mounting hole 4.2 assumed"),
    "PUR-SO-M3x10.5": ("round female spacer M3 x 10.5, OD 4.5, aluminium (cut from M3 x 11 or special)", "UNVERIFIED", "non-standard length; alternative M3 x 10 + 0.5 shim"),
    "PUR-SO-M3x11": ("round female spacer M3 x 11, OD 4.5, aluminium (Wurth 9701xx / Ettinger class)", "UNVERIFIED", ""),
    "PUR-M16-8": ("binder M16 IP67 8-pole male cable connector, shieldable (series 423 / 723 family)", "PARTIAL", "envelope from mechanical/common/purchased/parts.yaml j1_receptacle"),
    "PUR-M12-8": ("binder M12-A 8-pole male cable connector, shieldable (series 763 family)", "UNVERIFIED", "envelope from parts.yaml j2_receptacle"),
    "PUR-CABLE-J1": ("shielded PUR cable 2 x 18 AWG + 2 x 20 AWG + 4 x 24 AWG, OD 7.5, -40 C flex, 150 mm free length", "UNVERIFIED", "OD drives the grommet bore"),
    "PUR-CABLE-J2": ("shielded PUR cable 4 x 2 x 24 AWG twisted pairs, OD 6.5, -40 C flex, 150 mm free length", "UNVERIFIED", "OD drives the grommet bore"),
    "PUR-VENT-M6": ("ePTFE membrane vent M6 x 0.75, black housing (GORE / Amphenol LTW class)", "UNVERIFIED", ""),
    "PUR-FILM": ("aluminised PET entrance film, areal density per radiometry (TBD by detector physics)", "UNVERIFIED", "die-cut 110 x 81.8 with 4 holes"),
    "PUR-HEATER": ("polyimide heater zone 76 x 96, 7.5 W at 12 V, PSA backed (Minco / Holroyd class)", "UNVERIFIED", "zone size from the model; 4 zones may be one film"),
    "PUR-TCO": ("bimetal thermal cut-out, normally closed, opens 45 C (KSD-01F / Airpax 67F class)", "UNVERIFIED", "in series with HEAD_HTR"),
    "PUR-NTC-10K": ("10 k NTC ring-lug sensor M3 (Vishay / TDK class)", "UNVERIFIED", "regulation input of the board heater controller"),
    "PUR-DES-1G": ("silica gel pouch about 0.5 g, 4 off, + humidity indicator card", "UNVERIFIED", "3.0 cm3 space in the front strip"),
    "PUR-GSK-LID": ("lid gasket die-cut, closed-cell silicone 1.2 mm (prototype black; production conductive Ni/graphite silicone)", "UNVERIFIED", ""),
    "PUR-GSK-CAS": ("cassette gasket die-cut, black closed-cell silicone 0.8 mm", "UNVERIFIED", ""),
    "PUR-GSK-RIB": ("rib light-seal strip 5.4 x 1.0, black closed-cell silicone, PSA", "UNVERIFIED", ""),
    "PUR-GSK-EMI": ("conductive fabric-over-foam strip 2.3 x 1.0, PSA", "UNVERIFIED", ""),
    "PUR-FOAM-LINER": ("closed-cell EPDM / silicone foam liner 0.5 mm, PSA", "UNVERIFIED", ""),
    "PUR-PAD": ("lane retention pad, silicone foam 1.5 mm (1.2 installed) 80 x 100", "UNVERIFIED", ""),
    "PUR-SPR-ROD": ("compression spring 3.6 OD x 32 free, about 0.30 N/mm, stainless", "UNVERIFIED", "catalogue item to select (Lee / Gutekunst class)"),
    "PUR-DP2.5": ("dowel pin 2.5 m6 x 17 / x 14, stainless", "UNVERIFIED", ""),
    "PUR-DP3x40": ("dowel / hinge pin 3 x 40 with two circlips", "UNVERIFIED", ""),
    "PUR-M3x16-SHCS": ("ISO 4762 M3 x 16 A2 (guide pin, shank as pin)", "UNVERIFIED", ""),
}
SCREWS_NOT_MODELLED = [  # (pn, description, qty prototype, qty production)
    ("PUR-M2.5x8-CSK", "ISO 10642 M2.5 x 8 A2: spreader to rib inserts / tapped ribs (flush, under the board)", 10, 10),
    ("PUR-M3x6-CSK", "ISO 10642 M3 x 6 A2: lid standoffs from below the spreader", 17, 17),
    ("PUR-M2.5x8-CSK-C", "ISO 10642 M2.5 x 8 A2: window cassettes (4 each)", 16, 16),
    ("PUR-M2.5x10-PAN", "ISO 7045 M2.5 x 10 A2: bail blocks to the frame front face", 6, 6),
    ("PUR-M2.5x12-PAN", "ISO 7045 M2.5 x 12 A2: switch saddles to the spreader", 4, 4),
    ("PUR-M3x8-SHCS", "ISO 4762 M3 x 8 A2: rail inserts (2 each) and rods to the bar", 10, 10),
    ("PUR-M4x10-SHCS", "ISO 4762 M4 x 10 A2: rear bridge to the T-head ears", 4, 4),
    ("PUR-M3-BONDSEAL", "bonded sealing washer M3 (steel + NBR/silicone, -40 C), under every lid screw", 35, 35),
    ("PUR-M3-ISOWASH", "insulating shoulder washer M3 (PA66 / G10): T-head screws (FRAME isolated from the shoes)", 8, 0),
    ("PUR-INS-M2.5", "heat-set insert M2.5 in the printed frame (ribs 10, rear zone 6, cassettes 16, bail blocks 6)", 38, 0),
    ("PUR-INS-M3", "heat-set insert M3 in the printed lid bosses", 18, 0),
    ("PUR-DOWEL-3x6", "dowel pin 3 x 6 h8, split-joint location", 2, 0),
    ("PUR-RIVET-2.4", "blind rivet 2.4 Al, J1 blister front edge", 2, 2),
    ("PUR-COAX", "SiPM micro-coax pigtail U.FL class, about 60 mm, through the chimney (harness; length per OEM carrier)", 16, 16),
    ("PUR-RTV-BLACK", "black RTV, side-switch lead channel potting (2 x 0.1 ml)", 1, 1),
    ("PUR-EPOXY-COND", "conductive epoxy, J1 blister bead", 1, 1),
]


def _load_checks():
    return json.loads((OUT / "checks.json").read_text())


def bom(build):
    """Rows: pn, description, qty, unit, material, make (printed / machined / sheet / purchased / OEM / other WP), supplier, verification, note."""
    parts = A.build(build)
    rows = OrderedDict()
    for p in parts:
        if p.pn == "-" or p.kind == "envelope" and not p.pn.startswith("OEM"):
            if p.pn != "EL-RR-HEAD-ACQ":
                continue
        n = len(p.shape.Solids()) if p.name.startswith(("lid_standoffs", "board_standoffs", "guide_pins", "desiccant", "rib_gaskets", "fence_gaskets")) else 1
        key = p.pn
        make = {"printed": "printed (X1C)", "fab": "machined / sheet", "purchased": "purchased", "envelope": "other work package"}[p.kind]
        if p.pn.startswith("OEM"):
            make = "OEM optics (RFQ)"
        k = next((k for k in sorted(SUPPLIER, key=len, reverse=True) if p.pn.startswith(k)), None)
        sup, ver, note = SUPPLIER[k] if k else ("", "-" if not p.pn.startswith("PUR") else "UNVERIFIED", "")
        if key not in rows:
            rows[key] = {"pn": p.pn, "description": p.desc, "qty": 0, "unit": "pcs", "material": p.material, "make": make, "supplier_part": sup, "verification": ver, "note": note}
        rows[key]["qty"] += n
    proto = build == "prototype"
    for pn, side in (("RR-HD-S-433", "LH"), ("RR-HD-S-434", "RH")):
        rows[pn] = {"pn": pn, "description": f"VARIANT: side contact rail {side} for the 5 mm projection (strip 15 mm tall, same holes); replaces RR-HD-S-43{1 if side == 'LH' else 2}",
                    "qty": 0, "unit": "pcs (variant)", "material": "SS301", "make": "machined / sheet", "supplier_part": "", "verification": "-", "note": "STEP via assembly.build(projection=5)"}
    for pn, desc, qp, qs in SCREWS_NOT_MODELLED:
        q = qp if proto else qs
        if q:
            sup, ver, note = SUPPLIER.get(pn, ("", "UNVERIFIED", ""))
            rows[pn] = {"pn": pn, "description": desc, "qty": q, "unit": "pcs", "material": "-", "make": "purchased", "supplier_part": sup, "verification": ver, "note": note}
    # sheet parts carry their DXF
    for r in rows.values():
        if r["pn"] in ("RR-HD-S-121", "RR-HD-S-122", "RR-HD-S-123", "RR-HD-S-431", "RR-HD-S-432", "RR-HD-S-433", "RR-HD-S-434", "RR-HEAD-SHLD-A", "RR-HD-X-124", "RR-HD-X-125", "RR-HD-X-126"):
            r["note"] = (r["note"] + "; " if r["note"] else "") + "DXF in " + ("prototype" if proto else "production") + "/dxf"
    return list(rows.values())


def write_bom(path, rows, title):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


# ------------------------------------------------------------------------------------------------ print schedule
COLD = {
    "PA-CF": "PAHT-CF (PA12 base): polyamide 12 is the usual choice for cold-impact parts and keeps a useful notched impact strength well below -20 C "
             "(handbook behaviour of PA12, not tested here; the filament maker's cold data is not verified); carbon fibre lowers elongation, so no snap fits are made from it. Used for every part that carries a rail, latch, screw or insert load.",
    "PETG-CF": "PETG-CF: glass transition about 80 C, but noticeably more notch-sensitive in the cold than PA-CF; only for flat, lightly loaded parts that are "
               "clamped or bonded (cassettes, lane rings, barrier) and for the transport covers, which flex once per use at room temperature.",
    "TPU": "TPU 95A: stays elastic down to about -40 C (its Tg is far below zero), which is what a cable grommet needs in the cold.",
}


def print_schedule(checks):
    from .export import printed_parts
    man = yaml.safe_load((PROTO / "plates.yaml").read_text())
    ov = {r["pn"]: r for r in checks["data"]["printed_parts"]}
    L = ["# Print schedule -- prototype head (Bambu Lab X1 Carbon, stock 256 x 256 x 256 mm)", "",
         "Generated by `mechanical/head/docs.py` from `plates.yaml` and `out/checks.json`. **Not sliced**: the owner imports the print-orientation STEP files "
         "(`prototype/print/*.step`, Z up, part already on z = 0) into Bambu Studio and slices there. Fit and overhangs are tool-checked on the oriented solids "
         "(checks.py); slicer behaviour is not.", "",
         "## Materials and cold-impact reasoning", ""]
    for k, v in COLD.items():
        L.append(f"- **{k}** -- {v}")
    L += ["", "All PA-CF filament is dried (80 C, 8 h) before printing and the parts are stored sealed; the structure calculation uses both the dry and the conditioned modulus.", "",
          "## Plates", "", "| Plate | Parts (qty) | Material | Kit | Fits one plate | Overrides |", "|---|---|---|---|---|---|"]
    for pl in man["plates"]:
        L.append(f"| {pl['id']} | " + ", ".join(f"{p['part']} ({p['qty']})" for p in pl["parts"]) + f" | {pl['material']} | {pl['kit']} | {pl['fits_one_plate']} | "
                 + ", ".join(f"{k} {v}" for k, v in pl["overrides"].items()) + " |")
    L += ["", "## Parts: orientation, supports, settings", "",
          "Downward faces = faces above the bed whose normal points more than 45 deg down in the print orientation (tool-checked count / area; z, span, length of the largest).", "",
          "| Part number | Part | Qty | Material | Plate | Bounding box in print orientation (mm) | Orientation | Downward faces | Supports | Walls / infill |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in printed_parts():
        o = ov.get(r["pn"], {})
        big = "; ".join(f"z {x['z']} span {x['span_mm']} x {x['length_mm']}" for x in o.get("largest_downward_faces", [])[:2])
        L.append(f"| {r['pn']} | {r['name']} | {r['qty']} | {r['material']} | {r['plate']} | {' x '.join(str(v) for v in o.get('bbox_print_mm', []))} | {r['note']} | "
                 f"{o.get('downward_faces', '-')} ({o.get('downward_area_mm2', '-')} mm2){'; ' + big if big else ''} | {r['supports']} | {r['walls']} / {r['infill']} |")
    L += ["", "## Critical surfaces (no support marks, no seam)", "",
          "- Frame halves: the underside (bed face) is the cassette seat and film-plane datum -> first-layer flow / elephant-foot compensation on, no brim on the cassette lands "
          "(5 mm outer brim only); module seat shoulders (z 11.0), rib tops (z 29.4 / 30.0), spreader seat (z 30.0), joint faces (y = 0), lid boss tops (z 43.0). "
          "None of them faces down in print orientation (tool-checked list above), so the slicer never puts support on them. Seam position: rear wall outside.",
          "- Guide-rod bores print as 4.3 mm horizontal holes and are reamed 4.3 H9 after printing; dowel holes reamed 3.0 H8; heat-set inserts after reaming.",
          "- Rail inserts lie on their contact face (smooth bed side outward). Cassettes print flat: the film land is the top surface -> ironing on.", "",
          "## After printing", "",
          "1. Heat-set inserts (M2.5: 38, M3: 18) at 230-250 C with a flat tip, flush to 0.1 below the face; check perpendicularity with a screw.",
          "2. Light test before assembly: each frame half over a 1000 lm lamp in a dark room, look for pinholes in the 1.5 mm outer wall and the 3.25 mm half rib "
          "(contingency: black foil tape inside; L20 in head_report.md).", "3. Dry-fit the halves on the dowels: joint gap <= 0.1 mm along the full length."]
    (PROTO / "print_schedule.md").write_text("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------ assembly instructions
TORQUE = [("M2.5 into heat-set insert (printed)", "0.35 N m", "0.45 N m into tapped 6061"), ("M3 into heat-set insert (printed lid bosses)", "0.5 N m", "0.9 N m into tapped 6061"),
          ("M3 lid screw into aluminium standoff", "0.6 N m", "0.6 N m"), ("M3 low-head into the T-head (aluminium)", "0.9 N m", "0.9 N m"),
          ("M4 bridge to T-head ears", "2.0 N m", "2.0 N m"), ("M2.5 board screws", "0.35 N m", "0.35 N m"), ("cassette M2.5 CSK", "0.3 N m", "0.45 N m")]


def assembly_md(checks):
    d = checks["data"]
    mp, ms = d["mass_prototype"], d["mass_production"]
    t = d["dummy_ballast_mm"]
    rl = d["rails"]["front"]
    tt = "\n".join(f"| {a} | {b} | {c} |" for a, b, c in TORQUE)
    proto = f"""# Assembly -- prototype head RR-HD-X-000 (printed PA-CF frame halves)

Generated by `mechanical/head/docs.py`; images rendered from the model by `drawings.py steps` (`prototype/assembly/`). Parts and quantities:
`prototype/purchased_and_fabricated.csv`. Mass {mp['mass_g']:.0f} g, CG ({', '.join(f'{v:.1f}' for v in mp['cg_mm'])}) mm base_link (calculated).

## Torques and thread rules

| Joint | Prototype | Production |
|---|---|---|
{tt}

Heat-set inserts only in the printed parts (no thread forming in polymer); medium thread-lock on every screw that is not a service screw (service screws:
lid, cassettes, rail inserts). All lid screws carry a bonded sealing washer.

## Sequence

**1. Frame halves, shoes, isolators, rear bridge** -- ![step 1](assembly/step_01.png)
Fit the two 3 x 6 dowels in the left half; slide the tongue into the groove; seat the halves on a surface plate (underside down) and check the joint gap <= 0.1 mm.
Drop each shoe T-head into its pocket with the 0.5 mm G10 isolator on top (FRAME isolated from the shoes, see production/README.md section 4). Rear bridge on
the T-head ears, 4 x M4 x 10.

**2. Side rails, guide pins, side switches; rod springs, guide rods, stop pins** -- ![step 2](assembly/step_02.png)
Side switches into their pockets (plunger to the rear), leads through the channel, pot the channel with black RTV after the loop test. Rail L-strips onto the
45 deg slots, M3 guide pins from the top (trapped later by the spreader). Grease the rod bores; spring, rod, stop pin. Set the side-zone adjusting screw to a
0.40 +- 0.15 mm plunger preset (feeler on the plunger).

**3. Lane kits** -- ![step 3](assembly/step_03.png)
Per lane, from below upward: floor assembly on the 0.5 mm seat shoulder, lower ring, barrier plate, upper ring, reference assembly; SiPM carriers into the
chimney, chimney insert (fingers onto the carriers), coax up through the insert channel. Stack-height check with the depth gauge: reference top z 28.5
(shims 0.25 / 0.5 / 1.0 under the pad, see head_report.md section 8).

**4. Spreader** -- ![step 4](assembly/step_04.png)
Heater zones, pads and rib gasket strips are bonded to the spreader underside beforehand; thermal cut-out and NTC on the top. Tilt the spreader in with its front
edge under the frame lip, lower it, then: 10 x M2.5 CSK into the rib inserts, 6 x M2.5 pan into the rear-zone inserts (they also clamp the EMI comb foot -- fit
the comb first in step 5 order if preferred), 8 x M3 low-head with insulating shoulder washers into the T-heads. Lid standoffs from below with M3 x 6 CSK
(11 x 10.5 mm on fence feet, 6 x 11 mm in the chimney zones). Board standoffs are clinched in the spreader.

**5. EMI fences, board, shield cans, switches, cables** -- ![step 5](assembly/step_05.png)
Rear comb (liners into the chimneys around the coax), side and front fences; their feet are clamped by the standoffs and screws (bond points <= 50 mm,
tool-checked). Front-switch saddle (shim the trip point: see section "Checks"), lid-switch saddle. Board on the eight standoffs (8 x M2.5 with serrated
washers = FRAME bond), lane shield cans clipped on, coax to the board rear edge (bend radius >= 6 mm). J1 / J2 pigtails through the split grommets into
the U-slots, internal cable clamp, landing on the board. Desiccant pouches into the front strip, indicator card visible.

**6. Lid** -- ![step 6](assembly/step_06.png)
Lid gasket on the wall top land, liner under the lid. 35 x M3 button head + bonded washer: 17 into the standoffs, 18 into the wall bosses; tighten from the
centre outward. Blister (J1 landing clearance) is clamped by three of the rear screws and riveted at the front. Keeper plate swings down over the lid (its
hole clears the screw at (77.5, 0)), hinge pin with circlips.

**7. Window cassettes (underside)** -- ![step 7](assembly/step_07.png)
Film bonded to the cassette land beforehand (transfer adhesive, no wrinkle; pinhole check over a light box). Cassette gasket on the frame underside, cassette
with 4 x M2.5 CSK; the hard seat bosses set the film plane (z 10.00). A cassette is changed without opening the head.

**8. Leading rail** -- ![step 8](assembly/step_08.png)
Bail into the three bearing blocks, blocks onto the frame front face (6 x M2.5), bar onto the two rod ends (2 x M3), bail clips riveted to the bar, inserts
with the "3 DOWN" edge marking for 7 mm floor clearance (flip for 5 mm). Side strips: RR-HD-S-431/432 (3 mm) or RR-HD-S-433/434 (5 mm), same holes.

**9. Transport cover** -- ![step 9](assembly/step_09.png)
One clip-on cover per half: hook the front lip over the rail insert, swing up, snap the bridge over the shoe behind the x-stop shoulder. The rests touch the
cassette borders only (tool-checked clear of films, shoulders and wing returns).

Overview: ![top](assembly/overview_top.png) ![underside](assembly/overview_underside.png)

## Checks at the end of assembly (prototype)

1. Rail: push the bar with a force gauge: trip at <= 2.0 mm (calculated {rl['trip_travel_mm']['nominal']:.2f} nominal / {rl['trip_travel_mm']['max (unshimmed, PT max)']:.2f} max),
   continue to the stop: >= 15 mm after trip (calculated {rl['post_trip_stroke_mm']:.1f}); return force {rl['spring_force_N']['rest (both)']:.1f} N at rest. Shim the saddle (0.1 / 0.2 mm) if the trip is late.
2. Side zones: trip before the stop at 0.95 mm lateral (feeler + loop meter).
3. HEAD_LOOP across J1 pins 5/6: 1.00 kOhm +-1 %, open when any zone is pressed; PRES_ID 4.70 kOhm pin 7 to 2.
4. Standoff height / film plane: on the bench cradle, gap gauge at the four outer window corners 10.00 +- 0.30 (prototype trimmed with the 0.40 / 0.50 / 0.60 isolator).
5. Dark-count light-tightness test (production/README.md section 6, test E1) before the first source run.
"""
    (PROTO / "assembly.md").write_text(proto)
    prod = f"""# Assembly -- production head RR-HD-P-000 (CNC 6061 frame)

Generated by `mechanical/head/docs.py`; images from `drawings.py steps_production` (`production/assembly/`). Parts: `production/bom_production.csv`.
Mass {ms['mass_g']:.0f} g, CG ({', '.join(f'{v:.1f}' for v in ms['cg_mm'])}) mm (calculated). Same sequence as the prototype (`prototype/assembly.md`) with these differences:
one-piece frame (no dowels, no tongue), 0.5 mm aluminium bond shims instead of the G10 isolators, no EMI fences (the black-anodised frame with masked bond lands
is the enclosure), tapped threads instead of inserts, MJF PA12 lane parts, POM rail inserts and bail blocks, moulded silicone grommets, conductive lid gasket.

## Torques

| Joint | Prototype | Production |
|---|---|---|
{tt}

## Sequence

1. ![step 1](assembly/step_01.png) Frame on the fixture (shoe datums A/B/C); shoes with bond shims, rear bridge (M4 2.0 N m).
2. ![step 2](assembly/step_02.png) Side rails, guide pins, side switches (preset 0.40 mm), rods, springs, stop pins.
3. ![step 3](assembly/step_03.png) Lane kits from above; stack-height check.
4. ![step 4](assembly/step_04.png) Spreader (heater, pads, rib gaskets bonded), standoffs (11 mm), board, cans, switches, grommets, desiccant, cut-out, NTC.
5. ![step 5](assembly/step_05.png) Lid with conductive gasket, 35 x M3 + bonded washers (18 into tapped frame bosses), blister, keeper.
6. ![step 6](assembly/step_06.png) Cassettes (CNC 6061, black anodise) and leading rail.

Overview: ![production](assembly/overview.png)

End-of-line tests: `production/README.md` section 6.
"""
    (PROD / "assembly.md").write_text(prod)
    aux = f"""# Dummy head, bench cradle and gap gauges

Generated by `mechanical/head/docs.py`. STEP: `aux/RR-HD-D-000_dummy_head_assembly.step`, `aux/RR-HD-C-600_bench_cradle_with_head.step`, parts in `aux/step/`.

## Dummy head RR-HD-D-000 (BOM W34)

![dummy](dummy_head_lid_off.png)

- Same printed frame halves, shoes, bridge, keeper, rails, switches, lid and cassettes as the prototype (identical receiver: shoes, x-stop shoulders, latch keeper,
  flat left shoe tip that actuates HEAD_DOCK). No optics, no board, no fences.
- Mass / CG: steel ballast plate {t:.2f} mm per lane on the module seat (RR-HD-D-301) + printed spacer (RR-HD-D-302) that the standard pad clamps;
  aluminium plate RR-HD-D-501 on the eight board standoffs. Calculated: {d['mass_dummy']['mass_g']:.0f} g vs prototype {mp['mass_g']:.0f} g, CG offset within the
  check limits (head_report.md, check "dummy head mass and CG"). Re-solve the ballast thickness from the measured mass of the real modules (checks.py does it).
- Electrical: resistor block RR-HD-D-502 on the plate: HEAD_LOOP through the three real rail switches + 1.00 kOhm 1 % (J1 5/6), PRES_ID 4.70 kOhm 1 % pin 7 to 2,
  J2 pin 7 linked to pin 4 in the plug; same J1 / J2 pigtails and glands as the head. It therefore exercises dock, latch, loop and presence logic without optics.
- The five 8 mm holes per lane in ballast and spacer (centre and +-40 / +-30 mm) are the mounting positions for the gap followers of
  `mechanical/common/out/gap_measurement_method.md` (follower hardware belongs to the measurement equipment, not modelled here).

## Bench cradle RR-HD-C-600

![cradle](../prototype/assembly/cradle.png)

- Deck RR-HD-C-601: 6 mm cast tooling plate; its top face is the "floor" (z 0). Two shoe saddles with 8 mm lands at x 8 and 62 at z 16.00 (datum C),
  side guides (datum B) and x-stop faces at x 65.7 (datum A), as the body receiver; front post pad at z 23.20 under the centre bail block as third support.
  The head therefore sits with its film plane at 10.00 mm above the deck (tolerance stack: head_report.md section 7).
- Four 50.6 x 3.2 pockets at the lane centres take a 50.8 mm check source flush with the deck top -> **10.00 mm source-to-film**, repeatable to the
  head's own stack (+-{d['tolerance_stack']['prototype']['rss_pm_mm']:.2f} RSS prototype). The source slide RR-HD-C-609 gives a 7.0 mm position.
- Fences keep hands off the window zone and carry the slide stop; cable rests hold the pigtails and plugs off the bench. The films never touch the cradle.

## Gap gauges RR-HD-G-70x

10.00 mm setting block (followers zeroed at the film plane), stepped go/no-go wedges 4..10 and 10..16 mm in 0.5 mm steps, 1.5 / 3 / 5 mm ground shims
(floor-feature simulation), all per gap_measurement_method.md section 2.
"""
    (AUX / "README.md").write_text(aux)


def run():
    checks = _load_checks()
    n1 = write_bom(PROTO / "purchased_and_fabricated.csv", bom("prototype"), "prototype")
    n2 = write_bom(PROD / "bom_production.csv", bom("production"), "production")
    print_schedule(checks)
    assembly_md(checks)
    print(f"== docs: BOM rows prototype {n1}, production {n2}; print_schedule.md, assembly.md x2, aux/README.md")


if __name__ == "__main__":
    run()
