"""Tests for the render agent (TMDEV-32; split out of the worker by TMDEV-188):
the atomic RENDER_QUEUED->RENDERING claim, file staging + a subprocess render
timeout, the AI-review/failure tail, and startup reconciliation.

Run from renderer/api/: pytest tests/test_render_agent.py
"""
import io
import json
import os
import signal
import sqlite3
import unittest.mock as mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import render_agent
import pipeline as pipeline_module


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = str(tmp_path / "test.db")
    pipeline_module._init_db(p)  # full schema incl. render_fail_count/ai_review_count
    monkeypatch.setattr(render_agent, "DB_PATH", p)
    return p


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Point the renderer's REMOTION_DIR/OUTPUT_DIR at tmp_path so staging and
    render output land somewhere test-writable, not the real /app/remotion."""
    remotion_dir = tmp_path / "remotion"
    output_dir = tmp_path / "output_videos"
    (remotion_dir / "public").mkdir(parents=True)
    output_dir.mkdir()
    monkeypatch.setattr(render_agent, "REMOTION_DIR", remotion_dir)
    monkeypatch.setattr(render_agent, "OUTPUT_DIR", output_dir)
    # The renderer derives every job file from JOBS_DIR/<video_id> (TMDEV-162);
    # _job_files writes them there.
    monkeypatch.setattr(pipeline_module, "JOBS_DIR", tmp_path / "jobs")
    return remotion_dir, output_dir


def _seed_video(db_path, video_id="vid-1", status="RENDER_QUEUED", render_fail_count=0,
                 project_id="proj-1", voice_file_path="", timeline_path="",
                 scene_config_path="", updated_at="2026-01-01T00:00:00Z",
                 script="", tts_text=""):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO videos
           (id, project_id, topic, strategy, producibility_score, status, render_fail_count,
            voice_file_path, timeline_path, scene_config_path, script, tts_text,
            created_at, updated_at)
           VALUES (?, ?, 'DNS resolution', 'curriculum', 8, ?, ?, ?, ?, ?, ?, ?,
                   '2026-01-01T00:00:00Z', ?)""",
        (video_id, project_id, status, render_fail_count,
         voice_file_path, timeline_path, scene_config_path, script, tts_text, updated_at),
    )
    con.commit()
    con.close()


