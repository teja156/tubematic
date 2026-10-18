"""Video retention, archiving and manual delete (TMDEV-84).

Covers pipeline.archive_video through both of its callers — the DELETE route
and the render worker's retention sweep — plus every query that must leave
archived rows out, and the freeze that keeps an archived row out of the
pipeline for good.

Run from renderer/api/: pytest tests/test_retention.py
"""
import json
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
import worker

_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ago(days: float) -> str:
    return time.strftime(_FMT, time.gmtime(time.time() - days * 86400))


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    out, jobs = tmp_path / "output_videos", tmp_path / "jobs"
    out.mkdir()
    jobs.mkdir()
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)
    monkeypatch.setattr(pipeline, "JOBS_DIR", jobs)
    monkeypatch.setattr(worker, "DB_PATH", db)
    pipeline._init_db(db)
    return SimpleNamespace(db=db, out=out, jobs=jobs)


@pytest.fixture
def client(env):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(pipeline.create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sql(env, query, params=()):
    con = sqlite3.connect(env.db)
    con.execute(query, params)
    con.commit()
    con.close()


def _video(env, vid="vid-1", status="PUBLISHED", project="proj-1", files=True,
           archived_at=None, updated_at=None):
    """Seed a video, and by default a real mp4 and job dir for it."""
    if project:
        _sql(env, "INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?, ?, ?)",
             (project, project, _ago(30)))
    mp4 = env.out / (project or "default_proj") / f"{vid}.mp4"
    job_dir = env.jobs / vid
    if files:
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"mp4")
        (job_dir / "images").mkdir(parents=True)
        (job_dir / "audio.mp3").write_bytes(b"audio")
        (job_dir / "images" / "a.png").write_bytes(b"png")
    _sql(env,
         "INSERT INTO videos (id, project_id, topic, status, video_path, archived_at,"
         " created_at, updated_at) VALUES (?, ?, 'DNS resolution', ?, ?, ?, ?, ?)",
         (vid, project, status, f"/output_videos/{project or 'default_proj'}/{vid}.mp4",
          archived_at, _ago(60), updated_at if updated_at is not None else _ago(60)))
    return mp4, job_dir


_pub_seq = iter(range(10**6))


def _publication(env, vid="vid-1", published_at=None, status="PUBLISHED"):
    _sql(env,
         "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
         " status, post_url, published_at, created_at, updated_at)"
         " VALUES (?, ?, 'youtube', 'spc_yt', ?, 'https://yt/1', ?, ?, ?)",
         (f"pub-{next(_pub_seq)}", vid, status, published_at if published_at is not None else "",
          _ago(60), _ago(60)))


