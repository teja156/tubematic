"""Domain pause over HTTP — seeds only, and enforced at filing (TMDEV-115).

The HTTP mirror of mcp/tests/test_project_pause.py. POST /videos is not only
the dashboard's proxy target, so the filing refusal has to live here too or
the pause is enforced on one write path and not the other.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import pathlib
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


def _project(db_path, pid, *, seed, status, name="Database internals"):
    """Insert directly, bypassing the rule — the only way to build the stray
    paused non-seed row an older install could still hold."""
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO projects (id, name, is_curriculum_seed, status, created_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z')",
        (pid, name, int(seed), status),
    )
    con.commit()
    con.close()


def _status(db_path, pid):
    con = sqlite3.connect(db_path)
    out = con.execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()[0]
    con.close()
    return out


def _video(client, strategy, project_id="db-internals"):
    return client.post("/videos", json={
        "project_id": project_id, "topic": "B-trees on disk",
        "strategy": strategy, "producibility_score": 7,
    })


# ── POST /videos refuses a paused domain ────────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining"])
def test_a_paused_domain_refuses_every_sourced_strategy(client, db_path, strategy):
    _project(db_path, "db-internals", seed=True, status="paused")
    r = _video(client, strategy)
    assert r.status_code == 409
    assert json.loads(client.get("/videos").data) == []


def test_the_refusal_names_the_domain(client, db_path):
    _project(db_path, "db-internals", seed=True, status="paused", name="Database internals")
    err = json.loads(_video(client, "trending").data)["error"]
    assert "Database internals" in err
    assert "paused" in err
    assert "manual" not in err.lower()


def test_a_manual_submission_is_accepted_into_a_paused_domain(client, db_path):
    _project(db_path, "db-internals", seed=True, status="paused")
    assert _video(client, "manual").status_code == 201


def test_a_stray_paused_non_seed_still_refuses(client, db_path):
    _project(db_path, "db-internals", seed=False, status="paused")
    assert _video(client, "trending").status_code == 409


def test_an_active_domain_is_unaffected(client, db_path):
    _project(db_path, "db-internals", seed=True, status="active")
    assert _video(client, "trending").status_code == 201


# ── only a curriculum seed can be paused ────────────────────────────────────

def test_the_status_route_pauses_a_seed(client, db_path):
    _project(db_path, "db-internals", seed=True, status="active")
    r = client.post("/projects/db-internals/status", json={"status": "paused"})
    assert r.status_code == 200
    assert json.loads(r.data)["status"] == "paused"


def test_the_status_route_refuses_to_pause_a_non_seed(client, db_path):
    _project(db_path, "db-internals", seed=False, status="active")
    r = client.post("/projects/db-internals/status", json={"status": "paused"})
    assert r.status_code == 409
    assert "curriculum seed" in json.loads(r.data)["error"]
    assert _status(db_path, "db-internals") == "active"


def test_the_status_route_can_still_activate_a_stray_paused_non_seed(client, db_path):
    _project(db_path, "db-internals", seed=False, status="paused")
    r = client.post("/projects/db-internals/status", json={"status": "active"})
    assert r.status_code == 200


def test_post_projects_refuses_a_paused_non_seed(client, db_path):
    r = client.post("/projects", json={"id": "db-internals", "name": "Database internals",
                                       "is_curriculum_seed": False, "status": "paused"})
    assert r.status_code == 400
    assert json.loads(client.get("/projects").data) == []


def test_post_projects_accepts_a_paused_seed(client, db_path):
    r = client.post("/projects", json={"id": "db-internals", "name": "Database internals",
                                       "is_curriculum_seed": True, "status": "paused"})
    assert r.status_code == 201
    assert json.loads(r.data)["status"] == "paused"


def test_post_projects_clearing_the_seed_leaves_the_domain_active(client, db_path):
    """POST /projects is a full replace: status defaults to active when it is
    omitted, which is what makes clearing the seed flag reactivate a domain."""
    _project(db_path, "db-internals", seed=True, status="paused")
    r = client.post("/projects", json={"id": "db-internals", "name": "Database internals",
                                       "is_curriculum_seed": False})
    assert r.status_code == 201
    assert json.loads(r.data)["status"] == "active"


# ── the two copies of the messages agree ────────────────────────────────────

def test_the_messages_match_the_mcp_copy():
    """The agent can reach either write path, so it must read the same
    instruction from both, and both INSERTs must enforce the same rule. Executes the MCP copy's source rather than
    comparing constants, which would miss a drifted f-string."""
    mcp_path = pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py"
    src = mcp_path.read_text()
    start = src.index("TOPIC_CAP_MIN = ")
    end = src.index("@mcp.tool", start)
    ns: dict = {}
    exec(compile(src[start:end], str(mcp_path), "exec"), ns)
    assert (ns["_paused_domain_error"]("db-internals", "Database internals")
            == pipeline._paused_domain_error("db-internals", "Database internals"))
    assert (ns["_expired_domain_error"]("db-internals", "Database internals", 100, 100)
            == pipeline._expired_domain_error("db-internals", "Database internals", 100, 100))
    assert ns["_non_seed_pause_error"]("db-internals") == pipeline._non_seed_pause_error("db-internals")
    # The topic cap (TMDEV-153) shares this block: its bounds, its validation
    # and the guard that enforces both rules inside the INSERT.
    for name in ("TOPIC_CAP_MIN", "TOPIC_CAP_MAX", "TOPIC_CAP_DEFAULT", "_TOPIC_COUNT_SQL",
                 "_PROJECT_SELECT", "_DOMAIN_OPEN_GUARD"):
        assert ns[name] == getattr(pipeline, name), name
    for bad in (24, 751, True, "100", 25, 750):
        assert ns["_topic_cap_error"](bad) == pipeline._topic_cap_error(bad)
    # So does the description cap (TMDEV-170).
    assert ns["PROJECT_DESCRIPTION_MAX_CHARS"] == pipeline.PROJECT_DESCRIPTION_MAX_CHARS
    for value in ("scope", "x" * 2000, "x" * 2001, ["a"], 7):
        assert ns["_description_error"](value) == pipeline._description_error(value)


def _pause_mid_request(monkeypatch, db_path):
    """Pause the domain inside the window between the early check and the
    INSERT. _pick_agent_id runs there, and the early SELECT holds no
    transaction, so without a guard in the INSERT the pause is missed."""
    real_pick = pipeline._pick_agent_id

    def _pause_then_pick(con, *a, **kw):
        other = sqlite3.connect(db_path)
        other.execute("UPDATE projects SET status = 'paused' WHERE id = 'db-internals'")
        other.commit()
        other.close()
        return real_pick(con, *a, **kw)

    monkeypatch.setattr(pipeline, "_pick_agent_id", _pause_then_pick)


def test_a_pause_landing_between_the_check_and_the_insert_still_refuses(client, db_path, monkeypatch):
    _project(db_path, "db-internals", seed=True, status="active")
    _pause_mid_request(monkeypatch, db_path)
    r = _video(client, "trending")
    assert r.status_code == 409
    assert "paused" in json.loads(r.data)["error"]
    assert json.loads(client.get("/videos").data) == []


def test_a_manual_submission_is_not_caught_by_the_insert_guard(client, db_path, monkeypatch):
    _project(db_path, "db-internals", seed=True, status="active")
    _pause_mid_request(monkeypatch, db_path)
    assert _video(client, "manual").status_code == 201
