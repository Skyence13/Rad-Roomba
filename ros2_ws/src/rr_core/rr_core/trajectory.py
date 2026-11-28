"""Trajectory buffer: pose (map frame) at arbitrary host times inside ONE
continuous epoch.

Design 0.3 ch.7: "Bracket each interval with poses from the same continuous
trajectory epoch, and split or reject observations that straddle resets or
unresolvable localization jumps."  A new epoch starts at boot, re-localisation,
datum re-registration, a chassis reset or a detected jump; interpolation never
crosses an epoch boundary or a sample gap larger than `max_gap_us`.

Sample: dict(t_us, x, y, yaw, sxx, syy, syaw (variances), q (quality 0..1),
credit (bool: localization within budget), epoch (int)).

No ROS imports.
"""
from __future__ import annotations

import bisect
import math


class PoseUnavailable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class TrajectoryBuffer:
    def __init__(self, max_gap_us: int = 150_000, jump_m: float = 0.05, jump_rad: float = 0.1, jump_corr_m: float = 0.005):
        self.max_gap_us = max_gap_us
        self.jump_m, self.jump_rad = jump_m, jump_rad
        self.jump_corr_m = jump_corr_m       # review M3: a localiser correction above this opens a new epoch (no gate spans it)
        self.t = []
        self.samples = []
        self.epoch = 0
        self.epochs = [{"epoch": 0, "t_us": None, "reason": "START"}]

    def new_epoch(self, t_us, reason: str) -> int:
        self.epoch += 1
        self.epochs.append({"epoch": self.epoch, "t_us": t_us, "reason": reason})
        return self.epoch

    def add(self, t_us, x, y, yaw, sxx=0.0, syy=0.0, syaw=0.0, q=1.0, credit=True, epoch=None, tb_us=0.0, corr_m=0.0,
            nocredit=""):
        """Append a sample (strictly increasing time).  When `epoch` is None the
        buffer assigns the current epoch and opens a new one on a jump."""
        if self.t and t_us <= self.t[-1]:
            return None
        if epoch is None:
            if self.samples and self.samples[-1]["epoch"] == self.epoch:
                last = self.samples[-1]
                dt = (t_us - last["t_us"]) * 1e-6
                if (math.hypot(x - last["x"], y - last["y"]) > self.jump_m + 0.5 * dt
                        or abs(math.atan2(math.sin(yaw - last["yaw"]), math.cos(yaw - last["yaw"]))) > self.jump_rad + 1.0 * dt):
                    self.new_epoch(t_us, "JUMP")
                elif (corr_m or 0.0) > self.jump_corr_m:
                    self.new_epoch(t_us, "CORRECTION")
            epoch = self.epoch
        else:
            if epoch != self.epoch:
                self.epoch = epoch
                self.epochs.append({"epoch": epoch, "t_us": t_us, "reason": "EXTERNAL"})
        s = {"t_us": t_us, "x": x, "y": y, "yaw": yaw, "sxx": sxx, "syy": syy, "syaw": syaw,
             "q": q, "credit": bool(credit), "epoch": epoch, "tb_us": tb_us, "corr_m": corr_m or 0.0, "nocredit": nocredit}
        self.t.append(t_us)
        self.samples.append(s)
        return s

    @property
    def latest_t(self):
        return self.t[-1] if self.t else None

    def at(self, t_us: float) -> dict:
        """Interpolated pose; raises PoseUnavailable(reason)."""
        if not self.t or t_us < self.t[0]:
            raise PoseUnavailable("BEFORE_TRAJECTORY")
        if t_us > self.t[-1]:
            raise PoseUnavailable("AFTER_TRAJECTORY")
        i = bisect.bisect_right(self.t, t_us) - 1
        a = self.samples[i]
        if a["t_us"] == t_us or i + 1 >= len(self.samples):
            return dict(a)
        b = self.samples[i + 1]
        if a["epoch"] != b["epoch"]:
            raise PoseUnavailable("EPOCH_BOUNDARY")
        if b["t_us"] - a["t_us"] > self.max_gap_us:
            raise PoseUnavailable("POSE_GAP")
        f = (t_us - a["t_us"]) / (b["t_us"] - a["t_us"])
        dyaw = math.atan2(math.sin(b["yaw"] - a["yaw"]), math.cos(b["yaw"] - a["yaw"]))
        out = {"t_us": t_us, "x": a["x"] + f * (b["x"] - a["x"]), "y": a["y"] + f * (b["y"] - a["y"]),
               "yaw": a["yaw"] + f * dyaw, "epoch": a["epoch"],
               "credit": a["credit"] and b["credit"], "q": min(a["q"], b["q"])}
        for key in ("sxx", "syy", "syaw"):
            out[key] = max(a[key], b[key])
        tb = [v.get("tb_us") for v in (a, b)]
        out["tb_us"] = None if any(v is None for v in tb) else max(tb)
        return out

    def interval(self, t0_us: float, t1_us: float, fractions=(1 / 6, 1 / 2, 5 / 6)) -> list:
        """Poses at both endpoints (validity) and at the quadrature fractions.
        All must lie in one epoch; raises PoseUnavailable otherwise."""
        p0, p1 = self.at(t0_us), self.at(t1_us)
        if p0["epoch"] != p1["epoch"]:
            raise PoseUnavailable("EPOCH_BOUNDARY")
        out = [self.at(t0_us + f * (t1_us - t0_us)) for f in fractions]
        if any(p["epoch"] != p0["epoch"] for p in out):
            raise PoseUnavailable("EPOCH_BOUNDARY")
        return [p0] + out + [p1]
