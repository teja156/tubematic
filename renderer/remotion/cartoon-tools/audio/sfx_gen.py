# Ported from mromidev/claude-animated-shorts (templates/audio/sfx_gen.py), MIT License, Copyright (c) 2026 Mr omi.
# Verbatim: the synthesis library behind every sound; the video-specific parts live in score.py / cues.py / mix.py.

# Procedural sound effects for the bridge short (own numpy synthesis): marching boots on planks, deck flex + plank
# creaks, chain rattle and groan, bolt strain, metal snap/ping, chain whip, timber tearing, wood crack, big splash,
# droplets, river water, formant-synthesized crowd voices (oofs, whoa, murmur, hurrah) + applause, birds, crickets,
# breeze, swing squeaks, pushes, hammer on a sign, strolling footsteps, whooshes.
import numpy as np
from scipy import signal
from dsp import (SR, TAU, ns, tt, rng, lp, hp, bp, reson, resbank, peq, colored, smooth_noise, ramp, fades, shape,
                 phase, modal, impulse_train, pan, st, widen)


def _place_mono(buf, x, t):
    i = ns(t)
    a, b = max(0, i), min(len(buf), i + len(x))
    if b > a:
        buf[a:b] += x[a - i: b - i]


# ================================================================ creak engine (stick-slip friction)
def stick_slip(dur, rate, r, jitter=0.12, amp=None, accel_noise=0.0):
    """impulse train whose instantaneous rate follows `rate` (array or float, Hz); returns (impulses, times)"""
    n = ns(dur)
    rt = np.full(n, rate, float) if np.isscalar(rate) else np.interp(np.arange(n), np.linspace(0, n - 1, len(rate)), rate)
    x = np.zeros(n)
    t = r.uniform(0, 1.0 / max(rt[0], 1))
    while t < dur:
        k = ns(t)
        if k >= n:
            break
        a = 1.0 if amp is None else amp[min(k, len(amp) - 1)]
        x[k] += a * r.uniform(0.55, 1.0)
        t += (1.0 / max(rt[k], 1.0)) * (1 + r.normal(0, jitter))
    return x


WOOD = [(230, 9, 1.0), (520, 12, 0.8), (940, 14, 0.55), (1650, 16, 0.35), (2800, 18, 0.18)]
TIMBER = [(95, 7, 1.0), (180, 9, 0.9), (330, 11, 0.7), (560, 12, 0.5), (930, 14, 0.3), (1500, 15, 0.15)]
CHAIN = [(190, 28, 0.9), (430, 34, 1.0), (760, 38, 0.8), (1180, 42, 0.6), (1720, 45, 0.45), (2500, 50, 0.3), (3400, 55, 0.18)]
SMALLMETAL = [(1850, 40, 1.0), (3100, 45, 0.8), (4600, 50, 0.6), (6900, 55, 0.35)]


def creak(dur, r, rate0=110, rate1=180, modes=WOOD, shape_pts=None, rough=0.12, noise=0.05, scale=1.0):
    """wooden/metal creak: friction impulses exciting a resonator bank; rate glides rate0 -> rate1 (with a bend)"""
    n = ns(dur)
    u = np.linspace(0, 1, 64)
    rate = rate0 + (rate1 - rate0) * u + 0.15 * (rate0 + rate1) / 2 * np.sin(np.pi * u) * r.uniform(-1, 1)
    env_pts = shape_pts or [(0, 0), (0.15, 1), (0.7, 0.85), (1.0, 0)]
    env = np.interp(np.linspace(0, 1, n), [p[0] for p in env_pts], [p[1] for p in env_pts])
    x = stick_slip(dur, rate, r, rough, env)
    md = [(f * scale * r.uniform(0.94, 1.06), q, g) for f, q, g in modes]
    y = resbank(x, md)
    y += noise * bp(r.standard_normal(n), 400, 4000, 1) * env
    return fades(y, 0.004, 0.03)


def clink(r, f0=None, dur=0.12, bright=1.0):
    """one small metal-on-metal clink (chain link, buckle, canteen)"""
    f0 = f0 or np.exp(r.uniform(np.log(1800), np.log(5200)))
    modes = [(f0, 1.0, r.uniform(0.012, 0.03)), (f0 * r.uniform(2.3, 2.9), 0.5 * bright, 0.01), (f0 * r.uniform(3.9, 5.1), 0.25 * bright, 0.006)]
    y = modal(dur, modes, r)
    t = tt(dur)
    y += hp(r.standard_normal(len(t)), 3000) * np.exp(-t / 0.0008) * 0.4
    return y


