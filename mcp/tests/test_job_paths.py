"""Ids that become paths, and the job-path fields update_video no longer takes
(TMDEV-158/159/161/162).

Every tool that builds a path from a video_id checks its shape first, so no
tool depends on another guard (a row lookup) being present: delete_scene_file
had none, and an absolute video_id replaced SCENES_DIR outright. Each refusal
sits next to a working control, because a check that refuses a real id shape
breaks the pipeline just as surely as a missing one opens it.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest

import server

BAD_VIDEO_IDS = ["../x", "/tmp/x", "a/b", "a\\b", "..", ".", "x" * 256, "abc\n", "a\0b"]
# Filed before the creation rule existed. Checked as a path component at use,
# as tubematic_core/ids.py promises, so they keep working at every tool. The
# 128-character cap arrived with that rule, so a longer id is legacy too.
LEGACY_VIDEO_IDS = ["a.b", "Spaced Name", "x" * 129]
PATH_FIELDS = ["voice_file_path", "timeline_path", "scene_config_path", "video_path"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")
    (tmp_path / "generated").mkdir()
    server._init_db()
    return tmp_path


def _video(vid, status="VOICE_READY"):
    with server._conn() as con:
        con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at)"
                    " VALUES (?, 'T', ?, ?, ?)", (vid, status, _now(), _now()))


def _call(tool, **arguments):
    """Over a real client, as an agent calls it — the only way to see what
    FastMCP does with an argument the tool does not declare."""
    from fastmcp import Client

    async def go():
        async with Client(server.mcp) as client:
            return await client.call_tool(tool, arguments, raise_on_error=False)
    return asyncio.run(go())


# ── update_video: the path fields are gone ──────────────────────────────────

def test_update_video_no_longer_declares_the_path_fields():
    import inspect
    params = inspect.signature(server.update_video).parameters
    assert not set(PATH_FIELDS) & set(params)


@pytest.mark.parametrize("field", PATH_FIELDS)
def test_update_video_refuses_a_path_field_and_applies_nothing(db, field):
    _video("vid_a", status="VOICE_READY")
    result = _call("update_video", video_id="vid_a", gemini_feedback="changed",
                   **{field: "/jobs/vid_b/x"})
    assert result.is_error
    with server._conn() as con:
        row = con.execute("SELECT * FROM videos WHERE id = 'vid_a'").fetchone()
    assert row[field] == ""
    assert row["gemini_feedback"] == ""


def test_update_video_without_a_path_field_still_works(db):
    _video("vid_a")
    result = _call("update_video", video_id="vid_a", gemini_feedback="changed")
    assert not result.is_error


# ── every path-building tool checks the id's shape ──────────────────────────

TOOLS = [
    ("generate_voice", lambda v: server.generate_voice(v, "x")),
    ("generate_image", lambda v: server.generate_image(v, "img", "a prompt")),
    ("generate_character", lambda v: server.generate_character(v, "hero", "a prompt")),
    ("read_image", lambda v: server.read_image(v, "img")),
    ("write_scene_file", lambda v: server.write_scene_file(v, "intro", "x")),
    ("write_scene_config", lambda v: server.write_scene_config(v, {"totalFrames": 1})),
    ("get_timeline", lambda v: server.get_timeline(v)),
    ("get_scene_config", lambda v: server.get_scene_config(v)),
    ("validate_job", lambda v: server.validate_job(v)),
    ("read_scene_file", lambda v: server.read_scene_file("intro", video_id=v)),
    ("delete_scene_file", lambda v: server.delete_scene_file("intro", video_id=v)),
]


@pytest.mark.parametrize("name,call", TOOLS, ids=[t[0] for t in TOOLS])
@pytest.mark.parametrize("bad", BAD_VIDEO_IDS + [7])
def test_every_path_tool_refuses_a_malformed_video_id(db, name, call, bad):
    result = call(bad)
    assert "not a valid video id" in json.dumps(result)


@pytest.mark.parametrize("name,call", TOOLS, ids=[t[0] for t in TOOLS])
@pytest.mark.parametrize("legacy", LEGACY_VIDEO_IDS)
def test_every_path_tool_accepts_a_legacy_video_id(db, name, call, legacy):
    _video(legacy)
    result = call(legacy)
    assert "not a valid video id" not in json.dumps(result)


@pytest.mark.parametrize("legacy", LEGACY_VIDEO_IDS)
def test_a_legacy_video_is_usable_end_to_end(db, legacy):
    """Its job files sit at the derived path, a scene lands in its own
    directory, and the composed src validate_job checks is accepted."""
    _video(legacy)
    job = db / "jobs" / legacy
    job.mkdir(parents=True)
    (job / "timeline.json").write_text(json.dumps(
        {"totalFrames": 30, "fps": 30, "segments": [], "words": []}))
    assert "error" not in server.get_timeline(legacy)
    written = server.write_scene_file(legacy, "intro", "export const X = 1;")
    assert written["src"] == f"{legacy}/intro"
    assert (db / "generated" / legacy / "intro.tsx").is_file()
    assert server._check_scene_src(written["src"]) is None
    assert server.read_scene_file(written["src"])["tsx_content"] == "export const X = 1;"


@pytest.mark.parametrize("src", ["../intro", "./intro", "a\\b/intro", "a\nb/intro",
                                 "x" * 256 + "/intro", "/intro"])
def test_a_scene_src_whose_video_segment_is_unusable_is_refused(src):
    assert server._check_scene_src(src) is not None


@pytest.mark.parametrize("good", ["vid_0123456789ab", str(uuid.uuid4())])
def test_real_video_ids_pass_the_shape_check(db, good):
    _video(good)
    result = server.write_scene_file(good, "intro", "export const X = 1;")
    assert "error" not in result


def test_a_scene_name_with_no_room_for_its_tsx_is_refused_cleanly(db):
    """`<name>.tsx` must fit in a file name. 252 bytes plus the suffix is 256:
    a clean refusal, not an ENAMETOOLONG from the write."""
    _video("vid_a")
    result = server.write_scene_file("vid_a", "x" * 252, "export const X = 1;")
    assert "bytes" in result["error"]
    assert not (db / "generated" / "vid_a").exists()
    written = server.write_scene_file("vid_a", "x" * 251, "export const X = 1;")
    assert (db / "generated" / "vid_a" / f"{'x' * 251}.tsx").is_file()
    assert server.read_scene_file(written["src"])["tsx_content"] == "export const X = 1;"


# ── delete_scene_file (TMDEV-161) ───────────────────────────────────────────

@pytest.mark.parametrize("vid", ["../outside", "OUTSIDE_ABS"])
def test_delete_scene_file_cannot_reach_outside_the_scenes_dir(db, vid):
    outside = db / "outside"
    outside.mkdir()
    marker = outside / "intro.tsx"
    marker.write_text("keep me")
    if vid == "OUTSIDE_ABS":
        vid = str(outside)
    result = server.delete_scene_file("intro", video_id=vid)
    assert "error" in result
    assert marker.read_text() == "keep me"


def test_delete_scene_file_still_deletes_a_video_scene(db):
    _video("vid_a")
    server.write_scene_file("vid_a", "intro", "x")
    assert server.delete_scene_file("intro", video_id="vid_a") == {
        "deleted": True, "scene_name": "intro", "video_id": "vid_a"}


def test_delete_scene_file_still_deletes_a_legacy_flat_scene(db):
    (db / "generated" / "intro.tsx").write_text("x")
    assert server.delete_scene_file("intro")["deleted"] is True


def test_delete_scene_file_refuses_a_symlinked_video_dir(db):
    outside = db / "outside"
    outside.mkdir()
    (outside / "intro.tsx").write_text("keep me")
    (db / "generated" / "vid_a").symlink_to(outside)
    result = server.delete_scene_file("intro", video_id="vid_a")
    assert "error" in result
    assert (outside / "intro.tsx").exists()


# ── validate_job reads the derived files ────────────────────────────────────

def test_validate_job_never_reads_a_planted_path(db):
    """A row tampered with before the fix names a file outside the job dir.
    validate_job looks only at JOBS_DIR/<id>/, so it reports the job missing
    rather than parsing (and quoting back) whatever the row names."""
    planted = db / "secret.json"
    planted.write_text('{"totalFrames": 1}')
    with server._conn() as con:
        con.execute("INSERT INTO videos (id, topic, voice_file_path, timeline_path,"
                    " scene_config_path, created_at, updated_at)"
                    " VALUES ('vid_a', 'T', ?, ?, ?, ?, ?)",
                    (str(planted), str(planted), str(planted), _now(), _now()))
    result = server.validate_job("vid_a")
    assert result["passed"] is False
    assert all(str(planted) not in e for e in result["errors"])
    assert any("Missing audio.mp3" in e for e in result["errors"])


def test_validate_job_refuses_a_symlinked_job_file(db):
    _video("vid_a")
    (db / "jobs" / "vid_a").mkdir(parents=True)
    secret = db / "secret.json"
    secret.write_text("{}")
    (db / "jobs" / "vid_a" / "timeline.json").symlink_to(secret)
    result = server.validate_job("vid_a")
    assert result["passed"] is False
    assert "symlink" in " ".join(result["errors"])


def test_an_image_reference_cannot_probe_outside_the_images_dir(db):
    (db / "jobs" / "vid_a" / "images").mkdir(parents=True)
    (db / "jobs" / "vid_a" / "audio.mp3").write_bytes(b"x")
    config = {"scenes": [{"type": "generated", "src": "s",
                          "props": {"img": "/public/vid_a/images/../audio.mp3"}}]}
    errors = server._bad_image_refs(config, "vid_a")
    assert len(errors) == 1 and "does not exist" in errors[0]


# ── upsert_project: a new id must be a segment ──────────────────────────────

@pytest.mark.parametrize("bad", ["../x", "/tmp/x", "a/b", "..", "x" * 129, "node.js"])
def test_upsert_project_refuses_a_new_id_that_is_not_a_segment(db, bad):
    result = server.upsert_project(bad, "Name")
    assert "not a valid id" in result["error"]
    with server._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


@pytest.mark.parametrize("good", ["proj_0123abcd", "manual", "linux-internals"])
def test_upsert_project_accepts_the_real_id_shapes(db, good):
    assert server.upsert_project(good, "Name")["id"] == good


def test_a_legacy_domain_with_an_odd_id_stays_editable(db):
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, created_at) VALUES ('node.js', 'N', ?)",
                    (_now(),))
    result = server.upsert_project("node.js", "Renamed")
    assert "error" not in result
    assert result["name"] == "Renamed"


# ── a directory symlinked to another video's, inside the root ───────────────
# vid_a -> vid_b stays inside jobs/ (or generated/), so containment alone
# passes it and A would read or write B's files. Every tool goes through
# tubematic_core.jobfiles, which refuses a symlink in any component.

@pytest.fixture
def linked(db, monkeypatch):
    """jobs/vid_a -> jobs/vid_b and generated/vid_a -> generated/vid_b, with
    vid_b's real files in place. No network call may happen."""
    import httpx

    def _no_network(*a, **kw):
        raise AssertionError("a refused call reached the network")
    monkeypatch.setattr(httpx, "post", _no_network)
    monkeypatch.setattr(httpx, "Client", _no_network)
    monkeypatch.setattr(server, "_gemini_key", lambda: "k")
    monkeypatch.setattr(server, "_openai_key", lambda: "k")
    for vid in ("vid_a", "vid_b"):
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, topic, status, visual_style, created_at,"
                        " updated_at) VALUES (?, 'T', 'VOICE_READY', 'illustrated', ?, ?)",
                        (vid, _now(), _now()))
    job_b = db / "jobs" / "vid_b"
    (job_b / "images").mkdir(parents=True)
    from PIL import Image
    Image.new("RGB", (4, 4), "red").save(job_b / "images" / "x.png")
    with server._conn() as con:
        con.execute("UPDATE videos SET voice_file_path = 'w', timeline_path = 'w',"
                    " scene_config_path = 'w' WHERE id = 'vid_b'")
    (job_b / "audio.mp3").write_bytes(b"B-audio")
    (job_b / "timeline.json").write_text(json.dumps(
        {"totalFrames": 30, "fps": 30, "segments": [], "words": []}))
    (job_b / "scene-config.json").write_text(json.dumps(
        {"totalFrames": 30, "fps": 30, "scenes": [
            {"type": "generated", "src": "vid_a/intro",
             "props": {"img": "/public/vid_a/images/x.png"}}]}))
    (db / "jobs" / "vid_a").symlink_to(job_b)
    (db / "generated" / "vid_b").mkdir()
    (db / "generated" / "vid_b" / "intro.tsx").write_text("B-scene")
    (db / "generated" / "vid_a").symlink_to(db / "generated" / "vid_b")
    return db


