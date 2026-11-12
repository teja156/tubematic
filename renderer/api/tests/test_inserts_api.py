"""Insert scenes over HTTP (TMDEV-224): the per-video Inserts setting, the
domain default that seeds it, insert styles refused as a video's or a domain's
style, the switch that makes inserts be decided again, and the review prompt's
notes on a video's inserts.

The setting is a person's choice at the topic, frozen after it like the style:
the script is written for inserts (its segments are marked), so changing the
setting later would leave a script that no longer fits.
"""
import json
import os
import sqlite3

import pytest

import ai_review
import pipeline
import render_results
from pipeline import create_pipeline_blueprint


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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


def _video(client, **extra):
    body = {"topic": "a topic", "strategy": "manual", "producibility_score": 7, **extra}
    return client.post("/videos", json=body).get_json()["id"]


def _project(client, pid="dom", **extra):
    return client.post("/projects", json={"id": pid, "name": "Dom", **extra})


# ── the per-video setting ────────────────────────────────────────────────────

def test_a_new_video_starts_with_inserts_on_auto(client):
    vid = _video(client)
    assert client.get(f"/videos/{vid}").get_json()["insert_mode"] == "auto"


def test_the_setting_is_a_persons_choice_at_the_topic(client):
    vid = _video(client)
    assert client.patch(f"/videos/{vid}", json={"insert_mode": "none"}).status_code == 200
    assert client.get(f"/videos/{vid}").get_json()["insert_mode"] == "none"
    r = client.patch(f"/videos/{vid}", json={"insert_mode": "some"})
    assert r.status_code == 400 and "insert_mode must be one of" in r.get_json()["error"]


def test_the_setting_is_frozen_after_the_topic(client):
    vid = _video(client)
    client.patch(f"/videos/{vid}", json={"status": "TOPIC_APPROVED"})
    r = client.patch(f"/videos/{vid}", json={"insert_mode": "none"})
    assert r.status_code == 409, r.get_json()


# ── domains ──────────────────────────────────────────────────────────────────

def test_a_domains_insert_setting_seeds_every_new_video(client):
    assert _project(client, default_insert_mode="none").status_code == 201
    body = {"topic": "t", "strategy": "trending", "producibility_score": 7, "project_id": "dom"}
    vid = client.post("/videos", json=body).get_json()["id"]
    assert client.get(f"/videos/{vid}").get_json()["insert_mode"] == "none"


def test_a_domain_save_that_leaves_the_setting_out_means_auto(client):
    _project(client, default_insert_mode="none")
    assert _project(client).get_json()["default_insert_mode"] == "auto"
    r = _project(client, default_insert_mode=3)
    assert r.status_code == 400 and "default_insert_mode" in r.get_json()["error"]


def test_a_domain_cannot_default_to_an_insert_style_but_keeps_a_stored_one(client, db_path):
    r = _project(client, default_visual_style="system_flow")
    assert r.status_code == 400 and "insert style" in r.get_json()["error"]
    _project(client)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE projects SET default_visual_style = 'terminal_doc' WHERE id = 'dom'")
    con.commit()
    con.close()
    # A full replace re-sends the stored value; only a change is refused.
    assert _project(client, default_visual_style="terminal_doc").status_code == 201


# ── New Video ────────────────────────────────────────────────────────────────

def test_new_video_takes_the_setting_and_refuses_an_insert_style(client):
    r = client.post("/videos/manual", json={"title": "A title", "topic": "t", "insert_mode": "none"})
    assert r.status_code == 201 and r.get_json()["insert_mode"] == "none"
    r = client.post("/videos/manual", json={"title": "A title", "topic": "t"})
    assert r.get_json()["insert_mode"] == "auto"
    r = client.post("/videos/manual", json={"title": "A title", "topic": "t", "visual_style": "system_flow"})
    assert r.status_code == 400 and "insert style" in r.get_json()["error"]
    r = client.post("/videos/manual", json={"title": "A title", "topic": "t", "insert_mode": "x"})
    assert r.status_code == 400


