"""The mixer's rules an author relies on (TMDEV-185): an event sits at the
level the spec asks for (no hidden offset), the music ducks under it, and the
cue sheet says for every event whether the band covers it.

Needs numpy and scipy (the MCP image has them; a host without them skips).
Run from this directory: python3 -m pytest tests/
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import cues  # noqa: E402
import dsp  # noqa: E402


def _voice(path, dur=6.0):
    """a 'voice': 0.4 s bursts of band noise every second, so the timeline has words"""
    n = int(dur * dsp.SR)
    x = np.zeros(n)
    r = np.random.default_rng(1)
    for k in range(int(dur)):
        a = int((k + 0.3) * dsp.SR)
        x[a:a + int(0.4 * dsp.SR)] = r.normal(0, 0.1, int(0.4 * dsp.SR))
    dsp.write_wav(str(path), np.stack([x, x]))
    return [{"word": f"w{k}", "startFrame": int((k + 0.3) * 30), "endFrame": int((k + 0.7) * 30)} for k in range(int(dur))]


def _run(tmp_path, spec):
    tmp_path.mkdir(parents=True, exist_ok=True)
    words = _voice(tmp_path / "voice.wav")
    (tmp_path / "timeline.json").write_text(json.dumps({"fps": 30, "totalFrames": 180, "words": words}))
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    out = tmp_path / "mix"
    proc = subprocess.run([sys.executable, "-I", str(HERE / "mix.py"), "--voice", str(tmp_path / "voice.wav"),
                           "--timeline", str(tmp_path / "timeline.json"), "--spec", str(tmp_path / "spec.json"), "--out", str(out)],
                          cwd=str(HERE), capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return out, json.loads((out / "loudness.json").read_text()), (out / "cues.md").read_text()


def test_an_event_is_placed_at_its_naive_level_with_no_hidden_offset():
    assert cues.SFX_DB == 0.0
    c = cues.Cue(1.0, "hit", "a hit", lambda: (np.zeros(10), 0.0), naive=-4.0)
    assert c.applied == -4.0
    bed = cues.Cue(0.0, "bed", "a bed", lambda: (np.zeros(10), 0.0), naive=-30.0, kind="bed")
    assert bed.applied == -30.0


def test_the_music_ducks_under_an_event_and_the_sheet_says_what_the_band_covers(tmp_path):
    loud_band = {"music": {"tempo": 120, "key": "F", "seed": 7,
                           "sections": [{"name": "all", "start": 0, "end": 6, "style": "tutti", "level": -8}]},
                 "sfx": {"seed": 7, "cues": [{"t": 2.5, "gen": "hammer_hit", "naive": 0, "desc": "loud hit"},
                                             {"t": 4.5, "gen": "hammer_hit", "naive": -18, "dist": 30, "desc": "buried hit"},
                                             {"t": 5.9, "gen": "hammer_hit", "naive": -18, "dist": 30, "desc": "buried hit at the very end"}]}}
    out, loud, sheet = _run(tmp_path, loud_band)
    assert loud["events"] == 3 and loud["events_under_music"] == 2
    assert "| over music LU |" in sheet and "**2 under the music**" in sheet
    rows = [l for l in sheet.splitlines() if "| hammer_hit |" in l]
    assert len(rows) == 3
    over = [float(r.split("|")[9]) for r in rows]           # an "inf" here would fail float() for a reason: every event is measured
    assert over[0] > 0 and over[1] < 0 and over[2] < 0, over   # the last event lies in the final 200 ms, past the last window's start
    # the music is ducked round the loud hit: the same score without the hit is louder at the hit's moment
    # and the same just before it
    quiet_band = {"music": loud_band["music"], "sfx": {"seed": 7, "cues": []}}
    out2, _, _ = _run(tmp_path / "nohit", quiet_band)
    m_hit, _ = dsp.read_wav(str(out / "stem_music.wav"))
    m_plain, _ = dsp.read_wav(str(out2 / "stem_music.wav"))

    def level(m, t):
        seg = m[:, int((t - 0.1) * dsp.SR): int((t + 0.1) * dsp.SR)]
        return 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)
    before = level(m_plain, 1.9) - level(m_hit, 1.9)
    during = level(m_plain, 2.62) - level(m_hit, 2.62)
    assert during - before > 3.0, (before, during)
