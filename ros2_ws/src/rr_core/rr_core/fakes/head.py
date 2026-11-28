"""Python protocol fake of the detector head (device side of head ICD 2.0).

Written independently of the firmware core so that it doubles as a second
implementation of the protocol for the host driver tests.  It is NOT the
shipped head firmware: the native emulator `rr_head_sim` (firmware lead) is.

Stimulus: `set_rates({lane: {"alpha": cps, "beta": cps, "ref": cps}})` sets the
expected count rates; counts are Poisson draws of the rate integrated over each
gate's live time (seeded, deterministic).

Fault hooks: `reset()` (MCU reset: new boot UUID, binding/buffer/clock state
cleared), `power(False)`, `drop_replies`, `corrupt_replies`, `lane_null`,
`lane_flags`, `head_flags`, `mute` (no replies at all), `lose_gates(n)` (head 0.6.0: the next n gate records are lost:
their sequence numbers are skipped and the next frame delivered carries ACQ_FAULT once; STATUS health RECORD_LOST until
FAULT_CLEAR / HELLO), `saturate[lane] = "rate" | "forced"` (floor chain SATURATED; GATESTAT tells live < 50 % without
forced clears from forced clears), `health` (latched codes reported by STATUS).
Head 0.6.0 ops: STATUS (build, identity incl. cal_id, health, reset_cause), FAULT_CLEAR, GATESTAT (per-gate statistics,
same sequence numbers and retention as ACQ).

No ROS imports.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import uuid
from collections import OrderedDict

from .. import wire

CHANNELS = ("alpha", "beta", "ref")


class FakeHead:
    def __init__(self, clock, transport, descriptor_bytes: bytes, firmware: str = "sim-1.0",
                 seed: int = 1, clock_drift_ppm: float = 0.0, boot_offset_us: int = 250_000,
                 buffer_frames: int = 128, floor_dead_us: int = 90, ref_dead_us: int = 30,
                 holdover_ppm: float = 2400.0, diag: bool = True, head_c: float = 8.2, cal_id: str | None = "FAKE-BOARD-CAL-0",
                 status: bool = True):
        self.clock, self.transport = clock, transport
        self.descriptor_bytes = descriptor_bytes
        self.desc = json.loads(descriptor_bytes)
        self.firmware = firmware
        self.rng = random.Random(seed)
        self._uuid_rng = random.Random(seed * 7919 + 13)
        self.drift = 1.0 + clock_drift_ppm * 1e-6
        self.boot_offset_us = boot_offset_us
        self.buffer_frames = buffer_frames
        self.floor_dead_us, self.ref_dead_us = floor_dead_us, ref_dead_us
        self.holdover_ppm = holdover_ppm
        self.diag = diag
        self.head_c = head_c
        self.heater_duty = 0
        self.cal_id = cal_id
        self.status_supported = status
        self.health = []
        self.saturate = {}
        self._lose = 0
        self._fault_next = False
        self.reset_cause = "POWER_ON"
        self.rates = {lane: {ch: 0.0 for ch in CHANNELS} for lane in range(4)}
        self.lane_null = {}        # lane -> set of channels reported null
        self.lane_flags = {}       # lane -> list of flags
        self.head_flags = []
        self.powered = True
        self.mute = False
        self.drop_replies = 0
        self.corrupt_replies = 0
        self.stats = {"requests": 0, "replies": 0, "resets": 0, "gates": 0, "bad_lines": 0}
        self._decoder = wire.StreamDecoder(wire.HEAD_MAX_BYTES)
        self._boot()

    # ----------------------------------------------------------------- state
    def _boot(self):
        self.boot_id = str(uuid.UUID(int=self._uuid_rng.getrandbits(128), version=4))
        self._boot_host_us = self.clock.now_us()
        self.bound = False
        self._hello_seen = False
        self.armed = False
        self.span_us = None
        self.sync = None            # {"sync_id","bound_us","expiry_us","t_us"}
        self.frames = OrderedDict() # sequence -> frame
        self.next_seq = 0
        self._gate_start = None
        self._acc = None
        self._last_advance = None
        self._cache = (None, None)  # (id, reply line)
        self._decoder.reset()
        self._diag_seq = 0
        self._reject = [0, 0, 0, 0]
        self.gstats = OrderedDict()   # sequence -> GATESTAT entry

    def now_us(self) -> int:
        """Head monotonic clock since MCU boot."""
        return int((self.clock.now_us() - self._boot_host_us) * self.drift) + self.boot_offset_us

    def reset(self, cause="WATCHDOG"):
        """MCU reset (watchdog/brownout): fresh boot UUID, everything volatile cleared."""
        self.stats["resets"] += 1
        self.reset_cause = cause
        if cause == "WATCHDOG" and "WATCHDOG_RESET" not in self.health:
            self.health.append("WATCHDOG_RESET")
        self._boot()

    def lose_gates(self, n: int):
        self._lose += int(n)

    def power(self, on: bool):
        if on and not self.powered:
            self.powered = True
            self.reset()
        elif not on:
            self.powered = False

    def set_rates(self, rates: dict):
        for lane, chans in rates.items():
            self.rates[int(lane)].update(chans)

    # ------------------------------------------------------------ acquisition
    def _advance(self):
        """Integrate expected counts and close completed gates up to now."""
        if not self.armed:
            return
        now = self.now_us()
        t = self._last_advance
        while t < now:
            gate_end = self._gate_start + self.span_us
            seg_end = min(now, gate_end)
            dt = (seg_end - t) * 1e-6
            for lane in range(4):
                for ch in CHANNELS:
                    self._acc[lane][ch] += self.rates[lane][ch] * dt
            t = seg_end
            if t >= gate_end:
                self._close_gate()
        self._last_advance = now

    def _poisson(self, mean: float) -> int:
        if mean <= 0:
            return 0
        if mean > 50:
            return max(0, int(round(self.rng.gauss(mean, mean ** 0.5))))
        # Knuth; means here are small
        import math
        limit, k, p = math.exp(-mean), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def _close_gate(self):
        start, span = self._gate_start, self.span_us
        floor_live = span - self.floor_dead_us
        ref_live = span - self.ref_dead_us
        if self.sync is None:
            sync = {"state": "UNSYNCED", "sync_id": None, "bound_us": None, "age_us": None}
        else:
            age = max(0, start - self.sync["t_us"])
            if age <= self.sync["expiry_us"]:
                sync = {"state": "LOCKED", "sync_id": self.sync["sync_id"],
                        "bound_us": self.sync["bound_us"], "age_us": age}
            else:
                grown = self.sync["bound_us"] + int(self.holdover_ppm * 1e-6 * age)
                sync = {"state": "HOLDOVER", "sync_id": self.sync["sync_id"],
                        "bound_us": min(grown, 10_000_000), "age_us": age}
        segments = []
        gs = {k: [0] * 4 for k in ("fr", "as", "am", "ic", "ff", "rf", "sc", "lf", "lr", "ga", "gb", "gr")}
        for lane in range(4):
            acc = self._acc[lane]
            null = set(self.lane_null.get(lane, set()))
            flags = list(self.lane_flags.get(lane, []))
            sat = self.saturate.get(lane)
            f_live = floor_live if sat != "rate" else int(0.3 * span)
            scale_f, scale_r = f_live / span, ref_live / span
            draws = {"alpha": self._poisson(acc["alpha"] * scale_f),
                     "beta": self._poisson(acc["beta"] * scale_f),
                     "ref": self._poisson(acc["ref"] * scale_r)}
            gs["ga"][lane], gs["gb"][lane], gs["gr"][lane] = draws["alpha"], draws["beta"], draws["ref"]
            gs["lf"][lane], gs["lr"][lane] = int(1000 * f_live / span), int(1000 * ref_live / span)
            if sat:
                null |= {"alpha", "beta"}
                flags = sorted(set(flags) | {"SATURATED"})
                gs["sc"][lane] = 2 if sat == "rate" else 1
                gs["ff"][lane] = 0 if sat == "rate" else 3
            seg = {"id": lane,
                   "alpha": None if "alpha" in null else {"counts": draws["alpha"], "live_us": floor_live},
                   "beta_window": None if "beta" in null else {"counts": draws["beta"], "live_us": floor_live},
                   "photon_ref": None if "ref" in null else {"counts": draws["ref"], "live_us": ref_live},
                   "flags": flags}
            if null and not flags and not self.head_flags:
                seg["flags"] = ["REFERENCE_FAULT" if null == {"ref"} else "FLOOR_FAULT"]
            segments.append(seg)
            self._acc[lane] = {ch: 0.0 for ch in CHANNELS}
        if self._lose > 0:                  # head 0.6.0: a lost gate record -> skipped sequence number
            self._lose -= 1
            self._fault_next = True
            if "RECORD_LOST" not in self.health:
                self.health.append("RECORD_LOST")
            self.next_seq += 1
            self._gate_start = start + span
            self.stats["gates"] += 1
            return
        gflags = list(self.head_flags)
        if self._fault_next:
            gflags = sorted(set(gflags) | {"ACQ_FAULT"})
            self._fault_next = False
        frame = {"type": "ACQ", "icd": "2.0", "sequence": self.next_seq, "start_us": start,
                 "span_us": span, "sync": sync,
                 "thermal": {"head_c": self.head_c, "heater": "ON" if self.heater_duty else "OFF",
                             "duty_pct": self.heater_duty},
                 "flags": gflags, "segments": segments}
        self.frames[self.next_seq] = frame
        self.gstats[self.next_seq] = dict(seq=self.next_seq, **gs)
        while len(self.frames) > self.buffer_frames:
            self.frames.popitem(last=False)
        while len(self.gstats) > self.buffer_frames:
            self.gstats.popitem(last=False)
        self.next_seq += 1
        self._gate_start = start + span
        self.stats["gates"] += 1

    # --------------------------------------------------------------- protocol
    def step(self):
        if not self.powered:
            self.transport.read()        # bytes fall on a dead receiver
            return
        self._advance()
        data = self.transport.read()
        if not data:
            return
        for raw, rec, err in self._decoder.feed(data):
            if rec is None:
                self.stats["bad_lines"] += 1      # discard malformed / bad-CRC records silently
                continue
            self._handle(rec)

    def _reply(self, tid, status, body=None):
        line = wire.encode({"type": "RSP", "v": "2.0", "id": tid, "status": status, "body": body or {}})
        self._cache = (tid, line)
        self._send(line)

    def _send(self, line):
        if self.mute:
            return
        if self.drop_replies > 0:
            self.drop_replies -= 1
            return
        if self.corrupt_replies > 0:
            self.corrupt_replies -= 1
            bad = bytearray(line)
            bad[len(bad) // 3] ^= 0x04
            line = bytes(bad)
        self.stats["replies"] += 1
        self.transport.write(line)

    def _handle(self, req):
        self.stats["requests"] += 1
        tid = req.get("id")
        if req.get("type") != "REQ" or type(tid) is not int or not 0 <= tid <= 0xFFFFFFFF:
            return
        rx_us = self.now_us()
        if self._cache[0] == tid:
            self._send(self._cache[1])            # idempotent retry of the last transaction
            return
        if req.get("v") != "2.0":
            self._reply(tid, "UNSUPPORTED")
            return
        op, args = req.get("op"), req.get("args")
        if not isinstance(args, dict):
            self._reply(tid, "BAD_ARG")
            return
        handler = getattr(self, "_op_" + str(op), None)
        if handler is None:
            self._reply(tid, "UNSUPPORTED")
            return
        handler(tid, args, rx_us)

    def _op_HELLO(self, tid, args, rx_us):
        # A fresh HELLO disarms and discards buffered gates, sync fit and pending replies.
        self.bound = False
        self._hello_seen = True
        self.armed = False
        self.sync = None
        self.frames.clear()
        self.gstats.clear()
        self.next_seq = 0
        self.health = [h for h in self.health if h not in ("RECORD_LOST", "GATE_TIMING", "GATE_TIMEOUT")]   # new acquisition epoch
        self._reply(tid, "OK", {
            "boot_id": self.boot_id, "head_id": self.desc["serial"], "head_type": self.desc["head_type"],
            "firmware": self.firmware, "supported_discovery": ["2.0"], "acq_format": "2.0",
            "descriptor_id": self.desc["descriptor_id"],
            "descriptor_sha256": hashlib.sha256(self.descriptor_bytes).hexdigest(),
            "descriptor_bytes": len(self.descriptor_bytes), "setup_id": self.desc["setup_id"]})

    def _op_GET_DESCRIPTOR(self, tid, args, rx_us):
        if self.bound or not self._hello_seen:
            self._reply(tid, "BAD_ARG")           # initial handshake only
            return
        if args.get("boot_id") != self.boot_id:
            self._reply(tid, "WRONG_BOOT")
            return
        offset, count = args.get("offset"), args.get("count")
        if (args.get("descriptor_id") != self.desc["descriptor_id"] or type(offset) is not int
                or type(count) is not int or not 1 <= count <= 768
                or not 0 <= offset < len(self.descriptor_bytes)):
            self._reply(tid, "BAD_ARG")
            return
        block = self.descriptor_bytes[offset:offset + count]
        self._reply(tid, "OK", {"boot_id": self.boot_id, "descriptor_id": self.desc["descriptor_id"],
                                "offset": offset, "bytes_b64": base64.b64encode(block).decode("ascii")})

    def _op_BIND(self, tid, args, rx_us):
        if args.get("boot_id") != self.boot_id:
            self._reply(tid, "WRONG_BOOT")
            return
        if (not self._hello_seen or args.get("setup_id") != self.desc["setup_id"]
                or args.get("descriptor_sha256") != hashlib.sha256(self.descriptor_bytes).hexdigest()):
            self._reply(tid, "BAD_ARG")
            return
        self.bound = True
        self._reply(tid, "OK", {"bound": True})

    def _op_TIME(self, tid, args, rx_us):
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        self._reply(tid, "OK", {"rx_us": rx_us, "tx_us": self.now_us()})

    def _op_SYNC(self, tid, args, rx_us):
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        sid, bound, expiry = args.get("sync_id"), args.get("bound_us"), args.get("expiry_us")
        if (not isinstance(sid, str) or not sid or type(bound) is not int or bound < 0
                or type(expiry) is not int or expiry <= 0):
            self._reply(tid, "BAD_ARG")
            return
        self.sync = {"sync_id": sid, "bound_us": bound, "expiry_us": expiry, "t_us": rx_us}
        self._reply(tid, "OK", {})

    def _op_ARM(self, tid, args, rx_us):
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        span = args.get("span_us")
        lo, hi = self.desc["gate_range_us"]
        if type(span) is not int or not lo <= span <= hi:
            self._reply(tid, "BAD_ARG")
            return
        if self.armed:
            if span != self.span_us:
                self._reply(tid, "BUSY")          # change settings only after disarming
                return
        else:
            self.armed, self.span_us = True, span
            self._gate_start = rx_us
            self._last_advance = rx_us
            self._acc = [{ch: 0.0 for ch in CHANNELS} for _ in range(4)]
            self._first_seq = self.next_seq
        self._reply(tid, "OK", {"first_seq": self._first_seq, "span_us": self.span_us})

    def _op_READ(self, tid, args, rx_us):
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        after = args.get("after_seq")
        if type(after) is not int or after < -1:
            self._reply(tid, "BAD_ARG")
            return
        want = after + 1
        if self.frames:
            oldest, newest = next(iter(self.frames)), next(reversed(self.frames))
            if want < oldest:
                self._reply(tid, "GAP", {"oldest_seq": oldest, "newest_seq": newest})
                return
            if want <= newest:
                self._reply(tid, "OK", self.frames[want])
                return
        self._reply(tid, "EMPTY", {})

    def _op_DISARM(self, tid, args, rx_us):
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        last = None
        if self.armed:
            # complete the current gate, default the heater off, keep completed frames
            self._advance()
            self.armed = False
            self.heater_duty = 0
        if self.next_seq > 0:
            last = self.next_seq - 1
        self._reply(tid, "OK", {"last_seq": last})

    def _op_DIAG(self, tid, args, rx_us):
        # Additive engineering op (interface/head_icd_addendum_0.4.md section 3), reduced body;
        # the host archives it verbatim.
        if not self.diag:
            self._reply(tid, "UNSUPPORTED")
            return
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        seq = args.get("seq")
        if type(seq) is not int or seq < 0:
            self._reply(tid, "BAD_ARG")
            return
        if seq not in self.frames:
            self._reply(tid, "EMPTY" if seq >= self.next_seq else "GAP",
                        {} if seq >= self.next_seq else {"oldest_seq": next(iter(self.frames), 0),
                                                         "newest_seq": self.next_seq - 1})
            return
        self._reply(tid, "OK", {"type": "DIAG", "diag": "1.0", "sequence": seq,
                                "heater": {"on_us": 0, "transition": False, "plate_c": None},
                                "bias": {"set_v": 0.0, "v": 0.0, "ua": 0.0, "dac_writes": 0},
                                "bumper_zones": None,                  # rev A: not available (null, not an empty list)
                                "health": [],
                                "lanes": [{"id": n, "floor_reject": self._reject[n], "ref_reject": 0, "alpha_short": 0,
                                           "alpha_idle_clears": 0, "imon_na": [None, None]} for n in range(4)]})

    # ------------------------------------------------------------- head 0.6.0 additive ops
    def _op_STATUS(self, tid, args, rx_us):
        if not self.status_supported:
            self._reply(tid, "UNSUPPORTED")
            return
        self._reply(tid, "OK", {
            "link": "BOUND" if self.bound else ("HANDSHAKE" if self._hello_seen else "UNBOUND"), "armed": self.armed,
            "uptime_us": self.now_us(), "reset_cause": self.reset_cause, "span_us": self.span_us, "next_seq": self.next_seq,
            "health": list(self.health), "flags": list(self.head_flags),
            "build": {"firmware": self.firmware, "build_id": "fake-build-1", "image_crc32": "00000000", "proto": "2.0", "acq_format": "2.0"},
            "identity": {"serial": self.desc["serial"], "electronics_revision": self.desc.get("electronics_revision"),
                         "mechanical_revision": self.desc.get("mechanical_revision"), "descriptor_id": self.desc["descriptor_id"],
                         "descriptor_sha256": hashlib.sha256(self.descriptor_bytes).hexdigest(), "setup_id": self.desc["setup_id"],
                         "boot_id": self.boot_id, "cal_id": self.cal_id}})

    def _op_FAULT_CLEAR(self, tid, args, rx_us):
        if not self.status_supported:
            self._reply(tid, "UNSUPPORTED")
            return
        codes = args.get("codes")
        cleared = [h for h in self.health if codes is None or h in codes]
        self.health = [h for h in self.health if h not in cleared]
        self._reply(tid, "OK", {"cleared": cleared, "health": list(self.health)})

    def _op_GATESTAT(self, tid, args, rx_us):
        if not self.status_supported:
            self._reply(tid, "UNSUPPORTED")
            return
        if not self.bound:
            self._reply(tid, "UNBOUND")
            return
        after, limit = args.get("after_seq", -1), args.get("limit", 12)
        if type(after) is not int or after < -1 or type(limit) is not int or not 1 <= limit <= 12:
            self._reply(tid, "BAD_ARG")
            return
        if self.gstats:
            oldest = next(iter(self.gstats))
            if after + 1 < oldest and after + 1 < self.next_seq - len(self.gstats):
                self._reply(tid, "GAP", {"oldest_seq": oldest, "newest_seq": next(reversed(self.gstats))})
                return
        out = [g for q, g in self.gstats.items() if q > after]
        if not out:
            self._reply(tid, "EMPTY", {})
            return
        self._reply(tid, "OK", {"gates": out[:limit], "more": len(out) > limit, "last_seq": out[:limit][-1]["seq"]})
