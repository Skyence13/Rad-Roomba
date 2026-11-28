#!/usr/bin/env python3
"""Integration tests: launch rr_chassis_sim and exercise RR-CHS 1.0 over TCP with the environment
socket. Everything observed here is SIMULATED (host plant model).

    python3 test_integration.py /path/to/rr_chassis_sim [-v]
"""
import json
import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rrchs_client import Sim, frame, unframe  # noqa: E402

SIM_BIN = None
SCHEMA = None
OPM = "COMMISSIONING"

try:
    import jsonschema
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "interface", "chassis_link.schema.json")) as f:
        SCHEMA = json.load(f)
except ImportError:  # pragma: no cover
    jsonschema = None


_validators = {}


def _validator(name):
    if name not in _validators:
        _validators[name] = jsonschema.Draft202012Validator({"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": "#/$defs/" + name})
    return _validators[name]


def check_schema(test, op, rsp):
    """Validate a decoded response against interface/chassis_link.schema.json."""
    if jsonschema is None:
        return
    _validator("response").validate(rsp)
    if rsp["status"] == "BUSY":
        return
    _validator("body_" + op if rsp["status"] == "OK" else "error_body").validate(rsp["body"])


class Base(unittest.TestCase):
    speed = 2.0

    def setUp(self):
        self.sim = Sim(SIM_BIN, speed=self.speed, seed=7)
        self.link, self.env = self.sim.link, self.sim.env

    def tearDown(self):
        self.sim.stop()

    # -- helpers --
    def req(self, op, args=None, timeout=1.0):
        status, body = self.link.req(op, args, timeout)
        check_schema(self, op, self.link.last_rsp)
        return status, body

    def ok(self, op, args=None, timeout=1.0):
        status, body = self.req(op, args, timeout)
        self.assertEqual(status, "OK", (op, body))
        return body

    def idle(self, sim_seconds):
        """Wait while keeping the host link alive."""
        end = time.monotonic() + sim_seconds / self.speed
        while time.monotonic() < end:
            self.ok("TIME")
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))

    def wait_mode(self, mode, sim_seconds=3.0):
        end = time.monotonic() + sim_seconds / self.speed
        while True:
            st = self.ok("STATE")
            if st["mode"] == mode:
                return st
            if time.monotonic() > end:
                self.fail("mode %s not reached, still %s (hw %s sw %s)" % (mode, st["mode"], st["hw_inhibit_reasons"], st["protective_stop_reasons"]))
            time.sleep(0.01)

    def wait_rearm_ready(self, timeout=9.0):
        """Stage 3 / round 4 N1: REARM sets K1 only from a charged C_SET (conservative model: about 4-6 s of closed
        chain at 25 C); an operator waits for the
        REARM lamp (rearm_ready). Returns False (no failure) if it does not come, so refusal tests still press."""
        end = time.monotonic() + timeout / self.speed + 1.0
        while time.monotonic() < end:
            if self.ok("STATE").get("rearm_ready"):
                return True
            time.sleep(0.02)
        return False

    def press_rearm(self):
        self.wait_rearm_ready()
        self.env.set(press="REARM")

    def arm(self, op_mode=OPM):
        self.idle(0.4)
        hello = self.ok("HELLO")
        self.ok("SET_OP_MODE", {"op_mode": op_mode})
        self.press_rearm()
        self.wait_mode("ARMED_IDLE")
        bt = self.ok("BRAKE_TEST", timeout=5.0)
        self.assertTrue(bt["passed"], bt)
        self.wait_mode("STANDBY")
        self.press_rearm()
        self.wait_mode("ARMED_IDLE")
        # geometry comes from the chassis, never from literals in the host
        self.track = hello["caps"]["track_nom_m"]
        self.ticks_per_m = hello["caps"]["encoder_cpr"] / (2 * math.pi * hello["caps"]["wheel_radius_nom_m"])
        return hello

    def drive_for(self, v, w, sim_seconds, op_mode=OPM, until=None):
        """Cyclic DRIVE at 50 Hz of simulated time. Returns the list of replies."""
        out = []
        period = 0.02 / self.speed
        nxt = time.monotonic()
        end = nxt + sim_seconds / self.speed
        while time.monotonic() < end:
            r = self.link.drive(v, w, op_mode)
            check_schema(self, "DRIVE", self.link.last_rsp)
            out.append(r)
            if until and until(r):
                break
            nxt += period
            time.sleep(max(0.0, nxt - time.monotonic()))
        return out

    def start_moving(self, v=0.10, w=0.0):
        reps = self.drive_for(v, w, 4.0, until=lambda r: r["motion"] == "RUN" and abs(r["applied"]["v_mps"] - v) < 1e-3 and abs(r["applied"]["w_radps"] - w) < 1e-3)
        self.assertEqual(reps[-1]["mode"], "MOVING", reps[-1])
        return reps

    def events(self, after=0):
        ev = []
        while True:
            b = self.ok("EVENTS", {"after_seq": after})
            ev += b["events"]
            if not b["more"]:
                return ev
            after = ev[-1]["seq"]


