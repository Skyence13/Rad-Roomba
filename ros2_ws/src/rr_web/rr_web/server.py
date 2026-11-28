"""Operator interface served from the robot (aiohttp; local assets only).

  GET  /                      single-page UI (static files from this package)
  POST /api/login|logout      named accounts, roles viewer / operator / rp
  GET  /api/state             current state (any logged-in role)
  GET  /api/map               live plan-view layers
  GET  /api/events            server-sent events; the first event is the full current
                              state, so a reconnecting page never acts on a stale one
  POST /api/control           explicit take / release of the single control lease
  POST /api/command           {id, name, args}: role + lease + interlock checks, executed
                              exactly once per id, receipt returned on every retry
  GET  /api/audit             accepted and rejected operations (hash-chained)
  GET  /api/export/...        files of the last export

Motion commands are refused server-side (not merely hidden) without the lease,
for viewers, in Charge/Service and while traction is inhibited (`interlock_refusal`,
evaluated by this service from the backend state, in addition to the backend's own checks).  The backend is any object with
`lock`, `snapshot()`, `map_layers()`, `command(name, args, actor, role)`,
`export_dir()`, `profile_edit(...)`, `profiles_view()`.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp import web

from .control import ControlCenter

STATIC = Path(__file__).with_name("static")
COOKIE = "rr_session"
CONTROL_COMMANDS = ("preflight", "arm", "start", "pause", "rearm", "resume", "defer", "abort", "end",
                    "next", "expose", "park", "repeat", "skip", "register_datum", "head_power", "rehandshake")
OPEN_COMMANDS = ("export",)                 # operator or rp, no lease needed (also in Charge/Service)
RP_COMMANDS = ("profile_edit",)
# Commands that put the wheels in motion (directly or by resuming a task).  The web layer refuses
# them itself from the backend's reported state, independent of the checks in the backend.
MOTION_COMMANDS = ("start", "resume", "next", "expose", "park", "repeat")
CHARGE_REFUSED = MOTION_COMMANDS + ("preflight", "arm")      # brake test / arming are traction too
TRACTION_PERMITTED_MODES = ("ARMED_IDLE", "MOVING")


def interlock_refusal(name, snap):
    """Reason string when the web service must refuse `name` given the backend snapshot, else None.

    * Charge/Service (chassis mode SERVICE_CHARGE or safety.charge_service): no drive request at all.
    * Traction inhibited (chassis mode not ARMED_IDLE/MOVING, unknown mode, or a hardware inhibit
      reason present): no motion command; the operator clears the cause (local REARM, software
      re-arm) and the page then shows traction permitted again.  Nothing is queued."""
    ch, sf = snap.get("chassis") or {}, snap.get("safety") or {}
    mode = ch.get("mode")
    if name in CHARGE_REFUSED and (mode == "SERVICE_CHARGE" or sf.get("charge_service")):
        return "CHARGE_SERVICE: drive requests are refused while the charger is connected"
    if name in MOTION_COMMANDS:
        if mode not in TRACTION_PERMITTED_MODES or sf.get("hw_inhibit_reasons") or sf.get("traction_inhibited"):
            why = ",".join(list(sf.get("hw_inhibit_reasons") or []) + list(sf.get("protective_stop_reasons") or []))
            return f"INHIBITED: traction not permitted (chassis mode {mode}{': ' + why if why else ''})"
    return None


def make_app(backend, cc: ControlCenter, sim_hooks=None, sse_period_s=0.5) -> web.Application:
    app = web.Application()

    def token(req):
        return req.cookies.get(COOKIE)

    def need(req):
        s = cc.session(token(req))
        if s is None:
            raise web.HTTPUnauthorized(text=json.dumps({"reason": "NOT_LOGGED_IN"}), content_type="application/json")
        return s

    def state_for(tok):
        with backend.lock:
            snap = backend.snapshot()
        snap["control"] = cc.public_state(tok)
        return snap

    async def index(req):
        return web.FileResponse(STATIC / "index.html")

    async def login(req):
        body = await req.json()
        tok = cc.login(str(body.get("user", "")), str(body.get("password", "")))
        if tok is None:
            return web.json_response({"ok": False, "reason": "BAD_CREDENTIALS"}, status=401)
        s = cc.sessions[tok]
        resp = web.json_response({"ok": True, "user": s["user"], "role": s["role"], "csrf": s["csrf"],
                                  "demo_account": bool(cc.users.get(s["user"], {}).get("demo"))})
        resp.set_cookie(COOKIE, tok, httponly=True, samesite="Strict", max_age=int(cc.session_ttl_us / 1e6))
        return resp

    async def logout(req):
        cc.logout(token(req))
        resp = web.json_response({"ok": True})
        resp.del_cookie(COOKIE)
        return resp

    async def whoami(req):
        s = need(req)
        return web.json_response({"user": s["user"], "role": s["role"], "csrf": s["csrf"]})

    async def state(req):
        need(req)
        return web.json_response(state_for(token(req)))

    async def map_layers(req):
        need(req)
        with backend.lock:
            return web.json_response(backend.map_layers())

    async def events(req):
        need(req)
        tok = token(req)
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store",
                                           "X-Accel-Buffering": "no"})
        await resp.prepare(req)
        n = 0
        try:
            while True:
                if cc.session(tok, touch=False) is None:
                    await resp.write(b"event: logout\ndata: {}\n\n")
                    break
                cc.heartbeat(tok)             # an open event stream keeps this session's lease alive
                n += 1
                await resp.write(f"id: {n}\nevent: state\ndata: {json.dumps(state_for(tok))}\n\n".encode())
                await asyncio.sleep(sse_period_s)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        return resp

    async def heartbeat(req):
        return web.json_response({"ok": cc.heartbeat(token(req))})

    async def control(req):
        need(req)
        body = await req.json()
        if req.headers.get("X-CSRF") != cc.sessions[token(req)]["csrf"]:
            return web.json_response({"accepted": False, "reason": "CSRF"}, status=403)
        if body.get("action") == "take":
            out = cc.take_control(token(req), force=bool(body.get("force")))
        else:
            out = cc.release_control(token(req))
        return web.json_response(out)

    async def command(req):
        need(req)
        body = await req.json()
        name, args, key = body.get("name"), body.get("args") or {}, body.get("id")
        if name in CONTROL_COMMANDS:
            kw = {"needs_control": True}
        elif name in OPEN_COMMANDS:
            kw = {"needs_control": False}
        elif name in RP_COMMANDS:
            kw = {"needs_control": False, "needs_role": "rp"}
        else:
            return web.json_response({"accepted": False, "reason": "UNKNOWN_COMMAND"}, status=400)

        def execute(user, role):
            with backend.lock:
                if role == "viewer":
                    return {"accepted": False, "reason": "ROLE: viewers are read-only"}
                if name == "profile_edit":
                    return backend.profile_edit(args, user, role)
                refusal = interlock_refusal(name, backend.snapshot()) if name in CHARGE_REFUSED else None
                if refusal:
                    return {"accepted": False, "reason": refusal, "refused_by": "web"}
                return backend.command(name, args, user, role)
        result, status = cc.submit(token(req), key, name, args, execute, csrf=req.headers.get("X-CSRF", ""), **kw)
        return web.json_response(result, status=status)

    async def audit(req):
        s = need(req)
        if s["role"] == "viewer":
            return web.json_response({"reason": "ROLE"}, status=403)
        return web.json_response({"audit": cc.audit[-300:]})

    async def settings(req):
        need(req)
        with backend.lock:
            return web.json_response(backend.profiles_view())

    async def export_file(req):
        need(req)
        root = backend.export_dir()
        if root is None:
            return web.json_response({"reason": "NO_EXPORT"}, status=404)
        rel = req.match_info.get("path", "")
        path = (Path(root) / rel).resolve()
        if not str(path).startswith(str(Path(root).resolve())) or not path.is_file():
            return web.json_response({"files": sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file())})
        return web.FileResponse(path)

    async def sim(req):
        need(req)
        if sim_hooks is None:
            return web.json_response({"reason": "NOT_A_SIMULATION"}, status=404)
        body = await req.json()
        with backend.lock:
            return web.json_response(sim_hooks(body))

    app.add_routes([web.get("/", index), web.post("/api/login", login), web.post("/api/logout", logout),
                    web.get("/api/whoami", whoami), web.get("/api/state", state), web.get("/api/map", map_layers),
                    web.get("/api/events", events), web.post("/api/heartbeat", heartbeat),
                    web.post("/api/control", control), web.post("/api/command", command),
                    web.get("/api/audit", audit), web.get("/api/settings", settings),
                    web.get("/api/export/{path:.*}", export_file), web.post("/api/sim", sim),
                    web.static("/static", STATIC)])
    return app


class AppBackend:
    """Adapter from a RobotApp to the web server."""

    def __init__(self, robot_app, lock):
        self.app, self.lock = robot_app, lock
        self._export = None

    def snapshot(self):
        return self.app.snapshot()

    def map_layers(self):
        return self.app.map_layers()

    def command(self, name, args, actor, role):
        out = self.app.command(name, args, actor, role)
        if name == "export" and out.get("accepted"):
            self._export = out["dir"]
        return out

    def export_dir(self):
        return self._export

    def profiles_view(self):
        store = self.app.profiles
        return {"unit": "Bq/cm2", "accepted_entry_units": ["Bq/cm2", "Bq/m2"],
                "profiles": [dict(p, configured=not store.missing_for_decision(p),
                                  missing=store.missing_for_decision(p)) for p in store.document["profiles"]],
                "mission_snapshot": {"id": self.app.profile["id"], "revision": self.app.profile.get("revision")},
                "calibration": self.app.calibration.summary(), "history_revisions": len(store.history)}

    def profile_edit(self, args, user, role):
        from rr_core.profiles import ProfileError
        active = self.app.mission is not None and self.app.mission.state in ("SCAN", "HOLD", "ARMED")
        try:
            p = self.app.profiles.edit(args.get("profile"), args.get("changes") or {}, user, role,
                                       mission_active=active, unit=args.get("unit"))
        except ProfileError as err:
            return {"accepted": False, "reason": str(err)}
        return {"accepted": True, "revision": p["revision"]}