def rattle(dur, r, density=30.0, env=None, heavy=False):
    """chain / kit rattle: a cloud of clinks"""
    n = ns(dur)
    y = np.zeros(n)
    cnt = int(density * dur) + 1
    times = np.sort(r.uniform(0, dur, cnt))
    for tm in times:
        k = ns(tm)
        a = 1.0 if env is None else env[min(k, n - 1)]
        if a < 0.02:
            continue
        c = clink(r, np.exp(r.uniform(np.log(700 if heavy else 1600), np.log(2600 if heavy else 5500))), 0.1)
        _place_mono(y, c * a * r.uniform(0.4, 1.0), tm)
    return y


# ================================================================ marching boots
def boot(r, hard=1.0):
    """one hobnailed boot heel on a wooden plank"""
    dur = 0.22
    t = tt(dur)
    f = r.uniform(78, 118)
    thump = np.exp(-t / r.uniform(0.028, 0.045)) * np.sin(phase(f * (1 + 0.18 * np.exp(-t / 0.012))))
    plank = modal(dur, [(r.uniform(170, 260), 0.6, r.uniform(0.018, 0.035)), (r.uniform(380, 620), 0.45, r.uniform(0.012, 0.025)),
                        (r.uniform(800, 1300), 0.25, 0.01)], r)
    nz = r.standard_normal(len(t))
    slap = bp(nz, 500, 3500, 1) * np.exp(-t / 0.006) * 0.5
    click = hp(nz, 3500) * np.exp(-t / 0.0012) * 0.22 * hard
    return thump + plank + slap + click


def column_stomp(r, intensity=1.0, foot=0, boots=30, spread=0.007, width=0.6, boom_gain=1.0):
    """74 men landing the same foot together: ~30 audible boots with tiny timing spread + deck boom + kit jingle"""
    dur = 0.6
    out = np.zeros((2, ns(dur)))
    pre = 0.03
    for i in range(boots):
        row = i // 4
        g = r.uniform(0.6, 1.0) * 10 ** (-0.35 * row / 20)
        dt = pre + abs(r.normal(0, spread)) * (1 if r.uniform() < 0.7 else -0.6)
        x = boot(r, intensity) * g
        p = np.clip((i % 4 - 1.5) / 1.5 * width * 0.6 + r.normal(0, 0.1) + (0.05 if foot else -0.05), -1, 1)
        k = ns(max(0, dt))
        seg = pan(x, p)
        m = min(seg.shape[1], out.shape[1] - k)
        out[:, k:k + m] += seg[:, :m]
    t = tt(dur)
    boom = np.exp(-t / 0.13) * np.sin(phase(r.uniform(47, 56) * (1 + 0.25 * np.exp(-t / 0.02)))) * 2.2 * intensity * boom_gain
    out += np.roll(st(boom), ns(pre), axis=1)
    kit = rattle(0.25, r, 50, np.exp(-np.linspace(0, 1, ns(0.25)) * 3)) * 0.35
    out[:, ns(pre + 0.02): ns(pre + 0.02) + len(kit)] += widen(kit, r, 9, 0.8)
    return out, pre


def deck_flex(r, a):
    """the deck answers a footfall once it is bouncing: low flex 'whump', plank creak on the rebound, hangers rattle"""
    dur = 0.75
    n = ns(dur)
    t = np.arange(n) / SR
    whump = np.exp(-t / 0.2) * np.sin(phase(r.uniform(38, 48) * (1 - 0.12 * t))) * (1 - np.exp(-t / 0.015))
    c = creak(r.uniform(0.2, 0.32) + 0.2 * a, r, r.uniform(70, 110), r.uniform(150, 260), WOOD, rough=0.15, scale=r.uniform(0.85, 1.2))
    y = whump * 1.6
    _place_mono(y, c * (0.35 + 0.65 * a), r.uniform(0.07, 0.13))
    ratt = rattle(0.35, r, 25 + 40 * a, np.exp(-np.linspace(0, 1, ns(0.35)) * 2.5), heavy=True) * 0.3 * a
    _place_mono(y, ratt, 0.04)
    return widen(y, r, 13, 0.6)


