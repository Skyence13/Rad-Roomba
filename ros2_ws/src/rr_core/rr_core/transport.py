"""Byte transports for the two device links, selected by URL.

    serial:///dev/ttyUSB0?baud=1000000     real RS-485 adapter / USB CDC
    tcp://127.0.0.1:5540                   firmware emulators (native or Python)
    mem://name                             in-process pipe (tests, virtual time)

All transports are non-blocking: `read()` returns whatever has arrived (possibly
b""), `write()` sends, `wait(timeout_s)` blocks until readable or timeout
(virtual-time transports return immediately).  A closed peer raises
`TransportClosed`.

No ROS imports.
"""
from __future__ import annotations

import errno
import heapq
import select
import socket
from urllib.parse import parse_qs, urlparse


class TransportClosed(IOError):
    pass


class Clock:
    """Host monotonic clock in integer microseconds (CLOCK_MONOTONIC)."""

    def now_us(self) -> int:
        import time
        return time.monotonic_ns() // 1000


class VirtualClock(Clock):
    """Deterministic clock for simulation and tests."""

    def __init__(self, start_us: int = 1_000_000_000):
        self._t = int(start_us)

    def now_us(self) -> int:
        return self._t

    def advance(self, dt_us: int) -> int:
        self._t += int(dt_us)
        return self._t

    def set(self, t_us: int):
        if t_us < self._t:
            raise ValueError("virtual clock cannot go backwards")
        self._t = int(t_us)


class Transport:
    url = ""

    def read(self) -> bytes:
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def wait(self, timeout_s: float) -> None:
        return None

    def reset_input(self) -> bytes:
        """Discard stale host/adapter buffers; returns what was dropped."""
        dropped = b""
        try:
            while True:
                chunk = self.read()
                if not chunk:
                    break
                dropped += chunk
        except TransportClosed:
            pass
        return dropped

    def reopen(self) -> bool:
        """Try to (re)establish the transport. True when usable."""
        return True

    def close(self) -> None:
        return None


class TcpTransport(Transport):
    def __init__(self, host: str, port: int, url: str = ""):
        self.host, self.port, self.url = host, port, url or f"tcp://{host}:{port}"
        self._sock = None

    def reopen(self) -> bool:
        self.close()
        try:
            sock = socket.create_connection((self.host, self.port), timeout=0.5)
        except OSError:
            return False
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setblocking(False)
        self._sock = sock
        return True

    def read(self) -> bytes:
        if self._sock is None:
            raise TransportClosed("not connected")
        try:
            data = self._sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return b""
        except OSError as err:
            self.close()
            raise TransportClosed(str(err)) from err
        if data == b"":
            self.close()
            raise TransportClosed("peer closed")
        return data

    def write(self, data: bytes) -> None:
        if self._sock is None:
            raise TransportClosed("not connected")
        try:
            self._sock.setblocking(True)
            self._sock.settimeout(0.5)
            self._sock.sendall(data)
            self._sock.setblocking(False)
        except OSError as err:
            self.close()
            raise TransportClosed(str(err)) from err

    def wait(self, timeout_s: float) -> None:
        if self._sock is None:
            import time
            time.sleep(min(timeout_s, 0.05))
            return
        try:
            select.select([self._sock], [], [], timeout_s)
        except (OSError, ValueError):
            pass

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


class TcpListenTransport(Transport):
    """Device side of a TCP link (Python fakes serving the emulator ports): one client."""

    def __init__(self, host: str, port: int):
        self.url = f"tcp-listen://{host}:{port}"
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((host, port))
        self._srv.listen(1)
        self._srv.setblocking(False)
        self._conn = None

    def _accept(self):
        try:
            conn, _ = self._srv.accept()
        except (BlockingIOError, InterruptedError):
            return
        if self._conn is not None:
            self._conn.close()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.setblocking(False)
        self._conn = conn

    def read(self) -> bytes:
        self._accept()
        if self._conn is None:
            return b""
        try:
            data = self._conn.recv(65536)
        except (BlockingIOError, InterruptedError):
            return b""
        except OSError:
            data = b""
        if data == b"":
            self._conn.close()
            self._conn = None
        return data

    def write(self, data: bytes) -> None:
        if self._conn is None:
            return
        try:
            self._conn.setblocking(True)
            self._conn.settimeout(0.5)
            self._conn.sendall(data)
            self._conn.setblocking(False)
        except OSError:
            self._conn = None

    def close(self) -> None:
        for sock in (self._conn, self._srv):
            try:
                if sock is not None:
                    sock.close()
            except OSError:
                pass


