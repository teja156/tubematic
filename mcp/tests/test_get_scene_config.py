"""Tests for get_scene_config (VQA-10): the only way for the agent to read a
video's current scene-config.json.

videos.scene_config_path is container-absolute (/jobs/<vid>/scene-config.json),
exactly the problem get_timeline already solves for timeline.json — that fix
was never generalized, which is why a revision could only ever re-derive the
whole video instead of editing the one scene the feedback named.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def clear_claims():
    server._scene_claims.clear()
    yield
    server._scene_claims.clear()


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file and JOBS_DIR at a tmp dir.
    Returns a make_video factory."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make_video(video_id, status="REVISION_REQUESTED"):
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
            {"type": "generated", "src": "vid_1/intro-hook",
             "startFrame": 0, "durationInFrames": 150,
             "props": {"title": "Hello"}},
            {"type": "generated", "src": "StepFlowDiagram", "source": "installed",
             "startFrame": 150, "durationInFrames": 150,
             "props": {"steps": ["a", "b"]}},
        ],
        "sfx": [],
    }


def _write_config(video_id, config):
    job_dir = server.JOBS_DIR / video_id
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "scene-config.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


# ── Happy path ────────────────────────────────────────────────────────────

def test_returns_the_parsed_config(job_db):
    job_db("vid_1")
    _write_config("vid_1", _config())

    result = server.get_scene_config("vid_1")

    assert result["video_id"] == "vid_1"
    assert result["config"] == _config()
    assert result["path"].endswith("/vid_1/scene-config.json")


def test_returns_every_scene_entry_intact(job_db):
    """The whole point: props, source and frame spans survive the read, so the
    caller can hand untouched entries straight back to write_scene_config."""
    job_db("vid_1")
    _write_config("vid_1", _config())

    scenes = server.get_scene_config("vid_1")["config"]["scenes"]

    assert [s["src"] for s in scenes] == ["vid_1/intro-hook", "StepFlowDiagram"]
    assert scenes[1]["source"] == "installed"
    assert scenes[0]["props"] == {"title": "Hello"}


# ── Errors ────────────────────────────────────────────────────────────────

def test_unknown_video_id_errors(job_db):
    result = server.get_scene_config("vid_nope")
    assert "not found" in result["error"].lower()


def test_missing_config_says_it_has_not_been_authored_yet(job_db):
    """Mirrors get_timeline's "voice hasn't been generated yet" — the caller
    needs to know this is the first authoring pass, not a broken file."""
    job_db("vid_1")

    result = server.get_scene_config("vid_1")

    assert "error" in result
    assert "scene-config.json" in result["error"]
    assert "write_scene_config" in result["error"]


def test_malformed_json_errors_rather_than_raising(job_db):
    job_db("vid_1")
    job_dir = server.JOBS_DIR / "vid_1"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "scene-config.json").write_text("{not json", encoding="utf-8")

    result = server.get_scene_config("vid_1")

    assert "could not be read" in result["error"]


# ── Claim exemption ───────────────────────────────────────────────────────

def test_not_guarded_by_the_scene_work_claim(job_db, monkeypatch):
    """A pure read: no spend, no write. Guarding it would block a second
    session from diagnosing a stuck video for the full 15-minute TTL — the
    same reasoning that already exempts read_image, get_timeline,
    validate_job and list_scene_files."""
    job_db("vid_1")
    _write_config("vid_1", _config())
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._try_claim_scene_work("vid_1", "session:other")

    result = server.get_scene_config("vid_1")

    assert "error" not in result
    assert result["config"]["totalFrames"] == 300


def test_reading_does_not_take_a_claim(job_db, monkeypatch):
    """Not merely unblocked by someone else's claim — it must not create one
    either, or a read would wedge the video against the session that then
    tries to do the actual write."""
    job_db("vid_1")
    _write_config("vid_1", _config())
    monkeypatch.setattr(server, "_session_owner", lambda: "session:reader")

    server.get_scene_config("vid_1")

    assert server._try_claim_scene_work("vid_1", "session:writer") is None


# ── Round-trip ────────────────────────────────────────────────────────────

def test_unchanged_round_trip_leaves_the_file_byte_identical(job_db):
    """The mechanical half of VQA-10's acceptance #1: a revision that touches
    one scene must leave every other entry byte-identical. Both sides use
    json.dumps(..., indent=2), so this is achievable — pin it, because a
    formatting change on either side would silently rewrite the whole file
    and make "only this scene changed" unprovable from a diff."""
    job_db("vid_1")
    server.write_scene_config("vid_1", _config())
    path = server.JOBS_DIR / "vid_1" / "scene-config.json"
    before = path.read_bytes()

    config = server.get_scene_config("vid_1")["config"]
    server.write_scene_config("vid_1", config)

    assert path.read_bytes() == before


# ── The revision branch's entry-test discriminator ────────────────────────
#
# The skill decides between an incremental revision and a full re-derivation
# by comparing config.totalFrames against get_timeline's total_frames — NOT by
# checking whether scene_config_path is populated, which is what VQA-10's
# ticket text proposed. That would have routed every pronunciation revision
# (which re-voices and returns with the field still set from the prior round)
# into the incremental branch, violating the ticket's own acceptance #3.
#
# The branch itself is prose in SKILL.md and can only be proven by a live
# revision cycle. What IS mechanically checkable here is its premise: that the
# two tools surface comparable numbers to the same caller, and that a re-voice
# actually moves them apart. Without this, a future change to either tool's
# return shape could silently break the discriminator with nothing failing.

def _write_timeline(video_id, total_frames):
    job_dir = server.JOBS_DIR / video_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "timeline.json").write_text(
        json.dumps({"totalFrames": total_frames, "fps": 30, "segments": []}), encoding="utf-8")


def test_frame_counts_agree_when_the_audio_is_unchanged(job_db):
    """The incremental-revision case: same audio, so the old spans still mean
    something and every untouched entry can be carried through."""
    job_db("vid_1")
    server.write_scene_config("vid_1", _config(total_frames=300))
    _write_timeline("vid_1", 300)

    config = server.get_scene_config("vid_1")["config"]
    timeline = server.get_timeline("vid_1")

    assert config["totalFrames"] == timeline["total_frames"]


def test_a_re_voice_moves_the_frame_counts_apart(job_db):
    """The full-re-derivation case. A re-voice writes a new timeline.json of a
    different length while scene_config_path stays populated — which is
    exactly why the entry test cannot key on that field."""
    job_db("vid_1")
    server.write_scene_config("vid_1", _config(total_frames=300))
    _write_timeline("vid_1", 412)  # re-voiced: new audio, new length

    config = server.get_scene_config("vid_1")["config"]
    timeline = server.get_timeline("vid_1")

    assert config["totalFrames"] != timeline["total_frames"]
    # The field the ticket wanted to key on is still set — the trap itself.
    with server._conn() as con:
        row = con.execute("SELECT scene_config_path FROM videos WHERE id = ?", ("vid_1",)).fetchone()
    assert row["scene_config_path"]


def test_round_trip_changing_one_scene_leaves_the_others_untouched(job_db):
    job_db("vid_1")
    server.write_scene_config("vid_1", _config())

    config = server.get_scene_config("vid_1")["config"]
    config["scenes"][0]["props"]["title"] = "Fixed"
    server.write_scene_config("vid_1", config)

    after = server.get_scene_config("vid_1")["config"]
    assert after["scenes"][0]["props"]["title"] == "Fixed"
    assert after["scenes"][1] == _config()["scenes"][1]
    assert after["totalFrames"] == 300
