# Sound effects and ambience from a CUE SPEC (data the authoring agent writes), rendered into one stereo stem.
# Generalised from the bridge short's sfx.py (mromidev/claude-animated-shorts, MIT, Copyright (c) 2026 Mr omi):
# the level convention, the distance model and the composite generators are theirs; the cue list is data.
#
#   { "cues": [
#       {"t": 0.0, "gen": "bed_day", "args": {"dur": 14.0, "river": 0.6}, "naive": -30, "kind": "bed", "desc": "..."},
#       {"f": 142, "gen": "steam_whistle", "args": {"dur": 1.4}, "naive": -4, "pan": 0.3, "dist": 18, "desc": "..."},
#       ...
#   ] }
# Fields: t (s) or f (frame); gen (a name below); args (that generator's keyword arguments; `dur` in seconds where the
# generator takes one); naive = the event's loudness in LU relative to the voice stem (max momentary for events,
# integrated for beds); kind "event" (placed at exactly its naive level; the mixer ducks the music under it) or "bed" (not reduced);
# pan -1..1; dist = metres from the lens (adds gain loss, a low-pass and more reverb); extra dB; lpf Hz; send 0..1
# (valley reverb); group; desc; cut (s: hard end); fade [in, out] seconds.
import math
import numpy as np
from dsp import (SR, ns, tt, rng, dbg, lp, hp, bp, peq, shelf, pan, st, place, fades, widen, make_ir, convolve_st,
                 momentary_max, integrated, colored, smooth_noise, modal)
import sfx_gen as G
import instruments as I

SFX_DB = 0.0    # an event sits where the spec puts it: the bridge short's -6 dB "standard rule" buried every effect under the band
FPS = 30


def dist_fx(d):
    """distance (m) -> (gain dB, low-pass Hz, reverb send), the bridge's camera-distance model"""
    d = max(d, 3.5)
    g = -14.0 * math.log10(d / 3.5)
    lpf = float(np.clip(17000 * (3.5 / d) ** 0.55, 1800, 17000))
    send = 0.06 + 0.45 * float(np.clip(math.log(d / 3.5) / math.log(25), 0, 1))
    return g, lpf, send


def _mono(x):
    x = np.asarray(x, float)
    return x.mean(0) if x.ndim == 2 else x


# ---------------------------------------------------------------- composite generators (return (signal, anchor))
def bed_day(r, dur=10.0, river=0.5, flags=0.25, birds=0.45, wind=1.0):
    n = ns(dur)
    x = G.breeze(dur, r, wind, 0.15, 850)
    if river:
        rv = bp(colored(n, r, 0.8), 180, 1800, 1) * river * (0.8 + 0.2 * smooth_noise(n, r, 0.3))
        x = x + st(rv)
    if birds:
        x = x + pan(G.bird_chirps(dur, r, birds, "sparrow") * 0.08, 0.5)
        x = x + pan(G.bird_chirps(dur, r, birds * 0.66, "sparrow") * 0.05, -0.6)
    if flags:
        x = x + pan(G.flag_flutter(dur, r) * flags, 0.3)
    return fades(x, 0.4, 0.6), 0.0


def bed_golden(r, dur=10.0, crickets=1.0, birds=1.0):
    n = ns(dur)
    x = G.breeze(dur, r, 0.7, 0.1, 650)
    x = x + st(lp(bp(colored(n, r, 0.8), 150, 1400, 1), 1200) * 0.35)
    if birds:
        x = x + pan(G.bird_chirps(dur, r, 0.35 * birds, "blackbird") * 0.06, -0.5)
        x = x + pan(G.bird_chirps(dur, r, 0.25 * birds, "blackbird") * 0.04, 0.6)
    if crickets:
        x = x + widen(G.crickets(dur, r, 3) * 0.008 * crickets, r, 9, 1.0)
    return fades(x, 0.5, 0.4), 0.0


