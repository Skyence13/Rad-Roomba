"""Sessions, roles, the single control lease, idempotent command receipts and the
audit log of the operator interface (software/Operator_Interface.md "Access and
command authority"; RQ-041, VT-028).  ROS-free and clock-injected.

  * roles: viewer (read only), operator (mission commands), rp (profiles, disposition)
  * many sessions may view; exactly ONE session holds the control lease; take and
    release are explicit and visible to everyone; a take-over of a held lease needs
    `force` and is audited; the lease expires when its holder stops sending heartbeats
  * every command carries an idempotency key; a repeated key returns the stored
    receipt and is never executed twice
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

ROLE_RANK = {"viewer": 0, "operator": 1, "rp": 1}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 60_000).hex()


def check_password(password: str, stored: str) -> bool:
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


class ControlCenter:
    def __init__(self, clock, users: dict, session_ttl_s=3600.0, lease_ttl_s=5.0, token_factory=None,
                 audit_sink=None):
        """users: {name: {"role": viewer|operator|rp, "password_hash": "..."}}"""
        self.clock, self.users = clock, users
        self.session_ttl_us, self.lease_ttl_us = int(session_ttl_s * 1e6), int(lease_ttl_s * 1e6)
        self._token = token_factory or (lambda: secrets.token_urlsafe(24))
        self.sessions = {}            # token -> {user, role, csrf, t_last, t_heartbeat}
        self.lease = None             # {"session": token, "user": name, "since_us": t}
        self.receipts = {}            # idempotency key -> receipt
        self.audit = []
        self.audit_sink = audit_sink
        self._prev_hash = "0" * 64

    # ------------------------------------------------------------------ audit
    def _audit(self, **rec):
        rec = dict(rec, t_us=self.clock.now_us(), n=len(self.audit) + 1, prev=self._prev_hash)
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
        self._prev_hash = rec["hash"]
        self.audit.append(rec)
        if self.audit_sink:
            self.audit_sink(rec)
        return rec

    # --------------------------------------------------------------- sessions
    def login(self, user, password):
        u = self.users.get(user)
        if u is None or not check_password(password, u["password_hash"]):
            self._audit(op="login", user=user, accepted=False)
            return None
        token = self._token()
        now = self.clock.now_us()
        self.sessions[token] = {"user": user, "role": u["role"], "csrf": self._token(), "t_last": now, "t_heartbeat": now}
        self._audit(op="login", user=user, role=u["role"], accepted=True)
        return token

    def session(self, token, touch=True):
        s = self.sessions.get(token)
        if s is None:
            return None
        now = self.clock.now_us()
        if now - s["t_last"] > self.session_ttl_us:
            self.logout(token, why="EXPIRED")
            return None
        if touch:
            s["t_last"] = now
        return s

    def logout(self, token, why="LOGOUT"):
        s = self.sessions.pop(token, None)
        if s and self.lease and self.lease["session"] == token:
            self._drop_lease("HOLDER_" + why)
        if s:
            self._audit(op="logout", user=s["user"], why=why)

    def heartbeat(self, token):
        s = self.session(token)
        if s:
            s["t_heartbeat"] = self.clock.now_us()
        return s is not None

    # ------------------------------------------------------------------ lease
    def _drop_lease(self, why):
        if self.lease:
            self._audit(op="control_lost", user=self.lease["user"], why=why)
        self.lease = None

    def lease_state(self):
        """Current holder; expires a lease whose holder went silent."""
        if self.lease:
            s = self.sessions.get(self.lease["session"])
            if s is None or self.clock.now_us() - s["t_heartbeat"] > self.lease_ttl_us:
                self._drop_lease("HEARTBEAT_LOST")
        return None if not self.lease else {"user": self.lease["user"], "since_us": self.lease["since_us"]}

    def control_ok(self) -> bool:
        return self.lease_state() is not None

    def take_control(self, token, force=False):
        s = self.session(token)
        if s is None:
            return {"accepted": False, "reason": "NOT_LOGGED_IN"}
        if s["role"] != "operator":
            self._audit(op="take_control", user=s["user"], accepted=False, reason="ROLE")
            return {"accepted": False, "reason": "ROLE: only an operator can hold control"}
        holder = self.lease_state()
        if holder and self.lease["session"] != token:
            if not force:
                self._audit(op="take_control", user=s["user"], accepted=False, reason="HELD_BY:" + holder["user"])
                return {"accepted": False, "reason": "HELD", "holder": holder["user"]}
            self._drop_lease("TAKEN_OVER_BY:" + s["user"])
        s["t_heartbeat"] = self.clock.now_us()
        self.lease = {"session": token, "user": s["user"], "since_us": self.clock.now_us()}
        self._audit(op="take_control", user=s["user"], accepted=True, forced=bool(force and holder))
        return {"accepted": True, "holder": s["user"]}

    def release_control(self, token):
        if self.lease and self.lease["session"] == token:
            self._drop_lease("RELEASED")
            return {"accepted": True}
        return {"accepted": False, "reason": "NOT_HOLDER"}

    # --------------------------------------------------------------- commands
    def submit(self, token, key, name, args, execute, needs_control=True, needs_role=None, csrf=None):
        """Role/lease check, exactly-once execution, receipt and audit."""
        s = self.session(token)
        if s is None:
            return {"accepted": False, "reason": "NOT_LOGGED_IN"}, 401
        if csrf is not None and not hmac.compare_digest(csrf, s["csrf"]):
            self._audit(op="command", command=name, user=s["user"], accepted=False, reason="CSRF")
            return {"accepted": False, "reason": "CSRF"}, 403
        if not key or not isinstance(key, str) or len(key) > 80:
            return {"accepted": False, "reason": "IDEMPOTENCY_KEY_REQUIRED"}, 400
        if key in self.receipts:
            rec = self.receipts[key]
            if rec["user"] != s["user"] or rec["command"] != name:
                return {"accepted": False, "reason": "KEY_REUSED_FOR_ANOTHER_COMMAND"}, 409
            return dict(rec["result"], receipt=rec["n"], replayed=True), 200      # acknowledged once, not re-executed
        if needs_role and s["role"] != needs_role:
            result = {"accepted": False, "reason": f"ROLE: {needs_role} required"}
        elif needs_control and s["role"] != "operator":
            result = {"accepted": False, "reason": "ROLE: operator required"}
        elif needs_control and not (self.lease_state() and self.lease["session"] == token):
            holder = self.lease_state()
            result = {"accepted": False, "reason": "NO_CONTROL", "holder": holder["user"] if holder else None}
        else:
            s["t_heartbeat"] = self.clock.now_us()
            result = execute(s["user"], s["role"])
        a = self._audit(op="command", command=name, args=args, user=s["user"], role=s["role"], key=key,
                        accepted=bool(result.get("accepted")), reason=result.get("reason"))
        self.receipts[key] = {"n": a["n"], "user": s["user"], "command": name, "result": result}
        while len(self.receipts) > 5000:
            self.receipts.pop(next(iter(self.receipts)))
        return dict(result, receipt=a["n"], replayed=False), 200

    def public_state(self, token=None):
        s = self.sessions.get(token) if token else None
        holder = self.lease_state()
        return {"holder": holder["user"] if holder else None,
                "you": None if s is None else {"user": s["user"], "role": s["role"],
                                               "has_control": bool(self.lease and self.lease["session"] == token)},
                "viewers": sorted({v["user"] for v in self.sessions.values()}),
                "demo_accounts": self.demo_accounts}

    @property
    def demo_accounts(self) -> bool:
        """True when any account is a demonstration account (see rr_bringup.runtime.load_users)."""
        return any(u.get("demo") for u in self.users.values())
