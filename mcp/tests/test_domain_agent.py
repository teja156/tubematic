"""A domain's agent, model and effort through MCP (TMDEV-207).

The MCP copy of renderer/api/tests/test_domain_agent.py: create_video copies
the three values onto a new video, a domain on Automatic is still dealt by
weight, and upsert_project checks the agent and its model only when the pair
changes. Unlike POST /projects, upsert_project is a partial update, so an
omitted field is kept, with one exception that exists to stop a refused write
later: changing the agent without naming a model clears the stored model.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json

import pytest

import server

T0 = "2026-01-01T00:00:00Z"


@pytest.fixture
def db(tmp_path, monkeypatch):
    """claude takes every dealt video (weight 1); codex takes none (weight 0),
    so a video on codex can only have got there from its domain."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    _agent("claude", is_default=1, weight=1)
    _agent("codex", models=("gpt-a", "gpt-b"), weight=0)
    return tmp_path / "test.db"


def _agent(aid, models=("sonnet", "opus"), is_default=0, weight=1, archived_at=None):
    with server._conn() as con:
        con.execute(
            "INSERT INTO agents (id, name, binary, run_path, models, is_default, weight,"
            " archived_at, created_at, updated_at) VALUES (?, ?, ?, '/w', ?, ?, ?, ?, ?, ?)",
            (aid, aid.title(), f"/bin/{aid}", json.dumps(list(models)), is_default, weight,
             archived_at, T0, T0))


def _sql(sql, params=()):
    with server._conn() as con:
        return [tuple(r) for r in con.execute(sql, params).fetchall()]


def _defaults(row):
    return row["default_agent_id"], row["default_agent_model"], row["default_agent_effort"]


def _file(strategy="trending", pid="dom"):
    result = server.create_video(project_id=pid, topic="t", strategy=strategy,
                                 producibility_score=7)
    assert "error" not in result, result
    return result


def _picks(result):
    stored = _sql("SELECT agent_id, agent_model, agent_effort FROM videos WHERE id = ?",
                  (result["video_id"],))[0]
    # The result an agent reads must say what was stored.
    assert stored == (result["agent_id"], result["agent_model"], result["agent_effort"])
    return stored


# ── upsert_project ───────────────────────────────────────────────────────────

def test_upsert_project_stores_the_agent_model_and_effort(db):
    row = server.upsert_project("dom", "Domain", default_agent_id="codex",
                                default_agent_model="gpt-b", default_agent_effort="max")
    assert _defaults(row) == ("codex", "gpt-b", "max")
    assert _defaults(server.list_projects()[0]) == ("codex", "gpt-b", "max")


def test_a_new_domain_is_on_automatic(db):
    assert _defaults(server.upsert_project("dom", "Domain")) == ("", "", "")


def test_omitted_fields_are_kept(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b", default_agent_effort="max")
    row = server.upsert_project("dom", "Domain", description="edited")
    assert _defaults(row) == ("codex", "gpt-b", "max")


def test_blank_clears_each_field(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b", default_agent_effort="max")
    row = server.upsert_project("dom", "Domain", default_agent_id="", default_agent_effort="")
    assert _defaults(row) == ("", "", "")


@pytest.mark.parametrize("fields,names", [
    ({"default_agent_id": "ghost"}, "default_agent_id"),
    ({"default_agent_id": "codex", "default_agent_model": "sonnet"}, "default_agent_model"),
    ({"default_agent_model": "sonnet"}, "default_agent_id"),
    ({"default_agent_effort": "extreme"}, "default_agent_effort"),
])
def test_an_unusable_value_is_refused_and_nothing_is_written(db, fields, names):
    result = server.upsert_project("dom", "Domain", **fields)
    assert names in result["error"]
    assert _sql("SELECT COUNT(*) FROM projects") == [(0,)]


def test_an_uninstalled_agent_is_refused(db):
    _agent("gone", archived_at=T0)
    assert "uninstalled" in server.upsert_project("dom", "Domain",
                                                  default_agent_id="gone")["error"]


def test_an_effort_needs_no_agent(db):
    row = server.upsert_project("dom", "Domain", default_agent_effort="low")
    assert _defaults(row) == ("", "", "low")


def test_changing_the_agent_alone_clears_the_stored_model(db):
    """The stored model belongs to the old agent's list. Keeping it would make
    this call fail for a caller that only meant to move the domain."""
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b")
    row = server.upsert_project("dom", "Domain", default_agent_id="claude")
    assert _defaults(row) == ("claude", "", "")


def test_a_model_alone_is_checked_against_the_stored_agent(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex")
    assert "error" in server.upsert_project("dom", "Domain", default_agent_model="sonnet")
    row = server.upsert_project("dom", "Domain", default_agent_model="gpt-a")
    assert _defaults(row) == ("codex", "gpt-a", "")


def test_a_stored_pair_that_went_stale_does_not_block_another_edit(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b")
    _sql("UPDATE agents SET archived_at = ? WHERE id = 'codex'", (T0,))
    for fields in ({}, {"default_agent_id": "codex"},
                   {"default_agent_id": "codex", "default_agent_model": "gpt-b"}):
        row = server.upsert_project("dom", "Domain", description="edited", **fields)
        assert _defaults(row) == ("codex", "gpt-b", ""), fields


# ── create_video ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining", "manual"])
def test_every_strategy_starts_on_the_domains_agent(db, strategy):
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b", default_agent_effort="max")
    assert _picks(_file(strategy)) == ("codex", "gpt-b", "max")


def test_an_automatic_domain_is_dealt_as_before(db):
    server.upsert_project("dom", "Domain")
    assert _picks(_file()) == ("claude", "", "")


def test_a_domain_agent_takes_no_card_from_the_deck(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex")
    _file()
    assert _sql("SELECT COUNT(*) FROM agent_deck") == [(0,)]


def test_an_uninstalled_domain_agent_falls_back_to_the_deal(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b", default_agent_effort="max")
    _sql("UPDATE agents SET archived_at = ? WHERE id = 'codex'", (T0,))
    assert _picks(_file()) == ("claude", "", "max")


def test_a_model_the_agent_dropped_seeds_the_agents_default(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_model="gpt-b")
    _sql("UPDATE agents SET models = ? WHERE id = 'codex'", (json.dumps(["gpt-a"]),))
    assert _picks(_file()) == ("codex", "", "")


def test_an_effort_alone_rides_on_the_dealt_agent(db):
    server.upsert_project("dom", "Domain", default_agent_effort="low")
    assert _picks(_file()) == ("claude", "", "low")


def test_changing_the_domain_never_reaches_back(db):
    server.upsert_project("dom", "Domain", default_agent_id="codex")
    first = _file()
    server.upsert_project("dom", "Domain", default_agent_id="claude")
    assert _picks(first)[0] == "codex"


class _Gemini:
    """A fake httpx.Client that returns one mined candidate."""

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        import json as _json
        topics = [{"topic": "How a write-ahead log survives a crash",
                   "producibility_score": 8}]

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"candidates": [{"content": {"parts": [{"text": _json.dumps(topics)}]}}],
                        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10}}
        return _Resp()


def test_a_mined_topic_starts_on_the_domains_agent(db, monkeypatch):
    import httpx
    server.upsert_project("dom", "Domain", default_agent_id="codex",
                          default_agent_effort="max")
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "Client", _Gemini())
    result = server.mine_youtube_topics(project_id="dom",
                                        youtube_urls=["https://youtu.be/00000000001"])
    assert result["proposed"] == 1
    assert _sql("SELECT agent_id, agent_model, agent_effort FROM videos") == [("codex", "", "max")]
