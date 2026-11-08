# The Chicago short's own sounds (1858-61: mud, horses, jackscrews, a foreman's whistle, masons, a hotel dining room,
# a river at dusk), composed from the sfx_gen / dsp parts in the same style as cues.py's composites: every generator
# takes a seeded rng first and returns (signal, anchor seconds). Registered into cues.GENERATORS.
# The parts they are built from are mromidev/claude-animated-shorts' synthesis library (MIT, Copyright (c) 2026 Mr omi).
import numpy as np
from dsp import (SR, TAU, ns, tt, lp, hp, bp, peq, reson, resbank, colored, smooth_noise, fades, phase, modal, pan, st,
                 place, widen)
import sfx_gen as G
from sfx_gen import _place_mono, creak as _creak, stick_slip, WOOD, TIMBER, CHAIN, SMALLMETAL

IRON = [(240, 30, 0.8), (610, 38, 1.0), (1130, 44, 0.8), (1890, 48, 0.55), (2950, 52, 0.35), (4200, 55, 0.2)]
CHINA = [(1780, 1.0, 0.18), (3240, 0.55, 0.11), (4980, 0.3, 0.07), (7100, 0.15, 0.04)]


def _pad(x, n):
    x = np.asarray(x, float)
    return np.pad(x, [(0, 0)] * (x.ndim - 1) + [(0, max(0, n - x.shape[-1]))])[..., :n]


# ================================================================ mud
def squelch(r, size=1.0, dur=0.55):
    """one wet mud squelch: low thump, sucking slap, a cloud of fat low bubbles"""
    n = ns(dur)
    t = np.arange(n) / SR
    thump = np.exp(-t / (0.05 * size)) * np.sin(phase(r.uniform(55, 80) * (1 + 0.5 * np.exp(-t / 0.02)))) * 1.2 * size
    slap = bp(r.standard_normal(n), 180, 1600, 2) * np.exp(-t / 0.045) * (1 - np.exp(-t / 0.004)) * 1.1
    slap = peq(slap, r.uniform(350, 600), 8, 2.0)
    bub = G.bubbles(dur, r, 260 * np.exp(-t / 0.15) + 8, 120, 700, (0.008, 0.03), np.exp(-t / 0.25), rise=(2, 6)) * 1.3
    return fades(thump + slap + bub, 0.001, 0.08)


def boot_suck(r, dur=0.6, pop=1.0):
    """a boot pulled out of deep mud: a slurp rising in pitch through sticky pops, then the release pop"""
    n = ns(dur)
    t = np.arange(n) / SR
    u = t / dur
    fc = 180 + 700 * u ** 1.6
    nz = colored(n, r, 0.5)
    y = np.zeros(n)
    # a resonance sweeping up: short overlapping band-passed blocks
    blk = ns(0.02)
    for a in range(0, n, blk):
        seg = nz[a: a + blk + ns(0.01)]
        f = fc[min(a, n - 1)]
        z = reson(seg, f, 6) + 0.5 * reson(seg, f * 2.3, 5)
        y[a: a + len(z)] += z[: n - a] * np.hanning(len(z))[: n - a]
    am = 0.4 + 0.6 * np.abs(smooth_noise(n, r, 18))
    y *= am * np.interp(u, [0, 0.15, 0.85, 1], [0, 1, 0.9, 0.0])
    sticky = G.bubbles(dur, r, 90, 200, 900, (0.004, 0.015), np.interp(u, [0, 0.8, 1], [0.6, 1, 0]), rise=(4, 12)) * 0.7
    y = y / (np.std(y) + 1e-9) * 0.35 + sticky
    k = ns(dur * 0.88)
    pk = modal(0.12, [(r.uniform(260, 380), 1.0, 0.012), (r.uniform(700, 1000), 0.4, 0.006)], r) * 1.4 * pop
    _place_mono(y, pk, dur * 0.88)
    return fades(np.pad(y, (0, ns(0.12))), 0.005, 0.03)


def mud_step(r, size=1.0, suck=True):
    """the gentleman steps off the plank into the mud: a big squelch, sinking slurp, then a boot suck"""
    y = np.zeros(ns(1.6))
    _place_mono(y, squelch(r, 1.4 * size, 0.7) * 1.2, 0.0)
    sink = G.bubbles(0.8, r, 60, 100, 450, (0.01, 0.04), np.exp(-tt(0.8) / 0.35), rise=(1, 3)) * 0.8
    _place_mono(y, sink, 0.12)
    if suck:
        _place_mono(y, boot_suck(r, 0.5, 0.6) * 0.7, 0.85)
    return widen(y, r, 7, 0.5), 0.0


def hoof(r, surface="mud", hard=1.0):
    """one hoof: mud = thump + squelch; stone = the clip-clop knock"""
    if surface == "mud":
        y = squelch(r, 0.8 * hard, 0.4) * 0.8
        return y
    d = 0.18
    t = tt(d)
    knock = modal(d, [(r.uniform(650, 900), 1.0, 0.015), (r.uniform(1600, 2300), 0.6, 0.008), (r.uniform(2800, 3800), 0.3, 0.004)], r)
    th = np.exp(-t / 0.02) * np.sin(phase(r.uniform(110, 150) * np.ones(len(t)))) * 0.6
    return (knock + th + hp(r.standard_normal(len(t)), 2500) * np.exp(-t / 0.001) * 0.3) * hard


