"""Host <-> device clock fit shared by the head link and the chassis link.

contract.yaml `timing.sync_method`: host-mediated four-timestamp exchange (TIME
op), linear fit host = offset + drift * device,
bound = half round-trip + asymmetry allowance + drift * age.
Head ICD section 6: associate the device midpoint with the host midpoint, fit
over several exchanges, log offset, drift, anchors, residuals, asymmetry
allowance, age and bound, and account for unequal request and reply
serialization lengths.

Exchange timestamps (all integer microseconds):
    h0  host clock when the request's first byte is written
    d1  device clock at receipt of the request (rx_us)
    d2  device clock when the reply transmission starts (tx_us)
    h3  host clock when the complete reply has been read

With a byte time `tb` (10 us at 1 Mbaud 8N1; 0 for USB CDC / TCP), the request
occupies `req_bytes*tb` and the reply `rsp_bytes*tb` on the wire, so

    residual  R = (h3 - h0) - (d2 - d1) - tb*(req_bytes + rsp_bytes)   (>= 0)
    host time of d1  ~=  h0 + tb*req_bytes + R/2        +/- R/2

i.e. the unexplained delay R is split evenly and its half is the anchor's
uncertainty; a separate asymmetry allowance covers one-way differences that the
exchange cannot observe (to be replaced by a measured value, ICD section 6).

Evidence class of every number produced here: calculated (simulated when run
against the emulators).  No ROS imports.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Exchange:
    h0: int
    d1: int
    d2: int
    h3: int
    req_bytes: int = 0
    rsp_bytes: int = 0


@dataclass(frozen=True)
class Anchor:
    dev_us: float      # device time of the anchor (d1)
    host_us: float     # estimated host time of the same instant
    half_us: float     # half of the unexplained round-trip residual


@dataclass
class FitRecord:
    """One archived fit (also the body of the head SYNC record)."""
    fit_id: str
    epoch: str
    n: int
    dev_ref_us: float            # x0: device reference time (numerical conditioning)
    host_ref_us: float           # host time at dev_ref (offset form: host = host_ref + drift*(dev - dev_ref))
    drift: float
    drift_fitted: bool
    anchors: list = field(default_factory=list)      # [[dev_us, host_us, half_us], ...]
    residuals_us: list = field(default_factory=list)
    best_half_us: float = 0.0
    asym_allow_us: float = 0.0
    drift_unc_ppm: float = 0.0
    newest_anchor_host_us: float = 0.0
    bound_at_fit_us: float = 0.0
    byte_time_us: float = 0.0
    host_clock: str = "CLOCK_MONOTONIC"
    units: str = "us"

    def to_host(self, dev_us: float) -> float:
        return self.host_ref_us + self.drift * (dev_us - self.dev_ref_us)

    def to_device(self, host_us: float) -> float:
        return self.dev_ref_us + (host_us - self.host_ref_us) / self.drift

    def bound_us(self, host_us: float) -> float:
        """Worst-case time error estimate at host time `host_us`.

        min over anchors of (anchor half residual + |fit residual at the anchor|
        + drift uncertainty * distance in time from the anchor) + asymmetry
        allowance.  Monotonic growth with age after the newest anchor.
        """
        best = math.inf
        for (dev, host, half), res in zip(self.anchors, self.residuals_us):
            age = abs(host_us - host)
            best = min(best, half + abs(res) + self.drift_unc_ppm * 1e-6 * age)
        return best + self.asym_allow_us

    def as_dict(self) -> dict:
        return {
            "fit_id": self.fit_id, "epoch": self.epoch, "n": self.n,
            "dev_ref_us": self.dev_ref_us, "host_ref_us": self.host_ref_us,
            "drift": self.drift, "drift_fitted": self.drift_fitted,
            "anchors": self.anchors, "residuals_us": self.residuals_us,
            "best_half_us": self.best_half_us, "asym_allow_us": self.asym_allow_us,
            "drift_unc_ppm": self.drift_unc_ppm,
            "newest_anchor_host_us": self.newest_anchor_host_us,
            "bound_at_fit_us": self.bound_at_fit_us, "byte_time_us": self.byte_time_us,
            "host_clock": self.host_clock, "units": self.units,
        }


class ClockFit:
    """Sliding-window weighted linear fit for one clock epoch.

    A new device boot or a new attachment starts a new `ClockFit` (ICD 6:
    "Restart the fit after re-identification").
    """

    def __init__(self, epoch: str, byte_time_us: float = 10.0, asym_allow_us: float = 150.0,
                 drift_unc_fitted_ppm: float = 20.0, drift_unc_nominal_ppm: float = 200.0,
                 window: int = 12, expiry_us: int = 10_000_000, max_half_us: float = 20_000.0,
                 min_span_us: float = 500_000.0, max_drift_ppm: float = 500.0,
                 id_prefix: str = "fit"):
        self.epoch = epoch
        self.byte_time_us = byte_time_us
        self.asym_allow_us = asym_allow_us
        self.drift_unc_fitted_ppm = drift_unc_fitted_ppm
        self.drift_unc_nominal_ppm = drift_unc_nominal_ppm
        self.window = window
        self.expiry_us = expiry_us
        self.max_half_us = max_half_us
        self.min_span_us = min_span_us
        self.max_drift_ppm = max_drift_ppm
        self.id_prefix = id_prefix
        self._anchors: list[Anchor] = []
        self._count = 0
        self.rejected = 0
        self.current: FitRecord | None = None

    # ------------------------------------------------------------------ input
    def anchor_from(self, ex: Exchange) -> Anchor | None:
        wire = self.byte_time_us * (ex.req_bytes + ex.rsp_bytes)
        residual = (ex.h3 - ex.h0) - (ex.d2 - ex.d1) - wire
        if ex.h3 < ex.h0 or ex.d2 < ex.d1:
            return None
        if residual < 0:
            # Device says it held the request longer than the host saw the whole
            # exchange take: clocks disagree by more than the wire model allows.
            # Keep the anchor but give it the full round trip as uncertainty.
            half = (ex.h3 - ex.h0) / 2.0
            host = (ex.h0 + ex.h3) / 2.0 - (ex.d2 - ex.d1) / 2.0
        else:
            half = residual / 2.0
            host = ex.h0 + self.byte_time_us * ex.req_bytes + half
        if half > self.max_half_us:
            return None
        return Anchor(float(ex.d1), float(host), float(half))

    def add(self, ex: Exchange) -> FitRecord | None:
        """Add one exchange; returns the new fit, or None when it was rejected."""
        anchor = self.anchor_from(ex)
        if anchor is None:
            self.rejected += 1
            return None
        if self._anchors and anchor.dev_us <= self._anchors[-1].dev_us:
            self.rejected += 1          # device clock went backwards: caller must start a new epoch
            return None
        self._anchors.append(anchor)
        if len(self._anchors) > self.window:
            # keep the window but never drop the lowest-uncertainty anchor of the old half
            self._anchors.pop(0)
        self._count += 1
        self.current = self._fit()
        return self.current

    # ------------------------------------------------------------------- fit
    def _fit(self) -> FitRecord:
        anchors = self._anchors
        floor = 20.0   # us; keeps the weights finite for near-zero residuals
        x0 = anchors[-1].dev_us
        xs = [a.dev_us - x0 for a in anchors]
        ys = [a.host_us for a in anchors]
        ws = [1.0 / max(a.half_us, floor) ** 2 for a in anchors]
        sw = sum(ws)
        xm = sum(w * x for w, x in zip(ws, xs)) / sw
        ym = sum(w * y for w, y in zip(ws, ys)) / sw
        sxx = sum(w * (x - xm) ** 2 for w, x in zip(ws, xs))
        span = max(xs) - min(xs)
        drift, fitted = 1.0, False
        if len(anchors) >= 3 and span >= self.min_span_us and sxx > 0:
            sxy = sum(w * (x - xm) * (y - ym) for w, x, y in zip(ws, xs, ys))
            cand = sxy / sxx
            if abs(cand - 1.0) <= self.max_drift_ppm * 1e-6:
                drift, fitted = cand, True
        host_ref = ym - drift * xm          # host time at dev = x0
        residuals = [y - (host_ref + drift * x) for x, y in zip(xs, ys)]
        rec = FitRecord(
            fit_id=f"{self.id_prefix}-{self._count:05d}", epoch=self.epoch, n=len(anchors),
            dev_ref_us=x0, host_ref_us=host_ref, drift=drift, drift_fitted=fitted,
            anchors=[[a.dev_us, a.host_us, a.half_us] for a in anchors],
            residuals_us=residuals, best_half_us=min(a.half_us for a in anchors),
            asym_allow_us=self.asym_allow_us,
            drift_unc_ppm=self.drift_unc_fitted_ppm if fitted else self.drift_unc_nominal_ppm,
            newest_anchor_host_us=anchors[-1].host_us, byte_time_us=self.byte_time_us)
        rec.bound_at_fit_us = rec.bound_us(rec.newest_anchor_host_us)
        return rec

    # ----------------------------------------------------------------- query
    def bound_us(self, host_us: float) -> float:
        rec = self.current
        if rec is None:
            return math.inf
        if host_us - rec.newest_anchor_host_us > self.expiry_us:
            return math.inf            # contract timing.sync_expiry_s
        return rec.bound_us(host_us)

    def age_us(self, host_us: float) -> float:
        return math.inf if self.current is None else host_us - self.current.newest_anchor_host_us


def interval_to_host(rec: FitRecord, start_us: int, span_us: int, expiry_us: float):
    """Convert a device interval to host time with the bound over both endpoints.

    ICD section 6: "Convert the entire sample interval to robot time, and
    evaluate the time bound across its endpoints."  Returns (t0, t1, bound);
    bound is inf when the fit is older than `expiry_us` at either endpoint.
    """
    t0 = rec.to_host(start_us)
    t1 = rec.to_host(start_us + span_us)
    bound = max(rec.bound_us(t0), rec.bound_us(t1))
    if max(t0, t1) - rec.newest_anchor_host_us > expiry_us:
        bound = math.inf
    return t0, t1, bound
