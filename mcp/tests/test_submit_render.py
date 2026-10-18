"""Tests for submit_render (TMDEV-32): it's now a pure DB write — no network
call. It atomically claims VOICE_READY -> RENDER_QUEUED (the same
guarded-UPDATE pattern as before, just without a renderer POST in between);
the render worker (a separate always-on process) picks up RENDER_QUEUED
videos on its own poll loop.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file. Returns a make_video factory."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()

    def make_video(video_id, status="VOICE_READY"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos "
                "(id, project_id, topic, status, voice_file_path, timeline_path, "
                " scene_config_path, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id, "test topic", status,
                    str(tmp_path / "audio.mp3"), str(tmp_path / "timeline.json"),
                    str(tmp_path / "scene-config.json"),
                    _now(), _now(),
                ),
            )

    return make_video


def test_submit_render_success_advances_to_render_queued(job_db):
    job_db("vid_ok")

    result = server.submit_render("vid_ok")

    assert result == {"status": "queued", "video_id": "vid_ok"}
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_ok",)).fetchone()
    assert row["status"] == "RENDER_QUEUED"


def test_submit_render_rejects_when_not_voice_ready(job_db):
    job_db("vid_wrong_status", status="VOICING")

    result = server.submit_render("vid_wrong_status")

    assert result["error"] == "status_mismatch"
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_wrong_status",)).fetchone()
    assert row["status"] == "VOICING"


def test_submit_render_claims_atomically(job_db, monkeypatch):
    """Simulates a race between the initial status check and the atomic
    claim: another actor flips the video away from VOICE_READY in that
    window. The atomic claim itself — not just the earlier check — must
    catch this and leave the video at whatever it was flipped to."""
    job_db("vid_race")

    real_set_status = server._set_status

    def _flip_then_call(video_id, new_status, only_if=None):
        with server._conn() as con:
            con.execute("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = ?", (video_id,))
        return real_set_status(video_id, new_status, only_if=only_if)

    monkeypatch.setattr(server, "_set_status", _flip_then_call)

    result = server.submit_render("vid_race")

    assert result["error"] == "status_mismatch"
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_race",)).fetchone()
    assert row["status"] == "REVISION_REQUESTED"
