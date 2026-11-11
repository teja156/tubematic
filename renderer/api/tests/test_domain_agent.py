"""A domain's agent, model and effort (TMDEV-207).

A domain can name the agent its new videos start on, with a model from that
agent's list and an effort level. The three values are copied onto a video when
it is filed (POST /videos, POST /videos/manual), like the domain's voice, and
"" on the agent means Automatic: the weighted deal, as before.

The tests that matter most:
- an Automatic domain still deals, through _pick_agent_id itself (the pause and
  topic-cap race tests hook that call);
- a default that went stale (agent uninstalled, model dropped) never blocks an
  unrelated edit to the domain, because POST /projects is a full replace the
  dashboard re-sends on every edit.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import pathlib
import shutil
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint

T0 = "2026-01-01T00:00:00Z"


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
    try:
        rows = con.execute(sql, params).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _agent(db_path, aid, models=("sonnet", "opus"), is_default=0, weight=1, archived_at=None):
    _sql(db_path,
         "INSERT INTO agents (id, name, binary, run_path, install_scope, models, effort,"
         " is_default, weight, verified_at, archived_at, created_at, updated_at)"
         " VALUES (?, ?, ?, ?, 'user', ?, 'high', ?, ?, ?, ?, ?, ?)",
         (aid, aid.title(), f"/usr/local/bin/{aid}", f"/home/u/.{aid}-agent",
          json.dumps(list(models)), is_default, weight, T0, archived_at, T0, T0))


@pytest.fixture
def agents(db_path):
    """claude takes every dealt video (weight 1); codex takes none (weight 0),
    so a video on codex can only have got there from its domain."""
    _agent(db_path, "claude", is_default=1, weight=1)
    _agent(db_path, "codex", models=("gpt-a", "gpt-b"), weight=0)


def _project(client, pid="p1", **extra):
    return client.post("/projects", json={"id": pid, "name": "P", **extra})


def _file(client, strategy="trending", pid="p1"):
    r = client.post("/videos", json={"topic": "x", "strategy": strategy,
                                     "producibility_score": 7, "project_id": pid})
    assert r.status_code == 201, r.data
    return json.loads(r.data)


def _picks(video):
    return video["agent_id"], video["agent_model"], video["agent_effort"]


# ── storing the default ──────────────────────────────────────────────────────

def test_a_domain_stores_its_agent_model_and_effort(client, agents):
    r = _project(client, default_agent_id="codex", default_agent_model="gpt-b",
                 default_agent_effort="max")
    assert r.status_code == 201
    row = json.loads(r.data)
    assert (row["default_agent_id"], row["default_agent_model"],
            row["default_agent_effort"]) == ("codex", "gpt-b", "max")
    listed = json.loads(client.get("/projects").data)[0]
    assert listed["default_agent_id"] == "codex"


def test_a_new_domain_is_on_automatic(client, agents):
    row = json.loads(_project(client).data)
    assert (row["default_agent_id"], row["default_agent_model"],
            row["default_agent_effort"]) == ("", "", "")


@pytest.mark.parametrize("field", ["default_agent_id", "default_agent_model",
                                   "default_agent_effort"])
@pytest.mark.parametrize("bad", [False, 0, ["codex"]])
def test_a_non_string_is_refused_not_read_as_blank(client, agents, field, bad):
    assert _project(client, **{field: bad}).status_code == 400


def test_null_means_blank(client, agents):
    r = _project(client, default_agent_id=None, default_agent_model=None,
                 default_agent_effort=None)
    assert r.status_code == 201


def test_an_agent_that_is_not_installed_is_refused(client, agents):
    r = _project(client, default_agent_id="ghost")
    assert r.status_code == 400
    assert "default_agent_id" in json.loads(r.data)["error"]


def test_an_uninstalled_agent_is_refused(client, db_path, agents):
    _agent(db_path, "gone", archived_at=T0)
    assert _project(client, default_agent_id="gone").status_code == 400


def test_a_model_the_agent_does_not_offer_is_refused(client, agents):
    r = _project(client, default_agent_id="codex", default_agent_model="sonnet")
    assert r.status_code == 400
    assert "default_agent_model" in json.loads(r.data)["error"]


def test_a_model_needs_an_agent(client, agents):
    r = _project(client, default_agent_model="sonnet")
    assert r.status_code == 400
    assert "default_agent_id" in json.loads(r.data)["error"]


def test_an_effort_outside_the_set_is_refused(client, agents):
    assert _project(client, default_agent_effort="extreme").status_code == 400


def test_an_effort_needs_no_agent(client, agents):
    r = _project(client, default_agent_effort="low")
    assert r.status_code == 201 and json.loads(r.data)["default_agent_effort"] == "low"


def test_omitting_the_fields_returns_the_domain_to_automatic(client, agents):
    """The route is a full replace: a field left out is reset, like the voice."""
    _project(client, default_agent_id="codex", default_agent_model="gpt-b",
             default_agent_effort="max")
    row = json.loads(_project(client).data)
    assert (row["default_agent_id"], row["default_agent_model"],
            row["default_agent_effort"]) == ("", "", "")


def test_a_kept_agent_since_uninstalled_does_not_block_other_edits(client, db_path, agents):
    _project(client, default_agent_id="codex", default_agent_model="gpt-b")
    _sql(db_path, "UPDATE agents SET archived_at = ? WHERE id = 'codex'", (T0,))
    r = _project(client, description="edited", default_agent_id="codex",
                 default_agent_model="gpt-b")
    assert r.status_code == 201


def test_a_kept_model_since_dropped_does_not_block_other_edits(client, db_path, agents):
    _project(client, default_agent_id="codex", default_agent_model="gpt-b")
    _sql(db_path, "UPDATE agents SET models = ? WHERE id = 'codex'", (json.dumps(["gpt-a"]),))
    r = _project(client, description="edited", default_agent_id="codex",
                 default_agent_model="gpt-b")
    assert r.status_code == 201


def test_a_changed_model_is_checked_even_when_the_agent_is_kept(client, agents):
    _project(client, default_agent_id="codex", default_agent_model="gpt-b")
    r = _project(client, default_agent_id="codex", default_agent_model="sonnet")
    assert r.status_code == 400


def test_a_changed_agent_is_checked_against_the_model_sent_with_it(client, agents):
    """The old model belongs to the old agent's list, so it cannot ride along."""
    _project(client, default_agent_id="codex", default_agent_model="gpt-b")
    assert _project(client, default_agent_id="claude",
                    default_agent_model="gpt-b").status_code == 400
    assert _project(client, default_agent_id="claude").status_code == 201


