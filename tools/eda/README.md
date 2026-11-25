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
autorouter settings). Exit code 0 = pass, 1 = checks failed, 2 = definition error.

Requirements on the host: `python3`, `docker`, images `kicad/kicad:9.0` and
`ghcr.io/freerouting/freerouting:latest` (tested: KiCad 9.0.9, Freerouting 2.6.0).
Wrappers (use them for anything ad hoc, they handle mounts, uid and HOME):
`tools/docker/kicad.sh <cmd...>` and `tools/docker/freerouting.sh in.dsn out.ses [passes] [threads]`.
Both mount the repository at the same absolute path, run as the calling uid with
`--network none`, and work only on files inside the repository.

## What happens in a build

| step | where | what |
|---|---|---|
| 1 `_gen` | KiCad container | evaluate `board.py`; resolve symbols; write `.kicad_pro`, `sym-lib-table`, `fp-lib-table`, `rr_local.kicad_sym`, `rr_local.pretty/`, root + one `.kicad_sch` per group; export the KiCad netlist from the generated schematic and **cross-check it pin-by-pin against the definition**; build the unrouted `.kicad_pcb` with pcbnew (pad nets come from that netlist); auto-arrange unplaced parts; export `route/<name>.dsn` |
| 2 route | Freerouting container | `route/<name>.dsn` → `route/<name>.ses` (+ `freerouting.log`, `route_meta.json`). Skipped when the DSN hash is unchanged and a SES exists (so reruns are deterministic); `--reroute` forces it |
| 3 `_post` | KiCad container | import SES, verify pre-routes are untouched, remove dangling stubs, fill zones, add fab notes/dimensions, save; ERC; DRC with schematic parity; outputs; `reports/summary.json` |

Files per board directory:
```
board.py                       the definition (edit this, nothing else)
<name>.kicad_pro/.kicad_sch/.kicad_pcb, <group>.kicad_sch, rr_local.*, *-lib-table, 3d/   generated KiCad project
route/      <name>.dsn, <name>.ses (routing result = cache key + source of the tracks), freerouting.log
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
              company="Rad Roomba", layers=4,          # 2 or 4 (4 = F.Cu sig / In1 plane / In2 plane / B.Cu sig)
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
board.route(passes=100, threads=None, timeout=None, optimizer=True, fanout=None, enabled=True, extra_args=[])
board.autoplace_options(clearance=0.3, ic_halo=2.0, edge_margin=0.5, grid=0.25, spread=0.35, rotations=(0, 90, 180, 270))
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
  silk lines clear of pads and a pin-1 dot are generated.
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
* Zones on the outer (signal) layers are *not* given to the autorouter: those nets are
  routed with real tracks and the pour is added afterwards. Zones on inner plane layers
  are exported; Freerouting connects plane nets with fan-out vias.
* Pre-routes (`board.track`, `board.via`) are locked, exported as fixed, and verified
  after the SES import; the build fails if the router changed them.
* Unrouted connections are never hidden: they appear as `unconnected` / `unrouted_nets`
  in the summary and fail the build. Typical fixes: better placement, more passes, fewer
  parts per mm², a GND via (`board.via`) next to an isolated pad.
* Pours can be cut into islands by routing; islands are removed. Add `board.via("GND", x, y)`
  stitching vias where needed (see RR-TOF-A).
* The routing result lives in `route/<name>.ses`. Keep it under version control: with an
  unchanged definition the build re-uses it and reproduces the same PCB.

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
* 2 or 4 copper layers only; through vias only; no differential-pair or length tuning
  (net-class diff-pair fields are written but the autorouter ignores them).
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
* The dangling-stub clean-up after routing is single-pass and is skipped automatically
  if it would reduce connectivity (then `track_dangling` warnings remain and are counted).
* Fabrication notes (finish ENIG, 1 oz outer copper, stack-up thicknesses) are generic
  defaults printed on the fab drawing; adjust with `board.fab_note()` / in `pcb.py`.
* See `tools/eda/tests/stress/` for the scaling test and its measured limits (below).

## Scaling (measured, 4 CPU cores)
See the "Stress test" section at the end of this file.