def chain_groan(dur, r, i0=0.2, i1=1.0, rate0=22, rate1=40, beats=None, t0=0.0):
    """iron chains under rising tension: slow stick-slip through metal modes + a low moan; swells on each footfall"""
    n = ns(dur)
    t = np.arange(n) / SR
    inten = i0 + (i1 - i0) * (t / dur) ** 1.4
    am = np.full(n, 0.35)
    if beats is not None:
        for b in beats:
            u = t + t0 - (b + 0.04)
            am += np.where(u > 0, np.exp(-u / 0.22) * (1 - np.exp(-u / 0.03)), 0)
    env = np.clip(am, 0, 1.2) * inten
    rate = np.linspace(rate0, rate1, 64) * (1 + 0.1 * np.sin(np.linspace(0, 9, 64)))
    x = stick_slip(dur, rate, r, 0.2, env)
    y = resbank(x, [(f * r.uniform(0.97, 1.03), q, g) for f, q, g in CHAIN])
    moan_f = np.linspace(48, 72, n) * (1 + 0.03 * smooth_noise(n, r, 1.5))
    ph = phase(moan_f)
    moan = sum(np.sin(k * ph) / k for k in range(1, 14))
    moan = bp(moan, 180, 900, 2) * env * 0.4
    return fades(y + moan, 0.2, 0.05)


# ================================================================ metal / bolt
def bolt_strain(r, a=1.0, dur=0.32):
    c = creak(dur, r, r.uniform(320, 420) * (0.9 + 0.3 * a), r.uniform(520, 760) * (0.9 + 0.3 * a), SMALLMETAL,
              [(0, 0), (0.2, 1), (0.75, 0.7), (1, 0)], rough=0.1, noise=0.02)
    tick = clink(r, r.uniform(2500, 3800), 0.08) * 0.6
    y = c
    _place_mono(y, tick, 0.0)
    return y


def bolt_snap(r):
    """bolt shears: crack + two bolt halves ringing as they fly (slight Doppler drop) + release thunk + chain jolt"""
    dur = 1.6
    n = ns(dur)
    t = np.arange(n) / SR
    nz = r.standard_normal(n)
    crack = bp(nz, 900, 14000, 2) * np.exp(-t / 0.0028) * 2.2
    crack[: ns(0.0004)] += 1.5
    y = crack
    for k, (f0, dl, gl) in enumerate([(1760, 0.0, -0.07), (2090, 0.009, -0.05)]):
        g = 1 + gl * (1 - np.exp(-t / 0.35))
        ph = phase(f0 * g)
        ring = (np.exp(-t / 0.55) * np.sin(ph) + 0.55 * np.exp(-t / 0.22) * np.sin(2.756 * ph + 1)
                + 0.3 * np.exp(-t / 0.08) * np.sin(5.404 * ph + 2) + 0.12 * np.exp(-t / 0.03) * np.sin(8.933 * ph))
        ring *= 1 - np.exp(-t / 0.0015)
        y = y + np.roll(ring, ns(dl)) * (0.8 if k else 1.0)
    thunk = np.exp(-t / 0.07) * np.sin(phase(105 * (1 - 0.3 * t))) * 1.2
    y += thunk
    jolt = rattle(0.35, r, 70, np.exp(-np.linspace(0, 1, ns(0.35)) * 3), heavy=True) * 0.6
    _place_mono(y, jolt, 0.01)
    return fades(y, 0.0, 0.1)


def whoosh(dur, r, peak=0.3, f_lo=350, f_hi=2200, width=0.8, tail=0.25, air=0.15):
    """noise whoosh: band centre and level rise to `peak` then fall (ease-out burst when peak is early)"""
    n = ns(dur)
    nz = colored(n, r, 0.6)
    t = np.arange(n) / SR
    env = np.where(t < peak, (t / peak) ** 2.2, np.exp(-(t - peak) / tail))
    fc = lambda T: f_lo + (f_hi - f_lo) * np.interp(T, t, np.where(t < peak, t / peak, np.exp(-(t - peak) / (tail * 1.3))))
    y = shape(nz, lambda T, F: np.exp(-0.5 * (np.log2(np.maximum(F[:, None], 20) / fc(T)[None, :]) / width) ** 2), 1024, 256)
    y = y * env + air * hp(nz, 4000) * env ** 2
    return fades(y, 0.005, 0.04)


