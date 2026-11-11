"""The script formula over HTTP (TMDEV-213): a person's choice at the topic,
the switch to the runner-up and to another drafted opening at SCRIPT_READY,
what gives a pick back, the domain's default formula, and the setting that
lets Auto pick an experimental formula.

The two switches are the only HTTP writes of the formula decision after the
topic checkpoint, so every condition they check is repeated in their UPDATE.
Both send the video back to TOPIC_APPROVED to be rewritten and never edit the
stored script: a new formula or a new first sentence over the old body would
be a script nobody wrote. The reset is the same SQL fragment the MCP server
uses (tubematic_core.formulas.PICK_RESET_SET).

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline  # noqa: E402
from pipeline import create_pipeline_blueprint  # noqa: E402
from tubematic_core import formulas as tf  # noqa: E402

NOW = "2026-11-11T00:00:00Z"
HOOKS = [{"type": "problem", "text": "You renamed one file.", "kept": True, "note": ""},
         {"type": "question", "text": "Why does the log stop at today?", "kept": False, "note": ""},
         {"type": "myth", "text": "A rename is recorded, obviously.", "kept": False,
          "note": "claims a test the script never runs"}]


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = p
    pipeline._init_db(p)
    con = sqlite3.connect(p)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('dom', 'A domain', ?)", (NOW,))
    con.commit()
    con.close()
    return p


@pytest.fixture
def client(db_path):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _video(db_path, vid="vid_1", status="SCRIPT_READY", pick="follow-the-flow",
           runner_up="scene-story", choice="", hooks=HOOKS, style="system_flow"):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, project_id, topic, status, visual_style, formula_choice, "
        "formula_pick, formula_runner_up, formula_reason, formula_id, hook_type, "
        "hook_alternatives, script, created_at, updated_at) "
        "VALUES (?, 'dom', 't', ?, ?, ?, ?, ?, 'why', ?, 'problem', ?, 'old script', ?, ?)",
        (vid, status, style, choice, pick, runner_up, pick,
         json.dumps(hooks) if hooks else "", NOW, NOW))
    con.commit()
    con.close()
    return vid


def _row(db_path, vid="vid_1", cols=("status", "formula_choice", "formula_pick",
                                     "formula_runner_up", "formula_reason")):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = dict(con.execute(f"SELECT {', '.join(cols)} FROM videos WHERE id = ?", (vid,)).fetchone())
    con.close()
    return row


def _comments(db_path, vid="vid_1"):
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT author, content FROM comments WHERE video_id = ?", (vid,)).fetchall()
    con.close()
    return rows


# ── switch to the runner-up ──────────────────────────────────────────────────

def test_the_switch_sends_the_video_back_to_scripting_in_the_runner_up(client, db_path):
    _video(db_path)
    resp = client.post("/videos/vid_1/switch-formula", json={})
    assert resp.status_code == 200
    assert resp.get_json()["formula_pick"] == "scene-story"
    assert _row(db_path) == {
        "status": "TOPIC_APPROVED", "formula_choice": "scene-story", "formula_pick": "scene-story",
        "formula_runner_up": "follow-the-flow",
        "formula_reason": "Switched by a person from Follow the Flow to Scene Story."}
    assert _comments(db_path) == [("human", "Formula switched from Follow the Flow to Scene "
                                            "Story. Rewrite the script in Scene Story; the old "
                                            "script is discarded.")]


def test_the_switch_never_edits_the_stored_script(client, db_path):
    _video(db_path)
    client.post("/videos/vid_1/switch-formula", json={})
    assert _row(db_path, cols=("script", "formula_id")) == {"script": "old script",
                                                           "formula_id": "follow-the-flow"}


def test_a_second_switch_goes_back(client, db_path):
    _video(db_path)
    client.post("/videos/vid_1/switch-formula", json={})
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'SCRIPT_READY' WHERE id = 'vid_1'")
    con.commit()
    con.close()
    assert client.post("/videos/vid_1/switch-formula", json={}).status_code == 200
    row = _row(db_path)
    assert (row["formula_pick"], row["formula_runner_up"]) == ("follow-the-flow", "scene-story")


def test_a_switch_to_an_experimental_runner_up_needs_no_setting(client, db_path):
    # The runner-up of a domain default is what Auto would have picked, and a
    # person switching to a formula is that person's choice.
    _video(db_path, runner_up="stake-first-list")
    assert client.post("/videos/vid_1/switch-formula", json={}).status_code == 200
    assert _row(db_path)["formula_pick"] == "stake-first-list"


@pytest.mark.parametrize("kw, message", [
    ({"pick": ""}, "runner-up"),
    ({"runner_up": ""}, "runner-up"),
    ({"status": "TOPIC_APPROVED"}, "Script Ready"),
    ({"status": "VOICE_READY"}, "Script Ready"),
    ({"runner_up": "retired-formula"}, "no longer a formula"),
])
def test_a_switch_that_cannot_happen_is_refused_and_nothing_changes(client, db_path, kw, message):
    _video(db_path, **kw)
    before = _row(db_path)
    resp = client.post("/videos/vid_1/switch-formula", json={})
    assert resp.status_code == 409 and message in resp.get_json()["error"]
    assert _row(db_path) == before and _comments(db_path) == []


def test_a_switch_on_an_unknown_or_archived_video_is_refused(client, db_path):
    assert client.post("/videos/nope/switch-formula", json={}).status_code == 404
    _video(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET archived_at = ? WHERE id = 'vid_1'", (NOW,))
    con.commit()
    con.close()
    assert client.post("/videos/vid_1/switch-formula", json={}).status_code == 409
    assert _row(db_path)["formula_pick"] == "follow-the-flow"


# ── switch to another drafted opening ────────────────────────────────────────

def test_another_opening_is_marked_in_use_and_the_video_goes_back_to_scripting(client, db_path):
    _video(db_path)
    resp = client.post("/videos/vid_1/switch-opening", json={"index": 1})
    assert resp.status_code == 200
    row = _row(db_path, cols=("status", "hook_type", "hook_alternatives", "formula_pick", "script"))
    assert (row["status"], row["hook_type"]) == ("TOPIC_APPROVED", "question")
    assert [h["kept"] for h in json.loads(row["hook_alternatives"])] == [False, True, False]
    # The formula stays and the stored script is not touched.
    assert (row["formula_pick"], row["script"]) == ("follow-the-flow", "old script")
    author, text = _comments(db_path)[0]
    assert author == "human" and 'the Question one: "Why does the log stop at today?"' in text
    assert "word for word, in the same formula" in text


def test_choosing_an_opening_the_writer_ruled_out_clears_its_note(client, db_path):
    _video(db_path)
    client.post("/videos/vid_1/switch-opening", json={"index": 2})
    hooks = json.loads(_row(db_path, cols=("hook_alternatives",))["hook_alternatives"])
    assert hooks[2] == {"type": "myth", "text": "A rename is recorded, obviously.",
                        "kept": True, "note": ""}


def test_a_video_scripted_before_formula_picks_can_switch_its_opening(client, db_path):
    _video(db_path, pick="", runner_up="")
    assert client.post("/videos/vid_1/switch-opening", json={"index": 1}).status_code == 200


@pytest.mark.parametrize("body, status, message", [
    ({"index": 0}, 409, "already uses"),
    ({"index": 3}, 400, "from 0 to 2"),
    ({"index": -1}, 400, "from 0 to 2"),
    ({"index": "1"}, 400, "whole number"),
    ({"index": True}, 400, "whole number"),
    ({}, 400, "whole number"),
])
def test_a_bad_opening_choice_is_refused_and_nothing_changes(client, db_path, body, status, message):
    _video(db_path)
    resp = client.post("/videos/vid_1/switch-opening", json=body)
    assert resp.status_code == status and message in resp.get_json()["error"]
    assert _row(db_path)["status"] == "SCRIPT_READY" and _comments(db_path) == []


def test_an_opening_switch_needs_script_ready_and_drafted_openings(client, db_path):
    _video(db_path, status="VOICE_READY")
    assert client.post("/videos/vid_1/switch-opening", json={"index": 1}).status_code == 409
    _video(db_path, vid="vid_2", hooks=None)
    resp = client.post("/videos/vid_2/switch-opening", json={"index": 1})
    assert resp.status_code == 409 and "no drafted openings" in resp.get_json()["error"]
    assert client.post("/videos/nope/switch-opening", json={"index": 1}).status_code == 404


# ── what gives a pick back ───────────────────────────────────────────────────

def test_a_return_to_the_topic_drops_the_pick_and_keeps_the_persons_choice(client, db_path):
    _video(db_path, status="REVISION_REQUESTED", choice="follow-the-flow")
    assert client.patch("/videos/vid_1", json={"status": "TOPIC_PROPOSED"}).status_code == 200
    assert _row(db_path) == {"status": "TOPIC_PROPOSED", "formula_choice": "follow-the-flow",
                             "formula_pick": "", "formula_runner_up": "", "formula_reason": ""}


def test_a_script_revision_keeps_the_pick(client, db_path):
    _video(db_path)
    assert client.patch("/videos/vid_1", json={"status": "REVISION_REQUESTED"}).status_code == 200
    assert _row(db_path)["formula_pick"] == "follow-the-flow"


def test_a_style_switch_drops_the_formula_pick_so_it_is_made_for_the_new_style(client, db_path):
    _video(db_path, choice="")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET style_pick = 'system_flow', style_runner_up = 'stick' "
                "WHERE id = 'vid_1'")
    con.commit()
    con.close()
    assert client.post("/videos/vid_1/switch-style", json={}).status_code == 200
    row = _row(db_path)
    assert (row["status"], row["formula_pick"], row["formula_runner_up"]) == \
        ("TOPIC_APPROVED", "", "")


# ── a person's choice at the topic ───────────────────────────────────────────

def test_a_formula_can_be_chosen_at_the_topic(client, db_path):
    _video(db_path, status="TOPIC_PROPOSED", pick="", runner_up="", hooks=None)
    resp = client.patch("/videos/vid_1", json={"formula_choice": "scene-story",
                                               "status": "TOPIC_APPROVED"})
    assert resp.status_code == 200
    assert _row(db_path)["formula_choice"] == "scene-story"
    # An experimental formula is a person's choice and needs no setting.
    _video(db_path, vid="vid_2", status="TOPIC_PROPOSED", pick="", runner_up="", hooks=None)
    assert client.patch("/videos/vid_2", json={"formula_choice": "news-take"}).status_code == 200


def test_auto_is_chosen_with_a_blank(client, db_path):
    _video(db_path, status="TOPIC_PROPOSED", pick="", runner_up="", choice="scene-story", hooks=None)
    assert client.patch("/videos/vid_1", json={"formula_choice": ""}).status_code == 200
    assert _row(db_path)["formula_choice"] == ""


@pytest.mark.parametrize("value", ["no-such-formula", 7, None, ["scene-story"]])
def test_a_formula_choice_that_is_not_a_formula_is_refused(client, db_path, value):
    _video(db_path, status="TOPIC_PROPOSED", pick="", runner_up="", hooks=None)
    resp = client.patch("/videos/vid_1", json={"formula_choice": value})
    assert resp.status_code == 400 and "formula_choice" in resp.get_json()["error"]


@pytest.mark.parametrize("status", ["TOPIC_APPROVED", "SCRIPT_READY", "VOICE_READY", "VIDEO_READY"])
def test_the_choice_is_frozen_after_the_topic(client, db_path, status):
    _video(db_path, status=status)
    resp = client.patch("/videos/vid_1", json={"formula_choice": "scene-story"})
    assert resp.status_code == 409 and "TOPIC_PROPOSED" in resp.get_json()["error"]
    assert _row(db_path)["formula_choice"] == ""


# ── the domain's default and seeding ─────────────────────────────────────────

def _project(client, **kw):
    return client.post("/projects", json={"id": "dom", "name": "A domain", **kw})


def test_a_domain_default_formula_is_stored_and_cleared_by_omission(client, db_path):
    assert _project(client, default_formula_id="scene-story").get_json()["default_formula_id"] == \
        "scene-story"
    # A full replace: an edit that leaves it out puts the domain back on Auto.
    assert _project(client).get_json()["default_formula_id"] == ""


def test_a_default_formula_must_be_a_formula_and_may_be_experimental(client, db_path):
    resp = _project(client, default_formula_id="no-such-formula")
    assert resp.status_code == 400 and "is not a formula" in resp.get_json()["error"]
    assert _project(client, default_formula_id=7).status_code == 400
    assert _project(client, default_formula_id="news-take").status_code == 201


def test_a_stored_default_that_was_dropped_does_not_block_another_edit(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute("UPDATE projects SET default_formula_id = 'retired-formula' WHERE id = 'dom'")
    con.commit()
    con.close()
    resp = client.post("/projects", json={"id": "dom", "name": "Renamed",
                                          "default_formula_id": "retired-formula"})
    assert resp.status_code == 201 and resp.get_json()["name"] == "Renamed"


@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining", "manual"])
def test_the_domains_default_seeds_every_new_video(client, db_path, strategy):
    _project(client, default_formula_id="scene-story")
    resp = client.post("/videos", json={"project_id": "dom", "topic": "t", "strategy": strategy,
                                        "producibility_score": 7})
    assert resp.status_code == 201 and resp.get_json()["formula_choice"] == "scene-story"


def test_a_default_that_is_no_formula_any_more_seeds_nothing(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute("UPDATE projects SET default_formula_id = 'retired-formula' WHERE id = 'dom'")
    con.commit()
    con.close()
    resp = client.post("/videos", json={"project_id": "dom", "topic": "t", "strategy": "trending",
                                        "producibility_score": 7})
    assert resp.status_code == 201 and resp.get_json()["formula_choice"] == ""


def test_a_formula_sent_with_the_video_wins_over_the_domains_default(client, db_path):
    _project(client, default_formula_id="scene-story")
    resp = client.post("/videos", json={"project_id": "dom", "topic": "t", "strategy": "manual",
                                        "producibility_score": 7,
                                        "formula_choice": "incident-file"})
    assert resp.get_json()["formula_choice"] == "incident-file"
    bad = client.post("/videos", json={"project_id": "dom", "topic": "t", "strategy": "manual",
                                       "producibility_score": 7, "formula_choice": "nope"})
    assert bad.status_code == 400


def test_a_video_from_the_new_video_page_takes_its_pick_or_the_manual_domains_default(client, db_path):
    made = client.post("/videos/manual", json={"title": "A title", "topic": "A topic",
                                               "formula_choice": "myth-break-model"})
    assert made.status_code == 201 and made.get_json()["formula_choice"] == "myth-break-model"
    client.post("/projects", json={"id": pipeline.MANUAL_PROJECT_ID, "name": "Manual Videos",
                                   "default_formula_id": "scene-story"})
    made = client.post("/videos/manual", json={"title": "Another", "topic": "A topic"})
    assert made.get_json()["formula_choice"] == "scene-story"
    bad = client.post("/videos/manual", json={"title": "Bad", "topic": "A topic",
                                              "formula_choice": "nope"})
    assert bad.status_code == 400 and "formula_choice" in bad.get_json()["error"]


# ── the setting and the formula list ─────────────────────────────────────────

def test_auto_may_not_pick_experimental_formulas_until_the_setting_is_on(client, db_path):
    assert client.get("/settings").get_json()["auto_experimental_formulas"] is False
    assert client.post("/settings", json={"auto_experimental_formulas": True}).status_code == 200
    assert client.get("/settings").get_json()["auto_experimental_formulas"] is True
    assert client.post("/settings", json={"auto_experimental_formulas": "yes"}).status_code == 400


def test_the_formula_list_says_which_formulas_are_experimental(client, db_path):
    formulas = client.get("/script-formulas").get_json()["formulas"]
    assert [f["id"] for f in formulas] == list(tf.FORMULAS)
    assert {f["id"] for f in formulas if f["experimental"]} == \
        {fid for fid, f in tf.FORMULAS.items() if f["experimental"]}
