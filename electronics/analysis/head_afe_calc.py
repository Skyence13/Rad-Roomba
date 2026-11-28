#!/usr/bin/env python3
"""RR-HEAD-ACQ analogue front-end budget calculator.

Regenerates every table quoted in head_afe_budget.md:

    python3 electronics/analysis/head_afe_calc.py            # prints markdown tables
    python3 electronics/analysis/head_afe_calc.py --plots    # also writes head_afe_*.png

Evidence classes used in the output:
    datasheet  - value read from the manufacturer PDF named in SOURCES
    calculated - derived here from datasheet + assumed inputs
    assumed    - design range chosen by the head electronics lead (no measurement exists)
Nothing here is measured.  numpy/scipy only.
"""
import math
import sys
import numpy as np
from scipy import signal

Q_E = 1.602e-19
K_B = 1.381e-23
T_K = 293.0

SOURCES = {
    "J60035": "onsemi MICROJ-SERIES/D Rev. 9 (Oct 2026), Tables 1-4",
    "S14160": "Hamamatsu S14160/S14161 series KAPD1064E",
    "S13360": "Hamamatsu S13360 series KAPD1052E",
    "NUVMT": "Broadcom AFBR-S4N66P024M-DS (DS104)",
}

# ----------------------------------------------------------------------------- SiPM candidates (datasheet)
# dcr = dark count rate per device at 25 C [1/s]; ct = crosstalk probability; trec = microcell recharge [s]
SIPM = {
    # name: dict(...)
    "J60035@2.5V": dict(src="J60035", area_mm2=36.8, ncell=22292, vbr=24.45, vbr_tol=0.25, beta=21.5e-3, vov=2.5,
                        gain=2.9e6, pde=0.38, dcr=50e3 * 36.8, dcr_max=150e3 * 36.8, ct=0.08, cd=4140e-12, trec=50e-9,
                        idark_typ=0.9e-6, idark_max=1.25e-6, top=(-40, 85)),
    "J60035@6V": dict(src="J60035", area_mm2=36.8, ncell=22292, vbr=24.45, vbr_tol=0.25, beta=21.5e-3, vov=6.0,
                      gain=6.3e6, pde=0.50, dcr=150e3 * 36.8, dcr_max=None, ct=0.25, cd=4140e-12, trec=50e-9,
                      idark_typ=7.5e-6, idark_max=12e-6, top=(-40, 85)),
    "J30035@2.5V": dict(src="J60035", area_mm2=9.42, ncell=5676, vbr=24.45, vbr_tol=0.25, beta=21.5e-3, vov=2.5,
                        gain=2.9e6, pde=0.38, dcr=50e3 * 9.42, dcr_max=150e3 * 9.42, ct=0.08, cd=1070e-12, trec=45e-9,
                        idark_typ=0.23e-6, idark_max=0.31e-6, top=(-40, 85)),
    "S14160-6050HS": dict(src="S14160", area_mm2=36.0, ncell=14331, vbr=38.0, vbr_tol=None, beta=34e-3, vov=2.7,
                          gain=2.5e6, pde=0.50, dcr=None, dcr_max=None, ct=0.07, cd=2000e-12, trec=None,
                          idark_typ=2.5e-6, idark_max=7.5e-6, top=(-40, 85)),
    "S13360-6050PE": dict(src="S13360", area_mm2=36.0, ncell=14400, vbr=53.0, vbr_tol=5.0, beta=54e-3, vov=3.0,
                          gain=1.7e6, pde=0.40, dcr=2.0e6, dcr_max=6.0e6, ct=0.03, cd=1280e-12, trec=None,
                          idark_typ=None, idark_max=None, top=(-20, 60)),
    "NUV-MT 6x6 @12V": dict(src="NUVMT", area_mm2=36.0, ncell=22428, vbr=32.5, vbr_tol=None, beta=30e-3, vov=12.0,
                            gain=7.3e6, pde=0.63, dcr=4.4e6, dcr_max=None, ct=0.23, cd=1550e-12, trec=55e-9,
                            idark_typ=8.6e-6, idark_max=None, top=(-20, 60)),
}
# values not in the datasheets, filled with labelled assumptions/derivations
for k, s in SIPM.items():
    s["notes"] = []
    if s["dcr"] is None:        # Hamamatsu S14160: only dark current is specified -> derive DCR
        s["dcr"] = s["idark_typ"] / (s["gain"] * Q_E * (1 + s["ct"]))
        s["dcr_max"] = s["idark_max"] / (s["gain"] * Q_E * (1 + s["ct"]))
        s["notes"].append("DCR calculated from dark current / (gain*e*(1+ct))")
    if s["trec"] is None:       # not specified: assume Rq*Ccell-class 50 um cell value
        s["trec"] = 50e-9
        s["notes"].append("recharge 50 ns ASSUMED (not in datasheet)")
    if s["dcr_max"] is None:
        s["dcr_max"] = 3.0 * s["dcr"]
        s["notes"].append("DCR max ASSUMED 3x typ")
# OEM may tile several devices in parallel on one guide (design-range upper end)
ARRAY4 = dict(SIPM["J60035@2.5V"])
ARRAY4.update(dcr=4 * ARRAY4["dcr"], dcr_max=4 * ARRAY4["dcr_max"], cd=4 * ARRAY4["cd"], area_mm2=4 * 36.8,
              idark_typ=4 * 0.9e-6, notes=["4 devices in parallel (ASSUMED OEM option)"])
SIPM["4x J60035@2.5V"] = ARRAY4

T_HALF_C = 8.0          # assumed: DCR halves every 8 C (design range 7..10 C)
T_HALF_RANGE = (7.0, 10.0)

# ----------------------------------------------------------------------------- circuit values (must match circuit.py)
CIR = dict(
    R_IN=10.0,          # anode load resistor [ohm]: 2 x 20.0 in parallel fitted (selectable 5..49.9)
    R_SER=22.0,         # series protection resistor at preamp input
    R_F1=499.0, R_G1=24.9, G1=1 + 499.0 / 24.9, GBW1=300e6,     # OPA838 preamp
    C_D=220e-12, R_D=100.0, R_PZ=None,   # fast CR; R_PZ fitted at bring-up = trec/C_D
    C_PZ=47e-9,                          # stage 3 (S3-04): DC block in series with R_PZ (None = stage-1 network)
    R_PIN=1000.0, C_AC=100e-9, C_G1=10e-6,   # input AC coupling to VBL, preamp R_G AC ground (low-frequency poles)
    C_TRIM=4.8e-6, R_TRIMS=4990.0,       # trim node AC ground and sense resistor (slow anode-node step after big pulses)
    G2=1 + 499.0 / 24.9, GBW2=300e6, R_F2=499.0, C_F2=10e-12,
    R_S1=1000.0, C_S1=1e-9,              # slow integrator 1 us
    C_S2=4.7e-9, R_S3=10e3,              # slow baseline CR
    G3=1 + 2000.0 / 499.0, GBW3=205e6,   # OPA836
    V_BL=0.600, V_CLAMP=3.3 + 0.3, V_THR_MAX=2.5,
    EN_AMP=1.8e-9, IN_AMP=1.0e-12,       # OPA838 input noise (datasheet 1.8 nV/rtHz; current noise assumed 1 pA/rtHz)
    C_INJ=100e-12, V_TP_MAX=2.5,
    DAC_BITS=12, DAC_FS=2.5,
    CMP_VOS_MAX=6.5e-3, CMP_HYST=6e-3, CMP_TPD=4.5e-9, CMP_TPD_5MV=7.5e-9,
    LATCH_TW=3.3e-9,                     # SN74LVC74A min clock pulse width
    T_SERVICE=10e-6, W_ACCEPT=4e-6, T_ISR=1.5e-6,   # T_ISR assumed until measured
)

