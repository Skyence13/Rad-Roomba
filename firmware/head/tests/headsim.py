"""Test/bench helper: launch rr_head_sim and talk to it with the BASELINE host tools.

Everything protocol-related goes through interface/wire_codec.py (framing + CRC) and
interface/head_discovery.py (descriptor assembly / validation); this file only adds sockets.
"""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "interface"))
import wire_codec  # noqa: E402  baseline, unmodified
import head_discovery  # noqa: E402  baseline, unmodified


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sim:
    """One rr_head_sim process plus its stimulus socket."""

    def __init__(self, exe, *args, seed=1, clock="manual", gate_range=(10000, 1000000), truth_log=None):
        self.tcp_port = free_port()
        self.stim_port = free_port(socket.SOCK_DGRAM)
        cmd = [str(exe), "--tcp", f"127.0.0.1:{self.tcp_port}", "--stim", f"127.0.0.1:{self.stim_port}",
               "--seed", str(seed), "--clock", clock, "--quiet",
               "--gate-range", f"{gate_range[0]},{gate_range[1]}", *map(str, args)]
        if truth_log:
            cmd += ["--truth-log", str(truth_log)]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        ready = self.proc.stdout.readline()
        if not ready.startswith(b"rr_head_sim ready"):
            raise RuntimeError(f"emulator did not start: {ready!r}")
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.settimeout(10.0)

    def ctl(self, **cmd):
        """Send one stimulus/fault command; returns the emulator's JSON reply (raises if not ok)."""
        self.udp.sendto(json.dumps(cmd).encode(), ("127.0.0.1", self.stim_port))
        reply = json.loads(self.udp.recv(65536))
        if not reply.get("ok"):
            raise RuntimeError(f"emulator refused {cmd}: {reply}")
        return reply

    def advance(self, us):
        while us > 0:  # the emulator caps one advance at one hour
            step = min(us, 3_000_000_000)
            self.ctl(cmd="advance", us=step)
            us -= step

    def stop(self):
        """SIGTERM and wait: returns the exit status (0 = clean shutdown)."""
        self.udp.close()
        self.proc.terminate()
        try:
            return self.proc.wait(timeout=10)
        finally:
            self.proc.stdout.close()


class Link:
    """Host end of the RS-485 byte stream (TCP), framed with the baseline wire codec."""

    def __init__(self, sim, timeout=2.0):
        self.sock = socket.create_connection(("127.0.0.1", sim.tcp_port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.timeout = timeout
        self.next_id = 1
        self.buf = b""
        self.last_tx = b""
        self.last_rx = b""
        self.rx_bytes = 0
        self.tx_bytes = 0

    def close(self):
        self.sock.close()

    def send_raw(self, data):
        self.sock.sendall(data)
        self.tx_bytes += len(data)

    def recv_line(self, timeout=None):
        """One raw line including LF, or None on timeout."""
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                return None
            if not chunk:
                return None
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        self.rx_bytes += len(line) + 1
        return line + b"\n"

    def request(self, op, args=None, req_id=None, timeout=None):
        """One transaction. Returns the decoded RSP (validated framing/CRC, matching id) or None."""
        if req_id is None:
            req_id = self.next_id
            self.next_id += 1
        self.last_tx = wire_codec.encode({"type": "REQ", "v": "2.0", "id": req_id, "op": op, "args": args or {}})
        self.send_raw(self.last_tx)
        self.last_rx = self.recv_line(timeout)
        if self.last_rx is None:
            return None
        rsp = wire_codec.decode(self.last_rx)  # raises ValueError on a bad CRC
        if rsp.get("type") != "RSP" or rsp.get("v") != "2.0" or rsp.get("id") != req_id:
            raise AssertionError(f"reply does not match request {req_id}: {rsp}")
        return rsp

    def ok(self, op, args=None, **kw):
        rsp = self.request(op, args, **kw)
        if rsp is None or rsp["status"] != "OK":
            raise AssertionError(f"{op} {args}: {rsp}")
        return rsp["body"]

    def handshake(self, registry=None, mode="BENCH"):
        """HELLO, chunked GET_DESCRIPTOR, host-side validation with head_discovery, BIND.

        Returns (hello, descriptor_bytes, manifest). If registry is None a bench registry entry
        is derived from what the head reported (integration tests that are not about the
        registry); pass a real registry to exercise the trusted-registry check."""
        hello = self.ok("HELLO")
        chunks = []
        offset = 0
        while offset < hello["descriptor_bytes"]:
            body = self.ok("GET_DESCRIPTOR", {"boot_id": hello["boot_id"], "descriptor_id": hello["descriptor_id"],
                                              "offset": offset, "count": head_discovery.CHUNK_BYTES})
            chunks.append(body)
            offset += len(head_discovery.base64.b64decode(body["bytes_b64"]))
        data = head_discovery.assemble_descriptor(hello, chunks)
        if registry is None:
            desc = json.loads(data)
            registry = {"records": [{"serial": desc["serial"], "descriptor_id": desc["descriptor_id"],
                                     "head_type": desc["head_type"], "geometry_id": desc["geometry_id"],
                                     "setup_id": desc["setup_id"], "descriptor_sha256": hello["descriptor_sha256"],
                                     "firmware": hello["firmware"], "authorized_uses": ["BENCH"],
                                     "calibration_id": None}]}
        verified = head_discovery.evaluate(hello, data, registry, mode)
        body = self.ok("BIND", {"boot_id": hello["boot_id"], "setup_id": hello["setup_id"],
                                "descriptor_sha256": verified["descriptor_sha256"]})
        if body != {"bound": True}:
            raise AssertionError(body)
        return hello, data, head_discovery.attachment_manifest(hello, verified)