def bed_night(r, dur=10.0, crickets=1.5, wind=0.4):
    n = ns(dur)
    x = G.breeze(dur, r, wind, 0.08, 500)
    x = x + widen(G.crickets(dur, r, 4) * 0.012 * crickets, r, 9, 1.0)
    x = x + st(lp(colored(n, r, 1.2), 300) * 0.05)
    return fades(x, 0.6, 0.6), 0.0


def bed_water(r, dur=10.0, close=1.0, slosh=0.9):
    return fades(G.water_bed(dur, r, close, slosh), 0.35, 0.3), 0.0


def bed_town(r, dur=10.0, voices=14, wind=0.45):
    x = murmur(r, dur, voices)[0]
    x = x + bed_day(r, dur, 0.3, 0.3, 0.3, wind)[0] * 0.7
    return fades(x, 0.3, 0.4), 0.0


def murmur(r, dur=6.0, voices=22, early=False):
    n = ns(dur)
    out = np.zeros((2, n))
    for v in range(voices):
        kind = r.uniform()
        base, scale = ((r.uniform(95, 140), r.uniform(0.95, 1.05)) if kind < 0.45 else
                       (r.uniform(175, 235), r.uniform(1.12, 1.2)) if kind < 0.85 else (r.uniform(260, 330), r.uniform(1.25, 1.35)))
        y = G.babble(dur, r, base, scale, r.uniform(3.6, 4.8), r.uniform(0.55, 0.8), fmax=3400)
        y = lp(y, r.uniform(2200, 3600), 1) * r.uniform(0.3, 1.0)
        out += pan(y, r.uniform(-0.85, 0.85))
    if early:
        for k in range(4):
            h = G.hurrah(r, r.uniform(110, 230), r.uniform(1.0, 1.18))
            place(out, pan(lp(h, 3000, 1) * 0.5, r.uniform(-0.8, 0.8)), r.uniform(0.2, 1.6))
    return fades(out, 0.25, 0.8), 0.0


def cheer(r, dur=3.4, people=26, applause=0.9):
    n = ns(dur)
    t = np.arange(n) / SR
    out = np.zeros((2, n))
    for v in range(people):
        kid = v % 6 == 5
        base = r.uniform(270, 340) if kid else (r.uniform(105, 160) if v % 2 else r.uniform(180, 250))
        scale = 1.3 if kid else (1.0 if v % 2 else 1.15)
        for rep in range(1 + int(r.uniform() < 0.4)):
            h = G.hurrah(r, base * r.uniform(0.97, 1.05), scale, kid)
            tm = r.uniform(0.25, 1.1) + rep * r.uniform(0.75, 1.0)
            place(out, pan(lp(h, 4000, 1) * r.uniform(0.35, 1.0), r.uniform(-0.9, 0.9)), min(tm, max(0.0, dur - 0.6)))
    env = np.interp(t, [0, 0.4, 1.0, dur * 0.56, dur], [0.0, 0.5, 1.0, 0.75, 0.0])
    out += G.applause(dur, r, 40, env) * applause
    return fades(out, 0.05, 0.5), 0.0


def splashes(r, count=6):
    out = np.zeros((2, ns(2.8)))
    pat = [(0.0, 1.0, 0.0), (-0.55, 0.75, 0.025), (0.5, 0.7, 0.04), (-0.3, 0.55, 0.06), (0.35, 0.5, 0.075), (0.75, 0.35, 0.09)]
    for k, (p, g, dt) in enumerate(pat[:count]):
        s = G.splash_big(r)
        if k:
            s = lp(s, 9000, 1)
        place(out, pan(s * g, p), dt)
    return out, 0.0


def oofs(r, count=12):
    out = np.zeros((2, ns(0.9)))
    kinds = ["oof", "oof", "ugh", "oh", "oof", "ow", "ugh", "oof", "oh", "oof", "ugh", "ow"]
    for v, k in enumerate(kinds[:count]):
        o = G.oof(r, k)
        tm = abs(r.normal(0.06, 0.08)) + (0.0 if v < 5 else 0.1)
        place(out, pan(o * r.uniform(0.45, 1.0), r.uniform(-0.85, 0.85)), min(tm, 0.45))
    return out, 0.0


