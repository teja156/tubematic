"""poll.py's /videos/workable path, exercised through the real functions.

An earlier version of these tests reimplemented the grouping rule in the test
file and asserted against the copy. That cannot fail the way the code fails —
and it did not: `_fetch_workable_videos` referenced `urllib` and `json` without
importing either, raised NameError into its own `except Exception`, and
silently returned [] on every call. These tests drive the real functions.

Since TMDEV-129 every workable video gets a session of its own, under its own
agent, model and effort; there is no batch and no unscoped fallback.
"""
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import poll


def _resp(payload):
    body = json.dumps(payload).encode()

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return _R(body)


# ── _fetch_workable_videos ──────────────────────────────────────────────────

def test_fetch_returns_the_parsed_payload():
    """The regression guard: this went through `except Exception` as a
    NameError and returned [] for every caller."""
    rows = [{"id": "vid_a", "agent_model": "opus", "status": "VOICE_READY"}]
    with patch("urllib.request.urlopen", return_value=_resp(rows)):
        assert poll._fetch_workable_videos() == rows


def test_fetch_requests_the_workable_endpoint():
    seen = {}

    def _urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _resp([])

    with patch("urllib.request.urlopen", _urlopen):
        poll._fetch_workable_videos()
    assert seen["url"].endswith("/videos/workable")


def test_fetch_reports_a_transport_error_as_none(caplog):
    """None, not [] — an outage must not read as "no work", and it must be
    reached by a real failure, not by a NameError in the happy path."""
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        assert poll._fetch_workable_videos() is None
    assert "Could not fetch workable videos" in caplog.text


def test_fetch_reports_malformed_json_as_none():
    class _Bad(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    with patch("urllib.request.urlopen", return_value=_Bad(b"not json")):
        assert poll._fetch_workable_videos() is None
    with patch("urllib.request.urlopen", return_value=_resp({"not": "a list"})):
        assert poll._fetch_workable_videos() is None


CLAUDE = {"id": "claude", "binary": "claude", "run_path": "/tmp/ws",
          "models": ["sonnet", "opus", "haiku"], "effort": "high",
          "is_default": True, "archived_at": None}
OTHER = {"id": "other", "binary": "other", "run_path": "/tmp/ws2",
         "models": ["m1"], "effort": "low", "is_default": False, "archived_at": None}


@pytest.fixture
def poll_run(tmp_path, monkeypatch):
    """Drive main() with stubbed HTTP, capturing what invoke_agent receives.

    The stub API behaves like the real one: a video whose session ran is no
    longer workable, so the supervisor runs out of work and exits.
    """
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll, "_record_research_run", lambda dry_run=False: False)
    monkeypatch.setattr(poll, "_fetch_settings", lambda: {})
    monkeypatch.setattr(poll, "LOCKFILE", tmp_path / "poll.lock")
    monkeypatch.setattr(poll, "_post_outcome",
                        lambda vid, st, key="": {"status": "NEXT", "count": 0, "stuck": False})
    calls = []
    usage_tags = []
    done = set()

    def fake_invoke(prompt, agent, dry_run=False, model="", effort="",
                    operation="agent_pipeline", attribution=()):
        calls.append((prompt, agent["id"], model, effort))
        usage_tags.append((operation, list(attribution)))
        done.update(a["video_id"] for a in attribution)
    monkeypatch.setattr(poll, "invoke_agent", fake_invoke)

    def run(videos, *, workable=2, agents=(CLAUDE,), fetch_fails=False):
        monkeypatch.setattr(poll, "_fetch_pipeline_status", lambda: {
            "paused": False, "proposed_count": 99, "workable_count": workable,
            "research_runs_today": 0, "max_research_runs_per_day": 5,
            "research_pending_cap": 8, "active_strategies": [],
        })
        monkeypatch.setattr(poll, "_fetch_agents",
                            lambda: None if agents is None else list(agents))
        monkeypatch.setattr(poll, "_fetch_workable_videos",
                            lambda: None if fetch_fails else
                            [v for v in videos if v["id"] not in done])
        monkeypatch.setattr(sys, "argv", ["poll.py"])
        calls.clear()
        usage_tags.clear()
        done.clear()
        run.usage_tags = usage_tags
        try:
            poll.main()
        except SystemExit as e:
            run.exit_code = e.code
        else:
            run.exit_code = None
        return sorted(calls, key=lambda c: c[0])

    return run


def _scoped_to(prompt):
    return prompt.split("scoped to video ", 1)[1].split(",", 1)[0]


def test_each_video_gets_its_own_session_under_its_own_model(poll_run):
    calls = poll_run([
        {"id": "a", "agent_model": "opus", "status": "VOICE_READY"},
        {"id": "b", "agent_model": "haiku", "status": "TOPIC_APPROVED"},
        {"id": "c", "agent_model": "opus", "status": "VOICING"},
    ])
    assert {(_scoped_to(p), a, m, e) for p, a, m, e in calls} == {
        ("a", "claude", "opus", "high"), ("b", "claude", "haiku", "high"),
        ("c", "claude", "opus", "high")}


def test_a_blank_per_video_model_uses_the_agents_default_model(poll_run):
    """The agent's default model is models[0] — validated at install."""
    calls = poll_run([{"id": "a", "agent_model": "", "status": "VOICE_READY"}])
    assert calls[0][2] == "sonnet"


def test_an_unreachable_endpoint_starts_no_session(poll_run, caplog):
    """No unscoped fallback: a session told to work "every workable video"
    would cross agent boundaries, since the poller cannot know whose they are."""
    calls = poll_run([], workable=4, fetch_fails=True)
    assert calls == []
    assert poll_run.usage_tags == []


