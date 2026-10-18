"""A domain's description over HTTP (TMDEV-170).

The description is a multi-line scope statement the agent reads on every
research run, capped at PROJECT_DESCRIPTION_MAX_CHARS. POST /projects is a full
replace the dashboard re-sends on every edit, so the cap is checked only when
the description changes: one stored longer before the cap existed must not
block an unrelated edit. The HTTP mirror of mcp/tests/test_project_description.py.

Run from repo root: pytest renderer/api/tests/
"""
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


def _stored(db_path, pid="db-internals"):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT description FROM projects WHERE id = ?", (pid,)).fetchone()
    con.close()
    return row[0] if row else None


def _post(client, **fields):
    body = {"id": "db-internals", "name": "Database internals", **fields}
    return client.post("/projects", json=body)


def test_a_multi_line_description_is_stored_verbatim(client, db_path):
    text = "Storage engines and query planning.\n\nNot: ORMs or SQL tutorials."
    r = _post(client, description=text)
    assert r.status_code == 201
    assert r.get_json()["description"] == text
    assert _stored(db_path) == text


def test_the_cap_is_inclusive_on_create(client, db_path):
    assert _post(client, description="x" * 2000).status_code == 201
    assert _stored(db_path) == "x" * 2000


def test_one_past_the_cap_is_refused_on_create(client, db_path):
    r = _post(client, description="x" * 2001)
    assert r.status_code == 400
    assert r.get_json()["error"] == "description must be at most 2000 characters, got 2001"
    assert _stored(db_path) is None


def test_the_cap_counts_code_points(client, db_path):
    # An emoji is two UTF-16 units but one character, as the dashboard counts.
    assert _post(client, description="🐘" * 2000).status_code == 201


def test_a_change_to_an_over_cap_description_is_refused(client, db_path):
    assert _post(client, description="short").status_code == 201
    r = _post(client, description="x" * 2001)
    assert r.status_code == 400
    assert _stored(db_path) == "short"


def test_an_unchanged_over_cap_description_still_saves_other_edits(client, db_path):
    """The negative control: the dashboard re-sends the stored description with
    every row edit, so refusing it would block every edit to the domain."""
    assert _post(client, description="short").status_code == 201
    long_text = "y" * 3000
    con = sqlite3.connect(db_path)
    con.execute("UPDATE projects SET description = ? WHERE id = 'db-internals'", (long_text,))
    con.commit()
    con.close()
    r = _post(client, description=long_text, default_visual_style="stick")
    assert r.status_code == 201
    assert r.get_json()["default_visual_style"] == "stick"
    assert _stored(db_path) == long_text


@pytest.mark.parametrize("bad", [["a"], 7, True, {"a": 1}])
def test_a_non_string_description_is_refused(client, db_path, bad):
    r = _post(client, description=bad)
    assert r.status_code == 400
    assert r.get_json()["error"].startswith("description must be a string")
    assert _stored(db_path) is None


def test_null_and_absent_mean_none(client, db_path):
    assert _post(client, description=None).status_code == 201
    assert _stored(db_path) == ""
    assert _post(client).status_code == 201
    assert _stored(db_path) == ""
