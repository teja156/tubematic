# Ported from mromidev/claude-animated-shorts (templates/audio/dsp.py), MIT License, Copyright (c) 2026 Mr omi.
# Verbatim: the synthesis library behind every sound; the video-specific parts live in score.py / cues.py / mix.py.

# Own small DSP kit for "The Bridge That Fell for a Song" soundtrack (numpy + scipy only, no third-party audio code):
# filters, noise colours, envelopes, STFT spectral shaping, modal / additive helpers, stereo placement,
# synthetic reverb impulse responses, BS.1770-4 loudness (integrated / momentary / short-term / LRA), true peak,
# 16/24-bit WAV read/write.
import wave
import numpy as np
from scipy import signal

SR = 48000
TAU = 2 * np.pi


def ns(t):
    return int(round(t * SR))


def tt(dur):
    return np.arange(ns(dur)) / SR


def dbg(db):
    return 10.0 ** (db / 20.0)


def rng(seed):
    return np.random.default_rng(seed)


# ---------------------------------------------------------------- filters
def _sos(kind, f, order):
    return signal.butter(order, f, btype=kind, fs=SR, output="sos")


def lp(x, f, order=2):
    return signal.sosfilt(_sos("lowpass", min(f, SR * 0.45), order), x, axis=-1)


def hp(x, f, order=2):
    return signal.sosfilt(_sos("highpass", f, order), x, axis=-1)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(_sos("bandpass", [lo, min(hi, SR * 0.45)], order), x, axis=-1)


def biquad(kind, f0, q=0.707, gain_db=0.0):
    A = 10 ** (gain_db / 40)
    w = TAU * f0 / SR
    cw, sw = np.cos(w), np.sin(w)
    al = sw / (2 * q)
    if kind == "peak":
        b = [1 + al * A, -2 * cw, 1 - al * A]
        a = [1 + al / A, -2 * cw, 1 - al / A]
    elif kind == "bpf":
        b = [al, 0.0, -al]
        a = [1 + al, -2 * cw, 1 - al]
    elif kind == "lowshelf":
        sa = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    elif kind == "highshelf":
        sa = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    else:
        raise ValueError(kind)
    a = np.array(a, float)
    return np.array(b, float) / a[0], a / a[0]


def peq(x, f0, gain_db, q=1.0):
    b, a = biquad("peak", f0, q, gain_db)
    return signal.lfilter(b, a, x, axis=-1)


def shelf(x, f0, gain_db, kind="high", q=0.707):
    b, a = biquad("highshelf" if kind == "high" else "lowshelf", f0, q, gain_db)
    return signal.lfilter(b, a, x, axis=-1)


def reson(x, f0, q):
    b, a = biquad("bpf", f0, q)
    return signal.lfilter(b, a, x, axis=-1)


def resbank(x, modes):
    """parallel resonators: modes = [(freq, q, gain)]"""
    y = np.zeros_like(x)
    for f, q, g in modes:
        if f < SR * 0.45:
            y += g * reson(x, f, q)
    return y


# ---------------------------------------------------------------- noise
def colored(n, r, slope=0.0, lo=20.0):
    """noise with power spectrum ~ f^-slope (0 white, 1 pink, 2 brown), unit std"""
    X = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f = np.maximum(f, lo)
    X *= f ** (-slope / 2)
    x = np.fft.irfft(X, n)
    return x / (np.std(x) + 1e-12)


def smooth_noise(n, r, rate_hz, ctrl=200):
    """slow random curve in [-1, 1]-ish (low-passed control noise), e.g. for gusts or pitch drift"""
    m = max(4, int(n / SR * ctrl) + 4)
    c = r.standard_normal(m)
    c = signal.sosfiltfilt(signal.butter(2, min(rate_hz / (ctrl / 2), 0.99), output="sos"), c)
    c /= np.max(np.abs(c)) + 1e-12
    return np.interp(np.arange(n) / SR * ctrl, np.arange(m), c)


# ---------------------------------------------------------------- envelopes / shaping
def ramp(n, kind="cos"):
    u = np.linspace(0, 1, max(n, 1))
    return 0.5 - 0.5 * np.cos(np.pi * u) if kind == "cos" else u