# scintillation time profiles (assumed; literature-class values, to be replaced by OEM pulse data)
TAU_PLASTIC = 2.4e-9     # EJ-212 class decay
ZNS = [(0.70, 200e-9), (0.30, 5e-6)]   # ZnS(Ag): fraction, decay (fast 200 ns + slow tail lumped at 5 us)

# photo-electron design ranges (assumed)
PE = dict(spe=1, beta_min=4, beta_typ=15, beta_max=120, alpha_min=150, alpha_typ=1500, alpha_max=15000,
          ref_min=10, ref_typ=80, ref_max=600)


def tf_lp(tau):
    return signal.TransferFunction([1.0], [tau, 1.0])


class Chain:
    """Series connection of low-order stages, evaluated stage by stage (a single high-order polynomial is badly
    conditioned once the poles span nanoseconds to tens of microseconds, e.g. with the S3-04 C_PZ)."""

    def __init__(self, stages):
        self.stages = []
        for t in stages:
            self.stages += t.stages if isinstance(t, Chain) else [t]

    def freq(self, w):
        h = np.ones_like(w, dtype=complex)
        for t in self.stages:
            h = h * signal.freqresp(t, w)[1]
        return h


def cascade(*tfs):
    return Chain(tfs)


def freq(tf, w):
    return tf.freq(w) if isinstance(tf, Chain) else signal.freqresp(tf, w)[1]


def chain_tfs(cd, trec, r_in=None, r_pz="match"):
    """Transfer functions from SiPM current [A] to node voltages [V]."""
    c = CIR
    r_in = c["R_IN"] if r_in is None else r_in
    tau_in = r_in * cd
    zin = signal.TransferFunction([r_in], [tau_in, 1.0])            # node A (anode), V per A
    pre = signal.TransferFunction([c["G1"]], [c["G1"] / (2 * math.pi * c["GBW1"]), 1.0])
    # fast CR with optional pole-zero: H = R_D (1 + s R_PZ C_D) / (R_D + R_PZ + s R_D R_PZ C_D)
    if r_pz == "match":
        r_pz = trec / c["C_D"]
    if r_pz is None:
        cr = signal.TransferFunction([c["R_D"] * c["C_D"], 0.0], [c["R_D"] * c["C_D"], 1.0])
    elif c.get("C_PZ") is None:
        cr = signal.TransferFunction([c["R_D"] * r_pz * c["C_D"], c["R_D"]],
                                     [c["R_D"] * r_pz * c["C_D"], c["R_D"] + r_pz])
    else:
        # S3-04: (R_PZ + 1/(s C_PZ)) || C_D from PRE to FS, R_D to the baseline: no DC transmission
        cp, cd_, rd = c["C_PZ"], c["C_D"], c["R_D"]
        cr = signal.TransferFunction([rd * cd_ * cp * r_pz, rd * (cp + cd_), 0.0],
                                     [rd * cd_ * cp * r_pz, rd * (cp + cd_) + cp * r_pz, 1.0])
    g2 = signal.TransferFunction([c["G2"]], [c["R_F2"] * c["C_F2"], 1.0])
    g2bw = tf_lp(c["G2"] / (2 * math.pi * c["GBW2"]))
    fast = cascade(zin, pre, cr, g2, g2bw)
    # slow: RC integrator, CR baseline (loaded divider), gain
    integ = tf_lp(c["R_S1"] * c["C_S1"])
    tau_cr = (c["R_S1"] + c["R_S3"]) * c["C_S2"]
    crs = signal.TransferFunction([c["R_S3"] * c["C_S2"], 0.0], [tau_cr, 1.0])
    g3 = signal.TransferFunction([c["G3"]], [c["G3"] / (2 * math.pi * c["GBW3"]), 1.0])
    slow = cascade(zin, pre, integ, crs, g3)
    return dict(node_a=zin, pre=cascade(zin, pre), fast=fast, slow=slow, tau_in=tau_in, r_pz=r_pz)


def sipm_current(t, q, trec, light):
    """Current waveform [A] for charge q with exponential recharge and scintillator profile light=[(frac,tau)]."""
    dt = t[1] - t[0]
    cell = np.exp(-t / trec) / trec
    emit = np.zeros_like(t)
    for frac, tau in light:
        emit += frac * np.exp(-t / tau) / tau
    emit /= emit.sum() * dt
    i = signal.fftconvolve(emit, cell)[: len(t)] * dt
    return q * i / (i.sum() * dt) if False else q * i   # area of i is ~1 over a long window


def respond(tf, t, x):
    for st in (tf.stages if isinstance(tf, Chain) else [tf]):
        _, x, _ = signal.lsim(st, U=x, T=t)
    return x


_PM_CACHE = {}


def pulse_metrics(s, kind):
    """Peak volts per photo-electron at each node, shapes for beta (plastic) or alpha (ZnS) (cached)."""
    key = (id(s), kind, CIR.get("C_PZ"), CIR["R_IN"])
    if key not in _PM_CACHE:
        _PM_CACHE[key] = _pulse_metrics(s, kind)
    return _PM_CACHE[key]


def _pulse_metrics(s, kind):
    tfs = chain_tfs(s["cd"], s["trec"])
    q1 = s["gain"] * Q_E
    if kind == "beta":
        t = np.arange(0, 1.2e-6, 0.2e-9)
        light = [(1.0, TAU_PLASTIC)]
    else:
        t = np.arange(0, 60e-6, 2e-9)
        light = ZNS
    i = sipm_current(t, q1, s["trec"], light)
    out = {"t": t, "i_peak": i.max(), "q1": q1, "tau_in": tfs["tau_in"], "r_pz": tfs["r_pz"]}
    for node in ("node_a", "pre", "fast", "slow"):
        y = respond(tfs[node], t, i)
        out[node] = y
        out[node + "_pk"] = y.max()
        out[node + "_tpk"] = t[y.argmax()]
        out[node + "_min"] = y.min()
    yf = out["fast"]
    dt = t[1] - t[0]
    out["fast_area_over_peak"] = yf.clip(min=0).sum() * dt / yf.max()
    above = np.where(yf > 0.5 * yf.max())[0]
    out["fast_fwhm"] = (above[-1] - above[0]) * dt
    return out


# ----------------------------------------------------------------------------- noise
def enc_pe(s):
    """Equivalent noise charge of the fast path in photo-electrons rms (calculated)."""
    c = CIR
    tfs = chain_tfs(s["cd"], s["trec"])
    f = np.logspace(3, 9, 4000)
    w = 2 * math.pi * f
    # transfer from a voltage at the preamp + input to the fast output = fast / zin
    h_fast = freq(tfs["fast"], w)
    h_zin = freq(tfs["node_a"], w)
    h_v = h_fast / h_zin
    rp = c["R_F1"] * c["R_G1"] / (c["R_F1"] + c["R_G1"])
    en2_amp = c["EN_AMP"] ** 2 + 4 * K_B * T_K * (c["R_SER"] + rp) + (c["IN_AMP"] * (rp + c["R_SER"])) ** 2
    # R_IN thermal noise current flows in R_IN || C_d -> appears as voltage through zin/R_IN shaping
    v2_rin = 4 * K_B * T_K * c["R_IN"] * np.abs(h_zin / c["R_IN"]) ** 2
    s_out = (en2_amp + v2_rin) * np.abs(h_v) ** 2
    vn = math.sqrt(np.trapezoid(s_out, f))
    m = pulse_metrics(s, "beta")
    return vn, vn / m["fast_pk"], math.sqrt(en2_amp)