def hooves(r, dur=3.0, rate=2.2, surface="mud", gait="walk"):
    """a horse walking / struggling: `rate` footfalls per second (trot: each footfall a near-pair)"""
    out = np.zeros(ns(dur + 0.6))
    t = r.uniform(0, 0.2)
    k = 0
    while t < dur:
        g = r.uniform(0.6, 1.0) * (1.0 if k % 2 else 0.8)
        _place_mono(out, hoof(r, surface, g) * g, t)
        if gait == "trot" and k % 2 == 0:
            _place_mono(out, hoof(r, surface, g * 0.6) * 0.5, t + 0.03)
        t += (1 / rate) * r.uniform(0.85, 1.15)
        k += 1
    return out, 0.0


def whinny(r, dur=1.3, base=None):
    """horse whinny: a high bright cry that rises, then a fast whinnying vibrato tumbling down, a breathy end"""
    base = base or r.uniform(420, 520)
    n = ns(dur)
    t = np.arange(n) / SR
    u = t / dur
    f0 = base * np.interp(u, [0, 0.12, 0.28, 0.75, 1.0], [0.95, 1.7, 1.8, 0.95, 0.65])
    vib = 1 + np.interp(u, [0, 0.25, 0.35, 1], [0, 0, 0.09, 0.06]) * np.sin(TAU * np.interp(u, [0, 1], [13, 9]) * t)
    f0 = f0 * vib * (1 + 0.01 * smooth_noise(n, r, 20))
    forms = G.vowel_track(n, [(0, "i"), (dur * 0.3, "e"), (dur * 0.7, "ae"), (dur, "a")])
    amp = np.clip(t / 0.05, 0, 1) * np.interp(u, [0, 0.2, 0.7, 1], [0.8, 1, 0.8, 0]) * (0.75 + 0.25 * np.abs(np.sin(TAU * 11 * t)))
    y = G.vox(f0, forms, amp, r, 1.35, tilt=0.85, breath=0.5, fmax=7000)
    rasp = bp(r.standard_normal(n), 1500, 6000, 1) * amp * 0.25
    y = y + rasp
    sn = snort(r)[0] * 0.5
    y = np.concatenate([y, np.zeros(ns(0.4))])
    _place_mono(y, sn, dur - 0.05)
    return fades(y, 0.005, 0.05), 0.0


def snort(r, blows=2):
    """horse snort: fluttering nostril blows"""
    out = np.zeros(ns(0.25 * blows + 0.3))
    for k in range(blows):
        d = r.uniform(0.18, 0.28)
        n = ns(d)
        t = np.arange(n) / SR
        flutter = 0.5 + 0.5 * np.sin(TAU * r.uniform(28, 40) * t) ** 2
        y = bp(colored(n, r, 0.7), 200, 2500, 1) * np.exp(-t / (d * 0.5)) * (1 - np.exp(-t / 0.006)) * flutter
        y = peq(y, r.uniform(500, 800), 6, 1.5)
        _place_mono(out, y * (1.0 if k == 0 else 0.7), k * r.uniform(0.22, 0.3))
    return out, 0.0


def wagon_creak(r, dur=2.0, creaks=3, axle=0.4):
    """a stuck wagon rocking: slow wooden creaks, a squealing axle, a harness jingle"""
    out = np.zeros(ns(dur + 0.6))
    for k in range(creaks):
        tm = (k + r.uniform(0.0, 0.6)) * dur / creaks
        c = _creak(r.uniform(0.35, 0.6), r, r.uniform(35, 60), r.uniform(80, 140), WOOD, rough=0.22, scale=r.uniform(0.6, 0.85))
        _place_mono(out, c * r.uniform(0.6, 1.0), tm)
        if axle and r.uniform() < 0.6:
            a = _creak(r.uniform(0.2, 0.35), r, r.uniform(300, 420), r.uniform(450, 600), SMALLMETAL, rough=0.06, noise=0.01)
            _place_mono(out, a * axle * 0.5, tm + 0.1)
    jing = G.rattle(dur, r, 6, None, heavy=False) * 0.15
    out[: len(jing)] += jing
    return out, 0.0


# ================================================================ jackscrews
def screw_ratchet(r, dur=0.47, clicks=6, scale=1.0, groan=0.6):
    """one man gives one iron jackscrew a quarter turn: the bar's pawl clicks round, the thread groans under load"""
    n = ns(dur + 0.25)
    y = np.zeros(n)
    times = np.sort(np.clip(np.linspace(0.02, dur - 0.04, clicks) + r.normal(0, 0.008, clicks), 0, dur))
    for i, tm in enumerate(times):
        c = modal(0.09, [(f * scale * r.uniform(0.97, 1.03), a, tau) for f, a, tau in
                         [(1650, 1.0, 0.012), (2900, 0.6, 0.008), (4400, 0.35, 0.005), (820, 0.4, 0.018)]], r)
        c += hp(r.standard_normal(len(c)), 2500) * np.exp(-tt(0.09) / 0.0008) * 0.5
        _place_mono(y, c * r.uniform(0.6, 1.0) * (1.15 if i == len(times) - 1 else 1.0), tm)
    g = _creak(dur, r, 26 * scale, 48 * scale, IRON, [(0, 0), (0.2, 1), (0.8, 0.9), (1, 0)], rough=0.18, noise=0.03, scale=scale * 0.7)
    _place_mono(y, g * groan * 0.6, 0.0)
    thunk = np.exp(-tt(0.2) / 0.03) * np.sin(phase(r.uniform(70, 95) * np.ones(ns(0.2)))) * 0.5
    _place_mono(y, thunk, dur - 0.02)
    return y


