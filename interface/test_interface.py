#!/usr/bin/env python3
"""Executable self-checks for the portable design-package examples."""
import copy
import json
import hashlib
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from check_frames import AttachedReader, LEGACY_SCHEMA, SCHEMA, examine, validate_semantics
from wire_codec import decode, encode
from head_discovery import assemble_descriptor, attachment_manifest, evaluate, validate_geometry

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GOOD = json.loads((EXAMPLES / "head_normal.json").read_text())
BAD = json.loads((EXAMPLES / "head_degraded.json").read_text())
VALIDATOR = Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=FormatChecker())


SESSION = json.loads((EXAMPLES / "head_session.json").read_text())
KEY = SESSION["attachment_session_id"]


class HeadContract(unittest.TestCase):
    def test_expected_examples(self):
        history = {}
        for frame, wanted in ((GOOD, [0, 1, 2, 3]), (BAD, [])):
            VALIDATOR.validate(frame)
            validate_semantics(frame)
            self.assertEqual(examine(frame, history, 10000, KEY), (wanted, []))

    def test_nullable_reference_localizes_loss(self):
        f = copy.deepcopy(BAD)
        f["sync"] = copy.deepcopy(GOOD["sync"])
        self.assertEqual(examine(f, {}, 10000, KEY), ([0, 1, 3], []))

    def test_beyond_deadtime(self):
        f = copy.deepcopy(GOOD)
        f["segments"][2]["alpha"]["live_us"] = f["span_us"] + 1
        with self.assertRaises(ValueError):
            validate_semantics(f)

    def test_missing_reading_and_lane_order(self):
        f = copy.deepcopy(GOOD)
        f["segments"][0]["alpha"] = None
        with self.assertRaises(ValueError):
            validate_semantics(f)
        f["segments"] = list(reversed(f["segments"]))
        self.assertFalse(VALIDATOR.is_valid(f))

    def test_counter_gap_and_duplicate(self):
        history = {}
        examine(GOOD, history, 10000, KEY)
        with self.assertRaises(ValueError):
            examine(GOOD, history, 10000, KEY)
        f = copy.deepcopy(GOOD)
        f["sequence"] += 2
        f["start_us"] += 2 * f["span_us"]
        self.assertEqual(len(examine(f, history, 10000, KEY)[1]), 2)

    def test_identity_occurs_in_the_handshake_only(self):
        records = [json.loads(row) for row in (EXAMPLES / "head_transactions.ndjson").read_text().splitlines()]
        static = {"head_id", "head_type", "boot_id", "firmware", "fw", "setup_id",
                  "descriptor_sha256", "descriptor_id", "geometry_id", "attachment_session_id"}
        bound = False
        for req, rsp in zip(records[::2], records[1::2]):
            self.assertEqual(req["id"], rsp["id"])
            self.assertEqual((req["v"],rsp["v"]), ("2.0","2.0"))
            if bound:
                self.assertFalse(static.intersection(req["args"]))
                self.assertFalse(static.intersection(rsp["body"]))
            if req["op"] == "BIND":
                bound = rsp["body"]["bound"]
        self.assertTrue(bound)
        for field in static:
            self.assertFalse(VALIDATOR.is_valid(dict(GOOD, **{field:"unexpected"})))

    def test_attachment_lifetime(self):
        reply = decode((EXAMPLES / "head_response.wire").read_bytes())
        reader = AttachedReader(SESSION)
        with self.assertRaisesRegex(ValueError, "outstanding"):
            reader.capture_read(reply, reply["id"] + 1, VALIDATOR, 10000)
        saved, eligible, _ = reader.capture_read(reply, reply["id"], VALIDATOR, 10000)
        self.assertEqual(saved, {"attachment_session_id": KEY, "frame": GOOD})
        self.assertEqual(eligible, [0,1,2,3])
        reader.invalidate()  # Latched detach/reseat, host restart or ambiguous link.
        with self.assertRaisesRegex(ValueError, "handshake"):
            reader.capture_read(reply, reply["id"], VALIDATOR, 10000)

    def test_unbound_after_head_reset(self):
        reader = AttachedReader(SESSION)
        reply = {"type":"RSP","v":"2.0","id":4,"status":"UNBOUND","body":{}}
        with self.assertRaisesRegex(ValueError, "lost binding"):
            reader.capture_read(reply, 4, VALIDATOR, 10000)
        with self.assertRaisesRegex(ValueError, "attachment closed"):
            reader.capture_read(dict(reply,status="OK",body=GOOD), 4, VALIDATOR, 10000)
        self.assertEqual(reader.history, {})

    def test_new_connection_even_for_same_head_and_boot(self):
        h = json.loads((EXAMPLES / "head_hello.json").read_text())
        data = (EXAMPLES / "head_descriptor.json").read_bytes()
        registry = json.loads((EXAMPLES / "head_registry_bench.json").read_text())
        verified = evaluate(h,data,registry)
        first = attachment_manifest(h,verified)
        second = attachment_manifest(h,verified)
        self.assertNotEqual(first["attachment_session_id"],second["attachment_session_id"])
        for manifest in [first,second]:
            for name,value in SESSION.items():
                if name != "attachment_session_id":
                    self.assertEqual(manifest[name],value)
        history = {}
        examine(GOOD,history,10000,first["attachment_session_id"])
        reset = dict(GOOD,sequence=0,start_us=0)
        self.assertEqual(examine(reset,history,10000,second["attachment_session_id"]),([0,1,2,3],[]))

    def test_archival_v1_replay(self):
        schema = Draft202012Validator(json.loads(LEGACY_SCHEMA.read_text()),format_checker=FormatChecker())
        old = dict(GOOD,icd="1.0",head_id=SESSION["head_id"],boot_id=SESSION["boot_id"],
                   fw=SESSION["firmware"],setup_id=SESSION["setup_id"])
        schema.validate(old)
        self.assertFalse(VALIDATOR.is_valid(old))
        self.assertFalse(schema.is_valid(GOOD))

    def test_wire_round_trip_and_corruption(self):
        packet = (EXAMPLES / "head_response.wire").read_bytes()
        decoded = decode(packet)
        self.assertEqual(decoded["body"], GOOD)
        self.assertEqual(encode(decoded), packet)
        with self.assertRaises(ValueError):
            decode(packet.replace(b'"sequence":152', b'"sequence":153', 1))

    def test_wire_damaged_structure(self):
        packet = encode(GOOD)
        for damaged in (packet[:-1], b'x' * 8192 + packet, packet.replace(b'\t', b'\t\t')):
            with self.assertRaises(ValueError):
                decode(damaged)


    def test_head_descriptor_round_trip(self):
        replies = [json.loads(line) for line in (EXAMPLES / "head_transactions.ndjson").read_text().splitlines()]
        data = (EXAMPLES / "head_descriptor.json").read_bytes()
        hello = json.loads((EXAMPLES / "head_hello.json").read_text())
        registry = json.loads((EXAMPLES / "head_registry_bench.json").read_text())
        chunks = [r["body"] for r in replies if r["type"] == "RSP" and "bytes_b64" in r["body"]]
        self.assertEqual(data, assemble_descriptor(hello, chunks))
        with self.assertRaisesRegex(ValueError, "missing|incomplete"):
            assemble_descriptor(hello, chunks[1:])
        with self.assertRaisesRegex(ValueError, "changed"):
            assemble_descriptor(hello, [dict(chunks[0], boot_id="new")])
        self.assertEqual(evaluate(hello, data, registry)["mode"], "BENCH")
        with self.assertRaisesRegex(ValueError, "authorization"):
            evaluate(hello, data, registry, "SURVEY")

    def test_registry_rejects_changed_descriptor_and_unknown_head(self):
        data = (EXAMPLES / "head_descriptor.json").read_bytes()
        hello = json.loads((EXAMPLES / "head_hello.json").read_text())
        registry = json.loads((EXAMPLES / "head_registry_bench.json").read_text())
        with self.assertRaisesRegex(ValueError, "digest"):
            evaluate(hello, data.replace(b'bench-A', b'bench-B'), registry)
        altered = data.replace(b'bench-A', b'bench-B')
        new_digest = hashlib.sha256(altered).hexdigest()
        with self.assertRaisesRegex(ValueError, "registry"):
            evaluate(dict(hello, descriptor_sha256=new_digest), altered, registry)
        with self.assertRaisesRegex(ValueError, "unique trusted"):
            evaluate(hello, data, {"records":[]})
        registry["records"][0]["authorized_uses"].append("SURVEY")
        with self.assertRaisesRegex(ValueError, "measured geometry"):
            evaluate(hello, data, registry, "SURVEY")

    def test_descriptor_aperture_and_standoff(self):
        bounds = json.loads((EXAMPLES / "head_descriptor.json").read_text())
        geom = json.loads((EXAMPLES / "head_geometry_concept.json").read_text())
        for lane, expected in zip(bounds["segments"],geom["segments"]):
            self.assertEqual({key:lane[key] for key in expected},expected)
        self.assertAlmostEqual(bounds["nominal_window_standoff_m"], 0.010)
        mount_z = geom["drawing_origin_to_head_mount"]["xyz_m"][2]
        self.assertAlmostEqual(mount_z + bounds["envelope_m"]["min"][2], 0.007)
        for segment in bounds["segments"]:
            self.assertAlmostEqual(mount_z + segment["center_m"][2],0.010)
        broken = copy.deepcopy(bounds)
        broken["segments"][1]["sensitive_polygon_m"][0][1] = 0.50
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_geometry(broken)


if __name__ == "__main__":
    unittest.main(verbosity=2)