def fades(x, fin=0.003, fout=0.01):
    x = np.array(x, dtype=float, copy=True)
    a, b = ns(fin), ns(fout)
    n = x.shape[-1]
    if a > 0:
        x[..., : min(a, n)] *= ramp(a)[: min(a, n)]
    if b > 0:
        x[..., max(0, n - b):] *= ramp(b)[::-1][-min(b, n):]
    return x


def curve(n, pts, t0=0.0):
    """piecewise-linear automation sampled per audio sample: pts = [(time_s, value)] relative to t0"""
    xs = np.array([p[0] for p in pts], float)
    ys = np.array([p[1] for p in pts], float)
    return np.interp(t0 + np.arange(n) / SR, xs, ys)


def shape(x, gain, nper=1024, hop=256):
    """time-varying spectral gain via STFT; gain(times[F], freqs[B]) -> (B, F) magnitude multipliers"""
    n = len(x)
    f, t, Z = signal.stft(x, fs=SR, window="hann", nperseg=nper, noverlap=nper - hop, boundary="zeros", padded=True)
    G = gain(t, f)
    _, y = signal.istft(Z * G, fs=SR, window="hann", nperseg=nper, noverlap=nper - hop, boundary=True)
    y = y[:n]
    if len(y) < n:
        y = np.pad(y, (0, n - len(y)))
    return y


def phase(f):
    """instantaneous frequency (Hz per sample) -> phase (rad)"""
    return TAU * np.cumsum(f) / SR


def modal(dur, modes, r=None, glide=0.0, glide_tau=0.02):
    """sum of exponentially decaying sines: modes = [(freq, amp, tau)]; optional common pitch glide (fraction)"""
    t = tt(dur)
    y = np.zeros_like(t)
    g = 1 + glide * np.exp(-t / glide_tau) if glide else None
    for m in modes:
        f, a, tau = m[0], m[1], m[2]
        if f >= SR * 0.45:
            continue
        ph0 = r.uniform(0, TAU) if r is not None else 0.0
        if g is None:
            y += a * np.exp(-t / tau) * np.sin(TAU * f * t + ph0)
        else:
            y += a * np.exp(-t / tau) * np.sin(phase(f * g) + ph0)
    return y


def impulse_train(times, dur, amps=None):
    x = np.zeros(ns(dur) + 1)
    for i, tm in enumerate(times):
        k = ns(tm)
        if 0 <= k < len(x):
            x[k] += 1.0 if amps is None else amps[i]
    return x


# ---------------------------------------------------------------- stereo
def pan(x, p=0.0):
    """constant-power pan of a mono signal; centre gives L = R = x"""
    th = (float(np.clip(p, -1, 1)) + 1) * np.pi / 4
    return np.stack([x * np.cos(th), x * np.sin(th)]) * np.sqrt(2)


def st(x):
    x = np.asarray(x, float)
    if x.ndim == 1:
        return np.stack([x, x])
    return np.concatenate([x, x]) if x.shape[0] == 1 else x


def place(buf, x, t, gain=1.0):
    """add x (mono or stereo) into buf (2, N) starting at time t (s)"""
    x = st(x)
    i = ns(t)
    a, b = max(0, i), min(buf.shape[1], i + x.shape[1])
    if b > a:
        buf[:, a:b] += gain * x[:, a - i: b - i]


def widen(x, r, ms=11.0, amount=0.5):
    """decorrelate a mono sound into stereo (short complementary delays), keeps the centre image"""
    d = ns(ms / 1000)
    y = np.pad(x, (0, d))
    dl = np.pad(x, (d, 0))
    L = y + amount * 0.5 * dl
    R = y - amount * 0.5 * dl
    return np.stack([L, R])[:, : len(x)] / (1 + 0.25 * amount)


# ---------------------------------------------------------------- reverb
def make_ir(rt60, seed, length=None, pre=0.012, hf=1.0, early=(), density_lp=None):
    """stereo IR: decorrelated decaying noise, highs decay faster (hf), optional early reflections [(t, gain, pan)]"""
    r = rng(seed)
    n = ns(length or rt60 * 1.25)
    t = np.arange(n) / SR
    ir = np.zeros((2, n))
    for ch in range(2):
        z = r.standard_normal(n) * np.exp(-6.91 * t / rt60)
        z = shape(z, lambda T, F: np.exp(-6.91 * np.maximum(T[None, :], 0) / rt60 * hf * (F[:, None] / 5000.0) ** 1.2), 512, 128)
        z *= ramp(min(n, ns(0.02)))[np.minimum(np.arange(n), ns(0.02) - 1)]
        ir[ch] = z
    if density_lp:
        ir = lp(ir, density_lp, 1)
    for et, eg, ep in early:
        k = ns(et)
        if k < n:
            spike = np.zeros(n)
            spike[k] = 1.0
            spike = lp(spike, 6000, 1)
            ir += eg * pan(spike, ep) * np.sqrt(np.mean(ir ** 2) * 2000)
    ir /= np.sqrt(np.sum(ir ** 2) / 2)
    return np.concatenate([np.zeros((2, ns(pre))), ir], axis=1)