def whoas(r, count=9):
    out = np.zeros((2, ns(0.75)))
    for v in range(count):
        w = G.whoa(r, dur=r.uniform(0.35, 0.5))
        place(out, pan(w * r.uniform(0.4, 1.0), r.uniform(-0.8, 0.8)), r.uniform(0.0, 0.18))
    return out, 0.0


def debris(r, count=7):
    out = np.zeros((2, ns(1.2)))
    for k in range(count):
        knock = modal(0.3, [(r.uniform(180, 320), 1.0, 0.04), (r.uniform(450, 900), 0.6, 0.02), (r.uniform(1200, 2400), 0.3, 0.01)], r)
        sp = G.bubbles(0.3, r, 120, 400, 2200, (0.005, 0.02), np.exp(-tt(0.3) / 0.08)) * 0.5
        place(out, pan((knock + sp) * r.uniform(0.3, 1.0), r.uniform(-0.8, 0.8)), r.uniform(0, 0.8))
    return out, 0.0


def flash(r, dur=0.75):
    y = G.whoosh(dur, r, 0.33, 500, 4200, 0.9, 0.09, 0.4)
    t = tt(dur)
    boom = np.where(t > 0.33, np.exp(-(t - 0.33) / 0.12) * np.sin(2 * np.pi * 62 * (t - 0.33)), 0) * 0.8
    return widen(y + boom, r, 12, 0.9), 0.33


def scuffle(r, count=18):
    y = np.zeros((2, ns(0.6)))
    for k in range(count):
        s = G.stroll_step(r, r.uniform(0.6, 1.2)) * r.uniform(0.3, 1.0)
        place(y, pan(s, r.uniform(-0.6, 0.6)), r.uniform(0, 0.3))
    return y, 0.0


def bounces(r):
    y = np.zeros(ns(0.6))
    for k, (tm, a) in enumerate([(0.0, 1.0), (0.11, 0.45), (0.19, 0.25), (0.24, 0.12)]):
        c = G.clink(r, r.uniform(2600, 3400), 0.12) * a
        y[ns(tm): ns(tm) + len(c)] += c[: len(y) - ns(tm)]
    return y, 0.0


def groans(r, parts=None):
    parts = parts or [[0.0, "ugh", 1.0], [0.09, "ow", 0.7], [0.2, "ugh", 0.5]]
    out = np.zeros((2, ns(0.9)))
    for tm, kd, g in parts:
        o = G.oof(r, kd, base=r.uniform(90, 125), scale=r.uniform(0.95, 1.05))
        place(out, pan(o * g, r.uniform(-0.6, 0.6)), tm)
    return out, 0.0


def footsteps(r, dur=3.0, rate=2.0, scuff=0.5, people=1, pan_width=0.3):
    """one or more people walking: alternating steps at `rate` per second, each stroller on its own phase"""
    out = np.zeros((2, ns(dur + 0.4)))
    for p in range(people):
        ph = r.uniform(0, 1 / rate) if people > 1 else 0.0
        pp = r.uniform(-pan_width, pan_width) if people > 1 else 0.0
        t = ph
        k = 0
        while t < dur:
            s = G.stroll_step(r, scuff * r.uniform(0.7, 1.3)) * r.uniform(0.7, 1.0)
            place(out, pan(s, pp + (0.08 if k % 2 else -0.08)), t)
            t += (1 / rate) * r.uniform(0.95, 1.05)
            k += 1
    return out, 0.0


