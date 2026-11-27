"""Survey processing: gates + trajectory + descriptor + calibration + profile
-> credited coverage, decision cells (MODEL.md sections 5-6), scaler-count
observations, flags and residual areas.

Pure function of its inputs: attachment manifests, gate records (from
`HeadStreamInterpreter`), trajectory samples, supervisor marks and blocked
regions.  Gates are processed in (attachment order, sequence) order once the
watermark has passed them, so the live system and the offline replay perform
the identical floating-point operations in the identical order (RQ-026).

Reason codes for floor area (design 0.3 ch.7, RQ-013/014):
    ACCEPTABLE, INSUFFICIENT_SENSITIVITY, INVALID_DATA, BLOCKED, UNVISITED, EXCLUDED

No ROS imports.
"""
from __future__ import annotations

import base64
import bisect
import json
import math

import numpy as np

from . import estimator as est
from .estimator import LaneStat
from .geometry import erode_convex, inside_convex, lane_centers, lane_polygons, transform
from .profiles import CLASS_OF_CHANNEL, decision_parameters
from .trajectory import PoseUnavailable

REASONS = ("UNVISITED", "ACCEPTABLE", "INSUFFICIENT_SENSITIVITY", "INVALID_DATA", "BLOCKED", "EXCLUDED")
CREDIT_STAGES = ("SCAN", "SEARCH", "SCALER")       # stages whose gates feed the decision cells
FLAG_RANK = {"SCAN_DETECTION": 1, "UNRESOLVED_EXCEEDANCE": 2, "INVESTIGATION_LEVEL": 3}
CHANNELS = ("beta", "alpha")


def classify_cell(d, level, policy="ALARM_ONLY"):
    """Flag kind of one decision cell, or None (review_queue_policy, contract survey_methods).
    ALARM_ONLY: a flag needs the scan-stage alarm (statistic above the decision threshold at alpha_scan,
    `d.detected`); a non-alarming cell is never flagged, whatever its D#.  ALL_UNRESOLVED: also every
    cell that cannot be cleared at the investigation level (D + kappa_beta * u >= level)."""
    if d is None or d.D is None:
        return None
    if policy == "ALARM_ONLY" and not d.detected:
        return None
    if d.D >= level:
        return "INVESTIGATION_LEVEL"
    if d.D + est.kappa(d.beta) * d.u_total >= level:
        return "UNRESOLVED_EXCEEDANCE"
    if d.detected:
        return "SCAN_DETECTION"
    return None


class SurveyConfig:
    def __init__(self, length_m, width_m, keepouts=(), sub_res=0.005, cell_m=0.10,
                 position_allowance_m=0.010, min_cell_coverage=0.5, speed_ref_mps=0.10,
                 u0_window_factor=200.0, wall_names=("left wall", "right wall"), door_name="door threshold"):
        self.length_m, self.width_m = float(length_m), float(width_m)
        self.keepouts = [tuple(k) for k in keepouts]           # (x0, x1, y0, y1) excluded from the target
        self.sub_res, self.cell_m = sub_res, cell_m
        self.position_allowance_m = position_allowance_m       # erosion of the credited footprint
        self.min_cell_coverage = min_cell_coverage
        self.speed_ref_mps = speed_ref_mps
        self.u0_window_factor = u0_window_factor               # MODEL 3 (R1, rev 4): window >= 200 T_F
        self.wall_names, self.door_name = tuple(wall_names), door_name

    def as_dict(self):
        return dict(self.__dict__, frame="map: origin inside centre of the door threshold, +x to the bulkhead, +y left")


