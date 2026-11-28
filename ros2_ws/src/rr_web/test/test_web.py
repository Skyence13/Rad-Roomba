"""Operator web service: roles, single control lease, exactly-once commands, SSE, service mode.
Traces: RQ-041, RQ-042; VT-028 (tool-checked on a fake backend; real time)."""
import asyncio, json, threading
import pytest
from aiohttp.test_utils import TestClient, TestServer
from rr_core.transport import Clock
from rr_web.control import ControlCenter, hash_password
from rr_web.server import make_app


class FakeBackend:
    def __init__(self):
        self.lock = threading.Lock()
        self.executed = []
        self.mode = "ARMED_IDLE"

    def snapshot(self):
        return {"mission": {"state": "REVIEW"}, "chassis": {"mode": self.mode}, "n_exec": len(self.executed)}

    def map_layers(self):
        return {"cells": []}

    def command(self, name, args, actor, role):
        if self.mode == "SERVICE_CHARGE" and name in ("next", "start", "resume", "expose", "park", "arm"):
            return {"accepted": False, "reason": "CHARGE_SERVICE: traction inhibited"}
        self.executed.append((name, actor))
        return {"accepted": True, "n": len(self.executed)}

    def export_dir(self):
        return None

    def profiles_view(self):
        return {"profiles": []}

    def profile_edit(self, args, user, role):
        self.executed.append(("profile_edit", user))
        return {"accepted": True, "revision": 2}


USERS = {"op1": {"role": "operator", "password_hash": hash_password("pw1", "a")},
         "op2": {"role": "operator", "password_hash": hash_password("pw2", "b")},
         "view": {"role": "viewer", "password_hash": hash_password("pw3", "c")},
         "rp": {"role": "rp", "password_hash": hash_password("pw4", "d")}}


async def client(backend, cc):
    c = TestClient(TestServer(make_app(backend, cc, sse_period_s=0.05)))
    await c.start_server()
    return c


async def login(c, user, pw):
    r = await c.post("/api/login", json={"user": user, "password": pw})
    assert r.status == 200
    return {"X-CSRF": (await r.json())["csrf"]}