def steam_whistle(r, dur=1.2, notes=(58, 62, 65), hoarse=0.5):
    """a riverboat / locomotive steam whistle: a hoarse chord with a breathy chuff at the start and a droop at the end"""
    n = ns(dur + 0.4)
    out = np.zeros(n)
    for k, m in enumerate(notes):
        f = I.m2f(m) * (1 + 0.004 * k)
        y = I.brass(f, dur, 0.9, r, "soft", scoop=-35, fall=-25, rel=0.25)
        out[: len(y)] += y[:n] * (1.0 / len(notes))
    chuff = _mono(G.breeze(min(dur, 0.6), r, 1.4, 0.05, 2400)) * np.exp(-tt(min(dur, 0.6)) / 0.18) * hoarse
    out[: len(chuff)] += chuff
    hiss = bp(colored(n, r, 0.5), 1500, 6000, 1) * 0.08 * hoarse * np.interp(tt(n / SR), [0, 0.05, dur, dur + 0.3], [0, 1, 1, 0])
    out += hiss
    return widen(out, r, 8, 0.6), 0.0


def bell(r, f=660.0, strikes=1, gap=0.9, dur=2.5):
    """a cast bell: inharmonic partials, long ring; `strikes` repeated hits `gap` seconds apart"""
    out = np.zeros(ns(dur + gap * strikes))
    for k in range(strikes):
        y = modal(dur, [(f, 1.0, 0.6), (f * 2.0, 0.6, 0.45), (f * 2.4, 0.45, 0.4), (f * 2.7, 0.25, 0.3), (f * 4.1, 0.15, 0.2), (f * 0.5, 0.3, 0.8)], r)
        y = y * (1.0 if k == 0 else r.uniform(0.85, 1.0))
        a = ns(k * gap)
        out[a: a + len(y)] += y[: len(out) - a]
    return out, 0.0


def paddle_churn(r, dur=4.0, rpm=18.0, close=0.8):
    """a sidewheel paddle churning: the water bed plus a slap and froth on every blade entry"""
    out = st(G.water_bed(dur, r, close, 1.2)) * 0.7
    blades = 8
    period = 60.0 / (rpm * blades)
    t = r.uniform(0, period)
    while t < dur:
        s = lp(G.splash_big(r), 2500, 1) * r.uniform(0.25, 0.45) * close
        froth = G.bubbles(0.35, r, 200, 500, 2500, (0.004, 0.02), np.exp(-tt(0.35) / 0.12)) * 0.4
        place(out, pan(s, r.uniform(-0.2, 0.2)), t)
        place(out, pan(froth, r.uniform(-0.3, 0.3)), t + 0.04)
        t += period * r.uniform(0.96, 1.04)
    return fades(out, 0.2, 0.3), 0.0


def engine_chuff(r, dur=4.0, rate=1.6, depth=1.0):
    """a steam engine's exhaust beat: low chuffs at `rate` per second"""
    out = np.zeros(ns(dur + 0.3))
    t = 0.0
    while t < dur:
        d = 0.22
        y = _mono(G.breeze(d, r, 2.0, 0.05, 900)) * np.exp(-tt(d) / 0.06) * depth
        thump = np.sin(2 * np.pi * 55 * tt(d)) * np.exp(-tt(d) / 0.05) * 0.6 * depth
        a = ns(t)
        yy = (y + thump)[: len(out) - a]
        out[a: a + len(yy)] += yy
        t += (1 / rate) * r.uniform(0.98, 1.02)
    return lp(out, 1800, 1), 0.0


def telegraph_key(r, dur=1.6, wpm=18):
    """a morse key clicking: dot/dash pattern, wooden knock under the brass contact tick"""
    unit = 1.2 / wpm
    out = np.zeros(ns(dur + 0.2))
    t = 0.0
    while t < dur:
        dash = r.uniform() < 0.35
        hold = unit * (3 if dash else 1)
        for tm, g in ((t, 1.0), (t + hold, 0.7)):
            tick = G.clink(r, r.uniform(3200, 4200), 0.05, 0.8) * 0.35 * g
            knock = modal(0.08, [(r.uniform(900, 1300), 1.0, 0.012), (r.uniform(2200, 3000), 0.5, 0.008)], r) * 0.5 * g
            a = ns(tm)
            y = (tick + np.pad(knock, (0, max(0, len(tick) - len(knock))))[: len(tick)])[: len(out) - a]
            out[a: a + len(y)] += y
        t += hold + unit * (3 if r.uniform() < 0.2 else 1)
    return out, 0.0