def chain_whip(r):
    """the snapped backstay whipping up: fast swish + rattle along it + heavy clank as it flops"""
    y = whoosh(0.75, r, peak=0.07, f_lo=500, f_hi=2600, width=0.7, tail=0.18, air=0.3)
    ratt = rattle(0.6, r, 90, np.exp(-np.linspace(0, 1, ns(0.6)) * 2.2), heavy=True) * 0.5
    _place_mono(y, ratt, 0.02)
    clank = modal(0.5, [(310, 0.8, 0.09), (690, 0.6, 0.06), (1130, 0.4, 0.04), (1870, 0.25, 0.03)], r)
    clank += lp(r.standard_normal(ns(0.5)), 500) * np.exp(-tt(0.5) / 0.03) * 0.8
    _place_mono(y, np.concatenate([clank, np.zeros(ns(0.3))]) * 0.7, 0.6)
    return y


# ================================================================ timber + water
def timber_tear(r, dur=0.8):
    """the near half tearing loose: big low creak + splintering crackle that thickens"""
    n = ns(dur)
    t = np.arange(n) / SR
    c = creak(dur, r, 28, 75, TIMBER, [(0, 0), (0.3, 0.8), (0.85, 1), (1, 0.3)], rough=0.25, noise=0.08)
    dens = 10 + 120 * (t / dur) ** 2
    cr = np.zeros(n)
    tm = 0.05
    while tm < dur:
        k = ns(tm)
        crk = modal(0.06, [(r.uniform(600, 1800), 1, 0.006), (r.uniform(2000, 5000), 0.6, 0.003)], r)
        crk += hp(r.standard_normal(ns(0.06)), 1500) * np.exp(-tt(0.06) / 0.002)
        _place_mono(cr, crk * r.uniform(0.2, 1.0) * (t[min(k, n - 1)] / dur), tm)
        tm += r.exponential(1.0 / dens[min(k, n - 1)])
    return c + 0.5 * cr


def wood_crack(r):
    """deck slamming down: splintering crack burst + heavy timber boom"""
    dur = 1.2
    n = ns(dur)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for i in range(9):
        tm = (abs(r.normal(0, 0.03)) if i else 0.0) + i * 0.006     # first splinter exactly on the impact
        md = [(r.uniform(500, 1400), 1.0, 0.012), (r.uniform(1500, 3500), 0.7, 0.006), (r.uniform(3500, 7000), 0.4, 0.003)]
        k = modal(0.15, md, r) + hp(r.standard_normal(ns(0.15)), 1200) * np.exp(-tt(0.15) / 0.003)
        _place_mono(y, k * (1.0 if i == 0 else r.uniform(0.3, 0.8)), tm)
    boom = np.exp(-t / 0.32) * np.sin(phase(52 * (1 + 0.4 * np.exp(-t / 0.03)))) * 3.0
    boom += resbank(lp(r.standard_normal(n), 900) * np.exp(-t / 0.05), [(f, q, g) for f, q, g in TIMBER[:4]]) * 0.5
    return y + boom


def bubbles(dur, r, rate, f_lo=300, f_hi=2500, tau=(0.008, 0.035), env=None, rise=(4, 12)):
    """Minnaert-style bubble 'plinks': damped sines gliding up"""
    n = ns(dur)
    y = np.zeros(n)
    tm = 0.0
    while tm < dur:
        k = ns(tm)
        a = 1.0 if env is None else env[min(k, n - 1)]
        rr = rate if np.isscalar(rate) else rate[min(k, n - 1)]
        if a > 0.01:
            f0 = np.exp(r.uniform(np.log(f_lo), np.log(f_hi)))
            ta = r.uniform(*tau)
            L = min(int(ta * 6 * SR), n - k)
            if L > 8:
                tl = np.arange(L) / SR
                b = np.exp(-tl / ta) * np.sin(phase(f0 * (1 + r.uniform(*rise) * tl)))
                y[k:k + L] += b * a * r.uniform(0.2, 1.0) * (600 / f0) ** 0.3
        tm += r.exponential(1.0 / max(rr, 0.1))
    return y


