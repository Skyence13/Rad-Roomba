# rrkicad — scripted, headless KiCad 9 flow

One Python **board definition** (`electronics/<board>/board.py`) is the single source of
truth. From it the tool generates a native KiCad 9 project (schematic, PCB, project
file), autoroutes it, runs ERC/DRC and writes all fabrication / documentation outputs.
Nothing needs a GUI or network access; KiCad and Freerouting run in Docker.

```
python3 tools/eda/rrkicad.py build electronics/<board>/board.py   # everything
python3 tools/eda/rrkicad.py build .../board.py --no-route        # generate + check, no autorouter
python3 tools/eda/rrkicad.py build .../board.py --reroute         # ignore the cached route
python3 tools/eda/rrkicad.py sch   .../board.py                   # schematic + ERC + PDF only (fast)
python3 tools/eda/rrkicad.py check .../board.py                   # re-run ERC/DRC on the existing files
```
Options for `build`: `--passes N --threads N --timeout SEC` (override the definition's
autorouter settings), `--budget SEC` (wall-clock budget for all autorouter runs, see
"Long routing jobs"). Exit code 0 = pass, 1 = checks failed, 2 = definition error.

Requirements on the host: `python3`, `docker`, images `kicad/kicad:9.0` and
`ghcr.io/freerouting/freerouting:latest` (tested: KiCad 9.0.9, Freerouting 2.6.0).
Wrappers (use them for anything ad hoc, they handle mounts, uid and HOME):
`tools/docker/kicad.sh <cmd...>` and `tools/docker/freerouting.sh in.dsn out.ses [passes] [threads]`.
Both mount the repository at the same absolute path, run as the calling uid with
`--network none`, and work only on files inside the repository.

## What happens in a build

| step | where | what |
|---|---|---|
| 1 `_gen` | KiCad container | evaluate `board.py`; resolve symbols; write `.kicad_pro`, `sym-lib-table`, `fp-lib-table`, `rr_local.kicad_sym`, `rr_local.pretty/`, root + one `.kicad_sch` per group; export the KiCad netlist from the generated schematic and **cross-check it pin-by-pin against the definition**; build the unrouted `.kicad_pcb` with pcbnew (pad nets come from that netlist); auto-arrange unplaced parts; copy replicated blocks; plane fan-out vias; export `route/<name>.dsn` (with 25 um extra clearance and edge keep-outs for the autorouter) |
| 2 route | Freerouting container | `route/<name>.dsn` → `route/<name>.ses` (+ `freerouting.log`, `route_meta.json`). Skipped when the DSN hash is unchanged and a SES exists (so reruns are deterministic); `--reroute` forces it |
| 3 `_post` | KiCad container | import SES into the pristine generated board (separate process), verify pre-routes are untouched, replay `route/finish.json`, widen tracks the router necked below the fab minimum, remove dangling stubs (and unused escape vias on a fully connected board), fill zones, add fab notes/dimensions, save; ERC; DRC with schematic parity; outputs; `reports/summary.json`, `reports/open_connections.txt` |
| 4 continue / restart | both | only while connections are open: continue runs from the routed board, fresh restarts with other seeds, optionally within `--budget` (quick imports in between, best SES kept; see "Completion strategy" and "Long routing jobs") |
| 5 finisher | KiCad container | only while connections are still open: maze router with rip-up, then step 3 again |

Files per board directory:
```
board.py                       the definition (edit this, nothing else)
<name>.kicad_pro/.kicad_sch/.kicad_pcb, <group>.kicad_sch, rr_local.*, *-lib-table, 3d/   generated KiCad project
route/      <name>.dsn, <name>.ses (routing result = cache key + source of the tracks), freerouting.log,
            route_meta.json, progress.log (one JSON line per autorouter run), finish.json (finisher
            result), blocks.json (replicate), escape_vias.json (intermediate)
reports/    erc.json/.rpt, drc.json/.rpt, summary.json, placement.txt, build_state.json
out/        <name>-schematic.pdf, gerber/ (Gerbers, Excellon PTH/NPTH, drill maps, .gbrjob),
            <name>-pos.csv, <name>-bom.csv, <name>-fab.pdf, <name>-assembly-top/bottom.pdf,
            <name>-copper.pdf, <name>.step, <name>-render-top/bottom.png, pinmap.json, <name>.net
```
`reports/summary.json`: `status` (`pass`/`fail`), `fail_reasons`, ERC/DRC error/warning
counts by type, `unconnected`, `parity`, `unrouted_nets`, every waiver with its
justification and match count, auto-added `pwr_flags`, `single_pin_nets`, BOM lines
missing an MPN or flagged `verify`, routing statistics, and the output list.
**Fail** = any ERC error, DRC error, unconnected item or schematic-parity item that is
not waived. Warnings never fail the build but are counted.

`out/pinmap.json`: for every part pin: `pin`, `name`, `net` (null = no-connect), `type`,
`pad_xy_mm` (board frame) and `side`; plus a `nets` → `["REF.pin"]` index.

## Conventions

* Units: mm. **Board frame: X right, Y up**, origin = the point you define the outline
  against; it becomes the KiCad drill/place (aux) origin and grid origin, so
  `board.py`, the pick-and-place file, the STEP model and `pinmap.json` share coordinates.
* `at=(x, y, rot, side)`: `rot` is the KiCad footprint orientation in degrees (CCW
  positive), `side` `"F"` or `"B"`. For bottom parts it is the value KiCad shows for the
  flipped footprint — check the result in `pinmap.json` (`pad_xy_mm`) rather than guessing
  (e.g. the JST GH on RR-TOF-A needed `rot=180` on the bottom to face the edge).