# ── Per-video agents (TMDEV-90) ─────────────────────────────────────────────

def test_each_video_runs_under_its_own_agent(poll_run):
    calls = poll_run([
        {"id": "a", "agent_id": "other", "agent_model": "", "status": "VOICE_READY"},
        {"id": "b", "agent_id": "claude", "agent_model": "", "status": "VOICE_READY"},
    ], agents=(CLAUDE, OTHER))
    assert {(_scoped_to(p), a, m) for p, a, m, _ in calls} == {
        ("a", "other", "m1"), ("b", "claude", "sonnet")}


def test_a_video_with_no_agent_id_runs_on_the_default_agent(poll_run):
    other_default = {**OTHER, "is_default": True}
    calls = poll_run([{"id": "a", "agent_model": "", "status": "VOICE_READY"}],
                     agents=({**CLAUDE, "is_default": False}, other_default))
    assert calls[0][1:] == ("other", "m1", "low")


def test_a_video_pinned_to_an_archived_agent_is_skipped_loudly(poll_run, caplog):
    """Pinned for life: never silently rerouted to another agent."""
    archived = {**OTHER, "archived_at": "2026-09-10T00:00:00Z"}
    calls = poll_run([{"id": "a", "agent_id": "other", "agent_model": "",
                       "status": "VOICE_READY"},
                      {"id": "b", "agent_id": "claude", "agent_model": "",
                       "status": "VOICE_READY"}],
                     agents=(CLAUDE, archived))
    assert [(_scoped_to(p), a) for p, a, _, _ in calls] == [("b", "claude")]
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("Video a is assigned to agent 'other', which is uninstalled" in m for m in errors)
    assert any("--install-agent other" in m for m in errors)


def test_a_video_pinned_to_an_unknown_agent_is_skipped_loudly(poll_run, caplog):
    calls = poll_run([{"id": "a", "agent_id": "ghost", "agent_model": "",
                       "status": "VOICE_READY"}])
    assert calls == []
    assert "which is not installed" in caplog.text


def test_no_agent_installed_logs_and_exits_without_invoking(poll_run, caplog):
    calls = poll_run([{"id": "a", "agent_model": "", "status": "VOICE_READY"}], agents=())
    assert calls == []
    assert poll_run.exit_code is None
    assert "No agent installed" in caplog.text
    assert "--install-agent <agent>" in caplog.text


def test_only_archived_agents_counts_as_none_installed(poll_run, caplog):
    calls = poll_run([{"id": "a", "agent_model": "", "status": "VOICE_READY"}],
                     agents=({**CLAUDE, "archived_at": "2026-09-10T00:00:00Z"},))
    assert calls == []
    assert "No agent installed" in caplog.text


def test_an_unreachable_agents_endpoint_exits_1(poll_run, caplog):
    """An outage is not "nothing installed" — it must not be logged as one."""
    calls = poll_run([{"id": "a", "agent_model": "", "status": "VOICE_READY"}], agents=None)
    assert calls == []
    assert poll_run.exit_code == 1
    assert "No agent installed" not in caplog.text


# ── _fetch_agents ───────────────────────────────────────────────────────────

def test_fetch_agents_returns_the_list():
    with patch("urllib.request.urlopen", return_value=_resp([CLAUDE])):
        assert poll._fetch_agents() == [CLAUDE]


def test_fetch_agents_distinguishes_an_outage_from_an_empty_list():
    with patch("urllib.request.urlopen", return_value=_resp([])):
        assert poll._fetch_agents() == []
    with patch("urllib.request.urlopen", side_effect=OSError("refused")):
        assert poll._fetch_agents() is None
    with patch("urllib.request.urlopen", return_value=_resp({"not": "a list"})):
        assert poll._fetch_agents() is None


# ── Per-video effort (TMDEV-106) ────────────────────────────────────────────

def test_each_video_runs_at_its_own_effort(poll_run):
    """One session runs at one effort, and now one session is one video, so
    no video can run at another's level."""
    calls = poll_run([
        {"id": "a", "agent_model": "opus", "agent_effort": "max", "status": "VOICE_READY"},
        {"id": "b", "agent_model": "opus", "agent_effort": "low", "status": "VOICE_READY"},
    ])
    assert {(_scoped_to(p), e) for p, _, _, e in calls} == {("a", "max"), ("b", "low")}


def test_a_blank_per_video_effort_uses_the_agents_default(poll_run):
    """'' means "follow your agent", exactly as a blank agent_model does."""
    calls = poll_run([{"id": "a", "agent_model": "opus", "agent_effort": "",
                       "status": "VOICE_READY"}])
    assert calls[0][3] == "high"


def test_a_row_with_no_effort_column_still_runs(poll_run):
    """An agents row read from a database that predates the column."""
    calls = poll_run([{"id": "a", "agent_model": "opus", "status": "VOICE_READY"}],
                     agents=({k: v for k, v in CLAUDE.items() if k != "effort"},))
    assert len(calls) == 1
    assert calls[0][3] == ""


def test_each_session_is_tagged_with_its_one_videos_stage(poll_run):
    """The session's usage is recorded against its one video, with the status
    it started at as the stage — exact now, where a batch was split ÷N and
    labelled with each video's starting status (TMDEV-107)."""
    poll_run([{"id": "a", "agent_model": "opus", "status": "TOPIC_APPROVED"},
              {"id": "b", "agent_model": "haiku", "status": "VOICE_READY"}])
    assert sorted(poll_run.usage_tags, key=lambda t: t[1][0]["video_id"]) == [
        ("agent_pipeline", [{"video_id": "a", "stage": "TOPIC_APPROVED"}]),
        ("agent_pipeline", [{"video_id": "b", "stage": "VOICE_READY"}])]
