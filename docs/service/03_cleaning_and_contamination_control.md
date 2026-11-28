# 03 Cleaning and contamination control

**Status.** No cleaning or decontamination trial has been done (VT-023 is pending, RQ-033 "evidence pending"). What follows is what the design documents say about materials, seals and access, plus proposed practice marked as such. **Every statement about radiological handling needs the site's contamination-control procedure; statements that need it are marked [SITE].** The robot's purpose is to survey for alpha/beta surface contamination, so it will be contaminated by the work it does; the design must be cleanable, and the 0.3 baseline lists "clean and check the robot, head, wheels and handling tray" as the last step of the survey sequence (`docs/Rad_Roomba_Design.pdf` chapter 02, step 6).

**Updated 2026-11-28:** the printed prototype body is not released for assembly until the fit-review rework is verified (IB-73), so the features below are as modelled and may change (service access, grommets, J1/J2 receptacle orientation, pigtail routes). New features since the first version that affect cleaning: the receiver shims (4.00 mm G-10 with bushings and split pins, a crevice at each channel), the potted pigtail boots on the head lid rear strip and the parked-plug holsters (IB-75), the production body's SLS PA11 skins and cast PU 85A tyres (IB-68; cold and decontamination properties UNVERIFIED, VT-073), and the motor-terminal suppression capacitors and can straps inside the lower hull (harness section 7). Evidence classes as in `docs/build/README.md`.

## 1. What the printed prototype can and cannot be

| Surface | Material | What the sources say | Decontamination expectation |
|---|---|---|---|
| Body skins, covers, cassette, trays, fairings | ASA | Tolerates water/detergent, 70 % IPA short contact and dilute hypochlorite; **not ketones or esters** (`mechanical/prototype_x1c/print_schedule.md`) | Smooth outer faces can be wiped. **Layer lines, seams and the texture of the print are not shown to be decontaminable; no source tests it** (VT-023). Treat the printed surfaces as potentially retaining contamination: proposed. |
| Load-bearing printed parts (motor pods, wheel rims, bulkhead, hatch frame, saddle cover) | PAHT-CF | Carbon-filled, electrically conductive surface; low moisture uptake | Same layer-line caveat. Chemical compatibility with decontamination agents not stated. |
| Tyres | TPU 95A (printed) | stiffens in the cold; keyed to the rim and bonded | A printed TPU tyre has layer texture and a 4-wall, 20 % gyroid structure; it is the surface that touches the contaminated floor and the least cleanable surface. **Treat the tyres and the caster as the first items to be considered consumable or replaceable** (proposed). |
| Head frame, rails, cassettes, covers | PA-CF, PETG-CF | PETG-CF "good chemical resistance to decontamination wipes" (head `plates.yaml`); PA-CF compatibility not stated | printed prototype only; the production head is machined aluminium and MJF PA12 with a wipeable splash lip |
| Receiver thermal-break shims and the head shoes | G-10 (not a wiping material for fluids; G-10 data UNVERIFIED) and isolators RR-HD-S-113 | an insulating joint with bushings; wiped from the outside only | liquid in the joint is a thermal and an electrical path (frame isolation at least 10 Mohm unmated, E7): re-measure E7 after any wet cleaning near the shoes (proposed) |
| Head leading rail | printed rail inserts, flip 3 mm / 5 mm projection | reversible wear inserts, print 8 (one spare set) | replaceable: the rail inserts are the head's sacrificial contact surface |
| Machined aluminium parts (plate, channels, bar), stainless fasteners | 6061, 5052, 304 | cleanable metal | still behind joints and under gaskets |
| Window | aluminised PET entrance film on a removable cassette | the film is part of the response (areal density "per radiometry"); changing it changes the calibration | see section 3 |

Production intends metal and MJF parts (DEC-033). The printed prototype is a development article: **do not take the printed prototype into a contaminated area until the site agrees a plan for its disposal or restricted release** (proposed, [SITE]).

## 2. Wetted surfaces, seals and openings: what water and wipes can reach

