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
