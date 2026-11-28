# 02 Printing the prototype body and head (Bambu Lab X1 Carbon)

Nothing has been sliced or printed. The mechanical engineers state in both packages that slicing is done by the owner in Bambu Studio from the exported STEP files. Everything below is either quoted from the files cited or marked "proposed". Evidence classes: bounding-box bed fit and downward-face counts are `tool-checked`; masses and print times are `calculated` estimates (times are a rule of thumb from mass, not slicer figures); material behaviour at -25 C is handbook trend and `UNVERIFIED` for the spools you buy.

**Status 2026-11-28: the body is NOT ready to print for assembly, and the head frame is not released either.** The independent fit review (`docs/reviews/REVIEW_cad_pcb_harness_fit.md`; backlog IB-73, IB-75) found by intersecting fasteners, tools, plugs and cable routes with the STEP files that **neither body can be assembled as modelled**, in both builds: the main board cannot be fastened to the bridge posts, the receiver thermal-break screws collide with the motor pods and lower hull, the ToF carrier does not fit the look-sensor seats, the plate grommets are blocked by the motor cans, the main board cannot be removed through the service cover, and the docked J1/J2 pigtails pass through the hull. Rework is in progress (body engineer) together with a re-orientation of the J1/J2 receptacles, and the head board's front-edge connectors also do not fit (CR-H17), which touches the head frame's lid bosses and front region. The generated part tables (`print_schedule.md`, `plates.yaml`) still describe the pre-rework model. **Therefore this file does not list plate counts or per-part numbers that the rework will change; read them from the generated files after the lead records that the rework is verified.** What can be printed now is in section 4.

The mechanical packages also keep changing for other reasons (grip bar at x = -30, Pause/Stop at (-84, -122), the receiver thermal break of DEC-045, head pigtail boots). Re-export before printing (section 1) and check the part list against the print schedules, because part counts and orientations can change.


## 1. Where the files are

| What | Body (RR-X) | Head (RR-HD-X-000, dummy, cradle) |
|---|---|---|
| Print-orientation STEP (Z up, lowest face on z = 0, bounding-box corner at origin); also STL and 3MF | `mechanical/prototype_x1c/out/step/<part>.step`, `out/stl/`, `out/3mf/` | `mechanical/head/prototype/print/<pn>__<name>.step` (also .stl, .3mf) |
| Plate plan (which parts share a plate, positions, overrides) | `mechanical/prototype_x1c/plates.yaml` (plate count changes with the rework) | `mechanical/head/prototype/plates.yaml` |
| Human-readable schedule (orientation, supports, bounding box, mass, time) | `mechanical/prototype_x1c/print_schedule.md` | `mechanical/head/prototype/print_schedule.md` |
| Rebuild everything | `./mechanical/prototype_x1c/build.sh` (warm cache 4 to 6 min, cold 25 to 30 min on the shared machine) | `mechanical/head/build.sh` (6 to 8 min) |

Sources of truth: slice from the STEP files. Six body parts export STL with open edges (lower_hull_FL, FR, RL, RR and receiver_channel_fitcheck_L, R; `prototype_report.md`, IB-55); the slicer repairs them, so import those from STEP, not STL. The STEP, STL and 3MF output directories are generated and may not be tracked in the repository (IB-56: assemblies above 50 MB are untracked and shipped in the release ZIP); run the build scripts if a directory is missing.

Left and right mirrored parts have their own files; do not mirror one for the other (body). Exception: the head cradle fences print "mirror in the slicer for the right-hand part" (head print schedule).

## 2. Materials per part class

