"""Guided review of flagged areas (design 0.3 ch.2 "Take a technician back to a
flagged spot"; software/Operator_Interface.md "Guided review sequence").

  Next          parks the ORIGINAL detector lane over the saved footprint and
                verifies arrival within the contract tolerance; one destination per command
  Expose spot   reverses by the contract offset so the flagged floor is visible
  Park          returns to the defined parking pose; unvisited items stay open
  Repeat        stationary scaler count appended as a linked observation
  Skip          records a reason

A command is rejected (never queued) while traction is inhibited, while another
move is running, or without the control lease.  A route hold, blocked path, poor
localisation or a lost controlling session leaves the item open; motion needs a
deliberate re-arm and a fresh command.  No ROS imports.
"""
from __future__ import annotations

import math

import numpy as np

from rr_core.geometry import rot, transform
from rr_coverage.planner import approach, transit

QUEUE_KINDS = ("INVESTIGATION_LEVEL", "UNRESOLVED_EXCEEDANCE")            # ALL_UNRESOLVED policy
FLAG_KINDS = ("RATE_SATURATION", "INVESTIGATION_LEVEL", "UNRESOLVED_EXCEEDANCE", "SCAN_DETECTION")


class GuidedReview:
    def __init__(self, app, region, park_pose, arrival_tol_m=0.010, expose_offset_m=0.35, repeat_s=30.0,
                 wall_margin_m=0.03, include_scan_detections=False):
        self.app, self.region, self.park_pose = app, region, tuple(park_pose)
        self.arrival_tol_m, self.expose_offset_m, self.repeat_s = arrival_tol_m, expose_offset_m, repeat_s
        self.wall_margin_m = wall_margin_m
        self.kinds = QUEUE_KINDS + (("SCAN_DETECTION",) if include_scan_detections else ())
        self.status = {}             # flag id -> dict(status, notes, visits...)
        self.move = None
        self.current = None          # flag id the robot is parked at / exposed from
        self.parked = False
        self.count = None
        self.obs_n = 0
        self.log = []

    # ------------------------------------------------------------------ queue
    def items(self):
        out = []
        proc = self.app.pipeline.proc
        # ALARM_ONLY: every flag is an alarm at alpha_scan, so every flag is queued (incl. SCAN_DETECTION)
        kinds = tuple(FLAG_KINDS) if proc.params.get("review_queue_policy", "ALARM_ONLY") == "ALARM_ONLY" else tuple(self.kinds) + ("RATE_SATURATION",)
        for f in proc.flags:
            if f["kind"] not in kinds or f.get("x_m") is None:
                continue
            if f.get("recorded") == "provisional alarm not confirmed":
                continue                      # listed in flags.json / the report, not queued (MODEL.md rev 5 section 3)
            st = self.status.setdefault(f["id"], {"status": "OPEN", "notes": [], "visits": []})
            out.append({"id": f["id"], "kind": f["kind"], "class": f["class"], "status": st["status"],
                        "notes": st["notes"][-3:], "visits": st["visits"], "location": f["location"],
                        "source_lane": f["source_lane"], "D": f["D"], "u_total": f["u_total"], "D_star": f["D_star"],
                        "D_hash": f["D_hash"], "x_m": f["x_m"], "y_m": f["y_m"], "footprint": f["footprint"],
                        "position_uncertainty_m": f["position_uncertainty_m"], "observations": f["observations"],
                        "recommendation": f["recommendation"]})
        return out

    def _flag(self, fid):
        return next((f for f in self.app.pipeline.proc.flags if f["id"] == fid), None)

    def _note(self, fid, text, status=None):
        st = self.status.setdefault(fid, {"status": "OPEN", "notes": [], "visits": []})
        st["notes"].append(text)
        if status:
            st["status"] = status
        self.log.append({"t_us": self.app.clock.now_us(), "flag": fid, "note": text, "status": st["status"]})
        self.app.log_event({"ev": "guided", "flag": fid, "note": text, "status": st["status"]})

    # --------------------------------------------------------------- commands
    def command(self, name, args=None, actor="operator"):
        args = args or {}
        fn = getattr(self, "_cmd_" + name, None)
        if fn is None:
            return {"accepted": False, "reason": "UNKNOWN_COMMAND"}
        if name in ("next", "expose", "park", "repeat"):
            if self.move is not None or self.count is not None:
                return {"accepted": False, "reason": "BUSY: a guided action is in progress"}
            why = self.app.mover.inhibited()
            if why:
                return {"accepted": False, "reason": "INHIBITED:" + why}      # rejected, never queued
            if not self.app.loc.sample()["credit"]:
                return {"accepted": False, "reason": "LOCALIZATION: position not reliable"}
        return fn(args, actor)

    def _target_pose(self, flag, yaw):
        proc = self.app.pipeline.proc
        c = proc.lane_center_base(proc.a_index(flag["attachment"]), flag["source_lane"])
        xy = np.array([flag["x_m"], flag["y_m"]]) - rot(yaw) @ np.asarray(c)
        return (float(xy[0]), float(xy[1]), yaw)

    def _cmd_next(self, args, actor):
        open_items = [i for i in self.items() if i["status"] in ("OPEN",)]
        fid = args.get("flag") or (open_items[0]["id"] if open_items else None)
        if fid is None:
            return {"accepted": False, "reason": "NO_OPEN_ITEMS: use Park"}
        flag = self._flag(fid)
        if flag is None or flag.get("source_lane") is None:
            return {"accepted": False, "reason": "UNKNOWN_FLAG"}
        # the attachment that made the flag must still be the fitted head (original lane geometry)
        head = self.app.head.session
        proc = self.app.pipeline.proc
        if head is None or proc.sessions[proc.a_index(flag["attachment"])]["head_id"] != head["head_id"]:
            self._note(fid, "head changed since the scan: original lane geometry not available")
            return {"accepted": False, "reason": "HEAD_CHANGED"}
        prims = target = None
        for yaw in (flag["heading_rad"], flag["heading_rad"] + math.pi):
            yaw = math.atan2(math.sin(yaw), math.cos(yaw))
            target = self._target_pose(flag, yaw)
            prims = approach(self.app.mover.pose, target, self.region)
            if prims is not None:
                break
        if prims is None:
            self._note(fid, "UNREACHABLE: target pose outside the permitted robot-centre region")
            return {"accepted": False, "reason": "UNREACHABLE", "flag": fid}
        ok, why = self.app.mover.start(prims, source="guided")
        if not ok:
            return {"accepted": False, "reason": "INHIBITED:" + why}
        self.move = {"kind": "NEXT", "flag": fid, "target": target, "retries": 0}
        self.current, self.parked = None, False
        self._note(fid, f"Next accepted by {actor}", "EN_ROUTE")
        return {"accepted": True, "flag": fid, "target_pose": target}

    def _cmd_expose(self, args, actor):
        fid = self.current
        if fid is None or self.status[fid]["status"] != "AT_SPOT":
            return {"accepted": False, "reason": "NOT_AT_SPOT"}
        x, y, yaw = self.app.mover.pose
        tx, ty = x - self.expose_offset_m * math.cos(yaw), y - self.expose_offset_m * math.sin(yaw)
        pts = np.vstack(self.app.outline.at((tx, ty, yaw)))
        cfg = self.app.pipeline.proc.cfg
        m = self.wall_margin_m
        if (pts[:, 0].min() < m or pts[:, 0].max() > cfg.length_m - m or np.abs(pts[:, 1]).max() > cfg.width_m / 2 - m):
            self._note(fid, "Expose refused: no room to reverse by the registered offset")
            return {"accepted": False, "reason": "NO_ROOM_TO_REVERSE"}
        ok, why = self.app.mover.start([{"kind": "straight", "to": (tx, ty), "reverse": True, "why": "EXPOSE",
                                         "speed": 0.05}], source="guided")
        if not ok:
            return {"accepted": False, "reason": "INHIBITED:" + why}
        self.move = {"kind": "EXPOSE", "flag": fid, "target": (tx, ty, yaw)}
        return {"accepted": True, "flag": fid}

    def _cmd_park(self, args, actor):
        prims = transit(self.app.mover.pose, self.park_pose, self.region)
        if not prims:
            self.parked = True
            return {"accepted": True, "note": "already at the parking pose"}
        ok, why = self.app.mover.start(prims, source="guided")
        if not ok:
            return {"accepted": False, "reason": "INHIBITED:" + why}
        self.move = {"kind": "PARK", "flag": None, "target": self.park_pose}
        self.current = None
        return {"accepted": True}

    def _cmd_repeat(self, args, actor):
        fid = self.current
        if fid is None or self.status[fid]["status"] != "AT_SPOT":
            return {"accepted": False, "reason": "NOT_AT_SPOT"}
        self.obs_n += 1
        a = self.app
        self.count = {"flag": fid, "obs": f"REV-{self.obs_n:04d}", "t_a": a.clock.now_us(), "t_b": None,
                      "duration_s": float(args.get("duration_s", self.repeat_s))}
        t = a.clock.now_us()
        a.pipeline.record(t, "J", {"op": "mark", "t_us": t, "stage": "COUNT", "obs": self.count["obs"],
                                   "reason": "REPEAT", "tag": fid})
        return {"accepted": True, "observation": self.count["obs"]}

    def _cmd_skip(self, args, actor):
        fid, reason = args.get("flag") or self.current, (args.get("reason") or "").strip()
        if fid is None or fid not in {i["id"] for i in self.items()}:
            return {"accepted": False, "reason": "UNKNOWN_FLAG"}
        if not reason:
            return {"accepted": False, "reason": "REASON_REQUIRED"}
        self._note(fid, f"Skipped by {actor}: {reason}", "SKIPPED")
        return {"accepted": True, "flag": fid}

    def on_control_lost(self):
        """Lost controlling session: guided motion holds (HOLD latch on the chassis)."""
        if self.move is not None:
            self.app.chassis.stop("CONTROLLED")
            self._abort_move("controlling session lost: motion held")

    def _abort_move(self, text):
        mv = self.move
        self.move = None
        self.app.mover.cancel(text, state="IDLE")
        if mv and mv["flag"]:
            st = self.status[mv["flag"]]
            self._note(mv["flag"], text, "OPEN" if mv["kind"] == "NEXT" else st["status"])

    # ------------------------------------------------------------------- step
    def step(self):
        a, m = self.app, self.app.mover
        if self.count is not None:
            self._step_count()
        mv = self.move
        if mv is None:
            return
        if m.state in ("HELD", "BLOCKED", "FAILED"):
            self._abort_move(f"move stopped: {m.reason}; item left open; re-arm and send a fresh command")
            m.state = "IDLE"
            return
        if m.state != "DONE":
            return
        m.state = "IDLE"
        self.move = None
        fid = mv["flag"]
        if mv["kind"] == "PARK":
            err = math.hypot(m.pose[0] - self.park_pose[0], m.pose[1] - self.park_pose[1])
            # arrival is verified against the position budget (2 sigma, no slip); mapping-credit conditions such as a fresh
            # along-track fix or the chassis clock bound are reported but do not refuse a park (2026-11-28 credit model)
            why = [r for r in a.loc.credit_reasons() if r in ("2SIGMA", "SLIP", "NOT_INITIALIZED")]
            self.parked = err <= 0.03 and not why
            a.log_event({"ev": "guided", "note": "PARKED" if self.parked else "PARK_NOT_VERIFIED", "error_m": err,
                         "credit_reasons": a.loc.credit_reasons()})
            return
        flag = self._flag(fid)
        proc = a.pipeline.proc
        centre = transform(m.pose, [proc.lane_center_base(proc.a_index(flag["attachment"]), flag["source_lane"])])[0]
        if mv["kind"] == "NEXT":
            err = math.hypot(centre[0] - flag["x_m"], centre[1] - flag["y_m"])
            unc = a.loc.head_uncertainty_m()
            if err <= self.arrival_tol_m and a.loc.sample()["credit"]:
                self.current = fid
                self.status[fid]["visits"].append({"t_us": a.clock.now_us(), "achieved_xy": [float(centre[0]), float(centre[1])],
                                                   "target_xy": [flag["x_m"], flag["y_m"]], "error_m": err,
                                                   "uncertainty_2s_m": unc, "lane": flag["source_lane"],
                                                   "heading_rad": m.pose[2], "pose": list(m.pose)})
                self._note(fid, f"ARRIVED: lane {flag['source_lane']} over the saved footprint, offset {err * 1000:.1f} mm "
                                f"(tolerance {self.arrival_tol_m * 1000:.0f} mm, 2-sigma uncertainty {unc * 1000:.1f} mm)", "AT_SPOT")
                a.chassis.request("PANEL", {"pattern": "ARRIVED"})
            elif mv["retries"] < 1 and a.mover.inhibited() is None:
                back = (m.pose[0] - 0.10 * math.cos(m.pose[2]), m.pose[1] - 0.10 * math.sin(m.pose[2]))
                prims = [{"kind": "straight", "to": back, "reverse": True, "why": "REAPPROACH"},
                         {"kind": "straight", "to": mv["target"][:2], "reverse": False, "why": "APPROACH", "speed": 0.03, "creep_m": 0.08}]
                if a.mover.start(prims, source="guided")[0]:
                    mv["retries"] += 1
                    self.move = mv
            else:
                self._note(fid, f"ARRIVAL_NOT_VERIFIED: offset {err * 1000:.1f} mm, uncertainty {unc * 1000:.1f} mm; item left open", "OPEN")
        elif mv["kind"] == "EXPOSE":
            ahead = (flag["x_m"] - m.pose[0]) * math.cos(m.pose[2]) + (flag["y_m"] - m.pose[1]) * math.sin(m.pose[2])
            left = -(flag["x_m"] - m.pose[0]) * math.sin(m.pose[2]) + (flag["y_m"] - m.pose[1]) * math.cos(m.pose[2])
            info = {"spot_ahead_of_head_front_edge_m": round(ahead - a.outline.front, 3),
                    "spot_left_of_centreline_m": round(left, 3), "pose": list(m.pose)}
            self.status[fid]["exposed"] = info
            self._note(fid, f"EXPOSED: the flagged point is {info['spot_ahead_of_head_front_edge_m'] * 100:.0f} cm ahead of the head's "
                            f"front edge, {abs(left) * 100:.0f} cm {'left' if left >= 0 else 'right'} of the robot centreline", "EXPOSED")

    def _step_count(self):
        a, c = self.app, self.count
        now = a.clock.now_us()
        if c["t_b"] is None:
            if now - c["t_a"] >= c["duration_s"] * 1e6:
                c["t_b"] = now
                a.pipeline.record(now, "J", {"op": "mark", "t_us": now, "stage": None, "reason": "COUNT_DONE"})
            return
        if a.chassis.drive.get("_t_host", 0) < c["t_b"] or now - c["t_b"] < 400_000:
            return
        ok, why = a.chassis.stationary_window_valid(c["t_a"], c["t_b"])
        flag = self._flag(c["flag"])
        a.pipeline.record(now, "J", {"op": "advance", "w": now})
        a.pipeline.record(now, "J", {"op": "mark", "t_us": now, "stage": None, "reason": why or "COUNT_END", "count_end": True,
                                     "obs": c["obs"], "lane": flag["source_lane"], "valid": bool(ok), "flag": c["flag"],
                                     "mode": "PRESET_TIME", "pose": list(a.mover.pose), "target_xy": [flag["x_m"], flag["y_m"]]})
        obs = a.pipeline.proc.observations[c["obs"]]
        self._note(c["flag"], f"Repeat {c['obs']}: {obs['outcome']}")
        self.count = None
