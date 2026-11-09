"""Tests for the worker's publishing poll, metrics poll and weekly price sync
(TMDEV-83, TMDEV-97, TMDEV-107, TMDEV-133). The render path that used to share
its loop is tested in test_render_agent.py.

Run from renderer/api/: pytest tests/test_worker.py
"""
import io
import json
import os
import sqlite3
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
    """Create real audio/timeline/scene-config files under the jobs dir."""
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
    """A Popen-shaped mock of a process that has already exited: worker.py
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


# ── The split from the renderer (TMDEV-188) ─────────────────────────────────

def test_the_worker_and_the_renderer_read_settings_the_same_way():
    """The worker and render_results (the render rules the gateway and the
    review thread share) each carry their own _setting and _truncate_comment.
    A fix to one that misses the other makes the two disagree about a key, or
    cap a comment differently."""
    import inspect
    import render_results
    for name in ("_setting", "_truncate_comment"):
        assert inspect.getsource(getattr(worker, name)) == \
            inspect.getsource(getattr(render_results, name)), name
    assert worker._COMMENT_MAX_CHARS == render_results._COMMENT_MAX_CHARS
    assert worker._COMMENT_TRUNCATION_NOTE == render_results._COMMENT_TRUNCATION_NOTE


def test_the_worker_loop_never_renders():
    """Rendering is tubematic-renderer's. A claim here would put a render back
    in front of every publish and approval, which is what the split removed."""
    import inspect
    body = inspect.getsource(worker.main)
    for render_step in ("_claim_next", "_render_claimed", "_reconcile_rendering_videos",
                        "_run_gpu_probe", "_ensure_stills_server"):
        assert render_step not in body
        assert not hasattr(worker, render_step), render_step


@pytest.mark.parametrize("env, expected", [
    ({}, 20),
    ({"WORKER_POLL_INTERVAL_SECS": "7"}, 7),
    # Before the split this loop ran in the renderer under the old name; an
    # install that overrode it keeps its interval.
    ({"RENDER_POLL_INTERVAL_SECS": "45"}, 45),
    ({"WORKER_POLL_INTERVAL_SECS": "7", "RENDER_POLL_INTERVAL_SECS": "45"}, 7),
])
def test_the_poll_interval_honours_the_pre_split_variable(env, expected):
    import subprocess
    import sys
    clean = {k: v for k, v in os.environ.items()
             if k not in ("WORKER_POLL_INTERVAL_SECS", "RENDER_POLL_INTERVAL_SECS")}
    out = subprocess.run(
        [sys.executable, "-c", "import worker; print(worker.POLL_INTERVAL_SECS)"],
        cwd=os.path.dirname(worker.__file__), env={**clean, **env},
        capture_output=True, text=True, check=True)
    assert int(out.stdout.strip().splitlines()[-1]) == expected