# ----------------------------------------------------------------------------- dark-count pile-up
def borel_pmf(p_ct, kmax):
    mu = -math.log(1 - p_ct) if p_ct > 0 else 0.0
    pm = np.zeros(kmax + 1)
    for k in range(1, kmax + 1):
        if mu == 0:
            pm[k] = 1.0 if k == 1 else 0.0
        else:
            pm[k] = math.exp(-mu * k + (k - 1) * math.log(mu * k) - math.lgamma(k + 1))
    return pm


def dark_trigger_rate(rate, tau_r, p_ct, n_thr, kmax=60):
    """Rate [1/s] of upward crossings of level (n_thr - 0.5) p.e. by dark pulses.

    Rectangular resolving-time model: the amplitude seen by a new dark pulse is the compound-Poisson
    sum S of earlier pulses inside tau_r.  A trigger occurs when S < n_thr and S + A >= n_thr.
    """
    a = borel_pmf(p_ct, kmax)
    lam = rate * tau_r
    # Panjer recursion for compound Poisson with severity a[k]
    s = np.zeros(kmax + 1)
    s[0] = math.exp(-lam)
    for j in range(1, kmax + 1):
        k = np.arange(1, j + 1)
        s[j] = lam / j * np.sum(k * a[k] * s[j - k])
    tail = np.concatenate([np.cumsum(a[::-1])[::-1], [0.0]])   # tail[k] = P(A >= k)
    tot = 0.0
    for j in range(0, n_thr):
        need = n_thr - j
        tot += s[j] * (tail[need] if need <= kmax else 0.0)
    return rate * tot


def lowest_lld(rate, tau_r, p_ct, target):
    for n in range(2, 60):
        if dark_trigger_rate(rate, tau_r, p_ct, n) < target:
            return n
    return None


def mc_dark_rate(rate, p_ct, shape_t, shape_y, n_thr, t_total, seed=1):
    """Monte-Carlo cross-check with the real shaped pulse (peak normalised to 1 p.e.)."""
    rng = np.random.default_rng(seed)
    dt = shape_t[1] - shape_t[0]
    nseg = int(t_total / 2e-3)
    cross = 0
    a = borel_pmf(p_ct, 40)
    a = a / a.sum()
    for _ in range(nseg):
        n = rng.poisson(rate * 2e-3)
        times = np.sort(rng.uniform(0, 2e-3, n))
        amps = rng.choice(np.arange(41), size=n, p=a)
        idx = (times / dt).astype(int)
        x = np.zeros(int(2e-3 / dt) + len(shape_y))
        np.add.at(x, idx, amps)
        y = signal.fftconvolve(x, shape_y)[: len(x)]
        above = y > (n_thr - 0.5)
        cross += int(np.count_nonzero(above[1:] & ~above[:-1]))
    return cross / (nseg * 2e-3)


def check_against_circuit():
    """Compare the values used here with electronics/head_acq/design/circuit.py (channel F0)."""
    import importlib.util
    import os
    import sys as _sys
    import types
    board_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "head_acq")
    _sys.path.insert(0, board_dir)
    import overrides                       # stage-1 circuit.py + the stage-2/3 override layer = the board as built
    parts, _log = overrides.apply(overrides.load_circuit().PARTS)
    cir = types.SimpleNamespace(PARTS=parts)

    def between(a, b, kind):
        out = []
        for p in cir.PARTS:
            if p["dnp"] or not p["ref"].startswith(kind) or len(p["pins"]) != 2:
                continue
            nets = {v[1] for v in p["pins"].values() if v}
            if nets == {a, b}:
                out.append(p)
        return out

    def rpar(a, b):
        rs = [p["ohms"] for p in between(a, b, "R")]
        return 1.0 / sum(1.0 / r for r in rs)

    def cap(a, b):
        mult = {"pF": 1e-12, "nF": 1e-9, "uF": 1e-6}
        tot = 0.0
        for p in between(a, b, "C"):
            v = p["value"]
            tot += float(v[:-2]) * mult[v[-2:]]
        return tot
    c = CIR
    got = {
        "R_IN": rpar("F0_A", "F0_TRIM"), "R_SER": rpar("F0_A", "F0_PINA"),
        "G1": 1 + rpar("F0_PRE", "F0_PFB") / rpar("F0_PFB", "F0_PG"),
        "C_D": cap("F0_PRE", "F0_FS"), "R_D": rpar("F0_FS", "F0_VBL"),
        "G2": 1 + rpar("F0_FAST", "F0_FFB") / rpar("F0_FFB", "F0_VBL"), "C_F2": cap("F0_FAST", "F0_FFB"),
        "R_S1": rpar("F0_PRE", "F0_SI"), "C_S1": cap("F0_SI", "GND"), "C_S2": cap("F0_SI", "F0_SS"),
        "R_S3": rpar("F0_SS", "F0_VBL"), "G3": 1 + rpar("F0_SLOW", "F0_SFB") / rpar("F0_SFB", "F0_VBL"),
        "C_INJ": cap("F0_TPI", "F0_A"),
        "R_PIN": rpar("F0_PIN", "F0_VBL"), "C_AC": cap("F0_PINA", "F0_PIN"), "C_G1": cap("F0_PG", "GND"),
    }
    if c.get("C_PZ") is not None:
        got["C_PZ"] = cap("F0_PZ", "F0_FS")
    bad = {k: (v, c[k]) for k, v in got.items() if abs(v - c[k]) > 1e-3 * abs(c[k])}
    rpz = rpar("F0_PRE", "F0_PZ") if c.get("C_PZ") is not None else rpar("F0_PRE", "F0_FS")
    taps = {n: rpar(a, b) for n, (a, b) in (("FAST tap", ("F0_FAST", "F0_MFAST")), ("SLOW tap", ("F0_SLOW", "F0_MSLOW")),
                                            ("PRE tap", ("F0_PRE", "F0_MPRE")))}
    return bad, rpz, taps


# ----------------------------------------------------------------------------- stage 3 (review REVIEW_head_interference.md)
def tot_ns(y, t, thr):
    """Time over threshold (first to last sample above thr) [ns]."""
    a = np.where(y > thr)[0]
    return (a[-1] - a[0]) * (t[1] - t[0]) * 1e9 if len(a) else 0.0


def tot_rows(thr_pe=(8, 10), betas=(30, 120, 240), alphas=(150, 300, 1500, 15000)):
    """TOT of the FAST pulse at the LLD (in units of the beta single-p.e. amplitude, as the thresholds are set),
    clamped at the comparator clamp, for beta (plastic) and alpha (ZnS) pulses of each candidate device."""
    lim = CIR["V_CLAMP"] - CIR["V_BL"]
    rows = []
    for k, s in SIPM.items():
        mb, ma = pulse_metrics(s, "beta"), pulse_metrics(s, "alpha")
        u = mb["fast_pk"]
        for thr in thr_pe:
            tb = [tot_ns(np.minimum(n * mb["fast"], lim) / u, mb["t"], thr - 0.5) for n in betas]
            ta = [tot_ns(np.minimum(n * ma["fast"], lim) / u, ma["t"], thr - 0.5) for n in alphas]
            rows.append((k, thr, tb, ta, mb["fast_pk"] / mb["slow_pk"], ma["fast_pk"] / ma["slow_pk"]))
    return rows


