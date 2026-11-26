"""Primitive executor with route monitoring, shared by the survey supervisor
and the guided review.

Straight-line following with lateral/heading error bounds, in-place pivots,
and two LiDAR zones evaluated on the swept region of the COMMANDED move
(body + projecting head, forward, reverse and turning; architecture 6.4):

  protective zone  -> `STOP PROTECTIVE` with FIELD_FRONT/REAR/LEFT/RIGHT on the
                      chassis (latched; deliberate re-arm and a FRESH command needed)
  planning zone    -> (survey passes only) slow to rest without a latch, wait,
                      and report BLOCKED after `patience_s`.

The executor never queues: `start()` is refused while the chassis is inhibited,
and any hold discards the remaining primitives.  No ROS imports.
"""
from __future__ import annotations

import math

import numpy as np

from rr_core.geometry import points_in_parts, swept_parts, wrap


class MoverConfig:
    def __init__(self, speed=0.10, reverse_speed=0.05, yaw_rate=0.25, lat_bound_m=0.015, head_bound_rad=0.05,
                 pos_tol_m=0.002, yaw_tol_rad=0.004, protect_lookahead_m=0.25, protect_margin_m=0.05,
                 plan_lookahead_m=0.80, plan_margin_m=0.03, min_points=3, patience_s=10.0, clear_dwell_s=1.0,
                 obstacle_max_age_us=400_000, prim_timeout_factor=4.0):
        self.__dict__.update(locals())
        del self.__dict__["self"]


