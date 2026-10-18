"""POST /videos/manual — a video submitted by hand from the dashboard (TMDEV-118).

A separate route from POST /videos on purpose: that one is built for research
runs, where failing a create would lose a topic, so it clips an over-long title
and ignores a supplied agent_id. Here a human is present and picked the agent,
so both go the other way — an over-long title is refused and a picked agent is
kept.

Every dashboard submission is filed into one fixed domain, `manual`, created on
first use. The tests that matter most are the "writes nothing" ones: _conn()
commits on exit, so a refusal that came after the domain INSERT would leave an
empty domain behind on every bad submission.

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
def db_path(tmp_path, monkeypatch):
    """A fully migrated database. OPENAI_API_KEY is cleared because the
    Illustrated key gate falls back to it."""
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


def _sql(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(sql, params).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _seed_agent(db_path, aid="claude", models=("sonnet", "opus"), is_default=1, weight=1,
                archived_at=None):
    _sql(db_path,
         "INSERT INTO agents (id, name, binary, run_path, install_scope, models, effort,"
         " is_default, weight, verified_at, archived_at, created_at, updated_at)"
         " VALUES (?, ?, ?, ?, 'user', ?, 'high', ?, ?, ?, ?, ?, ?)",
         (aid, aid.title(), f"/usr/local/bin/{aid}", f"/home/u/.{aid}-agent",
          json.dumps(list(models)), is_default, weight, "2026-01-01T00:00:00Z", archived_at,
          "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))


def _seed_profile(db_path, pid="prof-1", status="READY"):
    _sql(db_path,
         "INSERT INTO script_profiles (id, name, status, created_at, updated_at)"
         " VALUES (?, 'Mine', ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
         (pid, status))


def _submit(client, **body):
    payload = {"title": "How DNS resolves a name", "topic": "Walk a DNS lookup end to end"}
    payload.update(body)
    return client.post("/videos/manual", json=payload)


def _counts(db_path):
    return (_sql(db_path, "SELECT COUNT(*) FROM projects")[0][0],
            _sql(db_path, "SELECT COUNT(*) FROM videos")[0][0])


# ── the happy path ──────────────────────────────────────────────────────────

def test_a_submission_lands_approved_in_the_manual_domain(client, db_path):
    r = _submit(client)
    assert r.status_code == 201
    v = json.loads(r.data)
    assert v["status"] == "TOPIC_APPROVED"
    assert v["strategy"] == "manual"
    assert v["producibility_score"] == 0
    assert v["project_id"] == pipeline.MANUAL_PROJECT_ID == "manual"
    assert v["title"] == "How DNS resolves a name"
    assert v["topic"] == "Walk a DNS lookup end to end"
    assert v["video_version"] == 1


def test_unchecking_auto_approve_leaves_it_at_topic_proposed(client):
    v = json.loads(_submit(client, approve=False).data)
    assert v["status"] == "TOPIC_PROPOSED"


def test_the_manual_domain_is_created_once_as_an_active_non_seed(client, db_path):
    assert _sql(db_path, "SELECT COUNT(*) FROM projects")[0][0] == 0
    _submit(client)
    _submit(client)
    rows = _sql(db_path, "SELECT id, name, is_curriculum_seed, status, description FROM projects")
    assert len(rows) == 1
    pid, name, seed, status, description = rows[0]
    assert (pid, name, seed, status) == ("manual", "Manual Videos", 0, "active")
    # The research agent reads descriptions from list_projects(); this is what
    # keeps its subject matching from filing a researched topic here.
    assert "never file researched topics here" in description


def test_a_renamed_manual_domain_is_not_overwritten(client, db_path):
    _submit(client)
    _sql(db_path, "UPDATE projects SET name = 'Hand-picked' WHERE id = 'manual'")
    _submit(client)
    assert _sql(db_path, "SELECT name FROM projects WHERE id = 'manual'")[0][0] == "Hand-picked"


def test_optional_picks_are_stored(client, db_path):
    _seed_agent(db_path)
    _seed_profile(db_path)
    client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]})
    v = json.loads(_submit(client, agent_id="claude", agent_model="opus", agent_effort="max",
                           script_profile_id="prof-1", visual_style="stick",
                           voice_id="abc123").data)
    assert (v["agent_id"], v["agent_model"], v["agent_effort"]) == ("claude", "opus", "max")
    assert v["script_profile_id"] == "prof-1"
    assert v["visual_style"] == "stick"
    assert v["voice_id"] == "abc123"


def test_untouched_picks_mean_the_defaults(client, db_path):
    v = json.loads(_submit(client).data)
    assert v["agent_model"] == "" and v["agent_effort"] == ""
    assert v["script_profile_id"] in ("", None)
    assert v["visual_style"] == pipeline.DEFAULT_VISUAL_STYLE
    assert v["voice_id"] == ""


def test_null_picks_mean_the_defaults(client):
    v = json.loads(_submit(client, agent_id=None, agent_model=None, agent_effort=None,
                           visual_style=None, voice_id=None, script_profile_id=None).data)
    assert v["visual_style"] == pipeline.DEFAULT_VISUAL_STYLE
    assert (v["agent_model"], v["agent_effort"], v["voice_id"]) == ("", "", "")


def test_title_and_topic_are_stripped(client):
    v = json.loads(_submit(client, title="  Short  ", topic="  Brief  ").data)
    assert (v["title"], v["topic"]) == ("Short", "Brief")


# ── the agent ───────────────────────────────────────────────────────────────

def test_no_agent_picked_is_dealt_like_any_new_video(client, db_path):
    _seed_agent(db_path)
    assert json.loads(_submit(client).data)["agent_id"] == "claude"


def test_no_agent_installed_leaves_agent_id_null(client):
    assert json.loads(_submit(client).data)["agent_id"] is None


def test_a_picked_agent_is_kept_not_redealt(client, db_path):
    _seed_agent(db_path, "claude", weight=100)
    _seed_agent(db_path, "codex", models=("gpt-5",), is_default=0, weight=0)
    for _ in range(5):
        assert json.loads(_submit(client, agent_id="codex").data)["agent_id"] == "codex"


@pytest.mark.parametrize("aid, archived, needle", [
    ("ghost", False, "not an installed agent"),
    ("old", True, "uninstalled"),
])
def test_an_agent_that_cannot_take_work_is_refused(client, db_path, aid, archived, needle):
    if archived:
        _seed_agent(db_path, "old", archived_at="2026-02-01T00:00:00Z")
    r = _submit(client, agent_id=aid)
    assert r.status_code == 400
    assert needle in json.loads(r.data)["error"]


def test_a_model_outside_the_picked_agents_list_is_refused(client, db_path):
    _seed_agent(db_path, "claude")
    _seed_agent(db_path, "codex", models=("gpt-5",), is_default=0)
    r = _submit(client, agent_id="codex", agent_model="opus")
    assert r.status_code == 400
    assert "not one of agent 'codex'" in json.loads(r.data)["error"]


def test_a_model_is_checked_against_the_dealt_agent(client, db_path):
    _seed_agent(db_path, "claude")
    assert _submit(client, agent_model="sonnet").status_code == 201
    assert _submit(client, agent_model="gpt-5").status_code == 400


def test_a_rejected_model_returns_the_dealt_card(client, db_path):
    """Dealing writes the deck; a refused model must roll that back, or every
    bad submission would skew the weighted split."""
    _seed_agent(db_path, "claude", weight=1)
    _seed_agent(db_path, "codex", models=("gpt-5",), is_default=0, weight=1)
    before = _sql(db_path, "SELECT cards FROM agent_deck")
    assert _submit(client, agent_model="not-a-model").status_code == 400
    assert _sql(db_path, "SELECT cards FROM agent_deck") == before


# ── refusals ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("body, needle", [
    ({"title": None}, "title"),
    ({"title": "   "}, "title"),
    ({"title": 7}, "title"),
    ({"title": "x" * 71}, "at most 70"),
    ({"topic": None}, "topic"),
    ({"topic": "  "}, "topic"),
    ({"agent_effort": "turbo"}, "agent_effort"),
    ({"agent_model": "two words"}, "agent_model"),
    ({"agent_model": "--flag"}, "agent_model"),
    ({"visual_style": "cubist"}, "visual_style"),
    ({"visual_style": "illustrated"}, "OpenAI"),
    ({"voice_id": "nobody"}, "elevenlabs_voices"),
    ({"script_profile_id": "missing"}, "READY script profile"),
    ({"approve": "yes"}, "approve"),
    ({"voice_id": ["abc"]}, "voice_id must be a string"),
    ({"script_profile_id": {"id": 1}}, "script_profile_id must be a string"),
    ({"visual_style": ["auto"]}, "visual_style must be a string"),
    ({"agent_id": 5}, "agent_id must be a string"),
    # Falsy non-strings must be refused too, not read as "the default".
    ({"visual_style": False}, "visual_style must be a string"),
    ({"voice_id": 0}, "voice_id must be a string"),
    ({"script_profile_id": []}, "script_profile_id must be a string"),
    ({"agent_id": 0}, "agent_id must be a string"),
    ({"agent_model": False}, "agent_model must be a string"),
    ({"agent_effort": 0}, "agent_effort must be a string"),
])
def test_a_bad_field_is_refused_and_writes_nothing(client, db_path, body, needle):
    r = _submit(client, **body)
    assert r.status_code == 400, r.data
    assert needle in json.loads(r.data)["error"]
    assert _counts(db_path) == (0, 0)


def test_a_title_of_exactly_70_is_accepted(client):
    assert _submit(client, title="x" * 70).status_code == 201


def test_a_profile_still_building_is_refused(client, db_path):
    _seed_profile(db_path, status="GENERATING")
    r = _submit(client, script_profile_id="prof-1")
    assert r.status_code == 400
    assert _counts(db_path) == (0, 0)


def test_illustrated_is_accepted_with_a_key(client, db_path):
    _sql(db_path, "INSERT OR REPLACE INTO settings (key, value) VALUES ('openai_api_key', ?)",
         ("sk-test",))
    assert json.loads(_submit(client, visual_style="illustrated").data)["visual_style"] == \
        "illustrated"


def test_an_agent_refusal_writes_nothing(client, db_path):
    r = _submit(client, agent_id="ghost")
    assert r.status_code == 400
    assert _counts(db_path) == (0, 0)