def crowd_cheer(r, dur=3.4, people=26, applause=0.9):
    return cheer(r, dur, people, applause)


def whoosh(r, dur=0.6, peak=0.09, f_lo=330, f_hi=2000, width=0.8, tail=0.18, air=0.15):
    return G.whoosh(dur, r, peak, f_lo, f_hi, width, tail, air), peak


def creak(r, dur=0.55, rate0=60, rate1=140, rough=0.2, scale=1.0):
    return G.creak(dur, r, rate0, rate1, G.TIMBER, rough=rough, scale=scale), 0.0


# every generator the spec may name: composites above, then sfx_gen's own (which take `r` first via a wrapper)
COMPOSITES = {k: v for k, v in dict(
    bed_day=bed_day, bed_golden=bed_golden, bed_night=bed_night, bed_water=bed_water, bed_town=bed_town, murmur=murmur, cheer=cheer,
    crowd_cheer=crowd_cheer, splashes=splashes, oofs=oofs, whoas=whoas, debris=debris, flash=flash, scuffle=scuffle, bounces=bounces,
    groans=groans, footsteps=footsteps, steam_whistle=steam_whistle, bell=bell, paddle_churn=paddle_churn, engine_chuff=engine_chuff,
    telegraph_key=telegraph_key, whoosh=whoosh, creak=creak,
).items()}
# sfx_gen functions usable directly: name -> (callable, takes dur first?)
RAW = {
    "clink": (lambda r, **a: (G.clink(r, **a), 0.0)),
    "rattle": (lambda r, dur=1.0, **a: (G.rattle(dur, r, **a), 0.0)),
    "boot": (lambda r, **a: (G.boot(r, **a), 0.0)),
    "column_stomp": (lambda r, **a: G.column_stomp(r, **a)),
    "deck_flex": (lambda r, a=0.8: (G.deck_flex(r, a), 0.0)),
    "chain_groan": (lambda r, dur=2.0, **a: (G.chain_groan(dur, r, **a), 0.0)),
    "bolt_snap": (lambda r: (G.bolt_snap(r), 0.0)),
    "chain_whip": (lambda r: (G.chain_whip(r), 0.0)),
    "timber_tear": (lambda r, **a: (G.timber_tear(r, **a), 0.0)),
    "wood_crack": (lambda r: (G.wood_crack(r), 0.0)),
    "splash_big": (lambda r: (G.splash_big(r), 0.0)),
    "water_bed": (lambda r, dur=4.0, **a: (G.water_bed(dur, r, **a), 0.0)),
    "oof": (lambda r, **a: (G.oof(r, **a), 0.0)),
    "whoa": (lambda r, **a: (G.whoa(r, **a), 0.0)),
    "hurrah": (lambda r, base=160.0, scale=1.1, kid=False: (G.hurrah(r, base, scale, kid), 0.0)),
    "applause": (lambda r, dur=3.0, people=36: (G.applause(dur, r, people), 0.0)),
    "bird_chirps": (lambda r, dur=4.0, **a: (G.bird_chirps(dur, r, **a), 0.0)),
    "crickets": (lambda r, dur=4.0, **a: (G.crickets(dur, r, **a), 0.0)),
    "breeze": (lambda r, dur=4.0, **a: (G.breeze(dur, r, **a), 0.0)),
    "flag_flutter": (lambda r, dur=4.0: (G.flag_flutter(dur, r), 0.0)),
    "hammer_hit": (lambda r, **a: (G.hammer_hit(r, **a), 0.0)),
    "stroll_step": (lambda r, **a: (G.stroll_step(r, **a), 0.0)),
    "push_thump": (lambda r: (G.push_thump(r), 0.0)),
    "swing_squeak": (lambda r, **a: (G.swing_squeak(r, **a), 0.12)),
}
GENERATORS = {**COMPOSITES, **RAW}
# the Chicago short's own generators (sfx_chicago.py)
import sfx_chicago  # noqa: E402
GENERATORS.update(sfx_chicago.GENERATORS)


