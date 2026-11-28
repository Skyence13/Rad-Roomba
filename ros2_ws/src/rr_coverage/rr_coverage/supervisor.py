"""Mission supervisor: Configure -> Ready -> Armed -> Scan -> Hold/Investigate
-> Resume/Abort -> Review (design 0.3 ch.7 "Survey execution and recovery"),
with the three survey methods of contract `survey_methods` (DEC-038).

Rules enforced here:
  * survey motion needs recorder, identity/calibration, clock fit and transforms
    (startup ordering); the chassis bridge stays inactive until `arm`;
  * a stop/fault never clears itself: HOLD needs a deliberate `rearm` (operator
    REARM_SW or the local button) and then a fresh `resume`; commands issued
    while inhibited are REJECTED, never queued;
  * turns, transits, holds and blocked waits earn no coverage credit (marks);
  * a blocked strip is deferred, its floor is marked BLOCKED and a return pass is
    attempted after the other passes; never-cleared strips stay as residuals;
  * after a hold inside a pass the robot backs up `recover_back_m` and re-surveys;
  * every completed task is checkpointed; a restart resumes as a new epoch.

No ROS imports.
"""
from __future__ import annotations

import math
from collections import deque

from rr_core import estimator as est
from rr_core.geometry import transform, wrap

from .planner import approach, transit

STATES = ("CONFIGURE", "READY", "ARMED", "SCAN", "HOLD", "REVIEW", "ABORTED", "SERVICE")


class MissionConfig:
    def __init__(self, op_mode="COMMISSIONING", method="CONTINUOUS_SCAN", speed=0.10, recover_back_m=0.15,
                 max_task_attempts=2, credit_grace_s=2.0, count_policy="INLINE", scaler_mode="PRESET_TIME",
                 scaler_preset_s=30.0, scaler_max_s=100.0, ratemeter_window_s=1.0, ratemeter_alpha=None,
                 station_pitch_m=0.08, settle_s=0.5, station_preset_s=10.0, refractory_m=0.10,
                 peak_search_m=0.15,
                 operator="operator"):
        self.__dict__.update(locals())
        del self.__dict__["self"]


