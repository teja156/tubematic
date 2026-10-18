"""poll.py's looping supervisor (TMDEV-129): slots, lanes, the no-progress
verdict, the scene-claim cooldown, session timeouts, and orphan adoption.

The supervisor replaced one-session-per-cron-tick. Its failure modes are all
about time and concurrency — a video dispatched twice, a hung session holding
a slot forever, a dead supervisor's session run a second time on top of
itself — so several tests here run real processes and real threads rather
than mocks: a mocked Popen cannot show that a killpg reached a grandchild.
"""
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

import pytest

import poll

AGENT = {"id": "claude", "binary": "claude", "run_path": "/tmp/ws", "models": ["opus"],
         "effort": "high", "is_default": True, "archived_at": None}


def _status(**overrides) -> dict:
    base = {"paused": False, "proposed_count": 99, "workable_count": 1,
            "research_runs_today": 0, "max_research_runs_per_day": 5,
            "research_pending_cap": 8, "active_strategies": ["curriculum"]}
    base.update(overrides)
    return base


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A stub API whose state tests can change while the supervisor runs."""
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll, "LOCKFILE", tmp_path / "poll.lock")
    monkeypatch.setattr(poll, "LOOP_WAIT_SECS", 0.05)
    monkeypatch.setattr(poll.sys, "argv", ["poll.py"])
    state = {"status": _status(), "settings": {}, "videos": [], "outcomes": [],
             "outcome": {"status": "NEXT", "count": 0, "stuck": False}, "passes": 0,
             "keys": []}

    def status():
        # A bound on every test: a regression that loops forever turns into an
        # unreachable API after a few hundred passes, which ends the supervisor
        # once it is idle — a failed assertion instead of a hung suite.
        state["passes"] += 1
        return {} if state["passes"] > 300 else dict(state["status"])
    monkeypatch.setattr(poll, "_fetch_pipeline_status", status)
    monkeypatch.setattr(poll, "_fetch_agents", lambda: [AGENT])
    monkeypatch.setattr(poll, "_fetch_settings", lambda: dict(state["settings"]))
    monkeypatch.setattr(poll, "_fetch_workable_videos", lambda: list(state["videos"]))
    monkeypatch.setattr(poll, "_record_research_run", lambda dry_run=False: True)
    monkeypatch.setattr(poll, "_fetch_mining_urls", lambda: [])

    def outcome(vid, start_status, session_key=""):
        state["outcomes"].append((vid, start_status))
        state["keys"].append(session_key)
        return dict(state["outcome"])
    monkeypatch.setattr(poll, "_post_outcome", outcome)
    return state


def _video(vid, status="VOICE_READY"):
    return {"id": vid, "status": status, "agent_model": "", "agent_effort": ""}


def _run_in_thread():
    t = threading.Thread(target=poll.main, daemon=True)
    t.start()
    return t


# ── Slots and lanes ─────────────────────────────────────────────────────────

def test_the_pipeline_lane_never_runs_more_than_the_cap(api, monkeypatch):
    api["settings"] = {"max_concurrent_agent_sessions": 2}
    api["status"] = _status(workable_count=5)
    api["videos"] = [_video(f"v{i}") for i in range(5)]
    lock = threading.Lock()
    live, peak, started = [0], [0], []

    def invoke(prompt, agent, **kw):
        vid = kw["attribution"][0]["video_id"]
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            started.append(vid)
        time.sleep(0.1)
        with lock:
            live[0] -= 1
            # Like the real API: a video whose session moved it is no longer workable.
            api["videos"] = [v for v in api["videos"] if v["id"] != vid]
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    poll.main()
    assert peak[0] == 2
    assert sorted(started) == [f"v{i}" for i in range(5)]


def test_the_oldest_video_is_dispatched_first(api, monkeypatch):
    api["settings"] = {"max_concurrent_agent_sessions": 1}
    api["videos"] = [_video("old"), _video("new")]
    started = []

    def invoke(prompt, agent, **kw):
        vid = kw["attribution"][0]["video_id"]
        started.append(vid)
        api["videos"] = [v for v in api["videos"] if v["id"] != vid]
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    poll.main()
    assert started == ["old", "new"]


def test_a_video_in_flight_is_never_dispatched_twice(api, monkeypatch):
    """The workable list still carries a video while its session runs —
    only the supervisor knows it is taken."""
    api["videos"] = [_video("v1")]
    release = threading.Event()
    calls = []

    def invoke(prompt, agent, **kw):
        calls.append(kw["attribution"][0]["video_id"])
        release.wait(5)
        api["videos"] = []
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    t = _run_in_thread()
    try:
        time.sleep(0.4)          # several passes while the session is running
        seen = list(calls)
    finally:
        release.set()
        api["videos"] = []
        t.join(10)
    assert seen == ["v1"]


def test_research_runs_beside_a_full_pipeline_lane_and_only_once(api, monkeypatch):
    """Outside the cap, and at most once per supervisor however many passes
    it makes — otherwise every finished session would start another research
    run until the daily cap was spent."""
    api["settings"] = {"max_concurrent_agent_sessions": 1}
    api["status"] = _status(proposed_count=0, workable_count=3)
    api["videos"] = [_video("a"), _video("b"), _video("c")]
    kinds = []

    def invoke(prompt, agent, **kw):
        kinds.append(kw["operation"])
        if kw["attribution"]:
            vid = kw["attribution"][0]["video_id"]
            api["videos"] = [v for v in api["videos"] if v["id"] != vid]
        time.sleep(0.05)
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    poll.main()
    assert kinds.count("agent_research") == 1
    assert kinds.count("agent_pipeline") == 3
    # Started in the first pass, beside the first pipeline session.
    assert "agent_research" in kinds[:2]


def test_no_active_strategy_skips_research_without_spending_a_run(api, monkeypatch):
    """The API leaves mining out while no Gemini key is stored (TMDEV-165), so
    an install whose only strategy was mining reports none. No session, and no
    recorded run eating the daily cap."""
    api["status"] = _status(proposed_count=0, workable_count=0, active_strategies=[])
    recorded, kinds = [], []
    monkeypatch.setattr(poll, "_record_research_run",
                        lambda dry_run=False: recorded.append(1) or True)
    monkeypatch.setattr(poll, "invoke_agent", lambda prompt, agent, **kw: kinds.append(kw["operation"]))
    poll.main()
    assert kinds == []
    assert recorded == []


def test_a_pause_stops_new_sessions_and_lets_running_ones_finish(api, monkeypatch):
    api["settings"] = {"max_concurrent_agent_sessions": 1}
    api["videos"] = [_video("v1"), _video("v2")]
    release = threading.Event()
    started, finished = [], []

    def invoke(prompt, agent, **kw):
        vid = kw["attribution"][0]["video_id"]
        started.append(vid)
        release.wait(5)
        finished.append(vid)
        api["videos"] = [v for v in api["videos"] if v["id"] != vid]
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    t = _run_in_thread()
    time.sleep(0.2)
    api["status"] = _status(paused=True)
    time.sleep(0.2)
    release.set()
    t.join(5)
    assert not t.is_alive()
    assert started == finished == ["v1"]


def test_the_supervisor_exits_once_idle(api, monkeypatch):
    api["status"] = _status(workable_count=0)
    with patch("poll.invoke_agent") as invoke:
        t0 = time.monotonic()
        poll.main()
    invoke.assert_not_called()
    assert time.monotonic() - t0 < 2


def test_every_pass_touches_the_heartbeat(api, monkeypatch):
    api["status"] = _status(workable_count=0)
    poll.main()
    assert poll.HEARTBEAT.exists()


# ── The verdict: success is read from the database ──────────────────────────

def _scored(api, caplog, outcome, returncode, runs=1, start="VOICE_READY", timed_out=False):
    api["outcome"] = outcome
    session = poll._Session("pipeline", "video=v1", video_id="v1", start_status=start)
    session.runs, session.returncode, session.timed_out = runs, returncode, timed_out
    caplog.set_level(logging.INFO, logger=poll.log.name)
    return poll._score_session(session)


def test_a_changed_status_is_progress_whatever_the_exit_code(api, caplog):
    end = _scored(api, caplog, {"status": "RENDER_QUEUED", "count": 0, "stuck": False}, 1)
    assert end == "RENDER_QUEUED"
    assert api["outcomes"] == [("v1", "VOICE_READY")]
    assert "Progress: VOICE_READY → RENDER_QUEUED" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_no_progress_on_a_clean_exit_is_a_warning(api, caplog):
    """Exit 0 having done nothing is how these CLIs fail quietly."""
    _scored(api, caplog, {"status": "VOICE_READY", "count": 1, "stuck": False}, 0)
    [rec] = [r for r in caplog.records if "No progress" in r.getMessage()]
    assert rec.levelno == logging.WARNING
    assert "exit code 0" in rec.getMessage()


def test_no_progress_on_a_non_zero_exit_is_an_error(api, caplog):
    _scored(api, caplog, {"status": "VOICE_READY", "count": 2, "stuck": False}, 3,
            timed_out=True)
    [rec] = [r for r in caplog.records if "No progress" in r.getMessage()]
    assert rec.levelno == logging.ERROR
    assert "exit code 3, timed out" in rec.getMessage()
    assert "2 session(s) in a row" in rec.getMessage()


def test_a_session_that_never_started_a_process_says_so(api, caplog):
    _scored(api, caplog, {"status": "VOICE_READY", "count": 1, "stuck": False}, None, runs=0)
    assert "no agent process ran" in caplog.text


def test_a_stuck_flag_is_logged_as_an_error(api, caplog):
    _scored(api, caplog, {"status": "VOICE_READY", "count": 3, "stuck": True}, 0)
    stuck = [r for r in caplog.records if "flagged stuck" in r.getMessage()]
    assert stuck and stuck[0].levelno == logging.ERROR
    assert "Retry agent" in stuck[0].getMessage()


def test_a_voicing_session_that_ran_on_into_scene_work_is_flagged(api, caplog):
    """Its cost would otherwise be recorded as voicing without a trace."""
    _scored(api, caplog, {"status": "RENDER_QUEUED", "count": 0, "stuck": False}, 0,
            start="VOICING")
    assert any(r.levelno == logging.WARNING and "ran past its stage" in r.getMessage()
               for r in caplog.records)


def test_every_outcome_carries_its_session_key(api, caplog):
    session = poll._Session("pipeline", "video=v1", video_id="v1", start_status="VOICING")
    poll._score_session(session)
    assert api["keys"] == [session.key]


def test_a_replayed_outcome_is_logged_not_scored_again(api, caplog):
    """No second "No progress" line and no stuck error for an outcome the API
    had already counted."""
    _scored(api, caplog, {"status": "VOICE_READY", "count": 3, "stuck": True,
                          "replayed": True}, 0)
    assert "already recorded" in caplog.text
    assert "No progress" not in caplog.text and "flagged stuck" not in caplog.text


def test_an_unrecordable_outcome_fails_open(api, caplog, monkeypatch):
    monkeypatch.setattr(poll, "_post_outcome", lambda vid, st, key="": None)
    assert _scored(api, caplog, {}, 0) == ""


# ── The scene-claim cooldown ────────────────────────────────────────────────

def test_a_claim_window_video_waits_out_the_dead_sessions_claim(api, monkeypatch):
    """Redispatching at once would be refused with scene_work_claimed by the
    previous session's claim, and count as another no-progress session."""
    monkeypatch.setattr(poll, "CLAIM_COOLDOWN_SECS", 0.4)
    api["videos"] = [_video("v1", "VOICE_READY")]
    api["outcome"] = {"status": "VOICE_READY", "count": 1, "stuck": False}
    times = []

    def invoke(prompt, agent, **kw):
        times.append(time.monotonic())
        if len(times) == 2:
            api["videos"] = []
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    poll.main()
    assert len(times) == 2
    assert times[1] - times[0] >= 0.4


