"""Tests for the render worker (TMDEV-32): the atomic RENDER_QUEUED->RENDERING
claim, file staging + a subprocess render timeout, the AI-review/failure tail
(moved unchanged from the old server._render — see test_render_tail.py's
former docstring, now merged in here), and startup reconciliation.

Run from renderer/api/: pytest tests/test_worker.py
"""
import json
import os
import signal
import sqlite3
import subprocess
import unittest.mock as mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import worker
import pipeline as pipeline_module


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = str(tmp_path / "test.db")
    pipeline_module._init_db(p)  # full schema incl. render_fail_count/ai_review_count
    monkeypatch.setattr(worker, "DB_PATH", p)
    return p


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Point the worker's REMOTION_DIR/OUTPUT_DIR at tmp_path so staging and
    render output land somewhere test-writable, not the real /app/remotion."""
    remotion_dir = tmp_path / "remotion"
    output_dir = tmp_path / "output_videos"
    (remotion_dir / "public").mkdir(parents=True)
    output_dir.mkdir()
    monkeypatch.setattr(worker, "REMOTION_DIR", remotion_dir)
    monkeypatch.setattr(worker, "OUTPUT_DIR", output_dir)
    # The worker derives every job file from JOBS_DIR/<video_id> (TMDEV-162);
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
    """A Popen-shaped mock: worker.py drives it via .communicate(timeout=...)
    then reads .returncode, exactly like a real process once communicate()
    has returned."""
    proc = mock.MagicMock()
    proc.pid = pid
    proc.args = ["npx", "remotion", "render"]
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    return proc


def _mock_subprocess_success():
    return _fake_popen(returncode=0, stdout="", stderr="")


def _mock_subprocess_failure(stderr="render error"):
    return _fake_popen(returncode=1, stdout="", stderr=stderr)


def _fake_popen_timeout(pid=4242):
    """communicate() raises TimeoutExpired, as it does for a real Popen once
    the timeout elapses — worker.py must then kill the process group."""
    proc = mock.MagicMock()
    proc.pid = pid
    proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=1200)
    return proc


# ── _claim_next ──────────────────────────────────────────────────────────────

def test_claim_next_claims_render_queued(db_path):
    _seed_video(db_path, status="RENDER_QUEUED")
    claimed = worker._claim_next()
    assert claimed == "vid-1"
    assert _read_video(db_path)["status"] == "RENDERING"


def test_claim_next_ignores_voice_ready(db_path):
    """VOICE_READY means the agent is still authoring scene config — not the
    worker's to touch until submit_render advances it to RENDER_QUEUED."""
    _seed_video(db_path, status="VOICE_READY")
    assert worker._claim_next() is None
    assert _read_video(db_path)["status"] == "VOICE_READY"


def test_claim_next_returns_none_when_nothing_queued(db_path):
    assert worker._claim_next() is None


def test_claim_next_fifo_by_updated_at(db_path):
    _seed_video(db_path, video_id="vid-new", status="RENDER_QUEUED",
                updated_at="2030-01-01T00:00:00Z")
    _seed_video(db_path, video_id="vid-old", status="RENDER_QUEUED",
                updated_at="2020-01-01T00:00:00Z")
    assert worker._claim_next() == "vid-old"


# ── render_timeout_secs (TMDEV-57) ────────────────────────────────────────────

def test_render_timeout_secs_defaults_to_2400(db_path):
    assert worker._render_timeout_secs() == 2400


def test_render_timeout_secs_reads_settings_table(db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '900')")
    con.commit()
    con.close()
    assert worker._render_timeout_secs() == 900


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
    with mock.patch("subprocess.Popen", return_value=fake_proc):
        worker._stage_and_render("vid-1")

    fake_proc.communicate.assert_called_once_with(timeout=900)


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
        worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")

    assert _render_props(popen)["watermark"] is False


# ── _stage_and_render (full flow: staging + subprocess + tail) ───────────────

def test_stage_and_render_success_ai_review_disabled_sets_video_ready(db_path, dirs, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    remotion_dir, _ = dirs
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_success()):
        worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "VIDEO_READY"
    assert not (remotion_dir / "public" / "vid-1" / "images").exists()


def test_stage_and_render_missing_job_files_sets_revision_requested(db_path, dirs):
    _seed_video(db_path, status="RENDERING", voice_file_path="/nonexistent/audio.mp3",
                timeline_path="/nonexistent/timeline.json",
                scene_config_path="/nonexistent/scene-config.json")

    worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")

    popen.assert_called_once()
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_an_empty_path_column_still_means_not_written(db_path, dirs, tmp_path):
    """The file existing is not enough: a column the writer never filled means
    the step never completed, exactly as before."""
    audio, timeline, _ = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio, timeline_path=timeline,
                scene_config_path="")
    with mock.patch("subprocess.Popen") as popen:
        worker._stage_and_render("vid-1")
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
        worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")
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
        worker._stage_and_render("vid-1")
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
        worker._stage_and_render(vid)
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
        worker._stage_and_render(vid)
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
        worker._stage_and_render(vid)
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
        worker._stage_and_render(vid)
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
        worker._stage_and_render("vid-1")
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
        worker._stage_and_render("vid-1")
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
        worker._stage_and_render("vid-1")
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
        worker._stage_and_render("vid-1")

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
        worker._stage_and_render("vid-1")

    assert mock_popen.call_args.kwargs["start_new_session"] is True
    mock_getpgid.assert_called_once_with(4242)
    mock_killpg.assert_called_once_with(4242, signal.SIGKILL)
    fake_proc.wait.assert_called_once()  # reaped, not left as a zombie