* Net names are global: the same string anywhere is the same net. PCB net names equal
  the names in `board.py`.
* Schematic style: one A3 sheet per group (extra sheets are added automatically when a
  group overflows). Every used pin has a short stub ending in a global label, or a power
  symbol for nets declared with `board.rail()`. Unused pins get no-connect flags. Nets
  that have power-input pins but no power-output pin get a `PWR_FLAG` on the root sheet
  (listed in the summary as `pwr_flags`).
* Reference designators are yours to assign; they must be unique.
* Every symbol pin must be either in `pins`, in `nc`, of type no_connect, or the part
  must say `unused="nc"`; otherwise the build stops and lists the pins.

## Board definition by example

```python
from rrkicad import Board, Pad, SymPin, Rules

board = Board("RR-XYZ-A", title="Example board", rev="A", date="2026-11-25", docnum="RR-EL-0123",
              company="Rad Roomba", layers=4,          # 2, 4 or 6:
                                                        #   4 = F.Cu sig / In1 plane / In2 plane / B.Cu sig
                                                        #   6 = F.Cu sig / In1 GND / In2 sig / In3 sig / In4 PWR / B.Cu sig
              thickness=1.6, silk_refs=True,            # False hides all reference designators on silk
              rules=Rules(),                            # fab rules, see "Rules" below
              paper="A3", description="free text shown on the root sheet")

# --- nets ----------------------------------------------------------------------
board.rail("+5V", "+3V3", "GND")                      # drawn with power symbols (stock power:<name> or generated)
board.netclass("PWR", ["+5V", "+3V3", "GND", "VBAT*"],  # exact names or KiCad wildcards
               track=0.4, clearance=0.2, via_dia=0.8, via_drill=0.4)

# --- parts: one group = one schematic sheet --------------------------------------
g = board.group("mcu", "Microcontroller", notes="Text block printed at the top of the sheet.")
g.part("U1", "MCU_ST_STM32G4:STM32G474RETx", "STM32G474RET6",        # ref, symbol, value
       footprint=None,                      # default: the symbol's Footprint property
       mfr="STMicroelectronics", mpn="STM32G474RET6",
       pins={"VDD": "+3V3", "VSS": "GND",   # key = pin NAME (all pins with that name) ...
             "7": "NRST", "PA0": "ADC0"},   # ... or pin NUMBER (numbers win)
       nc=["PC13"], unused="nc",            # explicit NC pins; unused="nc" marks all remaining pins NC
       at=(50, 40, 0, "F"),                 # omit -> auto-arranged
       notes="BOM note", verify=True,       # verify=True -> "verify: true" in the BOM notes
       dnp=False, bom=True, datasheet="https://...", description="...",
       fields={"Tolerance": "1%"},          # extra symbol/footprint fields
       sch_rot=0,                           # symbol rotation on the sheet (0/90/180/270)
       silk_ref=False,                      # per part: False | True | (x, y[, rot[, size]])
       zone_connect="solid",                # pads of this part: "solid" | "thermal" | "none"
       height=1.6,                          # body height (mm) for the generated 3D envelope, see "3D"
       model=None)                          # or a real model: "${KIPRJMOD}/3d/part.step"
g.C("C1", "100n", "+3V3", "GND", pkg="0402", mfr="Murata", mpn="GRM155R71C104KA88D", near="U1.16")
g.R("R1", "10k", "+3V3", "NRST", mfr="Yageo", mpn="RC0402FR-0710KL")           # pkg default 0402
g.FB("FB1", "600R@100MHz", "+3V3", "VDDA", pkg="0603", mfr="Murata", mpn="BLM18AG601SN1D")
g.L("L1", "10u", "SW", "VOUT", pkg="0805", mfr="...", mpn="...")
g.LED("D1", "green", "LED_A", "GND", pkg="0603", mfr="...", mpn="...")       # anode, cathode
# R/C/L/FB/LED accept every part() keyword (at=, near=, dnp=, ...).  pkg: 0201 0402 0603 0805 1206 1210 2010 2512

# identical blocks: place (or auto-arrange) one block, copy its placement AND routing at an offset
# (see "Replicating blocks" below)
# board.replicate((lane1_group, lane2_group), dx=80.0, dy=0.0)     # groups with the same parts in the same order
# board.replicate({"U1": "U101", "C1": "C101"}, dx=80.0)          # or an explicit {source_ref: destination_ref} map

# auto-arrange hints for parts without at=:
#   near="U1" | near="U1.16" (pad 16 of U1)   edge="left|right|top|bottom"   side="B"   rot=90 (fixed rotation)
# rail-to-rail capacitors without near= are spread over the supply pins of the ICs in their group.

# --- outline, holes, copper ------------------------------------------------------
board.outline_rect(100, 80, radius=2.0, origin="corner")   # origin "corner" (lower-left) or "center"
# board.outline_poly([(x, y), ...], radius=1.0)            # any closed polygon, every corner rounded
board.cutout_rect(50, 76, 12, 3, radius=1.0)               # centre x, y, w, h   (also cutout_circle, cutout_poly)
board.hole("H1", 4, 4, drill=3.2, keepout=7.0)             # NPTH + circular keep-out (tracks/vias/pour/parts)
board.hole("H2", 96, 4, drill=3.2, plated=True, pad=6.0, net="GND")
board.zone("GND", ["In1.Cu"], connect="solid")             # polygon=None -> whole board
board.zone("+3V3", ["In2.Cu"], connect="solid")
board.zone("+5V", ["In2.Cu"], polygon=[(0, 0), (30, 0), (30, 30), (0, 30)], priority=1)  # plane split
board.zone("GND", ["F.Cu", "B.Cu"])                        # pours; options: clearance, min_width,
                                                           # connect thermal|solid|none, thermal_gap/width, islands
board.keepout("KO_ANT", polygon=[(80, 60), (92, 60), (92, 72), (80, 72)],   # or circle=(x, y, dia)
              layers=("*.Cu",), tracks=True, vias=True, copper=True, pads=False, footprints=True)
board.track("XTAL_IN", [(10, 10), (12, 10), (13, 11)], layer="F.Cu", width=0.2)  # pre-route: locked, kept by the router
board.via("GND", 20, 20)                                   # pre-route via (net-class size unless dia=/drill=)
board.text("{name} rev {rev} {date}", 50, 2, layer="F.SilkS", size=1.0)   # also {title} {docnum}; B.* is mirrored
board.fab_note("Controlled impedance not required.")       # extra line on the fabrication drawing

# --- project-local library (parts missing from the stock libraries) -----------------
sym = board.symbol("MYSENSOR", [SymPin(1, "VDD", "power_in", "T"), SymPin(2, "OUT", "output", "R"),
                                SymPin(3, "GND", "power_in", "B"), SymPin(4, "EN", "input", "L")],
                   ref_prefix="U", datasheet="https://...")                  # -> "rr_local:MYSENSOR"
fp = board.footprint("MYSENSOR_LGA4", [Pad(1, -1.0, -0.8, 0.6, 0.9), Pad(2, 1.0, -0.8, 0.6, 0.9),
                                       Pad(3, 1.0, 0.8, 0.6, 0.9), Pad(4, -1.0, 0.8, 0.6, 0.9)],
                     body=(2.0, 1.2))                                        # -> "rr_local:MYSENSOR_LGA4"
g.part("U9", sym, "MYSENSOR", fp, mfr="...", mpn="...", pins={"VDD": "+3V3", "OUT": "S1", "GND": "GND", "EN": "+3V3"})

# --- autorouter / auto-arrange / waivers ---------------------------------------------
board.route(passes=100, threads=None, timeout=None, optimizer=True, enabled=True, extra_args=[],
            plane_fanout=True,     # rrkicad's own track+via beside every SMD pad of plane nets (see Routing notes)
            retries=2,             # extra "continue" autorouter runs while connections are open
            restarts=1,            # then fresh autorouter runs with another item-order seed (best result kept)
            fanout=False,          # Freerouting's own fan-out stage (escape via on every SMD pin; rarely useful)
            escape="auto",         # fine-pitch escape (see Routing notes): "auto" = on for 4/6 layers, True, False
            escape_pitch=0.65,     #   ICs whose pad pitch is below this get escaped ...
            escape_min_pads=16,    #   ... and that have at least this many perimeter pads
            escape_via=None,       #   (dia, drill) of escape vias; default = the fab minimum via of Rules
            escape_track=None,     #   stub width; default Rules.min_track
            escape_layers=None,    #   informational: target layer recorded per via (through vias reach all layers)
            escape_direct=True,    #   short direct pre-route to a nearby two-pad passive instead of a via
            finisher=True,         # built-in maze router for the last open connections (see Routing notes)
            finisher_ripup=True,   #   ... allowed to rip up and reroute autorouter copper of other signal nets
            finisher_seconds=900,  #   ... time budget
            budget=None,           # wall-clock budget (s) for all autorouter runs (also: build --budget SEC)
            chunk=900,             #   with a budget: cap per Freerouting run (each run leaves an SES on disk)
            stall=2,               #   with a budget: stop after this many continue runs without improvement
            zone_nets="auto",      # "auto" = "exclude" on 4/6 layers: nets with a copper zone are never autorouted
            fr_fallback="none")    # Freerouting's own fallback strategies after stagnation (see Routing notes)
# per part: g.part(..., escape=None | True | False)   None = decided by pad pitch, True = force, False = never
board.autoplace_options(clearance=0.3, ic_halo=2.0, edge_margin=0.5, grid=0.25, spread=0.35, rotations=(0, 90, 180, 270),
                        escape_keepaway=2.0)   # free band (mm) around the courtyard of escaped ICs (auto-arranged neighbours)
board.waive("drc", "silk_overlap", "Reference text overlaps on the dense RF corner; assembly uses the Fab layer.",
            match=r"R1[0-9]")                             # regex on the violation text; None = all of that type
board.severity("drc", "silk_over_copper", "ignore", "Silk is clipped by the fab's solder-mask subtraction.")
```
The file must leave the `Board` in a module-level variable named `board`. It is plain
Python evaluated **inside the KiCad container** (Python 3.11): loops, helper functions
and `from rrkicad.symlib import SymbolLibs` (to look at stock symbol pins) are fine.

