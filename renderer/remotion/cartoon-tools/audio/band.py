# The band: tracks, chord voicings and the playing patterns (oom-pah, snare, rolls, melodies, whistling chorus),
# generalised from the bridge short's music.py (mromidev/claude-animated-shorts, MIT, Copyright (c) 2026 Mr omi).
# Nothing in here knows a video: score.py turns a music spec into calls on these, and render() mixes the tracks
# with their hall / yard sends at a relative balance.
import re
import numpy as np
from dsp import SR, ns, rng, pan, place, fades, dbg, make_ir, convolve_st, integrated, lp, hp
import instruments as I

F = I.m2f

# ---------------------------------------------------------------- chords
NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
        "A#": 10, "Bb": 10, "B": 11}
NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
# voicing intervals from a bass root in octave 1-2 (34..45): after-beat horns ("pah") and a high triad ("hi"),
# matching the bridge's hand voicings (Bb: oom 34/41, pah 53 58 62, hi 58 62 65)
QUAL = {
    "": dict(pah=[19, 24, 28], hi=[24, 28, 31]),
    "m": dict(pah=[19, 24, 27], hi=[24, 27, 31]),
    "7": dict(pah=[10, 16, 19], hi=[16, 19, 22]),
    "m7": dict(pah=[10, 15, 19], hi=[15, 19, 22]),
    "maj7": dict(pah=[19, 23, 28], hi=[23, 28, 31]),
    "o7": dict(pah=[12, 15, 18, 21], hi=[15, 18, 21]),
    "dim": dict(pah=[12, 15, 18, 21], hi=[15, 18, 21]),
    "sus4": dict(pah=[19, 24, 29], hi=[24, 29, 31]),
}
_CH_RE = re.compile(r"^([A-G][#b]?)(.*)$")


def chord(name):
    """'Bb', 'F7', 'Cm', 'F#o7' -> dict(oom=(root, fifth), pah=[...], hi=[...]) in the band's registers"""
    m = _CH_RE.match(name.strip())
    if not m or m.group(2) not in QUAL:
        raise ValueError(f"unknown chord {name!r} (root A-G with #/b, quality one of {sorted(QUAL)})")
    pc, q = NOTE[m.group(1)], m.group(2)
    r = 34 + ((pc - 10) % 12)                       # Bb1 = 34 .. A2 = 45
    fifth = r + 7 if r + 7 <= 46 else r - 5
    if q in ("o7", "dim"):
        fifth = r
    return dict(oom=(r, fifth), pah=[r + i for i in QUAL[q]["pah"]], hi=[r + i for i in QUAL[q]["hi"]])


def transpose_chord(name, semis):
    m = _CH_RE.match(name.strip())
    pc = (NOTE[m.group(1)] + semis) % 12
    return NAMES[pc] + m.group(2)


# ---------------------------------------------------------------- the default tune (the bridge's theme A, in Bb)
# (bar, beat, length in quarters, midi): whistle / fife register. A spec may replace it with its own.
THEME_BB = [
    (1, 0, 1, 82), (1, 1, .75, 82), (1, 1.75, .25, 84), (1, 2, 1, 86), (1, 3, 1, 82),
    (2, 0, 1, 77), (2, 1, .5, 79), (2, 1.5, .5, 81), (2, 2, 1, 82), (2, 3.5, .5, 77),
    (3, 0, .75, 79), (3, .75, .25, 81), (3, 1, .5, 82), (3, 1.5, .5, 79), (3, 2, 1, 87), (3, 3, .5, 86), (3, 3.5, .5, 84),
    (4, 0, 2, 84), (4, 3.5, .5, 77),
    (5, 0, 1, 82), (5, 1, .75, 82), (5, 1.75, .25, 84), (5, 2, 1, 86), (5, 3, 1, 89),
    (6, 0, .5, 87), (6, .5, .5, 86), (6, 1, .5, 84), (6, 1.5, .5, 82), (6, 2, 1, 81), (6, 3, .5, 82), (6, 3.5, .5, 84),
    (7, 0, .75, 86), (7, .75, .25, 84), (7, 1, .5, 82), (7, 1.5, .5, 81), (7, 2, 1, 79), (7, 3, 1, 84),
    (8, 0, 1, 82), (8, 1, .5, 77), (8, 1.5, .5, 74), (8, 2, 1, 70),
]
PICKUP_BB = [(0, 2.5, .5, 74), (0, 3, .5, 75), (0, 3.5, .5, 77)]
CHORDS_BB = {1: ["Bb"] * 4, 2: ["F", "F", "Bb", "Bb"], 3: ["Cm", "Cm", "Eb", "Eb"], 4: ["F7"] * 4, 5: ["Bb"] * 4,
             6: ["Eb", "Eb", "F", "F"], 7: ["Gm", "Gm", "Cm", "F7"], 8: ["Bb"] * 4}


