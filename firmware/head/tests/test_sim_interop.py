#!/usr/bin/env python3
"""Integration tests: rr_head_sim (the real firmware core on Linux) driven by the BASELINE host
tools interface/wire_codec.py, interface/head_discovery.py and interface/check_frames.py.

Usage: test_sim_interop.py <path to rr_head_sim> [unittest options]
The baseline files are imported unmodified; ACQ frames are validated against the unchanged
interface/acquisition.schema.json.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headsim import REPO, Link, Sim, head_discovery, wire_codec  # noqa: E402
import check_frames  # noqa: E402  baseline, unmodified

EXE = None
EXAMPLES = REPO / "examples"
ACQ = Draft202012Validator(json.loads(check_frames.SCHEMA.read_text()), format_checker=FormatChecker())
READOUTS = ("alpha", "beta_window", "photon_ref")
RESULTS = {}


def read_all(link, after=-1, limit=100000):
    """Poll READ until EMPTY; returns the list of ACQ bodies."""
    frames = []
    while len(frames) < limit:
        rsp = link.request("READ", {"after_seq": after})
        if rsp["status"] != "OK":
            return frames, rsp
        frames.append(rsp["body"])
        after = rsp["body"]["sequence"]
    return frames, None


class SimCase(unittest.TestCase):
    sim_args = ()
    sim_kw = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.truth = Path(self.tmp.name) / "truth.ndjson"
        self.sim = Sim(EXE, *self.sim_args, truth_log=self.truth, **self.sim_kw)
        self.link = Link(self.sim)

    def tearDown(self):
        self.link.close()
        self.assertEqual(self.sim.stop(), 0, "emulator must shut down cleanly on SIGTERM")
        self.tmp.cleanup()

    def bound_reader(self):
        hello, data, manifest = self.link.handshake()
        return hello, check_frames.AttachedReader(manifest)

    def capture(self, reader, after):
        """One READ taken through the baseline AttachedReader (schema + semantics + continuity)."""
        rsp = self.link.request("READ", {"after_seq": after})
        return reader.capture_read(rsp, rsp["id"], ACQ, 10000)

    def truth_rows(self):
        return [json.loads(row) for row in self.truth.read_text().splitlines()]


class BaselineReplica(SimCase):
    """The emulator loaded with the 0.3 example identity must reproduce the 0.3 example bytes."""
    sim_args = ("--descriptor-file", EXAMPLES / "head_descriptor.json", "--serial", "HEAD-DEMO-001",
                "--descriptor-id", "D-SIPM4-001-P01", "--setup-id", "optic-test-01", "--firmware", "sim-1.0",
                "--boot-id", "8050a49f-b67f-4ce2-9b87-1502a340d1f4")

    def test_handshake_bytes_equal_the_baseline_example(self):
        rows = [json.loads(r) for r in (EXAMPLES / "head_transactions.ndjson").read_text().splitlines()]
        compared = 0
        for req, want in zip(rows[::2], rows[1::2]):
            if req["op"] not in ("HELLO", "GET_DESCRIPTOR", "BIND"):
                continue
            self.link.send_raw(wire_codec.encode(req))
            self.assertEqual(self.link.recv_line(), wire_codec.encode(want), msg=req["op"])
            compared += 1
        self.assertEqual(compared, 7)

    def test_baseline_registry_accepts_bench_and_rejects_survey(self):
        registry = json.loads((EXAMPLES / "head_registry_bench.json").read_text())
        hello, data, manifest = self.link.handshake(registry)
        self.assertEqual(hello, json.loads((EXAMPLES / "head_hello.json").read_text()))
        self.assertEqual(data, (EXAMPLES / "head_descriptor.json").read_bytes())
        session = json.loads((EXAMPLES / "head_session.json").read_text())
        for key, value in session.items():
            if key != "attachment_session_id":
                self.assertEqual(manifest[key], value)
        with self.assertRaisesRegex(ValueError, "authorization"):
            head_discovery.evaluate(hello, data, registry, "SURVEY")
        # a fixed descriptor cannot have its setup changed underneath it
        self.assertEqual(self.link.request("ENG_SETUP_SET", {"bias": {"ref_mv": 31000}})["status"], "UNSUPPORTED")


class Handshake(SimCase):
    def test_descriptor_rev_e_concept(self):
        hello, data, manifest = self.link.handshake()
        self.assertEqual(hashlib.sha256(data).hexdigest(), hello["descriptor_sha256"])
        self.assertTrue(data.endswith(b"}\n"))
        desc = json.loads(data)
        head_discovery.VALIDATOR.validate(desc)         # baseline descriptor schema, unchanged
        head_discovery.validate_geometry(desc)
        self.assertEqual(desc["geometry_basis"], "CONCEPT")
        self.assertEqual(desc["mechanical_revision"], "E")
        self.assertEqual((desc["serial"], desc["setup_id"]), (hello["head_id"], hello["setup_id"]))
        # geometry against the system contract (mm in base_link -> m in head_mount)
        import yaml
        contract = yaml.safe_load((REPO / "interface" / "system" / "contract.yaml").read_text())
        fr = contract["frames"]
        mount = fr["head_mount"]["xyz_mm"]
        env = fr["head_envelope_rev_e_mm"]
        opt = fr["optics"]
        for axis, key in enumerate("xyz"):
            self.assertAlmostEqual(desc["envelope_m"]["min"][axis], (env[key][0] - mount[axis]) / 1000, places=9)
            self.assertAlmostEqual(desc["envelope_m"]["max"][axis], (env[key][1] - mount[axis]) / 1000, places=9)
        for lane, y_mm in zip(desc["segments"], opt["segment_center_y_mm"]):
            cx = (opt["row_center_x_mm"] - mount[0]) / 1000
            cz = (opt["entrance_film_z_mm"] - mount[2]) / 1000
            for got, want in zip(lane["center_m"], [cx, y_mm / 1000, cz]):
                self.assertAlmostEqual(got, want, places=9)   # (131.2 - 65.7) / 1000 is not exact in binary floating point
            xs = sorted({p[0] for p in lane["sensitive_polygon_m"]})
            ys = sorted({p[1] for p in lane["sensitive_polygon_m"]})
            self.assertAlmostEqual(xs[1] - xs[0], opt["active_x_mm"] / 1000, places=9)
            self.assertAlmostEqual(ys[1] - ys[0], opt["active_y_mm"] / 1000, places=9)
        self.assertEqual(desc["nominal_window_standoff_m"], opt["entrance_film_z_mm"] / 1000)
        self.assertIn(desc["bumper_projection_below_window_m"] * 1000, opt["rail_projection_options_mm"])
        self.assertEqual(desc["gate_range_us"], [10000, 1000000])
        self.assertLessEqual(len(data), head_discovery.MAX_DESCRIPTOR_BYTES)
        self.assertEqual(manifest["acq_format"], "2.0")
        RESULTS["descriptor_bytes"] = len(data)

    def test_descriptor_chunking_any_size_and_bad_arguments(self):
        hello = self.link.ok("HELLO")
        base = {"boot_id": hello["boot_id"], "descriptor_id": hello["descriptor_id"]}
        for size in (1, 7, 100, 767, 768):
            chunks, offset = [], 0
            while offset < hello["descriptor_bytes"]:
                body = self.link.ok("GET_DESCRIPTOR", dict(base, offset=offset, count=size))
                chunks.append(body)
                offset += len(base64.b64decode(body["bytes_b64"]))
                if size == 1 and offset >= 40:
                    break
            if size != 1:
                head_discovery.assemble_descriptor(hello, chunks)   # checks length and SHA-256
        for bad in (dict(base, offset=0, count=769), dict(base, offset=0, count=0),
                    dict(base, offset=hello["descriptor_bytes"], count=1), dict(base, offset=-1, count=1),
                    dict(base, offset=0), dict(base, descriptor_id="D-OTHER", offset=0, count=1)):
            self.assertEqual(self.link.request("GET_DESCRIPTOR", bad)["status"], "BAD_ARG", msg=bad)
        stale = dict(base, boot_id="8050a49f-b67f-4ce2-9b87-1502a340d1f4", offset=0, count=1)
        self.assertEqual(self.link.request("GET_DESCRIPTOR", stale)["status"], "WRONG_BOOT")

    def test_unbound_answers_and_unknown_ops(self):
        for op, args in (("TIME", {}), ("SYNC", {"sync_id": "a", "bound_us": 1, "expiry_us": 1}),
                         ("ARM", {"span_us": 100000}), ("READ", {"after_seq": -1}), ("DISARM", {}),
                         ("DIAG", {"seq": 0})):
            self.assertEqual(self.link.request(op, args), {"type": "RSP", "v": "2.0", "id": self.link.next_id - 1,
                                                            "status": "UNBOUND", "body": {}})
        self.assertEqual(self.link.request("FROBNICATE")["status"], "UNSUPPORTED")
        self.sim.advance(1_000_000)
        self.assertEqual(self.sim.ctl(cmd="stats")["gates"], 0)      # an unbound head acquires nothing
        # protocol 1.x endpoints are rejected explicitly
        self.link.send_raw(wire_codec.encode({"type": "REQ", "v": "1.0", "id": 77, "op": "HELLO", "args": {}}))
        self.assertEqual(wire_codec.decode(self.link.recv_line())["status"], "UNSUPPORTED")

    def test_stale_handshake_and_reset_between_hello_and_bind(self):
        hello = self.link.ok("HELLO")
        bind = {"boot_id": hello["boot_id"], "setup_id": hello["setup_id"],
                "descriptor_sha256": hello["descriptor_sha256"]}
        self.assertEqual(self.link.request("BIND", dict(bind, setup_id="optic-test-01"))["status"], "BAD_ARG")
        self.assertEqual(self.link.request("BIND", dict(bind, descriptor_sha256="0" * 64))["status"], "BAD_ARG")
        self.assertEqual(self.link.request("ARM", {"span_us": 100000})["status"], "UNBOUND")
        self.sim.ctl(cmd="fault", kind="mcu_reset", ms=0)          # reset between HELLO and BIND
        self.assertEqual(self.link.request("BIND", bind)["status"], "WRONG_BOOT")
        self.assertEqual(self.link.request("READ", {"after_seq": -1})["status"], "UNBOUND")
        hello2 = self.link.ok("HELLO")
        self.assertNotEqual(hello2["boot_id"], hello["boot_id"])
        self.assertEqual(self.link.request("BIND", bind)["status"], "WRONG_BOOT")   # still the old handshake
        self.link.handshake()

    def test_setup_change_invalidates_binding(self):
        hello, reader = self.bound_reader()
        self.link.ok("ARM", {"span_us": 100000})
        self.assertEqual(self.link.request("ENG_SETUP_SET", {"thresholds": {"alpha": [1500] * 4}})["status"], "BUSY")
        self.link.ok("DISARM")
        self.sim.advance(200_000)
        body = self.link.ok("ENG_SETUP_SET", {"thresholds": {"alpha": [1500] * 4}})
        self.assertEqual(body, {"changed": True, "bound": False, "persisted": False})
        for op, args in (("READ", {"after_seq": -1}), ("ARM", {"span_us": 100000}), ("TIME", {})):
            self.assertEqual(self.link.request(op, args)["status"], "UNBOUND")
        hello2, _, _ = self.link.handshake()
        self.assertEqual(hello2["boot_id"], hello["boot_id"])
        self.assertNotEqual(hello2["setup_id"], hello["setup_id"])
        self.assertNotEqual(hello2["descriptor_sha256"], hello["descriptor_sha256"])
        self.assertEqual(self.link.ok("ENG_SETUP_GET")["setup"]["thresholds"]["alpha"], [1500] * 4)


class Acquisition(SimCase):
    def start(self, span=100000, **rates):
        hello, reader = self.bound_reader()
        self.link.ok("SYNC", {"sync_id": "fit-01", "bound_us": 280, "expiry_us": 60_000_000})
        self.sim.ctl(cmd="rates", **(rates or {"alpha": [0.5, 1, 2, 4], "beta": 80, "ref": 60}))
        body = self.link.ok("ARM", {"span_us": span})
        self.assertEqual(body, {"first_seq": 0, "span_us": span})
        return reader

    def test_read_stream_validates_with_baseline_tools(self):
        reader = self.start()
        self.assertEqual(self.link.request("READ", {"after_seq": -1})["status"], "EMPTY")
        self.sim.advance(100_000 * 40 + 5000)
        after, raw = -1, []
        for expect in range(40):
            saved, eligible, notices = self.capture(reader, after)
            frame = saved["frame"]
            raw.append(self.link.last_rx)
            self.assertEqual(frame["sequence"], expect)
            self.assertEqual(eligible, [0, 1, 2, 3])
            self.assertEqual(notices, [])                      # no sequence or time gap between gates
            after = frame["sequence"]
        self.assertEqual(self.link.request("READ", {"after_seq": after})["status"], "EMPTY")
        # the captured stream also passes the baseline command-line validator with --require-usable
        ndjson = Path(self.tmp.name) / "capture.ndjson"
        ndjson.write_text("".join(json.dumps(wire_codec.decode(r)["body"]) + "\n" for r in raw))
        session = Path(self.tmp.name) / "session.json"
        session.write_text(json.dumps({"attachment_session_id": reader.session_id, "acq_format": "2.0"}))
        cli = subprocess.run([sys.executable, str(REPO / "interface" / "check_frames.py"), "--session", str(session),
                              "--require-usable", str(ndjson)], capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
        self.assertEqual(cli.stdout.count("eligible_segments=[0, 1, 2, 3] notices=none"), 40)
        sizes = [len(r) for r in raw]
        RESULTS["acq_reply_bytes"] = {"min": min(sizes), "max": max(sizes), "mean": sum(sizes) / len(sizes)}

    def test_equal_gates_live_time_and_counts_conservation(self):
        self.start(alpha=[0.5, 1, 2, 4], beta=[80, 300, 2000, 20000], ref=[60, 60, 5000, 100],
                   floor_reject=[0, 5, 0, 50], ref_reject=3)
        self.sim.advance(100_000 * 120 + 5000)
        frames, last = read_all(self.link)
        self.assertEqual(last["status"], "EMPTY")
        self.assertEqual(len(frames), 120)
        truth = {row["start_us"]: row for row in self.truth_rows()}
        self.assertEqual(len(truth), 120)
        sums = {name: [0] * 4 for name in ("alpha", "beta", "ref")}
        for n, f in enumerate(frames):
            ACQ.validate(f)
            check_frames.validate_semantics(f)
            self.assertEqual(f["sequence"], n)
            self.assertEqual(f["span_us"], 100000)
            self.assertEqual(f["start_us"], frames[0]["start_us"] + n * 100000)   # equal, contiguous gates
            t = truth[f["start_us"]]
            for seg, tl in zip(f["segments"], t["lanes"]):
                self.assertEqual(seg["flags"], [])
                self.assertEqual(seg["alpha"]["counts"], tl["alpha"])              # emitted == drawn, per gate
                self.assertEqual(seg["beta_window"]["counts"], tl["beta"])
                self.assertEqual(seg["photon_ref"]["counts"], tl["ref"])
                self.assertEqual(seg["alpha"]["live_us"], seg["beta_window"]["live_us"])   # shared floor gate
                self.assertEqual(seg["alpha"]["live_us"], tl["floor_live_ticks"] // 144)
                self.assertEqual(seg["photon_ref"]["live_us"], tl["ref_live_ticks"] // 144)
                for ch in READOUTS:
                    self.assertTrue(1 <= seg[ch]["live_us"] <= f["span_us"])
                # non-paralyzable model: live = span - tau * recorded events (10 us per event on both chains)
                # and, on the floor chain, the 300 us afterglow hold (setup default) after every alpha event
                floor_events = tl["alpha"] + tl["beta"] + tl["floor_reject"]
                self.assertEqual(tl["floor_live_ticks"], 14400000 - floor_events * 1440 - tl["alpha"] * 300 * 144)
                self.assertEqual(tl["ref_live_ticks"], 14400000 - (tl["ref"] + tl["ref_reject"]) * 1440)
                sums["alpha"][seg["id"]] += seg["alpha"]["counts"]
                sums["beta"][seg["id"]] += seg["beta_window"]["counts"]
                sums["ref"][seg["id"]] += seg["photon_ref"]["counts"]
        stats = self.sim.ctl(cmd="stats")
        self.assertEqual(stats["gates"], 120)
        for name in sums:
            self.assertEqual(sums[name], stats["drawn"][name])   # conservation over the whole run
        # sanity of the physics: mean rates, and the dead-time loss at 20 kcps (n / (1 + n tau))
        self.assertAlmostEqual(sums["beta"][0] / 12.0, 80, delta=12)
        expect = 20000 / (1 + 20054 * 10e-6)
        self.assertAlmostEqual(sums["beta"][3] / 12.0, expect, delta=expect * 0.02)
        live3 = [f["segments"][3]["beta_window"]["live_us"] for f in frames]
        self.assertAlmostEqual(sum(live3) / len(live3), 100000 - expect * 0.1 * 10.0, delta=400)
        # DIAG carries the reject counters and raw ticks of the same gate
        diag = self.link.ok("DIAG", {"seq": 7})
        t = truth[frames[7]["start_us"]]
        self.assertEqual([l["floor_reject"] for l in diag["lanes"]], [l["floor_reject"] for l in t["lanes"]])
        self.assertEqual([l["ref_reject"] for l in diag["lanes"]], [l["ref_reject"] for l in t["lanes"]])
        self.assertEqual(diag["gate_ticks"], 14400000)
        self.assertEqual(diag["sequence"], 7)
        # optional engineering field: pulse-width (time over threshold) histogram per chain
        self.assertEqual(diag["width_bins_ns"], [150, 400, 2000])
        for lane, tl in zip(diag["lanes"], t["lanes"]):
            self.assertEqual(sum(lane["floor_width_hist"]), tl["alpha"] + tl["beta"] + tl["floor_reject"])
            self.assertEqual(lane["floor_width_hist"][3], tl["alpha"])
            self.assertEqual(sum(lane["ref_width_hist"]), tl["ref"] + tl["ref_reject"])
        RESULTS["diag_reply_bytes"] = len(self.link.last_rx)

    def test_measured_zero_is_preserved(self):
        reader = self.start(alpha=0, beta=0, ref=0)
        self.sim.advance(100_000 * 3 + 5000)
        saved, eligible, _ = self.capture(reader, -1)
        self.assertEqual(eligible, [0, 1, 2, 3])
        for seg in saved["frame"]["segments"]:
            for ch in READOUTS:
                self.assertEqual(seg[ch], {"counts": 0, "live_us": 100000})   # zero counts with full live time

    def test_null_channel_carries_a_flag(self):
        reader = self.start()
        self.sim.advance(100_000 * 2 + 5000)
        self.sim.ctl(cmd="fault", kind="null_channel", lane=2, chain="ref")
        self.sim.ctl(cmd="fault", kind="saturate", lane=0, chain="floor")
        self.sim.advance(100_000 * 3)
        saved, eligible, _ = self.capture(reader, 2)
        segs = saved["frame"]["segments"]
        self.assertEqual(eligible, [1, 3])
        self.assertIsNone(segs[2]["photon_ref"])
        self.assertEqual(segs[2]["flags"], ["REFERENCE_FAULT"])
        self.assertIsNotNone(segs[2]["beta_window"])               # floor counts of that lane are preserved
        self.assertIsNone(segs[0]["alpha"])
        self.assertIsNone(segs[0]["beta_window"])
        self.assertEqual(segs[0]["flags"], ["SATURATED"])
        self.assertIsNotNone(segs[0]["photon_ref"])
        diag = self.link.ok("DIAG", {"seq": 3})
        self.assertEqual(diag["lanes"][0]["flags"], ["FLOOR_SATURATED"])
        self.sim.ctl(cmd="fault", kind="null_channel", lane=2, chain="ref", on=False)
        self.sim.ctl(cmd="fault", kind="saturate", lane=0, chain="floor", on=False)
        self.sim.advance(100_000 * 3)
        _, eligible, _ = self.capture(reader, 5)
        self.assertEqual(eligible, [0, 1, 2, 3])
        # a real overload: 2 Mcps on lane 1 leaves < 50 % live time -> SATURATED, null, never zeros
        self.sim.ctl(cmd="rates", beta=[80, 2_000_000, 80, 80])
        self.sim.advance(100_000 * 3)
        saved, eligible, _ = self.capture(reader, 8)
        self.assertEqual(eligible, [0, 2, 3])
        self.assertEqual(saved["frame"]["segments"][1]["flags"], ["SATURATED"])
        self.assertIsNone(saved["frame"]["segments"][1]["beta_window"])

    def test_retry_is_idempotent(self):
        self.start()
        self.sim.advance(100_000 * 3 + 5000)
        first = self.link.request("READ", {"after_seq": -1})
        raw = self.link.last_rx
        self.sim.advance(100_000 * 5)                                     # the head moves on meanwhile
        for _ in range(3):
            self.link.send_raw(self.link.last_tx)                         # identical request, identical id
            self.assertEqual(self.link.recv_line(), raw)
        self.assertEqual(first["body"]["sequence"], 0)
        nxt = self.link.request("READ", {"after_seq": 0})
        self.assertEqual(nxt["body"]["sequence"], 1)                      # nothing was consumed by the retries
        arm = self.link.request("ARM", {"span_us": 100000})
        self.assertEqual(arm["body"], {"first_seq": 0, "span_us": 100000})    # matching ARM preserves acquisition

    def test_crc_error_then_retry(self):
        self.start()
        self.sim.advance(100_000 * 2 + 5000)
        self.sim.ctl(cmd="fault", kind="corrupt_crc", count=1)
        req_id = self.link.next_id
        with self.assertRaises(ValueError):
            self.link.request("READ", {"after_seq": -1})                  # baseline decoder rejects the bytes
        damaged = self.link.last_rx
        rsp = self.link.request("READ", {"after_seq": -1}, req_id=req_id)  # same id
        self.assertEqual(rsp["status"], "OK")
        self.assertEqual(rsp["body"]["sequence"], 0)
        self.assertEqual(len(damaged), len(self.link.last_rx))
        self.assertEqual(sum(a != b for a, b in zip(damaged, self.link.last_rx)), 1)   # one damaged byte
        # a damaged REQUEST is discarded silently by the head; the retry succeeds
        bad = bytearray(wire_codec.encode({"type": "REQ", "v": "2.0", "id": 900, "op": "READ", "args": {"after_seq": 0}}))
        good = bytes(bad)
        bad[20] ^= 0x04
        self.link.send_raw(bytes(bad))
        self.assertIsNone(self.link.recv_line(timeout=0.3))
        self.link.send_raw(good)
        self.assertEqual(wire_codec.decode(self.link.recv_line())["body"]["sequence"], 1)

    def test_gap_after_overflow_and_empty(self):
        reader = self.start(span=10000)
        self.sim.advance(2000 + 10000 * 5)
        saved, _, _ = self.capture(reader, -1)
        self.assertEqual(saved["frame"]["sequence"], 0)
        stat = self.link.ok("STATUS")
        depth = stat["buffer_frames"]
        self.assertGreaterEqual(depth, 128)
        self.sim.advance(10000 * 400)                                     # reads paused: 405 gates in total
        rsp = self.link.request("READ", {"after_seq": 0})
        self.assertEqual(rsp["status"], "GAP")
        newest = 404
        self.assertEqual(rsp["body"], {"oldest_seq": newest - depth + 1, "newest_seq": newest})
        oldest = rsp["body"]["oldest_seq"]
        saved, eligible, notices = self.capture(reader, oldest - 1)       # reissue from oldest_seq - 1
        self.assertEqual(saved["frame"]["sequence"], oldest)
        self.assertEqual(notices, [f"sequence gap of {oldest - 1}", f"time gap of {(oldest - 1) * 10000} us"])
        frames, last = read_all(self.link, oldest)
        self.assertEqual(last["status"], "EMPTY")
        self.assertEqual([f["sequence"] for f in frames], list(range(oldest + 1, newest + 1)))
        self.assertEqual(self.link.request("READ", {"after_seq": oldest - 2})["status"], "GAP")
        self.assertEqual(self.link.request("DIAG", {"seq": 1})["status"], "GAP")

    def test_reset_while_armed_yields_zero_frames_until_rehandshake(self):
        reader = self.start()
        self.sim.advance(100_000 * 5 + 5000)
        self.capture(reader, -1)
        self.sim.ctl(cmd="fault", kind="mcu_reset", cause="watchdog", ms=0)
        self.sim.advance(100_000 * 5)
        for after in (-1, 0, 4):
            rsp = self.link.request("READ", {"after_seq": after})
            self.assertEqual(rsp, {"type": "RSP", "v": "2.0", "id": rsp["id"], "status": "UNBOUND", "body": {}})
        with self.assertRaisesRegex(ValueError, "lost binding"):
            reader.capture_read(rsp, rsp["id"], ACQ, 10000)               # baseline reader closes the attachment
        self.assertEqual(self.link.request("ARM", {"span_us": 100000})["status"], "UNBOUND")
        self.assertEqual(self.sim.ctl(cmd="stats")["gates"], 5)          # nothing acquired after the reset
        status = self.link.ok("STATUS")
        self.assertEqual((status["link"], status["reset_cause"], status["next_seq"]), ("UNBOUND", "WATCHDOG", 0))
        self.assertIn("WATCHDOG_RESET", status["health"])
        hello, reader2 = self.bound_reader()
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(100_000 * 2 + 5000)
        saved, _, _ = self.capture(reader2, -1)
        self.assertEqual(saved["frame"]["sequence"], 0)                   # new attachment starts at zero
        self.assertLess(saved["frame"]["start_us"], 1_000_000)            # and on the new boot's clock
        self.assertEqual(saved["frame"]["sync"]["state"], "UNSYNCED")     # the old clock fit is gone

    def test_hello_discards_the_previous_attachment(self):
        self.start()
        self.sim.advance(100_000 * 5 + 5000)
        hello = self.link.ok("HELLO")
        self.assertEqual(self.link.request("READ", {"after_seq": -1})["status"], "UNBOUND")
        self.sim.advance(100_000 * 5)
        self.assertEqual(self.sim.ctl(cmd="stats")["gates"], 5)          # HELLO disarmed the head
        self.link.ok("BIND", {"boot_id": hello["boot_id"], "setup_id": hello["setup_id"],
                              "descriptor_sha256": hello["descriptor_sha256"]})
        self.assertEqual(self.link.request("READ", {"after_seq": -1})["status"], "EMPTY")   # old frames are gone
        self.assertEqual(self.link.ok("ARM", {"span_us": 100000})["first_seq"], 0)

    def test_disarm_rearm_continues_sequence(self):
        self.start()
        self.sim.advance(2000 + 100_000 * 3 + 40_000)                    # 3 complete gates, the 4th in progress
        body = self.link.ok("DISARM")
        self.assertEqual(body, {"last_seq": 3, "complete": False})
        self.assertEqual(self.link.request("ARM", {"span_us": 100000})["status"], "BUSY")
        self.sim.advance(100_000)
        self.assertEqual(self.link.ok("DISARM"), {"last_seq": 3, "complete": True})
        self.sim.advance(500_000)
        frames, _ = read_all(self.link)
        self.assertEqual([f["sequence"] for f in frames], [0, 1, 2, 3])   # the gate in progress was completed
        self.assertEqual(self.link.ok("ARM", {"span_us": 50000}), {"first_seq": 4, "span_us": 50000})
        self.sim.advance(2000 + 50_000 * 2)
        frames, _ = read_all(self.link, 3)
        self.assertEqual([(f["sequence"], f["span_us"]) for f in frames], [(4, 50000), (5, 50000)])
        self.assertGreater(frames[0]["start_us"], 900_000)
        for bad in (9999, 1000001, "100000", 100000.5):
            self.assertEqual(self.link.request("ARM", {"span_us": bad})["status"], "BAD_ARG" if bad != 50000 else "OK")

    def test_time_and_sync_states(self):
        hello, reader = self.bound_reader()
        t1 = self.link.ok("TIME")
        self.sim.advance(1000)
        t2 = self.link.ok("TIME")
        self.assertEqual(t2["rx_us"] - t1["rx_us"], 1000)
        self.assertEqual(t1["tx_us"] - t1["rx_us"], 150)                  # emulator turnaround
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(2000 + 100_000 * 2)
        self.link.ok("SYNC", {"sync_id": "fit-01", "bound_us": 280, "expiry_us": 250_000})
        installed = self.link.ok("TIME")["rx_us"]
        self.sim.advance(100_000 * 8)
        frames, _ = read_all(self.link)
        states = [f["sync"]["state"] for f in frames]
        self.assertEqual(states, ["UNSYNCED"] * 2 + ["LOCKED"] * 3 + ["HOLDOVER"] * 5)
        for f in frames:
            ACQ.validate(f)
            check_frames.validate_semantics(f)                           # null rules of the three states
            if f["sync"]["state"] != "UNSYNCED":
                self.assertEqual(f["sync"]["sync_id"], "fit-01")
                self.assertEqual(f["sync"]["age_us"], f["start_us"] - installed)
        self.assertEqual([f["sync"]["bound_us"] for f in frames[2:5]], [280] * 3)
        holdover = [f["sync"]["bound_us"] for f in frames[5:]]
        self.assertEqual(holdover, sorted(holdover))
        self.assertGreater(holdover[-1], holdover[0])
        history = {}
        elig = [check_frames.examine(f, history, 10000, "k")[0] for f in frames]
        self.assertEqual(elig, [[]] * 2 + [[0, 1, 2, 3]] * 3 + [[]] * 5)   # only LOCKED gates qualify
        for bad in ({"sync_id": "has space", "bound_us": 1, "expiry_us": 1}, {"sync_id": "a", "bound_us": -1, "expiry_us": 1},
                    {"sync_id": "a", "bound_us": 1}, {"sync_id": "", "bound_us": 1, "expiry_us": 1}):
            self.assertEqual(self.link.request("SYNC", bad)["status"], "BAD_ARG")

    def test_thermal_fault_and_heater(self):
        self.link.ok("ENG_SETUP_SET", {"heater": {"enable": True, "setpoint_mc": 5000, "max_duty_pct": 60}})
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="analog", sipm_c=[2.0, 2.1, 1.9, 2.0], heater_c=1.0)
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(2000 + 100_000 * 40)
        frames, _ = read_all(self.link)
        for f in frames:
            ACQ.validate(f)
            check_frames.validate_semantics(f)
            self.assertIn(f["thermal"]["duty_pct"], (0, 100))            # whole gates only
            self.assertEqual(f["thermal"]["head_c"], 2.0)
        duty = [f["thermal"]["duty_pct"] for f in frames]
        self.assertGreater(sum(duty), 0)
        # every change of heater state is marked in the DIAG record of the gate that contains the edge
        marks = [self.link.ok("DIAG", {"seq": f["sequence"]})["heater"]["transition"] for f in frames]
        edges = [n > 0 and duty[n] != duty[n - 1] for n in range(len(duty))]
        self.assertEqual(marks, edges)
        self.assertTrue(any(edges))
        # heater-plate sensor fault: heater off, HEATER_FAULT latched until cleared
        self.sim.ctl(cmd="fault", kind="thermal", what="heater_sensor_open")
        self.sim.advance(300_000)
        saved, eligible, _ = self.capture(reader, self.link.ok("STATUS")["newest_seq"] - 1)
        self.assertEqual(saved["frame"]["thermal"], {"head_c": 2.0, "heater": "FAULT", "duty_pct": 0})
        self.assertEqual(saved["frame"]["flags"], ["HEATER_FAULT"])
        self.assertEqual(eligible, [])
        self.sim.ctl(cmd="fault", kind="thermal", what="heater_sensor_open", on=False)
        self.sim.advance(300_000)
        self.assertIn("HEATER_SENSOR", self.link.ok("STATUS")["health"])
        self.assertEqual(self.link.ok("FAULT_CLEAR")["health"], [])
        # all SiPM sensors lost: head_c null + HEAD_TEMP_OUT_OF_RANGE
        self.sim.ctl(cmd="fault", kind="thermal", what="sipm_open")
        self.sim.advance(300_000)
        saved, eligible, _ = self.capture(reader, self.link.ok("STATUS")["newest_seq"] - 1)
        self.assertIsNone(saved["frame"]["thermal"]["head_c"])
        self.assertIn("HEAD_TEMP_OUT_OF_RANGE", saved["frame"]["flags"])
        # DISARM switches the heater off
        self.link.ok("DISARM")
        self.sim.advance(300_000)
        self.assertFalse(self.link.ok("STATUS")["heater"]["on"])

    def test_rate_schedule_applies_at_the_given_head_time(self):
        self.start(alpha=0, beta=0, ref=0)
        self.sim.advance(2000 + 100_000 * 2)
        now = self.sim.ctl(cmd="ping")["head_us"]
        # gates start at 2000 + n * 100000: switch 20 kcps on for exactly gate 5 and half of gate 6
        self.sim.ctl(cmd="rates", from_us=502_000, beta=[20000, 0, 0, 0])
        self.sim.ctl(cmd="rates", from_us=652_000, beta=0)
        self.assertEqual(self.sim.ctl(cmd="stats")["pending_rate_changes"], 2)
        self.assertLess(now, 502_000)
        self.sim.advance(100_000 * 8)
        frames, _ = read_all(self.link)
        beta = [f["segments"][0]["beta_window"]["counts"] for f in frames[:9]]
        self.assertEqual(beta[:5], [0] * 5)
        self.assertEqual(beta[7:], [0] * 2)
        self.assertAlmostEqual(beta[5], 2000 / 1.2, delta=170)             # n / (1 + n tau) at 20 kcps, tau 10 us
        self.assertAlmostEqual(beta[6] / beta[5], 0.5 * 1.2 / 1.1, delta=0.08)   # half a gate at the lower loss


class BoardFunctions(SimCase):
    """IB-17 / IB-18 through the emulator and the baseline tools: anode monitor, permit, expander, pulser, hold."""

    def arm(self, **rates):
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="rates", **(rates or {"alpha": 0, "beta": 50, "ref": 50}))
        self.sim.advance(7_500_000)      # bias ramped (500 mV per 100 ms) and settled
        self.link.ok("ARM", {"span_us": 100000})
        return reader

    def test_per_lane_bias_out_of_range_reaches_the_host(self):
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="rates", alpha=0, beta=50, ref=50)
        self.sim.advance(7_500_000)
        self.sim.ctl(cmd="analog", imon_ua=[1, 1, 1, 1, 1, 1, 400, 1])   # reference chain of lane 2 over 0.2 mA
        self.sim.advance(800_000)                                         # disarmed: the scan sees it
        self.assertEqual(self.link.ok("STATUS", {})["imon"]["fault"], ["R2"])
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(1_000_000)
        frames, _ = read_all(self.link)
        last = frames[-1]
        ACQ.validate(last)
        check_frames.validate_semantics(last)
        seg = last["segments"][2]
        self.assertEqual(seg["flags"], ["REFERENCE_FAULT"])
        self.assertIsNone(seg["photon_ref"])
        self.assertIsNotNone(seg["beta_window"])                 # the floor chain of that lane is untouched
        self.assertIn("BIAS_OUT_OF_RANGE", last["flags"])
        self.assertEqual(last["segments"][0]["flags"], [])
        diag = self.link.ok("DIAG", {"seq": last["sequence"]})
        self.assertEqual(diag["lanes"][2]["imon_na"], [None, None])      # scan paused while armed (review M2)
        self.assertIn("BIAS_OUT_OF_RANGE", diag["lanes"][2]["flags"])
        self.assertEqual(diag["lanes"][2]["alpha_idle_clears"], 0)
        st = self.link.ok("STATUS", {})
        self.assertEqual(st["imon"]["fault"], ["R2"])
        self.assertEqual(st["imon"]["scan"], "PAUSED_ARMED")
        self.assertEqual(st["bumper"], {"available": False, "now": None, "latched": None})   # rev A: not available
        self.assertIsNone(diag["bumper_zones"])

    def test_tripped_permit_lid_and_recovery(self):
        hello, reader = self.bound_reader()
        self.sim.advance(7_500_000)
        st = self.link.ok("STATUS", {})
        self.assertTrue(st["bias"]["on"])
        self.assertEqual(st["expander"], {"present": True, "hv_permit": True, "hv_inhibit": False,
                                          "lid_open": False, "efuse_fault": False, "hw_rev": 0})
        self.sim.ctl(cmd="analog", lid_open=True)
        self.sim.advance(2_000_000)
        st = self.link.ok("STATUS", {})
        self.assertIn("BIAS_PERMIT", st["health"])
        self.assertFalse(st["bias"]["on"])
        self.assertTrue(st["expander"]["lid_open"] and st["expander"]["hv_inhibit"] and not st["expander"]["hv_permit"])
        self.assertEqual(self.link.ok("FAULT_CLEAR", {})["cleared"], [])        # lid still open
        self.sim.ctl(cmd="analog", lid_open=False)
        self.assertIn("BIAS_PERMIT", self.link.ok("FAULT_CLEAR", {})["cleared"])
        self.sim.advance(7_500_000)
        st = self.link.ok("STATUS", {})
        self.assertTrue(st["bias"]["on"] and "BIAS_PERMIT" not in st["health"])
        self.assertTrue(self.sim.ctl(cmd="stats")["board"]["bias"]["permit"])
        # without the expander the same trip is found from BIAS_VMON
        self.sim.ctl(cmd="analog", expander=False, inhibit=True)
        self.sim.advance(2_000_000)
        st = self.link.ok("STATUS", {})
        self.assertIn("BIAS_PERMIT", st["health"])
        self.assertEqual(st["expander"]["present"], False)
        self.assertIsNone(st["expander"]["lid_open"])

    def test_setup_members_reach_the_board_model(self):
        hello, reader = self.bound_reader()
        self.link.ok("ENG_SETUP_SET", {"pulser": {"enable": True, "code": 500, "channel": 5, "width_us": 30,
                                                  "led_enable": True, "led_code": 2048},
                                       "afterglow": {"alpha_hold_us": 100}})
        board = self.sim.ctl(cmd="stats")["board"]
        self.assertEqual(board["pulser"], {"enable": True, "channel": 5, "code": 500, "width_us": 30,
                                           "charge_fc": 30518})   # 100 pF x 0.61 mV x 500
        self.assertEqual(board["led"]["v_led_mv"], 2500)           # 2 x 1.25 V
        self.assertEqual(board["alpha_hold_us"], 100)
        self.assertEqual(self.sim.ctl(cmd="stats")["board"]["bias"]["hv_set_code"], 0)   # HV_SET starts at 0
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="rates", alpha=0, beta=0, ref=0)
        self.sim.advance(1_000_000)
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(1_050_000)
        frames, _ = read_all(self.link)
        # 1000 charge pulses per second into reference chain 1 (R1): 61 fC.. = 131 p.e. -> inside REF_LLD..REF_ULD
        counts = [f["segments"][1]["photon_ref"]["counts"] for f in frames[1:8]]   # Poisson draws around 100 per 0.1 s gate
        self.assertTrue(all(60 <= c <= 140 for c in counts), counts)
        self.assertTrue(all(f["segments"][0]["photon_ref"]["counts"] == 0 for f in frames))

    def test_bright_beta_is_not_counted_as_alpha(self):
        """Review C1: a 120 p.e. beta crosses the ALPHA threshold (44 mV slow against 30 mV) but its time over threshold
        is ~160 ns against >= 277 ns for the weakest assumed ZnS alpha. Neither channel may gain the other's events."""
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="rates", alpha=[0, 20, 0, 0], beta=0, ref=0, floor_reject=0, ref_reject=0,
                     bright_beta=[400, 0, 0, 0], alpha_pe=300, bright_pe=120)
        self.sim.advance(300_000)
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(2_050_000)
        frames, _ = read_all(self.link)
        a0 = sum(f["segments"][0]["alpha"]["counts"] for f in frames)
        b0 = sum(f["segments"][0]["beta_window"]["counts"] for f in frames)
        a1 = sum(f["segments"][1]["alpha"]["counts"] for f in frames)
        self.assertEqual((a0, b0), (0, 0))                 # bright betas reach neither alpha nor beta window
        self.assertGreater(a1, 20)                         # real ZnS alphas (300 p.e., ~410 ns) still counted
        diag = [self.link.ok("DIAG", {"seq": f["sequence"]}) for f in frames]
        short = sum(d["lanes"][0]["alpha_short"] for d in diag)
        rej = sum(d["lanes"][0]["floor_reject"] for d in diag)
        drawn = self.sim.ctl(cmd="stats")["drawn"]["bright_beta"][0]
        self.assertEqual(short, rej)
        self.assertGreater(short, 0.8 * drawn)             # (the last gate is not read)
        # the old classification (no width condition) counts them as alpha
        self.link.ok("DISARM", {})
        self.sim.advance(300_000)
        hello, reader = self.bound_reader()
        self.link.ok("ENG_SETUP_SET", {"afterglow": {"alpha_min_tot_ns": 1}})   # 1 ns = no width condition (0 = follow the device type)
        hello, reader = self.bound_reader()
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(1_050_000)
        frames, _ = read_all(self.link)
        self.assertGreater(sum(f["segments"][0]["alpha"]["counts"] for f in frames), 100)

    def test_heater_transition_marker_is_derivable_from_acq(self):
        """Review m6: ACQ 2.0 cannot carry the marker; the per-gate heater state (thermal.heater, duty_pct 0/100) can: the gate
        with a transition is exactly the first gate whose state differs from the previous one."""
        hello, reader = self.bound_reader()
        self.link.ok("ENG_SETUP_SET", {"heater": {"enable": True, "setpoint_mc": 5000, "max_duty_pct": 100}})
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="analog", heater_c=-10)
        self.sim.ctl(cmd="rates", alpha=0, beta=10, ref=10)
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(2_000_000)
        self.sim.ctl(cmd="analog", heater_c=40)
        self.sim.advance(2_000_000)
        frames, _ = read_all(self.link)
        diag = [self.link.ok("DIAG", {"seq": f["sequence"]}) for f in frames]
        states = [f["thermal"]["heater"] for f in frames]
        self.assertIn("ON", states)
        derived = [False] + [states[i] != states[i - 1] for i in range(1, len(states))]
        marked = [d["heater"]["transition"] for d in diag]
        self.assertEqual(derived, marked)
        self.assertTrue(any(marked))
        self.assertTrue(all(f["thermal"]["duty_pct"] in (0, 100) for f in frames))

    def test_pileup_false_alphas_old_port_versus_fixed_port(self):
        """Review M6a: floor rate R on lane 0 with bright betas (120 p.e.); a second pulse within ~9 us piles up.
        Old width bookkeeping (last edge overwrites): the piled-up bright betas become alphas at rate b x R x 9 us.
        Fixed: they are never alpha and are counted in alpha_ambig."""
        results = {}
        for overwrite in (True, False):
            hello, reader = self.bound_reader()
            self.sim.ctl(cmd="analog", width_overwrite=overwrite)
            self.sim.ctl(cmd="rates", alpha=0, beta=[4000, 0, 0, 0], bright_beta=[1000, 0, 0, 0], ref=0, bright_pe=120)
            self.sim.advance(300_000)
            self.link.ok("ARM", {"span_us": 100000})
            self.sim.advance(5_050_000)
            frames, _ = read_all(self.link)
            gs = self.link.ok("GATESTAT", {"after_seq": frames[-12]["sequence"], "limit": 10})["gates"]
            alpha = sum(f["segments"][0]["alpha"]["counts"] for f in frames)
            amb = sum(g["am"][0] for g in gs)
            results[overwrite] = (alpha, amb, len(frames), gs)
            self.link.ok("DISARM", {})
            self.sim.advance(300_000)
        t = results[True][2] * 0.1
        expect = 1000 * (1 - 2.718281828 ** (-5000 * 9e-6))      # bright events per second that pile up
        print("    pile-up at 5000/s floor rate: old port %.1f false alphas/s (expected %.1f), fixed port %d alphas, %d ambiguous in the last 10 gates"
              % (results[True][0] / t, expect, results[False][0], results[False][1]))
        self.assertGreater(results[True][0] / t, 0.6 * expect)
        self.assertEqual(results[False][0], 0)
        self.assertGreater(results[False][1], 0)

    def test_gatestat_is_joinable_and_cheap(self):
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="rates", alpha=[5, 0, 0, 0], beta=50, ref=50, bright_beta=[50, 0, 0, 0])
        self.sim.advance(300_000)
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(2_050_000)
        frames, _ = read_all(self.link)
        rsp = self.link.request("GATESTAT", {"after_seq": -1, "limit": 10})
        self.assertEqual(rsp["status"], "OK")
        gs = rsp["body"]["gates"]
        self.assertEqual([g["seq"] for g in gs], [f["sequence"] for f in frames[:10]])      # same sequence numbers as ACQ
        for g, f in zip(gs, frames):
            diag = self.link.ok("DIAG", {"seq": f["sequence"]})
            for k, name in (("as", "alpha_short"), ("am", "alpha_ambig"), ("fr", "floor_reject"), ("ic", "alpha_idle_clears")):
                self.assertEqual(g[k], [lane[name] for lane in diag["lanes"]])
        self.assertTrue(rsp["body"]["more"])
        nbytes = len(json.dumps(rsp["body"], separators=(",", ":")))
        print("    GATESTAT 10 gates: %d bytes of body = %.1f %% of a 1 Mbaud bus once a second" % (nbytes, (nbytes + 100) * 10e-6 * 100))

    def test_afterglow_hold_is_dead_time(self):
        reader = self.arm(alpha=[2000, 0, 0, 0], beta=0, ref=0)
        self.sim.advance(1_050_000)
        frames, _ = read_all(self.link)
        f = frames[5]
        diag = self.link.ok("DIAG", {"seq": f["sequence"]})
        lane = diag["lanes"][0]
        dead = 14_400_000 - lane["floor_live_ticks"]
        # 10 us + 150 us hold per alpha event (emulator, simulated)
        self.assertAlmostEqual(dead / max(lane["alpha_raw"], 1), (10 + 300) * 144, delta=1500)   # piled-up alphas (never held) pay 10 us only