def _read_video(db_path, video_id="vid-1"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def _read_comments(db_path, video_id="vid-1"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM comments WHERE video_id = ? ORDER BY created_at", (video_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _job_files(tmp_path, video_id="vid-1"):
    """Create real audio/timeline/scene-config files for tests that exercise
    the full _stage_and_render staging step."""
    job_dir = tmp_path / "jobs" / video_id
    job_dir.mkdir(parents=True)
    audio = job_dir / "audio.mp3"
    timeline = job_dir / "timeline.json"
    scene_config = job_dir / "scene-config.json"
    audio.write_bytes(b"fake-audio")
    timeline.write_text("{}")
    scene_config.write_text('{"scenes": []}')
    return str(audio), str(timeline), str(scene_config)


def _fake_popen(returncode=0, stdout="", stderr="", pid=4242):
    """A Popen-shaped mock of a process that has already exited: render_agent.py
    drains .stdout/.stderr on threads while polling, then reads .returncode,
    exactly like a real process once it has ended."""
    proc = mock.MagicMock()
    proc.pid = pid
    proc.args = ["npx", "remotion", "render"]
    proc.stdout = io.StringIO(stdout)
    proc.stderr = io.StringIO(stderr)
    proc.poll.return_value = returncode
    proc.returncode = returncode
    return proc


@pytest.fixture(autouse=True)
def _fast_render_clock(monkeypatch):
    """The render watcher's clock jumps an hour per read and its sleep is a
    no-op, so a double whose poll() never returns a code hits the ceiling at
    once instead of waiting it out."""
    tick = {"now": 0.0}

    def clock():
        tick["now"] += 3600.0
        return tick["now"]
    monkeypatch.setattr(render_agent, "_clock", clock)
    monkeypatch.setattr(render_agent, "_sleep", lambda _s: None)


def _mock_subprocess_success():
    return _fake_popen(returncode=0, stdout="", stderr="")


def _mock_subprocess_failure(stderr="render error"):
    return _fake_popen(returncode=1, stdout="", stderr=stderr)


def _fake_popen_timeout(pid=4242):
    """A process that never ends: poll() keeps answering None and its pipes
    are silent, so the watcher gives up at its ceiling (the test clock above
    makes that immediate) — render_agent.py must then kill the process group."""
    proc = mock.MagicMock()
    proc.pid = pid
    proc.args = ["npx", "remotion", "render"]
    proc.stdout = io.StringIO("")
    proc.stderr = io.StringIO("")
    proc.poll.return_value = None
    return proc


# ── _claim_next ──────────────────────────────────────────────────────────────

def test_claim_next_claims_render_queued(db_path):
    _seed_video(db_path, status="RENDER_QUEUED")
    claimed = render_agent._claim_next()
    assert claimed == "vid-1"
    assert _read_video(db_path)["status"] == "RENDERING"


def test_claim_next_ignores_voice_ready(db_path):
    """VOICE_READY means the agent is still authoring scene config — not the
    renderer's to touch until submit_render advances it to RENDER_QUEUED."""
    _seed_video(db_path, status="VOICE_READY")
    assert render_agent._claim_next() is None
    assert _read_video(db_path)["status"] == "VOICE_READY"


def test_claim_next_returns_none_when_nothing_queued(db_path):
    assert render_agent._claim_next() is None


def test_claim_next_fifo_by_updated_at(db_path):
    _seed_video(db_path, video_id="vid-new", status="RENDER_QUEUED",
                updated_at="2030-01-01T00:00:00Z")
    _seed_video(db_path, video_id="vid-old", status="RENDER_QUEUED",
                updated_at="2020-01-01T00:00:00Z")
    assert render_agent._claim_next() == "vid-old"


def _set_hold(db_path, until):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (pipeline_module.RENDER_CLAIM_HOLD_KEY, until))
    con.commit()
    con.close()


def test_claim_next_claims_nothing_while_onboarding_holds_claims(db_path):
    """`onboard.py --step gpu` holds claims while it recreates the renderer,
    so no render is started just to be killed by the recreate."""
    _seed_video(db_path, status="RENDER_QUEUED")
    _set_hold(db_path, "2999-01-01T00:00:00Z")
    assert render_agent._claim_next() is None
    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


def test_claim_next_ignores_an_expired_hold(db_path):
    """A crashed onboarding leaves its hold behind; it must not stop
    rendering past its ceiling."""
    _seed_video(db_path, status="RENDER_QUEUED")
    _set_hold(db_path, "2000-01-01T00:00:00Z")
    assert render_agent._claim_next() == "vid-1"


# ── render_timeout_secs (TMDEV-57) ────────────────────────────────────────────

def test_render_timeout_secs_defaults_to_10800(db_path):
    assert render_agent._render_timeout_secs() == 10800
    assert render_agent._render_stall_timeout_secs() == 600


def test_render_timeout_secs_reads_settings_table(db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '900')")
    con.commit()
    con.close()
    assert render_agent._render_timeout_secs() == 900


def test_stage_and_render_uses_configured_timeout(db_path, dirs, tmp_path):
    """The value actually passed to communicate() must be the live setting,
    not a fixed constant baked in at import time."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '900')")
    con.commit()
    con.close()

    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    fake_proc = _mock_subprocess_success()
    seen = {}

    def watch(proc, timeout_secs, stall_secs):
        seen.update(timeout=timeout_secs, stall=stall_secs)
        return "", "", "exited"
    with mock.patch("subprocess.Popen", return_value=fake_proc), \
         mock.patch.object(render_agent, "_wait_for_render", side_effect=watch):
        render_agent._stage_and_render("vid-1")

    assert seen == {"timeout": 900, "stall": 600}


# ── The watermark render prop (TMDEV-141) ──────────────────────────────────

def _render_props(popen_mock) -> dict:
    argv = popen_mock.call_args.args[0]
    return json.loads(argv[argv.index("--props") + 1])


def test_stage_and_render_asks_for_the_watermark_by_default(db_path, dirs, tmp_path):
    """Default on, and it comes from the settings table. The scene-config
    here says the opposite and must not count: the agent writes that file."""
    audio, timeline, scene_config = _job_files(tmp_path)
    with open(scene_config, "w") as f:
        f.write('{"scenes": [], "watermark": false}')
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()) as popen:
        render_agent._stage_and_render("vid-1")

    assert _render_props(popen)["watermark"] is True


def test_stage_and_render_drops_the_watermark_when_the_setting_is_off(db_path, dirs, tmp_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('watermark_enabled', 'false')")
    con.commit()
    con.close()
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()) as popen:
        render_agent._stage_and_render("vid-1")

    assert _render_props(popen)["watermark"] is False


# ── _stage_and_render (full flow: staging + subprocess + tail) ───────────────

def test_stage_and_render_success_ai_review_disabled_sets_video_ready(db_path, dirs, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    remotion_dir, _ = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "VIDEO_READY"
    assert (remotion_dir / "public" / "vid-1" / "audio.mp3").exists()


def test_stage_and_render_stages_generated_images(db_path, dirs, tmp_path, monkeypatch):
    """Images live in a subdirectory of the job dir and must reach the served
    tree — scenes reference them as /public/<vid>/images/<name> (TMDEV-29)."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    remotion_dir, _ = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    images = tmp_path / "jobs" / "vid-1" / "images"
    images.mkdir()
    (images / "skyline.png").write_bytes(b"fake-png")
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")

    assert (remotion_dir / "public" / "vid-1" / "images" / "skyline.png").exists()


def test_stage_and_render_without_images_dir_still_renders(db_path, dirs, tmp_path, monkeypatch):
    """Most videos have no images — an absent images/ dir is normal and must
    not be treated as a missing job file."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    remotion_dir, _ = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "VIDEO_READY"
    assert not (remotion_dir / "public" / "vid-1" / "images").exists()


def test_stage_and_render_missing_job_files_sets_revision_requested(db_path, dirs):
    _seed_video(db_path, status="RENDERING", voice_file_path="/nonexistent/audio.mp3",
                timeline_path="/nonexistent/timeline.json",
                scene_config_path="/nonexistent/scene-config.json")

    render_agent._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    comments = _read_comments(db_path)
    assert "missing job file" in comments[-1]["content"]


# ── TMDEV-162: staging derives every path from the ids ─────────────────────

def test_a_tampered_row_stages_the_derived_files_not_the_planted_ones(db_path, dirs, tmp_path):
    """A row whose path columns were pointed elsewhere before the fix (PATCH and
    update_video once accepted any string) must stage the video's own files."""
    remotion_dir, _ = dirs
    _job_files(tmp_path)
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "secret.json").write_text('{"secret": true}')
    (planted / "images").mkdir()
    (planted / "images" / "loot.png").write_bytes(b"loot")
    _seed_video(db_path, status="RENDERING",
                voice_file_path=str(planted / "secret.json"),
                timeline_path=str(planted / "secret.json"),
                scene_config_path=str(planted / "secret.json"))

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")

    staged = remotion_dir / "public" / "vid-1"
    assert (staged / "timeline.json").read_text() == "{}"
    assert (staged / "scene-config.json").read_text() == '{"scenes": []}'
    assert (staged / "audio.mp3").read_bytes() == b"fake-audio"
    assert not (staged / "images").exists()


