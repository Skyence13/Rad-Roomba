# RR-X prototype body -- status

Scope note (owner, via coordinator): **no slicing is run in this work package**. `mechanical/tools/slice_plates.py` stays as an
optional convenience (smoke-tested once on two boxes); the owner slices from the STEP/STL/3MF exports in Bambu Studio.

| Item | State |
|---|---|
| Slicing tool + `rr-plates/1` schema (`mechanical/tools/README.md`) | done (optional; not run on the real plates) |
| Parameters (`rrx/dims.py`), helpers (`rrx/util.py`) | done |
| Structure: plate, receiver, motor pods, bridge, grip frame, caster, latch arm (`rrx/structure.py`) | written, being verified |
| Battery bay: tunnel, plug, cassette, bail, spacer (`rrx/battery.py`) | in progress |
| Shells with splits and joints (`rrx/shells.py`) | in progress |
| Sensor / control mounts (`rrx/sensors.py`) | in progress |
| Wheels, bumper, tray (`rrx/running.py`) | not started |
| Exports (STEP/STL/3MF in print orientation), plates.yaml, print_schedule.md | not started |
| Checks, report, BOM, assembly documentation | not started |
