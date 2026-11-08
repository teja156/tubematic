# The soundtrack of one video from data: voice (gain only) + a score built from the spec's `music` (ducked under
# speech, per-section level relative to the voice) + a synthesized SFX stem from the spec's `cues`. Master to the
# target loudness with a look-ahead true-peak limiter. Writes mix.wav, the three stems and cues.md.
# Generalised from the bridge short's mix.py (mromidev/claude-animated-shorts, MIT, Copyright (c) 2026 Mr omi).
#
#   python mix.py --voice voice.wav --timeline timeline.json --spec audio-spec.json --out <dir> [--lufs -14] [--duration s]
#
# voice.wav: 48 kHz mono or stereo (ffmpeg -i audio.mp3 -ar 48000 voice.wav). timeline.json: the pipeline's
# (totalFrames, fps, words[{word, startFrame, endFrame}]). The mix is exactly totalFrames / fps seconds long.
import argparse
import json
import os
import sys
import time
import numpy as np
from scipy import ndimage, signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dsp import SR, ns, st, dbg, read_wav, write_wav, integrated, momentary, short_term, lra, true_peak, fades  # noqa: E402
import score  # noqa: E402
import cues as CU  # noqa: E402

CEIL_DBTP = -1.5   # the AAC encode in the mux adds ~0.2-0.3 dB of peak; -1.5 on the WAV keeps the mp4 under -1.0
DUCK_DB = -3.0            # the music under every spoken word
EVENT_DUCK_DB = -5.0      # ...and under every sound-effect event, for the event's length (EVENT_DUCK_MAX_S at most)
EVENT_DUCK_MAX_S = 3.0


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def words_of(timeline):
    fps = float(timeline.get("fps", 30))
    return [dict(word=w["word"], s=w["startFrame"] / fps, e=(w["endFrame"] + 1) / fps) for w in timeline["words"]]


def speech_spans(words, merge=0.3):
    sp = []
    for w in words:
        s, e = float(w["s"]), float(w["e"])
        if sp and s - sp[-1][1] < merge:
            sp[-1][1] = max(sp[-1][1], e)
        else:
            sp.append([s, e])
    return sp


def duck_db(spans, dur, depth=DUCK_DB, pre=0.08, post=0.12, att=0.07, rel=0.45):
    N = ns(dur)
    ctrl = 1000
    nc = int(dur * ctrl) + 2
    va = np.zeros(nc)
    for s, e in spans:
        va[max(0, int((s - pre) * ctrl)): int((e + post) * ctrl)] = 1.0
    ka, kr = 1 - np.exp(-1 / (att * ctrl)), 1 - np.exp(-1 / (rel * ctrl))
    env = np.zeros(nc)
    e = 0.0
    for i in range(nc):
        tgt = va[i]
        e += (tgt - e) * (ka if tgt > e else kr)
        env[i] = e
    return np.interp(np.arange(N) / SR, np.arange(nc) / ctrl, depth * env)


def section_db(m_ducked, v, secs, dips, dur):
    """per-section music gain so that music sits `level` LU under the voice in that section; steps smoothed 0.4 s
    except where the music is silent (silence sections), which switch hard"""
    N = ns(dur)
    gains = {}
    prev = 0.0
    for name, a, b, level, style in secs:
        seg = slice(ns(a), ns(b))
        Lm, Lv = integrated(m_ducked[:, seg]), integrated(v[:, seg])
        if style == "silence":      # (Chicago) keep the previous gain: only reverb tails live here, never boost them
            gains[name] = prev
            continue
        gains[name] = (Lv + level - Lm) if (np.isfinite(Lm) and np.isfinite(Lv)) else 0.0
        prev = gains[name]
    curve = np.zeros(N)
    t = np.arange(N) / SR
    for name, a, b, level, style in secs:
        curve[t >= a] = gains[name]
    sm = ndimage.uniform_filter1d(curve, ns(0.4), mode="nearest")
    hard = np.zeros(N, bool)
    for name, a, b, level, style in secs:
        if style == "silence":
            hard[max(0, ns(a - 0.25)): ns(a + 0.25)] = True
            hard[max(0, ns(b - 0.25)): ns(b + 0.25)] = True
    curve = np.where(hard, curve, sm)
    for a, b, db in dips:
        d = np.zeros(N)
        d[ns(a): ns(b)] = db
        curve += ndimage.uniform_filter1d(d, ns(0.06), mode="nearest")
    return curve, gains


