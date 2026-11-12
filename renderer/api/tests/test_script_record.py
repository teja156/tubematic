"""A script's record over HTTP (TMDEV-211): the formula, the drafted openings
and the stored warnings, as the dashboard reads them.

The record is written by the MCP server's update_video. This process only
reads it, with two exceptions the tests pin: it decodes the two JSON columns
for every video route, and a script written through PATCH clears the record,
since PATCH stores a flat script that nothing checked and no formula produced.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline  # noqa: E402
from pipeline import create_pipeline_blueprint  # noqa: E402
from tubematic_core import formulas as tformulas  # noqa: E402

NOW = "2026-11-11T00:00:00Z"
HOOKS = [{"type": "problem", "text": "You renamed a file.", "kept": True, "note": ""},
         {"type": "question", "text": "Why does the log stop?", "kept": False, "note": ""},
         {"type": "myth", "text": "A rename is recorded.", "kept": False, "note": "overclaims"}]
WARNINGS = [{"id": "closing_ask", "message": "The last sentence asks the viewer to follow."}]
PUBLISH = {"publish_title": "A title", "publish_description": "A description."}


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


def _video(db_path, vid="vid_1", recorded=True):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, status, script, formula_id, hook_type, "
        "hook_alternatives, script_warnings, created_at, updated_at) "
        "VALUES (?, 't', 'SCRIPT_READY', 'Old words.', ?, ?, ?, ?, ?, ?)",
        (vid, *(("broken-expectation", "problem", json.dumps(HOOKS), json.dumps(WARNINGS))
                if recorded else ("", "", "", "")), NOW, NOW))
    con.commit()
    con.close()
    return vid


def _record(db_path, vid="vid_1"):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT formula_id, hook_type, hook_alternatives, script_warnings "
                      "FROM videos WHERE id = ?", (vid,)).fetchone()
    con.close()
    return row


def test_a_video_carries_its_record_decoded(client, db_path):
    vid = _video(db_path)
    got = client.get(f"/videos/{vid}").get_json()
    assert (got["formula_id"], got["hook_type"]) == ("broken-expectation", "problem")
    assert got["hook_alternatives"] == HOOKS
    assert got["script_warnings"] == WARNINGS


def test_a_video_with_no_record_carries_empty_lists(client, db_path):
    vid = _video(db_path, recorded=False)
    got = client.get(f"/videos/{vid}").get_json()
    assert (got["formula_id"], got["hook_type"]) == ("", "")
    assert got["hook_alternatives"] == [] and got["script_warnings"] == []


def test_the_list_routes_decode_the_record_too(client, db_path):
    _video(db_path)
    for route in ("/videos", "/videos/actionable"):
        row = next(v for v in client.get(route).get_json() if v["id"] == "vid_1")
        assert row["hook_alternatives"] == HOOKS and row["script_warnings"] == WARNINGS


def test_a_script_written_over_http_clears_the_record(client, db_path):
    vid = _video(db_path)
    r = client.patch(f"/videos/{vid}", json={"script": "New words.", **PUBLISH})
    assert r.status_code == 200
    assert tuple(_record(db_path)) == ("", "", "", "")
    assert r.get_json()["hook_alternatives"] == []


def test_a_patch_that_leaves_the_script_alone_keeps_the_record(client, db_path):
    vid = _video(db_path)
    r = client.patch(f"/videos/{vid}", json={"publish_title": "Another title"})
    assert r.status_code == 200
    assert _record(db_path)[0] == "broken-expectation"
    assert json.loads(_record(db_path)[3]) == WARNINGS


def test_the_formula_list_names_every_formula_and_hook_type(client):
    got = client.get("/script-formulas").get_json()
    assert [f["id"] for f in got["formulas"]] == list(tformulas.FORMULAS)
    assert {"id": "scene-story", "label": "Scene Story"}.items() <= next(
        f for f in got["formulas"] if f["id"] == "scene-story").items()
    assert {h["id"]: h["label"] for h in got["hook_types"]} == tformulas.HOOK_TYPES
