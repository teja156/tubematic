"""Tests for write_scene_config (TMDEV-25): the agent's only correct write
path for scene-config.json. Writes JOBS_DIR/{video_id}/scene-config.json and
records the resulting path on videos.scene_config_path in one call — same
JOBS_DIR-derived-path pattern generate_voice uses for voice_file_path/
timeline_path.

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


def _config(total_frames=300):
    return {
        "totalFrames": total_frames,
        "fps": 30,
        "scenes": [
            {"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": total_frames},
        ],
        "sfx": [],
    }


def test_write_scene_config_writes_where_every_reader_derives(job_db):
    """Agreement (TMDEV-162): readers derive the path through
    tubematic_core.jobfiles, so this writer must use the same name."""
    from tubematic_core import jobfiles
    job_db("vid_agree")
    result = server.write_scene_config("vid_agree", _config())
    assert result["path"] == str(
        jobfiles.job_file(server.JOBS_DIR, "vid_agree", jobfiles.SCENE_CONFIG))


def test_write_scene_config_success(job_db):
    job_db("vid_ok")

    result = server.write_scene_config("vid_ok", _config())

    expected_path = server.JOBS_DIR / "vid_ok" / "scene-config.json"
    assert result == {
        "video_id": "vid_ok",
        "path": str(expected_path),
        "size_bytes": expected_path.stat().st_size,
        "total_frames": 300,
        "scene_count": 1,
        # TMDEV-101: filled in rather than required, so a config written by a
        # skill that predates the canvas key still writes a complete file.
        "canvas": "dark",
        # The video's stored permission set, echoed back unchanged — not the
        # canvas, which is reported separately above.
        "visual_style": "auto",
        # TMDEV-101: on when the key is absent, which is what carries the
        # default to configs written by a skill that predates subtitles.
        "subtitles_enabled": True,
    }
    assert json.loads(expected_path.read_text()) == {**_config(), "canvas": "dark"}


def test_write_scene_config_persists_path_on_video(job_db):
    job_db("vid_persist")

    server.write_scene_config("vid_persist", _config())

    with server._conn() as con:
        row = con.execute(
            "SELECT scene_config_path FROM videos WHERE id = ?", ("vid_persist",)
        ).fetchone()
    assert row["scene_config_path"] == str(server.JOBS_DIR / "vid_persist" / "scene-config.json")


def test_write_scene_config_overwrites_existing_file(job_db):
    job_db("vid_overwrite")
    server.write_scene_config("vid_overwrite", _config(total_frames=100))

    result = server.write_scene_config("vid_overwrite", _config(total_frames=200))

    assert result["total_frames"] == 200
    path = server.JOBS_DIR / "vid_overwrite" / "scene-config.json"
    assert json.loads(path.read_text())["totalFrames"] == 200


def test_write_scene_config_unknown_video(job_db):
    result = server.write_scene_config("does_not_exist", _config())

    assert result == {"error": "Video not found: does_not_exist"}
    assert not (server.JOBS_DIR / "does_not_exist").exists()


@pytest.mark.parametrize(
    "bad_config",
    [
        "not a dict",
        {},
        {"totalFrames": 0, "scenes": [{}]},
        {"totalFrames": -5, "scenes": [{}]},
        {"totalFrames": "300", "scenes": [{}]},
        {"totalFrames": True, "scenes": [{}]},
        {"totalFrames": 300, "scenes": []},
        {"totalFrames": 300, "scenes": "not a list"},
        {"totalFrames": 300},
    ],
)
def test_write_scene_config_rejects_malformed_config(job_db, bad_config):
    job_db("vid_bad_config")

    result = server.write_scene_config("vid_bad_config", bad_config)

    assert "error" in result
    assert not (server.JOBS_DIR / "vid_bad_config").exists()
