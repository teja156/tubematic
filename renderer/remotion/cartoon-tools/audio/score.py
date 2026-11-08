# A score from a MUSIC SPEC (data the authoring agent writes), played by band.py. The styles are the bridge short's
# sections generalised: each one is a way of playing the tune over the chord cycle between two times.
#
#   {
#     "tempo": 120, "key": "Bb", "seed": 1870,
#     "theme": [[bar, beat, lenQuarters, midi], ...],        optional: own tune in Bb (bar 1..n); default = the kit tune
#     "chords": {"1": ["Bb","Bb","Bb","Bb"], "2": [...]},    optional: chords per bar in Bb (transposed with the key)
#     "sections": [ {"name": "hook", "start": 0.0, "end": 4.3, "style": "tutti", "level": -9.5}, ... ],
#     "hits": [12.4, 13.1],                                   optional: brass stab + timpani on these times
#     "dips": [[3.65, 4.30, -3.0]],                           optional: music rides (start, end, dB) for sentence ends
#     "end_fade": 0.4                                         optional: seconds of fade before the end
#   }
# Styles: tutti, march, light, vamp, whistle, tension, silence, sway, waltz, soft, swing, pad, stabs, creep.
# Hits: a time (brass stab + timpani, rolled into) or {"t": s, "kind": k, ...} with kind one of
#   stab (default), button (dry tutti chord + clash, no roll), rise (stab, a brass/glock climb over "dur", a stab on
#   top), turn (a low dry timpani/brass knock; "step" semitones up), reveal (soft timpani, vibes chord, cymbal
#   swell), chime (the final chord: vibes, glock, soft brass, rings).
# Chicago additions: the creep style, hit kinds, silence sections gated to true silence.
# `level` is the section's music loudness in LU relative to the voice (after ducking); default -10.
import numpy as np
from dsp import ns, rng
import instruments as I
from band import Band, chord, render, F

STYLES = ("tutti", "march", "light", "vamp", "whistle", "tension", "silence", "sway", "waltz", "soft", "swing", "pad", "stabs", "creep")


def _bars(b, t0, t1):
    """(bar index 1.., bar start time) for every bar that starts inside [t0, t1)"""
    bar = 4 * b.Q
    k, t = 1, t0
    while t < t1 - 1e-6:
        yield ((k - 1) % b.bars) + 1, t
        k += 1
        t += bar


