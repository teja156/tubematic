"""The pitch-keeping stretch of a voice recording (TMDEV-227).

The host this suite usually runs on has no ffmpeg, so the command is checked
with subprocess replaced; the one real-ffmpeg test runs where ffmpeg is on PATH
(the backend image has it) and is skipped elsewhere.
"""
import pathlib
import shutil
import subprocess
import sys
import wave

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import audio_speed as ta  # noqa: E402


def _write_wav(path: pathlib.Path, seconds: float, rate: int = 44100):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))


def test_the_words_are_divided_by_the_factor():
    words = [{"word": "one", "start": 0.0, "end": 0.5}, {"word": "two", "start": 1.1, "end": 2.2}]
    out = ta.scale_words(words, 1.1)
    assert out == [{"word": "one", "start": 0.0, "end": 0.5 / 1.1},
                   {"word": "two", "start": 1.1 / 1.1, "end": 2.2 / 1.1}]
    assert words[1]["end"] == 2.2  # the input is left as it was
    assert ta.scale_words(words, 1.0) == words and ta.scale_words(words, 1.0) is not words


def test_stretch_runs_atempo_and_reports_the_decoded_length(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        out = pathlib.Path(cmd[-1])
        if out.suffix == ".wav":
            _write_wav(out, 2.5)
        else:
            out.write_bytes(b"mp3")
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(ta.subprocess, "run", fake_run)
    audio, seconds = ta.stretch("ffmpeg", b"in", 1.15)
    assert audio == b"mp3" and seconds == 2.5
    assert "atempo=1.150000" in calls[0]
    assert "libmp3lame" in calls[1]


@pytest.mark.parametrize("factor", [0.4, 2.5])
def test_a_factor_atempo_cannot_take_is_refused(factor):
    with pytest.raises(ValueError, match="atempo"):
        ta.stretch("ffmpeg", b"in", factor)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg on PATH (the backend image has it)")
def test_a_real_stretch_shortens_the_recording_by_the_factor(tmp_path):
    src = tmp_path / "tone.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(src)], check=True)
    _, seconds = ta.stretch(shutil.which("ffmpeg"), src.read_bytes(), 1.25)
    assert seconds == pytest.approx(4 / 1.25, abs=0.06)