class Cue:
    def __init__(self, t, name, desc, gen, naive, kind="event", p=0.0, extra=0.0, lpf=None, send=0.12, group=None, cut=None, fade=None):
        self.t, self.name, self.desc, self.gen, self.naive = t, name, desc, gen, naive
        self.kind, self.p, self.extra, self.lpf, self.send, self.cut, self.fade = kind, p, extra, lpf, send, cut, fade
        self.group = group or name
        self.applied = naive + (SFX_DB if kind == "event" else 0.0) + extra
        self.measured = None
        self.music = self.over = None      # set by the mixer: the music at the event's moment, and the event over it


def from_spec(spec, dur, fps=FPS):
    """the spec's cue list -> [Cue]; every generator gets its own deterministic rng from the cue's index"""
    C = []
    R = rng(int(spec.get("seed", 1870)))
    for i, c in enumerate(spec.get("cues", [])):
        name = c["gen"]
        if name not in GENERATORS:
            raise ValueError(f"cue {i}: unknown generator {name!r}; one of {sorted(GENERATORS)}")
        t = float(c["t"]) if "t" in c else float(c["f"]) / fps
        if t >= dur:
            continue
        args = dict(c.get("args", {}))
        seed = int(R.integers(1 << 30))
        fn = GENERATORS[name]

        def gen(fn=fn, args=args, seed=seed):
            return fn(rng(seed), **args)
        kind = c.get("kind", "event")
        extra = float(c.get("extra", 0.0))
        lpf = c.get("lpf")
        send = float(c.get("send", 0.12 if kind == "event" else 0.0))
        if c.get("dist") is not None:
            g, dl, ds = dist_fx(float(c["dist"]))
            extra += max(g, -13.0)
            lpf = min(lpf, dl) if lpf else dl
            send = max(send, ds)
        C.append(Cue(t, c.get("name", name), c.get("desc", name), gen, float(c.get("naive", -10)), kind, float(c.get("pan", 0.0)), extra,
                     lpf, send, c.get("group"), c.get("cut"), c.get("fade")))
    return C


def render(C, dur, v_ref, on_event=None):
    """v_ref = integrated loudness of the voice stem (stereo). Returns (stereo stem, cues with measured levels)."""
    N = ns(dur)
    out = np.zeros((2, N))
    send = np.zeros(N)
    for c in C:
        x, anchor = c.gen()
        x = np.asarray(x, float)
        x = pan(x, c.p) if x.ndim == 1 else x
        if c.fade:
            x = fades(x, float(c.fade[0]), float(c.fade[1]))
        if c.cut is not None:
            k = ns(float(c.cut) - (c.t - anchor))
            if 0 < k < x.shape[1]:
                x = fades(x[:, :k], 0.0, 0.02)
        tgt = v_ref + c.applied
        cur = momentary_max(x) if c.kind == "event" else integrated(x)
        if np.isfinite(cur):
            x = x * dbg(tgt - cur)
        if c.lpf:
            x = lp(x, c.lpf, 1)
        c.measured = (momentary_max(x) if c.kind == "event" else integrated(x)) - v_ref
        t0 = c.t - anchor
        place(out, x, t0)
        if on_event:
            on_event(c, x, t0)
        if c.send > 0:
            G._place_mono(send, c.send * x.mean(0), t0)
    valley = make_ir(1.1, 77, pre=0.01, hf=1.6, early=[(0.09, 0.45, -0.5), (0.14, 0.3, 0.6), (0.23, 0.2, -0.2)])
    out += 0.55 * convolve_st(send, valley)
    out = hp(out, 25, 2)
    end = ns(dur - 0.12)
    out[:, end:] *= np.linspace(1, 0, N - end)[None, :] ** 2
    return out, C