def screw_turn(r, dur=0.47, screws=48, spread_ms=7.0, close=0.0, beam=0.8):
    """hundreds of men turning their screws a quarter turn in unison: ~screws audible ratchets, each slightly detuned
    and a few ms apart, panned across the room and fading by row; optional one close screw; the beam groans as it lifts"""
    n = ns(dur + 1.4)
    out = np.zeros((2, n))
    for i in range(screws):
        row = i // 8
        g = r.uniform(0.5, 1.0) * 10 ** (-0.5 * row / 20)
        dt = 0.03 + abs(r.normal(0, spread_ms / 1000))
        y = screw_ratchet(r, dur * r.uniform(0.95, 1.05), clicks=6, scale=r.uniform(0.88, 1.12), groan=0.4)
        y = lp(y, 9000 - 900 * row, 1)
        place(out, pan(y * g, r.uniform(-0.9, 0.9)), dt)
    if close:
        place(out, pan(screw_ratchet(r, dur, 6, 1.0, 0.9) * close * 2.2, 0.15), 0.03)
    if beam:
        b = _creak(dur + 0.6, r, 18, 34, TIMBER, [(0, 0), (0.15, 1), (0.6, 0.7), (1, 0)], rough=0.25, noise=0.05, scale=0.8)
        place(out, widen(b * beam * 1.6, r, 12, 0.7), 0.06)
        th = np.exp(-tt(0.5) / 0.09) * np.sin(phase(np.full(ns(0.5), 48.0))) * beam
        place(out, st(th), dur + 0.04)
        dust = G.rattle(0.8, r, 30, np.exp(-np.linspace(0, 1, ns(0.8)) * 3), heavy=False) * 0.08 * beam
        place(out, widen(lp(dust, 5000), r, 9, 1.0), dur + 0.05)
    return out, 0.03


def screw_crew(r, dur=4.0, men=8, period=1.6, spread=0.25, beam=0.4):
    """a crew working screws at their own pace (not in unison): a scattered texture of ratchets and groans"""
    out = np.zeros((2, ns(dur + 1.0)))
    for m in range(men):
        tm = r.uniform(0, period)
        p = r.uniform(-0.9, 0.9)
        g = r.uniform(0.4, 1.0)
        while tm < dur:
            y = screw_ratchet(r, r.uniform(0.35, 0.55), r.integers(4, 7), r.uniform(0.85, 1.15), 0.5)
            place(out, pan(y * g, p), tm)
            tm += period * r.uniform(1 - spread, 1 + spread)
    if beam:
        b = timber_groan(r, dur, 0.6)[0] * beam
        place(out, b, 0.0)
    return out, 0.0


def pea_whistle(r, blasts=((0.0, 0.32), (0.42, 0.55)), f0=None):
    """a foreman's pea whistle: a shrill ~3 kHz tone, the pea rattling it at ~35 Hz, breath on top; sharp blasts"""
    f0 = f0 or r.uniform(2750, 3150)
    end = max(a + d for a, d in blasts) + 0.15
    out = np.zeros(ns(end))
    for a, d in blasts:
        n = ns(d + 0.06)
        t = np.arange(n) / SR
        rate = r.uniform(30, 40) * (1 + 0.15 * smooth_noise(n, r, 6))
        pea = np.sin(phase(rate))
        f = f0 * (1 + 0.03 * pea + 0.015 * np.exp(-t / 0.02) + 0.004 * smooth_noise(n, r, 8))
        ph = phase(f)
        tone = np.sin(ph) + 0.18 * np.sin(2 * ph + 0.7) + 0.05 * np.sin(3 * ph)
        am = 0.65 + 0.35 * (0.5 + 0.5 * pea)
        env = np.clip(t / 0.012, 0, 1) * np.clip((d - t) / 0.03 + 1, 0, 1) * (1 + 0.25 * np.exp(-t / 0.04))
        br = bp(r.standard_normal(n), f0 * 0.6, min(f0 * 2.2, 15000), 1) * 0.12 + hp(r.standard_normal(n), 5000) * 0.04
        _place_mono(out, (tone * am + br) * env, a)
    return out, 0.0


def timber_groan(r, dur=2.4, intensity=1.0, settle=False):
    """a building's timbers groaning as it is jacked up: deep slow stick-slip, a low moan, scattered small creaks,
    optional heavy settle thump at the end"""
    n = ns(dur + 0.8)
    out = np.zeros((2, n))
    g = _creak(dur, r, 14, 30, TIMBER, [(0, 0), (0.12, 1), (0.85, 0.9), (1, 0)], rough=0.3, noise=0.06, scale=0.7) * 1.6
    place(out, widen(g, r, 14, 0.8), 0.0)
    m = ns(dur)
    tm = np.arange(m) / SR
    moan = lp(colored(m, r, 1.8), 140, 2) * np.interp(tm, [0, 0.3, dur - 0.3, dur], [0, 1, 1, 0]) * 0.5
    place(out, st(moan), 0.0)
    k = 0.15
    while k < dur - 0.3:
        c = _creak(r.uniform(0.15, 0.35), r, r.uniform(50, 90), r.uniform(120, 220), WOOD, rough=0.2, scale=r.uniform(0.7, 1.3))
        place(out, pan(c * r.uniform(0.2, 0.55), r.uniform(-0.7, 0.7)), k)
        k += r.exponential(0.35) + 0.12
    if settle:
        th = np.exp(-tt(0.7) / 0.14) * np.sin(phase(52 * (1 + 0.3 * np.exp(-tt(0.7) / 0.02)))) * 1.8
        th += lp(r.standard_normal(ns(0.7)), 600) * np.exp(-tt(0.7) / 0.03) * 0.6
        place(out, st(th), dur - 0.05)
    return out * intensity, 0.0