def test_a_legacy_host_shaped_path_still_renders_from_the_derived_location(db_path, dirs,
                                                                         tmp_path):
    """Negative control: rows written by a host-driven MCP hold host paths
    (HANDOFF). The column only says the file was written; the render reads
    JOBS_DIR/<id>/, so such a row keeps rendering."""
    _job_files(tmp_path)
    host = "/home/someone/.tubematic-data/jobs/vid-1"
    _seed_video(db_path, status="RENDERING", voice_file_path=f"{host}/audio.mp3",
                timeline_path=f"{host}/timeline.json",
                scene_config_path=f"{host}/scene-config.json")

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()) as popen:
        render_agent._stage_and_render("vid-1")

    popen.assert_called_once()
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_an_empty_path_column_still_means_not_written(db_path, dirs, tmp_path):
    """The file existing is not enough: a column the writer never filled means
    the step never completed, exactly as before."""
    audio, timeline, _ = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio, timeline_path=timeline,
                scene_config_path="")
    with mock.patch("subprocess.Popen") as popen:
        render_agent._stage_and_render("vid-1")
    popen.assert_not_called()
    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    assert "scene_config_path" in _read_comments(db_path)[-1]["content"]


@pytest.mark.parametrize("project", ["..", "../../tmp", "a/b"])
def test_an_escaping_project_id_fails_the_render_without_staging(db_path, dirs, tmp_path,
                                                                project):
    remotion_dir, _ = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES (?, 'x', 'n')", (project,))
    con.commit()
    con.close()
    _seed_video(db_path, status="RENDERING", project_id=project, voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen") as popen:
        render_agent._stage_and_render("vid-1")

    popen.assert_not_called()
    assert _read_video(db_path)["status"] == "FAILED"
    assert "Render refused" in _read_comments(db_path)[-1]["content"]
    assert not (remotion_dir / "public" / "vid-1").exists()


def test_a_legacy_project_id_with_a_dot_still_renders(db_path, dirs, tmp_path):
    _, output_dir = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('node.js', 'x', 'n')")
    con.commit()
    con.close()
    _seed_video(db_path, status="RENDERING", project_id="node.js", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)
    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")
    assert _read_video(db_path)["video_path"] == str(output_dir / "node.js" / "vid-1.mp4")


# A long id is legacy too: the 128-character cap arrived with the creation
# rule, and only creation applies it.
LONG_LEGACY_ID = "x" * 129


def test_a_legacy_project_id_over_the_creation_cap_still_renders(db_path, dirs, tmp_path):
    _, output_dir = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES (?, 'x', 'n')",
                (LONG_LEGACY_ID,))
    con.commit()
    con.close()
    _seed_video(db_path, status="RENDERING", project_id=LONG_LEGACY_ID, voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)
    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")
    assert _read_video(db_path)["video_path"] == str(output_dir / LONG_LEGACY_ID / "vid-1.mp4")


@pytest.mark.parametrize("vid", ["a.b", "Spaced Name", LONG_LEGACY_ID])
def test_a_legacy_video_id_still_stages_and_renders(db_path, dirs, tmp_path, monkeypatch, vid):
    """An id filed before the creation rule existed is checked as a path
    component at use, as ids.py promises. Refusing it here moved every such
    upgraded video to FAILED."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    remotion_dir, output_dir = dirs
    audio, timeline, scene_config = _job_files(tmp_path, vid)
    _seed_video(db_path, video_id=vid, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)
    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()) as popen:
        render_agent._stage_and_render(vid)
    popen.assert_called_once()
    assert (remotion_dir / "public" / vid / "audio.mp3").read_bytes() == b"fake-audio"
    row = _read_video(db_path, vid)
    assert row["status"] == "VIDEO_READY"
    assert row["video_path"] == str(output_dir / "proj-1" / f"{vid}.mp4")


@pytest.mark.parametrize("vid", ["..", "../x", "/tmp/x", "a/b", "x" * 256])
def test_an_unusable_video_id_fails_the_render_without_staging(db_path, dirs, tmp_path, vid):
    remotion_dir, _ = dirs
    _seed_video(db_path, video_id=vid, status="RENDERING", voice_file_path="a",
                timeline_path="t", scene_config_path="s")
    before = sorted(p.name for p in tmp_path.iterdir())
    with mock.patch("subprocess.Popen") as popen:
        render_agent._stage_and_render(vid)
    popen.assert_not_called()
    assert _read_video(db_path, vid)["status"] == "FAILED"
    assert list((remotion_dir / "public").iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# The render is written to `<id>.mp4`, so the id must leave four bytes for the
# suffix: 252 bytes is a working job directory and an impossible file name.
# Refused before staging, not with ENAMETOOLONG after it.
def test_a_video_id_too_long_for_its_mp4_fails_before_staging(db_path, dirs, tmp_path):
    remotion_dir, _ = dirs
    vid = "x" * 252
    audio, timeline, scene_config = _job_files(tmp_path, vid)
    _seed_video(db_path, video_id=vid, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)
    with mock.patch("subprocess.Popen") as popen:
        render_agent._stage_and_render(vid)
    popen.assert_not_called()
    assert _read_video(db_path, vid)["status"] == "FAILED"
    assert "Render refused" in _read_comments(db_path, vid)[-1]["content"]
    assert list((remotion_dir / "public").iterdir()) == []


def test_a_video_id_that_leaves_room_for_its_mp4_renders(db_path, dirs, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    _, output_dir = dirs
    vid = "x" * 251
    audio, timeline, scene_config = _job_files(tmp_path, vid)
    _seed_video(db_path, video_id=vid, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)
    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render(vid)
    row = _read_video(db_path, vid)
    assert row["status"] == "VIDEO_READY"
    assert row["video_path"] == str(output_dir / "proj-1" / f"{vid}.mp4")


def test_a_job_dir_linked_to_another_video_fails_the_render(db_path, dirs, tmp_path):
    """vid-1 -> vid-2 stays inside the jobs root, so only the per-component
    symlink walk stops vid-1 rendering with vid-2's audio."""
    remotion_dir, _ = dirs
    _job_files(tmp_path, "vid-2")
    (tmp_path / "jobs" / "vid-1").symlink_to(tmp_path / "jobs" / "vid-2")
    _seed_video(db_path, status="RENDERING", voice_file_path="a", timeline_path="t",
                scene_config_path="s")
    with mock.patch("subprocess.Popen") as popen:
        render_agent._stage_and_render("vid-1")
    popen.assert_not_called()
    assert _read_video(db_path)["status"] == "FAILED"
    assert "symlink" in _read_comments(db_path)[-1]["content"]
    assert not (remotion_dir / "public" / "vid-1").exists()


