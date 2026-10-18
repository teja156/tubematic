"""Unit tests for poll.py main() -- the lanes a supervisor dispatches into.

First written for TMDEV-44's single-cron decision tree (the two-gate research
cap). Since TMDEV-129 main() runs a looping supervisor with three lanes —
pipeline, research and script profiles — and these tests pin what each lane
starts and when. The loop's own mechanics are in test_poll_supervisor.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import call, patch

import pytest

import poll


@pytest.fixture(autouse=True)
def _isolated_lockfile(tmp_path, monkeypatch):
    """Point the poll lockfile at a scratch path so tests never contend with
    (or leave state behind for) a real cron-invoked poll on this machine."""
    monkeypatch.setattr(poll, "LOCKFILE", tmp_path / "poll.lock")
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll, "_fetch_agents", lambda: [AGENT])
    # Never reach a real API from a unit test; a test that cares overrides it.
    monkeypatch.setattr(poll, "_fetch_settings", lambda: {})
    monkeypatch.setattr(poll, "_post_outcome",
                        lambda vid, st, key="": {"status": "NEXT", "count": 0, "stuck": False})
    # One workable video, gone once its session has run — like the real API.
    served = []

    def workable():
        if served:
            return []
        served.append(1)
        return [{"id": "vid_1", "status": "VOICE_READY", "agent_model": ""}]
    monkeypatch.setattr(poll, "_fetch_workable_videos", workable)
    monkeypatch.setattr(poll.sys, "argv", ["poll.py"])


AGENT = {"id": "claude", "binary": "claude", "run_path": "/tmp/ws",
         "models": ["opus"], "is_default": True, "archived_at": None}


def _status(**overrides) -> dict:
    base = {
        "paused": False,
        "proposed_count": 0,
        "workable_count": 0,
        "research_runs_today": 0,
        "max_research_runs_per_day": 5,
        "research_pending_cap": 8,
        "active_strategies": ["curriculum", "trending", "mining"],
    }
    base.update(overrides)
    return base


def test_paused_starts_nothing():
    with patch("poll._fetch_pipeline_status",
               return_value=_status(paused=True, workable_count=1)), \
         patch("poll.invoke_agent") as invoke, \
         patch("poll._record_research_run") as record:
        poll.main()
    invoke.assert_not_called()
    record.assert_not_called()


def test_unreachable_api_exits_1():
    with patch("poll._fetch_pipeline_status", return_value={}), \
         patch("poll.invoke_agent") as invoke:
        with pytest.raises(SystemExit) as exc:
            poll.main()
    assert exc.value.code == 1
    invoke.assert_not_called()


def test_workable_only_invokes_pipeline_prompt_research_blocked_by_pending_cap():
    status = _status(workable_count=1, proposed_count=8, research_pending_cap=8)
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll.invoke_agent") as invoke, \
         patch("poll._record_research_run") as record:
        poll.main()
    record.assert_not_called()
    assert invoke.call_count == 1
    prompt = invoke.call_args[0][0]
    assert "TUBEMATIC POLL" in prompt


def test_research_allowed_records_run_before_invoking():
    status = _status(proposed_count=0, research_runs_today=1, max_research_runs_per_day=5)
    calls = []
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll.invoke_agent", side_effect=lambda *a, **k: calls.append("invoke")) as invoke, \
         patch("poll._record_research_run", side_effect=lambda **k: calls.append("record") or True) as record:
        poll.main()
    record.assert_called_once()
    assert invoke.call_count == 1
    prompt = invoke.call_args[0][0]
    assert "TUBEMATIC RESEARCH" in prompt
    assert calls == ["record", "invoke"]


def test_blocked_by_pending_cap_skips_research():
    status = _status(proposed_count=8, research_pending_cap=8, research_runs_today=0)
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll.invoke_agent") as invoke, \
         patch("poll._record_research_run") as record:
        poll.main()
    record.assert_not_called()
    invoke.assert_not_called()


def test_blocked_by_run_cap_skips_research():
    status = _status(proposed_count=0, research_runs_today=5, max_research_runs_per_day=5)
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll.invoke_agent") as invoke, \
         patch("poll._record_research_run") as record:
        poll.main()
    record.assert_not_called()
    invoke.assert_not_called()


def test_both_gates_blocked_nothing_invoked():
    status = _status(
        workable_count=0, proposed_count=8, research_pending_cap=8,
        research_runs_today=5, max_research_runs_per_day=5,
    )
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll.invoke_agent") as invoke, \
         patch("poll._record_research_run") as record:
        poll.main()
    record.assert_not_called()
    invoke.assert_not_called()


def test_record_run_failure_skips_research_but_workable_pass_still_runs():
    status = _status(workable_count=2, proposed_count=0, research_runs_today=0)
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll.invoke_agent") as invoke, \
         patch("poll._record_research_run", return_value=False) as record:
        poll.main()
    record.assert_called_once()
    # Only the pipeline prompt fires -- research is skipped since record-run
    # failed (fail-closed), but the earlier workable-video pass is unaffected.
    assert invoke.call_count == 1
    prompt = invoke.call_args[0][0]
    assert "TUBEMATIC POLL" in prompt


def test_already_running_exits_0_without_fetching_status():
    lockfile = poll.LOCKFILE
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    held_fh = open(lockfile, "w")
    try:
        import fcntl
        fcntl.flock(held_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch("poll._fetch_pipeline_status") as fetch:
            with pytest.raises(SystemExit) as exc:
                poll.main()
        assert exc.value.code == 0
        fetch.assert_not_called()
    finally:
        held_fh.close()


# ── Script profiles (TMDEV-81) ───────────────────────────────────────────────

def _profile(pid="prof-1", name="Corpus A") -> dict:
    return {"id": pid, "name": name, "status": "PENDING"}


def _once(rows):
    """A pending-profiles stub: the rows once, then nothing — the supervisor
    asks again on every pass until it runs out of work."""
    served = []

    def fetch():
        if served:
            return []
        served.append(1)
        return rows
    return fetch


def test_a_pending_profile_runs_beside_the_pipeline_and_research():
    """Its own lane, outside the session cap: a long transcript-analysis
    session no longer holds up a whole tick (TMDEV-129)."""
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=1, workable_count=1,
                                    proposed_count=0)), \
         patch("poll._fetch_pending_script_profiles", side_effect=_once([_profile()])), \
         patch("poll._record_profile_attempt", return_value="GENERATING") as record, \
         patch("poll._record_research_run", return_value=True), \
         patch("poll._fetch_mining_urls", return_value=[]), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    record.assert_called_once_with("prof-1", dry_run=False)
    heads = sorted(c.args[0].split(" —")[0] for c in invoke.call_args_list)
    assert heads == ["[TUBEMATIC POLL", "[TUBEMATIC RESEARCH", "[TUBEMATIC SCRIPT PROFILE"]


def test_a_profile_is_built_even_while_the_pipeline_is_paused():
    """Building a profile spends no ElevenLabs credit and produces no video, so
    the pause guard must not reach it — otherwise a dashboard row sits at
    PENDING with nothing saying why."""
    with patch("poll._fetch_pipeline_status",
               return_value=_status(paused=True, pending_script_profiles=1)), \
         patch("poll._fetch_pending_script_profiles", side_effect=_once([_profile()])), \
         patch("poll._record_profile_attempt", return_value="GENERATING"), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    assert invoke.call_count == 1
    assert "TUBEMATIC SCRIPT PROFILE" in invoke.call_args[0][0]


def test_an_unrecordable_attempt_skips_the_profile_and_the_pass_continues():
    """Fail closed, like research: no agent session runs without its attempt
    counted, or a crashing agent re-fires forever."""
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=1, workable_count=1)), \
         patch("poll._fetch_pending_script_profiles", return_value=[_profile()]), \
         patch("poll._record_profile_attempt", return_value=""), \
         patch("poll._record_research_run", return_value=False), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    assert invoke.call_count == 1
    assert "TUBEMATIC POLL" in invoke.call_args[0][0]


def test_a_capped_out_profile_is_skipped_and_the_next_one_is_tried():
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=2)), \
         patch("poll._fetch_pending_script_profiles",
               side_effect=_once([_profile("p-dead"), _profile("p-live")])), \
         patch("poll._record_profile_attempt",
               side_effect=["FAILED", "GENERATING"]), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    assert invoke.call_count == 1
    assert "p-live" in invoke.call_args[0][0]


def test_no_pending_profiles_leaves_the_normal_flow_untouched():
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=0, workable_count=1)), \
         patch("poll._fetch_pending_script_profiles") as fetch, \
         patch("poll._record_research_run", return_value=False), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    fetch.assert_not_called()
    assert "TUBEMATIC POLL" in invoke.call_args[0][0]


def test_dry_run_records_no_attempt_and_invokes_nothing():
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=1, workable_count=1)), \
         patch("poll._fetch_pending_script_profiles", return_value=[_profile()]), \
         patch("sys.argv", ["poll.py", "--dry-run"]), \
         patch("urllib.request.urlopen") as urlopen, \
         patch("subprocess.Popen") as popen, \
         patch("subprocess.run") as run:
        poll.main()
    run.assert_not_called()
    popen.assert_not_called()
    # No POST went out: the only urlopen calls a dry run can make are the GETs
    # that fetch state, never the attempt record.
    assert not any(getattr(c.args[0], "method", None) == "POST"
                   for c in urlopen.call_args_list if c.args)


def test_profile_and_research_runs_use_the_default_agent_and_its_default_model():
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=1)), \
         patch("poll._fetch_pending_script_profiles", side_effect=_once([_profile()])), \
         patch("poll._record_profile_attempt", return_value="GENERATING"), \
         patch("poll._record_research_run", return_value=True), \
         patch("poll._fetch_mining_urls", return_value=[]), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    assert invoke.call_count == 2
    for c in invoke.call_args_list:
        assert c.args[1] is AGENT
        assert c.kwargs["model"] == "opus"


def test_no_agent_installed_stops_before_profiles_and_research(monkeypatch):
    """A script profile or a research run needs an agent as much as a video."""
    monkeypatch.setattr(poll, "_fetch_agents", lambda: [])
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=1, workable_count=1)), \
         patch("poll._record_profile_attempt") as profile, \
         patch("poll._record_research_run") as research, \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    profile.assert_not_called()
    research.assert_not_called()
    invoke.assert_not_called()


def test_the_profile_prompt_carries_only_the_id_never_the_corpus():
    prompt = poll.build_script_profile_prompt("prof-1", "Corpus A")
    assert "prof-1" in prompt
    assert "get_script_profile_transcripts" in prompt
    assert "complete_script_profile" in prompt
    assert "tubematic-create-script-writing-skill" in prompt


# ── User preferences (TMDEV-117) ─────────────────────────────────────────────

PREFS = "Scripts: calm tone, no jokes."


def test_the_pipeline_and_research_prompts_both_carry_the_preferences(monkeypatch):
    fetches = []
    monkeypatch.setattr(poll, "_fetch_settings",
                        lambda: fetches.append(1) or {"user_preferences": PREFS})
    status = _status(workable_count=1, proposed_count=0)
    with patch("poll._fetch_pipeline_status", return_value=status), \
         patch("poll._record_research_run", return_value=True), \
         patch("poll._fetch_mining_urls", return_value=[]), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    prompts = [c.args[0] for c in invoke.call_args_list]
    assert sorted(p.split("\n")[0].split(" —")[0] for p in prompts) == \
        ["[TUBEMATIC POLL", "[TUBEMATIC RESEARCH"]
    assert all(PREFS in p for p in prompts)


def test_the_profile_prompt_carries_the_preferences(monkeypatch):
    monkeypatch.setattr(poll, "_fetch_settings", lambda: {"user_preferences": PREFS})
    with patch("poll._fetch_pipeline_status",
               return_value=_status(pending_script_profiles=1, proposed_count=8,
                                    research_pending_cap=8)), \
         patch("poll._fetch_pending_script_profiles", side_effect=_once([_profile()])), \
         patch("poll._record_profile_attempt", return_value="GENERATING"), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    assert PREFS in invoke.call_args[0][0]


def test_an_idle_pass_never_reads_the_settings(monkeypatch):
    """Nothing to start means no settings or preferences read: an idle cron
    tick stays a status request and an agents request."""
    fetches = []
    monkeypatch.setattr(poll, "_fetch_settings", lambda: fetches.append(1) or {})
    with patch("poll._fetch_pipeline_status",
               return_value=_status(proposed_count=8, research_pending_cap=8)), \
         patch("poll.invoke_agent") as invoke:
        poll.main()
    invoke.assert_not_called()
    assert fetches == []