def test_roles_lease_idempotency_and_service_mode():
    async def go():
        be, cc = FakeBackend(), ControlCenter(Clock(), USERS, lease_ttl_s=0.6)
        a, b, v, rp = [await client(be, cc) for _ in range(4)]
        assert (await a.get("/api/state")).status == 401
        assert (await a.post("/api/login", json={"user": "op1", "password": "bad"})).status == 401
        ha, hb, hv, hr = await login(a, "op1", "pw1"), await login(b, "op2", "pw2"), await login(v, "view", "pw3"), await login(rp, "rp", "pw4")
        # nobody holds control: commands are refused
        r = await (await a.post("/api/command", json={"id": "k0", "name": "next"}, headers=ha)).json()
        assert not r["accepted"] and r["reason"] == "NO_CONTROL"
        assert (await (await v.post("/api/control", json={"action": "take"}, headers=hv)).json())["reason"].startswith("ROLE")
        assert (await (await a.post("/api/control", json={"action": "take"}, headers=ha)).json())["accepted"]
        r = await (await b.post("/api/control", json={"action": "take"}, headers=hb)).json()
        assert not r["accepted"] and r["holder"] == "op1"                 # no silent takeover
        r = await (await b.post("/api/command", json={"id": "kb", "name": "next"}, headers=hb)).json()
        assert not r["accepted"] and r["holder"] == "op1"
        r = await (await v.post("/api/command", json={"id": "kv", "name": "next"}, headers=hv)).json()
        assert not r["accepted"] and r["reason"].startswith("ROLE")
        # exactly-once: the same id twice executes once and returns the same receipt
        r1 = await (await a.post("/api/command", json={"id": "k1", "name": "next"}, headers=ha)).json()
        r2 = await (await a.post("/api/command", json={"id": "k1", "name": "next"}, headers=ha)).json()
        assert r1["accepted"] and r2["replayed"] and r2["receipt"] == r1["receipt"] and len(be.executed) == 1
        assert (await a.post("/api/command", json={"id": "k1", "name": "park"}, headers=ha)).status == 409
        assert (await a.post("/api/command", json={"name": "next"}, headers=ha)).status == 400
        assert (await a.post("/api/command", json={"id": "k2", "name": "next"}, headers={"X-CSRF": "wrong"})).status == 403
        # visible ownership for every client
        st = await (await v.get("/api/state")).json()
        assert st["control"]["holder"] == "op1" and st["control"]["you"]["has_control"] is False
        # explicit takeover is possible, recorded, and removes the first operator's authority
        assert (await (await b.post("/api/control", json={"action": "take", "force": True}, headers=hb)).json())["accepted"]
        r = await (await a.post("/api/command", json={"id": "k3", "name": "next"}, headers=ha)).json()
        assert not r["accepted"] and r["holder"] == "op2"
        assert any(x["op"] == "control_lost" and "TAKEN_OVER_BY:op2" in x["why"] for x in cc.audit)
        # Charge/Service: motion refused server-side, export and RP settings still work
        be.mode = "SERVICE_CHARGE"
        r = await (await b.post("/api/command", json={"id": "k4", "name": "start"}, headers=hb)).json()
        assert not r["accepted"] and "CHARGE_SERVICE" in r["reason"]
        assert (await (await b.post("/api/command", json={"id": "k5", "name": "export"}, headers=hb)).json())["accepted"]
        r = await (await b.post("/api/command", json={"id": "k6", "name": "profile_edit", "args": {}}, headers=hb)).json()
        assert not r["accepted"] and r["reason"].startswith("ROLE")
        assert (await (await rp.post("/api/command", json={"id": "k7", "name": "profile_edit", "args": {}}, headers=hr)).json())["accepted"]
        # lease expires when the holder goes silent (no event stream, no heartbeat)
        await asyncio.sleep(0.8)
        assert (await (await v.get("/api/state")).json())["control"]["holder"] is None
        assert (await v.get("/api/audit")).status == 403
        au = (await (await b.get("/api/audit")).json())["audit"]
        assert all(au[i]["prev"] == au[i - 1]["hash"] for i in range(1, len(au))) and any(not x.get("accepted", True) for x in au)
        for c in (a, b, v, rp):
            await c.close()
    asyncio.run(go())


def test_sse_first_event_is_current_state_and_stream_keeps_lease():
    async def go():
        be, cc = FakeBackend(), ControlCenter(Clock(), USERS, lease_ttl_s=0.4)
        a = await client(be, cc)
        ha = await login(a, "op1", "pw1")
        await a.post("/api/control", json={"action": "take"}, headers=ha)
        await a.post("/api/command", json={"id": "x1", "name": "next"}, headers=ha)
        resp = await a.get("/api/events")
        first = b""
        while b"\n\n" not in first:
            first += await resp.content.read(256)
        data = json.loads(first.split(b"data: ", 1)[1].split(b"\n")[0])
        assert data["n_exec"] == 1 and data["control"]["holder"] == "op1"     # reconnect-to-current-state
        await asyncio.sleep(0.7)
        while True:                                   # keep draining so the server keeps writing
            chunk = await asyncio.wait_for(resp.content.read(4096), 1.0)
            if chunk:
                break
        assert cc.lease_state() is not None           # the open stream is the heartbeat
        resp.close()
        await asyncio.sleep(0.8)
        assert cc.lease_state() is None               # stream closed -> lease lost
        await a.close()
    asyncio.run(go())


