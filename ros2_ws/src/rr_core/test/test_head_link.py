"""Head link master against the Python head fake (simulated; virtual clock).
Traces: RQ-024, RQ-025, RQ-037, RQ-049; VT-019, VT-033."""
import json
import pytest
from rr_core.transport import VirtualClock, MemoryLink
from rr_core.head_link import HeadLinkMaster, HeadLinkConfig, HeadStreamInterpreter
from rr_core.fakes.head import FakeHead
from rr_core import wire


class Rig:
    def __init__(self, examples, registry, seed=1, delay=(200, 200), **cfg):
        self.clock = VirtualClock()
        self.link = MemoryLink(self.clock, delay_us=delay, byte_time_us=10.0)
        self.head = FakeHead(self.clock, self.link.ends[1], (examples / "head_descriptor.json").read_bytes(), seed=seed)
        self.head.set_rates({n: {"alpha": 0.5, "beta": 5.0, "ref": 4.0} for n in range(4)})
        self.entries = []
        n = [0]

        def uuid():
            n[0] += 1
            return f"00000000-0000-4000-8000-{n[0]:012d}"
        self.master = HeadLinkMaster(self.link.ends[0], self.clock, registry, HeadLinkConfig(**cfg),
                                     sink=self.entries.append, uuid_factory=uuid, tid_start=100)
        self.events = []

    def run(self, seconds, hook=None):
        for i in range(int(seconds * 1000)):
            self.clock.advance(1000)
            self.head.step()
            self.master.step()
            self.events += self.master.drain_events()
            if hook:
                hook(i)

    def ev(self, kind):
        return [e for e in self.events if e["ev"] == kind]


def test_handshake_sync_arm_read(examples, demo_registry):
    rig = Rig(examples, demo_registry)
    rig.run(4.0)
    opens = rig.ev("session_open")
    assert len(opens) == 1 and rig.master.state == "ARMED"
    man = opens[0]["manifest"]
    assert man["head_id"] == "HEAD-DEMO-001" and man["mode"] == "COMMISSIONING"
    gates = [e["gate"] for e in rig.ev("gate")]
    assert len(gates) >= 20
    assert [g["sequence"] for g in gates] == list(range(len(gates)))
    # manifest persisted before the first frame (stream order)
    kinds = [(k, p.get("c") if k == "C" else None) for _, k, p in rig.entries]
    first_open = kinds.index(("C", "SESSION_OPEN"))
    first_read = next(i for i, (t, k, p) in enumerate(rig.entries) if k == "T" and b'"READ"' in p)
    assert first_open < first_read
    late = gates[5:]
    assert all(not l["reasons"] for g in late for l in g["lanes"])
    assert max(g["bound_us"] for g in late) < 2000          # contract target bound (simulated)
    # host time conversion is right to within the bound
    g = late[-1]
    true_host = rig.head._boot_host_us + (g["start_us"] - rig.head.boot_offset_us)
    assert abs(g["t0_us"] - true_host) <= g["bound_us"]
    assert not rig.ev("gap") and not rig.ev("fault")


def test_lost_and_corrupt_replies_retry_same_id_without_double_count(examples, demo_registry):
    rig = Rig(examples, demo_registry)

    def hook(i):
        if i in (1500, 2100, 2600):
            rig.head.drop_replies = 1
        if i in (1800, 2300):
            rig.head.corrupt_replies = 1
    rig.run(4.0, hook)
    gates = [e["gate"] for e in rig.ev("gate")]
    assert [g["sequence"] for g in gates] == list(range(len(gates)))     # nothing lost, nothing doubled
    assert rig.master.interp.stats["retries"] >= 5
    assert rig.master.interp.stats["bad_lines"] >= 2
    assert len(rig.ev("session_open")) == 1 and not rig.ev("session_close")
    # retried ids reuse the identical request bytes
    tx = [p for _, k, p in rig.entries if k == "T"]
    ids = [wire.decode(p)["id"] for p in tx]
    assert len(ids) - len(set(ids)) == rig.master.interp.stats["retries"]


def test_reset_while_armed_closes_session_gap_and_fresh_handshake(examples, demo_registry):
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    n_before = len(rig.ev("gate"))
    old_boot = rig.head.boot_id
    rig.head.reset()
    rig.run(0.5)
    closes = rig.ev("session_close")
    assert len(closes) == 1 and "UNBOUND" in closes[0]["reason"]
    assert closes[0]["last_seq"] == rig.ev("gate")[n_before - 1]["gate"]["sequence"]
    # between the close and the new SESSION_OPEN no gate is attributed
    rig.run(4.0)
    opens = rig.ev("session_open")
    assert len(opens) == 2 and opens[1]["manifest"]["boot_id"] != old_boot
    a0, a1 = (o["manifest"]["attachment_session_id"] for o in opens)
    assert a0 != a1
    t_close, t_open = closes[0]["t_us"], opens[1]["t_us"]
    assert t_open - t_close >= rig.master.cfg.quiet_us
    assert not [e for e in rig.ev("gate") if t_close < e["t_us"] < t_open]
    new = [e["gate"] for e in rig.ev("gate") if e["gate"]["attachment"] == a1]
    assert new and new[0]["sequence"] == 0
    # fresh transaction ids across the transition
    ids = [(t, wire.decode(p)["id"]) for t, k, p in rig.entries if k == "T"]
    before = max(i for t, i in ids if t <= t_close)
    after = min(i for t, i in ids if t >= t_open - 2_000_000 and t > t_close)
    assert after - before >= rig.master.cfg.tid_stride