def splash_big(r):
    """the near half of the deck + 70 soldiers hitting two feet of water: thump, slap, body, bubble cloud, spray"""
    dur = 2.6
    n = ns(dur)
    t = np.arange(n) / SR
    nz = r.standard_normal(n)
    thump = np.exp(-t / 0.2) * np.sin(phase(58 * (1 + 0.5 * np.exp(-t / 0.025)))) * 2.0
    slap = bp(nz, 250, 7000, 1) * np.exp(-t / 0.035) * 1.6
    body_env = (1 - np.exp(-t / 0.02)) * (0.6 * np.exp(-t / 0.18) + 0.4 * np.exp(-t / 0.7))
    body = shape(colored(n, r, 0.4), lambda T, F: (np.exp(-0.5 * (np.log2(np.maximum(F[:, None], 20) / (900 + 1800 * np.exp(-T[None, :] / 0.4))) / 1.4) ** 2)), 1024, 256)
    body *= body_env * 1.4
    bub = bubbles(dur, r, 900 * np.exp(-t / 0.5) + 20, 250, 2600, (0.006, 0.03), np.exp(-t / 0.8)) * 1.1
    spray_env = np.clip((t - 0.25) / 0.2, 0, 1) * np.exp(-np.maximum(t - 0.45, 0) / 0.55)
    spray = bubbles(dur, r, 500 * spray_env + 5, 1200, 5000, (0.003, 0.012), spray_env, rise=(8, 25)) * 0.6
    spray += hp(nz, 3000) * spray_env * 0.06
    return fades(thump + slap + body + bub + spray, 0.0, 0.3)


def water_bed(dur, r, close=1.0, slosh_rate=0.8):
    """river around the soldiers sitting in it: flow noise, babble, lapping, sloshes, drips"""
    n = ns(dur)
    t = np.arange(n) / SR
    out = np.zeros((2, n))
    for ch in range(2):
        lap = 0.65 + 0.35 * smooth_noise(n, r, 0.5)
        flow = bp(colored(n, r, 0.8), 180, 2600, 1) * lap * 0.5
        bab = bubbles(dur, r, 70 * close + 15, 350, 2400, (0.006, 0.025)) * 0.9 * close
        rum = lp(colored(n, r, 2.0), 160, 2) * 0.35
        out[ch] = flow + bab + rum
    tm = r.uniform(0.2, 0.8)
    while tm < dur - 0.5:
        sl = shape(r.standard_normal(ns(0.5)), lambda T, F: np.exp(-0.5 * (np.log2(np.maximum(F[:, None], 20) / 700) / 1.2) ** 2), 512, 128)
        sl *= np.exp(-tt(0.5) / 0.12) * (1 - np.exp(-tt(0.5) / 0.03)) * 0.9 * close
        sl += bubbles(0.5, r, 120, 300, 1500, (0.006, 0.02), np.exp(-tt(0.5) / 0.15)) * 0.7 * close
        p = r.uniform(-0.7, 0.7)
        seg = pan(sl, p)
        k = ns(tm)
        out[:, k:k + seg.shape[1]] += seg[:, : n - k]
        tm += r.exponential(1 / slosh_rate) + 0.3
    drips = bubbles(dur, r, 3.5 * close, 1500, 4200, (0.004, 0.012), rise=(10, 30)) * 0.9
    out += widen(drips, r, 7, 1.0)
    return out


# ================================================================ formant voices
VOW = {"a": (730, 1090, 2440, 3400), "o": (570, 840, 2410, 3400), "u": (300, 870, 2240, 3300), "U": (440, 1020, 2240, 3300),
       "A": (640, 1190, 2390, 3400), "e": (530, 1840, 2480, 3500), "i": (270, 2290, 3010, 3600), "ae": (660, 1720, 2410, 3400),
       "er": (490, 1350, 1690, 3300), "E": (580, 1700, 2500, 3500), "ei": (400, 2000, 2550, 3500)}
BWS = np.array([85.0, 110.0, 160.0, 220.0])


def vox(f0, forms, amp, r, scale=1.0, tilt=1.15, breath=0.12, fmax=5500.0, jitter=0.012):
    """additive source-filter voice: f0 (n,), forms (n, 4) formant tracks, amp (n,) -> mono"""
    n = len(f0)
    jit = 1 + jitter * smooth_noise(n, r, 18.0)
    ph = phase(f0 * jit)
    y = np.zeros(n)
    K = int(fmax / max(f0.min(), 60))
    Fm = forms * scale
    for k in range(1, K + 1):
        fk = k * f0
        H = np.ones(n)
        for i in range(4):
            Fi = Fm[:, i]
            H *= Fi ** 2 / np.sqrt((Fi ** 2 - fk ** 2) ** 2 + (fk * BWS[i] * (1 + 0.3 * (scale - 1))) ** 2)
        y += H * k ** (-tilt) * np.sin(k * ph + r.uniform(0, TAU)) * (fk < fmax)
    asp = peq(bp(r.standard_normal(n), 500, 5000, 1), float(np.mean(Fm[:, 1])), 8, 1.5)
    y = y / (np.std(y) + 1e-9) + breath * asp / (np.std(asp) + 1e-9)
    return y * amp


