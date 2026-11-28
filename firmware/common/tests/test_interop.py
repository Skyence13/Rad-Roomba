#!/usr/bin/env python3
"""Differential tests: firmware/common (C) against the BASELINE Python tools in interface/.

Usage: test_interop.py <path to rrc_codec_tool>
Every comparison is byte-exact. The baseline files are imported unmodified.
"""
import base64
import hashlib
import json
import random
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "interface"))
import wire_codec  # noqa: E402  (baseline, unmodified)

TOOL = None


def run(mode, data):
    return subprocess.run([TOOL, mode], input=data, stdout=subprocess.PIPE, check=True).stdout


def random_value(rng, depth=0):
    kind = rng.randrange(9 if depth < 4 else 6)
    if kind == 0:
        return rng.randrange(-2**53, 2**53)
    if kind == 1:
        return rng.choice([0, 1, -1, 2**32 - 1, 2**63 - 1, -2**63, 2**64, 10**30])
    if kind == 2:
        return rng.choice([True, False, None])
    if kind == 3:
        return rng.choice([0.5, -1e-7, 1e300, 3.14159, 8.2, -0.0, 1e22, 123456.789])
    if kind in (4, 5):
        alphabet = 'abcXYZ019 _-"\\/\b\f\n\r\t\x00\x1f\x7fé€😀 '
        return "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 12)))
    if kind in (6, 7):
        return [random_value(rng, depth + 1) for _ in range(rng.randrange(0, 5))]
    return random_object(rng, depth + 1)


def random_object(rng, depth=0):
    return {f"k{n}" + rng.choice(["", "é", "\n", '"']): random_value(rng, depth)
            for n in range(rng.randrange(0, 6))}


class Interop(unittest.TestCase):
    def test_reencode_is_byte_identical(self):
        """C reader + writer + framing reproduce wire_codec.encode output exactly."""
        rng = random.Random(20261125)
        lines = [wire_codec.encode(random_object(rng)) for _ in range(3000)]
        lines += [(REPO / "examples" / "head_response.wire").read_bytes()]
        for row in (REPO / "examples" / "head_transactions.ndjson").read_text().splitlines():
            lines.append(wire_codec.encode(json.loads(row)))
        out = run("reencode", b"".join(lines))
        self.assertEqual(out, b"".join(lines))

    def test_accept_reject_matches_baseline_decoder(self):
        """Random corruption: the C receiver accepts exactly what wire_codec.decode accepts."""
        rng = random.Random(4)
        base = [wire_codec.encode(random_object(rng)) for _ in range(200)]
        cases = []
        for _ in range(6000):
            line = bytearray(rng.choice(base))
            for _ in range(rng.randrange(1, 3)):
                op = rng.randrange(5)
                pos = rng.randrange(len(line) - 1)  # keep the final LF: one line per case
                if op == 0:
                    line[pos] ^= 1 << rng.randrange(8)
                elif op == 1:
                    del line[pos]
                elif op == 2:
                    line.insert(pos, rng.choice(b'\t\r "{}[],:\\0aF\x80\xff'))
                elif op == 3:
                    line[pos] = rng.choice(b'\t\r"{}[],:\\09afAF')
                else:
                    line[pos:pos + 1] = line[pos:pos + 1] * 2
            if b"\n" in line[:-1] or len(line) < 2:
                continue
            cases.append(bytes(line))
        verdicts = run("check", b"".join(cases)).decode().splitlines()
        self.assertEqual(len(verdicts), len(cases))
        accepted = 0
        for line, verdict in zip(cases, verdicts):
            try:
                wire_codec.decode(line)
                want = True
            except (ValueError, UnicodeError, RecursionError):
                want = False
            accepted += want
            self.assertEqual(verdict == "OK", want, msg=f"{line!r} -> {verdict}")
        self.assertGreater(accepted, 20)          # the corpus exercises both outcomes
        self.assertLess(accepted, len(cases) - 1000)

    def test_specific_rejections(self):
        good = wire_codec.encode({"a": 1})
        dup = b'{"a":1,"a":2}'
        nan = b'{"a":NaN}'

        def framed(data):
            return data + b"\t" + f"{zlib.crc32(data):08X}".encode() + b"\n"
        cases = [
            (good, "OK"),
            (framed(dup), "ERR json-duplicate-key"),
            (framed(nan), "ERR json-syntax"),
            (framed(b"[1]"), "ERR json-not-object"),
            (framed(b""), "ERR json-syntax"),
            (good[:-9] + good[-9:].lower(), "ERR crc-format"),
            (good.replace(b"\t", b"\t\t"), "ERR delimiter"),
            (good.replace(b"1", b"2"), "ERR crc-mismatch"),
            (framed(b'{"a":"' + b"x" * 8175 + b'"}'), "ERR oversize"),      # 8193 bytes
            (framed(b'{"a":"' + b"x" * 8174 + b'"}'), "OK"),                # exactly 8192 bytes
        ]
        self.assertEqual(len(cases[-1][0]), 8192)
        out = run("check", b"".join(c for c, _ in cases)).decode().splitlines()
        self.assertEqual(out, [want for _, want in cases])
        for line, want in cases:
            ok = True
            try:
                wire_codec.decode(line)
            except ValueError:
                ok = False
            self.assertEqual(ok, want == "OK")

    def test_sha256_base64_crc32(self):
        rng = random.Random(7)
        blobs = [bytes(rng.randrange(256) for _ in range(n)) for n in list(range(0, 70)) + [767, 768, 769, 3390, 5000]]
        blobs.append((REPO / "examples" / "head_descriptor.json").read_bytes())
        out = run("digest", b"".join(b.hex().encode() + b"\n" for b in blobs)).decode().splitlines()
        for blob, row in zip(blobs, out):
            sha, _, rest = row.partition(" ")
            b64, _, crc = rest.rpartition(" ")
            self.assertEqual(sha, hashlib.sha256(blob).hexdigest())
            self.assertEqual(b64, base64.b64encode(blob).decode())
            self.assertEqual(crc, f"{zlib.crc32(blob):08X}")
        dec = run("b64dec", b"".join(base64.b64encode(b) + b"\n" for b in blobs)).decode().splitlines()
        self.assertEqual(dec, [b.hex() for b in blobs])
        self.assertEqual(run("b64dec", b"Zg=\nZh==\n*m9v\n").decode().split(), ["ERR"] * 3)


if __name__ == "__main__":
    TOOL = sys.argv.pop(1)
    unittest.main(verbosity=2)
