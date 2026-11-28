"""Survey processing: gates + trajectory + descriptor + calibration + profile
-> credited coverage, decision cells (MODEL.md revision 5, sections 3, 5, 6), scaler-count
observations, flags and residual areas.

Pure function of its inputs: attachment manifests (each with its own calibration binding), gate records (from
`HeadStreamInterpreter`), per-gate head statistics (GATESTAT), trajectory samples, supervisor marks and blocked
regions.

Two kinds of cell result (MODEL.md rev 5 section 3 "When a decision is evaluated"):
    provisional  evaluated live (every journaled `evaluate`, on the reference data received so far); drives the
                 live display, the flags of the review queue during the survey and nothing else; labelled
                 `provisional` wherever shown or exported.
    recorded     evaluated ONCE per cell by `finalize()` from the complete attachment record (all qualifying data,
                 members and reference windows sorted, a fresh evaluator, exact inputs): independent of the order in
                 which gates arrived and of the live evaluation schedule.  Exports carry the recorded result.
Per cell the first provisional alarm and the recorded decision are kept with their data times; a provisional alarm
not confirmed is recorded `provisional alarm not confirmed`, a recorded alarm without a provisional one
`alarm found at final evaluation` (and enters the revisit list).

Cell status (MODEL.md rev 5 section 6), precedence ALARM > NO DECISION > INCOMPLETE COVERAGE > SENSITIVITY
INSUFFICIENT > ACCEPTABLE; an alarm is never suppressed by coverage.  Sub-cell classes of the coverage map:
    UNVISITED, ACCEPTABLE, INSUFFICIENT_SENSITIVITY, INVALID_DATA, BLOCKED, EXCLUDED, NO_DECISION,
    INCOMPLETE_COVERAGE, ALARM, ACQUISITION_GAP
ACCEPTABLE is painted only in cells whose status is ACCEPTABLE; an ALARM cell is painted ALARM over its whole area.

No ROS imports.
"""
from __future__ import annotations

import base64
import bisect
import json
import math

import numpy as np

from . import estimator as est
from . import unull
from .estimator import LaneStat  # noqa: F401  (re-export for older callers)
from .geometry import convex_hull, erode_convex, inside_convex, lane_centers, lane_polygons, rect_clip_area, transform
from .profiles import CLASS_OF_CHANNEL, decision_parameters
from .trajectory import PoseUnavailable

REASONS = ("UNVISITED", "ACCEPTABLE", "INSUFFICIENT_SENSITIVITY", "INVALID_DATA", "BLOCKED", "EXCLUDED",
           "NO_DECISION", "INCOMPLETE_COVERAGE", "ALARM", "ACQUISITION_GAP")
STATUS_PRECEDENCE = ("ALARM", "NO DECISION", "INCOMPLETE COVERAGE", "SENSITIVITY INSUFFICIENT", "ACCEPTABLE")
CREDIT_STAGES = ("SCAN", "SEARCH", "SCALER")       # stages whose gates feed the decision cells
FLAG_RANK = {"SCAN_DETECTION": 1, "UNRESOLVED_EXCEEDANCE": 2, "INVESTIGATION_LEVEL": 3, "RATE_SATURATION": 4}
CHANNELS = ("beta", "alpha")
NO_CALIBRATION = "no result — no calibration for this head and setup"
RATE_ALARM = "ALARM — rate above counting range"
FOOTPRINT_MODEL = ("MODEL.md rev 5 section 6: lane aperture polygon of the descriptor (head_mount frame, mount transform of the "
                   "attachment) eroded on every side by the gate's credited 2 sigma position uncertainty at the lane "
                   "(2 sqrt(max(var_x, var_y) + r^2 var_yaw) over the gate's poses, r = farthest aperture corner from base_link; "
                   "credit refused above the position allowance), swept from gate start to gate end (convex hull of the eroded "
                   "polygon at the start, middle and end poses); weight = exact area fraction of the swept polygon inside the "
                   "0.10 m cell, rounded to the nearest 0.05, weights below 0.10 excluded from the statistic; coverage painted on "
                   "5 mm sub-cells whose four corners lie inside the swept polygon")
FOOTPRINT_MODEL_BEFORE = ("before 2026-11-28: fixed 10 mm erosion; three snapshot footprints at 1/6, 1/2, 5/6 of the gate "
                          "rasterised on 5 mm sub-cells (all four corners inside); weight = sub-cells in the cell / all "
                          "sub-cells of the three snapshots, cut at 0.10 before rounding to 0.05")


def classify_cell(d, level, policy="ALARM_ONLY"):
    """Flag kind of one decision cell, or None (review_queue_policy, contract survey_methods).
    ALARM_ONLY: a flag needs the alarm (`d.detected`).  ALL_UNRESOLVED: also every cell that cannot be cleared at
    the investigation level (D + kappa_beta * u >= level)."""
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
                 u0_window_factor=None, wall_names=("left wall", "right wall"), door_name="door threshold",
                 speed_tolerance_mps=0.002):
        self.length_m, self.width_m = float(length_m), float(width_m)
        self.keepouts = [tuple(k) for k in keepouts]           # (x0, x1, y0, y1) excluded from the target
        self.sub_res, self.cell_m = sub_res, cell_m
        self.position_allowance_m = position_allowance_m       # maximum credited 2 sigma (footprint erosion budget)
        self.min_cell_coverage = min_cell_coverage             # default when the profile has no minimum_cell_coverage
        self.speed_ref_mps = speed_ref_mps
        self.u0_window_factor = u0_window_factor               # revision 4 (superseded); kept for old run.json files
        self.speed_tolerance_mps = speed_tolerance_mps         # numerical tolerance of the envelope speed check
        self.wall_names, self.door_name = tuple(wall_names), door_name

    def as_dict(self):
        return dict(self.__dict__, frame="map: origin inside centre of the door threshold, +x to the bulkhead, +y left")