def test_a_paused_supervisor_does_not_wait_out_a_cooldown(api, monkeypatch):
    """No session could follow the wait, and the lock it holds is what an
    upgrade or a service stop waits for."""
    monkeypatch.setattr(poll, "CLAIM_COOLDOWN_SECS", 60)
    api["videos"] = [_video("v1", "VOICE_READY")]
    api["outcome"] = {"status": "VOICE_READY", "count": 1, "stuck": False}

    def invoke(prompt, agent, **kw):
        api["status"] = _status(paused=True)
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    t0 = time.monotonic()
    poll.main()
    assert time.monotonic() - t0 < 5


def test_no_cooldown_outside_the_claim_window(api, monkeypatch):
    monkeypatch.setattr(poll, "CLAIM_COOLDOWN_SECS", 60)
    api["videos"] = [_video("v1", "TOPIC_APPROVED")]
    api["outcome"] = {"status": "TOPIC_APPROVED", "count": 1, "stuck": False}
    calls = []

    def invoke(prompt, agent, **kw):
        calls.append(1)
        if len(calls) == 2:
            api["videos"] = []
    monkeypatch.setattr(poll, "invoke_agent", invoke)
    t0 = time.monotonic()
    poll.main()
    assert len(calls) == 2
    assert time.monotonic() - t0 < 5


