"""Tests for validate_job's segmented-script integrity checks (TMDEV-2 Task 4):
- videos.script_segments themselves are well-formed
- timeline.json's segments array (written by generate_voice, Task 2) is
  contiguous and covers 0 -> totalFrames with no gaps
- legacy videos without script_segments are unaffected

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
import sys
import types
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file and return a helper to insert a video row."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()

    def make_video(video_id, voice_file_path, timeline_path, scene_config_path, script_segments=None):
        with server._conn() as con:
            con.execute(
                """
                INSERT INTO videos (id, topic, voice_file_path, timeline_path,
                                     scene_config_path, script_segments, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, "test topic", str(voice_file_path), str(timeline_path),
                 str(scene_config_path),
                 json.dumps(script_segments) if script_segments else None,
                 _now(), _now()),
            )

        _place_job_files(video_id, voice_file_path, timeline_path, scene_config_path)

    return make_video


def _place_job_files(video_id, voice_file_path, timeline_path, scene_config_path):
    """Copy the job files to JOBS_DIR/<id>/, where validate_job looks for them.

    validate_job derives every path from the id (TMDEV-162); the row's columns
    only say each file was written. A path that names no file is left out, so
    a test of a missing file still finds it missing.
    """
    from pathlib import Path
    import shutil
    for src, name in ((voice_file_path, "audio.mp3"), (timeline_path, "timeline.json"),
                      (scene_config_path, "scene-config.json")):
        src = Path(str(src))
        dst = server.JOBS_DIR / video_id / name
        if src.is_file() and src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)


def _write_job_files(tmp_path, timeline_extra=None, total_frames=50):
    """Write a minimal valid audio.mp3 + timeline.json + scene-config.json job triplet.

    scene-config.json's totalFrames always matches timeline's default so the
    pre-existing frame-count check never fires here — keeps these tests
    isolated to the new segment-integrity checks.
    """
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"0" * 60_000)  # > 50KB, passes the size check

    timeline = {
        "totalFrames": total_frames,
        "fps": 30,
        "audioDurationSeconds": total_frames / 30,
        "words": [],
    }
    if timeline_extra:
        timeline.update(timeline_extra)
    timeline_path = tmp_path / "timeline.json"
    timeline_path.write_text(json.dumps(timeline))

    scene_config_path = tmp_path / "scene-config.json"
    scene_config_path.write_text(json.dumps({
        "totalFrames": timeline["totalFrames"],
        "fps": 30,
        "scenes": [],
        "sfx": [],
    }))

    return audio_path, timeline_path, scene_config_path


# ── valid case: segments well-formed, timeline.segments spans 0 -> totalFrames ──

def test_validate_job_segments_valid_passes(tmp_path, job_db):
    """A 20-frame (~0.67s) inter-segment gap is a normal TTS pause at a
    sentence break, well within SEGMENT_GAP_TOLERANCE_FRAMES (45) — must not
    be flagged as an error."""
    segments = [
        {"id": "s1", "voice": "Hello there.", "visual": ""},
        {"id": "s2", "voice": "This is segment two.", "visual": ""},
    ]
    audio, timeline, scene_config = _write_job_files(tmp_path, total_frames=300, timeline_extra={
        "segments": [
            {"id": "s1", "startFrame": 0, "endFrame": 200},
            {"id": "s2", "startFrame": 220, "endFrame": 300},
        ],
    })
    job_db("vid_valid", audio, timeline, scene_config, script_segments=segments)

    result = server.validate_job("vid_valid")
    segment_errors = [e for e in result["errors"] if "Segment" in e or "segments" in e]
    assert segment_errors == []


# ── gap in segment spans -> fails with a clear message ──────────────────────

def test_validate_job_segments_gap_fails(tmp_path, job_db):
    """A ~10s unaccounted-for gap between segments is far larger than any
    plausible TTS sentence pause — indicates a dropped/misaligned segment,
    not natural speech, so it must fail."""
    segments = [
        {"id": "s1", "voice": "Hello there.", "visual": ""},
        {"id": "s2", "voice": "This is segment two.", "visual": ""},
    ]
    audio, timeline, scene_config = _write_job_files(tmp_path, total_frames=500, timeline_extra={
        "segments": [
            {"id": "s1", "startFrame": 0, "endFrame": 200},
            # gap: s2 starts 300 frames (~10s) after s1 ends — tolerance is ±45
            {"id": "s2", "startFrame": 500, "endFrame": 500},
        ],
    })
    job_db("vid_gap", audio, timeline, scene_config, script_segments=segments)

    result = server.validate_job("vid_gap")
    assert result["passed"] is False
    errors = " ".join(result["errors"])
    assert "Segment span gap" in errors
    assert "s1" in errors and "s2" in errors


