"""A domain's default script profile over HTTP (TMDEV-145).

The default seeds a domain's *curriculum* videos only, like the default visual
style: a curriculum is the one sourcing mode that produces a series, and the
profile is part of the series' identity. A profile that has stopped being
usable (archived, or never READY) seeds nothing, because the approving PATCH
would refuse it and leave the human to work out why.

POST /projects is a full replace, so an unchanged default is re-sent by every
edit to the domain. Refusing a stored default that was archived since would
block every unrelated edit, so only a CHANGE is checked.

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


def _profile(db_path, pid, status="READY", archived=0):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO script_profiles (id, name, status, archived, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (pid, pid.title(), status, archived))
    con.commit()
    con.close()


def _archive(db_path, pid):
    con = sqlite3.connect(db_path)
    con.execute("UPDATE script_profiles SET archived = 1 WHERE id = ?", (pid,))
    con.commit()
    con.close()


def _domain(client, pid="dom", **extra):
    return client.post("/projects", json={"id": pid, "name": "Domain", **extra})


def _video(client, project_id="dom", strategy="curriculum"):
    body = {"topic": "a topic", "strategy": strategy, "producibility_score": 7,
            "project_id": project_id}
    resp = client.post("/videos", json=body)
    assert resp.status_code == 201, resp.data
    return json.loads(resp.data)


# ── POST /projects ───────────────────────────────────────────────────────────

def test_a_project_stores_a_default_profile(client, db_path):
    _profile(db_path, "prof")
    resp = _domain(client, default_script_profile_id="prof")
    assert resp.status_code == 201
    assert json.loads(resp.data)["default_script_profile_id"] == "prof"


def test_a_project_defaults_to_no_profile(client):
    assert json.loads(_domain(client).data)["default_script_profile_id"] == ""


@pytest.mark.parametrize("status,archived", [("PENDING", 0), ("FAILED", 0), ("READY", 1)])
def test_an_unusable_profile_is_refused_as_a_new_default(client, db_path, status, archived):
    _profile(db_path, "prof", status=status, archived=archived)
    resp = _domain(client, default_script_profile_id="prof")
    assert resp.status_code == 400
    assert "not a READY script profile" in json.loads(resp.data)["error"]


def test_an_unknown_profile_is_refused(client):
    assert _domain(client, default_script_profile_id="nope").status_code == 400


@pytest.mark.parametrize("bad", [7, False, 0, [], {}])
def test_a_non_string_default_is_refused_and_changes_nothing(client, db_path, bad):
    """Checked on the raw value: `or ""` first would read a false, 0 or empty
    list as "no default" and silently clear the stored one with a 201."""
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    resp = _domain(client, default_script_profile_id=bad)
    assert resp.status_code == 400
    assert "must be a string" in json.loads(resp.data)["error"]
    stored = json.loads(client.get("/projects").data)[0]["default_script_profile_id"]
    assert stored == "prof"


def test_a_null_default_means_none(client, db_path):
    """null is the same as omitting it, which on this full replace is none."""
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    resp = _domain(client, default_script_profile_id=None)
    assert resp.status_code == 201
    assert json.loads(resp.data)["default_script_profile_id"] == ""


def test_a_stored_default_archived_since_does_not_block_other_edits(client, db_path):
    """The full replace re-sends the stored default with every edit."""
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    _archive(db_path, "prof")
    resp = client.post("/projects", json={"id": "dom", "name": "Renamed",
                                          "default_script_profile_id": "prof"})
    assert resp.status_code == 201
    assert json.loads(resp.data)["name"] == "Renamed"


def test_an_omitted_default_is_cleared_by_the_full_replace(client, db_path):
    """Documented behaviour of POST /projects: every column is overwritten."""
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    resp = _domain(client)
    assert json.loads(resp.data)["default_script_profile_id"] == ""


# ── seeding on POST /videos ─────────────────────────────────────────────────

def test_a_curriculum_video_starts_with_the_domain_profile(client, db_path):
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    assert _video(client)["script_profile_id"] == "prof"


@pytest.mark.parametrize("strategy", ["trending", "mining", "manual"])
def test_other_strategies_do_not_inherit_it(client, db_path, strategy):
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    assert _video(client, strategy=strategy)["script_profile_id"] == ""


def test_a_domain_without_a_default_seeds_no_profile(client):
    _domain(client)
    assert _video(client)["script_profile_id"] == ""


def test_a_default_archived_since_seeds_nothing(client, db_path):
    _profile(db_path, "prof")
    _domain(client, default_script_profile_id="prof")
    _archive(db_path, "prof")
    assert _video(client)["script_profile_id"] == ""


def test_changing_the_default_never_reaches_back(client, db_path):
    _profile(db_path, "one")
    _profile(db_path, "two")
    _domain(client, default_script_profile_id="one")
    vid = _video(client)["id"]
    _domain(client, default_script_profile_id="two")
    assert json.loads(client.get(f"/videos/{vid}").data)["script_profile_id"] == "one"


def test_the_manual_route_is_not_seeded(client, db_path):
    """POST /videos/manual files into the manual domain as strategy manual."""
    _profile(db_path, "prof")
    _domain(client, pid="manual", default_script_profile_id="prof")
    resp = client.post("/videos/manual", json={"title": "A title", "topic": "A topic"})
    assert resp.status_code == 201
    assert json.loads(resp.data)["script_profile_id"] == ""