class Mover:
    def __init__(self, clock, chassis, outline, cfg: MoverConfig | None = None):
        self.clock, self.chassis, self.outline = clock, chassis, outline
        self.cfg = cfg or MoverConfig()
        self.state = "IDLE"            # IDLE RUNNING BLOCKED_WAIT DONE HELD BLOCKED FAILED
        self.reason = None
        self.queue, self.prim = [], None
        self.pose = None
        self.pose_ok = True
        self.obstacles = np.zeros((0, 2))
        self.obstacles_t = 0
        self.events = []
        self.source = "mover"
        self._blocked_since = self._clear_since = None
        self.path_error = False
        self.max_lat_err = self.max_head_err = 0.0

    # ---------------------------------------------------------------- inputs
    def set_pose(self, pose, ok=True):
        self.pose, self.pose_ok = pose, ok

    def set_obstacles(self, pts_base, t_us):
        self.obstacles, self.obstacles_t = np.asarray(pts_base).reshape(-1, 2), t_us

    def inhibited(self):
        """Reason string when a motion command would be refused, else None."""
        d = self.chassis.drive
        if self.chassis.link_state != "UP" or not d:
            return "CHASSIS_LINK_DOWN"
        if not self.chassis.active:
            return "BRIDGE_INACTIVE"
        mode = d.get("mode")
        if mode not in ("ARMED_IDLE", "MOVING"):
            stops = d.get("stops", {})
            return f"{mode}:" + ",".join(stops.get("hw", []) + stops.get("sw", []) + d.get("hold", []))
        return None

    def start(self, prims, source="mover"):
        why = self.inhibited()
        if why:
            self.events.append({"ev": "start_refused", "reason": why})
            return False, why
        if self.pose is None:
            return False, "NO_POSE"
        self.queue = [dict(p) for p in prims]
        self.prim = None
        self.state, self.reason, self.source = "RUNNING", None, source
        self._blocked_since = self._clear_since = None
        return True, ""

    def cancel(self, reason="CANCELLED", state="IDLE"):
        self.queue, self.prim = [], None
        self.chassis.clear_command()
        self.state, self.reason = state, reason

    # ------------------------------------------------------------------ step
    def step(self):
        if self.state not in ("RUNNING", "BLOCKED_WAIT"):
            return
        why = self.inhibited()
        if why:
            self._hold(why, stop=False)
            return
        if not self.pose_ok:
            self.chassis.stop("PROTECTIVE", "LOCALIZATION")
            self._hold("LOCALIZATION", stop=False)
            return
        if self.prim is None:
            if not self.queue:
                self.chassis.set_command(0.0, 0.0, self.source)
                if abs(self.chassis.drive.get("applied", {}).get("v_mps", 0)) < 1e-3:
                    self.state = "DONE"
                return
            self.prim = self.queue.pop(0)
            self.prim["_start"] = tuple(self.pose)
            self.prim["_t0"] = self.clock.now_us()
            self.max_lat_err = self.max_head_err = 0.0
            self.events.append({"ev": "prim_start", "prim": self.prim})
        p = self.prim
        v = w = 0.0
        done = False
        move = None
        if p["kind"] == "straight":
            v, w, done, move = self._straight(p)
        elif p["kind"] == "pivot":
            e = wrap(p["yaw"] - self.pose[2])
            if abs(e) < self.cfg.yaw_tol_rad:
                done = True
            else:
                w = math.copysign(min(self.cfg.yaw_rate, 0.8 * math.sqrt(2.0 * abs(e)) + 0.01), e)
                move = {"kind": "pivot", "angle": math.copysign(min(abs(e), 0.6), e)}
        elif p["kind"] == "wait":
            done = self.clock.now_us() - p["_t0"] >= p["duration_s"] * 1e6
        if move is not None and (v or w):
            hit = self._route_check(p, move)
            if hit == "PROTECT":
                reason = ("FIELD_FRONT" if move.get("dist", 0) > 0 else "FIELD_REAR") if move["kind"] == "straight" \
                    else ("FIELD_LEFT" if move["angle"] > 0 else "FIELD_RIGHT")
                self.chassis.stop("PROTECTIVE", reason)
                self._hold("ROUTE_HOLD:" + reason, stop=False)
                return
            now = self.clock.now_us()
            if hit == "PLAN":
                self._clear_since = None
                if self._blocked_since is None:
                    self._blocked_since = now
                    self.events.append({"ev": "blocked_wait", "pose": tuple(self.pose)})
                self.state = "BLOCKED_WAIT"
                if now - self._blocked_since > self.cfg.patience_s * 1e6:
                    self.chassis.set_command(0.0, 0.0, self.source)
                    self.queue, self.state, self.reason = [], "BLOCKED", "STRIP_BLOCKED"
                    self.events.append({"ev": "blocked", "prim": p, "pose": tuple(self.pose)})
                    self.prim = None
                    return
                v = w = 0.0
            elif self.state == "BLOCKED_WAIT":
                if self._clear_since is None:
                    self._clear_since = now
                if now - self._clear_since >= self.cfg.clear_dwell_s * 1e6:
                    self.state, self._blocked_since = "RUNNING", None
                    self.events.append({"ev": "blocked_cleared", "pose": tuple(self.pose)})
                else:
                    v = w = 0.0
        if done:
            self.chassis.set_command(0.0, 0.0, self.source)
            a = self.chassis.drive.get("applied", {})
            if abs(a.get("v_mps", 0)) < 1e-3 and abs(a.get("w_radps", 0)) < 2e-3:
                self.events.append({"ev": "prim_done", "prim": p, "pose": tuple(self.pose),
                                    "max_lat_err": self.max_lat_err, "max_head_err": self.max_head_err})
                self.prim = None
            return
        if self.clock.now_us() - p["_t0"] > self._timeout_us(p):
            self.chassis.set_command(0.0, 0.0, self.source)
            self.queue, self.prim, self.state, self.reason = [], None, "FAILED", "PRIMITIVE_TIMEOUT"
            return
        self.chassis.set_command(v, w, self.source)

    def _timeout_us(self, p):
        if p["kind"] == "straight":
            d = math.hypot(p["to"][0] - p["_start"][0], p["to"][1] - p["_start"][1])
            return (d / max(p.get("speed", 0.05), 0.01) * self.cfg.prim_timeout_factor + 20.0 + self.cfg.patience_s) * 1e6
        if p["kind"] == "pivot":
            return 60e6
        return (p.get("duration_s", 0) + 5) * 1e6

    def _hold(self, reason, stop=True):
        self.chassis.clear_command()
        self.queue, self.prim = [], None           # nothing stays pending (never queued)
        self.state, self.reason = "HELD", reason
        self.events.append({"ev": "held", "reason": reason, "pose": tuple(self.pose) if self.pose else None})

    def _straight(self, p):
        cfg = self.cfg
        x, y, yaw = self.pose
        sx, sy, _ = p["_start"]
        tx, ty = p["to"]
        L = math.hypot(tx - sx, ty - sy)
        rev = bool(p.get("reverse"))
        if L < 1e-6:
            return 0.0, 0.0, True, None
        ux, uy = (tx - sx) / L, (ty - sy) / L
        d = (tx - x) * ux + (ty - y) * uy                       # remaining along-track distance
        e_y = ux * (y - sy) - uy * (x - sx)                     # + = left of the line
        line_yaw = math.atan2(uy, ux)
        e_th = wrap(yaw - (line_yaw + math.pi if rev else line_yaw))
        self.max_lat_err, self.max_head_err = max(self.max_lat_err, abs(e_y)), max(self.max_head_err, abs(e_th))
        err = abs(e_y) > cfg.lat_bound_m or abs(e_th) > cfg.head_bound_rad
        if err != self.path_error:
            self.path_error = err
            self.events.append({"ev": "path_error", "on": err, "e_y": e_y, "e_th": e_th})
        if d <= cfg.pos_tol_m:
            return 0.0, 0.0, True, None
        speed = p.get("speed") or (cfg.reverse_speed if rev else cfg.speed)
        speed = min(speed, cfg.reverse_speed) if rev else speed
        vmag = min(speed, math.sqrt(2.0 * 0.20 * d) * 0.9 + 0.004)
        if p.get("creep_m") and d < p["creep_m"]:
            vmag = min(vmag, max(0.008, 0.25 * d + 0.004))
        sgn = -1.0 if rev else 1.0
        w = sgn * (-12.0 * e_y) * max(vmag, 0.02) / 0.1 - 1.5 * e_th
        w = max(-0.25, min(0.25, w))
        return sgn * vmag, w, False, {"kind": "straight", "dist": sgn * d}

    def _route_check(self, p, move):
        cfg = self.cfg
        if len(self.obstacles) == 0 or self.clock.now_us() - self.obstacles_t > cfg.obstacle_max_age_us:
            return None
        origin = (0.0, 0.0, 0.0)                                 # obstacle points are in base_link
        if move["kind"] == "straight":
            near = dict(move, dist=math.copysign(min(abs(move["dist"]), cfg.protect_lookahead_m), move["dist"]))
        else:
            near = move
        if points_in_parts(swept_parts(self.outline, origin, near, cfg.protect_margin_m), self.obstacles).sum() >= cfg.min_points:
            return "PROTECT"
        if move["kind"] == "straight" and p.get("route") == "planning" and move["dist"] > 0:
            far = dict(move, dist=min(move["dist"], cfg.plan_lookahead_m))
            if points_in_parts(swept_parts(self.outline, origin, far, cfg.plan_margin_m, step=0.05), self.obstacles).sum() >= cfg.min_points:
                return "PLAN"
        return None
