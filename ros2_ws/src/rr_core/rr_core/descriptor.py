"""Head descriptor transfer, validation, trusted-registry check and attachment
manifest (head ICD section 4 "Initial handshake and host provenance").

Port of the 0.3 baseline `interface/head_discovery.py` with one host-side
extension: the registry `authorized_uses` may also list "COMMISSIONING", a
labelled supervised mode (software/Operator_Interface.md "Overview and
preflight") that accepts CONCEPT geometry and a synthetic calibration.  Every
product made in that mode carries `field_use_approved: false`.  "SURVEY" keeps
the baseline rule: measured geometry, qualified limits and a local calibration.

No ROS imports.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator

from .wire import unpack_json, WireError

MAX_DESCRIPTOR_BYTES = 16384   # ICD: descriptor format 1.0
CHUNK_BYTES = 768              # ICD: GET_DESCRIPTOR count 1..768
MODES = ("BENCH", "COMMISSIONING", "SURVEY")
REQUIRED_CAPABILITIES = {"raw_counts", "per_channel_live_time", "head_temperature"}

_SCHEMA_DIR = Path(__file__).with_name("schemas")
DESCRIPTOR_SCHEMA = json.loads((_SCHEMA_DIR / "head_descriptor.schema.json").read_text())
_VALIDATOR = Draft202012Validator(DESCRIPTOR_SCHEMA)


class DescriptorError(ValueError):
    """Head configuration unavailable; `.reason` is a stable service code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def check_hello(hello: dict) -> None:
    need = ("boot_id", "head_id", "head_type", "firmware", "supported_discovery",
            "acq_format", "descriptor_id", "descriptor_sha256", "descriptor_bytes", "setup_id")
    missing = [k for k in need if k not in hello]
    if missing:
        raise DescriptorError("HELLO_MALFORMED", f"HELLO lacks {missing}")
    if "2.0" not in hello["supported_discovery"] or hello["acq_format"] != "2.0":
        raise DescriptorError("UNSUPPORTED_VERSION", "unsupported discovery or acquisition version")
    try:
        UUID(hello["boot_id"])
    except (ValueError, TypeError, AttributeError) as err:
        raise DescriptorError("HELLO_MALFORMED", "boot_id is not a UUID") from err
    count = hello["descriptor_bytes"]
    if type(count) is not int or not 1 <= count <= MAX_DESCRIPTOR_BYTES:
        raise DescriptorError("DESCRIPTOR_SIZE", "descriptor byte count outside budget")


def decode_chunk(hello: dict, body: dict, expected_offset: int, have: int) -> bytes:
    """Validate one GET_DESCRIPTOR reply body and return its bytes."""
    if body.get("boot_id") != hello["boot_id"] or body.get("descriptor_id") != hello["descriptor_id"]:
        raise DescriptorError("DESCRIPTOR_CHANGED", "descriptor changed during transfer")
    if type(body.get("offset")) is not int or body["offset"] != expected_offset:
        raise DescriptorError("DESCRIPTOR_CHUNK", "missing or repeated descriptor chunk")
    try:
        block = base64.b64decode(body["bytes_b64"], validate=True)
    except (binascii.Error, TypeError, KeyError) as err:
        raise DescriptorError("DESCRIPTOR_CHUNK", "invalid base64 chunk") from err
    if not 1 <= len(block) <= CHUNK_BYTES or have + len(block) > hello["descriptor_bytes"]:
        raise DescriptorError("DESCRIPTOR_CHUNK", "invalid descriptor chunk size")
    return block


def assemble_descriptor(hello: dict, replies) -> bytes:
    """Reconstruct one sequential response stream (baseline API)."""
    check_hello(hello)
    data = bytearray()
    for chunk in replies:
        data.extend(decode_chunk(hello, chunk, len(data), len(data)))
    if len(data) != hello["descriptor_bytes"] or hashlib.sha256(data).hexdigest() != hello["descriptor_sha256"]:
        raise DescriptorError("DESCRIPTOR_DIGEST", "incomplete descriptor or SHA-256 mismatch")
    return bytes(data)


def validate_geometry(desc: dict) -> None:
    bounds = desc["envelope_m"]
    if any(lo >= hi for lo, hi in zip(bounds["min"], bounds["max"])):
        raise DescriptorError("GEOMETRY", "invalid physical envelope")
    if abs(sum(c * c for c in desc["mount_to_window_normal"]) - 1.0) > 0.001:
        raise DescriptorError("GEOMETRY", "invalid window normal")
    for interval in (desc["electrical"]["supply_range_V"], desc["gate_range_us"],
                     desc["qualified_standoff_m"], desc["qualified_detector_temperature_C"]):
        if interval is not None and interval[0] > interval[1]:
            raise DescriptorError("GEOMETRY", "invalid operating interval")
    lanes = desc["segments"]
    if [s["id"] for s in lanes] != list(range(4)):
        raise DescriptorError("GEOMETRY", "missing, duplicated or out-of-order lane")
    if any(a["center_m"][1] <= b["center_m"][1] for a, b in zip(lanes, lanes[1:])):
        raise DescriptorError("GEOMETRY", "lane identities do not run left to right")
    for segment in lanes:
        points = segment["sensitive_polygon_m"]
        for point in [*points, segment["center_m"]]:
            if any(not math.isfinite(v) or not lo <= v <= hi
                   for v, lo, hi in zip(point, bounds["min"], bounds["max"])):
                raise DescriptorError("GEOMETRY", "active aperture outside physical envelope")
        turns, center_turns = [], []
        c = segment["center_m"]
        for n, p in enumerate(points):
            q = points[(n + 1) % 4]
            r = points[(n + 2) % 4]
            turns.append((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))
            center_turns.append((q[0] - p[0]) * (c[1] - p[1]) - (q[1] - p[1]) * (c[0] - p[0]))
        both = turns + center_turns
        if not (all(v > 0 for v in both) or all(v < 0 for v in both)):
            raise DescriptorError("GEOMETRY", "invalid active polygon or centre")


