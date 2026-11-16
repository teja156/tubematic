"""DELETE /projects/<id>: removing a paused curriculum seed and what is under it.

A domain delete is the only hard row delete in the API and is human-only (no MCP
tool), so these tests pin both what it refuses and what it takes with it. The
cost ledger staying put is the quiet one: the Costs page buckets spend by the
usage_event_videos links, so dropping them would move money between buckets.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import DELETABLE_STATUSES, VALID_VIDEO_STATUSES, create_pipeline_blueprint


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    out, jobs = tmp_path / "out", tmp_path / "jobs"
    out.mkdir()
    jobs.mkdir()
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)
    monkeypatch.setattr(pipeline, "JOBS_DIR", jobs)
    return out, jobs


@pytest.fixture
def db_path(tmp_path, dirs):
    p = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = p
    pipeline._init_db(p)
    return p


@pytest.fixture
def client(db_path):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sql(db_path, query, args=()):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        out = con.execute(query, args).fetchall()
        con.commit()
        return out
    finally:
        con.close()


def _project(db_path, pid, *, seed=True, status="paused"):
    _sql(db_path,
         "INSERT INTO projects (id, name, is_curriculum_seed, status, created_at) "
         "VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z')", (pid, pid, int(seed), status))


def _video(db_path, vid, pid, status="VIDEO_READY"):
    _sql(db_path,
         "INSERT INTO videos (id, project_id, topic, status, created_at, updated_at) "
         "VALUES (?, ?, 'a topic', ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
         (vid, pid, status))


def _count(db_path, table, where="1=1", args=()):
    return _sql(db_path, f"SELECT COUNT(*) FROM {table} WHERE {where}", args)[0][0]


def _auto_pilot(db_path, projects):
    _sql(db_path, "INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_pilot_config', ?)",
         (json.dumps({"projects": projects, "account_limits": {}}),))


# ── refusals ────────────────────────────────────────────────────────────────

def test_unknown_domain_is_404(client):
    assert client.delete("/projects/nope").status_code == 404


def test_an_active_seed_is_refused(client, db_path):
    _project(db_path, "dom", status="active")
    r = client.delete("/projects/dom")
    assert r.status_code == 409 and "Pause" in r.get_json()["error"]
    assert _count(db_path, "projects", "id = 'dom'") == 1


def test_a_non_seed_is_refused(client, db_path):
    _project(db_path, "trend", seed=False, status="active")
    r = client.delete("/projects/trend")
    assert r.status_code == 409 and "seed" in r.get_json()["error"]
    assert _count(db_path, "projects", "id = 'trend'") == 1


def test_the_manual_domain_is_refused(client, db_path):
    _project(db_path, "manual", seed=True, status="paused")
    assert client.delete("/projects/manual").status_code == 409
    assert _count(db_path, "projects", "id = 'manual'") == 1


@pytest.mark.parametrize("status", sorted(VALID_VIDEO_STATUSES - DELETABLE_STATUSES))
def test_a_video_in_progress_blocks_the_delete(client, db_path, status):
    _project(db_path, "dom")
    _video(db_path, "v1", "dom", "VIDEO_READY")
    _video(db_path, "v2", "dom", status)
    r = client.delete("/projects/dom")
    assert r.status_code == 409
    assert status in r.get_json()["error"]
    assert _count(db_path, "projects", "id = 'dom'") == 1
    assert _count(db_path, "videos", "project_id = 'dom'") == 2


# ── the cascade ─────────────────────────────────────────────────────────────

def test_delete_removes_everything_under_the_domain_and_nothing_else(client, db_path, dirs):
    out, jobs = dirs
    _project(db_path, "dom")
    _project(db_path, "other")
    _video(db_path, "v1", "dom", "PUBLISHED")
    _video(db_path, "v2", "dom", "TOPIC_PROPOSED")
    _video(db_path, "keep", "other")
    _sql(db_path, "INSERT INTO comments (video_id, author, content, created_at) "
                  "VALUES ('v1', 'human', 'hi', '2026-01-01T00:00:00Z')")
    _sql(db_path, "INSERT INTO video_publications (id, video_id, platform, social_account_id, created_at, updated_at) "
                  "VALUES ('p1', 'v1', 'youtube', 'acc', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    _sql(db_path, "INSERT INTO video_metrics (publication_id, fetched_at, views) "
                  "VALUES ('p1', '2026-01-02T00:00:00Z', 10)")
    _sql(db_path, "INSERT INTO usage_events (created_at, service, operation, cost_usd, cost_basis) "
                  "VALUES ('2026-01-01T00:00:00Z', 'elevenlabs', 'voice', 0.5, 'measured')")
    _sql(db_path, "INSERT INTO usage_event_videos (event_id, video_id, stage) "
                  "SELECT id, 'v1', 'voice' FROM usage_events")
    _auto_pilot(db_path, {"dom": ["acc"], "other": ["acc"]})
    (out / "dom").mkdir()
    (out / "dom" / "v1.mp4").write_bytes(b"x")
    (out / "other").mkdir()
    (out / "other" / "keep.mp4").write_bytes(b"x")
    for vid in ("v1", "v2", "keep"):
        (jobs / vid).mkdir()
        (jobs / vid / "timeline.json").write_text("{}")

    r = client.delete("/projects/dom")

    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "deleted_videos": 2, "file_errors": []}
    assert _count(db_path, "projects", "id = 'dom'") == 0
    assert _count(db_path, "videos", "project_id = 'dom'") == 0
    assert _count(db_path, "comments") == 0
    assert _count(db_path, "video_publications") == 0
    assert _count(db_path, "video_metrics") == 0
    config = json.loads(_sql(db_path, "SELECT value FROM settings WHERE key = 'auto_pilot_config'")[0][0])
    assert list(config["projects"]) == ["other"]
    # The cost ledger and its video links stay: Costs buckets spend by them.
    assert _count(db_path, "usage_events") == 1
    assert _count(db_path, "usage_event_videos", "video_id = 'v1'") == 1
    # Files: this domain's go, the other domain's stay.
    assert not (out / "dom").exists()
    assert not (jobs / "v1").exists() and not (jobs / "v2").exists()
    assert (out / "other" / "keep.mp4").exists()
    assert (jobs / "keep" / "timeline.json").exists()
    assert _count(db_path, "projects", "id = 'other'") == 1
    assert _count(db_path, "videos", "id = 'keep'") == 1


def test_a_domain_with_no_videos_deletes(client, db_path):
    _project(db_path, "dom")
    r = client.delete("/projects/dom")
    assert r.status_code == 200 and r.get_json()["deleted_videos"] == 0
    assert _count(db_path, "projects") == 0


def test_rejected_and_archived_videos_do_not_block(client, db_path):
    _project(db_path, "dom")
    _video(db_path, "v1", "dom", "TOPIC_REJECTED")
    _sql(db_path, "UPDATE videos SET archived_at = '2026-01-02T00:00:00Z' WHERE id = 'v1'")
    assert client.delete("/projects/dom").status_code == 200
    assert _count(db_path, "videos") == 0


def test_a_project_id_that_escapes_the_output_dir_is_reported_not_followed(client, db_path, dirs, tmp_path):
    out, _ = dirs
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "f").write_text("x")
    bad = "../victim"
    _project(db_path, bad)
    r = client.delete("/projects/" + bad.replace("/", "%2F"))
    # Flask may not route an encoded slash; either way the sibling folder survives.
    assert (victim / "f").exists()
    if r.status_code == 200:
        assert r.get_json()["file_errors"]