def _track(n, pts, t_rel):
    """pts = [(time_s, value)] -> per-sample curve"""
    return np.interp(t_rel, [p[0] for p in pts], [p[1] for p in pts])


def vowel_track(n, segs):
    """segs = [(time_s, vowel)] -> (n, 4) formant tracks with smooth transitions"""
    t = np.arange(n) / SR
    out = np.zeros((n, 4))
    for i in range(4):
        out[:, i] = np.interp(t, [s[0] for s in segs], [VOW[s[1]][i] for s in segs])
    return out


def oof(r, kind="oof", base=None, scale=None):
    """one man's impact grunt: 'oof', 'ugh', 'oh', 'ow' (falling pitch, pushed air, fricative / glottal end)"""
    base = base or r.uniform(95, 150)
    scale = scale or r.uniform(0.95, 1.1)
    if kind == "oof":
        d = r.uniform(0.2, 0.26)
        segs, fpts = [(0, "U"), (d, "u")], [(0, 1.3), (0.05, 1.2), (d, 0.82)]
    elif kind == "ugh":
        d = r.uniform(0.18, 0.24)
        segs, fpts = [(0, "A"), (d, "er")], [(0, 1.25), (d * 0.6, 1.05), (d, 0.7)]
    elif kind == "oh":
        d = r.uniform(0.22, 0.3)
        segs, fpts = [(0, "o"), (d, "U")], [(0, 1.4), (0.06, 1.45), (d, 0.9)]
    else:  # ow
        d = r.uniform(0.28, 0.36)
        segs, fpts = [(0, "a"), (d * 0.45, "a"), (d, "u")], [(0, 1.2), (d * 0.3, 1.5), (d, 0.85)]
    tail = 0.12 if kind == "oof" else 0.04
    n = ns(d + tail)
    t = np.arange(n) / SR
    f0 = base * _track(n, fpts, t)
    forms = vowel_track(n, segs)
    amp = np.clip(t / 0.012, 0, 1) * np.where(t < d, 1 - 0.35 * t / d, np.clip(1 - (t - d) / 0.025, 0, 1) * 0.65)
    y = vox(f0, forms, amp, r, scale, tilt=1.05, breath=0.35)
    push = bp(r.standard_normal(n), 300, 3000, 1) * np.exp(-t / 0.03) * 0.5
    y += push
    if kind == "oof":
        fr = hp(r.standard_normal(n), 1300) * np.clip((t - d + 0.03) / 0.03, 0, 1) * np.exp(-np.maximum(t - d, 0) / 0.05) * 0.35
        y += peq(fr, 4000, 6, 1.0)
    return fades(y, 0.002, 0.02)


def whoa(r, base=None, dur=None):
    base = base or r.uniform(105, 165)
    d = dur or r.uniform(0.38, 0.55)
    n = ns(d)
    t = np.arange(n) / SR
    f0 = base * _track(n, [(0, 1.0), (d * 0.4, 1.35), (d, 1.1)], t)
    forms = vowel_track(n, [(0, "u"), (0.07, "o"), (d * 0.6, "a"), (d, "A")])
    amp = np.clip(t / 0.05, 0, 1) * np.clip((d - t) / 0.08, 0, 1)
    return vox(f0, forms, amp, r, r.uniform(0.95, 1.1), tilt=1.0, breath=0.25)


def babble(dur, r, base, scale, rate=4.2, active=0.75, fmax=3600):
    """one person talking far away: random syllables, consonant puffs, pauses"""
    n = ns(dur)
    t = np.arange(n) / SR
    segs, fp, ap = [], [], []
    tm = r.uniform(0, 0.4)
    vs = list(VOW)
    while tm < dur:
        if r.uniform() > active:
            tm += r.uniform(0.25, 0.8)
            ap += [(tm - 0.01, 0.0)]
            continue
        L = r.uniform(0.6, 1.4) / rate
        v = vs[r.integers(len(vs))]
        segs.append((tm + L * 0.5, v))
        fp += [(tm, r.uniform(0.9, 1.2)), (tm + L, r.uniform(0.8, 1.1))]
        ap += [(tm, 0.05), (tm + L * 0.25, r.uniform(0.6, 1.0)), (tm + L * 0.8, r.uniform(0.4, 0.8)), (tm + L, 0.05)]
        tm += L
    if len(segs) < 2:
        return np.zeros(n)
    forms = vowel_track(n, [(0, segs[0][1])] + segs)
    f0 = base * _track(n, [(0, 1.0)] + sorted(fp), t) * (1 - 0.08 * t / dur)
    amp = _track(n, [(0, 0.0)] + sorted(ap) + [(dur, 0.0)], t)
    y = vox(f0, forms, amp, r, scale, tilt=1.25, breath=0.2, fmax=fmax)
    cons = hp(r.standard_normal(n), 2500) * np.clip(np.abs(np.gradient(amp)) * SR * 0.02, 0, 1) * 0.3
    return y + cons