# ================================================================ digging, pipes, ropes, masons
def shovel(r, scrape=1.0, throw=1.0):
    """one spadeful: steel scraping into earth, the toss, the dirt landing"""
    out = np.zeros(ns(1.1))
    d = r.uniform(0.18, 0.28)
    n = ns(d)
    t = np.arange(n) / SR
    grit = resbank(stick_slip(d, r.uniform(250, 420), r, 0.35), [(f * r.uniform(0.9, 1.1), q, g) for f, q, g in SMALLMETAL]) * 0.5
    sc = (bp(r.standard_normal(n), 1200, 6000, 1) * 0.6 + grit) * np.sin(np.pi * np.clip(t / d, 0, 1)) ** 0.7 * scrape
    _place_mono(out, sc, 0.0)
    tss = G.whoosh(0.3, r, 0.12, 400, 1600, 0.8, 0.1, 0.1) * 0.25 * throw
    _place_mono(out, tss, d + 0.08)
    land = d + r.uniform(0.32, 0.45)
    th = lp(r.standard_normal(ns(0.25)), 300, 2) * np.exp(-tt(0.25) / 0.03) * 1.4
    gr = G.rattle(0.3, r, 120, np.exp(-np.linspace(0, 1, ns(0.3)) * 4), heavy=True) * 0.15
    _place_mono(out, (th + _pad(lp(gr, 4000), ns(0.25))) * throw, land)
    return out


def shoveling(r, dur=3.0, diggers=4, period=1.1, spread=0.8):
    """a gang shoveling: each digger on his own cycle, panned apart"""
    out = np.zeros((2, ns(dur + 1.2)))
    for k in range(diggers):
        tm = r.uniform(0, period)
        p = (k - (diggers - 1) / 2) / max(1, diggers - 1) * spread * 2 if diggers > 1 else 0.0
        while tm < dur:
            place(out, pan(shovel(r, r.uniform(0.6, 1.0), r.uniform(0.6, 1.0)) * r.uniform(0.6, 1.0), p), tm)
            tm += period * r.uniform(0.9, 1.1)
    return out, 0.0


def dirt_dump(r, dur=1.4):
    """a cartload of fill tipped: a long rumble of earth and gravel sliding"""
    n = ns(dur)
    t = np.arange(n) / SR
    env = np.interp(t, [0, 0.15, dur * 0.5, dur], [0, 1, 0.7, 0])
    rum = lp(colored(n, r, 1.5), 250, 2) * env * 1.2
    gr = G.rattle(dur, r, 260, env, heavy=True) * 0.12
    return widen(rum + lp(gr, 5000), r, 10, 0.8), 0.0


def tamp(r, count=3, gap=0.55):
    """a rammer tamping fill: dull earth thuds"""
    out = np.zeros(ns(gap * count + 0.4))
    for k in range(count):
        th = np.exp(-tt(0.3) / 0.05) * np.sin(phase(np.full(ns(0.3), r.uniform(60, 80)))) * 1.2
        th += lp(r.standard_normal(ns(0.3)), 500) * np.exp(-tt(0.3) / 0.015) * 0.7
        _place_mono(out, th * r.uniform(0.8, 1.0), k * gap * r.uniform(0.95, 1.05))
    return out, 0.0


def pipe_land(r, big=1.0):
    """a cast-iron sewer pipe lowered onto the street: chain rattle, heavy thump, the hollow pipe ringing, dirt puff"""
    d = 2.0
    n = ns(d)
    t = np.arange(n) / SR
    thump = np.exp(-t / 0.11) * np.sin(phase(r.uniform(44, 56) * (1 + 0.35 * np.exp(-t / 0.02)))) * 2.2
    f = r.uniform(150, 190)
    ring = modal(d, [(f, 0.7, 0.55), (f * 2.76, 0.6, 0.4), (f * 5.4, 0.35, 0.22), (f * 8.9, 0.2, 0.1), (f * 1.5, 0.25, 0.3)], r)
    clank = modal(0.3, [(r.uniform(700, 1000), 0.8, 0.04), (r.uniform(1700, 2300), 0.5, 0.02)], r)
    y = thump + ring * 0.55
    _place_mono(y, clank, 0.0)
    ch = G.rattle(0.5, r, 60, np.exp(-np.linspace(0, 1, ns(0.5)) * 2), heavy=True) * 0.35
    _place_mono(y, ch, 0.02)
    puff = lp(r.standard_normal(n), 900) * np.exp(-t / 0.08) * 0.3
    return widen(fades((y + puff) * big, 0.0, 0.2), r, 9, 0.6), 0.0


