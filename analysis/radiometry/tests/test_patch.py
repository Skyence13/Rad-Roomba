"""Moving-patch overlap integrals, MODEL.md section 5."""
import numpy as np
import pytest

from rrrad import model, patch as p

H = p.Head()
V, GATE = 0.10, 0.10


def weights(pt, phase=0.0, **kw):
    ed = p.gate_edges_for_pass(H, pt, V, GATE, phase)
    return p.gate_weights(H, pt, V, ed, **kw), ed


def test_head_layout():
    assert H.aperture_area_cm2 == pytest.approx(80.0)
    assert H.seam_gap == pytest.approx(0.0075)
    assert np.allclose(H.lane_centres, [0.13125, 0.04375, -0.04375, -0.13125])   # as software/map_demo.py


def test_lane_centred_small_patch_total():
    pt = p.Patch.square(10.0, y=H.lane_centres[1])
    W, ed = weights(pt)
    # full-pass integral = (A_p/A_a) * L/v = (10/80) * 1 s, all in one lane
    assert W.sum() == pytest.approx(10.0 / 80.0 * H.L / V, rel=1e-12)
    assert np.count_nonzero(W.sum(axis=1)) == 1 and W[1].sum() == pytest.approx(W.sum())
    assert np.all(W >= 0) and W.max() <= GATE * 10.0 / 80.0 * (1 + 1e-9)


@pytest.mark.parametrize("phase", [0.0, 0.013, 0.05, 0.0999])
@pytest.mark.parametrize("area", [10.0, 100.0, 300.0])
def test_total_independent_of_gate_phase(phase, area):
    pt = p.Patch.square(area, y=H.lane_centres[2])
    W, _ = weights(pt, phase)
    oy = p.lateral_overlap(H, pt)
    assert W.sum() == pytest.approx(pt.lx * oy.sum() / (H.W * V), rel=1e-12)


def test_gate_integral_matches_numerical_quadrature():
    pt = p.Patch(0.0, H.lane_centres[0] + 0.01, 0.045, 0.02)
    W, ed = weights(pt, 0.037)
    for j in (3, 7, 9, 12):
        t = np.linspace(ed[j], ed[j + 1], 20001)
        w = p.overlap_length(pt.x + V * t, pt, H.L) * p.lateral_overlap(H, pt)[0] / (H.L * H.W)
        assert W[0, j] == pytest.approx(np.trapezoid(w, t), rel=1e-6, abs=1e-12)