def test_stage_and_render_timeout_reaps_reparented_grandchildren(db_path, dirs, tmp_path):
    """TMDEV-57 follow-up, confirmed live: killpg kills the whole process
    group at once, but grandchildren (node, chrome-headless, ffmpeg, ...)
    reparent to this container's PID 1 -- this same worker process -- the
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
        worker._stage_and_render("vid-1")

    assert mock_waitpid.call_args_list == [
        mock.call(-1, 0),
        mock.call(-1, 0),
        mock.call(-1, 0),
    ]


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
        worker._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


def test_stage_and_render_timeout_exceeding_cap_sets_failed(db_path, dirs, tmp_path):
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config, render_fail_count=2)

    with mock.patch("subprocess.Popen", return_value=_fake_popen_timeout()), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        worker._stage_and_render("vid-1")

    video = _read_video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 3


def test_stage_and_render_failure_sets_revision_requested(db_path, dirs, tmp_path):
    audio, timeline, scene_config = _job_files(tmp_path)
    _seed_video(db_path, status="RENDERING", voice_file_path=audio,
                timeline_path=timeline, scene_config_path=scene_config)

    with mock.patch("subprocess.Popen", return_value=_mock_subprocess_failure("out of memory")):
        worker._stage_and_render("vid-1")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    comments = _read_comments(db_path)
    assert any("Render failed" in c["content"] for c in comments)


# ── _handle_render_success (AI-review gating tail) ────────────────────────────

def test_handle_render_success_ai_review_disabled_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    _seed_video(db_path, status="RENDERING")
    worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_handle_render_success_no_gemini_key_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _seed_video(db_path, status="RENDERING")
    worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_handle_render_success_ai_review_clean_sets_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "Looks great, no issues found.",
                                          "must_fix": [], "suggestions": [],
                                          "feedback": "Looks great, no issues found."}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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
    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={
                                "overall": "otherwise clean",
                                "must_fix": [{"type": "text_offscreen", "timestamp": "0:07",
                                              "scene": "StepFlowDiagram", "description": "caption clipped",
                                              "suggestedFix": "wrap the line"}],
                                "suggestions": [],
                                "feedback": feedback,
                            }):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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
    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={
                                "overall": "solid, minor polish available",
                                "must_fix": [],
                                "suggestions": [{"area": "video", "timestamp": "0:30",
                                                 "scene": "StepFlow.tsx",
                                                 "description": "hook title could hold a beat longer",
                                                 "suggestedFix": "extend by 12 frames"}],
                                "feedback": feedback,
                            }):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={
                                "overall": "still one issue",
                                "must_fix": [{"type": "sync_drift", "timestamp": "unknown",
                                              "scene": "unknown", "description": "", "suggestedFix": ""}],
                                "suggestions": [],
                                "feedback": "still one issue",
                            }):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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
    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={
                                "overall": "still has an issue",
                                "must_fix": [{"type": "audio_drop", "timestamp": "1:00",
                                              "scene": "unknown", "description": "", "suggestedFix": ""}],
                                "suggestions": [],
                                "feedback": fresh_feedback,
                            }) as mock_review:
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={
                                "overall": "one issue",
                                "must_fix": [{"type": "sync_drift", "timestamp": "unknown",
                                              "scene": "unknown", "description": "", "suggestedFix": ""}],
                                "suggestions": [],
                                "feedback": "one issue",
                            }):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"


def test_handle_render_success_gemini_error_fails_open_to_video_ready(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, status="RENDERING")
    remotion_dir, _ = dirs
    scene_dir = remotion_dir / "public" / "vid-1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene-config.json").write_text('{"scenes": []}')

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "", "must_fix": [], "suggestions": [],
                                          "feedback": "AI review did not run: Gemini upload failed: timeout",
                                          "error": "Gemini upload failed: timeout"}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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

    worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["status"] == "VIDEO_READY"
    comments = _read_comments(db_path)
    assert any("scene-config.json not found" in c["content"] for c in comments)


def test_handle_render_success_unexpected_exception_sets_revision_requested(db_path, dirs, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    _seed_video(db_path, status="RENDERING")

    with mock.patch.object(worker.db, "update_fields", side_effect=Exception("disk full")):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    comments = _read_comments(db_path)
    assert any("Unexpected error in render tail" in c["content"] for c in comments)


# ── _handle_render_failure ─────────────────────────────────────────────────────
# Render-crash retry backstop (TMDEV-1): a render that keeps crashing must
# escalate to FAILED once it exceeds the retry cap (reusing max_render_retries),
# instead of looping REVISION_REQUESTED forever.

def test_handle_render_failure_below_cap_sets_revision_requested(db_path):
    _seed_video(db_path, status="RENDERING", render_fail_count=0)
    worker._handle_render_failure("vid-1", "Chromium crashed")
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
    worker._handle_render_failure("vid-1", "Chromium crashed")
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

    worker._handle_render_failure("vid-1", "Chromium crashed")

    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED"
    assert video["render_fail_count"] == 3


def test_handle_render_failure_persists_across_attempts(db_path):
    """render_fail_count is never reset between attempts, mirroring ai_review_count."""
    _seed_video(db_path, status="RENDERING", render_fail_count=0)
    worker._handle_render_failure("vid-1", "crash 1")
    assert _read_video(db_path)["render_fail_count"] == 1

    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'RENDERING' WHERE id = 'vid-1'")
    con.commit()
    con.close()
    worker._handle_render_failure("vid-1", "crash 2")

    assert _read_video(db_path)["render_fail_count"] == 2


def test_handle_render_failure_timeout_retry_status_is_render_queued(db_path):
    """The retry_status override _stage_and_render passes for a subprocess
    timeout auto-retries instead of bouncing to the agent."""
    _seed_video(db_path, status="RENDERING", render_fail_count=0)
    worker._handle_render_failure("vid-1", "timed out", retry_status="RENDER_QUEUED")
    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


# ── _reconcile_rendering_videos ────────────────────────────────────────────────
# TMDEV-32 changes this from TMDEV-1/TMDEV-30's original behavior: under the
# cap it now requeues to RENDER_QUEUED (auto-retry, no agent needed) instead
# of always bouncing to REVISION_REQUESTED — see worker.py's docstring.

def test_reconcile_below_cap_sets_render_queued(db_path):
    _seed_video(db_path, status="RENDERING", render_fail_count=0)

    worker._reconcile_rendering_videos()

    video = _read_video(db_path)
    assert video["status"] == "RENDER_QUEUED"
    assert video["render_fail_count"] == 1
    comments = _read_comments(db_path)
    assert "interrupted" in comments[-1]["content"].lower()


def test_reconcile_exceeding_cap_sets_failed(db_path):
    # default max_render_retries is 1 (TMDEV-74) -> the 2nd interruption
    # (count becomes 2) exceeds it.
    _seed_video(db_path, status="RENDERING", render_fail_count=1)

    worker._reconcile_rendering_videos()

    video = _read_video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 2
    comments = _read_comments(db_path)
    assert "giving up" in comments[-1]["content"].lower()


def test_reconcile_ignores_videos_not_rendering(db_path):
    _seed_video(db_path, video_id="vid-2", status="VOICING", render_fail_count=0)

    worker._reconcile_rendering_videos()

    video = _read_video(db_path, video_id="vid-2")
    assert video["status"] == "VOICING"
    assert video["render_fail_count"] == 0


def test_reconcile_no_rendering_videos_is_noop(db_path):
    _seed_video(db_path, status="VIDEO_READY", render_fail_count=0)

    worker._reconcile_rendering_videos()  # should not raise or change anything

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
    """ai_review.py is deliberately DB-free, so the worker is the only place
    these settings can be read — if this pass-through breaks, the review
    silently runs on the module defaults and every settings change is inert."""
    _seed_for_review(db_path, dirs, monkeypatch)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_model', 'gemini-3.6-flash')")
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_fps', '20')")
    con.commit()
    con.close()

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert run.call_args.kwargs["model"] == "gemini-3.6-flash"
    assert run.call_args.kwargs["fps"] == "20"


def test_handle_render_success_uses_review_defaults_when_unset(db_path, dirs, monkeypatch):
    _seed_for_review(db_path, dirs, monkeypatch)
    monkeypatch.delenv("AI_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("AI_REVIEW_FPS", raising=False)

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "fine"}) as run:
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

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
    monkeypatch.setattr(worker, "DB_PATH", str(db_path))
    assert worker._max_ai_review_loops() == 1
    assert worker._max_render_retries() == 1

    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('ai_review_max_loops', '2')")
    con.commit()
    con.close()
    assert worker._max_ai_review_loops() == 2
    # ...and the render budget is untouched by that write.
    assert worker._max_render_retries() == 1


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
    worker._handle_render_failure("vid-1", "boom")
    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"

    for _ in range(1):
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET status = 'RENDERING' WHERE id = 'vid-1'")
        con.commit()
        con.close()
        worker._handle_render_failure("vid-1", "boom")

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

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "many problems", "must_fix": [],
                                          "suggestions": [], "feedback": feedback}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    assert _read_video(db_path)["gemini_feedback"] == feedback


def test_long_review_comment_is_truncated_and_says_so(db_path, dirs, monkeypatch):
    """The comment stays capped, but silently clipping it would let the agent
    mistake a clipped review for a short one and miss blocking defects."""
    _seed_for_review(db_path, dirs, monkeypatch)
    feedback = _long_review()

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "many problems", "must_fix": [],
                                          "suggestions": [], "feedback": feedback}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "gemini_feedback" in body        # points at the complete copy
    assert "truncated" in body
    for c in _read_comments(db_path):
        assert len(c["content"]) <= worker._COMMENT_MAX_CHARS


def test_short_review_comment_is_untouched(db_path, dirs, monkeypatch):
    """The truncation marker must not appear on a review that fits."""
    _seed_for_review(db_path, dirs, monkeypatch)

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "fine", "must_fix": [], "suggestions": [],
                                          "feedback": "**Overall:** fine.\n\nNo blocking errors."}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "truncated" not in body


def test_truncate_comment_helper_boundaries():
    assert worker._truncate_comment("") == ""
    exact = "x" * worker._COMMENT_MAX_CHARS
    assert worker._truncate_comment(exact) == exact          # at the cap, untouched
    over = worker._truncate_comment("y" * (worker._COMMENT_MAX_CHARS + 1))
    assert len(over) <= worker._COMMENT_MAX_CHARS            # never grows past the cap
    assert over.endswith("for the complete review.")


def test_error_comment_keeps_the_routing_clause_when_the_error_is_long(db_path, dirs, monkeypatch):
    """httpx embeds the whole request URL in its error strings, so a review
    error can easily exceed the comment cap. The routing statement has to
    survive that: a comment that says an error happened but not where the
    video went is worse than no comment."""
    _seed_for_review(db_path, dirs, monkeypatch)
    huge_error = "Gemini review failed: " + ("u" * 5000)

    with mock.patch.object(worker.ai_review, "run_ai_review",
                            return_value={"overall": "", "must_fix": [], "suggestions": [],
                                          "feedback": "AI review did not run: boom",
                                          "error": huge_error}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")

    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "advancing to VIDEO_READY" in body
    assert _read_video(db_path)["status"] == "VIDEO_READY"   # fail-open preserved
    for c in _read_comments(db_path):
        assert len(c["content"]) <= worker._COMMENT_MAX_CHARS


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
    assert worker._setting("gemini_api_key", "") == "from-db"


def test_setting_falls_back_to_env_when_no_row_exists(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert worker._setting("gemini_api_key", "") == "from-env"


def test_blank_row_falls_through_to_env(db_path, monkeypatch):
    """The regression guard: onboarding writes "" for an unsupplied key, and a
    stack that supplies it via `environment:` would otherwise lose AI review."""
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "")
    assert worker._setting("gemini_api_key", "") == "from-env"


def test_blank_row_and_no_env_yields_the_default(db_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _row(db_path, "gemini_api_key", "")
    assert worker._setting("gemini_api_key", "fallback") == "fallback"


def test_blank_row_does_not_break_the_int_settings(db_path, monkeypatch):
    """int("") would raise; the accessors catch it, but falling through means
    the configured default applies instead of the hardcoded one."""
    monkeypatch.delenv("MAX_RENDER_RETRIES", raising=False)
    _row(db_path, "max_render_retries", "")
    assert worker._max_render_retries() == 1


def test_worker_matches_the_other_two_key_readers(db_path, monkeypatch):
    """mcp/server.py's key helpers and pipeline.py's _secret both use
    `stored or env`. Three readers of one table must not disagree."""
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "")
    assert worker._setting("gemini_api_key", "") == \
        (pipeline_module._secret({"gemini_api_key": ""}, "gemini_api_key", "GEMINI_API_KEY"))


# ── TMDEV-83: publishing poll + metrics poll ────────────────────────────────
#
# PUBLISHING is the first status in this codebase that Flask sets and the worker
# only observes — RENDER_QUEUED and RENDERING are both set by the worker itself.
# That is why it needs its own backstop rather than inheriting the render one.

def _publishing_video(db_path, vid="vid-pub", accounts=("spc_yt",), post_id="sp_1",
                      created_at=None, status="PUBLISHING"):
    # Defaults to now: an old created_at trips the wall-clock backstop, which is
    # exactly what the backstop tests pass an explicit date to do.
    created_at = created_at or worker.db._now()
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute(
        "INSERT INTO videos (id, project_id, topic, strategy, status, created_at, updated_at)"
        " VALUES (?,'p','T','manual',?, 'now','now')", (vid, status))
    for i, account in enumerate(accounts):
        con.execute(
            "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
            " postforme_post_id, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?, 'PENDING', ?, ?)",
            (f"{vid}-pub{i}", vid, "youtube", account, post_id, created_at, created_at))
    con.commit()
    con.close()
    return vid


def _rows(db_path, vid="vid-pub"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    pubs = [dict(r) for r in con.execute(
        "SELECT * FROM video_publications WHERE video_id = ? ORDER BY id", (vid,))]
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    return status, pubs


def _result(account, *, success=True, url="https://yt/1", error=None):
    return {"id": f"spr_{account}", "social_account_id": account, "post_id": "sp_1",
            "success": success, "error": error,
            "platform_data": {"id": "plat1", "url": url} if success else {}}


def _enable(db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('publishing_enabled','true')")
    con.execute("INSERT OR REPLACE INTO settings VALUES ('postforme_api_key','pfm')")
    con.commit()
    con.close()


def test_a_video_stays_publishing_until_every_target_has_reported(db_path):
    """There is no "pending" result: a target that has not published yet simply
    has no row. Completion is a row count, never a status field."""
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a", "spc_b"))
    with mock.patch("postforme.get_post_results", return_value=[_result("spc_a")]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert [p["status"] for p in pubs] == ["PUBLISHED", "PENDING"]


def test_all_targets_succeeding_publishes_the_video(db_path):
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a", "spc_b"))
    with mock.patch("postforme.get_post_results",
                    return_value=[_result("spc_a", url="https://yt/a"),
                                  _result("spc_b", url="https://ig/b")]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHED"
    assert [p["post_url"] for p in pubs] == ["https://yt/a", "https://ig/b"]
    assert all(p["published_at"] for p in pubs)


def test_a_partial_success_still_counts_as_published(db_path):
    """There is no un-publish. A video live on one account IS published, and
    calling it FAILED would lie about the account that did post."""
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a", "spc_b"))
    with mock.patch("postforme.get_post_results",
                    return_value=[_result("spc_a"),
                                  _result("spc_b", success=False,
                                          error={"message": "account disconnected"})]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHED"
    assert pubs[0]["status"] == "PUBLISHED"
    assert pubs[1]["status"] == "FAILED"
    assert "account disconnected" in pubs[1]["error"]


def test_every_target_failing_fails_the_video(db_path):
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a",))
    with mock.patch("postforme.get_post_results",
                    return_value=[_result("spc_a", success=False, error={"message": "nope"})]):
        worker._poll_publishing_videos()
    status, _ = _rows(db_path)
    assert status == "FAILED"


def test_a_target_that_never_reports_is_settled_by_the_wall_clock_backstop(db_path):
    """Without this a silent target wedges the video in PUBLISHING forever.

    Deliberately time-based rather than a retry counter like render_fail_count:
    a publish has no crash to count, only an absence.
    """
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a", "spc_b"),
                      created_at="2020-01-01T00:00:00Z")
    with mock.patch("postforme.get_post_results", return_value=[_result("spc_a")]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHED"
    assert pubs[1]["status"] == "FAILED"
    assert "did not report" in pubs[1]["error"]


def test_the_backstop_measures_from_the_publication_not_the_video(db_path):
    """videos.updated_at is the worker's FIFO ordering key for the atomic render
    claim. Timing a publish off it would couple two unrelated mechanisms — and
    the poll itself touches it."""
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a",), created_at="2020-01-01T00:00:00Z")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET updated_at = ?", (worker.db._now(),))
    con.commit()
    con.close()
    with mock.patch("postforme.get_post_results", return_value=[]):
        worker._poll_publishing_videos()
    status, _ = _rows(db_path)
    assert status == "FAILED"


def test_a_postforme_outage_leaves_the_video_alone_for_the_next_tick(db_path):
    """An outage is not a publish failure. Marking the video FAILED because the
    status API blinked would strand a video that is live on every platform."""
    _enable(db_path)
    _publishing_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.get_post_results", side_effect=pfm.PostformeError("503")):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert pubs[0]["status"] == "PENDING"


def test_the_poll_does_nothing_when_publishing_is_disabled(db_path):
    _publishing_video(db_path)
    with mock.patch("postforme.get_post_results") as results:
        worker._poll_publishing_videos()
    results.assert_not_called()


def test_a_publishing_video_with_no_rows_is_failed_rather_than_wedged(db_path):
    """Only reachable if a publish half-committed — and only after postforme
    confirms no post exists. Leaving it PUBLISHING would be a permanent stall;
    failing it *without* asking would abandon a live social post.

    The lookup is mocked deliberately: without it this test made a real network
    call to the live API and passed for the wrong reason (a 401 deferring it).
    """
    _enable(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, created_at,"
                " updated_at) VALUES ('vid-orphan','p','T','manual','PUBLISHING','n','n')")
    con.commit()
    con.close()
    with mock.patch("postforme.find_post_by_external_id", return_value=None):
        worker._poll_publishing_videos()
    status, _ = _rows(db_path, "vid-orphan")
    assert status == "FAILED"


# ── metrics ──

def _published(db_path, vid="vid-pub", accounts=("spc_yt",)):
    _publishing_video(db_path, vid=vid, accounts=accounts, status="PUBLISHED")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE video_publications SET status = 'PUBLISHED',"
                " post_url = 'https://yt/1', published_at = 'now'")
    con.commit()
    con.close()


def _metrics(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM video_metrics ORDER BY id")]
    con.close()
    return rows


# social_post_id is what ties a feed entry back to a publication — one
# POST /social-posts spans every target, so all of a video's publications carry
# that same id. The real payload includes it; an earlier fixture here did not,
# which let a version that just took entries[0] blindly look correct.
FEED = {"data": [{"platform": "youtube", "social_post_id": "sp_1",
                  "platform_post_id": "plat1",
                  "metrics": {"views": 120, "likes": 9, "comments": 2, "shares": 1}}],
        "meta": {"has_more": False, "next": None}}


def test_a_metrics_pass_snapshots_every_published_target(db_path):
    _enable(db_path)
    _published(db_path)
    with mock.patch("postforme.get_account_feed", return_value=FEED):
        worker._poll_video_metrics()
    rows = _metrics(db_path)
    assert len(rows) == 1
    assert (rows[0]["views"], rows[0]["likes"]) == (120, 9)
    assert json.loads(rows[0]["raw_json"])["views"] == 120


def test_metrics_are_a_time_series_not_an_upsert(db_path):
    """History cannot be backfilled. Overwriting would leave the analytics page
    able to show a number but never a trend."""
    _enable(db_path)
    _published(db_path)
    with mock.patch("postforme.get_account_feed", return_value=FEED):
        worker._poll_video_metrics()
        worker._force_metrics_due(db_path)
        worker._poll_video_metrics()
    assert len(_metrics(db_path)) == 2


def test_metrics_are_rate_limited_between_passes(db_path):
    """Every published video is polled on every pass, so an unthrottled loop
    would hammer postforme once per worker iteration."""
    _enable(db_path)
    _published(db_path)
    with mock.patch("postforme.get_account_feed", return_value=FEED) as feed:
        worker._poll_video_metrics()
        worker._poll_video_metrics()
    assert feed.call_count == 1


def test_a_failed_metrics_fetch_does_not_stop_the_other_publications(db_path):
    """One broken account must not blind the whole analytics page.

    Two *accounts*, deliberately: the pass walks one feed per account, so two
    videos on the same account would be a single call and could not show this.
    """
    _enable(db_path)
    _published(db_path, vid="vid-a", accounts=("spc_a",))
    _published(db_path, vid="vid-b", accounts=("spc_b",))
    import postforme as pfm
    with mock.patch("postforme.get_account_feed",
                    side_effect=[pfm.PostformeError("boom"), FEED]):
        worker._poll_video_metrics()
    assert len(_metrics(db_path)) == 1


def test_metrics_are_skipped_when_publishing_is_disabled(db_path):
    _published(db_path)
    with mock.patch("postforme.get_account_feed") as feed:
        worker._poll_video_metrics()
    feed.assert_not_called()


def test_two_videos_on_one_account_cost_a_single_feed_call(db_path):
    """The whole point of the per-account shape. Per publication this was two
    calls; at 5 requests/second a real library exceeded the limit and the 429s
    were caught and skipped, losing snapshots that cannot be backfilled."""
    _enable(db_path)
    _published(db_path, vid="vid-a")
    _published(db_path, vid="vid-b")
    feed = {"data": [
        {"platform": "youtube", "social_post_id": "sp_1", "metrics": {"views": 5}},
    ], "meta": {"has_more": False}}
    with mock.patch("postforme.get_account_feed", return_value=feed) as call:
        worker._poll_video_metrics()
    assert call.call_count == 1


def test_an_orphaned_post_is_adopted_rather_than_failed(db_path):
    """Flask leaves a video claimed when create_post fails ambiguously, and can
    also die between a successful create_post and the row insert. Failing the
    video without asking postforme would leave a live social post that nothing
    local knows about."""
    _enable(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, created_at,"
                " updated_at) VALUES ('vid-orphan','p','T','manual','PUBLISHING','n','n')")
    con.commit()
    con.close()

    orphan = {"id": "sp_recovered", "social_accounts": [
        {"id": "spc_yt", "platform": "youtube"}, {"id": "spc_ig", "platform": "instagram"}]}
    with mock.patch("postforme.find_post_by_external_id", return_value=orphan), \
         mock.patch("postforme.get_post_results", return_value=[]):
        worker._poll_publishing_videos()

    status, pubs = _rows(db_path, "vid-orphan")
    assert status == "PUBLISHING", "adopted, not failed — it keeps polling"
    assert sorted(p["platform"] for p in pubs) == ["instagram", "youtube"]
    assert all(p["postforme_post_id"] == "sp_recovered" for p in pubs)


def test_an_adopted_post_then_settles_normally(db_path):
    _enable(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, created_at,"
                " updated_at) VALUES ('vid-orphan','p','T','manual','PUBLISHING','n','n')")
    con.commit()
    con.close()
    orphan = {"id": "sp_r", "social_accounts": [{"id": "spc_yt", "platform": "youtube"}]}
    with mock.patch("postforme.find_post_by_external_id", return_value=orphan), \
         mock.patch("postforme.get_post_results", return_value=[]):
        worker._poll_publishing_videos()
    with mock.patch("postforme.get_post_results",
                    return_value=[_result("spc_yt", url="https://yt/r")]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path, "vid-orphan")
    assert status == "PUBLISHED"
    assert pubs[0]["post_url"] == "https://yt/r"


def test_a_lookup_failure_defers_rather_than_failing_the_video(db_path):
    """An outage while checking must not be read as "no post exists"."""
    _enable(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, created_at,"
                " updated_at) VALUES ('vid-orphan','p','T','manual','PUBLISHING','n','n')")
    con.commit()
    con.close()
    import postforme as pfm
    with mock.patch("postforme.find_post_by_external_id",
                    side_effect=pfm.PostformeError("503")):
        worker._poll_publishing_videos()
    status, _ = _rows(db_path, "vid-orphan")
    assert status == "PUBLISHING"


# ── TMDEV-97: a publish in flight must never be failed ──────────────────────
#
# Flask writes the publication rows at the claim, with an empty post id, and
# fills the post id in once create_post returns. Before that, a worker tick
# landing mid-upload saw PUBLISHING with no rows, found no post yet, and failed
# a video that went live moments later.

def _live(post_id="sp_1", accounts=("spc_yt",), created_at="2026-09-19T10:00:00Z"):
    return {"id": post_id, "social_accounts": [{"id": a, "platform": "youtube"} for a in accounts],
            "created_at": created_at, "results": [], "live": True}


def _dead(post_id="sp_old", accounts=("spc_yt",)):
    return {"id": post_id, "social_accounts": [{"id": a, "platform": "youtube"} for a in accounts],
            "created_at": "2026-09-01T10:00:00Z", "live": False,
            "results": [_result(a, success=False, error={"message": "rejected"})
                        for a in accounts]}


def test_a_worker_pass_during_the_upload_does_not_fail_the_publish(db_path, tmp_path,
                                                                   monkeypatch):
    """The acceptance regression: a worker pass BETWEEN the claim and
    create_post. It drives the real Flask route and runs the real worker poll
    from inside upload_media, which is exactly where the observed publish was
    failed — postforme had no post yet because the upload was still going."""
    from flask import Flask
    monkeypatch.setenv("TUBEMATIC_DB", db_path)
    out = tmp_path / "out"
    (out / "p").mkdir(parents=True)
    (out / "p" / "vid-up.mp4").write_bytes(b"\x00mp4")
    monkeypatch.setattr(pipeline_module, "OUTPUT_DIR", out)
    _enable(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('publishing_accounts', '[\"spc_yt\"]')")
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, video_path,"
                " created_at, updated_at) VALUES ('vid-up','p','T','manual','VIDEO_APPROVED',"
                " '/output_videos/p/vid-up.mp4', 'now','now')")
    con.commit()
    con.close()

    mid_upload = {}

    def upload_while_the_worker_ticks(*args, **kwargs):
        # postforme has no post yet: the upload is what precedes create_post.
        with mock.patch("postforme.find_post_by_external_id", return_value=None):
            worker._poll_publishing_videos()
            worker._poll_publishing_videos()
        mid_upload["status"], mid_upload["pubs"] = _rows(db_path, "vid-up")

    app = Flask(__name__)
    app.register_blueprint(pipeline_module.create_pipeline_blueprint())
    with app.test_client() as client, \
         mock.patch("postforme.list_accounts",
                    return_value=[{"id": "spc_yt", "platform": "youtube"}]), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media", side_effect=upload_while_the_worker_ticks), \
         mock.patch("postforme.create_post", return_value={"id": "sp_1"}):
        r = client.post("/videos/vid-up/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 201
    assert mid_upload["status"] == "PUBLISHING", "failed mid-upload — the TMDEV-97 race"
    assert [p["postforme_post_id"] for p in mid_upload["pubs"]] == [""]

    with mock.patch("postforme.get_post_results", return_value=[_result("spc_yt")]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path, "vid-up")
    assert status == "PUBLISHED"
    assert pubs[0]["post_url"] == "https://yt/1"


def test_an_in_progress_publish_with_no_post_waits_for_the_deadline(db_path):
    _enable(db_path)
    _publishing_video(db_path, post_id="")
    with mock.patch("postforme.find_post_by_external_id", return_value=None), \
         mock.patch("postforme.get_post_results") as results:
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert pubs[0]["status"] == "PENDING"
    results.assert_not_called()


def test_an_in_progress_publish_past_the_deadline_with_no_post_is_failed(db_path):
    """A Flask that died mid-publish is still caught — just after the deadline,
    and with its rows kept, since they are what offers Retry publishing."""
    _enable(db_path)
    _publishing_video(db_path, post_id="", created_at="2020-01-01T00:00:00Z")
    with mock.patch("postforme.find_post_by_external_id", return_value=None):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "FAILED"
    assert pubs[0]["status"] == "FAILED"
    assert "deadline" in pubs[0]["error"]


def test_a_live_post_is_adopted_by_in_progress_rows_before_the_deadline(db_path):
    """An ambiguous create_post that did create the post is recovered on the
    next tick, as before — without waiting out the deadline."""
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_yt", "spc_ig"), post_id="")
    with mock.patch("postforme.find_post_by_external_id",
                    return_value=_live(accounts=("spc_yt", "spc_ig"))):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert [p["postforme_post_id"] for p in pubs] == ["sp_1", "sp_1"]
    assert len(pubs) == 2, "adopted onto the existing rows, not duplicated"


def test_a_dead_post_is_not_adopted_before_the_deadline(db_path):
    """A dead post under this external_id can be an earlier attempt's. Adopting
    it mid-upload would fail the new publish on the old one's errors."""
    _enable(db_path)
    _publishing_video(db_path, post_id="")
    with mock.patch("postforme.find_post_by_external_id", return_value=_dead()):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert pubs[0]["postforme_post_id"] == ""