def rope_creak(r, dur=2.0, creaks=4):
    """a tripod and rope taking a hanging pipe's weight: fibrous rope creaks, the timber legs answering"""
    out = np.zeros(ns(dur + 0.6))
    ROPE = [(310, 4, 1.0), (620, 5, 0.8), (1050, 6, 0.5), (1700, 6, 0.3)]
    for k in range(creaks):
        tm = (k + r.uniform(0, 0.5)) * dur / creaks
        c = _creak(r.uniform(0.3, 0.55), r, r.uniform(90, 140), r.uniform(160, 260), ROPE, rough=0.3, noise=0.08, scale=r.uniform(0.85, 1.15))
        _place_mono(out, c * r.uniform(0.6, 1.0), tm)
        if r.uniform() < 0.5:
            w = _creak(r.uniform(0.25, 0.4), r, r.uniform(40, 70), r.uniform(90, 150), WOOD, rough=0.2, scale=r.uniform(0.7, 0.9))
            _place_mono(out, w * 0.5, tm + 0.15)
    return out, 0.0


def trowel(r, taps=3):
    """a mason's steel trowel tapping a brick home (bright tink over a dull brick tock)"""
    out = np.zeros(ns(0.15 * taps + 0.3))
    for k in range(taps):
        tink = modal(0.18, [(r.uniform(2100, 2500), 0.6, 0.03), (r.uniform(4600, 5400), 0.35, 0.015), (r.uniform(7200, 8200), 0.15, 0.006)], r)
        tock = modal(0.18, [(r.uniform(420, 560), 1.0, 0.012), (r.uniform(950, 1250), 0.5, 0.008)], r)
        _place_mono(out, (tink * 0.8 + tock) * (1.0 if k == 0 else 0.7), k * r.uniform(0.12, 0.17))
    return out


def brick_set(r):
    """a brick laid in wet mortar: soft squish, the brick's thock, a scrape of the trowel cutting off the mortar"""
    out = np.zeros(ns(0.9))
    sq = bp(r.standard_normal(ns(0.12)), 300, 2500, 1) * np.exp(-tt(0.12) / 0.03) * 0.5
    sq += G.bubbles(0.12, r, 200, 300, 1200, (0.003, 0.01)) * 0.3
    th = modal(0.2, [(r.uniform(320, 420), 1.0, 0.02), (r.uniform(800, 1000), 0.5, 0.01)], r)
    _place_mono(out, sq, 0.0)
    _place_mono(out, th, 0.004)
    d = 0.22
    scr = bp(r.standard_normal(ns(d)), 1800, 7000, 1) * np.sin(np.pi * np.clip(tt(d) / d, 0, 1)) * 0.35
    _place_mono(out, scr, 0.35)
    return out


def masonry(r, dur=3.0, masons=2, period=1.3):
    """masons building a wall: brick into mortar, trowel taps, mortar scrapes, each mason on his own rhythm"""
    out = np.zeros((2, ns(dur + 1.0)))
    for m in range(masons):
        tm = r.uniform(0, period * 0.6)
        p = -0.4 + 0.8 * m / max(1, masons - 1) if masons > 1 else 0.0
        k = 0
        while tm < dur:
            place(out, pan(brick_set(r) * r.uniform(0.7, 1.0), p), tm)
            place(out, pan(trowel(r, r.integers(2, 4)) * r.uniform(0.6, 0.9), p), tm + 0.5)
            tm += period * r.uniform(0.85, 1.15)
            k += 1
    return out, 0.0


# ================================================================ people, room, objects
def laughs(r, count=5):
    """a few onlookers laughing: 'ha-ha-ha' bursts, falling pitch"""
    out = np.zeros((2, ns(1.6)))
    for v in range(count):
        base = r.uniform(110, 160) if v % 3 else r.uniform(200, 260)
        sc = 1.0 if v % 3 else 1.15
        syl = r.integers(3, 6)
        tm0 = r.uniform(0, 0.35)
        y = np.zeros(ns(1.3))
        for k in range(syl):
            d = r.uniform(0.09, 0.13)
            m = ns(d)
            t = np.arange(m) / SR
            f0 = base * (1.35 - 0.08 * k) * np.interp(t, [0, d], [1.05, 0.92])
            forms = G.vowel_track(m, [(0, "a"), (d, "A")])
            amp = np.clip(t / 0.01, 0, 1) * np.clip((d - t) / 0.04, 0, 1)
            h = G.vox(f0, forms, amp, r, sc, tilt=1.0, breath=0.45) + hp(r.standard_normal(m), 1200) * np.clip(1 - t / 0.02, 0, 1) * 0.4
            _place_mono(y, h * (1 - 0.12 * k), k * r.uniform(0.15, 0.19))
        place(out, pan(lp(y, 4000, 1) * r.uniform(0.4, 1.0), r.uniform(-0.8, 0.8)), tm0)
    return out, 0.0


def coughs(r, count=3, people=2):
    """townsfolk coughing behind their cloths (muffled)"""
    out = np.zeros((2, ns(0.4 * count + 0.8)))
    for p in range(people):
        tm = r.uniform(0, 0.5) + p * 0.6
        pn = r.uniform(-0.6, 0.6)
        base = r.uniform(110, 150) if p % 2 == 0 else r.uniform(190, 240)
        for k in range(count):
            d = r.uniform(0.12, 0.18)
            m = ns(d)
            t = np.arange(m) / SR
            forms = G.vowel_track(m, [(0, "A"), (d, "er")])
            amp = np.clip(t / 0.004, 0, 1) * np.exp(-t / (d * 0.35))
            v = G.vox(base * np.interp(t, [0, d], [1.2, 0.8]), forms, amp, r, 1.0, tilt=1.0, breath=1.6)
            v += bp(r.standard_normal(m), 400, 3000, 1) * amp * 0.6
            place(out, pan(lp(v, 2200, 2) * (1 - 0.2 * k), pn), tm)
            tm += r.uniform(0.22, 0.32)
    return out, 0.0