def evaluate(hello: dict, data: bytes, registry: dict, mode: str = "BENCH") -> dict:
    """Return head/calibration identity only after every check for `mode`.

    The hash sent by the head is an integrity check; the local registry is the
    authority (ICD: "does not confer authorization").
    """
    if mode not in MODES:
        raise DescriptorError("MODE", "unknown mode")
    check_hello(hello)
    size = len(data)
    if not 1 <= size <= MAX_DESCRIPTOR_BYTES or size != hello["descriptor_bytes"]:
        raise DescriptorError("DESCRIPTOR_SIZE", "invalid descriptor byte count")
    digest = hashlib.sha256(data).hexdigest()
    if digest != hello["descriptor_sha256"]:
        raise DescriptorError("DESCRIPTOR_DIGEST", "descriptor digest mismatch")
    try:
        desc = unpack_json(data)
    except WireError as err:
        raise DescriptorError("DESCRIPTOR_FORMAT", str(err)) from err
    error = next(_VALIDATOR.iter_errors(desc), None)
    if error:
        raise DescriptorError("DESCRIPTOR_FORMAT", f"{error.json_path}: {error.message}")
    validate_geometry(desc)
    if (desc["serial"], desc["head_type"], desc["descriptor_id"], desc["setup_id"], desc["acq_format"]) != (
            hello["head_id"], hello["head_type"], hello["descriptor_id"], hello["setup_id"], hello["acq_format"]):
        raise DescriptorError("IDENTITY_MISMATCH", "descriptor does not match advertised unit")
    if not REQUIRED_CAPABILITIES.issubset(desc["capabilities"]):
        raise DescriptorError("CAPABILITY", "required acquisition capabilities absent")
    trusted = [r for r in registry["records"]
               if r["serial"] == desc["serial"] and r["descriptor_id"] == desc["descriptor_id"]]
    if len(trusted) != 1:
        raise DescriptorError("UNKNOWN_HEAD", "head and revision lack a unique trusted registry entry")
    entry = trusted[0]
    if (entry["descriptor_sha256"], entry["firmware"], entry["head_type"], entry["setup_id"], entry["geometry_id"]) != (
            digest, hello["firmware"], desc["head_type"], desc["setup_id"], desc["geometry_id"]):
        raise DescriptorError("REGISTRY_MISMATCH", "host registry disagrees with unit, revision or content")
    if mode not in entry["authorized_uses"]:
        raise DescriptorError("NOT_AUTHORIZED", f"head lacks local {mode} authorization")
    if mode == "COMMISSIONING" and not entry.get("calibration_id"):
        raise DescriptorError("NO_CALIBRATION", "commissioning mapping needs a (synthetic) calibration id")
    if mode == "SURVEY" and (
            desc["geometry_basis"] != "AS_BUILT" or not entry.get("calibration_id")
            or desc["qualified_standoff_m"] is None or desc["qualified_detector_temperature_C"] is None
            or desc["measured_registration_uncertainty_m"] is None or not desc["spatial_response_record_id"]
            or any(lane["reference_center_m"] is None or lane["window_to_effective_plane_m"] is None
                   for lane in desc["segments"])):
        raise DescriptorError("SURVEY_UNQUALIFIED",
                              "survey requires measured geometry, qualified limits and local calibration")
    return {"serial": desc["serial"], "mode": mode, "calibration_id": entry.get("calibration_id"),
            "geometry_id": desc["geometry_id"], "descriptor_sha256": digest,
            "geometry_basis": desc["geometry_basis"],
            "mount_transform": entry.get("mount_transform"), "descriptor": desc}


def attachment_manifest(hello: dict, verified: dict, attachment_session_id: str) -> dict:
    """Host archive key created at a successful BIND acknowledgement.

    Same fields as the baseline `examples/head_session.json`; the UUID is
    supplied by the caller (host-generated, never transmitted).
    """
    return {"attachment_session_id": str(UUID(attachment_session_id)), "head_id": verified["serial"],
            "boot_id": hello["boot_id"], "head_type": hello["head_type"],
            "firmware": hello["firmware"], "setup_id": hello["setup_id"],
            "descriptor_id": hello["descriptor_id"],
            "descriptor_sha256": verified["descriptor_sha256"],
            "geometry_id": verified["geometry_id"], "calibration_id": verified["calibration_id"],
            "mode": verified["mode"], "acq_format": hello["acq_format"]}


def load_registry(path) -> dict:
    registry = unpack_json(Path(path).read_bytes())
    if not isinstance(registry.get("records"), list):
        raise DescriptorError("REGISTRY", "registry lacks a records list")
    return registry
