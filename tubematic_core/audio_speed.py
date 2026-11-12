"""Speeding up a finished voice recording without changing its pitch (TMDEV-227).

eleven_v3 and eleven_v4 ignore ElevenLabs' own speed setting, and the native
models stop at 1.2, so the rest of a speed is a time-stretch of the recording
(voice_models.speed_plan decides how much). ffmpeg's atempo filter does it: it
keeps the pitch, and the user chose it over rubberband after listening to both
on the default voice. atempo takes 0.5 to 2.0 in one pass, which covers every
factor a speed plan can ask for (a video's speed is 0.9 to 1.25).

The word timings come from ElevenLabs' alignment of the unstretched recording,
so every one of them is divided by the same factor (scale_words), or the
captions and the scene cuts drift ahead of the voice.

Used by the MCP server's generate_voice and the API's voice preview; both run
in the backend image, whose Debian ffmpeg has atempo. No DB, no network.
"""
from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

ATEMPO_MIN = 0.5
ATEMPO_MAX = 2.0


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def stretch(ffmpeg: str, mp3: bytes, factor: float) -> tuple[bytes, float]:
    """The recording sped up by `factor` (1.1 = 10% faster) with its pitch
    kept, as a 128 kbps mono mp3, and its decoded length in seconds.

    The result goes through a WAV first: its frame count is the exact length,
    which is what the next run of a two-voice script is offset by, never an
    estimate from the mp3."""
    if not ATEMPO_MIN <= factor <= ATEMPO_MAX:
        raise ValueError(f"stretch factor {factor} is outside atempo's {ATEMPO_MIN}-{ATEMPO_MAX}")
    with tempfile.TemporaryDirectory(prefix="tubematic-stretch-") as tmp:
        d = Path(tmp)
        src, wav, out = d / "in.mp3", d / "out.wav", d / "out.mp3"
        src.write_bytes(mp3)
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(src), "-af", f"atempo={factor:.6f}",
                        "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(wav)],
                       check=True, capture_output=True, timeout=300)
        seconds = wav_seconds(wav)
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "128k",
                        str(out)], check=True, capture_output=True, timeout=300)
        return out.read_bytes(), seconds


def scale_words(words: list[dict], factor: float) -> list[dict]:
    """Word timings ({word, start, end} in seconds) for the recording sped up
    by `factor`: every time divided by it."""
    if factor == 1.0:
        return [dict(w) for w in words]
    return [{**w, "start": w["start"] / factor, "end": w["end"] / factor} for w in words]