def test_a_symlinked_job_file_fails_the_render(db_path, dirs, tmp_path):
    audio, timeline, scene_config = _job_files(tmp_path)
    secret = tmp_path / "secret.json"
    secret.write_text("{}")
    os.remove(timeline)
    os.symlink(secret, timeline)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio, timeline_path=timeline,
                scene_config_path=scene_config)
    with mock.patch("subprocess.Popen") as popen:
        render_agent._stage_and_render("vid-1")
    popen.assert_not_called()
    assert _read_video(db_path)["status"] == "FAILED"


def test_a_symlink_inside_images_is_not_staged(db_path, dirs, tmp_path):
    remotion_dir, _ = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    images = tmp_path / "jobs" / "vid-1" / "images"
    images.mkdir()
    (images / "real.png").write_bytes(b"png")
    secret = tmp_path / "secret.txt"
    secret.write_text("s")
    (images / "leak.png").symlink_to(secret)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio, timeline_path=timeline,
                scene_config_path=scene_config)
    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        render_agent._stage_and_render("vid-1")
    staged = remotion_dir / "public" / "vid-1" / "images"
    assert (staged / "real.png").exists()
    assert not (staged / "leak.png").exists()


def test_stage_and_render_timeout_auto_retries_render_queued(db_path, dirs, tmp_path):
    """A hung Chromium is environmental, not something the agent can fix by
    revising the scene — auto-retry via RENDER_QUEUED, not REVISION_REQUESTED."""
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config, render_fail_count=0)

    with mock.patch("subprocess.Popen", return_value=_fake_popen_timeout()), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        render_agent._stage_and_render("vid-1")

    video = _read_video(db_path)
    assert video["status"] == "RENDER_QUEUED"
    assert video["render_fail_count"] == 1


def test_stage_and_render_timeout_kills_whole_process_group(db_path, dirs, tmp_path):
    """TMDEV-57: subprocess.run's own timeout handling only kills the direct
    child, orphaning any Chromium/ffmpeg it spawned (confirmed live — they
    survived as <defunct> zombies competing with the next render attempt).
    Popen + start_new_session=True puts the whole tree in one process group,
    which this asserts gets killed and reaped, not just abandoned."""
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    fake_proc = _fake_popen_timeout(pid=4242)
    with mock.patch("subprocess.Popen", return_value=fake_proc) as mock_popen, \
         mock.patch("os.getpgid", return_value=4242) as mock_getpgid, \
         mock.patch("os.killpg") as mock_killpg, \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        render_agent._stage_and_render("vid-1")

    assert mock_popen.call_args.kwargs["start_new_session"] is True
    mock_getpgid.assert_called_once_with(4242)
    mock_killpg.assert_called_once_with(4242, signal.SIGKILL)
    fake_proc.wait.assert_called_once()  # reaped, not left as a zombie


def test_stage_and_render_timeout_reaps_reparented_grandchildren(db_path, dirs, tmp_path):
    """TMDEV-57 follow-up, confirmed live: killpg kills the whole process
    group at once, but grandchildren (node, chrome-headless, ffmpeg, ...)
    reparent to this container's PID 1 -- this same renderer process -- the
    instant their own parent dies, before proc.wait() (which only reaps the
    direct child) can claim them. A non-blocking WNOHANG drain (an earlier
    version of this fix) races ahead of heavier processes actually finishing
    exit and finds nothing -- confirmed live, they sat as permanent zombies.
    This asserts the loop *blocks* for each already-reparented child in turn
    until none remain, rather than giving up on the first not-ready check."""
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    # Two grandchildren to reap, then ChildProcessError signals "none left".
    waitpid_results = [(19, 0), (20, 0), ChildProcessError()]
    with mock.patch("subprocess.Popen", return_value=_fake_popen_timeout()), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=waitpid_results) as mock_waitpid:
        render_agent._stage_and_render("vid-1")

    assert mock_waitpid.call_args_list == [
        mock.call(-1, os.WNOHANG),
        mock.call(-1, os.WNOHANG),
        mock.call(-1, os.WNOHANG),
    ]


def test_stage_and_render_timeout_reap_never_waits_on_the_stills_server(db_path, dirs, tmp_path, monkeypatch):
    """The stills server (TMDEV-179) is a long-lived child of the renderer, so a
    blocking waitpid(-1) would sit on it forever after a timeout. The reaper
    drains non-blocking and stops as soon as no child but the stills server
    is left, polling only while an orphan of the killed group is still dying."""
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)
    # waitpid: one orphan reaped, then "children exist but none exited" for as long as we ask
    waitpid_results = [(19, 0), (0, 0), (0, 0), (0, 0)]
    others = iter([{20}, set()])   # the second orphan is still dying, then gone; the stills server never counts
    monkeypatch.setattr(render_agent, "_other_children", lambda: next(others, set()))
    monkeypatch.setattr(render_agent.time, "sleep", lambda s: None)
    with mock.patch("subprocess.Popen", return_value=_fake_popen_timeout()), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=waitpid_results) as mock_waitpid:
        render_agent._stage_and_render("vid-1")

    assert mock_waitpid.call_args_list == [mock.call(-1, os.WNOHANG)] * 3
    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


