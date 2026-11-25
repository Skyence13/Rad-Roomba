#!/usr/bin/env python3
"""Encode compact UTF-8 JSON records on stdin or decode and CRC-check RS-485 lines."""
import argparse
import json
import re
import sys
from zlib import crc32

MAX_BYTES = 8192
CRC = re.compile(b"[0-9A-F]{8}")


def reject_constant(token):
    raise ValueError(f"invalid JSON constant: {token}")


def check_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key: {key!r}")
        obj[key] = value
    return obj


def unpack_json(data):
    obj = json.loads(data.decode("utf-8"), object_pairs_hook=check_pairs,
                     parse_constant=reject_constant)
    if not isinstance(obj, dict):
        raise ValueError("expected one JSON object")
    return obj


def encode(obj):
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")
    line = data + b"\t" + f"{crc32(data):08X}".encode("ascii") + b"\n"
    if len(line) > MAX_BYTES:
        raise ValueError("wire line exceeds maximum")
    return line


def decode(line):
    if len(line) > MAX_BYTES or not line.endswith(b"\n"):
        raise ValueError("line too long or missing LF")
    fields = line[:-1].split(b"\t")
    if len(fields) != 2 or b"\r" in fields[0] or b"\n" in fields[0]:
        raise ValueError("invalid record delimiter")
    data, checksum = fields
    if not CRC.fullmatch(checksum) or int(checksum, 16) != crc32(data):
        raise ValueError("invalid CRC-32")
    return unpack_json(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("encode", "decode"))
    args = ap.parse_args()
    for num, line in enumerate(sys.stdin.buffer, 1):
        try:
            if args.mode == "encode":
                sys.stdout.buffer.write(encode(unpack_json(line)))
            else:
                obj = decode(line)
                print(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        except (ValueError, UnicodeError) as err:
            print(f"line {num}: {err}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