def hurrah(r, base, scale, kid=False):
    """one 'hurrah!' / 'hooray!' / 'hey!'"""
    kind = r.integers(3)
    if kind == 0:   # hur-RAH
        d = r.uniform(0.6, 0.85)
        segs = [(0, "er"), (0.08, "er"), (0.16, "a"), (d, "A")]
        fpts = [(0, 1.15), (0.12, 1.2), (0.2, 1.6), (d * 0.7, 1.5), (d, 1.15)]
    elif kind == 1:  # hoo-RAY
        d = r.uniform(0.55, 0.8)
        segs = [(0, "u"), (0.1, "U"), (0.2, "e"), (d * 0.6, "ei"), (d, "i")]
        fpts = [(0, 1.2), (0.15, 1.25), (0.25, 1.65), (d, 1.3)]
    else:           # HEY!
        d = r.uniform(0.3, 0.45)
        segs = [(0, "E"), (d * 0.7, "ei"), (d, "i")]
        fpts = [(0, 1.5), (0.08, 1.7), (d, 1.35)]
    n = ns(d)
    t = np.arange(n) / SR
    f0 = base * _track(n, fpts, t)
    forms = vowel_track(n, segs)
    amp = np.clip(t / 0.04, 0, 1) * np.clip((d - t) / 0.1, 0, 1) * (0.7 + 0.3 * np.clip((t - 0.15) / 0.1, 0, 1))
    h = hp(r.standard_normal(n), 800) * np.clip(1 - t / 0.06, 0, 1) * 0.4
    return vox(f0, forms, amp, r, scale, tilt=0.9 if not kid else 0.95, breath=0.3) + h


def applause(dur, r, people=36, env=None):
    n = ns(dur)
    out = np.zeros((2, n))
    for p in range(people):
        rate = r.uniform(3.6, 5.6)
        fc = r.uniform(900, 2600)
        cup = r.uniform(0.0, 0.6)
        tm = r.uniform(0, 1 / rate)
        y = np.zeros(n)
        while tm < dur:
            k = ns(tm)
            L = ns(0.05)
            if k + L >= n:
                break
            tl = np.arange(L) / SR
            c = reson(r.standard_normal(L), fc * r.uniform(0.9, 1.1), 1.4) * np.exp(-tl / r.uniform(0.005, 0.009))
            c += cup * reson(r.standard_normal(L), r.uniform(400, 700), 4) * np.exp(-tl / 0.012)
            y[k:k + L] += c * r.uniform(0.6, 1.0)
            tm += (1 / rate) * r.uniform(0.9, 1.1)
        out += pan(y, r.uniform(-0.9, 0.9))
    if env is not None:
        out *= env[None, :]
    return out


# ================================================================ nature
def bird_chirps(dur, r, density=0.5, kind="sparrow"):
    """sparse distant birds: sparrow chips or a blackbird-like fluting phrase"""
    n = ns(dur)
    y = np.zeros(n)
    tm = r.uniform(0.2, 1.5)
    while tm < dur - 1.0:
        if kind == "sparrow":
            for j in range(r.integers(2, 6)):
                L = r.uniform(0.04, 0.08)
                tl = tt(L)
                f = r.uniform(3800, 5600) * (1 - 0.35 * tl / L) if r.uniform() < 0.6 else r.uniform(3000, 4200) * (1 + 0.4 * tl / L)
                c = np.sin(phase(f)) * np.sin(np.pi * tl / L) ** 2
                _place_mono(y, c * r.uniform(0.5, 1.0), tm + j * r.uniform(0.09, 0.16))
            tm += r.exponential(1 / density) + 0.6
        else:
            for j in range(r.integers(3, 7)):
                L = r.uniform(0.09, 0.22)
                tl = tt(L)
                f0 = r.uniform(1500, 2900)
                f = f0 * (1 + r.uniform(-0.25, 0.3) * np.sin(np.pi * tl / L * r.uniform(0.5, 1.5)))
                c = (np.sin(phase(f)) + 0.15 * np.sin(2 * phase(f))) * np.sin(np.pi * tl / L) ** 1.5
                _place_mono(y, c * r.uniform(0.4, 1.0), tm)
                tm += L + r.uniform(0.03, 0.12)
            tm += r.exponential(1 / density) + 1.0
    return y