class StrictPlaceholders(SimCase):
    """Stage 3 / review O6: the target-like head refuses ARM until the device type is set and the thresholds are confirmed."""
    sim_args = ("--strict-placeholders",)

    def test_arm_refused_until_confirmed(self):
        hello, reader = self.bound_reader()
        rsp = self.link.request("ARM", {"span_us": 100000})
        self.assertEqual(rsp["status"], "FAULT")
        self.assertEqual(rsp["body"].get("reason"), "placeholder_thresholds")
        self.link.ok("ENG_SETUP_SET", {"thresholds_confirmed": True})
        hello, reader = self.bound_reader()
        self.link.ok("ARM", {"span_us": 100000})
        self.link.ok("DISARM", {})

    def test_device_types_set_the_alpha_cut_and_the_emulated_pulse_shapes(self):
        """T13 numbers: J60035 cut 290 ns (alpha 150 p.e. 374 ns, brightest beta 240 p.e. 202 ns); J30035 cut 180 ns
        (246 / 115 ns). Both must classify the 150 p.e. alpha as alpha and the 240 p.e. beta as a short ALPHA (reject)."""
        for device, cut in (("J60035", 290), ("J30035", 180), ("S13360", 190), ("4xJ60035", 655)):
            hello, reader = self.bound_reader()
            self.link.ok("ENG_SETUP_SET", {"device": device, "thresholds_confirmed": True})
            hello, reader = self.bound_reader()
            self.assertEqual(self.link.ok("STATUS", {})["alpha_tot_ns"], cut)
            self.sim.ctl(cmd="rates", alpha=[50, 0, 0, 0], beta=0, ref=0, bright_beta=[0, 100, 0, 0],
                         alpha_pe=150, bright_pe=240)
            self.link.ok("ARM", {"span_us": 100000})
            self.sim.advance(1_150_000)
            frames, _ = read_all(self.link)
            a0 = sum(f["segments"][0]["alpha"]["counts"] for f in frames)
            a1 = sum(f["segments"][1]["alpha"]["counts"] for f in frames)
            diag = [self.link.ok("DIAG", {"seq": f["sequence"]}) for f in frames]
            short1 = sum(d["lanes"][1]["alpha_short"] for d in diag)
            if device == "4xJ60035":
                # array: FAST 2.8 mV/p.e. and the LLD at 12 p.e. = 34 mV: a 150 p.e. alpha is 0.12 V, TOT 738 ns > 655 cut
                self.assertGreater(a0, 20)
            else:
                self.assertGreater(a0, 20, device)
            self.assertEqual(a1, 0, device)
            self.assertGreater(short1, 20, device)
            self.link.ok("DISARM", {})
            self.sim.advance(300_000)
            self.sim.ctl(cmd="rates", alpha=0, bright_beta=0)