def _snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() and not p.is_symlink() else None)
            for p in sorted(root.rglob("*")) if p.name != "test.db" and "test.db" not in p.name}


LINKED_TOOLS = [
    ("read_image", lambda: server.read_image("vid_a", "x")),
    ("generate_image", lambda: server.generate_image("vid_a", "img", "a prompt")),
    ("generate_character", lambda: server.generate_character("vid_a", "hero", "a prompt")),
    ("get_timeline", lambda: server.get_timeline("vid_a")),
    ("get_scene_config", lambda: server.get_scene_config("vid_a")),
    ("write_scene_config", lambda: server.write_scene_config("vid_a", {
        "totalFrames": 30, "fps": 30, "scenes": [{"type": "generated", "src": "vid_a/intro",
                                                  "durationInFrames": 30}]})),
    ("write_scene_file", lambda: server.write_scene_file("vid_a", "intro", "A-scene")),
    ("read_scene_file", lambda: server.read_scene_file("intro", video_id="vid_a")),
    ("read_scene_file composed", lambda: server.read_scene_file("vid_a/intro")),
    ("delete_scene_file", lambda: server.delete_scene_file("intro", video_id="vid_a")),
]


@pytest.mark.parametrize("name,call", LINKED_TOOLS, ids=[t[0] for t in LINKED_TOOLS])
def test_a_video_dir_linked_to_another_videos_is_refused(linked, name, call):
    before = _snapshot(linked)
    result = call()
    text = json.dumps(result, default=str)
    assert "symlink" in text, text
    assert "B-scene" not in text and "B-audio" not in text
    assert _snapshot(linked) == before


