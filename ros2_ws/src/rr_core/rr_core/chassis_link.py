"""Chassis link, host side of RR-CHS 1.0 (interface/chassis_icd.md; contract
`chassis_link`).  Sans-IO: call `step()` often; results in `self.samples`
(odometry/IMU on the host clock) and `self.out_events`.

Host obligations implemented (ICD section 9): HELLO after every connect and
boot_id change (fit, seq and ids discarded); fresh id for every request and a
strictly increasing `seq` for every DRIVE; a rejected DRIVE is reported and the
set-point is dropped (never re-sent, never queued); EVENTS read whenever
`event_seq` advances and archived, `gap` recorded; REARM_SW only on an explicit
call, with the nonce read after the stop; STOP PROTECTIVE with a reason for
host protective functions.

The link starts INACTIVE: until `activate()` it sends only v = w = 0 keep-alives.
A set-point lives for `cmd_valid_us` on the host and is sent with a TTL; when it
expires the link sends zeros.  No ROS imports.

Real-time hosts call `start_thread()`: the link then runs on its own thread with its own deadline
(DRIVE every `drive_period_us`), so a slow transaction on another link or a long computation in the
application loop cannot starve the keep-alive and let the chassis latch CMD_TIMEOUT (IB-46).  Results
are still read from `samples`, `out_events`, `drive`, `state` (deque / whole-object replacement, safe
across threads); the archive sink is called from the application thread inside `step()`.  The
deterministic harness never starts the thread and keeps calling `step()` itself.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque

from . import wire
from .clockfit import ClockFit, Exchange
from .transport import TransportClosed

PROTO = "1.0"
STOP_EVENT_KINDS = ("MODE", "PSTOP", "HOLD", "HW_LATCH", "CHAIN", "PERMIT", "J1", "J2", "BUTTON", "BOOT")


class _Lost(Exception):
    pass


class ChassisLink:
    def __init__(self, transport, clock, sink=None, drive_period_us=20_000, ttl_ms=200, cmd_valid_us=150_000,
                 reply_timeout_us=50_000, state_period_us=250_000, time_period_us=2_000_000, tid_start=1,
                 max_record=4096):
        self.transport, self.clock, self.sink = transport, clock, sink
        self.drive_period_us, self.ttl_ms, self.cmd_valid_us = drive_period_us, ttl_ms, cmd_valid_us
        self.reply_timeout_us = reply_timeout_us
        self.state_period_us, self.time_period_us = state_period_us, time_period_us
        self.max_record = max_record
        self._decoder = wire.StreamDecoder(max_record)
        self._tid = tid_start
        self._seq = 0
        self.active = False
        self.op_mode = "SERVICE"
        self._cmd = (0.0, 0.0, 0, None)       # v, w, valid_until, source
        self._ops = deque()                    # queued one-shot ops: (op, args, callback)
        self.hello = None
        self.boot_id = None
        self.fit = None
        self.state = {}
        self.drive = {}
        self.samples = deque()
        self.out_events = deque()
        self.chassis_events = []               # all chassis events (dicts with host time added)
        self._event_seq_read = 0
        self.stats = {"drive": 0, "rejected": 0, "timeouts": 0, "boots": 0, "event_gaps": 0, "drive_gap_max_us": 0}
        self._last_drive_tx_us = None
        self._thread = None
        self._stop_evt = threading.Event()
        self._log_q = deque()
        self._thread_error = None
        self.link_state = "DOWN"
        self.last_reject = None
        self.nonzero_reject = (None, 0)        # (reason, host time) of the last refused non-zero command
        self._last_ticks = None
        self._proc = self._main()

    # ---------------------------------------------------------------- public
    def activate(self, on=True):
        self.active = bool(on)

    def set_command(self, v, w, source="unknown"):
        """Latest set-point (replaces the previous one; expires on the host)."""
        self._cmd = (float(v), float(w), self.clock.now_us() + self.cmd_valid_us, source)

    def clear_command(self):
        self._cmd = (0.0, 0.0, 0, None)

    def request(self, op, args=None, callback=None):
        """Queue a one-shot op (REARM_SW, STOP, SET_OP_MODE, HEAD_POWER, CONFIG_SET, BRAKE_TEST, PANEL...)."""
        self._ops.append((op, args or {}, callback))

    def rearm_sw(self, operator, callback=None):
        """Deliberate re-arm by the controlling operator with the CURRENT nonce."""
        nonce = self.drive.get("rearm_nonce", self.state.get("rearm_nonce", 0))
        self.request("REARM_SW", {"nonce": nonce, "operator": operator[:32] or "operator"}, callback)

    def stop(self, kind="PROTECTIVE", reason="HOST_REQUEST", callback=None):
        self.clear_command()
        args = {"kind": kind}
        if kind == "PROTECTIVE":
            args["reason"] = reason
        self._ops.appendleft(("STOP", args, callback))

    def step(self):
        """Advance the link once (single-threaded hosts), or, when the link thread runs, hand its
        archive entries to the sink and re-raise a failure of the thread."""
        if self._thread is not None:
            self._drain_log()
            if self._thread_error is not None:
                err, self._thread_error = self._thread_error, None
                raise err
            return
        self._advance()

    def _advance(self):
        try:
            next(self._proc)
        except StopIteration:
            self._proc = self._main()

    def start_thread(self, period_s: float = 0.0005):
        """Run the link on its own thread (real-time hosts only; needs a real-time clock)."""
        if self._thread is not None:
            return
        self._sink_app = self.sink
        if self.sink is not None:
            self.sink = self._log_q.append
        self._stop_evt.clear()

        def run():
            while not self._stop_evt.is_set():
                try:
                    self._advance()
                except BaseException as err:             # noqa: BLE001 - reported to the application thread
                    self._thread_error = err
                    return
                time.sleep(period_s)
        self._thread = threading.Thread(target=run, name="rr-chassis-link", daemon=True)
        self._thread.start()

    def stop_thread(self):
        if self._thread is None:
            return
        self._stop_evt.set()
        self._thread.join(2.0)
        self._thread = None
        self._drain_log()
        self.sink = self._sink_app

    def _drain_log(self):
        sink = getattr(self, "_sink_app", None)
        while self._log_q:
            entry = self._log_q.popleft()
            if sink is not None:
                sink(entry)

    def to_host(self, chassis_us):
        return None if self.fit is None or self.fit.current is None else self.fit.current.to_host(chassis_us)

    def to_chassis(self, host_us):
        return None if self.fit is None or self.fit.current is None else self.fit.current.to_device(host_us)

    def time_bound_us(self):
        return math.inf if self.fit is None else self.fit.bound_us(self.clock.now_us())

    def stationary_window_valid(self, t_a_host, t_b_host):
        """ICD 6.10 host rule for a scaler count window [t_a, t_b] (host clock):
        latest `stationary` sample taken at/after t_b is stationary with since_us <= t_a,
        and no stop/inhibit event inside the window.  Returns (ok, reason)."""
        st = self.drive.get("stationary") or {}
        t_sample = self.drive.get("_t_host", 0)
        ta, tb = self.to_chassis(t_a_host), self.to_chassis(t_b_host)
        if ta is None or t_sample < t_b_host:
            return False, "NO_STATIONARY_SAMPLE_AFTER_WINDOW"
        if not st.get("is_stationary") or st.get("since_us") is None or st["since_us"] > ta:
            return False, "NOT_STATIONARY"
        if self._event_seq_read < self.drive.get("event_seq", 0):
            return False, "EVENTS_NOT_READ"
        for ev in self.chassis_events:
            if ev.get("boot_id") == self.boot_id and ev["kind"] in STOP_EVENT_KINDS and ta <= ev["t_us"] <= tb:
                return False, "EVENT_IN_WINDOW:" + ev["kind"]
        return True, ""

    # -------------------------------------------------------------- plumbing
    def _log(self, kind, payload):
        if self.sink is not None:
            self.sink((self.clock.now_us(), kind, payload))

    def _transact(self, op, args, timeout_us=None, retries=1, poll_same_id_us=None):
        self._tid = (self._tid + 1) & 0xFFFFFFFF
        tid = self._tid
        line = wire.encode(wire.make_request(PROTO, tid, op, args), self.max_record)
        timeout_us = timeout_us or self.reply_timeout_us
        start, attempt = self.clock.now_us(), 0
        while True:
            h0 = self.clock.now_us()
            try:
                self.transport.write(line)
            except TransportClosed as err:
                raise _Lost(str(err)) from err
            deadline = h0 + (poll_same_id_us or timeout_us)
            while True:
                try:
                    data = self.transport.read()
                except TransportClosed as err:
                    raise _Lost(str(err)) from err
                for raw, rec, _err in (self._decoder.feed(data) if data else ()):
                    if rec is not None and wire.is_response_to(rec, PROTO, tid):
                        if rec["status"] == "BUSY" and poll_same_id_us:
                            continue
                        rec["_h0"], rec["_h3"], rec["_req_bytes"], rec["_rsp_bytes"] = h0, self.clock.now_us(), len(line), len(raw)
                        return rec
                if self.clock.now_us() >= deadline:
                    break
                yield
            attempt += 1
            if poll_same_id_us:
                if self.clock.now_us() - start >= timeout_us:
                    break
            elif attempt > retries:
                break
        self.stats["timeouts"] += 1
        return None

    def _sleep(self, dt):
        end = self.clock.now_us() + dt
        while self.clock.now_us() < end:
            yield

    # ------------------------------------------------------------- procedure
    def _main(self):
        while True:
            self.link_state = "DOWN"
            if not self.transport.reopen():
                yield from self._sleep(500_000)
                continue
            try:
                yield from self._sleep(300_000)             # bring-up: wait 0.3 s before HELLO
                self.transport.reset_input()
                self._decoder.reset()
                yield from self._session()
            except _Lost as lost:
                self.out_events.append({"ev": "link_down", "reason": str(lost), "t_us": self.clock.now_us()})
                self._log("X", {"x": "chassis_link_down", "reason": str(lost)})
                self.clear_command()
                yield from self._sleep(300_000)

    def _hello(self):
        rsp = yield from self._transact("HELLO", {}, retries=2)
        if rsp is None or rsp["status"] != "OK":
            raise _Lost("HELLO")
        body = rsp["body"]
        new_boot = body["boot_id"] != self.boot_id
        self.hello, self.boot_id = body, body["boot_id"]
        self._seq = 0
        if new_boot:
            self.stats["boots"] += 1
            self.fit = ClockFit(epoch=self.boot_id, byte_time_us=0.0, asym_allow_us=150.0, id_prefix="chs")
            self._event_seq_read = 0
            self._last_ticks = None
            self.out_events.append({"ev": "chassis_boot", "boot_id": self.boot_id, "t_us": self.clock.now_us(),
                                    "caps": body.get("caps", {})})
        self._log("X", {"x": "chassis_hello", "body": body})
        self.link_state = "UP"

    def _time(self):
        rsp = yield from self._transact("TIME", {}, retries=0)
        if rsp is not None and rsp["status"] == "OK":
            b = rsp["body"]
            rec = self.fit.add(Exchange(rsp["_h0"], b["rx_us"], b["tx_us"], rsp["_h3"], 0, 0))
            if rec is not None:
                self._log("X", {"x": "chassis_fit", "fit": rec.as_dict()})

    def _session(self):
        yield from self._hello()
        for _ in range(5):
            yield from self._time()
            yield from self._sleep(60_000)
        now = self.clock.now_us()
        next_drive, next_state, next_time = now, now, now + self.time_period_us
        misses = 0
        while True:
            now = self.clock.now_us()
            if now >= next_drive:
                next_drive = max(next_drive + self.drive_period_us, now - self.drive_period_us)
                ok = yield from self._drive()
                misses = 0 if ok else misses + 1
                if misses >= 10:
                    raise _Lost("DRIVE_TIMEOUTS")
                continue
            if self._ops:
                op, args, cb = self._ops.popleft()
                if op == "BRAKE_TEST":
                    rsp = yield from self._transact(op, args, timeout_us=3_500_000, retries=0, poll_same_id_us=150_000)
                else:
                    rsp = yield from self._transact(op, args, timeout_us=150_000 if op == "CONFIG_SET" else None)
                result = {"op": op, "args": args, "status": rsp["status"] if rsp else "TIMEOUT",
                          "body": rsp["body"] if rsp else {}, "t_us": self.clock.now_us()}
                if op == "SET_OP_MODE" and rsp and rsp["status"] == "OK":
                    self.op_mode = rsp["body"]["op_mode"]
                self._log("X", {"x": "chassis_op", **result})
                self.out_events.append(dict(result, ev="op_result"))
                if cb:
                    cb(result)
                continue
            if self.drive.get("event_seq", 0) > self._event_seq_read:
                yield from self._events()
                continue
            if now >= next_state:
                next_state = now + self.state_period_us
                rsp = yield from self._transact("STATE", {}, retries=0)
                if rsp is not None and rsp["status"] == "OK":
                    self.state = rsp["body"]
                    self.state["_t_host"] = self.clock.now_us()
                continue
            if now >= next_time:
                next_time = now + self.time_period_us
                yield from self._time()
                continue
            yield

    def _events(self):
        rsp = yield from self._transact("EVENTS", {"after_seq": self._event_seq_read}, retries=1)
        if rsp is None or rsp["status"] != "OK":
            return
        body = rsp["body"]
        if body.get("gap"):
            self.stats["event_gaps"] += 1
            self._log("X", {"x": "chassis_event_gap", "after_seq": self._event_seq_read, "oldest": body.get("oldest_seq")})
            self.out_events.append({"ev": "event_gap", "t_us": self.clock.now_us()})
        for ev in body.get("events", []):
            ev = dict(ev, boot_id=self.boot_id, t_host_us=self.to_host(ev["t_us"]))
            self.chassis_events.append(ev)
            self._event_seq_read = max(self._event_seq_read, ev["seq"])
            self._log("X", {"x": "chassis_event", "event": ev})
            self.out_events.append({"ev": "chassis_event", "event": ev, "t_us": self.clock.now_us()})
        del self.chassis_events[:-2000]
        if not body.get("events"):
            self._event_seq_read = body.get("newest_seq", self._event_seq_read)

    def _drive(self):
        now = self.clock.now_us()
        v, w, until, source = self._cmd
        if not self.active or now > until:
            v = w = 0.0
        self._seq += 1
        if self._last_drive_tx_us is not None:
            self.stats["drive_gap_max_us"] = max(self.stats["drive_gap_max_us"], now - self._last_drive_tx_us)
        self._last_drive_tx_us = now
        rsp = yield from self._transact("DRIVE", {"seq": self._seq, "v_mps": round(v, 4), "w_radps": round(w, 4),
                                                  "ttl_ms": self.ttl_ms, "op_mode": self.op_mode}, retries=0)
        if rsp is None:
            return False
        if rsp["status"] != "OK":
            self.last_reject = rsp["status"]
            return True
        self.stats["drive"] += 1
        b = rsp["body"]
        b["_t_host"] = rsp["_h3"]
        b["_cmd"] = (v, w)
        self.drive = b
        if not b.get("accepted"):
            self.stats["rejected"] += 1
            self.last_reject = b.get("reject_reason")
            if v or w:
                # ICD 9.3: the robot is not executing my command - drop it, never resend.
                self.clear_command()
                self.nonzero_reject = (b.get("reject_reason"), now)
                self.out_events.append({"ev": "drive_rejected", "reason": b.get("reject_reason"),
                                        "mode": b.get("mode"), "t_us": now, "source": source})
        else:
            self.last_reject = None
        odom, imu = b["odom"], b.get("imu", {})
        t_host = self.to_host(odom["t_us"])
        if t_host is not None:
            ticks = (odom["left_ticks"], odom["right_ticks"])
            d = (0, 0) if self._last_ticks is None else (ticks[0] - self._last_ticks[0], ticks[1] - self._last_ticks[1])
            self._last_ticks = ticks
            self.samples.append({"t_us": t_host, "chassis_us": odom["t_us"], "d_left_ticks": d[0], "d_right_ticks": d[1],
                                 "left_ticks": ticks[0], "right_ticks": ticks[1],
                                 "gyro_z": (imu.get("gyro_rps") or [0, 0, 0])[2], "imu_ok": imu.get("ok", True),
                                 "boot_id": self.boot_id, "mode": b.get("mode"), "motion": b.get("motion"),
                                 "stationary": (b.get("stationary") or {}).get("is_stationary", False),
                                 "bound_us": self.fit.bound_us(self.clock.now_us())})
        return True