class TestProtocol(Base):
    def test_hello_time_and_framing(self):
        self.idle(0.4)
        h = self.ok("HELLO")
        self.assertEqual(h["proto"], "RR-CHS 1.0")
        self.assertEqual(h["caps"]["encoder_cpr"], 9600)
        self.assertEqual(h["reset"]["cause"], "POWER_ON")
        # four-timestamp exchange: offset and bound from 20 samples
        best = None
        for _ in range(20):
            t1 = time.monotonic()
            b = self.ok("TIME")
            t4 = time.monotonic()
            self.assertGreaterEqual(b["tx_us"], b["rx_us"])
            bound = ((t4 - t1) * 1e6 * self.speed - (b["tx_us"] - b["rx_us"])) / 2
            if best is None or bound < best:
                best = bound
        print("\n  SIMULATED over loopback TCP: best TIME half round-trip %.0f us of chassis time (emulator steps 1 ms)" % best, end="")
        self.assertLess(best, 10000 * self.speed)
        # bad CRC and broken JSON: no reply; then a good request still works
        self.link.send_raw(b'{"type":"REQ","v":"1.0","id":900,"op":"TIME","args":{}}\t00000000\n')
        self.link.send_raw(b'{"type":"REQ","v":"1.0","id":901,"op":"TIME","args":{}\t' + b"%08X" % 0 + b"\n")
        with self.assertRaises(TimeoutError):
            self.link.read_record(0.2)
        self.ok("TIME")
        # retry with identical bytes returns the identical cached record
        raw1 = self.link.last_reply_raw
        self.link.send_raw(self.link.last_raw)
        self.assertEqual(self.link.read_record(), raw1)
        # unknown op, wrong version
        self.assertEqual(self.req("FLY")[0], "UNSUPPORTED")
        self.link.send_raw(frame({"type": "REQ", "v": "2.0", "id": 950, "op": "TIME", "args": {}}))
        self.assertEqual(unframe(self.link.read_record())["status"], "UNSUPPORTED")

    def test_every_op(self):
        self.arm()
        st = self.ok("STATE")
        self.assertEqual(len(st["tof"]), 11)
        self.assertTrue(all(st["chain"].values()))
        self.assertTrue(st["stationary"]["is_stationary"])
        d = self.ok("DIAG")
        self.assertEqual(d["brake_test"]["state"], "PASSED")
        self.assertEqual(self.ok("HEAD_POWER", {"electronics": True, "heater_enable": True})["electronics"], True)
        self.assertEqual(self.ok("HEATER", {"chassis_setpoint_c": 12.5})["chassis_setpoint_c"], 12.5)
        self.ok("HEATER", {"chassis_setpoint_c": None})
        self.assertEqual(self.ok("PANEL", {"pattern": "ARRIVED"})["leds"]["ready"], "BLINK_2")
        g = self.ok("CONFIG_GET", {"key": "cal.track_m"})
        self.assertAlmostEqual(g["value"], 0.27)
        keys, off = [], 0
        while True:
            b = self.ok("CONFIG_GET", {"key": "_keys", "offset": off})
            keys += b["keys"]
            off += len(b["keys"])
            if off >= b["total"]:
                break
        self.assertIn("alert.rest_ms", keys)
        self.assertIn("stationary.gyro_max_radps", keys)
        for k in keys:  # every listed key is readable and inside its limits
            g = self.ok("CONFIG_GET", {"key": k})
            self.assertTrue(g["min"] <= g["value"] <= g["max"], g)
        s = self.ok("CONFIG_SET", {"key": "cal.track_m", "value": 0.2715})
        self.assertAlmostEqual(s["old"], 0.27)
        self.assertEqual(self.req("CONFIG_SET", {"key": "cal.track_m", "value": 9})[0], "BAD_ARG")
        r = self.link.drive(0.0, 0.0, OPM)
        self.assertTrue(r["accepted"])
        b = self.ok("STOP", {"kind": "PROTECTIVE", "reason": "LOCALIZATION"})
        self.assertEqual(b["mode"], "PROTECTIVE_STOP")
        self.assertEqual(self.req("REARM_SW", {"nonce": 1, "operator": "x"})[0], "REJECTED")
        status, b = self.link.rearm_sw()
        self.assertEqual((status, b["cleared"], b["mode"]), ("OK", ["LOCALIZATION"], "ARMED_IDLE"))
        self.ok("STOP", {"kind": "CONTROLLED"})
        self.assertEqual(self.wait_mode("HOLD")["hold"], ["HOST_STOP"])
        self.assertEqual(self.link.rearm_sw()[0], "OK")
        ev = self.events()
        kinds = {e["kind"] for e in ev}
        self.assertTrue({"BOOT", "LINK", "OP_MODE", "BUTTON", "HW_LATCH", "MODE", "BRAKE_TEST", "PERMIT", "HEAD_POWER", "CONFIG", "PSTOP", "PSTOP_CLEAR", "HOLD"} <= kinds, kinds)
        self.assertEqual([e["seq"] for e in ev], list(range(1, len(ev) + 1)))
        self.assertTrue(all(a["t_us"] <= b["t_us"] for a, b in zip(ev, ev[1:])))
        self.assertLessEqual(self.link.max_record, 2048)