def test_validate_job_refuses_a_scene_and_an_image_reached_through_a_link(linked, monkeypatch):
    """validate_job on vid_b (real dirs) whose config names vid_a's scene and
    image: both resolve only through the links, so both are errors."""
    monkeypatch.setenv("PATH", "/nonexistent")  # no npx: skip tsc and the text audit
    errors = " ".join(server.validate_job("vid_b")["errors"])
    assert "vid_a/intro" in errors and "symlink" in errors
    assert any("/public/vid_a/images/x.png" in e
               for e in server._bad_image_refs(
                   {"scenes": [{"type": "generated", "src": "s",
                                "props": {"img": "/public/vid_a/images/x.png"}}]}, "vid_a"))


def test_the_same_tools_still_work_on_the_real_tree(linked):
    assert "error" not in server.read_image("vid_b", "x")
    assert "error" not in server.get_timeline("vid_b")
    assert "error" not in server.get_scene_config("vid_b")
    assert server.read_scene_file("vid_b/intro")["tsx_content"] == "B-scene"
    assert "error" not in server.write_scene_file("vid_b", "outro", "x")
    assert server.delete_scene_file("outro", video_id="vid_b")["deleted"] is True
    assert server._bad_image_refs(
        {"scenes": [{"type": "generated", "src": "s",
                     "props": {"img": "/public/vid_b/images/x.png"}}]}, "vid_b") == []
    # A video with no job dir yet: writers create it.
    _video("vid_new")
    assert "error" not in server.write_scene_file("vid_new", "intro", "x")
    assert (linked / "generated" / "vid_new" / "intro.tsx").is_file()
    # The legacy flat form.
    (linked / "generated" / "flat.tsx").write_text("F")
    assert server.read_scene_file("flat")["tsx_content"] == "F"
    assert server.delete_scene_file("flat")["deleted"] is True
