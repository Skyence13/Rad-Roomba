"""Record framing shared by the head link (ICD 2.0 section 4) and the chassis
link (RR-CHS 1.0, contract.yaml `chassis_link.transport`).

One UTF-8 JSON object, TAB, eight uppercase hex characters of CRC-32
(zlib.crc32 over exactly the JSON bytes), LF.  Port of the 0.3 baseline
`interface/wire_codec.py`; `tests/test_wire.py` proves byte equality with the
baseline examples.

No ROS imports.
"""
from __future__ import annotations

import json
import re
from zlib import crc32

HEAD_MAX_BYTES = 8192      # head ICD section 4
CHASSIS_MAX_BYTES = 2048   # contract.yaml chassis_link.transport
_CRC = re.compile(rb"[0-9A-F]{8}")


class WireError(ValueError):
    """A received line is not a valid record (malformed, oversize, bad CRC...)."""


def _reject_constant(token):
    raise WireError(f"invalid JSON constant: {token}")


def _check_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise WireError(f"duplicate key: {key!r}")
        obj[key] = value
    return obj


def unpack_json(data: bytes) -> dict:
    """Strict JSON object decode: no duplicate keys, no NaN/Infinity."""
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_check_pairs,
                         parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as err:
        raise WireError(f"invalid JSON: {err}") from err
    if not isinstance(obj, dict):
        raise WireError("expected one JSON object")
    return obj


def encode(obj: dict, max_bytes: int = HEAD_MAX_BYTES) -> bytes:
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")
    line = data + b"\t" + f"{crc32(data):08X}".encode("ascii") + b"\n"
    if len(line) > max_bytes:
        raise WireError("wire line exceeds maximum")
    return line


def decode(line: bytes, max_bytes: int = HEAD_MAX_BYTES) -> dict:
    if len(line) > max_bytes or not line.endswith(b"\n"):
        raise WireError("line too long or missing LF")
    fields = line[:-1].split(b"\t")
    if len(fields) != 2 or b"\r" in fields[0] or b"\n" in fields[0]:
        raise WireError("invalid record delimiter")
    data, checksum = fields
    if not _CRC.fullmatch(checksum) or int(checksum, 16) != crc32(data):
        raise WireError("invalid CRC-32")
    return unpack_json(data)


class StreamDecoder:
    """Incremental line splitter for a half-duplex byte stream.

    `feed(data)` returns a list of `(raw_line, record_or_None, error_or_None)`.
    An unfinished or oversized record is discarded through the next LF (ICD
    section 4); the discarded bytes are still returned (truncated to the size
    limit) so the raw archive can keep them.
    """

    def __init__(self, max_bytes: int = HEAD_MAX_BYTES):
        self.max_bytes = max_bytes
        self._buf = bytearray()
        self._overflow = False

    def reset(self) -> bytes:
        """Drop any partial line (used for the quiet interval). Returns it."""
        dropped = bytes(self._buf)
        self._buf.clear()
        self._overflow = False
        return dropped

    @property
    def pending(self) -> int:
        return len(self._buf)

    def feed(self, data: bytes):
        out = []
        start = 0
        while True:
            idx = data.find(b"\n", start)
            if idx < 0:
                self._buf += data[start:]
                if len(self._buf) > self.max_bytes:
                    self._overflow = True
                    del self._buf[self.max_bytes:]
                break
            self._buf += data[start:idx + 1]
            start = idx + 1
            raw = bytes(self._buf)
            overflow = self._overflow or len(raw) > self.max_bytes
            self._buf.clear()
            self._overflow = False
            if overflow:
                out.append((raw[:self.max_bytes], None, "oversize record discarded"))
                continue
            try:
                out.append((raw, decode(raw, self.max_bytes), None))
            except WireError as err:
                out.append((raw, None, str(err)))
        return out


def make_request(version: str, tid: int, op: str, args: dict | None = None) -> dict:
    if not 0 <= tid <= 0xFFFFFFFF:
        raise WireError("transaction id outside u32")
    return {"type": "REQ", "v": version, "id": tid, "op": op, "args": args or {}}


def is_response_to(rec: dict, version: str, tid: int) -> bool:
    return (rec.get("type") == "RSP" and rec.get("v") == version
            and type(rec.get("id")) is int and rec["id"] == tid
            and isinstance(rec.get("status"), str)
            and isinstance(rec.get("body"), dict))