# ── Session timeout: a real process group ───────────────────────────────────

def _gone(pgid) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_session_past_its_deadline_is_killed_with_its_children(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "KILL_GRACE_SECS", 1)
    session = poll._Session("pipeline", "video=v1", video_id="v1",
                            deadline=time.time() + 0.5)
    poll._current_session.set(session)
    try:
        t0 = time.monotonic()
        # A grandchild in the background: killing only the direct child would
        # leave it running, holding whatever the agent had started.
        result = poll._execute(["sh", "-c", "sleep 30 & echo $! > child; sleep 30"],
                               cwd=tmp_path)
    finally:
        poll._current_session.set(None)
    assert result.timed_out
    assert time.monotonic() - t0 < 5
    grandchild = int((tmp_path / "child").read_text())
    time.sleep(0.1)
    assert poll._proc_start(grandchild) is None
    # Still registered: its usage and outcome are recorded after this returns.
    assert [e["run_id"] for e in poll._registry_read()] == [result.run_id]


def test_a_child_that_ignores_sigterm_is_killed_after_the_grace(tmp_path, monkeypatch):
    """The leader exits on SIGTERM at once; its child ignores SIGTERM. Waiting on
    the leader alone would return immediately and leave the child running."""
    monkeypatch.setattr(poll, "KILL_GRACE_SECS", 1)
    session = poll._Session("pipeline", "video=v1", video_id="v1",
                            deadline=time.time() + 0.5)
    poll._current_session.set(session)
    try:
        result = poll._execute(
            ["sh", "-c", "(trap '' TERM; exec sleep 30) & echo $! > child; exec sleep 30"],
            cwd=tmp_path)
    finally:
        poll._current_session.set(None)
    assert result.timed_out
    child = int((tmp_path / "child").read_text())
    time.sleep(0.2)
    assert poll._proc_start(child) is None, "the TERM-ignoring child was SIGKILLed"