def swingb(b):
    fl = np.floor(b)
    fr_ = b - fl
    return fl + (2 / 3 if fr_ in (0.5, 0.75) else (1 / 3 if fr_ == 0.25 else fr_))


class Band:
    """stereo tracks at N samples, each with a hall send; `cues` is the human-readable music map"""

    def __init__(self, dur, tempo=120.0, theme=None, pickup=None, chords=None, key="Bb", seed=1831):
        self.dur = dur
        self.N = ns(dur)
        self.Q = 60.0 / tempo                       # one quarter note (s)
        self.semis = (NOTE[key] - 10) % 12          # transpose from the Bb tune
        if self.semis > 6:
            self.semis -= 12
        self.theme = theme or THEME_BB
        self.pickup = pickup or PICKUP_BB
        self.chords = chords or CHORDS_BB
        self.bars = max(self.chords) if isinstance(self.chords, dict) else len(self.chords)
        self.tr = {}
        self.send = {}
        self.cues = []
        self.R = rng(seed)

    def r(self):
        return rng(int(self.R.integers(1 << 30)))

    def chords_at(self, bar):
        c = self.chords[bar] if isinstance(self.chords, dict) else self.chords[(bar - 1) % len(self.chords)]
        return [transpose_chord(x, self.semis) for x in c]

    def track(self, name, send=0.15):
        if name not in self.tr:
            self.tr[name] = np.zeros((2, self.N))
            self.send[name] = send
        return self.tr[name]

    def add(self, name, x, t, p=0.0, g=1.0, send=0.15):
        buf = self.track(name, send)
        x = np.asarray(x, float)
        place(buf, pan(x, p) if x.ndim == 1 else x, t, g)

    # ---------------------------------------------------------------- material
    def tune(self, t_bar1, bars=None, transpose=0, pickup=False, swing=False, late=0.0, until=None):
        """theme notes [(t, dur, midi)] with bar 1 at t_bar1, bars cycling through the tune; `until` clips"""
        Q = self.Q
        ev = []
        bars = list(bars) if bars is not None else list(range(1, self.bars + 1))
        src = self.theme + (self.pickup if pickup else [])
        for (b, beat, d, m) in src:
            if b == 0 and not pickup:
                continue
            if b != 0 and b not in bars:
                continue
            bb = swingb(beat) if swing else beat
            t = t_bar1 + (b - 1) * 4 * Q + bb * Q + late
            if until is not None and t >= until - 1e-6:
                continue
            ev.append((t, d * Q, m + transpose + self.semis))
        return sorted(ev)

    def oompah(self, t_bar, chords, vel=0.6, every=True, pah_vel=0.4, bounce=False, pah=True):
        """tuba on the beats (root/fifth alternating) + after-beat horns on the &s; bounce = octave eighths"""
        Q = self.Q
        for beat in range(4):
            c = chord(chords[beat])
            t = t_bar + beat * Q
            if bounce:
                lo = c["oom"][0] if c["oom"][0] >= 36 else c["oom"][0] + 12
                self.add("tuba", I.brass(F(lo), 0.2, vel, self.r(), "tuba", scoop=-30), t, -0.1)
                self.add("tuba", I.brass(F(lo + 12), 0.16, vel * 0.85, self.r(), "tuba", scoop=-45), t + Q / 2, -0.1)
            elif every or beat in (0, 2):
                m = c["oom"][beat % 2] if every else c["oom"][0 if beat == 0 else 1]
                self.add("tuba", I.brass(F(m), 0.3, vel * (1.0 if beat in (0, 2) else 0.88), self.r(), "tuba"), t, -0.1)
            if pah:
                if every:
                    for k, m in enumerate(c["pah"]):
                        self.add("pah", I.brass(F(m), 0.15, pah_vel, self.r(), "horn", scoop=-12), t + Q / 2 + 0.004 * k, 0.32 - 0.12 * k)
                elif beat in (1, 3):
                    for k, m in enumerate(c["pah"]):
                        self.add("pah", I.brass(F(m), 0.17, pah_vel, self.r(), "horn", scoop=-12), t + 0.004 * k, 0.32 - 0.12 * k)

    SN = {
        "light": [1, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 2, 0, 1, 1],
        "march": [3, 0, 1, 1, 2, 0, 1, 0, 3, 0, 1, 1, 2, 0, 1, 0],
        "drive": [2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1],
    }

    def snare_bar(self, t_bar, pat, vel, steps=range(16), cres=0.0):
        Q = self.Q
        for s in steps:
            v = self.SN[pat][s]
            if not v:
                continue
            t = t_bar + s * Q / 4
            vv = vel * (1 + cres * s / 16) * {1: 0.5, 2: 0.9, 3: 0.95}[v] * self.R.uniform(0.93, 1.05)
            if v == 3:
                self.add("snare", I.snare(vv * 0.4, self.r()), t - 0.026, 0.05)
            self.add("snare", I.snare(vv, self.r()), t + self.R.normal(0, 0.002), 0.05)

    def roll(self, t0, t1, v0, v1, accent=None, at=None):
        for t, v in I.snare_roll(t0, t1, v0, v1, self.r()):
            self.add("snare", I.snare(v, self.r(), dur=0.14, buzz=True), t, 0.05)
        if accent:
            at = t1 if at is None else at
            self.add("snare", I.snare(accent * 0.4, self.r()), at - 0.026, 0.05)
            self.add("snare", I.snare(accent, self.r()), at, 0.05)

    def melody(self, name, notes, vel, transpose=0, fn="glock", p=0.0, gate=0.9):
        for (t, d, m) in notes:
            m = m + transpose
            if fn == "glock":
                x = I.glock(F(m), vel * self.R.uniform(0.92, 1.05), self.r())
            elif fn == "fife":
                x = I.fife(F(m), d * gate, vel * self.R.uniform(0.94, 1.04), self.r())
            elif fn == "vibes":
                x = I.vibes(F(m), vel * self.R.uniform(0.92, 1.05), self.r(), dur=max(1.2, d + 0.8), damp=d + 0.35)
            elif fn == "musicbox":
                x = I.musicbox(F(m), vel * self.R.uniform(0.92, 1.05), self.r())
            else:
                raise ValueError(fn)
            self.add(name, x, t, p)

    def chorus(self, name, notes, voices, seed, joins=None, falters=None, spread=0.75, vel=1.0, solo_gain=1.0):
        """several people whistling the same tune: own detune, timing, vibrato, breath and place in the crowd"""
        rr = rng(seed)
        for v in range(voices):
            rv = rng(seed * 101 + v)
            nv = [(t, d, m, vel * rv.uniform(0.85, 1.0)) for (t, d, m) in notes if joins is None or t >= joins[v] - 1e-6]
            if not nv:
                continue
            fal = (falters[v], -rv.uniform(1.2, 3.2)) if falters else None
            t0, y = I.whistle(nv, rv, detune=rv.uniform(-11, 11) if v else 0.0, jit=0.010, lag=rv.uniform(0, 0.022) if v else 0.0,
                              vib_rate=rv.uniform(5.0, 6.6), vib_depth=rv.uniform(10, 22), breath=rv.uniform(0.04, 0.07), falter=fal)
            g = (solo_gain if v == 0 else rv.uniform(0.45, 0.8))
            p = 0.0 if v == 0 else spread * rr.uniform(-1, 1)
            if v:
                y = lp(y, rv.uniform(5000, 9000), 1)
            self.add(name, y, t0, p, g)

    def gate(self, t0, t1, keep=()):
        """silence every track except `keep` from t0 to t1 (a dead stop, a dropout)"""
        a, z = ns(t0), ns(t1)
        for k in self.tr:
            if k in keep:
                continue
            self.tr[k][:, a:z] = 0
            if a > 0:
                self.tr[k][:, max(0, a - ns(0.012)):a] *= np.linspace(1, 0, a - max(0, a - ns(0.012)))[None, :]

    def fade_out(self, t0, power=1.5):
        a = ns(t0)
        if a >= self.N:
            return
        env = np.ones(self.N)
        env[a:] = np.linspace(1, 0, self.N - a) ** power
        for k in self.tr:
            self.tr[k] *= env[None, :]


