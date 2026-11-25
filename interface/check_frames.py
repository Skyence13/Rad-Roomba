#!/usr/bin/env python3
"""Validate synthetic or captured head records and report default survey eligibility.

Requires Python 3.9+ and jsonschema 4.18+. See head_icd.md for further host checks.
"""
import argparse
import json
import sys
from uuid import UUID
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).with_name("acquisition.schema.json")
LEGACY_SCHEMA = SCHEMA.with_name("acquisition.v1.schema.json")
READOUTS = ("alpha", "beta_window", "photon_ref")


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_constant(token):
    raise ValueError(f"non-finite JSON number {token!r}")


def decode(text):
    return json.loads(text, object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)


def read_records(path):
    with path.open(encoding="utf-8") as source:
        if path.suffix.lower() == ".json":
            yield path.name, decode(source.read())
        else:
            for number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                if len(line.encode("utf-8")) > 8192:
                    raise ValueError(f"{path.name}:{number}: record exceeds wire limit")
                yield f"{path.name}:{number}", decode(line)


def validate_semantics(frame):
    clock = frame["sync"]
    clock_fields = (clock["sync_id"], clock["bound_us"], clock["age_us"])
    if clock["state"] == "UNSYNCED" and any(v is not None for v in clock_fields):
        raise ValueError("UNSYNCED requires null sync_id, bound_us and age_us")
    if clock["state"] != "UNSYNCED" and any(v is None for v in clock_fields):
        raise ValueError("LOCKED/HOLDOVER require a sync id, error bound and age")
    thermal = frame["thermal"]
    if (thermal["heater"] == "ON") != (thermal["duty_pct"] > 0):
        raise ValueError("applied heater duty conflicts with heater state")
    if thermal["heater"] == "FAULT" and "HEATER_FAULT" not in frame["flags"]:
        raise ValueError("heater fault must appear in the global flags")
    if thermal["head_c"] is None and "HEAD_TEMP_OUT_OF_RANGE" not in frame["flags"]:
        raise ValueError("a missing head temperature must invalidate the head thermal status")
    if frame["start_us"] + frame["span_us"] > 9007199254740991:
        raise ValueError("interval end exceeds wire integer limit")
    for segment in frame["segments"]:
        for channel in READOUTS:
            sample = segment[channel]
            if sample is None and not (segment["flags"] or frame["flags"]):
                raise ValueError(f"segment {segment['id']} {channel} is missing without a fault")
            if sample and sample["live_us"] > frame["span_us"]:
                raise ValueError(f"segment {segment['id']} {channel} live time exceeds frame")


def examine(frame, previous, sync_bound, session_id):
    """Select intact segments; continuity notices concern the gap, not a later valid bin."""
    key = session_id
    if not key:
        raise ValueError("a verified attachment session or a legacy archive key is required")
    notices = []
    if key in previous:
        seq, end = previous[key]
        if frame["sequence"] <= seq or frame["start_us"] < end:
            raise ValueError("repeated, out-of-order, or overlapping frame within one attachment or legacy boot")
        if frame["sequence"] > seq + 1:
            notices.append(f"sequence gap of {frame['sequence'] - seq - 1}")
        if frame["start_us"] > end:
            notices.append(f"time gap of {frame['start_us'] - end} us")
    previous[key] = (frame["sequence"], frame["start_us"] + frame["span_us"])
    clock = frame["sync"]
    valid_time = clock["state"] == "LOCKED" and clock["bound_us"] <= sync_bound
    eligible = [s["id"] for s in frame["segments"]
                if valid_time and not frame["flags"] and not s["flags"]
                and all(s[ch] is not None for ch in READOUTS)]
    return eligible, notices


class AttachedReader:
    """Offline host-side reader for one verified and bound attachment.

    Transport supplies the actual latched presence/link events and its one
    outstanding transaction ID. A new handshake creates a new reader.
    """
    def __init__(self, manifest):
        self.session_id = str(UUID(manifest["attachment_session_id"]))
        if manifest["acq_format"] != "2.0":
            raise ValueError("attachment does not use ACQ 2.0")
        self.history = {}
        self.active = True

    def invalidate(self):
        self.active = False

    def capture_read(self, reply, expected_id, validator, sync_bound):
        if not self.active:
            raise ValueError("attachment closed; handshake required")
        if (reply.get("type") != "RSP" or reply.get("v") != "2.0"
                or type(reply.get("id")) is not int or reply["id"] != expected_id):
            raise ValueError("response does not match outstanding READ")
        if reply.get("status") == "UNBOUND":
            self.invalidate()
            raise ValueError("head lost binding; handshake required")
        if reply.get("status") != "OK":
            raise ValueError(f"READ returned {reply.get('status')}")
        frame = reply["body"]
        error = next(validator.iter_errors(frame), None)
        if error:
            raise ValueError(f"{error.json_path}: {error.message}")
        validate_semantics(frame)
        eligible, notices = examine(frame, self.history, sync_bound, self.session_id)
        return {"attachment_session_id": self.session_id, "frame": frame}, eligible, notices


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("paths", type=Path, nargs="+", help="one frame per .json, or NDJSON stream")
    args.add_argument("--require-usable", action="store_true",
                      help="return 2 if any segment is instrument-ineligible, or a gap occurs")
    args.add_argument("--sync-bound-us", type=int, default=10000, help="trial maximum time error")
    source = args.add_mutually_exclusive_group(required=True)
    source.add_argument("--session", type=Path, help="host manifest for this contiguous ACQ 2.0 capture")
    source.add_argument("--legacy-v1", action="store_true", help="read archival self-identifying ACQ 1.0 records")
    opt = args.parse_args()
    if opt.sync_bound_us < 0:
        args.error("the sync bound must be nonnegative")
    try:
        session_id = None if opt.legacy_v1 else AttachedReader(decode(opt.session.read_text(encoding="utf-8"))).session_id
    except (OSError, KeyError, ValueError) as error:
        args.error(f"invalid attachment manifest: {error}")
    schema = json.loads((LEGACY_SCHEMA if opt.legacy_v1 else SCHEMA).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    previous = {}
    count = 0
    degraded = False
    for path in opt.paths:
        label = path.name
        try:
            for label, frame in read_records(path):
                error = next(validator.iter_errors(frame), None)
                if error:
                    raise ValueError(f"{error.json_path}: {error.message}")
                validate_semantics(frame)
                key = (frame["head_id"], frame["boot_id"]) if opt.legacy_v1 else session_id
                eligible, notices = examine(frame, previous, opt.sync_bound_us, key)
                degraded |= len(eligible) != 4 or bool(notices)
                print(f"{label} seq={frame['sequence']} eligible_segments={eligible}"
                      f" notices={','.join(notices) or 'none'}")
                count += 1
        except (ValueError, OSError) as exc:
            print(f"{label}: {exc}", file=sys.stderr)
            return 1
    if count == 0:
        print("No records found.", file=sys.stderr)
        return 1
    return 2 if opt.require_usable and degraded else 0


if __name__ == "__main__":
    sys.exit(main())