def test_cable_pull_times_out_and_recovers(examples, demo_registry):
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    rig.link.connected = False
    rig.link.flush()
    rig.run(1.0)
    assert rig.ev("session_close") and "TIMEOUT" in rig.ev("session_close")[0]["reason"]
    assert rig.master.state in ("QUIET", "HANDSHAKE", "DOWN")
    rig.link.connected = True
    rig.run(4.0)
    # the same powered head returns still bound: a fresh HELLO is nevertheless required
    assert len(rig.ev("session_open")) == 2
    assert rig.master.state == "ARMED"


def test_buffer_overflow_exact_gap(examples, demo_registry):
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    last = rig.master.interp.last_seq
    rig.master.cfg.read_poll_us = 10**9            # host stops reading (falls behind)
    rig.master.cfg.sync_refresh_us = 10**9
    saved = rig.master.cfg.diag_enabled
    rig.master._diag_supported = False
    rig.run(0.2)
    last = rig.master.interp.last_seq
    # advance 20 s with only the head running: 200 gates produced, 128 retained
    for _ in range(20_000):
        rig.clock.advance(1000)
        rig.head.step()
    rig.master.cfg.read_poll_us = 20_000
    import rr_core.head_link as hl
    rig.master._proc = rig.master._run()           # resume polling immediately
    rig.run(3.0)
    gaps = [e for e in rig.ev("gap") if e["kind"] == "BUFFER_EXPIRED"]
    assert len(gaps) == 1
    g = gaps[0]
    assert g["first_missing"] == last + 1 and g["last_missing"] == g["oldest_seq"] - 1
    seqs = [e["gate"]["sequence"] for e in rig.ev("gate")]
    assert g["count"] == g["last_missing"] - g["first_missing"] + 1 > 50
    assert seqs[seqs.index(last) + 1] == g["oldest_seq"]
    assert not any(g["first_missing"] <= s <= g["last_missing"] for s in seqs)


def test_null_reference_lane_and_holdover(examples, demo_registry):
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    rig.head.lane_null[2] = {"ref"}
    rig.run(1.0)
    g = rig.ev("gate")[-1]["gate"]
    assert g["lanes"][2]["ref"] is None and "NULL:photon_ref" in g["lanes"][2]["reasons"]
    assert g["lanes"][2]["beta"] is not None          # floor gross counts preserved
    assert not g["lanes"][1]["reasons"]


def test_unknown_head_blocks_and_never_arms(examples, demo_registry):
    demo_registry["records"][0]["descriptor_sha256"] = "0" * 64
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    assert rig.master.state == "BLOCKED" and rig.master.block_reason == "REGISTRY_MISMATCH"
    assert not rig.ev("session_open") and not rig.ev("gate")
    assert not [p for _, k, p in rig.entries if k == "T" and b'"ARM"' in p]


def test_replay_of_raw_stream_reproduces_events(examples, demo_registry):
    rig = Rig(examples, demo_registry)

    def hook(i):
        if i == 2000:
            rig.head.corrupt_replies = 1
        if i == 3500:
            rig.head.reset()
    rig.run(8.0, hook)
    interp = HeadStreamInterpreter(HeadLinkConfig())
    replayed = []
    for entry in rig.entries:
        replayed += interp.feed(entry)
    live = [e for e in rig.events if e["ev"] not in ("link_down", "blocked")]
    assert json.dumps(replayed, sort_keys=True) == json.dumps(live, sort_keys=True)


def test_presence_event_closes_session(examples, demo_registry):
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    rig.master.notify_continuity_event("J2_UNPLUG")
    rig.run(0.1)
    assert "CONTINUITY:J2_UNPLUG" in rig.ev("session_close")[0]["reason"]


def test_heater_transition_is_derived_from_consecutive_frames_and_after_gaps(examples, demo_registry):
    """head_icd_addendum_0.4 (firmware 0.5.1): ACQ has no heater-transition member; the host derives it from consecutive
    frames, and treats the gate after a sequence gap as marked.  DIAG members added by the firmware are archived verbatim
    and the interpreter hands the DIAG body to the processing (alpha_short per lane)."""
    rig = Rig(examples, demo_registry)
    rig.run(3.0)
    gates = [e["gate"] for e in rig.ev("gate")]
    assert all(g["marks"] == [] and g["heater_transition"] is False for g in gates)
    interp = rig.master.interp
    n0 = len(gates)
    interp._prev_heater = "ON"                         # the fake head reports OFF: the next gate contains the edge
    rig.run(0.5)
    g1 = [e["gate"] for e in rig.ev("gate")][n0]
    assert g1["marks"] == ["HEATER_TRANSITION"] and g1["heater_transition"] is True
    n1 = len(rig.ev("gate"))
    interp._marked_next = True                         # as set by a SEQUENCE_SKIP / BUFFER_EXPIRED / TIME_GAP
    rig.run(0.5)
    g2 = [e["gate"] for e in rig.ev("gate")][n1]
    assert g2["marks"] == ["AFTER_GAP"]
    diags = rig.ev("diag")
    assert diags and all(len(d["body"]["lanes"]) == 4 and "alpha_short" in d["body"]["lanes"][0] and d["body"]["bumper_zones"] is None for d in diags)