def flies(r, dur=3.0, n=3):
    """flies buzzing over the gutter: wingbeat buzz with wandering pitch, loudness and pan"""
    m = ns(dur)
    out = np.zeros((2, m))
    t = np.arange(m) / SR
    for k in range(n):
        f0 = r.uniform(170, 230) * (1 + 0.12 * smooth_noise(m, r, 1.5))
        ph = phase(f0)
        saw = sum(np.sin(j * ph) / j for j in range(1, 18))
        y = bp(saw, 200, 4000, 1)
        near = 0.15 + 0.85 * np.clip(0.5 + 0.6 * smooth_noise(m, r, 0.6), 0, 1) ** 2
        p = smooth_noise(m, r, 0.4) * 0.8
        th = (p + 1) * np.pi / 4
        out[0] += y * near * np.cos(th) * np.sqrt(2)
        out[1] += y * near * np.sin(th) * np.sqrt(2)
    return fades(out, 0.3, 0.3), 0.0


def drips(r, dur=3.0, rate=1.5):
    """water dripping into a puddle / a cellar floor"""
    y = G.bubbles(dur, r, rate, 900, 2600, (0.008, 0.02), rise=(8, 22))
    return widen(y, r, 8, 0.9), 0.0


def puddle_splash(r, size=0.6):
    """a small splash in standing water"""
    d = 1.0
    t = tt(d)
    nz = r.standard_normal(len(t))
    slap = bp(nz, 300, 6000, 1) * np.exp(-t / 0.03) * size
    bub = G.bubbles(d, r, 400 * np.exp(-t / 0.2) + 5, 300, 2400, (0.005, 0.02), np.exp(-t / 0.4)) * 0.8
    return widen(slap + bub, r, 8, 0.7), 0.0


def paper_rustle(r, dur=0.9, snap=0.8):
    """a newspaper handled: crinkle crackle, a page turned, the paper shaken flat with a snap"""
    n = ns(dur)
    t = np.arange(n) / SR
    env = np.interp(t, [0, 0.05, dur * 0.7, dur], [0, 1, 0.6, 0])
    cr = np.zeros(n)
    tm = 0.0
    while tm < dur:
        k = ns(tm)
        c = hp(r.standard_normal(ns(0.012)), 2000) * np.exp(-tt(0.012) / 0.0015)
        c = peq(c, r.uniform(3000, 7000), 6, 2)
        _place_mono(cr, c * r.uniform(0.2, 1.0) * env[min(k, n - 1)], tm)
        tm += r.exponential(1 / 160)
    sw = bp(colored(n, r, 0.3), 800, 6000, 1) * env * 0.25
    y = cr * 0.8 + sw
    if snap:
        d = 0.08
        s = bp(r.standard_normal(ns(d)), 300, 4000, 1) * np.exp(-tt(d) / 0.012) * 1.6 * snap
        _place_mono(y, s, dur * 0.72)
    return widen(fades(y, 0.005, 0.05), r, 6, 0.6), 0.0


def teacup_rattle(r, dur=1.4, intensity=1.0):
    """a teacup trembling on its saucer as the hotel rises under it: fine rapid china ticks swelling and fading,
    a faint low rumble from below"""
    n = ns(dur + 0.4)
    y = np.zeros(n)
    t = np.arange(n) / SR
    env = np.interp(t, [0, dur * 0.25, dur * 0.7, dur, dur + 0.1], [0.15, 1.0, 0.8, 0.05, 0])
    tm = 0.0
    f0 = r.uniform(2200, 2600)
    while tm < dur:
        k = ns(tm)
        c = modal(0.08, [(f0 * r.uniform(0.98, 1.02), 1.0, 0.02), (f0 * 1.83, 0.5, 0.012), (f0 * 2.9, 0.3, 0.007), (5200 * r.uniform(0.97, 1.03), 0.4, 0.008)], r)
        _place_mono(y, c * env[min(k, n - 1)] * r.uniform(0.3, 1.0), tm)
        tm += 1 / r.uniform(22, 34)
    rum = lp(colored(n, r, 1.8), 90, 2) * env * 0.6
    spoon = modal(0.4, [(r.uniform(3400, 3800), 1.0, 0.06), (r.uniform(6100, 6700), 0.4, 0.03)], r) * 0.6
    _place_mono(y, spoon, dur * 0.3)
    return fades(y * intensity + rum, 0.01, 0.05), 0.0


def china_clink(r, count=1):
    """a cup set on its saucer / a spoon on china"""
    out = np.zeros(ns(0.25 * count + 0.6))
    for k in range(count):
        f = r.uniform(0.9, 1.15)
        c = modal(0.5, [(fr * f, a, tau) for fr, a, tau in CHINA], r)
        _place_mono(out, c * r.uniform(0.6, 1.0), k * r.uniform(0.15, 0.3))
    return out, 0.0


