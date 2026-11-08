"""Cartoon 3D modules through write_scene_file, read_scene_file,
list_scene_files and delete_scene_file (TMDEV-185, Codex round 1).

A module is written atomically, so a failed write leaves the last good file;
a queued or rendering video's source is frozen; and a composed module name
('<video_id>/sets/street.ts', what list_scene_files hands out) means the same
thing to read and delete, with a conflicting explicit video_id an error rather
than a silent subdirectory.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""
import os
from datetime import datetime, timezone

import pytest

import server

ENTRY = "export default () => null;\n"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def clear_claims():
    server._scene_claims.clear()
    yield
    server._scene_claims.clear()


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()

    def make_video(video_id, status="VOICE_READY"):
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, created_at, updated_at) VALUES (?, NULL, ?, ?, ?, ?)",
                        (video_id, "t", status, _now(), _now()))

    def set_status(video_id, status):
        with server._conn() as con:
            con.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))
    make_video.set_status = set_status
    return make_video


@pytest.fixture
def scenes(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    generated.mkdir()
    monkeypatch.setattr(server, "SCENES_DIR", generated)
    monkeypatch.setattr(server, "INSTALLED_DIR", tmp_path / "installed")
    return generated


def _author(video_id):
    assert "error" not in server.write_scene_file(video_id, "CartoonShort", ENTRY)
    assert "error" not in server.write_scene_file(video_id, "story.ts", "export const TOTAL = 100;")
    assert "error" not in server.write_scene_file(video_id, "sets/street.ts", "export const STREET = 1;")


def test_a_queued_or_rendering_videos_source_is_frozen(job_db, scenes):
    job_db("vid-a")
    _author("vid-a")
    for status in ("RENDER_QUEUED", "RENDERING"):
        job_db.set_status("vid-a", status)
        result = server.write_scene_file("vid-a", "story.ts", "export const TOTAL = 1;")
        assert result["error"] == "status_mismatch" and result["current_status"] == status and "frozen" not in result["detail"]
        assert "cannot change now" in result["detail"]
        assert (scenes / "vid-a" / "story.ts").read_text() == "export const TOTAL = 100;"
    job_db.set_status("vid-a", "REVISION_REQUESTED")
    assert "error" not in server.write_scene_file("vid-a", "story.ts", "export const TOTAL = 1;")
    assert (scenes / "vid-a" / "story.ts").read_text() == "export const TOTAL = 1;"


def test_a_write_that_fails_leaves_the_last_good_file_and_no_leftovers(job_db, scenes, monkeypatch):
    job_db("vid-a")
    _author("vid-a")
    real_replace = os.replace

    def full_disk(src, dst):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(server.os, "replace", full_disk)
    result = server.write_scene_file("vid-a", "sets/street.ts", "export const STREET = 2;")
    assert result == {"error": "vid-a/sets/street.ts could not be written: [Errno 28] No space left on device"}
    assert (scenes / "vid-a" / "sets" / "street.ts").read_text() == "export const STREET = 1;"
    assert sorted(p.name for p in (scenes / "vid-a" / "sets").iterdir()) == ["street.ts"]      # the temp file is gone
    monkeypatch.setattr(server.os, "replace", real_replace)
    assert "error" not in server.write_scene_file("vid-a", "sets/street.ts", "export const STREET = 2;")
    assert (scenes / "vid-a" / "sets" / "street.ts").read_text() == "export const STREET = 2;"
    assert sorted(p.name for p in (scenes / "vid-a" / "sets").iterdir()) == ["street.ts"]


def test_listed_module_names_read_and_delete_as_listed(job_db, scenes):
    job_db("vid-a")
    _author("vid-a")
    listed = [s["name"] for s in server.list_scene_files(source="generated", video_id="vid-a")["scenes"]]
    assert listed == ["vid-a/CartoonShort", "vid-a/sets/street.ts", "vid-a/story.ts"]
    assert server.read_scene_file("vid-a/story.ts")["tsx_content"] == "export const TOTAL = 100;"
    assert server.read_scene_file("vid-a/sets/street.ts")["tsx_content"] == "export const STREET = 1;"
    assert server.read_scene_file("vid-a/sets/street.ts", video_id="vid-a")["tsx_content"] == "export const STREET = 1;"
    assert server.read_scene_file("sets/street.ts", video_id="vid-a")["tsx_content"] == "export const STREET = 1;"
    assert server.read_scene_file("story.ts", video_id="vid-a")["src"] == "vid-a/story.ts"
    assert server.delete_scene_file("vid-a/sets/street.ts") == {"deleted": True, "scene_name": "vid-a/sets/street.ts", "video_id": "vid-a"}
    assert server.delete_scene_file("vid-a/story.ts") == {"deleted": True, "scene_name": "vid-a/story.ts", "video_id": "vid-a"}
    assert not (scenes / "vid-a" / "story.ts").exists() and not (scenes / "vid-a" / "sets" / "street.ts").exists()
    assert server.delete_scene_file("story.ts", video_id="vid-a")["error"] == "not found"


def test_a_composed_name_with_another_video_id_is_a_conflict_not_a_subdirectory(job_db, scenes):
    job_db("vid-a")
    job_db("vid-b")
    _author("vid-a")
    _author("vid-b")
    for name in ("vid-a/story.ts", "vid-a/sets/street.ts"):
        for tool in (server.read_scene_file, server.delete_scene_file):
            result = tool(name, video_id="vid-b")
            assert "conflicting video_id" in result["error"] and "'vid-a'" in result["error"], (tool.__name__, name)
    assert (scenes / "vid-a" / "story.ts").exists() and (scenes / "vid-a" / "sets" / "street.ts").exists()
    # a subdirectory that is not some video's source tree is just a subdirectory
    assert server.read_scene_file("sets/street.ts", video_id="vid-b")["src"] == "vid-b/sets/street.ts"
    assert server.read_scene_file("nowhere/street.ts", video_id="vid-b")["error"].startswith("scene file not found")
    # a module needs its video one way or the other
    assert "pass its video_id" in server.read_scene_file("story.ts")["error"]
    assert "pass its video_id" in server.delete_scene_file("story.ts")["error"]
    assert "must be a Cartoon 3D module" in server.read_scene_file("vid-a/sets/deep/street.ts")["error"]