def test_stage_and_render_timeout_reap_stops_on_no_children(db_path, dirs, tmp_path):
    """If PID 1 has no other children at all, os.waitpid(-1, ...) raises
    ChildProcessError immediately -- the loop must treat that as "done" too,
    not let it escape and break the retry."""
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config, render_fail_count=0)

    with mock.patch("subprocess.Popen", return_value=_fake_popen_timeout()), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        render_agent._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


def test_stage_and_render_timeout_exceeding_cap_sets_failed(db_path, dirs, tmp_path):
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config, render_fail_count=2)

    with mock.patch("subprocess.Popen", return_value=_fake_popen_timeout()), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        render_agent._stage_and_render("vid-1")

    video = _read_video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 3


def test_stage_and_render_failure_sets_revision_requested(db_path, dirs, tmp_path):
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_failure("out of memory")):
        render_agent._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    comments = _read_comments(db_path)
    assert any("Render failed" in c["content"] for c in comments)


# ── _handle_render_success (AI-review gating tail) ────────────────────────────

def test_handle_render_success_ai_review_disabled_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    _seed_video(db_path, status="RENDERING")
    render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_handle_render_success_no_gemini_key_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _seed_video(db_path, status="RENDERING")
    render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_handle_render_success_ai_review_clean_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "Looks great, no issues found.",
                                          "must_fix": [], "suggestions": [],
                                          "feedback": "Looks great, no issues found."}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    video = _read_video(db_path)
    assert video["status"] == "VIDEO_READY"
    assert video["gemini_feedback"] == "Looks great, no issues found."
    comments = _read_comments(db_path)
    assert any("AI review 1 of 1 — clean" in c["content"] and "Looks great, no issues found." in c["content"]
               for c in comments)


def test_handle_render_success_passes_pronunciation_reference_to_review(db_path, dirs, monkeypatch):
    """VQA-6: the review can only check pronunciation if it is handed the
    authored wording and the exact text ElevenLabs was given."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING", script="Vhagar flew.", tts_text="Vah-gar flew.")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert run.call_args.kwargs["script_text"] == "Vhagar flew."
    assert run.call_args.kwargs["tts_text"] == "Vah-gar flew."


def test_handle_render_success_unvoiced_reference_passes_empty_strings(db_path, dirs, monkeypatch):
    """A row rendered before tts_text was ever recorded must not blow up the
    review tail (or pass None into the prompt builder)."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    # Empty strings, never None — the prompt builder is handed these directly.
    # Asserted per-key rather than as the whole kwargs dict, which also
    # carries the VQA-7 model/fps settings (covered separately below).
    assert run.call_args.kwargs["script_text"] == ""
    assert run.call_args.kwargs["tts_text"] == ""
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_handle_render_success_ai_review_must_fix_sets_revision_requested(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    feedback = ("**Overall:** otherwise clean\n\n"
                "**Must fix (1):**\n"
                "- **text_offscreen** @ 0:07 — scene `StepFlowDiagram`\n"
                "  caption clipped\n"
                "  Suggested fix: wrap the line\n\n"
                "**Suggestions (0):**\nNo improvement suggestions.")
    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={
                                "overall": "otherwise clean",
                                "must_fix": [{"type": "text_offscreen", "timestamp": "0:07",
                                              "scene": "StepFlowDiagram", "description": "caption clipped",
                                              "suggestedFix": "wrap the line"}],
                                "suggestions": [],
                                "feedback": feedback,
                            }):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED"
    assert video["gemini_feedback"] == feedback
    comments = _read_comments(db_path)
    assert any("AI review 1 of 1 found 1 must-fix, 0 suggestions" in c["content"]
               and "StepFlowDiagram" in c["content"]
               and "wrap the line" in c["content"]
               for c in comments)


def test_handle_render_success_ai_review_suggestions_only_sets_revision_requested(db_path, dirs, monkeypatch):
    """TMDEV-58: zero must-fix but non-empty suggestions still loops back —
    the agent still has real, actionable work to do."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    feedback = ("**Overall:** solid, minor polish available\n\n"
                "**Must fix (0):**\nNo blocking errors found.\n\n"
                "**Suggestions (1):**\n"
                "- **video** @ 0:30 — scene `StepFlow.tsx`\n"
                "  hook title could hold a beat longer\n"
                "  Suggested fix: extend by 12 frames")
    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={
                                "overall": "solid, minor polish available",
                                "must_fix": [],
                                "suggestions": [{"area": "video", "timestamp": "0:30",
                                                 "scene": "StepFlow.tsx",
                                                 "description": "hook title could hold a beat longer",
                                                 "suggestedFix": "extend by 12 frames"}],
                                "feedback": feedback,
                            }):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED"
    comments = _read_comments(db_path)
    assert any("AI review 1 of 1 found 0 must-fix, 1 suggestions" in c["content"]
               for c in comments)


def test_handle_render_success_ai_review_last_round_at_cap_still_routes_on_findings(db_path, dirs, monkeypatch):
    """The last non-forced round (new_count == max_render_retries, not yet
    over it) must still loop back to REVISION_REQUESTED on findings, exactly
    like any earlier round -- only new_count > max_render_retries forces
    acceptance. This is the boundary the `>` vs `>=` decision turns on."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_REVIEW_MAX_LOOPS", "2")
    _seed_video(db_path, status="RENDERING")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET ai_review_count = 1 WHERE id = 'vid-1'")  # -> becomes 2, == cap
    con.commit()
    con.close()
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={
                                "overall": "still one issue",
                                "must_fix": [{"type": "sync_drift", "timestamp": "unknown",
                                              "scene": "unknown", "description": "", "suggestedFix": ""}],
                                "suggestions": [],
                                "feedback": "still one issue",
                            }):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    video = _read_video(db_path)
    assert video["ai_review_count"] == 2
    assert video["status"] == "REVISION_REQUESTED"