def cutlery(r, dur=3.0, rate=2.5):
    """knives and forks on plates around a dining room"""
    out = np.zeros((2, ns(dur + 0.5)))
    tm = r.uniform(0, 0.3)
    while tm < dur:
        if r.uniform() < 0.3:
            c = modal(0.4, [(fr * r.uniform(0.85, 1.2), a, tau) for fr, a, tau in CHINA], r) * 0.6
        else:
            c = G.clink(r, r.uniform(2800, 5200), 0.12, 0.7) * 0.5
            c += modal(0.12, [(r.uniform(900, 1400), 0.6, 0.01)], r)
        place(out, pan(c * r.uniform(0.3, 1.0), r.uniform(-0.8, 0.8)), tm)
        tm += r.exponential(1 / rate)
    return out, 0.0


def shop_bell(r, rings=4):
    """a shop door's spring bell jingling"""
    out = np.zeros(ns(1.4))
    f = r.uniform(2300, 2700)
    for k in range(rings):
        y = modal(1.0, [(f, 1.0, 0.35), (f * 2.4, 0.5, 0.18), (f * 3.9, 0.25, 0.08)], r)
        _place_mono(out, y * (0.9 ** k) * r.uniform(0.6, 1.0), k * r.uniform(0.07, 0.11))
    return out, 0.0


def stair_steps(r, steps=6, rate=2.4, creak=0.5):
    """someone climbing rickety temporary wooden stairs: footfalls with a creak on every other tread"""
    out = np.zeros(ns(steps / rate + 0.8))
    for k in range(steps):
        tm = k / rate * r.uniform(0.95, 1.05)
        s = G.stroll_step(r, 0.4) * r.uniform(0.7, 1.0)
        _place_mono(out, s, tm)
        if creak and k % 2 == 0:
            c = _creak(r.uniform(0.18, 0.3), r, r.uniform(70, 110), r.uniform(150, 230), WOOD, rough=0.15, scale=r.uniform(0.9, 1.3))
            _place_mono(out, c * creak, tm + 0.04)
    return out, 0.0


def lamp_light(r, hiss=0.35):
    """a gas lamp lit: the soft 'fwump' of the gas catching, then a quiet steady hiss"""
    d = 1.6
    n = ns(d)
    t = np.arange(n) / SR
    pop = lp(r.standard_normal(n), 700, 2) * np.exp(-t / 0.03) * (1 - np.exp(-t / 0.004)) * 1.2
    pop += np.exp(-t / 0.06) * np.sin(phase(np.full(n, r.uniform(90, 120)))) * 0.6
    hs = bp(r.standard_normal(n), 2500, 9000, 1) * np.interp(t, [0, 0.05, 0.25, d - 0.3, d], [0, 1, 0.45, 0.4, 0]) * hiss
    flick = G.clink(r, r.uniform(3000, 4000), 0.06, 0.6) * 0.2
    y = pop + hs
    _place_mono(y, flick, 0.0)
    return fades(y, 0.002, 0.2), 0.03


def oar_strokes(r, dur=4.0, period=2.4):
    """a small boat rowed slowly: blade dips, drips running off, the oarlock creaking"""
    out = np.zeros((2, ns(dur + 1.5)))
    tm = r.uniform(0.1, 0.4)
    while tm < dur:
        for side in (-0.35, 0.35):
            d = 0.7
            t = tt(d)
            dip = bp(r.standard_normal(len(t)), 300, 3000, 1) * np.exp(-t / 0.06) * (1 - np.exp(-t / 0.01)) * 0.6
            dip += G.bubbles(d, r, 150 * np.exp(-t / 0.2) + 5, 300, 1800, (0.006, 0.02), np.exp(-t / 0.25)) * 0.7
            place(out, pan(dip, side), tm + r.uniform(0, 0.02))
            drip = G.bubbles(0.8, r, 12, 1200, 3000, (0.004, 0.012), np.exp(-tt(0.8) / 0.4), rise=(10, 25)) * 0.5
            place(out, pan(drip, side * 0.8), tm + 0.7)
        c = _creak(0.4, r, 60, 120, WOOD, rough=0.18, scale=r.uniform(1.0, 1.3))
        place(out, pan(c * 0.35, 0.0), tm + 0.3)
        tm += period * r.uniform(0.92, 1.08)
    return out, 0.0


# ================================================================ beds
def bed_street(r, dur=10.0, hooves=0.8, birds=0.4, murmur=0.35, wind=0.8, surface="mud", carts=0.5):
    """an 1850s street by day: wind, sparrows, a distant horse and cart on the mud (or paving), a faint crowd"""
    n = ns(dur)
    x = G.breeze(dur, r, wind, 0.15, 800)
    if birds:
        x = x + pan(G.bird_chirps(dur, r, birds, "sparrow") * 0.07, 0.5)
        x = x + pan(G.bird_chirps(dur, r, birds * 0.6, "sparrow") * 0.04, -0.6)
    if hooves:
        h = hooves_far(r, dur, surface)
        x = x + pan(lp(h, 2500, 1) * 0.35 * hooves, r.uniform(-0.6, 0.6))
    if carts:
        tm = r.uniform(0.5, 3.0)
        while tm < dur - 1.0:
            c = wagon_creak(r, 1.2, 2, 0.2)[0]
            place(x, pan(lp(c, 2000, 1) * 0.12 * carts, r.uniform(-0.7, 0.7)), tm)
            tm += r.uniform(4.0, 7.0)
    if murmur:
        x = x + lp(murmur_far(r, dur), 1800, 1) * murmur
    return fades(x, 0.4, 0.6), 0.0