class HeaterAndFrame(SimCase):
    """Stage 3: heater over-current cut-off and the frame-potential check through the emulator."""

    def test_overcurrent_opens_the_heater_and_frame_fault_too(self):
        hello, reader = self.bound_reader()
        self.link.ok("ENG_SETUP_SET", {"heater": {"enable": True, "setpoint_mc": 5000, "max_duty_pct": 100}})
        hello, reader = self.bound_reader()
        self.sim.ctl(cmd="analog", heater_c=-10, heater_ma=3000)
        self.sim.ctl(cmd="rates", alpha=0, beta=10, ref=10)
        self.sim.advance(300_000)
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(1_500_000)
        st = self.link.ok("STATUS", {})
        self.assertTrue(st["heater"]["on"])
        self.assertEqual(st["heater"]["ma"], 3000)
        self.assertEqual(st["frame"], {"mv": 0, "fault": False})
        self.sim.ctl(cmd="analog", heater_ma=3400)                       # a partial short: 3.4 A against the 3.2 A cut-off
        self.sim.advance(900_000)
        st = self.link.ok("STATUS", {})
        self.assertIn("HEATER_OVERCURRENT", st["health"])
        self.assertFalse(st["heater"]["on"])
        self.assertEqual(st["heater"]["ma"], 0)                          # the switch opened (emulator: current gone with it)
        self.link.ok("FAULT_CLEAR", {})
        self.sim.ctl(cmd="analog", heater_ma=2500, frame_mv=80)           # frame 80 mV above ground: contact with the heater return
        self.sim.advance(2_000_000)
        st = self.link.ok("STATUS", {})
        self.assertIn("FRAME_FAULT", st["health"])
        self.assertEqual(st["frame"]["mv"], 80)
        self.assertFalse(st["heater"]["on"])


