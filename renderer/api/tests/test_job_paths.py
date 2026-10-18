"""Ids that become paths, and the job-path columns nobody may write (TMDEV-158/159/162).

Three boundaries, each pinned in both directions:

- A NEW video or project id must be a plain path segment. An existing domain
  with an odd id (agents chose them) must stay editable through the upsert.
- PATCH /videos/<id> refuses the four job-path columns outright, with nothing
  applied, even when they ride along with a status change.
- Every reader derives the file from the ids. A row tampered with before the
  fix (video A's video_path naming video B's render) must not make archive
  delete B's file, nor publish upload it.

Run from renderer/api/: pytest tests/test_job_paths.py
"""
import json
import os
import sqlite3
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline

PATH_FIELDS = ["voice_file_path", "timeline_path", "scene_config_path", "video_path"]
BAD_IDS = ["../x", "/tmp/x", "a/b", "..", "x" * 129, 7, ["a"], "a.b", "-x"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    out, jobs = tmp_path / "output_videos", tmp_path / "jobs"
    out.mkdir()
    jobs.mkdir()
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)
    monkeypatch.setattr(pipeline, "JOBS_DIR", jobs)
    pipeline._init_db(db)
    return SimpleNamespace(db=db, out=out, jobs=jobs, tmp=tmp_path)


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


def _row(env, query, params=()):
    con = sqlite3.connect(env.db)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(query, params).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _project(env, pid="proj-1"):
    _sql(env, "INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?, ?, 'n')",
         (pid, pid))


def _video(env, vid, status="PUBLISHED", project="proj-1", **cols):
    _project(env, project)
    columns = {"id": vid, "project_id": project, "topic": "T", "strategy": "curriculum",
               "producibility_score": 8, "status": status,
               "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
               **cols}
    _sql(env, f"INSERT INTO videos ({', '.join(columns)}) VALUES "
              f"({', '.join('?' * len(columns))})", tuple(columns.values()))


def _mp4(env, vid, project="proj-1"):
    path = env.out / project / f"{vid}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00mp4")
    return path


# ── POST /videos: the id is a path segment ──────────────────────────────────

def _create(client, **body):
    return client.post("/videos", json={"topic": "T", "strategy": "manual",
                                         "producibility_score": 8, **body})


@pytest.mark.parametrize("bad", BAD_IDS)
def test_post_videos_refuses_an_id_that_is_not_a_segment(client, env, bad):
    r = _create(client, id=bad)
    assert r.status_code == 400
    assert "not a valid id" in json.loads(r.data)["error"]
    assert _row(env, "SELECT COUNT(*) AS n FROM videos")["n"] == 0


@pytest.mark.parametrize("good", ["vid_0123456789ab", str(uuid.uuid4())])
def test_post_videos_accepts_the_real_id_shapes(client, good):
    assert _create(client, id=good).status_code == 201


def test_post_videos_without_an_id_still_gets_one(client):
    r = _create(client)
    assert r.status_code == 201
    assert json.loads(r.data)["id"]


def test_an_unknown_project_is_a_400_not_a_500(client, env):
    r = _create(client, project_id="no-such-domain")
    assert r.status_code == 400
    assert "does not exist" in json.loads(r.data)["error"]


def test_a_known_project_still_files(client, env):
    _project(env, "proj_0123abcd")
    assert _create(client, project_id="proj_0123abcd").status_code == 201


# ── POST /projects: checked only when the row is new ────────────────────────

@pytest.mark.parametrize("bad", ["../x", "/tmp/x", "a/b", "..", "x" * 129, "node.js"])
def test_post_projects_refuses_a_new_id_that_is_not_a_segment(client, env, bad):
    r = client.post("/projects", json={"id": bad, "name": "N"})
    assert r.status_code == 400
    assert _row(env, "SELECT COUNT(*) AS n FROM projects")["n"] == 0


@pytest.mark.parametrize("bad", [7, ["a"], {"a": 1}])
def test_post_projects_refuses_a_non_string_id(client, bad):
    assert client.post("/projects", json={"id": bad, "name": "N"}).status_code == 400


@pytest.mark.parametrize("good", ["proj_0123abcd", "manual", "rust-internals"])
def test_post_projects_accepts_the_real_id_shapes(client, good):
    assert client.post("/projects", json={"id": good, "name": "N"}).status_code == 201


def test_a_legacy_domain_with_an_odd_id_stays_editable(client, env):
    """The dashboard re-sends the id on every edit. Refusing an existing row
    would lock a domain an agent once filed under `node.js` out of every edit."""
    _project(env, "node.js")
    r = client.post("/projects", json={"id": "node.js", "name": "Renamed"})
    assert r.status_code == 201
    assert _row(env, "SELECT name FROM projects WHERE id = 'node.js'")["name"] == "Renamed"


