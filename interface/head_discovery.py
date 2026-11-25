#!/usr/bin/env python3
"""Reference host checks for the proposed four-lane detector descriptor.

This offline example never operates a device, selects a release profile or authorizes motion.
Supply a trusted robot-side registry separately from the descriptor returned by the head.
"""
import argparse
import base64
import binascii
import hashlib
import json
import math
from uuid import UUID, uuid4
from pathlib import Path

from jsonschema import Draft202012Validator
from wire_codec import unpack_json

MAX_DESCRIPTOR_BYTES = 16384
CHUNK_BYTES = 768
SCHEMA = json.loads(Path(__file__).with_name("head_descriptor.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def assemble_descriptor(hello, replies):
    """Reconstruct one sequential response stream in the current boot session."""
    count = hello["descriptor_bytes"]
    if type(count) is not int or not 1 <= count <= MAX_DESCRIPTOR_BYTES:
        raise ValueError("descriptor byte count outside budget")
    data = bytearray()
    for chunk in replies:
        if chunk["boot_id"] != hello["boot_id"] or chunk["descriptor_id"] != hello["descriptor_id"]:
            raise ValueError("descriptor changed during transfer")
        if type(chunk["offset"]) is not int or chunk["offset"] != len(data):
            raise ValueError("missing or repeated descriptor chunk")
        try:
            block = base64.b64decode(chunk["bytes_b64"], validate=True)
        except (binascii.Error, TypeError) as err:
            raise ValueError("invalid base64 chunk") from err
        if not 1 <= len(block) <= CHUNK_BYTES or len(data) + len(block) > count:
            raise ValueError("invalid descriptor chunk size")
        data.extend(block)
    if len(data) != count or hashlib.sha256(data).hexdigest() != hello["descriptor_sha256"]:
        raise ValueError("incomplete descriptor or SHA-256 mismatch")
    return bytes(data)


def validate_geometry(desc):
    bounds = desc["envelope_m"]
    if any(lo >= hi for lo, hi in zip(bounds["min"], bounds["max"])):
        raise ValueError("invalid physical envelope")
    if abs(sum(c*c for c in desc["mount_to_window_normal"]) - 1.0) > 0.001:
        raise ValueError("invalid window normal")
    for interval in (desc["electrical"]["supply_range_V"], desc["gate_range_us"],
                     desc["qualified_standoff_m"], desc["qualified_detector_temperature_C"]):
        if interval is not None and interval[0] > interval[1]:
            raise ValueError("invalid operating interval")
    lanes = desc["segments"]
    if [s["id"] for s in lanes] != list(range(4)):
        raise ValueError("missing, duplicated or out-of-order lane")
    if any(a["center_m"][1] <= b["center_m"][1] for a, b in zip(lanes, lanes[1:])):
        raise ValueError("lane identities do not run left to right")
    for segment in lanes:
        points = segment["sensitive_polygon_m"]
        for point in [*points,segment["center_m"]]:
            if any(not math.isfinite(v) or not lo <= v <= hi for v,lo,hi in zip(point,bounds["min"],bounds["max"])):
                raise ValueError("active aperture outside physical envelope")
        # This descriptor version represents planar convex quadrilaterals in the XY projection.
        turns = []
        center_turns = []
        for n,p in enumerate(points):
            q = points[(n+1)%4]; r = points[(n+2)%4]; c = segment["center_m"]
            turns.append((q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0]))
            center_turns.append((q[0]-p[0])*(c[1]-p[1]) - (q[1]-p[1])*(c[0]-p[0]))
        if not (all(v > 0 for v in turns+center_turns) or all(v < 0 for v in turns+center_turns)):
            raise ValueError("invalid active polygon or centre")


def evaluate(hello, data, registry, mode="BENCH"):
    """Return head/calibration identity only after checks for the requested mode."""
    if mode not in ("BENCH","SURVEY"):
        raise ValueError("unknown mode")
    if "2.0" not in hello["supported_discovery"] or hello["acq_format"] != "2.0":
        raise ValueError("unsupported discovery or acquisition version")
    UUID(hello["boot_id"])
    size = len(data)
    if not 1 <= size <= MAX_DESCRIPTOR_BYTES or size != hello["descriptor_bytes"]:
        raise ValueError("invalid descriptor byte count")
    digest = hashlib.sha256(data).hexdigest()
    if digest != hello["descriptor_sha256"]:
        raise ValueError("descriptor digest mismatch")
    desc = unpack_json(data)
    error = next(VALIDATOR.iter_errors(desc), None)
    if error:
        raise ValueError(f"{error.json_path}: {error.message}")
    validate_geometry(desc)
    if (desc["serial"],desc["head_type"],desc["descriptor_id"],desc["setup_id"],desc["acq_format"]) != (
            hello["head_id"],hello["head_type"],hello["descriptor_id"],hello["setup_id"],hello["acq_format"]):
        raise ValueError("descriptor does not match advertised unit")
    capabilities = {"raw_counts","per_channel_live_time","head_temperature"}
    if not capabilities.issubset(desc["capabilities"]):
        raise ValueError("required acquisition capabilities absent")
    trusted = [r for r in registry["records"]
               if r["serial"] == desc["serial"] and r["descriptor_id"] == desc["descriptor_id"]]
    if len(trusted) != 1:
        raise ValueError("head and revision lack a unique trusted registry entry")
    entry = trusted[0]
    if (entry["descriptor_sha256"],entry["firmware"],entry["head_type"],entry["setup_id"],entry["geometry_id"]) != (
            digest,hello["firmware"],desc["head_type"],desc["setup_id"],desc["geometry_id"]):
        raise ValueError("host registry disagrees with unit, revision or content")
    if mode not in entry["authorized_uses"]:
        raise ValueError(f"head lacks local {mode} authorization")
    if mode == "SURVEY" and (desc["geometry_basis"] != "AS_BUILT" or not entry.get("calibration_id")
            or desc["qualified_standoff_m"] is None or desc["qualified_detector_temperature_C"] is None
            or desc["measured_registration_uncertainty_m"] is None or not desc["spatial_response_record_id"]
            or any(lane["reference_center_m"] is None or lane["window_to_effective_plane_m"] is None for lane in desc["segments"])):
        raise ValueError("survey requires measured geometry, qualified limits and local calibration")
    return {"serial":desc["serial"],"mode":mode,"calibration_id":entry.get("calibration_id"),
            "geometry_id":desc["geometry_id"],"descriptor_sha256":digest}


def attachment_manifest(hello, verified):
    """Create one host archive key at a successful BIND acknowledgement.

    Caller must first finish discovery, validate the descriptor via evaluate(), and match BIND's
    acknowledgement on the same uninterrupted physical connection. Persist this
    manifest before accepting count frames. No part of the UUID is transmitted.
    """
    return {"attachment_session_id": str(uuid4()), "head_id": verified["serial"],
            "boot_id": hello["boot_id"], "head_type": hello["head_type"],
            "firmware": hello["firmware"], "setup_id": hello["setup_id"],
            "descriptor_id": hello["descriptor_id"],
            "descriptor_sha256": verified["descriptor_sha256"],
            "geometry_id": verified["geometry_id"], "calibration_id": verified["calibration_id"],
            "mode": verified["mode"], "acq_format": hello["acq_format"]}


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("hello",type=Path)
    args.add_argument("descriptor",type=Path)
    args.add_argument("registry",type=Path)
    args.add_argument("--mode",choices=("BENCH","SURVEY"),default="BENCH")
    opt = args.parse_args()
    try:
        result = evaluate(unpack_json(opt.hello.read_bytes()),opt.descriptor.read_bytes(),
                          unpack_json(opt.registry.read_bytes()),opt.mode)
    except (KeyError,ValueError,TypeError,OSError) as error:
        args.exit(2, f"Head configuration unavailable: {error}\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