# ── filing a video into the domain ───────────────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining", "manual"])
def test_every_strategy_starts_on_the_domains_agent(client, agents, strategy):
    _project(client, default_agent_id="codex", default_agent_model="gpt-b",
             default_agent_effort="max")
    assert _picks(_file(client, strategy)) == ("codex", "gpt-b", "max")


def test_an_automatic_domain_is_dealt_as_before(client, agents):
    _project(client)
    assert _picks(_file(client)) == ("claude", "", "")


def test_an_automatic_domain_deals_through_the_picker(client, agents, monkeypatch):
    """The pause and topic-cap race tests hook _pick_agent_id to act between
    the early check and the INSERT, so the Automatic path must keep calling it."""
    _project(client)
    calls = []
    real = pipeline._pick_agent_id
    monkeypatch.setattr(pipeline, "_pick_agent_id", lambda con: calls.append(1) or real(con))
    _file(client)
    assert calls == [1]


def test_a_domain_agent_takes_no_card_from_the_deck(client, db_path, agents):
    _project(client, default_agent_id="codex")
    _file(client)
    assert _sql(db_path, "SELECT COUNT(*) FROM agent_deck") == [(0,)]


def test_an_uninstalled_domain_agent_falls_back_to_the_deal(client, db_path, agents):
    _project(client, default_agent_id="codex", default_agent_model="gpt-b",
             default_agent_effort="max")
    _sql(db_path, "UPDATE agents SET archived_at = ? WHERE id = 'codex'", (T0,))
    # The model belonged to codex, so it is not carried to the dealt agent.
    assert _picks(_file(client)) == ("claude", "", "max")


def test_a_model_the_agent_dropped_seeds_the_agents_default(client, db_path, agents):
    _project(client, default_agent_id="codex", default_agent_model="gpt-b")
    _sql(db_path, "UPDATE agents SET models = ? WHERE id = 'codex'", (json.dumps(["gpt-a"]),))
    assert _picks(_file(client)) == ("codex", "", "")


def test_an_effort_alone_rides_on_the_dealt_agent(client, agents):
    _project(client, default_agent_effort="low")
    assert _picks(_file(client)) == ("claude", "", "low")


def test_a_video_with_no_domain_is_dealt(client, agents):
    r = client.post("/videos", json={"topic": "x", "strategy": "trending",
                                     "producibility_score": 7})
    assert _picks(json.loads(r.data)) == ("claude", "", "")