class NoWidthHistogram(SimCase):
    sim_args = ("--no-width-hist",)

    def test_head_without_pulse_width_measurement(self):
        """The width histogram is optional: a head without it omits the DIAG fields, nothing else changes."""
        hello, reader = self.bound_reader()
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(2000 + 100_000 * 2)
        saved, eligible, _ = self.capture(reader, -1)
        self.assertEqual(eligible, [])                               # no SYNC yet: frame valid, not time-qualified
        diag = self.link.ok("DIAG", {"seq": 0})
        self.assertNotIn("width_bins_ns", diag)
        self.assertTrue(all("floor_width_hist" not in lane and "ref_width_hist" not in lane for lane in diag["lanes"]))


class LinkFaults(SimCase):
    def test_link_drop_delay_and_pause(self):
        hello, reader = self.bound_reader()
        self.link.ok("ARM", {"span_us": 10000})
        self.sim.advance(2000 + 10000 * 3)
        self.capture(reader, -1)
        # link interrupted: no reply; afterwards the same attachment continues (no reset happened)
        self.sim.ctl(cmd="fault", kind="link_drop", ms=300)
        self.assertIsNone(self.link.request("READ", {"after_seq": 0}, timeout=0.15))
        time.sleep(0.35)
        saved, _, _ = self.capture(reader, 0)
        self.assertEqual(saved["frame"]["sequence"], 1)
        # delayed reply: the host times out, sends the next poll, then the OLD reply arrives first
        self.sim.ctl(cmd="fault", kind="delay_reply", ms=250, count=1)
        slow_id = self.link.next_id
        self.assertIsNone(self.link.request("READ", {"after_seq": 1}, timeout=0.1))
        late = wire_codec.decode(self.link.recv_line(timeout=1.0))
        self.assertEqual((late["id"], late["body"]["sequence"]), (slow_id, 2))
        with self.assertRaisesRegex(ValueError, "outstanding"):
            reader.capture_read(late, slow_id + 1, ACQ, 10000)            # a fresh id never matches the stale reply
        # reads paused long enough to overflow the buffer: exact GAP afterwards
        self.sim.ctl(cmd="fault", kind="pause_reads", ms=200)
        self.assertIsNone(self.link.request("READ", {"after_seq": 2}, timeout=0.1))
        self.assertEqual(self.link.ok("STATUS")["armed"], True)           # other ops still answered
        self.sim.advance(10000 * 300)
        time.sleep(0.25)
        rsp = self.link.request("READ", {"after_seq": 2})
        self.assertEqual(rsp["status"], "GAP")
        self.assertEqual(rsp["body"]["newest_seq"] - rsp["body"]["oldest_seq"] + 1, self.link.ok("STATUS")["buffer_frames"])
        # lost gate records inside the head: sequence numbers are skipped and the frames are flagged
        self.sim.ctl(cmd="fault", kind="lost_gates", count=2)
        base = rsp["body"]["newest_seq"]
        self.sim.advance(10000 * 4)
        frames, _ = read_all(self.link, base)
        self.assertEqual([f["sequence"] for f in frames], [base + 3, base + 4])
        self.assertEqual(frames[0]["flags"], ["ACQ_FAULT"])
        self.assertIn("RECORD_LOST", self.link.ok("STATUS")["health"])

    def test_head_swap_is_detected(self):
        hello, data, manifest = self.link.handshake()
        registry = {"records": [{"serial": hello["head_id"], "descriptor_id": hello["descriptor_id"],
                                 "head_type": hello["head_type"], "geometry_id": manifest["geometry_id"],
                                 "setup_id": hello["setup_id"], "descriptor_sha256": hello["descriptor_sha256"],
                                 "firmware": hello["firmware"], "authorized_uses": ["BENCH"], "calibration_id": None}]}
        self.link.ok("ARM", {"span_us": 100000})
        self.sim.advance(300_000)
        self.sim.ctl(cmd="swap", serial="RRH-SIM-0002", variant="concept-e-5mm", ms=50)
        self.assertIsNone(self.link.request("READ", {"after_seq": -1}, timeout=0.02))   # connectors open
        time.sleep(0.08)
        self.assertEqual(self.link.request("READ", {"after_seq": -1})["status"], "UNBOUND")
        stale = {"boot_id": hello["boot_id"], "setup_id": hello["setup_id"], "descriptor_sha256": hello["descriptor_sha256"]}
        self.assertEqual(self.link.request("BIND", stale)["status"], "WRONG_BOOT")
        with self.assertRaisesRegex(ValueError, "unique trusted registry"):
            self.link.handshake(registry)                                 # the trusted registry does not know it
        self.assertEqual(self.link.request("READ", {"after_seq": -1})["status"], "UNBOUND")
        hello2, data2, manifest2 = self.link.handshake()
        self.assertEqual(hello2["head_id"], "RRH-SIM-0002")
        self.assertNotEqual(hello2["boot_id"], hello["boot_id"])
        self.assertNotEqual(hello2["descriptor_sha256"], hello["descriptor_sha256"])
        self.assertEqual(json.loads(data2)["bumper_projection_below_window_m"], 0.005)
        self.assertNotEqual(manifest2["attachment_session_id"], manifest["attachment_session_id"])