class SurveyProcessor:
    def __init__(self, cfg: SurveyConfig, calibration, profile: dict, traj, method: dict | None = None):
        self.cfg, self.cal, self.profile, self.traj = cfg, calibration, profile, traj
        self.method = method or {"name": "CONTINUOUS_SCAN"}
        r = cfg.sub_res
        self.x0, self.y0 = 0.0, -cfg.width_m / 2
        self.nx, self.ny = int(round(cfg.length_m / r)), int(round(cfg.width_m / r))
        self.sub_per_cell = int(round(cfg.cell_m / r))
        self.ncx = int(math.ceil(self.nx / self.sub_per_cell))
        self.ncy = int(math.ceil(self.ny / self.sub_per_cell))
        self.exposure = np.zeros((self.ny, self.nx), dtype=np.float32)
        self.seen_invalid = np.zeros((self.ny, self.nx), dtype=bool)
        self.blocked = np.zeros((self.ny, self.nx), dtype=bool)
        self.excluded = np.zeros((self.ny, self.nx), dtype=bool)
        for k in cfg.keepouts:
            ix0, ix1, iy0, iy1 = self._rect_idx(k)
            self.excluded[iy0:iy1, ix0:ix1] = True
        shape = (self.ncy, self.ncx, 4)
        self.acc = {ch: {"N_F": np.zeros(shape), "T_F": np.zeros(shape)} for ch in CHANNELS}
        self.acc_ref = {"N_U": np.zeros(shape), "T_U": np.zeros(shape)}
        self.members = {}              # (cy, cx) -> list of (a_idx, seq, lane, w)
        self.cell_stage = {}           # (cy, cx) -> set of stages
        self.cell_temp = {}            # (cy, cx) -> [sum head_c * w, sum w]
        self.dirty = set()
        self.decisions = {ch: {} for ch in CHANNELS}
        self.params = decision_parameters(profile, self._count_target_cells())
        self.decider = est.Decider()
        self.sessions = []             # manifests in open order
        self._geom = {}                # a_idx -> (polys_base, eroded_base, centers_base)
        self._ref = {}                 # a_idx -> [dict seq -> (N_U, T_U)] per lane
        self._ref_cache = {}
        self._gate_geo = {}            # (a_idx, seq) -> (x, y, yaw, t_mid)
        self._gate_counts = {}         # (a_idx, seq, lane) -> (Nb, tf, Na, Nu, tu)
        self._queue = []
        self.marks = [(-1, {"stage": None, "reason": "IDLE"})]
        self._mark_t = [-1]
        self.gate_log = []
        self.gaps = []
        self.observations = {}         # obs id -> dict
        self._obs_gates = {}
        self.flags = []
        self._flag_of_cell = {}
        self.blocked_regions = []
        self._station_pending = {}     # station tag -> buffered credits (STEP_AND_COUNT)
        self._station_result = {}      # station tag -> valid?
        self.stations = []
        self.stats = {"gates": 0, "lane_gates_credited": 0, "lane_gates_rejected": 0}

    # ------------------------------------------------------------- utilities
    def _rect_idx(self, rect):
        r = self.cfg.sub_res
        ix0 = max(0, int(math.floor((rect[0] - self.x0) / r + 1e-9)))
        ix1 = min(self.nx, int(math.ceil((rect[1] - self.x0) / r - 1e-9)))
        iy0 = max(0, int(math.floor((rect[2] - self.y0) / r + 1e-9)))
        iy1 = min(self.ny, int(math.ceil((rect[3] - self.y0) / r - 1e-9)))
        return ix0, ix1, iy0, iy1

    def _count_target_cells(self) -> int:
        s = self.sub_per_cell
        n = 0
        for cy in range(self.ncy):
            for cx in range(self.ncx):
                if not self.excluded[cy * s:(cy + 1) * s, cx * s:(cx + 1) * s].all():
                    n += 1
        return n

    def cell_center(self, cy, cx):
        return (self.x0 + (cx + 0.5) * self.cfg.cell_m, self.y0 + (cy + 0.5) * self.cfg.cell_m)

    def cell_of(self, x, y):
        return (int((y - self.y0) // self.cfg.cell_m), int((x - self.x0) // self.cfg.cell_m))

    # ---------------------------------------------------------------- inputs
    def open_session(self, manifest: dict):
        desc = json.loads(base64.b64decode(manifest["descriptor_b64"]))
        mount = manifest["mount_transform"]
        polys = lane_polygons(desc, mount)
        eroded = [erode_convex(p, self.cfg.position_allowance_m) for p in polys]
        a_idx = len(self.sessions)
        self.sessions.append(manifest)
        self._geom[a_idx] = (polys, eroded, lane_centers(desc, mount))
        self._ref[a_idx] = [dict() for _ in range(4)]
        return a_idx

    def a_index(self, attachment: str) -> int:
        for i in range(len(self.sessions) - 1, -1, -1):
            if self.sessions[i]["attachment_session_id"] == attachment:
                return i
        raise KeyError(attachment)

    def lane_center_base(self, a_idx: int, lane: int):
        return self._geom[a_idx][2][lane]

    def add_mark(self, t_us: int, **mark):
        """Supervisor annotation valid from t_us: stage (SCAN|SEARCH|SCALER|COUNT|None),
        tag, reason, obs (observation id for COUNT), valid (for COUNT_END)."""
        if t_us < self._mark_t[-1]:
            raise ValueError("marks must be time ordered")
        mark = dict(mark, t_us=t_us)
        self.marks.append((t_us, mark))
        self._mark_t.append(t_us)
        if mark.get("count_end"):
            self._finish_observation(mark)
        if mark.get("station_end") is not None:
            self._finish_station(mark)

    def mark_at(self, t_us):
        return self.marks[bisect.bisect_right(self._mark_t, t_us) - 1]

    def add_gap(self, gap: dict):
        self.gaps.append(gap)

    def add_blocked_region(self, rect, reason="BLOCKED", t_us=None):
        ix0, ix1, iy0, iy1 = self._rect_idx(rect)
        self.blocked[iy0:iy1, ix0:ix1] = True
        self.blocked_regions.append({"rect": list(rect), "reason": reason, "t_us": t_us})

    def add_gate(self, gate: dict):
        self._queue.append(gate)

    def advance(self, watermark_us: float):
        """Process queued gates that end before the watermark (pose and marks complete)."""
        keep = []
        for gate in self._queue:
            if gate["t1_us"] is None or gate["t1_us"] <= watermark_us:
                self._process(gate)
            else:
                keep.append(gate)
        self._queue = keep

    def finish(self):
        self.advance(math.inf)

    # --------------------------------------------------------------- per gate
    def _process(self, gate):
        self.stats["gates"] += 1
        a_idx = self.a_index(gate["attachment"])
        seq = gate["sequence"]
        log = {"attachment": gate["attachment"], "sequence": seq, "t0_us": gate["t0_us"], "t1_us": gate["t1_us"],
               "bound_us": gate["bound_us"], "stage": None, "pose": None, "lanes": []}
        self.gate_log.append(log)
        for lane in gate["lanes"]:          # reference series for U_null (independent of pose)
            if lane["ref"] is not None and not any(r.startswith(("HEAD_FLAG", "LANE_FLAG")) for r in lane["reasons"]):
                self._ref[a_idx][lane["id"]][seq] = (lane["ref"][0], lane["ref"][1] * 1e-6)
        common = []
        poses = None
        if gate["t0_us"] is None:
            common.append("NO_HOST_TIME")
        else:
            (t_m0, m0), (t_m1, m1) = self.mark_at(gate["t0_us"]), self.mark_at(gate["t1_us"])
            stage = m0.get("stage") if t_m0 == t_m1 else None
            log["stage"] = stage
            log["tag"] = m0.get("tag")
            if stage is None:
                common.append("NO_CREDIT:" + str(m1.get("reason") or m0.get("reason") or "STATE_CHANGE"))
            try:
                poses = self.traj.interval(gate["t0_us"], gate["t1_us"])
                mid = poses[len(poses) // 2]
                log["pose"] = [mid["x"], mid["y"], mid["yaw"], mid["epoch"]]
                self._gate_geo[(a_idx, seq)] = (mid["x"], mid["y"], mid["yaw"])
                if not all(p["credit"] for p in poses):
                    common.append("POSE_UNCERTAIN")
            except PoseUnavailable as err:
                common.append("NO_POSE:" + err.reason)
                poses = None
        polys, eroded, _ = self._geom[a_idx]
        stage = log["stage"]
        for lane in gate["lanes"]:
            n = lane["id"]
            reasons = list(lane["reasons"]) + common
            ok = not reasons and eroded[n] is not None
            log["lanes"].append({"id": n, "credited": bool(ok) and stage in CREDIT_STAGES, "reasons": reasons})
            if lane["beta"] is not None and lane["ref"] is not None:
                self._gate_counts[(a_idx, seq, n)] = (lane["beta"][0], lane["beta"][1] * 1e-6,
                                                      lane["alpha"][0] if lane["alpha"] else None,
                                                      lane["ref"][0], lane["ref"][1] * 1e-6)
            if stage == "COUNT":
                if not [r for r in reasons if not r.startswith("NO_CREDIT")] and lane["beta"] is not None:
                    self._obs_gates.setdefault(self.mark_at(gate["t0_us"])[1].get("obs"), []).append((a_idx, seq, n))
                continue
            if ok and stage == "SCALER":
                # STEP_AND_COUNT: a station's gates earn credit only when the supervisor has
                # confirmed the whole count valid (stationary, no stop/inhibit event inside).
                tag = self.mark_at(gate["t0_us"])[1].get("station")
                args = (a_idx, seq, n, lane, eroded[n], poses[1:-1], stage, gate["thermal"]["head_c"], polys[n])
                if tag in self._station_result:
                    self._apply_station_credit(args, self._station_result[tag])
                else:
                    self._station_pending.setdefault(tag, []).append(args)
            elif ok and stage in CREDIT_STAGES:
                self.stats["lane_gates_credited"] += 1
                self._credit(a_idx, seq, n, lane, eroded[n], poses[1:-1], stage, gate["thermal"]["head_c"])
            else:
                self.stats["lane_gates_rejected"] += 1
                if poses is not None and stage in CREDIT_STAGES:
                    for p in poses[1:-1]:      # visited with invalid data: full (uneroded) footprint
                        mask, ix0, iy0 = self._raster(transform((p["x"], p["y"], p["yaw"]), polys[n]), False)
                        self._paint(self.seen_invalid, mask, ix0, iy0, True)

    def _apply_station_credit(self, args, valid):
        if valid:
            self.stats["lane_gates_credited"] += 1
            self._credit(*args[:8])
        else:
            self.stats["lane_gates_rejected"] += 1
            for p in args[5]:
                mask, ix0, iy0 = self._raster(transform((p["x"], p["y"], p["yaw"]), args[8]), False)
                self._paint(self.seen_invalid, mask, ix0, iy0, True)

    def _finish_station(self, mark):
        tag = mark["station_end"]
        valid = bool(mark.get("valid"))
        self._station_result[tag] = valid
        self.stations.append({"station": tag, "valid": valid, "reason": mark.get("reason"), "t_us": mark.get("t_us"),
                              "pose": mark.get("pose")})
        for args in self._station_pending.pop(tag, []):
            self._apply_station_credit(args, valid)

    def _raster(self, poly, conservative: bool):
        """Sub-cell mask of a convex polygon on the (unclipped) local lattice.
        conservative: a sub-cell counts only when all four corners are inside."""
        r = self.cfg.sub_res
        lo, hi = poly.min(axis=0), poly.max(axis=0)
        ix0, ix1 = int(math.floor((lo[0] - self.x0) / r)), int(math.ceil((hi[0] - self.x0) / r))
        iy0, iy1 = int(math.floor((lo[1] - self.y0) / r)), int(math.ceil((hi[1] - self.y0) / r))
        if conservative:
            X, Y = np.meshgrid(self.x0 + np.arange(ix0, ix1 + 1) * r, self.y0 + np.arange(iy0, iy1 + 1) * r)
            c = inside_convex(poly, X, Y)
            mask = c[:-1, :-1] & c[1:, :-1] & c[:-1, 1:] & c[1:, 1:]
        else:
            X, Y = np.meshgrid(self.x0 + (np.arange(ix0, ix1) + 0.5) * r, self.y0 + (np.arange(iy0, iy1) + 0.5) * r)
            mask = inside_convex(poly, X, Y)
        return mask, ix0, iy0

    def _clip(self, mask, ix0, iy0):
        h, w = mask.shape
        cx0, cy0 = max(0, -ix0), max(0, -iy0)
        cx1, cy1 = min(w, self.nx - ix0), min(h, self.ny - iy0)
        if cx1 <= cx0 or cy1 <= cy0:
            return None
        return mask[cy0:cy1, cx0:cx1], ix0 + cx0, iy0 + cy0

    def _paint(self, target, mask, ix0, iy0, value):
        c = self._clip(mask, ix0, iy0)
        if c is not None:
            m, x, y = c
            target[y:y + m.shape[0], x:x + m.shape[1]][m] = value

    def _credit(self, a_idx, seq, n, lane, eroded, poses, stage, head_c):
        tf_b, tf_a, tu = lane["beta"][1] * 1e-6, lane["alpha"][1] * 1e-6, lane["ref"][1] * 1e-6
        s = self.sub_per_cell
        total = 0
        per_cell = {}
        for p in poses:
            mask, ix0, iy0 = self._raster(transform((p["x"], p["y"], p["yaw"]), eroded), True)
            total += int(mask.sum())
            c = self._clip(mask, ix0, iy0)
            if c is None:
                continue
            m, x, y = c
            m = m & ~self.excluded[y:y + m.shape[0], x:x + m.shape[1]]
            self.exposure[y:y + m.shape[0], x:x + m.shape[1]][m] += tf_b / len(poses)
            yy, xx = np.nonzero(m)
            if len(yy):
                ids = ((yy + y) // s) * self.ncx + (xx + x) // s
                for cid, cnt in zip(*np.unique(ids, return_counts=True)):
                    per_cell[int(cid)] = per_cell.get(int(cid), 0) + int(cnt)
        if total == 0:
            return
        for cid in sorted(per_cell):
            w = per_cell[cid] / total
            if w < est.MIN_LANE_GATE_WEIGHT:      # MODEL 5 (R5): excluded from the decision statistic
                continue
            w = round(w / est.WEIGHT_STEP) * est.WEIGHT_STEP      # MODEL 6 rev 4: weights on a 0.05 lattice (rule and statistic)
            cy, cx = divmod(cid, self.ncx)
            self.acc["beta"]["N_F"][cy, cx, n] += w * lane["beta"][0]
            self.acc["beta"]["T_F"][cy, cx, n] += w * tf_b
            self.acc["alpha"]["N_F"][cy, cx, n] += w * lane["alpha"][0]
            self.acc["alpha"]["T_F"][cy, cx, n] += w * tf_a
            self.acc_ref["N_U"][cy, cx, n] += w * lane["ref"][0]
            self.acc_ref["T_U"][cy, cx, n] += w * tu
            self.members.setdefault((cy, cx), []).append((a_idx, seq, n, w))
            self.cell_stage.setdefault((cy, cx), set()).add(stage)
            if head_c is not None:
                t = self.cell_temp.setdefault((cy, cx), [0.0, 0.0])
                t[0] += head_c * w
                t[1] += w
            self.dirty.add((cy, cx))

    # ----------------------------------------------------------------- U_null
    def _ref_prefix(self, a_idx, lane):
        key = (a_idx, lane)
        series = self._ref[a_idx][lane]
        cached = self._ref_cache.get(key)
        if cached is None or cached[0] != len(series):
            seqs = sorted(series)
            n = np.cumsum([0.0] + [series[q][0] for q in seqs])
            t = np.cumsum([0.0] + [series[q][1] for q in seqs])
            cached = (len(series), seqs, n, t)
            self._ref_cache[key] = cached
        return cached[1:]

    def _u_null(self, lane, members, T_F, span_s=0.1):
        """MODEL 3 (R1, revision 4): U_null = mean reference rate of the lane over a window of at least
        u0_window_factor * T_F centred on the dwell, EXCLUDING the gates under test; if the lane window is
        shorter, the four-lane pooled rate over a window of the same length, also excluding the gates under
        test (all four lanes at those sequences).  Never a same-gate pool.  Returns
        (U_null | None, method, window live time s, window counts)."""
        factor = self.cfg.u0_window_factor
        half = max(100, int(math.ceil(0.5 * factor * T_F / span_s)))
        under_test = {}
        for a_idx, seq, _ln, _w in members:
            under_test.setdefault(a_idx, set()).add(seq)
        own_by_a = {}
        for a_idx, seq, ln, _w in members:
            if ln == lane:
                own_by_a.setdefault(a_idx, set()).add(seq)

        def window(ln, excl):
            N = T = 0.0
            for a_idx, own in excl.items():
                seqs, cn, ct = self._ref_prefix(a_idx, ln)
                intervals = []
                for q in sorted(own):
                    lo, hi = q - half, q + half
                    if intervals and lo <= intervals[-1][1]:
                        intervals[-1][1] = hi
                    else:
                        intervals.append([lo, hi])
                for lo, hi in intervals:
                    i0, i1 = bisect.bisect_left(seqs, lo), bisect.bisect_right(seqs, hi)
                    N += cn[i1] - cn[i0]
                    T += ct[i1] - ct[i0]
                series = self._ref[a_idx][ln]
                for q in own:
                    if q in series:
                        N -= series[q][0]
                        T -= series[q][1]
            return N, T
        N, T = window(lane, own_by_a)
        if T >= factor * T_F and T > 0:
            return N / T, f"lane-window-excluding-test(+/-{half} gates)", T, N
        N = T = 0.0
        for ln in range(4):
            n_, t_ = window(ln, under_test)
            N += n_
            T += t_
        if T >= factor * T_F and T > 0:
            return N / T, f"four-lane-pooled-window-excluding-test(+/-{half} gates)", T, N
        return None, "unavailable", T, N

    # -------------------------------------------------------------- decisions
    def _lane_gates(self, lane, keys_w, channel, goal=None, alpha=None, head_c=None, members_all=None, T_F_hint=None):
        """LaneGates of one lane from (key, weight) gate list; U_null by MODEL 3."""
        ch = 0 if channel == "beta" else 2
        w = np.array([w for _k, w in keys_w])
        cnt = [self._gate_counts[k] for k, _w in keys_w]
        N_F = np.array([c[ch] for c in cnt])
        tf = np.array([c[1] for c in cnt])
        N_U = np.array([c[3] for c in cnt])
        tu = np.array([c[4] for c in cnt])
        return w, tf, N_F, tu, N_U

    def _cell_decision(self, cy, cx, channel, alpha):
        members = self.members.get((cy, cx), [])
        temp = self.cell_temp.get((cy, cx))
        head_c = temp[0] / temp[1] if temp and temp[1] else None
        goal = self.profile["detection_goal_Bq_cm2"]
        stats = []
        for lane in range(4):
            T_F = float(self.acc[channel]["T_F"][cy, cx, lane])
            T_U = float(self.acc_ref["T_U"][cy, cx, lane])
            if T_F <= 0 or T_U <= 0:
                continue
            gk = [((a, q, ln), w) for a, q, ln, w in members if ln == lane and (a, q, ln) in self._gate_counts]
            if not gk:
                continue
            w, tf, N_F, tu, N_U = self._lane_gates(lane, gk, channel)
            U0, how, T_win, N_win = self._u_null(lane, members, float(np.dot(w, tf)))
            ok, why = (True, "") if U0 is None else self.cal.check_envelope(lane, channel, U0, head_c, goal=goal, alpha=alpha,
                                                                         beta=self.params["beta"])
            stats.append(est.LaneGates(lane, w, tf, N_F, tu, N_U, U0, how, self.cal.cal(lane, channel), ok, why,
                                       u0_window_s=T_win, u0_window_counts=N_win))
        return est.combine(stats, alpha, self.params["beta"], decider=self.decider)

    def cell_coverage(self, cy, cx) -> float:
        s = self.sub_per_cell
        sl = (slice(cy * s, (cy + 1) * s), slice(cx * s, (cx + 1) * s))
        target = ~self.excluded[sl]
        n = int(target.sum())
        return float(((self.exposure[sl] > 0) & target).sum()) / n if n else 0.0

    def evaluate(self, channels=None) -> list:
        """Re-evaluate dirty decision cells; returns new/changed flags."""
        channels = channels or [self._decision_channel()]
        changed = []
        for (cy, cx) in sorted(self.dirty):
            for ch in channels:
                d = self._cell_decision(cy, cx, ch, self.params["alpha_scan"])
                self.decisions[ch][(cy, cx)] = d
                if ch == self._decision_channel():
                    flag = self._update_flag(cy, cx, ch, d)
                    if flag is not None:
                        changed.append(flag)
        self.dirty.clear()
        return changed

    def _decision_channel(self):
        cls = self.profile["decision_class"]
        return next(ch for ch, c in CLASS_OF_CHANNEL.items() if c == cls)

    def sensitivity_ok(self, d) -> bool:
        """MODEL 3: D# strictly below the goal AND calibration envelope valid."""
        return bool(d is not None and d.D_hash is not None and d.envelope_ok
                    and d.D_hash < self.profile["detection_goal_Bq_cm2"])

    # ------------------------------------------------------------------ flags
    def _classify(self, d):
        return classify_cell(d, self.profile["investigation_level_Bq_cm2"], self.params["review_queue_policy"])

    def _update_flag(self, cy, cx, channel, d):
        if self.cell_coverage(cy, cx) < self.cfg.min_cell_coverage:
            return None
        kind = self._classify(d)
        if kind is None:
            return None
        flag = self._flag_of_cell.get((cy, cx))
        if flag is None:
            for dy in (-1, 0, 1):               # join an adjacent flag; never merge existing flags
                for dx in (-1, 0, 1):
                    other = self._flag_of_cell.get((cy + dy, cx + dx))
                    if other is not None and (flag is None or other["n"] < flag["n"]):
                        flag = other
            if flag is None:
                flag = {"n": len(self.flags) + 1, "id": f"HS-{len(self.flags) + 1:04d}", "kind": kind,
                        "class": CLASS_OF_CHANNEL[channel], "cells": [], "status": "OPEN",
                        "observations": [], "visits": []}
                self.flags.append(flag)
            flag["cells"].append([cy, cx])
            self._flag_of_cell[(cy, cx)] = flag
        if FLAG_RANK[kind] > FLAG_RANK[flag["kind"]]:
            flag["kind"] = kind
        self._locate_flag(flag, channel)
        return flag

    def _locate_flag(self, flag, channel):
        """Peak cell, source lane, saved footprint, named location, contributing gates."""
        dec = self.decisions[channel]
        peak = max((tuple(c) for c in flag["cells"]), key=lambda c: dec[c].D)
        d = dec[peak]
        excess = {}
        contributing = []
        for cell in flag["cells"]:
            U0 = {ln["lane"]: ln["U0"] for ln in dec[tuple(cell)].lanes}
            for a_idx, seq, lane, w in self.members.get(tuple(cell), []):
                counts = self._gate_counts.get((a_idx, seq, lane))
                geo = self._gate_geo.get((a_idx, seq))
                if counts is None or geo is None or lane not in U0:
                    continue
                cal = self.cal.cal(lane, channel)
                n_f = counts[0] if channel == "beta" else counts[2]
                e = max(0.0, n_f - (cal.k * U0[lane] + cal.b) * counts[1])
                contributing.append([self.sessions[a_idx]["attachment_session_id"], seq, lane])
                if e > 0:
                    c = transform(geo, [self.lane_center_base(a_idx, lane)])[0]
                    excess.setdefault(lane, []).append((e, c[0], c[1], geo[2], a_idx, seq))
        if excess:
            lane = max(excess, key=lambda k: sum(v[0] for v in excess[k]))
            rows = excess[lane]
            wsum = sum(v[0] for v in rows)
            x = sum(v[0] * v[1] for v in rows) / wsum
            y = sum(v[0] * v[2] for v in rows) / wsum
            best = max(rows, key=lambda v: v[0])
            yaw, a_idx = best[3], best[4]
        else:
            lane, (x, y), yaw, a_idx = None, self.cell_center(*peak), 0.0, len(self.sessions) - 1
        poly = None
        if lane is not None:
            base_poly = self._geom[a_idx][0][lane]
            off = np.array([x, y]) - transform((0.0, 0.0, yaw), [self.lane_center_base(a_idx, lane)])[0]
            poly = (transform((off[0], off[1], yaw), base_poly)).round(4).tolist()
        half_w = self.cfg.width_m / 2
        wall = self.cfg.wall_names[0] if y >= 0 else self.cfg.wall_names[1]
        flag.update({
            "peak_cell": list(peak), "D": d.D, "u_stat": d.u_stat, "u_total": d.u_total, "D_star": d.D_star,
            "D_hash": d.D_hash, "method": d.method, "m": d.m, "alpha_lane": d.alpha_lane,
            "flagged_lanes": list(d.flagged_lanes), "decision_rule": d.rule,
            "flagged_by": list(d.flagged_by), "status": d.status,
            "lane_thresholds": [{k: l[k] for k in ("lane", "D_star", "method", "flagged")} for l in d.lanes], "x_m": x, "y_m": y, "heading_rad": yaw,
            "source_lane": lane, "footprint": poly,
            "location": {"distance_from_door_m": round(x, 3), "wall": wall,
                         "distance_from_wall_m": round(half_w - abs(y), 3),
                         "text": f"{x:.2f} m from the {self.cfg.door_name}, {half_w - abs(y):.2f} m from the {wall}"},
            "position_uncertainty_m": self.cfg.position_allowance_m,
            "attachment": self.sessions[a_idx]["attachment_session_id"] if self.sessions else None,
            "contributing_gates": sorted(map(tuple, {tuple(c) for c in contributing}))[:400],
            "stage": sorted(set().union(*[self.cell_stage.get(tuple(c), set()) for c in flag["cells"]])),
            "recommendation": self.recommend(peak, channel)})

    def recommend(self, cell, channel) -> dict:
        """Bounded stationary recount / slower pass recommendation (RQ-023, VT-022)."""
        return {"action": "STATIONARY_COUNT", "duration_s": self.params["recount_default_s"],
                "max_s": self.params["recount_max_s"], "alpha": self.params["alpha_recount"],
                "rule": "two-stage: scan flag -> stationary recount at alpha_recount (MODEL.md 3, R3)"}

    def recommend_for_shortfall(self, d, speed_mps) -> dict:
        goal = self.profile["detection_goal_Bq_cm2"]
        if d is None or d.D_hash is None or not d.envelope_ok:
            return {"action": "REFER_TO_RP", "why": (d.envelope_reason if d else "") or "no valid estimate"}
        need = (d.D_hash / goal) ** 2          # counting-dominated scaling of the required dwell
        if not math.isfinite(need):
            return {"action": "REFER_TO_RP", "why": "detection limit undefined"}
        v = speed_mps / need
        if v >= 0.02:
            return {"action": "SLOWER_PASS", "speed_mps": round(v, 3), "dwell_factor": round(need, 2)}
        t = min(self.params["recount_max_s"], max(self.params["recount_default_s"], d.T_F * need))
        return {"action": "STATIONARY_COUNT", "duration_s": round(t, 1), "max_s": self.params["recount_max_s"]}

    # ------------------------------------------------------------ observations
    def _finish_observation(self, mark):
        """Scaler count (contract survey_methods): evaluate at alpha_recount."""
        obs_id = mark["obs"]
        keys = self._obs_gates.get(obs_id, [])
        channel = self._decision_channel()
        target = mark.get("lane")
        lanes_out, decision = [], None
        for lane in range(4):
            mine = [k for k in keys if k[2] == lane]
            if not mine:
                continue
            g = self._count_lane(mine, lane, channel, self.params["alpha_recount"])
            d = est.combine([g], self.params["alpha_recount"], self.params["beta"], decider=self.decider)
            lanes_out.append({"lane": lane, **{k: getattr(d, k) for k in
                              ("D", "u_stat", "u_total", "D_star", "D_hash", "T_F", "detected", "method", "m", "alpha_lane", "status")},
                              "N_F": float(g.N_F.sum()), "N_U": float(g.N_U.sum()), "U0": g.U0, "u0_method": g.u0_method,
                              "envelope_ok": g.envelope_ok})
            if lane == target:
                decision = d
        valid = bool(mark.get("valid")) and decision is not None
        level = self.profile["investigation_level_Bq_cm2"]
        outcome = "INVALID"
        if valid:
            kb = est.kappa(decision.beta)
            if decision.D >= level:
                outcome = "EXCEEDS_INVESTIGATION_LEVEL"
            elif decision.D + kb * decision.u_total >= level:
                outcome = "INCONCLUSIVE"            # a marginal estimate alone cannot clear a patch
            elif decision.detected:
                outcome = "DETECTED_BELOW_INVESTIGATION_LEVEL"
            elif self.sensitivity_ok(decision):
                outcome = "NOT_DETECTED_SENSITIVITY_SUFFICIENT"
            else:
                outcome = "INCONCLUSIVE"
        obs = {"id": obs_id, "flag": mark.get("flag"), "lane": target, "valid": valid,
               "invalid_reason": mark.get("reason"), "outcome": outcome, "stage": "SCALER",
               "mode": mark.get("mode"), "alpha": self.params["alpha_recount"], "beta": self.params["beta"],
               "n_gates": len({(k[0], k[1]) for k in keys}), "pose": mark.get("pose"),
               "target_xy": mark.get("target_xy"), "achieved_xy": mark.get("achieved_xy"),
               "t_end_us": mark.get("t_us"), "lanes": lanes_out,
               "result": None if decision is None else {k: getattr(decision, k) for k in
                                                         ("D", "u_stat", "u_total", "D_star", "D_hash", "T_F", "detected", "method", "m", "alpha_lane", "status")}}
        self.observations[obs_id] = obs
        for flag in self.flags:
            if flag["id"] == mark.get("flag"):
                flag["observations"].append(obs_id)
        return obs

    def _count_lane(self, keys, lane, channel, alpha):
        """LaneGates of a stationary count (weights 1); U_null from the window excluding these gates."""
        ch = 0 if channel == "beta" else 2
        cnt = [self._gate_counts[k] for k in keys]
        w = np.ones(len(keys))
        tf = np.array([c[1] for c in cnt])
        U0, how, T_win, N_win = self._u_null(lane, [(k[0], k[1], k[2], 1.0) for k in keys], float(tf.sum()))
        ok, why = (True, "") if U0 is None else self.cal.check_envelope(
            lane, channel, U0, None, goal=self.profile["detection_goal_Bq_cm2"], alpha=alpha, beta=self.params["beta"])
        return est.LaneGates(lane, w, tf, [c[ch] for c in cnt], [c[4] for c in cnt], [c[3] for c in cnt], U0, how,
                             self.cal.cal(lane, channel), ok, why, u0_window_s=T_win, u0_window_counts=N_win)

    def live_count_state(self, obs_id, lane, t_now_us):
        """Running scaler result for the ADAPTIVE mode (D#, D, D*) from gates so far."""
        keys = [k for k in self._obs_gates.get(obs_id, []) if k[2] == lane]
        if not keys:
            return None
        return est.combine([self._count_lane(keys, lane, self._decision_channel(), self.params["alpha_recount"])],
                           self.params["alpha_recount"], self.params["beta"], decider=self.decider)

    # ---------------------------------------------------------------- outputs
    def classify_subcells(self) -> np.ndarray:
        """uint8 raster of REASONS indices for every sub-cell of the target."""
        self.evaluate()
        ch = self._decision_channel()
        s = self.sub_per_cell
        cell_ok = np.zeros((self.ncy, self.ncx), dtype=bool)
        for (cy, cx), d in self.decisions[ch].items():
            cell_ok[cy, cx] = self.sensitivity_ok(d)
        ok_sub = np.repeat(np.repeat(cell_ok, s, axis=0), s, axis=1)[:self.ny, :self.nx]
        out = np.zeros((self.ny, self.nx), dtype=np.uint8)                 # UNVISITED
        out[self.seen_invalid] = REASONS.index("INVALID_DATA")
        out[self.blocked] = REASONS.index("BLOCKED")
        covered = self.exposure > 0
        out[covered] = REASONS.index("INSUFFICIENT_SENSITIVITY")
        out[covered & ok_sub] = REASONS.index("ACCEPTABLE")
        out[self.excluded] = REASONS.index("EXCLUDED")
        return out

    def coverage_summary(self) -> dict:
        cls = self.classify_subcells()
        a = self.cfg.sub_res ** 2
        target = int((~self.excluded).sum())
        areas = {name: float((cls == i).sum()) * a for i, name in enumerate(REASONS)}
        credited = areas["ACCEPTABLE"] + areas["INSUFFICIENT_SENSITIVITY"]
        return {"target_area_m2": target * a, "areas_m2": areas,
                "valid_exposure_fraction": credited / (target * a) if target else 0.0,
                "acceptable_fraction": areas["ACCEPTABLE"] / (target * a) if target else 0.0,
                "sub_cell_m": self.cfg.sub_res, "decision_cell_m": self.cfg.cell_m,
                "position_allowance_m": self.cfg.position_allowance_m}

    def residuals(self, min_area_m2: float = 0.0) -> list:
        """Unresolved floor as axis-aligned rectangles (local x/y metres) with reason codes."""
        cls = self.classify_subcells()
        r = self.cfg.sub_res
        out = []
        for i, name in enumerate(REASONS):
            if name in ("ACCEPTABLE", "EXCLUDED"):
                continue
            mask = cls == i
            open_runs = {}
            for iy in range(self.ny + 1):
                runs = set()
                if iy < self.ny:
                    row = np.flatnonzero(np.diff(np.concatenate(([0], mask[iy].view(np.int8), [0]))))
                    runs = {(int(a), int(b)) for a, b in zip(row[::2], row[1::2])}
                for run in list(open_runs):
                    if run not in runs:
                        y_start = open_runs.pop(run)
                        rect = {"reason": name, "x0": round(self.x0 + run[0] * r, 4), "x1": round(self.x0 + run[1] * r, 4),
                                "y0": round(self.y0 + y_start * r, 4), "y1": round(self.y0 + iy * r, 4)}
                        rect["area_m2"] = round((rect["x1"] - rect["x0"]) * (rect["y1"] - rect["y0"]), 6)
                        if rect["area_m2"] >= min_area_m2:
                            out.append(rect)
                for run in runs:
                    open_runs.setdefault(run, iy)
        return sorted(out, key=lambda q: (q["reason"], q["x0"], q["y0"], q["x1"], q["y1"]))

    def cells_table(self, channels=CHANNELS) -> list:
        """One row per decision cell (design 0.3 ch.7 "production floor grid")."""
        self.evaluate()
        for ch in channels:                        # fill channels not evaluated live
            for key in sorted(self.members):
                if key not in self.decisions[ch]:
                    self.decisions[ch][key] = self._cell_decision(key[0], key[1], ch, self.params["alpha_scan"])
        rows = []
        for cy in range(self.ncy):
            for cx in range(self.ncx):
                x, y = self.cell_center(cy, cx)
                row = {"ix": cx, "iy": cy, "x_m": round(x, 4), "y_m": round(y, 4),
                       "coverage_fraction": round(self.cell_coverage(cy, cx), 4),
                       "stage": "+".join(sorted(self.cell_stage.get((cy, cx), []))),
                       "method": self.method["name"], "n_lane_gates": len(self.members.get((cy, cx), [])),
                       "review_queue_policy": self.params["review_queue_policy"], "alpha_decision": self.params["alpha_scan"]}
                for ch in channels:
                    d = self.decisions[ch].get((cy, cx))
                    p = CLASS_OF_CHANNEL[ch]
                    for name in ("D", "u_stat", "u_total", "D_star", "D_hash", "T_F"):
                        v = getattr(d, name) if d is not None else None
                        row[f"{p}.{name}"] = None if v is None or not math.isfinite(v) else v
                    row[f"{p}.detected"] = d.detected if d else None
                    row[f"{p}.threshold_method"] = d.method if d else ""
                    row[f"{p}.u0_method"] = "|".join(d.u0_methods) if d else ""
                    # MODEL.md rev 3 section 6 (IB-31): per-cell decision record
                    row[f"{p}.decision_rule"] = d.rule if d and d.m else ""
                    row[f"{p}.decision_status"] = (d.status_text or "ok") if d and d.D is not None else ""
                    row[f"{p}.m_lanes"] = d.m if d and d.m else None
                    row[f"{p}.c_weights"] = "|".join(f"{x:.4f}" for x in d.c) if d and d.m else ""
                    row[f"{p}.alpha_combined"] = d.alpha_comb if d and d.m else None
                    row[f"{p}.alpha_lane"] = d.alpha_lane if d and d.m else None
                    row[f"{p}.u0_windows"] = ";".join(f"L{l['lane']}:{l['U0']:.4g}/s:{(l['u0_window_s'] or 0):.0f}s:{int(l['u0_window_counts'] or 0)}cnt"
                                                      for l in d.lanes) if d and d.m else ""
                    row[f"{p}.lane_thresholds"] = ";".join(
                        f"L{l['lane']}:t*={l['D_star']:.4g}:{l['method']}" for l in d.lanes) if d and d.m else ""
                    row[f"{p}.flagged_by"] = "|".join(d.flagged_by) if d and d.m else ""
                    row[f"{p}.evaluator_check"] = ("ok" if d.check_ok else "FAILED") if d and d.m else ""
                    row[f"{p}.sensitivity_sufficient"] = bool(self.sensitivity_ok(d)) if d and d.D is not None else None
                    row[f"{p}.envelope"] = (d.envelope_reason or "ok") if d and d.D is not None else ""
                flag = self._flag_of_cell.get((cy, cx))
                row["flag"] = flag["id"] if flag else ""
                rows.append(row)
        return rows