def test_changing_the_domain_never_reaches_back(client, db_path, agents):
    _project(client, default_agent_id="codex")
    vid = _file(client)["id"]
    _project(client, default_agent_id="claude")
    assert _sql(db_path, "SELECT agent_id FROM videos WHERE id = ?", (vid,)) == [("codex",)]


def test_no_agent_installed_still_files_the_video(client):
    _project(client, default_agent_effort="low")
    assert _picks(_file(client)) == (None, "", "low")


# ── the New Video page's domain ──────────────────────────────────────────────

def _manual(client, **body):
    r = client.post("/videos/manual", json={"title": "T", "topic": "x", **body})
    assert r.status_code == 201, r.data
    return json.loads(r.data)


def test_a_manual_submission_on_automatic_takes_the_manual_domains_agent(client, agents):
    assert _picks(_manual(client)) == ("claude", "", "")  # the domain has none yet
    _project(client, pid=pipeline.MANUAL_PROJECT_ID, default_agent_id="codex",
             default_agent_model="gpt-b", default_agent_effort="max")
    assert _picks(_manual(client)) == ("codex", "gpt-b", "max")


def test_a_picked_effort_beats_the_manual_domains(client, agents):
    _project(client, pid=pipeline.MANUAL_PROJECT_ID, default_agent_id="codex",
             default_agent_effort="max")
    assert _picks(_manual(client, agent_effort="low")) == ("codex", "", "low")


def test_a_picked_agent_overrides_the_domains_agent_model_and_effort_together(client, agents):
    _project(client, pid=pipeline.MANUAL_PROJECT_ID, default_agent_id="codex",
             default_agent_model="gpt-b", default_agent_effort="max")
    assert _picks(_manual(client, agent_id="claude")) == ("claude", "", "")
    assert _picks(_manual(client, agent_id="claude", agent_model="opus",
                          agent_effort="low")) == ("claude", "opus", "low")


# ── the MCP copy ─────────────────────────────────────────────────────────────

def _mcp_functions(*names):
    path = pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py"
    src = path.read_text()
    ns = {"_pick_agent_id": pipeline._pick_agent_id, "_agent_models": pipeline._agent_models,
          "_agent_id_error": pipeline._agent_id_error,
          "_agent_model_error": pipeline._agent_model_error,
          "AGENT_EFFORTS": pipeline.AGENT_EFFORTS}
    for name in names:
        start = src.index(f"def {name}(")
        exec(compile(src[start:src.index("\ndef ", start + 1)], str(path), "exec"), ns)
    return [ns[name] for name in names]


def _domains_db(db_path, tmp_path):
    """Domains covering every branch, and one copy of the database per
    implementation: dealing writes the deck, so sharing one would interleave."""
    _agent(db_path, "claude", is_default=1, weight=1)
    _agent(db_path, "codex", models=("gpt-a", "gpt-b"), weight=0)
    _agent(db_path, "gone", archived_at=T0)
    rows = [("auto", "", "", ""), ("pinned", "codex", "gpt-b", "max"),
            ("stale_model", "codex", "sonnet", ""), ("uninstalled", "gone", "sonnet", "low"),
            ("missing", "ghost", "", ""), ("effort_only", "", "", "xhigh"),
            ("bad_effort", "codex", "", "extreme")]
    for pid, aid, model, effort in rows:
        _sql(db_path,
             "INSERT INTO projects (id, name, default_agent_id, default_agent_model,"
             " default_agent_effort, created_at) VALUES (?, ?, ?, ?, ?, ?)",
             (pid, pid, aid, model, effort, T0))
    other = str(tmp_path / "mcp-copy.db")
    shutil.copy(db_path, other)
    return [r[0] for r in rows] + [None, "no_such_domain"], other


def test_the_seeding_matches_the_mcp_copy(db_path, tmp_path):
    (mcp_fn,) = _mcp_functions("_domain_agent")
    pids, other = _domains_db(db_path, tmp_path)
    ours, theirs = sqlite3.connect(db_path), sqlite3.connect(other)
    ours.row_factory = theirs.row_factory = sqlite3.Row
    try:
        for pid in pids:
            assert mcp_fn(theirs, pid) == pipeline._domain_agent(ours, pid), pid
    finally:
        ours.close()
        theirs.close()


def test_the_refusals_match_the_mcp_copy(db_path, tmp_path):
    (mcp_fn,) = _mcp_functions("_domain_agent_error")
    _domains_db(db_path, tmp_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        for aid in ("", "claude", "codex", "gone", "ghost"):
            for model in ("", "sonnet", "gpt-b"):
                assert (mcp_fn(con, aid, model)
                        == pipeline._domain_agent_error(con, aid, model)), (aid, model)
    finally:
        con.close()
