"""The agent, model and effort the topic-research session runs on (TMDEV-243).

Three install-wide settings keys, all blank by default, which means the default
agent, its first model and its own effort, as before the keys existed.
POST /settings checks the agent and model like a domain's agent (installed and
live, model in that agent's list) and only when the pair changes, so a pair that
went stale (agent uninstalled since) never blocks an unrelated save.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint

T0 = "2026-01-01T00:00:00Z"
KEYS = ("research_agent_id", "research_agent_model", "research_agent_effort")


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


def _agent(db_path, aid, models=("sonnet", "opus"), is_default=0, archived_at=None):
    _sql(db_path,
         "INSERT INTO agents (id, name, binary, run_path, install_scope, models, effort,"
         " is_default, weight, verified_at, archived_at, created_at, updated_at)"
         " VALUES (?, ?, ?, ?, 'user', ?, 'high', ?, 1, ?, ?, ?, ?)",
         (aid, aid.title(), f"/usr/local/bin/{aid}", f"/home/u/.{aid}-agent",
          json.dumps(list(models)), is_default, T0, archived_at, T0, T0))


@pytest.fixture
def agents(db_path):
    _agent(db_path, "claude", is_default=1)
    _agent(db_path, "codex", models=("gpt-a", "gpt-b"))
    _agent(db_path, "old", archived_at=T0)


def _post(client, **body):
    return client.post("/settings", json=body)


def _err(r):
    return json.loads(r.data)["error"]


def test_the_three_keys_default_to_blank(client):
    data = json.loads(client.get("/settings").data)
    assert [data[k] for k in KEYS] == ["", "", ""]


def test_a_live_agent_model_and_effort_are_stored(client, agents):
    r = _post(client, research_agent_id="codex", research_agent_model="gpt-b",
              research_agent_effort="max")
    assert r.status_code == 200, r.data
    data = json.loads(client.get("/settings").data)
    assert [data[k] for k in KEYS] == ["codex", "gpt-b", "max"]


def test_an_agent_alone_and_an_effort_alone_are_fine(client, agents):
    assert _post(client, research_agent_id="codex").status_code == 200
    assert _post(client, research_agent_effort="low").status_code == 200


def test_an_unknown_agent_is_refused_with_the_research_name(client, agents):
    r = _post(client, research_agent_id="nope")
    assert r.status_code == 400
    assert "research_agent_id" in _err(r)
    assert "default_agent_id" not in _err(r)


def test_an_uninstalled_agent_is_refused(client, agents):
    r = _post(client, research_agent_id="old")
    assert r.status_code == 400
    assert "uninstalled" in _err(r)


def test_a_model_without_an_agent_is_refused(client, agents):
    r = _post(client, research_agent_model="sonnet")
    assert r.status_code == 400
    assert "research_agent_model" in _err(r)
    assert "research_agent_id" in _err(r)


def test_a_model_the_agent_does_not_offer_is_refused(client, agents):
    r = _post(client, research_agent_id="codex", research_agent_model="sonnet")
    assert r.status_code == 400
    assert "research_agent_model" in _err(r)


def test_a_model_is_checked_against_the_stored_agent(client, agents):
    _post(client, research_agent_id="codex")
    assert _post(client, research_agent_model="gpt-a").status_code == 200
    assert _post(client, research_agent_model="sonnet").status_code == 400


def test_changing_the_agent_needs_the_model_cleared_in_the_same_save(client, agents):
    _post(client, research_agent_id="codex", research_agent_model="gpt-a")
    assert _post(client, research_agent_id="claude").status_code == 400
    r = _post(client, research_agent_id="claude", research_agent_model="")
    assert r.status_code == 200, r.data


def test_a_bad_effort_is_refused(client, agents):
    r = _post(client, research_agent_effort="extreme")
    assert r.status_code == 400
    assert "research_agent_effort" in _err(r)


def test_back_to_blank_is_always_allowed(client, agents):
    _post(client, research_agent_id="codex", research_agent_model="gpt-a",
          research_agent_effort="low")
    r = _post(client, research_agent_id="", research_agent_model="", research_agent_effort="")
    assert r.status_code == 200
    assert [json.loads(client.get("/settings").data)[k] for k in KEYS] == ["", "", ""]


def test_a_stale_pair_never_blocks_an_unrelated_save(client, db_path, agents):
    _post(client, research_agent_id="codex", research_agent_model="gpt-a")
    _sql(db_path, "UPDATE agents SET archived_at = ? WHERE id = 'codex'", (T0,))
    r = _post(client, research_agent_id="codex", research_agent_model="gpt-a",
              research_pending_cap=9)
    assert r.status_code == 200, r.data
    data = json.loads(client.get("/settings").data)
    assert (data["research_agent_id"], data["research_pending_cap"]) == ("codex", 9)
    assert _post(client, research_pending_cap=10).status_code == 200


def test_a_stale_agent_can_be_cleared(client, db_path, agents):
    _post(client, research_agent_id="codex", research_agent_model="gpt-a")
    _sql(db_path, "UPDATE agents SET archived_at = ? WHERE id = 'codex'", (T0,))
    assert _post(client, research_agent_id="", research_agent_model="").status_code == 200
