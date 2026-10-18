"""A domain's topic cap over HTTP (TMDEV-153).

The HTTP mirror of mcp/tests/test_topic_cap.py. A domain whose count of videos
ever filed — archived and rejected included — has reached its topic_cap is
expired, and is refused on every research write path exactly like a paused
one. Manual submissions are exempt. Expired is derived on read, never stored.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint


@pytest.fixture
def db_path(tmp_path):
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


def _sql(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    rows = con.execute(sql, params).fetchall()
    con.commit()
    con.close()
    return rows


def _project(db_path, pid="db-internals", *, cap=25, status="active", name="Database internals"):
    _sql(db_path, "INSERT INTO projects (id, name, is_curriculum_seed, status, topic_cap, "
                  "created_at) VALUES (?, ?, 1, ?, ?, '2026-01-01T00:00:00Z')",
         (pid, name, status, cap))


def _videos(db_path, pid, n, *, start=0, archived=False):
    con = sqlite3.connect(db_path)
    for i in range(start, start + n):
        con.execute("INSERT INTO videos (id, project_id, topic, status, archived_at, created_at, "
                    "updated_at) VALUES (?, ?, 't', 'TOPIC_REJECTED', ?, '2026-02-01', "
                    "'2026-02-01')", (f"vid_{pid}_{i}", pid, "2026-03-01" if archived else None))
    con.commit()
    con.close()


def _count(db_path, pid="db-internals"):
    return _sql(db_path, "SELECT COUNT(*) FROM videos WHERE project_id = ?", (pid,))[0][0]


def _video(client, strategy, project_id="db-internals"):
    return client.post("/videos", json={
        "project_id": project_id, "topic": "B-trees on disk",
        "strategy": strategy, "producibility_score": 7,
    })


def _domain(client, **fields):
    body = {"id": "db-internals", "name": "Database internals", "is_curriculum_seed": True}
    body.update(fields)
    return client.post("/projects", json=body)


# ── POST /videos refuses an expired domain ──────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining"])
def test_a_domain_at_its_cap_refuses_every_sourced_strategy(client, db_path, strategy):
    _project(db_path, cap=25)
    _videos(db_path, "db-internals", 25, archived=True)
    r = _video(client, strategy)
    assert r.status_code == 409
    assert "expired" in json.loads(r.data)["error"]
    assert _count(db_path) == 25


def test_a_manual_submission_is_accepted_into_an_expired_domain(client, db_path):
    _project(db_path, cap=25)
    _videos(db_path, "db-internals", 25)
    assert _video(client, "manual").status_code == 201


def test_the_dashboard_new_video_page_files_past_the_manual_domains_cap(client, db_path):
    """POST /videos/manual always files into the fixed manual domain, so the
    cap must never stop it."""
    _project(db_path, pipeline.MANUAL_PROJECT_ID, cap=25, name="Manual Videos")
    _videos(db_path, pipeline.MANUAL_PROJECT_ID, 25)
    r = client.post("/videos/manual", json={"title": "A title", "topic": "A topic"})
    assert r.status_code == 201
    assert _count(db_path, pipeline.MANUAL_PROJECT_ID) == 26


def test_a_topic_landing_between_the_check_and_the_insert_still_refuses(client, db_path,
                                                                        monkeypatch):
    _project(db_path, cap=25)
    _videos(db_path, "db-internals", 24)
    real_pick = pipeline._pick_agent_id

    def _fill_then_pick(con, *a, **kw):
        _videos(db_path, "db-internals", 1, start=24)
        return real_pick(con, *a, **kw)

    monkeypatch.setattr(pipeline, "_pick_agent_id", _fill_then_pick)
    r = _video(client, "trending")
    assert r.status_code == 409
    assert "expired" in json.loads(r.data)["error"]
    assert _count(db_path) == 25


# ── POST /projects and GET /projects ────────────────────────────────────────

def test_a_new_domain_gets_the_default_cap(client):
    data = json.loads(_domain(client).data)
    assert data["topic_cap"] == pipeline.TOPIC_CAP_DEFAULT == 100
    assert (data["topic_count"], data["expired"]) == (0, False)


def test_the_cap_is_stored(client):
    assert json.loads(_domain(client, topic_cap=300).data)["topic_cap"] == 300


def test_an_omitted_cap_is_the_default_on_this_full_replace(client):
    """Like every other field of this route: a caller changing one field must
    send the others back. The dashboard's saveDomain does."""
    _domain(client, topic_cap=300)
    assert json.loads(_domain(client).data)["topic_cap"] == 100


@pytest.mark.parametrize("cap", [25, 750])
def test_the_bounds_themselves_are_accepted(client, cap):
    assert _domain(client, topic_cap=cap).status_code == 201


@pytest.mark.parametrize("cap", [24, 751, 0, True, "100", 100.5])
def test_a_cap_outside_the_bounds_or_not_a_whole_number_is_refused(client, cap):
    _domain(client, topic_cap=300)
    r = _domain(client, topic_cap=cap)
    assert r.status_code == 400
    assert "topic_cap" in json.loads(r.data)["error"]
    assert json.loads(client.get("/projects").data)[0]["topic_cap"] == 300


def test_a_cap_below_the_count_expires_the_domain_at_once(client, db_path):
    _domain(client)
    _videos(db_path, "db-internals", 30)
    data = json.loads(_domain(client, topic_cap=25).data)
    assert (data["topic_count"], data["expired"]) == (30, True)
    assert _video(client, "curriculum").status_code == 409


def test_get_projects_carries_the_count_and_expiry(client, db_path):
    _project(db_path, "a", cap=25)
    _project(db_path, "b", cap=100)
    _videos(db_path, "a", 25, archived=True)
    _videos(db_path, "b", 3)
    by_id = {p["id"]: p for p in json.loads(client.get("/projects").data)}
    assert (by_id["a"]["topic_count"], by_id["a"]["expired"]) == (25, True)
    assert (by_id["b"]["topic_count"], by_id["b"]["expired"]) == (3, False)


def test_set_status_returns_the_same_shape(client, db_path):
    _project(db_path, cap=25)
    data = json.loads(client.post("/projects/db-internals/status",
                                  json={"status": "paused"}).data)
    assert (data["topic_count"], data["expired"]) == (0, False)
