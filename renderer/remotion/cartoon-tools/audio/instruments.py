# Ported from mromidev/claude-animated-shorts (templates/audio/instruments.py), MIT License, Copyright (c) 2026 Mr omi.
# Verbatim: the synthesis library behind every sound; the video-specific parts live in score.py / cues.py / mix.py.

# Synthesized instruments for the original march (all own additive / modal synthesis):
# brass (tuba, after-beat horns, stabs), glockenspiel, vibraphone, music box, fife, human whistle (phrase-level with
# portamento, scoops, vibrato, breath), field snare (strokes, flams, buzz rolls), clash cymbal, triangle, timpani,
# warm pad, plucked strings, brushes.
import numpy as np
from scipy import signal
from dsp import SR, TAU, ns, tt, rng, lp, hp, bp, reson, peq, colored, smooth_noise, ramp, fades, shape, phase, modal


def m2f(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def _env(n, att, dur_n, rel, curve=1.5):
    e = np.ones(n)
    a = max(1, ns(att))
    e[:a] = np.linspace(0, 1, a) ** curve
    if dur_n < n:
        e[dur_n:] *= np.linspace(1, 0, n - dur_n) ** 2
    return e


# ---------------------------------------------------------------- brass
def brass(f, dur, vel=0.8, r=None, kind="tuba", scoop=-22.0, rel=0.07, fall=0.0):
    """additive brass: louder = brighter (brassy blat on the attack), lip scoop, small formant per instrument"""
    r = r or rng(0)
    n = ns(dur + rel)
    t = np.arange(n) / SR
    att = {"tuba": 0.035, "horn": 0.025, "stab": 0.012, "soft": 0.09}[kind]
    env = _env(n, att, ns(dur), rel)
    env *= 1 + (0.25 if kind == "stab" else 0.14) * vel * np.exp(-((t - att) / 0.035) ** 2)
    env *= (0.72 if kind == "stab" else 0.85) + (0.28 if kind == "stab" else 0.15) * np.exp(-t / (0.09 if kind == "stab" else 0.16))
    cents = scoop * np.exp(-t / 0.03) + 4 * smooth_noise(n, r, 3.0)
    if fall:
        cents += fall * 100 * np.clip((t - dur * 0.55) / (dur * 0.45 + rel), 0, 1) ** 2
    ph = phase(f * 2 ** (cents / 1200))
    form = {"tuba": (420, 260), "horn": (900, 450), "stab": (1100, 700), "soft": (380, 220)}[kind]
    top = {"tuba": 2400, "horn": 5000, "stab": 7000, "soft": 1500}[kind]
    K = max(1, int(min(48, top / f)))
    bc = (1.8 + 6.5 * vel * env ** 1.4) * (1.3 if kind == "stab" else 1.0)
    y = np.zeros(n)
    for k in range(1, K + 1):
        fk = k * f
        ak = k ** -0.75 / (1 + (k / bc) ** 3) * (1 + 1.2 * np.exp(-((fk - form[0]) / form[1]) ** 2))
        y += ak * np.sin(k * ph + r.uniform(0, TAU))
    nz = bp(r.standard_normal(n), 300, 3000, 1) * np.exp(-t / 0.02) * 0.04 * vel
    return (y * env + nz) * vel


# ---------------------------------------------------------------- mallets / bells
def glock(f, vel=0.7, r=None, dur=1.8):
    r = r or rng(0)
    t = tt(dur)
    k = (880.0 / f) ** 0.35
    y = modal(dur, [(f, 1.0, 1.25 * k), (f * 2.756, 0.30 * vel, 0.22 * k), (f * 5.404, 0.12 * vel, 0.07), (f * 8.933, 0.05 * vel, 0.025)], r)
    click = hp(r.standard_normal(len(t)), 3000) * np.exp(-t / 0.0007) * 0.25 * vel
    return fades((y + click) * vel, 0.0005, 0.05)


def vibes(f, vel=0.6, r=None, dur=1.6, damp=None, trem=5.2, trem_depth=0.25):
    """vibraphone: bars tuned 1 : 4 : 10, soft mallet, motor tremolo, damper at `damp` s"""
    r = r or rng(0)
    t = tt(dur)
    y = modal(dur, [(f, 1.0, 2.2), (f * 3.98, 0.16 * vel, 0.32), (f * 9.9, 0.04 * vel, 0.06)], r)
    y += hp(r.standard_normal(len(t)), 1500) * np.exp(-t / 0.0015) * 0.05 * vel
    y *= 1 - trem_depth * (0.5 + 0.5 * np.sin(TAU * trem * t + r.uniform(0, TAU)))
    if damp is not None and damp < dur:
        k = ns(damp)
        y[k:] *= np.exp(-np.arange(len(t) - k) / SR / 0.06)
    return fades(y * vel, 0.002, 0.05)


def musicbox(f, vel=0.6, r=None, dur=1.6):
    """music-box tine (cantilever partials 1 : 6.27 : 17.55) with a tiny pluck click"""
    r = r or rng(0)
    t = tt(dur)
    y = modal(dur, [(f, 1.0, 1.1), (f * 2.0, 0.04, 0.4), (f * 6.27, 0.13 * vel, 0.08), (f * 17.55, 0.05 * vel, 0.02)], r)
    y += hp(r.standard_normal(len(t)), 4000) * np.exp(-t / 0.0006) * 0.12 * vel
    return fades(y * vel, 0.0005, 0.05)


def triangle(vel=0.5, r=None, dur=1.6, f=1320.0):
    r = r or rng(0)
    modes = [(f, 1.0, 1.4), (f * 2.71, 0.6, 0.9), (f * 4.63, 0.45, 0.7), (f * 6.02, 0.3, 0.5), (f * 7.75, 0.2, 0.35), (f * 9.4, 0.12, 0.25)]
    y = modal(dur, modes, r)
    t = tt(dur)
    y += hp(r.standard_normal(len(t)), 5000) * np.exp(-t / 0.001) * 0.3
    return fades(y * vel * 0.4, 0.0003, 0.08)


# ---------------------------------------------------------------- winds
def fife(f, dur, vel=0.7, r=None, rel=0.05):
    r = r or rng(0)
    n = ns(dur + rel)
    t = np.arange(n) / SR
    env = _env(n, 0.018, ns(dur), rel, 1.2)
    env *= 1 + 0.1 * np.exp(-((t - 0.02) / 0.02) ** 2)
    vib = 11 * np.clip((t - 0.18) / 0.2, 0, 1) * np.sin(TAU * 5.6 * t + r.uniform(0, TAU))
    cents = 18 * np.exp(-t / 0.015) + vib + 3 * smooth_noise(n, r, 4.0)
    ph = phase(f * 2 ** (cents / 1200))
    y = np.sin(ph) + 0.20 * np.sin(2 * ph + 0.5) + 0.10 * np.sin(3 * ph + 1.1) + 0.035 * np.sin(4 * ph)
    nz = r.standard_normal(n)
    breath = reson(nz, f, 5) * 0.10 + hp(nz, 3000) * 0.015
    chiff = bp(nz, f * 1.5, min(f * 4, 16000), 1) * np.exp(-t / 0.012) * 0.25
    return (y * env + breath * env + chiff) * vel


def whistle(notes, r, detune=0.0, jit=0.010, lag=0.0, vib_rate=5.7, vib_depth=16.0, breath=0.05, bright=0.035,
            falter=None, gate=0.93, scoop=-70.0, ctrl=1000):
    """one person whistling a phrase. notes = [(t, dur, midi, vel)], legato notes glide into each other.
    falter = (time, semitones): pitch droops and the whistle dies out (nervous). Returns (start_time, mono)."""
    notes = sorted(notes)
    t0 = notes[0][0] + lag - 0.15
    t1 = notes[-1][0] + notes[-1][1] + lag + 0.4
    nc = int((t1 - t0) * ctrl) + 2
    tc = t0 + np.arange(nc) / ctrl
    logf = np.full(nc, np.nan)
    amp = np.zeros(nc)
    onset_off = np.zeros(nc)
    vib_env = np.zeros(nc)
    starts = []
    prev_end = -1e9
    for i, (ts, d, m, v) in enumerate(notes):
        s = ts + lag + r.normal(0, jit)
        e = s + d * gate
        nxt = notes[i + 1][0] + lag if i + 1 < len(notes) else 1e9
        legato = (s - prev_end) < 0.06
        a, b = int((s - t0) * ctrl), int((min(e, nxt) - t0) * ctrl)
        logf[a:b] = np.log2(m2f(m + detune / 100.0))
        amp[a:b] = v
        if not legato:
            k = np.arange(nc - a)
            onset_off[a:] += scoop * np.exp(-k / ctrl / 0.028)
        else:  # tongued articulation between legato notes
            k0 = max(0, a - 18)
            amp[k0:a + 6] = np.minimum(amp[k0:a + 6], 0.45 * v) if a + 6 <= nc else amp[k0:a + 6]
        if d > 0.3:
            ln = b - a
            u = np.clip((np.arange(ln) / ctrl - 0.16) / 0.22, 0, 1)
            vib_env[a:b] = np.maximum(vib_env[a:b], u)
        starts.append(s)
        prev_end = e
    # fill pitch through rests with the last pitch (so glides and releases stay on pitch)
    idx = np.where(~np.isnan(logf))[0]
    logf = np.interp(np.arange(nc), idx, logf[idx])
    # portamento: one-pole smoothing of the pitch line, asymmetric attack/release smoothing of the amplitude
    logf = signal.lfilter([1 - np.exp(-1 / (0.016 * ctrl))], [1, -np.exp(-1 / (0.016 * ctrl))], logf - logf[0]) + logf[0]
    a_att, a_rel = np.exp(-1 / (0.012 * ctrl)), np.exp(-1 / (0.035 * ctrl))
    sm = np.zeros(nc)
    acc = 0.0
    for i in range(nc):
        c = a_att if amp[i] > acc else a_rel
        acc = c * acc + (1 - c) * amp[i]
        sm[i] = acc
    amp = sm
    cents = onset_off + vib_depth * vib_env * np.sin(TAU * vib_rate * (tc - t0) + r.uniform(0, TAU))
    drift = signal.sosfiltfilt(signal.butter(2, 2.5 / (ctrl / 2), output="sos"), r.standard_normal(nc)) if nc > 64 else np.zeros(nc)
    cents += 5 * drift / (np.max(np.abs(drift)) + 1e-9)
    if falter:
        tf, semi = falter
        u = np.clip((tc - tf) / 0.38, 0, 1)
        cents += semi * 100 * u ** 1.6
        amp *= np.clip(1 - (tc - tf - 0.12) / 0.3, 0, 1)
    f = 2 ** logf * 2 ** (cents / 1200)
    n = int((t1 - t0) * SR)
    ta = np.arange(n) / SR
    fa = np.interp(ta, tc - t0, f)
    aa = np.interp(ta, tc - t0, amp)
    ph = phase(fa)
    y = np.sin(ph) + bright * np.sin(2 * ph + 0.4) + 0.008 * np.sin(3 * ph + 1.0)
    nz = r.standard_normal(n)
    fr_t = lambda T: np.interp(T, ta, fa)
    br = shape(nz, lambda T, F: np.exp(-0.5 * (np.log2(np.maximum(F[:, None], 20) / fr_t(T)[None, :]) / 0.09) ** 2), 2048, 256)
    air = hp(nz, 2500) * 0.25
    y = aa * (y + breath * 0.7 * br / (np.std(br) + 1e-9) + breath * air)
    return t0, fades(y, 0.005, 0.05)


# ---------------------------------------------------------------- drums
def snare(vel=0.8, r=None, dur=0.34, tune=1.0, snappy=1.0, buzz=False):
    """field (military) snare: head modes with tension pitch drop + snare wires + stick click"""
    r = r or rng(0)
    n = ns(dur)
    t = np.arange(n) / SR
    f0 = 196 * tune * (1 + 0.07 * vel * np.exp(-t / 0.01))
    ph = phase(f0)
    body = (0.9 * np.exp(-t / 0.05) * np.sin(ph) + 0.5 * np.exp(-t / 0.035) * np.sin(1.593 * ph + 1)
            + 0.3 * np.exp(-t / 0.028) * np.sin(2.136 * ph + 2) + 0.22 * np.exp(-t / 0.022) * np.sin(2.296 * ph + 0.5)
            + 0.14 * np.exp(-t / 0.018) * np.sin(2.653 * ph + 1.3))
    nz = r.standard_normal(n)
    tail = 0.055 + 0.07 * vel if not buzz else 0.035
    wires = bp(nz, 1700, 10500, 2) * np.exp(-t / tail) * (1 - np.exp(-t / 0.0012))
    wires = peq(wires, 4200, 3, 0.8)
    click = hp(r.standard_normal(n), 2500) * np.exp(-t / 0.0007)
    y = 0.55 * body * vel ** 1.2 + 0.85 * snappy * wires * vel ** 1.15 + 0.3 * click * vel
    return fades(y, 0.0002, 0.02)


def snare_roll(t_start, t_end, v0, v1, r, rate=28.0):
    """buzz roll: strokes at ~rate/s with velocity ramp; returns list of (t, vel)"""
    out = []
    t = t_start
    i = 0
    while t < t_end:
        u = (t - t_start) / max(t_end - t_start, 1e-6)
        v = (v0 + (v1 - v0) * u ** 1.3) * (0.85 + 0.3 * (i % 2)) * r.uniform(0.9, 1.08)
        out.append((t + r.normal(0, 0.002), v))
        t += 1.0 / rate
        i += 1
    return out


def cymbal(vel=0.7, r=None, dur=2.4, bright=1.0):
    """clash cymbal: dense inharmonic partials + hiss, highs fade first"""
    r = r or rng(0)
    n = ns(dur)
    t = np.arange(n) / SR
    y = np.zeros(n)
    fs = np.exp(r.uniform(np.log(380), np.log(12500), 150))
    for f in fs:
        tau = 1.6 * (900 / f) ** 0.45
        y += r.uniform(0.3, 1.0) * np.exp(-t / tau) * np.sin(TAU * f * t + r.uniform(0, TAU)) / np.sqrt(150)
    hiss = hp(r.standard_normal(n), 5200, 2) * np.exp(-t / (0.7 * bright)) * 0.6
    y = (y + hiss) * (1 - np.exp(-t / 0.002))
    y += bp(r.standard_normal(n), 2000, 9000, 1) * np.exp(-t / 0.006) * 0.8
    return fades(y * vel, 0.0005, 0.2)


def timpani(f, vel=0.8, r=None, dur=2.2):
    r = r or rng(0)
    t = tt(dur)
    modes = [(f, 1.0, 1.5), (f * 1.504, 0.55, 0.9), (f * 1.742, 0.3, 0.6), (f * 2.0, 0.35, 0.5), (f * 2.245, 0.18, 0.4), (f * 2.494, 0.12, 0.3)]
    y = modal(dur, modes, r, glide=0.025 * vel, glide_tau=0.06)
    thump = lp(r.standard_normal(len(t)), 400, 2) * np.exp(-t / 0.018) * 0.9
    return fades((y + thump) * vel, 0.001, 0.1)


def brush(vel=0.5, r=None, dur=0.35, swish=False):
    r = r or rng(0)
    n = ns(dur)
    t = np.arange(n) / SR
    nz = bp(r.standard_normal(n), 900, 9000, 1)
    if swish:
        e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5
    else:
        e = np.exp(-t / 0.045) * (1 - np.exp(-t / 0.003))
    return nz * e * vel * 0.5


# ---------------------------------------------------------------- strings / pads
def pluck(f, vel=0.7, r=None, dur=0.9, bright=0.5, pos=0.17):
    """plucked string (pizzicato) by additive partials with frequency-dependent decay"""
    r = r or rng(0)
    t = tt(dur)
    K = max(1, int(min(28, 7000 / f)))
    tau0 = 0.55 * (110 / f) ** 0.35
    y = np.zeros_like(t)
    for k in range(1, K + 1):
        ak = abs(np.sin(np.pi * k * pos)) / k ** (1.3 - 0.6 * bright)
        tau = tau0 / (1 + 0.45 * (k - 1) * (f / 150) ** 0.4)
        fk = k * f * np.sqrt(1 + 2e-5 * k * k)
        y += ak * np.exp(-t / tau) * np.sin(TAU * fk * t + r.uniform(0, TAU))
    y += lp(r.standard_normal(len(t)), 700) * np.exp(-t / 0.008) * 0.15
    return fades(y * vel * (1 - np.exp(-t / 0.0015)), 0.0005, 0.06)


def pad(freqs, dur, vel=0.5, r=None, att=0.6, rel=0.9, warm=900.0, detune=7.0, trem=None):
    """warm pad: three detuned saw voices per note through a gentle roll-off; stereo"""
    r = r or rng(0)
    n = ns(dur + rel)
    t = np.arange(n) / SR
    env = np.ones(n)
    a = ns(att)
    env[:a] = ramp(a)
    d = ns(dur)
    env[d:] *= ramp(n - d)[::-1]
    out = np.zeros((2, n))
    for f in freqs:
        for vi, (dc, pn) in enumerate([(-detune, -0.6), (0.0, 0.0), (detune, 0.6)]):
            cents = dc + 3 * np.sin(TAU * r.uniform(0.15, 0.4) * t + r.uniform(0, TAU))
            ph = phase(f * 2 ** (cents / 1200))
            K = max(1, int(min(30, 4000 / f)))
            y = np.zeros(n)
            for k in range(1, K + 1):
                y += (1 / k) / (1 + (k * f / warm) ** 2) * np.sin(k * ph + r.uniform(0, TAU))
            th = (pn + 1) * np.pi / 4
            out[0] += y * np.cos(th)
            out[1] += y * np.sin(th)
    if trem is not None:
        out *= trem(t)[None, :]
    return out * env[None, :] * vel / np.sqrt(len(freqs) * 3)