### Stock libraries
Symbols `Library:Name` and footprints `Library:Name` refer to the KiCad 9 stock
libraries in the container (`/usr/share/kicad/symbols`, `/usr/share/kicad/footprints`).
Unknown names stop the build with close-match suggestions. To browse:
`tools/docker/kicad.sh bash -c 'ls /usr/share/kicad/footprints/Package_SO.pretty | head'`,
or print a symbol's pins:
```
tools/docker/kicad.sh python3 -c "from rrkicad.symlib import SymbolLibs
for p in SymbolLibs().get('Device:R').pins: print(p.number, p.name, p.etype, p.unit)"
```
Multi-unit symbols are placed unit by unit automatically (map their pins by number).
Derived symbols (`extends`) are flattened like KiCad does.

### Local symbols / footprints
* `SymPin(number, name, etype="passive", side="L", unit=1)` — `etype` is a KiCad pin
  type (`input output bidirectional tri_state passive power_in power_out open_collector
  open_emitter no_connect unspecified free`); `side` L/R/T/B, pins are stacked in list
  order at 2.54 mm pitch; several `unit` values make a multi-unit symbol.
* `Pad(number, x, y, w, h=None, shape="roundrect", kind="smd", drill=None, rot=0, rratio=0.25, paste=True)`
  — coordinates in the **footprint editor frame (x right, y DOWN, top view)**; `shape`
  rect/roundrect/circle/oval; `kind` smd/thru/npth. `board.footprint(..., body=(w, h),
  courtyard=(w, h), pin1=True, model="${KIPRJMOD}/3d/x.step")`. Fab outline, courtyard,
  silk lines clear of pads and a pin-1 dot are generated. A footprint without pads (e.g. a
  shield-can outline) is allowed when it has `body=` or `courtyard=`.