# ── PATCH refuses the server-owned path columns ─────────────────────────────

@pytest.mark.parametrize("field", PATH_FIELDS)
def test_patch_refuses_each_path_field_and_applies_nothing(client, env, field):
    _video(env, "vid_a", status="VIDEO_READY")
    r = client.patch("/videos/vid_a", json={field: "/jobs/vid_b/x", "status": "VIDEO_APPROVED"})
    assert r.status_code == 400
    assert field in json.loads(r.data)["error"]
    row = _row(env, "SELECT * FROM videos WHERE id = 'vid_a'")
    assert row["status"] == "VIDEO_READY"
    assert row[field] == ""


def test_patch_without_a_path_field_still_works(client, env):
    _video(env, "vid_a", status="VIDEO_READY")
    r = client.patch("/videos/vid_a", json={"status": "VIDEO_APPROVED"})
    assert r.status_code == 200


# ── Readers derive, so a tampered row cannot reach another video's file ─────

def test_archive_ignores_a_video_path_naming_another_videos_render(client, env):
    own = _mp4(env, "vid_a")
    theirs = _mp4(env, "vid_b")
    _video(env, "vid_a", video_path=str(env.out / "proj-1" / "vid_b.mp4"))
    _video(env, "vid_b")
    r = client.delete("/videos/vid_a")
    assert r.status_code == 200
    assert theirs.exists()
    assert not own.exists()


def test_archive_with_an_escaping_project_id_touches_nothing_outside(env):
    """A project id that would leave OUTPUT_DIR names no file at all."""
    outside = env.tmp / "vid_a.mp4"
    outside.write_bytes(b"keep")
    con = sqlite3.connect(env.db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('..', 'x', 'n')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, created_at,"
                " updated_at) VALUES ('vid_a', '..', 'T', 'manual', 'PUBLISHED', 'n', 'n')")
    con.commit()
    con.close()
    result = pipeline.archive_video(env.db, "vid_a", {"PUBLISHED"}, "human", "gone")
    assert result["result"] == "archived"
    assert outside.read_bytes() == b"keep"


def test_publish_never_uploads_a_render_the_row_merely_names(client, env):
    _mp4(env, "vid_b")
    _video(env, "vid_a", status="VIDEO_APPROVED",
           video_path=str(env.out / "proj-1" / "vid_b.mp4"))
    _sql(env, "INSERT OR REPLACE INTO settings (key, value) VALUES ('publishing_enabled', 'true')")
    _sql(env, "INSERT OR REPLACE INTO settings (key, value) VALUES ('postforme_api_key', 'k')")
    _sql(env, "INSERT OR REPLACE INTO settings (key, value) "
              "VALUES ('publishing_accounts', '[\"spc_yt\"]')")
    with mock.patch("postforme.create_upload_url") as upload:
        r = client.post("/videos/vid_a/publish", json={"account_ids": ["spc_yt"], "title": "T"})
    assert r.status_code == 400
    assert "No rendered video file" in json.loads(r.data)["error"]
    upload.assert_not_called()


def test_the_retention_backlog_sizes_the_derived_file(client, env):
    _mp4(env, "vid_a")
    _video(env, "vid_a", status="FAILED", video_path="/somewhere/else/vid_b.mp4")
    body = json.loads(client.get("/retention/backlog").data)
    assert body["failed"]["bytes"] == len(b"\x00mp4")


def test_the_prefill_duration_ignores_a_planted_timeline_path(client, env):
    planted = env.tmp / "planted.json"
    planted.write_text(json.dumps({"audioDurationSeconds": 999}))
    (env.jobs / "vid_a").mkdir()
    (env.jobs / "vid_a" / "timeline.json").write_text(json.dumps({"audioDurationSeconds": 42}))
    _video(env, "vid_a", status="VIDEO_APPROVED", timeline_path=str(planted))
    body = json.loads(client.post("/videos/vid_a/publish-prefill").data)
    assert body["duration_secs"] == 42


def test_a_symlinked_timeline_is_not_read(client, env):
    secret = env.tmp / "secret.json"
    secret.write_text(json.dumps({"audioDurationSeconds": 77}))
    (env.jobs / "vid_a").mkdir()
    (env.jobs / "vid_a" / "timeline.json").symlink_to(secret)
    _video(env, "vid_a", status="VIDEO_APPROVED")
    body = json.loads(client.post("/videos/vid_a/publish-prefill").data)
    assert body["duration_secs"] is None