# relative balance inside the band (LU, measured on each track's own active span)
TARGET = {
    "whistle": 0.0, "fife": -3.0, "glock": -6.0, "tuba": -2.5, "pah": -7.5, "snare": -5.5, "cymbal": -11.0,
    "stab": -3.0, "timpani": -5.0, "turn": -2.5, "drone": -9.0, "creep": -8.0, "pad": -3.5, "vibes": -2.0, "musicbox": -1.5, "pluck": -4.0, "brush": -13.0, "triangle": -15.0,
}


def render(b, ref=-20.0):
    hall = make_ir(1.5, 7, pre=0.018, hf=1.4)
    yard = make_ir(0.9, 8, pre=0.008, hf=1.8, early=[(0.11, 0.5, -0.4), (0.19, 0.35, 0.5)])
    dry = np.zeros((2, b.N))
    wet_hall = np.zeros((2, b.N))
    wet_yard = np.zeros((2, b.N))
    levels = {}
    for k, x in b.tr.items():
        if not np.any(x):
            continue
        L = integrated(x)
        if not np.isfinite(L):
            continue
        g = dbg(ref + TARGET.get(k, -6) - L)
        levels[k] = (round(L, 1), round(ref + TARGET.get(k, -6), 1))
        x = x * g
        b.tr[k] = x
        dry += x
        if k == "whistle":
            wet_yard += 0.16 * x
        else:
            wet_hall += b.send[k] * x
    out = dry + 0.7 * convolve_st(wet_hall.mean(0), hall) + 0.8 * convolve_st(wet_yard.mean(0), yard)
    out = hp(out, 30, 2)
    return out, levels