def crickets(dur, r, voices=3):
    n = ns(dur)
    y = np.zeros(n)
    t = np.arange(n) / SR
    for v in range(voices):
        f = r.uniform(4200, 4900)
        pulse = (np.sin(TAU * r.uniform(28, 34) * t) > 0.2).astype(float)
        chirp = (np.sin(TAU * r.uniform(1.6, 2.4) * t + r.uniform(0, TAU)) > 0.55).astype(float)
        e = lp(pulse * chirp, 200, 1)
        y += np.sin(TAU * f * t) * e * r.uniform(0.4, 1.0)
    return y


def breeze(dur, r, level=1.0, gust=0.18, bright=900):
    n = ns(dur)
    out = np.zeros((2, n))
    g = 0.6 + 0.4 * smooth_noise(n, r, gust)
    for ch in range(2):
        w = lp(colored(n, r, 1.0), bright, 2) * g
        w += 0.25 * bp(colored(n, r, 0.5), 1200, 4000, 1) * g ** 2
        out[ch] = w * level
    return out


def flag_flutter(dur, r):
    n = ns(dur)
    t = np.arange(n) / SR
    rate = 5.5 + 1.5 * smooth_noise(n, r, 0.3)
    m = 0.5 + 0.5 * np.sin(phase(rate))
    return bp(r.standard_normal(n), 300, 3000, 1) * m ** 3 * (0.5 + 0.5 * smooth_noise(n, r, 0.2))


# ================================================================ park, sign, tourists
def swing_squeak(r, a=1.0, fwd=True):
    """playground swing hanger squeak through the bottom of the arc ('eee' forward, 'aww' back)"""
    d = 0.22 + 0.2 * a
    lo, hi = (520, 760) if fwd else (380, 470)
    c = creak(d, r, lo, hi, SMALLMETAL if fwd else CHAIN[2:], [(0, 0), (0.35, 1), (0.65, 1), (1, 0)], rough=0.06, noise=0.01,
              scale=r.uniform(0.9, 1.1))
    return c


def push_thump(r):
    d = 0.3
    t = tt(d)
    th = lp(r.standard_normal(len(t)), 350, 2) * np.exp(-t / 0.035) * 1.5
    cloth = bp(r.standard_normal(len(t)), 900, 4500, 1) * np.exp(-t / 0.05) * 0.25
    jing = rattle(0.25, r, 30, np.exp(-np.linspace(0, 1, ns(0.25)) * 3), heavy=False) * 0.25
    y = th + cloth
    _place_mono(y, jing, 0.02)
    return y


def hammer_hit(r, big=1.0):
    """officer's hammer: steel on nail head ('tink') + wooden sign 'thock' + post thump"""
    d = 0.9
    t = tt(d)
    tink = modal(d, [(3150, 0.6, 0.05), (5070, 0.45, 0.03), (7900, 0.25, 0.015)], r)
    sign = modal(d, [(165, 1.0, 0.09), (345, 0.8, 0.07), (610, 0.55, 0.05), (990, 0.35, 0.03), (1520, 0.2, 0.02)], r, glide=0.03)
    nz = r.standard_normal(len(t))
    hit = bp(nz, 400, 6000, 1) * np.exp(-t / 0.004) * 1.2
    post = np.exp(-t / 0.08) * np.sin(phase(82 * (1 + 0.3 * np.exp(-t / 0.01)))) * 1.3
    return fades((tink * 0.8 + sign * 1.2 + hit + post) * big, 0.0, 0.1)


def stroll_step(r, scuff=0.5):
    d = 0.3
    t = tt(d)
    heel = np.exp(-t / 0.03) * np.sin(phase(r.uniform(90, 130) * (1 + 0.15 * np.exp(-t / 0.01))))
    plank = modal(d, [(r.uniform(180, 280), 0.5, 0.025), (r.uniform(420, 700), 0.35, 0.015)], r)
    nz = r.standard_normal(len(t))
    tap = bp(nz, 700, 4000, 1) * np.exp(-t / 0.005) * 0.4
    sc = bp(nz, 400, 3000, 1) * np.clip(t / 0.02, 0, 1) * np.exp(-t / 0.07) * 0.25 * scuff
    return (heel * 0.7 + plank + tap + sc)