def lf_tail(npe, cpz, trim=True, s=None, t_end=700e-6, dt=10e-9):
    """Low-frequency FAST tail after an alpha of npe p.e. (J60035 unless s given), in p.e. of the beta FAST amplitude.
    Model (t >> 100 ns, fast poles dropped): anode node = R_IN + trim node (C_TRIM to a 4.99 k / C_TRIM recovery),
    input coupling C_AC into R_PIN (+22 ohm), preamp G1(s) with R_G to C_G1, PZ branch with or without C_PZ, G2."""
    c = CIR
    s = s or SIPM["J60035@2.5V"]
    rin, ct, tt = c["R_IN"], c["C_TRIM"], c["R_TRIMS"] * c["C_TRIM"]
    za = ([rin * ct, rin * ct / tt + 1.0], [ct, ct / tt]) if trim else ([rin], [1.0])
    tc = (c["R_PIN"] + c["R_SER"]) * c["C_AC"]
    hp = ([tc, 0.0], [tc, 1.0])
    g1 = ([c["C_G1"] * (c["R_G1"] + c["R_F1"]), 1.0], [c["C_G1"] * c["R_G1"], 1.0])
    rpz = s["trec"] / c["C_D"]
    pz = ([c["R_D"] / (c["R_D"] + rpz)], [1.0]) if cpz is None else ([cpz * c["R_D"], 0.0], [cpz * (c["R_D"] + rpz), 1.0])
    num, den = np.array([c["G2"]]), np.array([1.0])
    for n_, d_ in (za, hp, g1, pz):
        num, den = np.polymul(num, n_), np.polymul(den, d_)
    t = np.arange(0, t_end, dt)
    q = npe * s["gain"] * Q_E
    i = q * sum(f / tau * np.exp(-t / tau) for f, tau in ZNS)
    _, y, _ = signal.lsim(signal.TransferFunction(num, den), i, t)
    return t, y / pulse_metrics(s, "beta")["fast_pk"]


def mutual(a1, a2, r):
    """Coaxial-dipole mutual inductance (most favourable orientation), SI units."""
    return 4e-7 * math.pi * a1 * a2 / (2 * math.pi * r ** 3)


def emf_pe(emf, t_edge, s=None):
    """FAST response [p.e.] to a series EMF of amplitude emf lasting t_edge in the SiPM loop: Norton current
    i = C_d de/dt (two opposite impulses) into the input node; peak of the FAST response / FAST per p.e."""
    s = s or SIPM["J60035@2.5V"]
    tfs = chain_tfs(s["cd"], s["trec"])
    t = np.arange(0, 2e-6, 0.2e-9)
    x = np.zeros_like(t)
    x[0] = 2.0 / (t[1] - t[0])          # lsim interpolates linearly: a one-sample triangle of height 2/dt has area 1
    h = respond(tfs["fast"], t, x)
    n = int(round(t_edge / (t[1] - t[0])))
    y = s["cd"] * emf * (h - np.concatenate([np.zeros(n), h[:-n]]))
    return np.abs(y).max() / pulse_metrics(s, "beta")["fast_pk"]


def efficiency(mu_mpv, n_thr, scale=0.34, ngrid=4000):
    """P(N >= n_thr) for a MIP-class deposit: x = E/E_MPV ~ Moyal(1, scale) (scale 0.34 -> MPV = 0.70 x mean, assumed),
    N ~ Poisson(mu_mpv x)."""
    from scipy import stats
    x = np.linspace(0.05, 12, ngrid)
    w = stats.moyal.pdf(x, loc=1.0, scale=scale)
    w /= w.sum()
    return float(np.sum(w * stats.poisson.sf(n_thr - 1, mu_mpv * x)))


def mu_required(n_thr, eff=0.9):
    lo, hi = 0.5, 200.0
    for _ in range(60):
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if efficiency(m, n_thr) < eff else (lo, m)
    return hi


# ----------------------------------------------------------------------------- report helpers
def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def eng(x, unit="", digits=3):
    if x is None:
        return "n/a"
    if x == 0:
        return "0 " + unit
    e = int(math.floor(math.log10(abs(x)) / 3) * 3)
    e = max(-15, min(9, e))
    pre = {-15: "f", -12: "p", -9: "n", -6: "u", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}[e]
    return ("%." + str(digits) + "g %s%s") % (x / 10 ** e, pre, unit)


def section(title):
    print("\n### " + title + "\n")