def _section(b, name, t0, t1, style, idx):
    Q = b.Q
    bar = 4 * Q
    nbars = max(1, int(round((t1 - t0) / bar)))
    bars_in = [((k) % b.bars) + 1 for k in range(nbars)]
    if style == "silence":
        b.cues.append((t0, f"{name}: silence"))
        return
    if style in ("tutti", "march", "light", "soft", "vamp"):
        notes = b.tune(t0, bars=None, until=t1)
        # the tune cycles bar by bar from the section start
        notes = []
        for k, (bi, tb) in enumerate(_bars(b, t0, t1)):
            notes += b.tune(tb - (bi - 1) * bar, bars=[bi], until=t1)
        if style == "tutti":
            b.chorus("whistle", notes, 7, 11 + idx)
            b.melody("glock", notes, 0.5, 12, "glock", -0.35)
            b.add("cymbal", I.cymbal(0.45, b.r()), t0, 0.0)
        elif style == "march":
            b.melody("glock", notes, 0.5, 12, "glock", -0.35)
            b.melody("fife", notes, 0.58, 0, "fife", 0.25)
            b.add("cymbal", I.cymbal(0.42, b.r()), t0, 0.0)
        elif style == "light":
            b.melody("glock", notes, 0.36, 12, "glock", -0.35)
            b.melody("fife", notes, 0.42, 0, "fife", 0.25)
        elif style == "soft":
            b.chorus("whistle", notes, 6, 54 + idx, spread=0.7, vel=0.8, solo_gain=0.8)
            b.melody("glock", notes, 0.32, 12, "glock", -0.35)
            b.add("cymbal", I.cymbal(0.22, b.r()), t0, 0.0)
        for bi, tb in _bars(b, t0, t1):
            ch = b.chords_at(bi)
            last = tb + bar > t1 - 1e-6
            steps = range(16) if not last else range(12)
            if style == "tutti":
                b.oompah(tb, ch, 0.68, True, 0.42)
                b.snare_bar(tb, "march", 0.62, steps=steps)
            elif style == "march":
                b.oompah(tb, ch, 0.64, True, 0.44)
                b.snare_bar(tb, "march", 0.58, steps=steps)
            elif style == "light":
                b.oompah(tb, ch, 0.5, False, 0.34)
                b.snare_bar(tb, "light", 0.36, steps=steps)
            elif style == "soft":
                b.oompah(tb, ch, 0.48, False, 0.32)
                b.snare_bar(tb, "light", 0.32, steps=steps)
            elif style == "vamp":
                b.oompah(tb, ch, 0.58, True, 0.38)
                b.snare_bar(tb, "light", 0.45, steps=steps)
        b.cues.append((t0, f"{name}: {style} ({nbars} bars of the tune)"))
        return
    if style == "whistle":
        notes = []
        for k, (bi, tb) in enumerate(_bars(b, t0, t1)):
            notes += b.tune(tb - (bi - 1) * bar, bars=[bi], until=t1)
        joins = [0.0] + list(np.linspace(t0 + 0.75, t0 + 1.75, 8))
        b.chorus("whistle", notes, 9, 22 + idx, joins=joins, spread=0.8, solo_gain=1.05)
        b.add("cymbal", I.cymbal(0.3, b.r()), t0, 0.0)
        for j, (bi, tb) in enumerate(_bars(b, t0, t1)):
            b.oompah(tb, b.chords_at(bi), 0.6 + 0.02 * j, True, 0.4 + 0.02 * j)
            b.snare_bar(tb, "march", 0.52 + 0.03 * j)
        b.cues.append((t0, f"{name}: one whistler, then the crowd joins"))
        return
    if style == "tension":
        # dominant pedal, chromatic climb over the last two bars, snare drive and roll, dead stop at the end
        dom = b.chords_at(4)[0]
        for j, (bi, tb) in enumerate(_bars(b, t0, t1)):
            b.oompah(tb, [dom] * 4, 0.7, True, 0.5)
            b.snare_bar(tb, "march" if j == 0 else "drive", 0.6 + 0.05 * j, cres=0.3 if j else 0.0)
        climb_t0 = max(t0, t1 - 2 * bar)
        root = chord(dom)["oom"][0]
        for i in range(4):
            t = climb_t0 + i * (t1 - climb_t0) / 4
            m = root + i
            for k in range(2):
                b.add("tuba", I.brass(F(m), 0.2, 0.7 + 0.05 * i, b.r(), "tuba"), t + k * Q / 2, -0.1)
            for k in range(4):
                b.add("glock", I.glock(F(96 + i), 0.22 + 0.04 * i, b.r(), dur=0.5), t + k * Q / 4, -0.35)
        b.roll(max(t0, t1 - bar), t1, 0.45, 1.0)
        b.gate(t1 - 0.015, min(b.dur, t1 + 0.5))
        b.cues.append((t0, f"{name}: tension pedal, chromatic climb, roll, dead stop at {t1:.2f}"))
        return
    if style == "sway":
        chords = []
        step = 1.4
        t = t0
        cyc = [b.chords_at(1)[0], b.chords_at(6)[0], b.chords_at(1)[0], b.chords_at(4)[0]]
        k = 0
        while t < t1 - 0.2:
            chords.append((t, min(t1, t + step), cyc[k % 4]))
            t += step
            k += 1
        for (ta, tb_, c) in chords:
            ms = [chord(c)["oom"][0] + 12] + chord(c)["hi"]
            b.add("pad", I.pad([F(m) for m in ms], tb_ - ta, 0.55, b.r(), att=0.5 if ta == t0 else 0.25, rel=0.6), ta, 0.0)
            b.add("tuba", I.brass(F(ms[0] - 12 if ms[0] > 40 else ms[0]), tb_ - ta - 0.05, 0.32, b.r(), "soft", scoop=-8), ta + 0.05, -0.1)
        notes = [m for (_, _, m) in b.tune(t0, bars=[1, 2], until=t1)]
        tt_ = t0 + 0.3
        j = 0
        while tt_ < t1 - 0.3 and notes:
            b.add("vibes", I.vibes(F(notes[j % len(notes)]), 0.5, b.r(), dur=1.4, damp=0.7, trem_depth=0.12), tt_, -0.25)
            tt_ += 0.7
            j += 2
        b.cues.append((t0, f"{name}: warm pad sway, soft low brass, vibes"))
        return
    if style == "waltz":
        beat = Q
        barw = 3 * beat
        cyc = [b.chords_at(1)[0], b.chords_at(1)[0], b.chords_at(6)[0], b.chords_at(4)[0]]
        notes = [m for (_, _, m) in b.tune(t0, bars=[1, 2], until=t1)]
        k = 0
        t = t0
        while t < t1 - 0.1:
            c = chord(cyc[k % 4])
            b.add("pluck", I.pluck(F(c["oom"][0] + 12), 0.8, b.r(), dur=1.0), t, -0.05)
            for j in (1, 2):
                for mm in c["hi"][1:]:
                    b.add("pluck", I.pluck(F(mm), 0.4, b.r(), dur=0.5, bright=0.6), t + j * beat, 0.25)
            for j in range(3):
                if notes and (k * 3 + j) % 2 == 0:
                    b.add("musicbox", I.musicbox(F(notes[(k * 2 + j) % len(notes)] + 12), 0.62, b.r()), t + j * beat, 0.2)
            if k:
                b.add("triangle", I.triangle(0.35, b.r()), t, 0.35)
            b.add("pad", I.pad([F(m) for m in c["hi"]], barw, 0.32, b.r(), att=0.3, rel=0.4), t, 0.0)
            t += barw
            k += 1
        b.cues.append((t0, f"{name}: music-box waltz"))
        return
    if style == "swing":
        notes = []
        for k, (bi, tb) in enumerate(_bars(b, t0, t1)):
            notes += b.tune(tb - (bi - 1) * bar, bars=[bi], swing=True, late=0.025, until=t1)
        b.melody("vibes", notes, 0.6, 0, "vibes", -0.25)
        k = 0
        t = t0
        while t < t1 - 0.1:
            bi = ((k // 4) % b.bars) + 1
            c = chord(b.chords_at(bi)[k % 4])
            walk = [c["oom"][0] + 12, c["oom"][0] + 16, c["oom"][1] + 12, c["oom"][0] + 14][k % 4]
            b.add("pluck", I.pluck(F(walk), 0.85, b.r(), dur=0.9), t, -0.05)
            b.add("brush", I.brush(0.55 if k % 2 else 0.35, b.r(), dur=0.42, swish=True), t - 0.05, 0.1)
            b.add("brush", I.brush(0.35, b.r()), t + Q * 2 / 3, 0.15)
            if k % 2:
                for mm in c["hi"]:
                    b.add("vibes", I.vibes(F(mm), 0.22, b.r(), dur=0.9, damp=0.3, trem_depth=0.2), t + 0.02, 0.3)
            t += Q
            k += 1
        b.cues.append((t0, f"{name}: lazy swing, vibes, walking bass, brushes"))
        return
    if style == "pad":
        t = t0
        k = 0
        while t < t1 - 0.1:
            c = chord(b.chords_at(((k) % b.bars) + 1)[0])
            dur = min(bar, t1 - t)
            b.add("pad", I.pad([F(m) for m in [c["oom"][0] + 12] + c["hi"]], dur, 0.45, b.r(), att=0.6, rel=0.8), t, 0.0)
            t += bar
            k += 1
        b.cues.append((t0, f"{name}: pad only"))
        return
    if style == "creep":
        # under the building: a dark low drone on the dominant, a soft pizzicato tick every half bar; almost nothing,
        # so the turn hits (spec hits of kind "turn") carry the section
        dom = chord(b.chords_at(4)[0])
        root = dom["oom"][0]
        b.add("drone", I.pad([F(root), F(root + 7), F(root + 12)], t1 - t0, 0.5, b.r(), att=1.2, rel=0.8, warm=380), t0, 0.0)
        t, k = t0 + Q, 0
        while t < t1 - 0.2:
            b.add("creep", I.pluck(F(root + (12 if k % 2 == 0 else 19)), 0.55 if k % 2 == 0 else 0.4, b.r(), dur=0.7, bright=0.25), t, -0.15 + 0.3 * (k % 2))
            t += 2 * Q
            k += 1
        b.cues.append((t0, f"{name}: creep (low drone on the dominant, pizzicato tick every half bar)"))
        return
    if style == "stabs":
        # rolls into the hits inside this section (hits come from the spec); otherwise a pad under
        b.cues.append((t0, f"{name}: brass stabs on the hits"))
        return
    raise ValueError(f"unknown style {style!r}; one of {STYLES}")


def build(spec, dur):
    chords = spec.get("chords")
    if chords:
        chords = {int(k): v for k, v in chords.items()}
    theme = [tuple(x) for x in spec["theme"]] if spec.get("theme") else None
    b = Band(dur, tempo=spec.get("tempo", 120), theme=theme, chords=chords, key=spec.get("key", "Bb"), seed=spec.get("seed", 1831))
    secs = spec.get("sections", [])
    for i, s in enumerate(secs):
        t0, t1 = float(s["start"]), float(min(s["end"], dur))
        if t1 <= t0:
            continue
        _section(b, s.get("name", f"s{i}"), t0, t1, s.get("style", "march"), i)
    hits = [h if isinstance(h, dict) else {"t": h} for h in spec.get("hits", [])]
    nstab = 0
    for i, h in enumerate(hits):
        _hit(b, i, float(h["t"]), h.get("kind", "stab"), h, nstab, i == len(hits) - 1)
        nstab += h.get("kind", "stab") == "stab"
    for i, s in enumerate(secs):
        if s.get("style") == "silence":
            b.gate(float(s["start"]), float(min(s["end"], dur)))
    b.fade_out(dur - float(spec.get("end_fade", 0.4)))
    return b


def _stab_chord(b, c, th, vel=0.72, dur=0.18, oct_up=0):
    for m in [c["oom"][0] + 12] + c["pah"] + c["hi"][-1:]:
        m += oct_up
        b.add("stab", I.brass(F(m), dur, vel, b.r(), "stab", scoop=-12), th, (m - 56) / 22)


def _hit(b, i, th, kind, h, nstab, last):
    tonic, domc = chord(b.chords_at(1)[0]), chord(b.chords_at(4)[0])
    if kind == "stab":
        c = tonic if nstab % 2 == 0 else domc
        b.roll(max(0.0, th - 0.9), th - 0.02, 0.12, 0.55)
        _stab_chord(b, c, th)
        b.add("timpani", I.timpani(F(c["oom"][0]), 0.72, b.r()), th, -0.1)
        if last or h.get("cymbal"):
            b.add("cymbal", I.cymbal(0.25, b.r(), dur=1.2), th, 0.0)
        b.cues.append((th, f"hit {i + 1}: brass stab + timpani"))
    elif kind == "button":
        _stab_chord(b, tonic, th, 0.8, 0.22)
        b.add("timpani", I.timpani(F(tonic["oom"][0]), 0.8, b.r()), th, -0.1)
        b.add("cymbal", I.cymbal(0.5, b.r(), dur=1.6), th, 0.0)
        b.cues.append((th, f"hit {i + 1}: button (tutti chord + clash, no roll)"))
    elif kind == "rise":
        d = float(h.get("dur", 2.0))
        b.roll(max(0.0, th - 0.9), th - 0.02, 0.12, 0.55)
        _stab_chord(b, tonic, th)
        b.add("timpani", I.timpani(F(tonic["oom"][0]), 0.72, b.r()), th, -0.1)
        root = tonic["oom"][0] + 24
        steps = [0, 4, 7, 12, 16, 19, 24]
        for k, st_ in enumerate(steps):
            tk = th + 0.25 + k * (d - 0.45) / len(steps)
            b.add("pah", I.brass(F(root + st_), 0.2, 0.5 + 0.05 * k, b.r(), "horn", scoop=-15), tk, 0.2)
            b.add("glock", I.glock(F(root + 24 + st_), 0.4 + 0.05 * k, b.r(), dur=0.8), tk, -0.35)
        b.roll(th + 0.3, th + d - 0.03, 0.15, 0.6)
        _stab_chord(b, tonic, th + d, 0.8, 0.26, 12)
        b.add("timpani", I.timpani(F(tonic["oom"][0]), 0.8, b.r()), th + d, -0.1)
        b.add("cymbal", I.cymbal(0.4, b.r(), dur=1.6), th + d, 0.0)
        b.cues.append((th, f"hit {i + 1}: rise (stab, brass + glock climb, stab + clash at {th + d:.2f})"))
    elif kind == "turn":
        stp = int(h.get("step", 0))
        root = domc["oom"][0] + stp
        b.add("turn", I.timpani(F(root), 0.8, b.r(), dur=1.4), th, -0.05)
        b.add("turn", I.brass(F(root), 0.22, 0.75, b.r(), "tuba", scoop=-25), th, -0.1)
        b.add("turn", I.brass(F(root + 12), 0.14, 0.5, b.r(), "horn", scoop=-12), th, 0.1)
        b.add("turn", I.snare(0.35, b.r(), dur=0.15, snappy=0.4), th + 0.005, 0.05)
        b.cues.append((th, f"hit {i + 1}: turn knock (timpani + low brass, +{stp} st)"))
    elif kind == "reveal":
        b.add("cymbal", I.cymbal(0.18, b.r(), dur=2.5, bright=0.6), th, 0.0)
        b.add("timpani", I.timpani(F(tonic["oom"][0]), 0.45, b.r(), dur=2.6), th, -0.1)
        for m in tonic["hi"]:
            b.add("vibes", I.vibes(F(m + 12), 0.5, b.r(), dur=2.6, damp=2.2, trem_depth=0.2), th, (m - 60) / 20)
        b.add("pad", I.pad([F(m) for m in [tonic["oom"][0] + 12] + tonic["hi"]], 2.2, 0.55, b.r(), att=0.3, rel=1.2), th, 0.0)
        b.cues.append((th, f"hit {i + 1}: reveal (soft timpani, vibes chord, cymbal)"))
    elif kind == "chime":
        for m in tonic["hi"]:
            b.add("vibes", I.vibes(F(m + 12), 0.55, b.r(), dur=2.5, damp=2.4, trem_depth=0.15), th, (m - 60) / 20)
            b.add("glock", I.glock(F(m + 24), 0.35, b.r(), dur=2.0), th + 0.02, -0.35)
        b.add("tuba", I.brass(F(tonic["oom"][0] + 12), 1.2, 0.4, b.r(), "soft", scoop=-8), th, -0.1)
        b.add("timpani", I.timpani(F(tonic["oom"][0]), 0.4, b.r()), th, -0.1)
        b.cues.append((th, f"hit {i + 1}: final chime chord"))
    else:
        raise ValueError(f"unknown hit kind {kind!r}")


def sections(spec, dur):
    """[(name, start, end, level LU rel voice)] with silence sections kept (level ignored)"""
    out = []
    for i, s in enumerate(spec.get("sections", [])):
        out.append((s.get("name", f"s{i}"), float(s["start"]), float(min(s["end"], dur)), float(s.get("level", -10.0)), s.get("style", "march")))
    return out