def hooves_far(r, dur, surface="mud"):
    """a horse passing at a walk somewhere down the street (mono)"""
    return hooves(r, dur, 1.9, surface, "walk")[0][: ns(dur)]


def murmur_far(r, dur, voices=10):
    from cues import murmur
    return murmur(r, dur, voices)[0] * 0.25


def bed_crawl(r, dur=10.0, drips_=1.0, above=0.4):
    """under a building, in the dug-out crawlspace: close dark room tone, slow drips, joist creaks, the street
    muffled overhead"""
    n = ns(dur)
    t = np.arange(n) / SR
    x = np.zeros((2, n))
    for ch in range(2):
        x[ch] = lp(colored(n, r, 1.6), 220, 2) * 0.35 * (0.8 + 0.2 * smooth_noise(n, r, 0.2))
        x[ch] += bp(colored(n, r, 0.8), 300, 1400, 1) * 0.04
    if drips_:
        d = G.bubbles(dur, r, 0.8 * drips_, 1100, 2600, (0.01, 0.025), rise=(6, 18)) * 0.5
        x = x + widen(d, r, 13, 1.0)
    tm = r.uniform(0.5, 2.0)
    while tm < dur - 0.6:
        c = _creak(r.uniform(0.3, 0.6), r, r.uniform(30, 50), r.uniform(60, 100), TIMBER, rough=0.2, scale=r.uniform(0.9, 1.3))
        place(x, pan(lp(c, 1500, 1) * r.uniform(0.04, 0.09), r.uniform(-0.8, 0.8)), tm)
        tm += r.uniform(2.0, 4.5)
    if above:
        h = hooves(r, dur, 1.7, "stone", "walk")[0][:n]
        x = x + st(lp(h, 300, 2) * 0.25 * above)
    return fades(x, 0.4, 0.5), 0.0


def bed_dining(r, dur=6.0, voices=14, clatter=1.0):
    """the Tremont's dining room: warm room tone, guests murmuring, cutlery and china"""
    from cues import murmur
    n = ns(dur)
    x = np.zeros((2, n))
    for ch in range(2):
        x[ch] = lp(colored(n, r, 1.2), 400, 2) * 0.05
    m = murmur(r, dur, voices)[0]
    x = x + lp(m, 3000, 1) * 0.6
    c = cutlery(r, dur, 2.2 * clatter)[0][:, :n] * 0.25
    x = x + c
    return fades(x, 0.3, 0.4), 0.0


def bed_dusk(r, dur=8.0, water=0.7, crickets=1.0):
    """the river at dusk: water lapping at the bank, crickets, a soft breeze, birds settling"""
    x = G.breeze(dur, r, 0.45, 0.08, 600)
    w = G.water_bed(dur, r, 0.45, 0.5)
    x = x + w * 0.35 * water
    x = x + widen(G.crickets(dur, r, 4) * 0.01 * crickets, r, 9, 1.0)
    x = x + pan(G.bird_chirps(dur, r, 0.2, "blackbird") * 0.035, -0.5)
    return fades(x, 0.5, 0.5), 0.0


def bed_under(r, dur=4.0):
    """inside the earth of the buried street: a muffled, close pressure, distant footsteps overhead"""
    n = ns(dur)
    x = np.zeros((2, n))
    for ch in range(2):
        x[ch] = lp(colored(n, r, 1.8), 160, 2) * 0.4
    from cues import footsteps
    f = footsteps(r, dur, 2.0, 0.3, 3, 0.6)[0][:, :n]
    x = x + lp(f, 350, 2) * 0.6
    d = G.bubbles(dur, r, 0.5, 1000, 2200, (0.01, 0.025), rise=(6, 18)) * 0.3
    x = x + widen(d, r, 15, 1.0)
    return fades(x, 0.6, 0.6), 0.0


GENERATORS = dict(
    squelch=lambda r, **a: (squelch(r, **a), 0.0), boot_suck=lambda r, **a: (boot_suck(r, **a), 0.0), mud_step=mud_step,
    hooves=hooves, whinny=whinny, snort=snort, wagon_creak=wagon_creak,
    screw_ratchet=lambda r, **a: (screw_ratchet(r, **a), 0.0), screw_turn=screw_turn, screw_crew=screw_crew,
    pea_whistle=pea_whistle, timber_groan=timber_groan,
    shoveling=shoveling, dirt_dump=dirt_dump, tamp=tamp, pipe_land=pipe_land, rope_creak=rope_creak,
    masonry=masonry, trowel=lambda r, **a: (trowel(r, **a), 0.0), brick_set=lambda r: (brick_set(r), 0.0),
    laughs=laughs, coughs=coughs, flies=flies, drips=drips, puddle_splash=puddle_splash, paper_rustle=paper_rustle,
    teacup_rattle=teacup_rattle, china_clink=china_clink, cutlery=cutlery, shop_bell=shop_bell, stair_steps=stair_steps,
    lamp_light=lamp_light, oar_strokes=oar_strokes,
    bed_street=bed_street, bed_crawl=bed_crawl, bed_dining=bed_dining, bed_dusk=bed_dusk, bed_under=bed_under,
)
