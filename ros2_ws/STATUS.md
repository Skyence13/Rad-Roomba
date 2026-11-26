# ros2_ws status (robot software, design 0.4)

Updated continuously; the last section is the honest state at the time of the last edit.
Evidence classes: calculated / simulated / tool-checked. Nothing here is physically measured.

## Written and unit-tested (tools/test.sh unit — see the count at the bottom)

| Module | Content | Tests |
|---|---|---|
| `rr_core/wire.py` | Record framing (JSON TAB CRC-32 LF), strict JSON, stream decoder with resync/oversize discard | `test_wire_descriptor.py` (baseline examples byte-identical) |
| `rr_core/transport.py` | URL transports `serial://`, `tcp://`, in-memory link with latency/faults, virtual clock | used by link tests |
| `rr_core/clockfit.py` | Four-timestamp exchange, weighted offset+drift fit, bound (half residual + asymmetry + drift·age), expiry, serialisation-length correction | `test_clockfit.py` |
| `rr_core/descriptor.py`, `frames.py` | Ports of baseline `head_discovery.py` / `check_frames.py`; registry modes BENCH / COMMISSIONING / SURVEY | `test_wire_descriptor.py` |
| `rr_core/head_link.py` | `HeadStreamInterpreter` (passive, replayable) + `HeadLinkMaster` (HELLO → GET_DESCRIPTOR → registry/calibration → BIND → TIME/fit → SYNC → ARM → READ loop, retry-same-id, GAP/EMPTY, dedup, UNBOUND, continuity loss → close/quiet/fresh ids/fresh handshake, DIAG poll) | `test_head_link.py` against `rr_core/fakes/head.py` |
| `rr_core/fakes/head.py` | Independent Python head fake (not the firmware) | same |

## Written, tests pending / in progress

See the bottom section.

## Not started

See the bottom section.
