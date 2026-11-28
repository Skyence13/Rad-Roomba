"""IB-46: a slow head transaction must not starve the chassis DRIVE keep-alive.

The head transport is a stub whose read() blocks for 0.5 s (longer than the 200 ms DRIVE TTL) once armed, which is what a
head-side reconnect or stall looks like to the single application loop.  The chassis side is the Python fake served over
loopback TCP with its own device thread; it records when each DRIVE arrives.  Nothing depends on host load: the injected
stall is the cause, the assertion compares it with the TTL.  Simulated evidence (Python fake, real clock, loopback)."""
import socket
import sys
import threading
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
for pkg in sorted(SRC.iterdir()):
    if (pkg / pkg.name).is_dir() and str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))

from rr_bringup.app import RobotApp                                     # noqa: E402
from rr_bringup.runtime import demo_registry                            # noqa: E402
from rr_core.fakes.chassis import FakeChassis                           # noqa: E402
from rr_core.transport import Clock, TcpListenTransport, Transport, open_transport   # noqa: E402

STALL_S = 0.5            # > ttl 0.2 s
TTL_US = 200_000


class SlowHead(Transport):
    """Head transport that blocks inside read() for STALL_S per call once `stall` is set (injected slow head transaction)."""
    url = "slow-head"

    def __init__(self):
        self.stall = False
        self.stalled_calls = 0

    def read(self):
        if self.stall:
            self.stalled_calls += 1
            time.sleep(STALL_S)
        return b""

    def write(self, data):
        return None


class RecordingChassis(FakeChassis):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.drive_rx = []

    def _op_DRIVE(self, a, rx, tid, raw):
        self.drive_rx.append(self.clock.now_us())
        return super()._op_DRIVE(a, rx, tid, raw)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_case(tmp_path, threaded):
    clock = Clock()
    port = _free_port()
    dev_t = TcpListenTransport("127.0.0.1", port)
    fake = RecordingChassis(clock, dev_t, pose=(0.6, 0.0, 0.0))
    stop = threading.Event()

    def device():
        while not stop.is_set():
            fake.step()
            time.sleep(0.0005)
    dt = threading.Thread(target=device, daemon=True)
    dt.start()
    head = SlowHead()
    app = RobotApp(clock, head, open_transport(f"tcp://127.0.0.1:{port}"), tmp_path / ("t" if threaded else "s"), demo_registry(),
                   {"link": {"byte_time_us": 0.0}, "chassis_thread": threaded})
    try:
        t_end = time.monotonic() + 15
        while app.chassis.link_state != "UP" and time.monotonic() < t_end:
            app.step()
            time.sleep(0.0005)
        assert app.chassis.link_state == "UP"
        t_end = time.monotonic() + 0.6                           # steady state: DRIVE every 20 ms
        while time.monotonic() < t_end:
            app.step()
            time.sleep(0.0005)
        n0 = len(fake.drive_rx)
        head.stall = True                                         # inject: every head read now blocks for 0.5 s
        t_end = time.monotonic() + 2.2 * STALL_S
        while time.monotonic() < t_end:
            app.step()                                            # the application loop spends its time in the head read
            time.sleep(0.0005)
        head.stall = False
        gaps = [b - a for a, b in zip(fake.drive_rx[n0 - 1:], fake.drive_rx[n0:])]
        return max(gaps), head.stalled_calls, app.chassis.stats["drive_gap_max_us"]
    finally:
        app.shutdown()
        stop.set()
        dt.join(2)
        app.archive.close()
        dev_t.close()


def test_single_loop_is_starved_by_a_slow_head_transaction(tmp_path):
    """Reproduction (the IB-46 mechanism): without the thread the DRIVE gap equals the head stall, far above the TTL."""
    gap, calls, _ = run_case(tmp_path, threaded=False)
    print(f"single loop: max DRIVE gap {gap / 1000:.0f} ms, stalled head reads {calls}")
    assert calls >= 1
    assert gap > TTL_US, f"expected starvation, max DRIVE gap {gap} us"


def test_chassis_link_thread_keeps_the_drive_deadline(tmp_path):
    gap, calls, own_gap = run_case(tmp_path, threaded=True)
    print(f"chassis thread: max DRIVE gap {gap / 1000:.0f} ms (host-side stat {own_gap / 1000:.0f} ms), stalled head reads {calls}")
    assert calls >= 1
    assert gap < 0.5 * TTL_US, f"DRIVE gap {gap} us with the chassis on its own thread"        # 100 ms: 5x the 20 ms period
    assert own_gap < 0.5 * TTL_US
