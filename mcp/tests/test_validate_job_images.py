"""Tests for validate_job's image-reference checks (TMDEV-29).

An image src that doesn't resolve is not a blank frame — Remotion's <Img>
retries twice and then calls cancelRender(), failing the whole render. These
checks exist so that mistake is caught before a render cycle is burned.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pytest

import server

VID = "vid-1"


@pytest.fixture
def jobs_dir(tmp_path, monkeypatch):
    """Point JOBS_DIR at a throwaway tree and return a helper that materialises
    an image file for this video."""
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path)

    def make_image(name):
        d = tmp_path / VID / "images"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    return make_image


def _config(props):
    return {"scenes": [{"type": "generated", "src": "hero", "props": props}]}


# ── The happy path ────────────────────────────────────────────────────────────

def test_existing_image_passes(jobs_dir):
    jobs_dir("skyline.png")
    cfg = _config({"src": f"/public/{VID}/images/skyline.png"})
    assert server._bad_image_refs(cfg, VID) == []


def test_missing_image_is_flagged(jobs_dir):
    cfg = _config({"src": f"/public/{VID}/images/skyline.png"})
    errors = server._bad_image_refs(cfg, VID)
    assert len(errors) == 1
    assert "does not exist" in errors[0]
    assert "generate_image" in errors[0]


# ── The shapes an agent actually gets wrong ───────────────────────────────────

def test_container_path_is_flagged(jobs_dir):
    """/jobs/<vid>/... is the natural wrong guess: every path the agent sees via
    get_video is container-absolute. The file existing changes nothing — the
    renderer serves images over HTTP, not from the filesystem."""
    jobs_dir("skyline.png")
    cfg = _config({"src": f"/jobs/{VID}/images/skyline.png"})
    errors = server._bad_image_refs(cfg, VID)
    assert len(errors) == 1
    assert "not a served path" in errors[0]


def test_bare_relative_path_is_flagged(jobs_dir):
    jobs_dir("skyline.png")
    cfg = _config({"src": "images/skyline.png"})
    assert len(server._bad_image_refs(cfg, VID)) == 1


def test_right_video_but_outside_images_dir_is_flagged(jobs_dir):
    """Only <vid>/images/ is staged into the served tree, so an image sitting
    directly under the video's public prefix still 404s — and it is this
    video's, so it must not be reported as another video's."""
    cfg = _config({"src": f"/public/{VID}/skyline.png"})
    errors = server._bad_image_refs(cfg, VID)
    assert len(errors) == 1
    assert "not a served path" in errors[0]
    assert "another video" not in errors[0]


def test_other_videos_image_is_flagged(jobs_dir):
    cfg = _config({"src": "/public/some-other-vid/images/skyline.png"})
    errors = server._bad_image_refs(cfg, VID)
    assert len(errors) == 1
    assert "another video" in errors[0]


# ── Where the path can hide ───────────────────────────────────────────────────

def test_image_nested_in_a_list_is_found(jobs_dir):
    cfg = _config({"slides": [{"img": f"/public/{VID}/images/a.png"}]})
    assert len(server._bad_image_refs(cfg, VID)) == 1


def test_found_regardless_of_prop_name(jobs_dir):
    """Props are free-form (z.record(z.unknown())), so matching is by path
    shape, not by a conventional key name."""
    cfg = _config({"whateverKeyTheAgentPicked": f"/public/{VID}/images/a.png"})
    assert len(server._bad_image_refs(cfg, VID)) == 1


# ── The hint names only a tool that exists ───────────────────────────────────

def test_the_hint_does_not_name_the_removed_gif_tool(jobs_dir):
    cfg = _config({"src": f"/public/{VID}/images/a.png"})
    errors = server._bad_image_refs(cfg, VID)
    assert len(errors) == 1
    assert "generate_image" in errors[0]
    assert "write_gif_script" not in errors[0]


# ── Deliberate scope limits ───────────────────────────────────────────────────

def test_correctly_scoped_music_is_not_flagged(jobs_dir):
    """Only images are checked. music.mp3 under the right prefix is left alone
    — it is separately broken (never staged by worker.py) and surfacing that
    here would be an unrelated failure."""
    cfg = _config({"music": f"/public/{VID}/music.mp3"})
    assert server._bad_image_refs(cfg, VID) == []


def test_ordinary_strings_are_ignored(jobs_dir):
    cfg = _config({"caption": "Every request starts here", "color": "#0a0a0f"})
    assert server._bad_image_refs(cfg, VID) == []


def test_non_generated_scenes_are_skipped(jobs_dir):
    cfg = {"scenes": [{"type": "TextReveal", "props": {"src": "/nope/x.png"}}]}
    assert server._bad_image_refs(cfg, VID) == []


def test_scene_without_props_is_safe(jobs_dir):
    assert server._bad_image_refs({"scenes": [{"type": "generated", "src": "a"}]}, VID) == []


def test_extension_match_is_case_insensitive(jobs_dir):
    cfg = _config({"src": "images/Skyline.PNG"})
    assert len(server._bad_image_refs(cfg, VID)) == 1


def test_non_object_scene_config_adds_no_image_error(jobs_dir, tmp_path, monkeypatch):
    """A scene-config that parsed but isn't an object already yields one
    "'list' object has no attribute 'get'" line per pre-existing check; the
    image check must not pile on a fourth copy of the same message."""
    from datetime import datetime, timezone

    monkeypatch.setattr(server, "DB_FILE", tmp_path / "t.db")
    server._init_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = tmp_path / VID
    job.mkdir(parents=True, exist_ok=True)
    (job / "audio.mp3").write_bytes(b"x" * 60000)
    (job / "timeline.json").write_text(
        '{"totalFrames":50,"fps":30,"audioDurationSeconds":1.67,"words":[]}')
    (job / "scene-config.json").write_text("[]")
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, topic, voice_file_path, timeline_path, "
            "scene_config_path, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (VID, "t", str(job / "audio.mp3"), str(job / "timeline.json"),
             str(job / "scene-config.json"), now, now))

    errors = server.validate_job(VID)["errors"]

    assert not any("Image reference check failed" in e for e in errors)


def test_malformed_scene_config_adds_no_image_error(jobs_dir, tmp_path, monkeypatch):
    """When the JSON doesn't parse at all, scene_config is never bound — the
    image check must skip rather than report a confusing internal error."""
    from datetime import datetime, timezone

    monkeypatch.setattr(server, "DB_FILE", tmp_path / "t.db")
    server._init_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = tmp_path / VID
    job.mkdir(parents=True, exist_ok=True)
    (job / "audio.mp3").write_bytes(b"x" * 60000)
    (job / "timeline.json").write_text(
        '{"totalFrames":50,"fps":30,"audioDurationSeconds":1.67,"words":[]}')
    (job / "scene-config.json").write_text("{ not json")
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, topic, voice_file_path, timeline_path, "
            "scene_config_path, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (VID, "t", str(job / "audio.mp3"), str(job / "timeline.json"),
             str(job / "scene-config.json"), now, now))

    errors = server.validate_job(VID)["errors"]

    assert not any("Image reference check" in e for e in errors)