def event_margins(C, gm, vI):
    """Each event's level in the mix against the music's momentary loudness over
    the event's first 0.4 s (the final music stem, section gains and ducking
    applied). Sets c.music and c.over; returns how many events sit under the
    music, which the cue sheet and loudness.json report: an effect the band
    covers is a fix for the author (raise its naive level, or quieten the section)."""
    Mm = momentary(gm)
    under = 0
    for c in C:
        if c.kind != "event" or c.measured is None:
            continue
        i0, i1 = max(0, int((c.t - 0.2) / 0.01)), min(len(Mm) - 1, int((c.t + 0.4) / 0.01))
        music = float(Mm[i0:i1 + 1].max()) if len(Mm) and i1 >= i0 else -np.inf
        c.music = music
        c.over = float((vI + c.measured) - music) if np.isfinite(music) else float("inf")
        if c.over < 0:
            under += 1
    return under


def limiter(x, ceil_db=CEIL_DBTP, look=0.003, rel=0.08):
    """4x-oversampled peak detection, look-ahead min filter, release one-pole, centred smoothing -> gain curve"""
    c = dbg(ceil_db)
    n = x.shape[1]
    up = np.abs(signal.resample_poly(x, 4, 1, axis=-1)).max(0)
    pk = np.pad(up, (0, max(0, 4 * n - len(up))))[: 4 * n].reshape(n, 4).max(1)
    gr = np.minimum(1.0, c / np.maximum(pk, 1e-12))
    La = max(1, ns(look))
    g1 = ndimage.minimum_filter1d(gr, 2 * La + 1, mode="nearest")
    g2 = g1.copy()
    idx = np.flatnonzero(g1 < 1.0)
    if len(idx):
        kr = 1 - np.exp(-1 / (rel * SR))
        gap = ns(rel * 8)
        brk = np.flatnonzero(np.diff(idx) > gap)
        starts = np.concatenate([[idx[0]], idx[brk + 1]])
        ends = np.concatenate([idx[brk], [idx[-1]]])
        for a, b_ in zip(starts, ends):
            e = min(n, b_ + gap)
            seg = g1[a:e]
            out = np.empty(len(seg))
            g = 1.0
            for k in range(len(seg)):
                g = min(seg[k], g + (1 - g) * kr)
                out[k] = g
            g2[a:e] = out
    g3 = ndimage.uniform_filter1d(g2, 2 * La + 1, mode="nearest")
    g3 = np.minimum(g3, 1.0)
    return x * g3[None, :], g3


def lufs(x):
    v = integrated(x)
    return v if np.isfinite(v) else -99.0


def load_voice(path, dur):
    x, sr = read_wav(path)
    assert sr == SR, f"voice must be {SR} Hz, got {sr}"
    v = x[0] if x.shape[0] == 1 else x.mean(0)
    N = ns(dur)
    out = np.zeros(N)
    out[: min(N, len(v))] = v[:N]
    return st(out)


def section_table(v, m, s, words, secs):
    Mv, Mb = momentary(v), momentary(m + s)
    tc = np.arange(len(Mv)) * 0.01 + 0.2
    speak = np.zeros(len(tc), bool)
    for w in words:
        speak |= (tc >= float(w["s"]) + 0.03) & (tc <= float(w["e"]) - 0.03)
    speak &= Mv > lufs(v) - 10
    rows = []
    for name, a, b, level, style in secs:
        seg = slice(ns(a), ns(b))
        Lv, Lm, Ls, Lb = lufs(v[:, seg]), lufs(m[:, seg]), lufs(s[:, seg]), lufs(m[:, seg] + s[:, seg])
        k = speak & (tc >= a) & (tc < b) & np.isfinite(Mb) & (Mb > -70)
        p10 = float(np.percentile(Mv[k] - Mb[k], 10)) if k.sum() > 5 else float("nan")
        med = float(np.median(Mv[k] - Mb[k])) if k.sum() > 5 else float("nan")
        rows.append((name, a, b, Lv, Lm, Ls, Lb, Lv - Lb, p10, med))
    return rows