class NaiveBackend(FakeBackend):
    """Executes everything it is given: proves the refusals below come from the web layer."""

    def __init__(self):
        super().__init__()
        self.safety = {"traction_inhibited": False, "charge_service": False, "hw_inhibit_reasons": [], "protective_stop_reasons": []}

    def snapshot(self):
        return dict(super().snapshot(), safety=dict(self.safety))

    def command(self, name, args, actor, role):
        self.executed.append((name, actor))
        return {"accepted": True, "n": len(self.executed)}


def test_web_refuses_motion_in_charge_service_and_while_inhibited():
    """Server-side interlock independent of the backend (security hygiene; RQ-041, VT-028)."""
    async def go():
        be, cc = NaiveBackend(), ControlCenter(Clock(), USERS, lease_ttl_s=30)
        a = await client(be, cc)
        ha = await login(a, "op1", "pw1")
        assert (await (await a.post("/api/control", json={"action": "take"}, headers=ha)).json())["accepted"]
        n = iter(range(1000))

        async def cmd(name):
            return await (await a.post("/api/command", json={"id": f"c{next(n)}", "name": name}, headers=ha)).json()
        assert (await cmd("next"))["accepted"]                      # permitted state: passes through
        # Charge/Service: every drive request refused by the web service, nothing reaches the backend
        be.mode, be.safety["charge_service"], be.safety["traction_inhibited"] = "SERVICE_CHARGE", True, True
        before = len(be.executed)
        for name in ("start", "resume", "next", "expose", "park", "repeat", "arm", "preflight"):
            r = await cmd(name)
            assert not r["accepted"] and r["reason"].startswith("CHARGE_SERVICE") and r["refused_by"] == "web", (name, r)
        assert len(be.executed) == before
        assert (await cmd("export"))["accepted"] and (await cmd("pause"))["accepted"]   # data access / stop still allowed
        # hardware inhibit (e.g. E-stop): motion refused, re-arm/pause/abort still reach the backend
        be.mode = "HW_INHIBIT"
        be.safety.update(charge_service=False, traction_inhibited=True, hw_inhibit_reasons=["ESTOP"])
        before = len(be.executed)
        for name in ("start", "resume", "next", "expose", "park", "repeat"):
            r = await cmd(name)
            assert not r["accepted"] and r["reason"].startswith("INHIBITED") and "ESTOP" in r["reason"], (name, r)
        assert len(be.executed) == before
        assert (await cmd("rearm"))["accepted"] and (await cmd("abort"))["accepted"]
        # software protective stop: same refusal until the cause is cleared
        be.mode = "PROTECTIVE_STOP"
        be.safety.update(hw_inhibit_reasons=[], protective_stop_reasons=["FIELD_FRONT"])
        r = await cmd("resume")
        assert not r["accepted"] and "FIELD_FRONT" in r["reason"]
        be.mode = "ARMED_IDLE"
        be.safety.update(traction_inhibited=False, protective_stop_reasons=[])
        assert (await cmd("resume"))["accepted"]
        au = cc.audit
        assert sum(1 for x in au if x["op"] == "command" and x.get("reason", "") and str(x["reason"]).startswith(("CHARGE_SERVICE", "INHIBITED"))) >= 15
        await a.close()
    asyncio.run(go())


def test_demo_accounts_are_marked_and_warned(capsys):
    """The packaged accounts are flagged demo, a start-up warning is printed, and every client sees it."""
    from rr_bringup.runtime import load_users
    users = load_users()
    err = capsys.readouterr().err
    assert "DEMONSTRATION ACCOUNTS" in err and "TLS" in err
    assert users and all(u["demo"] for u in users.values())
    cc = ControlCenter(Clock(), users)
    assert cc.public_state()["demo_accounts"] is True
    assert ControlCenter(Clock(), USERS).public_state()["demo_accounts"] is False

    async def go():
        c = await client(FakeBackend(), cc)
        r = await (await c.post("/api/login", json={"user": "viewer", "password": "viewer"})).json()
        assert r["demo_account"] is True
        assert (await (await c.get("/api/state")).json())["control"]["demo_accounts"] is True
        await c.close()
    asyncio.run(go())
