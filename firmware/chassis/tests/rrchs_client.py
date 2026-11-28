"""Minimal RR-CHS 1.0 host client and emulator launcher (test and bring-up aid).

Usage as a module: see tests/test_integration.py. Usage as a tool:
    python3 rrchs_client.py [--host 127.0.0.1] [--port 5550] STATE
    python3 rrchs_client.py DRIVE '{"seq":1,"v_mps":0,"w_radps":0,"ttl_ms":200,"op_mode":"SERVICE"}'
"""
import json
import os
import socket
import subprocess
import sys
import time
import zlib


def frame(obj) -> bytes:
    js = json.dumps(obj, separators=(",", ":")).encode()
    return js + b"\t" + b"%08X" % (zlib.crc32(js) & 0xFFFFFFFF) + b"\n"


def unframe(line: bytes):
    if not line.endswith(b"\n") or line.count(b"\t") != 1:
        raise ValueError("bad record delimiters")
    js, crc = line[:-1].split(b"\t")
    if len(crc) != 8 or int(crc, 16) != (zlib.crc32(js) & 0xFFFFFFFF) or crc != crc.upper():
        raise ValueError("bad CRC")
    return json.loads(js)


class Link:
    """One transaction at a time over TCP (emulator) - a serial port object with read/write works the same way."""

    def __init__(self, host="127.0.0.1", port=5550, timeout=1.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b""
        self.next_id = 1
        self.seq = 1
        self.last_raw = b""
        self.max_record = 0

    def close(self):
        self.sock.close()

    def send_raw(self, data: bytes):
        self.sock.sendall(data)

    def read_record(self, timeout=1.0) -> bytes:
        end = time.monotonic() + timeout
        while b"\n" not in self.buf:
            self.sock.settimeout(max(0.001, end - time.monotonic()))
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                raise TimeoutError("no reply")
            if not chunk:
                raise ConnectionError("link closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line + b"\n"

    def req(self, op, args=None, timeout=1.0, rid=None):
        """Returns (status, body). Raises on framing errors or a mismatched id."""
        rid = self.next_id if rid is None else rid
        self.next_id = max(self.next_id, rid) + 1
        self.last_raw = frame({"type": "REQ", "v": "1.0", "id": rid, "op": op, "args": args or {}})
        self.sock.sendall(self.last_raw)
        raw = self.read_record(timeout)
        self.max_record = max(self.max_record, len(raw))
        rsp = unframe(raw)
        if rsp.get("type") != "RSP" or rsp.get("id") != rid:
            raise ValueError("unexpected reply %r" % rsp)
        self.last_reply_raw = raw
        self.last_rsp = rsp
        return rsp["status"], rsp["body"]

    def ok(self, op, args=None, timeout=1.0):
        status, body = self.req(op, args, timeout)
        if status != "OK":
            raise RuntimeError("%s -> %s %s" % (op, status, body))
        return body

    def drive(self, v, w, op_mode, ttl_ms=250, **extra):
        args = {"seq": self.seq, "v_mps": v, "w_radps": w, "ttl_ms": ttl_ms, "op_mode": op_mode}
        args.update(extra)
        self.seq += 1
        return self.ok("DRIVE", args)

    def rearm_sw(self, operator="integration.test"):
        nonce = self.ok("STATE")["rearm_nonce"]
        return self.req("REARM_SW", {"nonce": nonce, "operator": operator})


class Env:
    """UDP JSON environment socket of rr_chassis_sim: set inputs, inject faults, receive ground truth."""

    def __init__(self, host="127.0.0.1", port=5551):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
        self.truth = None
        self.set()  # subscribes this socket to the truth stream

    def close(self):
        self.sock.close()

    def _drain(self):
        """Discard queued datagrams (the 100 Hz truth stream), remembering the newest truth."""
        self.sock.setblocking(False)
        try:
            while True:
                msg = json.loads(self.sock.recvfrom(4096)[0])
                if msg.get("type") == "TRUTH":
                    self.truth = msg
        except BlockingIOError:
            pass
        finally:
            self.sock.settimeout(1.0)

    def set(self, **kv):
        self._drain()
        self.sock.sendto(json.dumps(kv).encode(), self.addr)
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            msg = json.loads(self.sock.recvfrom(4096)[0])
            if msg.get("type") == "ACK":
                if not msg["ok"]:
                    raise ValueError("emulator rejected %r" % kv)
                return
            self.truth = msg
        raise TimeoutError("no ACK from the emulator")

    def latest(self, wait=0.5):
        """A fresh ground-truth message: drains the queue, then waits for the next one."""
        self._drain()
        self.sock.settimeout(wait)
        try:
            while True:
                msg = json.loads(self.sock.recvfrom(4096)[0])
                if msg.get("type") == "TRUTH":
                    self.truth = msg
                    return msg
        except socket.timeout:
            return self.truth
        finally:
            self.sock.settimeout(1.0)


class Sim:
    """Launches rr_chassis_sim on free ports."""

    def __init__(self, binary, speed=1.0, seed=1):
        s1 = socket.socket()
        s1.bind(("127.0.0.1", 0))
        s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s2.bind(("127.0.0.1", 0))
        self.port, self.env_port = s1.getsockname()[1], s2.getsockname()[1]
        s1.close()
        s2.close()
        self.speed = speed
        self.proc = subprocess.Popen([binary, "--port", str(self.port), "--env-port", str(self.env_port), "--seed", str(seed), "--speed", str(speed), "--quiet"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.banner = self.proc.stdout.readline().decode()
        deadline = time.monotonic() + 5
        while True:
            try:
                self.link = Link(port=self.port)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.02)
        self.env = Env(port=self.env_port)

    def sleep(self, sim_seconds):
        time.sleep(sim_seconds / self.speed)

    def stop(self):
        try:
            self.link.close()
            self.env.close()
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc.stdout.close()


if __name__ == "__main__":
    argv = sys.argv[1:]
    host, port = "127.0.0.1", 5550
    while argv and argv[0].startswith("--"):
        if argv[0] == "--host":
            host = argv[1]
        elif argv[0] == "--port":
            port = int(argv[1])
        argv = argv[2:]
    if not argv:
        print(__doc__)
        sys.exit(2)
    link = Link(host, port)
    link.req("HELLO")
    status, body = link.req(argv[0], json.loads(argv[1]) if len(argv) > 1 else {}, timeout=4.0)
    print(status)
    print(json.dumps(body, indent=1))