class SurveyProcessor:
    def __init__(self, cfg: SurveyConfig, calibration, profile: dict, traj, method: dict | None = None,
                 calibrations=None):
        self.cfg, self.cal, self.profile, self.traj = cfg, calibration, profile, traj
        self.cal_by_id = {c.calibration_id: c for c in (calibrations or [])}
        if calibration is not None:
            self.cal_by_id.setdefault(calibration.calibration_id, calibration)
        self.method = method or {"name": "CONTINUOUS_SCAN"}
        r = cfg.sub_res
        self.x0, self.y0 = 0.0, -cfg.width_m / 2
        self.nx, self.ny = int(round(cfg.length_m / r)), int(round(cfg.width_m / r))
        self.sub_per_cell = int(round(cfg.cell_m / r))
        self.ncx = int(math.ceil(self.nx / self.sub_per_cell))
        self.ncy = int(math.ceil(self.ny / self.sub_per_cell))
        self.exposure = np.zeros((self.ny, self.nx), dtype=np.float32)
        self.seen_invalid = np.zeros((self.ny, self.nx), dtype=bool)
        self.gap_seen = np.zeros((self.ny, self.nx), dtype=bool)
        self.blocked = np.zeros((self.ny, self.nx), dtype=bool)
        self.excluded = np.zeros((self.ny, self.nx), dtype=bool)
        for k in cfg.keepouts:
            ix0, ix1, iy0, iy1 = self._rect_idx(k)
            self.excluded[iy0:iy1, ix0:ix1] = True
        self.members = {}              # (cy, cx) -> list of (a_idx, seq, lane, w)
        self.member_erosion = {}       # (a_idx, seq, lane) -> credited erosion (m)
        self.cell_stage = {}           # (cy, cx) -> set of stages
        self.cell_temp = {}            # (cy, cx) -> [sum head_c * w, sum w]
        self.cell_fault = {}           # (cy, cx) -> number of lane-gates over the cell excluded for a fault
        self.dirty = set()
        self.decisions = {ch: {} for ch in CHANNELS}       # what is shown now: recorded where finalised, else provisional
        self.provisional = {ch: {} for ch in CHANNELS}
        self.recorded = {ch: {} for ch in CHANNELS}
        self.first_provisional_alarm = {}                  # (cy, cx) -> record
        self.revisit = []                                  # recorded alarms without a provisional one
        self._recorded_version = None
        self._version = 0
        self.params = decision_parameters(profile, self._count_target_cells())
        self.decider = est.Decider(quantise=True)       # provisional (live) results only; finalize() uses an exact one
        self.sessions = []             # manifests in open order
        self.att = []                  # per attachment: calibration, binding status
        self._geom = {}                # a_idx -> (polys_base, None, centers_base, lever per lane)
        self._ref = {}                 # a_idx -> {seq: [(N_U, T_U) or None] * 4}
        self._series_cache = {}
        self._gate_geo = {}            # (a_idx, seq) -> (x, y, yaw)
        self._gate_t = {}              # (a_idx, seq) -> (t0_us, t1_us, speed_mps)
        self._gate_counts = {}         # (a_idx, seq, lane) -> (Nb, tf, Na, Nu, tu)
        self.gatestat = {}             # (a_idx, seq) -> GATESTAT record (head 0.6.0)
        self.saturated = {}            # (a_idx, seq, lane) -> {"cells": [...], "poly": ...}
        self._queue = []
        self.marks = [(-1, {"stage": None, "reason": "IDLE"})]
        self._mark_t = [-1]
        self.gate_log = []
        self.gaps = []
        self.diag = {}                 # (a_idx, seq) -> DIAG members per gate (alpha_short ...)
        self.observations = {}         # obs id -> dict
        self._obs_gates = {}
        self.flags = []
        self._flag_of_cell = {}
        self.blocked_regions = []
        self._station_pending = {}     # station tag -> buffered credits (STEP_AND_COUNT)
        self._station_result = {}      # station tag -> valid?
        self.stations = []
        self.stats = {"gates": 0, "lane_gates_credited": 0, "lane_gates_rejected": 0, "gap_gates_painted": 0}

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

    def min_cell_coverage(self):
        v = self.profile.get("minimum_cell_coverage")
        return float(v) if v is not None else float(self.cfg.min_cell_coverage)

    # ---------------------------------------------------------------- inputs
    def open_session(self, manifest: dict):
        """New attachment.  The calibration is the one BOUND to this attachment by the head link (manifest
        `calibration`, produced by CalibrationStore.resolve); without a binding record naming a known calibration whose
        identity was checked (or a declared demonstration binding) the attachment's data are archived and reported
        `no result - no calibration for this head and setup` (MODEL.md rev 5 section 1; review C2)."""
        desc = json.loads(base64.b64decode(manifest["descriptor_b64"]))
        mount = manifest["mount_transform"]
        polys = lane_polygons(desc, mount)
        lever = [float(np.max(np.hypot(p[:, 0], p[:, 1]))) for p in polys]
        a_idx = len(self.sessions)
        self.sessions.append(manifest)
        self._geom[a_idx] = (polys, None, lane_centers(desc, mount), lever)
        self._ref[a_idx] = {}
        binding = manifest.get("calibration") if isinstance(manifest.get("calibration"), dict) else None
        cal_id = (binding or {}).get("calibration_id")
        cal = self.cal_by_id.get(cal_id) if cal_id else None
        why = ""
        if binding is None:
            why = "no calibration binding record in the attachment manifest"
        elif cal is None:
            why = f"calibration {cal_id!r} not available to processing"
        elif binding.get("sha256") not in (None, cal.sha256):
            why = "calibration content differs from the bound record (sha256)"
        elif not (binding.get("identity_match") is True or binding.get("demonstration") is True):
            why = "calibration identity not verified against the head (serial, electronics revision, firmware, setup_id)"
        self.att.append({"calibration": None if why else cal, "calibration_id": cal_id, "binding": binding,
                         "refused": why or None, "standoff": self._standoff(desc)})
        return a_idx

    @staticmethod
    def _standoff(desc):
        q = desc.get("qualified_standoff_m")
        if q is not None:
            return {"mm": 1000.0 * float(q), "basis": "qualified (descriptor qualified_standoff_m)"}
        n = desc.get("nominal_window_standoff_m")
        if n is not None:
            return {"mm": 1000.0 * float(n), "basis": "nominal design value (descriptor nominal_window_standoff_m), NOT measured"}
        return {"mm": None, "basis": "unknown"}

    def a_index(self, attachment: str) -> int:
        for i in range(len(self.sessions) - 1, -1, -1):
            if self.sessions[i]["attachment_session_id"] == attachment:
                return i
        raise KeyError(attachment)

    def cal_of(self, a_idx):
        return self.att[a_idx]["calibration"] if a_idx < len(self.att) else None

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

    def add_diag(self, ev: dict):
        """DIAG record of one gate (head ICD addendum): engineering members kept per (attachment, sequence)."""
        body = ev.get("body") or {}
        seq = body.get("sequence")
        if type(seq) is not int or not isinstance(body.get("lanes"), list):
            return
        a_idx = self.a_index(ev["attachment"])
        self.diag[(a_idx, seq)] = {
            "alpha_short": [l.get("alpha_short") for l in body["lanes"]],
            "alpha_idle_clears": [l.get("alpha_idle_clears") for l in body["lanes"]],
            "imon_na": [l.get("imon_na") for l in body["lanes"]],
            "heater_transition": (body.get("heater") or {}).get("transition"),
            "dac_writes": (body.get("bias") or {}).get("dac_writes"), "bumper_zones": body.get("bumper_zones"),
            "cal": body.get("cal")}
        del_old = len(self.diag) - 20000
        for k in list(self.diag)[:max(0, del_old)]:
            del self.diag[k]

    def add_gatestat(self, ev: dict):
        """GATESTAT entry of one gate (head firmware 0.6.0): joined by (attachment, sequence)."""
        g = ev.get("gate") or {}
        if type(g.get("seq")) is not int:
            return
        self.gatestat[(self.a_index(ev["attachment"]), g["seq"])] = g
        self._version += 1

    def add_gap(self, gap: dict):
        self.gaps.append(gap)

    def add_blocked_region(self, rect, reason="BLOCKED", t_us=None):
        ix0, ix1, iy0, iy1 = self._rect_idx(rect)
        self.blocked[iy0:iy1, ix0:ix1] = True
        self.blocked_regions.append({"rect": list(rect), "reason": reason, "t_us": t_us})
        self._version += 1

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
    @staticmethod
    def _ref_valid(lane):
        """The lane's reference is usable for U_null unless the gate has a global flag or the reference chain itself is
        null / flagged (a floor-only fault keeps the reference: review m11, ICD section 6)."""
        if lane["ref"] is None:
            return False
        for r in lane["reasons"]:
            if r.startswith("HEAD_FLAG") or r in ("LANE_FLAG:REFERENCE_FAULT", "LANE_FLAG:DISCRIMINATOR_FAULT",
                                                  "NULL:photon_ref", "UNSYNCED", "HOLDOVER", "BOUND"):
                return False
        return True

    def _credited_erosion(self, a_idx, lane, poses):
        lever = self._geom[a_idx][3][lane]
        return max(2.0 * math.sqrt(max(p["sxx"], p["syy"], 0.0) + lever * lever * max(p["syaw"], 0.0)) for p in poses)

    def _swept(self, poly_base, poses):
        """Swept polygon (convex hull of the polygon at the start, middle and end poses)."""
        pts = np.concatenate([transform((p["x"], p["y"], p["yaw"]), poly_base) for p in (poses[0], poses[len(poses) // 2], poses[-1])])
        return convex_hull(pts)

    def _process(self, gate):
        self.stats["gates"] += 1
        self._version += 1
        a_idx = self.a_index(gate["attachment"])
        seq = gate["sequence"]
        log = {"attachment": gate["attachment"], "sequence": seq, "t0_us": gate["t0_us"], "t1_us": gate["t1_us"],
               "bound_us": gate["bound_us"], "stage": None, "pose": None, "lanes": [], "erosion_m": None, "speed_mps": None,
               "marks": list(gate.get("marks") or []), "head_c": gate["thermal"].get("head_c"),
               "heater": gate["thermal"].get("heater")}
        self.gate_log.append(log)
        self._ref[a_idx][seq] = [(lane["ref"][0], lane["ref"][1] * 1e-6) if self._ref_valid(lane) else None
                                 for lane in sorted(gate["lanes"], key=lambda l: l["id"])]
        common = []
        poses = None
        cal = self.cal_of(a_idx)
        if cal is None:
            common.append("NO_CALIBRATION")
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
                dt = (gate["t1_us"] - gate["t0_us"]) * 1e-6
                speed = math.hypot(poses[-1]["x"] - poses[0]["x"], poses[-1]["y"] - poses[0]["y"]) / dt if dt > 0 else 0.0
                log["speed_mps"] = speed
                self._gate_t[(a_idx, seq)] = (gate["t0_us"], gate["t1_us"], speed)
                if not all(p["credit"] for p in poses):
                    common.append("POSE_UNCERTAIN")
            except PoseUnavailable as err:
                common.append("NO_POSE:" + err.reason)
                poses = None
        if (a_idx, seq) not in self._gate_t and gate["t0_us"] is not None:
            self._gate_t[(a_idx, seq)] = (gate["t0_us"], gate["t1_us"], None)
        polys = self._geom[a_idx][0]
        stage = log["stage"]
        erosions = []
        for lane in gate["lanes"]:
            n = lane["id"]
            reasons = list(lane["reasons"]) + common
            erosion = None
            if poses is not None and not reasons:
                erosion = self._credited_erosion(a_idx, n, poses)
                if erosion > self.cfg.position_allowance_m + 1e-12:
                    reasons.append("POSE_UNCERTAIN:2sigma>allowance")
            eroded = erode_convex(polys[n], erosion) if erosion is not None and not reasons else None
            ok = not reasons and eroded is not None
            erosions.append(erosion)
            log["lanes"].append({"id": n, "credited": bool(ok) and stage in CREDIT_STAGES, "reasons": reasons,
                                 "erosion_m": erosion})
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
                args = (a_idx, seq, n, lane, eroded, poses, stage, gate["thermal"]["head_c"], polys[n], erosion)
                if tag in self._station_result:
                    self._apply_station_credit(args, self._station_result[tag])
                else:
                    self._station_pending.setdefault(tag, []).append(args)
            elif ok and stage in CREDIT_STAGES:
                self.stats["lane_gates_credited"] += 1
                self._credit(a_idx, seq, n, lane, eroded, poses, stage, gate["thermal"]["head_c"], erosion)
            else:
                self.stats["lane_gates_rejected"] += 1
                if poses is not None and stage in CREDIT_STAGES:
                    self._reject_paint(a_idx, seq, n, polys[n], poses, reasons)
        ers = [e for e in erosions if e is not None]
        log["erosion_m"] = max(ers) if ers else None

    def _reject_paint(self, a_idx, seq, n, poly_base, poses, reasons):
        """Visited with invalid data: full (uneroded) swept footprint painted INVALID_DATA; the cells it covers count a
        gate excluded for a fault (not ACCEPTABLE); a rate saturation is kept for the ALARM rule (section 6)."""
        hull = self._swept(poly_base, poses)
        mask, ix0, iy0 = self._raster(hull, False)
        self._paint(self.seen_invalid, mask, ix0, iy0, True)
        fault = [r for r in reasons if r.startswith(("HEAD_FLAG", "LANE_FLAG", "NULL:"))]
        cells = self._cells_of(hull, min_w=0.0)
        if fault:
            for cell in cells:
                self.cell_fault[cell] = self.cell_fault.get(cell, 0) + 1
        if "LANE_FLAG:SATURATED" in reasons:
            self.saturated[(a_idx, seq, n)] = {"cells": sorted(cells), "poly": hull.round(4).tolist()}
            for cell in cells:
                self.dirty.add(cell)

    def _paint_gaps(self):
        """Skipped sequence numbers are missing gates (head 0.6.0): the floor swept while they were acquired (host time from
        the end of the gate before the hole to the start of the gate after it) is painted ACQUISITION_GAP, never credited
        (review m7).  Recomputed from the complete sequence record, so it does not depend on the order of arrival."""
        if getattr(self, "_gaps_version", None) == self._version:
            return
        self.gap_seen[:] = False
        holes = []
        for a_idx, ref in self._ref.items():
            seqs = sorted(q for q in ref if (a_idx, q) in self._gate_t)
            polys = self._geom[a_idx][0]
            for q0, q1 in zip(seqs, seqs[1:]):
                if q1 - q0 <= 1:
                    continue
                t_a, t_b = self._gate_t[(a_idx, q0)][1], self._gate_t[(a_idx, q1)][0]
                holes.append({"attachment": self.sessions[a_idx]["attachment_session_id"], "first_missing": q0 + 1,
                              "last_missing": q1 - 1, "t0_us": t_a, "t1_us": t_b})
                t = t_a
                while t < t_b:
                    t_end = min(t + 100_000, t_b)
                    try:
                        poses = self.traj.interval(t, t_end)
                    except PoseUnavailable:
                        t = t_end
                        continue
                    for n in range(len(polys)):
                        mask, ix0, iy0 = self._raster(self._swept(polys[n], poses), False)
                        self._paint(self.gap_seen, mask, ix0, iy0, True)
                    t = t_end
        self.missing_gates = holes
        self._gaps_version = self._version

    def _apply_station_credit(self, args, valid):
        if valid:
            self.stats["lane_gates_credited"] += 1
            self._credit(*args[:8], args[9])
        else:
            self.stats["lane_gates_rejected"] += 1
            self._reject_paint(args[0], args[1], args[2], args[8], args[5], ["STATION_INVALID"])

    def _finish_station(self, mark):
        tag = mark["station_end"]
        valid = bool(mark.get("valid"))
        self._station_result[tag] = valid
        self.stations.append({"station": tag, "valid": valid, "reason": mark.get("reason"), "t_us": mark.get("t_us"),
                              "pose": mark.get("pose")})
        for args in self._station_pending.pop(tag, []):
            self._apply_station_credit(args, valid)
        self._version += 1

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

    def _cells_of(self, hull, min_w=None):
        """{(cy, cx): exact area fraction of the hull inside the cell} for cells of the grid."""
        area = rect_clip_area(hull, -1e9, 1e9, -1e9, 1e9)
        if area <= 0:
            return {}
        c = self.cfg.cell_m
        lo, hi = hull.min(axis=0), hull.max(axis=0)
        out = {}
        for cy in range(max(0, int((lo[1] - self.y0) // c)), min(self.ncy, int((hi[1] - self.y0) // c) + 1)):
            for cx in range(max(0, int((lo[0] - self.x0) // c)), min(self.ncx, int((hi[0] - self.x0) // c) + 1)):
                x0, y0 = self.x0 + cx * c, self.y0 + cy * c
                f = rect_clip_area(hull, x0, x0 + c, y0, y0 + c) / area
                if f > (min_w if min_w is not None else 0.0):
                    out[(cy, cx)] = f
        return out

    def _credit(self, a_idx, seq, n, lane, eroded, poses, stage, head_c, erosion):
        """MODEL.md rev 5 section 6 footprint weights (see FOOTPRINT_MODEL)."""
        tf_b = lane["beta"][1] * 1e-6
        hull = self._swept(eroded, poses)
        mask, ix0, iy0 = self._raster(hull, True)
        c = self._clip(mask, ix0, iy0)
        if c is not None:
            m, x, y = c
            m = m & ~self.excluded[y:y + m.shape[0], x:x + m.shape[1]]
            self.exposure[y:y + m.shape[0], x:x + m.shape[1]][m] += tf_b
        self.member_erosion[(a_idx, seq, n)] = erosion
        for (cy, cx), f in sorted(self._cells_of(hull).items()):
            if f < est.MIN_LANE_GATE_WEIGHT - 0.5 * est.WEIGHT_STEP:
                continue
            w = round(round(f / est.WEIGHT_STEP) * est.WEIGHT_STEP, 10)    # nearest 0.05
            if w < est.MIN_LANE_GATE_WEIGHT - 1e-12:                          # MODEL 5 (R5): below 0.10 excluded
                continue
            self.members.setdefault((cy, cx), []).append((a_idx, seq, n, w))
            self.cell_stage.setdefault((cy, cx), set()).add(stage)
            if head_c is not None:
                t = self.cell_temp.setdefault((cy, cx), [0.0, 0.0])
                t[0] += head_c * w
                t[1] += w
            self.dirty.add((cy, cx))

    # ----------------------------------------------------------------- U_null
    def _series(self, a_idx):
        ref = self._ref[a_idx]
        key = (a_idx, len(ref))
        s = self._series_cache.get(a_idx)
        if s is None or s[0] != key:
            geo = {q: g[:2] for (a, q), g in self._gate_geo.items() if a == a_idx}
            s = (key, unull.Series.build(ref, geo))
            self._series_cache[a_idx] = s
        return s[1]

    @staticmethod
    def _u0_method(rec):
        if rec.get("status") == "UNAVAILABLE" or rec.get("U0") is None:
            return "unavailable"
        w = rec["windows"][rec["selected"]]
        side = "two-sided" if rec.get("two_sided") else "one-sided"
        return f"{rec['source']}:{side}:N={w['n']:.0f}/{w['t_s']:.1f}s"

    # -------------------------------------------------------------- decisions
    def _units(self, cell, channel, alpha_min):
        """LaneGates per (attachment, lane) of a cell, each with its rev-5 U_null record."""
        members = sorted(self.members.get(cell, []))
        temp = self.cell_temp.get(cell)
        head_c = temp[0] / temp[1] if temp and temp[1] else None
        goal = self.profile["detection_goal_Bq_cm2"]
        by_unit, dwell = {}, {}
        for a, q, ln, w in members:
            if (a, q, ln) in self._gate_counts and self.cal_of(a) is not None:
                by_unit.setdefault((a, ln), []).append((q, w))
                lo, hi = dwell.get(a, (q, q))
                dwell[a] = (min(lo, q), max(hi, q))
        units = []
        for (a, ln), rows in sorted(by_unit.items()):
            ch = 0 if channel == "beta" else 2
            cnt = [self._gate_counts[(a, q, ln)] for q, _w in rows]
            if any(c[ch] is None for c in cnt):
                rows_cnt = [(r, c) for r, c in zip(rows, cnt) if c[ch] is not None]
                if not rows_cnt:
                    continue
                rows, cnt = [r for r, _ in rows_cnt], [c for _, c in rows_cnt]
            w = np.array([r[1] for r in rows])
            rec = unull.u_null(self._series(a), ln, dwell[a], alpha_min)
            cal_a = self.cal_of(a)
            c = cal_a.cal(ln, channel)
            ok, why = True, ""
            if rec.get("U0") is not None:
                speeds = [self._gate_t.get((a, q), (None, None, None))[2] for q, _w in rows]
                ok, why = cal_a.check_envelope(ln, channel, rec["U0"], head_c, goal=goal, alpha=self.params["alpha_scan"],
                                               beta=self.params["beta"], speed_mps=max([s for s in speeds if s is not None], default=None),
                                               speed_tol=self.cfg.speed_tolerance_mps, standoff_mm=self.att[a]["standoff"]["mm"])
            units.append(est.LaneGates(ln, w, [x[1] for x in cnt], [x[ch] for x in cnt], [x[4] for x in cnt], [x[3] for x in cnt],
                                       rec.get("U0"), self._u0_method(rec), c, ok, why,
                                       u0_window_s=(rec["windows"][rec["selected"]]["t_s"] if rec.get("U0") is not None else None),
                                       u0_window_counts=(rec["windows"][rec["selected"]]["n"] if rec.get("U0") is not None else None),
                                       N_post=rec.get("N_post"), T_post=rec.get("T_post"), u0_rec=rec,
                                       unit=f"L{ln}" if a == 0 else f"A{a}:L{ln}",
                                       keys=[(self.sessions[a]["attachment_session_id"], q, ln, wq) for q, wq in rows]))
        return units

    def _decide(self, cell, channel, alpha, decider):
        members = self.members.get(cell, [])
        m_cand = max(1, len({(a, ln) for a, _q, ln, _w in members}))
        alpha_min = (1.0 - est.ALPHA_SPLIT_COMBINED) * alpha / m_cand
        units = self._units(cell, channel, alpha_min)
        if not units and members:
            return est.Decision(alpha=alpha, beta=self.params["beta"], status="NO_CALIBRATION", status_text=NO_CALIBRATION)
        d = est.combine(units, alpha, self.params["beta"], decider=decider)
        d.unit_records = units
        d.t_data_us = self._data_time(cell, units)
        return d

    def _data_time(self, cell, units):
        """Host time at which the data of this decision were complete: last member gate or last reference gate used."""
        t = []
        for a, q, _ln, _w in self.members.get(cell, []):
            g = self._gate_t.get((a, q))
            if g:
                t.append(g[1])
        for g in units:
            rec = g.u0_rec or {}
            a = 0 if ":" not in g.unit else int(g.unit[1:g.unit.index(":")])
            for w in rec.get("windows") or []:
                gg = self._gate_t.get((a, w["seq_hi"]))
                if gg:
                    t.append(gg[1])
        return max(t) if t else None

    def cell_coverage(self, cy, cx) -> float:
        s = self.sub_per_cell
        sl = (slice(cy * s, (cy + 1) * s), slice(cx * s, (cx + 1) * s))
        target = ~self.excluded[sl]
        n = int(target.sum())
        return float(((self.exposure[sl] > 0) & target).sum()) / n if n else 0.0

    def evaluate(self, channels=None) -> list:
        """PROVISIONAL evaluation of the dirty cells on the reference data received so far; returns new/changed flags.
        Never the recorded result (see finalize)."""
        channels = channels or [self._decision_channel()]
        changed = []
        for cell in sorted(self.dirty):
            for ch in channels:
                if cell not in self.members:
                    continue
                d = self._decide(cell, ch, self.params["alpha_scan"], self.decider)
                d.provisional = True
                self.provisional[ch][cell] = d
                self.decisions[ch][cell] = d
                if ch == self._decision_channel():
                    if d.detected and cell not in self.first_provisional_alarm:
                        self.first_provisional_alarm[cell] = {"t_data_us": d.t_data_us, "D": d.D, "D_star": d.D_star,
                                                              "flagged_by": list(d.flagged_by)}
                    flag = self._update_flag(cell, ch, d, provisional=True)
                    if flag is not None:
                        changed.append(flag)
        if self._decision_channel() in channels:
            changed += self._saturation_flags(provisional=True)
        self.dirty.clear()
        return changed

    def finalize(self):
        """RECORDED evaluation (MODEL.md rev 5 section 3): once per cell from the complete record, independent of the
        order of arrival and of the live schedule (members sorted, a fresh evaluator, exact inputs).  Idempotent while
        no new data arrive; flags reconciled with the provisional alarms."""
        if self._recorded_version == self._version:
            return
        self.evaluate()
        decider = est.Decider()
        ch0 = self._decision_channel()
        self.recorded = {ch: {} for ch in CHANNELS}
        for cell in sorted(self.members):
            for ch in CHANNELS:
                d = self._decide(cell, ch, self.params["alpha_scan"], decider)
                d.provisional = False
                self.recorded[ch][cell] = d
        self.decisions = {ch: dict(self.recorded[ch]) for ch in CHANNELS}
        self.recorded_decider = decider
        self._reconcile_flags(ch0)
        self._recorded_version = self._version

    def _reconcile_flags(self, ch):
        rec = self.recorded[ch]
        for f in self.flags:
            f.setdefault("provisional_D", f.get("D"))
        alarm_cells = sorted(c for c, d in rec.items() if self._classify(d) is not None)
        for cell in alarm_cells:
            if cell not in self._flag_of_cell:
                flag = self._update_flag(cell, ch, rec[cell], provisional=False)
                if flag is not None and flag.get("origin") == "recorded":
                    flag["recorded_note"] = "alarm found at final evaluation"
        for f in self.flags:
            if f["kind"] == "RATE_SATURATION":
                f["recorded"] = "recorded alarm (rate above counting range)"
                continue
            hit = [tuple(c) for c in f["cells"] if self._classify(rec.get(tuple(c))) is not None]
            if hit:
                f["recorded"] = "recorded alarm" if f.get("origin") != "recorded" else "alarm found at final evaluation"
                self._locate_flag(f, ch)
            else:
                f["recorded"] = "provisional alarm not confirmed"
        self.revisit = [{"flag": f["id"], "x_m": f.get("x_m"), "y_m": f.get("y_m"), "cells": f["cells"],
                         "reason": "alarm found at final evaluation"} for f in self.flags if f.get("origin") == "recorded"]
        for f in self._saturation_flags(provisional=False):
            pass

    def _decision_channel(self):
        cls = self.profile["decision_class"]
        return next(ch for ch, c in CLASS_OF_CHANNEL.items() if c == cls)

    def sensitivity_ok(self, d) -> bool:
        """MODEL 3: D# <= the goal AND calibration envelope valid."""
        return bool(d is not None and d.D_hash is not None and d.envelope_ok
                    and d.D_hash <= self.profile["detection_goal_Bq_cm2"])

    # ------------------------------------------------------------ cell status
    def _rate_alarm_cells(self):
        if getattr(self, "_rate_version", None) != self._version:
            self._rate_cache = self._rate_alarm_cells_compute()
            self._rate_version = self._version
        return self._rate_cache

    def _rate_alarm_cells_compute(self):
        """Cells covered by a lane-gate whose floor chain is saturated BY RATE (MODEL.md rev 5 section 6): GATESTAT sc bit 2
        (floor live < 50 %) without forced clears (ff = 0, sc bit 1 clear).  Without the head's per-gate statistics the
        cause is unknown and the saturation is treated as a possible rate alarm (conservative).  Forced clears = detector
        fault: the gate stays removed (INVALID_DATA), no alarm."""
        out = {}
        for (a, q, ln), rec in self.saturated.items():
            gs = self.gatestat.get((a, q))
            if gs is None:
                cause = "saturated - cause unknown (no per-gate statistics)"
            else:
                sc = (gs.get("sc") or [0] * 4)[ln]
                ff = (gs.get("ff") or [0] * 4)[ln]
                if ff or (sc & 1):
                    continue
                if not (sc & 2):
                    continue
                cause = f"floor live fraction {((gs.get('lf') or [None] * 4)[ln])} per mille, no forced clears"
            for cell in rec["cells"]:
                out.setdefault(tuple(cell), []).append({"attachment": self.sessions[a]["attachment_session_id"], "sequence": q,
                                                        "lane": ln, "cause": cause})
        return out

    def cell_status(self, cell, d=None):
        """(status, reason, flag state) of one cell (MODEL.md rev 5 section 6)."""
        ch = self._decision_channel()
        d = d if d is not None else self.decisions[ch].get(cell)
        flag = self._flag_of_cell.get(cell)
        fstate = flag["id"] if flag else ""
        rate = self._rate_alarm_cells().get(cell)
        if (d is not None and d.detected) or rate:
            why = []
            if d is not None and d.detected:
                why.append("flagged by " + "+".join(d.flagged_by))
            if rate:
                why.append(RATE_ALARM)
            return "ALARM", "; ".join(why), fstate
        if not self.members.get(cell):
            return "INCOMPLETE COVERAGE", "no credited gate", fstate
        if d is None or d.status in ("NO_DECISION_REF", "NO_DECISION_EVAL", "NO_CALIBRATION", "NO_DATA") or d.D is None:
            return "NO DECISION", (d.status_text if d is not None else "not evaluated"), fstate
        cov = self.cell_coverage(*cell)
        if cov < self.min_cell_coverage():
            return "INCOMPLETE COVERAGE", f"coverage {cov:.2f} < {self.min_cell_coverage():g}", fstate
        if self.cell_fault.get(cell):
            return "INCOMPLETE COVERAGE", f"{self.cell_fault[cell]} lane-gate(s) over the cell excluded for a fault", fstate
        if getattr(d, "gradient_lanes", None):
            return "SENSITIVITY INSUFFICIENT", "reference gradient (" + ",".join(d.gradient_lanes) + ")", fstate
        if not d.envelope_ok:
            return "SENSITIVITY INSUFFICIENT", d.envelope_reason or "calibration validity envelope", fstate
        if d.D_hash is None or not math.isfinite(d.D_hash) or d.D_hash > self.profile["detection_goal_Bq_cm2"]:
            return "SENSITIVITY INSUFFICIENT", "D# above the detection goal", fstate
        return "ACCEPTABLE", "", fstate

    # ------------------------------------------------------------------ flags
    def _classify(self, d):
        return classify_cell(d, self.profile["investigation_level_Bq_cm2"], self.params["review_queue_policy"])

    def _new_flag(self, kind, channel, origin):
        flag = {"n": len(self.flags) + 1, "id": f"HS-{len(self.flags) + 1:04d}", "kind": kind,
                "class": CLASS_OF_CHANNEL[channel], "cells": [], "status": "OPEN", "origin": origin,
                "observations": [], "visits": []}
        self.flags.append(flag)
        return flag

    def _update_flag(self, cell, channel, d, provisional=True):
        """Never suppressed by coverage (MODEL.md rev 5 section 6; review M1): the coverage is stated in the flag."""
        cy, cx = cell
        kind = self._classify(d)
        if kind is None:
            return None
        flag = self._flag_of_cell.get((cy, cx))
        if flag is None:
            for dy in (-1, 0, 1):               # join an adjacent flag; never merge existing flags
                for dx in (-1, 0, 1):
                    other = self._flag_of_cell.get((cy + dy, cx + dx))
                    if other is not None and other["kind"] != "RATE_SATURATION" and (flag is None or other["n"] < flag["n"]):
                        flag = other
            if flag is None:
                flag = self._new_flag(kind, channel, "provisional" if provisional else "recorded")
            flag["cells"].append([cy, cx])
            self._flag_of_cell[(cy, cx)] = flag
        if FLAG_RANK[kind] > FLAG_RANK[flag["kind"]]:
            flag["kind"] = kind
        self._locate_flag(flag, channel)
        return flag

    def _saturation_flags(self, provisional=True):
        """RATE_SATURATION flags (one per connected group of cells), queued regardless of the review-queue policy."""
        out = []
        rate = self._rate_alarm_cells()
        for cell in sorted(rate):
            if cell in self._flag_of_cell and self._flag_of_cell[cell]["kind"] == "RATE_SATURATION":
                continue
            flag = None
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    o = self._flag_of_cell.get((cell[0] + dy, cell[1] + dx))
                    if o is not None and o["kind"] == "RATE_SATURATION":
                        flag = o
            if flag is None:
                flag = self._new_flag("RATE_SATURATION", self._decision_channel(), "provisional" if provisional else "recorded")
            flag["cells"].append(list(cell))
            self._flag_of_cell.setdefault(cell, flag)
            src = rate[cell][0]
            a = self.a_index(src["attachment"])
            g = self._gate_geo.get((a, src["sequence"]))
            x, y = self.cell_center(*cell) if g is None else tuple(transform(g, [self.lane_center_base(a, src["lane"])])[0])
            half_w = self.cfg.width_m / 2
            wall = self.cfg.wall_names[0] if y >= 0 else self.cfg.wall_names[1]
            flag.update({"peak_cell": list(cell), "D": None, "u_stat": None, "u_total": None, "D_star": None, "D_hash": None,
                         "status": RATE_ALARM, "x_m": float(x), "y_m": float(y), "heading_rad": g[2] if g else 0.0,
                         "source_lane": src["lane"], "footprint": self.saturated[(a, src["sequence"], src["lane"])]["poly"],
                         "saturation": rate[cell], "position_uncertainty_m": self.cfg.position_allowance_m,
                         "location": {"distance_from_door_m": round(x, 3), "wall": wall, "distance_from_wall_m": round(half_w - abs(y), 3),
                                      "text": f"{x:.2f} m from the {self.cfg.door_name}, {half_w - abs(y):.2f} m from the {wall}"},
                         "coverage_fraction": self.cell_coverage(*cell), "recommendation": self.recommend(cell, self._decision_channel()),
                         "attachment": src["attachment"], "stage": sorted(self.cell_stage.get(cell, set()))})
            out.append(flag)
        return out

    def _locate_flag(self, flag, channel):
        """Peak cell, source lane, saved footprint, named location, contributing gates."""
        dec = self.decisions[channel]
        cells = [tuple(c) for c in flag["cells"] if tuple(c) in dec and dec[tuple(c)].D is not None]
        if not cells:
            return
        peak = max(cells, key=lambda c: dec[c].D)
        d = dec[peak]
        excess = {}
        contributing = []
        for cell in cells:
            U0 = {(0 if ":" not in ln.get("unit", "L") else int(ln["unit"][1:ln["unit"].index(":")]), ln["lane"]): ln["U0"]
                  for ln in dec[cell].lanes}
            for a_idx, seq, lane, w in self.members.get(cell, []):
                counts = self._gate_counts.get((a_idx, seq, lane))
                geo = self._gate_geo.get((a_idx, seq))
                cal_a = self.cal_of(a_idx)
                if counts is None or geo is None or (a_idx, lane) not in U0 or cal_a is None:
                    continue
                cal = cal_a.cal(lane, channel)
                n_f = counts[0] if channel == "beta" else counts[2]
                e = max(0.0, n_f - (cal.k * U0[(a_idx, lane)] + cal.b) * counts[1])
                contributing.append([self.sessions[a_idx]["attachment_session_id"], seq, lane])
                if e > 0:
                    c = transform(geo, [self.lane_center_base(a_idx, lane)])[0]
                    excess.setdefault((a_idx, lane), []).append((e, c[0], c[1], geo[2], a_idx, seq))
        if excess:
            key = max(sorted(excess), key=lambda k: sum(v[0] for v in excess[k]))
            lane = key[1]
            rows = excess[key]
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
            "flagged_by": list(d.flagged_by), "status": d.status, "provisional": bool(getattr(d, "provisional", True)),
            "coverage_fraction": self.cell_coverage(*peak),
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
        """Scaler count (contract survey_methods): evaluated at alpha_recount, U_null from the other three lanes during
        the recount (MODEL.md rev 5 section 3 "Recounts")."""
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
            if g is None:
                continue
            d = est.combine([g], self.params["alpha_recount"], self.params["beta"], decider=self.decider)
            lanes_out.append({"lane": lane, **{k: getattr(d, k) for k in
                              ("D", "u_stat", "u_total", "D_star", "D_hash", "T_F", "detected", "method", "m", "alpha_lane", "status")},
                              "N_F": float(g.N_F.sum()), "N_U": float(g.N_U.sum()), "U0": g.U0, "u0_method": g.u0_method,
                              "u0": g.u0_rec, "envelope_ok": g.envelope_ok})
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
        """LaneGates of a stationary count (weights 1); U_null = the other three lanes during the count, ratio-scaled."""
        ch = 0 if channel == "beta" else 2
        a = keys[0][0]
        cal_a = self.cal_of(a)
        if cal_a is None:
            return None
        cnt = [self._gate_counts[k] for k in keys]
        w = np.ones(len(keys))
        tf = np.array([c[1] for c in cnt])
        rec = unull.recount_u_null(self._series(a), lane, [k[1] for k in keys], (1.0 - est.ALPHA_SPLIT_COMBINED) * alpha)
        ok, why = (True, "") if rec.get("U0") is None else cal_a.check_envelope(
            lane, channel, rec["U0"], None, goal=self.profile["detection_goal_Bq_cm2"], alpha=alpha, beta=self.params["beta"],
            standoff_mm=self.att[a]["standoff"]["mm"])
        sel = rec["windows"][rec["selected"]] if rec.get("U0") is not None else None
        return est.LaneGates(lane, w, tf, [c[ch] for c in cnt], [c[4] for c in cnt], [c[3] for c in cnt], rec.get("U0"),
                             self._u0_method(rec), cal_a.cal(lane, channel), ok, why,
                             u0_window_s=sel["t_s"] if sel else None, u0_window_counts=sel["n"] if sel else None,
                             N_post=rec.get("N_post"), T_post=rec.get("T_post"), u0_rec=rec)

    def live_count_state(self, obs_id, lane, t_now_us):
        """Running scaler result for the ADAPTIVE mode (D#, D, D*) from gates so far."""
        keys = [k for k in self._obs_gates.get(obs_id, []) if k[2] == lane]
        if not keys:
            return None
        g = self._count_lane(keys, lane, self._decision_channel(), self.params["alpha_recount"])
        if g is None:
            return None
        return est.combine([g], self.params["alpha_recount"], self.params["beta"], decider=self.decider)

    # ---------------------------------------------------------------- outputs
    def classify_subcells(self) -> np.ndarray:
        """uint8 raster of REASONS indices for every sub-cell of the target (from the decisions shown now: recorded once
        finalised, else provisional)."""
        self.evaluate()
        self._paint_gaps()
        s = self.sub_per_cell
        status = np.full((self.ncy, self.ncx), -1, dtype=np.int16)
        code = {"ACCEPTABLE": REASONS.index("ACCEPTABLE"), "SENSITIVITY INSUFFICIENT": REASONS.index("INSUFFICIENT_SENSITIVITY"),
                "NO DECISION": REASONS.index("NO_DECISION"), "INCOMPLETE COVERAGE": REASONS.index("INCOMPLETE_COVERAGE"),
                "ALARM": REASONS.index("ALARM")}
        cells = set(self.members) | set(self._rate_alarm_cells())
        for cell in cells:
            st = self.cell_status(cell)[0]
            status[cell] = code[st]
        st_sub = np.repeat(np.repeat(status, s, axis=0), s, axis=1)[:self.ny, :self.nx]
        out = np.zeros((self.ny, self.nx), dtype=np.uint8)                 # UNVISITED
        out[self.gap_seen] = REASONS.index("ACQUISITION_GAP")
        out[self.seen_invalid] = REASONS.index("INVALID_DATA")
        out[self.blocked] = REASONS.index("BLOCKED")
        covered = self.exposure > 0
        out[covered] = REASONS.index("INCOMPLETE_COVERAGE")
        for name in ("INSUFFICIENT_SENSITIVITY", "NO_DECISION", "INCOMPLETE_COVERAGE", "ACCEPTABLE"):
            m = covered & (st_sub == REASONS.index(name))
            out[m] = REASONS.index(name)
        out[st_sub == REASONS.index("ALARM")] = REASONS.index("ALARM")    # the whole alarm cell, whatever its coverage
        out[self.excluded] = REASONS.index("EXCLUDED")
        return out

    def coverage_summary(self) -> dict:
        cls = self.classify_subcells()
        a = self.cfg.sub_res ** 2
        target = int((~self.excluded).sum())
        areas = {name: float((cls == i).sum()) * a for i, name in enumerate(REASONS)}
        covered = float(((self.exposure > 0) & ~self.excluded).sum()) * a
        return {"target_area_m2": target * a, "areas_m2": areas,
                "valid_exposure_fraction": covered / (target * a) if target else 0.0,
                "acceptable_fraction": areas["ACCEPTABLE"] / (target * a) if target else 0.0,
                "sub_cell_m": self.cfg.sub_res, "decision_cell_m": self.cfg.cell_m,
                "position_allowance_m": self.cfg.position_allowance_m,
                "provisional": self._recorded_version != self._version}

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

    def cell_members_table(self) -> list:
        """MODEL.md rev 5 sections 6 / 8: every member lane-gate of every cell with its weight and credited erosion."""
        rows = []
        for (cy, cx) in sorted(self.members):
            for a, q, ln, w in sorted(self.members[(cy, cx)]):
                rows.append({"ix": cx, "iy": cy, "attachment": self.sessions[a]["attachment_session_id"], "sequence": q,
                             "lane": ln, "weight": w, "erosion_m": self.member_erosion.get((a, q, ln))})
        return rows

    def cells_table(self, channels=CHANNELS) -> list:
        """One row per decision cell, RECORDED results (finalize) with the provisional values beside them."""
        self.finalize()
        ch0 = self._decision_channel()
        rate = self._rate_alarm_cells()
        rows = []
        for cy in range(self.ncy):
            for cx in range(self.ncx):
                x, y = self.cell_center(cy, cx)
                st, why, fstate = self.cell_status((cy, cx))
                row = {"ix": cx, "iy": cy, "x_m": round(x, 4), "y_m": round(y, 4),
                       "status": st, "status_reason": why,
                       "coverage_fraction": round(self.cell_coverage(cy, cx), 4),
                       "stage": "+".join(sorted(self.cell_stage.get((cy, cx), []))),
                       "method": self.method["name"], "n_lane_gates": len(self.members.get((cy, cx), [])),
                       "gates_excluded_for_fault": self.cell_fault.get((cy, cx), 0),
                       "rate_saturation": "|".join(f"{r['attachment']}:{r['sequence']}:L{r['lane']}" for r in rate.get((cy, cx), [])),
                       "review_queue_policy": self.params["review_queue_policy"], "alpha_decision": self.params["alpha_scan"]}
                for ch in channels:
                    d = self.recorded[ch].get((cy, cx))
                    p = CLASS_OF_CHANNEL[ch]
                    for name in ("D", "u_stat", "u_total", "D_star", "D_hash", "T_F"):
                        v = getattr(d, name) if d is not None else None
                        row[f"{p}.{name}"] = None if v is None or not math.isfinite(v) else v
                    comp = getattr(d, "u_components", None) or {}
                    for k in ("u_cal_lane", "u_cal_common_k", "u_cal_K"):
                        row[f"{p}.{k}"] = comp.get(k) if d is not None else None
                    row[f"{p}.footprint_dilution"] = "|".join(f"{v:.3f}" for v in getattr(d, "footprint_dilution", [])) if d else ""
                    row[f"{p}.detected"] = d.detected if d else None
                    row[f"{p}.threshold_method"] = d.method if d else ""
                    row[f"{p}.u0_method"] = "|".join(d.u0_methods) if d else ""
                    row[f"{p}.decision_rule"] = d.rule if d and d.m else ""
                    row[f"{p}.decision_status"] = (d.status_text or "ok") if d and d.D is not None else (d.status_text if d else "")
                    row[f"{p}.m_lanes"] = d.m if d and d.m else None
                    row[f"{p}.c_weights"] = "|".join(f"{x:.6f}" for x in d.c) if d and d.m else ""
                    row[f"{p}.alpha_combined"] = d.alpha_comb if d and d.m else None
                    row[f"{p}.alpha_lane"] = d.alpha_lane if d and d.m else None
                    row[f"{p}.u0_windows"] = ";".join(_u0_text(l) for l in d.lanes) if d and d.m else ""
                    row[f"{p}.lane_thresholds"] = ";".join(
                        f"{l['unit']}:t*={l['D_star']:.6g}:{l['method']}" for l in d.lanes) if d and d.m else ""
                    row[f"{p}.flagged_by"] = "|".join(d.flagged_by) if d and d.m else ""
                    row[f"{p}.evaluator_check"] = ("ok" if d.check_ok else "FAILED") if d and d.m else ""
                    row[f"{p}.sensitivity_sufficient"] = bool(self.sensitivity_ok(d)) if d and d.D is not None else None
                    row[f"{p}.envelope"] = (d.envelope_reason or "ok") if d and d.D is not None else ""
                    row[f"{p}.t_recorded_us"] = getattr(d, "t_data_us", None) if d else None
                    pv = self.provisional[ch].get((cy, cx))
                    row[f"provisional.{p}.D"] = pv.D if pv is not None and ch == ch0 else None
                    row[f"provisional.{p}.D_star"] = pv.D_star if pv is not None and ch == ch0 else None
                    row[f"provisional.{p}.detected"] = pv.detected if pv is not None and ch == ch0 else None
                fa = self.first_provisional_alarm.get((cy, cx))
                rec_alarm = bool(self.recorded[ch0].get((cy, cx)) is not None and self.recorded[ch0][(cy, cx)].detected)
                row["provisional.first_alarm_t_us"] = fa["t_data_us"] if fa else None
                row["provisional.first_alarm_D"] = fa["D"] if fa else None
                row["alarm_bookkeeping"] = ("provisional alarm not confirmed" if fa and not rec_alarm else
                                            "alarm found at final evaluation" if rec_alarm and not fa else
                                            "recorded alarm (provisional alarm confirmed)" if rec_alarm else "")
                row["flag"] = fstate
                rows.append(row)
        return rows


def _u0_text(l):
    rec = l.get("u0") or {}
    if not rec or rec.get("U0") is None:
        return f"{l['unit']}:unavailable"
    ws = rec.get("windows") or []
    sub = ",".join(f"{w['side']}[{w['seq_lo']}-{w['seq_hi']}]N={w['n']:.0f}/T={w['t_s']:.3f}s/span={w.get('span_m', 0.0):.3f}m" for w in ws)
    extra = f":ratio={rec['lane_ratio']:.5f}(n={rec['ratio_counts'][0]:.0f}/{rec['ratio_counts'][1]:.0f})" if rec.get("lane_ratio") else ""
    return (f"{l['unit']}:{rec['source']}:U0={rec['U0']:.6g}/s:sel={rec['selected']}:{sub}:grad={rec.get('gradient_per_m', 0.0):.4g}/m"
            f":bias={rec.get('projected_bias', 0.0):.4g}:Nmin={rec['n_min']}:status={rec['status']}{extra}")