def test_large_patch_saturates_to_uniform_response():
    pt = p.Patch(0.0, 0.0, 1.0, 1.0)         # covers every aperture for many gates
    W, ed = weights(pt)
    mid = W[:, W.shape[1] // 2]
    assert np.allclose(mid, GATE)             # w(t) = 1: E[N] = K * D * t_gate
    assert W.max() <= GATE * (1 + 1e-9)


def test_seam_cases():
    seam_y = 0.5 * (H.lane_centres[1] + H.lane_centres[2])
    # narrower than the 7.5 mm seam gap: invisible on this pass
    W, _ = weights(p.Patch(0.0, seam_y, 0.03, 0.007))
    assert W.sum() == 0.0
    # 10 cm2 square on the seam: loses the 7.5 mm gap, rest split equally
    pt = p.Patch.square(10.0, y=seam_y)
    W, _ = weights(pt)
    lane_sum = W.sum(axis=1)
    assert lane_sum[1] == pytest.approx(lane_sum[2]) and lane_sum[0] == lane_sum[3] == 0.0
    assert W.sum() == pytest.approx(0.125 * (pt.ly - H.seam_gap) / pt.ly, rel=1e-12)
    # second pass shifted by half a pitch puts the patch on a lane centre
    W2, _ = weights(pt, y_offset=H.pitch / 2)
    assert W2.sum() == pytest.approx(0.125, rel=1e-12)


def test_edge_cases():
    # outside the swath
    assert weights(p.Patch.square(100.0, y=0.5))[0].sum() == 0.0
    # zero-area patch
    assert weights(p.Patch(0.0, H.lane_centres[0], 0.0, 0.02))[0].sum() == 0.0
    # patch wider than the swath: every lane sees its own full width
    W, _ = weights(p.Patch(0.0, 0.0, 0.05, 1.0))
    assert np.allclose(W.sum(axis=1), 0.05 / V)
    # pass that ends when the aperture is centred on the patch: half of the integral
    pt = p.Patch.square(100.0, y=H.lane_centres[1])
    full, ed = weights(pt)
    half = p.gate_weights(H, pt, V, ed[ed <= 1e-12])
    assert half.sum() == pytest.approx(full.sum() / 2, rel=1e-12)
    # one long gate over the whole crossing equals the sum of the short gates
    one = p.gate_weights(H, pt, V, np.array([ed[0], ed[-1]]))
    assert one.sum() == pytest.approx(full.sum(), rel=1e-12)
    # stationary on the patch: w = overlap fraction, integral = w * t
    st = p.gate_weights(H, p.Patch.square(10.0, y=H.lane_centres[1]), 0.0, np.array([0.0, 30.0]))
    assert st[1, 0] == pytest.approx(30.0 * 10.0 / 80.0)
    # stationary beside the patch
    st0 = p.gate_weights(H, p.Patch.square(10.0, y=H.lane_centres[1]), 0.0, np.array([0.0, 30.0]), x_start=0.5)
    assert st0.sum() == 0.0


def test_selection_and_summation():
    pt = p.Patch.square(10.0, y=H.lane_centres[1])
    W, ed = weights(pt)
    T_S, W_S = p.patch_sum(W, ed)
    n_gates = np.count_nonzero(W[1])
    assert T_S == pytest.approx(n_gates * GATE) and W_S == pytest.approx(0.125)
    # crossing lasts (L + lx)/v = 1.316 s, from -0.658 s to +0.658 s:
    # 14 gates when a gate edge is at t = 0, 15 when the patch centre is mid-gate
    assert n_gates == 14
    W2, ed2 = weights(pt, 0.05)
    assert np.count_nonzero(W2[1]) == 15
    assert p.patch_sum(W2, ed2)[0] == pytest.approx(1.5)
    # a 100 cm2 square centred on a lane spills 2.5 mm into both neighbours
    big = p.Patch.square(100.0, y=H.lane_centres[1])
    Wb, edb = weights(big)
    assert np.count_nonzero(Wb.sum(axis=1)) == 3
    T_all, W_all = p.patch_sum(Wb, edb)
    T_main, W_main = p.patch_sum(Wb, edb, p.select(Wb, 0.1 * Wb.max()))
    assert T_all > 2.9 * T_main / 1.0 * 0.9 and W_main / W_all > 0.93     # 3x the time for 6 % more signal


def test_windows():
    pt = p.Patch.square(10.0, y=H.lane_centres[1])
    W, _ = weights(pt, 0.0)
    best, i = p.best_window(W[1], 10)
    assert best <= W[1].sum() + 1e-15 and best > 0.9 * W[1].sum()
    # tumbling 1 s cells: aligned captures most in one cell, misaligned splits about in half
    c_split = p.tumbling_cells(W[1], 10, offset=np.argmax(W[1]) % 10 + 1)
    assert c_split.sum() <= W[1].sum() + 1e-15
    assert p.best_window(W[1], 10_000)[0] == pytest.approx(W[1].sum())


def test_patch_dhash_scales_with_dilution():
    v0 = model.u0sq_comp(3.3, 1.4, 1.4, 1.0, 0.5)
    full = model.detection_limit_activity(v0, 1.4, 24.0)
    d = p.patch_dhash(1.4, 0.125, v0, 24.0)
    assert d == pytest.approx(float(full) * 1.4 / 0.125, rel=1e-12)
    assert np.isinf(p.patch_dhash(1.4, 0.0, v0, 24.0))
