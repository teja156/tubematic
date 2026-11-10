"""Auto's style pick over HTTP (TMDEV-203): the switch to the runner-up at
SCRIPT_READY, and the two rules that give a pick back (a changed style, a
topic revision).

The switch is the one HTTP write of the style after the topic checkpoint, so
every condition it checks is repeated in its UPDATE. The reset rules are the
same SQL fragments the MCP server uses (tubematic_core.visual_styles), so the
two processes cannot disagree on what a revision does to a pick.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import pathlib
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline  # noqa: E402
from pipeline import create_pipeline_blueprint  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

NOW = "2026-11-10T00:00:00Z"


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


def _video(db_path, vid="vid_1", status="SCRIPT_READY", style="system_flow",
           pick="system_flow", runner_up="stick", mascot=""):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, status, visual_style, style_pick, style_runner_up, "
        "style_reason, mascot_id, script, created_at, updated_at) "
        "VALUES (?, 't', ?, ?, ?, ?, 'why', ?, 'old script', ?, ?)",
        (vid, status, style, pick, runner_up, mascot, NOW, NOW))
    con.commit()
    con.close()
    return vid


def _row(db_path, vid="vid_1"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = dict(con.execute(
        "SELECT status, visual_style, style_pick, style_runner_up, style_reason FROM videos "
        "WHERE id = ?", (vid,)).fetchone())
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
    r = client.post("/videos/vid_1/switch-style")
    assert r.status_code == 200, r.get_json()
    assert _row(db_path) == {"status": "TOPIC_APPROVED", "visual_style": "stick",
                             "style_pick": "stick", "style_runner_up": "system_flow",
                             "style_reason": "Switched by a person from System Flow to Stick Explainer."}
    (author, content), = _comments(db_path)
    assert author == "human" and "Rewrite the script for Stick Explainer" in content
    assert r.get_json()["style_pick"] == "stick"


def test_switching_twice_goes_back(client, db_path):
    _video(db_path)
    client.post("/videos/vid_1/switch-style")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'SCRIPT_READY' WHERE id = 'vid_1'")
    con.commit()
    con.close()
    assert client.post("/videos/vid_1/switch-style").status_code == 200
    assert _row(db_path)["visual_style"] == "system_flow"


def test_a_switch_to_mixed_scenes_leaves_auto(client, db_path):
    _video(db_path, runner_up="scenes")
    assert client.post("/videos/vid_1/switch-style").status_code == 200
    row = _row(db_path)
    assert (row["visual_style"], row["style_pick"]) == ("auto", "scenes")


@pytest.mark.parametrize("kw, code, fragment", [
    ({"status": "TOPIC_APPROVED"}, 409, "Script Ready"),
    ({"status": "VOICING"}, 409, "Script Ready"),
    ({"pick": "", "style": "stick"}, 409, "Auto picked"),
    ({"runner_up": ""}, 409, "Auto picked"),
    ({"runner_up": "gone_style"}, 409, "no longer a style"),
    ({"runner_up": "illustrated"}, 409, "needs an OpenAI key"),
])
def test_the_switch_is_refused(client, db_path, kw, code, fragment):
    _video(db_path, **kw)
    before = _row(db_path)
    r = client.post("/videos/vid_1/switch-style")
    assert r.status_code == code and fragment in r.get_json()["error"]
    assert _row(db_path) == before


def test_an_unknown_video_is_404(client):
    assert client.post("/videos/nope/switch-style").status_code == 404


def test_an_archived_video_is_refused(client, db_path):
    _video(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET archived_at = ? WHERE id = 'vid_1'", (NOW,))
    con.commit()
    con.close()
    assert client.post("/videos/vid_1/switch-style").status_code == 409


def test_the_switch_holds_the_write_lock_while_it_checks(client, db_path, monkeypatch):
    """An approval, a second switch, a key removed in Settings or a GPU probe
    result cannot commit between the switch's checks and its write: while it
    checks what the install can make, every other writer is locked out.
    Mutation-check: drop BEGIN IMMEDIATE and the write below goes through."""
    _video(db_path)
    real = tvs.routing_candidates
    seen = []

    def probing(*a, **kw):
        other = sqlite3.connect(db_path, timeout=0)
        try:
            other.execute("UPDATE videos SET status = 'VOICING' WHERE id = 'vid_1'")
            other.commit()
            seen.append("wrote")
        except sqlite3.OperationalError as exc:
            seen.append(str(exc))
        finally:
            other.close()
        return real(*a, **kw)

    monkeypatch.setattr(tvs, "routing_candidates", probing)
    assert client.post("/videos/vid_1/switch-style").status_code == 200
    assert seen == ["database is locked"]
    assert _row(db_path)["status"] == "TOPIC_APPROVED"


# ── giving a pick back ───────────────────────────────────────────────────────

def test_a_changed_style_clears_the_pick_and_the_same_one_keeps_it(client, db_path):
    _video(db_path, status="TOPIC_PROPOSED")
    assert client.patch("/videos/vid_1", json={"visual_style": "system_flow"}).status_code == 200
    assert _row(db_path)["style_pick"] == "system_flow"
    assert client.patch("/videos/vid_1", json={"visual_style": "stick"}).status_code == 200
    assert _row(db_path) == {"status": "TOPIC_PROPOSED", "visual_style": "stick", "style_pick": "",
                             "style_runner_up": "", "style_reason": ""}


def test_a_move_back_to_the_topic_gives_the_pick_back_to_auto(client, db_path):
    _video(db_path, status="REVISION_REQUESTED")
    r = client.patch("/videos/vid_1", json={"status": "TOPIC_PROPOSED"})
    assert r.status_code == 200, r.get_json()
    assert _row(db_path) == {"status": "TOPIC_PROPOSED", "visual_style": "auto", "style_pick": "",
                             "style_runner_up": "", "style_reason": ""}


def test_a_person_chosen_style_survives_a_move_back_to_the_topic(client, db_path):
    _video(db_path, status="REVISION_REQUESTED", style="stick", pick="", runner_up="")
    client.patch("/videos/vid_1", json={"status": "TOPIC_PROPOSED"})
    assert _row(db_path)["visual_style"] == "stick"


def test_the_approval_keeps_the_pick(client, db_path):
    """The dashboard sends the picker's value with every approval."""
    _video(db_path, status="SCRIPT_READY")
    r = client.patch("/videos/vid_1", json={"status": "VOICING"})
    assert r.status_code == 200, r.get_json()
    assert _row(db_path)["style_pick"] == "system_flow"