| Feature | Where | What it means for cleaning |
|---|---|---|
| Perimeter gasket (closed-cell silicone foam 4 x 2.5 mm, -40 C) on the lower land; flat gasket sheet at flange joints, hump curb, hull splice, bulkhead/nose; cover gasket 6 x 2 mm on the saddle cover ledge; hatch gasket 3 x 2 mm | body | fitted dry, butt joints scarfed and glued; gaskets are **not** shown to be water-tight under pressure; `UNVERIFIED` supplier items (`hardware_by_subassembly.md` J) |
| Neutral-cure RTV along the plate edge, floor plug, pod notches, cheek slots; O-ring cord in the motor pod notches | body | seals are adhesive; a failed bead is a leak path |
| ePTFE membrane vent M12, one in the lower hull rear right quarter; M6 vent in the head rear wall beside J2 | body, head | **vents breathe: do not spray, soak or jet them**; a wetted membrane is blocked; a contaminated vent cannot be cleaned and is replaced |
| Duck-bill drain valves, 3 mm holes beside the caster bracket (2) | body | liquid can leave; keep them clear; they are an opening into the lower hull if the valve is damaged |
| J1 (M16) and J2 (M12 A-coded) receptacles | nose | IP67 **when mated** (contract); unmated receptacles and the pigtail plugs are not sealed; cap or keep mated while cleaning |
| Charge inlet under a hinged cover with an O-ring sealed cover switch | top | keep the cover closed; opening the cover opens the traction chain |
| LiDAR on the hump (gasket and cable gland) | top | IP65 device (recalled; scan-plane height and gland unverified) |
| Head lid gasket (silicone, 1.2 mm to 0.8 mm installed), cassette gaskets, rib light-seal strips, jacket foam caps and bands | head | the light-tight volume; **any liquid entering is a failure of light tightness and of the board** (SiPM bias up to 62.5 V, HV creepage when damp is the concern: `head_afe_budget.md` section 10); the external jacket is wipeable-skin foam, PSA-bonded |
| Entrance film and cassette | head underside | the film is the detector window; it is thin and fragile; see section 3 |
| Tyre-to-head clearance 17 mm; splash lip on the wing rear faces; debris deflector ahead of each tyre | body, head | designed to keep tyre debris away from the window |

An ingress-protection rating for the complete robot is **not defined**. Cleaning with wipes and damp cloths is the assumption; no source supports hose-down, steam, immersion or pressure washing, and one of the open items of RQ-033 is the proof of cleanability and ingress (VT-023).

## 3. Head window protection and replacement