class Mission:
    def __init__(self, app, plan: dict, cfg: MissionConfig):
        self.app, self.plan, self.cfg = app, plan, cfg
        self.state = "CONFIGURE"
        self.hold_reason = None
        self.tasks = plan["tasks"]
        self.region = plan["pivot_region"]
        self.phase = "NEXT"
        self.task = None
        self.retry_round = 0
        self.events = deque(maxlen=500)
        self.deferred_counts = []
        self.counted_spots = []
        self.count = None
        self.obs_n = 0
        self._rate = {n: deque(maxlen=400) for n in range(4)}
        self.ratemeter = {n: {"rate": None, "net": None, "alarm_level": None, "alarm": False} for n in range(4)}
        self._credit_bad_since = None
        self._station = None
        self._alert_rest_saved = None
        self._hold_ctx = None
        self.preflight_done = False
        self.finished = False

    # ---------------------------------------------------------------- helpers
    def _log(self, kind, **data):
        ev = dict(data, ev=kind, t_us=self.app.clock.now_us(), state=self.state)
        self.events.append(ev)
        self.app.log_event(ev)

    def _mark(self, **mark):
        t = self.app.clock.now_us()
        self.app.pipeline.record(t, "J", dict(mark, op="mark", t_us=t))

    def along_track_reference_missing(self):
        """Site rule (IB-30): in a trailer longer than the configured LiDAR range the along-trailer
        reference needs the doors closed or a removable flat target across the door end
        (`trailer.door_target_x_m`); otherwise survey motion is refused."""
        tr, rng = self.app.cfg["trailer"], float(self.app.cfg["lidar"]["range_max"])
        if tr["length_m"] <= rng or tr.get("door_closed") or tr.get("door_target_x_m") is not None:
            return None
        return (f"ALONG_TRACK_REFERENCE: trailer {tr['length_m']} m > LiDAR range {rng} m with the doors open - "
                "close the doors or place the door-end target and set trailer.door_target_x_m")

    def prerequisites(self):
        """Everything that must hold before survey motion (startup ordering)."""
        a = self.app
        missing = []
        if a.archive_error or a.pipeline.archive is None:
            missing.append("RECORDER")
        if a.head.state != "ARMED" or a.head.session is None:
            missing.append("HEAD_IDENTITY:" + str(a.head.block_reason or a.head.state))
        elif not (a.head.status()["bound_us"] is not None and a.head.status()["bound_us"] <= a.head.cfg.max_bound_us):
            missing.append("HEAD_CLOCK")
        if a.chassis.link_state != "UP":
            missing.append("CHASSIS_LINK")
        elif not math.isfinite(a.chassis.time_bound_us()) or a.chassis.time_bound_us() > a.head.cfg.max_bound_us:
            missing.append("CHASSIS_CLOCK")
        ref = self.along_track_reference_missing()
        if ref:
            missing.append(ref)
        if not a.loc.initialized:
            missing.append("TRANSFORMS:datum not registered")
        elif not a.loc.sample()["credit"]:
            missing.append("LOCALIZATION")
        mode = a.chassis.drive.get("mode")
        if mode not in ("ARMED_IDLE", "MOVING"):
            missing.append("CHASSIS_MODE:" + str(mode))
        if a.chassis.op_mode != self.cfg.op_mode:
            missing.append("OP_MODE")
        return missing

    # --------------------------------------------------------------- commands
    def command(self, name, args=None, actor="operator"):
        args = args or {}
        fn = getattr(self, "_cmd_" + name, None)
        if fn is None:
            return {"accepted": False, "reason": "UNKNOWN_COMMAND"}
        mode = self.app.chassis.drive.get("mode") or self.app.chassis.state.get("mode")
        if mode == "SERVICE_CHARGE" and name in ("preflight", "arm", "start", "resume"):
            return {"accepted": False, "reason": "CHARGE_SERVICE: traction inhibited"}
        out = fn(args, actor)
        self._log("command", name=name, actor=actor, accepted=out["accepted"], reason=out.get("reason"))
        return out

    def _cmd_preflight(self, args, actor):
        """Select the op_mode, switch head power on and run the stationary brake test
        (which drops the hardware latch: the operator presses the local REARM again)."""
        c = self.app.chassis
        if self.state not in ("CONFIGURE", "READY"):
            return {"accepted": False, "reason": "STATE:" + self.state}
        c.request("SET_OP_MODE", {"op_mode": self.cfg.op_mode})
        c.request("HEAD_POWER", {"electronics": True, "heater_enable": False})
        if c.drive.get("mode") == "ARMED_IDLE" and not self.preflight_done:
            c.request("BRAKE_TEST", {}, lambda r: setattr(self, "preflight_done", r["status"] == "OK" and r["body"].get("passed")))
        self.state = "READY"
        return {"accepted": True, "note": "press the local REARM button only when safety.rearm_prompt says so (rearm_ready), once, before and after the brake test"}

    def _cmd_arm(self, args, actor):
        if self.state not in ("READY", "CONFIGURE"):
            return {"accepted": False, "reason": "STATE:" + self.state}
        self.app.chassis.activate(True)
        missing = [m for m in self.prerequisites() if m != "BRIDGE"]
        if missing:
            self.app.chassis.activate(False)
            return {"accepted": False, "reason": "PREREQUISITES", "missing": missing}
        self.state = "ARMED"
        return {"accepted": True}

    def _cmd_start(self, args, actor):
        if self.state != "ARMED":
            return {"accepted": False, "reason": "STATE:" + self.state}
        missing = self.prerequisites()
        if missing:
            return {"accepted": False, "reason": "PREREQUISITES", "missing": missing}
        self.state, self.phase = "SCAN", "NEXT"
        self._mark(stage=None, reason="MISSION_START", method=self.cfg.method)
        return {"accepted": True}

    def _cmd_pause(self, args, actor):
        if self.state != "SCAN":
            return {"accepted": False, "reason": "STATE:" + self.state}
        self.app.chassis.stop("CONTROLLED")
        self._enter_hold("OPERATOR_PAUSE")
        return {"accepted": True}

    def _cmd_rearm(self, args, actor):
        """Deliberate software re-arm by the controlling operator (never sets the hardware latch)."""
        c = self.app.chassis
        d = c.drive
        if d.get("stops", {}).get("hw") or d.get("mode") in ("HW_INHIBIT", "STANDBY"):
            return {"accepted": False, "reason": "LOCAL_REARM_REQUIRED",
                    "detail": "hardware latch can only be set with the REARM button on the robot"}
        c.rearm_sw(actor)
        return {"accepted": True}

    def _cmd_resume(self, args, actor):
        if self.state != "HOLD":
            return {"accepted": False, "reason": "STATE:" + self.state}
        missing = self.prerequisites()
        if missing:
            return {"accepted": False, "reason": "PREREQUISITES", "missing": missing}   # rejected, not queued
        self.state, self.hold_reason = "SCAN", None
        self.phase = "RECOVER"
        return {"accepted": True}

    def _cmd_defer(self, args, actor):
        """Skip the task that is held/blocked; its floor stays open for a return pass."""
        if self.state != "HOLD" or self.task is None:
            return {"accepted": False, "reason": "NOTHING_TO_DEFER"}
        self._defer_task("OPERATOR_DEFER")
        return {"accepted": True}

    def _cmd_abort(self, args, actor):
        if self.state in ("REVIEW", "ABORTED"):
            return {"accepted": False, "reason": "STATE:" + self.state}
        self.app.mover.cancel("ABORT")
        self.app.chassis.clear_command()
        self._mark(stage=None, reason="ABORT")
        self._finish("ABORTED")
        return {"accepted": True}

    def _cmd_end(self, args, actor):
        if self.state not in ("HOLD", "ARMED"):
            return {"accepted": False, "reason": "STATE:" + self.state}
        self._finish("ENDED_BY_OPERATOR")
        return {"accepted": True}

    # ------------------------------------------------------------------ holds
    def _enter_hold(self, reason):
        if self.state == "HOLD":
            return
        mover = self.app.mover
        self._hold_ctx = {"phase": self.phase, "pose": tuple(mover.pose) if mover.pose else None, "reason": reason}
        mover.cancel(reason, state="IDLE")
        self.app.chassis.clear_command()
        self._mark(stage=None, reason="HOLD:" + reason)
        if self.count is not None:
            self._end_count(valid=False, reason="HOLD:" + reason)
        if self._station is not None and self._station.get("t_a") is not None:
            self._mark(stage=None, reason="STATION_ABORT", station_end=self._station["tag"], valid=False)
            self._station["t_a"] = None
        self.state, self.hold_reason = "HOLD", reason
        self._log("hold", reason=reason)
        self.app.checkpoint()

    def _defer_task(self, why):
        t = self.task
        if t is None:
            return
        if t.get("maneuver") and t.get("phase_reached") in ("WALL_ENTRY", "PASS"):
            self._wall_abandon(why, move=self.state == "SCAN")     # in HOLD: the return runs on Resume
            return
        pose = self.app.mover.pose
        lay = self.plan["layout"]
        dirn = 1.0 if abs(t["heading"]) < 1 else -1.0
        xa = pose[0] + dirn * lay["x_min"] if t["phase_reached"] == "PASS" else t["x_start"] + dirn * lay["x_min"]
        xb = t["x_end"] + dirn * lay["x_max"]
        rect = (min(xa, xb), max(xa, xb), t["y"] + lay["y_lo"] - 0.0, t["y"] + lay["y_hi"])
        tt = self.app.clock.now_us()
        self.app.pipeline.record(tt, "J", {"op": "blocked", "rect": [round(v, 4) for v in rect], "reason": why, "t_us": tt})
        t["status"] = "DEFERRED"
        t["defer_reason"] = why
        self._log("task_deferred", task=t["id"], reason=why, rect=rect)
        self.task = None
        self.phase = "NEXT"
        if self.state == "HOLD":
            self._hold_ctx = None

    # ------------------------------------------------------------------- step
    def step(self):
        a = self.app
        mode = a.chassis.drive.get("mode") or a.chassis.state.get("mode")
        if mode == "SERVICE_CHARGE" and self.state not in ("SERVICE", "REVIEW"):
            if self.state == "SCAN":
                self._enter_hold("CHARGER_CONNECTED")
            self._prev_state, self.state = self.state, "SERVICE"
            a.chassis.activate(False)
        elif self.state == "SERVICE" and mode != "SERVICE_CHARGE":
            self.state = "HOLD" if self._prev_state in ("SCAN", "HOLD") else "CONFIGURE"   # stays inactive until deliberate setup
            self.hold_reason = "CHARGER_REMOVED"
        if self.state != "SCAN":
            return
        mover = a.mover
        for ev in mover.events:
            if ev["ev"] == "prim_start":
                p = ev["prim"]
                self._mark(stage=p.get("stage"), tag=p.get("tag"), reason=p.get("why") or p["kind"].upper())
            elif ev["ev"] == "path_error" and self.phase == "PASS":
                p = mover.prim or {}
                self._mark(stage=None if ev["on"] else p.get("stage"), tag=p.get("tag"), reason="PATH_ERROR")
            elif ev["ev"] in ("blocked_wait", "blocked_cleared") and mover.prim is not None:
                p = mover.prim
                self._mark(stage=None if ev["ev"] == "blocked_wait" else p.get("stage"), tag=p.get("tag"), reason="BLOCKED_WAIT")
        mover.events.clear()
        # acquisition supervision (independent of the web interface)
        why = None
        cmode = a.chassis.drive.get("mode")
        if cmode not in ("ARMED_IDLE", "MOVING") and a.chassis.link_state == "UP":
            st = a.chassis.drive.get("stops", {})
            self._enter_hold(f"CHASSIS:{cmode}:" + ",".join(st.get("hw", []) + st.get("sw", []) + a.chassis.drive.get("hold", [])))
            return
        if a.archive_error:
            why = "RECORDER:" + str(a.archive_error)
        elif a.head.state != "ARMED":
            why = "HEAD_LINK:" + str(a.head.block_reason or a.head.state)
        elif a.loc.status()["hold_request"]:
            why = "LOCALIZATION"
        else:
            if a.loc.sample()["credit"]:
                self._credit_bad_since = None
            elif self._credit_bad_since is None:
                self._credit_bad_since = a.clock.now_us()
            elif a.clock.now_us() - self._credit_bad_since > self.cfg.credit_grace_s * 1e6:
                why = "LOCALIZATION"
        if why:
            a.chassis.stop("PROTECTIVE", "HEAD_LINK" if why.startswith("HEAD") else
                           ("LOCALIZATION" if why == "LOCALIZATION" else "HOST_REQUEST"))
            self._enter_hold(why)
            return
        if mover.state == "HELD":
            self._enter_hold(mover.reason)
            return
        if mover.state == "FAILED":
            a.chassis.stop("PROTECTIVE", "HOST_REQUEST")
            self._enter_hold("MOTION:" + str(mover.reason))
            return
        getattr(self, "_ph_" + self.phase)()

    # ----------------------------------------------------------------- phases
    def _start(self, prims):
        ok, why = self.app.mover.start(prims, source="survey")
        if not ok:
            self._enter_hold("START_REFUSED:" + why)
        return ok

    def _pass_prim(self, t, x_to=None):
        return {"kind": "straight", "to": (t["x_end"] if x_to is None else x_to, t["y"]), "reverse": False,
                "stage": t["stage"] if self.cfg.method != "STEP_AND_COUNT" else None, "tag": t["id"],
                "why": "PASS", "route": "planning", "speed": self.cfg.speed}

    def _ph_NEXT(self):
        pending = [t for t in self.tasks if t["status"] == "PENDING"]
        if not pending:
            retry = [t for t in self.tasks if t["status"] == "DEFERRED" and t["attempts"] < self.cfg.max_task_attempts]
            if retry and self.retry_round < self.cfg.max_task_attempts:
                self.retry_round += 1
                for t in retry:
                    t["status"] = "PENDING"          # return passes after the other passes
                self._log("return_passes", tasks=[t["id"] for t in retry])
                return
            if self.deferred_counts:
                self.phase = "DEFERRED_COUNT"
                return
            self._finish("COMPLETE")
            return
        t = self.task = pending[0]
        t["attempts"] += 1
        t["phase_reached"] = "TRANSIT"
        man = t.get("maneuver")
        target = tuple(man["entry_pose"]) if man else (t["x_start"], t["y"], t["heading"])
        prims = transit(self.app.mover.pose, target, self.region)
        for p in prims:
            p.setdefault("route", "planning")
        self.phase = "TRANSIT"
        if prims:
            self._start(prims)
        self._log("task_start", task=t["id"], name=t["name"])

    def _ph_TRANSIT(self):
        m = self.app.mover
        if m.state == "BLOCKED":
            self._defer_task("TRANSIT_BLOCKED")
        elif m.state in ("DONE", "IDLE"):
            if self.task.get("maneuver"):
                self._wall_entry()
            else:
                self._begin_pass()

    # ------------------------------------------------ wall tracks (reverse entry, CR-06 / IB-29)
    def _wall_prims(self, key):
        return [dict(p, route="planning") if not p.get("reverse") else dict(p) for p in self.task["maneuver"][key]]

    def _wall_entry(self):
        """Reverse along the planned diagonal onto the wall track, then the small align pivot.
        No coverage credit (no stage).  The reverse relies on the chassis rear field; a refused or
        stopped reverse ends the attempt: the robot returns to the entry point and the strip stays
        a residual (never retried blindly)."""
        self.task["phase_reached"] = "WALL_ENTRY"
        self.phase = "WALL_ENTRY"
        self._log("wall_entry", task=self.task["id"])
        self._start(self._wall_prims("entry"))

    def _ph_WALL_ENTRY(self):
        if self.app.mover.state in ("DONE", "IDLE"):
            self._begin_pass()

    def _ph_WALL_EXIT(self):
        if self.app.mover.state in ("DONE", "IDLE"):
            self.task["_exited"] = True
            self._task_done()

    def _ph_WALL_RETURN(self):
        """Back to the entry point along the verified entry path after an abandoned wall track."""
        if self.app.mover.state in ("DONE", "IDLE"):
            t = self.task
            self._log("wall_returned", task=t["id"])
            self.task = None
            self.phase = "NEXT"

    def _wall_return_prims(self, pose):
        """From anywhere on the entry path or the track: reverse along the track to its start E,
        pivot back to the entry heading, forward along the diagonal to the entry point P
        (the exact reverse of the verified entry, so the swept region is the checked one)."""
        t, man = self.task, self.task["maneuver"]
        h, h_m = t["heading"], man["h_m"]
        P = man["entry_pose"]
        prims = []
        if abs(wrap(pose[2] - h)) < 0.03:
            if math.hypot(pose[0] - t["x_start"], pose[1] - t["y"]) > 0.003:
                prims.append({"kind": "straight", "to": (t["x_start"], t["y"]), "reverse": True, "why": "WALL_RETURN_BACK",
                              "speed": self.app.mover.cfg.reverse_speed})
        prims.append({"kind": "pivot", "yaw": h_m, "why": "WALL_RETURN_PIVOT"})
        prims.append({"kind": "straight", "to": (P[0], P[1]), "reverse": False, "why": "WALL_RETURN", "route": "planning"})
        return prims

    def _wall_exit_prims(self, pose):
        """Resume an interrupted exit: finish the back-off, the peel pivot and the diagonal."""
        t, man = self.task, self.task["maneuver"]
        h = t["heading"]
        ex = man["exit"]
        prims = []
        if abs(wrap(pose[2] - h)) < 0.03:
            fb = ex[0]["to"]
            if math.hypot(pose[0] - fb[0], pose[1] - fb[1]) > 0.003:
                prims.append(dict(ex[0]))
        prims += [dict(ex[1]), dict(ex[2], route="planning")]
        return prims

    def _wall_abandon(self, why, move=True):
        """Stop using this wall track for this mission: residual recorded, robot returns to P."""
        t = self.task
        pose = self.app.mover.pose
        lay = self.plan["layout"]
        dirn = 1.0 if abs(t["heading"]) < 1 else -1.0
        rect = (min(t["x_start"] + dirn * lay["x_min"], t["x_end"] + dirn * lay["x_max"]),
                max(t["x_start"] + dirn * lay["x_min"], t["x_end"] + dirn * lay["x_max"]),
                t["y"] + lay["y_lo"], t["y"] + lay["y_hi"])
        tt = self.app.clock.now_us()
        self.app.pipeline.record(tt, "J", {"op": "blocked", "rect": [round(v, 4) for v in rect], "reason": why, "t_us": tt})
        t["status"] = "RESIDUAL"                      # not retried: the strip stays a reported residual
        t["defer_reason"] = why
        self._log("wall_track_abandoned", task=t["id"], reason=why, rect=rect)
        self.phase = "WALL_RETURN"
        if move:
            self._start(self._wall_return_prims(pose))
        else:
            self._hold_ctx = {"phase": "WALL_RETURN", "pose": tuple(pose) if pose else None, "reason": why}

    def _begin_pass(self):
        t = self.task
        t["phase_reached"] = "PASS"
        if self.cfg.method == "STEP_AND_COUNT":
            dirn = 1.0 if abs(t["heading"]) < 1 else -1.0
            n = int(math.floor(abs(t["x_end"] - t["x_start"]) / self.cfg.station_pitch_m + 1e-6))
            t.setdefault("stations", [round(t["x_start"] + dirn * i * self.cfg.station_pitch_m, 5) for i in range(n + 1)])
            t.setdefault("station_i", 0)
            if self._alert_rest_saved is None:
                # one full pre-motion alert per series, a chirp per hop (owner decision 2026-11-26)
                self._alert_rest_saved = 2000.0
                self.app.chassis.request("CONFIG_GET", {"key": "alert.rest_ms"},
                                         lambda r: setattr(self, "_alert_rest_saved", r["body"].get("value", 2000.0)))
                ms = (self.cfg.station_preset_s + self.cfg.settle_s + 5.0) * 1000.0
                self.app.chassis.request("CONFIG_SET", {"key": "alert.rest_ms", "value": ms})
                self._log("config_set", key="alert.rest_ms", value=ms, why="STEP_AND_COUNT series")
            self.phase = "STEP_MOVE"
            self._station = None
            return
        self.phase = "PASS"
        self._start([self._pass_prim(t)])

    def _ph_PASS(self):
        m = self.app.mover
        if m.state == "BLOCKED":
            self._mark(stage=None, reason="STRIP_BLOCKED")
            self._defer_task("STRIP_BLOCKED")
        elif m.state == "DONE":
            self._task_done()

    def _task_done(self):
        t = self.task
        if t.get("maneuver") and not t.get("_exited"):
            self._mark(stage=None, reason="PASS_END")
            self.phase = "WALL_EXIT"
            self._log("wall_exit", task=t["id"])
            self._start(self._wall_prims("exit"))
            return
        self._mark(stage=None, reason="PASS_END")
        self.task["status"] = "DONE"
        self._log("task_done", task=self.task["id"])
        self.task = None
        self.phase = "NEXT"
        t = self.app.clock.now_us()
        self.app.pipeline.record(t, "J", {"op": "evaluate"})
        self.app.checkpoint()

    def _ph_RECOVER(self):
        """After a hold: back up along the pass and re-survey from verified overlap."""
        ctx, t = self._hold_ctx or {}, self.task
        self._hold_ctx = None
        if t is None:
            self.phase = "NEXT"
            return
        pose = self.app.mover.pose
        was = ctx.get("phase")
        if t.get("maneuver") and was in ("WALL_ENTRY", "WALL_RETURN"):
            # a stopped or refused reverse entry is not retried: back out along the entry path
            if was == "WALL_ENTRY":
                self._wall_abandon("WALL_ENTRY_STOPPED:" + str(ctx.get("reason")))
            else:
                self.phase = "WALL_RETURN"
                self._start(self._wall_return_prims(pose))
            return
        if t.get("maneuver") and was == "WALL_EXIT":
            self.phase = "WALL_EXIT"
            self._start(self._wall_exit_prims(pose))
            return
        if was in ("PASS", "COUNT", "COUNT_BACK", "PASS_RESUME") or (was or "").startswith("STEP"):
            dirn = 1.0 if abs(t["heading"]) < 1 else -1.0
            if self.cfg.method == "STEP_AND_COUNT":
                self.phase = "STEP_MOVE"
                self._station = None
                return
            back = pose[0] - dirn * self.cfg.recover_back_m
            back = max(back, t["x_start"]) if dirn > 0 else min(back, t["x_start"])
            prims = []
            if abs(back - pose[0]) > 0.003:
                prims.append({"kind": "straight", "to": (back, t["y"]), "reverse": True, "why": "RECOVER_BACK"})
            prims.append(self._pass_prim(t))
            self.phase = "PASS"
            self._start(prims)
        else:
            t["status"] = "PENDING"
            t["attempts"] -= 1
            self.task = None
            self.phase = "NEXT"

    # ------------------------------------------------------- step-and-count
    def _ph_STEP_MOVE(self):
        t, m = self.task, self.app.mover
        if self._station is None:
            if t["station_i"] >= len(t["stations"]):
                self._task_done()
                return
            x = t["stations"][t["station_i"]]
            self._station = {"tag": f"{t['id']}-S{t['station_i']:03d}", "x": x, "tries": 0, "t_a": None}
            if abs(x - m.pose[0]) > 0.003:
                self._start([{"kind": "straight", "to": (x, t["y"]), "reverse": False, "why": "HOP", "tag": t["id"],
                              "route": "planning", "speed": self.cfg.speed, "creep_m": 0.03}])
                return
        if m.state == "BLOCKED":
            self._station = None
            self._defer_task("STRIP_BLOCKED")
        elif m.state in ("DONE", "IDLE"):
            self._station["t_settle"] = self.app.clock.now_us()
            self.phase = "STEP_SETTLE"

    def _ph_STEP_SETTLE(self):
        a, s = self.app, self._station
        st = a.chassis.drive.get("stationary") or {}
        if a.clock.now_us() - s["t_settle"] >= self.cfg.settle_s * 1e6 and st.get("is_stationary"):
            s["t_a"] = a.clock.now_us()
            self._mark(stage="SCALER", station=s["tag"], tag=self.task["id"], reason="STATION_COUNT")
            self.phase = "STEP_COUNT"

    def _ph_STEP_COUNT(self):
        a, s, t = self.app, self._station, self.task
        now = a.clock.now_us()
        if s.get("t_b") is None:
            if now - s["t_a"] >= self.cfg.station_preset_s * 1e6:
                s["t_b"] = now
                self._mark(stage=None, reason="STATION_DONE")
            return
        if a.chassis.drive.get("_t_host", 0) < s["t_b"] or now - s["t_b"] < 60_000:
            return                                  # need a stationary sample taken after the window
        ok, why = a.chassis.stationary_window_valid(s["t_a"], s["t_b"])
        self._mark(stage=None, reason="STATION_END", station_end=s["tag"], valid=ok, pose=list(a.mover.pose),
                   why=why)
        s["tries"] += 1
        if ok or s["tries"] >= 2:
            t["station_i"] += 1
            self._station = None
            if t["station_i"] % 10 == 0:
                a.checkpoint()
        else:
            s["t_a"] = s["t_b"] = None
            s["t_settle"] = now
            self.phase = "STEP_SETTLE"
            return
        self.phase = "STEP_MOVE"

    # ------------------------------------------------------ search-then-count
    def on_gate(self, gate):
        """Search-stage ratemeter (MODEL.md rev 5 section 3 "Search stage", review M2): per lane the section-6 statistic
        (m = 1, weights 1) over the trailing dwell (`ratemeter_window_s`, nominally L/v), U_null from a PAST-ONLY reference
        under the section-3 rule (two past sub-windows, larger mean; lane, else ratio-scaled four-lane pool; never the
        gates under test), predictive threshold at alpha_scan, decision class of the profile.  Provisional: it triggers
        recounts only.  Thresholds are cached on a quantised key (U_null 1 % log grid, window count to 1, live times to
        1 ms; the threshold is computed from the quantised inputs) - the recorded cell decision never uses this cache."""
        from rr_core import unull
        from rr_core.processing import CHANNELS
        from rr_core.profiles import CLASS_OF_CHANNEL
        a = self.app
        proc = a.pipeline.proc
        n_win = max(1, int(round(self.cfg.ratemeter_window_s * 1e6 / gate["span_us"])))
        searching = (self.state == "SCAN" and self.phase == "PASS" and self.cfg.method == "SEARCH_THEN_COUNT"
                     and a.mover.state == "RUNNING")
        prof = proc.profile
        alpha = self.cfg.ratemeter_alpha or prof["alpha_per_decision"]
        channel = next(ch for ch in CHANNELS if CLASS_OF_CHANNEL[ch] == prof["decision_class"])
        att = gate["attachment"]
        try:
            a_idx = proc.a_index(att)
        except KeyError:
            return
        cal_a = proc.cal_of(a_idx)
        ref = self.__dict__.setdefault("_rm_ref", {}).setdefault(att, {})
        geo = self.__dict__.setdefault("_rm_geo", {}).setdefault(att, {})
        seq = gate["sequence"]
        lanes = sorted(gate["lanes"], key=lambda l: l["id"])
        ref[seq] = [(l["ref"][0], l["ref"][1] * 1e-6) if proc._ref_valid(l) else None for l in lanes]
        try:
            p = a.pipeline.traj.at(0.5 * (gate["t0_us"] + gate["t1_us"])) if gate["t0_us"] is not None else None
            if p is not None:
                geo[seq] = (p["x"], p["y"])
        except Exception:
            pass
        for old in [q for q in ref if q < seq - 1500]:
            ref.pop(old, None)
            geo.pop(old, None)
        series = None
        dec = self.__dict__.setdefault("_rm_decider", est.Decider())
        for lane in lanes:
            n = lane["id"]
            ok = not lane["reasons"] and lane.get(channel) is not None and lane["ref"] is not None and gate["t0_us"] is not None
            hist = self._rate[n]
            hist.append((gate["t0_us"], gate["t1_us"], lane[channel][0], lane[channel][1] * 1e-6,
                         lane["ref"][0], lane["ref"][1] * 1e-6, seq) if ok else None)
            win = list(hist)[-n_win:]
            if len(win) < n_win or any(w is None for w in win) or cal_a is None:
                self.ratemeter[n].update(rate=None, net=None, alarm=False)
                continue
            N_F, T_F = sum(w[2] for w in win), sum(w[3] for w in win)
            N_U, T_U = sum(w[4] for w in win), sum(w[5] for w in win)
            c = cal_a.cal(n, channel)
            r = N_F / T_F - c.k * N_U / T_U - c.b
            if self.cfg.method != "SEARCH_THEN_COUNT":
                self.ratemeter[n] = {"rate": N_F / T_F, "net": r, "alarm_level": None, "alarm": False, "D": r / c.K,
                                     "t_us": gate["t1_us"], "statistic": "display only (no search stage in this method)"}
                continue
            if series is None:
                series = unull.Series.build(ref, geo)
            rec = unull.u_null(series, n, (win[0][6], win[-1][6]), alpha, past_only=True)
            if rec.get("U0") is None:
                self.ratemeter[n] = {"rate": N_F / T_F, "net": r, "alarm_level": None, "alarm": False, "D": r / c.K,
                                     "t_us": gate["t1_us"], "u0": "unavailable (past reference too short)"}
                continue
            qU = math.exp(round(math.log(rec["U0"]) / 0.01) * 0.01)
            qN = max(1.0, float(round(rec["N_post"])))
            tf = [round(w[3], 3) for w in win]
            tu = [round(w[5], 3) for w in win]
            g = est.LaneGates(n, [1.0] * len(win), tf, [w[2] for w in win], tu, [w[4] for w in win], qU, "search", c,
                              N_post=qN, T_post=qN / qU)
            _c, t_star, ok_t, meth = dec.threshold((dec._lane_key(g),), alpha)
            D = r / c.K
            alarm = bool(ok_t and D > t_star)
            self.ratemeter[n] = {"rate": N_F / T_F, "net": r, "alarm_level": c.k * rec["U0"] + c.b + t_star * c.K, "alarm": alarm,
                                 "D": D, "D_star": t_star, "U0": rec["U0"], "u0_source": rec["source"], "u0_N": rec["N_post"],
                                 "method": meth, "alpha": alpha, "t_us": gate["t1_us"], "provisional": True}
            if searching:
                self._track_peak(n, 0.5 * (win[0][0] + win[-1][1]), r, c.K, alarm)
            else:
                self._peak = None

    def _track_peak(self, lane, t_centre, r, K, alarm):
        """The alarm fires on the leading edge of a spot; follow the window rate for at most
        `peak_search_m` (or until it has fallen to half its maximum) to locate the peak."""
        pk = getattr(self, "_peak", None)
        x = self.app.mover.pose[0]
        if pk is None:
            if alarm:
                self._peak = {"lane": lane, "t": t_centre, "r": r, "x0": x, "K": K}
            return
        if pk["lane"] != lane:
            return
        if r > pk["r"]:
            pk["r"], pk["t"] = r, t_centre
        if abs(x - pk["x0"]) >= self.cfg.peak_search_m or r < 0.5 * pk["r"]:
            self._peak = None
            self._search_alarm(lane, pk["t"], pk["r"] / K)

    def _search_alarm(self, lane, t_centre, D):
        a, t = self.app, self.task
        try:
            p = a.pipeline.traj.at(t_centre)
        except Exception:
            return
        centre = transform((p["x"], p["y"], p["yaw"]), [a.pipeline.proc.lane_center_base(len(a.pipeline.proc.sessions) - 1, lane)])[0]
        for s in self.counted_spots + self.deferred_counts:
            if math.hypot(s["xy"][0] - centre[0], s["xy"][1] - centre[1]) < self.cfg.refractory_m:
                return                       # already counted / queued (any lane, any pass)
        spot = {"lane": lane, "xy": [float(centre[0]), float(centre[1])], "pose": [p["x"], p["y"], p["yaw"]],
                "D_search": D, "task": t["id"], "t_us": t_centre,
                "alarm_record": {k: v for k, v in (self.ratemeter.get(lane) or {}).items()
                                 if k in ("D", "D_star", "U0", "u0_source", "u0_N", "method", "alpha", "provisional")}}
        self._log("search_alarm", **spot)
        if self.cfg.count_policy == "DEFERRED":
            self.deferred_counts.append(spot)
            return
        if self.count is not None:
            return
        a.mover.cancel("SEARCH_ALARM", state="IDLE")
        self._mark(stage=None, reason="COUNT_APPROACH")
        self.count = {"spot": spot, "inline": True}
        self.counted_spots.append(spot)
        self.phase = "COUNT_BACK"
        self.count["started_move"] = False

    def _ph_COUNT_BACK(self):
        a, c = self.app, self.count
        m = a.mover
        if not c["started_move"]:
            if abs(a.chassis.drive.get("applied", {}).get("v_mps", 0)) > 1e-3:
                a.chassis.set_command(0.0, 0.0, "survey")
                return
            tgt = c["spot"]["pose"]
            c["started_move"] = True
            d = math.hypot(tgt[0] - m.pose[0], tgt[1] - m.pose[1])
            if d > 0.004:
                ahead = (tgt[0] - m.pose[0]) * math.cos(m.pose[2]) + (tgt[1] - m.pose[1]) * math.sin(m.pose[2])
                self._start([{"kind": "straight", "to": (tgt[0], tgt[1]), "reverse": ahead < 0, "why": "COUNT_CENTRE",
                              "speed": 0.05, "creep_m": 0.05}])
                return
        if m.state in ("DONE", "IDLE"):
            c["t_settle"] = a.clock.now_us()
            self.phase = "COUNT"

    def _begin_count(self, flag=None):
        a, c = self.app, self.count
        self.obs_n += 1
        c.update(obs=f"OBS-{self.obs_n:04d}", t_a=a.clock.now_us(), flag=flag, t_b=None)
        self._mark(stage="COUNT", obs=c["obs"], reason="SCALER_COUNT", tag=c["spot"].get("task"))

    def _ph_COUNT(self):
        a, c = self.app, self.count
        now = a.clock.now_us()
        if c.get("t_a") is None:
            st = a.chassis.drive.get("stationary") or {}
            if now - c["t_settle"] >= self.cfg.settle_s * 1e6 and st.get("is_stationary"):
                self._begin_count(c.get("flag"))
            return
        if c["t_b"] is None:
            el = (now - c["t_a"]) * 1e-6
            stop = el >= self.cfg.scaler_preset_s
            if self.cfg.scaler_mode == "ADAPTIVE":
                stop = el >= self.cfg.scaler_max_s
                if not stop and el >= 5.0 and int(el * 10) % 10 == 0:
                    d = a.pipeline.proc.live_count_state(c["obs"], c["spot"]["lane"], now)
                    goal = a.pipeline.proc.profile["detection_goal_Bq_cm2"]
                    if d is not None and d.D is not None and (d.D_hash < goal or abs(d.D - d.D_star) > 2.0 * d.u_total):
                        stop = True
            if stop:
                c["t_b"] = now
                self._mark(stage=None, reason="COUNT_DONE")
            return
        if a.chassis.drive.get("_t_host", 0) < c["t_b"] or now - c["t_b"] < 400_000:
            return                                  # stationary sample after the window + gates delivered
        ok, why = a.chassis.stationary_window_valid(c["t_a"], c["t_b"])
        self._end_count(ok, why)
        if c.get("inline"):
            self.phase = "PASS"
            self._start([self._pass_prim(self.task)])
        else:
            self.phase = "DEFERRED_COUNT"

    def _end_count(self, valid, reason):
        a, c = self.app, self.count
        self.count = None
        if c is None or c.get("obs") is None:
            return
        t = a.clock.now_us()
        a.pipeline.record(t, "J", {"op": "advance", "w": t})
        m = a.mover.pose
        centre = transform(m, [a.pipeline.proc.lane_center_base(len(a.pipeline.proc.sessions) - 1, c["spot"]["lane"])])[0]
        self._mark(stage=None, reason=reason or "COUNT_END", count_end=True, obs=c["obs"], lane=c["spot"]["lane"],
                   valid=bool(valid), flag=c.get("flag"), mode=self.cfg.scaler_mode, pose=list(m),
                   target_xy=c["spot"]["xy"], achieved_xy=[float(centre[0]), float(centre[1])])
        self._log("scaler_count", obs=c["obs"], valid=bool(valid), reason=reason,
                  outcome=a.pipeline.proc.observations[c["obs"]]["outcome"])

    def _ph_DEFERRED_COUNT(self):
        a, m = self.app, self.app.mover
        if self.count is None:
            if not self.deferred_counts:
                self.phase = "NEXT"
                return
            spot = self.deferred_counts.pop(0)
            self.counted_spots.append(spot)
            prims = approach(m.pose, tuple(spot["pose"]), self.region)
            if prims is None:
                self._log("deferred_count_unreachable", **spot)
                return
            self.count = {"spot": spot, "inline": False, "moving": True}
            self._start(prims)
            return
        c = self.count
        if c.get("moving"):
            if m.state == "BLOCKED":
                self._log("deferred_count_blocked", **c["spot"])
                self.count = None
            elif m.state in ("DONE", "IDLE"):
                c["moving"] = False
                c["t_settle"] = a.clock.now_us()
                self.phase = "COUNT"

    # ----------------------------------------------------------------- finish
    def _finish(self, why):
        a = self.app
        if self._alert_rest_saved is not None:
            a.chassis.request("CONFIG_SET", {"key": "alert.rest_ms", "value": self._alert_rest_saved})
            self._log("config_set", key="alert.rest_ms", value=self._alert_rest_saved, why="restore after STEP_AND_COUNT")
            self._alert_rest_saved = None
        a.chassis.clear_command()
        t = a.clock.now_us()
        a.pipeline.record(t, "J", {"op": "mark", "t_us": t, "stage": None, "reason": "MISSION_END:" + why})
        a.pipeline.record(t, "J", {"op": "evaluate"})
        # end of the survey: the recorded evaluation (MODEL.md rev 5 section 3) so that the review queue holds recorded
        # alarms (and alarms found at the final evaluation), not unconfirmed provisional ones.  Journaled: replay does the
        # same at the same point.  Runs in the application thread (blocks it for ~0.1-0.2 s per cell on this host).
        a.pipeline.record(t, "J", {"op": "finalize"})
        self.state = "REVIEW" if why != "ABORTED" else "REVIEW"
        self.finished = True
        self.finish_reason = why
        self._log("mission_end", reason=why, tasks={t["id"]: t["status"] for t in self.tasks})
        a.checkpoint()

    def snapshot(self):
        done = sum(1 for t in self.tasks if t["status"] == "DONE")
        return {"state": self.state, "hold_reason": self.hold_reason, "phase": self.phase, "method": self.cfg.method,
                "task": self.task["name"] if self.task else None, "tasks_done": done, "tasks_total": len(self.tasks),
                "tasks_deferred": [t["id"] for t in self.tasks if t["status"] == "DEFERRED"],
                "tasks_residual": [t["id"] for t in self.tasks if t["status"] == "RESIDUAL"],
                "deferred_counts": len(self.deferred_counts), "ratemeter": self.ratemeter,
                "station": self._station["tag"] if self._station else None,
                "counting": self.count["obs"] if self.count and self.count.get("obs") else None,
                "prerequisites_missing": self.prerequisites() if self.state in ("CONFIGURE", "READY", "ARMED", "HOLD") else []}
