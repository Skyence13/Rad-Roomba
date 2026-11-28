"""Clock fit: offset+drift recovery, bound growth, expiry, asymmetry. RQ-012/RQ-024, VT-019 (calculated)."""
import math, random
from rr_core.clockfit import ClockFit, Exchange, interval_to_host


def exchanges(offset, drift_ppm, n, period=2_000_000, d_out=300, d_back=300, hold=120, jitter=0, seed=0,
              tb=10.0, req=50, rsp=70):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        h0 = 5_000_000 + i * period
        jo, jb = rng.uniform(0, jitter), rng.uniform(0, jitter)
        host_rx = h0 + tb * req + d_out + jo
        d1 = (host_rx - offset) / (1 + drift_ppm * 1e-6)
        d2 = d1 + hold
        h3 = offset + d2 * (1 + drift_ppm * 1e-6) + tb * rsp + d_back + jb
        out.append(Exchange(int(h0), int(round(d1)), int(round(d2)), int(math.ceil(h3)), req, rsp))
    return out


def test_recovers_offset_and_drift_within_bound():
    fit = ClockFit("e", byte_time_us=10.0)
    rec = None
    for ex in exchanges(offset=123_456_789, drift_ppm=35.0, n=10, jitter=200, seed=3):
        rec = fit.add(ex)
    assert rec.drift_fitted and abs((rec.drift - 1) * 1e6 - 35.0) < 30.0
    for dev in (4_000_000, 15_000_000, 22_000_000):
        truth = 123_456_789 + dev * (1 + 35e-6)
        host = rec.to_host(dev)
        assert abs(host - truth) <= rec.bound_us(host)
    assert rec.bound_at_fit_us < 2000            # contract target


def test_unequal_serialisation_is_removed():
    # 50-byte request, 700-byte reply at 1 Mbaud: uncorrected midpoint would be 3.25 ms off
    fit = ClockFit("e", byte_time_us=10.0, asym_allow_us=0.0)
    rec = fit.add(exchanges(1_000_000, 0, 1, req=50, rsp=700)[0])
    assert abs(rec.to_host(3_000_000) - 4_000_000) < 500


def test_bound_grows_with_age_and_expires():
    fit = ClockFit("e", expiry_us=10_000_000)
    for ex in exchanges(0, 0, 4):
        fit.add(ex)
    t = fit.current.newest_anchor_host_us
    assert fit.bound_us(t + 5e6) > fit.bound_us(t)
    assert math.isinf(fit.bound_us(t + 10_000_001))
    assert math.isinf(interval_to_host(fit.current, int(fit.current.to_device(t + 9.95e6)), 100_000, 10e6)[2])


def test_asymmetry_larger_than_allowance_is_visible_in_bound_only_via_rtt():
    # 4 ms one-way latency (symmetric): bound must cover half of it
    fit = ClockFit("e")
    for ex in exchanges(0, 0, 5, d_out=4000, d_back=4000):
        fit.add(ex)
    assert fit.current.bound_at_fit_us >= 4000


def test_rejects_backwards_device_clock_and_huge_rtt():
    fit = ClockFit("e", max_half_us=20_000)
    exs = exchanges(0, 0, 3)
    fit.add(exs[1])
    assert fit.add(exs[0]) is None
    assert fit.add(exchanges(0, 0, 4, d_out=50_000, d_back=50_000)[3]) is None
    assert fit.rejected == 2
