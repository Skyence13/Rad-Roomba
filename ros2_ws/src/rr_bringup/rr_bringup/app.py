"""RobotApp: the ROS-free composition of the robot software.

One object wires head link -> archive/pipeline, chassis link -> localisation ->
trajectory, the motion executor, the mission supervisor and the guided review.
The ROS node (`rr_bringup.robot_node`) and the deterministic simulation harness
(`rr_sim.harness`) both drive this class; only the clock and the transports
differ.  No ROS imports.
"""
from __future__ import annotations

import json
import math
import uuid
from pathlib import Path

import numpy as np

from rr_core.archive import Archive, ArchiveError
from rr_core.chassis_link import ChassisLink
from rr_core.export import export_survey
from rr_core.geometry import RobotOutline, lane_polygons
from rr_core.head_link import HeadLinkConfig, HeadLinkMaster
from rr_core.pipeline import SurveyPipeline, build_from_run
from rr_core.processing import SurveyConfig
from rr_core.profiles import DATA, Calibration, CalibrationStore, ProfileStore
from rr_coverage.motion import Mover, MoverConfig
from rr_coverage.planner import PlanConfig, plan_coverage
from rr_coverage.supervisor import Mission, MissionConfig
from rr_guidance.guidance import GuidedReview
from rr_localization.estimator import LocalizerConfig, WallLocalizer

DEFAULTS = {
    "trailer": {"id": "SIM-TRAILER", "length_m": 3.0, "width_m": 2.5, "door_closed": True, "door_target_x_m": None,
                "keepouts": []},
    "profile_id": "ore-floor-demo-synthetic",
    "mode": "COMMISSIONING", "op_mode": "COMMISSIONING",
    "survey": {"sub_res": 0.005, "cell_m": 0.10, "position_allowance_m": 0.010},
    "plan": {}, "mission": {}, "mover": {}, "link": {}, "localizer": {},
    "lidar": {"range_max": 12.0},        # xy/yaw come from frames.yaml unless given here
    "outline": {},                       # RobotOutline kwargs; default = frames.yaml + contract (geometry_config)
    "auto_head_power": True,
    "head_setup": {"device": "J60035"},   # ENG_SETUP_SET before the first ARM (head firmware 0.5.2); add "thresholds_confirmed": true or "thresholds": {...}
    "start_pose": None,                  # default: first pass start
    "simulated": True,
    "chassis_thread": False,             # real-time hosts: chassis link on its own thread (IB-46); the virtual-time harness keeps False
    # MODEL.md rev 5 section 1 / review C2: STRICT = a calibration is bound only to the head whose serial, electronics revision,
    # firmware, setup_id (and cal_id) it names; DEMONSTRATION = explicit, loudly marked mode for the synthetic calibration
    "calibration_binding": "STRICT",
    "archive_scans": True,               # MODEL.md rev 5 section 8: range data archived as received (S entries)
}


def scan_record(t_us, angles, ranges):
    """Archived LiDAR scan (MODEL.md rev 5 section 8): time stamp, angles and ranges as received; ranges in mm as
    little-endian uint16 (0 = no return / out of range), angles as start, increment and count when uniform."""
    import base64 as _b64
    a = np.asarray(angles, float)
    r = np.asarray(ranges, float)
    mm = np.where(np.isfinite(r) & (r > 0) & (r < 65.0), np.round(r * 1000.0), 0).astype("<u2")
    rec = {"t_us": int(t_us), "n": int(a.size), "ranges_mm_u16le_b64": _b64.b64encode(mm.tobytes()).decode("ascii")}
    if a.size > 1 and np.allclose(np.diff(a), a[1] - a[0], rtol=0, atol=1e-9):
        rec.update(angle_min=float(a[0]), angle_inc=float(a[1] - a[0]))
    else:
        rec["angles"] = [float(x) for x in a]
    return rec


def merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class RobotApp:
    def __init__(self, clock, head_transport, chassis_transport, run_dir, registry, config=None,
                 calibrations=None, profiles=None, uuid_factory=None, resume=False):
        self.clock = clock
        from .geometry_config import load_robot_geometry
        self.geometry = geo = load_robot_geometry()
        cfg = merge(DEFAULTS, config)
        cfg["outline"] = merge({k: v for k, v in geo["outline"].items()}, cfg["outline"])
        cfg["lidar"] = merge(geo["lidar"], cfg["lidar"])
        cfg.setdefault("guided_arrival_tolerance_m", geo["guided_arrival_tolerance_m"])
        cfg.setdefault("expose_spot_reverse_offset_m", geo["expose_spot_reverse_offset_m"])
        self.cfg = cfg
        self.run_dir = Path(run_dir)
        self.calibrations = calibrations or [Calibration.load(DATA / "demo_calibration.json")]
        self.profiles = profiles or ProfileStore.load(DATA / "demo_site_profile_ore.json")
        if cfg["calibration_binding"] not in ("STRICT", "DEMONSTRATION"):
            raise ValueError("calibration_binding must be STRICT or DEMONSTRATION")
        self.cal_store = CalibrationStore(self.calibrations, demonstration=cfg["calibration_binding"] == "DEMONSTRATION")
        self.outline = RobotOutline(**cfg["outline"])
        self.archive_error = None
        self._events = []
        self.gate_feed = []            # raw gate records for publishers (bounded)
        self.audit = []
        tr = cfg["trailer"]
        link_cfg = HeadLinkConfig(mode=cfg["mode"], setup=cfg.get("head_setup"), **cfg["link"])
        self._uuid = uuid_factory or (lambda: str(uuid.uuid4()))
        self.archive = Archive(self.run_dir)
        if resume and (self.run_dir / "run.json").exists():
            # reboot / pack swap: replay the committed raw data, continue as a NEW epoch
            self.pipeline, self.run = build_from_run(self.run_dir, archive=self.archive, calibrations=self.calibrations)
            self.calibration = self.pipeline.proc.cal
            self.profile = self.pipeline.proc.profile
            self.resumed = True
        else:
            profile_raw = self.profiles.get(cfg["profile_id"])
            self.calibration = self.cal_store.by_id.get(profile_raw.get("head_calibration_id"))
            self.profile = self.profiles.snapshot(cfg["profile_id"], self.calibration, cfg["mode"])
            survey_cfg = dict(length_m=tr["length_m"], width_m=tr["width_m"], keepouts=tr["keepouts"], **cfg["survey"])
            method = {"name": merge(MissionConfig().__dict__, cfg["mission"])["method"], "params": cfg["mission"]}
            self.run = {"run_id": self._uuid(), "trailer_id": tr["id"], "survey_config": survey_cfg,
                        "link_config": {"mode": cfg["mode"], **cfg["link"]}, "method": method,
                        "profile": self.profile, "calibration_record": self.calibration.record,
                        "calibration_records": [c.record for c in self.calibrations],
                        "calibration_binding": cfg["calibration_binding"],
                        "robot_outline": self.outline.as_dict(), "simulated": cfg["simulated"],
                        "trajectory_config": {}, "config": cfg}
            self.archive.write_run_manifest(self.run)
            self.pipeline = SurveyPipeline(SurveyConfig(**survey_cfg), self.calibration, self.profile, link_cfg,
                                           method, archive=self.archive, calibrations=self.calibrations)
            self.resumed = False
        self.head = HeadLinkMaster(head_transport, clock, registry, link_cfg, resolve_calibration=self.cal_store.resolve,
                                   sink=self._head_sink, uuid_factory=self._uuid)
        self.head.interp = self.pipeline.interp          # one interpreter: live == replay
        if self.resumed and self.pipeline.interp.session is not None:
            # host/driver restart ends the previous attachment (ICD "Broken continuity")
            self.head._emit("C", {"c": "SESSION_CLOSE", "reason": "HOST_RESTART"})
        self.chassis = ChassisLink(chassis_transport, clock, sink=self._aux_sink)
        self.loc = WallLocalizer(LocalizerConfig(tr["length_m"], tr["width_m"], door_closed=tr["door_closed"],
                                                 door_target_x_m=None if tr["door_closed"] else tr.get("door_target_x_m"),
                                                 lidar_xy=tuple(cfg["lidar"]["xy"]), lidar_yaw=cfg["lidar"]["yaw"],
                                                 **cfg["localizer"]))
        self.mover = Mover(clock, self.chassis, self.outline, MoverConfig(**cfg["mover"]))
        self.mission = None
        self.guidance = None
        self.plan = None
        self._next_ctrl = self._next_adv = 0
        self._caps_applied = None
        self.control_ok = lambda: True       # replaced by the web layer (control lease)
        self._lease_was_ok = True
        self._summary_cache = (None, None)
        if self.resumed:
            t = clock.now_us()
            self.pipeline.record(t, "J", {"op": "resume", "t_us": t, "reason": "PROCESS_RESTART",
                                          "archive_epoch": self.archive.epoch})

    # ------------------------------------------------------------------ sinks
    def _head_sink(self, entry):
        try:
            self.pipeline.archive_entry(entry)
        except ArchiveError as err:
            self.archive_error = str(err)

    def _aux_sink(self, entry):
        try:
            self.archive.append(entry)
        except ArchiveError as err:
            self.archive_error = str(err)

    def log_event(self, ev):
        self._events.append(ev)
        del self._events[:-300]
        self._aux_sink((self.clock.now_us(), "X", {"x": "event", **_plain(ev)}))

    def checkpoint(self):
        if self.mission is None:
            return
        try:
            self.archive.write_checkpoint({"run_id": self.run["run_id"], "t_us": self.clock.now_us(),
                                           "archive_epoch": self.archive.epoch, "mission_state": self.mission.state,
                                           "tasks": self.mission.tasks, "method": self.mission.cfg.method,
                                           "deferred_counts": self.mission.deferred_counts,
                                           "trajectory_epoch": self.pipeline.traj.epoch})
        except (ArchiveError, OSError) as err:
            self.archive_error = str(err)

    # ------------------------------------------------------------------ setup
    def _ensure_plan(self):
        """The plan needs the lane geometry, i.e. a bound head (descriptor + mount)."""
        if self.plan is not None or not self.pipeline.proc.sessions:
            return
        m = self.pipeline.proc.sessions[-1]
        import base64
        desc = json.loads(base64.b64decode(m["descriptor_b64"]))
        lanes = lane_polygons(desc, m["mount_transform"])
        tr_cfg = self.cfg["trailer"]
        mcfg = MissionConfig(**merge(dict(self.geometry.get("survey_method_defaults") or {}, op_mode=self.cfg["op_mode"]),
                                     self.cfg["mission"]))       # contract survey_methods defaults, config overrides
        door_end_x = 0.0 if tr_cfg["door_closed"] or tr_cfg.get("door_target_x_m") is None else float(tr_cfg["door_target_x_m"])
        pcfg = PlanConfig(**merge({"allowance_m": self.cfg["survey"]["position_allowance_m"], "method": mcfg.method,
                                   "door_end_x_m": door_end_x,
                                   "speed_mps": mcfg.speed, "station_pitch_m": mcfg.station_pitch_m,
                                   "settle_s": mcfg.settle_s, "scaler_preset_s": mcfg.station_preset_s}, self.cfg["plan"]))
        tr = self.cfg["trailer"]
        self.plan = plan_coverage(tr["length_m"], tr["width_m"], self.outline, lanes, pcfg)
        ck = self.archive.read_checkpoint() if self.resumed else None
        if ck:
            done = {t["id"]: t for t in ck["tasks"]}
            for t in self.plan["tasks"]:
                old = done.get(t["id"])
                if old and old["status"] == "DONE":
                    t["status"] = "DONE"          # an interrupted task is re-surveyed in the new epoch
        self.mission = Mission(self, self.plan, mcfg)
        if ck:
            self.mission.deferred_counts = ck.get("deferred_counts", [])
        first = next((t for t in self.plan["tasks"]), None)
        self.park_pose = tuple(self.cfg["start_pose"] or (first["x_start"], first["y"], first["heading"]))
        self.guidance = GuidedReview(self, self.plan["pivot_region"], self.park_pose,
                                     arrival_tol_m=self.cfg.get("guided_arrival_tolerance_m", 0.010),
                                     expose_offset_m=self.cfg.get("expose_spot_reverse_offset_m", 0.35),
                                     repeat_s=self.pipeline.proc.params["recount_default_s"])
        self.log_event({"ev": "plan", "n_tasks": len(self.plan["tasks"]), "estimated_time_s": self.plan["estimated_time_s"]})

    # ------------------------------------------------------------------- step
    def shutdown(self):
        """Stop the chassis link thread (if any) and flush its archive entries; call before closing the archive."""
        self.chassis.stop_thread()

    def step(self):
        now = self.clock.now_us()
        if self.cfg["chassis_thread"]:
            self.chassis.start_thread()           # idempotent; a real-time clock is required
        self.head.step()
        evs = self.head.drain_events()
        if evs:
            self.pipeline.on_head_events(evs)
            for ev in evs:
                if ev["ev"] == "gate":
                    self.gate_feed.append(ev["gate"])
                    del self.gate_feed[:-600]
                    if self.mission is not None:
                        self.mission.on_gate(ev["gate"])
                elif ev["ev"] in ("session_open", "session_close", "blocked", "link_down", "fault", "gap"):
                    self.log_event({k: v for k, v in ev.items() if k not in ("manifest", "gate")})
            self._ensure_plan()
        self.chassis.step()
        while self.chassis.samples:
            s = self.chassis.samples.popleft()
            if not self.loc.initialized:
                continue
            self._aux_sink((now, "K", _plain(s)))          # pose-estimate input as received (MODEL.md rev 5 section 8)
            p = self.loc.predict(s)
            try:
                self.pipeline.record(now, "P", p)
            except ArchiveError as err:
                self.archive_error = str(err)
            self.mover.set_pose((p["x"], p["y"], p["yaw"]), ok=not self.loc.status()["hold_request"])
        while self.chassis.out_events:
            ev = self.chassis.out_events.popleft()
            if ev["ev"] == "chassis_boot":
                caps = ev.get("caps", {})
                if caps.get("track_nom_m"):
                    self.loc.cfg.track_m, self.loc.cfg.wheel_radius_m = caps["track_nom_m"], caps["wheel_radius_nom_m"]
                    self.loc.cfg.cpr = caps.get("encoder_cpr", self.loc.cfg.cpr)
                if self.loc.initialized and self._caps_applied is not None:
                    self.pipeline.record(now, "J", {"op": "epoch", "t_us": now, "reason": "CHASSIS_BOOT"})
                if self._caps_applied is None and self.cfg["auto_head_power"]:
                    # head electronics on at first link-up (traction stays inactive); never automatic afterwards
                    self.chassis.request("HEAD_POWER", {"electronics": True, "heater_enable": False})
                self._caps_applied = caps
            elif ev["ev"] == "chassis_event":
                e = ev["event"]
                # latched connector-presence transitions close the head attachment (ICD "Broken continuity")
                if e["kind"] in ("J1", "J2") or (e["kind"] == "HEAD_POWER" and not e["detail"].get("electronics")) \
                        or (e["kind"] == "CHAIN" and e["detail"].get("el") in ("HEAD_DOCK", "HEAD_LOOP_OK") and not e["detail"].get("closed")):
                    if self.head.session is not None:
                        self.head.notify_continuity_event(f"{e['kind']}:{json.dumps(e['detail'], sort_keys=True)}")
            elif ev["ev"] in ("drive_rejected", "link_down", "event_gap"):
                self.log_event(ev)
        hp = self.chassis.state.get("head_power")
        if hp is not None:
            self.head.enabled = bool(hp.get("electronics"))      # no polling of an unpowered head
        if now >= self._next_ctrl:
            self._next_ctrl = now + 20_000
            lease = bool(self.control_ok())
            if self.guidance is not None:
                if self._lease_was_ok and not lease:
                    self.guidance.on_control_lost()
                self.guidance.step()
            self._lease_was_ok = lease
            self.mover.step()
            if self.mission is not None:
                self.mission.step()
        if now >= self._next_adv:
            self._next_adv = now + 200_000
            lt = self.pipeline.traj.latest_t
            if lt is not None and self.pipeline.proc._queue:
                self.pipeline.record(now, "J", {"op": "advance", "w": lt - 60_000})
            self._eval_n = getattr(self, "_eval_n", 0) + 1
            if self._eval_n % 25 == 0 and self.pipeline.proc.dirty:
                self.pipeline.record(now, "J", {"op": "evaluate"})   # live map refresh every 5 s

    def on_scan(self, t_us, angles, ranges):
        if not self.loc.initialized:
            return
        if self.cfg.get("archive_scans", True):
            self._aux_sink((self.clock.now_us(), "S", scan_record(t_us, angles, ranges)))
        pts = self.loc.update_scan(t_us, angles, ranges, self.cfg["lidar"]["range_max"])
        self.mover.set_obstacles(pts, t_us)

    # --------------------------------------------------------------- commands
    MISSION_CMDS = ("preflight", "arm", "start", "pause", "rearm", "resume", "defer", "abort", "end")
    GUIDED_CMDS = ("next", "expose", "park", "repeat", "skip")
    MOTION_CMDS = ("preflight", "arm", "start", "resume", "next", "expose", "park")

    def command(self, name, args=None, actor="operator", role="operator"):
        args = args or {}
        mode = self.chassis.drive.get("mode") or self.chassis.state.get("mode")
        if name in self.MOTION_CMDS and mode == "SERVICE_CHARGE":
            out = {"accepted": False, "reason": "CHARGE_SERVICE: traction inhibited while the charger is connected"}
        elif name == "register_datum":
            pose = args.get("pose") or self.cfg["start_pose"] or (self.park_pose if self.plan else None)
            if pose is None:
                out = {"accepted": False, "reason": "NO_POSE"}
            elif self.mission is not None and self.mission.state == "SCAN":
                out = {"accepted": False, "reason": "STATE:SCAN"}
            else:
                now = self.clock.now_us()
                if self.loc.initialized:
                    self.pipeline.record(now, "J", {"op": "epoch", "t_us": now, "reason": "DATUM_REGISTRATION"})
                self.loc.initialize(*pose, t_us=None)
                out = {"accepted": True, "pose": list(pose)}
        elif name in self.MISSION_CMDS:
            out = self.mission.command(name, args, actor) if self.mission else {"accepted": False, "reason": "NO_HEAD_BOUND: plan unavailable"}
        elif name in self.GUIDED_CMDS:
            if self.mission is None or self.mission.state != "REVIEW":
                out = {"accepted": False, "reason": "STATE: guided review needs a committed survey (REVIEW)"}
            else:
                out = self.guidance.command(name, args, actor)
        elif name == "head_power":
            self.chassis.request("HEAD_POWER", {"electronics": bool(args.get("on", True)), "heater_enable": False})
            out = {"accepted": True}
        elif name == "rehandshake":
            self.head.request_rehandshake()
            out = {"accepted": True}
        elif name == "export":
            out = {"accepted": True, **{k: v for k, v in self.export(args.get("dir") or self.run_dir / "export").items() if k == "dir"}}
        else:
            out = {"accepted": False, "reason": "UNKNOWN_COMMAND"}
        rec = {"t_us": self.clock.now_us(), "command": name, "args": _plain(args), "actor": actor, "role": role,
               "accepted": out.get("accepted"), "reason": out.get("reason"),
               "chassis_mode": mode, "mission_state": self.mission.state if self.mission else None}
        self.audit.append(rec)
        self._aux_sink((self.clock.now_us(), "X", {"x": "audit", **rec}))
        return out

    def export(self, out_dir):
        now, lt = self.clock.now_us(), self.pipeline.traj.latest_t
        if lt is not None:
            self.pipeline.record(now, "J", {"op": "advance", "w": lt - 60_000})
        self.pipeline.record(now, "J", {"op": "evaluate"})          # journaled: replay evaluates at the same point
        self.archive.flush()
        return export_survey(self.pipeline, self.run, out_dir, run_dir=self.run_dir)

    # ----------------------------------------------------------------- status
    @staticmethod
    def _rearm_prompt(st, mode):
        """Operator prompt for the local REARM button (ICD 4.6, 6.6): offered ONLY when the chassis reports rearm_ready;
        otherwise the reason is shown (chain element open, discharge time about 2 s, REARM held, fault)."""
        if mode in ("ARMED_IDLE", "MOVING", "HOLD") and st.get("hw_latch"):
            return {"press_rearm": False, "text": "hardware latch set", "reasons": []}
        if st.get("rearm_ready") is True:
            return {"press_rearm": True, "text": "Press REARM once on the robot", "reasons": []}
        reasons = []
        open_ = [k for k, v in (st.get("chain") or {}).items() if not v and k != "ARM_PERMIT"]
        if open_:
            reasons.append("chain not closed (open or unknown): " + ", ".join(open_))
        faults = [str(x) for x in (st.get("faults") or [])]
        if faults:
            reasons.append("fault flags: " + ", ".join(faults))
        if st.get("rearm_refusal"):
            reasons.append("last REARM press refused: " + str(st["rearm_refusal"]))
        if not reasons:
            reasons.append("waiting: REARM is accepted about 2 s after the chain closes, and not while the REARM line is held or pressed early")
        return {"press_rearm": False, "text": "Do not press REARM yet", "reasons": reasons}

    def snapshot(self, with_map=False):
        d, st = self.chassis.drive, self.chassis.state
        mode = d.get("mode") or st.get("mode")
        hs = self.head.status()
        ls = self.loc.status()
        proc = self.pipeline.proc
        fua = bool(self.profile.get("field_use_approved")) and self.calibration.field_use_approved
        snap = {
            "t_us": self.clock.now_us(), "run_id": self.run["run_id"], "robot_id": self.cfg.get("robot_id", "RR-SIM-01"),
            "field_use_approved": fua,
            "banner": None if fua else "SYNTHETIC calibration/profile - NOT for field use (field_use_approved: false)",
            "trailer": self.cfg["trailer"], "profile": {"id": self.profile["id"], "revision": self.profile.get("revision"),
                                                         "unit": "Bq/cm2", "investigation_level": self.profile["investigation_level_Bq_cm2"],
                                                         "detection_goal": self.profile["detection_goal_Bq_cm2"],
                                                         "decision_class": self.profile["decision_class"]},
            "calibration_id": self.calibration.calibration_id,
            "chassis": {"link": self.chassis.link_state, "mode": mode, "op_mode": self.chassis.op_mode,
                        "motion": d.get("motion"), "accepted": d.get("accepted"), "reject_reason": d.get("reject_reason"),
                        "applied": d.get("applied"), "stationary": d.get("stationary"),
                        "battery": st.get("battery"), "head_presence": st.get("head_presence"),
                        "time_bound_us": _fin(self.chassis.time_bound_us())},
            "safety": {"hw_latch": st.get("hw_latch"), "hw_inhibit_reasons": d.get("stops", {}).get("hw", []),
                       "protective_stop_reasons": d.get("stops", {}).get("sw", []), "hold": d.get("hold", []),
                       "chain": st.get("chain"), "rearm_ready": st.get("rearm_ready"), "rearm_prompt": self._rearm_prompt(st, mode),
                       # chassis fault flags exactly as reported (unknown names included, never filtered); chain false = open OR unknown
                       "faults": [str(x) for x in (st.get("faults") or [])],
                       "chain_not_closed": [k for k, v in (st.get("chain") or {}).items() if not v],
                       "local_only": ["ESTOP", "HANDS_ON", "hardware latch (REARM button on the robot)"],
                       "remote_clearable": ["software protective stop", "controlled-stop hold", "local Pause"],
                       "traction_inhibited": mode not in ("ARMED_IDLE", "MOVING"),
                       "charge_service": mode == "SERVICE_CHARGE"},
            "head": {k: hs[k] for k in ("state", "block_reason", "block_detail", "attachment", "head_id", "last_seq", "bound_us")},
            "localization": {"pose": [self.loc.x[0], self.loc.x[1], self.loc.x[2]] if self.loc.initialized else None,
                             "frame": "map (trailer): origin door-threshold centre, +x to bulkhead, +y left",
                             "uncertainty_2s_m": ls["head_uncertainty_2s_m"], "credit": ls["credit"], "slip": ls["slip"],
                             "hold_request": ls["hold_request"], "sigma": ls["sigma"]},
            "recorder": {"ok": self.archive_error is None, "error": self.archive_error, "epoch": self.archive.epoch,
                         "entries": self.archive.entries_written},
            "mission": self.mission.snapshot() if self.mission else {"state": "CONFIGURE", "prerequisites_missing": ["HEAD_IDENTITY"]},
            "mover": {"state": self.mover.state, "reason": self.mover.reason},
            "review": {"policy": proc.params.get("review_queue_policy"), "alpha_queue": proc.params.get("alpha_queue"),
                       "items": self.guidance.items() if self.guidance else [], "current": self.guidance.current if self.guidance else None,
                       "parked": self.guidance.parked if self.guidance else False,
                       "busy": bool(self.guidance and (self.guidance.move or self.guidance.count))},
            "observations": list(proc.observations.values())[-20:],
            "flags_total": len(proc.flags), "events": self._events[-30:],
            "plan": None if self.plan is None else {k: self.plan[k] for k in ("n_pairs", "offset_m", "pair_stride_m", "seam_overlap_per_side_m",
                                                                              "predicted_residual", "estimated_time_s", "method")},
        }
        if with_map:
            snap["map"] = self.map_layers()
        return _plain(snap)

    def map_layers(self):
        """Compact layers for the live plan view (no interpolation between cells)."""
        from rr_core.export import coverage_blocks
        proc = self.pipeline.proc
        ch = proc._decision_channel()                # decisions as of the last journaled evaluation
        cells = []
        for (cy, cx), dd in sorted(proc.decisions[ch].items()):
            if dd.D is None:
                continue
            cells.append([cx, cy, round(dd.D, 4), round(dd.u_total, 4), None if not math.isfinite(dd.D_hash) else round(dd.D_hash, 4),
                          1 if proc.sensitivity_ok(dd) else 0])
        blocks = coverage_blocks(proc, 4)
        rle = []
        for row in blocks:
            idx = np.flatnonzero(np.diff(row.astype(np.int16))) + 1
            starts = np.concatenate(([0], idx))
            rle.append([[int(s), int(row[s])] for s in starts])
        return {"cell_m": proc.cfg.cell_m, "origin": [proc.x0, proc.y0], "nx": proc.ncx, "ny": proc.ncy, "cells": cells,
                "block_m": proc.cfg.sub_res * 4, "coverage_rle": rle, "coverage_shape": list(blocks.shape),
                "reasons": ["UNVISITED", "ACCEPTABLE", "INSUFFICIENT_SENSITIVITY", "INVALID_DATA", "BLOCKED", "EXCLUDED"],
                "summary": proc.coverage_summary(),
                "flags": [{"id": f["id"], "kind": f["kind"], "x": f.get("x_m"), "y": f.get("y_m"), "footprint": f.get("footprint")}
                          for f in proc.flags if f["kind"] != "SCAN_DETECTION"],
                "outline": [p.tolist() for p in self.outline.parts]}


def _fin(v):
    return v if isinstance(v, (int, float)) and math.isfinite(v) else None


def _plain(v):
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if isinstance(v, (np.floating, np.integer, np.bool_)):
        return _plain(v.item())
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v
