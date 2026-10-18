"""Tests for TMDEV-61 follow-up: generated scene TSX moved from one shared
directory (generated/{scene_name}.tsx) to per-video subfolders
(generated/{video_id}/{scene_name}.tsx). Two videos naming a scene the same
thing used to silently overwrite each other's TSX — the render would then
succeed but use the wrong scene, a silently wrong video rather than a failed
one. Namespacing closes that both for concurrent writes and for the sequential
case (weeks apart) that a video_id-keyed lock alone could never fix.

Legacy flat-file backward compatibility lives in test_scene_resolution.py.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def scene_dirs(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    installed = tmp_path / "installed"
    generated.mkdir()
    installed.mkdir()
    monkeypatch.setattr(server, "SCENES_DIR", generated)
    monkeypatch.setattr(server, "INSTALLED_DIR", installed)
    return generated, installed


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()

    def make_video(video_id, voice_file_path="a", timeline_path="b", scene_config_path="c"):
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


# ── write_scene_file ─────────────────────────────────────────────────────────

def test_write_scene_file_writes_into_video_subfolder(scene_dirs, job_db):
    generated, _installed = scene_dirs
    job_db("vid_a")
    server.write_scene_file("vid_a", "intro-hook", "x")
    assert (generated / "vid_a" / "intro-hook.tsx").exists()
    assert not (generated / "intro-hook.tsx").exists()


def test_write_scene_file_returns_composed_src(scene_dirs, job_db):
    job_db("vid_a")
    result = server.write_scene_file("vid_a", "intro-hook", "x")
    assert result["src"] == "vid_a/intro-hook"
    assert result["video_id"] == "vid_a"
    assert result["scene_name"] == "intro-hook"


def test_write_scene_file_same_name_different_videos_do_not_collide(scene_dirs, job_db):
    """The regression test for the ticket: two videos both naming a scene
    'intro-hook' must not overwrite each other."""
    generated, _installed = scene_dirs
    job_db("vid_a")
    job_db("vid_b")
    server.write_scene_file("vid_a", "intro-hook", "export default () => 'A';")
    server.write_scene_file("vid_b", "intro-hook", "export default () => 'B';")

    assert (generated / "vid_a" / "intro-hook.tsx").read_text() == "export default () => 'A';"
    assert (generated / "vid_b" / "intro-hook.tsx").read_text() == "export default () => 'B';"


def test_write_scene_file_rejects_unknown_video(scene_dirs, job_db):
    generated, _installed = scene_dirs
    result = server.write_scene_file("vid_nope", "intro-hook", "x")
    assert result == {"error": "Video not found: vid_nope"}
    assert not any(generated.iterdir())


@pytest.mark.parametrize("bad_name", ["", "foo/bar", "../x", "foo_bar", "-lead", "with space"])
def test_write_scene_file_rejects_bad_scene_name(scene_dirs, job_db, bad_name):
    job_db("vid_a")
    result = server.write_scene_file("vid_a", bad_name, "x")
    assert "error" in result


def test_write_scene_file_video_id_is_the_traversal_guard(scene_dirs, job_db):
    generated, _installed = scene_dirs
    result = server.write_scene_file("../../etc", "intro-hook", "x")
    assert "error" in result
    # Nothing written outside SCENES_DIR's temp root.
    assert not any(generated.parent.glob("**/intro-hook.tsx"))


def test_write_scene_file_overwrites_within_the_same_video(scene_dirs, job_db):
    generated, _installed = scene_dirs
    job_db("vid_a")
    server.write_scene_file("vid_a", "intro-hook", "v1")
    server.write_scene_file("vid_a", "intro-hook", "v2")
    assert (generated / "vid_a" / "intro-hook.tsx").read_text() == "v2"


# ── list_scene_files ─────────────────────────────────────────────────────────

def test_list_scene_files_composes_nested_generated_names(scene_dirs, job_db):
    job_db("vid_a")
    server.write_scene_file("vid_a", "intro-hook", "x")
    result = server.list_scene_files(source="generated")
    assert result["scenes"] == [{"name": "vid_a/intro-hook", "source": "generated"}]


def test_list_scene_files_still_lists_legacy_flat_generated(scene_dirs):
    generated, _installed = scene_dirs
    (generated / "legacy.tsx").write_text("x")
    result = server.list_scene_files(source="generated")
    assert result["scenes"] == [{"name": "legacy", "source": "generated"}]


def test_list_scene_files_filters_by_video_id(scene_dirs, job_db):
    job_db("vid_a")
    job_db("vid_b")
    server.write_scene_file("vid_a", "intro-hook", "x")
    server.write_scene_file("vid_b", "outro", "x")
    result = server.list_scene_files(source="generated", video_id="vid_a")
    assert result["scenes"] == [{"name": "vid_a/intro-hook", "source": "generated"}]


def test_list_scene_files_video_id_filter_does_not_hide_installed(scene_dirs, job_db):
    _generated, installed = scene_dirs
    (installed / "StepFlowDiagram.tsx").write_text("x")
    job_db("vid_a")
    server.write_scene_file("vid_a", "intro-hook", "x")
    result = server.list_scene_files(source="all", video_id="vid_a")
    assert {"name": "StepFlowDiagram", "source": "installed"} in result["scenes"]
    assert {"name": "vid_a/intro-hook", "source": "generated"} in result["scenes"]
    assert len(result["scenes"]) == 2


def test_list_scene_files_installed_stays_flat(scene_dirs):
    _generated, installed = scene_dirs
    (installed / "StepFlowDiagram.tsx").write_text("x")
    result = server.list_scene_files(source="installed")
    assert result["scenes"] == [{"name": "StepFlowDiagram", "source": "installed"}]


def test_list_scene_files_caps_and_flags_truncation_with_no_filter(scene_dirs, job_db):
    job_db("vid_a")
    for i in range(55):
        server.write_scene_file("vid_a", f"scene{i:02d}", "x")
    result = server.list_scene_files(source="generated")
    assert len(result["scenes"]) == 50
    assert result["truncated"] is True


def test_list_scene_files_video_id_filter_is_not_truncated(scene_dirs, job_db):
    job_db("vid_a")
    for i in range(55):
        server.write_scene_file("vid_a", f"scene{i:02d}", "x")
    result = server.list_scene_files(source="generated", video_id="vid_a")
    assert len(result["scenes"]) == 55
    assert "truncated" not in result


# ── delete_scene_file ────────────────────────────────────────────────────────

def test_delete_scene_file_with_video_id_deletes_from_subfolder(scene_dirs, job_db):
    generated, _installed = scene_dirs
    job_db("vid_a")
    server.write_scene_file("vid_a", "intro-hook", "x")
    result = server.delete_scene_file("intro-hook", video_id="vid_a")
    assert result == {"deleted": True, "scene_name": "intro-hook", "video_id": "vid_a"}
    assert not (generated / "vid_a" / "intro-hook.tsx").exists()


def test_delete_scene_file_scoped_to_one_video(scene_dirs, job_db):
    generated, _installed = scene_dirs
    job_db("vid_a")
    job_db("vid_b")
    server.write_scene_file("vid_a", "intro-hook", "A")
    server.write_scene_file("vid_b", "intro-hook", "B")

    server.delete_scene_file("intro-hook", video_id="vid_a")
    assert not (generated / "vid_a" / "intro-hook.tsx").exists()
    assert (generated / "vid_b" / "intro-hook.tsx").read_text() == "B"


def test_delete_scene_file_not_found_returns_error_not_raise(scene_dirs, job_db):
    job_db("vid_a")
    result = server.delete_scene_file("nope", video_id="vid_a")
    assert result == {"error": "not found", "scene_name": "nope", "video_id": "vid_a"}


# ── validate_job — composed src, malformed src, stale-flat-src guard ────────

def test_validate_job_resolves_composed_src(tmp_path, scene_dirs, job_db):
    generated, _installed = scene_dirs
    (generated / "vid_a").mkdir()
    (generated / "vid_a" / "intro-hook.tsx").write_text("x")

    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": "vid_a/intro-hook", "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_a", audio, timeline, scene_config)

    result = server.validate_job("vid_a")
    assert not any("not found" in e for e in result["errors"])
    assert not any("malformed" in e for e in result["errors"])


def test_validate_job_still_resolves_legacy_flat_src(tmp_path, scene_dirs, job_db):
    generated, _installed = scene_dirs
    (generated / "intro-hook.tsx").write_text("x")

    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_a", audio, timeline, scene_config)

    result = server.validate_job("vid_a")
    assert not any("not found" in e for e in result["errors"])
    assert not any("stale" in e for e in result["errors"])


@pytest.mark.parametrize("bad_src", ["../../secrets", "a/b/c", "generated/vid_x/foo"])
def test_validate_job_rejects_malformed_src_shape(tmp_path, scene_dirs, job_db, bad_src):
    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        {"type": "generated", "src": bad_src, "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_a", audio, timeline, scene_config)

    result = server.validate_job("vid_a")
    errors = " ".join(result["errors"])
    assert "malformed" in errors
    # A shape error, not a confusing "not found" against a bogus nested path.
    assert "not found" not in errors


def test_validate_job_flags_stale_flat_src_shadowed_by_a_video_scoped_file(tmp_path, scene_dirs, job_db):
    generated, _installed = scene_dirs
    (generated / "intro-hook.tsx").write_text("old shared version")
    (generated / "vid_a").mkdir()
    (generated / "vid_a" / "intro-hook.tsx").write_text("new namespaced version")

    audio, timeline, scene_config = _write_job_files(tmp_path, scenes=[
        # Stale config still points at the flat legacy src, even though this
        # video now has its own namespaced scene of the same name.
        {"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 300},
    ])
    job_db("vid_a", audio, timeline, scene_config)

    result = server.validate_job("vid_a")
    errors = " ".join(result["errors"])
    assert "stale" in errors
    assert "vid_a/intro-hook" in errors


def test_write_scene_file_src_round_trips_through_write_scene_config_and_validate_job(
    tmp_path, scene_dirs, job_db, monkeypatch,
):
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path)

    # generate_voice's timeline.json/audio.mp3 are a prerequisite for
    # validate_job; scene_config_path is left unset here — write_scene_config
    # (called below) fills it in.
    (tmp_path / "vid_a").mkdir()
    timeline_path = tmp_path / "vid_a" / "timeline.json"
    timeline_path.write_text(json.dumps({
        "totalFrames": 300, "fps": 30, "audioDurationSeconds": 10.0, "words": [],
    }))
    audio_path = tmp_path / "vid_a" / "audio.mp3"
    audio_path.write_bytes(b"0" * 60_000)
    job_db("vid_a", voice_file_path=audio_path, timeline_path=timeline_path, scene_config_path="")

    written = server.write_scene_file("vid_a", "intro-hook", "x")
    config = {
        "totalFrames": 300,
        "fps": 30,
        "scenes": [{"type": "generated", "src": written["src"],
                    "startFrame": 0, "durationInFrames": 300}],
        "sfx": [],
    }
    server.write_scene_config("vid_a", config)

    result = server.validate_job("vid_a")
    assert not any("not found" in e or "malformed" in e or "stale" in e for e in result["errors"])