* Mounting holes from `board.hole()` are generated footprints in `rr_local.pretty`
  (board-only, no courtyard; the keep-out rule area protects them).
* Generated rail symbols (rails with no stock `power:` symbol) also live in `rr_local.kicad_sym`.

### Rules
`Rules(min_track=0.15, min_clearance=0.15, min_via_dia=0.6, min_via_drill=0.3, min_annular=0.13,
edge_clearance=0.3, min_hole=0.3, min_hole_clearance=0.25, min_hole_to_hole=0.25, track=0.2,
clearance=0.15, via_dia=0.6, via_drill=0.3, min_silk_text=0.8, min_silk_thickness=0.1)` —
written to the project's board setup and the `Default` net class; `netclass()` adds
classes on top (first matching pattern wins).

## Routing notes
* **Plane fan-out (4/6 layers).** For every net that has a zone on a plane layer
  (`In1/In2` on 4 layers, `In1/In4` on 6) the PCB step itself adds a short locked track
  and a via beside each SMD pad of that net (through-hole pads connect to the plane
  directly). The via respects copper clearance, hole-to-hole, edge clearance, cut-outs,
  via keep-outs and other parts' courtyards where possible, and must land inside its
  own net's plane polygon (split planes). Clearances are pairwise (the larger of both net
  classes, like KiCad's DRC); footprint-internal rule areas and copper drawn inside
  footprints (net ties) are obstacles. Exposed/thermal pads get their via in the pad centre.
  **Long fan-out:** a pad with no legal via position beside it is connected by the maze
  router (see Finisher) to the nearest legal via position inside its own plane polygon
  (windows 5 / 12 / 30 mm), as locked pre-route; `summary.json` → `routing.plane_fanout`
  lists them (`long_fanout`) and the pads still without a connection (`failed`, with the
  reason). After zone fill, KiCad's DRC connectivity check is what confirms every plane
  connection (`unconnected` must be 0).
* **Zone nets are not autorouted (4/6 layers, `zone_nets="auto"`).** Every net that has a
  copper zone is moved into a DSN net class `RR_ZONE_<class>` that Freerouting is told to
  ignore (`--router.autorouter.ignore_net_classes`); its pads connect through the plane
  fan-out / long fan-out and the zone fill only. Whatever stays open is left to the finisher
  and reported. On 2-layer boards (`"auto"` = `"route"`) zone nets are routed as tracks and
  the pour is added afterwards (RR-TOF-A, RR-PANEL).
  Split planes must be **non-overlapping polygons** (Freerouting rejects overlapping
  plane areas; do not rely on zone priority for splits).
  If you also pour a plane net on the outer layers, use `connect="solid"` for that pour
  (or leave the outer layers unpoured): thermal spokes next to fan-out tracks get starved.