def test_validate_job_segments_missing_timeline_segments_fails(tmp_path, job_db):
    """script_segments present but timeline.json predates Task 2 (no 'segments' key)
    -> a clear, non-crashing validation failure, not a raw KeyError."""
    segments = [{"id": "s1", "voice": "Hello there.", "visual": ""}]
    audio, timeline, scene_config = _write_job_files(tmp_path)  # no "segments" key
    job_db("vid_missing_segments", audio, timeline, scene_config, script_segments=segments)

    result = server.validate_job("vid_missing_segments")
    assert result["passed"] is False
    errors = " ".join(result["errors"])
    assert "segments" in errors
    assert "generate_voice" in errors


def test_validate_job_malformed_script_segments_fails(tmp_path, job_db):
    """A stored script_segments with a blank 'voice' fails the same rule as
    update_video's _validate_script_segments (single source of truth)."""
    segments = [{"id": "s1", "voice": "   ", "visual": ""}]
    audio, timeline, scene_config = _write_job_files(tmp_path, timeline_extra={
        "segments": [{"id": "s1", "startFrame": 0, "endFrame": 50}],
    })
    job_db("vid_malformed", audio, timeline, scene_config, script_segments=segments)

    result = server.validate_job("vid_malformed")
    assert result["passed"] is False
    assert any("voice" in e for e in result["errors"])


# ── legacy video (no script_segments) is completely unaffected ─────────────

def test_validate_job_legacy_video_unaffected(tmp_path, job_db):
    """A legacy video with no script_segments gets none of the new checks, even
    though its timeline.json has no 'segments' key at all (the normal legacy shape)."""
    audio, timeline, scene_config = _write_job_files(tmp_path)  # no "segments" key
    job_db("vid_legacy", audio, timeline, scene_config, script_segments=None)

    result = server.validate_job("vid_legacy")
    segment_errors = [e for e in result["errors"] if "Segment" in e or "segments" in e]
    assert segment_errors == []


def test_validate_job_legacy_video_existing_checks_still_run(tmp_path, job_db):
    """Proof (not just assertion) that legacy behavior is unchanged: an
    existing, pre-Task-4 check (audio too small) still fires normally for a
    legacy video, and zero segment-integrity errors appear alongside it."""
    audio, timeline, scene_config = _write_job_files(tmp_path)
    audio.write_bytes(b"0" * 100)  # well under the 50KB floor
    job_db("vid_legacy_bad_audio", audio, timeline, scene_config, script_segments=None)

    result = server.validate_job("vid_legacy_bad_audio")
    assert result["passed"] is False
    assert any("too small" in e for e in result["errors"])
    assert not any("Segment" in e or "segments" in e for e in result["errors"])


# ── TMDEV-30: robustness fixes ──────────────────────────────────────────────

def test_validate_job_audio_decode_error_is_reported_not_raised(tmp_path, job_db, monkeypatch):
    """A decode failure (not ImportError) on a corrupt/truncated mp3 during
    the optional silence check must be recorded as a validation error, not
    propagate uncaught and crash the whole call. Only ImportError (pydub not
    installed) is a legitimate no-op."""
    class _FakeAudioSegment:
        @staticmethod
        def from_mp3(path):
            raise ValueError("simulated decode failure")

    fake_pydub = types.ModuleType("pydub")
    fake_pydub.AudioSegment = _FakeAudioSegment
    monkeypatch.setitem(sys.modules, "pydub", fake_pydub)

    audio, timeline, scene_config = _write_job_files(tmp_path)
    job_db("vid_decode_fail", audio, timeline, scene_config, script_segments=None)

    result = server.validate_job("vid_decode_fail")

    assert result["passed"] is False
    assert any("decode" in e.lower() for e in result["errors"])


def test_validate_job_empty_voice_file_path_treated_as_missing(tmp_path, job_db):
    """Path("") == Path(".") — the cwd, which always exists — so an empty
    voice_file_path must be treated as missing rather than silently passing
    the existence check and then crashing trying to decode the cwd as an
    mp3."""
    _, timeline, scene_config = _write_job_files(tmp_path)
    job_db("vid_empty_path", "", timeline, scene_config, script_segments=None)

    result = server.validate_job("vid_empty_path")

    assert result["passed"] is False
    assert any("audio.mp3" in e for e in result["errors"])
