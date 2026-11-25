"""ACQ 2.0 frame validation and per-lane instrument eligibility.

Port of the 0.3 baseline `interface/check_frames.py` (`validate_semantics`,
`examine`).  The schema is the unmodified `interface/acquisition.schema.json`
(copied into `rr_core/schemas`, byte-compared by a unit test).

No ROS imports.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

READOUTS = ("alpha", "beta_window", "photon_ref")
WIRE_INT_MAX = 9007199254740991

_SCHEMA = json.loads((Path(__file__).with_name("schemas") / "acquisition.schema.json").read_text())
Draft202012Validator.check_schema(_SCHEMA)
ACQ_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=FormatChecker())


class FrameError(ValueError):
    pass


def validate_schema(frame: dict) -> None:
    error = next(ACQ_VALIDATOR.iter_errors(frame), None)
    if error:
        raise FrameError(f"{error.json_path}: {error.message}")


def validate_semantics(frame: dict) -> None:
    clock = frame["sync"]
    clock_fields = (clock["sync_id"], clock["bound_us"], clock["age_us"])
    if clock["state"] == "UNSYNCED" and any(v is not None for v in clock_fields):
        raise FrameError("UNSYNCED requires null sync_id, bound_us and age_us")
    if clock["state"] != "UNSYNCED" and any(v is None for v in clock_fields):
        raise FrameError("LOCKED/HOLDOVER require a sync id, error bound and age")
    thermal = frame["thermal"]
    if (thermal["heater"] == "ON") != (thermal["duty_pct"] > 0):
        raise FrameError("applied heater duty conflicts with heater state")
    if thermal["heater"] == "FAULT" and "HEATER_FAULT" not in frame["flags"]:
        raise FrameError("heater fault must appear in the global flags")
    if thermal["head_c"] is None and "HEAD_TEMP_OUT_OF_RANGE" not in frame["flags"]:
        raise FrameError("a missing head temperature must invalidate the head thermal status")
    if frame["start_us"] + frame["span_us"] > WIRE_INT_MAX:
        raise FrameError("interval end exceeds wire integer limit")
    for segment in frame["segments"]:
        for channel in READOUTS:
            sample = segment[channel]
            if sample is None and not (segment["flags"] or frame["flags"]):
                raise FrameError(f"segment {segment['id']} {channel} is missing without a fault")
            if sample and sample["live_us"] > frame["span_us"]:
                raise FrameError(f"segment {segment['id']} {channel} live time exceeds frame")


def examine(frame: dict, previous: dict, sync_bound: float, session_id: str):
    """Baseline continuity/eligibility check (kept API-compatible).

    Returns (eligible lane ids, notices).  Raises on a repeated, out-of-order or
    overlapping frame within one attachment.
    """
    if not session_id:
        raise FrameError("a verified attachment session is required")
    notices = []
    if session_id in previous:
        seq, end = previous[session_id]
        if frame["sequence"] <= seq or frame["start_us"] < end:
            raise FrameError("repeated, out-of-order, or overlapping frame within one attachment")
        if frame["sequence"] > seq + 1:
            notices.append(f"sequence gap of {frame['sequence'] - seq - 1}")
        if frame["start_us"] > end:
            notices.append(f"time gap of {frame['start_us'] - end} us")
    previous[session_id] = (frame["sequence"], frame["start_us"] + frame["span_us"])
    eligible = [lane for lane, why in lane_status(frame, sync_bound) if not why]
    return eligible, notices


def lane_status(frame: dict, sync_bound: float):
    """[(lane id, [reason codes])] from the frame alone (instrument eligibility).

    Reasons: UNSYNCED / HOLDOVER / BOUND (head-reported timing), HEAD_FLAG:<f>,
    LANE_FLAG:<f>, NULL:<channel>.  An empty list means the lane is instrument-
    eligible; host-side timing and pose qualification are applied separately.
    """
    clock = frame["sync"]
    common = []
    if clock["state"] != "LOCKED":
        common.append(clock["state"])
    elif clock["bound_us"] > sync_bound:
        common.append("BOUND")
    common += [f"HEAD_FLAG:{f}" for f in frame["flags"]]
    out = []
    for seg in frame["segments"]:
        why = list(common)
        why += [f"LANE_FLAG:{f}" for f in seg["flags"]]
        why += [f"NULL:{ch}" for ch in READOUTS if seg[ch] is None]
        out.append((seg["id"], why))
    return out