def test_post_videos_refuses_an_insert_style(client):
    r = client.post("/videos", json={"topic": "t", "strategy": "manual", "producibility_score": 7,
                                     "visual_style": "terminal_doc"})
    assert r.status_code == 400 and "insert style" in r.get_json()["error"]


# ── the switch to the runner-up ──────────────────────────────────────────────

def test_a_switch_to_the_runner_up_decides_the_inserts_again(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, status, visual_style, style_pick, style_runner_up, style_reason, "
        "insert_styles, insert_reason, created_at, updated_at) VALUES ('v1', 't', 'SCRIPT_READY', "
        "'whiteboard', 'whiteboard', 'stick', 'why', '[\"system_flow\"]', 'a flow', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert client.post("/videos/v1/switch-style").status_code == 200
    got = client.get("/videos/v1").get_json()
    assert (got["insert_styles"], got["insert_reason"]) == ("", "")


# ── the review prompt ────────────────────────────────────────────────────────

def test_the_review_prompt_names_each_insert_and_its_look():
    cfg = {"fps": 30, "inserts": [{"style": "system_flow", "startFrame": 600, "durationInFrames": 240},
                                  {"style": "whiteboard", "startFrame": 900, "durationInFrames": 60}]}
    block = render_results._insert_review_block(cfg)
    assert "INSERT SCENES" in block and "From 0:20.0 to 0:28.0:" in block
    assert "System Flow diagram" in block
    assert block.count("From ") == 1  # a main style is never read as an insert
    assert render_results._insert_review_block({"fps": 30}) == ""


def test_the_review_prompt_carries_the_block():
    assert ai_review.insert_review_block([]) == ""
    assert "From 1:05.5 to 1:12.0:" in ai_review.insert_review_block([(65.5, 72.0, "- note\n")])


def test_the_visual_styles_list_marks_insert_styles(client):
    styles = {s["id"]: s for s in client.get("/visual-styles").get_json()["styles"]}
    assert styles["terminal_doc"]["role"] == "insert"
    assert styles["cartoon_3d"]["inserts"] == {"host": False}
    assert styles["auto"]["inserts"]["host"] is True
    assert json.dumps(styles)  # serialisable as the dashboard reads it


def test_a_video_reports_the_inserts_its_scene_config_holds(client, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "JOBS_DIR", tmp_path / "jobs")
    vid = _video(client)
    assert client.get(f"/videos/{vid}").get_json()["insert_summary"] is None
    d = tmp_path / "jobs" / vid
    d.mkdir(parents=True)
    (d / "scene-config.json").write_text(json.dumps({"fps": 30, "inserts": [
        {"style": "system_flow", "startFrame": 300, "durationInFrames": 240},
        {"style": "terminal_doc", "startFrame": 900, "durationInFrames": 150}]}))
    assert client.get(f"/videos/{vid}").get_json()["insert_summary"] == {
        "count": 2, "seconds": 13.0, "styles": ["system_flow", "terminal_doc"]}


def test_a_return_to_the_topic_gives_a_legacy_insert_style_back_to_auto(client, db_path):
    """A person chose System Flow before it became an insert style: a revised
    topic gets a new script, which is never a whole System Flow video."""
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, status, visual_style, style_pick, resolved_renderer, created_at, "
        "updated_at) VALUES ('v2', 't', 'REVISION_REQUESTED', 'system_flow', '', 'dom', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.execute(
        "INSERT INTO videos (id, topic, status, visual_style, style_pick, created_at, updated_at) "
        "VALUES ('v3', 't', 'REVISION_REQUESTED', 'whiteboard', '', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    for vid in ("v2", "v3"):
        r = client.patch(f"/videos/{vid}", json={"status": "TOPIC_PROPOSED"})
        assert r.status_code == 200, r.get_json()
    v2, v3 = client.get("/videos/v2").get_json(), client.get("/videos/v3").get_json()
    assert (v2["visual_style"], v2["resolved_renderer"]) == ("auto", "")
    assert v3["visual_style"] == "whiteboard"  # a person's main style is kept
