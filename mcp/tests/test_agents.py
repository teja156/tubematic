"""Tests for installed agents as seen from the MCP server (TMDEV-90).

Agents are written only by the host-side installer; the MCP server pins each
new video to one, checks a video's agent_model against that agent's model list,
and reports the live agents in get_pipeline_status. No MCP tool writes agents.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import inspect
import pathlib
import re
import json
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    with server._conn() as con:
        con.execute("INSERT INTO projects (id, name, created_at) VALUES ('proj_1', 'P', ?)",
                    (_now(),))
    return tmp_path / "test.db"


def _make_agent(aid="claude", models=("sonnet", "opus"), is_default=1, weight=1,
                archived_at=None, created_at="2026-01-01T00:00:00Z", raw_models=None):
    with server._conn() as con:
        con.execute(
            "INSERT INTO agents (id, name, binary, run_path, models, is_default, weight,"
            " archived_at, created_at, updated_at) VALUES (?, ?, ?, '/w', ?, ?, ?, ?, ?, ?)",
            (aid, aid.title(), f"/bin/{aid}",
             raw_models if raw_models is not None else json.dumps(list(models)),
             is_default, weight, archived_at, created_at, created_at))


def _create():
    return server.create_video(project_id="proj_1", topic="t", strategy="manual",
                               producibility_score=7)


def _agent_id_of(video_id):
    with server._conn() as con:
        return con.execute("SELECT agent_id FROM videos WHERE id = ?",
                           (video_id,)).fetchone()["agent_id"]


# ── Schema ──────────────────────────────────────────────────────────────────

def test_init_db_creates_the_agents_table_and_videos_agent_id(db):
    with server._conn() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(agents)")}
        vcols = {r["name"] for r in con.execute("PRAGMA table_info(videos)")}
    assert {"id", "models", "is_default", "weight", "archived_at"} <= cols
    assert "agent_id" in vcols


def test_the_tool_count_matches_the_docs():
    """The public docs state a tool count, and it is the canonical thing that
    silently goes stale — a tool is added, every test still passes, and the
    number is wrong until a person happens to notice.

    This started life as a TMDEV-90 guard hardcoding 38 ("agents add returned
    data only — no new tool"). A bare number there is a thing to bump blindly;
    comparing the two makes adding a tool fail until docs/developer/06-mcp-server.md is updated too,
    which is the only failure worth catching.
    """
    src = inspect.getsource(server)
    actual = src.count("\n@mcp.tool\n")

    docs = (pathlib.Path(__file__).resolve().parents[2]
            / "docs" / "developer" / "06-mcp-server.md").read_text()
    m = re.search(r"^## The (\d+) tools$", docs, re.M)
    assert m, "docs/developer/06-mcp-server.md no longer states a tool count"
    assert actual == int(m.group(1)), (
        f"mcp/server.py has {actual} tools but docs/developer/06-mcp-server.md says "
        f"{m.group(1)} — also check docs/user-guide/01-overview.md and docs/README.md, "
        "which repeat it")


# ── create_video ────────────────────────────────────────────────────────────

def test_create_video_returns_and_stores_the_picked_agent(db):
    _make_agent()
    out = _create()
    assert out["agent_id"] == "claude"
    assert _agent_id_of(out["video_id"]) == "claude"


def test_create_video_with_no_agent_installed_returns_none(db):
    out = _create()
    assert out["agent_id"] is None
    assert _agent_id_of(out["video_id"]) is None


def test_create_video_never_pins_an_archived_agent(db):
    _make_agent("old", weight=100, is_default=0, archived_at="2026-01-02T00:00:00Z")
    _make_agent("claude")
    assert {_create()["agent_id"] for _ in range(20)} == {"claude"}


# ── update_video(agent_model=...) membership ────────────────────────────────

@pytest.mark.parametrize("model", ["sonnet", "opus", ""])
def test_a_model_in_the_agents_list_is_accepted(db, model):
    _make_agent()
    vid = _create()["video_id"]
    out = server.update_video(vid, agent_model=model)
    assert "error" not in out
    assert server.get_video(vid)["agent_model"] == model


def test_a_model_not_in_the_agents_list_is_rejected(db):
    _make_agent()
    vid = _create()["video_id"]
    err = server.update_video(vid, agent_model="haiku")["error"]
    assert "'claude'" in err and "sonnet" in err and "opus" in err
    assert server.get_video(vid)["agent_model"] == ""


def test_membership_is_checked_against_the_videos_own_agent(db):
    _make_agent("claude", is_default=1)
    vid = _create()["video_id"]
    _make_agent("codex", models=("gpt-5",), is_default=0, created_at="2026-01-02T00:00:00Z")
    assert "error" in server.update_video(vid, agent_model="gpt-5")


def test_an_archived_agent_rejects_a_model(db):
    _make_agent()
    vid = _create()["video_id"]
    with server._conn() as con:
        con.execute("UPDATE agents SET archived_at = ?, is_default = 0", (_now(),))
    assert "uninstalled" in server.update_video(vid, agent_model="opus")["error"]
    assert "error" not in server.update_video(vid, agent_model="")


def test_no_agent_installed_points_at_the_installer(db):
    vid = _create()["video_id"]
    err = server.update_video(vid, agent_model="opus")["error"]
    assert "python onboard.py --install-agent <agent>" in err
    assert "error" not in server.update_video(vid, agent_model="")


def test_a_corrupt_model_list_rejects_every_model(db):
    _make_agent(raw_models="{not json")
    vid = _create()["video_id"]
    assert "no usable model list" in server.update_video(vid, agent_model="opus")["error"]


def test_the_freeze_still_wins_over_membership(db):
    """A late edit must read as 'frozen', not as a model problem."""
    vid = _create()["video_id"]  # no agent installed
    _status(vid, "VOICE_READY")
    assert "human checkpoint" in server.update_video(vid, agent_model="opus")["error"]


# ── update_video(agent_id=...) — TMDEV-110 ──────────────────────────────────

def _status(video_id, status, **cols):
    cols["status"] = status
    with server._conn() as con:
        con.execute(f"UPDATE videos SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?",
                    list(cols.values()) + [video_id])


def _two_agents():
    """claude is dealt every card; codex (weight 0) only ever gets a video
    by being picked."""
    _make_agent("claude")
    _make_agent("codex", models=("gpt-5", "gpt-5-mini"), is_default=0, weight=0,
                created_at="2026-01-02T00:00:00Z")
    return _create()["video_id"]


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"])
def test_the_agent_can_be_changed_at_every_human_checkpoint(db, status):
    vid = _two_agents()
    _status(vid, status)
    out = server.update_video(vid, agent_id="codex")
    assert "error" not in out, out
    assert _agent_id_of(vid) == "codex"


@pytest.mark.parametrize("status", ["TOPIC_APPROVED", "VOICING", "VOICE_READY",
                                    "REVISION_REQUESTED", "VIDEO_APPROVED"])
@pytest.mark.parametrize("field,value", [("agent_id", "codex"),
                                         ("agent_model", "sonnet"),
                                         ("agent_effort", "max")])
def test_the_agent_group_is_frozen_outside_a_checkpoint(db, status, field, value):
    vid = _two_agents()
    _status(vid, status)
    err = server.update_video(vid, **{field: value})["error"]
    assert field in err and "human checkpoint" in err and status in err
    v = server.get_video(vid)
    assert (v["agent_id"], v["agent_model"], v["agent_effort"]) == ("claude", "", "")


@pytest.mark.parametrize("value", ["", "   "])
def test_the_agent_must_be_named(db, value):
    vid = _two_agents()
    assert "agent_id" in server.update_video(vid, agent_id=value)["error"]
    assert _agent_id_of(vid) == "claude"


def test_an_unknown_agent_is_rejected(db):
    vid = _two_agents()
    assert "'gemini'" in server.update_video(vid, agent_id="gemini")["error"]
    assert _agent_id_of(vid) == "claude"


def test_an_uninstalled_agent_is_never_offered(db):
    vid = _two_agents()
    with server._conn() as con:
        con.execute("UPDATE agents SET archived_at = '2026-01-03T00:00:00Z' WHERE id = 'codex'")
    assert "'codex'" in server.update_video(vid, agent_id="codex")["error"]
    assert _agent_id_of(vid) == "claude"


def test_echoing_the_videos_own_agent_is_a_no_op_even_when_uninstalled(db):
    vid = _two_agents()
    _status(vid, "TOPIC_PROPOSED", agent_model="opus")
    with server._conn() as con:
        con.execute("UPDATE agents SET archived_at = '2026-01-03T00:00:00Z' WHERE id = 'claude'")
    assert "error" not in server.update_video(vid, agent_id="claude")
    assert (_agent_id_of(vid), server.get_video(vid)["agent_model"]) == ("claude", "opus")


def test_changing_the_agent_clears_the_model(db):
    vid = _two_agents()
    _status(vid, "SCRIPT_READY", agent_model="opus")
    assert "error" not in server.update_video(vid, agent_id="codex")
    assert server.get_video(vid)["agent_model"] == ""


def test_pinning_the_default_agent_explicitly_keeps_the_model(db):
    vid = _two_agents()
    _status(vid, "TOPIC_PROPOSED", agent_id=None, agent_model="opus")
    assert "error" not in server.update_video(vid, agent_id="claude")
    assert (_agent_id_of(vid), server.get_video(vid)["agent_model"]) == ("claude", "opus")


def test_a_model_sent_with_the_change_is_checked_against_the_new_agent(db):
    vid = _two_agents()
    assert "'codex'" in server.update_video(vid, agent_id="codex", agent_model="opus")["error"]
    assert _agent_id_of(vid) == "claude"
    assert "error" not in server.update_video(vid, agent_id="codex", agent_model="gpt-5-mini")
    assert (_agent_id_of(vid), server.get_video(vid)["agent_model"]) == ("codex", "gpt-5-mini")


def test_the_effort_survives_an_agent_change(db):
    vid = _two_agents()
    _status(vid, "TOPIC_PROPOSED", agent_effort="max")
    assert "error" not in server.update_video(vid, agent_id="codex")
    assert server.get_video(vid)["agent_effort"] == "max"


def test_a_model_write_racing_an_agent_change_is_refused(db, monkeypatch):
    """The model is checked against claude; if codex lands before the UPDATE,
    writing it would pin a model codex does not have."""
    vid = _two_agents()
    real = server._agent_model_error

    def _check_then_race(con, agent_id, model):
        err = real(con, agent_id, model)
        with server._conn() as side:
            side.execute("UPDATE videos SET agent_id = 'codex' WHERE id = ?", (vid,))
        return err

    monkeypatch.setattr(server, "_agent_model_error", _check_then_race)
    assert "agent changed" in server.update_video(vid, agent_model="opus")["error"]
    assert (_agent_id_of(vid), server.get_video(vid)["agent_model"]) == ("codex", "")


# ── get_pipeline_status ─────────────────────────────────────────────────────

def test_pipeline_status_lists_live_agents_only(db):
    _make_agent("claude", models=("sonnet", "opus"), is_default=1, weight=3)
    _make_agent("old", is_default=0, archived_at="2026-01-02T00:00:00Z",
                created_at="2026-01-02T00:00:00Z")
    agents = server.get_pipeline_status()["agents"]
    assert agents == [{"id": "claude", "name": "Claude", "models": ["sonnet", "opus"],
                       "effort": "high", "is_default": True, "weight": 3}]


def test_pipeline_status_agents_is_empty_with_none_installed(db):
    assert server.get_pipeline_status()["agents"] == []


def test_pipeline_status_agents_carry_their_effort(db):
    """The slash command tells the agent to mark its agent's own effort as the
    default when offering the five levels. It can only do that if this payload
    says what that level is — it is not derivable from anything else here, and
    an instruction written against a field the tool does not return is an
    instruction that silently cannot be followed.
    """
    _make_agent("claude")
    with server._conn() as con:
        con.execute("UPDATE agents SET effort = 'max' WHERE id = 'claude'")
    assert server.get_pipeline_status()["agents"][0]["effort"] == "max"


# ── update_video(agent_effort=...) — TMDEV-106 ──────────────────────────────

@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max", ""])
def test_every_documented_effort_and_blank_is_accepted(db, effort):
    _make_agent()
    vid = _create()["video_id"]
    out = server.update_video(vid, agent_effort=effort)
    assert "error" not in out
    assert server.get_video(vid)["agent_effort"] == effort


@pytest.mark.parametrize("effort", ["HIGH", "extreme", "--effort", "two words"])
def test_an_unknown_effort_is_rejected(db, effort):
    _make_agent()
    vid = _create()["video_id"]
    err = server.update_video(vid, agent_effort=effort)["error"]
    assert "agent_effort" in err
    assert server.get_video(vid)["agent_effort"] == ""


def test_the_effort_is_stripped(db):
    _make_agent()
    vid = _create()["video_id"]
    assert "error" not in server.update_video(vid, agent_effort="  max  ")
    assert server.get_video(vid)["agent_effort"] == "max"


def test_the_effort_needs_no_installed_agent(db):
    """Unlike agent_model, which is checked against that agent's own list —
    the five levels are the same for every agent, so there is nothing to look
    up, and a video with no agent yet must not lose the human's pick."""
    vid = _create()["video_id"]
    assert "error" not in server.update_video(vid, agent_effort="max")


def test_the_effort_is_frozen_between_checkpoints(db):
    _make_agent()
    vid = _create()["video_id"]
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'VOICE_READY' WHERE id = ?", (vid,))
    err = server.update_video(vid, agent_effort="max")["error"]
    assert "human checkpoint" in err and "agent_effort" in err
    assert server.get_video(vid)["agent_effort"] == ""


def test_the_effort_can_be_set_in_the_same_call_that_approves_the_topic(db):
    """The guard reads the CURRENT status, so /tubematic-submit-new-job's
    update_video → set_video_status pair still works."""
    _make_agent()
    vid = _create()["video_id"]
    out = server.update_video(vid, agent_model="opus", agent_effort="max",
                              script_profile_id="")
    assert "error" not in out
    assert set(out["updated_fields"]) >= {"agent_model", "agent_effort"}


def test_a_new_video_starts_on_its_agents_effort(db):
    """'' is the value that means "follow your agent"."""
    _make_agent()
    assert server.get_video(_create()["video_id"])["agent_effort"] == ""



@pytest.mark.parametrize("field,value", [("agent_id", "codex"), ("agent_effort", "max")])
def test_an_agent_pick_is_refused_if_the_video_moves_on_mid_call(db, monkeypatch, field, value):
    """The checkpoint is read on one connection and written on another; a
    status change in between must not let the pick land on a video an agent
    is already working on. _now() is stamped after validation and before the
    UPDATE, so advancing the video there lands exactly in that window."""
    vid = _two_agents()
    _status(vid, "SCRIPT_READY")
    real_now = server._now

    def _advance_then_now():
        with server._conn() as side:
            side.execute("UPDATE videos SET status = 'VOICING' WHERE id = ?", (vid,))
        return real_now()

    monkeypatch.setattr(server, "_now", _advance_then_now)
    err = server.update_video(vid, **{field: value})["error"]
    assert "VOICING" in err and "SCRIPT_READY" in err
    v = server.get_video(vid)
    assert (v["agent_id"], v["agent_effort"]) == ("claude", "")