def test_a_timed_out_run_is_not_retried(monkeypatch, tmp_path):
    """A killed run says nothing about its flags; the retry chain must stop."""
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/claude")
    monkeypatch.setattr(poll, "resolve_agent_cwd", lambda agent: tmp_path)
    result = poll._Result(-15, "", "error: unknown option '--effort'", timed_out=True)
    with patch.object(poll, "_execute", return_value=result) as run:
        poll.invoke_agent("p", AGENT, effort="max")
    assert run.call_count == 1


# ── The registry and orphan adoption ────────────────────────────────────────

def test_a_session_stays_registered_until_its_bookkeeping_is_done(tmp_path):
    """A supervisor that dies after the agent exits but before the usage and
    outcome are recorded must leave its successor something to finish: the
    entry outlives the process, the output files outlive the process until the
    usage is recorded, and the entry goes only once the session is scored."""
    session = poll._Session("pipeline", "video=v1", video_id="v1", start_status="VOICING",
                            deadline=time.time() + 30)
    results = []

    def run():
        poll._current_session.set(session)
        results.append(poll._execute(["sleep", "0.5"], cwd=tmp_path))
    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.2)
    during = poll._registry_read()
    t.join(5)
    assert [(e["video_id"], e["start_status"]) for e in during] == [("v1", "VOICING")]
    assert during[0]["proc_start"], "pid reuse is detected by the start time"
    [entry] = poll._registry_read()
    assert entry["usage_done"] is False and entry["session_key"] == session.key
    assert Path(entry["stdout"]).exists(), "kept for a successor to record the usage from"
    poll._registry_run_done(results[0].run_id)
    [entry] = poll._registry_read()
    assert entry["usage_done"] is True
    assert not list(poll.SESSIONS_DIR.iterdir()), "files go once the usage is recorded"
    poll._registry_remove_session(session.key)
    assert poll._registry_read() == []