- **Protection during handling and transport:** clip-on transport covers (one per frame half) protect the downward window; the transport tray has head guards and an EVA foam pad "clean, soft surface 7 mm below the rails". Fit the cover before lifting the head; use a site-designated handling surface (`mechanical/head/prototype/assembly.md` step 9; `head_icd.md` section 2).
- **Window design:** the entrance film is bonded to a removable cassette (4 x M2.5 CSK per cassette) with three guard webs under it; the leading rail (3 mm or 5 mm below the film plane) takes the floor contact. A cassette is changed from below with the head on the bench cradle or a transport cover **without opening the head** (head `production/README.md` section 8).
- **Replacement procedure (head source):** bond the film to the cassette land beforehand (transfer adhesive, no wrinkle; pinhole check over a light box); gasket on the frame underside; cassette with 4 x M2.5 CSK (0.3 N m prototype); the hard seat bosses set the film plane at z 10.00. **After any cassette or film change: end-of-line test E1 (dark-count light tightness) and E4 (standoff and film plane, 10.00 +-0.30 mm), and a service-ID entry** (`production/README.md` sections 8 and 9). Opening the lid, spreader or a cassette invalidates light tightness until E1 is repeated.
- **Calibration consequence:** a different film or a change of the window changes the response; "recheck response and window integrity after contact or damage and qualify affected data using the site procedure" (checklist "Recovery, battery and disposition"); a head swap or cassette change records a calibration change (VT-009). The source-response check (see 02) after a window change does not by itself restore a calibration.
- **Damage assessment:** pinholes in the film let light into the lane (a dark-count rise); a punctured window also exposes the ZnS(Ag) screen. Cleaning the film itself is not defined: do not rub it (it is thin aluminised PET); the sources give no cleaning method for the film and the approach is "not yet defined" ([SITE] and the optics supplier's guidance, RFQ section on windows and guards: "replacement method").

## 4. Wipe-down (proposed, within the stated material compatibility)

1. Stop and inhibit the robot (E-stop or selector), unplug the charger, close the inlet cover. Selector OFF is a functional switch-off, not isolation: for work near terminals remove the pack (see 01 section 9).
2. Wipe outer ASA and PETG-CF surfaces with water and detergent or 70 % IPA (short contact), or dilute hypochlorite where the site requires it; **never ketones or esters** on ASA. Wipe from clean toward dirty, from top to bottom, wheels and underside last. Do not saturate: keep liquid out of vents, drains, unmated connectors, the inlet and the LiDAR gland.
3. Wheels, tyres, caster and the front edge: remove debris, wipe; inspect for embedded material in the tread and layer lines.
4. Inspect gaskets, seams and fasteners for lifted edges; note anything that looks wet inside.
5. Dry. Monitor the wipes or the surface with the site's instruments per its procedure. Concentrations, instruments, action levels: [SITE].
6. Bag and segregate contaminated wipes per the site.

## 5. Handling a contaminated robot

- The robot weighs at most 12 kg and has an integral grip (`docs/architecture/SYSTEM_ARCHITECTURE.md` section 6; carry attitude target pending, IB-10). Carry it by the grip with the head covered; set it on the handling tray (wheels into the chocks, caster into the cup, head guards on, straps over saddle and hump).
- **Drive inhibited before lifting**; confirm the charger is unplugged; do not lift with the head's rail or window as a hold.
- A pack that has been in a contaminated robot is capped, segregated and handled as the site prescribes; the pack shipping documentation (UN 38.3) is an open item.
- Opening the robot (saddle cover, lid, head lid, spreader) in a contaminated state is **not defined**: the saddle cover is removable (9 captive screws); internal surfaces are not wipeable in the printed prototype. [SITE].
- Data: the contamination record, the run, and any flagged areas stay with the original scan; contaminated-robot status is a record, not a calibration event.

## 6. Frisking the robot itself before it leaves a controlled area

No source defines this procedure. Points that follow from the design:

- The robot's own detector head is a floor-looking 80 x 100 mm window at 10 mm standoff; it is **not a frisking probe for the robot and must not be used as one**: it is the contaminated object, it has no calibration for that geometry, and a pass of the survey software is not a release (the 0.3 design: "a release-status entry in a site system is an RP decision under the applicable procedure"). Proposed: use the site's hand instruments and wipe counting.
- Areas to frisk: tyres and caster, the front edge and rail inserts, the head window and cassette frame, the underside (sole, skids, grille), gaps at the head receiver, the transport tray, handles and the grip, the charge cover. Also removed packs and cassettes.
- Wipes and direct counts, thresholds, who signs, how the result is recorded: [SITE].
- After frisking, restore the robot to a clean state for the next use only after the site accepts it; keep the contamination record with the serial.

## 7. Open items

| Item | ID | Status |
|---|---|---|
| Cleanability of printed layer lines and TPU tyres; effect of decontamination agents on PAHT-CF, PA-CF | VT-023, RQ-033 | pending; no source |
| Ingress rating of the robot and head; cleaning method limits (wipe only?) | VT-023 | not yet defined |
| Method of cleaning or protecting the entrance film; replacement frequency | RFQ 0.4 "Window and guard"; VT-023 | not yet defined |
| Disposal or restricted release of the printed prototype after use | [SITE] | not yet defined |
| Frisking procedure, instruments, action levels | [SITE] | not yet defined |
| Opening the robot while contaminated | [SITE] | not yet defined |
| Effect of cleaning on the calibration (window change, tyre change) | VT-016, VT-023 | not yet defined |
| Retrieval and contamination control of a robot stopped in a trailer | DEC-004, RSK-012 | site |
| Production body materials (SLS PA11, cast PU 85A) cleanability and cold behaviour | IB-68, VT-073 | UNVERIFIED |
| Pigtail boots, holsters and docked pigtails: cleaning and the plug parking | IB-75 | open |
| Re-measure the head frame isolation (E7) and heater-circuit insulation (W-103.HTR-ISO) after wet cleaning, light tightness (E1) after anything that wets the head | `harness/cables.md` section 8; head `production/README.md` | proposed |
