"""Python protocol fake of the motion MCU (device side of RR-CHS 1.0,
interface/chassis_icd.md).  Independent of the firmware core; a reduced but
rule-faithful subset: link session, reply cache, DRIVE acceptance order, TTL and
CMD_TIMEOUT, HOST_LINK_LOST, hardware latch (local REARM only), software
protective stop with rearm nonce, hold, pre-motion alert, brake test, op_mode
caps, head power, events, stationary evidence, kinematic truth with slip.

Environment API mirrors the native emulator's UDP inputs (`env(name, value)`,
`press(name)`); `truth()` gives the ground-truth pose.

No ROS imports.
"""
from __future__ import annotations

import math
import random
import uuid

from .. import wire

CHAIN = ("MODE_RUN", "ESTOP", "HANDS_ON", "CHG_COVER", "HEAD_DOCK", "HEAD_LOOP", "LAB_KEY_N",
         "BODY_BUMPER", "WDG_OK", "ARM_PERMIT")
CAPS = {"COMMISSIONING": (0.20, 0.05, 0.30), "SURVEY_SHARED": (0.10, 0.05, 0.30),
        "SURVEY_UNATTENDED": (0.20, 0.05, 0.30), "GUIDED": (0.10, 0.05, 0.30),
        "LAB": (0.0, 0.0, 0.0), "SERVICE": (0.0, 0.0, 0.0)}
SESSION_OPS = ("DRIVE", "REARM_SW", "SET_OP_MODE", "HEAD_POWER", "HEATER", "PANEL", "CONFIG_SET", "BRAKE_TEST")
MAX_RECORD = 4096