* **Fine-pitch escape (4/6 layers by default).** Before routing, every IC whose pad pitch is
  below `escape_pitch` (0.65 mm; QFP, QFN, TSSOP-0.5, ...) and has at least
  `escape_min_pads` (16) perimeter pads, or that has `escape=True`, gets
  its pin escapes as locked pre-routes (`rrkicad/escape.py`):
  - signal pads: a short stub (`escape_track`, default `min_track`) out of the pad tip and a
    via on a ring outside the package, alternating between two staggered radii. The ring is
    *fanned*: neighbouring vias are spaced by via radius + half stub + clearance of the two
    nets, so the stub of an outer-row via passes between two inner-row vias with full
    clearance even with 0.6 mm vias at 0.5 mm pitch (the inner radius grows until every
    outer stub clears its neighbours' vias). Pads whose planned spot is blocked get a local
    search over further radii / lateral offsets, then (packages without exposed pad) a
    position under the package;
  - plane-net pads: via *under* the package for QFP-like parts (keeps the ring free),
    otherwise a ring position whose via lies inside the net's own plane polygon;
  - pads whose net reaches a two-pad passive (pull-up, series R placed `near=` the pin)
    within 4 mm: a direct pre-route to that pad instead of a via, when one or two straight
    segments do it with clearance (`escape_direct`);
  - skipped (listed with the reason in `summary.json` → `routing.escape.skipped`):
    no-connect pins, pins tied only to an adjacent pin, square/round pads (BGA), and pads
    with no legal position (left to the autorouter, also listed as a build note; for zone nets on
    4/6 layers: left to the finisher).
  All checks are exact geometry (`rrkicad/geom.py`): copper clearance of both net classes
  + the 25 um DSN margin, hole-to-hole, hole clearance, board edge, cut-outs, via
  keep-outs, other parts' courtyards (vias stay outside them), existing fan-out vias. The
  items are exported to the DSN as fixed wiring *of their net*, so Freerouting starts from
  the escape vias. `summary.json` → `routing.escape`: per part pitch / ring / inward / direct
  / skipped counts, totals, via and stub size. Escape vias the router did not use (it
  connected at the pad instead) are removed with their stub after the SES import (only
  escape vias, only if connectivity does not get worse). The escape runs before the plane
  fan-out; the plane fan-out puts a via in the centre of exposed/thermal pads.
  Small fine-pitch parts (< 16 pads: USON-10 ESD arrays, SOT-563, ...) are left to the
  autorouter by default: it escapes them reliably, and a via ring around a flow-through
  ESD array works against its layout; force one with `escape=True`.
  The auto-arranger keeps `escape_keepaway` (2 mm) free around
  escaped ICs; explicitly placed neighbours are the author's responsibility (a pad whose
  via would land in a neighbour's courtyard is skipped and reported).
* **Finisher.** If connections are still open after the autorouter (and its continue runs),
  `finisher=True` runs a plain grid maze router (A*, 0.05 mm grid, 8 directions, through
  vias between signal layers, never on plane layers) for each open connection KiCad's DRC
  reports, on a clearance-inflated occupancy grid (both net classes' clearance + half the
  track width; vias against copper on every layer, drills, same-net SMD pads; edge,
  cut-outs, keep-outs), in a window that grows 6 mm -> 15 mm -> whole board. Every path is
  re-checked with exact geometry before it is added. If there is no free path and
  `finisher_ripup=True` (default), it searches again allowing to cross *unlocked autorouter
  copper of other signal nets* at a cost, rips up what the new path violates, and
  reconnects every ripped net (which may in turn rip up further autorouter copper, never
  pre-routes, escape/fan-out copper, nets with zones or the finisher's own new copper);
  at most 40 steps per open connection (`finisher_seconds` caps the whole finisher), and the whole transaction is undone if any ripped
  net cannot be reconnected. Results go to `route/finish.json`
  (added items and ripped-up items, keyed to the SES hash, re-applied on cached builds; keep
  it under version control with the SES); `summary.json` → `routing.finisher` lists what it routed and what not and why.
  DRC checks the result like everything else; nothing is ever marked connected by the
  finisher itself. Slow in Python on large windows (minutes per hopeless connection).
* Freerouting reports "N pin-to-pin clearance violations" in `route/freerouting.log` for
  QFN exposed pads vs. their perimeter pads: that is the footprint's own pad spacing under
  the 25 um DSN margin, fixed items it cannot change; KiCad DRC is the reference.
* Freerouting's fallback strategies after stagnation (default chain ending in
  `continue-auto-neck`; even `continue` re-routes from the initial board) can eat the whole
  timeout: rrkicad passes `--router.autorouter.fallback_strategies=none` unless
  `route(fr_fallback=...)` or `extra_args` say otherwise - its own continue runs and restarts
  do that job and keep the best result.
* The autorouter gets keep-out bands along the outline and around cut-outs so routed
  copper keeps the board-edge clearance, and via keep-outs (plus track keep-outs on their
  layer, minus the tie's pads) over copper drawn inside footprints (net ties) - Freerouting
  does not see that copper. Rule areas that ban neither tracks nor vias (e.g. a "no
  footprints" area) are not exported to the router (KiCad would export them as full
  routing keep-outs).
* Pre-routes (`board.track`, `board.via`) and the plane fan-out are locked, exported as
  fixed, and verified after the SES import; the build fails if the router changed them.
* **Completion strategy.** If connections are still open after the first run, the build
  automatically lets Freerouting *continue from the routed result* (new DSN from the
  routed board; fresh rip-up budget concentrated on the failed nets), up to
  `retries` times, keeping a run only if it reduces the open count. Each continue run uses
  a different Freerouting item-order seed (`--router.autorouter.item_order_seed`); a run
  that does not improve is discarded and the next seed is tried. If connections are still
  open after that, Freerouting starts once more from scratch with another item-order seed
  (`restarts`, default 1; a fresh run is deterministic for a given DSN and seed, so repeating
  it unchanged is pointless) followed by its own continue runs; the result with fewer open
  connections is kept. Then the finisher (below) takes what is left. Freerouting itself
  also switches strategy when it stagnates (visible in `route/freerouting.log`).
  What is still open afterwards is reported, never hidden: `summary.json` →
  `drc.unrouted` lists every open connection with net, both end items and their board
  coordinates (also printed as `OPEN ...` lines), `routing.autorouter.attempts` lists
  the runs. A board with open connections is always FAIL.
* Giving Freerouting a `timeout` is safe: it is passed as Freerouting's own job timeout
  (verified: it stops and still writes the result); a hard kill follows 3 min later.
* The routing result lives in `route/<name>.ses` (+ `route_meta.json` with the DSN
  hash). Keep both under version control: with an unchanged definition the build
  re-uses them and reproduces the same PCB. `route/<name>.unrouted.kicad_pcb` is an
  intermediate file and need not be kept.

## Long routing jobs (large boards)
`python3 tools/eda/rrkicad.py build board.py --budget 2400` (or `route(budget=2400)`):
* every Freerouting run is capped at `chunk` seconds (default 900) and writes a scratch SES;
  it is imported with a quick import (connectivity count only, no ERC/DRC/outputs) and
  replaces `route/<name>.ses` only if it leaves fewer connections open. So
  `route/<name>.ses` always holds the best state so far - an interrupted job loses at most
  the run in progress; a later plain `build` re-uses it (DSN unchanged);
* after the first run, continue runs resume from the best routed board (new DSN exported
  from it), each with another item-order seed, until the budget is used up (less than
  3 min left) or `stall` runs in a row did not improve; then `restarts` fresh runs if time
  is left; then the finisher (its own `finisher_seconds`); then one full check;
* `route/progress.log`: one JSON line per run (kind, seed, seconds, open count, kept, best,
  elapsed) - `tail -f` it to watch an unattended job;
* the count used everywhere is KiCad's connectivity count after zone fill (`summary.json` →
  `drc.unconnected`; `drc.unconnected_listed` is how many KiCad's DRC report lists, it stops
  at 499).

### Recommended recipe for the final runs on the large boards
1. Placement first: every plane pad needs a via spot within ~4 mm (check `summary.json` →
   `routing.plane_fanout.failed` after `build --no-route`; aim for 0), 2+ mm free around
   fine-pitch ICs if escape is used, no DRC errors before routing.
2. Hand pre-routes (`board.track` / `board.via`) for power trunks, HV, analogue, safety chain.
3. Route lane 0 / the source block, then freeze it with `replicate()` (second build).
4. Unless step 1 reached 0, keep zone nets routable: `route(zone_nets="route")`.
   Escape: `escape="auto"` helps where the fine-pitch ICs have room (stress boards);
   if `routing.escape.skipped` lists many "no legal escape position", use `escape=False`.
5. One long run per DSN: `route(timeout=7200, passes=500, retries=2, restarts=0,
   optimizer=False)` and `build board.py` (no `--budget`): one uninterrupted Freerouting job,
   then continue runs from its result. Use `--budget SEC` (chunks of `chunk` s) only when
   the job must survive interruptions - the best SES is then on disk after every chunk.
6. Watch `route/progress.log`; results: `reports/summary.json` (`drc.unconnected`, `drc.errors`,
   `drc.by_type`), `reports/open_connections.txt` (KiCad's list, max 499), `route/<name>.ses`.
   A later `build` with an unchanged DSN re-uses the SES (and `route/finish.json`) without
   routing; `build --reroute` starts again.
7. Finish the remaining tens of connections in KiCad.

## Replicating blocks (identical lanes/channels)
`board.replicate(pairs, dx, dy, routes=True)` — `pairs` is `{source_ref: destination_ref}`
or a `(source_group, destination_group)` tuple (same parts in the same order).
* Placement: every destination part takes its source's position + (dx, dy), same rotation
  and side. The source block may be placed explicitly or auto-arranged; destinations
  are excluded from auto-arrange. Call it once per copy (lane 0 → 1, 0 → 2, 0 → 3).
* Routing (`routes=True`, default): after each routed build the tracks/vias of the
  **block-internal nets** (nets whose pins all belong to the source parts; rails and
  inter-block nets are excluded) are stored in `route/blocks.json`. The *next* build adds
  them as fixed pre-routes for the source block and, shifted and renamed, for each copy.
  So: build once (autorouter routes everything), build again (blocks frozen and
  identical; the autorouter only has plane leftovers and inter-block nets). If the
  source placement changes, the stored routes are ignored with a note and refreshed by
  the next build. Keep `route/blocks.json` under version control.
* Plane fan-out / escape are generated per pad for the copies as usual and are *not* stored in
  `blocks.json` (only router copper and the definition's own pre-routes are); a stored item
  identical to copper already on the board (e.g. a pre-route the definition draws for every
  lane itself) is not replayed again. (Before 2026-11-27 both happened and gave co-located
  vias; such an old `blocks.json` heals on the next routed build.) Overlaps of a copy with
  foreign parts, tracks or keep-outs show up in DRC, they are not checked at copy time.
* Auto-arrange: when a source part is auto-arranged, the spots of all its copies must be
  free as well and are reserved, so no other part lands where a copy will go.
Tested on `tools/eda/tests/replicate/` (2 lanes, 2 layers) and on a copy of RR-HEAD-ACQ
(`tools/eda/tests/head_escape/`, 4 lanes).

## Importing a stage-1 circuit definition
`rrkicad.importer.from_circuit(board, "design/circuit.py", ...)` converts a tool-neutral
`PARTS` list (dicts with `ref, value, mpn, manufacturer, description, package,
symbol_hint, footprint_hint, pins={pin_number: (pin_name, net) | None}, block, dnp,
notes`, optional `verify`, `height_mm`) into groups (one per `block`) and parts:
```python
from rrkicad import Board
from rrkicad.importer import from_circuit
board = Board("RR-CHS-MAIN", title="...", layers=6, ...)
report = from_circuit(board, os.path.join(os.path.dirname(__file__), "design/circuit.py"),
                      footprints={"U10": "Package_DFN_QFN:...", "MICROFIT-2x2-RA": "Connector_Molex:..."},  # by ref or package
                      symbols={"U42": "rr_local:MYSYM"},        # override the symbol of single parts
                      place={"J_PWR": (8, 50, 90, "F")},        # at= by ref (everything else is auto-arranged)
                      titles={"mcu": "Microcontroller"},        # sheet titles by block
                      allow_missing=False)                      # True: skip parts that have no footprint yet
board.rail("GND", "+3V3", ...); board.netclass(...); board.outline_rect(...); ...
```
Symbol per part: `symbols[ref]`, else `symbol_hint` if that stock symbol exists, has all
pin numbers used and no conflicting stacked pins (a hint `rr_local:NAME` is accepted when
`board.symbol("NAME", ...)` was defined before the import and has all pin numbers), else a
generated local box symbol (all
pins `passive`, named from the MPN). Pins with `None` become no-connects. `report` lists
`hint_rejected` (with the reason), `local_symbols`, `missing_footprints`. Parts can be
tuned afterwards: `board.part("U1").at = ...` is not supported - pass `place=`; other
attributes (`near`, `side`, `edge`, `zone_connect`, `silk_ref`) may be set on
`board.part(ref)` before the build. Reference designators are taken as they are
(`J_PWR`, `R_SH1` work).

Measured (schematic + ERC only, `python3 tools/eda/rrkicad.py sch tools/eda/tests/import_<x>/board.py`):

| circuit.py | parts imported | stock / generated symbols | hints rejected | no footprint | sheets | ERC | time |
|---|---|---|---|---|---|---|---|
| chassis_main (768) | 753 | 710 parts / 18 symbols | 46 | 15 | 18 | 0 errors, 112 warnings | 14 s |
| panel (24) | 24 | 24 / 0 | 0 | 0 | 6 | 0 errors, 0 warnings | 3 s |
| head_acq (1085) | 1081 | 971 parts / 20 symbols | 114 | 4 | 22 | 0 errors, 57 warnings | 17 s |

`reports/import_report.json` in each test directory lists every rejected hint with the
reason (mostly symbol names that do not exist in the stock library, with the closest
matches) and every part without a footprint - that list is the stage-2 to-do list.
Generated symbols have all-passive pins, so ERC cannot check pin directions on them.
No PCB was built from these imports (no placement, rails or outline decisions yet).

## Reproducibility
UUIDs are derived from hashes (schematic) or a seeded generator (PCB), ordering is
stable, report dates are stripped, Gerber/drill/STEP creation dates are set to the board
date. Re-running an unchanged definition reproduces identical KiCad project files.
Not byte-stable: PDFs and PNGs (embedded timestamps) and a *new* Freerouting run (its
optimiser is multi-threaded) — which is why the SES is cached.

## Known limitations
* No drawn wires in the schematic: connectivity is by label/power symbol only (readable,
  but not a hand-drawn schematic). No buses, no hierarchical pins, no symbol mirroring.
* Net labels are always global; there is no per-sheet local net scope.
* 2, 4 or 6 copper layers; through vias only; no differential-pair or length tuning
  (net-class diff-pair fields are written but the autorouter ignores them).
* Fine-pitch escape handles perimeter packages (QFP/QFN/SO/TSSOP); BGA (round pads) is
  skipped. Escape vias are through vias (no blind/buried/micro vias).
* Auto-arrange is a greedy helper (top/bottom side per part, courtyard rectangles). It
  avoids overlaps and keep-outs but knows nothing about signal integrity; place
  connectors, sensitive analogue parts and anything mechanical explicitly.
* `waive()` is tool-level: the item is listed as waived in `summary.json` but the KiCad
  GUI will still show it. `severity()` changes the project rule severity and is visible
  in the GUI too. Both require a written reason.
* 3D: the stock `kicad/kicad:9.0` image has **no 3D model library**. For every footprint
  whose stock model file is missing the tool writes a box envelope
  `3d/<footprint>_h<height>.step` (F.Fab outline x `height=`; per-package default heights,
  1.0 mm otherwise with a note in the summary) and links it, so `out/<name>.step` shows
  board + component envelopes for fit checks. Envelopes are bounding boxes, not real
  shapes; give `model=` for a real STEP model or `Board(envelopes=False)` to disable.
* Fine-pitch escape, plane fan-out, long fan-out and the finisher are Python geometry /
  maze search inside the KiCad container: fine on 150-500-part boards, minutes to tens of
  minutes on a 1000-part board (long fan-out capped by `long_fanout_seconds`, finisher by
  `finisher_seconds`). The finisher's rip-up only touches autorouter copper of other
  signal nets.
* Replicated block copies are not checked against keep-outs or foreign copper at copy time
  (DRC reports it). Footprint-level clearance overrides are not passed to Freerouting.
* Freerouting is deterministic for a given DSN and seed; the continue runs / restarts use
  other seeds. Each new DSN (any change of placement or pre-routes) starts routing from
  scratch.
* The dangling-stub clean-up after routing is single-pass and is skipped automatically
  if it would reduce connectivity (then `track_dangling` warnings remain and are counted).
* Fabrication notes (finish ENIG, 1 oz outer copper, stack-up thicknesses) are generic
  defaults printed on the fab drawing; adjust with `board.fab_note()` / in `pcb.py`.
* See `tools/eda/tests/stress/` for the scaling test and its measured limits (below).

## Stress test and practical limits

`tools/eda/tests/stress/board.py`: synthetic 4-layer 100 x 80 mm board, 150 parts
(LQFP-64, QFN-48 0.5 mm, 20 SOT-23-5, SOIC-8 multi-unit, SOT-223, 119 passives, 2x10
headers, JST GH, screw terminal, local symbol + footprint, DNP, cut-out, keep-out,
pre-route, GND plane + split power plane), 146 parts auto-arranged, 377 connections.
`tools/eda/tests/stress6/` is the same circuit on 6 layers with the MCU decoupling on the
bottom side. Shared 4-core machine, KiCad 9.0.9, Freerouting 2.6.0; all results tool-checked
(KiCad ERC/DRC with schematic parity):

| board / flow | Freerouting runs (s -> open) | total | result |
|---|---|---|---|
| STRESS-150 before escape (previous engineer) | 607 -> 7, 494 -> 6, 227 -> 6 | 25 min | FAIL, 6 open |
| STRESS-150-6L before escape | 607 -> 8, 289 -> 4, 227 -> 4 | 22 min | FAIL, 4 open |
| STRESS-150 escape, run A / B (same DSN) | 462 -> 1, 56 -> 1, 47 -> 1, restart 305 -> **0** (B: 426, 54, 39, restart 314 -> 0) | 18 min each | **PASS** x2, DRC 0 errors, parity 0 |
| STRESS-150-6L escape, run A / B | 62 -> **0** (B: 63 -> 0) | 90 s each | **PASS** x2, DRC 0 errors, parity 0 |
| STRESS-150 escape + zone nets not autorouted + finisher (intermediate) | 226 -> 1, continues / restart -> 1; finisher routed the last one (+5V through-hole pin outside its plane) | 11 min | **PASS**, DRC 0 errors, parity 0 |
| STRESS-150, final code (+ extended / long fan-out incl. through-hole pins) | 274 -> **0** | 337 s | **PASS**, DRC 0 errors, parity 0 |
| STRESS-150-6L, final code | 84 -> 2 (zone-net pads whose long fan-out failed); finisher routed both | 335 s | **PASS**, DRC 0 errors, parity 0 |
Notes: a fresh Freerouting run is deterministic for a given DSN and seed (the two runs of each
board reproduce each other); what changes the outcome is the DSN or the seed - hence
`restarts`. Earlier 4-layer variants of the escape code passed directly in 243-549 s
(2 of 3), one left IO46 open in every run until the restart with another seed.
What made the difference: the escape (every fine-pitch pad has its via before routing; the
boxed-in pads were the whole failure before), via in the QFN exposed pad, seeded continue
runs + restart, and the finisher for the last one. Tried and rejected: MCU decoupling on the
bottom side of the 4-layer board (5 open: B.Cu is half of the routing capacity there).

Finisher test (copy of a routed STRESS-150-6L with the copper of 7 nets deleted, 8 open):
8 of 8 routed in 36 s without rip-up, PASS. Rip-up test (4-layer board, 4 open): 2 of 4
routed with rip-up (7 and 13 nets rerouted), DRC 0 errors, 2 stayed open.

What a board author should do (in order of effect):
1. 6 layers for anything with 0.5 mm-pitch ICs and buses; on 4 layers expect the last
   connection or two to need the restart / finisher.
2. Place ICs and connectors explicitly, buses facing each other; keep 2 mm (more for
   0.6 mm vias and long QFP sides) around fine-pitch ICs free of other parts - the escape
   ring needs it (`escape_keepaway`); pads whose via would land in a neighbour's
   courtyard are skipped and listed.
3. Escape vias: the fab-minimum via (default). 0.45/0.2 mm vias (if the fab allows) fit
   two staggered rows at 0.5 mm pitch without fanning.
4. Planes: every supply pad should lie over its own plane polygon (else a long fan-out
   track is generated); split planes as non-overlapping polygons.
5. Pre-route analogue / sensitive nets yourself; the router optimises connectivity only.
6. Large boards: `build --budget SEC`, watch `route/progress.log`; see the real-board
   results below.

### Real boards (measured on copies, 2026-11-27)
`tests/head_escape/` = copy of RR-HEAD-ACQ (1085 parts, 326 x 96 mm, 6 layers, four replicated
lanes, lane-0 routes replayed from `blocks.json`), escape on, zone nets not autorouted:

| run | generation | Freerouting (KiCad open count after each run) | finisher | result |
|---|---|---|---|---|
| `--budget 2400` | 15 min; escape 87 vias + 20 direct (LQFP-100, 4 WQFN-16 DACs), fan-out 783 vias, 32 long fan-outs, 171 plane pads unconnected | 930 s -> 795, 945 s -> 741, 378 s -> 712 | 6 routed in 900 s | FAIL 707 open, DRC 2 errors, parity 0, 71 min |
| `--budget 3000` (+ extended fan-out) | 15 min; fan-out 815 vias (32 extended), 8 long fan-outs, 163 plane pads unconnected | 941 s -> 797, 933 s -> 734, 929 s -> 709 | 6 of 200 tried in 971 s | FAIL **704 open**, DRC 2 errors, parity 0, 81 min |

Lead's plain run of the original definition (escape off, zone nets autorouted, one long
Freerouting run): 1 h 45 min -> **340 open**, 3 DRC errors. So on this board the escape +
zone-net exclusion + chunked continue runs were **not better than plain autorouting** - worse
at equal effort. Best understanding of why:
* zone nets excluded: 163-171 plane pads have no via spot (dense placement, HV clearances),
  so their ~300 connections can no longer be done by Freerouting at all; the maze long
  fan-out is too slow on this board (~20-50 s per pad) to take them over. On the plain run
  Freerouting routed most of them as tracks;
* chunking: each 15-minute chunk ends in a new Freerouting job that re-reads the board and
  restarts its pass schedule; one uninterrupted job uses the time better on a 1000-item board
  (~50 connections gained per chunk late in the job);
* escape: 60 of the escape pads had no legal spot, and the via rings take routing space next
  to dense lanes; on the stress boards (room around the ICs) it was what made them complete.
The 2 DRC errors: a replicated lane via inside a lane-1 keep-out (copies are not keep-out
checked) and a footprint-level 0.2 mm clearance at U2001 that the DSN does not carry. One
build ended with exit code 139 (segfault) in the final check after the finisher; re-running
that stage alone (`_post`) completed normally - not reproduced, cause unknown.
RR-CHS-MAIN copy (`tests/chassis_escape/`): generation/ERC checked (0/0), not routed (run
stopped by the lead's change of plan).

Other generator tests:Other generator tests: `tools/eda/tests/replicate/` (placement + route replication,
`waive`, `severity`), `tools/eda/tests/import_chassis|import_panel|import_head_acq/`
(importer + schematic for the three stage-1 circuit definitions: 753/768, 24/24 and
1081/1085 parts imported, the rest have no footprint yet; ERC 0 errors each).
Only one build per board directory at a time (a `.rrkicad.lock` file enforces it).
