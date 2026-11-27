"""Head link, host (link-master) side of head protocol 2.0 (interface/head_icd.md).

Two classes:

`HeadStreamInterpreter`  passive.  Consumes the ordered raw head stream
    (every transmitted request, every received line byte-for-byte, and the
    host-side control entries SESSION_OPEN / SESSION_CLOSE / NOTE) and derives
    clock fits, gate records, gap records, duplicates and faults.  The live
    driver and the offline replay run this same code on the same entries, which
    is what makes replay bit-for-bit reproducible (RQ-026, VT-020).

`HeadLinkMaster`  active.  Sans-IO state machine stepped with `step()`:
    transport (re)open -> quiet interval -> HELLO -> chunked GET_DESCRIPTOR with
    SHA-256 -> registry/calibration check -> BIND -> TIME exchanges and clock fit
    -> SYNC -> ARM -> READ loop (retry with the same id, CRC handling,
    EMPTY/GAP, dedup, DIAG polling when supported) -> on continuity loss:
    session close, stale-buffer discard, quiet interval, fresh transaction ids,
    fresh handshake (ICD section 4 "Broken continuity").

Stream entry: (t_host_us:int, kind:str, payload) with kind
    "T"  bytes   request line written at t (first byte)
    "R"  bytes   one received line (or discarded fragment) read at t
    "C"  dict    host control entry {"c": "SESSION_OPEN"|"SESSION_CLOSE"|"NOTE", ...}

No ROS imports.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from collections import OrderedDict, deque

from . import wire
from .clockfit import ClockFit, Exchange, interval_to_host
from .descriptor import (CHUNK_BYTES, DescriptorError, attachment_manifest, check_hello,
                         decode_chunk, evaluate)
from .frames import FrameError, lane_status, validate_schema, validate_semantics
from .transport import TransportClosed

PROTO = "2.0"


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


class HeadLinkConfig:
    def __init__(self, **kw):
        self.mode = "COMMISSIONING"            # registry use requested (BENCH/COMMISSIONING/SURVEY)
        self.span_us = 100_000                 # contract timing.head_gate_us_default
        self.max_bound_us = 10_000.0           # contract timing.max_time_bound_us_for_mapping
        self.target_bound_us = 2_000.0         # contract timing.target_time_bound_us
        self.sync_refresh_us = 2_000_000       # contract timing.sync_refresh_period_s
        self.sync_expiry_us = 10_000_000       # contract timing.sync_expiry_s
        self.sync_expiry_mode = "duration"     # see CONTRACT_CHANGE_REQUESTS.md CR-01
        self.byte_time_us = 10.0               # 1 Mbaud 8N1; 0 for TCP emulators
        self.asym_allow_us = 150.0
        self.reply_timeout_us = 40_000         # > 8192 bytes at 1 Mbaud would be 82 ms; ACQ ~7 ms
        self.handshake_timeout_us = 150_000
        self.max_retries = 2                   # same-id retries per transaction
        self.read_poll_us = 20_000             # re-poll period after EMPTY
        self.initial_exchanges = 6
        self.initial_exchange_gap_us = 120_000
        self.quiet_us = 300_000                # measured quiet interval before a new handshake
        self.reopen_period_us = 500_000
        self.block_retry_us = 5_000_000
        self.diag_period_us = 1_000_000
        self.diag_enabled = True
        self.setup = None                      # ENG_SETUP_SET members written before the first ARM (firmware 0.5.2: device,
                                               # thresholds / thresholds_confirmed); None = leave the head's setup alone
        self.max_status_faults = 5
        self.tid_stride = 4096                 # id jump across a session transition
        for key, value in kw.items():
            if not hasattr(self, key):
                raise TypeError(f"unknown HeadLinkConfig field {key}")
            setattr(self, key, value)


# =============================================================== interpreter
class HeadStreamInterpreter:
    """Derive sessions, fits, gates and gaps from the raw head stream."""

    def __init__(self, cfg: HeadLinkConfig | None = None):
        self.cfg = cfg or HeadLinkConfig()
        self.index = 0                 # entry counter (raw lineage key)
        self.session = None            # open manifest dict or None
        self.fit: ClockFit | None = None
        self.installed_fits = set()
        self.last_seq = None           # last accepted sequence in this session
        self._prev_heater = None       # head_icd_addendum 0.5.1: heater transition derived from consecutive frames
        self._marked_next = False      # after a gap the next gate is treated as marked
        self.last_end_us = None
        self.first_seq = None
        self.armed = False
        self._pending = OrderedDict()  # tid -> request info
        self._seen_frames = OrderedDict()   # sequence -> sha256 of canonical body
        self.stats = {"tx": 0, "rx": 0, "bad_lines": 0, "stale": 0, "duplicates": 0,
                      "gates": 0, "gaps": 0, "retries": 0, "unassigned_frames": 0,
                      "time_exchanges": 0, "time_exchanges_rejected": 0}

    # ------------------------------------------------------------------ feed
    def feed(self, entry):
        """Process one stream entry; returns a list of event dicts."""
        t, kind, payload = entry
        idx = self.index
        self.index += 1
        if kind == "T":
            return self._on_tx(t, payload, idx)
        if kind == "R":
            return self._on_rx(t, payload, idx)
        if kind == "C":
            return self._on_ctrl(t, payload, idx)
        raise ValueError(f"unknown stream entry kind {kind!r}")

    def _on_ctrl(self, t, ctrl, idx):
        what = ctrl.get("c")
        if what == "SESSION_OPEN":
            manifest = ctrl["manifest"]
            self.session = manifest
            aid = manifest["attachment_session_id"]
            self.fit = ClockFit(epoch=aid, byte_time_us=self.cfg.byte_time_us,
                                asym_allow_us=self.cfg.asym_allow_us,
                                expiry_us=self.cfg.sync_expiry_us)
            self.installed_fits = set()
            self.last_seq = self.last_end_us = self.first_seq = None
            self.armed = False
            self._seen_frames.clear()
            self._pending.clear()
            return [{"ev": "session_open", "t_us": t, "manifest": manifest, "raw_index": idx}]
        if what == "SESSION_CLOSE":
            out = []
            if self.session is not None:
                out.append({"ev": "session_close", "t_us": t,
                            "attachment": self.session["attachment_session_id"],
                            "reason": ctrl.get("reason", ""), "last_seq": self.last_seq,
                            "last_end_us": self.last_end_us, "raw_index": idx})
            self.session = None
            self.fit = None
            self.armed = False
            self._pending.clear()
            return out
        return [{"ev": "note", "t_us": t, "note": ctrl, "raw_index": idx}]

    def _on_tx(self, t, raw, idx):
        self.stats["tx"] += 1
        try:
            req = wire.decode(raw)
        except wire.WireError:
            return []
        tid = req.get("id")
        info = self._pending.get(tid)
        if info is None:
            self._pending[tid] = {"op": req.get("op"), "args": req.get("args", {}), "n_tx": 1,
                                  "t_last": t, "req_bytes": len(raw), "done": False}
            while len(self._pending) > 64:
                self._pending.popitem(last=False)
        else:
            info["n_tx"] += 1
            info["t_last"] = t
            self.stats["retries"] += 1
        return []

    def _on_rx(self, t, raw, idx):
        self.stats["rx"] += 1
        try:
            rec = wire.decode(raw)
        except wire.WireError as err:
            self.stats["bad_lines"] += 1
            return [{"ev": "bad_line", "t_us": t, "error": str(err), "raw_index": idx}]
        tid = rec.get("id")
        info = self._pending.get(tid)
        if info is None or not wire.is_response_to(rec, PROTO, tid) or info["done"]:
            self.stats["stale"] += 1
            return [{"ev": "stale_reply", "t_us": t, "id": tid, "raw_index": idx}]
        info["done"] = True
        op, status, body = info["op"], rec["status"], rec["body"]
        if self.session is None:
            if op == "READ" and status == "OK":
                # ICD section 5 / design 0.3 ch.7: a binding absent at capture leaves the
                # count unassigned, with no coverage credit.
                self.stats["unassigned_frames"] += 1
                return [{"ev": "unassigned_frame", "t_us": t, "raw_index": idx}]
            return []
        aid = self.session["attachment_session_id"]
        if status == "UNBOUND":
            return [{"ev": "unbound", "t_us": t, "op": op, "attachment": aid, "raw_index": idx}]
        if op == "TIME" and status == "OK":
            return self._on_time(t, info, body, len(raw), idx)
        if op == "SYNC" and status == "OK":
            self.installed_fits.add(info["args"].get("sync_id"))
            return []
        if op == "ARM" and status == "OK":
            if not self.armed:
                self.armed = True
                self.first_seq = body.get("first_seq")
                if self.last_seq is None and type(self.first_seq) is int:
                    self.last_seq = self.first_seq - 1
            return [{"ev": "armed", "t_us": t, "attachment": aid, "first_seq": body.get("first_seq"),
                     "span_us": body.get("span_us"), "raw_index": idx}]
        if op == "DISARM" and status == "OK":
            self.armed = False
            return [{"ev": "disarmed", "t_us": t, "attachment": aid, "last_seq": body.get("last_seq"),
                     "raw_index": idx}]
        if op == "READ":
            if status == "OK":
                return self._on_frame(t, body, idx)
            if status == "GAP":
                return self._on_gap(t, info, body, idx)
            return []
        if op == "DIAG" and status == "OK":
            return [{"ev": "diag", "t_us": t, "attachment": aid, "body": body, "raw_index": idx}]
        return []

    def _on_time(self, t, info, body, rsp_bytes, idx):
        self.stats["time_exchanges"] += 1
        rx, tx = body.get("rx_us"), body.get("tx_us")
        # A retried TIME returns the head's cached reply (stale device times) and the
        # host cannot tell which transmission was answered: never fit on it.
        if info["n_tx"] != 1 or type(rx) is not int or type(tx) is not int:
            self.stats["time_exchanges_rejected"] += 1
            return []
        rec = self.fit.add(Exchange(h0=info["t_last"], d1=rx, d2=tx, h3=t,
                                    req_bytes=info["req_bytes"], rsp_bytes=rsp_bytes))
        if rec is None:
            self.stats["time_exchanges_rejected"] += 1
            return []
        return [{"ev": "fit", "t_us": t, "attachment": self.session["attachment_session_id"],
                 "fit": rec.as_dict(), "raw_index": idx}]

    def _on_gap(self, t, info, body, idx):
        aid = self.session["attachment_session_id"]
        after = info["args"].get("after_seq")
        oldest, newest = body.get("oldest_seq"), body.get("newest_seq")
        if type(oldest) is not int or type(after) is not int:
            return [{"ev": "fault", "t_us": t, "attachment": aid, "fault": "GAP_MALFORMED", "raw_index": idx}]
        first_missing = after + 1
        if self.last_seq is not None:
            first_missing = max(first_missing, self.last_seq + 1)
        last_missing = oldest - 1
        out = []
        if last_missing >= first_missing:
            self.stats["gaps"] += 1
            self._marked_next = True
            out.append({"ev": "gap", "t_us": t, "attachment": aid, "kind": "BUFFER_EXPIRED",
                        "first_missing": first_missing, "last_missing": last_missing,
                        "count": last_missing - first_missing + 1,
                        "after_end_us": self.last_end_us, "oldest_seq": oldest,
                        "newest_seq": newest, "raw_index": idx})
        # ICD: "Reissue from oldest_seq - 1 after logging the missing range."
        self.last_seq = max(self.last_seq if self.last_seq is not None else -1, oldest - 1)
        return out

    def _on_frame(self, t, frame, idx):
        aid = self.session["attachment_session_id"]
        try:
            validate_schema(frame)
            validate_semantics(frame)
        except (FrameError, KeyError, TypeError) as err:
            return [{"ev": "fault", "t_us": t, "attachment": aid, "fault": "INVALID_FRAME",
                     "detail": str(err), "raw_index": idx}]
        seq = frame["sequence"]
        digest = hashlib.sha256(_canon(frame)).hexdigest()
        if self.last_seq is not None and seq <= self.last_seq:
            # ICD section 6: deduplicate exact frames by (attachment, sequence);
            # conflicting copies are a fault.
            known = self._seen_frames.get(seq)
            if known is None or known == digest:
                self.stats["duplicates"] += 1
                return [{"ev": "duplicate", "t_us": t, "attachment": aid, "sequence": seq, "raw_index": idx}]
            return [{"ev": "fault", "t_us": t, "attachment": aid, "fault": "CONFLICTING_DUPLICATE",
                     "sequence": seq, "raw_index": idx}]
        out = []
        if self.last_end_us is not None and frame["start_us"] < self.last_end_us:
            return [{"ev": "fault", "t_us": t, "attachment": aid, "fault": "OVERLAPPING_FRAME",
                     "sequence": seq, "raw_index": idx}]
        if self.last_seq is not None and seq > self.last_seq + 1:
            self._marked_next = True
            self.stats["gaps"] += 1
            out.append({"ev": "gap", "t_us": t, "attachment": aid, "kind": "SEQUENCE_SKIP",
                        "first_missing": self.last_seq + 1, "last_missing": seq - 1,
                        "count": seq - self.last_seq - 1, "after_end_us": self.last_end_us,
                        "before_start_us": frame["start_us"], "raw_index": idx})
        elif self.last_end_us is not None and frame["start_us"] > self.last_end_us:
            self._marked_next = True
            out.append({"ev": "gap", "t_us": t, "attachment": aid, "kind": "TIME_GAP",
                        "first_missing": None, "last_missing": None, "count": 0,
                        "after_end_us": self.last_end_us, "before_start_us": frame["start_us"],
                        "gap_us": frame["start_us"] - self.last_end_us, "raw_index": idx})
        self.last_seq = seq
        self.last_end_us = frame["start_us"] + frame["span_us"]
        self._seen_frames[seq] = digest
        while len(self._seen_frames) > 512:
            self._seen_frames.popitem(last=False)

        common = []
        t0 = t1 = bound = fit_id = None
        rec = self.fit.current if self.fit else None
        if rec is None:
            common.append("NO_FIT")
        else:
            t0, t1, bound = interval_to_host(rec, frame["start_us"], frame["span_us"],
                                             self.cfg.sync_expiry_us)
            fit_id = rec.fit_id
            if not math.isfinite(bound):
                common.append("FIT_EXPIRED")
                bound = None
            elif bound > self.cfg.max_bound_us:
                common.append("HOST_BOUND")
        sync_id = frame["sync"]["sync_id"]
        if sync_id is not None and sync_id not in self.installed_fits:
            common.append("SYNC_ID_UNKNOWN")
        lanes = []
        for (lane, why), seg in zip(lane_status(frame, self.cfg.max_bound_us), frame["segments"]):
            def pair(ch):
                return None if seg[ch] is None else [seg[ch]["counts"], seg[ch]["live_us"]]
            lanes.append({"id": lane, "alpha": pair("alpha"), "beta": pair("beta_window"),
                          "ref": pair("photon_ref"), "flags": list(seg["flags"]),
                          "reasons": why + common})
        # heater transition: ACQ 2.0 has no member for it; the heater switches only on gate boundaries, so a change of
        # thermal.heater between consecutive gates marks the gate that contains the edge; after a sequence gap the next
        # gate is treated as marked (head_icd_addendum_0.4, heater transition)
        heater = frame["thermal"].get("heater")
        marks = []
        if self._prev_heater is not None and heater != self._prev_heater:
            marks.append("HEATER_TRANSITION")
        if self._marked_next:
            marks.append("AFTER_GAP")
        self._prev_heater, self._marked_next = heater, False
        self.stats["gates"] += 1
        out.append({"ev": "gate", "t_us": t, "gate": {
            "marks": marks, "heater_transition": "HEATER_TRANSITION" in marks,
            "attachment": aid, "sequence": seq, "start_us": frame["start_us"],
            "span_us": frame["span_us"], "t0_us": t0, "t1_us": t1, "bound_us": bound,
            "fit_id": fit_id, "sync": dict(frame["sync"]), "thermal": dict(frame["thermal"]),
            "flags": list(frame["flags"]), "lanes": lanes, "raw_index": idx}})
        return out


# ==================================================================== master
class _LinkLost(Exception):
    pass


class _Blocked(Exception):
    pass


class HeadLinkMaster:
    """Active link master.  Call `step()` often (>= 1 kHz in real time, once per
    virtual tick in simulation).  Results are appended to `self.events`.

    `registry`   trusted robot-side head registry (dict with "records").
    `resolve_calibration(verified, hello) -> dict`  must return the calibration
                 binding for this head/setup/profile or raise DescriptorError.
    `sink(entry)` receives every raw stream entry BEFORE it is interpreted (the
                 archive appends it there; SESSION_OPEN is therefore durable
                 before the first frame is accepted).
    `uuid_factory()` returns a fresh attachment_session_id.
    """

    def __init__(self, transport, clock, registry, cfg: HeadLinkConfig | None = None,
                 resolve_calibration=None, sink=None, uuid_factory=None, tid_start=None):
        self.transport, self.clock, self.registry = transport, clock, registry
        self.cfg = cfg or HeadLinkConfig()
        self.resolve_calibration = resolve_calibration
        self.sink = sink
        if uuid_factory is None:
            from uuid import uuid4
            uuid_factory = lambda: str(uuid4())   # noqa: E731
        self.uuid_factory = uuid_factory
        self.interp = HeadStreamInterpreter(self.cfg)
        self.events = deque()
        self.state = "DOWN"
        self.block_reason = None
        self.block_detail = None
        self.want_armed = True
        self.enabled = True                 # False: stay idle (e.g. SERVICE_CHARGE, head power off)
        self._decoder = wire.StreamDecoder(wire.HEAD_MAX_BYTES)
        if tid_start is None:
            tid_start = (clock.now_us() // 1000) & 0x3FFFFFFF
        self._tid = int(tid_start) & 0xFFFFFFFF
        self._presence_lost = None
        self._rehandshake = False
        self._diag_supported = self.cfg.diag_enabled
        self._fault = None
        self.hello = None
        self.descriptor_bytes = None
        self.verified = None
        self._proc = self._main()

    # ---------------------------------------------------------- public hooks
    def notify_continuity_event(self, reason: str):
        """Latched connector-presence transition, head power change, etc.
        (reported by the chassis bridge independently of serial polling)."""
        self._presence_lost = reason

    def request_rehandshake(self):
        self._rehandshake = True

    def step(self):
        try:
            next(self._proc)
        except StopIteration:      # never expected; restart the procedure
            self._proc = self._main()

    def drain_events(self):
        out = list(self.events)
        self.events.clear()
        return out

    @property
    def session(self):
        return self.interp.session

    def status(self) -> dict:
        fit = self.interp.fit.current if self.interp.fit else None
        now = self.clock.now_us()
        bound = self.interp.fit.bound_us(now) if self.interp.fit else math.inf
        return {"state": self.state, "block_reason": self.block_reason,
                "block_detail": self.block_detail,
                "attachment": self.session["attachment_session_id"] if self.session else None,
                "head_id": self.hello.get("head_id") if self.hello else None,
                "last_seq": self.interp.last_seq, "fit_id": fit.fit_id if fit else None,
                "bound_us": bound if math.isfinite(bound) else None,
                "stats": dict(self.interp.stats), "transport": self.transport.url}

    # -------------------------------------------------------------- plumbing
    def _emit(self, kind, payload):
        entry = (self.clock.now_us(), kind, payload)
        if self.sink is not None:
            self.sink(entry)
        for ev in self.interp.feed(entry):
            if ev["ev"] == "fault":
                self._fault = ev["fault"]
            self.events.append(ev)
        return entry

    def _note(self, **fields):
        self._emit("C", dict(c="NOTE", **fields))

    def _next_tid(self):
        self._tid = (self._tid + 1) & 0xFFFFFFFF
        return self._tid

    def _poll_rx(self):
        """Read the transport once; journal every line; return decoded records."""
        try:
            data = self.transport.read()
        except TransportClosed as err:
            raise _LinkLost(f"TRANSPORT:{err}") from err
        records = []
        if data:
            for raw, rec, _err in self._decoder.feed(data):
                self._emit("R", raw)
                if rec is not None:
                    records.append(rec)
        return records

    def _sleep(self, dt_us):
        end = self.clock.now_us() + dt_us
        while self.clock.now_us() < end:
            yield

    def _transact(self, op, args=None, timeout_us=None, retries=None):
        tid = self._next_tid()
        line = wire.encode(wire.make_request(PROTO, tid, op, args))
        timeout_us = timeout_us or self.cfg.reply_timeout_us
        retries = self.cfg.max_retries if retries is None else retries
        for _attempt in range(retries + 1):
            self._emit("T", line)
            try:
                self.transport.write(line)
            except TransportClosed as err:
                raise _LinkLost(f"TRANSPORT:{err}") from err
            deadline = self.clock.now_us() + timeout_us
            while True:
                for rec in self._poll_rx():
                    if wire.is_response_to(rec, PROTO, tid):
                        return rec
                if self.clock.now_us() >= deadline:
                    break
                yield
            # timeout or damaged reply: retry with the SAME id; the head answers
            # from its reply cache, so a READ is never consumed twice (ICD section 4).
        raise _LinkLost(f"TIMEOUT:{op}")

    # ------------------------------------------------------------- procedure
    def _main(self):
        while True:
            if not self.enabled:
                self.state = "DISABLED"
                yield
                continue
            self.state = "DOWN"
            if not self.transport.reopen():
                yield from self._sleep(self.cfg.reopen_period_us)
                continue
            try:
                yield from self._quiet()
                yield from self._setup_step()
                yield from self._handshake()
                yield from self._sync_and_arm()
                yield from self._run()
            except _LinkLost as lost:
                self._close_session(str(lost))
            except _Blocked as blocked:
                self._close_session(f"BLOCKED:{blocked}")
                self.state = "BLOCKED"
                self._rehandshake = False
                self._presence_lost = None
                end = self.clock.now_us() + self.cfg.block_retry_us
                while self.clock.now_us() < end and not self._rehandshake and self.enabled:
                    yield
                self._rehandshake = False

    def _close_session(self, reason):
        if self.session is not None:
            self._emit("C", {"c": "SESSION_CLOSE", "reason": reason})
        else:
            self._note(note="HANDSHAKE_ABORTED", reason=reason)
        self.events.append({"ev": "link_down", "t_us": self.clock.now_us(), "reason": reason})
        self._fault = None
        self._presence_lost = None
        # Fresh ids across the transition so a deferred reply cannot match a new poll.
        self._tid = (self._tid + self.cfg.tid_stride) & 0xFFFFFFFF

    def _quiet(self):
        """Discard stale buffers and wait for a measured quiet interval."""
        self.state = "QUIET"
        dropped = self.transport.reset_input()
        fragment = self._decoder.reset()
        if dropped or fragment:
            self._emit("R", (fragment + dropped)[:wire.HEAD_MAX_BYTES])
        quiet_since = self.clock.now_us()
        while self.clock.now_us() - quiet_since < self.cfg.quiet_us:
            try:
                data = self.transport.read()
            except TransportClosed as err:
                raise _LinkLost(f"TRANSPORT:{err}") from err
            if data:
                self._emit("R", data[:wire.HEAD_MAX_BYTES])   # residual traffic: archived, never parsed
                quiet_since = self.clock.now_us()
            yield
        self._decoder.reset()
        self._note(note="QUIET_INTERVAL_OK", quiet_us=self.cfg.quiet_us)

    @staticmethod
    def _setup_diff(want, have):
        """Members of `want` (nested) that differ from the head's reported setup."""
        out = {}
        for k, v in want.items():
            if isinstance(v, dict) and isinstance(have, dict) and isinstance(have.get(k), dict):
                d = HeadLinkMaster._setup_diff(v, have[k])
                if d:
                    out[k] = d
            elif not isinstance(have, dict) or have.get(k) != v:
                out[k] = v
        return out

    def _setup_step(self):
        """Head ICD addendum 0.5.2: before the first ARM the setup member `device` must be a real type and the
        thresholds written or confirmed.  ENG_SETUP_GET, then ENG_SETUP_SET of what differs from the mission
        configuration (head_setup); the change invalidates the binding, which the handshake that follows renews.
        Every request and reply is archived like any other transaction.  UNSUPPORTED (fixed descriptor) is skipped."""
        want = self.cfg.setup
        if not want:
            return
        self.state = "SETUP"
        rsp = yield from self._transact("ENG_SETUP_GET", {}, self.cfg.handshake_timeout_us)
        if rsp["status"] == "UNSUPPORTED":
            self._note(note="SETUP_UNSUPPORTED")
            return
        if rsp["status"] != "OK":
            self._block("SETUP_GET_" + rsp["status"], "head refused ENG_SETUP_GET")
        diff = self._setup_diff(want, rsp["body"].get("setup") or {})
        if not diff:
            return
        rsp = yield from self._transact("ENG_SETUP_SET", dict(diff), self.cfg.handshake_timeout_us)
        if rsp["status"] != "OK":
            self._block("SETUP_SET_" + rsp["status"], f"head refused ENG_SETUP_SET {sorted(diff)}: {rsp['body']}")
        self._note(note="SETUP_WRITTEN", members=sorted(diff))

    def _handshake(self):
        self.state = "HANDSHAKE"
        self.block_reason = self.block_detail = None
        self.hello = self.descriptor_bytes = self.verified = None
        self._diag_supported = self.cfg.diag_enabled
        rsp = yield from self._transact("HELLO", {}, self.cfg.handshake_timeout_us)
        if rsp["status"] != "OK":
            self._block("HELLO_" + rsp["status"], "head refused HELLO")
        hello = rsp["body"]
        try:
            check_hello(hello)
        except DescriptorError as err:
            self._block(err.reason, str(err))
        self.hello = hello
        data = bytearray()
        while len(data) < hello["descriptor_bytes"]:
            count = min(CHUNK_BYTES, hello["descriptor_bytes"] - len(data))
            rsp = yield from self._transact(
                "GET_DESCRIPTOR", {"boot_id": hello["boot_id"], "descriptor_id": hello["descriptor_id"],
                                   "offset": len(data), "count": count}, self.cfg.handshake_timeout_us)
            if rsp["status"] == "WRONG_BOOT":
                raise _LinkLost("BOOT_CHANGED_DURING_HANDSHAKE")     # discard partial data
            if rsp["status"] != "OK":
                self._block("DESCRIPTOR_" + rsp["status"], "descriptor read refused")
            try:
                data.extend(decode_chunk(hello, rsp["body"], len(data), len(data)))
            except DescriptorError as err:
                if err.reason == "DESCRIPTOR_CHANGED":
                    raise _LinkLost("DESCRIPTOR_CHANGED") from err
                self._block(err.reason, str(err))
        data = bytes(data)
        try:
            verified = evaluate(hello, data, self.registry, self.cfg.mode)
            calibration = None
            if self.resolve_calibration is not None:
                calibration = self.resolve_calibration(verified, hello)
        except DescriptorError as err:
            self._block(err.reason, str(err))
        self.descriptor_bytes, self.verified = data, verified
        rsp = yield from self._transact(
            "BIND", {"boot_id": hello["boot_id"], "setup_id": hello["setup_id"],
                     "descriptor_sha256": verified["descriptor_sha256"]}, self.cfg.handshake_timeout_us)
        if rsp["status"] == "WRONG_BOOT":
            raise _LinkLost("BOOT_CHANGED_BEFORE_BIND")
        if rsp["status"] != "OK" or rsp["body"].get("bound") is not True:
            self._block("BIND_" + rsp["status"], "head refused BIND")
        manifest = attachment_manifest(hello, verified, self.uuid_factory())
        manifest.update({
            "opened_host_us": self.clock.now_us(),
            "geometry_basis": verified["geometry_basis"],
            "mount_transform": verified.get("mount_transform"),
            "calibration": calibration,
            "descriptor_b64": base64.b64encode(data).decode("ascii"),
            "host_clock": "CLOCK_MONOTONIC", "link_url": self.transport.url,
        })
        # Persist the immutable attachment record before accepting counts (ICD 4 step 3).
        self._emit("C", {"c": "SESSION_OPEN", "manifest": manifest})

    def _block(self, reason, detail):
        self.block_reason, self.block_detail = reason, detail
        self.events.append({"ev": "blocked", "t_us": self.clock.now_us(), "reason": reason, "detail": detail})
        raise _Blocked(reason)

    def _time_exchange(self):
        before = self.interp.fit.current.fit_id if self.interp.fit.current else None
        rsp = yield from self._transact("TIME", {})
        if rsp["status"] == "UNBOUND":
            raise _LinkLost("UNBOUND")
        fit = self.interp.fit.current
        return fit if fit is not None and fit.fit_id != before else None

    def _install_sync(self, fit):
        now = self.clock.now_us()
        bound = int(math.ceil(self.interp.fit.bound_us(now)))
        expiry = self.cfg.sync_expiry_us
        if self.cfg.sync_expiry_mode == "absolute_head_time":
            expiry = int(fit.to_device(now) + self.cfg.sync_expiry_us)
        rsp = yield from self._transact("SYNC", {"sync_id": fit.fit_id, "bound_us": bound,
                                                 "expiry_us": expiry})
        if rsp["status"] == "UNBOUND":
            raise _LinkLost("UNBOUND")
        return rsp["status"] == "OK"

    def _sync_and_arm(self):
        self.state = "SYNCING"
        fit = None
        for _ in range(self.cfg.initial_exchanges):
            fit = (yield from self._time_exchange()) or fit
            yield from self._sleep(self.cfg.initial_exchange_gap_us)
        if fit is None:
            raise _LinkLost("NO_CLOCK_FIT")
        if not (yield from self._install_sync(fit)):
            raise _LinkLost("SYNC_REFUSED")
        yield from self._arm()

    def _arm(self):
        rsp = yield from self._transact("ARM", {"span_us": self.cfg.span_us})
        if rsp["status"] == "UNBOUND":
            raise _LinkLost("UNBOUND")
        if rsp["status"] != "OK":
            # 0.5.2: FAULT with a reason (device_type_unset / placeholder_thresholds) is shown to the operator as such
            why = (rsp.get("body") or {}).get("reason") or (rsp.get("body") or {}).get("detail")
            self._block("ARM_" + rsp["status"] + (f":{why}" if why else ""),
                        f"head refused ARM{(': ' + str(why)) if why else ''}"
                        + (" - set head_setup.device and write or confirm the thresholds (thresholds_confirmed) in the mission configuration"
                           if why in ("device_type_unset", "placeholder_thresholds") else ""))
        self.state = "ARMED"

    def _run(self):
        cfg = self.cfg
        now = self.clock.now_us()
        next_time = now + cfg.sync_refresh_us
        next_read = now
        next_diag = now + cfg.diag_period_us
        status_faults = 0
        while True:
            now = self.clock.now_us()
            if not self.enabled:
                raise _LinkLost("DISABLED")
            if self._presence_lost:
                raise _LinkLost(f"CONTINUITY:{self._presence_lost}")
            if self._rehandshake:
                self._rehandshake = False
                raise _LinkLost("REHANDSHAKE_REQUESTED")
            if self._fault:
                raise _LinkLost(f"FAULT:{self._fault}")
            if now >= next_time:
                next_time = now + cfg.sync_refresh_us
                fit = yield from self._time_exchange()
                if fit is not None:
                    yield from self._install_sync(fit)
                continue
            if self.want_armed != self.interp.armed:
                if self.want_armed:
                    yield from self._arm()
                else:
                    rsp = yield from self._transact("DISARM", {})
                    if rsp["status"] == "UNBOUND":
                        raise _LinkLost("UNBOUND")
                    self.state = "BOUND_IDLE"
                continue
            if now >= next_read and (self.interp.armed or self.interp.last_seq is not None):
                after = self.interp.last_seq if self.interp.last_seq is not None else -1
                rsp = yield from self._transact("READ", {"after_seq": after})
                status = rsp["status"]
                if status in ("OK", "GAP"):
                    status_faults = 0
                    next_read = self.clock.now_us()          # drain the buffer
                elif status == "EMPTY":
                    status_faults = 0
                    next_read = self.clock.now_us() + cfg.read_poll_us
                elif status == "UNBOUND":
                    raise _LinkLost("UNBOUND")               # MCU reset / binding lost
                else:
                    status_faults += 1
                    next_read = self.clock.now_us() + cfg.read_poll_us
                    if status_faults >= cfg.max_status_faults:
                        raise _LinkLost(f"STATUS:{status}")
                continue
            if self._diag_supported and now >= next_diag:
                next_diag = now + cfg.diag_period_us
                if self.interp.last_seq is None:
                    continue
                # head_icd_addendum_0.4 section 3: engineering record per sequence
                rsp = yield from self._transact("DIAG", {"seq": self.interp.last_seq})
                if rsp["status"] == "UNSUPPORTED":
                    self._diag_supported = False     # heads without DIAG answer UNSUPPORTED
                    self._note(note="DIAG_UNSUPPORTED")
                elif rsp["status"] == "UNBOUND":
                    raise _LinkLost("UNBOUND")
                continue
            yield