class TestMotion(Base):
    speed = 1.0

    def test_cyclic_drive_50hz_with_pose_feedback(self):
        self.arm()
        t_first = self.env.latest()
        reps = self.drive_for(0.10, 0.20, 6.0)
        reps += self.drive_for(0.0, 0.0, 1.0)
        acc = [r["accepted"] for r in reps]
        self.assertTrue(all(acc), "rejected: %s" % {r["reject_reason"] for r in reps if not r["accepted"]})
        self.assertEqual(reps[3]["motion"], "ALERT")
        # integrate cumulative ticks exactly as the host bridge will
        x = y = yaw = 0.0
        for a, b in zip(reps, reps[1:]):
            self.assertGreaterEqual(b["odom"]["t_us"], a["odom"]["t_us"])
            dl = (b["odom"]["left_ticks"] - a["odom"]["left_ticks"]) / self.ticks_per_m
            dr = (b["odom"]["right_ticks"] - a["odom"]["right_ticks"]) / self.ticks_per_m
            ds, dth = (dl + dr) / 2, (dr - dl) / self.track
            x += ds * math.cos(yaw + dth / 2)
            y += ds * math.sin(yaw + dth / 2)
            yaw += dth
        time.sleep(0.05)
        truth = self.env.latest()
        gx, gy, gyaw = truth["x"] - t_first["x"], truth["y"] - t_first["y"], truth["yaw"] - t_first["yaw"]
        err = math.hypot(x - gx, y - gy)
        print("\n  SIMULATED 50 Hz DRIVE arc: travelled %.3f m, yaw %.3f rad; tick odometry vs ground truth %.2f mm, %.4f rad" % (math.hypot(gx, gy), gyaw, err * 1000, abs(yaw - gyaw)), end="")
        self.assertGreater(math.hypot(gx, gy), 0.25)
        self.assertLess(err, 0.003)
        self.assertLess(abs(yaw - gyaw), 0.003)
        gz = [r["imu"]["gyro_rps"][2] for r in reps if r["motion"] == "RUN" and abs(r["applied"]["w_radps"] - 0.2) < 1e-6]
        self.assertAlmostEqual(sum(gz) / len(gz), 0.20, delta=0.01)
        self.assertTrue(reps[-1]["stationary"]["is_stationary"])

    def test_bumper_trip_during_motion(self):
        self.arm()
        self.start_moving(0.20)
        x0 = self.env.latest()["x"]
        seq0 = self.ok("STATE")["event_seq"]
        self.env.set(bumper_l=True)
        st = self.wait_mode("HW_INHIBIT", 1.0)
        self.assertIn("BODY_BUMPER", st["hw_inhibit_reasons"])
        self.assertFalse(st["hw_latch"])
        r = self.link.drive(0.2, 0.0, OPM)
        self.assertEqual((r["accepted"], r["reject_reason"], r["stops"]["hw"]), (False, "HW_INHIBIT", ["BODY_BUMPER"]))
        self.idle(0.6)
        truth = self.env.latest()
        self.assertLess(abs(truth["v"]), 1e-3)
        print("\n  SIMULATED bumper trip at 0.20 m/s: stopped %.1f mm after the trip was injected (includes UDP delivery)" % ((truth["x"] - x0) * 1000), end="")
        self.assertLess(truth["x"] - x0, 0.06)
        ev = [e for e in self.events(seq0)]
        self.assertTrue(any(e["kind"] == "CHAIN" and e["detail"] == {"el": "BODY_BUMPER_L", "closed": False} for e in ev))
        self.assertTrue(any(e["kind"] == "HW_LATCH" and e["detail"]["set"] is False and "BODY_BUMPER" in e["detail"]["reasons"] for e in ev))
        # released: stays inhibited; software re-arm cannot set the latch; the local button can
        self.env.set(bumper_l=False)
        self.idle(2.3)  # 2 s of CHAIN_END live is no longer enough (round 4 N1: T11 C_SET model)
        st = self.ok("STATE")
        self.assertEqual((st["mode"], st["rearm_ready"]), ("HW_INHIBIT", False))
        self.assertTrue(self.wait_rearm_ready())
        st = self.ok("STATE")
        self.assertEqual((st["mode"], st["hw_inhibit_reasons"], st["rearm_ready"]), ("HW_INHIBIT", ["BODY_BUMPER"], True))
        status, b = self.link.rearm_sw()
        self.assertEqual((status, b["hw_latch"]), ("OK", False))
        self.assertEqual(self.ok("STATE")["mode"], "HW_INHIBIT")
        self.press_rearm()
        self.wait_mode("ARMED_IDLE")
        x1 = self.env.latest()["x"]
        self.idle(0.8)
        self.assertAlmostEqual(self.env.latest()["x"], x1, delta=1e-4)  # nothing was queued

    def test_s15_stimuli_refused_rearm_and_link_outage(self):
        """What the host scenario s15 (no automatic resumption) drives on rr_chassis_sim: a body-bumper inhibit and
        clear, a local REARM pressed too early (refused and reported, never silent), the realistic re-arm (wait for
        rearm_ready, 250 ms press), and a timed link outage (usb_down_ms: bytes in both directions lost)."""
        self.arm()
        self.start_moving(0.10)
        self.env.set(bumper_l=True)
        self.wait_mode("HW_INHIBIT", 1.0)
        self.idle(1.0)  # chain open 1 s: C_SET discharged (a short opening keeps the charge, stage 4 G8)
        self.env.set(bumper_l=False)
        self.idle(0.5)
        seq0 = self.ok("STATE")["event_seq"]
        self.env.set(press="REARM", press_ms=250)  # too early: SET_READY low, C_SET untouched
        self.idle(0.6)
        st = self.ok("STATE")
        self.assertEqual((st["mode"], st["hw_latch"], st["rearm_ready"], st["rearm_refusal"]), ("HW_INHIBIT", False, False, "NOT_READY"))
        ev = [e for e in self.events(seq0) if e["kind"] == "REARM_REFUSED"]
        self.assertEqual([e["detail"] for e in ev], [{"why": "NOT_READY"}])
        self.assertEqual(self.ok("DIAG")["rearm"]["why"], "NOT_READY")
        self.assertTrue(self.wait_rearm_ready())
        self.env.set(press="REARM", press_ms=250)
        st = self.wait_mode("ARMED_IDLE")
        self.assertIsNone(st["rearm_refusal"])
        x1 = self.env.latest()["x"]
        self.idle(0.5)
        self.assertAlmostEqual(self.env.latest()["x"], x1, delta=1e-4)  # re-armed, but nothing moves without a new DRIVE
        # link outage while moving: HOST_LINK_LOST / CMD_TIMEOUT stop; link back: still stopped until REARM_SW
        self.start_moving(0.10)
        self.env.set(usb_down_ms=1500)
        time.sleep(1.8 / self.speed)
        self.assertLess(abs(self.env.latest()["v"]), 1e-3)
        self.idle(0.3)
        st = self.ok("STATE")
        self.assertEqual(st["mode"], "PROTECTIVE_STOP")
        self.assertTrue({"HOST_LINK_LOST", "CMD_TIMEOUT"} & set(st["protective_stop_reasons"]), st["protective_stop_reasons"])
        x2 = self.env.latest()["x"]
        self.idle(0.5)
        self.assertAlmostEqual(self.env.latest()["x"], x2, delta=1e-4)
        self.ok("HELLO")
        status, b = self.link.rearm_sw()
        self.assertEqual(status, "OK", b)
        self.wait_mode("ARMED_IDLE")

    def test_estop_and_charger_cover(self):
        self.arm()
        self.ok("HEAD_POWER", {"electronics": True, "heater_enable": False})
        self.start_moving(0.10)
        self.env.set(estop=True)
        st = self.wait_mode("HW_INHIBIT", 1.0)
        self.assertEqual(st["hw_inhibit_reasons"], ["ESTOP"])
        self.assertFalse(st["chain"]["ESTOP"])
        self.idle(0.5)
        self.assertLess(abs(self.env.latest()["v"]), 1e-3)
        self.env.set(estop=False)
        self.idle(0.3)  # a REARM pressed before the chain reads closed is refused (review m3)
        self.press_rearm()
        self.wait_mode("ARMED_IDLE")
        # charger cover opened while armed: SERVICE_CHARGE, latch gone, head power forced off, no motion
        self.env.set(chg_cover_open=True)
        self.wait_mode("SERVICE_CHARGE", 1.0)
        self.idle(0.1)  # latch relay release time
        st = self.ok("STATE")
        self.assertEqual((st["hw_latch"], st["chain"]["CHG_COVER"], st["chain"]["ARM_PERMIT"]), (False, False, False))
        self.assertIn("CHARGER", st["hw_inhibit_reasons"])
        self.assertFalse(self.env.latest()["head_pwr"])
        self.assertEqual(self.req("HEAD_POWER", {"electronics": True, "heater_enable": False})[0], "REJECTED")
        self.assertEqual(self.link.drive(0.05, 0, OPM)["reject_reason"], "SERVICE_CHARGE")
        self.press_rearm()
        self.idle(0.4)
        self.assertEqual(self.ok("STATE")["mode"], "SERVICE_CHARGE")
        self.env.set(chg_cover_open=False)
        st = self.wait_mode("HW_INHIBIT", 1.0)
        self.assertEqual(st["hw_inhibit_reasons"], ["CHARGER"])

    def test_chain_nodes_permit_readback_and_look_pairs(self):
        """IB-01 / IB-02 / IB-34 through the protocol: node semantics, CHAIN_END_RB, direction-specific look pairs."""
        self.arm()
        d = self.ok("DIAG")
        self.assertTrue(d["chain_end"])
        self.assertEqual(set(d["chain_state"].values()), {"CLOSED"})
        self.assertEqual(len(d["readbacks"]), 23)
        # reversing with the forward pair blind and a rear-pair sensor fine: no stop
        self.start_moving(-0.05)
        self.env.set(tof={"LOOK_FL": "INVALID"})
        reps = self.drive_for(-0.05, 0.0, 0.6)
        self.assertEqual((reps[-1]["mode"], reps[-1]["stops"]["sw"]), ("MOVING", []))
        # the tail pair in the direction of travel stops it, reason by side
        self.env.set(tof={"LOOK_RR": None})
        reps = self.drive_for(-0.05, 0.0, 6.0, until=lambda r: r["mode"] == "PROTECTIVE_STOP")
        self.assertIn("LOOKAHEAD_R", reps[-1]["stops"]["sw"])
        self.env.set(tof={"LOOK_FL": 524, "LOOK_RR": 267})
        self.idle(0.5)
        status, b = self.link.rearm_sw()
        self.assertEqual((status, b["mode"]), ("OK", "ARMED_IDLE"))
        # selector to SERVICE: everything behind it is UNKNOWN, only MODE_NOT_RUN is a reason
        self.env.set(mode_run=False)
        st = self.wait_mode("HW_INHIBIT", 1.0)
        self.assertEqual(st["hw_inhibit_reasons"], ["MODE_NOT_RUN"])
        d = self.ok("DIAG")
        self.assertEqual((d["chain_state"]["MODE_RUN"], d["chain_state"]["HANDS_ON"], d["chain_state"]["HEAD_LOOP"]), ("OPEN", "UNKNOWN", "CLOSED"))
        self.assertNotIn("ESTOP_DISCREPANCY", d["faults"])
        self.env.set(mode_run=True)
        self.idle(0.3)
        # ARM_PERMIT element that does not close: warning, no re-arm possible
        self.env.set(permit_open=True)
        self.idle(0.3)
        st = self.ok("STATE")
        self.assertIn("PERMIT_STUCK_OFF", st["faults"])
        self.assertEqual((st["chain"]["ARM_PERMIT"], st["rearm_ready"]), (False, False))
        self.press_rearm()
        self.idle(0.3)
        self.assertFalse(self.env.latest()["latch"])
        self.env.set(permit_open=False)
        self.idle(0.3)
        self.assertNotIn("PERMIT_STUCK_OFF", self.ok("STATE")["faults"])

    def test_link_stall_stops_within_ttl(self):
        self.arm()
        self.start_moving(0.20)
        self.link.drive(0.20, 0.0, OPM, ttl_ms=200)
        t0 = time.monotonic()
        self.env.set(usb_stall=True)  # the host side of the link freezes
        stopped_after = None
        while time.monotonic() - t0 < 2.0:
            tr = self.env.latest(0.05)
            if abs(tr["v"]) < 1e-3:
                stopped_after = time.monotonic() - t0
                break
        self.assertIsNotNone(stopped_after, "robot kept moving with a stalled link")
        print("\n  SIMULATED link stall at 0.20 m/s (ttl 200 ms): at rest %.0f ms after the stall" % (stopped_after * 1000), end="")
        self.assertLess(stopped_after, 0.2 + 0.2 + 0.35)  # ttl + protective ramp + margin for scheduling
        self.env.set(usb_stall=False)
        st = self.ok("STATE")
        self.assertEqual(st["mode"], "PROTECTIVE_STOP")
        self.assertIn("CMD_TIMEOUT", st["protective_stop_reasons"])
        r = self.link.drive(0.2, 0.0, OPM)
        self.assertEqual((r["accepted"], r["reject_reason"]), (False, "PROTECTIVE_STOP"))
        self.idle(0.5)
        self.assertEqual(self.ok("STATE")["mode"], "PROTECTIVE_STOP")  # link recovery does not re-arm
        status, b = self.link.rearm_sw()
        self.assertEqual(status, "OK")
        self.assertIn("CMD_TIMEOUT", b["cleared"])
        self.wait_mode("ARMED_IDLE")

    def test_mcu_reset_mid_motion(self):
        hello0 = self.arm()
        self.start_moving(0.20)
        x0 = self.env.latest()["x"]
        self.env.set(mcu_reset="WATCHDOG")
        time.sleep(0.6)
        truth = self.env.latest()
        self.assertLess(abs(truth["v"]), 1e-3)
        self.assertFalse(truth["latch"])
        self.assertLess(truth["x"] - x0, 0.06)
        self.link.buf = b""
        r = self.link.drive(0.2, 0.0, OPM)
        self.assertEqual((r["accepted"], r["reject_reason"]), (False, "NO_SESSION"))
        hello1 = self.ok("HELLO")
        self.assertNotEqual(hello1["boot_id"], hello0["boot_id"])
        self.assertEqual(hello1["reset"]["cause"], "WATCHDOG")
        self.assertEqual(hello1["reset"]["boot_count"], hello0["reset"]["boot_count"] + 1)
        self.assertLess(hello1["uptime_us"], 2_000_000)
        st = self.ok("STATE")
        self.assertIn(st["mode"], ("STANDBY", "HW_INHIBIT"))
        self.assertFalse(st["hw_latch"])
        self.assertEqual(st["op_mode"], "SERVICE")
        ev = self.events()
        self.assertEqual((ev[0]["kind"], ev[0]["detail"]["prev_mode"]), ("BOOT", "MOVING"))
        self.assertEqual(self.link.drive(0.1, 0.0, OPM)["reject_reason"], "STANDBY")

    def test_step_and_count(self):
        self.arm()
        alerts = 0
        for hop in range(3):
            x0 = self.env.latest()["x"]
            reps = self.drive_for(0.10, 0.0, 4.0, until=lambda r: r["odom"]["left_ticks"] / self.ticks_per_m >= 0.1 * (hop + 1) - 0.006)
            alerts += any(r["motion"] == "ALERT" for r in reps)
            self.drive_for(0.0, 0.0, 0.7)
            a = self.link.drive(0.0, 0.0, OPM)
            self.assertTrue(a["stationary"]["is_stationary"])
            self.drive_for(0.0, 0.0, 1.5)  # the "count"
            b = self.link.drive(0.0, 0.0, OPM)
            self.assertEqual(b["stationary"], a["stationary"])
            self.assertEqual(b["event_seq"], a["event_seq"])
            self.assertAlmostEqual(self.env.latest()["x"] - x0, 0.10, delta=0.015)
        self.assertEqual(alerts, 1)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        print(__doc__)
        sys.exit(2)
    SIM_BIN = sys.argv.pop(1)
    if jsonschema is None:
        print("NOTE: python 'jsonschema' not installed - schema validation skipped")
    unittest.main(verbosity=2)