class SerialTransport(Transport):
    def __init__(self, device: str, baud: int, url: str = ""):
        self.device, self.baud, self.url = device, baud, url
        self._ser = None

    def reopen(self) -> bool:
        import serial  # python3-serial; imported lazily so tests need no device
        self.close()
        try:
            self._ser = serial.Serial(self.device, self.baud, bytesize=8, parity="N",
                                      stopbits=1, timeout=0, write_timeout=0.5)
        except (OSError, serial.SerialException):
            self._ser = None
            return False
        return True

    def read(self) -> bytes:
        if self._ser is None:
            raise TransportClosed("not open")
        try:
            return self._ser.read(65536)
        except Exception as err:  # serial.SerialException, OSError on unplug
            self.close()
            raise TransportClosed(str(err)) from err

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise TransportClosed("not open")
        try:
            self._ser.write(data)
        except Exception as err:
            self.close()
            raise TransportClosed(str(err)) from err

    def reset_input(self) -> bytes:
        dropped = super().reset_input()
        if self._ser is not None:
            try:
                self._ser.reset_input_buffer()
            except Exception:
                pass
        return dropped

    def wait(self, timeout_s: float) -> None:
        if self._ser is None:
            import time
            time.sleep(min(timeout_s, 0.05))
            return
        try:
            select.select([self._ser.fileno()], [], [], timeout_s)
        except (OSError, ValueError):
            pass

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None


class MemoryEnd(Transport):
    """One end of a `MemoryLink`."""

    def __init__(self, link: "MemoryLink", side: int):
        self._link, self._side = link, side
        self.url = f"mem://{link.name}/{side}"

    def read(self) -> bytes:
        return self._link._read(self._side)

    def write(self, data: bytes) -> None:
        self._link._write(self._side, data)

    def reopen(self) -> bool:
        return self._link.connected


class MemoryLink:
    """Deterministic in-process duplex pipe with per-direction latency.

    Side 0 is the host, side 1 the device.  Delivery time is
    `now + delay + per-byte time * len`, evaluated on the supplied clock.
    Fault hooks: `connected=False` (cable pulled: writes vanish, reads raise),
    `drop_next[side]` (lose the next N writes from that side),
    `corrupt_next[side]` (flip one byte in the next N writes).
    """

    def __init__(self, clock: Clock, name: str = "link", delay_us=(200, 200),
                 byte_time_us: float = 0.0):
        self.clock, self.name = clock, name
        self.delay_us = list(delay_us)       # [host->device, device->host]
        self.byte_time_us = byte_time_us
        self.connected = True
        self.drop_next = [0, 0]
        self.corrupt_next = [0, 0]
        self._queues = ([], [])              # heaps of (t_deliver, n, data) for reader side
        self._n = 0
        self.ends = (MemoryEnd(self, 0), MemoryEnd(self, 1))

    def _write(self, side: int, data: bytes) -> None:
        if not self.connected:
            if side == 0:
                return                        # host writes into an open circuit
            return
        if self.drop_next[side] > 0:
            self.drop_next[side] -= 1
            return
        if self.corrupt_next[side] > 0:
            self.corrupt_next[side] -= 1
            mutable = bytearray(data)
            pos = max(0, len(mutable) // 2)
            mutable[pos] ^= 0x01
            data = bytes(mutable)
        t = self.clock.now_us() + self.delay_us[side] + int(self.byte_time_us * len(data))
        self._n += 1
        heapq.heappush(self._queues[1 - side], (t, self._n, data))

    def _read(self, side: int) -> bytes:
        queue = self._queues[side]
        now = self.clock.now_us()
        out = b""
        while queue and queue[0][0] <= now:
            out += heapq.heappop(queue)[2]
        return out

    def flush(self) -> None:
        self._queues[0].clear()
        self._queues[1].clear()


def open_transport(url: str) -> Transport:
    """Create (not yet open) a transport from a URL; call `reopen()` to connect."""
    parsed = urlparse(url)
    if parsed.scheme == "tcp":
        if not parsed.hostname or not parsed.port:
            raise ValueError(f"tcp URL needs host and port: {url}")
        return TcpTransport(parsed.hostname, parsed.port, url)
    if parsed.scheme == "serial":
        query = parse_qs(parsed.query)
        baud = int(query.get("baud", ["1000000"])[0])
        if not parsed.path:
            raise ValueError(f"serial URL needs a device path: {url}")
        return SerialTransport(parsed.path, baud, url)
    raise ValueError(f"unsupported transport URL scheme: {url}")


__all__ = ["Clock", "VirtualClock", "Transport", "TransportClosed", "TcpTransport",
           "SerialTransport", "MemoryLink", "MemoryEnd", "open_transport", "errno"]