def test_handle_render_success_ai_review_over_cap_runs_review_and_forces_video_ready(db_path, dirs, monkeypatch):
    """TMDEV-58: past the cap the review still runs (closing the old hole
    where the shipped render carried the previous round's stale feedback),
    but the video is forced to VIDEO_READY regardless of what it found."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_REVIEW_MAX_LOOPS", "2")
    _seed_video(db_path, status="RENDERING")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET ai_review_count = 2 WHERE id = 'vid-1'")
    con.commit()
    con.close()
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    fresh_feedback = "**Overall:** still has an issue\n\n**Must fix (1):**\n- **audio_drop** @ 1:00"
    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={
                                "overall": "still has an issue",
                                "must_fix": [{"type": "audio_drop", "timestamp": "1:00",
                                              "scene": "unknown", "description": "", "suggestedFix": ""}],
                                "suggestions": [],
                                "feedback": fresh_feedback,
                            }) as mock_review:
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    mock_review.assert_called_once()
    video = _read_video(db_path)
    assert video["status"] == "VIDEO_READY"
    assert video["gemini_feedback"] == fresh_feedback  # fresh, not stale from a prior round
    comments = _read_comments(db_path)
    assert any("Max AI reviews (2) reached" in c["content"] and "still has an issue" in c["content"]
               for c in comments)


def test_handle_render_success_max_render_retries_one_still_allows_one_revision_round(db_path, dirs, monkeypatch):
    """Pinning the off-by-one this ticket settled on: with the cap set to 1,
    the very first review must still be able to loop back to
    REVISION_REQUESTED when it has findings -- the rejected `>=` boundary
    would have forced acceptance immediately, making the feature a no-op at
    this (reachable) setting."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_REVIEW_MAX_LOOPS", "1")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={
                                "overall": "one issue",
                                "must_fix": [{"type": "sync_drift", "timestamp": "unknown",
                                              "scene": "unknown", "description": "", "suggestedFix": ""}],
                                "suggestions": [],
                                "feedback": "one issue",
                            }):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"


def test_handle_render_success_gemini_error_fails_open_to_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "", "must_fix": [], "suggestions": [],
                                          "feedback": "AI review did not run: Gemini upload failed: timeout",
                                          "error": "Gemini upload failed: timeout"}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    video = _read_video(db_path)
    assert video["status"] == "VIDEO_READY"
    assert video["gemini_feedback"] == "AI review did not run: Gemini upload failed: timeout"
    comments = _read_comments(db_path)
    assert any("AI review failed" in c["content"] for c in comments)


def test_handle_render_success_scene_config_missing_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    # Do NOT create scene-config.json in the staged public dir — absence is the test condition

    render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["status"] == "VIDEO_READY"
    comments = _read_comments(db_path)
    assert any("scene-config.json not found" in c["content"] for c in comments)