def test_a_session_is_deregistered_only_after_it_is_scored(api, monkeypatch, tmp_path):
    """End to end through _run_session: the entry is there while the outcome is
    being posted, and gone after."""
    seen_at_scoring = []
    real = poll._post_outcome

    def outcome(vid, st, key=""):
        seen_at_scoring.append([e["run_id"] for e in poll._registry_read()])
        return real(vid, st, key)
    monkeypatch.setattr(poll, "_post_outcome", outcome)
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/bin/true")
    monkeypatch.setattr(poll, "resolve_agent_cwd", lambda agent: tmp_path)
    monkeypatch.setattr(poll, "_report_usage", lambda *a, **k: None)
    session = poll._Session("pipeline", "video=v1", video_id="v1", start_status="VOICING",
                            agent_id="claude", operation="agent_pipeline",
                            deadline=time.time() + 30)
    import contextvars
    contextvars.Context().run(poll._run_session, session, "p", AGENT, "opus", "")
    assert len(seen_at_scoring) == 1 and len(seen_at_scoring[0]) == 1
    assert poll._registry_read() == []


def _orphan(tmp_path, seconds, *, deadline_in=600, video="v1"):
    """A real process left behind by a 'dead' supervisor, and its registry entry."""
    out, err = tmp_path / "o.out", tmp_path / "o.err"
    out.write_text("")
    err.write_text("")
    proc = subprocess.Popen(["sleep", str(seconds)], start_new_session=True)
    # In production init reaps an orphan; here the test is its parent, and an
    # unreaped zombie still counts as a member of its process group.
    threading.Thread(target=proc.wait, daemon=True).start()
    entry = {"pid": proc.pid, "proc_start": poll._proc_start(proc.pid), "run_id": "run-1",
             "session_key": "sess-1", "usage_done": False, "lane": "pipeline",
             "label": f"video={video}", "video_id": video, "start_status": "VOICING",
             "agent_id": "claude", "model": "opus", "operation": "agent_pipeline",
             "attribution": [{"video_id": video, "stage": "VOICING"}],
             "deadline": time.time() + deadline_in, "stdout": str(out), "stderr": str(err)}
    poll._registry_write([entry])
    return proc


def test_a_live_orphan_is_adopted_holds_its_video_and_is_scored_when_it_exits(
        api, monkeypatch, tmp_path):
    # Usage is read through the agent's CLI, so finishing an orphan skips it
    # when the binary is not on PATH -- as on a CI runner with no agent installed.
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/bin/claude")
    proc = _orphan(tmp_path, 0.6)
    api["videos"] = [_video("v1", "VOICING")]
    with patch("poll.invoke_agent") as invoke, patch("poll._report_usage") as usage:
        t = _run_in_thread()
        time.sleep(0.3)
        # Adopted, so its video is in flight and not dispatched again.
        invoke.assert_not_called()
        proc.wait()
        api["videos"] = []
        t.join(5)
    assert not t.is_alive()
    assert api["outcomes"] == [("v1", "VOICING")]
    usage.assert_called_once()
    assert poll._registry_read() == []


def test_an_adopted_research_session_keeps_the_research_lane_single(api, monkeypatch, tmp_path):
    proc = _orphan(tmp_path, 0.6)
    entries = poll._registry_read()
    entries[0].update(lane="research", label="research", video_id="", start_status="")
    poll._registry_write(entries)
    api["status"] = _status(proposed_count=0, workable_count=0)
    with patch("poll.invoke_agent") as invoke, patch("poll._report_usage"):
        t = _run_in_thread()
        time.sleep(0.3)
        started_while_adopted = invoke.call_count
        proc.wait()
        t.join(5)
    assert started_while_adopted == 0
    assert invoke.call_count == 1, "research runs once the adopted one has ended"