def test_a_dead_post_past_the_deadline_settles_with_its_real_errors(db_path):
    _enable(db_path)
    _publishing_video(db_path, post_id="", created_at="2020-01-01T00:00:00Z")
    dead = _dead()
    with mock.patch("postforme.find_post_by_external_id", return_value=dead):
        worker._poll_publishing_videos()
    with mock.patch("postforme.get_post_results", return_value=dead["results"]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "FAILED"
    assert "rejected" in pubs[0]["error"]


def test_a_publish_request_always_finishes_before_the_worker_deadline():
    """The invariant the late-response handling rests on. Past the deadline
    the worker fails an in-flight publish and Retry can move the video on, so
    a create_post landing afterwards would attach a live post to the wrong
    attempt, or to none. The upload cap is what makes that impossible: its
    worst case (the cap, one stalled write and the response read at the
    per-operation timeout) plus the short calls around it must stay under the
    deadline. Raising either timeout without the other breaks it."""
    import postforme as pfm
    worst = (pfm.UPLOAD_MAX_SECS + 2 * pfm._UPLOAD_TIMEOUT_SECS
             + 10 * pfm._TIMEOUT_SECS)
    assert worst < worker._PUBLISH_TIMEOUT_SECS


def test_adopting_a_post_restarts_the_deadline(db_path):
    """A post adopted near the deadline must get a full window for its
    platforms to report, or its unreported targets fail on the next pass."""
    _enable(db_path)
    _publishing_video(db_path, post_id="", created_at="2020-01-01T00:00:00Z")
    with mock.patch("postforme.find_post_by_external_id", return_value=_live()):
        worker._poll_publishing_videos()
    with mock.patch("postforme.get_post_results", return_value=[]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert pubs[0]["status"] == "PENDING"


def test_expiry_never_fails_a_video_whose_post_id_was_filled_in(db_path):
    """The expiry writes are one transaction and each re-checks that the
    publish is still in flight. A row that gained a post id before the
    expiry ran keeps the video PUBLISHING, so the worker keeps settling it."""
    _enable(db_path)
    _publishing_video(db_path, accounts=("spc_a", "spc_b"), post_id="",
                      created_at="2020-01-01T00:00:00Z")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE video_publications SET postforme_post_id = 'sp_1'"
                " WHERE social_account_id = 'spc_a'")
    con.commit()
    con.close()
    _, pubs = _rows(db_path)
    with mock.patch("postforme.find_post_by_external_id", return_value=None):
        worker._settle_in_progress("vid-pub", "pfm",
                                   [p for p in pubs if not p["postforme_post_id"]])
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert {p["social_account_id"]: p["status"] for p in pubs} == \
        {"spc_a": "PENDING", "spc_b": "FAILED"}


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
    with mock.patch.object(worker.ai_review, "run_ai_review",
                           return_value={"overall": "", "must_fix": [], "suggestions": [],
                                         "feedback": "ok", "usage": usage}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    [row] = _usage_rows(db_path)
    assert (row["service"], row["model"], row["operation"], row["video_id"]) == \
        ("gemini", "gemini-2.5-flash", "ai_review", "vid-1")
    assert json.loads(row["units"]) == {"input": 66000, "output": 300}
    assert row["cost_basis"] == "priced"  # gemini-2.5-flash is in the built-in snapshot


def test_a_review_without_usage_records_nothing(db_path, dirs, monkeypatch):
    """A review that never reached Gemini (no usage key) was not billed."""
    _review_ready(db_path, dirs, monkeypatch)
    with mock.patch.object(worker.ai_review, "run_ai_review",
                           return_value={"overall": "", "must_fix": [], "suggestions": [],
                                         "feedback": "AI review did not run: x", "error": "x"}):
        worker._handle_render_success("vid-1", "/output_videos/proj-1/vid-1.mp4")
    assert _usage_rows(db_path) == []


def test_the_price_sync_runs_weekly_not_every_pass(db_path):
    with mock.patch.object(worker.tprices, "sync_prices",
                           return_value={"ok": True, "updated": [], "rejected": [],
                                         "missing": [], "error": ""}) as sync:
        worker._sync_prices_if_due()
        worker._sync_prices_if_due()
    assert sync.call_count == 1


def test_a_failing_price_sync_never_stops_the_worker(db_path):
    with mock.patch.object(worker.tprices, "sync_prices", side_effect=RuntimeError("boom")):
        worker._sync_prices_if_due()  # must not raise
    # Stamped before the work, so a sync that dies does not retry 20 s later.
    con = sqlite3.connect(db_path)
    stamp = con.execute("SELECT value FROM settings WHERE key = 'last_price_sync_at'").fetchone()
    con.close()
    assert stamp is not None


# ── TMDEV-133: scheduled publishing ──────────────────────────────────────────

def _scheduled_video(db_path, scheduled_at, vid="vid-pub", status="SCHEDULED",
                     created_at="2020-01-01T00:00:00Z", post_id="sp_1"):
    # created_at defaults to long ago: a scheduled post's rows are written at
    # the claim, possibly days before it goes out.
    _publishing_video(db_path, vid=vid, status=status, created_at=created_at, post_id=post_id)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET scheduled_at = ?, scheduled_timezone = 'UTC' WHERE id = ?",
                (scheduled_at, vid))
    con.commit()
    con.close()
    return vid


def test_a_scheduled_video_is_left_alone_until_it_is_due(db_path):
    _enable(db_path)
    _scheduled_video(db_path, "2999-01-01T00:00:00Z")
    with mock.patch("postforme.get_post_results") as results:
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "SCHEDULED"
    assert pubs[0]["status"] == "PENDING"
    results.assert_not_called()


def test_a_due_scheduled_video_is_watched_with_a_fresh_deadline(db_path):
    """Moved to PUBLISHING with created_at reset. Without the reset the rows,
    written when it was scheduled, are already past the one-hour deadline and
    every target would fail before postforme had even sent the post."""
    _enable(db_path)
    _scheduled_video(db_path, "2020-06-01T00:00:00Z")
    with mock.patch("postforme.get_post_results", return_value=[]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHING"
    assert pubs[0]["status"] == "PENDING"
    assert pubs[0]["created_at"] > "2020-01-01T00:00:00Z"


def test_a_due_scheduled_video_settles_on_its_results(db_path):
    _enable(db_path)
    _scheduled_video(db_path, "2020-06-01T00:00:00Z")
    with mock.patch("postforme.get_post_results", return_value=[_result("spc_yt")]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "PUBLISHED"
    assert pubs[0]["status"] == "PUBLISHED"


def test_a_scheduled_video_is_not_moved_while_publishing_is_off(db_path):
    """Off means no postforme polling at all — the same as for PUBLISHING. It
    is picked up, with a fresh deadline, once publishing is turned back on."""
    _scheduled_video(db_path, "2020-06-01T00:00:00Z")
    worker._poll_publishing_videos()
    status, _ = _rows(db_path)
    assert status == "SCHEDULED"


def test_an_adopted_post_that_is_not_due_waits_in_scheduled(db_path):
    """A scheduled publish whose create_post was ambiguous: the worker adopts
    the post by external_id. It has no results until it goes out, so settling
    it now would fail it at the deadline — it waits in SCHEDULED instead."""
    _enable(db_path)
    _scheduled_video(db_path, "2999-01-01T00:00:00Z", status="PUBLISHING", post_id="",
                     created_at=None)
    with mock.patch("postforme.find_post_by_external_id", return_value=_live()):
        worker._poll_publishing_videos()   # adopts
    with mock.patch("postforme.get_post_results") as results:
        worker._poll_publishing_videos()   # parks
    status, pubs = _rows(db_path)
    assert status == "SCHEDULED"
    assert pubs[0]["postforme_post_id"] == "sp_1"
    results.assert_not_called()


def test_a_future_schedule_is_never_failed_by_the_deadline(db_path):
    _enable(db_path)
    _scheduled_video(db_path, "2999-01-01T00:00:00Z", status="PUBLISHING")
    with mock.patch("postforme.get_post_results", return_value=[]):
        worker._poll_publishing_videos()
    status, pubs = _rows(db_path)
    assert status == "SCHEDULED"
    assert pubs[0]["status"] == "PENDING"