class FakeChassis:
    def __init__(self, clock, transport, seed: int = 1, pose=(0.5, 0.0, 0.0), track_m=0.270,
                 wheel_radius_m=0.052, cpr=9600, gyro_noise=0.002, gyro_bias=0.0, drift_ppm=0.0):
        self.clock, self.transport = clock, transport
        self.rng = random.Random(seed)
        self.track, self.radius, self.cpr = track_m, wheel_radius_m, cpr
        self.gyro_noise, self.gyro_bias = gyro_noise, gyro_bias
        self.drift = 1.0 + drift_ppm * 1e-6
        self.x, self.y, self.yaw = pose
        self.inputs = {"estop": False, "hands_on": False, "bumper_l": False, "bumper_r": False,
                       "mode_run": True, "head_docked": True, "j2": True, "chg_cover_open": False,
                       "chg_plug": False, "pres_ohm": 4700.0, "loop_ohm": 1000.0, "rear_blocked": False,
                       "cliff": False, "slip": 0.0, "usb_down": False, "tilt_deg": 0.0}
        self.config = {"alert.rest_ms": 2000.0, "alert.premotion_ms": 1500.0, "cal.track_m": track_m,
                       "cal.wheel_radius_l_m": wheel_radius_m, "cal.wheel_radius_r_m": wheel_radius_m,
                       "safety.require_brake_test": 1.0, "link.timeout_ms": 1000.0, "stationary.min_ms": 100.0}
        self._decoder = wire.StreamDecoder(MAX_RECORD)
        self._last_step = None
        self._boot_count = 0
        self._boot("POWER_ON")

    # ------------------------------------------------------------------ boot
    def _boot(self, cause):
        self._boot_count += 1
        self.boot_id = str(uuid.UUID(int=self.rng.getrandbits(128), version=4))
        self._boot_host = self.clock.now_us()
        self.session = 0
        self.op_mode = "SERVICE"
        self.hw_latch = False
        self.hw_reasons, self.sw_reasons, self.hold = [], [], []
        self.nonce = 0
        self.brake_passed = False
        self._brake = None           # (tid, raw request, t_done)
        self.events = []
        self.event_seq = 0
        self.cmd = None              # (v, w, t_expire_us)
        self.last_seq = -1
        self.v = self.w = 0.0
        self.left_ticks = self.right_ticks = 0.0
        self.motion = "REST"
        self._alert_until = None
        self._rest_since = self._boot_host
        self._stat_since = None
        self._last_req = None
        self._cache = (None, None, None)
        self.head_power = {"electronics": False, "heater_enable": False}
        self.mode = "BOOT"
        self.panel = "AUTO"
        self._presence = self._presence_class()
        self._event("BOOT", {"reset": cause, "boot_count": self._boot_count, "fw": "py-fake 0.4"})
        self._decoder.reset()

    def now_us(self):
        return int((self.clock.now_us() - self._boot_host) * self.drift)

    def _event(self, kind, detail):
        self.event_seq += 1
        self.events.append({"seq": self.event_seq, "t_us": self.now_us(), "kind": kind, "detail": detail})
        del self.events[:-128]

    # ------------------------------------------------------------ environment
    def env(self, name, value):
        old = self.inputs.get(name)
        self.inputs[name] = value
        if name == "mcu_reset" and value:
            self._boot("WATCHDOG")
            return
        if name == "pose":
            self.x, self.y, self.yaw = value
            return
        if old != value:
            el = {"estop": "ESTOP_A", "hands_on": "HANDS_ON", "bumper_l": "BODY_BUMPER_L", "bumper_r": "BODY_BUMPER_R",
                  "mode_run": "MODE_RUN", "head_docked": "HEAD_DOCK", "chg_cover_open": "CHG_COVER",
                  "chg_plug": "CHG_PLUG_LINK"}.get(name)
            if el:
                closed = bool(value) if name in ("mode_run", "head_docked") else not bool(value)
                self._event("CHAIN", {"el": el, "closed": closed})
            if name == "j2":
                self._event("J2", {"present": bool(value)})
            if name == "loop_ohm":
                self._event("CHAIN", {"el": "HEAD_LOOP_OK", "closed": 600 <= value <= 1600})
            if name == "pres_ohm":
                new = self._presence_class()
                if new != self._presence:
                    self._event("J1", {"from": self._presence, "to": new, "ohm": value})
                    self._presence = new

    def press(self, name):
        self._event("BUTTON", {"name": name, "pressed": True})
        if name == "PAUSE":
            if self.hw_latch and "LOCAL_PAUSE" not in self.hold:
                self.hold.append("LOCAL_PAUSE")
                self._new_nonce()
                self.cmd = None
                self._event("HOLD", {"on": True, "why": "LOCAL_PAUSE"})
        elif name == "REARM":
            chain = self._chain()
            if not self.hw_latch and all(chain.values()) and self.mode not in ("BOOT", "FAULT"):
                self.hw_latch = True
                self.hw_reasons = []
                self._event("HW_LATCH", {"set": True, "reasons": []})
            if self.hw_latch and not self._sw_active():
                if self.sw_reasons or self.hold:
                    self._event("PSTOP_CLEAR", {"by": "LOCAL", "operator": "LOCAL", "cleared": list(self.sw_reasons)})
                self.sw_reasons, self.hold = [], []

    def truth(self):
        return {"x": self.x, "y": self.y, "yaw": self.yaw, "v": self.v, "w": self.w, "mode": self.mode,
                "boot_id": self.boot_id, "chassis_us": self.now_us()}

    # -------------------------------------------------------------- supervision
    def _presence_class(self):
        ohm = self.inputs["pres_ohm"]
        if ohm > 20000:
            return "ABSENT"
        if 3900 <= ohm <= 5600:
            return "HEAD_DIRECT"
        if 950 <= ohm < 1330:
            return "HEAD_VIA_LAB_EXTENSION"
        if 1330 <= ohm <= 1800:
            return "LAB_EXTENSION_ONLY"
        return "FAULT"

    def _chain(self):
        i = self.inputs
        pres = self._presence_class()
        return {"MODE_RUN": bool(i["mode_run"]), "ESTOP": not i["estop"], "HANDS_ON": not i["hands_on"],
                "CHG_COVER": not (i["chg_cover_open"] or i["chg_plug"]), "HEAD_DOCK": bool(i["head_docked"]),
                "HEAD_LOOP": 600 <= i["loop_ohm"] <= 1600 and pres in ("HEAD_DIRECT", "HEAD_VIA_LAB_EXTENSION"),
                "LAB_KEY_N": pres not in ("HEAD_VIA_LAB_EXTENSION", "LAB_EXTENSION_ONLY"),
                "BODY_BUMPER": not (i["bumper_l"] or i["bumper_r"]), "WDG_OK": True,
                "ARM_PERMIT": self.mode not in ("BOOT", "FAULT", "SERVICE_CHARGE", "LAB")}

    def _hw_active(self):
        c, i = self._chain(), self.inputs
        out = []
        if not c["MODE_RUN"]: out.append("MODE_NOT_RUN")
        if not c["ESTOP"]: out.append("ESTOP")
        if not c["HANDS_ON"]: out.append("HANDS_ON")
        if not c["CHG_COVER"]: out.append("CHARGER")
        if not c["HEAD_DOCK"]: out.append("HEAD_UNDOCKED")
        if self._presence_class() == "ABSENT": out.append("J1_ABSENT")
        elif not 600 <= i["loop_ohm"] <= 1600: out.append("HEAD_LOOP_OPEN" if i["loop_ohm"] > 1600 else "HEAD_LOOP_SHORT")
        if not c["LAB_KEY_N"]: out.append("LAB_KEY")
        if not c["BODY_BUMPER"]: out.append("BODY_BUMPER")
        return out

    def _sw_active(self):
        out = []
        if self.inputs["cliff"]: out.append("CLIFF_FL")
        if self.inputs["tilt_deg"] > 15: out.append("TILT")
        return out

    def _new_nonce(self):
        self.nonce = self.rng.randrange(1, 2 ** 32)

    def _pstop(self, reason):
        if reason not in self.sw_reasons:
            self.sw_reasons.append(reason)
            self.cmd = None
            self._new_nonce()
            self._event("PSTOP", {"reason": reason, "v_mps": round(self.v, 4)})

    def _update_mode(self):
        old = self.mode
        i = self.inputs
        active = self._hw_active()
        if self.hw_latch and active:
            self.hw_latch = False
            self.hw_reasons = list(active)
            self.cmd = None
            self._event("HW_LATCH", {"set": False, "reasons": list(active)})
        elif not self.hw_latch:
            for r in active:
                if r not in self.hw_reasons and self.hw_reasons:
                    self.hw_reasons.append(r)
            if active and not self.hw_reasons:
                self.hw_reasons = list(active)
        moving = abs(self.v) > 1e-4 or abs(self.w) > 1e-4 or self.motion in ("ALERT", "RUN", "DECEL")
        if self.clock.now_us() - self._boot_host < 200_000:
            mode = "BOOT"
        elif i["chg_cover_open"] or i["chg_plug"]:
            mode = "SERVICE_CHARGE"
            if self.head_power["electronics"]:
                self.head_power = {"electronics": False, "heater_enable": False}
                self._event("HEAD_POWER", {"electronics": False, "heater_enable": False, "why": "CHARGE"})
        elif self._presence_class() in ("HEAD_VIA_LAB_EXTENSION", "LAB_EXTENSION_ONLY"):
            mode = "LAB"
        elif not self.hw_latch:
            mode = "HW_INHIBIT" if self.hw_reasons else ("PROTECTIVE_STOP" if self.sw_reasons else "STANDBY")
        elif self.sw_reasons:
            mode = "PROTECTIVE_STOP"
        elif self.hold:
            mode = "HOLD"
        elif moving:
            mode = "MOVING"
        else:
            mode = "ARMED_IDLE"
        if mode != old:
            self.mode = mode
            self._event("MODE", {"from": old, "to": mode})
        if self._presence_class() not in ("HEAD_DIRECT", "HEAD_VIA_LAB_EXTENSION") and self.head_power["electronics"]:
            self.head_power = {"electronics": False, "heater_enable": False}
            self._event("HEAD_POWER", {"electronics": False, "heater_enable": False, "why": "PRESENCE"})

    # ------------------------------------------------------------------ motion
    def _physics(self, dt):
        now = self.clock.now_us()
        tv = tw = 0.0
        armed = self.hw_latch and not self.sw_reasons and not self.hold
        if self.cmd is not None:
            if now >= self.cmd[2]:
                nonzero = self.cmd[0] != 0 or self.cmd[1] != 0
                self.cmd = None
                if nonzero and armed:
                    self._pstop("CMD_TIMEOUT")
            elif armed:
                tv, tw = self.cmd[0], self.cmd[1]
        if armed and self._last_req is not None and now - self._last_req > self.config["link.timeout_ms"] * 1000:
            self._pstop("HOST_LINK_LOST")
            tv = tw = 0.0
        if armed:
            for r in self._sw_active():
                self._pstop(r)
            if tv < 0 and self.inputs["rear_blocked"]:
                self._pstop("FIELD_REAR")
        if self.sw_reasons or self.hold or not self.hw_latch:
            tv = tw = 0.0
        at_rest = abs(self.v) < 1e-6 and abs(self.w) < 1e-6
        if (tv or tw) and at_rest and self.motion in ("REST",):
            if now - self._rest_since > self.config["alert.rest_ms"] * 1000:
                self._alert_until = now + int(self.config["alert.premotion_ms"] * 1000)
                self.motion = "ALERT"
            else:
                self.motion = "RUN"
        if self.motion == "ALERT":
            if not (tv or tw):
                self.motion = "REST"
            elif now >= self._alert_until:
                self.motion = "RUN"
            else:
                tv = tw = 0.0
        if not self.hw_latch:
            self.v = self.w = 0.0                # brake relays: hard stop in the fake
        else:
            dec = 1.0 if self.sw_reasons else 0.40
            dv = tv - self.v
            lim = (0.30 if abs(tv) > abs(self.v) else dec) * dt
            self.v += max(-lim, min(lim, dv))
            dw = tw - self.w
            self.w += max(-1.5 * dt, min(1.5 * dt, dw))
        moving = abs(self.v) > 1e-6 or abs(self.w) > 1e-6
        if moving:
            self.motion = "RUN" if (tv or tw) else "DECEL"
            self._rest_since = now
            self._stat_since = None
        else:
            if self.motion != "ALERT":
                self.motion = "REST"
            if self._stat_since is None:
                self._stat_since = self.now_us()
        slip = self.inputs["slip"]
        vl, vr = self.v - self.w * self.track / 2, self.v + self.w * self.track / 2
        k = self.cpr / (2 * math.pi * self.radius)
        self.left_ticks += vl * dt * k
        self.right_ticks += vr * dt * k
        tv_true, tw_true = self.v * (1 - slip), self.w
        self.yaw += tw_true * dt
        self.x += tv_true * dt * math.cos(self.yaw)
        self.y += tv_true * dt * math.sin(self.yaw)

    # ---------------------------------------------------------------- protocol
    def step(self):
        now = self.clock.now_us()
        if self._last_step is not None and now > self._last_step:
            self._physics((now - self._last_step) * 1e-6)
        self._last_step = now
        self._update_mode()
        if self._brake and now >= self._brake[2]:
            tid, raw, _ = self._brake
            self._brake = None
            self.hw_latch = False
            self.brake_passed = True
            self._event("BRAKE_TEST", {"passed": True, "fail": []})
            self._event("HW_LATCH", {"set": False, "reasons": []})
            self._update_mode()
            self._reply(tid, "BRAKE_TEST", raw, "OK", {"passed": True, "fail": [], "latch_drop_ms": 6, "relay_ms": 9,
                        "vmot_decay_ms": 140, "vmot_end_v": 0.3, "probe_i_a": [0.0, 0.0], "moved_ticks": [0, 0],
                        "mode": self.mode})
        data = self.transport.read()
        if self.inputs["usb_down"] or not data:
            return
        for raw, rec, _err in self._decoder.feed(data):
            if rec is not None:
                self._handle(rec, raw)

    def _reply(self, tid, op, raw, status, body):
        line = wire.encode({"type": "RSP", "v": "1.0", "id": tid, "status": status, "body": body}, MAX_RECORD)
        self._cache = (tid, op, line)
        self.transport.write(line)

    def _telemetry(self):
        t = self.now_us()
        k = self.cpr / (2 * math.pi * self.radius)
        vl, vr = self.v - self.w * self.track / 2, self.v + self.w * self.track / 2
        stat = self._stat_since is not None and t - self._stat_since >= self.config["stationary.min_ms"] * 1000
        return {"mode": self.mode,
                "odom": {"t_us": t, "left_ticks": int(round(self.left_ticks)), "right_ticks": int(round(self.right_ticks)),
                         "left_tps": round(vl * k, 2), "right_tps": round(vr * k, 2)},
                "imu": {"t_us": t - 5000, "gyro_rps": [0.0, 0.0, round(self.w + self.gyro_bias + self.rng.gauss(0, self.gyro_noise), 5)],
                        "accel_mps2": [0.0, 0.0, 9.81], "ok": True},
                "stops": {"hw": list(self.hw_reasons), "sw": list(self.sw_reasons)}, "event_seq": self.event_seq,
                "stationary": {"is_stationary": bool(stat), "since_us": self._stat_since},
                "applied": {"v_mps": round(self.v, 4), "w_radps": round(self.w, 4)}, "motion": self.motion,
                "allow": {"fwd": not self.inputs["cliff"], "rev": not self.inputs["rear_blocked"], "pivot": True},
                "v_cap_mps": CAPS[self.op_mode][0], "hold": list(self.hold), "rearm_nonce": self.nonce}

    def _handle(self, req, raw):
        tid, op, args = req.get("id"), req.get("op"), req.get("args")
        if req.get("type") != "REQ" or type(tid) is not int:
            return
        self._last_req = self.clock.now_us()
        rx = self.now_us()
        if self._cache[0] == tid and self._cache[1] == op:
            self.transport.write(self._cache[2])
            return
        if not str(req.get("v", "")).startswith("1."):
            return self._reply(tid, op, raw, "UNSUPPORTED", {"reason": "VERSION"})
        if not isinstance(args, dict):
            return self._reply(tid, op, raw, "BAD_ARG", {"reason": "args"})
        if self._brake is not None:
            if op == "BRAKE_TEST" and tid == self._brake[0]:
                return
            return self.transport.write(wire.encode({"type": "RSP", "v": "1.0", "id": tid, "status": "BUSY",
                                                     "body": {"reason": "BRAKE_TEST", "state": "RUNNING"}}))
        if op in SESSION_OPS and self.session == 0:
            if op == "DRIVE":
                return self._reply(tid, op, raw, "OK", dict(self._telemetry(), accepted=False, reject_reason="NO_SESSION"))
            return self._reply(tid, op, raw, "REJECTED", {"reason": "NO_SESSION", "mode": self.mode})
        handler = getattr(self, "_op_" + str(op), None)
        if handler is None:
            return self._reply(tid, op, raw, "UNSUPPORTED", {"reason": "op"})
        out = handler(args, rx, tid, raw)
        if out is not None:
            self._reply(tid, op, raw, out[0], out[1])

    def _op_HELLO(self, a, rx, tid, raw):
        if self.mode == "MOVING":
            self._pstop("HOST_LINK_LOST")
        self.session += 1
        self.last_seq = -1
        self._event("LINK", {"up": True, "session": self.session})
        return "OK", {"fw": "rr-chassis py-fake 0.4", "hw_rev": "SIM", "serial": "RRC-000000", "boot_id": self.boot_id,
                      "proto": "RR-CHS 1.0",
                      "caps": {"encoder_cpr": self.cpr, "wheel_radius_nom_m": self.radius, "track_nom_m": self.track,
                               "max_v_mps": 0.2, "max_w_radps": 0.3, "max_rev_mps": 0.05, "max_accel_mps2": 0.3,
                               "ttl_ms_max": 250, "drive_hz": 50, "odom_hz": 100, "record_max": MAX_RECORD,
                               "events_retained": 128, "tof_count": 11},
                      "session": self.session, "uptime_us": self.now_us(),
                      "reset": {"cause": "POWER_ON", "boot_count": self._boot_count},
                      "config": {"gen": 1, "crc": "00000000", "source": "DEFAULTS"}}

    def _op_TIME(self, a, rx, tid, raw):
        return "OK", {"rx_us": rx, "tx_us": self.now_us() + 40}

    def _op_DRIVE(self, a, rx, tid, raw):
        seq, v, w, ttl, om = a.get("seq"), a.get("v_mps"), a.get("w_radps"), a.get("ttl_ms"), a.get("op_mode")
        num = (int, float)
        if (type(seq) is not int or not isinstance(v, num) or not isinstance(w, num) or type(ttl) is not int
                or not 1 <= ttl <= 250 or abs(v) > 0.5 or abs(w) > 1.0 or om not in CAPS):
            return "BAD_ARG", {"reason": "DRIVE"}
        reason = None
        cap = CAPS[self.op_mode]
        if seq <= self.last_seq:
            reason = "SEQ"
        elif self.mode in ("BOOT", "FAULT", "SERVICE_CHARGE", "LAB", "STANDBY", "HW_INHIBIT", "PROTECTIVE_STOP", "HOLD"):
            reason = self.mode
        elif om != self.op_mode:
            reason = "OP_MODE"
        elif v > cap[0] + 1e-9 or -v > cap[1] + 1e-9 or abs(w) > cap[2] + 1e-9:
            reason = "LIMIT"
        elif (v or w) and self.config["safety.require_brake_test"] and not self.brake_passed:
            reason = "BRAKE_TEST_REQUIRED"
        elif (v < 0 and self.inputs["rear_blocked"]) or (v > 0 and self.inputs["cliff"]):
            reason = "DIR_INHIBITED"
        if reason is None:
            self.last_seq = seq
            self.cmd = (float(v), float(w), self.clock.now_us() + ttl * 1000)
        body = self._telemetry()
        body.update(accepted=reason is None, reject_reason=reason)
        return "OK", body

    def _op_STATE(self, a, rx, tid, raw):
        t = self._telemetry()
        charge = "CC" if self.inputs["chg_plug"] else "NONE"
        return "OK", {"mode": self.mode, "op_mode": self.op_mode, "hw_latch": self.hw_latch, "chain": self._chain(),
                      "hw_inhibit_reasons": list(self.hw_reasons), "protective_stop_reasons": list(self.sw_reasons),
                      "head_presence": self._presence_class(), "j2_present": bool(self.inputs["j2"]),
                      "rails": {"vbat_v": 13.1, "vmot_v": 13.0 if self.hw_latch else 0.2, "ibat_a": 1.4, "v5_v": 5.09},
                      "battery": {"soc_pct": 80, "temp_c": [18.0, 18.5], "charge_state": charge},
                      "temps": {"board_c": 24.0, "bay_c": 19.0}, "tof": [], "bumpers": {
                          "body_l": bool(self.inputs["bumper_l"]), "body_r": bool(self.inputs["bumper_r"]),
                          "head_loop": "OK" if 600 <= self.inputs["loop_ohm"] <= 1600 else "OPEN"},
                      "panel": {"buttons": {"rearm": False, "pause": False}, "pattern": self.panel},
                      "heater": {"chassis_duty_pct": 0}, "faults": [], "sw_active": self._sw_active(),
                      "hw_active": self._hw_active(), "stationary": t["stationary"],
                      "rearm_ready": (not self.hw_latch) and all(self._chain().values()),
                      "rearm_nonce": self.nonce, "hold": list(self.hold), "head_power": dict(self.head_power),
                      "brake_test": {"state": "PASSED" if self.brake_passed else "NONE"},
                      "event_seq": self.event_seq, "uptime_us": self.now_us()}

    def _op_EVENTS(self, a, rx, tid, raw):
        after = a.get("after_seq")
        if type(after) is not int or after < 0:
            return "BAD_ARG", {"reason": "after_seq"}
        evs = [e for e in self.events if e["seq"] > after][:12]
        oldest = self.events[0]["seq"] if self.events else 0
        return "OK", {"events": evs, "newest_seq": self.event_seq, "oldest_seq": oldest,
                      "more": bool(evs) and evs[-1]["seq"] < self.event_seq, "gap": after + 1 < oldest}

    def _op_REARM_SW(self, a, rx, tid, raw):
        op_name = a.get("operator")
        if type(a.get("nonce")) is not int or not isinstance(op_name, str) or not 1 <= len(op_name) <= 32:
            return "BAD_ARG", {"reason": "REARM_SW"}
        if a["nonce"] != self.nonce:
            self._event("REARM_REJECT", {"why": "NONCE", "operator": op_name})
            return "REJECTED", {"reason": "NONCE", "mode": self.mode, "rearm_nonce": self.nonce}
        active = self._sw_active()
        if active:
            self._event("REARM_REJECT", {"why": "CAUSE_ACTIVE", "operator": op_name})
            return "REJECTED", {"reason": "CAUSE_ACTIVE", "active": active, "mode": self.mode}
        cleared, hold = list(self.sw_reasons), list(self.hold)
        self.sw_reasons, self.hold = [], []
        self._new_nonce()
        self._event("PSTOP_CLEAR", {"by": "REARM_SW", "operator": op_name, "cleared": cleared})
        self._update_mode()
        return "OK", {"cleared": cleared, "hold_cleared": hold, "mode": self.mode, "hw_latch": self.hw_latch,
                      "rearm_nonce": self.nonce}

    def _op_STOP(self, a, rx, tid, raw):
        kind = a.get("kind")
        if kind == "CONTROLLED":
            if "HOST_STOP" not in self.hold:
                self.hold.append("HOST_STOP")
                self._new_nonce()
                self._event("HOLD", {"on": True, "why": "HOST_STOP"})
            self.cmd = None
        elif kind == "PROTECTIVE":
            self._pstop(a.get("reason", "HOST_REQUEST"))
        else:
            return "BAD_ARG", {"reason": "kind"}
        self._update_mode()
        return "OK", {"mode": self.mode, "stops": {"hw": list(self.hw_reasons), "sw": list(self.sw_reasons)},
                      "hold": list(self.hold), "rearm_nonce": self.nonce}

    def _op_SET_OP_MODE(self, a, rx, tid, raw):
        om = a.get("op_mode")
        if om not in CAPS:
            return "BAD_ARG", {"reason": "op_mode"}
        if abs(self.v) > 1e-6 or abs(self.w) > 1e-6 or self.cmd and (self.cmd[0] or self.cmd[1]):
            return "REJECTED", {"reason": "NOT_STATIONARY", "mode": self.mode}
        self._event("OP_MODE", {"from": self.op_mode, "to": om})
        self.op_mode = om
        c = CAPS[om]
        return "OK", {"op_mode": om, "caps": {"v_fwd_mps": c[0], "v_rev_mps": c[1], "w_radps": c[2]}}

    def _op_HEAD_POWER(self, a, rx, tid, raw):
        el, ht = a.get("electronics"), a.get("heater_enable")
        if type(el) is not bool or type(ht) is not bool or (ht and not el):
            return "BAD_ARG", {"reason": "HEAD_POWER"}
        if (el or ht) and self.mode in ("SERVICE_CHARGE", "BOOT", "FAULT"):
            return "REJECTED", {"reason": self.mode, "mode": self.mode}
        if (el or ht) and self._presence_class() not in ("HEAD_DIRECT", "HEAD_VIA_LAB_EXTENSION"):
            return "REJECTED", {"reason": "HEAD_ABSENT", "mode": self.mode}
        if self.head_power != {"electronics": el, "heater_enable": ht}:
            self.head_power = {"electronics": el, "heater_enable": ht}
            self._event("HEAD_POWER", {"electronics": el, "heater_enable": ht, "why": "HOST"})
        return "OK", dict(self.head_power, head_presence=self._presence_class())

    def _op_HEATER(self, a, rx, tid, raw):
        return "OK", {"chassis_setpoint_c": a.get("chassis_setpoint_c"), "duty_pct": 0, "bay_c": 19.0, "sensor_ok": True}

    def _op_PANEL(self, a, rx, tid, raw):
        self.panel = a.get("pattern", "AUTO")
        return "OK", {"pattern": self.panel, "leds": {}, "buzzer": False}

    def _op_CONFIG_GET(self, a, rx, tid, raw):
        key = a.get("key")
        if key not in self.config:
            return "BAD_ARG", {"reason": "key"}
        return "OK", {"key": key, "value": self.config[key], "rw": True}

    def _op_CONFIG_SET(self, a, rx, tid, raw):
        key, value = a.get("key"), a.get("value")
        if key not in self.config or not isinstance(value, (int, float)):
            return "BAD_ARG", {"reason": "key"}
        if self.mode == "MOVING":
            return "REJECTED", {"reason": "NOT_STATIONARY", "mode": self.mode}
        old = self.config[key]
        self.config[key] = float(value)
        self._event("CONFIG", {"key": key, "old": old, "new": float(value), "gen": 2})
        return "OK", {"key": key, "value": float(value), "old": old, "gen": 2, "crc": "00000000"}

    def _op_BRAKE_TEST(self, a, rx, tid, raw):
        if self.mode != "ARMED_IDLE":
            return "REJECTED", {"reason": "NOT_ARMED_IDLE", "mode": self.mode}
        self._brake = (tid, raw, self.clock.now_us() + 800_000)
        return None