class Determinism(unittest.TestCase):
    def run_once(self, seed):
        sim = Sim(EXE, seed=seed)
        link = Link(sim)
        try:
            hello, _, _ = link.handshake()
            sim.ctl(cmd="rates", alpha=[0.5, 1, 2, 4], beta=[80, 90, 100, 110], ref=60)
            link.ok("ARM", {"span_us": 100000})
            sim.advance(2000 + 100_000 * 30)
            raw = []
            after = -1
            for _ in range(30):
                rsp = link.request("READ", {"after_seq": after})
                raw.append(link.last_rx)
                after = rsp["body"]["sequence"]
            return hello["boot_id"], b"".join(raw)
        finally:
            link.close()
            self.assertEqual(sim.stop(), 0)

    def test_same_seed_same_bytes(self):
        a = self.run_once(1234)
        b = self.run_once(1234)
        c = self.run_once(1235)
        self.assertEqual(a, b)
        self.assertNotEqual(a[0], c[0])
        self.assertNotEqual(a[1], c[1])


class RealClock(unittest.TestCase):
    def test_real_time_stream_pty_and_bus_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            pty = Path(tmp) / "head-pty"
            sim = Sim(EXE, "--pty", pty, seed=9, clock="real", gate_range=(10000, 1000000))
            link = Link(sim)
            try:
                hello, _, manifest = link.handshake()
                reader = check_frames.AttachedReader(manifest)
                h0 = time.monotonic_ns()
                t = link.ok("TIME")
                h3 = time.monotonic_ns()
                self.assertGreaterEqual(t["tx_us"], t["rx_us"])
                offset_us = (h0 + h3) / 2000 - (t["rx_us"] + t["tx_us"]) / 2
                link.ok("SYNC", {"sync_id": "fit-01", "bound_us": int((h3 - h0) / 2000) + 100, "expiry_us": 10_000_000})
                sim.ctl(cmd="rates", alpha=[0.5, 1, 2, 4], beta=80, ref=60)
                link.ok("ARM", {"span_us": 100000})
                tx0, rx0 = link.tx_bytes, link.rx_bytes
                t_start = time.monotonic()
                got, after, polls = [], -1, 0
                while len(got) < 12 and time.monotonic() - t_start < 5.0:
                    rsp = link.request("READ", {"after_seq": after})
                    polls += 1
                    if rsp["status"] == "OK":
                        saved, eligible, notices = reader.capture_read(rsp, rsp["id"], ACQ, 10000)
                        got.append(saved["frame"])
                        after = saved["frame"]["sequence"]
                        self.assertEqual((eligible, notices), ([0, 1, 2, 3], []))
                    else:
                        self.assertEqual(rsp["status"], "EMPTY")
                        time.sleep(0.02)                                  # 50 Hz poll like the host driver
                elapsed = time.monotonic() - t_start
                self.assertEqual(len(got), 12)
                self.assertAlmostEqual(elapsed, 1.2, delta=0.35)          # gates arrive at the wall-clock rate
                # frame start times map onto the host clock through the TIME exchange
                host_now_us = time.monotonic_ns() / 1000
                self.assertLess(abs(got[-1]["start_us"] + offset_us + 100000 - host_now_us), 300_000)
                wire_bytes = (link.tx_bytes - tx0) + (link.rx_bytes - rx0)
                RESULTS["real_clock_poll"] = {"gates": 12, "polls": polls, "elapsed_s": round(elapsed, 3),
                                              "wire_bytes": wire_bytes,
                                              "bus_load_pct_at_1Mbaud": round(wire_bytes * 10e-6 / elapsed * 100, 2)}
                # the PTY carries the same byte stream
                fd = os.open(os.path.realpath(pty), os.O_RDWR | os.O_NOCTTY)
                try:
                    import termios
                    import tty
                    tty.setraw(fd, termios.TCSANOW)
                    os.write(fd, wire_codec.encode({"type": "REQ", "v": "2.0", "id": 5000, "op": "STATUS", "args": {}}))
                    buf = b""
                    deadline = time.monotonic() + 2
                    while not buf.endswith(b"\n") and time.monotonic() < deadline:
                        buf += os.read(fd, 4096)
                    status = wire_codec.decode(buf)
                    self.assertEqual((status["id"], status["body"]["link"]), (5000, "BOUND"))
                finally:
                    os.close(fd)
                # the wire carries nothing unsolicited: one reply per request
                self.assertIsNone(link.recv_line(timeout=0.25))
            finally:
                link.close()
                self.assertEqual(sim.stop(), 0)
            self.assertFalse(pty.is_symlink())                             # removed on clean shutdown


def tearDownModule():
    out = os.environ.get("RRH_TEST_RESULTS")
    if out:
        Path(out).write_text(json.dumps(RESULTS, indent=2, sort_keys=True) + "\n")
    if RESULTS:
        print("measured on the emulator:", json.dumps(RESULTS, sort_keys=True), file=sys.stderr)


if __name__ == "__main__":
    EXE = Path(sys.argv.pop(1)).resolve()
    unittest.main(verbosity=2)