| Class | Body material | Why (as stated) | Source |
|---|---|---|---|
| Skins, covers, cassette, trays, ToF clips, fairings, hull, deck, hump, cowl | ASA | UV stable, tolerates water/detergent, 70 % IPA short contact and dilute hypochlorite, not ketones or esters; glass transition about 100 C so heat-set inserts and a sun-heated trailer are safe | body `print_schedule.md` |
| Load-bearing: motor pods, wheel rims, front bulkhead, hatch frame, cassette handle, cliff pods, dock bracket, coupler carrier, saddle cover | PAHT-CF (PA12 base) | stiffness, creep resistance, strength at -25 C (handbook); carbon-filled so the surface is conductive: not for the cassette or anything touching terminals | same |
| Tyres | TPU 95A | grip when warm; stiffens below about -10 C, glass transition near -30 C: **traction at -20 / -25 C is not assumed** | same |
| Head frame halves, rail inserts, bail blocks, chimney inserts, saddles | PA-CF (PAHT-CF) | notched impact at low temperature (PA12 handbook behaviour, filament maker's cold data not verified); no snap fits from it | head `print_schedule.md` |
| Head window cassettes, lane rings, barrier, transport covers, cradle | PETG-CF | flat lightly loaded wipe-down parts; lower cold impact strength, not used where a rail or latch load passes | same |
| Head cable grommets | TPU 95A | external spool, not through the AMS | head `plates.yaml` |

Filament presets named: Bambu ASA @BBL X1C 0.4 nozzle, Bambu PAHT-CF @BBL X1C, Bambu TPU 95A HF @BBL X1C (body); Bambu PETG-CF, Bambu TPU 95A (head). The head `plates.yaml` says the names are "UNVERIFIED against the installed Bambu Studio version".

## 3. Settings the mechanical engineers state

Only these. Anything not in the table (print speed, temperatures, cooling, flow) is not specified in any source: "not yet defined" (section 9).

| Item | Body | Head | Source |
|---|---|---|---|
| Nozzle, plate | 0.4 mm (hardened), Textured PEI Plate, closed chamber for ASA and PAHT-CF | 0.4 mm, Textured PEI | body `print_schedule.md` heading and General; head `plates.yaml` |
| Layer height | 0.2 mm | 0.2 mm | both |
| ASA | process 0.20 mm Standard; 4 walls; 20 % gyroid; 5 mm outer brim; brim on every part taller than 80 mm or with a contact patch under 25 cm2 | not used (listed fallback for transport covers only) | body `plates.yaml` |
| PAHT-CF | process 0.20 mm Strength; 5 walls; 35 % gyroid; 5 mm brim; glue stick on the textured PEI; print dry (80 C / 8 h) | frame halves: 5 walls, 40 % gyroid (100 % below z 11 and in the ribs), 5 mm outer brim, no supports required (optional tree supports under the 60 mm rear-wall bridges); small parts 3 to 4 walls, 100 % infill | body `plates.yaml`; head `print_schedule.md` |
| TPU | 4 walls, 20 % gyroid, print slow and dry | grommets 3 walls, 100 % | both |
| PETG-CF (head) | n/a | cassettes, lane rings, barrier: 3 walls, 100 %; transport covers 3 walls, 20 % gyroid, supports yes (two short bridges); cradle parts 4 walls, 25 % | head `print_schedule.md` |
| Seam | rear / inside | frame halves: rear wall outside | both |
| Supports | tree (auto) only where the part table says so | frame halves none required; transport covers yes | both |
| Floor insulation plug (RRX-P11) | 15 % gyroid (insulation) | n/a | body part table |
| Head critical surfaces | n/a | first-layer flow / elephant-foot compensation on for the frame halves; ironing on for the cassettes (film land is the top surface); no brim on the cassette lands | head `print_schedule.md` |

Print orientation for every part is in the part tables of the two schedules and is already baked into the exported STEP files. Do not re-orient in the slicer. Notable orientations: body lower-hull pieces print upside-down with the gasket land on the bed (print the tongue first on a 9 mm support raft, or tree supports under the land); head frame halves print with the underside on the bed because that face is the cassette seat and film-plane datum.

Plate plans: the body has 20 plates (large shell pieces one per plate; small parts shelf-packed with 8 mm gaps, avoiding the 18 x 28 mm front-left exclusion corner; re-arrange freely). The head's 13 plates use 8 mm edge margin and the same exclusion corner. Rough body machine time 123 h and printed mass ASA 1510 g (pre-rework figures), PAHT-CF 228 g, TPU 129 g (`calculated`). The head frame halves are each about 79 cm3 (`plates.yaml`).

## 4. Print order and what may be printed now

Proposed (no source orders the prints). Print what de-risks the rest, and nothing that the open rework can invalidate.

**May be printed now (proposed; confirm each item with the lead against IB-73 and IB-75 first):**

1. **First-article coupons** (section 5) in ASA, PAHT-CF, PA-CF, PETG-CF and TPU from the actual spools: insert pull-out (VT-061), cold impact, insert-hole sizes.
2. **Fit-check and process articles that make no claim of being the assembly part**, each labelled "not for assembly": the receiver channel fit-check copies (RRX-P02L/R, they are fit checks only; the datum part is the machined channel, whose mounting now carries the G-10 thermal break and is part of the rework), a motor pod around a real gearmotor (clocking) only as a fit test because IB-73 C2 touches the pods, a wheel rim on a real Pololu #1999 hub and a tyre (hub dimensions VERIFIED; the review does not name the rims or tyres, but the rework can change any part), one D2HW pocket piece.
3. **One head frame half pair as a trial article** (light-tightness, joint gap, warp, cassette seat flatness: head `print_schedule.md` "After printing"), clearly marked as a trial, because the head's lid bosses and front region may change with CR-H17 and the boot/receptacle outcome. This is a proposal; the lead has not said the head frame is releasable.

**Not to be printed for assembly until the rework is verified:** the chassis shells (lower hull, nose cowl, shoulders, decks, hump, tail door), battery tunnel and cassette interfaces that touch the posts, the main-board bridge and CM5 trays, the motor pods and cliff pods, cheek fairings and look-sensor clips (IB-73 C2, C3, C4, M2, M10), the head frame halves for a build, and anything that carries a harness route.

**After the lead releases the models:** body structure and shells in the order of the assembly stages of the regenerated `assembly.md`; tyres last (about 7.5 h each at the rule-of-thumb time; slow and dry); dummy head parts, transport tray parts and head cradle parts at the end.

## 5. First-article coupons

Sources name these tests (`assembly.md`, `STATUS.md` open list, IB-55); the coupon geometries are not defined anywhere: "not yet defined". Proposed in the last column.

| Coupon test | Why | Pass criterion in the sources | Proposed method |
|---|---|---|---|
| Heat-set insert pull-out, one coupon per batch and per material, M3 first (also M2, M2.5, M4) | the grip misuse case uses 600 N, which is `UNVERIFIED` | **VT-061: at least 5 coupons per material and insert type with the installation tool and temperature used for the build, pulled out at room temperature and at -20 C at a stated rate; pull-out of at least 600 N (the design value, UNVERIFIED)**; the body `assembly.md` also states an M3 target of at least 400 N in ASA | proposed: insert at the stated tip temperature into a printed boss of the real hole size (M3: 4.0 mm hole x 5.7 deep), pull with a force gauge or test frame to failure; record peak force and mode; repeat in PAHT-CF at 240 to 250 C |
| Notched impact / drop at -25 C, ASA and PAHT-CF (head PA-CF too) | cold brittleness is handbook trend only | none stated; ASA "falls to roughly half of the +23 C value" (UNVERIFIED) | proposed: same coupon set at +23 C and after soak at -25 C, compare |
| Tyre cold traction (TPU) | not assumed below -10 C | none stated; VT-013 and VT-003 own it | proposed: later, with the robot, in the cold box; do not print for it now |
| Insert hole size check | hole diameters are tight (M2 3.2, M2.5 3.8 body or 3.7 head, M3 4.0, M4 5.6 mm) | none | proposed: print a small plate with the four hole sizes, check with pin gauges |
| Dimensional coupon for joints and bores | head joint, reamed bores 4.3 H9 and 3.0 H8 | head joint gap at most 0.1 mm along the full length when dry-fitted | proposed: print the head frame halves and dry fit |
| Light-tightness of printed wall | pinholes in the 1.5 mm outer wall and 3.25 mm half rib | no pinholes in a dark room over a 1000 lm lamp; contingency black foil tape inside (L20 in `head_report.md`) | quoted from head `print_schedule.md` |

Other first-article items from the body status list (`STATUS.md`) belong to assembly and are in [03_assembly_and_wiring.md](03_assembly_and_wiring.md): grip proof load (VT-002) and cassette latch pull test.

## 6. Inserts

Heat-set inserts go in after printing and before any part is assembled (`assembly.md` general rules): soldering iron with the matching insert tip, ASA 220 to 235 C, PAHT-CF 240 to 250 C (dry the part first), press square to 0.1 mm proud then flatten with a cold flat tip. Head: 230 to 250 C with a flat tip, flush to 0.1 mm below the face, check perpendicularity with a screw. Quantities: body 26 x M2, 4 x M2.5, 94 x M3, 10 x M4; head 38 x M2.5 and 18 x M3 (`hardware_by_subassembly.md` H; head CSV). Screw into inserts: M2 0.15, M2.5 0.3, M3 0.5 to 0.6, M4 1.5, M5 2.5 N m (body); head M2.5 0.35, M3 0.5 N m. The brand is not chosen and the pull-out value is unverified (IB-55).

The head rib screws stay M2.5 into heat-set inserts because the 6.5 mm rib cannot hold an M3 insert next to the lane cavities, a deviation from the M3 minimum rule accepted provisionally (IB-41, head `README.md` open item 5).

## 7. Post-processing

| Step | Source |
|---|---|
| Ream head guide-rod bores to 4.3 H9 and dowel holes to 3.0 H8, then fit inserts | head `print_schedule.md` "Critical surfaces" |
| Head tongue/groove joint: fit two 3 x 6 dowels, dry-fit the halves on a surface plate (underside down), joint gap at most 0.1 mm | head `print_schedule.md`; head `assembly.md` step 1 |
| Slit the TPU grommets with a blade after printing (cable axis vertical) | head print table |
| Light test each frame half; black foil tape inside if pinholes | head `print_schedule.md` |
| Bond tyres on the rim keys (flexible cyanoacrylate or polyurethane adhesive; tyre is also keyed with 8 ribs) | `hardware_by_subassembly.md` C |
| Dry PA-CF and TPU before printing (80 C / 8 h for PA-CF); store dry | both |
| Decontaminable finish: not defined for printed layer lines; see [../service/03_cleaning_and_contamination_control.md](../service/03_cleaning_and_contamination_control.md) | n/a |

## 8. What to measure on each printed part before assembly

The sources give no incoming-inspection list for printed parts. The checks below come from the sources where a number exists, otherwise they are proposals to be confirmed by the mechanical engineers.

| Part (class) | Measure | Expected | Source / status |
|---|---|---|---|
| Every part | bounding box against the schedule, weight against "Mass each" | box within the slicer's accuracy; mass calc. only | proposed; schedule values are calculated |
| Every insert hole | diameter and depth | M2 3.2 x 4.0, M2.5 3.8 x 5.0 (head 3.7), M3 4.0 x 5.7, M4 5.6 x 8.1 mm | `dims.INSERT` (body CSV note); head `plates` |
| Lower hull pieces | flatness of the gasket land (z 61.9) and the sole ring | land continuous across the four pieces, gap at most 0.3 mm with a straight edge (assembled check) | body `assembly.md` stage 2 |
| Receiver channel fit-check copies | slide the 16.00 x 14.00 x 70 mm gauge bar through each channel | printed copy is for fit check only; datum parts are machined | body stage 1; `print_schedule.md` |
| Motor pod | gearmotor seats with the gearbox face on the end wall; both clockings present | fits | body stage 3 |
| Wheel rim, tyre | tyre run-out after assembly less than 0.5 mm radial; both tyre bottoms and the caster wheel on a surface plate within 0.3 mm | stage 3 check | body `assembly.md` |
| Battery tunnel, cassette | empty cassette slides in and out without binding; reversed key rib blocked; coupler halves mate by hand | stage 4 check | body |
| Head frame halves | joint gap at most 0.1 mm dry; underside (cassette seat, film datum) flat; no pinholes | head `print_schedule.md` | head |
| Head window cassettes | film land flat; film plane z 10.00 set by the seat bosses (assembled check E4: 10.00 +-0.30 mm) | head E4 | head `production/README.md` section 9 |
| Rail inserts | smooth bed side outward; print 8 (one spare set) | head print table | head |
| Printed head frame | dimensional change after the first thermal cycle: not defined | not yet defined | no source |

## 9. Open items

| Item | ID | Status |
|---|---|---|
| Slicer settings beyond walls, infill, brim, support (speeds, temperatures, cooling, flow) are not specified | not yet defined | no backlog ID |
| Coupon geometries and test frames for insert pull-out and cold impact | not yet defined | IB-55 (insert value 600 N UNVERIFIED) |
| Insert brand and tip temperatures for the chosen brand | IB-55 | Open |
| Open edges in six body STL exports | IB-55 | Open (use STEP) |
| Pause/Stop moved 10 mm outboard to (-84, -122); depth still UNVERIFIED (50 mm assumed) | IB-65 | Open |
| **Fit review: neither body can be assembled as modelled (main-board fastening, thermal-break screws, ToF seats, grommets, service access, cable routes); rework in progress, with the J1/J2 receptacle re-orientation** | IB-73, IB-75 | Open; no body print is released |
| Head front-edge board connectors do not fit (CR-H17); head frame lid bosses and front fence may change | IB-75 | Open |
| Receiver thermal break (4.00 mm G-10 shim, bushings, split pins) is in the models; clamp creep, spring-washer preload and gap stability are `calculated` only | IB-64, VT-060 | Pending |
| Printed head: no inherent EMI shielding; pigtail and loop geometry decide pickup | IB-67, VT-049 | Open |
| Head board change requests CR-M01..M04 not adopted by head mechanical: head frame geometry (J1 port, rear lid standoffs) may change | IB-52 | Open |
| Printed prototype head has no inherent EMI shielding (EMI fence and cans are metal) | IB-09, IB-23, IB-41 | Open; bench test B11 / VT-041 decides |
| Cold behaviour of printed ASA, PAHT-CF, PETG-CF, TPU, creep of printed parts under preload, tyre traction at -20 / -25 C, caster below -20 C | VT-013, IB-55 | Pending |
| Decontamination of layer lines and TPU | VT-023 | Pending |
| Whether the shared head density values (PA-CF 1.22 in the head `plates.yaml` against PAHT-CF 1.06 in the body `plates.yaml`, same Bambu PAHT-CF filament) matter for the mass estimates | not yet defined | contradiction between the two plates files, reported to the lead |