def test_get_returns_the_pick_columns(client, db_path):
    _video(db_path)
    body = client.get("/videos/vid_1").get_json()
    assert (body["style_pick"], body["style_runner_up"], body["style_reason"]) == (
        "system_flow", "stick", "why")


def test_both_processes_use_the_shared_reset_sql():
    """The rules are SQL fragments in tubematic_core.visual_styles; the MCP
    server cannot be imported here, so its source is read."""
    mcp_src = (pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py").read_text()
    api_src = pathlib.Path(pipeline.__file__).read_text()
    for src in (mcp_src, api_src):
        assert "tvs.AUTO_PICK_RESET_SET" in src
        assert "tvs.style_change_clears_pick(" in src


def test_a_switch_clears_the_renderer_and_canvas_of_the_old_scenes(client, db_path):
    """The switch is followed by a new script, voice and scenes, so the canvas
    recorded for the old ones must not be forced on the new style."""
    _video(db_path, style="auto", pick="scenes", runner_up="illustrated")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET resolved_renderer = 'dom', resolved_visual_style = 'light'")
    con.execute("INSERT INTO settings (key, value) VALUES ('openai_api_key', 'sk-test')")
    con.commit()
    con.close()
    assert client.post("/videos/vid_1/switch-style").status_code == 200
    con = sqlite3.connect(db_path)
    got = con.execute("SELECT visual_style, resolved_renderer, resolved_visual_style FROM videos").fetchone()
    con.close()
    assert got == ("illustrated", "", "")


def test_a_person_changing_the_style_clears_the_old_scene_choices(client, db_path):
    _video(db_path, status="TOPIC_PROPOSED", style="auto", pick="", runner_up="")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET resolved_renderer = 'cartoon_3d', resolved_visual_style = 'dark'")
    con.commit()
    con.close()

    def resolved():
        c = sqlite3.connect(db_path)
        out = c.execute("SELECT resolved_renderer, resolved_visual_style FROM videos").fetchone()
        c.close()
        return out

    assert client.patch("/videos/vid_1", json={"visual_style": "auto"}).status_code == 200
    assert resolved() == ("cartoon_3d", "dark")
    assert client.patch("/videos/vid_1", json={"visual_style": "stick"}).status_code == 200
    assert resolved() == ("", "")