def test_handle_render_success_unexpected_exception_sets_revision_requested(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    _seed_video(db_path, status="RENDERING")

    with mock.patch.object(render_agent.db, "update_fields", side_effect=Exception("disk full")):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    comments = _read_comments(db_path)
    assert any("Unexpected error in render tail" in c["content"] for c in comments)


# ── _handle_render_failure ─────────────────────────────────────────────────────
# Render-crash retry backstop (TMDEV-1): a render that keeps crashing must
# escalate to FAILED once it exceeds the retry cap (reusing max_render_retries),
# instead of looping REVISION_REQUESTED forever.

def test_handle_render_failure_below_cap_sets_revision_requested(db_path):
    _seed_video(db_path, status="RENDERING", render_fail_count=0)
    render_agent._handle_render_failure("vid-1", "Chromium crashed")
    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED"
    assert video["render_fail_count"] == 1
    comments = _read_comments(db_path)
    assert "Render failed" in comments[-1]["content"]


def test_handle_render_failure_exceeding_cap_sets_failed(db_path):
    # default max_render_retries is 1 (TMDEV-74) -> the 2nd failure (count
    # becomes 2) exceeds it. Seeded at the boundary rather than well past it,
    # so a silent change to the default fails this test instead of sliding by.
    _seed_video(db_path, status="RENDERING", render_fail_count=1)
    render_agent._handle_render_failure("vid-1", "Chromium crashed")
    video = _read_video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 2
    comments = _read_comments(db_path)
    assert "giving up" in comments[-1]["content"].lower()


def test_handle_render_failure_respects_custom_max_render_retries_setting(db_path):
    """A raised cap must actually be read. The value is deliberately one the
    default (1, since TMDEV-74) would have escalated on, so the assertion
    fails if the setting is ignored — pinning it to the default proved
    nothing."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('max_render_retries', '3')")
    con.commit()
    con.close()
    _seed_video(db_path, status="RENDERING", render_fail_count=2)

    render_agent._handle_render_failure("vid-1", "Chromium crashed")

    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED"
    assert video["render_fail_count"] == 3


def test_handle_render_failure_persists_across_attempts(db_path):
    """render_fail_count is never reset between attempts, mirroring ai_review_count."""
    _seed_video(db_path, status="RENDERING", render_fail_count=0)
    render_agent._handle_render_failure("vid-1", "crash 1")
    assert _read_video(db_path)["render_fail_count"] == 1

    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'RENDERING' WHERE id = 'vid-1'")
    con.commit()
    con.close()
    render_agent._handle_render_failure("vid-1", "crash 2")

    assert _read_video(db_path)["render_fail_count"] == 2


def test_handle_render_failure_timeout_retry_status_is_render_queued(db_path):
    """The retry_status override _stage_and_render passes for a subprocess
    timeout auto-retries instead of bouncing to the agent."""
    _seed_video(db_path, status="RENDERING", render_fail_count=0)
    render_agent._handle_render_failure("vid-1", "timed out", retry_status="RENDER_QUEUED")
    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


# ── _reconcile_rendering_videos ────────────────────────────────────────────────
# TMDEV-32 changes this from TMDEV-1/TMDEV-30's original behavior: under the
# cap it now requeues to RENDER_QUEUED (auto-retry, no agent needed) instead
# of always bouncing to REVISION_REQUESTED — see render_agent.py's docstring.

def test_reconcile_below_cap_sets_render_queued(db_path):
    _seed_video(db_path, status="RENDERING", render_fail_count=0)

    render_agent._reconcile_rendering_videos()

    video = _read_video(db_path)
    assert video["status"] == "RENDER_QUEUED"
    assert video["render_fail_count"] == 1
    comments = _read_comments(db_path)
    assert "interrupted" in comments[-1]["content"].lower()


def test_reconcile_exceeding_cap_sets_failed(db_path):
    # default max_render_retries is 1 (TMDEV-74) -> the 2nd interruption
    # (count becomes 2) exceeds it.
    _seed_video(db_path, status="RENDERING", render_fail_count=1)

    render_agent._reconcile_rendering_videos()

    video = _read_video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 2
    comments = _read_comments(db_path)
    assert "giving up" in comments[-1]["content"].lower()


def test_reconcile_ignores_videos_not_rendering(db_path):
    _seed_video(db_path, video_id="vid-2", status="VOICING", render_fail_count=0)

    render_agent._reconcile_rendering_videos()

    video = _read_video(db_path, video_id="vid-2")
    assert video["status"] == "VOICING"
    assert video["render_fail_count"] == 0


def test_reconcile_no_rendering_videos_is_noop(db_path):
    _seed_video(db_path, status="VIDEO_READY", render_fail_count=0)

    render_agent._reconcile_rendering_videos()  # should not raise or change anything

    assert _read_video(db_path)["status"] == "VIDEO_READY"


# ── AI-review model/fps settings and the loop-cap split (VQA-7) ────────────

def _seed_for_review(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')


def test_handle_render_success_passes_model_and_fps_from_settings(db_path, dirs, monkeypatch):
    """ai_review.py is deliberately DB-free, so the renderer is the only place
    these settings can be read — if this pass-through breaks, the review
    silently runs on the module defaults and every settings change is inert."""
    _seed_for_review(db_path, dirs, monkeypatch)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_model', 'gemini-3.6-flash')")
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_fps', '20')")
    con.commit()
    con.close()

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert run.call_args.kwargs["model"] == "gemini-3.6-flash"
    assert run.call_args.kwargs["fps"] == "20"


def test_handle_render_success_uses_review_defaults_when_unset(db_path, dirs, monkeypatch):
    _seed_for_review(db_path, dirs, monkeypatch)
    monkeypatch.delenv("AI_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("AI_REVIEW_FPS", raising=False)

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert run.call_args.kwargs["model"] == "gemini-2.5-flash"
    assert run.call_args.kwargs["fps"] == "10"


def test_ai_review_loop_cap_defaults_to_one_and_is_independent(db_path, monkeypatch):
    """The split itself. Before VQA-7 both budgets read one key, so lowering
    the review loop halved the render retry budget as a side effect.

    Asserted by moving one row and watching the *other* accessor stay put:
    both defaults are 1 since TMDEV-74, so comparing the two default values
    would pass even if the split were reverted."""
    monkeypatch.delenv("AI_REVIEW_MAX_LOOPS", raising=False)
    monkeypatch.delenv("MAX_RENDER_RETRIES", raising=False)
    monkeypatch.setattr(render_agent, "DB_PATH", str(db_path))
    assert render_agent._max_ai_review_loops() == 1
    assert render_agent._max_render_retries() == 1

    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_max_loops', '2')")
    con.commit()
    con.close()
    assert render_agent._max_ai_review_loops() == 2
    # ...and the render budget is untouched by that write.
    assert render_agent._max_render_retries() == 1


def test_render_retry_budget_is_unaffected_by_the_review_loop_setting(db_path):
    """A crashing render must still get its full retry budget when the review
    loop is set to 1 — the two caps are separate keys (VQA-7)."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_max_loops', '1')")
    con.commit()
    con.close()
    _seed_video(db_path, status="RENDERING")

    # default max_render_retries is 1 -> failure 1 retries, failure 2 gives up.
    # Writing ai_review_max_loops above must not change either boundary.
    render_agent._handle_render_failure("vid-1", "boom")
    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"

    for _ in range(1):
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET status = 'RENDERING' WHERE id = 'vid-1'")
        con.commit()
        con.close()
        render_agent._handle_render_failure("vid-1", "boom")

    video = _read_video(db_path)
    assert video["render_fail_count"] == 2
    assert video["status"] == "FAILED"


# ── Feedback storage vs comment truncation (VQA-7 follow-up) ──────────────

def _long_review(n_chars: int = 12000) -> str:
    body = "\n".join(f"- **animation_defect** @ 0:{i:02d} — a real blocking defect number {i}"
                     for i in range(400))
    return ("**Overall:** many problems.\n\n**Must fix (400):**\n" + body)[:n_chars]


def test_gemini_feedback_is_stored_in_full(db_path, dirs, monkeypatch):
    """The agent acts on gemini_feedback, and must-fix entries are no longer
    capped by the prompt — so any cap here would silently drop real blocking
    defects. This is the assertion that keeps the column uncapped."""
    _seed_for_review(db_path, dirs, monkeypatch)
    feedback = _long_review()
    assert len(feedback) > 8000  # the cap that used to apply

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "many problems", "must_fix": [],
                                          "suggestions": [], "feedback": feedback}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["gemini_feedback"] == feedback