def write_cues(path, C, b, stats, rows, G, secs, fps, dur):
    vI = stats["v_ref"] + G
    L = []
    w = L.append
    w("# Soundtrack cue sheet")
    w("")
    w("All sound is synthesized (numpy/scipy): `instruments.py` / `sfx_gen.py` play what `score.py` and `cues.py` read from the audio spec; `mix.py` mixes.")
    w("Voice: gain only (no EQ, no compression, no pitch).")
    w("")
    w(f"- Length {dur:.3f} s, 48 kHz stereo 24-bit. Integrated **{stats['I']:.1f} LUFS**, true peak **{stats['TP']:.1f} dBTP**, "
      f"LRA {stats['LRA']:.1f} LU, max momentary {stats['Mmax']:.1f} LUFS, max short-term {stats['Smax']:.1f} LUFS")
    w(f"- Stems: voice {stats['voice_I']:.1f} LUFS, music {stats['music_I']:.1f} LUFS, sfx {stats['sfx_I']:.1f} LUFS (voice gain {G:+.2f} dB)")
    n_ev, n_under = stats["events"], stats["events_under_music"]
    w(f"- Events over the music: {n_ev - n_under} of {n_ev} sit above the music at their moment"
      + (" — every effect is audible" if not n_under else
         f"; **{n_under} under the music** (see the `over music` column): raise their naive level or quieten the section"))
    gr = stats["gr"]
    w(f"- Limiter (ceiling {CEIL_DBTP} dBTP): max gain reduction {gr['max']:.2f} dB, active (>0.1 dB) on {gr['pct_over_0_1']:.2f} % of samples")
    w("")
    w("## Voice on top: per-section loudness (LUFS at mix gain)")
    w("bed = music + sfx. margin = voice - bed. speech median / p10 = the 400 ms momentary margin over windows centred on spoken words.")
    w("")
    w("| section | time s | voice | music | sfx | bed | margin LU | speech median LU | speech p10 LU |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        f = lambda x: "-" if x <= -98 else f"{x:.1f}"
        w(f"| {r[0]} | {r[1]:.2f}-{r[2]:.2f} | {f(r[3])} | {f(r[4])} | {f(r[5])} | {f(r[6])} | {r[7]:.1f} | {r[9]:.1f} | {r[8]:.1f} |")
    w("")
    w("## Music map")
    w("Applied section gains (dB): " + ", ".join(f"{k} {v:+.1f}" for k, v in stats["sec_gains"].items()))
    w("")
    w("| time s | frame | music |")
    w("|---|---|---|")
    for t, d in sorted(b.cues):
        w(f"| {t:.2f} | {int(round(t * fps))} | {d} |")
    w("")
    w("## SFX events")
    w(f"Events: applied = naive + distance/extra (no fixed offset); the music is ducked {-EVENT_DUCK_DB:.0f} dB under every event. "
      f"Beds: integrated, not reduced. 'mix LUFS' = the event's level in the mix (voice stem {vI:.1f} LUFS integrated); "
      f"'over music' = that level against the music's momentary loudness at the event's moment (below 0 = covered by the band).")
    w("")
    w("| # | time s | frame | cue | what | naive LU | applied LU | mix LUFS | over music LU | pan |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(sorted(C, key=lambda c: (c.t, c.name))):
        kind = " (bed)" if c.kind == "bed" else ""
        meas = c.measured if c.measured is not None else c.applied
        over = "-" if c.over is None else ("inf" if not np.isfinite(c.over) else f"{c.over:+.1f}")
        w(f"| {i + 1} | {c.t:.3f} | {c.t * fps:.1f} | {c.name}{kind} | {c.desc} | {c.naive:+.0f} | {c.applied:+.1f} | {vI + meas:.1f} | {over} | {c.p:+.2f} |")
    w("")
    open(path, "w", encoding="utf-8").write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--duration", type=float, default=None)
    a = ap.parse_args()
    t_start = time.time()
    os.makedirs(a.out, exist_ok=True)
    timeline = json.load(open(a.timeline))
    spec = json.load(open(a.spec))
    fps = float(timeline.get("fps", 30))
    dur = a.duration or timeline["totalFrames"] / fps
    N = ns(dur)
    words = words_of(timeline)
    spans = speech_spans(words)
    v = load_voice(a.voice, dur)
    v_ref = integrated(v)
    log(f"voice: {v_ref:.2f} LUFS (as stereo), TP {true_peak(v):.2f} dBTP, {dur:.3f} s")

    # ---------------- music
    music_spec = spec.get("music", {})
    b = score.build(music_spec, dur)
    m_raw, levels = score.render(b, ref=-20.0)
    log("music rendered", f"{lufs(m_raw):.2f} LUFS raw", levels)
    secs = score.sections(music_spec, dur) or [("all", 0.0, dur, -10.0, "march")]

    # ---------------- sfx (before the music's gains: the music ducks under every event)
    C = CU.from_spec(spec.get("sfx", {"cues": spec.get("cues", [])}), dur, fps)
    ev_spans = []

    def note_event(c, x, t0):
        if c.kind == "event":
            ev_spans.append([max(0.0, t0), min(dur, t0 + min(x.shape[1] / SR, EVENT_DUCK_MAX_S))])
    s_st, C = CU.render(C, dur, v_ref, on_event=note_event)
    log("sfx rendered", f"{lufs(s_st):.2f} LUFS, {len(C)} cues")

    dk = duck_db(spans, dur) + duck_db(ev_spans, dur, depth=EVENT_DUCK_DB, pre=0.03, post=0.05, att=0.03, rel=0.35)
    m_d = m_raw * dbg(dk)[None, :]
    dips = [tuple(x) for x in music_spec.get("dips", [])]
    sec_curve, sec_gains = section_db(m_d, v, secs, dips, dur)
    m = m_d * dbg(sec_curve)[None, :]
    end = ns(dur - 0.03)
    m[:, end:] *= np.linspace(1, 0, N - end)[None, :]

    # ---------------- master
    mix0 = v + m + s_st
    G = a.lufs - lufs(mix0)
    y, g3 = mix0, np.ones(N)
    for it in range(5):
        y, g3 = limiter(mix0 * dbg(G))
        L = lufs(y)
        log(f"master iter {it}: gain {G:+.2f} dB -> {L:.2f} LUFS, TP {true_peak(y):.2f} dBTP, max GR {-20 * np.log10(g3.min()):.2f} dB")
        if abs(L - a.lufs) < 0.02:
            break
        G += a.lufs - L
    y = fades(y, 0.0, 0.03)
    assert y.shape == (2, N)
    gv, gm, gs = v * dbg(G), m * dbg(G), s_st * dbg(G)
    under = event_margins(C, gm, v_ref + G)
    n_events = sum(1 for c in C if c.kind == "event")
    log(f"events over the music: {n_events - under} of {n_events}" + (f" ({under} under)" if under else ""))
    write_wav(os.path.join(a.out, "mix.wav"), y)
    write_wav(os.path.join(a.out, "stem_voice.wav"), gv)
    write_wav(os.path.join(a.out, "stem_music.wav"), gm)
    write_wav(os.path.join(a.out, "stem_sfx.wav"), gs)
    log("wrote mix + stems")

    # ---------------- measure
    I_, TP, LRA = lufs(y), true_peak(y), lra(y)
    Mmax, Smax = float(np.max(momentary(y))), float(np.max(short_term(y)))
    grdb = -20 * np.log10(g3)
    gr_stats = dict(max=float(grdb.max()), pct_over_0_5=float((grdb > 0.5).mean() * 100), pct_over_0_1=float((grdb > 0.1).mean() * 100))
    rows = section_table(gv, gm, gs, words, secs)
    stats = dict(I=I_, TP=TP, LRA=LRA, Mmax=Mmax, Smax=Smax, G=G, gr=gr_stats, v_ref=v_ref,
                 voice_I=lufs(gv), music_I=lufs(gm), sfx_I=lufs(gs), sec_gains=sec_gains,
                 events=n_events, events_under_music=under)
    log(json.dumps({k: (round(x, 2) if isinstance(x, float) else x) for k, x in stats.items() if k not in ("gr", "sec_gains")}))
    for r in rows:
        log(f"{r[0]:<15} voice {r[3]:6.1f}  music {r[4]:6.1f}  sfx {r[5]:6.1f}  bed {r[6]:6.1f}  margin {r[7]:5.1f}  speech med {r[9]:5.1f} p10 {r[8]:5.1f}")
    write_cues(os.path.join(a.out, "cues.md"), C, b, stats, rows, G, secs, fps, dur)
    json.dump({k: (round(x, 2) if isinstance(x, float) else x) for k, x in stats.items()}, open(os.path.join(a.out, "loudness.json"), "w"), indent=1)
    log(f"done in {time.time() - t_start:.0f} s")


if __name__ == "__main__":
    main()