def _row(env, vid="vid-1"):
    con = sqlite3.connect(env.db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM videos WHERE id = ?", (vid,)).fetchone()
    con.close()
    return dict(row) if row else None


def _comments(env, vid="vid-1"):
    con = sqlite3.connect(env.db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM comments WHERE video_id = ? ORDER BY id", (vid,))]
    con.close()
    return rows


def _setting(env, key, value):
    _sql(env, "INSERT INTO settings (key, value) VALUES (?, ?)"
              " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


# ── the deletable set ────────────────────────────────────────────────────────

DELETABLE = {"TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED", "SCRIPT_READY",
             "VIDEO_READY", "VIDEO_APPROVED", "PUBLISHED", "FAILED"}
BLOCKED = pipeline.VALID_VIDEO_STATUSES - DELETABLE


def test_the_deletable_set_is_pinned():
    """Processing statuses and the two scene-claim statuses are blocked. The
    claim statuses are the non-obvious half: the claim lives only in MCP, so
    blocking the statuses it can exist in is the guard — not a claim read.
    SCHEDULED is blocked because postforme holds a post that will go out."""
    assert pipeline.DELETABLE_STATUSES == DELETABLE
    assert BLOCKED == {"VOICING", "RENDER_QUEUED", "RENDERING", "SCHEDULED", "PUBLISHING",
                       "VOICE_READY", "REVISION_REQUESTED"}


def test_the_dashboard_copy_of_the_deletable_set_matches():
    """The dashboard decides whether to *show* Delete from its own copy. The
    two are kept in sync by comment alone, so read the TS source and compare —
    the constant test above cannot see the other process's copy."""
    import pathlib
    import re
    src = (pathlib.Path(__file__).resolve().parents[3]
           / "dashboard" / "lib" / "videoStatus.ts").read_text()
    block = re.search(r"DELETABLE_STATUSES[^=]*=\s*new Set<VideoStatus>\(\[(.*?)\]\)", src, re.S)
    assert block, "DELETABLE_STATUSES not found in dashboard/lib/videoStatus.ts"
    assert set(re.findall(r'"([A-Z_]+)"', block.group(1))) == pipeline.DELETABLE_STATUSES


# ── DELETE /videos/<id> ──────────────────────────────────────────────────────

@pytest.mark.parametrize("status", sorted(DELETABLE))
def test_delete_removes_the_files_and_archives_the_row(client, env, status):
    mp4, job_dir = _video(env, status=status)
    r = client.delete("/videos/vid-1")
    assert r.status_code == 200, r.data
    body = json.loads(r.data)
    assert body["ok"] and body["file_errors"] == []
    assert not mp4.exists() and not job_dir.exists()
    row = _row(env)
    assert row is not None, "the record must be kept"
    assert row["archived_at"] == body["archived_at"]
    assert row["video_path"] == "", "a stale video_path would render a dead player"
    assert row["status"] == status, "archiving must not overwrite what the video was"
    assert [c["author"] for c in _comments(env)] == ["human"]


@pytest.mark.parametrize("status", sorted(BLOCKED))
def test_delete_is_refused_for_processing_and_claim_statuses(client, env, status):
    mp4, job_dir = _video(env, status=status)
    r = client.delete("/videos/vid-1")
    assert r.status_code == 409
    assert json.loads(r.data)["current"] == status
    assert mp4.exists() and job_dir.exists()
    assert _row(env)["archived_at"] is None
    assert _comments(env) == []


def test_deleting_an_archived_video_again_is_a_conflict(client, env):
    _video(env, status="VIDEO_READY", files=False, archived_at=_ago(1))
    r = client.delete("/videos/vid-1")
    assert r.status_code == 409
    assert "already archived" in json.loads(r.data)["error"]


def test_deleting_an_unknown_video_is_404(client):
    assert client.delete("/videos/nope").status_code == 404


def test_missing_files_do_not_fail_the_delete(client, env):
    _video(env, status="FAILED", files=False)
    r = client.delete("/videos/vid-1")
    assert r.status_code == 200
    assert json.loads(r.data)["file_errors"] == []
    assert _row(env)["archived_at"]


def test_a_project_less_video_has_its_mp4_found_under_default_proj(client, env):
    mp4, _ = _video(env, status="VIDEO_READY", project=None)
    assert client.delete("/videos/vid-1").status_code == 200
    assert not mp4.exists()


def test_a_file_removal_error_is_reported_and_the_row_stays_archived(client, env, monkeypatch):
    _video(env, status="VIDEO_READY")

    def boom(path, *a, **kw):
        raise PermissionError("read-only")

    monkeypatch.setattr(pipeline.shutil, "rmtree", boom)
    r = client.delete("/videos/vid-1")
    assert r.status_code == 200
    errors = json.loads(r.data)["file_errors"]
    assert len(errors) == 1 and "read-only" in errors[0]
    assert _row(env)["archived_at"]


def test_other_videos_files_are_untouched(client, env):
    _video(env, vid="vid-1", status="VIDEO_READY")
    other_mp4, other_job = _video(env, vid="vid-2", status="VIDEO_READY")
    assert client.delete("/videos/vid-1").status_code == 200
    assert other_mp4.exists() and other_job.exists()


# ── archived rows leave every list and count ─────────────────────────────────

def test_get_videos_excludes_archived_rows_by_default(client, env):
    _video(env, vid="live", status="PUBLISHED", files=False)
    _video(env, vid="gone", status="PUBLISHED", files=False, archived_at=_ago(1))
    assert [v["id"] for v in json.loads(client.get("/videos").data)] == ["live"]
    assert [v["id"] for v in json.loads(client.get("/videos?archived=only").data)] == ["gone"]
    both = {v["id"] for v in json.loads(client.get("/videos?archived=include").data)}
    assert both == {"live", "gone"}


def test_get_videos_rejects_an_unknown_archived_value(client):
    assert client.get("/videos?archived=yes").status_code == 400


def test_an_archived_video_is_still_served_by_id(client, env):
    _video(env, status="PUBLISHED", files=False, archived_at=_ago(1))
    r = client.get("/videos/vid-1")
    assert r.status_code == 200
    assert json.loads(r.data)["archived_at"]


def test_an_archived_workable_video_is_never_offered_to_the_agent(client, env):
    """The money path: poll.py reads /videos/workable, and a deleted
    TOPIC_APPROVED video must not be scripted and voiced anyway."""
    _video(env, vid="live", status="TOPIC_APPROVED", files=False)
    _video(env, vid="gone", status="TOPIC_APPROVED", files=False, archived_at=_ago(1))
    assert [v["id"] for v in json.loads(client.get("/videos/workable").data)] == ["live"]


def test_an_archived_checkpoint_video_is_not_actionable(client, env):
    _video(env, status="TOPIC_PROPOSED", files=False, archived_at=_ago(1))
    assert json.loads(client.get("/videos/actionable").data) == []


def test_stats_and_pipeline_status_leave_archived_rows_out(client, env):
    """proposed_count is the research pending cap's input — a deleted proposal
    counted there would throttle research forever."""
    _video(env, vid="live", status="TOPIC_PROPOSED", files=False)
    _video(env, vid="gone", status="TOPIC_PROPOSED", files=False, archived_at=_ago(1))
    _video(env, vid="gone2", status="TOPIC_APPROVED", files=False, archived_at=_ago(1))
    assert json.loads(client.get("/stats").data) == {"TOPIC_PROPOSED": 1}
    status = json.loads(client.get("/pipeline/status").data)
    assert status["proposed_count"] == 1
    assert status["workable_count"] == 0
    assert status["video_counts"] == {"TOPIC_PROPOSED": 1}


# ── an archived row is frozen ────────────────────────────────────────────────

def test_an_archived_video_cannot_be_patched(client, env):
    _video(env, status="SCRIPT_READY", files=False, archived_at=_ago(1))
    r = client.patch("/videos/vid-1", json={"status": "VOICING"})
    assert r.status_code == 409
    r = client.patch("/videos/vid-1", json={
        "status": "VOICING", "onlyIfCurrentStatus": "SCRIPT_READY"})
    assert r.status_code == 409
    assert _row(env)["status"] == "SCRIPT_READY"


def test_an_archived_video_cannot_be_published(client, env):
    _setting(env, "publishing_enabled", "true")
    _setting(env, "postforme_api_key", "pfm-key")
    _video(env, status="VIDEO_APPROVED", files=False, archived_at=_ago(1))
    r = client.post("/videos/vid-1/publish", json={"account_ids": ["spc_yt"]})
    assert r.status_code == 409
    assert _row(env)["status"] == "VIDEO_APPROVED"


# ── retention_days setting ───────────────────────────────────────────────────

def test_retention_days_defaults_to_7(client):
    assert json.loads(client.get("/settings").data)["retention_days"] == 7


@pytest.mark.parametrize("value", [0, 1, 365])
def test_retention_days_accepts_0_to_365(client, value):
    """0 is allowed — unlike log retention — and means 'never sweep'."""
    assert client.post("/settings", json={"retention_days": value}).status_code == 200
    assert json.loads(client.get("/settings").data)["retention_days"] == value


@pytest.mark.parametrize("value", [-1, 366])
def test_retention_days_outside_0_to_365_is_rejected(client, value):
    assert client.post("/settings", json={"retention_days": value}).status_code == 400


# ── the worker's retention sweep ─────────────────────────────────────────────

def _sweep(env):
    worker._force_retention_due(env.db)
    worker._sweep_retention()


def test_a_video_published_longer_ago_than_retention_is_swept(env):
    mp4, job_dir = _video(env)
    _publication(env, published_at=_ago(8))
    _sweep(env)
    row = _row(env)
    assert row["archived_at"] and row["video_path"] == ""
    assert row["status"] == "PUBLISHED"
    assert not mp4.exists() and not job_dir.exists()
    assert [c["author"] for c in _comments(env)] == ["agent"]


def test_a_recently_published_video_is_kept(env):
    mp4, _ = _video(env)
    _publication(env, published_at=_ago(6))
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


def test_the_latest_publication_is_the_clock(env):
    """Published to a second platform yesterday: the file is a day old in the
    sense that matters, whatever the first target's date says."""
    mp4, _ = _video(env)
    _publication(env, published_at=_ago(30))
    _publication(env, published_at=_ago(1))
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


@pytest.mark.parametrize("status", sorted(pipeline.VALID_VIDEO_STATUSES - {"PUBLISHED"}))
def test_a_video_that_is_not_published_is_never_swept(env, status):
    """An unpublished mp4 cost real ElevenLabs and render time; losing it to a
    sweep is unrecoverable. Even an old publication row does not qualify it.

    This is also the pin for unpublished_retention_days' default of 0: with the
    key unset, FAILED and TOPIC_REJECTED are as safe as every other status."""
    mp4, job_dir = _video(env, status=status)
    _publication(env, published_at=_ago(100))
    _sweep(env)
    assert _row(env)["archived_at"] is None
    assert mp4.exists() and job_dir.exists()


def test_a_published_video_with_no_usable_publish_time_is_never_swept(env):
    """published_at is NOT NULL DEFAULT '': '' < cutoff is true in SQL, so a
    naive MAX would read it as infinitely old and sweep on the first tick."""
    mp4, _ = _video(env)
    _publication(env, published_at="")
    _video(env, vid="vid-norows")
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()
    assert _row(env, "vid-norows")["archived_at"] is None


def test_a_failed_publication_does_not_start_the_clock(env):
    _video(env)
    _publication(env, published_at=_ago(30), status="FAILED")
    _publication(env, published_at=_ago(1))
    _sweep(env)
    assert _row(env)["archived_at"] is None


def test_retention_days_0_disables_the_sweep(env):
    mp4, _ = _video(env)
    _publication(env, published_at=_ago(400))
    _setting(env, "retention_days", "0")
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


def test_the_configured_retention_is_honoured(env):
    _video(env)
    _publication(env, published_at=_ago(3))
    _setting(env, "retention_days", "2")
    _sweep(env)
    assert _row(env)["archived_at"]


def test_a_corrupt_retention_value_falls_back_to_the_default(env):
    _video(env, vid="old")
    _publication(env, vid="old", published_at=_ago(8))
    _video(env, vid="young")
    _publication(env, vid="young", published_at=_ago(6))
    _setting(env, "retention_days", "banana")
    _sweep(env)
    assert _row(env, "old")["archived_at"] and _row(env, "young")["archived_at"] is None


def test_the_sweep_is_rate_limited_between_passes(env):
    _sweep(env)  # stamps
    _video(env)
    _publication(env, published_at=_ago(8))
    worker._sweep_retention()  # within the hour: no pass
    assert _row(env)["archived_at"] is None
    _sweep(env)
    assert _row(env)["archived_at"]


def test_one_video_failing_does_not_stop_the_pass(env, monkeypatch):
    for vid in ("vid-a", "vid-b"):
        _video(env, vid=vid)
        _publication(env, vid=vid, published_at=_ago(8))
    real = pipeline.archive_video
    calls = []

    def flaky(db_path, video_id, *a, **kw):
        calls.append(video_id)
        if len(calls) == 1:
            raise OSError("disk on fire")
        return real(db_path, video_id, *a, **kw)

    monkeypatch.setattr(pipeline, "archive_video", flaky)
    _sweep(env)
    assert len(calls) == 2
    archived = [v for v in ("vid-a", "vid-b") if _row(env, v)["archived_at"]]
    assert archived == [calls[1]]


def test_an_error_inside_the_pass_never_escapes(env, monkeypatch):
    """main() has no error handling; an escaping exception restarts the
    container, which _reconcile_rendering_videos counts as a render failure."""
    def boom():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(worker, "_sweep_retention_once", boom)
    worker._sweep_retention()  # must not raise


def test_metrics_survive_archiving(env):
    """Analytics are read from video_publications + video_metrics, neither of
    which archiving touches."""
    _video(env)
    _publication(env, published_at=_ago(8))
    _sweep(env)
    con = sqlite3.connect(env.db)
    assert con.execute("SELECT COUNT(*) FROM video_publications").fetchone()[0] == 1
    con.close()


# ── unpublished_retention_days: FAILED and TOPIC_REJECTED (TMDEV-134) ───────

UNPUBLISHED = {"FAILED", "TOPIC_REJECTED"}


def test_unpublished_retention_days_defaults_to_0(client):
    """Off by default: a failed video is paid-for output someone may still
    want to inspect, so sweeping it has to be asked for."""
    assert json.loads(client.get("/settings").data)["unpublished_retention_days"] == 0


@pytest.mark.parametrize("value", [0, 1, 365])
def test_unpublished_retention_days_accepts_0_to_365(client, value):
    assert client.post("/settings", json={"unpublished_retention_days": value}).status_code == 200
    assert json.loads(client.get("/settings").data)["unpublished_retention_days"] == value


@pytest.mark.parametrize("value", [-1, 366])
def test_unpublished_retention_days_outside_0_to_365_is_rejected(client, value):
    assert client.post("/settings", json={"unpublished_retention_days": value}).status_code == 400


def _unpublished_on(env, days="3"):
    _setting(env, "unpublished_retention_days", days)


def test_an_old_failed_video_is_swept_when_enabled(env):
    mp4, job_dir = _video(env, status="FAILED", updated_at=_ago(5))
    _unpublished_on(env)
    _sweep(env)
    row = _row(env)
    assert row["archived_at"] and row["video_path"] == ""
    assert row["status"] == "FAILED"
    assert not mp4.exists() and not job_dir.exists()
    comments = _comments(env)
    assert [c["author"] for c in comments] == ["agent"]
    assert "failed more than 3 day(s) ago" in comments[0]["content"]


def test_an_old_rejected_video_with_files_is_swept(env):
    """A direct PATCH can reject a video at any stage, so "rejected means no
    files" is a UI convention, not an invariant."""
    mp4, job_dir = _video(env, status="TOPIC_REJECTED", updated_at=_ago(5))
    _unpublished_on(env)
    _sweep(env)
    row = _row(env)
    assert row["archived_at"] and row["status"] == "TOPIC_REJECTED"
    assert not mp4.exists() and not job_dir.exists()
    assert "rejected more than 3 day(s) ago" in _comments(env)[0]["content"]


def test_an_old_rejected_topic_with_no_files_is_archived_cleanly(env, caplog):
    """User decision: every eligible row is archived, files or not, so old
    rejected topics leave the board for the Archive."""
    _video(env, status="TOPIC_REJECTED", files=False, updated_at=_ago(5))
    _unpublished_on(env)
    with caplog.at_level("ERROR"):
        _sweep(env)
    assert _row(env)["archived_at"]
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.parametrize("status", sorted(UNPUBLISHED))
def test_a_recently_failed_or_rejected_video_is_kept(env, status):
    mp4, _ = _video(env, status=status, updated_at=_ago(2))
    _unpublished_on(env)
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


@pytest.mark.parametrize(
    "status", sorted(pipeline.VALID_VIDEO_STATUSES - UNPUBLISHED - {"PUBLISHED"}))
def test_the_unpublished_key_never_reaches_other_statuses(env, status):
    mp4, job_dir = _video(env, status=status, updated_at=_ago(100))
    _unpublished_on(env)
    _sweep(env)
    assert _row(env)["archived_at"] is None
    assert mp4.exists() and job_dir.exists()


def test_the_unpublished_key_leaves_published_videos_alone(env):
    """Two keys, two independent passes: turning the published sweep off
    while turning this one on must not archive a published video."""
    mp4, _ = _video(env, updated_at=_ago(100))
    _publication(env, published_at=_ago(100))
    _setting(env, "retention_days", "0")
    _unpublished_on(env)
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


def test_retention_days_alone_never_touches_failed_videos(env):
    mp4, _ = _video(env, status="FAILED", updated_at=_ago(100))
    _setting(env, "retention_days", "1")
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


def test_both_passes_run_in_one_sweep(env):
    _video(env, vid="pub")
    _publication(env, vid="pub", published_at=_ago(8))
    _video(env, vid="failed", status="FAILED", updated_at=_ago(5))
    _unpublished_on(env)
    _sweep(env)
    assert _row(env, "pub")["archived_at"] and _row(env, "failed")["archived_at"]


def test_the_unpublished_pass_alone_is_rate_limited(env):
    """With retention_days at 0 the stamp must still be written, or an
    unpublished-only install would sweep on every loop tick."""
    _setting(env, "retention_days", "0")
    _unpublished_on(env)
    _sweep(env)  # stamps
    _video(env, status="FAILED", updated_at=_ago(5))
    worker._sweep_retention()  # within the hour: no pass
    assert _row(env)["archived_at"] is None
    _sweep(env)
    assert _row(env)["archived_at"]


def test_a_corrupt_unpublished_value_falls_back_to_off(env):
    mp4, _ = _video(env, status="FAILED", updated_at=_ago(100))
    _unpublished_on(env, "banana")
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


def test_a_retry_that_wins_the_race_is_not_archived(env, monkeypatch):
    """The status check lives in archive_video's UPDATE, so a video retried out
    of FAILED between the select and the archive is a conflict, not a loss."""
    mp4, _ = _video(env, status="FAILED", updated_at=_ago(5))
    _unpublished_on(env)
    real = pipeline.archive_video

    def retried_first(db_path, video_id, *a, **kw):
        _sql(env, "UPDATE videos SET status = 'RENDER_QUEUED' WHERE id = ?", (video_id,))
        return real(db_path, video_id, *a, **kw)

    monkeypatch.setattr(pipeline, "archive_video", retried_first)
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


# ── GET /retention/backlog ───────────────────────────────────────────────────

def test_backlog_counts_and_sizes_each_status(client, env):
    _video(env, vid="f1", status="FAILED")            # mp4 3 + audio 5 + png 3 = 11
    _video(env, vid="r1", status="TOPIC_REJECTED")    # 11
    _video(env, vid="r2", status="TOPIC_REJECTED", files=False)
    body = json.loads(client.get("/retention/backlog").data)
    assert body == {"failed": {"count": 1, "bytes": 11},
                    "rejected": {"count": 2, "bytes": 11}}


def test_backlog_leaves_out_archived_and_other_statuses(client, env):
    _video(env, vid="gone", status="FAILED", files=False, archived_at=_ago(1))
    _video(env, vid="pub", status="PUBLISHED")
    _video(env, vid="ready", status="VIDEO_READY")
    body = json.loads(client.get("/retention/backlog").data)
    assert body == {"failed": {"count": 0, "bytes": 0},
                    "rejected": {"count": 0, "bytes": 0}}


def test_backlog_ignores_the_retention_setting(client, env):
    """It answers "what would the key free", so it is useful before the key
    is turned on — which is the only time anyone needs it."""
    _video(env, vid="new", status="FAILED", updated_at=_ago(0))
    body = json.loads(client.get("/retention/backlog").data)
    assert body["failed"] == {"count": 1, "bytes": 11}


def test_backlog_is_read_only(client, env):
    mp4, job_dir = _video(env, status="FAILED")
    client.get("/retention/backlog")
    assert mp4.exists() and job_dir.exists() and _row(env)["archived_at"] is None


def test_a_clock_reset_that_wins_the_race_is_not_archived(env, monkeypatch):
    """The age is re-checked inside archive_video's UPDATE, not only by the
    sweep's SELECT: an edit that refreshes updated_at between the two, leaving
    the video FAILED, restarts the clock and must keep the files."""
    mp4, _ = _video(env, status="FAILED", updated_at=_ago(5))
    _unpublished_on(env)
    real = pipeline.archive_video

    def touched_first(db_path, video_id, *a, **kw):
        _sql(env, "UPDATE videos SET updated_at = ? WHERE id = ?", (_ago(0), video_id))
        return real(db_path, video_id, *a, **kw)

    monkeypatch.setattr(pipeline, "archive_video", touched_first)
    _sweep(env)
    assert _row(env)["archived_at"] is None and mp4.exists()


@pytest.mark.parametrize("vid", [".", "..", "../outside"])
def test_backlog_never_walks_outside_a_direct_job_dir(client, env, vid):
    """POST /videos takes a caller-supplied id, and the id is a path segment:
    '.' would size the whole jobs tree, '..' its parent. archive_video refuses
    the same ids for the same reason."""
    for i in range(3):
        _video(env, vid=f"big-{i}", status="VIDEO_READY")   # bytes under jobs/
    (env.jobs.parent / "outside").mkdir()
    (env.jobs.parent / "outside" / "f").write_bytes(b"x" * 100)
    _video(env, vid=vid, status="FAILED", files=False)
    assert json.loads(client.get("/retention/backlog").data)["failed"] == {"count": 1, "bytes": 0}


def test_backlog_sizes_the_mp4_as_one_file_never_a_directory(client, env):
    """A video_path whose basename is '..' resolves to a directory under
    OUTPUT_DIR; it must count 0, not the whole tree."""
    _video(env, vid="ok", status="VIDEO_READY")
    _video(env, vid="odd", status="FAILED", files=False)
    _sql(env, "UPDATE videos SET video_path = '/output_videos/proj-1/..' WHERE id = 'odd'")
    assert json.loads(client.get("/retention/backlog").data)["failed"] == {"count": 1, "bytes": 0}