def test_long_review_comment_is_truncated_and_says_so(db_path, dirs, monkeypatch):
    """The comment stays capped, but silently clipping it would let the agent
    mistake a clipped review for a short one and miss blocking defects."""
    _seed_for_review(db_path, dirs, monkeypatch)
    feedback = _long_review()

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "many problems", "must_fix": [],
                                          "suggestions": [], "feedback": feedback}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "gemini_feedback" in body        # points at the complete copy
    assert "truncated" in body
    for c in _read_comments(db_path):
        assert len(c["content"]) <= render_agent._COMMENT_MAX_CHARS


def test_short_review_comment_is_untouched(db_path, dirs, monkeypatch):
    """The truncation marker must not appear on a review that fits."""
    _seed_for_review(db_path, dirs, monkeypatch)

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "**Overall:** fine.\n\nNo blocking errors."}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "truncated" not in body


def test_truncate_comment_helper_boundaries():
    assert render_agent._truncate_comment("") == ""
    exact = "x" * render_agent._COMMENT_MAX_CHARS
    assert render_agent._truncate_comment(exact) == exact          # at the cap, untouched
    over = render_agent._truncate_comment("y" * (render_agent._COMMENT_MAX_CHARS + 1))
    assert len(over) <= render_agent._COMMENT_MAX_CHARS            # never grows past the cap
    assert over.endswith("for the complete review.")


def test_error_comment_keeps_the_routing_clause_when_the_error_is_long(db_path, dirs, monkeypatch):
    """httpx embeds the whole request URL in its error strings, so a review
    error can easily exceed the comment cap. The routing statement has to
    survive that: a comment that says an error happened but not where the
    video went is worse than no comment."""
    _seed_for_review(db_path, dirs, monkeypatch)
    huge_error = "Gemini review failed: " + ("u" * 5000)

    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                            return_value={"overall": "", "must_fix": [], "suggestions": [],
                                          "feedback": "AI review did not run: boom",
                                          "error": huge_error}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "advancing to VIDEO_READY" in body
    assert _read_video(db_path)["status"] == "VIDEO_READY"   # fail-open preserved
    for c in _read_comments(db_path):
        assert len(c["content"]) <= render_agent._COMMENT_MAX_CHARS


# ── _setting precedence (TMDEV-73) ──────────────────────────────────────────
# The settings table is the source of truth; env is a fallback only. A *blank*
# row must fall through rather than win: onboarding seeds "" for every
# credential it did not ask about, so an empty row would otherwise shadow a key
# supplied through the container environment and silently skip AI review.

def _row(db_path, key, value):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    con.commit()
    con.close()


def test_setting_prefers_a_populated_row_over_env(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "from-db")
    assert render_agent._setting("gemini_api_key", "") == "from-db"


def test_setting_falls_back_to_env_when_no_row_exists(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert render_agent._setting("gemini_api_key", "") == "from-env"


def test_blank_row_falls_through_to_env(db_path, monkeypatch):
    """The regression guard: onboarding writes "" for an unsupplied key, and a
    stack that supplies it via `environment:` would otherwise lose AI review."""
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "")
    assert render_agent._setting("gemini_api_key", "") == "from-env"


def test_blank_row_and_no_env_yields_the_default(db_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _row(db_path, "gemini_api_key", "")
    assert render_agent._setting("gemini_api_key", "fallback") == "fallback"


def test_blank_row_does_not_break_the_int_settings(db_path, monkeypatch):
    """int("") would raise; the accessors catch it, but falling through means
    the configured default applies instead of the hardcoded one."""
    monkeypatch.delenv("MAX_RENDER_RETRIES", raising=False)
    _row(db_path, "max_render_retries", "")
    assert render_agent._max_render_retries() == 1


def test_the_renderer_matches_the_other_two_key_readers(db_path, monkeypatch):
    """mcp/server.py's key helpers and pipeline.py's _secret both use
    `stored or env`. Three readers of one table must not disagree."""
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "")
    assert render_agent._setting("gemini_api_key", "") == \
        (pipeline_module._secret({"gemini_api_key": ""}, "gemini_api_key", "GEMINI_API_KEY"))


# ── Usage recording and the price sync (TMDEV-107) ───────────────────────────

def _usage_rows(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT e.*, l.video_id FROM usage_events e "
                       "LEFT JOIN usage_event_videos l ON l.event_id = e.id").fetchall()
    con.close()
    return rows


def _review_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')


def test_each_review_is_recorded_against_the_video(db_path, dirs, monkeypatch):
    """A review that loops twice costs two rows — the old flat 2¢ could not
    tell one review from three."""
    _review_ready(db_path, dirs, monkeypatch)
    usage = {"model": "gemini-2.5-flash", "fps": 10,
             "usageMetadata": {"promptTokenCount": 66000, "candidatesTokenCount": 300}}
    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                           return_value={"overall": "", "must_fix": [], "suggestions": [],
                                         "feedback": "ok", "usage": usage}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    [row] = _usage_rows(db_path)
    assert (row["service"], row["model"], row["operation"], row["video_id"]) == \
        ("gemini", "gemini-2.5-flash", "ai_review", "vid-1")
    assert json.loads(row["units"]) == {"input": 66000, "output": 300}
    assert row["cost_basis"] == "priced"  # gemini-2.5-flash is in the built-in snapshot


def test_a_review_without_usage_records_nothing(db_path, dirs, monkeypatch):
    """A review that never reached Gemini (no usage key) was not billed."""
    _review_ready(db_path, dirs, monkeypatch)
    with mock.patch.object(render_agent.ai_review, "run_ai_review",
                           return_value={"overall": "", "must_fix": [], "suggestions": [],
                                         "feedback": "AI review did not run: x", "error": "x"}):
        render_agent._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    assert _usage_rows(db_path) == []