def convolve_st(x, ir):
    """x mono (n) or stereo (2, n) send -> stereo wet (2, n) (tail cropped)"""
    n = x.shape[-1]
    if x.ndim == 1:
        return np.stack([signal.fftconvolve(x, ir[c])[:n] for c in range(2)])
    return np.stack([signal.fftconvolve(x[c], ir[c])[:n] for c in range(2)])


# ---------------------------------------------------------------- loudness (ITU-R BS.1770-4 / EBU R128)
_KB1 = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
_KA1 = np.array([1.0, -1.69065929318241, 0.73248077421585])
_KB2 = np.array([1.0, -2.0, 1.0])
_KA2 = np.array([1.0, -1.99004745483398, 0.99007225036621])


def kfilt(x):
    return signal.lfilter(_KB2, _KA2, signal.lfilter(_KB1, _KA1, x, axis=-1), axis=-1)


def _blocks(x, win, hop):
    x = st(x)
    z2 = kfilt(x) ** 2
    c = np.concatenate([np.zeros((2, 1)), np.cumsum(z2, axis=-1)], axis=-1)
    w, h = ns(win), ns(hop)
    if x.shape[1] < w:
        z = (c[:, -1] / w).sum()
        return np.array([-0.691 + 10 * np.log10(z + 1e-30)]), np.array([z])
    s = np.arange(0, x.shape[1] - w + 1, h)
    z = ((c[:, s + w] - c[:, s]) / w).sum(0)
    return -0.691 + 10 * np.log10(z + 1e-30), z


def integrated(x):
    L, z = _blocks(x, 0.4, 0.1)
    keep = L > -70
    if not keep.any():
        return -np.inf
    rel = -0.691 + 10 * np.log10(z[keep].mean()) - 10
    k2 = keep & (L > rel)
    return -0.691 + 10 * np.log10(z[k2].mean())


def momentary(x, hop=0.01):
    return _blocks(x, 0.4, hop)[0]


def momentary_max(x):
    return float(momentary(x).max())


def short_term(x, hop=0.1):
    return _blocks(x, 3.0, hop)[0]


def lra(x):
    L, z = _blocks(x, 3.0, 0.1)
    keep = L > -70
    if keep.sum() < 2:
        return 0.0
    rel = -0.691 + 10 * np.log10(z[keep].mean()) - 20
    v = L[keep & (L > rel)]
    return float(np.percentile(v, 95) - np.percentile(v, 10))


def true_peak(x):
    up = signal.resample_poly(st(x), 4, 1, axis=-1)
    return 20 * np.log10(np.abs(up).max() + 1e-30)


def norm_to(x, target_lufs, mode="momentary"):
    """scale x so its max momentary (events) or integrated (beds) loudness hits target"""
    cur = momentary_max(x) if mode == "momentary" else integrated(x)
    if not np.isfinite(cur):
        return x
    return x * dbg(target_lufs - cur)


# ---------------------------------------------------------------- wav io
def read_wav(path):
    with wave.open(path, "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / float(1 << 23)
    elif sw == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / float(1 << 31)
    else:
        raise ValueError(sw)
    return x.reshape(-1, ch).T, sr


def write_wav(path, x, bits=24):
    x = st(x)
    ch, n = x.shape
    if bits == 24:
        q = np.clip(np.round(x.T * 8388607.0), -8388608, 8388607).astype("<i4")
        data = np.ascontiguousarray(q).view(np.uint8).reshape(n, ch, 4)[:, :, :3].tobytes()
        sw = 3
    else:
        q = np.clip(np.round(x.T * 32767.0), -32768, 32767).astype("<i2")
        data = q.tobytes()
        sw = 2
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(sw)
        w.setframerate(SR)
        w.writeframes(data)
