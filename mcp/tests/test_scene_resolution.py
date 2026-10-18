"""Tests for the generated/ vs installed/ scene resolution surface added for
scene persistence + the reusable scene library (list_scene_files, validate_job).

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def scene_dirs(tmp_path, monkeypatch):
    """Point SCENES_DIR (generated) and INSTALLED_DIR at isolated temp dirs."""
    generated = tmp_path / "generated"
    installed = tmp_path / "installed"
    generated.mkdir()
    installed.mkdir()
    monkeypatch.setattr(server, "SCENES_DIR", generated)
    monkeypatch.setattr(server, "INSTALLED_DIR", installed)
    return generated, installed


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file and return a helper to insert a video row."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()

    def make_video(video_id, voice_file_path, timeline_path, scene_config_path):
        with server._conn() as con:
            con.execute(
                """
                INSERT INTO videos (id, topic, voice_file_path, timeline_path,
                                     scene_config_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, "test topic", str(voice_file_path), str(timeline_path),
                 str(scene_config_path), _now(), _now()),
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


def _write_job_files(tmp_path, scenes):
    """Write a minimal valid audio.mp3 + timeline.json + scene-config.json job triplet."""
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"0" * 60_000)  # > 50KB, passes the size check

    timeline_path = tmp_path / "timeline.json"
    timeline_path.write_text(json.dumps({
        "totalFrames": 300,
        "fps": 30,
        "audioDurationSeconds": 10.0,
        "words": [],
    }))

    scene_config_path = tmp_path / "scene-config.json"
    scene_config_path.write_text(json.dumps({
        "totalFrames": 300,
        "fps": 30,
        "scenes": scenes,
        "sfx": [],
    }))

    return audio_path, timeline_path, scene_config_path


# ── list_scene_files ────────────────────────────────────────────────────────

# These two tests write directly into the flat generated/ dir (bypassing
# write_scene_file, which now always namespaces under a video_id) — they are
# deliberately kept as-is as legacy-flat backward-compat coverage: a
# pre-namespacing file must keep resolving to its bare stem. Namespaced
# coverage lives in test_scene_subfolders.py.

def test_list_scene_files_tags_by_source(scene_dirs):
    generated, installed = scene_dirs
    (generated / "intro-hook.tsx").write_text("export default function X() { return null; }")
    (installed / "StepFlowDiagram.tsx").write_text("export default function Y() { return null; }")

    result = server.list_scene_files()
    assert result == {
        "scenes": [
            {"name": "intro-hook", "source": "generated"},
            {"name": "StepFlowDiagram", "source": "installed"},
        ]
    }


def test_list_scene_files_filters_by_source(scene_dirs):
    generated, installed = scene_dirs
    (generated / "intro-hook.tsx").write_text("x")
    (installed / "StepFlowDiagram.tsx").write_text("x")

    assert server.list_scene_files(source="generated") == {
        "scenes": [{"name": "intro-hook", "source": "generated"}]
    }
    assert server.list_scene_files(source="installed") == {
        "scenes": [{"name": "StepFlowDiagram", "source": "installed"}]
    }


def test_list_scene_files_empty_dirs(scene_dirs):
    assert server.list_scene_files() == {"scenes": []}


def test_list_scene_files_rejects_invalid_source(scene_dirs):
    result = server.list_scene_files(source="bogus")
    assert "error" in result


# ── validate_job — scene existence check, source-aware ─────────────────────

def test_validate_job_generated_scene_found(tmp_path, scene_dirs, job_db):
    generated, _installed = scene_dirs
    (generated / "intro-hook.tsx").write_text("x")

    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_test1", audio, timeline, scene_config)

    result = server.validate_job("vid_test1")
    assert not any("not found" in e for e in result["errors"])


def test_validate_job_installed_scene_found(tmp_path, scene_dirs, job_db):
    _generated, installed = scene_dirs
    (installed / "StepFlowDiagram.tsx").write_text("x")

    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": "StepFlowDiagram", "source": "installed",
         "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_test2", audio, timeline, scene_config)

    result = server.validate_job("vid_test2")
    assert not any("not found" in e for e in result["errors"])


def test_validate_job_installed_scene_missing_fails_with_hint(tmp_path, scene_dirs, job_db):
    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": "NoSuchScene", "source": "installed",
         "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_test3", audio, timeline, scene_config)

    result = server.validate_job("vid_test3")
    errors = " ".join(result["errors"])
    assert "NoSuchScene" in errors
    assert "source=installed" in errors
    assert "list_scene_files(source='installed')" in errors


def test_validate_job_generated_scene_missing_fails_with_hint(tmp_path, scene_dirs, job_db):
    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": "never-written", "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_test4", audio, timeline, scene_config)

    result = server.validate_job("vid_test4")
    errors = " ".join(result["errors"])
    assert "never-written" in errors
    assert "source=generated" in errors
    assert "write_scene_file" in errors


# ── write_scene_file / delete_scene_file — still generated-only ────────────

def test_write_scene_file_only_writes_generated(scene_dirs, job_db):
    generated, installed = scene_dirs
    job_db("vid_test5", "a", "b", "c")
    result = server.write_scene_file("vid_test5", "my-scene", "export default function() { return null; }")
    assert (generated / "vid_test5" / "my-scene.tsx").exists()
    assert not (installed / "my-scene.tsx").exists()
    assert result["scene_name"] == "my-scene"
    assert result["src"] == "vid_test5/my-scene"


def test_delete_scene_file_only_affects_generated(scene_dirs):
    # Legacy-flat backward-compat coverage: video_id omitted deletes a
    # pre-namespacing flat file, and installed/ stays untouched either way.
    generated, installed = scene_dirs
    (generated / "my-scene.tsx").write_text("x")
    (installed / "my-scene.tsx").write_text("x")  # same stem, different dir

    result = server.delete_scene_file("my-scene")
    assert result == {"deleted": True, "scene_name": "my-scene", "video_id": ""}
    assert not (generated / "my-scene.tsx").exists()
    assert (installed / "my-scene.tsx").exists()  # untouched