def test_an_orphan_past_its_deadline_is_killed(api, monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "KILL_GRACE_SECS", 0.2)
    proc = _orphan(tmp_path, 30, deadline_in=-1)
    api["status"] = _status(workable_count=0)
    with patch("poll._report_usage"):
        t = _run_in_thread()
        t.join(5)
    assert proc.poll() is not None, "the orphan was stopped"
    assert api["outcomes"] == [("v1", "VOICING")]


def test_an_overdue_orphans_term_ignoring_child_is_killed_within_the_grace(
        api, monkeypatch, tmp_path):
    """The leader exits on SIGTERM; its child ignores it. The group is still
    alive, so the orphan is not finished — it gets SIGKILL at KILL_GRACE_SECS,
    not on some later 60-second pass."""
    monkeypatch.setattr(poll, "LOOP_WAIT_SECS", 30)
    monkeypatch.setattr(poll, "KILL_GRACE_SECS", 1)
    proc = subprocess.Popen(
        ["sh", "-c", "(trap '' TERM; exec sleep 30) & echo $! > child; exec sleep 30"],
        cwd=tmp_path, start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()
    time.sleep(0.2)
    poll._registry_write([{"pid": proc.pid, "proc_start": poll._proc_start(proc.pid),
                           "run_id": "run-1", "session_key": "sess-1", "usage_done": True,
                           "lane": "pipeline", "label": "video=v1", "video_id": "v1",
                           "start_status": "VOICING", "agent_id": "claude",
                           "deadline": time.time() - 1, "stdout": "", "stderr": ""}])
    api["status"] = _status(workable_count=0)
    child = int((tmp_path / "child").read_text())
    t0 = time.monotonic()
    with patch("poll._report_usage"):
        poll.main()
    assert time.monotonic() - t0 < 10
    time.sleep(0.2)
    assert poll._proc_start(child) is None, "the TERM-ignoring child was SIGKILLed"
    assert api["outcomes"] == [("v1", "VOICING")]


def test_an_adopted_sessions_end_is_noticed_within_seconds(api, monkeypatch, tmp_path):
    """Adopted processes are not our children, so nothing wakes the loop when
    one ends; it looks every second rather than once per LOOP_WAIT_SECS."""
    monkeypatch.setattr(poll, "LOOP_WAIT_SECS", 30)
    _orphan(tmp_path, 0.5)
    api["status"] = _status(workable_count=0)
    t0 = time.monotonic()
    with patch("poll._report_usage"):
        poll.main()
    assert time.monotonic() - t0 < 5
    assert api["outcomes"] == [("v1", "VOICING")]


def test_a_finished_but_unrecorded_session_is_recorded_by_the_next_supervisor(
        api, monkeypatch, tmp_path):
    """The supervisor died after the agent exited but before recording it. The
    successor records the usage under the run id it was registered with — so a
    report the dead one had already made is not counted twice — and scores the
    session once. A run already recorded is not reported again."""
    out = tmp_path / "r2.out"
    out.write_text('{"type": "result"}')
    common = {"proc_start": "1", "session_key": "sess-9", "lane": "pipeline",
              "label": "video=v1", "video_id": "v1", "start_status": "TOPIC_APPROVED",
              "agent_id": "claude", "model": "opus", "operation": "agent_pipeline",
              "attribution": [{"video_id": "v1", "stage": "TOPIC_APPROVED"}],
              "deadline": time.time() + 600}
    poll._registry_write([
        {**common, "pid": 999991, "run_id": "run-a", "usage_done": True,
         "stdout": "", "stderr": ""},
        {**common, "pid": 999992, "run_id": "run-b", "usage_done": False,
         "stdout": str(out), "stderr": str(tmp_path / "r2.err")}])
    api["status"] = _status(workable_count=0)
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/bin/claude")
    monkeypatch.setattr(poll, "resolve_agent_cwd", lambda agent: tmp_path)
    reported = []
    monkeypatch.setattr(poll, "_report_usage",
                        lambda *a, session_id="", **k: reported.append(session_id))
    poll.main()
    assert reported == ["run-b"]
    assert api["outcomes"] == [("v1", "TOPIC_APPROVED")]
    assert api["keys"] == ["sess-9"], "re-reported under the session's own key"
    assert poll._registry_read() == []
    assert not out.exists()


def test_a_reused_pid_is_not_mistaken_for_an_orphan(api, monkeypatch, tmp_path):
    """The pid now names a different process (here, the test runner itself):
    adopting it would wait on — or kill — something unrelated."""
    entry = {"pid": os.getpid(), "proc_start": "1", "lane": "pipeline", "label": "video=v1",
             "video_id": "v1", "start_status": "VOICING", "agent_id": "claude",
             "deadline": time.time() - 1, "stdout": "", "stderr": ""}
    poll._registry_write([entry])
    api["status"] = _status(workable_count=0)
    with patch("poll._report_usage"), patch("os.killpg") as killpg:
        poll.main()
    killpg.assert_not_called()
    # Treated as finished: its bookkeeping ran and the entry is gone.
    assert api["outcomes"] == [("v1", "VOICING")]
    assert poll._registry_read() == []


# ── The lock, the heartbeat and the watchdog tick ───────────────────────────

def _hold_lock():
    import fcntl
    poll.LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    fh = open(poll.LOCKFILE, "w")
    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fh


def test_a_tick_finding_a_stale_heartbeat_logs_an_error_and_kills_nothing(
        api, caplog, monkeypatch):
    fh = _hold_lock()
    try:
        poll.HEARTBEAT.touch()
        old = time.time() - poll.HEARTBEAT_STALE_SECS - 60
        os.utime(poll.HEARTBEAT, (old, old))
        with patch("os.kill") as kill, patch("os.killpg") as killpg, \
                pytest.raises(SystemExit) as exc:
            poll.main()
    finally:
        fh.close()
    assert exc.value.code == 0
    kill.assert_not_called()
    killpg.assert_not_called()
    assert any(r.levelno == logging.ERROR and "may be hung" in r.getMessage()
               for r in caplog.records)


def test_a_tick_finding_a_fresh_heartbeat_just_exits(api, caplog):
    fh = _hold_lock()
    try:
        poll.HEARTBEAT.touch()
        with pytest.raises(SystemExit):
            poll.main()
    finally:
        fh.close()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# ── Per-session log context ─────────────────────────────────────────────────

def test_every_line_names_its_session():
    """Three sessions interleave in one poll.log; without a label per line it
    is unreadable. The JSONL sink gets video_id / profile_id the same way."""
    flt = poll._SessionContext()
    rec = logging.LogRecord("poll", logging.INFO, "", 0, "m", (), None)
    flt.filter(rec)
    assert rec.session == "supervisor"

    def in_session():
        poll._current_session.set(poll._Session("pipeline", "video=v9", video_id="v9"))
        r = logging.LogRecord("poll", logging.INFO, "", 0, "m", (), None)
        flt.filter(r)
        return r
    import contextvars
    r = contextvars.Context().run(in_session)
    assert r.session == "video=v9" and r.video_id == "v9"
    # The session never leaks back into the caller's context.
    assert poll._current_session.get() is None


def test_the_cooldown_matches_the_mcp_claim_ttl_and_statuses():
    """Read as source text: poll.py cannot import the MCP server. A cooldown
    shorter than the TTL brings the scene_work_claimed refusal back; a claim
    status missing here means no cooldown where one is needed."""
    import re
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = open(os.path.join(root, "mcp", "server.py")).read()
    ttl = int(re.search(r"^SCENE_CLAIM_TTL_SECS = (\d+)", src, re.M).group(1))
    statuses = set(re.findall(r'"([A-Z_]+)"', re.search(
        r"^_CLAIM_STATUSES = frozenset\(\{(.*?)\}\)", src, re.M).group(1)))
    assert poll.CLAIM_COOLDOWN_SECS == ttl
    assert set(poll.CLAIM_STATUSES) == statuses
