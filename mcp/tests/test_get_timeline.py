"""Tests for get_timeline (TMDEV-40): the only correct way for the agent to
read a video's timeline.json. videos.timeline_path is container-absolute
(/jobs/<vid>/timeline.json), so it cannot be read from the host or the agent
sandbox directly — this tool is what tubematic-scene-config's Workflow step 1
calls instead.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file and JOBS_DIR at a tmp dir.
    Returns a make_video factory."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make_video(video_id, status="VOICE_READY"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?, ?)",
                (video_id, "test topic", status, _now(), _now()),
            )

    return make_video


def _timeline(total_frames=300, with_segments=True):
    tl = {
        "totalFrames": total_frames,
        "fps": 30,
        "audioDurationSeconds": total_frames / 30,
        "words": [
            {"word": "hello", "startFrame": 0, "endFrame": 10},
            {"word": "world", "startFrame": 10, "endFrame": 20},
        ],
    }
    if with_segments:
        tl["segments"] = [
            {"id": "seg-1", "startFrame": 0, "endFrame": total_frames // 2},
            {"id": "seg-2", "startFrame": total_frames // 2, "endFrame": total_frames},
        ]
    return tl


def _write_timeline(video_id, timeline):
    job_dir = server.JOBS_DIR / video_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")


def test_get_timeline_success_segments_only(job_db):
    job_db("vid_ok")
    _write_timeline("vid_ok", _timeline())

    result = server.get_timeline("vid_ok")

    assert result == {
        "video_id": "vid_ok",
        "total_frames": 300,
        "fps": 30,
        "segments": [
            {"id": "seg-1", "startFrame": 0, "endFrame": 150},
            {"id": "seg-2", "startFrame": 150, "endFrame": 300},
        ],
    }
    assert "words" not in result


def test_get_timeline_include_words(job_db):
    job_db("vid_words")
    _write_timeline("vid_words", _timeline())

    result = server.get_timeline("vid_words", include_words=True)

    assert result["words"] == [
        {"word": "hello", "startFrame": 0, "endFrame": 10},
        {"word": "world", "startFrame": 10, "endFrame": 20},
    ]


def test_get_timeline_legacy_video_empty_segments(job_db):
    """Pre-script_segments videos have no 'segments' key in timeline.json —
    the tool should return an empty list, not error, so the skill's legacy
    keyword-anchored fallback can detect "no segments" and branch cleanly."""
    job_db("vid_legacy")
    _write_timeline("vid_legacy", _timeline(with_segments=False))

    result = server.get_timeline("vid_legacy")

    assert result["segments"] == []


def test_get_timeline_unknown_video(job_db):
    result = server.get_timeline("does_not_exist")

    assert result == {"error": "Video not found: does_not_exist"}


def test_get_timeline_missing_file(job_db):
    job_db("vid_no_voice_yet")

    result = server.get_timeline("vid_no_voice_yet")

    assert "error" in result
    assert "timeline.json not found" in result["error"]


def test_get_timeline_malformed_json(job_db):
    job_db("vid_corrupt")
    job_dir = server.JOBS_DIR / "vid_corrupt"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "timeline.json").write_text("{not valid json", encoding="utf-8")

    result = server.get_timeline("vid_corrupt")

    assert "error" in result
    assert "could not be read" in result["error"]


def test_get_timeline_video_id_traversal_rejected(job_db):
    """The id's shape is checked before any path is built (TMDEV-158), so a
    path-traversal attempt like '../../etc' never reaches JOBS_DIR / video_id,
    whether or not a row could be found for it."""
    result = server.get_timeline("../../etc")

    assert "not a valid video id" in result["error"]
