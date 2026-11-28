"""Moving-patch expected counts, MODEL.md section 5.

A rectangular patch of uniform activity density D_p crosses rectangular
apertures on a straight pass. With the uniform (top-hat) spatial response
MODEL.md prescribes until a measured response exists,

    E[N_net] = K * D_p * integral_gate w(t) dt,   w(t) = overlap area / aperture area.

Geometry: x along travel, y across travel, metres. Lane i has its aperture
centred at y = lane_centres[i]; the head moves in +x at speed v and the
aperture centre is at x_start + v*t. All integrals over time are analytic
(the along-travel overlap is a trapezoid in the aperture position).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import model

__all__ = ["Head", "Patch", "lateral_overlap", "overlap_length", "gate_edges_for_pass",
           "gate_weights", "select", "patch_sum", "best_window", "tumbling_cells", "patch_dhash"]


@dataclass(frozen=True)
class Head:
    """Rev D head layout from the design text: 4 apertures 80 mm x 100 mm on 87.5 mm pitch."""
    L: float = 0.100        # along travel (m)
    W: float = 0.080        # across travel (m)
    pitch: float = 0.0875   # lane pitch (m)
    n_lanes: int = 4

    @property
    def lane_centres(self) -> np.ndarray:
        """Lane 0 is the robot's left (+y), as in software/map_demo.py."""
        return ((self.n_lanes - 1) / 2.0 - np.arange(self.n_lanes)) * self.pitch

    @property
    def aperture_area_cm2(self) -> float:
        return self.L * self.W * 1e4

    @property
    def seam_gap(self) -> float:
        return self.pitch - self.W


@dataclass(frozen=True)
class Patch:
    """Axis-aligned rectangular patch: centre (x, y), extent lx along travel, ly across."""
    x: float
    y: float
    lx: float
    ly: float

    @classmethod
    def square(cls, area_cm2: float, x: float = 0.0, y: float = 0.0) -> "Patch":
        side = np.sqrt(area_cm2 * 1e-4)
        return cls(x, y, side, side)

    @property
    def area_cm2(self) -> float:
        return self.lx * self.ly * 1e4


def _interval_overlap(c1, w1, c2, w2):
    lo = np.maximum(c1 - w1 / 2.0, c2 - w2 / 2.0)
    hi = np.minimum(c1 + w1 / 2.0, c2 + w2 / 2.0)
    return np.maximum(hi - lo, 0.0)


def lateral_overlap(head: Head, patch: Patch, y_offset: float = 0.0) -> np.ndarray:
    """Across-travel overlap (m) of the patch with each lane; y_offset shifts the head."""
    return _interval_overlap(head.lane_centres + y_offset, head.W, patch.y, patch.ly)


def overlap_length(s, patch: Patch, L: float):
    """Along-travel overlap (m) of the patch with an aperture centred at x = s."""
    return _interval_overlap(np.asarray(s, float), L, patch.x, patch.lx)


def _overlap_primitive(s, patch: Patch, L: float):
    """Integral of overlap_length from -inf to s (m^2): second difference of u_+^2 / 2."""
    s = np.asarray(s, float)
    a1 = patch.x - patch.lx / 2.0 - L / 2.0
    a2 = patch.x - patch.lx / 2.0 + L / 2.0
    a3 = patch.x + patch.lx / 2.0 - L / 2.0
    a4 = patch.x + patch.lx / 2.0 + L / 2.0

    def q(u):
        return 0.5 * np.square(np.maximum(u, 0.0))

    return q(s - a1) - q(s - a2) - q(s - a3) + q(s - a4)


def gate_edges_for_pass(head: Head, patch: Patch, v: float, gate: float, phase: float = 0.0,
                        margin_gates: int = 1) -> np.ndarray:
    """Gate edges (s) covering the whole crossing, with t = 0 when the aperture is centred on the patch.

    Edges lie at phase + j*gate; phase in [0, gate) sets the gate boundary
    position relative to the patch centre (gate-phase dependence).
    """
    half = (head.L + patch.lx) / (2.0 * v)
    j0 = int(np.floor((-half - phase) / gate)) - margin_gates
    j1 = int(np.ceil((half - phase) / gate)) + margin_gates
    return phase + gate * np.arange(j0, j1 + 1)


def gate_weights(head: Head, patch: Patch, v: float, edges, x_start=None, y_offset: float = 0.0) -> np.ndarray:
    """W[lane, gate] = integral over the gate of w(t) dt, in seconds (MODEL.md section 5).

    edges: monotonically increasing gate edges (s). The aperture centre is at
    x_start + v*t (default x_start = patch.x, i.e. centred on the patch at t=0).
    v = 0 gives a stationary measurement.
    """
    edges = np.asarray(edges, float)
    x0 = patch.x if x_start is None else x_start
    oy = lateral_overlap(head, patch, y_offset)              # (n_lanes,)
    if v == 0.0:
        ox_dt = overlap_length(x0, patch, head.L) * np.diff(edges)
    else:
        G = _overlap_primitive(x0 + v * edges, patch, head.L)
        ox_dt = np.diff(G) / v                                # m*s per gate
        # remove rounding residue (|value| < 1e-12 of a fully covered gate) so that
        # "overlaps the patch" is an exact statement
        ox_dt = np.where(ox_dt < 1e-12 * head.L * np.diff(edges), 0.0, ox_dt)
    return np.outer(oy, ox_dt) / (head.L * head.W)


def select(Wmat: np.ndarray, min_weight: float = 0.0) -> np.ndarray:
    """Gates and lanes 'whose apertures overlap' the patch (MODEL.md section 5): W > min_weight."""
    return Wmat > min_weight


def patch_sum(Wmat: np.ndarray, edges, mask=None):
    """Summed live time T_S (s) and summed weight W_S (s) over the selected gates and lanes."""
    dur = np.diff(np.asarray(edges, float))
    mask = select(Wmat) if mask is None else mask
    T_S = float(np.sum(mask * dur[None, :]))
    W_S = float(np.sum(Wmat[mask]))
    return T_S, W_S


def best_window(w_gate: np.ndarray, n: int):
    """Largest sum of n contiguous gates of a 1-D weight series, and its start index."""
    w_gate = np.asarray(w_gate, float)
    if n >= w_gate.size:
        return float(w_gate.sum()), 0
    c = np.concatenate([[0.0], np.cumsum(w_gate)])
    sums = c[n:] - c[:-n]
    i = int(np.argmax(sums))
    return float(sums[i]), i


def tumbling_cells(w_gate: np.ndarray, n: int, offset: int = 0) -> np.ndarray:
    """Sum a 1-D gate series into consecutive cells of n gates starting at index offset."""
    w = np.asarray(w_gate, float)[offset:]
    m = (w.size // n) * n
    return w[:m].reshape(-1, n).sum(axis=1)


def patch_dhash(T_S: float, W_S: float, u0sq: float, K: float, u_rel_K: float = 0.0,
                alpha: float = 0.05, beta: float = 0.05) -> float:
    """Patch activity density (Bq/cm2) detectable from the summed gates (MODEL.md section 5).

    The summed counts are treated with the section-3 expressions at T_F = T_S;
    the patch produces a mean net rate K*D_p*W_S/T_S, i.e. an effective response
    K*W_S/T_S. u0sq is u~^2(0) evaluated for T_F = T_S (and the matching T_U).
    """
    if W_S <= 0.0:
        return float("inf")
    return float(model.detection_limit_activity(u0sq, T_S, K * W_S / T_S, u_rel_K, alpha, beta))