def main():
    c = CIR
    plots = "--plots" in sys.argv
    print("# head_afe_calc.py output (regenerate: python3 electronics/analysis/head_afe_calc.py)")

    # ---- T1 candidates
    section("T1 SiPM candidates (datasheet unless noted)")
    rows = []
    for k, s in SIPM.items():
        rows.append([k, "%.1f" % s["vbr"], "%.1f" % (s["beta"] * 1e3), "%.1f" % s["vov"], "%.2g" % s["gain"],
                     "%.0f" % (s["pde"] * 100), "%.2f" % (s["dcr"] / 1e6), "%.2f" % (s["dcr_max"] / 1e6),
                     "%.0f" % (s["ct"] * 100), "%.0f" % (s["cd"] * 1e12), "%.0f" % (s["trec"] * 1e9),
                     "%d..%d" % s["top"], "; ".join(s["notes"]) or SOURCES[s["src"]]])
    print(md_table(["device", "Vbr V", "dVbr/dT mV/C", "Vov V", "gain", "PDE %", "DCR typ MHz @25C", "DCR max MHz",
                    "crosstalk %", "Ct pF", "recharge ns", "Top C", "source / note"], rows))

    # ---- T2 signal per p.e.
    section("T2 Signal per photo-electron at each node (calculated; R_IN = %.1f ohm, G1 = %.1f, G2 = %.1f, G3 = %.2f, "
            "pole-zero resistor matched to the recharge time)" % (c["R_IN"], c["G1"], c["G2"], c["G3"]))
    rows = []
    met = {}
    for k, s in SIPM.items():
        mb = pulse_metrics(s, "beta")
        ma = pulse_metrics(s, "alpha")
        met[k] = (mb, ma)
        rows.append([k, "%.3f" % (mb["q1"] * 1e12), "%.0f" % (mb["tau_in"] * 1e9), "%.0f" % mb["r_pz"],
                     "%.1f" % (mb["i_peak"] * 1e6), "%.1f" % (mb["node_a_pk"] * 1e6), "%.2f" % (mb["pre_pk"] * 1e3),
                     "%.2f" % (mb["fast_pk"] * 1e3), "%.0f" % (mb["fast_tpk"] * 1e9), "%.0f" % (mb["fast_fwhm"] * 1e9),
                     "%.0f" % (mb["fast_area_over_peak"] * 1e9), "%.3f" % (mb["slow_pk"] * 1e3),
                     "%.3f" % (ma["fast_pk"] * 1e3), "%.3f" % (ma["slow_pk"] * 1e3), "%.2f" % (ma["slow_tpk"] * 1e6)])
    print(md_table(["device", "Q/p.e. pC", "tau_in ns", "R_PZ ohm", "I pk uA/p.e. (beta)", "node A uV/p.e.",
                    "preamp mV/p.e.", "FAST mV/p.e. (beta)", "t_peak ns", "FWHM ns", "resolving time ns",
                    "SLOW mV/p.e. (beta)", "FAST mV/p.e. (alpha)", "SLOW mV/p.e. (alpha)", "SLOW t_peak us (alpha)"],
                   rows))

    # ---- T3 amplitudes for the event classes
    section("T3 Amplitudes above baseline for the assumed photo-electron design range (calculated; linear values, "
            "'CLIP' = exceeds the stage or clamp limit and saturates)")
    lim_pre = 4.85 - c["V_BL"]
    lim_fast = c["V_CLAMP"] - c["V_BL"]
    rows = []
    for k in ("J60035@2.5V", "S14160-6050HS", "S13360-6050PE", "NUV-MT 6x6 @12V", "4x J60035@2.5V"):
        mb, ma = met[k]
        for name, npe, m in (("single p.e.", PE["spe"], mb), ("beta min", PE["beta_min"], mb),
                             ("beta typ", PE["beta_typ"], mb), ("beta max", PE["beta_max"], mb),
                             ("alpha min", PE["alpha_min"], ma), ("alpha typ", PE["alpha_typ"], ma),
                             ("alpha max", PE["alpha_max"], ma)):
            def v(x, lim):
                return ("%.3g V" % x) if x < lim else "CLIP (%.3g V lin.)" % x
            rows.append([k, name, npe, "%.3g" % (npe * m["q1"] * 1e12), "%.3g" % (npe * m["i_peak"] * 1e3),
                         v(npe * m["node_a_pk"], 5.6), v(npe * m["pre_pk"], lim_pre), v(npe * m["fast_pk"], lim_fast),
                         v(npe * m["slow_pk"], lim_fast)])
    print(md_table(["device", "pulse", "p.e.", "charge pC", "I peak mA", "node A", "preamp out", "FAST out",
                    "SLOW out"], rows))
    print("\nLinear limits above baseline: preamp %.2f V, FAST/SLOW at the comparator (Schottky clamp) %.2f V, "
          "highest threshold %.2f V above ground = %.2f V above baseline." %
          (lim_pre, lim_fast, c["V_THR_MAX"], c["V_THR_MAX"] - c["V_BL"]))

    # ---- T4 threshold scale
    section("T4 Threshold scale and DAC resolution (calculated)")
    lsb = c["DAC_FS"] / 2 ** c["DAC_BITS"]
    rows = []
    for k, (mb, ma) in met.items():
        span = (c["V_THR_MAX"] - c["V_BL"])
        rows.append([k, "%.2f" % (mb["fast_pk"] * 1e3), "%.3f" % (lsb / mb["fast_pk"]), "%.0f" % (span / mb["fast_pk"]),
                     "%.2f" % (c["CMP_VOS_MAX"] / mb["fast_pk"]), "%.2f" % (c["CMP_HYST"] / mb["fast_pk"]),
                     "%.3f" % (ma["slow_pk"] * 1e3), "%.0f" % (span / ma["slow_pk"])])
    print(md_table(["device", "FAST mV/p.e.", "DAC LSB p.e. (12 bit, 0.61 mV)", "max BETA_ULD p.e.",
                    "comparator offset max p.e. (6.5 mV)", "hysteresis p.e. (6 mV)", "SLOW mV/p.e. (alpha)",
                    "max ALPHA threshold p.e."], rows))

    # ---- T5 electronic noise
    section("T5 Electronic noise of the fast path (calculated)")
    rows = []
    for k, s in SIPM.items():
        vn, enc, en_in = enc_pe(s)
        rows.append([k, "%.0f" % (s["cd"] * 1e12), "%.2f" % (en_in * 1e9), "%.2f" % (vn * 1e3), "%.3f" % enc])
    print(md_table(["device", "Ct pF", "input-referred e_n nV/rtHz (amp + resistors)", "FAST output noise mV rms",
                    "ENC p.e. rms"], rows))

    # ---- calibrate the rectangular-window model against a Monte-Carlo with the real pulse shape
    s0 = SIPM["J60035@2.5V"]
    mb0 = met["J60035@2.5V"][0]
    dt = 1e-9
    tt = np.arange(0, 600e-9, dt)
    shape = np.interp(tt, mb0["t"], mb0["fast"]) / mb0["fast_pk"]
    mc_rows = {n: mc_dark_rate(s0["dcr"], s0["ct"], tt, shape, n, 0.2) for n in (3, 4, 5)}
    best = None
    for fcal in np.arange(0.2, 1.21, 0.02):
        err = sum((math.log(dark_trigger_rate(s0["dcr"], fcal * mb0["fast_area_over_peak"], s0["ct"], n) / mc_rows[n])) ** 2
                  for n in (3, 4, 5))
        if best is None or err < best[0]:
            best = (err, fcal)
    F_CAL = best[1]

    # ---- T6 dark-count limited threshold
    section("T6 Lowest usable BETA_LLD from dark-count pile-up (calculated from datasheet DCR, crosstalk and the "
            "resolving time of T2 x %.2f (factor fitted to the Monte-Carlo below); DCR(T) = DCR(25 C) * 2^((T-25)/%.0f C) "
            "assumed, range %.0f..%.0f C)" % (F_CAL, T_HALF_C, *T_HALF_RANGE))
    temps = (25, 10, 0, -20)
    hdr = ["device", "DCR case"] + ["%+d C: LLD p.e. for <1/s (<0.1/s) [<0.05/s]" % t for t in temps]
    LLD005 = {}
    rows = []
    for k, s in SIPM.items():
        mb = met[k][0]
        for case, d in (("typ", s["dcr"]), ("max", s["dcr_max"])):
            r = [k, case]
            for t in temps:
                rate = d * 2 ** ((t - 25) / T_HALF_C)
                n1 = lowest_lld(rate, F_CAL * mb["fast_area_over_peak"], s["ct"], 1.0)
                n01 = lowest_lld(rate, F_CAL * mb["fast_area_over_peak"], s["ct"], 0.1)
                n005 = lowest_lld(rate, F_CAL * mb["fast_area_over_peak"], s["ct"], 0.05)
                LLD005[(k, case, t)] = n005
                r.append("%s (%s) [%s]  DCR %.2g/s" % (n1, n01, n005, rate))
            rows.append(r)
    print(md_table(hdr, rows))
    print("\nThe table gives the integer n such that a threshold at (n - 0.5) p.e. has a dark trigger rate below the "
          "target.  Stage 3 design criterion (review M1): dark triggers <= 0.05 1/s per chain = 10 %% of the radiometry "
          "beta-window background b_beta = 0.5 1/s, i.e. the [square-bracket] column.  Sensitivity to the assumed halving temperature (J60035@2.5V typ, -20 C): " +
          ", ".join("T_half %.0f C -> %s p.e." % (th, lowest_lld(SIPM["J60035@2.5V"]["dcr"] * 2 ** (-45 / th),
                                                                 F_CAL * met["J60035@2.5V"][0]["fast_area_over_peak"],
                                                                 0.08, 1.0)) for th in (7, 8, 10)))
    rows = []
    for n in (3, 4, 5):
        an0 = dark_trigger_rate(s0["dcr"], mb0["fast_area_over_peak"], s0["ct"], n)
        an = dark_trigger_rate(s0["dcr"], F_CAL * mb0["fast_area_over_peak"], s0["ct"], n)
        rows.append([n, "%.3g" % an0, "%.3g" % an, "%.3g" % mc_rows[n], "%.2f" % (mc_rows[n] / an)])
    print("\nMonte-Carlo check (J60035@2.5V, 25 C, 0.2 s of simulated dark pulses, real shaped pulse):\n")
    print(md_table(["n (threshold n-0.5 p.e.)", "model, resolving time = area/peak 1/s", "model, fitted factor 1/s", "Monte-Carlo 1/s", "MC / fitted model"], rows))

    # ---- T7 timing
    section("T7 Timing budget (calculated unless marked)")
    mb, ma = met["J60035@2.5V"]
    t, y = mb["t"], mb["fast"] / mb["fast_pk"]
    need = c["LATCH_TW"] + 1.0e-9      # comparator must produce >= latch tw plus ~1 ns edge allowance
    # smallest amplitude ratio A/T that gives time over threshold >= need
    ratio = None
    for a in np.arange(1.001, 1.5, 0.001):
        tot = np.count_nonzero(a * y > 1.0) * (t[1] - t[0])
        if tot >= need:
            ratio = a
            break
    dead_mean = c["W_ACCEPT"] + c["T_SERVICE"] / 2 + c["T_ISR"]
    dead_max = c["W_ACCEPT"] + c["T_SERVICE"] + c["T_ISR"]
    rows = [
        ["SiPM recharge (J60035)", "50 ns", "datasheet"],
        ["Input pole R_IN*Ct (J60035, %.1f ohm)" % c["R_IN"], "%.0f ns" % (mb["tau_in"] * 1e9), "calculated"],
        ["FAST peaking time / FWHM / resolving time", "%.0f / %.0f / %.0f ns" %
         (mb["fast_tpk"] * 1e9, mb["fast_fwhm"] * 1e9, mb["fast_area_over_peak"] * 1e9), "calculated"],
        ["FAST undershoot after a beta pulse (fraction of peak)", "%.3f" % (-mb["fast_min"] / mb["fast_pk"]),
         "calculated (pole-zero matched)"],
        ["SLOW peaking time for a ZnS(Ag) alpha", "%.2f us" % (ma["slow_tpk"] * 1e6), "calculated (ZnS profile assumed)"],
        ["Comparator propagation delay (100 mV / 5 mV overdrive)", "4.5 / 7.5 ns typ (12 ns max over T at 5 mV)",
         "datasheet TLV3501"],
        ["Latch minimum clock pulse width (SN74LVC74A, 3.3 V)", "3.3 ns", "datasheet"],
        ["Smallest pulse/threshold ratio that still clocks the latch (TOT >= %.1f ns)" % (need * 1e9),
         "%.3f (i.e. effective threshold +%.1f %%)" % (ratio, (ratio - 1) * 100), "calculated"],
        ["Timer capture resolution (144 MHz)", "6.94 ns", "calculated"],
        ["Acceptance window W", "%.0f us default" % (c["W_ACCEPT"] * 1e6), "contract"],
        ["Service interval", "%.0f us (100 kHz)" % (c["T_SERVICE"] * 1e6), "contract"],
        ["Dead time per event: W + U(0, T_service) + ISR", "mean %.1f us, max %.1f us" % (dead_mean * 1e6, dead_max * 1e6),
         "calculated; ISR allowance %.1f us ASSUMED; measured per event in operation" % (c["T_ISR"] * 1e6)],
    ]
    print(md_table(["item", "value", "evidence"], rows))
    rows = []
    for r in (10, 100, 2000, 1e4, 5e4, 1e5):
        live = 1 / (1 + r * dead_mean)
        rows.append(["%.0f" % r, "%.4f" % live, "%.0f" % (r * live), "%.2f" % (100 * (1 - math.exp(-r * c["W_ACCEPT"]))),
                     "%.3f" % (100 * (1 - math.exp(-r * mb["fast_area_over_peak"])))])
    print("\nNon-paralysable live fraction with the mean dead time (calculated):\n")
    print(md_table(["true rate 1/s", "live fraction", "recorded rate 1/s", "P(second event inside W) %",
                    "P(pile-up inside fast resolving time) %"], rows))
    print("\nRate at which the live fraction reaches 0.5: %.3g /s; hard ceiling 1 event per service tick = %.0f /s." %
          (1 / dead_mean, 1 / c["T_SERVICE"]))

    # ---- T8 bias
    section("T8 Bias set-point, trim and temperature compensation (calculated)")
    k_hv = 25.0
    lsb_hv = c["DAC_FS"] / 2 ** 12 * k_hv
    lsb_trim = c["DAC_FS"] / 2 ** 12
    print("HV = %.1f x V(HV_SET): full scale %.1f V, 12-bit step %.2f mV (16-bit DAC80508 drop-in: %.2f mV). "
          "Anode trim step %.2f mV, range 0.10..2.50 V usable.\n" %
          (k_hv, k_hv * c["DAC_FS"], lsb_hv * 1e3, c["DAC_FS"] / 65536 * k_hv * 1e3, lsb_trim * 1e3))
    rows = []
    r_filt = 1000.0 + 100.0
    for k, s in SIPM.items():
        v25 = s["vbr"] + s["vov"]
        vm25 = s["vbr"] + s["beta"] * (-25 - 25) + s["vov"]
        v40 = s["vbr"] + s["beta"] * (40 - 25) + s["vov"]
        vmax = v40 + (s["vbr_tol"] or 0.0)
        idk = s["idark_typ"]
        rows.append([k, "%.2f" % v25, "%.2f" % vm25, "%.2f" % v40, "%.2f" % vmax,
                     "%.2f" % (100 * s["beta"] / s["vov"]), "%.3f" % (100 * lsb_trim / s["vov"]),
                     ("%.1f" % (idk * r_filt * 1e3)) if idk else "n/a",
                     ("%.2f" % (100 * idk * r_filt / s["vov"])) if idk else "n/a",
                     "yes" if vmax <= 60.0 else "NO (>60 V)"])
    print(md_table(["device", "Vbias 25 C", "Vbias -25 C", "Vbias +40 C", "max incl. Vbr tolerance",
                    "gain change %/C uncompensated", "gain step per trim LSB %", "IR drop in 1.1 k filter mV (dark typ)",
                    "= gain error % if uncorrected", "inside 20-60 V"], rows))

    # ---- T9 heater
    section("T9 Heater (calculated; element 4.8 ohm = 30 W at 12.0 V)")
    r_h = 4.8
    rows = []
    for v in (10.0, 12.0, 12.8, 14.6, 15.0):
        p = v * v / r_h
        rows.append(["%.1f" % v, "%.2f" % (v / r_h), "%.1f" % p, "%.0f" % (100 * 16 / p), "%.0f" % (100 * 19 / p)])
    print(md_table(["bus V at the element", "I A", "P W", "duty % for 16 W (-20 C)", "duty % for 19 W (-25 C)"], rows))
    t_slew = 1.2e-3
    di = 15.0 / r_h / t_slew
    m_h = 10e-9
    print("\nSlew-limited edge %.1f ms: dI/dt = %.0f A/s; with an assumed %.0f nH mutual inductance to a pigtail loop the "
          "induced voltage is %.1f uV for %.1f ms (an un-slewed 100 ns edge would give %.2f V)." %
          (t_slew * 1e3, di, m_h * 1e9, m_h * di * 1e6, t_slew * 1e3, m_h * 15.0 / r_h / 100e-9))
    mbj = met["J60035@2.5V"][0]
    f_edge = 0.35 / t_slew
    att_fast = 2 * math.pi * f_edge * CIR["R_D"] * CIR["C_D"]  # CR high-pass well below its corner
    print("Edge spectrum corner %.0f Hz; fast CR (22 ns) passes %.1e of it -> %.2e p.e. equivalent at the FAST output "
          "(J60035).  Switching energy per edge 0.5*V*I*t = %.0f mJ at 15 V." %
          (f_edge, att_fast, m_h * di * CIR["G1"] * CIR["G2"] * att_fast / mbj["fast_pk"], 0.5 * 15 * 15 / r_h * t_slew * 1e3))

    # ---- T10 power
    section("T10 Power budget (calculated from datasheet typical/maximum quiescent currents; MCU current assumed)")
    loads_5va = [("16 x OPA838 (preamp, fast)", 16 * 0.95, 16 * 1.05), ("5 x OPA836 (slow x4, monitor)", 5 * 1.0, 5 * 1.4),
                 ("4 x TLV9062 trim buffers + 2 misc op-amps", 6 * 1.1, 6 * 1.5), ("4 x DAC60508", 4 * 2.5, 4 * 4.0),
                 ("5 x TMUX1108, references, dividers", 2.0, 4.0)]
    loads_evt = [("20 comparators TLV350x", 20 * 3.2, 20 * 5.0), ("20 latches + OR gates, decoders", 3.0, 8.0)]
    loads_3v3 = [("STM32G474 at 144 MHz", 45.0, 70.0), ("TPS61391 boost input (HV 66 V x 0.6 mA / 60 %)", 20.0, 45.0),
                 ("ISO1430 logic side, TMP117 x2, EEPROM, TCXO, LEDs", 12.0, 20.0), ("REF3030, TLV7021 x2, misc", 1.0, 3.0)]
    v_pre = 5.63
    eff_typ, eff_min = 0.88, 0.82
    rows = []
    tot_typ = tot_max = 0.0
    for rail, loads in (("+5V_A (TPS7A2050)", loads_5va), ("+3V3_EVT (TLV76733)", loads_evt),
                        ("+3V3 (TLV76733)", loads_3v3)):
        it = sum(x[1] for x in loads)
        im = sum(x[2] for x in loads)
        tot_typ += it
        tot_max += im
        vr = 5.0 if "5V" in rail else 3.3
        rows.append([rail, "; ".join("%s %.0f/%.0f" % x for x in loads), "%.0f" % it, "%.0f" % im,
                     "%.0f" % ((v_pre - vr) * it), "%.0f" % ((v_pre - vr) * im)])
    print(md_table(["rail (from +5V6 pre-regulator)", "loads mA typ/max", "I typ mA", "I max mA", "LDO loss typ mW",
                    "LDO loss max mW"], rows))
    p_typ = v_pre * tot_typ * 1e-3 / eff_typ + 0.02
    p_max = v_pre * tot_max * 1e-3 / eff_min + 0.05
    print("\nPre-regulator output %.2f V: %.0f mA typ / %.0f mA max -> input power %.2f W typ (buck %.0f %%) / %.2f W max "
          "(buck %.0f %%), including eFuse and input-filter loss.  Input current at 12.8 V: %.0f mA typ; at 9.0 V and "
          "maximum load: %.0f mA.  Bus side of the isolator (from BUS_5V on J2, not in this total): ~60 mA while "
          "transmitting into 60 ohm, <10 mA idle (datasheet class, UNVERIFIED exact figure)." %
          (v_pre, tot_typ, tot_max, p_typ, eff_typ * 100, p_max, eff_min * 100, p_typ / 12.8 * 1e3, p_max / 9.0 * 1e3))
    print("Against the allocation: %.2f W typ / %.2f W max vs 5 W target and 10 W limit." % (p_typ, p_max))

    # ---- T11 test pulser
    section("T11 Charge-injection pulser (calculated)")
    rows = []
    for k in ("J60035@2.5V", "S14160-6050HS", "S13360-6050PE", "NUV-MT 6x6 @12V"):
        q1 = SIPM[k]["gain"] * Q_E
        rows.append([k, "%.3f" % (q1 * 1e12), "%.0f" % (c["C_INJ"] * c["V_TP_MAX"] / q1),
                     "%.2f" % (c["C_INJ"] * c["DAC_FS"] / 4096 / q1)])
    print(md_table(["device", "Q per p.e. pC", "full-scale injection p.e. (100 pF x 2.5 V = 250 pC)",
                    "step per DAC LSB p.e."], rows))

    # ================================================================== stage 3 tables (review fixes)
    section("T13 Time over threshold at the raw LLD (C1): FAST pulse clamped at %.1f V above baseline, threshold in "
            "beta-p.e. units (as the LLD is set); TOT in ns (calculated, pulse model of T2, C_PZ = %s)" %
            (CIR["V_CLAMP"] - CIR["V_BL"], eng(CIR.get("C_PZ"), "F")))
    rows = []
    for k, thr, tb, ta, rb, ra in tot_rows():
        rows.append([k, "%d" % thr, " / ".join("%.0f" % x for x in tb), " / ".join("%.0f" % x for x in ta),
                     "%.0f" % (min(ta) - max(tb)), "%.1f / %.1f" % (rb, ra)])
    print(md_table(["device", "LLD p.e.", "beta 30 / 120 / 240 p.e. TOT ns", "alpha 150 / 300 / 1500 / 15000 p.e. TOT ns",
                    "gap: weakest alpha - brightest beta ns", "FAST/SLOW per p.e. beta / alpha"], rows))
    print("\nCapture tick 6.94 ns on each edge (two timers): TOT uncertainty +-7 ns, i.e. a cut must sit >= 2 ticks from "
          "both populations.  The alpha TOT is set by the ZnS decay (assumed 200 ns) and the beta TOT by R_IN*Ct and the "
          "fast CR; the cut has to be chosen per device type from this table and confirmed with Sr-90 and Am-241.")

    section("T14 Low-frequency FAST tail after a large alpha (m2; calculated, J60035, values in p.e. at FAST)")
    rows = []
    pts = (5, 50, 100, 150, 200, 300, 500)
    for label, cpz, trim in (("stage-1 PZ (DC 0.307), no trim node (review model)", None, False),
                             ("stage-1 PZ, with trim-node step", None, True),
                             ("S3-04: C_PZ 47 nF, with trim-node step", 47e-9, True),
                             ("C_PZ 100 nF, with trim-node step", 100e-9, True)):
        for npe in (15000, 1500):
            t, y = lf_tail(npe, cpz, trim)
            k0 = int(2e-6 / (t[1] - t[0]))
            rows.append([label, npe] + ["%.2f" % y[int(p * 1e-6 / (t[1] - t[0]))] for p in pts] +
                        ["%.1f at %.0f us" % (y[k0:].min(), t[k0 + y[k0:].argmin()] * 1e6)])
    print(md_table(["network", "alpha p.e."] + ["%d us" % p for p in pts] + ["minimum after 2 us"], rows))
    print("\nThe trim node (4.8 uF, recovering through 4.99 k in ~24 ms) takes the alpha charge as a slow step at the anode; "
          "the input coupling turns it into a long negative tail that the review's model (first row) does not contain.")

    section("T15 Lane-monitor tap loading and switching charge at the comparator input (M2; calculated, J60035 "
            "6.56 mV/p.e. at FCMP; C_bus 50-150 pF, source node 10 pF, switch charge 0.3-3 pC, OPA838 |Z_out| <= 30 ohm "
            "at 20 MHz - all assumed)")
    zo, cs, vpe, dv = 30.0, 10e-12, 6.93e-3, 0.040
    g_pre = pulse_metrics(SIPM["J60035@2.5V"], "beta")["fast_pk"] / pulse_metrics(SIPM["J60035@2.5V"], "beta")["pre_pk"]
    rows = [["1 k at FCMP (stage 1), review mux.py", "-14 / -18 %", "+1.3 (40 mV)", "+0.7 / +7.1", "1-3 MHz"]]
    for rt in (4.99e3, 10e3):
        for node, gain in (("FAST", 1.0), ("PRE (x FAST/PRE gain %.1f)" % g_pre, g_pre)):
            load = zo / rt * gain
            share = dv / rt * zo * gain / vpe
            inj = ["%.3f" % (q / (rt * cs) * zo * gain / vpe) for q in (0.3e-12, 3e-12)]
            rows.append(["%.2f k at %s (op-amp output)" % (rt / 1e3, node), "-%.2f %%" % (100 * load),
                         "+%.3f" % share, "+" + " / +".join(inj),
                         "%.0f-%.0f kHz" % (1e-3 / (2 * math.pi * rt * 150e-12), 1e-3 / (2 * math.pi * rt * 50e-12))])
    print(md_table(["tap", "amplitude loss while connected (C_bus 50 / 150 pF)", "charge sharing at closure, p.e.",
                    "switch charge 0.3 / 3 pC, p.e.", "monitor bandwidth (C_bus 150 / 50 pF)"], rows))
    print("\nWith MON_LANE_EN = 0 (S3-02) no lane switch is closed or toggled while armed: all three effects are zero. "
          "The 10 k numbers apply only to engineering captures with the monitor enabled.")

    section("T16 Motor pickup into the SiPM loop (M4; calculated, J60035; coaxial-dipole mutual inductance; aggressor "
            "values assumed as stated)")
    cases = [("budget case: 1 A in 100 ns, 10 cm2 lead loop at 65 mm", 1.0, 100e-9, 10e-4, 0.065),
             ("same with 150 ns edges (DRV8874)", 1.0, 150e-9, 10e-4, 0.065),
             ("real differential lead ripple 60 mA p-p (L = 2.5 mH) in 150 ns", 0.06, 150e-9, 10e-4, 0.065),
             ("bridge hot loop on RR-CHS-MAIN: 2.68 A / 150 ns, 2 cm2 at 90 mm", 2.68, 150e-9, 2e-4, 0.090),
             ("common-mode lead current 80 mA (80 V/us x 1 nF) / 150 ns, 10 cm2 at 74 mm", 0.08, 150e-9, 10e-4, 0.074),
             ("brush commutation arc ~0.1 A common mode in ~5 ns, 10 cm2 at 74 mm", 0.1, 5e-9, 10e-4, 0.074)]
    rows = []
    for label, di, te, a1, r in cases:
        cells = [label]
        for a2, rr in ((0.5e-4, r), (0.68e-4, r), (2e-6, r)):
            e = mutual(a1, a2, rr) * di / te
            cells.append("%.3g uV / %.2f" % (e * 1e6, emf_pe(e, te)))
        rows.append(cells)
    print(md_table(["aggressor", "open pigtail 0.5 cm2 (35 mm, stage-1 assumption): EMF / FAST p.e.", "open pigtail 0.68 cm2 (47.5 mm ~ as-routed floor coax 44-47 mm)",
                    "coax, 2 mm2 launch"], rows))
    print("\nThe coax column does not depend on the pigtail length (only the launch loop at the U.FL and the carrier pads "
          "remains); the shield-loop term of review m1 (~0.3 p.e.) comes on top.  The band that matters is 1-100 MHz "
          "(edges of 5-150 ns): the FAST shaper passes 1-30 MHz with full gain.")

    section("T17 Beta efficiency vs photoelectron yield and the minimum yield for the optics RFQ (M1; calculated: "
            "Poisson photostatistics x Moyal energy loss, MPV = 0.70 x mean, assumed)")
    s0_ = SIPM["J60035@2.5V"]
    n_typ = LLD005[("J60035@2.5V", "typ", 10)]
    n_max = LLD005[("J60035@2.5V", "max", 10)]
    rows = []
    for mu in (4, 8, 10, 15, 20, 25, 30, 45):
        rows.append([mu] + ["%.2f" % efficiency(mu, n) for n in (8, n_typ, n_max, 12)])
    print(md_table(["p.e. at the MPV deposit (one point of the plate)", "eff. LLD 8", "eff. LLD %d (J60035 typ, +10 C, "
                    "0.05/s)" % n_typ, "eff. LLD %d (J60035 max DCR, +10 C, 0.05/s)" % n_max, "eff. LLD 12"], rows))
    req = {n: mu_required(n) for n in (n_typ, n_max)}
    print("\nMinimum yield so that the WORST point of the plate keeps >= 90 %% efficiency: LLD %d -> %.1f p.e. at the MPV "
          "deposit; LLD %d -> %.1f p.e.  With the +-50 %% light-collection variation (assumed) the plate average at the "
          "MPV is then 2 x / 1.5 x that, and the plate-average MEAN yield 1/0.70 x higher." %
          (n_typ, req[n_typ], n_max, req[n_max]))
    REQ_YIELD = req

    section("T12 Cross-check against circuit.py (channel F0)")
    bad, rpz, taps = check_against_circuit()
    print("Board netlist = design/circuit.py + electronics/head_acq/overrides.py (stage 2/3).  Values in this script that "
          "differ from it: %s.  Pole-zero resistor fitted: %.0f ohm (matched value for a 50 ns recharge time: %.0f ohm), "
          "in series with C_PZ = %s.  Lane-monitor taps: %s (all at op-amp outputs)." %
          (bad or "none", rpz, 50e-9 / c["C_D"], eng(c.get("C_PZ"), "F"),
           ", ".join("%s %.0f ohm" % kv for kv in taps.items())))

    if plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        here = __file__.rsplit("/", 1)[0]
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        for k in ("J60035@2.5V", "S14160-6050HS", "S13360-6050PE", "4x J60035@2.5V"):
            mb, ma = met[k]
            ax[0].plot(mb["t"] * 1e9, mb["fast"] * 1e3, label=k)
            ax[1].plot(ma["t"] * 1e6, ma["slow"] * 1e3, label=k)
        ax[0].set(xlim=(0, 400), xlabel="t (ns)", ylabel="FAST out per p.e. (mV)", title="beta-like pulse, fast path")
        ax[1].set(xlim=(0, 30), xlabel="t (us)", ylabel="SLOW out per p.e. (mV)", title="ZnS(Ag) alpha-like pulse, slow path")
        ax[0].legend(fontsize=7)
        ax[0].grid(alpha=.3)
        ax[1].grid(alpha=.3)
        fig.tight_layout()
        fig.savefig(here + "/head_afe_pulses.png", dpi=110)
        print("\nwrote head_afe_pulses.png")


if __name__ == "__main__":
    main()
